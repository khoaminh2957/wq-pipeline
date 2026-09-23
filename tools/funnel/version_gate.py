#!/usr/bin/env python3
"""version_gate.py — the "must beat v1" gate (Khoa 2026-07-17). Any future loop update ships ONLY if its
champion BEATS the saved baseline on BOTH performance AND robustness. Loads v<N>/baseline_metrics.json and
compares a candidate; deterministic, no API.

Rule (both required):
  PERFORMANCE — candidate sharpe STRICTLY greater than the baseline champion's sharpe.
  ROBUST      — candidate is >= the baseline on every robustness axis: zero-fail, HT-ratio pass, theme-match,
                and drawdown no worse (<=) than the baseline's.

Usage:
  version_gate.py --candidate cand.json [--baseline v1/baseline_metrics.json]
  cand.json = {"sharpe":..,"drawdown":..,"zero_fail":true,"ht_pass":true,"theme_match":true}
  python: version_gate.beats(candidate, baseline) -> {"advance":bool, "reasons":[...]}
"""
from __future__ import annotations
import argparse, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _champ(baseline):
    c = baseline.get("champion", {})
    perf = c.get("performance", {})
    rob = c.get("robust", {})
    return {
        "sharpe": perf.get("sharpe"),
        "drawdown": perf.get("drawdown"),
        "zero_fail": bool(rob.get("zero_fail")),
        "ht_pass": bool(rob.get("ht_returns_ratio_pass")),
        "theme_match": bool(rob.get("theme_match")),
    }


def beats(candidate: dict, baseline: dict):
    """Return {advance, reasons}. advance == candidate beats the baseline on performance AND robust."""
    b = _champ(baseline)
    reasons, ok = [], True
    cs, bs = candidate.get("sharpe"), b["sharpe"]
    # PERFORMANCE: strictly greater sharpe
    if cs is None or bs is None or not (cs > bs):
        ok = False
        reasons.append(f"performance: sharpe {cs} not > baseline {bs}")
    else:
        reasons.append(f"performance: sharpe {cs} > {bs} ✓")
    # ROBUST: zero-fail, ht_pass, theme_match must all hold; drawdown no worse
    for k in ("zero_fail", "ht_pass", "theme_match"):
        if b.get(k) and not candidate.get(k):
            ok = False
            reasons.append(f"robust: {k} regressed (baseline True, candidate {candidate.get(k)})")
    cd, bd = candidate.get("drawdown"), b["drawdown"]
    if bd is not None and (cd is None or cd > bd + 1e-9):
        ok = False
        reasons.append(f"robust: drawdown {cd} not proven <= baseline {bd}")
    else:
        reasons.append(f"robust: drawdown {cd} <= baseline {bd} ✓")
    return {"advance": ok, "reasons": reasons, "baseline_sharpe": bs, "candidate_sharpe": cs}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--baseline", default=str(ROOT / "v1/baseline_metrics.json"))
    a = ap.parse_args(argv)
    cand = json.load(open(a.candidate))
    base = json.load(open(a.baseline))
    res = beats(cand, base)
    print(json.dumps(res, indent=1))
    print("ADVANCE ✓ (beats baseline)" if res["advance"] else "BLOCKED ✗ (does not beat baseline)")
    return 0 if res["advance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
