#!/usr/bin/env bash
# Paired S2 / S1 / passive evaluation of earlier S2 checkpoints, to see whether the
# recoverable-push survival drop (false give-up) appears at once or grows with training.
# Usage: [TAG=s2_dmg10000] [UPDATES="0 50 100 150"] scripts/run_stage2_eval_trend.sh [seed ...]
#        writes <S2 run>/s2_eval_update_<N>.json (s2_eval.json for update 200 is untouched)
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SEEDS=("${@:-63001 63002 63003}")
read -r -a SEEDS <<< "${SEEDS[*]}"
TAG="${TAG:-s2_dmg10000}"
UPDATES="${UPDATES:-0 50 100 150}"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
for SEED in "${SEEDS[@]}"; do
  S1=$(ls -td results/stage1_v1_0/seed_$SEED/push_0.12_hard0.5_posture1.0_natural4_r2/3d_* | head -1)
  S2=$(ls -td results/stage2/seed_$SEED/push_0.08_hard0.5_posture1.0_${TAG}/3d_* | head -1)
  for U in $UPDATES; do
    echo "=== S2 eval seed $SEED update $U: $S2 vs $S1 $(date '+%F %T')"
    "$PY" scripts/stage2_eval.py "$S2" --s1-run "$S1" --s2-update "$U" --s1-update 200 \
        --out "$S2/s2_eval_update_$U.json" || exit 1
  done
done
echo "=== S2 eval trend done $(date '+%F %T')"
