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
