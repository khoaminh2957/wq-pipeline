#!/usr/bin/env python3
"""5x test for version_gate.py (Khoa: future must beat v1; tested >=5x)."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.funnel.version_gate import beats

BASE = {"champion": {"performance": {"sharpe": 1.11, "drawdown": 0.052},
                     "robust": {"zero_fail": True, "ht_returns_ratio_pass": True, "theme_match": True}}}


def check():
    e = []
    # higher sharpe + equal robust + better DD -> ADVANCE
    if not beats({"sharpe": 1.6, "drawdown": 0.05, "zero_fail": True, "ht_pass": True, "theme_match": True}, BASE)["advance"]:
        e.append("1.6 zero-fail should advance")
    # equal sharpe -> NOT advance (must be strictly greater)
    if beats({"sharpe": 1.11, "drawdown": 0.05, "zero_fail": True, "ht_pass": True, "theme_match": True}, BASE)["advance"]:
        e.append("equal sharpe must NOT advance")
    # higher sharpe but NOT zero-fail -> NOT advance (robust regressed)
    if beats({"sharpe": 2.0, "drawdown": 0.05, "zero_fail": False, "ht_pass": True, "theme_match": True}, BASE)["advance"]:
        e.append("non-zero-fail must NOT advance even at 2.0 sharpe")
    # higher sharpe but worse drawdown -> NOT advance
    if beats({"sharpe": 1.5, "drawdown": 0.20, "zero_fail": True, "ht_pass": True, "theme_match": True}, BASE)["advance"]:
        e.append("worse drawdown must NOT advance")
    # higher sharpe but theme lost -> NOT advance
    if beats({"sharpe": 1.5, "drawdown": 0.05, "zero_fail": True, "ht_pass": True, "theme_match": False}, BASE)["advance"]:
        e.append("theme regressed must NOT advance")
    # the champion itself does NOT beat itself
    if beats({"sharpe": 1.11, "drawdown": 0.052, "zero_fail": True, "ht_pass": True, "theme_match": True}, BASE)["advance"]:
        e.append("champion must not beat itself")
    return e


if __name__ == "__main__":
    for i in range(1, 6):
        er = check()
        print(f"RUN {i}: {'PASS' if not er else 'FAIL -> ' + '; '.join(er)}")
    er = check()
    print(f"\n{'5/5 runs PASS' if not er else 'FAILED: ' + '; '.join(er)}")
    sys.exit(0 if not er else 1)
