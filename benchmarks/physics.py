"""Physics-only trace benchmark using identical actions and scenario seeds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from rl_fall.env import RLFallEnv
from rl_fall.telemetry import ResourceSampler


SCENARIOS = ("standing", "moving", "falling", "multi_contact", "partial_damage", "high_damage")


def configure_scenario(env: RLFallEnv, name: str, seed: int) -> np.ndarray:
    observation, _ = env.reset(seed=seed)
    if name == "moving":
        env.data.qvel[0] = 0.7
        env.data.qvel[2] = 0.5
    elif name == "falling":
        env.data.qpos[2] = 0.65
        env.data.qvel[2] = 1.8
    elif name == "multi_contact":
        env.data.qpos[1] = -0.34
        env.data.qpos[2] = 1.15
    elif name == "partial_damage":
        env.damage_model.reset(np.full(6, 0.25))
    elif name == "high_damage":
        env.damage_model.reset(np.full(6, 0.75))
    if name != "standing":
        import mujoco
        mujoco.mj_forward(env.model, env.data)
        observation = env._get_observation(sample_sensor=True)
    return observation


def trace_hash(actions: np.ndarray) -> str:
    return hashlib.sha256(actions.tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transitions", type=int, default=20_000)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=21001)
    parser.add_argument("--output", type=Path, default=Path("results/benchmark/physics"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    actions = np.random.default_rng(args.seed).uniform(
        -1.0, 1.0, size=(args.transitions, 8)
    ).astype(np.float32)
    sampler = ResourceSampler(args.output / "resources.jsonl")
    rows: list[dict[str, object]] = []
    sampler.start()
    try:
        for scenario_index, scenario in enumerate(SCENARIOS):
            for repetition in range(args.repetitions):
                env = RLFallEnv(condition="B", seed=args.seed)
                configure_scenario(env, scenario, args.seed + scenario_index)
                start = time.perf_counter()
                control_transitions = 0
                for action in actions:
                    _, _, terminated, truncated, _ = env.step(action)
                    control_transitions += 1
                    if terminated or truncated:
                        configure_scenario(env, scenario, args.seed + scenario_index)
                elapsed = time.perf_counter() - start
                rows.append({
                    "scenario": scenario, "repetition": repetition,
                    "control_transitions": control_transitions,
                    "physics_substeps": control_transitions * env.config.substeps,
                    "seconds": elapsed,
                    "control_transitions_per_second": control_transitions / elapsed,
                    "final_damage_mean": float(np.mean(env.damage_model.damage)),
                    "contact_control_steps": sum(env.contact_counts.values()),
                })
                env.close()
    finally:
        sampler.stop()
    with (args.output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "stage": "P2_physics_diagnostic", "status": "complete",
        "seed": args.seed, "transitions_per_trace": args.transitions,
        "repetitions": args.repetitions, "scenarios": list(SCENARIOS),
        "action_trace_sha256": trace_hash(actions),
        "counting_unit": "completed control transitions; physics substeps reported separately",
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

