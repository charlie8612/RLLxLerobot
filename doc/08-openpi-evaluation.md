# OpenPI (JAX) 評估筆記

## 背景

Pi0-FAST 在 LeRobot PyTorch port 上的 inference 速度太慢（~30 秒/chunk on RTX 3090），
無法即時控制機器人。torch.compile 預估能加速到 ~10-15 秒，但仍不夠即時。

Physical Intelligence 官方的 OpenPI 使用 JAX/XLA，autoregressive decoding 可以被編譯成
fused kernel，預估在同樣的 3090 上能達到 ~3-5 秒/chunk。

## 為什麼考慮 OpenPI

| | LeRobot (PyTorch) | OpenPI (JAX) |
|---|---|---|
| Pi0-FAST inference (3090) | ~30s（無 compile）/ ~10-15s（compile） | ~3-5s（估） |
| 維護方 | HuggingFace 社群 port | Physical Intelligence 官方 |
| 品質 | 踩過多個 bug（tokenizer、save、dtype） | 官方維護，文件清楚 |
| Robot 整合 | LeRobot plugin 架構，已有 Piper plugin | 需自寫 gRPC robot server |
| Dataset | LeRobot format | 支援讀 LeRobot format |

## 如果要裝 OpenPI

### 環境

```bash
conda create -n openpi python=3.10
conda activate openpi
pip install openpi-client
# server 端（載入 model）
pip install jax[cuda12] openpi
```

> 不要裝在 piper env 裡，JAX 和 PyTorch CUDA runtime 會衝突。

### 架構

OpenPI 是 client-server 架構：

```
┌──────────────┐     gRPC      ┌──────────────┐
│ Robot Client │ ──────────── │ OpenPI Server │
│ (Python)     │   obs → act   │ (JAX model)  │
│              │               │ GPU 0/1      │
│ Piper SDK    │               │              │
│ Camera       │               │ pi0fast-base │
└──────────────┘               └──────────────┘
```

- **Server**：`openpi-server --model pi0-fast --port 8000`，載入 model 到 GPU
- **Client**：送 observation dict（images + state + task），收 action array
- Robot control 需要自己寫（用 piper_sdk 直接控制，不經過 LeRobot）

### 需要做的事

1. 新 conda env 裝 JAX + OpenPI
2. 寫 Piper robot client（參考 `plugins/lerobot-robot-piper/` 的控制邏輯）
3. Camera 讀取（可以直接用 OpenCV，不需要 LeRobot 的 camera wrapper）
4. Fine-tune：OpenPI 支援用 LeRobot format dataset 直接訓練，不需轉格式
5. 驗證 inference 速度是否真的有改善

### 現有資源可複用

- Dataset：`/home/charliechan/dataset/charliechan/piper-pick-cube-dual`（LeRobot format，OpenPI 直接讀）
- Camera udev rules：`/dev/cam_c270`、`/dev/cam_arc`
- CAN 啟動：`scripts/0_can_up.sh`
- Piper SDK：`piper_sdk` 已裝在系統 Python

### 風險

- JAX on consumer GPU（3090/3080）的實際速度沒有公開 benchmark，3-5 秒是估計值
- 需要額外維護一套 robot control code（目前 LeRobot plugin 已經穩定）
- 如果速度提升不夠顯著（例如只快 2x），投入產出比不高

## 決策

**暫不實施**。先用 torch.compile 測試加速效果，如果仍然太慢再評估 OpenPI。
Diffusion Policy 已經可以即時控制，Pi0-FAST 目前作為實驗性質。

## 參考

- OpenPI GitHub：https://github.com/Physical-Intelligence/openpi
- OpenPI 文件：https://www.pi.website/blog/openpi
- Pi0 論文：https://www.physicalintelligence.company/blog/pi0
