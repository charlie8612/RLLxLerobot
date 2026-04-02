#!/usr/bin/env python3
"""Read current Piper arm pose (no motor enable, CAN read only).

Usage:
    python tools/read_piper_pose.py               # print joint values
    python tools/read_piper_pose.py --rest-dict    # print as REST_STATE_DEG dict
    python tools/read_piper_pose.py --waypoint     # print as waypoint JSON entry
    python tools/read_piper_pose.py --can-port piper_right
"""

import argparse
import json
import time

from piper_sdk import C_PiperInterface_V2

JOINT_NAMES = ["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6"]


def read_pose(can_port: str = "piper_left") -> dict[str, float]:
    piper = C_PiperInterface_V2(can_port)
    piper.ConnectPort()
    time.sleep(0.5)

    js = piper.GetArmJointMsgs().joint_state
    gs = piper.GetArmGripperMsgs().gripper_state

    pose = {}
    for i, name in enumerate(JOINT_NAMES, 1):
        pose[f"{name}.pos"] = getattr(js, f"joint_{i}") / 1000.0
    pose["gripper.pos"] = abs(gs.grippers_angle) / 1000.0
    return pose


def main():
    parser = argparse.ArgumentParser(description="Read Piper arm pose (CAN only, no enable)")
    parser.add_argument("--can-port", default="piper_left")
    parser.add_argument("--rest-dict", action="store_true", help="Print as REST_STATE_DEG dict")
    parser.add_argument("--waypoint", action="store_true", help="Print as waypoint JSON entry")
    args = parser.parse_args()

    pose = read_pose(args.can_port)

    if args.rest_dict:
        print("REST_STATE_DEG = {")
        for k, v in pose.items():
            print(f'    "{k}": {v:.2f},')
        print("}")
    elif args.waypoint:
        entry = {"state": {k: round(v, 3) for k, v in pose.items()}, "pause": 0.0}
        print(json.dumps(entry, indent=2))
    else:
        for k, v in pose.items():
            print(f"  {k}: {v:.2f}")


if __name__ == "__main__":
    main()
