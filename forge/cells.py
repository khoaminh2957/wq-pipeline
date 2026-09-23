"""forge.cells — which pyramid cells to aim at (C10 multi-region by EMPTY cells, C20 cells first).

A cell is (region, delay, category). The platform counter is the ONLY source of alphaCount
(memory: pyramid-cell-ev-targeting — book membership is not the counter). Inputs are files that
the existing crawlers already write; nothing here talks to the network.

  need       = max(0, UNLOCK_AT - alphaCount)          UNLOCK_AT = 3 (EX-ANTE, platform docs)
  weight     = need * multiplier * has_catalogue * has_hypothesis
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import NamedTuple

UNLOCK_AT = 3
_SEG_RE = re.compile(r"^([A-Z]+)_(.+)_d([01])$")


class Cell(NamedTuple):
    region: str
    delay: int
    category: str
    universe: str | None
    count: int
    need: int
    multiplier: float
    n_fields: int
    datasets: tuple           # (id, users) sorted quietest first
    weight: float


def load_pair_counts(path) -> dict:
    """{(region, delay): {category: alphaCount}} from state/pyramid_cell_counts.json.
    Accepts schema {"pairs": [{region, delay, counts}]} and {"by_pair": {"USA:1": {"counts"}}}."""
    art = json.load(open(path))
    out = {}
    if isinstance(art.get("pairs"), list):
        for p in art["pairs"]:
            out[(str(p["region"]), int(p["delay"]))] = {str(k): int(v) for k, v in p["counts"].items()}
    elif isinstance(art.get("by_pair"), dict):
        for key, p in art["by_pair"].items():
            region, delay = key.split(":")
            out[(region, int(delay))] = {str(k): int(v) for k, v in p["counts"].items()}
    else:
        raise ValueError("%s: neither 'pairs' nor 'by_pair'" % path)
    return out


def _name(x):
    return x.get("name") if isinstance(x, dict) else x


def load_survey(path) -> dict:
    """{(region, delay): {"universe": u, "categories": {cat: {"multiplier": m, "datasets": [(id, users), ...]}}}}
    from fetched/rc/datasets_survey.json (segment key REGION_UNIVERSE_dD -> list of dataset rows)."""
    art = json.load(open(path))
    out = {}
    for seg, rows in art.items():
        m = _SEG_RE.match(seg)
        if not m:
            continue
        region, universe, delay = m.group(1), m.group(2), int(m.group(3))
        if isinstance(rows, dict):
            rows = rows.get("results", [])
        cats = {}
        for r in rows:
            cat = _name(r.get("category"))
            if not cat:
                continue
            c = cats.setdefault(cat, {"multiplier": None, "datasets": []})
            if r.get("pyramidMultiplier") is not None:
                c["multiplier"] = float(r["pyramidMultiplier"])
            c["datasets"].append((r.get("id"), int(r.get("userCount") or 0)))
        for c in cats.values():
            c["datasets"].sort(key=lambda t: (t[1], t[0]))
        out[(region, delay)] = {"universe": universe, "categories": cats}
    return out


def catalogue_categories(fields_dir, region: str, delay: int, universe: str | None = None) -> dict:
    """{category: number of fields on disk} for one pair, from fetched/rc/fields/<seg>.jsonl.
    With no universe given, the file with the most rows for that pair is used."""
    fields_dir = pathlib.Path(fields_dir)
    cands = [fields_dir / ("%s_%s_d%d.jsonl" % (region, universe, delay))] if universe else \
        sorted(fields_dir.glob("%s_*_d%d.jsonl" % (region, delay)), key=lambda p: p.stat().st_size, reverse=True)
    counts = {}
    for p in cands:
        if not p.exists():
            continue
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    cat = _name(json.loads(line).get("category"))
                except ValueError:
                    continue
                if cat:
                    counts[cat] = counts.get(cat, 0) + 1
        break
    return counts


def rank_cells(pair_counts: dict, survey: dict, catalogues: dict, hypotheses=None) -> list:
    """Cells sorted by weight (desc), then need, then the quietest dataset. `catalogues` maps
    (region, delay) -> {category: n_fields}; `hypotheses` is a set of categories with at least one
    hypothesis, or None to skip that factor."""
    cells = []
    for (region, delay), counts in pair_counts.items():
        seg = survey.get((region, delay), {})
        cats_meta = seg.get("categories", {})
        cat_fields = catalogues.get((region, delay), {})
        for category, count in counts.items():
            need = max(0, UNLOCK_AT - int(count))
            meta = cats_meta.get(category, {})
            mult = meta.get("multiplier") or 1.0
            n_fields = int(cat_fields.get(category, 0))
            has_h = 1 if (hypotheses is None or category in hypotheses) else 0
            weight = need * mult * (1 if n_fields > 0 else 0) * has_h
            cells.append(Cell(region, delay, category, seg.get("universe"), int(count), need, mult,
                              n_fields, tuple(meta.get("datasets", [])), weight))
    cells.sort(key=lambda c: (-c.weight, -c.need, c.datasets[0][1] if c.datasets else 10 ** 9, c.region, c.category))
    return cells


def targets(root, hypotheses=None) -> list:
    root = pathlib.Path(root)
    counts = load_pair_counts(root / "state/pyramid_cell_counts.json")
    survey = load_survey(root / "fetched/rc/datasets_survey.json")
    cats = {pair: catalogue_categories(root / "fetched/rc/fields", pair[0], pair[1],
                                       survey.get(pair, {}).get("universe")) for pair in counts}
    return rank_cells(counts, survey, cats, hypotheses)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parents[1]))
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args(argv)
    cells = targets(a.root)
    open_cells = [c for c in cells if c.need > 0]
    print("cells: %d   empty (need>0): %d   reachable (weight>0): %d" % (
        len(cells), len(open_cells), sum(c.weight > 0 for c in cells)))
    for c in cells[:a.top]:
        q = ("%s(u%d)" % c.datasets[0]) if c.datasets else "-"
        print("%5.2f  %s/d%d %-14s count %d need %d mult %.1f fields %4d quietest %s" % (
            c.weight, c.region, c.delay, c.category, c.count, c.need, c.multiplier, c.n_fields, q))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
