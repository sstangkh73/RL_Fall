#!/usr/bin/env bash
# Curriculum stage 1 (balance): train through increasing push levels, each level
# continuing from the previous level's final checkpoint. Safe to rerun after an
# interruption: complete levels are skipped and an interrupted level resumes from
# its newest periodic checkpoint.
# Usage: [BODY=v0_3] [HARD=0.5] [POSTURE=2.0] [INIT_CHECKPOINT=path.zip] [LOG_STD=-1.6] [TAG=name]
#        scripts/run_stage1.sh [seed] [updates-per-level] [levels...]
#   BODY  body version (default v0_2)
#   HARD  share of pushes drawn from the step-requiring range (default 0)
#   POSTURE  weight of the pre-push foot-placement penalty (default 0)
#   INIT_CHECKPOINT  continue from an existing policy instead of training from scratch
#   LOG_STD  reset the policy log-std after loading INIT_CHECKPOINT (first level only)
#   TAG  suffix for the output directory, to keep repeated settings apart
#   CP  weight of the post-push capture-point landing bonus (default 0)
#   POSTURE_VERSION  1 = any foot drift penalised, 2 = natural stance rule,
#                    3 = natural stance, cost keeps growing but reward stays positive (default 1)
#   NATURAL  1 = start from a randomised relaxed stance (default 0)
#   HARD_RANGE  "lo hi" impulse range of the step-requiring pushes (default 0.13 0.25)
#   FALL_CONTINUE  S2: seconds to keep running after a fall (default: a fall ends the episode)
#   DAMAGE_W  S2: reward cost per unit of weighted damage (default 0)
#   CRITIC_WARMUP  freeze the actor for the first N updates of each level (default 0)
#   LR  override the learning rate of INIT_CHECKPOINT / resumed runs (default: keep it)
#   ANCHOR  KL loss weight toward the frozen ANCHOR_CHECKPOINT policy (default 0)
#   ANCHOR_CHECKPOINT  explicit S1 checkpoint, also used when resuming
#   OUT_ROOT  results root (default results/stage1 or results/stage1_<body>)
#   STAGE  manifest stage label (default S1_balance)
set -euo pipefail

SEED="${1:-61001}"
UPDATES="${2:-300}"
shift $(( $# > 2 ? 2 : $# ))
LEVELS=("${@:-0.2 0.3 0.45}")
read -r -a LEVELS <<< "${LEVELS[*]}"
EVERY="${EVERY:-25}"  # balance updates are 16,384 transitions each
BODY="${BODY:-v0_2}"
HARD="${HARD:-0}"
POSTURE="${POSTURE:-0}"
CP="${CP:-0}"
POSTURE_VERSION="${POSTURE_VERSION:-1}"
EXTRA=()
if [ "${NATURAL:-0}" = "1" ]; then EXTRA+=(--natural-stance); fi
if [ -n "${HARD_RANGE:-}" ]; then read -r -a RANGE <<< "$HARD_RANGE"; EXTRA+=(--hard-push-range "${RANGE[@]}"); fi
if [ -n "${FALL_CONTINUE:-}" ]; then EXTRA+=(--fall-continue-s "$FALL_CONTINUE"); fi
if [ -n "${DAMAGE_W:-}" ]; then EXTRA+=(--damage-weight "$DAMAGE_W"); fi
if [ -n "${CRITIC_WARMUP:-}" ]; then EXTRA+=(--critic-warmup-updates "$CRITIC_WARMUP"); fi
if [ -n "${LR:-}" ]; then EXTRA+=(--learning-rate "$LR"); fi
if [ -n "${ANCHOR:-}" ]; then EXTRA+=(--anchor-coef "$ANCHOR"); fi
if [ -n "${ANCHOR_CHECKPOINT:-}" ]; then EXTRA+=(--anchor-checkpoint "$ANCHOR_CHECKPOINT"); fi
STAGE="${STAGE:-S1_balance}"
TAG="${TAG:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HOME/venvs/rl_fall/bin/python}"
if [ "$BODY" = "v0_2" ]; then OUT="results/stage1/seed_${SEED}"
else OUT="results/stage1_${BODY}/seed_${SEED}"; fi
if [ -n "${OUT_ROOT:-}" ]; then OUT="${OUT_ROOT}/seed_${SEED}"; fi
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
mkdir -p "$OUT"

INIT=()
if [ -n "${INIT_CHECKPOINT:-}" ]; then INIT=(--init-checkpoint "$INIT_CHECKPOINT"); fi
STD=()
if [ -n "${LOG_STD:-}" ]; then STD=(--log-std "$LOG_STD"); fi
for LEVEL in "${LEVELS[@]}"; do
    LEVEL_OUT="$OUT/push_${LEVEL}"
    if [ "$HARD" != "0" ]; then LEVEL_OUT="${LEVEL_OUT}_hard${HARD}"; fi
    if [ "$POSTURE" != "0" ]; then LEVEL_OUT="${LEVEL_OUT}_posture${POSTURE}"; fi
    if [ -n "$TAG" ]; then LEVEL_OUT="${LEVEL_OUT}_${TAG}"; fi
    RUN_DIR="$(ls -td "$LEVEL_OUT"/3d_* 2>/dev/null | head -1 || true)"
    if [ -n "$RUN_DIR" ] && grep -q '"status": "complete"' "$RUN_DIR/manifest.json" 2>/dev/null; then
        echo "=== $(date '+%F %T') S1 body=$BODY seed=$SEED push<=$LEVEL already complete: $RUN_DIR"
    else
        START=(--output "$LEVEL_OUT" "${INIT[@]}" "${STD[@]}")
        if [ -n "$RUN_DIR" ] && ls "$RUN_DIR"/checkpoint_update_*.zip > /dev/null 2>&1; then
            START=(--resume "$RUN_DIR")
        fi
        echo "=== $(date '+%F %T') S1 body=$BODY seed=$SEED push<=$LEVEL hard=$HARD posture=$POSTURE updates=$UPDATES ${START[*]}"
        "$PY" -m rl_fall.train --environment 3d --body "$BODY" --mode balance \
            --hard-push-fraction "$HARD" --posture-weight "$POSTURE" \
            --capture-point-weight "$CP" --posture-version "$POSTURE_VERSION" "${EXTRA[@]}" \
            --condition A --max-push-impulse "$LEVEL" --stage "$STAGE" \
            --device cpu --seed "$SEED" --n-envs 8 --threads 4 \
            --warmup-updates 0 --measured-updates "$UPDATES" --evaluation-scenarios 64 \
            --checkpoint-updates $(seq 0 "$EVERY" "$UPDATES") "${START[@]}" >> "$LEVEL_OUT.log" 2>&1
        RUN_DIR="$(ls -td "$LEVEL_OUT"/3d_* | head -1)"
    fi
    INIT=(--init-checkpoint "$RUN_DIR/checkpoint.zip")
    STD=()
done
echo "=== $(date '+%F %T') S1 body=$BODY seed=$SEED done"
