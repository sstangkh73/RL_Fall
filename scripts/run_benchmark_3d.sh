#!/usr/bin/env bash
# Linux 3D benchmark pipeline: tests -> P1 convergence -> P2 physics/PPO -> selection -> P3.
# Pass --with-p4 to also run the P4 learning-quality gate. Rerunning resumes P3 by
# skipping complete manifests. Usage: scripts/run_benchmark_3d.sh [--with-p4]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
OUT="results/benchmark_3d"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"

step() { echo; echo "=== $(date '+%F %T') $*"; }

step "pytest"
"$PY" -m pytest
step "system snapshot"
"$PY" benchmarks/system_probe.py --output "$OUT/system_snapshot.json" > /dev/null
if [ ! -f "$OUT/physics_validation.json" ]; then
    step "P1-3D numerical convergence"
    "$PY" benchmarks/validate_physics_3d.py > /dev/null
fi
if [ ! -f "$OUT/physics/manifest.json" ]; then
    step "P2-3D physics 20,000 x 3"
    "$PY" benchmarks/physics_3d.py --transitions 20000 --repetitions 3
fi
if [ ! -f "$OUT/P2_selection.json" ]; then
    step "P2-3D PPO screening (warm-up 10 + measured 20)"
    "$PY" benchmarks/training.py screen --environment 3d --devices cpu cuda \
        --env-counts 1 4 8 --threads 1 4
    step "P2-3D selection"
    "$PY" benchmarks/select_configuration.py --environment 3d > /dev/null
    cat "$OUT/P2_selection.md"
fi

read -r ENVS THREADS < <("$PY" -c "import json; p=json.load(open('configs/benchmark/p3_candidate_3d.json')); print(p['primary_environment_count'], p['learner_threads'])")
step "P3-3D confirmation: envs=$ENVS threads=$THREADS"
"$PY" benchmarks/training.py confirm --environment 3d --env-counts "$ENVS" \
    --primary-env-count "$ENVS" --threads "$THREADS"

if [ "${1:-}" = "--with-p4" ]; then
    step "P4-3D learning quality"
    "$PY" benchmarks/training.py quality --environment 3d --n-envs "$ENVS" --threads "$THREADS"
fi

step "report"
"$PY" benchmarks/report.py --input "$OUT" --output "$OUT/benchmark_report.md"
step "done"
