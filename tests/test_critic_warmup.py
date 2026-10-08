import torch
from stable_baselines3 import PPO

from rl_fall.train import run_training

ACTOR = ("mlp_extractor.policy_net.", "action_net.", "log_std")
CRITIC = ("mlp_extractor.value_net.", "value_net.")


def _changed(before: dict, after: dict, prefixes: tuple[str, ...]) -> bool:
    keys = [key for key in before if key.startswith(prefixes)]
    assert keys
    return any(not torch.equal(before[key], after[key]) for key in keys)


def test_critic_warmup_freezes_the_actor_then_releases_it(tmp_path):
    result = run_training(tmp_path, device="cpu", condition="B", seed=5, n_envs=1,
                          wrapper="dummy", threads=1, warmup_updates=0,
                          measured_updates=2, evaluation_scenarios=1, stage="smoke",
                          checkpoint_updates=(0, 1, 2), environment="planar",
                          critic_warmup_updates=1)
    run_dir = tmp_path / result["run_id"]
    weights = [PPO.load(run_dir / f"checkpoint_update_{update}.zip", device="cpu")
               .policy.state_dict() for update in (0, 1, 2)]

    # Update 1 is the warm-up: only the value net moves.
    assert not _changed(weights[0], weights[1], ACTOR)
    assert _changed(weights[0], weights[1], CRITIC)
    # Update 2 trains the actor again.
    assert _changed(weights[1], weights[2], ACTOR)


def test_learning_rate_override_applies_to_a_loaded_checkpoint(tmp_path):
    common = dict(device="cpu", condition="B", seed=5, n_envs=1, wrapper="dummy",
                  threads=1, warmup_updates=0, measured_updates=1,
                  evaluation_scenarios=1, stage="smoke", checkpoint_updates=(0, 1),
                  environment="planar")
    first = run_training(tmp_path / "a", **common)
    start = tmp_path / "a" / first["run_id"] / "checkpoint_update_1.zip"
    result = run_training(tmp_path / "b", init_checkpoint=start, learning_rate=3e-5, **common)
    model = PPO.load(tmp_path / "b" / result["run_id"] / "checkpoint_update_1.zip",
                     device="cpu")

    assert PPO.load(start, device="cpu").learning_rate != 3e-5
    assert model.learning_rate == 3e-5
    assert all(group["lr"] == 3e-5 for group in model.policy.optimizer.param_groups)
