#!/usr/bin/env python3
"""gate_gap.py — the v4 loop's baseline-selection metric: HOW CLOSE is an alpha to passing ALL submission gates?

For each binding gate, compute a normalized shortfall in [0,1] (0 = passing, 1 = worst). The alpha's
gate_distance = max shortfall (the binding constraint) with the mean as tie-break; the loop's baseline each round
is the alpha with the SMALLEST gate_distance. This encodes "chọn alpha gần với điều kiện thoả tất cả các gates
nhất" (Khoa) precisely instead of by feel.

Gates (USA d1 TOP1000 Power Pool, ground truth incl the LOW_FITNESS rejection):
  LOW_SHARPE >= 1.58 · LOW_2Y_SHARPE >= 1.58 · LOW_SUB_UNIVERSE_SHARPE (dynamic limit) ·
  CONCENTRATED_WEIGHT (PASS/FAIL) · LOW_FITNESS >= 1.0 · theme HT_HIGH_TURNOVER_RETURNS_RATIO (PASS) ·
  HIGH_TURNOVER <= 0.70 (hard FAIL guard).
"""
from __future__ import annotations
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

SHARPE_BAR = 1.58
FITNESS_BAR = 1.0
TURNOVER_BAR = 0.70


def _check(row, name):
    for c in row.get("checks", []) or []:
        if isinstance(c, dict) and c.get("name") == name:
            return c.get("result"), c.get("value"), c.get("limit")
    return None, None, None


def _short(value, bar, span):
    """Normalized shortfall of value vs a >=bar gate; span = the range over which shortfall saturates to 1."""
    if value is None:
        return 1.0
    return max(0.0, min(1.0, (bar - value) / span))


def _gap_from_check(row, name, fallback_value, bar, span):
    """Shortfall driven by the CHECK RESULT first (region-correct: each check carries its own limit).
    PASS -> 0. WARNING/FAIL -> distance from the check's own limit (fallback: our USA bar). Missing check ->
    fall back to the raw metric vs our bar (never treat missing as passing when we have the raw value)."""
    res, val, lim = _check(row, name)
    if res == "PASS":
        return 0.0
    if res in ("WARNING", "FAIL"):
        b = lim if isinstance(lim, (int, float)) and lim > 0 else bar
        v = val if isinstance(val, (int, float)) else fallback_value
        return _short(v, b, max(b, span))
    # check absent — judge from the raw metric against our USA bar
    return _short(fallback_value, bar, span)


def gate_gaps(row):
    """Per-gate normalized shortfalls in [0,1] (0 = passing). Check-result-first (region-correct limits)."""
    g = {}
    g["LOW_SHARPE"] = _gap_from_check(row, "LOW_SHARPE", row.get("sharpe"), SHARPE_BAR, SHARPE_BAR)
    g["LOW_2Y_SHARPE"] = _gap_from_check(row, "LOW_2Y_SHARPE", None, SHARPE_BAR, SHARPE_BAR)
    g["LOW_SUB_UNIVERSE_SHARPE"] = _gap_from_check(row, "LOW_SUB_UNIVERSE_SHARPE", None, 0.9, 0.9)
    rcw, _, _ = _check(row, "CONCENTRATED_WEIGHT")
    g["CONCENTRATED_WEIGHT"] = 0.0 if rcw in ("PASS", None) else 1.0
    g["LOW_FITNESS"] = _gap_from_check(row, "LOW_FITNESS", row.get("fitness"), FITNESS_BAR, FITNESS_BAR)
    rth, _, _ = _check(row, "HT_HIGH_TURNOVER_RETURNS_RATIO")
    g["THEME_RETURNS_RATIO"] = 0.0 if rth == "PASS" else (0.5 if rth is None else 1.0)   # unknown ≠ pass
    tv = row.get("turnover")
    g["HIGH_TURNOVER"] = 0.0 if (tv is None or tv < TURNOVER_BAR) else 1.0
    return g


def gate_distance(row):
    """Scalar closeness-to-submit: (max shortfall, mean shortfall). Lower = closer. (0,0) = passes everything."""
    g = gate_gaps(row)
    vals = list(g.values())
    return (max(vals), sum(vals) / len(vals))


def pick_baseline(rows):
    """The round's baseline = alpha with the smallest gate_distance (needs sharpe + checks present)."""
    cand = [r for r in rows if isinstance(r.get("sharpe"), (int, float)) and r.get("checks")]
    if not cand:
        return None, None
    best = min(cand, key=gate_distance)
    return best, gate_distance(best)


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else ""
    rows = [json.loads(l) for l in open(ROOT / "state/resim_results.jsonl") if l.strip()]
    rows = [r for r in rows if isinstance(r, dict) and str(r.get("old_id", "")).startswith(prefix)]
    best, dist = pick_baseline(rows)
    if not best:
        print("no candidates"); return 1
    print(f"BASELINE: {best['old_id']} / {best.get('alpha')}  gate_distance=(max {dist[0]:.3f}, mean {dist[1]:.3f})")
    for k, v in gate_gaps(best).items():
        print(f"  {k:26s} shortfall={v:.3f} {'PASS' if v == 0 else ''}")
    # top-5 leaderboard
    lb = sorted([r for r in rows if r.get("checks")], key=gate_distance)[:5]
    print("\nclosest-to-submit leaderboard:")
    for r in lb:
        d = gate_distance(r)
        print(f"  {str(r['old_id'])[:26]:26s} max={d[0]:.3f} mean={d[1]:.3f} sh={r.get('sharpe')} fit={r.get('fitness')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
