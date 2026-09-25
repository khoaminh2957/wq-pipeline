"""forge.gen.propose: one round end to end, offline. 10,000 seeded draws against the runner's own structural
gate; the contract and the route stamp (shared interface: fresh / neighbour / repair); the floor and the
dataset posterior (draw-5 gen G2); plan-time D18; the family rules; the repair queue; the D51 neighbours with
the handed filter, the shortfall counter and the cell charge (draw-5 gen N1-N3); purity."""
import collections
import json
import math
import random
import types

import pytest

import fingerprint as FP
from forge import cells as C
from forge import runner as R
from forge import signature as S
from forge.factory import candidate_id
from forge.gen import families as FM
from forge.gen import posterior as PO
from forge.gen import productions as P
from forge.gen import propose as PR
from forge.gen import repair as RP
from forge.gen import state as ST
from forge.tests.test_gen_productions import CELLS, LABS, _draws, synthetic_labels
from forge.tests.test_gen_spend import _curve, _walk

FD = {fid: v["dataset"] for fid, v in LABS.items()}


def fd(region, universe, delay):
    return FD


def runner_structurally_ok(labels):
    """`runner.plan`'s own `structurally_ok`, read only: the nested function's code object, closed over the
    label set, run in runner's globals (a module-level one is used instead if the runner owner lifts it)."""
    lifted = getattr(R, "structurally_ok", None)
    if callable(lifted):
        return lifted
    code = next(c for c in R.plan.__code__.co_consts if isinstance(c, types.CodeType) and c.co_name == "structurally_ok")
    cells = {"struct_labels": types.CellType(labels), "struct_refused": types.CellType(collections.Counter())}
    return types.FunctionType(code, R.__dict__, "structurally_ok", None, tuple(cells[n] for n in code.co_freevars))


EMPTY = ST.build({}, [], {})
BIG = {}


def big():
    if not BIG:
        BIG["a"] = PR.propose(EMPTY, LABS, CELLS, 10000, seed=5, field_datasets=fd, cell_cap=10 ** 6)
    return BIG["a"]


def test_ten_thousand_seeded_draws_no_refusal_no_repeat_same_output_for_the_same_seed():
    res = big()
    cands = res["candidates"]
    assert len(cands) == 10000
    assert res["counts"].get("structure-refused", 0) == 0 and res["counts"].get("excluded", 0) == 0
    gate = runner_structurally_ok(LABS)
    assert all(gate(c) for c in cands)                          # the runner's gate, not a copy of it
    # "0 exact repeats" is the duplicate COUNTER: admit() refuses a repeat, so the output cannot hold one by
    # construction (draw-5 gen N5); the counter says whether the grammar drew one at all
    assert res["counts"].get("duplicate", 0) == 0
    assert len({(c["formula"], json.dumps(c["settings"], sort_keys=True)) for c in cands}) == 10000
    fams = {c["meta"]["hypothesis"] for c in cands}               # empty state: every family was founded here
    assert res["counts"]["family-founded"] == len(fams) < 10000
    again = PR.propose(EMPTY, LABS, CELLS, 10000, seed=5, field_datasets=fd, cell_cap=10 ** 6)
    assert again == res                                          # every candidate, count and cell, deep-equal
    other = PR.propose(EMPTY, LABS, CELLS, 300, seed=6, field_datasets=fd)
    assert [c["id"] for c in other["candidates"]] != [c["id"] for c in cands[:300]]


def test_every_candidate_carries_the_contract_and_the_state_sha():
    for c in big()["candidates"][:2000]:
        m = c["meta"]
        assert m["hypothesis"].startswith("gen:") and m["composite"] == 1 and m["arm"] == "gen"
        assert m["generator"] == P.GENERATOR and m["gen_state"] == EMPTY.sha and m["gen_route"] == "fresh"
        assert m["gen_draw"] in ("posterior", "floor") and not {"neighbour_of", "repair_of"} & set(m)
        assert m["category"] in {cell.category for cell in CELLS} and m["field"] == m["legs"][0]["field"]
        assert all(L["sign_source"] in ("description", "coin") and L["orientation"] in "+-" for L in m["legs"])
        sig = S.signature(c["formula"], "USA", 1, mechanism=m["hypothesis"], field_datasets=FD)
        assert c["signature"]["key"] == sig["key"]


def test_the_floor_is_one_draw_in_five_and_the_only_route_to_tier_u():
    res = big()
    assert res["n_floor"] == math.ceil(res["n_draws"] / 5) == 2000
    assert res["by_route"] == {"fresh": 10000}
    assert collections.Counter(c["meta"]["gen_draw"] for c in res["candidates"]) == {"floor": 2000, "posterior": 8000}
    tier = collections.Counter(c["meta"]["gen_draw"] for c in res["candidates"]
                               if any(L["ts"] == P.TS_TIER_U for L in c["meta"]["legs"]))
    assert tier["posterior"] == 0 and tier["floor"] > 100


def test_orientation_reaches_the_formula_through_propose():
    """Draw-5 gen G2 (O1/O2): a '-' leg is written '(1 - leg)' and a '+' leg is not. No other production writes
    '(1 - ', so the count in the whole formula equals the number of '-' legs."""
    signs = collections.Counter()
    for c in big()["candidates"][:3000]:
        legs = c["meta"]["legs"]
        assert c["formula"].count("(1 - ") == sum(L["orientation"] == "-" for L in legs), c["formula"]
        signs.update(L["orientation"] for L in legs)
    assert signs["+"] > 500 and signs["-"] > 500


def _skewed_state():
    """Generated rows (no formula: they found no family and trigger nothing) whose legs used one Option dataset
    and INDUSTRY and read y = 1, and every other Option dataset and neutralization y = 0 -- a posterior that
    all but forbids the rest."""
    rows = {}
    opt = sorted({v["dataset"] for v in LABS.values() if v["category"] == "Option" and v.get("dataset")})
    for d in opt:
        good = d == "ds00"
        for i in range(200):
            a = "%s_%d" % (d, i)
            sh = 1.9 if good else 0.1
            neut = "INDUSTRY" if good else ("STATISTICAL", "SUBINDUSTRY")[i % 2]
            rows[a] = {"alpha": a, "sharpe": sh, "settings": {"neutralization": neut},
                       "checks": [{"name": "LOW_SHARPE", "result": "FAIL", "limit": 1.58, "value": sh}],
                       "meta": {"hypothesis": "gen:post_%s" % d, "legs": [{"dataset": d}]}}
    return ST.build(rows)


def test_a_skewed_posterior_moves_posterior_draws_and_leaves_floor_draws_at_base_weight():
    """Draw-5 gen G2 (T1-T3, and X03 for the settings): theta_d multiplies the base field weight in posterior
    draws only; a floor draw uses base weights and uniform settings (D35, §3.2)."""
    st = _skewed_state()
    assert st.posterior.dataset("ds00") == (201, 1) and st.posterior.dataset("ds05") == (1, 201)
    pool = P.FieldPool(LABS, "USA", 1)
    items, cum, _ = pool._table("Option", None)
    base = sum(pool.base(v) for v in items if v["dataset"] == "ds00") / cum[-1]
    assert 0.15 < base < 0.35                                    # ds00's share under base weights
    res = PR.propose(st, LABS, [CELLS[0]], 1000, seed=21, cell_cap=1000)
    by = collections.defaultdict(list)
    for c in res["candidates"]:
        by[c["meta"]["gen_draw"]].append(c)
    assert len(by["floor"]) == 200 and len(by["posterior"]) == 800

    def share(cs, f):
        return sum(1 for c in cs if f(c)) / len(cs)
    fav = lambda c: c["meta"]["legs"][0]["dataset"] == "ds00"                      # noqa: E731
    ind = lambda c: c["settings"]["neutralization"] == "INDUSTRY"                   # noqa: E731
    assert share(by["posterior"], fav) > 0.9                     # measured 0.989
    assert abs(share(by["floor"], fav) - base) < 0.1             # measured 0.245 against 0.231
    assert share(by["posterior"], ind) > 0.9
    assert abs(share(by["floor"], ind) - 1 / 3) < 0.1


def test_plan_time_d18_refuses_a_twin_of_an_accepted_post():
    first = PR.propose(EMPTY, LABS, CELLS, 40, seed=7, field_datasets=fd)["candidates"][0]
    posted = ST.build({}, [{"alpha": "P1", "http": 201, "formula": first["formula"]}], {})
    res = PR.propose(posted, LABS, CELLS, 40, seed=7, field_datasets=fd)
    assert res["counts"]["d18-post-twin"] >= 1
    si = FP.StructuralIndex()
    si.register(first["formula"], "P1")
    assert not any(si.is_dup(c["formula"])[0] for c in res["candidates"])


def _rows_for(formula, fam, n, passed_at=None, sharpe=0.5):
    """n journal rows of one formula under family `fam` (no grammar levels, so the posterior -- and so the
    round's draws -- stay those of the empty state)."""
    rows = {}
    for i in range(n):
        ok = passed_at is not None and i == passed_at
        cks = [{"name": "LOW_SHARPE", "result": "PASS" if ok else "FAIL", "limit": 1.58, "value": sharpe},
               {"name": "IS_LADDER_SHARPE", "result": "PASS", "year": 5}]
        rows["%s%d" % (fam, i)] = {"alpha": "%s%d" % (fam, i), "formula": formula, "sharpe": 1.9 if ok else sharpe,
                                   "checks": cks, "settings": {"region": "USA", "delay": 1, "universe": "TOP3000"},
                                   "meta": {"hypothesis": "gen:" + fam}}
    return rows


def _stopped_rows(state, fam, formula):
    """Journal rows (and history, curves) that put family `fam` of `formula` in `state` (D36)."""
    rows = {}
    if state == "DEAD":
        rows = _rows_for(formula, fam, 40)
    elif state == "PASSED_EXHAUSTED":
        rows = _rows_for(formula, fam, 41, passed_at=0)
    elif state == "LADDER_DEAD":
        rows = _rows_for(formula, fam, 40, sharpe=1.2)
        for r in rows.values():
            r["checks"][1].update(result="FAIL", year=2)
    history, curves = [], {}
    if state == "PNL_STOP":
        rows = _rows_for(formula, fam, 1)
        rng = random.Random(33)
        post = _walk(rng)
        history = [{"alpha": "POST", "http": 201, "formula": "rank(close)"}]
        curves = {"POST": _curve(post), fam + "0": _curve([p + 0.2 * rng.gauss(0, 1) for p in post])}
    return rows, history, curves


@pytest.mark.parametrize("state", ["DEAD", "PASSED_EXHAUSTED", "LADDER_DEAD", "PNL_STOP"])
def test_no_refusing_family_state_admits_a_twin(state):
    """Every D36 state but OPEN / PASSED refuses (draw-5 gen exec survivors X16-X18 read DEAD only)."""
    first = PR.propose(EMPTY, LABS, CELLS, 40, seed=8, field_datasets=fd)["candidates"][0]
    st = ST.build(*_stopped_rows(state, "famS", first["formula"]))
    assert st.verdict("famS", "USA/d1")[0] == state
    res = PR.propose(st, LABS, CELLS, 40, seed=8, field_datasets=fd)
    assert res["counts"]["family-" + state] >= 1
    assert all(c["meta"]["hypothesis"] != "gen:famS" for c in res["candidates"])


def test_a_dead_familys_twins_are_never_planned():
    first = PR.propose(EMPTY, LABS, CELLS, 40, seed=8, field_datasets=fd)["candidates"][0]
    dead = ST.build(_rows_for(first["formula"], "famD", 40), [], {})
    assert dead.verdict("famD", "USA/d1") == ("DEAD", 0)
    res = PR.propose(dead, LABS, CELLS, 40, seed=8, field_datasets=fd)
    assert res["counts"]["family-DEAD"] >= 1
    assert all(c["meta"]["hypothesis"] != "gen:famD" for c in res["candidates"])


def test_no_family_takes_more_than_its_room_in_one_round():
    tiny = synthetic_labels(n_ds=3, per_ds=6)
    res = PR.propose(ST.build({}, [], {}), tiny, [CELLS[0]], 400, seed=9, cell_cap=400)
    per = collections.Counter(c["meta"]["hypothesis"] for c in res["candidates"])
    assert res["counts"].get("family-room", 0) > 0 and max(per.values()) == 40      # binds, and at 40


def _trigger_rows(n, fam_prefix="famR"):
    rows = {}
    for i, (core, s) in enumerate(_draws(n, seed=40 + n)):
        cks = [{"name": nm, "result": "FAIL" if nm == "LOW_FITNESS" else "PASS"}
               for nm in ("LOW_SHARPE", "LOW_FITNESS", "IS_LADDER_SHARPE", "CONCENTRATED_WEIGHT")]
        cks[0].update(limit=1.58, value=1.5)
        rows["T%d" % i] = {"alpha": "T%d" % i, "formula": core["formula"], "sharpe": 1.5, "checks": cks, "settings": s,
                           "meta": {"hypothesis": "gen:%s%d" % (fam_prefix, i), "gen_route": "draw", "legs": core["legs"],
                                    "gen_alpha": core["alpha"], "category": "Option"}}
    return rows


def test_repairs_follow_the_coin_oldest_first_within_ten_percent():
    rows = _trigger_rows(8)
    st = ST.build(rows, [], {})
    assert [r["alpha"] for r in st.triggers] == ["T%d" % i for i in range(8)]
    res = PR.propose(st, LABS, CELLS, 100, seed=10, field_datasets=fd)
    reps = [c for c in res["candidates"] if c["meta"]["gen_route"] == "repair"]
    assert 0 < len(reps) <= 10
    heads = [r["alpha"] for r in st.triggers if RP.coin(r["formula"])]
    assert reps[0]["meta"]["repair_of"] == heads[0]              # oldest coin-true trigger first
    assert {c["meta"]["repair_of"] for c in reps} <= set(heads)
    for c in reps:
        base = rows[c["meta"]["repair_of"]]
        assert c["formula"] == base["formula"] and c["meta"]["hypothesis"] == base["meta"]["hypothesis"]
        assert c["settings"] in RP.grid(base["settings"])
    tails = [r for r in st.triggers if not RP.coin(r["formula"])]
    assert tails and not {c["meta"]["repair_of"] for c in reps} & {r["alpha"] for r in tails}


def test_a_repair_obeys_its_familys_spending_rules():
    rows = _trigger_rows(8)
    head = next(a for a, r in rows.items() if RP.coin(r["formula"]))
    fam = FM.family_of(rows[head])
    rows.update(_rows_for(rows[head]["formula"], fam, 40))      # the trigger's family: 41 rows, best 0.5
    for r in list(rows.values()):
        if FM.family_of(r) == fam:
            r["sharpe"] = 0.5
            r["checks"] = [dict(c, value=0.5) if c["name"] == "LOW_SHARPE" else c for c in r["checks"]]
    st = ST.build(rows, [], {})
    assert st.verdict(fam, "USA/d1")[0] == "DEAD"
    res = PR.propose(st, LABS, CELLS, 100, seed=10, field_datasets=fd)
    assert not any(c["meta"].get("repair_of") == head for c in res["candidates"])
    assert res["counts"]["family-DEAD"] >= 1


def test_neighbours_for_every_handed_alpha_bypass_the_family_stops_and_d18():
    rows = _trigger_rows(3, fam_prefix="famN")
    for r in rows.values():
        r["checks"] = [dict(c, result="PASS") for c in r["checks"]]
    rng = random.Random(12)
    post = _walk(rng)
    history = [{"alpha": "T0", "http": 201, "formula": rows["T0"]["formula"]}]          # T0 itself was POSTed
    st = ST.build(rows, history, {"T0": _curve(post)})
    assert st.verdict("famN0", "USA/d1") == ("PNL_STOP", 0)
    res = PR.propose(st, LABS, CELLS, 50, seed=13, field_datasets=fd, handed=list(rows.values()))
    nb = [c for c in res["candidates"] if c["meta"]["gen_route"] == "neighbour"]
    assert collections.Counter(c["meta"]["neighbour_of"] for c in nb) == {"T0": 2, "T1": 2, "T2": 2}
    for c in nb:
        base = rows[c["meta"]["neighbour_of"]]
        assert c["formula"] == base["formula"]
        assert sum(str(c["settings"][k]) != str(base["settings"][k]) for k in ("decay", "neutralization", "truncation")) == 1
    assert res["candidates"][:6] == nb                           # first in the round


def _passes(n, fam_prefix="famN"):
    """n generated harvest-pass rows, alphas N0.. (the trigger rows with every check PASS)."""
    rows = {}
    for i, r in enumerate(_trigger_rows(n, fam_prefix=fam_prefix).values()):
        rows["N%d" % i] = dict(r, alpha="N%d" % i, checks=[dict(c, result="PASS") for c in r["checks"]])
    return rows


def test_every_route_is_stamped_and_counted():
    """The shared interface: meta.gen_route is "fresh" for a draw, "neighbour" for a D51 neighbour and "repair"
    for a D37 repair; by_route counts them; only a fresh draw carries gen_draw, only a row-derived one its link."""
    rows = dict(_trigger_rows(8), **_passes(2))
    st = ST.build(rows, [], {})
    res = PR.propose(st, LABS, CELLS, 100, seed=10, field_datasets=fd, handed=list(_passes(2).values()))
    routes = collections.Counter(c["meta"]["gen_route"] for c in res["candidates"])
    assert set(routes) == set(PR.ROUTES) == {"fresh", "neighbour", "repair"}
    assert res["by_route"] == dict(routes) and routes["neighbour"] == 4
    for c in res["candidates"]:
        m = c["meta"]
        assert ("gen_draw" in m) == (m["gen_route"] == "fresh")
        assert ("neighbour_of" in m) == (m["gen_route"] == "neighbour")
        assert ("repair_of" in m) == (m["gen_route"] == "repair")
        assert m["arm"] == "gen" and m["gen_state"] == st.sha


def test_handed_rows_are_kept_only_when_provable_and_once_per_alpha():
    """Draw-5 gen N2: a library row, a generated row that is not harvest-pass and a repeat get no neighbours."""
    good = _passes(1)["N0"]
    lib = dict(good, alpha="L1", meta={"hypothesis": "usa_library_hyp"})
    failing = dict(good, alpha="F1", checks=[dict(c, result="FAIL") for c in good["checks"]])
    pending = dict(good, alpha="P1", checks=[dict(c, result="PENDING") for c in good["checks"]])
    res = PR.propose(EMPTY, LABS, [], 10, seed=17, handed=[lib, good, failing, dict(good), pending])
    assert [c["meta"]["neighbour_of"] for c in res["candidates"]] == ["N0", "N0"]
    assert res["counts"]["handed-dropped"] == 3 and res["counts"]["handed-repeat"] == 1


def test_a_neighbour_shortfall_is_counted_and_a_budget_cut_is_not():
    """Draw-5 gen N3: with 3 of the 4 one-setting variants already simulated, 1 comes back and the missing one
    is counted; a round whose n runs out plans the rest next round and counts nothing."""
    row = _passes(1)["N0"]
    variants = RP.one_setting_variants(row["settings"])
    seen = {candidate_id(row["formula"], s) for s in variants[:3]}
    res = PR.propose(EMPTY, LABS, [], 10, seed=18, handed=[row], seen_ids=seen)
    assert len(res["candidates"]) == 1 and res["counts"]["neighbour-short"] == 1
    cut = PR.propose(EMPTY, LABS, [], 1, seed=18, handed=[row])
    assert len(cut["candidates"]) == 1 and "neighbour-short" not in cut["counts"]


def test_an_existing_in_cohort_neighbour_counts_and_an_out_of_cohort_one_does_not():
    """Draw-5 gen G1 through propose (and exec survivor X22: the state's neighbour index is read)."""
    row = _passes(1)["N0"]
    row["meta"].update(pipeline_version="V1", run_config="rc1")
    s = RP.one_setting_variants(row["settings"])[0]
    sib = dict(row, alpha="S1", settings=s, sharpe=1.4, meta=dict(row["meta"]))
    same = PR.propose(ST.build({"N0": row, "S1": sib}), LABS, [], 10, seed=19, handed=[row])
    assert len(same["candidates"]) == 1
    sib["meta"] = dict(row["meta"], pipeline_version="V2")
    other = PR.propose(ST.build({"N0": row, "S1": sib}), LABS, [], 10, seed=19, handed=[row])
    assert len(other["candidates"]) == 2
    assert s not in [c["settings"] for c in other["candidates"]]       # the out-of-cohort one is not re-planned


def test_neighbours_and_repairs_are_charged_to_their_cell():
    """Draw-5 gen N1: by_cell used to leave neighbours and repairs out (40 candidates, 2 neighbours: sum 38)."""
    row = _passes(1)["N0"]                                      # USA / TOP3000 / d1, category Option = CELLS[0]
    res = PR.propose(EMPTY, LABS, CELLS, 40, seed=20, field_datasets=fd, handed=[row])
    assert res["by_route"].get("neighbour") == 2 and sum(res["by_cell"].values()) == 40
    only = PR.propose(EMPTY, LABS, CELLS, 2, seed=20, field_datasets=fd, handed=[row])
    assert only["by_cell"] == {CELLS[0]: 2}
    capped = PR.propose(EMPTY, LABS, CELLS[:1], 40, seed=20, field_datasets=fd, handed=[row], cell_cap=10)
    assert capped["by_cell"] == {CELLS[0]: 10} and capped["by_route"] == {"neighbour": 2, "fresh": 8}
    away = PR.propose(EMPTY, LABS, CELLS[1:2], 5, seed=20, field_datasets=fd, handed=[row])
    assert away["counts"]["uncharged-neighbour"] == 2 and away["by_cell"] == {CELLS[1]: 3}
    rows = _trigger_rows(8)
    st = ST.build(rows, [], {})
    rep = PR.propose(st, LABS, CELLS, 100, seed=10, field_datasets=fd)
    assert rep["by_route"].get("repair", 0) > 0 and sum(rep["by_cell"].values()) == len(rep["candidates"])


def test_the_callers_chain_runs_last_and_the_inputs_are_not_touched():
    calls = []

    def accept(c):
        calls.append(c["id"])
        return len(calls) % 2 == 0

    taken = {CELLS[0]: 25}
    n_fam, sha = len(EMPTY.families), EMPTY.sha
    res = PR.propose(EMPTY, LABS, CELLS[:2], 50, seed=14, field_datasets=fd, taken=taken, cell_cap=30, accept=accept)
    assert res["counts"]["accept-refused"] == len(calls) - len(res["candidates"]) > 0
    assert [c["id"] for c in res["candidates"]] == calls[1::2]
    assert res["by_cell"][CELLS[0]] <= 5 and res["by_cell"][CELLS[1]] <= 30
    assert taken == {CELLS[0]: 25} and len(EMPTY.families) == n_fam and EMPTY.sha == sha
    base = PR.propose(EMPTY, LABS, CELLS[:2], 50, seed=14, field_datasets=fd)
    seen = {base["candidates"][0]["id"]}                          # "already in the journal"
    res2 = PR.propose(EMPTY, LABS, CELLS[:2], 50, seed=14, field_datasets=fd, seen_ids=seen)
    assert seen.isdisjoint(c["id"] for c in res2["candidates"]) and res2["counts"]["duplicate"] >= 1


def test_a_cell_nothing_serves_or_without_a_universe_is_skipped():
    empty = [C.Cell("USA", 1, "Institutions", "TOP3000", 0, 0, 1.0, 0, (), 1.0),
             C.Cell("USA", 1, "Option", None, 0, 0, 1.0, 0, (), 1.0)]
    res = PR.propose(EMPTY, LABS, empty, 50, seed=15)
    assert res["candidates"] == [] and res["n_draws"] == 0
    assert res["counts"] == {"cell-unserved": 1, "cell-no-universe": 1}          # draw-5 gen N10: counted


def test_a_row_derived_candidate_still_meets_the_structural_gate_and_the_exclusions():
    """Draws are typed by construction, so only a row-derived candidate can exercise the tripwires: a journal row
    whose formula the gate refuses (g02_f00 is sparse and has no density operator: H4) or that an exclusion hits."""
    settings = P.draw_settings(random.Random(1), PO.floor_weights()[0], "USA", "TOP3000", 1)
    base = {"alpha": "X", "sharpe": 2.0, "settings": settings, "meta": {"hypothesis": "gen:famX"},
            "checks": [{"name": "LOW_SHARPE", "result": "PASS"}]}          # harvest-pass: handed rows must be
    bad = dict(base, formula="multiply(rank(g02_f00), rank(g01_f01))")
    assert not runner_structurally_ok(LABS)({"formula": bad["formula"], "settings": bad["settings"]})
    ex = dict(base, alpha="Y", formula="signed_power(multiply(rank(g00_f01), rank(g01_f01)), 2)")
    res = PR.propose(EMPTY, LABS, [], 10, seed=16, handed=[bad, ex])
    assert res["candidates"] == []
    assert res["counts"] == {"structure-refused": 2, "excluded": 2, "neighbour-short": 4}
