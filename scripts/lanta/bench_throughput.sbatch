#!/bin/bash
# Measure per-node training throughput on a LANTA CPU node (input to the M3 estimate).
# Runs K copies of the S1 trainer side by side (8 envs + 4 learner threads each, the same
# settings as every recipe run) for a short fixed number of updates, then sums the
# steady_transitions_per_second of their manifests.
# Usage: sbatch [--export=ALL,K=10,UPDATES=20] scripts/lanta/bench_throughput.sbatch
# Not submitted yet: replace the account before the first submission.
#SBATCH -J rlfall-bench
#SBATCH -p compute
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH -c 128
#SBATCH -t 01:00:00
#SBATCH -A <project-account>
#SBATCH -o logs/%x-%j.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "${BASH_SOURCE[0]}")/../..}"
export PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
K="${K:-10}"
UPDATES="${UPDATES:-20}"
OUT_ROOT="results/lanta_bench/k${K}_${SLURM_JOB_ID:-local}"
for I in $(seq 1 "$K"); do
  env BODY=v1_0 POSTURE=2.0 OUT_ROOT="$OUT_ROOT" EVERY="$UPDATES" \
      scripts/run_stage1.sh $((70000 + I)) "$UPDATES" 0.12 &
done
wait
"$PY" - "$OUT_ROOT" <<'PY'
import glob, json, sys
rates = [json.load(open(p))["steady_transitions_per_second"]
         for p in glob.glob(f"{sys.argv[1]}/seed_*/*/3d_*/manifest.json")]
print(f"runs={len(rates)} per_run_mean={sum(rates)/max(len(rates),1):.0f} t/s node_total={sum(rates):.0f} t/s")
PY
