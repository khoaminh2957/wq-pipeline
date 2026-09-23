#!/usr/bin/env python3
"""cell_targets.py -- what raw material exists behind each OPEN pyramid cell?

READ-ONLY, OFFLINE. Opens no socket. Never simulates, never submits.

THE QUESTION
------------
`tools/cell_map.py` answers "which cell does THIS alpha fill?". This module answers the
inverse, which is the one a generator needs: "for a cell that still needs alphas, what is
there to build from, and how much of it?"

THE JOIN, AND WHY IT IS NOT A GUESS
-----------------------------------
A pyramid cell is (region, delay, CATEGORY). A catalogue row carries `category.name`. That
those two are the SAME category is MEASURED, not assumed, and the measurement is
tools/cell_map.py R1/R2 -- 48/48 exact cell-set match against the platform's own
alpha["pyramids"], 94 memberships, and the membership sums reproduce
/users/self/activities/pyramid-alphas exactly in all 16 USA-d1 cells. This module inherits
that result; it does not re-establish it. Two cheap consistency checks are re-run here
because they are one line each and they would catch a catalogue swap:

  * the 16 category names in fetched/rc/fields/USA_TOP3000_d1.jsonl are set-IDENTICAL to the
    16 in state/pyramid_cell_counts.json["by_pair"]["USA:1"] (measured 2026-08-13);
  * every one of the 299 datasets in that catalogue carries exactly ONE field category, and
    it equals the dataset's own category in fetched/rc/datasets_USA_TOP3000_d1.jsonl
    (0 mixed datasets, 0 mismatches, measured 2026-08-13).
`assert_join_consistent()` is those two checks; `--check-join` runs them.

WHAT THE COUNTS MEAN, AND WHAT THEY DO NOT
------------------------------------------
`pairable_datasets` and `matrix_pairs` are counted under the CURRENT base-pool rules
(harness13/massgen/mg/base_pool.py: MATRIX-only operands, pairing WITHIN a dataset), so the
totals here are directly comparable to that module's own documented 192 / 295. Reproduced
here from the same catalogue: 192 datasets hold >= 2 MATRIX and 295 hold >= 2 of
(MATRIX|VECTOR). `matrix_pairs` is C(n,2) per dataset -- the DISTINCT unordered field pairs
available, an upper bound on two-field ratio bases, NOT a count of anything simulated.

NOTHING HERE PREDICTS A RETURN. A category with 127,387 available pairs is not thereby a
category whose alphas pass a gate. MECHANISM: UNKNOWN for every count in this file -- they
are catalogue arithmetic and nothing more. See CELL_TARGETS_R10.md for the separate,
measured question of whether open-cell signals actually pass, and for the R3 constraint
(an alpha predicted into >= 3 cells is credited in none) that caps what "aiming" can buy.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from cell_map import CATEGORY_ID  # noqa: E402  the 16 pyramid categories, sourced from the API

FIELDS_DIR = ROOT / "fetched/rc/fields"
DATASETS_DIR = ROOT / "fetched/rc"
PYRAMID_COUNTS = ROOT / "state/pyramid_cell_counts.json"

# A cell unlocks at 3 alphas and gains nothing after that (project note: pyramid-cell-ev-targeting).
UNLOCK_AT = 3


class JoinError(RuntimeError):
    """The catalogue and the pyramid disagree about what a category is. Fail, never guess."""


def load_catalogue(segment):
    """segment e.g. "USA_TOP3000_d1" -> list of field rows. Raises if the dump is absent."""
    path = FIELDS_DIR / f"{segment}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"no crawled catalogue at {path}")
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def pyramid_counts(region="USA", delay=1, path=PYRAMID_COUNTS):
    """{category: alphaCount} for one (region, delay), from the crawled platform counter."""
    art = json.load(open(path))
    key = f"{region}:{delay}"
    try:
        return dict(art["by_pair"][key]["counts"])
    except KeyError:
        raise JoinError(f"{path} holds no pair {key}")


def _cat(row):
    c = row.get("category")
    return c.get("name") if isinstance(c, dict) else c


def _dataset(row):
    d = row.get("dataset")
    return d.get("id") if isinstance(d, dict) else d


def assert_join_consistent(rows, counts, datasets_path=None):
    """The two one-line checks from the docstring. Returns a note; raises JoinError on failure."""
    cat_names = {_cat(r) for r in rows if _cat(r)}
    if cat_names != set(counts):
        raise JoinError(
            "catalogue categories and pyramid categories are not the same set; "
            f"catalogue-only={sorted(cat_names - set(counts))} "
            f"pyramid-only={sorted(set(counts) - cat_names)}")
    if not cat_names <= set(CATEGORY_ID):
        raise JoinError(f"unknown category name(s) {sorted(cat_names - set(CATEGORY_ID))}")

    per_dataset = collections.defaultdict(set)
    for r in rows:
        per_dataset[_dataset(r)].add(_cat(r))
    mixed = sorted(d for d, v in per_dataset.items() if len(v) > 1)
    if mixed:
        raise JoinError(f"{len(mixed)} dataset(s) carry more than one field category: {mixed[:5]}")

    note = f"{len(cat_names)} categories set-identical; {len(per_dataset)} datasets single-category"
    if datasets_path and pathlib.Path(datasets_path).exists():
        bad = []
        with open(datasets_path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                d = json.loads(line)
                own = next(iter(per_dataset.get(d["id"], {None})))
                if own is not None and own != _cat(d):
                    bad.append(d["id"])
        if bad:
            raise JoinError(f"{len(bad)} dataset(s) disagree with their fields' category: {bad[:5]}")
        note += "; dataset-catalogue agrees"
    return note


def inventory(rows):
    """{category: counts}. Pure catalogue arithmetic -- see the module docstring."""
    per_cat = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for r in rows:
        per_cat[_cat(r)][_dataset(r)][r.get("type")] += 1

    out = {}
    for cat, dsets in per_cat.items():
        matrix = {d: t["MATRIX"] for d, t in dsets.items()}
        both = {d: t["MATRIX"] + t["VECTOR"] for d, t in dsets.items()}
        out[cat] = {
            "datasets": len(dsets),
            "fields": sum(sum(t.values()) for t in dsets.values()),
            "matrix": sum(matrix.values()),
            "vector": sum(t["VECTOR"] for t in dsets.values()),
            # reachable under today's base_pool rules: >= 2 MATRIX fields in one dataset
            "pairable_datasets": sum(1 for n in matrix.values() if n >= 2),
            "matrix_pairs": sum(math.comb(n, 2) for n in matrix.values() if n >= 2),
            # what the vec_* exclusion costs, if that SPEC clause were ever lifted
            "pairable_datasets_mv": sum(1 for n in both.values() if n >= 2),
            "mv_pairs": sum(math.comb(n, 2) for n in both.values() if n >= 2),
        }
    return out


def targets(segment="USA_TOP3000_d1", region="USA", delay=1):
    """Inventory joined to the live cell counts, with the still-needed count per cell.

    `signals_per_needed` is pairable_datasets / alphas still needed -- distinct MECHANICS per
    alpha the cell still wants. Mechanics, not pairs, because one submission kills its whole
    signal family (project note: submittable-count-equals-distinct-mechanics), so the pair
    count overstates what a cell can actually absorb. It is a RATIO OF INVENTORY, not an
    estimate of yield: no term in it has ever been simulated.
    """
    rows = load_catalogue(segment)
    counts = pyramid_counts(region, delay)
    note = assert_join_consistent(rows, counts, DATASETS_DIR / f"datasets_{segment}.jsonl")
    inv = inventory(rows)

    out = {}
    for cat, have in counts.items():
        need = max(0, UNLOCK_AT - have)
        rec = dict(inv.get(cat, {"datasets": 0, "fields": 0, "matrix": 0, "vector": 0,
                                 "pairable_datasets": 0, "matrix_pairs": 0,
                                 "pairable_datasets_mv": 0, "mv_pairs": 0}))
        rec["have"] = have
        rec["need"] = need
        rec["open"] = need > 0
        rec["signals_per_needed"] = (rec["pairable_datasets"] / need) if need else None
        out[cat] = rec
    return {"segment": segment, "region": region, "delay": delay, "join": note, "cells": out}


def render(rep):
    cells = rep["cells"]
    lines = [f"segment {rep['segment']}  pyramid {rep['region']} d{rep['delay']}",
             f"join: {rep['join']}", ""]
    head = (f"{'':1}{'cell':16}{'have':>5}{'need':>5}{'ds':>5}{'fields':>8}{'MATRIX':>8}"
            f"{'VECTOR':>8}{'ds>=2M':>8}{'pairs':>10}{'mech/need':>11}")
    lines += [head, "-" * len(head)]
    order = sorted(cells, key=lambda c: (not cells[c]["open"], -cells[c]["pairable_datasets"]))
    for c in order:
        r = cells[c]
        ratio = "-" if r["signals_per_needed"] is None else f"{r['signals_per_needed']:.2f}"
        lines.append(f"{'*' if r['open'] else ' '}{c:16}{r['have']:>5}{r['need']:>5}"
                     f"{r['datasets']:>5}{r['fields']:>8}{r['matrix']:>8}{r['vector']:>8}"
                     f"{r['pairable_datasets']:>8}{r['matrix_pairs']:>10}{ratio:>11}")
    tot_pair = sum(r["pairable_datasets"] for r in cells.values())
    op = {c: r for c, r in cells.items() if r["open"]}
    lines += ["-" * len(head),
              f" {'ALL':16}{'':5}{sum(r['need'] for r in cells.values()):>5}"
              f"{sum(r['datasets'] for r in cells.values()):>5}"
              f"{sum(r['fields'] for r in cells.values()):>8}"
              f"{sum(r['matrix'] for r in cells.values()):>8}"
              f"{sum(r['vector'] for r in cells.values()):>8}{tot_pair:>8}"
              f"{sum(r['matrix_pairs'] for r in cells.values()):>10}",
              f" {'OPEN only':16}{'':5}{sum(r['need'] for r in op.values()):>5}"
              f"{sum(r['datasets'] for r in op.values()):>5}"
              f"{sum(r['fields'] for r in op.values()):>8}"
              f"{sum(r['matrix'] for r in op.values()):>8}"
              f"{sum(r['vector'] for r in op.values()):>8}"
              f"{sum(r['pairable_datasets'] for r in op.values()):>8}"
              f"{sum(r['matrix_pairs'] for r in op.values()):>10}",
              "",
              "* = cell still under %d alphas. 'pairs' = C(n,2) MATRIX pairs within a dataset;"
              % UNLOCK_AT,
              "  an upper bound on two-field bases, not a yield. mech/need = ds>=2M / need."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--segment", default="USA_TOP3000_d1")
    ap.add_argument("--region", default="USA")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-join", action="store_true",
                    help="run only the two join-consistency checks and exit")
    a = ap.parse_args(argv)
    if a.check_join:
        rows = load_catalogue(a.segment)
        note = assert_join_consistent(rows, pyramid_counts(a.region, a.delay),
                                      DATASETS_DIR / f"datasets_{a.segment}.jsonl")
        print("join OK:", note)
        return 0
    rep = targets(a.segment, a.region, a.delay)
    print(json.dumps(rep, indent=1) if a.json else render(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
