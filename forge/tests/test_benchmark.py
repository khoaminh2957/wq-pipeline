"""Suite for forge/offline/benchmark.py -- the pipeline scorecard.

What these pin is the SHAPE of the judgement, not any particular number: floors that cannot be
compensated, uncertainty that cannot be omitted, two submission readings that cannot be silently
collapsed into one, a rank with no constant in it (D25), and a comparison on a pre-registered estimand
that says what it could not have seen (D24). Each test added after architecture round 2 names the
finding it guards (docs/evalharness/audits/architecture_round2.md).
"""
import collections
import datetime
import functools
import hashlib
import math
import random

import pytest

from forge.offline import benchmark as B

H = 3600.0


def _ts(day, hour=12):
    """Epoch seconds of `hour`:00 America/New_York on `day`."""
    return datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time(hour), tzinfo=B.ET).timestamp()


# ----------------------------------------------------------------------------- the scoring frame
def test_a_failed_floor_is_a_fail_however_the_card_ranks():
    """D2 is the whole design: no strong axis may hide a dead one -- and D25's rank cannot either. D29: the
    verdict is the rank's first level, so this FAIL card ranks below a PASS card with a tenth of its rate."""
    axes = {"axis1_product": {"value": 1.0, "floor_met": True, "refuted": 0, "unproven": 0},
            "axis2_throughput": {"value": 40.0, "floor_met": True, "post_horizon": {"final": True}},  # ten times the floor
            "axis3_gearing": {"value": 0.0, "floor_met": False}}        # dead
    card = B.scorecard(axes)
    assert card["verdict"] == "FAIL" and card["floors_unmet"] == ["axis3_gearing"]
    assert card["rank"] == {"verdict": "FAIL", "refuted_or_unproven_submitted": 0, "proven_clean_per_quota_day": 40.0,
                            "axis3_held_fraction": 0.0, "horizon_final": True, "comparable_from_et": None}
    passing = B.scorecard(dict(axes, axis2_throughput=dict(axes["axis2_throughput"], value=4.0),
                               axis3_gearing={"value": 1.0, "floor_met": True}))
    assert passing["verdict"] == "PASS" and B.rank_cmp(passing, card) == -1


def test_all_floors_met_is_the_only_way_to_pass():
    axes = {k: {"value": B.FLOOR[k], "floor_met": True} for k in B.FLOOR}
    assert B.scorecard(axes)["verdict"] == "PASS"


def test_the_composite_and_its_constants_are_gone():
    """D25 (Khoa, 2026-09-23): no 0-100 composite, no weights, no UNPROVEN_CREDIT. Round 2 measured the
    composite falling when clean output was added and flipping rankings at UNPROVEN_CREDIT = 0.474."""
    assert not hasattr(B, "UNPROVEN_CREDIT") and not hasattr(B, "WEIGHT")
    card = B.scorecard({k: {"value": B.FLOOR[k], "floor_met": True} for k in B.FLOOR})
    assert "composite_0_100" not in card
    assert B.RANK_ORDER == ("refuted_or_unproven_submitted", "proven_clean_per_quota_day", "axis3_held_fraction")
    assert B.VERDICT_ORDER == {"PASS": 0, "FAIL": 1}                     # D29: the verdict leads


def _levels(not_proven, rate, a3, verdict="FAIL", final=True):
    return {"rank": {"verdict": verdict, "refuted_or_unproven_submitted": not_proven, "proven_clean_per_quota_day": rate,
                     "axis3_held_fraction": a3, "horizon_final": final, "comparable_from_et": "2026-10-07"}}


def test_the_rank_is_lexicographic_in_the_order_khoa_ticked():
    """D25: (1) fewer refuted (D26: + unproven), (2) more proven clean per quota day, (3) axis 3 -- a lower
    level decides only on a tie above it, and an unmeasured level ranks below every measured value (A5)."""
    assert B.rank_cmp(_levels(0, 0.1, 0.5), _levels(1, 9.0, 1.0)) == -1      # level 1 beats any rate
    assert B.rank_cmp(_levels(1, 0.3, 0.1), _levels(1, 0.2, 1.0)) == -1      # level 2 beats any axis 3
    assert B.rank_cmp(_levels(1, 0.2, 0.9), _levels(1, 0.2, 0.8)) == -1      # level 3 on a tie
    assert B.rank_cmp(_levels(1, 0.2, 0.9), _levels(1, 0.2, 0.9)) == 0
    assert B.rank_cmp(_levels(0, None, 1.0), _levels(0, 0.0, 1.0)) == 1      # unknown exposure < a measured 0
    cards = [_levels(1, 0.5, 1.0), _levels(0, 0.1, 1.0), _levels(0, 0.2, None), _levels(0, 0.2, 0.5)]
    ordered = sorted(cards, key=functools.cmp_to_key(B.rank_cmp))
    assert [c["rank"]["proven_clean_per_quota_day"] for c in ordered] == [0.2, 0.2, 0.1, 0.5]
    assert sorted(cards, key=B.rank_key) == ordered


# ------------------------------------------------------------------ a cohort the axes can grade
PASS = [{"name": n, "result": "PASS"} for n in B.BINDING]
STANDARD = {"h_ok": [], "h_bad": [(2, "counterparty names no agent class")]}


def _settings(decay=4, neut="INDUSTRY"):
    return {"region": "USA", "delay": 1, "universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": 0.08}


def _steady_curve():
    d0 = datetime.date(2019, 1, 2)
    return {(d0 + datetime.timedelta(days=i)).isoformat(): float(i) for i in range(420)}


def _cohort(specs, version=None):
    """specs: (kind, alpha, day, post_lag_days or None). kind P = PROVEN (every gate measured and
    passing: two true neighbours, a steady curve, DSR/PBO/corr passing, admissible hypothesis); U =
    UNPROVEN (no neighbours); R = REFUTED (its hypothesis trips a hard gate).
    Returns (rows, scored, corr, history, curves)."""
    rows, scored, corr, hist, curves = [], {}, {}, [], {}
    for kind, alpha, day, lag in specs:
        meta = {"hypothesis": "h_bad" if kind == "R" else "h_ok", "mechanism_key": "m_%s" % alpha}
        if version:
            meta["pipeline_version"] = version
        base = {"status": "COMPLETE", "checks": PASS, "dateCreated": "%sT12:00:00-04:00" % day,
                "formula": "rank(%s)" % alpha, "meta": meta}
        rows.append(dict(base, alpha=alpha, sharpe=1.8, settings=_settings()))
        if kind in ("P", "R"):
            rows.append(dict(base, alpha=alpha + "_n1", sharpe=1.7, settings=_settings(decay=8)))
            rows.append(dict(base, alpha=alpha + "_n2", sharpe=1.6, settings=_settings(neut="SUBINDUSTRY")))
        scored[alpha] = {"dsr": 0.97, "pbo_pass": True}
        corr[alpha] = {"prod": 0.5, "self": 0.4}
        curves[alpha] = _steady_curve()
        if lag is not None:
            hist.append({"alpha": alpha, "http": 201, "posted_at": _ts(day) + lag * 86400, "mechanism_key": None})
    return rows, scored, corr, hist, curves


def _card(specs, now, version=None, deploys=None, **kw):
    rows, scored, corr, hist, curves = _cohort(specs, version)
    return B.build_from(rows, scored, corr, hist, curves, STANDARD, now=now, version=version, deploys=deploys, **kw)


NOW_0923 = _ts("2026-09-23", 15)
#: D27: a card is ranked only once its POST horizon is final at seen_until. Every fixture row below is created
#: by 09-22, whose horizon closes 2026-10-07 00:00 ET, so cards that are RANKED are graded at this clock.
NOW_1010 = _ts("2026-10-10", 15)


def test_the_rank_is_monotone_in_proven_output_at_the_desks_real_exposure():
    """F4-NL / A6, through the real axis1_product at the desk's 19 quota days (09-04..09-22). Round 2:
    P 32.8, P+U 28.0, P+P+P+R 28.3 -- adding clean output LOWERED the composite. Under D25 adding a
    proven submission can only raise the rank. D26: an UNPROVEN submission now costs a place at level 1
    exactly like a refuted one -- before it, P+U tied P, so not measuring paid (draw-3 scoring SERIOUS 2).
    The ticked order puts level 1 first, so P+P+P+R and P+P+P+U rank below P: D25/D26 as decided, pinned
    here so it is never a surprise."""
    P = [("P", "p1", "2026-09-05", 0.1)]
    U = [("U", "u1", "2026-09-06", 0.1)]
    PPP = P + [("P", "p2", "2026-09-07", 0.1), ("P", "p3", "2026-09-08", 0.1)]
    R = [("R", "r1", "2026-09-09", 0.1)]
    cards = {name: _card(s, NOW_1010, since="2026-09-04", until="2026-09-23")
             for name, s in (("P", P), ("P+U", P + U), ("PPP", PPP), ("PPP+U", PPP + U), ("PPP+R", PPP + R))}
    assert all(c["window"]["quota_days"] == 19 for c in cards.values())
    k = {name: B.rank_key(c) for name, c in cards.items()}
    assert k["P+U"] > k["P"]                         # D26: an unproven submission costs a place
    assert k["PPP"] < k["P"]                         # more proven output ranks higher
    assert k["PPP+U"] > k["PPP"] and k["PPP+U"] > k["P"] and k["PPP+U"] == k["PPP+R"]
    assert k["PPP+R"] > k["PPP"] and k["PPP+R"] > k["P"]
    assert cards["PPP+U"]["rank"]["refuted_or_unproven_submitted"] == 1
    assert cards["PPP"]["rank"]["proven_clean_per_quota_day"] == round(3 / 19, 3)


AXIS3_MET = {"value": 1.0, "floor_met": True}


def test_an_unproven_submission_never_counts_as_clean():
    """A5: clean used to be 'not refuted', so four submissions whose neighbourhood was never measured
    met the axis-2 floor. Now only PROVEN counts; unproven is reported beside it -- and unproven fails
    AXIS 1's floor too (the adjudicator's surviving mutant 'axis-1 floor = none refuted' passed here)."""
    specs = [("U", "u%d" % i, "2026-09-22", 0.1) for i in range(4)]
    card = _card(specs, NOW_0923, since="2026-09-22", axis3=AXIS3_MET)
    a1, a2 = card["axes"]["axis1_product"], card["axes"]["axis2_throughput"]
    assert a1["status_counts"] == {"unproven": 4} and a1["value"] == 0.0
    assert a1["refuted"] == 0 and a1["floor_met"] is False                 # 0 refuted is not enough
    assert a2["proven_clean_submissions"] == 0 and a2["unproven_submissions"] == 4
    assert a2["proven_clean_per_quota_day"] == 0.0 and not a2["floor_met"]
    assert card["verdict"] == "FAIL" and card["floors_unmet"] == ["axis1_product", "axis2_throughput"]
    proven = _card([("P", "p%d" % i, "2026-09-22", 0.1) for i in range(4)], NOW_0923, since="2026-09-22",
                   axis3=AXIS3_MET)
    assert proven["axes"]["axis2_throughput"]["proven_clean_per_quota_day"] == 4.0
    assert proven["verdict"] == "PASS"


def test_an_absent_axis_is_an_unmet_floor():
    """Draw-3 scoring MINOR (S7): `k in axes and ...` read a card with NO axis 3 as meeting the axis-3
    floor, and this suite pinned that PASS. A floor nobody measured has not been met."""
    specs = [("P", "p%d" % i, "2026-09-22", 0.1) for i in range(4)]
    card = _card(specs, NOW_0923, since="2026-09-22")                      # no axis3 passed
    assert "axis3_gearing" not in card["axes"]
    assert card["verdict"] == "FAIL" and card["floors_unmet"] == ["axis3_gearing"]
    assert card["floors_absent"] == ["axis3_gearing"]
    assert B.scorecard({})["floors_unmet"] == list(B.FLOOR)


# ------------------------------------------------------------------------------- the uncertainty
def test_wilson_widens_as_the_sample_shrinks_and_never_leaves_zero_one():
    wide = B.wilson(1, 300)
    narrow = B.wilson(100, 30000)
    assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])
    for k, n in ((0, 10), (3, 31044), (1, 1), (0, 0)):
        lo, hi = B.wilson(k, n)
        assert 0.0 <= lo <= hi <= 1.0


def test_the_desks_own_numbers_come_out_where_they_should():
    lo, hi = B.wilson(3, 31044)               # 3 submissions in the whole forge era
    assert lo * 5000 == pytest.approx(0.16, abs=0.02) and hi * 5000 == pytest.approx(1.42, abs=0.05)
    lo, hi = B.wilson(1, 300)                 # one submission in a 300-alpha window
    assert hi / max(lo, 1e-9) > 20            # an interval spanning a factor of twenty says nothing


def test_a_window_with_no_events_still_bounds_the_rate():
    """One clean quota day does not exclude a true rate of 3 per day -- the reason D5's one-day
    window cannot rank two versions on the count alone."""
    assert B.rule_of_three(5000) * 5000 == pytest.approx(3.0)
    assert math.isinf(B.rule_of_three(0))


def test_the_poisson_interval_is_a_rate_per_day_and_bounds_zero_events():
    lo, hi = B.poisson_interval(0, 1)
    assert lo == 0.0 and 3.6 < hi < 3.8                      # exact upper bound for k=0 is -ln(0.025)
    lo, hi = B.poisson_interval(4, 19)
    assert 0.05 < lo < 0.06 and 0.53 < hi < 0.55             # the desk's own history, 4 over 19 days


# -------------------------------------------------------------------------- axis 1's measures
def _row(alpha, sharpe, formula="rank(x)", decay=4, neut="INDUSTRY", trunc=0.08, hyp="h"):
    return {"alpha": alpha, "sharpe": sharpe, "formula": formula,
            "settings": {"region": "USA", "delay": 1, "universe": "TOP3000", "decay": decay,
                         "neutralization": neut, "truncation": trunc},
            "meta": {"hypothesis": hyp}}


def _by_formula(rows):
    import collections
    idx = collections.defaultdict(list)
    for r in rows:
        s = r["settings"]
        idx[(B._norm_formula(r["formula"]), s["region"], s["delay"], s["universe"])].append(r)
    return idx


def test_neighbourhood_uses_true_one_setting_neighbours_only():
    """Round 1, S2: the whole hypothesis group is not a neighbourhood. Only the same formula with
    exactly one of decay / neutralisation / truncation changed counts."""
    me = _row("me", 1.7)
    rows = [me, _row("d8", 0.1, decay=8), _row("sub", 0.2, neut="SUBINDUSTRY"),
            _row("two_knobs", 1.7, decay=8, neut="SECTOR"),          # two settings differ: not a neighbour
            _row("other_formula", 1.7, formula="rank(y)", decay=8)]   # a different formula: not a neighbour
    v = B.neighbourhood_stability(_by_formula(rows), me)
    assert v["n"] == 2 and v["verdict"] == "fragile"
    steady = [me, _row("d8", 1.6, decay=8), _row("sub", 1.5, neut="SUBINDUSTRY")]
    assert B.neighbourhood_stability(_by_formula(steady), me)["verdict"] == "stable"


def test_too_few_neighbours_is_unmeasured_never_a_pass_or_a_fail():
    me = _row("me", 1.7)
    assert B.neighbourhood_stability(_by_formula([me, _row("d8", 1.6, decay=8)]), me)["verdict"] == "unmeasured"


def test_a_cached_curve_is_a_date_dict_and_is_read_in_date_order():
    """Round 1, F2: all 2,810 cached curves are {date: cumulative} dicts and the first version turned
    every one into [] -- axis 1 read 'insufficient' for every alpha."""
    d0 = datetime.date(2019, 1, 2)
    curve = {(d0 + datetime.timedelta(days=i)).isoformat(): float(i) for i in range(400)}
    shuffled = dict(reversed(list(curve.items())))              # insertion order must not matter
    assert B.curve_values(shuffled) == [float(i) for i in range(400)]
    assert B.regime_stability(shuffled)["verdict"] == "consistent"


def test_regime_stability_separates_a_steady_alpha_from_a_one_window_bet():
    steady = [i * 1.0 for i in range(400)]
    v = B.regime_stability(steady)
    assert v["verdict"] == "consistent" and all(x == float("inf") for x in v["thirds"])
    one = [i * 1.0 for i in range(133)] + [132.0] * 267
    assert B.regime_stability(one)["verdict"] == "one-regime"
    two = [i * 1.0 for i in range(266)] + [265.0] * 134
    assert B.regime_stability(two)["verdict"] == "mixed"


def _curve_from(thirds):
    """A 421-point cumulative curve from three 140-day runs of daily changes."""
    v, out = 0.0, [0.0]
    for seg in thirds:
        for x in seg:
            v += x
            out.append(v)
    return out


WIN = [1.0] * 140                                  # sd 0, mean +1: winning
LOSE_BIG = [-1.0] * 140                            # sd 0, mean -1: losing
LOSE_SMALL = [-0.5] * 140
NOISY_UP = [1.1, -1.0] * 70                        # mean +0.05, SE ~0.09 (t ~0.6): FLAT, though its mean is > 0


def test_a_third_is_judged_against_its_own_standard_error():
    """S3-NL: the sign of a third's mean decided, so two near-flat thirds and one losing third read
    'mixed' and PASSED while the whole curve lost money (round 2: Sharpe -2.58, PnL -101.4)."""
    flat_flat_lose = B.regime_stability(_curve_from([NOISY_UP, NOISY_UP, LOSE_BIG]))
    assert flat_flat_lose["labels"] == ["flat", "flat", "losing"]
    assert flat_flat_lose["overall_pnl"] < 0 and flat_flat_lose["verdict"] == "negative-overall"
    assert flat_flat_lose["verdict"] not in B.REGIME_PASS
    # overall positive, but one third lost beyond noise: still not a pass
    win_win_lose = B.regime_stability(_curve_from([WIN, WIN, LOSE_SMALL]))
    assert win_win_lose["overall_pnl"] > 0 and win_win_lose["verdict"] == "losing-third"
    # three positive MEANS, only one beyond noise: a one-window bet, not 'consistent'
    one_real = B.regime_stability(_curve_from([WIN, NOISY_UP, NOISY_UP]))
    assert one_real["labels"] == ["winning", "flat", "flat"] and one_real["verdict"] == "one-regime"
    # two real wins and a flat third (no loss beyond noise) still pass
    assert B.regime_stability(_curve_from([WIN, WIN, NOISY_UP]))["verdict"] == "mixed"


def test_a_short_or_absent_curve_is_unmeasured():
    assert B.regime_stability([1, 2, 3])["verdict"] == "unmeasured"
    assert B.regime_stability(None)["verdict"] == "unmeasured"


def test_alpha_status_keeps_unmeasured_apart_from_passed_and_failed():
    assert B.alpha_status({"a": True, "b": True}) == "proven"
    assert B.alpha_status({"a": True, "b": None}) == "unproven"
    assert B.alpha_status({"a": False, "b": None}) == "refuted"


def test_a_version_card_draws_neighbours_from_its_own_rows_only():
    """S10-NL: the neighbour pool was every scored row of every version, so version B's simulations
    could refute version A's alpha after the fact."""
    rows, scored, corr, hist, curves = _cohort([("U", "a1", "2026-09-10", 0.1)], version="A")
    # version B later simulates a1's formula with one knob changed, and those neighbours collapse
    for alpha, s in (("b_n1", _settings(decay=8)), ("b_n2", _settings(neut="SUBINDUSTRY"))):
        rows.append({"alpha": alpha, "status": "COMPLETE", "checks": PASS, "dateCreated": "2026-09-15T12:00:00-04:00",
                     "formula": "rank(a1)", "sharpe": 0.1, "settings": s, "meta": {"pipeline_version": "B"}})
    now = _ts("2026-09-20", 15)
    as_version = B.build_from(rows, scored, corr, hist, curves, STANDARD, version="A", now=now)
    d = as_version["axes"]["axis1_product"]["detail"][0]
    assert d["neighbourhood"]["verdict"] == "unmeasured" and d["status"] == "unproven"
    by_date = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=now, since="2026-09-10", until="2026-09-11")
    assert by_date["axes"]["axis1_product"]["detail"][0]["status"] == "refuted"   # the weak card still pools


def test_every_card_carries_its_provenance():
    """S10-NL: a card could not say what produced it. The clock is the one passed in, the scorer is
    named by the sha256 of its bytes, the inputs by their sizes and latest dates."""
    rows, scored, corr, hist, curves = _cohort([("P", "p1", "2026-09-10", 0.1), ("U", "u1", "2026-09-12", None)])
    now = _ts("2026-09-20", 15)
    pv = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=now, deploys=[])["provenance"]
    assert pv["generated_at"] == now and pv["generated_at_et"].startswith("2026-09-20T15:00")
    assert pv["scorer_sha256"] == hashlib.sha256(open(B.__file__, "rb").read()).hexdigest()
    assert pv["inputs"]["rows"] == 4 and pv["inputs"]["scored_rows"] == 4 and pv["inputs"]["last_row_day"] == "2026-09-12"
    assert pv["inputs"]["accepted_posts"] == 1 and pv["inputs"]["last_post_day"] == "2026-09-10"
    assert pv["inputs"]["standard"] == 2 and pv["inputs"]["deploys"] == 0
    # round 4 m4: the meaning ledger is bounded by the WRITER's scored_at, so a back-dated row written later moves a
    # re-grade at the same clock; the card says so, and meaning_index's docstring no longer claims otherwise
    assert any(x.startswith("meaning") for x in pv["not_bounded_by_now"])
    assert "so a card graded later is not moved by a row written after its clock" not in " ".join(
        B.meaning_index.__doc__.split())


# ------------------------------------------------------------------------ axis 2 and the windows
def test_the_two_submission_readings_are_reported_separately():
    """rK5RGeqa was generated 09-10 and POSTed on the 09-22 ET quota day: not this version's product
    under D14, but today's submission to the operator."""
    rows = [{"alpha": "x", "sharpe": 1.0, "checks": [], "formula": None, "meta": {}, "settings": {}}]
    t = B.axis2_throughput(rows, [], days=1, proven_alphas=set(), posts_in_window=[{"alpha": "older"}])
    assert t["submissions_of_alphas_this_version_produced"] == 0 and t["posts_this_version_made"] == 1


def test_axis2_is_per_quota_day_and_counts_only_proven_submissions():
    """Round 1, F3 and F4: the floor is per quota day; A5: only a PROVEN submission is throughput."""
    rows = [{"alpha": str(i), "checks": [], "formula": None, "meta": {}, "settings": {}} for i in range(100)]
    subs = [{"alpha": "1", "mechanism_key": "a"}, {"alpha": "2", "mechanism_key": "b"}]
    t = B.axis2_throughput(rows, subs, days=2, proven_alphas={"1"}, statuses={"1": "proven", "2": "unproven"})
    assert t["proven_clean_submissions"] == 1 and t["proven_clean_per_quota_day"] == 0.5
    assert t["unproven_submissions"] == 1
    assert t["poisson_95_per_day"][0] > 0.0


def test_sustainable_needs_all_three_pieces_of_evidence():
    rows = [{"alpha": str(i), "checks": [], "formula": None, "meta": {}, "settings": {}} for i in range(100)]
    subs = [{"alpha": str(i), "mechanism_key": m} for i, m in ((1, "a"), (2, "b"), (3, "a"), (4, "b"))]
    proven = {"1", "2", "3", "4"}
    assert B.axis2_throughput(rows, subs, 2, proven, held_next=True)["sustainable"] is True
    one_mech = [{"alpha": str(i), "mechanism_key": "a"} for i in (1, 2, 3, 4)]
    assert B.axis2_throughput(rows, one_mech, 2, proven, held_next=True)["sustainable"] is False
    assert B.axis2_throughput(rows, subs, 2, proven, held_next=False)["sustainable"] is False
    # S9-NL: a next window that cannot be judged yet is NOT a False
    assert B.axis2_throughput(rows, subs, 2, proven, held_next="not evaluable")["sustainable"] == "not evaluable"


def test_a_whole_history_card_says_not_evaluable_not_false():
    """S9-NL: with since=None the comparison window lay wholly before the cohort's first row, and that
    read as held_in_previous_window False on every whole-history and version card."""
    card = _card([("P", "p%d" % i, "2026-09-%02d" % (10 + i), 0.1) for i in range(5)], NOW_0923)
    ev = card["axes"]["axis2_throughput"]["sustainability_evidence"]
    assert ev["held_in_next_window"] == "not evaluable"
    assert "has not finished" in card["axes"]["axis2_throughput"]["next_window"]


def test_d7_reads_the_next_window_and_counts_only_proven_there():
    """D7 as written: the rate must hold in the NEXT window of equal length (draw 2 read the previous
    one). m1: a refuted POST in that window is not the rate holding."""
    win = dict(since="2026-09-10", until="2026-09-12")          # window 09-10..11; next window 09-12..13
    held = _card([("P", "a", "2026-09-10", 0.1), ("P", "b", "2026-09-12", 0.1)], _ts("2026-09-20", 15), **win)
    assert held["axes"]["axis2_throughput"]["sustainability_evidence"]["held_in_next_window"] is True
    refuted_only = _card([("P", "a", "2026-09-10", 0.1), ("R", "b", "2026-09-12", 0.1)], _ts("2026-09-30", 15), **win)
    assert refuted_only["axes"]["axis2_throughput"]["sustainability_evidence"]["held_in_next_window"] is False
    # the same, graded before the next window's POST horizon has closed: not yet a False
    open_horizon = _card([("P", "a", "2026-09-10", 0.1), ("R", "b", "2026-09-12", 0.1)], _ts("2026-09-20", 15), **win)
    assert open_horizon["axes"]["axis2_throughput"]["sustainability_evidence"]["held_in_next_window"] == "not evaluable"
    nothing_ran = _card([("P", "a", "2026-09-10", 0.1)], _ts("2026-09-30", 15), **win)
    assert nothing_ran["axes"]["axis2_throughput"]["sustainability_evidence"]["held_in_next_window"] == "not evaluable"


def _journal_row(alpha, day, status="COMPLETE", version=None):
    return {"alpha": alpha, "status": status, "checks": [{"name": "LOW_SHARPE", "result": "FAIL"}],
            "dateCreated": "%sT12:00:00-04:00" % day, "formula": "rank(%s)" % alpha,
            "settings": {"region": "USA", "delay": 1}, "meta": {"pipeline_version": version} if version else {}}


def test_the_window_is_whole_et_quota_days_and_never_the_unfinished_one():
    """Round 1, S5: local midnight, and a one-minute window 'met' 4 per day."""
    rows = [_journal_row("a", "2026-09-21"), _journal_row("b", "2026-09-22"), _journal_row("c", "2026-09-23")]
    card = B.build_from(rows, {}, {}, [], {}, {}, now=NOW_0923)
    assert card["window"]["quota_days"] == 2 and card["window"]["excluded_unfinished_day"] == "2026-09-23"
    assert card["axes"]["axis2_throughput"]["scored_alphas"] == 2          # c, from the unfinished day, is out


def test_warning_rows_are_scored():
    """Round 1, F3: WARNING rows (16 % of the journal, the first ACTIVE submission among them) were dropped."""
    card = B.build_from([_journal_row("w", "2026-09-22", status="WARNING")], {}, {}, [], {}, {}, now=NOW_0923)
    assert card["axes"]["axis2_throughput"]["scored_alphas"] == 1


def test_an_unknown_version_is_an_error_not_all_history():
    with pytest.raises(ValueError, match="no scored row carries"):
        B.build_from([_journal_row("a", "2026-09-22", version="v1")], {}, {}, [], {}, {}, version="nope", now=NOW_0923)


def test_build_from_never_reads_the_clock():
    """A4: the clock is an argument. A card graded 'now' used to change with the hour it was run."""
    with pytest.raises(ValueError, match="pass `now`"):
        B.build_from([_journal_row("a", "2026-09-22")], {}, {}, [], {}, {})


def test_a_post_counts_only_within_the_horizon_and_by_now():
    """A4: a POST credited to the alpha's cohort must land within POST_HORIZON_DAYS of creation and not
    after the grading clock; round 2 measured a closed window's rate RISING after the fact."""
    assert B.POST_HORIZON_DAYS == 14
    specs = [("P", "late", "2026-09-01", B.POST_HORIZON_DAYS + 6),     # POSTed 09-21: past the horizon
             ("P", "in", "2026-09-02", 10),                            # POSTed 09-12
             ("P", "future", "2026-09-03", 1)]                         # POSTed 09-04, after this `now`
    card = _card(specs, _ts("2026-09-04", 0) - 60, since="2026-09-01")
    assert card["axes"]["axis2_throughput"]["submissions_of_alphas_this_version_produced"] == 0
    later = _card(specs, _ts("2026-09-30", 15), since="2026-09-01", until="2026-09-04")
    t = later["axes"]["axis2_throughput"]
    assert t["submissions_of_alphas_this_version_produced"] == 2 and t["proven_clean_submissions"] == 2
    # D49 (Khoa, 2026-09-23): moved from {"in", "future"} -- the late POST is graded by axis 1 (and so counts at
    # rank level 1) though it is never credited
    assert {d["alpha"] for d in later["axes"]["axis1_product"]["detail"]} == {"late", "in", "future"}
    assert later["axes"]["axis1_product"]["posted_beyond_the_horizon"] == ["late"]
    assert t["post_horizon"]["final"] is True
    assert _card(specs, _ts("2026-09-10", 15), since="2026-09-01", until="2026-09-04")[
        "axes"]["axis2_throughput"]["post_horizon"]["final"] is False


def test_one_alpha_posted_twice_counts_once():
    """M6: one alpha with two accepted POSTs read clean_submissions 2."""
    rows, scored, corr, hist, curves = _cohort([("P", "p1", "2026-09-10", 0.1)])
    hist.append(dict(hist[0], posted_at=hist[0]["posted_at"] + H))
    card = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-30", 15),
                        since="2026-09-10", until="2026-09-11")
    assert card["axes"]["axis2_throughput"]["proven_clean_submissions"] == 1


# ------------------------------------------------------------------------------------ exposure
def _deploy(pv, day, outcome="deployed", hour=10):
    row = {"outcome": outcome, "started_at": _ts(day, hour) - 600, "finished_at": _ts(day, hour),
           "version": "tree-" + str(pv), "git_dirty": False, "commit_time": None}
    if pv is not None:
        row["pipeline_version"] = pv
    return row


def test_live_days_come_from_the_deploy_ledger():
    """A3: exposure = the ET days the version was RUNNING. Deploy days are excluded (two versions ran on
    them), a rollback restores the previous version, a failed rollback makes the running one unknown,
    and a re-deploy of the same pipeline version is not a change."""
    ledger = [_deploy("A", "2026-09-01"), _deploy("A", "2026-09-03"),          # same-version re-deploy
              _deploy("B", "2026-09-05", "rolled_back"), _deploy("B", "2026-09-08"),
              _deploy("C", "2026-09-12", "rollback_failed")]
    now = _ts("2026-09-15", 12)
    a = B.live_days(ledger, "A", now)
    assert a["known"] and a["days"] == ["2026-09-02", "2026-09-03", "2026-09-04", "2026-09-06", "2026-09-07"]
    assert B.live_days(ledger, "B", now)["days"] == ["2026-09-09", "2026-09-10", "2026-09-11"]
    assert B.live_days(ledger, "C", now)["known"] is False                   # never went live
    assert B.live_days(None, "A", now)["known"] is False
    # MEASURED 2026-09-23: the real ledger row carries `version`, not `pipeline_version`
    assert B.live_days([_deploy(None, "2026-09-01")], "8f8b7517b8598d07", now)["known"] is False


def test_a_retired_version_card_does_not_decay():
    """A3, round 2 (v12_decay.py): 20 clean over 09-10..14 read 4.0 PASS graded on 09-15 and 1.538 FAIL
    graded on 09-23 -- same rows -- because the card ran from the first row to TODAY."""
    specs = [("P", "v%02d" % i, "2026-09-%02d" % (10 + i // 4), 0.05) for i in range(20)]
    ledger = [_deploy("V", "2026-09-09"), _deploy("W", "2026-09-15")]
    early = _card(specs, _ts("2026-09-16", 15), version="V", deploys=ledger)
    late = _card(specs, NOW_0923, version="V", deploys=ledger)
    for c in (early, late):
        t = c["axes"]["axis2_throughput"]
        assert c["window"]["quota_days"] == 5 and t["proven_clean_per_quota_day"] == 4.0 and t["floor_met"]
    assert late["window"]["exposure"]["known"] is True


def test_without_the_ledger_a_version_card_says_exposure_unknown():
    """A3: no guessing the denominator. The card grades the product but carries no rate and cannot meet
    the throughput floor; its rank level 2 sorts below every measured rate."""
    specs = [("P", "v%02d" % i, "2026-09-%02d" % (10 + i // 4), 0.05) for i in range(20)]
    card = _card(specs, NOW_0923, version="V", deploys=None)
    t = card["axes"]["axis2_throughput"]
    assert t["quota_days"] is None and t["proven_clean_per_quota_day"] is None and t["exposure"] == "exposure unknown"
    assert not t["floor_met"] and "exposure unknown" in card["window"]["exposure"]["note"]
    assert card["axes"]["axis1_product"]["proven"] == 20
    assert card["rank"]["proven_clean_per_quota_day"] is None
    late = _card(specs, NOW_1010, version="V", deploys=None)             # D27: ranked once final
    assert B.rank_cmp(late, _card(specs[:1], NOW_1010, since="2026-09-10", until="2026-09-23")) == 1


# -------------------------------------------------------------------- the post-deploy comparison
def _arm(version, days, n_per_day, k_by_day):
    rows = []
    for d, k in zip(days, k_by_day):
        for i in range(n_per_day):
            rows.append({"alpha": "%s_%s_%d" % (version, d, i), "status": "COMPLETE",
                         "checks": PASS if i < k else [{"name": "LOW_SHARPE", "result": "FAIL"}],
                         "dateCreated": "%sT12:00:00-04:00" % d, "formula": "rank(x%d)" % i,
                         "settings": {"region": "USA", "delay": 1}, "meta": {"pipeline_version": version}})
    return rows


A_DAYS = ["2026-09-%02d" % d for d in range(1, 6)]
B_DAYS = ["2026-09-%02d" % d for d in range(10, 15)]


def test_the_estimand_is_pre_registered_and_is_not_the_submission_count():
    """D24: fixed before any comparison; every report that uses it must say it is not the submission count."""
    assert B.ESTIMAND["name"] == "alphas clearing EVERY binding check per 1,000 scored alphas"
    assert B.ESTIMAND["per"] == 1000 and B.ESTIMAND["alpha"] == 0.05
    rows = _arm("A", A_DAYS, 1000, [2, 1, 1, 1, 1]) + _arm("B", B_DAYS, 1000, [4, 4, 4, 3, 3])
    out = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=_ts("2026-09-20", 15))
    assert out["estimand"] == B.ESTIMAND["name"] and "NOT the submission count" in out["estimand_is_not"]
    assert out["versions"]["A"]["scored_alphas"] == 5000 and out["versions"]["A"]["clearing_every_binding_check"] == 6


def test_the_exact_test_matches_a_hand_count():
    """Second derivation (RULE 0 #5): K = 24 events, 18 of them in B, equal exposure -> under H0
    k_B ~ Binomial(24, 1/2); P(k_B >= 18) = (C(24,18)+...+C(24,24)) / 2^24 = 190051 / 16777216."""
    assert sum(math.comb(24, i) for i in range(18, 25)) == 190051
    assert B.rate_test_p(6, 5000, 18, 5000) == pytest.approx(2 * 190051 / 2 ** 24, rel=1e-9)
    assert B.rate_test_p(0, 10, 0, 10) == 1.0


def test_compare_uses_an_exact_test_not_interval_overlap():
    """A1: 'different when the 95 % intervals do not overlap' has a size of at most 0.3 %. Here the two
    intervals overlap and the exact test (p = 0.0227) still separates the arms."""
    rows = _arm("A", A_DAYS, 1000, [2, 1, 1, 1, 1]) + _arm("B", B_DAYS, 1000, [4, 4, 4, 3, 3])
    now = _ts("2026-09-20", 15)
    out = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=now)
    ia, ib = out["versions"]["A"]["exact_95_per_1000"], out["versions"]["B"]["exact_95_per_1000"]
    assert ib[0] < ia[1]                                          # the intervals overlap
    assert out["p_value"] == pytest.approx(0.02266, abs=1e-4) and out["verdict"] == "better"
    assert B.compare(rows, [], {}, {}, {}, {}, "B", "A", now=now)["verdict"] == "worse"
    same = _arm("A", A_DAYS, 1000, [2, 1, 1, 1, 1]) + _arm("B", B_DAYS, 1000, [1, 1, 2, 1, 1])
    assert B.compare(same, [], {}, {}, {}, {}, "A", "B", now=now)["verdict"] == "indistinguishable"


def test_compare_takes_now_and_never_reads_the_clock():
    """A4: compare() called current_quota_day() with no argument, so its verdict depended on the hour."""
    rows = _arm("A", A_DAYS, 10, [1] * 5) + _arm("B", B_DAYS, 10, [1] * 5)
    with pytest.raises(TypeError):
        B.compare(rows, [], {}, {}, {}, {}, "A", "B")
    out = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=_ts("2026-09-12", 15))
    assert out["graded_at"] == _ts("2026-09-12", 15) and out["excluded_unfinished_day"] == "2026-09-12"
    assert out["versions"]["B"]["scored_alphas"] == 20                 # 09-10, 09-11 only; 09-12 is unfinished


def _poisson_draw(rng, lam):
    k, p = 0, math.exp(-lam)
    c, u = p, rng.random()
    while u > c:
        k += 1
        p *= lam / k
        c += p
    return k


def test_the_minimum_detectable_ratio_is_what_a_simulation_detects():
    """A1: a comparison must say what it could have seen. Second derivation by simulation, independent
    of _power(): draw both arms' counts at the stated ratio and run the real test; about 80 % of draws
    must reject there, and at ratio 1 no more than alpha (the test is exact, so conservative)."""
    n, base = 5000, 24 / 10000
    mdr = B.minimum_detectable_ratio(n, n, base)
    assert mdr["increase"] and mdr["decrease"] is not None and mdr["increase"] > 1 > mdr["decrease"]
    rng = random.Random(20260923)

    def rejects(ratio, draws=3000):
        return sum(B.rate_test_p(_poisson_draw(rng, base * n), n, _poisson_draw(rng, base * n * ratio), n)
                   <= B.ESTIMAND["alpha"] for _ in range(draws)) / draws
    assert 0.77 <= rejects(mdr["increase"]) <= 0.92
    assert 0.77 <= rejects(mdr["decrease"]) <= 0.92
    assert rejects(1.0) <= B.ESTIMAND["alpha"] + 0.012
    assert rejects(mdr["increase"] / 1.4) < 0.77


def test_at_the_desks_rate_one_day_cannot_see_a_collapse_and_the_card_says_so():
    """A1 restated on D24's estimand. POST-HOC base: 37 of 32,656 scored alphas cleared every binding
    check in the forge era (1.13 per 1,000), about 1,500-5,000 scored a day. With ~1,500 each, even a
    B that clears nothing cannot be flagged; with a week's volume each (~21,000), it can."""
    base = 37 / 32656
    one_day = B.minimum_detectable_ratio(1500, 1500, base)
    assert one_day["decrease"] is None
    assert "NO decrease" in B._mdr_statement(dict(one_day, baseline_per_1000=base * 1000), 1500, 1500)
    assert B.minimum_detectable_ratio(21000, 21000, base)["decrease"] is not None


def test_compare_prints_the_calendar_gap():
    """A3/A4: versions run one after another (D21: no concurrent control), so the calendar is confounded
    with the version; the gap between the windows is printed with the design."""
    rows = _arm("A", ["2026-09-01", "2026-09-03"], 50, [1, 1]) + _arm("B", ["2026-09-10", "2026-09-12"], 50, [1, 1])
    out = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=_ts("2026-09-20", 15))
    assert out["calendar"]["a"] == ["2026-09-01", "2026-09-03"] and out["calendar"]["b"] == ["2026-09-10", "2026-09-12"]
    assert out["calendar"]["gap_days"] == 6 and "6 calendar day(s)" in out["calendar"]["statement"]
    assert "sequential" in out["design"] and "minimum_detectable_ratio" in out
    assert "round 3 F1" in out["design"]


def test_the_submission_reading_waits_for_the_post_horizon():
    """A4, round 2 (v3_compare.py): two IDENTICAL cohorts, each alpha POSTed some days after creation,
    read 1.714/day against 0 -- 'worse' -- because the newer cohort's POSTs had not happened yet."""
    ledger = [_deploy("A", "2026-09-01"), _deploy("B", "2026-09-05"), _deploy("C", "2026-09-09")]
    a_rows, a_sc, a_co, a_hi, a_cu = _cohort([("P", "a%d" % i, d, 12) for i, d in
                                              enumerate(("2026-09-02", "2026-09-03", "2026-09-04"))], "A")
    b_rows, b_sc, b_co, b_hi, b_cu = _cohort([("P", "b%d" % i, d, 12) for i, d in
                                              enumerate(("2026-09-06", "2026-09-07", "2026-09-08"))], "B")
    args = (a_rows + b_rows, a_hi + b_hi, {**a_cu, **b_cu}, STANDARD, {**a_sc, **b_sc}, {**a_co, **b_co}, "A", "B")
    early = B.compare(*args, now=_ts("2026-09-19", 15), deploys=ledger)["submissions_secondary"]
    assert early["A"]["status"] == "final" and early["A"]["proven_clean_per_quota_day"] == 1.0
    assert early["B"]["status"] == "censored" and "proven_clean_per_quota_day" not in early["B"]
    late = B.compare(*args, now=_ts("2026-09-24", 15), deploys=ledger)["submissions_secondary"]
    assert late["A"]["proven_clean_per_quota_day"] == late["B"]["proven_clean_per_quota_day"] == 1.0
    assert late["A"]["note"].startswith("NOT the estimand")


def test_compare_without_stamped_rows_is_no_data():
    out = B.compare([_journal_row("a", "2026-09-10")], [], {}, {}, {}, {}, "A", "B", now=_ts("2026-09-20", 15))
    assert out["verdict"] == "no-data"


# -------------------------------------------------------------------------------- axis 3 is real
def test_the_fitness_functions_run_against_the_real_repository():
    ffs = B.fitness_functions()
    assert len(ffs) >= 6
    for name, ok, evidence in ffs:
        assert isinstance(ok, bool) and evidence, name


def test_a_deferred_import_cycle_is_a_smell_and_a_module_level_one_is_a_wall(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("def f():\n    from forge import b\n")      # deferred
    (pkg / "b.py").write_text("from forge import a\n")                    # module level
    cyc = B.import_cycles(pkg)
    assert cyc["module_level"] == [] and cyc["deferred"]                  # b->a is top-level but a->b is not
    (pkg / "a.py").write_text("from forge import b\n")
    assert B.import_cycles(pkg)["module_level"]


def test_import_cycles_come_from_the_syntax_tree_not_a_line_regex(tmp_path):
    """S4-NL: the regex missed relative imports, `import forge.x` and parenthesised multi-line imports
    (a real module-level cycle read 'none'), and read an import quoted in a docstring as an edge."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("from . import b\n")
    (pkg / "b.py").write_text("from forge import (\n    a,\n)\n")
    assert B.import_cycles(pkg)["module_level"] == ["a -> b"]
    (pkg / "b.py").write_text("import forge.a\n")
    assert B.import_cycles(pkg)["module_level"] == ["a -> b"]
    (pkg / "b.py").write_text('"""Usage:\n    from forge import a\n"""\n')
    assert B.import_cycles(pkg) == {"module_level": [], "deferred": []}
    (pkg / "b.py").write_text("x = lambda: __import__('os')\ndef g():\n    import forge.a\n")
    assert B.import_cycles(pkg) == {"module_level": [], "deferred": ["a -> b"]}


RUNNER_HEAD = "import argparse\nimport pathlib\n\n\ndef plan(ab='off'):\n    return 0\n\n\n"


def _fake_runner(tmp_path, body):
    (tmp_path / "forge").mkdir(parents=True)
    (tmp_path / "forge/runner.py").write_text(RUNNER_HEAD + body)
    return tmp_path


def test_the_ab_check_reads_the_runners_real_parser(tmp_path):
    """S4-NL: the check was the substring '--ab' in runner.py; a comment satisfied it. The runner's
    own parser must now carry --ab, parse each arm, and main() must hand it to plan(). Nothing after
    the parse may run: the fake main() below would write RAN if it got that far."""
    no_option = ("def main(argv=None):\n    # an --ab arm tags meta.arm (a comment, not an option)\n"
                 "    ap = argparse.ArgumentParser()\n    ap.add_argument('-n', type=int, default=3)\n"
                 "    a = ap.parse_args(argv)\n    pathlib.Path(__file__).with_name('RAN').write_text('x')\n"
                 "    return plan()\n")
    root = _fake_runner(tmp_path / "one", no_option)
    ok, why = B._ab_arm_is_real(root)
    assert ok is False and "no --ab" in why
    assert not (root / "forge/RAN").exists()
    not_handed = no_option.replace("default=3)\n", "default=3)\n    ap.add_argument('--ab', choices=('off', 'new'), default='off')\n")
    ok, why = B._ab_arm_is_real(_fake_runner(tmp_path / "two", not_handed))
    assert ok is False and "never hands" in why
    handed = not_handed.replace("return plan()", "return plan(ab=a.ab)")
    assert B._ab_arm_is_real(_fake_runner(tmp_path / "three", handed))[0] is True
    assert B._ab_arm_is_real(B.ROOT)[0] is True                        # the real runner


def test_an_empty_test_file_does_not_cover_its_module(tmp_path):
    """S4-NL: 'every forge module has a test' was a file-stem match, so an empty test_x.py counted."""
    (tmp_path / "forge/tests").mkdir(parents=True)
    for m in ("alpha", "beta", "gamma", "delta", "eps"):
        (tmp_path / "forge" / ("%s.py" % m)).write_text("X = 1\n")
    t = tmp_path / "forge/tests"
    (t / "test_alpha.py").write_text('"""nothing here yet"""\n')                                  # empty
    (t / "test_beta.py").write_text("from forge import beta as BT\n\n\ndef test_x():\n    assert BT.X\n")
    (t / "test_gamma.py").write_text("from forge import gamma\n\n\ndef helper():\n    return gamma.X\n")  # no test fn
    (t / "test_delta.py").write_text("class TestD:\n    def test_x(self):\n        from forge.delta import X\n        assert X\n")
    (t / "test_eps.py").write_text("from forge import eps\n\n\ndef test_other():\n    assert 1\n")     # never uses it
    mods, tested = B._modules_with_a_real_test(tmp_path)
    assert mods == ["alpha", "beta", "delta", "eps", "gamma"] and tested == ["beta", "delta"]


def test_axis3_floor_is_every_measured_check(monkeypatch):
    """S4-NL: at a floor of 0.80 a crashed drill read AXIS 3 FLOOR MET 6 of 7 on both draw-2 runs."""
    assert B.FLOOR["axis3_gearing"] == 1.0
    monkeypatch.setattr(B, "fitness_functions", lambda root=B.ROOT: [("c%d" % i, True, "ok") for i in range(6)])
    crashed = B.axis3_gearing(drill={"ok": False, "status": "crashed", "note": "x"})
    assert (crashed["held"], crashed["of"]) == (6, 7) and crashed["floor_met"] is False
    assert B.axis3_gearing(drill={"ok": True, "status": "carried", "note": "x"})["floor_met"] is True


def test_dora_is_reported_never_scored(monkeypatch):
    """A9: DORA inside axis 3 made the pre-merge gate depend on deploy history -- one rollback blocked
    every commit, and seven no-op 'deployed' rows lifted a failing tree over the floor.

    Draw-3 scoring MINOR: this test patched `_dora_from_ledger` with raising=False, a function that no
    longer exists, so the patch did nothing. It now patches B.dora -- the one reader of the ledger --
    with raising left on, and the card below shows the patched keys, so the patch is proven live while
    axis 3 stays untouched."""
    bad = {"status": "measured", "deploys": 4, "deploys_per_week": 0.1, "change_failure_rate": 0.9,
           "time_to_restore_hours_median": 99.0, "lead_time_hours_median": None}
    monkeypatch.setattr(B, "dora", lambda rows, now=None, window_days=28: bad)
    monkeypatch.setattr(B, "fitness_functions", lambda root=B.ROOT: [("c%d" % i, True, "ok") for i in range(6)])
    a = B.axis3_gearing(drill={"ok": True, "status": "carried", "note": "x"})
    assert not any(f["name"].startswith("DORA") for f in a["fitness_functions"])
    assert a["value"] == 1.0 and a["floor_met"] is True and "dora" not in a
    ledger = [_deploy("A", "2026-09-01"), _deploy("B", "2026-09-02", "rolled_back"), _deploy("B", "2026-09-04")]
    card = B.build_from([_journal_row("a", "2026-09-05")], {}, {}, [], {}, {}, now=_ts("2026-09-06", 15),
                        deploys=ledger, axis3=a)
    assert card["dora"]["keys"] is bad                                   # the patch reached the card
    assert card["dora"]["scored"] is False and not all(b["ok"] for b in card["dora"]["band"])
    assert card["axes"]["axis3_gearing"]["value"] == 1.0


def _quiet_disk(monkeypatch, curves=None):
    """build()'s other readers pinned to fixed, empty inputs: only the fixture journal is read from disk."""
    from forge import harvest as HV, probe as P, submit as SUB
    monkeypatch.setattr(SUB, "posted_history", lambda *a, **k: [])
    monkeypatch.setattr(HV, "load_scored", lambda *a, **k: {})
    monkeypatch.setattr(P, "load_corr", lambda *a, **k: {})
    monkeypatch.setattr(B, "load_deploys", lambda root=B.ROOT: None)
    monkeypatch.setattr(B, "load_standard", lambda root=B.ROOT: {})
    monkeypatch.setattr(B, "load_meaning", lambda path=None: None)
    monkeypatch.setattr(B, "load_run_config_log", lambda path=None: None)
    monkeypatch.setattr(B, "axis3_gearing", lambda **k: {"value": 1.0, "floor_met": True, "fitness_functions": []})


def _journal_file(tmp_path, rows, cut):
    import json
    import os
    f = tmp_path / "forge.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    os.utime(f, (cut, cut))
    return f


def test_the_scorecard_names_its_own_gaps(tmp_path, monkeypatch):
    """Draw-3 scoring SERIOUS 5: this test graded the LIVE journal, so one stamped row (the VPS already
    held 740) turned it red at the next sync. It now grades a FIXTURE journal, both ways: unstamped rows
    must raise the gap, and one stamped row must clear it. SERIOUS 4 rides on the same call: build() must
    pass the journal copy's mtime into the card as data_through, and the host into its provenance."""
    import socket
    _quiet_disk(monkeypatch)
    cut = _ts("2026-09-22", 16)
    unstamped = _journal_file(tmp_path, [_journal_row("a", "2026-09-21"), _journal_row("b", "2026-09-22")], cut)
    card = B.build(journal=unstamped, since="2026-09-20", run_drill=False, now=NOW_0923)
    assert any("pipeline_version" in g and str(unstamped) in g for g in card["gaps"])
    assert "weak" in card["version_attribution"]
    assert card["window"]["data_through"] == cut and card["provenance"]["inputs"]["data_through"] == cut
    assert card["window"]["excluded_uncovered_day"] == "2026-09-22"          # cut 16:00 on 09-22: not whole
    assert card["window"]["until_exclusive"] == "2026-09-22" and card["window"]["quota_days"] == 2
    assert card["axes"]["axis2_throughput"]["scored_alphas"] == 1           # b, created on the cut day, is out
    assert card["provenance"]["host"] == socket.gethostname()
    stamped = _journal_file(tmp_path, [_journal_row("a", "2026-09-21", version="v1")], cut)
    one = B.build(journal=stamped, run_drill=False, now=NOW_0923)["gaps"]
    assert not any("pipeline_version" in g for g in one)
    assert any("Exactly one cohort (v1)" in g and "compare() needs two" in g for g in one)   # draw3_fix scoring 12
    # the curve gap is COUNTED on this host, not asserted: no accepted POST, no gap; one without a curve, named
    assert not any("PnL curve" in g for g in card["gaps"])
    from forge import submit as SUB
    monkeypatch.setattr(SUB, "posted_history", lambda *a, **k: [{"alpha": "a", "http": 201, "posted_at": cut}])
    (tmp_path / "curves").mkdir()
    gaps = B.build(journal=unstamped, curves_dir=tmp_path / "curves", run_drill=False, now=NOW_0923)["gaps"]
    assert any("1 of 1 accepted" in g and ": a" in g for g in gaps)


# ----------------------------------------------------------------------------- the branch drill
def test_the_branch_drill_grows_a_real_branch_without_touching_code():
    """D8: the fitness functions say a branch COULD be grown; the drill grows one on a copy of the
    library and requires the real planner to carry it with no forge/*.py changed."""
    from forge.offline import branch_drill as BD
    r = BD.drill()
    assert r["ok"] is True and r["status"] == "carried"
    assert r["constructions"] > 0 and r["other_constructions"] == 0
    assert r["code_unchanged"] is True


def test_the_branch_drill_never_deletes_a_plan_it_did_not_write(tmp_path):
    """MEASURED 2026-09-23: unlinking plans/<seed>.json blindly deleted a pre-existing plan when the
    seed collided (157 -> 156). An explicit seed that already has a plan is refused outright."""
    from forge.offline import branch_drill as BD
    from forge import runner as R
    existing = sorted(R.PLANS.glob("*.json"))[0]
    seed = int(existing.stem) if existing.stem.isdigit() else None
    if seed is None:
        pytest.skip("no numeric plan file to collide with")
    before = existing.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        BD.drill(seed=seed)
    assert existing.read_bytes() == before


def test_axis3_counts_the_drill_as_a_fitness_function():
    a = B.axis3_gearing(drill={"ok": False, "status": "not-carried", "note": "x"})
    names = [f["name"] for f in a["fitness_functions"]]
    assert "a real branch goes through the planner" in names
    assert a["held"] < a["of"]


# -------------------------------------------------------------------------------------- DORA
def test_dora_refuses_to_compute_from_one_point():
    assert B.dora([])["status"] == "insufficient"
    assert B.dora([{"outcome": "deployed", "started_at": 1, "finished_at": 2}])["status"] == "insufficient"


def test_dora_computes_the_four_keys_on_a_known_ledger():
    rows = [
        {"outcome": "deployed", "started_at": 0, "finished_at": 1 * H, "commit_time": 0, "git_dirty": False,
         "version": "v1"},
        {"outcome": "rolled_back", "started_at": 10 * H, "finished_at": 11 * H, "commit_time": 9 * H, "git_dirty": False,
         "version": "v2"},
        {"outcome": "deployed", "started_at": 13 * H, "finished_at": 14 * H, "commit_time": 12 * H, "git_dirty": False,
         "version": "v3"},
        {"outcome": "deployed", "started_at": 20 * H, "finished_at": 21 * H, "commit_time": 20 * H, "git_dirty": True,
         "version": "v4"},
    ]
    d = B.dora(rows, now=21 * H, window_days=28)
    assert d["status"] == "measured" and d["deploys"] == 4
    assert d["change_failure_rate"] == pytest.approx(0.25)
    assert d["time_to_restore_hours_median"] == pytest.approx(3.0)       # 11h fail -> 14h clean
    # lead time uses clean deploys only: 1h and 2h -> median 1.5h; the dirty one has no honest commit
    assert d["lead_time_hours_median"] == pytest.approx(1.5)
    assert d["deploys_per_week"] == pytest.approx(1.0)


# ================================================================ draw-3 build audit, scoring section
# Each test below names the finding of docs/evalharness/audits/draw3_build.md (scoring) it guards; the
# scenario letters (S3, S4, ...) are the adjudicator's, from adj_scoring/verify.py.

def _merge(*cohorts):
    rows, scored, corr, hist, curves = [], {}, {}, [], {}
    for r, s, c, h, cu in cohorts:
        rows += r
        scored.update(s)
        corr.update(c)
        hist += h
        curves.update(cu)
    return rows, scored, corr, hist, curves


# ----------------------------------------------------------------- SERIOUS 1: exposure is for the rate
def test_a_refutation_on_a_deploy_day_is_graded_with_the_ledger_as_without_it():
    """S3: a refuted submission created 12:00 on V's deploy day (the deploy finished 10:00) read refuted 0
    WITH the ledger and 1 without it -- supplying more data hid a refutation. Axis 1 and rank level 1 now
    grade every stamped row; the ledger narrows only the rate."""
    rows, scored, corr, hist, curves = _merge(_cohort([("P", "p1", "2026-09-10", 0.1)], "V"),
                                              _cohort([("R", "rdep", "2026-09-09", 0.1)], "V"))
    ledger = [_deploy("V", "2026-09-09", hour=10)]
    w = B.build_from(rows, scored, corr, hist, curves, STANDARD, version="V", now=NOW_0923, deploys=ledger)
    wo = B.build_from(rows, scored, corr, hist, curves, STANDARD, version="V", now=NOW_0923, deploys=None)
    for c in (w, wo):
        assert c["axes"]["axis1_product"]["status_counts"] == {"proven": 1, "refuted": 1}
        assert c["rank"]["refuted_or_unproven_submitted"] == 1 and "axis1_product" in c["floors_unmet"]
    t = w["axes"]["axis2_throughput"]
    assert w["window"]["quota_days"] == 13 and t["proven_clean_submissions"] == 1     # live 09-10..09-22
    assert t["proven_clean_per_quota_day"] == round(1 / 13, 3)
    assert w["window"]["exposure"]["rows_outside_exposure"] == 3                      # rdep and its 2 neighbours
    assert w["window"]["exposure"]["submissions_outside_exposure"] == 1
    assert w["window"]["effective"]["axis1_first_day"] == "2026-09-09"


def test_a_version_live_for_no_whole_day_has_no_rate_and_keeps_its_refutations():
    """S4: V deployed 09-20 and replaced 09-21 POSTed 2 refuted alphas and read 0 days, 0 refuted and a
    MEASURED rate 0.0 -- and outranked an exposure-unknown card. Now its refutations count, and zero live
    days is UNMEASURED (None), never 0.0."""
    rows, scored, corr, hist, curves = _cohort([("R", "q1", "2026-09-20", 0.1), ("R", "q2", "2026-09-20", 0.1)], "V")
    ledger = [_deploy("V", "2026-09-20", hour=10), _deploy("W", "2026-09-21", hour=9)]
    q = B.build_from(rows, scored, corr, hist, curves, STANDARD, version="V", now=NOW_1010, deploys=ledger)
    t = q["axes"]["axis2_throughput"]
    assert q["window"]["quota_days"] == 0 and q["window"]["exposure"]["known"] is True
    assert q["rank"]["refuted_or_unproven_submitted"] == 2
    assert t["proven_clean_per_quota_day"] is None and t["value"] is None and t["poisson_95_per_day"] is None
    assert t["exposure"] == "0 whole ET quota days: no rate" and t["floor_met"] is False
    unknown = _card([("P", "u1", "2026-09-20", 0.1)], NOW_1010, version="U", deploys=None)
    assert unknown["rank"]["refuted_or_unproven_submitted"] == 0 and unknown["rank"]["proven_clean_per_quota_day"] is None
    assert B.rank_cmp(q, unknown) == 1                                   # 2 refuted rank below 0
    # the first S4 input: the version's only row is on the unfinished day -- nothing graded, no rate
    z_rows = _cohort([("P", "z1", "2026-09-23", None)], "Z")
    z = B.build_from(*z_rows[:4], z_rows[4], STANDARD, version="Z", now=NOW_0923,
                     deploys=[_deploy("Z", "2026-09-23", hour=9)])
    zu = B.build_from(*z_rows[:4], z_rows[4], STANDARD, version="Z", now=NOW_0923, deploys=None)
    assert z["rank"]["proven_clean_per_quota_day"] is None
    assert B.rank_cmp(z, zu) == 0                                        # used to be -1 on a measured 0.0
    # a date window holding no whole day is unmeasured too
    empty = _card([("P", "p1", "2026-09-22", 0.1)], NOW_0923, since="2026-09-23")
    assert empty["window"]["quota_days"] == 0 and empty["rank"]["proven_clean_per_quota_day"] is None


# ------------------------------------------------------------------- SERIOUS 4: the data's own cut
def test_the_day_the_data_was_cut_on_is_excluded_like_the_unfinished_day():
    """SERIOUS 4: the Mac's journal ended 2026-09-22T16:04 ET and was graded as if 09-22 were a whole day.
    A day the data does not cover to its end is now excluded from axis 1, from every rate and from the
    next-window judgement, and the card prints the requested window beside the effective one."""
    specs = [("P", "a", "2026-09-20", 0.1), ("P", "b", "2026-09-21", 0.1), ("R", "c", "2026-09-22", 0.1)]
    full = _card(specs, NOW_0923, since="2026-09-20")
    assert full["window"]["quota_days"] == 3 and full["rank"]["refuted_or_unproven_submitted"] == 1
    assert full["window"]["data_through"] is None and "not stated" in full["window"]["coverage_note"]
    cut = _ts("2026-09-22", 16) + 4 * 60
    part = _card(specs, NOW_0923, since="2026-09-20", data_through=cut)
    w = part["window"]
    assert w["quota_days"] == 2 and w["until_exclusive"] == "2026-09-22" and w["excluded_uncovered_day"] == "2026-09-22"
    assert w["requested"] == {"since": "2026-09-20", "until_exclusive": None}
    assert w["effective"]["until_exclusive"] == "2026-09-22" and w["effective"]["axis1_last_day"] == "2026-09-21"
    assert w["data_through_et"].startswith("2026-09-22T16:04")
    assert part["rank"]["refuted_or_unproven_submitted"] == 0
    assert part["axes"]["axis2_throughput"]["proven_clean_per_quota_day"] == 1.0
    # a cut at exactly 00:00 ET of 09-22 means 09-21 is whole; a cut after `now` changes nothing
    assert _card(specs, NOW_0923, since="2026-09-20", data_through=_ts("2026-09-22", 0))["window"]["quota_days"] == 2
    later = _card(specs, NOW_0923, since="2026-09-20", data_through=NOW_0923 + 3600)
    assert later["window"]["quota_days"] == 3 and later["window"]["excluded_uncovered_day"] is None


def test_a_next_window_the_data_does_not_cover_cannot_be_judged():
    """SERIOUS 4 on D7: a next window reaching the day the copy was cut on is not evaluable, not False."""
    win = dict(since="2026-09-10", until="2026-09-12")
    specs = [("P", "a", "2026-09-10", 0.1), ("R", "b", "2026-09-12", 0.1)]
    graded = _ts("2026-09-30", 15)
    assert _card(specs, graded, **win)["axes"]["axis2_throughput"]["sustainability_evidence"]["held_in_next_window"] is False
    cut = _card(specs, graded, data_through=_ts("2026-09-13", 12), **win)["axes"]["axis2_throughput"]
    assert cut["sustainability_evidence"]["held_in_next_window"] == "not evaluable"
    assert "not wholly covered" in cut["next_window"]


def test_compare_excludes_the_day_the_data_was_cut_on():
    """SERIOUS 4 on the estimand: every rate, compare()'s included."""
    rows = _arm("A", A_DAYS, 10, [1] * 5) + _arm("B", B_DAYS, 10, [1] * 5)
    out = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=_ts("2026-09-20", 15), data_through=_ts("2026-09-13", 9))
    assert sorted(out["versions"]["B"]["per_day"]) == ["2026-09-10", "2026-09-11", "2026-09-12"]
    assert out["excluded_uncovered_day"] == "2026-09-13" and out["data_through"] == _ts("2026-09-13", 9)


# ---------------------------------------------------------------------- SERIOUS 6: the cell mix
def _arm_in(version, days, n_per_day, k_by_day, region):
    rows = _arm(version, days, n_per_day, k_by_day)
    for r in rows:
        r["alpha"] = "%s_%s" % (region, r["alpha"])
        r["settings"] = {"region": region, "delay": 1}
    return rows


def test_compare_decides_within_cell_and_the_pooled_numbers_never_decide():
    """D28 (Khoa, 2026-09-23 ~15:30). The arms' mix is inverted: A scores 10/500 in USA/d1 and 0/100 in GLB/d1,
    B 10/100 and 0/500. POOLED both read 10/600 and the pooled test gives p = 1; WITHIN USA/d1, the one cell
    with an event, B's rate is five times A's. Before D28 the pooled label decided ("indistinguishable")
    while the text said there was no verdict yet (draw3_fix scoring 10: JSON and text disagreed). Now the
    within-cell test decides, the pooled numbers are printed beside it, and the text states the verdict the
    JSON carries."""
    now = _ts("2026-09-20", 15)
    rows = (_arm_in("A", A_DAYS, 100, [2] * 5, "USA") + _arm_in("A", A_DAYS, 20, [0] * 5, "GLB")
            + _arm_in("B", B_DAYS, 20, [2] * 5, "USA") + _arm_in("B", B_DAYS, 100, [0] * 5, "GLB"))
    out = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=now)
    assert out["versions"]["A"]["per_cell"] == {"GLB/d1": [0, 100], "USA/d1": [10, 500]}
    assert out["versions"]["B"]["per_cell"] == {"GLB/d1": [0, 500], "USA/d1": [10, 100]}
    assert out["cell_mix_differs"] is True and out["cell_mix"]["df"] == 1
    # the pooled test, by hand: 10/600 against 10/600 -- printed, never deciding
    assert out["pooled"]["p_value"] == round(B.rate_test_p(10, 600, 10, 600), 5) == 1.0
    assert out["pooled"]["rate_ratio_b_over_a"] == 1.0 and out["pooled"]["decides"] is False
    # within cell, by hand: K = 20 in USA/d1, k_B ~ Binomial(20, 100/600) under H0, k_B = 10
    upper = sum(math.comb(20, i) * (1 / 6) ** i * (5 / 6) ** (20 - i) for i in range(10, 21))
    assert out["p_value"] == round(2 * upper, 5) and out["p_value"] < 0.05
    assert out["rate_ratio_b_over_a"] == 5.0                   # Mantel-Haenszel: (10*500/600) / (10*100/600)
    assert out["cells"]["USA/d1"]["direction"] == "B higher" and out["cells"]["GLB/d1"]["direction"] == "no event"
    assert out["verdict"] == "better" and out["verdict_text"].startswith("better WITHIN CELL (D28)")
    assert "never deciding" in out["verdict_text"] and "DIFFERS" in out["verdict_text"]
    assert B.compare(rows, [], {}, {}, {}, {}, "B", "A", now=now)["verdict"] == "worse"
    # the same mix in both arms: no flag, and the within-cell and pooled tests are one test
    same = _arm_in("A", A_DAYS, 100, [2] * 5, "USA") + _arm_in("B", B_DAYS, 100, [8] * 5, "USA")
    s = B.compare(same, [], {}, {}, {}, {}, "A", "B", now=now)
    assert s["cell_mix_differs"] is False and "one cell" in s["cell_mix"]["note"]
    assert s["p_value"] == s["pooled"]["p_value"] and s["verdict"] == "better"


def test_the_cell_mix_statistic_is_the_textbook_two_by_two():
    """Second derivation (RULE 0 #5): for a 2 x 2 table the Pearson statistic is N(ad - bc)^2 / (row and
    column totals), and the chi-square(1) tail is erfc(sqrt(x / 2))."""
    a, b, c, d = 500, 100, 100, 500                  # arm A: 500 USA, 100 GLB; arm B: 100 USA, 500 GLB
    n = a + b + c + d
    by_hand = n * (a * d - b * c) ** 2 / ((a + b) * (c + d) * (a + c) * (b + d))
    cm = B.cell_mix({"USA/d1": [0, a], "GLB/d1": [0, b]}, {"USA/d1": [0, c], "GLB/d1": [0, d]})
    assert cm["statistic"] == pytest.approx(by_hand, rel=1e-9)
    assert cm["p_value"] == pytest.approx(math.erfc(math.sqrt(by_hand / 2)), rel=1e-6, abs=1e-300)
    near = B.cell_mix({"USA/d1": [0, 500], "GLB/d1": [0, 100]}, {"USA/d1": [0, 505], "GLB/d1": [0, 98]})
    assert near["differs"] is False and near["p_value"] > 0.5


def test_the_chi_square_tail_matches_its_closed_forms():
    """chi2_sf against closed forms: df 1 erfc(sqrt(x/2)), df 2 exp(-x/2), df 4 exp(-x/2)(1 + x/2); and the
    95 % point of chi-square(1) is 3.841."""
    for x in (0.1, 1.0, 3.841458820694124, 10.0, 40.0):
        assert B.chi2_sf(x, 1) == pytest.approx(math.erfc(math.sqrt(x / 2)), rel=1e-9)
        assert B.chi2_sf(x, 2) == pytest.approx(math.exp(-x / 2), rel=1e-9)
        assert B.chi2_sf(x, 4) == pytest.approx(math.exp(-x / 2) * (1 + x / 2), rel=1e-9)
    assert B.chi2_sf(3.841458820694124, 1) == pytest.approx(0.05, abs=1e-9)


# ------------------------------------------------------------------------------------- the MINORs
def test_dora_skips_noop_rows():
    """S6: with 1 rollback and 7 noop rows the reader said CFR 0.111 and 2.25 deploys a week, both band
    checks ok. tools/deploy.py: "A NOOP IS NOT A DEPLOY, and every reader computing DORA must skip it"."""
    base = _ts("2026-09-10", 10)
    ledger = ([{"outcome": "deployed", "started_at": base, "finished_at": base + H, "version": "v1"},
               {"outcome": "rolled_back", "started_at": base + 2 * H, "finished_at": base + 3 * H, "version": "v2"}]
              + [{"outcome": "noop", "started_at": base + (4 + i) * H, "finished_at": base + (4.5 + i) * H,
                  "version": "v1"} for i in range(7)])
    d = B.dora(ledger, now=base + 20 * H)
    assert d["deploys"] == 2 and d["change_failure_rate"] == 0.5 and d["deploys_per_week"] == 0.5
    assert [ok for _, ok, _ in B.dora_checks(d)] == [False, False]
    assert B.dora(ledger[:1] + ledger[2:], now=base + 20 * H)["status"] == "insufficient"


def test_dora_counts_a_restore_only_when_the_version_changes():
    """Round 2 A9, "count a restore only when the version changes": v2 is rolled back (v1 runs again);
    re-shipping v1 an hour later restores nothing; the restore is v3, 10 h after the failure."""
    ledger = [{"outcome": "deployed", "started_at": 0, "finished_at": 1 * H, "version": "v1"},
              {"outcome": "rolled_back", "started_at": 5 * H, "finished_at": 6 * H, "version": "v2"},
              {"outcome": "deployed", "started_at": 6.5 * H, "finished_at": 7 * H, "version": "v1"},
              {"outcome": "deployed", "started_at": 15 * H, "finished_at": 16 * H, "version": "v3"}]
    assert B.dora(ledger, now=16 * H)["time_to_restore_hours_median"] == pytest.approx(10.0)
    no_change = ledger[:3]
    assert B.dora(no_change, now=16 * H)["time_to_restore_hours_median"] is None
    # after a failed rollback the running version is unknown, so the next versioned deploy restores it
    lost = [dict(ledger[0]), dict(ledger[1], outcome="rollback_failed"), dict(ledger[2])]
    assert B.dora(lost, now=16 * H)["time_to_restore_hours_median"] == pytest.approx(1.0)


def test_load_standard_fails_loudly_with_the_path(tmp_path):
    """Round 2 A5 / draw-3 scoring MINOR: load_standard returned {} on ANY exception, which after A5 set
    every submitted alpha's standard gate to UNMEASURED and every proven count to 0, silently."""
    import shutil
    (tmp_path / "forge").mkdir()
    shutil.copytree(B.ROOT / "forge/hypotheses", tmp_path / "forge/hypotheses", ignore=shutil.ignore_patterns("staged"))
    (tmp_path / "forge/composites").mkdir()
    (tmp_path / "forge/composites/broken.yaml").write_text("id: broken\nlegs: [no_such_leg, nor_this]\n")
    with pytest.raises(RuntimeError) as err:
        B.load_standard(tmp_path)
    assert str(tmp_path / "forge/composites") in str(err.value) and "broken.yaml" in str(err.value)
    from forge import hypotheses as HY
    real = B.load_standard()
    ids = {c.id for c in HY.load_composites(B.ROOT / "forge/composites", HY.load_library(B.ROOT / "forge/hypotheses"))}
    assert real and set(real) == ids and all(isinstance(v, list) for v in real.values())


def test_the_submission_reading_can_say_exposure_unknown_and_names_the_newest_graded_day():
    """S8: without a ledger the reading was 'censored' for ever, its final date moving forward each day,
    and the 'exposure unknown' branch could not be reached. S9: the censored note printed until_exclusive
    (09-19) as the newest day; the newest graded day is 09-08, final 2026-09-23."""
    a = _cohort([("P", "a%d" % i, d, 12) for i, d in enumerate(("2026-09-02", "2026-09-03", "2026-09-04"))], "A")
    b = _cohort([("P", "b%d" % i, d, 12) for i, d in enumerate(("2026-09-06", "2026-09-07", "2026-09-08"))], "B")
    rows, scored, corr, hist, curves = _merge(a, b)
    args = (rows, hist, curves, STANDARD, scored, corr, "B")
    early = B._submission_reading(*args, _ts("2026-09-19", 15), None)
    late = B._submission_reading(*args, _ts("2026-10-30", 15), None)
    assert early["status"] == late["status"] == "exposure unknown"
    assert early["post_horizon_final"] is False and late["post_horizon_final"] is True
    assert early["final_after_et"] == late["final_after_et"] == "2026-09-23T00:00-04:00"   # does not drift
    ledger = [_deploy("A", "2026-09-01"), _deploy("B", "2026-09-05"), _deploy("C", "2026-09-09")]
    cen = B._submission_reading(*args, _ts("2026-09-19", 15), ledger)
    assert cen["status"] == "censored" and "newest graded day 2026-09-08" in cen["note"]
    assert cen["final_after_et"] == "2026-09-23T00:00-04:00"


def test_the_neighbour_pool_holds_nothing_created_after_the_grading_clock():
    """Draw-3 scoring MINOR (pool.py): two rows created 09-25 flipped an alpha from unproven to refuted on
    a card graded 09-20. A card sees only rows created by its own `now`."""
    rows, scored, corr, hist, curves = _cohort([("U", "x", "2026-09-10", 0.1)], "V")
    later = [dict(rows[0], alpha="x_n%d" % i, sharpe=0.1, dateCreated="2026-09-25T12:00:00-04:00",
                  settings=_settings(decay=8) if i == 0 else _settings(neut="SUBINDUSTRY")) for i in range(2)]
    ledger = [_deploy("V", "2026-09-09")]

    def status(now):
        c = B.build_from(rows + later, scored, corr, hist, curves, STANDARD, version="V", now=now, deploys=ledger)
        return c["axes"]["axis1_product"]["detail"][0]["status"]
    assert status(_ts("2026-09-20", 15)) == "unproven"
    assert status(_ts("2026-09-26", 15)) == "refuted"                   # once they exist, they count


def test_two_mechanisms_imply_an_interval_above_zero():
    """S11: the S9-NL conjunct interval_excludes_zero follows from two_or_more_mechanisms (k >= 2 gives a
    positive exact lower bound for any exposure); D7 as ticked keeps both, and the docstring says so
    rather than calling the pieces independent."""
    assert all(B.poisson_interval(k, days)[0] > 0 for k in range(1, 40) for days in range(1, 60))
    doc = " ".join(B.axis2_throughput.__doc__.split())
    assert "The pieces are NOT independent" in doc and "D7 as ticked names all three" in doc


def _decimal_cdf(k, lam):
    """P(Poisson(lam) <= k) summed exactly in 60-digit decimal: a derivation independent of the module."""
    from decimal import Decimal, localcontext
    with localcontext() as ctx:
        ctx.prec = 60
        L = Decimal(repr(lam))
        term = (-L).exp()
        total = term
        for i in range(1, k + 1):
            term = term * L / i
            total += term
        return float(total)


def _wilson_hilferty(k, upper, z=1.959963984540054):
    """Garwood bound from the Wilson-Hilferty cube-root approximation to the chi-square quantile."""
    if upper:
        m = k + 1
        return m * (1 - 1 / (9 * m) + z / (3 * math.sqrt(m))) ** 3
    return k * (1 - 1 / (9 * k) - z / (3 * math.sqrt(k))) ** 3


@pytest.mark.parametrize("k", [800, 1500])
def test_the_poisson_interval_is_exact_past_the_old_underflow(k):
    """S10: exp(-lam) underflowed past lam ~745, so k = 800 read [742.7, 745.1] and k = 1500 read
    [745.1, 745.1]. Three derivations now agree: the defining tail equations re-evaluated in exact
    decimal arithmetic, the Wilson-Hilferty approximation, and scipy when it is installed."""
    lo, hi = B.poisson_interval(k, 1)
    assert lo < k < hi
    assert _decimal_cdf(k, hi) == pytest.approx(0.025, abs=1e-7)                 # P(X <= k | hi) = 2.5 %
    assert 1 - _decimal_cdf(k - 1, lo) == pytest.approx(0.025, abs=1e-7)         # P(X >= k | lo) = 2.5 %
    assert hi == pytest.approx(_wilson_hilferty(k, True), rel=2e-4)
    assert lo == pytest.approx(_wilson_hilferty(k, False), rel=2e-4)
    lo7, hi7 = B.poisson_interval(k, 7)
    assert (lo7, hi7) == pytest.approx((lo / 7, hi / 7), rel=1e-12)
    try:
        from scipy.stats import chi2
    except ImportError:
        return
    assert hi == pytest.approx(chi2.ppf(0.975, 2 * k + 2) / 2, rel=1e-7)
    assert lo == pytest.approx(chi2.ppf(0.025, 2 * k) / 2, rel=1e-7)


def test_the_poisson_interval_holds_to_k_of_one_hundred_thousand():
    """The log-space sum stays correct at the top of the range the task names (k up to 100,000)."""
    lo, hi = B.poisson_interval(100000, 1)
    assert hi == pytest.approx(_wilson_hilferty(100000, True), rel=1e-6)
    assert lo == pytest.approx(_wilson_hilferty(100000, False), rel=1e-6)


def test_the_poisson_cdf_agrees_with_the_incomplete_gamma_function():
    """Second derivation of _poisson_cdf: P(Poisson(lam) <= k) = Q(k + 1, lam), computed by an unrelated
    series / continued fraction (_gamma_q)."""
    for k, lam in ((0, 0.5), (3, 2.0), (10, 25.0), (40, 30.0), (799, 800.0), (1500, 1400.0), (1500, 1600.0)):
        assert B._poisson_cdf(k, lam) == pytest.approx(B._gamma_q(k + 1, lam), rel=1e-9, abs=1e-300)


def test_the_comments_say_what_was_measured_and_nothing_more():
    """Draw-3 scoring MINORs that live in prose, checked on the source so a revert shows:
      * compare(): dispersion cannot tell day-level heterogeneity from within-day clustering, so the
        sentence naming non-independence across days as the finding is gone (MECHANISM: UNKNOWN);
      * REGIME_SE_MULTIPLE's 2.0 is this module's EX-ANTE convention, not round 2's;
      * ESTIMAND's comment names the journal copy and its cut, and reconciles 37 with D24's 34;
      * live_days no longer says exposure stays unknown "until deploy.py writes it" (ec6a5cd75d58fea2 never
        will be written)."""
    src = open(B.__file__).read()
    assert "per-alpha outcome is NOT independent across days" not in B.compare.__doc__
    assert "MECHANISM: UNKNOWN" in B.compare.__doc__
    assert "as the round-2\n#: fix states it" not in src and "THIS MODULE'S OWN EX-ANTE CONVENTION" in src
    assert "mtime 2026-09-22T16:05:13-04:00" in src and "COMPLETE only 34" in src
    assert "vRk095rv" in src and "qMWbdlmv" in src and "ZY0Zowe1" in src
    assert "until deploy.py writes it." not in B.live_days.__doc__ and "ec6a5cd75d58fea2" in B.live_days.__doc__
    assert 'said "not measuring is never rewarded (A5)"; that was false then' in " ".join(B.rank_key.__doc__.split())


def test_the_estimands_binding_checks_are_frozen_inside_it(monkeypatch):
    """Draw-3 scoring MINOR: the numerator read the module's mutable BINDING. The list is now a literal in
    ESTIMAND, and an edit to BINDING (axis 1's gate) does not move the estimand."""
    assert B.ESTIMAND["binding_checks"] == ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE",
                                            "CONCENTRATED_WEIGHT", "HIGH_TURNOVER", "LOW_TURNOVER")
    rows = _arm("A", A_DAYS, 10, [1] * 5) + _arm("B", B_DAYS, 10, [1] * 5)
    now = _ts("2026-09-20", 15)
    before = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=now)["versions"]["A"]["clearing_every_binding_check"]
    monkeypatch.setattr(B, "BINDING", B.BINDING + ("SOME_NEW_CHECK",))
    after = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=now)["versions"]["A"]["clearing_every_binding_check"]
    assert before == after == 5
    # draw3_fix scoring 3 (EST): the default now reads BINDING at call time. Under `names=BINDING`, bound when
    # the def ran, this read True -- and the line it replaces passed B.BINDING explicitly, a tautology.
    assert B.clears_every_binding_check(rows[0]) is False


def test_import_forge_x_credits_x_only(tmp_path):
    """S12: `import forge.x` binds `forge`, so a test that read only forge.y.X credited x too."""
    (tmp_path / "forge/tests").mkdir(parents=True)
    for m in ("alpha", "beta", "gamma", "delta"):
        (tmp_path / "forge" / ("%s.py" % m)).write_text("X = 1\n")
    t = tmp_path / "forge/tests"
    (t / "test_alpha.py").write_text("import forge.alpha\nimport forge.beta\n\n\ndef test_b():\n    assert forge.beta.X\n")
    (t / "test_beta.py").write_text("import forge.alpha\nimport forge.beta\n\n\ndef test_b():\n    assert forge.beta.X\n")
    (t / "test_gamma.py").write_text("def test_g():\n    import forge.gamma, forge.beta\n    assert forge.beta.X\n")
    (t / "test_delta.py").write_text("import forge.delta as FD\n\n\ndef test_d():\n    assert FD.X\n")
    assert B._modules_with_a_real_test(tmp_path) == (["alpha", "beta", "delta", "gamma"], ["beta", "delta"])


def test_a_test_that_only_names_its_module_does_not_cover_it(tmp_path):
    """Round 4 m7 (g8tree/): test bodies that evaluate a name bound to the module and throw it away -- `eps`, `zeta.f`
    -- counted the module as tested. Now a use is a CALL of, or an ASSERTION over, something bound from it; a bare
    bind (`x = zeta.X`) is not one either. A call, an assert, and a module value passed to a call are."""
    (tmp_path / "forge/tests").mkdir(parents=True)
    bodies = {"a1": "zeta_e", "a2": "zeta.f", "a3": "x = zeta.X", "b1": "zeta.f()", "b2": "assert zeta.X == 1",
              "b3": "sorted(zeta.X)", "b4": "assert zeta_e"}
    for m, body in bodies.items():
        (tmp_path / "forge" / ("%s.py" % m)).write_text("X = 1\n")
        (tmp_path / "forge/tests" / ("test_%s.py" % m)).write_text(
            "from forge import %s as zeta\nfrom forge.%s import X as zeta_e\n\n\ndef test_x():\n    %s\n" % (m, m, body))
    mods, tested = B._modules_with_a_real_test(tmp_path)
    assert mods == sorted(bodies) and tested == ["b1", "b2", "b3", "b4"], tested


def test_a_type_checking_import_is_not_a_module_level_edge(tmp_path):
    """S13: a module-level `if TYPE_CHECKING:` import never runs, and was read as a WALL. Its else branch
    does run at import time and stays module-level. The dead ast.Lambda branch is gone from the walker."""
    import ast
    import inspect
    import textwrap
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from forge import b\n")
    (pkg / "b.py").write_text("from forge import a\n")
    assert B.import_cycles(pkg) == {"module_level": [], "deferred": ["a -> b"]}
    (pkg / "a.py").write_text("import typing\nif typing.TYPE_CHECKING:\n    pass\nelse:\n    from forge import b\n")
    assert B.import_cycles(pkg)["module_level"] == ["a -> b"]
    code = ast.parse(textwrap.dedent(inspect.getsource(B._import_edges)))
    assert not any(isinstance(n, ast.Attribute) and n.attr == "Lambda" for n in ast.walk(code))


def _runner_at(tmp_path, name, text):
    root = tmp_path / name
    (root / "forge").mkdir(parents=True)
    (root / "forge/runner.py").write_text(text)
    return root


PARSE = ("def main(argv=None):\n    ap = argparse.ArgumentParser()\n"
         "    ap.add_argument('--ab', choices=('off', 'new'), default='off')\n    a = ap.parse_args(argv)\n")


def test_the_ab_check_reads_the_syntax_tree_and_runs_nothing(tmp_path):
    """Draw-3 scoring MINOR (S14, dc.py): the check EXECUTED runner.main() up to its parse. `plan(ab=a.ab)`
    under `if False:` passed; code before the parse ran (a file was written); a runner with a @dataclass
    and `from __future__ import annotations` read "does not import" (at a floor of 1.0 that fails axis
    3); and each call added two entries to sys.path. It is now a pure reading of the syntax tree."""
    import sys
    dead = RUNNER_HEAD + PARSE + "    if False:\n        plan(ab=a.ab)\n    return plan()\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "dead", dead))[0] is False
    notnot = RUNNER_HEAD + PARSE + "    while not True:\n        plan(ab=a.ab)\n    return plan()\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "notnot", notnot))[0] is False
    after = RUNNER_HEAD + PARSE + "    return plan()\n    plan(ab=a.ab)\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "after", after))[0] is False
    nested = RUNNER_HEAD + PARSE + "    def later():\n        return plan(ab=a.ab)\n    return plan()\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "nested", nested))[0] is False
    side = ("import argparse\nimport pathlib\npathlib.Path(__file__).with_name('AT_IMPORT').write_text('x')\n\n"
            "def plan(ab='off'):\n    return 0\n\n\ndef main(argv=None):\n"
            "    pathlib.Path(__file__).with_name('PRE').write_text('x')\n"
            + PARSE.split("\n", 1)[1] + "    return plan(ab=a.ab)\n")
    root = _runner_at(tmp_path, "side", side)
    before = list(sys.path)
    assert B._ab_arm_is_real(root)[0] is True
    assert not (root / "forge/PRE").exists() and not (root / "forge/AT_IMPORT").exists()
    assert sys.path == before
    dc = ("from __future__ import annotations\nimport argparse\nimport dataclasses\n\n\n@dataclasses.dataclass\n"
          "class K:\n    x: int = 0\n\n\ndef plan(ab='off'):\n    return 0\n\n\n" + PARSE + "    return plan(ab=a.ab)\n")
    assert B._ab_arm_is_real(_runner_at(tmp_path, "dc", dc)) == (
        True, "runner.main()'s parser offers --ab new and main() hands it to plan(ab=...) in reachable code")
    other = RUNNER_HEAD + PARSE + "    b = ap.parse_args([])\n    return plan(ab=b.mode)\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "other", other))[0] is False
    not_parsed = RUNNER_HEAD + PARSE + "    cfg = argparse.Namespace(ab='off')\n    return plan(ab=cfg.ab)\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "not_parsed", not_parsed))[0] is False   # .ab of no parse
    assert B._ab_arm_is_real(B.ROOT)[0] is True                          # the real runner, never imported
    assert "_wq_fitness_runner" not in sys.modules


def test_axis1s_thresholds_are_named_and_the_gates_read_them(monkeypatch):
    """Draw-3 scoring MINOR: DSR >= 0.95, neighbour retention >= 0.5, >= 2 neighbours, >= 300 curve points and
    the strict '<' on correlation lived inline. Each is now a named constant, and moving it moves the gate."""
    assert (B.DSR_MIN, B.NEIGHBOUR_RETENTION_MIN, B.NEIGHBOURS_MIN, B.CURVE_POINTS_MIN) == (0.95, 0.5, 2, 300)
    assert B.CORR_UNDER_LINE(0.7, 0.7) is False and B.CORR_UNDER_LINE(0.6999, 0.7) is True

    def gates(**over):
        for k, v in over.items():
            monkeypatch.setattr(B, k, v)
        c = _card([("P", "p1", "2026-09-10", 0.1)], _ts("2026-09-20", 15), since="2026-09-10", until="2026-09-11")
        return c["axes"]["axis1_product"]["detail"][0]["gates"]
    base = gates()
    assert all(v is True for v in base.values())
    assert gates(DSR_MIN=0.99)["dsr_ge_095"] is False                     # the alpha's DSR is 0.97
    assert gates(NEIGHBOUR_RETENTION_MIN=0.95)["neighbourhood_stable"] is False    # median 1.65 of 1.8
    assert gates(NEIGHBOURS_MIN=3)["neighbourhood_stable"] is None
    assert gates(CURVE_POINTS_MIN=500)["regime_stable"] is None            # the curve has 420 points
    assert gates(CORR_UNDER_LINE=lambda a, b: False)["corr_under_lines"] is False


def test_the_one_day_caveat_is_computed_not_typed():
    """Draw-3 scoring MINOR: '61 %' was typed into the caveat. It is exp(-rate) at the agreements' reference
    rate of 0.5 per day, and at the card's own rate when there is one."""
    rows = [{"alpha": str(i), "checks": [], "formula": None, "meta": {}, "settings": {}} for i in range(10)]
    t = B.axis2_throughput(rows, [{"alpha": "1", "mechanism_key": "a"}], 2, {"1"}, statuses={"1": "proven"})
    assert "= %.0f %%" % (100 * math.exp(-0.5)) in t["caveat"] and "61 %" in t["caveat"]
    assert "own rate of 0.500 per day, %.0f %%" % (100 * math.exp(-0.5)) in t["caveat"]
    assert "own rate" not in B.axis2_throughput(rows, [], 2, set())["caveat"]


# ------------------------------------------------------ the adjudicator's 7 surviving mutants, killed
def test_the_exact_test_with_unequal_arms_is_pinned_by_hand():
    """Mutant 'pi0 swapped in rate_test_p' survived: every test used equal arms. K = 12, pi0 = 5000/6000:
    k_b = 10 sits in the middle of Binomial(12, 5/6), so p = 1.0; k_b = 12 has upper tail (5/6)^12."""
    assert B.rate_test_p(2, 1000, 10, 5000) == 1.0
    assert B.rate_test_p(0, 1000, 12, 5000) == pytest.approx(2 * (5 / 6) ** 12, rel=1e-12)
    assert B.rate_test_p(12, 1000, 0, 5000) == pytest.approx(2 * (1 / 6) ** 12, rel=1e-9)


def test_the_power_at_no_change_is_the_size_with_unequal_arms():
    """Mutant 'pi0 swapped in _power' survived. At a ratio of 1 the exact power is the test's size, which
    an exact test holds at or below alpha whatever the exposures."""
    base = 20 / 6000
    assert B._power(1000, 5000, base, 1.0, 0.05, {}) <= 0.05
    assert B._power(5000, 1000, base, 1.0, 0.05, {}) <= 0.05


def test_an_unproven_submission_in_the_next_window_is_not_the_rate_holding():
    """Mutant 'the next window counts not-refuted' survived: only a refuted next-window POST was tested."""
    win = dict(since="2026-09-10", until="2026-09-12")
    c = _card([("P", "a", "2026-09-10", 0.1), ("U", "b", "2026-09-12", 0.1)], _ts("2026-09-30", 15), **win)
    assert c["axes"]["axis2_throughput"]["sustainability_evidence"]["held_in_next_window"] is False


def test_live_days_never_include_the_unfinished_day():
    """Mutant 'live_days includes today' survived: the ledger test's today was not a live day."""
    now = _ts("2026-09-05", 12)
    assert B.live_days([_deploy("A", "2026-09-01")], "A", now)["days"] == ["2026-09-02", "2026-09-03", "2026-09-04"]


def test_an_unmeasured_level_one_or_three_ranks_below_every_measured_value():
    """Mutants 'None as 0 at level 1' and 'None as 0 at level 3' survived: no test put None against 0."""
    assert B.rank_cmp(_levels(None, 0.2, 1.0), _levels(0, 0.2, 1.0)) == 1
    assert B.rank_cmp(_levels(None, 9.0, 1.0), _levels(3, 0.1, 0.5)) == 1
    assert B.rank_cmp(_levels(0, 0.2, None), _levels(0, 0.2, 0.0)) == 1


# ------------------------------------------------------------------ A2: --compare, --record, host
def test_main_compare_prints_a_comparison_graded_at_the_wall_clock(monkeypatch, capsys):
    """A2: main() gains --compare VERSION_A VERSION_B, which prints compare() with `now` passed in."""
    import time
    rows = _arm("A", A_DAYS, 100, [1] * 5) + _arm("B", B_DAYS, 100, [3] * 5)
    monkeypatch.setattr(B, "load_inputs", lambda *a, **k: {
        "rows": rows, "history": [], "curves": {}, "standard": {}, "scored": {}, "corr": {}, "deploys": None,
        "data_through": _ts("2026-09-20", 9), "run_config_log": ["the log"]})
    seen = {}
    real = B.compare

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)
    monkeypatch.setattr(B, "compare", spy)
    t0 = time.time()
    assert B.main(["--compare", "A", "B"]) == 0
    assert t0 <= seen["now"] <= time.time() and seen["data_through"] == _ts("2026-09-20", 9)
    assert seen["run_config_log"] == ["the log"]                                      # D45
    text = capsys.readouterr().out
    assert "VERDICT" in text and "better" in text and "USA/d1" in text
    with pytest.raises(SystemExit):
        B.main(["--compare", "A", "B", "--record"])


def test_record_appends_once_per_cohort_day_and_host_and_never_rewrites(tmp_path, monkeypatch, capsys):
    """A2 / S10-NL ("no card ledger exists"): --record appends the card, provenance and host included, as
    ONE JSON line to state/benchmark/cards.jsonl; an earlier line is never rewritten. D41 (Khoa, 2026-09-23):
    a second --record of the same cohort on the same graded ET day from the same host appends NOTHING and
    says so; another host, another day or another cohort appends."""
    import json
    # the drawing's finding 8: a recorded card names its cohort, so these are version cards (moved from date cards)
    rows, scored, corr, hist, curves = _merge(_cohort([("P", "p1", "2026-09-10", 0.1)], "V"),
                                              _cohort([("P", "w1", "2026-09-10", 0.1)], "W"))
    card = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 15), host="judge-host",
                        version="V")
    assert card["provenance"]["host"] == "judge-host"
    ledger = tmp_path / "state/benchmark/cards.jsonl"
    monkeypatch.setattr(B, "CARDS_LEDGER", ledger)
    monkeypatch.setattr(B, "build", lambda **k: card)
    B.main(["--record", "--no-drill", "--version", "V"])
    first = ledger.read_bytes()
    assert "recorded in" in capsys.readouterr().err
    B.main(["--record", "--no-drill", "--version", "V"])
    assert ledger.read_bytes() == first                                  # D41: nothing appended
    assert "NOT recorded" in capsys.readouterr().err
    back = json.loads(first)
    assert back["provenance"]["host"] == "judge-host" and back["provenance"]["scorer_sha256"] == B.scorer_sha256()
    for other in (B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 15), host="mac",
                               version="V"),
                  B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-21", 1), host="judge-host",
                               version="V"),
                  B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 16), host="judge-host",
                               version="W")):
        assert B.record_card(other, ledger) == (ledger, True)
    # the same cohort, day and host graded an hour later: still the same record
    again = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 23), host="judge-host",
                         version="V")
    assert B.record_card(again, ledger) == (ledger, False)
    lines = ledger.read_bytes().splitlines(keepends=True)
    assert len(lines) == 4 and lines[0] == first
    with pytest.raises(ValueError, match="no provenance"):
        B.record_card({"verdict": "FAIL"}, ledger)


def test_a_version_cards_record_key_is_its_cohort(tmp_path):
    """D41 keys a version card by its D30 cohort: two cohorts of one pipeline_version are two records."""
    rows = [dict(_journal_row("a", "2026-09-10", version="V"), meta={"pipeline_version": "V", "run_config": "r1"}),
            dict(_journal_row("b", "2026-09-10", version="V"), meta={"pipeline_version": "V", "run_config": "r2"})]
    now, ledger = _ts("2026-09-20", 15), tmp_path / "cards.jsonl"
    c1, c2 = (B.build_from(rows, {}, {}, [], {}, {}, now=now, version=v, host="h") for v in ("V@r1", "V@r2"))
    assert B.record_key(c1)["cohort"] == {"pipeline_version": "V", "run_config": "r1"}
    assert [B.record_card(c, ledger)[1] for c in (c1, c2, c1)] == [True, True, False]


def test_a_recorded_line_is_strict_json_on_a_line_of_its_own(tmp_path):
    """Draw3_fix scoring 7 (V5): a steady curve's regime thirds hold float('inf'), and the ledger line held the
    token Infinity, which a strict parser rejects. And an earlier append cut short (no trailing newline)
    must not swallow the next line."""
    import json

    def strict(s):
        return json.loads(s, parse_constant=lambda c: (_ for _ in ()).throw(ValueError("non-JSON constant " + c)))
    rows, scored, corr, hist, curves = _cohort([("P", "p1", "2026-09-10", 0.1)], "V")    # finding 8: a version card
    card = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 15), host="h", version="V")
    assert card["axes"]["axis1_product"]["detail"][0]["regime"]["thirds"][0] == float("inf")
    ledger = tmp_path / "cards.jsonl"
    ledger.write_bytes(b'{"cut": "short"')                              # a previous append, cut short
    assert B.record_card(card, ledger) == (ledger, True)
    lines = ledger.read_bytes().split(b"\n")
    assert lines[0] == b'{"cut": "short"' and lines[-1] == b""
    back = strict(lines[1])
    assert back["axes"]["axis1_product"]["detail"][0]["regime"]["thirds"][0] == "inf"


# ----------------------------------------------------------------- the TICK items, printed not changed
def test_every_card_prints_the_facts_khoa_needs_for_the_open_ticks():
    """TICK items (RULE 2): printed with the card's own numbers, never changing a verdict. Draw3_fix scoring 9:
    D26-D29 are ticked and implemented, so their items are gone -- among them the false "measuring them could
    only move it down" (an alpha measured as PROVEN raises level 2) -- and D7's open "held" definition, which
    the list omitted, is on it."""
    c = _card([("P", "p1", "2026-09-21", 0.1), ("U", "u1", "2026-09-22", 0.1)], NOW_0923, since="2026-09-21",
              axis3=AXIS3_MET)
    items = [t["item"] for t in c["open_ticks"]]
    assert items == ["level 1 is a raw count", "D7 'held in the next window'", "D28 as read here",
                     "D47, D54, D55 as read here", "POST_HORIZON_DAYS = 14", "D56 as read here", "watch outcomes in DORA",
                     "REGIME_SE_MULTIPLE = 2.0", "the exposure rules"]      # D54-D56 and draw5 scoring M10 added
    facts = {t["item"]: t["fact"] for t in c["open_ticks"]}
    assert facts["level 1 is a raw count"].startswith("1 refuted or unproven")
    assert "'> 0'" in facts["D7 'held in the next window'"] and "not evaluable" in facts["D7 'held in the next window'"]
    text = B.render(c)
    assert "FOR KHOA" in text and "window requested" in text and "window effective" in text
    assert "could only move it down" not in text and "not implemented" not in text


def test_the_rank_is_monotone_only_at_fixed_exposure():
    """S5, now stated in rank_key's docstring rather than claimed away: on a date card an EARLIER proven
    submission lengthens the window, so P+P can rank below P (TICK territory; pinned so it is seen)."""
    p = _card([("P", "p1", "2026-09-20", 0.1)], NOW_1010, until="2026-09-23")
    pp = _card([("P", "p1", "2026-09-20", 0.1), ("P", "p0", "2026-09-05", 0.1)], NOW_1010, until="2026-09-23")
    assert (p["window"]["quota_days"], pp["window"]["quota_days"]) == (3, 18)
    assert B.rank_cmp(pp, p) == 1 and "Monotone only AT FIXED EXPOSURE" in " ".join(B.rank_key.__doc__.split())


def test_every_forge_module_has_a_real_test_on_the_real_tree():
    """The coverage fitness function now requires EVERY module (MODULE_TEST_COVERAGE_MIN = 1.0); with
    forge/tests/test_standard.py it holds on this tree."""
    assert B.MODULE_TEST_COVERAGE_MIN == 1.0
    mods, tested = B._modules_with_a_real_test()
    assert "standard" in tested and tested == mods, sorted(set(mods) - set(tested))
    ff = {n: ok for n, ok, _ in B.fitness_functions()}
    assert ff["every forge module has a test"] is True


# ============================================ draw3_fix scoring (docs/evalharness/audits/draw3_fix.md) and
# Khoa's D26-D30, D39, D41. Each test names the fix ("draw3_fix scoring N") or decision it guards.

# ------------------------------------------------------------------ fix 1 and D27: seen_until, not now
def test_a_cut_far_before_now_leaves_the_horizon_open_and_the_next_window_not_evaluable():
    """Draw3_fix scoring 1 (adjv1.py, V1b). Window 09-10..11, next window 09-12..13; b created 09-12 and
    POSTed 09-17; the journal copy cut 09-15 12:00; graded 09-30. With the POST history as it stood at the
    cut, the card read held False and its horizon final -- judged against `now`, never the cut. At
    seen_until = min(now, data_through) the next window's horizon (final 09-28) is still open, so it is not
    evaluable; with the full history it holds."""
    win = dict(since="2026-09-10", until="2026-09-12")
    rows, scored, corr, hist, curves = _cohort([("P", "a", "2026-09-10", 0.1), ("P", "b", "2026-09-12", 5)])
    at_cut = [h for h in hist if h["alpha"] != "b"]
    cut, graded = _ts("2026-09-15", 12), _ts("2026-09-30", 15)
    t = B.build_from(rows, scored, corr, at_cut, curves, STANDARD, now=graded, data_through=cut, **win)[
        "axes"]["axis2_throughput"]
    assert t["sustainability_evidence"]["held_in_next_window"] == "not evaluable"
    assert "still open at seen_until 2026-09-15T12:00" in t["next_window"]
    full = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=graded, data_through=cut, **win)
    assert full["axes"]["axis2_throughput"]["sustainability_evidence"]["held_in_next_window"] is True
    # V1b: cut 09-12, graded 10-30 -- the newest graded day 09-10 closes 09-25, after the cut
    v1b = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-10-30", 15),
                       data_through=_ts("2026-09-12", 12), **win)
    ph = v1b["axes"]["axis2_throughput"]["post_horizon"]
    assert ph["final"] is False and ph["seen_until"] == _ts("2026-09-12", 12)
    assert ph["comparable_from_et"] == "2026-09-25" and v1b["rank"]["horizon_final"] is False
    uncut = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-10-30", 15), **win)
    assert uncut["axes"]["axis2_throughput"]["post_horizon"]["final"] is True


def test_an_open_card_is_not_ranked_and_prints_when_it_can_be():
    """D27 (Khoa, 2026-09-23): rank_cmp REFUSES a card whose POST horizon is not final at seen_until, and the
    card prints the ET date from which it is comparable. Before, a live version ranked below an identical
    retired one only because its POSTs had not landed yet (round 2's A4 bias moved into the rank)."""
    specs = [("P", "p1", "2026-09-20", 0.1)]
    open_card = _card(specs, NOW_0923, until="2026-09-23")
    closed = _card(specs, NOW_1010, until="2026-09-23")
    assert open_card["rank"]["comparable_from_et"] == "2026-10-05" and open_card["rank"]["horizon_final"] is False
    with pytest.raises(B.NotComparable, match="comparable from 2026-10-05"):
        B.rank_cmp(open_card, closed)
    with pytest.raises(B.NotComparable):
        B.rank_key(open_card)
    assert B.rank_cmp(closed, closed) == 0
    assert "NOT COMPARABLE until 2026-10-05 ET (D27)" in B.render(open_card)
    assert "RANK comparable" in B.render(closed)
    # the cut, not the clock: graded 10-10 on a copy cut 10-06 01:00 ET the horizon (10-05) is closed; on a copy cut
    # 10-01 01:00 ET it is open (draw4_build scoring 6: this comment said "cut 09-30 ... closed")
    assert _card(specs, NOW_1010, until="2026-09-23", data_through=_ts("2026-10-06", 1))["rank"]["horizon_final"] is True
    assert _card(specs, NOW_1010, until="2026-09-23", data_through=_ts("2026-10-01", 1))["rank"]["horizon_final"] is False


def test_compares_submission_reading_is_judged_at_the_data_cut():
    """Draw3_fix scoring 3 (S4g) and 1: compare() must hand data_through to the secondary reading. Graded 09-24
    both arms' horizons have closed by the clock (A: 09-19, B: 09-23), but on a copy cut 09-12 neither has."""
    ledger = [_deploy("A", "2026-09-01"), _deploy("B", "2026-09-05"), _deploy("C", "2026-09-09")]
    a = _cohort([("P", "a%d" % i, d, 12) for i, d in enumerate(("2026-09-02", "2026-09-03", "2026-09-04"))], "A")
    b = _cohort([("P", "b%d" % i, d, 12) for i, d in enumerate(("2026-09-06", "2026-09-07", "2026-09-08"))], "B")
    rows, scored, corr, hist, curves = _merge(a, b)
    args = (rows, hist, curves, STANDARD, scored, corr, "A", "B")
    assert {v["status"] for v in B.compare(*args, now=_ts("2026-09-24", 15), deploys=ledger)[
        "submissions_secondary"].values()} == {"final"}
    cut = B.compare(*args, now=_ts("2026-09-24", 15), deploys=ledger, data_through=_ts("2026-09-12", 12))
    assert {v["status"] for v in cut["submissions_secondary"].values()} == {"censored"}


# --------------------------------------------------------------------------- fix 2: coverage gap
def test_the_card_names_whole_days_on_which_the_journal_holds_no_row():
    """Draw3_fix scoring 2 (V11): rows run to 09-12 and data_through is 09-20; the card read a rate over
    09-10..09-19 and said only that 09-20 was excluded. It now names the seven empty days."""
    rows = [_journal_row("a", "2026-09-10"), _journal_row("b", "2026-09-12")]
    card = B.build_from(rows, {}, {}, [], {}, {}, now=_ts("2026-09-21", 15), since="2026-09-10",
                        data_through=_ts("2026-09-20", 23))
    w = card["window"]
    assert w["quota_days"] == 10 and w["until_exclusive"] == "2026-09-20"
    gap = w["coverage_gap"]
    assert (gap["first"], gap["last"], gap["days"], gap["last_row_day"]) == ("2026-09-13", "2026-09-19", 7, "2026-09-12")
    assert "COVERAGE GAP" in B.render(card) and "2026-09-13..2026-09-19" in B.render(card)
    whole = rows + [_journal_row("c", "2026-09-19")]
    assert B.build_from(whole, {}, {}, [], {}, {}, now=_ts("2026-09-21", 15), since="2026-09-10",
                        data_through=_ts("2026-09-20", 23))["window"]["coverage_gap"] is None


# ------------------------------------------------------------------ fix 3: the surviving mutants
def test_axis_ones_binding_gate_reads_binding_when_it_is_called(monkeypatch):
    """Draw3_fix scoring 3 (EST, V6): `names=BINDING` was bound when the def ran, so an edit of BINDING never
    reached axis 1. Asserted THROUGH axis1_product, as the fix asks."""
    rows, scored, corr, hist, curves = _cohort([("P", "p1", "2026-09-10", 0.1)])

    def gate():
        c = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 15), since="2026-09-10",
                         until="2026-09-11")
        return c["axes"]["axis1_product"]["detail"][0]["gates"]["all_binding_pass"]
    assert gate() is True
    monkeypatch.setattr(B, "BINDING", B.BINDING + ("SOME_NEW_CHECK",))
    assert gate() is False


def test_the_rates_numerator_counts_only_alphas_created_on_live_days():
    """Draw3_fix scoring 3 (S1f): a PROVEN submission created on the deploy day is graded by axis 1 and left
    out of the rate's numerator as well as its denominator; the old tests put only REFUTED alphas there."""
    rows, scored, corr, hist, curves = _merge(_cohort([("P", "p1", "2026-09-10", 0.1)], "V"),
                                              _cohort([("P", "pdep", "2026-09-09", 0.1)], "V"))
    c = B.build_from(rows, scored, corr, hist, curves, STANDARD, version="V", now=NOW_0923,
                     deploys=[_deploy("V", "2026-09-09", hour=10)])
    t = c["axes"]["axis2_throughput"]
    assert c["axes"]["axis1_product"]["proven"] == 2 and c["window"]["quota_days"] == 13
    assert t["proven_clean_submissions"] == 1 and t["proven_clean_per_quota_day"] == round(1 / 13, 3)
    assert c["window"]["exposure"]["submissions_outside_exposure"] == 1


def test_the_cell_mix_expected_counts_weigh_each_arm_by_its_size():
    """Draw3_fix scoring 3 (S6c): an expected count of col / 2 survived because the only 2 x 2 had equal arms.
    Unequal arms (600 against 300), against the closed form N(ad - bc)^2 / (margins)."""
    a, b, c, d = 500, 100, 50, 250
    n = a + b + c + d
    by_hand = n * (a * d - b * c) ** 2 / ((a + b) * (c + d) * (a + c) * (b + d))
    cm = B.cell_mix({"USA/d1": [0, a], "GLB/d1": [0, b]}, {"USA/d1": [0, c], "GLB/d1": [0, d]})
    assert cm["statistic"] == pytest.approx(by_hand, rel=1e-9)
    assert cm["min_expected"] == round((c + d) * (b + d) / n, 2)          # arm B's GLB/d1: 300 x 350 / 900


def test_a_cell_one_arm_never_scored_in_is_a_mix_difference():
    """Draw3_fix scoring 3 (S6g): dropping cells present in one arm only survived. A scores USA/d1 only, B
    USA/d1 and GLB/d1: the 2 x 2 is [[100, 0], [100, 100]], statistic 300 x 100^4 / (100 x 200 x 200 x 100)."""
    cm = B.cell_mix({"USA/d1": [0, 100]}, {"USA/d1": [0, 100], "GLB/d1": [0, 100]})
    assert cm["cells"] == ["GLB/d1", "USA/d1"] and cm["df"] == 1
    assert cm["statistic"] == pytest.approx(75.0) and cm["differs"] is True


# ----------------------------------------------------------- the correlation gate's missing reading
def test_a_prod_reading_with_no_self_reading_is_unmeasured_not_failed():
    """Draw3_fix scoring task: a PROD reading with no SELF reading read as a FAILED gate (refuted), where nothing
    had been measured to fail. A reading present and over its line is still a measured failure."""
    def status(c):
        rows, scored, corr, hist, curves = _cohort([("P", "p1", "2026-09-10", 0.1)])
        corr["p1"] = c
        d = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 15), since="2026-09-10",
                         until="2026-09-11")["axes"]["axis1_product"]["detail"][0]
        return d["gates"]["corr_under_lines"], d["status"]
    assert status({"prod": 0.5}) == (None, "unproven")
    assert status({"self": 0.4}) == (None, "unproven")
    assert status({}) == (None, "unproven")
    assert status({"prod": 0.75}) == (False, "refuted")
    assert status({"self": 0.75}) == (False, "refuted")
    assert status({"prod": 0.5, "self": 0.4}) == (True, "proven")
    assert status({"prod": 0.5, "self": 0.7}) == (False, "refuted")


# --------------------------------------------------------------------- fix 5: a missing journal
def test_a_missing_journal_is_a_gap_not_a_crash(tmp_path, monkeypatch):
    """Draw3_fix scoring 5: load_inputs called stat() on the journal unconditionally; where it is untracked (the
    CI checkout) FileNotFoundError was raised and `|| true` hid it."""
    _quiet_disk(monkeypatch)
    absent = tmp_path / "absent.jsonl"
    card = B.build(journal=absent, run_drill=False, now=NOW_0923)
    assert card["window"]["data_through"] is None and card["provenance"]["inputs"]["rows"] == 0
    assert any("does not exist on this host" in g and str(absent) in g for g in card["gaps"])


# ------------------------------------------------------------------------ fix 6: the rate wording
def test_the_rate_wording_tells_unknown_exposure_from_zero_days():
    """Draw3_fix scoring 6. V2: exposure KNOWN to be 0 whole days printed "no rate (exposure unknown)" and
    "from None". V3: exposure UNKNOWN printed "rate on 13 day(s)"."""
    rows, scored, corr, hist, curves = _cohort([("R", "q1", "2026-09-20", 0.1)], "V")
    zero = B.build_from(rows, scored, corr, hist, curves, STANDARD, version="V", now=NOW_0923,
                        deploys=[_deploy("V", "2026-09-20", hour=10), _deploy("W", "2026-09-21", hour=9)])
    text = B.render(zero)
    assert "0 whole ET quota days: no rate" in text and "no rate (0 whole ET quota days)" in text
    assert "from None" not in text and "exposure unknown" not in text and "rate on 0 days" in text
    specs = [("P", "v%02d" % i, "2026-09-%02d" % (10 + i // 4), 0.05) for i in range(20)]
    unknown = _card(specs, NOW_0923, version="V", deploys=None)
    ef = unknown["window"]["effective"]
    assert (ef["rate_days"], ef["rate_first_day"], ef["rate_last_day"]) == (None, None, None)
    text = B.render(unknown)
    assert "exposure unknown: no rate" in text and "window effective: no rate (exposure unknown)" in text
    assert "rate on 13 day(s)" not in text and "whole ET quota day(s) from" not in text


# ------------------------------------------------------------------------------- fix 8: DORA
def test_dora_counts_an_interrupted_or_units_down_deploy_as_a_failure():
    """Draw3_fix scoring 8 (V8): [deployed, interrupted, units_down, deployed] read CFR 0.0 and both band checks
    ok. tools/deploy.py's DEPLOY_LOG row contract names both outcomes as not clean."""
    base = _ts("2026-09-10", 10)
    ledger = [{"outcome": o, "started_at": base + i * H, "finished_at": base + (i + 0.5) * H, "version": "v%d" % i}
              for i, o in enumerate(("deployed", "interrupted", "units_down", "deployed"))]
    d = B.dora(ledger, now=base + 20 * H)
    assert d["deploys"] == 4 and d["change_failure_rate"] == 0.5
    assert B.dora_checks(d)[0][1] is False


# --------------------------------------------------------------- fix 10: the comparison's print
def test_the_comparison_prints_its_smallest_expected_count_and_note():
    """Draw3_fix scoring 10: min_expected and the chi-square note were computed and never printed (V9)."""
    now = _ts("2026-09-20", 15)
    rows = (_arm_in("A", A_DAYS[:1], 10, [1], "USA") + _arm_in("A", A_DAYS[:1], 2, [0], "GLB")
            + _arm_in("B", B_DAYS[:1], 10, [1], "USA") + _arm_in("B", B_DAYS[:1], 2, [0], "GLB"))
    out = B.compare(rows, [], {}, {}, {}, {}, "A", "B", now=now)
    text = B.render_compare(out)
    assert out["cell_mix"]["min_expected"] == 2.0 and "min expected 2.0" in text
    assert "note: an expected count is under 5" in text
    assert out["verdict_text"].split()[0] == out["verdict"]               # the text states the JSON's verdict


# ------------------------------------------------------------------------------- fix 11: wording
def test_the_draw3_fix_wording_says_only_what_was_measured():
    """Draw3_fix scoring 11, six sentences, checked on the source so a revert shows."""
    import inspect
    flat = lambda s: " ".join(s.split())                                            # noqa: E731
    src = open(B.__file__).read()
    assert "pooled comparison is confounded exactly when" not in flat(B.cell_mix.__doc__)
    assert "only when the per-cell rates also differ" in flat(B.cell_mix.__doc__)
    assert "Whichever holds" not in B.compare.__doc__ and "Which holds is UNMEASURED" in flat(B.compare.__doc__)
    assert "created before the last whole day" not in flat(B.__doc__)
    assert "names no file" in flat(B.load_standard.__doc__)
    assert "on the VPS journal, COMPLETE rows with a check set" in flat(src) and "27,890 of 37,307" in flat(src)
    assert "dispersion 11.99, chi-square 95.96 on 8 df" in flat(B.compare.__doc__)
    assert "09-22" not in flat(inspect.getsource(B.open_ticks))                     # no stale dated fact


# ---------------------------------------------------------------- fix 12 and D30: cohorts and the gap
def _stamped(alpha, day, pv, rc=None):
    meta = {"pipeline_version": pv} if pv is not None else {}
    if rc is not None:
        meta["run_config"] = rc
    return dict(_journal_row(alpha, day), meta=meta)


def test_the_cohort_gap_counts_plain_cohorts(tmp_path, monkeypatch):
    """Draw3_fix scoring 12: the gap cleared on ANY truthy stamp -- `unknown`, `+untracked`, `+MISMATCH` -- and on
    a single version, while compare() needs two. It counts distinct PLAIN cohorts (D30)."""
    _quiet_disk(monkeypatch)
    cut = _ts("2026-09-22", 16)

    def gaps(rows):
        return [g for g in B.build(journal=_journal_file(tmp_path, rows, cut), run_drill=False, now=NOW_0923)["gaps"]
                if "cohort" in g]
    suffixed = [_stamped("a", "2026-09-21", "e4726594f240aa07+MISMATCH:112bf034df6a7ed6"),
                _stamped("b", "2026-09-21", "112bf034df6a7ed6+untracked"), _stamped("c", "2026-09-21", "unknown")]
    g = gaps(suffixed)
    # draw4_build scoring 6 (moved from "plain meta.pipeline_version (3 carry a suffixed or marker stamp"): the gap
    # counts stamp PAIRS that form no cohort
    assert len(g) == 1 and "stamp pair that forms a cohort (3 carry a meta.pipeline_version whose pair forms none" in g[0]
    rc_only = gaps([_stamped("f", "2026-09-21", "V", 5), _stamped("h", "2026-09-21", "V", "ambiguous")])
    assert len(rc_only) == 1 and "(2 carry" in rc_only[0] and "suffixed or marker pipeline_version or run_config" in rc_only[0]
    g = gaps(suffixed + [_stamped("d", "2026-09-21", "v1")])
    assert len(g) == 1 and "Exactly one cohort (v1)" in g[0]
    assert gaps(suffixed + [_stamped("d", "2026-09-21", "v1"), _stamped("e", "2026-09-21", "v1", "r2")]) == []


def test_a_cohort_is_the_pair_of_stamps_and_a_suffixed_stamp_forms_none():
    """D30 (Khoa, 2026-09-23 ~15:45, implementation note): a cohort is (meta.pipeline_version, meta.run_config);
    a row without run_config is (pv, None); a suffixed or marker stamp never forms one; the deploy ledger joins
    on pipeline_version only, so a (pv, run_config) card still gets pv's live days."""
    rows = [_stamped("a", "2026-09-10", "V", "r1"), _stamped("b", "2026-09-10", "V", "r2"),
            _stamped("c", "2026-09-10", "V"), _stamped("d", "2026-09-10", "V+untracked"),
            _stamped("e", "2026-09-10", "unknown"), _stamped("f", "2026-09-10", "V", 5), _stamped("g", "2026-09-10", None)]
    assert [B.cohort_of(r) for r in rows] == [("V", "r1"), ("V", "r2"), ("V", None), None, None, None, None]
    now, ledger = _ts("2026-09-20", 15), [_deploy("V", "2026-09-09")]
    r1 = B.build_from(rows, {}, {}, [], {}, {}, now=now, version="V@r1", deploys=ledger)
    assert r1["axes"]["axis2_throughput"]["scored_alphas"] == 1
    assert r1["window"]["cohort"] == {"pipeline_version": "V", "run_config": "r1"} and r1["window"]["version"] == "V@r1"
    # D45 (moved, as draw4_build scoring 2 asked): this read quota_days 10, V's whole live-day set, for ANY run_config
    # of V. With no run_config log read, a run_config cohort's exposure is unknown; with the log it is its own days.
    assert r1["window"]["exposure"]["known"] is False and r1["window"]["quota_days"] is None
    log = [{"at": _ts("2026-09-09", 11), "pipeline_version": "V", "run_config": "r1", "host": "vps"}]
    r1 = B.build_from(rows, {}, {}, [], {}, {}, now=now, version="V@r1", deploys=ledger, run_config_log=log)
    assert r1["window"]["exposure"]["known"] is True and r1["window"]["quota_days"] == 10   # 09-10..19
    assert r1["provenance"]["inputs"]["run_config_log"] == 1
    bare = B.build_from(rows, {}, {}, [], {}, {}, now=now, version="V")
    assert [d["alpha"] for d in bare["axes"]["axis1_product"]["detail"]] == [] and bare["axes"]["axis2_throughput"]["scored_alphas"] == 1
    assert B.build_from(rows, {}, {}, [], {}, {}, now=now, version=("V", "r2"))["window"]["version"] == "V@r2"
    for bad in ("V+untracked", "unknown", "x+EXTRAS:3", "ambiguous"):
        with pytest.raises(ValueError, match="forms no cohort"):
            B.build_from(rows, {}, {}, [], {}, {}, now=now, version=bad)
    with pytest.raises(ValueError, match="run_config"):
        B.build_from([_stamped("w", "2026-09-10", "W", "r9")], {}, {}, [], {}, {}, now=now, version="W")
    arms = _arm("A", A_DAYS, 10, [1] * 5) + _arm("A", B_DAYS, 10, [3] * 5)
    for r in arms:
        r["meta"] = dict(r["meta"], run_config="old" if r["dateCreated"] < "2026-09-10" else "new")
        r["alpha"] += r["meta"]["run_config"]
    out = B.compare(arms, [], {}, {}, {}, {}, "A@old", ("A", "new"), now=now)
    assert list(out["versions"]) == ["A@old", "A@new"]
    assert [out["versions"][k]["clearing_every_binding_check"] for k in out["versions"]] == [5, 15]


# ----------------------------------------------------------------------------- D26 and D29
def test_an_unproven_submission_costs_a_place_at_level_one():
    """D26 (Khoa, 2026-09-23): level 1 = REFUTED + UNPROVEN submitted. S2 measured rank_cmp(unmeasured,
    measured) = -1 under refuted-only: the alpha whose neighbours were never measured ranked ABOVE the same
    alpha measured as fragile. Now they tie at level 1."""
    unmeasured = _card([("U", "x", "2026-09-10", 0.1)], NOW_1010, until="2026-09-23")
    fragile = _card([("R", "x", "2026-09-10", 0.1)], NOW_1010, until="2026-09-23")
    assert unmeasured["rank"]["refuted_or_unproven_submitted"] == fragile["rank"]["refuted_or_unproven_submitted"] == 1
    assert B.rank_cmp(unmeasured, fragile) == 0


def test_the_verdict_leads_the_rank_on_real_cards():
    """D29 (Khoa, 2026-09-23): a PASS card ranks above a FAIL card whatever the lower levels say. The FAIL card
    below has more proven output per day (5 against 4) and fails axis 3 only."""
    four = [("P", "p%d" % i, "2026-09-22", 0.1) for i in range(4)]
    five = [("P", "q%d" % i, "2026-09-22", 0.1) for i in range(5)]
    passing = _card(four, NOW_1010, since="2026-09-22", until="2026-09-23", axis3=AXIS3_MET)
    failing = _card(five, NOW_1010, since="2026-09-22", until="2026-09-23", axis3={"value": 0.857, "floor_met": False})
    assert passing["verdict"] == "PASS" and failing["verdict"] == "FAIL"
    assert failing["rank"]["proven_clean_per_quota_day"] > passing["rank"]["proven_clean_per_quota_day"]
    assert B.rank_cmp(passing, failing) == -1


# ------------------------------------------------------------------------------- D28: within cell
def test_the_stratified_test_is_the_exact_convolution_of_the_per_cell_binomials():
    """D28's test, second derivation (RULE 0 #5): two cells by exact fractions -- cell 1 K = 8, pi = 1/2,
    k_B = 6; cell 2 K = 4, pi = 3/4, k_B = 3; T = 9 -- and the one-cell case is rate_test_p exactly."""
    from fractions import Fraction as Fr

    def pmf(K, pi):
        return [Fr(math.comb(K, i)) * pi ** i * (1 - pi) ** (K - i) for i in range(K + 1)]
    p1, p2 = pmf(8, Fr(1, 2)), pmf(4, Fr(3, 4))
    dist = [sum(p1[i] * p2[t - i] for i in range(9) if 0 <= t - i <= 4) for t in range(13)]
    assert sum(dist) == 1
    exact = min(Fr(1), 2 * min(sum(dist[:10]), sum(dist[9:])))
    assert B.stratified_rate_test_p([(2, 100, 6, 100), (1, 50, 3, 150)]) == pytest.approx(float(exact), rel=1e-12)
    one = B.rate_test_p(6, 5000, 18, 5000)
    assert B.stratified_rate_test_p([(6, 5000, 18, 5000)]) == one
    assert B.stratified_rate_test_p([(6, 5000, 18, 5000), (0, 10, 0, 10), (3, 0, 4, 100)]) == one
    assert B.stratified_rate_test_p([]) == 1.0


def test_better_or_worse_needs_every_cell_with_an_event_to_point_the_same_way():
    """D28: 'better/worse only when the cells that have events agree in direction; disagreement reads
    INDISTINGUISHABLE'. In each case below the stratified test IS significant, and only the agreement rule
    withholds the label. As read here (open_ticks, 'D28 as read here'): a tie, or a cell with an event that
    one arm never scored in, points no way."""
    now = _ts("2026-09-20", 15)
    usa = _arm_in("A", A_DAYS, 200, [1] * 5, "USA") + _arm_in("B", B_DAYS, 200, [6] * 5, "USA")   # 5 vs 30 per 1,000 rows

    def verdict(extra):
        out = B.compare(usa + extra, [], {}, {}, {}, {}, "A", "B", now=now)
        assert out["p_value"] < 0.05, out["p_value"]
        return out["verdict"], out["why"]
    agree = _arm_in("A", A_DAYS, 200, [1] * 5, "GLB") + _arm_in("B", B_DAYS, 200, [3] * 5, "GLB")
    assert verdict(agree)[0] == "better"
    against = _arm_in("A", A_DAYS, 200, [2] * 5, "GLB") + _arm_in("B", B_DAYS, 200, [1] * 5, "GLB")
    v, why = verdict(against)
    assert v == "indistinguishable" and "GLB/d1 B lower" in why and "USA/d1 B higher" in why
    tie = _arm_in("A", A_DAYS, 200, [1] * 5, "GLB") + _arm_in("B", B_DAYS, 200, [1] * 5, "GLB")
    assert verdict(tie) == ("indistinguishable", verdict(tie)[1]) and "GLB/d1 equal" in verdict(tie)[1]
    one_arm = _arm_in("A", A_DAYS, 200, [2] * 5, "EUR")
    v, why = verdict(one_arm)
    assert v == "indistinguishable" and "EUR/d1 one arm only" in why
    assert verdict(_arm_in("A", A_DAYS, 200, [0] * 5, "EUR"))[0] == "better"      # no event there: no direction needed


# ------------------------------------------------------------------------------------ D39: meaning
def _gen_card(meaning, now=None, hyp="gen:fam_x"):
    rows, scored, corr, hist, curves = _cohort([("P", "g1", "2026-09-10", 0.1)])
    for r in rows:
        r["meta"] = dict(r["meta"], hypothesis=hyp)
    return B.build_from(rows, scored, corr, hist, curves, STANDARD, now=now or _ts("2026-09-20", 15),
                        since="2026-09-10", until="2026-09-11", meaning=meaning)


def _mrow(alpha="g1", sha=None, at=None, **gates):
    """A meaning row; `sha` None = the sha256 of the alpha's own formula text in _cohort ("rank(<alpha>)"), the key
    the writer stamps (round 3 S8: the reader now checks it)."""
    g = {"G1": None, "G2": None, "G3": None, "G4": True, "G5": True, "G6": True, "G7": True, "G8": True}
    g.update(gates)
    sha = hashlib.sha256(("rank(%s)" % alpha).encode()).hexdigest() if sha is None else sha
    return {"alpha": alpha, "formula_sha": sha, "gates": g, "route": "rule", "scorer": "fixture",
            "scored_at": at if at is not None else _ts("2026-09-11", 9)}


def test_a_generated_alpha_takes_its_gate_half_from_the_meaning_ledger():
    """D39 (Khoa, 2026-09-23 ~17:20): a `gen:` alpha is PROVEN on D10's gate half when every DECIDABLE gate (G4's
    leg clause, G5-G8) is true; G1-G3 are UNMEASURED ('not applicable to a generated alpha') and never make it
    unproven; a missing row does. Before, load_standard maps composites only, so every generated alpha read
    unproven for ever and, under D26, counted against its version (04_passfirst_design.md section 4.4)."""
    def gate(meaning, **kw):
        d = _gen_card(meaning, **kw)["axes"]["axis1_product"]["detail"][0]
        return d["gates"]["hypothesis_standard_8of8"], d["status"]
    assert gate([_mrow()]) == (True, "proven")
    assert gate([_mrow(G1=False, G2=False, G3=False)]) == (True, "proven")      # not applicable, whatever is written
    assert gate([_mrow(G6=False)]) == (False, "refuted")
    assert gate([_mrow(G7=None)]) == (None, "unproven")
    assert gate([_mrow(G5=1)]) == (None, "unproven")                            # not exactly true: not a pass
    assert gate([]) == (None, "unproven")                                       # read, no row for this alpha
    assert gate(None) == (None, "unproven")                                     # not read
    assert gate([_mrow(at=_ts("2026-09-21", 9))]) == (None, "unproven")        # scored after the grading clock
    assert gate([_mrow(at="2026-09-11T09:00:00-04:00")]) == (True, "proven")   # an ISO time reads too
    # round 3 S8, both moved: a row for ANOTHER formula is ignored (was: two shas made the alpha unmeasured), and
    # the EARLIEST row of the alpha's own formula decides (was: the latest row won)
    assert gate([_mrow(), _mrow(sha="s2", at=_ts("2026-09-12", 9))]) == (True, "proven")
    assert gate([_mrow(G8=False), _mrow(at=_ts("2026-09-12", 9))]) == (False, "refuted")
    card = _gen_card([_mrow()])
    assert card["axes"]["axis1_product"]["detail"][0]["standard_route"]["decidable"]["G4"] is True
    assert "G1-G3 UNMEASURED: not applicable to a generated alpha (D39)" in B.render(card)
    # a library composite keeps load_standard, whatever the meaning ledger holds
    lib = _gen_card([_mrow()], hyp="h_bad")["axes"]["axis1_product"]["detail"][0]
    assert lib["gates"]["hypothesis_standard_8of8"] is False and "load_standard" in lib["standard_route"]["route"]


def test_build_reads_the_meaning_ledger_and_names_its_absence(tmp_path, monkeypatch):
    """D39 through build(): load_inputs reads state/forge/meaning.jsonl; when it is absent and a generated alpha
    was scored, the card says so rather than read every one unproven silently."""
    import json
    real_load_meaning = B.load_meaning
    _quiet_disk(monkeypatch)
    row = dict(_journal_row("g1", "2026-09-21"), meta={"hypothesis": "gen:fam_x"})
    journal = _journal_file(tmp_path, [row], _ts("2026-09-22", 16))
    assert any("meaning.jsonl does not exist" in g and "1 generated" in g
               for g in B.build(journal=journal, run_drill=False, now=NOW_0923)["gaps"])
    ledger = tmp_path / "meaning.jsonl"
    ledger.write_text(json.dumps(_mrow()) + "\n")
    assert real_load_meaning(ledger) == [_mrow()] and real_load_meaning(tmp_path / "none.jsonl") is None
    monkeypatch.setattr(B, "load_meaning", lambda path=None: [_mrow()])
    card = B.build(journal=journal, run_drill=False, now=NOW_0923)
    assert not any("meaning.jsonl" in g for g in card["gaps"]) and card["provenance"]["inputs"]["meaning"] == 1


# --------------------------------------------------------------------- fix 13: the structural holes
def test_the_ab_check_closes_the_three_adversarial_holes(tmp_path):
    """Draw3_fix scoring 13 (V13): a parse by a DIFFERENT parser, a REBOUND namespace, and the handing call
    after `if True: return` each read as a real A/B arm."""
    other_parser = (RUNNER_HEAD + "def main(argv=None):\n    ap = argparse.ArgumentParser()\n"
                    "    ap.add_argument('--ab', choices=('off', 'new'), default='off')\n"
                    "    bp = argparse.ArgumentParser()\n    a = bp.parse_args(argv)\n    return plan(ab=a.ab)\n")
    assert B._ab_arm_is_real(_runner_at(tmp_path, "other_parser", other_parser))[0] is False
    rebound = RUNNER_HEAD + PARSE + "    a = argparse.Namespace(ab='new')\n    return plan(ab=a.ab)\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "rebound", rebound))[0] is False
    parser_rebound = (RUNNER_HEAD + PARSE.replace("    a = ap.parse_args(argv)\n",
                                                  "    ap = argparse.ArgumentParser()\n    a = ap.parse_args(argv)\n")
                      + "    return plan(ab=a.ab)\n")
    assert B._ab_arm_is_real(_runner_at(tmp_path, "parser_rebound", parser_rebound)) == (
        False, "the parser carrying --ab (ap) is bound 2 times in main()")
    after_if_true = RUNNER_HEAD + PARSE + "    if True:\n        return plan()\n    return plan(ab=a.ab)\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "after_if_true", after_if_true))[0] is False
    both_leave = RUNNER_HEAD + PARSE + "    if a:\n        return plan()\n    else:\n        raise SystemExit\n    plan(ab=a.ab)\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "both_leave", both_leave))[0] is False
    # still true: a branch that may fall through, and a comprehension variable named like the parse
    ok = RUNNER_HEAD + PARSE + "    if a:\n        return plan()\n    _ = [a for a in ()]\n    return plan(ab=a.ab)\n"
    assert B._ab_arm_is_real(_runner_at(tmp_path, "ok", ok))[0] is True
    assert B._ab_arm_is_real(B.ROOT)[0] is True                                      # the real runner


def test_a_home_made_type_checking_is_not_typings(tmp_path):
    """Draw3_fix scoring 13 (V14): `TYPE_CHECKING = True` made a module-level import, which RUNS, read as
    deferred. Only typing's own TYPE_CHECKING, never rebound in the file, defers an import."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "b.py").write_text("from forge import a\n")
    for text, level in (("TYPE_CHECKING = True\nif TYPE_CHECKING:\n    from forge import b\n", "module_level"),
                        ("from typing import TYPE_CHECKING\nTYPE_CHECKING = True\nif TYPE_CHECKING:\n    from forge import b\n",
                         "module_level"),
                        ("import os\nif os.TYPE_CHECKING:\n    from forge import b\n", "module_level"),
                        ("from typing import TYPE_CHECKING as TC\nif TC:\n    from forge import b\n", "deferred"),
                        ("import typing as t\nif t.TYPE_CHECKING:\n    from forge import b\n", "deferred")):
        (pkg / "a.py").write_text(text)
        cyc = B.import_cycles(pkg)
        assert cyc[level] == ["a -> b"] and cyc["module_level" if level == "deferred" else "deferred"] == [], text


def test_structural_families_puts_root_on_the_path_once():
    """Draw3_fix scoring 13: every call inserted ROOT into sys.path again."""
    import sys
    n = sys.path.count(str(B.ROOT))
    for _ in range(3):
        B.structural_families([])
    assert sys.path.count(str(B.ROOT)) == max(n, 1)


def test_the_module_coverage_check_states_its_scope():
    """Draw3_fix scoring 15, documented as a limit: the check covers top-level forge/*.py only."""
    ev = {n: e for n, _, e in B.fitness_functions()}["every forge module has a test"]
    assert "top-level forge modules" in ev and "forge/llm and forge/offline are outside this check" in ev


# ============================== draw-4 build audit, scoring (docs/evalharness/audits/draw4_build.md), pipeline P2,
# round 3 (docs/evalharness/audits/architecture_round3.md F1, S1, S8, S10) and Khoa's D45, D47, D49. Each test names
# the item it guards; the scenario files (p1.py ... p5.py, v4_gen.py, g_late_post.py) are the auditors'.

# -------------------------------------------------------------------- scoring 1: watch rows are never deploys
def _watch(outcome, push, hours_after=1.0, prev_pv=None, prev_version=None):
    """A watch row as tools/deploy.py _record_watch() writes it (DEPLOY_LOG, WATCH ROWS)."""
    return {"outcome": outcome, "started_at": push["finished_at"] + 60, "finished_at": push["finished_at"] + hours_after * H,
            "exit": 0, "watched": push["started_at"], "version": push["version"],
            "pipeline_version": push.get("pipeline_version"), "previous_version": prev_version,
            "previous_pipeline_version": prev_pv, "round_seed": 1, "round_exit": 0, "round_traceback": False}


def test_a_watch_row_is_never_a_deploy():
    """Draw4_build scoring 1 (p5.py): V deployed 09-09 and graded 09-20 has 10 live days; one watch_ok row an hour
    later took that to 0, and dora() read [deploy, deploy] + watch_ok + watch `interrupted` as 4 deploys, CFR 0.25.
    tools/deploy.py's WATCH ROWS contract: a watch row is never a deploy; watch_rolled_back puts the previous
    pipeline back and is a change failure of the push it names."""
    now = _ts("2026-09-20", 15)
    u, v = _deploy("U", "2026-09-01"), _deploy("V", "2026-09-09")
    ten = ["2026-09-%02d" % d for d in range(10, 20)]
    assert B.live_days([u, v], "V", now)["days"] == ten
    assert B.WATCH_KEEPS_RUNNING == ("watch_ok", "watch_timeout", "watch_not_rolled_back")       # draw5 scoring M2
    for keeps in ("watch_ok", "watch_timeout", "watch_not_rolled_back"):
        assert B.live_days([u, v, _watch(keeps, v)], "V", now)["days"] == ten, keeps
    back = [u, v, _watch("watch_rolled_back", v, prev_pv="U", prev_version="tree-U")]
    assert B.live_days(back, "V", now) ["days"] == [] and B.live_days(back, "V", now)["known"] is True
    assert B.live_days(back, "U", now)["days"] == ["2026-09-%02d" % d for d in range(2, 9)] + ten
    for lost in ("interrupted", "watch_interrupted", "watch_rollback_failed", "watch_units_down"):
        assert B.live_days([u, v, _watch(lost, v)], "V", now)["days"] == [], lost
    d = B.dora([u, v, _watch("watch_ok", v), _watch("interrupted", v, 2)], now=now)
    assert d["deploys"] == 2 and d["change_failure_rate"] == 0.0
    w = _deploy("W", "2026-09-12")
    d = B.dora([u, v, _watch("watch_rolled_back", v, 1, prev_pv="U", prev_version="tree-U"), w], now=now)
    assert d["deploys"] == 3 and d["change_failure_rate"] == round(1 / 3, 3)
    assert d["time_to_restore_hours_median"] == pytest.approx((w["finished_at"] - (v["finished_at"] + H)) / H, abs=0.01)
    # re-shipping the version the rollback put back restores nothing
    assert B.dora([u, v, _watch("watch_rolled_back", v, 1, prev_pv="U", prev_version="tree-U"),
                   _deploy("U", "2026-09-12")], now=now)["time_to_restore_hours_median"] is None


# ------------------------------------------------------------- scoring 2 and D45: a cohort's own exposure
def _log(at, pv, rc, host="vps"):
    return {"at": at, "pipeline_version": pv, "run_config": rc, "host": host}


def test_a_run_config_cohort_takes_only_the_days_its_log_records():
    """Draw4_build scoring 2 (p1.py) and D45 (Khoa, 2026-09-23 ~20:15): V deployed 09-09; (V, r1) has one row on 09-10
    and (V, r2) five rows on 09-15..19; graded 09-20 both cohorts read quota_days 10 -- V's whole live-day set. Now a
    cohort's days are V's live days on which the run_config log records its run_config all day; the day it changed
    is excluded for both; another host's rows never end the loop's run_config (draw5 scoring M3: this said "a dry
    run on the Mac", and the runner records live starts only)."""
    now, ledger = _ts("2026-09-20", 15), [_deploy("V", "2026-09-09")]
    log = [_log(_ts("2026-09-09", 10) + 1800, "V", "r1"), _log(_ts("2026-09-12", 15), "V", "rdry", host="mac"),
           _log(_ts("2026-09-14", 12), "V", "r2"), _log(_ts("2026-09-25", 0), "V", "r9")]      # r9: after `now`
    r1 = B.cohort_live_days(ledger, log, ("V", "r1"), now)
    assert r1["known"] and r1["days"] == ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"]
    assert r1["excluded_run_config_days"] == ["2026-09-14"] and r1["unknown_days"] == []
    r2 = B.cohort_live_days(ledger, log, ("V", "r2"), now)
    assert r2["days"] == ["2026-09-%02d" % d for d in range(15, 20)] and r2["excluded_run_config_days"] == ["2026-09-14"]
    # the Mac's own cohort is ITS host's: part of 09-12, then every whole day after (a day counts when some host
    # held the cohort all day); it took nothing from r1 or r2 on the loop's host
    assert B.cohort_live_days(ledger, log, ("V", "rdry"), now)["days"] == ["2026-09-%02d" % d for d in range(13, 20)]
    # its only row is after the clock: unknown -- with or without the after-`now` filter, which is redundant (draw5 M4)
    assert B.cohort_live_days(ledger, log, ("V", "r9"), now)["known"] is False
    assert B.cohort_live_days(ledger, log, ("V", None), now) == B.live_days(ledger, "V", now)     # pre-D30 rows
    assert B.cohort_live_days(ledger, None, ("V", "r1"), now)["known"] is False and "run_config log" in \
        B.cohort_live_days(ledger, None, ("V", "r1"), now)["note"]
    # through the card: each cohort's rate on its own days
    rows, scored, corr, hist, curves = _cohort([("P", "a1", "2026-09-10", 0.1)] +
                                               [("P", "b%d" % d, "2026-09-%02d" % d, 0.1) for d in range(15, 20)], "V")
    for r in rows:
        r["meta"]["run_config"] = "r1" if r["alpha"].startswith("a") else "r2"
    cards = {rc: B.build_from(rows, scored, corr, hist, curves, STANDARD, version="V@" + rc, now=now, deploys=ledger,
                              run_config_log=log) for rc in ("r1", "r2")}
    assert cards["r1"]["window"]["quota_days"] == 4 and cards["r2"]["window"]["quota_days"] == 5
    assert cards["r2"]["axes"]["axis2_throughput"]["proven_clean_per_quota_day"] == 1.0
    assert cards["r2"]["window"]["exposure"]["excluded_run_config_days"] == ["2026-09-14"]
    sec = B.compare(rows, hist, curves, STANDARD, scored, corr, "V@r1", "V@r2", now=_ts("2026-10-10", 15), deploys=ledger,
                    run_config_log=log)["submissions_secondary"]
    # graded 10-10, r2 held the host from 09-14 12:00 until r9's row at 09-25 00:00: 09-15..24, 5 proven over 10 days
    assert sec["V@r2"]["status"] == "final" and sec["V@r2"]["proven_clean_per_quota_day"] == 0.5
    assert B.compare(rows, hist, curves, STANDARD, scored, corr, "V@r1", "V@r2", now=_ts("2026-10-10", 15),
                     deploys=ledger)["submissions_secondary"]["V@r2"]["status"] == "exposure unknown"


def test_build_reads_the_run_config_log(tmp_path, monkeypatch):
    """D45 through build(): load_inputs reads state/forge/run_config_log.jsonl and build() hands it to build_from, so a
    run_config cohort's card has its own days; with no log it reads exposure unknown."""
    import json
    real = B.load_run_config_log
    _quiet_disk(monkeypatch)
    monkeypatch.setattr(B, "load_deploys", lambda root=B.ROOT: [_deploy("V", "2026-09-09")])
    journal = _journal_file(tmp_path, [_stamped("a", "2026-09-12", "V", "r1")], _ts("2026-09-20", 16))
    card = B.build(journal=journal, version="V@r1", run_drill=False, now=_ts("2026-09-21", 15))
    assert card["window"]["exposure"]["known"] is False and card["provenance"]["inputs"]["run_config_log"] is None
    log = tmp_path / "run_config_log.jsonl"
    log.write_text(json.dumps(_log(_ts("2026-09-09", 11), "V", "r1")) + "\n")
    assert real(log) == [_log(_ts("2026-09-09", 11), "V", "r1")] and real(tmp_path / "none.jsonl") is None
    monkeypatch.setattr(B, "load_run_config_log", lambda path=None: real(log))
    card = B.build(journal=journal, version="V@r1", run_drill=False, now=_ts("2026-09-21", 15))
    assert card["window"]["exposure"]["known"] is True and card["window"]["quota_days"] == 10     # 09-10..19


def test_days_before_the_logs_first_row_for_a_cohort_read_exposure_unknown():
    """D45: "Days before any transition row for a cohort read 'exposure unknown', never a guess." This module's
    per-day reading: those days are left out of the rate and listed; the card has no rate only when no day is known."""
    now, ledger = _ts("2026-09-20", 15), [_deploy("V", "2026-09-09")]
    late = [_log(_ts("2026-09-15", 12), "V", "r1")]
    e = B.cohort_live_days(ledger, late, ("V", "r1"), now)
    assert e["known"] and e["days"] == ["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19"]
    assert e["unknown_days"] == ["2026-09-%02d" % d for d in range(10, 15)] and e["excluded_run_config_days"] == ["2026-09-15"]
    assert "read exposure unknown: left out of the rate" in e["note"]
    only_unknown = B.cohort_live_days(ledger, [_log(_ts("2026-09-19", 23), "V", "r1")], ("V", "r1"), now)
    assert only_unknown["known"] is False and only_unknown["note"].startswith("exposure unknown")


# ------------------------------------------------------------------- scoring 3 and pipeline P2: marker run_configs
def test_a_marker_run_config_forms_no_cohort(tmp_path, monkeypatch):
    """Draw4_build scoring 3 (p1.py) and pipeline P2: cohort_of({pv ec6a5cd75d58fea2, run_config "ambiguous"}) was
    ('ec6a5cd75d58fea2', 'ambiguous'), parse_cohort("ec6a5cd75d58fea2@ambiguous") accepted it, and "abc+x" formed a
    cohort too; the pseudo-cohort suppressed build()'s one-cohort gap. recover_orphans writes "ambiguous"."""
    pv = "ec6a5cd75d58fea2"
    for rc in ("ambiguous", "unknown", "abc+x", "r+EXTRAS:2"):
        assert B.cohort_of(_stamped("a", "2026-09-10", pv, rc)) is None, rc
        with pytest.raises(ValueError, match="forms no cohort"):
            B.parse_cohort("%s@%s" % (pv, rc))
        with pytest.raises(ValueError, match="forms no cohort"):
            B.parse_cohort((pv, rc))
    assert B.cohort_of(_stamped("a", "2026-09-10", pv, "e1f7afbdafa17d1a")) == (pv, "e1f7afbdafa17d1a")
    _quiet_disk(monkeypatch)
    rows = [_stamped("a", "2026-09-21", pv, "r1"), _stamped("b", "2026-09-21", pv, "ambiguous")]
    gaps = B.build(journal=_journal_file(tmp_path, rows, _ts("2026-09-22", 16)), run_drill=False, now=NOW_0923)["gaps"]
    assert any("Exactly one cohort (%s@r1)" % pv in g for g in gaps)
    with pytest.raises(ValueError, match="forms no cohort"):
        B.compare(rows, [], {}, {}, {}, {}, pv + "@r1", pv + "@ambiguous", now=NOW_0923)


# ------------------------------------------------- scoring 4: the builder's own sub-rules, one assert each
def test_the_draw3_fix_sub_rules_are_each_pinned():
    """Draw4_build scoring 4 (mut.py): eight mutants left 140 passed. One assertion per mutant, in its order."""
    # (1) the status_counts branch counts refuted AND unproven
    assert B.rank_levels({"axis1_product": {"status_counts": {"refuted": 1, "unproven": 2}}})[
        "refuted_or_unproven_submitted"] == 3
    # (2) a hand-built axis 1 without both counts has no level 1
    assert B.rank_levels({"axis1_product": {"refuted": 1}})["refuted_or_unproven_submitted"] is None
    # (3) a card without post_horizon is not final
    lv = B.rank_levels({"axis2_throughput": {"value": 1.0}})
    assert lv["horizon_final"] is False
    with pytest.raises(B.NotComparable):
        B.rank_key({"rank": lv})
    # (4) G8 is decidable: a generated alpha with G8 false is refuted, not proven
    d = _gen_card([_mrow(G8=False)])["axes"]["axis1_product"]["detail"][0]
    assert (d["gates"]["hypothesis_standard_8of8"], d["status"]) == (False, "refuted")
    # (5) the lower tail of the stratified test, by exact fractions: K = 20, pi = 5/6, k_b = 10
    from fractions import Fraction as Fr
    lower = sum(Fr(math.comb(20, i)) * Fr(5, 6) ** i * Fr(1, 6) ** (20 - i) for i in range(11))
    assert B.stratified_rate_test_p([(10, 100, 10, 500)]) == pytest.approx(float(2 * lower), rel=1e-9)
    assert round(float(2 * lower), 6) == 0.001197
    # (6) rank_cmp refuses an open SECOND card as well as an open first one
    with pytest.raises(B.NotComparable):
        B.rank_cmp(_levels(0, 1.0, 1.0), _levels(0, 1.0, 1.0, final=False))
    # (7) a card with no verdict ranks below FAIL
    assert B.rank_key(_levels(0, 9.0, 1.0, verdict=None))[0] == 2 > B.rank_key(_levels(0, 0.1, 0.1))[0] == 1
    # (8) a reading exactly AT its line, the other missing, is a measured failure
    rows, scored, corr, hist, curves = _cohort([("P", "p1", "2026-09-10", 0.1)])
    corr["p1"] = {"prod": B.SUB.CORR_LINE_DEFAULT}
    d = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 15), since="2026-09-10",
                     until="2026-09-11")["axes"]["axis1_product"]["detail"][0]
    assert (d["gates"]["corr_under_lines"], d["status"]) == (False, "refuted")


# ------------------------------------------------------------------ scoring 5: D27's date across a DST change
def test_the_comparable_date_holds_across_a_dst_change():
    """Draw4_build scoring 5 (p1.py): newest graded day 2026-10-18 printed comparable_from_et 2026-11-01, and a card
    graded at 00:00 ET that day still raised NotComparable (the horizon ends 23:00 EST). Second derivation: newest +
    15 ET calendar days = 2026-11-02. Across the March change the exact end is 01:00 EDT, so the printed day moves to
    03-16, and finality keeps the exact instant (the audit's 00:00-of-newest+15 would read final an hour early)."""
    assert datetime.datetime.fromtimestamp(B.horizon_final_at("2026-10-18"), B.ET).isoformat() == "2026-11-01T23:00:00-05:00"
    assert B.comparable_from(B.horizon_final_at("2026-10-18")) == "2026-11-02"
    assert B.comparable_from(B.horizon_final_at("2026-10-25")) == "2026-11-09"
    assert B.comparable_from(B.horizon_final_at("2026-10-10")) == "2026-10-25"          # no change crossed
    assert datetime.datetime.fromtimestamp(B.horizon_final_at("2027-02-28"), B.ET).isoformat() == "2027-03-15T01:00:00-04:00"
    assert B.comparable_from(B.horizon_final_at("2027-02-28")) == "2027-03-16"

    def card(day, graded):
        return _card([("P", "p1", day, 0.1)], graded, since=day, until=_next(day), axis3=AXIS3_MET)
    open_card = card("2026-10-18", _ts("2026-11-01", 0))
    assert open_card["rank"]["comparable_from_et"] == "2026-11-02" and open_card["rank"]["horizon_final"] is False
    with pytest.raises(B.NotComparable, match="comparable from 2026-11-02"):
        B.rank_key(open_card)
    B.rank_key(card("2026-10-18", _ts("2026-11-02", 0)))                                # the promise holds
    assert card("2027-02-28", _ts("2027-03-15", 0))["rank"]["horizon_final"] is False     # a POST at 00:30 EDT still counts
    B.rank_key(card("2027-02-28", _ts("2027-03-16", 0)))


def _next(day):
    return (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()


# ------------------------------------------------------------------------ scoring 6: text the code contradicted
def test_the_draw4_texts_say_what_the_code_does():
    """Draw4_build scoring 6, each sentence against the code (the gap wording is pinned in
    test_the_cohort_gap_counts_plain_cohorts)."""
    import inspect
    flat = lambda s: " ".join(s.split())                                                   # noqa: E731
    assert "a mix difference cannot move" not in flat(B.cell_mix.__doc__)
    assert "CAN still move compare()'s verdict" in flat(B.cell_mix.__doc__)
    assert "a 'deploy' is a push row of the ledger" in flat(B.dora.__doc__) and "units_down" in B.dora.__doc__
    rows = [_journal_row("a", "2026-09-10"), _journal_row("b", "2026-09-12")]
    gap = B.build_from(rows, {}, {}, [], {}, {}, now=_ts("2026-09-21", 15), since="2026-09-10",
                       data_through=_ts("2026-09-20", 23))["window"]["coverage_gap"]["note"]
    assert "are among this card's rate days" in gap and "and the rate still counts" not in gap   # draw5 M17
    # p2.py: an exposure-unknown card read window.quota_days 13 and since 09-10 beside rate_days None
    specs = [("P", "v%02d" % i, "2026-09-%02d" % (10 + i // 4), 0.05) for i in range(20)]
    w = _card(specs, NOW_0923, version="V", deploys=None)["window"]
    assert (w["quota_days"], w["since"], w["effective"]["rate_days"]) == (None, None, None)
    src = inspect.getsource(test_an_open_card_is_not_ranked_and_prints_when_it_can_be)
    assert "graded 10-10 on a copy cut 09-30, the horizon" not in src


# ------------------------------------------------------------------------------ D49: late POSTs cost a place
def test_a_late_post_counts_against_level_one_and_is_never_credited():
    """D49 (Khoa, 2026-09-23 ~21:00; round 3 S1, g_late_post.py): an unproven alpha POSTed 14.05 or 15 days after
    creation read level 1 = 0 -- the horizon that bounds credit also bounded the penalty. Now level 1 = 1 whatever
    the lag, and only a POST within the horizon is credited to axis 2."""
    for lag, credited in ((13.0, 1), (14.0, 1), (14.05, 0), (15.0, 0)):
        c = _card([("U", "u0", "2026-09-10", lag)], _ts("2026-10-10", 15), since="2026-09-10", until="2026-09-11")
        assert c["rank"]["refuted_or_unproven_submitted"] == 1, lag
        assert c["axes"]["axis2_throughput"]["submissions_of_alphas_this_version_produced"] == credited, lag
        assert B.rank_key(c)[1] == 1
        assert c["axes"]["axis1_product"]["posted_beyond_the_horizon"] == ([] if credited else ["u0"])
    late = _card([("U", "u0", "2026-09-10", 15.0)], _ts("2026-10-10", 15), since="2026-09-10", until="2026-09-11")
    assert "1 such alpha(s)" in {t["item"]: t["fact"] for t in late["open_ticks"]}["POST_HORIZON_DAYS = 14"]


# ------------------------------------------ D47, D54, D55, D60 and round 4 F1, S1, S3: the arms, by round
OCT = ["2026-10-%02d" % d for d in range(1, 32)]


def _round_rows(arm, day, n, k, rnd, cell="USA", pv="V", route="fresh", by="randomiser", hour=12, status="COMPLETE",
                run_config="rc", tag=""):
    """n journal rows of ONE round (meta.round `rnd`), k of them clearing every binding check, stamped as the shared
    interface fixes: meta.arm, meta.arm_by (the randomiser's own rounds read "randomiser") and meta.round = the seed; a
    branch row carries meta.gen_route (`route`; None leaves it out)."""
    meta = {"pipeline_version": pv, "run_config": run_config, "arm": arm, "arm_by": by, "round": rnd, "seed": rnd}
    if arm == B.ARMS[1] and route is not None:
        meta["gen_route"] = route
    return [{"alpha": "%s%s_%s_%s_%s_%d" % (tag, arm, rnd, route, cell, i), "status": status,
             "checks": PASS if i < k else [{"name": "LOW_SHARPE", "result": "FAIL"}],
             "dateCreated": "%sT%02d:00:00-04:00" % (day, hour), "formula": "rank(x%d)" % i,
             "settings": {"region": cell, "delay": 1}, "meta": dict(meta)} for i in range(n)]


def _day_of_rounds(day, pattern, n, start, **kw):
    """One ET day of rounds: `pattern` = [(arm, k)], each a round of n rows with its own meta.round from `start`."""
    return [r for i, (arm, k) in enumerate(pattern) for r in _round_rows(arm, day, n, k, start + i, **kw)]


def test_the_round_is_the_unit_and_its_p_is_the_exact_relabelling_p():
    """D54 and round 4 F1 (FATAL): the alpha-unit test read better / worse in 0.155 of placebo draws on the desk's own
    rounds because D24 events cluster inside rounds. Here, 7 days of two B rounds (5 and 0 events) and two A rounds (1
    and 1), 100 alphas each: pooled per day B leads 5 to 2, and the alpha-unit stratified test calls it (p < 0.01).
    Relabelling whole rounds within each day, the same data read p = 0.0980 EXACTLY (second way: the 6^7 relabellings
    enumerated here, in half-units {3, 5, 5, -5, -5, -3} per day); the Monte Carlo p must sit within its own error of
    that. z by the relabelling variance: 7 x (1/3) x 14.75 = 34.42, z = 10.5 / 5.867 = 1.7898."""
    rows = []
    for i, d in enumerate(OCT[:7]):
        rows += _day_of_rounds(d, [("gen", 5), ("gen", 0), ("composites", 1), ("composites", 1)], 100, 10 * i)
    out = B.compare_arms(rows, "V", now=_ts(OCT[8], 15))
    look = out["looks"][0]
    assert (look["look"], look["shared_days"], look["last_day"]) == (1, 7, OCT[6])
    dist = {0: 1.0}
    for _ in range(7):
        step = {}
        for s, p in dist.items():
            for v in (3, 5, 5, -5, -5, -3):
                step[s + v] = step.get(s + v, 0.0) + p / 6
        dist = step
    exact = sum(p for s, p in dist.items() if abs(s) >= 21)
    assert exact == pytest.approx(0.0980438, abs=1e-6)
    assert abs(look["p_value"] - exact) < 3 * exact / math.sqrt(B.ARMS_PERM_EXCEED)          # BC's relative error
    assert look["z_normal_approx"] == pytest.approx(1.7898, abs=1e-4) and look["statistic"] == pytest.approx(10.5)
    assert B.stratified_rate_test_p([(2, 200, 5, 200)] * 7) < 0.01                           # the alpha-unit reading
    assert out["verdict"] == "withheld" and not look["crossed"] and "the next look is at 14" in out["why"]
    assert out["arms"]["gen"]["rounds"] == 14 and out["arms"]["composites"]["clearing_every_binding_check"] == 14
    assert out["cells"] == {"USA/d1": {"events": 49, "excess_b": 10.5, "direction": "B higher"}}
    assert out["rate_ratio_b_over_a"] == 2.5 and out["arms"]["gen"]["per_1000"] == 25.0      # draw5 M7: B/A, not A/B


def test_only_randomised_rounds_and_fresh_draws_enter_the_comparison():
    """D54, D60 and round 4 S3 / draw5 scoring S1 (V2's layout, fixed data): 20 days, each with two A rounds and two
    B rounds of 50 fresh draws, ONE event per round in both arms -- no effect. Each B round also carries two D51
    neighbour rows, one clearing. Counted in B they made it 2 against 1 per round: "better" at look 1 (every day's B
    pair beats its A pair, relabelling p about 2 / 6^7). Now they are BESIDE the estimand and the read-out withholds.
    Round 4 S3: a search-recipe round (arm composites, arm_by explicit) with no event each day would have made A
    worse; it is EXCLUDED and counted. So are rows of the older --ab arms (draw5 M15), a marker run_config (draw5 M12),
    a row without meta.round, and a round whose rows carry two arms. Unscored rows are counted per arm (round 4 m6)."""
    rows, rid = [], 0
    for d in OCT[:20]:
        for arm in ("gen", "gen", "composites", "composites"):
            rid += 1
            rows += _round_rows(arm, d, 50, 1, rid)
            if arm == "gen":
                rows += _round_rows(arm, d, 2, 1, rid, route="neighbour")
                rows += _round_rows(arm, d, 1, 0, rid, route="fresh", status="ERROR", hour=13, tag="err")
        rows += _round_rows("composites", d, 50, 0, 1000 + rid, by="explicit")            # a recipe round (S3)
    rows += _round_rows("composites", OCT[0], 30, 3, 2001, by=None)                        # no arm_by stamp
    rows += _round_rows("new", OCT[1], 30, 3, 2002)                                        # --ab new (M15)
    rows += _round_rows("gen", OCT[2], 30, 3, 2003, run_config="ambiguous")               # marker run_config (M12)
    nr = _round_rows("gen", OCT[3], 30, 3, 2004)
    for r in nr:
        del r["meta"]["round"]
    two = _round_rows("gen", OCT[4], 5, 5, 2005) + _round_rows("composites", OCT[4], 5, 0, 2005)
    out = B.compare_arms(rows + nr + two, "V", now=_ts(OCT[21], 15))
    assert out["verdict"] == "withheld" and [x["look"] for x in out["looks"]] == [1, 2]
    assert all(x["p_value"] == 1.0 for x in out["looks"]) and out["cells"]["USA/d1"]["direction"] == "equal"
    assert out["arms"]["gen"]["clearing_every_binding_check"] == out["arms"]["composites"]["clearing_every_binding_check"] == 40
    assert out["beside"] == {"gen/neighbour": {"rounds": 40, "scored_rows": 80, "clearing_every_binding_check": 40}}
    assert out["arms"]["gen"]["unscored_rows"] == 40 and out["arms"]["composites"]["unscored_rows"] == 0
    assert out["excluded"]["by_reason"] == {
        "meta.arm 'new' is not an arm of D47": {"rounds": 1, "rows": 30},
        "meta.arm_by 'explicit': not assigned by the randomiser (D60)": {"rounds": 20, "rows": 1000},
        "meta.arm_by None: not assigned by the randomiser (D60)": {"rounds": 1, "rows": 30},
        "no meta.round": {"rounds": 1, "rows": 30},
        "run_config 'ambiguous' forms no cohort (D30)": {"rounds": 1, "rows": 30},
        "the rows of one meta.round carry different arms": {"rounds": 1, "rows": 10}}
    assert (out["excluded"]["rounds"], out["excluded"]["rows"]) == (25, 1130)
    text = B.render_arms(out)
    assert "EXCLUDED from the comparison (D60): 25 round(s), 1130 row(s)" in text and "gen/neighbour" in text
    only_ab = B.compare_arms(_round_rows("current", OCT[0], 10, 1, 1) + _round_rows("new", OCT[0], 10, 1, 2), "V",
                             now=_ts(OCT[2], 15))
    assert only_ab["verdict"] == "no-data" and "meta.arm 'new' is not an arm of D47 (1 round(s), 10 row(s))" in only_ab["why"]


def test_d60_counts_an_excluded_round_once_whatever_reasons_its_rows_fall_under():
    """D60: "the card prints how many were excluded". One hand-run round (meta.seed 3001, arm_by explicit) whose rows
    fall under two reasons -- 4 with a marker run_config, 6 without -- is ONE excluded round, listed under both
    reasons. The first build summed the per-reason counts and printed 2."""
    rows = _round_rows("composites", OCT[0], 4, 0, 3001, by="explicit", run_config="ambiguous", tag="m")
    rows += _round_rows("composites", OCT[0], 6, 1, 3001, by="explicit")
    out = B.compare_arms(rows, "V", now=_ts(OCT[2], 15))
    assert {w: e["rounds"] for w, e in out["excluded"]["by_reason"].items()} == {
        "meta.arm_by 'explicit': not assigned by the randomiser (D60)": 1, "run_config 'ambiguous' forms no cohort (D30)": 1}
    assert (out["excluded"]["rounds"], out["excluded"]["rows"]) == (1, 10)
    assert "1 round(s) of it are excluded" in out["why"]


def test_compare_arms_stops_at_the_day_the_data_was_cut_on():
    """Draw5 scoring M7 (I13, ignoring data_through, survived): with rounds on 9 days and the copy cut on the 8th
    (data_through 10-08 09:00), the cut day and every day after are outside the read-out, like the unfinished day:
    7 shared days, look 1 taken through 10-07. Without data_through, 9 shared days."""
    rows = []
    for i, d in enumerate(OCT[:9]):
        rows += _day_of_rounds(d, [("gen", 1), ("composites", 1)], 20, 10 * i)
    now = _ts(OCT[12], 15)
    cut = B.compare_arms(rows, "V", now=now, data_through=_ts(OCT[7], 9))
    assert cut["excluded_uncovered_day"] == OCT[7] and cut["shared_days"] == OCT[:7]
    assert [x["last_day"] for x in cut["looks"]] == [OCT[6]]
    assert B.compare_arms(rows, "V", now=now)["shared_days"] == OCT[:9]


def test_the_read_out_looks_at_7_14_21_28_shared_days_and_daily_reads_add_none():
    """D55 and round 4 S1: daily reads at a fixed 0.05 accumulated 0.131 false verdicts by day 28. The read-out now looks
    only at 7, 14, 21 and 28 SHARED days (a day on which both arms ran a randomiser round): read every day of a month
    whose 10th ran A rounds only, the looks appear exactly at the 7th/14th/21st/28th shared day and never change after
    they are taken, and nothing after the 28th is read. No effect here (one event in one round of each arm a day)."""
    rows, rid = [], 0
    for d in OCT:
        pattern = [("composites", 1), ("composites", 0)] if d == OCT[9] else [
            ("gen", 1), ("gen", 0), ("composites", 1), ("composites", 0)]
        rows += _day_of_rounds(d, pattern, 40, rid)
        rid += 10
    shared = [d for d in OCT if d != OCT[9]]
    seen, first_seen = [], {}
    for i, d in enumerate(OCT):
        now = _ts(_next(d), 15)
        out = B.compare_arms([r for r in rows if r["dateCreated"] <= "%sT23" % d], "V", now=now)
        n_shared = sum(1 for s in shared if s <= d)
        want = sum(1 for k in B.ARMS_LOOK_DAYS if k <= n_shared)
        assert len(out["looks"]) == want, (d, n_shared)
        for x in out["looks"]:
            assert first_seen.setdefault(x["look"], x) == x                                  # a look never moves
        seen.append(out["verdict"])
        if want:
            assert [x["last_day"] for x in out["looks"]] == [shared[k - 1] for k in B.ARMS_LOOK_DAYS[:want]]
    assert seen == ["withheld"] * 28 + ["indistinguishable"] * 3
    two_days = [r for r in rows if r["dateCreated"] < OCT[2]]
    assert "2 shared whole ET day(s)" in B.compare_arms(two_days, "V", now=_ts(OCT[3], 15))["why"]


def test_a_crossing_stops_the_read_out_and_is_final():
    """D55: "an early stop is allowed only across a boundary". Every day both B rounds hold 3 events and both A rounds
    none (40 alphas each): at 7 shared days the exact relabelling p is 2 / 6^7 = 7.1e-6, under look 1's nominal 5.15e-5,
    so the read-out stops there "better" -- read again at 20 days it is still look 1's verdict, with no second look."""
    rows = []
    for i, d in enumerate(OCT[:20]):
        rows += _day_of_rounds(d, [("gen", 3), ("gen", 3), ("composites", 0), ("composites", 0)], 40, 10 * i)
    for d_last in (OCT[6], OCT[19]):
        out = B.compare_arms([r for r in rows if r["dateCreated"] <= "%sT23" % d_last], "V", now=_ts(_next(d_last), 15))
        assert out["verdict"] == "better" and [x["look"] for x in out["looks"]] == [1]
        assert out["looks"][0]["p_value"] <= B.ARMS_NOMINAL_P[0] and "stops here" in out["why"]


def test_the_obrien_fleming_boundary_is_re_derived_two_ways():
    """D55: the boundary constant, re-derived here and not taken from the module's comment. Way 1: the
    Armitage-McPherson-Rowe recursion (Simpson on 200 points) for the canonical Gaussian random walk crossing the
    constant partial-sum boundary C sqrt(4) at one of 4 looks: 0.05 at ARMS_OBF_C, and C +- 0.002 bracket it. Way 2: a
    Monte Carlo of the walk (100,000 draws). Control: one look at 1.959964 crosses 0.05. The z boundaries and nominal
    p are the constant's own transforms."""
    def phi(x):
        return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

    def cross(c, looks, grid=200):
        b = c * math.sqrt(looks)
        h = 2 * b / grid
        xs = [-b + i * h for i in range(grid + 1)]
        w = [h / 3 * (1 if i in (0, grid) else 4 if i % 2 else 2) for i in range(grid + 1)]
        f = [phi(x) for x in xs]
        for _ in range(looks - 1):
            f = [sum(w[j] * f[j] * phi(x - xs[j]) for j in range(grid + 1)) for x in xs]
        return 1.0 - sum(w[i] * f[i] for i in range(grid + 1))
    assert cross(B.ARMS_OBF_C, 4) == pytest.approx(0.05, abs=2e-5)
    assert cross(B.ARMS_OBF_C - 0.002, 4) > 0.05 > cross(B.ARMS_OBF_C + 0.002, 4)
    assert cross(1.959964, 1) == pytest.approx(0.05, abs=1e-6)
    rng, hits, n = random.Random(20260924), 0, 100000
    for _ in range(n):
        s = 0.0
        for k in range(1, 5):
            s += rng.gauss(0.0, 1.0)
            if abs(s) >= B.ARMS_OBF_C * 2.0:
                hits += 1
                break
    assert abs(hits / n - 0.05) < 4 * math.sqrt(0.05 * 0.95 / n), hits / n
    assert B.ARMS_LOOK_DAYS == (7, 14, 21, 28) and B.MIN_SHARED_DAYS == 7
    assert [round(z, 4) for z in B.ARMS_BOUNDARY_Z] == [4.0486, 2.8628, 2.3375, 2.0243]
    assert [float("%.4g" % p) for p in B.ARMS_NOMINAL_P] == [5.153e-05, 0.004199, 0.01942, 0.04294]
    assert "5.153e-05/0.004199/0.01942/0.04294" in B.ARMS_DESIGN["looks"]


#: D54's placebo input: the desk's OWN rounds. Every (ET day, meta.seed) round of the Mac journal copy
#: state/layered/runs/forge.jsonl (sha256 cb2960ea30efe80a..., mtime 2026-09-22T16:05:13-04:00, so 09-22 is not whole)
#: over its whole days, the last row per alpha, scored rows only; each entry "k/n/o" = D24 events and scored alphas
#: in USA/d1, and scored alphas in every other cell, which hold no event. DERIVED 2026-09-24 TWICE and compared
#: equal (scratchpad d6s_ev/census_a.py through this module's read_journal / quota_day_of_row / cell_of /
#: clears_every_binding_check; census_b.py by plain json with its own ET conversion, last-row rule and literal check
#: names). 187 rounds, 9 days, 37 events, 31,039 scored -- the counts round 3 and 4 F1 used. Embedded so the placebo
#: runs where the journal is not (the hosted CI tier).
DESK_ROUNDS = {
    "2026-09-04": ("0/0/197 0/0/290 0/0/300 0/0/80 0/0/100 0/0/60 0/0/60 0/0/50 0/0/60 0/0/80 0/0/60 0/0/300 "
                   "0/40/0 0/80/0 0/40/0 0/40/0 0/80/0 0/40/0 0/40/0 0/40/0 0/0/200 0/40/0 2/58/0 0/40/0 0/100/0 "
                   "0/40/0 0/140/154 1/140/70"),
    "2026-09-05": ("0/140/160 0/140/160 0/140/160 0/140/5 0/140/150 0/140/160 3/140/160 0/140/160 1/140/160 "
                   "2/140/160 0/140/160 0/140/100"),
    "2026-09-06": ("0/4/0 0/11/0 0/5/0 1/132/20 0/57/0 1/81/0 0/102/0 0/93/0 3/134/0 3/149/70 0/19/0 0/56/0 "
                   "0/64/0 0/140/160 1/79/0 0/140/71 1/18/0 0/84/0 0/4/0 0/75/0 2/145/70 0/119/0 0/124/0 "
                   "0/139/160 0/140/68 0/120/180 0/140/160 0/140/160 0/100/190 0/120/180 0/120/180 0/120/180 "
                   "0/1/0 0/2/0"),
    "2026-09-07": ("0/160/140 0/180/120 0/180/120 0/180/120 0/160/140 0/180/120 0/180/100 0/180/100 0/180/60 "
                   "0/180/60 0/180/60 0/289/0 0/290/0 0/270/0 0/290/0 0/300/0 0/299/0 0/230/0"),
    "2026-09-08": ("0/180/60 0/179/80 0/180/59 0/180/80 0/180/100 0/170/80 0/180/80 0/180/80 0/240/60 0/290/0 "
                   "0/298/0 0/290/0 0/270/0 0/250/0 0/210/0 0/200/0 0/210/0 0/210/0 0/210/0 0/210/0"),
    "2026-09-09": ("0/6/0 0/2/0 0/2/0 0/14/0 0/2/0 0/2/0 0/2/0 0/12/0 0/14/0 0/8/0 0/2/0 0/12/0 0/10/0 0/6/0 "
                   "0/8/0 0/6/0 0/2/0 0/10/0 0/6/0 0/14/0 0/4/0 0/4/0 0/6/0 0/4/0 0/8/0 0/14/0 0/6/0 0/6/0 0/8/0 "
                   "0/2/0 0/8/0 0/8/0 0/10/0 0/18/0 0/6/0 0/8/0 0/222/0 0/202/0 0/206/0 0/214/0 0/220/0 0/296/0 "
                   "1/270/30 0/270/30 0/270/30 0/268/30 0/270/30 0/270/30 0/199/20 0/96/0 0/260/30 0/99/0 "
                   "0/270/30 0/100/0 0/1/0 0/1/0 0/2/0"),
    "2026-09-10": ("4/270/30 7/270/30 0/270/30 0/270/30 2/260/30"),
    "2026-09-11": ("0/270/30 0/270/30 0/270/30 1/270/30"),
    "2026-09-20": ("0/270/30 0/250/30 0/270/30 0/220/30 0/250/30 1/230/30 0/259/30 0/270/30 0/270/30"),
}


def _desk_rounds(rng, days=None, first=0):
    """The desk's rounds as _arms_decision takes them, each round's arm by a fair coin (D53's 50/50); `days` = the
    source day of each synthetic day, in order (default: the 9 real days, each once), labelled from `first`."""
    out = []
    for i, src in enumerate(days or sorted(DESK_ROUNDS), first):
        d = "d%03d" % i
        for x in DESK_ROUNDS[src].split():
            k, n, o = map(int, x.split("/"))
            out.append((d, B.ARMS[rng.random() < 0.5], [(d, "USA/d1", k, n)] * bool(n) + [(d, "other", 0, o)] * bool(o)))
    return out


def _shared_days(rounds):
    arms = collections.defaultdict(set)
    for d, a, _ in rounds:
        arms[d].add(a)
    return sorted(d for d, a in arms.items() if len(a) == 2)


def _alpha_unit_verdict(rounds):
    """The decision D47 first registered and D54 replaced, rebuilt here as the CONTROL: the exact test stratified by
    (day, cell) with the ALPHA as the unit, better / worse at 0.05 when every cell with an event agrees, withheld under
    5 shared days."""
    st = collections.defaultdict(lambda: [0, 0, 0, 0])
    for d, a, entries in rounds:
        for dd, c, k, n in entries:
            st[(dd, c)][0 if a == B.ARMS[0] else 2] += k
            st[(dd, c)][1 if a == B.ARMS[0] else 3] += n
    shared = {s: v for s, v in st.items() if v[1] and v[3]}
    excess, events = collections.defaultdict(float), collections.Counter()
    for (d, c), (ka, na, kb, nb) in shared.items():
        excess[c] += kb - (ka + kb) * nb / (na + nb)
        events[c] += ka + kb
    dirs = {"B higher" if excess[c] > 0 else "B lower" if excess[c] < 0 else "equal" for c in events if events[c]}
    if len({d for d, _ in shared}) < 5 or B.stratified_rate_test_p(list(shared.values())) > 0.05 or len(dirs) != 1:
        return "no verdict"
    return {"B higher": "better", "B lower": "worse"}.get(dirs.pop(), "no verdict")


FALSE_VERDICT = ("better", "worse")


def _placebo_desk_days(seed, draws):
    """On the desk's 9 real days, each draw reassigns every round's arm by a coin and reads, on the SAME draw: (P0) the
    read-out exactly as compare_arms() runs it (D55's looks -- on 9 days only look 1, at 7 shared days, can happen);
    (P1) the round-unit test at ONE look at 0.05 over every shared day, round 4 F1's placebo; (P1c) the alpha-unit
    decision D54 replaced. The share of draws reading better or worse, each."""
    rng, got = random.Random(seed), [0, 0, 0]
    for _ in range(draws):
        rounds = _desk_rounds(rng)
        got[0] += B._arms_decision(rounds)["verdict"] in FALSE_VERDICT
        got[1] += B._arms_decision(rounds, looks=(len(_shared_days(rounds)),), nominal=(0.05,))["verdict"] in FALSE_VERDICT
        got[2] += _alpha_unit_verdict(rounds) in FALSE_VERDICT
    return tuple(x / draws for x in got)


def _placebo_desk_bootstrap(seed, draws, shared=28):
    """(P2) The read-out over D55's four looks on the desk's rounds: the desk has 9 whole days, so each draw deals whole
    real days with replacement, each round's arm by a coin, until `shared` shared days exist, then runs the read-out
    exactly as compare_arms() does. The share reading better or worse."""
    rng, names, bad = random.Random(seed), sorted(DESK_ROUNDS), 0
    for _ in range(draws):
        rounds, n = [], 0
        while n < shared:
            day = _desk_rounds(rng, [rng.choice(names)], len({d for d, _, _ in rounds}))
            n += len({a for _, a, _ in day}) == 2
            rounds += day
        bad += B._arms_decision(rounds)["verdict"] in FALSE_VERDICT
    return bad / draws


def _clustered_rounds(rng, days, rounds=10, phi=11.0, shape=0.3, ratio=1.0, n=280, base=4.1 / 2800):
    """Synthetic randomised rounds with BOTH clusterings round 3 and 4 F1 measured: each ET day draws G ~ Gamma(k, 1/k),
    k = mu / (phi - 1), mu = rounds x n x base = 4.1 events a day; each ROUND draws C ~ Gamma(shape, 1/shape); a round
    of n alphas in USA/d1 counts Poisson(n base G C, x ratio in B), its arm a fair coin (D53). Arithmetic, not a
    measurement: the day totals' dispersion is phi + (n base)^2 rounds / shape x (1 + 1/k) / mu = 11 + 4.7 = 15.7 (F1
    measured 11.34 in USA/d1); the round-weighted within-day ratio is about (1 + n base (1 + 1/k) / shape) (R - 1) / R
    = 5.7 x 0.9 = 5.1 -- MEASURED 5.09 over the pinned draws, against the desk's 2.235, so this generator clusters
    inside rounds MORE than the desk (a harder case, not a copy of it). Draw5 scoring M24: the draw-5 generator's
    docstring said 4.1 events a day and drew about 3.5; M25: it had no within-round clustering."""
    mu = rounds * n * base
    k = mu / (phi - 1)
    out = []
    for d in range(days):
        g = rng.gammavariate(k, 1 / k)
        for _ in range(rounds):
            arm = B.ARMS[rng.random() < 0.5]
            lam = n * base * g * rng.gammavariate(shape, 1 / shape) * (ratio if arm == B.ARMS[1] else 1.0)
            out.append(("d%03d" % d, arm, [("d%03d" % d, "USA/d1", _poisson_draw(rng, lam), n)]))
    return out


def _placebo_clustered(seed, draws, days=28):
    """(P3) the read-out on _clustered_rounds under NO effect, and (P3c) the alpha-unit control on the same draws; with
    the generator's realised round-weighted ratio and between-day dispersion, each averaged over the draws."""
    rng, bad, old, ratio, disp = random.Random(seed), 0, 0, [], []
    for _ in range(draws):
        rounds = _clustered_rounds(rng, days)
        bad += B._arms_decision(rounds)["verdict"] in FALSE_VERDICT
        old += _alpha_unit_verdict(rounds) in FALSE_VERDICT
        ratio.append(B._round_clustering(rounds)["ratio"])
        per_day = collections.defaultdict(lambda: [0, 0])
        for d, _, [(_, _, k, n)] in rounds:
            per_day[d][0] += k
            per_day[d][1] += n
        disp.append(B._dispersion(per_day) or 0.0)
    return bad / draws, old / draws, statistics_mean(ratio), statistics_mean(disp)


def statistics_mean(xs):
    return sum(xs) / len(xs)


def test_the_desks_own_rounds_are_what_the_fixture_says():
    """The placebo's input, pinned: 187 rounds, 37 events, all in USA/d1, 31,039 scored (round 3 F1's counts), and
    the round-clustering diagnostic that makes the round the unit: the round-weighted statistic 72.845 against a
    null mean of 32.594 when alphas are exchangeable, ratio 2.235. Second way (scratchpad d6s_ev/clustering_check.py,
    no benchmark code): 72.845 and 32.594 by its own closed form; 5,000 simulated deals of each day's events to its
    alphas gave a null mean of 32.465 and 4 of 5,000 at or above 72.845 (round 4 F1: 72.85 against 32.41, 4,000)."""
    units = [x.split("/") for v in DESK_ROUNDS.values() for x in v.split()]
    assert (len(DESK_ROUNDS), len(units)) == (9, 187)
    assert sum(int(k) for k, _, _ in units) == 37 and sum(int(n) + int(o) for _, n, o in units) == 31039
    rounds = _desk_rounds(random.Random(1))
    assert B._round_clustering(rounds) == {"sum_sq_excess": 72.845, "null_mean_if_alphas_exchangeable": 32.594,
                                           "ratio": 2.235}


def test_the_placebo_on_the_desks_own_rounds_reads_at_most_five_percent():
    """D54: "before any read-out a placebo on the desk's own rounds must show a false-verdict rate <= 5 %"; round 4 F1:
    the alpha-unit decision read better / worse 0.155 of the time when the real rounds were reassigned at random.
    SEEDS AND DRAWS DECLARED BEFORE ANY RUN WITH THEM (scratchpad d6s_ev/placebo_declaration.txt, 2026-09-24T04:19Z):
    desk days 20260927 x 4,000 draws; desk days resampled to 28 shared days 20260928 x 2,000. Each rate is pinned AS
    MEASURED, in benchmark.ARMS_PLACEBO (the card prints it). MEASURED: the read-out on the 9 real days 0.00025 -- at
    most 0.05, D54's gate as written, but only look 1 is reachable in 9 days; one look at 0.05 0.052 and the four looks
    on resampled days 0.0525 -- ABOVE 0.05 by less than one standard error (0.0035, 0.0049): the test is calibrated at
    its nominal level (a 16,000-draw diagnostic: 0.0517 with the fixed permutation seed, 0.0498 with it varied), so
    '<= 5 %' is not shown there, and those two are held here only to "not above 0.05 beyond two standard errors", the
    tolerance round 4 F1's own test ask used ("at most ~0.06"). Which reading holds is Khoa's (open_ticks). The
    alpha-unit control on the same draws must read well above 0.05, or the placebo has no teeth (0.1565)."""
    read_out, one_look, alpha_unit = _placebo_desk_days(20260927, 4000)
    boot = _placebo_desk_bootstrap(20260928, 2000)
    got = {"desk_days_read_out": read_out, "desk_days_one_look": one_look, "desk_days_alpha_unit_control": alpha_unit,
           "desk_days_resampled_to_28_read_out": boot}
    assert got == {k: B.ARMS_PLACEBO[k] for k in got}, got
    assert read_out <= 0.05 and alpha_unit > 0.12, got
    assert one_look <= 0.05 + 2 * math.sqrt(0.05 * 0.95 / 4000) and boot <= 0.05 + 2 * math.sqrt(0.05 * 0.95 / 2000), got


def test_the_read_out_holds_its_size_when_events_cluster_inside_rounds_and_days():
    """Round 4 F1's test ask (a generator with within-round clustering) and S1's (the cumulative false-verdict rate of
    the read-out as a daily reader meets it, at most 0.05; daily looks at a fixed 0.05 read 0.131 by day 28). Under NO
    effect, 28 days, D55's four looks -- a daily reader sees exactly these (test_the_read_out_looks_at_7_14_21_28_...).
    Teeth: the generator's realised clustering (round-weighted ratio and between-day dispersion well above 1), and the
    alpha-unit control on the same draws reading well above 0.05. SEED AND DRAWS DECLARED BEFORE ANY RUN WITH THEM
    (placebo_declaration.txt): 20260929 x 1,000. Pinned as measured in benchmark.ARMS_PLACEBO."""
    bad, old, ratio, disp = _placebo_clustered(20260929, 1000)
    assert (bad, old) == (B.ARMS_PLACEBO["clustered_generator_28_read_out"],
                          B.ARMS_PLACEBO["clustered_generator_alpha_unit_control"]), (bad, old, ratio, disp)
    assert bad <= 0.05 and old > 0.10 and ratio > 1.5 and disp > 6.0, (bad, old, ratio, disp)
    rng = random.Random(1)
    sequential = [(d, B.ARMS[int(d[1:]) >= 14], e) for d, _, e in _clustered_rounds(rng, 28)]   # the D33 layout
    assert B._arms_decision(sequential)["verdict"] == "withheld"                                    # no shared day


def test_the_arms_design_was_registered_before_any_arm_row():
    """D47's design, amended by D54, D55 and D60 BEFORE any arm row existed: its comment records the host count (0 rows
    with arm gen / composites, arm_by, gen_route or round at 04:20 UTC 2026-09-24) the amendment was written after. The
    estimand is D24's, unchanged. The minimum detectable ratio is withheld, not computed on the wrong unit."""
    assert B.ARMS == ("composites", "gen") and B.ARMS_ASSIGNED_BY == "randomiser" and B.ARMS_FRESH_ROUTE == "fresh"
    assert B.ARMS_DESIGN["estimand"] == B.ESTIMAND["name"] and B.ARMS_DESIGN["alpha"] == B.ESTIMAND["alpha"]
    assert "the ROUND" in B.ARMS_DESIGN["unit"] and "permutation test of the arm labels" in B.ARMS_DESIGN["test"]
    src = " ".join(open(B.__file__).read().split())
    assert ("2026-09-24T04:20Z: 43,382 lines, 0 carrying arm \"gen\" or #: \"composites\", 0 carrying arm_by, 0 carrying "
            "gen_route, 0 carrying round") in src
    assert not hasattr(B, "arms_mdr") and "UNMEASURED" in B.ARMS_MDR_NOTE
    rows = [r for i, d in enumerate(OCT[:2]) for r in _day_of_rounds(d, [("gen", 1), ("composites", 1)], 5, 10 * i)]
    assert B.compare_arms(rows, "V", now=_ts(OCT[3], 15))["minimum_detectable_ratio"] == {"note": B.ARMS_MDR_NOTE}


# ------------------------------------------------------------ D56: PBO on a generated family pool
def test_pbo_insufficient_on_a_generated_pool_is_not_applicable():
    """D56 (Khoa, 2026-09-24; round 4 S5, pf_e3_pbo_unproven.py): a generated submission in a D38 family pool of 3 read
    PBO "insufficient (< 20 trials)", pass None, and so UNPROVEN, floor unmet, and a cost at rank level 1 -- for every
    generated alpha, since such a pool holds at most 12 settings. Now it reads NOT APPLICABLE: printed UNMEASURED, left
    out of the status and the gate coverage. The truth table, every other gate passing: only the generated alpha with
    that status moves; a library alpha, a 'pending' pool and no status stay unproven; a failed PBO stays refuted."""
    def card(hyp, pbo_pass, pbo_status):
        rows, scored, corr, hist, curves = _cohort([("P", "g1", "2026-09-10", 0.1)])
        for r in rows:
            r["meta"] = dict(r["meta"], hypothesis=hyp)
        scored["g1"] = {"dsr": 0.97, "pbo_pass": pbo_pass, "pbo_status": pbo_status}
        return B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-30", 15), since="2026-09-10",
                            until="2026-09-11", meaning=[_mrow()], axis3=AXIS3_MET)
    insufficient = "insufficient (< 20 trials)"
    cases = {("gen:fam_x", None, insufficient): "proven", ("h_ok", None, insufficient): "unproven",
             ("gen:fam_x", None, "pending"): "unproven", ("gen:fam_x", None, None): "unproven",
             ("gen:fam_x", False, "ok"): "refuted", ("gen:fam_x", True, "ok"): "proven"}
    for (hyp, ok, status), want in cases.items():
        a1 = card(hyp, ok, status)["axes"]["axis1_product"]
        assert a1["detail"][0]["status"] == want, (hyp, ok, status)
    c = card("gen:fam_x", None, insufficient)
    a1, d = c["axes"]["axis1_product"], c["axes"]["axis1_product"]["detail"][0]
    assert d["gates"]["pbo_pass"] is None and set(d["not_applicable"]) == {"pbo_pass"}
    assert a1["floor_met"] is True and a1["gate_coverage"] == 1.0 and c["rank"]["refuted_or_unproven_submitted"] == 0
    text = B.render(c)
    assert "pbo_pass UNMEASURED: not applicable (D56)" in text and "unmeasured: pbo_pass" not in text
    assert "D56 as read here" in {t["item"] for t in c["open_ticks"]}


# ------------------------------------------------------------ D57: level 1 at equal post-creation lag
def test_rank_cmp_counts_level_one_at_equal_post_creation_lag():
    """D57 (Khoa, 2026-09-24; round 4 S2, s2_d49.py): two identical cohorts, one unproven alpha each POSTed 20 days
    after creation, created 09-10 (V1) and 09-20 (V2), graded 10-06 with both horizons final: level 1 read 1 against
    0 and rank_cmp(V2, V1) = -1, only because V1's POST had had time to happen. rank_cmp now counts both at the shorter
    post-creation exposure -- V2's, 10-06 15:00 less 09-21 00:00 = 15.625 days -- so V1's lag-20 POST is not counted
    and they tie. Graded 10-11 both POSTs are in (1 and 1). Control, lag 10: counted on both at every date. A real
    difference inside the common lag still ranks."""
    def card(day, lag, graded):
        return _card([("U", "u_" + day, day, lag)], _ts(graded, 15), since=day, until=_next(day), axis3=AXIS3_MET)
    v1, v2 = card("2026-09-10", 20.0, "2026-10-06"), card("2026-09-20", 20.0, "2026-10-06")
    assert (v1["rank"]["refuted_or_unproven_submitted"], v2["rank"]["refuted_or_unproven_submitted"]) == (1, 0)
    assert v1["rank"]["horizon_final"] and v2["rank"]["horizon_final"]
    assert v2["rank"]["post_exposure_days"] == pytest.approx(15.625) and v1["rank"]["level1_post_lag_days"] == [
        pytest.approx(20.0)]
    assert B.rank_cmp(v2, v1) == 0 == B.rank_cmp(v1, v2)                                    # round 4 S2: was -1
    assert B.rank_key(v1)[1] == 1 and B.rank_key(v1, 15.625)[1] == 0 and B.rank_key(v1, 20.0)[1] == 1
    assert B.rank_cmp(card("2026-09-20", 20.0, "2026-10-11"), card("2026-09-10", 20.0, "2026-10-11")) == 0
    for graded in ("2026-10-06", "2026-10-09"):
        a, b = card("2026-09-10", 10.0, graded), card("2026-09-20", 10.0, graded)
        assert (a["rank"]["refuted_or_unproven_submitted"], b["rank"]["refuted_or_unproven_submitted"]) == (1, 1)
        assert B.rank_cmp(b, a) == 0
    unposted = _card([("U", "u_n", "2026-09-20", None)], _ts("2026-10-06", 15), since="2026-09-20",
                     until=_next("2026-09-20"), axis3=AXIS3_MET)
    assert B.rank_cmp(unposted, card("2026-09-10", 5.0, "2026-10-06")) == -1
    assert B.rank_cmp(_levels(0, 0.1, 1.0), _levels(1, 0.1, 1.0)) == -1                      # hand-built: raw counts


def test_level_one_is_equalised_at_the_lag_the_data_can_show_and_only_when_both_cards_can_be():
    """D57, the two readings the first build got wrong (found 2026-09-24 by this builder, re-running round 4 S2's pair).
    (1) The exposure is measured to seen_until, D27's clock: V2's copy is cut 10-05 12:00 (data_through), so its own
    POST of 10-07 is not in its data and it reads level 1 = 0; graded 10-11 with the exposure measured to `now` (20.625
    days) V1's lag-17 POST counted and rank_cmp(V2, V1) read -1 -- round 4 S2's bias again. To seen_until the exposure
    is 10-05 12:00 less 09-21 00:00 = 14.5 days: neither POST counts, and they tie. (2) A card that carries no lags (a
    hand-built one, or one recorded before D57) cannot be equalised: both are counted raw. The first build truncated
    only the card that had lags: a card whose lag-20 POST lies beyond its own exposure (15.625 days, from its newest
    day) read 0 against 1 for a copy of its own levels without the lags, and the copy ranked BELOW it."""
    now = _ts("2026-10-11", 15)
    v1 = _card([("U", "u_v1", "2026-09-10", 17.0)], now, since="2026-09-10", until="2026-09-11", axis3=AXIS3_MET)
    v2 = _card([("U", "u_v2", "2026-09-20", None)], now, since="2026-09-20", until="2026-09-21", axis3=AXIS3_MET,
               data_through=_ts("2026-10-05", 12))
    assert v2["rank"]["horizon_final"] and v2["rank"]["post_exposure_days"] == pytest.approx(14.5)
    assert v1["rank"]["post_exposure_days"] == pytest.approx(30.625)
    assert B.rank_cmp(v2, v1) == 0 == B.rank_cmp(v1, v2)
    late = _card([("U", "u_old", "2026-09-10", 20.0), ("U", "u_new", "2026-09-20", None)], _ts("2026-10-06", 15),
                 since="2026-09-10", until="2026-09-21", axis3=AXIS3_MET)       # exposure from 09-20: 15.625 days
    hand = {"rank": {k: v for k, v in late["rank"].items() if k not in ("level1_post_lag_days", "post_exposure_days")}}
    assert late["rank"]["refuted_or_unproven_submitted"] == 1 and late["rank"]["post_exposure_days"] < 20.0
    assert B.rank_cmp(hand, late) == 0 == B.rank_cmp(late, hand)


# ------------------------------------------------------------------ draw-5 scoring MINORs
def test_dora_is_pinned_for_every_watch_outcome():
    """Draw5 scoring M1 (C01, C02, C07 survived): three pushes and one watch row of each outcome tools/deploy.py can
    write. Deploys stay 3 and 0.75 a week whatever the watch says (a watch row is never a deploy); the change-failure
    rate is 1/3 for the four outcomes that say the first round failed, 0 for the other three."""
    now = _ts("2026-09-20", 15)
    u, v, w = _deploy("U", "2026-09-01"), _deploy("V", "2026-09-09"), _deploy("W", "2026-09-12")
    for outcome, cfr in (("watch_rolled_back", 0.333), ("watch_rollback_failed", 0.333), ("watch_units_down", 0.333),
                         ("watch_not_rolled_back", 0.333), ("watch_ok", 0.0), ("watch_timeout", 0.0),
                         ("watch_interrupted", 0.0)):
        d = B.dora([u, v, w, _watch(outcome, v, prev_pv="U", prev_version="tree-U")], now=now)
        assert (d["deploys"], d["deploys_per_week"], d["change_failure_rate"]) == (3, 0.75, cfr), outcome


def test_a_day_one_host_held_whole_counts_whatever_another_host_did():
    """Draw5 scoring M3 (A19, "part beats whole", survived): on 09-12 the loop's host holds (V, r1) all day while a
    second host's row names r1 at 15:00 -- a part day there. The day COUNTS (some host held the cohort all day), as the
    corrected docstring says; the second host's later days count too, which is the stated stale-host consequence."""
    now, ledger = _ts("2026-09-20", 15), [_deploy("V", "2026-09-09")]
    log = [_log(_ts("2026-09-09", 11), "V", "r1"), _log(_ts("2026-09-12", 15), "V", "r1", host="mac")]
    e = B.cohort_live_days(ledger, log, ("V", "r1"), now)
    assert e["days"] == ["2026-09-%02d" % d for d in range(10, 20)] and e["excluded_run_config_days"] == []
    doc = " ".join(B.cohort_live_days.__doc__.split())
    assert "(a dry run on another machine must not end the loop's run_config)" not in doc     # the false sentence
    assert "whatever any other host did on d" in doc
    assert "REDUNDANT" in doc and "EVEN a day the log attributes to another run_config" in doc      # M4, M19


def test_formula_sha_keeps_whitespace():
    """Draw5 scoring M5 (E08, strip, survived): the meaning ledger's key is the sha256 of the formula text as the
    journal holds it, no normalisation -- ' rank(x)' and 'rank(x)' are different keys."""
    assert B.formula_sha(" rank(x)") != B.formula_sha("rank(x)") != B.formula_sha("rank(x) ")
    assert B.formula_sha("rank(x)") == hashlib.sha256(b"rank(x)").hexdigest()


def test_the_ledger_loaders_open_their_path_as_named(tmp_path):
    """Draw5 scoring M11 (V5): load_run_config_log, load_meaning and load_deploys globbed their path, so a ledger under
    a directory whose name holds `[1]` read 0 rows while is_file() was True."""
    import json
    d = tmp_path / "state[1]"
    (d / "state").mkdir(parents=True)
    row = {"at": 1.0, "pipeline_version": "V", "run_config": "r", "host": "h"}
    for name in ("log.jsonl", "meaning.jsonl", "state/deploys.jsonl"):
        (d / name).write_text("not json\n" + json.dumps(row) + "\n")
    assert B.load_run_config_log(d / "log.jsonl") == [row] and B.load_meaning(d / "meaning.jsonl") == [row]
    assert B.load_deploys(d) == [row] and B.load_meaning(d / "absent.jsonl") is None and B.load_deploys(tmp_path) is None


def test_the_draw5_texts_say_what_the_code_does():
    """Draw5 scoring M17, M18, M20-M22, M27, each sentence against the code. M17: the coverage-gap note counts the
    empty days that are among the rate's days (a version card whose live days end before the gap counts fewer)."""
    rows = [_journal_row("a", "2026-09-10", version="V"), _journal_row("b", "2026-09-12", version="V")]
    kw = dict(now=_ts("2026-09-21", 15), since="2026-09-10", data_through=_ts("2026-09-20", 23))
    gap = B.build_from(rows, {}, {}, [], {}, {}, **kw)["window"]["coverage_gap"]
    assert gap["in_rate_days"] == 7 and "7 of those day(s) are among this card's rate days" in gap["note"]
    live = B.build_from(rows, {}, {}, [], {}, {}, version="V", deploys=[_deploy("V", "2026-09-09"),
                                                                        _deploy("W", "2026-09-14")], **kw)["window"]
    assert live["coverage_gap"]["in_rate_days"] == 1                                       # only 09-13 was V's
    assert "a day the run_config changed" in live["exposure"]["graded_by_axis1_not_in_rate"]           # M18
    flat = lambda s: " ".join(s.split())                                                   # noqa: E731
    src = flat(open(B.__file__).read())
    assert "the file does not exist, and no runner writes it yet" not in src                     # M20: the false text
    assert "note_run_config() -> record_run_config()" in src
    rows2 = _arm("A", A_DAYS, 1000, [2, 1, 1, 1, 1]) + _arm("B", B_DAYS, 1000, [4, 4, 4, 3, 3])
    design = B.compare(rows2, [], {}, {}, {}, {}, "A", "B", now=_ts("2026-09-20", 15))["design"]
    assert "one rate per arm across days" in design and "independent alphas" not in design       # M21
    assert "0.540 and 0.547" in B.COMPARE_IS_NOT_GATE3 and "0.561" in B.COMPARE_IS_NOT_GATE3      # M22
    assert "D52: it FAILS only when EVERY leg is crowded" in src                            # M27
    assert "recorded rather than relabelled" in flat(B.compare.__doc__)                     # M16


# --------------------------------------------------------------------- round 3 S8: the meaning reader
def test_the_meaning_reader_takes_the_earliest_row_of_the_alphas_own_formula():
    """Round 3 S8 (v4_gen.py): the reader believed any row. A row carrying another formula's sha read PROVEN, a row
    scored in 1970 read PROVEN, and "G5 False, then a later all-true row, same sha" read PROVEN. Now the row must carry
    the sha256 of the alpha's own formula text, be scored after the alpha was created and by `now`, and the earliest
    such row decides."""
    def gate(meaning):
        d = _gen_card(meaning)["axes"]["axis1_product"]["detail"][0]
        return d["gates"]["hypothesis_standard_8of8"], d["status"]
    other = hashlib.sha256(b"rank(someone_else)").hexdigest()
    assert gate([_mrow(sha=other)]) == (None, "unproven")
    assert gate([_mrow(at=1)]) == (None, "unproven")
    assert gate([_mrow(G5=False), _mrow(at=_ts("2026-09-12", 9))]) == (False, "refuted")
    assert gate([_mrow(at=_ts("2026-09-12", 9)), _mrow(G5=False, at=_ts("2026-09-13", 9))]) == (True, "proven")
    assert gate([_mrow(sha=["not", "a", "sha"])]) == (None, "unproven")                   # was a TypeError
    note = _gen_card([_mrow(sha=other)])["axes"]["axis1_product"]["detail"][0]["standard_route"]["note"]
    assert "this alpha's own formula (formula_sha)" in note
    assert B.formula_sha("rank(g1)") == hashlib.sha256(b"rank(g1)").hexdigest() and B.formula_sha(None) is None
    f = {"g1": (B.formula_sha("rank(g1)"), _ts("2026-09-10"))}
    first, second = _mrow(G6=False), _mrow()                                               # same time: file order
    assert B.meaning_index([first, second], _ts("2026-09-20"), f)["g1"] is first
    assert B.meaning_index([_mrow()], _ts("2026-09-20"), {}) == {}                        # no journal formula: no row


# ------------------------------------------------------------ round 3 S10: the journal, streamed and reduced
def _big_row(alpha, day, junk_kb, **kw):
    row = dict(_journal_row(alpha, day), sharpe=1.2, raw="x" * (junk_kb * 1024), pnl=list(range(50)), **kw)
    row["settings"] = dict(row["settings"], universe="TOP3000", decay=4, instrumentType="EQUITY", language="FASTEXPR")
    row["meta"] = {"pipeline_version": "V", "hypothesis": "h", "legs": ["a", "b"], "composite": 1}
    row["checks"] = [{"name": "LOW_SHARPE", "result": "FAIL", "limit": 1.58, "value": 1.2},
                     {"name": "PROD_CORRELATION", "result": "PENDING", "limit": 0.7, "value": None}]
    return row


def test_the_journal_is_read_line_by_line_reduced_and_as_named(tmp_path, monkeypatch):
    """Round 3 S10 (the reader's half): build() held every parsed line of the journal before keeping the last row per
    alpha, with every field -- 741 MB peak RSS on the Mac's 115.7 MB journal. read_journal() streams, keeps the last
    row per alpha reduced to JOURNAL_KEEP*, and shares identical checks. Pinned by the reader's own peak (tracemalloc):
    300 rows of 40 KB each (12 MB of text) must peak far under the text's size -- the old reader held it all. The path
    is read as named (harvest.read_jsonl globbed it: forge[1].jsonl read 0 rows)."""
    import json
    import tracemalloc
    _quiet_disk(monkeypatch)
    rows = [_big_row("a%03d" % (i % 150), "2026-09-%02d" % (10 + i // 150), 40) for i in range(300)]
    path = tmp_path / "forge[1].jsonl"
    path.write_text("not json\n[1, 2]\n" + "".join(json.dumps(r) + "\n" for r in rows))
    tracemalloc.start()
    try:
        x = B.load_inputs(journal=path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 3_000_000, peak                                   # the file is 12.4 MB
    got = {r["alpha"]: r for r in x["rows"]}
    assert len(x["rows"]) == 150 and x["journal_exists"] is True
    assert got["a000"]["dateCreated"].startswith("2026-09-11")                            # the last row wins
    r = got["a000"]
    assert set(r) == {"alpha", "status", "dateCreated", "formula", "sharpe", "settings", "meta", "checks"}
    assert r["settings"] == {"region": "USA", "delay": 1, "universe": "TOP3000", "decay": 4}
    assert r["meta"] == {"pipeline_version": "V", "hypothesis": "h"}
    assert r["checks"][0] == {"name": "LOW_SHARPE", "result": "FAIL", "limit": 1.58}
    assert r["checks"][0] is got["a001"]["checks"][0]                                     # shared, not copied
    assert B.read_journal(tmp_path / "absent.jsonl") == ([], False) and B.read_journal(tmp_path) == ([], False)


def test_a_card_from_reduced_rows_equals_a_card_from_whole_rows(tmp_path):
    """The guard JOURNAL_KEEP's comment names: every reader of `rows` finds what it needs in the reduced row. Cards of
    every kind the fixtures here build -- a date card, a version card with deploys and a run_config log, generated
    alphas with meaning rows -- and compare() and compare_arms() read the same from whole and from reduced rows.
    (Re-derived once on the Mac's real journal as well: three date windows, identical JSON; 37 of 32,656 clearing.)
    Draw5 scoring M6 (F05, F07 survived): p1's second neighbour differs from it in TRUNCATION only, and two --ab rounds
    are told apart by meta.SEED only, so dropping either field from the reduced row changes a card; the randomiser's
    arm_by / round and the generator's gen_route (a neighbour round) are read by compare_arms the same way (D54)."""
    import json
    whole, scored, corr, hist, curves = _merge(_cohort([("P", "p1", "2026-09-10", 0.1), ("R", "r1", "2026-09-11", 0.1)], "V"),
                                               _cohort([("P", "q1", "2026-09-15", 0.1), ("U", "u1", "2026-09-16", 0.1)], "W"))
    for r in whole:
        r["checks"] = r["checks"] + [{"name": "SELF_CORRELATION", "result": "PASS", "limit": 0.6, "value": 0.1}]
        r["meta"]["run_config"] = "rc1"
        r["settings"] = dict(r["settings"], pasteurization="ON")
    gen = [dict(r, meta=dict(r["meta"], hypothesis="gen:f")) for r in _cohort([("P", "g1", "2026-09-12", 0.1)], "V")[0]]
    for r in gen:
        r["meta"]["run_config"] = "rc1"
    for r in whole:
        if r["alpha"] == "p1_n2":
            r["settings"] = dict(_settings(), truncation=0.05, pasteurization="ON")      # a truncation-only neighbour
    arms = [x for i, d in enumerate(OCT[:8]) for x in _day_of_rounds(d, [("gen", 2), ("composites", 1)], 20, 10 * i)]
    arms += _round_rows("gen", OCT[0], 3, 2, 0, route="neighbour")
    ab = [dict(x, meta={k: v for k, v in x["meta"].items() if k != "round"}) for x in
          _round_rows("new", OCT[1], 4, 1, 501) + _round_rows("new", OCT[1], 4, 1, 502)]
    whole += gen + arms + ab
    path = tmp_path / "j.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in whole))
    reduced, _ = B.read_journal(path)
    now = _ts("2026-10-10", 15)
    ledger = [_deploy("V", "2026-09-09"), _deploy("W", "2026-09-14")]
    log = [_log(_ts("2026-09-09", 11), "V", "rc1"), _log(_ts("2026-09-14", 11), "W", "rc1")]
    kw = dict(now=now, deploys=ledger, run_config_log=log, meaning=[_mrow(alpha="g1", at=_ts("2026-09-13", 9))],
              axis3=AXIS3_MET, host="h")

    def same(fn):
        return json.dumps(fn(whole), sort_keys=True, default=str) == json.dumps(fn(reduced), sort_keys=True, default=str)
    assert same(lambda rows: B.build_from(rows, scored, corr, hist, curves, STANDARD, **kw))
    for v in ("V@rc1", "W@rc1"):
        assert same(lambda rows: B.build_from(rows, scored, corr, hist, curves, STANDARD, version=v, **kw))
    assert same(lambda rows: B.compare(rows, hist, curves, STANDARD, scored, corr, "V@rc1", "W@rc1", now=now,
                                       deploys=ledger, run_config_log=log))
    arms_out = B.compare_arms(reduced, "V", now=now)
    assert same(lambda rows: B.compare_arms(rows, "V", now=now))
    assert arms_out["excluded"]["by_reason"]["meta.arm 'new' is not an arm of D47"] == {"rounds": 2, "rows": 8}
    assert arms_out["beside"]["gen/neighbour"]["scored_rows"] == 3 and len(arms_out["looks"]) == 1
    p1 = B.build_from(reduced, scored, corr, hist, curves, STANDARD, **kw)["axes"]["axis1_product"]["detail"]
    assert {d["alpha"]: d["neighbourhood"]["n"] for d in p1}["p1"] == 2                  # truncation read


# --------------------------------------------------- the drawing's findings 8-9: what a recorded card is
def test_a_recorded_card_names_its_cohort_and_need_not_be_rankable(tmp_path, monkeypatch, capsys):
    """01_architecture.md draw 4, section 1 ("What the judge would grade") and section 4 item 2: wq-judge.sh's
    `--record` recorded build(version=None), a date-window card that grades no version (D1, D14); and at the judge's
    00:30 ET clock every card it appends is unrankable. A recorded card must now name its cohort, and recording must
    not ask whether it can be ranked."""
    rows, scored, corr, hist, curves = _cohort([("P", "p1", "2026-09-10", 0.1)], "V")
    ledger = tmp_path / "cards.jsonl"
    dated = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-20", 15), host="h")
    with pytest.raises(ValueError, match="names no cohort"):
        B.record_card(dated, ledger)
    assert not ledger.exists()
    monkeypatch.setattr(B, "CARDS_LEDGER", ledger)
    monkeypatch.setattr(B, "build", lambda **k: dated)
    with pytest.raises(SystemExit):
        B.main(["--record", "--no-drill"])
    assert "--record needs --version" in capsys.readouterr().err and not ledger.exists()
    live = B.build_from(rows, scored, corr, hist, curves, STANDARD, now=_ts("2026-09-11", 0) + 1800, host="h", version="V")
    with pytest.raises(B.NotComparable):
        B.rank_key(live)                                             # the judge's clock: the horizon is open
    assert B.record_card(live, ledger) == (ledger, True)
    import json
    back = json.loads(ledger.read_text())
    assert back["window"]["cohort"] == {"pipeline_version": "V", "run_config": None}
    assert back["rank"]["horizon_final"] is False and back["rank"]["comparable_from_et"] == "2026-09-25"
