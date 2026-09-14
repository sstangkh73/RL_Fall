"""Development convergence check at 500 Hz versus 1000 Hz physics."""

from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from rl_fall.env import EnvironmentConfig, RLFallEnv


CASES = {"standing": 0.0, "low_drop": 0.10, "high_drop": 0.30}


def run_case(physics_dt: float, lift_m: float) -> dict[str, float]:
    config = EnvironmentConfig(condition="B", physics_dt=physics_dt)
    env = RLFallEnv(condition="B", seed=31001, config=config)
    env.reset(seed=31001)
    env.data.qpos[1] += lift_m
    mujoco.mj_forward(env.model, env.data)
    centers = env.joint_ranges.mean(axis=1)
    half_ranges = np.diff(env.joint_ranges, axis=1).ravel() / 2.0
    action = ((env.data.qpos[env.actuated_qpos] - centers) / half_ranges).astype(np.float32)
    for _ in range(75):
        env.step(action)
    result = {
        "mean_damage": float(np.mean(env.damage_model.damage)),
        "peak_contact_load_n": float(max(env.max_contact_loads.values())),
        "final_root_x_m": float(env.data.qpos[0]),
        "final_root_z_offset_m": float(env.data.qpos[1]),
        "final_root_pitch_rad": float(env.data.qpos[2]),
    }
    env.close()
    return result


def relative_difference(a: float, b: float) -> float:
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / scale


def main() -> None:
    results: dict[str, object] = {}
    passed = True
    for name, lift in CASES.items():
        main_result = run_case(0.002, lift)
        fine_result = run_case(0.001, lift)
        differences = {
            metric: relative_difference(main_result[metric], fine_result[metric])
            for metric in main_result
        }
        case_pass = differences["mean_damage"] <= 0.10
        passed = passed and case_pass
        results[name] = {
            "500_hz": main_result, "1000_hz": fine_result,
            "relative_differences": differences,
            "damage_within_10_percent": case_pass,
        }
    report = {
        "stage": "P1_numerical_convergence", "status": "pass" if passed else "fail",
        "criterion": "mean damage differs by no more than 10 percent in each standard case",
        "results": results,
    }
    path = Path("results/benchmark/physics_validation.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
