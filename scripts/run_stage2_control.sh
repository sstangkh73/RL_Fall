#!/usr/bin/env bash
# Control for the S2 false give-up: the same S2 fine-tune (pushes U(0,0.08) / U(0.15,0.25),
# 2.5 s run-on after a fall, lr 1e-4, 200 updates) but with NO damage cost (DAMAGE_W=0).
# If this run also loses recoverable-push survival against natural4_r2, the drop comes from
# continued PPO training / the push mix, not from the damage reward.
# Train, paired eval at update 200, then the checkpoint trend (50/100/150).
# Usage: scripts/run_stage2_control.sh [seed ...]   (results tag s2_dmg0)
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export DAMAGE_W=0
export CRITIC_WARMUP=0
export LR=
TAG="s2_dmg0"
bash scripts/run_stage2_pilot.sh "$@" || exit 1
TAG="$TAG" bash scripts/run_stage2_eval.sh "$@" || exit 1
TAG="$TAG" UPDATES="50 100 150" bash scripts/run_stage2_eval_trend.sh "$@"
