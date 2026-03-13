#!/bin/bash
# Phase 6: Eval Pi0-FAST on real Piper arm (RTX 3080)
# Fine-tuned checkpoint, with teleop for manual reset between episodes

CUDA_VISIBLE_DEVICES=0 \
lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.max_relative_target=2.0 \
    --robot.speed_rate=30 \
    --robot.cameras="{ overhead: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --policy.type=pi0_fast \
    --policy.pretrained_path=/tmp2/charlie/training-outputs/pi0fast_dual_cam/checkpoints/last/pretrained_model \
    --policy.dtype=bfloat16 \
    --policy.compile_model=true \
    --dataset.repo_id=charliechan/eval_pi0fast_piper \
    --dataset.num_episodes=10 \
    --dataset.single_task="pick up cube" \
    --dataset.fps=20 \
    --dataset.episode_time_s=300 \
    --display_data=true \
    --dataset.push_to_hub=false
