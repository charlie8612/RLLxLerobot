# Lab Robotics Infrastructure Overview

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 LeRobot (上層 framework)                  │
│   lerobot-teleoperate / lerobot-record / lerobot-train   │
│   dataset, policy (ACT / Diffusion / Pi0), eval          │
└──────────┬──────────────────────────────┬────────────────┘
           │                              │
     Teleoperator API               Robot API
     get_action()                   get_observation()
                                    send_action()
           │                              │
┌──────────▼──────────────┐  ┌────────────▼───────────────┐
│  lerobot-teleoperator-  │  │  lerobot-robot-piper       │
│  robotis (plugin)       │  │  (plugin)                  │
│                         │  │                            │
│  dynamixel_sdk          │  │  piper_sdk                 │
│  (Protocol 2.0 直讀)     │  │  C_PiperInterface_V2       │
└──────────┬──────────────┘  └────────────┬───────────────┘
           │                              │
     ROBOTIS OMY-L100               CAN Bus (1 Mbps)
     (Leader Arm)                   piper_left / piper_right
           │                              │
           └──────── 人操作 ──────────────┘
                  (teleoperation)
```

## 設計原則

1. **解耦控制層**：機器人硬體控制（piper_sdk）與上層框架（LeRobot）分離
2. **Plugin 架構**：以 LeRobot 外掛套件形式存在，不改 LeRobot 原始碼
3. **不依賴 ROS2**：LeRobot pipeline 直接透過 CAN/Serial 與硬體通訊
4. **可替換性**：換機器人只需換 plugin，dataset/training 不用改

## 硬體接線 (現有)

```
USB-CAN adapter ──→ piper_left  (CAN, 1 Mbps)  ──→ Piper Arm (左手)
USB-Serial      ──→ /dev/robotis_left  (ttyUSB1) ──→ ROBOTIS Leader (左手)
USB Camera      ──→ /dev/cam_c270 (Logitech 046d:0825) ──→ Overhead Camera (旁邊固定視角)
USB Camera      ──→ /dev/cam_arc  (ARC 05a3:9230)     ──→ Wrist Camera (eye-in-hand)
```

> udev rules 檔案：`config/99-usb-camera.rules`（安裝方式見檔案內註解）
>
> CAN udev rules 檔案：`config/99-usb-can.rules`（綁定 USB-CAN serial → `piper_left` / `piper_right`）

### CAN Bus 啟動

CAN interface 開機後預設是 **DOWN**，每次開機（或插拔 USB-CAN）後需要手動啟動：

```bash
bash scripts/0_can_up.sh
```

> ⚠️ 需要 sudo 權限。此腳本會自動偵測 `piper_left` / `piper_right`，設定 bitrate 1 Mbps 並啟動。
> 未啟動的話，任何與 Piper arm 通訊的腳本都會報 `CAN port piper_left is not UP`。

> ⚠️ **Camera 權限**：使用者必須加入 `video` group 才能存取 USB camera：
> ```bash
> sudo usermod -aG video $USER
> ```
> 加完後需要**重新登入**才會生效。未加入會導致 OpenCV / `lerobot-find-cameras` 無法開啟 camera device。

## Pipeline 流程

```
1. Teleoperate    人用 leader arm (或鍵盤) 操作 follower
2. Record         LeRobot 同步錄製 joint states + camera → LeRobotDataset
3. Replay         從 dataset 讀取 action 回放到 follower，驗證軌跡品質
4. Train          用 ACT / Diffusion Policy 等訓練 imitation learning model
5. Eval           載入 trained policy，在真實機器人上推論執行 + 手動標記 success/fail → CSV + wandb
```

## 現有資源

| Repo | 用途 | 狀態 |
|------|------|------|
| `piper_sdk` (pip) | 官方 Python CAN bus SDK | 穩定，直接用 |
| `piper_ros` (`ros2_ws/src/piper/`) | ROS2 控制節點 | 現有 teleop 用，LeRobot 不需要 |
| `piper_control` | Lab 改寫的控制框架 | 可參考 API 設計 |
| `piper_util` | 寫死動作 demo 工具 | 參考用 |
| ROBOTIS packages (`ros2_ws/src/robotis/`) | OMY-L100 leader arm | leader 端驅動 |

## 儲存空間管理

`/home` 磁碟空間有限（863G），大型檔案已搬到 `/tmp2/charlie` 並用 symlink 指回原路徑，對腳本透明。

| 原路徑 | 搬到 | 說明 |
|--------|------|------|
| `~/.cache/huggingface/hub` | `/tmp2/charlie/huggingface-cache/hub` (symlink) | 所有 HuggingFace model weights |
| `~/.cache/huggingface/lerobot` | `/tmp2/charlie/huggingface-cache/lerobot` (symlink) | LeRobot dataset cache、eval recordings、calibration |
| `outputs/train/diffusion_dual_cam` | `/tmp2/charlie/training-outputs/` | Diffusion Policy 訓練 checkpoints (21 個) |

> ⚠️ `/tmp2/charlie` 的資料不在 `/home` 備份範圍內，重要的 checkpoint 應另外備份。
>
> 定期可清理的快取（不影響功能，需要時會自動重新下載/產生）：
> - `~/.cache/wandb/artifacts/` — wandb artifact 快取
> - `pip cache purge` — pip 下載快取

## Phase 進度

| Phase | 內容 | 狀態 | 文件 |
|-------|------|------|------|
| 1 | PiperFollower + Keyboard Teleop | ✅ 完成 | [02](02-phase1-piper-follower.md) |
| 2 | ROBOTIS Leader Teleoperator + Record/Replay/GUI | ✅ 完成 | [03](03-phase2-robotis-leader.md) |
| 3 | Dual Camera 整合 | ✅ 完成 | [04](04-phase3-dual-camera.md) |
| 4 | 雙手 Teleoperation | ✅ Teleop 完成 | [05](05-phase4-dual-arm-teleop.md) |
| 5 | Diffusion Policy（從零訓練） | ✅ 完成（收集→訓練→Eval） | [06](06-phase5-diffusion-policy.md) |
| 6 | Pi0-FAST（Pretrained Fine-tune） | 🔧 訓練完成，inference 慢（~30s/chunk） | [07](07-phase6-pi0fast.md) |
| 7 | SmolVLA（輕量 VLA） | 🔧 Inference 可跑，待 fine-tune | [08](08-phase7-smolvla.md) |

> Phase 4 (雙手) 不擋 Phase 5/6。單手雙 camera 就可以訓練。

## Scripts & Tools

操作用腳本和維護工具，詳見各自 README。

| 目錄 | 用途 | README |
|------|------|--------|
| `scripts/` | Phase 別的錄製、回放、驗證、訓練、eval 腳本 | [scripts/README.md](../scripts/README.md) |
| `tools/` | Dataset 維護、wandb 維護、校準、debug 工具（Python） | [tools/README.md](../tools/README.md) |

### 錄製操作快捷鍵

| 按鍵 | 功能 |
|------|------|
| → (右箭頭) | 提前結束當前 episode |
| ← (左箭頭) | 重錄當前 episode |
| Esc | 停止錄製，正常退出 |

> 注意：不要用 Ctrl+C 結束錄製，會導致 camera 資源無法釋放。

## 待評估功能（Backlog）

以下功能尚未確定要做，但在 robot learning lab 中常見且可能需要。

| # | 功能 | 說明 | Priority | 完成 |
|---|------|------|:--------:|:----:|
| B1 | DAgger / 人類介入修正 | Policy 執行中人可隨時拿 leader arm 接管修正，修正資料自動追加進 dataset。比「失敗→重錄整段」高效很多。LeRobot 無原生支援，需在 eval loop 加 teleop 接管切換。 | 🟠 | |
| B2 | Simulation 環境 | MuJoCo / Isaac Sim / SAPIEN，用於無限生成 data、快速驗證 policy、sim2real transfer。需確認 Piper 是否有現成 URDF/MJCF。 | 🟢 | |
| B3 | Foundation Model 微調 | 用 pre-trained model（Pi0、Octo、OpenVLA）fine-tune，資料需求可從 50 episodes 降到 10-20。LeRobot 已部分支援（如 Pi0）。 | 🟠 | |
| B4 | Automated Success Detection | Eval 時自動判斷 episode 成功/失敗。可用額外 camera + vision check 或感測器，結果自動寫進 eval log。 | 🟢 | |
| B5 | Dataset Annotation / Reward Labeling | 標記 episode 品質（good/ok/bad）、sub-task phase（approach→grasp→lift）、reward signal。用於 weighted IL 或 RLHF。 | 🟢 | |
| B6 | Multi-task / Task Conditioning | 一個 policy 執行多種任務，錄製時標記 language instruction，訓練用 language-conditioned policy。LeRobot 的 single_task 欄位已有基礎。 | 🟢 | |
| B7 | VR Teleop | 用 VR controller（如 Meta Quest）做 teleop，6-DOF 操作更直覺，資料品質更高。需另寫一套 teleoperator plugin。 | 🟢 | |
| B8 | Checkpoint 管理與 A/B Deploy | 記錄每個 checkpoint 對應的 training config、dataset version、eval 結果，快速切換比較。避免手動改路徑。 | 🟢 | |
| B9 | Waypoint Capture + Interpolation | 用 teleop 控制手臂到定點，按 Enter 記錄 waypoint，收集完後用 smoothstep interpolation 自動生成軌跡執行。適合固定流程的任務（如定點取放），不需要訓練 policy。`tools/waypoint.py`，詳見 [tools/README.md](../tools/README.md)。 | 🟠 | ✅ |

## Known Issues

| # | 問題 | 說明 | Priority | 解決 |
|---|------|------|:--------:|:----:|
| K1 | keypad plugin 未裝時 LeRobot 噴 warning | 搬移路徑後重新 `pip install -e` 時漏裝 keypad plugin，啟動任何 LeRobot 指令都會噴 `No module named 'lerobot_teleoperator_keypad'` error log。原因是 LeRobot 的 `register_third_party_plugins()` 會掃所有已註冊的 `lerobot_*` package metadata，即使當前指令沒用到也會嘗試 import。<br><br>**修法**：已補裝修復。未來搬移路徑時記得三個 plugin 都要重裝。 | 🔴 | ✅ |
| K2 | 開機時手臂跳到上一次位置 | Piper arm controller 內部記住上一次 `JointCtrl` 目標位置，啟用 MOVE_J 後往舊目標跑。不是 CAN buffer 問題，清 trajectory 也無效。<br><br>**修法**：以 1% 速度啟用 MOVE_J，連發 5 次 hold-in-place 覆蓋舊目標，再切到正常速度。 | 🔴 | ✅ |
| K3 | USB camera 權限問題 | 新接的 USB camera 可能被分配到 `root:video` 權限的 device node（如 `/dev/video6`），導致 `lerobot-find-cameras` 和 OpenCV 無法開啟。<br><br>**修法**：`sudo usermod -aG video charliechan`，然後 `sudo loginctl kill-user charliechan` 強制重建 session（VS Code Remote SSH 的 systemd user session 不會因重連而刷新 group）。 | 🟠 | ✅ |
| K4 | 錄製時無語音提示（spd-say 沒聲音） | PulseAudio 的 default sink 變成 `auto_null`（虛擬空裝置），加上 ALSA Master/Headphone 被 mute，導致 `spd-say` 播不出聲音。多人共用機器時 PulseAudio 是 per-user 的，重啟不影響其他人。<br><br>**修法**：`pulseaudio -k && pulseaudio --start` 重啟自己的 PulseAudio，然後 `amixer -c 0 set Master unmute && amixer -c 0 set Master 80% && amixer -c 0 set Headphone unmute && amixer -c 0 set Headphone 80%`，最後 `spd-say "test"` 驗證。 | 🟠 | ✅ |
| K5 | 雙手 Ctrl+C 關閉不乾淨 | 雙手 teleop 按 Ctrl+C 時只關掉一隻手臂，需要按兩次才能完全退出。推測是 subprocess 的 signal handling 問題，主 process 收到 SIGINT 後只 disconnect 了一側。 | 🟢 | |
| K6 | C270 USB 斷線 | C270 插在 Bus 05（獨立 2-port USB controller）時會頻繁斷線重連。<br><br>**修法**：改插到跟 cam_arc 同一排的 USB 孔（Bus 01，16-port 主 controller）。用 `lsusb -t` 確認 C270 在 Bus 01 底下。 | 🟠 | ✅ |
| K7 | Eval 時 FPS warning 洗版 | `lerobot-record` 有 policy 時，推論造成的 FPS 下降是正常的（chunk inference ~2s），但 warning 會一直刷。<br><br>**修法**：patch `lerobot/src/lerobot/scripts/lerobot_record.py` L422，有 policy 時不印 warning。**注意：這是直接改 LeRobot 原始碼，更新 LeRobot 時需重新 apply。** | 🟢 | ✅ |
| K8 | Ctrl+C 手臂倒地 | `lerobot-record` 的 `finally` block 先跑 `log_say("Stop recording", blocking=True)` 再 `disconnect()`。Ctrl+C 若打斷在 `select_action` 或 `log_say` 卡住時，`disconnect()` 來不及跑，手臂直接斷電倒地。<br><br>**修法**：patch `lerobot_record.py` 的 `finally` block，將 `robot.disconnect()` 移到最前面並包 try/except。**注意：這是直接改 LeRobot 原始碼，更新 LeRobot 時需重新 apply。** | 🔴 | ✅ |

## 安全原則

> **所有 script / tool / command 都不要使用 `sudo`。** 如果確實需要 root 權限，必須先確認後才能加。

## 文件維護原則

> **每次有新的開發動作（新 phase、新功能、bug fix、架構變更等），完成後都要回來更新對應的文件。**
>
> - 更新本文件的 **Phase 進度表**
> - 更新或新增對應的 phase 文件（`0x-phaseN-xxx.md`）
> - 如果有新腳本，更新 `scripts/README.md`
> - 如果有新工具，更新 `tools/README.md`
> - 確保路徑、狀態、數據與實際一致，不要讓文件和程式碼脫節

## 相關文件

- [01-lerobot-piper-plugin.md](01-lerobot-piper-plugin.md) — Plugin 架構與 package 結構
- [02-phase1-piper-follower.md](02-phase1-piper-follower.md) — Phase 1 詳細步驟與踩坑記錄
- [03-phase2-robotis-leader.md](03-phase2-robotis-leader.md) — Phase 2 硬體規格、校準、踩坑記錄
- [04-phase3-dual-camera.md](04-phase3-dual-camera.md) — Phase 3 雙 camera 計畫
- [05-phase4-dual-arm-teleop.md](05-phase4-dual-arm-teleop.md) — Phase 4 雙手 teleop 計畫
- [06-phase5-diffusion-policy.md](06-phase5-diffusion-policy.md) — Phase 5: Diffusion Policy
- [07-phase6-pi0fast.md](07-phase6-pi0fast.md) — Phase 6: Pi0-FAST Fine-tune
- [08-phase7-smolvla.md](08-phase7-smolvla.md) — Phase 7: SmolVLA 輕量 VLA
- [08-openpi-evaluation.md](08-openpi-evaluation.md) — OpenPI (JAX) 評估：是否值得遷移
