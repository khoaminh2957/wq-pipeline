"""Random-within-the-grammar generator (Khoa 2026-09-07, ticked: "ngẫu nhiên trong ngữ pháp + bộ thẩm định cuối").

Every draw is random, but only inside the set the labels allow, so every construction type-checks
by construction; `typed.judge` runs on the result anyway as the last gate and its refusals are
counted (a refusal here is a bug in this file, not a bad draw).

Layers (Khoa's tick):
  L0  a labelled field with a stated sign (MATRIX; a VECTOR is read through vec_avg)
  L1  time: ts_backfill for quarterly/annual, density for sparse, a scale for currency / share
      levels (divide by a same-unit size field), then optionally ts_mean / ts_delta / ts_zscore
  L2  a SCORE: group_rank(x, G) | rank(x) | ts_rank(x, w); a "-" leg becomes 1 - score
  L3  multiply of 2-3 legs from DIFFERENT domains, or a gate: if_else(greater(legA, 0.5), legB, 0)
  L4  optional condition on an unstated-sign field: if_else(greater(rank(ts_mean(g, w)), q), core, 0)
"""
from __future__ import annotations

import collections
import glob
import json
import math
import pathlib
import random
import re

from forge import typed as T
from forge.labels import for_region
from forge.factory import DEFAULT_SETTINGS, MAX_OPS, candidate_id, op_count
from forge.signature import signature

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIRECTIONAL_KINDS = {"level", "ratio", "return", "score"}
GATE_KINDS = {"level", "ratio", "count", "dispersion", "score"}
SCALE_DOMAINS = {"size", "sales", "fundamental-other"}
NEUTS = ["STATISTICAL", "INDUSTRY", "SUBINDUSTRY"]
DECAYS = [4, 8]
TRUNC = 0.08
STD_GROUPS = ["sector", "industry", "subindustry"]
WINDOWS_SMOOTH = [5, 10, 20]
WINDOWS_TS = [63, 126, 252]


def region_groups(region: str, delay: int, fields_dir=ROOT / "fetched/rc/fields") -> list:
    """GROUP fields the catalogue lists for this region/delay (sector/industry/subindustry first)."""
    found = set()
    for f in glob.glob(str(fields_dir / ("%s_*_d%d.jsonl" % (region, delay)))):
        for line in open(f):
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("type") == "GROUP" and j["id"] in T.GROUPS:
                found.add(j["id"])
    return [g for g in STD_GROUPS if g in found] or sorted(found) or ["sector"]


class Pool:
    """The labelled fields usable in one region/delay, split by role."""

    def __init__(self, labels: dict, region: str, delay: int):
        key = "%s/d%d" % (region, delay)
        self.key = key
        self.all = [for_region(v, key) for v in labels.values() if key in v.get("regions", [])]
        self.directional = [v for v in self.all if v["sign"] in ("+", "-") and v["kind"] in DIRECTIONAL_KINDS
                            and v["unit"] not in ("code", "bool")]
        self.gates = [v for v in self.all if v["sign"] == "unstated" and v["kind"] in GATE_KINDS and v["structure"] == "MATRIX"
                      and v["sparsity"] != "sparse"]
        # an event stream's intensity (how many news / transactions / estimates) is a natural gate
        self.event_gates = [v for v in self.all if v["structure"] == "VECTOR" and v.get("vec_role") in ("event-count", "event-flag", "event-code")]
        self.scales = {}
        for unit in ("currency", "shares"):
            self.scales[unit] = [v for v in self.all if v["unit"] == unit and v["kind"] == "level" and v["sign"] == "unstated"
                                 and v["structure"] == "MATRIX" and v["domain"] in SCALE_DOMAINS | {"volume-activity"}
                                 and v["sparsity"] != "sparse"]

        # a numbered family (market_relevance_score_1..100) is one idea, not a hundred: its members
        # share the family's draw mass so a 100-member family cannot crowd out single fields
        self.family_size = collections.Counter(_stem(v["id"]) for v in self.all)

    def weight(self, v) -> float:
        # uncrowded datasets first (C9): 1/sqrt(users+1); dense a little more than medium
        fam = max(1, self.family_size.get(_stem(v["id"]), 1))
        return (1.0 / math.sqrt((v.get("users") or 0) + 1.0)) * (1.0 if v["sparsity"] == "dense" else 0.7) / fam


def _stem(fid: str) -> str:
    return re.sub(r"_?\d+$", "", fid)


def _pick(rng: random.Random, items: list, weight) -> dict | None:
    if not items:
        return None
    ws = [weight(v) for v in items]
    return rng.choices(items, weights=ws, k=1)[0]


def leg(v: dict, pool: Pool, rng: random.Random, groups: list) -> dict | None:
    """One typed leg from a labelled field: formula (a SCORE oriented so that higher = long) + meta."""
    x = v["id"]
    steps = []
    if v["structure"] == "VECTOR":
        reds = v.get("vec_reducers") or ["vec_avg"]
        red = reds[0] if rng.random() < 0.7 or len(reds) == 1 else rng.choice(reds[1:])
        after = (v.get("vec_after") or {}).get(red, v["kind"])
        if after == "count":
            return None                                    # an event count has no direction: gates only
        x = "%s(%s)" % (red, x)
        steps.append(red)
    if v["kind"] == "level" and v["unit"] in ("currency", "shares"):
        den = _pick(rng, [s for s in pool.scales[v["unit"]] if s["id"] != v["id"] and s["time"] == v["time"]] or pool.scales[v["unit"]],
                    lambda s: 1.0)
        if den is None:
            return None
        x = "%s / %s" % (x, den["id"])
        steps.append("scale:%s" % den["id"])
    if v["time"] in ("quarterly", "annual"):
        w = rng.choice(WINDOWS_TS[:2] if v["time"] == "quarterly" else WINDOWS_TS[1:])
        x = "ts_backfill(%s, %d)" % (x, w)
        steps.append("backfill")
    elif v["sparsity"] == "sparse":
        x = "add(%s, 0, filter=true)" % x
        steps.append("density")
    else:
        r = rng.random()
        if r < 0.35:
            x = "ts_mean(%s, %d)" % (x, rng.choice(WINDOWS_SMOOTH))
            steps.append("smooth")
        elif r < 0.5 and v["kind"] == "level" and not any(st.startswith("scale:") for st in steps):
            x = "ts_delta(%s, %d)" % (x, rng.choice(WINDOWS_SMOOTH))          # a scaled level is a ratio: H2 forbids its delta
            steps.append("change")
        elif r < 0.6:
            x = "ts_zscore(%s, %d)" % (x, rng.choice(WINDOWS_TS))
            steps.append("ts_zscore")
    r = rng.random()
    if r < 0.6:
        g = rng.choice(groups)
        score = "group_rank(%s, %s)" % (x, g)
        steps.append("group_rank:%s" % g)
    elif r < 0.8:
        score = "rank(%s)" % x
        steps.append("rank")
    else:
        score = "ts_rank(%s, %d)" % (x, rng.choice(WINDOWS_TS))
        steps.append("ts_rank")
    if v["sign"] == "-":
        score = "(1 - %s)" % score
        steps.append("flip")
    return {"formula": score, "field": v["id"], "domain": v["domain"], "dataset": v.get("dataset"), "category": v.get("category"),
            "kind": v["kind"], "sign": v["sign"], "sign_source": v.get("sign_source"), "steps": steps}


def compose(pool: Pool, rng: random.Random, groups: list, cell_category: str) -> dict | None:
    """Two or three legs from different domains, one of them able to fill the cell's category."""
    served = [v for v in pool.directional if v.get("category") == cell_category]
    if not served:
        return None
    first = _pick(rng, served, pool.weight)
    legs = [leg(first, pool, rng, groups)]
    if legs[0] is None:
        return None
    n_legs = 3 if rng.random() < 0.3 else 2
    tries = 0
    while len(legs) < n_legs and tries < 20:
        tries += 1
        v = _pick(rng, [u for u in pool.directional if u["domain"] not in {L["domain"] for L in legs}], pool.weight)
        if v is None:
            break
        L = leg(v, pool, rng, groups)
        if L:
            legs.append(L)
    if len(legs) < 2:
        return None
    if len(legs) == 2 and rng.random() < 0.3:
        combiner = "gate"
        core = "if_else(greater(%s, 0.5), %s, 0)" % (legs[0]["formula"], legs[1]["formula"])
    else:
        combiner = "multiply"
        core = legs[0]["formula"]
        for L in legs[1:]:
            core = "multiply(%s, %s)" % (core, L["formula"])
    gate = None
    if rng.random() < 0.3 and (pool.gates or pool.event_gates):
        q = rng.choice([0.5, 0.7, 0.8])
        if pool.event_gates and rng.random() < 0.3:
            gv = _pick(rng, pool.event_gates, pool.weight)
            red = "vec_count" if "vec_count" in (gv.get("vec_reducers") or []) else (gv.get("vec_reducers") or ["vec_count"])[0]
            gx = "add(%s(%s), 0, filter=true)" % (red, gv["id"])          # no event = zero, not NaN
            gate = {"field": gv["id"], "domain": gv["domain"], "q": q, "event": gv.get("event_stream"), "reducer": red}
        else:
            gv = _pick(rng, pool.gates, pool.weight)
            gx = gv["id"]
            if gv["time"] in ("quarterly", "annual"):
                gx = "ts_backfill(%s, 126)" % gx
            gate = {"field": gv["id"], "domain": gv["domain"], "q": q}
        core = "if_else(greater(rank(ts_mean(%s, 20)), %s), %s, 0)" % (gx, q, core)
    return {"formula": core, "legs": legs, "combiner": combiner, "gate": gate}


def expand(labels: dict, cell, rng: random.Random, max_candidates: int = 20, field_datasets=None, groups=None) -> dict:
    """Judged candidates for one cell in the planner's candidate shape; also the refusal count."""
    if not cell.universe:
        return {"candidates": [], "refused": 0, "reasons": {}}
    pool = Pool(labels, cell.region, cell.delay)
    groups = groups or region_groups(cell.region, cell.delay)
    out, seen, refused, reasons = [], set(), 0, {}
    tries = 0
    while len(out) < max_candidates and tries < max_candidates * 6:
        tries += 1
        c = compose(pool, rng, groups, cell.category)
        if c is None:
            break
        formula = c["formula"]
        if op_count(formula) > MAX_OPS:
            continue
        verdict = T.judge(formula, labels, pool.key)
        if not verdict["ok"]:
            refused += 1
            for h in verdict["hard"][:1]:
                reasons[h[:40]] = reasons.get(h[:40], 0) + 1
            continue
        settings = dict(DEFAULT_SETTINGS, region=cell.region, universe=cell.universe, delay=int(cell.delay),
                        neutralization=rng.choice(NEUTS), decay=rng.choice(DECAYS), truncation=TRUNC)
        cid = candidate_id(formula, settings)
        if cid in seen:
            continue
        seen.add(cid)
        domains = [L["domain"] for L in c["legs"]]
        hyp = "typed:" + "_x_".join(domains)
        out.append({
            "id": cid, "formula": formula, "settings": settings,
            "meta": {"hypothesis": hyp, "composite": 1, "combiner": c["combiner"], "arm": "typed",
                     "legs": [L["field"] for L in c["legs"]], "families": domains, "category": cell.category,
                     "region": cell.region, "delay": int(cell.delay), "field": c["legs"][0]["field"], "field2": c["legs"][1]["field"],
                     "dataset": "+".join(sorted({L["dataset"] for L in c["legs"] if L["dataset"]})),
                     "field_type": "TYPED", "params": {"legs": [L["steps"] for L in c["legs"]], "gate": c["gate"]},
                     "sign": 1, "judge_soft": verdict["soft"], "sign_sources": [L["sign_source"] for L in c["legs"]]},
            "signature": signature(formula, cell.region, cell.delay, mechanism=hyp, field_datasets=field_datasets),
        })
    return {"candidates": out, "refused": refused, "reasons": reasons,
            "pool": {"directional": len(pool.directional), "gates": len(pool.gates), "event_gates": len(pool.event_gates)}}
