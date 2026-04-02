#!/bin/bash
# Teleoperate: ROBOTIS leader arm → Piper follower

lerobot-teleoperate \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --robot.gripper_effort=300 \
    --fps=200
