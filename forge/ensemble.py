"""forge.ensemble — 2–3-leg ensembles of MEASURED single-field legs (Khoa's tick, 2026-09-04 13:50).

PURPOSE: on the empty cells every single-field hypothesis tops out at Sharpe ≈ 0.75 (487 sims,
two rounds); the 9 historical tier-4 alphas were ensembles of simple legs (00_baseline §A3), and
the ensemble-leg-scale law (one normaliser per leg, weights ≤ 1, monotone) took an earlier family
from 0/754 to 18/164 zero-fail. Whether it lifts THESE legs over the bar is the next round's
experiment — nothing here is proven for this data.

CONSTRUCTION: for one cell, the best measured row per hypothesis (platform Sharpe ≥ `min_sharpe`,
its EX-ANTE sign kept — no flips), legs from DIFFERENT datasets, combined as
    leg_a + w·leg_b [+ w·leg_c]          each leg already ends in group_rank(...) → dimensionless
with w ∈ {1.0, 0.5} on the weaker legs. No price carrier (C30). Settings from the strongest leg.
Leg selection is in-sample: the DSR pool for ensembles is the ensembles tried in that cell, and
the selection of legs adds multiple testing the pool does not see — stated, not hidden.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re

from forge.factory import DEFAULT_SETTINGS, MAX_OPS, candidate_id, op_count
from forge.signature import signature

MIN_SHARPE = 0.2
WEIGHTS = (1.0, 0.5)


def best_legs(rows, region, delay, category, min_sharpe: float = MIN_SHARPE,
              same_dataset: bool = False, cross_category: bool = False) -> list:
    """Best measured single-leg rows for one cell, strongest first. By default one leg per
    hypothesis and one per dataset; `same_dataset` keeps the best leg per (hypothesis, field) so
    several fields of one dataset can be averaged; `cross_category` admits legs measured on other
    categories of the SAME region/delay — the alpha still fills the target cell through its
    target-category leg (pyramid multi-membership), and the extra leg must not be a price carrier
    (C30: rows whose dataset is price-volume are refused). Ensemble rows are never legs."""
    best = {}
    for r in rows.values() if isinstance(rows, dict) else rows:
        m = r.get("meta") or {}
        st = r.get("settings") or {}
        if not m.get("forge") or m.get("ensemble") or not r.get("alpha"):
            continue
        if st.get("region") != region or int(st.get("delay", -1)) != int(delay):
            continue
        if m.get("category") != category and not cross_category:
            continue
        if str(m.get("dataset") or "").startswith("pv"):
            continue
        s = r.get("sharpe")
        if not isinstance(s, (int, float)) or s < min_sharpe:
            continue
        key = (m.get("hypothesis"), m.get("field")) if same_dataset else m.get("hypothesis")
        if key not in best or s > best[key]["sharpe"]:
            best[key] = r
    legs, seen_ds = [], set()
    for r in sorted(best.values(), key=lambda x: -x["sharpe"]):
        ds = (r.get("meta") or {}).get("dataset")
        if ds in seen_ds and not same_dataset:
            continue
        seen_ds.add(ds)
        legs.append(r)
    # the target category must be represented, or the ensemble fills nothing we aimed at
    if cross_category and not any((l.get("meta") or {}).get("category") == category for l in legs):
        return []
    return legs


def _leg_expr(row) -> str:
    return "(%s)" % row["formula"].strip()


def combine(legs, weights) -> str:
    parts = [_leg_expr(legs[0])]
    for leg, w in zip(legs[1:], weights):
        parts.append(_leg_expr(leg) if w == 1.0 else "%s * %s" % (w, _leg_expr(leg)))
    return " + ".join(parts)


def expand(cell, rows, rng, max_candidates: int = 20, max_legs: int = 3, field_datasets=None,
           same_dataset: bool = False, cross_category: bool = False) -> list:
    """Ensemble candidates for one cell from the journal's measured legs. Every combination keeps
    at least one leg of the cell's own category (the leading leg when cross_category)."""
    legs = best_legs(rows, cell.region, cell.delay, cell.category, same_dataset=same_dataset, cross_category=cross_category)
    if len(legs) < 2 or not cell.universe:
        return []
    own = [l for l in legs if (l.get("meta") or {}).get("category") == cell.category]
    others = [l for l in legs if l not in own]
    legs = (own[:3] + others[:3])[:5] if cross_category else legs[:4]
    combos = []
    for k in range(2, min(max_legs, len(legs)) + 1):
        for subset in itertools.combinations(legs, k):
            if cross_category and not any((l.get("meta") or {}).get("category") == cell.category for l in subset):
                continue
            for ws in itertools.product(WEIGHTS, repeat=k - 1):
                combos.append((subset, ws))
    rng.shuffle(combos)
    out, seen = [], set()
    for subset, ws in combos:
        if len(out) >= max_candidates:
            break
        formula = combine(list(subset), ws)
        if op_count(formula) > MAX_OPS:
            continue
        lead = subset[0]
        st = dict(DEFAULT_SETTINGS, region=cell.region, universe=cell.universe, delay=int(cell.delay),
                  neutralization=(lead.get("settings") or {}).get("neutralization", "INDUSTRY"),
                  decay=int((lead.get("settings") or {}).get("decay", 8)),
                  truncation=float((lead.get("settings") or {}).get("truncation", 0.08)))
        cid = candidate_id(formula, st)
        if cid in seen:
            continue
        seen.add(cid)
        hyps = [(l.get("meta") or {}).get("hypothesis") for l in subset]
        mech = "ens:" + "+".join(sorted(hyps))
        out.append({
            "id": cid, "formula": formula, "settings": st,
            "meta": {"hypothesis": mech, "ensemble": 1, "legs": [l["alpha"] for l in subset],
                     "leg_hypotheses": hyps, "leg_sharpes": [l["sharpe"] for l in subset], "weights": [1.0, *ws],
                     "category": cell.category, "region": cell.region, "delay": int(cell.delay),
                     "dataset": "+".join(sorted({(l.get("meta") or {}).get("dataset") or "?" for l in subset})),
                     "field": None, "field_type": "ENSEMBLE", "params": {}, "sign": 1},
            "signature": signature(formula, cell.region, cell.delay, mechanism=mech, field_datasets=field_datasets),
        })
    return out
