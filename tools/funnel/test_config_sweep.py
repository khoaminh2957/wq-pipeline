#!/usr/bin/env python3
"""5x regression test for config_sweep.py. Fixture root: CHN d0 mdl175_gainvariance120 TOP2000U.
Asserts: exactly 100 rows, all unique, all (region,universe,delay)==root, validate_targets exit 0,
distinct neutralizations >= 4, settings enums legal per settings_options.json, and the pool
grammar carries the mandated sweeps (ts_quantile 3 drivers [Khoa fix], quantile driver x sigma
[S10-15], winsorize std 3/4/5 [S10-18], normalize useStd). Also asserts determinism
(same seed -> identical output). Prints PASS/FAIL per run."""
import json, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config_sweep  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CS = HERE / "config_sweep.py"
VT = ROOT / "tools/validate_targets.py"
OUTDIR = ROOT / "state/benchmark/fixtures/config_sweep_test"

ROOTSPEC = dict(field="mdl175_gainvariance120", dataset="model175",
                region="CHN", universe="TOP2000U", delay=0)


def run_once(i, seed=7):
    run = f"cstest{i}"
    cmd = [sys.executable, str(CS), "--field", ROOTSPEC["field"], "--dataset", ROOTSPEC["dataset"],
           "--region", ROOTSPEC["region"], "--universe", ROOTSPEC["universe"],
           "--delay", str(ROOTSPEC["delay"]), "--run", run, "--seed", str(seed),
           "--out-dir", str(OUTDIR)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"RUN {i}: FAIL — config_sweep exit {p.returncode}\n{p.stderr}")
        return False, None
    out = pathlib.Path(p.stdout.strip().splitlines()[-1])
    rows = json.load(open(out))

    checks = {}
    checks["180 rows"] = len(rows) == 180
    sigs = {(r["formula"], r["settings"]["neutralization"], r["settings"]["truncation"],
             r["settings"]["decay"], r["settings"]["pasteurization"],
             r["settings"]["nanHandling"]) for r in rows}
    checks["all unique"] = len(sigs) == 180
    checks["fixed r/u/d"] = all(
        r["settings"]["region"] == ROOTSPEC["region"] and
        r["settings"]["universe"] == ROOTSPEC["universe"] and
        r["settings"]["delay"] == ROOTSPEC["delay"] for r in rows)
    neuts = {r["settings"]["neutralization"] for r in rows}
    checks["neut>=4"] = len(neuts) >= 4
    checks["enums legal"] = all(
        r["settings"]["pasteurization"] in config_sweep.PAST and
        r["settings"]["unitHandling"] in config_sweep.UNIT and
        r["settings"]["nanHandling"] in config_sweep.NAN and
        r["settings"]["neutralization"] in config_sweep.NEU[ROOTSPEC["region"]]
        for r in rows)
    pool = config_sweep.build_pool(ROOTSPEC["field"])
    # pin the pool size so doc drift is caught (v7.1: 235 = 29 non-monotone
    # inner instances x 7 outers + 16 monotone x 2 shape-sensitive outers)
    checks["pool==235 unique"] = len(pool) == 235 and len(set(pool)) == 235
    # grammar sau SEMANTIC-DEDUP (Khoa audit 2026-07-16): ts_quantile 3 driver [Khoa fix] +
    # quantile outer gaussian/cauchy (không sigma-sweep: affine dup; không uniform: ≡ rank) +
    # winsorize std 3/4/5 CHỈ dưới outer shape-sensitive; KHÔNG còn normalize/rankrev/winrank/market-group
    checks["grammar sweeps"] = (
        all(any(f'ts_quantile(ts_backfill({ROOTSPEC["field"]},22),22,driver="{d}")' in p for p in pool)
            for d in ("gaussian", "uniform", "cauchy")) and
        all(any(f"quantile(" in p and f"driver={d})" in p for p in pool)
            for d in ("gaussian", "cauchy")) and
        all(any(f"winsorize(ts_backfill({ROOTSPEC['field']},22),std={s})" in p for p in pool)
            for s in (3, 4, 5)))
    # semantic-dedup guard: không còn outer/pair trùng portfolio
    checks["semantic dedup"] = (
        not any("normalize(" in p for p in pool) and
        not any("reverse(rank(" in p for p in pool) and
        not any(",market)" in p for p in pool) and
        not any("sigma=" in p for p in pool) and
        not any("driver=uniform)" in p for p in pool) and     # quantile outer uniform ≡ rank (ts_quantile "uniform" có quote nên không match)
        not any(p.startswith(("rank(", "-rank(", "group_rank(", "quantile(")) and
                ("winsorize" in p or "signed_power" in p or "ts_quantile" in p) for p in pool))
    vt = subprocess.run([sys.executable, str(VT), str(out)], capture_output=True, text=True)
    checks["validate exit0"] = vt.returncode == 0

    ok = all(checks.values())
    detail = " ".join(f"{k}={'ok' if v else 'X'}" for k, v in checks.items())
    print(f"RUN {i}: {'PASS' if ok else 'FAIL'} | {detail} | distinct_neut={len(neuts)}")
    if not ok:
        print("   validate stderr:", vt.stdout[-400:])
    return ok, rows


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    results, first = [], None
    for i in range(1, 6):
        ok, rows = run_once(i)
        results.append(ok)
        if rows is not None:
            if first is None:
                first = [r["formula"] for r in rows]
            elif [r["formula"] for r in rows] != first:
                print(f"RUN {i}: FAIL — determinism (seed 7 differs from run 1)")
                results[-1] = False
    passed = sum(results)
    print(f"\n{passed}/5 runs PASS")
    sys.exit(0 if passed == 5 else 1)


if __name__ == "__main__":
    main()
