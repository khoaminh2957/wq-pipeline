import json

from framelib import evidence as EV

BINDING = ["LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE", "CONCENTRATED_WEIGHT",
           "HIGH_TURNOVER", "LOW_TURNOVER"]


def row(key, fill, region="USA", delay=1, sharpe=1.0, limit=1.58, d24=False, missing=0, turnover=0.2, cond=(),
        settings=("TOP3000", "INDUSTRY", 4, 0.08), group="forge", datasets=None):
    binding = {b: ("PASS" if d24 else "FAIL") for b in BINDING}
    for b in BINDING[3:3 + missing]:
        binding[b] = None
    uni, neu, dec, tru = settings
    return {"corpus": group, "corpus_group": group, "alpha": "a%s" % abs(hash((key, tuple(fill), region, sharpe))),
            "frame_key": key, "fill": list(fill), "cond_fields": list(cond), "region": region, "delay": delay,
            "universe": uni, "neutralization": neu, "decay": dec, "truncation": tru,
            "settings_src": "row" if uni else "pyramid", "sharpe": sharpe, "turnover": turnover,
            "low_sharpe_limit": limit, "binding": binding, "d24": d24, "n_binding_fail": 0, "n_binding_missing": missing,
            "slot_types": [{"dataset": d} for d in (datasets or ["ds_" + f for f in fill])]}


def test_wilson_lower_bound():
    assert EV.wilson_lower(0, 0) is None
    assert EV.wilson_lower(0, 10) == 0.0
    assert EV.wilson_lower(5, 10) == 0.2366
    assert EV.wilson_lower(10, 10) == 0.7225


def test_collect_matches_key_and_pinned_positions(tmp_path):
    p = tmp_path / "rows.jsonl"
    rows = [row("rank(divide($1,$2))", ["a", "cap"]), row("rank(divide($1,$2))", ["b", "cap"]),
            row("rank(divide($1,$2))", ["a", "sales"]), row("rank($1)", ["a"])]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    got = EV.collect(p, {"rank(divide($1,$2))": [("E_pinned", {2: "cap"}), ("E_free", {})]})
    assert sorted(r["fill"] for r in got["E_pinned"]) == [("a", "cap"), ("b", "cap")]
    assert len(got["E_free"]) == 3 and "rank($1)" not in got


def test_block_counts_per_cell_and_never_pools(tmp_path):
    rs = [row("k", ["a"], d24=True), row("k", ["b"]), row("k", ["c"], missing=1),
          row("k", ["a"], region="JPN", sharpe=2.2, limit=2.69), row("k", ["b"], region="JPN", sharpe=2.0, limit=2.69)]
    p = tmp_path / "rows.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rs))
    b = EV.block(EV.collect(p, {"k": [("E", {})]})["E"], {"path": "x", "sha256": "y"})
    usa, jpn = b["cells"]["USA/d1"], b["cells"]["JPN/d1"]
    assert (usa["n_rows"], usa["n_complete"], usa["n_d24"], usa["d24_rate"]) == (3, 2, 1, 0.5)
    assert (usa["n_ge_0p8"], usa["ge_0p8_rate"]) == (0, 0.0)            # 1.0 < 0.8 x 1.58
    assert (jpn["n_ge_0p8"], jpn["limits"]) == (1, {"2.69": 2})         # 2.2 >= 0.8 x 2.69; 2.0 is not (it is vs 1.58)
    assert (b["n_rows"], b["n_fills"], b["label"]) == (5, 3, "POST-HOC")
    assert b["reliability"] == {"verdict": "UNMEASURED", "method": None, "rounds": []}
    assert usa["n_datasets"] == 3 and usa["corpus_groups"] == {"forge": 3}


def test_modal_settings_uses_only_complete_row_settings(tmp_path):
    rs = [row("k", ["a"]), row("k", ["b"]), row("k", ["c"], settings=("TOP1000", "SECTOR", 0, 0.05)),
          row("k", ["d"], settings=(None, None, None, None)), row("k", ["e"], region="EUR", settings=("TOP2500", "INDUSTRY", 4, 0.08))]
    p = tmp_path / "rows.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rs))
    m = EV.modal_settings(EV.collect(p, {"k": [("E", {})]})["E"])
    assert m == {"source": "canonical-modal", "n_rows": 4, "n_modal": 3, "neutralization": "INDUSTRY", "decay": 4,
                 "truncation": 0.08, "universe": {"EUR": "TOP2500", "USA": "TOP3000"}}
    assert EV.modal_settings([]) == {"source": "none"}
