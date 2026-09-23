"""Offline check of forge.dsr on every stored cumulative-PnL curve (state/pnl_curves/*.json).

Writes state/forge/dsr_curves.jsonl (one row per curve) and prints a summary. Second-way check:
the Sharpe recomputed from daily PnL differences is compared with the platform's own `is.sharpe`
for ACTIVE-book alphas that have a curve — if they disagree the curve is not what we think it is.
Usage: python forge/offline/dsr_curves.py [--n-trials 300]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import dsr  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-trials", type=int, default=300)
    ap.add_argument("--curves", default=str(ROOT / "state/pnl_curves"))
    ap.add_argument("--book", default=str(ROOT / "fetched/rc/active_book.json"))
    ap.add_argument("--out", default=str(ROOT / "state/forge/dsr_curves.jsonl"))
    a = ap.parse_args()

    rows = []
    for path in sorted(glob.glob(os.path.join(a.curves, "*.json"))):
        try:
            curve = json.load(open(path))
        except Exception:
            continue
        rets = dsr.daily_returns_from_curve(curve)
        if len(rets) < 250:
            continue
        mean, sd, skew, kurt = dsr.moments(rets)
        if sd <= 0:
            continue
        rows.append({"alpha": pathlib.Path(path).stem, "T": len(rets), "sr_daily": mean / sd,
                     "sharpe_annual": mean / sd * dsr.ANNUALISE, "skew": skew, "kurt": kurt})
    if not rows:
        print("no curves"); return 1

    # V[SR] across the whole stored population (per-period), then SR0 at N trials.
    var_sr = statistics.variance(r["sr_daily"] for r in rows)
    sr0 = dsr.expected_max_sharpe(var_sr, a.n_trials)
    for r in rows:
        r["sr0_daily"] = sr0
        r["dsr"] = dsr.probabilistic_sharpe(r["sr_daily"], sr0, r["T"], r["skew"], r["kurt"])
        r["dsr_alone"] = dsr.probabilistic_sharpe(r["sr_daily"], 0.0, r["T"], r["skew"], r["kurt"])
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    med = lambda k: statistics.median(r[k] for r in rows)  # noqa: E731
    t_med = int(med("T")); k_med = med("kurt"); s_med = med("skew")
    # pass line: smallest daily SR with DSR >= 0.95 at the median T/skew/kurt (two fixed-point steps)
    sr = sr0
    for _ in range(4):
        denom = 1 - s_med * sr + (k_med - 1) / 4 * sr * sr
        sr = sr0 + 1.6449 * math.sqrt(denom) / math.sqrt(t_med - 1)
    print("curves scored: %d   T median %d" % (len(rows), t_med))
    print("skew median %.2f   kurtosis median %.2f (normal = 3)" % (s_med, k_med))
    print("sd of annual Sharpe across curves: %.3f" % (math.sqrt(var_sr) * dsr.ANNUALISE))
    print("luck ceiling SR0 at N=%d: %.3f annual" % (a.n_trials, sr0 * dsr.ANNUALISE))
    print("pass line (DSR>=0.95 at median moments): annual Sharpe %.3f" % (sr * dsr.ANNUALISE))
    print("DSR>=0.95 at N=%d: %d / %d   (alone, N=1: %d)" % (
        a.n_trials, sum(r["dsr"] >= 0.95 for r in rows), len(rows), sum(r["dsr_alone"] >= 0.95 for r in rows)))

    # second-way check against the platform's own Sharpe
    try:
        book = {b["id"]: (b.get("is") or {}).get("sharpe") for b in json.load(open(a.book))}
    except Exception as e:  # noqa: BLE001
        print("book unavailable:", e); return 0
    pairs = [(r["alpha"], r["sharpe_annual"], book[r["alpha"]]) for r in rows
             if r["alpha"] in book and book[r["alpha"]] is not None]
    if pairs:
        diffs = sorted(abs(c - p) for _, c, p in pairs)
        rel = sorted(abs(c - p) / abs(p) for _, c, p in pairs if p)
        print("platform-vs-curve Sharpe on %d ACTIVE alphas: median |diff| %.3f, p90 %.3f; median rel %.1f%%" % (
            len(pairs), diffs[len(diffs) // 2], diffs[int(len(diffs) * 0.9)], 100 * rel[len(rel) // 2]))
        for aid, c, p in pairs[:4]:
            print("   %s curve %.3f platform %.3f" % (aid, c, p))
    else:
        print("no ACTIVE alpha has a stored curve — platform-vs-curve check impossible here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
