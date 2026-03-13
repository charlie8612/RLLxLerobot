#!/usr/bin/env python3
"""Test Pi0-FAST inference speed with INT8 quantization vs bfloat16."""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import time
import torch
from lerobot.policies.pi0_fast.modeling_pi0_fast import PI0FastPolicy
from lerobot.datasets.lerobot_dataset import LeRobotDataset

print("Loading dataset...")
ds = LeRobotDataset("charliechan/piper-pick-cube-dual",
                     root="/home/charliechan/dataset/charliechan/piper-pick-cube-dual")

print("Loading fine-tuned model (bfloat16)...")
policy = PI0FastPolicy.from_pretrained(
    "/tmp2/charlie/training-outputs/pi0fast_dual_cam/checkpoints/last/pretrained_model"
)
policy.eval()

# Prepare a real batch
sample = ds[50]
batch = {k: v.unsqueeze(0).to("cuda") if isinstance(v, torch.Tensor) else v
         for k, v in sample.items()}
tok_out = policy._paligemma_tokenizer(
    "pick up cube", return_tensors="pt", padding="max_length",
    max_length=policy.config.tokenizer_max_length, truncation=True
)
batch["observation.language.tokens"] = tok_out["input_ids"].to("cuda")
batch["observation.language.attention_mask"] = tok_out["attention_mask"].to("cuda").bool()

# Benchmark bfloat16
print("\n--- bfloat16 baseline ---")
vram_bf16 = torch.cuda.memory_allocated(0) / 1024**3
print(f"VRAM: {vram_bf16:.2f} GB")

times = []
for i in range(3):
    policy._action_queue.clear()
    with torch.no_grad():
        t0 = time.time()
        try:
            action = policy.select_action(batch)
            dt = time.time() - t0
            times.append(dt)
            print(f"  Run {i}: {dt:.2f}s, action={[f'{x:.1f}' for x in action.cpu().tolist()]}")
        except Exception as e:
            dt = time.time() - t0
            times.append(dt)
            print(f"  Run {i}: {dt:.2f}s, ERROR: {str(e)[:60]}")

print(f"  Avg: {sum(times)/len(times):.2f}s")

# Now quantize to INT8
print("\n--- Quantizing to INT8 ---")
import bitsandbytes as bnb

def quantize_model_int8(model):
    """Replace Linear layers with INT8 Linear."""
    for name, module in model.named_children():
        if isinstance(module, torch.nn.Linear):
            has_bias = module.bias is not None
            # Convert weights to float16 for bitsandbytes compatibility
            weight_f16 = module.weight.data.to(torch.float16)
            int8_layer = bnb.nn.Linear8bitLt(
                module.in_features, module.out_features,
                bias=has_bias, has_fp16_weights=False
            )
            int8_layer.weight = bnb.nn.Int8Params(
                weight_f16, requires_grad=False, has_fp16_weights=False
            )
            if has_bias:
                int8_layer.bias = torch.nn.Parameter(module.bias.data.to(torch.float16))
            setattr(model, name, int8_layer)
        else:
            quantize_model_int8(module)

# Cast entire model to float16 first for compatibility
policy.model.to(torch.float16)
quantize_model_int8(policy.model)
policy.model.to("cuda")
torch.cuda.empty_cache()

vram_int8 = torch.cuda.memory_allocated(0) / 1024**3
print(f"VRAM: {vram_int8:.2f} GB (saved {vram_bf16 - vram_int8:.2f} GB)")

times_q = []
for i in range(3):
    policy._action_queue.clear()
    with torch.no_grad():
        t0 = time.time()
        try:
            action = policy.select_action(batch)
            dt = time.time() - t0
            times_q.append(dt)
            print(f"  Run {i}: {dt:.2f}s, action={[f'{x:.1f}' for x in action.cpu().tolist()]}")
        except Exception as e:
            dt = time.time() - t0
            times_q.append(dt)
            print(f"  Run {i}: {dt:.2f}s, ERROR: {str(e)[:60]}")

print(f"  Avg: {sum(times_q)/len(times_q):.2f}s")
print(f"\nSpeedup: {sum(times)/len(times) / (sum(times_q)/len(times_q)):.2f}x")
