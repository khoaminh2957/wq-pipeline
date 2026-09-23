#!/usr/bin/env python3
"""What submit_rank.py must REFUSE, and what today's real inventory actually yields.

Every test runs with `socket.socket` replaced by a raiser, and `test_socket_ban_is_real` proves the
ban bites. submit_rank is a read-only ranker: if any test in this file ever reaches the network,
the module has grown a capability it must not have.

The last test is a REGRESSION LOCK ON A FINDING, not on code: as of 2026-08-13 every one of the six
short cells (News 2/3, Insiders 2/3, Sentiment 1/3, Social Media 0/3, Short Interest 0/3,
Imbalance 0/3) has an EMPTY shortlist. If a future change makes any of them non-empty, that is
either new inventory or a loosened refusal, and the diff must say which.
"""
import json
import pathlib
import socket
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import submit_rank as SR  # noqa: E402


class NetworkTouched(AssertionError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def raiser(*a, **k):
        raise NetworkTouched("submit_rank tried to open a socket; it is a read-only ranker")
    monkeypatch.setattr(socket, "socket", raiser)


def test_socket_ban_is_real():
    with pytest.raises(NetworkTouched):
        socket.socket()


# ------------------------------------------------------------------ fixtures

def rec(alpha, *, prod=0.50, self_=0.40, sharpe=2.0, turnover=0.20, mech="fieldA+fieldB",
        cells=("News",), spent=False):
    return {"alpha": alpha, "cells": set(cells), "dataset": "", "status": "RESERVE",
            "sharpe": sharpe, "fitness": 1.2, "turnover": turnover, "prod": prod, "self": self_,
            "breach": 0, "csv_prod": prod, "mechanic": mech, "family": SR.family_of(mech),
            "spent": spent}


def ev(*records):
    return {r["alpha"]: r for r in records}


# ------------------------------------------------------------------ the presence contract

def test_missing_prod_is_unrankable_not_last():
    """Absent is neither pass nor fail. The candidate must be ABSENT from the order, not sorted
    to the bottom of it, because a bottom slot is still a slot the driver can reach."""
    code, why = SR.verdict(rec("blind", prod=None))
    assert code == SR.PROD_MISSING
    assert "not clean" in why and "GET" in why           # and it says what measuring would cost
    kept, refused = SR.rank("News", evidence=ev(rec("blind", prod=None)))
    assert kept == []
    assert [c for _, c, _ in refused] == [SR.PROD_MISSING]


def test_missing_self_is_unrankable():
    assert SR.verdict(rec("x", self_=None))[0] == SR.SELF_MISSING


def test_prod_none_never_reaches_the_ranker_via_rank_for_cell():
    e = ev(rec("blind", prod=None), rec("clean", prod=0.50))
    assert SR.rank("News", ["blind", "clean"], evidence=e) [0][0]["alpha"] == "clean"


# ------------------------------------------------------------------ the two limits

@pytest.mark.parametrize("p,code", [(0.6999, SR.RANKABLE), (0.70, SR.PROD_FAIL),
                                    (0.7031, SR.PROD_FAIL), (0.8846, SR.PROD_FAIL)])
def test_prod_limit_is_closed_at_070(p, code):
    """0.7031 is the value the platform itself rejected on 3qeeOxlQ, with `limit: 0.7`."""
    assert SR.verdict(rec("a", prod=p))[0] == code


@pytest.mark.parametrize("s,code", [(0.6999, SR.RANKABLE), (0.70, SR.SELF_FAIL),
                                    (0.8542, SR.SELF_FAIL)])
def test_self_limit_is_closed_at_070(s, code):
    assert SR.verdict(rec("a", self_=s))[0] == code


def test_spent_alpha_is_refused_before_any_correlation_question():
    """A 403 adjudicates and permanently spends the alpha, so a spent id is refused even when its
    correlations look perfect."""
    assert SR.verdict(rec("a", prod=0.10, self_=0.10, spent=True))[0] == SR.SPENT


# ------------------------------------------------------------------ mechanic identity + de-dup

def test_decay_only_variants_are_one_mechanic():
    """6XppexRK and mL55V97K differ ONLY in ts_decay_linear(..., 20) vs (..., 5). Same fields, same
    signal, one submit adjudicates both."""
    f20 = ("signed_power(zscore(ts_decay_linear(add(-rank(divide(close, open)), "
           "multiply(rank(divide(ts_backfill(insd3_form4_bvol, 20), "
           "ts_backfill(insd3_form4_bnum, 20))), 0.7), filter=true), 20)), 1.0)")
    f5 = f20.replace(")), 20)), 1.0)", ")), 5)), 1.0)")
    assert SR.mechanic_of(f20) == SR.mechanic_of(f5)
    assert SR.mechanic_of(f20) == "insd3_form4_bnum+insd3_form4_bvol"
    assert SR.family_of(SR.mechanic_of(f20)) == "insd3_form4"


def test_carrier_and_operators_do_not_create_mechanic_identity():
    """Every alpha in this corpus carries the same close/open/vwap legs. If those counted, every
    alpha would be one mechanic and the de-dup would refuse everything."""
    carrier = "add(-rank(divide(close, open)), multiply(-rank(divide(close, vwap)), 0.6))"
    assert SR.mechanic_of(carrier) == ""
    assert SR.mechanic_of(f"add({carrier}, rank(nws18_relevance))") == "nws18_relevance"


def test_unknown_mechanics_do_not_collide():
    """Two alphas with no formula and no dataset label must not be de-duped against each other."""
    assert SR.mechanic_of("", "") == ""
    e = ev(rec("a", mech=""), rec("b", mech=""))
    kept, _ = SR.rank("News", evidence=e)
    assert len(kept) == 2


def test_second_variant_of_one_mechanic_is_refused_within_a_cell():
    e = ev(rec("strong", prod=0.50, sharpe=3.0, mech="M1"),
           rec("twin", prod=0.51, sharpe=2.9, mech="M1"))
    kept, refused = SR.rank("News", evidence=e)
    assert [r["alpha"] for r in kept] == ["strong"]
    assert ("twin", SR.MECHANIC_DUP) in [(r["alpha"], c) for r, c, _ in refused]


def test_mechanic_dedup_holds_ACROSS_cells_in_one_plan():
    """The wasted-irreversible-action case: one mechanic filling two cells' shortlists would spend
    two submits to adjudicate one signal family."""
    e = ev(rec("shared_a", mech="M1", cells=("News", "Sentiment")),
           rec("shared_b", mech="M1", cells=("News", "Sentiment")))
    plan = SR.plan_shortlists({"News": 1, "Sentiment": 1}, e)
    taken = [r["alpha"] for c in plan.values() for r in c["take"]]
    assert len(taken) == 1, f"one mechanic was spent twice: {taken}"
    assert plan["Sentiment"]["short"] + plan["News"]["short"] == 1


# ------------------------------------------------------------------ the order itself

def test_prod_band_outranks_sharpe():
    """Lexicographic on purpose: nothing measured sets an exchange rate between prod headroom and
    Sharpe, so a big Sharpe may not buy down a correlation risk."""
    e = ev(rec("near_limit_but_huge", prod=0.69, sharpe=9.0, mech="M1"),
           rec("clear_and_modest", prod=0.40, sharpe=1.6, mech="M2"))
    order = [r["alpha"] for r in SR.rank("News", evidence=e)[0]]
    assert order == ["clear_and_modest", "near_limit_but_huge"]


def test_bands_come_from_the_measured_drift():
    """DRIFT is the median |delta| of the 8 prod readings that moved out of 111 paired; the bands
    are one and two of those steps back from the limit."""
    assert SR.prod_band(SR.PROD_LIMIT - 2 * SR.DRIFT - 1e-6) == 0
    assert SR.prod_band(SR.PROD_LIMIT - SR.DRIFT - 1e-6) == 1
    assert SR.prod_band(0.6999) == 2


def test_within_a_band_low_turnover_then_sharpe_breaks_the_tie():
    e = ev(rec("churny", prod=0.40, turnover=0.55, sharpe=3.0, mech="M1"),
           rec("slow", prod=0.41, turnover=0.12, sharpe=1.7, mech="M2"))
    assert [r["alpha"] for r in SR.rank("News", evidence=e)[0]][0] == "slow"


# ------------------------------------------------------------------ the submit_plan contract

def test_rank_for_cell_returns_ids_that_are_a_subset_of_its_input():
    """submit_plan.build_plan RAISES if the ranker names an alpha it did not offer."""
    e = ev(rec("a"), rec("b", mech="M2"), rec("c", prod=None, mech="M3"))
    out = [r["alpha"] for r in SR.rank("News", ["a", "c"], evidence=e)[0]]
    assert set(out) <= {"a", "c"}          # never names an alpha it was not offered
    assert "c" not in out                  # the unmeasured one is absent, not last
    # and the real entry point returns bare ids off the real ledger without raising
    assert all(isinstance(x, str) for x in SR.rank_for_cell("News", ["a", "c"]))


def test_rank_for_cell_ignores_ids_outside_the_cell():
    e = ev(rec("news_one", cells=("News",)), rec("sent_one", cells=("Sentiment",)))
    assert [r["alpha"] for r in SR.rank("News", ["news_one", "sent_one"], evidence=e)[0]] \
        == ["news_one"]


def test_module_holds_no_http_client_and_no_post():
    src = (ROOT / "tools/submit_rank.py").read_text()
    for forbidden in ("requests", "urllib", "http.client", ".post(", "session("):
        assert forbidden not in src.replace("no HTTP client", ""), \
            f"submit_rank.py mentions {forbidden!r}; it must stay read-only"


# ------------------------------------------------------------------ ledger parsing

def test_category_column_wins_over_the_dataset_free_text():
    """QPGG7gn5's dataset reads 'H5_news_tone_imbalance' — a hypothesis NAME whose words claim News
    and Imbalance by accident. Its category says Sentiment, and that is the one that counts."""
    assert SR.cells_claimed("Sentiment", "H5_news_tone_imbalance") == {"Sentiment"}


def test_dataset_is_read_only_when_the_category_names_nothing():
    """The 2026-08-01 funnel rows put an iteration code in `category` and the cell in `dataset`."""
    assert SR.cells_claimed("PX51527r02", "News/News Sentiment") >= {"News"}


def test_measured_files_override_the_csv_columns():
    """winners.csv wrote a per-BATCH self value into the per-alpha column: 1Yppwox6 reads 0.733
    there while state/prod_corr_measured.json measured 0.4013. The measurement must win."""
    e = SR.load_evidence()
    if "1Yppwox6" not in e:
        pytest.skip("ledger no longer carries 1Yppwox6")
    assert e["1Yppwox6"]["self"] == pytest.approx(0.4013)
    assert e["1Yppwox6"]["prod"] == pytest.approx(0.6792)


# ------------------------------------------------------------------ today's real inventory

TODAY = {"News": 1, "Insiders": 1, "Sentiment": 2,
         "Social Media": 3, "Short Interest": 3, "Imbalance": 3}


def test_todays_six_short_cells_all_have_empty_shortlists():
    plan = SR.plan_shortlists(TODAY, SR.load_evidence())
    nonempty = {c: [r["alpha"] for r in d["take"]] for c, d in plan.items() if d["take"]}
    assert nonempty == {}, (
        "a short cell became fillable — say whether that is new inventory or a loosened "
        f"refusal: {nonempty}")
    assert all(d["short"] == TODAY[c] for c, d in plan.items())


def test_every_refusal_in_todays_plan_carries_a_reason():
    plan = SR.plan_shortlists(TODAY, SR.load_evidence())
    for cell, d in plan.items():
        for r, code, why in d["refused"]:
            assert code in {SR.SPENT, SR.PROD_MISSING, SR.SELF_MISSING, SR.PROD_FAIL,
                            SR.SELF_FAIL, SR.MECHANIC_DUP}, (cell, r["alpha"], code)
            assert why.strip(), (cell, r["alpha"])


def test_social_media_and_short_interest_have_no_inventory_at_all():
    """Distinct from 'every candidate was refused': there is nothing in the ledger to refuse."""
    e = SR.load_evidence()
    for cell in ("Social Media", "Short Interest"):
        kept, refused = SR.rank(cell, evidence=e)
        assert kept == [] and refused == [], f"{cell} now has inventory: {kept or refused}"


def test_the_two_unmeasured_candidates_are_named_in_the_report():
    """wpaaEXEd (Imbalance) and 6XppexRK (Insiders) are the whole of the ledger's blind spot; the
    report must name them rather than bury the count."""
    txt = SR.explain(TODAY, SR.load_evidence())
    assert "wpaaEXEd" in txt and "6XppexRK" in txt
    assert "no offline surrogate for PROD" in txt


def test_report_states_what_it_cannot_know():
    txt = SR.explain(TODAY, SR.load_evidence())
    assert "UNKNOWN AGE" in txt
    assert "EMPTY" in txt


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
