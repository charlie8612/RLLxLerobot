#!/usr/bin/env python3
"""Record video from a USB camera via OpenCV.

Usage:
    python tools/record_cam.py                                # default: /dev/cam_c270
    python tools/record_cam.py --device /dev/video0 --fps 15
    python tools/record_cam.py -o /tmp2/charlie/my_video.mp4

Press Ctrl+C to stop recording.
"""

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser(description="Record video from USB camera")
    parser.add_argument("--device", default="/dev/cam_c270", help="Video device (default: /dev/cam_c270)")
    parser.add_argument("--fps", type=int, default=30, help="Recording FPS (default: 30)")
    parser.add_argument("-o", "--output", default=None, help="Output filename (default: auto timestamp)")
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
    print(f"Frame: {w}x{h}")

    if args.output:
        out_path = args.output
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = f"/tmp2/charlie/cam_{timestamp}.mp4"

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    tmp_avi = tempfile.mktemp(suffix=".avi", dir=str(Path(out_path).parent))
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(tmp_avi, fourcc, 30, (w, h))

    print(f"Output: {out_path}")
    print("Press Ctrl+C to stop recording...")

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Lost camera feed")
                break

            writer.write(frame)
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
