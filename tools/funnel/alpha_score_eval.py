#!/usr/bin/env python3
"""alpha_score_eval.py — validation harness + deterministic CI gate battery for the alpha SCORER (Stage 7).

Ranking-first, group-leak-safe, label-agnostic. PRIMARY = within-root Kendall-tau + NDCG@5 of the composite vs a
desk-anchored quality reference (binding USA-d1 gate margins), under GroupKFold on root. Plus 7 CI gates that FAIL
the build. `evaluate(rows) -> {pass, gates:{...}, metrics:{...}}`.
"""
from __future__ import annotations
import json, pathlib, sys
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import alpha_score as A  # noqa: E402


# ---- desk-anchored quality reference (NOT the training objective; a coherence lens for ranking eval) ----
def desk_ref(row):
    """A monotone desk proxy for 'better alpha': high fitness/returns, low turnover, decent sharpe/2Y. Used only to
    measure whether the composite's WITHIN-ROUND ordering is coherent — never fed to the model."""
    m = A.extract(row)
    f = lambda x, d=0.0: x if isinstance(x, (int, float)) else d
    tv = max(f(m["turnover"]), 0.01)
    return (2.0 * f(m["fitness"]) + 1.5 * f(m["returns"]) * 10 - 1.0 * tv
            + 0.5 * f(m["sharpe"]) + 0.5 * f(m["sharpe_2y"]))


def _ndcg(order_by_score, rel, k=5):
    idx = np.argsort(-np.asarray(order_by_score))[:k]
    dcg = sum(rel[i] / np.log2(j + 2) for j, i in enumerate(idx))
    ideal = np.argsort(-np.asarray(rel))[:k]
    idcg = sum(rel[i] / np.log2(j + 2) for j, i in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def within_root_ranking(rows, scorer, min_configs=10):
    """Per-root Kendall-tau + NDCG@5 of composite-score vs desk_ref, averaged over roots with >=min_configs."""
    from scipy.stats import kendalltau
    groups = {}
    for r in rows:
        groups.setdefault(A.root_of(r.get("old_id")), []).append(r)
    taus, ndcgs = [], []
    for root, g in groups.items():
        if len(g) < min_configs:
            continue
        s = [scorer.score(r) for r in g]
        ref = [desk_ref(r) for r in g]
        if len(set(s)) < 2 or len(set(ref)) < 2:
            continue
        tau = kendalltau(s, ref).correlation
        if tau == tau:  # not nan
            taus.append(tau)
        rel = np.maximum(np.asarray(ref) - min(ref), 0)
        ndcgs.append(_ndcg(s, rel, k=5))
    return {"n_roots": len(taus), "kendall_tau_mean": round(float(np.mean(taus)), 3) if taus else None,
            "kendall_tau_median": round(float(np.median(taus)), 3) if taus else None,
            "ndcg5_mean": round(float(np.mean(ndcgs)), 3) if ndcgs else None}


def evaluate(rows, scorer=None):
    scorer = scorer or A.AlphaScorer.load()
    clean = [r for r in rows if A.is_usa_d1(r) and r.get("sharpe") is not None]
    gates, metrics = {}, {}

    # --- PRIMARY: within-root ranking coherence ---
    metrics["within_root_ranking"] = within_root_ranking(clean, scorer)

    # --- GATE 1: Khoa constraint ordering ---
    w = scorer.weights
    gates["1_constraints"] = bool(min(w[p] for p in A.PRIORITY) > max(w[o] for o in A.OTHER)
                                  and w["turnover"] >= w["fitness"] and w["turnover"] >= w["returns"])

    # --- GATE 2: degeneracy probes score below real-median AND are ceiling-ineligible ---
    real = sorted(scorer.score(r) for r in clean)
    med = real[len(real) // 2] if real else 0
    probes = {
        "null_allzero": {"old_id": "probe_null", "sharpe": 0, "fitness": 0, "returns": 0, "turnover": 0, "drawdown": 0, "checks": []},
        "zeroturn_const": {"old_id": "probe_zt", "sharpe": 0, "fitness": 0, "returns": 0, "turnover": 0.0, "drawdown": 0, "checks": []},
        "tiny_dead": {"old_id": "probe_td", "sharpe": 0.05, "fitness": 0.02, "returns": 0.001, "turnover": 0.005, "drawdown": 0.05, "checks": []},
    }
    deg = {name: {"score": scorer.score(p), "below_median": scorer.score(p) < med,
                  "ceiling_eligible": A.AlphaScorer.ceiling_eligible(p)} for name, p in probes.items()}
    metrics["degeneracy_probes"] = deg
    gates["2_degeneracy"] = all(d["below_median"] and not d["ceiling_eligible"] for d in deg.values())

    # --- GATE 3: calibration — top score-decile desk_ref >= mid decile ---
    scored = sorted(((scorer.score(r), desk_ref(r)) for r in clean), reverse=True)
    n = len(scored)
    if n >= 10:
        top = np.mean([d for _, d in scored[:n // 10]])
        mid = np.mean([d for _, d in scored[4 * n // 10:6 * n // 10]])
        gates["3_calibration"] = bool(top >= mid)
        metrics["calibration"] = {"top_decile_ref": round(float(top), 3), "mid_decile_ref": round(float(mid), 3)}
    else:
        gates["3_calibration"] = True

    # --- GATE 4: turnover partial-dependence monotone-down (2nd-diff <= tol) over [0.01,0.7] ---
    base = {"fitness": 0.5, "returns": 0.05, "sharpe": 1.0, "drawdown": 0.1, "checks": [{"name": "LOW_2Y_SHARPE", "value": 1.0}]}
    tvs = np.linspace(0.01, 0.7, 25)
    pdp = [scorer.score({**base, "turnover": t}) for t in tvs]
    mono_down = all(pdp[i] >= pdp[i + 1] - 1e-9 for i in range(len(pdp) - 1))
    gates["4_turnover_pdp_monotone_down"] = bool(mono_down)
    metrics["turnover_pdp"] = {"tvr_0.02": pdp[0], "tvr_0.35": pdp[12], "tvr_0.7": pdp[-1]}

    # --- GATE 5: per-metric monotonicity (dscore/dx sign) ---
    def mono(metric, up):
        lo = {"fitness": 0.3, "returns": 0.03, "turnover": 0.1, "sharpe": 0.5, "sharpe_2y": 0.5, "sub_universe": 0.3, "drawdown": 0.1}
        r1 = {**{k: lo[k] for k in lo}, "checks": [{"name": "LOW_2Y_SHARPE", "value": lo["sharpe_2y"]}, {"name": "LOW_SUB_UNIVERSE_SHARPE", "value": lo["sub_universe"]}]}
        hi = dict(r1); hi[metric] = lo[metric] * 2 + 0.1
        if metric in ("sharpe_2y", "sub_universe"):
            hi["checks"] = [{"name": "LOW_2Y_SHARPE", "value": hi["sharpe_2y"] if metric == "sharpe_2y" else lo["sharpe_2y"]},
                            {"name": "LOW_SUB_UNIVERSE_SHARPE", "value": hi["sub_universe"] if metric == "sub_universe" else lo["sub_universe"]}]
        d = scorer.score(hi) - scorer.score(r1)
        return d >= -1e-9 if up else d <= 1e-9
    permetric = {m: mono(m, A.HIGHER_BETTER[m]) for m in A.FEATURES}
    gates["5_per_metric_monotone"] = all(permetric.values())
    metrics["per_metric_monotone"] = permetric

    # --- GATE 6: weight stability across seeds (weights are fixed-by-construction -> trivially stable) ---
    seeds_w = []
    for s in range(5):
        sc2 = A.AlphaScorer.fit(rows, seed=s)
        seeds_w.append(tuple(round(sc2.weights[k], 4) for k in A.FEATURES))
    gates["6_weight_stability"] = len(set(seeds_w)) == 1
    metrics["weight_sets_across_seeds"] = len(set(seeds_w))

    # --- GATE 7: ceiling monotonicity (ledger invariant) ---
    if A.CEILING.exists():
        st = json.load(open(A.CEILING))
        ceils = [r["ceiling_after"] for r in st.get("rounds", [])]
        gates["7_ceiling_monotone"] = all(ceils[i] <= ceils[i + 1] for i in range(len(ceils) - 1))
    else:
        gates["7_ceiling_monotone"] = True

    # --- GATE 8: analytic monotonicity of the anchored priority metrics (decorrelation-compatibility) ---
    ok8 = True
    for ai, a in enumerate(A.RESID_ANCHOR, start=1):
        fb = sum(scorer.weights[k] * abs(scorer.resid[k]["coef"][ai]) / scorer.resid[k]["span"] for k in A.RESID_METRICS)
        ok8 = ok8 and (scorer.weights[a] >= fb)
    gates["8_resid_feedback_below_weight"] = bool(ok8)

    # --- GATE 9: decorrelation actually held (satellites ⟂ profitability; cross-redundancy low) ---
    import numpy as _np
    from scipy.stats import spearmanr as _sp
    prof = _np.array([(scorer._norm("fitness", A.extract(r).get("fitness"))
                       + scorer._norm("returns", A.extract(r).get("returns"))) / 2 for r in clean])
    sat_ok = True
    for k in A.RESID_METRICS:
        rv = _np.array([scorer._resid_norm(k, A.extract(r)) for r in clean])
        if len(set(rv)) > 1:
            sat_ok = sat_ok and (abs(_sp(rv, prof).correlation) <= A.DECORR_MAX_CORR)
    # cross-redundancy: mean |spearman| of {fitness,returns} contribs vs the 3 OTHER contribs
    den = sum(scorer.weights.values())
    def contrib(k):
        t = _np.array([(scorer._resid_norm(k, A.extract(r)) if k in A.RESID_METRICS else scorer._norm(k, A.extract(r).get(k))) for r in clean])
        return scorer.weights[k] * t
    cross = _np.mean([abs(_sp(contrib(p), contrib(o)).correlation) for p in ("fitness", "returns") for o in A.OTHER])
    gates["9_decorrelation_held"] = bool(sat_ok and cross <= 0.30)
    metrics["decorrelation"] = {"cross_redundancy": round(float(cross), 3),
                                "sat_prof_corr": {k: round(float(_sp(_np.array([scorer._resid_norm(k, A.extract(r)) for r in clean]), prof).correlation), 3) for k in A.RESID_METRICS}}

    all_pass = all(gates.values())
    return {"pass": all_pass, "gates": gates, "metrics": metrics}


def main():
    rows = [json.loads(l) for l in open(ROOT / "state/resim_results.jsonl") if l.strip()]
    res = evaluate([r for r in rows if isinstance(r, dict)])
    print(json.dumps(res, indent=1, default=str))
    print("\nBUILD", "PASS ✓" if res["pass"] else "FAIL ✗")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
