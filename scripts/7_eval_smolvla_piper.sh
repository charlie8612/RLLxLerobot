#!/bin/bash
# Phase 7: Eval ISdept/smolvla-piper on real Piper arm
# This model was fine-tuned on 315 episodes of Piper pick-place data
# 7-DOF, 3 cameras (400x640) — we use 2 real + 1 empty
#
# Camera mapping (matching SmolVLA convention):
#   camera1 = top (overhead)  → empty (缺 top camera)
#   camera2 = wrist           → cam_arc
#   camera3 = side            → cam_c270
# TODO: 補一顆 top camera（鵝頸夾從正上方往下看）對應 camera1

CUDA_VISIBLE_DEVICES=0 \
lerobot-record \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.unit=rad \
    --robot.max_relative_target=0.035 \
    --robot.speed_rate=30 \
    --robot.go_home_on_connect=true \
    --robot.log_inference=true \
    --robot.cameras="{ camera3: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30}, camera2: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --policy.path=ISdept/smolvla-piper \
    --policy.device=cuda \
    --policy.empty_cameras=1 \
    --dataset.repo_id=charliechan/eval_smolvla_piper_ft \
    --dataset.num_episodes=10 \
    --dataset.single_task="pick up cube" \
    --dataset.fps=20 \
    --dataset.episode_time_s=300 \
    --display_data=false \
    --dataset.push_to_hub=false
