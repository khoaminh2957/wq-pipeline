"""The field library: one typed record per (field, cell), built from the two metadata sources.

  fetched/rc/field_labels.jsonl   the typed vocabulary (forge/labels.py): dataset, kind, unit, time, sign,
                                  crowding, users, coverage / sparsity / structure per region
  fetched/rc/fields/*.jsonl       the platform catalogues, one file per REGION_UNIVERSE_dN: which fields
                                  exist in a cell and universe, their coverage, userCount, alphaCount,
                                  pyramidMultiplier, and the GROUP fields that field_labels does not carry

A CELL is "REGION/dN" (forge/signature.py's definition, FRAME SPEC v1 R13). The catalogue is the
authority on presence; field_labels on type. A catalogue field without a label is UNLABELLED; the
structural gate treats such a field as unknown (forge/typed.py `_leaf`). Catalogue rows of type SYMBOL /
UNIVERSE and the RESERVED group-token names are left out and counted in `excluded`.

A field's TYPE SIGNATURE in a cell is the tuple of label values the structural gate reads, as the gate
reads them for that cell (typed `_leaf` overlays by_region). Two fields with one signature are
indistinguishable to structurally_ok; tests/test_compat.py checks that on real fields.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LABELS = ROOT / "fetched/rc/field_labels.jsonl"
FIELDS_DIR = ROOT / "fetched/rc/fields"
KEEP_TYPES = ("MATRIX", "VECTOR", "GROUP")
LABEL_KEYS = ("dataset", "category", "subcategory", "domain", "kind", "unit", "time", "sparsity", "structure",
              "coverage", "crowding", "users", "sign", "sign_source", "directional", "regions", "by_region",
              "vec_role", "vec_reducers", "vec_after")
UNLABELLED = ("UNLABELLED",)
# Catalogue GROUP fields named like a group token: the parser and the judge read these names as tokens
# (FRAME SPEC v1 R11; forge.typed.GROUPS adds currency), so they are frame text, never a slot's field.
RESERVED = frozenset({"sector", "industry", "subindustry", "market", "country", "exchange", "currency"})


def cell_of(region, delay) -> str:
    return "%s/d%s" % (region, delay)


def parse_cell(cell: str) -> tuple:
    region, d = cell.split("/")
    return region, int(d[1:])


def _file_cell(path) -> str:
    parts = os.path.basename(path)[:-len(".jsonl")].split("_")
    return cell_of(parts[0], parts[-1][1:])


class FieldLibrary:
    def __init__(self, labels: dict, catalogue: dict, excluded: dict | None = None, sources: dict | None = None):
        self.labels = labels                  # id -> label (LABEL_KEYS only)
        self.catalogue = catalogue            # cell -> id -> catalogue entry
        self.excluded = dict(excluded or {})  # catalogue rows skipped, by type
        self.sources = dict(sources or {})
        self._index = {}
        self.memo = {}                        # framelib.compat's per-library cache

    @classmethod
    def build(cls, labels_path=LABELS, fields_dir=FIELDS_DIR, cells=None) -> "FieldLibrary":
        """`cells`: read only these cells' catalogues (the labels are always read whole)."""
        labels = {}
        with open(labels_path) as fh:
            for line in fh:
                j = json.loads(line)
                labels[j["id"]] = {k: j[k] for k in LABEL_KEYS if k in j}
        catalogue, excluded = collections.defaultdict(dict), collections.Counter()
        files = sorted(glob.glob(os.path.join(str(fields_dir), "*.jsonl")))
        for path in files:
            cell = _file_cell(path)
            if cells is not None and cell not in cells:
                continue
            with open(path) as fh:
                for line in fh:
                    r = json.loads(line)
                    if r.get("type") not in KEEP_TYPES:
                        excluded[r.get("type")] += 1
                        continue
                    if r["id"] in RESERVED:
                        excluded["reserved name"] += 1
                        continue
                    e = catalogue[cell].get(r["id"])
                    if e is None:
                        e = catalogue[cell][r["id"]] = {
                            "type": r["type"], "dataset": (r.get("dataset") or {}).get("id"),
                            "category": (r.get("category") or {}).get("name"), "universes": {}, "users": 0,
                            "alphas": 0, "pyramid_multiplier": None}
                    e["universes"][r.get("universe")] = r.get("coverage")
                    e["users"] = max(e["users"], r.get("userCount") or 0)
                    e["alphas"] = max(e["alphas"], r.get("alphaCount") or 0)
                    if r.get("pyramidMultiplier") is not None:
                        e["pyramid_multiplier"] = max(e["pyramid_multiplier"] or 0, r["pyramidMultiplier"])
        return cls(labels, dict(catalogue), excluded,
                   {"labels": str(labels_path), "fields_dir": str(fields_dir), "catalogues": [os.path.basename(p) for p in files]})

    # ---- presence and records
    def cells(self) -> list:
        return sorted(self.catalogue)

    def ids_in(self, cell) -> dict:
        return self.catalogue.get(cell, {})

    def record(self, fid: str, cell: str) -> dict | None:
        """The typed record of one field in one cell (None when the field is not in the cell)."""
        cat = self.ids_in(cell).get(fid)
        if cat is None:
            return None
        lab = self.labels.get(fid)
        rec = {"id": fid, "cell": cell, "catalogue_type": cat["type"], "dataset": cat["dataset"],
               "category": cat["category"], "universes": sorted(cat["universes"]),
               "catalogue_coverage": cat["universes"], "catalogue_users": cat["users"], "alphas": cat["alphas"],
               "pyramid_multiplier": cat["pyramid_multiplier"], "labelled": lab is not None}
        if lab is not None:
            br = (lab.get("by_region") or {}).get(cell) or {}
            rec.update({k: lab.get(k) for k in ("subcategory", "domain", "kind", "unit", "time", "sign", "sign_source",
                                                "directional", "crowding", "users", "vec_role", "vec_reducers")})
            rec.update({"structure": br.get("structure", lab.get("structure")),
                        "coverage": br.get("coverage", lab.get("coverage")),
                        "sparsity": br.get("sparsity", lab.get("sparsity"))})
        else:
            rec.update({"kind": "group" if cat["type"] == "GROUP" else None, "structure": cat["type"]})
        return rec

    def signature(self, fid: str, cell: str) -> tuple:
        lab = self.labels.get(fid)
        if lab is None:
            return UNLABELLED
        br = (lab.get("by_region") or {}).get(cell) or {}
        vr, va = lab.get("vec_reducers"), lab.get("vec_after")
        return (br.get("structure", lab["structure"]), br.get("sparsity", lab["sparsity"]), lab["kind"], lab["unit"],
                tuple(vr) if vr else None, tuple(sorted(va.items())) if va else None)

    def index(self, cell) -> dict:
        """signature -> dataset -> sorted field ids, for the fields present in `cell`."""
        if cell not in self._index:
            idx = collections.defaultdict(lambda: collections.defaultdict(list))
            for fid, cat in self.ids_in(cell).items():
                idx[self.signature(fid, cell)][cat["dataset"] or "?"].append(fid)
            self._index[cell] = {s: {d: sorted(ids) for d, ids in by.items()} for s, by in idx.items()}
        return self._index[cell]

    def signatures(self, cell) -> list:
        return sorted(self.index(cell), key=repr)
