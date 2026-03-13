#!/usr/bin/env python3
"""Wandb run cleanup tool.

List, filter, and delete wandb runs.

Usage:
    # 列出所有 runs
    python tools/wandb_cleanup.py --project piper-pick-cube --list

    # 只列出 crashed / failed runs
    python tools/wandb_cleanup.py --project piper-pick-cube --list --state crashed,failed

    # 列出沒有 summary metrics 的空 runs
    python tools/wandb_cleanup.py --project piper-pick-cube --list --empty

    # 刪除指定 run IDs
    python tools/wandb_cleanup.py --project piper-pick-cube --delete abc123 def456

    # 刪除所有 crashed runs
    python tools/wandb_cleanup.py --project piper-pick-cube --delete-by-state crashed

    # 刪除所有空 runs
    python tools/wandb_cleanup.py --project piper-pick-cube --delete-empty

    # Dry run（只顯示會刪什麼，不真的刪）
    python tools/wandb_cleanup.py --project piper-pick-cube --delete-empty --dry-run
"""

import argparse
import sys

ENTITY = "charlie88162-nycu"


def get_api():
    from wandb import Api
    return Api()


def list_runs(api, project, state_filter=None, empty_only=False):
    runs = api.runs(f"{ENTITY}/{project}")
    results = []
    for r in runs:
        # Filter by state
        if state_filter:
            if r.state not in state_filter:
                continue

        # Filter empty runs (no non-internal summary keys)
        summary_keys = [k for k in r.summary.keys() if not k.startswith("_")]
        is_empty = len(summary_keys) == 0

        if empty_only and not is_empty:
            continue

        results.append({
            "id": r.id,
            "name": r.name,
            "state": r.state,
            "job_type": r.job_type or "-",
            "summary_keys": len(summary_keys),
            "run": r,
        })
    return results


def print_runs(runs):
    if not runs:
        print("  No runs found.")
        return

    # Header
    print(f"  {'ID':<12s} {'State':<10s} {'Job Type':<10s} {'#Keys':>5s}  Name")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*5}  {'-'*30}")
    for r in runs:
        print(f"  {r['id']:<12s} {r['state']:<10s} {r['job_type']:<10s} {r['summary_keys']:>5d}  {r['name']}")
    print(f"\n  Total: {len(runs)} runs")


def delete_runs(runs, dry_run=False):
    if not runs:
        print("  Nothing to delete.")
        return

    print(f"\n  Will delete {len(runs)} run(s):")
    for r in runs:
        print(f"    {r['id']}  {r['name']}  ({r['state']})")

    if dry_run:
        print("\n  (dry run — no runs deleted)")
        return

    confirm = input(f"\n  Confirm delete {len(runs)} runs? [y/N]: ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    for r in runs:
        r["run"].delete()
        print(f"    Deleted: {r['id']} ({r['name']})")
    print(f"\n  Done. {len(runs)} runs deleted.")


def main():
    parser = argparse.ArgumentParser(description="Wandb run cleanup tool")
    parser.add_argument("--project", required=True, help="Wandb project name")

    # List
    parser.add_argument("--list", action="store_true", help="List runs")
    parser.add_argument("--state", type=str, default=None,
                        help="Filter by state (comma-separated: finished,crashed,failed,running)")
    parser.add_argument("--empty", action="store_true", help="Only show empty runs (no summary metrics)")

    # Delete
    parser.add_argument("--delete", nargs="+", metavar="RUN_ID", help="Delete specific run IDs")
    parser.add_argument("--delete-by-state", type=str, default=None,
                        help="Delete all runs with given state (e.g. crashed)")
    parser.add_argument("--delete-empty", action="store_true", help="Delete all empty runs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")

    args = parser.parse_args()

    api = get_api()

    state_filter = args.state.split(",") if args.state else None

    if args.list or (not args.delete and not args.delete_by_state and not args.delete_empty):
        runs = list_runs(api, args.project, state_filter=state_filter, empty_only=args.empty)
        print_runs(runs)

    elif args.delete:
        all_runs = list_runs(api, args.project)
        to_delete = [r for r in all_runs if r["id"] in args.delete]
        not_found = set(args.delete) - {r["id"] for r in to_delete}
        if not_found:
            print(f"  Warning: run IDs not found: {', '.join(not_found)}")
        delete_runs(to_delete, dry_run=args.dry_run)

    elif args.delete_by_state:
        states = args.delete_by_state.split(",")
        runs = list_runs(api, args.project, state_filter=states)
        delete_runs(runs, dry_run=args.dry_run)

    elif args.delete_empty:
        runs = list_runs(api, args.project, empty_only=True)
        delete_runs(runs, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
