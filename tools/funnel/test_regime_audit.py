#!/usr/bin/env python3
"""5x regression test for regime_audit.py — API-free, deterministic.

Fixture: one SAVED recordset dir (state/benchmark/fixtures/regime_audit/
GrL5AJ7Q, copied from fetched/recordsets/) + its golden. GrL5AJ7Q is a true
boom-dependent alpha: best-2y (2015-16) carries 57.7% of PnL and ex-boom
sharpe is 0.892, so BOTH S8.4 flags must fire. Plus structural invariants
(worst_half == min of halves, pct_pos in [0,1], flag consistency, ex-boom
excludes exactly the best2y years).
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import regime_audit as RA

FIX_DIR = ROOT / "state/benchmark/fixtures/regime_audit"
GOLDEN = json.load(open(FIX_DIR / "golden_GrL5AJ7Q.json"))


def check_once():
    problems = []
    got = RA.regime_audit("GrL5AJ7Q", FIX_DIR)

    # 1. golden equality (every S8.4 output field)
    for k, v in GOLDEN.items():
        if got.get(k) != v:
            problems.append(f"golden.{k}: got {got.get(k)!r} want {v!r}")

    # 2. structural invariants (not golden-tautological)
    halves = [h for h in got["half_sharpes"] if h is not None]
    if halves and got["worst_half"] != min(halves):
        problems.append("worst_half != min(half_sharpes)")
    if not (0.0 <= got["pct_pos"] <= 1.0):
        problems.append(f"pct_pos out of [0,1]: {got['pct_pos']}")
    if len(got["yearly_sharpes"]) != 10:
        problems.append("yearly_sharpes must carry all 10 IS years")
    if got["best2y"] != ["2015", "2016"]:
        problems.append(f"best2y misidentified: {got['best2y']}")
    # flag consistency with the computed numbers
    want_flag1 = got["best2y_pnl_share"] is not None and got["best2y_pnl_share"] > 0.5
    want_flag2 = got["ex_best2y_sharpe"] is not None and got["ex_best2y_sharpe"] < 1.0
    if ("BEST_2Y_GT_50PCT_PNL" in got["flags"]) != want_flag1:
        problems.append("BEST_2Y flag inconsistent with best2y_pnl_share")
    if ("EX_BOOM_SHARPE_LT_1" in got["flags"]) != want_flag2:
        problems.append("EX_BOOM flag inconsistent with ex_best2y_sharpe")
    # this fixture is the boom-dependent case: both flags MUST fire
    if set(got["flags"]) != {"BEST_2Y_GT_50PCT_PNL", "EX_BOOM_SHARPE_LT_1"}:
        problems.append(f"boom-dependent fixture must raise both flags: {got['flags']}")

    return (not problems), "; ".join(problems), got


def main():
    outputs, passed = [], 0
    for i in range(1, 6):
        ok, detail, got = check_once()
        snap = json.dumps(got, sort_keys=True)
        outputs.append(snap)
        if ok and snap == outputs[0]:
            passed += 1
            print(f"run {i}: PASS")
        else:
            print(f"run {i}: FAIL — {detail}"
                  + ("" if snap == outputs[0] else " [non-deterministic]"))
    print(f"{passed}/5 runs passed")
    sys.exit(0 if passed == 5 else 1)


if __name__ == "__main__":
    main()
