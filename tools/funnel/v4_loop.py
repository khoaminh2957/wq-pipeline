#!/usr/bin/env python3
"""v4_loop.py — the deterministic spine of the v4 loop (v4/LOOP.md S4–S6).

`round <prefix>`: analyze a simulated round — score all rows, pick the baseline (gate_gap smallest distance),
print the per-gate shortfall table, name the BINDING gate and its verified playbook lever, check the oracle
(submittable + theme) for a FULL-PASS, and write the round ledger to state/v4/round_<prefix>.json.

The idea/build stages (S0–S2) are AI-driven; sims fire via run_multisim.py. This file is the part that must
never drift: baseline selection, gate accounting, lever mapping, full-pass detection, honest ledger.
"""
from __future__ import annotations
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import gate_gap as GG          # noqa: E402
import submittable as SUB      # noqa: E402
import theme_check as TC       # noqa: E402

V4STATE = ROOT / "state" / "v4"

# binding gate -> the VERIFIED lever for the next 180 (operator_playbook.md)
LEVERS = {
    "LOW_SHARPE": "ts_zscore/ts_rank(.,126) + STATISTICAL neut + dispersion-conditioning (verified +0.1-0.3)",
    "LOW_2Y_SHARPE": "trade_when(rank(d2c)>0.5,.,-1) or util/SI-change conditioning + ts_zscore window sweep (verified 1.29->2.11)",
    "LOW_FITNESS": "returns-regime (SUBINDUSTRY/MARKET) + hump/decay/trunc valve toward tvr in [0.01,0.125]; needs ret/max(tvr,.125)>=0.40",
    "LOW_SUB_UNIVERSE_SHARPE": "breadth: bounded-uniform transforms (rank/quantile-gaussian), avoid concentration (no quantile-cauchy)",
    "CONCENTRATED_WEIGHT": "truncation tighter (0.01-0.02) + signed_power(.,0.5) concave cap",
    "THEME_RETURNS_RATIO": "returns up or turnover down (ratio gate); re-check dataset vs active theme exclusions",
    "HIGH_TURNOVER": "hump(x,hump=0.005-0.02) / settings.decay 2-8 / ts_decay_linear on the fast leg (verified monotone tvr cut)",
}


def load_round(prefix):
    rows = [json.loads(l) for l in open(ROOT / "state/resim_results.jsonl") if l.strip()]
    return [r for r in rows if isinstance(r, dict) and str(r.get("old_id", "")).startswith(prefix)
            and r.get("sharpe") is not None]


def full_pass(row, formula=None, settings=None):
    """Oracle + theme — the ONLY definition of done (v4/LOOP.md win condition)."""
    v = SUB.verdict(row)
    ok_gates = bool(v.get("submittable")) and not v.get("blockers")
    theme_ok, theme_why = True, []
    try:
        at = TC.active_theme()
        r2 = dict(row)
        if formula: r2["formula"] = formula
        if settings: r2["settings"] = settings
        theme_ok, theme_why = TC.theme_match(r2, at) if at else (True, [])
        if isinstance(theme_ok, tuple):   # older signature safety
            theme_ok, theme_why = theme_ok
    except Exception as e:
        theme_ok, theme_why = False, [f"theme_check error: {e}"]
    return ok_gates and theme_ok, {"oracle": v, "theme_ok": theme_ok, "theme_why": theme_why}


def analyze(prefix, cfg_path=None):
    rows = load_round(prefix)
    if not rows:
        return {"prefix": prefix, "error": "no simulated rows"}
    cfg = {}
    if cfg_path and pathlib.Path(cfg_path).exists():
        cfg = {c["old_id"]: c for c in json.load(open(cfg_path))}
    baseline, dist = GG.pick_baseline(rows)
    gaps = GG.gate_gaps(baseline)
    binding = max(gaps, key=gaps.get)
    c = cfg.get(baseline["old_id"], {})
    fp, fp_detail = full_pass(baseline, c.get("formula"), c.get("settings"))
    # any full-passer in the whole round (not just the baseline)?
    passers = []
    for r in rows:
        cc = cfg.get(r["old_id"], {})
        ok, _ = full_pass(r, cc.get("formula"), cc.get("settings"))
        if ok:
            passers.append(r["old_id"])
    ledger = {
        "prefix": prefix, "n_rows": len(rows),
        "baseline": {"old_id": baseline["old_id"], "alpha": baseline.get("alpha"),
                     "sharpe": baseline.get("sharpe"), "fitness": baseline.get("fitness"),
                     "turnover": baseline.get("turnover"), "returns": baseline.get("returns"),
                     "formula": c.get("formula"), "settings": c.get("settings")},
        "gate_distance": {"max": round(dist[0], 4), "mean": round(dist[1], 4)},
        "gate_shortfalls": {k: round(v, 4) for k, v in gaps.items()},
        "binding_gate": binding, "next_lever": LEVERS.get(binding, "?"),
        "full_pass": fp, "full_passers_in_round": passers,
        "oracle": {k: fp_detail["oracle"].get(k) for k in ("submittable", "status", "blockers", "low_sharpe", "low_2y")},
        "theme_ok": fp_detail["theme_ok"], "theme_why": fp_detail["theme_why"],
        "escalate": dist[0] < 0.10 and not fp,     # near a gate -> +90/+180 per protocol
    }
    V4STATE.mkdir(parents=True, exist_ok=True)
    (V4STATE / f"round_{prefix.rstrip('_')}.json").write_text(json.dumps(ledger, indent=1))
    return ledger


def _print(led):
    if led.get("error"):
        print(f"{led['prefix']}: {led['error']}"); return
    b = led["baseline"]
    print("=" * 78)
    print(f"v4 ROUND {led['prefix']} — {led['n_rows']} sims")
    print("=" * 78)
    print(f"BASELINE {b['old_id']} / {b['alpha']}  sh={b['sharpe']} fit={b['fitness']} tvr={b['turnover']} ret={b['returns']}")
    print(f"gate_distance max={led['gate_distance']['max']} mean={led['gate_distance']['mean']}")
    for k, v in led["gate_shortfalls"].items():
        mark = " <-- BINDING" if k == led["binding_gate"] and v > 0 else (" PASS" if v == 0 else "")
        print(f"  {k:26s} {v:.3f}{mark}")
    if led["full_pass"]:
        print(f"\n*** FULL PASS — queue for Khoa's submit decision (never auto-submit) ***")
    else:
        print(f"\nnext lever [{led['binding_gate']}]: {led['next_lever']}")
        if led["escalate"]:
            print("ESCALATE: near-gate (max<0.10) -> +90/+180 sims this family")
    if led["full_passers_in_round"]:
        print(f"full-passers in round: {led['full_passers_in_round']}")
    print(f"ledger -> state/v4/round_{led['prefix'].rstrip('_')}.json")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "round":
        _print(analyze(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
        return 0
    print("usage: v4_loop.py round <old_id_prefix> [configs.json]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
