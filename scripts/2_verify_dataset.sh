#!/bin/bash
# Verify recorded dataset contents
python3 -c "
from lerobot.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset('charliechan/piper-leader-test')
print(f'Episodes: {ds.meta.total_episodes}')
print(f'Frames: {len(ds)}')
print(f'Features: {list(ds.meta.features.keys())}')
"
