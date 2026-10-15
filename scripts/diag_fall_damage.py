"""Does a fall produce damage? Per-part peak load and damage when falls run on.

The S2 pilot scores falls by weighted damage (head 5, torso 2, limbs 1). Damage only
grows while a contact exceeds the segment's literature tolerance (injury_kN), so this
checks whether simulated falls get there at all. Episodes keep running for --after
seconds once the body has fallen (no termination), for the passive body and, if
RUN_DIR is given, the S1 policy.

Usage: python scripts/diag_fall_damage.py [RUN_DIR] [--update 200] [--episodes 12]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl_fall.damage import PARTS
from rl_fall.env3d import RLFall3DEnv

SEED_BASE = 9000  # same scenarios as stage1_survival
IMPULSES = (0.08, 0.15, 0.20, 0.25)
WEIGHTS = {"head": 5.0, "torso": 2.0, "left_arm": 1.0, "right_arm": 1.0,
           "left_leg": 1.0, "right_leg": 1.0}


def _fix_push(env: RLFall3DEnv, impulse: float, angle: float) -> None:
    mass = float(np.sum(env.model.body_mass))
    direction = np.array([np.cos(angle), np.sin(angle), 0.0])
    env.push_force_world = (impulse * mass * np.sqrt(9.81 * env.body_height)
                            / env.push_duration * direction)
    env.push_impulse = impulse


def run(kwargs: dict, policy, impulse: float, seed: int, angle: float,
        after_s: float) -> dict:
    env = RLFall3DEnv(seed=seed, **kwargs)
    observation, _ = env.reset(seed=seed)
    _fix_push(env, impulse, angle)
    fall_step = None
    peak_ratio = {part: 0.0 for part in PARTS}
    while env.elapsed_steps < env.config.max_episode_steps:
        if policy is None:
            action = np.zeros(env.action_space.shape, dtype=np.float32)
        else:
            model, normalizer = policy
            action, _ = model.predict(normalizer.normalize_obs(observation[None]),
                                      deterministic=True)
            action = action[0]
        observation, _, _, _, info = env.step(action)
        for part, load in info["step_peak_contact_loads_n"].items():
            # Loads are on the 250 N per-part scale, so load / 250 = force / tolerance.
            peak_ratio[part] = max(peak_ratio[part],
                                   load / env.damage_model.parameters.threshold_n[part])
        if env.fallen and fall_step is None:
            fall_step = env.elapsed_steps
        if fall_step is not None and (env.elapsed_steps - fall_step) * env.config.control_dt >= after_s:
            break
    damage = dict(zip(PARTS, env.damage_model.damage.tolist()))
    return {"fallen": fall_step is not None, "peak_ratio": peak_ratio, "damage": damage,
            "weighted": sum(WEIGHTS[p] * d for p, d in damage.items())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path, nargs="?")
    parser.add_argument("--update", type=int, default=200)
    parser.add_argument("--episodes", type=int, default=12)
    parser.add_argument("--after", type=float, default=2.5)
    args = parser.parse_args()
    torch.set_num_threads(4)
    kwargs = {"condition": "A", "body": "v1_0", "mode": "balance", "max_push_impulse": 0.45,
              "natural_stance": True}
    policies = {"passive": None}
    if args.run_dir is not None:
        manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
        kwargs["natural_stance"] = bool(manifest.get("natural_stance"))
        model = PPO.load(args.run_dir / f"checkpoint_update_{args.update}.zip", device="cpu")
        normalizer = VecNormalize.load(
            str(args.run_dir / f"vecnormalize_update_{args.update}.pkl"),
            DummyVecEnv([lambda: RLFall3DEnv(**kwargs)]))
        normalizer.training = False
        policies[f"update_{args.update}"] = (model, normalizer)
    angles = np.linspace(-np.pi, np.pi, args.episodes, endpoint=False)
    for name, policy in policies.items():
        for impulse in IMPULSES:
            results = [run(kwargs, policy, impulse, SEED_BASE + i, float(angles[i]), args.after)
                       for i in range(args.episodes)]
            falls = [r for r in results if r["fallen"]]
            print(f"{name:>10} impulse {impulse:.2f}: fell {len(falls)}/{len(results)}")
            if not falls:
                continue
            for part in PARTS:
                ratios = [r["peak_ratio"][part] for r in falls]
                damages = [r["damage"][part] for r in falls]
                print(f"    {part:>9} peak F/tol median {np.median(ratios):5.2f} max {max(ratios):5.2f}"
                      f" | >tol {sum(x > 1 for x in ratios):2d}/{len(falls)}"
                      f" | damage mean {np.mean(damages):.4f} max {max(damages):.4f}")
            weighted = [r["weighted"] for r in falls]
            print(f"    weighted damage mean {np.mean(weighted):.4f} median {np.median(weighted):.4f}"
                  f" max {max(weighted):.4f}")


if __name__ == "__main__":
    main()
