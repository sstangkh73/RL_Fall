#!/usr/bin/env bash
# One predeclared experiment: joint10000 recipe + no survival reward after a hard push
# starts (HARD_NO_BONUS=1), so only damage counts on hard pushes. Everything else as joint10000.
# Primary gate (pre-registered 10 Oct 2026, before training): final200 s2_eval.json with
# --episodes-scale 4 = 192 easy + 192 hard paired episodes per policy (GOAL needs >= 48),
# all three seeds. s2_eval_n48.json (default 48) and updates 50/100/150 (48) are
# supplementary only and never replace the primary verdict. No gate changes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
SEEDS=(63001 63002 63003)
S1_TIMES=(20261008T100414 20261008T112408 20261008T124330)
TAG=s2_dmg10000_anc1.0_objective_hardnobonus

# Validate all pinned sources before any training; never select a latest M1 run.
for i in 0 1 2; do
  seed="${SEEDS[$i]}"
  s1="results/stage1_v1_0/seed_${seed}/push_0.12_hard0.5_posture1.0_natural4_r2/3d_A_env8_subproc_cpu_seed${seed}_t4_${S1_TIMES[$i]}"
  stage="results/stage2/seed_${seed}/push_0.08_hard0.5_posture1.0_${TAG}"
  "$PY" - "$s1" "$stage" "$seed" <<'PY'
import hashlib, json, sys
from pathlib import Path
s1, stage, seed = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
m = json.loads((s1 / 'manifest.json').read_text())
assert m['status'] == 'complete' and m['seed'] == seed
assert m['measured_updates'] == 200 and m['body'] == 'v1_0'
assert m['posture_version'] == 4 and m['natural_stance']
for f in ('checkpoint.zip', 'vecnormalize.pkl', 'checkpoint_update_200.zip', 'vecnormalize_update_200.pkl'):
    p = s1 / f
    print('Pinned S1', p, 'sha256', hashlib.sha256(p.read_bytes()).hexdigest(), flush=True)
runs = list(stage.glob('3d_*'))
assert len(runs) <= 1, 'ambiguous S2 runs: refuse latest-run selection'
if runs:
    assert list(runs[0].glob('checkpoint_update_*.zip')), 'existing S2 has no resume checkpoint; refuse a second run'
PY
done
if [ "${CHECK_ONLY:-0}" = 1 ]; then exit 0; fi

check_eval() {  # out s2 s1 update n_episodes
  "$PY" - "$@" <<'PY'
import json, sys
from pathlib import Path
e = json.loads(Path(sys.argv[1]).read_text())
assert e['script'] == 'scripts/stage2_eval.py'
assert Path(e['s2_run']).resolve() == Path(sys.argv[2]).resolve()
assert Path(e['s1_run']).resolve() == Path(sys.argv[3]).resolve()
assert e['s2_update'] == int(sys.argv[4]) and e['s1_update'] == 200
assert e['after_s'] == 2.5
assert e['recoverable']['n_episodes'] == e['unrecoverable']['n_episodes'] == int(sys.argv[5])
print('Reusing existing evaluation:', sys.argv[1])
PY
}

for i in 0 1 2; do
  seed="${SEEDS[$i]}"
  s1="results/stage1_v1_0/seed_${seed}/push_0.12_hard0.5_posture1.0_natural4_r2/3d_A_env8_subproc_cpu_seed${seed}_t4_${S1_TIMES[$i]}"
  stage="results/stage2/seed_${seed}/push_0.08_hard0.5_posture1.0_${TAG}"
  # Clear optional inherited overrides, so the named experiment is fixed.
  env BODY=v1_0 POSTURE=1.0 POSTURE_VERSION=4 NATURAL=1 CP=10 HARD=0.5 HARD_RANGE="0.15 0.25" \
    FALL_CONTINUE=2.5 DAMAGE_W=10000 HARD_NO_BONUS=1 OUT_ROOT=results/stage2 STAGE=S2_recover_or_fall \
    INIT_CHECKPOINT="$s1/checkpoint.zip" TAG="$TAG" CRITIC_WARMUP=0 LR= LOG_STD= EVERY=25 \
    ANCHOR=1.0 ANCHOR_CHECKPOINT="$s1/checkpoint.zip" ANCHOR_EPOCHS= ANCHOR_MODE=objective \
    bash scripts/run_stage1.sh "$seed" 200 0.08
  # There must be exactly one run, and its effective configuration must match.
  s2=$("$PY" - "$stage" "$s1" "$seed" <<'PY'
import json, sys
from pathlib import Path
stage, s1, seed = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
runs = list(stage.glob('3d_*'))
assert len(runs) == 1, 'ambiguous S2 runs'
run = runs[0]
m = json.loads((run / 'manifest.json').read_text())
for k, expected in {'status':'complete', 'seed':seed, 'measured_updates':200,
                    'damage_weight':10000, 'hard_push_no_bonus':True,
                    'anchor_coef':1.0, 'anchor_mode':'objective',
                    'anchor_raw_obs':True, 'max_push_impulse':0.08,
                    'fall_continue_s':2.5, 'posture_version':4, 'body':'v1_0',
                    'natural_stance':True, 'hard_push_fraction':0.5,
                    'hard_push_range':[0.15, 0.25], 'anchor_max_impulse':0.08,
                    'capture_point_weight':10, 'posture_weight':1.0,
                    'critic_warmup_updates':0, 'learning_rate_override':None,
                    'log_std_override':None}.items():
    assert m[k] == expected, (k, m[k], expected)
assert Path(m['anchor_checkpoint']).resolve() == (s1 / 'checkpoint.zip').resolve()
if m['resumed_from_update'] is None:
    assert Path(m['init_checkpoint']).resolve() == (s1 / 'checkpoint.zip').resolve()
else:
    # Training records the resume checkpoint as init_checkpoint. Check the saved
    # update0 actor/critic and observation RMS against pinned S1 instead.
    import numpy as np
    import torch
    from stable_baselines3 import PPO
    import pickle
    torch.set_num_threads(1)
    initial = PPO.load(run / 'checkpoint_update_0.zip', device='cpu').policy.state_dict()
    frozen = PPO.load(s1 / 'checkpoint.zip', device='cpu').policy.state_dict()
    assert initial.keys() == frozen.keys()
    assert all(torch.equal(initial[k], frozen[k]) for k in initial)
    with (run / 'vecnormalize_update_0.pkl').open('rb') as f:
        a = pickle.load(f)
    with (s1 / 'vecnormalize.pkl').open('rb') as f:
        b = pickle.load(f)
    assert all(np.array_equal(getattr(a.obs_rms, k), getattr(b.obs_rms, k))
               for k in ('mean', 'var', 'count'))
    assert (a.clip_obs, a.epsilon) == (b.clip_obs, b.epsilon)
print(run)
PY
  )
  # Primary gate first: final200 at 192 episodes per group.
  out="$s2/s2_eval.json"
  if [ -e "$out" ]; then
    check_eval "$out" "$s2" "$s1" 200 192
  else
    "$PY" scripts/stage2_eval.py "$s2" --s1-run "$s1" --s2-update 200 --s1-update 200 \
      --episodes-scale 4 --out "$out"
  fi
  # Supplementary (never the verdict): default 48 at final200, and trend checkpoints.
  for update in 200 50 100 150; do
    out="$s2/s2_eval_update_${update}.json"
    if [ "$update" = 200 ]; then out="$s2/s2_eval_n48.json"; fi
    if [ -e "$out" ]; then
      check_eval "$out" "$s2" "$s1" "$update" 48
    else
      "$PY" scripts/stage2_eval.py "$s2" --s1-run "$s1" --s2-update "$update" --s1-update 200 --out "$out"
    fi
  done
done
