#!/bin/bash
# Phase 7: Eval SmolVLA on real Piper arm
# Using pretrained smolvla_base directly (no fine-tune)
#
# SmolVLA camera convention (from paper Section 3.2):
#   camera1 = top (overhead)  → cam_c270
#   camera2 = wrist           → cam_arc
#   camera3 = side            → empty (SO100 real-world only uses top + wrist)

CUDA_VISIBLE_DEVICES=0 \
lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.max_relative_target=2.0 \
    --robot.speed_rate=30 \
    --robot.cameras="{ camera1: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30}, camera2: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --policy.path=lerobot/smolvla_base \
    --policy.empty_cameras=1 \
    --dataset.repo_id=charliechan/eval_smolvla_piper \
    --dataset.num_episodes=10 \
    --dataset.single_task="pick up cube" \
    --dataset.fps=20 \
    --dataset.episode_time_s=300 \
    --display_data=true \
    --dataset.push_to_hub=false
