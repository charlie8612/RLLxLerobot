#!/usr/bin/env python3
"""Auto record + replay for pin_ball task.

Loops policies outer / per-policy index inner — i.e. empty1..empty4, then
heavy1..heavy4, then light1..light4.

Each trial:
  1. Start record_cam.py (background subprocess)
  2. Wait for camera warmup
  3. Run the policy's bash replay script (blocking)
  4. Send SIGINT to recorder, wait for ffmpeg conversion to finish

Output: /tmp2/charlie/pin_ball/pin_ball_<k>_<ball_type>_<policy>.mp4
        where k = per-policy index (1..n), ball_type = --ball-type (e.g. light)

Usage:
  python tools/auto_record_pinball.py --ball-type light
  python tools/auto_record_pinball.py --ball-type heavy --n 4
"""

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = Path("/tmp2/charlie/pin_ball")
DEFAULT_DEVICE = "/dev/cam_c270"
CAMERA_WARMUP_S = 2.0
RECORDER_STOP_TIMEOUT_S = 30.0
INTER_TRIAL_PAUSE_S = 5.0

SOUND_START = "/usr/share/sounds/Yaru/stereo/desktop-logoff.oga"
SOUND_DONE = "/usr/share/sounds/Yaru/stereo/desktop-login.oga"

POLICIES = [
    ("empty", ["bash", "scripts/2_replay_episode.sh"]),
    ("heavy", ["bash", "scripts/8_replay_1.sh", "4"]),
    ("light", ["bash", "scripts/8_replay_2.sh", "4"]),
]


def beep(sound_path: str = SOUND_DONE, count: int = 1) -> None:
    for _ in range(count):
        try:
            subprocess.run(
                ["paplay", sound_path],
                check=False, timeout=5,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("\a", end="", flush=True)


def run_one(policy_name: str, policy_cmd: list[str], k: int, ball_type: str,
            device: str, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = output_dir / f"pin_ball_{k}_{ball_type}_{policy_name}.mp4"

    print(f"\n=== {policy_name} #{k} (ball={ball_type}) ===")
    print(f"  policy:   {' '.join(policy_cmd)}")
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

    print(f"  [policy] run: {' '.join(policy_cmd)}")
    pol_ret = subprocess.run(policy_cmd, cwd=str(REPO), input="\n", text=True).returncode
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
    ap.add_argument("--ball-type", required=True,
                    help="Ball type prefix for filename (e.g. light, heavy, medium)")
    ap.add_argument("--policy", default="all",
                    help="Comma-separated policy names to run, or 'all' (default: all). "
                         f"Available: {','.join(p[0] for p in POLICIES)}")
    ap.add_argument("--n", type=int, default=4, help="Recordings per policy (default: 4)")
    ap.add_argument("--indices", default=None,
                    help="Comma-separated specific indices to run (e.g. '4' or '2,4'). "
                         "Overrides --n if set.")
    ap.add_argument("--device", default=DEFAULT_DEVICE, help=f"Camera device (default: {DEFAULT_DEVICE})")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                    help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    args = ap.parse_args()

    if args.indices:
        try:
            indices = [int(s.strip()) for s in args.indices.split(",") if s.strip()]
        except ValueError:
            print(f"[ERR] --indices must be comma-separated ints, got: {args.indices}", file=sys.stderr)
            return 1
        if any(i < 1 for i in indices):
            print("[ERR] indices must be >= 1", file=sys.stderr)
            return 1
    else:
        if args.n < 1:
            print("[ERR] --n must be >= 1", file=sys.stderr)
            return 1
        indices = list(range(1, args.n + 1))

    all_names = [p[0] for p in POLICIES]
    if args.policy == "all":
        selected = POLICIES
    else:
        wanted = [s.strip() for s in args.policy.split(",") if s.strip()]
        unknown = [w for w in wanted if w not in all_names]
        if unknown:
            print(f"[ERR] unknown policy: {unknown}. Available: {all_names}", file=sys.stderr)
            return 1
        selected = [(name, cmd) for name, cmd in POLICIES if name in wanted]

    print(f"ball_type = {args.ball_type}")
    print(f"policies  = {[p[0] for p in selected]}")
    print(f"indices   = {indices}")

    results: list[tuple[str, int, int]] = []  # (policy, k, rc)
    trials = [(name, cmd, k) for name, cmd in selected for k in indices]
    for idx, (policy_name, policy_cmd, k) in enumerate(trials):
        try:
            rc = run_one(policy_name, policy_cmd, k, args.ball_type, args.device, args.output_dir)
        except KeyboardInterrupt:
            print("\n[ABORT] Ctrl+C received, stopping.", file=sys.stderr)
            return 130
        results.append((policy_name, k, rc))
        if idx < len(trials) - 1:
            print(f"\n  pausing {INTER_TRIAL_PAUSE_S}s before next trial...")
            time.sleep(INTER_TRIAL_PAUSE_S)

    print("\n=== summary ===")
    for policy_name, k, rc in results:
        path = args.output_dir / f"pin_ball_{k}_{args.ball_type}_{policy_name}.mp4"
        status = "OK" if rc == 0 else "FAIL"
        print(f"  [{status}] {path}")
    failed = [r for r in results if r[2] != 0]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
