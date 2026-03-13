#!/bin/bash
# Bring up Piper CAN interfaces
# Must run before any script that talks to the Piper arm
# Requires sudo

set -e

CAN_BITRATE=1000000

for iface in piper_left piper_right; do
    if ! ip link show "$iface" &>/dev/null; then
        echo "[SKIP] $iface not found (USB-CAN not plugged in?)"
        continue
    fi

    STATE=$(ip -br link show "$iface" | awk '{print $2}')
    if [ "$STATE" = "UP" ]; then
        echo "[OK]   $iface already UP"
    else
        sudo ip link set "$iface" down
        sudo ip link set "$iface" type can bitrate $CAN_BITRATE
        sudo ip link set "$iface" up
        echo "[UP]   $iface activated (bitrate $CAN_BITRATE)"
    fi
done
