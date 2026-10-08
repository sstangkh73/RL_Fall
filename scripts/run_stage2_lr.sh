#!/usr/bin/env bash
# S2 pilot with a smaller fine-tune learning rate (no critic warm-up): train, paired eval
# at update 200, then the checkpoint trend (50/100/150) so the false give-up curve can be
# compared with s2_dmg10000 (lr 1e-4) and s2_dmg10000_cw25.
# Usage: [LR=3e-5] [DAMAGE_W=10000] scripts/run_stage2_lr.sh [seed ...]
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export LR="${LR:-3e-5}"
export DAMAGE_W="${DAMAGE_W:-10000}"
export CRITIC_WARMUP=0
TAG="s2_dmg${DAMAGE_W}_lr${LR}"
bash scripts/run_stage2_pilot.sh "$@" || exit 1
TAG="$TAG" bash scripts/run_stage2_eval.sh "$@" || exit 1
TAG="$TAG" UPDATES="50 100 150" bash scripts/run_stage2_eval_trend.sh "$@"
