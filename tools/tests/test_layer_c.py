"""Layer C — the conditional / market gate. Every assertion traces to a stated rule or a real failure.

The failures this file exists to prevent, all of them already paid for on the live account:

  * 12,643 arity violations in 2,000 draws, because operators whose `definition` is written INFIX
    were being CALLED. The six comparison operators are in exactly that class -- their definitions
    are `input1 > input2` and nothing else -- so they must never appear as `greater(`.
  * 3 of 4 live simulations returned `Required attribute "lookback" must have a value.`, because a
    parameter whose default is a NAME was read as optional. `trade_when(x, y, z)` and
    `if_else(input1, input2, input 3)` have THREE required arguments and no defaults at all.
  * `trade_when` and the Logical category are lifted OUT of the layer-A/B exclusion for layer C
    ONLY. If they leak back into A or B the exclusion has silently been repealed, so that is tested
    rather than trusted.
"""
import ast
import pathlib
import random
import re
import socket
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layer_c as LC          # noqa: E402
import layered_alpha as LA    # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a test opened a socket")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def pool():
    return LC.build_pool()


@pytest.fixture(scope="module")
def ab_pools():
    """Layer A/B/D exactly as the existing composer builds them, so the gate is tested around a real
    layer-D expression and not around a toy string."""
    ops = LA.load_operators()
    a, b, _ = LA.split_layers(ops)
    c = [{"kind": "field", "expr": "close", "why": "x", "dataset": "d", "category": "Price Volume"},
         {"kind": "ratio", "expr": "(revenue / total_assets)", "why": "y", "dataset": "d",
          "category": "Fundamental"}]
    return a, b, c


# ------------------------------------------------------------------ the real signatures

def test_all_twelve_gate_operators_exist_in_the_platform_catalogue():
    ops = LC.load_gate_operators()
    assert set(ops) == set(LC.GATE_OPS), set(LC.GATE_OPS) - set(ops)


def test_trade_when_is_transformational_not_logical():
    """Read from `fetched/operators.json`, not inferred from the name. It matters because
    `split_layers` routes Transformational into layer A -- and `trade_when` is excluded there."""
    assert LC.load_gate_operators()["trade_when"]["category"] == "Transformational"


def test_trade_when_and_if_else_have_three_required_arguments_and_no_defaults():
    """`trade_when(x, y, z)` and `if_else(input1, input2, input 3)`. Nothing here is optional, and
    the `z` of trade_when in particular has no default -- omitting it is the `Required attribute`
    error class."""
    ops = LC.load_gate_operators()
    assert ops["trade_when"]["arity"] == (3, 3)
    assert ops["trade_when"]["optional"] == []
    assert ops["if_else"]["arity"] == (3, 3)
    assert ops["if_else"]["optional"] == []


def test_the_comparison_operators_have_no_documented_call_form():
    """Their `definition` is infix (`input1 > input2`), so the call-signature parser cannot parse
    them AT ALL. That is the signal there is no call form, and it is why this module emits them
    infix -- the same fix that removed 12,643 arity violations for add/subtract/multiply/divide."""
    ops = LC.load_gate_operators()
    for name in LC.INFIX_COMPARISONS:
        assert ops[name]["infix"] is True
        assert ops[name]["arity"] is None
        assert "(" not in ops[name]["definition"], ops[name]["definition"]
        assert LA._params(ops[name]["definition"]) == ([], [])


def test_the_four_call_logicals_are_calls_with_the_arity_their_definitions_give():
    ops = LC.load_gate_operators()
    assert ops["and"]["arity"] == (2, 2)
    assert ops["or"]["arity"] == (2, 2)
    assert ops["not"]["arity"] == (1, 1)
    assert ops["is_nan"]["arity"] == (1, 1)
    for name in LC.CALL_LOGICALS:
        assert ops[name]["infix"] is False


def test_a_symbolic_default_would_still_be_read_as_required():
    """The rule that cost 3 of 4 live simulations, re-checked through the parser layer C imports so
    the two layers cannot drift apart."""
    req, opt = LA._params("ts_backfill(x,lookback = d, k=1)")
    assert "d" in req and "k" in opt


# ------------------------------------------------------------------ the rendered formula

def _arity_table():
    """Call arity for every operator that may legitimately appear as `name(`.

    INFIX arithmetic and the INFIX comparisons are excluded because they must never appear as calls
    at all -- that is a separate, stricter assertion below.
    """
    t = {}
    for o in LA.load_operators():
        name = o["name"]
        if name in LA.INFIX or name in LC.INFIX_COMPARISONS:
            continue
        req, opt = LA._params(o.get("definition"))
        t[name] = (1 + len(req), 1 + len(req) + len(opt))
    return t


def _violations(expr, table):
    out = []
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\(", expr):
        name = m.group(1)
        if name not in table:
            continue
        j, depth, args = m.end(), 1, 1
        while j < len(expr) and depth:
            ch = expr[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 1:
                args += 1
            j += 1
        lo, hi = table[name]
        if not (lo <= args <= hi):
            out.append("%s got %d want %d..%d" % (name, args, lo, hi))
    return out


def _renders(pool, ab_pools, n, seed):
    """n gated alphas: a real layer-A/B/D composition wrapped in a real layer-C gate."""
    a, b, c = ab_pools
    rng = random.Random(seed)
    leafless = [e for e in pool if not e["needs_leaf"]]
    out = []
    for _ in range(n):
        inner, _m = LA.compose(a, b, c, rng)
        alt, _m2 = LA.compose(a, b, c, rng)
        e = rng.choice(pool)
        ex = rng.choice([x for x in leafless if x["cond"] != e["cond"]])
        f, meta = LC.render_gate(e, inner, rng, exit_entry=ex, expr2=alt, leaf="close")
        out.append((f, meta, inner))
    return out


def test_800_renders_have_no_arity_violation_and_balanced_parens(pool, ab_pools):
    """THE REGRESSION TEST FOR THE WHOLE FILE, over more than the 500 required."""
    table = _arity_table()
    for f, _meta, _inner in _renders(pool, ab_pools, 800, 7):
        assert f.count("(") == f.count(")"), f[:160]
        v = _violations(f, table)
        assert not v, "%s in %s" % (v, f[:200])


def test_no_comparison_operator_is_ever_written_as_a_call(pool, ab_pools):
    """`greater(a, b)` is undocumented. The platform's own worked examples use `volume > adv20` and
    `volume >= ts_mean(volume, 5)`."""
    for f, _meta, _inner in _renders(pool, ab_pools, 600, 8):
        for name in LC.INFIX_COMPARISONS:
            assert not re.search(r"\b%s\s*\(" % name, f), "%s called in %s" % (name, f[:160])
    for e in pool:
        for name in LC.INFIX_COMPARISONS:
            assert not re.search(r"\b%s\s*\(" % name, e["cond"]), e["cond"]


def test_trade_when_always_gets_all_three_arguments(pool, ab_pools):
    """z has no default. `trade_when(cond, alpha)` is the `Required attribute` error class."""
    for f, meta, _inner in _renders(pool, ab_pools, 600, 9):
        if not f.startswith("trade_when("):
            continue
        assert _top_level_args(f, "trade_when") == 3, f[:200]
        if meta["mode"] == "hold":
            assert f.endswith(", -1)"), f[-40:]


def test_if_else_always_gets_all_three_arguments(pool, ab_pools):
    for f, _meta, _inner in _renders(pool, ab_pools, 600, 10):
        if not f.startswith("if_else("):
            continue
        assert _top_level_args(f, "if_else") == 3, f[:200]


def _top_level_args(expr, name):
    m = re.match(re.escape(name) + r"\(", expr)
    assert m, expr[:80]
    j, depth, args = m.end(), 1, 1
    while j < len(expr) and depth:
        ch = expr[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 1:
            args += 1
        j += 1
    return args


def test_every_required_window_is_actually_supplied(pool):
    """A `d` left empty is the `Required attribute` error class. Every windowed operator in a layer-C
    condition must carry its window."""
    needs_d = {o["name"] for o in LA.load_operators()
               if "d" in LA._params(o.get("definition"))[0]}
    for e in pool:
        for name in needs_d:
            for m in re.finditer(r"\b%s\(" % re.escape(name), e["cond"]):
                seg = e["cond"][m.end():]
                assert "," in seg, "%s called with no window in %s" % (name, e["cond"])


def test_equality_is_only_ever_used_against_an_integer_quantity(pool):
    """`close == ts_mean(close, 20)` is true on a set of measure zero and an alpha gated on it never
    trades. The only `==` / `!=` in the pool is `days_from_last_change(x) == 0`, whose left side is a
    day COUNT -- and that is the platform's own documented trade_when recipe."""
    for e in pool:
        if e["cmp"] in ("==", "!="):
            assert e["cond"].startswith("days_from_last_change("), e["cond"]
            assert e["cond"].endswith(" 0"), e["cond"]


def test_a_condition_needing_a_leaf_fails_closed_when_none_is_given(pool):
    """An unsubstituted `{leaf}` shipped to a simulation is literal text in a formula. A bare
    `except: pass` hiding exactly this class already cost this project days."""
    e = next(x for x in pool if x["needs_leaf"])
    with pytest.raises(ValueError):
        LC.render_gate(e, "rank(close)", random.Random(1), mode="hold", leaf=None)
    f, _m = LC.render_gate(e, "rank(close)", random.Random(1), mode="hold", leaf="volume")
    assert "{leaf}" not in f


def test_no_render_ever_leaves_an_unsubstituted_placeholder(pool, ab_pools):
    for f, _meta, _inner in _renders(pool, ab_pools, 500, 11):
        assert "{" not in f and "}" not in f, f[:160]


def test_the_modes_that_need_a_second_expression_refuse_to_guess(pool):
    e = next(x for x in pool if not x["needs_leaf"])
    rng = random.Random(2)
    with pytest.raises(ValueError):
        LC.render_gate(e, "rank(close)", rng, mode="exit")
    with pytest.raises(ValueError):
        LC.render_gate(e, "rank(close)", rng, mode="pick")


def test_an_exit_condition_identical_to_the_trigger_is_refused(pool):
    """z is evaluated first: z true -> NaN. If z is the same predicate as x, the position is closed
    on exactly the days the trigger fires, so the alpha can only ever be NaN or a held stale value.
    Same class as the counter-on-a-counter rule in layer B: a simulation spent for no information."""
    e = next(x for x in pool if not x["needs_leaf"])
    with pytest.raises(ValueError):
        LC.render_gate(e, "rank(close)", random.Random(3), mode="exit", exit_entry=e)


def test_every_mode_is_reachable_and_recorded(pool, ab_pools):
    seen = {meta["mode"] for _f, meta, _inner in _renders(pool, ab_pools, 400, 12)}
    assert seen == set(LC.MODES), seen


# ------------------------------------------------------------------ the gate stays in layer C

def test_the_gate_operators_are_absent_from_layer_a_and_layer_b():
    """The exclusion is LIFTED FOR LAYER C ONLY. If any of the twelve reaches pool A or pool B, the
    exclusion has been silently repealed."""
    a, b, _dropped = LA.split_layers(LA.load_operators())
    names = {o["name"] for o in a} | {o["name"] for o in b}
    assert not (names & LC.GATE_OPS), names & LC.GATE_OPS


def test_a_layer_ab_composition_never_contains_a_gate_operator(ab_pools):
    a, b, c = ab_pools
    rng = random.Random(13)
    for _ in range(400):
        f, _m = LA.compose(a, b, c, rng)
        for name in LC.GATE_OPS:
            assert not re.search(r"\b%s\s*\(" % name, f), "%s in a layer A/B formula" % name
        for tok in (">", "<", "==", "!="):
            assert tok not in f, "%s in a layer A/B formula: %s" % (tok, f[:160])


def test_the_gate_wraps_the_alpha_and_never_reaches_inside_it(pool, ab_pools):
    """The layer-D expression is passed through VERBATIM, and every gate token sits outside its span.
    That is what keeps the twelve operators in layer C by construction rather than by a check."""
    for f, _meta, inner in _renders(pool, ab_pools, 500, 14):
        i = f.find(inner)
        assert i >= 0, "the inner alpha was not preserved verbatim"
        span = range(i, i + len(inner))
        for name in LC.GATE_OPS:
            for m in re.finditer(r"\b%s\s*\(" % name, f):
                assert m.start() not in span, "%s appeared inside the layer-D expression" % name


# ------------------------------------------------------------------ the pool's own claims

def test_every_entry_carries_a_reason_an_origin_and_a_kind(pool):
    """A condition with no stated reading is an arbitrary comparison, which is what this layer is
    supposed not to be."""
    for e in pool:
        assert e["why"] and len(e["why"]) > 30, e
        assert e["origin"] in ("EX-ANTE", "SPECULATION"), e
        assert e["kind"] in ("regime", "event", "hygiene", "position"), e
        assert e["reading"], e
        assert e["family"], e
        assert e["scope"] in LC._SCOPE_ORDER, e
        assert isinstance(e["unverified"], list), e


def test_the_speculative_readings_are_labelled_speculation(pool):
    """`close > ts_mean(close, d)` is a FACT about today; calling it a TREND asserts persistence, and
    no field description and no experiment here establishes persistence. Same for reading
    `close > vwap` as buying pressure."""
    for e in pool:
        if e["name"].startswith(("price_vs_moving_average", "close_vs_vwap")):
            assert e["origin"] == "SPECULATION", e["name"]
        if e["name"].startswith(("volume_vs_own_mean", "volume_vs_adv20", "volume_ts_rank",
                                 "realised_vol_vs_own_level", "range_vs_own_mean",
                                 "return_shock", "driver_")):
            assert e["origin"] == "EX-ANTE", e["name"]


def test_the_data_availability_check_is_not_counted_as_a_market_regime(pool):
    """`not(is_nan(x))` is data hygiene. Labelling it a regime would be the rationalisation."""
    for e in pool:
        if "is_nan" in e["cond"]:
            assert e["kind"] == "hygiene", e["name"]
    assert any(e["kind"] == "hygiene" for e in pool)


def test_every_two_sided_regime_is_drawable_in_both_directions(pool):
    """If only the "high participation" side were ever emitted, a measured effect could not be
    separated from "gating at all reduces turnover" -- a different claim. The control is built into
    the pool rather than argued for afterwards."""
    for stem, hi, lo in (("volume_vs_own_mean", "hi", "lo"),
                         ("volume_vs_adv20", "hi", "lo"),
                         ("volume_ts_rank", "hi", "lo"),
                         ("realised_vol_vs_own_level", "hi", "lo"),
                         ("price_vs_moving_average", "hi", "lo"),
                         ("range_vs_own_mean", "hi", "lo"),
                         ("return_shock", "hi", "lo"),
                         ("close_vs_vwap", "hi", "lo")):
        assert any(e["name"].startswith("%s_%s" % (stem, hi)) for e in pool), stem
        assert any(e["name"].startswith("%s_%s" % (stem, lo)) for e in pool), stem


def test_all_twelve_operators_are_actually_exercised(pool):
    """Reading a signature and then never using the operator is how a signature stays unverified."""
    used = set()
    for e in pool:
        used |= set(e["ops"])
    used |= {"and", "or"}                       # via combine()
    used |= {"trade_when", "if_else"}           # via render_gate()
    assert LC.GATE_OPS <= used, LC.GATE_OPS - used


def test_combine_builds_a_two_argument_call_and_inherits_the_weaker_origin(pool):
    exante = next(e for e in pool if e["origin"] == "EX-ANTE" and not e["needs_leaf"])
    spec = next(e for e in pool if e["origin"] == "SPECULATION")
    c = LC.combine(exante, spec, "and")
    assert c["cond"].startswith("and(")
    assert _top_level_args(c["cond"], "and") == 2
    assert c["origin"] == "SPECULATION", "a compound is only as well-founded as its weakest part"
    o = LC.combine(exante, exante, "or")
    assert _top_level_args(o["cond"], "or") == 2 and o["origin"] == "EX-ANTE"
    with pytest.raises(ValueError):
        LC.combine(exante, exante, "xor")


def test_a_combined_condition_still_renders_without_arity_violations(pool):
    table = _arity_table()
    rng = random.Random(15)
    leafless = [e for e in pool if not e["needs_leaf"]]
    for _ in range(200):
        c = LC.combine(rng.choice(leafless), rng.choice(leafless), rng.choice(("and", "or")))
        f, _m = LC.render_gate(c, "rank(ts_delta(close, 5))", rng, mode="hold")
        assert f.count("(") == f.count(")")
        assert not _violations(f, table), f[:200]


def test_the_conditions_are_built_only_from_fields_that_exist_and_are_fully_covered():
    """A gate built on a sparse field introduces NaN of its own, and then the alpha's coverage is a
    property of the gate rather than of the signal. Checked against the real field catalogue."""
    import json
    have = {}
    p = ROOT / "fetched/rc/fields/USA_TOP3000_d1.jsonl"
    for line in p.read_text(errors="ignore").splitlines():
        if not line.startswith("{"):
            continue
        r = json.loads(line)
        if (r.get("_region"), r.get("_delay"), r.get("_universe")) == ("USA", 1, "TOP3000"):
            have[r.get("id")] = r
    allowed = ("volume", "adv20", "close", "high", "low", "vwap", "returns", "cap",
               "market", "sector", "industry")
    for f in allowed:
        assert f in have, f
        assert have[f]["coverage"] == 1.0 and have[f]["dateCoverage"] == 1.0, f
    for g in ("market", "sector", "industry"):
        assert have[g]["type"] == "GROUP", g
    used = set()
    for e in LC.build_pool():
        used |= set(re.findall(
            r"\b(volume|adv20|close|high|low|vwap|returns|cap|open|market|sector|industry|"
            r"subindustry|country|exchange|sharesout)\b", e["cond"]))
    assert used <= set(allowed), used - set(allowed)


# ------------------------------------------------------- round 2: the families and their controls

#: The only family whose statistic lives on a lattice that CONTAINS its threshold, so `>` and `>=`
#: are different conditions there and only one token is emitted.
_ONE_TOKEN_FAMILIES = {"persistence"}


def test_every_entry_name_is_unique_so_a_row_can_be_attributed_to_one_condition(pool):
    """Before the comparison tag was appended, `volume_vs_adv20_hi` was the name of BOTH the `>` and
    the `>=` entry. A terminal row could then not be attributed to one of them, and the `>` vs `>=`
    noise floor -- the pool's only null control on a continuous quantity -- could not be estimated."""
    names = [e["name"] for e in pool]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, dupes
    conds = [e["cond"] for e in pool]
    assert len(set(conds)) == len(conds), "duplicate condition strings"


def test_the_gt_ge_noise_floor_control_is_intact_on_every_continuous_family(pool):
    """`>` and `>=` select the SAME days when the boundary has measure zero, so a measured difference
    between them is the pipeline's own noise and nothing else. That control only exists if both
    tokens are actually emitted, in matched pairs."""
    by_name = {e["name"]: e for e in pool}
    for e in pool:
        if e["family"] in _ONE_TOKEN_FAMILIES or e["cmp"] is None:
            continue
        twin = {"_gt": "_ge", "_ge": "_gt", "_lt": "_le", "_le": "_lt"}.get(e["name"][-3:])
        if twin is None:                       # `==` / `!=` have no twin and must not have one
            assert e["cmp"] in ("==", "!="), e["name"]
            continue
        assert e["name"][:-3] + twin in by_name, "%s has no %s twin" % (e["name"], twin)


def test_the_lattice_family_emits_one_comparison_token_per_direction(pool):
    """(#days above - #days below)/d lives on a lattice of step 2/d that CONTAINS 0.6 for d in
    (5, 10, 20). There `> 0.6` and `>= 0.6` are different conditions, nothing here distinguishes
    them, and emitting both would put two conditions under one reading."""
    toks = {e["cmp"] for e in pool if e["family"] in _ONE_TOKEN_FAMILIES}
    assert toks == {">", "<"}, toks


def test_the_new_two_sided_families_are_in_the_pool_in_both_directions(pool):
    """Same requirement round 1 imposed, checked for everything round 2 added: with only one side, a
    measured effect cannot be separated from 'gating at all reduces turnover'."""
    for stem in ("xs_rank_of_driver", "xs_rank_of_relative_volume", "xs_rank_of_cap",
                 "xs_dispersion_returns_market", "xs_dispersion_relative_volume_market",
                 "xs_dispersion_returns_sector", "close_above_mean_persistently",
                 "volume_above_adv20_persistently", "vol_vs_sector_vol",
                 "relative_volume_rank_in_sector", "relative_volume_rank_in_industry",
                 "return_vs_sector_return"):
        for side in ("hi", "lo"):
            assert any(e["name"].startswith("%s_%s" % (stem, side)) for e in pool), (stem, side)


def test_scope_says_whether_the_gate_selects_names_or_switches_the_whole_book(pool):
    """A market_wide condition has the same value for every instrument, so it turns the whole book on
    and off; a per_name condition reshapes the cross-section. Pooling the two would compare two
    different interventions."""
    by_scope = {}
    for e in pool:
        by_scope.setdefault(e["scope"], set()).add(e["family"])
    assert by_scope["market_wide"] == {"xs_dispersion"}
    assert by_scope["group_wide"] == {"xs_dispersion"}
    assert by_scope["constant"] == {"wrapper_null"}
    for e in pool:
        if e["family"] == "xs_dispersion":
            assert e["scope"] == ("market_wide" if ", market)" in e["cond"] else "group_wide"), e
        elif e["family"] != "wrapper_null":
            assert e["scope"] == "per_name", e["name"]


def test_the_wrapper_null_control_is_a_predicate_that_is_true_by_construction(pool):
    """`close` has coverage 1.0 and dateCoverage 1.0, so `not(is_nan(close))` is true for every name
    on every day. `trade_when(TRUE, alpha, -1)` should be the IDENTITY per the trade_when docs -- if
    it is not, the wrapper and not the condition is producing the effect, and every gated-vs-ungated
    comparison in the round is confounded."""
    ctl = [e for e in pool if e["family"] == "wrapper_null"]
    assert len(ctl) == 1, ctl
    assert ctl[0]["cond"] == "not(is_nan(close))"
    assert ctl[0]["scope"] == "constant" and ctl[0]["kind"] == "hygiene"
    assert not ctl[0]["needs_leaf"], "the control must not depend on the layer-D driver"


def test_group_mean_is_never_used_because_it_is_documented_as_the_harmonic_mean(pool):
    """`group_mean` is documented as 'the harmonic mean of a data field within each specified group'.
    A harmonic mean is undefined at zero and dominated by the smallest values, so on returns or on
    any quantity that can be near zero it is not the average anything here wants to read. The
    cross-sectional sd is built from the group_neutralize / group_zscore identity instead."""
    assert "group_mean" in {o["name"] for o in LA.load_operators()}, "the ban must be on a real op"
    for e in pool:
        assert "group_mean" not in e["cond"], e["name"]


def test_the_cross_sectional_sd_is_the_documented_identity_and_not_a_proxy(pool):
    """group_neutralize(x, g) = x - mean_g(x) and group_zscore(x, g) = (x - mean_g(x)) / sd_g(x), so
    the ratio IS sd_g(x). It is only that identity if BOTH halves use the same x and the same g."""
    seen = 0
    for e in pool:
        for m in re.finditer(r"\(group_neutralize\((.+?), (\w+)\) / group_zscore\((.+?), (\w+)\)\)",
                             e["cond"]):
            assert m.group(1) == m.group(3), e["cond"]
            assert m.group(2) == m.group(4), e["cond"]
            seen += 1
    assert seen >= 2, seen
    assert LC._xs_sd("returns", "market") == \
        "(group_neutralize(returns, market) / group_zscore(returns, market))"


def test_the_undocumented_assumption_is_recorded_on_exactly_the_entries_that_make_it(pool):
    """`unverified` exists so the deploy round can run the fully-documented subset FIRST instead of
    discovering an undocumented form by spending simulations on it."""
    for e in pool:
        if e["family"] == "xs_dispersion":
            assert e["unverified"], e["name"]
            assert "same group mean" in e["unverified"][0].lower().replace("  ", " "), e["unverified"]
        else:
            assert e["unverified"] == [], (e["name"], e["unverified"])


def test_a_whole_book_multiplier_is_flagged_as_possibly_a_no_op(pool):
    """`if_else(cond, alpha * k, alpha)` with a condition identical for every name multiplies the
    WHOLE cross-section by k. If the platform normalises the alpha vector to book size that is the
    ungated alpha exactly. This module has NOT established that it does, so the row is flagged and
    left runnable -- paired against its ungated partner it measures the normalisation."""
    wide = next(e for e in pool if e["scope"] == "market_wide")
    narrow = next(e for e in pool if e["scope"] == "per_name" and not e["needs_leaf"])
    rng = random.Random(21)
    _f, m = LC.render_gate(wide, "rank(close)", rng, mode="scale")
    assert m["degenerate_if_normalised"] is True
    _f, m = LC.render_gate(wide, "rank(close)", rng, mode="hold")
    assert m["degenerate_if_normalised"] is False
    _f, m = LC.render_gate(narrow, "rank(close)", rng, mode="scale")
    assert m["degenerate_if_normalised"] is False


def test_the_meta_carries_the_factors_the_comparison_is_stratified_on(pool, ab_pools):
    """178 conditions cannot each have an arm; family, mode, scope and origin can. If a terminal row
    does not carry them the round has no factor to compare on."""
    for _f, meta, _inner in _renders(pool, ab_pools, 200, 22):
        for k in ("family", "mode", "scope", "kind", "origin", "layer_c", "unverified"):
            assert k in meta and meta[k] is not None, k


def test_persistence_measures_the_run_instead_of_asserting_it(pool):
    """`price_vs_moving_average` is SPECULATION in this pool because being above a mean is a fact
    about ONE day while 'trend' asserts it keeps holding. The persistence family puts the run INTO
    the arithmetic -- sign() is documented as +1/-1/0, so its d-day mean is a day count -- which is
    why its reading is EX-ANTE. Neither family claims the run continues."""
    fam = [e for e in pool if e["family"] == "persistence"]
    assert fam
    for e in fam:
        assert e["origin"] == "EX-ANTE", e["name"]
        assert e["cond"].startswith("ts_mean(sign("), e["cond"]
        # A word-ban on "continues" was the first version of this assertion and it FAILED on the
        # disclaimer "No claim is made that the run continues" -- the same class as the wrong test
        # regex in the 2026-08-02 audit. The forward-looking words are what to ban.
        for word in (" will ", "future", "precedes", "leads to"):
            assert word not in e["why"].lower(), (word, e["why"])
    assert any("no claim is made that the run continues" in e["why"].lower() for e in fam)
    for e in pool:
        if e["family"] == "price_vs_moving_average":
            assert e["origin"] == "SPECULATION", e["name"]


def test_the_cross_sectional_position_family_is_marked_as_depending_on_the_signal(pool):
    """`rank(<leaf>)` gates on the alpha's OWN driver, so it is not independent of the signal -- it
    restricts the alpha to its own tail rather than to a state of the market. `needs_leaf` is the
    flag the analysis must filter on; the other two position conditions are market facts."""
    fam = {e["name"]: e for e in pool if e["family"] == "xs_position"}
    assert fam
    for name, e in fam.items():
        assert e["kind"] == "position", name
        assert e["needs_leaf"] is name.startswith("xs_rank_of_driver"), name


def test_every_new_family_renders_without_arity_violations(pool):
    """The round-1 arity sweep draws uniformly from the pool, so a family of 12 entries out of 178
    can be under-sampled. Every new family is rendered explicitly, in every mode it allows."""
    table = _arity_table()
    rng = random.Random(23)
    leafless = [e for e in pool if not e["needs_leaf"]]
    fams = {"xs_position", "xs_dispersion", "persistence", "relative_regime", "wrapper_null"}
    covered = set()
    for e in pool:
        if e["family"] not in fams:
            continue
        covered.add(e["family"])
        ex = next(x for x in leafless if x["cond"] != e["cond"])
        for mode in LC.MODES:
            f, _m = LC.render_gate(e, "rank(ts_delta(close, 5))", rng, mode=mode,
                                   exit_entry=ex, expr2="zscore(close)", leaf="close")
            assert f.count("(") == f.count(")"), f[:200]
            assert not _violations(f, table), "%s in %s" % (_violations(f, table), f[:200])
            assert "{" not in f and "}" not in f, f[:200]
    assert covered == fams, fams - covered


# ------------------------------------------------------------------ it cannot simulate or submit

def test_layer_c_has_no_network_path_at_all():
    """Agent 4 may not simulate or submit. Checked by walking the AST, so a mention in a comment
    cannot satisfy it and a string cannot hide an endpoint."""
    tree = ast.parse((ROOT / "tools" / "layer_c.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "http" not in node.value.lower(), node.value[:80]
            assert "/submit" not in node.value, node.value[:80]
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            for m in mods:
                assert m.split(".")[0] not in ("requests", "urllib", "http", "socket"), m
