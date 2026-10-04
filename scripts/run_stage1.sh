#!/usr/bin/env bash
# Curriculum stage 1 (balance): train through increasing push levels, each level
# continuing from the previous level's final checkpoint.
# Usage: scripts/run_stage1.sh [seed] [updates-per-level] [levels...]
set -euo pipefail

SEED="${1:-61001}"
UPDATES="${2:-300}"
shift $(( $# > 2 ? 2 : $# ))
LEVELS=("${@:-0.2 0.3 0.45}")
read -r -a LEVELS <<< "${LEVELS[*]}"
EVERY="${EVERY:-25}"  # balance updates are 16,384 transitions each
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
OUT="results/stage1/seed_${SEED}"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
mkdir -p "$OUT"

INIT=()
for LEVEL in "${LEVELS[@]}"; do
    LEVEL_OUT="$OUT/push_${LEVEL}"
    echo "=== $(date '+%F %T') S1 seed=$SEED push<=$LEVEL updates=$UPDATES ${INIT[*]:-from scratch}"
    "$PY" -m rl_fall.train --environment 3d --body v0_2 --mode balance \
        --condition A --max-push-impulse "$LEVEL" --stage S1_balance \
        --output "$LEVEL_OUT" --device cpu --seed "$SEED" --n-envs 8 --threads 4 \
        --warmup-updates 0 --measured-updates "$UPDATES" --evaluation-scenarios 64 \
        --checkpoint-updates $(seq 0 "$EVERY" "$UPDATES") "${INIT[@]}" > "$LEVEL_OUT.log" 2>&1
    RUN_DIR="$(ls -td "$LEVEL_OUT"/3d_* | head -1)"
    INIT=(--init-checkpoint "$RUN_DIR/checkpoint.zip")
done
echo "=== $(date '+%F %T') S1 seed=$SEED done"
