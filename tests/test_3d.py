import mujoco
import numpy as np

from rl_fall.damage import PART_INDEX, apply_functional_limits
from rl_fall.env import EnvironmentConfig
from rl_fall.env3d import JOINT_PARTS, RLFall3DEnv


def test_3d_model_has_free_root_16_actuated_joints_and_locked_mass():
    env = RLFall3DEnv(seed=1)
    assert env.model.nq == 23
    assert env.model.nv == 22
    assert env.action_space.shape == (16,)
    assert env.observation_space.shape == (70,)
    assert len(env.actuated_qpos) == len(env.actuated_qvel) == 16
    np.testing.assert_allclose(np.sum(env.model.body_mass), 20.0)
    root_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, "root")
    assert env.model.jnt_type[root_id] == mujoco.mjtJoint.mjJNT_FREE


def test_3d_reset_is_seeded_finite_and_clear_of_floor_contact():
    first = RLFall3DEnv(seed=7)
    second = RLFall3DEnv(seed=99)
    obs_a, _ = first.reset(seed=123)
    obs_b, _ = second.reset(seed=123)
    np.testing.assert_array_equal(obs_a, obs_b)
    assert np.isfinite(obs_a).all()
    assert first.data.ncon == 0


def test_3d_motion_is_not_planar_constrained():
    env = RLFall3DEnv(seed=3)
    env.reset(seed=3)
    before_y = float(env.data.qpos[1])
    env.data.qvel[1] = 0.5
    for _ in range(3):
        observation, *_ = env.step(np.zeros(16, dtype=np.float32))
    assert float(env.data.qpos[1]) != before_y
    assert np.isfinite(observation).all()


def test_3d_limb_damage_maps_to_four_axes_and_torso_caps_all_joints():
    limits = np.array(
        [35, 25, 18, 20, 35, 25, 18, 20,
         60, 40, 30, 45, 60, 40, 30, 45], dtype=float
    )
    damage = np.zeros(6)
    damage[PART_INDEX["left_arm"]] = 0.5
    applied = apply_functional_limits(
        np.full(16, 1000.0), limits, damage, True, JOINT_PARTS
    )
    np.testing.assert_allclose(applied[:4], limits[:4] * 0.5)
    np.testing.assert_allclose(applied[4:], limits[4:])

    damage[:] = 0.0
    damage[PART_INDEX["torso"]] = 0.75
    capped = apply_functional_limits(limits, limits, damage, True, JOINT_PARTS)
    assert np.sum(np.abs(capped) / limits) <= 16 * 0.25 + 1e-12


def test_3d_head_damage_masks_all_target_coordinates_without_leak():
    env = RLFall3DEnv(seed=5)
    damage = np.zeros(6)
    damage[PART_INDEX["head"]] = 1.0
    observation, _ = env.reset(seed=5, options={"damage": damage})
    np.testing.assert_array_equal(observation[43:46], np.zeros(3))
    assert observation[46] == 0.0


def test_3d_episode_horizon_is_terminal_not_truncated():
    config = EnvironmentConfig(condition="B", episode_seconds=0.04)
    env = RLFall3DEnv(condition="B", seed=8, config=config)
    env.reset(seed=8)
    _, _, terminated, truncated, _ = env.step(np.zeros(16, dtype=np.float32))
    assert not terminated and not truncated
    _, _, terminated, truncated, _ = env.step(np.zeros(16, dtype=np.float32))
    assert terminated and not truncated
