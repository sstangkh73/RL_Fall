Task: create a new evaluation script `scripts/stage2_eval.py` in this repo (C:\RL_Fall, Python, MuJoCo + stable-baselines3). Also add a small fast test `tests/test_stage2_eval.py`.

Context: S1 policy = stage-1 balance policy; S2 policy = fine-tuned "recover or fall" policy. The env is `rl_fall.env3d.RLFall3DEnv`. With `fall_continue_s>0` a fall does not end the episode; it runs on that many seconds after the fall so the impact damage is recorded. Read `scripts/diag_fall_damage.py` and `scripts/stage1_survival.py` FIRST and reuse their approach (same `_fix_push`, same SEED_BASE=9000, same way of loading a PPO checkpoint + VecNormalize from a run dir and its manifest.json, same `env.damage_model.damage` / `rl_fall.damage.PARTS` per-part damage, weights head 5, torso 2, arms/legs 1).

CLI:

    python scripts/stage2_eval.py S2_RUN_DIR --s1-run S1_RUN_DIR [--s2-update 200] [--s1-update 200] [--after 2.5] [--out PATH] [--episodes-scale 1.0]

Default output path: S2_RUN_DIR/s2_eval.json.
Each run dir has manifest.json, checkpoint_update_<N>.zip, vecnormalize_update_<N>.pkl. Build env kwargs like diag_fall_damage.py: condition = manifest condition (default "A"), body = manifest body, mode "balance", max_push_impulse 0.45, natural_stance = bool(manifest natural_stance), fall_continue_s = args.after. Do NOT pass damage_weight (leave default 0). Use the S2 manifest for S2, and the S1 manifest for S1 and passive.

Scenarios (paired: the SAME scenario list is run for S2, S1 and passive = zero action):

- recoverable group: impulses 0.05 and 0.08, 24 episodes each (48 total)
- unrecoverable group: impulses 0.15, 0.20, 0.25, 16 episodes each (48 total)
- Within an impulse, episode i uses seed SEED_BASE + i and push angle angles[i], angles = np.linspace(-pi, pi, n, endpoint=False) for that impulse's n.
- Each episode: env.reset(seed), _fix_push(env, impulse, angle), step with deterministic actions until env.elapsed_steps reaches env.config.max_episode_steps or terminated/truncated, or until `after` seconds after the first step where env.fallen became True. Record fallen (bool), per-part damage, weighted = sum(w[p]*damage[p]).
- `--episodes-scale` (float, default 1.0) multiplies the per-impulse episode counts (round, min 1); for smoke tests only.

Output JSON (these keys are required; extra keys are fine):

- "script": "scripts/stage2_eval.py"
- "s2_run", "s1_run" (str), "s2_update", "s1_update" (int), "after_s" (float)
- "recoverable": n_episodes (int), s2_survival, s1_survival, passive_survival (0-1), s2_weighted_damage, s1_weighted_damage, passive_weighted_damage
- "unrecoverable": same fields as recoverable
- "false_give_up": float
- "head_damage_share": float
- "per_impulse": impulse string -> policy name -> n, survival, weighted_damage_mean
- "per_part_damage_mean_unrecoverable": policy name -> part -> mean damage

Definitions: weighted damage of a group = mean over ALL episodes in the group (falls and non-falls). survival = fraction not fallen. false_give_up = (# recoverable scenarios where S1 survived but S2 fell) / (# recoverable scenarios where S1 survived); 0.0 if denominator is 0. head_damage_share = sum over S2 unrecoverable episodes of 5*head_damage / sum of S2 unrecoverable weighted damage (0.0 if total is 0). Print a short human-readable summary to stdout too. Use torch.set_num_threads(4).

Test `tests/test_stage2_eval.py`: must run in < 30 s and need no trained checkpoints. Factor the summary math into a pure function (e.g. `summarize(records)` taking per-episode record dicts) and test false_give_up, head_damage_share, survival and group means on hand-made records. Import the script module via importlib from its file path (scripts/ is not a package).

Constraints: do NOT modify any file under `auto-loop/`. Do NOT modify src/rl_fall/*, existing scripts, or existing tests. Only create the two new files.

Done check: tests pass in WSL:
wsl.exe -d Ubuntu -- bash -lc "cd /mnt/c/RL_Fall && ~/venvs/rl_fall/bin/python -m pytest tests/test_stage2_eval.py -q"
and `--help` of the script works with the same python.
