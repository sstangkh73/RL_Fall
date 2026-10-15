#!/usr/bin/env python3
"""Check milestones M1-M4 of auto-loop/GOAL.md against real result files.

Runs inside WSL (stdlib only). Exit 0 only when every milestone passes.
Writes a readable summary to auto-loop/reports/goal-status.md.
AI must not edit this file (run-loop.ps1 stops if it changes).

Usage: python3 check_goal.py --win-root /mnt/c/RL_Fall --wsl-repo ~/RL_Fall
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

SEEDS = ("63001", "63002", "63003")
# M1 gate (GOAL.md): natural stance before the push, reactive survival after it.
MAX_FEET_DRIFT_M = 0.08
MAX_COM_DROP_M = 0.03
MAX_TRUNK_LEAN_DEG = 10.0
MIN_MEAN_SURVIVAL_AT_0_10 = 0.60
# Runs must be trained after the stance-penalty fix was planned.
MIN_RUN_STAMP = "20261008T000000"
# M2 gate (plan section 5).
RECOVERABLE_TOLERANCE = 0.05
MAX_FALSE_GIVE_UP = 0.10
MIN_EVAL_EPISODES = 48
# M4 report size (~4 pages).
MAX_SUMMARY_CHARS = 16000


class Check:
    def __init__(self, name):
        self.name = name
        self.errors = []
        self.notes = []

    def fail(self, msg):
        self.errors.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    @property
    def ok(self):
        return not self.errors


def load_json(path, check, what):
    if not os.path.isfile(path):
        check.fail(f"{what} not found: {path}")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        check.fail(f"{what} unreadable ({exc}): {path}")
        return None


def latest_key(d, prefix):
    keys = [k for k in d if re.fullmatch(prefix + r"_\d+", k)]
    return max(keys, key=lambda k: int(k.rsplit("_", 1)[1])) if keys else None


def value_at(impulses, values, impulse):
    for i, x in enumerate(impulses):
        if abs(x - impulse) < 1e-9:
            return values[i]
    return None


def check_m1(win, repo):
    c = Check("M1 — S1 gate (natural stance + reactive survival, 3 seeds)")
    spec = load_json(os.path.join(win, "auto-loop/milestones/m1_runs.json"), c, "m1_runs.json")
    if spec is None:
        return c, {}
    runs = spec.get("seeds", {})
    survivals = []
    per_seed = {}
    for seed in SEEDS:
        rel = runs.get(seed)
        if not rel:
            c.fail(f"seed {seed}: no run listed in m1_runs.json")
            continue
        run_dir = os.path.join(repo, rel)
        stamp = re.search(r"(\d{8}T\d{6})$", rel.rstrip("/"))
        if not stamp:
            c.fail(f"seed {seed}: run dir has no timestamp: {rel}")
        elif stamp.group(1) < MIN_RUN_STAMP:
            c.fail(f"seed {seed}: run {stamp.group(1)} predates the fix (needs >= {MIN_RUN_STAMP})")
        if f"seed{seed}" not in rel.replace("_", ""):
            c.fail(f"seed {seed}: run dir does not belong to this seed: {rel}")
        curve = load_json(os.path.join(run_dir, "survival_curve.json"), c, f"seed {seed} survival_curve.json")
        if curve is None:
            continue
        upd, stance = latest_key(curve, "update"), latest_key(curve, "stance")
        if upd is None or stance is None:
            c.fail(f"seed {seed}: survival_curve.json lacks update_N / stance_N")
            continue
        imp = curve.get("impulses", [])
        surv = curve[upd].get("survival", [])
        step = curve[upd].get("step_rate", [])
        st = curve[stance]
        drift, drop, lean = st.get("feet_drift_m"), st.get("com_drop_m"), st.get("trunk_lean_deg")
        s10 = value_at(imp, surv, 0.10)
        s08, s12 = value_at(imp, step, 0.08), value_at(imp, step, 0.12)
        per_seed[seed] = dict(drift=drift, drop=drop, lean=lean, s10=s10, step08=s08, step12=s12, key=upd)
        if drift is None or drift > MAX_FEET_DRIFT_M:
            c.fail(f"seed {seed}: feet drift {fmt_cm(drift)} > {MAX_FEET_DRIFT_M * 100:.0f} cm")
        if drop is None or drop > MAX_COM_DROP_M:
            c.fail(f"seed {seed}: CoM drop {fmt_cm(drop)} > {MAX_COM_DROP_M * 100:.0f} cm")
        if lean is None or lean > MAX_TRUNK_LEAN_DEG:
            c.fail(f"seed {seed}: trunk lean {lean} deg > {MAX_TRUNK_LEAN_DEG:.0f}")
        if s10 is None:
            c.fail(f"seed {seed}: impulse 0.10 not evaluated")
        else:
            survivals.append(s10)
        if s08 is None or s12 is None:
            c.fail(f"seed {seed}: step rate at 0.08 and 0.12 not evaluated")
        elif not s12 > s08:
            c.fail(f"seed {seed}: stepping does not rise with push (0.08: {s08:.0%}, 0.12: {s12:.0%})")
    if len(survivals) == len(SEEDS):
        mean = sum(survivals) / len(survivals)
        c.note(f"mean survival at 0.10 = {mean:.0%}")
        if mean < MIN_MEAN_SURVIVAL_AT_0_10:
            c.fail(f"mean survival at 0.10 = {mean:.0%} < {MIN_MEAN_SURVIVAL_AT_0_10:.0%}")
    for seed, v in per_seed.items():
        c.note(
            f"seed {seed} ({v['key']}): drift {fmt_cm(v['drift'])}, CoM drop {fmt_cm(v['drop'])}, "
            f"lean {fmt(v['lean'], '.1f')} deg, survive@0.10 {fmt(v['s10'], '.0%')}, "
            f"step@0.08 {fmt(v['step08'], '.0%')} -> @0.12 {fmt(v['step12'], '.0%')}"
        )
    return c, per_seed


def check_m2(win, repo):
    c = Check("M2 — S2 pilot (recover or fall, 3 seeds)")
    spec = load_json(os.path.join(win, "auto-loop/milestones/m2_summary.json"), c, "m2_summary.json")
    if spec is None:
        return c
    for seed in SEEDS:
        entry = spec.get("seeds", {}).get(seed)
        if not entry:
            c.fail(f"seed {seed}: missing in m2_summary.json")
            continue
        ev = load_json(os.path.join(repo, entry.get("eval_file", "")), c, f"seed {seed} eval_file")
        if ev is None:
            continue
        script = ev.get("script")
        if not script or not os.path.isfile(os.path.join(repo, script)):
            c.fail(f"seed {seed}: eval file must name the script that produced it (field 'script')")
        try:
            rec, unrec = ev["recoverable"], ev["unrecoverable"]
            n_rec, n_unrec = int(rec["n_episodes"]), int(unrec["n_episodes"])
            s2_surv, s1_surv = float(rec["s2_survival"]), float(rec["s1_survival"])
            d_s2 = float(unrec["s2_weighted_damage"])
            d_s1 = float(unrec["s1_weighted_damage"])
            d_pass = float(unrec["passive_weighted_damage"])
            fgu = float(ev["false_give_up"])
            head = float(ev["head_damage_share"])
        except (KeyError, TypeError, ValueError) as exc:
            c.fail(f"seed {seed}: eval file missing field {exc}")
            continue
        if min(n_rec, n_unrec) < MIN_EVAL_EPISODES:
            c.fail(f"seed {seed}: too few eval episodes ({n_rec}/{n_unrec} < {MIN_EVAL_EPISODES})")
        if s2_surv < s1_surv - RECOVERABLE_TOLERANCE:
            c.fail(f"seed {seed}: recoverable survival S2 {s2_surv:.0%} < S1 {s1_surv:.0%} - 5 pts")
        if not (d_s2 < d_s1 and d_s2 < d_pass):
            c.fail(f"seed {seed}: unrecoverable damage S2 {d_s2:.3g} not below S1 {d_s1:.3g} and passive {d_pass:.3g}")
        if fgu > MAX_FALSE_GIVE_UP:
            c.fail(f"seed {seed}: false give-up {fgu:.0%} > {MAX_FALSE_GIVE_UP:.0%}")
        c.note(
            f"seed {seed}: recoverable S2 {s2_surv:.0%} vs S1 {s1_surv:.0%}; damage S2 {d_s2:.3g} / "
            f"S1 {d_s1:.3g} / passive {d_pass:.3g}; false give-up {fgu:.0%}; head share {head:.0%}"
        )
    return c


def check_m3(win):
    c = Check("M3 — LANTA compute estimate + Slurm script")
    spec = load_json(os.path.join(win, "auto-loop/milestones/m3_compute.json"), c, "m3_compute.json")
    if not os.path.isfile(os.path.join(win, "planning/LANTA_Compute_Estimate_TH.md")):
        c.fail("planning/LANTA_Compute_Estimate_TH.md not found")
    if spec is None:
        return c, None
    nh = spec.get("node_hours")
    if not isinstance(nh, (int, float)) or nh <= 0:
        c.fail("node_hours must be a positive number")
        nh = None
    for key in ("transitions_to_gate", "throughput_per_node", "runs"):
        if key not in spec:
            c.fail(f"m3_compute.json missing '{key}'")
    sb = spec.get("sbatch", [])
    if not sb:
        c.fail("m3_compute.json lists no sbatch scripts")
    for rel in sb:
        p = os.path.join(win, rel)
        if not os.path.isfile(p):
            c.fail(f"sbatch script not found: {rel}")
        elif "#SBATCH" not in open(p, encoding="utf-8", errors="replace").read():
            c.fail(f"no #SBATCH directives in {rel}")
    if nh:
        c.note(f"node_hours = {nh}")
    return c, nh


def check_m4(win, node_hours):
    c = Check("M4 — evidence summary for advisor / LANTA")
    p = os.path.join(win, "planning/Evidence_Summary_TH.md")
    if not os.path.isfile(p):
        c.fail("planning/Evidence_Summary_TH.md not found")
        return c
    text = open(p, encoding="utf-8").read()
    if len(text) > MAX_SUMMARY_CHARS:
        c.fail(f"summary too long ({len(text)} chars > {MAX_SUMMARY_CHARS}, ~4 pages)")
    for seed in SEEDS:
        if seed not in text:
            c.fail(f"summary does not report seed {seed}")
    if node_hours is not None and str(int(node_hours)) not in text.replace(",", ""):
        c.fail(f"summary does not state the node-hours from M3 ({node_hours})")
    for word in ("S3", "proxy"):
        if word not in text:
            c.fail(f"summary lacks '{word}' (S3 plan / damage-proxy limitation)")
    return c


def fmt(x, spec):
    return "n/a" if x is None else format(x, spec)


def fmt_cm(x):
    return "n/a" if x is None else f"{x * 100:.1f} cm"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win-root", required=True)
    ap.add_argument("--wsl-repo", required=True)
    a = ap.parse_args()
    win, repo = a.win_root, os.path.expanduser(a.wsl_repo)

    m1, _ = check_m1(win, repo)
    m2 = check_m2(win, repo)
    m3, nh = check_m3(win)
    m4 = check_m4(win, nh)
    checks = [m1, m2, m3, m4]

    lines = [f"# Goal status ({dt.datetime.now():%Y-%m-%d %H:%M:%S})", ""]
    for c in checks:
        lines.append(f"## {'PASS' if c.ok else 'FAIL'} — {c.name}")
        lines += [f"- ✗ {e}" for e in c.errors] + [f"- {n}" for n in c.notes] + [""]
    report = "\n".join(lines)
    print(report)
    try:
        os.makedirs(os.path.join(win, "auto-loop/reports"), exist_ok=True)
        with open(os.path.join(win, "auto-loop/reports/goal-status.md"), "w", encoding="utf-8") as f:
            f.write(report)
    except OSError as exc:
        print(f"warning: could not write goal-status.md: {exc}", file=sys.stderr)
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
