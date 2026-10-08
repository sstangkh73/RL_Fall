#!/usr/bin/env bash
# FGU noise floor: paired eval of earlier S1 checkpoints (in the "s2" slot) against the
# S1 update-200 reference. Measures how much false give-up appears from ordinary
# checkpoint-to-checkpoint drift of S1 training itself, with no S2 reward at all.
# Usage: [UPDATES="125 150 175"] scripts/run_s1_fgu_noise_floor.sh [seed ...]
#        writes results/stage2/fgu_noise_floor/seed_<S>/s1_update_<N>_vs_200.json
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SEEDS=("${@:-63001 63002 63003}")
read -r -a SEEDS <<< "${SEEDS[*]}"
UPDATES="${UPDATES:-125 150 175}"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
for SEED in "${SEEDS[@]}"; do
  S1=$(ls -td results/stage1_v1_0/seed_$SEED/push_0.12_hard0.5_posture1.0_natural4_r2/3d_* | head -1)
  OUT=results/stage2/fgu_noise_floor/seed_$SEED
  mkdir -p "$OUT"
  for U in $UPDATES; do
    echo "=== S1 noise floor seed $SEED update $U vs 200: $S1 $(date '+%F %T')"
    "$PY" scripts/stage2_eval.py "$S1" --s1-run "$S1" --s2-update "$U" --s1-update 200 \
        --out "$OUT/s1_update_${U}_vs_200.json" || exit 1
  done
done
echo "=== S1 noise floor done $(date '+%F %T')"
