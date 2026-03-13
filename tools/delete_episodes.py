#!/usr/bin/env python3
"""Delete bad episodes from a LeRobot dataset.

Usage:
    # 列出所有 episode 的 frame 數（預覽用）
    python tools/delete_episodes.py charliechan/piper-pick-cube --list

    # 刪除 episode 3 和 7
    python tools/delete_episodes.py charliechan/piper-pick-cube --delete 3 7

    # 刪除後不保留備份
    python tools/delete_episodes.py charliechan/piper-pick-cube --delete 3 7 --no-backup
"""

import argparse
import shutil
from pathlib import Path

from lerobot.utils.constants import HF_LEROBOT_HOME
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.dataset_tools import delete_episodes


def list_episodes(repo_id: str):
    ds = LeRobotDataset(repo_id)
    print(f"Dataset: {repo_id}")
    print(f"Total: {ds.num_episodes} episodes, {ds.num_frames} frames\n")

    ep_indices = ds.hf_dataset["episode_index"]
    for ep in range(ds.num_episodes):
        count = sum(1 for e in ep_indices if e == ep)
        print(f"  Episode {ep:3d}: {count:4d} frames")


def do_delete(repo_id: str, episodes: list[int], keep_backup: bool):
    ds = LeRobotDataset(repo_id)
    print(f"Before: {ds.num_episodes} episodes, {ds.num_frames} frames")
    print(f"Deleting episodes: {episodes}")

    tmp_repo_id = f"{repo_id}-tmp-clean"
    new_ds = delete_episodes(ds, episode_indices=episodes, repo_id=tmp_repo_id)

    original_dir = HF_LEROBOT_HOME / repo_id
    tmp_dir = HF_LEROBOT_HOME / tmp_repo_id
    backup_dir = Path(str(original_dir) + "-backup")

    # Swap directories
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    original_dir.rename(backup_dir)
    tmp_dir.rename(original_dir)

    # Verify
    ds_check = LeRobotDataset(repo_id)
    print(f"After:  {ds_check.num_episodes} episodes, {ds_check.num_frames} frames")

    if keep_backup:
        print(f"\nBackup saved at: {backup_dir}")
        print(f"To remove backup: rm -rf {backup_dir}")
    else:
        shutil.rmtree(backup_dir)
        print("\nBackup removed.")


def main():
    parser = argparse.ArgumentParser(description="Delete episodes from a LeRobot dataset")
    parser.add_argument("repo_id", help="Dataset repo_id (e.g. charliechan/piper-pick-cube)")
    parser.add_argument("--list", action="store_true", help="List all episodes and frame counts")
    parser.add_argument("--delete", nargs="+", type=int, metavar="EP", help="Episode indices to delete")
    parser.add_argument("--no-backup", action="store_true", help="Don't keep a backup of the original dataset")
    args = parser.parse_args()

    if args.list:
        list_episodes(args.repo_id)
    elif args.delete:
        do_delete(args.repo_id, args.delete, keep_backup=not args.no_backup)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
