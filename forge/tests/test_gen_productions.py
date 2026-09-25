"""forge.gen.productions: the §2.2 grammar, typed by construction, and the §2.3 exclusions.

The synthetic label set below is shared by every test_gen_*.py file (hermetic: CI carries no fetched/).
It is built to exercise every typing constraint: VECTOR fields, sparse fields, six kind/unit pairs per
dataset, three fields each (so a three-field spread-ratio exists, H1 partners exist and H1 traps exist),
description- and prior-signed fields, and flags that must never be drawn.
"""
import json
import pathlib
import random

import pytest

from forge import cells as C
from forge import signature as S
from forge import typed as T
from forge.gen import posterior as PO
from forge.gen import productions as P

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATS = ("Option", "Short Interest", "Fundamental", "Analyst", "Sentiment")
KINDS = (("level", "currency"), ("level", "shares"), ("ratio", "ratio"), ("return", "return"), ("score", "score"),
         ("count", "count"))
CELLS = [C.Cell("USA", 1, cat, "TOP3000", 0, 0, 1.0, 0, (), 1.0) for cat in CATS]
#: The four accepted forge POSTs (state/forge/submitted.jsonl, read 2026-09-23).
POSTS = {
    "vRk095rv": "multiply(multiply((1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 10), sector)), group_rank(ts_backfill(operating_income / equity, 126), sector)), (1 - group_rank(ts_rank((income - cashflow_op) / abs(assets), 126), sector)))",
    "kqVbg1xP": "multiply(group_rank(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 5), sector), (1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 20), subindustry)))",
    "vRk1J2jd": "multiply((1 - group_rank(ts_rank(ts_backfill(diff_current_vs_hist_price_ratio_earnings, 21), 252), industry)), group_rank(ts_backfill(operating_income / assets, 126), industry))",
    "rK5RGeqa": "multiply(multiply(group_rank(ts_sum(add(directional_significant_value_1, 0, filter=true), 60), sector), group_rank(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 10), industry)), group_rank(ts_rank(operating_income / assets, 126), industry))",
}


def synthetic_labels(n_ds=40, per_ds=18, region="USA/d1"):
    labs = {}
    for i in range(n_ds):
        for j in range(per_ds):
            kind, unit = KINDS[(i + j) % len(KINDS)]
            fid = "g%02d_f%02d" % (i, j)
            sign = "+-"[(i * 7 + j) % 2] if (i + j) % 5 else "unstated"
            src = ("description" if (i + 2 * j) % 3 == 0 else "domain-prior") if sign != "unstated" else "unstated"
            vec = (i * j) % 11 == 5
            v = {"id": fid, "dataset": "ds%02d" % i, "category": CATS[i % len(CATS)],
                 "domain": "dom%02d" % ((i + j % 2) % 17), "kind": kind, "unit": unit, "sign": sign,
                 "sign_source": src, "time": "daily", "sparsity": ("dense", "medium", "sparse")[(i + 3 * j) % 3],
                 "structure": "VECTOR" if vec else "MATRIX", "users": (i * 13 + j) % 50, "regions": [region],
                 "by_region": {}}
            if vec:
                v.update(vec_reducers=["vec_avg", "vec_max"], vec_after={"vec_avg": kind, "vec_max": kind})
            labs[fid] = v
    for i in range(3):                                   # flags: never a primary, never a partner
        fid = "flagfield_%d" % i
        labs[fid] = {"id": fid, "dataset": "ds00", "category": "Option", "domain": "dom00", "kind": "flag", "unit": "bool",
                     "sign": "+", "sign_source": "description", "time": "daily", "sparsity": "dense", "structure": "MATRIX",
                     "users": 0, "regions": [region], "by_region": {}}
    return labs


LABS = synthetic_labels()


def _draws(n, seed, labels=LABS, category="Option"):
    """n raw draws (no rejection by the structural gate anywhere on this path), alternating floor weights and
    random posterior-like weights so both modes are exercised."""
    rng = random.Random(seed)
    pool = P.FieldPool(labels, "USA", 1)
    Wf, _ = PO.floor_weights()
    post = PO.Posterior([])
    Wp, theta = PO.round_weights(post, rng, pool.datasets)
    out = []
    for i in range(n * 3):
        W, th = (Wf, None) if i % 2 else (Wp, theta)
        core = P.draw(rng, pool, W, th, category)
        if core is not None:
            out.append((core, P.draw_settings(rng, W, "USA", "TOP3000", 1)))
        if len(out) >= n:
            break
    return out


def test_every_raw_draw_passes_the_structural_gate_by_construction():
    """productions.draw never asks the judge; the judge must accept every draw anyway (H1-H4 by construction)."""
    draws = _draws(3000, seed=1)
    assert len(draws) == 3000
    for core, s in draws:
        ok, why = P.structurally_ok(core["formula"], s, LABS)
        assert ok, (why, core["formula"])
        assert P.exclusion_reason(core["formula"], s) is None, core["formula"]


def test_depth_is_the_parse_nesting_and_pins_the_four_posts():
    """§2.3's depth: operator nesting of typed.parse's tree. The accepted POSTs read 6, 5, 5, 5."""
    assert [P.depth(T.parse(POSTS[a])) for a in ("vRk095rv", "kqVbg1xP", "vRk1J2jd", "rK5RGeqa")] == [6, 5, 5, 5]
    for core, _ in _draws(1000, seed=2):
        assert P.depth(T.parse(core["formula"])) <= P.MAX_DEPTH


def test_exclusions_fire_on_each_excluded_construction_and_on_none_of_the_posts():
    base = POSTS["kqVbg1xP"]
    s = {"region": "USA", "delay": 1, "decay": 4}
    assert "signed_power" in P.exclusion_reason("signed_power(%s, 2)" % base, s)
    assert "vector_neut" in P.exclusion_reason("vector_neut(%s, rank(close))" % base, s)
    assert "negated" in P.exclusion_reason("if_else(greater(rank(x), 0.5), -group_rank(y, sector), 0)", s)
    assert "decay 16" in P.exclusion_reason(base, dict(s, decay=16))
    deep = "rank(rank(rank(rank(rank(rank(rank(x)))))))"
    assert "depth 7" in P.exclusion_reason(deep, s)
    assert all(P.exclusion_reason(f, s) is None for f in POSTS.values())


def test_no_draw_uses_an_excluded_operator_a_flag_or_decay_16():
    for core, s in _draws(2000, seed=3):
        ops = P._ops(T.parse(core["formula"]), set())
        assert not ops & {"signed_power", "vector_neut", "reverse"}
        assert "flagfield" not in core["formula"]
        assert s["decay"] in P.DECAY and s["truncation"] in P.TRUNC and s["neutralization"] in P.NEUT


def test_sparse_fields_only_under_a_density_route_and_change_ops_never_on_a_ratio():
    for core, _ in _draws(2000, seed=4):
        for leg in core["legs"]:
            if any(LABS[f]["sparsity"] == "sparse" for f in leg["fields"]):
                assert leg["ts"] in ("ts_backfill", "ts_sum_event"), leg
            kind = "ratio" if leg["sig"] in ("ratio", "spread_ratio") else P.effective(LABS[leg["field"]])[0]
            if leg["ts"] == "ts_delta" or (leg["tier_u"] in T.CHANGE):
                assert kind not in T.NON_DIFF, leg


def test_multi_field_sig_is_one_dataset_one_unit_and_a_scale_denominator():
    """§2.2: two- and three-field SIG draws its fields from ONE dataset (all 65 such nodes in the 37 passes did)."""
    seen = set()
    for core, _ in _draws(2000, seed=5):
        for leg in core["legs"]:
            seen.add(leg["sig"])
            fs = [LABS[f] for f in leg["fields"]]
            assert len({f["dataset"] for f in fs}) == 1
            assert len({P.effective(f)[1] for f in fs}) == 1
            if leg["sig"] in ("ratio", "spread_ratio"):
                assert P.effective(fs[-1])[0] in P.SCALE_KINDS
    assert seen == set(P.SIG)


def test_first_leg_serves_the_cell_and_later_legs_are_new_domains():
    for core, _ in _draws(1000, seed=6, category="Fundamental"):
        legs = core["legs"]
        assert LABS[legs[0]["field"]]["category"] == "Fundamental"
        doms = [L["domain"] for L in legs]
        assert len(set(doms)) == len(doms)


def test_orientation_is_the_description_sign_else_a_recorded_coin():
    both = set()
    for core, _ in _draws(1500, seed=7):
        for leg in core["legs"]:
            a = LABS[leg["sign_field"]]
            if a["sign_source"] == "description":
                assert leg["sign_source"] == "description" and leg["orientation"] == a["sign"]
            else:
                assert leg["sign_source"] == "coin"
                both.add(leg["orientation"])
    assert both == {"+", "-"}


def test_tier_u_only_with_floor_weights_and_it_is_reached():
    rng = random.Random(8)
    pool = P.FieldPool(LABS, "USA", 1)
    Wp, theta = PO.round_weights(PO.Posterior([]), rng, pool.datasets)
    assert P.TS_TIER_U not in Wp["TS"]
    Wf, _ = PO.floor_weights()
    posterior_tier = sum(L["ts"] == P.TS_TIER_U for _ in range(500)
                         for core in [P.draw(rng, pool, Wp, theta, "Option")] if core for L in core["legs"])
    floor_ops = {L["tier_u"] for _ in range(1500) for core in [P.draw(rng, pool, Wf, None, "Option")] if core
                 for L in core["legs"] if L["ts"] == P.TS_TIER_U}
    assert posterior_tier == 0
    assert len(floor_ops) >= 8 and floor_ops <= set(P.TIER_U)


def test_tier_u_is_derived_from_typed_and_the_platform_operator_list():
    """TIER_U = (typed.SMOOTH | DISPERSION | CHANGE) - the TS levels, kept where operators.json defines
    `op(x, d)` with every further argument defaulted. The hermetic half always runs; the file half needs
    fetched/rc/operators.json."""
    main = {"ts_mean", "ts_rank", "ts_backfill", "ts_sum", "ts_zscore", "ts_delta"}
    assert set(P.TIER_U) <= (T.SMOOTH | T.DISPERSION | T.CHANGE) - main
    path = ROOT / "fetched/rc/operators.json"
    if not path.exists():
        pytest.skip("fetched/rc/operators.json absent (hermetic tier)")
    import re
    derived = set()
    for o in json.load(open(path)):
        name = o.get("name")
        if name not in (T.SMOOTH | T.DISPERSION | T.CHANGE) - main or o.get("category") != "Time Series":
            continue
        args = [a.strip() for a in re.sub(r"^[a-z_]+\(|\)\s*$", "", o["definition"]).split(",")]
        if len(args) >= 2 and args[0] == "x" and args[1] == "d" and all("=" in a for a in args[2:]):
            derived.add(name)
    assert derived == set(P.TIER_U)


def test_a_draw_is_a_function_of_the_rng_state():
    a = [c["formula"] for c, _ in _draws(300, seed=9)]
    b = [c["formula"] for c, _ in _draws(300, seed=9)]
    c = [c["formula"] for c, _ in _draws(300, seed=10)]
    assert a == b and a != c


def test_candidate_carries_the_section_4_1_contract_and_the_catalogue_signature():
    core, s = _draws(1, seed=11)[0]
    fd = {fid: v["dataset"] for fid, v in LABS.items()}
    cand = P.candidate(core, s, "Option", "abc123def456", "draw", "0" * 16, fd)
    m = cand["meta"]
    for k in ("hypothesis", "category", "field", "legs", "arm", "generator", "gen_state", "composite"):
        assert k in m, k
    assert m["hypothesis"] == "gen:abc123def456" and m["composite"] == 1 and m["arm"] == "gen"
    assert all({"orientation", "sign_source"} <= set(L) for L in m["legs"])
    sig = S.signature(cand["formula"], "USA", 1, mechanism=m["hypothesis"], field_datasets=fd)
    assert cand["signature"]["key"] == sig["key"] and cand["signature"]["mechanism_key"] == sig["mechanism_key"]
    assert set(cand["signature"]["datasets"]) == {L["dataset"] for L in m["legs"]} | {
        LABS[f]["dataset"] for L in m["legs"] for f in L["fields"]}
    from forge.factory import candidate_id
    assert cand["id"] == candidate_id(cand["formula"], s)


def test_from_row_keeps_the_generator_meta_and_drops_the_old_runs_stamps():
    core, s = _draws(1, seed=12)[0]
    c0 = P.candidate(core, s, "Option", "fam000000001", "draw", "a" * 16)
    row = {"alpha": "A1", "formula": c0["formula"], "settings": s,
           "meta": dict(c0["meta"], pipeline_version="old", run_config="old", seed=1, cand="x", forge=1)}
    c1 = P.from_row(row, dict(s, decay={4: 8, 8: 4}[s["decay"]]), "neighbour", "b" * 16, neighbour_of="A1")
    m = c1["meta"]
    assert m["gen_state"] == "b" * 16 and m["gen_route"] == "neighbour" and m["neighbour_of"] == "A1"
    assert m["hypothesis"] == c0["meta"]["hypothesis"] and m["legs"] == c0["meta"]["legs"]
    assert not {"pipeline_version", "run_config", "seed", "cand", "forge"} & set(m)


def test_a_minus_leg_is_written_one_minus_and_a_plus_leg_is_not():
    """Draw-5 gen G2 (O1: orientation never applied; O2: applied inverted). Both left every gen test green."""
    rng = random.Random(13)
    pool = P.FieldPool(LABS, "USA", 1)
    Wf, _ = PO.floor_weights()
    seen = {"+": 0, "-": 0}
    for _ in range(3000):
        leg = P.draw_leg(rng, pool, Wf, None, None, set(), 5)
        if leg is None:
            continue
        assert leg["formula"].startswith("(1 - ") == (leg["orientation"] == "-"), leg["formula"]
        if leg["orientation"] == "-":
            assert leg["formula"].endswith(")") and leg["formula"].count("(1 - ") == 1
        seen[leg["orientation"]] += 1
    assert seen["+"] > 300 and seen["-"] > 300


def _vec(fid, reducers, kind="level", unit="currency", ds="dsV", after=None, sign="+"):
    return {"id": fid, "dataset": ds, "category": "Option", "domain": "domV", "kind": kind, "unit": unit, "sign": sign,
            "sign_source": "description", "time": "daily", "sparsity": "dense", "structure": "VECTOR", "users": 1,
            "regions": ["USA/d1"], "by_region": {}, "vec_reducers": list(reducers),
            "vec_after": after if after is not None else {r: kind for r in reducers}}


def test_effective_agrees_with_typed_on_every_vector_reducer():
    """Draw-5 gen N10: effective() read vec_stddev / vec_range as ("dispersion", the field's unit); typed refuses
    both outright in the structural gate (H4), and reads the other reducers as effective() does."""
    for red in sorted(T.VEC):
        labs = {"vf": _vec("vf", [red], after={})}
        judge = T.Judge(labs, "USA/d1", True)
        got = P.effective(labs["vf"])
        ok = P.structurally_ok("rank(%s(vf))" % red, {"region": "USA", "delay": 1}, labs)[0]
        if red in T.DISPERSION:
            assert got is None and ok is False, red
        else:
            t = judge.infer(T.parse("%s(vf)" % red), "dir")
            assert got == (t["kind"], t["unit"], "%s(vf)" % red) and ok is True, (red, got, t)


def test_the_pool_offers_no_field_the_gate_refuses_and_no_reduced_non_directional_primary():
    """Draw-5 gen N10 (a vec_stddev-first VECTOR field is neither primary nor partner), exec P02 (a VECTOR field
    reduced to a count is not a primary) and P03 (a flag or code is never a partner, whatever its unit)."""
    labs = {"a": dict(_vec("a", ["vec_avg"]), structure="MATRIX"),
            "disp": _vec("disp", ["vec_stddev"]),
            "cnt": _vec("cnt", ["vec_count"], after={"vec_count": "count"}),
            "flg": dict(_vec("flg", ["vec_avg"], kind="flag"), structure="MATRIX", sign="unstated")}
    pool = P.FieldPool(labs, "USA", 1)
    assert [v["id"] for v in pool.primaries] == ["a"]
    rng = random.Random(3)
    got = {(pool.partner(rng, labs["a"], {"a"}, scale_only=False) or {}).get("id") for _ in range(50)}
    assert got == {None}                     # disp (unit currency) and flg (unit currency) are never offered


def test_windows_and_the_gate_line_are_the_grammars():
    """Exec survivors P13 (ts_backfill off 126), P21 (the gate's 0.5), P32 (TS=none wraps nothing), P33 (a TIER_U
    window comes from W_SHORT or W_LONG) and P20 (only the FIRST leg is held to the cell's category)."""
    assert P.BACKFILL_W == 126
    tier_w, cats, gates = set(), set(), 0
    rng = random.Random(14)
    pool = P.FieldPool(LABS, "USA", 1)
    Wf, _ = PO.floor_weights()
    for _ in range(2500):
        core = P.draw(rng, pool, Wf, None, "Option")
        if core is None:
            continue
        f = core["formula"]
        if core["alpha"] == "gate":
            gates += 1
            assert f.startswith("if_else(greater(") and f.endswith(", 0)") and ", 0.5), " in f, f
        if "ts_backfill(" in f:
            assert all(m.endswith(", 126)") for m in _calls(f, "ts_backfill")), f
        for L in core["legs"]:
            if L["ts"] == P.TS_TIER_U:
                tier_w.update(w[0] for w in L["windows"][:1])
        cats.update(LABS[L["field"]]["category"] for L in core["legs"][1:])
    assert gates > 100 and tier_w == {"W_SHORT", "W_LONG"} and len(cats) > 1
    for _ in range(3000):                                            # TS = none: the SIG itself under SCORE
        leg = P.draw_leg(rng, pool, Wf, None, None, set(), 5)
        if leg is not None and leg["ts"] == "none":
            inner = leg["formula"][len("(1 - "):-1] if leg["orientation"] == "-" else leg["formula"]
            assert not any(op in inner for op in ("ts_mean(", "ts_backfill(", "ts_zscore(", "ts_delta(", "ts_sum(")), inner
            break
    else:
        raise AssertionError("no TS=none leg drawn")


def _calls(formula, op):
    """Every `op(...)` substring of a formula, balanced on parentheses."""
    out, i = [], formula.find(op + "(")
    while i >= 0:
        depth, j = 0, i + len(op)
        while True:
            depth += {"(": 1, ")": -1}.get(formula[j], 0)
            j += 1
            if depth == 0:
                break
        out.append(formula[i:j])
        i = formula.find(op + "(", i + 1)
    return out


def test_a_spread_never_pairs_a_field_with_itself():
    """Exec survivor P34: on a label set where no dataset holds a second field of a unit, a spread cannot be
    formed, never degraded to `a - a`."""
    tiny = synthetic_labels(n_ds=3, per_ds=6)
    rng = random.Random(15)
    pool = P.FieldPool(tiny, "USA", 1)
    Wf, _ = PO.floor_weights()
    n = 0
    for _ in range(1500):
        core = P.draw(rng, pool, Wf, None, "Option")
        for L in (core or {}).get("legs", []):
            n += 1
            assert len(set(L["fields"])) == len(L["fields"]), L
    assert n > 100


def test_the_structural_gate_is_asked_for_the_candidates_own_region():
    """Exec survivor P24: structurally_ok reads the field in the settings' region/delay (typed reads
    by_region); judged as USA/d1 for every cell, a field sparse only in EUR would pass unguarded."""
    labs = synthetic_labels(n_ds=3, per_ds=6)
    labs["g00_f00"] = dict(labs["g00_f00"], regions=["USA/d1", "EUR/d1"], by_region={"EUR/d1": {"sparsity": "sparse"}})
    f = "multiply(rank(g00_f00), rank(g01_f02))"
    assert P.structurally_ok(f, {"region": "USA", "delay": 1}, labs)[0] is True
    assert P.structurally_ok(f, {"region": "EUR", "delay": 1}, labs)[0] is False


def test_candidate_stamps_the_route_and_the_draw_mode():
    """The shared interface: meta.gen_route; meta.gen_draw only when the draw mode is given."""
    core, s = _draws(1, seed=16)[0]
    c = P.candidate(core, s, "Option", "fam000000002", "fresh", "c" * 16, draw_mode="floor")
    assert c["meta"]["gen_route"] == "fresh" and c["meta"]["gen_draw"] == "floor"
    assert "gen_draw" not in P.candidate(core, s, "Option", "fam000000002", "fresh", "c" * 16)["meta"]
