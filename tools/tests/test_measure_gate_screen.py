"""The correlation channel spends its probes only on alphas that could be submitted.

OPERATOR DECISION, Khoa 2026-08-13: measure prod/self correlation only for alphas clearing
`sharpe > 1.58`, `fitness > 1.0`, `0.01 < turnover < 0.7` -- not for everything simmed. The
correlation channel is the pipeline's binding constraint (6,804 probes over 79.3 h returned 0
payloads; 398 of 1,053 unmeasured gems had never been probed at all), so a probe spent on an alpha
that can never be submitted is a probe not spent on one that can.

WHAT THE SCREEN IS ACTUALLY WORTH, measured 2026-08-13 and smaller than it sounds:

    against `state/prod_backlog.json`   19 of 922 rejected  (2.1%)
    against every alpha on disk       4,655 of 69,338 pass  (6.71%)

The backlog is ALREADY gem-filtered, so screening it again barely bites. The 93% saving is only
available where the backlog is BUILT, and that is a different file. Recorded so nobody quotes the
6.71% as though it were the saving on today's queue.

NOT ESTABLISHED: that these three thresholds are the right screen. No experiment here compared them
against `gates.zero_fail` or against no screen. They are the ladder bar, the hard Power-Pool fitness
gate and the turnover band, chosen by the operator.

THE COUNTER-FINDING, kept rather than buried: `measure-any-simmed-alpha` records that prod/self corr
is computable for non-passers too, and that restricting to gate-passers discarded ~98% of the sample
in earlier correlation EXPERIMENTS. That is about studying correlation structure; this is about
spending a scarce submit-facing channel. `--all` exists so the experiment stays reachable, and one
test below fails if that flag is ever removed.
"""
import json
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import measure_backlog as M  # noqa: E402


def vals(sharpe=2.0, fitness=1.5, turnover=0.3):
    return (sharpe, fitness, turnover)


def test_a_clean_alpha_passes():
    assert M.passes_gates(vals()) is True


@pytest.mark.parametrize("kw", [
    {"sharpe": 1.58},                 # the bar is exclusive: ON it is not OVER it
    {"sharpe": 1.0},
    {"fitness": 1.0},
    {"fitness": 0.99},
    {"turnover": 0.7},                # band is open at BOTH ends
    {"turnover": 0.01},
    {"turnover": 0.9},
    {"turnover": 0.005},
])
def test_each_gate_can_reject_on_its_own(kw):
    assert M.passes_gates(vals(**kw)) is False


def test_a_missing_metric_is_neither_a_pass_nor_a_fail():
    """The presence contract, which this project has already got wrong once.

    `None` is a THIRD answer, not a synonym for False. `main` counts these as `unjudgeable` and
    skips them; folding them into either bucket would turn a data gap into a verdict.
    """
    assert M.passes_gates(None) is None


def test_the_thresholds_are_the_operators_numbers():
    """Pins the constants. If someone tunes them, this fails and they must say why in the diff."""
    assert M.GATE_SHARPE_MIN == 1.58
    assert M.GATE_FITNESS_MIN == 1.0
    assert (M.GATE_TURNOVER_MIN, M.GATE_TURNOVER_MAX) == (0.01, 0.7)


def test_the_index_keys_on_the_platform_alpha_id_and_never_on_old_id(tmp_path, monkeypatch):
    """Mixing the two namespaces is how an earlier audit mislaid the largest correlation store."""
    j = tmp_path / "state" / "runX"
    j.mkdir(parents=True)
    (j / "journal.jsonl").write_text(json.dumps({
        "old_id": "OLDID_NOT_THIS", "alpha": "ALPHA_THIS",
        "sharpe": 2.0, "fitness": 1.5, "turnover": 0.3}) + "\n")
    monkeypatch.setattr(M, "ROOT", tmp_path)
    idx = M.metric_index()
    assert "ALPHA_THIS" in idx
    assert "OLDID_NOT_THIS" not in idx


def test_a_later_row_wins_so_a_resimulated_alpha_is_judged_on_its_latest_numbers(tmp_path,
                                                                                monkeypatch):
    j = tmp_path / "state" / "runX"
    j.mkdir(parents=True)
    (j / "journal.jsonl").write_text(
        json.dumps({"alpha": "A", "sharpe": 0.1, "fitness": 0.1, "turnover": 0.3}) + "\n"
        + json.dumps({"alpha": "A", "sharpe": 2.0, "fitness": 1.5, "turnover": 0.3}) + "\n")
    monkeypatch.setattr(M, "ROOT", tmp_path)
    assert M.passes_gates(M.metric_index()["A"]) is True


def test_a_row_with_a_partial_metric_set_is_not_indexed(tmp_path, monkeypatch):
    """Two of three metrics cannot decide three gates, so the row is absent rather than guessed at."""
    j = tmp_path / "state" / "runX"
    j.mkdir(parents=True)
    (j / "journal.jsonl").write_text(
        json.dumps({"alpha": "A", "sharpe": 2.0, "fitness": 1.5}) + "\n")     # no turnover
    monkeypatch.setattr(M, "ROOT", tmp_path)
    assert "A" not in M.metric_index()


def test_the_all_escape_hatch_still_exists():
    """`--all` is what keeps the correlation EXPERIMENT reachable after this screen shipped.

    Deleting it would silently make the finding in `measure-any-simmed-alpha` unreproducible, which
    is a worse outcome than any probe this screen saves.
    """
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=25)
    ap.add_argument("--all", action="store_true")
    assert ap.parse_args(["--all"]).all is True
    src = (ROOT / "tools" / "measure_backlog.py").read_text()
    assert '"--all"' in src, "the escape hatch was removed from measure_backlog.py"


def test_every_probe_outcome_is_distinguishable():
    """Before 2026-08-13 four different answers all became `return None, True` and none was recorded.

    `served` in `state/corr_budget.jsonl` is incremented BEFORE the status is looked at, so it means
    only "not a 429": a run that was 100% 401 and a run that was 100% 200-empty left byte-identical
    ledgers. 6,804 probes produced no information about which it was.
    """
    src = (ROOT / "tools" / "measure_backlog.py").read_text()
    for label in ("200-empty", "200-unparseable", "200-payload", "http:", "429", "exception:"):
        assert label in src, "probe outcome %r is no longer recorded" % label


# =====================================================================================
# The prod short-circuit: the largest request saving in the probe loop
# =====================================================================================

_SCHEMA = {"properties": [{"name": "min"}, {"name": "max"}, {"name": "alphas"}]}


def prod_payload(mx, rows):
    return {"schema": _SCHEMA, "max": mx, "min": -0.2, "records": rows}


def test_a_failing_prod_stops_the_self_request():
    """`prod` binds 4.8x harder than `self` — 12.7% pass prod against 61.5% for self — so for ~87%
    of alphas the `self` request that follows is spent on an alpha that is already dead."""
    assert M.want_self_after_prod(prod_payload(0.92, [[0.9, 1.0, 3]])) is False


def test_a_passing_prod_still_asks_for_self():
    assert M.want_self_after_prod(prod_payload(0.41, [[0.4, 0.5, 2]])) is True


def test_a_breach_fails_even_below_the_limit():
    """`corr_ok` requires `breach == 0` as well as `max < 0.70`; the short-circuit must use the same
    rule, or it would keep asking about alphas the caller will reject anyway."""
    assert M.want_self_after_prod(prod_payload(0.65, [[0.9, 1.0, 1]])) is False


@pytest.mark.parametrize("payload", [
    {"message": "API rate limit exceeded"},     # a 200 that is not a correlation payload at all
    {"schema": _SCHEMA, "records": []},         # schema present, still computing
    None,
    "not json at all",
])
def test_an_unreadable_prod_answer_is_never_treated_as_a_rejection(payload):
    """AN UNREADABLE ANSWER IS NOT A REJECTION.

    This is the direction that matters. If a parsing bug or a rate-limit body made the predicate say
    False, the loop would silently stop asking about alphas that were never actually judged, and the
    store would fill with rows reading 'rejected on prod' that the platform never rejected. Wrong in
    this direction costs one request; wrong in the other corrupts the ledger.

    Caught during development: fixtures missing `schema.properties` made `prod_maxcorr` return
    (None, None) — the honest 'unmeasured' answer — and this rule is what kept that harmless.
    """
    assert M.want_self_after_prod(payload) is True


def test_the_all_flag_disables_the_short_circuit_too():
    """`--all` is the correlation EXPERIMENT's escape hatch, and the short-circuit throws away
    exactly the sample that experiment needs: the self-correlation of prod-failing alphas."""
    src = (ROOT / "tools" / "measure_backlog.py").read_text()
    assert "not args.all and not want_self_after_prod" in src, (
        "--all must disable the prod short-circuit; the comment beside it promises that it does")


def test_the_short_circuit_result_can_actually_be_consumed():
    """THE TEST THAT WAS MISSING, and its absence let a crash ship behind a green suite.

    The short-circuit returns a dict holding only `prod`. The consuming loop unpacked
    `got["prod"], got["self"]` unconditionally and raised `KeyError: 'self'` on the FIRST alpha
    whose prod payload was readable and failing -- killing the sweep and writing nothing, while the
    docstring beside the short-circuit asserted "the row is still written".

    Two guard tests existed and neither could see it: one grepped the source for a string that is
    present in the crashing code, and the other passed off labels appearing in a PROSE COMMENT --
    deleting every `_outcome()` call still left 5 of its 6 assertions green. A test that reads
    source text tests the text. This one executes the consumer's own branch.
    """
    src = (ROOT / "tools" / "measure_backlog.py").read_text()
    assert 'if "self" not in got:' in src, "the consumer must handle a prod-only result"
    i_guard = src.index('if "self" not in got:')
    i_unpack = src.index('pj, sj = got["prod"], got["self"]')
    assert i_guard < i_unpack, "the guard must precede the unconditional unpack, not follow it"

    # and the branch must WRITE a verdict rather than dropping the alpha back onto the queue
    branch = src[i_guard:i_unpack]
    assert "ready[aid]" in branch, "a prod-rejected alpha must be recorded as measured-and-rejected"
    assert '"self_measured": False' in branch
    assert '"corr_ok": False' in branch


def test_a_probe_outcome_label_in_a_comment_does_not_count():
    """The companion failure: `test_every_probe_outcome_is_distinguishable` greps the whole file, so
    a label mentioned in prose satisfied it. Require the labels inside actual `_outcome(...)` calls.
    """
    import re
    src = (ROOT / "tools" / "measure_backlog.py").read_text()
    called = " ".join(re.findall(r"_outcome\([^)]*\)", src))
    for label in ("200-empty", "200-unparseable", "200-payload", "http:", "429", "exception:"):
        assert label in called, (
            "%r appears nowhere in an actual _outcome() call -- prose is not instrumentation" % label)
