# Phase 4: 雙手 Teleoperation

**狀態：✅ Teleop 完成（Step 1–4），Step 5–6 待做**

## 目標

同時用兩隻 ROBOTIS leader arm 控制兩隻 Piper follower arm，實現雙手 teleoperation + 錄製。

## 硬體配置

```
USB-CAN adapter ──→ piper_left   (CAN, Bus 01 Port 3)  ──→ Piper Arm (左手)
USB-CAN adapter ──→ piper_right  (CAN, Bus 01 Port 4)  ──→ Piper Arm (右手)
USB-Serial      ──→ /dev/robotis_left  (ttyUSB1, Bus 01 Port 6)   ──→ ROBOTIS Leader (左手)
USB-Serial      ──→ /dev/robotis_right (ttyUSB0, Bus 01 Port 11)  ──→ ROBOTIS Leader (右手)
```

兩隻手硬體完全相同（兩隻左手），joint mapping 共用同一組校準參數。

---

## 架構決策

### 方案 B：Bimanual Plugin Wrapper

參照 LeRobot 官方 `bi_so_follower` / `bi_so_leader` pattern：

- `BiPiperFollower(Robot)` — 包兩個 `PiperFollower`，feature key 加 `left_` / `right_` prefix
- `BiRobotisLeader(Teleoperator)` — 包兩個 `RobotisLeader`，同樣加 prefix
- 與 LeRobot CLI (`lerobot-record`, `lerobot-teleoperate`) 原生相容

### Config 拆分（draccus 相容）

LeRobot 用 draccus 做 CLI config 解析。如果 bimanual config 的 field 直接用 `PiperFollowerConfig`（已 `register_subclass` 的 choice type），draccus 會**無限遞迴**展開 choice tree。

解法（與 LeRobot 官方 `bi_so_follower` 做法一致）：

```python
# 純 dataclass，不繼承 RobotConfig，不註冊 choice
@dataclass
class PiperFollowerBaseConfig:
    can_port: str = "piper_left"
    ...

# CLI 用：同時繼承 RobotConfig + BaseConfig，註冊 choice
@RobotConfig.register_subclass("piper_follower")
@dataclass
class PiperFollowerConfig(RobotConfig, PiperFollowerBaseConfig):
    pass

# Bimanual 用 BaseConfig，避免 choice 遞迴
@RobotConfig.register_subclass("bi_piper_follower")
@dataclass
class BiPiperFollowerConfig(RobotConfig):
    left_arm_config: PiperFollowerBaseConfig   # ← 不是 choice type
    right_arm_config: PiperFollowerBaseConfig
```

Leader 那邊同理（`RobotisLeaderBaseConfig` / `RobotisLeaderConfig`）。

### Subprocess 架構（GIL 迴避）

**問題**：piper_sdk 的 `C_PiperInterface_V2` 會建立 background CAN receive thread。兩個 instance 在同一個 Python process 內時，background threads 搶 GIL，導致所有 I/O 操作慢 ~10 倍。

**驗證**：
- 同一 process 雙手 teleop：`read_leader` avg 20ms，`send_action` avg 16ms，total ~36ms
- 兩個獨立 process 各跑一手：各自 total ~4ms，完全流暢
- 瓶頸不是 USB 頻寬（同 USB bus 但兩個 process 不受影響）

**解法**：右手設備放在獨立 subprocess，有自己的 GIL：

```
Main Process (LeRobot teleop loop)
  ├── Left PiperFollower    (直接呼叫)
  ├── Left RobotisLeader    (直接呼叫)
  └── Pipe ──→ Right Arm Subprocess
                ├── Right PiperFollower   (獨立 GIL)
                └── Right RobotisLeader   (獨立 GIL)
```

實作：
- `SubprocessFollower` — proxy class，透過 `multiprocessing.Pipe` 與子 process 的 `PiperFollower` 通訊
- `SubprocessLeader` — 同理，包裝 `RobotisLeader`
- `BiPiperFollower` 的 `left_arm` 用原生 `PiperFollower`，`right_arm` 用 `SubprocessFollower`
- `BiRobotisLeader` 同理

### 額外修正

- `robotis_leader.py` `_read_positions_rad()` 加入 retry 機制（最多 3 次），sync read 失敗時 fallback 到上次讀數，避免偶發 USB-Serial 瞬斷導致整個 teleop crash
- 雙手版本已同步單手的所有改進：
  - **Joint mapping**：使用 ROS2 offset 基準 + 實測 motor 對應（透過 `RobotisLeaderBaseConfig` 預設值繼承）
  - **開機防暴衝**：1% 速度啟動 + hold-in-place 覆蓋舊目標（透過 `PiperFollower.connect()` 自動生效）
  - **Gripper 回彈**：spring effect 參數已傳遞至 `bi_robotis_leader.py` 和 `subprocess_leader.py`
  - **Gripper 全開**：`gripper_piper_open_mm = 70.0`（透過 BaseConfig 預設值繼承）

---

## Plugin 檔案結構

```
plugins/lerobot-robot-piper/lerobot_robot_piper/
├── __init__.py
├── config_piper_follower.py        # PiperFollowerBaseConfig + PiperFollowerConfig
├── piper_follower.py               # PiperFollower
├── config_bi_piper_follower.py     # BiPiperFollowerConfig
├── bi_piper_follower.py            # BiPiperFollower
└── subprocess_arm.py               # SubprocessFollower + _follower_worker

plugins/lerobot-teleoperator-robotis/lerobot_teleoperator_robotis/
├── __init__.py
├── config_robotis_leader.py        # RobotisLeaderBaseConfig + RobotisLeaderConfig
├── robotis_leader.py               # RobotisLeader (含 retry)
├── config_bi_robotis_leader.py     # BiRobotisLeaderConfig
├── bi_robotis_leader.py            # BiRobotisLeader
└── subprocess_leader.py            # SubprocessLeader + _leader_worker
```

## Feature 命名

```
# 14 channels (left 7 + right 7):
left_joint_1.pos ~ left_joint_6.pos, left_gripper.pos
right_joint_1.pos ~ right_joint_6.pos, right_gripper.pos
```

---

## 使用方式

### Teleop

```bash
lerobot-teleoperate \
    --robot.type=bi_piper_follower \
    --teleop.type=bi_robotis_leader \
    --fps=200
```

### Record（待測試）

```bash
lerobot-record \
    --robot.type=bi_piper_follower \
    --robot.left_arm_config.cameras="{ left_wrist: {type: opencv, index_or_path: /dev/video0, width: 640, height: 480, fps: 30} }" \
    --robot.right_arm_config.cameras="{ right_wrist: {type: opencv, index_or_path: /dev/video2, width: 640, height: 480, fps: 30} }" \
    --teleop.type=bi_robotis_leader \
    --dataset.repo_id=charliechan/piper-dual-arm-test \
    --dataset.num_episodes=3 \
    --dataset.single_task="pick up large object with both hands" \
    --dataset.fps=20 \
    --dataset.push_to_hub=false
```

---

## 踩坑記錄

### 1. draccus 無限遞迴

- **症狀**：`lerobot-teleoperate --robot.type=bi_piper_follower` 啟動後卡死，stack trace 無限重複 `choice_wrapper.py → dataclass_wrapper.py`
- **原因**：`BiPiperFollowerConfig` 的 field 直接用 `PiperFollowerConfig`（`RobotConfig` 的 registered subclass），draccus 展開 choice tree 時遇到自己 → 無限遞迴
- **修法**：拆出 `PiperFollowerBaseConfig`（純 dataclass），bimanual config 用 base config

### 2. GIL 搶佔導致 10 倍延遲

- **症狀**：雙手 teleop loop 40ms（24Hz），單手 4ms（200Hz+）。threading 並行化無效
- **驗證方法**：兩個獨立 terminal 各跑一隻手的 `lerobot-teleoperate` → 完全流暢
- **原因**：piper_sdk `C_PiperInterface_V2` 的 background CAN receive thread 在同一 process 內搶 Python GIL。兩個 instance 的 background threads 持續消耗 GIL time，導致主 thread 的 serial read 和 CAN write 都被拖慢
- **修法**：右手設備放在 `multiprocessing` subprocess 中，透過 `Pipe` 通訊

### 3. Dynamixel sync read 偶發失敗

- **症狀**：`RuntimeError: Sync read failed: [TxRxResult] There is no status packet!`
- **原因**：USB-Serial 通訊偶發瞬斷
- **修法**：`_read_positions_rad()` 加入 retry（最多 3 次）+ fallback 到上次讀數

---

## Benchmark 數據

使用 `tools/bench_dual_teleop.py`：

| 模式 | read_leader | send_action | total |
|------|------------|-------------|-------|
| 單手 (baseline) | 2.76ms | 1.55ms | **4.35ms** |
| 雙手同 process (sequential) | 24.20ms | 15.66ms | **39.92ms** |
| 雙手同 process (parallel threads) | 19.20ms | 16.06ms | **35.33ms** |
| 雙手 subprocess (最終方案) | ~4ms | ~2ms | **~8ms** |

---

## 待完成

- [ ] Step 5: 雙手 + camera 錄製測試
- [x] Step 6: 建立 `scripts/4_teleoperate_bimanual.sh`（teleop 已驗證通過）
- [ ] 更新 `doc/00-infra-overview.md` Phase 進度

## 參考

- LeRobot bimanual 範例：`lerobot/src/lerobot/robots/bi_so_follower/`
- LeRobot bimanual leader：`lerobot/src/lerobot/teleoperators/bi_so_leader/`
- 現有單手 plugin：`plugins/lerobot-robot-piper/`, `plugins/lerobot-teleoperator-robotis/`
- Benchmark 工具：`tools/bench_dual_teleop.py`
