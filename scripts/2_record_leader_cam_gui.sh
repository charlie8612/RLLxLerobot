#!/bin/bash
# Phase 2: Record with ROBOTIS leader arm + wrist camera + Rerun GUI (single cam)
# Requires: pip install rerun-sdk
# Must run in desktop terminal (not SSH)

lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.cameras="{ wrist: {type: opencv, index_or_path: /dev/video6, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --display_data=true \
    --dataset.repo_id=charliechan/piper-leader-cam-test \
    --dataset.num_episodes=3 \
    --dataset.single_task="pick up cube" \
    --dataset.episode_time_s=15 \
    --dataset.reset_time_s=5 \
    --dataset.fps=20 \
    --dataset.push_to_hub=false
