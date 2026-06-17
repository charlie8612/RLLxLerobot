#!/bin/bash
# Install/refresh USB camera udev symlinks. Run with: sudo bash scripts/install_cam_rules.sh
set -e
SRC="/home/charliechan/piper-lerobot/config/99-usb-camera.rules"
cp "$SRC" /etc/udev/rules.d/99-usb-camera.rules
udevadm control --reload-rules
udevadm trigger
sleep 1
echo "=== camera symlinks ==="
ls -l /dev/cam_arc /dev/cam_wrist /dev/cam_c270 /dev/cam_c270b 2>&1
