#!/bin/bash
# Teleoperate: ROBOTIS leader arm → Piper follower

lerobot-teleoperate \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --robot.gripper_effort=5000 \
    # --robot.use_mit_mode=true \
    # --robot.joint_kp=30.0 \
    # --robot.joint_kd=0.8 \
    --fps=200
