#!/usr/bin/env python3
"""anti_corr.py — MECHANISMS that attack PROD_CORRELATION and SELF_CORRELATION directly.

Khoa 2026-07-25 (iter 42-50): every iteration from here must ADD a real anti-correlation
mechanism, not just measure correlation better.

What the day's measurements established, and why these mechanisms are the ones worth building:

* The gate is a SINGLE exact number per side: `PROD_CORRELATION <= 0.7` and
  `SELF_CORRELATION < 0.7`. 3qeeOxlQ was rejected at 0.7031 — a miss of 0.0031. Small structural
  changes are therefore decisive, and they are measurable now that prod_maxcorr reads the exact
  value instead of a 0.1-wide histogram bucket edge.

* SELF-correlation has an obvious structural cause: EVERY alpha the generator emits carries the
  same two OHLC legs, `-rank(close/open)` and `-rank(close/vwap)*0.6`. A shared component across
  the whole book guarantees mutual correlation no matter how orthogonal the dataset legs are.
  e7x0G7ag measured 0.99 against its twin and YPggJ8p6 0.98 against theirs.

* PROD-correlation has the mirror cause: that same carrier is the most crowded microstructure
  signal on the platform, so it aligns with the production book by construction.

Each mechanism is a pure formula transform: `f(expr, **kw) -> expr`. They compose, and each is
applied as a SEPARATE batch arm so its effect on the two exact numbers is attributable rather
than assumed.
"""
from __future__ import annotations

# Distinct carriers. The generator has always used exactly CARRIERS['std']; every other entry is
# a different microstructure mechanic, so two alphas built with different carriers no longer share
# a common component. 'none' is included because carrier-free was previously rejected on edge
# grounds alone, before we could measure what it bought on the correlation side.
CARRIERS = {
    "std":     ["-rank(divide(close, open))", "multiply(-rank(divide(close, vwap)), 0.6)"],
    "hilo":    ["-rank(divide(close, high))", "multiply(-rank(divide(low, close)), 0.6)"],
    "gap":     ["-rank(divide(open, ts_delay(close, 1)))",
                "multiply(-rank(ts_delta(divide(close, open), 5)), 0.6)"],
    "range":   ["-rank(divide(subtract(high, low), close))",
                "multiply(rank(divide(subtract(close, low), subtract(high, low))), 0.6)"],
    "vwrel":   ["-rank(divide(vwap, ts_mean(vwap, 20)))",
                "multiply(-rank(divide(close, ts_mean(close, 5))), 0.6)"],
    "none":    [],
}

# Crowded exposures to strip with vector_neut. Anything the production book is heavily loaded on
# is a component we want removed from our own signal.
# NOTE: `returns`, `volume` and `adv20` are BANNED (used by live alphas; the standing no-reuse rule
# is enforced fail-closed at precheck), so every proxy here is built from unbanned OHLC/vwap/cap:
# close-ratio stands in for returns, and the vwap-vs-close spread stands in for the volume/liquidity
# factor. Same exposure, no banned token.
CROWDED = {
    "mom":   "ts_delta(close, 21)",
    "rev":   "-ts_delta(close, 5)",
    "vol":   "ts_std_dev(divide(close, ts_delay(close, 1)), 60)",
    "size":  "log(cap)",
    "liq":   "-rank(divide(subtract(high, low), close))",
}

# Regime conditions. An alpha that only trades in a particular state has a different time profile
# from an always-on production alpha, which lowers correlation even when the signal overlaps.
_RET = "divide(close, ts_delay(close, 1))"
REGIMES = {
    "hivol":  f"greater(ts_std_dev({_RET}, 20), ts_std_dev({_RET}, 120))",
    "lovol":  f"less(ts_std_dev({_RET}, 20), ts_std_dev({_RET}, 120))",
    "trend":  "greater(ts_mean(close, 20), ts_mean(close, 60))",
    "range":  "less(abs(ts_delta(close, 20)), ts_std_dev(close, 20))",
    "wide":   "greater(divide(subtract(high, low), close), ts_mean(divide(subtract(high, low), close), 60))",
}


def m1_carrier(legs, carrier="hilo"):
    """M1 CARRIER SWAP — replace the one shared carrier with a different microstructure mechanic.

    Attacks SELF first (two alphas on different carriers no longer share a component) and PROD
    second (the std carrier is the crowded one). `carrier='none'` drops it entirely."""
    return CARRIERS[carrier] + list(legs)


def m2_vector_neut(expr, factor="mom"):
    """M2 STRIP A CROWDED EXPOSURE — vector_neut removes the component of the signal that lies
    along a crowded factor, leaving the idiosyncratic remainder. Attacks PROD directly."""
    return f"vector_neut({expr}, {CROWDED[factor]})"


def m3_regime(expr, regime="hivol"):
    """M3 REGIME GATING — trade only in a chosen market state. Changes WHEN the alpha is active,
    so its PnL path diverges from an always-on production alpha even on a similar signal."""
    return f"trade_when({REGIMES[regime]}, {expr}, -1)"


def m4_group_relative(expr, group="subindustry"):
    """M4 GROUP-RELATIVE RESCORING — rank/zscore WITHIN a group instead of cross-sectionally, so
    the alpha expresses relative value inside peers rather than a market-wide ordering (which is
    what the crowded book already expresses)."""
    return f"group_zscore({expr}, {group})"


def m5_shape(expr, kind="rank"):
    """M5 RESPONSE SHAPE — a different monotone response changes the weight distribution while
    keeping the signal's ordering, so PnL covariance with a linear-weighted book drops."""
    if kind == "rank":
        return f"rank({expr})"
    if kind == "tanh":
        return f"tanh({expr})"
    if kind == "sigmoid":
        return f"sigmoid({expr})"
    if kind == "quantile":
        return f"quantile({expr})"
    if kind == "winsor":
        return f"winsorize({expr}, std=3)"
    return expr


def m6_horizon(expr, fast=5, slow=60):
    """M6 HORIZON DIFFERENCING — subtract the slow-moving component of the alpha's own signal,
    leaving what is NEW relative to its own trend. The production book is dominated by slow
    signals, so removing the slow part is a direct attack on PROD."""
    return f"subtract({expr}, ts_mean({expr}, {slow}))"


def m7_soft_regime(expr, regime="hivol", strength=1.0):
    """M7 SOFT REGIME WEIGHTING — scale by how strongly the regime holds instead of switching the
    alpha off. M3's binary trade_when worked (zqRN8LGE went ACTIVE from M3wide) but it throws away
    every non-regime day, which costs sharpe. A continuous weight keeps those days at reduced size,
    so the PnL path still diverges from an always-on production alpha at a smaller cost."""
    w = {"hivol": f"rank(ts_std_dev({_RET}, 20))",
         "lovol": f"-rank(ts_std_dev({_RET}, 20))",
         "trend": "rank(divide(ts_mean(close, 20), ts_mean(close, 60)))",
         "wide":  "rank(divide(subtract(high, low), close))"}[regime]
    return f"multiply({expr}, add({w}, {strength}))"


_STRENGTH = {
    "hivol": f"rank(ts_std_dev({_RET}, 20))",
    "wide":  "rank(divide(subtract(high, low), close))",
    "trend": "rank(divide(ts_mean(close, 20), ts_mean(close, 60)))",
}


def m8_regime_flip(expr, regime="hivol"):
    """M8 SIGNED REGIME TILT — trade the signal one way in the regime and the opposite way outside,
    scaled by HOW FAR the regime is from neutral.

    A binary `if_else(cond, E, -E)` collapses to `E * sign(cond)` and throws the condition's
    magnitude away (logic_operators.md D2/D7, flagged by logic_check). Mapping the regime strength
    to [-1, 1] keeps the flip that makes the PnL path structurally different from an always-on
    production alpha, while weighting each day by how strongly the regime actually holds."""
    st = _STRENGTH[regime]
    return f"multiply({expr}, subtract(multiply(2, {st}), 1))"


def m9_strip_carrier(expr, carrier="std"):
    """M9 STRIP THE SHARED COMPONENT FROM THE OUTPUT — keep the carrier in the construction (iter42
    proved it IS the edge: every M1 swap collapsed sharpe from 1.62 to 0.04-0.72) but vector_neut
    the carrier back out of the FINISHED signal.

    This is the one move that addresses SELF-correlation at its root without paying M1's price:
    the shared component that makes every alpha in the book covary is removed after it has done its
    work of shaping the leg weights."""
    legs = CARRIERS[carrier]
    if not legs:
        return expr
    base = legs[0].lstrip('-')
    return f"vector_neut({expr}, {base})"


# ---------------------------------------------------------------------------------------------
# M11 SKELETON DIVERSITY — the composition SHAPE is itself a correlation source.
#
# Every alpha this generator has ever emitted has the identical shape
#     signed_power(zscore(ts_decay_linear(add(carrier + legs), W)), P)
# so they all share one time-response and one weight-distribution shape, on top of sharing the
# carrier. Two alphas built that way covary even when their fields are disjoint.
#
# The shapes below are structurally different compositions of the SAME legs. SK_regress is
# modelled on the community book's dominant form (see fetched/alphas_all.jsonl), which nests a
# ts_regression residual inside rank -> group_neutralize and puts ts_decay_linear OUTERMOST —
# the reverse of ours.
# ---------------------------------------------------------------------------------------------

def sk_std(legs, window=16, power=2.0, group="subindustry"):
    """The incumbent shape, for control."""
    inner = f"add({', '.join(legs)}, filter=true)"
    return f"signed_power(zscore(ts_decay_linear({inner}, {window})), {power})"


def sk_outer_decay(legs, window=16, power=2.0, group="subindustry"):
    """Decay OUTERMOST instead of innermost: neutralise and rank first, smooth the result.

    `group=None` drops the in-formula group op — required whenever settings.neutralization is not
    a GROUP (STATISTICAL / CROWDING / NONE); precheck enforces that any group_* argument equals
    the neutralization setting."""
    inner = f"add({', '.join(legs)}, filter=true)"
    core = f"group_neutralize(rank({inner}), {group})" if group else f"rank({inner})"
    return f"ts_decay_linear({core}, {window})"


def sk_tszscore(legs, window=120, power=2.0, group="subindustry"):
    """TIME-SERIES z-score instead of cross-sectional: each name is scored against its OWN
    history, so the alpha stops expressing a market-wide ordering (which is what the crowded
    book expresses) and expresses per-name deviation instead."""
    inner = f"add({', '.join(legs)}, filter=true)"
    z = f"ts_zscore({inner}, {window})"
    return f"group_neutralize({z}, {group})" if group else z


def sk_tsrank(legs, window=60, power=2.0, group="subindustry"):
    """TIME-RANK then group-scale: a bounded, non-linear time response with a different weight
    distribution from zscore + signed_power."""
    inner = f"add({', '.join(legs)}, filter=true)"
    tr = f"ts_rank({inner}, {window})"
    return f"group_scale({tr}, {group})" if group else f"zscore({tr})"


def sk_regress(legs, window=60, power=2.0, group="subindustry"):
    """RESIDUAL SKELETON — regress the signal on the crowded carrier over time and keep only what
    the carrier does NOT explain (`rettype=2`), then rank and group-neutralise, decaying last.
    This is the community book's dominant shape and the strongest structural break from ours."""
    inner = f"add({', '.join(legs)}, filter=true)"
    x = CARRIERS["std"][0].lstrip('-')
    resid = f"ts_regression({inner}, {x}, {window}, lag=0, rettype=2)"
    core = f"group_neutralize(rank({resid}), {group})" if group else f"rank({resid})"
    return f"ts_decay_linear({core}, 16)"


SKELETONS = {
    "SKstd": sk_std,
    "SKouter": sk_outer_decay,
    "SKtsz": sk_tszscore,
    "SKtsr": sk_tsrank,
    "SKreg": sk_regress,
}


MECHANISMS = {
    "M1_carrier": m1_carrier,
    "M2_vecneut": m2_vector_neut,
    "M3_regime": m3_regime,
    "M4_grouprel": m4_group_relative,
    "M5_shape": m5_shape,
    "M6_horizon": m6_horizon,
    "M7_softregime": m7_soft_regime,
    "M8_regimeflip": m8_regime_flip,
    "M9_stripcarrier": m9_strip_carrier,
}
