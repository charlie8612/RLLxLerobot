#!/bin/bash
# Phase 3: Dual camera teleoperate — MJPEG (壓縮，用來對比延遲)
# overhead = /dev/cam_c270 (旁邊固定視角)
# wrist    = /dev/cam_arc (eye-in-hand)

lerobot-teleoperate \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.cameras="{ overhead: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30, fourcc: MJPG}, wrist: {type: opencv, index_or_path: /dev/cam_arc, width: 640, height: 480, fps: 30, fourcc: MJPG} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --display_data=false \
    --fps=200
