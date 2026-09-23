"""Suite for forge/novelty.py -- the structural no-repeat rule on the submit path (Khoa D18).

Every test here pins a contract the 2026-09-22 audit found broken in the first version, so the
names say which failure they prevent rather than which function they call.
"""
from forge import novelty as N

# The real submitted formulas (state/forge/submitted.jsonl + the journal, read 2026-09-22). They are
# the ground truth for "two genuinely different mechanisms must NOT read as a repeat".
SUBMITTED_SHORT = ("multiply(multiply((1 - group_rank(ts_mean(executed_short_trade_share_count / "
                   "aggregate_executed_trade_share_count, 20), sector)), group_rank(ts_rank(operating_income / "
                   "equity, 252), sector)), (1 - group_rank(ts_rank(accrual / assets, 252), sector)))")
SUBMITTED_IV = ("multiply(group_rank(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 5), sector), "
                "(1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 5), sector)))")
IV_VARIANT = ("multiply(group_rank(ts_mean(implied_volatility_call_90 - implied_volatility_put_90, 20), industry), "
              "(1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 10), industry)))")


def _h(alpha, http=201, formula=None):
    return {"alpha": alpha, "http": http, "formula": formula, "posted_at": 1.0}


def test_the_formula_comes_from_the_submit_log_before_the_journal():
    """The audit's blocker 2: mL516W9W has no journal row, and reading the journal ONLY made the
    index permanently incomplete on the VPS -- which, failing closed, held every candidate forever.
    The submit-log row carries `formula` and is authoritative."""
    hist = [_h("mL516W9W", formula=SUBMITTED_IV)]
    idx = N.build(hist, rows={})                       # no journal row at all
    assert idx.complete is True and len(idx) == 1
    # the journal is the fallback, used only when the log row has no formula
    idx2 = N.build([_h("a1")], rows={"a1": {"formula": SUBMITTED_SHORT}})
    assert idx2.complete is True and len(idx2) == 1


def test_only_accepted_posts_are_registered_and_the_rest_are_not_silently_dropped():
    hist = [_h("ok", 201, SUBMITTED_IV), _h("refused", 403, SUBMITTED_SHORT),
            _h("unknown", None, SUBMITTED_SHORT), _h("dup", 201, SUBMITTED_IV)]
    idx = N.build(hist, rows={})
    assert len(idx) == 2                               # 'ok' and 'dup'; 403 and None are not submissions
    assert idx.complete is True


def test_an_accepted_post_with_no_readable_formula_makes_the_index_incomplete():
    idx = N.build([_h("a1", 201, SUBMITTED_IV), _h("ghost", 201, None)], rows={})
    assert idx.complete is False and idx.missing == ["ghost"]


def test_a_horizon_window_and_group_variant_of_a_submitted_alpha_is_a_repeat():
    idx = N.build([_h("kqVbg1xP", formula=SUBMITTED_IV)], rows={})
    is_repeat, score, twin = idx.verdict(IV_VARIANT)
    assert is_repeat is True and twin == "kqVbg1xP" and score >= 0.85


def test_two_genuinely_different_submitted_mechanisms_do_not_read_as_repeats():
    idx = N.build([_h("vRk095rv", formula=SUBMITTED_SHORT)], rows={})
    is_repeat, score, twin = idx.verdict(SUBMITTED_IV)
    assert is_repeat is False and 0.0 < score < 0.85 and twin == "vRk095rv"


def test_a_candidate_with_no_formula_is_unknown_not_novel():
    """The audit's fail-open finding: an unreadable SUBMISSION held the round while an unreadable
    CANDIDATE sailed through. Both are now 'unknown', and the caller holds on None."""
    idx = N.build([_h("vRk095rv", formula=SUBMITTED_SHORT)], rows={})
    assert idx.verdict("") == (None, 0.0, None)
    assert idx.verdict(None) == (None, 0.0, None)


def test_register_adds_a_structure_so_the_next_pick_in_the_same_run_sees_it():
    """The audit's blocker 3: two structural twins POSTed in one invocation because the index was
    built once. `register` is what the POST loop calls after each accepted POST."""
    idx = N.build([], rows={})
    assert idx.verdict(IV_VARIANT)[0] is False
    assert idx.register(SUBMITTED_IV, "kqVbg1xP") is True
    assert idx.verdict(IV_VARIANT)[0] is True
    assert idx.register("", "nothing") is False        # nothing to register is reported, not ignored


def test_an_empty_index_calls_nothing_a_repeat():
    idx = N.build([], rows={})
    assert idx.complete is True and len(idx) == 0
    assert idx.verdict(SUBMITTED_IV)[0] is False


def test_formula_of_prefers_the_log_and_falls_back_to_the_journal():
    assert N.formula_of("a", {"a": {"formula": "LOG"}}, {"a": {"formula": "JOURNAL"}}) == "LOG"
    assert N.formula_of("a", {"a": {}}, {"a": {"formula": "JOURNAL"}}) == "JOURNAL"
    assert N.formula_of("a", {}, {}) is None
