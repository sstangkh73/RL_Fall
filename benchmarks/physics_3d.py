"""Physics-only 3D trace benchmark using identical actions and seeds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path

import mujoco
import numpy as np

from rl_fall.env3d import RLFall3DEnv
from rl_fall.telemetry import ResourceSampler


SCENARIOS = (
    "standing", "moving", "forward_fall", "lateral_fall",
    "twisting", "multi_contact", "partial_damage", "high_damage",
)


def _set_root_rotation(env: RLFall3DEnv, axis: np.ndarray, angle: float) -> None:
    axis = np.asarray(axis, dtype=np.float64)
    axis /= np.linalg.norm(axis)
    env.data.qpos[3:7] = np.concatenate(
        ([np.cos(angle / 2.0)], axis * np.sin(angle / 2.0))
    )


def configure_scenario(env: RLFall3DEnv, name: str, seed: int) -> np.ndarray:
    observation, _ = env.reset(seed=seed)
    if name == "moving":
        env.data.qvel[:6] = [0.6, 0.4, 0.0, 0.2, -0.1, 0.4]
    elif name == "forward_fall":
        _set_root_rotation(env, np.array([0.0, 1.0, 0.0]), 0.75)
        env.data.qvel[4] = 1.6
    elif name == "lateral_fall":
        _set_root_rotation(env, np.array([1.0, 0.0, 0.0]), 0.75)
        env.data.qvel[3] = 1.6
    elif name == "twisting":
        env.data.qvel[5] = 2.2
        env.data.qpos[env.actuated_qpos[[2, 6, 10, 14]]] = [0.7, -0.7, 0.5, -0.5]
    elif name == "multi_contact":
        env.data.qpos[2] = 0.30
        _set_root_rotation(env, np.array([1.0, 1.0, 0.0]), 1.05)
    elif name == "partial_damage":
        env.damage_model.reset(np.full(6, 0.25))
    elif name == "high_damage":
        env.damage_model.reset(np.full(6, 0.75))
    if name != "standing":
        mujoco.mj_forward(env.model, env.data)
        observation = env._get_observation(sample_sensor=True)
    return observation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transitions", type=int, default=20_000)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=41001)
    parser.add_argument(
        "--output", type=Path, default=Path("results/benchmark_3d/physics")
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    actions = np.random.default_rng(args.seed).uniform(
        -1.0, 1.0, size=(args.transitions, 16)
    ).astype(np.float32)
    action_hash = hashlib.sha256(actions.tobytes()).hexdigest()
    rows: list[dict[str, object]] = []
    sampler = ResourceSampler(args.output / "resources.jsonl")
    sampler.start()
    try:
        for scenario_index, scenario in enumerate(SCENARIOS):
            for repetition in range(args.repetitions):
                env = RLFall3DEnv(condition="B", seed=args.seed)
                configure_scenario(env, scenario, args.seed + scenario_index)
                start = time.perf_counter()
                for action in actions:
                    _, _, terminated, truncated, _ = env.step(action)
                    if terminated or truncated:
                        configure_scenario(env, scenario, args.seed + scenario_index)
                elapsed = time.perf_counter() - start
                rows.append({
                    "scenario": scenario,
                    "repetition": repetition,
                    "control_transitions": args.transitions,
                    "physics_substeps": args.transitions * env.config.substeps,
                    "seconds": elapsed,
                    "control_transitions_per_second": args.transitions / elapsed,
                    "final_damage_mean": float(np.mean(env.damage_model.damage)),
                    "contact_control_steps": sum(env.contact_counts.values()),
                    "action_trace_sha256": action_hash,
                })
                env.close()
    finally:
        sampler.stop()

    with (args.output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "stage": "P2_3d_physics_diagnostic",
        "status": "complete",
        "environment_dimension": "3d",
        "physics_backend": "MuJoCo CPU",
        "seed": args.seed,
        "transitions_per_trace": args.transitions,
        "repetitions": args.repetitions,
        "scenarios": list(SCENARIOS),
        "action_trace_sha256": action_hash,
        "counting_unit": (
            "completed control transitions; physics substeps reported separately"
        ),
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
