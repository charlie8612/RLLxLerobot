#!/bin/bash
# Phase 3: Dual camera teleoperate test (no recording)
# overhead = /dev/cam_c270b (旁邊固定視角)
# wrist    = /dev/cam_wrist (eye-in-hand)
# Must run in desktop terminal (not SSH)

lerobot-teleoperate \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.cameras="{ overhead: {type: opencv, index_or_path: /dev/cam_c270b, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --display_data=true \
    --fps=200
