#!/usr/bin/env bash
# The v1.0 S1 recipe (rerunnable; resumes after interruptions).
# Usage: scripts/run_stage1_v1_recipe.sh [seed ...]   (default 63002 63003)
#   A  posture v1 2.0, push <= 0.12, 200 updates (from scratch)
#   B  + 50% step-requiring pushes 0.13-0.25, 300 updates
#   CP + capture-point bonus 10, log-std -1.0, 150 updates
#   R1 natural stance rule (v3, weight 1.0) + relaxed starts, hard 0.08-0.15, 200 updates
#   R2 same with hard 0.13-0.25, 200 updates
# 8 Oct: R1/R2 moved from posture v2 (cost capped at 18 cm drift; seed 63002 drifted
# 29.8 cm) to v3 (cost keeps growing, reward stays positive). The v2 runs are kept
# under the natural_r1/natural_r2 tags; A, B and CP are unchanged and are reused.
# Seed 63001 also had a 500-update continuation between B and CP that changed nothing; omitted.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PYTHONPATH=$PWD/src
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
OUT=results/stage1_v1_0
latest() { ls -td "$OUT/seed_$1/$2"/3d_* | head -1; }
SEEDS=("${@:-63002 63003}")
read -r -a SEEDS <<< "${SEEDS[*]}"
for SEED in "${SEEDS[@]}"; do
  env BODY=v1_0 POSTURE=2.0 scripts/run_stage1.sh $SEED 200 0.12
  A=$(latest $SEED push_0.12_posture2.0)
  env BODY=v1_0 HARD=0.5 POSTURE=2.0 INIT_CHECKPOINT="$A/checkpoint.zip" scripts/run_stage1.sh $SEED 300 0.12
  B=$(latest $SEED push_0.12_hard0.5_posture2.0)
  env BODY=v1_0 HARD=0.5 POSTURE=2.0 CP=10 INIT_CHECKPOINT="$B/checkpoint.zip" LOG_STD=-1.0 TAG=cp10 \
      scripts/run_stage1.sh $SEED 150 0.12
  CPR=$(latest $SEED push_0.12_hard0.5_posture2.0_cp10)
  env BODY=v1_0 POSTURE=1.0 POSTURE_VERSION=3 NATURAL=1 CP=10 HARD=0.5 HARD_RANGE="0.08 0.15" \
      INIT_CHECKPOINT="$CPR/checkpoint.zip" LOG_STD=-1.0 TAG=natural3_r1 scripts/run_stage1.sh $SEED 200 0.12
  R1=$(latest $SEED push_0.12_hard0.5_posture1.0_natural3_r1)
  env BODY=v1_0 POSTURE=1.0 POSTURE_VERSION=3 NATURAL=1 CP=10 HARD=0.5 HARD_RANGE="0.13 0.25" \
      INIT_CHECKPOINT="$R1/checkpoint.zip" TAG=natural3_r2 scripts/run_stage1.sh $SEED 200 0.12
  R2=$(latest $SEED push_0.12_hard0.5_posture1.0_natural3_r2)
  if [ ! -f "$R2/survival_curve.json" ]; then
    echo "=== survival seed $SEED $R2"
    $PY scripts/stage1_survival.py "$R2" --updates 200 --impulses 0.03 0.05 0.08 0.10 0.12 0.15 0.20 2>&1 | grep -v -i warn
  fi
  echo "=== seed $SEED done $(date '+%F %T')"
done
echo "=== seeds done $(date '+%F %T')"
