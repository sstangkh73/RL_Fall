"""Stage-1 survival curve: fraction of 10 s balance episodes survived at fixed push
impulses, for the passive stance (zero action) and for saved S1 checkpoints, plus
the fraction of episodes with at least one recovery step.

A step is a foot leaving the floor for >= 0.15 s and landing >= 10 cm from where
it lifted off. The body, condition and push settings come from the run manifest.

Usage: python scripts/stage1_survival.py RUN_DIR [--updates 50 150] [--scenarios 24]
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

IMPULSES = (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25)
SEED_BASE = 9000  # disjoint from training and checkpoint-evaluation seeds
STEP_MIN_AIR_STEPS = 8      # 0.16 s at 50 Hz control
STEP_MIN_DISPLACEMENT_M = 0.10


def _fix_impulse(env: RLFall3DEnv, impulse: float) -> None:
    # Keep the sampled direction, timing and duration; replace only the magnitude.
    mass = float(np.sum(env.model.body_mass))
    direction = env.push_force_world / max(float(np.linalg.norm(env.push_force_world)), 1e-9)
    env.push_force_world = impulse * mass * np.sqrt(9.81 * 1.2) / env.push_duration * direction
    env.push_impulse = impulse


class StepCounter:
    def __init__(self, env: RLFall3DEnv) -> None:
        self.env = env
        self.feet = sorted(env.foot_geom_ids)
        self.air = [0] * len(self.feet)
        self.liftoff = [None] * len(self.feet)
        self.steps = 0

    def update(self) -> None:
        touching = set()
        for index in range(self.env.data.ncon):
            contact = self.env.data.contact[index]
            touching.update((int(contact.geom1), int(contact.geom2)))
        for k, geom in enumerate(self.feet):
            position = self.env.data.geom_xpos[geom][:2].copy()
            if geom in touching:
                if (self.air[k] >= STEP_MIN_AIR_STEPS and self.liftoff[k] is not None
                        and np.linalg.norm(position - self.liftoff[k]) >= STEP_MIN_DISPLACEMENT_M):
                    self.steps += 1
                self.air[k], self.liftoff[k] = 0, position
            else:
                self.air[k] += 1


def run_episode(kwargs: dict[str, object], policy: tuple[PPO, Path] | None,
                impulse: float, seed: int) -> tuple[bool, int]:
    env = RLFall3DEnv(seed=seed, **kwargs)
    if policy is None:
        env.reset(seed=seed)
    else:
        model, normalizer = policy
        venv = VecNormalize.load(str(normalizer), DummyVecEnv([lambda: env]))
        venv.training = False
        venv.seed(seed)
        observation = venv.reset()
    _fix_impulse(env, impulse)
    counter = StepCounter(env)
    done = False
    while not done:
        if policy is None:
            _, _, done, _, info = env.step(np.zeros(env.action_space.shape, dtype=np.float32))
        else:
            action, _ = model.predict(observation, deterministic=True)
            observation, _, dones, infos = venv.step(action)
            done, info = bool(dones[0]), infos[0]
        if not done:  # the vec env auto-resets on the terminal step
            counter.update()
    return not info["fallen"], counter.steps


def curve(kwargs: dict[str, object], policy: tuple[PPO, Path] | None,
          scenarios: int) -> dict[str, list[float]]:
    survival, stepping = [], []
    for impulse in IMPULSES:
        results = [run_episode(kwargs, policy, impulse, SEED_BASE + index)
                   for index in range(scenarios)]
        survival.append(sum(alive for alive, _ in results) / scenarios)
        stepping.append(sum(steps > 0 for _, steps in results) / scenarios)
    return {"survival": survival, "step_rate": stepping}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--updates", nargs="+", type=int, default=())
    parser.add_argument("--scenarios", type=int, default=24)
    args = parser.parse_args()
    torch.set_num_threads(4)
    manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
    kwargs = {"condition": manifest.get("condition", "A"),
              "body": manifest.get("body", "v0_2"), "mode": "balance",
              "max_push_impulse": 0.45}
    rows: dict[str, object] = {"impulses": list(IMPULSES), "scenarios": args.scenarios,
                               "body": kwargs["body"], "passive": curve(kwargs, None, args.scenarios)}
    for update in args.updates:
        model = PPO.load(args.run_dir / f"checkpoint_update_{update}.zip", device="cpu")
        normalizer = args.run_dir / f"vecnormalize_update_{update}.pkl"
        rows[f"update_{update}"] = curve(kwargs, (model, normalizer), args.scenarios)
    (args.run_dir / "survival_curve.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"body {kwargs['body']}; survival (stepping episodes) per impulse")
    print("impulse".ljust(14), " ".join(f"{i:>11.2f}" for i in IMPULSES))
    for name, values in rows.items():
        if isinstance(values, dict):
            print(name.ljust(14), " ".join(
                f"{s:>5.0%} ({t:>3.0%})" for s, t in zip(values["survival"], values["step_rate"])))


if __name__ == "__main__":
    main()
