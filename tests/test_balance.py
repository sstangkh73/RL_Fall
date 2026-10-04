import numpy as np
import pytest

from rl_fall.env3d import RLFall3DEnv


def _stance_action(env: RLFall3DEnv) -> np.ndarray:
    # Balance-mode actions are offsets from the stance.
    return np.zeros(env.action_space.shape, dtype=np.float32)


def test_v0_2_keeps_mass_dof_and_spaces():
    env = RLFall3DEnv(condition="A", seed=1, body="v0_2", mode="balance")
    np.testing.assert_allclose(np.sum(env.model.body_mass), 20.0)
    assert env.model.nq == 23 and env.model.nv == 22
    assert env.action_space.shape == (16,)
    assert env.observation_space.shape == (70,)
    assert len(env.foot_geom_ids) == 2
    assert env.config.max_episode_steps == 500


def test_balance_mode_requires_feet():
    with pytest.raises(ValueError):
        RLFall3DEnv(condition="A", body="v0_1", mode="balance")


def test_balance_reset_starts_clear_of_floor_with_task_slots_zeroed():
    env = RLFall3DEnv(condition="A", seed=4, body="v0_2", mode="balance")
    observation, _ = env.reset(seed=4)
    assert env.data.ncon == 0
    assert np.isfinite(observation).all()
    np.testing.assert_array_equal(observation[41:47], np.zeros(6))


def test_passive_stance_stands_without_push():
    env = RLFall3DEnv(condition="A", seed=2, body="v0_2", mode="balance",
                      max_push_impulse=0.0)
    env.reset(seed=2)
    action = _stance_action(env)
    for _ in range(150):
        _, reward, terminated, _, info = env.step(action)
        assert not terminated
        assert not info["fallen"]
        assert reward > 1.0


def test_lying_body_is_a_terminal_fall_with_zero_reward():
    env = RLFall3DEnv(condition="A", seed=3, body="v0_2", mode="balance")
    env.reset(seed=3)
    qpos = env.data.qpos.copy()
    qpos[2] = 0.15
    qpos[3:7] = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]  # torso pitched 90 degrees
    env.reset(seed=3, options={"qpos": qpos})
    _, reward, terminated, truncated, info = env.step(np.zeros(16, dtype=np.float32))
    assert terminated and not truncated
    assert info["fallen"]
    assert reward == 0.0


def test_task_mode_defaults_are_unchanged():
    default = RLFall3DEnv(seed=9)
    explicit = RLFall3DEnv(seed=9, body="v0_1", mode="task", max_push_impulse=0.45)
    obs_a, _ = default.reset(seed=9)
    obs_b, _ = explicit.reset(seed=9)
    np.testing.assert_array_equal(obs_a, obs_b)
    assert default.push_start == explicit.push_start
    np.testing.assert_array_equal(default.push_force_world, explicit.push_force_world)
