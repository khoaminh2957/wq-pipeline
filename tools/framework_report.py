"""Score each framework against the prediction it registered BEFORE the batch.

This file exists to make a framework refutable. `BACKBONE.md` was not: it stated eight rules and
named no observation that would have shown any of them wrong, and adversarial review then killed
five -- four of which turned out to be this project's own generator configuration measured back out
of its own corpus.

THREE REFUSALS, and they are not negotiable per run:

  * fewer than MIN_ROWS judgeable rows in an arm            -> NO VERDICT for that arm
  * a comparison where either side is under MIN_ROWS        -> NO VERDICT, no number printed
  * Mann-Whitney is reported as a test of DOMINANCE, never of means. On skewed payoffs a rank test
    read as a mean test passes for every random control -- this project has the scar.

Absolute predictions ("zero alphas above 0.5") are judged on their own arm and survive the
framework/neutralization confound. Comparative predictions ("beats flat") do not, and every one is
printed with its confound named on the line above it.
"""

import argparse
import collections
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import frameworks as FW  # noqa: E402

RUNDIR = ROOT / "state/layered/runs"

#: Below this an arm gets NO VERDICT. Inherited from `layered_report.py`, which set it after a round
#: reported a "result" off 3 rows per arm.
MIN_ROWS = 20

#: The screen every gem must clear. Not a submission gate -- the cheap filter that says an alpha is
#: worth measuring correlation on.
SCREEN = {"sharpe": 1.58, "fitness": 1.0, "turnover": (0.01, 0.7)}


def load(paths):
    """Terminal framework rows. A row without a `framework` in its meta belongs to the 2^6
    factorial experiment and is NOT mixed in -- the two metas are deliberately distinct shapes."""
    rows = []
    for p in paths:
        for line in pathlib.Path(p).read_text(errors="ignore").splitlines():
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            fw = (r.get("meta") or {}).get("framework")
            if fw and fw in FW.BY_NAME:
                rows.append(r)
    return rows


def _num(r, key):
    v = r.get(key)
    return v if isinstance(v, (int, float)) else None


def _checks(r):
    """`checks` carries THREE shapes across this project's journals, including 614 rows that list
    the checks which PASSED -- inverted polarity, at the HEAD of the file. Only the dict-of-records
    shape is read here; anything else returns empty and the row is counted as unjudgeable rather
    than silently scored as a pass."""
    c = r.get("checks")
    if not isinstance(c, list):
        return {}
    out = {}
    for item in c:
        if isinstance(item, dict) and item.get("name"):
            out[item["name"]] = item
    return out


def _screened(r):
    s, f, t = _num(r, "sharpe"), _num(r, "fitness"), _num(r, "turnover")
    if None in (s, f, t):
        return None
    lo, hi = SCREEN["turnover"]
    return s > SCREEN["sharpe"] and f > SCREEN["fitness"] and lo < t < hi


def _zero_fail(r):
    """True only when every scored check PASSes. A row whose checks are missing or in the bare-name
    shape returns None and is excluded, never counted as a pass -- `gates.zero_fail` once returned
    a truthy 3-tuple and produced a '100%' that was an artifact of Python truthiness."""
    ch = _checks(r)
    if not ch:
        return None
    res = [v.get("result") for v in ch.values()]
    if not any(x == "PASS" for x in res):
        return None
    return all(x in ("PASS", "PENDING") for x in res)


#: A ratio whose denominator is the alpha's own sharpe is 0/0 noise when that sharpe is near zero.
#: The first framework batch made the point at full volume: at no threshold the ordering was
#: subu 0.84 > margin 0.75 > ... > era_a 0.31, and by |sharpe| > 0.5 it was margin 0.78 > s6_pos
#: 0.74 > flat 0.72 > era_a 0.70 > ... > subu 0.59 -- `subu` fell from first to sixth and era_a rose
#: from ninth to fourth. The apparent spread was entirely division by numbers near zero.
SUBU_MIN_ABS_SHARPE = 0.5


def _subu_ratio(r, min_abs_sharpe=SUBU_MIN_ABS_SHARPE):
    """Sub-universe sharpe divided by the alpha's own sharpe, or None when the denominator is too
    small for the quotient to mean anything.

    S3: the gate's limit is `k * the alpha's own sharpe`, so raising sharpe raises the bar by the
    same factor and the gate cannot be bought with signal strength. What has to move is THIS ratio,
    and no run in this repository has ever recorded it as an outcome."""
    ch = _checks(r).get("LOW_SUB_UNIVERSE_SHARPE")
    s = _num(r, "sharpe")
    if not ch or s is None or abs(s) < min_abs_sharpe:
        return None
    v = ch.get("value")
    if not isinstance(v, (int, float)):
        return None
    return v / s


def _med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _rate(vals):
    vals = [v for v in vals if v is not None]
    return (sum(1 for v in vals if v) / len(vals), len(vals)) if vals else (None, 0)


def _fmt(v, nd=3):
    return "--" if v is None else ("%.*f" % (nd, v))


def summarise(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["meta"]["framework"]].append(r)
    out = {}
    for name, rs in by.items():
        cw = [_checks(r).get("CONCENTRATED_WEIGHT") for r in rs]
        cw_vals = [c.get("value") for c in cw if c and isinstance(c.get("value"), (int, float))]
        zf, zf_n = _rate([_zero_fail(r) for r in rs])
        sc, sc_n = _rate([_screened(r) for r in rs])
        out[name] = {
            "n": len(rs),
            "n_terminal": sum(1 for r in rs if _num(r, "sharpe") is not None),
            "sharpe": _med([_num(r, "sharpe") for r in rs]),
            "fitness": _med([_num(r, "fitness") for r in rs]),
            "turnover": _med([_num(r, "turnover") for r in rs]),
            "margin": _med([_num(r, "margin") for r in rs]),
            "cw_max": max(cw_vals) if cw_vals else None,
            "cw_n": len(cw_vals),
            "cw_fail": _rate([c.get("result") == "FAIL" for c in cw if c])[0],
            "zero_fail": zf, "zero_fail_n": zf_n,
            "screen": sc, "screen_n": sc_n,
            "subu_ratio": _med([_subu_ratio(r) for r in rs]),
            "subu_n": sum(1 for r in rs if _subu_ratio(r) is not None),
        }
    return out


def verdicts(stats):
    """One line per prediction. Every comparative line names its confound first."""
    lines = []

    def underpowered(*names):
        thin = [n for n in names if stats.get(n, {}).get("n_terminal", 0) < MIN_ROWS]
        return thin

    # ---- S1. ABSOLUTE, and it survives the framework/neutralization confound: the deductive claim
    # is that a neutralized group holding one name is zeroed, so the book floor is two names and the
    # max share is 0.5. One alpha above 0.5001 refutes it outright, at any n.
    s1 = stats.get("s1_neut")
    if s1 and s1["cw_n"]:
        ok = s1["cw_max"] is not None and s1["cw_max"] <= 0.5001
        lines.append("S1  %-9s CONCENTRATED_WEIGHT max %s over %d scored rows -> %s"
                     % ("s1_neut", _fmt(s1["cw_max"], 4), s1["cw_n"],
                        "UPHELD (cap holds)" if ok else "REFUTED -- a neutralized alpha exceeded 0.5"))
    else:
        lines.append("S1  NO VERDICT -- CONCENTRATED_WEIGHT was not scored on any s1_neut row")

    # ---- S6. The paired arms ARE the experiment the corpus could not run: exactly 6 matched
    # sign-flip groups exist in 50,482 multi-leg rows and none has a 0-negation arm.
    thin = underpowered("s6_neg", "s6_pos")
    if thin:
        lines.append("S6  NO VERDICT -- under %d terminal rows in %s" % (MIN_ROWS, ", ".join(thin)))
    else:
        a, b = stats["s6_neg"], stats["s6_pos"]
        lines.append("S6  CONFOUND: none by construction -- the arms differ only in the minus on "
                     "the carrier leg.")
        lines.append("S6  zero-fail neg %s (n=%d) vs pos %s (n=%d); median sharpe %s vs %s"
                     % (_fmt(a["zero_fail"]), a["zero_fail_n"], _fmt(b["zero_fail"]),
                        b["zero_fail_n"], _fmt(a["sharpe"]), _fmt(b["sharpe"])))

    # ---- S2 is an IDENTITY and a batch cannot refute it. What a batch CAN refute is the belief
    # that a framework can steer margin at all.
    m, fl = stats.get("margin"), stats.get("flat")
    if not m or not fl or underpowered("margin", "flat"):
        lines.append("S2  NO VERDICT -- under %d terminal rows in margin or flat" % MIN_ROWS)
    else:
        lines.append("S2  CONFOUND: `margin` declares BOTH decay %d (vs %d everywhere else) AND a "
                     "shallower chain (depth 1-3), so the two move together."
                     % (FW.DECAY_LARGE, FW.DECAY_SMALL))
        lines.append("S2  margin %s vs flat %s | sharpe %s vs %s | fitness %s vs %s"
                     % (_fmt(m["margin"], 5), _fmt(fl["margin"], 5), _fmt(m["sharpe"]),
                        _fmt(fl["sharpe"]), _fmt(m["fitness"]), _fmt(fl["fitness"])))
        # E1 measured decay sliding ALONG `sharpe*sqrt(margin)=const` -- margin 10.82->9.07 bps as
        # sharpe rose, fitness pass rate 0.451 vs 0.453. This line is the direct check of that.
        iso = [k for k in ("margin", "flat")
               if stats[k]["sharpe"] and stats[k]["margin"]]
        if len(iso) == 2:
            prod = {k: stats[k]["sharpe"] * (stats[k]["margin"] ** 0.5) for k in iso}
            lines.append("S2  iso-fitness product sharpe*sqrt(margin): margin %s vs flat %s -- "
                         "E1 says these should MATCH (decay slides along the curve); a real gap "
                         "means decay moves the product and E1's decomposition is wrong"
                         % (_fmt(prod["margin"], 4), _fmt(prod["flat"], 4)))

    # ---- S3, the binding constraint. The ratio is the deliverable whether or not the guess holds.
    ratios = {k: v for k, v in stats.items() if v["subu_n"] >= MIN_ROWS}
    if not ratios:
        lines.append("S3  NO VERDICT -- LOW_SUB_UNIVERSE_SHARPE scored on under %d rows in every "
                     "arm. This is the FIRST measurement of this ratio in the repository; if it "
                     "stays unscored, nothing here can attack the binding constraint." % MIN_ROWS)
    else:
        lines.append("S3  CONFOUND: `subu` declares SUBINDUSTRY neutralization, so framework and "
                     "setting are not separable in this batch.")
        lines.append("S3  sub-universe/full sharpe ratio: " + "  ".join(
            "%s %s(n=%d)" % (k, _fmt(v["subu_ratio"]), v["subu_n"])
            for k, v in sorted(ratios.items(), key=lambda kv: -(kv[1]["subu_ratio"] or 0))))

    # ---- the null arm. If nothing beats flat, that is the finding.
    if fl and not underpowered("flat"):
        # `(v["sharpe"] or -9)` was the first version and it is WRONG: a median sharpe of exactly
        # 0.0 is falsy in Python, so every arm sitting at 0.000 -- which was most of them in the
        # first batch -- silently became -9 and the line reported five frameworks "above" a flat
        # that was itself scored as -9. Compare with an explicit None check.
        fs = fl["sharpe"]
        better = [k for k, v in stats.items()
                  if k != "flat" and v["n_terminal"] >= MIN_ROWS
                  and v["sharpe"] is not None and fs is not None and v["sharpe"] > fs]
        lines.append("NULL flat median sharpe %s; frameworks above it: %s"
                     % (_fmt(fs), ", ".join(sorted(better)) or "NONE -- structure did not move "
                        "the median at this sample size"))
        # A median comparison is meaningless when every arm sits at zero. Report the tail too.
        tails = {k: v for k, v in stats.items() if v["n_terminal"] >= MIN_ROWS}
        if tails and all(abs(v["sharpe"] or 0) < 0.05 for v in tails.values()):
            lines.append("NULL WARNING: every arm's median sharpe is within 0.05 of zero, so the "
                         "median comparison above has no power. Judge on the tail and on "
                         "degenerate-book rate instead.")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help="journals; default every fw_*.jsonl")
    a = ap.parse_args()
    paths = a.paths or sorted(RUNDIR.glob("fw_*.jsonl"))
    if not paths:
        print("no framework journals found under %s" % RUNDIR)
        return 1
    rows = load(paths)
    print("%d framework rows from %d journal(s)" % (len(rows), len(paths)))
    if not rows:
        return 1
    stats = summarise(rows)

    hdr = ("%-9s %5s %5s %8s %8s %8s %9s %8s %8s %8s"
           % ("fw", "n", "term", "sharpe", "fitness", "turnov", "margin", "zerofail", "screen",
              "subuRat"))
    print(hdr)
    print("-" * len(hdr))
    for name in sorted(stats):
        v = stats[name]
        print("%-9s %5d %5d %8s %8s %8s %9s %8s %8s %8s"
              % (name, v["n"], v["n_terminal"], _fmt(v["sharpe"]), _fmt(v["fitness"]),
                 _fmt(v["turnover"]), _fmt(v["margin"], 5), _fmt(v["zero_fail"]),
                 _fmt(v["screen"]), _fmt(v["subu_ratio"])))
    print()
    for line in verdicts(stats):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
