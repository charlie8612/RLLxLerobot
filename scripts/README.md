# Scripts

LeRobot integration test scripts. 檔名前綴數字代表所屬 Phase。

## Usage

```bash
conda activate piper
cd ~/piper-lerobot
bash scripts/<script_name>.sh
```

## Phase 2: Leader Arm Teleop

### 無 Camera

| Script | Description |
|--------|-------------|
| `2_record_leader.sh` | 用 ROBOTIS leader arm 錄製 3 episodes，fps=20，15s/episode，無 camera。Dataset: `charliechan/piper-leader-test` |
| `2_verify_dataset.sh` | 驗證 `piper-leader-test` dataset，印出 episode 數、frame 數、features |
| `2_replay_episode.sh` | 回放 `piper-leader-test` 的 episode。用法：`bash 2_replay_episode.sh [episode_num]`，預設 episode 0 |
| `2_teleoperate_leader.sh` | ROBOTIS leader arm → Piper follower teleop，fps=200 |

### 單 Camera

| Script | Description |
|--------|-------------|
| `2_record_leader_cam.sh` | 用 ROBOTIS leader arm + wrist camera 錄製 3 episodes，無 GUI。Dataset: `charliechan/piper-leader-cam-test` |
| `2_record_leader_cam_gui.sh` | 同上，但開啟 Rerun GUI 即時顯示 camera 畫面和 joint positions。需要桌面環境 + `pip install rerun-sdk` |
| `2_verify_dataset_cam.sh` | 驗證 `piper-leader-cam-test` dataset，確認有 camera observation |
| `2_replay_episode_cam.sh` | 回放 `piper-leader-cam-test` 的 episode 到 Piper。用法：`bash 2_replay_episode_cam.sh [episode_num]`，預設 episode 0 |
| `2_viz_dataset_cam.sh` | 用瀏覽器視覺化 `piper-leader-cam-test` dataset，可看 camera 影片和 joint 數值 |

## Phase 3: Dual Camera

| Script | Description |
|--------|-------------|
| `3_record_dual_cam.sh` | 雙 camera（overhead `/dev/cam_c270` + wrist `/dev/cam_arc`）錄製 3 episodes + Rerun GUI。Dataset: `charliechan/piper-dual-cam-test` |

## Phase 4: Dual Arm Teleop

| Script | Description |
|--------|-------------|
| `4_teleoperate_bimanual.sh` | 雙手 teleoperate：兩隻 ROBOTIS leader arm → 兩隻 Piper follower，fps=200 |

## Phase 5: Diffusion Policy (pick up cube)

| Script | Description |
|--------|-------------|
| `5_record_pick_cube.sh` | 錄製 pick up cube 訓練資料。50 episodes，leader arm + wrist camera + Rerun GUI。Dataset: `charliechan/piper-pick-cube` |
| `5_train_diffusion.sh` | 用 lerobot-train CLI 訓練 Diffusion Policy（含 wandb）。輸出至 `outputs/train/diffusion_piper/` |
| `5_train_diffusion_custom.py` | 獨立 Python 訓練腳本，可改參數、加 early stopping。輸出至 `outputs/train/diffusion_piper_custom/` |
| `5_eval_diffusion.sh` | 載入訓練好的 Diffusion Policy 在 Piper 上跑 inference + 錄製 eval episodes |
| `5_eval_diffusion_custom.py` | Eval + 手動標記成功/失敗。每個 episode 結束後按 s/f/d，自動統計 success rate，存 CSV log + 上傳 wandb |

## Phase 6: Pi0-FAST Fine-tune (pick up cube)

| Script | Description |
|--------|-------------|
| `6_train_pi0fast.sh` | Fine-tune Pi0-FAST pretrained model（含 wandb）。需先完成環境設定，見 [doc/07](../doc/07-phase6-pi0fast.md)。輸出至 `outputs/train/pi0fast_piper/` |
| `6_eval_pi0fast.sh` | 載入 fine-tuned Pi0-FAST 在 Piper 上跑 inference + 錄製 eval episodes |
