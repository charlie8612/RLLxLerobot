#!/bin/bash
# Phase 6: Fine-tune Pi0-FAST on dual-camera pick-up-cube dataset
# Requires: transformers (fix/lerobot_openpi branch), scipy, sentencepiece, bitsandbytes
# Requires: HuggingFace login + PaliGemma license agreed
# See doc/07-phase6-pi0fast.md for setup details

CUDA_VISIBLE_DEVICES=0 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
lerobot-train \
    --dataset.repo_id=charliechan/piper-pick-cube-dual \
    --dataset.root=/home/charliechan/dataset/charliechan/piper-pick-cube-dual \
    --policy.type=pi0_fast \
    --policy.pretrained_path=lerobot/pi0fast-base \
    --policy.dtype=bfloat16 \
    --policy.gradient_checkpointing=true \
    --policy.chunk_size=10 \
    --policy.n_action_steps=10 \
    --policy.max_action_tokens=256 \
    --batch_size=2 \
    --steps=5000 \
    --save_freq=500 \
    --output_dir=/tmp2/charlie/training-outputs/pi0fast_dual_cam \
    --job_name=pi0fast_dual_cam_v1 \
    --policy.device=cuda \
    --policy.push_to_hub=false \
    --wandb.enable=true \
    --wandb.project=piper-pick-cube \
    --wandb.disable_artifact=true
