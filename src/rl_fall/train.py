"""Single-run PPO training and evaluation entry point."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import platform
import pickle
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, TextIO

import gymnasium as gym
import numpy as np
import psutil
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.running_mean_std import RunningMeanStd
from stable_baselines3.common.vec_env import (
    DummyVecEnv,
    SubprocVecEnv,
    VecEnv,
    VecNormalize,
)

from .env import EnvironmentConfig, RLFallEnv
from .env3d import BALANCE_EPISODE_SECONDS, BODY_ASSETS, RLFall3DEnv
from .damage import PARTS
from .telemetry import ResourceSampler
from .anchor_ppo import AnchorPPO

# CREATE_NO_WINDOW exists only on Windows; 0 is the POSIX no-op.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

TOTAL_ROLLOUT_TRANSITIONS = 2048
# Curriculum (non-benchmark) PPO settings. With 2,048-transition updates, 10 epochs
# and lr 3e-4, stage-1 balance improved for ~250 updates and then degraded.
CURRICULUM_PPO = {
    "rollout_transitions": 16384, "learning_rate": 1e-4, "batch_size": 2048,
    "n_epochs": 5, "target_kl": 0.02,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_source(run_dir: Path, environment: str) -> str:
    root = Path.cwd()
    selected_files = (
        [Path("assets/body_3d.xml"), Path("assets/body_3d_v0_2.xml"),
         Path("assets/body_3d_v0_3.xml"), Path("assets/body_v1_0_female.xml"),
         Path("configs/research/body_v1_0_female.json"),
         Path("configs/benchmark/base_3d.json"),
         Path("configs/benchmark/model_3d_v0_1.json")]
        if environment == "3d"
        else [Path("assets/planar_body.xml"), Path("configs/benchmark/base.json"),
              Path("configs/benchmark/model_v0_1.json")]
    )
    relative_paths = sorted(
        list(Path("src/rl_fall").glob("*.py"))
        + selected_files,
        key=lambda path: path.as_posix(),
    )
    digest = hashlib.sha256()
    snapshot = run_dir / "source_snapshot"
    for relative in relative_paths:
        source = root / relative
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def make_env_factory(
    condition: str, seed: int, rank: int, environment: str = "planar",
    env_kwargs: dict[str, object] | None = None,
) -> Callable[[], gym.Env]:
    def factory() -> gym.Env:
        # Simulation workers do not import torch or initialize CUDA themselves.
        env_class = RLFall3DEnv if environment == "3d" else RLFallEnv
        return env_class(condition=condition, seed=seed + rank, **(env_kwargs or {}))

    return factory


def make_vec_env(
    condition: str, seed: int, n_envs: int, wrapper: str,
    environment: str = "planar", env_kwargs: dict[str, object] | None = None,
    norm_reward: bool = False, gamma: float = 0.999,
) -> VecNormalize:
    factories = [
        make_env_factory(condition, seed, rank, environment, env_kwargs)
        for rank in range(n_envs)
    ]
    if wrapper == "dummy":
        base: VecEnv = DummyVecEnv(factories)
    elif wrapper == "subproc":
        base = SubprocVecEnv(factories, start_method="spawn")
    else:
        raise ValueError("wrapper must be dummy or subproc")
    return VecNormalize(base, training=True, norm_obs=True, norm_reward=norm_reward,
                        clip_obs=10.0, gamma=gamma)


class UpdateMetricsCallback(BaseCallback):
    def __init__(self) -> None:
        super().__init__(verbose=0)
        self.task_reward = 0.0
        self.damage_penalty = 0.0
        self.task_successes = 0
        self.damage_increment = np.zeros(6, dtype=np.float64)
        self.contact_control_steps = {name: 0 for name in
                                      ("head", "torso", "left_arm", "right_arm",
                                       "left_leg", "right_leg")}
        self.episode_terminations = 0
        self.falls = 0
        self.balance_reward = 0.0

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        dones = self.locals.get("dones", np.zeros(len(infos), dtype=bool))
        for index, info in enumerate(infos):
            self.task_reward += float(info.get("reward_task", 0.0))
            self.damage_penalty += float(info.get("reward_damage_penalty", 0.0))
            self.task_successes += int(info.get("task_success", 0))
            self.damage_increment += np.asarray(info.get("damage_increment", np.zeros(6)))
            for part, load in info.get("step_peak_contact_loads_n", {}).items():
                self.contact_control_steps[part] += int(float(load) > 0.0)
            self.episode_terminations += int(bool(dones[index]))
            self.falls += int(bool(info.get("fallen", False)))
            self.balance_reward += float(info.get("reward_balance", 0.0))
        return True


@dataclass(frozen=True)
class AnchorNormalizer:
    """Observation statistics copied from S1, never updated by S2 rollouts."""

    obs_rms: RunningMeanStd
    clip_obs: float
    epsilon: float

    @classmethod
    def load(cls, checkpoint: Path) -> AnchorNormalizer:
        path = checkpoint.with_name(
            checkpoint.stem.replace("checkpoint", "vecnormalize") + ".pkl"
        )
        with path.open("rb") as stream:
            saved = pickle.load(stream)
        return cls(copy.deepcopy(saved.obs_rms), saved.clip_obs, saved.epsilon)


class AnchorSamplesCallback(BaseCallback):
    def __init__(
        self, training_env: VecNormalize, normalizer: AnchorNormalizer,
        max_impulse: float,
    ) -> None:
        super().__init__(verbose=0)
        self.normalizer = normalizer
        self.normalizing_env = training_env
        self.max_impulse = max_impulse
        self.previous_fallen = np.zeros(training_env.num_envs, dtype=bool)
        self.obs_s2: list[np.ndarray] = []
        self.obs_anchor: list[np.ndarray] = []

    def _on_rollout_start(self) -> None:
        # Episodes can span learn() calls: clear samples, retain previous-step flags.
        self.obs_s2.clear()
        self.obs_anchor.clear()

    def _on_step(self) -> bool:
        infos, dones = self.locals["infos"], self.locals["dones"]
        eligible = np.array([
            info.get("push_impulse", float("inf")) <= self.max_impulse + 1e-9
            for info in infos
        ]) & ~self.previous_fallen
        if eligible.any():
            obs = self.locals["obs_tensor"].detach().cpu().numpy()[eligible].copy()
            env = self.normalizing_env
            raw = obs * np.sqrt(env.obs_rms.var + env.epsilon) + env.obs_rms.mean
            frozen = self.normalizer
            normalized = (raw - frozen.obs_rms.mean) / np.sqrt(
                frozen.obs_rms.var + frozen.epsilon
            )
            self.obs_s2.append(obs)
            self.obs_anchor.append(np.clip(
                normalized, -frozen.clip_obs, frozen.clip_obs
            ).astype(np.float32))
        self.previous_fallen[:] = [
            bool(info.get("fallen", False)) and not bool(done)
            for info, done in zip(infos, dones)
        ]
        return True

    def samples(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.obs_s2:
            shape = (0, *self.normalizing_env.observation_space.shape)
            return np.empty(shape, dtype=np.float32), np.empty(shape, dtype=np.float32)
        return np.concatenate(self.obs_s2), np.concatenate(self.obs_anchor)


class ObjectiveAnchorSamplesCallback(AnchorSamplesCallback):
    """Capture raw inputs before env.step updates RMS or clips observations.

    The legacy post-update mode retains its old collection for reproducibility.
    Objective mode attaches an independent eligible-state dataset before train().
    """
    def __init__(self, training_env, normalizer, max_impulse, policy, coef):
        super().__init__(training_env, normalizer, max_impulse)
        self.anchor_policy = policy
        self.coef = coef

    def _on_rollout_start(self) -> None:
        super()._on_rollout_start()
        self.raw_previous = self.normalizing_env.get_original_obs().copy()

    def _on_step(self) -> bool:
        infos, dones = self.locals["infos"], self.locals["dones"]
        eligible = np.array([
            info.get("push_impulse", float("inf")) <= self.max_impulse + 1e-9
            for info in infos
        ]) & ~self.previous_fallen
        if eligible.any():
            self.obs_s2.append(
                self.locals["obs_tensor"].detach().cpu().numpy()[eligible].copy()
            )
            frozen = self.normalizer
            normalized = (self.raw_previous[eligible] - frozen.obs_rms.mean) / np.sqrt(
                frozen.obs_rms.var + frozen.epsilon
            )
            self.obs_anchor.append(np.clip(
                normalized, -frozen.clip_obs, frozen.clip_obs
            ).astype(np.float32))
        self.previous_fallen[:] = [
            bool(info.get("fallen", False)) and not bool(done)
            for info, done in zip(infos, dones)
        ]
        # This includes reset observations for done environments, exactly as the
        # next action's input does. Never use terminal_observation for that action.
        self.raw_previous = self.normalizing_env.get_original_obs().copy()
        return True

    def _on_rollout_end(self) -> None:
        self.model.set_anchor_samples(self.anchor_policy, *self.samples(), self.coef)


def anchor_step(
    model: PPO, anchor_policy: ActorCriticPolicy,
    obs_s2: np.ndarray | torch.Tensor, obs_anchor: np.ndarray | torch.Tensor,
    coef: float, epochs: int, batch_size: int,
) -> tuple[float, float]:
    """Minimize KL(S1 || S2) with the PPO optimizer, leaving the critic untouched."""
    if coef <= 0 or len(obs_s2) == 0:
        return 0.0, 0.0
    obs_s2 = torch.as_tensor(obs_s2, dtype=torch.float32, device=model.device)
    obs_anchor = torch.as_tensor(obs_anchor, dtype=torch.float32, device=model.device)
    policy = model.policy
    policy.set_training_mode(True)

    def kl(indices: torch.Tensor | slice) -> torch.Tensor:
        with torch.no_grad():
            frozen = anchor_policy.get_distribution(obs_anchor[indices]).distribution
        current = policy.get_distribution(obs_s2[indices]).distribution
        return torch.distributions.kl_divergence(frozen, current).sum(dim=-1)

    def mean_kl() -> float:
        with torch.no_grad():
            total = sum(
                kl(slice(start, start + batch_size)).sum().item()
                for start in range(0, len(obs_s2), batch_size)
            )
        return total / len(obs_s2)

    before = mean_kl()
    for _ in range(epochs):
        indices = torch.randperm(len(obs_s2), device=model.device)
        for batch in indices.split(batch_size):
            loss = coef * kl(batch).mean()
            # Clear PPO's last gradients, including the critic's Adam momentum path.
            policy.optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), model.max_grad_norm)
            policy.optimizer.step()
    return before, mean_kl()


def synchronize(device: str) -> None:
    if device == "cuda":
        torch.cuda.synchronize()


def set_actor_trainable(model: PPO, trainable: bool) -> None:
    """Freeze or unfreeze the actor; the value net always trains.

    Frozen parameters get no gradient, so Adam leaves them (and their moments) alone.
    Used to let the critic catch up with a new reward before the policy moves.
    """
    policy = model.policy
    for parameter in (*policy.mlp_extractor.policy_net.parameters(),
                      *policy.action_net.parameters(), policy.log_std):
        parameter.requires_grad_(trainable)


def set_learning_rate(model: PPO, learning_rate: float) -> None:
    """Replace a loaded model's constant learning rate (applied to Adam at each update)."""
    model.learning_rate = learning_rate
    model._setup_lr_schedule()


def create_model(
    env: VecEnv, device: str, seed: int, n_steps: int, network_width: int = 128,
    log_std_init: float = 0.0, gamma: float = 0.999,
    learning_rate: float = 3e-4, batch_size: int = 512, n_epochs: int = 10,
    target_kl: float | None = None,
    model_class: type[PPO] = PPO,
) -> PPO:
    return model_class(
        "MlpPolicy", env, device=device, seed=seed,
        learning_rate=learning_rate, n_steps=n_steps, batch_size=batch_size,
        n_epochs=n_epochs, target_kl=target_kl,
        gamma=gamma, gae_lambda=0.95, clip_range=0.2,
        policy_kwargs={
            "net_arch": {
                "pi": [network_width, network_width],
                "vf": [network_width, network_width],
            },
            "log_std_init": log_std_init,
        },
        verbose=0,
    )


def _initial_weights_path(
    root: Path, seed: int, n_envs: int, environment: str, network_width: int,
    mode: str = "task",
) -> Path:
    # Curriculum modes use a different log_std_init, so they never share files.
    suffix = "" if mode == "task" else f"_{mode}"
    return (
        root / "paired_initial_weights"
        / f"{environment}_w{network_width}_seed_{seed}_envs_{n_envs}{suffix}.pt"
    )


def load_or_create_initial_weights(model: PPO, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        state = torch.load(path, map_location="cpu", weights_only=True)
        model.policy.load_state_dict(state)
    else:
        state = {key: value.detach().cpu() for key, value in model.policy.state_dict().items()}
        torch.save(state, path)
    return _sha256(path)


def _latest_checkpoint_update(run_dir: Path) -> int | None:
    updates = [int(path.stem.rsplit("_", 1)[1])
               for path in run_dir.glob("checkpoint_update_*.zip")]
    return max(updates) if updates else None


def _logs_up_to(
    run_dir: Path, update: int
) -> tuple[list[dict[str, float | int | str]], list[dict[str, object]]]:
    """Rows logged before an interruption, cut back to the resume checkpoint."""
    rows: list[dict[str, float | int | str]] = []
    path = run_dir / "updates.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8") as stream:
            for row in list(csv.DictReader(stream))[:update]:
                parsed: dict[str, float | int | str] = {}
                for key, value in row.items():
                    try:
                        parsed[key] = int(value)
                    except ValueError:
                        try:
                            parsed[key] = float(value)
                        except ValueError:
                            parsed[key] = value
                rows.append(parsed)
    if len(rows) != update:
        raise ValueError(f"updates.csv has {len(rows)} rows, expected {update} to resume")
    evaluations_path = run_dir / "evaluations.json"
    evaluations = []
    if evaluations_path.exists():
        evaluations = [row for row in json.loads(evaluations_path.read_text(encoding="utf-8"))
                       if row["update"] <= update]
    return rows, evaluations


def evaluate(
    model: PPO, training_env: VecNormalize, seed: int, scenarios: int = 8,
    environment: str = "planar", env_kwargs: dict[str, object] | None = None,
    condition: str = "B", evaluation_impairment: bool | None = True,
) -> dict[str, object]:
    env_class = RLFall3DEnv if environment == "3d" else RLFallEnv
    base = DummyVecEnv([
        lambda: env_class(condition=condition, seed=seed,
                          evaluation_impairment=evaluation_impairment,
                          **(env_kwargs or {}))
    ])
    env = VecNormalize(base, training=False, norm_obs=True, norm_reward=False,
                       clip_obs=training_env.clip_obs)
    env.obs_rms = training_env.obs_rms
    successes: list[int] = []
    falls: list[int] = []
    episode_steps: list[int] = []
    damage: list[list[float]] = []
    contacts = {name: 0 for name in PARTS}
    for scenario in range(scenarios):
        env.seed(seed + scenario)
        observation = env.reset()
        done = np.array([False])
        last_info: dict[str, object] = {}
        while not done[0]:
            action, _ = model.predict(observation, deterministic=True)
            observation, _, done, infos = env.step(action)
            last_info = infos[0]
        successes.append(int(last_info["task_successes_episode"]))
        falls.append(int(bool(last_info.get("fallen", False))))
        episode_steps.append(int(last_info["elapsed_control_steps"]))
        damage.append(list(last_info["damage"]))
        for name, count in dict(last_info["contact_counts"]).items():
            contacts[name] += int(count)
    env.close()
    return {
        "scenarios": scenarios,
        "mean_task_successes": float(np.mean(successes)),
        "task_successes": successes,
        "mean_final_damage": np.mean(np.asarray(damage), axis=0).tolist(),
        "contact_counts": contacts,
        "fall_rate": float(np.mean(falls)),
        "mean_episode_steps": float(np.mean(episode_steps)),
    }


def run_training(
    output_dir: Path, device: str, condition: str, seed: int, n_envs: int,
    wrapper: str, threads: int, warmup_updates: int, measured_updates: int,
    evaluation_scenarios: int = 0, stage: str = "smoke",
    checkpoint_updates: tuple[int, ...] = (),
    environment: str = "planar", network_width: int | None = None,
    body: str = "v0_1", mode: str = "task", max_push_impulse: float = 0.45,
    init_checkpoint: Path | None = None, hard_push_fraction: float = 0.0,
    posture_weight: float = 0.0, resume_dir: Path | None = None,
    log_std: float | None = None, capture_point_weight: float = 0.0,
    posture_version: int = 1, natural_stance: bool = False,
    hard_push_range: tuple[float, float] | None = None,
    fall_continue_s: float = 0.0, damage_weight: float = 0.0,
    critic_warmup_updates: int = 0, learning_rate: float | None = None,
    anchor_coef: float = 0.0, anchor_checkpoint: Path | None = None,
    anchor_max_impulse: float | None = None, anchor_epochs: int | None = None,
    anchor_mode: str = "post_update",
) -> dict[str, object]:
    if anchor_mode not in ("post_update", "objective"):
        raise ValueError("anchor_mode must be post_update or objective")
    if anchor_mode == "objective" and anchor_epochs is not None:
        raise ValueError("anchor_epochs applies only to post_update mode")
    if anchor_epochs is None and anchor_mode == "post_update":
        anchor_epochs = CURRICULUM_PPO["n_epochs"]
    if anchor_coef > 0 and anchor_checkpoint is None:
        raise ValueError("anchor_checkpoint is required when anchor_coef > 0")
    model_class = AnchorPPO if anchor_coef > 0 and anchor_mode == "objective" else PPO
    if environment not in ("planar", "3d"):
        raise ValueError("environment must be planar or 3d")
    if environment == "planar" and (body, mode) != ("v0_1", "task"):
        raise ValueError("body and mode options apply to the 3d environment only")
    env_kwargs = (
        {"body": body, "mode": mode, "max_push_impulse": max_push_impulse,
         "hard_push_fraction": hard_push_fraction, "posture_weight": posture_weight,
         "capture_point_weight": capture_point_weight,
         "posture_version": posture_version, "natural_stance": natural_stance,
         "hard_push_range": hard_push_range,
         "fall_continue_s": fall_continue_s, "damage_weight": damage_weight}
        if environment == "3d" else None
    )
    # Task-mode evaluation keeps the benchmark's impaired condition-B scenarios;
    # curriculum modes evaluate under the training condition.
    eval_condition, eval_impairment = (
        ("B", True) if mode == "task" else (condition, None)
    )
    # Balance returns reach hundreds with gamma 0.999 and destabilised PPO in the
    # first S1 run; curriculum modes use a 2 s horizon and normalized rewards.
    gamma = 0.999 if mode == "task" else 0.99
    norm_reward = mode != "task"
    if network_width is None:
        network_width = 256 if environment == "3d" else 128
    rollout = (TOTAL_ROLLOUT_TRANSITIONS if mode == "task"
               else CURRICULUM_PPO["rollout_transitions"])
    if rollout % n_envs:
        raise ValueError("n_envs must divide 2048")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but torch.cuda.is_available() is false")
    if checkpoint_updates and evaluation_scenarios <= 0:
        raise ValueError("checkpoint evaluation requires evaluation_scenarios > 0")
    torch.set_num_threads(threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass  # only settable once per process; already fixed by an earlier run
    n_steps = rollout // n_envs
    resumed_from = None
    if resume_dir is not None:
        # Continue an interrupted run in place from its newest periodic checkpoint.
        run_dir = resume_dir
        run_id = run_dir.name
        resumed_from = _latest_checkpoint_update(run_dir)
        if resumed_from is None:
            raise ValueError(f"no checkpoint_update_*.zip to resume in {run_dir}")
        init_checkpoint = run_dir / f"checkpoint_update_{resumed_from}.zip"
        source_sha256 = snapshot_source(run_dir / f"resume_{resumed_from}", environment)
    else:
        run_id = (
            f"{environment}_{condition}_env{n_envs}_{wrapper}_{device}_seed{seed}_t{threads}_"
            f"{time.strftime('%Y%m%dT%H%M%S')}"
        )
        run_dir = output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        source_sha256 = snapshot_source(run_dir, environment)
    telemetry = ResourceSampler(run_dir / "resources.jsonl")
    status, failure = "failed", None
    env: VecEnv | None = None
    updates_stream: TextIO | None = None
    result: dict[str, object] = {"run_id": run_id, "status": status}
    started_wall = time.time()
    startup_start = time.perf_counter()
    try:
        telemetry.start()
        env = make_vec_env(condition, seed, n_envs, wrapper, environment, env_kwargs,
                           norm_reward, gamma)
        if init_checkpoint is not None:
            # Curriculum continuation: policy, optimizer and observation statistics.
            model = model_class.load(init_checkpoint, env=env, device=device)
            model.set_random_seed(seed)
            normalizer = init_checkpoint.with_name(
                init_checkpoint.stem.replace("checkpoint", "vecnormalize") + ".pkl"
            )
            saved = VecNormalize.load(str(normalizer), env.venv)
            env.obs_rms, env.ret_rms = saved.obs_rms, saved.ret_rms
            weights_hash = _sha256(init_checkpoint)
            if log_std is not None and resumed_from is None:
                # A new curriculum phase may restart exploration at a chosen noise level.
                with torch.no_grad():
                    model.policy.log_std.fill_(log_std)
            if learning_rate is not None:
                # Fine-tuning may use a smaller step than the checkpoint was trained with.
                set_learning_rate(model, learning_rate)
        else:
            # Curriculum modes start with smaller exploration noise (std ~0.37).
            model = create_model(env, device, seed, n_steps, network_width,
                                 model_class=model_class,
                                 log_std_init=0.0 if mode == "task" else -1.0,
                                 gamma=gamma,
                                 **({} if mode == "task" else {
                                     key: CURRICULUM_PPO[key] for key in
                                     ("learning_rate", "batch_size", "n_epochs", "target_kl")
                                 }))
            weights_hash = load_or_create_initial_weights(
                model, _initial_weights_path(
                    output_dir, seed, n_envs, environment, network_width, mode
                )
            )

        anchor_callback = None
        if anchor_coef > 0:
            anchor_model = PPO.load(anchor_checkpoint, device=device)
            anchor_model.policy.set_training_mode(False)
            for parameter in anchor_model.policy.parameters():
                parameter.requires_grad_(False)
            anchor_args = (
                env, AnchorNormalizer.load(anchor_checkpoint),
                max_push_impulse if anchor_max_impulse is None else anchor_max_impulse,
            )
            anchor_callback = (
                ObjectiveAnchorSamplesCallback(*anchor_args, anchor_model.policy, anchor_coef)
                if anchor_mode == "objective" else AnchorSamplesCallback(*anchor_args)
            )

        def run_evaluation() -> dict[str, object]:
            return evaluate(
                model, env, seed + 1_000_000, evaluation_scenarios, environment,
                env_kwargs, eval_condition, eval_impairment,
            )

        synchronize(device)
        startup_seconds = time.perf_counter() - startup_start
        update_rows: list[dict[str, float | int | str]] = []
        evaluation_rows: list[dict[str, object]] = []
        if resumed_from is not None:
            update_rows, evaluation_rows = _logs_up_to(run_dir, resumed_from)
        # Rows are flushed as they complete so long runs keep their logs if interrupted.
        updates_stream = (run_dir / "updates.csv").open("w", newline="", encoding="utf-8")
        updates_writer: csv.DictWriter | None = None
        if update_rows:
            updates_writer = csv.DictWriter(updates_stream, fieldnames=list(update_rows[0]))
            updates_writer.writeheader()
            updates_writer.writerows(update_rows)
            updates_stream.flush()

        def write_evaluations() -> None:
            (run_dir / "evaluations.json").write_text(
                json.dumps(evaluation_rows, indent=2, sort_keys=True), encoding="utf-8"
            )

        if 0 in checkpoint_updates and resumed_from is None:
            model.save(run_dir / "checkpoint_update_0")
            env.save(run_dir / "vecnormalize_update_0.pkl")
            eval_start = time.perf_counter()
            metrics = run_evaluation()
            evaluation_rows.append({
                "update": 0,
                "seconds": time.perf_counter() - eval_start,
                "metrics": metrics,
            })
            write_evaluations()
        planned = 0
        for phase, count in (("warmup", warmup_updates), ("steady", measured_updates)):
            for phase_update in range(count):
                planned += 1
                if planned <= len(update_rows):
                    continue  # finished before the interruption
                synchronize(device)
                begin = time.perf_counter()
                set_actor_trainable(model, len(update_rows) >= critic_warmup_updates)
                callback = UpdateMetricsCallback()
                model.learn(total_timesteps=rollout,
                            reset_num_timesteps=False, progress_bar=False,
                            callback=(callback if anchor_callback is None else
                                      CallbackList([callback, anchor_callback])))
                if anchor_callback is not None:
                    obs_s2, obs_anchor = anchor_callback.samples()
                    anchor_kl_before, anchor_kl_after = 0.0, 0.0
                    if anchor_mode == "objective":
                        anchor_kl_before, anchor_kl_after = model.anchor_kl_before, model.anchor_kl_after
                    elif len(update_rows) >= critic_warmup_updates:
                        anchor_kl_before, anchor_kl_after = anchor_step(
                            model, anchor_model.policy, obs_s2, obs_anchor, anchor_coef,
                            anchor_epochs, CURRICULUM_PPO["batch_size"],
                        )
                synchronize(device)
                elapsed = time.perf_counter() - begin
                update_rows.append({
                    "phase": phase, "phase_update": phase_update,
                    "global_update": len(update_rows),
                    "transitions": rollout,
                    "seconds": elapsed,
                    "transitions_per_second": rollout / elapsed,
                    "reward_task_sum": callback.task_reward,
                    "reward_damage_penalty_sum": callback.damage_penalty,
                    "task_successes": callback.task_successes,
                    "damage_increment_json": json.dumps(callback.damage_increment.tolist()),
                    "contact_control_steps_json": json.dumps(
                        callback.contact_control_steps, sort_keys=True
                    ),
                    "episode_terminations": callback.episode_terminations,
                    "falls": callback.falls,
                    "reward_balance_sum": callback.balance_reward,
                })
                if anchor_callback is not None:
                    update_rows[-1].update({
                        "anchor_samples": len(obs_s2),
                        "anchor_kl_before": anchor_kl_before,
                        "anchor_kl_after": anchor_kl_after,
                    })
                    if anchor_mode == "objective":
                        update_rows[-1].update({
                            "anchor_kl_objective": model.anchor_kl_objective,
                            "anchor_policy_loss": model.anchor_policy_loss,
                            "anchor_grad_norm_before_clip": model.anchor_grad_norm,
                            "anchor_epochs_completed": model.anchor_epochs_completed,
                            "anchor_optimizer_steps": model.anchor_optimizer_steps,
                            "anchor_early_stopped": int(model.anchor_early_stopped),
                        })
                if updates_writer is None:
                    updates_writer = csv.DictWriter(
                        updates_stream, fieldnames=list(update_rows[0])
                    )
                    updates_writer.writeheader()
                updates_writer.writerow(update_rows[-1])
                updates_stream.flush()
                completed_updates = len(update_rows)
                if completed_updates in checkpoint_updates:
                    model.save(run_dir / f"checkpoint_update_{completed_updates}")
                    env.save(run_dir / f"vecnormalize_update_{completed_updates}.pkl")
                    eval_start = time.perf_counter()
                    metrics = run_evaluation()
                    evaluation_rows.append({
                        "update": completed_updates,
                        "seconds": time.perf_counter() - eval_start,
                        "metrics": metrics,
                    })
                    write_evaluations()
        synchronize(device)
        save_start = time.perf_counter()
        model.save(run_dir / "checkpoint")
        save_seconds = time.perf_counter() - save_start
        env.save(run_dir / "vecnormalize.pkl")
        evaluation = (
            run_evaluation()
            if evaluation_scenarios > 0 and not checkpoint_updates else None
        )
        steady = [float(row["seconds"]) for row in update_rows if row["phase"] == "steady"]
        status = "complete"
        result = {
            "run_id": run_id, "status": status,
            "startup_seconds": startup_seconds,
            "warmup_seconds": sum(float(row["seconds"]) for row in update_rows
                                  if row["phase"] == "warmup"),
            "steady_seconds": sum(steady),
            "steady_transitions": measured_updates * rollout,
            "steady_transitions_per_second": (
                measured_updates * rollout / sum(steady) if steady else None
            ),
            "save_seconds": save_seconds, "evaluation": evaluation,
            "paired_initial_weights_sha256": weights_hash,
        }
    except BaseException as exc:
        failure = f"{type(exc).__name__}: {exc}"
        result = {"run_id": run_id, "status": status, "failure": failure}
        raise
    finally:
        if updates_stream is not None:
            updates_stream.close()
        if env is not None:
            env.close()
        telemetry.stop()
        manifest = {
            **result, "stage": stage,
            "started_unix": started_wall, "finished_unix": time.time(),
            "condition": condition, "device": device, "physics_backend": "MuJoCo CPU",
            "environment_dimension": environment,
            "network_width": network_width,
            "body": body, "mode": mode, "max_push_impulse": max_push_impulse,
            "hard_push_fraction": hard_push_fraction, "posture_weight": posture_weight,
            "capture_point_weight": capture_point_weight,
            "posture_version": posture_version, "natural_stance": natural_stance,
            "hard_push_range": list(hard_push_range) if hard_push_range else None,
            "fall_continue_s": fall_continue_s, "damage_weight": damage_weight,
            "critic_warmup_updates": critic_warmup_updates,
            "learning_rate_override": learning_rate,
            "anchor_coef": anchor_coef,
            "anchor_checkpoint": str(anchor_checkpoint) if anchor_checkpoint else None,
            "anchor_max_impulse": (max_push_impulse if anchor_max_impulse is None
                                   else anchor_max_impulse),
            "anchor_epochs": anchor_epochs,
            "anchor_mode": anchor_mode,
            "anchor_raw_obs": anchor_mode == "objective",
            "anchor_objective_sampling": ("uniform_eligible_with_replacement"
                                          if anchor_mode == "objective" else None),
            "anchor_uses_torch_rng": anchor_coef > 0 and anchor_mode == "objective",
            "anchor_objective_weighting": ("conditional_mean_not_eligible_fraction_scaled"
                                           if anchor_mode == "objective" else None),
            "gamma": gamma, "norm_reward": norm_reward,
            "init_checkpoint": str(init_checkpoint) if init_checkpoint else None,
            "resumed_from_update": resumed_from, "log_std_override": log_std,
            "n_envs": n_envs, "n_steps_per_env": n_steps, "wrapper": wrapper,
            "learner_threads": threads, "seed": seed,
            "warmup_updates": warmup_updates, "measured_updates": measured_updates,
            "checkpoint_updates": list(checkpoint_updates),
            "total_rollout_transitions": rollout,
            "python": platform.python_version(), "platform": platform.platform(),
            "logical_processors": os.cpu_count(),
            "system_ram_bytes": psutil.virtual_memory().total,
            "torch": torch.__version__, "torch_cuda_build": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "git_commit": _git_commit(),
            "source_snapshot_sha256": source_sha256,
            "config_sha256": _sha256(Path(
                "configs/benchmark/base_3d.json" if environment == "3d"
                else "configs/benchmark/base.json"
            )),
            "asset_sha256": _sha256(Path(
                f"assets/{BODY_ASSETS[body]}" if environment == "3d"
                else "assets/planar_body.xml"
            )),
            "environment_config": asdict(EnvironmentConfig(
                condition=condition,
                episode_seconds=BALANCE_EPISODE_SECONDS if mode == "balance" else 30.0,
            )),
            "process_tree_rss_note": "sum can double-count shared pages",
            "failure": failure,
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("results/benchmark"))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--condition", choices=tuple("ABCD"), default="B")
    parser.add_argument("--seed", type=int, default=22001)
    parser.add_argument("--n-envs", type=int, choices=(1, 4, 8, 16), default=1)
    parser.add_argument("--wrapper", choices=("dummy", "subproc"), default=None)
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--warmup-updates", type=int, default=10)
    parser.add_argument("--measured-updates", type=int, default=20)
    parser.add_argument("--evaluation-scenarios", type=int, default=0)
    parser.add_argument("--stage", choices=("smoke", "P2_screening", "P3_confirmation",
                                             "P4_learning", "learning_curve",
                                             "S1_balance", "S2_recover_or_fall"),
                        default="smoke")
    parser.add_argument("--checkpoint-updates", nargs="*", type=int, default=())
    parser.add_argument("--environment", choices=("planar", "3d"), default="planar")
    parser.add_argument("--network-width", type=int, choices=(128, 256, 512), default=None)
    parser.add_argument("--body", choices=tuple(BODY_ASSETS), default="v0_1")
    parser.add_argument("--mode", choices=("task", "balance"), default="task")
    parser.add_argument("--max-push-impulse", type=float, default=0.45)
    parser.add_argument("--init-checkpoint", type=Path, default=None)
    parser.add_argument("--hard-push-fraction", type=float, default=0.0,
                        help="share of pushes drawn from the step-requiring range")
    parser.add_argument("--posture-weight", type=float, default=0.0,
                        help="penalty weight for foot-placement drift before the push")
    parser.add_argument("--resume", type=Path, default=None,
                        help="continue an interrupted run directory from its newest checkpoint")
    parser.add_argument("--log-std", type=float, default=None,
                        help="reset the policy log-std after loading --init-checkpoint")
    parser.add_argument("--capture-point-weight", type=float, default=0.0,
                        help="bonus for post-push foot landings near the capture point")
    parser.add_argument("--posture-version", type=int, choices=(1, 2, 3, 4), default=1,
                        help="1: penalise any foot drift; 2: natural stance (dead zone, crouch, lean); "
                             "3: natural stance with an uncapped, never-negative cost; "
                             "4: v3 plus a foot-drift cost once settled after the push")
    parser.add_argument("--natural-stance", action="store_true",
                        help="start episodes from a randomised relaxed stance (spec bodies)")
    parser.add_argument("--hard-push-range", nargs=2, type=float, default=None,
                        help="impulse range of the step-requiring pushes (default 0.13 0.25)")
    parser.add_argument("--fall-continue-s", type=float, default=0.0,
                        help="S2: keep running this long after a fall instead of ending the episode")
    parser.add_argument("--damage-weight", type=float, default=0.0,
                        help="S2: reward cost per unit of weighted damage (head 5, torso 2, limbs 1)")
    parser.add_argument("--critic-warmup-updates", type=int, default=0,
                        help="freeze the actor (policy net, action net, log-std) for the first N "
                             "updates so only the value net adapts to a new reward")
    parser.add_argument("--learning-rate", type=float, default=None,
                        help="override the learning rate of --init-checkpoint / --resume")
    parser.add_argument("--anchor-coef", type=float, default=0.0,
                        help="KL loss weight toward a frozen S1 policy on recoverable pushes")
    parser.add_argument("--anchor-checkpoint", type=Path, default=None,
                        help="explicit S1 checkpoint, required when --anchor-coef > 0")
    parser.add_argument("--anchor-max-impulse", type=float, default=None,
                        help="largest impulse eligible for anchoring (default max-push-impulse)")
    parser.add_argument("--anchor-epochs", type=int, default=None,
                        help="KL anchor passes over the samples after each PPO update "
                             "(default PPO n_epochs); Adam makes this, not the coef, the strength knob")
    parser.add_argument("--anchor-mode", choices=("post_update", "objective"), default="post_update",
                        help="separate legacy KL phase, or KL in the PPO minibatch objective")
    args = parser.parse_args()
    wrapper = args.wrapper or ("dummy" if args.n_envs == 1 else "subproc")
    result = run_training(args.output, args.device, args.condition, args.seed,
                          args.n_envs, wrapper, args.threads, args.warmup_updates,
                          args.measured_updates, args.evaluation_scenarios, args.stage,
                          tuple(args.checkpoint_updates), args.environment,
                          args.network_width, args.body, args.mode,
                          args.max_push_impulse, args.init_checkpoint,
                          args.hard_push_fraction, args.posture_weight, args.resume,
                          args.log_std, args.capture_point_weight, args.posture_version,
                          args.natural_stance,
                          tuple(args.hard_push_range) if args.hard_push_range else None,
                          args.fall_continue_s, args.damage_weight,
                          args.critic_warmup_updates, args.learning_rate,
                          args.anchor_coef, args.anchor_checkpoint, args.anchor_max_impulse,
                          args.anchor_epochs, args.anchor_mode)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
