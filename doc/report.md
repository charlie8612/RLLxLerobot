# Piper Robot Imitation Learning Pipeline 報告

---

## 1. Infrastructure Survey

做 imitation learning 需要一條完整的 pipeline：**Teleop → Record → Train → Eval**。
以下比較了主流的 robot learning framework 和 lab 現有資源。

### 主流 Robot Learning Framework 比較

| Framework | 來源 | 涵蓋範圍 | 硬體整合 | Policy 支援 | 適合場景 |
|-----------|------|----------|----------|-------------|----------|
| **LeRobot** | HuggingFace | Teleop → Record → Train → Eval 全包 | Plugin 架構，新硬體寫 plugin 即可 | ACT, Diffusion, Pi0-FAST 等內建 | 想用統一 pipeline 快速跑通 IL |
| **robomimic** | Stanford/NUS | Dataset → Train → Eval (simulation) | 無硬體整合，專注 simulation (robosuite) | BC, BC-RNN, Diffusion 等 | 純 simulation 研究、benchmark |
| **ACT 原始碼** | Tony Zhao (Stanford) | 綁定 ALOHA 硬體的完整 pipeline | 只支援 ALOHA (Dynamixel based) | ACT only | 有 ALOHA 硬體的 lab |
| **DROID** | Stanford | 大規模多機器人資料收集 | 支援 Franka，自訂 teleop 硬體 | 資料收集為主，訓練另外接 | 大規模 data collection campaign |
| **gello** | UC Berkeley | Universal teleop 硬體方案 | 提供 3D-printed leader arm 設計 | 無訓練 pipeline，純 teleop | 只需要 teleop 方案 |
| **ROS2 + rosbag** | 自建 | Teleop + Record | 現有 ROS2 driver 直接用 | 無，需自己寫 training script | 已有 ROS2 生態、不想換框架 |

### 各方案評估（對我們的情況）

| 方案 | 做法 | 評估 |
|------|------|------|
| **robomimic** | 用 robomimic 訓練，自己寫資料收集和 real robot eval | robomimic 專注 simulation，real robot 整合要全部自己來；dataset 格式 (HDF5) 也和 real robot 錄製不直接相容 |
| **ACT 原始碼** | Fork ACT repo，改成支援 Piper | 深度綁定 ALOHA 硬體（Dynamixel follower），改動量大；且只有 ACT 一種 policy |
| **ROS2 + 自建** | 用現有 ROS2 teleop + rosbag 錄資料，自己寫 training | teleop 已有，但 rosbag → training data 需寫轉換工具，policy eval 接回 ROS2 也要自己做 |
| **LeRobot + Plugin** | 寫 LeRobot plugin 接 Piper 硬體 | Plugin 開發量可控（3 個小 package），上層 record / train / eval 全部現成；換 policy 一行參數切換 |

### Lab 現有資源

| 資源 | 說明 | 可利用程度 |
|------|------|------------|
| `piper_ros` (ROS2) | 現有 5-node teleop 方案 | 參考 joint mapping 邏輯，但不直接用 |
| `piper_sdk` (pip) | 官方 Python CAN bus SDK | 直接用，作為 plugin 底層 |
| `dynamixel_sdk` | Dynamixel Protocol 2.0 SDK | 直接用，讀 leader arm |
| ROBOTIS OMY-L100 packages | ROS2 driver + config | 參考馬達型號和參數 |

### 結論：選 LeRobot + Plugin

關鍵理由：
1. **唯一涵蓋 real robot 全 pipeline 的框架** — robomimic 偏 simulation，ACT 綁 ALOHA，gello 只有 teleop
2. **Plugin 架構** — 不用 fork / 改原始碼，寫 plugin 就能支援新硬體
3. **多 policy 支援** — 同一份 data 可以訓 Diffusion / ACT / Pi0-FAST，方便比較
4. **社群活躍** — HuggingFace 持續更新，新 policy（如 Pi0）上線快

---

## 2. 為什麼這樣選？（以 Imitation Learning 為目標）

做 imitation learning 需要一條完整的 pipeline：

```
Teleoperate → Record Dataset → Train Policy → Inference on Robot
```

LeRobot 已經把這四步全部包好了，包含：
- 標準化的 dataset 格式（LeRobotDataset, parquet + video）
- 內建多種 policy（ACT, Diffusion Policy, Pi0-FAST）
- 統一的 eval 介面（直接把 policy 接回 robot 跑）
- Wandb 整合、Rerun 視覺化

**唯一缺的就是 Piper 硬體的驅動**。所以只需要寫 plugin 把硬體接進去，上面的一切都能直接用。

如果走 ROS2，雖然 teleop 已經有了，但：
- rosbag 格式和訓練需要的格式完全不同，需要寫轉換工具
- policy inference 回到 robot 也要自己接 ROS2 topic
- 換 policy 架構就要改一堆 code

**核心原則：把時間花在收資料和訓練上，不要花在接水管上。**

---

## 3. Teleop 實作方式 & 與原本的差異

### 原本的做法（ROS2, 5 nodes）

```
hardware_interface → /joint_states → robotis2piper.py → /joint_ctrl → piper_ctrl_node → SDK
```

- 5 個 ROS2 node，透過 topic 溝通
- 每次 topic publish 有序列化/反序列化開銷
- 依賴 ROS2 runtime，環境設定繁瑣

### 現在的做法（LeRobot Plugin, 1 class 直呼叫）

```
dynamixel_sdk.sync_read → joint mapping → PiperFollower.send_action() → piper_sdk
```

- **1 個 Python class**，直接讀 leader、mapping、送 follower
- 不經過 ROS2，架構更簡單（不需要設定 ROS2 workspace、launch file、node 等）
- 200 Hz 控制迴圈（延遲和 ROS2 方案相當，差異不大）

### 三個 Plugin 的分工

| Plugin | 角色 | 功能 |
|--------|------|------|
| `lerobot_robot_piper` | Follower (Robot) | 透過 piper_sdk 控制 Piper arm，讀寫 joint states |
| `lerobot_teleoperator_robotis` | Leader (Teleoperator) | 透過 dynamixel_sdk 讀 ROBOTIS OMY-L100 位置，mapping 到 Piper 角度 |
| `lerobot_teleoperator_keypad` | 鍵盤 Teleop (測試用) | 用 termios raw input 做 joint-level 鍵盤控制 |

### Plugin 自動發現機制

LeRobot 用 `importlib.metadata` 掃描 pip 已安裝的 `lerobot_robot_*` / `lerobot_teleoperator_*` package，自動註冊。CLI 就能直接用：

```bash
--robot.type=piper_follower
--teleop.type=robotis_leader
```

**不需要改 LeRobot 任何一行原始碼。**

### Joint Mapping（Leader → Follower）

- ROBOTIS OMY-L100 和 Piper 的關節數量、角度範圍、方向都不同
- 用自製校準工具 `tools/calibrate_single.py` 逐 joint 校準 scale + offset
- 公式：`piper_deg = clamp(scale * leader_rad + offset_rad) * 180/pi, min, max)`
- Joint 順序也有對應（例如 Piper J4 ← Leader M5, Piper J5 ← Leader M4）

---

## 4. 資料儲存形式

### LeRobotDataset 結構

實際的 dataset 儲存在 `~/.cache/huggingface/lerobot/<repo_id>/`，結構如下：

```
charliechan/piper-pick-cube/
├── meta/
│   ├── info.json                          # dataset metadata（見下方）
│   ├── stats.json                         # 全局統計（min/max/mean/std per feature）
│   ├── tasks.parquet                      # task 描述（e.g. "pick up cube"）
│   └── episodes/chunk-000/file-000.parquet # 每個 episode 的 start/end index
├── data/chunk-000/file-000.parquet        # 所有 episode 的 observation + action
└── videos/observation.images.wrist/
    └── chunk-000/file-000.mp4             # wrist camera 影片（AV1 編碼）
```

### info.json — Dataset Metadata

錄製完後可以用 `info.json` 確認 dataset 的完整性，這也是驗證腳本在檢查的東西：

```json
{
    "codebase_version": "v3.0",
    "robot_type": "piper_follower",
    "total_episodes": 11,
    "total_frames": 3150,
    "total_tasks": 1,
    "fps": 20,
    "features": {
        "action":              { "dtype": "float32", "shape": [7], "names": ["joint_1.pos", ..., "gripper.pos"] },
        "observation.state":   { "dtype": "float32", "shape": [7], "names": ["joint_1.pos", ..., "gripper.pos"] },
        "observation.images.wrist": { "dtype": "video", "shape": [480, 640, 3],
                                      "info": { "video.codec": "av1", "video.fps": 20 } },
        "timestamp":      { "dtype": "float32" },
        "frame_index":    { "dtype": "int64" },
        "episode_index":  { "dtype": "int64" },
        "task_index":     { "dtype": "int64" }
    }
}
```

### 驗證方式

錄製完用 Python 確認資料正確性：

```python
from lerobot.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset("charliechan/piper-pick-cube")
print(f"Episodes: {ds.meta.total_episodes}")        # 11
print(f"Frames: {len(ds)}")                          # 3150
print(f"Features: {list(ds.meta.features.keys())}")
# ['action', 'observation.state', 'observation.images.wrist',
#  'timestamp', 'frame_index', 'episode_index', 'index', 'task_index']
```

也可以用 `lerobot-dataset-viz` 視覺化回放，確認 camera 影片和 joint 數值對得上。

### 每個 frame 的內容

| Feature | Shape | dtype | 說明 |
|---------|-------|-------|------|
| `action` | (7,) | float32 | teleop 送出的目標：6 joint angles (deg) + gripper (mm) |
| `observation.state` | (7,) | float32 | robot 回讀的實際位置：同上 |
| `observation.images.wrist` | (480, 640, 3) | video | wrist camera RGB，存為 AV1 mp4 |
| `timestamp` | (1,) | float32 | 該 frame 的時間戳 |
| `frame_index` | (1,) | int64 | 該 episode 內的 frame 編號 |
| `episode_index` | (1,) | int64 | episode 編號 |
| `task_index` | (1,) | int64 | 對應 tasks.parquet 的 task |

> `action` 和 `observation.state` 的差異：action 是 leader arm 送出的目標位置，observation.state 是 follower 實際到達的位置。兩者會有微小延遲差異。

### 資料品質管理

- 錄製中可用 **←** 重錄壞掉的 episode，**→** 提前結束
- 事後用 `tools/delete_episodes.py` 刪除壞 episode（自動重新編號）
- `lerobot-dataset-viz` 視覺化回放驗證品質

### 目前收集的資料

- **Dataset**: `charliechan/piper-pick-cube`
- **任務**: pick up cube
- **Episodes**: 11（原始 12 條，刪除 1 條垃圾）
- **Frames**: 3150
- **Camera**: 單 wrist camera (640x480, AV1, 20fps)
- **磁碟大小**: data ~100 MB + video ~200 MB

---

## 5. 訓練 & Inference

### Stage A: Diffusion Policy（從零訓練）— ✅ 完成

**架構**: ResNet18 (vision encoder) + 1D UNet (action denoising)
**參數量**: ~60-80M
**VRAM**: 訓練 ~8-12 GB
**訓練**: 20K steps，loss 從 ~0.82 收斂至 ~0.08
**Eval 結果**: 機器人會動，pipeline 已打通

```bash
lerobot-train \
    --policy.type=diffusion \
    --dataset.repo_id=charliechan/piper-pick-cube \
    --output_dir=outputs/train/diffusion_piper
```

**Inference（在真機上推論）**:

```bash
lerobot-record \
    --robot.type=piper_follower \
    --control.policy.path=outputs/train/diffusion_piper/checkpoints/last/pretrained_model \
    --dataset.repo_id=charliechan/eval-diffusion-piper
```

推論時 `lerobot-record` 會：
1. 讀 camera image + joint state 作為 observation
2. 送進 policy 得到 predicted action
3. 把 action 送到 robot 執行
4. 同時錄製 eval dataset 方便分析

### Stage B: Pi0-FAST（Pretrained Fine-tune）— 未開始

**架構**: PaliGemma (SigLIP + Gemma 2B) + FAST action tokenizer
**參數量**: ~3B
**VRAM**: bf16 訓練 ~16-20 GB

- 用 pretrained `lerobot/pi0fast_base` 做 fine-tune
- 理論上用更少 demos 就能達到更好泛化
- Action space 內建 auto-pad 到 32 維，Piper 7 維直接支援

### 預設超參數

| 參數 | Diffusion | Pi0-FAST |
|------|-----------|----------|
| Observation steps | 2 | - |
| Action horizon | 16 | 10 |
| Action steps (per inference) | 8 | 10 |
| 訓練時間（估計） | 數小時 | 更長 |

---

## 6. 包好東西的好處 & 壞處

### 好處

| 項目 | 說明 |
|------|------|
| **Pipeline 一條龍** | teleop → record → train → eval 全部用同一套工具，不用自己接 |
| **Dataset 標準化** | LeRobotDataset 格式統一，換 policy 不用改資料格式 |
| **Policy 可替換** | 同一份 dataset 可以訓 Diffusion / ACT / Pi0-FAST，一行 `--policy.type=` 切換 |
| **Plugin 解耦** | 換機器人只需換 plugin，上層 dataset / training / eval 完全不動 |
| **不依賴 ROS2** | 少了一層 middleware，部署更簡單，延遲更低 |
| **社群支援** | LeRobot 持續更新，新 policy / 新功能直接可用 |
| **可復現** | Dataset + config 完整記錄，別人拿到就能重新訓練 |

### 壞處

| 項目 | 說明 |
|------|------|
| **被 LeRobot 綁定** | API 改版就要跟著改 plugin（例如 features 格式、config 系統變動） |
| **LeRobot 的限制** | 原生不支援雙手、不支援 DAgger 等進階功能，要做得自己擴展 |
| **Debug 困難** | 出問題時要同時理解 LeRobot 內部邏輯 + 自己的 plugin + 硬體，三層一起查 |
| **SSH 相容性** | LeRobot 部分功能依賴 X11（pynput, Rerun GUI），headless 環境受限 |
| **黑盒訓練** | 用 `lerobot-train` 跑訓練很方便，但超參數調整、客製化架構需要深入理解內部實作 |
| **硬體差異吸收** | Joint mapping、單位轉換、CAN 通訊的細節都藏在 plugin 裡，新人接手需要時間理解 |

### 總結

> 如果目標是**快速驗證 imitation learning 在新硬體上可不可行**，LeRobot + Plugin 是目前最省力的做法。
> 代價是跟 LeRobot 生態綁定，以及在框架不支援的地方需要自己擴展。
>
> 這個 trade-off 在當前階段是值得的——先跑通 pipeline、拿到 baseline 結果，再根據需求決定要不要往更客製化的方向走。
