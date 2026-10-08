#!/usr/bin/env bash
# Print S2 pilot training curves (selected columns every 20 updates) per seed.
cd ~/RL_Fall
for S in 63001 63002 63003; do
  R=$(ls -td results/stage2/seed_$S/*/3d_* | head -1)
  echo "=== $S $R"
  ls "$R"
  F="$R/updates.csv"
  [ -f "$F" ] || F=$(ls "$R"/*.csv | head -1)
  head -1 "$F" | tr ',' '\n' | nl | tr '\n' ' '; echo
  awk -F, 'NR==1 || (NR-1)%20==0 || NR==2' "$F"
done
