#!/bin/bash
# Teleoperate: ROBOTIS leader arm → Piper follower

lerobot-teleoperate \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --robot.cameras="{ overhead: {type: opencv, index_or_path: /dev/cam_c270, width: 640, height: 480, fps: 30} }" \
    --teleop.type=robotis_leader \
    --teleop.port=/dev/robotis_left \
    --robot.gripper_effort=5000 \
    --robot.use_mit_mode=true \
    --robot.joint_kp=30.0 \
    --robot.joint_kd=0.8 \
    --fps=200 \
    --display_data=true 
