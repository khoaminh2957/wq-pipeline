"""Canary report: what one forge round produced, read straight from the journal (no network).

  python forge/offline/canary_report.py [--seed SEED]
Prints: statuses, error messages, UNITS rate, platform-pass and turnover-band counts, per-hypothesis
and per-cell Sharpe distributions, and the Sharpe spread of every (hypothesis, cell) pool — the
number that decides how hard the DSR gate bites (SR0 = pool sd × 2.90 at N = 300).
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import dsr as D, harvest as HV, score as SC  # noqa: E402


def q(xs, p):
    xs = sorted(xs)
    return xs[int((len(xs) - 1) * p)] if xs else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--journal", default=str(HV.JOURNAL))
    a = ap.parse_args()
    rows = HV.read_jsonl(a.journal)
    if a.seed is not None:
        rows = [r for r in rows if (r.get("meta") or {}).get("seed") == a.seed]
    kids = [r for r in rows if (r.get("meta") or {}).get("forge") and r.get("status") not in (None, "PARENT-POSTED")]
    print("rows %d | children %d | statuses %s" % (len(rows), len(kids), dict(collections.Counter(r.get("status") for r in kids))))
    msgs = collections.Counter((r.get("message") or "")[:90] for r in kids if r.get("status") not in ("COMPLETE", "WARNING"))
    for m, n in msgs.most_common(6):
        print("   %3d × %s" % (n, m))
    landed = [r for r in kids if r.get("alpha")]
    if not landed:
        print("no alphas landed yet")
        return 0
    units = sum(1 for r in landed if any(isinstance(c, dict) and c.get("name") == "UNITS" and c.get("result") == "FAIL"
                                         for c in r.get("checks") or []))
    stages = collections.Counter(SC.stage(r)["stage"] for r in landed)
    print("landed %d | UNITS fail %d (%.1f%%) | stages %s" % (len(landed), units, 100.0 * units / len(landed), dict(stages)))
    sh = [r["sharpe"] for r in landed if isinstance(r.get("sharpe"), (int, float))]
    tv = [r["turnover"] for r in landed if isinstance(r.get("turnover"), (int, float))]
    print("sharpe p10 %.2f p50 %.2f p90 %.2f max %.2f | turnover p10 %.3f p50 %.3f p90 %.3f | >=1.58: %d | fitness>=1: %d" % (
        q(sh, .1), q(sh, .5), q(sh, .9), max(sh), q(tv, .1), q(tv, .5), q(tv, .9), sum(1 for s in sh if s >= 1.58),
        sum(1 for r in landed if isinstance(r.get("fitness"), (int, float)) and r["fitness"] >= 1.0)))
    fails = collections.Counter()
    for r in landed:
        for name in SC.platform_verdict(r)[1]:
            fails[name] += 1
    print("failing checks (rows):", dict(fails.most_common(8)))
    print("--- per (hypothesis, cell): n, sharpe p50/max, |sharpe| max, pool sd annual → SR0@N=300")
    by = collections.defaultdict(list)
    for r in landed:
        m = r.get("meta") or {}
        st = r.get("settings") or {}
        by[(m.get("hypothesis"), "%s/d%s" % (st.get("region"), st.get("delay")), m.get("category"))].append(r)
    for key, rs in sorted(by.items(), key=lambda t: -max((x.get("sharpe") or 0) for x in t[1])):
        s = [x["sharpe"] for x in rs if isinstance(x.get("sharpe"), (int, float))]
        if not s:
            continue
        var = D.var_sr_from_annual_sharpes(s)
        sd = D.ANNUALISE * var ** 0.5
        print("   %-38s %-9s %-13s n %3d  p50 %5.2f  max %5.2f  |max| %5.2f  sd %.2f → SR0 %.2f" % (
            key[0], key[1], key[2], len(s), statistics.median(s), max(s), max(abs(v) for v in s), sd,
            D.ANNUALISE * D.expected_max_sharpe(var, 300)))
    best = sorted(landed, key=lambda r: -(r.get("sharpe") or -9))[:5]
    print("--- top 5 by sharpe")
    for r in best:
        st = SC.stage(r)
        print("   %s sharpe %.2f fit %.2f tvr %.3f %s %s | %s" % (r["alpha"], r["sharpe"], r.get("fitness") or 0, r.get("turnover") or 0,
                                                             st["stage"], st["failed"], (r.get("formula") or "")[:90]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
