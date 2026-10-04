"""Stage-1 survival curve: fraction of 10 s balance episodes survived at fixed push
impulses, for the passive stance (zero action) and for saved S1 checkpoints.

Usage: python scripts/stage1_survival.py RUN_DIR [--updates 500 1500] [--scenarios 24]
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

IMPULSES = (0.05, 0.08, 0.10, 0.12, 0.15, 0.20)
SEED_BASE = 9000  # disjoint from training and checkpoint-evaluation seeds


def _fix_impulse(env: RLFall3DEnv, impulse: float) -> None:
    # Keep the sampled direction, timing and duration; replace only the magnitude.
    mass = float(np.sum(env.model.body_mass))
    direction = env.push_force_world / max(float(np.linalg.norm(env.push_force_world)), 1e-9)
    env.push_force_world = impulse * mass * np.sqrt(9.81 * 1.2) / env.push_duration * direction
    env.push_impulse = impulse


def survival(policy: tuple[PPO, Path] | None, impulse: float, scenarios: int) -> float:
    survived = 0
    for index in range(scenarios):
        env = RLFall3DEnv(condition="A", seed=SEED_BASE + index, body="v0_2",
                          mode="balance", max_push_impulse=0.45)
        if policy is None:
            env.reset(seed=SEED_BASE + index)
            _fix_impulse(env, impulse)
            done = False
            while not done:
                _, _, done, _, info = env.step(np.zeros(16, dtype=np.float32))
        else:
            model, normalizer = policy
            venv = VecNormalize.load(str(normalizer), DummyVecEnv([lambda: env]))
            venv.training = False
            venv.seed(SEED_BASE + index)
            observation = venv.reset()
            _fix_impulse(env, impulse)
            done = np.array([False])
            while not done[0]:
                action, _ = model.predict(observation, deterministic=True)
                observation, _, done, infos = venv.step(action)
            info = infos[0]
        survived += int(not info["fallen"])
    return survived / scenarios


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--updates", nargs="+", type=int, default=())
    parser.add_argument("--scenarios", type=int, default=24)
    args = parser.parse_args()
    torch.set_num_threads(4)
    rows = {"impulses": list(IMPULSES), "scenarios": args.scenarios,
            "passive": [survival(None, i, args.scenarios) for i in IMPULSES]}
    for update in args.updates:
        model = PPO.load(args.run_dir / f"checkpoint_update_{update}.zip", device="cpu")
        normalizer = args.run_dir / f"vecnormalize_update_{update}.pkl"
        rows[f"update_{update}"] = [
            survival((model, normalizer), i, args.scenarios) for i in IMPULSES
        ]
    (args.run_dir / "survival_curve.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    print("impulse".ljust(14), " ".join(f"{i:>5.2f}" for i in IMPULSES))
    for name, values in rows.items():
        if name not in ("impulses", "scenarios"):
            print(name.ljust(14), " ".join(f"{v:>5.2f}" for v in values))


if __name__ == "__main__":
    main()
