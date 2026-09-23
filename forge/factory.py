"""forge.factory — expand hypothesis × cell × field catalogue into concrete simulation candidates.

Every candidate carries: formula, full platform settings, meta (hypothesis id, cell, field,
dataset, params) and its novelty signature. VECTOR fields are reduced with the hypothesis'
`signal.vector` operator before entering the MATRIX template (58% of the fields behind empty
cells are VECTOR — measured 2026-09-04). Nothing here is random except the sampling of the grid,
which is seeded by the caller.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import random
import re

from forge.signature import signature

MAX_OPS = 62            # platform refuses > 64 operators; measured 2026-08-30 (~260 wasted POSTs)
DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY", "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
    "language": "FASTEXPR", "visualization": False, "maxTrade": "OFF", "maxPosition": "OFF",
}


def op_count(expr: str) -> int:
    """Operators as the platform counts them: function calls + infix arithmetic (mirrors climb.op_count)."""
    return len(re.findall(r"[a-z_][a-z0-9_]*\(", expr)) + len(re.findall(r" [\+\-\*/] ", expr))


def _name(x):
    return x.get("name") if isinstance(x, dict) else x


def _id(x):
    return x.get("id") if isinstance(x, dict) else x


def catalogue_index(rows) -> dict:
    """{field_id: {"type", "dataset", "category", "subcategory"}} from crawled field rows."""
    out = {}
    for r in rows:
        fid = r.get("id")
        if not fid:
            continue
        out[fid] = {"type": r.get("type"), "dataset": _id(r.get("dataset")),
                    "category": _name(r.get("category")), "subcategory": _name(r.get("subcategory"))}
    return out


def _usable(h, fid, meta, category):
    if meta["category"] != category or meta["type"] not in ("MATRIX", "VECTOR"):
        return False
    if h.datasets and meta["dataset"] not in h.datasets:
        return False
    return not (meta["type"] == "VECTOR" and not h.signal.get("vector"))


def eligible_fields(h, category: str, index: dict) -> list:
    """Legs the hypothesis may use for a cell of `category`, sorted. One-leg hypotheses give
    [(field_id, type, dataset)]; with `signal2` each entry is
    (field_id, type, dataset, field2_id, type2) — pairs where BOTH fields are in the catalogue."""
    sig = h.signal
    if h.signal2:
        out = []
        for f1, f2 in zip(sig["fields"], h.signal2["fields"]):
            m1, m2 = index.get(f1), index.get(f2)
            if m1 and m2 and _usable(h, f1, m1, category) and _usable(h, f2, m2, category):
                out.append((f1, m1["type"], m1["dataset"], f2, m2["type"]))
        return sorted(out)
    wanted = set(sig.get("fields") or [])
    pattern = re.compile(sig["pattern"]) if sig.get("pattern") else None
    out = []
    for fid, meta in index.items():
        if not _usable(h, fid, meta, category):
            continue
        if wanted and fid not in wanted:
            continue
        if pattern and not pattern.search(fid):
            continue
        out.append((fid, meta["type"], meta["dataset"]))
    return sorted(out)


def _leg(h, field, ftype):
    x = "%s(%s)" % (h.signal["vector"], field) if ftype == "VECTOR" else field
    density = h.signal.get("density")
    if density == "zero":
        return "add(%s, 0, filter=true)" % x
    if density == "backfill":
        return "ts_backfill(%s, %d)" % (x, int(h.signal.get("density_window") or 20))
    return x


def render(h, field: str, ftype: str, params: dict, field2: str | None = None, ftype2: str | None = None,
           template_i: int = 0) -> str:
    kw = dict(params, signal=_leg(h, field, ftype))
    if field2 is not None:
        kw["signal2"] = _leg(h, field2, ftype2)
    return h.templates()[template_i].format(**kw)


def candidate_id(formula: str, settings: dict) -> str:
    key = re.sub(r"\s+", "", formula) + "|" + json.dumps(
        {k: settings.get(k) for k in ("region", "universe", "delay", "neutralization", "decay", "truncation")}, sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def expand(h, cell, index: dict, rng: random.Random, max_candidates: int = 20) -> list:
    """Candidates for one hypothesis on one cell. `cell` needs region, delay, universe, category.
    The full grid (fields × params × neutralization × decay) is shuffled with `rng` and cut to
    `max_candidates` (AlphaBench: ~20 per round is the cost/quality point)."""
    if not cell.universe or cell.delay not in h.delays:
        return []
    if h.regions != "any" and cell.region not in h.regions:
        return []
    if cell.category not in h.categories():
        return []
    fields = eligible_fields(h, cell.category, index)
    if not fields:
        return []
    field_datasets = {fid: m["dataset"] for fid, m in index.items()}
    names = sorted(h.params)
    grid = list(itertools.product(fields, range(len(h.templates())), *(h.params[n] for n in names),
                                  h.settings["neutralization"], h.settings["decay"]))
    rng.shuffle(grid)
    out, seen = [], set()
    for combo in grid:
        if len(out) >= max_candidates:
            break
        leg, ti, *pvals, neut, decay = combo
        fid, ftype, ds = leg[:3]
        f2, t2 = (leg[3], leg[4]) if len(leg) == 5 else (None, None)
        params = dict(zip(names, pvals))
        formula = render(h, fid, ftype, params, f2, t2, template_i=ti)
        if op_count(formula) > MAX_OPS:
            continue
        settings = dict(DEFAULT_SETTINGS, region=cell.region, universe=cell.universe, delay=int(cell.delay),
                        neutralization=neut, decay=int(decay), truncation=float(h.settings.get("truncation", 0.08)))
        cid = candidate_id(formula, settings)
        if cid in seen:
            continue
        seen.add(cid)
        out.append({
            "id": cid, "formula": formula, "settings": settings,
            "meta": {"hypothesis": h.id, "category": cell.category, "region": cell.region, "delay": int(cell.delay),
                     "field": fid, "field_type": ftype, "field2": f2, "dataset": ds, "params": params, "sign": h.sign,
                     "template_i": ti},
            "signature": signature(formula, cell.region, cell.delay, mechanism=h.id, field_datasets=field_datasets),
        })
    return out
