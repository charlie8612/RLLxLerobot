#!/usr/bin/env python3
"""Record video from ZED 2 camera via OpenCV.

Usage:
    python tools/record_zed2.py                        # default: left eye, 30fps
    python tools/record_zed2.py --mode sbs             # side-by-side (both eyes)
    python tools/record_zed2.py --mode left --fps 15   # left eye at 15fps
    python tools/record_zed2.py -o my_video.mp4        # custom output filename

Press Ctrl+C to stop recording.
"""

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser(description="Record video from ZED 2")
    parser.add_argument(
        "--device", default="/dev/video0", help="Video device (default: /dev/video0)"
    )
    parser.add_argument(
        "--mode",
        choices=["left", "right", "sbs"],
        default="left",
        help="left/right eye or side-by-side (default: left)",
    )
    parser.add_argument("--fps", type=int, default=30, help="Recording FPS (default: 30)")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output filename (default: zed2_YYYYMMDD_HHMMSS.mp4)",
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        print(f"Error: Cannot open {args.device}")
        return 1

    ret, frame = cap.read()
    if not ret:
        print("Error: Cannot read from camera")
        cap.release()
        return 1

    h, w = frame.shape[:2]
    half_w = w // 2
    print(f"ZED 2 raw frame: {w}x{h} (side-by-side)")

    # Determine output frame size
    if args.mode == "left":
        out_w, out_h = half_w, h
        print(f"Recording LEFT eye: {out_w}x{out_h}")
    elif args.mode == "right":
        out_w, out_h = half_w, h
        print(f"Recording RIGHT eye: {out_w}x{out_h}")
    else:
        out_w, out_h = w, h
        print(f"Recording SIDE-BY-SIDE: {out_w}x{out_h}")

    # Output path
    if args.output:
        out_path = args.output
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = f"/tmp2/charlie/zed2_{timestamp}.mp4"

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    # Record to temporary AVI (MJPG), then convert to H.264 MP4 with actual fps
    tmp_avi = tempfile.mktemp(suffix=".avi", dir=str(Path(out_path).parent))
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    # Use a placeholder fps for AVI; final MP4 will use actual measured fps
    writer = cv2.VideoWriter(tmp_avi, fourcc, 30, (out_w, out_h))

    print(f"Output: {out_path} @ ~{args.fps}fps")
    print("Press Ctrl+C to stop recording...")

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Lost camera feed")
                break

            if args.mode == "left":
                out_frame = frame[:, :half_w]
            elif args.mode == "right":
                out_frame = frame[:, half_w:]
            else:
                out_frame = frame

            writer.write(out_frame)
            frame_count += 1

            if frame_count % args.fps == 0:
                elapsed_so_far = time.time() - start_time
                print(
                    f"\r  Recording... {frame_count} frames, "
                    f"{elapsed_so_far:.1f}s, "
                    f"{frame_count/elapsed_so_far:.1f} fps",
                    end="", flush=True,
                )

    except KeyboardInterrupt:
        pass

    elapsed = time.time() - start_time
    cap.release()
    writer.release()

    actual_fps = frame_count / elapsed if elapsed > 0 else args.fps
    print(f"\nDone! {frame_count} frames in {elapsed:.1f}s ({actual_fps:.1f} fps)")

    # Convert to H.264 MP4 with actual measured fps
    print("Converting to H.264 MP4...")
    result = subprocess.run(
        ["ffmpeg", "-y", "-r", str(actual_fps), "-i", tmp_avi,
         "-c:v", "libx264", "-preset", "fast",
         "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(actual_fps), out_path],
        capture_output=True, text=True,
    )
    Path(tmp_avi).unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr}")
        return 1

    print(f"Saved to: {out_path}")
    return 0


if __name__ == "__main__":
    exit(main())
