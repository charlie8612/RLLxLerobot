#!/bin/bash
# Phase 5 Stage A: Eval Diffusion Policy on real Piper arm
# Must run in desktop terminal (not SSH) — needs camera + Rerun GUI

lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.cameras="{ wrist: {type: opencv, index_or_path: /dev/video0, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --policy.type=diffusion \
    --policy.pretrained_path=/tmp2/charlie/training-outputs/diffusion_dual_cam/checkpoints/last/pretrained_model \
    --dataset.repo_id=charliechan/eval_diffusion_piper \
    --dataset.num_episodes=3 \
    --dataset.single_task="pick up cube" \
    --dataset.fps=20 \
    --dataset.push_to_hub=false \
    --display_data=true
