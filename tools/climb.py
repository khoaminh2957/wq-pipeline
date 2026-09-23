"""Closed-loop alpha builder: 300 sims a round, keep the best, grow around it, reset when it stalls.

OPERATOR SPEC (Khoa, 2026-08-14), followed exactly:

  round 1     300 random alphas, each ONE function around ONE field or ratio
  round n>1   300 random growths of the current baseline, each either
                  WRAP     op(baseline)
                  COMBINE  op(baseline <+-*/> op(new_field))
  after each  argmax FITNESS becomes the new baseline
  stop        when the round stops improving fitness by much
  cycle end   gems written out; no gems -> reset to round 1, fully random again

THE OBJECTIVE IS SUB-UNIVERSE SHARPE FROM 2026-08-15 (Khoa). Fitness was the placeholder before
that, and the swap was one flag exactly as designed. `LOW_SUB_UNIVERSE_SHARPE` is the ratio gate the
council named the binding constraint -- limit = 0.433 x the alpha's own sharpe -- so optimising the
sub-universe sharpe directly aims the climb at the thing that actually refuses. He chose the RAW
value over the ratio; the raw value cannot blow up, while the ratio runs -84 to +82 across the
corpus purely from a denominator passing through zero.

FITNESS IS NO LONGER THE OBJECTIVE, and this paragraph used to say it was -- a stale comment that
survived the swap described just above and contradicted the code two hundred lines below it. The
default is `sub_sharpe` (`layered_sim.py --objective`). Fitness now appears in exactly one place:
`screened()`, as SCREEN_FITNESS = 1.0, one of the three conditions for calling a row a gem. It does
not rank baselines and it does not set the phase benchmark.

Nothing here assumes sub_sharpe is the right answer either. `--objective` takes any scraped metric,
so the same loop can be re-run on sharpe, on fitness, on a composite, and which metric finds gems
fastest is a later experiment rather than a rewrite. MECHANISM: UNKNOWN.

THE ONE THING I FLAGGED AND KHOA RULED ON. Taking the argmax of 300 selects partly on noise: the
maximum of N draws is biased upward, so round n+1 explores around a point that is partly luck and
part of its "improvement" is regression to the mean. Khoa chose plain argmax, so plain argmax is
what runs. What this file does instead of arguing is MEASURE the bias -- `state/climb/state.json`
records, for every round, the baseline's fitness as measured when it was chosen and again when it is
re-measured as part of the next round's candidates, and `--report` prints the drift. If the drift is
large the number will say so.

MEASUREMENT IS TIERED, to spend as few API calls as possible (Khoa's requirement):

  tier 1   sharpe, fitness, turnover        <- from the ONE `GET /alphas/{id}` the scrape already
  tier 2   every other platform check          makes. Tiers 1 and 2 arrive in the SAME response, so
                                               tier 2 is free; the gating below costs nothing there.
  tier 3   ELIGIBLE for prod-corr and       <- SEPARATE endpoints, one call each, and the only real
           self-corr, which are separate         cost. Reached ONLY by an alpha that cleared tier 1's
           endpoints and must be MEASURED        screen and holds a PASS on every gate in
                                                 REJECT_CHECKS.

**TIER 3 IS NOT A GEM AND MUST NEVER BE CALLED ONE.** It is the point where the correlation probe
becomes worth paying for. On the live climb, 569 rows reached tier 3 and every one of them carried
`PROD_CORRELATION`, `SELF_CORRELATION`, `DATA_DIVERSITY` and `REGULAR_SUBMISSION` as **PENDING** --
the platform had not computed them. Announcing those as gems is exactly the error the council named:
"the four correlation gates are PENDING on 69,262/69,262 rows, so every zero-fail number ever
computed from this file scores them as passes."

  tier 4   GEM                             <- prod-corr and self-corr MEASURED and PASSED. Only a
                                              tier-4 row goes in the gem ledger.

**IT NEVER SUBMITS.** A gem is written to the ledger and announced; the irreversible POST is Khoa's
decision alone, and a 403 spends an alpha forever.
"""

import argparse
import collections
import json
import os
import re
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layered_alpha as LA  # noqa: E402

STATE = ROOT / "state/climb/state.json"
LEDGER = ROOT / "state/climb/gems.jsonl"

#: Khoa's screen, and the only tier that costs nothing to evaluate.
SCREEN_SHARPE, SCREEN_FITNESS = 1.58, 1.0
SCREEN_TURNOVER = (0.01, 0.7)

#: Arithmetic is written infix -- `add`/`subtract`/`multiply`/`divide` are never called. Calling
#: them with one operand produced 12,643 arity violations in an earlier generation.
INFIX_OPS = ("+", "-", "*", "/")

#: Operators the platform's UNITS check requires a DIMENSIONLESS input for.
#:
#: Measured over 28,380 journal rows: 1,085 UNITS warnings, and 978 of them (90%) say
#: `expected "Unit[]"` -- the operator wanted a plain number and got a field carrying a unit like
#: CSPrice or CSShare. `power(depreciation_expense, 1.02)` is the shape: raising a PRICE to the
#: power 1.02 has no meaning, and the platform says so.
#:
#: By operator: add 383, subtract 194, sqrt 136, hump 113, ts_product 95, power 87,
#: group_backfill 77. So 53% is the infix combine putting two differently-united things together,
#: and ~40% is a unary operator applied straight to a raw field.
#: CLOSED BY MEASUREMENT, 2026-08-18. Parsing all 446 unit warnings in the journal for the operator
#: each one names gives the COMPLETE set the platform demands `Unit[]` from, rather than the set
#: someone remembered:
#:
#:     subtract idx1 93 | add idx1 78 | sqrt 56 | hump 49 | ts_product 47 | power 38
#:     group_backfill 35
#:
#: `add` and `subtract` are the infix case, handled by UNIT_MATCHING_INFIX. Everything else is here.
#: `group_backfill` was the one omission -- it survived the first patch, was caught by a live test
#: on the new moves, and is the last operator on that list that was not already covered.
#:
#: A further 68 warnings expect a NON-empty unit (add idx1 53, subtract idx1 15): two operands that
#: both carry units, but DIFFERENT ones. Ranking both sides fixes those too, since both become
#: Unit[], so no separate rule is needed.
UNIT_FREE_OPS = frozenset((
    "sqrt", "power", "hump", "ts_product", "log", "signed_power", "exp", "inverse",
    "s_log_1p", "sigmoid", "tanh", "arc_tan", "arc_sin", "arc_cos", "group_backfill",
))

#: Infix operators that require BOTH sides to share a unit. `*` and `/` combine units happily
#: (price x share is a valid unit); `+` and `-` do not.
UNIT_MATCHING_INFIX = ("+", "-")

#: THE PLATFORM'S HARD EXPRESSION LIMIT, found the expensive way on 2026-08-30: a depth-5 growth
#: round drew 300 candidates and most exceeded it -- "Expression with 65 operators exceeds limit
#: of 64" -- so ~260 POSTs each burned a slot and a poll cycle to learn a fact we could count for
#: free, the round crawled for 3h55m and landed 40 rows. HOW THE PLATFORM COUNTS, calibrated on
#: its own verdicts (not guessed): function calls PLUS infix arithmetic. The errored row: 57
#: calls + 8 infix = 65 exactly; the longest COMPLETE rows sit at 54-60. Guard at 62 for margin,
#: overridable for recalibration if a future verdict disagrees.
MAX_FORMULA_OPS = int(os.environ.get("WQ_MAX_FORMULA_OPS") or 62)


def op_count(expr):
    """Operators as THE PLATFORM counts them: function calls + infix arithmetic."""
    return len(re.findall(r"[a-z_][a-z0-9_]*\(", expr)) + len(re.findall(r" [\+\-\*/] ", expr))

#: What we wrap an expression in to strip its unit. `rank` is cross-sectional, dimensionless by
#: construction, and already the most common normaliser in this corpus -- so this adds no new
#: vocabulary to the search, it only fixes WHERE the vocabulary is applied.
UNIT_STRIP = "rank"


def unit_safe(expr, op_name=None, infix=None):
    """Make `expr` dimensionless when the operator about to consume it demands that.

    Khoa, 2026-08-18: fix the UNITS violations without changing much. This is the whole fix -- one
    wrap at the point of composition, no change to the operator pool, the field pool, or the search
    grammar. An expression already wrapped in the stripper is left alone rather than nested twice.
    """
    need = (op_name in UNIT_FREE_OPS) or (infix in UNIT_MATCHING_INFIX)
    if not need:
        return expr
    if expr.startswith(UNIT_STRIP + "("):
        return expr
    return "%s(%s)" % (UNIT_STRIP, expr)

#: CHECKS THAT DISQUALIFY A BASELINE, in the order Khoa added them (2026-08-14).
#:
#: CONCENTRATED_WEIGHT came first: plain argmax had chosen sharpe 1.82 / fitness 1.80 on a book of
#: FOUR names, and every later round would have grown on top of it.
#:
#: LOW_SUB_UNIVERSE_SHARPE and IS_LADDER_SHARPE were added once the climb reached them: all twenty
#: of the first screen-passers failed exactly these two and nothing else. LOW_SUB_UNIVERSE_SHARPE is
#: the RATIO gate -- limit = k * the alpha's own sharpe -- which the council named the binding
#: constraint precisely because raising sharpe raises the bar by the same factor.
#:
#: What the two cost, measured on 772 in-band rows BEFORE they were added:
#:     CONCENTRATED_WEIGHT alone                 590 survive, best fitness 1.270
#:     + LOW_SUB_UNIVERSE_SHARPE                 261 survive, best fitness 1.050
#:     + IS_LADDER_SHARPE                        178 survive, best fitness 1.050
#: So the climb keeps 178 candidates and gives up 0.22 of fitness to stop building on alphas that
#: cannot clear the gates. That trade is Khoa's call and the numbers are here so it can be revisited.
#: Khoa, 2026-08-17: CLUSTER_TEST, UNITS and LOW_2Y_SHARPE join the baseline filter, not just the
#: probe filter. Measured before applying, over 27,180 journal rows carrying an alpha id:
#:
#:     baseline-eligible now                        6,561  (24.1%)  ~48 of a 200-candidate round
#:     + CLUSTER_TEST / UNITS / LOW_2Y_SHARPE       5,453  (20.1%)  ~40 of 200
#:
#: Safe: the climb still has ~40 candidates a round to pick from, so it cannot be starved of a
#: baseline. What is NOT safe, and is deliberately kept out of this tuple, is also demanding that
#: every gate be SCORED -- that leaves 0 of 27,180 and the climb stalls on its next round. The
#: scored requirement stays in `tier()`, where it governs probe eligibility only.
#: KHOA CUT THIS TO THREE, 2026-08-18. CLUSTER_TEST, UNITS and LOW_2Y_SHARPE come out: the unit
#: generator fix dropped the UNITS rate from 10.92% to 1.88%, so screening on it at BASELINE-SELECT
#: time now costs more candidates than it saves. These three remain because each one, on its own,
#: makes a baseline unfit to climb FROM: a 4-name book, the ratio gate that binds, and the ladder.
#: A gem still has to pass EVERYTHING -- this list governs what we are willing to stand on, not what
#: we are willing to submit.
REJECT_CHECKS = ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE")

#: THE SEED ROUND FILTERS ON LESS. Khoa, 2026-08-18: "bo loc low subuniverse sharpe cho vong dau".
#:
#: Measured on 6,331 real depth-1 seeds, counting one gate at a time over the rows already inside
#: the turnover band:
#:
#:     LOW_SUB_UNIVERSE_SHARPE  blocks 1,793 (46.6%)
#:     CONCENTRATED_WEIGHT      blocks 1,388 (36.1%)
#:     IS_LADDER_SHARPE         blocks     0 ( 0.0%)   <- never SCORED on a depth-1 row
#:
#: The ratio gate is the heaviest thing standing between a fresh cycle and its first baseline, and
#: a seed is `op(field)` -- one operator on one field. Refusing it for a sub-universe sharpe judges
#: a starting point by a bar built for a finished alpha. It applies again from the first growth
#: round, where the alpha is something that can reasonably be held to it.
#:
#: CONCENTRATED_WEIGHT stays: a 4-name book is not a starting point, it is a dead end that every
#: later round would inherit.
SEED_REJECT_CHECKS = tuple(g for g in REJECT_CHECKS if g != "LOW_SUB_UNIVERSE_SHARPE")

#: GATES WHERE A WARNING STILL DISQUALIFIES. Khoa, 2026-08-18: "cu concentrated weight la loai".
#:
#: Loosening WARNING earlier the same day re-opened the exact hole this gate was added to close.
#: The very first baseline chosen under the new rule was:
#:
#:     ts_delta(rsk88_mfm_ase1_ind_storage_warehousing, 20)
#:     fitness 27.58 | sharpe 7.73 | longCount 4 | shortCount 0
#:     CONCENTRATED_WEIGHT: WARNING (0.5)
#:
#: A book of FOUR names, all long, and every round of that cycle would have grown from it -- which
#: is word for word the case that put CONCENTRATED_WEIGHT in the list on 2026-08-14. The gate fired
#: correctly; what failed was treating its WARNING as acceptable.
#:
#: This is deliberately a SEPARATE list rather than a special case inside the loosening: a warning
#: means different things on different gates, and the ones where it means "the book is too small to
#: stand on" have to be named, not inferred.
HARD_CHECKS = ("CONCENTRATED_WEIGHT",)

#: EXTRA gates that must also be clean before an alpha is worth a correlation read.
#:
#: Khoa, 2026-08-17: "sau này chỉ cào corr khi có tất cả gate khác pass". The correlation endpoint
#: is the pipeline's binding constraint -- it throttles for reasons that are NOT our request rate
#: (measured: refused with the bucket at 56-59 of 60), so every read spent on an alpha that has
#: already failed something elsewhere is a read stolen from one that might have become a gem.
#:
#: Measured on the live queue, 74 distinct signals eligible for the probe:
#:
#:     CLUSTER_TEST     61 PASS / 13 adverse   <- discriminates
#:     UNITS             0 PASS /  4 adverse   <- discriminates
#:     LOW_2Y_SHARPE     0 PASS /  1 adverse   <- discriminates
#:
#: Adding these dropped 17 of 74 signals and saved 23% of the probe budget per round.
#:
#: EMPTY SINCE 2026-08-17: all three were promoted into REJECT_CHECKS above, so they now block a
#: baseline as well as a probe. The tuple stays because the probe/baseline distinction is real and
#: the next gate found this way belongs here first -- a gate is proven on the probe path, where a
#: mistake costs API calls, before it is trusted on the baseline path, where a mistake costs the
#: climb its baseline.
#:
#: THREE GATES ARE ADVERSE ON PROBE TARGETS AND MUST NEVER JOIN EITHER LIST:
#: MATCHES_THEMES, MATCHES_COMPETITION and OSMOSIS_ALLOCATION are adverse on 74 of 74 -- adding any
#: one empties the queue completely. A gate with zero variance cannot discriminate anything; that
#: is the same trap as "the carrier is necessary", which held in 11,731 of 11,731 rows. They stay
#: informational and are recorded on the gem row instead.
PROBE_EXTRA_CHECKS = ()

#: A round that fails to beat the standing baseline by this fraction counts as no progress.
#: DEFAULT IS A GUESS, not a measurement -- no experiment here has established what a real
#: improvement looks like round to round. It is a flag so the first real cycle can correct it.
#: THE RANKING OBJECTIVE. Khoa moved this back to fitness on 2026-08-18.
#: Fitness has a median of 0.09 and is NEGATIVE on 28% of rows, against 0.30 / 30.2%
#: for sub_sharpe -- which is why `gained()` below cannot use a bare multiplication.
OBJECTIVE = os.environ.get("WQ_OBJECTIVE") or "fitness"

MIN_GAIN = 0.05
STALL_ROUNDS = 2


#: METRICS THAT ARE NOT ON THE ALPHA PAYLOAD. `sub_sharpe` is the sub-universe sharpe, and it lives
#: inside the LOW_SUB_UNIVERSE_SHARPE check as its `value` -- there is no top-level field for it. It
#: is available on 3,936 of 4,000 journalled rows.
#:
#: KHOA CHOSE THE RAW VALUE, not the ratio (2026-08-15). The gate itself is a ratio -- limit =
#: 0.433 x the alpha's own sharpe -- so a high raw value does not guarantee clearing it. What the
#: raw value avoids is the division: the ratio runs -84 to +82 across the corpus purely because the
#: denominator passes through zero, which is the same 0/0 trap that made me report a `subu 0.84`
#: yesterday that dissolved the moment a floor was put under the denominator.
DERIVED = {
    "sub_sharpe": lambda m: next(
        (c.get("value") for c in (m.get("checks") or [])
         if isinstance(c, dict) and c.get("name") == "LOW_SUB_UNIVERSE_SHARPE"
         and isinstance(c.get("value"), (int, float))), None),
}


def metric(row, name):
    """The objective's value for a row, whether it sits on the payload or inside the checks."""
    fn = DERIVED.get(name)
    if fn:
        return fn(row)
    return row.get(name)


def screened(m):
    s, f, t = m.get("sharpe"), m.get("fitness"), m.get("turnover")
    if not all(isinstance(x, (int, float)) for x in (s, f, t)):
        return False
    lo, hi = SCREEN_TURNOVER
    return s > SCREEN_SHARPE and f > SCREEN_FITNESS and lo < t < hi


def failing_checks(m):
    """Names of every check the platform scored FAIL. Only the dict-of-records shape is read: this
    project's journals carry `checks` in three shapes, including rows that list the checks which
    PASSED, and reading those naively inverts every conclusion."""
    ch = m.get("checks")
    if not isinstance(ch, list):
        return None                      # unknown, NOT "none" -- the caller must not treat it as a pass
    if ch and not all(isinstance(c, dict) for c in ch):
        # FAIL CLOSED. 614 rows at the head of `resim_results.jsonl` carry `checks` as a list of
        # BARE NAMES listing the checks that PASSED -- inverted polarity. Such a list contains no
        # FAIL record, so a naive scan returns [] and the alpha is promoted to tier 3 as if it were
        # clean. An unrecognised shape is unknown, never clean.
        return None
    return [c["name"] for c in ch
            if isinstance(c, dict) and c.get("name") and c.get("result") == "FAIL"]


def warned_checks(m):
    """Names of every check the platform scored WARNING. Same shape rules as `failing_checks`.

    **A WARNING IS NOT A PASS.** This project has already published a wrong number by treating it as
    one -- "7 of 7 failed CONCENTRATED_WEIGHT" was reported when literal PASS was 1 of 117. Here the
    same gap was about to be worse than a wrong number: of the 6 rows the first version of `tier`
    called GEMS, **all 6 carried a WARNING and 0 were clean**, including WARNING on IS_LADDER_SHARPE
    -- one of the gates Khoa had just named as disqualifying.
    """
    ch = m.get("checks")
    if not isinstance(ch, list):
        return None
    if ch and not all(isinstance(c, dict) for c in ch):
        return None
    return [c["name"] for c in ch
            if isinstance(c, dict) and c.get("name") and c.get("result") == "WARNING"]


def blocked_on(m, gates=None):
    """(adverse, unscored) for the named gates -- kept SEPARATE, and the separation is the point.

    An ADVERSE grade is FAIL or WARNING: the platform looked and did not pass it. **A WARNING IS NOT
    A PASS** -- this project once published "7 of 7 failed CONCENTRATED_WEIGHT" while literal PASS
    was 1 of 117, and the first version of `tier` here called 6 rows GEMS of which all 6 carried a
    WARNING and 0 were clean.

    UNSCORED is a different thing and must not be merged with it. `IS_LADDER_SHARPE` is scored on
    only 560 of 1,020 rows, and treating unscored as adverse leaves **0 survivors out of 1,020** --
    the climb would have no baseline at all and stall on its next round. So unscored is returned
    separately: counted, visible, and not disqualifying. Conflating the two is the same gate-PRESENCE
    error behind the council's false "carrier-free fails the ladder less".

    Returns (None, None) when the check set is unreadable, so "clean" and "unknown" stay distinct.
    """
    gates = REJECT_CHECKS if gates is None else gates
    ch = m.get("checks")
    if not isinstance(ch, list) or (ch and not all(isinstance(c, dict) for c in ch)):
        return None, None
    got = {c["name"]: c.get("result") for c in ch if isinstance(c, dict) and c.get("name")}
    adverse = [g for g in gates if got.get(g) in ("FAIL", "WARNING", "ERROR")]
    unscored = [g for g in gates if g not in got]
    return adverse, unscored


#: Gates the platform leaves PENDING until a correlation probe is paid for. A PENDING check is NOT
#: a pass, and treating it as one is how "zero-fail" numbers get manufactured.
CORR_GATES = ("PROD_CORRELATION", "SELF_CORRELATION")

#: THE CHECK AND THE VALUE ARE DIFFERENT SURFACES, and defining a gem by the check made tier 4
#: unreachable. `/alphas/{id}/correlations/prod` returned 0.664 for the standing best while its
#: `PROD_CORRELATION` check still read PENDING -- the platform computes that check at SUBMISSION
#: time, not on demand. So a gem is defined by the MEASURED value against its threshold.
#:
#: PROD 0.71 is this project's measured try/skip line (`exact-prod-corr-metric`: the metric is
#: `j["max"]` of the histogram payload). SELF 0.70 is an ASSUMPTION, not a measurement -- nothing
#: here has established the self-correlation cutoff, and the first six measured alphas all sit at
#: 0.18-0.25, far below any plausible line. Stated so it can be corrected rather than inherited.
#: THE CORRELATION ENDPOINT THROTTLES, AND NOBODY HERE KNOWS THE RULE. Observed 2026-08-14: six
#: alphas measured cleanly, then roughly forty probes later every request returns
#: `429 {"detail":"THROTTLED"}` with NO Retry-After header and no rate-limit headers at all. It kept
#: returning 429 after the simulation loop had stopped, so it is not contention with our own traffic.
#:
#: **MECHANISM: UNKNOWN, and deliberately left unknown.** `measure_backlog.py` records that this
#: exact symptom has already been explained wrongly twice in this repository -- first as "its own
#: small budget with a multi-day cooldown", then as "purely a pacing problem" -- both written
#: confidently, both wrong. A third confident story is worth less than nothing. What is established:
#: the body says THROTTLED, no duration is given, and backing off is the only response that has ever
#: worked. Anything past that needs an experiment nobody has run.
PROD_CORR_MAX = 0.71
SELF_CORR_MAX = 0.70
PROBE = ROOT / "state/climb/probe.jsonl"


def measured_corr(path=None):
    """{alpha: {"prod": float, "self": float}} from the probe log -- latest reading wins.

    A `200-empty` body is the platform STARTING the computation, not a result, and is skipped.
    """
    path = pathlib.Path(path or PROBE)
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="ignore").splitlines():
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        aid = r.get("alpha")
        if not aid:
            continue
        got = out.setdefault(aid, {})
        for kind in ("prod", "self"):
            if isinstance(r.get(kind), (int, float)):
                got[kind] = r[kind]
    return out


def tier(m, measured=None):
    """Which measurement tier this alpha earned. Tier 3 is where the correlation probe becomes
    worth paying for; tier 4 is a gem.

    `measured` is the probe log (see `measured_corr`). Without it nothing can reach tier 4, which is
    correct: an unmeasured correlation is not a passed one.

    TIER 3 NOW REQUIRES AN EXPLICIT PASS ON EVERY GATE IN `REJECT_CHECKS`, not merely the absence of
    a FAIL. Warnings on the informational checks (MATCHES_THEMES, MATCHES_COMPETITION,
    OSMOSIS_ALLOCATION) do NOT block -- whether any of those actually prevents a submission is
    MECHANISM: UNKNOWN here, so they are recorded on the gem row rather than used to reject.
    """
    if not screened(m):
        return 1
    fails = failing_checks(m)
    if fails is None or fails:
        return 2
    adverse, unscored = blocked_on(m)
    if adverse is None or adverse:
        return 2

    # ONLY PAY FOR A CORRELATION WHEN EVERYTHING ELSE IS ALREADY CLEAN.
    #
    # This used to discard `unscored` and check nothing beyond REJECT_CHECKS, so a read could be
    # spent on an alpha whose ladder was never graded, or which had already failed CLUSTER_TEST.
    # The correlation endpoint is the binding constraint on the whole pipeline and it refuses us
    # for reasons unrelated to our rate, so a wasted read is not merely wasteful -- it displaces
    # the one alpha that might have become a gem.
    #
    # The strictness applies to PROBE ELIGIBILITY ONLY, never to baseline selection. `pick()` keeps
    # the looser REJECT_CHECKS on purpose: treating unscored as adverse leaves 0 survivors of 1,020,
    # and a climb with no baseline stalls on its next round. Two different questions, two rules --
    # "good enough to grow from" is not "worth an irreplaceable API call".
    # "ALL GATES PASS" MEANS EVERY VERDICT IS A PASS -- NOT THAT EVERY GATE HAS A VERDICT.
    #
    # I conflated those this morning and it made tier 3 mathematically impossible. Measured over
    # 28,330 finished rows: UNITS is scored on 3.7% of them, LOW_2Y_SHARPE on 41.4%,
    # IS_LADDER_SHARPE on 57.4% -- and rows carrying ALL SIX verdicts: ZERO. So demanding a verdict
    # on each gate demanded something the platform never produces, and the probe queue went to nil
    # while the loop kept mining and could no longer turn anything into a gem.
    #
    # Khoa asked that a correlation only be spent when the other gates pass. A gate the platform
    # declined to grade has not failed, and treating silence as failure is the same error as the
    # zero-variance gates: it removes everything and discriminates nothing.
    #
    # `adverse` above already enforces the real rule -- any gate that WAS graded must not be
    # FAIL/WARNING/ERROR. Unscored is counted, visible on the row, and not disqualifying.
    _ = unscored
    extra_adverse, extra_unscored = blocked_on(m, PROBE_EXTRA_CHECKS)
    if extra_adverse:
        return 2
    corr = (measured or {}).get(m.get("alpha") or "", {})
    if "prod" not in corr or "self" not in corr:
        return 3                      # eligible for the probe, NOT a gem
    if corr["prod"] < PROD_CORR_MAX and corr["self"] < SELF_CORR_MAX:
        return 4                      # measured AND under both lines -- a gem
    return 2                          # measured and over a line


def leaf_weights(pool_c, policy=None):
    """One draw weight per leaf, prioritising the pyramid cells nearest to unlocking.

    Khoa, 2026-08-15: the open cells are to be PRIORITISED, not merely kept. A category one alpha
    short gets weight 1.0, two short 0.5, three short 0.33, and each category's total is shared
    among its leaves -- so Sentiment's 1,065 fields do not drown Insiders' 118 by sheer count.

    MECHANISM: UNKNOWN for whether nearest-to-unlocking is the right order. The EV argument is that
    one gem into a one-short cell buys an unlock outright, but nothing here has measured whether
    such a cell is easier or harder to fill than an empty one. Uniform weights if the gate is off.
    """
    import pool_gate as PGATE
    st = PGATE.state()
    return PGATE.draw_weights(pool_c, st, policy or PGATE.DEFAULT_POLICY)


# ------------------------------------------------------------------- the per-year book filter
#
# Khoa, 2026-08-15: a baseline must hold more than 1000 names EVERY YEAR. He asked for it before
# anyone had looked, and the first two alphas checked showed why:
#
#   mL516W9W (submitted 2026-08-14)   2014-2020: long 0, short 0, pnl 0.  SEVEN YEARS OF NOTHING.
#                                     2021: 901.  2022: 1211.  2023: 1267.
#   gJ8d1Goe (its lineage root)       identical shape, 8 of 10 years under 1000.
#
# So a sharpe of 3.61 and a fitness of 2.93 were computed over three trading years out of ten, and
# the climb had been optimising an alpha that does not trade for 70% of its own backtest. The
# scalar `longCount` on the alpha payload cannot see this -- it is one number for the whole run.
#
# MECHANISM: UNKNOWN for why the book is empty before 2021. The obvious candidate is a field whose
# history starts there, but no experiment here has separated that from a structure that only
# produces positions under conditions which first occur in 2021.
#
# COST. This is one extra API call per alpha, so it is applied ONLY at baseline selection, walking
# down the ranking until a candidate passes -- a handful of calls a round, not 300. That is also
# exactly what Khoa asked for: "bộ lọc vào alpha baseline".

#: FIELDS ALREADY SPENT. Khoa, 2026-08-15: "thêm 1 lớp lọc là bỏ các field nào đã được sử dụng".
#: This REVERSES his earlier ruling that a reset should re-randomise with nothing banned, and the
#: reason is on the record: cycles 5 through 11 kept rediscovering the same core and burning 330
#: simulations each to go nowhere.
#:
#: A field is spent once a cycle has ENDED on a baseline containing it -- not merely once it has
#: been drawn, or one round of 100 would ban a third of the pool. `state/banned_fields.json` is
#: honoured too: that file holds fields from alphas already SUBMITTED, and the standing rule is that
#: those are never reused.
#: HOW MANY CONSECUTIVE GEMLESS CYCLES BEFORE MOVING SEGMENT. Khoa, 2026-08-15: "nếu chuỗi lên tới
#: 6-7 chu kì mà vẫn ko tìm ra gem thì đổi". Rotating on a single gemless cycle abandons a segment
#: before it has had a fair sample -- the first version did exactly that and jumped USA -> EUR after
#: one cycle. A cycle is a handful of rounds and gems are rare, so a streak is the right unit.
#: Khoa raised this from 6 to 10 on 2026-08-18, counted from cycle 1 (the op(field)
#: seed), so a segment gets a full phase before it is abandoned.
GEMLESS_BEFORE_ROTATE = 10

SPENT = ROOT / "state/climb/spent_fields.json"
BANNED = ROOT / "state/banned_fields.json"


def spent_fields():
    """Field ids the climb should no longer draw: spent by a finished cycle, or submitted."""
    out = set()
    p = pathlib.Path(SPENT)
    if p.exists():
        try:
            out |= set(json.loads(p.read_text()))
        except ValueError:
            pass
    b = pathlib.Path(BANNED)
    if b.exists():
        try:
            d = json.loads(b.read_text())
            out |= set(d.get("banned_fields") or [])
        except ValueError:
            pass
    return out


def spend_fields(formula):
    """Retire every field a finished cycle's baseline used. Idempotent."""
    got = spent_fields()
    new = set(leaf_fields(formula)) - got
    if not new:
        return 0
    p = pathlib.Path(SPENT)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(got | new)))
    return len(new)


# THE PER-YEAR BOOK FILTER IS OFF.
#
# Khoa asked for it on 2026-08-15 ("alpha đó bắt buộc phải có long short >1000 ở mỗi năm") and
# withdrew it on 2026-08-16 ("bỏ lớp lọc short long >1000"). The default on `pick()` and
# `write_gems()` is now False; the constants stay so turning it back on is one keyword argument,
# not a rewrite.
#
# What it cost while it was on, measured: it is the only screen in the loop that needs an API call
# per candidate, and a single round logged `yearly-stats-unreadable x44` -- 44 candidates dropped
# because the statistic could not be READ, which is not the same fact as a thin book and was being
# treated as one.
#
# The per-year book is still RECORDED on every gem row, because it is real information: one
# headline alpha showed sharpe 3.61 measured over three trading years out of ten while a book line
# of 1431 long / 1406 short sat next to it. Recording a fact and gating on it are different things.
MIN_YEAR_BOOK = 1000

#: HOW MANY TRAILING YEARS MUST HOLD THE BOOK. Khoa lowered this from "every year" on 2026-08-15
#: ("hạ ngưỡng xuống, ví dụ >1000 ở 5 năm gần nhất"), and the example number turned out to pass
#: nobody. Measured on the eight tier-4 alphas before setting it:
#:
#:     2014-2021   0 of 8 hold more than 1000 in ANY of those years
#:     2022        8 of 8
#:     2023        8 of 8
#:
#:     last 1 year   8 of 8 pass        last 3 years  0 of 8      (2021 kills them: 901, 883, ...)
#:     last 2 years  8 of 8 pass        last 5 years  0 of 8
#:
#: So 5 was unreachable and only 1 or 2 leave anything standing. 2 is the loosest value that still
#: requires more than a single year, and it is set here rather than at 5 because a rule nobody can
#: satisfy is not a lowered bar, it is the old bar with a friendlier name.
#:
#: WHAT IT GIVES UP, stated plainly: an alpha now needs to trade in 2 of its 10 backtest years. A
#: sharpe measured over two years is a much weaker claim than one measured over ten, and this rule
#: does not pretend otherwise.
YEAR_BOOK_TRAILING = 2
YEARLY_CACHE = ROOT / "state/climb/yearly_stats.json"


def yearly_book(alpha_id, session=None, cache=None, tries=6, sleep_s=15):
    """[(year, long+short)] for an alpha, or None if it could not be read.

    The FIRST call returns 200 with an EMPTY body and starts the platform computing -- the same
    shape as the correlation endpoint. A single-pass read measures nothing, so this retries.
    None means UNKNOWN and the caller must not treat it as a pass.
    """
    import json as _json
    import time as _time
    path = pathlib.Path(cache or YEARLY_CACHE)
    store = {}
    if path.exists():
        try:
            store = _json.loads(path.read_text())
        except ValueError:
            store = {}
    if alpha_id in store:
        return [tuple(x) for x in store[alpha_id]]

    import layered_sim as LS
    s = session or LS.session()
    for i in range(tries):
        try:
            r = s.get("%s/alphas/%s/recordsets/yearly-stats" % (LS.API, alpha_id), timeout=40)
        except Exception:
            return None
        if r.status_code != 200:
            return None
        if (r.text or "").strip():
            try:
                j = r.json()
            except ValueError:
                return None
            cols = [c.get("name") for c in (j.get("schema") or {}).get("properties", [])]
            if not {"year", "longCount", "shortCount"} <= set(cols):
                return None
            iy, il, ish = cols.index("year"), cols.index("longCount"), cols.index("shortCount")
            out = [(str(rec[iy]), int(rec[il]) + int(rec[ish])) for rec in (j.get("records") or [])]
            store[alpha_id] = out
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_json.dumps(store))
            return out
        if i < tries - 1:
            _time.sleep(sleep_s)
    return None


def year_book_ok(alpha_id, min_book=MIN_YEAR_BOOK, trailing=YEAR_BOOK_TRAILING, **kw):
    """(passed, detail) for the TRAILING `trailing` years. None = unreadable, never a pass.

    An alpha with NO yearly rows fails: a book that was never reported is not a book over 1000. An
    alpha with FEWER rows than the window also fails -- a two-year rule cannot be satisfied by one
    year of history.
    """
    years = yearly_book(alpha_id, **kw)
    if years is None:
        return None, "yearly-stats unreadable"
    if not years:
        return False, "no yearly rows"
    if trailing and len(years) < trailing:
        return False, "only %d year(s) of history, need %d" % (len(years), trailing)
    window = years[-trailing:] if trailing else years
    bad = [(y, n) for y, n in window if n < min_book]
    if bad:
        return False, "%d of the last %d year(s) under %d: %s" % (
            len(bad), len(window), min_book,
            ", ".join("%s=%d" % (y, n) for y, n in bad[:4]))
    return True, "last %d year(s) at or above %d (%s)" % (
        len(window), min_book, ", ".join("%s=%d" % (y, n) for y, n in window))


def _op_pool(pool_a, pool_b):
    """Every operator either layer can supply, as one flat list. Round 1 draws ONE of these; the
    growth rule draws one per move. The A/B split exists for the layered composer's grammar and has
    no meaning here, where a growth is a single wrap."""
    return list(pool_a) + list(pool_b)


def round1(pool_a, pool_b, pool_c, rng, n):
    """`n` alphas of the form op(leaf) -- one function, one field or ratio. Khoa's round-1 spec."""
    ops = _op_pool(pool_a, pool_b)
    weights = leaf_weights(pool_c)
    seen, out = set(), []
    guard = 0
    while len(out) < n and guard < n * 30:
        guard += 1
        op = rng.choice(ops)
        leaf = LA._weighted_choice(pool_c, weights, rng)["expr"]
        f = LA._apply(op, unit_safe(leaf, op_name=op["name"]), rng)
        if f in seen:
            continue
        seen.add(f)
        out.append((f, {"round": 1, "move": "seed", "op": op["name"], "leaf": leaf, "depth": 1}))
    return out


# WHY A NEW CYCLE STARTS DEEP -- measured 2026-08-16 on 8,539 finished alphas.
#
# IS_LADDER_SHARPE is the binding gate, and clearing it is a function of STRUCTURAL DEPTH, not of
# sharpe. Holding the era constant, by nesting-paren count:
#
#     parens   ladder SCORED   ladder PASS
#     0-4          0.0%            0.0%     <- the platform does not even score it
#     4-7         99.1%            0.0%
#     7-11        99.2%            9.4%
#     11-16       99.3%           46.1%
#     16+         99.6%           49.0%
#
# And sharpe alone does not substitute: at sharpe 2.0-2.5, shallow (<7 parens) alphas passed the
# ladder 0.0% of the time (n=30) against 79.5% for deep ones (n=391).
#
# The loop used to open every cycle at depth 1 and add one level per grow round, but a cycle dies
# after STALL_ROUNDS no-gain rounds and resets. In 24 h it produced 4,506 alphas of which 78.6%
# sat at <=3 parens -- below the depth at which the gate is even measured -- and exactly 3 ever
# reached 11. Tier-3 yield over the last 1,325 simulations: ZERO.
#
# Khoa, 2026-08-16: "khi stall là reset hoàn toàn và bắt đầu 1 chu kì hoàn toàn mới." The full
# reset stays. What changes is only WHERE a fresh cycle starts: at the measured depth instead of
# at depth 1. The moves are the same two moves, drawn the same way -- they are simply applied a
# few times before the first simulation rather than one per round across rounds that never last
# long enough.
#
# Measured mapping from grow-steps to parens: depth 5 -> median 11, depth 6 -> median 14.
SEED_PAREN_BAND = (11, 16)
SEED_MAX_MOVES = 9

#: HOW MANY CANDIDATES THE SEED ROUND DRAWS, overriding the round size for that round only.
#: Khoa, 2026-08-18. Measured reason to spend more here than elsewhere: of 6,331 real depth-1 seeds
#: only 40.0% clear the seed filters, so a 200-draw offers ~80 usable starting points and a 350-draw
#: offers ~140. Every later round of the cycle grows from whatever this one picks.
#: NOT ESTABLISHED: that a wider draw yields a BETTER baseline rather than just more of them. The
#: maximum of N samples rises with N whether or not the underlying quality does.
SEED_N = int(os.environ.get("WQ_SEED_N") or 350)
# One switch, so the change is reversible in one edit and an A/B is one environment variable.
# KHOA TURNED THIS OFF, 2026-08-18, and the reason is that MY OWN MEASUREMENT refuted the reason I
# added it. The argument was that structural depth clears IS_LADDER_SHARPE. What depth actually does
# is get the gate SCORED (2.5% -> 93.3% of rows), which is a different fact from getting it PASSED:
# median |sharpe| is 0.27 for a deep seed against 1.91 for something the climb reached by growing.
# A gate that was not scored has not been passed -- the same confusion that made tier 3 unreachable
# earlier the same day. Default is now OFF; `WQ_DEEP_SEED=1` turns it back on for an A/B.
DEEP_SEED = os.environ.get("WQ_DEEP_SEED", "0") != "0"


#: THE MOVE SET. Khoa, 2026-08-18: add new combination types and draw from all of them, not just
#: the original two.
#:
#: WHY THESE FIVE, and not five arbitrary ones -- each closes a shape the old two could not reach,
#: measured on 1,187 live formulas / 4,289 infix nodes:
#:
#:   * the right operand of every infix had median depth 1 and max 4, and only 1.66% of nodes had
#:     both sides grown -- so the tree was a LEFT SPINE. BLEND grows an independent branch first,
#:     which is the only way two real sub-signals can meet. An ensemble was structurally
#:     unreachable before this, not merely rare.
#:   * all 37 pooled operators are unary, so a relationship BETWEEN two series could only ever be
#:     expressed pointwise by + - * /. RELATE supplies ts_corr / ts_covariance / ts_regression.
#:   * there were no logical operators at all, so no alpha could act only in a regime. GATE and
#:     FLIP supply that; the journal records one live alpha from regime gating (anti_corr M3).
#:   * NEUT removes the component of the signal another field explains -- the de-crowding shape.
#:
#: NOT ESTABLISHED: that any of these raise the gem rate. The weights below are a GUESS -- the two
#: original moves keep the majority of the draw so the search does not lurch, and every new move is
#: rare enough that a bad one cannot dominate a round. Override with WQ_MOVE_WEIGHTS as JSON to
#: A/B any of it in one environment variable. MECHANISM: UNKNOWN.
# KHOA CHOSE AN EVEN SPREAD, 2026-08-18: "phan bo deu". Every move gets the same 1/7 of the draw.
# My earlier 34/34/12/7/6/3/4 was a guess dressed as caution -- it held the two original moves at
# 68% for no measured reason, which would have made the five new moves take five times longer to
# accumulate a readable sample. An even spread is also the only weighting that needs no defence.
MOVE_WEIGHTS = {"wrap": 1, "combine": 1, "blend": 1, "relate": 1, "gate": 1, "flip": 1, "neut": 1}
try:
    MOVE_WEIGHTS.update(json.loads(os.environ.get("WQ_MOVE_WEIGHTS") or "{}"))
except ValueError:
    pass

#: Two-series operators. Arity and argument ORDER are copied from OPERATORS.md verbatim, because a
#: wrong arity is a 400 from the platform, not a bad alpha.
RELATE_OPS = ("ts_corr", "ts_covariance", "ts_regression")
#: NEUTRALISERS, and the one that must NOT be used bare. `vector_neut(x, y)` returns the REJECTION
#: -- the part of x orthogonal to y -- so it neutralises on its own. `regression_proj(y, x)` returns
#: the PROJECTION, the part of y that x explains: using it bare would keep exactly the crowded
#: component and discard the distinctive one, the precise opposite of the intent. The residual has
#: to be written out, as the platform docs themselves do:
#:
#:     -returns - regression_proj(-returns, ts_stddev(returns, 20))  ==  regression_neut(...)
#:
#: `regression_neut` is NOT on the RC-85 allowlist -- it exists only inside that doc example --
#: so the subtraction is the only way to get a residual out of it.
#:
#: Khoa spotted this by asking whether NEUT was a vector-field operator. It is not (`vector_neut`
#: is Cross Sectional and its own docs demonstrate it on `open` and `close`), but the question is
#: what surfaced the projection/rejection error sitting next to it.
NEUT_OPS = ("vector_neut", "regression_proj")

#: A conditional compares two magnitudes, so it has the same unit requirement `+` and `-` have.
#: Rather than wrap both sides, the condition is built on `ts_rank`, whose output is a rank in
#: [0, 1] and therefore dimensionless by construction -- the comparison can then be against a plain
#: number with no unit question at all.
GATE_THRESHOLDS = (0.55, 0.65, 0.75, 0.85)

#: `if_else` names the baseline TWICE, so it doubles the expression. Past this length the move
#: falls back to a wrap rather than emitting something the platform may refuse on size alone.
FLIP_MAX_BASELINE = 400


def _leaf_expr(ops, pool_c, weights, rng):
    """`op(field)` -- the smallest complete sub-expression, unit-safe."""
    op = rng.choice(ops)
    leaf = LA._weighted_choice(pool_c, weights, rng)["expr"]
    return LA._apply(op, unit_safe(leaf, op_name=op["name"]), rng), leaf


def _branch(ops, pool_c, weights, rng, steps):
    """An INDEPENDENT sub-expression, grown by the original two moves only.

    This is what the old grammar could not produce: every new field used to enter as `op(leaf)` and
    nothing more, so no second branch ever got to be as deep as the first. Recursion is impossible
    here -- `_branch` calls only wrap and combine, never the new moves.
    """
    expr, _ = _leaf_expr(ops, pool_c, weights, rng)
    for _ in range(steps):
        op = rng.choice(ops)
        if rng.random() < 0.5:
            expr = LA._apply(op, unit_safe(expr, op_name=op["name"]), rng)
            continue
        infix = rng.choice(INFIX_OPS)
        other, _ = _leaf_expr(ops, pool_c, weights, rng)
        combined = "%s %s %s" % (unit_safe(expr, infix=infix), infix,
                                 unit_safe(other, infix=infix))
        expr = LA._apply(op, unit_safe("(%s)" % combined, op_name=op["name"]), rng)
    return expr


def _pick_move(rng):
    live = [(k, v) for k, v in MOVE_WEIGHTS.items() if v > 0]
    total = sum(v for _, v in live)
    if total <= 0:                      # a zero-sum weight vector must not make one move certain
        return "wrap"
    x = rng.random() * total
    acc = 0.0
    for name, w in live:
        acc += w
        if x <= acc:
            return name
    return live[-1][0]


def _grow_once(baseline, ops, pool_c, weights, rng):
    """One move applied to `baseline`, drawn from MOVE_WEIGHTS.

        WRAP     op(baseline)
        COMBINE  op(baseline <+-*/> op(new_field))
        BLEND    op(baseline <+-*/> BRANCH)          -- branch grown 2-4 moves deep
        RELATE   ts_corr|ts_covariance|ts_regression(baseline, BRANCH, d)
        GATE     trade_when(cond, baseline, -1)      -- trade only inside a regime
        FLIP     if_else(cond, baseline, -baseline)  -- conditional sign flip
        NEUT     vector_neut|regression_proj(baseline, BRANCH)

    Every move returns the same (formula, meta) pair, so the seeder, the round-by-round growth and
    the journal all see one shape. `meta["move"]` is what a later analysis groups on.
    """
    move = _pick_move(rng)
    op = rng.choice(ops)

    if move == "wrap":
        return LA._apply(op, unit_safe(baseline, op_name=op["name"]), rng), \
            {"move": "wrap", "op": op["name"]}

    if move == "combine":
        inner_op = rng.choice(ops)
        leaf = LA._weighted_choice(pool_c, weights, rng)["expr"]
        infix = rng.choice(INFIX_OPS)
        # `+` and `-` demand both sides share a unit; `*` and `/` combine units legitimately. This
        # is 53% of every UNITS warning in the corpus (add 383, subtract 194).
        left = unit_safe(baseline, infix=infix)
        right = unit_safe(LA._apply(inner_op, unit_safe(leaf, op_name=inner_op["name"]), rng),
                          infix=infix)
        combined = "%s %s %s" % (left, infix, right)
        return LA._apply(op, unit_safe("(%s)" % combined, op_name=op["name"]), rng), {
            "move": "combine", "op": op["name"], "infix": infix,
            "inner_op": inner_op["name"], "leaf": leaf}

    steps = rng.randint(2, 4)

    if move == "blend":
        branch = _branch(ops, pool_c, weights, rng, steps)
        infix = rng.choice(INFIX_OPS)
        combined = "%s %s %s" % (unit_safe(baseline, infix=infix), infix,
                                 unit_safe(branch, infix=infix))
        return LA._apply(op, unit_safe("(%s)" % combined, op_name=op["name"]), rng), {
            "move": "blend", "op": op["name"], "infix": infix, "branch_steps": steps}

    if move == "relate":
        name = rng.choice(RELATE_OPS)
        branch = _branch(ops, pool_c, weights, rng, steps)
        d = rng.choice(LA.WINDOWS)
        return "%s(%s, %s, %d)" % (name, baseline, branch, d), {
            "move": "relate", "op": name, "d": d, "branch_steps": steps}

    if move in ("gate", "flip"):
        branch = _branch(ops, pool_c, weights, rng, steps)
        d = rng.choice(LA.WINDOWS)
        thr = rng.choice(GATE_THRESHOLDS)
        cond = "greater(ts_rank(%s, %d), %s)" % (branch, d, thr)
        if move == "gate":
            return "trade_when(%s, %s, -1)" % (cond, baseline), {
                "move": "gate", "op": "trade_when", "d": d, "thr": thr,
                "branch_steps": steps}
        if len(baseline) > FLIP_MAX_BASELINE:
            return LA._apply(op, unit_safe(baseline, op_name=op["name"]), rng), \
                {"move": "wrap", "op": op["name"], "note": "flip-too-long"}
        return "if_else(%s, %s, (-1 * %s))" % (cond, baseline, baseline), {
            "move": "flip", "op": "if_else", "d": d, "thr": thr, "branch_steps": steps}

    name = rng.choice(NEUT_OPS)
    branch = _branch(ops, pool_c, weights, rng, steps)
    if name == "vector_neut":
        return "vector_neut(%s, %s)" % (baseline, branch), {
            "move": "neut", "op": name, "branch_steps": steps}
    # The residual, not the projection. Both operands are in the baseline's own units by
    # construction, so this subtraction does NOT go through `unit_safe` -- ranking either side
    # would leave a difference of two ranks, which is not a residual of anything.
    return "(%s - regression_proj(%s, %s))" % (baseline, baseline, branch), {
        "move": "neut", "op": "regression_resid", "branch_steps": steps}


def round1_deep(pool_a, pool_b, pool_c, rng, n, band=SEED_PAREN_BAND, max_moves=SEED_MAX_MOVES):
    """`n` fully random alphas built straight into the measured depth band.

    Still a completely fresh cycle: every operator and every field is drawn at random, and nothing
    is carried over from the cycle that stalled. No stored skeleton is replayed -- composing the
    structure rather than reusing a remembered one is what keeps the search from collapsing onto a
    single ensemble shape.
    """
    ops = _op_pool(pool_a, pool_b)
    weights = leaf_weights(pool_c)
    lo, hi = band
    seen, out = set(), []
    guard = 0
    while len(out) < n and guard < n * 40:
        guard += 1
        leaf = LA._weighted_choice(pool_c, weights, rng)["expr"]
        op = rng.choice(ops)
        # The FOURTH wiring point of the unit fix, and the one it originally missed. This is the
        # seed of every cycle, so the operator here lands straight on a RAW FIELD -- exactly the
        # `hump(weighted_return_long) -> expected "Unit[]", found "Unit[CSPrice:1]"` shape. Found by
        # a live test on 2026-08-18, not by reading the patch back.
        f = LA._apply(op, unit_safe(leaf, op_name=op["name"]), rng)
        meta = {"round": 1, "move": "seed-deep", "op": op["name"], "leaf": leaf, "depth": 1}
        moves = 0
        while f.count("(") < lo and moves < max_moves:
            f2, m2 = _grow_once(f, ops, pool_c, weights, rng)
            if f2.count("(") > hi:
                break            # overshoot: keep the shallower one and let the guard retry
            f, moves = f2, moves + 1
            meta["depth"] = moves + 1
            meta.setdefault("moves", []).append(m2["move"])
        p = f.count("(")
        if p < lo or p > hi or f in seen:
            continue             # only the band counts; a near miss is a retry, not a compromise
        seen.add(f)
        meta["parens"] = p
        out.append((f, meta))
    return out


def grow(baseline, pool_a, pool_b, pool_c, rng, n, depth):
    """`n` growths of `baseline`, exactly the two moves Khoa specified.

        WRAP     op(baseline)
        COMBINE  op(baseline <+-*/> op(new_field))

    The two are drawn with equal probability. COMBINE is the move that introduces new DATA, which is
    the only way the loop can reach a field it has not already used; WRAP can only reshape what is
    already there. Neither is privileged by any measurement -- the split is 50/50 because nothing
    here has established a reason for anything else. MECHANISM: UNKNOWN.
    """
    ops = _op_pool(pool_a, pool_b)
    weights = leaf_weights(pool_c)
    seen, out = set(), []
    guard = 0
    while len(out) < n and guard < n * 30:
        guard += 1
        f, meta = _grow_once(baseline, ops, pool_c, weights, rng)
        if f in seen or f == baseline:
            continue
        if op_count(f) > MAX_FORMULA_OPS:
            # Over the platform's 64-operator limit: POSTing it buys a guaranteed ERROR. A
            # baseline near the cap makes most draws land here, the round comes back small, and
            # the ladder's own no-gain/stall machinery ends the cycle -- which is the correct
            # outcome for a tree that has nowhere left to grow.
            continue
        seen.add(f)
        meta["depth"] = depth + 1
        out.append((f, meta))
    return out


# ------------------------------------------------------------------------- parameter tuning
#
# Khoa, 2026-08-14: rounds ALTERNATE between growing the structure and tuning the numbers already
# in the baseline. "ko cần tính chẵn lẻ nữa mà là xen kẻ" -- the alternation follows the LAST
# round's kind, not the round number, because a tune round with nothing to tune is passed over and
# parity would then drift out of step with what actually ran.
#
# WHAT THE EVIDENCE SAYS ABOUT TUNING, stated up front so the round is read honestly. R3_E1 swept
# every numeric in the corpus:
#   in-formula decay   STEERABLE, smaller wins -- replicated four ways, argmax = smallest offered
#                      in 89.2% of sweeps against 29.0% by chance, +0.405 sharpe over a 5->60 sweep
#   lookback           the cleanest NULL in the corpus: shorter wins 48/98 shells (p 0.755), and
#                      the direction INVERTS by operator (ts_zscore 0.570 vs ts_rank 0.371)
#   exponent           significant and useless: p 1.4e-05, effect 0.040 sharpe against a 1.58 bar
#   leg weights        NO VERDICT at 10 shells
# So a tune round is expected to move little except through decay. It runs because Khoa asked for
# it and because the corpus evidence is about OTHER generators' formulas; whether it holds for this
# climb's own baselines is unmeasured, and the round measures it.

#: What a tune round may vary. `group` is included on Khoa's instruction: group granularity changes
#: book width directly, and a narrow book is what CONCENTRATED_WEIGHT blocks on.
_INT_ARG = re.compile(r"(?<=[,(])\s*(\d+)\s*(?=[,)])")
_FLOAT_ARG = re.compile(r"(?<=[,(])\s*(\d+\.\d+)\s*(?=[,)])")
_GROUP_ARG = re.compile(r"(?<=[,(])\s*(%s)\s*(?=[,)])" % "|".join(LA.GROUPS))

#: Exponent-like floats. A weight in a blend is also a float, and this pool suits both -- neither
#: has a measured optimum, so the pool is a spread rather than a claim.
_FLOATS = (0.25, 0.4, 0.5, 0.66, 0.8, 1.0, 1.25, 1.5, 2.0)

#: Slots changed per variant. Khoa: "đổi baseline đúng 2 số hoặc 3 số miễn lắp đầy được tổ hợp biến
#: dị 300 alpha". Capped by how many slots the baseline actually has.
TUNE_SLOTS = (2, 3)


def tunable_slots(formula):
    """Every position in `formula` a tune round may change: (start, end, kind, current, choices).

    Found by scanning ARGUMENT positions rather than by parsing the whole expression. A number is
    only a slot when it sits after a comma or an open paren and before a comma or a close paren --
    so `ts_delta(x, 20)` yields the 20 and a field named `oth460_1l_qidxt` yields nothing.
    """
    out = []
    for rx, kind, choices in ((_INT_ARG, "window", LA.WINDOWS),
                              (_FLOAT_ARG, "float", _FLOATS),
                              (_GROUP_ARG, "group", LA.GROUPS)):
        for m in rx.finditer(formula):
            cur = m.group(1)
            out.append((m.start(1), m.end(1), kind, cur, choices))
    return sorted(out)


def tune(baseline, rng, n, slots_per_variant=TUNE_SLOTS):
    """`n` variants of `baseline` with the SAME structure and different numbers.

    Each variant changes EXACTLY k slots, k drawn from `slots_per_variant` and capped by how many
    slots exist. A variant that lands back on the baseline's own values is discarded, so every row
    in the round is a real variant rather than a re-measurement of the baseline.
    """
    slots = tunable_slots(baseline)
    if not slots:
        return []
    seen, out = {baseline}, []
    guard = 0
    while len(out) < n and guard < n * 40:
        guard += 1
        k = min(rng.choice(slots_per_variant), len(slots))
        chosen = rng.sample(range(len(slots)), k)
        parts, changed = [], []
        last = 0
        for i in sorted(chosen):
            s, e, kind, cur, choices = slots[i]
            alt = [str(c) for c in choices if str(c) != cur]
            if not alt:
                continue
            new = rng.choice(alt)
            parts.append(baseline[last:s])
            parts.append(new)
            last = e
            changed.append({"kind": kind, "from": cur, "to": new})
        parts.append(baseline[last:])
        f = "".join(parts)
        if f in seen:
            continue
        seen.add(f)
        out.append((f, {"move": "tune", "changed": changed, "n_slots": len(slots)}))
    return out


def next_kind(st):
    """Which kind of round to run now. ALTERNATES on the last round's kind, not on parity.

    A tune round with no tunable slot is passed over (Khoa: "trong trường hợp ko có tham số thì tạm
    pass đợt"), and the caller runs a grow instead -- so parity would drift out of step with what
    actually ran, which is why the alternation is stateful.
    """
    if not st.get("baseline"):
        return "seed"
    return "grow" if st.get("last_kind") == "tune" else "tune"


def load_state():
    if STATE.exists():
        st = json.loads(STATE.read_text())
        st.setdefault("segment", ["USA", "TOP3000", 1])
        st.setdefault("gemless_streak", 0)
        return st
    return {"cycle": 1, "round": 0, "baseline": None, "baseline_score": None,
            "history": [], "no_gain": 0, "segment": ["USA", "TOP3000", 1],
            "gemless_streak": 0}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1))


def draw(st, pool_a, pool_b, pool_c, rng, n, out=None):
    """The next round's candidates. Rounds ALTERNATE grow / tune; see `next_kind`.

    Returns the candidate list; the kind actually run is recorded on every row's meta as `move`, so
    a journalled row never has to be re-classified later.
    """
    say = out or (lambda _m: None)
    kind = next_kind(st)
    if kind == "seed" and SEED_N and SEED_N != n:
        # A WIDER FIRST ROUND. Khoa, 2026-08-18: "o vong dau cho sim 350 de tim duoc 1 alpha tot".
        # The seed round picks the point every later round of the cycle grows from, and it is the
        # one round with nothing to fall back on -- so it is the round where a bigger draw buys the
        # most. Announced, never silent: a round that ran a different size than the caller asked
        # for must say so, or the sim count in the log stops matching the quota that was spent.
        say("SEED ROUND: %d candidates (round size %d, widened for the first round)" % (SEED_N, n))
        n = SEED_N
    if kind == "seed":
        if DEEP_SEED:
            got = round1_deep(pool_a, pool_b, pool_c, rng, n)
            # Never silently return a short round: if the band could not be filled, say by how much
            # and fill the rest at depth 1 rather than pretending the round was what it asked for.
            if len(got) < n:
                short = n - len(got)
                say("round kind SEED-DEEP: %d/%d in the %d-%d paren band; %d short, filling at "
                    "depth 1" % (len(got), n, SEED_PAREN_BAND[0], SEED_PAREN_BAND[1], short))
                got = got + round1(pool_a, pool_b, pool_c, rng, short)
            else:
                say("round kind SEED-DEEP: %d alphas in the %d-%d paren band"
                    % (len(got), SEED_PAREN_BAND[0], SEED_PAREN_BAND[1]))
            return got
        return round1(pool_a, pool_b, pool_c, rng, n)
    if kind == "tune":
        got = tune(st["baseline"], rng, n)
        if got:
            slots = len(tunable_slots(st["baseline"]))
            if len(got) < n:
                # TOP UP RATHER THAN WASTE THE ROUND. A baseline with one tunable slot yields five
                # distinct variants, so a 100-simulation round was spending five. The shortfall is
                # filled with GROW candidates and the round is labelled by whichever move dominates,
                # so the history still says what actually ran.
                extra = grow(st["baseline"], pool_a, pool_b, pool_c, rng, n - len(got),
                             depth=st.get("depth", 1))
                say("round kind TUNE: %d slot(s) -> only %d variant(s); topping up with %d grow"
                    % (slots, len(got), len(extra)))
                return got + extra
            say("round kind TUNE: %d slot(s) in the baseline" % slots)
            return got
        # PASSED OVER, not failed. Khoa: a baseline with no parameter means the tune round has
        # nothing to do, so it is skipped and a grow runs instead. This is exactly why the
        # alternation follows the last round's KIND and not the round number.
        say("round kind TUNE PASSED: the baseline has no tunable parameter -- growing instead")
    say("round kind GROW")
    return grow(st["baseline"], pool_a, pool_b, pool_c, rng, n, depth=st.get("depth", 1))


def pick(rows, objective=OBJECTIVE, require_band=True, reject_checks=REJECT_CHECKS,
         year_book=False, min_book=MIN_YEAR_BOOK, session=None):
    """The best baseline candidate, per Khoa's two filters (2026-08-14):

      1. the baseline MUST sit inside the turnover band, 0.01 < turnover < 0.7
      2. if it FAILS CONCENTRATED_WEIGHT, drop it and take the next one down
      3. it must hold more than 1000 names in EVERY YEAR (2026-08-15). This one costs an API call,
         so it is checked LAST, only on candidates that already passed everything free, walking
         down the ranking until one passes.

    Both were added after the first live rounds showed what plain argmax picks. The standing best
    by fitness was sharpe 1.82 / fitness 1.80 -- and `book 4 long / 4 short`, failing
    CONCENTRATED_WEIGHT. Climbing from it would have grown every later round on top of an 8-name
    book. Earlier the same lookup returned sharpe 25.18 at turnover 1.000, and sharpe 6.64 at book
    0/0.

    Returns (formula, score, row, skipped) where `skipped` counts, by reason, what was passed over.
    A skipped candidate is never silently dropped -- the counts are journalled and printed.

    A GATE THAT WAS NOT SCORED HAS NOT BEEN PASSED. `IS_LADDER_SHARPE` is scored on only 560 of
    1,020 rows here, so "does not fail it" silently includes "was never graded on it". That is the
    exact gate-PRESENCE artifact that produced the council's false "carrier-free fails the ladder
    less" -- the gate was scored on 71.7% of one arm and 99.3% of the other, and conditioning on
    presence collapsed the effect to p 0.234. A candidate accepted without a reject gate scored is
    counted as `<GATE>-not-scored`, so the uncertainty is on the page instead of inside the number.

    A row whose checks are absent is NOT rejected: CONCENTRATED_WEIGHT is scored on essentially
    every row, so an unscored one is rare, and rejecting on absence could leave a round with no
    baseline at all. Those rows are counted separately as `unscored` so the uncertainty is visible
    rather than assumed away.
    """
    lo, hi = SCREEN_TURNOVER
    skipped = collections.Counter()
    ranked = sorted(
        (r for r in rows
         if isinstance(metric(r, objective), (int, float)) and r.get("formula")),
        key=lambda r: -metric(r, objective))
    for r in ranked:
        if require_band:
            tv = r.get("turnover")
            if not isinstance(tv, (int, float)):
                skipped["no-turnover"] += 1
                continue
            if not (lo < tv < hi):
                skipped["turnover-out-of-band"] += 1
                continue
        fails = failing_checks(r)
        if fails is None:
            skipped["checks-unscored"] += 1        # counted, but ACCEPTED -- see the docstring
        elif reject_checks:
            hard = sorted(set(fails) & set(reject_checks))
            if hard:
                skipped["+".join(hard)] += 1
                continue
            # KHOA, 2026-08-18: only a FAIL disqualifies a BASELINE now; a WARNING is counted and
            # accepted. This is deliberately NOT the rule for a gem, which must still pass every
            # scored gate -- the two questions are different. What we stand on to climb may carry a
            # warning; what we submit may not. The count stays so the loosening is visible: if
            # warned baselines turn out to lead nowhere, `skipped` already holds the evidence.
            adverse, unscored = blocked_on(r, reject_checks)
            hard_warn = sorted(set(adverse or ()) & set(HARD_CHECKS))
            if hard_warn:
                skipped["WARNING-rejected:" + "+".join(hard_warn)] += 1
                continue
            for g in (adverse or []):
                skipped["WARNING-accepted:" + g] += 1
            for g in (unscored or []):
                skipped[g + "-not-scored"] += 1     # counted, ACCEPTED -- see blocked_on
        if year_book and r.get("alpha"):
            # LAST, because it is the only filter that costs a request. Everything above is free.
            ok, why = year_book_ok(r["alpha"], min_book=min_book, session=session)
            if ok is None:
                skipped["yearly-stats-unreadable"] += 1
                continue                      # UNKNOWN is not a pass
            if not ok:
                skipped["year-book<%d" % min_book] += 1
                continue
        return r.get("formula"), metric(r, objective), r, skipped
    return None, None, None, skipped


def gained(score, prev, min_gain=MIN_GAIN):
    """Did `score` beat `prev` by `min_gain` (a FRACTION), for a prev of any sign?

    The obvious form, `score > prev * (1 + min_gain)`, INVERTS on a negative baseline: with
    prev = -0.50 the bar becomes -0.525, so -0.51 -- which is WORSE -- registers as progress. It
    never fired (0 of 64 rounds had a negative baseline under sub_sharpe), but the objective is now
    fitness, whose median is 0.09 and which is negative on 28% of rows, so it would have.

    Measuring the step against |prev| keeps the bar above `prev` whatever its sign, and a zero
    baseline needs any strictly positive score rather than being unbeatable.
    """
    if prev is None:
        return True
    if prev == 0:
        return score > 0
    return score > prev + min_gain * abs(prev)


def advance(st, rows, objective=OBJECTIVE, min_gain=MIN_GAIN, stall_rounds=STALL_ROUNDS):
    """Fold one round's results into the state. Returns (state, event) where event is one of
    'progress', 'no-gain', 'stall'."""
    # The SEED round filters on less: with no baseline yet, this round is choosing a starting
    # point, and the ratio gate rejects 46.6% of seeds for missing a bar meant for a grown alpha.
    seed_round = not st.get("baseline")
    formula, score, row, skipped = pick(
        rows, objective, reject_checks=SEED_REJECT_CHECKS if seed_round else REJECT_CHECKS)
    st["round"] = st.get("round", 0) + 1
    prev = st.get("baseline_score")

    # The kind that ACTUALLY ran, read off the rows rather than recomputed -- a tune round that was
    # passed over ran as a grow, and the state must alternate from what happened.
    kinds = collections.Counter((r.get("meta") or {}).get("move") for r in rows)
    # THE MAJORITY MOVE, not the first one seen. A tune round that was topped up with grow
    # candidates must alternate from what actually dominated it, or the next round repeats the
    # same kind and the alternation quietly stops.
    if kinds.get("seed"):
        ran = "seed"
    else:
        ran = "tune" if kinds.get("tune", 0) > kinds.get("wrap", 0) + kinds.get("combine", 0) \
            else "grow"
    st["last_kind"] = ran

    entry = {"cycle": st["cycle"], "round": st["round"], "n": len(rows), "kind": ran,
             "best_score": score, "prev_baseline_score": prev,
             "screened": sum(1 for r in rows if screened(r)),
             "tier3": sum(1 for r in rows if tier(r) == 3),
             "gems": sum(1 for r in rows if tier(r) == 4),
             "skipped": dict(skipped)}

    if formula is None:
        # DEAD END, not a slow round. Khoa, 2026-08-15: "khi ko chọn ra được alpha baseline do lỗi
        # ko vượt qua lọc thì bắt đầu lại từ đầu". Nothing in 300 candidates cleared the filters, so
        # there is nothing to climb from -- waiting for a second no-gain round would spend another
        # 300 simulations growing a branch that has no baseline at all.
        entry["event"] = "dead-end"
        st["no_gain"] = st.get("no_gain", 0) + 1
        st.setdefault("history", []).append(entry)
        return st, "dead-end"
    elif prev is None or gained(score, prev, min_gain):
        # THE BASELINE'S RE-MEASURED SCORE. Every growth contains the baseline, so the round's own
        # rows are a second look at it; the drift between the two is the selection bias Khoa was
        # told about and chose to accept. Recorded, never argued with.
        entry["event"] = "progress"
        st["baseline"], st["baseline_score"] = formula, score
        st["depth"] = (row.get("meta") or {}).get("depth", st.get("depth", 1))
        st["no_gain"] = 0
    else:
        entry["event"] = "no-gain"
        st["no_gain"] = st.get("no_gain", 0) + 1
        if score > (prev or -9e9):        # improved, but not by enough to count
            st["baseline"], st["baseline_score"] = formula, score

    st.setdefault("history", []).append(entry)
    if st["no_gain"] >= stall_rounds:
        entry["event"] = "stall"
        return st, "stall"
    return st, entry["event"]


#: How many times a cycle may be retried on the same benchmark before the whole phase restarts.
#: Khoa, 2026-08-17: "nếu ở chu kì sau mà benchmark ko cải thiện thì reset chu kì đó tối đa 2 lần,
#: nếu ko cải tiến được nữa thì reset toàn phase bắt đầu lại từ chu kì 1".
CYCLE_RETRIES = 2


def cycle_best(st, cycle=None):
    """The best score this cycle actually reached, from the history it already writes.

    Read from `history` rather than tracked in a new field: every round appends `best_score` with
    its cycle number, so the number is already on disk and cannot drift out of step with a second
    counter. A cycle that never picked a baseline has no scores and returns None, which is a
    different fact from zero and is kept that way.
    """
    cycle = st.get("cycle") if cycle is None else cycle
    # ROUND ENTRIES ONLY -- the entry must carry a round number. Ladder events (cycle-advanced /
    # cycle-retry / phase-reset) also carry a numeric best_score, and they are appended AFTER the
    # cycle counter moves, so they land in the NEXT cycle's history. Counting them let a score walk
    # forward forever: the 4-name book's 27.58 was carried by its own advance event into cycle 3,
    # then by the retry events into every later reading, and the benchmark could never come down.
    # The 2.0 benchmark that kept reappearing after every phase reset all week was this same defect.
    # Measured 2026-08-28: cycle 3's real rounds scored 0.52-1.04 while cycle_best said 27.58.
    scores = [h.get("best_score") for h in (st.get("history") or [])
              if h.get("cycle") == cycle and h.get("round") is not None
              and isinstance(h.get("best_score"), (int, float))]
    return max(scores) if scores else None


def reset(st, gems):
    """End of a cycle. Gems are written out, the baseline's fields are RETIRED, and the loop starts
    over.

    Khoa reversed the no-banning rule on 2026-08-15 after cycles 5-11 kept rediscovering the same
    core. The fields of the baseline the cycle ended on are spent and will not be drawn again.

    THE BENCHMARK LADDER (Khoa, 2026-08-17). A cycle now has to BEAT the phase's standing
    benchmark, not merely finish:

        beat it            -> benchmark rises, retry count clears, cycle += 1
        missed it, <= 2x   -> RETRY the same cycle number against the same benchmark
        missed it, 3rd     -> PHASE RESET: back to cycle 1, benchmark cleared

    The point is to stop the loop grinding forever on a plateau. Cycles 9 and 10 both died on their
    first round with no baseline at all, and cycle 11 climbed to 0.74 -- but nothing forced any of
    them to be better than what came before, so a phase could wander sideways indefinitely.

    A retry still retires the baseline's fields and still counts toward the gemless streak: it is a
    fresh attempt at the same bar, not a rewind. Rewinding those would let a stuck phase redraw the
    same exhausted core, which is the exact failure the field-retirement rule was added to stop.
    """
    # ROTATE THE SEGMENT when a cycle produced no gem. Khoa, 2026-08-15: "trong cycle toi neu ko
    # tim ra alpha gem thi rotate qua cac region khac". A cycle that DID find one stays put -- the
    # segment is evidently productive and there is no reason to leave it.
    import pool_gate as PGATE
    cur = tuple(st.get("segment") or ("USA", "TOP3000", 1))
    if gems:
        st["gemless_streak"] = 0
    else:
        st["gemless_streak"] = st.get("gemless_streak", 0) + 1
    # A STREAK, NOT A SINGLE CYCLE. Khoa corrected this on 2026-08-15: "ko phải chu kì có gem thì ở
    # lại mà nếu chuỗi lên tới 6-7 chu kì mà vẫn ko tìm ra gem thì đổi". My first version rotated on
    # any gemless cycle and duly jumped USA -> EUR after ONE cycle, which abandons a segment before
    # it has been given a fair sample -- a cycle is a handful of rounds and gems are rare.
    if st["gemless_streak"] >= GEMLESS_BEFORE_ROTATE:
        nxt = PGATE.next_segment(cur)
        if nxt and tuple(nxt) != cur:
            st["segment"] = list(nxt)
            st["gemless_streak"] = 0
            st.setdefault("history", []).append(
                {"cycle": st.get("cycle"), "event": "segment-rotated",
                 "from": list(cur), "to": list(nxt), "after_gemless": GEMLESS_BEFORE_ROTATE,
                 "note": "%d consecutive cycles without a gem. Each segment has its OWN ratio-gate "
                         "constant (0.295-0.711 across segments) and its OWN pyramid counts -- "
                         "nothing measured here carries across."
                         % GEMLESS_BEFORE_ROTATE})
    # KHOA, 2026-08-18: "chi cam khi ra gem". A cycle that found nothing has not shown its fields
    # are exhausted -- it has shown this branch of the search was, which is a different claim. Only
    # a gem retires the fields that produced it.
    if st.get("baseline") and gems:
        n = spend_fields(st["baseline"])
        if n:
            st.setdefault("history", []).append(
                {"cycle": st.get("cycle"), "event": "fields-retired", "n": n,
                 "from": st["baseline"][:120]})
    # --- the benchmark ladder -------------------------------------------------------------
    got = cycle_best(st)
    bench = st.get("phase_benchmark")
    tries = st.get("cycle_retries", 0)
    improved = got is not None and (bench is None or got > bench)

    if improved:
        st["phase_benchmark"], st["cycle_retries"] = got, 0
        st["cycle"] = st.get("cycle", 1) + 1
        event, note = "cycle-advanced", "best %.4f beats benchmark %s" % (
            got, "none" if bench is None else "%.4f" % bench)
    elif tries < CYCLE_RETRIES:
        # SAME cycle number: this is another attempt at the same bar, so the history stays readable
        # as "cycle N, attempt 2" rather than pretending progress was made.
        st["cycle_retries"] = tries + 1
        event, note = "cycle-retry", "best %s did not beat benchmark %.4f -- retry %d of %d" % (
            "none" if got is None else "%.4f" % got, bench or 0.0, tries + 1, CYCLE_RETRIES)
    else:
        # PHASE RESET. Everything the phase learned about where to stand is cleared: the benchmark,
        # the retry count, the cycle number, the gemless streak. Retired fields are NOT cleared --
        # they are what stops the fresh phase walking straight back into the exhausted core.
        # gemless_streak is NOT cleared here, and a test pins that. It counts cycles without a GEM,
        # which is a different question from whether the benchmark moved -- and a phase reset fires
        # every 3 non-improving cycles, so clearing it would hold the streak permanently below the
        # 6 that triggers a segment rotation and quietly make rotation unreachable. Only a gem
        # clears it. Found by the rotation test the moment this branch was added.
        st["phase_benchmark"], st["cycle_retries"] = None, 0
        st["cycle"] = 1
        event, note = "phase-reset", (
            "best %s did not beat benchmark %.4f after %d retries -- restarting the phase at "
            "cycle 1" % ("none" if got is None else "%.4f" % got, bench or 0.0, CYCLE_RETRIES))

    st.setdefault("history", []).append(
        {"cycle": st.get("cycle"), "event": event, "best_score": got,
         "benchmark": st.get("phase_benchmark"), "retries": st.get("cycle_retries"), "note": note})

    st["round"], st["baseline"], st["baseline_score"] = 0, None, None
    st["no_gain"], st["depth"], st["last_kind"] = 0, 1, None
    return st


def write_candidates(rows, cycle, path=None):
    """Every tier-3 alpha, to the CANDIDATE list -- the queue a correlation probe should read.

    These are NOT gems. Their correlation gates are PENDING, meaning unmeasured, and an unmeasured
    gate is not a passed one.
    """
    path = path or (STATE.parent / "corr_candidates.jsonl")
    got = [r for r in rows if tier(r) == 3]
    if not got:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        for r in got:
            fh.write(json.dumps({
                "cycle": cycle, "alpha": r.get("alpha"), "formula": r.get("formula"),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
                "turnover": r.get("turnover"), "found_at": time.time(),
                "note": "TIER 3: cleared every scored gate. PROD_CORRELATION and SELF_CORRELATION "
                        "are PENDING -- unmeasured, NOT passed. Measure with measure_backlog.py "
                        "before this is called anything.",
            }) + "\n")
    return len(got)


def ledger_alphas(path=None):
    """Alpha ids already in the gem ledger."""
    p = pathlib.Path(path or LEDGER)
    out = set()
    if not p.exists():
        return out
    for line in p.read_text(errors="ignore").splitlines():
        if line.startswith("{"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("alpha"):
                out.add(r["alpha"])
    return out


def write_gems(rows, cycle, measured=None, year_book=False, session=None):
    """NEW tier-4 alphas, to the ledger. **This does not submit and must never submit.**

    DEDUPLICATED AGAINST THE LEDGER, and that is not tidiness. Without it the same alphas were
    re-appended every cycle: 50 gem rows turned out to be FIVE distinct alphas written ten times.
    The loop ends a cycle when the ledger GROWS, so the count kept growing, every cycle ended
    immediately on stale gems, and seven cycles spent 330 simulations each going in a circle.

    THE YEAR FILTER APPLIES HERE TOO. All five of those alphas hold long 0 / short 0 from 2014 to
    2020 -- seven years of nothing -- and a gem that does not trade for 70% of its own backtest is
    not a gem. The filter was in `pick()` only, which guarded the baseline and not the ledger.
    """
    measured = measured_corr() if measured is None else measured
    known = ledger_alphas()
    got = []
    for r in rows:
        if tier(r, measured) != 4:
            continue
        aid = r.get("alpha")
        if not aid or aid in known:
            continue
        if year_book:
            ok, _why = year_book_ok(aid, session=session)
            if not ok:                       # False or None -- UNKNOWN is never a gem
                continue
        known.add(aid)
        got.append(r)
    if not got:
        return 0
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        for r in got:
            fh.write(json.dumps({
                "cycle": cycle, "alpha": r.get("alpha"), "formula": r.get("formula"),
                "sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
                "turnover": r.get("turnover"), "margin": r.get("margin"),
                "settings": r.get("settings"), "found_at": time.time(),
                # Every warning is recorded even though the informational ones do not block. A gem
                # row that hid them would be the same defect that nearly published 6 false gems.
                "warnings": warned_checks(r),
                "prod_corr": (measured.get(r.get("alpha")) or {}).get("prod"),
                "self_corr": (measured.get(r.get("alpha")) or {}).get("self"),
                "year_book": year_book_ok(r.get("alpha"))[1],
                "note": ("TIER 4: cleared the screen, every scored gate, AND has a MEASURED "
                         "prod/self correlation under both lines (prod < %.2f, self < %.2f). "
                         "Informational warnings, if any, are listed above -- whether any of them "
                         "blocks a submission is UNKNOWN here. The SELF line is an ASSUMPTION, not "
                         "a measurement. NOT SUBMITTED -- the irreversible POST is Khoa's decision."
                         % (PROD_CORR_MAX, SELF_CORR_MAX)),
            }) + "\n")
    return len(got)


#: Where a "best alpha right now" is looked for. The climb's own journal first, then the recovered
#: rows, then any other run journal -- an alpha that cost quota counts whichever experiment produced
#: it, and a report that only knew about the current loop would understate what we actually hold.
BEST_GLOBS = ("state/layered/runs/climb.jsonl",
              "state/layered/runs/recovered.jsonl",
              "state/layered/runs/fw_*.jsonl",
              "state/layered/runs/gap_*.jsonl",
              "state/layered/runs/climb_*.jsonl")


#: Anything that is not a field id: operator names, group names, and bare numbers.
_NOT_A_FIELD = set(LA.GROUPS) | {"close", "open", "vwap", "high", "low", "volume", "returns", "cap"}


def leaf_fields(formula):
    """The set of DATA FIELDS a formula reads, ignoring operators, groups and numbers.

    A token is a field when it is followed by something other than "(" -- an operator is always
    followed by its open paren, a field never is.
    """
    if not formula:
        return frozenset()
    out = set()
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*(\()?", formula):
        name, paren = m.group(1), m.group(2)
        if paren or name in _NOT_A_FIELD:
            continue
        out.add(name)
    return frozenset(out)


def stale_gems(path=None, prod_max=PROD_CORR_MAX, self_max=SELF_CORR_MAX):
    """Gem rows whose STORED correlation no longer matches the newest reading.

    `gems.jsonl` is written once and never revisited, so a row keeps the numbers an alpha had at
    the moment it qualified. The live gate is fine -- `tier(measured=measured_corr())` reads the
    newest value and rejects these -- but the LEDGER is what a human reads, and on 2026-08-16 two
    of seven rows were advertising correlations that had since moved:

        gJ8dZqav   stored 0.5056 / 0.2142   ->  measured 0.9288 / 0.9288
        npNQP123   stored 0.5570 / 0.2283   ->  measured 0.9204 / 0.9204

    Both are far over both lines. An operator reading the ledger would have submitted an alpha the
    platform was going to refuse, and a 403 spends that alpha permanently. This is the same disease
    as the 596 false gems -- a value captured once and then trusted forever.

    Returns [{alpha, stored, latest, over_line}], newest reading wins.
    """
    ledger = pathlib.Path(path or LEDGER)
    if not ledger.exists():
        return []
    measured = measured_corr()
    out, seen = [], set()
    for line in ledger.read_text(errors="ignore").splitlines():
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        aid = r.get("alpha")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        m = measured.get(aid) or {}
        np_, ns = m.get("prod"), m.get("self")
        if not isinstance(np_, (int, float)) or not isinstance(ns, (int, float)):
            continue
        sp, ss = r.get("prod_corr"), r.get("self_corr")
        drift = max(abs((sp if isinstance(sp, (int, float)) else 0) - np_),
                    abs((ss if isinstance(ss, (int, float)) else 0) - ns))
        if drift <= 0.02:
            continue
        out.append({"alpha": aid, "stored": (sp, ss), "latest": (np_, ns),
                    "over_line": np_ > prod_max or ns > self_max})
    return out


def candidate_reps(objective=OBJECTIVE, globs=None, root=ROOT):
    """(representatives, total) -- one candidate per distinct SIGNAL, best by `objective`.

    Khoa, 2026-08-14: "ko đo toàn bộ 709 gem vì trong đó có nhiều alpha là duplication của nhau nên
    đo nhiều cũng là vô ích". He is right, and it is structural rather than incidental: a hill climb
    grows ONE baseline, so consecutive rounds differ by a single wrapper and read the same data. A
    correlation probe on the 40th reshape of a baseline answers the same question as the 1st.

    Signals are separated by the SET OF DATA FIELDS the formula reads. Two alphas over the same
    fields are the same signal wearing different operators; two over different fields are not.
    MECHANISM: this is a structural proxy, not a measurement -- the project already has a real one
    (`pnl-distance-predicts-self-corr`: self-corr = 0.0662 + 0.9675 * pearson(daily pnl), +/-0.022),
    but that needs a PnL fetch per alpha, which is the very cost this dedup exists to avoid.
    """
    # THE QUEUE MUST EXCLUDE WHAT HAS ALREADY BEEN MEASURED.
    #
    # This called tier(r) with no probe log. tier(m, measured=None) can never return 4, so an alpha
    # whose correlations were measured days ago still answers 3 and stays queued forever. Measured
    # 2026-08-16: the series `candidates 878 -> signals 111` was byte-identical across twelve
    # consecutive rounds; 23 of the 111 representatives already held readings and FIVE were gems
    # sitting in the ledger. The loop paid a >=900 s wait to re-measure them, forty times.
    #
    # Same defect, same day, as best_line() calling tier(b) without the probe log. I fixed that one
    # call site and did not grep for the others.
    try:
        _meas = measured_corr()
    except Exception:                              # noqa: BLE001 - never let this empty the queue
        _meas = None
    rows = [r for r in _journal_rows(globs, root)
            if tier(r, measured=_meas) == 3 and r.get("alpha")]
    by_alpha = {}
    for r in rows:
        by_alpha[r["alpha"]] = r
    best = {}
    for r in by_alpha.values():
        key = leaf_fields(r.get("formula"))
        v = metric(r, objective)
        if not isinstance(v, (int, float)):
            continue
        if key not in best or v > (metric(best[key], objective) or -9e9):
            best[key] = r
    reps = sorted(best.values(), key=lambda r: -(metric(r, objective) or 0))
    return reps, len(by_alpha)


def _journal_rows(globs=None, root=ROOT):
    """Every journalled row, from the same globs the best-alpha lookup reads."""
    import glob as _glob
    out = []
    for pat in (globs or BEST_GLOBS):
        for path in _glob.glob(str(root / pat)):
            for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
                if line.startswith("{"):
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    return out


def best_alpha(objective=OBJECTIVE, globs=BEST_GLOBS, root=ROOT, require_band=True,
               reject_checks=("CONCENTRATED_WEIGHT",), only_fields=None):
    """The single best row we hold right now, by `objective`.

    Khoa, 2026-08-14: every Discord notification must name the best alpha at the moment it is sent.
    A status line without it says how the machine is doing and not what it has produced, and those
    are different questions.

    `require_band` KEEPS DEGENERATES OFF THE HEADLINE, and it is not cosmetic. Two real cases, both
    found within minutes of first running this on the VPS:

      * sharpe 25.18 / fitness 35.43 at **turnover 1.000** -- turns the whole book over daily.
      * sharpe 6.64 / margin 601 bps at **book 0 long / 0 short** -- holds nothing at all, and it
        PASSED the sharpe/fitness/turnover screen, which is exactly why the screen alone is not a
        safe headline filter.

    Neither can be submitted at any sharpe, so putting either at the top of every message would
    announce a number that means nothing. Both are excluded and COUNTED, never silently dropped:
    the count is printed, so the filter is visible.

    `reject_checks` MATCHES THE BASELINE RULE. Khoa ruled that a baseline failing
    CONCENTRATED_WEIGHT is passed over; an alpha that cannot be a baseline should not be announced
    as our best either. The standing headline was sharpe 1.82 / fitness 1.80 on `book 4 long / 4
    short`, failing CONCENTRATED_WEIGHT -- an eight-name book reported as the best thing we hold,
    while twenty real screen-passers on books of 660 names sat below it.

    Rows without the objective are skipped, never scored as zero -- an ERROR row with no fitness
    must not win by default in a field of negatives.

    Returns (best_row, n_excluded).
    """
    import glob as _glob
    lo, hi = SCREEN_TURNOVER
    measured = measured_corr()
    best, excluded = None, 0
    for pat in globs:
        for path in _glob.glob(str(root / pat)):
            for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
                if not line.startswith("{"):
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                v = metric(r, objective)
                if not isinstance(v, (int, float)) or not r.get("formula"):
                    continue
                if only_fields is not None and not (leaf_fields(r["formula"]) <= only_fields):
                    continue          # uses a field the current pool can no longer draw
                if require_band:
                    tv = r.get("turnover")
                    lcv, scv = r.get("longCount"), r.get("shortCount")
                    dead = (isinstance(lcv, int) and isinstance(scv, int) and lcv + scv == 0)
                    if dead or not isinstance(tv, (int, float)) or not (lo < tv < hi):
                        if best is None or v > (metric(best, objective) or -9e9):
                            excluded += 1
                        continue
                if reject_checks:
                    fails = failing_checks(r)
                    if fails and any(c in fails for c in reject_checks):
                        if best is None or v > (metric(best, objective) or -9e9):
                            excluded += 1
                        continue
                # A MEASURED correlation over its line disqualifies the headline too. The first
                # alpha this caught was `88pYR1gz`, which the headline was calling our best while
                # its prod correlation was 1.0 -- a perfect duplicate of something already in the
                # production book, the worst possible value on the gate that actually refuses.
                corr = (measured or {}).get(r.get("alpha") or "", {})
                if (isinstance(corr.get("prod"), (int, float)) and corr["prod"] >= PROD_CORR_MAX) \
                        or (isinstance(corr.get("self"), (int, float))
                            and corr["self"] >= SELF_CORR_MAX):
                    if best is None or v > (metric(best, objective) or -9e9):
                        excluded += 1
                    continue
                if best is None or v > metric(best, objective):
                    best = r
    return best, excluded


def both_lines(objective="sub_sharpe", **kw):
    """TWO NUMBERS, because they answer different questions and conflating them misleads.

    The headline had been reporting the best alpha in every journal -- which after the pyramid gate
    and the coverage floor includes alphas built from fields the pool can no longer draw. That is
    still the best thing we HOLD, and it is honest to say so, but it is not what the pipeline can
    still produce, and reading it as the latter is how a shrinking search space stays invisible.
    """
    held = best_line(objective, **dict(kw, label="best alpha we HOLD"))
    pool = reachable_fields()
    if not pool:
        return held + "\n\n(reachable-now unavailable: the field catalogue could not be read)"
    now = best_line(objective, **dict(kw, label="best REACHABLE from today's pool",
                                      only_fields=pool))
    return held + "\n\n" + now


def reachable_fields(root=ROOT):
    """The field ids the CURRENT pool can still draw. Empty set if the catalogue cannot be read --
    the caller then reports nothing rather than guessing."""
    try:
        import layered_alpha as _LA
        return {f["id"] for f in _LA.load_fields()}
    except Exception:                                  # noqa: BLE001 - a report must still go out
        return set()


def tier4_label(b):
    """Never assert a negative you did not check.

    The old label read "tier 4 — GEM, not submitted" unconditionally. It never consulted the
    submitted ledger, and one tier-4 alpha in this very population is ACTIVE on the platform -- so
    five of the seven loop messages affirmatively described a burned alpha as available. When the
    ledger cannot be read, the claim is OMITTED rather than softened: an unreadable ledger is not
    evidence of an empty one, and this ledger lives only on the machine that POSTs.
    """
    try:
        import climb_submit as CS
        ids, readable = CS.submitted_ids()
    except Exception:                              # noqa: BLE001 - a report must still go out
        return "tier 4 — GEM (sổ đã nộp: không đọc được)"
    if not readable:
        return "tier 4 — GEM (sổ đã nộp: không đọc được trên máy này)"
    aid = b.get("alpha") or b.get("id")
    if aid and aid in ids:
        return "tier 4 — GEM, ĐÃ NỘP (slot đã tiêu)"
    return "tier 4 — GEM, chưa có trong sổ đã nộp"


def best_line(objective="sub_sharpe", **kw):
    """The best alpha as a short block for a Discord message. Never raises: a notification that
    fails because the best-alpha lookup broke is worse than a notification without it."""
    label = kw.pop("label", "best alpha now")
    try:
        b, excluded = best_alpha(objective, **kw)
    except Exception as exc:                       # noqa: BLE001 - a report must still go out
        return "best alpha: lookup failed (%s: %s)" % (type(exc).__name__, exc)
    if not b:
        return ("best alpha: none yet — no row inside the turnover band carries a %s "
                "(%d higher-scoring row(s) excluded as out-of-band)" % (objective, excluded))

    def g(k):
        v = b.get(k)
        return "%.3f" % v if isinstance(v, (int, float)) else "--"

    # MARGIN IN BPS, not in raw units. At 3 decimals the raw number prints as 0.000 for every alpha
    # that has ever existed here, which is worse than omitting it. Bps is also the unit S2's bar is
    # stated in: fitness >= F <=> margin >= F^2/(500*sharpe^2), which is 8.01 bps at F=1, sharpe 1.58.
    mv = b.get("margin")
    marg = ("%.2f bps" % (mv * 1e4)) if isinstance(mv, (int, float)) else "--"

    # WHAT THE FITNESS BAR REQUIRES OF THIS ALPHA -- and the first version of this line was WRONG.
    # It printed `1e4/(500*sharpe^2)`, which drops the `max(turnover, 0.125)` floor inside the
    # fitness identity. Two agents re-derived it independently and agree to the digit: the bar is
    # understated on 61.6% of in-band climb rows (3,186 of 5,171), median factor 2.066, and on the
    # wider journal set 64.9% (9,490 of 14,630), median 2.00x, max 12.38x. On the live headline it
    # printed 1.53 bps where the true bar is 2.30.
    #
    #   turnover >= 0.125   turnover cancels      M >= F^2 / (500 * s^2)
    #   turnover <  0.125   the floor blocks it   M >= F^2 * 0.125 / (500 * s^2 * T)
    #
    # The correction factor max(1, 0.125/T) is never below 1, so the old line could only ever
    # UNDERSTATE the bar -- it made every alpha look further past the gate than it was. 346 of
    # 14,555 in-band rows (2.38%) clear the printed bar and fail the true one.
    #
    # F is left at 1.0 deliberately: all six segments in `pool_gate.ROTATION` are delay 1, where F
    # is 1.0 (EUR measured n=90, CHN documented). The 1.3/1.5 limits are delay-0 only, and no
    # delay-0 segment is in the rotation. If one is ever added this line must read F from the row's
    # own LOW_FITNESS limit.
    sv, tv = b.get("sharpe"), b.get("turnover")
    if isinstance(sv, (int, float)) and sv and isinstance(tv, (int, float)) and tv > 0:
        need = "%.2f bps" % (1e4 / (500 * sv * sv) * max(1.0, 0.125 / tv))
    else:
        need = "--"

    screen = "PASS" if screened(b) else "no"
    # tier(b) WITHOUT the probe log can NEVER return 4, so this headline printed "corr UNMEASURED"
    # while nine measured tier-4 alphas sat in the probe log the whole time. The lookup must not be
    # able to break a notification, so a failure degrades to the unmeasured answer rather than
    # raising.
    try:
        _meas = measured_corr()
    except Exception:                              # noqa: BLE001 - a report must still go out
        _meas = None
    t = tier(b, measured=_meas)
    tname = {1: "tier 1", 2: "tier 2",
             3: "tier 3 — corr UNMEASURED, not a gem",
             4: tier4_label(b)}[t]
    # WHAT FAILED, AND HOW BIG THE BOOK IS. "screen PASS · tier 2" without naming the failing check
    # is the kind of half-information that misleads: the first VPS row to reach it showed sharpe
    # 6.64 and margin 601 bps, numbers that only happen on a book of a few names. A reader who is
    # told the screen passed and not what blocked it will read it as a near-gem.
    fails = failing_checks(b)
    if fails is None:
        why = "checks not scored"
    elif fails:
        why = "fails " + ", ".join(sorted(fails)[:4])
    else:
        why = "no failing check"
    lc, sc = b.get("longCount"), b.get("shortCount")
    book = ("book %s long / %s short" % (lc, sc)
            if isinstance(lc, int) and isinstance(sc, int) else "book unknown")

    return ("**%s** (by %s)\n"
            "%s %s | sharpe %s | fitness %s | turnover %s\n"
            "margin %s (fitness 1.0 needs %s at this sharpe)\n"
            "screen %s · %s%s\n"
            "%s · %s\n"
            "`%s`"
            % (label, objective, b.get("alpha") or "(no id)", b.get("status") or "",
               g("sharpe"), g("fitness"), g("turnover"), marg, need,
               screen, tname,
               (" · %d higher-scoring row(s) excluded: empty book, turnover outside %.2f-%.2f, "
                "failing CONCENTRATED_WEIGHT, or a measured correlation over its line"
                % (excluded, SCREEN_TURNOVER[0], SCREEN_TURNOVER[1])) if excluded else "",
               why, book,
               (b.get("formula") or "")[:300]))


def report(st):
    seg = st.get("segment") or ["USA", "TOP3000", 1]
    lines = ["cycle %s, round %s, baseline score %s, depth %s, segment %s/%s/d%s, "
             "%d gemless cycle(s) in a row (rotate at %d)"
             % (st.get("cycle"), st.get("round"), st.get("baseline_score"), st.get("depth", 1),
                seg[0], seg[1], seg[2], st.get("gemless_streak", 0), GEMLESS_BEFORE_ROTATE)]
    # A STALE GEM ROW IS A TRAP, SO IT GOES AT THE TOP.
    # The ledger stores the correlation an alpha had when it qualified and never revisits it. Two
    # of seven rows were advertising numbers that had since crossed both lines; submitting one is a
    # 403, which spends the alpha forever. The live gate rejects them, but the ledger is what a
    # person reads, and a person is who presses the button.
    try:
        bad = stale_gems()
    except Exception:                              # noqa: BLE001 - a report must still print
        bad = []
    for b in bad:
        lines.insert(0, "!! GEM LEDGER STALE: %s stored %.4f/%.4f but now measures %.4f/%.4f%s"
                     % (b["alpha"], b["stored"][0] or -1, b["stored"][1] or -1,
                        b["latest"][0], b["latest"][1],
                        "  -- OVER THE LINE, DO NOT SUBMIT" if b["over_line"] else ""))
    hist = st.get("history", [])
    if hist:
        lines.append("%-6s %-6s %-5s %6s %10s %10s %9s %6s %s"
                     % ("cycle", "round", "kind", "n", "best", "prev", "screened", "tier3",
                        "event"))
        for h in hist[-25:]:
            lines.append("%-6s %-6s %-5s %6s %10s %10s %9s %6s %s"
                         % (h.get("cycle"), h.get("round"), h.get("kind") or "-", h.get("n"),
                            _f(h.get("best_score")), _f(h.get("prev_baseline_score")),
                            h.get("screened"), h.get("tier3"), h.get("event")))
            # A SILENT FILTER is how a loop climbs the wrong hill for hours unnoticed. Every
            # candidate passed over for Khoa's two baseline rules is named here.
            if h.get("skipped"):
                lines.append("       skipped: %s"
                             % ", ".join("%s x%d" % (k, v)
                                         for k, v in sorted(h["skipped"].items())))
    if st.get("baseline"):
        lines.append("baseline: %s" % st["baseline"][:200])
    return lines


def _f(v):
    return "--" if not isinstance(v, (int, float)) else "%.4f" % v


#: A Discord body may not exceed this. Below the 2000 the platform enforces, so a brief that grows
#: is caught here rather than by a truncation marker in Khoa's chat.
BRIEF_MAX = 400


def brief(st, extra=None):
    """Three short lines: where the climb is, what it holds, what is queued.

    Khoa, 2026-08-17: "thông tin thì quá dài dòng, ko súc tích". The loop was piping
    `--report | head -20` into every notification -- the full cycle-history table, 2,835 characters
    of it, truncated at 1,900, and the one message that mattered (auth expired) did not even carry
    the link. A debug dump is not a message: the operator needs the fact and the action, and the
    history belongs in the log where it can be read at length.

    `extra` is the one line specific to the event that fired.
    """
    seg = st.get("segment") or ["USA", "TOP3000", 1]
    lines = []
    if extra:
        lines.append(extra)
    bench = st.get("phase_benchmark")
    tries = st.get("cycle_retries", 0)
    mark = "moc %s%s" % ("chua co" if bench is None else "%.2f" % bench,
                         "" if not tries else " · thu lai %d/%d" % (tries, CYCLE_RETRIES))
    lines.append("chu ky %s vong %s · diem %s · %s · sau %s · %s/%s/d%s · %s chu ky lien khong gem"
                 % (st.get("cycle"), st.get("round"), st.get("baseline_score"), mark,
                    st.get("depth", 1), seg[0], seg[1], seg[2], st.get("gemless_streak", 0)))

    # The best alpha, in one line. Khoa's standing requirement, and the reason it kept being cut is
    # that it sat at the end of a table instead of at the top of a sentence.
    try:
        b, _ = best_alpha("sub_sharpe")
    except Exception:                              # noqa: BLE001 - a message must still go out
        b = None
    if b:
        lines.append("tot nhat %s · sharpe %.2f · fitness %.2f · turnover %.3f"
                     % (b.get("alpha") or "?", b.get("sharpe") or 0.0,
                        b.get("fitness") or 0.0, b.get("turnover") or 0.0))
    else:
        lines.append("tot nhat: chua doc duoc")

    # A stale gem row is a trap and outranks everything else in the message.
    try:
        bad = [x for x in stale_gems() if x["over_line"]]
    except Exception:                              # noqa: BLE001
        bad = []
    if bad:
        lines.insert(0, "!! %d dong gem THIU da vuot nguong — DUNG NOP: %s"
                     % (len(bad), ", ".join(x["alpha"] for x in bad[:3])))

    out = "\n".join(lines)
    return out[:BRIEF_MAX]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brief", metavar="EVENT", nargs="?", const="",
                    help="one compact status for a chat message: the event, where the climb is, "
                         "and the best alpha. Never a table -- see brief().")
    ap.add_argument("--draw", type=int, metavar="N",
                    help="print N candidates for the current round and exit")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--list-candidates", action="store_true",
                    help="with --candidates, print the deduplicated representatives")
    ap.add_argument("--candidates", action="store_true",
                    help="count tier-3 rows whose correlations are still PENDING -- the queue a "
                         "correlation probe should read. Prints the count on the last line.")
    ap.add_argument("--rescore", action="store_true",
                    help="re-read every tier-3 candidate from the platform so freshly computed "
                         "correlation gates land in the journal, then write any that became gems")
    ap.add_argument("--on-gem", action="store_true",
                    help="what to do when a gem is found: re-read the pyramid, and END THE CYCLE if "
                         "the standing baseline uses a category that has just filled")
    ap.add_argument("--reset", action="store_true",
                    help="end the cycle and start over at round 1")
    ap.add_argument("--gems", type=int, default=0,
                    help="how many gems this cycle produced. A cycle that found one must NOT count "
                         "towards the gemless streak that triggers a segment rotation.")
    ap.add_argument("--both", action="store_true",
                    help="print BOTH the best alpha we hold and the best still reachable from "
                         "today's pool -- they answer different questions")
    ap.add_argument("--best", action="store_true",
                    help="print the best alpha we hold right now. Khoa: every Discord notification "
                         "must carry this.")
    ap.add_argument("--objective", default="sub_sharpe",
                    help="metric the argmax runs on. Fitness is a PLACEHOLDER (Khoa): the point of "
                         "this flag is that swapping it is a flag change, not a rewrite.")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()

    st = load_state()

    if a.brief is not None:
        print(brief(st, a.brief or None))
        return 0

    if a.candidates:
        reps, total = candidate_reps(objective=a.objective)
        print("tier-3 candidates with PENDING correlations: %d" % total)
        print("distinct SIGNALS among them: %d  (a climb emits many reshapes of one baseline; "
              "measuring every reshape spends the scarcest channel on the same answer)" % len(reps))
        if a.list_candidates:
            for r in reps[:40]:
                print("   %-10s fit %.2f  fields=%d  %s"
                      % (r.get("alpha"), r.get("fitness") or 0, len(leaf_fields(r.get("formula"))),
                         (r.get("formula") or "")[:90]))
        print(len(reps))
        return 0

    if a.rescore:
        # RE-READ, do not infer. The journal row was written before the probe ran, so its gates are
        # the OLD ones. A gem declared from a stale row is the same class of error as reading a
        # PENDING gate as a pass.
        import layered_sim as LS
        reps, total = candidate_reps(objective=a.objective)
        want = {r["alpha"]: r for r in reps}
        print("rescoring %d representative(s) of %d candidate(s)" % (len(want), total))
        if not want:
            print("nothing to rescore")
            return 0
        s = LS.session()
        fresh, moved = [], 0
        for aid, old in want.items():
            got = LS.scrape(s, aid)
            if not isinstance(got.get("checks"), list):
                continue
            row = dict(old)
            row.update(got)
            fresh.append(row)
            if tier(row) == 4:
                moved += 1
        print("rescored %d candidate(s); %d became gems" % (len(fresh), moved))
        if fresh:
            path = ROOT / "state/layered/runs/climb_rescored.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                for row in fresh:
                    fh.write(json.dumps(row) + "\n")
            write_gems(fresh, st.get("cycle", 1))
        return 0

    if a.on_gem:
        import pool_gate as PGATE
        counts, err = PGATE.refresh()
        if err:
            print("pyramid refresh FAILED (%s) -- counts left alone, nothing disabled" % err)
            return 0
        st2 = PGATE.state()
        print(PGATE.describe(st2))
        base = st.get("baseline") or ""
        if base and st2.get("ok"):
            # EVERY DESCENDANT of this baseline carries its fields, so if one of them sits in a cell
            # that has just filled, climbing on is spending quota on a branch that can no longer
            # advance any pyramid. Khoa's ruling: end the cycle.
            import layered_alpha as LA
            cat = {}
            for f in LA.load_fields(pyramid_gate=False, min_coverage=0.0):
                c = f.get("category")
                cat[f["id"]] = c.get("name") if isinstance(c, dict) else c
            used = {cat[t] for t in leaf_fields(base) if t in cat}
            dead = used & set(st2["disabled"])
            if dead:
                print("baseline uses NOW-FULL cell(s) %s -- ending the cycle"
                      % ", ".join(sorted(dead)))
                save_state(reset(st, gems=0))
                return 0
            print("baseline cells still open: %s" % ", ".join(sorted(used)) or "(none resolved)")
        return 0

    if a.reset:
        # THE GEM COUNT MATTERS AND WAS HARDCODED TO ZERO. The loop calls this after finding gems,
        # so every productive cycle was being counted as gemless -- which under the streak rule
        # would eventually rotate away from a segment that was actually working.
        st = reset(st, gems=a.gems)
        save_state(st)
        print("cycle reset -> cycle %s, round 0, no baseline, segment %s, gemless streak %d"
              % (st.get("cycle"), st.get("segment"), st.get("gemless_streak", 0)))
        return 0

    if a.both:
        print(both_lines(a.objective))
        return 0
    if a.best:
        print(best_line(a.objective))
        return 0
    if a.report:
        print("\n".join(report(st)))
        print()
        print(both_lines(a.objective))
        return 0

    if a.draw:
        ops = LA.load_operators()
        pool_a, pool_b, _d = LA.split_layers(ops)
        rng = random.Random(a.seed if a.seed is not None else int(time.time()))
        pool_c = LA.build_pool_c(LA.load_fields(), rng=random.Random(0))
        for f, m in draw(st, pool_a, pool_b, pool_c, rng, a.draw):
            print(json.dumps({"formula": f, "meta": m}))
        return 0

    print("\n".join(report(st)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
