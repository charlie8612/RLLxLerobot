# Phase 6: Pi0-FAST（Pretrained Model Fine-tune）

## 目標

用 `lerobot/pi0fast-base` pretrained model 在 Piper 的 pick up cube 資料上 fine-tune，
驗證 foundation model 在不同機器人上的遷移能力。

**狀態：🔧 環境就緒，訓練待跑**

---

## 模型資訊

- **Pretrained checkpoint**：`lerobot/pi0fast-base`（注意是 hyphen 不是 underscore）
- **架構**：PaliGemma (SigLIP vision + Gemma 2B LLM) + FAST action tokenizer
- **參數量**：~3B
- **VRAM 需求**：bf16 full fine-tune + 8-bit Adam ~20-22 GB，inference ~6 GB
- **Action space**：內建 auto-pad 到 32 維，Piper 的 7 維直接支援

### 跨機器人相容性

Pi0 pretrained model 是在以下 8 種機器人的資料上訓練的：
- UR5e、Bimanual UR5e、Franka Emika Panda
- Bimanual Trossen、Bimanual ARX
- Mobile Trossen、Mobile Fibocom

**Piper 不在其中**，但 Pi0 架構設計上支援跨平台：
- Action 維度自動 pad 到 32 維（Piper 7 維直接支援）
- Normalization 根據 dataset 統計值重新計算
- Pretrained 的視覺理解和序列預測能力跨機器人通用
- Fine-tune 時會調整 action projection layers 適應 Piper 動力學

---

## 環境設定

### 必要套件

Pi0-FAST 的依賴比 Diffusion Policy 多很多，需要額外安裝：

```bash
conda activate piper

# 1. 安裝特殊分支的 transformers（LeRobot Pi0 必須用這個）
pip install "transformers @ git+https://github.com/huggingface/transformers.git@fix/lerobot_openpi"

# 2. 其他依賴
pip install scipy sentencepiece bitsandbytes
```

> ⚠️ **不能用 pip 的一般 transformers**。LeRobot 的 Pi0 實作依賴 `transformers.models.siglip.check` module，
> 只存在於 HuggingFace 的 `fix/lerobot_openpi` 分支。用錯版本會報 `An incorrect transformer version is used`。
> 具體要求定義在 `lerobot/pyproject.toml` 的 `[project.optional-dependencies]` `pi` 項。

### HuggingFace 認證

需要登入 HuggingFace 並同意 PaliGemma 的 gated license：

```bash
# 1. 登入（需要 HuggingFace token，至少 Read 權限）
python -c "from huggingface_hub import login; login()"
# "Add token as git credential" 選 No

# 2. 去 PaliGemma model page 同意 license
#    https://huggingface.co/google/paligemma-3b-pt-224
#    點 "Acknowledge license" 或 "Access repository"
```

> `lerobot/pi0fast-base` 本身不是 gated repo，不需要額外同意。
> 但它內部用的 tokenizer 來自 `google/paligemma-3b-pt-224`（gated），所以必須同意 Google 的條款。

### 8-bit Optimizer（解決 OOM）

RTX 3090 (24GB) 跑 3B model 的 full fine-tune 會 OOM。
已修改 LeRobot 的 `AdamWConfig` 支援 8-bit Adam（bitsandbytes），
並在 `PI0FastConfig.get_optimizer_preset()` 中預設啟用。

修改的檔案：
- `lerobot/src/lerobot/optim/optimizers.py` — `AdamWConfig` 加 `use_8bit` 參數
- `lerobot/src/lerobot/policies/pi0_fast/configuration_pi0_fast.py` — `get_optimizer_preset()` 設 `use_8bit=True`

---

## 訓練

```bash
bash scripts/6_train_pi0fast.sh
```

### 關鍵參數說明

| 參數 | 值 | 說明 |
|------|-----|------|
| `pretrained_path` | `lerobot/pi0fast-base` | 注意是 **hyphen** 不是 underscore |
| `batch_size` | 2 | RTX 3090 24GB 搭配 8-bit Adam 的上限 |
| `steps` | 5000 | 小 dataset (11 eps) 不需要太多 steps |
| `save_freq` | 1000 | 每 1000 步存 checkpoint |
| `gradient_checkpointing` | true | 省 activation memory |
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` | 減少 CUDA memory fragmentation |

### 訓練速度

- RTX 3090 上約 **1.3 step/s**
- 5000 steps ≈ **~1 小時**
- Wandb project: `piper-pick-cube`

### Checklist

- [x] 環境設定完成（transformers 特殊分支、scipy、sentencepiece、bitsandbytes）
- [x] HuggingFace 認證（登入 + PaliGemma license 同意）
- [x] 8-bit optimizer patch（解決 24GB OOM）
- [x] 確認訓練可以啟動並穩定跑
- [ ] 完成訓練，檢查 loss 收斂
- [ ] 用 wandb 監控

---

## 推論 (Eval)

```bash
bash scripts/6_eval_pi0fast.sh
```

- [ ] 載入 fine-tuned Pi0-FAST 在真機上跑
- [ ] 與 Phase 5 的 Diffusion Policy 比較成功率

---

## 踩坑記錄

### 1. Pretrained repo 名稱錯誤

文件原本寫 `lerobot/pi0fast_base`（underscore），實際 HuggingFace 上是 `lerobot/pi0fast-base`（hyphen）。
用錯名稱會報 `Repository Not Found`。

### 2. transformers 版本不對

LeRobot 的 Pi0 實作依賴 HuggingFace transformers 的特殊分支 `fix/lerobot_openpi`，
裡面有 `transformers.models.siglip.check` module。

- pip 的一般 `transformers` 5.x 或 4.57.x 都沒有這個 module
- 必須用：`pip install "transformers @ git+https://github.com/huggingface/transformers.git@fix/lerobot_openpi"`
- 裝錯會報 `An incorrect transformer version is used`

### 3. 隱式依賴未列在 extras

`lerobot[pi0]` extra 在 v0.4.5 不存在（pyproject.toml 裡用的 key 是 `pi`，不是 `pi0`）。
需要手動安裝：`transformers`（特殊分支）、`scipy`、`sentencepiece`、`bitsandbytes`。

### 4. PaliGemma 是 gated repo

`google/paligemma-3b-pt-224` 需要去 model page 同意 license。
沒同意的話，tokenizer 載入會報 `403 Forbidden`，但錯誤訊息被包成
`Couldn't instantiate the backend tokenizer`，容易誤判為套件版本問題。

### 5. CUDA OOM（RTX 3090 24GB）

3B model 的 bf16 full fine-tune + AdamW optimizer states 需要 ~24-26 GB：
- Model weights (bf16): ~6 GB
- Optimizer states (fp32, 2x): ~12 GB
- Activations + gradients: ~6-8 GB

即使 batch_size=1 也會 OOM。解法：
- 用 8-bit Adam（bitsandbytes）省 ~75% optimizer memory
- 搭配 `gradient_checkpointing=true` 省 activation memory
- 設 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 減少 fragmentation
- batch_size=2 可穩定跑，實測用 ~22 GB

---

## 參考

- Pi0 論文：[Physical Intelligence](https://www.physicalintelligence.company/blog/pi0)
- FAST tokenizer：`physical-intelligence/fast`（HuggingFace）
- LeRobot Pi0 文件：`lerobot/docs/source/pi0.mdx`
- OpenPI 原始實作：https://github.com/Physical-Intelligence/openpi
