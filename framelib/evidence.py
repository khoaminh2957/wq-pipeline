"""Evidence: what the canonical corpus observed for a frame, per cell. POST-HOC, never a verdict.

Source: frames/canonical/rows_framed.jsonl (FRAME SPEC v1, signed 2026-09-24; one row per alpha).
A frame's rows are those whose frame_key is the frame's canonical key and whose fill holds each pinned
field at its position. Everything is counted per CELL (REGION/dN, "?/d?" when unknown) and never pooled
across cells: the LOW_SHARPE bar differs by row (1.58 / 2.07 / 2.69 / 3.49) and IS_LADDER_SHARPE is absent
on whole cells, so a pooled rate mixes different tests (RECONCILIATION.md 7.1, 7.2).

Definitions (EVIDENCE_VERSION pins them; change one -> bump the version):
  n_complete      rows whose 7 binding checks are all present
  d24             all 7 binding checks strictly PASS (R17); d24_rate = n_d24 / n_complete
  ge_0p8          sharpe >= 0.8 x that row's LOW_SHARPE limit; rate over rows that carry a limit
  *_wilson_lo95   Wilson score lower bound, z = 1.959964 -- a description of the counts, not a test
  n_fills         distinct fills; n_datasets = distinct datasets among the fill fields (slot_types)

What these numbers can NOT say (carried as CAVEATS in every evidence block's `caveats` version):
  C1 how often a frame was filled was decided by the generator that drew it (7.7), not by durability
  C2 the corpora are selected samples: climb_rescored is re-read candidates, resim keeps 11,726 of 69,448 (7.4)
  C3 the fills were not drawn at random from the compatible fields, so a rate describes those fills only
  C4 settings (universe, neutralization, decay) vary inside a cell and are unknown on 14,942 rows (7.3)
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import statistics

EVIDENCE_VERSION = 1
Z95 = 1.959964
CAVEATS = ("C1 fill counts measure allocation, not durability", "C2 corpora are selected samples",
           "C3 fills were not drawn at random", "C4 settings vary within a cell and are partly unknown")
VERDICTS = ("UNMEASURED", "ROBUST", "NOT_ROBUST", "INCONCLUSIVE")
ROUND_KEYS = ("round", "date", "cell", "n_fills", "comparison_arm", "effect", "source", "label")


def wilson_lower(k: int, n: int, z: float = Z95):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, round((c - m) / d, 4)) + 0.0


def _r4(x):
    return None if x is None else round(x, 4) + 0.0


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cell_stats(rows: list) -> dict:
    """The per-cell block from slim rows (see `_slim`)."""
    comp = [r for r in rows if r["n_missing"] == 0]
    nd24 = sum(1 for r in rows if r["d24"])
    wl = [r for r in rows if r["limit"] is not None]
    nge = sum(1 for r in wl if r["sharpe"] >= 0.8 * r["limit"])
    ratio = [r["sharpe"] / r["limit"] for r in wl if r["limit"]]
    tov = [r["turnover"] for r in rows if isinstance(r["turnover"], (int, float))]
    sv = collections.Counter(r["settings"] for r in rows)
    return {
        "n_rows": len(rows), "n_fills": len({r["fill"] for r in rows}),
        "n_datasets": len({d for r in rows for d in r["datasets"] if d}),
        "corpus_groups": dict(sorted(collections.Counter(r["group"] for r in rows).items())),
        "n_complete": len(comp), "n_d24": nd24,
        "d24_rate": _r4(nd24 / len(comp)) if comp else None, "d24_wilson_lo95": wilson_lower(nd24, len(comp)),
        "n_with_limit": len(wl), "n_ge_0p8": nge,
        "ge_0p8_rate": _r4(nge / len(wl)) if wl else None, "ge_0p8_wilson_lo95": wilson_lower(nge, len(wl)),
        "ratio_median": _r4(statistics.median(ratio)) if ratio else None,
        "turnover_median": _r4(statistics.median(tov)) if tov else None,
        "limits": dict(sorted(collections.Counter(str(r["limit"]) for r in wl).items())),
        "settings_top": [[k, v] for k, v in sorted(sv.items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
    }


def _slim(r: dict) -> dict:
    return {"cell": "%s/d%s" % ("?" if r["region"] is None else r["region"], "?" if r["delay"] is None else r["delay"]),
            "region": r["region"], "fill": tuple(r["fill"]),
            "datasets": [(t or {}).get("dataset") for t in (r.get("slot_types") or [])],
            "group": r["corpus_group"], "n_missing": r["n_binding_missing"], "d24": bool(r["d24"]),
            "sharpe": r["sharpe"], "limit": r["low_sharpe_limit"], "turnover": r.get("turnover"),
            "settings": "|".join(str(r.get(k)) for k in ("universe", "neutralization", "decay", "truncation")),
            "complete_settings": r.get("settings_src") == "row" and all(
                r.get(k) is not None for k in ("universe", "neutralization", "decay", "truncation")),
            "universe": r.get("universe"), "neutralization": r.get("neutralization"), "decay": r.get("decay"),
            "truncation": r.get("truncation")}


def collect(rows_path, wanted: dict) -> dict:
    """wanted: canonical key -> [(entry id, {canonical index: pinned field})]. One pass over the rows.
    Returns entry id -> [slim rows]."""
    out = collections.defaultdict(list)
    with open(rows_path) as fh:
        for line in fh:
            r = json.loads(line)
            targets = wanted.get(r["frame_key"])
            if not targets:
                continue
            for eid, pinned in targets:
                if all(r["fill"][i - 1] == f for i, f in pinned.items()):
                    out[eid].append(_slim(r))
    return dict(out)


def block(rows: list, source: dict) -> dict:
    """The evidence block of one frame from its slim rows."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    return {"evidence_version": EVIDENCE_VERSION, "label": "POST-HOC", "source": dict(source), "caveats": list(CAVEATS),
            "n_rows": len(rows), "n_fills": len({r["fill"] for r in rows}),
            "cells": {c: cell_stats(v) for c, v in sorted(by.items())},
            "reliability": {"verdict": "UNMEASURED", "method": None, "rounds": []}}


def modal_settings(rows: list) -> dict:
    """The most frequent complete (neutralization, decay, truncation), and the most frequent universe per
    region, among rows whose settings came from the row itself. A description of what was run."""
    comp = [r for r in rows if r["complete_settings"]]
    if not comp:
        return {"source": "none"}
    trip = collections.Counter((r["neutralization"], r["decay"], r["truncation"]) for r in comp)
    (neu, dec, tru), n = sorted(trip.items(), key=lambda kv: (-kv[1], repr(kv[0])))[0]
    uni = collections.defaultdict(collections.Counter)
    for r in comp:
        uni[r["region"]][r["universe"]] += 1
    return {"source": "canonical-modal", "n_rows": len(comp), "n_modal": n, "neutralization": neu, "decay": dec,
            "truncation": tru,
            "universe": {reg: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for reg, c in sorted(uni.items())}}
