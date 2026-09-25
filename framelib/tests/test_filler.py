import pytest

from framelib import compat as CM
from framelib import fields as FL
from framelib import filler as FI
from framelib import frames as FR

CELL = "USA/d1"
ENTRY = {"id": "Fx", "version": 3, "text": "rank(subtract(ts_mean($1,20),$2))",
         "settings": {"source": "designer", "neutralization": "INDUSTRY", "decay": 4, "truncation": 0.08,
                      "universe": {"USA": "TOP3000"}}}


def test_same_seed_same_fills_even_with_a_fresh_library(fl, meta_dir):
    a = FI.fill(ENTRY, fl, CELL, 3, seed=1)
    b = FI.fill(ENTRY, fl, CELL, 3, seed=1)
    fresh = FL.FieldLibrary.build(meta_dir / "field_labels.jsonl", meta_dir / "fields")
    c = FI.fill(ENTRY, fresh, CELL, 3, seed=1)
    assert a["fills"] and a["fills"] == b["fills"] == c["fills"]


def test_different_seeds_draw_differently(fl):
    draws = {tuple(f["formula"] for f in FI.fill(ENTRY, fl, CELL, 2, seed=s)["fills"]) for s in range(8)}
    assert len(draws) > 1


@pytest.mark.parametrize("by", ["dataset", "field"])
def test_every_fill_passes_the_gate_and_reframes_to_its_frame(fl, by):
    for text in ("rank(subtract(ts_mean($1,20),$2))", "rank(divide($1,$2))", "trade_when(greater(volume,adv20),rank($1),-1)",
                 "add(rank(vec_avg($1)),rank(ts_delta($2,5)))"):
        n = FR.normalize(text)
        out = FI.fill(text, fl, CELL, 5, seed=2, by=by)
        assert out["fills"], (text, out)
        for f in out["fills"]:
            assert CM.structurally_ok(f["formula"], fl.labels, "USA", 1)[0]
            assert FR.frame_formula(f["formula"])[:2] == (n.key, n.key_fill(f["fill"]))
            assert len(set(f["fill"])) == len(f["fill"])
            assert not set(f["fill"]) & (set(n.cond_fields) | set(n.pinned.values()))


def test_settings_come_from_the_entry_and_the_cell_and_are_never_invented(fl):
    f = FI.fill(ENTRY, fl, CELL, 1, seed=1)["fills"][0]
    assert f["settings"] == {"region": "USA", "delay": 1, "universe": "TOP3000", "neutralization": "INDUSTRY",
                             "decay": 4, "truncation": 0.08}
    assert f["settings_complete"] is True and (f["frame_id"], f["frame_version"]) == ("Fx", 3)
    g = FI.fill("rank($1)", fl, CELL, 1, seed=1)["fills"][0]
    assert g["settings"]["universe"] is None and g["settings_complete"] is False
    h = FI.fill(ENTRY, fl, CELL, 1, seed=1, settings={"decay": 0})["fills"][0]
    assert h["settings"]["decay"] == 0


def test_dead_frames_say_why(fl):
    assert "absent in USA/d1" in FI.fill("trade_when(greater(nope_field,1),rank($1),-1)", fl, CELL, 3, seed=1)["dead"][0]
    assert FI.fill("group_rank(rank(volume),$1)", fl, CELL, 3, seed=1)["dead"] == ["$1 admits no field present in USA/d1"]
    assert FI.fill("rank(ts_delta(rank($1),5))", fl, CELL, 3, seed=1)["dead"] == ["H2 ts_delta on a score"]
    assert FI.fill("rank(ts_delta(divide($1,$2),5))", fl, CELL, 3, seed=1)["dead"] == ["H2 ts_delta on a ratio"]
    assert FI.fill("rank($1)", fl, "EUR/d1", 3, seed=1)["fills"]


def test_exclude_and_budget(fl):
    first = FI.fill("rank($1)", fl, CELL, 1, seed=4)["fills"][0]["formula"]
    again = FI.fill("rank($1)", fl, CELL, 3, seed=4, exclude=[first])
    assert first not in [f["formula"] for f in again["fills"]]
    small = FI.fill("rank(subtract($1,$2))", fl, CELL, 50, seed=1, max_attempts=10)
    assert small["attempts"] == 10 and len(small["fills"]) < 50
    assert sum(small["rejected"].values()) + len(small["fills"]) == 10
    with pytest.raises(ValueError):
        FI.fill("rank($1)", fl, CELL, 1, seed=1, by="nope")


def test_the_final_gate_decides_even_when_the_rule_is_too_wide(fl, monkeypatch):
    """compat's rule only ever widens (probe errors, stand-in artefacts); the filler must still refuse."""
    monkeypatch.setattr(CM, "admissible", lambda normal, k, cell, lib, chosen=None: frozenset(lib.signatures(cell)))
    out = FI.fill("rank(ts_delta($1,5))", fl, CELL, 20, seed=1, max_attempts=200)
    kinds = {fl.record(f["fill"][0], CELL)["kind"] for f in out["fills"]}
    assert out["fills"] and not kinds & {"ratio", "score", "flag"}
    assert any(k.startswith("gate: H2") for k in out["rejected"])


def test_a_fill_that_reframes_elsewhere_is_refused(fl, monkeypatch):
    """A condition field reused in a slot turns into a slot on re-framing: another frame, refused."""
    monkeypatch.setattr(CM, "pool", lambda *a, **kw: {"pv1": ["volume"]})
    out = FI.fill("trade_when(greater(volume,adv20),rank($1),-1)", fl, CELL, 3, seed=1, max_attempts=5)
    assert out["fills"] == [] and out["rejected"] == {"re-frames to another frame": 5}


def test_a_field_is_never_used_in_two_slots(fl, monkeypatch):
    monkeypatch.setattr(CM, "pool", lambda *a, **kw: {"dsA": ["f_level_a"]})
    out = FI.fill("rank(subtract($1,$2))", fl, CELL, 3, seed=1, max_attempts=4)
    assert out["fills"] == [] and out["rejected"] == {"field repeated in two slots": 4}


def test_declared_constraints_narrow_the_pool_and_unit_eq_holds(fl):
    entry = {"text": "add(rank(ts_mean($1,5)),rank($2))", "slots": [                  # the gate needs no unit match here
        {"slot": "$1", "context": "MATRIX", "positions": [], "constraints": {"datasets": ["dsA", "dsB"], "sparsity": ["dense"]}},
        {"slot": "$2", "context": "MATRIX", "positions": [], "constraints": {"exclude_datasets": ["dsB"], "unit_eq": "$1"}}]}
    out = FI.fill(entry, fl, CELL, 30, seed=3, max_attempts=100)
    assert out["fills"] and any(k.startswith("constraint unit_eq") for k in out["rejected"])
    for f in out["fills"]:
        a, b = (fl.record(x, CELL) for x in f["fill"])
        assert a["dataset"] in ("dsA", "dsB") and a["sparsity"] == "dense" and b["dataset"] != "dsB"
        assert a["unit"] == b["unit"]
    dead = FI.fill({"text": "rank($1)", "slots": [{"constraints": {"kind": ["nope"]}}]}, fl, CELL, 3, seed=1)
    assert dead["dead"] == ["$1 admits no field present in USA/d1 under its constraints"]
