#!/bin/bash
# Check whether the s2ctrl job is still alive and how far it has got.
cd ~/RL_Fall
echo "now: $(date '+%F %T')"
echo "heartbeat: $(date -d @"$(cat /mnt/c/RL_Fall/auto-loop/reports/jobs/20261008-220533-s2ctrl.heartbeat)" '+%F %T')"
pgrep -af 'train.py|run_stage2|stage2_eval' | cut -c1-150
for d in results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg0/*/; do
  echo "== $d"
  [ -f "$d/updates.csv" ] && echo "updates.csv mtime $(date -r "$d/updates.csv" '+%F %T') last=$(tail -n 1 "$d/updates.csv" | cut -d, -f2)"
done
