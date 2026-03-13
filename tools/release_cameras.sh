#!/bin/bash
# Release stuck camera devices (no sudo needed)
# Only kills processes that are holding our cameras
# Usage: bash tools/release_cameras.sh

for dev in /dev/cam_c270 /dev/cam_arc; do
    pids=$(lsof -t "$dev" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "$dev held by:"
        # Show what each process is, so you know what's being killed
        for pid in $pids; do
            cmd=$(ps -p "$pid" -o pid=,user=,comm=,args= 2>/dev/null)
            echo "  $cmd"
        done
        kill $pids 2>/dev/null
        sleep 0.3
        remaining=$(lsof -t "$dev" 2>/dev/null)
        if [ -n "$remaining" ]; then
            kill -9 $remaining 2>/dev/null
        fi
        echo "  -> killed"
    else
        echo "$dev — free"
    fi
done
