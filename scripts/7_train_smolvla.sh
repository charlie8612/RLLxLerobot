#!/bin/bash
# Phase 7: Fine-tune ISdept/smolvla-piper on our dual-camera pick-up-cube dataset
# ISdept model is already Piper 7-DOF fine-tuned (radian, 3 cameras)
# Our dataset is degree-based — training will re-learn normalization stats
#
# Camera mapping: our overhead → camera1 (front), wrist → camera2 (gripper)
# ISdept used 3 cameras (front/gripper/right), we have 2, pad 1 empty

CUDA_VISIBLE_DEVICES=0 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
lerobot-train \
    --dataset.repo_id=charliechan/piper-pick-cube-dual \
    --dataset.root=/home/charliechan/dataset/charliechan/piper-pick-cube-dual \
    --policy.path=ISdept/smolvla-piper \
    --rename_map='{"observation.images.overhead": "observation.images.camera1", "observation.images.wrist": "observation.images.camera2"}' \
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
