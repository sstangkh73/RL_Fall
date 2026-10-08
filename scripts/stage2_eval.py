"""Paired recover-or-fall evaluation of S2, S1 and passive (zero-action) policies."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

# Support the specified direct CLI invocation from a src-layout checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rl_fall.damage import PARTS
from rl_fall.env3d import RLFall3DEnv

SEED_BASE = 9000
GROUPS = {
    "recoverable": ((0.05, 24), (0.08, 24)),
    "unrecoverable": ((0.15, 16), (0.20, 16), (0.25, 16)),
}
POLICIES = ("s2", "s1", "passive")
WEIGHTS = {"head": 5.0, "torso": 2.0, "left_arm": 1.0, "right_arm": 1.0,
           "left_leg": 1.0, "right_leg": 1.0}


def _fix_push(env: RLFall3DEnv, impulse: float, angle: float) -> None:
    # Preserve the seed-drawn timing, duration and application point.
    mass = float(np.sum(env.model.body_mass))
    direction = np.array([np.cos(angle), np.sin(angle), 0.0])
    env.push_force_world = (impulse * mass * np.sqrt(9.81 * env.body_height)
                            / env.push_duration * direction)
    env.push_impulse = impulse


def make_scenarios(episodes_scale: float = 1.0) -> list[dict]:
    """Build once, then reuse the exact same scenarios for all three policies."""
    scenarios = []
    for group, impulses in GROUPS.items():
        for impulse, count in impulses:
            n = max(1, round(count * episodes_scale))
            angles = np.linspace(-np.pi, np.pi, n, endpoint=False)
            scenarios.extend({"group": group, "impulse": impulse,
                              "seed": SEED_BASE + i, "angle": float(angle)}
                             for i, angle in enumerate(angles))
    return scenarios


def env_kwargs(manifest: dict, after_s: float) -> dict:
    return {"condition": manifest.get("condition", "A"),
            "body": manifest["body"], "mode": "balance", "max_push_impulse": 0.45,
            "natural_stance": bool(manifest.get("natural_stance")),
            "fall_continue_s": after_s}


def load_policy(run_dir: Path, update: int, kwargs: dict) -> tuple[PPO, VecNormalize]:
    model = PPO.load(run_dir / f"checkpoint_update_{update}.zip", device="cpu")
    venv = DummyVecEnv([lambda: RLFall3DEnv(**kwargs)])
    try:
        normalizer = VecNormalize.load(
            str(run_dir / f"vecnormalize_update_{update}.pkl"), venv)
    except Exception:
        venv.close()
        raise
    normalizer.training = False
    return model, normalizer


def run_episode(kwargs: dict, policy: tuple[PPO, VecNormalize] | None,
                scenario: dict, after_s: float) -> dict:
    env = RLFall3DEnv(seed=scenario["seed"], **kwargs)
    try:
        observation, _ = env.reset(seed=scenario["seed"])
        _fix_push(env, scenario["impulse"], scenario["angle"])
        fall_step = None
        while env.elapsed_steps < env.config.max_episode_steps:
            if policy is None:
                action = np.zeros(env.action_space.shape, dtype=np.float32)
            else:
                model, normalizer = policy
                action, _ = model.predict(normalizer.normalize_obs(observation[None]),
                                          deterministic=True)
                action = action[0]
            observation, _, terminated, truncated, _ = env.step(action)
            if env.fallen and fall_step is None:
                fall_step = env.elapsed_steps
            if terminated or truncated:
                break
            if (fall_step is not None
                    and (env.elapsed_steps - fall_step) * env.config.control_dt >= after_s):
                break
        damage = dict(zip(PARTS, env.damage_model.damage.tolist()))
        return {**scenario, "fallen": fall_step is not None, "damage": damage,
                "weighted": sum(WEIGHTS[p] * damage[p] for p in PARTS)}
    finally:
        env.close()


def _metrics(records: list[dict]) -> dict:
    n = len(records)
    return {"n": n,
            "survival": sum(not r["fallen"] for r in records) / n if n else 0.0,
            "weighted_damage_mean": sum(r["weighted"] for r in records) / n if n else 0.0}


def summarize(records: list[dict]) -> dict:
    """Summarize episode records without running environments or loading checkpoints.

    Each record contains policy, group, impulse, seed, angle, fallen, damage and
    weighted. Paired scenarios are identified by (impulse, seed, angle).
    Group damage means include every episode, including survivors.
    """
    summary = {}
    for group in GROUPS:
        by_policy = {name: [r for r in records if r["group"] == group
                            and r["policy"] == name] for name in POLICIES}
        group_summary = {"n_episodes": len(by_policy["s2"])}
        for name, episodes in by_policy.items():
            metrics = _metrics(episodes)
            group_summary[f"{name}_survival"] = metrics["survival"]
            group_summary[f"{name}_weighted_damage"] = metrics["weighted_damage_mean"]
        summary[group] = group_summary

    recoverable = [r for r in records if r["group"] == "recoverable"]
    s2_fallen = {(r["impulse"], r["seed"], r["angle"]): r["fallen"]
                 for r in recoverable if r["policy"] == "s2"}
    s1_survivors = [r for r in recoverable if r["policy"] == "s1" and not r["fallen"]]
    false_give_up = sum(s2_fallen[(r["impulse"], r["seed"], r["angle"])]
                        for r in s1_survivors)
    summary["false_give_up"] = false_give_up / len(s1_survivors) if s1_survivors else 0.0

    unrecoverable = [r for r in records if r["group"] == "unrecoverable"]
    s2_episodes = [r for r in unrecoverable if r["policy"] == "s2"]
    total_weighted = sum(r["weighted"] for r in s2_episodes)
    summary["head_damage_share"] = (
        sum(WEIGHTS["head"] * r["damage"]["head"] for r in s2_episodes) / total_weighted
        if total_weighted else 0.0)
    summary["per_impulse"] = {
        f"{impulse:.2f}": {
            name: _metrics([r for r in records if r["impulse"] == impulse
                            and r["policy"] == name]) for name in POLICIES}
        for impulses in GROUPS.values() for impulse, _ in impulses}
    summary["per_part_damage_mean_unrecoverable"] = {}
    for name in POLICIES:
        episodes = [r for r in unrecoverable if r["policy"] == name]
        summary["per_part_damage_mean_unrecoverable"][name] = {
            part: sum(r["damage"][part] for r in episodes) / len(episodes) if episodes else 0.0
            for part in PARTS}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("s2_run", type=Path)
    parser.add_argument("--s1-run", type=Path, required=True)
    parser.add_argument("--s2-update", type=int, default=200)
    parser.add_argument("--s1-update", type=int, default=200)
    parser.add_argument("--after", type=float, default=2.5)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--episodes-scale", type=float, default=1.0,
                        help="multiply per-impulse counts (smoke tests only)")
    args = parser.parse_args()
    if not math.isfinite(args.after) or args.after < 0:
        parser.error("--after must be finite and >= 0")
    if not math.isfinite(args.episodes_scale):
        parser.error("--episodes-scale must be finite")
    torch.set_num_threads(4)

    s2_manifest = json.loads((args.s2_run / "manifest.json").read_text(encoding="utf-8"))
    s1_manifest = json.loads((args.s1_run / "manifest.json").read_text(encoding="utf-8"))
    kwargs = {"s2": env_kwargs(s2_manifest, args.after),
              "s1": env_kwargs(s1_manifest, args.after),
              "passive": env_kwargs(s1_manifest, args.after)}
    scenarios = make_scenarios(args.episodes_scale)
    policies = {"passive": None}
    records = []
    try:
        policies["s2"] = load_policy(args.s2_run, args.s2_update, kwargs["s2"])
        policies["s1"] = load_policy(args.s1_run, args.s1_update, kwargs["s1"])
        for name in POLICIES:
            for scenario in scenarios:
                records.append({"policy": name,
                                **run_episode(kwargs[name], policies[name], scenario, args.after)})
    finally:
        for policy in policies.values():
            if policy is not None:
                policy[1].close()

    summary = {"script": "scripts/stage2_eval.py",
               "s2_run": str(args.s2_run), "s1_run": str(args.s1_run),
               "s2_update": args.s2_update, "s1_update": args.s1_update,
               "after_s": args.after, **summarize(records)}
    out = args.out if args.out is not None else args.s2_run / "s2_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for group in GROUPS:
        values = summary[group]
        print(f"{group} ({values['n_episodes']} paired episodes): " + "; ".join(
            f"{name} survival {values[f'{name}_survival']:.1%}, "
            f"weighted damage {values[f'{name}_weighted_damage']:.6f}" for name in POLICIES))
    print(f"false give-up {summary['false_give_up']:.1%}; "
          f"S2 unrecoverable head damage share {summary['head_damage_share']:.1%}")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
