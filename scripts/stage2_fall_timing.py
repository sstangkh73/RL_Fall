"""Diagnostic only: time from push to fall on the S2 gate scenarios.

Tests whether S2 delays unrecoverable falls compared with S1 and passive. The S2
balance reward pays ~1.5 per step until the fall, so delaying a fall by 25 steps
(0.5 s) is worth about as much as the whole damage penalty of a typical fall.
Reuses the gate scenarios and policy loading of stage2_eval; not a gate result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage2_eval import (POLICIES, PARTS, WEIGHTS, _fix_push, env_kwargs, load_policy,
                         make_scenarios)
from rl_fall.env3d import RLFall3DEnv


def run_timed_episode(kwargs: dict, policy, scenario: dict, after_s: float) -> dict:
    env = RLFall3DEnv(seed=scenario["seed"], **kwargs)
    try:
        observation, _ = env.reset(seed=scenario["seed"])
        _fix_push(env, scenario["impulse"], scenario["angle"])
        fall_step = None
        reward_after_push = 0.0
        while env.elapsed_steps < env.config.max_episode_steps:
            if policy is None:
                action = np.zeros(env.action_space.shape, dtype=np.float32)
            else:
                model, normalizer = policy
                action, _ = model.predict(normalizer.normalize_obs(observation[None]),
                                          deterministic=True)
                action = action[0]
            observation, reward, terminated, truncated, _ = env.step(action)
            if env.data.time >= env.push_start:
                reward_after_push += float(reward)
            if env.fallen and fall_step is None:
                fall_step = env.elapsed_steps
            if terminated or truncated:
                break
            if (fall_step is not None
                    and (env.elapsed_steps - fall_step) * env.config.control_dt >= after_s):
                break
        damage = dict(zip(PARTS, env.damage_model.damage.tolist()))
        fall_time = (fall_step * env.config.control_dt - env.push_start
                     if fall_step is not None else None)
        return {**scenario, "fallen": fall_step is not None, "push_start": env.push_start,
                "fall_after_push_s": fall_time, "balance_reward_after_push": reward_after_push,
                "damage": damage, "weighted": sum(WEIGHTS[p] * damage[p] for p in PARTS)}
    finally:
        env.close()


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    array = np.asarray(values)
    return {"n": len(values), "mean": float(array.mean()), "median": float(np.median(array)),
            "p10": float(np.percentile(array, 10)), "p90": float(np.percentile(array, 90))}


def summarize(records: list[dict]) -> dict:
    hard = [r for r in records if r["group"] == "unrecoverable"]
    summary = {}
    for name in POLICIES:
        episodes = [r for r in hard if r["policy"] == name]
        falls = [r for r in episodes if r["fallen"]]
        summary[name] = {
            "fall_after_push_s": _stats([r["fall_after_push_s"] for r in falls]),
            "weighted_damage_mean": float(np.mean([r["weighted"] for r in episodes])),
            "per_impulse_fall_after_push_s": {
                f"{impulse:.2f}": _stats([r["fall_after_push_s"] for r in falls
                                          if r["impulse"] == impulse])
                for impulse in sorted({r["impulse"] for r in hard})}}
    # Paired S2-minus-baseline fall delay on scenarios where both policies fell.
    key = lambda r: (r["impulse"], r["seed"], r["angle"])
    s2 = {key(r): r for r in hard if r["policy"] == "s2" and r["fallen"]}
    for base in ("s1", "passive"):
        deltas = [s2[key(r)]["fall_after_push_s"] - r["fall_after_push_s"]
                  for r in hard if r["policy"] == base and r["fallen"] and key(r) in s2]
        summary[f"paired_delay_s2_minus_{base}_s"] = _stats(deltas)
    # Does a later fall go with more weighted damage for S2?
    s2_falls = list(s2.values())
    if len(s2_falls) > 2:
        summary["s2_corr_fall_time_vs_damage"] = float(np.corrcoef(
            [r["fall_after_push_s"] for r in s2_falls], [r["weighted"] for r in s2_falls])[0, 1])
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("s2_run", type=Path)
    parser.add_argument("--s1-run", type=Path, required=True)
    parser.add_argument("--s2-update", type=int, default=200)
    parser.add_argument("--s1-update", type=int, default=200)
    parser.add_argument("--after", type=float, default=2.5)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--episodes-scale", type=float, default=1.0)
    args = parser.parse_args()
    torch.set_num_threads(4)

    s2_manifest = json.loads((args.s2_run / "manifest.json").read_text(encoding="utf-8"))
    s1_manifest = json.loads((args.s1_run / "manifest.json").read_text(encoding="utf-8"))
    kwargs = {"s2": env_kwargs(s2_manifest, args.after),
              "s1": env_kwargs(s1_manifest, args.after),
              "passive": env_kwargs(s1_manifest, args.after)}
    # S2 training kwargs so the logged reward matches what the S2 policy was paid.
    reward_kwargs = {k: s2_manifest[k] for k in ("posture_weight", "capture_point_weight",
                                                 "posture_version", "damage_weight")
                     if k in s2_manifest}
    for name in POLICIES:
        kwargs[name] = {**kwargs[name], **reward_kwargs}
    scenarios = [s for s in make_scenarios(args.episodes_scale)
                 if s["group"] == "unrecoverable"]
    policies = {"passive": None}
    records = []
    try:
        policies["s2"] = load_policy(args.s2_run, args.s2_update, kwargs["s2"])
        policies["s1"] = load_policy(args.s1_run, args.s1_update, kwargs["s1"])
        for name in POLICIES:
            for scenario in scenarios:
                records.append({"policy": name, **run_timed_episode(
                    kwargs[name], policies[name], scenario, args.after)})
    finally:
        for policy in policies.values():
            if policy is not None:
                policy[1].close()

    result = {"script": "scripts/stage2_fall_timing.py", "diagnostic_only": True,
              "milestone_eligible": False, "s2_run": str(args.s2_run),
              "s1_run": str(args.s1_run), "s2_update": args.s2_update,
              "s1_update": args.s1_update, "after_s": args.after,
              "reward_kwargs": reward_kwargs, "summary": summarize(records),
              "episodes": records}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main()
