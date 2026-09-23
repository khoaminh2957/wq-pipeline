#!/usr/bin/env python3
"""5x determinism + wiring test for funnel_run.py --dry-run. Prints PASS/FAIL per run.
A green run:
  - produces exactly 5 stage-1 tops, 25 stage-2 tops, a benchmark file,
  - records the BLOCKING precheck gate (S10-20/22) for stage1 + all 5 seeds,
  - verifies same-dataset stage2 enforcement (S10-21) both positively (manifest
    flag) and negatively (4-choice / wrong-dataset / same-field / same-structure
    specs must be REFUSED before any sim),
  - is byte-identical to the first run (deterministic)."""
import copy, hashlib, json, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SPEC = ROOT / "state/funnel/example_spec.json"
RUN = "funnel_test"
MAN = ROOT / f"state/funnel/{RUN}_manifest.json"
BENCH = ROOT / f"state/benchmark/{RUN}_benchmark.json"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def funnel(spec_path):
    return subprocess.run([sys.executable, str(HERE / "funnel_run.py"),
                           "--spec", str(spec_path), "--run", RUN, "--dry-run"],
                          capture_output=True, text=True)


def bad_specs(base):
    """Mutations that stage2 enforcement (S10-21) must refuse."""
    four = copy.deepcopy(base)
    four["stage2"] = four["stage2"][:4]
    same_field = copy.deepcopy(base)
    same_field["stage2"][0]["second_field"] = base["root"]["field"]
    wrong_ds = copy.deepcopy(base)
    wrong_ds["stage2"][0]["second_field"] = "adjfactor"      # pv1, not root dataset
    same_struct = copy.deepcopy(base)
    same_struct["root"]["structure"] = same_struct["stage2"][0]["structure"]
    return {"4-choices": four, "second==root-field": same_field,
            "wrong-dataset": wrong_ds, "structure==root": same_struct}


def check_enforcement(tmpdir):
    base = json.load(open(SPEC))
    for name, spec in bad_specs(base).items():
        p = pathlib.Path(tmpdir) / f"bad_{name.replace('=', '_')}.json"
        p.write_text(json.dumps(spec))
        r = funnel(p)
        if r.returncode == 0:
            return f"S10-21 enforcement missed: {name} spec was ACCEPTED"
        if f"{RUN}_stage1_targets.json" in r.stderr:  # must refuse before any sim
            return f"S10-21 enforcement too late for {name}"
    return None


def one_run(tmpdir):
    err = check_enforcement(tmpdir)
    if err:
        return None, err
    r = funnel(SPEC)
    if r.returncode != 0:
        return None, f"exit {r.returncode}: {r.stderr.strip()[:300]}"
    if not MAN.exists() or not BENCH.exists():
        return None, "manifest/benchmark not written"
    man = json.load(open(MAN))
    bench = json.load(open(BENCH))
    if len(man["stage1"]["top5"]) != 5:
        return None, f"top5 has {len(man['stage1']['top5'])}"
    if len(man["top25"]) != 25:
        return None, f"top25 has {len(man['top25'])}"
    if man["stage2"]["total_simmed"] != 500:
        return None, f"stage2 simmed {man['stage2']['total_simmed']} != 500"
    seeds = man["stage2"]["seeds"]
    if len(seeds) != 5:
        return None, f"stage2 ran {len(seeds)} seeds != 5"
    # S10-20/22: the blocking precheck (incl. validate_targets) ran for every batch
    gates = [man["stage1"]["precheck"]] + [s["precheck"] for s in seeds]
    if not all(g.get("ok") and g.get("validate_targets") for g in gates):
        return None, f"precheck gate missing/failed in manifest: {gates}"
    # S10-21: every seed's second field verified same-dataset
    if not all(s.get("same_dataset_verified") for s in seeds):
        return None, "same_dataset_verified missing on a stage2 seed"
    if bench["n"] != 25 or not bench["alphas"]:
        return None, "benchmark missing alphas"
    if bench["alphas"][0]["rank"] != 1:
        return None, "benchmark not ranked"
    return (digest(MAN), digest(BENCH)), None


def main():
    ref = None
    ok = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(1, 6):
            sig, err = one_run(tmpdir)
            if err:
                print(f"RUN {i}: FAIL — {err}")
                continue
            if ref is None:
                ref = sig
                print(f"RUN {i}: PASS (reference; man={sig[0][:12]} bench={sig[1][:12]})")
                ok += 1
            elif sig == ref:
                print(f"RUN {i}: PASS (identical to reference)")
                ok += 1
            else:
                print(f"RUN {i}: FAIL — output differs from reference "
                      f"(man={sig[0][:12]} bench={sig[1][:12]})")
    print(f"\n{ok}/5 runs green")
    sys.exit(0 if ok == 5 else 1)


if __name__ == "__main__":
    main()
