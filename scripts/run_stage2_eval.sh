#!/usr/bin/env bash
# Paired S2 / S1 / passive evaluation (scripts/stage2_eval.py) for the latest S2 pilot run
# of each seed against its M1 policy (natural4_r2, update 200).
# Usage: [TAG=s2_dmg10000] [RECOVERABLE_MAX=0.08] [UPDATE=200] scripts/run_stage2_eval.sh [seed ...]
#        (default seeds 63001 63002 63003); writes <S2 run>/s2_eval.json
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SEEDS=("${@:-63001 63002 63003}")
read -r -a SEEDS <<< "${SEEDS[*]}"
TAG="${TAG:-s2_dmg10000}"
UPDATE="${UPDATE:-200}"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
for SEED in "${SEEDS[@]}"; do
  S1=$(ls -td results/stage1_v1_0/seed_$SEED/push_0.12_hard0.5_posture1.0_natural4_r2/3d_* | head -1)
  S2=$(ls -td results/stage2/seed_$SEED/push_${RECOVERABLE_MAX:-0.08}_hard0.5_posture1.0_${TAG}/3d_* | head -1)
  echo "=== S2 eval seed $SEED: $S2 vs $S1 $(date '+%F %T')"
  "$PY" scripts/stage2_eval.py "$S2" --s1-run "$S1" --s2-update "$UPDATE" --s1-update 200 || exit 1
done
echo "=== S2 eval done $(date '+%F %T')"
