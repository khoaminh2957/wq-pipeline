"""tools.ci_fixture — a FROZEN cohort the scorer is pinned against (draw 2, round 1 F1 and S8).

A pre-merge gate cannot grade the pipeline's output -- under D14 a candidate version has produced no
rows at merge time -- so what it CAN grade is the scorer itself: this fixed, synthetic cohort is scored
by forge.offline.benchmark.build_from, and the card must equal tools/ci_golden_card.json. A change to a
floor, a weight, a gate or the composite changes the card, so it cannot slip through a commit unseen.

WHAT THIS PROVES AND WHAT IT DOES NOT. It proves the scorer did not CHANGE. It does not prove the scorer
is RIGHT -- the cohort is synthetic and the golden card was recorded from the scorer it now guards.
Every case below is chosen to exercise one decision the scorer makes; the comment says which.
"""
from __future__ import annotations

import datetime
import zoneinfo

ET = zoneinfo.ZoneInfo("America/New_York")
NOW = datetime.datetime(2026, 9, 20, 15, 0, tzinfo=ET).timestamp()     # the 09-20 quota day is unfinished
PASS = [{"name": n, "result": "PASS"} for n in ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE",
                                                 "IS_LADDER_SHARPE", "CONCENTRATED_WEIGHT", "HIGH_TURNOVER",
                                                 "LOW_TURNOVER")]


def _row(alpha, day, sharpe, formula, decay=4, neut="INDUSTRY", status="COMPLETE", hyp="comp_a", checks=None):
    return {"alpha": alpha, "status": status, "sharpe": sharpe, "formula": formula,
            "dateCreated": "%sT12:00:00-04:00" % day, "checks": checks if checks is not None else PASS,
            "settings": {"region": "USA", "delay": 1, "universe": "TOP3000", "decay": decay,
                         "neutralization": neut, "truncation": 0.08},
            "meta": {"hypothesis": hyp, "mechanism_key": "%s#ds#USA/d1" % hyp}}


def _curve(slope_by_third):
    """A {date: cumulative} curve (the real cache format) of 420 days, one slope per third."""
    d0, out, v = datetime.date(2019, 1, 2), {}, 0.0
    for i in range(420):
        v += slope_by_third[min(i // 140, 2)]
        out[(d0 + datetime.timedelta(days=i)).isoformat()] = v
    return out


def cohort():
    """(rows, scored, corr, history, curves, standard, now)."""
    rows = [
        # P1 -- PROVEN: every gate measured and passing; two true neighbours with similar Sharpe
        _row("P1", "2026-09-17", 1.8, "rank(a)"),
        _row("P1n1", "2026-09-17", 1.7, "rank(a)", decay=8),
        _row("P1n2", "2026-09-17", 1.6, "rank(a)", neut="SUBINDUSTRY"),
        # U1 -- UNPROVEN: no neighbours, no curve; nothing failed, two gates unmeasured
        _row("U1", "2026-09-18", 1.7, "rank(b)", status="WARNING", hyp="comp_b"),
        # R1 -- REFUTED: its own neighbours collapse (fragile) and its hypothesis trips a hard gate
        _row("R1", "2026-09-19", 1.9, "rank(c)", hyp="comp_bad"),
        _row("R1n1", "2026-09-19", 0.1, "rank(c)", decay=8, hyp="comp_bad"),
        _row("R1n2", "2026-09-19", 0.2, "rank(c)", neut="SUBINDUSTRY", hyp="comp_bad"),
        # the unfinished day: must be excluded from every rate
        _row("T1", "2026-09-20", 2.0, "rank(d)"),
        # a failing, never-submitted row: scored, not a product
        _row("F1", "2026-09-18", 0.3, "rank(e)", checks=[{"name": "LOW_SHARPE", "result": "FAIL"}]),
    ]
    scored = {a: {"dsr": 0.97, "pbo_pass": True} for a in ("P1", "U1", "R1", "T1")}
    corr = {a: {"prod": 0.55, "self": 0.40} for a in ("P1", "U1", "R1", "T1")}
    history = [{"alpha": a, "http": 201, "posted_at": datetime.datetime(2026, 9, d, 13, tzinfo=ET).timestamp(),
                "mechanism_key": None} for a, d in (("P1", 17), ("U1", 18), ("R1", 19), ("T1", 20))]
    curves = {"P1": _curve((1.0, 1.0, 1.0)), "R1": _curve((1.0, 0.0, 0.0))}
    standard = {"comp_a": [], "comp_b": [], "comp_bad": [(2, "counterparty names no agent class")]}
    return rows, scored, corr, history, curves, standard, NOW


#: axis 3 is the live repository's own measurement and is pinned separately by its checks, so the
#: fixture scores it at a fixed value rather than re-measuring the tree.
AXIS3 = {"value": 1.0, "floor_met": True}


def card():
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from forge.offline import benchmark as B
    rows, scored, corr, history, curves, standard, now = cohort()
    c = B.build_from(rows, scored, corr, history, curves, standard, now=now, axis3=dict(AXIS3))
    a1, a2 = c["axes"]["axis1_product"], c["axes"]["axis2_throughput"]
    return {
        "constants": {"FLOOR": B.FLOOR, "WEIGHT": B.WEIGHT, "UNPROVEN_CREDIT": B.UNPROVEN_CREDIT,
                      "DORA_BAND": B.DORA_BAND, "BINDING": list(B.BINDING)},
        "verdict": c["verdict"], "floors_unmet": c["floors_unmet"], "composite_0_100": c["composite_0_100"],
        "window": {k: c["window"][k] for k in ("since", "until_exclusive", "quota_days")},
        "axis1": {"value": a1["value"], "status_counts": a1["status_counts"], "gate_coverage": a1["gate_coverage"],
                  "per_alpha": {d["alpha"]: {"status": d["status"], "gates": d["gates"]} for d in a1["detail"]}},
        "axis2": {k: a2[k] for k in ("quota_days", "scored_alphas", "clean_submissions", "clean_per_quota_day",
                                     "poisson_95_per_day", "posts_this_version_made", "sustainable")},
    }
