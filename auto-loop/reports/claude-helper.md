# Claude helper calls

ทุกครั้งที่ Codex ในลูปสั่งงาน Claude ผ่าน tools/claude.ps1

## 2026-10-09 14:39:19  (exit 0, 486s, $0.67, 17 turns)

**Codex สั่ง:**

``text
You are Claude, helper to Codex in C:\RL_Fall. Analysis only; do not edit any files. In particular never edit auto-loop/ (progress.md exception is not needed).
Task: concise second opinion on M2 architecture after 7 failed recipes. Read only src/rl_fall/train.py anchor implementation, tests/test_anchor.py, and if needed local SB3 PPO train in WSL. Latest wide+separate anchor ae1 final results seeds 63001/2/3: recoverable survival 83.3/95.8/83.3% vs S1 87.5/95.8/95.8; false give-up 11.9/4.3/17.4%; weighted damage .001461/.001629/.001391 vs S1 .001867/.001899/.001427, passive .001607 all. Plain ae1 previously passed seeds 1/3 but 2 damage .00175 > passive. Anchor ae5 preserves recovery but hardly reduces damage. Separate Adam KL phase strength controlled by epochs, coef scaling largely canceled by Adam. No hard-push episodes leak into anchor; parameter sharing can interfere.
Proposed single experiment: optional AnchorPPO subclass adding coef * KL(frozen S1 || current) to the same minibatch PPO objective, evaluated only on upright recoverable rollout samples, keep old post-update mode for reproducibility, correct raw obs capture (callback sees rms already advanced). New mode CLI/env/tag/manifest; coef=1.0, original recoverable max=.08; 200 updates all seeds final checkpoint only. Review whether this is well-posed, recommend minimal implementation pitfalls or reject with evidence. Raw samples should use VecNormalize.get_original_obs saved at rollout start/end step and previous fallen mask; align time-major flatten to SB3 rollout minibatch indices; S1 normalizer frozen. Avoid reading whole project. Return concise analysis with file pointers. Check done: state suggested architecture, any critical pitfall, no edits.

``

**Claude ตอบ:**

**Verdict:** the experiment is well-posed. Run it, with three changes below. I changed no files and didn't run anything.

## Why the joint objective is the right next test
- The current mode runs a PPO update, then a separate KL pass through the same Adam optimizer (`src/rl_fall/train.py:229-264`, called at `:600-607`). Adam rescales gradients per parameter, so in a separate pass `coef` mostly cancels out and the anchor strength is really set by `anchor_epochs`. That matches what you saw. Inside one minibatch loss, `coef` is weighed against the PPO surrogate before Adam sees the gradient, so `coef=1.0` finally means something.
- **Correction to your premise:** with `net_arch={"pi":[w,w],"vf":[w,w]}` (`train.py:304-307`), the only shared extractor is SB3's default flatten extractor, which has no weights. The actor and critic share no parameters, so "parameter sharing" isn't what interferes. What actually interferes:
  1. Both loss phases share the Adam moment estimates.
  2. One actor has to serve both soft-push and hard-push episodes.

  The joint loss fixes the first. It can't fix the second.

## Suggested architecture
It matches what `tests/test_anchor.py:241-380` already specifies.
- **Module:** `rl_fall/anchor_ppo.py` with `AnchorPPO(PPO)`.
  - `set_anchor_samples(policy, obs_s2, obs_s1, coef)`.
  - `anchor_loss(n)` draws n samples uniformly, with replacement, from the eligible pool.
  - `train()` is a copy of SB3 2.9.0's `ppo.py` train loop with `loss += coef * anchor_loss(batch_size)` before `backward` (upstream builds the loss at line 256 and clips gradients at 277).
  - Pin the copied loop to SB3 2.9.0.
- **Sampling:** draw from the eligible pool instead of matching rollout-buffer minibatch indices. The KL term needs no advantages or returns, so index matching adds risk for no gain. If you do match indices anyway: SB3 flattens env-major, not time-major (`arr.swapaxes(0,1).reshape(...)`, `buffers.py:75`, so row = env·n_steps + step). Store per-step arrays at `self.model.rollout_buffer.pos` inside `_on_step`. That is valid because `on_step` (`on_policy_algorithm.py:224`) runs before `rollout_buffer.add` (`:247`).
- **Raw observations:** at `_on_rollout_start`, cache `env.get_original_obs()`, which is the raw form of `_last_obs`. Use that cache for step t in `_on_step`, then re-cache from `get_original_obs()` after the step; after a done that returns the reset observation, as the test expects.
  - The current reconstruction (`train.py:207`) un-normalizes with statistics that have already moved forward one step. Drop it in the new mode, but keep it in the old mode for reproducibility.
  - The evaluation path doesn't touch the training environment's raw-observation cache (`evaluate` builds its own VecNormalize, `train.py:383`), so the cache stays valid between `learn()` calls.
- **Masks:** keep the previous-fallen mask and the push-impulse mask as they are (`train.py:200-219`). The callback order is correct.

## Pitfalls
1. **Early stopping:** `target_kl=0.02` (`train.py:48`) stops training at `approx_kl > 0.03`. Pulling toward S1 moves the policy away from the policy that collected the rollout, which can raise `approx_kl` and end epochs early. Anchoring then quietly weakens PPO. Log the epochs completed per update for both the anchored and plain runs.
2. **Critic warmup:** skip `anchor_loss` while the actor is frozen. The test at `:379` requires `kl_before == kl_after` on row 0.
3. **Gradient clipping:** the gradient-norm clip at `max_grad_norm` now covers both terms together. A large early KL gradient can take up most of the clip budget. Log the anchor loss and the policy loss separately, plus the gradient norm before clipping.
4. **RNG stream:** sampling with replacement uses the torch RNG, which also drives action noise during rollouts. Anchored runs are therefore not RNG-matched to plain runs once samples are non-empty. That's fine, but say so in the manifest.
5. **Possible confound:** before the push, upright states in soft and hard episodes look the same. So the anchor (soft episodes only) and PPO (hard episodes too) pull the same pre-push states in different directions. If the damage gains come from a pre-push posture change, the anchor will erase them along with the false give-ups. Cheap fix: log the KL separately for pre-push and post-push samples.
6. **Effective strength:** sampling with replacement gives a fixed number of anchor samples per minibatch, regardless of what fraction of the rollout is eligible. Record that the effective weight is `coef` per minibatch, not scaled by the eligible fraction.
7. **Sanity check:** assert once per rollout that the cached raw observation, normalized with the previous step's statistics, roughly equals `obs_tensor`. This catches stale caches, for example after resume.

## Pass/fail rule
Write this down before running, since seed 2 has already flipped a verdict once. Pass only if, on all three seeds:
- recoverable survival is at least S1's, within a margin set in advance;
- false give-up is at most S1's (that value isn't in your numbers, so check it);
- weighted damage is below passive's .001607.

If `coef=1` fails on survival, a second coefficient would be one more recipe rather than new evidence. A more informative next step would be to give hard and soft pushes separate behaviour, but that's beyond this experiment.

event ดิบ: `auto-loop/.loop/claude/20261009-143113.jsonl`

## 2026-10-09 14:42:50  (exit 0, 105s, $0.60, 10 turns)

**Codex สั่ง:**

``text
You are Claude helper reviewing Codex's final change in C:\RL_Fall. Review only; DO NOT edit files. Never edit auto-loop/ except progress.md (not needed). No training or jobs. Do not search all filesystem. SB3 source if needed is exactly /home/sstangkh73/venvs/rl_fall/lib/python3.12/site-packages/stable_baselines3/ppo/ppo.py in Ubuntu; read via wsl.exe -d Ubuntu -- bash -lc with literal paths and no shell variables.
Task: review git diff -- src/rl_fall/train.py tests/test_anchor.py scripts/run_stage1.sh scripts/run_stage2_pilot.sh scripts/lanta/s2_pilot.sbatch and new files src/rl_fall/anchor_ppo.py scripts/run_stage2_objective.sh. These implement optional joint PPO+KL objective vs reproducible legacy post_update mode. Uniform with-replacement eligible independent samples per PPO minibatch; exact cached raw obs; critic warmup skips KL; copied SB3 2.9.0 train with MIT attribution (dependency already pinned in pyproject); fields excluded teacher/samples save; diagnostics epochs/optimizer steps/loss/gradnorm; CLI/env/tag propagate including LANTA script (no submit). New experiment coefficient1 recoverable .08 200 updates 63001/2/3 sequential, final200 predeclared; gate stays GOAL.md exactly (S2 survival >= S1 -5pp, FGU<=10%, damage below both baselines). Your earlier recommendation FGU<=S1 was rejected because it changes user gate.
Full verify before new diagnostic edits passed 64 tests M1 PASS M2-M4 incomplete. Tiny objective training+resume test passed; real body8env2update smoke is running. Please identify only correctness/regression blockers or say OK with residual limits; do not read entire project, do not run tests (Codex does). Done = concise findings with file pointers and confirmation no files edited.

``

**Claude ตอบ:**

No blockers. I found nothing that would make the objective mode or the legacy `post_update` mode wrong or non-reproducible. I edited no files and ran no tests or jobs; I only read the diff, the two new files, the related parts of `train.py`, and the installed SB3 `ppo.py` (via WSL).

**What I checked and found correct**
- **Copied SB3 code:** `AnchorPPO.train` (`src/rl_fall/anchor_ppo.py:83-225`) matches installed SB3 2.9.0 `PPO.train` line for line. The only additions are the KL term (`:170-172`), recording the gradient norm that `clip_grad_norm_` already returns (`:193-194`), and counters. The MIT notice is there. gSDE and non-Box action spaces are rejected (`:57`), so dropping the `use_sde` path is safe.
- **Sampling:** each PPO minibatch draws its own independent uniform sample, with replacement, from the eligible states (`:72`). It is not tied to the PPO buffer indices. `rollout_buffer.get` uses numpy's RNG, so the PPO minibatch order is unchanged.
- **Cached raw observations:** `raw_previous` comes from `get_original_obs()` at rollout start (after `_setup_learn` has reset the env) and again after each step (`train.py:243,268`). So it pairs exactly with `obs_tensor` for the same action, and for finished envs it uses the reset observation, not `terminal_observation`. The anchor normalisation matches VecNormalize (`sqrt(var+eps)`, then clip). `evaluate` uses a separate env (`train.py:431-445`), so it doesn't disturb `old_obs`.
- **Timing:** `on_rollout_end` sets the samples before `train()` runs.
- **Critic warmup:** while the actor is frozen, the KL step and its RNG draws are skipped (`anchor_ppo.py:92`). This matches `set_actor_trainable`, which freezes `policy_net`, `action_net` and `log_std` together.
- **Checkpoints and resume:**
  - `_excluded_save_params` keeps the teacher and the samples out of the checkpoint.
  - The attributes are set before `super().__init__`, so `AnchorPPO.load` works on a plain S1 PPO zip.
  - On resume, `force_reset` forces an env reset and `previous_fallen` starts as zeros.
- **Legacy mode:** unchanged. It still uses the `PPO` class, the same callback, `anchor_step` and the default `anchor_epochs`.
- **Tags:** the objective script's tag `s2_dmg10000_anc1.0_objective` matches what `run_stage2_pilot.sh` builds, so the eval scripts find the run. The LANTA script appends the tag parts in the same order as the pilot script.

**Limits to note (none block the run)**
1. **`anchor_kl_before` means different things in the two modes.** In objective mode it is measured before any update (`anchor_ppo.py:91`). In legacy mode it is measured after the PPO update but before the anchor phase (`train.py:302`). Don't compare that column across modes directly.
2. **`UPDATES` isn't pinned in `scripts/run_stage2_objective.sh`.** It isn't exported there, so a stray `UPDATES` in the calling shell would change the run length. Eval stays at update 200 either way. Consider `export UPDATES=200` to lock in the predeclared update-200 endpoint.
3. **Resuming isn't bit-identical.** The torch RNG state isn't restored, so a resumed run won't exactly match an uninterrupted one. The legacy `randperm` path has the same limit, and the manifest flag `anchor_uses_torch_rng` records it.
4. **The KL can be logged without a matching step.** If `target_kl` stops training early, the KL for that minibatch is logged but no optimizer step is taken. `anchor_optimizer_steps` counts this correctly.
5. **`run_stage2_pilot.sh` now stops on the first seed that fails** (`|| exit $?`). Before, it went on to the next seed. This also applies to legacy runs. It's safer, but it is a behaviour change.
6. **Two cosmetic manifest issues:** with objective mode and `anchor_coef=0`, it still reports `anchor_raw_obs: true`. `anchor_policy_loss` holds the PPO policy-gradient loss, not a separate anchor loss.

The gate in the scripts is unchanged; I don't suggest changing it.

event ดิบ: `auto-loop/.loop/claude/20261009-144105.jsonl`

## 2026-10-09 19:12:36  (exit 0, 64s, $0.47, 3 turns)

**Codex สั่ง:**

``text
You are Claude, the short-task helper; Codex is the lead in C:\RL_Fall. Analyze only. Do not edit ANY files (especially auto-loop; general rule prohibits editing auto-loop except progress.md, but this task forbids all edits). Do not launch jobs or invoke another AI. Do not ask questions. Give a concise second opinion, <=600 words. No need to inspect the whole project.

M2 has failed in 8 predeclared recipes. Need check our conclusion and propose ONE next experiment without changing gates or selecting a favorable checkpoint. Current results and diagnostics are in tmp/s2_joint_results.txt; source implementation src/rl_fall/anchor_ppo.py; recipe scripts/run_stage2_objective.sh. Relevant earlier result tables are planning/Curriculum_Plan_TH.md lines 552-640. Read only those files/sections if needed.

Current experiment: joint PPO + coef1.0 * KL(S1||S2), recoverable U(0,.08), hard U(.15,.25) half episodes, damage weight10000, M1 initial checkpoint, fixed 200 updates. Anchor samples come from recoverable, upright episodes, raw pre-action observations. The actor is shared across hard and easy states, so anchor can constrain damage behavior via parameter sharing. Target KL early stops 2/1/0 of 200 updates in seeds 63001/2/3, all after update50 have full5 epochs/40 steps. Mean KL_after last50=.03329/.03342/.03159, no evidence of optimization collapse. Grad norm ~3.7 (clipped at .5), combined actor/critic norm, cannot attribute conflict from scalar losses alone.

Final200: S2 recoverable survival .875/.95833/.9375 vs S1 .875/.95833/.95833; FGU .07143/.04348/.06522. Hard weighted damage .00108895/.00168224/.00129235 vs S1 .00186652/.00189923/.00142666 and passive .00160695 all seeds. Head damage fraction .00008132/0/.00008541 (NOT exactly zero). Seed63002 torso weighted component .00157543 =93.65% of S2 total hard damage; arms low. Hard survivors seed63002=3/48 (S1=0) and damage mean includes survivors. Others=0. Final200 passes 63001/63003 only; 63002 fails passive comparison by4.685%. Trend150 passes all3 but was diagnostic only and cannot replace200.

Legacy ae1 coef1 (separate Adam phase) also passed2/3 final with 63002 damage .00175. Legacywide ae1 failed all3. Unanchored wide reduced63002 damage to .00116 but failed FGU. Proposed next: same objective recipe from M1, coefficient0.5 for ALL3 seeds at final200, one variable changed, path tags anc0.5_objective. Hypothesis: reducing conditional KL weighting lets seed63002 improve torso impacts while hopefully preserving recovery; no claim it will pass. Need fixed endpoint and all results incl failed seeds, no milestone file until gate passes. Alternative is diagnostics rather than another training run if evidence insufficient.

Verify completion: state whether our gate interpretation is correct; flag factual/causal overclaims; assess whether coef0.5 is a justified single-variable experiment or recommend one better-supported step (brief rationale). No edits. If prior failures suggest an architectural concern, name it, but no human is available and user authorizes reasonable autonomous decisions.

``

**Claude ตอบ:**

**Second opinion: M2 joint-objective coef1.0 run**

I read only `tmp/s2_joint_results.txt` and plan lines 552–640. I did not check `anchor_ppo.py`, so the claims about gradient clipping are taken on trust. I made no edits.

**1. Gate interpretation: correct.**
- At final update 200, seed 63002 has damage 0.00168224 against passive 0.00160695. That is 4.685% too high, so the seed fails, and M2 fails at 2/3 seeds.
- Your figures check out:
  - Recoverable survival and FGU pass in all three seeds.
  - The torso share is right: weighted torso (2×0.000787716 = 0.00157543) plus the arms gives exactly 0.00168224.
  - The 3/48 hard survivors match the per-impulse data (2/16 at 0.15, 1/16 at 0.20).
- Not using the update-150 results instead of update 200 is correct.

**2. Overclaims and missing caveats**
- **"Anchor constrains damage via parameter sharing."** This is still a hypothesis, and this run cuts against it. In 63001 the anchored run reached 0.00109, the lowest damage of any anchored run, so the anchor did not block damage reduction there.
- **Seed 63002 does not respond to anchor strength.** Its update-200 damage across four anchor variants was:
  - ae5 (strongest): 0.00164
  - ae1: 0.00175
  - wide-ae1: 0.00163
  - joint coef1: 0.00168

  The strongest anchor did not give the worst damage. There is no evidence that weakening the anchor helps this seed.
- **The joint coef1 anchor is already weaker than legacy ae1.** KL measured after the anchor step is about 0.033 here, versus about 0.010–0.020 for ae1 and about 0.002 for ae5. It is also still rising (0.028 → 0.034) rather than levelling off. So "loosen the anchor further" has already been partly tried, and 63002 did not move.
- **The miss is smaller than normal checkpoint-to-checkpoint swing.** 63002's damage went 0.00145 / 0.00176 / 0.00144 / 0.00168 at updates 50/100/150/200, a swing of about 20%. The miss is only 4.7% (about 0.000075). With 48 episodes, a single-variable change of that size cannot be told apart from evaluation noise.
- **Including hard survivors probably flatters 63002.** If those 3 survivors had low damage, the damage among episodes that actually fell is even higher than reported. Avoid wording that suggests the survivors made it look worse.
- **A pattern across the whole failure history.** Every policy, S1 included, concentrates damage on the torso (×2 weight). The passive baseline spreads it onto the arms (passive torso 0.00048, arms about 0.00064). Beating passive requires moving impacts from torso to arms, which only 63001 has done. Anchor strength does not target that.
- **Not a gate item, but worth noting.** 63003 at push 0.08 dropped to 87.5% versus S1 95.8%.

**3. Is coef0.5 justified?**
It is a valid single-variable change, but weakly supported:
- There is no dose-response in 63002.
- The expected effect is smaller than the noise.
- FGU has little headroom (0.071 / 0.043 / 0.065 against a 10% limit), and the unanchored and wide runs failed on FGU.

Most likely outcome: 63002 lands around 0.0015–0.0017 again, and FGU risk rises in 63001 and 63003. That would cost about 3.5 hours and teach little.

**4. Recommended next step: one diagnostic before any more training**
Re-evaluate the existing, frozen update-200 checkpoints with no training.
- **What:** all three S2 checkpoints, plus S1 and passive, on an independent eval seed set at least 4× larger (for example 192 hard episodes).
- **Logged per episode:** survived or fell, weighted damage by body part, and push impulse.
- **Declare up front, in the log:** this is diagnostic only. It cannot change the M2 verdict, is not a gate re-evaluation, and does not select any checkpoint.
- **What it tells you:**
  - (a) The standard error of S2 minus passive damage per seed. That shows whether any coefficient change could be detected at all.
  - (b) 63002's damage among falls only, without the survivors.
  - (c) Whether 63002's excess comes from a few bad torso-first falls or is spread evenly.

**How to decide after it:**
- If the 63002 gap is more than about 2 SE and torso-driven, the next training run should target where impacts land, not anchor strength. One option is Codex's option 3: anchor only before the push and in late recovery, leaving the ambiguous early post-push window free. That is a single variable, with tag and rules declared before the run.
- If the gap is within about 1 SE, record that the current 48-episode gate cannot resolve this margin. Don't change the gate. Choose the next run by expected effect size, and coef0.5 is unlikely to qualify.
- If you skip the diagnostic and train anyway, coef0.5 for all 3 seeds is defensible, but write down the predicted outcome above before running.

**Architectural concern.** One shared actor serves both recoverable and unrecoverable pushes, and the two look alike in the observation for the first steps after the push. So any recoverable-only anchor also pulls the fall behaviour in those early steps. That is a structural limit, not a tuning problem. If the window-limited anchor also fails, the next things to try are a push-phase or time-since-push input, or a separate fall head.

event ดิบ: `auto-loop/.loop/claude/20261009-191132.jsonl`

## 2026-10-09 19:20:00  (exit 0, 67s, $0.48, 14 turns)

**Codex สั่ง:**

``text
You are Claude, short review helper; Codex leads C:\RL_Fall. Review only, do not edit files or run jobs. General prohibition: no auto-loop edits except progress.md; THIS TASK forbids all edits including progress.md. Do not ask questions, invoke another AI, or read the whole project.

Review ONLY new scripts/stage2_diagnostics.py, scripts/run_stage2_objective_diagnostic.sh, tests/test_stage2_diagnostics.py, and the new section in git diff -- planning/Curriculum_Plan_TH.md. Use git diff --no-index /dev/null for untracked new files if necessary or read directly. Give blockers and factual/statistical concerns <=400 words. Targeted tests passed4; real checkpoint smoke is running; verify will run next.

Purpose: Your previous opinion recommended larger independent reset-seed evaluation rather than coefficient tuning. This implementation evaluates all3 FROZEN objective coef1 final200 checkpoints against their explicit S1 final200 paths + passive. Independent reset base19000, scale4 ->192 easy+192hard episodes per policy perseed. It preserves the existing production evaluator unchanged; reuses its environment/run_episode/summarize. The fixed angle grid is expanded, not a random-angle population sample. Seed19000+i is reused across impulses, so paired SE and percentile bootstrap resample means over reset-seed clusters, with equal cluster size assertion. No CI across training seeds, no claim of a formal population guarantee. It logs all raw episodes, per-part weights, falls-only and survivors-only means, torso paired difference tails, paired differences against both baselines. Output is separate from source results, contains diagnostic_only=true,milestone_eligible=false, source checkpoint/norm/manifest/script hashes. No writing milestones, training, changing gates, or choosing150.

Check pairing/cluster SE/CI correctness, fixed input paths, safe reuse behavior with source/evidence hashes, gate independence and wording. Docs corrected your previous implication that checkpoint swings determine evaluation SE: they cannot without frozen-policy evaluation. Checkpoint150 all-pass remains diagnostic only. No need another algorithm recommendation. Verify done = identify concrete issues or say no blockers after checking; DO NOT modify files.

``

**Claude ตอบ:**

**Verdict: no blockers.** I read the three new files, the plan diff, and the relevant parts of `stage2_eval.py`. I edited nothing and ran nothing (I skipped plan-and-report because it writes files).

**Pairing, SE and CI: correct**
- Pairs are matched on (impulse, seed, angle) within each group. Duplicate, missing and unbalanced pairs are rejected.
- The SE is the standard deviation of the per-cluster means divided by √n, and the percentile bootstrap resamples those cluster means. The test's expected values (SE = 1, CI [1, 3]) are right.
- One wording point: in `make_scenarios`, the angle at index *i* goes with seed base + *i*. So each "reset-seed cluster" is really a seed×angle unit, and the bootstrap treats the angle as random too. That's fine as a diagnostic, but the doc line "fixed angle grid, not random sampling" should also say the CI resamples seed and angle together. That gives 64 clusters of 3 for the hard group and 96 clusters of 2 for the easy group.
- Seeds 19000–19063 appear in both groups, but the groups are analysed separately, so this is fine.

**Inputs and gate independence**
- The S1 paths in the run script match the `init_checkpoint`/`anchor_checkpoint` paths in the S2 manifests in `s2joint_diagnostics_20261009.txt`. Those manifests point to S1 `checkpoint.zip`, while the diagnostic hashes `checkpoint_update_200.zip`. This is consistent with the production gate's `--s1-update 200` default. If someone later reads it as "S2 vs its anchor teacher", it's only true if the two files are byte-identical; checking that hash once would close the question.
- I couldn't check from Windows that the source files exist: they live under the WSL tree, not `C:\RL_Fall\results`. The running smoke test will show this.
- Environment settings match production: S1 and passive use the S1 manifest, and the push is fixed at 0.45.
- Gate seeds (9000–9023) don't overlap. The overlap check only compares against the scale-1 gate scenarios, which is what the M2 evals actually used.
- `evaluation_summary` contains no pass/fail fields, and `diagnostic_only` and `milestone_eligible` are set as described. The gate code and the production evaluator are unchanged.

**Reuse behaviour: safe**
- Saved results are reused only if the provenance matches exactly (source hashes, script hash, evaluator hash). Any later edit to the script therefore forces a fresh output directory. That's expensive but safe.
- `episodes.json` is written with a plain, non-atomic write after all episodes finish. A crash mid-write would leave a corrupt file that fails loudly on the next run.
- The summary is re-checked against the episodes file's hash before reuse.

**Statistical points for the docs (not blockers)**
1. There will be three seeds × two baselines × two groups, so 12 CIs. Don't read one CI that excludes zero (for example 63002 vs passive) as confirmed without saying it is one of many comparisons.
2. The 63002 excess was about 7.5e-5 on a mean of about 1.6e-3. Write down now whether 64 clusters is expected to detect an effect that size. Otherwise "CI includes zero" may just mean there's too little data, and that shouldn't be read as evidence that S2 matches the baseline.
3. The torso tail statistics count individual episodes and have no cluster SE, so they should be labelled as descriptive only.
4. The falls-only and survivors-only means compare different subsets of episodes for each policy, so they are not paired. If the policies fall at different rates, their difference should not be read as a causal per-fall effect.

The plan wording ("diagnostic only", no M2 replacement, no claim about uncertainty across training) is accurate. It also correctly separates checkpoint-to-checkpoint swings from evaluation SE.

event ดิบ: `auto-loop/.loop/claude/20261009-191853.jsonl`
