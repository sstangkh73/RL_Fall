import csv

import gymnasium as gym
import numpy as np
import pytest
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl_fall import train
from rl_fall.train import AnchorNormalizer, AnchorSamplesCallback, anchor_step, create_model


class TinyEnv(gym.Env):
    observation_space = gym.spaces.Box(-100, 100, shape=(3,), dtype=np.float32)
    action_space = gym.spaces.Box(-1, 1, shape=(2,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.steps = 0
        return np.zeros(3, dtype=np.float32), {}

    def step(self, action):
        self.steps += 1
        obs = np.array([self.steps, *action], dtype=np.float32)
        return obs, -float(np.square(action).sum()), self.steps == 5, False, {
            "fallen": self.steps >= 3, "push_impulse": 0.06,
        }


def _env(n_envs=1):
    return VecNormalize(DummyVecEnv([TinyEnv for _ in range(n_envs)]))


def _model(env, seed=5):
    torch.set_num_threads(1)
    return create_model(env, "cpu", seed, n_steps=64, network_width=8,
                        learning_rate=3e-3, batch_size=32, n_epochs=2)


def test_anchor_step_reduces_kl_without_changing_critic_or_frozen_policy():
    env = _env()
    try:
        model, frozen = _model(env), _model(env, seed=7)
        with torch.no_grad():
            frozen.policy.action_net.bias.add_(0.7)
        frozen.policy.requires_grad_(False)
        obs_s2 = torch.randn(128, 3)
        obs_anchor = obs_s2 * 0.5 + 0.2
        # Give the critic Adam moments and leftover PPO gradients. The anchor
        # must clear those gradients so even a previously trained critic stays fixed.
        model.policy.predict_values(obs_s2).square().mean().backward()
        model.policy.optimizer.step()
        before = {key: value.clone() for key, value in model.policy.state_dict().items()}
        frozen_before = {key: value.clone() for key, value in frozen.policy.state_dict().items()}

        kl_before, kl_after = anchor_step(model, frozen.policy, obs_s2, obs_anchor,
                                         coef=1.0, epochs=5, batch_size=32)

        assert 0 <= kl_after < kl_before
        critic_keys = [key for key in before if key.startswith(
            ("mlp_extractor.value_net.", "value_net."))]
        assert critic_keys
        assert all(torch.equal(before[key], model.policy.state_dict()[key])
                   for key in critic_keys)
        assert all(torch.equal(value, frozen.policy.state_dict()[key])
                   for key, value in frozen_before.items())
        assert all(parameter.grad is None for parameter in frozen.policy.parameters())
    finally:
        env.close()


def test_callback_uses_previous_fall_flag_resets_on_done_and_converts_normalization():
    env = _env(2)
    try:
        env.obs_rms.mean[:] = [1, 2, 3]
        env.obs_rms.var[:] = [4, 9, 16]
        rms = train.RunningMeanStd(shape=(3,))
        rms.mean[:] = [-1, 0, 1]
        rms.var[:] = [1, 4, 9]
        normalizer = AnchorNormalizer(rms, clip_obs=3.0, epsilon=1e-6)
        callback = AnchorSamplesCallback(env, normalizer, max_impulse=0.08)
        observations = torch.tensor([[1., 2., 3.], [4., 5., 6.]])

        def step(fallen, impulses, dones=(False, False)):
            callback.locals = {
                "obs_tensor": observations, "dones": dones,
                "infos": [{"fallen": fall, "push_impulse": impulse}
                          for fall, impulse in zip(fallen, impulses)],
            }
            assert callback._on_step()

        # The action causing a fall is eligible; its input observation was upright.
        # The upper-limit tolerance accepts env 0 and rejects env 1.
        step((True, False), (0.08 + 0.5e-9, 0.08 + 2e-9))
        obs_s2, obs_anchor = callback.samples()
        np.testing.assert_array_equal(obs_s2, observations[:1].numpy())
        raw = obs_s2 * np.sqrt(env.obs_rms.var + env.epsilon) + env.obs_rms.mean
        expected = np.clip((raw - rms.mean) / np.sqrt(rms.var + normalizer.epsilon), -3, 3)
        np.testing.assert_allclose(obs_anchor, expected, rtol=1e-6)
        np.testing.assert_array_equal(rms.mean, [-1, 0, 1])
        np.testing.assert_array_equal(rms.var, [1, 4, 9])

        # A new rollout clears samples but must remember an ongoing fall.
        callback._on_rollout_start()
        step((True, False), (0.06, 0.2))
        assert len(callback.samples()[0]) == 0
        # A terminal fallen observation is excluded before resetting its flag.
        step((True, False), (0.06, 0.2), dones=(True, False))
        assert len(callback.samples()[0]) == 0
        step((False, False), (0.06, 0.06))
        assert len(callback.samples()[0]) == 2
    finally:
        env.close()


@pytest.mark.parametrize("name", ["checkpoint", "checkpoint_update_7"])
def test_anchor_normalizer_loads_matching_frozen_statistics(tmp_path, name):
    env = _env()
    try:
        env.obs_rms.mean[:] = [1, 2, 3]
        env.clip_obs, env.epsilon = 5.0, 1e-6
        env.save(tmp_path / (name.replace("checkpoint", "vecnormalize") + ".pkl"))
        frozen = AnchorNormalizer.load(tmp_path / f"{name}.zip")
        env.obs_rms.update(np.full((4, 3), 100.0))
        np.testing.assert_array_equal(frozen.obs_rms.mean, [1, 2, 3])
        assert frozen.clip_obs == 5.0
        assert frozen.epsilon == 1e-6
    finally:
        env.close()


def test_positive_anchor_requires_explicit_checkpoint_even_with_init_or_resume(tmp_path):
    for options in ({}, {"init_checkpoint": tmp_path / "init.zip"},
                    {"resume_dir": tmp_path / "resume"}):
        with pytest.raises(ValueError, match="anchor_checkpoint"):
            train.run_training(tmp_path, "cpu", "B", 5, 1, "dummy", 1, 0, 1,
                               anchor_coef=1.0, **options)
    assert not list(tmp_path.iterdir())


def _tiny_training(monkeypatch):
    monkeypatch.setattr(train, "TOTAL_ROLLOUT_TRANSITIONS", 64)
    monkeypatch.setattr(train, "make_vec_env", lambda *args, **kwargs: _env())
    monkeypatch.setattr(train, "evaluate", lambda *args, **kwargs: {})
    return dict(device="cpu", condition="B", seed=5, n_envs=1, wrapper="dummy",
                threads=1, warmup_updates=0, evaluation_scenarios=1,
                environment="planar", network_width=8)


def test_training_logs_anchor_skips_critic_warmup_and_keeps_s1_on_resume(tmp_path, monkeypatch):
    common = _tiny_training(monkeypatch)
    env = _env()
    checkpoint = tmp_path / "checkpoint.zip"
    initial_checkpoint = tmp_path / "initial" / "checkpoint.zip"
    initial_checkpoint.parent.mkdir()
    try:
        _model(env).save(initial_checkpoint)
        env.save(initial_checkpoint.with_name("vecnormalize.pkl"))
        frozen = _model(env, seed=7)
        with torch.no_grad():
            frozen.policy.action_net.bias.add_(0.7)
        frozen.save(checkpoint)
        env.save(tmp_path / "vecnormalize.pkl")
    finally:
        env.close()
    calls = []
    real_step = train.anchor_step

    def tracked_step(model, policy, *args):
        assert all(not parameter.requires_grad for parameter in policy.parameters())
        assert all(torch.equal(value, frozen.policy.state_dict()[key])
                   for key, value in policy.state_dict().items())
        calls.append(len(args[0]))
        epochs.append(args[3])
        return real_step(model, policy, *args)

    epochs = []

    monkeypatch.setattr(train, "anchor_step", tracked_step)
    result = train.run_training(
        tmp_path / "run", measured_updates=2, checkpoint_updates=(0, 1, 2),
        init_checkpoint=initial_checkpoint, critic_warmup_updates=1, anchor_coef=1.0,
        anchor_checkpoint=checkpoint, max_push_impulse=0.08,
        learning_rate=1e-4, **common,
    )
    run_dir = tmp_path / "run" / result["run_id"]
    assert len(calls) == 1 and calls[0] > 0
    initial = PPO.load(run_dir / "checkpoint_update_0.zip").policy.state_dict()
    warm = PPO.load(run_dir / "checkpoint_update_1.zip").policy.state_dict()
    actor_keys = [key for key in initial if key.startswith(
        ("mlp_extractor.policy_net.", "action_net.", "log_std"))]
    assert all(torch.equal(initial[key], warm[key]) for key in actor_keys)

    resumed = train.run_training(
        tmp_path / "run", measured_updates=3, resume_dir=run_dir,
        critic_warmup_updates=1, anchor_coef=1.0, anchor_checkpoint=checkpoint,
        max_push_impulse=0.08, anchor_max_impulse=0.07, anchor_epochs=1, **common,
    )
    assert len(calls) == 2
    assert epochs == [train.CURRICULUM_PPO["n_epochs"], 1]
    assert result["anchor_epochs"] == train.CURRICULUM_PPO["n_epochs"]
    assert resumed["anchor_epochs"] == 1
    assert resumed["anchor_checkpoint"] == str(checkpoint)
    assert resumed["anchor_coef"] == 1.0
    assert result["anchor_max_impulse"] == 0.08
    assert resumed["anchor_max_impulse"] == 0.07
    with (run_dir / "updates.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3
    assert all(int(row["anchor_samples"]) > 0 for row in rows)
    assert float(rows[0]["anchor_kl_before"]) == float(rows[0]["anchor_kl_after"]) == 0
    assert all(float(row["anchor_kl_after"]) < float(row["anchor_kl_before"])
               for row in rows[1:])


def test_disabled_anchor_preserves_weights_rng_and_csv_schema(tmp_path, monkeypatch):
    common = _tiny_training(monkeypatch)
    monkeypatch.setattr(train, "AnchorSamplesCallback", lambda *args: pytest.fail("disabled callback"))
    monkeypatch.setattr(train, "anchor_step", lambda *args: pytest.fail("disabled anchor phase"))
    first = train.run_training(tmp_path / "default", measured_updates=1, **common)
    torch_rng, numpy_rng = torch.get_rng_state().clone(), np.random.get_state()
    second = train.run_training(tmp_path / "disabled", measured_updates=1,
                                anchor_coef=0.0, anchor_checkpoint=tmp_path / "missing.zip",
                                anchor_max_impulse=0.07, **common)
    assert torch.equal(torch_rng, torch.get_rng_state())
    current_rng = np.random.get_state()
    np.testing.assert_array_equal(numpy_rng[1], current_rng[1])
    assert numpy_rng[0] == current_rng[0] and numpy_rng[2:] == current_rng[2:]
    run_dirs = [tmp_path / name / result["run_id"]
                for name, result in (("default", first), ("disabled", second))]
    weights = [PPO.load(path / "checkpoint.zip").policy.state_dict() for path in run_dirs]
    assert all(torch.equal(value, weights[1][key]) for key, value in weights[0].items())
    with (run_dirs[0] / "updates.csv").open() as stream:
        columns = next(csv.reader(stream))
    with (run_dirs[1] / "updates.csv").open() as stream:
        assert next(csv.reader(stream)) == columns
    assert not any(column.startswith("anchor_") for column in columns)
