"""Gymnasium environment for the planar RL Fall benchmark workload."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

from .damage import (
    PARTS,
    PART_INDEX,
    DamageModel,
    DamageParameters,
    apply_functional_limits,
    target_sensor,
)
from .tasks import AlternatingTask, TaskParameters


@dataclass(frozen=True)
class EnvironmentConfig:
    condition: str = "B"
    control_dt: float = 0.02
    physics_dt: float = 0.002
    episode_seconds: float = 30.0
    damage_penalty_scale: float = 1.0
    kp: float = 55.0
    kd: float = 3.0

    @property
    def substeps(self) -> int:
        ratio = self.control_dt / self.physics_dt
        if not np.isclose(ratio, round(ratio)):
            raise ValueError("control_dt must be an integer multiple of physics_dt")
        return int(round(ratio))

    @property
    def max_episode_steps(self) -> int:
        return int(round(self.episode_seconds / self.control_dt))


CONDITIONS = {
    "A": {"impairment": False, "penalty": False},
    "B": {"impairment": True, "penalty": False},
    "C": {"impairment": False, "penalty": True},
    "D": {"impairment": True, "penalty": True},
}


class RLFallEnv(gym.Env[np.ndarray, np.ndarray]):
    """Headless planar rigid-body task with persistent functional damage.

    The 30-second boundary is part of the finite-horizon task, so it emits
    ``terminated=True`` rather than an infrastructure truncation. Falling,
    contact, or complete damage never ends an episode early.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        condition: str = "B",
        seed: int | None = None,
        evaluation_impairment: bool | None = None,
        config: EnvironmentConfig | None = None,
        damage_parameters: DamageParameters | None = None,
    ) -> None:
        super().__init__()
        condition = condition.upper()
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {tuple(CONDITIONS)}")
        self.config = config or EnvironmentConfig(condition=condition)
        if self.config.condition.upper() != condition:
            raise ValueError("condition argument and config.condition disagree")

        asset = Path(__file__).resolve().parents[2] / "assets" / "planar_body.xml"
        self.model = mujoco.MjModel.from_xml_path(str(asset))
        self.model.opt.timestep = self.config.physics_dt
        self.data = mujoco.MjData(self.model)

        self.condition = condition
        self.impairment_enabled = (
            CONDITIONS[condition]["impairment"]
            if evaluation_impairment is None
            else bool(evaluation_impairment)
        )
        self.penalty_enabled = CONDITIONS[condition]["penalty"]
        self.damage_model = DamageModel(damage_parameters)

        self.base_limits = np.array([35, 20, 35, 20, 60, 45, 60, 45], dtype=np.float64)
        self.joint_ranges = np.array(
            [[-2.7, 2.7], [-2.5, 0.1], [-2.7, 2.7], [-2.5, 0.1],
             [-1.8, 1.8], [-0.1, 2.6], [-1.8, 1.8], [-0.1, 2.6]],
            dtype=np.float64,
        )
        self.actuated_qpos = np.arange(3, 11)
        self.actuated_qvel = np.arange(3, 11)
        self.torso_body_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "torso_body"
        )
        self.hand_site_ids = np.array(
            [
                mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "left_hand"),
                mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "right_hand"),
            ]
        )
        self.geom_part: dict[int, str] = {}
        for geom_id in range(self.model.ngeom):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or ""
            if name == "head":
                self.geom_part[geom_id] = "head"
            elif name == "torso":
                self.geom_part[geom_id] = "torso"
            elif name.startswith("left_upper_arm") or name.startswith("left_lower_arm"):
                self.geom_part[geom_id] = "left_arm"
            elif name.startswith("right_upper_arm") or name.startswith("right_lower_arm"):
                self.geom_part[geom_id] = "right_arm"
            elif name.startswith("left_thigh") or name.startswith("left_shin"):
                self.geom_part[geom_id] = "left_leg"
            elif name.startswith("right_thigh") or name.startswith("right_shin"):
                self.geom_part[geom_id] = "right_leg"

        self.action_space = spaces.Box(-1.0, 1.0, shape=(8,), dtype=np.float32)
        # joint angle/velocity 16, base velocity 3, gravity direction 2,
        # task one-hot 2, head-routed target 2 + mask, previous action 8,
        # damage 6, remaining time 1 = 41.
        self.observation_space = spaces.Box(
            low=-1.0e6, high=1.0e6, shape=(41,), dtype=np.float32
        )
        self.previous_action = np.zeros(8, dtype=np.float32)
        self.elapsed_steps = 0
        self.contact_counts = {name: 0 for name in PARTS}
        self.max_contact_loads = {name: 0.0 for name in PARTS}
        self.last_applied_torque = np.zeros(8, dtype=np.float64)
        self._last_task_distance = 0.0
        self._last_sensor_target = np.zeros(2, dtype=np.float32)
        self._last_sensor_valid = 1.0
        self._episode_seed = seed
        self._set_random_streams(seed)

    def _set_random_streams(self, seed: int | None) -> None:
        sequence = np.random.SeedSequence(seed)
        task_ss, push_ss, sensor_ss, initial_ss = sequence.spawn(4)
        self.task_rng = np.random.default_rng(task_ss)
        self.push_rng = np.random.default_rng(push_ss)
        self.sensor_rng = np.random.default_rng(sensor_ss)
        self.initial_rng = np.random.default_rng(initial_ss)
        self.task = AlternatingTask(self.config.control_dt, self.task_rng, TaskParameters())

    def _torso_xz(self) -> np.ndarray:
        pos = self.data.xpos[self.torso_body_id]
        return pos[[0, 2]].copy()

    def _hand_xz(self) -> np.ndarray:
        return self.data.site_xpos[self.hand_site_ids][:, [0, 2]].copy()

    def _sample_push(self) -> None:
        self.push_start = float(self.push_rng.uniform(2.0, 4.0))
        self.push_duration = float(self.push_rng.uniform(0.05, 0.15))
        dimensionless_impulse = float(self.push_rng.uniform(0.0, 0.45))
        direction = float(self.push_rng.choice(np.array([-1.0, 1.0])))
        total_mass = float(np.sum(self.model.body_mass))
        reference_height = 1.2
        impulse_ns = dimensionless_impulse * total_mass * np.sqrt(9.81 * reference_height)
        self.push_force_x = direction * impulse_ns / self.push_duration

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self._episode_seed = seed
            self._set_random_streams(seed)
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[0] = self.initial_rng.uniform(-0.05, 0.05)
        self.data.qpos[1] = self.initial_rng.uniform(-0.005, 0.005)
        self.data.qpos[2] = self.initial_rng.uniform(-0.04, 0.04)
        crouch = np.array([0.0, -0.25, 0.0, -0.25, 0.05, 0.10, 0.05, 0.10])
        self.data.qpos[self.actuated_qpos] = crouch
        if options and "qpos" in options:
            supplied = np.asarray(options["qpos"], dtype=np.float64)
            if supplied.shape != self.data.qpos.shape:
                raise ValueError(f"qpos option must have shape {self.data.qpos.shape}")
            self.data.qpos[:] = supplied
        self.data.qvel[:] = 0.0
        if options and "qvel" in options:
            supplied = np.asarray(options["qvel"], dtype=np.float64)
            if supplied.shape != self.data.qvel.shape:
                raise ValueError(f"qvel option must have shape {self.data.qvel.shape}")
            self.data.qvel[:] = supplied
        mujoco.mj_forward(self.model, self.data)

        initial_damage = None if not options else options.get("damage")
        self.damage_model.reset(initial_damage)
        self.previous_action.fill(0.0)
        self.elapsed_steps = 0
        self.contact_counts = {name: 0 for name in PARTS}
        self.max_contact_loads = {name: 0.0 for name in PARTS}
        self.last_applied_torque.fill(0.0)
        self.task.reset(self._torso_xz())
        self._last_task_distance = self.task.distance(self._torso_xz(), self._hand_xz())
        self._sample_push()
        observation = self._get_observation(sample_sensor=True)
        return observation, self._info(np.zeros(6), success=False)

    def _requested_torque(self, action: np.ndarray) -> np.ndarray:
        centers = self.joint_ranges.mean(axis=1)
        half_ranges = (self.joint_ranges[:, 1] - self.joint_ranges[:, 0]) / 2.0
        targets = centers + np.asarray(action, dtype=np.float64) * half_ranges
        angles = self.data.qpos[self.actuated_qpos]
        velocities = self.data.qvel[self.actuated_qvel]
        return self.config.kp * (targets - angles) - self.config.kd * velocities

    def _contact_loads(self) -> dict[str, float]:
        loads = {name: 0.0 for name in PARTS}
        force = np.zeros(6, dtype=np.float64)
        for contact_index in range(self.data.ncon):
            contact = self.data.contact[contact_index]
            mujoco.mj_contactForce(self.model, self.data, contact_index, force)
            magnitude = float(np.linalg.norm(force[:3]))
            for geom in (int(contact.geom1), int(contact.geom2)):
                part = self.geom_part.get(geom)
                if part is not None:
                    loads[part] = max(loads[part], magnitude)
        return loads

    def step(self, action: np.ndarray):
        action = np.asarray(action, dtype=np.float32)
        if not self.action_space.contains(action):
            action = np.clip(action, -1.0, 1.0).astype(np.float32)

        total_increment = np.zeros(6, dtype=np.float64)
        step_peak_loads = {name: 0.0 for name in PARTS}
        for _ in range(self.config.substeps):
            torque = apply_functional_limits(
                self._requested_torque(action),
                self.base_limits,
                self.damage_model.damage,
                self.impairment_enabled,
            )
            self.last_applied_torque[:] = torque
            self.data.qfrc_applied[:] = 0.0
            self.data.qfrc_applied[self.actuated_qvel] = torque
            sim_time = float(self.data.time)
            self.data.xfrc_applied[:] = 0.0
            if self.push_start <= sim_time < self.push_start + self.push_duration:
                self.data.xfrc_applied[self.torso_body_id, 0] = self.push_force_x
            mujoco.mj_step(self.model, self.data)
            loads = self._contact_loads()
            total_increment += self.damage_model.update(loads, self.config.physics_dt)
            for part, load in loads.items():
                step_peak_loads[part] = max(step_peak_loads[part], load)

        for part, load in step_peak_loads.items():
            if load > 0.0:
                self.contact_counts[part] += 1
            self.max_contact_loads[part] = max(self.max_contact_loads[part], load)

        torso = self._torso_xz()
        hands = self._hand_xz()
        distance, success = self.task.advance(torso, hands)
        progress_reward = self.task.parameters.shaping_scale * (
            self._last_task_distance - distance
        )
        if success:
            # The target switch does not create a shaping jump.
            self._last_task_distance = self.task.distance(torso, hands)
        else:
            self._last_task_distance = distance
        task_reward = float(success) + float(progress_reward)
        damage_penalty = (
            self.config.damage_penalty_scale * float(np.mean(total_increment))
            if self.penalty_enabled
            else 0.0
        )
        reward = task_reward - damage_penalty

        self.previous_action[:] = action
        self.elapsed_steps += 1
        terminated = self.elapsed_steps >= self.config.max_episode_steps
        truncated = False
        observation = self._get_observation(sample_sensor=True)
        info = self._info(total_increment, success)
        info["step_peak_contact_loads_n"] = step_peak_loads
        info["reward_task"] = task_reward
        info["reward_damage_penalty"] = -damage_penalty
        return observation, reward, terminated, truncated, info

    def _get_observation(self, sample_sensor: bool) -> np.ndarray:
        joint_angles = self.data.qpos[self.actuated_qpos]
        joint_velocities = self.data.qvel[self.actuated_qvel]
        base_velocity = self.data.qvel[:3]
        pitch = float(self.data.qpos[2])
        gravity_direction = np.array([np.sin(pitch), -np.cos(pitch)])
        relative_target = self.task.target - self._torso_xz()
        if sample_sensor:
            self._last_sensor_target, self._last_sensor_valid = target_sensor(
                relative_target,
                self.damage_model.damage[PART_INDEX["head"]],
                self.impairment_enabled,
                self.sensor_rng,
            )
        remaining = 1.0 - self.elapsed_steps / self.config.max_episode_steps
        observation = np.concatenate(
            [
                joint_angles,
                joint_velocities,
                base_velocity,
                gravity_direction,
                self.task.kind_one_hot(),
                self._last_sensor_target,
                np.array([self._last_sensor_valid]),
                self.previous_action,
                self.damage_model.damage,
                np.array([remaining]),
            ]
        ).astype(np.float32)
        return observation

    def _info(self, damage_increment: np.ndarray, success: bool) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "impairment_enabled": self.impairment_enabled,
            "task_success": int(success),
            "task_successes_episode": self.task.successes,
            "task_kind": int(self.task.kind),
            "damage": self.damage_model.damage.astype(float).tolist(),
            "damage_increment": np.asarray(damage_increment, dtype=float).tolist(),
            "contact_counts": self.contact_counts.copy(),
            "max_contact_loads_n": self.max_contact_loads.copy(),
            "sensor_valid": self._last_sensor_valid,
            "elapsed_control_steps": self.elapsed_steps,
            "environment_config": asdict(self.config),
        }

    def close(self) -> None:
        pass


def _smoke() -> None:
    from gymnasium.utils.env_checker import check_env

    env = RLFallEnv(seed=7)
    check_env(env, skip_render_check=True)
    observation, _ = env.reset(seed=7)
    for _ in range(25):
        observation, _, terminated, truncated, _ = env.step(env.action_space.sample())
        assert not truncated
        if terminated:
            observation, _ = env.reset()
    print(f"smoke_ok observation_shape={observation.shape} substeps={env.config.substeps}")


if __name__ == "__main__":
    _smoke()
