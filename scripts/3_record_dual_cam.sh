#!/bin/bash
# Phase 3: Dual camera test — record with ROBOTIS leader arm + Rerun GUI
# overhead = /dev/cam_c270 (旁邊固定視角)
# wrist    = /dev/cam_arc (eye-in-hand)
# Must run in desktop terminal (not SSH)

lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.cameras="{ overhead: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --display_data=true \
    --dataset.repo_id=charliechan/piper-pick-cube-dual \
    --dataset.root=/home/charliechan/dataset/charliechan/piper-pick-cube-dual \
    --dataset.num_episodes=3 \
    --resume=true \
    --dataset.single_task="pick up cube" \
    --dataset.episode_time_s=15 \
    --dataset.reset_time_s=5 \
    --dataset.fps=20 \
    --dataset.push_to_hub=false
