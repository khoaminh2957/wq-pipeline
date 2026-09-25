"""Suite for forge/meaning.py -- the rule half of D19 as amended by D39 and D52 (00_agreements.md).

Three parts. (1) D52 pinned on the four accepted POSTs, with the catalogue values read on 2026-09-23 from
fetched/rc/fields/USA_TOP3000_d1.jsonl (the Mac copy, dated 07-15) and, when the desk's files are present,
on those files. (2) One truth table per gate, on a synthetic catalogue, each case named for the rule it
pins. (3) The row, the writer and the reader: the shared meaning.jsonl interface and its one reader,
forge/offline/benchmark.py. Nothing here touches the network or the live ledger.
"""
import builtins
import hashlib
import json
import pathlib

import pytest

from forge import meaning as M

ROOT = pathlib.Path(__file__).resolve().parents[2]
ST = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "INDUSTRY", "decay": 4, "truncation": 0.08}

# ------------------------------------------------------------------------------------------------ (1) D52
# The four accepted POSTs (http 201, ACTIVE), formulas verbatim from state/forge/submitted.jsonl, settings and
# composite from their journal rows (state/layered/runs/forge.jsonl), read 2026-09-23.
POSTS = [
    ("vRk095rv", "usa_short_x_profitability_x_accruals",
     "multiply(multiply((1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 10), sector)), group_rank(ts_backfill(operating_income / equity, 126), sector)), (1 - group_rank(ts_rank((income - cashflow_op) / abs(assets), 126), sector)))",
     dict(ST, neutralization="STATISTICAL", decay=4, truncation=0.15), 1788530990.0, 1788531577.9),
    ("kqVbg1xP", "options_x_short",
     "multiply(group_rank(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 5), sector), (1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 20), subindustry)))",
     dict(ST, neutralization="STATISTICAL", decay=8), 1788623616.0, 1788689963.2),
    ("vRk1J2jd", "ownmultiple_x_profitability",
     "multiply((1 - group_rank(ts_rank(ts_backfill(diff_current_vs_hist_price_ratio_earnings, 21), 252), industry)), group_rank(ts_backfill(operating_income / assets, 126), industry))",
     dict(ST, neutralization="STATISTICAL", decay=8), 1789093173.0, 1789095119.0),
    ("rK5RGeqa", "usa_insider_x_ivspread_x_profitability",
     "multiply(multiply(group_rank(ts_sum(add(directional_significant_value_1, 0, filter=true), 60), sector), group_rank(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 10), industry)), group_rank(ts_rank(operating_income / assets, 126), industry))",
     dict(ST, neutralization="INDUSTRY", decay=4), 1789104726.0, 1790097809.7),
]
# alphaCount, fetched/rc/fields/USA_TOP3000_d1.jsonl on the Mac (07-15). The VPS copy (08-12, read-only ssh
# 2026-09-23) reads the short fields 32/33, the P/E field 6 and the insider field 1: the same verdicts.
POST_COUNTS = {"sector": 446847, "industry": 327837, "subindustry": 379228,
               "executed_short_trade_share_count": 10, "aggregate_executed_trade_share_count": 10,
               "operating_income": 67731, "equity": 27790, "income": 15084, "cashflow_op": 23095, "assets": 169009,
               "implied_volatility_call_30": 7089, "implied_volatility_put_30": 6259,
               "diff_current_vs_hist_price_ratio_earnings": 2, "directional_significant_value_1": 1}
# fetched/rc/field_labels.jsonl records of the same fields (the axes forge.typed and the sign check read).
POST_LABELS = {
    "executed_short_trade_share_count": {"domain": "short-flow", "kind": "count", "unit": "count", "sign": "unstated", "sign_source": "unstated", "time": "daily", "sparsity": "dense", "structure": "MATRIX"},
    "aggregate_executed_trade_share_count": {"domain": "volume-activity", "kind": "count", "unit": "count", "sign": "unstated", "sign_source": "unstated", "time": "daily", "sparsity": "dense", "structure": "MATRIX"},
    "operating_income": {"domain": "profitability", "kind": "level", "unit": "currency", "sign": "+", "sign_source": "domain-prior", "time": "quarterly", "sparsity": "medium", "structure": "MATRIX"},
    "equity": {"domain": "fundamental-other", "kind": "level", "unit": "currency", "sign": "unstated", "sign_source": "unstated", "time": "quarterly", "sparsity": "medium", "structure": "MATRIX"},
    "income": {"domain": "profitability", "kind": "level", "unit": "currency", "sign": "+", "sign_source": "domain-prior", "time": "quarterly", "sparsity": "medium", "structure": "MATRIX"},
    "cashflow_op": {"domain": "cashflow", "kind": "level", "unit": "currency", "sign": "+", "sign_source": "domain-prior", "time": "quarterly", "sparsity": "medium", "structure": "MATRIX"},
    "assets": {"domain": "size", "kind": "level", "unit": "currency", "sign": "unstated", "sign_source": "unstated", "time": "quarterly", "sparsity": "medium", "structure": "MATRIX"},
    "implied_volatility_call_30": {"domain": "option", "kind": "dispersion", "unit": "unitless", "sign": "unstated", "sign_source": "unstated", "time": "daily", "sparsity": "dense", "structure": "MATRIX"},
    "implied_volatility_put_30": {"domain": "option", "kind": "dispersion", "unit": "unitless", "sign": "unstated", "sign_source": "unstated", "time": "daily", "sparsity": "dense", "structure": "MATRIX"},
    "diff_current_vs_hist_price_ratio_earnings": {"domain": "valuation", "kind": "ratio", "unit": "ratio", "sign": "-", "sign_source": "description", "time": "annual", "sparsity": "dense", "structure": "MATRIX"},
    "directional_significant_value_1": {"domain": "insider-flow", "kind": "level", "unit": "unitless", "sign": "unstated", "sign_source": "unstated", "time": "event", "sparsity": "medium", "structure": "MATRIX"},
}
# the per-leg alphaCount under D52 (minimum over the leg's data fields, grouping fields excluded)
POST_LEG_COUNTS = {"vRk095rv": [10, 27790, 15084], "kqVbg1xP": [6259, 10],
                   "vRk1J2jd": [2, 67731], "rK5RGeqa": [1, 6259, 67731]}
# The two NO_GO families state/alpha_hypotheses.jsonl held on 2026-09-23 (precheck_lib.load_nogo_families).
REAL_NOGO = [frozenset({"credit_risk_default_probability_percent"}),
             frozenset({"mdl262_rev_ttm_predict", "oth432_aacr_trkdpitdeltapredict_funda_predict",
                        "oth432_atot_trkdpitdeltapredict_funda_predict"})]


def _cat(counts, labels, region="USA", universe="TOP3000", delay=1):
    return {"region": region, "universe": universe, "delay": delay, "labels": labels, "source": "test",
            "fields": {f: {"alphaCount": c, "type": "MATRIX"} for f, c in counts.items()}}


def _post_ledgers():
    from forge import factory as F
    index = [(M.FP.structural_signature(f), comp) for _a, comp, f, _s, _t, _p in POSTS]
    return {"journal": {F.candidate_id(f, s): [(t, a)] for a, _c, f, s, t, _p in POSTS},
            "posts": [{"alpha": a, "http": 201, "formula": f, "posted_at": p} for a, _c, f, _s, _t, p in POSTS],
            "post_rows": {}, "nogo": REAL_NOGO, "nogo_source": "test",
            "composites": {"verdicts": {c: {"G1": True, "G2": True, "G3": True} for _a, c, *_ in POSTS},
                           "index": index}}


@pytest.mark.parametrize("i", range(len(POSTS)))
def test_d52_the_four_accepted_posts_pass_g4_each_on_exactly_one_uncrowded_leg(i):
    """D52, round 3 S12: G4 FAILS only when EVERY leg is crowded; grouping fields are excluded. On the four
    ACTIVE submissions every one passes, and each verdict rests on ONE leg: vRk095rv and kqVbg1xP on the
    short-volume ratio (10), vRk1J2jd on the P/E-against-history field (2), rK5RGeqa on the insider field (1)."""
    alpha, comp, formula, settings, _t, _p = POSTS[i]
    row = M.score(formula, {"hypothesis": comp}, _cat(POST_COUNTS, POST_LABELS), _post_ledgers(),
                  alpha=alpha, settings=settings, scored_at=1.0)
    legs = row["evidence"]["G4"]["legs"]
    assert [l["alphaCount"] for l in legs] == POST_LEG_COUNTS[alpha]
    assert sum(l["alphaCount"] < M.CROWDED for l in legs) == 1
    assert row["gates"]["G4"] is True


def test_d52_on_the_four_posts_the_minimum_and_the_maximum_agree_and_grouping_decides():
    """What the four POSTs can and cannot pin (the module docstring's claim). With grouping fields excluded,
    a leg's alphaCount read as the MAXIMUM over its fields also passes all four, so they do not choose between
    minimum and maximum (the truth table does). With the grouping fields COUNTED and the maximum taken --
    S12's other reading -- all four fail: 0 of 4, as the round-3 adjudicator found."""
    from forge import typed as TY

    def g4(formula, agg, drop):
        legs = M.legs_of(TY.parse(formula))[1]
        counts = [agg(POST_COUNTS[x] for x in M._leaves(n) if x not in drop) for n, _o in legs]
        return any(c < M.CROWDED for c in counts)
    assert [g4(f, max, M.GROUPING) for _a, _c, f, *_ in POSTS] == [True] * 4
    assert [g4(f, min, M.GROUPING) for _a, _c, f, *_ in POSTS] == [True] * 4
    assert [g4(f, max, ()) for _a, _c, f, *_ in POSTS] == [False] * 4


@pytest.mark.parametrize("i", range(len(POSTS)))
def test_the_four_accepted_posts_read_eight_of_eight_on_the_rule(i):
    """Every gate of each POST, stated (task: "state the result per formula"): G1-G3 from its own composite
    (route library), G4-G8 true, so D39's decidable verdict is True. G5 checks one leg across the four (the
    P/E field, description sign -, leg (1 - SCORE)); on the other three G5 is a vacuous pass."""
    alpha, comp, formula, settings, _t, _p = POSTS[i]
    row = M.score(formula, {"hypothesis": comp}, _cat(POST_COUNTS, POST_LABELS), _post_ledgers(),
                  alpha=alpha, settings=settings, scored_at=1.0)
    assert row["gates"] == {g: True for g in M.GATES}
    assert (row["route"], row["inherited_from"]) == ("library", comp)
    assert M.decidable_verdict(row["gates"]) is True
    checked = row["evidence"]["G5"]["checked"]
    assert checked == ([{"field": "diff_current_vs_hist_price_ratio_earnings", "orientation": -1,
                         "description_sign": "-", "ok": True}] if alpha == "vRk1J2jd" else [])


def test_d52_on_the_desks_own_files_when_they_are_present():
    """The same pin on the files themselves, so a drift of the literals above is seen. Skipped where the
    desk's state is absent (a hosted runner: state/forge/submitted.jsonl is untracked)."""
    log = ROOT / "state/forge/submitted.jsonl"
    if not log.exists() or not (ROOT / "fetched/rc/fields/USA_TOP3000_d1.jsonl").exists():
        pytest.skip("the desk's submit log or USA catalogue is not in this tree")
    on_file = {r["alpha"]: r["formula"] for r in map(json.loads, log.read_text().splitlines())
               if r.get("http") in (200, 201) and r.get("formula")}
    fields = {x for _a, _c, f, *_ in POSTS for x in M._leaves(M.TY.parse(f))}
    cat = M.load_catalogue(root=ROOT, only=fields)
    for alpha, comp, formula, settings, _t, _p in POSTS:
        assert on_file.get(alpha) == formula
        row = M.score(formula, {"hypothesis": comp}, cat, {}, alpha=alpha, settings=settings, scored_at=1.0)
        legs = row["evidence"]["G4"]["legs"]
        assert row["gates"]["G4"] is True and sum(l["alphaCount"] < M.CROWDED for l in legs) == 1, (alpha, legs)


# --------------------------------------------------------------------------------------- (2) truth tables
def _lab(domain, sign="unstated", source="unstated", kind="level", unit="currency"):
    return {"domain": domain, "kind": kind, "unit": unit, "sign": sign, "sign_source": source,
            "time": "daily", "sparsity": "dense", "structure": "MATRIX"}


LABS = {"fa": _lab("dom-a", "+", "description"), "fa2": _lab("dom-a", "+", "description"),
        "fb": _lab("dom-b"), "fb2": _lab("dom-b"), "fc": _lab("dom-c"),
        "fneg": _lab("dom-c", "-", "description"), "fprior": _lab("dom-d", "-", "domain-prior"),
        "fret": _lab("dom-e", kind="return", unit="return")}
COUNTS = {f: 5000 for f in LABS}
TWO = "multiply(group_rank(ts_mean(fa, 5), sector), group_rank(ts_mean(fb, 5), industry))"


def _empty(**kw):
    base = {"journal": {}, "posts": [], "post_rows": {}, "nogo": [], "nogo_source": "test",
            "composites": {"verdicts": {}, "index": []}}
    base.update(kw)
    return base


def _run(formula, counts=None, labels=LABS, ledgers=None, meta=None, alpha="A1", settings=ST, catalogue="default"):
    cat = _cat(dict(COUNTS, **(counts or {})), labels) if catalogue == "default" else catalogue
    return M.score(formula, meta or {"hypothesis": "gen:fam1"}, cat, _empty() if ledgers is None else ledgers,
                   alpha=alpha, settings=settings, scored_at=1.0)


@pytest.mark.parametrize("fa, fb, want", [
    (500, 300, False),       # every leg crowded
    (500, 199, True),        # one leg under the line
    (200, 200, False),       # the line itself is crowded (>= 200)
    (199, 5000, True),
    (None, 5000, None),      # fa not in the catalogue, the other leg crowded: undecided
    (None, 10, True),        # the other leg is known uncrowded: decided whatever fa is
])
def test_g4_fails_only_when_every_leg_is_crowded(fa, fb, want):
    counts = dict(COUNTS, fa=fa, fb=fb)
    counts = {k: v for k, v in counts.items() if v is not None}
    cat = _cat(counts, LABS)
    assert _run(TWO, catalogue=cat)["gates"]["G4"] is want


def test_g4_a_crowded_leg_with_a_field_missing_from_the_catalogue_is_undecided_not_crowded():
    """Minimum over a partly known leg: the known field is crowded, the missing one could be anything, so the
    leg's crowding is unknown and G4 is null -- not a FAIL on a count nobody read."""
    f = "multiply(group_rank(ts_mean(fa / fb, 5), sector), group_rank(ts_mean(fc, 5), industry))"
    cat = _cat({"fb": 5000, "fc": 5000}, LABS)
    row = _run(f, catalogue=cat)
    assert row["evidence"]["G4"]["legs"][0]["alphaCount"] is None and row["gates"]["G4"] is None


def test_g4_a_multi_field_leg_takes_the_minimum_of_its_fields():
    """The definition D52 left open: a crowded field divided by an uncrowded one reads as the uncrowded count
    (10), so the leg is uncrowded. Under the maximum it would read 5000 and G4 would fail."""
    f = "multiply(group_rank(ts_mean(fa / fb, 5), sector), group_rank(ts_mean(fc, 5), industry))"
    row = _run(f, counts={"fa": 5000, "fb": 10, "fc": 5000})
    assert [l["alphaCount"] for l in row["evidence"]["G4"]["legs"]] == [10, 5000]
    assert row["gates"]["G4"] is True


def test_g4_excludes_sector_industry_subindustry_and_only_those():
    """D52 names three grouping fields. With a (synthetic) sector count of 5 both legs stay crowded, because
    sector is not a leg field; `market`, which D52 does not name, is counted as a field."""
    assert _run(TWO, counts={"fa": 500, "fb": 500, "sector": 5, "industry": 5})["gates"]["G4"] is False
    f = "multiply(group_rank(ts_mean(fa, 5), market), group_rank(ts_mean(fb, 5), industry))"
    assert _run(f, counts={"fa": 500, "fb": 500, "market": 5})["gates"]["G4"] is True


@pytest.mark.parametrize("catalogue, settings", [
    (None, ST),
    (_cat(COUNTS, LABS, region="EUR"), ST),
    (_cat(COUNTS, LABS, delay=0), ST),
    (_cat(COUNTS, LABS), {k: v for k, v in ST.items() if k != "region"}),
])
def test_g4_and_g7_are_null_without_the_catalogue_of_the_alphas_own_cell(catalogue, settings):
    row = _run(TWO, catalogue=catalogue, settings=settings)
    assert row["gates"]["G4"] is None and row["gates"]["G7"] is None


def test_g4_names_the_clauses_it_does_not_decide():
    ev = _run(TWO)["evidence"]["G4"]
    assert "PRIMARY" in ev["other_clauses"] and "sign map" in ev["other_clauses"]


@pytest.mark.parametrize("formula, want, checked", [
    # agreement and contradiction on a description-signed field (fa: +, fneg: -)
    ("multiply(group_rank(ts_mean(fa, 5), sector), group_rank(fb, sector))", True, [("fa", 1)]),
    ("multiply((1 - group_rank(ts_mean(fa, 5), sector)), group_rank(fb, sector))", False, [("fa", -1)]),
    ("multiply(-group_rank(ts_mean(fa, 5), sector), group_rank(fb, sector))", False, [("fa", -1)]),
    ("multiply((1 - group_rank(fneg, sector)), group_rank(fb, sector))", True, [("fneg", -1)]),
    ("multiply(group_rank(fneg, sector), group_rank(fb, sector))", False, [("fneg", 1)]),
    # a domain-prior sign never fails (sign_verdict's rule), and is not "checked"
    ("multiply(group_rank(fprior, sector), group_rank(fb, sector))", True, []),
    # a spread of two description-signed fields has no labelled sign: not checked
    ("multiply(group_rank(ts_mean(fa - fa2, 5), sector), group_rank(fb, sector))", True, []),
    # a denominator is a scale: fa below it is not the leg's direction, even with nothing above it
    ("multiply((1 - group_rank(ts_mean(fb / fa, 5), sector)), group_rank(fc, sector))", True, []),
    ("multiply((1 - group_rank(ts_mean(5 / fa, 5), sector)), group_rank(fc, sector))", True, []),
    # a gate's condition leg: greater keeps its orientation, less flips it
    ("if_else(greater(group_rank(fa, sector), 0.5), group_rank(fb, sector), 0)", True, [("fa", 1)]),
    ("if_else(less(group_rank(fa, sector), 0.5), group_rank(fb, sector), 0)", False, [("fa", -1)]),
    ("if_else(greater(0.5, group_rank(fa, sector)), group_rank(fb, sector), 0)", False, [("fa", -1)]),
])
def test_g5_truth_table(formula, want, checked):
    row = _run(formula)
    assert row["gates"]["G5"] is want
    assert [(c["field"], c["orientation"]) for c in row["evidence"]["G5"]["checked"]] == checked


def test_g5_an_override_written_in_meta_does_not_rescue_a_contradiction():
    """sign_verdict passes a contradiction whose notes say "override"; a generated alpha has no author, so
    the notes are always '' -- a planner-written meta field cannot buy a pass."""
    f = "multiply((1 - group_rank(ts_mean(fa, 5), sector)), group_rank(fb, sector))"
    meta = {"hypothesis": "gen:fam1", "notes": "fa: override, the description says the label file is wrong"}
    assert _run(f, meta=meta)["gates"]["G5"] is False


def test_g5_a_vacuous_pass_says_it_is_vacuous_and_null_without_labels():
    row = _run("multiply(group_rank(fb, sector), group_rank(fc, sector))")
    assert row["gates"]["G5"] is True and "vacuous" in row["evidence"]["G5"]["why"]
    assert _run(TWO, labels=None)["gates"]["G5"] is None


@pytest.mark.parametrize("formula, want, why", [
    (TWO, True, "holds"),
    ("if_else(greater(group_rank(fb, sector), 0.5), group_rank(fa, sector), 0)", True, "holds"),
    ("group_rank(ts_mean(fa, 5), sector)", False, "one leg"),
    ("-group_rank(ts_mean(fa, 5), sector)", False, "one leg"),
    ("add(group_rank(fa, sector), group_rank(fb, sector))", False, "additive"),
    ("multiply(group_rank(fa, sector), group_rank(fa2, industry))", False, "one domain"),
    # a denominator contributes no domain (forge.typed): fa/fb2 is a dom-a leg, like fa2
    ("multiply(group_rank(fa / fb2, sector), group_rank(fa2, industry))", False, "one domain"),
    ("multiply(fa, group_rank(fb, sector))", False, "H3"),
    ("multiply(group_rank(ts_delta(fret, 5), sector), group_rank(fb, sector))", False, "already a change"),
    ("multiply(group_rank(ts_delta(fa, 5), sector), group_rank(fb, sector))", True, "holds"),
    ("multiply(group_rank(fx_unlabelled, sector), group_rank(fa, sector))", None, "unknown"),
])
def test_g6_truth_table(formula, want, why):
    row = _run(formula, counts={"fx_unlabelled": 10})
    assert row["gates"]["G6"] is want and why in row["evidence"]["G6"]["why"]


def test_g6_is_null_without_labels():
    assert _run(TWO, labels=None)["gates"]["G6"] is None


def test_g7_existence_decides_and_point_in_time_stays_null():
    row = _run(TWO)
    assert row["gates"]["G7"] is True
    assert row["evidence"]["G7"]["point_in_time"] is None and "UNMEASURED" in row["evidence"]["G7"]["point_in_time_why"]
    cat = _cat({"fa": 10}, LABS)                                     # fb absent; sector/industry are group keys
    row = _run(TWO, catalogue=cat)
    assert row["gates"]["G7"] is False and row["evidence"]["G7"]["missing"] == ["fb"]


def _journal(*entries):
    from forge import factory as F
    return {F.candidate_id(TWO, ST): list(entries)}


@pytest.mark.parametrize("entries, want", [
    ([(100.0, "A1")], True),                          # the alpha's own row never collides (round 3 X4)
    ([(100.0, "A1"), (None, "A1")], True),            # ... not even an undated second row of its own
    ([(50.0, "B9"), (100.0, "A1")], False),           # the same formula + settings, another alpha, earlier
    ([(100.0, "A1"), (150.0, "B9")], True),           # another alpha, LATER: this one came first
    ([(None, "B9"), (100.0, "A1")], None),            # order unknown
    ([(50.0, "B9")], None),                           # this alpha has no journal row: order unknown
    ([], True),
])
def test_g8_journal_clause(entries, want):
    assert _run(TWO, ledgers=_empty(journal=_journal(*entries)))["gates"]["G8"] is want


IV_POST = POSTS[1][2]
IV_VARIANT = ("multiply(group_rank(ts_mean(implied_volatility_call_90 - implied_volatility_put_90, 20), industry), "
              "(1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 10), "
              "industry)))")


@pytest.mark.parametrize("posts, alpha, want", [
    ([{"alpha": "kqVbg1xP", "http": 201, "formula": IV_POST}], "A1", False),      # D18 near-dup of a POST
    ([{"alpha": "A1", "http": 201, "formula": IV_POST}], "A1", True),             # its own POST is not a twin
    ([{"alpha": "kqVbg1xP", "http": 403, "formula": IV_POST}], "A1", True),       # a 403 is not a submission
    ([{"alpha": "ghost", "http": 201, "formula": None}], "A1", None),             # incomplete index: unknown
    ([{"alpha": "ghost", "http": 201, "formula": None},
      {"alpha": "kqVbg1xP", "http": 201, "formula": IV_POST}], "A1", False),     # a found twin is still found
])
def test_g8_d18_clause(posts, alpha, want):
    row = M.score(IV_VARIANT, {}, None, _empty(posts=posts), alpha=alpha, settings=ST, scored_at=1.0)
    assert row["gates"]["G8"] is want


@pytest.mark.parametrize("formula, nogo, want", [
    ("group_rank(ts_backfill(credit_risk_default_probability_percent, 21), subindustry)", REAL_NOGO, False),
    # a one-field family needs the EXACT field set (B10 O1): inside a two-field formula it is not a hit
    ("multiply(group_rank(credit_risk_default_probability_percent, sector), group_rank(fb, sector))", REAL_NOGO, True),
    ("multiply(group_rank(fa, sector), group_rank(fb / fc, sector))", [frozenset({"fa", "fb"})], False),  # subset
    ("multiply(group_rank(fa, sector), group_rank(fc, sector))", [frozenset({"fa", "fb"})], True),
    (TWO, None, None),
])
def test_g8_nogo_clause(formula, nogo, want):
    assert _run(formula, ledgers=_empty(nogo=nogo))["gates"]["G8"] is want


def test_g8_is_null_when_a_ledger_was_not_read():
    for key in ("journal", "posts", "nogo"):
        assert _run(TWO, ledgers=_empty(**{key: None}))["gates"]["G8"] is None, key


def _comp_ledgers(verdicts=None):
    idx = [(M.FP.structural_signature(POSTS[1][2]), "options_x_short"),
           (M.FP.structural_signature(POSTS[2][2]), "ownmultiple_x_profitability")]
    v = verdicts or {"options_x_short": {"G1": True, "G2": False, "G3": True},
                     "ownmultiple_x_profitability": {"G1": True, "G2": True, "G3": True}}
    return _empty(composites={"verdicts": v, "index": idx})


def test_g1_to_g3_are_not_applicable_to_a_generated_alpha_that_resembles_no_composite():
    row = _run(TWO, ledgers=_comp_ledgers())
    assert [row["gates"][g] for g in M.NOT_APPLICABLE] == [None] * 3
    assert (row["route"], row["inherited_from"]) == ("generated", None)
    assert row["evidence"]["G1"]["label"] == "NOT APPLICABLE (D39)"


def test_a_generated_near_dup_of_an_authored_composite_inherits_its_text_verdicts():
    """D39: a generated alpha that is a near-dup of an authored composite inherits that composite's G1-G3
    (inherited_from records which)."""
    row = _run(IV_VARIANT, ledgers=_comp_ledgers(), meta={"hypothesis": "gen:fam7"})
    assert (row["route"], row["inherited_from"]) == ("inherited", "options_x_short")
    assert [row["gates"][g] for g in M.NOT_APPLICABLE] == [True, False, True]


def test_a_row_naming_a_composite_it_does_not_resemble_does_not_take_its_text():
    """Round 3 S8: routing followed the planner-written label. Here the label names ownmultiple_x_profitability
    and the formula is the IV/short structure: the text comes from the composite it resembles."""
    row = _run(IV_VARIANT, ledgers=_comp_ledgers(), meta={"hypothesis": "ownmultiple_x_profitability"})
    assert (row["route"], row["inherited_from"]) == ("inherited", "options_x_short")
    row = _run(TWO, ledgers=_comp_ledgers(), meta={"hypothesis": "ownmultiple_x_profitability"})
    assert (row["route"], row["gates"]["G1"]) == ("generated", None)


def test_the_composite_index_unread_gives_route_unknown():
    row = _run(TWO, ledgers=_empty(composites=None))
    assert row["route"] == "unknown" and row["gates"]["G1"] is None


@pytest.mark.parametrize("gates, want", [
    ({g: True for g in M.GATES}, True),
    (dict({g: True for g in M.GATES}, G1=None, G2=None, G3=None), True),     # G1-G3 never block (D39)
    (dict({g: True for g in M.GATES}, G6=False), False),
    (dict({g: True for g in M.GATES}, G7=None), None),
    (dict({g: True for g in M.GATES}, G7=None, G4=False), False),
    (dict({g: True for g in M.GATES}, G5=1), None),                          # not exactly true: null
])
def test_decidable_verdict_is_d39_and_reads_as_the_judge_reads_it(gates, want):
    from forge.offline import benchmark as B
    assert M.decidable_verdict(gates) is want
    row = {"alpha": "A1", "gates": gates, "formula_sha": "x", "scored_at": 1.0}
    assert B._standard_gate("gen:fam1", "A1", None, {"A1": row})[0] is want


# --------------------------------------------------------------------------------------- (3) the row
def test_the_row_is_the_shared_schema_and_the_sha_is_of_the_formula_text():
    row = _run(TWO)
    assert set(row) == {"alpha", "formula_sha", "gates", "inherited_from", "route", "scorer", "scored_at", "evidence"}
    assert row["formula_sha"] == hashlib.sha256(TWO.encode()).hexdigest()
    assert list(row["gates"]) == list(M.GATES) and row["scorer"].startswith("forge/meaning.py@sha256:")
    M.check_row(row)


def test_the_writer_and_the_reader_agree_on_names_and_paths():
    from forge import runner as RN, submit as SUB
    from forge.offline import benchmark as B
    assert M.DECIDABLE == B.MEANING_DECIDABLE and M.NOT_APPLICABLE == B.MEANING_NOT_APPLICABLE
    assert M.LEDGER == B.MEANING_LEDGER
    assert M.JOURNAL_GLOB == RN.JOURNAL_GLOB
    assert tuple(M.ROOT / p for p in M.POST_LOGS) == (SUB.LOG, SUB.CLIMB_LOG)


def test_score_reads_no_file(monkeypatch):
    import forge.llm.verify  # noqa: F401 -- the lazy import in _g5 happens before the guard

    def refuse(*a, **k):
        raise AssertionError("score opened a file")
    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(pathlib.Path, "open", refuse)
    _run(TWO, ledgers=_post_ledgers())


def test_an_unparseable_formula_leaves_the_structure_gates_null():
    row = _run("multiply(fa,, fb")
    assert [row["gates"][g] for g in ("G4", "G5", "G6", "G7")] == [None] * 4


def test_append_is_idempotent_per_alpha_and_formula_sha(tmp_path):
    """Round 3 S8: a later all-true row for the same (alpha, sha) used to overturn an earlier false one. The
    writer keeps the earliest: a second row for the pair is not appended."""
    p = tmp_path / "meaning.jsonl"
    first = _run(TWO)
    assert M.append(first, p) == (p, True)
    second = dict(first, gates={g: True for g in M.GATES}, scored_at=2.0)
    assert M.append(second, p) == (p, False)
    assert [json.loads(x)["scored_at"] for x in p.read_text().splitlines()] == [1.0]
    assert M.append(dict(first, alpha="A2"), p) == (p, True)


def test_append_puts_its_row_on_a_whole_line_after_a_torn_one(tmp_path):
    p = tmp_path / "meaning.jsonl"
    p.write_text('{"alpha": "cut sh')
    M.append(_run(TWO), p)
    lines = p.read_text().splitlines()
    assert lines[0] == '{"alpha": "cut sh' and json.loads(lines[1])["alpha"] == "A1"


@pytest.mark.parametrize("change", [
    {"gates": dict({g: True for g in M.GATES}, G5=1)},
    {"gates": dict({g: True for g in M.GATES}, G5=1.0)},
    {"gates": dict({g: True for g in M.GATES}, G5={"value": True})},
    {"gates": {g: True for g in M.GATES if g != "G8"}},
    {"formula_sha": "abc"},
    {"route": "hand-typed"},
    {"scorer": ""},
    {"scored_at": float("nan")},
    {"scored_at": True},
    {"scored_at": "2026-09-23T10:00:00"},     # draw-4 scoring: an offset-less ISO time reads in the host's zone
    {"alpha": ""},
    {"inherited_from": ""},
])
def test_append_refuses_a_row_outside_the_schema(tmp_path, change):
    with pytest.raises(ValueError):
        M.append(dict(_run(TWO), **change), tmp_path / "m.jsonl")
    assert not (tmp_path / "m.jsonl").exists()


def test_a_written_row_reads_back_through_the_judge(tmp_path):
    """End to end on the one reader: a row this module writes is what benchmark.load_meaning and
    meaning_index read, and a generated alpha with every decidable gate true reads PROVEN on the gate half."""
    from forge.offline import benchmark as B
    p = tmp_path / "meaning.jsonl"
    alpha, comp, formula, settings, created, _p = POSTS[2]
    row = M.score(formula, {"hypothesis": "gen:fam1"}, _cat(POST_COUNTS, POST_LABELS), _post_ledgers(),
                  alpha=alpha, settings=settings, scored_at=created + 60)
    M.append(row, p)
    journal_row = {"alpha": alpha, "formula": formula, "dateCreated": "2026-09-10T22:19:33-04:00"}
    idx = B.meaning_index(B.load_meaning(p), now=created + 120, formulas=B._formulas([journal_row]))
    assert idx[alpha]["formula_sha"] == B.formula_sha(formula)        # the two sha definitions agree
    assert B._standard_gate("gen:fam1", alpha, None, idx)[0] is True


def test_load_catalogue_and_load_ledgers_read_a_miniature_desk(tmp_path):
    """The loaders on a frozen miniature state/: the catalogue of the cell, labels, the journal (first alpha
    per candidate), both POST logs, an absent NO_GO bank read as none, and the composite index."""
    (tmp_path / "fetched/rc/fields").mkdir(parents=True)
    (tmp_path / "fetched/rc/fields/USA_TOP3000_d1.jsonl").write_text(
        "\n".join(json.dumps({"id": f, "alphaCount": c, "type": "MATRIX"}) for f, c in COUNTS.items()))
    (tmp_path / "fetched/rc/field_labels.jsonl").write_text(
        "\n".join(json.dumps(dict(v, id=k)) for k, v in LABS.items()))
    cat = M.load_catalogue(root=tmp_path, only={"fa", "fb"})
    assert set(cat["fields"]) == {"fa", "fb"} and set(cat["labels"]) == {"fa", "fb"}
    assert M.load_catalogue(region="EUR", root=tmp_path) is None
    for d in ("forge/hypotheses", "forge/composites", "state/layered/runs", "state/forge", "state/climb"):
        (tmp_path / d).mkdir(parents=True)
    for src in ("forge/hypotheses/option_call_put_iv_spread.yaml", "forge/hypotheses/short_volume_ratio_informed.yaml",
                "forge/composites/options_x_short.yaml"):
        (tmp_path / src).write_bytes((ROOT / src).read_bytes())
    iv = {"formula": IV_POST, "settings": ST, "meta": {"composite": 1, "hypothesis": "options_x_short"}}
    (tmp_path / "state/layered/runs/forge.jsonl").write_text("\n".join(json.dumps(r) for r in [
        dict(iv, alpha="kqVbg1xP", dateCreated="2026-09-05T11:53:36-04:00"),
        dict(iv, alpha="Z2", dateCreated="2026-09-06T11:53:36-04:00"),
        {"formula": TWO, "settings": ST, "meta": {"hypothesis": "gen:x"}}]))           # no alpha: not simulated
    (tmp_path / "state/forge/submitted.jsonl").write_text(json.dumps({"alpha": "kqVbg1xP", "http": 201}))
    (tmp_path / "state/climb/submitted.jsonl").write_text(json.dumps({"alpha": "mL5", "http": 201, "formula": TWO}))
    L = M.load_ledgers(root=tmp_path)
    from forge import factory as F
    assert [a for _t, a in L["journal"][F.candidate_id(IV_POST, ST)]] == ["kqVbg1xP", "Z2"]
    assert F.candidate_id(TWO, ST) not in L["journal"]
    assert [h["alpha"] for h in L["posts"]] == ["kqVbg1xP", "mL5"]
    assert L["post_rows"] == {"kqVbg1xP": {"formula": IV_POST}}                    # the journal fallback
    assert L["nogo"] == [] and "absent" in L["nogo_source"]
    assert [c for _s, c in L["composites"]["index"]] == ["options_x_short"]
    assert L["composites"]["verdicts"]["options_x_short"] == {"G1": True, "G2": True, "G3": True}
    row = M.score(IV_POST, {"hypothesis": "options_x_short"}, None, L, alpha="Z2", settings=ST, scored_at=1.0)
    assert row["gates"]["G8"] is False
    assert row["evidence"]["G8"]["clauses"]["journal"]["value"] is False           # kqVbg1xP came first
    row = M.score(IV_POST, {"hypothesis": "options_x_short"}, None, L, alpha="kqVbg1xP", settings=ST, scored_at=1.0)
    assert row["evidence"]["G8"]["clauses"]["journal"]["value"] is True            # and is not its own twin
    assert (row["route"], row["inherited_from"]) == ("library", "options_x_short")


def test_load_ledgers_reads_the_nogo_bank_through_precheck_lib(tmp_path):
    """The ratified builder reads the bank (four statuses, word-bound): a TESTED-NULL row is a family, a
    'gate_fail' row is not."""
    for d in ("forge/hypotheses", "forge/composites", "state", "tools/funnel"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / M.PRECHECK).write_bytes((ROOT / M.PRECHECK).read_bytes())
    (tmp_path / M.NOGO_BANK).write_text("\n".join(json.dumps(r) for r in [
        {"id": "h1", "status": "TESTED-NULL", "roles": {"x": "fa (ds - a field)"}},
        {"id": "h2", "status": "gate_fail:LOW_SHARPE", "roles": {"x": "fb (ds - b field)"}}]))
    L = M.load_ledgers(root=tmp_path)
    assert L["nogo"] == [frozenset({"fa"})]
