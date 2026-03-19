# Phase 7: SmolVLA（輕量 VLA Fine-tune）

**狀態：🔧 Inference 可跑，待 fine-tune**

---

## 目標

用 SmolVLA（~450M params）取代 Pi0-FAST（~3B params），解決 inference 太慢的問題。

## 模型資訊

- **Base model**: `lerobot/smolvla_base`
- **架構**: SmolVLM2-500M VLM + Flow Matching action expert
- **參數量**: ~450M total, ~100M trainable (action expert only)
- **VRAM**: 訓練 ~8GB (bs=8), inference ~1.4GB
- **論文**: [arxiv 2506.01844](https://arxiv.org/abs/2506.01844)

### SmolVLA vs Pi0-FAST

| | Pi0-FAST (Phase 6) | SmolVLA (Phase 7) |
|--|---|---|
| 模型大小 | 3B | 450M |
| 可訓練參數 | 3B (full fine-tune) | 100M (expert only) |
| 訓練速度 | 1.3 step/s, bs=2 | 3.3 step/s, bs=8 |
| VRAM | ~22 GB | ~8 GB |
| Inference | ~30s/chunk | ~1.8s/chunk |

### Camera Convention（論文 Section 3.2）

SmolVLA pretrain 時將 community datasets 的 camera 統一 rename：

| 名稱 | 視角 | 我們的設備 |
|------|------|-----------|
| camera1 | top/front (正面/俯視) | cam_c270 |
| camera2 | wrist/gripper (手腕) | cam_arc |
| camera3 | side/right (側面) | empty 或第三顆 camera |

## 已測試的 Model

### `ISdept/smolvla-piper` (fine-tuned on Piper)

- 7-DOF, 315 episodes pick-place, 3 cameras (front/gripper/right)
- **單位**: radian（我們的 dataset 用 degree）→ 需要 `--robot.unit=rad`
- **camera rename_map**: `front→camera1, gripper→camera2, right→camera3`
- Inference 可跑，但環境/camera 差異大，效果有限

## Plugin 改動

### `config_piper_follower.py` 新增參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `unit` | `"deg"` | joint angle 單位。`"rad"` 時 plugin 自動轉換 rad↔deg |
| `go_home_on_connect` | `false` | 連線後先 smoothstep 到 home position |
| `home_position_deg` | 全零 | home position（度），可自訂 |
| `log_inference` | `false` | 每次 chunk inference 時印 log（時間 + action 值） |

### `piper_follower.py` 改動

- `get_observation()`: unit=rad 時回傳 radian
- `send_action()`: unit=rad 時自動 rad→deg 再送硬體
- `_move_to_rest()` / `_move_to_home()`: 內部統一用 degree interpolation，不受 unit 影響
- 新增 `_get_current_deg()` / `_send_action_deg()` helper

## LeRobot 原始碼修改

以下修改直接在 `lerobot/` 原始碼上，**更新 LeRobot 時需重新 apply**：

| 檔案 | 修改 | 原因 |
|------|------|------|
| `lerobot_record.py` L422 | 有 policy 時不印 FPS warning | 推論造成的 FPS 下降是正常的 (K7) |
| `lerobot_record.py` finally block | `robot.disconnect()` 移到最前面 + try/except | Ctrl+C 時確保手臂安全 disconnect (K8) |
| `lerobot_record.py` L370 | 新增 inference log（`log_inference` config 控制） | Debug 用 |

## Scripts

| 腳本 | 用途 |
|------|------|
| `scripts/7_train_smolvla.sh` | Fine-tune ISdept/smolvla-piper on 自己的 dual-camera data |
| `scripts/7_eval_smolvla_piper.sh` | Eval ISdept/smolvla-piper（Piper fine-tuned, unit=rad） |

## 待做

- [ ] 用自己的 data fine-tune smolvla_base（`bash scripts/7_train_smolvla.sh`，~50 min）
- [ ] Fine-tune 後 eval，與 Diffusion Policy / Pi0-FAST 比較
- [ ] 補第三顆 camera (top view) 提升效果
