#!/usr/bin/env bash
# 1-update smoke test of the S2 KL anchor on the real S1 checkpoint (output to /tmp).
cd /mnt/c/RL_Fall
S1=$(ls -td ~/RL_Fall/results/stage1_v1_0/seed_63001/push_0.12_hard0.5_posture1.0_natural4_r2/3d_* | head -1)
PYTHONPATH=src ~/venvs/rl_fall/bin/python -m rl_fall.train --output /tmp/anchor_smoke --environment 3d \
  --body v1_0 --mode balance --n-envs 8 --threads 4 --warmup-updates 0 --measured-updates 2 \
  --max-push-impulse 0.08 --hard-push-fraction 0.5 --hard-push-range 0.15 0.25 --posture-weight 1.0 \
  --posture-version 4 --natural-stance --capture-point-weight 10 --fall-continue-s 2.5 --damage-weight 10000 \
  --init-checkpoint "$S1/checkpoint.zip" --anchor-coef 1.0 --anchor-checkpoint "$S1/checkpoint.zip" \
  --stage S2_recover_or_fall > /tmp/anchor_smoke.out 2>&1
echo "exit $?"; tail -5 /tmp/anchor_smoke.out
cat "$(ls -td /tmp/anchor_smoke/3d_* | head -1)/updates.csv" | cut -d, -f1-3,14-
