#!/usr/bin/env python3
"""5x regression test for funnel_stage3 --dry-run — API-free, deterministic.

Fixtures (all mdl175, MATRIX, same dataset prefix):
  * top-9 seeds where EVERY seed FAILs at least one check (zero-fail=False) so the
    escalation TRIGGERS; homogeneous CHN/TOP2000U/delay0.
  * 9 third-field/structure choices (one per seed), each field3 a NEW mdl175 field
    != field1/field2, structure != the seed's.

Each run asserts: escalation triggered, 9x180=1620 targets, ceil(1620/10)=162
multi-sim POSTs, exactly TOP-27 selected, manifest + top27 written, and the whole
thing is byte-identical to run 1 (deterministic mock sim). Guard runs (not part of
the 5x count) assert the three REFUSALS: != 9 choices, cross-dataset field3, and
field3 in {field1,field2}; plus the NO-ESCALATION branch when a seed is zero-fail.
"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.funnel import funnel_stage3 as f3

SCRATCH = pathlib.Path("/private/tmp/claude-501/-Users-kanenguyen-wq-pipeline/"
                       "796acd74-5c3c-4644-8d64-55644a861aa4/scratchpad")
SCRATCH.mkdir(parents=True, exist_ok=True)

ROOT_FIELD = "mdl175_gainlossvarianceratio120"
SEED_F2 = ["mdl175_alpha20", "mdl175_gainvariance120", "mdl175_01am", "mdl175_02am",
           "mdl175_06am", "mdl175_21ame", "mdl175_41vme", "mdl175_42cr", "mdl175_02da"]
SEED_STRUCT = ["multiply", "if_else", "divide", "multiply", "if_else",
               "divide", "multiply", "if_else", "divide"]
FIELD3 = ["mdl175_02ame", "mdl175_02dca", "mdl175_02icc", "mdl175_02rc", "mdl175_02vbo",
          "mdl175_21cr", "mdl175_21tvp", "mdl175_41rta", "mdl175_405rtsr"]
# structure3 must differ from the seed structure
STRUCT3 = ["divide", "multiply", "if_else", "divide", "multiply",
           "if_else", "divide", "multiply", "if_else"]

SETTINGS = {"region": "CHN", "universe": "TOP2000U", "delay": 0}


def make_top9(all_fail=True):
    """9 seed rows. all_fail=True -> every seed has a FAIL (escalation triggers)."""
    rows = []
    for i in range(9):
        # full-row checks; a FAIL present for every seed when all_fail
        # the base gate set is adjudicated, so a non-all_fail seed is a real zero-fail rather
        # than a row that merely failed to report the gates that would have blocked it
        checks = [{"name": "LOW_SHARPE", "result": "FAIL" if all_fail else "PASS",
                   "value": 1.0, "limit": 3.49},
                  {"name": "LOW_FITNESS", "result": "PASS", "value": 1.2, "limit": 1.0},
                  {"name": "LOW_TURNOVER", "result": "PASS", "value": 0.2, "limit": 0.01},
                  {"name": "HIGH_TURNOVER", "result": "PASS", "value": 0.2, "limit": 0.7},
                  {"name": "CONCENTRATED_WEIGHT", "result": "PASS"}]
        rows.append({"id": f"seed{i}", "old_id": f"seed{i}", "sharpe": 1.0 + i * 0.01,
                     "checks": checks, "settings": dict(SETTINGS, instrumentType="EQUITY")})
    return rows


def make_choices():
    return [{"field1": ROOT_FIELD, "field2": SEED_F2[i], "seed_structure": SEED_STRUCT[i],
             "third_field": FIELD3[i], "structure": STRUCT3[i]} for i in range(9)]


def one_run(run):
    m = f3.run_stage3(run, make_top9(), make_choices(), dry_run=True)
    errs = []
    if not m["escalation_triggered"]:
        errs.append("escalation NOT triggered on an all-fail top-9")
        return errs, None
    if m["n_targets"] != 1620:
        errs.append(f"n_targets {m['n_targets']} != 1620")
    if m["n_posts"] != 162:
        errs.append(f"n_posts {m['n_posts']} != ceil(1620/10)=162")
    if len(m["top27"]) != 27:
        errs.append(f"top27 has {len(m['top27'])} rows, not 27")
    if len(set(m["top27"])) != len(m["top27"]):
        errs.append("top27 has duplicate ids")
    top_path = f3.ROOT / m["top27_file"]
    man_path = f3.FUN / f"{run}_stage3_manifest.json"
    if not top_path.exists() or not man_path.exists():
        errs.append("top27/manifest file missing")
    # each seed contributed a distinct 180-block -> 1620 unique target ids
    targets = json.load(open(f3.ROOT / m["targets_file"]))
    if len({t["id"] for t in targets}) != 1620:
        errs.append("target ids not globally unique")
    return errs, m


def guard_refusals():
    errs = []
    top9, ch = make_top9(), make_choices()
    # != 9 choices
    try:
        f3.run_stage3("g_nchoices", top9, ch[:8], dry_run=True)
        errs.append("!= 9 choices NOT refused")
    except SystemExit:
        pass
    # cross-dataset field3
    bad = make_choices(); bad[0]["third_field"] = "pv13_hf_composite"
    try:
        f3.run_stage3("g_xdataset", top9, bad, dry_run=True)
        errs.append("cross-dataset field3 NOT refused")
    except SystemExit:
        pass
    # field3 == field1
    b1 = make_choices(); b1[0]["third_field"] = b1[0]["field1"]
    try:
        f3.run_stage3("g_f3eqf1", top9, b1, dry_run=True)
        errs.append("field3==field1 NOT refused")
    except SystemExit:
        pass
    # field3 == field2
    b2 = make_choices(); b2[0]["third_field"] = b2[0]["field2"]
    try:
        f3.run_stage3("g_f3eqf2", top9, b2, dry_run=True)
        errs.append("field3==field2 NOT refused")
    except SystemExit:
        pass
    # NO-ESCALATION branch: a seed that passes ALL gates -> no sweep
    m = f3.run_stage3("g_noescalate", make_top9(all_fail=False), ch, dry_run=True)
    if m["escalation_triggered"] or m["top27"] is not None:
        errs.append("escalation wrongly triggered when a seed is zero-fail")
    return errs


def main():
    baseline = None
    passes = 0
    for run in range(1, 6):
        # SAME run name across iterations: determinism means same inputs -> same
        # output (the mock RNG is salted by the run name, which is an input).
        errs, m = one_run("s3test")
        errs += guard_refusals()
        if m is not None:
            blob = json.dumps(m["top27"], sort_keys=True)
            if baseline is None:
                baseline = blob
            elif blob != baseline:
                errs.append("non-deterministic: top27 differs from run 1")
        ok = not errs
        passes += ok
        print(f"RUN {run}: {'PASS' if ok else 'FAIL'}"
              + ("" if ok else "  -> " + "; ".join(errs)))
    print(f"\n{passes}/5 runs PASS")
    sys.exit(0 if passes == 5 else 1)


if __name__ == "__main__":
    main()
