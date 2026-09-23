"""Offline backtest of the forge post-sim gates on the historical journal (design §11).

Questions answered, each with its number:
  1. How many historical rows would forge stage as `candidate` (platform PASS ∧ turnover band ∧
     DSR ≥ 0.95), with N = the row's own round size (meta.round / per-file pool) and V[SR] from
     that pool? Compared with the climb's tier counts.
  2. The ACTIVE book (platform-accepted alphas) that have a stored curve: how many pass the DSR
     gate at N = 300 (the round size they were selected from)? A gate that rejects most of what
     the platform accepted is mis-calibrated for the objective (count of submittable alphas).
  3. Degenerate books (CONCENTRATED_WEIGHT WARNING/FAIL): all rejected?
Runs on the VPS (needs state/pnl_curves and state/layered/runs).
"""
from __future__ import annotations

import collections
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import dsr as D, harvest as HV, score as SC  # noqa: E402


def main() -> int:
    rows = {}
    for p in glob.glob(str(ROOT / "state/layered/runs/*.jsonl")):
        for r in HV.read_jsonl(p):
            if r.get("alpha") and r.get("checks"):
                r["_file"] = pathlib.Path(p).name
                rows[r["alpha"]] = r
    print("journal rows with checks: %d" % len(rows))

    # pools: a climb row's round (cycle, round) within its file; else the file
    def pkey(r):
        # a climb row names its round but not always its cycle; the seed identifies the round file-wide
        m = r.get("meta") or {}
        return (r["_file"], m.get("cycle"), m.get("round"), m.get("seed"))
    sharpes = collections.defaultdict(list)
    for r in rows.values():
        if isinstance(r.get("sharpe"), (int, float)):
            sharpes[pkey(r)].append(float(r["sharpe"]))
    pools = {k: (len(v), D.var_sr_from_annual_sharpes(v)) for k, v in sharpes.items()}

    stages = collections.Counter()
    platform_pass = 0
    cand = []
    for a, r in rows.items():
        st = SC.stage(r)
        if st["stage"] == "needs-dsr":
            platform_pass += 1
            curve = HV.cached_curve(a)
            if curve is None:
                stages["needs-dsr(no curve)"] += 1
                continue
            n, var = pools.get(pkey(r), (1, 0.0))
            out = D.evaluate(curve, n_trials=n, var_sr=var)
            st = SC.stage(r, out)
            if st["stage"] == "candidate":
                cand.append((a, r.get("sharpe"), out["dsr"], n, out["sr0_annual"], r["_file"]))
        stages[st["stage"]] += 1
    print("Q1 stages:", dict(stages.most_common()))
    print("   platform-pass ∧ turnover band: %d; forge candidates (DSR≥0.95): %d" % (platform_pass, len(cand)))
    by_file = collections.Counter(c[5] for c in cand)
    print("   candidates by journal file:", dict(by_file.most_common(6)))

    # curve coverage: which journal rows even have a stored curve, and at what stage
    curve_ids = {pathlib.Path(q).stem for q in glob.glob(str(ROOT / "state/pnl_curves/*.json"))}
    in_rows = [a for a in curve_ids if a in rows]
    cov = collections.Counter(SC.stage(rows[a])["stage"] for a in in_rows)
    print("curve coverage: %d curves on disk, %d belong to a journal row with checks; their stages: %s"
          % (len(curve_ids), len(in_rows), dict(cov.most_common(6))))
    if "--fetch" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--fetch") + 1])
        sys.path.insert(0, str(ROOT / "tools"))
        import layered_sim as LS, self_corr_predict as SP
        s = LS.session(); LS.keep_jar_fresh(s)
        todo = [a for a, r in rows.items() if SC.stage(r)["stage"] == "needs-dsr" and HV.cached_curve(a) is None][:limit]
        got = 0
        for i, a in enumerate(todo):
            if SP.pnl(s, a, budget=25):
                got += 1
            if (i + 1) % 25 == 0:
                print("  fetched %d/%d (%d with a curve)" % (i + 1, len(todo), got), flush=True)
        print("fetched curves for %d of %d platform-pass rows" % (got, len(todo)))
        return 0

    book = json.load(open(ROOT / "fetched/rc/active_book.json"))
    ids = [b["id"] for b in book]
    var300 = None
    all_sr = [float(r["sharpe"]) for r in rows.values() if isinstance(r.get("sharpe"), (int, float))]
    var_all = D.var_sr_from_annual_sharpes(all_sr)
    passed = tested = 0
    fails = []
    for aid in ids:
        curve = HV.cached_curve(aid)
        if curve is None:
            continue
        tested += 1
        out = D.evaluate(curve, n_trials=300, var_sr=var_all)
        if out.get("ok") and out["dsr"] >= SC.DSR_MIN:
            passed += 1
        else:
            fails.append((aid, round(out.get("sharpe_annual", 0), 2), round(out.get("dsr", 0), 3)))
    print("Q2 ACTIVE book with a curve: %d; DSR≥0.95 at N=300 (sd of Sharpe across all rows %.2f annual): %d pass, %d fail"
          % (tested, D.ANNUALISE * var_all ** 0.5, passed, tested - passed))
    print("   failing ACTIVE alphas (id, sharpe, dsr):", fails[:12])

    degenerate = [r for r in rows.values() if any(isinstance(c, dict) and c.get("name") == "CONCENTRATED_WEIGHT"
                                                  and c.get("result") in ("WARNING", "FAIL") for c in r["checks"])]
    rejected = sum(1 for r in degenerate if SC.platform_verdict(r)[0] == "fail")
    print("Q3 degenerate books (CONCENTRATED_WEIGHT adverse): %d, rejected by forge: %d" % (len(degenerate), rejected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
