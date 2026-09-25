"""The taxonomy: every axis a frame is classified on, and the rule that assigns each value.

Every axis except `turnover_class` is a function of the frame TEXT and is EX-ANTE: it restates operator
semantics (OPERATORS.md, fetched/rc/operators.json, forge/typed.py's operator families). None of these
values says anything about performance, and an axis named after an economic idea (economic_function)
names the QUANTITY the operators compute, not the effect a fill captures -- which effect a fill
captures depends on its fields and is MECHANISM: UNKNOWN until measured.

`turnover_class` is POST-HOC: the observed median turnover of the frame's canonical rows, per cell.
It is UNKNOWN without evidence and MIXED when cells disagree; it is never pooled across cells.

A LEG is a data-bearing subtree: one that holds a slot or a pinned field outside a condition position.
Condition positions for legs: argument 0 of if_else and trade_when, and trade_when's argument 2 (its exit
condition per OPERATORS.md; FRAME SPEC v1 still numbers fields there as slots).
"""
from __future__ import annotations

import math

from forge import typed as TY

TAXONOMY_VERSION = 1

COMBINERS = {
    "SINGLE": "one leg",
    "SUM": "add of >= 2 legs, not all weighted",
    "WEIGHTED_SUM": "add of >= 2 legs, each multiply(leg, constant)",
    "SPREAD": "subtract of two legs",
    "PRODUCT": "multiply of >= 2 legs",
    "RATIO": "divide of two legs",
    "RELATION": "ts_corr / ts_covariance / ts_regression / ts_co_* / regression_proj / vector_neut / vector_proj of two legs",
    "SWITCH": "if_else whose two branches both carry a leg",
    "OTHER": "any other operator joining >= 2 legs (max, min, group ops with a data argument, ...)",
}
CONDITIONING = {
    "NONE": "no if_else, no trade_when",
    "IF_ELSE": "exactly one if_else",
    "TRADE_WHEN": "exactly one trade_when",
    "MULTI": "two or more conditioning operators",
}
CONDITION_INPUT = {
    "NONE": "no conditioning operator",
    "CONSTANT": "the condition subtrees hold no field",
    "FIXED": "the condition subtrees hold only fixed fields (condition or pinned)",
    "SLOT": "the condition subtrees hold only slots",
    "MIXED": "the condition subtrees hold fixed fields and slots",
}
GROUPING = {
    "NONE": "no group argument",
    "TOKEN": "a group token (industry, sector, ...) in the text",
    "SLOT": "a slot in a group position",
    "BOTH": "a group token and a group slot",
}
# (name, largest window included); trading-calendar conventions: 5 = a week, 21 = a month, 63 = a quarter,
# 252 = a year. Definitions, not findings.
HORIZONS = (("DAYS", 5), ("MONTH", 21), ("QUARTER", 63), ("YEAR", 252), ("MULTIYEAR", math.inf))
HORIZON_NAMES = ("NONE",) + tuple(h for h, _ in HORIZONS)
# (name, upper bound exclusive). 0.01 and 0.70 are the platform's LOW_TURNOVER / HIGH_TURNOVER limits as
# they appear in the forge journal's checks; 0.30 is the turnover below which memory/ladder-is-a-hard-gate.md
# records a lower IS_LADDER_SHARPE bar; 0.10 is a definition.
TURNOVER_BANDS = (("BELOW_MIN", 0.01), ("LOW", 0.10), ("MID", 0.30), ("HIGH", 0.70), ("ABOVE_MAX", math.inf))
TURNOVER_CLASSES = ("UNKNOWN", "MIXED") + tuple(b for b, _ in TURNOVER_BANDS)
# The quantity a leg computes: its OUTERMOST function-defining operator (forge/typed.py families).
FUNCTION_OPS = (("CHANGE", TY.CHANGE), ("DISPERSION", TY.DISPERSION), ("CO_MOVEMENT", TY.RELATE),
                ("COUNT_TIMING", TY.COUNTING))
ECONOMIC_FUNCTIONS = {
    "CHANGE": "a change over time (ts_delta, ts_returns, ts_av_diff, last_diff_value, ...); momentum or "
              "reversal is set by the orientation, not by the frame",
    "DISPERSION": "the spread of the input (ts_std_dev, ts_skewness, ts_entropy, vec_stddev, ...)",
    "CO_MOVEMENT": "how two inputs move together (ts_corr, ts_covariance, ts_regression, ...)",
    "COUNT_TIMING": "counts and time-since (ts_count_nans, days_from_last_change, ts_arg_max, vec_count, ...)",
    "LEVEL": "no function-defining operator: a (smoothed, normalised) level",
    "MIXED": "legs compute different quantities",
}
DIMENSIONS = {
    "combiner": tuple(COMBINERS), "conditioning": tuple(CONDITIONING), "condition_input": tuple(CONDITION_INPUT),
    "grouping": tuple(GROUPING), "horizon": HORIZON_NAMES, "turnover_class": TURNOVER_CLASSES,
    "economic_function": tuple(ECONOMIC_FUNCTIONS),
}
RELATION_OPS = TY.RELATE | {"regression_proj", "vector_neut", "vector_proj"}
_LEG_EXCLUDED = {("if_else", 0), ("trade_when", 0), ("trade_when", 2)}


def _is_const(n) -> bool:
    if n.op is None:
        return n.name is None and isinstance(n.value, float)
    return n.op == "reverse" and len(n.args) == 1 and _is_const(n.args[0])


def _kids(n, fixed_or_slot):
    """The data-bearing children of n (positional, then keyword), condition positions excluded."""
    out = [a for i, a in enumerate(n.args) if (n.op, i) not in _LEG_EXCLUDED and _has_data(a, fixed_or_slot)]
    return out + [v for v in n.kw.values() if v.op is not None and _has_data(v, fixed_or_slot)]


def _has_data(n, names) -> bool:
    if n.op is None:
        return n.name in names
    return bool(_kids(n, names))


def _flatten(n, op, names):
    out = []
    for k in _kids(n, names):
        out.extend(_flatten(k, op, names) if k.op == op else [k])
    return out


def _combiner(tree, names):
    n = tree
    while True:
        kids = _kids(n, names) if n.op is not None else []
        if len(kids) >= 2:
            break
        if not kids:
            return "SINGLE", [n]
        n = kids[0]
    if n.op == "add":
        legs = _flatten(n, "add", names)
        weighted = all(l.op == "multiply" and len(_kids(l, names)) == 1 and any(_is_const(a) for a in l.args) for l in legs)
        return ("WEIGHTED_SUM" if weighted else "SUM"), legs
    if n.op == "multiply":
        return "PRODUCT", _flatten(n, "multiply", names)
    name = {"subtract": "SPREAD", "divide": "RATIO", "if_else": "SWITCH"}.get(n.op)
    if name is None:
        name = "RELATION" if n.op in RELATION_OPS else "OTHER"
    return name, kids


def _function(n, names) -> str:
    if n.op is None:
        return "LEVEL"
    for name, ops in FUNCTION_OPS:
        if n.op in ops:
            return name
    kids = _kids(n, names)
    if n.op == "divide" and len(kids) == 2 and kids[0] is n.args[0]:
        kids = kids[:1]                     # typed: "the denominator is a scale, not a leg"
    fs = {_function(k, names) for k in kids}
    if not fs:
        return "LEVEL"
    return fs.pop() if len(fs) == 1 else "MIXED"


def _cond_names(n, inside, out):
    if n.op is None:
        if inside and n.name is not None:
            out.append(n.name)
        return
    for i, a in enumerate(n.args):
        _cond_names(a, inside or (n.op, i) in _LEG_EXCLUDED, out)
    for v in n.kw.values():
        if v.op is not None:
            _cond_names(v, inside, out)


def _depth(n) -> int:
    if n.op is None:
        return 0
    return 1 + max([_depth(a) for a in n.args] + [_depth(v) for v in n.kw.values()] + [0])


def _count_ops(n, ops) -> int:
    if n.op is None:
        return 0
    return (n.op in ops) + sum(_count_ops(a, ops) for a in n.args) + sum(_count_ops(v, ops) for v in n.kw.values())


def band(value, bands):
    for name, hi in bands:
        if value < hi or (hi == math.inf):
            return name
    return bands[-1][0]


def horizon(windows) -> tuple:
    """(class, largest window) from [[op, window], ...]."""
    if not windows:
        return "NONE", None
    w = max(v for _, v in windows)
    for name, hi in HORIZONS:
        if w <= hi:
            return name, w
    return HORIZONS[-1][0], w


def turnover_class(evidence) -> str:
    """POST-HOC: the band of each cell's median turnover; UNKNOWN without data, MIXED when cells differ."""
    cells = (evidence or {}).get("cells") or {}
    got = {band(c["turnover_median"], TURNOVER_BANDS) for c in cells.values() if c.get("turnover_median") is not None}
    if not got:
        return "UNKNOWN"
    return got.pop() if len(got) == 1 else "MIXED"


def classify(normal, evidence=None) -> dict:
    """The frame's characteristics on every axis, plus its family."""
    tree = normal.tree
    slots = {nm for nm in _names(tree) if normal.is_slot(nm)}
    fixed = set(normal.pinned.values()) | set(normal.cond_fields)
    data = slots | set(normal.pinned.values())
    comb, legs = _combiner(tree, data)
    n_if, n_tw = _count_ops(tree, {"if_else"}), _count_ops(tree, {"trade_when"})
    cond = "NONE" if n_if + n_tw == 0 else "MULTI" if n_if + n_tw > 1 else ("IF_ELSE" if n_if else "TRADE_WHEN")
    cn = []
    _cond_names(tree, False, cn)
    has_fixed, has_slot = any(x in fixed for x in cn), any(x in slots for x in cn)
    cin = ("NONE" if cond == "NONE" else "MIXED" if has_fixed and has_slot else "FIXED" if has_fixed
           else "SLOT" if has_slot else "CONSTANT")
    gslot = any(s["context"] == "GROUP" for s in normal.slots)
    grouping = "BOTH" if normal.groups and gslot else "TOKEN" if normal.groups else "SLOT" if gslot else "NONE"
    hz, maxw = horizon(normal.windows)
    ctx = {}
    for s in normal.slots:
        ctx[s["context"]] = ctx.get(s["context"], 0) + 1
    fn = _function(tree, data)
    leg_fns = [_function(l, data) for l in legs]
    out = {
        "taxonomy_version": TAXONOMY_VERSION,
        "combiner": comb, "n_legs": len(legs), "conditioning": cond, "condition_input": cin,
        "grouping": grouping, "horizon": hz, "max_window": maxw, "economic_function": fn, "leg_functions": leg_fns,
        "slot_kinds": "+".join("%s*%d" % (k, ctx[k]) for k in sorted(ctx)), "n_slots": len(normal.slots),
        "depth": _depth(tree), "operators": list(normal.operators), "turnover_class": turnover_class(evidence),
    }
    out["family"] = family(out)
    return out


def family(ch: dict) -> str:
    return "%s.%s.%s" % (ch["combiner"], ch["conditioning"], ch["economic_function"])


def _names(n):
    if n.op is None:
        return [n.name] if n.name is not None else []
    out = []
    for a in n.args:
        out.extend(_names(a))
    for v in n.kw.values():
        if v.op is not None:
            out.extend(_names(v))
    return out
