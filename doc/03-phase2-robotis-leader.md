# Phase 2: ROBOTIS OMY-L100 Leader Teleoperator

## 目標

建立 `lerobot_teleoperator_robotis` plugin，用 OMY-L100 leader arm 直接驅動 Piper follower，
取代鍵盤 teleop，達成真正的 leader-follower teleoperation。

**狀態：✅ 全部完成**

---

## 技術決策

### 方案選擇：直接用 dynamixel_sdk（方案 B）

| 方案 | 做法 | 結論 |
|------|------|------|
| ~~A: DynamixelMotorsBus~~ | 用 LeRobot 內建的 Dynamixel 驅動 | ❌ 不支援 OMY-L100 的組合 |
| **B: dynamixel_sdk 直讀** | 用 Dynamixel SDK Protocol 2.0 直接 sync_read | ✅ 採用 |

Leader arm 只需要**讀 position**，不需要寫。直接用 `dynamixel_sdk` 做 sync_read 最簡單可靠。

---

## OMY-L100 硬體規格

### 實際馬達型號（X-series，非 YM-series）

> ⚠️ 雖然 URDF/xacro 文件提到 YM070/YM080，但實際硬體 ping 出來的是 X-series。

| Joint | Motor Model | Motor ID | Drive Mode | 方向 |
|-------|-------------|----------|------------|------|
| joint1 (base) | XH540-W150 (model 1110) | 1 | 0 | NORMAL |
| joint2 | XH540-W150 (model 1110) | 2 | 1 | REVERSE |
| joint3 | XH540-W150 (model 1110) | 3 | 0 | NORMAL |
| joint4 | XC330-T288 (model 1220) | 4 | 1 | REVERSE |
| joint5 | XC330-T288 (model 1220) | 5 | 0 | NORMAL |
| joint6 | XC330-T288 (model 1220) | 6 | 1 | REVERSE |
| rh_r1 (gripper) | XC330-T181 (model 1210) | 7 | 0 | NORMAL |

### X-series Register Addresses

| Register | Address | Length | 說明 |
|----------|---------|--------|------|
| Drive Mode | 10 | 1 byte | bit 0: 0=NORMAL, 1=REVERSE |
| Operating Mode | 11 | 1 byte | 0=Current Control (leader 用這個) |
| Homing Offset | 20 | 4 bytes | 全部為 0 |
| Torque Enable | 64 | 1 byte | 0=off, 1=on |
| Goal Current | 102 | 2 bytes | 寫入電流（gripper spring 用） |
| Present Velocity | 128 | 4 bytes | 讀取速度（gripper damping 用） |
| Present Position | 132 | 4 bytes | 讀取位置用 |

### Position 轉換

```
X-series: 4096 units = 1 revolution (2π rad)
Zero position: raw 2048 = 0 rad (物理中心點)

rad = (raw - 2048) × 2π / 4096
```

- 開機後 raw 值在 0-4095 範圍內（單圈絕對編碼器）
- 不關機轉超過一圈，raw 值會線性累加超出範圍
- 不做 normalize（避免 ±π 邊界跳變），靠 clamp 保障安全

### 通訊參數

| 項目 | 值 |
|------|-----|
| Protocol | 2.0 |
| Baud Rate | 4,000,000 bps |
| Serial Port | `/dev/robotis_left` (USB-Serial) |

---

## Joint Mapping（Leader → Follower）

### 校準方法

使用 `tools/calibrate_single.py` 逐 joint 校準：

```bash
python3 tools/calibrate_single.py <piper_joint>  # 1-6 or 7 (gripper)
```

流程：
1. 動 leader 的一個關節到一端 → 按 Enter
2. 動到另一端 → 按 Enter
3. 工具自動偵測哪個 motor、算出 scale 和 offset
4. 選方向（同向/反向）
5. 把結果貼進 `config_robotis_leader.py`

如果方向反了：scale 反號，offset = (min_rad + max_rad) - 原 offset。

### 當前 Mapping（ROS2 offset 基準 + 實測 motor 對應）

```python
joint_mapping: list[tuple] = field(default_factory=lambda: [
    (0, +1.0, +0.00,  -150.0, 150.0),  # Piper J1 ← M1  (base rotation)
    (1, +1.0, +1.57,     0.0, 150.0),  # Piper J2 ← M2  (shoulder)
    (2, +1.0, -2.66,  -170.0,   0.0),  # Piper J3 ← M3  (elbow)
    (4, +1.0, -1.57,  -100.0, 100.0),  # Piper J4 ← M5  (wrist roll)
    (3, +1.0, +1.57,   -70.0,  70.0),  # Piper J5 ← M4  (wrist pitch)
    (5, -1.0, +0.33,  -120.0, 120.0),  # Piper J6 ← M6  (wrist rotation)
])
```

格式：`(leader_index, scale, offset_rad, piper_min_deg, piper_max_deg)`

計算：`piper_deg = clamp(scale × leader_rad + offset) × 180/π, min, max)`

### Mapping 來源說明

- **Motor→Joint 對應**（M1→J1, M2→J2, ...）：`calibrate_mapping.py` 實測，逐 joint 動 leader 後 auto-detect
- **Scale ±1.0 & Offset**：來自 ROS2 `robotis2piper.py`，已驗證可用
- **ROS2 與 LeRobot 的 motor 對應不同**：ROS2 的 `robotis2piper.py` 使用 base↔tip 反轉 mapping（M4→J1, M1→J6），因為當時 leader arm 的物理擺放方式不同。當前 setup 是同向配置，所以用直接對應。兩者的 position 讀數（raw→rad 轉換）完全一致，只是 motor→joint 的對應關係因物理擺放而異
- 舊的校準參數和 ROS2 原始 mapping 都保留在 `config_robotis_leader.py` 的註解中

---

## 架構

### ROS2（原本）vs LeRobot Plugin（現在）

```
ROS2 (5 nodes + topics):
  hardware_interface → /joint_states → robotis2piper.py → /joint_ctrl → piper_ctrl_node → SDK

LeRobot Plugin (1 class, 直接呼叫):
  dynamixel_sdk.sync_read → mapping → PiperFollower.send_action() → SDK
```

### Plugin 結構

```
plugins/lerobot-teleoperator-robotis/
├── pyproject.toml
└── lerobot_teleoperator_robotis/
    ├── __init__.py
    ├── config_robotis_leader.py    # RobotisLeaderConfig
    └── robotis_leader.py           # RobotisLeader(Teleoperator)
```

### LeRobot 迴圈

```python
while True:                                    # 200 Hz
    action = teleop.get_action()               # 讀 leader 7 顆馬達 + mapping
    robot.send_action(action)                  # 送角度給 Piper
```

---

## 踩坑記錄

### 1. 馬達型號搞錯
- URDF/xacro 文件寫 YM070/YM080，但實際是 **X-series** (XH540, XC330)
- 用錯的 register address (512/552) 寫入導致 motors 4-7 進入 error state
- 確認方法：ROS2 launch log 會 ping 並顯示 model number

### 2. Position 轉換少了 center offset
- X-series 的 raw 2048 = 0 rad，必須減 2048
- 沒減的話所有值偏移 ~π rad，Piper 初始位置完全錯誤

### 3. Drive Mode REVERSE
- Motors 2, 4, 6 設為 REVERSE（bit 0 = 1）
- 最終用校準工具直接校準，scale 的正負號自動吸收方向差異

### 4. Multi-turn 模式
- 部分 motor 在 Current Control Mode 下位置值可超出 ±π
- 不做 atan2 normalize（會在 ±π 邊界造成危險跳變）
- 靠 clamp 限制 Piper 輸出範圍

### 5. Follower 抖動
- 原因 1：`max_relative_target` 機制每次讀回 Piper 位置再 clamp，讀回噪音造成震盪
- 原因 2：`MotionCtrl_2` 的第 4 參數用 `0x00`，ROS2 用 `0xAD`（軌跡平滑）
- 修正：關掉 `max_relative_target`（設 None），改用 `0xAD`

### 6. 頻率
- LeRobot 預設 60Hz，ROS2 用 200Hz
- 加 `--fps=200` 後延遲明顯改善

### 7. Gripper 不會自動回彈
- ROS2 用 `spring_actuator_controller` 對 M7 施加彈簧力矩，讓 gripper 鬆手時自動回到 open 位置
- LeRobot plugin 原本沒有這個功能，gripper 停在哪就在哪
- 修正：在 `robotis_leader.py` 加入 gripper spring effect，每個 cycle 對 M7 寫入 Goal Current
- 公式同 ROS2：`torque = -stiffness × (pos - neutral) - damping × velocity`
- 參數：`stiffness=0.06`, `neutral=0.0 rad`, `damping=0.004`（皆為 ROS2 預設值）
- M7 啟用 torque（Current Control Mode），其他 motor 維持 torque off
- Config: `gripper_spring_enabled`, `gripper_spring_stiffness`, `gripper_spring_damping` 等

### 8. 開機爆衝（K2 改良修復）
- 原因：Piper arm controller **內部記住上一次 session 的 JointCtrl 目標位置**。啟用 MOVE_J mode 後立刻往舊目標跑
- 這不是 CAN buffer 問題，`MotionCtrl_1` 清 trajectory 也無效
- 舊修法（hold-in-place）本質上是跟 stale command 賽跑，不穩定
- **新修法**：先讀當前位置 → 以 **1% 速度**啟用 MOVE_J → **連發 5 次** JointCtrl（當前位置）覆蓋舊目標 → 等 0.1s → 切到正常速度。即使舊目標被執行，1% 速度下幾乎不動
- 同時 `speed_rate` 改用 config 參數（預設 50%），不再寫死 100%

---

## 使用方式

### Teleoperate

```bash
lerobot-teleoperate --robot.type=piper_follower --robot.can_port=piper_left --teleop.type=robotis_leader --teleop.port=/dev/robotis_left --fps=200
```

### 校準工具

```bash
# 校準單一 joint
python3 tools/calibrate_single.py 1   # Piper J1

# 讀取 motor 狀態
python3 tools/test_robotis_read.py

# 檢查 Drive Mode
python3 tools/test_drive_mode.py
```

---

## LeRobot 整合驗證 ✅

### 1. 錄製 Data (`lerobot-record`)

```bash
lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --fps=200 \
    --dataset.repo_id=charliechan/piper-leader-test \
    --dataset.num_episodes=3 \
    --dataset.single_task="pick up cube" \
    --dataset.push_to_hub=false
```

- [x] 確認 joint states 正常錄製到 LeRobotDataset (3 episodes, 5364 frames)
- [x] 確認 fps 和資料完整性

### 2. 重播 Data (`lerobot-replay`)

- [x] 從錄好的 dataset 讀取 action 回放到 Piper
- [x] 確認軌跡和錄製時一致

### 3. 圖形介面錄製 + 回放

- [x] 使用 Rerun GUI 錄製（`--display_data=true`，需桌面環境 X11 + `rerun-sdk`）
- [x] 確認 camera 畫面即時顯示（單 camera `/dev/video0` 驗證通過）
- [x] 使用 `lerobot-dataset-viz` 回放錄製的 dataset（含 camera 影片 + joint 數值）

### 4. Episode 控制鍵

- [x] pynput 在 X11 session 下正常運作（Wayland 不支援，需切換到 "Ubuntu on Xorg"）
- [x] 右箭頭 → 提前結束 episode，左箭頭 ← 重錄，Esc 停止錄製

### 踩坑補充

- **Wayland 不支援 pynput**：桌面登入需選 "Ubuntu on Xorg"，pynput 才能抓到全域按鍵
- **`OpenCVCamera` 沒有 `channels` 屬性**：`observation_features` 中 camera shape 需從 config 讀 `(height, width, 3)`，不能從 camera instance 讀

---

## 參考

- OMY-L100 URDF: `ros2_ws/src/robotis/open_manipulator/open_manipulator_description/urdf/omy_l100/`
- OMY-L100 hardware config: `ros2_ws/src/robotis/open_manipulator/open_manipulator_bringup/config/omy_l100_leader_ai/`
- ROS2 mapping node: `ros2_ws/src/piper/piper_ros/src/piper/piper/robotis2piper.py`
- ROS2 Piper control node: `ros2_ws/src/piper/piper_ros/src/piper/piper/piper_ctrl_single_node.py`
- X-series model files: `ros2_ws/src/robotis/dynamixel_hardware_interface/param/dxl_model/xh540_w150.model`
