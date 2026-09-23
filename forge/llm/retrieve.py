"""What the model is allowed to know, assembled from files — never from its own memory.

A local model cannot hold 127,642 field ids, and when asked for one it invents a plausible name.
`forge/llm/verify.py` catches that afterwards, but catching it wastes a generation. This module
removes the failure at the source: every field id, every partner leg and every forbidden family
pair is RETRIEVED and put in the prompt, so the model's job is reduced to choosing among facts and
writing the economics. That is the one thing a small model does well.

Selection does NOT rank by crowding (Khoa tick 2026-09-20, "Bỏ hẳn sort crowding"). It used to:
`shortlist` sorted ascending on userCount and the dataset picker capped it at 200, on the premise
that an uncrowded field decorrelates from the submitted book. MEASURED 2026-09-20, n=102 rows
carrying both a correlation reading and a known field crowding, two crowding metrics and two
derivations: pearson(log10 userCount, PROD) = -0.001 and pearson(log10 alphaCount, PROD) = +0.003.
Crowding predicts correlation exactly not at all. What does: |sharpe| +0.655 and turnover -0.473.
The premise was never tested before because forge/probe.py only measures gate-passers and only
crowded fields ever passed -- so the sample could not contain the answer (see round_4/crowding.md).

The price of the old sort was measured on the same day: the LLM arm wrote on fields of median 9
users against the hand-written library's 3,249, ran ~0.4 lower Sharpe p50, and held 0 of the 27
rows that reached the Sharpe bar. MECHANISM for why crowding is irrelevant: UNKNOWN.

What remains is selection by cell -- the pyramid cell a field's category serves, so a proposal can
aim at an OPEN cell -- and by coverage, because a thin field is thin whoever trades it.
Nothing here reads a simulated result (labels are never derived from sims -- Khoa, 2026-09-07).
"""
from __future__ import annotations

import collections

DESC_CHARS = 170


def used_pairs(ctx) -> set:
    """Family pairs the live library already covers; a proposal repeating one is a sibling."""
    return {tuple(sorted(set(c.families))) for c in ctx.composites}


def partners(ctx, limit: int = 30) -> list:
    """Existing legs a new leg can be combined with, newest-cheapest first for the prompt."""
    out = []
    for h in ctx.library:
        cats = h.categories()
        out.append({"id": h.id, "family": h.family or "-", "sign": h.sign,
                    "category": cats[0] if cats else "-", "title": (h.title or "")[:90]})
    out.sort(key=lambda r: r["family"])
    return out[:limit]


def shortlist(ctx, dataset: str | None = None, domain: str | None = None, n: int = 30,
              max_users: int | None = None, signed_only: bool = True, exclude_burned: bool = False) -> list:
    """Candidate fields for a new leg, as dicts the prompt can print verbatim.

    `dataset` / `domain` narrow the pool; `signed_only` drops fields the label file could not give
    a direction, because a leg needs one. `max_users` still filters when a caller asks for it, but
    it is OFF by default and nothing ranks by it -- crowding does not predict correlation (module
    docstring), so ordering by it only cost Sharpe.
    """
    rows = []
    for fid, cat in ctx.catalogue.items():
        lab = ctx.labels.get(fid)
        if not lab:
            continue
        ds = cat.get("dataset") or {}
        ds_id = ds.get("id") if isinstance(ds, dict) else ds
        if dataset and ds_id != dataset:
            continue
        if is_price_volume(ds_id):        # C30, and the caller may have named a pv dataset outright
            continue
        if domain and lab.get("domain") != domain:
            continue
        if signed_only and lab.get("sign") not in ("+", "-"):
            continue
        users = cat.get("userCount") or 0
        if max_users is not None and users > max_users:
            continue
        if exclude_burned and fid in ctx.burned:
            continue
        rows.append({"id": fid, "dataset": ds_id, "type": cat.get("type"),
                     "category": (cat.get("category") or {}).get("name") if isinstance(cat.get("category"), dict) else cat.get("category"),
                     "domain": lab.get("domain"), "kind": lab.get("kind"), "unit": lab.get("unit"),
                     "time": lab.get("time"), "coverage": lab.get("coverage"), "sign": lab.get("sign"),
                     "sign_source": lab.get("sign_source"), "users": users,
                     "alphas": cat.get("alphaCount") or 0,
                     "description": (cat.get("description") or "")[:DESC_CHARS]})
    rows.sort(key=lambda r: -(r["coverage"] or 0))
    return rows[:n]


def is_price_volume(dataset_id) -> bool:
    """C30: no price carrier as a base. `forge/ensemble.py` already refuses these by the same test,
    and `forge/compose.py` states outright that legs cannot be price carriers because 'the library
    has none'. That was true only because nothing had written one yet -- the author's own pool held
    six pv datasets (pv87, pv64, pv48, pv20, pv109, pv73) the whole time, all under the old 200-user
    cap, so the constraint was never enforced here. Found 2026-09-20 while lifting the cap."""
    return str(dataset_id or "").startswith("pv")


def datasets_for_author(ctx, max_users: int | None = None, min_signed: int = 3) -> list:
    """Datasets a mechanism can be written on: enough signed fields to build a leg, most material
    first, never a price carrier (C30). Was `datasets_by_crowding`, which capped users at 200 and
    ranked the emptiest dataset top; that cap is what kept the LLM off every field that has ever
    cleared the Sharpe bar."""
    agg = collections.defaultdict(lambda: {"signed": 0, "users": 0, "cat": "-"})
    for fid, cat in ctx.catalogue.items():
        lab = ctx.labels.get(fid)
        if not lab or lab.get("sign") not in ("+", "-"):
            continue
        ds = cat.get("dataset") or {}
        ds_id = ds.get("id") if isinstance(ds, dict) else ds
        if not ds_id:
            continue
        a = agg[ds_id]
        a["signed"] += 1
        a["users"] = max(a["users"], cat.get("userCount") or 0)
        c = cat.get("category")
        a["cat"] = (c.get("name") if isinstance(c, dict) else c) or a["cat"]
    out = [{"dataset": k, **v} for k, v in agg.items()
           if v["signed"] >= min_signed and not is_price_volume(k)
           and (max_users is None or v["users"] <= max_users)]
    out.sort(key=lambda r: -r["signed"])
    return out


def fields_block(rows: list) -> str:
    """The retrieved fields as a compact table the model reads and quotes ids from."""
    out = ["id | type | kind/unit | cadence | cov | sign(src) | users | description"]
    for r in rows:
        out.append("%s | %s | %s/%s | %s | %.2f | %s(%s) | %d | %s" % (
            r["id"], r["type"], r["kind"], r["unit"], r["time"], r["coverage"] or 0,
            r["sign"], r["sign_source"], r["users"], r["description"].replace("\n", " ")))
    return "\n".join(out)


def partners_block(rows: list) -> str:
    out = ["leg_id | family | sign | category | what it says"]
    for r in rows:
        out.append("%s | %s | %+d | %s | %s" % (r["id"], r["family"], r["sign"], r["category"], r["title"]))
    return "\n".join(out)


def pairs_block(pairs: set) -> str:
    return ", ".join(sorted("×".join(p) for p in pairs))
