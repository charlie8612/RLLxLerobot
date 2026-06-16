#!/bin/bash
# Phase 2: Record dataset using ROBOTIS leader arm teleop (no camera)

lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --dataset.repo_id=charliechan/piper-demo-balancebar \
    --dataset.num_episodes=1 \
    --dataset.single_task="pinball" \
    --dataset.episode_time_s=60 \
    --dataset.reset_time_s=5 \
    --dataset.fps=20 \
    --dataset.video=false \
    --dataset.push_to_hub=false
