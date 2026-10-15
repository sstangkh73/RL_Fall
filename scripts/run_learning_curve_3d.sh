#!/usr/bin/env bash
# Long CPU PPO learning curve (3D, condition B) to estimate transitions-to-solution.
# Each update is 2,048 transitions; checkpoints are evaluated on 64 impaired scenarios.
# Usage: scripts/run_learning_curve_3d.sh [updates] [checkpoint-every] [seed]
set -euo pipefail

UPDATES="${1:-12000}"
EVERY="${2:-1500}"
SEED="${3:-55001}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"

"$PY" -m rl_fall.train --environment 3d --output results/learning_curve_3d \
    --stage learning_curve --device cpu --condition B --seed "$SEED" \
    --n-envs 8 --threads 4 --warmup-updates 0 --measured-updates "$UPDATES" \
    --evaluation-scenarios 64 --checkpoint-updates $(seq 0 "$EVERY" "$UPDATES")
