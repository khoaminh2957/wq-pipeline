"""tools/cell_map.py reproduces the platform's OWN pyramid assignment, or refuses.

The fixture tools/tests/fixtures/cell_map_ground_truth.json is a READ-ONLY capture of
GET /users/self/alphas and GET /users/self/activities/pyramid-alphas taken 2026-08-12: 48
ACTIVE alphas whose cell membership the PLATFORM decided, plus the platform's 16 USA-d1
counts. A rule that cannot reproduce this is not a rule, so the headline test is an exact
set match on all 48, not a threshold.

Every number in cell_map's docstring is asserted here, so a silent regression in the field
catalogs shows up as a failing test rather than as a wrong submit.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import cell_map  # noqa: E402

FIXTURE = json.load(open(pathlib.Path(__file__).parent / "fixtures/cell_map_ground_truth.json"))
ALPHAS = FIXTURE["alphas"]
COUNTER = FIXTURE["usa_d1_counter"]


def _catalog_present():
    return (ROOT / "fetched/rc/fields/USA_TOP3000_d1.jsonl").exists()


needs_catalog = pytest.mark.skipif(
    not _catalog_present(),
    reason="fetched/rc/fields/USA_TOP3000_d1.jsonl absent -- the matched catalog R1 was measured on",
)


def test_fixture_is_the_whole_ground_truth():
    assert len(ALPHAS) == 48
    assert {a["region"] for a in ALPHAS} == {"USA"}
    assert {a["delay"] for a in ALPHAS} == {1}
    assert set(COUNTER) == set(cell_map.CATEGORY_ID)


@needs_catalog
def test_predicted_set_matches_the_platform_on_every_alpha():
    """R1: 48/48 exact set match. Failures are listed individually, never summarised."""
    fails = []
    for a in ALPHAS:
        v = cell_map.cells_for(a["code"], a["region"], a["delay"], a["universe"])
        if set(v.predicted) != set(a["cells"]):
            fails.append(f"{a['id']}: platform={a['cells']} predicted={sorted(v.predicted)} "
                         f"unresolved={list(v.unresolved)}")
    assert not fails, "\n".join(fails)


@needs_catalog
def test_no_formula_token_is_left_unresolved_by_the_matched_catalog():
    unresolved = {a["id"]: cell_map.cells_for(a["code"], a["region"], a["delay"],
                                              a["universe"]).unresolved
                  for a in ALPHAS}
    assert not {k: v for k, v in unresolved.items() if v}


@needs_catalog
def test_confidence_is_high_only_for_the_matched_catalog_tier():
    a = next(x for x in ALPHAS if len(x["cells"]) == 2 and x["universe"] == "TOP3000")
    assert cell_map.cells_for(a["code"], "USA", 1, "TOP3000").confidence == "high"


def test_unresolved_token_forces_an_unknown_verdict_that_is_a_refusal():
    """R4: an unidentified token is not 'a field with no category'. UNKNOWN => withhold."""
    v = cell_map.cells_for("add(close, no_such_field_xyz)")
    assert v.confidence == "unknown"
    assert v.refuse is True
    assert v.cells == frozenset()
    assert "no_such_field_xyz" in v.unresolved


def test_empty_formula_is_a_refusal_not_an_empty_answer():
    v = cell_map.cells_for("1.0")
    assert v.refuse is True


@needs_catalog
def test_a_category_owed_only_to_a_group_classifier_is_flagged_not_asserted():
    """The one UNTESTED edge. Every classifier (sector/industry/...) carries category
    "Price Volume", so a pure-fundamental alpha neutralised by industry is predicted into
    Price Volume as well. All six ground-truth alphas using a classifier also carry real
    price-volume data, so zero unconfounded cases exist and the verdict must say so."""
    v = cell_map.cells_for("group_neutralize(rank(assets), industry)")
    assert "Price Volume" in v.predicted
    assert v.confidence == "low"
    assert "GROUP classifier" in v.reason


@needs_catalog
def test_real_price_volume_data_is_not_demoted_by_the_group_caveat():
    v = cell_map.cells_for("group_neutralize(ts_zscore(close, 20), industry)")
    assert v.confidence == "high"


def test_operator_names_are_not_mistaken_for_fields():
    v = cell_map.cells_for("group_neutralize(-ts_zscore(close, 20), subindustry, filter=true)")
    assert not v.unresolved, v.unresolved


# --- R2 / R3: multi-membership, which is the part that changes the submitter's planning -------

def test_membership_is_a_set_and_two_cells_is_the_norm():
    """R2: 4 alphas fill 1 cell, 42 fill 2, 2 fill 3. A submitter assuming one cell mis-plans."""
    sizes = {}
    for a in ALPHAS:
        sizes[len(a["cells"])] = sizes.get(len(a["cells"]), 0) + 1
    assert sizes == {1: 4, 2: 42, 3: 2}


def test_a_two_cell_alpha_is_credited_in_both_cells():
    """R2, re-derived: summing memberships over the alphas with effective>0 reproduces the
    platform counter EXACTLY in all 16 USA-d1 cells."""
    got = {c: 0 for c in COUNTER}
    for a in ALPHAS:
        if a["effective"]:
            for c in a["cells"]:
                got[c] += 1
    assert got == COUNTER


def test_three_cell_alphas_were_credited_nowhere():
    """R3: every 3-cell alpha carries effective == 0, and the counter excludes it from all three.
    n = 2 and MECHANISM IS UNKNOWN -- this asserts the observation, not an explanation."""
    three = [a for a in ALPHAS if len(a["cells"]) == 3]
    assert len(three) == 2
    assert all(a["effective"] == 0 for a in three)
    naive = {c: 0 for c in COUNTER}
    for a in ALPHAS:
        for c in a["cells"]:
            naive[c] += 1
    assert {c: naive[c] - COUNTER[c] for c in COUNTER if naive[c] != COUNTER[c]} == {
        "Price Volume": 2, "Model": 2, "News": 2}


def test_effective_equals_cell_count_below_the_forfeit_threshold():
    for a in ALPHAS:
        if len(a["cells"]) < cell_map.FORFEIT_AT:
            assert a["effective"] == len(a["cells"]), a["id"]


@needs_catalog
def test_a_three_cell_prediction_is_refused_not_submitted():
    """The forfeit rule must reach the submitter as a refusal, since a submit that lands in no
    cell spends one of four irreversible daily slots for nothing."""
    a = next(x for x in ALPHAS if len(x["cells"]) == 3)
    v = cell_map.cells_for(a["code"], a["region"], a["delay"], a["universe"])
    assert len(v.predicted) == 3
    assert v.cells == frozenset()
    assert v.refuse is True


# --- the platform's own answer outranks the rule ----------------------------------------------

def test_platform_cells_reads_the_authoritative_record():
    cells, eff = cell_map.platform_cells(
        {"pyramids": [{"name": "USA/D1/PV"}, {"name": "USA/D1/SENTIMENT"}],
         "pyramidThemes": {"effective": 2}})
    assert cells == frozenset({"Price Volume", "Sentiment"})
    assert eff == 2


def test_platform_cells_on_an_untagged_alpha_is_empty_not_an_error():
    assert cell_map.platform_cells({}) == (frozenset(), None)


def test_category_ids_match_the_platform_vocabulary():
    assert len(cell_map.CATEGORY_ID) == 16
    assert cell_map.CATEGORY_ID["Price Volume"] == "pv"
    assert cell_map.CATEGORY_ID["Social Media"] == "socialmedia"
