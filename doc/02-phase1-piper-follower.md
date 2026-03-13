# Phase 1: PiperFollower + Keyboard Teleop

## 目標

用最小可行的方式打通 LeRobot pipeline：
**鍵盤控制 Piper → record dataset → replay 驗證**

完成後你就有一個可用的 LeRobot-compatible Piper driver，
後續只需要加 leader arm teleoperator 和 camera 就能做 imitation learning。

---

## Step 1: 環境準備 ✅

### 1.1 安裝 LeRobot

```bash
conda activate piper

git clone https://github.com/huggingface/lerobot.git lerobot
cd lerobot
pip install -e ".[dev]"
```

### 1.2 確認 piper_sdk 可用

```bash
conda activate piper
pip install piper_sdk  # 如果 piper env 裡還沒裝的話
```

> **實際確認結果**：piper_sdk v0.6.1 已安裝在 `~/.local/lib/python3.10/site-packages/piper_sdk/`

### 1.3 確認 LeRobot 安裝正常

```bash
lerobot-teleoperate --help
lerobot-record --help
lerobot-replay --help
```

> ✅ 全部正常

---

## Step 2: 研究 LeRobot 介面 ✅

### 關鍵發現

文件裡原本預期的 features 格式是錯的。LeRobot **實際使用的是 flat dict**：

```python
# ❌ 原本的猜測（錯誤）
{"observation.state": {"dtype": "float32", "shape": (7,), ...}}

# ✅ 實際格式（參考 SO-100 實作）
{"joint_1.pos": float, "joint_2.pos": float, ..., "gripper.pos": float}
```

### 重要參考檔案

```
lerobot/src/lerobot/robots/robot.py              # Robot ABC
lerobot/src/lerobot/robots/config.py              # RobotConfig (draccus ChoiceRegistry)
lerobot/src/lerobot/robots/so_follower/           # SO-100 實作 — 最好的參考
lerobot/src/lerobot/teleoperators/teleoperator.py # Teleoperator ABC
lerobot/src/lerobot/utils/import_utils.py         # Plugin 自動發現機制
```

### LeRobot Plugin 自動發現機制

LeRobot 用 `importlib.metadata` 掃描所有已安裝的 pip package，前綴符合以下的會自動 import：
- `lerobot_robot_*`
- `lerobot_teleoperator_*`
- `lerobot_camera_*`
- `lerobot_policy_*`

Import 後，`@RobotConfig.register_subclass("type_name")` decorator 會自動向 draccus 註冊，
CLI 就能用 `--robot.type=type_name` 來指定。

Device class 是靠 config class name 反推的：`PiperFollowerConfig` → strip `Config` → `PiperFollower`，
然後在 `config_xxx.py` 同目錄的 `xxx.py` 裡找到這個 class。

---

## Step 3: 建立 lerobot_robot_piper plugin ✅

### 3.1 Package 結構（實際）

```
plugins/lerobot-robot-piper/
├── pyproject.toml
└── lerobot_robot_piper/
    ├── __init__.py                  # import config + class, 觸發 register
    ├── config_piper_follower.py     # PiperFollowerConfig
    └── piper_follower.py           # PiperFollower(Robot)
```

> ⚠️ **Package name 必須用底線** `lerobot_robot_piper`，不能用 hyphen `lerobot-robot-piper`，
> 因為 `register_third_party_plugins()` 會直接 `importlib.import_module(dist_name)`。

### 3.2 pyproject.toml

```toml
# plugins/lerobot-robot-piper/pyproject.toml
[build-system]
requires = ["setuptools>=64", "setuptools-scm>=8"]
build-backend = "setuptools.build_meta"

[project]
name = "lerobot_robot_piper"
version = "0.1.0"
description = "LeRobot plugin for AgileX Piper robot arm"
requires-python = ">=3.10"
dependencies = [
    "piper-sdk",
    "numpy",
]
```

### 3.3 Config（實際）

```python
# plugins/lerobot-robot-piper/lerobot_robot_piper/config_piper_follower.py
from dataclasses import dataclass, field
from lerobot.cameras import CameraConfig
from lerobot.robots.config import RobotConfig

@RobotConfig.register_subclass("piper_follower")
@dataclass
class PiperFollowerConfig(RobotConfig):
    can_port: str = "piper_left"
    speed_rate: int = 50
    max_relative_target: float | None = 5.0   # 度，每步最大變化量
    gripper_effort: int = 1000                 # 0.001 N*m
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
```

### 3.4 PiperFollower 實作（實際）

```python
# plugins/lerobot-robot-piper/lerobot_robot_piper/piper_follower.py
# 核心邏輯摘要，完整程式碼見檔案本身

class PiperFollower(Robot):
    config_class = PiperFollowerConfig
    name = "piper_follower"
```

**單位**：
- API 層：joint = 度 (degrees)，gripper = mm
- SDK 層：joint = 0.001 度，gripper = 0.001 mm
- 轉換：API × 1000 = SDK

**Features 格式**（flat dict, 每個 joint 一個 key）：
```python
observation_features = action_features = {
    "joint_1.pos": float,
    "joint_2.pos": float,
    "joint_3.pos": float,
    "joint_4.pos": float,
    "joint_5.pos": float,
    "joint_6.pos": float,
    "gripper.pos": float,
}
```

**connect() 流程**：
1. `C_PiperInterface_V2(can_port)` → `ConnectPort()`
2. `EnablePiper()` 迴圈等待直到 enable 確認（見下方踩坑記錄）
3. `MotionCtrl_2(0x01, 0x01, 100, 0x00)` 設定 CAN + MOVE J 模式
4. `GripperCtrl(0, effort, 0x01, 0)` enable gripper

**get_observation()**：
- `GetArmJointMsgs().joint_state.joint_1~6` → / 1000 = 度
- `GetArmGripperMsgs().gripper_state.grippers_angle` → / 1000 = mm

**send_action()**：
1. Joint limit clamp
2. `max_relative_target` 安全限速（讀 observation 比對差值）
3. `MotionCtrl_2(0x01, 0x01, 100, 0x00)` ← **每次都要呼叫**
4. `JointCtrl(j1, j2, j3, j4, j5, j6)` (0.001 度 int)
5. `GripperCtrl(abs(val), effort, 0x01, 0)` (0.001 mm int)

### 3.5 安裝

```bash
cd lerobot-robot-piper
pip install -e .
```

---

## Step 4: 建立 lerobot_teleoperator_keypad plugin ✅

> ⚠️ 原計畫叫 `lerobot-teleoperator-keyboard`，但改名為 `keypad`
> 以區分 LeRobot 內建的 `keyboard` teleoperator（那個是 event-based，不做 joint control）。

### 4.1 Package 結構（實際）

```
plugins/lerobot-teleoperator-keypad/
├── pyproject.toml
└── lerobot_teleoperator_keypad/
    ├── __init__.py
    ├── config_keypad_joint.py     # KeypadJointConfig
    └── keypad_joint.py           # KeypadJoint(Teleoperator)
```

### 4.2 pyproject.toml

```toml
# plugins/lerobot-teleoperator-keypad/pyproject.toml
[build-system]
requires = ["setuptools>=64", "setuptools-scm>=8"]
build-backend = "setuptools.build_meta"

[project]
name = "lerobot_teleoperator_keypad"
version = "0.1.0"
description = "Keyboard joint-space teleoperator for LeRobot"
requires-python = ">=3.10"
dependencies = [
    "numpy",
    "pynput",
]
```

### 4.3 實作重點

- **不用 pynput**：SSH 環境下 pynput 需要 X11 DISPLAY，改用 `termios` + `os.read()` 讀 raw terminal input
- 背景 thread 持續讀取鍵盤輸入，用 lock 同步
- 內部維護一個 7-dim target position array（度/mm）

**操作方式**：
```
1-6     : 選擇 joint 1~6
7       : 選擇 gripper
w / ↑   : 增加選中的 joint/gripper
s / ↓   : 減少選中的 joint/gripper
+/=     : 加大步進
-       : 減小步進
r       : 重置到初始位置
0       : 回到零位 (home)
```

**action_features** 和 robot 的一致：
```python
{"joint_1.pos": float, ..., "joint_6.pos": float, "gripper.pos": float}
```

### 4.4 安裝

```bash
cd lerobot-teleoperator-keypad
pip install -e .
```

---

## Step 5: 整合測試 — Teleoperate ✅

### 5.1 確認 CAN 啟動

```bash
ip -br link show | grep piper
# 預期看到：piper_left  UP
```

### 5.2 跑 teleoperate

```bash
lerobot-teleoperate \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --teleop.type=keypad_joint
```

**驗收結果**：
- [x] 按 1-6 選擇 joint，w/s 能讓對應 joint 動
- [x] 選 7 後 w/s 能開合夾爪
- [x] 控制迴圈穩定跑 ~59 Hz

---

## Step 6: 測試 Record ✅

### 6.1 LeRobot Record 機制說明

`lerobot-record` 的核心流程：

```
for each episode (共 num_episodes 個):
    for each frame (持續 episode_time_s 秒, 以 fps 頻率):
        obs = robot.get_observation()          # 讀取當前狀態
        action = teleop.get_action()           # 讀取操作指令
        robot.send_action(action)              # 執行動作
        dataset.add_frame({...obs, ...action}) # 存入 buffer
    dataset.save_episode()                     # 寫入磁碟（parquet + 影片編碼）
    if not last_episode:
        reset phase (reset_time_s 秒)          # 等待環境重置
```

**錄製中的鍵盤控制**（由 LeRobot 內建的 keyboard listener 處理，跟我們的 keypad teleop 分開）：
- `→` (右箭頭)：提前結束當前 episode，進入 reset
- `←` (左箭頭)：丟棄當前 episode，重新錄製
- `Esc`：停止整個錄製

> ⚠️ 這邊可能有衝突：我們的 keypad teleop 也用 raw terminal 讀按鍵。
> LeRobot 的 record 腳本另外開了一個 pynput keyboard listener 來抓 episode 控制鍵。
> SSH 環境下 pynput 不可用，episode 控制鍵可能失效。
> **解法**：先不管 episode 控制鍵，用 `--dataset.episode_time_s` 設定固定時長讓它自動結束。

### 6.2 Dataset 儲存位置

預設路徑：`$HF_LEROBOT_HOME/<repo_id>/`（通常是 `~/.cache/huggingface/lerobot/<repo_id>/`）

```
~/.cache/huggingface/lerobot/charliechan/piper-keyboard-test/
├── meta/
│   ├── info.json              # fps, features, robot_type 等 metadata
│   ├── stats.json             # 全局統計（min/max/mean/std）
│   ├── tasks.parquet          # task 描述
│   └── episodes/chunk-000/    # 每個 episode 的 metadata
├── data/chunk-000/            # observation + action 的 parquet 資料
└── videos/                    # 有 camera 才會有這個目錄
```

目前 Phase 1 沒有 camera，所以只有 `meta/` + `data/` 目錄，不會有 `videos/`。

### 6.3 執行 Record

```bash
lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --teleop.type=keypad_joint \
    --dataset.repo_id=charliechan/piper-keyboard-test \
    --dataset.num_episodes=3 \
    --dataset.single_task="move joints with keyboard" \
    --dataset.fps=20 \
    --dataset.episode_time_s=15 \
    --dataset.reset_time_s=5 \
    --dataset.video=false \
    --dataset.push_to_hub=false
```

參數說明：
- `fps=20`：20 Hz 錄製，夠用且不會太大
- `episode_time_s=15`：每個 episode 15 秒（鍵盤控制不需要太長）
- `reset_time_s=5`：episode 之間等 5 秒（手動把手臂歸位）
- `video=false`：Phase 1 沒有 camera
- `push_to_hub=false`：先存本地，不上傳

**操作流程**：
1. 啟動後 keypad teleop 會連線，顯示 joint 狀態
2. 用 `1-6` + `w/s` 控制手臂做簡單動作（例如移動 J1 來回）
3. 15 秒後自動結束 episode
4. 5 秒 reset 時間，手動把手臂歸位（按 `0` 回 home）
5. 重複 3 次

**驗收結果**：
- [x] 能順利錄完 3 個 episode，沒有 crash
- [x] Dataset 儲存在 `~/.cache/huggingface/lerobot/charliechan/piper-keyboard-test/`
- [x] Python 檢查 dataset 內容正確

```python
from lerobot.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset("charliechan/piper-keyboard-test")
print(f"Episodes: {ds.meta.total_episodes}")   # → 3
print(f"Frames: {len(ds)}")                     # → 897 (299 × 3)
print(f"Features: {list(ds.meta.features.keys())}")
# → ['action', 'observation.state', 'timestamp', 'frame_index', 'episode_index', 'index', 'task_index']
```

> ⚠️ **注意事項**：
> - import 路徑是 `lerobot.datasets`（不是 `lerobot.common.datasets`）
> - SSH 環境下 LeRobot 內建的 episode 控制鍵（←/→/Esc）不可用（pynput 需要 X11），
>   會顯示 "Switching to headless mode" 警告，但不影響錄製功能
> - LeRobot **不會自動讓手臂歸位**，reset phase 只是計時器，需要手動按 `0` 歸位
> - Episode 之間位置是連續的，如果不手動歸位，下一個 episode 會從上一個結束的位置繼續

---

## Step 7: 測試 Replay ✅

### 7.1 LeRobot Replay 機制說明

`lerobot-replay` 很單純：

```
dataset = LeRobotDataset(repo_id, episodes=[episode])
for each frame in dataset:
    action = frame[action_columns]        # 從 dataset 讀取 action
    robot.send_action(action)             # 發送到機器人
    sleep(1/fps - execution_time)         # 維持原始 fps
```

不需要 teleoperator，只需要 robot + dataset。

### 7.2 執行 Replay

```bash
lerobot-replay \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --dataset.repo_id=charliechan/piper-keyboard-test \
    --dataset.episode=0
```

**驗收結果**：
- [x] Piper 能重現錄製時的動作軌跡
- [x] 軌跡看起來跟錄製時大致相符

### 7.3 注意事項

- Replay 前建議先手動把手臂移到錄製起始位附近，否則第一幀會突然跳位
  （`max_relative_target=5.0` 會限速，但仍會有突然移動的感覺）
- Replay 使用 dataset 錄製時的 fps（這裡是 20 Hz）

---

## 踩坑記錄

### Bug 1: EnableArm 從未被呼叫（Joint 不動但 Gripper 能動）

**現象**：`send_action()` 有呼叫 `MotionCtrl_2()` + `JointCtrl()`，joint 就是不動。Gripper 正常。

**原因**：
```python
# ❌ 錯誤寫法
while not self.piper.GetArmEnableStatus():  # 回傳 list，非空 list 永遠 truthy
    self.piper.EnableArm(7)                  # ← 從未執行

# ✅ 正確寫法
while not self.piper.EnablePiper():          # 回傳 bool，內部有 enable 確認機制
    time.sleep(0.01)
```

`GetArmEnableStatus()` 回傳的是 `list[bool]`（7 個馬達的狀態），
在 Python 裡非空 list 永遠是 truthy，所以 `not list` = `False`，迴圈體永遠不執行。

另外也需要用 `C_PiperInterface_V2`（不是 `C_PiperInterface`），`EnablePiper()` 是 V2 的 convenience method。

### Bug 2: pynput 在 SSH 下不可用

**現象**：`PYNPUT_AVAILABLE = False`，teleop 直接 raise error。

**原因**：pynput 的 keyboard listener 需要 X11 DISPLAY。SSH 進去的 terminal 沒有 DISPLAY。

**解法**：改用 `termios` + `tty.setcbreak()` + `os.read()` 做 raw terminal input，
完全不依賴 X11。加上 `w`/`s` 鍵作為 ↑/↓ 的替代（escape sequence 在某些 terminal 下可能被吃掉）。

### Bug 3: Arrow keys 的 escape sequence 被 Python buffered IO 吃掉

**現象**：`sys.stdin.read(1)` 無法正確讀取 arrow key 的 3-byte escape sequence `\x1b[A`。

**原因**：`sys.stdin.read()` 走 Python 的 buffered IO，在 cbreak mode 下行為不可靠。

**解法**：改用 `os.read(fd, 16)` 做 unbuffered read，一次讀取所有可用 bytes，
手動解析 escape sequence。同時加 `w`/`s` 作為 fallback。

---

## piper_sdk API 筆記

### 單位

| 項目 | SDK 單位 | API 單位 | 轉換 |
|------|----------|----------|------|
| Joint angle | 0.001 度 (int) | 度 (float) | × 1000 |
| Gripper stroke | 0.001 mm (int) | mm (float) | × 1000 |
| Gripper effort | 0.001 N·m (int) | — | 1000 = 1 N·m |

### Joint Limits（度）

| Joint | Min | Max |
|-------|-----|-----|
| J1 | -150 | 150 |
| J2 | 0 | 180 |
| J3 | -170 | 0 |
| J4 | -100 | 100 |
| J5 | -70 | 70 |
| J6 | -120 | 120 |
| Gripper | 0 mm | 70 mm |

### 關鍵 API 呼叫順序

```python
from piper_sdk import C_PiperInterface_V2

piper = C_PiperInterface_V2("piper_left")
piper.ConnectPort()

# 1. Enable（必須用 EnablePiper 迴圈等待）
while not piper.EnablePiper():
    time.sleep(0.01)

# 2. 設定模式（每次 JointCtrl 前都要呼叫）
piper.MotionCtrl_2(0x01, 0x01, 100, 0x00)
#                   │     │     │    └─ 0x00=position-velocity, 0xAD=MIT
#                   │     │     └─ speed rate 0-100%
#                   │     └─ 0x01=MOVE J (joint control)
#                   └─ 0x01=CAN control mode

# 3. 發送 joint 目標（0.001 度 int）
piper.JointCtrl(j1, j2, j3, j4, j5, j6)

# 4. Gripper（獨立控制，不依賴 MotionCtrl_2）
piper.GripperCtrl(angle_0001mm, effort_0001nm, 0x01, 0)
#                                               └─ 0x01=enable

# 5. 讀取 feedback
joints = piper.GetArmJointMsgs()     # .joint_state.joint_1~6 (0.001 度)
grip = piper.GetArmGripperMsgs()     # .gripper_state.grippers_angle (0.001 mm)
```

### 其他參考

- piper_sdk demo 目錄：`~/.local/lib/python3.10/site-packages/piper_sdk/demo/V2/`
- [Reimagine-Robotics/piper_control](https://github.com/Reimagine-Robotics/piper_control)：
  更高層的控制框架，包裝了 piper_sdk。目前未使用，直接用 piper_sdk 即可。
