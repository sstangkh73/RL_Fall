import numpy as np
from gymnasium.utils.env_checker import check_env
from stable_baselines3.common.vec_env import DummyVecEnv

from rl_fall.damage import PART_INDEX
from rl_fall.env import CONDITIONS, EnvironmentConfig, RLFallEnv


def test_gym_api_and_seeded_reset_are_repeatable():
    env = RLFallEnv(seed=42)
    check_env(env, skip_render_check=True)
    first, _ = env.reset(seed=42)
    second, _ = env.reset(seed=42)
    np.testing.assert_array_equal(first, second)
    assert first.shape == (41,)


def test_all_four_conditions_match_factorial_design():
    expected = {
        "A": (False, False), "B": (True, False),
        "C": (False, True), "D": (True, True),
    }
    for name, (impairment, penalty) in expected.items():
        env = RLFallEnv(condition=name)
        assert env.impairment_enabled is impairment
        assert env.penalty_enabled is penalty
        assert CONDITIONS[name] == {"impairment": impairment, "penalty": penalty}


def test_fall_or_total_damage_does_not_end_episode_early():
    env = RLFallEnv(condition="B", seed=1)
    env.reset(options={"damage": np.ones(6)})
    env.data.qpos[1] = -0.4
    _, _, terminated, truncated, info = env.step(np.zeros(8, dtype=np.float32))
    assert not terminated
    assert not truncated
    assert info["damage"] == [1.0] * 6


def test_target_is_zero_with_mask_when_head_fully_damaged():
    env = RLFallEnv(condition="B", seed=2)
    env.reset(options={"damage": np.array([1, 0, 0, 0, 0, 0], dtype=float)})
    observation = env._get_observation(sample_sensor=True)
    np.testing.assert_array_equal(observation[23:25], np.zeros(2))
    assert observation[25] == 0.0
    assert env.damage_model.damage[PART_INDEX["head"]] == 1.0


def test_task_horizon_is_terminal_and_vecenv_preserves_terminal_observation():
    config = EnvironmentConfig(condition="B", episode_seconds=0.04)
    vec = DummyVecEnv([lambda: RLFallEnv(condition="B", seed=9, config=config)])
    vec.reset()
    _, _, dones, infos = vec.step(np.zeros((1, 8), dtype=np.float32))
    assert not dones[0]
    reset_observation, _, dones, infos = vec.step(np.zeros((1, 8), dtype=np.float32))
    assert dones[0]
    assert "terminal_observation" in infos[0]
    terminal = infos[0]["terminal_observation"]
    assert terminal[-1] == 0.0
    assert reset_observation[0, -1] == 1.0


def test_damage_penalty_only_in_c_and_d():
    action = np.zeros(8, dtype=np.float32)
    for condition in "ABCD":
        env = RLFallEnv(condition=condition, seed=5)
        env.reset()
        _, _, _, _, info = env.step(action)
        if condition in "AB":
            assert info["reward_damage_penalty"] == 0.0
        else:
            assert info["reward_damage_penalty"] <= 0.0
