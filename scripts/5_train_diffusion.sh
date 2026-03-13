#!/bin/bash
# Phase 5: Train Diffusion Policy on dual-camera pick-up-cube dataset

CUDA_VISIBLE_DEVICES=1 lerobot-train \
    --policy.type=diffusion \
    --dataset.repo_id=charliechan/piper-pick-cube-dual \
    --dataset.root=/home/charliechan/dataset/charliechan/piper-pick-cube-dual \
    --output_dir=/tmp2/charlie/training-outputs/diffusion_dual_cam \
    --job_name=diffusion_dual_cam_v1 \
    --policy.device=cuda \
    --policy.push_to_hub=false \
    --policy.noise_scheduler_type=DDPM \
    --policy.num_inference_steps=10 \
    --policy.resize_shape="[240, 320]" \
    --steps=20000 \
    --save_freq=1000 \
    --wandb.enable=true \
    --wandb.project=piper-pick-cube \
    --wandb.disable_artifact=true
