#!/bin/bash
# S1 v1.0 recipe (A -> B -> CP -> R1 -> R2 + survival eval) for several seeds on one LANTA CPU node.
# Each seed runs scripts/run_stage1_v1_recipe.sh in the background (8 envs + 4 learner
# threads per run); a node holds ~10 seeds side by side
# (each run uses ~12 threads; more than 128 threads in total oversubscribes the node). The recipe is rerunnable, so a
# job that hits the time limit can simply be resubmitted and resumes from its checkpoints.
# Usage: sbatch [--export=ALL,SEEDS="63001 63002 63003"] scripts/lanta/s1_recipe.sbatch
# Not submitted yet: replace the account before the first submission.
#SBATCH -J rlfall-s1
#SBATCH -p compute
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH -c 128
#SBATCH -t 12:00:00
#SBATCH -A <project-account>
#SBATCH -o logs/%x-%j.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "${BASH_SOURCE[0]}")/../..}"
export PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
SEEDS="${SEEDS:-63001 63002 63003}"
mkdir -p logs
for SEED in $SEEDS; do
  bash scripts/run_stage1_v1_recipe.sh "$SEED" > "logs/s1_recipe_${SEED}.log" 2>&1 &
done
wait
echo "=== S1 recipe done $(date '+%F %T') seeds: $SEEDS"
