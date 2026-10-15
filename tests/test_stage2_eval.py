"""Fast, checkpoint-free checks of paired stage-2 evaluation summaries."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage2_eval.py"
SPEC = importlib.util.spec_from_file_location("stage2_eval", SCRIPT)
stage2_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2_eval)


def record(policy, group, impulse, seed, fallen, weighted, **damage):
    return {"policy": policy, "group": group, "impulse": impulse, "seed": seed,
            "angle": 0.0, "fallen": fallen, "weighted": weighted,
            "damage": {part: damage.get(part, 0.0) for part in stage2_eval.PARTS}}


def test_paired_summary_math():
    records = []
    # Unequal per-impulse counts distinguish pooled means from means of means.
    for impulse, seed, s2_fell, s1_fell, passive_fell, s2_d, s1_d, passive_d in (
        (0.05, 9000, True, False, True, 1.0, 0.2, 3.0),
        (0.05, 9001, False, False, True, 0.0, 0.4, 1.0),
        (0.05, 9002, True, True, False, 2.0, 0.6, 0.0),
        (0.08, 9000, True, False, False, 3.0, 0.8, 0.0),
    ):
        for policy, fell, weighted in (("s2", s2_fell, s2_d), ("s1", s1_fell, s1_d),
                                      ("passive", passive_fell, passive_d)):
            records.append(record(policy, "recoverable", impulse, seed, fell, weighted,
                                  head=weighted / 5))
    records.extend([
        record("s2", "unrecoverable", 0.15, 9000, True, 0.9, head=0.1, torso=0.2),
        record("s2", "unrecoverable", 0.15, 9001, True, 1.1, head=0.2, left_arm=0.1),
        record("s2", "unrecoverable", 0.20, 9000, False, 1.0, torso=0.5),
        record("s1", "unrecoverable", 0.15, 9000, True, 0.8, torso=0.4),
        record("s1", "unrecoverable", 0.15, 9001, False, 0.2, left_leg=0.2),
        record("s1", "unrecoverable", 0.20, 9000, True, 0.0),
        record("passive", "unrecoverable", 0.15, 9000, True, 2.0, head=0.4),
        record("passive", "unrecoverable", 0.15, 9001, True, 1.0, torso=0.5),
        record("passive", "unrecoverable", 0.20, 9000, True, 0.6, right_leg=0.6),
    ])

    # Pairing must use scenario identity, not record order or seed alone.
    summary = stage2_eval.summarize(list(reversed(records)))
    assert summary["false_give_up"] == pytest.approx(2 / 3)
    assert summary["head_damage_share"] == pytest.approx(0.5)
    assert summary["recoverable"] == pytest.approx({
        "n_episodes": 4, "s2_survival": 0.25, "s1_survival": 0.75,
        "passive_survival": 0.5, "s2_weighted_damage": 1.5,
        "s1_weighted_damage": 0.5, "passive_weighted_damage": 1.0,
    })
    assert summary["unrecoverable"] == pytest.approx({
        "n_episodes": 3, "s2_survival": 1 / 3, "s1_survival": 1 / 3,
        "passive_survival": 0.0, "s2_weighted_damage": 1.0,
        "s1_weighted_damage": 1 / 3, "passive_weighted_damage": 1.2,
    })
    assert set(summary["per_impulse"]) == {"0.05", "0.08", "0.15", "0.20", "0.25"}
    assert summary["per_impulse"]["0.05"]["s2"] == pytest.approx({
        "n": 3, "survival": 1 / 3, "weighted_damage_mean": 1.0,
    })
    assert summary["per_impulse"]["0.08"]["s1"]["survival"] == 1.0
    parts = summary["per_part_damage_mean_unrecoverable"]
    assert parts["s2"] == pytest.approx({
        "head": 0.1, "torso": 0.7 / 3, "left_arm": 0.1 / 3,
        "right_arm": 0.0, "left_leg": 0.0, "right_leg": 0.0,
    })
    assert parts["s1"]["torso"] == pytest.approx(0.4 / 3)
    assert parts["passive"]["right_leg"] == pytest.approx(0.2)


def test_zero_denominators():
    records = [record(policy, group, impulse, 9000, True, 0.0)
               for policy in stage2_eval.POLICIES
               for group, impulse in (("recoverable", 0.05), ("unrecoverable", 0.15))]
    summary = stage2_eval.summarize(records)
    assert summary["false_give_up"] == 0.0
    assert summary["head_damage_share"] == 0.0
    for group in stage2_eval.GROUPS:
        for policy in stage2_eval.POLICIES:
            assert summary[group][f"{policy}_survival"] == 0.0
            assert summary[group][f"{policy}_weighted_damage"] == 0.0


@pytest.mark.parametrize("scale, counts", [
    (1.0, (24, 24, 16, 16, 16)),
    (0.1, (2, 2, 2, 2, 2)),
    (0.001, (1, 1, 1, 1, 1)),
    (0.0, (1, 1, 1, 1, 1)),
])
def test_scenarios(scale, counts):
    scenarios = stage2_eval.make_scenarios(scale)
    assert len(scenarios) == sum(counts)
    for impulse, n in zip((0.05, 0.08, 0.15, 0.20, 0.25), counts):
        episodes = [s for s in scenarios if s["impulse"] == impulse]
        assert [s["seed"] for s in episodes] == list(range(9000, 9000 + n))
        assert [s["angle"] for s in episodes] == pytest.approx(
            np.linspace(-np.pi, np.pi, n, endpoint=False))
        expected_group = "recoverable" if impulse < 0.1 else "unrecoverable"
        assert all(s["group"] == expected_group for s in episodes)
