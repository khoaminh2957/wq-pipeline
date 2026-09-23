#!/usr/bin/env python3
"""regime_audit.py — S8.4 mandatory pre-submit regime audit (S10-27 port).

Pure LOCAL arithmetic over fetched/recordsets/<sid>/{yearly-stats,daily-pnl}.json
(the exact files the md names). NO WQ API calls. Sits on the SUBMIT path: run it
on every submit candidate BEFORE presenting to Khoa; a flagged alpha needs an
all-weather diversifier pairing or a rethink, never an auto-pass.

Computes (v6.2 S8.4 list, verbatim):
  yearly_sharpes    {year: sharpe} from yearly-stats (IS rows)
  half_sharpes      [h1, h2] annualized sharpe of each half of the daily pnl
                    (mean/std * sqrt(252); book size cancels)
  worst_half        min(half_sharpes)
  pct_pos           share of days with pnl > 0
  best2y            best CONSECUTIVE 2-year window by summed yearly pnl
  best2y_pnl_share  best2y pnl / total pnl (None if total <= 0)
  ex_best2y_sharpe  annualized sharpe of the daily pnl EXCLUDING best2y years
  flags             BEST_2Y_GT_50PCT_PNL   if best2y_pnl_share > 0.5
                    EX_BOOM_SHARPE_LT_1    if ex_best2y_sharpe < 1.0

Usage:
    python3 tools/funnel/regime_audit.py <sid> [recordsets_dir]
    regime_audit(sid, recordsets_dir) -> dict
"""
from __future__ import annotations
import json
import math
import pathlib
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "fetched" / "recordsets"
ANN = math.sqrt(252.0)


def _records(path):
    j = json.load(open(path))
    cols = [p["name"] for p in j["schema"]["properties"]]
    return [dict(zip(cols, row)) for row in j["records"]]


def _sharpe(pnls):
    """Annualized sharpe of a daily pnl series (book size cancels)."""
    if len(pnls) < 2:
        return None
    mu = st.mean(pnls)
    sd = st.stdev(pnls)
    if sd == 0:
        return None
    return round(mu / sd * ANN, 4)


def regime_audit(sid, recordsets_dir=None):
    d = pathlib.Path(recordsets_dir) if recordsets_dir else DEFAULT_DIR
    ydir = d / sid
    yearly = [r for r in _records(ydir / "yearly-stats.json")
              if str(r.get("stage", "IS")).upper() == "IS"]
    daily = _records(ydir / "daily-pnl.json")

    yearly_sharpes = {str(r["year"]): r["sharpe"] for r in yearly}
    yearly_pnl = {str(r["year"]): float(r["pnl"] or 0) for r in yearly}

    pnls = [float(r["pnl"] or 0) for r in daily]
    dates = [str(r["date"]) for r in daily]
    half = len(pnls) // 2
    half_sharpes = [_sharpe(pnls[:half]), _sharpe(pnls[half:])]
    worst_half = min((h for h in half_sharpes if h is not None), default=None)
    pct_pos = round(sum(1 for p in pnls if p > 0) / len(pnls), 4) if pnls else None

    # best CONSECUTIVE 2-year window by summed pnl
    years = sorted(yearly_pnl)
    best2y, best_sum = None, None
    for a, b in zip(years, years[1:]):
        s = yearly_pnl[a] + yearly_pnl[b]
        if best_sum is None or s > best_sum:
            best2y, best_sum = [a, b], s
    total_pnl = sum(yearly_pnl.values())
    best2y_pnl_share = (round(best_sum / total_pnl, 4)
                        if best2y and total_pnl > 0 else None)

    ex_pnls = ([p for p, dtstr in zip(pnls, dates) if dtstr[:4] not in set(best2y)]
               if best2y else pnls)
    ex_best2y_sharpe = _sharpe(ex_pnls)

    flags = []
    if best2y_pnl_share is not None and best2y_pnl_share > 0.5:
        flags.append("BEST_2Y_GT_50PCT_PNL")
    if ex_best2y_sharpe is not None and ex_best2y_sharpe < 1.0:
        flags.append("EX_BOOM_SHARPE_LT_1")

    return {"sid": sid, "yearly_sharpes": yearly_sharpes,
            "half_sharpes": half_sharpes, "worst_half": worst_half,
            "pct_pos": pct_pos, "best2y": best2y,
            "best2y_pnl_share": best2y_pnl_share,
            "ex_best2y_sharpe": ex_best2y_sharpe, "flags": flags}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = regime_audit(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(out, indent=1))
