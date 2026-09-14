from pathlib import Path

import mujoco
import numpy as np


def test_planar_model_has_eight_actuated_joints_and_expected_mass():
    asset = Path(__file__).resolve().parents[1] / "assets" / "planar_body.xml"
    model = mujoco.MjModel.from_xml_path(str(asset))
    # Three unactuated planar root DoFs plus eight controlled joints.
    assert model.njnt == 11
    assert model.nv == 11
    np.testing.assert_allclose(np.sum(model.body_mass), 20.0, rtol=0, atol=1e-10)
    assert model.opt.timestep == 0.002


def test_environment_joint_targets_match_xml_ranges_and_pose_has_no_penetration():
    from rl_fall.env import RLFallEnv

    env = RLFallEnv(seed=4)
    env.reset(seed=4)
    np.testing.assert_allclose(env.model.jnt_range[3:], env.joint_ranges)
    assert env.data.ncon == 0


def test_physics_state_remains_finite_under_short_random_trace():
    from rl_fall.env import RLFallEnv

    env = RLFallEnv(seed=11)
    env.reset(seed=11)
    rng = np.random.default_rng(11)
    for _ in range(200):
        env.step(rng.uniform(-1, 1, size=8).astype(np.float32))
        assert np.isfinite(env.data.qpos).all()
        assert np.isfinite(env.data.qvel).all()
