"""Tabulate S2 vs S1 survival per recoverable impulse (0.05 / 0.08) for every S2 run at update 200."""
import glob
import json

for path in sorted(glob.glob("results/stage2/seed_*/push_*/3d_*/s2_eval.json")):
    d = json.load(open(path))
    tag = path.split("/")[3].replace("push_0.08_hard0.5_posture1.0_", "")
    seed = path.split("/")[2]
    cells = []
    for imp in ("0.05", "0.08"):
        p = d["per_impulse"][imp]
        cells.append(f"{imp}: S2 {p['s2']['survival']:.0%} / S1 {p['s1']['survival']:.0%}")
    print(f"{seed} {tag:22s} FGU={d['false_give_up']:.3f} | " + " | ".join(cells))
