"""Stage-1 survival curve: fraction of 10 s balance episodes survived at fixed push
impulses, for the passive stance (zero action) and for saved S1 checkpoints, plus
the fraction of episodes with at least one recovery step.

A step is a foot leaving the floor for >= 0.15 s and landing >= 10 cm from where
it lifted off. The body and condition come from the run manifest. Push directions
are swept evenly around the body (scenario i uses direction i mod --directions);
seeds still vary push timing, duration and application point. Seed-drawn
directions made a 24-scenario set unrepresentative (0/24 falls vs 2/6 elsewhere).

Usage: python scripts/stage1_survival.py RUN_DIR [--updates 50 150] [--directions 16 --repeats 3]
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


def _fix_push(env: RLFall3DEnv, impulse: float, angle: float) -> None:
    # Keep the sampled timing, duration and point; set magnitude and direction.
    mass = float(np.sum(env.model.body_mass))
    direction = np.array([np.cos(angle), np.sin(angle), 0.0])
    env.push_force_world = (impulse * mass * np.sqrt(9.81 * env.body_height)
                            / env.push_duration * direction)
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
                impulse: float, seed: int, angle: float) -> tuple[bool, int]:
    env = RLFall3DEnv(seed=seed, **kwargs)
    if policy is None:
        env.reset(seed=seed)
    else:
        model, normalizer = policy
        venv = VecNormalize.load(str(normalizer), DummyVecEnv([lambda: env]))
        venv.training = False
        venv.seed(seed)
        observation = venv.reset()
    _fix_push(env, impulse, angle)
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


def stance_check(kwargs: dict[str, object], policy: tuple[PPO, Path] | None,
                 episodes: int = 12, seconds: float = 2.0) -> dict[str, float]:
    """Pre-push posture without any push: foot drift, CoM drop and trunk lean."""
    drifts, drops, leans = [], [], []
    for index in range(episodes):
        env = RLFall3DEnv(seed=SEED_BASE + 500 + index, **kwargs)
        if policy is None:
            env.reset(seed=SEED_BASE + 500 + index)
        else:
            model, normalizer = policy
            venv = VecNormalize.load(str(normalizer), DummyVecEnv([lambda: env]))
            venv.training = False
            venv.seed(SEED_BASE + 500 + index)
            observation = venv.reset()
        env.push_force_world[:] = 0.0
        for _ in range(int(seconds / env.config.control_dt)):
            if policy is None:
                env.step(np.zeros(env.action_space.shape, dtype=np.float32))
            else:
                action, _ = model.predict(observation, deterministic=True)
                observation, _, _, _ = venv.step(action)
        drifts.append(float(np.linalg.norm(env._feet_vector() - env._nominal_feet)))
        drops.append(env._reference_com_height - float(env.data.subtree_com[1][2]))
        leans.append(float(np.degrees(np.arccos(np.clip(env._upright_cos(), -1, 1)))))
    return {"feet_drift_m": float(np.median(drifts)), "com_drop_m": float(np.median(drops)),
            "trunk_lean_deg": float(np.median(leans))}


def curve(kwargs: dict[str, object], policy: tuple[PPO, Path] | None,
          directions: int, repeats: int,
          impulses: tuple[float, ...] = IMPULSES) -> dict[str, list[float]]:
    survival, stepping = [], []
    scenarios = directions * repeats
    for impulse in impulses:
        results = [run_episode(kwargs, policy, impulse, SEED_BASE + index,
                               2.0 * np.pi * (index % directions) / directions)
                   for index in range(scenarios)]
        survival.append(sum(alive for alive, _ in results) / scenarios)
        # Feet also lift while the body topples, so count steps only in survived episodes.
        survivors = [steps for alive, steps in results if alive]
        stepping.append(sum(steps > 0 for steps in survivors) / max(len(survivors), 1))
    return {"survival": survival, "step_rate": stepping}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--updates", nargs="+", type=int, default=())
    parser.add_argument("--directions", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--impulses", nargs="+", type=float, default=IMPULSES)
    parser.add_argument("--output", default="survival_curve.json",
                        help="file name written inside RUN_DIR")
    args = parser.parse_args()
    torch.set_num_threads(4)
    manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
    kwargs = {"condition": manifest.get("condition", "A"),
              "body": manifest.get("body", "v0_2"), "mode": "balance",
              "max_push_impulse": 0.45}
    if manifest.get("natural_stance"):
        kwargs["natural_stance"] = True  # evaluate from the same relaxed starts
    rows: dict[str, object] = {
        "impulses": list(args.impulses), "directions": args.directions,
        "repeats": args.repeats, "body": kwargs["body"],
        "passive": curve(kwargs, None, args.directions, args.repeats, tuple(args.impulses)),
    }
    for update in args.updates:
        model = PPO.load(args.run_dir / f"checkpoint_update_{update}.zip", device="cpu")
        normalizer = args.run_dir / f"vecnormalize_update_{update}.pkl"
        rows[f"update_{update}"] = curve(kwargs, (model, normalizer),
                                        args.directions, args.repeats, tuple(args.impulses))
        if kwargs["body"] in ("v1_0",):
            rows[f"stance_{update}"] = stance_check(kwargs, (model, normalizer))
    (args.run_dir / args.output).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"body {kwargs['body']}; survival (share of survivors that stepped) per impulse")
    print("impulse".ljust(14), " ".join(f"{i:>11.2f}" for i in args.impulses))
    for name, values in rows.items():
        if name.startswith("stance_"):
            print(f"{name}: feet drift {values['feet_drift_m'] * 100:.1f} cm, CoM drop "
                  f"{values['com_drop_m'] * 100:.1f} cm, trunk lean {values['trunk_lean_deg']:.1f} deg")
        elif isinstance(values, dict):
            print(name.ljust(14), " ".join(
                f"{s:>5.0%} ({t:>3.0%})" for s, t in zip(values["survival"], values["step_rate"])))


if __name__ == "__main__":
    main()
