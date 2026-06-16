#!/bin/bash
# Phase 8: Record dataset using ROBOTIS leader arm teleop (no camera) — set 1

lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --dataset.repo_id=charliechan/piper-leader-high-1 \
    --dataset.num_episodes=5 \
    --dataset.single_task="pinball" \
    --dataset.episode_time_s=15 \
    --dataset.reset_time_s=5 \
    --dataset.fps=20 \
    --dataset.video=false \
    --dataset.push_to_hub=false
