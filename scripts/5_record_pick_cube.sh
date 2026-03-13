#!/bin/bash
# Phase 5 Stage A: Record pick-up-cube demonstrations
# Dual camera (overhead + wrist), 320x240, leader arm + Rerun GUI
# Must run in desktop terminal (not SSH)
#
# Camera device paths (see doc/04-phase3-dual-camera.md):
#   overhead: /dev/cam_c270
#   wrist:    /dev/cam_arc

lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.cameras="{ overhead: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --display_data=true \
    --dataset.repo_id=charliechan/piper-pick-cube-dual \
    --dataset.root=/home/charliechan/dataset/charliechan/piper-pick-cube-dual \
    --dataset.num_episodes=10 \
    --dataset.single_task="pick up cube" \
    --dataset.episode_time_s=20 \
    --dataset.reset_time_s=5 \
    --dataset.fps=20 \
    --dataset.push_to_hub=false
