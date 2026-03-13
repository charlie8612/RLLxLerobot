"""
自己寫的 Diffusion Policy，和 LeRobot 內建的架構一模一樣，但全部攤開在一個檔案裡。
你可以直接改任何元件：換 backbone、改 UNet、換 noise scheduler、改 loss。

架構總覽：
    ┌──────────────────────────────────────────────────────────────┐
    │                     DiffusionPolicy                          │
    │                                                              │
    │  Inputs:                                                     │
    │    observation.images.wrist  (B, n_obs, C, H, W)             │
    │    observation.state         (B, n_obs, 7)                   │
    │                                                              │
    │  ┌──────────────┐                                            │
    │  │ RgbEncoder   │  image → ResNet18 → SpatialSoftmax → 64d  │
    │  └──────┬───────┘                                            │
    │         ↓                                                    │
    │  concat(image_feat, state) → global_cond                     │
    │         ↓                                                    │
    │  ┌──────────────┐                                            │
    │  │ UNet1d       │  (noisy_action, timestep, global_cond)     │
    │  │              │   → predicted noise (or sample)            │
    │  └──────────────┘                                            │
    │                                                              │
    │  Training: MSE(pred, target)                                 │
    │  Inference: iterative denoising → clean action trajectory    │
    └──────────────────────────────────────────────────────────────┘
"""

import math
from collections import deque

import einops
import numpy as np
import torch
import torch.nn.functional as F
import torchvision
from diffusers.schedulers.scheduling_ddpm import DDPMScheduler
from diffusers.schedulers.scheduling_ddim import DDIMScheduler
from torch import Tensor, nn


# ===========================================================================
#  Config（所有超參數集中在這裡）
# ===========================================================================
class DiffusionPolicyConfig:
    def __init__(
        self,
        # --- 動作空間 ---
        state_dim: int = 7,          # observation.state 維度（Piper: 6 joints + 1 gripper）
        action_dim: int = 7,         # action 維度（跟 state_dim 一樣）
        # --- 觀察與動作序列 ---
        n_obs_steps: int = 2,        # 用幾步歷史觀察
        horizon: int = 16,           # diffusion 預測的 action 序列長度
        n_action_steps: int = 8,     # 實際執行幾步
        # --- Vision Encoder ---
        vision_backbone: str = "resnet18",
        pretrained_backbone_weights: str = "ResNet18_Weights.IMAGENET1K_V1",
        num_keypoints: int = 32,     # SpatialSoftmax keypoints → 輸出 keypoints*2 維
        image_shape: tuple = (3, 480, 640),  # (C, H, W) 輸入影像大小
        num_cameras: int = 1,        # camera 數量
        # --- UNet ---
        down_dims: tuple = (512, 1024, 2048),  # 每層 channel，層數 = len(down_dims)
        kernel_size: int = 5,
        n_groups: int = 8,           # GroupNorm groups
        diffusion_step_embed_dim: int = 128,
        use_film_scale: bool = True, # FiLM scale modulation
        # --- Diffusion ---
        noise_scheduler_type: str = "DDPM",  # "DDPM" / "DDIM"
        num_train_timesteps: int = 100,
        num_inference_steps: int = 100,      # DDIM 可以設更少（如 10）加速推論
        beta_schedule: str = "squaredcos_cap_v2",
        beta_start: float = 0.0001,
        beta_end: float = 0.02,
        prediction_type: str = "epsilon",    # "epsilon" / "sample"
        clip_sample: bool = True,
        clip_sample_range: float = 1.0,
    ):
        # 把所有參數存成 attribute
        for k, v in locals().items():
            if k != "self":
                setattr(self, k, v)

        # 驗證
        downsampling_factor = 2 ** len(down_dims)
        assert horizon % downsampling_factor == 0, (
            f"horizon ({horizon}) 必須是 {downsampling_factor} 的倍數 "
            f"(因為 UNet 有 {len(down_dims)} 層 downsampling)"
        )


# ===========================================================================
#  Vision Encoder: ResNet → SpatialSoftmax → Linear
# ===========================================================================
class SpatialSoftmax(nn.Module):
    """把 2D feature map 轉成 keypoint 座標 (x, y)。"""

    def __init__(self, in_c, in_h, in_w, num_kp):
        super().__init__()
        self.conv = nn.Conv2d(in_c, num_kp, kernel_size=1)
        self.num_kp = num_kp
        self.in_h = in_h
        self.in_w = in_w

        # 建立座標 grid
        pos_x, pos_y = np.meshgrid(
            np.linspace(-1.0, 1.0, in_w),
            np.linspace(-1.0, 1.0, in_h),
        )
        pos_x = torch.from_numpy(pos_x.reshape(in_h * in_w, 1)).float()
        pos_y = torch.from_numpy(pos_y.reshape(in_h * in_w, 1)).float()
        self.register_buffer("pos_grid", torch.cat([pos_x, pos_y], dim=1))

    def forward(self, x: Tensor) -> Tensor:
        """(B, C, H, W) → (B, num_kp * 2)"""
        x = self.conv(x)                                     # (B, num_kp, H, W)
        x = x.reshape(-1, self.in_h * self.in_w)             # (B*num_kp, H*W)
        attention = F.softmax(x, dim=-1)                      # softmax over spatial
        expected_xy = attention @ self.pos_grid                # (B*num_kp, 2)
        return expected_xy.reshape(-1, self.num_kp * 2)       # (B, num_kp*2)


class RgbEncoder(nn.Module):
    """
    影像編碼器：ResNet backbone → SpatialSoftmax → Linear

    你可以：
    - 換 backbone：改成 resnet34/50，或換成完全不同的 CNN/ViT
    - 改 SpatialSoftmax：換成 GlobalAvgPool 或其他 pooling
    - 改 output dim：調 num_keypoints
    """

    def __init__(self, cfg: DiffusionPolicyConfig):
        super().__init__()
        # --- Backbone ---
        # 拿 ResNet 但去掉最後的 avgpool + fc
        backbone_model = getattr(torchvision.models, cfg.vision_backbone)(
            weights=cfg.pretrained_backbone_weights
        )
        self.backbone = nn.Sequential(*(list(backbone_model.children())[:-2]))

        # --- 算 feature map shape ---
        with torch.no_grad():
            dummy = torch.zeros(1, *cfg.image_shape)
            feat = self.backbone(dummy)
            _, feat_c, feat_h, feat_w = feat.shape

        # --- Pooling ---
        self.pool = SpatialSoftmax(feat_c, feat_h, feat_w, cfg.num_keypoints)
        self.feature_dim = cfg.num_keypoints * 2

        # --- Output projection ---
        self.out = nn.Linear(self.feature_dim, self.feature_dim)
        self.relu = nn.ReLU()

    def forward(self, x: Tensor) -> Tensor:
        """(B, C, H, W) → (B, feature_dim)"""
        x = self.backbone(x)
        x = self.pool(x)
        x = self.relu(self.out(x))
        return x


# ===========================================================================
#  UNet 1D: action denoiser
# ===========================================================================
class SinusoidalPosEmb(nn.Module):
    """Timestep → sinusoidal embedding"""

    def __init__(self, dim):
        super().__init__()
        self.dim = dim

    def forward(self, x: Tensor) -> Tensor:
        half = self.dim // 2
        emb = math.log(10000) / (half - 1)
        emb = torch.exp(torch.arange(half, device=x.device) * -emb)
        emb = x.unsqueeze(-1) * emb.unsqueeze(0)
        return torch.cat([emb.sin(), emb.cos()], dim=-1)


class Conv1dBlock(nn.Module):
    """Conv1d → GroupNorm → Mish"""

    def __init__(self, in_ch, out_ch, kernel_size, n_groups=8):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size, padding=kernel_size // 2),
            nn.GroupNorm(n_groups, out_ch),
            nn.Mish(),
        )

    def forward(self, x):
        return self.block(x)


class ConditionalResBlock1d(nn.Module):
    """
    Residual block with FiLM conditioning.
    FiLM: output = scale * conv(x) + bias（用 condition 來調變 feature）

    你可以改這裡來換不同的 conditioning 方式，例如 cross-attention。
    """

    def __init__(self, in_ch, out_ch, cond_dim, kernel_size=5, n_groups=8, use_film_scale=True):
        super().__init__()
        self.conv1 = Conv1dBlock(in_ch, out_ch, kernel_size, n_groups)
        self.conv2 = Conv1dBlock(out_ch, out_ch, kernel_size, n_groups)

        # FiLM: condition → bias (and optionally scale)
        self.use_film_scale = use_film_scale
        film_out_dim = out_ch * 2 if use_film_scale else out_ch
        self.cond_encoder = nn.Sequential(
            nn.Mish(),
            nn.Linear(cond_dim, film_out_dim),
        )

        # Residual connection
        self.residual_conv = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()

    def forward(self, x: Tensor, cond: Tensor) -> Tensor:
        """
        x:    (B, in_ch, T)
        cond: (B, cond_dim)
        """
        h = self.conv1(x)

        # FiLM modulation
        film = self.cond_encoder(cond).unsqueeze(-1)  # (B, film_dim, 1)
        if self.use_film_scale:
            scale, bias = film.chunk(2, dim=1)
            h = h * (1 + scale) + bias
        else:
            h = h + film

        h = self.conv2(h)
        return h + self.residual_conv(x)


class UNet1d(nn.Module):
    """
    1D UNet for action denoising.

    結構：
        input (B, action_dim, horizon)
            ↓
        [Encoder] down_block × N (with skip connections)
            ↓
        [Middle] 2 × ResBlock
            ↓
        [Decoder] up_block × N (concat skip connections)
            ↓
        output (B, action_dim, horizon)

    每個 block 都用 FiLM conditioning（timestep + observation encoding）。

    你可以：
    - 改 down_dims 調大小
    - 加 attention layer
    - 換成 Transformer
    """

    def __init__(self, cfg: DiffusionPolicyConfig, global_cond_dim: int):
        super().__init__()

        # --- Timestep encoder ---
        d = cfg.diffusion_step_embed_dim
        self.timestep_encoder = nn.Sequential(
            SinusoidalPosEmb(d),
            nn.Linear(d, d * 4),
            nn.Mish(),
            nn.Linear(d * 4, d),
        )

        # FiLM condition = timestep_emb + global_cond
        cond_dim = d + global_cond_dim

        res_kwargs = dict(
            cond_dim=cond_dim,
            kernel_size=cfg.kernel_size,
            n_groups=cfg.n_groups,
            use_film_scale=cfg.use_film_scale,
        )

        # --- Encoder (downsampling) ---
        in_out = [(cfg.action_dim, cfg.down_dims[0])] + list(
            zip(cfg.down_dims[:-1], cfg.down_dims[1:])
        )
        self.down_modules = nn.ModuleList()
        for i, (dim_in, dim_out) in enumerate(in_out):
            is_last = i >= len(in_out) - 1
            self.down_modules.append(nn.ModuleList([
                ConditionalResBlock1d(dim_in, dim_out, **res_kwargs),
                ConditionalResBlock1d(dim_out, dim_out, **res_kwargs),
                nn.Conv1d(dim_out, dim_out, 3, 2, 1) if not is_last else nn.Identity(),
            ]))

        # --- Middle ---
        mid_dim = cfg.down_dims[-1]
        self.mid_modules = nn.ModuleList([
            ConditionalResBlock1d(mid_dim, mid_dim, **res_kwargs),
            ConditionalResBlock1d(mid_dim, mid_dim, **res_kwargs),
        ])

        # --- Decoder (upsampling) ---
        self.up_modules = nn.ModuleList()
        for i, (dim_out, dim_in) in enumerate(reversed(in_out[1:])):
            is_last = i >= len(in_out) - 1
            self.up_modules.append(nn.ModuleList([
                ConditionalResBlock1d(dim_in * 2, dim_out, **res_kwargs),  # *2 for skip
                ConditionalResBlock1d(dim_out, dim_out, **res_kwargs),
                nn.ConvTranspose1d(dim_out, dim_out, 4, 2, 1) if not is_last else nn.Identity(),
            ]))

        # --- Final conv ---
        self.final_conv = nn.Sequential(
            Conv1dBlock(cfg.down_dims[0], cfg.down_dims[0], kernel_size=cfg.kernel_size),
            nn.Conv1d(cfg.down_dims[0], cfg.action_dim, 1),
        )

    def forward(self, x: Tensor, timestep: Tensor, global_cond: Tensor) -> Tensor:
        """
        x:           (B, horizon, action_dim) noisy action
        timestep:    (B,) diffusion timestep
        global_cond: (B, global_cond_dim) observation encoding
        Returns:     (B, horizon, action_dim) predicted noise or sample
        """
        # (B, T, D) → (B, D, T) for conv1d
        x = einops.rearrange(x, "b t d -> b d t")

        # Condition = timestep embedding + observation
        t_emb = self.timestep_encoder(timestep)
        cond = torch.cat([t_emb, global_cond], dim=-1)

        # Encoder
        skips = []
        for res1, res2, downsample in self.down_modules:
            x = res1(x, cond)
            x = res2(x, cond)
            skips.append(x)
            x = downsample(x)

        # Middle
        for mid_block in self.mid_modules:
            x = mid_block(x, cond)

        # Decoder
        for res1, res2, upsample in self.up_modules:
            x = torch.cat([x, skips.pop()], dim=1)  # skip connection
            x = res1(x, cond)
            x = res2(x, cond)
            x = upsample(x)

        x = self.final_conv(x)

        # (B, D, T) → (B, T, D)
        return einops.rearrange(x, "b d t -> b t d")


# ===========================================================================
#  Diffusion Policy: 把所有東西組起來
# ===========================================================================
class DiffusionPolicyCustom(nn.Module):
    """
    完整的 Diffusion Policy model.

    你可以改的地方：
    - self.rgb_encoder: 換成任何 vision encoder
    - self.unet: 換成任何 denoising network（甚至 Transformer）
    - self.noise_scheduler: 換 noise schedule
    - compute_loss(): 改 loss function
    - generate_actions(): 改 inference 流程
    """

    def __init__(self, cfg: DiffusionPolicyConfig):
        super().__init__()
        self.cfg = cfg

        # --- Vision Encoder ---
        self.rgb_encoder = RgbEncoder(cfg)

        # global_cond_dim = image_feat * n_cameras + state_dim，再乘 n_obs_steps
        single_step_cond_dim = self.rgb_encoder.feature_dim * cfg.num_cameras + cfg.state_dim
        global_cond_dim = single_step_cond_dim * cfg.n_obs_steps

        # --- UNet ---
        self.unet = UNet1d(cfg, global_cond_dim=global_cond_dim)

        # --- Noise Scheduler ---
        scheduler_cls = DDPMScheduler if cfg.noise_scheduler_type == "DDPM" else DDIMScheduler
        self.noise_scheduler = scheduler_cls(
            num_train_timesteps=cfg.num_train_timesteps,
            beta_start=cfg.beta_start,
            beta_end=cfg.beta_end,
            beta_schedule=cfg.beta_schedule,
            clip_sample=cfg.clip_sample,
            clip_sample_range=cfg.clip_sample_range,
            prediction_type=cfg.prediction_type,
        )

        # --- Inference 用的 action queue ---
        self._action_queue = deque(maxlen=cfg.n_action_steps)

    # ------------------------------------------------------------------
    #  Observation Encoding
    # ------------------------------------------------------------------
    def encode_observations(self, batch: dict) -> Tensor:
        """
        把 images + state 編碼成一個 global conditioning vector.

        你可以在這裡加入其他 modality（例如 depth、force sensor）。
        """
        B = batch["observation.state"].shape[0]
        n_obs = self.cfg.n_obs_steps
        cond_parts = []

        # --- Encode images ---
        # images shape: (B, n_obs, n_cameras, C, H, W)
        images = batch["observation.images"]
        # Flatten batch and time dims for the encoder
        imgs_flat = images.reshape(-1, *images.shape[-3:])  # (B*n_obs*n_cam, C, H, W)
        img_feat = self.rgb_encoder(imgs_flat)               # (B*n_obs*n_cam, feat_dim)
        img_feat = img_feat.reshape(B, n_obs, -1)            # (B, n_obs, n_cam*feat_dim)
        cond_parts.append(img_feat)

        # --- State ---
        state = batch["observation.state"]                    # (B, n_obs, state_dim)
        cond_parts.append(state)

        # --- Concat all and flatten time steps ---
        cond = torch.cat(cond_parts, dim=-1)                  # (B, n_obs, cond_dim_per_step)
        cond = cond.flatten(1)                                # (B, n_obs * cond_dim_per_step)
        return cond

    # ------------------------------------------------------------------
    #  Training: compute loss
    # ------------------------------------------------------------------
    def compute_loss(self, batch: dict) -> Tensor:
        """
        Training 的 forward pass.

        流程：
        1. 編碼 observation → global_cond
        2. 取 ground truth action trajectory
        3. 隨機加噪 → noisy_trajectory
        4. UNet 預測 noise（或 clean sample）
        5. 算 loss

        === 想改 loss 就改這裡 ===
        """
        global_cond = self.encode_observations(batch)

        # Ground truth action trajectory
        trajectory = batch["action"]  # (B, horizon, action_dim)

        # 隨機噪聲
        noise = torch.randn_like(trajectory)

        # 隨機 timestep
        timesteps = torch.randint(
            0, self.noise_scheduler.config.num_train_timesteps,
            (trajectory.shape[0],), device=trajectory.device,
        ).long()

        # 加噪
        noisy_trajectory = self.noise_scheduler.add_noise(trajectory, noise, timesteps)

        # UNet 預測
        pred = self.unet(noisy_trajectory, timesteps, global_cond)

        # Target
        if self.cfg.prediction_type == "epsilon":
            target = noise
        else:
            target = trajectory

        # ========== 改 Loss 在這裡 ==========
        loss = F.mse_loss(pred, target)

        # 範例: 對 gripper 加大 weight
        # per_dim = F.mse_loss(pred, target, reduction="none")  # (B, horizon, 7)
        # w = torch.ones(7, device=pred.device)
        # w[6] = 5.0
        # loss = (per_dim * w).mean()

        return loss

    # ------------------------------------------------------------------
    #  Inference: generate action trajectory
    # ------------------------------------------------------------------
    @torch.no_grad()
    def generate_actions(self, batch: dict) -> Tensor:
        """
        Inference: 從純噪聲開始，反覆 denoise 得到 clean action trajectory.

        Returns: (B, horizon, action_dim)
        """
        global_cond = self.encode_observations(batch)
        B = global_cond.shape[0]

        # 從純噪聲開始
        trajectory = torch.randn(
            (B, self.cfg.horizon, self.cfg.action_dim),
            device=global_cond.device,
        )

        # 設定 inference timesteps
        self.noise_scheduler.set_timesteps(self.cfg.num_inference_steps, device=global_cond.device)

        # 反覆 denoise
        for t in self.noise_scheduler.timesteps:
            timestep = t.expand(B)
            pred = self.unet(trajectory, timestep, global_cond)
            trajectory = self.noise_scheduler.step(pred, t, trajectory).prev_sample

        return trajectory

    # ------------------------------------------------------------------
    #  Single-step inference（給 eval loop 用）
    # ------------------------------------------------------------------
    @torch.no_grad()
    def select_action(self, obs: dict) -> Tensor:
        """
        給即時推論用。內部維護一個 action queue：
        - queue 空了 → 呼叫 generate_actions 產生一整段
        - 每次 pop 一個 action 出來執行

        obs: 單一時間步的觀察（會自動 unsqueeze batch dim）
        Returns: (action_dim,) 單一 action
        """
        if len(self._action_queue) == 0:
            actions = self.generate_actions(obs)            # (1, horizon, action_dim)
            # 只取前 n_action_steps 步
            actions = actions[0, :self.cfg.n_action_steps]  # (n_action_steps, action_dim)
            self._action_queue.extend(actions)

        return self._action_queue.popleft()

    def reset(self):
        """清空 action queue（新 episode 開始時呼叫）"""
        self._action_queue.clear()
