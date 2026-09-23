"""The producer must be safe to trust, because `auto_submit` trusts a decisions file that exists.

`auto_submit` fails closed on a MISSING file — so the dangerous state is not "no producer", it is
"a producer that writes something wrong". Everything here tests a refusal.
"""
import json
import pathlib
import socket
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import decide_submits as D  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A test that reaches the network fails. This module reads live pyramid counts in `main`."""
    def boom(*a, **k):
        raise AssertionError("a test opened a socket")
    monkeypatch.setattr(socket, "socket", boom)


def store(**over):
    row = {"prod_maxcorr": 0.50, "self_maxcorr": 0.30,
           "prod_breach_count": 0, "self_measured": True}
    row.update(over)
    return {"A": row}


FRESH = 60.0


# ------------------------------------------------------------------ the correlation refusals

def test_a_clean_verdict_with_room_to_spare_passes():
    ok, why = D.corr_ok("A", store(), FRESH)
    assert ok is True and "margin" in why


def test_a_missing_verdict_is_a_refusal_not_a_pass():
    """The presence contract. An alpha nobody measured is not an alpha that measured clean."""
    ok, why = D.corr_ok("A", {}, FRESH)
    assert ok is False and "no correlation verdict" in why


@pytest.mark.parametrize("over,frag", [
    ({"prod_maxcorr": 0.71}, "prod"),
    ({"self_maxcorr": 0.95}, "self"),
    ({"prod_breach_count": 3}, "breach"),
    ({"self_measured": False}, "self"),
    ({"prod_maxcorr": None}, "prod"),
    ({"self_maxcorr": "0.3"}, "self"),
    ({"prod_maxcorr": True}, "prod"),          # a bool is not a measurement
])
def test_each_correlation_gate_refuses_on_its_own(over, frag):
    ok, why = D.corr_ok("A", store(**over), FRESH)
    assert ok is False and frag in why.lower()


def test_a_stale_store_refuses_everything_however_clean_it_reads():
    ok, why = D.corr_ok("A", store(), D.CORR_MAX_AGE_S + 1)
    assert ok is False and "old" in why


def test_a_margin_thinner_than_the_measured_drift_is_refused():
    """THE RULE THAT REFUSED EVERY CANDIDATE ON 2026-08-13, and it is the point of this module.

    Stored prod readings drift ONE-DIRECTIONALLY UPWARD — 8 of 111 changed, 8 of 8 upward, 6
    crossing 0.70 clean->dirty, 0 the other way, median |delta| 0.0662. A reading 0.002 below the
    wall is therefore not evidence that the alpha is below the wall; it is evidence that we measured
    it a while ago. Six real Insiders candidates (0.6447 .. 0.6983) all sat inside that band.

    NOT ESTABLISHED: that 0.0662 is the right threshold. It is the median of an 8-observation drift
    sample, chosen because a wrong refusal costs a delay and a wrong POST costs the alpha forever.
    """
    ok, why = D.corr_ok("A", store(prod_maxcorr=0.6983), FRESH)
    assert ok is False and "drift" in why
    # and the same alpha with real headroom is allowed through
    assert D.corr_ok("A", store(prod_maxcorr=0.60), FRESH)[0] is True


def test_the_margin_threshold_is_the_measured_drift_and_not_a_round_number():
    assert D.MIN_MARGIN == 0.0662
    assert D.PROD_MAX == D.SELF_MAX == 0.70


# ------------------------------------------------------------------ the plan-level refusals

class FakeCells:
    def __init__(self, counts):
        self.counts, self.source, self.age_s, self.error = counts, "fake", 0, None


CELLS = FakeCells({"News": 2, "Insiders": 2, "Sentiment": 1, "Imbalance": 0,
                   "Price Volume": 40, "Model": 19, "Risk": 3})


def _wire(monkeypatch, rows, formulas, cells_of, corr):
    monkeypatch.setattr(D, "_journal_rows", lambda: rows)
    monkeypatch.setattr(D, "_formulas", lambda: formulas)
    monkeypatch.setattr(D, "_submitted_ids", lambda: set())
    monkeypatch.setattr(D.gates, "zero_fail", lambda r: (True, [], []))
    monkeypatch.setattr(D.cell_map, "cells_for",
                        lambda fm, **k: types.SimpleNamespace(
                            cells=cells_of[fm], confidence="high"))
    monkeypatch.setattr(D, "corr_ok", lambda a, s, age: corr(a))


def test_a_full_cell_receives_nothing(monkeypatch):
    """The operator's rule, and the one that must never be got backwards."""
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"}, {"f1": ["Price Volume"]}, lambda a: (True, "clean"))
    dec, rej = D.build(CELLS, now=0)
    assert dec == {}
    assert rej["fills no short cell"] == 1


def test_a_short_cell_receives_one(monkeypatch):
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"}, {"f1": ["Insiders", "Price Volume"]},
          lambda a: (True, "clean"))
    dec, _ = D.build(CELLS, now=0)
    assert list(dec) == ["A"]
    assert dec["A"]["cell"] == "Insiders"
    assert dec["A"]["region"] == "USA" and dec["A"]["delay"] == 1


def test_an_alpha_touching_three_cells_is_refused(monkeypatch):
    """Measured n=2: a 3-cell alpha is credited to NO cell. Thin evidence, expensive either way —
    it refuses 44.6% of held formulas, and the settling experiment is an irreversible submit."""
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"},
          {"f1": ["Insiders", "News", "Price Volume"]}, lambda a: (True, "clean"))
    dec, rej = D.build(CELLS, now=0)
    assert dec == {} and rej["3+ cells -> credited nowhere (n=2)"] == 1


def test_two_alphas_of_one_mechanic_never_both_enter_the_plan(monkeypatch):
    """One submit kills its whole signal family, so the second is a wasted irreversible action."""
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "same"}, "fitness": 1.5},
            "B": {"old_id": "o2", "meta": {"mechanic": "same"}, "fitness": 1.4}}
    _wire(monkeypatch, rows, {"o1": "f1", "o2": "f2"},
          {"f1": ["News"], "f2": ["Insiders"]}, lambda a: (True, "clean"))
    dec, rej = D.build(CELLS, now=0)
    assert len(dec) == 1 and rej["mechanic already in this plan"] == 1


def test_a_plan_never_over_fills_a_cell(monkeypatch):
    """News needs exactly 1. Two eligible alphas must not both be planned into it."""
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5},
            "B": {"old_id": "o2", "meta": {"mechanic": "m2"}, "fitness": 1.4}}
    _wire(monkeypatch, rows, {"o1": "f1", "o2": "f2"},
          {"f1": ["News"], "f2": ["News"]}, lambda a: (True, "clean"))
    dec, rej = D.build(CELLS, now=0)
    assert len(dec) == 1 and rej["cell already satisfied by this plan"] == 1


def test_the_nearest_to_unlocking_cell_wins(monkeypatch):
    """One submit into a 2/3 cell unlocks it; into a 0/3 cell it unlocks nothing for two more."""
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"}, {"f1": ["Imbalance", "Insiders"]},
          lambda a: (True, "clean"))
    dec, _ = D.build(CELLS, now=0)
    assert dec["A"]["cell"] == "Insiders"


def test_a_low_confidence_mapping_is_refused(monkeypatch):
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    monkeypatch.setattr(D, "_journal_rows", lambda: rows)
    monkeypatch.setattr(D, "_formulas", lambda: {"o1": "f1"})
    monkeypatch.setattr(D, "_submitted_ids", lambda: set())
    monkeypatch.setattr(D.gates, "zero_fail", lambda r: (True, [], []))
    monkeypatch.setattr(D.cell_map, "cells_for",
                        lambda fm, **k: types.SimpleNamespace(cells=["Insiders"], confidence="low"))
    monkeypatch.setattr(D, "corr_ok", lambda a, s, age: (True, "clean"))
    dec, rej = D.build(CELLS, now=0)
    assert dec == {} and rej["cell mapping not high-confidence"] == 1


def test_an_already_submitted_alpha_never_re_enters_a_plan(monkeypatch):
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"}, {"f1": ["Insiders"]}, lambda a: (True, "clean"))
    monkeypatch.setattr(D, "_submitted_ids", lambda: {"A"})
    dec, rej = D.build(CELLS, now=0)
    assert dec == {} and rej["already submitted"] == 1


def test_a_non_gem_never_enters_a_plan(monkeypatch):
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"}, {"f1": ["Insiders"]}, lambda a: (True, "clean"))
    monkeypatch.setattr(D.gates, "zero_fail", lambda r: (False, ["LOW_SHARPE"], []))
    dec, rej = D.build(CELLS, now=0)
    assert dec == {} and rej["not a gem"] == 1


def test_no_cell_counts_means_no_plan(monkeypatch):
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"}, {"f1": ["Insiders"]}, lambda a: (True, "clean"))
    dec, _ = D.build(FakeCells(None), now=0)
    assert dec == {}


# ------------------------------------------------------------------ the write is opt-in

def test_writing_is_opt_in_and_the_module_writes_nothing_on_import():
    """`auto_submit` trusts a decisions file that exists, so producing one must be deliberate."""
    src = (ROOT / "tools" / "decide_submits.py").read_text()
    assert '"--write"' in src
    assert "if not args.write:" in src
    i_guard, i_write = src.index("if not args.write:"), src.index("OUT.write_text(")
    assert i_guard < i_write, "the opt-in guard must precede the only write"
    assert src.count("OUT.write_text(") == 1, "there must be exactly one writer of the decisions file"


def test_the_decisions_shape_matches_what_auto_submit_demands(monkeypatch):
    """A producer that writes the wrong keys is a producer that makes the consumer fail closed —
    or worse, one that omits a key the consumer defaults."""
    rows = {"A": {"old_id": "o1", "meta": {"mechanic": "m1"}, "fitness": 1.5}}
    _wire(monkeypatch, rows, {"o1": "f1"}, {"f1": ["Insiders"]}, lambda a: (True, "clean"))
    dec, _ = D.build(CELLS, now=0)
    assert set(dec["A"]) == {"cell", "region", "delay", "formula", "family", "reason"}
    assert json.loads(json.dumps(dec))            # must be serialisable as-is
