"""Fixtures: a small synthetic field library in the real file formats (field_labels.jsonl rows and a
REGION_UNIVERSE_dN catalogue), so the tests do not depend on the untracked 106 MB labels file."""
from __future__ import annotations

import json

import pytest

from framelib import fields as FL

VEC_AFTER = {"vec_avg": "score", "vec_max": "score", "vec_min": "score"}


def _label(fid, dataset, kind, unit, structure="MATRIX", sparsity="dense", sign="+", by_region=None, vec=False):
    regions = sorted(by_region) if by_region else ["USA/d1"]
    br = by_region or {"USA/d1": {"structure": structure, "coverage": 0.95 if sparsity == "dense" else 0.3,
                                  "sparsity": sparsity}}
    d = {"id": fid, "dataset": dataset, "category": "Test", "subcategory": "Test", "structure": structure,
         "domain": "test", "kind": kind, "unit": unit, "time": "daily", "horizon_d": None, "sparsity": sparsity,
         "coverage": 0.95, "crowding": "light", "users": 3, "sign": sign, "sign_source": "description",
         "directional": False, "description": "synthetic", "why": {}, "regions": regions, "by_region": br}
    if vec:
        d.update({"vec_role": "event-value", "vec_reducers": ["vec_avg", "vec_max", "vec_min"], "vec_after": VEC_AFTER,
                  "event_stream": "event"})
    return d


LABELS = [
    _label("f_level_a", "dsA", "level", "currency"),
    _label("f_level_b", "dsB", "level", "currency"),
    _label("f_level_c", "dsC", "level", "currency", sign="unstated"),
    _label("f_count", "dsB", "count", "count"),
    _label("f_ratio", "dsC", "ratio", "ratio"),
    _label("f_score", "dsC", "score", "score"),
    _label("f_sparse", "dsA", "level", "currency", sparsity="sparse"),
    _label("f_flag", "dsD", "flag", "bool"),
    _label("f_vec", "dsD", "score", "score", structure="VECTOR", vec=True),
    _label("f_region", "dsE", "level", "currency", by_region={
        "USA/d1": {"structure": "MATRIX", "coverage": 0.9, "sparsity": "dense"},
        "EUR/d1": {"structure": "VECTOR", "coverage": 0.9, "sparsity": "dense"}}),
    _label("volume", "pv1", "level", "shares"),
    _label("adv20", "pv1", "level", "shares"),
]


def _cat(fid, dataset, ftype, region="USA", universe="TOP3000", delay=1, users=5):
    return {"id": fid, "description": "synthetic", "dataset": {"id": dataset, "name": dataset},
            "category": {"id": "test", "name": "Test"}, "subcategory": {"id": "test", "name": "Test"},
            "region": region, "delay": delay, "universe": universe, "type": ftype, "dateCoverage": 1.0,
            "coverage": 0.9, "userCount": users, "alphaCount": 2, "pyramidMultiplier": 1.2, "themes": [],
            "_region": region, "_universe": universe, "_delay": delay}


@pytest.fixture(scope="session")
def meta_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("meta")
    with open(d / "field_labels.jsonl", "w") as fh:
        for row in LABELS:
            fh.write(json.dumps(row) + "\n")
    fd = d / "fields"
    fd.mkdir()
    usa = [_cat(l["id"], l["dataset"], l["structure"]) for l in LABELS]
    usa += [_cat("grp_x", "dsG", "GROUP"), _cat("industry", "dsG", "GROUP"), _cat("sym_x", "dsS", "SYMBOL"),
            _cat("f_unlabelled", "dsU", "MATRIX")]
    with open(fd / "USA_TOP3000_d1.jsonl", "w") as fh:
        for row in usa:
            fh.write(json.dumps(row) + "\n")
    with open(fd / "EUR_TOP2500_d1.jsonl", "w") as fh:
        for row in (_cat("f_region", "dsE", "VECTOR", "EUR", "TOP2500"), _cat("f_level_a", "dsA", "MATRIX", "EUR", "TOP2500")):
            fh.write(json.dumps(row) + "\n")
    return d


@pytest.fixture()
def fl(meta_dir):
    return FL.FieldLibrary.build(meta_dir / "field_labels.jsonl", meta_dir / "fields")
