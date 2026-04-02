#!/bin/bash
# Phase 7: Record demonstrations in radian for SmolVLA fine-tune
# unit=rad so dataset matches ISdept/smolvla-piper's radian space
# Camera names match SmolVLA convention: camera1=front, camera2=gripper
#
# 錄完後直接用 7_train_smolvla.sh fine-tune

lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.unit=rad \
    --robot.speed_rate=30 \
    --robot.cameras="{ camera1: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30}, camera2: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --display_data=false \
    --dataset.repo_id=charliechan/piper-pick-cube-smolvla \
    --dataset.num_episodes=50 \
    --dataset.single_task="pick up cube" \
    --dataset.episode_time_s=20 \
    --dataset.reset_time_s=5 \
    --dataset.fps=20 \
    --dataset.push_to_hub=false
