# Codex task: KL anchor to the frozen S1 policy on recoverable pushes (S2 fine-tune)

Repo: C:\RL_Fall (Python, stable-baselines3 PPO, MuJoCo). Read `src/rl_fall/train.py`, `src/rl_fall/env3d.py`
(info keys `fallen` and `push_impulse` at env3d.py ~649-650), `scripts/run_stage1.sh`, `scripts/run_stage2_pilot.sh`,
`scripts/run_stage2_wide.sh`, `tests/test_critic_warmup.py` (style reference for a train.py test).

## Why
S2 fine-tunes the S1 policy (checkpoint `results/stage1_v1_0/.../checkpoint.zip`) with damage reward and a 50/50
mix of recoverable U(0, RECOVERABLE_MAX) and unrecoverable U(0.15, 0.25) pushes. In every variant tried so far the
policy forgets how to recover from recoverable pushes (false give-up 10-65%). We want an auxiliary loss that keeps the
policy close to the frozen S1 policy on recoverable-push states that have not fallen, while leaving it free elsewhere.

## What to implement

1. `src/rl_fall/train.py`
   - New args to `run_training`: `anchor_coef: float = 0.0`, `anchor_checkpoint: Path | None = None`,
     `anchor_max_impulse: float | None = None` (None -> use `max_push_impulse`). CLI flags `--anchor-coef`,
     `--anchor-checkpoint`, `--anchor-max-impulse`. Record all three in manifest.json.
     When `anchor_coef > 0`, `anchor_checkpoint` is required (raise ValueError otherwise). It must be an explicit
     path (not derived from init_checkpoint, because on `--resume` init_checkpoint becomes the run's own checkpoint).
   - Load the anchor once: `PPO.load(anchor_checkpoint, device=device)` (no env), freeze all its parameters, and load
     its normalizer `vecnormalize.pkl` that sits next to it (same naming rule as the existing init_checkpoint
     normalizer: `checkpoint.zip` -> `vecnormalize.pkl`, `checkpoint_update_N.zip` -> `vecnormalize_update_N.pkl`).
     Keep only its `obs_rms`, `clip_obs` and `epsilon` (frozen, never updated).
   - Collect anchor samples during the rollout with a callback (extend `UpdateMetricsCallback` or add a second
     callback via `CallbackList`). At each `_on_step`, `self.locals["obs_tensor"]` is the S2-normalized observation the
     action was taken from. For each env i, the sample is eligible iff
     `infos[i]["push_impulse"] <= anchor_max_impulse + 1e-9` AND the robot was NOT fallen at that observation
     (use the `fallen` flag from env i's PREVIOUS step info; reset to False for env i after `dones[i]`; start False).
     Store eligible obs. Convert to raw obs with the training VecNormalize's current `obs_rms`
     (`raw = obs * sqrt(var + eps) + mean`), then re-normalize with the anchor's frozen obs_rms and clip to
     +-clip_obs. Keep both the S2-normalized obs (input to the trained policy) and the anchor-normalized obs.
   - After each `model.learn(...)` call in the update loop (only when anchor_coef > 0 and the actor is trainable,
     i.e. respect `critic_warmup_updates`), run an anchor phase: `CURRICULUM_PPO["n_epochs"]` epochs over the
     eligible samples in shuffled minibatches of `CURRICULUM_PPO["batch_size"]`, loss =
     `anchor_coef * mean_over_batch( KL( pi_anchor(.|s_anchor) || pi_theta(.|s_s2) ).sum(action_dim) )`
     using `torch.distributions.kl_divergence` on the diagonal Gaussians
     (`policy.get_distribution(obs).distribution`), the model's own `policy.optimizer`, and
     `clip_grad_norm_(policy.parameters(), model.max_grad_norm)`. The anchor distribution is computed under
     `torch.no_grad()`. Only actor parameters receive gradient (KL does not touch the value net; assert or just
     rely on it). Put this in a small testable function, e.g.
     `anchor_step(model, anchor_policy, obs_s2, obs_anchor, coef, epochs, batch_size) -> (kl_before, kl_after)`.
   - Add columns `anchor_samples`, `anchor_kl_before`, `anchor_kl_after` to updates.csv ONLY when anchor_coef > 0
     (runs without the anchor must produce exactly the same updates.csv columns as today, so resume of old runs works).
   - With `anchor_coef == 0` behavior must be bit-for-bit unchanged (no extra callback, no extra RNG use).
2. `scripts/run_stage1.sh` and `scripts/run_stage2_pilot.sh`: pass env `ANCHOR` (coef, default empty/0) and
   `ANCHOR_CHECKPOINT` through to `--anchor-coef` / `--anchor-checkpoint`; in run_stage2_pilot.sh the anchor
   checkpoint is the same S1 `checkpoint.zip` used as INIT_CHECKPOINT; when ANCHOR is set, append `_anc<ANCHOR>` to TAG
   (do this in run_stage2_pilot.sh the same way `_lr<LR>` is appended). Follow the existing style of those scripts.
3. New `scripts/run_stage2_anchor.sh` modelled on `scripts/run_stage2_wide.sh`: `RECOVERABLE_MAX=0.08`,
   `DAMAGE_W=10000`, `CRITIC_WARMUP=0`, `LR=`, `ANCHOR=${ANCHOR:-1.0}`; TAG `s2_dmg10000_anc${ANCHOR}`; train, then
   `run_stage2_eval.sh` and `run_stage2_eval_trend.sh` with `UPDATES="50 100 150"` exactly like run_stage2_wide.sh
   (check those eval scripts find runs by TAG and RECOVERABLE_MAX so the results dir
   `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000_anc1.0/` is found). Header comment explaining it.
4. `tests/test_anchor.py` (fast, small: n_envs 1-2, few hundred transitions, dummy wrapper, or call `anchor_step`
   directly on a tiny PPO built with `create_model`):
   - `anchor_step` lowers the KL to a different frozen policy and leaves value-net params unchanged.
   - the eligibility rule: samples after a fall, and samples from episodes with push_impulse above the max, are excluded
     (unit-test the callback/mask logic with fake infos).
   - `anchor_coef > 0` without `anchor_checkpoint` raises ValueError.

## Rules
- Do NOT modify anything under `auto-loop/` (except you may append to `auto-loop/progress.md`; not needed).
- Do not change defaults or behavior of existing runs; do not touch `results/`; do not delete or weaken tests.
- Do not run long training. Do not commit.

## Done when
- `wsl.exe -d Ubuntu -- bash -lc "cd /mnt/c/RL_Fall && ~/venvs/rl_fall/bin/python -m pytest -q"` passes
  (if you cannot run WSL, run `python -m pytest -q tests/test_anchor.py` wherever possible and say so).
- `bash -n scripts/run_stage2_anchor.sh scripts/run_stage2_pilot.sh scripts/run_stage1.sh` is clean.
- Report the files changed and a short summary.
