#!/usr/bin/env bash
# Single experiment: KL(S1 || S2) in the PPO loss instead of a second Adam phase.
# Predeclared endpoint: update 200 for all three seeds; trend is diagnostic only.
# Default recoverable U(0, .08), hard U(.15, .25), damage weight 10000.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export RECOVERABLE_MAX="${RECOVERABLE_MAX:-0.08}"
export DAMAGE_W=10000 CRITIC_WARMUP=0 LR= ANCHOR_EPOCHS=
export UPDATES=200 UPDATE=200
export ANCHOR="${ANCHOR:-1.0}" ANCHOR_MODE=objective
TAG="s2_dmg10000_anc${ANCHOR}_objective"
bash scripts/run_stage2_pilot.sh "$@"
TAG="$TAG" bash scripts/run_stage2_eval.sh "$@"
TAG="$TAG" UPDATES="50 100 150" bash scripts/run_stage2_eval_trend.sh "$@"
