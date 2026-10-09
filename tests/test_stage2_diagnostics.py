"""Evidence pairing, cluster uncertainty and survivor denominators."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage2_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("stage2_diagnostics", SCRIPT)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def records():
    rows = []
    # The same reset seed at two impulses is perfectly correlated. Treating
    # four episodes as independent would underestimate uncertainty by sqrt(3).
    for group, impulses in (("recoverable", (.05, .08)), ("unrecoverable", (.15, .20))):
        for impulse in impulses:
            for seed, delta in ((19000, 1.), (19001, 3.)):
                for policy in ("s2", "s1", "passive"):
                    weighted = delta if policy == "s2" else 0.
                    rows.append({"policy": policy, "group": group, "impulse": impulse,
                                 "seed": seed, "angle": float(seed % 2),
                                 "fallen": seed == 19001, "weighted": weighted,
                                 "damage": {p: weighted / 2 if p == "torso" else 0.
                                            for p in diagnostic.evaluation.PARTS}})
    return rows


def test_pairing_and_cluster_uncertainty_avoid_pseudoreplication():
    selected = [r for r in reversed(records()) if r["group"] == "unrecoverable"]
    result = diagnostic.paired_deltas(selected, "passive", 29000)
    assert result["n_paired_episodes"] == 4
    assert result["n_reset_seed_clusters"] == 2
    assert result["mean"] == 2.
    assert result["cluster_standard_error"] == pytest.approx(1.)
    assert result["cluster_bootstrap_ci95"] == pytest.approx([1., 3.])
    assert result["torso_weighted_delta_mean"] == 2.


def test_falls_only_preserves_all_episode_mean_and_survivors():
    result = diagnostic.diagnostics(records())
    r = result["controllers"]["unrecoverable"]["s2"]
    assert (r["n_episodes"], r["n_falls"], r["n_survivors"]) == (4, 2, 2)
    assert r["weighted_damage_all_mean"] == 2.
    assert r["weighted_damage_falls_only_mean"] == 3.
    assert r["weighted_damage_survivors_only_mean"] == 1.
    assert sum(r["per_part_weighted_damage_mean"].values()) == 2.
    # Identical policies produce zero uncertainty, including the bootstrap.
    same = [dict(r, policy="s2" if r["policy"] == "s1" else "passive")
            for r in records() if r["group"] == "unrecoverable" and r["policy"] in ("s1", "passive")]
    paired = diagnostic.paired_deltas(same, "passive", 29000)
    assert paired["mean"] == paired["cluster_standard_error"] == 0.
    assert paired["cluster_bootstrap_ci95"] == [0., 0.]


def test_diagnostic_rejects_duplicate_missing_and_unbalanced_pairs():
    selected = [r for r in records() if r["group"] == "unrecoverable"]
    with pytest.raises(ValueError, match="duplicate"):
        diagnostic.paired_deltas(selected + [selected[0]], "passive", 29000)
    with pytest.raises(ValueError, match="identical"):
        diagnostic.paired_deltas(selected[1:], "s1", 29000)
    unequal = [r for r in selected if not (r["seed"] == 19000 and r["impulse"] == .15)]
    with pytest.raises(ValueError, match="equal"):
        diagnostic.paired_deltas(unequal, "passive", 29000)


def test_new_scenarios_preserve_push_design_and_use_disjoint_reset_seeds():
    original = diagnostic.evaluation.make_scenarios(4)
    new = diagnostic.scenarios(19000, 4)
    assert len(new) == 384
    assert sum(s["group"] == "unrecoverable" for s in new) == 192
    assert not {s["seed"] for s in new} & {s["seed"] for s in diagnostic.evaluation.make_scenarios()}
    for a, b in zip(original, new):
        assert a["group"] == b["group"] and a["angle"] == b["angle"] and a["impulse"] == b["impulse"]
        assert b["seed"] == a["seed"] + 10000
    for bad in (0, -1, np.nan, np.inf):
        with pytest.raises(ValueError):
            diagnostic.scenarios(19000, bad)
