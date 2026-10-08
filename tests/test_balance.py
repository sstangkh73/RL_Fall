import numpy as np
import pytest

from rl_fall.env3d import RLFall3DEnv


def _stance_action(env: RLFall3DEnv) -> np.ndarray:
    # Balance-mode actions are offsets from the stance.
    return np.zeros(env.action_space.shape, dtype=np.float32)


def test_v0_2_keeps_mass_dof_and_spaces():
    env = RLFall3DEnv(condition="A", seed=1, body="v0_2", mode="balance")
    np.testing.assert_allclose(np.sum(env.model.body_mass), 20.0)
    assert env.model.nq == 23 and env.model.nv == 22
    assert env.action_space.shape == (16,)
    assert env.observation_space.shape == (70,)
    assert len(env.foot_geom_ids) == 2
    assert env.config.max_episode_steps == 500


def test_balance_mode_requires_feet():
    with pytest.raises(ValueError):
        RLFall3DEnv(condition="A", body="v0_1", mode="balance")


def test_balance_reset_starts_clear_of_floor_with_task_slots_zeroed():
    env = RLFall3DEnv(condition="A", seed=4, body="v0_2", mode="balance")
    observation, _ = env.reset(seed=4)
    assert env.data.ncon == 0
    assert np.isfinite(observation).all()
    np.testing.assert_array_equal(observation[41:47], np.zeros(6))


def test_passive_stance_stands_without_push():
    env = RLFall3DEnv(condition="A", seed=2, body="v0_2", mode="balance",
                      max_push_impulse=0.0)
    env.reset(seed=2)
    action = _stance_action(env)
    for _ in range(150):
        _, reward, terminated, _, info = env.step(action)
        assert not terminated
        assert not info["fallen"]
        assert reward > 1.0


def test_lying_body_is_a_terminal_fall_with_zero_reward():
    env = RLFall3DEnv(condition="A", seed=3, body="v0_2", mode="balance")
    env.reset(seed=3)
    qpos = env.data.qpos.copy()
    qpos[2] = 0.15
    qpos[3:7] = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]  # torso pitched 90 degrees
    env.reset(seed=3, options={"qpos": qpos})
    _, reward, terminated, truncated, info = env.step(np.zeros(16, dtype=np.float32))
    assert terminated and not truncated
    assert info["fallen"]
    assert reward == 0.0


def test_task_mode_defaults_are_unchanged():
    default = RLFall3DEnv(seed=9)
    explicit = RLFall3DEnv(seed=9, body="v0_1", mode="task", max_push_impulse=0.45)
    obs_a, _ = default.reset(seed=9)
    obs_b, _ = explicit.reset(seed=9)
    np.testing.assert_array_equal(obs_a, obs_b)
    assert default.push_start == explicit.push_start
    np.testing.assert_array_equal(default.push_force_world, explicit.push_force_world)


@pytest.mark.parametrize("body, n_joints", [("v0_2", 16), ("v0_3", 20)])
def test_balance_bodies_size_spaces_by_joint_count(body, n_joints):
    env = RLFall3DEnv(condition="A", seed=5, body=body, mode="balance")
    observation, _ = env.reset(seed=5)
    np.testing.assert_allclose(np.sum(env.model.body_mass), 20.0)
    assert env.action_space.shape == (n_joints,)
    assert observation.shape == (3 * n_joints + 22,)
    assert env.data.ncon == 0
    assert len(env.foot_geom_ids) == 2


def test_v0_3_ankles_are_leg_joints_with_more_authority():
    env = RLFall3DEnv(condition="A", seed=6, body="v0_3", mode="balance")
    assert env.joint_parts[16:] == ("left_leg", "left_leg", "right_leg", "right_leg")
    assert np.all(env.action_scale[:8] == 0.25)   # arms unchanged
    assert np.all(env.action_scale[8:] == 0.6)    # hips, knees, ankles


def test_v0_3_passive_stance_stands_without_push():
    env = RLFall3DEnv(condition="A", seed=7, body="v0_3", mode="balance",
                      max_push_impulse=0.0)
    env.reset(seed=7)
    for _ in range(150):
        _, _, terminated, _, info = env.step(np.zeros(20, dtype=np.float32))
        assert not terminated and not info["fallen"]


def test_v0_3_is_balance_only_for_now():
    with pytest.raises(ValueError):
        RLFall3DEnv(seed=1, body="v0_3", mode="task")


def test_hard_push_fraction_draws_from_step_range():
    impulses = []
    for seed in range(40):
        env = RLFall3DEnv(condition="A", seed=seed, body="v0_3", mode="balance",
                          max_push_impulse=0.12, hard_push_fraction=1.0)
        env.reset(seed=seed)
        impulses.append(env.push_impulse)
    assert min(impulses) >= 0.13 and max(impulses) <= 0.25


def test_v1_0_smpl_topology_matches_reference_person():
    env = RLFall3DEnv(condition="A", seed=11, body="v1_0", mode="balance")
    observation, _ = env.reset(seed=11)
    assert env.model.nbody - 1 == 24              # SMPL bodies
    assert env.action_space.shape == (69,)        # 23 joints x 3 hinges
    assert observation.shape == (3 * 69 + 22,)
    np.testing.assert_allclose(np.sum(env.model.body_mass), 60.0, atol=0.01)
    assert env.data.ncon == 0                     # stance clears the floor and itself
    assert env.body_height == 1.60


def test_v1_0_injury_sites_use_literature_tolerances():
    env = RLFall3DEnv(condition="A", seed=12, body="v1_0", mode="balance")
    by_name = {env.model.geom(g).name: t for g, t in env.geom_injury_threshold.items()}
    assert by_name["head"] == 2350.0      # temporo-parietal skull (Raymond 2009)
    assert by_name["pelvis"] == 5770.0    # 5th-percentile female pelvis (Cavanaugh 1993)
    assert by_name["L_palm"] == 2260.0    # distal radius (Frykman 1967)
    assert by_name["L_foot"] == 3700.0    # foot/ankle axial (Funk 2002)


def test_v1_0_passive_stance_stands_without_push():
    env = RLFall3DEnv(condition="A", seed=13, body="v1_0", mode="balance",
                      max_push_impulse=0.0)
    env.reset(seed=13)
    for _ in range(200):
        _, _, terminated, _, info = env.step(np.zeros(69, dtype=np.float32))
        assert not terminated and not info["fallen"]
    assert not np.any(np.asarray(info["damage"]))  # standing loads stay below tolerances


def test_posture_term_penalises_foot_drift_before_the_push():
    env = RLFall3DEnv(condition="A", seed=14, body="v1_0", mode="balance",
                      max_push_impulse=0.0, posture_weight=2.0)
    env.reset(seed=14)
    _, _, _, _, info = env.step(np.zeros(69, dtype=np.float32))
    assert info["posture_penalty"] < 1e-3
    env._nominal_feet = env._nominal_feet + np.array([0.2, 0.0])  # pretend feet moved 20 cm
    _, _, _, _, info = env.step(np.zeros(69, dtype=np.float32))
    assert info["posture_penalty"] == 2.0


def test_capture_point_bonus_rewards_post_push_landing_near_capture_point():
    env = RLFall3DEnv(condition="A", seed=15, body="v1_0", mode="balance",
                      max_push_impulse=0.0, capture_point_weight=10.0)
    env.reset(seed=15)
    for _ in range(10):                       # let both feet settle onto the floor
        env.step(np.zeros(69, dtype=np.float32))
    env.push_start = 0.0                      # treat the rest of the episode as post-push
    left, _ = env.sole_geom_ids
    env._foot_air_steps[0] = 10               # left foot was swinging
    com = env.data.subtree_com[1].copy()
    env._previous_com = com.copy()            # zero velocity: capture point = CoM
    env.data.geom_xpos[left][:2] = com[:2]    # land exactly on the capture point
    assert env._capture_point_bonus() == 10.0
    env._foot_air_steps[0] = 10
    env._rewarded_steps = 3                   # only the first three landings pay
    assert env._capture_point_bonus() == 0.0


def test_natural_stance_shifts_weight_and_varies_foot_spacing():
    widths, offsets = [], []
    for seed in range(6):
        env = RLFall3DEnv(condition="A", seed=seed, body="v1_0", mode="balance",
                          natural_stance=True)
        env.reset(seed=seed)
        assert env.data.ncon == 0
        left, right = (env.data.geom_xpos[g][:2] for g in env.sole_geom_ids)
        widths.append(abs(left[1] - right[1]))
        offsets.append(env.data.subtree_com[1][1] - (left[1] + right[1]) / 2)
    assert max(widths) - min(widths) > 0.02          # foot spacing varies by > 2 cm
    assert max(abs(o) for o in offsets) > 0.02        # weight shifted over one foot


def test_natural_posture_rule_allows_relaxed_drift_and_penalises_bracing():
    env = RLFall3DEnv(condition="A", seed=16, body="v1_0", mode="balance",
                      max_push_impulse=0.0, posture_weight=1.0, posture_version=2)
    env.reset(seed=16)
    assert env._bracing_score(0.05, 1.0) == 0.0        # 5 cm weight-shift drift is free
    assert abs(env._bracing_score(0.18, 1.0) - 1.0) < 1e-9  # 18 cm wide stance is penalised
    env._reference_com_height += 0.08                  # as if the CoM dropped 8 cm
    assert env._bracing_score(0.0, 1.0) > 0.9          # crouching is penalised


def test_v3_posture_cost_keeps_growing_past_the_dead_zone_and_reward_stays_positive():
    penalties = []
    for drift in (0.05, 0.09, 0.12, 0.18, 0.30, 0.50, 1.00):
        env = RLFall3DEnv(condition="A", seed=17, body="v1_0", mode="balance",
                          max_push_impulse=0.0, posture_weight=1.0, posture_version=3)
        env.reset(seed=17)
        env._nominal_feet = env._nominal_feet + np.array([drift, 0.0])  # pretend feet moved
        _, reward, _, _, info = env.step(np.zeros(69, dtype=np.float32))
        assert not info["fallen"] and reward > 0.0
        penalties.append(info["posture_penalty"])
    assert penalties[0] < 1e-3                         # within the 8 cm dead zone: free
    assert all(b > a for a, b in zip(penalties, penalties[1:]))  # every extra cm costs more
    assert penalties[4] > 1.0                          # 30 cm costs more than v2's cap (1.0)


def test_v4_posture_cost_returns_after_the_push_settles_from_re_anchored_feet():
    def run(version):
        env = RLFall3DEnv(condition="A", seed=18, body="v1_0", mode="balance",
                          max_push_impulse=0.0, posture_weight=1.0, posture_version=version)
        env.reset(seed=18)
        settle = env.push_start + env.push_duration + 1.5
        rows = []
        while float(env.data.time) < settle + 0.2:
            during = env.push_start <= float(env.data.time) < settle
            if during:
                env._nominal_feet = env._feet_vector() + np.array([0.30, 0.0])  # a recovery step
            _, _, _, _, info = env.step(np.zeros(69, dtype=np.float32))
            assert not info["fallen"]
            rows.append((during, info["posture_penalty"]))
        return env, rows

    env3, rows3 = run(3)
    env4, rows4 = run(4)
    assert all(p == 0.0 for during, p in rows4 if during)  # recovery window is free
    assert all(p == 0.0 for _, p in rows3[-5:])             # v3: free forever after the push
    assert env4._feet_reanchored                            # v4 re-anchored the feet...
    assert all(p < 1e-3 for _, p in rows4[-5:])             # ...so the 30 cm step costs nothing
    env4._nominal_feet = env4._feet_vector() + np.array([0.20, 0.0])  # then shuffle 20 cm
    _, reward, _, _, info = env4.step(np.zeros(69, dtype=np.float32))
    assert info["posture_penalty"] > 0.0 and reward > 0.0   # post-settle drift costs again
