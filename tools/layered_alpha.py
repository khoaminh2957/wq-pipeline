#!/usr/bin/env python3
"""Three pre-built pools (A / B / C) and a random draw that composes one alpha per simulation.

THE SHAPE, as the operator specified it (Khoa, 2026-08-13):

    LAYER A   outer functions, a combination of 1..10 LEGS
    LAYER B   inside each A leg, other functions, a combination of 1..10
    LAYER C   a real field, or a pre-built economic ratio that actually means something

    alpha = A_combine( a1(B1), a2(B2), ..., ak(Bk) )        k drawn from 1..10
    Bi    = b1(b2(...(Ci)...))                              chain drawn from 1..10
    Ci    = <field>  |  divide(<field_x>, <field_y>)

The pools are BUILT AHEAD and written to disk, so a simulation round draws and submits rather than
computing anything. That is the operator's "được tạo sẵn": at sim time there is nothing to derive.

THE LAYER SPLIT is the operator's, not mine, and it maps onto the platform's own 67-operator
catalogue (`fetched/operators.json`):

    A  <-  Cross Sectional + the outer-shaping Arithmetic  (rank, zscore, winsorize, scale,
           normalize, quantile, signed_power, sign, log, sqrt, abs, inverse, ...)
    B  <-  Time Series + Group                             (ts_decay_linear, ts_delta, ts_rank,
           ts_zscore, ts_mean, ts_backfill, ts_std_dev, hump, group_neutralize, group_rank, ...)

CARRIER: NOT PRIVILEGED, BY OPERATOR DECISION. The 11,731 same-segment historical rows are NOT all
gems -- 430 are, 11,301 are not, and the carrier is present in 430/430 AND 11,301/11,301. It has
ZERO variance and cannot discriminate anything (council R2-06 F5). A carrier-free sweep measured 0
zero-fail in 2,039, but its ladder evidence was a gate-PRESENCE artifact and does not stand. The
operator was told this and chose full randomness anyway, so `close`/`open`/`vwap` sit in pool C as
ordinary draws with no boost. `carrier_present()` labels every composed alpha so the resulting yield
split answers the question with data instead of with the prior. **This is a deliberate departure
from the only construction class this project has ever seen produce a gem** — recorded here so a
future reader does not mistake it for an oversight.

WHAT IS NOT ESTABLISHED. That randomly composed structures produce gems at all. The prior evidence
points the other way (bare ratios: 0 gems in 1,048 sims), and nothing here predicts otherwise. The
experiment is the point; the outcome is not assumed.

--------------------------------------------------------------------------------------------------
THE 2^4 CELL (P1R2). `PREREG_P1.md` §3 pre-registers a balanced 2^4 factorial over four factors, and
`INTEGRATION_P1R1.md` S8 measured that the code could assign exactly ONE of them. A `Cell` is one
draw of all four, assigned PER ALPHA and recorded in `meta`, so every journalled row carries the cell
it was generated under:

    D  layer-D field screen   leaves drawn only from `screen_pool_c` survivors   (a FILTER)
    C  layer-C market gate    the composed alpha wrapped by `layer_c.render_gate` (ADDITIVE)
    U  unit model             the `units` arm; U=0 is the `control` arm           (a FILTER)
    S  ordered layer-B stage  S=1 REMOVES the rule (`free`); S=0 applies it     (a FILTER)
                              -- the polarity is inverted on purpose; see `Cell`

`CellAssigner` draws from a shuffled fixed-quota block of all 16 cells (permuted-block
randomisation), not from four independent coin flips, because independent flips drift and PREREG §2
is void without balanced cells. PREREG §3.3 requires the cell to be drawn BEFORE generation: D is a
filter, and generate-then-filter lets the treatment set its own sample size. Both D and U are applied
at the POINT OF CHOICE here, so no draw is ever rejected and the cell's realised count equals its
assigned count by construction.

FAILS CLOSED. `compose` raises if D=on without `pool_c_kept` or C=on without `gate_pool`. Composing a
D=on row from the unscreened pool would journal a complete-looking row for an experiment that never
varied D, which is the exact class `INTEGRATION_P1R1.md` ranks "silent first".
"""
import argparse
import collections
import itertools
import json
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPS = ROOT / "fetched/rc/operators.json"
FIELDS = ROOT / "fetched/rc/fields/USA_TOP3000_d1.jsonl"
POOLDIR = ROOT / "state/layered"

#: The three layer-D screens, and the gate pool layer C draws from. Named here rather than inline so
#: the packaging round has one surface to move (HARNESS_SOP.md, "Packaging").
SCREEN_FILES = {
    "coverage": "screen_coverage.json",
    "variation": "screen_variation.json",
    "meaning": "screen_meaning.json",
}
GATE_POOL_FILE = "pool_c_gate.json"

#: Both layers draw a combination size in this range -- the operator's "tổ hợp từ 1 tới 10".
COMBO_MIN, COMBO_MAX = 1, 10

#: LAYER A LEG COUNT, narrowed from the operator's original 1-10 on 2026-08-13, by Khoa, after the
#: measurement below. Layer B chain depth still uses the full COMBO range -- only the leg count moved.
#:
#: MEASURED, and it is the strongest structural signal this project has produced: within our own
#: 117 rows, **2 legs failed CONCENTRATED_WEIGHT 0 times in 11; 9 legs failed 11 times in 11**, and
#: the relationship survives stratification on book size (legs<=4 / book>=500 = 29% fail; legs>=5 /
#: book>=500 = 66%). That gate kills 64.1% of our alphas against 7.4% of the historical corpus.
#:
#: THE RISK KHOA ACCEPTED, recorded here rather than left implicit: n=117 is small, the region 5-10
#: is being discarded on ONE gate, and nothing establishes that many legs are bad for sharpe -- leg
#: count was a clean null there (rho=-0.060, p=0.53). If factor E (one normaliser over the whole
#: ensemble) turns out to fix concentration on its own, this narrowing bought nothing and cost the
#: wide end of the search space. MECHANISM: UNKNOWN for why leg count drives concentration.
LEGS_MIN, LEGS_MAX = 1, 4

#: A hard ceiling on how many layer-C leaves one alpha may hold. A x B is up to 100 legs, and a
#: formula that long is rejected by the platform before it is ever a result. Chosen so the draw
#: stays honest at small sizes and only bites at the extreme corner; every truncation is COUNTED and
#: reported, never silent -- a silent cap reads as "the full space was explored".
MAX_LEAVES = 24

#: Windows for the time-series layer. These are the decays this project has actually simulated;
#: nothing here measured that they are the right ones.
WINDOWS = (5, 10, 20, 60, 120, 250)
GROUPS = ("industry", "subindustry", "sector", "market")

#: Operators excluded from random composition, each for a stated reason -- not taste.
#: WRITTEN INFIX, NEVER AS A CALL (operator instruction, 2026-08-13): use `+ - * /`.
#: This is not cosmetic. Measured over 2,000 draws before the change, calling them as functions
#: produced **12,643 arity violations** -- `multiply` 10,929, `add` 1,774, `divide` 940 -- because
#: `add(x, y, filter=false)` and `multiply(x, y, ...)` are BINARY and the composer was handing them
#: one operand. Every one of those would have spent a simulation on a formula the platform rejects.
#: Infix removes the failure mode by construction rather than by a check.
INFIX = {"add", "subtract", "multiply", "divide"}

_EXCLUDE = {
    "trade_when",       # control flow, not a transform: needs an event predicate to mean anything
    "bucket",           # returns a grouping, not a signal
    "vector_neut",      # VECTOR-typed operands only; pool C is scalar
    "kth_element",      # needs an index whose meaning depends on the operand's shape
    "ts_regression",    # 3+ operands with distinct roles; a random pairing is noise by construction
    "ts_corr", "ts_covariance",   # binary time series; same reason

    # FOUND BY READING THE PLATFORM'S OWN DESCRIPTIONS after 4 of 4 live simulations returned ERROR.
    # Both were being wrapped around a signal, and neither takes one:
    "ts_step",          # "Returns a counter of days, incrementing by one each day." Its definition
                        # is literally `ts_step(1)` -- it takes a LENGTH and GENERATES a series. The
                        # composer was writing `ts_step(<field>)`, which is not a transform at all.
    "densify",          # "Converts a GROUPING FIELD of many buckets into lesser number of only
                        # available buckets." It operates on a grouping field, not on a signal, so
                        # `densify(<field>)` asks it to compress something that is not buckets.

    # ADMITTED WITH THE 85-OPERATOR FILE (council R2-08 settled `fetched/rc/operators.json` as
    # authoritative). These are the members of the 18 newly-reachable operators that pool C's SCALAR
    # fields cannot feed. Same EX-ANTE ground as `vector_neut` above:
    "vec_min", "vec_max", "vec_count", "vec_stddev", "vec_range",
                        # "... of VECTOR FIELD x". Pool C is USA_TOP3000_d1 scalar fields. NOTE: the
                        # historical corpus reached COMPLETE with these 2,787-3,071 times each, so
                        # they work ON VECTOR FIELDS -- admitting them here needs vector fields in
                        # pool C first, not a change to this line.
    "group_cartesian_product",   # "Merge two GROUPS into one group" -- returns a group index, same
                        # class as `bucket` and `densify`.
    "regression_proj", "vector_proj",   # 2 operands with distinct roles (target vs independent);
                        # a random pairing is noise by construction, as for `ts_regression`.
    "inst_pnl",         # its own description warns against use in an alpha; SPECULATION that it
                        # composes at all -- 0 terminal-state occurrences anywhere (R2-08).
}


# ------------------------------------------------------------------------------------ operators

def _params(definition):
    """Positional parameter names after `x`, split into required and optional.

    Parsed from the platform's own `definition` string (e.g. `ts_decay_linear(x, d, dense = false)`),
    because that is the authority on arity. A name carrying `=` has a default and may be omitted.
    """
    m = re.match(r"\s*\w+\s*\((.*)\)\s*$", definition or "")
    if not m:
        return [], []
    parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
    req, opt = [], []
    for p in parts[1:]:                       # parts[0] is the operand itself
        name = p.split("=")[0].strip()
        if "=" not in p:
            req.append(name)
            continue
        default = p.split("=", 1)[1].strip()
        # A DEFAULT THAT IS A NAME IS NOT A DEFAULT. `ts_backfill(x, lookback = d, k=1)` reads like
        # an optional parameter, and treating it as one produced
        #     Required attribute "lookback" must have a value.
        # on 3 of 4 live simulations. The `d` is a PLACEHOLDER meaning "supply a window", not a
        # value. A real default is a literal -- `false`, `0.01`, `4.0`, `gaussian`, `1`. So: a
        # symbolic default means REQUIRED, a literal default means optional.
        if _is_literal(default):
            opt.append(name)
        else:
            req.append(name if name not in ("lookback",) else "d")
    return req, opt


_LITERAL = re.compile(r"^(true|false|-?\d+(\.\d+)?|gaussian|cauchy|uniform)$", re.I)


def _is_literal(token):
    """Is this default an actual value, or a placeholder naming what the caller must supply?"""
    return bool(_LITERAL.match(token.strip()))


def load_operators(path=None):
    j = json.loads(pathlib.Path(path or OPS).read_text())
    return j if isinstance(j, list) else (j.get("operators") or [])


# ----------------------------------------------------------------------------------- unit model
#
# THE PLATFORM STATES ITS OWN EXPECTATION. Every unit warning journalled in
# `state/layered/runs/*.jsonl` has one shape:
#     Incompatible unit for input of "hump" at index 0, expected "Unit[]", found "Unit[CSPrice:1]"
# So an operator either DEMANDS a unitless operand or it does not, and an expression either carries
# a unit or it does not. `fetched/operators.json` carries NO unit field at all -- 67 operators, keys
# are name/category/definition/description/documentation/level/scope -- so the classes below are
# read off each operator's own DEFINITION and DESCRIPTION (EX-ANTE) and then checked against the 19
# journalled warning rows.
#
# THE PREVIOUS RULE AND WHY IT MADE THINGS WORSE. It required one of six assumed "normalisers"
# (rank, zscore, quantile, normalize, scale, winsorize) outermost on every leg. `add` fell to 2 of
# 12, but the total rate rose, because the rule is not about position -- it is per operator.

#: DEMANDS a unitless operand. The five without a note were NAMED BY THE PLATFORM; counted over the
#: 19 journalled warning rows (distinct alpha x distinct message):
#:     hump 8 | add 4 | group_backfill 4 | sqrt 2 | ts_product 1
#: `sqrt` appears in that list only BECAUSE of the domain guard added at the same time as the
#: previous fix: `sqrt(abs(x))` still carries the unit of x.
#: `log` and `subtract` are EX-ANTE only and have never been observed warning -- the logarithm of a
#: dimensional quantity has no definition, and `subtract` is `add` with a sign. They are included
#: because a false positive costs one draw and a false negative costs a simulation.
#:
#: NOT ESTABLISHED: that this set is COMPLETE. The platform reports exactly ONE failure per
#: simulation (all 19 rows carry a single message), so any other operator that also demands `Unit[]`
#: is masked by whichever failure came first and could not appear here. 5 of the 37 pool operators
#: have been observed demanding; the other 32 are UNKNOWN, not cleared.
#: MECHANISM: UNKNOWN for why `group_backfill` -- documented as a winsorized group mean, which
#: preserves units -- demands a unitless operand. Recorded as an observation, not explained.
DEMANDS_UNITLESS = {"hump", "sqrt", "log", "ts_product", "group_backfill", "add", "subtract"}

#: STRIPS the operand's unit: the output is a rank, a count of days, a sign, or a ratio to a spread
#: or a standard deviation, none of which carries the operand's dimension. EX-ANTE, from the
#: platform's own descriptions -- rank "returning numbers evenly spaced between 0.0 and 1.0",
#: ts_arg_max "returns the number of days since the maximum value occurred", zscore "measured in
#: terms of standard deviations from the mean", ts_scale "to a 0-1 range based on its minimum and
#: maximum values".
#:
#: NOT ESTABLISHED BY DATA, AND THE CORPUS CANNOT ESTABLISH IT. Because the platform reports only
#: the FIRST failure, a formula that did not warn at one operator may simply have failed earlier;
#: absence of a warning is not evidence that an operator stripped. The corpus can only REFUTE a
#: member of this set, and it did -- see `winsorize` below. The weakest entries are the day-counters
#: (ts_arg_min/ts_arg_max/days_from_last_change/ts_count_nans): they demonstrably do not carry the
#: operand's unit, but whether the platform gives them a unit of their own is UNKNOWN -- no `found`
#: string in the corpus names anything but Price and Share.
STRIPS = {
    "rank", "zscore", "quantile", "scale", "sign",
    "ts_rank", "ts_zscore", "ts_scale",
    "ts_arg_min", "ts_arg_max", "ts_count_nans", "days_from_last_change",
    "group_rank", "group_zscore", "group_scale",
}

# EVERYTHING ELSE PRESERVES its operand's unit. Two members were assumed to strip and do not:
#
# WINSORIZE -- REFUTED BY THE CORPUS, and this is the defect that made the previous fix worse.
# `winsorize(x, std=4)` CLIPS at four standard deviations; it never divides, so the output is in the
# operand's units. Two rows in which EVERY leg already ended in one of the six assumed normalisers
# still warned on `add`, and in both the `found` unit fits exactly one leg, whose outer is winsorize:
#   78zG61Rx  found Unit[CSPrice:-1] <- winsorize(inverse(ts_decay_linear(momentum_vwap..., 10)))
#                                       the only unit-inverting operator anywhere in that formula
#   WjAYPg0d  found Unit[CSPrice:1]  <- winsorize(abs(ts_sum(atm_put_option_forward_price, 20)))
# Under the previous model both rows are unexplained, since it held all six to strip.
#
# NORMALIZE -- EX-ANTE, no data. `normalize(x, useStd = false, limit = 0.0)`: on the default the
# operator subtracts the cross-sectional mean and does nothing else, and a difference of two
# quantities keeps their unit. The composer never passes `useStd`.

#: The six operators that may sit outermost on a leg. UNCHANGED from the previous fix -- the defect
#: was never which operators are eligible, it was the belief that all six strip.
A_OUTER = {"rank", "zscore", "quantile", "normalize", "scale", "winsorize"}

#: The four of them that strip. The legs are joined with `+`, and `add` demands `Unit[]`, so a leg
#: must END unitless. That does NOT mean the outermost operator must be a stripper: `winsorize` and
#: `normalize` preserve, and preserving a unitless expression leaves it unitless. They keep the slot
#: whenever the chain below them has already stripped, and only lose it when it has not.
A_OUTER_STRIPPING = A_OUTER & STRIPS


# --------------------------------------------------------------------------------- unit checker

UNITLESS, UNITFUL = 0, 1

#: The comparison tokens were ABSENT from this regex until the layer-C gate started flowing through
#: here. `INTEGRATION_P1R1.md` S3/L1 measured the consequence: at top level the tokeniser stopped at
#: the first `>` and `_parse` analysed only the fragment before it (a silent wrong answer -- all 107
#: gate conditions returned "no refusal" from a parse that never reached them); nested inside a call
#: it ran off the end of the token list with `IndexError`. Both are fixed by tokenising them.
#: Multi-character tokens come FIRST in the alternation, or `<=` lexes as `<` then `=`.
_TOK = re.compile(r"\s*(<=|>=|==|!=|[A-Za-z_][A-Za-z0-9_]*|\d+\.?\d*|[(),+\-*/<>])")

_CMP_TOKENS = ("<", ">", "<=", ">=", "==", "!=")


def _parse(formula):
    """The composed formula as a tree. Only the grammar this module emits: calls, `+ - * /`,
    identifiers and numbers."""
    toks, i = [], 0
    while i < len(formula):
        m = _TOK.match(formula, i)
        if not m:
            break
        toks.append(m.group(1))
        i = m.end()
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        t = toks[pos[0]]
        pos[0] += 1
        return t

    def expr():
        n = sums()
        while peek() in _CMP_TOKENS:
            take()
            n = ("#cmp", [n, sums()])
        return n

    def sums():
        n = term()
        while peek() in ("+", "-"):
            n = (take(), [n, term()])
        return n

    def term():
        n = atom()
        while peek() in ("*", "/"):
            n = (take(), [n, atom()])
        return n

    def atom():
        t = take()
        if t == "(":
            n = expr()
            take()
            return n
        if t == "-":
            return ("neg", [atom()])
        if t[0].isdigit():
            return ("#lit", [])
        if peek() == "(":
            take()
            args = []
            if peek() != ")":
                args.append(expr())
                while peek() == ",":
                    take()
                    args.append(expr())
            take()
            return (t, args)
        return ("#leaf", [])

    return expr()


def unit_refusals(formula):
    """Every operator in `formula` that this model says is being handed a unit it cannot take.

    Empty means the model predicts no `Incompatible unit` warning. THIS IS A PREDICTION FROM THE
    MODEL ABOVE, NOT AN OBSERVATION -- and the model is deliberately a CONSERVATIVE
    OVER-APPROXIMATION: a leaf field's unit is not in the field metadata, so every leaf is treated
    as carrying one. Measured over the journalled corpus, it names the operator the platform named
    on 19 of 19 warning rows and misses none, and it also refuses 70 of the 98 rows the platform
    passed. It bounds the warning rate from above; it does not estimate it.
    """
    out = []

    def walk(node):
        op, args = node
        if op == "#lit":
            return UNITLESS
        if op == "#leaf":
            return UNITFUL                # a field's unit is not in the metadata -- conservative
        if op == "#cmp":
            # A comparison returns a BOOLEAN, which carries no unit. Both operands are still walked,
            # so a refusal INSIDE a gate condition is still reported. NO refusal is raised for
            # comparing two operands of different classes: nothing in the 19 journalled warning rows
            # names a comparison operator, so a rule there would be SPECULATION, not a model.
            for a in args:
                walk(a)
            return UNITLESS
        if op in ("+", "-"):
            cs = [walk(a) for a in args]
            if any(c != cs[0] for c in cs):
                out.append("add" if op == "+" else "subtract")
            return max(cs)
        if op in ("*", "/"):
            return UNITFUL if any(walk(a) == UNITFUL for a in args) else UNITLESS
        if op == "neg":
            return walk(args[0])
        cs = [walk(a) for a in args]
        c0 = cs[0] if cs else UNITLESS
        if op in DEMANDS_UNITLESS and c0 != UNITLESS:
            out.append(op)
        return UNITLESS if op in STRIPS else c0

    walk(_parse(formula))
    return out


def split_layers(ops):
    """(pool_a, pool_b) by the operator's rule: A = Cross Sectional + outer Arithmetic,
    B = Time Series + Group.

    An operator whose required parameters this composer cannot supply meaningfully is dropped and
    named in `dropped`, so the pool's contents are auditable rather than mysterious.
    """
    a, b, dropped = [], [], []
    for o in ops:
        name, cat = o.get("name"), o.get("category")
        if name in INFIX:
            dropped.append((name, "written infix as + - * / -- never called"))
            continue
        if name in _EXCLUDE:
            dropped.append((name, "excluded: see _EXCLUDE"))
            continue
        req, opt = _params(o.get("definition"))
        unsupported = [r for r in req if r not in ("d", "group", "y")]
        if unsupported:
            dropped.append((name, "required param(s) %s not supplied by the composer" % unsupported))
            continue
        entry = {"name": name, "required": req, "optional": opt, "category": cat}
        if cat in ("Cross Sectional", "Arithmetic", "Transformational"):
            a.append(entry)
        elif cat in ("Time Series", "Group"):
            b.append(entry)
        else:
            dropped.append((name, "category %r belongs to neither layer" % cat))
    return a, b, dropped


# ------------------------------------------------------------------------------------- layer C

#: Description phrases that mark a quantity as a RATE, RATIO, PERCENTILE or SCORE. Dividing two of
#: these produces a number with no economic reading -- a percentile over a percentile is not a
#: quantity. Ratios are only built where at least one side is a LEVEL.
_ALREADY_NORMALISED = re.compile(
    r"\b(percentile|percentage|ratio|rate|score|rank|index|z-?score|probability|likelihood|"
    r"yield|margin|growth|change|per share|proportion|share of)\b", re.I)

#: Description phrases marking a LEVEL -- a quantity with units that a denominator can normalise.
_LEVEL = re.compile(
    r"\b(total|amount|value|volume|count|number|revenue|sales|assets|liabilit|equity|debt|"
    r"income|earnings|cash|capital|expense|cost|shares|price|market cap|size)\b", re.I)


#: MINIMUM COVERAGE FOR A LEAF, operator instruction (Khoa, 2026-08-14): "cắt bớt các field có
#: coverage bé hơn 95% trong pool". Applied at load, so EVERY consumer of the pool -- the climb, the
#: frameworks, the factorial -- draws from the same screened catalogue rather than each re-deciding.
#:
#: What it costs: 31,114 of 67,205 fields survive (46.3%). The pool stays large.
#: What it removes: the median field sits at coverage 0.9289 and the 10th percentile at 0.5000, and
#: **12,079 fields sit at EXACTLY 0.5000** -- a spike this project has noticed before and never
#: explained. MECHANISM: UNKNOWN for why so many land on that value.
#:
#: HONEST LIMIT, because a coverage screen has been measured here before and did NOT survive: the
#: council tested coverage as a predictor of degeneracy and it failed (BACKBONE_V2 K7), and the
#: separate "avoid option/earnings data" rule collapsed once pooled within coverage (D8). So this
#: cut is an OPERATOR DECISION about what belongs in the pool, not a finding that low-coverage
#: fields produce worse alphas. Nothing here has established that. It is a flag, and a round run at
#: 0.0 measures the difference whenever anyone wants the answer.
MIN_COVERAGE = 0.95


def load_fields(path=None, region="USA", delay=1, universe="TOP3000", min_coverage=None,
                pyramid_gate=True, drop_spent=True):
    """The catalogue, screened on coverage and on the pyramid.

    PYRAMID GATE (Khoa, 2026-08-15): a category whose pyramid cell is already full is switched off
    entirely -- there is no reason to spend a simulation on a cell that cannot be advanced. And the
    cells still OPEN are exempted from the coverage floor, because the floor was an operator
    decision about pool membership and never a measured finding, while an open cell with eight
    usable fields is a real constraint. That exemption is what takes the pool from 1,196 back to
    2,012. See `pool_gate.py`.

    Fails OPEN: if the pyramid counts cannot be read, nothing is disabled. Silently shrinking the
    pool 26x looks exactly like working, which is this project's dominant bug class.
    """
    min_coverage = MIN_COVERAGE if min_coverage is None else min_coverage
    gate = {"ok": False}
    if pyramid_gate:
        import pool_gate as PGATE
        gate = PGATE.state(region=region, delay=delay)
    # SPENT FIELDS. Retired by a finished cycle, or belonging to an alpha already submitted.
    spent = set()
    if drop_spent:
        try:
            import climb as _CLIMB
            spent = _CLIMB.spent_fields()
        except Exception:                      # noqa: BLE001 - a missing store bans nothing
            spent = set()
    rows, dropped, gated, retired = [], 0, 0, 0
    for line in pathlib.Path(path or FIELDS).read_text(errors="ignore").splitlines():
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") != "MATRIX":
            continue                          # pool C is scalar; VECTOR needs a reducer first
        if (r.get("_region"), r.get("_delay"), r.get("_universe")) != (region, delay, universe):
            continue
        if not (r.get("description") and r.get("id")):
            continue
        if r["id"] in spent:
            retired += 1
            continue
        if gate.get("ok"):
            cat = r.get("category")
            cat = cat.get("name") if isinstance(cat, dict) else cat
            if cat in gate["disabled"]:
                gated += 1
                continue
            if cat in gate["open"]:
                rows.append(r)             # OPEN CELL: exempt from the coverage floor
                continue
        cov = r.get("coverage")
        if min_coverage and (not isinstance(cov, (int, float)) or cov < min_coverage):
            # A field with NO coverage value is dropped too. An unknown coverage is not a high one,
            # and this project's dominant bug class is a missing value read as a benign one.
            dropped += 1
            continue
        rows.append(r)
    load_fields.dropped = dropped
    load_fields.gated = gated
    load_fields.retired = retired
    load_fields.gate = gate
    return rows


def build_pool_c(fields, *, max_ratios_per_dataset=40, rng=None):
    """Layer C: raw fields plus economic ratios built FROM THE DESCRIPTIONS, not from the names.

    A ratio is admitted only when it can be read as a real quantity:
      * both operands sit in the SAME dataset -- crossing datasets pairs numbers whose units and
        vintages nobody here has checked
      * the DENOMINATOR is a level (has units something can be measured against)
      * the two are not the same field
    A percentile divided by a percentile is refused, because the result has no economic reading even
    though it is arithmetically fine. That refusal is what "có ý nghĩa thật sự" buys.

    NOT ESTABLISHED: that these ratios carry signal. The screen is on MEANING, and meaning is a
    necessary condition for a hypothesis, not evidence for one.
    """
    rng = rng or random.Random(1234)
    by_ds = {}
    for f in fields:
        by_ds.setdefault((f.get("dataset") or {}).get("id"), []).append(f)

    raw = [{"kind": "field", "expr": f["id"], "dataset": (f.get("dataset") or {}).get("id"),
            "category": (f.get("category") or {}).get("name"), "why": f["description"][:160]}
           for f in fields]

    ratios = []
    for ds, fs in by_ds.items():
        if len(fs) < 2:
            continue
        levels = [f for f in fs if _LEVEL.search(f["description"] or "")
                  and not _ALREADY_NORMALISED.search(f["description"] or "")]
        if not levels:
            continue
        pairs = []
        for num in fs:
            for den in levels:
                if num["id"] == den["id"]:
                    continue
                pairs.append((num, den))
        rng.shuffle(pairs)
        for num, den in pairs[:max_ratios_per_dataset]:
            ratios.append({
                "kind": "ratio",
                "expr": "(%s / %s)" % (num["id"], den["id"]),
                "dataset": ds,
                "category": (num.get("category") or {}).get("name"),
                "why": "%s  PER  %s" % (num["description"][:80], den["description"][:80]),
            })
    return raw + ratios


# ------------------------------------------------------------- the layer-D screen (factor D)
#
# THE THREE SCREENS DISAGREE ON VOCABULARY AND ON NAMESPACE. Measured here, 2026-08-13, and
# independently in `INTEGRATION_P1R1.md` S4/S5:
#
#   file                   keys                        verdict values
#   screen_coverage.json   73,258  pool-C **expr**     `keep` 72,793 / `drop` 465  (67 are ratios)
#   screen_variation.json     682  raw **field id**    `keep` 641 / `unknown` 41 / drop 0
#   screen_meaning.json    67,205  raw **field id**    `KEEP` 62,380 / `DROP` 3,688 / `FLAG` 1,137
#
# Consequences measured before normalising, both re-derived in this module's own numbers below:
#   * a naive `verdict == "drop"` filter removes 0 of the 3,688 meaning-drops (they are UPPERCASE);
#     1 of the 3,688 is separately caught by the coverage file, so 3,687 survive.
#   * 367 of the 6,053 ratios contain a dropped field. 67 of those (all of them coverage-drops) are
#     already dropped by the coverage file under their own ratio key; the other 300 survive.
#
# THE NORMALISATION, AND WHAT EACH STEP ASSUMES. Stated because each is a decision, not a fact:
#
#  N1  CASE. Verdicts are compared upper-cased. ASSUMES `drop` and `DROP` denote the same decision.
#      Support: coverage's own `why` strings are threshold statements ("coverage 0.1236 < 0.20") and
#      meaning's `_meta.verdict_semantics.DROP` is "description resolves to a named opaque family".
#      Both read as "remove from the pool". Nothing tested that they are equally RELIABLE -- see N5.
#  N2  NAMESPACE. Everything is resolved in **expr** space. An expr is dropped if its own key is
#      dropped by any screen, or if any field id it is built from is dropped by any screen.
#      ASSUMES a ratio is no better than its worst component. This is not invented: the coverage
#      screen already behaves this way (all 67 ratios holding a coverage-dropped field are themselves
#      keyed `drop`), and N2 extends that behaviour to the two screens that were never keyed by expr.
#  N3  `FLAG` IS NOT A DROP. Stated by `screen_meaning.json` `_meta`: "tier B ... Hand-audit precision
#      7/15 = 0.47. NOT usable as a drop. Label only."
#  N4  ABSENCE IS NOT A DROP, and neither is `unknown`. Stated by `screen_variation.json` `_meta`:
#      "Absence from this file means UNKNOWN, never drop." Under N4 the variation screen contributes
#      ZERO drops, so factor D is in practice coverage + meaning; a "3-of-3 screen" label on this
#      round would overstate it.
#  N5  RECORDED, NOT RESOLVED: `screen_meaning.json` `_meta.READ_THIS` says its own performance check
#      "does NOT support using this screen as a filter" (n=115, difference -0.015 sharpe,
#      permutation p=0.46, corpus MDE ~0.10) and asks to ship it as a label. PREREG §3.1 nevertheless
#      names D a filter over "coverage, variation, economic meaning", and D=on is what that
#      pre-registration says. The disagreement is carried into the journal (`meta.layer_d_screen`)
#      rather than settled here. MECHANISM: UNKNOWN for whether a meaningless description produces a
#      worse alpha -- the only measurement available is the null above.
#
# MEASURED under N1-N4 against the shipped pool (`state/layered/pool_c.json`, 73,258 entries):
#     kept 68,806 (93.9%)  = 63,120 fields + 5,686 ratios
#     removed 4,452        = 4,085 field exprs + 367 ratio exprs
# Cross-check (RULE 0 #5): `INTEGRATION_P1R1.md` reports 69,106 survivors for a case-insensitive
# intersection that does NOT propagate to ratios. 69,106 - 300 = 68,806, and 300 is exactly the count
# of meaning-dropped ratios that only N2 catches. The two derivations agree.

#: `(numerator / denominator)` as `build_pool_c` emits it. Field ids carry no spaces, so `\S+` is
#: unambiguous; anything that does not match is treated as a single raw field id.
_RATIO_EXPR = re.compile(r"^\((\S+) / (\S+)\)$")


def expr_components(expr):
    """The field ids an expr is built from. A raw field is its own only component."""
    m = _RATIO_EXPR.match(expr)
    return [m.group(1), m.group(2)] if m else [expr]


def load_screens(pooldir=None):
    """The three layer-D screens as written, unnormalised. Missing files raise -- a screen silently
    absent would shrink the D treatment to whatever happened to be on disk."""
    d = pathlib.Path(pooldir or POOLDIR)
    return {name: json.loads((d / fn).read_text()) for name, fn in SCREEN_FILES.items()}


def screen_drops(screens):
    """{screen name -> the set of ids that screen DROPS}, case-normalised (N1). `_meta` is skipped,
    `FLAG` (N3) and `unknown` (N4) are not drops."""
    out = {}
    for name, table in screens.items():
        out[name] = {k for k, v in table.items()
                     if k != "_meta" and isinstance(v, dict)
                     and str(v.get("verdict") or "").upper() == "DROP"}
    return out


def screen_pool_c(pool_c, screens):
    """(kept, report) -- the layer-D pool factor D=on draws its leaves from.

    Returns the survivors under N1-N4 plus a report naming what each screen removed, so the D
    treatment's actual content is auditable from the run rather than from this docstring.
    """
    per_screen = screen_drops(screens)
    dropped = set().union(*per_screen.values()) if per_screen else set()
    kept, removed = [], collections.Counter()
    for x in pool_c:
        expr = x["expr"]
        if any(t in dropped for t in [expr] + expr_components(expr)):
            removed[x["kind"]] += 1
        else:
            kept.append(x)
    report = {
        "n_pool": len(pool_c),
        "n_kept": len(kept),
        "n_removed": sum(removed.values()),
        "removed_by_kind": dict(removed),
        "drops_per_screen": {k: len(v) for k, v in per_screen.items()},
        "normalisation": "N1 case-folded; N2 resolved in expr space, a ratio inherits its "
                         "components' drops; N3 FLAG is not a drop; N4 absence/unknown is not a drop",
    }
    return kept, report


# --------------------------------------------------------------------------- the 2^4 cell
#
# One draw of the four pre-registered factors, assigned per alpha and recorded on every row.

class _CellBase(collections.namedtuple("Cell", "D C U S E W")):
    pass


_CellBase.__new__.__defaults__ = (False, False)      # E and W default off


class Cell(_CellBase):
    """One draw of the four pre-registered factors. **Read S carefully; its polarity is not the
    obvious one and getting it wrong silently flips the sign of that factor's whole contrast.**

        D = 1   the layer-D field screen is APPLIED (leaves drawn from the survivors)
        C = 1   the layer-C market gate is APPLIED (the alpha is wrapped)
        U = 1   the unit model is APPLIED (the `units` arm); U = 0 is `control`
        S = 1   the ordered layer-B stage rule is **REMOVED** -- the `free` composer
        S = 0   the ordered layer-B stage rule is APPLIED -- the `ordered` composer
        E = 1   ONE NORMALISER WRAPS THE WHOLE ENSEMBLE. 83.3% of clean historical alphas do this;
                0 of 132 of ours did, because the join line had nothing after it. No pool change can
                produce it.
        W = 1   pool C is drawn FREQUENCY-WEIGHTED from the clean corpus instead of uniformly.
                Measured: uniform gives a carrier in 0.002 of draws -- identical to today's pool --
                while weighted gives 0.574 against the clean corpus's 0.863. The clean corpus's
                defining property is a FREQUENCY, so a uniform vocabulary swap changes nothing.
                W = 1 deliberately bakes a POST-HOC regularity in as a prior; the arm measures
                whether that prior pays.

    S is inverted relative to the other three because PREREG §3.1 defines the factor as *"removal of
    the ordered-stage rule ... removal of a filter"*, and because `layered_report.LEGACY_ARM` already
    decodes the round-1 corpus this way: `free -> ("S", 1)`, `ordered -> ("S", 0)`. Coding S as "the
    rule is on" would have made every row this module writes disagree in sign with every row already
    journalled, with no error anywhere. So "the S switch is off by default" means the ordered-stage
    rule is not applied, i.e. **S = 1** in the default cell.
    """
    __slots__ = ()

    @property
    def id(self):
        # Built from the namedtuple's OWN field names, so adding a factor cannot leave the id
        # silently truncated -- the hardcoded "D%dC%dU%dS%d" raised the moment E and W were added,
        # which is the good failure; a format string with spare slots would have dropped them.
        return "".join("%s%d" % (f, int(bool(v))) for f, v in zip(self._fields, self))

    def as_dict(self):
        """The `meta['factors']` shape `layered_report.cell_of` reads first."""
        # Built from the tuple's OWN fields. The hardcoded four-key version kept emitting D/C/U/S
        # after E and W existed, so the report saw them as level-UNKNOWN on every row and silently
        # analysed four factors while six were being varied.
        return {f: int(bool(v)) for f, v in zip(self._fields, self)}

    @property
    def stage_ordered(self):
        """True when the ordered layer-B stage rule is APPLIED. See the polarity note above."""
        return not self.S


#: 2^6 = 64 cells. Two factors were added after round 3 measured what no pool change could reach:
#: E (one normaliser over the whole ensemble) and W (frequency-weighted pool C). At the round size
#: PREREG uses, 64 cells still gives every MAIN EFFECT half the batch -- which is the whole point of
#: a factorial and the reason adding factors is nearly free. Interactions are not powered and are
#: exploratory, exactly as PREREG already states for the first four.
ALL_CELLS = tuple(Cell(*bits) for bits in itertools.product((False, True), repeat=6))


class CellAssigner:
    """PERMUTED-BLOCK randomisation over the 16 cells: shuffle all 16, hand them out, reshuffle.

    Not four independent coin flips. Independent flips drift -- at PREREG's N=640 per round the
    per-cell count is Binomial(640, 1/16), sd 6.1, so cells routinely differ by ~25 rows and the
    balance every standard error in PREREG §2 assumes is not there. Permuted blocks hold every pair
    of cells within one row of each other at all times, and after each complete block the design is
    exactly balanced.

    The seed is an attribute so the caller can journal it; PREREG's manifest requires it
    ("assignment: cell drawn BEFORE generation from a shuffled fixed quota list, seed recorded").
    """

    def __init__(self, seed, cells=ALL_CELLS):
        self.seed = seed
        self.cells = tuple(cells)
        self.n_drawn = 0
        self._rng = random.Random(seed)
        self._block = []

    def next(self):
        if not self._block:
            self._block = list(self.cells)
            self._rng.shuffle(self._block)
        self.n_drawn += 1
        return self._block.pop()


# ------------------------------------------------------------------------------------- compose

#: THE ORDERED LAYER-B STAGE RULE, REINSTATED AS AN OPTION (factor S), OFF BY DEFAULT.
#:
#: WHAT WAS ACTUALLY MEASURED, and the only two numbers there are: Mann-Whitney U=327, p=0.72 on the
#: first 50 rows (`HARNESS_SOP.md`) and U=936, p=0.6353 at n=84. `free` median sharpe 0.020 vs
#: `ordered` -0.010. **Both are NULLS.** They license "no advantage detected at this n" and nothing
#: stronger; PREREG §2.3 puts the minimum detectable effect at n=84 well above the observed gap, and
#: `wilcoxon-is-not-a-mean-test` applies -- MW tested DOMINANCE, not the median it is quoted beside.
#: The rule was then DELETED outright, which turned "not shown to help" into "cannot be measured
#: again" and left PREREG §4.2's S branch ("S is REVERTED and the ordered-stage rule is reinstated")
#: with nothing to reinstate. It is an OPTION here so it is re-testable.
#:
#: WHAT THIS MAP IS, HONESTLY. `tools/layered_alpha.py` is untracked, no backup exists, and the
#: `__pycache__` copy is current, so the deleted `B_STAGES` could not be recovered. Recoverable from
#: the written record: the stage ORDER (`repair -> contextualise -> extract -> smooth`, quoted in
#: this module before the deletion) and four members of one stage -- `OPERATOR_AUDIT_P1R1.md` records
#: `last_diff_value`, `ts_delta`, `ts_av_diff` and `ts_quantile` in `B_STAGES["extract"]`. Everything
#: else below is RECONSTRUCTED from each operator's own platform description, not recovered.
#:
#: AND IT IS DEMONSTRABLY NOT THE SAME RULE. The deleted rule forbade 16.5% of chain links. Measured
#: over 2,000 draws of the free composer, this map forbids **38.1%** -- more than twice as many. So
#: the S factor as shipped is a NEW ordered-stage rule that has never been tested, not a restoration
#: of the one that was not shown to help. Candidates for the gap, none distinguished by any
#: experiment and none selected: the original mapped only a subset of pool B and left the rest exempt
#: (`ts_quantile`, which never enters pool B, was listed in it, so the map was hand-written over a
#: list rather than over the pool); the original had fewer stages; the 16.5% was measured over a
#: different denominator. **MECHANISM: UNKNOWN.**
B_STAGES = {
    # fill gaps first -- the rule's EX-ANTE ground was that filling gaps AFTER differencing across
    # them repairs nothing. (`OPERATOR_AUDIT_P1R1.md`: "its stage rule puts repair before extract".)
    # `group_extra` admitted with the 85-operator file: "Replaces NaN values by their corresponding
    # group means" -- gap filling, so it is repair by the same reading as the two below. EX-ANTE.
    "repair": ("ts_backfill", "group_backfill", "group_extra"),
    # place a value against its peers or its own history
    "contextualise": ("ts_zscore", "ts_rank", "ts_scale", "group_zscore", "group_rank",
                      "group_scale", "group_neutralize"),
    # turn a level into a difference, an event or a count. The first three are RECORDED members of
    # the deleted map; the rest are reconstructed.
    # The last three are admitted with the 85-operator file. All three are literally `x` minus a
    # reference computed from x's own window -- `x - ts_min(x,d)`, `x - f*(ts_min+ts_max)`,
    # `(ts_min+ts_max) - f*x` -- which is the definition of this stage. EX-ANTE, from the platform's
    # own definition strings, not from any outcome.
    "extract": ("ts_delta", "ts_av_diff", "last_diff_value", "ts_delay", "ts_arg_min", "ts_arg_max",
                "days_from_last_change", "ts_count_nans",
                "ts_min_diff", "ts_min_max_diff", "ts_min_max_cps"),
    # aggregate over time
    # The last three are admitted with the 85-operator file: an entropy over the past d days, a
    # moment over the past d days, and a tuned decay -- each aggregates a window into one number.
    # EX-ANTE. `ts_target_tvr_decay` also touches turnover directly, which is the one lever S2 of
    # BACKBONE_V2 names; that is a reason to WATCH it, not a reason to place it elsewhere.
    "smooth": ("ts_mean", "ts_sum", "ts_decay_linear", "ts_std_dev", "ts_product", "hump",
               "ts_entropy", "ts_skewness", "ts_target_tvr_decay"),
}

#: operator name -> its index in the stage order. An operator absent from the map is EXEMPT from the
#: rule rather than forbidden by it; nothing in pool B is absent today.
_STAGE_OF = {name: i for i, stage in enumerate(("repair", "contextualise", "extract", "smooth"))
             for name in B_STAGES[stage]}

#: The U factor's two levels, kept as strings because the baseline journal and `layered_report.py`
#: read `meta['arm']`. `units` applies the unit model; `control` reproduces the composer that
#: produced the 86-row corpus. Assigned PER ALPHA inside one batch, so the comparison is not
#: confounded by time of day, market regime or quota state -- which a before/after across two runs
#: would be. U=1 is `units`.
ARMS = ("units", "control")

#: Operators that return a COUNT or an INDEX rather than a level. Stacking two of them was a
#: measured source of degenerate alphas (see the chain rule in `compose`).
_COUNTERS = {"ts_count_nans", "days_from_last_change", "ts_arg_min", "ts_arg_max", "ts_step"}


def _apply(op, inner, rng):
    """Render one operator call around `inner`, supplying only parameters it actually requires.

    `log` and `sqrt` are DOMAIN-GUARDED. A raw signal goes negative, and `log` of a non-positive
    number is undefined -- one journalled degenerate alpha was `log(ts_delta(industry_reit_flag,...))`
    on a binary flag whose differences are mostly zero. Emitting `log((abs(x) + 1))` and
    `sqrt(abs(x))` keeps the shape the operator provides without handing it an input it cannot take.
    """
    if op["name"] == "log":
        return "log((abs(%s) + 1))" % inner
    if op["name"] == "sqrt":
        return "sqrt(abs(%s))" % inner
    args = [inner]
    for r in op["required"]:
        if r == "d":
            args.append(str(rng.choice(WINDOWS)))
        elif r == "group":
            args.append(rng.choice(GROUPS))
        elif r == "y":
            args.append(str(round(rng.uniform(0.2, 2.0), 2)))
    return "%s(%s)" % (op["name"], ", ".join(args))


def _weighted_choice(pool, weights, rng):
    """One leaf, drawn proportional to `weights`. Falls back to uniform if the weights are unusable
    -- a zero-sum weight vector must not silently make one entry certain."""
    total = sum(weights)
    if total <= 0:
        return rng.choice(pool)
    x = rng.random() * total
    acc = 0.0
    for item, w in zip(pool, weights):
        acc += w
        if x <= acc:
            return item
    return pool[-1]


def _compose_ab(pool_a, pool_b, pool_c, rng, cell, combo_min, combo_max, max_leaves,
                weights=None):
    """The layer A/B expression for one cell. Returns (formula, leg_meta, n_legs, truncated)."""
    arm = "units" if cell.U else "control"
    n_legs = rng.randint(LEGS_MIN, LEGS_MAX)
    per_leg = max(1, min(combo_max, max_leaves // n_legs))
    truncated = per_leg < combo_max

    outers = [o for o in pool_a if o["name"] in A_OUTER]
    shapers = [o for o in pool_a if o["name"] not in A_OUTER]

    def unit_ok(cands, cls):
        """THE COMPOSER RULE: an operator that demands `Unit[]` may only be applied to an expression
        the unit model calls stripped. Applied by CONSTRUCTION at the point of choice, so no draw is
        rejected and no formula has to be repaired afterwards."""
        if arm != "units" or cls == UNITLESS:
            return cands
        return [o for o in cands if o["name"] not in DEMANDS_UNITLESS]

    def stage_ok(cands, prev):
        """FACTOR S: a chain link may not step backwards through repair -> contextualise -> extract
        -> smooth. Applied at the point of choice, like the unit rule, so no draw is rejected and the
        cell's realised count equals its assigned count (PREREG §3.3)."""
        if not cell.stage_ordered or prev is None:
            return cands
        lo = _STAGE_OF[prev]
        return [o for o in cands if _STAGE_OF.get(o["name"], lo) >= lo]

    legs, leg_meta = [], []
    for _ in range(n_legs):
        depth = rng.randint(combo_min, per_leg)
        # FACTOR W -- DRAW LAYER C BY ITS FREQUENCY IN THE CLEAN CORPUS, not uniformly.
        #
        # Measured, and it is why a uniform vocabulary swap is worthless: the 6,818 alphas that
        # cleared LOW_SHARPE without failing CONCENTRATED_WEIGHT contain only FIVE distinct ratios,
        # and `close/open` is in ~86% of them. `rng.choice` makes the pool file the distribution, so
        # swapping 73,258 leaves for 3,094 leaves a carrier at ONE entry either way -- carrier rate
        # 0.002 before and 0.002 after. Weighted, the same pool gives 0.574 against the clean
        # corpus's 0.863.
        #
        # W=1 DELIBERATELY BAKES A POST-HOC REGULARITY IN AS A PRIOR. Frequency there may be a
        # record of which generator ran most, not of what works. That is exactly why it is an ARM
        # and not a default: the batch measures whether the prior pays.
        if getattr(cell, "W", 0) and weights is not None:
            leaf = _weighted_choice(pool_c, weights, rng)
        else:
            leaf = rng.choice(pool_c)
        expr = leaf["expr"]
        chain = []
        prev = None
        cls = UNITFUL                     # a leaf's unit is not in the metadata -- conservative
        for _ in range(depth):
            # NO OPERATOR IMMEDIATELY REPEATED, AND NO COUNTER ON A COUNTER. Measured: 11% of
            # terminal rows came back with `longCount=0, turnover=0` -- a simulation spent for no
            # information at all -- and the journalled formulas name the cause. One was
            # `days_from_last_change(days_from_last_change(x))`: the inner call returns a day count
            # that increments every day, so "days since it last changed" is a constant. `_COUNTERS`
            # return integers or indices, and stacking them destroys whatever variation was left.
            legal = unit_ok(pool_b, cls)
            staged = stage_ok(legal, prev)
            choices = [o for o in staged
                       if o["name"] != prev
                       and not (o["name"] in _COUNTERS and prev in _COUNTERS)]
            # The fallback stays INSIDE the unit-legal set, and inside the stage-legal set where one
            # exists. A fallback to the whole pool would be a silent hole in the rule, and a hole
            # that only opens on rare draws is the worst kind.
            op = rng.choice(choices or staged or legal)
            expr = _apply(op, expr, rng)
            if op["name"] in STRIPS:
                cls = UNITLESS
            chain.append(op["name"])
            prev = op["name"]

        # An optional shaper INSIDE the leg, never outermost.
        shaped = None
        cands = unit_ok(shapers, cls)
        if cands and rng.random() < 0.35:
            sh = rng.choice(cands)
            expr = _apply(sh, expr, rng)
            if sh["name"] in STRIPS:
                cls = UNITLESS
            shaped = sh["name"]

        # The legs are joined with `+`, which demands `Unit[]`, so the leg must END unitless. Any of
        # the six may sit outermost once the chain below has stripped; only the four strippers may
        # when it has not.
        pick = outers if (arm != "units" or cls == UNITLESS) else \
            [o for o in outers if o["name"] in A_OUTER_STRIPPING]
        outer = rng.choice(pick or outers)
        expr = _apply(outer, expr, rng)
        w = round(rng.uniform(0.2, 1.0), 2)
        if w != 1.0:
            expr = "(%s * %s)" % (expr, w)
        legs.append(expr)
        leg_meta.append({"outer": outer["name"], "inner": chain, "leaf": leaf["expr"],
                         "leaf_kind": leaf["kind"], "weight": w, "why": leaf["why"],
                         "shaper": shaped})

    formula = legs[0] if len(legs) == 1 else "(%s)" % " + ".join(legs)

    # FACTOR E -- ONE NORMALISER OVER THE WHOLE ENSEMBLE.
    #
    # Measured, and it is the sharpest structural difference anyone has found between our grammar
    # and the corpus that works: **83.3% of clean historical alphas wrap the joined ensemble in a
    # single outer normaliser; 0 of 132 of ours do**, because this line ends with `" + ".join(legs)`
    # and nothing follows it. No change to any POOL can produce it -- it is this one line.
    #
    # WHY IT MIGHT MATTER, and it is a hypothesis not a finding: 64.1% of our rows fail
    # CONCENTRATED_WEIGHT against 7.4% historically, and per-leg normalisation bounds each leg's
    # VALUES while leaving the summed book's WEIGHTS unbounded. A normaliser over the sum bounds the
    # thing the check actually measures. NOT ESTABLISHED -- three other candidates fit the same gap
    # (fewer legs, a dense carrier, the unmeasured IS window) and the round-3 analysis could not
    # separate them. MECHANISM: UNKNOWN.
    if getattr(cell, "E", 0) and len(legs) > 1:
        # A_OUTER_STRIPPING, not A_OUTER: `winsorize` clips and `normalize` on its defaults only
        # subtracts the mean, so neither strips the unit -- measured on two live rows where
        # every leg already ended in one of them and the platform still warned.
        formula = "%s(%s)" % (rng.choice(sorted(A_OUTER_STRIPPING)), formula)
    return formula, leg_meta, n_legs, truncated


def load_gate_pool(pooldir=None):
    """The layer-C conditions factor C draws from (`state/layered/pool_c_gate.json`), as written by
    `tools/layer_c.py --build`.

    FAILS CLOSED ON A STALE ARTIFACT, and this is not hypothetical: measured 2026-08-13, the shipped
    `pool_c_gate.json` (107 entries, 16:25) predates `tools/layer_c.py` (178 entries, 18:56) and is
    missing the `family`, `scope` and `unverified` keys the current `render_gate` reads, so every
    C=on draw raised `KeyError: 'family'`. The required key set is taken from a freshly built pool
    rather than restated here, so this check cannot drift from layer C's own contract.
    """
    pool = json.loads((pathlib.Path(pooldir or POOLDIR) / GATE_POOL_FILE).read_text())
    want = set(_render_gate().build_pool()[0])
    missing = want - set(pool[0] if pool else {})
    if missing:
        raise ValueError("%s is stale: entries are missing %s, which tools/layer_c.py's render_gate "
                         "reads. Rebuild it with `python3 tools/layer_c.py --build`."
                         % (GATE_POOL_FILE, sorted(missing)))
    return pool


def _render_gate():
    """`layer_c.render_gate`, imported rather than reimplemented -- the gate's arity and infix rules
    have exactly one copy, the same way `layer_c` imports `_params` from here."""
    d = str(pathlib.Path(__file__).resolve().parent)
    if d not in sys.path:
        sys.path.insert(0, d)
    import layer_c
    return layer_c


def _gate(expr, leaf, gate_pool, rng, make_second):
    """FACTOR C: wrap a composed alpha in one layer-C gate. Returns (formula, gate_meta, second).

    Every mode `layer_c.MODES` documents stays reachable. Two mechanics are handled HERE rather than
    left to the caller, because both would otherwise drop a draw, and PREREG §3.3 is explicit that a
    treatment which sets its own sample size voids §2:

      * `mode="exit"` -- `render_gate` REFUSES an exit condition identical to the trigger (per the
        docs z is evaluated first, so the alpha would be closed on exactly the days it fires;
        `INTEGRATION_P1R1.md` L2 hit it on 1 of 400 draws). The exit entry is therefore drawn from
        the conditions whose `cond` string differs, which cannot raise. Both entries are rendered
        against the same leaf, so equal `cond` strings and equal rendered conditions coincide.
      * `mode="pick"` -- `if_else(cond, expr, expr2)` needs a second expression; `make_second()` is
        called for a second independent layer A/B draw from the same cell, and ONLY for this mode, so
        the other three modes cost exactly what they did before.

    Every condition carrying `{leaf}` is substituted with the FIRST leg's layer-D leaf, and that leaf
    is recorded. NOT ESTABLISHED that a multi-leg alpha has one driver: with n_legs>1 the gate names
    one leg's leaf and the `why` string's "the layer-D field this alpha is built on" is then only
    true of that leg. Recorded, not corrected.
    """
    layer_c = _render_gate()
    entry = rng.choice(gate_pool)
    mode = rng.choice(layer_c.MODES)
    kw = {"leaf": leaf}
    second = None
    if mode == "exit":
        others = [e for e in gate_pool if e["cond"] != entry["cond"]]
        kw["exit_entry"] = rng.choice(others)
    if mode == "pick":
        second = make_second()
        kw["expr2"] = second[0]
    formula, meta = layer_c.render_gate(entry, expr, rng, mode=mode, **kw)
    meta["leaf"] = leaf
    return formula, meta, second


def compose(pool_a, pool_b, pool_c, rng, *, combo_min=COMBO_MIN, combo_max=COMBO_MAX,
            max_leaves=MAX_LEAVES, arm=None, cell=None, assigner=None, pool_c_kept=None,
            gate_pool=None):
    """One random alpha for one 2^4 cell. Returns (formula, meta).

    `meta` records every draw AND the cell, so any journalled row can be assigned to its arm on all
    four factors without re-deriving anything.

    HOW THE CELL IS OBTAINED, in order:
      `cell=`      an explicit Cell (tests, or a caller doing its own assignment)
      `assigner=`  a `CellAssigner` -- the pre-registered path, drawn BEFORE generation (§3.3)
      neither      LEGACY DEFAULT: D=C=S=off and U drawn as before. This reproduces the composer that
                   produced the round-1 corpus exactly, and is recorded as `cell_source` =
                   "legacy-default" on every row it produces. It is NOT the pre-registered
                   assignment: a round run this way journals only two distinct cells, which is
                   visible in the report rather than silent.
    """
    if cell is not None and assigner is not None:
        raise ValueError("pass cell= or assigner=, not both")
    if cell is not None:
        cell_source = "explicit"
        if arm is not None and (arm == "units") != bool(cell.U):
            raise ValueError("arm=%r contradicts cell.U=%r" % (arm, cell.U))
    elif assigner is not None:
        # Checked BEFORE `next()`: a raise after the draw would consume a cell out of the block and
        # leave the quota list permanently short by one.
        if arm is not None:
            raise ValueError("arm= cannot be forced while an assigner is drawing U")
        cell_source = "assigner"
        cell = assigner.next()
    else:
        cell_source = "legacy-default"
        # S=1 is the `free` composer, i.e. the ordered-stage rule OFF -- see Cell's polarity note.
        cell = Cell(D=False, C=False, U=((arm or rng.choice(ARMS)) == "units"), S=True,
                    E=False, W=False)

    # FAIL CLOSED. A D=on row composed from the unscreened pool, or a C=on row with no gate, journals
    # as a complete row for an experiment in which that factor never varied.
    leaves, screen_meta = pool_c, None
    if cell.D:
        if not pool_c_kept:
            raise ValueError("cell %s has D=on: pass pool_c_kept= (see screen_pool_c). Composing "
                             "D=on from the unscreened pool would make D unassignable." % cell.id)
        leaves = pool_c_kept
        screen_meta = {"n_pool": len(pool_c), "n_kept": len(pool_c_kept)}
    if cell.C and not gate_pool:
        raise ValueError("cell %s has C=on: pass gate_pool= (see load_gate_pool)." % cell.id)

    # Weights come from the pool's own `n_clean` if it carries one (pool_c2 does; the original
    # pool_c does not). A pool with no frequency column yields None, and factor W then degrades to
    # the uniform draw rather than to a silent uniform-pretending-to-be-weighted.
    leaf_weights = None
    if leaves and isinstance(leaves[0], dict) and "n_clean" in leaves[0]:
        leaf_weights = [float(x.get("n_clean") or 0) for x in leaves]
        if sum(leaf_weights) <= 0:
            leaf_weights = None

    formula, leg_meta, n_legs, truncated = _compose_ab(
        pool_a, pool_b, leaves, rng, cell, combo_min, combo_max, max_leaves,
        weights=leaf_weights)

    # `factors` and `cell` are BOTH written, in the exact shapes `layered_report.cell_of` reads (a
    # {D,C,U,S} dict first, a "D1C0U1S1" string second). `arm` is kept because the round-1 corpus and
    # `LEGACY_ARM` are keyed on it; the report prefers `factors`, so they cannot disagree.
    #
    # `carrier` is taken from the UNGATED expression on purpose. The gate conditions contain `close`
    # and would flip the label on any alpha that already held `open`, which would make a C=on/C=off
    # carrier comparison measure the gate rather than the alpha.
    meta = {
        "arm": "units" if cell.U else "control",
        "factors": cell.as_dict(), "cell": cell.id, "cell_source": cell_source,
        "n_legs": n_legs, "depth_cap_applied": truncated, "legs": leg_meta,
        "carrier": carrier_present(formula),
        "n_leaves": len(leg_meta),
        "layer_d_screen": screen_meta,
        "stage_ordered": cell.stage_ordered,
        "gate": None,
    }

    if cell.C:
        def make_second():
            f2, legs2, n2, _t2 = _compose_ab(
                pool_a, pool_b, leaves, rng, cell, combo_min, combo_max, max_leaves)
            return f2, legs2, n2

        # `gate` carries `render_gate`'s OWN meta. `INTEGRATION_P1R1.md` S2 measured that this dict
        # had no journal path and no reader -- the class that once made 2,639 rows unanalysable --
        # so it is nested here, where `layered_sim._child_row` journals `meta` wholesale.
        formula, gate_meta, second = _gate(formula, leg_meta[0]["leaf"], gate_pool, rng, make_second)
        meta["gate"] = gate_meta
        if second is not None:
            meta["legs_alt"], meta["n_legs_alt"] = second[1], second[2]
            meta["n_leaves"] += len(second[1])

    return formula, meta


def carrier_present(formula):
    """Does this alpha carry the close/open carrier every historical gem carries?

    Labelled, never enforced. The operator chose full randomness; this makes the resulting yield
    split a measurement rather than an argument.
    """
    return ("close" in formula and "open" in formula)


# ---------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", action="store_true", help="write the three pools to state/layered/")
    ap.add_argument("--sample", type=int, default=5, help="print this many composed alphas")
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    ops = load_operators()
    a, b, dropped = split_layers(ops)
    fields = load_fields()
    rng = random.Random(args.seed)
    c = build_pool_c(fields, rng=rng)

    print("pool A (outer)  %3d  %s" % (len(a), ", ".join(o["name"] for o in a)))
    print("pool B (inner)  %3d  %s" % (len(b), ", ".join(o["name"] for o in b)))
    print("pool C (leaves) %3d  (%d raw fields + %d economic ratios) from %d MATRIX fields"
          % (len(c), sum(1 for x in c if x["kind"] == "field"),
             sum(1 for x in c if x["kind"] == "ratio"), len(fields)))
    print("dropped         %3d" % len(dropped))
    for name, why in dropped:
        print("    %-20s %s" % (name, why))

    if args.build:
        POOLDIR.mkdir(parents=True, exist_ok=True)
        (POOLDIR / "pool_a.json").write_text(json.dumps(a, indent=2))
        (POOLDIR / "pool_b.json").write_text(json.dumps(b, indent=2))
        (POOLDIR / "pool_c.json").write_text(json.dumps(c, indent=2))
        print("wrote %s/{pool_a,pool_b,pool_c}.json" % POOLDIR)

    print("\n--- %d sample draws ---" % args.sample)
    for i in range(args.sample):
        f, m = compose(a, b, c, rng)
        print("\n[%d] legs=%d carrier=%s" % (i + 1, m["n_legs"], m["carrier"]))
        print("    %s" % (f if len(f) < 400 else f[:400] + " ..."))
        print("    leaf: %s  (%s)" % (m["legs"][0]["leaf"], m["legs"][0]["why"][:90]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
