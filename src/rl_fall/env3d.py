"""True three-dimensional MuJoCo workload for the RL Fall benchmark."""

from __future__ import annotations

import json
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
ANKLE_JOINT_NAMES = (
    "left_ankle_pitch", "left_ankle_roll", "right_ankle_pitch", "right_ankle_roll",
)
BODY_ASSETS = {
    "v0_1": "body_3d.xml", "v0_2": "body_3d_v0_2.xml", "v0_3": "body_3d_v0_3.xml",
    "v1_0": "body_v1_0_female.xml",
}
# Spec-driven bodies take joints, strength, injury thresholds and stance from a
# research spec instead of the hand-written tables below.
BODY_SPECS = {"v1_0": "configs/research/body_v1_0_female.json"}
BODY_TRUNK = {"v1_0": "Chest"}          # default "torso_body"
BODY_HEIGHT_M = {"v1_0": 1.60}          # default 1.2; scales dimensionless pushes
FALL_TRUNK_HEIGHT_M = {"v1_0": 0.70}    # default FALL_TORSO_HEIGHT_M
# v1.0 stance: arms 10 deg abducted and elbows 10 deg flexed so they clear the trunk.
V1_STANCE_DEG = {"L_Shoulder_x": 10.0, "R_Shoulder_x": -10.0,
                 "L_Elbow_y": -10.0, "R_Elbow_y": -10.0}
V1_PART = {"Pelvis": "torso", "Torso": "torso", "Spine": "torso", "Chest": "torso",
           "Neck": "head", "Head": "head", "Thorax": "arm", "Shoulder": "arm",
           "Elbow": "arm", "Wrist": "arm", "Hand": "arm", "Hip": "leg", "Knee": "leg",
           "Ankle": "leg", "Toe": "leg"}
# Full torque at this joint error defines the v1.0 PD stiffness (kp = limit / error).
V1_KP_FULL_TORQUE_RAD = 0.25
V1_KD_RATIO = 1.0 / 20.0
BODY_JOINTS = {
    "v0_1": JOINT_NAMES,
    "v0_2": JOINT_NAMES,
    "v0_3": JOINT_NAMES + ANKLE_JOINT_NAMES,
}
BODY_JOINT_PARTS = {
    "v0_1": JOINT_PARTS,
    "v0_2": JOINT_PARTS,
    "v0_3": JOINT_PARTS + ("left_leg", "left_leg", "right_leg", "right_leg"),
}
BODY_TORQUE_LIMITS = {
    "v0_1": (35, 25, 18, 20, 35, 25, 18, 20, 60, 40, 30, 45, 60, 40, 30, 45),
    "v0_2": (35, 25, 18, 20, 35, 25, 18, 20, 60, 40, 30, 45, 60, 40, 30, 45),
    "v0_3": (35, 25, 18, 20, 35, 25, 18, 20, 60, 40, 30, 45, 60, 40, 30, 45,
             30, 20, 30, 20),
}
MODES = ("task", "balance")
# Curriculum stage 1: straight legs on flat feet, elbows slightly bent.
BALANCE_STANCE = np.array(
    [0.0, 0.0, 0.0, -0.25, 0.0, 0.0, 0.0, -0.25,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
)
BALANCE_ROOT_HEIGHT = 0.642  # v0.2/v0.3 feet start 2 mm above the floor in the stance.
BALANCE_EPISODE_SECONDS = 10.0
# Fraction of each joint's half-range one unit of action may offset from the
# stance; full authority let PPO learn bang-bang kicks that topple the body.
BALANCE_ACTION_SCALE = 0.25
# v0.3 legs (hips, knees, ankles) get more authority so stepping is reachable.
BALANCE_LEG_ACTION_SCALE = {"v0_2": 0.25, "v0_3": 0.6, "v1_0": 0.6}
# Ankle PD gains: with the shared kp=55 the body (m*g*h ~ 137 Nm/rad about the
# ankles) collapses at once; 2 x 150 Nm/rad gives ~2x the gravitational stiffness.
ANKLE_KP = 150.0
ANKLE_KD = 5.0
# Pushes beyond the feet-in-place limit (~0.127 for v0.2) that need a step.
HARD_PUSH_RANGE = (0.13, 0.25)
# Capture-point shaping: a bonus when a swing foot lands near the instantaneous
# capture point CoM + v / omega0 after the push (Hof 2005; Poddar et al. 2026).
CAPTURE_SIGMA_M = 0.10
CAPTURE_MIN_AIR_STEPS = 4      # 0.08 s airborne before a landing counts as a step
CAPTURE_MAX_REWARDED_STEPS = 3
# Natural-stance rule (posture_version 2): relaxed standing is free, bracing is not.
# Feet may drift 8 cm (weight shifts, small foot moves) before any penalty; lowering
# the CoM by > 3 cm (crouching) or leaning the trunk > 10 deg before the push is
# penalised. The summed penalty is capped at the weight so the per-step reward stays
# positive and falling never becomes the better option. Values are starting choices,
# to be replaced by postural-sway data.
NATURAL_FEET_DEADZONE_M = 0.08
NATURAL_CROUCH_LIMIT_M = 0.03
NATURAL_LEAN_LIMIT_RAD = np.radians(10.0)
# posture_version 3: same dead zones, but the cost never stops growing. v2's cap was
# reached at 18 cm drift, so a policy that wanted a wide stance paid the same price
# for 30 cm (seed 63002, 7 Oct). v3 makes foot drift past the dead zone linear (not
# quadratic, so 9 cm already costs) and removes a share s / (s + half) of the
# pre-penalty reward: the cost rises with every extra centimetre and the per-step
# reward stays positive, so falling never becomes the better option.
NATURAL_V3_HALF_SCORE = 0.5
# Relaxed-stance start: pelvis shifted over one foot (both hips +/- 0.06 rad about x)
# and feet set slightly wider or narrower (+/- per-hip spread).
NATURAL_SHIFT_RAD = 0.06
NATURAL_SPREAD_RAD = (-0.02, 0.04)
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
        hard_push_fraction: float = 0.0,
        posture_weight: float = 0.0,
        capture_point_weight: float = 0.0,
        posture_version: int = 1,
        natural_stance: bool = False,
        hard_push_range: tuple[float, float] | None = None,
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
            raise ValueError("balance mode needs a body with feet (v0_2 or v0_3)")
        if mode == "task" and body in ("v0_3", "v1_0"):
            raise ValueError(f"{body} is only wired for balance mode so far")
        if not 0.0 <= hard_push_fraction <= 1.0:
            raise ValueError("hard_push_fraction must be in [0, 1]")
        self.hard_push_fraction = float(hard_push_fraction)
        # Curriculum step (a): penalise changing the foot placement before the push,
        # so the policy cannot pre-widen its stance and must step reactively.
        self.posture_weight = float(posture_weight)
        self.capture_point_weight = float(capture_point_weight)
        if posture_version not in (1, 2, 3):
            raise ValueError("posture_version must be 1, 2 or 3")
        self.posture_version = posture_version
        self.natural_stance = bool(natural_stance)
        if natural_stance and body not in BODY_SPECS:
            raise ValueError("natural_stance needs a spec body (v1_0)")
        self.hard_push_range = tuple(hard_push_range or HARD_PUSH_RANGE)
        self.body_height = BODY_HEIGHT_M.get(body, 1.2)
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

        self.geom_injury_threshold: dict[int, float] = {}
        if body in BODY_SPECS:
            joint_names = self._init_spec_body(body)
        else:
            joint_names = BODY_JOINTS[body]
            self.joint_parts = BODY_JOINT_PARTS[body]
            self.base_limits = np.array(BODY_TORQUE_LIMITS[body], dtype=np.float64)
            self.stance = np.zeros(len(joint_names))
            self.stance[:16] = BALANCE_STANCE
            is_ankle = np.array([name in ANKLE_JOINT_NAMES for name in joint_names])
            self.kp = np.where(is_ankle, ANKLE_KP, self.config.kp)
            self.kd = np.where(is_ankle, ANKLE_KD, self.config.kd)
        n_joints = len(joint_names)
        self.action_scale = np.array([
            BALANCE_LEG_ACTION_SCALE.get(body, BALANCE_ACTION_SCALE)
            if part.endswith("_leg") else BALANCE_ACTION_SCALE
            for part in self.joint_parts
        ])
        joint_ids = np.array([
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            for name in joint_names
        ])
        if np.any(joint_ids < 0):
            raise RuntimeError("3D asset is missing an expected joint")
        self.actuated_qpos = self.model.jnt_qposadr[joint_ids].copy()
        self.actuated_qvel = self.model.jnt_dofadr[joint_ids].copy()
        if body in BODY_SPECS:
            self.model.dof_damping[self.actuated_qvel] += self._implicit_kd
        self.joint_ranges = self.model.jnt_range[joint_ids].copy()
        self.torso_body_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, BODY_TRUNK.get(body, "torso_body")
        )
        self.fall_trunk_height = FALL_TRUNK_HEIGHT_M.get(body, FALL_TORSO_HEIGHT_M)
        self.hand_site_ids = np.array([
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "left_hand"),
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "right_hand"),
        ])
        if body not in BODY_SPECS:
            self.geom_part: dict[int, str] = {}
        for geom_id in range(0 if body in BODY_SPECS else self.model.ngeom):
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
        # Two sole geoms (not toes) define the stance vector for the posture term.
        soles = sorted(
            geom_id for geom_id in self.foot_geom_ids
            if "toe" not in (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or "")
        )
        self.sole_geom_ids = soles if len(soles) == 2 else []
        self._nominal_feet = np.zeros(2)
        self._foot_air_steps = [0, 0]
        self._rewarded_steps = 0
        self._previous_com = np.zeros(3)
        self._reference_com_height = 0.0
        self._joint_index = {
            mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, int(joint_id)): index
            for index, joint_id in enumerate(joint_ids)
        }

        self.action_space = spaces.Box(-1.0, 1.0, shape=(n_joints,), dtype=np.float32)
        # joint angle/velocity 2n, base velocity 6, body gravity 3, task one-hot 2,
        # 3-D target + mask, prior action n, damage 6, time 1 (70 for 16 joints).
        self.observation_space = spaces.Box(
            low=-1.0e6, high=1.0e6, shape=(3 * n_joints + 22,), dtype=np.float32
        )
        self.previous_action = np.zeros(n_joints, dtype=np.float32)
        self.elapsed_steps = 0
        self.contact_counts = {name: 0 for name in PARTS}
        self.max_contact_loads = {name: 0.0 for name in PARTS}
        self.last_applied_torque = np.zeros(n_joints, dtype=np.float64)
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

    def _init_spec_body(self, body: str) -> list[str]:
        """Joints, strength, PD gains, stance and injury sites from a research spec."""
        root = Path(__file__).resolve().parents[2]
        spec = json.loads((root / BODY_SPECS[body]).read_text(encoding="utf-8"))
        model = self.model
        names, parts, limits = [], [], []
        for joint_id in range(model.njnt):
            if model.jnt_type[joint_id] != mujoco.mjtJoint.mjJNT_HINGE:
                continue
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
            body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY,
                                          int(model.jnt_bodyid[joint_id]))
            segment, axis = body_name.split("_")[-1], name[-1]
            names.append(name)
            parts.append(self._spec_part(body_name))
            limits.append(float(spec["torque_limit_Nm"][segment][axis]))
        self.joint_parts = tuple(parts)
        self.base_limits = np.array(limits, dtype=np.float64)
        self.kp = self.base_limits / V1_KP_FULL_TORQUE_RAD
        # The derivative gain goes into MuJoCo's joint damping, which implicitfast
        # integrates implicitly. Applied explicitly it chattered on the short spine
        # segments (kd * dt / I > 2) and the body collapsed within 1 s.
        self._implicit_kd = self.kp * V1_KD_RATIO
        self.kd = np.zeros_like(self.kp)
        self.stance = np.array([np.radians(V1_STANCE_DEG.get(name, 0.0)) for name in names])
        self.geom_part = {}
        for geom_id in range(model.ngeom):
            body_id = int(model.geom_bodyid[geom_id])
            if body_id == 0:
                continue  # floor
            body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
            segment = body_name.split("_")[-1]
            self.geom_part[geom_id] = self._spec_part(body_name)
            self.geom_injury_threshold[geom_id] = (
                1000.0 * float(spec["segments"][segment]["injury_kN"])
            )
        return names

    @staticmethod
    def _spec_part(body_name: str) -> str:
        part = V1_PART[body_name.split("_")[-1]]
        if part in ("arm", "leg"):
            return ("left_" if body_name.startswith("L_") else "right_") + part
        return part

    def _torso_xyz(self) -> np.ndarray:
        return self.data.xpos[self.torso_body_id].copy()

    def _hand_xyz(self) -> np.ndarray:
        if np.any(self.hand_site_ids < 0):  # spec bodies have no hand sites yet
            return np.repeat(self._torso_xyz()[None, :], 2, axis=0)
        return self.data.site_xpos[self.hand_site_ids].copy()

    def _feet_vector(self) -> np.ndarray:
        left, right = self.sole_geom_ids
        return (self.data.geom_xpos[left] - self.data.geom_xpos[right])[:2].copy()

    def _sample_push(self) -> None:
        # Same draw order in every mode so task-mode benchmark streams are unchanged.
        start_range = (1.0, 3.0) if self.mode == "balance" else (2.0, 4.0)
        self.push_start = float(self.push_rng.uniform(*start_range))
        self.push_duration = float(self.push_rng.uniform(0.05, 0.15))
        dimensionless_impulse = float(self.push_rng.uniform(0.0, self.max_push_impulse))
        # Extra draws only when enabled, so default push streams stay unchanged.
        if self.hard_push_fraction > 0.0 and self.push_rng.uniform() < self.hard_push_fraction:
            dimensionless_impulse = float(self.push_rng.uniform(*self.hard_push_range))
        self.push_impulse = dimensionless_impulse
        angle = float(self.push_rng.uniform(-np.pi, np.pi))
        total_mass = float(np.sum(self.model.body_mass))
        impulse_ns = dimensionless_impulse * total_mass * np.sqrt(9.81 * self.body_height)
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
        if self.mode == "balance":
            if self.body not in BODY_SPECS:  # spec bodies keep the asset's root height
                self.data.qpos[2] = BALANCE_ROOT_HEIGHT
            self.data.qpos[self.actuated_qpos] = self.stance
        else:
            self.data.qpos[self.actuated_qpos] = crouch
        if self.natural_stance:
            self._apply_natural_stance()
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
        if self.sole_geom_ids:
            self._nominal_feet = self._feet_vector()
        self._reference_com_height = float(self.data.subtree_com[1][2])
        self._foot_air_steps = [0, 0]
        self._rewarded_steps = 0
        self._previous_com = self.data.subtree_com[1].copy()
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
                self.stance
                + np.asarray(action, dtype=np.float64) * self.action_scale * half_ranges,
                self.joint_ranges[:, 0], self.joint_ranges[:, 1],
            )
        else:
            targets = centers + np.asarray(action, dtype=np.float64) * half_ranges
        return (
            self.kp * (targets - self.data.qpos[self.actuated_qpos])
            - self.kd * self.data.qvel[self.actuated_qvel]
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
                    tolerance = self.geom_injury_threshold.get(geom)
                    if tolerance is not None:
                        # Express the load relative to this site's literature
                        # tolerance, on the damage model's per-part scale.
                        load = (magnitude * self.damage_model.parameters.threshold_n[part]
                                / tolerance)
                    else:
                        load = magnitude
                    loads[part] = max(loads[part], load)
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
                self.damage_model.damage, self.impairment_enabled, self.joint_parts,
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
            self._torso_xyz()[2] < self.fall_trunk_height
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
        posture_penalty = 0.0
        if (self.posture_weight > 0.0 and not self.fallen and self.sole_geom_ids
                and float(self.data.time) < self.push_start):
            drift = float(np.linalg.norm(self._feet_vector() - self._nominal_feet))
            if self.posture_version == 1:
                posture_penalty = self.posture_weight * min(1.0, (drift / 0.10) ** 2)
            elif self.posture_version == 3:
                score = self.posture_weight * self._bracing_score(drift, upright, linear_drift=True)
                posture_penalty = max(0.0, reward) * score / (score + NATURAL_V3_HALF_SCORE)
            else:
                posture_penalty = self.posture_weight * min(1.0, self._bracing_score(drift, upright))
            reward -= posture_penalty
        capture_bonus = self._capture_point_bonus() if not self.fallen else 0.0
        reward += capture_bonus
        self.previous_action[:] = action
        self.elapsed_steps += 1
        terminated = self.fallen or self.elapsed_steps >= self.config.max_episode_steps
        observation = self._get_observation(sample_sensor=True)
        info = self._info(total_increment, success=False)
        info["step_peak_contact_loads_n"] = step_peak_loads
        info["reward_task"] = 0.0
        info["reward_damage_penalty"] = 0.0
        info["reward_balance"] = reward
        info["posture_penalty"] = posture_penalty
        info["capture_point_bonus"] = capture_bonus
        info["fallen"] = self.fallen
        info["push_impulse"] = self.push_impulse
        return observation, reward, terminated, False, info

    def _bracing_score(self, drift: float, upright: float, linear_drift: bool = False) -> float:
        """0 for relaxed standing; grows with wide stance, crouching and leaning."""
        crouch = self._reference_com_height - float(self.data.subtree_com[1][2])
        lean = float(np.arccos(np.clip(upright, -1.0, 1.0)))
        excess = max(0.0, drift - NATURAL_FEET_DEADZONE_M) / 0.10
        return (
            (excess if linear_drift else excess ** 2)
            + (max(0.0, crouch - NATURAL_CROUCH_LIMIT_M) / 0.05) ** 2
            + (max(0.0, lean - NATURAL_LEAN_LIMIT_RAD) / NATURAL_LEAN_LIMIT_RAD) ** 2
        )

    def _apply_natural_stance(self) -> None:
        """Start from a relaxed stance: weight over one foot, varied foot spacing."""
        shift = float(self.initial_rng.uniform(-NATURAL_SHIFT_RAD, NATURAL_SHIFT_RAD))
        spread = float(self.initial_rng.uniform(*NATURAL_SPREAD_RAD))
        qpos = self.data.qpos
        for side, sign in (("L", 1.0), ("R", -1.0)):
            # Rotation about +x moves either foot toward +y; ankles undo it so the
            # soles stay flat. A common angle shifts the pelvis, +/- spread widens.
            hip = -shift + sign * spread
            qpos[self.actuated_qpos[self._joint_index[f"{side}_Hip_x"]]] = hip
            qpos[self.actuated_qpos[self._joint_index[f"{side}_Ankle_x"]]] = -hip
        mujoco.mj_forward(self.model, self.data)
        # Re-seat the body so the lowest sole corner sits 2 mm above the floor.
        lowest = min(self._lowest_point(geom) for geom in self.foot_geom_ids)
        qpos[2] += 0.002 - lowest

    def _lowest_point(self, geom: int) -> float:
        center = self.data.geom_xpos[geom]
        rotation = self.data.geom_xmat[geom].reshape(3, 3)
        half = self.model.geom_size[geom]
        corners = [center + rotation @ (half * np.array([sx, sy, sz]))
                   for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        return min(float(corner[2]) for corner in corners)

    def _capture_point_bonus(self) -> float:
        """Reward the first few post-push landings by distance to the capture point."""
        com = self.data.subtree_com[1].copy()
        velocity = (com - self._previous_com) / self.config.control_dt
        self._previous_com = com
        if self.capture_point_weight <= 0.0 or not self.sole_geom_ids:
            return 0.0
        touching = set()
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            touching.update((int(contact.geom1), int(contact.geom2)))
        omega0 = np.sqrt(9.81 / max(float(com[2]), 0.1))
        capture_point = com[:2] + velocity[:2] / omega0
        bonus = 0.0
        after_push = float(self.data.time) >= self.push_start
        for side, geom in enumerate(self.sole_geom_ids):
            if geom not in touching:
                self._foot_air_steps[side] += 1
                continue
            landed = self._foot_air_steps[side] >= CAPTURE_MIN_AIR_STEPS
            self._foot_air_steps[side] = 0
            if landed and after_push and self._rewarded_steps < CAPTURE_MAX_REWARDED_STEPS:
                distance = float(np.linalg.norm(self.data.geom_xpos[geom][:2] - capture_point))
                bonus += self.capture_point_weight * np.exp(-(distance / CAPTURE_SIGMA_M) ** 2)
                self._rewarded_steps += 1
        return bonus

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
