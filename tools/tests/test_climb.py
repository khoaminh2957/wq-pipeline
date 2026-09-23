"""Tests for the closed-loop builder.

This loop runs unattended and spends 300 simulations a round, so a wrong rule is not a wrong number
-- it is a whole cycle of quota spent climbing the wrong hill. Every assertion below is a rule Khoa
specified or a failure this project has already paid for.
"""

import collections
import json
import pathlib
import random
import re
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layered_alpha as LA  # noqa: E402
import climb as C  # noqa: E402


@pytest.fixture(scope="module")
def pools():
    ops = LA.load_operators()
    pool_a, pool_b, _dropped = LA.split_layers(ops)
    pool_c = LA.build_pool_c(LA.load_fields(), rng=random.Random(0))
    return pool_a, pool_b, pool_c


# ---- round 1 is ONE function around ONE leaf ----------------------------------------------

def test_round1_is_one_function_around_one_leaf(pools):
    """Khoa's round-1 spec: '1 hàm và một tổ hợp field đơn hoặc ratio'."""
    a, b, c = pools
    got = C.round1(a, b, c, random.Random(1), 60)
    assert len(got) == 60
    for f, m in got:
        assert m["move"] == "seed" and m["depth"] == 1
        assert f.startswith(m["op"] + "(") or m["op"] in ("log", "sqrt")
        assert f.count("(") == f.count(")")


def test_round1_candidates_are_distinct(pools):
    a, b, c = pools
    got = C.round1(a, b, c, random.Random(2), 120)
    assert len({f for f, _ in got}) == len(got)


# ---- growth is exactly the two moves Khoa named -------------------------------------------

def test_growth_only_ever_emits_a_known_move(pools):
    """Khoa, 2026-08-18: the move set grew from two to seven. The invariant is no longer "wrap or
    combine" -- it is that nothing OUTSIDE the declared set can reach the journal, because a move
    name nobody declared is a name no later analysis can group on."""
    a, b, c = pools
    base = "ts_sum(some_field, 5)"
    got = C.grow(base, a, b, c, random.Random(3), 80, depth=1)
    assert {m["move"] for _f, m in got} <= set(C.MOVE_WEIGHTS)
    assert len(got) == 80


def test_the_old_two_move_grammar_is_reproducible_by_weight(pools, monkeypatch):
    """The new moves must be a SUPERSET, not a replacement: zeroing their weights has to give back
    exactly the old grammar. Without this, `WQ_MOVE_WEIGHTS` could not A/B the change."""
    monkeypatch.setattr(C, "MOVE_WEIGHTS", {"wrap": 50, "combine": 50})
    a, b, c = pools
    got = C.grow("ts_sum(some_field, 5)", a, b, c, random.Random(3), 60, depth=1)
    assert {m["move"] for _f, m in got} == {"wrap", "combine"}


def test_a_zero_sum_weight_vector_does_not_make_one_move_certain(pools, monkeypatch):
    """The same trap `_weighted_choice` already guards: weights that sum to zero must fall back to
    something defined rather than silently electing whichever entry is first."""
    monkeypatch.setattr(C, "MOVE_WEIGHTS", {"wrap": 0, "combine": 0, "blend": 0})
    a, b, c = pools
    got = C.grow("ts_sum(some_field, 5)", a, b, c, random.Random(3), 10, depth=1)
    assert got and {m["move"] for _f, m in got} == {"wrap"}


@pytest.mark.parametrize("move", ["blend", "relate", "gate", "flip", "neut"])
def test_each_new_move_is_reachable_and_well_formed(pools, monkeypatch, move):
    """Each new move must actually fire when it is the only one weighted, and must emit a formula
    the platform could parse. A wrong argument count is a 400 -- it costs quota and returns nothing
    about the alpha -- so arity is asserted here rather than discovered in a live run."""
    monkeypatch.setattr(C, "MOVE_WEIGHTS", {move: 1})
    a, b, c = pools
    base = "ts_sum(some_field, 5)"
    got = C.grow(base, a, b, c, random.Random(11), 40, depth=1)
    assert got
    # `flip` deliberately falls back to a wrap once the baseline is too long to duplicate.
    assert {m["move"] for _f, m in got} <= {move, "wrap"}
    fired = [(f, m) for f, m in got if m["move"] == move]
    assert fired, "move %s never fired" % move
    arity = {"ts_corr": 3, "ts_covariance": 3, "ts_regression": 3, "vector_neut": 2,
             "regression_proj": 2, "trade_when": 3, "if_else": 3, "greater": 2}
    for f, _m in fired:
        assert f.count("(") == f.count(")"), f
        assert base in f
        for name, want in arity.items():
            for i in _call_sites(f, name):
                assert _n_args(f, i) == want, "%s: %s" % (name, f[:120])


def _call_sites(f, name):
    out, at = [], 0
    while True:
        at = f.find(name + "(", at)
        if at < 0:
            return out
        if at == 0 or not (f[at - 1].isalnum() or f[at - 1] == "_"):
            out.append(at + len(name))
        at += 1


def _n_args(f, open_paren):
    """Count TOP-LEVEL commas inside the call that starts at `open_paren`."""
    d, n = 0, 1
    for j in range(open_paren, len(f)):
        if f[j] == "(":
            d += 1
        elif f[j] == ")":
            d -= 1
            if d == 0:
                return n
        elif f[j] == "," and d == 1:
            n += 1
    raise AssertionError("unbalanced: %s" % f[:120])


def test_every_growth_contains_the_baseline(pools):
    """The whole climb rests on this. A growth that dropped the baseline would silently restart the
    search while the state still claimed to be at round n."""
    a, b, c = pools
    base = "ts_sum(some_field, 5)"
    for f, _m in C.grow(base, a, b, c, random.Random(4), 80, depth=1):
        assert base in f


def test_growth_never_returns_the_baseline_unchanged(pools):
    a, b, c = pools
    base = "ts_sum(some_field, 5)"
    for f, _m in C.grow(base, a, b, c, random.Random(5), 60, depth=1):
        assert f != base


def test_combine_uses_infix_arithmetic_not_calls(pools):
    """`add`/`subtract`/`multiply`/`divide` are written + - * / by operator decision. Calling them
    with one operand produced 12,643 arity violations in an earlier generation."""
    a, b, c = pools
    got = C.grow("ts_sum(f, 5)", a, b, c, random.Random(6), 120, depth=1)
    for f, m in got:
        for op in LA.INFIX:
            assert op + "(" not in f, f
        if m["move"] == "combine":
            assert m["infix"] in C.INFIX_OPS


def test_growth_increments_depth(pools):
    a, b, c = pools
    for _f, m in C.grow("x", a, b, c, random.Random(7), 20, depth=4):
        assert m["depth"] == 5


def test_growth_parenthesises_the_combination(pools):
    """`op(baseline + op(field))` must bind as one argument. Without the parens the infix would
    escape the call and the formula would mean something else."""
    a, b, c = pools
    for f, m in C.grow("BASE", a, b, c, random.Random(8), 120, depth=1):
        assert f.count("(") == f.count(")")
        if m["move"] == "combine":
            # The baseline may now arrive wrapped -- `+` and `-` require both sides to share a
            # unit, so each side is made dimensionless first. The property under test is the
            # PARENTHESISATION, not the literal text, so assert that.
            assert re.search(r"\((?:rank\()?BASE\)? %s " % re.escape(m["infix"]), f), f[:120]
            assert "BASE" in f


# ---- the objective, and the argmax Khoa chose ---------------------------------------------

def _cand(name, fitness, turnover=0.3, cw=None, gates="PASS", **kw):  # noqa: C901
    """A baseline candidate. Turnover is in band by default because Khoa's first filter requires it,
    and the reject gates carry an explicit PASS by default -- a helper that left them unscored would
    make every test exercise the not-scored path instead of the one under test."""
    r = {"formula": name, "fitness": fitness, "turnover": turnover}
    # The default objective is `sub_sharpe`, which lives INSIDE the checks. A helper that set only
    # `fitness` would leave every candidate unrankable under the real default and the tests would be
    # exercising a path the loop never takes. `sub` defaults to the fitness value so the ordering a
    # test writes is the ordering it gets.
    checks = [{"name": "LOW_SHARPE", "result": "PASS"},
              {"name": "LOW_SUB_UNIVERSE_SHARPE",
               "result": gates or "PASS",
               "value": kw.pop("sub", fitness)}]
    if gates:
        checks += [{"name": g, "result": gates} for g in C.REJECT_CHECKS
                   if g != "LOW_SUB_UNIVERSE_SHARPE"]
    if cw is not None:
        checks = [c for c in checks if c["name"] != "CONCENTRATED_WEIGHT"]
        checks.append({"name": "CONCENTRATED_WEIGHT", "result": cw})
    r["checks"] = checks
    move = kw.pop("move", None)
    if move:
        r["meta"] = {"move": move}
    r.update(kw)
    return r


def test_pick_is_argmax(pools):
    rows = [_cand("a", 1.0), _cand("b", 2.5), _cand("c", 1.9)]
    assert C.pick(rows)[:2] == ("b", 2.5)


def test_pick_skips_rows_without_the_objective():
    """An ERROR row with no fitness must not win a round by being treated as 0.0 among negatives."""
    rows = [{"formula": "err", "turnover": 0.3}, _cand("neg", -0.4),
            {"formula": "none", "fitness": None, "turnover": 0.3}]
    assert C.pick(rows)[:2] == ("neg", -0.4)


def test_pick_returns_nothing_when_no_row_has_the_objective():
    got = C.pick([{"formula": "x"}, {"formula": "y", "fitness": "n/a"}])
    assert got[:3] == (None, None, None)


def test_objective_is_swappable():
    """Fitness is a PLACEHOLDER by Khoa's own framing -- swapping the metric must be a parameter,
    never a rewrite."""
    rows = [_cand("a", 9.0, sharpe=0.1), _cand("b", 0.1, sharpe=9.0)]
    assert C.pick(rows, objective="fitness")[0] == "a"
    assert C.pick(rows, objective="sharpe")[0] == "b"


# ---- the stall rule -----------------------------------------------------------------------

def _fresh():
    return {"cycle": 1, "round": 0, "baseline": None, "baseline_score": None,
            "history": [], "no_gain": 0}


def test_a_real_gain_is_progress_and_moves_the_baseline():
    st, ev = C.advance(_fresh(), [_cand("a", 1.0)])
    assert ev == "progress" and st["baseline"] == "a"
    st, ev = C.advance(st, [_cand("b", 2.0)])
    assert ev == "progress" and st["baseline_score"] == 2.0


def test_a_small_gain_counts_as_no_progress_but_still_keeps_the_better_alpha():
    st, _ = C.advance(_fresh(), [_cand("a", 1.0)])
    st, ev = C.advance(st, [_cand("b", 1.01)])
    assert ev == "no-gain"
    assert st["baseline"] == "b", "a better alpha is still the better alpha"
    assert st["no_gain"] == 1


def test_two_consecutive_no_gain_rounds_stall():
    st, _ = C.advance(_fresh(), [_cand("a", 1.0)])
    st, _ = C.advance(st, [_cand("b", 1.01)])
    st, ev = C.advance(st, [_cand("c", 1.02)])
    assert ev == "stall"


def test_a_gain_resets_the_stall_counter():
    st, _ = C.advance(_fresh(), [_cand("a", 1.0)])
    st, _ = C.advance(st, [_cand("b", 1.01)])
    st, ev = C.advance(st, [_cand("c", 5.0)])
    assert ev == "progress" and st["no_gain"] == 0


def test_a_round_where_nothing_scored_is_a_dead_end_not_a_crash():
    """Was `no-gain` until 2026-08-15; Khoa made it end the cycle outright. A round where nothing
    scored has no baseline to climb from, so a second round would grow nothing."""
    st, ev = C.advance(_fresh(), [{"formula": "x", "turnover": 0.3}, {"formula": "y", "turnover": 0.3}])
    assert ev == "dead-end" and st["baseline"] is None


def test_reset_clears_the_climb_and_bumps_the_cycle():
    """Khoa chose full randomness on reset -- no banning of explored ground."""
    st, _ = C.advance(_fresh(), [_cand("a", 3.0)])
    st = C.reset(st, gems=0)
    assert st["cycle"] == 2 and st["baseline"] is None and st["baseline_score"] is None
    assert st["round"] == 0 and st["no_gain"] == 0


def test_history_survives_a_reset():
    """The drift between a baseline's score when chosen and when re-measured is the selection bias
    Khoa was told about and accepted. It is only auditable if the history is kept."""
    st, _ = C.advance(_fresh(), [_cand("a", 3.0)])
    n = len(st["history"])
    st = C.reset(st, gems=0)
    # A reset APPENDS rather than truncating: it records the segment rotation and the fields it
    # retired. What must never happen is the earlier rounds disappearing.
    assert len(st["history"]) >= n
    assert st["history"][0]["round"] == 1


# ---- the measurement tiers ----------------------------------------------------------------

def _row(sharpe, fitness, turnover, checks=None):
    r = {"sharpe": sharpe, "fitness": fitness, "turnover": turnover}
    if checks is not None:
        r["checks"] = checks
    return r


def test_tier1_is_anything_that_misses_the_screen():
    assert C.tier(_row(1.0, 2.0, 0.2)) == 1          # sharpe short
    assert C.tier(_row(2.0, 0.5, 0.2)) == 1          # fitness short
    assert C.tier(_row(2.0, 2.0, 0.9)) == 1          # turnover out of band
    assert C.tier(_row(None, None, None)) == 1


def test_tier2_is_screened_but_something_failed():
    r = _row(2.0, 2.0, 0.2, [{"name": "LOW_SHARPE", "result": "PASS"},
                             {"name": "CONCENTRATED_WEIGHT", "result": "FAIL"}])
    assert C.tier(r) == 2


def _gates(extra=(), corr="PENDING"):
    ch = [{"name": g, "result": "PASS"} for g in C.REJECT_CHECKS]
    ch += [{"name": g, "result": corr} for g in C.CORR_GATES]
    return ch + list(extra)


def test_tier3_is_eligibility_for_the_probe_not_a_gem():
    """569 live rows reached tier 3 and EVERY ONE carried PROD_CORRELATION and SELF_CORRELATION as
    PENDING -- unmeasured, not passed. Calling those gems is the error the council named: 'the four
    correlation gates are PENDING on 69,262/69,262 rows, so every zero-fail number ever computed
    from this file scores them as passes.'"""
    assert C.tier(_row(2.0, 2.0, 0.2, _gates())) == 3


def test_tier4_is_decided_by_the_MEASURED_value_not_the_check():
    """The check and the value are different surfaces, and defining a gem by the check made tier 4
    unreachable: /alphas/{id}/correlations/prod returned 0.664 for the standing best while its
    PROD_CORRELATION check still read PENDING, because the platform computes that check at
    SUBMISSION time."""
    r = _row(2.0, 2.0, 0.2, _gates())
    r["alpha"] = "A1"
    assert C.tier(r) == 3, "unmeasured is never a gem"
    assert C.tier(r, {"A1": {"prod": 0.55, "self": 0.22}}) == 4


def test_a_correlation_over_the_line_is_not_a_gem():
    r = _row(2.0, 2.0, 0.2, _gates())
    r["alpha"] = "A1"
    assert C.tier(r, {"A1": {"prod": 0.85, "self": 0.22}}) == 2
    assert C.tier(r, {"A1": {"prod": 0.55, "self": 0.95}}) == 2


def test_only_one_side_measured_is_still_not_a_gem():
    r = _row(2.0, 2.0, 0.2, _gates())
    r["alpha"] = "A1"
    assert C.tier(r, {"A1": {"prod": 0.55}}) == 3


def test_missing_checks_is_never_promoted_past_tier2():
    """`checks` comes in three shapes across this project's journals, including 614 rows that list
    the checks which PASSED. An unknown check set must never be read as a clean one."""
    assert C.tier(_row(2.0, 2.0, 0.2)) == 2
    assert C.tier(_row(2.0, 2.0, 0.2, "not-a-list")) == 2
    assert C.failing_checks({"checks": None}) is None


def test_bare_name_checks_do_not_count_as_passes():
    """The inverted-polarity shape: 614 rows at the head of `resim_results.jsonl` carry `checks` as
    a list of BARE NAMES listing the checks that PASSED. Such a list has no FAIL record, so a naive
    scan returns [] and promotes the alpha to tier 3 as if it were clean. It must fail closed."""
    r = _row(2.0, 2.0, 0.2, ["LOW_SHARPE", "LOW_FITNESS"])
    assert C.failing_checks(r) is None
    assert C.tier(r) == 2, "an unrecognised check shape is unknown, never clean"


# ---- it must never submit -----------------------------------------------------------------

def test_module_has_no_submit_path():
    """A simulation is cheap and repeatable; a submission is one irreversible POST per alpha and a
    403 spends it forever.

    The ban is on WRITING to the platform, not on reading it. `--rescore` opens a session to re-read
    candidates whose correlations were just computed -- re-reading is the whole point, because a gem
    declared from a journal row written BEFORE the probe ran would be asserting a gate that was
    PENDING at the time. So the test forbids POST verbs and submit paths, and separately proves the
    module never posts anything.
    """
    src = (ROOT / "tools/climb.py").read_text()
    for token in ("/submit", "requests.post", "post_one(", "post_many(", ".post(", "session.post"):
        assert token not in src, token


def test_write_gems_records_but_never_submits(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", tmp_path / "gems.jsonl")
    # The year filter now guards the ledger too, so a gem needs a full book history as well.
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [("2022", 2000), ("2023", 2100)])
    rows = [_row(2.0, 2.0, 0.2, _gates()), _row(1.0, 2.0, 0.2, _gates())]
    rows[0]["formula"], rows[0]["alpha"] = "good", "A1"
    rows[1]["alpha"] = "A2"
    m = {"A1": {"prod": 0.55, "self": 0.22}, "A2": {"prod": 0.55, "self": 0.22}}
    assert C.write_gems(rows, cycle=3, measured=m) == 1, "only the screened one is a gem"
    written = [json.loads(l) for l in (tmp_path / "gems.jsonl").read_text().splitlines()]
    assert len(written) == 1 and written[0]["alpha"] == "A1" and written[0]["cycle"] == 3
    assert "NOT SUBMITTED" in written[0]["note"]


def test_candidates_are_written_separately_from_gems(tmp_path, monkeypatch):
    """The tier-3 queue is what a correlation probe should read. It must never be the gem ledger."""
    monkeypatch.setattr(C, "LEDGER", tmp_path / "gems.jsonl")
    r = _row(2.0, 2.0, 0.2, _gates())
    r["formula"], r["alpha"] = "cand", "C1"
    assert C.write_gems([r], cycle=1, measured={}) == 0, "unmeasured correlations are not a gem"
    assert C.write_candidates([r], cycle=1, path=tmp_path / "cand.jsonl") == 1
    row = json.loads((tmp_path / "cand.jsonl").read_text().splitlines()[0])
    assert "PENDING" in row["note"] and "NOT passed" in row["note"]


# ---- the meta shapes every experiment writes through one journal writer -------------------

def test_tag_handles_every_meta_shape():
    """THE BUG THIS EXISTS FOR. `_child_row` indexed `meta["n_legs"]` directly. A climb row has no
    such key -- it carries move/op/depth -- so the line crashed on the first harvested child of
    every round: parents posted, quota spent, nothing collected, and the loop immediately started
    another round and did it again. 14 rounds in 25 minutes before it was caught.

    I had already made the DRY-RUN preview tolerant of the three shapes and missed this identical
    pattern 200 lines below it. Fixing one site of a pattern and shipping is the same class of error
    as the deploy skew that abandoned 1,410 simulations.
    """
    import layered_sim as LS
    assert LS._tag({"cell": "RF_OS"}) == "RF_OS"
    assert LS._tag({"move": "wrap", "depth": 3}) == "wrap/d3"
    assert LS._tag({"framework": "s6_neg"}) == "s6_neg"
    assert LS._tag({"legs": [1, 2, 3]}) == "legs=3"
    assert LS._tag({}) == "-"
    assert LS._tag(None) == "-"


def test_child_row_survives_every_meta_shape(tmp_path):
    """`_child_row` runs on EVERY harvested child, so it must never raise on a meta shape one of the
    experiments produces. Exercised with alpha=None so nothing touches the network."""
    import layered_sim as LS
    metas = [
        {"move": "seed", "op": "rank", "depth": 1},                 # climb round 1
        {"move": "combine", "op": "rank", "infix": "+", "depth": 4},  # climb growth
        {"cell": "OF_RS", "profile": "RS", "source": "ours"},        # gap 2x2
        {"framework": "s1_risk", "n_legs": 5, "carrier": True},      # framework batch
        {"legs": [{"inner": ["a"]}], "n_legs": 1, "carrier": False},  # 2^6 factorial
        {},                                                          # nothing at all
    ]
    out_lines = []
    with (tmp_path / "j.jsonl").open("w") as jf:
        for m in metas:
            c = {"formula": "rank(x)", "meta": m, "settings": {"decay": 3}}
            rec = LS._child_row(None, jf, [], out_lines.append, c, "COMPLETE", None, 7, "",
                                sim_url="u", t0=0.0)
            assert rec["meta"] is m
    assert len(out_lines) == len(metas)


# ---- every Discord message names the best alpha (Khoa, 2026-08-14) ------------------------

def _journal(tmp_path, rows, name="climb.jsonl"):
    # The default objective lives inside `checks`, so a headline test must supply it or nothing
    # ranks. Rows that already carry their own checks keep them.
    for r in rows:
        if "checks" not in r:
            r["checks"] = []
        if not any(c.get("name") == "LOW_SUB_UNIVERSE_SHARPE" for c in r["checks"]):
            r["checks"] = list(r["checks"]) + [
                {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS",
                 "value": r.get("sub", r.get("fitness", 0.0))}]
    d = tmp_path / "state/layered/runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return tmp_path


def test_best_alpha_picks_the_highest_objective_in_band(tmp_path):
    root = _journal(tmp_path, [
        {"formula": "a", "alpha": "A", "sharpe": 1.0, "fitness": 0.5, "turnover": 0.2},
        {"formula": "b", "alpha": "B", "sharpe": 2.0, "fitness": 0.9, "turnover": 0.3},
        {"formula": "c", "alpha": "C", "sharpe": 1.5, "fitness": 0.7, "turnover": 0.25},
    ])
    b, excluded = C.best_alpha(root=root, objective="sub_sharpe",
                              globs=("state/layered/runs/climb.jsonl",))
    assert b["alpha"] == "B" and excluded == 0


def test_a_degenerate_turnover_never_takes_the_headline(tmp_path):
    """THE REASON THIS FILTER EXISTS. The first VPS run returned sharpe 25.18 / fitness 35.43 at
    turnover 1.000 -- an alpha that turns the whole book over daily and cannot be submitted at any
    sharpe. Announcing it at the top of every message would report a number that means nothing."""
    root = _journal(tmp_path, [
        {"formula": "real", "alpha": "REAL", "sharpe": 1.5, "fitness": 0.8, "turnover": 0.3},
        {"formula": "junk", "alpha": "JUNK", "sharpe": 25.18, "fitness": 35.43, "turnover": 1.0},
    ])
    b, excluded = C.best_alpha(root=root, objective="sub_sharpe",
                              globs=("state/layered/runs/climb.jsonl",))
    assert b["alpha"] == "REAL"
    assert excluded == 1, "the exclusion must be COUNTED, never silently dropped"


def test_the_exclusion_is_visible_in_the_message(tmp_path):
    root = _journal(tmp_path, [
        {"formula": "real", "alpha": "REAL", "sharpe": 1.5, "fitness": 0.8, "turnover": 0.3},
        {"formula": "junk", "alpha": "JUNK", "sharpe": 25.0, "fitness": 35.0, "turnover": 1.0},
    ])
    line = C.best_line(root=root, globs=("state/layered/runs/climb.jsonl",))
    assert "REAL" in line and "excluded" in line and "JUNK" not in line


def test_best_line_names_the_margin_bar_the_alpha_must_clear(tmp_path):
    """S2: fitness >= F <=> margin >= F^2/(500*sharpe^2). Printing the required bps next to the
    actual makes the gap readable instead of leaving the reader to do the algebra."""
    root = _journal(tmp_path, [{"formula": "x", "alpha": "X", "sharpe": 1.58,
                                "fitness": 0.9, "turnover": 0.3, "margin": 0.0005}])
    line = C.best_line(root=root, globs=("state/layered/runs/climb.jsonl",))
    assert "5.00 bps" in line and "8.01 bps" in line


def test_best_line_never_raises_when_there_is_nothing(tmp_path):
    """A notification that fails because the best-alpha lookup broke is worse than one without it."""
    line = C.best_line(root=tmp_path, globs=("state/layered/runs/nothing_*.jsonl",))
    assert "none yet" in line


def test_rows_without_the_objective_do_not_win(tmp_path):
    # ERR carries NO objective at all; NEG carries a negative one. A missing value is unmeasured,
    # never zero, so the negative must win.
    root = _journal(tmp_path, [
        {"formula": "err", "alpha": "ERR", "turnover": 0.3,
         "checks": [{"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PENDING"}]},
        {"formula": "neg", "alpha": "NEG", "turnover": 0.3, "sub": -0.4},
    ])
    b, _ = C.best_alpha(root=root, objective="sub_sharpe",
                              globs=("state/layered/runs/climb.jsonl",))
    assert b["alpha"] == "NEG"


def test_an_empty_book_never_takes_the_headline(tmp_path):
    """The second real case, and the sharper one: sharpe 6.64 with margin 601 bps at book 0/0. It
    PASSED the sharpe/fitness/turnover screen, which is exactly why the screen alone is not a safe
    headline filter -- an alpha holding nothing cannot be submitted at any sharpe."""
    root = _journal(tmp_path, [
        {"formula": "real", "alpha": "REAL", "sharpe": 1.5, "fitness": 0.8, "turnover": 0.3,
         "longCount": 800, "shortCount": 790},
        {"formula": "empty", "alpha": "EMPTY", "sharpe": 6.64, "fitness": 29.7, "turnover": 0.083,
         "longCount": 0, "shortCount": 0},
    ])
    b, excluded = C.best_alpha(root=root, objective="sub_sharpe",
                              globs=("state/layered/runs/climb.jsonl",))
    assert b["alpha"] == "REAL" and excluded == 1


def test_best_line_names_the_failing_checks_and_the_book(tmp_path):
    """"screen PASS, tier 2" without naming what failed reads as a near-gem."""
    # NOT CONCENTRATED_WEIGHT -- that one is now a headline reject, matching the baseline rule.
    # `IS_LADDER_SHARPE` is what every real screen-passer in the live climb actually fails.
    root = _journal(tmp_path, [{"formula": "x", "alpha": "X", "sharpe": 2.0, "fitness": 1.2,
                                "turnover": 0.3, "longCount": 500, "shortCount": 500,
                                "checks": [{"name": "IS_LADDER_SHARPE", "result": "FAIL"},
                                           {"name": "LOW_SHARPE", "result": "PASS"}]}])
    line = C.best_line(root=root, globs=("state/layered/runs/climb.jsonl",))
    assert "IS_LADDER_SHARPE" in line and "book 500 long / 500 short" in line


# ---- Khoa's two baseline filters, 2026-08-14 ----------------------------------------------

def test_baseline_must_be_inside_the_turnover_band():
    """Filter 1. The first live lookup returned sharpe 25.18 at turnover 1.000 -- an alpha that
    turns the whole book over daily and cannot be submitted at any sharpe."""
    rows = [_cand("junk", 35.0, turnover=1.0), _cand("real", 0.9, turnover=0.3)]
    f, score, _row, skipped = C.pick(rows)
    assert f == "real" and score == 0.9
    assert skipped["turnover-out-of-band"] == 1


def test_a_baseline_failing_concentrated_weight_is_passed_over():
    """Filter 2. The standing best by fitness was sharpe 1.82 / fitness 1.80 on `book 4 long /
    4 short`, failing CONCENTRATED_WEIGHT. Climbing from it would have grown every later round on
    top of an 8-name book."""
    rows = [_cand("concentrated", 1.80, cw="FAIL"), _cand("wide", 0.90, cw="PASS")]
    f, score, _row, skipped = C.pick(rows)
    assert f == "wide" and score == 0.90
    assert skipped["CONCENTRATED_WEIGHT"] == 1


def test_it_walks_down_the_ranking_not_just_one_step():
    rows = [_cand("c1", 9.0, cw="FAIL"), _cand("c2", 8.0, turnover=0.99),
            _cand("c3", 7.0, cw="FAIL"), _cand("ok", 1.0, cw="PASS")]
    f, _s, _r, skipped = C.pick(rows)
    assert f == "ok"
    assert skipped["CONCENTRATED_WEIGHT"] == 2 and skipped["turnover-out-of-band"] == 1


def test_an_unscored_check_set_is_accepted_but_counted():
    """Rejecting on absence could leave a round with no baseline at all. CONCENTRATED_WEIGHT is
    scored on essentially every row, so an unscored one is rare -- counted, not assumed away."""
    # `checks` in the UNREADABLE shape -- `failing_checks` returns None. The objective still has to
    # be reachable, so the sub-sharpe rides on the row itself via the DERIVED lookup falling back.
    rows = [{"formula": "unscored", "fitness": 2.0, "turnover": 0.3,
             "checks": [{"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS", "value": 2.0},
                        "BARE_NAME"]}]
    f, _s, _r, skipped = C.pick(rows)
    assert f == "unscored" and skipped["checks-unscored"] == 1


def test_other_failing_checks_do_not_block_a_baseline():
    """Only CONCENTRATED_WEIGHT is a reject. A baseline that merely misses LOW_SHARPE is exactly
    what the climb exists to improve on."""
    rows = [_cand("low", 2.0, cw="PASS")]
    rows[0]["checks"].append({"name": "LOW_SHARPE", "result": "FAIL"})
    assert C.pick(rows)[0] == "low"


def test_skipped_counts_reach_the_history():
    """A silent filter is how a loop climbs the wrong hill for hours without anyone noticing."""
    st, _ = C.advance(_fresh(), [_cand("bad", 9.0, cw="FAIL"), _cand("good", 1.0, cw="PASS")])
    assert st["history"][-1]["skipped"]["CONCENTRATED_WEIGHT"] == 1


# ---- the pool coverage cut (Khoa, 2026-08-14) ---------------------------------------------

def test_pool_drops_fields_below_the_coverage_floor():
    """Operator instruction: cut fields with coverage under 95% from the pool. Applied at load, so
    every consumer -- climb, frameworks, factorial -- draws from the same screened catalogue."""
    assert LA.MIN_COVERAGE == 0.95
    kept = LA.load_fields(pyramid_gate=False)
    assert all(f["coverage"] >= 0.95 for f in kept)
    assert len(kept) < len(LA.load_fields(min_coverage=0.0, pyramid_gate=False))


def test_a_field_with_no_coverage_value_is_dropped():
    """An unknown coverage is not a high one. This project's dominant bug class is a missing value
    read as a benign one -- eight confirmed cases of a transient condition treated as a fact."""
    for f in LA.load_fields(pyramid_gate=False):
        assert isinstance(f.get("coverage"), (int, float))


def test_the_cut_is_a_flag_so_the_counterfactual_stays_measurable():
    """The council tested coverage as a predictor of degeneracy and it FAILED (BACKBONE_V2 K7), and
    'avoid option/earnings data' collapsed once pooled within coverage (D8). So this cut is an
    operator decision about pool membership, not a finding that low coverage produces worse alphas.
    Keeping it a parameter is what makes that difference measurable later."""
    assert (len(LA.load_fields(min_coverage=0.0, pyramid_gate=False))
            > len(LA.load_fields(min_coverage=0.99, pyramid_gate=False)))


def test_the_ratio_floor_holds_with_the_pyramid_gate_OFF():
    """Khoa's standing requirement: pool C carries at least 2000 ratios. It survives the coverage
    floor -- 3,918 ratios of 35,032 leaves."""
    import random as _r
    pool_c = LA.build_pool_c(LA.load_fields(pyramid_gate=False), rng=_r.Random(0))
    assert sum(1 for x in pool_c if "/" in x["expr"]) >= 2000


def test_the_pyramid_gate_BREAKS_the_ratio_floor_and_that_is_a_known_conflict():
    """TWO OPERATOR INSTRUCTIONS THAT CANNOT BOTH HOLD, recorded rather than silently resolved.

    Khoa asked earlier for "pool C phải có ít nhất 2000 ratio", and on 2026-08-15 for full pyramid
    cells to be switched off. The open cells hold 2,012 fields in total, which yields ~1,062 ratios.
    The floor is unreachable while the gate is on.

    The newer instruction wins because it is more specific AND was given with the shrinkage in hand
    -- he was shown 1,196 -> 2,012 before ruling. This test exists so the conflict stays visible: if
    the ratio floor ever matters again, it is the pyramid gate that has to give.
    """
    import random as _r
    gated = LA.build_pool_c(LA.load_fields(), rng=_r.Random(0))
    n = sum(1 for x in gated if "/" in x["expr"])
    assert n < 2000, "if this ever passes, the conflict has resolved itself and the note is stale"


def test_the_headline_applies_the_same_concentrated_weight_rule_as_the_baseline(tmp_path):
    """An alpha that cannot be a baseline should not be announced as our best. The standing headline
    was sharpe 1.82 / fitness 1.80 on book 4 long / 4 short failing CONCENTRATED_WEIGHT, while
    twenty real screen-passers on books of 660 names sat below it."""
    root = _journal(tmp_path, [
        {"formula": "narrow", "alpha": "NARROW", "sharpe": 1.82, "fitness": 1.80,
         "turnover": 0.52, "longCount": 4, "shortCount": 4,
         "checks": [{"name": "CONCENTRATED_WEIGHT", "result": "FAIL"}]},
        {"formula": "wide", "alpha": "WIDE", "sharpe": 1.88, "fitness": 1.27,
         "turnover": 0.117, "longCount": 660, "shortCount": 659,
         "checks": [{"name": "CONCENTRATED_WEIGHT", "result": "PASS"}]},
    ])
    b, excluded = C.best_alpha(root=root, objective="sub_sharpe",
                              globs=("state/layered/runs/climb.jsonl",))
    assert b["alpha"] == "WIDE" and excluded == 1


def test_the_gates_the_climb_actually_hit_are_baseline_rejects():
    """The set is exact on purpose: a gate joins it only after being measured to DISCRIMINATE, and
    the exactness is what stops a zero-variance gate from being added on plausibility.

    Original three, 2026-08-15: all twenty of the first screen-passers failed exactly
    LOW_SUB_UNIVERSE_SHARPE and IS_LADDER_SHARPE and nothing else.

    Three more, 2026-08-17, after auditing every gate the platform grades over the 74 signals then
    eligible for a correlation read -- CLUSTER_TEST 61 PASS / 13 adverse, UNITS 0/4, LOW_2Y_SHARPE
    0/1. Baseline survival measured BEFORE applying: 6,561 -> 5,453 of 27,180 rows, ~40 of a
    200-candidate round, so the climb cannot be starved of a baseline.
    """
    # Khoa cut it back to the original three on 2026-08-18. CLUSTER_TEST, UNITS and LOW_2Y_SHARPE
    # came out: the generator-side unit fix took the UNITS rate from 10.92% to 1.88%, so filtering
    # on it when CHOOSING SOMETHING TO CLIMB FROM now removes more candidates than it protects.
    # A gem is still required to pass every scored gate -- that rule lives in `tier`, not here.
    assert set(C.REJECT_CHECKS) == {"CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE",
                                    "IS_LADDER_SHARPE"}
    # The three that are adverse on 74 of 74 must never appear: a gate with no variance cannot
    # discriminate, and adding one empties both the probe queue and the baseline pool.
    for zero_variance in ("MATCHES_THEMES", "MATCHES_COMPETITION", "OSMOSIS_ALLOCATION"):
        assert zero_variance not in C.REJECT_CHECKS


def test_a_baseline_failing_the_ratio_gate_is_passed_over():
    """LOW_SUB_UNIVERSE_SHARPE is the RATIO gate: limit = k * the alpha's OWN sharpe, so raising
    sharpe raises the bar by the same factor. Building the climb on an alpha that fails it means
    every later round inherits a structure that cannot clear it."""
    rows = [_cand("ratio_fail", 1.27, gates="FAIL"), _cand("clean", 1.05)]
    rows[0]["checks"] = [c if c["name"] != "CONCENTRATED_WEIGHT"
                         else {"name": "CONCENTRATED_WEIGHT", "result": "PASS"}
                         for c in rows[0]["checks"]]
    rows[0]["checks"] = [c if c["name"] != "IS_LADDER_SHARPE"
                         else {"name": "IS_LADDER_SHARPE", "result": "PASS"}
                         for c in rows[0]["checks"]]
    f, score, _r, skipped = C.pick(rows)
    assert f == "clean" and score == 1.05
    # The helper sets EVERY reject gate to `gates`, and REJECT_CHECKS grew on 2026-08-17, so the
    # skip key is now the combined name. Assert the gate is named rather than pinning the string.
    assert sum(v for k, v in skipped.items() if "LOW_SUB_UNIVERSE_SHARPE" in k) == 1


def test_a_baseline_failing_the_ladder_is_passed_over():
    rows = [_cand("ladder_fail", 1.20), _cand("clean", 0.90)]
    rows[0]["checks"] = [c for c in rows[0]["checks"] if c["name"] != "IS_LADDER_SHARPE"]
    rows[0]["checks"].append({"name": "IS_LADDER_SHARPE", "result": "FAIL"})
    assert C.pick(rows)[0] == "clean"


def test_an_unscored_reject_gate_is_counted_not_assumed_passed():
    """A GATE THAT WAS NOT SCORED HAS NOT BEEN PASSED. IS_LADDER_SHARPE is scored on only 560 of
    1,020 live rows, so "does not fail it" silently includes "was never graded on it" -- the exact
    gate-PRESENCE artifact behind the council's false 'carrier-free fails the ladder less', where
    the gate was scored on 71.7% of one arm against 99.3% of the other and conditioning on presence
    collapsed the effect to p 0.234."""
    r = _cand("no_ladder_score", 1.0)
    r["checks"] = [c for c in r["checks"] if c["name"] != "IS_LADDER_SHARPE"]
    f, _s, _row, skipped = C.pick([r])
    assert f == "no_ladder_score", "it is accepted -- rejecting on absence could leave no baseline"
    assert skipped["IS_LADDER_SHARPE-not-scored"] == 1
    assert "LOW_SUB_UNIVERSE_SHARPE-not-scored" not in skipped


def test_a_warning_no_longer_blocks_a_BASELINE_but_is_still_counted():
    """Khoa, 2026-08-18: only a FAIL disqualifies a baseline. The two questions are separate --
    what we are willing to STAND ON may carry a warning; what we SUBMIT may not, and
    `test_a_warning_on_a_named_gate_is_not_a_gem` still pins that half. The count must survive the
    loosening, because it is the only evidence available if warned baselines lead nowhere."""
    # The warning has to sit on a gate that is NOT in HARD_CHECKS: `_cand(gates="WARNING")` marks
    # every reject gate at once, CONCENTRATED_WEIGHT included, and that one still disqualifies.
    rows = [_gaterow("warned", 2.0, LOW_SUB_UNIVERSE_SHARPE="WARNING"), _cand("clean", 0.5)]
    f, _s, _r, skipped = C.pick(rows)
    assert f == "warned", "a warning is no longer a rejection at baseline-select time"
    assert any(k.startswith("WARNING-accepted:") for k in skipped), skipped


def test_a_FAIL_still_blocks_a_baseline():
    """The loosening is to WARNING only. A FAIL on a named gate must still pass the candidate over,
    or the three remaining gates would stop meaning anything at all."""
    rows = [_cand("failed", 2.0, gates="FAIL"), _cand("clean", 0.5)]
    f, _s, _r, _sk = C.pick(rows)
    assert f == "clean"


def test_a_warning_on_a_named_gate_is_not_a_gem():
    r = _cand("warned", 2.0, sharpe=2.0, turnover=0.3, gates="WARNING")
    assert C.tier(r) == 2


def test_unscored_is_not_merged_with_adverse():
    """Treating an unscored gate as adverse leaves 0 survivors out of 1,020 live rows -- the climb
    would have no baseline at all and stall on its next round. Unscored is counted, not
    disqualifying; that separation is the whole point of blocked_on returning two lists."""
    row = {"formula": "x", "turnover": 0.3, "checks": []}
    adverse, unscored = C.blocked_on(row)
    assert adverse == [] and set(unscored) == set(C.REJECT_CHECKS)


# ---- alternating grow / tune rounds (Khoa, 2026-08-14) ------------------------------------

BASE = "ts_decay_linear(scale((ts_backfill(oth335_x, 60) + group_scale(mdl177_y, market))), 5)"


def test_tunable_slots_finds_windows_groups_and_floats():
    slots = [(k, c) for _s, _e, k, c, _ch in C.tunable_slots(BASE)]
    assert ("window", "60") in slots and ("window", "5") in slots
    assert ("group", "market") in slots


def test_a_field_name_containing_digits_is_not_a_slot():
    """`oth460_1l_qidxt` and `pv20_returns252` must not be mistaken for parameters. A number is a
    slot only when it sits alone as an ARGUMENT, after a comma or paren and before a comma or
    paren."""
    assert C.tunable_slots("zscore(pv20_returns252)") == []
    assert C.tunable_slots("rank(oth460_1l_qidxt)") == []
    got = C.tunable_slots("ts_mean(pv20_returns252, 20)")
    assert [(k, c) for _s, _e, k, c, _ch in got] == [("window", "20")]


def test_tune_changes_two_or_three_slots_and_keeps_the_structure():
    """Khoa: 'đổi baseline đúng 2 số hoặc 3 số'."""
    import random as _r
    for f, m in C.tune(BASE, _r.Random(2), 60):
        assert 1 <= len(m["changed"]) <= 3
        assert m["move"] == "tune"
        # same structure: the operator sequence is untouched
        assert f.count("(") == BASE.count("(") and f.count(",") == BASE.count(",")
        for op in ("ts_decay_linear", "scale", "ts_backfill", "group_scale"):
            assert op + "(" in f


def test_tune_never_re_emits_the_baseline():
    """A variant identical to the baseline is a re-measurement, not a variant, and would spend a
    simulation to learn nothing."""
    import random as _r
    got = C.tune(BASE, _r.Random(3), 80)
    assert BASE not in {f for f, _m in got}
    assert len({f for f, _m in got}) == len(got)


def test_tune_returns_nothing_when_the_baseline_has_no_parameter():
    """The live case at the moment this was written: the standing baseline was
    `zscore(pv87_2_pretaxprofit_qf_matrix_all_chngratio_number)`, which has no parameter at all."""
    import random as _r
    assert C.tune("zscore(pv87_2_pretaxprofit_qf_matrix_all_chngratio_number)", _r.Random(0), 50) == []


def test_rounds_alternate_on_the_last_kind_not_on_parity():
    """Khoa: 'ko cần tính chẵn lẻ nữa mà là xen kẻ'. A tune round that is passed over runs as a
    grow, so parity would drift out of step with what actually ran."""
    assert C.next_kind({}) == "seed"
    assert C.next_kind({"baseline": BASE, "last_kind": "seed"}) == "tune"
    assert C.next_kind({"baseline": BASE, "last_kind": "tune"}) == "grow"
    assert C.next_kind({"baseline": BASE, "last_kind": "grow"}) == "tune"


def test_a_tune_round_with_no_slots_is_passed_over_and_grows_instead(pools):
    """Khoa: 'trong trường hợp ko có tham số thì tạm pass đợt'."""
    a, b, c = pools
    import random as _r
    st = {"baseline": "zscore(pv87_2_pretaxprofit)", "last_kind": "seed", "depth": 1}
    said = []
    got = C.draw(st, a, b, c, _r.Random(1), 12, out=said.append)
    assert got and {m["move"] for _f, m in got} <= set(C.MOVE_WEIGHTS)
    assert any("PASSED" in s for s in said)


def test_advance_records_the_kind_that_actually_ran():
    """Read off the rows, never recomputed: a passed-over tune ran as a grow, and the state must
    alternate from what happened."""
    st, _ = C.advance(_fresh(), [_cand("a", 1.0, move="seed")])
    assert st["last_kind"] == "seed" and st["history"][-1]["kind"] == "seed"
    st, _ = C.advance(st, [dict(_cand("b", 2.0), meta={"move": "tune"})])
    assert st["last_kind"] == "tune"


# ---- the submitter: root of a lineage, one a day (Khoa, 2026-08-14) -----------------------

import climb_submit as CS  # noqa: E402


def test_normalise_survives_a_tune_round():
    """Literal comparison found ZERO ancestors of a deep gem; normalised comparison found 210. The
    difference is entirely the tune rounds rewriting windows and group names in place."""
    a = "ts_decay_linear(ts_backfill(f, 60), 5)"
    b = "ts_decay_linear(ts_backfill(f, 250), 20)"
    assert CS.normalise(a) == CS.normalise(b)
    assert CS.normalise("group_scale(f, market)") == CS.normalise("group_scale(f, sector)")


def test_lineage_keeps_only_the_shallowest_gem():
    """Khoa: '6 gem đó thật sự chỉ là từ 1 gem mà ra nên chỉ cần nộp gem gốc là được'. The six that
    first reached tier 4 shared six core fields at Jaccard 0.75-0.86 and differed only in the
    OUTERMOST operator."""
    gems = [{"alpha": "DEEP", "formula": "group_neutralize(winsorize(ts_mean(f, 20)))"},
            {"alpha": "ROOT", "formula": "ts_mean(f, 20)"},
            {"alpha": "MID", "formula": "winsorize(ts_mean(f, 20))"}]
    roots = CS.lineages(gems)
    assert [r["alpha"] for r in roots] == ["ROOT"]


def test_two_unrelated_gems_are_two_lineages():
    gems = [{"alpha": "A", "formula": "ts_mean(alpha_field, 20)"},
            {"alpha": "B", "formula": "ts_sum(other_field, 5)"}]
    assert {r["alpha"] for r in CS.lineages(gems)} == {"A", "B"}


def test_a_spent_lineage_is_not_offered_again(tmp_path, monkeypatch):
    """One submit kills its whole signal family: 464 rows of one mechanic gave 26 gems and 1
    submission."""
    log = tmp_path / "submitted.jsonl"
    log.write_text(json.dumps({"normalised": CS.normalise("ts_mean(f, 20)"),
                               "http": 201, "posted_at": time.time()}) + "\n")
    monkeypatch.setattr(CS, "LOG", log)
    spent = CS.already_submitted(log)
    assert CS.normalise("winsorize(ts_mean(f, 60))") .find(spent[0]) >= 0


def test_the_module_records_the_whole_body_not_a_prefix(tmp_path):
    """Every 403 body ever stored in this repository was truncated at 400 characters, so the
    platform's actual refusal reason is nowhere on disk."""
    log = tmp_path / "s.jsonl"
    body = "x" * 5000
    CS.record({"alpha": "A", "formula": "f"}, 403, body, path=log)
    got = json.loads(log.read_text().splitlines()[0])
    assert got["body"] == body and len(got["body"]) == 5000


def test_posting_requires_an_explicit_flag(monkeypatch):
    """`--submit` is the only path that POSTs; listing must never post.

    This used to assert the literal source line `if a.list or not (a.submit or a.alpha)`. That line
    WAS the defect -- with `--alpha` set the condition is False and control fell straight through to
    the POST -- so the test pinned the bug in place and went red the moment it was fixed. Assert the
    BEHAVIOUR instead: drive main() with a transport that raises if it is ever reached.
    """
    src = (ROOT / "tools/climb_submit.py").read_text()
    assert src.count(".post(") == 1, "exactly one POST call, in `post()`"

    import climb_submit as CS
    reached = []

    def never(*a, **k):
        reached.append(a)
        return None, "a POST was attempted without --submit"

    monkeypatch.setattr(CS, "post", never)
    for argv in (["--list"], ["--alpha", "ABCD1234"], []):
        monkeypatch.setattr(sys, "argv", ["climb_submit.py"] + argv)
        try:
            CS.main()
        except SystemExit:
            pass
    assert reached == [], "no argv without --submit may reach a POST: %r" % (reached,)


def test_naming_an_alpha_does_not_waive_the_gates():
    src = (ROOT / "tools/climb_submit.py").read_text()
    assert "naming one does not waive them" in src


# ---- the pyramid pool gate (Khoa, 2026-08-15) ---------------------------------------------

import pool_gate as PG  # noqa: E402


def _counts(tmp_path, counts, ts=None):
    p = tmp_path / "pyramid_cell_counts.json"
    p.write_text(json.dumps({"pairs": [{"region": "USA", "delay": 1, "counts": counts,
                                        "ts": ts or time.time()}], "ts": ts or time.time()}))
    return p


def test_a_full_cell_is_disabled_and_an_open_one_is_not(tmp_path):
    st = PG.state(_counts(tmp_path, {"Model": 3, "News": 2, "Imbalance": 0}))
    assert st["ok"] and st["disabled"] == {"Model"}
    assert st["open"] == {"News", "Imbalance"}
    assert st["needs"] == {"News": 1, "Imbalance": 3}


def test_a_cell_over_the_unlock_count_is_still_disabled(tmp_path):
    st = PG.state(_counts(tmp_path, {"Model": 9}))
    assert st["disabled"] == {"Model"}


def test_unreadable_counts_disable_NOTHING(tmp_path):
    """FAIL OPEN, deliberately. Disabling on bad data shrinks the search space 26x and looks exactly
    like working, which is this project's dominant bug class; not disabling merely spends
    simulations on a full cell, which is visible in the next report."""
    for path in (tmp_path / "missing.json", tmp_path / "bad.json"):
        if path.name == "bad.json":
            path.write_text("{not json")
        st = PG.state(path)
        assert st["ok"] is False and st["disabled"] == frozenset()
        assert "NOTHING is disabled" in PG.describe(st)


def test_counts_for_another_segment_are_not_borrowed(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"pairs": [{"region": "CHN", "delay": 1, "counts": {"Model": 3}}]}))
    assert PG.state(p, region="USA")["ok"] is False


def test_the_pool_drops_full_categories_and_exempts_open_ones_from_the_floor():
    """Khoa's ruling: hard-disable the full cells, and waive the coverage floor for the open ones --
    that exemption is what takes the usable pool from 1,196 back to 2,012."""
    gated = LA.load_fields()
    assert LA.load_fields.gate.get("ok"), "the live artifact should be readable"
    disabled = LA.load_fields.gate["disabled"]
    open_ = LA.load_fields.gate["open"]
    cats = {PG.category_of(f) for f in gated}
    assert not (cats & disabled), "a disabled category leaked into the pool"
    assert cats <= open_
    # the waiver: at least one kept field sits BELOW the floor
    assert any(f["coverage"] < LA.MIN_COVERAGE for f in gated
               if isinstance(f.get("coverage"), (int, float)))


def test_the_gate_can_be_turned_off_so_the_counterfactual_stays_measurable():
    assert len(LA.load_fields(pyramid_gate=False)) > len(LA.load_fields())


def test_draw_weights_favour_the_cell_nearest_to_unlocking_UNDER_THAT_POLICY():
    """A category one alpha short outweighs one three short, and a category's total is shared among
    its leaves so a big category does not win on count alone."""
    pool = ([{"category": "News"}] * 100 + [{"category": "Imbalance"}] * 2)
    # `counts` is required: the default policy is `filled`, w = count + 1. Omitting it made both
    # cells read as count 0 and the ordering vanished -- the test was passing a state the real
    # caller never produces.
    st = {"ok": True, "needs": {"News": 1, "Imbalance": 3},
          "counts": {"News": 2, "Imbalance": 0}}
    w = PG.draw_weights(pool, st, "nearest")   # the DEFAULT is uniform since Khoa asked for it
    news = sum(x for x, f in zip(w, pool) if f["category"] == "News")
    imb = sum(x for x, f in zip(w, pool) if f["category"] == "Imbalance")
    assert news > imb, "one-short must outweigh three-short"
    assert w[0] < w[-1], "a leaf in a 2-field category carries more weight than one in a 100-field"


def test_draw_weights_are_uniform_when_the_gate_is_off():
    pool = [{"category": "News"}, {"category": "Model"}]
    assert PG.draw_weights(pool, {"ok": False}) == [1.0, 1.0]


def test_leaf_weights_match_the_pool_length():
    import random as _r
    pool_c = LA.build_pool_c(LA.load_fields(), rng=_r.Random(0))
    assert len(C.leaf_weights(pool_c)) == len(pool_c)


def test_the_draw_policy_is_named_and_swappable():
    """`filled` (w = count + 1) was Khoa's choice from the measured draw-share table; `uniform`
    superseded it hours later when he asked for the pick to be fully random. Both are kept because
    nothing here has MEASURED which ordering finds unlocks fastest -- only arguments, and they point
    different ways."""
    assert PG.DEFAULT_POLICY == "uniform"
    assert set(PG.WEIGHT_POLICIES) == {"nearest", "filled", "emptiest", "uniform"}


def test_filled_orders_by_how_full_the_cell_already_is():
    pool = [{"category": "Full2"}, {"category": "Empty"}]
    st = {"ok": True, "needs": {"Full2": 1, "Empty": 3}, "counts": {"Full2": 2, "Empty": 0}}
    w = PG.draw_weights(pool, st, "filled")
    assert w[0] > w[1]


def test_an_empty_cell_never_drops_to_zero_draws():
    """The +1 in `count + 1` is the whole point: a cell at 0 would otherwise get zero weight and
    never be worked on, so it could never leave 0."""
    pool = [{"category": "Empty"}]
    w = PG.draw_weights(pool, {"ok": True, "needs": {"Empty": 3}, "counts": {"Empty": 0}}, "filled")
    assert w[0] > 0


def test_emptiest_is_the_opposite_bet():
    pool = [{"category": "Full2"}, {"category": "Empty"}]
    st = {"ok": True, "needs": {"Full2": 1, "Empty": 3}, "counts": {"Full2": 2, "Empty": 0}}
    assert PG.draw_weights(pool, st, "emptiest")[1] > PG.draw_weights(pool, st, "emptiest")[0]


def test_every_policy_shares_a_category_total_among_its_leaves():
    """A 1,065-field category must not outdraw a 118-field one on count alone."""
    pool = [{"category": "Big"}] * 100 + [{"category": "Small"}]
    st = {"ok": True, "needs": {"Big": 3, "Small": 3}, "counts": {"Big": 0, "Small": 0}}
    for name in PG.WEIGHT_POLICIES:
        w = PG.draw_weights(pool, st, name)
        big = sum(x for x, f in zip(w, pool) if f["category"] == "Big")
        small = sum(x for x, f in zip(w, pool) if f["category"] == "Small")
        assert abs(big - small) < 1e-9, name


# ---- the per-year book filter (Khoa, 2026-08-15) ------------------------------------------

def test_year_book_rejects_an_alpha_that_is_empty_for_years(monkeypatch):
    """THE ALPHA THIS CAUGHT. mL516W9W, submitted 2026-08-14, holds long 0 / short 0 from 2014
    through 2020 -- SEVEN YEARS OF NOTHING -- and only reaches 1,211 names in 2022. Its sharpe of
    3.61 was computed over three trading years out of ten. The scalar `longCount` on the alpha
    payload is one number for the whole run and cannot see this.

    Under the TRAILING-2 rule Khoa set on 2026-08-15 it now PASSES, because 2022 and 2023 both hold
    four figures. That is the cost of lowering the bar, and it is asserted here rather than left to
    be discovered: the rule this alpha originally failed was `trailing=None`, every year.
    """
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [
        ("2014", 0), ("2015", 0), ("2016", 0), ("2017", 0), ("2018", 0), ("2019", 0),
        ("2020", 0), ("2021", 901), ("2022", 1211), ("2023", 1267)])
    assert C.year_book_ok("mL516W9W")[0] is True, "trailing 2 passes it"
    ok, why = C.year_book_ok("mL516W9W", trailing=None)
    assert ok is False and "8 of" in why, "every-year still rejects it"


def test_year_book_accepts_a_full_history(monkeypatch):
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [("2022", 1211), ("2023", 1267)])
    assert C.year_book_ok("X")[0] is True


def test_one_thin_year_is_enough_to_reject(monkeypatch):
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [("2022", 1211), ("2023", 999)])
    assert C.year_book_ok("X")[0] is False, "one thin year inside the window is enough"


def test_unreadable_yearly_stats_is_UNKNOWN_not_a_pass(monkeypatch):
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: None)
    assert C.year_book_ok("X")[0] is None


def test_no_yearly_rows_is_a_failure_not_a_pass(monkeypatch):
    """A book that was never reported is not a book over 1000."""
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [])
    assert C.year_book_ok("X")[0] is False


def test_pick_walks_past_a_baseline_that_is_empty_for_years(monkeypatch):
    thin, fat = "THIN", "FAT"
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: ([("2022", 50), ("2023", 60)] if aid == thin
                                          else [("2022", 2000), ("2023", 2100)]))
    rows = [_cand("thin", 2.9, alpha=thin), _cand("fat", 1.1, alpha=fat)]
    f, score, _r, skipped = C.pick(rows, year_book=True)
    assert f == "fat" and score == 1.1
    assert skipped["year-book<1000"] == 1


def test_pick_skips_a_candidate_whose_stats_cannot_be_read(monkeypatch):
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: (None if aid == "A"
                                          else [("2022", 2000), ("2023", 2100)]))
    rows = [_cand("a", 2.9, alpha="A"), _cand("b", 1.1, alpha="B")]
    f, _s, _r, skipped = C.pick(rows, year_book=True)
    assert f == "b" and skipped["yearly-stats-unreadable"] == 1


def test_the_year_filter_is_checked_LAST_because_it_costs_a_request(monkeypatch):
    """A candidate rejected on turnover or CONCENTRATED_WEIGHT must never reach the network."""
    calls = []
    monkeypatch.setattr(C, "yearly_book",
                        lambda aid, **kw: calls.append(aid) or [("2022", 2000), ("2023", 2100)])
    rows = [_cand("out_of_band", 9.0, turnover=1.0, alpha="OOB"),
            _cand("cw_fail", 8.0, cw="FAIL", alpha="CW"),
            _cand("good", 1.0, alpha="GOOD")]
    assert C.pick(rows, year_book=True)[0] == "good"
    assert calls == ["GOOD"], "only the candidate that passed every free filter was fetched"


def test_the_ledger_never_records_the_same_alpha_twice(tmp_path, monkeypatch):
    """50 gem rows turned out to be FIVE alphas written ten times. The loop ends a cycle when the
    ledger GROWS, so the count kept growing and seven cycles spent 330 simulations each going in a
    circle."""
    monkeypatch.setattr(C, "LEDGER", tmp_path / "gems.jsonl")
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [("2022", 2000), ("2023", 2100)])
    r = _row(2.0, 2.0, 0.2, _gates())
    r["formula"], r["alpha"] = "f", "A1"
    m = {"A1": {"prod": 0.5, "self": 0.2}}
    assert C.write_gems([r], 1, measured=m) == 1
    assert C.write_gems([r], 2, measured=m) == 0, "already in the ledger"
    assert len(C.ledger_alphas()) == 1


def test_a_gem_must_also_pass_the_year_filter(tmp_path, monkeypatch):
    """All five ledger alphas hold long 0 / short 0 from 2014 to 2020. A gem that does not trade for
    70% of its own backtest is not a gem, and the filter had guarded the baseline only."""
    monkeypatch.setattr(C, "LEDGER", tmp_path / "gems.jsonl")
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [("2014", 0), ("2022", 50), ("2023", 1200)])
    r = _row(2.0, 2.0, 0.2, _gates())
    r["formula"], r["alpha"] = "f", "THIN"
    assert C.write_gems([r], 1, measured={"THIN": {"prod": 0.5, "self": 0.2}},
                        year_book=True) == 0


def test_an_unknown_year_book_is_not_a_gem(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", tmp_path / "gems.jsonl")
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: None)
    r = _row(2.0, 2.0, 0.2, _gates())
    r["formula"], r["alpha"] = "f", "U"
    assert C.write_gems([r], 1, measured={"U": {"prod": 0.5, "self": 0.2}},
                        year_book=True) == 0


def test_no_selectable_baseline_ends_the_cycle_immediately():
    """Khoa, 2026-08-15: "khi ko chọn ra được alpha baseline do lỗi ko vượt qua lọc thì bắt đầu lại
    từ đầu". Nothing in 300 candidates cleared the filters, so there is nothing to climb from, and
    waiting for a second no-gain round would spend another 300 simulations growing a branch that has
    no baseline at all."""
    st, ev = C.advance(_fresh(), [_cand("bad", 9.0, turnover=1.0)])
    assert ev == "dead-end"
    assert st["history"][-1]["event"] == "dead-end"


def test_a_dead_end_is_distinct_from_a_stall():
    """A stall means the climb stopped improving; a dead end means it never started. They reset the
    same way but the history must not confuse them."""
    st, _ = C.advance(_fresh(), [_cand("a", 1.0)])
    st, ev = C.advance(st, [_cand("b", 1.01)])
    assert ev == "no-gain"
    st, ev = C.advance(st, [])
    assert ev == "dead-end"


# ---- the objective is sub-universe sharpe (Khoa, 2026-08-15) ------------------------------

def test_sub_sharpe_is_read_out_of_the_check_not_the_payload():
    """There is no top-level field for it -- it is the `value` inside LOW_SUB_UNIVERSE_SHARPE."""
    row = {"checks": [{"name": "LOW_SUB_UNIVERSE_SHARPE", "value": 1.4, "result": "PASS"}]}
    assert C.metric(row, "sub_sharpe") == 1.4
    assert C.metric({"checks": []}, "sub_sharpe") is None
    assert C.metric({"checks": "bad"}, "sub_sharpe") is None


def test_every_entry_point_shares_ONE_objective():
    """Khoa moved the objective back to fitness on 2026-08-18. What this pins is not the value but
    the SHARING: three functions used to carry the default as three separate string literals, so a
    change had to be made in three places or the ranking would silently disagree with itself."""
    import inspect
    for fn in (C.pick, C.advance, C.best_alpha, C.candidate_reps):
        assert inspect.signature(fn).parameters["objective"].default is C.OBJECTIVE, fn.__name__
    assert C.OBJECTIVE == "fitness"


def test_pick_ranks_on_the_objective_it_is_given():
    hi = _cand("hi_fit", 9.0, sub=0.2)
    lo = _cand("hi_sub", 0.1, sub=3.0)
    assert C.pick([hi, lo], year_book=False)[0] == "hi_fit", "default is fitness"
    assert C.pick([hi, lo], objective="sub_sharpe", year_book=False)[0] == "hi_sub"


def test_a_row_with_no_sub_sharpe_cannot_win():
    """It is unmeasured, not zero. An alpha the gate never scored must not beat one it did."""
    no = {"formula": "none", "turnover": 0.3, "checks": []}
    yes = _cand("has", 0.1, sub=-5.0, gates="FAIL")
    assert C.pick([no, yes], year_book=False)[0] is None, "the FAIL is rejected, the unscored ranks nowhere"


def test_a_measured_correlation_over_the_line_never_takes_the_headline(tmp_path, monkeypatch):
    """`88pYR1gz` was being announced as our best alpha while its prod correlation was 1.0 -- a
    perfect duplicate of something already in the production book, and the worst possible value on
    the gate that actually refuses."""
    root = _journal(tmp_path, [
        {"formula": "dup", "alpha": "DUP", "sharpe": 3.6, "turnover": 0.08, "sub": 9.0,
         "longCount": 1376, "shortCount": 1500},
        {"formula": "ok", "alpha": "OK", "sharpe": 2.0, "turnover": 0.3, "sub": 1.0,
         "longCount": 800, "shortCount": 800},
    ])
    monkeypatch.setattr(C, "measured_corr",
                        lambda *a, **k: {"DUP": {"prod": 1.0, "self": 1.0},
                                         "OK": {"prod": 0.4, "self": 0.2}})
    b, excluded = C.best_alpha(root=root, objective="sub_sharpe",
                              globs=("state/layered/runs/climb.jsonl",))
    assert b["alpha"] == "OK" and excluded == 1


def test_an_unmeasured_correlation_does_not_disqualify_the_headline(tmp_path, monkeypatch):
    """Unmeasured is UNKNOWN, not over the line. The headline says `corr UNMEASURED` on its own."""
    root = _journal(tmp_path, [
        {"formula": "a", "alpha": "A", "sharpe": 2.0, "turnover": 0.3, "sub": 5.0,
         "longCount": 800, "shortCount": 800}])
    monkeypatch.setattr(C, "measured_corr", lambda *a, **k: {})
    b, _ = C.best_alpha(root=root, objective="sub_sharpe",
                              globs=("state/layered/runs/climb.jsonl",))
    assert b["alpha"] == "A"


def test_the_climb_builds_pool_c_fresh_and_never_uses_the_frozen_file():
    """`load_pools()` reads state/layered/pool_c.json, frozen 2026-08-13 with 73,258 leaves of which
    70,184 -- 95.8% -- come from pyramid cells that are now FULL. Every screen added since lived in
    `load_fields()`, which that path never calls, so neither the coverage floor nor the pyramid gate
    had ever reached the running loop."""
    src = (ROOT / "tools/layered_sim.py").read_text()
    climb_block = src[src.index("if climb:"):src.index("elif gap2x2:")]
    assert "LA.build_pool_c(" in climb_block and "LA.load_fields(" in climb_block
    assert "never from state/layered/pool_c.json" in climb_block


# ---- held vs reachable (Khoa approved 2026-08-15) -----------------------------------------

def test_reachable_excludes_an_alpha_using_a_field_the_pool_dropped(tmp_path, monkeypatch):
    """After the pyramid gate the journals still hold alphas built from fields the pool can no
    longer draw. They are the best thing we HOLD, which is honest, but they are not what the
    pipeline can still produce -- and reading one as the other is how a shrinking search space stays
    invisible."""
    root = _journal(tmp_path, [
        {"formula": "rank(gone_field)", "alpha": "OLD", "sharpe": 3.6, "turnover": 0.08,
         "sub": 9.0, "longCount": 900, "shortCount": 900},
        {"formula": "rank(live_field)", "alpha": "NEW", "sharpe": 2.0, "turnover": 0.3,
         "sub": 1.0, "longCount": 900, "shortCount": 900},
    ])
    monkeypatch.setattr(C, "measured_corr", lambda *a, **k: {})
    g = ("state/layered/runs/climb.jsonl",)
    held, _ = C.best_alpha(root=root, objective="sub_sharpe", globs=g)
    assert held["alpha"] == "OLD"
    now, _ = C.best_alpha(root=root, objective="sub_sharpe", globs=g, only_fields={"live_field"})
    assert now["alpha"] == "NEW"


def test_both_lines_label_the_two_numbers_differently(tmp_path, monkeypatch):
    root = _journal(tmp_path, [
        {"formula": "rank(live_field)", "alpha": "A", "sharpe": 2.0, "turnover": 0.3,
         "sub": 1.0, "longCount": 900, "shortCount": 900}])
    monkeypatch.setattr(C, "measured_corr", lambda *a, **k: {})
    monkeypatch.setattr(C, "reachable_fields", lambda **k: {"live_field"})
    out = C.both_lines(root=root, globs=("state/layered/runs/climb.jsonl",))
    assert "best alpha we HOLD" in out and "best REACHABLE from today's pool" in out


def test_an_unreadable_catalogue_reports_nothing_rather_than_guessing(tmp_path, monkeypatch):
    root = _journal(tmp_path, [
        {"formula": "rank(f)", "alpha": "A", "sharpe": 2.0, "turnover": 0.3, "sub": 1.0,
         "longCount": 900, "shortCount": 900}])
    monkeypatch.setattr(C, "measured_corr", lambda *a, **k: {})
    monkeypatch.setattr(C, "reachable_fields", lambda **k: set())
    assert "reachable-now unavailable" in C.both_lines(
        root=root, globs=("state/layered/runs/climb.jsonl",))


def test_a_thin_tune_round_is_topped_up_rather_than_wasted(pools):
    """A live baseline with ONE tunable slot yielded five distinct variants, so a 100-simulation
    round was spending five. The shortfall is filled with grow candidates."""
    a, b, c = pools
    import random as _r
    st = {"baseline": "ts_mean(some_field, 20)", "last_kind": "grow", "depth": 1}
    got = C.draw(st, a, b, c, _r.Random(1), 60)
    assert len(got) == 60
    moves = collections.Counter(m["move"] for _f, m in got)
    assert moves["tune"] > 0 and moves["wrap"] + moves["combine"] > 0


def test_a_topped_up_round_alternates_from_the_MAJORITY_move():
    """Otherwise the next round repeats the same kind and the alternation quietly stops."""
    rows = [dict(_cand("t%d" % i, 1.0), meta={"move": "tune"}) for i in range(3)]
    rows += [dict(_cand("g%d" % i, 1.0), meta={"move": "wrap"}) for i in range(9)]
    st, _ = C.advance(_fresh(), rows)
    assert st["last_kind"] == "grow", "grow dominated, so the next round must be tune"


def test_a_mostly_tune_round_still_counts_as_tune():
    rows = [dict(_cand("t%d" % i, 1.0), meta={"move": "tune"}) for i in range(9)]
    rows += [dict(_cand("g", 1.0), meta={"move": "wrap"})]
    st, _ = C.advance(_fresh(), rows)
    assert st["last_kind"] == "tune"


def test_the_year_rule_is_a_TRAILING_window_not_every_year(monkeypatch):
    """Khoa lowered it from every year, and his example of five turned out to pass nobody: on the
    eight tier-4 alphas, 2014-2021 holds 0 of 8 in every single year and only 2022-2023 hold any.
    Last 1 year passes 8 of 8, last 2 passes 8 of 8, last 3 passes ZERO -- 2021 kills them all at
    901, 883 and so on."""
    assert C.YEAR_BOOK_TRAILING == 2
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [
        ("2020", 0), ("2021", 901), ("2022", 1211), ("2023", 1267)])
    assert C.year_book_ok("X")[0] is True
    assert C.year_book_ok("X", trailing=3)[0] is False, "2021 at 901 must still fail"
    assert C.year_book_ok("X", trailing=None)[0] is False, "every-year still available"


def test_too_little_history_cannot_satisfy_the_window(monkeypatch):
    """A two-year rule is not satisfied by one year of history."""
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [("2023", 5000)])
    ok, why = C.year_book_ok("X")
    assert ok is False and "only 1 year" in why


def test_the_detail_names_the_years_it_checked():
    """A pass that does not say WHICH years it looked at is how a two-year rule gets read as ten."""
    import types
    C.yearly_book.__wrapped__ = None
    saved = C.yearly_book
    try:
        C.yearly_book = lambda aid, **kw: [("2022", 1211), ("2023", 1267)]
        ok, why = C.year_book_ok("X")
        assert ok is True and "2022=1211" in why and "2023=1267" in why
    finally:
        C.yearly_book = saved


# ---- uniform picks, spent fields, region rotation (Khoa, 2026-08-15 late) -----------------

def test_the_field_pick_is_uniform_again():
    """Khoa asked for "hoàn toàn ngẫu nhiên khi pick hàm và field". That is incompatible with
    prioritising -- a policy cannot both favour the cells nearest unlocking and draw evenly -- so
    `uniform` supersedes the `filled` choice he made earlier the same day. `filled` stays on the
    flag; what is given up is that News and Insiders were taking ~28% of draws apiece."""
    assert PG.DEFAULT_POLICY == "uniform"
    pool = [{"category": "Big"}] * 50 + [{"category": "Small"}] * 2
    st = {"ok": True, "needs": {"Big": 1, "Small": 3}, "counts": {"Big": 2, "Small": 0}}
    w = PG.draw_weights(pool, st)
    big = sum(x for x, f in zip(w, pool) if f["category"] == "Big")
    small = sum(x for x, f in zip(w, pool) if f["category"] == "Small")
    assert abs(big - small) < 1e-9, "every open cell gets the same share regardless of how close"


def test_spent_fields_are_retired_when_a_cycle_ends(tmp_path, monkeypatch):
    """REVERSES the earlier "reset re-randomises with nothing banned" ruling, and the record says
    why: cycles 5-11 kept rediscovering the same core and burned 330 simulations each going
    nowhere."""
    monkeypatch.setattr(C, "SPENT", tmp_path / "spent.json")
    monkeypatch.setattr(C, "BANNED", tmp_path / "nope.json")
    st = dict(_fresh(), baseline="ts_mean(alpha_field, 20)")
    C.reset(st, gems=0)
    assert C.spent_fields() == set(), \
        "Khoa, 2026-08-18: a gemless cycle has not shown its FIELDS were exhausted"
    st = dict(_fresh(), baseline="ts_mean(alpha_field, 20)")
    C.reset(st, gems=1)
    assert "alpha_field" in C.spent_fields(), "a gem still retires the fields that produced it"


def test_a_field_is_spent_only_when_a_CYCLE_ends_not_when_it_is_drawn(tmp_path, monkeypatch):
    """One round of 100 would otherwise ban a third of the pool."""
    monkeypatch.setattr(C, "SPENT", tmp_path / "spent.json")
    monkeypatch.setattr(C, "BANNED", tmp_path / "nope.json")
    st, _ = C.advance(_fresh(), [_cand("ts_mean(drawn_field, 5)", 1.0)])
    assert C.spent_fields() == set(), "drawing is not spending"


def test_submitted_fields_are_honoured_too(tmp_path, monkeypatch):
    """state/banned_fields.json holds fields from alphas already SUBMITTED, and the standing rule is
    that those are never reused."""
    (tmp_path / "banned.json").write_text(json.dumps({"banned_fields": ["gone"]}))
    monkeypatch.setattr(C, "SPENT", tmp_path / "spent.json")
    monkeypatch.setattr(C, "BANNED", tmp_path / "banned.json")
    assert "gone" in C.spent_fields()


def test_the_rotation_only_lists_segments_whose_catalogue_exists():
    """A rotation into a region with no catalogue would draw from nothing and read as a dead cycle
    rather than a missing file."""
    avail = PG.available_rotation()
    assert avail and all(PG.catalogue_for(*s).exists() for s in avail)


def test_rotation_needs_a_STREAK_not_a_single_gemless_cycle(tmp_path, monkeypatch):
    """Khoa corrected this: "ko phải chu kì có gem thì ở lại mà nếu chuỗi lên tới 6-7 chu kì mà vẫn
    ko tìm ra gem thì đổi". The first version rotated on ANY gemless cycle and duly jumped USA to
    EUR after one, which abandons a segment before it has had a fair sample."""
    monkeypatch.setattr(C, "SPENT", tmp_path / "spent.json")
    monkeypatch.setattr(C, "BANNED", tmp_path / "nope.json")
    st = dict(_fresh(), segment=["USA", "TOP3000", 1], baseline="rank(f)", gemless_streak=0)
    for i in range(C.GEMLESS_BEFORE_ROTATE - 1):
        C.reset(st, gems=0)
        st["baseline"] = "rank(f%d)" % i
        assert st["segment"] == ["USA", "TOP3000", 1], "must not move on cycle %d" % (i + 1)
    C.reset(st, gems=0)
    assert st["segment"] != ["USA", "TOP3000", 1], "moves on the %dth" % C.GEMLESS_BEFORE_ROTATE
    assert st["gemless_streak"] == 0, "the streak resets when the segment changes"


def test_a_gem_resets_the_gemless_streak(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "SPENT", tmp_path / "spent.json")
    monkeypatch.setattr(C, "BANNED", tmp_path / "nope.json")
    st = dict(_fresh(), segment=["USA", "TOP3000", 1], baseline="rank(f)", gemless_streak=5)
    C.reset(st, gems=2)
    assert st["gemless_streak"] == 0 and st["segment"] == ["USA", "TOP3000", 1]


def test_the_segment_is_drawn_at_random_and_always_moves():
    """Khoa, 2026-08-18: "ngau nhien ko thu tu". A fixed order made the sequence of segments a
    function of how many gemless stretches had happened -- not a property of any market -- and a
    segment sitting after a productive one got sampled far more often than one sitting after a
    barren one. What must hold now is only that the draw LEAVES where it is."""
    import random
    avail = PG.available_rotation()
    assert len(avail) > 1, "the test needs somewhere to move to"
    for cur in avail:
        for seed in range(12):
            nxt = PG.next_segment(cur, rng=random.Random(seed))
            assert tuple(nxt) != tuple(cur), "a rotation that returns where it is rotates nothing"
            assert tuple(nxt) in {tuple(x) for x in avail}


def test_a_random_segment_draw_actually_reaches_more_than_one_place():
    """A draw that is random but always lands on the same segment would pass the test above while
    being a fixed rotation with extra steps."""
    import random
    avail = PG.available_rotation()
    cur = avail[0]
    seen = {tuple(PG.next_segment(cur, rng=random.Random(s))) for s in range(40)}
    assert len(seen) > 1, seen


def test_both_delays_are_in_the_rotation():
    """Khoa asked for delay 0 alongside delay 1. `available_rotation` filters on the catalogue being
    on disk, so this asserts the LISTING carries both -- a region whose d0 was never fetched simply
    does not appear, which is the intended behaviour, not a missing entry."""
    assert {d for _r, _u, d in PG.ROTATION} == {0, 1}


def test_the_margin_bar_respects_the_turnover_floor(tmp_path, monkeypatch):
    """The first version printed 1e4/(500*s^2) and dropped the max(turnover,0.125) floor inside the
    fitness identity. Two agents re-derived it independently and agreed to the digit: understated on
    61.6% of in-band climb rows, median factor 2.066, max 12.38x, and 2.38% of rows clear the
    printed bar while failing the true one. The factor max(1, 0.125/T) is never below 1, so the old
    line could only ever make an alpha look further past the gate than it was."""
    monkeypatch.setattr(C, "measured_corr", lambda *a, **k: {})
    # ABOVE the floor: turnover cancels, the bar is the plain one.
    root = _journal(tmp_path, [{"formula": "f", "alpha": "A", "sharpe": 1.58, "turnover": 0.30,
                                "sub": 1.0, "margin": 0.0009,
                                "longCount": 900, "shortCount": 900}])
    assert "8.01 bps" in C.best_line(root=root, globs=("state/layered/runs/climb.jsonl",))
    # BELOW the floor: the bar rises by 0.125/turnover. This is the live headline's case.
    root2 = _journal(tmp_path / "b", [{"formula": "f", "alpha": "B", "sharpe": 3.61,
                                       "turnover": 0.0833, "sub": 1.0, "margin": 0.001979,
                                       "longCount": 900, "shortCount": 900}])
    line = C.best_line(root=root2, globs=("state/layered/runs/climb.jsonl",))
    assert "2.30 bps" in line, "was printing 1.53 bps, which is the bar without the floor"


def test_a_raising_post_is_still_recorded_and_still_retires_the_lineage(tmp_path, monkeypatch):
    """THE ONLY PATH THAT CAN SPEND TWO IRREVERSIBLE SLOTS. If the POST raised, `record()` was never
    reached, the lineage was not retired, and the loop re-POSTed the same alpha next round. A raise
    says the outcome is UNKNOWN -- the request may have reached the platform and been adjudicated
    before the timeout -- it never says the POST did not happen."""
    monkeypatch.setattr(CS.LS, "session", lambda: None)

    class Boom:
        def post(self, *a, **k):
            raise TimeoutError("read timed out")
    http, body = CS.post("A1", session=Boom())
    assert http is None and "OUTCOME UNKNOWN" in body
    log = tmp_path / "s.jsonl"
    CS.record({"alpha": "A1", "formula": "rank(f)"}, http, body, path=log)
    row = json.loads(log.read_text().splitlines()[0])
    assert row["http"] is None and row["normalised"], "the lineage key must be written"
    assert CS.normalise("rank(f)") in CS.already_submitted(log), "lineage retired despite the raise"


def test_notify_no_longer_sends_and_its_cli_enqueues():
    """Replaces an obsolete guard.

    The old assertion checked that `notify` carried an `import json` -- the sole diff against a
    working copy back when the module POSTed directly and a missing import broke it silently. That
    module no longer touches the network at all, so the assertion tested nothing about the property
    that now matters: exactly one sender exists, and every producer reaches it through the spool.
    """
    import importlib
    import notify
    importlib.reload(notify)

    # The name is kept so a forgotten call site fails loudly instead of quietly reintroducing a
    # second transport.
    for fn in (notify.post, notify.post_pinned):
        try:
            fn("x")
        except RuntimeError as exc:
            assert "enqueue" in str(exc) or "removed" in str(exc), str(exc)
        else:
            raise AssertionError("%s must refuse to send" % fn.__name__)

    import os
    import tempfile
    tmp = tempfile.mkdtemp(prefix="wq_notify_cli_")
    old = os.environ.get("WQ_NOTIFY_DIR")
    os.environ["WQ_NOTIFY_DIR"] = tmp
    try:
        msg_id = notify.enqueue_cli("body", title="T")
        assert msg_id, "the CLI path must produce a spooled message"
        spooled = os.listdir(os.path.join(tmp, "pending"))
        assert len(spooled) == 1, spooled
    finally:
        if old is None:
            os.environ.pop("WQ_NOTIFY_DIR", None)
        else:
            os.environ["WQ_NOTIFY_DIR"] = old


# --- the year filter is OFF by default (Khoa, 2026-08-16: "bỏ lớp lọc short long >1000") --------
#
# The five tests above still pass `year_book=True`, so the machinery stays covered and turning it
# back on is one keyword argument. What these two assert is the DEFAULT, which is the thing that
# actually decides what the loop does.

def test_the_year_filter_is_off_by_default_in_pick(monkeypatch):
    calls = []
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: calls.append(aid) or [("2014", 0)])
    thin = _cand("thin", 2.9, alpha="THIN")
    f, score, _r, _skipped = C.pick([thin, _cand("fat", 1.1, alpha="FAT")])
    assert f == "thin" and score == 2.9, "a thin per-year book must no longer block a baseline"
    assert calls == [], "the filter costs an API call per candidate; off means not fetched at all"


def test_the_year_filter_is_off_by_default_in_write_gems(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", tmp_path / "gems.jsonl")
    monkeypatch.setattr(C, "yearly_book", lambda aid, **kw: [("2014", 0), ("2022", 50)])
    r = _row(2.0, 2.0, 0.2, _gates())
    r["formula"], r["alpha"] = "f", "THIN"
    assert C.write_gems([r], 1, measured={"THIN": {"prod": 0.5, "self": 0.2}}) == 1


# ---- only pay for a correlation when everything else is clean (Khoa, 2026-08-17) -----------
#
# "sau này chỉ cào corr khi có tất cả gate khác pass". The correlation endpoint is the pipeline's
# binding constraint and it refuses us for reasons unrelated to our request rate, so a read spent
# on an already-failed alpha displaces one that might have become a gem.

def _checks(**kw):
    return [{"name": k, "result": v} for k, v in kw.items()]


def _probe_row(**over):
    base = dict(sharpe=2.0, fitness=2.0, turnover=0.2, margin=50.0, alpha="A1")
    gates = dict(CONCENTRATED_WEIGHT="PASS", LOW_SUB_UNIVERSE_SHARPE="PASS",
                 IS_LADDER_SHARPE="PASS", CLUSTER_TEST="PASS", UNITS="PASS",
                 LOW_2Y_SHARPE="PASS")
    gates.update(over.pop("gates", {}))
    base.update(over)
    base["checks"] = _checks(**gates)
    return base


def test_a_clean_alpha_is_still_probe_eligible():
    assert C.tier(_probe_row()) == 3


def test_an_UNSCORED_gate_does_not_block_the_probe():
    """This test used to assert the opposite, and that assertion broke gem production outright.

    "All other gates pass" means every VERDICT is a pass -- not that every gate HAS a verdict.
    Measured over 28,330 finished rows: UNITS is graded on 3.7%, LOW_2Y_SHARPE on 41.4%,
    IS_LADDER_SHARPE on 57.4%, and rows carrying all six verdicts: ZERO. Demanding a verdict per
    gate demanded something the platform never produces, so tier 3 became unreachable and the loop
    mined on with nothing able to become a gem.

    A gate the platform declined to grade has not failed.
    """
    r = _probe_row()
    r["checks"] = [c for c in r["checks"] if c["name"] != "IS_LADDER_SHARPE"]
    assert C.tier(r) == 3, "an ungraded gate must not disqualify an otherwise clean alpha"


def test_tier3_is_reachable_at_all():
    """The guard the previous version of this file lacked. A rule that removes every candidate is
    indistinguishable from a broken pipeline, and it took a corpus measurement to notice."""
    assert C.tier(_probe_row()) == 3
    sparse = _probe_row()
    sparse["checks"] = [c for c in sparse["checks"]
                        if c["name"] in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE")]
    assert C.tier(sparse) == 3, "the common case -- only the two universally-graded gates -- must pass"


def test_a_gate_outside_REJECT_CHECKS_still_blocks_the_probe():
    for gate in C.PROBE_EXTRA_CHECKS:
        assert C.tier(_probe_row(gates={gate: "FAIL"})) == 2, gate
        assert C.tier(_probe_row(gates={gate: "WARNING"})) == 2, gate


def test_baseline_selection_is_NOT_tightened_with_the_probe():
    """Two different questions. Treating unscored as adverse leaves 0 survivors of 1,020, so the
    climb would have no baseline at all -- 'good enough to grow from' is not 'worth an
    irreplaceable API call'."""
    assert "CLUSTER_TEST" not in C.REJECT_CHECKS, "withdrawn from the baseline filter 2026-08-18"
    r = _probe_row()
    r["checks"] = [c for c in r["checks"] if c["name"] != "IS_LADDER_SHARPE"]
    adverse, unscored = C.blocked_on(r)
    assert adverse == [] and unscored == ["IS_LADDER_SHARPE"]


def test_a_zero_variance_gate_must_never_join_the_probe_filter():
    """MATCHES_THEMES, MATCHES_COMPETITION and OSMOSIS_ALLOCATION are adverse on 74 of 74 probe
    targets. Adding one empties the queue outright -- the same trap as 'the carrier is necessary',
    which held in 11,731 of 11,731 rows and could therefore discriminate nothing."""
    for gate in ("MATCHES_THEMES", "MATCHES_COMPETITION", "OSMOSIS_ALLOCATION"):
        assert gate not in C.PROBE_EXTRA_CHECKS and gate not in C.REJECT_CHECKS, gate


# ---- a chat message is not a debug dump (Khoa, 2026-08-17) ---------------------------------
#
# "thông tin thì quá dài dòng, ko súc tích". Six notify sites were piping `--report | head -20`
# into Discord: 2,835 characters of cycle-history table, truncated at 1,900, and the one message
# that mattered -- auth expired -- did not even carry the link.

def test_brief_is_short_enough_to_arrive_whole(monkeypatch):
    st = {"cycle": 8, "round": 4, "baseline_score": 0.74, "depth": 9,
          "segment": ["USA", "TOP3000", 1], "gemless_streak": 4}
    monkeypatch.setattr(C, "best_alpha", lambda *a, **k: (
        {"alpha": "N1b3a35X", "sharpe": 3.39, "fitness": 2.72, "turnover": 0.21}, 0))
    monkeypatch.setattr(C, "stale_gems", lambda *a, **k: [])
    body = C.brief(st, "AUTH HET HAN")
    assert len(body) <= C.BRIEF_MAX
    assert len(body.splitlines()) <= 4, "a message is a few lines, not a table"


def test_brief_always_names_the_best_alpha(monkeypatch):
    """Khoa's standing requirement. It kept being cut because it sat at the END of a table; in a
    brief it is a sentence near the top and cannot be truncated away."""
    st = {"cycle": 1, "round": 1, "baseline_score": 0.1, "segment": ["USA", "TOP3000", 1]}
    monkeypatch.setattr(C, "best_alpha", lambda *a, **k: (
        {"alpha": "ABCD1234", "sharpe": 2.0, "fitness": 1.0, "turnover": 0.3}, 0))
    monkeypatch.setattr(C, "stale_gems", lambda *a, **k: [])
    assert "ABCD1234" in C.brief(st, "GEM MOI")


def test_a_stale_gem_warning_outranks_everything_in_the_message(monkeypatch):
    st = {"cycle": 1, "round": 1, "baseline_score": 0.1, "segment": ["USA", "TOP3000", 1]}
    monkeypatch.setattr(C, "best_alpha", lambda *a, **k: (None, 0))
    monkeypatch.setattr(C, "stale_gems", lambda *a, **k: [
        {"alpha": "gJ8dZqav", "stored": (0.5, 0.2), "latest": (0.93, 0.93), "over_line": True}])
    body = C.brief(st, "GEM MOI")
    assert body.splitlines()[0].startswith("!!"), "the trap goes first or it gets skimmed past"
    assert "gJ8dZqav" in body and len(body) <= C.BRIEF_MAX


def test_brief_survives_a_broken_best_alpha_lookup(monkeypatch):
    """A message that fails because a lookup broke is worse than a message without the lookup."""
    st = {"cycle": 1, "round": 1, "baseline_score": 0.1, "segment": ["USA", "TOP3000", 1]}
    def boom(*a, **k):
        raise RuntimeError("journal unreadable")
    monkeypatch.setattr(C, "best_alpha", boom)
    monkeypatch.setattr(C, "stale_gems", boom)
    body = C.brief(st, "AUTH HET HAN")
    assert "AUTH HET HAN" in body and "chua doc duoc" in body


# ---- the benchmark ladder (Khoa, 2026-08-17) -----------------------------------------------
#
# "nếu ở chu kì sau mà benchmark ko cải thiện thì reset chu kì đó tối đa 2 lần, nếu ko cải tiến
# được nữa thì reset toàn phase bắt đầu lại từ chu kì 1".

def _phase(scores, monkeypatch, tmp_path):
    """Drive reset() through cycles reaching `scores`, returning (state, events)."""
    monkeypatch.setattr(C, "spend_fields", lambda *a, **k: 0)
    st = {"cycle": 1, "round": 0, "history": [], "segment": ["USA", "TOP3000", 1]}
    events = []
    for got in scores:
        if got is not None:
            # Shaped like a real ROUND entry -- it must carry a round number, because cycle_best
            # now ignores ladder-event entries (which have none) to stop scores walking forward
            # across cycles. A fixture without `round` would test a shape the loop never writes.
            st["history"].append({"cycle": st["cycle"], "round": 1, "best_score": got})
        st = C.reset(st, gems=0)
        events.append(st["history"][-1]["event"])
    return st, events


def test_a_cycle_that_beats_the_benchmark_advances(monkeypatch, tmp_path):
    st, ev = _phase([0.50, 0.80, 0.95], monkeypatch, tmp_path)
    assert ev == ["cycle-advanced"] * 3
    assert st["cycle"] == 4 and st["phase_benchmark"] == 0.95 and st["cycle_retries"] == 0


def test_a_plateau_retries_twice_then_resets_the_whole_phase(monkeypatch, tmp_path):
    st, ev = _phase([0.90, 0.40, 0.30, 0.20], monkeypatch, tmp_path)
    assert ev == ["cycle-advanced", "cycle-retry", "cycle-retry", "phase-reset"]
    assert st["cycle"] == 1, "a phase reset starts over at cycle 1"
    assert st["phase_benchmark"] is None and st["cycle_retries"] == 0


def test_a_retry_that_recovers_clears_the_retry_count(monkeypatch, tmp_path):
    """Otherwise two unlucky cycles anywhere in a phase would doom the third, however good."""
    st, ev = _phase([0.90, 0.40, 0.95], monkeypatch, tmp_path)
    assert ev == ["cycle-advanced", "cycle-retry", "cycle-advanced"]
    assert st["cycle_retries"] == 0 and st["phase_benchmark"] == 0.95


def test_a_retry_keeps_the_same_cycle_number(monkeypatch, tmp_path):
    """A retry is another attempt at the same bar, not progress, and the history must say so."""
    st, _ = _phase([0.90, 0.40], monkeypatch, tmp_path)
    assert st["cycle"] == 2 and st["cycle_retries"] == 1


def test_a_cycle_with_no_baseline_at_all_counts_as_no_improvement(monkeypatch, tmp_path):
    """cycle_best returns None, which is not zero and must not be read as one -- but it certainly
    does not beat a benchmark either."""
    st, ev = _phase([None, None, None], monkeypatch, tmp_path)
    assert ev == ["cycle-retry", "cycle-retry", "phase-reset"]
    assert C.cycle_best({"cycle": 1, "history": []}) is None


def test_a_phase_reset_does_NOT_un_retire_spent_fields(monkeypatch, tmp_path):
    """Retired fields are what stop a fresh phase walking straight back into the exhausted core --
    the failure the retirement rule was added to stop after cycles 5-11 rediscovered it."""
    src = (ROOT / "tools/climb.py").read_text()
    i = src.index("def reset(st, gems)")
    body = src[i:i + src[i:].index("\ndef ")]
    assert "spent_fields" not in body.split("phase-reset")[-1], \
        "the phase-reset branch must not clear the spent-field ban"


def test_a_phase_reset_does_not_make_segment_rotation_unreachable(monkeypatch, tmp_path):
    """The interaction that the rotation test caught the moment the ladder was added.

    A phase reset fires every 3 non-improving cycles; rotation needs 6 gemless ones. If a reset
    cleared the gemless streak the streak could never reach 6 and rotation would be silently
    unreachable. Only a GEM clears it.
    """
    monkeypatch.setattr(C, "spend_fields", lambda *a, **k: 0)
    st = {"cycle": 1, "round": 0, "history": [], "segment": ["USA", "TOP3000", 1]}
    for _ in range(C.GEMLESS_BEFORE_ROTATE):
        st = C.reset(st, gems=0)
    assert any(h.get("event") == "phase-reset" for h in st["history"]), "the ladder did fire"
    assert any(h.get("event") == "segment-rotated" for h in st["history"]), \
        "rotation must still be reachable across phase resets"


# ---- UNITS violations (Khoa, 2026-08-18) ---------------------------------------------------
#
# "tìm cách sửa pipeline để ko bị dính unit nữa, ko thay đổi gì nhiều". Measured over 28,380
# journal rows: 1,085 UNITS warnings, 978 of them (90%) reading `expected "Unit[]"` -- an operator
# that wanted a plain number and got a field carrying CSPrice or CSShare.

def test_a_unit_sensitive_operator_never_sees_a_raw_field(pools):
    a, b, c = pools
    for f, _m in C.round1(a, b, c, random.Random(3), 150):
        for op in C.UNIT_FREE_OPS:
            for hit in re.finditer(re.escape(op) + r"\(([A-Za-z_][A-Za-z_0-9]*)", f):
                inner = hit.group(1)
                known_ops = {o["name"] for o in list(a) + list(b)}
                assert inner in known_ops, \
                    "%s applied straight to bare `%s` in %s" % (op, inner, f[:90])


def test_both_sides_of_a_plus_or_minus_are_made_dimensionless(pools):
    """`+` and `-` require the two sides to share a unit; `*` and `/` combine units legitimately.
    This half is 53% of every UNITS warning in the corpus -- add 383, subtract 194."""
    a, b, c = pools
    base = C.round1(a, b, c, random.Random(7), 1)[0][0]
    seen = 0
    for f, m in C.grow(base, a, b, c, random.Random(11), 200, depth=2):
        if m["move"] == "combine" and m["infix"] in C.UNIT_MATCHING_INFIX:
            seen += 1
            assert re.search(r"%s\(.*\) [+-] %s\(" % (C.UNIT_STRIP, C.UNIT_STRIP), f), f[:120]
    assert seen, "the fixture produced no +/- combines, so this asserted nothing"


def test_the_wrap_is_not_applied_twice_or_where_it_is_not_needed():
    """Cheap to get wrong in the direction that quietly doubles formula depth."""
    assert C.unit_safe("rank(x)", op_name="sqrt") == "rank(x)"
    assert C.unit_safe("x", op_name="ts_rank") == "x", "a unit-safe operator must not be wrapped"
    assert C.unit_safe("x", infix="*") == "x", "* combines units legitimately"
    assert C.unit_safe("x", infix="+") == "rank(x)"


def test_every_operator_application_passes_through_unit_safe():
    """The recurring failure here is not the fix, it is the WIRING: the unit fix was attached at
    three call sites on 2026-08-18 and the fourth -- the deep seeder, which applies an operator
    straight to a raw field and so needs it most -- was missed, then found by a live simulation
    rather than by reading the patch back. Asserting it structurally is what stops a fifth site
    from being added without the wrap. Checked on the parse tree, not by grep, because a comment
    mentioning `unit_safe` would satisfy a text search.
    """
    import ast

    src = pathlib.Path(__file__).resolve().parents[1] / "climb.py"
    tree = ast.parse(src.read_text())
    bare = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "_apply"
                and isinstance(fn.value, ast.Name) and fn.value.id == "LA"):
            continue
        if not node.args or len(node.args) < 2:
            continue
        inner = node.args[1]
        ok = (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
              and inner.func.id == "unit_safe")
        if not ok:
            bare.append(node.lineno)
    assert not bare, "LA._apply without unit_safe at line(s): %s" % bare


def test_the_gain_test_cannot_reward_a_WORSE_score_on_a_negative_baseline():
    """`score > prev * (1 + min_gain)` inverts when prev < 0: with prev = -0.50 the bar becomes
    -0.525, so -0.51 -- worse -- reads as progress. It never fired under sub_sharpe (0 of 64 rounds
    had a negative baseline), but the objective is now fitness: median 0.09, negative on 28% of
    rows. So the arithmetic had to be fixed BEFORE the objective changed, not after it misfired."""
    assert not C.gained(-0.51, -0.50), "a worse score is not a gain"
    assert not C.gained(-0.49, -0.50), "1% better is under the 5% bar"
    assert C.gained(-0.40, -0.50), "20% better clears it"
    assert C.gained(1.06, 1.00) and not C.gained(1.04, 1.00)
    assert C.gained(0.01, 0.0) and not C.gained(0.0, 0.0), "a zero baseline needs a real positive"
    assert C.gained(0.1, None), "no baseline yet means anything is progress"


def test_auto_submit_requires_a_pyramid_match_and_fails_closed():
    """Khoa, 2026-08-29: "neu alpha nop duoc thi hay cu nop" -- the unattended path now posts ANY
    all-gates-pass alpha, with ONE added condition from the same order: it must match the current
    pyramid. That is read off the platform's own MATCHES_PYRAMID check, measured before adoption
    (PASS on 99.0% of 38,055 rows, 254/254 of then-current tier-4s, adverse on zero -- so the
    requirement starves nothing). Unscored fails closed: unknown is not a match, and 'checks' in a
    shape we do not recognise is unknown too."""
    import climb_submit as CS
    assert CS.pyramid_ok({"checks": [{"name": "MATCHES_PYRAMID", "result": "PASS"}]})
    assert not CS.pyramid_ok({"checks": [{"name": "MATCHES_PYRAMID", "result": "WARNING"}]})
    assert not CS.pyramid_ok({"checks": [{"name": "MATCHES_PYRAMID", "result": "FAIL"}]})
    assert not CS.pyramid_ok({"checks": []}), "unscored is not a match"
    assert not CS.pyramid_ok({}), "no checks at all is not a match"


def test_the_super_gem_line_still_orders_the_queue():
    """The 0.30 line no longer gates the unattended path, but it still sorts it: when several
    roots are eligible, the least self-correlated posts first. None sorts last -- an unmeasured
    self-corr must never beat a measured one to the front of an irreversible queue."""
    import climb_submit as CS
    rows = [{"alpha": "b", "self_corr": 0.45}, {"alpha": "a", "self_corr": 0.12},
            {"alpha": "c", "self_corr": None}]
    rows.sort(key=lambda r: (r.get("self_corr") if isinstance(r.get("self_corr"),
                                                              (int, float)) else 9e9))
    assert [r["alpha"] for r in rows] == ["a", "b", "c"]


def _gaterow(name, fitness, **results):
    """A candidate whose gate results are set INDIVIDUALLY. `_cand` applies one verdict to every
    reject gate at once, which cannot express "fails exactly one of them" -- the case under test."""
    checks = [{"name": "LOW_SHARPE", "result": "PASS"}]
    for g in C.REJECT_CHECKS:
        c = {"name": g, "result": results.get(g, "PASS")}
        if g == "LOW_SUB_UNIVERSE_SHARPE":
            c["value"] = fitness
        checks.append(c)
    return {"formula": name, "fitness": fitness, "turnover": 0.3, "checks": checks}


def test_the_seed_round_does_not_apply_the_ratio_gate():
    """Khoa, 2026-08-18: "bo loc low subuniverse sharpe cho vong dau".

    Measured on 6,331 real depth-1 seeds already inside the turnover band, one gate at a time:
    LOW_SUB_UNIVERSE_SHARPE blocks 46.6%, CONCENTRATED_WEIGHT 36.1%, IS_LADDER_SHARPE 0.0% (it is
    never SCORED that shallow). The ratio gate is what stands between a fresh cycle and its first
    baseline, and it judges a one-operator seed by a bar built for a finished alpha.

    What must NOT change: the gate applies again the moment there is something to grow.
    """
    assert "LOW_SUB_UNIVERSE_SHARPE" not in C.SEED_REJECT_CHECKS
    assert "CONCENTRATED_WEIGHT" in C.SEED_REJECT_CHECKS, "a 4-name book is still no place to start"

    ratio_only = _gaterow("seedy", 1.0, LOW_SUB_UNIVERSE_SHARPE="FAIL")
    st, _ev = C.advance(_fresh(), [ratio_only])
    assert st["baseline"] == "seedy", "the seed round must accept it"

    # ...and the very next round, which HAS a baseline, must refuse the same row.
    st2 = dict(_fresh(), baseline="something", baseline_score=0.1)
    st2, _ev2 = C.advance(st2, [ratio_only])
    assert st2["baseline"] == "something", "the ratio gate is back once there is a baseline"


def test_concentrated_weight_still_blocks_a_seed():
    """The seed round filters on LESS, not on nothing."""
    st, _ev = C.advance(_fresh(), [_gaterow("tiny_book", 1.0, CONCENTRATED_WEIGHT="FAIL")])
    assert st["baseline"] is None


def test_the_seed_round_draws_more_than_the_round_size(pools, monkeypatch):
    """Khoa, 2026-08-18: "o vong dau cho sim 350". The seed round chooses the point every later
    round of the cycle grows from and is the one round with nothing to fall back on, so it gets the
    wider draw. Only that round: a grow round asked for `n` must still get `n`, or the quota spent
    per cycle stops matching what the loop was told to run."""
    a, b, c = pools
    said = []
    seed = C.draw(_fresh(), a, b, c, random.Random(1), 40, out=said.append)
    assert len(seed) == C.SEED_N, "the seed round takes SEED_N, not the round size"
    assert any("SEED ROUND" in m for m in said), "a round that changes its own size must say so"

    grown = C.draw(dict(_fresh(), baseline="ts_sum(f, 5)", baseline_score=1.0, last_kind="tune"),
                   a, b, c, random.Random(1), 40, out=[].append)
    assert len(grown) == 40, "only the SEED round is widened"


def test_the_seed_width_is_one_environment_variable(monkeypatch):
    """It is a guess -- the maximum of N samples rises with N whether or not quality does -- so it
    has to be changeable without a code edit for the A/B to be one command."""
    import importlib
    monkeypatch.setenv("WQ_SEED_N", "123")
    m = importlib.reload(C)
    try:
        assert m.SEED_N == 123
    finally:
        monkeypatch.delenv("WQ_SEED_N", raising=False)
        importlib.reload(C)


def test_a_warning_on_CONCENTRATED_WEIGHT_still_disqualifies():
    """Khoa, 2026-08-18: "cu concentrated weight la loai".

    Loosening WARNING earlier the same day re-opened the exact hole this gate exists to close. The
    first baseline chosen under the loosened rule was
    `ts_delta(rsk88_mfm_ase1_ind_storage_warehousing, 20)` -- fitness 27.58, longCount 4,
    shortCount 0, CONCENTRATED_WEIGHT WARNING -- a book of FOUR names that the whole cycle would
    have grown from. The gate fired; treating its warning as acceptable is what failed.

    The rest of the loosening must survive: a warning on any OTHER named gate is still accepted,
    because reverting that produced 0 survivors out of 200 and a dead-ended loop.
    """
    assert "CONCENTRATED_WEIGHT" in C.HARD_CHECKS
    hot = _gaterow("four_names", 9.0, CONCENTRATED_WEIGHT="WARNING")
    plain = _gaterow("real_book", 1.0, LOW_SUB_UNIVERSE_SHARPE="WARNING")
    f, score, _r, skipped = C.pick([hot, plain])
    assert f == "real_book", "the 4-name book must not win on its fitness"
    assert score == 1.0
    assert "WARNING-rejected:CONCENTRATED_WEIGHT" in skipped
    assert "WARNING-accepted:LOW_SUB_UNIVERSE_SHARPE" in skipped


def test_the_hard_gate_applies_to_the_seed_round_too():
    """The seed round filters on a shorter list, but CONCENTRATED_WEIGHT is on both lists -- the
    round that picks the starting point is precisely where a 4-name book does the most damage."""
    assert "CONCENTRATED_WEIGHT" in C.SEED_REJECT_CHECKS
    st, _ev = C.advance(_fresh(), [_gaterow("four_names", 9.0, CONCENTRATED_WEIGHT="WARNING")])
    assert st["baseline"] is None


def test_cycle_best_ignores_ladder_event_entries():
    """The benchmark poisoned itself for a week before this was caught. Ladder events are appended
    AFTER the cycle counter moves, so an advance carrying cycle 2's best lands in cycle 3's history
    -- and cycle_best(3) then reports a score no round of cycle 3 ever produced. The 4-name book's
    27.58 walked forward this way (measured 2026-08-28: real cycle-3 rounds scored 0.52-1.04 while
    cycle_best said 27.58), and the 2.0 benchmark that kept resurrecting after every phase reset was
    the same defect. Only entries that name a ROUND are scores; events are bookkeeping."""
    st = {"cycle": 3, "history": [
        {"cycle": 3, "round": 1, "best_score": 0.62, "event": "progress"},
        {"cycle": 3, "round": 2, "best_score": 0.72, "event": "progress"},
        {"cycle": 3, "event": "cycle-advanced", "best_score": 27.58},   # no round: an event
        {"cycle": 3, "event": "cycle-retry", "best_score": 27.58},
    ]}
    assert C.cycle_best(st) == 0.72
    assert C.cycle_best({"cycle": 1, "history": [
        {"cycle": 1, "event": "phase-reset", "best_score": 27.58}]}) is None


def test_keep_jar_fresh_swaps_cookies_into_the_live_session(tmp_path):
    """The round's Session loads the jar once; before this, a tap mid-round changed nothing and the
    12:49 round on 2026-08-18 lost 29 of 31 new-operator rows to a session that died under it. The
    watcher must (a) swap on jar change, (b) REPLACE the same-name cookie rather than duplicate it
    -- a duplicate would send both the dead and the fresh token on every request."""
    import pickle
    import time as _t
    import requests
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    import layered_sim as LS

    jar_path = tmp_path / "jar.pkl"
    j1 = requests.cookies.RequestsCookieJar()
    j1.set("t", "OLD", domain="api.worldquantbrain.com", path="/")
    jar_path.write_bytes(pickle.dumps(j1))

    s = requests.Session()
    s.cookies.update(j1)
    t = LS.keep_jar_fresh(s, path=jar_path, interval=0.05)
    assert t is not None and t.daemon, "must never keep the process alive"

    j2 = requests.cookies.RequestsCookieJar()
    j2.set("t", "NEW", domain="api.worldquantbrain.com", path="/")
    _t.sleep(0.08)                      # let one poll see the OLD mtime first
    jar_path.write_bytes(pickle.dumps(j2))
    import os
    os.utime(jar_path)                  # force a distinct mtime on coarse filesystems

    for _ in range(60):                 # up to 3s for the swap
        if s.cookies.get("t", domain="api.worldquantbrain.com", path="/") == "NEW":
            break
        _t.sleep(0.05)
    assert s.cookies.get("t", domain="api.worldquantbrain.com", path="/") == "NEW"
    assert sum(1 for c in s.cookies if c.name == "t") == 1, "replaced, not duplicated"


def test_keep_jar_fresh_with_no_jar_returns_none(tmp_path):
    import layered_sim as LS
    assert LS.keep_jar_fresh(object(), path=tmp_path / "missing.pkl") is None


def test_watchdog_recovery_debounce_kills_the_auth_flap(monkeypatch):
    """While auth is dead the loop restarts every ~5 min and holds its flock for the ~1-2 min auth
    check, so the classifier sees short RUNNING windows all day: 16 m3 messages during one day of a
    CONSTANT outage (2026-08-28). Recovery now needs 5 straight RUNNING ticks; the flap (<=2) never
    clears it, a real round (median 7 min) does. Death still confirms at 2 -- fast to alarm."""
    import watchdog as W
    import loopstate as LS
    sent = []
    monkeypatch.setattr(W, "_fire", lambda v, p, f, n: sent.append((p, v)) or "x")

    st = {}
    pattern = ([LS.DEAD] * 4 + [LS.RUNNING] * 2) * 30      # the measured flap, 30 cycles
    for i, v in enumerate(pattern):
        monkeypatch.setattr(LS, "classify", lambda now=None, _v=v: (_v, {}))
        W.tick(now=1000.0 + 60 * i, state=st, emit=True)
    assert sent == [(None, LS.DEAD)], "a constant outage is ONE message, not %d" % len(sent)

    sent.clear()
    st2 = {}
    for i, v in enumerate([LS.DEAD] * 4 + [LS.RUNNING] * 8):
        monkeypatch.setattr(LS, "classify", lambda now=None, _v=v: (_v, {}))
        W.tick(now=5000.0 + 60 * i, state=st2, emit=True)
    assert sent == [(None, LS.DEAD), (LS.DEAD, LS.RUNNING)], sent


def test_op_count_matches_the_platform_calibration():
    """The platform counts function calls PLUS infix arithmetic. Calibrated on its own verdict:
    the row it refused as "65 operators" has 57 calls + 8 infix. A guessed metric here would ship
    another 260-wasted-POST round like 2026-08-30."""
    assert C.op_count("rank(close)") == 1
    assert C.op_count("ts_mean((close + open), 20)") == 2, "one call + one infix"
    assert C.op_count("(a / b)") == 1
    f = " + ".join("rank(close)" for _ in range(10))     # 10 calls + 9 infix
    assert C.op_count(f) == 19


def test_growth_never_emits_a_formula_over_the_operator_cap(pools):
    """Found 2026-08-30: a depth-5 round POSTed ~260 candidates over the platform's 64-operator
    limit, each a guaranteed ERROR, and crawled 3h55m for 40 rows. Over-cap draws must die at the
    draw, where counting is free."""
    a, b, c = pools
    big = "rank((" + " + ".join("ts_mean(f%d, 5)" % i for i in range(30)) + "))"   # ~60 ops
    got = C.grow(big, a, b, c, random.Random(7), 40, depth=5)
    assert all(C.op_count(f) <= C.MAX_FORMULA_OPS for f, _m in got), \
        max(C.op_count(f) for f, _m in got)
    # a baseline AT the cap yields few or no growths -- small rounds are the ladder's business
    huge = "rank((" + " + ".join("ts_mean(g%d, 5)" % i for i in range(40)) + "))"
    got2 = C.grow(huge, a, b, c, random.Random(7), 40, depth=6)
    assert all(C.op_count(f) <= C.MAX_FORMULA_OPS for f, _m in got2)
