#!/bin/bash
# Phase 2: Replay a recorded episode on Piper (from camera dataset)
# Usage: bash replay_episode_cam.sh [episode_num]

EPISODE=${1:-0}

lerobot-replay \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --dataset.repo_id=charliechan/piper-leader-cam-test \
    --dataset.episode=$EPISODE
