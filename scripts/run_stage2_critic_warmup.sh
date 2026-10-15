#!/usr/bin/env bash
# S2 pilot with a critic warm-up: train, paired eval at update 200, then the
# checkpoint trend (50/100/150) so the false give-up curve can be compared with
# the s2_dmg10000 run (no warm-up).
# Usage: [CRITIC_WARMUP=25] [DAMAGE_W=10000] scripts/run_stage2_critic_warmup.sh [seed ...]
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export CRITIC_WARMUP="${CRITIC_WARMUP:-25}"
export DAMAGE_W="${DAMAGE_W:-10000}"
TAG="s2_dmg${DAMAGE_W}_cw${CRITIC_WARMUP}"
bash scripts/run_stage2_pilot.sh "$@" || exit 1
TAG="$TAG" bash scripts/run_stage2_eval.sh "$@" || exit 1
TAG="$TAG" UPDATES="50 100 150" bash scripts/run_stage2_eval_trend.sh "$@"
