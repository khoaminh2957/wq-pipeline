#!/usr/bin/env python3
"""5x regression test for second_field_sweep.generate — API-free.

Fixture (per task): field1=mdl175_gainvariance120, field2=mdl175_alpha20,
structure=multiply, root_structure=weighted_sum, region=CHN, universe=TOP2000U,
delay=0. Asserts each run: 100 unique valid rows, structure != plain weighted
sum, (region,universe,delay) fixed, deterministic vs run 1, and validate_targets
reports 0 errors. Iteration-2 fix coverage: multiply filter=false/true both swept
(S10-18), winsorize std=2/std=4 both swept (S10-18), JPN gets the full 11-value
neutralization list derived from settings_options.json (S10-19), unitHandling
axis derived (S10-16), cross-dataset field2 rejected (S10-21), and
structure==root_structure rejected. Prints PASS/FAIL per run and a summary.
"""
import json, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.funnel.second_field_sweep import (generate, NEUT_BY_REGION,
                                             cond_transforms, transforms,
                                             _ZERO_CENTERED_PREFIXES)

ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")
SCRATCH = pathlib.Path("/private/tmp/claude-501/-Users-kanenguyen-wq-pipeline/"
                       "796acd74-5c3c-4644-8d64-55644a861aa4/scratchpad")
SCRATCH.mkdir(parents=True, exist_ok=True)

FX = dict(field1="mdl175_gainvariance120", field2="mdl175_alpha20",
          structure="multiply", root_structure="weighted_sum",
          region="CHN", universe="TOP2000U", delay=0)

_WSUM = re.compile(r"^\s*[\d.]+\s*\*.+\+\s*[\d.]+\s*\*")


def check(rows) -> list[str]:
    errs = []
    if len(rows) != 180:
        errs.append(f"expected 180 rows, got {len(rows)}")
    # uniqueness by formula+settings
    keys = set()
    for r in rows:
        s = r["settings"]
        k = (re.sub(r"\s+", "", r["formula"]), s["region"], s["universe"], s["delay"],
             s["neutralization"], s["decay"], s["truncation"], s["pasteurization"],
             s["unitHandling"], s["nanHandling"])
        keys.add(k)
    neg = sum(1 for r in rows if r["formula"].strip().startswith("-"))
    if not (0.35*len(rows) <= neg <= 0.65*len(rows)):
        errs.append(f"sign 50/50 axis broken: {neg}/{len(rows)} negative")
    if len(keys) != len(rows):
        errs.append(f"non-unique rows: {len(rows)-len(keys)} collisions")
    # (region,universe,delay) fixed
    fixed = {(r["settings"]["region"], r["settings"]["universe"], r["settings"]["delay"]) for r in rows}
    if fixed != {(FX["region"], FX["universe"], FX["delay"])}:
        errs.append(f"(region,universe,delay) not fixed: {fixed}")
    # structure is the multiply interaction, not a weighted sum, uses both fields
    for r in rows:
        f = r["formula"]
        if not f.lstrip("-").startswith("multiply("):
            errs.append(f"row not multiply-structure: {f[:60]}"); break
        if _WSUM.match(f):
            errs.append(f"weighted-sum leaked: {f[:60]}"); break
        if FX["field1"] not in f or FX["field2"] not in f:
            errs.append(f"missing a field: {f[:60]}"); break
    # some real config-axis variety was actually swept
    for axis in ("neutralization", "decay", "truncation", "pasteurization", "nanHandling"):
        if len({r["settings"][axis] for r in rows}) < 2:
            errs.append(f"axis {axis} not swept (constant)")
    # S10-16: unitHandling derived from settings_options.json (single legal value)
    if {r["settings"]["unitHandling"] for r in rows} != {"VERIFY"}:
        errs.append("unitHandling not the derived legal value VERIFY")
    # S10-18: multiply filter enum swept per full documented signature
    filt = {m.group(1) for r in rows for m in [re.search(r"filter=(true|false)\)$", r["formula"])] if m}
    if filt != {"true", "false"}:
        errs.append(f"multiply filter param not fully swept: {filt}")
    # S10-18: winsorize std swept
    stds = {m for r in rows for m in re.findall(r"winsorize\([^,]+, std=(\d)\)", r["formula"])}
    if not {"2", "4"} <= stds:
        errs.append(f"winsorize std not swept: {stds}")
    # CHN full 11-value neutralization list available AND broadly sampled
    if len(NEUT_BY_REGION[FX["region"]]) != 11:
        errs.append(f"CHN neutralization list != 11: {NEUT_BY_REGION[FX['region']]}")
    if len({r["settings"]["neutralization"] for r in rows}) < 8:
        errs.append("fewer than 8 distinct neutralizations sampled across 180 rows")
    return errs


def check_guards() -> list[str]:
    """Iteration-2 defect guards that must raise / hold (S10-19, S10-21)."""
    errs = []
    # S10-19: JPN/USA neutralizations derived from settings_options.json = 11 values
    for reg in ("JPN", "USA"):
        if len(NEUT_BY_REGION.get(reg, [])) != 11:
            errs.append(f"{reg} neutralization list not the 11 derived values "
                        f"({len(NEUT_BY_REGION.get(reg, []))})")
    jpn = generate("mdl175_gainvariance120", "mdl175_alpha20", "if_else",
                   "JPN", "TOP1600", 1, root_structure="weighted_sum")
    if len({r["settings"]["neutralization"] for r in jpn}) < 8:
        errs.append("JPN sweep uses < 8 distinct neutralizations (hardcoded-5 regression)")
    if len(jpn) != 180 or not all(r["formula"].lstrip("-").startswith("if_else(") for r in jpn):
        errs.append("if_else structure sweep broken")
    # v7.1 must-fix: no if_else condition transform may make greater(cond, 0)
    # constant. [0,1]-ranged transforms (rank/ts_rank/group_rank) and [-1,0]
    # reverse(rank) are banned as conditions; every emitted condition must be a
    # zero-centered transform, and the two-field combination must survive.
    banned_cond = ("rank(", "ts_rank(", "group_rank(", "reverse(")
    cond_re = re.compile(r"^-?if_else\(greater\((.+), 0\), ")
    for r in jpn:
        m = cond_re.match(r["formula"])
        if not m:
            errs.append(f"if_else row lost its greater(cond, 0) shape: {r['formula'][:70]}"); break
        cond = m.group(1)
        if cond.startswith(banned_cond) or not cond.startswith(_ZERO_CENTERED_PREFIXES):
            errs.append(f"degenerate if_else condition (non-zero-centered): {cond[:60]}"); break
        if "mdl175_alpha20" not in r["formula"]:
            errs.append("if_else row lost field2"); break
    if set(cond_transforms("f")) - set(transforms("f")):
        errs.append("cond_transforms not a subset of transforms")
    if any(t.startswith(banned_cond) for t in cond_transforms("f")):
        errs.append("cond_transforms still contains a [0,1]/[-1,0]-ranged transform")
    # S10-21: cross-dataset second field must be rejected
    try:
        generate("mdl175_gainvariance120", "pv13_hf_composite", "multiply",
                 "CHN", "TOP2000U", 0)
        errs.append("cross-dataset field2 NOT rejected")
    except ValueError:
        pass
    # structure must differ from root structure
    try:
        generate("mdl175_gainvariance120", "mdl175_alpha20", "multiply",
                 "CHN", "TOP2000U", 0, root_structure="multiply")
        errs.append("structure==root_structure NOT rejected")
    except ValueError:
        pass
    return errs


def main():
    baseline = None
    passes = 0
    for run in range(1, 6):
        rows = generate(**FX)
        errs = check(rows) + check_guards()
        blob = json.dumps(rows, sort_keys=True)
        if baseline is None:
            baseline = blob
        elif blob != baseline:
            errs.append("non-deterministic: differs from run 1")
        # validate_targets.py must report 0 errors
        out = SCRATCH / f"s2_fixture_run{run}.json"
        json.dump(rows, open(out, "w"), indent=1)
        vt = subprocess.run([sys.executable, str(ROOT / "tools/validate_targets.py"), str(out)],
                            capture_output=True, text=True)
        if vt.returncode != 0:
            errs.append("validate_targets FAIL: " + vt.stdout.strip().replace("\n", " | "))
        ok = not errs
        passes += ok
        print(f"RUN {run}: {'PASS' if ok else 'FAIL'}"
              + ("" if ok else "  -> " + "; ".join(errs)))
    print(f"\n{passes}/5 runs PASS")
    sys.exit(0 if passes == 5 else 1)


if __name__ == "__main__":
    main()
