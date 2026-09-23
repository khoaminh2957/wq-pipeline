"""TVR experiment (Khoa tick 2026-09-20, "Thí nghiệm cặp đối chứng"): paired turnover twins.

THE PROBLEM. LOW_FITNESS refused 1,005 of 1,008 rows on quota day ET 2026-09-20. All three that
passed carried turnover <= 0.1238; the median turnover of a passer was 0.1196 against 0.1718 for a
refusal. That is not a coincidence, it is the platform's own arithmetic: fitness = Sharpe *
sqrt(|returns| / max(turnover, 0.125)), so the denominator is FLOORED at 0.125 and turnover above
it is penalised by a square root while turnover below it is free. Applying that formula to the 27
rows that reached the Sharpe bar, 11 of them clear fitness >= 1.0 at turnover 0.125 -- arithmetic on
a known formula, NOT a prediction, because cutting turnover changes the alpha and not merely the
denominator.

A CLAIM THAT DID NOT SURVIVE, recorded because the retraction is the useful part. This module was
first written on pearson(turnover, PROD) = -0.473 over all 102 rows with a correlation reading, read
as "lower turnover buys fitness but costs correlation". Pooled WITHIN the Sharpe band that decides
anything (|sharpe| >= 1.58, n=46) the sign REVERSES to +0.278, and the turnover ranges of rows that
clear both 0.70 lines and rows that do not are the same interval: [0.079, 0.189] p50 0.121 against
[0.077, 0.192] p50 0.135. The -0.473 was Sharpe leaking through an unpooled comparison -- Sharpe
drives PROD hard (r=+0.655) and prod p50 climbs 0.569 -> 0.795 across the Sharpe bands. So:
    fitness wants turnover DOWN        (EXACT, it is the formula)
    correlation's response to turnover  UNKNOWN; not measurably separated inside the band
Cutting turnover may well be nearly free on correlation. That is what this run is for.

WHY IT IS STILL PAIRED. Correlation is what actually refuses these alphas -- of 46 rows that cleared
the Sharpe bar and carry a reading, 7 sit under both lines, 39 do not -- so any change to turnover
must be reported on that axis too or the run cannot say whether it helped. Every twin is reported
against its own base on BOTH axes. The variable that DOES separate the 7 from the 39 in that band is
the mechanism, not the turnover (usa_short_x_profitability_x_accruals 2 of 2, options_x_short 1 of
25), but that is POST-HOC on single-digit counts and no experiment has tested it.

DESIGN (paired, following forge/offline/pow_pairs.py, which established that simulations are
deterministic -- 4 duplicate constructions returned identical metrics, diagnosis_ladder.md §3c -- so
the base is the journal row itself and is never re-simulated):
  base rows  USA/d1 COMPLETE, Sharpe >= MIN_SHARPE, turnover >= MIN_TURNOVER so there is room to
             cut, no existing decay/power/hump wrapper, capped at PER_MECH rows per mechanism so one
             construction cannot carry the result (the 2026-09-20 correlation sample had 11 of its
             15 rows from a single mechanism, effective n 4 not 15)
  twins      one per arm, ARMS below; meta.recipe = TVR, meta.base_alpha = the base row
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import allocate as AL, harvest as HV, probe as PR, score as SC  # noqa: E402
from forge.factory import candidate_id  # noqa: E402

TAG = "TVR"
PLAN = ROOT / "state/forge/plans/tvr.json"
MIN_SHARPE = 1.45
MIN_TURNOVER = 0.15
PER_MECH = 12
FITNESS_FLOOR = 0.125          # the denominator floor in the platform's fitness formula


def arms() -> dict:
    """arm name -> a function turning a base formula into the twin's formula.

    This is the whole experiment: each arm is one way of spending signal speed to buy turnover, and
    they differ in what they spend it on. Whether they differ in what they cost on correlation is
    UNMEASURED -- see the retraction in the module docstring; the honest prior is no difference.

    TODO(human): define the arms.

    The operators available for this (all on the RC-85 allowlist, signatures in OPERATORS.md):
      ts_decay_linear(x, d)      weighted average over d days -- smooths the SIGNAL itself, so the
                                 alpha becomes genuinely slower. Cheapest turnover, but slow is what
                                 the submitted book already is, so this is the arm most likely to
                                 push PROD correlation up.
      hump(x, hump=0.01)         suppresses position CHANGES smaller than the threshold and leaves
                                 the signal's speed alone. Cuts turnover without slowing the alpha;
                                 whether it cuts enough at a tolerable threshold is UNMEASURED.
      ts_mean(x, d)              plain moving average; blunter than ts_decay_linear, same direction.
      trade_when(cond, x, -1)    trades only when a condition holds; the sharpest instrument and the
                                 easiest to overfit, since the condition is a free parameter.

    Return a dict of {arm_name: callable(base_formula) -> twin_formula}. Two to four arms; each name
    must also be added to forge/offline/ab_report.py ARMS or the arm is dropped silently from the
    report (that bug is why that tuple exists). A pair of arms that differ only in strength measures
    the dose; a pair that differ in operator measures which instrument is cheaper on correlation.
    """


def _chk(row, name) -> dict:
    for c in row.get("checks") or []:
        if c.get("name") == name:
            return c
    return {}


def base_rows(journal=HV.JOURNAL, per_mech=PER_MECH, min_sharpe=MIN_SHARPE,
              min_turnover=MIN_TURNOVER) -> list:
    """Rows worth cutting: strong enough to matter, turnover high enough that cutting it does
    something, and not already wrapped in an operator that does the same job."""
    latest = {}
    for r in HV.read_jsonl(journal):
        if r.get("alpha"):
            latest[r["alpha"]] = r
    pool, seen = [], set()
    for r in latest.values():
        m, s = r.get("meta") or {}, r.get("settings") or {}
        if r.get("status") != "COMPLETE" or not r.get("checks") or not m.get("forge"):
            continue
        if s.get("region") != "USA" or int(s.get("delay", -1)) != 1 or m.get("recipe"):
            continue
        f = r.get("formula") or ""
        if not f or any(op in f for op in ("ts_decay_linear", "signed_power", "hump", "trade_when")):
            continue
        if not isinstance(r.get("sharpe"), (int, float)) or abs(r["sharpe"]) < min_sharpe:
            continue
        if not isinstance(r.get("turnover"), (int, float)) or r["turnover"] < min_turnover:
            continue
        key = (f, json.dumps(s, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        pool.append(r)
    pool.sort(key=lambda r: -abs(r["sharpe"]))
    per, out = collections.Counter(), []
    for r in pool:
        h = (r.get("meta") or {}).get("hypothesis")
        if per[h] >= per_mech:
            continue
        per[h] += 1
        out.append(r)
    return out


def twins(rows: list, spec=None) -> list:
    spec = spec if spec is not None else arms()
    if not spec:
        raise SystemExit("tvr_pairs.arms() returned nothing -- the arms are not defined yet")
    out = []
    for r in rows:
        st, m = dict(r.get("settings") or {}), dict(r.get("meta") or {})
        for arm, wrap in spec.items():
            formula = wrap(r["formula"])
            meta = dict(m, recipe=TAG, arm=arm, base_alpha=r["alpha"], base_sharpe=r.get("sharpe"),
                        base_fitness=r.get("fitness"), base_returns=r.get("returns"),
                        base_turnover=r.get("turnover"), cand=candidate_id(formula, st))
            out.append({"formula": formula, "settings": st, "meta": meta})
    return out


def build(out_path=PLAN, journal=HV.JOURNAL) -> dict:
    rows = base_rows(journal)
    cons = twins(rows)
    plan = {"seed": 0, "n": len(cons), "made_at": time.time(), "hypotheses": len({(r.get("meta") or {}).get("hypothesis") for r in rows}),
            "cells_considered": 1, "gate": {}, "quarantined": 0, "ensembles": "off", "n_ensembles": 0,
            "blocks": [{"cell": "USA/d1 (turnover twins)", "weight": 0, "kept": len(cons), "class": TAG}],
            "allocate": False, "pair_classes": {}, "blocks_by_class": {TAG: len(cons)}, "mode": "composites",
            "composites": len(rows), "n_composites": len(cons), "by_delay": {0: 0, 1: len(cons)},
            "experiment": TAG, "bases": [r["alpha"] for r in rows], "constructions": cons}
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out_path).write_text(json.dumps(plan))
    return plan


def _q(xs, k=0.5):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    i = (len(xs) - 1) * k
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def report(journal=HV.JOURNAL, corr=None) -> dict:
    """Paired deltas on BOTH axes. `corr` defaults to the stored correlation readings; a twin with
    no reading is counted separately rather than silently pooled as if correlation were unchanged."""
    corr = PR.load_corr() if corr is None else corr
    latest = {}
    for r in HV.read_jsonl(journal):
        if r.get("alpha"):
            latest[r["alpha"]] = r
    tw = [r for r in latest.values()
          if (r.get("meta") or {}).get("recipe") == TAG and r.get("status") == "COMPLETE" and r.get("checks")]
    out = {"twins_landed": len(tw), "arms": {}}
    for arm in sorted({(r.get("meta") or {}).get("arm") for r in tw}):
        pairs = []
        for r in (x for x in tw if x["meta"].get("arm") == arm):
            b = latest.get(r["meta"].get("base_alpha"))
            if not b:
                continue
            cb, ct = corr.get(b["alpha"]) or {}, corr.get(r["alpha"]) or {}
            both = all(isinstance(c.get(k), (int, float)) for c in (cb, ct) for k in ("prod", "self"))
            pairs.append({"twin": r["alpha"], "base": b["alpha"], "hyp": r["meta"].get("hypothesis"),
                          "d_turnover": (r.get("turnover") or 0) - (b.get("turnover") or 0),
                          "d_sharpe": abs(r.get("sharpe") or 0) - abs(b.get("sharpe") or 0),
                          "d_fitness": (r.get("fitness") or 0) - (b.get("fitness") or 0),
                          "tvr_twin": r.get("turnover"), "under_floor": (r.get("turnover") or 1) <= FITNESS_FLOOR,
                          "fit1_base": (b.get("fitness") or 0) >= 1.0, "fit1_twin": (r.get("fitness") or 0) >= 1.0,
                          "y2_base": bool(AL.cleared_first_window(b)), "y2_twin": bool(AL.cleared_first_window(r)),
                          "sub_base": _chk(b, "LOW_SUB_UNIVERSE_SHARPE").get("result") == "PASS",
                          "sub_twin": _chk(r, "LOW_SUB_UNIVERSE_SHARPE").get("result") == "PASS",
                          "pass_base": SC.stage(b)["stage"] not in ("fail", "incomplete"),
                          "pass_twin": SC.stage(r)["stage"] not in ("fail", "incomplete"),
                          "corr_both": both,
                          "d_prod": (ct["prod"] - cb["prod"]) if both else None,
                          "d_self": (ct["self"] - cb["self"]) if both else None})
        by_hyp = collections.defaultdict(list)
        for p in pairs:
            by_hyp[p["hyp"]].append(p)

        def summ(ps):
            m = [p for p in ps if p["corr_both"]]
            return {"n": len(ps), "n_corr": len(m),
                    "d_turnover_p50": _q([p["d_turnover"] for p in ps]),
                    "d_sharpe_p50": _q([p["d_sharpe"] for p in ps]),
                    "d_sharpe_iqr": [_q([p["d_sharpe"] for p in ps], 0.25), _q([p["d_sharpe"] for p in ps], 0.75)],
                    "d_fitness_p50": _q([p["d_fitness"] for p in ps]),
                    "under_floor": sum(p["under_floor"] for p in ps),
                    "fit1_base": sum(p["fit1_base"] for p in ps), "fit1_twin": sum(p["fit1_twin"] for p in ps),
                    "y2_base": sum(p["y2_base"] for p in ps), "y2_twin": sum(p["y2_twin"] for p in ps),
                    "sub_base": sum(p["sub_base"] for p in ps), "sub_twin": sum(p["sub_twin"] for p in ps),
                    "pass_base": sum(p["pass_base"] for p in ps), "pass_twin": sum(p["pass_twin"] for p in ps),
                    "d_prod_p50": _q([p["d_prod"] for p in m]), "d_self_p50": _q([p["d_self"] for p in m])}
        out["arms"][arm] = {"all": summ(pairs), "by_hyp": {h: summ(ps) for h, ps in sorted(by_hyp.items())},
                            "pairs": pairs}
    return out


def _line(name, s) -> str:
    if not s["n"]:
        return "  %-42s n 0" % name
    corr = ("dProd %+.3f | dSelf %+.3f (n %d)" % (s["d_prod_p50"], s["d_self_p50"], s["n_corr"])
            if s["n_corr"] else "corr NOT MEASURED -- no verdict on the gate that decides submittability")
    return ("  %-42s n %3d | dTvr p50 %+.3f | under floor %d | dSharpe p50 %+.2f [%+.2f, %+.2f] | "
            "dFit p50 %+.2f | fit>=1 %d->%d | y2 %d->%d | sub %d->%d | all-binding %d->%d | %s"
            % (name, s["n"], s["d_turnover_p50"], s["under_floor"], s["d_sharpe_p50"], s["d_sharpe_iqr"][0],
               s["d_sharpe_iqr"][1], s["d_fitness_p50"], s["fit1_base"], s["fit1_twin"], s["y2_base"],
               s["y2_twin"], s["sub_base"], s["sub_twin"], s["pass_base"], s["pass_twin"], corr))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("build", "report"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        p = build()
        by = collections.Counter((c["meta"]["hypothesis"], c["meta"]["arm"]) for c in p["constructions"])
        print("TVR plan: %d twins of %d bases -> %s" % (len(p["constructions"]), len(p["bases"]), PLAN))
        for k, v in sorted(by.items()):
            print("  %-46s %-10s %d" % (k[0], k[1], v))
        for c in p["constructions"][:1] + p["constructions"][-1:]:
            print("  [%s/%s] %s" % (c["meta"]["arm"], c["meta"]["base_alpha"], c["formula"][:150]))
        return 0
    rep = report()
    if a.json:
        print(json.dumps(rep, indent=1))
        return 0
    print("TVR twins landed: %d" % rep["twins_landed"])
    for arm, s in rep["arms"].items():
        print("arm %s" % arm)
        print(_line("ALL", s["all"]))
        for h, hs in s["by_hyp"].items():
            print(_line(h, hs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
