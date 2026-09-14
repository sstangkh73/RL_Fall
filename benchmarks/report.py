"""Aggregate complete benchmark manifests without inventing missing results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

ELIGIBLE_STAGES = {"P2_screening", "P3_confirmation", "P4_learning"}


def training_exclusion_reasons(
    row: dict[str, object], current_asset: str, current_config: str,
    environment: str, include_smoke: bool,
) -> list[str]:
    reasons = []
    if row.get("asset_sha256") != current_asset:
        reasons.append("asset hash differs from current benchmark asset")
    if row.get("config_sha256") != current_config:
        reasons.append("config hash differs from current benchmark config")
    if row.get("environment_dimension", "planar") != environment:
        reasons.append(f"environment is not {environment}")
    if not include_smoke and row.get("stage") not in ELIGIBLE_STAGES:
        reasons.append(f"stage {row.get('stage')} is excluded")
    return reasons


def reconcile_training_manifests(
    manifests: list[dict[str, object]], current_asset: str, current_config: str,
    environment: str, include_smoke: bool,
) -> tuple[
    list[dict[str, object]],
    list[tuple[dict[str, object], list[str]]],
    list[dict[str, object]],
]:
    complete, excluded, incomplete = [], [], []
    for row in manifests:
        if row.get("status") != "complete":
            incomplete.append(row)
            continue
        reasons = training_exclusion_reasons(
            row, current_asset, current_config, environment, include_smoke
        )
        if reasons:
            excluded.append((row, reasons))
        else:
            complete.append(row)
    assert len(manifests) == len(complete) + len(excluded) + len(incomplete)
    return complete, excluded, incomplete


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/benchmark"))
    parser.add_argument("--output", type=Path,
                        default=Path("results/benchmark/benchmark_report.md"))
    parser.add_argument("--include-smoke", action="store_true")
    parser.add_argument("--environment", choices=("auto", "planar", "3d"), default="auto")
    args = parser.parse_args()
    environment = args.environment
    if environment == "auto":
        environment = "3d" if "benchmark_3d" in args.input.as_posix() else "planar"
    all_manifests = []
    for path in args.input.glob("*/manifest.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["manifest_path"] = str(path)
        all_manifests.append(data)
    manifests = [row for row in all_manifests if "device" in row]
    diagnostic_manifests = [row for row in all_manifests if "device" not in row]
    current_asset = sha256(Path(
        "assets/body_3d.xml" if environment == "3d" else "assets/planar_body.xml"
    ))
    current_config = sha256(Path(
        "configs/benchmark/base_3d.json" if environment == "3d"
        else "configs/benchmark/base.json"
    ))
    complete, excluded_complete, incomplete = reconcile_training_manifests(
        manifests, current_asset, current_config, environment, args.include_smoke
    )
    key_fields = ("stage", "condition", "n_envs", "wrapper", "learner_threads",
                  "seed", "warmup_updates", "measured_updates", "asset_sha256",
                  "config_sha256", "source_snapshot_sha256")
    paired: dict[tuple[object, ...], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in complete:
        key = tuple(row.get(field) for field in key_fields)
        paired[key][str(row["device"])] = row
    pair_rows = []
    for key, devices in paired.items():
        if "cpu" not in devices or "cuda" not in devices:
            continue
        cpu, cuda = devices["cpu"], devices["cuda"]
        cpu_time, cuda_time = float(cpu["steady_seconds"]), float(cuda["steady_seconds"])
        pair_rows.append({
            **dict(zip(key_fields, key)),
            "cpu_seconds": cpu_time, "cuda_seconds": cuda_time,
            "cuda_speedup_cpu_time_over_cuda_time": cpu_time / cuda_time,
            "cpu_transitions_per_second": cpu["steady_transitions_per_second"],
            "cuda_transitions_per_second": cuda["steady_transitions_per_second"],
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pair_csv = args.output.with_suffix(".csv")
    if pair_rows:
        with pair_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(pair_rows[0]))
            writer.writeheader()
            writer.writerows(pair_rows)
    speedups = [float(row["cuda_speedup_cpu_time_over_cuda_time"]) for row in pair_rows]
    lines = [
        f"# CPU/CUDA {environment} benchmark report", "",
        "MuJoCo physics runs on CPU in both families. Only PPO inference/update changes device.", "",
        "## Manifest reconciliation", "",
        f"- Manifest files found: {len(all_manifests)}",
        f"- Training manifests: {len(manifests)} = {len(complete)} included complete + "
        f"{len(excluded_complete)} excluded complete + {len(incomplete)} incomplete",
        f"- Non-training diagnostic manifests: {len(diagnostic_manifests)}",
        f"- Matched CPU/CUDA pairs among included runs: {len(pair_rows)}", "",
    ]
    if excluded_complete:
        lines += ["## Excluded complete training runs", ""]
        for row, reasons in excluded_complete:
            lines.append(
                f"- {row.get('run_id')}: " + "; ".join(reasons)
            )
        lines.append("")
    if diagnostic_manifests:
        lines += ["## Non-training diagnostic manifests", ""]
        for row in diagnostic_manifests:
            lines.append(
                f"- {row.get('stage', 'unknown stage')}: {row['manifest_path']}"
            )
        lines.append("")
    if speedups:
        lines += [
            "## Paired timing", "",
            "| stage | condition | envs | wrapper | threads | seed | CPU s | CUDA s | speedup |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|",
        ]
        for row in pair_rows:
            lines.append(
                f"| {row['stage']} | {row['condition']} | {row['n_envs']} | {row['wrapper']} | "
                f"{row['learner_threads']} | {row['seed']} | {row['cpu_seconds']:.3f} | "
                f"{row['cuda_seconds']:.3f} | "
                f"{row['cuda_speedup_cpu_time_over_cuda_time']:.3f}x |"
            )
        lines += ["", f"Median CUDA speedup: {statistics.median(speedups):.3f}x; "
                  f"range {min(speedups):.3f}x–{max(speedups):.3f}x.", ""]
    else:
        lines += ["No matched complete CPU/CUDA pair exists yet; no device conclusion is reported.", ""]
    if incomplete:
        lines += ["## Incomplete runs", ""]
        for row in incomplete:
            lines.append(f"- {row.get('run_id')}: {row.get('failure')}")
        lines.append("")
    lines += [
        "## Scope limits", "",
        "These timings are system-benchmark evidence only. They do not establish learning-quality "
        "equivalence or protective falling. Process-tree RSS is a sum and can double-count shared pages.",
    ]
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
