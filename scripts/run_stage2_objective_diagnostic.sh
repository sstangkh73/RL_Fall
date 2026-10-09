#!/usr/bin/env bash
# Predeclared diagnostic only: frozen coef1 final200, independent reset seeds,
# 192 recoverable + 192 hard scenarios per policy/seed. No training/gate change.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
SEEDS=(63001 63002 63003)
S2_TIMES=(20261009T144426 20261009T155457 20261009T171929)
S1_TIMES=(20261008T100414 20261008T112408 20261008T124330)
for i in 0 1 2; do
  seed="${SEEDS[$i]}"
  s2="results/stage2/seed_${seed}/push_0.08_hard0.5_posture1.0_s2_dmg10000_anc1.0_objective/3d_A_env8_subproc_cpu_seed${seed}_t4_${S2_TIMES[$i]}"
  s1="results/stage1_v1_0/seed_${seed}/push_0.12_hard0.5_posture1.0_natural4_r2/3d_A_env8_subproc_cpu_seed${seed}_t4_${S1_TIMES[$i]}"
  "$PY" scripts/stage2_diagnostics.py "$s2" --s1-run "$s1" --seed-base 19000 --episodes-scale 4 \
    --out-dir "results/stage2_diagnostics/joint_coef1_seedbase19000_scale4/seed_${seed}"
done
