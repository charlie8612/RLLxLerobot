# Tools

LeRobot dataset 維護工具、校準工具、debug 工具。

## Usage

```bash
conda activate piper
cd ~/piper-lerobot
python tools/<tool_name>.py --help
```

## Dataset 維護

| Tool | Description |
|------|-------------|
| `delete_episodes.py` | 從 dataset 中刪除指定的壞 episodes。支援預覽（`--list`）、刪除（`--delete`）、備份控制（`--no-backup`） |

### delete_episodes.py

```bash
# 列出所有 episode 及 frame 數
python tools/delete_episodes.py charliechan/piper-pick-cube --list

# 刪除 episode 3 和 7
python tools/delete_episodes.py charliechan/piper-pick-cube --delete 3 7

# 刪除且不保留備份
python tools/delete_episodes.py charliechan/piper-pick-cube --delete 3 7 --no-backup
```

> **Bad episode 處理流程**：錄製時發現壞的 episode，用左箭頭重錄。事後發現的，用 `delete_episodes.py --delete` 直接刪除後重新訓練。不需要額外的 filtering 機制，直接刪最乾淨。

## Wandb 維護

| Tool | Description |
|------|-------------|
| `wandb_cleanup.py` | Wandb run 清理工具。列出、篩選、刪除 wandb runs |

### wandb_cleanup.py

```bash
# 列出所有 runs
python tools/wandb_cleanup.py --project piper-pick-cube --list

# 只列出 crashed / failed runs
python tools/wandb_cleanup.py --project piper-pick-cube --list --state crashed,failed

# 列出沒有 summary metrics 的空 runs
python tools/wandb_cleanup.py --project piper-pick-cube --list --empty

# 刪除指定 run IDs
python tools/wandb_cleanup.py --project piper-pick-cube --delete abc123 def456

# 刪除所有空 runs（會先確認）
python tools/wandb_cleanup.py --project piper-pick-cube --delete-empty

# Dry run（只顯示會刪什麼，不真的刪）
python tools/wandb_cleanup.py --project piper-pick-cube --delete-empty --dry-run
```

## Calibration

| Tool | Description |
|------|-------------|
| `calibrate_mapping.py` | 互動式校準工具，mapping OMY-L100 leader joints → Piper follower joints |
| `calibrate_single.py` | 單 joint 校準。用法：`python tools/calibrate_single.py <piper_joint>`（1-6 或 7=gripper） |

## Debug / 狀態查詢

| Tool | Description |
|------|-------------|
| `read_piper.py` | 讀取 Piper 當前 6 軸角度 + 夾爪位置 |
| `test_robotis_read.py` | Debug 工具，即時讀取 OMY-L100 所有馬達位置 |
| `test_compare_ros2.py` | 比較 ROS2 node 和 dynamixel_sdk 直讀的數值 |
| `test_drive_mode.py` | 測試 Piper 控制模式 |

## Waypoint Capture + Interpolation (B9)

| Tool | Description |
|------|-------------|
| `waypoint.py` | 用 leader arm teleop 到定點，記錄 waypoint，收集完後自動播放軌跡。適合固定流程的任務（定點取放），不需要訓練 policy |

### 錄製

```bash
python tools/waypoint.py record -o waypoints/pick_place.json
```

用 leader arm 控制 Piper，到達想記錄的位置後：

| 輸入 | 功能 |
|------|------|
| Enter | 記錄當前位置（到達後不停留） |
| `p<秒數>` | 記錄當前位置，到達後暫停 N 秒（例如 `p2`） |
| `d` | 刪除最後一個 waypoint |
| `l` | 列出目前所有 waypoints |
| `q` | 結束錄製並存檔 |

### 播放

```bash
# 預設速度（60 deg/s）播放一次
python tools/waypoint.py execute waypoints/pick_place.json

# 慢速播放，迴圈 3 次
python tools/waypoint.py execute waypoints/pick_place.json --speed 30 --loop 3
```

### 查看

```bash
python tools/waypoint.py list waypoints/pick_place.json
```

### 安全關機

結束時（Ctrl+C 或 q），手臂會先慢速移到 rest position 再斷電，不會直接摔落。Rest position 定義在 `waypoint.py` 的 `REST_STATE`。如需更新，用 `python tools/read_piper.py` 讀取當前安全姿態角度後修改。
