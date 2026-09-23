#!/usr/bin/env python3
"""LAYER C — the conditional / market gate. The layer that decides WHEN the alpha trades.

Khoa, 2026-08-13. The stack is now:

    LAYER A   outer functions, 1..10 legs          (Cross Sectional + shaping Arithmetic)
    LAYER B   inner functions per leg, 1..10 deep  (Time Series + Group)
    LAYER C   NEW: the CONDITIONAL / MARKET GATE   (trade_when, if_else, comparisons)
    LAYER D   was C: real fields and economic ratios

        trade_when(volume > ts_mean(volume, 20), D, -1)
        if_else(D1 > D2, D1, D2)

THE REVERSAL, RECORDED. `tools/layered_alpha.py` excludes `trade_when` on the stated ground that it
is "control flow, not a transform: needs an event predicate to mean anything", and `split_layers`
drops the whole Logical category with "category 'Logical' belongs to neither layer". Both were
CORRECT for a composer that had no notion of a regime — there was no event predicate to give
`trade_when`, so every draw would have been noise. Both are WRONG as a permanent rule, because a
gate is exactly what layer C is for. **The exclusion is lifted for layer C only.** The operators
named in `GATE_OPS` below must still never appear in layer A or layer B; that is asserted in
`tools/tests/test_layer_c.py`, not left to convention.

TWO SIGNATURE RULES, BOTH LOAD-BEARING, BOTH TAKEN FROM THE PLATFORM'S OWN `definition` STRINGS
(`fetched/operators.json`), which is the authority on arity:

 1. A PARAMETER WHOSE DEFAULT IS A NAME IS REQUIRED; only a LITERAL default is optional.
    `ts_backfill(x, lookback = d, k=1)` reads optional and is not — misreading it returned
    `Required attribute "lookback" must have a value.` on 3 of 4 live simulations. The parser that
    encodes this rule is `layered_alpha._params`, and this module IMPORTS it rather than restating
    it, so there is exactly one copy of the rule that cost those simulations.

 2. THE COMPARISON OPERATORS HAVE NO CALL FORM IN THE DOCUMENTATION. Their `definition` strings are
    written INFIX and nothing else:
        greater        `input1 > input2`
        greater_equal  `input1 >= input2`
        less           `input1 < input2`
        less_equal     `input1 <= input2`
        equal          `input1 == input2`
        not_equal      `input1!= input2`
    Both worked examples in the platform docs use the infix form too — `volume >= ts_mean(volume, 5)`
    under `trade_when`, `volume > adv20` under `if_else`. So this module writes them infix, the same
    way `layered_alpha` writes `add`/`subtract`/`multiply`/`divide` infix after calling them
    produced 12,643 arity violations in 2,000 draws.
    NOT ESTABLISHED: whether `greater(a, b)` is also accepted by the platform. No documentation says
    it is and nothing here tested it, so the documented form is the one emitted.
    `and(input1, input2)`, `or(input1, input2)`, `not(x)` and `is_nan(input)` ARE written as calls in
    their definitions, so those four are emitted as calls.

 3. `==` AND `!=` ARE EMITTED ONLY AGAINST INTEGER-VALUED QUANTITIES. Equality on a continuous
    quantity is true on a set of measure zero, so `close == ts_mean(close, 20)` is a condition that
    is essentially never met and an alpha gated on it never trades. The only equality condition in
    the pool is `days_from_last_change(<leaf>) == 0`, which is the platform's own documented
    `trade_when` recipe and whose left side is a day COUNT.

WHAT `trade_when`'s THIRD ARGUMENT IS. From the operator's detailed docs, verbatim in substance:
z is the EXIT condition; when z is true the alpha is set to NaN and the position is closed; when z is
false and x is true the alpha takes the new value; when both are false it HOLDS its previous value.
The docs' own example passes `-1` for z and states "The exit condition is always false (-1), so
positions are not closed by this rule." That is why `mode="hold"` emits `-1` — it is the documented
way to say "never exit", not a magic number.

WHAT IS NOT ESTABLISHED, said once and plainly: that gating improves anything. No simulation has
been run with this module. The frozen baseline is median sharpe 0.000 and 0/80 screen-passers
(HARNESS_SOP.md), and nothing here predicts that a gate moves it. **MECHANISM: UNKNOWN** for every
condition in the pool — each `why` states what the condition MEASURES, never why gating on it would
pay. The direction of every two-sided regime is drawn from the pool in BOTH directions for exactly
this reason: if only the "high participation" side were ever emitted, a measured effect could not be
separated from "gating at all reduces turnover", which is a different claim.

ROUND 2 (P1R2) ADDS FOUR CONDITION FAMILIES AND TWO KEYS THE COMPARISON NEEDS.

 4. `scope` — DOES THE CONDITION VARY ACROSS NAMES ON A GIVEN DAY? Every round-1 condition was
    `per_name`. A `market_wide` condition has the same value for every instrument, so it turns the
    WHOLE BOOK on and off; a `per_name` condition zeroes different names on the same day and so
    reshapes the cross-section. Those are not the same experiment and the analysis must not pool
    them. Values: `per_name`, `group_wide` (constant within a sector/industry), `market_wide`,
    `constant` (true for every name on every day, by construction).

 5. `unverified` — a per-entry list of what about the entry is NOT documented. It is empty for
    every round-1 entry. It exists so the deploy round can run the fully-documented subset first
    instead of discovering an undocumented form by spending simulations on it.

 6. `family` — the analysis factor. 178 conditions cannot each get an arm; family can. Several spec
    rows share one family (e.g. the sector and industry forms of `relative_regime`).

 7. THE CROSS-SECTIONAL STANDARD DEVIATION IS AN IDENTITY, NOT AN APPROXIMATION. There is no
    group-standard-deviation operator in the 67-operator catalogue, and the only aggregator that
    returns a group LEVEL broadcast back to members, `group_mean`, is documented as the HARMONIC
    mean. But two documented definitions compose exactly:
        group_neutralize(x, g)  =  x - mean_g(x)            ("subtracting the group mean")
        group_zscore(x, g)      = (x - mean_g(x)) / sd_g(x)
    so `group_neutralize(x, g) / group_zscore(x, g)` IS sd_g(x), for any name whose z is not exactly
    zero, and it is numerically stable because numerator and denominator shrink together. The single
    assumption — that both operators use the same group mean — is what the `unverified` list on
    those entries records. `group_mean` is used nowhere in this module.

 8. THE POOL CARRIES ITS OWN NULL CONTROLS, and they are the reason two design choices survive:
      * `>` vs `>=` on a CONTINUOUS quantity select the same days (the boundary has measure zero),
        so any measured difference between the two tokens is the pipeline's own noise floor. The
        entry name records which token was used so that floor can actually be estimated. The
        `persistence` family is the exception — its statistic lives on a lattice that CONTAINS the
        threshold, so there the two tokens are genuinely different conditions and only one is
        emitted.
      * `wrapper_null` (`not(is_nan(close))`, true for every name every day because `close` has
        coverage 1.0) makes `trade_when(TRUE, alpha, -1)`. Per the trade_when docs that is the
        identity. If it measures differently from the ungated alpha then the WRAPPER, not the
        condition, is producing the effect, and every gate comparison in the round is confounded.
"""
import argparse
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPS = ROOT / "fetched/rc/operators.json"
POOLDIR = ROOT / "state/layered"

#: Windows layer C may draw. Same set layer B uses; nothing here measured that they are the right
#: ones, they are the decays this project has actually simulated.
WINDOWS = (5, 10, 20, 60, 120, 250)

#: The 12 operators layer C is allowed to use, and the ONLY layer permitted to use them.
#: `trade_when` is category Transformational, not Logical -- checked against `fetched/operators.json`
#: rather than assumed from the name.
GATE_OPS = frozenset({
    "trade_when", "if_else",
    "greater", "less", "greater_equal", "less_equal", "equal", "not_equal",
    "and", "or", "not", "is_nan",
})

#: Written infix because the platform's `definition` gives no call form (see rule 2 in the docstring).
INFIX_COMPARISONS = frozenset({"greater", "less", "greater_equal", "less_equal",
                               "equal", "not_equal"})

#: Written as calls because their `definition` strings are calls.
CALL_LOGICALS = frozenset({"and", "or", "not", "is_nan"})

#: Comparison tokens by direction. `>` and `>=` are BOTH emitted, and the reason is not that one is
#: better: on a continuous quantity the boundary has measure zero, so the two select the same days.
#: The platform documents both, neither is preferred here, and the draw records which was used.
_GT = (">", ">=")
_LT = ("<", "<=")
_EQ = ("==",)
_NE = ("!=",)

#: Single-token forms. Used ONLY where the statistic is on a lattice that contains the threshold, so
#: `>` and `>=` select different day sets and nothing here distinguishes them. Emitting both there
#: would put two different conditions under one name and destroy the `>` vs `>=` noise-floor control.
_GT1 = (">",)
_LT1 = ("<",)

#: Short tag per comparison token, appended to the entry name. Without it `volume_vs_adv20_hi` is the
#: name of BOTH the `>` and the `>=` entry, and the noise-floor control cannot be estimated because
#: the two arms are not distinguishable in the terminal row.
_CMP_TAG = {">": "gt", ">=": "ge", "<": "lt", "<=": "le", "==": "eq", "!=": "ne"}


def _xs_sd(x, g):
    """The cross-sectional standard deviation of `x` within group `g`, broadcast to every member.

    AN IDENTITY BETWEEN TWO DOCUMENTED DEFINITIONS, not an approximation and not a proxy:

        group_neutralize(x, g)  =  x - mean_g(x)          "subtracting the group mean"
        group_zscore(x, g)      = (x - mean_g(x)) / sd_g(x)

    so the ratio is sd_g(x) exactly, whatever ddof `group_zscore` uses -- the sd does not cancel out
    of the numerator, it is simply not in it. Numerically stable: as a name approaches the group mean
    both numerator and denominator shrink by the same factor. Undefined only where z is EXACTLY zero.

    THE ONE ASSUMPTION, recorded on every entry that uses it: that the two operators use the same
    group mean. Both are documented as "the group mean"; no experiment here checked they agree, and
    if `group_zscore` used a winsorised or robust centre the ratio would not be the sd.

    Written this way because `group_mean` -- the only aggregator returning a group LEVEL -- is
    documented as the HARMONIC mean, and there is no group-standard-deviation operator in the
    67-operator catalogue at all.
    """
    return "(group_neutralize(%s, %s) / group_zscore(%s, %s))" % (x, g, x, g)


def _disp_template(x, g):
    """`<xs sd of x in g> {cmp} ts_mean(<the same sd>, {d})` -- today's cross-sectional dispersion
    against its own {d}-day level. Built from one string so the two halves cannot drift apart."""
    s = _xs_sd(x, g)
    return "%s {cmp} ts_mean(%s, {d})" % (s, s)


#: Recorded once so it is not restated on every entry that needs it.
_SD_UNVERIFIED = ("the cross-sectional-sd identity assumes group_neutralize and group_zscore use the "
                  "SAME group mean; both are documented as 'the group mean' and no experiment here "
                  "checked that they agree",)


# --------------------------------------------------------------------------------- the conditions
#
# EVERY `why` STATES WHAT THE CONDITION MEASURES. None of them states why gating on it would pay,
# because no experiment here distinguished that. `origin` labels the ECONOMIC READING, not the
# arithmetic -- the arithmetic is definitional in every row:
#
#   EX-ANTE      the reading follows from the field's or operator's own documented definition.
#                "volume above its own average = participation" is EX-ANTE because `volume` is
#                documented as "Daily volume" -- shares traded IS participation, not a proxy for it.
#                "realised dispersion below its own longer-run level = calm" is EX-ANTE because
#                `ts_std_dev(returns, d)` IS the dispersion of returns; "calm" is a synonym for a
#                low value of it, not a forecast.
#   SPECULATION  the reading asserts something the definition does not contain. "close above its
#                200-day mean = TREND" is SPECULATION: being above a mean is a fact about today,
#                while "trend" asserts PERSISTENCE, and no documentation and no experiment named
#                here establishes persistence. Same for reading `close > vwap` as buying pressure --
#                `vwap` is documented only as "Daily volume weighted average price"; the docs say
#                nothing about who was pressing.
#
# `kind` separates what these things actually are:
#   regime   a state of the market that lasts longer than one print
#   event    a discrete thing that happened on a day
#   hygiene  not a regime at all -- a data-availability check, labelled so it is never counted as one
#
# Fields used are all pv1 with coverage 1.0 and dateCoverage 1.0 in
# `fetched/rc/fields/USA_TOP3000_d1.jsonl` (volume, adv20, close, high, low, vwap, returns), so a
# gate built from them does not itself introduce NaN. That was checked, not assumed.

_SPEC = (
    {
        "name": "volume_vs_own_mean",
        "template": "volume {cmp} ts_mean(volume, {d})",
        "windows": WINDOWS,
        "kind": "regime",
        "ops": ("ts_mean",),
        "variants": (
            ("hi", _GT, "participation", "EX-ANTE",
             "more shares changed hands today than on an average day of the last {d}; `volume` is "
             "documented as Daily volume, so this IS participation, not a proxy for it"),
            ("lo", _LT, "thin participation", "EX-ANTE",
             "fewer shares changed hands today than on an average day of the last {d}"),
        ),
    },
    {
        # The platform's own `if_else` doc example is `Event = volume > adv20`. Kept separate from
        # the row above because `adv20` is a PRECOMPUTED field ("Average daily volume in past 20
        # days") and `ts_mean(volume, 20)` is computed here; they need not agree on NaN handling or
        # on partial windows, and nothing here checked that they do.
        "name": "volume_vs_adv20",
        "template": "volume {cmp} adv20",
        "windows": (None,),
        "kind": "regime",
        "ops": (),
        "variants": (
            ("hi", _GT, "participation", "EX-ANTE",
             "today's volume exceeds the platform's own 20-day average daily volume field"),
            ("lo", _LT, "thin participation", "EX-ANTE",
             "today's volume is below the platform's own 20-day average daily volume field"),
        ),
    },
    {
        # `ts_rank` is documented as returning a NORMALISED rank between 0 and 1, so a 0.8 / 0.2
        # threshold is well defined. That range is from the operator's detailed docs, not inferred.
        "name": "volume_ts_rank",
        "template": "ts_rank(volume, {d}) {cmp} {thr}",
        "windows": (60, 120, 250),
        "kind": "regime",
        "ops": ("ts_rank",),
        "variants": (
            ("hi", _GT, "participation", "EX-ANTE",
             "today's volume sits in the top fifth of its own last {d} days"),
            ("lo", _LT, "thin participation", "EX-ANTE",
             "today's volume sits in the bottom fifth of its own last {d} days"),
        ),
        "thresholds": {"hi": "0.8", "lo": "0.2"},
    },
    {
        "name": "realised_vol_vs_own_level",
        "template": "ts_std_dev(returns, {d}) {cmp} ts_mean(ts_std_dev(returns, {d}), {d2})",
        "windows": ((10, 60), (10, 120), (20, 120), (20, 250), (60, 250)),
        "kind": "regime",
        "ops": ("ts_std_dev", "ts_mean"),
        "variants": (
            ("lo", _LT, "calm regime", "EX-ANTE",
             "{d}-day dispersion of daily returns is below its own {d2}-day level; ts_std_dev of "
             "returns IS realised volatility, so 'calm' is a synonym for a low value, not a forecast"),
            ("hi", _GT, "stressed regime", "EX-ANTE",
             "{d}-day dispersion of daily returns is above its own {d2}-day level"),
        ),
    },
    {
        "name": "price_vs_moving_average",
        "template": "close {cmp} ts_mean(close, {d})",
        "windows": (20, 60, 120, 250),
        "kind": "regime",
        "ops": ("ts_mean",),
        "variants": (
            ("hi", _GT, "trend (SPECULATIVE reading)", "SPECULATION",
             "the close is above its own {d}-day mean. That is definitional. Calling it a TREND "
             "asserts persistence, which no field description and no experiment here establishes"),
            ("lo", _LT, "downtrend (SPECULATIVE reading)", "SPECULATION",
             "the close is below its own {d}-day mean; the persistence claim is equally unestablished"),
        ),
    },
    {
        "name": "range_vs_own_mean",
        "template": "(high - low) {cmp} ts_mean((high - low), {d})",
        "windows": (10, 20, 60),
        "kind": "regime",
        "ops": ("ts_mean",),
        "variants": (
            ("lo", _LT, "narrow-range day", "EX-ANTE",
             "today's high-minus-low is smaller than its own {d}-day average; the range IS the "
             "day's realised span. Reading narrowness as compression that PRECEDES expansion would "
             "be SPECULATION and is not claimed"),
            ("hi", _GT, "wide-range day", "EX-ANTE",
             "today's high-minus-low is larger than its own {d}-day average"),
        ),
    },
    {
        "name": "return_shock",
        "template": "abs(returns) {cmp} ts_std_dev(returns, {d})",
        "windows": (20, 60, 120),
        "kind": "event",
        "ops": ("abs", "ts_std_dev"),
        "variants": (
            ("hi", _GT, "one-sigma move", "EX-ANTE",
             "today's absolute return exceeds its own {d}-day standard deviation, i.e. a move larger "
             "than one of this name's own recent sigmas"),
            ("lo", _LT, "quiet day for this name", "EX-ANTE",
             "today's absolute return is inside its own {d}-day standard deviation"),
        ),
    },
    {
        "name": "close_vs_vwap",
        "template": "close {cmp} vwap",
        "windows": (None,),
        "kind": "event",
        "ops": (),
        "variants": (
            ("hi", _GT, "closed above VWAP (SPECULATIVE reading)", "SPECULATION",
             "the close printed above the day's volume-weighted average price. That comparison is "
             "definitional; reading it as buying pressure is not -- `vwap` is documented only as "
             "'Daily volume weighted average price' and says nothing about who was pressing"),
            ("lo", _LT, "closed below VWAP (SPECULATIVE reading)", "SPECULATION",
             "the close printed below the day's volume-weighted average price; same caveat"),
        ),
    },
    {
        # THE PLATFORM'S OWN documented trade_when recipe. `days_from_last_change` docs state it
        # "Can be used as a trade_when condition" and give
        #     trade_when(Last_earnings_date == 0, alpha, -1)
        # This is the one place `==` / `!=` are emitted, and the left side is a day COUNT -- an
        # integer -- so equality selects a real set of days rather than a measure-zero one.
        "name": "driver_refreshed_today",
        "template": "days_from_last_change({leaf}) {cmp} 0",
        "windows": (None,),
        "kind": "event",
        "ops": ("days_from_last_change",),
        "needs_leaf": True,
        "variants": (
            ("fresh", _EQ, "the driver updated today", "EX-ANTE",
             "the layer-D field this alpha is built on changed value today; documented as a "
             "trade_when condition in the operator's own reference"),
            ("stale", _NE, "the driver is stale", "EX-ANTE",
             "the layer-D field this alpha is built on has not changed today"),
        ),
    },
    {
        # NOT A MARKET REGIME, and labelled `hygiene` so it is never counted as one. `is_nan` is
        # documented as the NaN detector and `not` as logical negation; trading only where the driver
        # has a value is data hygiene. Kept in the pool because it is the honest use of two of the
        # twelve operators, not because it gates on anything about the market.
        "name": "driver_present",
        "template": "not(is_nan({leaf}))",
        "windows": (None,),
        "kind": "hygiene",
        "ops": ("not", "is_nan"),
        "needs_leaf": True,
        "variants": (
            ("present", None, "data present -- NOT a regime", "EX-ANTE",
             "the layer-D driver has a value today; this is data availability, not a market state, "
             "and is marked kind=hygiene so nothing counts it as a regime"),
        ),
    },

    # ================================================================== ROUND 2 (P1R2) ADDITIONS
    #
    # Four families the round-1 pool had none of, plus one control. Each is here because it asks a
    # question none of the round-1 conditions can ask, not to make the pool bigger:
    #
    #   xs_position      round 1 asked only "is this name unusual AGAINST ITS OWN HISTORY". Every
    #                    condition compared a name to a time series of itself. None asked where the
    #                    name sits IN TODAY'S CROSS-SECTION.
    #   xs_dispersion    round 1 had no condition that is the same for every name on a day, so it
    #                    could not gate on a state of the MARKET as opposed to a state of a name.
    #   persistence      round 1 conditions are all facts about ONE print. `price_vs_moving_average`
    #                    was labelled SPECULATION precisely because "trend" asserts persistence that
    #                    a one-day comparison does not contain. This family MEASURES it instead.
    #   relative_regime  round 1 compared a name only to itself. This compares it to its sector.
    #   wrapper_null     the control that makes the other four readable.

    {
        # `rank` is documented as "Ranks the values of the input x among all instruments, returning
        # numbers evenly spaced between 0.0 and 1.0", so a 0.9 / 0.1 threshold selects a decile BY
        # CONSTRUCTION and needs no distributional assumption.
        #
        # NOT INDEPENDENT OF THE ALPHA, and this is the one thing that makes the family different in
        # kind from every other: `needs_leaf` is True, so the gate is a function of the SIGNAL the
        # alpha is built on. It restricts the alpha to its own extreme tail rather than to a state of
        # the market. The analysis must not pool it with market conditions; `needs_leaf` is the flag.
        "name": "xs_rank_of_driver",
        "family": "xs_position",
        "template": "rank({leaf}) {cmp} {thr}",
        "windows": (None,),
        "kind": "position",
        "scope": "per_name",
        "ops": ("rank",),
        "needs_leaf": True,
        "variants": (
            ("hi", _GT, "top decile of today's cross-section on the alpha's own driver", "EX-ANTE",
             "the layer-D driver of this alpha ranks in the top tenth of all instruments today; "
             "`rank` is documented as returning numbers evenly spaced between 0.0 and 1.0, so the "
             "threshold IS a decile. This gates on the SIGNAL, not on a market state"),
            ("lo", _LT, "bottom decile of today's cross-section on the alpha's own driver",
             "EX-ANTE",
             "the layer-D driver ranks in the bottom tenth of all instruments today; same caveat -- "
             "the condition is a function of the signal itself"),
        ),
        "thresholds": {"hi": "0.9", "lo": "0.1"},
    },
    {
        # `volume` ranked raw across names would mostly rank share counts, which differ by float and
        # price and are not comparable between instruments. `volume / adv20` is dimensionless -- each
        # name's volume in units of its own 20-day average -- so a cross-sectional rank of it
        # compares like with like. That is a property of the ratio, not a claim about what it means.
        "name": "xs_rank_of_relative_volume",
        "family": "xs_position",
        "template": "rank((volume / adv20)) {cmp} {thr}",
        "windows": (None,),
        "kind": "position",
        "scope": "per_name",
        "ops": ("rank",),
        "variants": (
            ("hi", _GT, "top decile of today's cross-section on volume-over-adv20", "EX-ANTE",
             "this name's volume, expressed in units of its own 20-day average daily volume, is in "
             "the top tenth of all instruments today; the ratio is dimensionless so names are "
             "comparable, which raw share volume is not"),
            ("lo", _LT, "bottom decile of today's cross-section on volume-over-adv20", "EX-ANTE",
             "this name's volume relative to its own 20-day average is in the bottom tenth of all "
             "instruments today"),
        ),
        "thresholds": {"hi": "0.9", "lo": "0.1"},
    },
    {
        # ROUND 1 DROPPED `cap`, and the reason it gave was specific and correct: `cap > ts_mean(cap,
        # d)` is `price_vs_moving_average` plus share issuance, so a result attributed to a "size
        # regime" could not be told apart from the price-vs-MA result. RE-EXAMINED: that argument is
        # about the TIME-SERIES comparison of cap against its own past. It does not reach the
        # CROSS-SECTIONAL rank, which orders names by size on one day and duplicates nothing in the
        # pool -- no other condition compares one name's size to another's. Kept for that reason and
        # for no other; the round-1 exclusion of `cap > ts_mean(cap, d)` stands untouched.
        "name": "xs_rank_of_cap",
        "family": "xs_position",
        "template": "rank(cap) {cmp} {thr}",
        "windows": (None,),
        "kind": "position",
        "scope": "per_name",
        "ops": ("rank",),
        "variants": (
            ("hi", _GT, "largest decile by market capitalisation", "EX-ANTE",
             "this name is in the largest tenth of the universe by market capitalisation today; "
             "`cap` is documented as Daily market capitalization, so this IS size"),
            ("lo", _LT, "smallest decile by market capitalisation", "EX-ANTE",
             "this name is in the smallest tenth of the universe by market capitalisation today"),
        ),
        "thresholds": {"hi": "0.9", "lo": "0.1"},
    },
    {
        # THE FIRST MARKET-WIDE CONDITION IN THE POOL. With group=market the value is the same for
        # every instrument on a day, so this gate turns the entire book on and off rather than
        # selecting names. That is a structurally different intervention from every round-1 condition
        # and is why `scope` exists.
        "name": "xs_dispersion_returns_market",
        "family": "xs_dispersion",
        "template": _disp_template("returns", "market"),
        "windows": (60, 120),
        "kind": "regime",
        "scope": "market_wide",
        "ops": ("group_neutralize", "group_zscore", "ts_mean"),
        "unverified": _SD_UNVERIFIED,
        "variants": (
            ("hi", _GT, "wide cross-section of returns", "EX-ANTE",
             "the standard deviation of today's returns ACROSS instruments is above its own {d}-day "
             "average. The quantity is an identity between two documented definitions "
             "(group_neutralize / group_zscore = the group sd), not a proxy; 'wide' is a synonym for "
             "a large value of it, not a forecast"),
            ("lo", _LT, "narrow cross-section of returns", "EX-ANTE",
             "the standard deviation of today's returns across instruments is below its own {d}-day "
             "average"),
        ),
    },
    {
        "name": "xs_dispersion_relative_volume_market",
        "family": "xs_dispersion",
        "template": _disp_template("(volume / adv20)", "market"),
        "windows": (60, 120),
        "kind": "regime",
        "scope": "market_wide",
        "ops": ("group_neutralize", "group_zscore", "ts_mean"),
        "unverified": _SD_UNVERIFIED,
        "variants": (
            ("hi", _GT, "unevenly distributed participation", "EX-ANTE",
             "the standard deviation ACROSS instruments of volume-over-adv20 is above its own "
             "{d}-day average, i.e. today's participation is spread more unevenly across names than "
             "usual. Which names are busy is not part of this statement"),
            ("lo", _LT, "evenly distributed participation", "EX-ANTE",
             "the standard deviation across instruments of volume-over-adv20 is below its own "
             "{d}-day average"),
        ),
    },
    {
        # group=sector: constant WITHIN a sector, different between sectors. Neither per_name nor
        # market_wide, so it gets its own scope value rather than being forced into one of those.
        "name": "xs_dispersion_returns_sector",
        "family": "xs_dispersion",
        "template": _disp_template("returns", "sector"),
        "windows": (60, 120),
        "kind": "regime",
        "scope": "group_wide",
        "ops": ("group_neutralize", "group_zscore", "ts_mean"),
        "unverified": _SD_UNVERIFIED,
        "variants": (
            ("hi", _GT, "wide cross-section of returns inside this name's sector", "EX-ANTE",
             "the standard deviation of today's returns across the members of THIS name's sector is "
             "above its own {d}-day average"),
            ("lo", _LT, "narrow cross-section of returns inside this name's sector", "EX-ANTE",
             "the standard deviation of today's returns across this name's sector is below its own "
             "{d}-day average"),
        ),
    },
    {
        # PERSISTENCE, MEASURED RATHER THAN ASSERTED. `price_vs_moving_average` is SPECULATION in
        # this pool because being above a mean is a fact about ONE day while "trend" asserts that it
        # keeps holding. `sign(close - ts_mean(close, d))` is +1/-1/0 per the sign docs, so its
        # {d2}-day mean is (#days above - #days below)/{d2} -- the persistence is now IN the
        # arithmetic, which is why the reading is EX-ANTE here and SPECULATION there. What remains
        # SPECULATION, and is NOT claimed: that a run which has held CONTINUES.
        #
        # ONE COMPARISON TOKEN ONLY. (#above - #below)/{d2} lives on a lattice of step 2/{d2} that
        # contains 0.6 for {d2} in (5, 10, 20), so `> 0.6` and `>= 0.6` are DIFFERENT conditions
        # here. Elsewhere in the pool the two select the same days and serve as a noise-floor
        # control; emitting both here would silently break that control.
        "name": "close_above_mean_persistently",
        "family": "persistence",
        "template": "ts_mean(sign(close - ts_mean(close, {d})), {d2}) {cmp} {thr}",
        "windows": ((20, 5), (20, 10), (60, 10), (60, 20)),
        "kind": "regime",
        "scope": "per_name",
        "ops": ("sign", "ts_mean"),
        "variants": (
            ("hi", _GT1, "close held above its {d}-day mean on most of the last {d2} days",
             "EX-ANTE",
             "(days above - days below)/{d2} exceeds 0.6 over the last {d2} days, where 'above' is "
             "close > its own {d}-day mean. `sign` is documented as +1/-1/0, so this count is what "
             "the arithmetic computes. No claim is made that the run continues"),
            ("lo", _LT1, "close held below its {d}-day mean on most of the last {d2} days",
             "EX-ANTE",
             "(days above - days below)/{d2} is under -0.6 over the last {d2} days, i.e. the close "
             "was below its own {d}-day mean on most of them"),
        ),
        "thresholds": {"hi": "0.6", "lo": "-0.6"},
    },
    {
        "name": "volume_above_adv20_persistently",
        "family": "persistence",
        "template": "ts_mean(sign(volume - adv20), {d}) {cmp} {thr}",
        "windows": (5, 10, 20),
        "kind": "regime",
        "scope": "per_name",
        "ops": ("sign", "ts_mean"),
        "variants": (
            ("hi", _GT1, "volume ran above adv20 on most of the last {d} days", "EX-ANTE",
             "(days above - days below)/{d} exceeds 0.6 over the last {d} days, where 'above' is "
             "today's volume > the platform's own 20-day average daily volume field"),
            ("lo", _LT1, "volume ran below adv20 on most of the last {d} days", "EX-ANTE",
             "(days above - days below)/{d} is under -0.6 over the last {d} days"),
        ),
        "thresholds": {"hi": "0.6", "lo": "-0.6"},
    },
    {
        # THIS NAME AGAINST ITS SECTOR, which no round-1 condition does -- every one of them compares
        # a name only to its own past. `group_zscore` is documented as "how far each value is from
        # the group mean in terms of standard deviations", so a threshold of 1 IS one within-sector
        # standard deviation and needs no calibration.
        "name": "vol_vs_sector_vol",
        "family": "relative_regime",
        "template": "group_zscore(ts_std_dev(returns, {d}), sector) {cmp} {thr}",
        "windows": (20, 60),
        "kind": "regime",
        "scope": "per_name",
        "ops": ("group_zscore", "ts_std_dev"),
        "variants": (
            ("hi", _GT, "this name is more volatile than its sector", "EX-ANTE",
             "this name's {d}-day realised volatility is more than one within-sector standard "
             "deviation ABOVE its sector's mean; ts_std_dev of returns IS realised volatility and "
             "group_zscore is documented in units of within-group standard deviations"),
            ("lo", _LT, "this name is calmer than its sector", "EX-ANTE",
             "this name's {d}-day realised volatility is more than one within-sector standard "
             "deviation BELOW its sector's mean"),
        ),
        "thresholds": {"hi": "1", "lo": "-1"},
    },
    {
        # `group_rank` is documented as "assigning a value between 0.0 and 1.0" within the group, so
        # 0.8 / 0.2 are quintiles of the sector by construction.
        "name": "relative_volume_rank_in_sector",
        "family": "relative_regime",
        "template": "group_rank((volume / adv20), sector) {cmp} {thr}",
        "windows": (None,),
        "kind": "regime",
        "scope": "per_name",
        "ops": ("group_rank",),
        "variants": (
            ("hi", _GT, "busiest fifth of its sector today", "EX-ANTE",
             "this name's volume relative to its own 20-day average ranks in the top fifth of its "
             "SECTOR today; group_rank is documented as returning 0.0 to 1.0 within the group"),
            ("lo", _LT, "quietest fifth of its sector today", "EX-ANTE",
             "this name's volume relative to its own 20-day average ranks in the bottom fifth of "
             "its sector today"),
        ),
        "thresholds": {"hi": "0.8", "lo": "0.2"},
    },
    {
        # Same condition at a finer grouping. Kept separate from the sector form and NOT merged,
        # because sector and industry are different partitions of the universe and nothing here
        # measured that they behave alike -- assuming they do is the thing this project calls
        # rationalising. Same `family`, so the analysis can pool them deliberately if it chooses to.
        "name": "relative_volume_rank_in_industry",
        "family": "relative_regime",
        "template": "group_rank((volume / adv20), industry) {cmp} {thr}",
        "windows": (None,),
        "kind": "regime",
        "scope": "per_name",
        "ops": ("group_rank",),
        "variants": (
            ("hi", _GT, "busiest fifth of its industry today", "EX-ANTE",
             "this name's volume relative to its own 20-day average ranks in the top fifth of its "
             "INDUSTRY today -- a finer partition than sector, and not assumed to behave like it"),
            ("lo", _LT, "quietest fifth of its industry today", "EX-ANTE",
             "this name's volume relative to its own 20-day average ranks in the bottom fifth of "
             "its industry today"),
        ),
        "thresholds": {"hi": "0.8", "lo": "0.2"},
    },
    {
        # kind=event, not regime: this is about ONE day's return, not a state that lasts.
        "name": "return_vs_sector_return",
        "family": "relative_regime",
        "template": "group_zscore(returns, sector) {cmp} {thr}",
        "windows": (None,),
        "kind": "event",
        "scope": "per_name",
        "ops": ("group_zscore",),
        "variants": (
            ("hi", _GT, "moved up more than one within-sector sigma today", "EX-ANTE",
             "today's return is more than one within-sector standard deviation above the mean return "
             "of this name's sector; that is what group_zscore measures and nothing more"),
            ("lo", _LT, "moved down more than one within-sector sigma today", "EX-ANTE",
             "today's return is more than one within-sector standard deviation below the mean "
             "return of this name's sector"),
        ),
        "thresholds": {"hi": "1", "lo": "-1"},
    },
    {
        # THE NULL CONTROL FOR THE WRAPPER ITSELF, and it is not a condition at all.
        # `close` has coverage 1.0 and dateCoverage 1.0 in the USA TOP3000 d1 catalogue, so
        # `is_nan(close)` is false for every name on every day and this predicate is TRUE by
        # construction -- hence scope="constant", which is honest about it selecting nothing.
        # Per the trade_when docs (x true -> the alpha takes its new value) `trade_when(TRUE, a, -1)`
        # is the IDENTITY. That is a prediction, not a fact: if this arm measures differently from an
        # ungated alpha then the wrapper is doing something the documentation does not describe, and
        # every gated-vs-ungated comparison in the round is confounded by it.
        "name": "always_true",
        "family": "wrapper_null",
        "template": "not(is_nan(close))",
        "windows": (None,),
        "kind": "hygiene",
        "scope": "constant",
        "ops": ("not", "is_nan"),
        "variants": (
            ("control", None, "TRUE for every name every day -- NOT a regime", "EX-ANTE",
             "close has coverage 1.0 and dateCoverage 1.0, so this predicate is true by "
             "construction. It is the null control for the trade_when wrapper: the identity gate"),
        ),
    },
)


def _fmt(text, d, d2, thr):
    return (text.replace("{d2}", str(d2)).replace("{d}", str(d))
                .replace("{thr}", str(thr)))


def build_pool():
    """Every layer-C condition, fully expanded. Deterministic: no rng, no sampling.

    Each entry carries the CONDITION and a one-line `why` saying what it measures, plus `origin`
    (EX-ANTE / SPECULATION) on the economic reading and `kind` (regime / event / hygiene).
    """
    pool = []
    for spec in _SPEC:
        for suffix, cmps, reading, origin, why in spec["variants"]:
            thr = (spec.get("thresholds") or {}).get(suffix)
            for w in spec["windows"]:
                d, d2 = (w if isinstance(w, tuple) else (w, None))
                for cmp_tok in (cmps or (None,)):
                    cond = _fmt(spec["template"], d, d2, thr)
                    if cmp_tok is not None:
                        cond = cond.replace("{cmp}", cmp_tok)
                    name = "%s_%s" % (spec["name"], suffix)
                    if d is not None:
                        name += "_%s" % d
                    if d2 is not None:
                        name += "_%s" % d2
                    if cmp_tok is not None:
                        name += "_%s" % _CMP_TAG[cmp_tok]
                    pool.append({
                        "name": name,
                        "family": spec.get("family", spec["name"]),
                        "cond": cond,
                        "kind": spec["kind"],
                        "scope": spec.get("scope", "per_name"),
                        "reading": _fmt(reading, d, d2, thr),
                        "origin": origin,
                        "why": _fmt(why, d, d2, thr),
                        "needs_leaf": bool(spec.get("needs_leaf")),
                        "cmp": cmp_tok,
                        "ops": list(spec["ops"]) + ([_CMP_NAME[cmp_tok]] if cmp_tok else []),
                        "unverified": list(spec.get("unverified", ())),
                    })
    return pool


_CMP_NAME = {">": "greater", ">=": "greater_equal", "<": "less", "<=": "less_equal",
             "==": "equal", "!=": "not_equal"}

#: Most name-varying first. Used only to give a compound the scope of its most selective part.
_SCOPE_ORDER = ("per_name", "group_wide", "market_wide", "constant")


def combine(e1, e2, op, *, kind="regime"):
    """`and(c1, c2)` / `or(c1, c2)` -- both are 2-arity CALLS per their own definitions.

    A compound gate is narrower than either part, and nothing here measured whether narrower is
    better. MECHANISM: UNKNOWN.
    """
    if op not in ("and", "or"):
        raise ValueError("combine takes 'and' or 'or', got %r" % op)
    return {
        "name": "%s_%s_%s" % (e1["name"], op, e2["name"]),
        "family": "compound",
        "cond": "%s(%s, %s)" % (op, e1["cond"], e2["cond"]),
        "kind": kind,
        # The compound varies across names if EITHER part does, so it takes the most name-varying
        # scope of the two. A per_name condition ANDed with a market_wide one still selects names.
        "scope": min((e1["scope"], e2["scope"]), key=_SCOPE_ORDER.index),
        "reading": "%s %s %s" % (e1["reading"], op.upper(), e2["reading"]),
        # A compound is only as well-founded as its weakest part.
        "origin": "SPECULATION" if "SPECULATION" in (e1["origin"], e2["origin"]) else "EX-ANTE",
        "why": "both parts must hold on the same day: (%s) %s (%s)" % (e1["why"], op.upper(),
                                                                      e2["why"]),
        "needs_leaf": e1["needs_leaf"] or e2["needs_leaf"],
        "cmp": None,
        "ops": sorted(set(e1["ops"]) | set(e2["ops"]) | {op}),
        "unverified": sorted(set(e1["unverified"]) | set(e2["unverified"])),
    }


# ------------------------------------------------------------------------------------ the render

#: The four gate shapes, each traceable to something STATED rather than invented:
#:   hold   Khoa's example 1 and the trade_when docs: `trade_when(cond, alpha, -1)`, z=-1 meaning
#:          "never exit", so on a false trigger the alpha HOLDS its previous value.
#:   exit   trade_when's documented third capability -- z true closes the position to NaN. Without
#:          this mode the z parameter is dead in every render.
#:   scale  the platform's own SIMULATED if_else example (sid JjOJdajA, sharpe 1.58):
#:          `if_else(event, 2 * alpha, alpha)` -- conditional leverage.
#:   pick   Khoa's example 2: `if_else(D1 > D2, D1, D2)` -- choose between two expressions.
#: `flip` (`if_else(cond, alpha, -alpha)`) was considered and LEFT OUT: it changes the sign of the
#: signal rather than when it trades, which is a different experiment from the one this layer is for.
MODES = ("hold", "exit", "scale", "pick")

#: Multipliers for `scale`. The documented example used 2.
SCALES = (1.5, 2.0, 3.0)


def render_gate(entry, expr, rng, *, mode=None, exit_entry=None, expr2=None, leaf=None):
    """Wrap a layer-D (A/B-composed) expression in a layer-C gate. Returns (formula, meta).

    `expr` is passed through VERBATIM -- the gate is a wrapper and never reaches inside it, which is
    what keeps the gate operators out of layers A and B by construction rather than by a check.

    FAILS CLOSED on a missing leaf. A condition carrying an unsubstituted `{leaf}` would be shipped
    to a simulation as literal text; a bare `except: pass` hiding exactly this class of thing already
    cost this project days.
    """
    cond = _condition(entry, leaf)
    available = ["hold", "scale"]
    if exit_entry is not None:
        available.append("exit")
    if expr2 is not None:
        available.append("pick")
    mode = mode or rng.choice(available)
    if mode not in MODES:
        raise ValueError("unknown mode %r" % mode)

    scale = None
    if mode == "hold":
        formula = "trade_when(%s, %s, -1)" % (cond, expr)
    elif mode == "exit":
        if exit_entry is None:
            raise ValueError("mode='exit' needs an exit_entry; z has no default")
        exit_cond = _condition(exit_entry, leaf)
        # DEGENERATE BY CONSTRUCTION, refused rather than emitted. Per the docs, z is evaluated
        # first: z true -> NaN. If z is the same predicate as x, then every day the trigger fires
        # the position is simultaneously closed, so the alpha can only ever be NaN or a held stale
        # value. That is a simulation spent for no information, the same class as the
        # counter-on-a-counter rule in layer B.
        if exit_cond == cond:
            raise ValueError("exit condition is identical to the trigger (%s): the alpha would be "
                             "closed on exactly the days it fires" % entry["name"])
        formula = "trade_when(%s, %s, %s)" % (cond, expr, exit_cond)
    elif mode == "scale":
        scale = rng.choice(SCALES)
        formula = "if_else(%s, (%s * %s), %s)" % (cond, expr, scale, expr)
    else:
        if expr2 is None:
            raise ValueError("mode='pick' needs expr2; if_else takes three arguments, none optional")
        formula = "if_else(%s, %s, %s)" % (cond, expr, expr2)

    meta = {
        "layer_c": entry["name"], "family": entry["family"], "mode": mode, "cond": cond,
        "kind": entry["kind"], "scope": entry["scope"],
        "reading": entry["reading"], "origin": entry["origin"], "why": entry["why"],
        "scale": scale,
        "exit_cond": _condition(exit_entry, leaf) if mode == "exit" else None,
        "unverified": list(entry["unverified"]),
        # FLAGGED, NOT REFUSED. `if_else(cond, alpha * k, alpha)` with a condition that is the same
        # for every name on a day multiplies the WHOLE cross-section by k. If the platform normalises
        # the alpha vector to book size then that is exactly the ungated alpha and the row carries no
        # information -- the same class as the exit-equals-trigger degeneracy, which IS refused. The
        # difference is that the exit-equals-trigger case follows from the trade_when docs, while
        # this one depends on a normalisation this module has NOT established. So it is flagged and
        # left runnable: paired against its ungated partner it MEASURES whether the platform
        # normalises, which nothing here can otherwise answer.
        "degenerate_if_normalised": bool(mode == "scale"
                                         and entry["scope"] in ("market_wide", "constant")),
    }
    return formula, meta


def _condition(entry, leaf):
    cond = entry["cond"]
    if "{leaf}" in cond:
        if not leaf:
            raise ValueError("condition %r needs a layer-D leaf and none was given" % entry["name"])
        cond = cond.replace("{leaf}", leaf)
    return cond


# -------------------------------------------------------------------------------- operator checks

def load_gate_operators(path=None):
    """The 12 gate operators as the PLATFORM defines them, with required/optional parsed by the same
    parser layer A/B uses (`layered_alpha._params`), so the symbolic-default rule has one copy."""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import layered_alpha as LA

    j = json.loads(pathlib.Path(path or OPS).read_text())
    ops = j if isinstance(j, list) else (j.get("operators") or [])
    out = {}
    for o in ops:
        if o.get("name") not in GATE_OPS:
            continue
        req, opt = LA._params(o.get("definition"))
        out[o["name"]] = {
            "name": o["name"], "category": o.get("category"), "definition": o.get("definition"),
            "required": req, "optional": opt,
            # An infix definition does not parse as a call, which is the signal that there IS no
            # documented call form. Recorded rather than worked around.
            "infix": o["name"] in INFIX_COMPARISONS,
            "arity": None if o["name"] in INFIX_COMPARISONS else (1 + len(req),
                                                                  1 + len(req) + len(opt)),
        }
    return out


# ---------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", action="store_true", help="write the pool to state/layered/")
    ap.add_argument("--sample", type=int, default=6, help="print this many rendered gates")
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    pool = build_pool()
    gate_ops = load_gate_operators()

    print("layer C pool  %3d conditions" % len(pool))
    for kind in ("regime", "event", "position", "hygiene"):
        n = sum(1 for e in pool if e["kind"] == kind)
        print("    %-8s %3d" % (kind, n))
    for origin in ("EX-ANTE", "SPECULATION"):
        print("    %-12s %3d" % (origin, sum(1 for e in pool if e["origin"] == origin)))

    print("\ngate operators (%d/12 found in %s)" % (len(gate_ops), OPS.name))
    for name in sorted(GATE_OPS):
        o = gate_ops.get(name)
        if o is None:
            print("    %-14s MISSING from operators.json" % name)
            continue
        print("    %-14s %-16s %-28s %s" % (
            name, o["category"], o["definition"],
            "INFIX (no documented call form)" if o["infix"] else "call, arity %d..%d" % o["arity"]))

    if args.build:
        POOLDIR.mkdir(parents=True, exist_ok=True)
        (POOLDIR / "pool_c_gate.json").write_text(json.dumps(pool, indent=2))
        print("\nwrote %s/pool_c_gate.json" % POOLDIR)

    rng = random.Random(args.seed)
    demo = "rank(ts_delta(close, 5))"
    print("\n--- %d sample gates around %s ---" % (args.sample, demo))
    leafless = [e for e in pool if not e["needs_leaf"]]
    for i in range(args.sample):
        e = rng.choice(pool)
        f, m = render_gate(e, demo, rng, exit_entry=rng.choice(leafless),
                           expr2="rank(-ts_delta(close, 20))", leaf="close")
        print("\n[%d] %s  mode=%s  %s / %s" % (i + 1, m["layer_c"], m["mode"], m["kind"],
                                               m["origin"]))
        print("    %s" % f)
        print("    why: %s" % m["why"][:150])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
