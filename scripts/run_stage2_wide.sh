#!/usr/bin/env bash
# S2 pilot with the recoverable pushes widened to U(0, 0.12), the same range the M1 policy
# (natural4_r2) was trained on (hypothesis c). The base S2 recipe drew no pushes between 0.08
# and 0.15, and its recoverable-survival loss sits mostly at 0.08, the top of that range.
# Everything else is the base recipe (DAMAGE_W=10000, lr 1e-4, no warm-up, unrecoverable U(0.15, 0.25)).
# Train, paired eval at update 200, then the checkpoint trend (50/100/150).
# Usage: scripts/run_stage2_wide.sh [seed ...]
#        results under results/stage2/seed_*/push_0.12_hard0.5_posture1.0_s2_dmg10000/
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export RECOVERABLE_MAX=0.12
export DAMAGE_W=10000
export CRITIC_WARMUP=0
export LR=
TAG="s2_dmg${DAMAGE_W}"
bash scripts/run_stage2_pilot.sh "$@" || exit 1
TAG="$TAG" bash scripts/run_stage2_eval.sh "$@" || exit 1
TAG="$TAG" UPDATES="50 100 150" bash scripts/run_stage2_eval_trend.sh "$@"
