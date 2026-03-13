#!/usr/bin/env python3
"""Read current Piper arm joint positions and gripper state."""

import argparse
from lerobot_robot_piper.piper_follower import PiperFollower
from lerobot_robot_piper.config_piper_follower import PiperFollowerConfig

KEYS = [
    "joint_1.pos", "joint_2.pos", "joint_3.pos",
    "joint_4.pos", "joint_5.pos", "joint_6.pos",
    "gripper.pos",
]


def main():
    parser = argparse.ArgumentParser(description="Read Piper arm state")
    parser.add_argument("--can-port", default="piper_left")
    args = parser.parse_args()

    config = PiperFollowerConfig()
    config.can_port = args.can_port
    robot = PiperFollower(config)
    robot.connect()

    obs = robot.get_observation()
    for k in KEYS:
        print(f"  {k}: {obs[k]:.2f}")

    robot.disconnect()


if __name__ == "__main__":
    main()
