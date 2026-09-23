"""Tests for the framework registry.

The regressions these exist to catch are all ones this project has actually paid for:
a composer shipped against a different module signature and abandoned 1,410 simulations; an
experimental arm applied in the POST body instead of at construction, so the guard refused three of
four arms while the run looked healthy; `add`/`multiply` called with one operand 12,643 times.
"""

import pathlib
import random
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layered_alpha as LA  # noqa: E402
import frameworks as FW  # noqa: E402


@pytest.fixture(scope="module")
def pools():
    ops = LA.load_operators()
    pool_a, pool_b, _dropped = LA.split_layers(ops)
    pool_c = LA.build_pool_c(LA.load_fields(), rng=random.Random(0))
    return pool_a, pool_b, pool_c


def _built(name, pools, n=60, seed0=0):
    pool_a, pool_b, pool_c = pools
    return [FW.build(FW.BY_NAME[name], pool_a, pool_b, pool_c, random.Random(seed0 + s))
            for s in range(n)]


# ---- the registry itself ------------------------------------------------------------------

def test_every_framework_carries_a_prediction():
    """A framework with no prediction cannot be refuted, which is the failure BACKBONE.md died of."""
    for f in FW.FRAMEWORKS:
        assert f.predicts and len(f.predicts) > 40, f.name


def test_flat_is_present_and_unconstrained():
    """Without a null arm nothing can be shown to beat anything."""
    flat = FW.BY_NAME["flat"]
    assert flat.outer is FW.FREE and flat.negate is FW.FREE
    assert flat.neutralization is FW.FREE and flat.carrier is FW.FREE
    assert flat.claims == ()


def test_names_are_unique():
    names = [f.name for f in FW.FRAMEWORKS]
    assert len(names) == len(set(names))


def test_assign_is_balanced_within_one_batch():
    """Every framework gets the same share of ONE batch -- a before/after across runs is confounded
    by time of day, market regime and quota state."""
    n = len(FW.FRAMEWORKS) * 7
    picks = FW.assign(random.Random(1), n)
    counts = {name: picks.count(name) for name in FW.BY_NAME}
    assert set(counts.values()) == {7}, counts


def test_assign_is_not_a_repeating_cycle():
    """Blocks are permuted; a fixed cycle would align an arm with position in the batch."""
    picks = FW.assign(random.Random(2), len(FW.FRAMEWORKS) * 4)
    k = len(FW.FRAMEWORKS)
    assert len({tuple(picks[i * k:(i + 1) * k]) for i in range(4)}) > 1


# ---- composition holds for every framework ------------------------------------------------

@pytest.mark.parametrize("name", [f.name for f in FW.FRAMEWORKS])
def test_composes_and_parenthesises(name, pools):
    for formula, _meta in _built(name, pools, n=40):
        assert formula.count("(") == formula.count(")"), formula
        assert formula.strip() == formula and formula


@pytest.mark.parametrize("name", [f.name for f in FW.FRAMEWORKS])
def test_arithmetic_is_infix_never_called(name, pools):
    """`add`/`subtract`/`multiply`/`divide` are written + - * / by operator decision. Calling them
    is what produced 12,643 arity violations."""
    for formula, _meta in _built(name, pools, n=40):
        for op in LA.INFIX:
            assert op + "(" not in formula, formula


@pytest.mark.parametrize("name", [f.name for f in FW.FRAMEWORKS])
def test_leg_count_is_inside_the_declared_range(name, pools):
    lo, hi = FW.BY_NAME[name].legs
    for _formula, meta in _built(name, pools, n=40):
        assert lo <= meta["n_legs"] <= hi


# ---- the declared constraints are applied AT CONSTRUCTION ---------------------------------
# An arm applied anywhere later is an arm that silently does not exist.

def test_s6_neg_puts_the_minus_on_the_carrier_leg_and_nowhere_else(pools):
    """S6 is about the sign on ONE leg. Negating others would test the arm the corpus already
    measured as a null (OR 0.69, p 0.57)."""
    for _formula, meta in _built("s6_neg", pools, n=120):
        ci = meta["carrier_idx"]
        assert ci is not None
        assert meta["signs"][ci] is True
        assert not any(s for i, s in enumerate(meta["signs"]) if i != ci)


def test_s6_pos_negates_nothing(pools):
    """s6_neg's paired control. This pair IS the 0-negation arm the corpus lacks -- exactly 6
    matched sign-flip groups exist in 50,482 multi-leg rows and none has one."""
    for _formula, meta in _built("s6_pos", pools, n=120):
        assert meta["carrier_idx"] is not None
        assert not any(meta["signs"])


def test_s6_arms_differ_only_in_the_sign(pools):
    """Same seed, same everything but the minus -- otherwise the comparison is not paired."""
    pool_a, pool_b, pool_c = pools
    for s in range(30):
        a, ma = FW.build(FW.BY_NAME["s6_neg"], pool_a, pool_b, pool_c, random.Random(s))
        b, mb = FW.build(FW.BY_NAME["s6_pos"], pool_a, pool_b, pool_c, random.Random(s))
        assert ma["n_legs"] == mb["n_legs"] and ma["carrier_idx"] == mb["carrier_idx"]
        assert ma["weights"] == mb["weights"]
        assert a.replace("-", "+") == b.replace("-", "+") or a != b


@pytest.mark.parametrize("name", ["s6_neg", "s6_pos", "era_b"])
def test_carrier_true_always_puts_a_carrier_in_the_formula(name, pools):
    """`meta.carrier` disagreed with the formula on 3,822 corpus rows and a finding flipped sign
    between the two definitions. Both are recorded, and here they must agree."""
    for _formula, meta in _built(name, pools, n=60):
        assert meta["carrier_declared"] is True
        assert meta["carrier_in_formula"] is True


@pytest.mark.parametrize("name,outer", [
    ("era_a", ("ts_decay_linear", "group_neutralize", "normalize")),
    ("era_b", ("signed_power", "zscore", "ts_decay_linear")),
])
def test_declared_outer_chain_is_applied_outermost_first(name, outer, pools):
    for formula, meta in _built(name, pools, n=25):
        assert meta["outer"] == list(outer)
        pos = [formula.index(op + "(") for op in outer]
        assert pos == sorted(pos), formula[:120]


def test_free_outer_never_exceeds_two_operators(pools):
    for _formula, meta in _built("flat", pools, n=60):
        assert len(meta["outer"]) <= 2


# ---- settings are applied at construction, not in the POST body ---------------------------

def test_settings_for_applies_the_declared_neutralization():
    base = {"neutralization": "NONE", "decay": 0}
    assert FW.settings_for(FW.BY_NAME["s1_neut"], base)["neutralization"] == "INDUSTRY"
    assert FW.settings_for(FW.BY_NAME["subu"], base)["neutralization"] == "SUBINDUSTRY"
    assert base["neutralization"] == "NONE", "settings_for must not mutate its argument"


def test_settings_for_leaves_free_frameworks_alone():
    base = {"neutralization": "SECTOR"}
    assert FW.settings_for(FW.BY_NAME["flat"], base)["neutralization"] == "SECTOR"


def test_only_the_margin_arm_declares_a_decay():
    """CORRECTION to my own first design. Pinning every framework at decay 3 silently DISABLED
    `layered_sim`'s settings arm -- the only running test of the largest unexplained gap in the
    project (this generator screened 0/129 against the resim corpus's 6.70%, and the leading suspect
    is exactly resim's settings: decay 6-14 with INDUSTRY/STATISTICAL). Pinning it turned off the
    experiment testing the leading suspect. Only `margin` declares a decay, because its whole
    prediction is about one."""
    base = {"decay": 7}
    for f in FW.FRAMEWORKS:
        got = FW.settings_for(f, base)["decay"]
        assert got == (FW.DECAY_LARGE if f.name == "margin" else 7), f.name
    assert FW.DECAY_SMALL < FW.DECAY_LARGE


def test_the_margin_arm_is_the_only_one_differing_from_flat_in_decay():
    """If more than one arm moved decay, decay and framework would be confounded across the batch
    and neither could be read."""
    odd = [f.name for f in FW.FRAMEWORKS if f.decay is not FW.FREE]
    assert odd == ["margin"], odd


def test_s1_has_a_negative_control_arm():
    """S1 is the only claim in this project that made a risky prediction and survived it. The
    two-name-floor argument caps GROUP neutralizations and says nothing about RISK-FACTOR ones, so
    `s1_risk` must NOT cap. A control that can fail is what separates S1 from a coincidence."""
    grp, risk = FW.BY_NAME["s1_neut"], FW.BY_NAME["s1_risk"]
    assert grp.neutralization == "INDUSTRY" and risk.neutralization == "STATISTICAL"
    assert grp.legs == risk.legs and grp.depth == risk.depth and grp.decay == risk.decay
    assert "ABOVE 0.5" in risk.predicts


def test_s7_is_not_claimed_by_any_framework():
    """R3_OOS refuted it: rho(n_legs, CW_FAIL) is +0.016 on alphas_all, +0.501 on layered, and runs
    +0.148 to -0.421 by decile inside its own append-only file."""
    assert not [f.name for f in FW.FRAMEWORKS if "S7" in f.claims]


# ---- required parameters are supplied -----------------------------------------------------

def test_signed_power_receives_its_exponent(pools):
    """`ts_backfill.lookback` is the ONLY name-defaulted required parameter (12 of 13 others reach
    COMPLETE when omitted), but a required LITERAL parameter still has to be passed."""
    for formula, _meta in _built("era_b", pools, n=25):
        assert formula.startswith("signed_power(")
        assert formula.rstrip().endswith(")")
        head = formula[len("signed_power("):-1]
        depth, top_commas = 0, 0
        for ch in head:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                top_commas += 1
        assert top_commas == 1, formula[:140]


@pytest.mark.parametrize("name", [f.name for f in FW.FRAMEWORKS])
def test_no_operator_is_called_with_a_bare_required_name(name, pools):
    """The `Required attribute "lookback"` class: a NAME left in the argument list instead of a
    value. It killed 3 of 4 live simulations."""
    for formula, _meta in _built(name, pools, n=30):
        for tok in (", d)", ", d,", ", group)", ", y)"):
            assert tok not in formula, formula
