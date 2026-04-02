#!/bin/bash
# Phase 7: Fine-tune ISdept/smolvla-piper on our radian dataset
# Dataset recorded with unit=rad + SmolVLA camera convention (camera1/camera2)
# ISdept model uses 3 cameras, we have 2, pad 1 empty

CUDA_VISIBLE_DEVICES=0 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
lerobot-train \
    --dataset.repo_id=charliechan/piper-pick-cube-smolvla \
    --policy.path=ISdept/smolvla-piper \
    --policy.empty_cameras=1 \
    --batch_size=8 \
    --steps=10000 \
    --save_freq=1000 \
    --output_dir=/tmp2/charlie/training-outputs/smolvla_piper_ft \
    --job_name=smolvla_piper_ft_v1 \
    --policy.device=cuda \
    --policy.push_to_hub=false \
    --wandb.enable=true \
    --wandb.project=piper-pick-cube \
    --wandb.disable_artifact=true
