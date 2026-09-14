"""Sequential screening launcher; CPU and CUDA never contend concurrently."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import psutil
import torch


def run_one(command: list[str], root: Path) -> None:
    print("RUN", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def already_complete(root: Path, *, stage: str, device: str, condition: str,
                     seed: int, n_envs: int, threads: int, warmup: int,
                     measured: int, environment: str = "planar") -> bool:
    result_dir = root / (
        "results/benchmark_3d" if environment == "3d" else "results/benchmark"
    )
    for path in result_dir.glob("*/manifest.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            manifest.get("status") == "complete"
            and manifest.get("stage") == stage
            and manifest.get("device") == device
            and manifest.get("condition") == condition
            and manifest.get("seed") == seed
            and manifest.get("n_envs") == n_envs
            and manifest.get("learner_threads") == threads
            and manifest.get("warmup_updates") == warmup
            and manifest.get("measured_updates") == measured
            and manifest.get("environment_dimension", "planar") == environment
        ):
            print(f"SKIP complete {stage} {condition} {device} seed={seed} envs={n_envs}")
            return True
    return False


def run_if_needed(command: list[str], root: Path, *, stage: str, device: str,
                  condition: str, seed: int, n_envs: int, threads: int,
                  warmup: int, measured: int, environment: str = "planar") -> None:
    if not already_complete(root, stage=stage, device=device, condition=condition,
                            seed=seed, n_envs=n_envs, threads=threads,
                            warmup=warmup, measured=measured,
                            environment=environment):
        run_one(command, root)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--environment", choices=("planar", "3d"), default="planar")


def base_command(args: argparse.Namespace, device: str, condition: str, seed: int,
                 n_envs: int, stage: str, warmup: int, measured: int) -> list[str]:
    wrapper = "dummy" if n_envs == 1 else "subproc"
    return [
        sys.executable, "-m", "rl_fall.train", "--device", device,
        "--environment", args.environment,
        "--output", "results/benchmark_3d" if args.environment == "3d"
        else "results/benchmark",
        "--condition", condition, "--seed", str(seed), "--n-envs", str(n_envs),
        "--wrapper", wrapper, "--threads", str(args.threads), "--stage", stage,
        "--warmup-updates", str(warmup), "--measured-updates", str(measured),
    ]


def check_memory_gate(env_counts: list[int]) -> tuple[list[int], float]:
    available_gib = psutil.virtual_memory().available / (1024**3)
    allowed: list[int] = []
    for count in env_counts:
        if count > 1 and available_gib < 3.0:
            print(f"SKIP envs={count}: available RAM {available_gib:.2f} GiB is below 3 GiB gate")
        else:
            allowed.append(count)
    return allowed, available_gib


def confirmation_preflight(allow_busy_system: bool) -> None:
    available_gib = psutil.virtual_memory().available / (1024**3)
    gpu_util = None
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            text=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        gpu_util = float(output.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        pass
    reasons = []
    if available_gib < 3.0:
        reasons.append(f"available RAM {available_gib:.2f} GiB < 3 GiB")
    if gpu_util is not None and gpu_util > 10.0:
        reasons.append(f"pre-existing GPU utilization {gpu_util:.0f}% > 10%")
    if reasons and not allow_busy_system:
        raise SystemExit(
            "Confirmation preflight failed: " + "; ".join(reasons)
            + ". Close or pause workloads yourself, then retry. "
              "Use --allow-busy-system only if you intentionally accept confounded timing."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    screen = subparsers.add_parser("screen")
    screen.add_argument("--devices", nargs="+", choices=("cpu", "cuda"),
                        default=("cpu", "cuda"))
    screen.add_argument("--env-counts", nargs="+", type=int, default=(1, 4, 8))
    screen.add_argument("--threads", nargs="+", type=int, default=(1,))
    screen.add_argument("--seed", type=int, default=22001)
    screen.add_argument("--warmup-updates", type=int, default=10)
    screen.add_argument("--measured-updates", type=int, default=20)
    screen.add_argument("--include-dummy-4", action="store_true")
    screen.add_argument("--environment", choices=("planar", "3d"), default="planar")
    confirm = subparsers.add_parser("confirm")
    confirm.add_argument("--env-counts", nargs="+", type=int, required=True)
    confirm.add_argument("--primary-env-count", type=int, required=True)
    confirm.add_argument("--seeds", nargs="+", type=int, default=(33001, 33002, 33003))
    confirm.add_argument("--allow-busy-system", action="store_true")
    add_common(confirm)
    quality = subparsers.add_parser("quality")
    quality.add_argument("--n-envs", type=int, required=True)
    quality.add_argument("--seeds", nargs="+", type=int, default=(44001, 44002, 44003))
    quality.add_argument("--allow-busy-system", action="store_true")
    add_common(quality)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not torch.cuda.is_available():
        raise SystemExit("CUDA screening requested but CUDA is unavailable")
    if args.mode == "confirm":
        confirmation_preflight(args.allow_busy_system)
        requested, available_gib = check_memory_gate(list(args.env_counts))
        if args.primary_env_count not in requested:
            raise SystemExit("primary env count did not pass the memory gate")
        actual_plan = {
            "stage": "P3_confirmation", "environment_counts": requested,
            "primary_environment_count": args.primary_env_count,
            "threads": args.threads, "seeds": args.seeds,
            "warmup_updates": 10, "measured_updates": 100,
            "allow_busy_system": args.allow_busy_system,
            "available_ram_gib_at_launch": available_gib,
            "order": "B first; CPU/CUDA order alternates by seed; then A/C/D",
            "resume_policy": "skip matching complete manifests; rerun failed or interrupted",
        }
        result_dir = root / (
            "results/benchmark_3d" if args.environment == "3d"
            else "results/benchmark"
        )
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "p3_plan_actual.json").write_text(
            json.dumps(actual_plan, indent=2, sort_keys=True), encoding="utf-8"
        )
        # Run the main B comparison first at all selected environment counts.
        for seed_index, seed in enumerate(args.seeds):
            devices = ("cpu", "cuda") if seed_index % 2 == 0 else ("cuda", "cpu")
            for n_envs in requested:
                for device in devices:
                    run_if_needed(base_command(args, device, "B", seed, n_envs,
                                               "P3_confirmation", 10, 100), root,
                                  stage="P3_confirmation", device=device, condition="B",
                                  seed=seed, n_envs=n_envs, threads=args.threads,
                                  warmup=10, measured=100,
                                  environment=args.environment)
        # Secondary A/C/D comparisons use the single primary environment count.
        for seed_index, seed in enumerate(args.seeds):
            devices = ("cpu", "cuda") if seed_index % 2 == 0 else ("cuda", "cpu")
            for condition in "ACD":
                for device in devices:
                    run_if_needed(base_command(args, device, condition, seed,
                                               args.primary_env_count, "P3_confirmation",
                                               10, 100), root,
                                  stage="P3_confirmation", device=device,
                                  condition=condition, seed=seed,
                                  n_envs=args.primary_env_count, threads=args.threads,
                                  warmup=10, measured=100,
                                  environment=args.environment)
        return
    if args.mode == "quality":
        confirmation_preflight(args.allow_busy_system)
        requested, _ = check_memory_gate([args.n_envs])
        if not requested:
            raise SystemExit("quality env count did not pass the memory gate")
        for seed_index, seed in enumerate(args.seeds):
            devices = ("cpu", "cuda") if seed_index % 2 == 0 else ("cuda", "cpu")
            for device in devices:
                command = base_command(args, device, "B", seed, args.n_envs,
                                       "P4_learning", 0, 512)
                command += ["--evaluation-scenarios", "64", "--checkpoint-updates",
                            "0", "128", "256", "512"]
                run_one(command, root)
        return

    requested, available_gib = check_memory_gate(list(args.env_counts))
    if "cuda" in args.devices and not torch.cuda.is_available():
        raise SystemExit("CUDA screening requested but CUDA is unavailable")
    plan = {
        "stage": "P2_screening", "devices": args.devices,
        "environment_counts": requested, "threads": args.threads,
        "available_ram_gib_before": available_gib,
        "order": "sequential CPU then CUDA within each layout",
    }
    output = root / (
        "results/benchmark_3d" if args.environment == "3d" else "results/benchmark"
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "screening_plan_actual.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8"
    )
    for n_envs in requested:
        wrappers = ["dummy" if n_envs == 1 else "subproc"]
        if n_envs == 4 and args.include_dummy_4:
            wrappers.append("dummy")
        for wrapper in wrappers:
            for threads in args.threads:
                for device in args.devices:
                    command = [
                        sys.executable, "-m", "rl_fall.train",
                        "--environment", args.environment,
                        "--output", "results/benchmark_3d"
                        if args.environment == "3d" else "results/benchmark",
                        "--device", device, "--condition", "B",
                        "--seed", str(args.seed), "--n-envs", str(n_envs),
                        "--wrapper", wrapper, "--threads", str(threads),
                        "--stage", "P2_screening",
                        "--warmup-updates", str(args.warmup_updates),
                        "--measured-updates", str(args.measured_updates),
                    ]
                    run_one(command, root)


if __name__ == "__main__":
    # Required for Windows spawn semantics.
    main()
