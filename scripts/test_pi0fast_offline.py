#!/usr/bin/env python3
"""Offline test: load fine-tuned Pi0-FAST and run inference on real dataset frames."""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from lerobot.policies.pi0_fast.modeling_pi0_fast import PI0FastPolicy
from lerobot.datasets.lerobot_dataset import LeRobotDataset
import time

print("Loading dataset...")
ds = LeRobotDataset("charliechan/piper-pick-cube-dual",
                     root="/home/charliechan/dataset/charliechan/piper-pick-cube-dual")

print("Loading fine-tuned model...")
policy = PI0FastPolicy.from_pretrained(
    "/tmp2/charlie/training-outputs/pi0fast_dual_cam/checkpoints/last/pretrained_model"
)
policy.eval()
print(f"VRAM: {torch.cuda.memory_allocated(0)/1024**3:.2f} GB")

# Test on first 5 frames from episode 0
print("\n--- Inference on real dataset frames ---")
print(f"{'frame':>5} | {'inf_time':>8} | {'predicted action':>60} | {'ground truth action':>60}")
print("-" * 140)

for i in range(0, 50, 10):
    sample = ds[i]
    batch = {k: v.unsqueeze(0).to("cuda") if isinstance(v, torch.Tensor) else v
             for k, v in sample.items()}
    # Tokenize language instruction
    tok_out = policy._paligemma_tokenizer(
        "pick up cube", return_tensors="pt", padding="max_length",
        max_length=policy.config.tokenizer_max_length, truncation=True
    )
    batch["observation.language.tokens"] = tok_out["input_ids"].to("cuda")
    batch["observation.language.attention_mask"] = tok_out["attention_mask"].to("cuda").bool()

    with torch.no_grad():
        t0 = time.time()
        try:
            action = policy.select_action(batch)
            dt = time.time() - t0
            pred = action.cpu().tolist()
            gt = sample["action"].tolist()
            print(f"{i:5d} | {dt:7.2f}s | {str([f'{x:.1f}' for x in pred]):>60} | {str([f'{x:.1f}' for x in gt]):>60}")
        except Exception as e:
            dt = time.time() - t0
            print(f"{i:5d} | {dt:7.2f}s | ERROR: {str(e)[:80]}")

    # Clear action queue for next independent prediction
    policy._action_queue.clear()

print(f"\nVRAM peak: {torch.cuda.max_memory_allocated(0)/1024**3:.2f} GB")
