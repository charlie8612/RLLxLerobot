#!/bin/bash
# Phase 2: Visualize recorded dataset (camera + joints) in browser
# Usage: bash viz_dataset_cam.sh [episode_num]

EPISODE=${1:-0}

lerobot-dataset-viz \
    --repo-id charliechan/piper-leader-cam-test \
    --episode-index $EPISODE
