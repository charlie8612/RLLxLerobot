#!/usr/bin/env python3
"""Benchmark dual-arm teleop loop timing.

Bypasses LeRobot to measure raw hardware latency.
Run with: conda run -n piper python tools/bench_dual_teleop.py
Press Ctrl+C to stop.
"""
import time
import statistics

from lerobot_robot_piper import PiperFollowerConfig, PiperFollower
from lerobot_teleoperator_robotis import RobotisLeaderConfig, RobotisLeader


def main():
    # --- Single arm baseline ---
    print("=== Single arm (left) baseline ===")
    leader_l = RobotisLeader(RobotisLeaderConfig(port="/dev/robotis_left"))
    follower_l = PiperFollower(PiperFollowerConfig(can_port="piper_left"))
    leader_l.connect()
    follower_l.connect()

    times = {"read_leader": [], "get_obs": [], "send_action": [], "total": []}
    for i in range(200):
        t0 = time.perf_counter()

        obs = follower_l.get_observation()
        t1 = time.perf_counter()

        action = leader_l.get_action()
        t2 = time.perf_counter()

        follower_l.send_action(action)
        t3 = time.perf_counter()

        times["get_obs"].append((t1 - t0) * 1000)
        times["read_leader"].append((t2 - t1) * 1000)
        times["send_action"].append((t3 - t2) * 1000)
        times["total"].append((t3 - t0) * 1000)

    for k, v in times.items():
        print(f"  {k:15s}: avg={statistics.mean(v):.2f}ms  p50={statistics.median(v):.2f}ms  p99={sorted(v)[int(len(v)*0.99)]:.2f}ms  max={max(v):.2f}ms")

    leader_l.disconnect()
    follower_l.disconnect()
    time.sleep(0.5)

    # --- Dual arm sequential ---
    print("\n=== Dual arm SEQUENTIAL ===")
    leader_l = RobotisLeader(RobotisLeaderConfig(port="/dev/robotis_left"))
    leader_r = RobotisLeader(RobotisLeaderConfig(port="/dev/robotis_right"))
    follower_l = PiperFollower(PiperFollowerConfig(can_port="piper_left"))
    follower_r = PiperFollower(PiperFollowerConfig(can_port="piper_right"))
    leader_l.connect()
    leader_r.connect()
    follower_l.connect()
    follower_r.connect()

    times = {"get_obs": [], "read_leader": [], "send_action": [], "total": []}
    for i in range(200):
        t0 = time.perf_counter()

        obs_l = follower_l.get_observation()
        obs_r = follower_r.get_observation()
        t1 = time.perf_counter()

        action_l = leader_l.get_action()
        action_r = leader_r.get_action()
        t2 = time.perf_counter()

        follower_l.send_action(action_l)
        follower_r.send_action(action_r)
        t3 = time.perf_counter()

        times["get_obs"].append((t1 - t0) * 1000)
        times["read_leader"].append((t2 - t1) * 1000)
        times["send_action"].append((t3 - t2) * 1000)
        times["total"].append((t3 - t0) * 1000)

    for k, v in times.items():
        print(f"  {k:15s}: avg={statistics.mean(v):.2f}ms  p50={statistics.median(v):.2f}ms  p99={sorted(v)[int(len(v)*0.99)]:.2f}ms  max={max(v):.2f}ms")

    # --- Dual arm parallel (leader reads only) ---
    print("\n=== Dual arm PARALLEL leader reads ===")
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=2)

    times = {"get_obs": [], "read_leader": [], "send_action": [], "total": []}
    for i in range(200):
        t0 = time.perf_counter()

        obs_l = follower_l.get_observation()
        obs_r = follower_r.get_observation()
        t1 = time.perf_counter()

        fl = executor.submit(leader_l.get_action)
        fr = executor.submit(leader_r.get_action)
        action_l = fl.result()
        action_r = fr.result()
        t2 = time.perf_counter()

        follower_l.send_action(action_l)
        follower_r.send_action(action_r)
        t3 = time.perf_counter()

        times["get_obs"].append((t1 - t0) * 1000)
        times["read_leader"].append((t2 - t1) * 1000)
        times["send_action"].append((t3 - t2) * 1000)
        times["total"].append((t3 - t0) * 1000)

    for k, v in times.items():
        print(f"  {k:15s}: avg={statistics.mean(v):.2f}ms  p50={statistics.median(v):.2f}ms  p99={sorted(v)[int(len(v)*0.99)]:.2f}ms  max={max(v):.2f}ms")

    # --- Via BiPiper (what lerobot-teleoperate actually uses) ---
    print("\n=== Via BiPiperFollower + BiRobotisLeader (LeRobot plugin) ===")
    leader_l.disconnect()
    leader_r.disconnect()
    follower_l.disconnect()
    follower_r.disconnect()
    executor.shutdown()
    time.sleep(0.5)

    from lerobot_robot_piper import BiPiperFollowerConfig, BiPiperFollower
    from lerobot_teleoperator_robotis import BiRobotisLeaderConfig, BiRobotisLeader

    bi_follower = BiPiperFollower(BiPiperFollowerConfig())
    bi_leader = BiRobotisLeader(BiRobotisLeaderConfig())
    bi_leader.connect()
    bi_follower.connect()

    times = {"get_obs": [], "read_leader": [], "send_action": [], "total": []}
    for i in range(200):
        t0 = time.perf_counter()

        obs = bi_follower.get_observation()
        t1 = time.perf_counter()

        action = bi_leader.get_action()
        t2 = time.perf_counter()

        bi_follower.send_action(action)
        t3 = time.perf_counter()

        times["get_obs"].append((t1 - t0) * 1000)
        times["read_leader"].append((t2 - t1) * 1000)
        times["send_action"].append((t3 - t2) * 1000)
        times["total"].append((t3 - t0) * 1000)

    for k, v in times.items():
        print(f"  {k:15s}: avg={statistics.mean(v):.2f}ms  p50={statistics.median(v):.2f}ms  p99={sorted(v)[int(len(v)*0.99)]:.2f}ms  max={max(v):.2f}ms")

    bi_leader.disconnect()
    bi_follower.disconnect()
    print("\nDone.")


if __name__ == "__main__":
    main()
