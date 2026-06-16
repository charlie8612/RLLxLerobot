#!/bin/bash
# Replay a recorded episode on Piper
# Usage: bash scripts/2_replay_episode.sh [episode_number]
#
# Matches the dataset recorded by scripts/2_record_leader.sh.
# Control mode follows config default (use_mit_mode=False -> MOVE J + JointCtrl),
# which is the same mode used during recording. Faithful to record.

EPISODE=${1:-0}

lerobot-replay \
    --robot.type=piper_follower \
    --robot.can_port=piper_left \
    --dataset.repo_id=charliechan/piper-demo-balancebar \
    --dataset.episode=$EPISODE
