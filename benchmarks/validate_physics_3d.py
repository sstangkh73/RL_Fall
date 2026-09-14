"""Development convergence check for true 3D falls at 500 versus 1000 Hz."""

from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from rl_fall.env import EnvironmentConfig
from rl_fall.env3d import RLFall3DEnv


CASES = {
    "standing": (0.0, None, 0.0),
    "low_drop": (0.10, None, 0.0),
    "high_drop": (0.30, None, 0.0),
    "forward_fall": (0.12, "pitch", 0.70),
    "lateral_fall": (0.12, "roll", 0.70),
}


def _set_rotation(env: RLFall3DEnv, axis: np.ndarray, angle: float) -> None:
    axis = np.asarray(axis, dtype=np.float64)
    axis /= np.linalg.norm(axis)
    env.data.qpos[3:7] = np.concatenate(
        ([np.cos(angle / 2.0)], axis * np.sin(angle / 2.0))
    )


def run_case(
    physics_dt: float, lift_m: float, rotation: str | None, angle: float
) -> dict[str, float]:
    config = EnvironmentConfig(condition="B", physics_dt=physics_dt)
    env = RLFall3DEnv(condition="B", seed=51001, config=config)
    env.reset(seed=51001)
    env.data.qpos[2] += lift_m
    if rotation == "pitch":
        _set_rotation(env, np.array([0.0, 1.0, 0.0]), angle)
    elif rotation == "roll":
        _set_rotation(env, np.array([1.0, 0.0, 0.0]), angle)
    mujoco.mj_forward(env.model, env.data)
    centers = env.joint_ranges.mean(axis=1)
    half_ranges = np.diff(env.joint_ranges, axis=1).ravel() / 2.0
    action = (
        (env.data.qpos[env.actuated_qpos] - centers) / half_ranges
    ).astype(np.float32)
    action = np.clip(action, -1.0, 1.0)
    for _ in range(75):
        env.step(action)
    result = {
        "mean_damage": float(np.mean(env.damage_model.damage)),
        "peak_contact_load_n": float(max(env.max_contact_loads.values())),
        "final_root_x_m": float(env.data.qpos[0]),
        "final_root_y_m": float(env.data.qpos[1]),
        "final_root_z_m": float(env.data.qpos[2]),
    }
    env.close()
    return result


def relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


def main() -> None:
    results: dict[str, object] = {}
    passed = True
    for name, (lift, rotation, angle) in CASES.items():
        main_result = run_case(0.002, lift, rotation, angle)
        fine_result = run_case(0.001, lift, rotation, angle)
        differences = {
            metric: relative_difference(main_result[metric], fine_result[metric])
            for metric in main_result
        }
        case_pass = differences["mean_damage"] <= 0.10
        passed = passed and case_pass
        results[name] = {
            "500_hz": main_result,
            "1000_hz": fine_result,
            "relative_differences": differences,
            "damage_within_10_percent": case_pass,
        }
    report = {
        "stage": "P1_3d_numerical_convergence",
        "status": "pass" if passed else "fail",
        "criterion": "mean damage differs by no more than 10 percent per case",
        "results": results,
    }
    path = Path("results/benchmark_3d/physics_validation.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
