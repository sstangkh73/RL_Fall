"""Select and document a P3 candidate from current-revision P2 screening data."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("planar", "3d"), default="planar")
    environment = parser.parse_args().environment
    is_3d = environment == "3d"
    result_root = ROOT / "results" / ("benchmark_3d" if is_3d else "benchmark")
    current_asset = sha256(ROOT / "assets" / ("body_3d.xml" if is_3d else "planar_body.xml"))
    current_config = sha256(
        ROOT / "configs" / "benchmark" / ("base_3d.json" if is_3d else "base.json")
    )
    runs: list[dict[str, object]] = []
    for path in result_root.glob("*/manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            manifest.get("stage") == "P2_screening"
            and manifest.get("status") == "complete"
            and manifest.get("asset_sha256") == current_asset
            and manifest.get("config_sha256") == current_config
            and manifest.get("environment_dimension", "planar") == environment
            # The 3D amendment requires warm-up 10 + measured 20 for selection;
            # reduced-budget diagnostic screens must not mix in.
            and (not is_3d or (manifest.get("warmup_updates"),
                               manifest.get("measured_updates")) == (10, 20))
        ):
            manifest["path"] = str(path.parent)
            runs.append(manifest)
    layouts: dict[tuple[int, str, int], dict[str, dict[str, object]]] = {}
    for run in runs:
        key = (int(run["n_envs"]), str(run["wrapper"]), int(run["learner_threads"]))
        layouts.setdefault(key, {})[str(run["device"])] = run
    candidates = []
    for key, devices in layouts.items():
        if set(devices) != {"cpu", "cuda"}:
            continue
        cpu, cuda = devices["cpu"], devices["cuda"]
        candidates.append({
            "n_envs": key[0], "wrapper": key[1], "learner_threads": key[2],
            "cpu_tps": cpu["steady_transitions_per_second"],
            "cuda_tps": cuda["steady_transitions_per_second"],
            "cuda_speedup": float(cpu["steady_seconds"]) / float(cuda["steady_seconds"]),
            "paired_initial_weights_sha256": cpu["paired_initial_weights_sha256"],
            "_runs": (cpu, cuda),
        })
    if not candidates:
        raise SystemExit("No current-revision complete P2 CPU/CUDA pair")
    # Primary layout maximizes the tuned CPU baseline; CUDA is still measured with
    # exactly the same layout. Per-device optima remain visible in the table.
    selected = max(candidates, key=lambda row: float(row["cpu_tps"]))
    snapshot_path = result_root / "system_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    available_gib = float(snapshot["system_available_ram_bytes"]) / 1024**3
    gpu_util = float(snapshot["gpus"][0]["utilization.gpu"]) if snapshot["gpus"] else None
    resource_ready = available_gib >= 3.0 and (gpu_util is None or gpu_util <= 10.0)
    reasons = []
    if available_gib < 3.0:
        reasons.append(f"available RAM {available_gib:.2f} GiB is below the 3 GiB gate")
    if gpu_util is not None and gpu_util > 10.0:
        reasons.append(f"pre-existing GPU utilization is {gpu_util:.0f}%")

    selected_cpu, selected_cuda = selected["_runs"]
    for row in candidates:
        del row["_runs"]
    cpu_run_seconds = float(selected_cpu["warmup_seconds"]) + 5 * float(selected_cpu["steady_seconds"])
    cuda_run_seconds = float(selected_cuda["warmup_seconds"]) + 5 * float(selected_cuda["steady_seconds"])
    # With one environment P3 has 24 runs: 12 on each device.
    p3_seconds = 12 * (cpu_run_seconds + cuda_run_seconds)
    decision = {
        "stage": "P2_selection", "status": "candidate_selected_P3_not_started",
        "current_asset_sha256": current_asset, "current_config_sha256": current_config,
        "screening_pairs": sorted(
            candidates, key=lambda row: (row["n_envs"], row["learner_threads"])
        ),
        "selected_shared_layout": selected,
        "selection_rule": "fastest tuned CPU baseline; identical layout retained for CPU/CUDA pair",
        "P3_plan": {
            "environment_counts": [selected["n_envs"]],
            "primary_environment_count": selected["n_envs"],
            "learner_threads": selected["learner_threads"],
            "paired_seeds": [33001, 33002, 33003],
            "warmup_updates": 10, "measured_updates": 100,
            "run_count": 24,
            "estimated_hours_from_P2_condition_B": p3_seconds / 3600.0,
            "estimate_limit": "A/C/D may have different contact and compute loads",
        },
        "resource_preflight": {
            "ready": resource_ready, "available_ram_gib": available_gib,
            "gpu_utilization_percent": gpu_util, "hold_reasons": reasons,
            "paging_status": "not measured",
        },
        "interpretation": (
            "P2 is one screening seed. CPU is the candidate, not a confirmed winner; "
            "P3 must still run paired CPU/CUDA seeds."
        ),
    }
    json_path = result_root / "P2_selection.json"
    json_path.write_text(json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8")
    config_path = ROOT / "configs" / "benchmark" / (
        "p3_candidate_3d.json" if is_3d else "p3_candidate.json"
    )
    config_path.write_text(json.dumps(decision["P3_plan"] | {
        "status": "hold" if not resource_ready else "ready",
        "resource_preflight_reasons": reasons,
        "source_P2_selection": str(json_path.relative_to(ROOT)),
    }, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# P2 screening decision", "",
        "MuJoCo physics remained on CPU for both run families. P2 used one screening seed and is not confirmation.", "",
        "| envs | wrapper | threads | CPU transitions/s | CUDA transitions/s | CUDA speedup |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in sorted(candidates, key=lambda item: (int(item["n_envs"]),
                                                   int(item["learner_threads"]))):
        lines.append(
            f"| {row['n_envs']} | {row['wrapper']} | {row['learner_threads']} | "
            f"{float(row['cpu_tps']):.1f} | {float(row['cuda_tps']):.1f} | "
            f"{float(row['cuda_speedup']):.3f}x |"
        )
    lines += [
        "", f"Candidate shared layout: {selected['n_envs']} environment, "
        f"{selected['wrapper']}, {selected['learner_threads']} learner threads.",
        f"Estimated P3 wall time from B screening: {p3_seconds / 3600.0:.2f} hours for 24 runs.",
        "", "P3 status: " + ("ready" if resource_ready else "hold"),
    ]
    for reason in reasons:
        lines.append(f"- {reason}")
    lines += ["", decision["interpretation"]]
    (result_root / "P2_selection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
