"""True three-dimensional MuJoCo workload for the RL Fall benchmark."""

from __future__ import annotations

from dataclasses import asdict
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
from .env import CONDITIONS, EnvironmentConfig
from .tasks import TaskParameters
from .tasks3d import SpatialAlternatingTask


JOINT_NAMES = (
    "left_shoulder_flex", "left_shoulder_abduct", "left_shoulder_twist", "left_elbow",
    "right_shoulder_flex", "right_shoulder_abduct", "right_shoulder_twist", "right_elbow",
    "left_hip_flex", "left_hip_abduct", "left_hip_twist", "left_knee",
    "right_hip_flex", "right_hip_abduct", "right_hip_twist", "right_knee",
)
JOINT_PARTS = (
    *("left_arm",) * 4,
    *("right_arm",) * 4,
    *("left_leg",) * 4,
    *("right_leg",) * 4,
)
BODY_ASSETS = {"v0_1": "body_3d.xml", "v0_2": "body_3d_v0_2.xml"}
MODES = ("task", "balance")
# Curriculum stage 1: straight legs on flat feet, elbows slightly bent.
BALANCE_STANCE = np.array(
    [0.0, 0.0, 0.0, -0.25, 0.0, 0.0, 0.0, -0.25,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
)
BALANCE_ROOT_HEIGHT = 0.642  # v0.2 feet start 2 mm above the floor in the stance.
BALANCE_EPISODE_SECONDS = 10.0
# Fraction of each joint's half-range one unit of action may offset from the
# stance; full authority let PPO learn bang-bang kicks that topple the body.
BALANCE_ACTION_SCALE = 0.25
FALL_TORSO_HEIGHT_M = 0.45
FALL_UPRIGHT_COS = 0.5


class RLFall3DEnv(gym.Env[np.ndarray, np.ndarray]):
    """Spatial free-body task with persistent functional damage.

    Physics remains on MuJoCo's CPU backend.  Only PPO's policy/optimizer moves
    between CPU and CUDA in the paired device benchmark.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        condition: str = "B",
        seed: int | None = None,
        evaluation_impairment: bool | None = None,
        config: EnvironmentConfig | None = None,
        damage_parameters: DamageParameters | None = None,
        body: str = "v0_1",
        mode: str = "task",
        max_push_impulse: float = 0.45,
    ) -> None:
        super().__init__()
        condition = condition.upper()
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {tuple(CONDITIONS)}")
        if body not in BODY_ASSETS:
            raise ValueError(f"body must be one of {tuple(BODY_ASSETS)}")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode == "balance" and body == "v0_1":
            raise ValueError("balance mode needs a body with feet (v0_2)")
        self.body = body
        self.mode = mode
        self.max_push_impulse = float(max_push_impulse)
        self.config = config or EnvironmentConfig(
            condition=condition,
            episode_seconds=BALANCE_EPISODE_SECONDS if mode == "balance" else 30.0,
        )
        if self.config.condition.upper() != condition:
            raise ValueError("condition argument and config.condition disagree")

        asset = Path(__file__).resolve().parents[2] / "assets" / BODY_ASSETS[body]
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

        self.base_limits = np.array(
            [35, 25, 18, 20, 35, 25, 18, 20,
             60, 40, 30, 45, 60, 40, 30, 45],
            dtype=np.float64,
        )
        joint_ids = np.array([
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            for name in JOINT_NAMES
        ])
        if np.any(joint_ids < 0):
            raise RuntimeError("3D asset is missing an expected joint")
        self.actuated_qpos = self.model.jnt_qposadr[joint_ids].copy()
        self.actuated_qvel = self.model.jnt_dofadr[joint_ids].copy()
        self.joint_ranges = self.model.jnt_range[joint_ids].copy()
        self.torso_body_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "torso_body"
        )
        self.hand_site_ids = np.array([
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "left_hand"),
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "right_hand"),
        ])
        self.geom_part: dict[int, str] = {}
        for geom_id in range(self.model.ngeom):
            name = mujoco.mj_id2name(
                self.model, mujoco.mjtObj.mjOBJ_GEOM, geom_id
            ) or ""
            if name == "head":
                self.geom_part[geom_id] = "head"
            elif name == "torso":
                self.geom_part[geom_id] = "torso"
            elif name.startswith(("left_upper_arm", "left_lower_arm")):
                self.geom_part[geom_id] = "left_arm"
            elif name.startswith(("right_upper_arm", "right_lower_arm")):
                self.geom_part[geom_id] = "right_arm"
            elif name.startswith(("left_thigh", "left_shin")):
                self.geom_part[geom_id] = "left_leg"
            elif name.startswith(("right_thigh", "right_shin")):
                self.geom_part[geom_id] = "right_leg"
        self.floor_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
        self.foot_geom_ids = {
            geom_id for geom_id in range(self.model.ngeom)
            if (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or "")
            .endswith("_foot")
        }
        self._non_foot_floor_contact = False
        self.fallen = False

        self.action_space = spaces.Box(-1.0, 1.0, shape=(16,), dtype=np.float32)
        # joint angle/velocity 32, base velocity 6, body gravity 3,
        # task one-hot 2, 3-D target + mask, prior action 16, damage 6, time 1.
        self.observation_space = spaces.Box(
            low=-1.0e6, high=1.0e6, shape=(70,), dtype=np.float32
        )
        self.previous_action = np.zeros(16, dtype=np.float32)
        self.elapsed_steps = 0
        self.contact_counts = {name: 0 for name in PARTS}
        self.max_contact_loads = {name: 0.0 for name in PARTS}
        self.last_applied_torque = np.zeros(16, dtype=np.float64)
        self._last_task_distance = 0.0
        self._last_sensor_target = np.zeros(3, dtype=np.float32)
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
        self.task = SpatialAlternatingTask(
            self.config.control_dt, self.task_rng, TaskParameters()
        )

    def _torso_xyz(self) -> np.ndarray:
        return self.data.xpos[self.torso_body_id].copy()

    def _hand_xyz(self) -> np.ndarray:
        return self.data.site_xpos[self.hand_site_ids].copy()

    def _sample_push(self) -> None:
        # Same draw order in every mode so task-mode benchmark streams are unchanged.
        start_range = (1.0, 3.0) if self.mode == "balance" else (2.0, 4.0)
        self.push_start = float(self.push_rng.uniform(*start_range))
        self.push_duration = float(self.push_rng.uniform(0.05, 0.15))
        dimensionless_impulse = float(self.push_rng.uniform(0.0, self.max_push_impulse))
        self.push_impulse = dimensionless_impulse
        angle = float(self.push_rng.uniform(-np.pi, np.pi))
        total_mass = float(np.sum(self.model.body_mass))
        impulse_ns = dimensionless_impulse * total_mass * np.sqrt(9.81 * 1.2)
        magnitude = impulse_ns / self.push_duration
        self.push_force_world = magnitude * np.array(
            [np.cos(angle), np.sin(angle), 0.0], dtype=np.float64
        )
        # Random application point relative to the torso centre creates pitch,
        # roll, and yaw disturbances in addition to horizontal translation.
        self.push_point_local = np.array([
            self.push_rng.uniform(-0.10, 0.10),
            self.push_rng.uniform(-0.07, 0.07),
            self.push_rng.uniform(-0.15, 0.15),
        ])

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
        self.data.qpos[0:2] = self.initial_rng.uniform(-0.05, 0.05, size=2)
        crouch = np.array(
            [0.0, 0.0, 0.0, -0.25, 0.0, 0.0, 0.0, -0.25,
             0.05, 0.0, 0.0, 0.10, 0.05, 0.0, 0.0, 0.10]
        )
        self.data.qpos[self.actuated_qpos] = crouch
        if self.mode == "balance":
            self.data.qpos[2] = BALANCE_ROOT_HEIGHT
            self.data.qpos[self.actuated_qpos] = BALANCE_STANCE
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

        self.damage_model.reset(None if not options else options.get("damage"))
        self.previous_action.fill(0.0)
        self.elapsed_steps = 0
        self.contact_counts = {name: 0 for name in PARTS}
        self.max_contact_loads = {name: 0.0 for name in PARTS}
        self.last_applied_torque.fill(0.0)
        self._non_foot_floor_contact = False
        self.fallen = False
        self.task.reset(self._torso_xyz())
        self._last_task_distance = self.task.distance(
            self._torso_xyz(), self._hand_xyz()
        )
        self._sample_push()
        observation = self._get_observation(sample_sensor=True)
        return observation, self._info(np.zeros(6), success=False)

    def _requested_torque(self, action: np.ndarray) -> np.ndarray:
        centers = self.joint_ranges.mean(axis=1)
        half_ranges = (self.joint_ranges[:, 1] - self.joint_ranges[:, 0]) / 2.0
        if self.mode == "balance":
            # Zero action holds the stance; targets stay inside the joint ranges.
            targets = np.clip(
                BALANCE_STANCE
                + np.asarray(action, dtype=np.float64) * BALANCE_ACTION_SCALE * half_ranges,
                self.joint_ranges[:, 0], self.joint_ranges[:, 1],
            )
        else:
            targets = centers + np.asarray(action, dtype=np.float64) * half_ranges
        return (
            self.config.kp * (targets - self.data.qpos[self.actuated_qpos])
            - self.config.kd * self.data.qvel[self.actuated_qvel]
        )

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
            if self.mode == "balance":
                pair = (int(contact.geom1), int(contact.geom2))
                if self.floor_geom_id in pair:
                    other = pair[1] if pair[0] == self.floor_geom_id else pair[0]
                    if other not in self.foot_geom_ids:
                        self._non_foot_floor_contact = True
        return loads

    def step(self, action: np.ndarray):
        action = np.asarray(action, dtype=np.float32)
        if not self.action_space.contains(action):
            action = np.clip(action, -1.0, 1.0).astype(np.float32)

        total_increment = np.zeros(6, dtype=np.float64)
        step_peak_loads = {name: 0.0 for name in PARTS}
        for _ in range(self.config.substeps):
            torque = apply_functional_limits(
                self._requested_torque(action), self.base_limits,
                self.damage_model.damage, self.impairment_enabled, JOINT_PARTS,
            )
            self.last_applied_torque[:] = torque
            self.data.qfrc_applied[:] = 0.0
            self.data.qfrc_applied[self.actuated_qvel] = torque
            self.data.xfrc_applied[:] = 0.0
            sim_time = float(self.data.time)
            if self.push_start <= sim_time < self.push_start + self.push_duration:
                rotation = self.data.xmat[self.torso_body_id].reshape(3, 3)
                lever_world = rotation @ self.push_point_local
                self.data.xfrc_applied[self.torso_body_id, :3] = self.push_force_world
                self.data.xfrc_applied[self.torso_body_id, 3:] = np.cross(
                    lever_world, self.push_force_world
                )
            mujoco.mj_step(self.model, self.data)
            loads = self._contact_loads()
            total_increment += self.damage_model.update(loads, self.config.physics_dt)
            for part, load in loads.items():
                step_peak_loads[part] = max(step_peak_loads[part], load)

        for part, load in step_peak_loads.items():
            if load > 0.0:
                self.contact_counts[part] += 1
            self.max_contact_loads[part] = max(self.max_contact_loads[part], load)

        if self.mode == "balance":
            return self._balance_step(action, total_increment, step_peak_loads)

        torso, hands = self._torso_xyz(), self._hand_xyz()
        distance, success = self.task.advance(torso, hands)
        progress_reward = self.task.parameters.shaping_scale * (
            self._last_task_distance - distance
        )
        self._last_task_distance = (
            self.task.distance(torso, hands) if success else distance
        )
        task_reward = float(success) + float(progress_reward)
        damage_penalty = (
            self.config.damage_penalty_scale * float(np.mean(total_increment))
            if self.penalty_enabled else 0.0
        )

        self.previous_action[:] = action
        self.elapsed_steps += 1
        terminated = self.elapsed_steps >= self.config.max_episode_steps
        observation = self._get_observation(sample_sensor=True)
        info = self._info(total_increment, success)
        info["step_peak_contact_loads_n"] = step_peak_loads
        info["reward_task"] = task_reward
        info["reward_damage_penalty"] = -damage_penalty
        return observation, task_reward - damage_penalty, terminated, False, info

    def _upright_cos(self) -> float:
        return float(self.data.xmat[self.torso_body_id].reshape(3, 3)[2, 2])

    def _balance_step(
        self, action: np.ndarray, total_increment: np.ndarray,
        step_peak_loads: dict[str, float],
    ):
        upright = self._upright_cos()
        self.fallen = (
            self._torso_xyz()[2] < FALL_TORSO_HEIGHT_M
            or upright < FALL_UPRIGHT_COS
            or self._non_foot_floor_contact
        )
        # Survival bonus plus uprightness; small effort and jerk costs. A fall ends
        # the episode with no further reward, which is the implicit penalty.
        reward = 0.0 if self.fallen else (
            1.0 + 0.5 * upright
            - 0.05 * float(np.mean(np.square(action)))
            - 0.05 * float(np.mean(np.square(action - self.previous_action)))
        )
        self.previous_action[:] = action
        self.elapsed_steps += 1
        terminated = self.fallen or self.elapsed_steps >= self.config.max_episode_steps
        observation = self._get_observation(sample_sensor=True)
        info = self._info(total_increment, success=False)
        info["step_peak_contact_loads_n"] = step_peak_loads
        info["reward_task"] = 0.0
        info["reward_damage_penalty"] = 0.0
        info["reward_balance"] = reward
        info["fallen"] = self.fallen
        info["push_impulse"] = self.push_impulse
        return observation, reward, terminated, False, info

    def _get_observation(self, sample_sensor: bool) -> np.ndarray:
        rotation = self.data.xmat[self.torso_body_id].reshape(3, 3)
        gravity_body = rotation.T @ np.array([0.0, 0.0, -1.0])
        relative_target = self.task.target - self._torso_xyz()
        if self.mode == "balance":
            # No task in stage 1: kind, target and validity slots stay zero.
            remaining = 1.0 - self.elapsed_steps / self.config.max_episode_steps
            return np.concatenate([
                self.data.qpos[self.actuated_qpos],
                self.data.qvel[self.actuated_qvel],
                self.data.qvel[:6],
                gravity_body,
                np.zeros(6),
                self.previous_action,
                self.damage_model.damage,
                np.array([remaining]),
            ]).astype(np.float32)
        if sample_sensor:
            self._last_sensor_target, self._last_sensor_valid = target_sensor(
                relative_target, self.damage_model.damage[PART_INDEX["head"]],
                self.impairment_enabled, self.sensor_rng,
            )
        remaining = 1.0 - self.elapsed_steps / self.config.max_episode_steps
        return np.concatenate([
            self.data.qpos[self.actuated_qpos],
            self.data.qvel[self.actuated_qvel],
            self.data.qvel[:6],
            gravity_body,
            self.task.kind_one_hot(),
            self._last_sensor_target,
            np.array([self._last_sensor_valid]),
            self.previous_action,
            self.damage_model.damage,
            np.array([remaining]),
        ]).astype(np.float32)

    def _info(self, damage_increment: np.ndarray, success: bool) -> dict[str, Any]:
        return {
            "environment_dimension": "3d",
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

    env = RLFall3DEnv(seed=7)
    check_env(env, skip_render_check=True)
    observation, _ = env.reset(seed=7)
    for _ in range(25):
        observation, _, terminated, truncated, _ = env.step(env.action_space.sample())
        assert not truncated
        if terminated:
            observation, _ = env.reset()
    print(
        f"smoke_ok observation_shape={observation.shape} "
        f"action_shape={env.action_space.shape} substeps={env.config.substeps}"
    )


if __name__ == "__main__":
    _smoke()
