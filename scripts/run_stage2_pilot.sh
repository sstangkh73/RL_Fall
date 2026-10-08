#!/usr/bin/env bash
# S2 pilot (recover or fall): fine-tune the M1 policy (natural4_r2, update 200).
# Usage: [DAMAGE_W=10000] [UPDATES=200] [CRITIC_WARMUP=0] scripts/run_stage2_pilot.sh [seed ...]
#        (default seeds 63001 63002 63003)
# Same S1 shaping (natural stance v4, capture point) plus:
#   pushes half recoverable U(0, 0.08) and half unrecoverable U(0.15, 0.25)
#   (v4 S1 survives 85-90% at 0.08 and 2-8% at 0.15),
#   a fall no longer ends the episode: it runs on 2.5 s so the impact is scored,
#   weighted damage (head 5, torso 2, limbs 1) costs DAMAGE_W per unit
#   (S1 falls score ~0.0015 weighted, so 10000 makes a typical fall cost ~15 reward).
# Rerunnable: complete runs are skipped and interrupted ones resume.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SEEDS=("${@:-63001 63002 63003}")
read -r -a SEEDS <<< "${SEEDS[*]}"
DAMAGE_W="${DAMAGE_W:-10000}"
UPDATES="${UPDATES:-200}"
# CRITIC_WARMUP=N freezes the actor for the first N updates so the S1 critic can learn
# the post-fall states and damage cost before the policy moves (tag gets _cw<N>).
CRITIC_WARMUP="${CRITIC_WARMUP:-0}"
TAG="s2_dmg${DAMAGE_W}"
if [ "$CRITIC_WARMUP" != "0" ]; then TAG="${TAG}_cw${CRITIC_WARMUP}"; fi
for SEED in "${SEEDS[@]}"; do
  S1=$(ls -td results/stage1_v1_0/seed_$SEED/push_0.12_hard0.5_posture1.0_natural4_r2/3d_* | head -1)
  env BODY=v1_0 POSTURE=1.0 POSTURE_VERSION=4 NATURAL=1 CP=10 HARD=0.5 HARD_RANGE="0.15 0.25" \
      FALL_CONTINUE=2.5 DAMAGE_W="$DAMAGE_W" OUT_ROOT=results/stage2 STAGE=S2_recover_or_fall \
      INIT_CHECKPOINT="$S1/checkpoint.zip" TAG="$TAG" CRITIC_WARMUP="$CRITIC_WARMUP" \
      scripts/run_stage1.sh "$SEED" "$UPDATES" 0.08
  echo "=== S2 seed $SEED done $(date '+%F %T')"
done
echo "=== S2 seeds done $(date '+%F %T')"
