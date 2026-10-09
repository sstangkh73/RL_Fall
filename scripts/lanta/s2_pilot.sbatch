#!/bin/bash
# S2 (recover or fall) fine-tune + paired evaluation for several seeds on one LANTA CPU node.
# Needs the S1 natural4_r2 runs of the same seeds (scripts/lanta/s1_recipe.sbatch).
# Settings pass through to scripts/run_stage2_pilot.sh (DAMAGE_W, UPDATES, CRITIC_WARMUP, LR,
# RECOVERABLE_MAX, ANCHOR, ANCHOR_EPOCHS) and RECOVERABLE_MAX to scripts/run_stage2_eval.sh.
# Usage: sbatch [--export=ALL,SEEDS="63001 63002 63003",DAMAGE_W=10000] scripts/lanta/s2_pilot.sbatch
# Anchored recipe (scripts/run_stage2_anchor.sh): --export=ALL,ANCHOR=1.0,ANCHOR_EPOCHS=1[,RECOVERABLE_MAX=0.12]
# Not submitted yet: replace the account before the first submission.
#SBATCH -J rlfall-s2
#SBATCH -p compute
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH -c 128
#SBATCH -t 04:00:00
#SBATCH -A <project-account>
#SBATCH -o logs/%x-%j.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "${BASH_SOURCE[0]}")/../..}"
export PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
SEEDS="${SEEDS:-63001 63002 63003}"
mkdir -p logs
# The eval must read the run tag the pilot writes (same rule as run_stage2_pilot.sh).
TAG="s2_dmg${DAMAGE_W:-10000}"
if [ "${CRITIC_WARMUP:-0}" != "0" ]; then TAG="${TAG}_cw${CRITIC_WARMUP}"; fi
if [ -n "${LR:-}" ]; then TAG="${TAG}_lr${LR}"; fi
if [ -n "${ANCHOR:-}" ]; then TAG="${TAG}_anc${ANCHOR}"; fi
if [ -n "${ANCHOR_EPOCHS:-}" ]; then TAG="${TAG}_ae${ANCHOR_EPOCHS}"; fi
export TAG
for SEED in $SEEDS; do
  ( bash scripts/run_stage2_pilot.sh "$SEED" && bash scripts/run_stage2_eval.sh "$SEED" ) \
      > "logs/s2_pilot_${SEED}.log" 2>&1 &
done
wait
echo "=== S2 done $(date '+%F %T') seeds: $SEEDS"
