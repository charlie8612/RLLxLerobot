#!/usr/bin/env python3
"""
Diffusion Policy 自由訓練腳本 — 模型架構直接在這裡組裝。

重點：沒有 template class、沒有 config wrapper。
你的模型就是一個 nn.Module，想怎麼搭就怎麼搭。
唯一的約定：實作 compute_loss(batch) → Tensor。

想換架構？直接改 MyDiffusionPolicy 這個 class。
想換 encoder？把 self.rgb_encoder 換掉。
想用 Transformer 取代 UNet？換掉 self.denoiser。
想加 depth sensor？在 encode_observations() 裡加。
想改 loss？在 compute_loss() 裡改。

Usage:
    conda activate piper
    cd ~/piper-lerobot && python scripts/5_train_diffusion_custom.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import torch
import torch.nn.functional as F
from torch import Tensor, nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from lerobot.datasets.lerobot_dataset import LeRobotDataset

# 積木箱：拿你需要的零件
from models.diffusion_blocks import (
    RgbEncoder,
    UNet1d,
    make_noise_scheduler,
)


# =====================================================================
#  Config — 訓練超參數
# =====================================================================
DATASET_REPO_ID = "charliechan/piper-pick-cube"
OUTPUT_DIR = Path("/tmp2/charlie/training-outputs/diffusion_piper_custom")
DEVICE = "cuda"

BATCH_SIZE = 32
NUM_WORKERS = 4
STEPS = 500
SAVE_EVERY = 100
LOG_EVERY = 50
GRAD_CLIP_NORM = 10.0

EARLY_STOP_PATIENCE = 500   # 0 = 不啟用
EARLY_STOP_MIN_DELTA = 1e-5

LR = 1e-4
LR_MIN = 1e-6

# 序列長度
N_OBS_STEPS = 2     # 用幾步歷史觀察
HORIZON = 16        # diffusion 預測的 action 長度
N_ACTION_STEPS = 8  # 實際執行幾步


# =====================================================================
#  你的模型 — 直接在這裡搭建，想怎麼改就怎麼改
# =====================================================================

class MyDiffusionPolicy(nn.Module):
    """
    這就是你的模型。不繼承任何 template，不依賴任何 config class。
    所有架構決定都在這裡，一目了然。

    想做實驗？直接改這個 class：
    - 換 vision encoder → 改 __init__ 裡的 self.rgb_encoder
    - 換 denoiser (UNet → Transformer) → 改 self.denoiser
    - 加新的 input modality → 改 encode_observations()
    - 換 loss function → 改 compute_loss()
    - 換 noise schedule → 改 self.noise_scheduler
    """

    def __init__(self, state_dim: int, action_dim: int, image_shape: tuple):
        super().__init__()

        # ---- 存維度資訊 ----
        self.action_dim = action_dim
        self.horizon = HORIZON
        self.n_obs_steps = N_OBS_STEPS
        self.n_action_steps = N_ACTION_STEPS
        self.prediction_type = "epsilon"  # "epsilon" or "sample"

        # ---- Vision Encoder ----
        # 想換？直接換成任何 (B, C, H, W) → (B, feat_dim) 的 module
        self.rgb_encoder = RgbEncoder(
            backbone="resnet18",
            pretrained_weights="ResNet18_Weights.IMAGENET1K_V1",
            image_shape=image_shape,
            num_keypoints=32,
        )

        # ---- 算 conditioning 維度 ----
        # global_cond = [image_features, state] × n_obs_steps
        single_step_dim = self.rgb_encoder.feature_dim + state_dim
        global_cond_dim = single_step_dim * N_OBS_STEPS

        # ---- Denoiser ----
        # 想換成 Transformer？把 UNet1d 換掉，
        # 只要 forward(noisy_actions, timestep, global_cond) → pred 就行
        self.denoiser = UNet1d(
            input_dim=action_dim,
            global_cond_dim=global_cond_dim,
            down_dims=(512, 1024, 2048),
        )

        # ---- Noise Scheduler ----
        self.noise_scheduler = make_noise_scheduler(
            scheduler_type="DDPM",
            num_train_timesteps=100,
            prediction_type=self.prediction_type,
        )

    # ------------------------------------------------------------------
    #  Observation encoding — 想加新 modality？改這裡
    # ------------------------------------------------------------------
    def encode_observations(self, batch: dict) -> Tensor:
        """
        images + state → global conditioning vector

        目前: concat(image_feat, state) 再 flatten n_obs_steps
        你可以加 depth、force、language embedding... 任何東西
        """
        B = batch["observation.state"].shape[0]
        parts = []

        # Images: (B, n_obs, n_cam, C, H, W) → (B, n_obs, feat_dim)
        images = batch["observation.images"]
        imgs_flat = images.reshape(-1, *images.shape[-3:])
        img_feat = self.rgb_encoder(imgs_flat)
        img_feat = img_feat.reshape(B, self.n_obs_steps, -1)
        parts.append(img_feat)

        # State: (B, n_obs, state_dim)
        parts.append(batch["observation.state"])

        # Concat and flatten time dimension
        cond = torch.cat(parts, dim=-1)      # (B, n_obs, dim_per_step)
        return cond.flatten(1)                # (B, n_obs * dim_per_step)

    # ------------------------------------------------------------------
    #  Training loss — 想改 loss？改這裡
    # ------------------------------------------------------------------
    def compute_loss(self, batch: dict) -> Tensor:
        """
        1. encode observations → global_cond
        2. 拿 ground truth action, 加隨機噪聲
        3. denoiser 預測 noise（或 clean sample）
        4. 算 loss

        想做的事情，例如：
        - Weighted MSE (gripper 加大 weight)
        - Huber loss
        - 加 auxiliary loss (state prediction, etc.)
        全部在這裡改。
        """
        global_cond = self.encode_observations(batch)
        trajectory = batch["action"]  # (B, horizon, action_dim)

        noise = torch.randn_like(trajectory)
        timesteps = torch.randint(
            0, self.noise_scheduler.config.num_train_timesteps,
            (trajectory.shape[0],), device=trajectory.device,
        ).long()

        noisy_trajectory = self.noise_scheduler.add_noise(trajectory, noise, timesteps)
        pred = self.denoiser(noisy_trajectory, timesteps, global_cond)

        target = noise if self.prediction_type == "epsilon" else trajectory

        # ======== 改 loss 在這裡 ========
        loss = F.mse_loss(pred, target)

        return loss

    # ------------------------------------------------------------------
    #  Inference — 想改推論流程？改這裡
    # ------------------------------------------------------------------
    @torch.no_grad()
    def generate_actions(self, batch: dict) -> Tensor:
        """從噪聲 denoise → clean action trajectory。Returns (B, horizon, action_dim)。"""
        global_cond = self.encode_observations(batch)
        B = global_cond.shape[0]

        trajectory = torch.randn(
            (B, self.horizon, self.action_dim), device=global_cond.device,
        )

        self.noise_scheduler.set_timesteps(
            self.noise_scheduler.config.num_train_timesteps,
            device=global_cond.device,
        )

        for t in self.noise_scheduler.timesteps:
            pred = self.denoiser(trajectory, t.expand(B), global_cond)
            trajectory = self.noise_scheduler.step(pred, t, trajectory).prev_sample

        return trajectory


# =====================================================================
#  Batch 預處理
# =====================================================================

def prepare_batch(batch: dict, device: str) -> dict:
    """
    把 DataLoader 出來的 batch 轉換成模型需要的格式。

    LeRobotDataset + delta_timestamps 出來的格式:
        observation.images.wrist: (B, n_obs, C, H, W)
        observation.state:        (B, n_obs, state_dim)
        action:                   (B, horizon, action_dim)

    模型需要:
        observation.images: (B, n_obs, n_cam, C, H, W)  ← 加 camera dim
        observation.state:  (B, n_obs, state_dim)
        action:             (B, horizon, action_dim)
    """
    batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}

    # 把各 camera 的 image key 合併成一個 tensor，加上 camera dimension
    # 過濾掉 _is_pad key（delta_timestamps 產生的 padding mask）
    image_keys = sorted(
        k for k in batch
        if k.startswith("observation.images.") and not k.endswith("_is_pad")
    )
    if image_keys:
        imgs = torch.stack([batch[k] for k in image_keys], dim=-4)
        if imgs.ndim == 4:       # 沒有 n_obs dim → 加上去
            imgs = imgs.unsqueeze(1)
        batch["observation.images"] = imgs

    # state 確保有 n_obs dim
    if batch["observation.state"].ndim == 2:
        batch["observation.state"] = batch["observation.state"].unsqueeze(1)

    return batch


# =====================================================================
#  Training loop
# =====================================================================

def save_checkpoint(model, optimizer, lr_scheduler, step, save_dir):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), save_dir / "model.pt")
    torch.save({
        "step": step,
        "optimizer": optimizer.state_dict(),
        "lr_scheduler": lr_scheduler.state_dict(),
    }, save_dir / "training_state.pt")
    print(f"  Saved step {step} → {save_dir}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 1. Dataset ----
    print(f"Loading dataset: {DATASET_REPO_ID}")

    # 先開一次讀 metadata
    ds_meta = LeRobotDataset(DATASET_REPO_ID)
    fps = ds_meta.fps
    state_dim = ds_meta.features["observation.state"]["shape"][0]
    action_dim = ds_meta.features["action"]["shape"][0]
    image_keys = sorted(k for k in ds_meta.features if k.startswith("observation.images"))
    raw_shape = tuple(ds_meta.features[image_keys[0]]["shape"])  # metadata 存 (H, W, C)
    image_shape = (raw_shape[2], raw_shape[0], raw_shape[1])      # 轉成 (C, H, W)
    del ds_meta

    # 用 delta_timestamps 讓 dataset 回傳序列資料
    #   observation: 過去 N_OBS_STEPS 步
    #   action: 未來 HORIZON 步
    delta_timestamps = {
        "observation.state": [i / fps for i in range(1 - N_OBS_STEPS, 1)],
        "action": [i / fps for i in range(HORIZON)],
    }
    for key in image_keys:
        delta_timestamps[key] = [i / fps for i in range(1 - N_OBS_STEPS, 1)]

    dataset = LeRobotDataset(DATASET_REPO_ID, delta_timestamps=delta_timestamps)

    print(f"  Episodes: {dataset.num_episodes}, Frames: {dataset.num_frames}")
    print(f"  state_dim={state_dim}, action_dim={action_dim}, image_shape={image_shape}")

    # ---- 2. Build model ----
    model = MyDiffusionPolicy(
        state_dim=state_dim,
        action_dim=action_dim,
        image_shape=image_shape,
    ).to(DEVICE)

    num_params = sum(p.numel() for p in model.parameters())
    num_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Total params: {num_params:,}  Trainable: {num_trainable:,}")

    # ---- 3. Optimizer & Scheduler ----
    optimizer = torch.optim.Adam(
        model.parameters(), lr=LR, betas=(0.95, 0.999), eps=1e-8, weight_decay=1e-6,
    )
    lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=STEPS, eta_min=LR_MIN)

    # ---- 4. Dataloader ----
    dataloader = DataLoader(
        dataset, batch_size=BATCH_SIZE, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=True, drop_last=True,
    )

    def infinite_loader():
        while True:
            yield from dataloader

    dl_iter = iter(infinite_loader())

    # ---- 5. Training loop ----
    print(f"\nTraining for {STEPS} steps")
    print(f"  batch_size={BATCH_SIZE}  save_every={SAVE_EVERY}  early_stop={EARLY_STOP_PATIENCE}\n")

    model.train()
    best_loss = float("inf")
    patience_counter = 0
    loss_history = []

    pbar = tqdm(range(STEPS), desc="Training")
    for step in pbar:
        batch = next(dl_iter)
        batch = prepare_batch(batch, DEVICE)

        loss = model.compute_loss(batch)

        optimizer.zero_grad()
        loss.backward()
        if GRAD_CLIP_NORM > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
        optimizer.step()
        lr_scheduler.step()

        loss_val = loss.item()
        loss_history.append(loss_val)
        pbar.set_postfix(loss=f"{loss_val:.4f}", lr=f"{optimizer.param_groups[0]['lr']:.2e}")

        if (step + 1) % LOG_EVERY == 0:
            avg = sum(loss_history[-LOG_EVERY:]) / LOG_EVERY
            print(f"  Step {step+1:5d} | avg_loss: {avg:.4f} | lr: {optimizer.param_groups[0]['lr']:.2e}")

        if (step + 1) % SAVE_EVERY == 0:
            save_checkpoint(model, optimizer, lr_scheduler, step + 1, OUTPUT_DIR / f"checkpoint_{step+1}")

        if EARLY_STOP_PATIENCE > 0:
            if loss_val < best_loss - EARLY_STOP_MIN_DELTA:
                best_loss = loss_val
                patience_counter = 0
            else:
                patience_counter += 1
            if patience_counter >= EARLY_STOP_PATIENCE:
                print(f"\nEarly stopping at step {step+1} (best_loss={best_loss:.4f})")
                break

    save_checkpoint(model, optimizer, lr_scheduler, step + 1, OUTPUT_DIR / "final")
    print(f"\nDone! Final loss: {loss_history[-1]:.4f} | Best: {best_loss:.4f}")
    print(f"Checkpoints: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
