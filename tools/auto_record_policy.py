#!/usr/bin/env python3
"""Auto record + policy execution for balance_bar task.

Loops colors outer / per-color index inner — i.e. blue1..blueN, then red1..redN, etc.
Each trial:
  1. Start record_cam.py (background subprocess)
  2. Wait for camera warmup
  3. Run waypoint.py execute <waypoint.json> (blocking, auto-presses Enter)
  4. Send SIGINT to recorder, wait for ffmpeg conversion to finish

Output: /tmp2/charlie/balance_bar/balance_bar_<i>_<color><k>.mp4
        where i = session number (--i), k = per-color index (1..n)

Usage:
  python tools/auto_record_policy.py --i 1          # session 1, 7 each color
  python tools/auto_record_policy.py --i 2 --n 3    # session 2, 3 each color
  python tools/auto_record_policy.py --i 1 --colors blue --n 7
"""

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WAYPOINT_DIR = REPO / "waypoints" / "balance_bar"
DEFAULT_OUTPUT_DIR = Path("/tmp2/charlie/balance_bar")
DEFAULT_DEVICE = "/dev/cam_c270"
DEFAULT_COLORS = ["blue", "red", "white"]
CAMERA_WARMUP_S = 2.0
RECORDER_STOP_TIMEOUT_S = 30.0
INTER_TRIAL_PAUSE_S = 5.0

SOUND_START = "/usr/share/sounds/Yaru/stereo/desktop-logoff.oga"  # falling chime
SOUND_DONE = "/usr/share/sounds/Yaru/stereo/desktop-login.oga"    # rising chime


def beep(sound_path: str = SOUND_DONE, count: int = 1) -> None:
    """Play a notification sound. Falls back to terminal bell if paplay fails."""
    for _ in range(count):
        try:
            subprocess.run(
                ["paplay", sound_path],
                check=False, timeout=5,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("\a", end="", flush=True)


def run_one(color: str, k: int, i: int, device: str, output_dir: Path, task_prefix: str) -> int:
    waypoint_json = WAYPOINT_DIR / f"test2_{color}.json"
    if not waypoint_json.exists():
        print(f"[ERR] missing waypoint file: {waypoint_json}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = output_dir / f"{task_prefix}_{i}_{color}{k}.mp4"

    print(f"\n=== {color} #{k} (session {i}) ===")
    print(f"  waypoint: {waypoint_json}")
    print(f"  output:   {out_mp4}")
    beep(SOUND_START)

    rec_cmd = [
        sys.executable, str(REPO / "tools" / "record_cam.py"),
        "--device", device,
        "-o", str(out_mp4),
    ]
    print(f"  [rec] start: {' '.join(rec_cmd)}")
    rec_proc = subprocess.Popen(rec_cmd)

    print(f"  [rec] camera warmup ({CAMERA_WARMUP_S}s)...")
    time.sleep(CAMERA_WARMUP_S)

    if rec_proc.poll() is not None:
        print(f"[ERR] recorder exited early with code {rec_proc.returncode}", file=sys.stderr)
        return 1

    pol_cmd = [
        sys.executable, str(REPO / "tools" / "waypoint.py"),
        "execute", str(waypoint_json),
    ]
    print(f"  [policy] run: {' '.join(pol_cmd)}")
    pol_ret = subprocess.run(pol_cmd, input="\n", text=True).returncode
    print(f"  [policy] done (exit={pol_ret})")

    print(f"  [rec] sending SIGINT...")
    rec_proc.send_signal(signal.SIGINT)
    try:
        rec_ret = rec_proc.wait(timeout=RECORDER_STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        print(f"[WARN] recorder didn't stop in {RECORDER_STOP_TIMEOUT_S}s, terminating", file=sys.stderr)
        rec_proc.terminate()
        rec_ret = rec_proc.wait(timeout=5)
    print(f"  [rec] done (exit={rec_ret})")
    beep(SOUND_DONE)

    if pol_ret != 0:
        print(f"[WARN] policy returned non-zero ({pol_ret}); video saved anyway: {out_mp4}")
    return 0 if (pol_ret == 0 and rec_ret == 0) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--i", type=int, required=True, help="Session number (goes into filename prefix)")
    ap.add_argument("--n", type=int, default=7, help="Recordings per color (default: 7)")
    ap.add_argument("--colors", default=",".join(DEFAULT_COLORS),
                    help=f"Comma-separated colors (default: {','.join(DEFAULT_COLORS)})")
    ap.add_argument("--device", default=DEFAULT_DEVICE, help=f"Camera device (default: {DEFAULT_DEVICE})")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                    help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    ap.add_argument("--task-prefix", default="balance_bar",
                    help="Output filename prefix (default: balance_bar)")
    args = ap.parse_args()

    colors = [c.strip() for c in args.colors.split(",") if c.strip()]
    if not colors:
        print("[ERR] no colors specified", file=sys.stderr)
        return 1
    if args.n < 1:
        print("[ERR] --n must be >= 1", file=sys.stderr)
        return 1

    indices = list(range(1, args.n + 1))
    print(f"session i = {args.i}")
    print(f"colors    = {colors}")
    print(f"indices   = {indices} ({args.n} per color)")

    results: list[tuple[str, int, int]] = []  # (color, k, rc)
    trials = [(c, k) for c in colors for k in indices]
    for idx, (color, k) in enumerate(trials):
        try:
            rc = run_one(color, k, args.i, args.device, args.output_dir, args.task_prefix)
        except KeyboardInterrupt:
            print("\n[ABORT] Ctrl+C received, stopping.", file=sys.stderr)
            return 130
        results.append((color, k, rc))
        if idx < len(trials) - 1:
            print(f"\n  pausing {INTER_TRIAL_PAUSE_S}s before next trial...")
            time.sleep(INTER_TRIAL_PAUSE_S)

    print("\n=== summary ===")
    for color, k, rc in results:
        path = args.output_dir / f"{args.task_prefix}_{args.i}_{color}{k}.mp4"
        status = "OK" if rc == 0 else "FAIL"
        print(f"  [{status}] {path}")
    failed = [r for r in results if r[2] != 0]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
