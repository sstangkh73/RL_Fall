"""Single-run PPO training and evaluation entry point."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, TextIO

import gymnasium as gym
import numpy as np
import psutil
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
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


def synchronize(device: str) -> None:
    if device == "cuda":
        torch.cuda.synchronize()


def create_model(
    env: VecEnv, device: str, seed: int, n_steps: int, network_width: int = 128,
    log_std_init: float = 0.0, gamma: float = 0.999,
    learning_rate: float = 3e-4, batch_size: int = 512, n_epochs: int = 10,
    target_kl: float | None = None,
) -> PPO:
    return PPO(
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
    init_checkpoint: Path | None = None,
) -> dict[str, object]:
    if environment not in ("planar", "3d"):
        raise ValueError("environment must be planar or 3d")
    if environment == "planar" and (body, mode) != ("v0_1", "task"):
        raise ValueError("body and mode options apply to the 3d environment only")
    env_kwargs = (
        {"body": body, "mode": mode, "max_push_impulse": max_push_impulse}
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
    torch.set_num_interop_threads(1)
    n_steps = rollout // n_envs
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
            model = PPO.load(init_checkpoint, env=env, device=device)
            model.set_random_seed(seed)
            normalizer = init_checkpoint.with_name(
                init_checkpoint.stem.replace("checkpoint", "vecnormalize") + ".pkl"
            )
            saved = VecNormalize.load(str(normalizer), env.venv)
            env.obs_rms, env.ret_rms = saved.obs_rms, saved.ret_rms
            weights_hash = _sha256(init_checkpoint)
        else:
            # Curriculum modes start with smaller exploration noise (std ~0.37).
            model = create_model(env, device, seed, n_steps, network_width,
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

        def run_evaluation() -> dict[str, object]:
            return evaluate(
                model, env, seed + 1_000_000, evaluation_scenarios, environment,
                env_kwargs, eval_condition, eval_impairment,
            )

        synchronize(device)
        startup_seconds = time.perf_counter() - startup_start
        update_rows: list[dict[str, float | int | str]] = []
        evaluation_rows: list[dict[str, object]] = []
        # Rows are flushed as they complete so long runs keep their logs if interrupted.
        updates_stream = (run_dir / "updates.csv").open("w", newline="", encoding="utf-8")
        updates_writer: csv.DictWriter | None = None

        def write_evaluations() -> None:
            (run_dir / "evaluations.json").write_text(
                json.dumps(evaluation_rows, indent=2, sort_keys=True), encoding="utf-8"
            )

        if 0 in checkpoint_updates:
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
        for phase, count in (("warmup", warmup_updates), ("steady", measured_updates)):
            for phase_update in range(count):
                synchronize(device)
                begin = time.perf_counter()
                callback = UpdateMetricsCallback()
                model.learn(total_timesteps=rollout,
                            reset_num_timesteps=False, progress_bar=False,
                            callback=callback)
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
            "gamma": gamma, "norm_reward": norm_reward,
            "init_checkpoint": str(init_checkpoint) if init_checkpoint else None,
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
                                             "S1_balance"),
                        default="smoke")
    parser.add_argument("--checkpoint-updates", nargs="*", type=int, default=())
    parser.add_argument("--environment", choices=("planar", "3d"), default="planar")
    parser.add_argument("--network-width", type=int, choices=(128, 256, 512), default=None)
    parser.add_argument("--body", choices=tuple(BODY_ASSETS), default="v0_1")
    parser.add_argument("--mode", choices=("task", "balance"), default="task")
    parser.add_argument("--max-push-impulse", type=float, default=0.45)
    parser.add_argument("--init-checkpoint", type=Path, default=None)
    args = parser.parse_args()
    wrapper = args.wrapper or ("dummy" if args.n_envs == 1 else "subproc")
    result = run_training(args.output, args.device, args.condition, args.seed,
                          args.n_envs, wrapper, args.threads, args.warmup_updates,
                          args.measured_updates, args.evaluation_scenarios, args.stage,
                          tuple(args.checkpoint_updates), args.environment,
                          args.network_width, args.body, args.mode,
                          args.max_push_impulse, args.init_checkpoint)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
