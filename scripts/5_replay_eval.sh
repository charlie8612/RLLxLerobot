#!/bin/bash
# Phase 5: Replay eval dataset episodes in Rerun GUI
# Usage:
#   ./scripts/5_replay_eval.sh        # list available episodes
#   ./scripts/5_replay_eval.sh 3      # replay episode 3
#   ./scripts/5_replay_eval.sh all    # replay all episodes one by one

REPO_ID="charliechan/eval_diffusion_dual_cam"
ROOT="/home/charliechan/dataset"
TOTAL=$(python3 -c "import json; print(json.load(open('${ROOT}/${REPO_ID}/meta/info.json'))['total_episodes'])" 2>/dev/null)

if [ -z "$TOTAL" ] || [ "$TOTAL" = "0" ]; then
    echo "No eval dataset found at ${ROOT}/${REPO_ID}"
    exit 1
fi

if [ -z "$1" ]; then
    echo "Eval dataset: ${REPO_ID}"
    echo "Available episodes: 0 ~ $((TOTAL - 1))  (total: ${TOTAL})"
    echo ""
    echo "Usage:"
    echo "  $0 <episode>   # replay one episode"
    echo "  $0 all          # replay all episodes"
    exit 0
fi

if [ "$1" = "all" ]; then
    for i in $(seq 0 $((TOTAL - 1))); do
        echo "=== Episode $i / $((TOTAL - 1)) ==="
        python -m lerobot.scripts.lerobot_dataset_viz \
            --repo-id "$REPO_ID" \
            --root "$ROOT" \
            --episode-index "$i"
    done
else
    python -m lerobot.scripts.lerobot_dataset_viz \
        --repo-id "$REPO_ID" \
        --root "$ROOT" \
        --episode-index "$1"
fi
