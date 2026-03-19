#!/bin/bash
# Phase 7: Fine-tune SmolVLA on dual-camera pick-up-cube dataset
# SmolVLA = SmolVLM2-500M VLM + action expert (~500M params total)
# Much lighter than Pi0-FAST (3B), should train faster and infer faster
#
# Requires: num2words, accelerate, safetensors, transformers
#
# Camera mapping: our overhead → camera1, wrist → camera2, camera3 → empty
# smolvla_base was pretrained with 3 cameras, we only have 2, so pad 1 empty

CUDA_VISIBLE_DEVICES=0 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
lerobot-train \
    --dataset.repo_id=charliechan/piper-pick-cube-dual \
    --dataset.root=/home/charliechan/dataset/charliechan/piper-pick-cube-dual \
    --policy.path=lerobot/smolvla_base \
    --rename_map='{"observation.images.overhead": "observation.images.camera1", "observation.images.wrist": "observation.images.camera2"}' \
    --policy.empty_cameras=1 \
    --batch_size=8 \
    --steps=10000 \
    --save_freq=1000 \
    --output_dir=/tmp2/charlie/training-outputs/smolvla_dual_cam \
    --job_name=smolvla_dual_cam_v1 \
    --policy.device=cuda \
    --policy.push_to_hub=false \
    --wandb.enable=true \
    --wandb.project=piper-pick-cube \
    --wandb.disable_artifact=true
