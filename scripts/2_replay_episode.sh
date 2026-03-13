#!/bin/bash
# Replay a recorded episode on Piper (default: episode 0)
EPISODE=${1:-0}
lerobot-replay --robot.type=piper_follower --robot.can_port=piper_left --dataset.repo_id=charliechan/piper-leader-test --dataset.episode=$EPISODE
