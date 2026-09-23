#!/usr/bin/env python3
"""Regression tests for corr_rank.py — the offline SELF-correlation ranker.

The thing this file most needs to protect is not the arithmetic, it is the LABEL. corr_rank is a
ranker whose "clean" calls are wrong 8.0% of the time, and the one way it does real damage is by
being read as a gate. So the banner test below is a contract test, not a cosmetic one.

    python3 tools/funnel/test_corr_rank.py
"""
import json
import math
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import corr_rank as CR

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        FAILS.append(f"{name}  {detail}")
        print(f"  FAIL {name}  {detail}")


DATES = [f"2020-01-{d:02d}" for d in range(1, 21)]


def curve(daily):
    """Cumulative curve over DATES from a list of 19 daily deltas."""
    out, tot = {}, 0.0
    out[DATES[0]] = 0.0
    for i, x in enumerate(daily, 1):
        tot += x
        out[DATES[i]] = tot
    return out


UP = [1.0, -2.0, 3.0, -1.0, 0.5, 2.0, -3.0, 1.5, -0.5, 4.0,
      -2.5, 1.0, 0.0, -1.0, 2.0, -4.0, 3.0, 1.0, -2.0]
DOWN = [-x for x in UP]
OTHER = [3.0, 1.0, -1.0, 0.5, -2.0, -0.5, 1.0, 2.5, 0.0, -3.0,
         1.5, -1.0, 2.0, 0.5, -0.5, 1.0, -2.0, 0.0, 3.0]


def with_curves(mapping, fn):
    """Run fn() with corr_rank.load_curve served from an in-memory mapping."""
    orig = CR.load_curve
    CR.load_curve = lambda aid: mapping.get(aid)
    try:
        return fn()
    finally:
        CR.load_curve = orig


def main():
    print("corr_rank")

    # --- predict: an identical curve is correlation 1.0, and a book alpha is not its own neighbour
    m = {"cand": curve(UP), "bookA": curve(UP), "bookB": curve(OTHER)}
    grid = DATES
    got = with_curves(m, lambda: CR.predict(["cand"], ["bookA", "bookB"], grid))
    check("identical curve -> 1.0", abs(got["cand"][0] - 1.0) < 1e-9, got["cand"])
    check("nearest book id reported", got["cand"][1] == "bookA", got["cand"])

    got = with_curves(m, lambda: CR.predict(["bookA"], ["bookA", "bookB"], grid))
    check("self excluded from own book", got["bookA"][1] == "bookB", got["bookA"])

    # --- a mirrored curve is -1.0, and the ranker takes the MAX (signed), matching the platform's
    #     max-of-the-correlation-column, so an anti-correlated book alpha must NOT read as a match.
    m2 = {"cand": curve(UP), "bookA": curve(DOWN), "bookB": curve(OTHER)}
    got = with_curves(m2, lambda: CR.predict(["cand"], ["bookA", "bookB"], grid))
    check("mirror image is not the max", got["cand"][1] == "bookB", got["cand"])
    check("mirror image scores -1 against bookA",
          abs(got["cand"][0]) < 1.0, got["cand"])

    # --- the number is a Pearson of DAILY pnl, not of the cumulative curve. Two curves that share
    #     a big common trend but have unrelated day-to-day moves correlate ~1.0 cumulatively and
    #     near 0 daily; getting this backwards is the whole difference between signal and level.
    trend = [10.0] * 19
    m3 = {"cand": curve([u + t for u, t in zip(UP, trend)]),
          "bookA": curve([o + t for o, t in zip(OTHER, trend)])}
    got = with_curves(m3, lambda: CR.predict(["cand"], ["bookA"], grid))
    cum_c = [m3["cand"][d] for d in grid]
    cum_b = [m3["bookA"][d] for d in grid]
    mc, mb = sum(cum_c) / len(cum_c), sum(cum_b) / len(cum_b)
    sc = math.sqrt(sum((x - mc) ** 2 for x in cum_c))
    sb = math.sqrt(sum((x - mb) ** 2 for x in cum_b))
    cum_r = sum((x - mc) * (y - mb) for x, y in zip(cum_c, cum_b)) / (sc * sb)
    check("differences the curve (daily << cumulative)",
          got["cand"][0] < 0.5 < cum_r, f"daily={got['cand'][0]:.3f} cumulative={cum_r:.3f}")

    # --- a candidate whose curve does not span the grid is DROPPED, never scored on a short window
    short = dict(list(curve(UP).items())[:5])
    m4 = {"cand": short, "bookA": curve(OTHER)}
    got = with_curves(m4, lambda: CR.predict(["cand"], ["bookA"], grid))
    check("short curve dropped, not scored", "cand" not in got, got)

    # --- a flat (zero-variance) curve has no correlation to anything; it must drop, not divide by 0
    m5 = {"cand": curve([0.0] * 19), "bookA": curve(OTHER)}
    got = with_curves(m5, lambda: CR.predict(["cand"], ["bookA"], grid))
    check("flat curve dropped", "cand" not in got, got)

    # --- date_grid keeps the LAST days+1 dates common to >=90% of the book
    g = CR.date_grid({"a": curve(UP), "b": curve(OTHER)}, days=4)
    check("date_grid length days+1", len(g) == 5, len(g))
    check("date_grid takes the tail", g[-1] == DATES[-1], g)

    # --- load_curve reads BOTH on-disk formats: fetched/pnl jsonl rows and state/pnl_curves dicts
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "fetched/pnl").mkdir(parents=True)
        (root / "state/pnl_curves").mkdir(parents=True)
        with open(root / "fetched/pnl/AAA.jsonl", "w") as f:
            f.write('["2020-01-01", 0.0]\n["2020-01-02", 5.0]\n')
        json.dump({"2020-01-01": 0.0, "2020-01-02": 7.0},
                  open(root / "state/pnl_curves/BBB.json", "w"))
        orig = CR.ROOT
        CR.ROOT = root
        try:
            a, b, c = CR.load_curve("AAA"), CR.load_curve("BBB"), CR.load_curve("CCC")
        finally:
            CR.ROOT = orig
        check("jsonl curve read", a == {"2020-01-01": 0.0, "2020-01-02": 5.0}, a)
        check("json curve read", b == {"2020-01-01": 0.0, "2020-01-02": 7.0}, b)
        check("missing curve is None", c is None, c)

    # --- CONTRACT: the honest-error rate must survive in the code, the banner and the output.
    check("DANGER_RATE is the measured 8.0%", abs(CR.DANGER_RATE - 0.080) < 1e-9, CR.DANGER_RATE)
    check("banner says NOT A GATE", "NOT A GATE" in CR.BANNER, CR.BANNER[:40])
    check("banner states the danger rate", "8.0%" in CR.BANNER, CR.BANNER[:80])
    check("banner names prod as the binding half", "prod" in CR.BANNER.lower(), "")
    check("banner says prod has no surrogate", "NO offline surrogate" in CR.BANNER, "")
    check("docstring flags it as a ranker not a gate",
          "IT IS NOT A GATE" in CR.__doc__, "")
    check("gate limit is 0.70 not 0.71", CR.GATE == 0.70, CR.GATE)
    src = pathlib.Path(CR.__file__).read_text()
    check("--out rows carry the not-a-gate flag", "IS_A_RANK_NOT_A_GATE" in src, "")
    check("--out rows carry the danger rate", '"dangerous_clean_rate": DANGER_RATE' in src, "")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED")
        for f in FAILS:
            print("   ", f)
        return 1
    print("all pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
