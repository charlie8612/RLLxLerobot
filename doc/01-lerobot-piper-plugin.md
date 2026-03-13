# LeRobot Piper Plugin — 架構與 Package 結構

## 目標

建立 LeRobot plugin packages，讓 Piper + ROBOTIS leader arm 可以直接使用
LeRobot 的 teleoperate / record / replay / train pipeline。

## Plugin Packages

### lerobot_robot_piper（Follower）

```
plugins/lerobot-robot-piper/
├── pyproject.toml
└── lerobot_robot_piper/
    ├── __init__.py
    ├── config_piper_follower.py     # PiperFollowerConfig
    └── piper_follower.py           # PiperFollower(Robot)
```

- CLI type: `--robot.type=piper_follower`
- 透過 `piper_sdk` (`C_PiperInterface_V2`) 控制 Piper arm
- 支援 cameras dict 傳入（CLI 或 config）

### lerobot_teleoperator_robotis（Leader Arm）

```
plugins/lerobot-teleoperator-robotis/
├── pyproject.toml
└── lerobot_teleoperator_robotis/
    ├── __init__.py
    ├── config_robotis_leader.py    # RobotisLeaderConfig
    └── robotis_leader.py           # RobotisLeader(Teleoperator)
```

- CLI type: `--teleop.type=robotis_leader`
- 透過 `dynamixel_sdk` Protocol 2.0 sync_read 讀取 leader arm position
- 內建 joint mapping（scale + offset）轉換到 Piper 角度

### lerobot_teleoperator_keypad（鍵盤 Teleop）

```
plugins/lerobot-teleoperator-keypad/
├── pyproject.toml
└── lerobot_teleoperator_keypad/
    ├── __init__.py
    ├── config_keypad_joint.py     # KeypadJointConfig
    └── keypad_joint.py           # KeypadJoint(Teleoperator)
```

- CLI type: `--teleop.type=keypad_joint`
- 用 `termios` raw terminal input（不依賴 X11）
- 主要用於測試，正式錄製用 leader arm

## LeRobot Plugin 自動發現機制

LeRobot 用 `importlib.metadata` 掃描已安裝的 pip package，前綴符合以下的會自動 import：
- `lerobot_robot_*`
- `lerobot_teleoperator_*`
- `lerobot_camera_*`
- `lerobot_policy_*`

Import 後，`@RobotConfig.register_subclass("type_name")` decorator 自動向 draccus 註冊，
CLI 就能用 `--robot.type=type_name` 來指定。

Device class 靠 config class name 反推：`PiperFollowerConfig` → strip `Config` → `PiperFollower`，
在同目錄找到對應 class。

> ⚠️ Package name 必須用底線 `lerobot_robot_piper`，不能用 hyphen，
> 因為 `register_third_party_plugins()` 會直接 `importlib.import_module(dist_name)`。

## 安裝

```bash
cd plugins/lerobot-robot-piper && pip install -e .
cd plugins/lerobot-teleoperator-robotis && pip install -e .
cd plugins/lerobot-teleoperator-keypad && pip install -e .
```
