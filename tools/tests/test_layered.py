"""The layered composer must produce formulas the platform accepts, and must never submit.

Every assertion here traces to something that actually went wrong on the live account:

  * 12,643 arity violations over 2,000 draws, because `add`/`multiply`/`divide` were being CALLED
    with one operand. Fixed by writing them infix.
  * 3 of 4 live simulations returned `Required attribute "lookback" must have a value.`, because
    `ts_backfill(x, lookback = d, k=1)` was parsed as having an optional `lookback`. The `= d` is a
    placeholder, not a default.
  * 4 of 4 in an earlier batch returned ERROR while `ts_step` (a day counter that takes a LENGTH)
    and `densify` (which compresses a GROUPING FIELD) were being wrapped around a signal.
"""
import collections
import json
import pathlib
import random
import re
import socket
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layered_alpha as LA  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a test opened a socket")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def pools():
    ops = LA.load_operators()
    a, b, _ = LA.split_layers(ops)
    c = [{"kind": "field", "expr": "close", "why": "x", "dataset": "d", "category": "Price Volume"},
         {"kind": "ratio", "expr": "(revenue / total_assets)", "why": "y", "dataset": "d",
          "category": "Fundamental"}]
    return a, b, c


# ------------------------------------------------------------------ the signature parser

def test_a_symbolic_default_is_required_not_optional():
    """`lookback = d` names what the caller must supply. Reading it as optional cost 3 of 4 live
    simulations with `Required attribute "lookback" must have a value.`"""
    req, opt = LA._params("ts_backfill(x,lookback = d, k=1)")
    assert "d" in req and "k" in opt


@pytest.mark.parametrize("definition,req,opt", [
    ("ts_decay_linear(x, d, dense = false)", ["d"], ["dense"]),
    ("group_backfill(x, group, d, std = 4.0)", ["group", "d"], ["std"]),
    ("hump(x, hump = 0.01)", [], ["hump"]),
    ("rank(x, rate=2)", [], ["rate"]),
    ("quantile(x, driver = gaussian, sigma = 1.0)", [], ["driver", "sigma"]),
    ("zscore(x)", [], []),
])
def test_the_parser_matches_the_platforms_own_definitions(definition, req, opt):
    assert LA._params(definition) == (req, opt)


def test_a_literal_default_is_optional_and_a_name_is_not():
    for lit in ("false", "true", "0.01", "4.0", "-1", "gaussian", "uniform"):
        assert LA._is_literal(lit), lit
    for name in ("d", "lookback", "group", "x"):
        assert not LA._is_literal(name), name


# ------------------------------------------------------------------ the layer split

def test_arithmetic_written_infix_never_appears_as_a_call(pools):
    """`add(x, y, filter=false)` and `multiply(x, y, ...)` are BINARY. Calling them with one operand
    produced 12,643 arity violations over 2,000 draws before this rule."""
    a, b, _ = pools
    names = {o["name"] for o in a} | {o["name"] for o in b}
    assert not (names & LA.INFIX)


def test_generators_and_grouping_operators_are_excluded(pools):
    """`ts_step` returns a day counter from a LENGTH; `densify` compresses a GROUPING FIELD.
    Neither transforms a signal, and wrapping them around one returned ERROR."""
    a, b, _ = pools
    names = {o["name"] for o in a} | {o["name"] for o in b}
    assert "ts_step" not in names
    assert "densify" not in names


def test_the_layers_are_split_the_way_the_operator_specified(pools):
    a, b, _ = pools
    assert {o["category"] for o in a} <= {"Cross Sectional", "Arithmetic", "Transformational"}
    assert {o["category"] for o in b} <= {"Time Series", "Group"}
    assert "rank" in {o["name"] for o in a}
    assert "ts_decay_linear" in {o["name"] for o in b}


# ------------------------------------------------------------------ the composed formula

def _arity_table(ops):
    t = {}
    for o in ops:
        if o["name"] in LA.INFIX:
            continue
        req, opt = LA._params(o.get("definition"))
        t[o["name"]] = (1 + len(req), 1 + len(req) + len(opt))
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


def test_a_thousand_draws_have_no_arity_violation_and_balanced_parens(pools):
    """THE REGRESSION TEST FOR THE WHOLE FILE. Before the infix and signature fixes this failed
    12,643 times in 2,000 draws, and each one would have spent a real simulation."""
    a, b, c = pools
    table = _arity_table(LA.load_operators())
    rng = random.Random(99)
    for _ in range(1000):
        f, _m = LA.compose(a, b, c, rng)
        assert f.count("(") == f.count(")"), f[:120]
        v = _violations(f, table)
        assert not v, "%s in %s" % (v, f[:160])


def test_every_required_window_and_group_is_actually_supplied(pools):
    """A `d` or a `group` left empty is the `Required attribute` error class."""
    a, b, c = pools
    rng = random.Random(5)
    needs_d = {o["name"] for o in a + b if "d" in o["required"]}
    for _ in range(300):
        f, _m = LA.compose(a, b, c, rng)
        for name in needs_d:
            for m in re.finditer(re.escape(name) + r"\(", f):
                seg = f[m.end():m.end() + 400]
                assert "," in seg, "%s called with no window in %s" % (name, f[:120])


def test_the_combination_size_honours_the_operators_range(pools):
    a, b, c = pools
    rng = random.Random(11)
    sizes = {LA.compose(a, b, c, rng)[1]["n_legs"] for _ in range(400)}
    # Leg count narrowed to LEGS_MIN..LEGS_MAX on 2026-08-13 (Khoa), after 2 legs failed
    # CONCENTRATED_WEIGHT 0/11 and 9 legs failed 11/11. Chain depth still spans the full COMBO range,
    # so the two are asserted separately -- one constant no longer governs both.
    assert min(sizes) >= LA.LEGS_MIN and max(sizes) <= LA.LEGS_MAX
    assert len(sizes) == (LA.LEGS_MAX - LA.LEGS_MIN + 1), \
        "every leg count in the range must be reachable, not just some"


def test_the_carrier_is_labelled_and_never_forced(pools):
    """The operator chose full randomness over privileging the carrier every historical gem has.
    The label is what turns that choice into a measurement instead of an argument."""
    a, b, c = pools
    rng = random.Random(3)
    f, m = LA.compose(a, b, [c[0]], rng)          # pool of just `close`
    assert m["carrier"] is False                  # close alone is not a carrier; open is missing
    assert LA.carrier_present("((close / open) * 0.5)") is True


# ------------------------------------------------------------------ layer C meaning

def test_a_ratio_never_divides_one_percentile_by_another():
    """"Ý nghĩa thật sự": a percentile over a percentile is arithmetically fine and economically
    meaningless. The denominator must be a quantity with units."""
    fields = [
        {"id": "pct_a", "description": "Percentile rank of the size component versus all companies",
         "dataset": {"id": "d"}, "category": {"name": "Other"}, "type": "MATRIX"},
        {"id": "pct_b", "description": "Percentile score of M&A target likelihood",
         "dataset": {"id": "d"}, "category": {"name": "Other"}, "type": "MATRIX"},
    ]
    c = LA.build_pool_c(fields, rng=random.Random(1))
    assert all(x["kind"] == "field" for x in c), "no ratio may be built from two percentiles"


def test_a_ratio_is_built_when_the_denominator_is_a_real_quantity():
    fields = [
        {"id": "rnd_expense", "description": "Research and development expense for the quarter",
         "dataset": {"id": "d"}, "category": {"name": "Fundamental"}, "type": "MATRIX"},
        {"id": "total_revenue", "description": "Total revenue reported for the period",
         "dataset": {"id": "d"}, "category": {"name": "Fundamental"}, "type": "MATRIX"},
    ]
    c = LA.build_pool_c(fields, rng=random.Random(1))
    ratios = [x for x in c if x["kind"] == "ratio"]
    assert ratios, "a level denominator must admit a ratio"
    assert all(" / " in r["expr"] for r in ratios), "ratios are infix, never divide()"
    assert all(r["why"] for r in ratios), "a ratio must carry the descriptions that give it meaning"


def test_a_ratio_never_crosses_datasets():
    """Two datasets can differ in units and vintage, and nothing here checked that."""
    fields = [
        {"id": "a_rev", "description": "Total revenue", "dataset": {"id": "d1"},
         "category": {"name": "F"}, "type": "MATRIX"},
        {"id": "b_assets", "description": "Total assets", "dataset": {"id": "d2"},
         "category": {"name": "F"}, "type": "MATRIX"},
    ]
    c = LA.build_pool_c(fields, rng=random.Random(1))
    assert not [x for x in c if x["kind"] == "ratio"]


# ------------------------------------------------------------------ it cannot submit

def test_neither_module_contains_a_submit_path():
    """A simulation is repeatable; a submission is one irreversible POST per alpha and a 403 spends
    it forever. Checked by walking the AST, so a mention in a comment cannot satisfy it."""
    import ast
    for name in ("layered_alpha.py", "layered_sim.py"):
        tree = ast.parse((ROOT / "tools" / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "/submit" not in node.value, "%s names a submit endpoint" % name
            if isinstance(node, ast.Attribute) and node.attr in ("put", "patch", "delete"):
                raise AssertionError("%s uses %s" % (name, node.attr))


# ============================================================================================
# The layer A/B improvements — each rule traces to a measured failure in batch1
# ============================================================================================

def test_every_leg_ends_in_one_of_the_six_outer_operators(pools):
    a, b, c = pools
    rng = random.Random(21)
    for _ in range(200):
        _f, m = LA.compose(a, b, c, rng)
        for leg in m["legs"]:
            assert leg["outer"] in LA.A_OUTER, leg["outer"]


def test_a_shaper_may_appear_but_never_outermost(pools):
    """The shapers are not thrown away — they draw inside the leg, where an outer operator still
    follows."""
    a, b, c = pools
    rng = random.Random(22)
    seen = set()
    for _ in range(400):
        _f, m = LA.compose(a, b, c, rng)
        for leg in m["legs"]:
            if leg.get("shaper"):
                seen.add(leg["shaper"])
                assert leg["shaper"] not in LA.A_OUTER
    assert seen, "shapers must still be reachable, just not outermost"


def test_no_operator_is_immediately_repeated_in_a_chain(pools):
    a, b, c = pools
    rng = random.Random(23)
    for _ in range(300):
        _f, m = LA.compose(a, b, c, rng)
        for leg in m["legs"]:
            ch = leg["inner"]
            assert all(x != y for x, y in zip(ch, ch[1:])), ch


def test_a_counter_is_never_stacked_on_a_counter(pools):
    """`days_from_last_change(days_from_last_change(x))` was journalled with `longCount=0,
    turnover=0` — the inner call returns a day counter that increments every day, so "days since it
    last changed" is a constant. Counters return integers or indices; stacking them destroys
    whatever variation was left, and the simulation is spent for no information."""
    a, b, c = pools
    rng = random.Random(24)
    for _ in range(300):
        _f, m = LA.compose(a, b, c, rng)
        for leg in m["legs"]:
            ch = leg["inner"]
            for x, y in zip(ch, ch[1:]):
                assert not (x in LA._COUNTERS and y in LA._COUNTERS), (x, y)


def test_log_and_sqrt_are_never_handed_an_input_they_cannot_take(pools):
    """A raw signal goes negative. One journalled degenerate alpha was
    `log(ts_delta(industry_reit_flag, ...))` — a binary flag whose differences are mostly zero."""
    a, b, c = pools
    rng = random.Random(25)
    for _ in range(400):
        f, _m = LA.compose(a, b, c, rng)
        for m_ in re.finditer(r"log\(", f):
            assert f[m_.end():m_.end() + 5] == "(abs(", f[m_.start():m_.start() + 40]
        for m_ in re.finditer(r"sqrt\(", f):
            assert f[m_.end():m_.end() + 4] == "abs(", f[m_.start():m_.start() + 40]


def test_the_improvements_did_not_break_arity_or_parens(pools):
    """The whole point of a change is that it fixes one thing without breaking the other."""
    a, b, c = pools
    table = _arity_table(LA.load_operators())
    rng = random.Random(26)
    for _ in range(500):
        f, _m = LA.compose(a, b, c, rng)
        assert f.count("(") == f.count(")")
        assert not _violations(f, table), f[:160]


# ============================================================================================
# The UNIT MODEL and the composer rule that follows from it
#
# THE DEFECT THIS SECTION EXISTS FOR. The previous fix forced one of six assumed "normalisers" to
# sit outermost on every leg. `add` fell from 12 to 2 of the warnings, and the TOTAL warning rate
# rose, because the rule is per OPERATOR, not per position:
#   * `hump` demands `Unit[]` and sits in layer B after extract-stage operators that preserve units
#   * `sqrt` entered the warnings BECAUSE of the domain guard added at the same time -- `sqrt(abs(x))`
#     still carries the unit of x
#   * two of the six assumed normalisers do not strip at all
# ============================================================================================

def test_the_two_operators_that_broke_the_previous_fix_are_not_stripers():
    """`winsorize(x, std=4)` CLIPS at four standard deviations and never divides; `normalize(x,
    useStd = false, ...)` subtracts the cross-sectional mean and, on the default this composer uses,
    does nothing else. Both keep the operand's unit.

    REFUTATION, not taste: two journalled rows in which EVERY leg already ended in one of the six
    assumed normalisers still warned on `add`, and in both the reported unit fits exactly one leg,
    whose outermost operator is `winsorize`:
        78zG61Rx  found Unit[CSPrice:-1]  winsorize(inverse(ts_decay_linear(momentum_vwap..., 10)))
        WjAYPg0d  found Unit[CSPrice:1]   winsorize(abs(ts_sum(atm_put_option_forward_price, 20)))
    """
    assert "winsorize" not in LA.STRIPS
    assert "normalize" not in LA.STRIPS
    assert LA.unit_refusals("(rank(close) + winsorize(open))") == ["add"]
    assert LA.unit_refusals("(rank(close) + winsorize(rank(open)))") == []


def test_the_five_operators_the_platform_named_are_all_in_the_demand_set():
    """Counted over the 19 journalled warning rows: hump 8 | add 4 | group_backfill 4 | sqrt 2 |
    ts_product 1. Every one of them says `expected "Unit[]"` in the platform's own words."""
    for name in ("hump", "add", "group_backfill", "sqrt", "ts_product"):
        assert name in LA.DEMANDS_UNITLESS, name


def test_the_unit_rule_holds_over_a_thousand_draws(pools):
    """THE RULE: an operator demanding `Unit[]` may only be applied to an expression the model calls
    stripped. Checked by re-parsing the EMITTED FORMULA, not by trusting the composer's bookkeeping."""
    a, b, c = pools
    rng = random.Random(41)
    for _ in range(1000):
        f, _m = LA.compose(a, b, c, rng, arm="units")
        assert LA.unit_refusals(f) == [], f[:200]


def _replay(meta):
    """The same question asked of a different record: the composer's own per-leg draw log, replayed
    from the leaf outwards. RULE 0 #5 -- a measurement re-derived a second way. If the emitted string
    and the recorded draws ever disagree, one of the two tests fails."""
    bad = []
    for leg in meta["legs"]:
        cls = LA.UNITFUL                       # the leaf
        chain = list(leg["inner"]) + ([leg["shaper"]] if leg.get("shaper") else []) + [leg["outer"]]
        for name in chain:
            if name in LA.DEMANDS_UNITLESS and cls != LA.UNITLESS:
                bad.append(name)
            if name in LA.STRIPS:
                cls = LA.UNITLESS
        if cls != LA.UNITLESS and len(meta["legs"]) > 1:
            bad.append("+")                    # a unitful leg meeting `add`
    return bad


def test_the_recorded_draws_agree_with_the_emitted_formula(pools):
    a, b, c = pools
    rng = random.Random(42)
    for _ in range(1000):
        _f, m = LA.compose(a, b, c, rng, arm="units")
        assert _replay(m) == [], m["legs"]


def test_the_control_arm_really_does_violate_the_rule(pools):
    """The control must differ from the treatment, or the experiment measures nothing. It reproduces
    the composer that produced the 86-row corpus."""
    a, b, c = pools
    rng = random.Random(43)
    n = sum(1 for _ in range(300) if LA.unit_refusals(LA.compose(a, b, c, rng, arm="control")[0]))
    assert n > 0


def test_every_operator_is_still_reachable_under_the_rule(pools):
    """A unit rule that quietly deletes operators from the search space has traded one defect for
    another. `hump`, `group_backfill`, `ts_product`, `sqrt` and `log` must still draw -- after a
    stripper, which is the whole content of the rule."""
    a, b, c = pools
    rng = random.Random(44)
    seen = set()
    for _ in range(1500):
        _f, m = LA.compose(a, b, c, rng, arm="units")
        for leg in m["legs"]:
            seen.update(leg["inner"])
            seen.add(leg["outer"])
            if leg.get("shaper"):
                seen.add(leg["shaper"])
    missing = ({o["name"] for o in a + b}) - seen
    assert not missing, missing


CORPUS = sorted((ROOT / "state/layered/runs").glob("*.jsonl"))


@pytest.mark.skipif(not CORPUS, reason="no journalled runs under state/layered/runs/")
def test_the_model_names_the_operator_the_platform_named(pools):
    """THE MODEL'S OWN REGRESSION TEST. Over every journalled terminal row, the model's refusal set
    must contain the operator the PLATFORM complained about. It is a deliberate OVER-approximation
    (a leaf field's unit is not in the metadata, so every leaf is treated as carrying one), so it
    also refuses rows the platform passed -- that direction is safe, the other is not."""
    pat = re.compile(r'Incompatible unit for input of "([^"]+)"')
    hit = miss = 0
    for p in CORPUS:
        for line in p.read_text(errors="ignore").splitlines():
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") not in ("COMPLETE", "WARNING") or not r.get("formula"):
                continue
            named = set(pat.findall(r.get("message") or ""))
            for ch in (r.get("checks") or []):
                if ch.get("name") == "UNITS" and ch.get("message"):
                    named |= set(pat.findall(ch["message"]))
            if not named:
                continue
            if named & set(LA.unit_refusals(r["formula"])):
                hit += 1
            else:
                miss += 1
    assert hit >= 19, "the corpus should carry at least the 19 known warning rows, saw %d" % hit
    assert miss == 0, "%d journalled warnings the model would not have prevented" % miss


# ============================================================================================
# The two-arm experiment
# ============================================================================================

def test_both_arms_are_drawn_when_none_is_forced(pools):
    """Randomised assignment per alpha inside one batch — not a before/after across runs, which
    would be confounded by time of day, market regime and quota state."""
    a, b, c = pools
    rng = random.Random(32)
    seen = collections.Counter(LA.compose(a, b, c, rng)[1]["arm"] for _ in range(200))
    assert set(seen) == set(LA.ARMS)
    assert min(seen.values()) > 60, "assignment must be roughly balanced, got %s" % dict(seen)


def test_the_arm_is_recorded_on_every_alpha(pools):
    """An unlabelled row is a row that cannot enter either arm, and a silently dropped row is how a
    randomised comparison stops being randomised."""
    a, b, c = pools
    rng = random.Random(33)
    for _ in range(100):
        _f, m = LA.compose(a, b, c, rng)
        assert m["arm"] in LA.ARMS


def test_the_unit_rule_did_not_reintroduce_arity_or_paren_errors(pools):
    a, b, c = pools
    table = _arity_table(LA.load_operators())
    rng = random.Random(34)
    for arm in LA.ARMS:
        for _ in range(300):
            f, _m = LA.compose(a, b, c, rng, arm=arm)
            assert f.count("(") == f.count(")")
            assert not _violations(f, table), f[:160]


# `test_the_report_refuses_a_verdict_on_too_few_rows` lived here. It read `layered_report.py` as
# TEXT and grepped it for three strings, so it stayed GREEN with the refusal thresholds set to 0 —
# the third guard test of that class found in this project. It is replaced by
# `tools/tests/test_layered_report.py`, which drives the code path and exercises both sides of every
# threshold; a mutation battery confirms that each constant, set to 0, turns that file red.


# ============================================================================================
# THE 2^4 CELL — PREREG_P1 §3 names four factors and INTEGRATION_P1R1 S8 measured that the code
# could assign exactly ONE. Every test below exists because a factor that cannot be varied still
# produces a complete-looking round that answers a different question than the pre-registered one.
# ============================================================================================

@pytest.fixture(scope="module")
def gate_pool():
    """Built in memory, NOT read from `state/layered/pool_c_gate.json`, because that artifact is
    stale relative to `tools/layer_c.py` (see `test_the_shipped_gate_pool_is_checked_for_staleness`).
    `layer_c.build_pool` is documented deterministic — no rng, no sampling."""
    import layer_c
    return layer_c.build_pool()


@pytest.fixture(scope="module")
def screened(pools):
    """A tiny synthetic screen: a raw field id dropped in the UPPERCASE vocabulary, which is the
    combination (wrong case AND wrong namespace) the real files actually present."""
    _a, _b, c = pools
    screens = {
        "coverage": {"close": {"verdict": "keep"}},
        "variation": {"_meta": {"note": "no drops by decision"}},
        "meaning": {"revenue": {"verdict": "DROP"}},
    }
    return LA.screen_pool_c(c, screens)


# ---- assignment ----------------------------------------------------------------------------

def test_all_sixtyfour_cells_are_reachable_and_exactly_balanced(pools, screened, gate_pool):
    """PREREG §3.3: the cell is drawn BEFORE generation from a shuffled fixed quota list. Four
    independent coin flips would put each cell at Binomial(N, 1/64) — and every
    standard error in PREREG §2 assumes balance."""
    a, b, c = pools
    kept, _r = screened
    asg = LA.CellAssigner(seed=20260813)
    rng = random.Random(1)
    seen = collections.Counter()
    for _ in range(64 * 20):
        _f, m = LA.compose(a, b, c, rng, assigner=asg, pool_c_kept=kept, gate_pool=gate_pool)
        seen[m["cell"]] += 1
    assert len(seen) == 64, sorted(seen)
    assert set(seen.values()) == {20}, dict(seen)
    assert {cell.id for cell in LA.ALL_CELLS} == set(seen)


def test_the_assigner_never_lets_two_cells_drift_apart():
    """The property permuted blocks buy that independent flips do not: balance holds at EVERY point
    in the batch, so a round truncated by a 429 or a 401 mid-dispatch (PREREG §6.2/§6.3) is still
    balanced instead of differentially composed."""
    asg = LA.CellAssigner(seed=7)
    seen = collections.Counter()
    for i in range(1, 16 * 9 + 1):
        seen[asg.next().id] += 1
        counts = [seen.get(cell.id, 0) for cell in LA.ALL_CELLS]
        assert max(counts) - min(counts) <= 1, (i, dict(seen))
    assert asg.n_drawn == 16 * 9


def test_the_assigner_is_reproducible_from_its_seed():
    """PREREG's manifest requires the seed recorded; a seed that does not reproduce the sequence
    records nothing."""
    one = [LA.CellAssigner(seed=99).next().id for _ in range(40)]
    assert one == [LA.CellAssigner(seed=99).next().id for _ in range(40)]
    assert one != [LA.CellAssigner(seed=100).next().id for _ in range(40)]


def test_every_row_carries_its_cell_in_the_shape_the_report_reads(pools, screened, gate_pool):
    """`layered_report.cell_of` reads `meta['factors']` first and `meta['cell']` (a STRING) second.
    A dict in `meta['cell']` is silently ignored by that reader, so this asserts against the
    report's own decoder rather than against this module's intent."""
    import layered_report as LR
    a, b, c = pools
    kept, _r = screened
    asg = LA.CellAssigner(seed=5)
    rng = random.Random(5)
    for _ in range(64):
        _f, m = LA.compose(a, b, c, rng, assigner=asg, pool_c_kept=kept, gate_pool=gate_pool)
        assert set(m["factors"]) == set(LR.FACTORS)
        assert m["cell"] == "".join("%s%d" % (f, m["factors"][f]) for f in LR.FACTORS)
        assert LR.cell_of({"meta": m}) == m["factors"], m["cell"]


def test_the_S_polarity_matches_prereg_and_the_legacy_corpus():
    """S is *removal* of the ordered-stage rule (PREREG §3.1), and `layered_report.LEGACY_ARM`
    already decodes the round-1 journal that way: `free -> ("S", 1)`, `ordered -> ("S", 0)`. Coding
    S as "the rule is applied" would flip the sign of the S contrast against every row already
    journalled, with no error anywhere."""
    import layered_report as LR
    assert LR.LEGACY_ARM["free"] == ("S", 1) and LR.LEGACY_ARM["ordered"] == ("S", 0)
    assert LA.Cell(D=0, C=0, U=0, S=1).stage_ordered is False
    assert LA.Cell(D=0, C=0, U=0, S=0).stage_ordered is True


def test_the_legacy_call_still_works_and_says_so(pools):
    """`layered_sim.draw` calls `compose(a, b, c, rng)` with no cell. That must not crash and must
    not silently claim to be the pre-registered assignment: it produces exactly two cells (U only)
    and labels every row `legacy-default`, which is visible in the report."""
    a, b, c = pools
    rng = random.Random(31)
    seen = collections.Counter()
    for _ in range(200):
        _f, m = LA.compose(a, b, c, rng)
        assert m["cell_source"] == "legacy-default"
        assert m["factors"]["D"] == 0 and m["factors"]["C"] == 0 and m["factors"]["S"] == 1
        seen[m["cell"]] += 1
    assert len(seen) == 2, dict(seen)


def test_a_treatment_can_never_silently_run_without_its_pool(pools):
    """FAIL CLOSED. D=on composed from the unscreened pool, or C=on with no gate, journals a
    complete-looking row for an experiment in which that factor never varied — the class
    INTEGRATION_P1R1 ranks 'silent first'."""
    a, b, c = pools
    rng = random.Random(2)
    with pytest.raises(ValueError):
        LA.compose(a, b, c, rng, cell=LA.Cell(D=1, C=0, U=1, S=1))
    with pytest.raises(ValueError):
        LA.compose(a, b, c, rng, cell=LA.Cell(D=1, C=0, U=1, S=1), pool_c_kept=[])
    with pytest.raises(ValueError):
        LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=1, U=1, S=1))
    with pytest.raises(ValueError):
        LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=0, U=1, S=1), arm="control")
    with pytest.raises(ValueError):
        LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=0, U=1, S=1),
                   assigner=LA.CellAssigner(seed=1))


# ---- D: the screen normalisation ------------------------------------------------------------

def test_the_screen_normalisation_crosses_both_vocabularies_and_both_namespaces(pools, screened):
    """The three screens disagree twice over. `screen_meaning` writes UPPERCASE `DROP` keyed by raw
    FIELD ID, so a naive `verdict == "drop"` on the pool-C `expr` misses it twice: on case, and on
    the ratio that merely CONTAINS the dropped field."""
    _a, _b, c = pools
    kept, report = screened
    exprs = {x["expr"] for x in kept}
    assert "close" in exprs, "a kept field must survive"
    assert "(revenue / total_assets)" not in exprs, \
        "a ratio inherits its components' drops (N2); this one holds an UPPERCASE-DROP field"
    assert report["n_removed"] == len(c) - len(kept) == 1


def test_FLAG_and_unknown_and_absence_are_not_drops():
    """Each is stated by the screen's OWN `_meta`: FLAG is 'NOT usable as a drop. Label only.'
    (hand-audit precision 7/15), and 'Absence from this file means UNKNOWN, never drop.'"""
    pool = [{"kind": "field", "expr": n, "why": "", "dataset": "d", "category": "x"}
            for n in ("a", "b", "c")]
    screens = {"meaning": {"a": {"verdict": "FLAG"}, "b": {"verdict": "unknown"}}}
    kept, report = LA.screen_pool_c(pool, screens)
    assert [x["expr"] for x in kept] == ["a", "b", "c"]
    assert report["n_removed"] == 0


def test_D_on_restricts_the_leaf_pool_and_D_off_does_not(pools):
    """The falsification test for factor D. D=on must draw ONLY from survivors; D=off must be able
    to draw a dropped leaf, or the two halves are the same experiment."""
    a, b, _c = pools
    full = [{"kind": "field", "expr": "keep_me", "why": "", "dataset": "d", "category": "x"},
            {"kind": "field", "expr": "drop_me", "why": "", "dataset": "d", "category": "x"}]
    kept, _r = LA.screen_pool_c(full, {"meaning": {"drop_me": {"verdict": "DROP"}}})
    assert [x["expr"] for x in kept] == ["keep_me"]

    rng = random.Random(6)
    on = set()
    for _ in range(120):
        _f, m = LA.compose(a, b, full, rng, cell=LA.Cell(D=1, C=0, U=1, S=1), pool_c_kept=kept)
        on.update(leg["leaf"] for leg in m["legs"])
        assert m["layer_d_screen"] == {"n_pool": 2, "n_kept": 1}
    assert on == {"keep_me"}

    off = set()
    for _ in range(120):
        _f, m = LA.compose(a, b, full, rng, cell=LA.Cell(D=0, C=0, U=1, S=1), pool_c_kept=kept)
        off.update(leg["leaf"] for leg in m["legs"])
        assert m["layer_d_screen"] is None
    assert off == {"keep_me", "drop_me"}, "D=off must NOT be quietly screened too"


@pytest.mark.skipif(not (ROOT / "state/layered/pool_c.json").exists(), reason="pools not built")
def test_the_real_screens_normalise_to_the_measured_survivor_count():
    """RULE 0 §5, the second derivation. INTEGRATION_P1R1 measured 69,106 survivors for a
    case-insensitive filter that does NOT propagate into ratios; 300 meaning-dropped ratios are
    caught only by the expr-space rule (N2), and 69,106 - 300 = 68,806. If either number moves the
    normalisation changed, and this test says so instead of a report saying it later."""
    pool = json.loads((ROOT / "state/layered/pool_c.json").read_text())
    kept, report = LA.screen_pool_c(pool, LA.load_screens())
    assert report["drops_per_screen"] == {"coverage": 465, "variation": 0, "meaning": 3688}
    assert report["n_pool"] == 73258 and len(kept) == 68806
    assert report["removed_by_kind"] == {"field": 4085, "ratio": 367}


# ---- C: the gate ----------------------------------------------------------------------------

def test_C_on_wraps_the_alpha_and_C_off_leaves_it_bare(pools, gate_pool):
    a, b, c = pools
    rng = random.Random(8)
    for _ in range(120):
        f, m = LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=1, U=1, S=1), gate_pool=gate_pool)
        assert f.startswith(("trade_when(", "if_else(")), f[:60]
        assert m["gate"] and m["gate"]["mode"] in ("hold", "exit", "scale", "pick")
    for _ in range(120):
        f, m = LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=0, U=1, S=1), gate_pool=gate_pool)
        assert not f.startswith(("trade_when(", "if_else("))
        assert m["gate"] is None


def test_the_gates_own_meta_reaches_the_journal(pools, gate_pool):
    """INTEGRATION_P1R1 S2: `render_gate`'s meta had no journal path and no reader — the class that
    once made 2,639 rows unanalysable. `layered_sim._child_row` journals `meta` wholesale, so the
    gate's dict must be nested INSIDE it, and must be JSON-serialisable to get there."""
    a, b, c = pools
    rng = random.Random(9)
    modes = collections.Counter()
    for _ in range(200):
        _f, m = LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=1, U=1, S=1), gate_pool=gate_pool)
        g = m["gate"]
        assert {"layer_c", "mode", "cond", "kind", "origin", "why", "leaf"} <= set(g)
        assert "{leaf}" not in g["cond"]
        json.dumps(m)
        modes[g["mode"]] += 1
    assert set(modes) == {"hold", "exit", "scale", "pick"}, dict(modes)


def test_no_gated_draw_is_ever_dropped(pools, gate_pool):
    """`render_gate` REFUSES an exit condition identical to its trigger (correctly — z is evaluated
    first, so the alpha would close on exactly the days it fires; INTEGRATION_P1R1 L2 hit it on 1 of
    400 draws). PREREG §3.3: a treatment that sets its own sample size voids §2, so the exit entry
    is drawn from the conditions that differ and the refusal can never fire."""
    a, b, c = pools
    rng = random.Random(10)
    for _ in range(400):
        _f, m = LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=1, U=1, S=1), gate_pool=gate_pool)
        if m["gate"]["mode"] == "exit":
            assert m["gate"]["exit_cond"] != m["gate"]["cond"]


def test_the_carrier_label_is_not_contaminated_by_the_gate(pools, gate_pool):
    """The gate conditions contain `close`. Labelling the carrier on the GATED formula would flip
    the label on any alpha already holding `open`, and a C=on vs C=off carrier split would then
    measure the gate rather than the alpha."""
    a, b_all, _c = pools
    pool = [{"kind": "field", "expr": "open", "why": "", "dataset": "d", "category": "x"}]
    b = [o for o in b_all if o["name"] == "ts_mean"]
    rng = random.Random(11)
    for _ in range(30):
        f, m = LA.compose(a, b, pool, rng, cell=LA.Cell(D=0, C=1, U=0, S=1), gate_pool=gate_pool)
        assert "open" in f
        assert m["carrier"] is False, "the gate's own `close` must not create a carrier"


def test_the_shipped_gate_pool_is_checked_for_staleness():
    """MEASURED 2026-08-13: `state/layered/pool_c_gate.json` (107 entries, 16:25) predates
    `tools/layer_c.py` (178 entries, 18:56) and lacks the `family`/`scope`/`unverified` keys the
    current `render_gate` reads — every C=on draw raised `KeyError: 'family'`. Either the artifact
    has been rebuilt and loads, or the loader refuses it by name. Silently returning a stale pool is
    the one outcome this forbids."""
    import layer_c
    try:
        pool = LA.load_gate_pool()
    except ValueError as e:
        assert "stale" in str(e) and "layer_c.py --build" in str(e)
        return
    assert set(pool[0]) >= set(layer_c.build_pool()[0])


# ---- S: the ordered stage rule ---------------------------------------------------------------

def test_S_off_forbids_backward_stage_steps_and_S_on_permits_them(pools):
    """The falsification test for factor S. It is a NEW rule, not the refuted one: the deleted rule
    forbade 16.5% of chain links, this map forbids 38.1% of free-arm links (measured, 2,000 draws).
    What the two nulls (U=327 p=0.72 at n=50; U=936 p=0.6353 at n=84) license is 'no advantage
    detected', never 'died' — so it must be re-testable, which is what this asserts."""
    a, b, c = pools
    rng = random.Random(12)
    for _ in range(300):
        _f, m = LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=0, U=1, S=0))   # rule APPLIED
        assert m["stage_ordered"] is True
        for leg in m["legs"]:
            ch = leg["inner"]
            for x, y in zip(ch, ch[1:]):
                assert LA._STAGE_OF[y] >= LA._STAGE_OF[x], (x, y)
    back = 0
    for _ in range(300):
        _f, m = LA.compose(a, b, c, rng, cell=LA.Cell(D=0, C=0, U=1, S=1))   # rule REMOVED
        assert m["stage_ordered"] is False
        for leg in m["legs"]:
            ch = leg["inner"]
            back += sum(1 for x, y in zip(ch, ch[1:]) if LA._STAGE_OF[y] < LA._STAGE_OF[x])
    assert back > 0, "S=1 must actually permit what S=0 forbids, or the factor is a no-op"


def test_every_pool_b_operator_carries_a_stage(pools):
    """An operator missing from the map is EXEMPT from the rule, not forbidden by it — a silent
    exemption would shrink the S treatment to whatever happened to be listed."""
    _a, b, _c = pools
    assert not ({o["name"] for o in b} - set(LA._STAGE_OF))
    assert sum(len(v) for v in LA.B_STAGES.values()) == len(LA._STAGE_OF), "a name is in two stages"


# ---- the regressions must hold in EVERY cell ------------------------------------------------

def test_arity_parens_and_the_unit_rule_hold_in_all_sixteen_cells(pools, screened, gate_pool):
    """THE REGRESSION TEST FOR THE WHOLE ROUND. Every rule that traces to a live failure — infix
    arithmetic, supplied windows, the domain guards, the outer-operator rule, the unit model — must
    survive in all 64 cells, not only in the two the composer used to have."""
    a, b, c = pools
    kept, _r = screened
    table = _arity_table(LA.load_operators())
    needs_d = {o["name"] for o in a + b if "d" in o["required"]}
    for cell in LA.ALL_CELLS:
        rng = random.Random(13)
        for _ in range(40):
            f, m = LA.compose(a, b, c, rng, cell=cell, pool_c_kept=kept, gate_pool=gate_pool)
            assert f.count("(") == f.count(")"), (cell.id, f[:120])
            assert "{" not in f, (cell.id, f[:120])
            assert not _violations(f, table), (cell.id, f[:160])
            for name in needs_d:
                for mm in re.finditer(re.escape(name) + r"\(", f):
                    assert "," in f[mm.end():mm.end() + 400], (cell.id, name)
            for mm in re.finditer(r"log\(", f):
                assert f[mm.end():mm.end() + 5] == "(abs(", (cell.id, f[:120])
            for mm in re.finditer(r"sqrt\(", f):
                assert f[mm.end():mm.end() + 4] == "abs(", (cell.id, f[:120])
            for leg in m["legs"]:
                assert leg["outer"] in LA.A_OUTER
            if cell.U:
                assert LA.unit_refusals(f) == [], (cell.id, f[:200])


def test_the_unit_checker_survives_a_comparison_at_top_level_and_nested(gate_pool):
    """INTEGRATION_P1R1 S3/L1: `_TOK` carried no comparison token, so at top level the parse stopped
    at the first `>` and returned a silent 'no refusal', and nested inside a call it raised
    IndexError. Both directions are asserted, plus every condition it will actually meet."""
    assert LA.unit_refusals("(rank(close) + winsorize(open))") == ["add"]
    assert LA.unit_refusals("(rank(close) + winsorize(open)) > ts_mean(close, 20)") == ["add"]
    assert LA.unit_refusals("trade_when(close > ts_mean(close, 20), rank(close), -1)") == []
    assert LA.unit_refusals(
        "if_else(volume >= adv20, (rank(close) + winsorize(open)), rank(close))") == ["add"]
    for e in gate_pool:
        cond = e["cond"].replace("{leaf}", "close")
        assert LA.unit_refusals(cond) == [], cond
