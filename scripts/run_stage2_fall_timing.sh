#!/usr/bin/env bash
# Diagnostic only: push-to-fall timing on the S2 gate scenarios for the final200
# S2 runs of joint10000 and damage20000 (all three seeds), against pinned S1 update200.
# Output: results/stage2_diagnostics/fall_timing/<recipe>/seed_<seed>.json (not a gate).
set -euo pipefail
cd "$(dirname "$0")/.."
source ~/venvs/rl_fall/bin/activate

declare -A S1=(
  [63001]=results/stage1_v1_0/seed_63001/push_0.12_hard0.5_posture1.0_natural4_r2/3d_A_env8_subproc_cpu_seed63001_t4_20261008T100414
  [63002]=results/stage1_v1_0/seed_63002/push_0.12_hard0.5_posture1.0_natural4_r2/3d_A_env8_subproc_cpu_seed63002_t4_20261008T112408
  [63003]=results/stage1_v1_0/seed_63003/push_0.12_hard0.5_posture1.0_natural4_r2/3d_A_env8_subproc_cpu_seed63003_t4_20261008T124330
)
for recipe in s2_dmg10000_anc1.0_objective s2_dmg20000_anc1.0_objective; do
  for seed in 63001 63002 63003; do
    runs=(results/stage2/seed_${seed}/push_0.08_hard0.5_posture1.0_${recipe}/3d_*/)
    if [ "${#runs[@]}" -ne 1 ]; then
      echo "expected exactly one run for $recipe seed $seed, found ${#runs[@]}" >&2
      exit 1
    fi
    out=results/stage2_diagnostics/fall_timing/${recipe}/seed_${seed}.json
    echo "=== $(date '+%F %T') $recipe seed $seed ${runs[0]}"
    python scripts/stage2_fall_timing.py "${runs[0]%/}" --s1-run "${S1[$seed]}" --out "$out" \
      | grep -A5 '"paired_delay_s2_minus_passive_s"\|"s2_corr' || true
  done
done
