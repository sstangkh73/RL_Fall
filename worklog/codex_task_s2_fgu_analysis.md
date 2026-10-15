# Codex task: second opinion on S2 false give-up (ANALYSIS ONLY)

**DO NOT modify, create or delete any file in the repository.** Read code and result files only.
Your only output is your final answer message (in English or Thai), max ~60 lines.

## Context
Project: MuJoCo humanoid + PPO (stable-baselines3). Stage S1 policy (`natural4_r2`, update 200)
recovers from pushes. Stage S2 fine-tunes it for 200 updates (16,384 transitions per update, 8 envs)
so that on unrecoverable pushes it falls with less weighted damage, while still surviving recoverable pushes.

Key code:
- `src/rl_fall/env3d.py` (env; S2 options `fall_continue_s`, `damage_weight`, `S2_DAMAGE_WEIGHTS`,
  posture_version 4, capture point shaping, push sampling with `hard` fraction and hard range)
- `src/rl_fall/train.py` (PPO setup, `--init-checkpoint`, `--learning-rate`, `--critic-warmup-updates`)
- `scripts/run_stage1.sh`, `scripts/run_stage2_pilot.sh` (S2 recipe: pushes U(0,0.08) half / U(0.15,0.25) half,
  FALL_CONTINUE=2.5 s, DAMAGE_W=10000)
- `scripts/stage2_eval.py` (paired deterministic eval: recoverable 0.05/0.08 x24, unrecoverable 0.15/0.20/0.25 x16)
- Results notes: `planning/Curriculum_Plan_TH.md` section 5 (tables for s2_dmg10000, cw25, lr3e-5)
- Results files (WSL clone; may also exist under C:\RL_Fall\results): `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000*/3d_*/` (updates.csv, manifest, s2_eval*.json)

## Gate (must hold for all 3 seeds 63001-63003 at the pre-registered update 200)
- S2 survival on recoverable >= S1 survival - 5 pp
- S2 weighted damage on unrecoverable < S1 and < passive  (this ALREADY passes every run)
- false give-up (S1 survives, S2 falls; over episodes S1 survives) <= 10%

## What was tried (all fail on false give-up, which oscillates across checkpoints, not trending)
FGU at update 50/100/150/200 per seed (63001, 63002, 63003):
1. base lr 1e-4: 14.3/7.1/19.0/11.9 ; 6.5/19.6/6.5/28.3 ; 10.9/6.5/2.2/30.4   (update 0 = S1 exactly, FGU 0)
2. critic warm-up 25 updates (actor frozen): 9.5/14.3/4.8/33.3 ; 6.5/13.0/8.7/13.0 ; 4.3/17.4/10.9/28.3
3. lr 3e-5: 7.1/4.8/9.5/9.5 ; 8.7/10.9/15.2/65.2 ; 47.8/4.3/8.7/23.9
Other findings: swapping VecNormalize stats S1<->S2 shows the drop is in the weights, not obs normalization.
Reward: standing ~1.5/step (gamma 0.99 → value ~150); a typical fall costs ~15 from damage, so the reward
should NOT favour giving up. Obs includes `remaining` time. A no-damage control (DAMAGE_W=0, same everything else)
is now running to test whether the drop is just continued-PPO drift.

## New results (2026-10-09)
4. Control DAMAGE_W=0 (same recipe otherwise), update 200: recoverable survival 66.7/79.2/93.8%, FGU 28.6/19.6/6.5%;
   trend 50/100/150 FGU 2.2-26.2%. => the FGU is NOT caused by the damage term.
5. Noise floor: S1 checkpoints update 125/150/175 evaluated against S1 update 200 (no S2 at all):
   FGU 63001 7.1/2.4/11.9, 63002 2.2/4.3/0.0, 63003 0.0/4.3/10.9 (mean ~5%), recoverable survival 89.6-100%.
6. Per impulse at update 200 (S2 vs S1 survival): at 0.05 S2 is mostly 79-100% vs S1 96-100%;
   at 0.08 S2 is 21-88% vs S1 75-96%. The loss sits at 0.08, the TOP of the S2 recoverable training range.
   S1 (natural4_r2) was trained with recoverable U(0,0.12) + hard U(0.13,0.25); S2 trains U(0,0.08) + U(0.15,0.25),
   so S2 never sees 0.08-0.15. A run with recoverable U(0,0.12) (everything else base) is now training.

## Questions
1. Most likely root cause(s) of the oscillating recoverable-push survival loss? Look for concrete code-level issues
   (e.g. reward after fall / fallen latch / termination vs truncation & bootstrapping with fall_continue,
   push sampling differences between train and eval, deterministic eval vs stochastic training, log_std, entropy,
   the 0.08-0.15 gap, anything in train.py fine-tune loading).
2. Rank 2-3 concrete fixes by expected effect and cost (each ~2.5 h of training for 3 seeds), e.g. KL/BC anchor to S1
   on recoverable pushes, wider recoverable range U(0,0.12), lower DAMAGE_W, more updates, larger batch, etc.
3. Point to exact file:line for any bug you find.
