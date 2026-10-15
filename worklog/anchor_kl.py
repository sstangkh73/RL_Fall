"""Print anchor_* columns of S2 anchor runs at a few updates.
Usage: python worklog/anchor_kl.py [tag]   (run from ~/RL_Fall)
"""
import csv
import glob
import sys

tag = sys.argv[1] if len(sys.argv) > 1 else "s2_dmg10000_anc1.0"
for f in sorted(glob.glob(f"results/stage2/seed_*/push_*_{tag}/3d_*/updates.csv")):
    rows = list(csv.DictReader(open(f)))
    keys = [k for k in rows[0] if k.startswith("anchor") or k in ("ep_rew_mean", "approx_kl")]
    print(f)
    for i in (0, 49, 99, 149, len(rows) - 1):
        if i < len(rows):
            print(" ", i + 1, {k: rows[i][k] for k in keys})
