#!/usr/bin/env bash
# S2 with a KL anchor to the frozen M1 (S1 natural4_r2) policy on recoverable,
# pre-fall states, to retain recovery while damage fine-tuning adapts elsewhere.
# Base recipe: recoverable U(0, 0.08), damage weight 10000, no critic warm-up,
# unchanged S1 learning rate. Train, paired eval at 200, then trend at 50/100/150.
# Usage: [ANCHOR=1.0] [ANCHOR_EPOCHS=5] scripts/run_stage2_anchor.sh [seed ...]
# (the anchor runs as its own Adam phase, so ANCHOR_EPOCHS, not ANCHOR, sets its strength)
# Results: results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000_anc1.0/
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export RECOVERABLE_MAX=0.08
export DAMAGE_W=10000
export CRITIC_WARMUP=0
export LR=
export ANCHOR="${ANCHOR:-1.0}"
export ANCHOR_EPOCHS="${ANCHOR_EPOCHS:-}"
TAG="s2_dmg10000_anc${ANCHOR}"
if [ -n "$ANCHOR_EPOCHS" ]; then TAG="${TAG}_ae${ANCHOR_EPOCHS}"; fi
bash scripts/run_stage2_pilot.sh "$@" || exit 1
TAG="$TAG" bash scripts/run_stage2_eval.sh "$@" || exit 1
TAG="$TAG" UPDATES="50 100 150" bash scripts/run_stage2_eval_trend.sh "$@"
