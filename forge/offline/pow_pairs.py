"""POW experiment (Khoa tick 2026-09-09 14:50: "Chạy ngay hôm nay", 300 sims): paired signed_power twins.

Round-2 lever L1 (docs/harness5/round_2/diagnosis_fitness.md §7): fitness = Sharpe^1.5 * sqrt(sigma /
max(turnover, 0.125)); at an unchanged ordering, signed_power(x, y > 1) stretches the tails of the
position vector -> book volatility sigma up (EX-ANTE from the platform's own arithmetic); the Sharpe
effect is UNKNOWN (R17/R18/R23 at n 40: sigma +22 % / +25 % / +10 %, Sharpe p50 -0.08 / -0.11 / +0.01).

DESIGN (paired; simulations are deterministic -- 4 duplicate constructions gave identical metrics,
diagnosis_ladder.md §3c -- so the base is the journal row itself, never re-simulated):
  base rows  USA/d1 COMPLETE rows with Sharpe >= MIN_SHARPE, no power/decay wrap, three strata:
             usa_short_x_profitability_x_accruals (pure-sigma case, turnover ~0.10), options_x_short
             at STATISTICAL (positive control: 4 of its 18 passers are STATISTICAL) and
             ravenpack_x_short (the round-1 bar-reacher) -- PER_STRATUM best by Sharpe each
  twins      signed_power(<base formula>, 1.5)  arm pow15;  signed_power(<base formula>, 2)  arm pow2
             same settings; meta.recipe = POW, meta.base_alpha = the base row
PREDICTIONS written before the run (the Researcher's, §7): sigma +10 % (y 1.5) / +20 % (y 2) at p50,
fitness x1.05 / x1.10 at held Sharpe, Sharpe p50 within +-0.1 of base. REFUTED if sigma gain < 5 %,
or Sharpe p50 falls > 0.15, or all-binding passes do not rise. Logged: CONCENTRATED_WEIGHT,
sub-universe, ladder window (both expected sigma-free).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import harvest as HV, score as SC  # noqa: E402
from forge.factory import candidate_id  # noqa: E402
from forge import allocate as AL  # noqa: E402

TAG = "POW"
PLAN = ROOT / "state/forge/plans/pow.json"
POWERS = {"pow15": 1.5, "pow2": 2}
STRATA = (("usa_short_x_profitability_x_accruals", None), ("options_x_short", "STATISTICAL"), ("ravenpack_x_short", None))
PER_STRATUM = 50
MIN_SHARPE = 1.4


def _chk(row, name) -> dict:
    for c in row.get("checks") or []:
        if c.get("name") == name:
            return c
    return {}


def base_rows(journal=HV.JOURNAL, per_stratum=PER_STRATUM, min_sharpe=MIN_SHARPE) -> list:
    latest = {}
    for r in HV.read_jsonl(journal):
        if r.get("alpha"):
            latest[r["alpha"]] = r
    out = []
    for hyp, neut in STRATA:
        pool = []
        seen = set()
        for r in latest.values():
            m, s = r.get("meta") or {}, r.get("settings") or {}
            if r.get("status") != "COMPLETE" or not r.get("checks") or m.get("hypothesis") != hyp:
                continue
            if s.get("region") != "USA" or s.get("delay") != 1 or (neut and s.get("neutralization") != neut):
                continue
            f = r.get("formula") or ""
            if not f or "signed_power" in f or "ts_decay_linear" in f or m.get("recipe"):
                continue
            if not isinstance(r.get("sharpe"), (int, float)) or r["sharpe"] < min_sharpe:
                continue
            key = (f, json.dumps(s, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            pool.append(r)
        pool.sort(key=lambda r: -r["sharpe"])
        out.extend(pool[:per_stratum])
    return out


def twins(rows: list, powers=POWERS) -> list:
    out = []
    for r in rows:
        f, st, m = r["formula"], dict(r.get("settings") or {}), dict(r.get("meta") or {})
        for arm, y in powers.items():
            formula = "signed_power(%s, %s)" % (f, y)
            meta = dict(m, recipe=TAG, arm=arm, power=y, base_alpha=r["alpha"], base_sharpe=r.get("sharpe"),
                        base_fitness=r.get("fitness"), base_returns=r.get("returns"), base_turnover=r.get("turnover"),
                        cand=candidate_id(formula, st))
            out.append({"formula": formula, "settings": st, "meta": meta})
    return out


def build(out_path=PLAN, journal=HV.JOURNAL) -> dict:
    rows = base_rows(journal)
    cons = twins(rows)
    plan = {"seed": 0, "n": len(cons), "made_at": time.time(), "hypotheses": len(STRATA), "cells_considered": 1, "gate": {},
            "blocks": [{"cell": "USA/d1 (paired twins)", "weight": 0, "kept": len(cons), "class": TAG}],
            "quarantined": 0, "ensembles": "off", "n_ensembles": 0, "allocate": False, "pair_classes": {},
            "blocks_by_class": {TAG: len(cons)}, "mode": "composites", "composites": len(STRATA), "n_composites": len(cons),
            "by_delay": {0: 0, 1: len(cons)}, "experiment": TAG, "bases": [r["alpha"] for r in rows], "constructions": cons}
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out_path).write_text(json.dumps(plan))
    return plan


def _sigma(r):
    sh, ret = r.get("sharpe"), r.get("returns")
    if isinstance(sh, (int, float)) and isinstance(ret, (int, float)) and sh:
        return abs(ret) / abs(sh)
    return None


def _binding_pass(r) -> bool:
    return SC.stage(r)["stage"] not in ("fail", "incomplete")


def _q(xs, k=0.5):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    i = (len(xs) - 1) * k
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def report(journal=HV.JOURNAL) -> dict:
    latest = {}
    for r in HV.read_jsonl(journal):
        if r.get("alpha"):
            latest[r["alpha"]] = r
    tw = [r for r in latest.values() if (r.get("meta") or {}).get("recipe") == TAG and r.get("status") == "COMPLETE" and r.get("checks")]
    out = {"twins_landed": len(tw), "arms": {}}
    for arm in POWERS:
        rows = [r for r in tw if r["meta"].get("arm") == arm]
        pairs = []
        for r in rows:
            b = latest.get(r["meta"].get("base_alpha"))
            if not b or not isinstance(_sigma(b), float) or not isinstance(_sigma(r), float):
                continue
            pairs.append({"twin": r["alpha"], "base": b["alpha"], "hyp": r["meta"].get("hypothesis"),
                          "d_sigma_pct": (_sigma(r) / _sigma(b) - 1) * 100,
                          "d_sharpe": r["sharpe"] - b["sharpe"], "d_fitness": (r.get("fitness") or 0) - (b.get("fitness") or 0),
                          "d_turnover": (r.get("turnover") or 0) - (b.get("turnover") or 0),
                          "fit1_base": (b.get("fitness") or 0) >= 1.0, "fit1_twin": (r.get("fitness") or 0) >= 1.0,
                          "y2_base": bool(AL.cleared_first_window(b)), "y2_twin": bool(AL.cleared_first_window(r)),
                          "sub_base": _chk(b, "LOW_SUB_UNIVERSE_SHARPE").get("result") == "PASS",
                          "sub_twin": _chk(r, "LOW_SUB_UNIVERSE_SHARPE").get("result") == "PASS",
                          "conc_twin": _chk(r, "CONCENTRATED_WEIGHT").get("result"),
                          "pass_base": _binding_pass(b), "pass_twin": _binding_pass(r)})
        by_hyp = {}
        for p in pairs:
            by_hyp.setdefault(p["hyp"], []).append(p)
        summ = lambda ps: {"n": len(ps), "d_sigma_pct_p50": _q([p["d_sigma_pct"] for p in ps]),   # noqa: E731
                           "d_sigma_pct_iqr": [_q([p["d_sigma_pct"] for p in ps], 0.25), _q([p["d_sigma_pct"] for p in ps], 0.75)],
                           "d_sharpe_p50": _q([p["d_sharpe"] for p in ps]),
                           "d_sharpe_iqr": [_q([p["d_sharpe"] for p in ps], 0.25), _q([p["d_sharpe"] for p in ps], 0.75)],
                           "d_fitness_p50": _q([p["d_fitness"] for p in ps]), "d_turnover_p50": _q([p["d_turnover"] for p in ps]),
                           "fit1_base": sum(p["fit1_base"] for p in ps), "fit1_twin": sum(p["fit1_twin"] for p in ps),
                           "y2_base": sum(p["y2_base"] for p in ps), "y2_twin": sum(p["y2_twin"] for p in ps),
                           "sub_base": sum(p["sub_base"] for p in ps), "sub_twin": sum(p["sub_twin"] for p in ps),
                           "conc_fail_twin": sum(p["conc_twin"] not in ("PASS", None) for p in ps),
                           "pass_base": sum(p["pass_base"] for p in ps), "pass_twin": sum(p["pass_twin"] for p in ps)}
        out["arms"][arm] = {"all": summ(pairs), "by_hyp": {h: summ(ps) for h, ps in sorted(by_hyp.items())}, "pairs": pairs}
    return out


def _line(name, s) -> str:
    if not s["n"]:
        return "  %-42s n 0" % name
    return ("  %-42s n %3d | dσ p50 %+5.1f%% [%+.1f, %+.1f] | dSharpe p50 %+.2f [%+.2f, %+.2f] | dFit p50 %+.2f | dTvr %+.3f | fit≥1 %d→%d | y2 %d→%d | sub %d→%d | conc-fail %d | all-binding %d→%d"
            % (name, s["n"], s["d_sigma_pct_p50"], s["d_sigma_pct_iqr"][0], s["d_sigma_pct_iqr"][1], s["d_sharpe_p50"], s["d_sharpe_iqr"][0],
               s["d_sharpe_iqr"][1], s["d_fitness_p50"], s["d_turnover_p50"], s["fit1_base"], s["fit1_twin"], s["y2_base"], s["y2_twin"],
               s["sub_base"], s["sub_twin"], s["conc_fail_twin"], s["pass_base"], s["pass_twin"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("build", "report"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        p = build()
        by = {}
        for c in p["constructions"]:
            k = (c["meta"]["hypothesis"], c["meta"]["arm"])
            by[k] = by.get(k, 0) + 1
        print("POW plan: %d twins of %d bases -> %s" % (len(p["constructions"]), len(p["bases"]), PLAN))
        for k, v in sorted(by.items()):
            print("  %-42s %-6s %d" % (k[0], k[1], v))
        for c in p["constructions"][:1] + p["constructions"][-1:]:
            print("  [%s/%s] %s" % (c["meta"]["arm"], c["meta"]["base_alpha"], c["formula"][:150]))
        return 0
    rep = report()
    if a.json:
        print(json.dumps(rep, indent=1))
        return 0
    print("POW twins landed: %d" % rep["twins_landed"])
    for arm, s in rep["arms"].items():
        print("arm %s (signed_power y=%s)" % (arm, POWERS[arm]))
        print(_line("ALL", s["all"]))
        for h, hs in s["by_hyp"].items():
            print(_line(h, hs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
