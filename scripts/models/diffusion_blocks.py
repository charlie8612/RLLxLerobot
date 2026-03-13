"""
Diffusion Policy 積木箱 — 可重用的零件，自由組合。

這裡只有 building blocks，沒有「完整模型」。
你在訓練腳本裡自己決定怎麼組裝。

零件清單:
    Vision:   SpatialSoftmax, RgbEncoder
    UNet:     SinusoidalPosEmb, Conv1dBlock, ConditionalResBlock1d, UNet1d
    Noise:    make_noise_scheduler()
"""

import math

import einops
import numpy as np
import torch
import torch.nn.functional as F
import torchvision
from diffusers.schedulers.scheduling_ddim import DDIMScheduler
from diffusers.schedulers.scheduling_ddpm import DDPMScheduler
from torch import Tensor, nn


# ===========================================================================
#  Vision blocks
# ===========================================================================

class SpatialSoftmax(nn.Module):
    """2D feature map → (num_kp * 2) keypoint coordinates."""

    def __init__(self, in_c: int, in_h: int, in_w: int, num_kp: int):
        super().__init__()
        self.conv = nn.Conv2d(in_c, num_kp, kernel_size=1)
        self.num_kp = num_kp
        self.in_h = in_h
        self.in_w = in_w

        pos_x, pos_y = np.meshgrid(
            np.linspace(-1.0, 1.0, in_w),
            np.linspace(-1.0, 1.0, in_h),
        )
        pos_x = torch.from_numpy(pos_x.reshape(in_h * in_w, 1)).float()
        pos_y = torch.from_numpy(pos_y.reshape(in_h * in_w, 1)).float()
        self.register_buffer("pos_grid", torch.cat([pos_x, pos_y], dim=1))

    def forward(self, x: Tensor) -> Tensor:
        x = self.conv(x)
        x = x.reshape(-1, self.in_h * self.in_w)
        attention = F.softmax(x, dim=-1)
        expected_xy = attention @ self.pos_grid
        return expected_xy.reshape(-1, self.num_kp * 2)


class RgbEncoder(nn.Module):
    """
    Image → feature vector.

    用法:
        enc = RgbEncoder(backbone="resnet18", image_shape=(3, 480, 640), num_keypoints=32)
        feat = enc(images)  # (B, C, H, W) → (B, feature_dim)
    """

    def __init__(
        self,
        backbone: str = "resnet18",
        pretrained_weights: str = "ResNet18_Weights.IMAGENET1K_V1",
        image_shape: tuple = (3, 480, 640),
        num_keypoints: int = 32,
    ):
        super().__init__()
        backbone_model = getattr(torchvision.models, backbone)(weights=pretrained_weights)
        self.backbone = nn.Sequential(*(list(backbone_model.children())[:-2]))

        with torch.no_grad():
            dummy = torch.zeros(1, *image_shape)
            feat = self.backbone(dummy)
            _, feat_c, feat_h, feat_w = feat.shape

        self.pool = SpatialSoftmax(feat_c, feat_h, feat_w, num_keypoints)
        self.feature_dim = num_keypoints * 2
        self.out = nn.Sequential(nn.Linear(self.feature_dim, self.feature_dim), nn.ReLU())

    def forward(self, x: Tensor) -> Tensor:
        return self.out(self.pool(self.backbone(x)))


# ===========================================================================
#  UNet 1D blocks
# ===========================================================================

class SinusoidalPosEmb(nn.Module):
    """Scalar timestep → sinusoidal embedding vector."""

    def __init__(self, dim: int):
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

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, n_groups: int = 8):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size, padding=kernel_size // 2),
            nn.GroupNorm(n_groups, out_ch),
            nn.Mish(),
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.block(x)


class ConditionalResBlock1d(nn.Module):
    """Residual block with FiLM conditioning: output = scale * conv(x) + bias"""

    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        cond_dim: int,
        kernel_size: int = 5,
        n_groups: int = 8,
        use_film_scale: bool = True,
    ):
        super().__init__()
        self.conv1 = Conv1dBlock(in_ch, out_ch, kernel_size, n_groups)
        self.conv2 = Conv1dBlock(out_ch, out_ch, kernel_size, n_groups)
        self.use_film_scale = use_film_scale
        film_out_dim = out_ch * 2 if use_film_scale else out_ch
        self.cond_encoder = nn.Sequential(nn.Mish(), nn.Linear(cond_dim, film_out_dim))
        self.residual_conv = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()

    def forward(self, x: Tensor, cond: Tensor) -> Tensor:
        h = self.conv1(x)
        film = self.cond_encoder(cond).unsqueeze(-1)
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

    用法:
        unet = UNet1d(
            input_dim=7,         # action_dim
            global_cond_dim=142, # observation encoding size
            down_dims=(512, 1024, 2048),
        )
        pred = unet(noisy_actions, timestep, global_cond)
    """

    def __init__(
        self,
        input_dim: int,
        global_cond_dim: int,
        down_dims: tuple = (512, 1024, 2048),
        diffusion_step_embed_dim: int = 128,
        kernel_size: int = 5,
        n_groups: int = 8,
        use_film_scale: bool = True,
    ):
        super().__init__()
        d = diffusion_step_embed_dim
        self.timestep_encoder = nn.Sequential(
            SinusoidalPosEmb(d), nn.Linear(d, d * 4), nn.Mish(), nn.Linear(d * 4, d),
        )
        cond_dim = d + global_cond_dim
        res_kw = dict(cond_dim=cond_dim, kernel_size=kernel_size, n_groups=n_groups, use_film_scale=use_film_scale)

        in_out = [(input_dim, down_dims[0])] + list(zip(down_dims[:-1], down_dims[1:]))
        self.down_modules = nn.ModuleList()
        for i, (dim_in, dim_out) in enumerate(in_out):
            is_last = i >= len(in_out) - 1
            self.down_modules.append(nn.ModuleList([
                ConditionalResBlock1d(dim_in, dim_out, **res_kw),
                ConditionalResBlock1d(dim_out, dim_out, **res_kw),
                nn.Conv1d(dim_out, dim_out, 3, 2, 1) if not is_last else nn.Identity(),
            ]))

        mid_dim = down_dims[-1]
        self.mid_modules = nn.ModuleList([
            ConditionalResBlock1d(mid_dim, mid_dim, **res_kw),
            ConditionalResBlock1d(mid_dim, mid_dim, **res_kw),
        ])

        self.up_modules = nn.ModuleList()
        for i, (dim_out, dim_in) in enumerate(reversed(in_out[1:])):
            is_last = i >= len(in_out) - 1
            self.up_modules.append(nn.ModuleList([
                ConditionalResBlock1d(dim_in * 2, dim_out, **res_kw),
                ConditionalResBlock1d(dim_out, dim_out, **res_kw),
                nn.ConvTranspose1d(dim_out, dim_out, 4, 2, 1) if not is_last else nn.Identity(),
            ]))

        self.final_conv = nn.Sequential(
            Conv1dBlock(down_dims[0], down_dims[0], kernel_size=kernel_size),
            nn.Conv1d(down_dims[0], input_dim, 1),
        )

    def forward(self, x: Tensor, timestep: Tensor, global_cond: Tensor) -> Tensor:
        x = einops.rearrange(x, "b t d -> b d t")
        t_emb = self.timestep_encoder(timestep)
        cond = torch.cat([t_emb, global_cond], dim=-1)

        skips = []
        for res1, res2, downsample in self.down_modules:
            x = res1(x, cond)
            x = res2(x, cond)
            skips.append(x)
            x = downsample(x)

        for mid_block in self.mid_modules:
            x = mid_block(x, cond)

        for res1, res2, upsample in self.up_modules:
            x = torch.cat([x, skips.pop()], dim=1)
            x = res1(x, cond)
            x = res2(x, cond)
            x = upsample(x)

        x = self.final_conv(x)
        return einops.rearrange(x, "b d t -> b t d")


# ===========================================================================
#  Noise scheduler factory
# ===========================================================================

def make_noise_scheduler(
    scheduler_type: str = "DDPM",
    num_train_timesteps: int = 100,
    beta_schedule: str = "squaredcos_cap_v2",
    beta_start: float = 0.0001,
    beta_end: float = 0.02,
    prediction_type: str = "epsilon",
    clip_sample: bool = True,
    clip_sample_range: float = 1.0,
):
    """建立 noise scheduler。回傳 DDPMScheduler 或 DDIMScheduler。"""
    cls = DDPMScheduler if scheduler_type == "DDPM" else DDIMScheduler
    return cls(
        num_train_timesteps=num_train_timesteps,
        beta_start=beta_start,
        beta_end=beta_end,
        beta_schedule=beta_schedule,
        clip_sample=clip_sample,
        clip_sample_range=clip_sample_range,
        prediction_type=prediction_type,
    )
