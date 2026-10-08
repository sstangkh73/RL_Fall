import json
import sys

p = sys.argv[1]
m = json.load(open(p))
keys = ("transition", "second", "update", "wall", "n_envs", "threads", "cpu", "elapsed")
picked = {k: v for k, v in m.items() if any(s in k for s in keys) and not isinstance(v, (list, dict))}
print(p.split("results/")[1].rsplit("/manifest", 1)[0], m.get("status"), picked)
