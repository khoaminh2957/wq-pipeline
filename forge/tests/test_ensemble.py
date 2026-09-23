import random

from forge import cells as C
from forge import ensemble as E


def _row(alpha, hyp, sharpe, ds, formula, region="JPN", delay=1, cat="Model", neut="SUBINDUSTRY", decay=16, ens=False):
    m = {"forge": 1, "hypothesis": hyp, "category": cat, "dataset": ds, "field": formula.split("(")[-1].split(",")[0]}
    if ens:
        m["ensemble"] = 1
    return {"alpha": alpha, "sharpe": sharpe, "formula": formula, "meta": m,
            "settings": {"region": region, "delay": delay, "universe": "TOP1200", "neutralization": neut, "decay": decay, "truncation": 0.08}}


ROWS = {
    "A": _row("A", "h_intangible", 0.71, "model313", "group_rank(ts_backfill(mdl313_iai, 63), industry)"),
    "A2": _row("A2", "h_intangible", 0.55, "model313", "group_rank(ts_backfill(mdl313_ico, 63), industry)"),
    "B": _row("B", "h_credit", 0.21, "model28", "-group_rank(ts_backfill(one_year_default_probability_pct, 21), subindustry)"),
    "Bdup": _row("Bdup", "h_credit2", 0.30, "model28", "-group_rank(ts_backfill(global_default_risk_percentile, 5), industry)"),   # same dataset as B
    "C": _row("C", "h_quality", 0.12, "model16", "group_rank(ts_backfill(fscore_quality, 21), industry)"),                        # under min sharpe
    "D": _row("D", "h_cash", 0.42, "ml_factor_proj", "group_rank(ts_backfill(change_3y_fcf_to_assets, 21), industry)", cat="Other"),  # other cell
    "E": _row("E", "ens:x", 0.9, "model313+model28", "(x) + (y)", ens=True),                                                       # never a leg
    "F": _row("F", "h_nan", None, "model50", "group_rank(x, industry)"),
}


def test_best_legs_one_per_hypothesis_and_dataset_sorted():
    legs = E.best_legs(ROWS, "JPN", 1, "Model")
    assert [l["alpha"] for l in legs] == ["A", "Bdup"]          # A beats A2; Bdup (0.30) beats B on the same dataset; C < 0.2
    assert E.best_legs(ROWS, "JPN", 1, "Other")[0]["alpha"] == "D"
    assert E.best_legs(ROWS, "EUR", 1, "Model") == []


def test_combine_and_expand():
    cell = C.Cell("JPN", 1, "Model", "TOP1200", 0, 3, 1.7, 100, (), 5.1)
    cands = E.expand(cell, ROWS, random.Random(1), max_candidates=20)
    assert len(cands) == 2                                        # 2 legs × weights {1.0, 0.5}
    forms = sorted(c["formula"] for c in cands)
    assert forms[0] == "(group_rank(ts_backfill(mdl313_iai, 63), industry)) + (-group_rank(ts_backfill(global_default_risk_percentile, 5), industry))"
    assert forms[1].startswith("(group_rank(ts_backfill(mdl313_iai, 63), industry)) + 0.5 * (")
    c0 = cands[0]
    assert c0["settings"]["neutralization"] == "SUBINDUSTRY" and c0["settings"]["decay"] == 16 and c0["settings"]["universe"] == "TOP1200"
    assert c0["meta"]["ensemble"] == 1 and c0["meta"]["hypothesis"] == "ens:h_credit2+h_intangible"
    assert c0["meta"]["legs"] == ["A", "Bdup"] and c0["meta"]["leg_sharpes"] == [0.71, 0.30]
    assert c0["signature"]["mechanism_key"].startswith("ens:h_credit2+h_intangible#")
    assert E.op_count(c0["formula"]) in (5, 6)


def test_three_legs_and_cap():
    rows = dict(ROWS)
    rows["G"] = _row("G", "h_third", 0.33, "model36", "group_rank(ts_backfill(star_sr_global_rank, 5), industry)")
    cell = C.Cell("JPN", 1, "Model", "TOP1200", 0, 3, 1.7, 100, (), 5.1)
    cands = E.expand(cell, rows, random.Random(2), max_candidates=100)
    # 3 pairs × 2 weights + 1 triple × 4 weight combos = 10
    assert len(cands) == 10
    triples = [c for c in cands if len(c["meta"]["legs"]) == 3]
    assert len(triples) == 4 and all(c["meta"]["weights"][0] == 1.0 for c in triples)
    assert len(E.expand(cell, rows, random.Random(2), max_candidates=3)) == 3
    assert E.expand(C.Cell("JPN", 1, "Model", None, 0, 3, 1.7, 100, (), 5.1), rows, random.Random(2)) == []


def test_same_dataset_and_cross_category_legs():
    rows = dict(ROWS)
    rows["P"] = _row("P", "h_pv", 1.5, "pv1", "rank(close / open)")                                # price carrier: refused
    rows["D2"] = _row("D2", "h_cash", 0.42, "ml_factor_proj", "group_rank(ts_backfill(change_3y_fcf_to_assets, 21), industry)", cat="Other")
    # same dataset: A and A2 (two fields of model313) both become legs
    legs = E.best_legs(rows, "JPN", 1, "Model", same_dataset=True)
    assert [l["alpha"] for l in legs] == ["A", "A2", "Bdup", "B"]
    # cross category: the Other-category leg D2 joins the Model cell; the pv leg never does
    legs = E.best_legs(rows, "JPN", 1, "Model", cross_category=True)
    assert [l["alpha"] for l in legs] == ["A", "D", "Bdup"]           # D and D2 tie on h_cash; the first stays
    cell = C.Cell("JPN", 1, "Model", "TOP1200", 0, 3, 1.7, 100, (), 5.1)
    cands = E.expand(cell, rows, random.Random(3), max_candidates=100, cross_category=True)
    assert cands and all(any(h in ("h_intangible", "h_credit2") for h in c["meta"]["leg_hypotheses"]) for c in cands)
    assert any("change_3y_fcf_to_assets" in c["formula"] for c in cands)
    assert not any("close" in c["formula"] for c in cands)
    # a cell whose own category has no leg gets nothing even with cross_category
    assert E.expand(C.Cell("JPN", 1, "Analyst", "TOP1200", 0, 3, 1.7, 100, (), 5.1), rows, random.Random(3), cross_category=True) == []
