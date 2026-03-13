# Phase 5: Diffusion Policy（從零訓練）

## 目標

用左手 Piper 的 teleoperation 資料，從零訓練 Diffusion Policy，驗證 imitation learning pipeline。

**狀態：✅ 完成（收集→訓練→Eval pipeline 打通）**

## 前置條件

- [x] 單手 teleop + record + replay pipeline 完成
- [x] 雙 camera 整合完成（overhead + wrist）
- [x] 決定訓練用的任務

## 任務定義

- **任務**：pick up cube（抓起方塊）
- **場景**：桌面上放一個方塊，Piper 從固定起始位抓起
- **Camera**：雙 camera（`overhead` + `wrist`，640x480@30fps）
- **成功條件**：方塊離開桌面

## 硬體資源

| GPU | VRAM | 用途 |
|-----|------|------|
| RTX 3090 | 24 GB | 主要訓練 / inference |
| RTX 3080 | 10 GB | 備用 |

## Piper Action Space

- 6 revolute joints + 1 gripper = **7 維 action**
- joint_1~6：位置控制（degrees）
- gripper：行程控制（0~70 mm）

---

## 步驟一：資料收集

- [x] 佈置場景（桌面、方塊位置、camera 角度）
- [x] 用 leader arm 錄製 episodes

```bash
bash scripts/5_record_pick_cube.sh
```

- [x] 檢查資料品質，刪除失敗的 episode

### 資料收集結果

| 項目 | 值 |
|------|-----|
| Dataset | `charliechan/piper-pick-cube-dual` |
| Episodes | 10 |
| Frames | 2435 |
| FPS | 20 |
| Features | `action`, `observation.state`, `observation.images.overhead`, `observation.images.wrist` |

### 資料收集注意事項

- 錄製時用鍵盤控制，**不要用 Ctrl+C**（會導致 camera 鎖住）：
  - **→**（右箭頭）：提前結束當前 episode
  - **←**（左箭頭）：重錄當前 episode
  - **Esc**：停止錄製，正常退出
- 如果 camera 卡住：`sudo fuser -k /dev/videoN`
- 刪除壞 episode 用工具：`python tools/delete_episodes.py charliechan/piper-pick-cube-dual --delete <ep_num>`

---

## 步驟二：訓練

### 模型資訊

| 項目 | 值 |
|------|-----|
| 架構 | ResNet18 (vision) + 1D UNet (action denoising) |
| 參數量 | ~60-80M |
| Noise scheduler | DDPM (train) / DDPM 10 steps (inference) |
| Diffusion 參數 | horizon=16, n_obs_steps=2, n_action_steps=8 |
| Image resize | 240x320 |
| VRAM 需求 | 訓練 ~8-12 GB，inference < 1 GB |
| 訓練量 | 20K steps（RTX 3090） |

### 訓練指令

```bash
bash scripts/5_train_diffusion.sh
```

### 訓練注意事項

- 必須加 `--policy.push_to_hub=false`，否則會報錯要求 `policy.repo_id`
- Wandb 首次使用需先 `wandb login` 取得 API key
- Camera 名稱必須跟錄製時一致（`overhead`、`wrist`）
- 如果記憶體不夠，可調 `--dataset.batch_size` 和 `--policy.n_obs_steps`
- 另有獨立 Python 訓練腳本 `5_train_diffusion_custom.py` + `models/diffusion_custom.py`，可自訂架構與 loss

---

## 步驟三：推論 (Eval)

兩種方式：

**方式 1：簡易 eval（原本的 lerobot-record）**

```bash
bash scripts/5_eval_diffusion.sh
```

**方式 2：帶標記的 eval（推薦）**

```bash
python scripts/5_eval_diffusion_custom.py
```

每個 episode 結束後按 `s`（成功）/ `f`（失敗）/ `d`（丟棄），自動統計 success rate，結果存 CSV + 上傳 wandb。不修改 LeRobot 原始碼（standalone wrapper）。

- Config 在腳本最上方的常數區塊修改（policy path、episode 數、camera 等）
- CSV log 存在 `outputs/eval/eval_<timestamp>.csv`
- wandb 上傳到同 project（`piper-pick-cube`），job_type=`eval`

**Eval dataset 回放：**

```bash
./scripts/5_replay_eval.sh          # 列出有哪些 episodes
./scripts/5_replay_eval.sh 3        # 看 episode 3
./scripts/5_replay_eval.sh all      # 全部看
```

### 完成項目

- [x] 載入 trained policy 在真機上跑
- [x] 錄製 eval episodes（機器人會動，pipeline 打通）
- [x] 帶標記的 eval 流程（success/fail annotation + wandb 上傳）
- [ ] 根據結果決定是否需要更多資料或調參

---

## 已知限制

- **資料量不足**：目前只有 10 episodes，Diffusion Policy 通常需要 50+ episodes 才能穩定
- **Inference 速度**：DDPM 10 steps inference 約 500ms，導致 eval loop 週期性掉到 ~2 Hz，影響控制品質
- **改善方向**：增加 demos、改用 DDIM scheduler 減少 inference steps、或換 Pi0-FAST

---

## 備註

- Phase 5 和 Phase 6 共用同一份資料集 `charliechan/piper-pick-cube-dual`
- Diffusion Policy 訓練快、模型小，適合快速迭代
- 先用最簡單的 pick up cube 驗證整個 pipeline，再挑戰更複雜的任務
