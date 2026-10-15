"""Independent paired diagnostics of frozen policies; never a milestone gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage2_eval as evaluation


def scenarios(seed_base: int, scale: float) -> list[dict]:
    if seed_base < 0 or not math.isfinite(scale) or scale <= 0:
        raise ValueError("seed base must be nonnegative and scale finite and positive")
    return [{**s, "seed": s["seed"] - evaluation.SEED_BASE + seed_base}
            for s in evaluation.make_scenarios(scale)]


def paired_deltas(records: list[dict], baseline: str, bootstrap_seed: int) -> dict:
    """Balanced impulse design; cluster by reset seed reused across impulses.

    Episodes within a reset-seed cluster need not be independent. Average each
    seed's paired differences first, then compute SE/bootstrap over these seed
    means. Angles remain a fixed grid: this is diagnostic uncertainty under the
    sampling design, not a population guarantee or uncertainty over training.
    """
    paired = {}
    for name in ("s2", baseline):
        selected = [r for r in records if r["policy"] == name]
        index = {(r["impulse"], r["seed"], r["angle"]): r for r in selected}
        if len(index) != len(selected):
            raise ValueError("duplicate scenario for a policy")
        paired[name] = index
    if not paired["s2"] or paired["s2"].keys() != paired[baseline].keys():
        raise ValueError("paired policies must have identical nonempty scenarios")
    clusters = {}
    deltas, torso_deltas = [], []
    for key in sorted(paired["s2"]):
        a, b = paired["s2"][key], paired[baseline][key]
        delta = a["weighted"] - b["weighted"]
        deltas.append(delta)
        torso_deltas.append(evaluation.WEIGHTS["torso"] * (a["damage"]["torso"] - b["damage"]["torso"]))
        clusters.setdefault(a["seed"], []).append(delta)
    if len({len(v) for v in clusters.values()}) != 1:
        raise ValueError("cluster sizes must be equal in the balanced diagnostic design")
    means = np.array([np.mean(v) for v in clusters.values()])
    n = len(means)
    rng = np.random.default_rng(bootstrap_seed)
    boot = means[rng.integers(n, size=(10000, n))].mean(axis=1)
    positive_torso = np.maximum(torso_deltas, 0)
    tail_n = max(1, math.ceil(len(deltas) * .1))
    return {
        "n_paired_episodes": len(deltas), "n_reset_seed_clusters": n,
        "mean": float(np.mean(deltas)),
        "cluster_standard_error": float(np.std(means, ddof=1) / np.sqrt(n)) if n > 1 else None,
        "cluster_bootstrap_ci95": np.quantile(boot, [.025, .975]).tolist() if n > 1 else None,
        "bootstrap_replicates": 10000, "bootstrap_seed": bootstrap_seed,
        "torso_weighted_delta_mean": float(np.mean(torso_deltas)),
        "torso_weighted_delta_median": float(np.median(torso_deltas)),
        "torso_positive_delta_fraction": float(np.mean(np.array(torso_deltas) > 0)),
        "top10pct_share_of_positive_torso_deltas": (
            float(np.sort(positive_torso)[-tail_n:].sum() / positive_torso.sum())
            if positive_torso.sum() else 0.0),
    }


def diagnostics(records: list[dict]) -> dict:
    comparisons, controllers = {}, {}
    for group in evaluation.GROUPS:
        selected = [r for r in records if r["group"] == group]
        comparisons[group] = {
            f"s2_minus_{baseline}": paired_deltas(selected, baseline, 29000)
            for baseline in ("s1", "passive")}
        controllers[group] = {}
        for policy in evaluation.POLICIES:
            episodes = [r for r in selected if r["policy"] == policy]
            falls = [r for r in episodes if r["fallen"]]
            survivors = [r for r in episodes if not r["fallen"]]
            damage = np.array([r["weighted"] for r in episodes])
            controllers[group][policy] = {
                "n_episodes": len(episodes), "n_falls": len(falls),
                "n_survivors": len(survivors),
                "weighted_damage_all_mean": float(damage.mean()),
                "weighted_damage_falls_only_mean": (
                    float(np.mean([r["weighted"] for r in falls])) if falls else None),
                "weighted_damage_survivors_only_mean": (
                    float(np.mean([r["weighted"] for r in survivors])) if survivors else None),
                "weighted_damage_p95": float(np.quantile(damage, .95)),
                "weighted_damage_max": float(damage.max()),
                "per_part_weighted_damage_mean": {
                    part: float(np.mean([r["damage"][part] * evaluation.WEIGHTS[part] for r in episodes]))
                    for part in evaluation.PARTS},
            }
    return {"paired_damage_differences": comparisons, "controllers": controllers}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("s2_run", type=Path)
    parser.add_argument("--s1-run", required=True, type=Path)
    parser.add_argument("--seed-base", required=True, type=int)
    parser.add_argument("--episodes-scale", type=float, default=4)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        planned = scenarios(args.seed_base, args.episodes_scale)
    except ValueError as error:
        parser.error(str(error))
    gate_seeds = {s["seed"] for s in evaluation.make_scenarios()}
    if gate_seeds.intersection(s["seed"] for s in planned):
        parser.error("diagnostic reset seeds must not overlap the gate reset seeds")
    if any(args.out_dir.resolve().is_relative_to(p.resolve()) for p in (args.s2_run, args.s1_run)):
        parser.error("write diagnostics outside both source runs")
    runs = {"s2": args.s2_run, "s1": args.s1_run}
    provenance = {
        "s2_run": str(args.s2_run), "s1_run": str(args.s1_run),
        "s2_update": 200, "s1_update": 200, "after_s": 2.5,
        "scenario_seed_base": args.seed_base, "episodes_scale": args.episodes_scale,
        "source_sha256": {
            name: {filename: sha256(run / filename) for filename in (
                "checkpoint_update_200.zip", "vecnormalize_update_200.pkl", "manifest.json")}
            for name, run in runs.items()},
        "script_sha256": sha256(Path(__file__)),
        "evaluator_sha256": sha256(Path(evaluation.__file__)),
    }
    records_path, summary_path = args.out_dir / "episodes.json", args.out_dir / "diagnostic.json"
    if records_path.exists():
        saved = json.loads(records_path.read_text())
        if saved["provenance"] != provenance:
            raise ValueError("existing diagnostic provenance differs; choose a new output directory")
        records = saved["episodes"]
    else:
        if summary_path.exists():
            raise ValueError("summary exists without episode evidence; choose a new output directory")
        torch.set_num_threads(4)
        manifests = {name: json.loads((run / "manifest.json").read_text()) for name, run in runs.items()}
        kwargs = {name: evaluation.env_kwargs(m, 2.5) for name, m in manifests.items()}
        kwargs["passive"] = kwargs["s1"]
        policies = {"passive": None}
        records = []
        try:
            for name, run in runs.items():
                policies[name] = evaluation.load_policy(run, 200, kwargs[name])
            for name in evaluation.POLICIES:
                for i, scenario in enumerate(planned, 1):
                    records.append({"policy": name, **evaluation.run_episode(kwargs[name], policies[name], scenario, 2.5)})
                    if i % 96 == 0:
                        print(f"{name}: {i}/{len(planned)} diagnostic episodes", flush=True)
        finally:
            for policy in policies.values():
                if policy is not None:
                    policy[1].close()
        args.out_dir.mkdir(parents=True, exist_ok=True)
        records_path.write_text(json.dumps({"provenance": provenance, "episodes": records}, indent=2))
    expected = {(s["group"], s["impulse"], s["seed"], s["angle"]) for s in planned}
    for policy in evaluation.POLICIES:
        actual = [r for r in records if r["policy"] == policy]
        if len(actual) != len(expected) or {(r["group"], r["impulse"], r["seed"], r["angle"]) for r in actual} != expected:
            raise ValueError("episode evidence does not match the predeclared scenarios")
    if summary_path.exists():
        existing = json.loads(summary_path.read_text())
        if existing["provenance"] != provenance or existing["episodes_sha256"] != sha256(records_path):
            raise ValueError("existing summary does not match the episode evidence")
        print(f"Complete diagnostic already exists: {summary_path}")
        return
    report = {
        "script": "scripts/stage2_diagnostics.py", "diagnostic_only": True,
        "milestone_eligible": False, "status": "complete", "provenance": provenance,
        "episodes_file": str(records_path), "episodes_sha256": sha256(records_path),
        "uncertainty_note": "Paired reset-seed clusters, fixed angle grid; not uncertainty across training seeds or a gate replacement.",
        "evaluation_summary": evaluation.summarize(records), **diagnostics(records),
    }
    summary_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote diagnostic only: {summary_path}")


if __name__ == "__main__":
    main()
