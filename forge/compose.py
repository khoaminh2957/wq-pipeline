"""forge.compose — cross-family composites: the construction the ratified hypothesis standard
prescribes (Dim 5 / hard gate 6) and the single-field library cannot satisfy on its own.

Khoa 2026-09-04 ("1"): rebuild the construction layer to the standard. A composite joins >= 2
legs of DIFFERENT families with a conditioning combiner on rank-bounded operands:
    multiply:  multiply(A⁺, B⁺)                 high only when both legs agree (confirmation)
    gate:      if_else(greater(B⁺, 0.5), A, 0)  trade A only where B confirms (conditioning)
where X⁺ is the leg oriented so that "good" is high: a leg written `-group_rank(...)` becomes
`(1 - group_rank(...))`. Every leg is already a group_rank in [0, 1], so every product operand
is rank-bounded (standard Dim 5). The standard's own measurement (00_baseline / hypothesis_standard):
single-op constructions 0.13–0.55 Sharpe, multiply 1.95, if_else 1.58 — on USA d1 model77 data;
whether it transfers to these cells is the next round's experiment.
The cell is filled by the leg whose category matches it; the other leg may come from another
category of the same region/delay (pyramid multi-membership). No price carrier can enter: legs are
library hypotheses, and the library has none (C30).
"""
from __future__ import annotations

import itertools
import random

from forge import factory as F
from forge.factory import DEFAULT_SETTINGS, MAX_OPS, candidate_id, op_count
from forge.signature import signature


def positive_form(formula: str) -> str:
    f = formula.strip()
    return "(1 - %s)" % f[1:].strip() if f.startswith("-") else f


def combine(a_formula: str, b_formula: str, combiner: str) -> str:
    if combiner == "multiply":
        return "multiply(%s, %s)" % (positive_form(a_formula), positive_form(b_formula))
    if combiner == "gate":
        return "if_else(greater(%s, 0.5), %s, 0)" % (positive_form(b_formula), a_formula.strip())
    raise ValueError("unknown combiner %r" % combiner)


def _leg_candidates(h, cell, index, rng, per_leg):
    """Distinct leg FORMULAS (the leg's own settings are irrelevant: the composite sets them)."""
    leg_cell = cell if cell.category in h.categories() else cell._replace(category=h.categories()[0])
    seen, out = set(), []
    for c in F.expand(h, leg_cell, index, rng, max_candidates=10 ** 6):
        if c["formula"] in seen:
            continue
        seen.add(c["formula"])
        out.append(c)
        if len(out) >= per_leg:
            break
    return out, (leg_cell.category == cell.category)


def expand(comp, cell, index: dict, lib_by_id: dict, rng: random.Random, max_candidates: int = 20,
           per_leg: int = 4, field_datasets=None) -> list:
    """Composite candidates for one cell. Empty when a leg has no field here or no leg serves
    the cell's category."""
    if not cell.universe:
        return []
    legs, served = [], False
    for hid in comp.legs:
        h = lib_by_id.get(hid)
        if h is None or cell.delay not in h.delays or (h.regions != "any" and cell.region not in h.regions):
            return []
        cands, is_target = _leg_candidates(h, cell, index, rng, per_leg)
        if not cands:
            return []
        served = served or is_target
        legs.append(cands)
    if not served:
        return []
    combos = list(itertools.product(*legs, comp.combiners, comp.settings["neutralization"], comp.settings["decay"]))
    rng.shuffle(combos)
    out, seen = [], set()
    for combo in combos:
        if len(out) >= max_candidates:
            break
        *leg_c, combiner, neut, decay = combo
        if len(leg_c) > 2 and combiner != "multiply":
            continue                                 # three legs: confirmation only (Khoa 15:20, 3-leg Piotroski)
        formula = combine(leg_c[0]["formula"], leg_c[1]["formula"], combiner)
        for extra in leg_c[2:]:                      # each further leg confirms: multiply by its positive form
            formula = "multiply(%s, %s)" % (formula, positive_form(extra["formula"]))
        if op_count(formula) > MAX_OPS:
            continue
        settings = dict(DEFAULT_SETTINGS, region=cell.region, universe=cell.universe, delay=int(cell.delay),
                        neutralization=neut, decay=int(decay), truncation=float(comp.settings.get("truncation", 0.08)))
        cid = candidate_id(formula, settings)
        if cid in seen:
            continue
        seen.add(cid)
        out.append({
            "id": cid, "formula": formula, "settings": settings,
            "meta": {"hypothesis": comp.id, "composite": 1, "combiner": combiner,
                     "legs": [c["meta"]["hypothesis"] for c in leg_c], "families": list(comp.families),
                     "category": cell.category, "region": cell.region, "delay": int(cell.delay),
                     "field": leg_c[0]["meta"]["field"], "field2": leg_c[1]["meta"]["field"],
                     "dataset": "+".join(sorted({c["meta"]["dataset"] for c in leg_c})),
                     "field_type": "COMPOSITE", "params": {"legs": [c["meta"]["params"] for c in leg_c]}, "sign": 1},
            "signature": signature(formula, cell.region, cell.delay, mechanism=comp.id, field_datasets=field_datasets),
        })
    return out
