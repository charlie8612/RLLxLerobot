#!/usr/bin/env python3
"""B9 — Waypoint Capture + Interpolation

Two modes:
  1. Record:  用 ROBOTIS leader arm teleop 控制 Piper 到定點，
              按 Enter 記錄 waypoint，按 q 結束。存成 JSON。
  2. Execute: 讀取 JSON，用 smoothstep interpolation 自動播放軌跡。

Usage:
  # 錄製 waypoints
  python tools/waypoint.py record -o waypoints/pick_place.json

  # 播放 waypoints
  python tools/waypoint.py execute waypoints/pick_place.json

  # 播放，指定速度（度/秒），迴圈 3 次
  python tools/waypoint.py execute waypoints/pick_place.json --speed 45 --loop 3

  # 查看已存的 waypoints
  python tools/waypoint.py list waypoints/pick_place.json

Record 操作：
  Enter       記錄當前位置（到達後不停留）
  p<秒數>     記錄當前位置，到達後暫停 N 秒（例如 p2 = 暫停 2 秒）
  d           刪除最後一個 waypoint
  l           列出目前所有 waypoints
  q           結束錄製並存檔
"""

import argparse
import json
import math
import os
import re
import sys
import time
import selectors
import signal

# --------------------------------------------------------------------------- #
#  Imports — uses LeRobot plugin API (PiperFollower / RobotisLeader)
# --------------------------------------------------------------------------- #
from lerobot_robot_piper.piper_follower import PiperFollower
from lerobot_robot_piper.config_piper_follower import PiperFollowerConfig
from lerobot_teleoperator_robotis.robotis_leader import RobotisLeader
from lerobot_teleoperator_robotis.config_robotis_leader import RobotisLeaderConfig

# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #
JOINT_KEYS = [
    "joint_1.pos", "joint_2.pos", "joint_3.pos",
    "joint_4.pos", "joint_5.pos", "joint_6.pos",
]
GRIPPER_KEY = "gripper.pos"
ALL_KEYS = JOINT_KEYS + [GRIPPER_KEY]

CONTROL_RATE = 100.0  # Hz for interpolation
DEFAULT_SPEED = 60.0  # deg/s
MIN_DURATION = 0.3    # seconds — avoid instant jumps for tiny moves
SAFE_SPEED = 30.0     # deg/s for moving to rest position on shutdown

# Rest position: arm folded, safe for power-off
REST_STATE = {
    "joint_1.pos": -0.83,
    "joint_2.pos": -0.14,
    "joint_3.pos": -0.38,
    "joint_4.pos": -1.39,
    "joint_5.pos": 0.0,
    "joint_6.pos": 2.11,
    "gripper.pos": 0.0,
}


def smoothstep(x: float) -> float:
    """Smooth interpolation between 0 and 1 for x in [0, 1]."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def read_state(robot: PiperFollower) -> dict[str, float]:
    """Read current Piper state as {joint_N.pos: deg, gripper.pos: mm}."""
    obs = robot.get_observation()
    return {k: obs[k] for k in ALL_KEYS}


def format_state(state: dict[str, float], compact: bool = False) -> str:
    """Pretty-print joint state. compact=True for live display (shorter)."""
    if compact:
        vals = "/".join(f"{state[k]:+.1f}" for k in JOINT_KEYS)
        return f"[{vals}] G={state[GRIPPER_KEY]:.1f}"
    parts = []
    for i, k in enumerate(JOINT_KEYS):
        parts.append(f"J{i+1}={state[k]:+7.1f}")
    parts.append(f"G={state[GRIPPER_KEY]:4.1f}mm")
    return " ".join(parts)


def compute_duration(start: dict[str, float], target: dict[str, float], speed: float) -> float:
    """Compute move duration based on max joint displacement and desired speed (deg/s)."""
    max_delta = 0.0
    for k in JOINT_KEYS:
        max_delta = max(max_delta, abs(target[k] - start[k]))
    # Gripper: treat mm roughly as degrees for speed calculation
    max_delta = max(max_delta, abs(target[GRIPPER_KEY] - start[GRIPPER_KEY]))
    duration = max_delta / speed
    return max(duration, MIN_DURATION)


def print_waypoints_table(waypoints: list[dict]):
    """Print recorded waypoints as a table."""
    if not waypoints:
        print("  (no waypoints)")
        return
    print(f"  {'#':>3}  {'J1':>7}  {'J2':>7}  {'J3':>7}  {'J4':>7}  {'J5':>7}  {'J6':>7}  {'Grip':>6}  {'Pause':>5}")
    print(f"  {'---':>3}  {'-------':>7}  {'-------':>7}  {'-------':>7}  {'-------':>7}  {'-------':>7}  {'-------':>7}  {'------':>6}  {'-----':>5}")
    for i, wp in enumerate(waypoints):
        s = wp["state"]
        pause = wp.get("pause", 0.0)
        vals = "  ".join(f"{s[k]:>+7.1f}" for k in JOINT_KEYS)
        pause_str = f"{pause:.1f}s" if pause > 0 else "-"
        print(f"  {i:>3}  {vals}  {s[GRIPPER_KEY]:>6.1f}  {pause_str:>5}")


def save_waypoints(waypoints: list[dict], filepath: str):
    """Save waypoints to JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump({"waypoints": waypoints}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(waypoints)} waypoints -> {filepath}")


def load_waypoints(filepath: str) -> list[dict]:
    """Load waypoints from JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    waypoints = data["waypoints"]
    print(f"Loaded {len(waypoints)} waypoints from {filepath}")
    return waypoints


# --------------------------------------------------------------------------- #
#  Interpolation executor
# --------------------------------------------------------------------------- #
def interpolate_and_execute(
    robot: PiperFollower,
    start: dict[str, float],
    target: dict[str, float],
    duration: float,
):
    """Smooth interpolation from start to target over `duration` seconds."""
    steps = max(int(duration * CONTROL_RATE), 1)
    dt = 1.0 / CONTROL_RATE

    for i in range(steps):
        t = smoothstep((i + 1) / steps)
        action = {}
        for k in ALL_KEYS:
            action[k] = start[k] + t * (target[k] - start[k])
        robot.send_action(action)
        time.sleep(dt)

    # Stabilise at target
    for _ in range(10):
        robot.send_action(target)
        time.sleep(dt)


# --------------------------------------------------------------------------- #
#  Connect helpers
# --------------------------------------------------------------------------- #
def safe_disconnect(robot: PiperFollower):
    """Move to rest position before disconnecting to prevent the arm from dropping."""
    print("\n  Moving to rest position...")
    try:
        current = read_state(robot)
        duration = compute_duration(current, REST_STATE, SAFE_SPEED)
        interpolate_and_execute(robot, current, REST_STATE, duration)
        print("  Rest position reached.")
    except Exception as e:
        print(f"  Warning: failed to reach rest position: {e}")
    robot.disconnect()
    print("  Arm disconnected.")


def connect_robot(can_port: str) -> PiperFollower:
    config = PiperFollowerConfig()
    config.can_port = can_port
    robot = PiperFollower(config)
    robot.connect()
    return robot


def connect_leader(port: str) -> RobotisLeader:
    config = RobotisLeaderConfig()
    config.port = port
    teleop = RobotisLeader(config)
    teleop.connect()
    return teleop


# --------------------------------------------------------------------------- #
#  RECORD mode
# --------------------------------------------------------------------------- #
PAUSE_RE = re.compile(r"^p(\d+\.?\d*)$")  # matches p0.5, p2, p1.5, etc.


def cmd_record(args):
    print("Connecting to Piper arm...")
    robot = connect_robot(args.can_port)

    print("Connecting to leader arm...")
    teleop = connect_leader(args.leader_port)

    waypoints: list[dict] = []
    running = True

    def handle_sigint(sig, frame):
        nonlocal running
        running = False
        print("\n\nInterrupted -- finishing up...")

    signal.signal(signal.SIGINT, handle_sigint)

    sel = selectors.DefaultSelector()
    sel.register(sys.stdin, selectors.EVENT_READ)

    print()
    print("=" * 65)
    print("  WAYPOINT RECORDER")
    print("=" * 65)
    print("  Enter       record position (no pause)")
    print("  p<seconds>  record position + pause (e.g. p2 = pause 2s)")
    print("  d           delete last waypoint")
    print("  l           list all waypoints")
    print("  q           finish and save")
    print("=" * 65)

    CLEAR_LINE = "\r\033[K"  # move to start of line + erase to end

    def log(msg: str):
        """Print a message above the live line."""
        sys.stdout.write(CLEAR_LINE)  # erase the live line
        print(msg)                    # print message (with newline)
        # live line will be redrawn on next loop iteration

    try:
        while running:
            # Teleop loop: read leader, send to follower
            action = teleop.get_action()
            robot.send_action(action)

            # Display current state (always overwrite same line)
            state = read_state(robot)
            sys.stdout.write(f"{CLEAR_LINE}  Live: {format_state(state, compact=True)}  [wp:{len(waypoints)}]")
            sys.stdout.flush()

            # Non-blocking stdin check
            events = sel.select(timeout=0.02)
            for key, _ in events:
                line = sys.stdin.readline().strip()

                if line.lower() == "q":
                    running = False
                elif line.lower() == "d":
                    if waypoints:
                        waypoints.pop()
                        log(f"  Deleted. {len(waypoints)} waypoints remaining.")
                    else:
                        log("  No waypoints to delete.")
                elif line.lower() == "l":
                    sys.stdout.write(CLEAR_LINE)
                    print_waypoints_table(waypoints)
                else:
                    # Check for pause command: p2, p0.5, etc.
                    pause = 0.0
                    m = PAUSE_RE.match(line.lower())
                    if m:
                        pause = float(m.group(1))

                    state = read_state(robot)
                    wp = {"state": state, "pause": pause}
                    waypoints.append(wp)
                    pause_info = f" (pause {pause}s)" if pause > 0 else ""
                    log(f"  #{len(waypoints)-1}: {format_state(state)}{pause_info}")

    finally:
        sel.unregister(sys.stdin)
        sel.close()

        if waypoints:
            filepath = args.output or os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "waypoints", "untitled.json",
            )
            save_waypoints(waypoints, filepath)
            print()
            print_waypoints_table(waypoints)
        else:
            print("\nNo waypoints captured.")

        teleop.disconnect()
        safe_disconnect(robot)


# --------------------------------------------------------------------------- #
#  EXECUTE mode
# --------------------------------------------------------------------------- #
def cmd_execute(args):
    waypoints = load_waypoints(args.file)
    if not waypoints:
        print("No waypoints to execute.")
        return

    print_waypoints_table(waypoints)

    print("\nConnecting to Piper arm...")
    robot = connect_robot(args.can_port)

    running = True

    def handle_sigint(sig, frame):
        nonlocal running
        running = False
        print("\n\nInterrupted -- stopping after current segment...")

    signal.signal(signal.SIGINT, handle_sigint)

    speed = args.speed
    loop = args.loop
    print(f"\nSpeed: {speed} deg/s, Loop: {loop}x")
    input("Press Enter to start...")

    try:
        for loop_i in range(loop):
            if not running:
                break
            if loop > 1:
                print(f"\n--- Loop {loop_i + 1}/{loop} ---")

            for wp_i, wp in enumerate(waypoints):
                if not running:
                    break
                target = wp["state"]
                pause = wp.get("pause", 0.0)

                current = read_state(robot)
                duration = compute_duration(current, target, speed)

                pause_info = f" -> pause {pause}s" if pause > 0 else ""
                print(f"  #{wp_i}: {format_state(target)}  ({duration:.1f}s){pause_info}")

                interpolate_and_execute(robot, current, target, duration)

                if pause > 0:
                    time.sleep(pause)

        if running:
            print("\nDone.")

    finally:
        safe_disconnect(robot)


# --------------------------------------------------------------------------- #
#  LIST mode
# --------------------------------------------------------------------------- #
def cmd_list(args):
    waypoints = load_waypoints(args.file)
    print_waypoints_table(waypoints)


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="B9 -- Waypoint Capture + Interpolation for Piper arm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--can-port", default="piper_left",
                        help="CAN port name (default: piper_left)")
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- record ----
    p_rec = sub.add_parser("record", help="Record waypoints via leader arm teleop")
    p_rec.add_argument("-o", "--output", type=str, default=None,
                       help="Output JSON file (default: waypoints/untitled.json)")
    p_rec.add_argument("--leader-port", default="/dev/robotis_left",
                       help="ROBOTIS leader serial port")
    p_rec.set_defaults(func=cmd_record)

    # ---- execute ----
    p_exec = sub.add_parser("execute", help="Execute waypoints with interpolation")
    p_exec.add_argument("file", help="Waypoint JSON file")
    p_exec.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                        help=f"Joint speed in deg/s (default: {DEFAULT_SPEED})")
    p_exec.add_argument("--loop", type=int, default=1,
                        help="Number of times to loop (default: 1)")
    p_exec.set_defaults(func=cmd_execute)

    # ---- list ----
    p_list = sub.add_parser("list", help="List waypoints in a file")
    p_list.add_argument("file", help="Waypoint JSON file")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
