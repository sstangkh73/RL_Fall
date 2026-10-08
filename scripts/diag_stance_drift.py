"""Foot drift over time in the no-push stance check, per episode.

Prints drift (cm) at 0.25 s intervals for the same 12 relaxed starts that
stage1_survival.stance_check uses, plus the episode's (unused) push_start, so one
can see whether the drift builds up before or after the time the penalty stops.

Usage: python scripts/diag_stance_drift.py RUN_DIR [--update 200] [--seconds 2.0]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl_fall.env3d import RLFall3DEnv

SEED_BASE = 9000  # same as stage1_survival.stance_check


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--update", type=int, default=200)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--episodes", type=int, default=12)
    args = parser.parse_args()
    torch.set_num_threads(4)
    manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
    kwargs = {"condition": manifest.get("condition", "A"), "body": manifest.get("body", "v1_0"),
              "mode": "balance", "max_push_impulse": 0.45,
              "natural_stance": bool(manifest.get("natural_stance"))}
    model = PPO.load(args.run_dir / f"checkpoint_update_{args.update}.zip", device="cpu")
    normalizer = args.run_dir / f"vecnormalize_update_{args.update}.pkl"
    finals = []
    for index in range(args.episodes):
        env = RLFall3DEnv(seed=SEED_BASE + 500 + index, **kwargs)
        venv = VecNormalize.load(str(normalizer), DummyVecEnv([lambda: env]))
        venv.training = False
        venv.seed(SEED_BASE + 500 + index)
        observation = venv.reset()
        env.push_force_world[:] = 0.0
        steps = int(args.seconds / env.config.control_dt)
        every = max(1, int(0.25 / env.config.control_dt))
        trace = []
        for step in range(1, steps + 1):
            action, _ = model.predict(observation, deterministic=True)
            observation, _, _, _ = venv.step(action)
            if step % every == 0:
                trace.append(np.linalg.norm(env._feet_vector() - env._nominal_feet) * 100)
        finals.append(trace[-1])
        print(f"ep {index:2d} push_start {env.push_start:.2f}s  drift cm: "
              + " ".join(f"{d:5.1f}" for d in trace))
    print(f"median final drift {np.median(finals):.1f} cm")


if __name__ == "__main__":
    main()
