#!/usr/bin/env bash
# Run scripts/diag_s2_obsnorm.py for each seed (S2 latest run vs natural4_r2).
# Usage: [TAG=s2_dmg10000] [UPDATE=200] scripts/run_diag_s2_obsnorm.sh [seed ...]
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SEEDS=("${@:-63001 63002 63003}")
read -r -a SEEDS <<< "${SEEDS[*]}"
TAG="${TAG:-s2_dmg10000}"
UPDATE="${UPDATE:-200}"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
export PYTHONPATH="$PWD/src"
for SEED in "${SEEDS[@]}"; do
  S1=$(ls -td results/stage1_v1_0/seed_$SEED/push_0.12_hard0.5_posture1.0_natural4_r2/3d_* | head -1)
  S2=$(ls -td results/stage2/seed_$SEED/push_0.08_hard0.5_posture1.0_${TAG}/3d_* | head -1)
  echo "=== obsnorm diag seed $SEED update $UPDATE: $S2 $(date '+%F %T')"
  "$PY" scripts/diag_s2_obsnorm.py "$S2" --s1-run "$S1" --s2-update "$UPDATE"
done
