#!/bin/bash
# Teleoperate: Dual ROBOTIS leader arms → Dual Piper followers

lerobot-teleoperate \
    --robot.type=bi_piper_follower \
    --robot.left_arm_config.can_port=piper_left \
    --robot.right_arm_config.can_port=piper_right \
    --teleop.type=bi_robotis_leader \
    --teleop.left_arm_config.port=/dev/robotis_left \
    --teleop.right_arm_config.port=/dev/robotis_right \
    --fps=200
