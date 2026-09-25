"""framelib.loop.newframes: the day's new candidate frames (F8), on a small synthetic field library.

Nothing here simulates or touches the network. The field library is written in the real file formats
(framelib/tests/conftest.py's helpers): six datasets of 12 level/currency fields (dsA..dsF), a one-field
dataset (dsOne), two condition fields (dsQ), and a dataset the platform does not offer "today" (dsGone: in the
catalogue, not in datasets_ok.json).
"""
from __future__ import annotations

import itertools
import json
import os
import pathlib
import random
import subprocess
import sys

import pytest

from forge import typed as TY
from framelib import compat as CM
from framelib import evidence as EV
from framelib import frames as FR
from framelib import schema as SC
from framelib import store as ST
from framelib import taxonomy as TX
from framelib.experiments import round1 as R1
from framelib.fields import FieldLibrary
from framelib.loop import newframes as NF
from framelib.tests import conftest as CF

REPO = pathlib.Path(__file__).resolve().parents[2]
DAY, NEXT_DAY = "2026-09-25", "2026-09-26"
NOW = "2026-09-25T08:00:00+00:00"
BUILT = "2026-09-24T08:00:00+00:00"
SRC = [{"kind": "test", "path": "t.jsonl", "sha256": "ab" * 32, "ref": "line 1"}]
DS = ("dsA", "dsB", "dsC", "dsD", "dsE", "dsF")
OFFERED = DS + ("dsOne", "dsQ")
P1, P2 = "greater(rank(cond_q1),0.5)", "less(rank(cond_q2),0.3)"
WIN = "rank(ts_mean($1,20))"
SPREAD = "subtract(ts_zscore($1,60),group_neutralize(ts_zscore($1,60),industry))"
COND1 = "if_else(%s,group_rank(ts_mean($1,5),industry),0)" % P1
COND2 = "if_else(%s,rank($1),0.5)" % P2
PROD = "multiply(rank($1),rank(ts_mean($2,20)))"
OPS = "rank(ts_delta(ts_mean($1,10),5))"
MIX = [WIN, SPREAD, COND1, COND2, PROD, OPS, "rank(ts_zscore($1,120))", "group_rank(ts_mean($1,60),sector)",
       "rank(ts_std_dev($1,20))"]


def write_meta(d: pathlib.Path) -> pathlib.Path:
    labels = [CF._label("%s_f%02d" % (ds.lower(), i), ds, "level", "currency") for ds in DS for i in range(12)]
    labels += [CF._label("one_lvl", "dsOne", "level", "currency")]
    labels += [CF._label("gone_f%02d" % i, "dsGone", "level", "currency") for i in range(12)]
    labels += [CF._label("cond_q1", "dsQ", "level", "currency"), CF._label("cond_q2", "dsQ", "level", "currency")]
    (d / "field_labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))
    (d / "fields").mkdir(exist_ok=True)
    (d / "fields" / "USA_TOP3000_d1.jsonl").write_text(
        "".join(json.dumps(CF._cat(x["id"], x["dataset"], "MATRIX")) + "\n" for x in labels))
    (d / "datasets_ok.json").write_text(json.dumps(list(OFFERED)))
    (d / "selection.json").write_text(json.dumps({"dropped_mined": []}))
    return d


@pytest.fixture(scope="module")
def meta(tmp_path_factory):
    return write_meta(tmp_path_factory.mktemp("newframes_meta"))


def field_lib(meta) -> FieldLibrary:
    return FieldLibrary.build(meta / "field_labels.jsonl", meta / "fields")


def canonical(n_rows=4):
    cell = {"n_rows": n_rows, "n_fills": n_rows, "n_datasets": 1, "corpus_groups": {"forge": n_rows},
            "n_complete": n_rows, "n_d24": 0, "d24_rate": 0.0, "d24_wilson_lo95": EV.wilson_lower(0, n_rows),
            "n_with_limit": n_rows, "n_ge_0p8": 1, "ge_0p8_rate": round(1 / n_rows, 4),
            "ge_0p8_wilson_lo95": EV.wilson_lower(1, n_rows), "ratio_median": 0.4, "turnover_median": 0.2,
            "limits": {"1.58": n_rows}, "settings_top": []}
    return {"evidence_version": EV.EVIDENCE_VERSION, "label": "POST-HOC", "source": {"path": "rows", "sha256": "cd" * 32},
            "caveats": list(EV.CAVEATS), "n_rows": n_rows, "n_fills": n_rows, "cells": {"USA/d1": cell},
            "reliability": {"verdict": "UNMEASURED", "method": None, "rounds": []}}


def ent(text, cons=None, mined=False):
    specs = {k: {"constraints": c} for k, c in enumerate(cons or [], 1) if c}
    return SC.new_entry(text, sources=SRC, built_by="test", built_at=BUILT, slot_specs=specs,
                        evidence=canonical() if mined else None)


def make_lib(root, entries):
    for e in entries:
        ST.save(e, root)
    ST.write_index(list(ST.read_all(root).values()), root)
    return {e["id"]: e for e in entries}


def run(meta, root, n, *, seed=7, day=DAY, dropped=(), hist=None, corpus=(), dry=False):
    return NF.run(n, seed=seed, day=day, now=NOW, root=root, fl=field_lib(meta), datasets_ok=meta / "datasets_ok.json",
                  hist=hist or {}, corpus=set(corpus), dropped=list(dropped), dropped_ids=meta / "selection.json",
                  dry_run=dry)


def only_kinds(monkeypatch, *kinds):
    monkeypatch.setattr(NF, "MUTATIONS", kinds)


def texts(cands):
    return sorted(c["text"] for c in cands)


def dataset_of(f):
    return ("dsOne" if f == "one_lvl" else "dsGone" if f.startswith("gone_") else "dsQ" if f.startswith("cond_")
            else "ds" + f[2].upper())


def assert_fillable(meta, added):
    """Every added frame's recorded fills: structurally_ok, re-frame to the frame, fields offered today, and
    pairwise disjoint fields."""
    fl = field_lib(meta)
    for a in added:
        nm = FR.normalize(a["text"])
        assert len(a["fills"]) == NF.MIN_FILLS
        for x, y in itertools.combinations(a["fills"], 2):
            assert not set(x) & set(y), (a["id"], x, y)
        for fill in a["fills"]:
            formula = nm.fill(fill)
            assert CM.structurally_ok(formula, fl.labels, "USA", 1)[0], formula
            assert FR.frame_formula(formula)[0] == nm.key
            assert all(dataset_of(f) in OFFERED for f in fill), fill


# ---- the mutation operators, on frame text alone -------------------------------------------------------

def _e(text):
    return {"id": SC.frame_id(FR.normalize(text).text), "text": text}


def test_window_moves_one_site_to_the_nearest_ladder_rungs_and_identical_subtrees_move_together():
    got = NF.window_mutations(_e(WIN), FR.normalize(WIN))
    assert texts(got) == ["rank(ts_mean($1,10))", "rank(ts_mean($1,60))"]
    got = NF.window_mutations(_e(SPREAD), FR.normalize(SPREAD))
    assert texts(got) == ["subtract(ts_zscore($1,120),group_neutralize(ts_zscore($1,120),industry))",
                          "subtract(ts_zscore($1,20),group_neutralize(ts_zscore($1,20),industry))"]
    assert {c["mutation"]["sites"] for c in got} == {2}
    got = NF.window_mutations(_e(OPS), FR.normalize(OPS))              # two different sites: one changes at a time
    assert texts(got) == ["rank(ts_delta(ts_mean($1,10),10))", "rank(ts_delta(ts_mean($1,20),5))",
                          "rank(ts_delta(ts_mean($1,5),5))"]
    for keep in ("rank(ts_backfill($1,60))", "rank(ts_delay($1,20))"):   # d bounds a fill / is a lag
        assert NF.window_mutations(_e(keep), FR.normalize(keep)) == []


def test_a_slot_free_condition_changes_only_whole():
    t = "if_else(greater(ts_mean(cond_q1,20),ts_mean(cond_q2,60)),rank(ts_mean($1,20)),0.5)"
    assert texts(NF.window_mutations(_e(t), FR.normalize(t))) == [
        "if_else(greater(ts_mean(cond_q1,20),ts_mean(cond_q2,60)),rank(ts_mean($1,10)),0.5)",
        "if_else(greater(ts_mean(cond_q1,20),ts_mean(cond_q2,60)),rank(ts_mean($1,60)),0.5)"]
    assert texts(NF.opswap_mutations(_e(t), FR.normalize(t))) == [
        "if_else(greater(ts_mean(cond_q1,20),ts_mean(cond_q2,60)),rank(ts_decay_linear($1,20)),0.5)"]
    g = "if_else(greater(group_rank(cond_q1,industry),0.5),group_rank($1,sector),0)"
    assert texts(NF.group_mutations(_e(g), FR.normalize(g))) == [
        "if_else(greater(group_rank(cond_q1,industry),0.5),group_rank($1,industry),0)",
        "if_else(greater(group_rank(cond_q1,industry),0.5),group_rank($1,subindustry),0)"]
    # a condition that holds a slot: its window may move, its operator is never swapped
    s = "if_else(greater(ts_zscore($1,20),0),rank($1),0.5)"
    assert texts(NF.window_mutations(_e(s), FR.normalize(s))) == ["if_else(greater(ts_zscore($1,10),0),rank($1),0.5)",
                                                                  "if_else(greater(ts_zscore($1,60),0),rank($1),0.5)"]
    assert NF.opswap_mutations(_e(s), FR.normalize(s)) == []


def test_group_tokens_move_among_the_gics_groups():
    got = NF.group_mutations(_e(SPREAD), FR.normalize(SPREAD))
    assert texts(got) == ["subtract(ts_zscore($1,60),group_neutralize(ts_zscore($1,60),sector))",
                          "subtract(ts_zscore($1,60),group_neutralize(ts_zscore($1,60),subindustry))"]


def test_every_swap_set_is_one_taxonomy_role_with_the_same_positional_arguments():
    fn = {op: name for name, ops in TX.FUNCTION_OPS for op in ops}
    for role, ops in NF.SWAP_GROUPS.items():
        functions = {fn.get(op, "LEVEL") for op in ops}
        assert len(functions) == 1, (role, functions)
        if functions == {"LEVEL"}:
            assert set(ops) <= TY.SMOOTH or set(ops) <= (TY.SCORE01 | TY.ZSCORE), role
        assert len({FR.WINDOW_ARG.get(op) for op in ops}) == 1, role
        assert len({FR.GROUP_ARGS.get(op) for op in ops}) == 1, role


def test_an_operator_swap_keeps_the_frame_family_and_skips_keyword_calls():
    got = NF.opswap_mutations(_e(OPS), FR.normalize(OPS))
    assert texts(got) == ["rank(ts_av_diff(ts_mean($1,10),5))", "rank(ts_delta(ts_decay_linear($1,10),5))",
                          "rank(ts_min_diff(ts_mean($1,10),5))"]
    fam = TX.classify(FR.normalize(OPS))["family"]
    assert {TX.classify(FR.normalize(c["text"]))["family"] for c in got} == {fam}
    kw = "rank(ts_rank($1,20,constant=0))"
    assert NF.opswap_mutations(_e(kw), FR.normalize(kw)) == []


def test_presets_are_one_sided_slot_free_compares_on_fields_offered_today(meta):
    fl = field_lib(meta)
    R1.restrict(fl, set(OFFERED), None)
    lib = [ent(COND1), ent(COND2), ent("if_else(greater(ts_mean(cond_q1,20),ts_mean(cond_q2,60)),rank($1),0.5)"),
           ent("if_else(greater(rank(gone_f00),0.5),rank($1),0.5)"), ent("if_else(greater(rank($1),0.5),rank($1),0.5)")]
    pre = NF.presets(lib, fl)
    assert sorted(pre) == sorted([P1, P2])
    assert pre[P1] == [SC.frame_id(FR.normalize(COND1).text)]


def test_condition_add_wraps_an_unconditioned_frame_and_replace_swaps_a_slot_free_condition():
    pre = {P1: ["Fa"], P2: ["Fb"]}
    add = NF.condition_mutations(_e(WIN), FR.normalize(WIN), pre)
    assert texts(add) == ["if_else(%s,%s,0.5)" % (p, WIN) for p in sorted(pre)]      # rank root: a [0, 1] score
    assert {c["preset_from"][0] for c in add} == {"Fa", "Fb"}
    add = NF.condition_mutations(_e(PROD), FR.normalize(PROD), pre)
    assert texts(add) == ["if_else(%s,%s,0)" % (p, PROD) for p in sorted(pre)]
    rep = NF.condition_mutations(_e(COND1), FR.normalize(COND1), pre)
    assert texts(rep) == [COND1.replace(P1, P2)]
    assert rep[0]["mutation"] == {"kind": "condition", "action": "replace", "from": P1, "to": P2, "preset_from": ["Fb"]}
    held = "trade_when(%s,rank($1),greater(rank(cond_q2),0.9))" % P1            # the exit holds a field
    assert NF.condition_mutations(_e(held), FR.normalize(held), pre) == []
    free = "trade_when(%s,rank($1),reverse(1))" % P1                              # -1 in the normal form
    assert texts(NF.condition_mutations(_e(free), FR.normalize(free), pre)) == [free.replace(P1, P2)]


def test_combine_multiplies_two_frames_legs_and_carries_their_slot_roles():
    a = ent(PROD)
    b = ent("rank(divide($1,$2))", cons=[{"unit_eq": "$2"}, {"unit_eq": "$1"}])
    normals = {e["id"]: FR.normalize(e["text"]) for e in (a, b)}
    got = NF.combine_pair(a, b, normals)
    assert texts(got) == ["multiply(rank($1),rank(divide($3,$4)))", "multiply(rank(ts_mean($2,20)),rank(divide($3,$4)))"]
    c = next(x for x in got if x["text"].startswith("multiply(rank(ts_mean"))
    nm2 = FR.normalize(c["text"])
    assert NF.slot_specs(c, nm2, [a["slots"], b["slots"]]) == {2: {"constraints": {"unit_eq": "$3"}},
                                                               3: {"constraints": {"unit_eq": "$2"}}}
    # a unit_eq whose partner slot is not in the new frame is dropped
    a2 = ent("multiply(rank($1),rank(ts_mean($2,5)))", cons=[None, {"unit_eq": "$1", "datasets": ["dsA"]}])
    normals[a2["id"]] = FR.normalize(a2["text"])
    c = next(x for x in NF.combine_pair(a2, b, normals) if x["text"].startswith("multiply(rank(ts_mean"))
    assert NF.slot_specs(c, FR.normalize(c["text"]), [a2["slots"], b["slots"]])[1] == {"constraints": {"datasets": ["dsA"]}}
    # two legs of one structure are not paired
    d = ent("multiply(rank($1),rank(ts_delta($2,5)))")
    normals[d["id"]] = FR.normalize(d["text"])
    assert texts(NF.combine_pair(a, d, normals)) == ["multiply(rank($1),rank(ts_delta($4,5)))",
                                                     "multiply(rank(ts_mean($2,20)),rank($3))",
                                                     "multiply(rank(ts_mean($2,20)),rank(ts_delta($4,5)))"]


def test_a_pair_is_combined_in_id_order_whatever_the_shuffle():
    a, b = ent(WIN), ent("rank(ts_delta($1,5))")
    normals = {e["id"]: FR.normalize(e["text"]) for e in (a, b)}
    seen = set()
    for seed in range(10):
        for c in NF.candidates("combine", [a, b], normals, {}, random.Random(seed), set(), set()):
            assert [e["id"] for e in c["parents"]] == sorted([a["id"], b["id"]])
            seen.add(c["text"])
    assert len(seen) == 1                      # never the product and its commuted copy


# ---- the call ----------------------------------------------------------------------------------------------

def test_the_dropped_mined_frames_go_first_in_id_order_on_their_historic_datasets(meta, tmp_path):
    make_lib(tmp_path, [ent(t) for t in MIX])
    dropped = sorted((ent("rank(ts_mean($1,%d))" % w, mined=True) for w in (3, 7, 9, 11)), key=lambda e: e["id"])
    hist = {e["canonical_key"]: {"slot_ds": [{"dsB"}], "slot_fields": [{"dsb_f00"}], "fills": {("dsb_f00",)}}
            for e in dropped}
    make_lib(tmp_path, [dropped[1]])                                     # already in the library: skipped
    rep = run(meta, tmp_path, 7, dropped=dropped, hist=hist, corpus={e["canonical_key"] for e in dropped})
    got = [a for a in rep["added"] if a["origin"] == "mined-dropped"]
    assert [a["id"] for a in got] == [dropped[0]["id"], dropped[2]["id"], dropped[3]["id"]]
    assert [a["kind"] for a in rep["added"]][:3] == ["mined-dropped"] * 3
    assert rep["rejected"]["mined-dropped: already in the library"] == 1
    for a in got:
        assert all(f.startswith("dsb_") for fill in a["fills"] for f in fill) and ["dsb_f00"] not in a["fills"]
        e = ST.read_all(tmp_path)[a["id"]]
        pv = e["provenance"]
        assert (pv["origin"], pv["parents"], pv["mutation"], pv["cohort_day"]) == ("mined-dropped", [], None, DAY)
        assert pv["sources"][-1] == {"kind": "mined-dropped", "path": str(meta / "selection.json"),
                                     "sha256": EV.sha256(meta / "selection.json"), "ref": "dropped_mined"}
        assert e["status_history"][-1]["by"] == NF.BUILT_BY and e["evidence"]["n_rows"] == 4
    assert_fillable(meta, rep["added"])


def test_the_mutation_kinds_take_turns(meta, tmp_path):
    make_lib(tmp_path, [ent(t) for t in MIX])
    rep = run(meta, tmp_path, 5)
    assert [a["kind"] for a in rep["added"]] == list(NF.MUTATIONS)
    assert len({p for a in rep["added"] for p in a["parents"]}) == 6          # a parent gives one frame per call
    assert_fillable(meta, rep["added"])


def test_a_mutation_must_have_a_canonical_key_new_to_the_library(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "window")
    monkeypatch.setattr(NF, "WINDOW_LADDER", (5, 10))
    lib = make_lib(tmp_path, [ent("rank(ts_mean($1,5))"), ent("rank(ts_mean($1,10))")])
    rep = run(meta, tmp_path, 2)
    assert rep["added"] == [] and rep["rejected"] == {"window: canonical key in the library": 2}
    assert sorted(ST.read_all(tmp_path)) == sorted(lib)


def test_a_mutation_must_have_a_canonical_key_new_to_the_corpus(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "window")
    monkeypatch.setattr(NF, "WINDOW_LADDER", (5, 10))
    make_lib(tmp_path, [ent("rank(ts_mean($1,5))")])
    rep = run(meta, tmp_path, 1, corpus={"rank(ts_mean($1,10))"})
    assert rep["added"] == [] and rep["rejected"] == {"window: canonical key in the canonical corpus": 1}


def test_two_parents_that_mutate_into_one_frame_give_it_once(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "window")
    monkeypatch.setattr(NF, "WINDOW_LADDER", (5, 10, 20))
    make_lib(tmp_path, [ent("rank(ts_mean($1,5))"), ent("rank(ts_mean($1,20))")])
    rep = run(meta, tmp_path, 2)
    assert [a["text"] for a in rep["added"]] == ["rank(ts_mean($1,10))"]
    assert rep["rejected"] == {"window: canonical key made earlier in this call": 1}


def test_fills_come_only_from_datasets_offered_today(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "window")
    gone, kept = ent(WIN, cons=[{"datasets": ["dsGone"]}]), ent("rank(ts_mean($1,120))", cons=[{"datasets": ["dsA"]}])
    make_lib(tmp_path, [gone])
    rep = run(meta, tmp_path, 1)
    assert rep["added"] == [] and rep["rejected"] == {"window: fewer than 3 disjoint fills today": 1}
    make_lib(tmp_path, [kept])
    rep = run(meta, tmp_path, 1)
    assert [a["parents"] for a in rep["added"]] == [[kept["id"]]]
    assert all(f.startswith("dsa_") for fill in rep["added"][0]["fills"] for f in fill)
    assert_fillable(meta, rep["added"])


def test_the_three_fills_use_disjoint_fields_and_one_short_candidate_ends_its_parents_group(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "window")
    t = "rank(subtract(ts_mean($1,20),ts_mean($2,20)))"          # two window sites: four candidates
    make_lib(tmp_path, [ent(t, cons=[{"datasets": ["dsOne"]}, None])])   # slot 1 has one field
    rep = run(meta, tmp_path, 1)
    assert rep["added"] == [] and rep["rejected"] == {"window: fewer than 3 disjoint fills today": 1}
    assert rep["groups_spent"] == 1 and rep["checks"] == 1 and rep["exhausted"] == ["window"]
    make_lib(tmp_path, [ent(t.replace("20", "120"), cons=[{"datasets": ["dsA"]}, None])])
    rep = run(meta, tmp_path, 1)
    assert len(rep["added"]) == 1
    assert_fillable(meta, rep["added"])


def test_a_frame_the_structural_gate_refuses_is_not_filed(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "combine")
    lib = make_lib(tmp_path, [ent(WIN), ent("ts_delta($1,5)")])
    rep = run(meta, tmp_path, 1)
    assert rep["added"] == [] and rep["rejected"] == {"combine: fewer than 3 disjoint fills today": 1}
    a, b = sorted(lib.values(), key=lambda e: e["id"])
    text = NF.combine_pair(a, b, {e["id"]: FR.normalize(e["text"]) for e in (a, b)})[0]["text"]
    fl = field_lib(meta)
    ok, hard = CM.structurally_ok(FR.normalize(text).fill(["dsa_f00", "dsb_f00"]), fl.labels, "USA", 1)
    assert not ok and hard[0].startswith("H3 multiply operand is not bounded")


def test_a_mutation_takes_its_parents_own_role_pools(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "window")
    mined = ent(WIN, mined=True)
    make_lib(tmp_path, [mined])
    hist = {mined["canonical_key"]: {"slot_ds": [{"dsC"}], "slot_fields": [{"dsc_f00"}], "fills": {("dsc_f00",)}}}
    rep = run(meta, tmp_path, 1, hist=hist)
    (a,) = rep["added"]
    assert ST.read_all(tmp_path)[a["id"]]["slots"][0]["constraints"] == {"datasets": ["dsC"]}
    assert all(f.startswith("dsc_") for fill in a["fills"] for f in fill)
    novel = ent("rank(ts_mean($1,120))", cons=[{"datasets": ["dsD"], "kind": ["level"]}])
    make_lib(tmp_path / "n", [novel])
    (b,) = run(meta, tmp_path / "n", 1)["added"]
    assert ST.read_all(tmp_path / "n")[b["id"]]["slots"][0]["constraints"] == {"datasets": ["dsD"], "kind": ["level"]}


def test_a_new_frame_carries_its_provenance_and_taxonomy(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "condition", "combine")
    lib = make_lib(tmp_path, [ent(t) for t in MIX])
    rep = run(meta, tmp_path, 2)
    assert [a["kind"] for a in rep["added"]] == ["condition", "combine"]
    saved = ST.read_all(tmp_path)
    for a in rep["added"]:
        e = saved[a["id"]]
        assert SC.validate(e) == [] and e["status"] == "candidate"
        assert e["characteristics"] == TX.classify(FR.normalize(e["text"]))
        pv = e["provenance"]
        assert pv["origin"] == "mutation" and pv["cohort_day"] == DAY and pv["parent"] == pv["parents"][0]
        assert pv["mutation"]["kind"] == a["kind"] and pv["built_by"] == NF.BUILT_BY
        parents = [s for s in pv["sources"] if s["kind"] == "mutation-parent"]
        assert [s["ref"] for s in parents] == pv["parents"] and all(p in lib for p in pv["parents"])
        for s in parents:
            assert s["sha256"] == EV.sha256(ST.frames_dir(tmp_path) / ("%s.json" % s["ref"]))
    cond, comb = (saved[a["id"]]["provenance"] for a in rep["added"])
    assert [s["ref"] for s in cond["sources"] if s["kind"] == "condition-preset"] == cond["mutation"]["preset_from"][:1]
    assert len(comb["parents"]) == 2 and comb["parents"] == sorted(comb["parents"])


def test_the_same_seed_gives_the_same_frames(meta, tmp_path):
    for d in ("x", "y"):
        make_lib(tmp_path / d, [ent(t) for t in MIX])
    rx, ry = run(meta, tmp_path / "x", 6, seed=3), run(meta, tmp_path / "y", 6, seed=3)
    assert rx["added"] == ry["added"] and len(rx["added"]) == 6
    fx, fy = ST.frames_dir(tmp_path / "x"), ST.frames_dir(tmp_path / "y")
    assert sorted(p.name for p in fx.iterdir()) == sorted(p.name for p in fy.iterdir())
    for p in fx.iterdir():                      # identical but for the library's own path in provenance.sources
        assert p.read_text().replace(str(tmp_path / "x"), "LIB") == (fy / p.name).read_text().replace(str(tmp_path / "y"), "LIB")


SCRIPT = """
import json, pathlib, sys
from framelib.tests import test_loop_newframes as T
d = pathlib.Path(sys.argv[1])
meta = T.write_meta(d)
T.make_lib(d / "lib", [T.ent(t) for t in T.MIX])
rep = T.run(meta, d / "lib", 6, seed=5, dry=True)
print(json.dumps([[a["id"], a["fills"]] for a in rep["added"]]))
"""


def test_the_frames_do_not_depend_on_the_process_hash_seed(tmp_path):
    outs = []
    for hs in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=hs, PYTHONDONTWRITEBYTECODE="1")
        d = tmp_path / hs
        d.mkdir()
        r = subprocess.run([sys.executable, "-B", "-c", SCRIPT, str(d)], cwd=REPO, env=env, capture_output=True,
                           text=True, timeout=100)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.append(json.loads(r.stdout.strip().splitlines()[-1]))
    assert outs[0] == outs[1] and len(outs[0]) == 6


def test_a_rerun_the_same_day_continues_and_todays_cohort_is_never_a_parent(meta, tmp_path):
    make_lib(tmp_path, [ent(t) for t in MIX])
    first = [a["id"] for a in run(meta, tmp_path, 3)["added"]]
    assert len(first) == 3
    again = run(meta, tmp_path, 3)
    assert again["added"] == [] and again["already"] == sorted(first) and not again["written"]
    more = run(meta, tmp_path, 5)
    assert len(more["added"]) == 2 and not {p for a in more["added"] for p in a["parents"]} & set(first)
    nxt = run(meta, tmp_path, 1, day=NEXT_DAY, seed=11)
    assert nxt["already"] == [] and len(nxt["added"]) == 1


def test_the_check_budget_ends_the_call(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "window")
    monkeypatch.setattr(NF, "CHECKS_PER_FRAME", 1)
    make_lib(tmp_path, [ent("rank(ts_mean($1,%d))" % w, cons=[{"datasets": ["dsGone"]}]) for w in (3, 7, 9, 11, 13)])
    rep = run(meta, tmp_path, 3)
    assert rep["added"] == [] and rep["checks"] == 3 == rep["check_budget"] and rep["short"] == 3
    assert rep["exhausted"] == []


def test_combine_pairs_are_drawn_lazily(meta, tmp_path, monkeypatch):
    only_kinds(monkeypatch, "combine")
    make_lib(tmp_path, [ent("rank(ts_mean($1,%d))" % w) for w in range(2, 32)])     # 30 frames: 435 pairs
    calls = []
    real = NF.combine_pair
    monkeypatch.setattr(NF, "combine_pair", lambda *a: calls.append(1) or real(*a))
    rep = run(meta, tmp_path, 1)
    assert len(rep["added"]) == 1 and len(calls) <= 3


def test_a_dry_run_writes_nothing_and_a_run_files_through_the_store(meta, tmp_path):
    make_lib(tmp_path, [ent(t) for t in MIX])
    before = {p.name: p.read_bytes() for p in list(ST.frames_dir(tmp_path).iterdir()) + [tmp_path / "INDEX.json"]}
    rep = run(meta, tmp_path, 4, dry=True)
    assert len(rep["added"]) == 4 and not rep["written"]
    assert {p.name: p.read_bytes() for p in list(ST.frames_dir(tmp_path).iterdir()) + [tmp_path / "INDEX.json"]} == before
    rep = run(meta, tmp_path, 4)
    loaded = {e["id"] for e in ST.load(tmp_path)}                     # validates every entry and INDEX.json
    assert rep["written"] and {a["id"] for a in rep["added"]} <= loaded and len(loaded) == len(MIX) + 4
    index = json.loads((tmp_path / "INDEX.json").read_text())
    assert sorted(index["index"]["status"]["candidate"]) == sorted(loaded)


def patch_build(monkeypatch, meta):
    """main builds the field library of the repo's metadata; the tests give it the synthetic one."""
    real = FieldLibrary.build
    monkeypatch.setattr(FieldLibrary, "build", classmethod(
        lambda cls, *a, **k: real(meta / "field_labels.jsonl", meta / "fields")))


def _args(meta, tmp_path, **over):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(json.dumps({"frame_key": "rank($1)"}) + "\n")
    hist = tmp_path / "hist.jsonl"
    hist.write_text("")
    a = {"--library": str(tmp_path / "lib"), "--datasets-ok": str(meta / "datasets_ok.json"), "--history": str(hist),
         "--canonical": str(corpus), "--dropped-ids": str(meta / "selection.json"), "--dropped-lib": str(tmp_path),
         "--day": DAY, "--now": NOW}
    a.update(over)
    return [x for k, v in a.items() for x in (k, v)]


@pytest.mark.parametrize("what", ["--datasets-ok", "--history", "--canonical", "--dropped-ids", "empty-corpus", "bad-library"])
def test_main_fails_closed_and_writes_nothing(meta, tmp_path, capsys, monkeypatch, what):
    patch_build(monkeypatch, meta)
    make_lib(tmp_path / "lib", [ent(t) for t in MIX])
    before = sorted(p.name for p in ST.frames_dir(tmp_path / "lib").iterdir())
    over = {what: str(tmp_path / "absent")} if what.startswith("--") else {}
    argv = _args(meta, tmp_path, **over)
    if what == "empty-corpus":
        (tmp_path / "corpus.jsonl").write_text("")
    if what == "bad-library":
        (tmp_path / "lib" / "INDEX.json").write_text("{}")
    assert NF.main(argv + ["--n", "2"]) == 2
    assert "fail-closed, nothing written" in capsys.readouterr().out
    assert sorted(p.name for p in ST.frames_dir(tmp_path / "lib").iterdir()) == before


def test_main_seeds_from_the_day_and_files_the_cohort(meta, tmp_path, capsys, monkeypatch):
    make_lib(tmp_path / "lib", [ent(t) for t in MIX])
    make_lib(tmp_path / "copy", [ent(t) for t in MIX])
    patch_build(monkeypatch, meta)
    assert NF.main(_args(meta, tmp_path) + ["--n", "2"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["seed"] == 20260925 and rep["written"] and len(rep["added"]) == 2
    assert rep["added"] == run(meta, tmp_path / "copy", 2, seed=20260925, corpus={"rank($1)"}, dry=True)["added"]


def test_the_shipped_dropped_list_is_the_curators_34_frames_outside_the_first_100():
    ids = json.loads(NF.DROPPED_IDS.read_text())["dropped_mined"]
    assert len(ids) == len(set(ids)) == 34
    dropped = NF.load_dropped(NF.DROPPED_IDS, NF.DROPPED_LIB)
    assert [e["id"] for e in dropped] == sorted(ids)
    first = [e for e in ST.load() if e["provenance"]["origin"] in ("mined", "novel")]     # the curator's selection
    assert len(first) == 100
    taken = {e["id"] for e in first} | {e["canonical_key"] for e in first}
    for e in dropped:
        assert e["provenance"]["origin"] == "mined" and e["evidence"]["n_rows"] > 0
        assert e["id"] not in taken and e["canonical_key"] not in taken
        assert SC.validate(NF.dropped_entry(e, NF.DROPPED_IDS, DAY, NOW)) == []


def test_load_dropped_reads_the_listed_entries_in_id_order(tmp_path):
    es = [ent("rank(ts_mean($1,%d))" % w, mined=True) for w in (3, 7, 9)]
    make_lib(tmp_path, es)
    ids = sorted(e["id"] for e in es)
    (tmp_path / "selection.json").write_text(json.dumps({"dropped_mined": [ids[2], ids[0]], "mined": 1}))
    assert [e["id"] for e in NF.load_dropped(tmp_path / "selection.json", tmp_path)] == [ids[0], ids[2]]
