import pathlib
import random
import re

import pytest

from forge import typed as TY
from framelib import compat as CM
from framelib import fields as FL
from framelib import frames as FR

REPO = pathlib.Path(__file__).resolve().parents[2]
CELL = "USA/d1"
SINGLE_SLOT = ["rank($1)", "rank(ts_delta($1,5))", "vec_avg($1)", "rank(ts_backfill($1,20))", "group_rank(rank(volume),$1)",
               "rank(divide(volume,$1))", "trade_when(greater(volume,adv20),rank($1),-1)", "multiply(rank($1),$1)",
               "ts_std_dev($1,20)", "if_else(greater(volume,1),rank($1),0.5)"]


def test_structurally_ok_is_the_call_forge_runner_makes():
    src = (REPO / "forge/runner.py").read_text()
    body = src[src.index("    def structurally_ok(cand) -> bool:"):]
    body = body[:body.index("\n    rng = ")]
    assert 'TY.judge(cand["formula"], struct_labels, "%s/d%s" % (st.get("region"), st.get("delay")), structural=True)' in body
    assert 'labels_path = pathlib.Path(root) / "fetched/rc/field_labels.jsonl"' in src
    assert "struct_labels = LB.load(labels_path)" in src
    assert FL.LABELS == REPO / "fetched/rc/field_labels.jsonl"
    ok, hard = CM.structurally_ok("rank(ts_delta(f_ratio,5))", {"f_ratio": {
        "kind": "ratio", "unit": "ratio", "sign": "+", "domain": "x", "time": "daily", "sparsity": "dense",
        "structure": "MATRIX"}}, "USA", 1)
    assert not ok and hard[0].startswith("H2")


@pytest.mark.parametrize("text", SINGLE_SLOT)
def test_rule_equals_the_gate_on_every_field_for_one_slot(fl, text):
    n = FR.normalize(text)
    adm = CM.admissible(n, 1, CELL, fl)
    fixed = set(n.cond_fields) | set(n.pinned.values())
    for f in sorted(fl.ids_in(CELL)):
        if f in fixed:
            continue
        gate = CM.structurally_ok(n.fill([f]), fl.labels, "USA", 1)[0]
        assert (fl.signature(f, CELL) in adm) == gate, (text, f)


def test_pool_excludes_fixed_fields_and_compatible_excludes_chosen(fl):
    n = FR.normalize("rank(subtract($1,$2))")
    assert "f_level_a" in [f for ids in CM.pool(n, 2, CELL, fl, {1: "f_level_a"}).values() for f in ids]
    comp = CM.compatible_fields(n, 2, CELL, fl, {1: "f_level_a"})
    assert comp == {"dsB": ["f_level_b"], "dsC": ["f_level_c"], "dsE": ["f_region"]}   # same unit, dense, not chosen
    n2 = FR.normalize("rank(divide(volume,$1))")
    assert all("volume" not in ids for ids in CM.pool(n2, 1, CELL, fl).values())


def test_a_stand_in_imposes_no_unit_on_the_probed_slot(fl):
    """$1 is a stand-in while $2 is probed; the divide's H1 refusal names the stand-in's marker unit, so
    it is dropped and $2 keeps every field a real $1 could pair with (and only a scale may divide)."""
    n = FR.normalize("rank(divide(subtract(ts_backfill($1,60),last_diff_value(ts_backfill($1,60),250)),$2))")
    ids = [f for v in CM.pool(n, 2, CELL, fl).values() for f in v]
    assert {"f_level_b", "f_count", "f_ratio"} <= set(ids) and "f_score" not in ids and "f_flag" not in ids
    assert CM.dead_reasons(n, fl, CELL) == []
    four = FR.normalize("multiply(group_rank(ts_mean(subtract($1,$2),5),industry),subtract(1,group_rank(ts_mean(divide($3,$4),10),sector)))")
    p2 = CM.pool(four, 2, CELL, fl, {1: "f_level_a"})          # $3, $4 stand-ins: no divide(1,1), no crash
    assert sorted(f for v in p2.values() for f in v) == ["f_level_a", "f_level_b", "f_level_c", "f_region"]
    assert "probe_errors" not in fl.memo


def test_a_probe_that_raises_is_counted_and_refuses_nothing(fl):
    n = FR.normalize("add(rank($1),rank(divide(2,1)))")         # typed raises on a constant-only divide
    adm = CM.admissible(n, 1, CELL, fl)
    assert fl.memo["probe_errors"]["IndexError"] >= 1
    assert adm == frozenset(fl.signatures(CELL))


def test_group_and_vector_slots(fl):
    g = FR.normalize("group_rank(rank(volume),$1)")
    assert CM.pool(g, 1, CELL, fl) == {}                        # unlabelled GROUP fields are refused by the gate
    v = FR.normalize("rank(vec_avg($1))")
    assert CM.compatible_fields(v, 1, CELL, fl) == {"dsD": ["f_vec"]}
    d = FR.normalize("if_else(less(rank(vec_stddev($1)),0.5),rank(vec_avg($1)),0.5)")
    assert CM.dead_reasons(d, fl, CELL) and "stand-in" in CM.dead_reasons(d, fl, CELL)[0]


LABELS_PRESENT = FL.LABELS.exists()


@pytest.mark.skipif(not LABELS_PRESENT, reason="fetched/rc/field_labels.jsonl is not in this checkout")
def test_a_real_field_and_its_signature_probe_get_the_same_verdict():
    """On 400 real USA/d1 fields: the gate's verdict and reasons are the same for the field and for a
    synthetic field carrying only its type signature -- the premise of the compatibility rule."""
    lib = FL.FieldLibrary.build(cells=[CELL])
    rng = random.Random(3)
    sample = rng.sample(sorted(lib.labels), 4000)
    sample = [f for f in sample if f in lib.ids_in(CELL)][:400]
    assert len(sample) >= 100
    for text in SINGLE_SLOT[:4] + ["add(rank($1),rank(ts_delta($1,20)))", "rank(divide($1,close))"]:
        n = FR.normalize(text)
        for f in sample:
            real = TY.judge(n.fill([f]), lib.labels, CELL, structural=True)
            lab = CM.probe_label(lib.signature(f, CELL))
            labels = {CM.PROBE: lab, "close": lib.labels["close"]}
            probe = TY.judge(n.fill([CM.PROBE]), labels, CELL, structural=True)
            strip = lambda hs, name: [re.sub(r"\b%s\b" % re.escape(name), "X", h) for h in hs]
            assert (real["ok"], strip(real["hard"], f)) == (probe["ok"], strip(probe["hard"], CM.PROBE)), (text, f)


@pytest.mark.skipif(not LABELS_PRESENT, reason="fetched/rc/field_labels.jsonl is not in this checkout")
def test_stripped_labels_judge_like_the_full_file():
    from forge import labels as LB
    full = LB.load(FL.LABELS)
    lib = FL.FieldLibrary.build(cells=[CELL])
    rng = random.Random(5)
    ids = [f for f in rng.sample(sorted(full), 3000) if CELL in full[f].get("regions", [])][:300]
    for f in ids:
        for text in ("rank(ts_delta($1,5))", "rank(vec_avg($1))", "rank(divide($1,close))"):
            s = FR.substitute(text, [f])
            assert TY.judge(s, full, CELL, structural=True) == TY.judge(s, lib.labels, CELL, structural=True)
