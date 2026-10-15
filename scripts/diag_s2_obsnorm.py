"""Does S2 lose recoverable-push survival through drifted observation statistics?

Runs the recoverable scenarios of stage2_eval with the S1 weights under the S1
normalizer and under the S2 normalizer, plus the S2 weights under both. If S1
weights + S2 normalizer already fall more, the drop comes from VecNormalize
statistics updated on post-fall (lying) observations, not from the policy update.
Usage: python scripts/diag_s2_obsnorm.py <s2_run> --s1-run <s1_run> [--s2-update 200]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stage2_eval import env_kwargs, load_policy, make_scenarios, run_episode  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("s2_run", type=Path)
    parser.add_argument("--s1-run", type=Path, required=True)
    parser.add_argument("--s2-update", type=int, default=200)
    parser.add_argument("--s1-update", type=int, default=200)
    args = parser.parse_args()

    manifest = json.loads((args.s1_run / "manifest.json").read_text())
    kwargs = env_kwargs(manifest, 2.5)
    s1_model, s1_norm = load_policy(args.s1_run, args.s1_update, kwargs)
    s2_model, s2_norm = load_policy(args.s2_run, args.s2_update, kwargs)

    mean_shift = np.abs(s2_norm.obs_rms.mean - s1_norm.obs_rms.mean) / np.sqrt(
        s1_norm.obs_rms.var + 1e-8)
    var_ratio = s2_norm.obs_rms.var / (s1_norm.obs_rms.var + 1e-8)
    print(f"obs mean shift in S1 std units: median {np.median(mean_shift):.3f}, "
          f"max {mean_shift.max():.3f} (dim {int(mean_shift.argmax())})")
    print(f"obs var ratio S2/S1: median {np.median(var_ratio):.2f}, "
          f"min {var_ratio.min():.2f}, max {var_ratio.max():.2f}")
    print(f"return std S1 {np.sqrt(s1_norm.ret_rms.var).item():.2f}, "
          f"S2 {np.sqrt(s2_norm.ret_rms.var).item():.2f}")

    scenarios = [s for s in make_scenarios() if s["group"] == "recoverable"]
    combos = {"s1_weights+s1_norm": (s1_model, s1_norm),
              "s1_weights+s2_norm": (s1_model, s2_norm),
              "s2_weights+s1_norm": (s2_model, s1_norm),
              "s2_weights+s2_norm": (s2_model, s2_norm)}
    for name, policy in combos.items():
        fallen = [run_episode(kwargs, policy, s, 2.5)["fallen"] for s in scenarios]
        print(f"{name}: recoverable survival {1 - np.mean(fallen):.1%} "
              f"({len(fallen)} episodes)", flush=True)


if __name__ == "__main__":
    main()
