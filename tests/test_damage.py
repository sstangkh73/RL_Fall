import numpy as np

from rl_fall.damage import (
    PART_INDEX,
    DamageModel,
    apply_functional_limits,
    target_sensor,
)


def test_damage_is_monotonic_and_persistent():
    model = DamageModel()
    first = model.update({"head": 500.0}, 0.1)
    damaged = model.damage.copy()
    assert first[PART_INDEX["head"]] > 0
    model.update({}, 10.0)
    np.testing.assert_array_equal(model.damage, damaged)


def test_damage_is_nearly_timestep_invariant_for_constant_load():
    coarse, fine = DamageModel(), DamageModel()
    for _ in range(100):
        coarse.update({"torso": 300.0}, 0.01)
    for _ in range(1000):
        fine.update({"torso": 300.0}, 0.001)
    np.testing.assert_allclose(coarse.damage, fine.damage, rtol=1e-12, atol=1e-12)


def test_each_limb_reduces_only_its_two_joint_limits():
    requested = np.full(8, 1_000.0)
    limits = np.array([35, 20, 35, 20, 60, 45, 60, 45], dtype=float)
    damage = np.zeros(6)
    damage[PART_INDEX["left_arm"]] = 0.5
    applied = apply_functional_limits(requested, limits, damage, True)
    np.testing.assert_allclose(applied[:2], limits[:2] * 0.5)
    np.testing.assert_allclose(applied[2:], limits[2:])


def test_torso_cap_cannot_be_bypassed_by_many_joints():
    limits = np.array([35, 20, 35, 20, 60, 45, 60, 45], dtype=float)
    damage = np.zeros(6)
    damage[PART_INDEX["torso"]] = 0.75
    applied = apply_functional_limits(limits, limits, damage, True)
    assert np.sum(np.abs(applied) / limits) <= 8 * 0.25 + 1e-12


def test_impairment_off_preserves_torque_while_damage_still_exists():
    limits = np.array([35, 20, 35, 20, 60, 45, 60, 45], dtype=float)
    damage = np.ones(6)
    applied = apply_functional_limits(limits, limits, damage, False)
    np.testing.assert_array_equal(applied, limits)


def test_head_damage_controls_target_validity_without_leak():
    target = np.array([0.4, -0.2])
    rng = np.random.default_rng(3)
    sensed, valid = target_sensor(target, 1.0, True, rng)
    np.testing.assert_array_equal(sensed, np.zeros(2))
    assert valid == 0.0
    sensed, valid = target_sensor(target, 1.0, False, rng)
    np.testing.assert_allclose(sensed, target)
    assert valid == 1.0
