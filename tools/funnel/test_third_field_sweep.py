#!/usr/bin/env python3
"""5x regression test for third_field_sweep.generate — API-free.

Fixture (per task): the stage-3 escalation of a stage-2 seed. Fields are the real
model175 CHN ids (the task shorthand gainlossvarianceratio60 / alpha60 is the
mdl175_* field): field1=mdl175_gainlossvarianceratio60, field2=mdl175_alpha60,
field3=mdl175_bp, structure3=multiply, seed_structure=divide (differs), region=CHN,
universe=TOP2000U, delay=0. Asserts each run: 180 unique valid rows, all THREE
fields present, structure3 (multiply) differs from the seed structure, SIGN ~50/50,
(region,universe,delay) fixed, deterministic vs run 1, and validate_targets reports
0 errors. Guards cover: field3 same-dataset / != seed fields / MATRIX enforcement,
structure3==seed_structure rejection, and the structure3=if_else zero-centered wrap.
Prints PASS/FAIL per run and a summary; exit 0 iff 5/5.
"""
import json, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.funnel.third_field_sweep import generate

ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")
SCRATCH = pathlib.Path("/private/tmp/claude-501/-Users-kanenguyen-wq-pipeline/"
                       "796acd74-5c3c-4644-8d64-55644a861aa4/scratchpad")
SCRATCH.mkdir(parents=True, exist_ok=True)

FX = dict(field1="mdl175_gainlossvarianceratio60", field2="mdl175_alpha60",
          field3="mdl175_bp", structure3="multiply", seed_structure="divide",
          region="CHN", universe="TOP2000U", delay=0)

_WSUM = re.compile(r"^\s*[\d.]+\s*\*.+\+\s*[\d.]+\s*\*")


def check(rows) -> list[str]:
    errs = []
    if len(rows) != 180:
        errs.append(f"expected 180 rows, got {len(rows)}")
    keys = set()
    for r in rows:
        s = r["settings"]
        k = (re.sub(r"\s+", "", r["formula"]), s["region"], s["universe"], s["delay"],
             s["neutralization"], s["decay"], s["truncation"], s["pasteurization"],
             s["unitHandling"], s["nanHandling"])
        keys.add(k)
    if len(keys) != len(rows):
        errs.append(f"non-unique rows: {len(rows)-len(keys)} collisions")
    # SIGN 50/50
    neg = sum(1 for r in rows if r["formula"].strip().startswith("-"))
    if not (0.35*len(rows) <= neg <= 0.65*len(rows)):
        errs.append(f"sign 50/50 axis broken: {neg}/{len(rows)} negative")
    # (region,universe,delay) fixed
    fixed = {(r["settings"]["region"], r["settings"]["universe"], r["settings"]["delay"]) for r in rows}
    if fixed != {(FX["region"], FX["universe"], FX["delay"])}:
        errs.append(f"(region,universe,delay) not fixed: {fixed}")
    for r in rows:
        f = r["formula"]
        # structure3 (multiply) is the OUTER structure, differing from the seed
        if not f.lstrip("-").startswith("multiply("):
            errs.append(f"row not structure3=multiply outer: {f[:70]}"); break
        if _WSUM.match(f):
            errs.append(f"weighted-sum leaked: {f[:70]}"); break
        # all THREE fields present in every row
        if not (FX["field1"] in f and FX["field2"] in f and FX["field3"] in f):
            errs.append(f"missing a field: {f[:80]}"); break
        # the seed structure (divide) appears nested inside — differs from multiply
        if "divide(" not in f:
            errs.append(f"seed structure (divide) not nested: {f[:80]}"); break
    # config axes actually swept
    for axis in ("neutralization", "decay", "truncation", "pasteurization", "nanHandling"):
        if len({r["settings"][axis] for r in rows}) < 2:
            errs.append(f"axis {axis} not swept (constant)")
    if {r["settings"]["unitHandling"] for r in rows} != {"VERIFY"}:
        errs.append("unitHandling not the derived legal value VERIFY")
    return errs


def check_guards() -> list[str]:
    errs = []
    # structure3 == seed_structure rejected for if_else/divide (no new interaction shape)...
    try:
        generate(FX["field1"], FX["field2"], FX["field3"], "if_else", "CHN",
                 "TOP2000U", 0, seed_structure="if_else")
        errs.append("structure3==seed_structure (if_else) NOT rejected")
    except ValueError:
        pass
    # ...but ALLOWED for multiply (Khoa 2026-07-17): multiply(seed, t3(f3)) is a genuine 3-way
    # product, richer than the 2-way seed and magnitude-preserving (not the if_else sign-collapse).
    try:
        rows3 = generate(FX["field1"], FX["field2"], FX["field3"], "multiply", "CHN",
                         "TOP2000U", 0, seed_structure="multiply", n=30)
        if len(rows3) != 30:
            errs.append(f"multiply 3-way produced {len(rows3)} rows (want 30)")
        f0 = rows3[0]["formula"].lstrip("-")
        if not f0.startswith("multiply(multiply("):
            errs.append(f"3-way multiply not nested multiply(multiply(...)): {f0[:70]}")
    except ValueError as e:
        errs.append(f"multiply==multiply 3-way wrongly rejected: {e}")
    # cross-dataset field3 rejected
    try:
        generate(FX["field1"], FX["field2"], "pv13_hf_composite", "multiply", "CHN",
                 "TOP2000U", 0, seed_structure="divide")
        errs.append("cross-dataset field3 NOT rejected")
    except ValueError:
        pass
    # field3 == field1 rejected
    try:
        generate(FX["field1"], FX["field2"], FX["field1"], "multiply", "CHN",
                 "TOP2000U", 0, seed_structure="divide")
        errs.append("field3==field1 NOT rejected")
    except ValueError:
        pass
    # non-MATRIX / unknown same-dataset field3 rejected
    try:
        generate(FX["field1"], FX["field2"], "mdl175_notarealmatrixfield", "multiply",
                 "CHN", "TOP2000U", 0, seed_structure="divide")
        errs.append("non-MATRIX field3 NOT rejected")
    except ValueError:
        pass
    # structure3=if_else: seed zero-centered as condition, both fields survive, 180 rows
    ie = generate(FX["field1"], FX["field2"], FX["field3"], "if_else", "JPN",
                  "TOP1600", 1, seed_structure="multiply")
    cond_re = re.compile(r"^-?if_else\(greater\(zscore\((.+)\), 0\), ")
    for r in ie:
        m = cond_re.match(r["formula"])
        if not m:
            errs.append(f"if_else structure3 lost zero-centered greater() shape: {r['formula'][:80]}"); break
        inner = m.group(1)
        if not (FX["field1"] in inner and FX["field2"] in inner):
            errs.append("if_else structure3 seed condition lost a seed field"); break
        if FX["field3"] not in r["formula"]:
            errs.append("if_else structure3 lost field3"); break
    if len(ie) != 180:
        errs.append(f"if_else structure3 sweep produced {len(ie)} rows")
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
        out = SCRATCH / f"s3_fixture_run{run}.json"
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
