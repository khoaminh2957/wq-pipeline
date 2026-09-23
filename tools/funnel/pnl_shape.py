#!/usr/bin/env python3
"""pnl_shape.py — turn each alpha's daily PnL curve into SHAPE descriptors, then attribute curve reshaping to
operators by diffing base-vs-variant pairs. Shows WHAT an operator does to the equity curve (drawdown depth,
underwater duration, tail days, slope/recency, smoothness) — the mechanism behind the summary-metric deltas.

Reads state/funnel/pnl_curves.json (from fetch_pnl_curves.py). WQB pnl recordset: records=[[date, cum_pnl], ...].
"""
from __future__ import annotations
import json, pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CURVES = ROOT / "state/funnel/pnl_curves.json"


def _pnl_col(rec):
    """WQB pnl recordset columns = [date, pnl, risk-neutralized-pnl, investability-constrained-pnl]. Return the
    index of the main cumulative 'pnl' column (default 1)."""
    props = (rec.get("schema") or {}).get("properties") or []
    for i, p in enumerate(props):
        if p.get("name") == "pnl":
            return i
    return 1


def _series(rec):
    """records -> (dates, cumulative_pnl array). WQB 'pnl' col is cumulative book PnL (the equity curve)."""
    ci = _pnl_col(rec)
    dates, cum = [], []
    for row in rec["records"]:
        if isinstance(row, dict):
            d = row.get("date"); v = row.get("pnl")
        else:
            d = row[0]; v = row[ci] if ci < len(row) else None
        if v is None:
            continue
        dates.append(d); cum.append(float(v))
    return dates, np.asarray(cum, float)


def descriptors(rec):
    dates, cum = _series(rec)
    n = len(cum)
    if n < 30:
        return None
    daily = np.diff(cum, prepend=cum[0])            # daily PnL (first day = level)
    daily = np.diff(cum)                             # true day-over-day change, len n-1
    sd = daily.std() or 1e-9
    # --- drawdown on the cumulative equity curve ---
    peak = np.maximum.accumulate(cum)
    dd = cum - peak                                  # <=0, in book$ units
    span = (cum.max() - cum.min()) or 1e-9
    max_dd = dd.min()
    max_dd_frac = -max_dd / span                     # depth relative to total PnL span
    underwater = dd < -1e-9
    # longest underwater run (days)
    longest, cur = 0, 0
    for u in underwater:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    # --- tails ---
    z = daily / sd
    tail_days = int((np.abs(z) > 3).sum())
    worst_day = float(daily.min()); best_day = float(daily.max())
    downside = daily[daily < 0]
    down_vol = downside.std() if len(downside) else 0.0
    # --- slope / recency (is the recent book steeper or flatter than the full history) ---
    def slope(a):
        x = np.arange(len(a)); return float(np.polyfit(x, a, 1)[0])
    full_slope = slope(cum)
    tail_win = min(504, n // 2)                       # ~2y
    recent_slope = slope(cum[-tail_win:])
    recency_ratio = recent_slope / full_slope if abs(full_slope) > 1e-9 else 0.0
    # --- smoothness / monotonicity ---
    up_frac = float((daily > 0).mean())
    # R^2 of linear fit to cumulative (1.0 = perfectly straight up = smooth)
    x = np.arange(n); fit = np.polyval(np.polyfit(x, cum, 1), x)
    ss_res = float(((cum - fit) ** 2).sum()); ss_tot = float(((cum - cum.mean()) ** 2).sum()) or 1e-9
    straightness = 1 - ss_res / ss_tot
    new_high_frac = float((cum >= peak - 1e-9).mean())
    ann = float(daily.mean() / sd * np.sqrt(252))     # curve-implied sharpe (sanity vs reported)
    return {
        "n_days": n, "start": dates[0], "end": dates[-1],
        "final_pnl": round(float(cum[-1]), 1),
        "curve_sharpe": round(ann, 2),
        "max_dd_frac": round(max_dd_frac, 3),          # drawdown depth (of total span)
        "longest_underwater_days": longest,
        "underwater_frac": round(float(underwater.mean()), 3),
        "tail_days_gt3sd": tail_days,
        "worst_day": round(worst_day, 1), "best_day": round(best_day, 1),
        "down_vol": round(float(down_vol), 2),
        "recency_ratio": round(recency_ratio, 2),      # >1 recent steeper (good 2Y), <1 recent flatter
        "up_day_frac": round(up_frac, 3),
        "straightness": round(straightness, 3),        # 1=smooth ramp, low=choppy
        "new_high_frac": round(new_high_frac, 3),
    }


# base -> variant comparison pairs: (label, base_old_id, variant_old_id, operator_applied)
def compare(curves, pairs):
    out = []
    for label, base_id, var_id, op in pairs:
        b = curves.get(base_id); v = curves.get(var_id)
        if not (b and v):
            out.append({"pair": label, "operator": op, "note": "missing curve"}); continue
        db, dv = descriptors(b), descriptors(v)
        if not (db and dv):
            out.append({"pair": label, "operator": op, "note": "too short"}); continue
        delta = {k: round(dv[k] - db[k], 3) for k in db if isinstance(db[k], (int, float))}
        out.append({"pair": label, "operator": op, "base": db, "variant": dv, "delta": delta})
    return out


def main():
    curves = json.load(open(CURVES))
    # map round -> the old_id present (first fetched per round)
    by_round = {}
    for oid, c in curves.items():
        by_round.setdefault(c.get("round"), oid)
    print("=" * 108)
    print("PnL-CURVE SHAPE  (per alpha)")
    print("=" * 108)
    hdr = f"{'round':18s}{'days':>5s}{'cSharpe':>8s}{'maxDD':>7s}{'uwDays':>7s}{'uw%':>6s}{'tails':>6s}{'recency':>8s}{'up%':>6s}{'smooth':>7s}{'newHi%':>7s}"
    print(hdr)
    for rnd, oid in by_round.items():
        d = descriptors(curves[oid])
        if not d:
            continue
        print(f"{str(rnd)[:18]:18s}{d['n_days']:>5d}{d['curve_sharpe']:>8.2f}{d['max_dd_frac']:>7.2f}"
              f"{d['longest_underwater_days']:>7d}{d['underwater_frac']:>6.2f}{d['tail_days_gt3sd']:>6d}"
              f"{d['recency_ratio']:>8.2f}{d['up_day_frac']:>6.2f}{d['straightness']:>7.2f}{d['new_high_frac']:>7.2f}")
    return curves, by_round


if __name__ == "__main__":
    main()
