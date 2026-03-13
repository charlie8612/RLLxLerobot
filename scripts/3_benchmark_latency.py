#!/usr/bin/env python3
"""Benchmark teleop loop latency — measure where time is spent."""
import time
import sys

# --- Config -----------------------------------------------------------
CAN_PORT = "piper_left"
TELEOP_PORT = "/dev/robotis_left"
CAMERAS = {
    "overhead": {"type": "opencv", "index_or_path": "/dev/cam_c270",
                 "width": 640, "height": 480, "fps": 30, "fourcc": "MJPG"},
    "wrist":    {"type": "opencv", "index_or_path": "/dev/cam_arc",
                 "width": 640, "height": 480, "fps": 30, "fourcc": "MJPG"},
}
N_ITERS = 100
# ----------------------------------------------------------------------

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot_robot_piper.config_piper_follower import PiperFollowerConfig
from lerobot_robot_piper.piper_follower import PiperFollower
from lerobot_teleoperator_robotis.config_robotis_leader import RobotisLeaderConfig
from lerobot_teleoperator_robotis.robotis_leader import RobotisLeader


def build_cam_configs(cam_dict):
    configs = {}
    for name, c in cam_dict.items():
        configs[name] = OpenCVCameraConfig(
            index_or_path=c["index_or_path"],
            width=c["width"], height=c["height"], fps=c["fps"],
            fourcc=c.get("fourcc"),
        )
    return configs


def benchmark(label, cam_names):
    """Run N_ITERS teleop iterations and print per-step timing."""
    selected = {k: v for k, v in CAMERAS.items() if k in cam_names}
    cam_configs = build_cam_configs(selected)

    robot_cfg = PiperFollowerConfig(can_port=CAN_PORT, cameras=cam_configs)
    robot = PiperFollower(robot_cfg)

    teleop_cfg = RobotisLeaderConfig(port=TELEOP_PORT)
    teleop = RobotisLeader(teleop_cfg)

    robot.connect()
    teleop.connect()

    # Warmup
    for _ in range(10):
        robot.get_observation()
        teleop.get_action()

    times_obs = []
    times_cam = {name: [] for name in cam_names}
    times_action = []
    times_send = []
    times_total = []

    for i in range(N_ITERS):
        t0 = time.perf_counter()

        # --- get_observation (joints only) ---
        joint_msgs = robot.piper.GetArmJointMsgs()
        gripper_msgs = robot.piper.GetArmGripperMsgs()
        t1 = time.perf_counter()

        # --- camera reads ---
        for name in cam_names:
            tc0 = time.perf_counter()
            robot.cameras[name].read_latest()
            tc1 = time.perf_counter()
            times_cam[name].append((tc1 - tc0) * 1000)
        t2 = time.perf_counter()

        # --- teleop get_action ---
        action = teleop.get_action()
        t3 = time.perf_counter()

        # --- send_action ---
        robot.send_action(action)
        t4 = time.perf_counter()

        times_obs.append((t1 - t0) * 1000)
        times_action.append((t3 - t2) * 1000)
        times_send.append((t4 - t3) * 1000)
        times_total.append((t4 - t0) * 1000)

    teleop.disconnect()
    robot.disconnect()

    # --- Report ---
    def stats(arr):
        arr.sort()
        avg = sum(arr) / len(arr)
        p50 = arr[len(arr) // 2]
        p95 = arr[int(len(arr) * 0.95)]
        return f"avg={avg:.2f}  p50={p50:.2f}  p95={p95:.2f} ms"

    print(f"\n{'='*60}")
    print(f"  {label}  ({N_ITERS} iterations)")
    print(f"{'='*60}")
    print(f"  Joint read:     {stats(times_obs)}")
    for name in cam_names:
        print(f"  Camera [{name:>8s}]: {stats(times_cam[name])}")
    print(f"  Teleop action:  {stats(times_action)}")
    print(f"  Send action:    {stats(times_send)}")
    print(f"  TOTAL:          {stats(times_total)}")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("  Teleop Latency Benchmark")
    print("=" * 60)

    print("\n[1/3] No camera...")
    benchmark("NO CAMERA", [])

    print("\n[2/3] Single camera (wrist)...")
    benchmark("SINGLE CAM (wrist)", ["wrist"])

    print("\n[3/3] Dual camera...")
    benchmark("DUAL CAM (overhead + wrist)", ["overhead", "wrist"])
