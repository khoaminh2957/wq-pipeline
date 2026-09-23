"""Suite for tools/cell_targets.py -- the open-cell raw-material inventory.

OFFLINE BY CONSTRUCTION. `_no_network` is autouse and replaces socket.socket with something
that raises, so a test that reaches the network FAILS instead of quietly succeeding.

RULE 0: every test asserts an OBSERVABLE CONTRACT -- an arithmetic identity over a fixture, a
failure mode of the join, or a number this repo already measured elsewhere and that must
still reproduce. None asserts that any of these fields predicts a return.
"""

import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cell_targets  # noqa: E402


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("cell_targets must not open a socket")
    monkeypatch.setattr(socket, "socket", _boom)


def _field(fid, cat, dataset, kind="MATRIX"):
    return {"id": fid, "category": {"name": cat}, "dataset": {"id": dataset}, "type": kind}


# ------------------------------------------------------------------------------- inventory arithmetic

def test_pairable_needs_two_matrix_in_the_SAME_dataset():
    """One MATRIX field in each of two datasets pairs with nothing: the pool pairs within."""
    rows = [_field("a", "News", "ds1"), _field("b", "News", "ds2")]
    inv = cell_targets.inventory(rows)["News"]
    assert inv["datasets"] == 2 and inv["matrix"] == 2
    assert inv["pairable_datasets"] == 0 and inv["matrix_pairs"] == 0


def test_matrix_pairs_is_C_n_2_per_dataset():
    rows = [_field(f"f{i}", "Sentiment", "ds1") for i in range(4)]
    rows += [_field(f"g{i}", "Sentiment", "ds2") for i in range(3)]
    inv = cell_targets.inventory(rows)["Sentiment"]
    assert inv["pairable_datasets"] == 2
    assert inv["matrix_pairs"] == 6 + 3          # C(4,2) + C(3,2)


def test_vector_fields_are_excluded_from_matrix_pairs_but_counted_in_mv():
    """The base pool's vec_* clause is a SCOPE choice; this separates what it costs."""
    rows = [_field("m", "News", "ds1"), _field("v1", "News", "ds1", "VECTOR"),
            _field("v2", "News", "ds1", "VECTOR")]
    inv = cell_targets.inventory(rows)["News"]
    assert inv["matrix"] == 1 and inv["vector"] == 2
    assert inv["pairable_datasets"] == 0 and inv["matrix_pairs"] == 0
    assert inv["pairable_datasets_mv"] == 1 and inv["mv_pairs"] == 3   # C(3,2)


# ------------------------------------------------------------------------------------------ the join

def test_join_fails_when_category_sets_differ():
    """A catalogue holding a category the pyramid has never heard of is not a thin cell --
    it is the wrong catalogue, and the inventory built on it would be silently wrong."""
    rows = [_field("a", "News", "ds1"), _field("b", "Broker", "ds2")]
    with pytest.raises(cell_targets.JoinError):
        cell_targets.assert_join_consistent(rows, {"News": 2, "Broker": 0})  # unknown to CATEGORY_ID


def test_join_fails_when_one_dataset_carries_two_categories():
    rows = [_field("a", "News", "ds1"), _field("b", "Sentiment", "ds1")]
    counts = {c: 0 for c in ("News", "Sentiment")}
    with pytest.raises(cell_targets.JoinError) as e:
        cell_targets.assert_join_consistent(rows, counts)
    assert "more than one field category" in str(e.value)


def test_join_fails_when_the_dataset_catalogue_disagrees(tmp_path):
    rows = [_field("a", "News", "ds1")]
    dpath = tmp_path / "ds.jsonl"
    dpath.write_text(json.dumps({"id": "ds1", "category": {"name": "Sentiment"}}) + "\n")
    with pytest.raises(cell_targets.JoinError) as e:
        cell_targets.assert_join_consistent(rows, {"News": 2}, dpath)
    assert "disagree" in str(e.value)


def test_join_passes_on_agreeing_catalogues(tmp_path):
    rows = [_field("a", "News", "ds1"), _field("b", "News", "ds1")]
    dpath = tmp_path / "ds.jsonl"
    dpath.write_text(json.dumps({"id": "ds1", "category": {"name": "News"}}) + "\n")
    assert "dataset-catalogue agrees" in cell_targets.assert_join_consistent(rows, {"News": 2}, dpath)


# ---------------------------------------------------------------------------------- need and ratios

def test_need_counts_down_to_the_unlock_threshold_and_never_below_zero():
    rep = cell_targets.targets()
    cells = rep["cells"]
    assert cells["Imbalance"]["need"] == cell_targets.UNLOCK_AT
    assert cells["Price Volume"]["have"] >= cell_targets.UNLOCK_AT
    assert cells["Price Volume"]["need"] == 0
    assert cells["Price Volume"]["signals_per_needed"] is None       # not 40/0, and not 0


def test_signals_per_needed_is_mechanics_over_need():
    rep = cell_targets.targets()["cells"]
    for c, r in rep.items():
        if r["need"]:
            assert r["signals_per_needed"] == pytest.approx(r["pairable_datasets"] / r["need"])


# ------------------------------------------------- reproduces numbers this repo measured elsewhere

def test_reproduces_base_pool_192_and_295_over_the_whole_segment():
    """harness13/massgen/mg/base_pool.py::datasets_with_pairable_fields documents 192 datasets
    with >= 2 MATRIX and 295 with >= 2 (MATRIX|VECTOR) for USA_TOP3000_d1. Summing this
    module's per-category counts must land on the same two numbers, or one of us is wrong."""
    inv = cell_targets.inventory(cell_targets.load_catalogue("USA_TOP3000_d1"))
    assert sum(r["pairable_datasets"] for r in inv.values()) == 192
    assert sum(r["pairable_datasets_mv"] for r in inv.values()) == 295
    assert sum(r["matrix"] for r in inv.values()) == 67205            # same docstring, MATRIX count


def test_the_six_open_cells_are_the_ones_the_platform_counter_says_are_open():
    """Guards against a stale hard-coded list: the open set is DERIVED, never typed in."""
    rep = cell_targets.targets()["cells"]
    assert {c for c, r in rep.items() if r["open"]} == {
        "News", "Insiders", "Sentiment", "Social Media", "Short Interest", "Imbalance"}


def test_imbalance_is_a_single_dataset_of_two_fields():
    """The headline negative. If a future crawl widens it, this test must fail loudly so the
    recommendation in CELL_TARGETS_R10.md gets revisited rather than silently inherited."""
    r = cell_targets.targets()["cells"]["Imbalance"]
    assert (r["datasets"], r["fields"], r["matrix"], r["matrix_pairs"]) == (1, 2, 2, 1)


def test_render_marks_open_cells_and_reports_the_open_subtotal():
    out = cell_targets.render(cell_targets.targets())
    assert "*Imbalance" in out and "OPEN only" in out
    assert "*Price Volume" not in out
