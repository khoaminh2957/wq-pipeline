import json

from forge.offline import recover_orphans as RO


class _R:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


def test_match_uses_formula_and_settings():
    c1 = {"formula": "rank(a) * rank(b)", "settings": {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "STATISTICAL", "decay": 4, "truncation": 0.15}, "meta": {"hypothesis": "x", "forge": 1}}
    c2 = dict(c1, settings=dict(c1["settings"], decay=8), meta={"hypothesis": "x", "forge": 1, "cand": "other"})
    idx = {RO._norm(c1["formula"]): [c1, c2]}
    assert RO.match(idx, "rank(a)*rank(b)", {"region": "USA", "decay": 4}) is c1
    assert RO.match(idx, "rank(a)*rank(b)", {"region": "USA", "decay": 8}) is c2
    assert RO.match(idx, "rank(a)*rank(b)", {"region": "USA"}) is None          # ambiguous -> never guessed
    assert RO.match(idx, "rank(zz)", {"region": "USA"}) is None
    twice = {RO._norm(c1["formula"]): [c1, json.loads(json.dumps(c1))]}     # same construction in two plan files
    assert RO.match(twice, "rank(a)*rank(b)", {"region": "USA", "decay": 4}) is c1


def test_unmatched_and_rematch(tmp_path):
    j = tmp_path / "forge.jsonl"
    con = {"formula": "f1", "settings": {"region": "USA", "delay": 1}, "meta": {"forge": 1, "hypothesis": "h", "arm": "S"}}
    j.write_text(json.dumps({"status": "ORPHAN-UNMATCHED", "alpha": None, "sim_url": "U1", "parent_url": "P", "child_index": 3,
                             "formula": "f1", "settings": {"region": "USA", "delay": 1}, "meta": None}) + "\n"
                 + json.dumps({"status": "ORPHAN-UNMATCHED", "alpha": None, "sim_url": "U2", "parent_url": "P", "child_index": 4,
                               "formula": "f9", "settings": {"region": "USA", "delay": 1}, "meta": None}) + "\n"
                 + json.dumps({"status": "ORPHAN-UNMATCHED", "alpha": None, "sim_url": "U3", "formula": "f1", "settings": {}}) + "\n"
                 + json.dumps({"status": "COMPLETE", "alpha": "A3", "sim_url": "U3"}) + "\n")
    todo = RO.unmatched(j)
    assert [r["sim_url"] for r in todo] == ["U1", "U2"]                       # U3 already attributed
    cidx = {"f1": [con]}
    resp = {"U1": _R(200, {"status": "COMPLETE", "alpha": "A1", "regular": "f1", "settings": {"region": "USA", "delay": 1}})}
    rows = RO.rematch(todo, cidx, lambda aid: {"sharpe": 1.7}, lambda url: resp.get(url), sleep=lambda _: None)
    assert len(rows) == 1 and rows[0]["alpha"] == "A1" and rows[0]["meta"]["arm"] == "S" and rows[0]["sharpe"] == 1.7 and rows[0]["child_index"] == 3


def test_orphans_and_recover(tmp_path):
    j = tmp_path / "forge.jsonl"
    j.write_text(json.dumps({"status": "PARENT-POSTED", "parent_url": "P1", "formulas": ["f1", "f2"]}) + "\n"
                 + json.dumps({"status": "PARENT-POSTED", "parent_url": "P2", "formulas": ["f3"]}) + "\n"
                 + json.dumps({"status": "COMPLETE", "alpha": "A", "parent_url": "P2"}) + "\n")
    o = RO.orphans(j)
    assert [p["parent_url"] for p in o] == ["P1"]
    con = {"formula": "f1", "settings": {"region": "USA", "delay": 1}, "meta": {"forge": 1, "hypothesis": "h"}}
    cidx = {"f1": [con]}
    responses = {"P1": _R(200, {"status": "COMPLETE", "children": ["c1", "c2"]}),
                 "https://api.worldquantbrain.com/simulations/c1": _R(200, {"status": "COMPLETE", "alpha": "A1", "regular": "f1", "settings": {"region": "USA", "delay": 1}}),
                 "https://api.worldquantbrain.com/simulations/c2": _R(200, {"status": "COMPLETE", "alpha": "A2", "regular": "f9", "settings": {"region": "USA", "delay": 1}})}
    rows = RO.recover(None, o[0], cidx, lambda aid: {"sharpe": 1.9, "checks": [{"name": "LOW_SHARPE", "result": "PASS"}]},
                      lambda url: responses.get(url), sleep=lambda _: None)
    assert len(rows) == 2
    assert rows[0]["alpha"] == "A1" and rows[0]["meta"]["hypothesis"] == "h" and rows[0]["sharpe"] == 1.9 and rows[0]["child_index"] == 0
    assert rows[1]["status"] == "ORPHAN-UNMATCHED" and rows[1]["alpha"] is None and rows[1]["meta"] is None
    # a parent that is not terminal yields nothing
    assert RO.recover(None, o[0], cidx, lambda a: {}, lambda url: _R(200, {"status": "RUNNING"}), sleep=lambda _: None) == []


def test_a_parent_with_only_machine_side_child_rows_is_still_an_orphan(tmp_path):
    j = tmp_path / "forge.jsonl"
    j.write_text("\n".join(json.dumps(r) for r in [
        {"status": "PARENT-POSTED", "parent_url": "P1", "formulas": ["f"]},
        {"status": "POLL-DEADLINE", "alpha": None, "parent_url": "P1"},
        {"status": "PARENT-POSTED", "parent_url": "P2", "formulas": ["f"]},
        {"status": "AUTH-FAIL", "alpha": None, "parent_url": "P2"},
        {"status": "PARENT-POSTED", "parent_url": "P3", "formulas": ["f"]},
        {"status": "ERROR", "alpha": None, "parent_url": "P3"},
        {"status": "PARENT-POSTED", "parent_url": "P4", "formulas": ["f"]},
        {"status": "COMPLETE", "alpha": "A", "parent_url": "P4"}]) + "\n")
    assert [p["parent_url"] for p in RO.orphans(j)] == ["P1", "P2"]


def test_same_construction_planned_in_two_rounds_is_not_ambiguous():
    """MEASURED 2026-09-09: 131 recoverable children were filed ORPHAN-UNMATCHED because the same
    construction had been planned again in a later round and the two plan entries differed only by
    `meta.seed`. Round bookkeeping is not identity; `category` and `arm` still are."""
    base = {"formula": "multiply(a, b)", "settings": {"region": "USA", "universe": "TOP3000", "delay": 1,
            "neutralization": "SUBINDUSTRY", "decay": 8, "truncation": 0.15},
            "meta": {"hypothesis": "h", "category": "Insiders", "arm": "new", "seed": 111}}
    other_round = {**base, "meta": {**base["meta"], "seed": 222}}
    other_cat = {**base, "meta": {**base["meta"], "seed": 222, "category": "Other"}}
    other_arm = {**base, "meta": {**base["meta"], "seed": 222, "arm": "current"}}
    st = base["settings"]
    assert RO.match({RO._norm(base["formula"]): [base, other_round]}, base["formula"], st) is base
    assert RO.match({RO._norm(base["formula"]): [base, other_cat]}, base["formula"], st) is None
    assert RO.match({RO._norm(base["formula"]): [base, other_arm]}, base["formula"], st) is None
    # a genuine settings difference is still separated by the discriminators, not by identity
    other_decay = {**base, "meta": {**base["meta"], "seed": 222}, "settings": {**st, "decay": 4}}
    assert RO.match({RO._norm(base["formula"]): [base, other_decay]}, base["formula"], st) is base


def test_the_pipeline_version_stamp_is_provenance_not_identity():
    """Architecture attack round 1, S1: with the stamp in the identity, a construction planned by two
    versions matched NOTHING (pre-stamp + stamped: False; two stamps: False) and every child of it
    would have been filed ORPHAN-UNMATCHED at the first stamped deploy."""
    from forge.offline import recover_orphans as RO
    base = {"formula": "rank(x)", "settings": {"delay": 1, "decay": 4, "neutralization": "INDUSTRY"},
            "meta": {"hypothesis": "h", "category": "News", "seed": 1}}
    cases = [
        ({}, {}),                                                      # unstamped, two rounds
        ({"pipeline_version": "a"}, {"pipeline_version": "a"}),        # same stamp
        ({}, {"pipeline_version": "a"}),                               # pre-stamp + stamped
        ({"pipeline_version": "a"}, {"pipeline_version": "b"}),        # two different stamps
    ]
    for m1, m2 in cases:
        c1 = {**base, "meta": {**base["meta"], **m1, "seed": 1}}
        c2 = {**base, "meta": {**base["meta"], **m2, "seed": 2}}
        index = {RO._norm("rank(x)"): [c1, c2]}
        assert RO.match(index, "rank(x)", base["settings"]) is not None, (m1, m2)
