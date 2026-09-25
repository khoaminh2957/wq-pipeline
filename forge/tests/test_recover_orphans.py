import json

import pytest

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


def test_a_construction_planned_by_two_versions_is_attributed_to_neither(tmp_path):
    """Architecture round 2, A11. Identity ignores the version stamp (test above), so match() returned
    hits[0] and the recovered row inherited whichever plan `glob` listed first. Round 2 measured it:
    plans 101.json {A_version} and 202.json {B_version}, glob order ['202.json', '101.json'], recovered
    meta {'seed': 202, 'pipeline_version': 'B_version'} whichever round POSTed it -- a permanent
    mis-attribution under D14. Now the version is written as RO.AMBIGUOUS_VERSION, which the scorer
    excludes from every version's cohort."""
    st = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY", "decay": 8, "truncation": 0.15}
    base = {"formula": "rank(x)", "settings": st, "meta": {"hypothesis": "h", "category": "News"}}
    for seed, v in ((101, "A_version"), (202, "B_version")):
        plan = {"constructions": [{**base, "meta": {**base["meta"], "seed": seed, "pipeline_version": v}}]}
        (tmp_path / ("%d.json" % seed)).write_text(json.dumps(plan))
    idx = RO.load_plans(tmp_path)
    key = RO._norm("rank(x)")
    assert RO.AMBIGUOUS_VERSION == "ambiguous"
    for order in (idx[key], list(reversed(idx[key]))):          # whichever order glob lists the plans
        got = RO.match({key: order}, "rank(x)", st)
        assert got["meta"]["pipeline_version"] == "ambiguous"
        assert got["formula"] == "rank(x)" and got["settings"] == st and got["meta"]["hypothesis"] == "h"
    # the plan index every later match reads is not rewritten
    assert sorted(c["meta"]["pipeline_version"] for c in idx[key]) == ["A_version", "B_version"]
    # the journal row the recovery writes carries it
    row = RO.child_row({"status": "COMPLETE", "alpha": "A1", "regular": "rank(x)", "settings": st}, "U1", "P1", 0,
                       idx, lambda aid: {"sharpe": 1.2}, sleep=lambda _: None)
    assert row["alpha"] == "A1" and row["meta"]["pipeline_version"] == "ambiguous"

    # a pre-stamp plan and a stamped one: the version is just as unknown
    pre = {**base, "meta": {**base["meta"], "seed": 1}}
    stamped = {**base, "meta": {**base["meta"], "seed": 2, "pipeline_version": "A_version"}}
    assert RO.match({key: [pre, stamped]}, "rank(x)", st)["meta"]["pipeline_version"] == "ambiguous"
    # one version planned it twice, or nobody stamped it: unchanged -- the very plan entry, nothing added
    again = {**base, "meta": {**base["meta"], "seed": 3, "pipeline_version": "A_version"}}
    assert RO.match({key: [stamped, again]}, "rank(x)", st) is stamped
    assert RO.match({key: [pre, {**pre, "meta": {**pre["meta"], "seed": 4}}]}, "rank(x)", st) is pre


def test_an_ambiguous_row_names_no_round_and_keeps_the_candidates(tmp_path):
    """draw-3 pipeline MINOR 7. The A11 branch kept hits[0]'s `meta.seed`: plans 101.json {A_version} and
    202.json {B_version} recovered as {'seed': 202, 'pipeline_version': 'ambiguous'} (glob order), and
    forge/offline/ab_report.py groups A/B rounds by meta.seed, so the row joined round 202 on glob order.
    Now the seed is None and both rounds are kept in meta.seed_candidates, in one order whatever glob does."""
    st = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY", "decay": 8, "truncation": 0.15}
    base = {"formula": "rank(x)", "settings": st, "meta": {"hypothesis": "h", "category": "News", "arm": "new"}}
    for seed, v in ((101, "A_version"), (202, "B_version")):
        plan = {"constructions": [{**base, "meta": {**base["meta"], "seed": seed, "pipeline_version": v}}]}
        (tmp_path / ("%d.json" % seed)).write_text(json.dumps(plan))
    idx = RO.load_plans(tmp_path)
    key = RO._norm("rank(x)")
    for order in (idx[key], list(reversed(idx[key]))):
        got = RO.match({key: order}, "rank(x)", st)
        assert got["meta"]["pipeline_version"] == "ambiguous"
        assert got["meta"]["seed"] is None and got["meta"]["seed_candidates"] == [101, 202]
        assert got["meta"]["arm"] == "new" and got["meta"]["hypothesis"] == "h"
    assert sorted(c["meta"]["seed"] for c in idx[key]) == [101, 202]         # the plan index is not rewritten
    assert all("seed_candidates" not in c["meta"] for c in idx[key])
    # two versions but ONE round (the same --seed on both): that round is known and is kept, nothing added
    one = [{**base, "meta": {**base["meta"], "seed": 7, "pipeline_version": v}} for v in ("A_version", "B_version")]
    got = RO.match({key: one}, "rank(x)", st)
    assert got["meta"]["pipeline_version"] == "ambiguous" and got["meta"]["seed"] == 7 and "seed_candidates" not in got["meta"]


def test_ab_report_keeps_an_ambiguous_row_out_of_every_round(tmp_path, monkeypatch):
    """draw-3 pipeline MINOR 7, the reader's side, run against the REAL forge/offline/ab_report.report() (read,
    not edited). A seed of None is dropped from its rounds (`if k is not None`) and still counts in its arm's
    pooled total. The string "ambiguous" first specified for the seed was measured to make report() raise
    TypeError (it sorts the round keys, str against int), which is why the seed is None.
    Hermetic (draw3_fix pipeline 4): report() also reads ROOT/state/forge/corr.jsonl and submitted.jsonl, and
    one `{"prod": 0.3}` row in the tree's corr.jsonl failed this test with KeyError 'alpha' (the adjudicator's
    snapshot) -- inside deploy's `pytest forge/tests -x` smoke. The module's ROOT is pointed at an empty tree."""
    from forge.offline import ab_report as AB
    monkeypatch.setattr(AB, "ROOT", tmp_path)
    st = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY", "decay": 8, "truncation": 0.15}
    base = {"formula": "rank(x)", "settings": st, "meta": {"hypothesis": "h", "category": "News", "arm": "new"}}
    plans = tmp_path / "plans"
    plans.mkdir()
    for seed, v in ((101, "A_version"), (202, "B_version")):
        plan = {"constructions": [{**base, "meta": {**base["meta"], "seed": seed, "pipeline_version": v}}]}
        (plans / ("%d.json" % seed)).write_text(json.dumps(plan))
    recovered = RO.child_row({"status": "COMPLETE", "alpha": "A3", "regular": "rank(x)", "settings": st}, "U3", "P3", 0,
                             RO.load_plans(plans), lambda aid: {"sharpe": 1.2}, sleep=lambda _: None)
    assert recovered["meta"]["seed"] is None
    rows = [{"alpha": "A1", "status": "COMPLETE", "sharpe": 1.0, "meta": {"arm": "new", "seed": 101}},
            {"alpha": "A2", "status": "COMPLETE", "sharpe": 1.1, "meta": {"arm": "current", "seed": 202}},
            recovered]
    journal = tmp_path / "forge.jsonl"
    journal.write_text("".join(json.dumps(r) + "\n" for r in rows))
    rep = AB.report(journal=journal, scored_path=tmp_path / "no-scored.jsonl")
    rounds = {r["seed"]: {arm: s["n"] for arm, s in r.items() if arm != "seed"} for r in rep["rounds"]}
    assert rounds == {101: {"new": 1}, 202: {"current": 1}}                 # A3 is in neither round
    assert rep["pooled"]["new"]["n"] == 2 and rep["pooled"]["current"]["n"] == 1


def test_match_survives_an_unhashable_stamp_or_seed():
    """draw-3 pipeline MINOR 7: match() built a set of the raw stamps, so a plan entry whose
    `pipeline_version` was a list (a plan that did not come from the runner) raised TypeError and stopped
    the whole recovery. The sets are now built from JSON text."""
    st = {"region": "USA", "delay": 1}
    base = {"formula": "rank(x)", "settings": st, "meta": {"hypothesis": "h"}}
    key = RO._norm("rank(x)")
    a = {**base, "meta": {**base["meta"], "seed": [1], "pipeline_version": ["v1"]}}
    b = {**base, "meta": {**base["meta"], "seed": {"r": 2}, "pipeline_version": {"v": 2}}}
    got = RO.match({key: [a, b]}, "rank(x)", st)
    assert got["meta"]["pipeline_version"] == "ambiguous" and got["meta"]["seed"] is None
    assert got["meta"]["seed_candidates"] == [[1], {"r": 2}]
    same = {**a, "meta": dict(a["meta"])}                                      # equal unhashable stamps: one version
    assert RO.match({key: [a, same]}, "rank(x)", st) is a


def test_a_construction_planned_under_two_run_configs_is_one_construction():
    """D30 adds meta.run_config (the runner's arguments) beside meta.pipeline_version. It is round provenance,
    not identity, for the reason the version is (architecture round 1, S1): the same formula and settings are
    one simulation whatever FORGE_ARGS planned them, and with run_config inside _identity() two such plan
    entries read as two candidates -- match() returned None and the child was filed ORPHAN-UNMATCHED, the
    2026-09-09 class. When the two run_configs differ, the row's run_config is not known: AMBIGUOUS_VERSION,
    as the version is under A11, and the version both entries agree on is kept."""
    st = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY", "decay": 8, "truncation": 0.15}
    base = {"formula": "rank(x)", "settings": st, "meta": {"hypothesis": "h", "category": "News", "pipeline_version": "V"}}
    key = RO._norm("rank(x)")
    a = {**base, "meta": {**base["meta"], "seed": 101, "run_config": "rcA"}}
    b = {**base, "meta": {**base["meta"], "seed": 202, "run_config": "rcB"}}
    for order in ([a, b], [b, a]):
        got = RO.match({key: order}, "rank(x)", st)
        assert got is not None
        assert got["meta"]["run_config"] == RO.AMBIGUOUS_VERSION and got["meta"]["pipeline_version"] == "V"
        assert got["meta"]["seed"] is None and got["meta"]["seed_candidates"] == [101, 202]
    assert [c["meta"]["run_config"] for c in (a, b)] == ["rcA", "rcB"]            # the plan entries are not rewritten
    # one run_config, planned twice: the very plan entry, nothing added
    again = {**a, "meta": {**a["meta"], "seed": 303}}
    assert RO.match({key: [a, again]}, "rank(x)", st) is a
    # both stamps differ: both are unknown
    c = {**b, "meta": {**b["meta"], "pipeline_version": "W"}}
    got = RO.match({key: [a, c]}, "rank(x)", st)
    assert (got["meta"]["pipeline_version"], got["meta"]["run_config"]) == (RO.AMBIGUOUS_VERSION, RO.AMBIGUOUS_VERSION)


# ------------------------------------------------------------------------------------ D46 / draw-4 pipeline P1
_ST = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY", "decay": 8, "truncation": 0.15}
#: the plan shapes the draw-4 adjudicator measured (scratchpad/adjd4_dupplan.py), as the arm drivers write them
_PLAN_META = {
    # forge/offline/pow_pairs.py: meta copied from a journal row of ANOTHER version, its arm included
    "pow": {"hypothesis": "h", "recipe": "POW", "seed": 5, "arm": "current",
            "pipeline_version": "v-of-the-base-row", "run_config": "rc-of-the-base-row"},
    # forge/offline/c11_neut.py: a row of the running version, no run_config (built before D30)
    "c11": {"hypothesis": "h", "seed": 5, "arm": "c11-x", "pipeline_version": "v-running"},
    # forge/llm/formula.py: no stamp at all
    "llmformula": {"hypothesis": "llm:x", "arm": "llmformula"},
    # no arm: the runner adds one (D47 groundwork), so this entry's identity differs from its runner copy's
    "noarm": {"hypothesis": "h"},
}


@pytest.mark.parametrize("shape", sorted(_PLAN_META))
def test_a_plan_round_recovers_the_pair_it_dispatched(tmp_path, monkeypatch, shape):
    """D46 (Khoa 2026-09-23 ~20:15; draw-4 pipeline SERIOUS 1 / P1). The REAL runner main() re-stamps a `--plan`
    round and writes its copy, as `<seed>.json`, into the plans directory that already holds the experiment's own
    plan (on the VPS, read 2026-09-23: pow.json, c11.json and llmformula*.json sit among 216 runner copies). The
    REAL load_plans(), match() and child_row() then attribute the child. The recovered row must carry exactly the
    meta that was dispatched. MEASURED before the fix by the adjudicator: (ambiguous, ambiguous) for pow,
    (v-running, ambiguous) for c11, (ambiguous, ambiguous) for llmformula; and with the arm stamp, `noarm`
    matched nothing (ORPHAN-UNMATCHED)."""
    import layered_sim as LS
    from forge import runner as R
    plans = tmp_path / "plans"
    plans.mkdir()
    exp = plans / ("%s.json" % shape)
    exp.write_text(json.dumps({"seed": 5, "n": 1, "hypotheses": 0, "cells_considered": 0, "gate": {}, "blocks": [],
                               "constructions": [{"formula": "rank(x)", "settings": _ST, "meta": dict(_PLAN_META[shape])}]}))
    sent = []
    monkeypatch.setattr(R, "PLANS", plans)
    monkeypatch.setattr(R, "RUN_CONFIG_LOG", tmp_path / "run_config_log.jsonl")
    monkeypatch.setattr(R, "notify_queue", lambda p, root: None)
    monkeypatch.setattr(R, "_VERSION", "v-running")
    monkeypatch.setattr(LS, "run", lambda n, **kw: sent.append(kw["batch"]))
    assert R.main(["--plan", str(exp), "--seed", "77"]) == 0
    (dispatched,), = sent
    assert sorted(p.name for p in plans.iterdir()) == sorted([exp.name, "77.json"])
    assert dispatched["meta"]["pipeline_version"] == "v-running" and dispatched["meta"]["run_config"]
    row = RO.child_row({"status": "COMPLETE", "alpha": "A1", "regular": "rank(x)", "settings": _ST}, "U1", "P1", 0,
                       RO.load_plans(plans), lambda aid: {"sharpe": 1.2}, sleep=lambda _: None)
    assert row["status"] == "COMPLETE" and row["alpha"] == "A1"
    got = row["meta"]
    assert (got["pipeline_version"], got["run_config"]) == (dispatched["meta"]["pipeline_version"],
                                                            dispatched["meta"]["run_config"])
    assert got == dispatched["meta"]


def test_load_plans_reads_the_runners_copies_only(tmp_path):
    """D46 / P1: only `<seed>.json` (forge/runner.py main(); `--seed` is an int, so it may be negative) is
    indexed; an experiment script's plan is not."""
    for name, formula in (("5.json", "a"), ("-3.json", "b"), ("1788939868.json", "c"), ("pow.json", "d"),
                          ("llmformula_a.json", "e"), ("12a.json", "f"), ("c11.json", "g")):
        (tmp_path / name).write_text(json.dumps({"constructions": [{"formula": formula, "settings": {}, "meta": {}}]}))
    assert sorted(RO.load_plans(tmp_path)) == ["a", "b", "c"]


def test_a_per_round_gen_state_is_bookkeeping_not_identity():
    """Architecture round 3 S15: the pass-first generator stamps meta.gen_state (the sha256 of the loop state it
    recomputes every round) on every construction. With it in the identity, two plan entries of one
    construction differing in seed and gen_state returned None -- ORPHAN-UNMATCHED, the 2026-09-09 class. It
    joins ROUND_KEYS; `arm` does not (S15), because D47 compares arms."""
    base = {"formula": "rank(x)", "settings": _ST, "meta": {"hypothesis": "gen:fam", "category": "News", "arm": "gen",
                                                          "pipeline_version": "V", "run_config": "R"}}
    a = {**base, "meta": {**base["meta"], "seed": 101, "gen_state": "a" * 64}}
    b = {**base, "meta": {**base["meta"], "seed": 202, "gen_state": "b" * 64}}
    key = RO._norm("rank(x)")
    assert "gen_state" in RO.ROUND_KEYS and "arm" not in RO.ROUND_KEYS
    assert RO.match({key: [a, b]}, "rank(x)", _ST) is a
    # OPEN, pinned as it stands (draw3_fix pipeline 5, extended to gen_state): hits[0]'s seed and gen_state
    assert RO.match({key: [b, a]}, "rank(x)", _ST) is b
    other_arm = {**b, "meta": {**b["meta"], "arm": "composites"}}
    assert RO.match({key: [a, other_arm]}, "rank(x)", _ST) is None


def test_a_row_ambiguous_on_either_stamp_forms_no_cohort():
    """draw-4 pipeline P2, the pipeline's contract test: a row match() marks AMBIGUOUS_VERSION in either stamp
    must form no cohort in the REAL forge/offline/benchmark.cohort_of() (read, not edited). Before the scoring
    owner's half landed, (v-running, 'ambiguous') formed a cohort of its own (draw-4 pipeline SERIOUS 2)."""
    from forge.offline import benchmark as B
    key = RO._norm("rank(x)")
    base = {"formula": "rank(x)", "settings": _ST, "meta": {"hypothesis": "h", "pipeline_version": "v-running"}}
    same_version = [{**base, "meta": {**base["meta"], "seed": s, "run_config": rc}} for s, rc in ((1, "rcA"), (2, "rcB"))]
    two_versions = [{**base, "meta": {**base["meta"], "seed": s, "pipeline_version": v, "run_config": "rcA"}}
                    for s, v in ((1, "v1"), (2, "v2"))]
    for entries, want in ((same_version, ("v-running", RO.AMBIGUOUS_VERSION)),
                          (two_versions, (RO.AMBIGUOUS_VERSION, "rcA"))):
        row = RO.child_row({"status": "COMPLETE", "alpha": "A1", "regular": "rank(x)", "settings": _ST}, "U1", "P1", 0,
                           {key: entries}, lambda aid: {}, sleep=lambda _: None)
        assert (row["meta"]["pipeline_version"], row["meta"]["run_config"]) == want
        assert B.cohort_of(row) is None
    # the control: an unambiguous row does form its cohort
    row = RO.child_row({"status": "COMPLETE", "alpha": "A2", "regular": "rank(x)", "settings": _ST}, "U2", "P2", 0,
                       {key: same_version[:1]}, lambda aid: {}, sleep=lambda _: None)
    assert B.cohort_of(row) == ("v-running", "rcA")


def test_the_round_of_a_randomised_round_is_bookkeeping_and_arm_by_is_identity():
    """D54 and the runner's `--mode randomised` (shared interface: meta.round = the seed, meta.arm_by = "randomiser" or
    "explicit"). `round` is set per ROUND as seed is: without it in ROUND_KEYS, two plan entries of one construction
    from two randomised rounds read as two candidates and match() returned None (ORPHAN-UNMATCHED, the 2026-09-09
    class). `arm_by` stays identity with `arm`: it decides whether a row enters D54's comparison. When the entries
    name several rounds the row's round is None in BOTH branches of match(), never hits[0]'s: benchmark's arms
    read-out takes meta.round as its test's unit and excludes a row without one, while hits[0] is glob order. The
    seed keeps its OPEN (draw3_fix pipeline 5: hits[0]'s when the stamps agree). `gen_draw` the same way: set by
    the draw's place in its round (forge/gen/propose.py), None when the entries disagree, a mismatch never
    unmatched."""
    base = {"formula": "rank(x)", "settings": _ST, "meta": {"hypothesis": "gen:fam", "category": "News", "arm": "gen",
                                                          "arm_by": "randomiser", "pipeline_version": "V", "run_config": "R"}}
    a = {**base, "meta": {**base["meta"], "seed": 101, "round": 101, "gen_draw": "floor"}}
    b = {**base, "meta": {**base["meta"], "seed": 202, "round": 202, "gen_draw": "posterior"}}
    key = RO._norm("rank(x)")
    assert "round" in RO.ROUND_KEYS and "gen_draw" in RO.ROUND_KEYS and "arm_by" not in RO.ROUND_KEYS
    for first, second in ((a, b), (b, a)):
        got = RO.match({key: [first, second]}, "rank(x)", _ST)
        assert got["meta"] == dict(first["meta"], round=None, gen_draw=None)          # the seed: hits[0]'s (OPEN)
        assert first["meta"]["round"] is not None                                     # the plan index is not rewritten
    same_round = {**b, "meta": {**b["meta"], "seed": 101, "round": 101, "gen_draw": "floor"}}
    assert RO.match({key: [a, same_round]}, "rank(x)", _ST) is a                      # nothing to disagree on
    explicit = {**b, "meta": {**b["meta"], "arm_by": "explicit"}}
    assert RO.match({key: [a, explicit]}, "rank(x)", _ST) is None
    two_versions = {**b, "meta": {**b["meta"], "pipeline_version": "V2"}}
    for order in ([a, two_versions], [two_versions, a]):
        m = RO.match({key: order}, "rank(x)", _ST)["meta"]
        assert (m["pipeline_version"], m["seed"], m["round"], m["seed_candidates"], m["gen_draw"]) == \
            (RO.AMBIGUOUS_VERSION, None, None, [101, 202], None)
