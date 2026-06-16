#!/bin/bash
# Phase 8: Replay set 3
# Usage: bash scripts/8_replay_3.sh [episode_number]

EPISODE=${1:-0}

lerobot-replay \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --dataset.repo_id=charliechan/piper-high-3 \
    --dataset.episode=$EPISODE
