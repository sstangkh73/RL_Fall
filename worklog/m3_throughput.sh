#!/usr/bin/env bash
# Print throughput/transitions from manifests of S1 recipe + S2 runs (M3 estimate input).
cd ~/RL_Fall
for f in results/stage1_v1_0/seed_*/*/3d_*/manifest.json results/stage2/seed_*/*/3d_*/manifest.json; do
  ~/venvs/rl_fall/bin/python /mnt/c/RL_Fall/worklog/m3_manifest.py "$f"
done
nproc; lscpu | grep 'Model name'
