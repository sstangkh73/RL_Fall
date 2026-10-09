# Codex task: analysis only — S2 damage vs. passive baseline (DO NOT EDIT ANY FILE)

You are reviewing an RL project (MuJoCo humanoid v1.0 + SB3 PPO) at `C:\RL_Fall` (repo root).
**Analysis only. Do not modify, create or delete any file.** Reply with text.

## Context
- S2 = fine-tune the S1 push-recovery policy so that, on unrecoverable pushes (impulse U(0.15, 0.25)),
  it falls safely (minimise weighted impact damage: head 5, torso 2, limbs 1), while on recoverable pushes
  (U(0, 0.08)) it still recovers like S1. Falls do not end the episode (2.5 s continue). Damage cost = DAMAGE_W(10000) × weighted damage.
- Code: `src/rl_fall/env3d.py` (env, damage), `src/rl_fall/train.py` (PPO, KL anchor to frozen S1:
  `--anchor-coef/--anchor-epochs`, separate Adam phase after each PPO update on pre-fall states with push ≤ max),
  scripts `scripts/run_stage2_pilot.sh`, `scripts/run_stage2_anchor.sh`, eval `scripts/stage2_eval.py` (48 paired episodes per group).
- Gate per seed (all 3 seeds 63001–63003, update 200 only, no checkpoint picking):
  recoverable survival ≥ S1 − 5 pts; unrecoverable weighted damage < S1 AND < passive (limp fall, 0.001607 same for all seeds);
  false give-up ≤ 10%.

## Results so far (update 200; unrecoverable damage S2, S1 = 0.00187/0.00190/0.00143 for 63001/2/3, passive 0.00161)
| run | rec. survival | FGU | unrec damage |
|---|---|---|---|
| dmg10000 (no anchor) | FGU up to 65% | 6.5–65% | ~0.0010–0.0011 (low) |
| wide U(0,0.12), no anchor | 83/83/79% | 17/15/20% | 0.00086/0.00116/0.00042 |
| anchor ae5 (5 anchor epochs/update) | 96/94/92% | 0/2/9% | 0.00176/0.00164/0.00153 (fails) |
| anchor ae1 (1 epoch/update) | 87.5/95.8/91.7% | 7/2/9% | 0.00133/**0.00175**/0.00125 (63002 > passive) |
Anchor ae1: KL(S1‖θ) before anchor ~0.022–0.045, after ~0.010–0.020. 63002 stays 0.0017–0.0018 at every checkpoint (50–200).
Running now: anchor ae1 + recoverable U(0, 0.12) (anchor also on ≤0.12).

## Questions
1. Why might the anchor block damage reduction for seed 63002 specifically? Does the anchor sample set
   (pre-fall states with push ≤ max, judged from previous-step `fallen`) leak states from unrecoverable episodes
   (e.g. before the push lands, or the first steps after a hard push, which look like recoverable ones)? Check `AnchorSamplesCallback` in train.py.
2. Would restricting anchor samples to steps before the push + first K steps after a recoverable push, or weighting
   anchor by push impulse, be sound? Any bug you see in the anchor implementation?
3. If anchor+wide also fails on one seed, what is the most promising single next change (ranked), and is the damage
   gate (< passive 0.00161) plausibly reachable given `wide` already reached 0.0004–0.0012 without anchor?
Cite file:line for every claim. Keep it under ~600 words.
