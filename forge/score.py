"""forge.score — post-simulation gates and the robust score (design §6).

Inputs are journal rows as layered_sim writes them: `checks` = [{name, result, limit, value}],
`sharpe`, `fitness`, `turnover`, `returns`, `drawdown`, `margin`, `longCount`, `shortCount`,
`settings`, `meta`. Limits are READ FROM THE ROW — they differ by segment (d0: 2.69/1.5).

Stages, in order:
  platform  every binding check PASS (C14: PASS is enough, no margin); CONCENTRATED_WEIGHT
            WARNING disqualifies (Khoa 2026-08-14: "cứ concentrated weight là loại")
  turnover  C15 band 2%–25%; above → "decay-retry", below → "low"
  dsr       C13 DSR >= 0.95 from the PnL curve, N = candidates in the same selection pool
  → candidate for the correlation probe; the soft score orders candidates within a pool.
"""
from __future__ import annotations

import math

from forge import dsr as D

TURNOVER_BAND = (0.02, 0.25)
DSR_MIN = 0.95
# Checks the platform reports PENDING at sim time or that do not bind a regular submission.
# REGULAR_SUBMISSION is the platform's AGGREGATE verdict and reads PENDING at sim time; treating it
# as a binding PENDING check staged the first two full passers (vRk095rv, qMWbdlmv, 2026-09-04
# 21:12, Sharpe 1.85 / fitness 1.03, every real check PASS) as "incomplete" and no harvest, probe or
# submit ever saw them. It is judged by its parts, never by itself.
NON_BINDING = ("SELF_CORRELATION", "PROD_CORRELATION", "MATCHES_COMPETITION", "MATCHES_THEMES",
               "OSMOSIS_ALLOCATION", "POWER_POOL_CORRELATION", "CLUSTER_TEST", "DATA_DIVERSITY",
               "MATCHES_PYRAMID", "REGULAR_SUBMISSION")


def checks(row) -> dict:
    return {c.get("name"): c for c in (row.get("checks") or []) if isinstance(c, dict) and c.get("name")}


def platform_verdict(row) -> tuple:
    """('pass', []) or ('fail', [names]) or ('incomplete', []) when the row carries no checks."""
    ck = checks(row)
    if not ck:
        return "incomplete", []
    # A BINDING CHECK MUST READ PASS. Measured 2026-09-04 (composites round, GLB/d1): the platform
    # grades Sharpe 1.01 against a 1.58 line as WARNING, not FAIL -- WARNING is the band just under
    # the line, not a pass. C21 (auto-submit) requires "all gates PASS"; C14 only says no EXTRA
    # margin is demanded above the line. So FAIL and WARNING both refuse; PENDING/None on a binding
    # check is "incomplete", never a pass.
    bad, pending = [], []
    for name, c in ck.items():
        res = c.get("result")
        if name in NON_BINDING:
            continue
        if res in ("FAIL", "WARNING", "ERROR"):
            bad.append(name)
        elif res != "PASS":
            pending.append(name)
    if bad:
        return "fail", sorted(bad)
    return ("incomplete", []) if pending else ("pass", [])


def pyramids_of(row) -> list:
    """Cells the platform says this alpha fills: [{name, multiplier}] from MATCHES_PYRAMID."""
    c = checks(row).get("MATCHES_PYRAMID") or {}
    return list(c.get("pyramids") or [])


def turnover_verdict(row) -> str:
    """C15: above 25% → retry with decay. Below 2% is NOT a rejection: C14 says the platform's PASS
    is sufficient and its LOW_TURNOVER line is 1%; measured 2026-09-04 (composites round), rows at
    turnover 1.3–1.7% passed every platform check and were the best of the round."""
    t = row.get("turnover")
    if t is None:
        return "unknown"
    lo, hi = TURNOVER_BAND
    if t > hi:
        return "decay-retry"
    return "ok" if t >= lo or _platform_low_turnover_passes(row) else "low"


def _platform_low_turnover_passes(row) -> bool:
    c = checks(row).get("LOW_TURNOVER") or {}
    return c.get("result") == "PASS"


def limit_ratio(row, name) -> float | None:
    """value / limit for a check (>1 means margin above the bar); None when unavailable."""
    c = checks(row).get(name) or {}
    v, lim = c.get("value"), c.get("limit")
    try:
        return float(v) / float(lim) if lim else None
    except (TypeError, ValueError):
        return None


def stage(row, dsr_out=None) -> dict:
    """Where a simulated row stands. `dsr_out` is forge.dsr.evaluate(...) or None (not yet)."""
    verdict, bad = platform_verdict(row)
    out = {"platform": verdict, "failed": bad, "turnover": turnover_verdict(row),
           "pyramids": [p.get("name") for p in pyramids_of(row)], "dsr": None, "stage": None}
    if verdict != "pass":
        out["stage"] = "fail" if verdict == "fail" else "incomplete"
        return out
    if out["turnover"] != "ok":
        out["stage"] = "turnover-" + out["turnover"]
        return out
    if dsr_out is None:
        out["stage"] = "needs-dsr"
        return out
    if not dsr_out.get("ok"):
        out["stage"] = "dsr-unscored"
        return out
    out["dsr"] = dsr_out["dsr"]
    out["stage"] = "candidate" if dsr_out["dsr"] >= DSR_MIN else "dsr-fail"
    return out


def robust_score(row, dsr_out, dataset_load: int = 0, op_count: int = 0) -> float:
    """Soft ordering score for candidates in one pool. Every term is a proxy for out-of-sample
    survival (OS is unobservable, C25); weights are EX-ANTE equal, not fitted."""
    terms = []
    if dsr_out and dsr_out.get("ok"):
        terms.append(dsr_out["dsr"])                                  # 0..1
    sub = limit_ratio(row, "LOW_SUB_UNIVERSE_SHARPE")
    if sub is not None:
        terms.append(min(sub, 2.0) / 2.0)                             # sub-universe margin
    lad = limit_ratio(row, "IS_LADDER_SHARPE")
    if lad is not None:
        terms.append(min(lad, 2.0) / 2.0)                             # trailing-2y margin
    dd = row.get("drawdown")
    if dd is not None:
        terms.append(max(0.0, 1.0 - float(dd)))                       # lower drawdown better
    terms.append(1.0 / (1.0 + math.log1p(max(dataset_load, 0))))      # novelty distance to book
    terms.append(max(0.0, 1.0 - op_count / 20.0))                     # complexity (Falck et al.)
    return sum(terms) / len(terms)


def second_best(scored, tol: float = 0.10):
    """C16: within one hypothesis, if the top two scores differ by < tol (relative), promote #2.
    `scored` = [(score, item)]; returns the chosen item or None."""
    if not scored:
        return None
    ranked = sorted(scored, key=lambda t: -t[0])
    if len(ranked) >= 2 and ranked[0][0] > 0 and (ranked[0][0] - ranked[1][0]) / ranked[0][0] < tol:
        return ranked[1][1]
    return ranked[0][1]
