"""forge.offline.benchmark — the pipeline scorecard of record (docs/evalharness/00_agreements.md).

Khoa's /goal asks one question in three parts, and this module answers exactly those three:
  AXIS 1  the PRODUCT -- is the alpha good, robust, and trustworthy, with OS never observable?
  AXIS 2  the THROUGHPUT -- four a day? how many scored alphas per submission? sustainable or luck?
  AXIS 3  the GEARING -- can branches be grown onto this pipeline, or is it a dead end?

DRAW 2 (docs/evalharness/01_architecture.md), after adversarial round 1 found the composite unable to
rank, axis 1 structurally zero, axis 2 in the wrong unit and the pre-merge gate grading the journal
instead of the diff. What changed in structure:
  * `build_from()` is PURE -- rows, scores, curves, the deploy ledger and the clock in; a card out.
    `build()` only reads files and the wall clock. So the scorer can be run on a FROZEN fixture and
    pinned by a golden card (tools/ci_gate.py).
  * `compare()` judges a VERSION after it has run, on cohorts stamped with meta.pipeline_version.
  * Days are ET QUOTA days (the platform resets at 00:00 America/New_York), whole days only.

AFTER ROUND 2 (docs/evalharness/audits/architecture_round2.md; Khoa's D24 and D25, 2026-09-23):
  * THE RANKING (D25; F4-NL, A6). The 0-100 composite is gone, and with it WEIGHT and UNPROVEN_CREDIT.
    Round 2 measured it FALLING when clean output was added (P 32.8 against P+P+P+R 28.3), bunching
    every passing card into [50, 52.5], and flipping rankings at UNPROVEN_CREDIT = 0.474. Versions are
    ranked LEXICOGRAPHICALLY with no weight and no constant: rank_key().
  * CLEAN MEANS PROVEN (A5). A submission counts as clean throughput, and toward any floor, only when
    every axis-1 gate was MEASURED and passed. "Unproven" is reported beside it and never counted: a
    missing measurement used to move an alpha only toward clean, so not measuring paid.
  * EXPOSURE AND CENSORING (A3, A4). A version card's days are the days the deploy ledger says the
    version was running, or "exposure unknown"; a POST counts only within POST_HORIZON_DAYS of the
    alpha's creation; the clock is an argument, never read inside.
  * THE POST-DEPLOY COMPARISON (D24; A1). compare() judges a pre-registered, higher-frequency estimand
    (ESTIMAND) with an exact test and says what size of change the exposure could have detected.
  * PROVENANCE (S10-NL). Every card says when it was graded, by which scorer bytes, on what inputs.

AFTER THE DRAW-3 BUILD AUDIT (docs/evalharness/audits/draw3_build.md, scoring section):
  * EXPOSURE IS FOR THE RATE ONLY (SERIOUS 1). Axis 1 and rank level 1 grade EVERY stamped row created on
    a whole ET quota day in [since, last), `last` being the earliest of `until`, the unfinished day and the
    day the data was cut on (draw3_fix scoring 11: this said "before the last whole day"); the deploy
    ledger's live days feed only axis 2's rate. Passing the ledger used to hide a refutation made on a
    deploy day, and zero live days read as a MEASURED rate of 0.0.
  * THE DATA'S OWN CUT (SERIOUS 4). build() passes the journal copy's mtime as `data_through`; the quota
    day it falls in is treated exactly like the unfinished day. The card prints the requested window and
    the effective one.
  * THE CELL MIX (SERIOUS 6). compare() prints per-cell k/n and flags a cell mix that differs between the
    arms. Since D28 (below) the mix no longer withholds a verdict: the verdict is taken WITHIN cell.
  * Every threshold is a named constant with its origin stated, or the statement that none is known.

AFTER THE DRAW-3 FIX AUDIT (docs/evalharness/audits/draw3_fix.md, scoring) AND KHOA'S D26-D30, D39, D41:
  * SEEN UNTIL (D27; draw3_fix scoring 1). Every "is the POST horizon closed" judgement reads
    seen_until = min(now, data_through), never `now` alone: a journal copy cut 09-15 and graded 09-30 used to
    read its horizon final, and a next window with no POST yet read held False.
  * THE RANK (D29, D26, D27). Key = (verdict PASS before FAIL, REFUTED + UNPROVEN submitted, proven clean
    per quota day, axis 3). rank_key / rank_cmp REFUSE (NotComparable) a card whose POST horizon is not
    final at seen_until; the card prints the ET date from which it is comparable.
  * WITHIN CELL (D28). compare() decides on an exact test stratified by cell, and better/worse needs every
    cell with an event to point the same way; the pooled numbers are printed and never decide.
  * COHORTS (D30). A cohort is (meta.pipeline_version, meta.run_config); a suffixed or marker stamp never
    forms one; the deploy ledger joins on pipeline_version only.
  * GENERATED ALPHAS (D39). A `gen:` alpha takes D10's gate half from state/forge/meaning.jsonl.
  * THE CARD LEDGER (D41). --record appends at most one card per (cohort, graded ET day, host).

AFTER THE DRAW-4 BUILD AUDIT (docs/evalharness/audits/draw4_build.md, scoring 1-6 and pipeline P2), ROUND 3
(docs/evalharness/audits/architecture_round3.md F1, S8, S10) AND KHOA'S D45, D47, D49:
  * WATCH ROWS ARE NEVER DEPLOYS (scoring 1; tools/deploy.py DEPLOY_LOG, WATCH ROWS). live_days() and dora()
    read a watch_rolled_back as the previous pipeline put back and a change failure of the push it names;
    watch_ok, watch_timeout and watch_not_rolled_back leave the running version as it was.
  * A COHORT'S EXPOSURE (D45; scoring 2). A (pipeline_version, run_config) cohort's live days are the
    pipeline_version's live days on which state/forge/run_config_log.jsonl records that run_config for the
    whole day (cohort_live_days); days before the log's first row for the cohort read "exposure unknown".
  * A MARKER RUN_CONFIG FORMS NO COHORT (scoring 3, pipeline P2), exactly as a marker pipeline_version never did.
  * LATE POSTS (D49; round 3 S1). Every accepted POST of a graded alpha counts against rank level 1 whatever its
    lag; POST_HORIZON_DAYS bounds credit (axis 2) and finality only.
  * THE ARMS (D47; round 3 F1). compare_arms() reads the proof: rounds randomised within each ET day between
    meta.arm "composites" and "gen", compared by an exact test conditioned on every (day, cell) -- the alpha-unit
    test D54 replaced (below). compare() stays
    for version against version and states on its face that it is not RULE 2 gate-3 evidence.
  * THE MEANING ROW (round 3 S8). The row whose formula_sha is the sha256 of the alpha's own formula, scored
    earliest after the alpha was created and by `now`, decides; no longer the latest row of any formula.
  * THE JOURNAL IS STREAMED (round 3 S10, the reader's half): read_journal() keeps the last row per alpha,
    reduced to the fields a card reads.
  * A RECORDED CARD NAMES ITS COHORT, and recording never asks whether the card can be ranked (record_card).

AFTER ROUND 4 (docs/evalharness/audits/architecture_round4.md F1, S1-S3, S5) AND KHOA'S D54-D57, D60 (2026-09-24):
  * THE ROUND IS THE UNIT (D54; F1). compare_arms() compares rounds, not alphas: each randomised round contributes
    its D24 rate per cell, and the test permutes arm labels across the rounds of each ET day. Only rounds the
    randomiser assigned count (meta.arm_by "randomiser"); in the branch only fresh generator draws (meta.gen_route
    "fresh") enter the estimand, and D51 neighbour and D37 repair rows are reported beside it (draw5 scoring S1).
  * A GROUP-SEQUENTIAL READ-OUT (D55; S1). Looks at 7, 14, 21 and 28 shared days, O'Brien-Fleming boundaries at a
    total two-sided 0.05; a verdict only across a boundary. Reading the card daily adds no look.
  * EXCLUDED ROUNDS ARE COUNTED (D60; S3): every round of the version outside the comparison, and why.
  * PBO "insufficient" ON A GENERATED POOL IS NOT APPLICABLE (D56; S5): printed UNMEASURED, never counted.
  * LEVEL 1 AT EQUAL LAG (D57; S2): rank_cmp counts level-1 POSTs within the same post-creation lag on both cards.

THE SCORING FRAME (D2, unchanged by D25). Each axis carries a HARD FLOOR; failing any floor is a FAIL,
whatever the others score. The rank orders versions and never turns a FAIL into a PASS.

WHAT IS GRADED (D14, "ko dựa trên dữ liệu cũ"): the rows the graded version produced. With a version
id, by the cohort (`meta.pipeline_version`, `meta.run_config`) (D30); without one, by the ET quota-day
window, labelled WEAK.

THE DENOMINATOR: rows scored = distinct alpha ids carrying a check set with status COMPLETE or WARNING
(round 1: WARNING rows are 16 % of the journal and include the first ACTIVE submission). No sim-slot
ledger exists to convert scored alphas into quota spent.
"""
from __future__ import annotations

import ast
import collections
import datetime
import hashlib
import json
import math
import operator
import pathlib
import socket
import statistics
import sys
import zoneinfo

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import harvest as HV, submit as SUB  # noqa: E402

ET = zoneinfo.ZoneInfo("America/New_York")
SCORED_STATUS = ("COMPLETE", "WARNING")
BINDING = ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE",
           "CONCENTRATED_WEIGHT", "HIGH_TURNOVER", "LOW_TURNOVER")
DAY_S = 86400.0

# ----------------------------------------------------------------------------- the floors (D6, D2)
#: Khoa chose ABSOLUTE floors from the goal (D6). The best measured rate is ~0.5 submissions per quota
#: day; the axis-2 floor is 4. Every card reads FAIL for a long time -- the floor states the goal, the
#: rank orders attempts. Changing any number here changes the pinned golden card (tools/ci_gate.py).
FLOOR = {
    "axis1_product": 1.00,      # every submitted alpha PROVEN: every robustness gate measured and passed
    "axis2_throughput": 4.0,    # PROVEN clean submissions per ET quota day (A5: unproven never counts)
    # S4-NL: at 0.80 one check in seven could fail, and both draw-2 Actions runs printed "[NO] a real
    # branch goes through the planner" beside "AXIS 3 GEARING FLOOR MET 6 of 7". Every measured check
    # must hold; a check that could not be measured is reported and not counted (axis3_gearing).
    "axis3_gearing": 1.00,
}
#: D25 (Khoa, 2026-09-23): the levels versions are ranked on after the verdict, most important first. No
#: weights. D26 (Khoa, 2026-09-23 ~15:30): level 1 counts REFUTED + UNPROVEN submitted alphas, and is named
#: for what it counts -- at "refuted_submitted", an alpha whose neighbours were never measured cost nothing
#: while the same alpha measured as fragile cost a place (draw-3 scoring SERIOUS 2: rank_cmp(unmeasured,
#: measured) = -1), so not measuring paid.
RANK_ORDER = ("refuted_or_unproven_submitted", "proven_clean_per_quota_day", "axis3_held_fraction")
#: D29 (Khoa, 2026-09-23 ~15:45): the verdict leads the rank -- the full key is (verdict, *RANK_ORDER).
#: Before it a FAIL card could rank above a PASS card, against D2 ("floors first, then score"). A card
#: carrying no verdict ranks below FAIL.
VERDICT_ORDER = {"PASS": 0, "FAIL": 1}
#: DORA thresholds, REPORTED on a card and never scored (A9). The "high performer" band of Forsgren,
#: Humble & Kim, Accelerate (2018) and the State of DevOps report of the same series. EX-ANTE, taken
#: from the literature, not fitted here.
DORA_BAND = {"change_failure_rate_max": 0.15, "time_to_restore_hours_max": 24.0, "deploys_per_week_min": 1.0}

#: A4: a POST is credited to the alpha's cohort only when it lands within this many days of the alpha's
#: creation, the same horizon for every card and both arms of a comparison, and a POST-based number is
#: final only once the horizon has elapsed for the cohort's newest day. Round 2 measured two IDENTICAL
#: cohorts reading 1.714/day against 0 ("worse") because the newer one's POSTs had not happened yet.
#: THE VALUE IS A CONVENTION, NOT A MEASUREMENT, chosen 2026-09-23 AFTER the four creation-to-POST lags
#: were seen (POST-HOC, N = 4: 0.01, 0.77, 0.02 and 11.49 days, the last rK5RGeqa, reason UNKNOWN);
#: 14 keeps all four. Nothing measured says how long a submittable alpha stays submittable. A longer
#: horizon credits more late POSTs and delays every final number by the same amount.
POST_HORIZON_DAYS = 14

#: S3-NL: a third of an alpha's history is WINNING only when its mean daily PnL change is above zero by
#: more than this many standard errors, LOSING only when below zero by more than this many, and FLAT
#: otherwise. THIS MODULE'S OWN EX-ANTE CONVENTION, chosen by the draw-3 builder: ~2 is the two-sided
#: 95 % normal quantile (1.96) rounded. Round 2's fix (architecture_round2.md S3-NL) asks for a judgement
#: against the standard error and states NO number (draw-3 scoring MINOR: the comment used to attribute
#: 2.0 to round 2). It assumes serially independent daily changes, which is UNMEASURED for these curves;
#: positive autocorrelation would make the SE too small and call thirds winning or losing too often.
#: Open for Khoa (RULE 2); printed on every card (open_ticks).
REGIME_SE_MULTIPLE = 2.0

# ------------------------------------------------------------------ axis 1's thresholds, by name
# Draw-3 scoring MINOR: these five lived INLINE, so tools/ci_fixture.py could pin them only by a case on
# each side. Each is named here with where its number comes from, or the statement that nothing does.

#: A submitted alpha's Deflated Sharpe Ratio must be at least this. EX-ANTE convention: Bailey & López de
#: Prado (JPM 2014) read DSR as a probability, and 0.95 is the conventional 95 % level; it is the same
#: number as the loop's own candidate gate (forge/score.py DSR_MIN), held here as a separate constant so
#: the judge does not move when the loop's gate does. DSR >= 0.95 does NOT establish that an alpha is not
#: overfit (docs/evalharness/00_research.md, "what DSR does NOT prove").
DSR_MIN = 0.95
#: Neighbourhood stability: the median Sharpe of the alpha's true one-setting neighbours must retain at
#: least this share of its own Sharpe. ORIGIN UNKNOWN: no document under docs/evalharness states 0.5
#: (searched 2026-09-23), and nothing measured links it to out-of-sample behaviour. Round 1 (S2)
#: recommended judging the neighbours in standard-error units rather than by a ratio; not done here.
NEIGHBOUR_RETENTION_MIN = 0.5
#: Fewer true neighbours than this is UNMEASURED, never a pass or a fail. A CONVENTION: one neighbour's
#: Sharpe is its own median, so two is the smallest count whose median is not a single draw; no
#: measurement chose it.
NEIGHBOURS_MIN = 2
#: A PnL curve shorter than this many points is UNMEASURED for the regime gate. A CONVENTION (about 100
#: daily changes per third); no measurement chose it.
CURVE_POINTS_MIN = 300
#: A correlation reading must be STRICTLY under its line: a reading AT the line fails. EX-ANTE (code):
#: this mirrors the submitter, which holds a candidate when `prod >= pl or self_ >= sl`
#: (forge/submit.py eligible()) and re-checks `fresh["prod"] < pl` before a POST (forge/submit.py main()). Whether
#: the platform's own check is strict: UNKNOWN (not measured).
CORR_UNDER_LINE = operator.lt

#: D24 (Khoa, 2026-09-23 ~13:25), PRE-REGISTERED. Fixed in this file BEFORE any two versions were
#: compared on it. Changing any field after a comparison has been read is the post-hoc choice RULE 0
#: forbids: an edit here is a NEW estimand, and every earlier comparison must be re-run on it, never
#: re-read. Why this and not the submission count (A1): at 0.211 clean submissions per quota day a version
#: that produces NOTHING is flagged "worse" after 7 days with probability 2.4e-5.
#:
#: WHY NO COMPARISON CAN HAVE BEEN READ, per journal copy (draw-3 scoring SERIOUS 5: this comment used to
#: say a bare "0 of 32,662", which was true of one copy only):
#:   * the MacBook's copy of state/layered/runs/forge.jsonl, mtime 2026-09-22T16:05:13-04:00, newest
#:     dateCreated 2026-09-22T16:04:03-04:00: 0 of its 32,662 alpha ids carry meta.pipeline_version;
#:   * the VPS journal, read-only 2026-09-23 ~04:30 ET: 1,198 alpha ids are stamped, all with the ONE
#:     value ec6a5cd75d58fea2 (the adjudicator had read 740 earlier). compare() needs two stamped
#:     versions, so none could be run on either machine. Re-read read-only 2026-09-23 06:47 ET by the
#:     draw3_fix scoring engineer: 2,606 stamped ids, still the one value, none carrying meta.run_config --
#:     one cohort (D30), so still no comparison.
#:
#: D28 (Khoa, 2026-09-23 ~15:30) CHANGED `test` below from the pooled conditional test to the same test
#: stratified by cell, and added `stratum` and `decides`. Per 00_agreements.md it was changed BEFORE any
#: comparison was run; the one-cohort read just above is the measurement that says none could have been.
#:
#: THE EVENT COUNT, RE-COUNTED 2026-09-23 (draw-3 scoring MINOR: this comment said 37 and D24 says 34):
#:   Mac copy above ........ COMPLETE+WARNING 37 of 32,656 scored | COMPLETE only 34 of 27,350
#:   VPS, ~04:30 ET ........ COMPLETE+WARNING 37 of 35,763 scored | COMPLETE only 34 of 30,277
#: The gap is exactly three WARNING rows, all created 2026-09-04: vRk095rv (the first ACTIVE submission),
#: qMWbdlmv and ZY0Zowe1. This estimand counts WARNING rows (round 1 F3, SCORED_STATUS). MEASURED: counting
#: COMPLETE rows only gives 34 on both machines. NOT ESTABLISHED: that D24's 34 was counted that way. Its
#: source, docs/evalharness/02_funnel_baseline.md (VPS, 2026-09-22 23:35), gives a denominator of 25,743,
#: which no definition I tried reproduces: on the VPS journal, COMPLETE rows with a check set, last row per
#: alpha id, created before 2026-09-22 23:35 ET, number 27,890 (the draw3_fix scoring adjudicator's count,
#: re-counted read-only 2026-09-23 06:47 ET by the draw3_fix scoring engineer: 27,890 of 37,307 ids; draw3_fix
#: scoring 11: this used to name no copy). So the cause of the difference is UNKNOWN beyond "34 = COMPLETE
#: only" being one definition that fits the numerator.
#:
#: `binding_checks` is FROZEN here as a literal (draw-3 scoring MINOR): the numerator used to read the
#: module's mutable BINDING, so an edit made for axis 1 would have changed the estimand silently.
ESTIMAND = {
    "name": "alphas clearing EVERY binding check per 1,000 scored alphas",
    "not_the_submission_count": "this is NOT the submission count: a submission also needs the "
                                "correlation lines, the submitter and the 4-per-day cap, none of which "
                                "this estimand sees",
    "binding_checks": ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE",
                       "CONCENTRATED_WEIGHT", "HIGH_TURNOVER", "LOW_TURNOVER"),
    "numerator": "distinct alpha ids whose check set reads PASS for every name in binding_checks",
    "denominator": "distinct alpha ids scored (status COMPLETE or WARNING, with a check set), created on "
                   "a whole ET quota day before the day `now` falls in and before the day `data_through` "
                   "falls in",
    "per": 1000,
    "interval": "exact Poisson (Garwood) 95 % on the count, exposure = scored alphas / 1,000",
    "stratum": "cell = <region>/d<delay> of the alpha's settings (D28)",
    "test": "exact conditional test of two Poisson rates STRATIFIED BY CELL (D28): given each cell's "
            "K_c = k_ac + k_bc, k_bc ~ Binomial(K_c, n_bc / (n_ac + n_bc)) under H0; the statistic is the sum "
            "of k_bc over the cells both arms scored in, its null distribution the exact convolution of those "
            "binomials; two-sided p = min(1, 2 x the smaller tail)",
    "decides": "better / worse only when the stratified test is significant at `alpha` AND every cell with "
               "at least one event was scored by both arms and points strictly the same way; otherwise "
               "indistinguishable. The pooled test is printed and never decides (D28)",
    "alpha": 0.05,
    "power_for_mdr": 0.80,
}


# ------------------------------------------------------------------------------- the uncertainty
def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """(low, high) for a proportion k/n."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def rule_of_three(n: int) -> float:
    """Upper 95 % bound on a rate after n trials with ZERO events."""
    return 3.0 / n if n > 0 else float("inf")


#: _poisson_log_cdf stops summing once the terms are falling and this many nats below the largest. It bounds
#: COMPUTATION, not inference: every remaining term together is then below e^-50 x sqrt(lam) of the sum,
#: under 1e-19 for lam up to 1e5.
_LOG_TAIL_NATS = 50.0


def _poisson_log_cdf(k: int, lam: float) -> float:
    """log P(X <= k) for X ~ Poisson(lam), summed in LOG SPACE.

    Draw-3 scoring MINOR (S10): the old linear recurrence started from exp(-lam), which underflows to 0.0
    once lam passes ~745, so poisson_interval(800, 1) read [742.7, 745.1] -- an interval that does not
    contain 800 -- and k = 1500 read [745.1, 745.1]. Here each term's LOG is walked down from i = k
    (log P(i-1) = log P(i) + log i - log lam) under a running log-sum-exp, so no term is ever formed on
    its own scale."""
    if k < 0:
        return float("-inf")
    if lam <= 0:
        return 0.0
    lt = -lam + k * math.log(lam) - math.lgamma(k + 1)          # log P(X = k)
    top, s = lt, 1.0                                             # the sum is exp(top) * s
    log_lam = math.log(lam)
    for i in range(k, 0, -1):
        lt += math.log(i) - log_lam                              # log P(X = i - 1)
        if lt > top:
            s, top = s * math.exp(top - lt) + 1.0, lt
        else:
            s += math.exp(lt - top)
            if i - 1 < lam and lt < top - _LOG_TAIL_NATS:        # falling from here down, and negligible
                break
    return top + math.log(s)


def _poisson_cdf(k: int, lam: float) -> float:
    return math.exp(_poisson_log_cdf(k, lam))


def _gamma_q(a: float, x: float) -> float:
    """The regularized UPPER incomplete gamma function Q(a, x), by the series (x < a + 1) or Lentz's
    continued fraction (Numerical Recipes 6.2). Used for the chi-square tail of the cell-mix test; it is
    also P(Poisson(x) <= a - 1) for integer a, which the suite uses as a second derivation of
    _poisson_cdf."""
    if x <= 0:
        return 1.0
    log_front = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1.0:
        ap, term, total = a, 1.0 / a, 1.0 / a
        for _ in range(100000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-16:
                break
        return max(0.0, 1.0 - total * math.exp(log_front))
    tiny = 1e-300
    b = x + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 100000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        step = d * c
        h *= step
        if abs(step - 1.0) < 1e-16:
            break
    return math.exp(log_front) * h


def chi2_sf(x: float, df: int) -> float:
    """P(X >= x) for X ~ chi-square(df)."""
    return _gamma_q(df / 2.0, x / 2.0) if x > 0 else 1.0


def poisson_interval(k: int, days: int, alpha: float = 0.05) -> tuple:
    """Exact (Garwood) interval on an EVENT RATE per day: k events over `days` days.

    Round 1 (statistician): a Wilson interval on a per-alpha proportion scaled to "per 5,000" described
    rates the system cannot produce -- submissions are capped at 4 per quota day. Submissions per day
    are counts over days, so the interval is a Poisson one on the count, divided by the days.
    """
    if days <= 0:
        return (0.0, float("inf"))

    def solve(target_fn):
        lo, hi = 0.0, max(10.0, 3.0 * k + 20.0)
        for _ in range(100):
            mid = (lo + hi) / 2
            if target_fn(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2
    upper = solve(lambda lam: _poisson_cdf(k, lam) <= alpha / 2)
    lower = 0.0 if k == 0 else solve(lambda lam: 1 - _poisson_cdf(k - 1, lam) >= alpha / 2)
    return (lower / days, upper / days)


def _binom_pmf(k: int, p: float) -> list:
    """P(X = i) for X ~ Binomial(k, p), i = 0..k, by a log-space recurrence (no underflow at large k)."""
    if p <= 0.0:
        return [1.0] + [0.0] * k
    if p >= 1.0:
        return [0.0] * k + [1.0]
    lp = k * math.log1p(-p)
    step = math.log(p) - math.log1p(-p)
    out = [math.exp(lp)]
    for i in range(k):
        lp += math.log(k - i) - math.log(i + 1) + step
        out.append(math.exp(lp))
    return out


def rate_test_p(k_a: int, n_a: float, k_b: int, n_b: float) -> float:
    """Two-sided p of the exact conditional test that two Poisson rates are equal (ESTIMAND["test"]).

    Given K = k_a + k_b events, under H0 k_b ~ Binomial(K, n_b / (n_a + n_b)); the p-value doubles the
    smaller tail. A1: the draw-2 rule -- "different" when two 95 % intervals do not overlap -- has a
    size of at most 0.3 %, not 5 %, so it almost never said anything.
    """
    K = k_a + k_b
    if K == 0 or n_a <= 0 or n_b <= 0:
        return 1.0
    pmf = _binom_pmf(K, n_b / (n_a + n_b))
    return min(1.0, 2.0 * min(sum(pmf[:k_b + 1]), sum(pmf[k_b:])))


def stratified_rate_test_p(strata) -> float:
    """Two-sided p of the exact conditional test that B's rate equals A's WITHIN every stratum (D28,
    ESTIMAND["test"]). `strata` = [(k_a, n_a, k_b, n_b)], one per cell.

    Conditional on each stratum's total K_c, k_bc ~ Binomial(K_c, n_bc / (n_ac + n_bc)) under H0, the strata
    independent; the statistic T = sum of k_bc, and T's exact null distribution is the convolution of those
    binomials (no normal approximation). p = min(1, 2 x the smaller tail), as rate_test_p. A stratum where an
    arm scored nothing, or with no event, has a degenerate conditional law and adds nothing to T's spread; it
    is skipped. With one informative stratum this IS rate_test_p. Before D28 compare() pooled the cells,
    whose share of a day ranged 0.32-0.94 with all 37 events in USA/d1 (draw-3 scoring SERIOUS 6)."""
    dist, t = [1.0], 0
    for k_a, n_a, k_b, n_b in strata:
        K = k_a + k_b
        if K == 0 or n_a <= 0 or n_b <= 0:
            continue
        pmf = _binom_pmf(K, n_b / (n_a + n_b))
        conv = [0.0] * (len(dist) + K)
        for i, x in enumerate(dist):
            if x:
                for j, y in enumerate(pmf):
                    conv[i + j] += x * y
        dist, t = conv, t + k_b
    if len(dist) == 1:
        return 1.0
    return min(1.0, 2.0 * min(sum(dist[:t + 1]), sum(dist[t:])))


def _rejection_bounds(k: int, pi0: float, alpha: float) -> tuple:
    """(lo, hi): with K = k, the test rejects exactly when k_b <= lo or k_b >= hi (lo = -1 / hi = k + 1
    when that tail is empty)."""
    pmf = _binom_pmf(k, pi0)
    lo, cum = -1, 0.0
    for i in range(k + 1):
        cum += pmf[i]
        if cum <= alpha / 2:
            lo = i
        else:
            break
    hi, cum = k + 1, 0.0
    for i in range(k, -1, -1):
        cum += pmf[i]
        if cum <= alpha / 2:
            hi = i
        else:
            break
    return lo, hi


def _power(n_a, n_b, base, ratio, alpha, bounds) -> float:
    """Exact power of rate_test_p when A's rate is `base` per alpha and B's is ratio x base: the sum over
    K ~ Poisson(lam_a + lam_b) of the conditional rejection probability."""
    lam_a, lam_b = base * n_a, base * ratio * n_b
    lam = lam_a + lam_b
    if lam <= 0:
        return 0.0
    pi0, pi1 = n_b / (n_a + n_b), lam_b / lam
    total, logw = 0.0, -lam
    for k in range(1, int(lam + 12 * math.sqrt(lam) + 30) + 1):
        logw += math.log(lam) - math.log(k)
        w = math.exp(logw)
        if w == 0.0:
            continue
        if k not in bounds:
            bounds[k] = _rejection_bounds(k, pi0, alpha)
        lo, hi = bounds[k]
        if lo < 0 and hi > k:
            continue
        pmf1 = _binom_pmf(k, pi1)
        total += w * ((sum(pmf1[:lo + 1]) if lo >= 0 else 0.0) + (sum(pmf1[hi:]) if hi <= k else 0.0))
    return total


#: The exact power enumeration is O(K^2) in the expected event count; above this the MDR is not computed
#: (and says so) rather than stall a scorer. The desk's whole forge era holds 37 such events. Both
#: limits bound COMPUTATION, not inference: neither changes a verdict.
MDR_MAX_EVENTS = 1000
MDR_MAX_RATIO = 1e4


def minimum_detectable_ratio(n_a: float, n_b: float, base: float, alpha=None, power=None) -> dict:
    """The smallest rate ratio B/A (above 1, and below 1) that rate_test_p detects with `power`, at these
    exposures, when A runs at `base` events per scored alpha. A1: a comparison that cannot say what it
    could have seen reads "indistinguishable" as if it were news.

    Found by doubling then bisection on the EXACT power (_power); a discrete test's power is not
    perfectly monotone in the ratio, so the answer is good to about 1 %."""
    alpha = ESTIMAND["alpha"] if alpha is None else alpha
    power = ESTIMAND["power_for_mdr"] if power is None else power
    out = {"power": power, "alpha": alpha, "increase": None, "decrease": None, "increase_note": None}
    if base <= 0 or n_a <= 0 or n_b <= 0:
        out["note"] = "not computable: no event in either arm, so there is no baseline rate"
        return out
    if base * (n_a + n_b) > MDR_MAX_EVENTS:
        out["note"] = "not computed: more than %d expected events, beyond the exact enumeration" % MDR_MAX_EVENTS
        return out
    bounds = {}

    def pw(r):
        return _power(n_a, n_b, base, r, alpha, bounds)
    r = 2.0
    while True:
        if base * (n_a + r * n_b) > MDR_MAX_EVENTS:
            out["increase_note"] = "an increase big enough to detect lies beyond the exact enumeration's budget"
            break
        if pw(r) >= power:
            break
        if r >= MDR_MAX_RATIO:
            out["increase_note"] = "no increase up to %gx is detectable" % MDR_MAX_RATIO
            break
        r = min(2.0 * r, MDR_MAX_RATIO)
    if out["increase_note"] is None:
        lo, hi = max(1.0, r / 2.0), r
        while hi / lo > 1.01:
            mid = math.sqrt(lo * hi)
            if pw(mid) >= power:
                hi = mid
            else:
                lo = mid
        out["increase"] = round(hi, 3)
    if pw(0.0) >= power:
        lo, hi = 0.0, 1.0                       # power(lo) >= target > power(hi) ~ alpha
        while hi - lo > 0.005:
            mid = (lo + hi) / 2.0
            if pw(mid) >= power:
                lo = mid
            else:
                hi = mid
        out["decrease"] = round(lo, 3)
    return out


# --------------------------------------------------------------------- axis 1: is the product good
def _norm_formula(f) -> str:
    return "".join((f or "").split())


def neighbourhood_stability(rows_by_formula, row) -> dict:
    """Sharpe of the alpha's TRUE one-setting neighbours (D3).

    Round 1 (S2): the first version compared an alpha with its whole hypothesis group -- every leg, every
    window -- which measures the hypothesis, not the alpha's sensitivity to its own settings. A true
    neighbour has the SAME formula and region/delay/universe and differs in exactly ONE of decay,
    neutralisation, truncation. Fewer than NEIGHBOURS_MIN such neighbours is UNMEASURED, never a pass and
    never a fail; stable means the neighbours' median Sharpe keeps at least NEIGHBOUR_RETENTION_MIN of the
    alpha's own. MECHANISM linking settings-fragility to OS failure: UNKNOWN.
    """
    s = row.get("settings") or {}
    key = (_norm_formula(row.get("formula")), s.get("region"), s.get("delay"), s.get("universe"))
    knobs = ("decay", "neutralization", "truncation")
    peers = []
    for r in rows_by_formula.get(key, []):
        if r.get("alpha") == row.get("alpha"):
            continue
        rs = r.get("settings") or {}
        if sum(1 for k in knobs if str(rs.get(k)) != str(s.get(k))) == 1 and isinstance(r.get("sharpe"), (int, float)):
            peers.append(r["sharpe"])
    own = row.get("sharpe")
    if len(peers) < NEIGHBOURS_MIN or not isinstance(own, (int, float)) or own == 0:
        return {"n": len(peers), "verdict": "unmeasured", "retained": None}
    retained = statistics.median(peers) / own
    return {"n": len(peers), "median_neighbour_sharpe": round(statistics.median(peers), 3),
            "retained": round(retained, 3), "verdict": "stable" if retained >= NEIGHBOUR_RETENTION_MIN else "fragile"}


def curve_values(curve) -> list:
    """Cumulative PnL as an ordered list. Round 1 (F2): every cached curve is a {date: cumulative} dict,
    and the first version turned each into [] -- axis 1 read 'insufficient' for every alpha."""
    if isinstance(curve, dict):
        return [curve[k] for k in sorted(curve)]
    return list(curve or [])


#: regime_stability verdicts that pass axis 1's regime gate
REGIME_PASS = ("consistent", "mixed")


def regime_stability(curve) -> dict:
    """Did each third of the alpha's own history make money? (D3). Thirds are chosen before looking,
    unlike a calendar regime split drawn after seeing the curve.

    S3-NL (round 1's S3, not landed in draw 2): each third used to count as "positive" on the sign of
    its mean alone, so two near-flat thirds and one losing third read "mixed" and PASSED while the whole
    curve lost 101.4 (Sharpe -2.58). Now each third is judged against its own standard error
    (REGIME_SE_MULTIPLE): winning, losing, or flat. The verdict, first match wins:
      negative-overall  the curve ends below where it started, whatever the thirds say
      losing-third      at least one third lost money beyond noise
      consistent        all three thirds won
      mixed             two won, one was flat
      one-regime        at most one third won
    Only consistent and mixed pass (REGIME_PASS). The per-third Sharpe is printed as before; a third
    with gains and no dispersion has an unbounded Sharpe, not a zero one.
    """
    vals = curve_values(curve)
    if len(vals) < CURVE_POINTS_MIN:
        return {"n": len(vals), "verdict": "unmeasured", "thirds": None}
    rets = [b - a for a, b in zip(vals, vals[1:])]
    k = len(rets) // 3
    thirds, t_stats, labels = [], [], []
    for i in range(3):
        seg = rets[i * k:(i + 1) * k] if i < 2 else rets[2 * k:]
        mean = statistics.fmean(seg) if seg else 0.0
        sd = statistics.pstdev(seg) if len(seg) > 1 else 0.0
        se = statistics.stdev(seg) / math.sqrt(len(seg)) if len(seg) > 1 else 0.0
        thirds.append(round(mean / sd * math.sqrt(252), 3) if sd else
                      (float("inf") if mean > 0 else (float("-inf") if mean < 0 else 0.0)))
        t_stats.append(round(mean / se, 2) if se else
                       (float("inf") if mean > 0 else (float("-inf") if mean < 0 else 0.0)))
        labels.append("winning" if mean > REGIME_SE_MULTIPLE * se else
                      "losing" if mean < -REGIME_SE_MULTIPLE * se else "flat")
    overall = vals[-1] - vals[0]
    winning = labels.count("winning")
    verdict = ("negative-overall" if overall < 0 else "losing-third" if "losing" in labels else
               "consistent" if winning == 3 else "mixed" if winning == 2 else "one-regime")
    return {"n": len(rets), "thirds": thirds, "t_stats": t_stats, "labels": labels,
            "winning_thirds": winning, "overall_pnl": round(overall, 3), "verdict": verdict}


def _chk(row, name) -> dict:
    for c in row.get("checks") or []:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    return {}


def clears_every_binding_check(row, names=None) -> bool:
    """Every name in `names` reads PASS on the row's check set. Axis 1's binding gate passes nothing and
    reads the module's BINDING AT CALL TIME; the D24 numerator passes ESTIMAND["binding_checks"], which is
    frozen (draw-3 scoring MINOR). Draw3_fix scoring 3 (EST): the default used to be `names=BINDING`, bound
    once when this def ran, so a later edit of BINDING never reached a caller relying on the default, and a
    compare() that dropped its `names` argument read the same as one that passed it."""
    names = BINDING if names is None else names
    return all(_chk(row, n).get("result") == "PASS" for n in names)


def _corr_ok(row, c):
    """The correlation gate: True when BOTH readings are numbers strictly under their lines; False when any
    reading present is at or over its line (a measured failure, whatever is missing); None when a reading is
    missing and the one present is under its line. Draw3_fix scoring task: a PROD reading with no SELF
    reading read False -- a FAILED gate, so the alpha read REFUTED -- where nothing had been measured to
    fail; tools/ci_fixture.py case_axis1_gates pinned that as it decided, "not endorsed"."""
    pl, sl = SUB.corr_lines(row)
    p, s = c.get("prod"), c.get("self")
    if not (isinstance(p, (int, float)) and isinstance(s, (int, float))):
        return False if any(isinstance(v, (int, float)) and not CORR_UNDER_LINE(v, line)
                            for v, line in ((p, pl), (s, sl))) else None
    return (isinstance(p, (int, float)) and isinstance(s, (int, float))
            and CORR_UNDER_LINE(p, pl) and CORR_UNDER_LINE(s, sl))


#: D39 (Khoa, 2026-09-23 ~17:20): an alpha whose meta.hypothesis starts with this was GENERATED
#: (docs/evalharness/04_passfirst_design.md section 4.1: `hypothesis = gen:<family>`). Its D10 gate half is
#: read from MEANING_LEDGER, never from load_standard, which maps library composites only -- through it a
#: generated alpha read UNMEASURED for ever, so it could never be PROVEN and, under D26, every generated
#: submission would have counted against its version (04_passfirst_design.md section 4.4).
GENERATED_PREFIX = "gen:"
#: D39: the gates a program can decide for a generated alpha -- G4's leg clause (the row's G4 is read as that
#: clause, the only decidable half, 04 section 4.2; D52: it FAILS only when EVERY leg is crowded, alphaCount >=
#: 200 -- draw5 scoring M27: this comment read it the opposite way) and G5-G8. The generated alpha is PROVEN on
#: the gate half when every one of these is true.
MEANING_DECIDABLE = ("G4", "G5", "G6", "G7", "G8")
#: D39: G1-G3 need written prose a generated formula does not have. Recorded "not applicable to a generated
#: alpha" and printed UNMEASURED on every card; they never make a generated alpha unproven.
MEANING_NOT_APPLICABLE = ("G1", "G2", "G3")
#: 04_passfirst_design.md section 4.2: one JSON row per (alpha, formula sha). THE SCHEMA THIS READER
#: ASSUMES, written when no writer existed (read 2026-09-23 afternoon: no forge/meaning.py):
#: {"alpha": str, "formula_sha": str, "gates": {"G1": true/false/null, ..., "G8": ...}, "route": str,
#: "scorer": str, "scored_at": epoch seconds or an ISO time}; the draw-4 fix builders' shared interface adds
#: "inherited_from" and fixes formula_sha = sha256 of the formula TEXT (formula_sha()). forge/meaning.py, its
#: writer since 2026-09-23 ~21:30 (another owner's), stamps the same sha. A row outside that shape is not read.
MEANING_LEDGER = ROOT / "state/forge/meaning.jsonl"


def formula_sha(formula) -> str | None:
    """sha256 hex of the formula text as the journal holds it (UTF-8, no normalisation), the key the meaning
    ledger's writer stamps (shared interface, D39); None when the row carries no formula string."""
    return hashlib.sha256(formula.encode("utf-8")).hexdigest() if isinstance(formula, str) else None


def _formulas(rows) -> dict:
    """{alpha: (formula_sha of its formula, creation epoch)} of journal rows, for meaning_index."""
    return {r["alpha"]: (formula_sha(r.get("formula")), _created_ts(r)) for r in rows if r.get("alpha")}


def _epoch(t):
    """Epoch seconds from a number or an ISO-8601 string; None when neither."""
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    try:
        return datetime.datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp() if t else None
    except ValueError:
        return None


def meaning_index(rows, now, formulas) -> dict:
    """{alpha: the meaning row graded on this card} from MEANING_LEDGER's rows, or {} when `rows` is None.
    `formulas` = {alpha: (formula_sha of the journal's formula, creation epoch)} (_formulas).

    A row is seen only when it was SCORED BY `now` (scored_at <= now; a row with no readable time cannot be
    shown to precede the clock), the same bound the neighbour pool has (draw-3 scoring MINOR). THE BOUND IS THE
    WRITER'S scored_at, NOT THE TIME THE ROW WAS APPENDED (round 4 m4, g4_pD.py: one real append with scored_at =
    created + 60 s turned an unproven alpha proven at the same `now`): a row written after a card's clock but
    stamped earlier moves a re-grade at that clock, so provenance lists meaning under `not_bounded_by_now`. The
    writer-side fix (forge/meaning.py stamping its own append time) is not this module's.

    Round 3 S8 (v4_gen.py, real build_from): the reader believed any row -- the latest one won, and its
    formula_sha was compared with nothing, so a row carrying ANOTHER formula's sha read proven, and a later
    all-true row overturned an earlier G5 False. Now, of an alpha's rows:
      * only a row whose formula_sha equals formula_sha(the journal row's formula) is about this alpha's
        formula; any other row is ignored (the ledger is keyed by (alpha, formula sha));
      * a row scored BEFORE the alpha was created is ignored (S8's scored_at = 1 row; with the earliest row
        deciding, a back-dated row would otherwise always win);
      * of what remains, the EARLIEST scored_at decides (ties: the first in file order), so a row written
        later cannot overturn the verdict the alpha was graded on.
    NOT done here, and listed: S8's rule that `gen:` routing applies only when no library composite matches
    (the planner-written meta.hypothesis still routes), and the judge computing G4-G8 itself (S8 option (a))."""
    best = {}
    for i, m in enumerate(rows or ()):
        if not (isinstance(m, dict) and isinstance(m.get("alpha"), str) and isinstance(m.get("gates"), dict)):
            continue
        sha, created = (formulas or {}).get(m["alpha"], (None, None))
        t = _epoch(m.get("scored_at"))
        if sha is None or created is None or t is None or t > now or t < created or m.get("formula_sha") != sha:
            continue
        if m["alpha"] not in best or (t, i) < best[m["alpha"]][0]:
            best[m["alpha"]] = ((t, i), m)
    return {a: m for a, (_, m) in best.items()}


def _standard_gate(hyp, alpha, standard, meaning) -> tuple:
    """(gate value, detail) for D10's gate half. A library composite reads load_standard's tripped gates
    (`standard`; None = not measured). A GENERATED alpha (D39) reads its meaning row: True when every
    MEANING_DECIDABLE gate is true, False when any is false, None when any is unset or the row is missing
    (`meaning` None = the ledger was not read). A gate value that is not exactly true / false / null reads
    as null: a malformed value is not a pass."""
    if isinstance(hyp, str) and hyp.startswith(GENERATED_PREFIX):
        row = (meaning or {}).get(alpha)
        detail = {"route": "generated (D39): state/forge/meaning.jsonl",
                  "not_applicable": "G1-G3 UNMEASURED: not applicable to a generated alpha (D39)"}
        if row is None:
            detail["note"] = ("meaning.jsonl was not read" if meaning is None
                              else "no meaning row for this alpha's own formula (formula_sha), scored after its "
                                   "creation and by the grading clock (meaning_index)")
            return None, detail
        vals = {g: row["gates"].get(g) if row["gates"].get(g) is True or row["gates"].get(g) is False else None
                for g in MEANING_DECIDABLE}
        detail.update({"decidable": vals, "formula_sha": row.get("formula_sha"), "meaning_route": row.get("route"),
                       "scorer": row.get("scorer"), "scored_at": row.get("scored_at")})
        return (False if False in vals.values() else True if all(v is True for v in vals.values()) else None), detail
    trips = (standard or {}).get(hyp) if standard is not None else None
    return (None if trips is None else not trips), {"route": "library composite: load_standard"}


def alpha_status(gates: dict) -> str:
    """proven (every gate measured and passed) / refuted (any gate failed) / unproven (none failed,
    some could not be measured). A gate value of None means UNMEASURED. A gate that does not apply (D56) is
    left out of `gates` by the caller."""
    if any(v is False for v in gates.values()):
        return "refuted"
    return "proven" if all(v is True for v in gates.values()) else "unproven"


#: D56 (Khoa, 2026-09-24 ~02:20; round 4 S5): the status forge/pbo.py pbo() writes when a pool holds fewer than
#: MIN_TRIALS (20) trials -- "insufficient (< 20 trials)", carried to the scored store as `pbo_status` by
#: forge/harvest.py. On a GENERATED alpha (GENERATED_PREFIX) this reads NOT APPLICABLE: a D38 family pool holds at
#: most 12 settings of one formula (3 x 2 x 2, round 4 S5), so PBO could never be measured there, and counting it
#: unmeasured made every generated submission UNPROVEN and a cost at rank level 1 -- D39's own reasoning for G1-G3.
#: Printed UNMEASURED and never counted; the alpha's robustness rests on DSR and its two D51 neighbours. Any other
#: status ("pending", "empty", "too short", none), and any library alpha, is unchanged: unmeasured.
PBO_INSUFFICIENT = "insufficient"


def axis1_product(graded_rows, scored, corr, curves=None, standard=None, all_rows=None, meaning=None) -> dict:
    """Is what this version SUBMITTED good, robust and trustworthy? (D3, D10)

    Gates per submitted alpha, each True / False / None (unmeasured): every binding platform check PASS;
    DSR >= DSR_MIN; PBO pass; both correlation lines clear (CORR_UNDER_LINE; _corr_ok); true-neighbour
    stability; regime stability; and D10's hard gates of the hypothesis standard (round 1: they were
    missing) -- the key keeps D10's name `hypothesis_standard_8of8`, and for a GENERATED alpha it holds
    D39's reading, the decidable gates G4-G8 (_standard_gate; `standard_route` in the detail says which).
    `standard` maps hypothesis id -> list of tripped gates ([] = admissible), or is None (unmeasured).
    `meaning` = meaning_index() of state/forge/meaning.jsonl, or None when the ledger was not read.
    `all_rows` is the pool neighbours are drawn from (build_from restricts it to the graded version's
    own rows when the cohort is version-stamped, S10-NL).

    D56: a generated alpha whose PBO status is PBO_INSUFFICIENT has its `pbo_pass` listed under the detail's
    `not_applicable`: it stays None in `gates` (printed UNMEASURED) and is left out of the status and of
    gate_coverage.

    A5/A6: the value is the PROVEN fraction. Draw 2 credited an unproven alpha UNPROVEN_CREDIT = 0.5, an
    unmeasured constant on which rankings flipped at 0.474; unproven is now counted and shown, never
    credited.
    """
    by_formula = collections.defaultdict(list)
    for r in (all_rows if all_rows is not None else graded_rows):
        s = r.get("settings") or {}
        by_formula[(_norm_formula(r.get("formula")), s.get("region"), s.get("delay"), s.get("universe"))].append(r)

    submitted = [r for r in graded_rows if r.get("_submitted")]
    detail, statuses = [], collections.Counter()
    for r in submitted:
        a = r["alpha"]
        x = scored.get(a) or {}
        c = corr.get(a) or {}
        nb = neighbourhood_stability(by_formula, r)
        rg = regime_stability((curves or {}).get(a))
        hyp = (r.get("meta") or {}).get("hypothesis")
        std_gate, std_detail = _standard_gate(hyp, a, standard, meaning)
        gates = {
            "all_binding_pass": clears_every_binding_check(r),
            "dsr_ge_095": (x["dsr"] >= DSR_MIN) if isinstance(x.get("dsr"), (int, float)) else None,
            "pbo_pass": x.get("pbo_pass") if isinstance(x.get("pbo_pass"), bool) else None,
            "corr_under_lines": _corr_ok(r, c),
            "neighbourhood_stable": None if nb["verdict"] == "unmeasured" else nb["verdict"] == "stable",
            "regime_stable": None if rg["verdict"] == "unmeasured" else rg["verdict"] in REGIME_PASS,
            "hypothesis_standard_8of8": std_gate,
        }
        na = ({"pbo_pass": "UNMEASURED: not applicable (D56) -- PBO %r on a generated family pool" % x.get("pbo_status")}
              if (isinstance(hyp, str) and hyp.startswith(GENERATED_PREFIX) and gates["pbo_pass"] is None
                  and str(x.get("pbo_status") or "").startswith(PBO_INSUFFICIENT)) else {})
        st = alpha_status({k: v for k, v in gates.items() if k not in na})
        statuses[st] += 1
        detail.append({"alpha": a, "status": st, "gates": gates, "not_applicable": na, "neighbourhood": nb,
                       "regime": rg, "dsr": x.get("dsr"), "pbo": x.get("pbo"), "hypothesis": hyp,
                       "standard_route": std_detail})
    n = len(submitted)
    measured = sum(1 for d in detail for k, v in d["gates"].items() if v is not None and k not in d["not_applicable"])
    total = sum(len(d["gates"]) - len(d["not_applicable"]) for d in detail)
    return {"cohort": "alphas this version submitted", "n": n, "status_counts": dict(statuses),
            "proven": statuses["proven"], "unproven": statuses["unproven"], "refuted": statuses["refuted"],
            "value": round(statuses["proven"] / n, 4) if n else 0.0, "floor": FLOOR["axis1_product"],
            "floor_met": bool(n) and statuses["proven"] == n,
            "gate_coverage": round(measured / total, 3) if total else None,
            "verdict": "no-product" if not n else ", ".join("%d %s" % (v, k) for k, v in sorted(statuses.items())),
            "detail": detail,
            "caveat": "OS is never observable; every gate is an in-sample consistency test. MECHANISM "
                      "linking any of them to out-of-sample behaviour: UNKNOWN."}


def structural_families(rows) -> dict:
    """Distinct structural families among rows that cleared every binding check.

    MEASURED 2026-09-22: 34 fully-qualified alphas collapse into 7 families over 3 hypotheses. A
    submission retires its whole family (a sibling reads the correlation lines against it), so the
    family count -- not the qualified-alpha count -- is what the submission count can be drawn from.
    This is the denominator with enough events to move: 7 rather than 3.

    Draw3_fix scoring 13: this inserted ROOT into sys.path on EVERY call; it now inserts it only when it is
    not already there (fingerprint.py lives at ROOT, which the module's own import already put on the path).
    """
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import fingerprint as FP
    except ImportError:
        return {"families": None, "reason": "fingerprint.py unavailable"}
    idx, fams = FP.StructuralIndex(), []
    for r in rows:
        f = r.get("formula")
        if not f or not clears_every_binding_check(r):
            continue
        dup, _, label = idx.is_dup(f)
        if not dup:
            idx.register(f, r["alpha"])
            fams.append(r["alpha"])
    return {"families": len(fams), "representatives": fams}


# ------------------------------------------------------------ axis 2: is the throughput real
def quota_day_of_row(r):
    """ET quota day of a journal row, from its platform timestamp; None when absent or unparseable."""
    t = _created_ts(r)
    return datetime.datetime.fromtimestamp(t, ET).date().isoformat() if t is not None else None


def _created_ts(r):
    """Epoch seconds of a journal row's platform creation time; None when absent or unparseable."""
    d = r.get("dateCreated")
    if not d:
        return None
    try:
        return datetime.datetime.fromisoformat(str(d).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def axis2_throughput(graded_rows, submissions, days, proven_alphas, held_next=None, posts_in_window=None,
                     statuses=None) -> dict:
    """Four a day? At what cost? Sustainable or luck? (D6, D7)

    Unit (round 1, F3): PROVEN CLEAN submissions per whole ET quota day -- the floor's own unit. A5:
    clean used to mean "not refuted", so a submission whose robustness gates were never measured
    counted as throughput; now only a PROVEN one does, and unproven / refuted submissions are counted
    beside it and never in the rate. `days` is None when the version's exposure is unknown (A3): the
    card then carries no rate and cannot meet the floor. `days` == 0 (a version live for no whole day, or
    a window with no whole day in it) is UNMEASURED too, never a rate of 0.0 (draw-3 scoring SERIOUS 1,
    S4: a version deployed 09-20 and replaced 09-21 read a MEASURED 0.0 and outranked an exposure-unknown
    card).

    Sustainable (D7, as Khoa ticked it) is the conjunction of three pieces: the Poisson interval excludes
    zero, the proven clean submissions span >= 2 mechanisms, and the rate HOLDS IN THE NEXT WINDOW of
    equal length (`held_next`: True / False / "not evaluable", from build_from). The pieces are NOT
    independent (draw-3 scoring MINOR, S11): two mechanisms need k >= 2 proven clean submissions, and the
    exact interval's lower bound is above zero for every k >= 1, so the first conjunct is implied by the
    second. D7 as ticked names all three, so all three are kept and printed. S9-NL: draw 2 read the
    PREVIOUS window, which on a whole-history or version card lies before the cohort's first row, and
    reported that as False; a window that cannot be judged now says "not evaluable".
    """
    n = len(graded_rows)
    statuses = statuses or {}
    clean = [s for s in submissions if s.get("alpha") in proven_alphas]
    k = len(clean)
    known = days is not None
    rate = k / days if known and days else None
    lo, hi = poisson_interval(k, days) if known and days else (None, None)
    fam = structural_families(graded_rows)
    mechanisms = len({s.get("mechanism_key") for s in clean if s.get("mechanism_key")})
    held = "not evaluable" if held_next is None else held_next
    ev = {"interval_excludes_zero": (lo > 0) if known and days else "not evaluable",
          "two_or_more_mechanisms": mechanisms >= 2,
          "held_in_next_window": held}
    sustainable = (False if any(v is False for v in ev.values()) else
                   "not evaluable" if any(v == "not evaluable" for v in ev.values()) else True)
    return {"quota_days": days,
            "exposure": ("exposure unknown" if not known else
                         "%d whole ET quota day(s)" % days if days else "0 whole ET quota days: no rate"),
            "scored_alphas": n,
            "submissions_of_alphas_this_version_produced": len(submissions),
            "proven_clean_submissions": k,
            "unproven_submissions": sum(1 for s in submissions if statuses.get(s.get("alpha")) == "unproven"),
            "refuted_submissions": sum(1 for s in submissions if statuses.get(s.get("alpha")) == "refuted"),
            "posts_this_version_made": len(posts_in_window or []),
            "proven_clean_per_quota_day": round(rate, 3) if rate is not None else None,
            "poisson_95_per_day": ([round(lo, 3), round(hi, 3) if hi != float("inf") else None]
                                   if lo is not None else None),
            "scored_per_proven_clean_submission": round(n / k) if k else None,
            "scored_per_quota_day": round(n / days, 1) if days else None,
            "qualified_families": fam.get("families"),
            "scored_per_family": round(n / fam["families"]) if fam.get("families") else None,
            "distinct_mechanisms": mechanisms,
            "value": round(rate, 3) if rate is not None else None, "floor": FLOOR["axis2_throughput"],
            "floor_met": bool(known and days and rate >= FLOOR["axis2_throughput"]),
            "sustainable": sustainable, "sustainability_evidence": ev,
            "caveat": _one_day_caveat(rate)}


#: The rate the D5 x D6 paragraph of docs/evalharness/00_agreements.md reasons at: "Under a Poisson rate of
#: 0.5/day a single day returns 0 submissions 61 % of the time" (the best measured rate then was 3 over
#: 31,044 simulations, 0.48 per 5,000-sim day). A REFERENCE for the caveat below, not a parameter of any
#: verdict; draw-3 scoring MINOR: the 61 % used to be typed into the caveat by hand.
AGREED_REFERENCE_RATE_PER_DAY = 0.5


def _one_day_caveat(rate) -> str:
    """P(a quota day returns 0) = exp(-rate) under a Poisson rate, at the agreed reference rate and, when
    the card has one above zero, at the card's own measured rate."""
    ref = AGREED_REFERENCE_RATE_PER_DAY
    own = ("; at this card's own rate of %.3f per day, %.0f %%" % (rate, 100 * math.exp(-rate))
           if rate else "")
    return ("At %.1f submissions per quota day (the rate 00_agreements.md reasons at), one day returns 0 "
            "with probability exp(-%.1f) = %.0f %%%s; the interval, not the count, is what a single window "
            "can support." % (ref, ref, 100 * math.exp(-ref), own))


# ----------------------------------------------------------- axis 3: can branches be grown on it
#: "every forge module has a test" holds only when EVERY module has one: the check's name says every, and
#: at draw 2's 0.8 it held with forge/standard.py untested (21 of 22). Raised to 1.0 in draw 3 once
#: forge/tests/test_standard.py closed that gap (draw-3 scoring task; measured on the real tree: 22 of 22).
#: A LIMIT, stated (draw3_fix scoring 15): "every" means every TOP-LEVEL forge/*.py. The 19 modules under
#: forge/llm and forge/offline are outside the check; 00_agreements.md records the raise to 1.0 and that
#: scope as an orchestrator decision (under D42).
MODULE_TEST_COVERAGE_MIN = 1.0


def fitness_functions(root=ROOT) -> list:
    """Architecture checks that must hold for a new branch to be pluggable (D8).

    Each returns (name, ok, evidence). They are deliberately mechanical: an architecture claim that
    cannot fail a test is a slogan. S4-NL: three of them were existence checks a comment or an empty
    file could satisfy; those three now judge structure (AST, the real argument parser).
    """
    root = pathlib.Path(root)
    out = []

    # 1. the library is data, not code: adding a mechanism must not require editing a module
    comps = list((root / "forge/composites").glob("*.yaml"))
    legs = list((root / "forge/hypotheses").glob("*.yaml"))
    out.append(("mechanisms are data", bool(comps and legs),
                "%d composites + %d legs are YAML the loader globs" % (len(comps), len(legs))))

    # 2. new work can be staged where the live loop cannot see it. Tested as the LOADER'S BEHAVIOUR:
    # the first version checked that forge/*/staged/ existed, which is a property of one machine --
    # git does not track an empty directory, so the first GitHub Actions run failed it on a clean
    # clone of an unchanged architecture. What matters is that the loader ignores subdirectories.
    out.append(("new work can be staged invisibly", *_loader_ignores_subdirectories(root)))

    # 3. an A/B arm exists, so a change can be measured against the thing it replaces (S4-NL: was the
    # substring "--ab" anywhere in runner.py)
    out.append(("a change can be A/B'd in one round", *_ab_arm_is_real(root)))

    # 4. the deployed code has an identity, so a result can be attributed to a version
    out.append(("the deployed code has a version", (root / "tools/deploy.py").exists(),
                "tools/deploy.py hashes the shipped content"))

    # 5. no import cycles among the forge modules: a cycle means a branch cannot be added in isolation
    cyc = import_cycles(root / "forge")
    out.append(("no module-level import cycle in forge/", not cyc["module_level"],
                "module-level cycles: %s; deferred (a coupling smell, not a wall): %s"
                % (cyc["module_level"] or "none", cyc["deferred"] or "none")))

    # 6. the test suite covers the modules a branch would touch (S4-NL: was a file-stem match, which an
    # empty test file satisfied)
    mods, tested = _modules_with_a_real_test(root)
    covered = len(tested) / len(mods) if mods else 0.0
    untested = sorted(set(mods) - set(tested))
    out.append(("every forge module has a test", covered >= MODULE_TEST_COVERAGE_MIN,
                "%d of %d top-level forge modules have a test_<module>.py with a test function that uses the "
                "module (%.0f %%)%s; forge/llm and forge/offline are outside this check"
                % (len(tested), len(mods), covered * 100, ("; untested: " + ", ".join(untested)) if untested else "")))

    return out


def _loader_ignores_subdirectories(root=ROOT):
    """(ok, evidence): drop a deliberately INVALID leg into a staged/ subdirectory of a copy of the
    library; the real loader must load the copy exactly as it loads the original."""
    import shutil
    import tempfile
    from forge import hypotheses as H
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="wq-staged-"))
    try:
        lib = tmp / "hypotheses"
        shutil.copytree(root / "forge/hypotheses", lib, ignore=shutil.ignore_patterns("staged"))
        (lib / "staged").mkdir()
        (lib / "staged" / "broken.yaml").write_text("id: broken\nthis is not a valid leg: [\n")
        try:
            n = len(H.load_library(lib))
        except Exception as exc:  # noqa: BLE001
            return False, "the loader read staged/ and failed on it: %s" % type(exc).__name__
        return True, "a broken leg in staged/ was ignored; %d legs loaded" % n
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _constant_truth(test):
    """True / False when an `if`/`while` test is a constant (`False`, `0`, `None`, `not True`, ...), else
    None: the static reading of "this branch can never run"."""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _constant_truth(test.operand)
        return None if inner is None else not inner
    return None


def _always_leaves(st) -> bool:
    """True when statement `st` never falls through to the next one: a return/raise/break/continue, or an
    `if` whose every branch that can run leaves. Draw3_fix scoring 13 (V13): `if True: return` let the
    statements after it read as reachable."""
    if isinstance(st, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
        return True
    if isinstance(st, ast.If):
        truth = _constant_truth(st.test)
        runs = [b for b, taken in ((st.body, truth is not False), (st.orelse, truth is not True)) if taken]
        return all(b and any(_always_leaves(s) for s in b) for b in runs)
    return False


def _binding_counts(fn) -> collections.Counter:
    """How many times each name is BOUND in `fn`'s own scope -- parameters, assignment / for / with / walrus
    / del targets, `except ... as`, imports, nested def and class names -- not inside a nested def, lambda,
    class or comprehension target, which bind in their own scope."""
    a = fn.args
    c = collections.Counter(x.arg for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if x)
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            c[n.name] += 1
            continue
        if isinstance(n, ast.Lambda):
            continue
        if isinstance(n, ast.comprehension):
            stack.extend([n.iter] + n.ifs)
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            c[n.id] += 1
        elif isinstance(n, ast.ExceptHandler) and n.name:
            c[n.name] += 1
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            c.update((x.asname or x.name).split(".")[0] for x in n.names)
        stack.extend(ast.iter_child_nodes(n))
    return c


def _reachable_nodes(fn) -> list:
    """Every AST node of `fn`'s own body that can run: not in a branch a CONSTANT test rules out, not after
    a statement that always leaves the block (_always_leaves: a return/raise/break/continue, or an `if` all
    of whose runnable branches leave), and not inside a nested def, lambda or class (which may never be
    called)."""
    out = []
    scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

    def block(stmts):
        for st in stmts:
            visit(st)
            if _always_leaves(st):
                break

    def visit(n):
        if isinstance(n, scopes):
            return
        out.append(n)
        if isinstance(n, (ast.If, ast.While, ast.IfExp)):
            truth = _constant_truth(n.test)
            visit(n.test)
            for branch, runs in ((n.body, truth is not False), (n.orelse, truth is not True)):
                if runs:
                    block(branch) if isinstance(branch, list) else visit(branch)
            return
        for _, value in ast.iter_fields(n):
            if isinstance(value, list):
                if value and all(isinstance(v, ast.stmt) for v in value):
                    block(value)
                else:
                    for v in value:
                        if isinstance(v, ast.AST):
                            visit(v)
            elif isinstance(value, ast.AST):
                visit(value)
    block(fn.body)
    return out


def _ab_arm_is_real(root=ROOT):
    """(ok, evidence) for "a change can be A/B'd in one round", judged on forge/runner.py's SYNTAX TREE.

    S4-NL: the check was the substring "--ab" anywhere in runner.py, which a comment satisfied. Draw 3
    replaced it by EXECUTING runner.main() up to its argument parse, and the draw-3 scoring audit found
    four holes in that (MINOR; S14 and dc.py, each reproduced by the adjudicator): `plan(ab=a.ab)` under
    `if False:` passed; code main() ran BEFORE parsing ran inside the check (a file was written); a
    runner holding a `@dataclass` and `from __future__ import annotations` (the real runner has that line)
    read "does not import", which at a floor of 1.0 fails axis 3; and every call added two entries to
    sys.path. Now the runner is PARSED, never executed or imported, and sys.path is not touched.

    It holds only when main():
      * builds an argparse.ArgumentParser and calls add_argument("--ab", ...) on it with LITERAL keyword
        values and at least one choice besides the default, and a scratch parser built here from those
        literals alone parses every such arm to itself;
      * hands the parsed value on in a REACHABLE call plan(..., ab=<parsed>.<dest>), where <parsed> is a
        name main() bound to that parser's parse_args(...) (or the first element of parse_known_args), and
        reachable means _reachable_nodes: not in a branch a constant test rules out, not after a statement
        that always leaves (a return, or `if True: return`), not inside a nested def or lambda.
    Draw3_fix scoring 13 (V13), three holes closed: the parse must be on the SAME parser that carries --ab
    (a parse by a second parser used to count), and that parser's name and <parsed> must each be bound
    exactly once in main() (_binding_counts; a rebound name used to count, though a static reading cannot
    say which value reaches plan()).
    What a syntax tree cannot say: whether that call is TAKEN on a given run (the real one sits under
    `if a.plan: ... else:`). The branch drill is the check that runs the planner.
    """
    import argparse
    path = pathlib.Path(root) / "forge/runner.py"
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError, ValueError) as exc:
        return False, "forge/runner.py cannot be read as Python: %s" % type(exc).__name__
    main = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    if main is None:
        return False, "forge/runner.py has no top-level main()"
    live = _reachable_nodes(main)

    def call_to(n, attr):
        return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr
                and isinstance(n.func.value, ast.Name))
    parsers = {t.id for n in live if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
               and ((isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "ArgumentParser")
                    or (isinstance(n.value.func, ast.Name) and n.value.func.id == "ArgumentParser"))
               for t in n.targets if isinstance(t, ast.Name)}
    if not parsers:
        return False, "runner.main() builds no argparse.ArgumentParser"
    add = next((n for n in live if call_to(n, "add_argument") and n.func.value.id in parsers
                and any(isinstance(a, ast.Constant) and a.value == "--ab" for a in n.args)), None)
    if add is None:
        return False, "runner.main()'s parser has no --ab option"
    if not all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in add.args):
        return False, "--ab's option strings are not all literals"
    options = [a.value for a in add.args]
    kwargs = {}
    for kw in add.keywords:
        if kw.arg == "help":
            continue
        try:
            kwargs[kw.arg] = ast.literal_eval(kw.value)
        except (ValueError, TypeError, SyntaxError):
            return False, "--ab's %s= is not a literal, so a static check cannot say what it parses to" % kw.arg
    dest = kwargs.get("dest") or next(o for o in options if o.startswith("--"))[2:].replace("-", "_")
    arms = [c for c in (kwargs.get("choices") or ()) if c != kwargs.get("default")]
    if not arms:
        return False, "--ab offers no arm besides its default %r" % (kwargs.get("default"),)
    scratch = argparse.ArgumentParser(add_help=False, allow_abbrev=False, exit_on_error=False)
    try:
        scratch.add_argument(*options, **kwargs)
    except (TypeError, ValueError) as exc:
        return False, "--ab's literal arguments do not build an option: %s" % exc
    for arm in arms:
        try:
            got = getattr(scratch.parse_args(["--ab", arm]), dest)
        except (argparse.ArgumentError, SystemExit):
            return False, "the runner's --ab rejects its own arm %s" % arm
        if got != arm:
            return False, "--ab %s parses to %r" % (arm, got)
    holder = add.func.value.id                       # the parser that carries --ab
    bound = _binding_counts(main)
    if bound[holder] != 1:
        return False, "the parser carrying --ab (%s) is bound %d times in main()" % (holder, bound[holder])
    parsed = set()
    for n in live:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            v = n.value
            if call_to(v, "parse_args") and v.func.value.id == holder:
                parsed |= {t.id for t in n.targets if isinstance(t, ast.Name)}
            elif call_to(v, "parse_known_args") and v.func.value.id == holder:
                parsed |= {t.elts[0].id for t in n.targets if isinstance(t, ast.Tuple) and t.elts
                           and isinstance(t.elts[0], ast.Name)}
    parsed = {p for p in parsed if bound[p] == 1}
    handed = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "plan"
                 and any(kw.arg == "ab" and isinstance(kw.value, ast.Attribute) and kw.value.attr == dest
                         and isinstance(kw.value.value, ast.Name) and kw.value.value.id in parsed
                         for kw in c.keywords)
                 for c in live)
    if not handed:
        return False, "--ab parses (%s) but main() never hands the parsed value to plan(ab=...) in reachable code" % "/".join(arms)
    return True, "runner.main()'s parser offers --ab %s and main() hands it to plan(ab=...) in reachable code" % "/".join(arms)


def _module_names_bound(node, mod: str) -> set:
    """What an import statement binds to forge.<mod> (or to something inside it), as the DOTTED PATH a use
    must spell: ("M",) for `from forge import mod as M`, `from forge.mod import M` or `import forge.mod as
    M`; ("forge", "mod") for a plain `import forge.mod`, which binds the name `forge` -- so only a read of
    `forge.mod...` uses it. Draw-3 scoring MINOR (S12): the bound name used to be `forge` alone, so a test
    file importing forge.alpha and forge.beta and reading only forge.beta.X credited alpha."""
    out = set()
    target = "forge." + mod
    if isinstance(node, ast.Import):
        for a in node.names:
            if a.name == target or a.name.startswith(target + "."):
                out.add((a.asname,) if a.asname else ("forge", mod))
    elif isinstance(node, ast.ImportFrom) and node.level == 0:
        if node.module == "forge":
            out |= {(a.asname or a.name,) for a in node.names if a.name == mod}
        elif node.module and (node.module == target or node.module.startswith(target + ".")):
            out |= {(a.asname or a.name,) for a in node.names}
    return out


def _dotted(node) -> tuple:
    """("forge", "beta", "X") for the expression forge.beta.X; ("X",) for a bare name; () otherwise."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return tuple([node.id] + parts[::-1]) if isinstance(node, ast.Name) else ()


def _test_uses_module(path: pathlib.Path, mod: str) -> bool:
    """True when the test file holds a test function (top level, or a method of a Test* class) that CALLS, or
    ASSERTS OVER, forge.<mod>: a name or dotted path bound to it by an import at module level or inside that
    function (_module_names_bound) appears inside a call (as the callee or an argument) or inside an assert's test.
    An import alone, at either level, is not a use (S12). Round 4 m7 (g8tree/): a READ was enough, so test bodies
    `eps` and `zeta.f` -- a name evaluated and thrown away -- counted a module whose only function raises as tested.
    MEASURED 2026-09-24 on the real tree (scratchpad d6s_ev/m7_probe.py): all 23 forge modules stay tested under this
    rule. CONSEQUENCE, named: a test that binds (`x = M.X`) and asserts over the bound name only is not a use."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, OSError, ValueError):
        return False
    funcs, module_level = [], set()

    def walk(node, in_fn, cls):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not in_fn and ch.name.startswith("test") and (cls is None or cls.startswith("Test")):
                    funcs.append(ch)
                walk(ch, True, cls)
            elif isinstance(ch, ast.ClassDef):
                walk(ch, in_fn, ch.name)
            else:
                if not in_fn and isinstance(ch, (ast.Import, ast.ImportFrom)):
                    module_level.update(_module_names_bound(ch, mod))
                walk(ch, in_fn, cls)
    walk(tree, False, None)
    for fn in funcs:
        bound = set(module_level)
        for n in ast.walk(fn):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                bound |= _module_names_bound(n, mod)

        def reads(node):
            return any(chain and any(chain[:len(b)] == b for b in bound)
                       for chain in (_dotted(x) for x in ast.walk(node) if isinstance(x, (ast.Name, ast.Attribute))))
        for n in ast.walk(fn):
            if (isinstance(n, ast.Call) and reads(n)) or (isinstance(n, ast.Assert) and reads(n.test)):
                return True
    return False


def _modules_with_a_real_test(root=ROOT) -> tuple:
    """(modules, tested) over forge/*.py. S4-NL: a file-stem match counted an EMPTY test_<m>.py as a
    test; a module is tested only when forge/tests/test_<m>.py has a test function that uses it."""
    root = pathlib.Path(root)
    mods = sorted(p.stem for p in (root / "forge").glob("*.py") if p.stem != "__init__")
    tested = [m for m in mods if (root / "forge/tests" / ("test_%s.py" % m)).exists()
              and _test_uses_module(root / "forge/tests" / ("test_%s.py" % m), m)]
    return mods, tested


def _type_checking_names(tree) -> tuple:
    """(names, typing aliases) that stand for the real typing.TYPE_CHECKING in this module: a name bound by
    `from typing import TYPE_CHECKING [as X]`, and X in `X.TYPE_CHECKING` for X bound by `import typing [as
    X]` -- each only when the file binds it NO other way, anywhere. Draw3_fix scoring 13 (V14): a home-made
    `TYPE_CHECKING = True` made a module-level import, which runs, read as deferred."""
    names, aliases, other = set(), set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                real = n.module == "typing" and not n.level and a.name == "TYPE_CHECKING"
                (names if real else other).add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                (aliases if a.name == "typing" else other).add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            other.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            other.add(n.name)
        elif isinstance(n, ast.arg):
            other.add(n.arg)
    return names - other, aliases - other


def _is_type_checking(test, tc) -> bool:
    """`if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:` -- a block the interpreter never runs -- where the
    name really is typing's (`tc` = _type_checking_names of the file)."""
    names, aliases = tc
    return ((isinstance(test, ast.Name) and test.id in names)
            or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
                and isinstance(test.value, ast.Name) and test.value.id in aliases))


def _import_edges(tree, names: set):
    """[(target module, deferred?)] for every import of a sibling module of the forge package in `tree`.
    Deferred = the statement sits inside a function body, so it runs at call time only, or under
    `if TYPE_CHECKING:` with typing's own TYPE_CHECKING (_type_checking_names; draw3_fix scoring 13), so it
    never runs and couples the modules for a type checker only (draw-3 scoring
    MINOR, S13: a module-level `if TYPE_CHECKING:` import was read as a WALL). Its `else:` branch runs at
    import time and stays module-level. Resolved: `from forge import x`, `from forge.x import y`,
    `import forge.x`, `from . import x`, `from .x import y`. (Draw 3 also tested for ast.Lambda; an import
    statement cannot sit inside a lambda, so that branch could never match and is gone.)"""
    out = []
    tc = _type_checking_names(tree)

    def targets(node):
        if isinstance(node, ast.Import):
            return {a.name.split(".")[1] for a in node.names if a.name.startswith("forge.")}
        if node.level == 0:
            if node.module == "forge":
                return {a.name for a in node.names}
            if node.module and node.module.startswith("forge."):
                return {node.module.split(".")[1]}
            return set()
        if node.level == 1:
            return {a.name for a in node.names} if not node.module else {node.module.split(".")[0]}
        return set()

    def visit(node, deferred):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.extend((t, deferred) for t in targets(node) & names)
            return
        if isinstance(node, ast.If) and _is_type_checking(node.test, tc):
            for st in node.body:
                visit(st, True)
            for st in node.orelse:
                visit(st, deferred)
            return
        inner = deferred or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for ch in ast.iter_child_nodes(node):
            visit(ch, inner)
    visit(tree, False)
    return out


def import_cycles(pkg: pathlib.Path) -> dict:
    """{"module_level": [...], "deferred": [...]} -- cycles among the package's own modules.

    The distinction decides what axis 3 is entitled to say. A cycle whose edges are all inside
    functions (or under `if TYPE_CHECKING:`, which never runs) still imports cleanly (Python resolves a
    function-level import at call time) and is a coupling SMELL: the
    modules cannot be reasoned about separately, but a branch can still be added. A cycle with even
    one module-level edge is a WALL: importing either module drags the other in, and a new component
    that touches one touches both.
    S4-NL: the graph used to come from a line regex, which missed relative imports (`from . import x`),
    `import forge.x` and parenthesised multi-line imports, and read an import quoted inside a docstring
    as an edge. It is now built from the AST (_import_edges).
    MEASURED 2026-09-23 on forge/ (regex version): three cycles -- probe<->harvest, submit<->harvest and
    submit->probe->harvest->submit -- every edge deferred inside a function body.
    """
    names = {p.stem for p in pkg.glob("*.py")}
    top, deep = {}, {}
    for p in sorted(pkg.glob("*.py")):
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            tree = ast.Module(body=[], type_ignores=[])
        edges = _import_edges(tree, names)
        t = {m for m, deferred in edges if not deferred}
        top[p.stem], deep[p.stem] = t, t | {m for m, _ in edges}

    def cycles_in(graph):
        found = []

        def walk(n, path):
            if n in path:
                found.append(path[path.index(n):] + [n])
                return
            for m in sorted(graph.get(n, ())):
                walk(m, path + [n])
        for n in sorted(graph):
            walk(n, [])
        return sorted({tuple(sorted(set(c))) for c in found})

    at_module = cycles_in(top)
    return {"module_level": [" -> ".join(c) for c in at_module],
            "deferred": [" -> ".join(c) for c in cycles_in(deep) if c not in at_module]}


def dora(rows, now=None, window_days=28) -> dict:
    """The four DORA keys from the deploy ledger (tools/deploy.py DEPLOY_LOG).

    Definitions follow Forsgren, Humble & Kim (Accelerate, 2018), restricted to what this desk can
    measure: a 'deploy' is a push row of the ledger -- tools/deploy.py writes "one line per deploy ATTEMPT
    that got past the guards", which includes a `units_down` returned BEFORE the swap when the loop could be
    neither stopped nor restarted (draw4_build scoring 6: this said "an attempt that reached the code swap",
    which that row did not; the attempt stopped production, so it is read as a deploy and a failure); a
    'failure' is one that was rolled back, failed to roll back, or went live unrecorded; 'restore' is the time
    from a failed attempt to the next attempt that went live clean AND CHANGED THE VERSION. With fewer than two
    deploys every key is reported as insufficient rather than computed from one point. A9: REPORTED on a card,
    never part of a value.

    Draw4_build scoring 1 (p5.py): WATCH ROWS were read as deploys, so dora([deploy, deploy]) plus a watch_ok
    and a watch `interrupted` read 4 deploys and CFR 0.25. Per tools/deploy.py's WATCH ROWS contract a watch row
    is never a deploy: a watch whose outcome is in WATCH_ROUND_FAILED makes the push it names (`watched` = that
    push's started_at) a change failure -- watch_rolled_back as the contract states, and the three other
    outcomes that say the first round failed, by the failure definition above (a failed rollback, units down,
    or no rollback at all) -- and the watch row is the failure's time for time-to-restore. The running version
    after a watch follows live_days' reading: watch_rolled_back restores `previous_version`, WATCH_KEEPS_RUNNING
    changes nothing, any other watch outcome makes it unknown. D43 narrows which rounds the watch will judge
    failed; that is tools/deploy.py's side.

    Draw-3 scoring MINOR (S6), finishing round 2's A9 on the reader's side:
      * a `noop` row is NOT a deploy and is skipped (tools/deploy.py DEPLOY_LOG: "A NOOP IS NOT A DEPLOY,
        and every reader computing DORA must skip it"). With 1 rollback and 7 noop rows the old reader
        said CFR 0.111 and 2.25 deploys a week, and both band checks read ok;
      * a restore counts only when the version changes: the restoring deploy's `version` must differ from
        the one running after the failure (the previous version after a `rolled_back`, unknown after any
        other failure). Re-shipping what was already running restores nothing; a deploy with no
        `version` cannot show a change and is not counted as a restore.
    Draw3_fix scoring 8: an `interrupted` row (an exception escaped the push after the swap) and a
    `units_down` row (the units did not come back) are FAILURES. The failure set named only rolled_back,
    rollback_failed and unrecorded, so the ledger [deployed, interrupted, units_down, deployed] read CFR 0.0
    and both band checks read ok; tools/deploy.py's DEPLOY_LOG row contract names both outcomes and asks
    this reader to stop reading INTERRUPTED as a clean deploy.
    """
    now = now if now is not None else __import__("time").time()
    rows = sorted((r for r in rows if r.get("outcome") and r.get("outcome") != "noop"),
                  key=lambda r: r.get("started_at") or 0)
    pushes = [r for r in rows if not _is_watch(r)]
    if len(pushes) < 2:
        return {"status": "insufficient", "deploys": len(pushes),
                "note": "DORA needs at least two recorded deploys; the ledger holds %d" % len(pushes)}
    recent = [r for r in pushes if (r.get("started_at") or 0) >= now - window_days * 86400]
    failed = {"rolled_back", "rollback_failed", "unrecorded", "interrupted", "units_down"}
    failed_by_watch = {r.get("watched") for r in rows if _is_watch(r) and r["outcome"] in WATCH_ROUND_FAILED}
    fails = [r for r in pushes if r["outcome"] in failed or r.get("started_at") in failed_by_watch]
    leads = [r["finished_at"] - r["commit_time"] for r in pushes
             if r["outcome"] == "deployed" and r.get("commit_time") is not None and not r.get("git_dirty")]
    running, running_after = None, []          # the `version` live after each row; None = unknown
    for r in rows:
        if _is_watch(r):
            if r["outcome"] not in WATCH_KEEPS_RUNNING:
                running = r.get("previous_version") if r["outcome"] == "watch_rolled_back" else None
        elif r["outcome"] == "deployed":
            running = r.get("version")
        elif r["outcome"] != "rolled_back":     # a rollback restores what ran before; anything else is unknown
            running = None
        running_after.append(running)
    restores = []
    for i, r in enumerate(rows):
        if r["outcome"] in (WATCH_ROUND_FAILED if _is_watch(r) else failed):
            nxt = next((x for x in rows[i + 1:] if not _is_watch(x) and x["outcome"] == "deployed"
                        and x.get("version") is not None and x.get("version") != running_after[i]), None)
            if nxt:
                restores.append(nxt["finished_at"] - r["finished_at"])
    return {"status": "measured", "deploys": len(pushes),
            "deploys_per_week": round(len(recent) / (window_days / 7.0), 2),
            "lead_time_hours_median": round(statistics.median(leads) / 3600, 2) if leads else None,
            "lead_time_note": None if leads else "no clean (non-dirty) deploy carries a commit time",
            "change_failure_rate": round(len(fails) / len(pushes), 3),
            "time_to_restore_hours_median": round(statistics.median(restores) / 3600, 2) if restores else None}


def dora_checks(d: dict) -> list:
    """DORA keys judged against DORA_BAND, for DISPLAY on a card (A9: never in axis 3's value)."""
    if not d or d.get("status") != "measured":
        return []
    b = DORA_BAND
    out = [("DORA change-failure rate <= %.0f %%" % (100 * b["change_failure_rate_max"]),
            d["change_failure_rate"] <= b["change_failure_rate_max"], "measured %.3f" % d["change_failure_rate"]),
           ("DORA deploys per week >= %.0f" % b["deploys_per_week_min"],
            d["deploys_per_week"] >= b["deploys_per_week_min"], "measured %.2f" % d["deploys_per_week"])]
    ttr = d.get("time_to_restore_hours_median")
    if ttr is not None:
        out.append(("DORA time to restore <= %.0f h" % b["time_to_restore_hours_max"],
                    ttr <= b["time_to_restore_hours_max"], "measured %.2f h" % ttr))
    return out


def axis3_gearing(drill=None, root=ROOT, run_drill=True) -> dict:
    """Architecture fitness + the branch drill (D8). Every check that could be MEASURED counts equally;
    one that could not (the drill when not run) is reported, not scored. The floor is 1.0 (S4-NL).

    A9: DORA is no longer in this value. It read state/deploys.jsonl, which tools/deploy.py writes on the
    same machine, so the PRE-MERGE gate (tools/ci_gate.py check_fitness) depended on deploy history --
    one rollback blocked every commit, and seven no-op "deployed" rows lifted a tree failing 2 of 7
    architecture checks over the floor. DORA is reported on the card (build_from's `deploys`).

    What this measures is the checkout at `root` -- the tree that runs it, not necessarily the graded
    version's deployed tree (F4-NL, not addressed here); `measured_on` says so on the card.
    """
    ffs = fitness_functions(root)
    if drill is None and run_drill:
        from forge.offline import branch_drill as BD
        try:
            drill = BD.drill(root)
        except Exception as exc:  # noqa: BLE001 -- a drill that crashes is a FAILED drill
            drill = {"status": "crashed", "ok": False, "note": "%s: %s" % (type(exc).__name__, exc)}
    if drill is not None:
        ffs = ffs + [("a real branch goes through the planner", bool(drill.get("ok")),
                      "%s: %s" % (drill.get("status"), drill.get("note")))]
    held = sum(1 for _, ok, _ in ffs if ok)
    value = held / len(ffs) if ffs else 0.0
    return {"fitness_functions": [{"name": n, "ok": ok, "evidence": e} for n, ok, e in ffs],
            "held": held, "of": len(ffs),
            "branch_drill": drill or {"status": "not run"},
            "measured_on": "the checkout at %s, not the graded version's deployed tree" % pathlib.Path(root),
            "value": round(value, 3), "floor": FLOOR["axis3_gearing"],
            "floor_met": bool(ffs) and value >= FLOOR["axis3_gearing"]}


# ------------------------------------------------------------------------------ the scorecard (D2)
def scorecard(axes: dict) -> dict:
    """Non-compensatory PASS/FAIL on the hard floors (D2) plus the LEXICOGRAPHIC rank levels (D25).

    D25 replaced the 0-100 composite: `rank` holds the three levels in RANK_ORDER and rank_key() turns
    them into a sort key. The rank never touches the verdict -- a FAIL is a FAIL however it ranks.

    An ABSENT axis is an UNMET floor (draw-3 scoring MINOR, S7): the test `k in axes and ...` counted a card
    with no axis 3 as meeting the axis-3 floor, so it read PASS on two measured axes out of three. A floor
    nobody measured has not been met. `floors_absent` names them."""
    unmet = [k for k in FLOOR if not (axes.get(k) or {}).get("floor_met")]
    verdict = "PASS" if not unmet else "FAIL"
    return {"verdict": verdict, "floors_unmet": unmet,
            "floors_absent": [k for k in FLOOR if k not in axes],
            "rank": rank_levels(axes, verdict),
            "rank_means": "lexicographic: the verdict (PASS before FAIL, D29), then fewer REFUTED + UNPROVEN "
                          "submitted alphas (D26), then more PROVEN clean submissions per quota day, then axis "
                          "3's held fraction (D25); no weights, and a level that could not be measured ranks "
                          "below every measured value. A card whose POST horizon is not final at seen_until "
                          "is not ranked at all (D27). It never turns a FAIL into a PASS.",
            "axes": axes}


def rank_levels(axes: dict, verdict=None) -> dict:
    """The rank levels read off a card's axes and its verdict; a level of None could not be measured.

    `refuted_or_unproven_submitted` (D26) needs both counts: a hand-built axis 1 carrying only `refuted` has
    no level 1, since reading a missing unproven count as 0 is not measuring paying again. `horizon_final`
    and `comparable_from_et` (D27) come from axis 2's post_horizon; a card without one is not final."""
    a1, a2, a3 = (axes.get(k) or {} for k in ("axis1_product", "axis2_throughput", "axis3_gearing"))
    if "refuted" in a1 and "unproven" in a1:
        not_proven = a1["refuted"] + a1["unproven"]
    elif "status_counts" in a1:
        not_proven = a1["status_counts"].get("refuted", 0) + a1["status_counts"].get("unproven", 0)
    else:
        not_proven = None
    ph = a2.get("post_horizon") or {}
    lv = {"verdict": verdict,
          "refuted_or_unproven_submitted": not_proven,
          "proven_clean_per_quota_day": a2.get("value") if a2 else None,
          "axis3_held_fraction": a3.get("value") if a3 else None,
          "horizon_final": ph.get("final") is True,
          "comparable_from_et": ph.get("comparable_from_et")}
    if isinstance(a1.get("level1_post_lag_days"), dict):          # D57: a card build_from made
        lv["level1_post_lag_days"] = sorted(a1["level1_post_lag_days"].values())
        lv["post_exposure_days"] = ph.get("post_exposure_days")
    return lv


class NotComparable(ValueError):
    """D27: rank_key / rank_cmp refuse a card whose POST horizon is not final at its seen_until."""


def _level1_at(lv: dict, lag_days) -> int | None:
    """D57: level 1 counting only the level-1 alphas whose first accepted POST came within `lag_days` of creation.
    `lag_days` None, or a card that carries no lags (hand-built levels, a card recorded before D57), gives the raw
    count."""
    lags = lv.get("level1_post_lag_days")
    if lag_days is None or lags is None or lv.get("refuted_or_unproven_submitted") is None:
        return lv.get("refuted_or_unproven_submitted")
    return sum(1 for x in lags if x <= lag_days)


def _levels_of(card: dict) -> dict:
    return card.get("rank") or rank_levels(card.get("axes") or {}, card.get("verdict"))


def rank_key(card: dict, lag_days=None) -> tuple:
    """Sort key, BEST FIRST under ascending order: (verdict, *RANK_ORDER). `lag_days` (D57): count level 1 at this
    creation-to-POST lag (_level1_at); rank_cmp passes the lag both cards have been exposed for.

    (0) PASS before FAIL (D29); (1) fewer REFUTED + UNPROVEN submitted alphas (D26); (2) more PROVEN clean
    submissions per ET quota day; (3) higher axis-3 held fraction (D25). A level that could not be measured
    (None) sorts below every measured value. RAISES NotComparable when the card's POST horizon is not final
    at seen_until = min(now, data_through) (D27): its levels 1 and 2 can still move as POSTs land, and a live
    version used to rank below an identical retired one only because its POSTs had not arrived yet (round
    2's A4 bias, draw-3 scoring SERIOUS 3). The message names the ET date from which it is comparable.

    WHAT THIS DOES NOT GIVE (RULE 0 #7; the second is printed on every card by open_ticks):
      * Monotone only AT FIXED EXPOSURE. Adding a proven clean submission raises level 2 when the days
        stay the same; on a date card whose window starts at the first row, an EARLIER proven submission
        lengthens the window and can lower level 2 (S5: P alone 3 days at 0.333, P+P 18 days at 0.111).
      * Level 1 is a raw count, not a rate per exposure: a version that ran longer accumulates more.
      * A FINAL card can still move (draw5 scoring M23, D49): a POST later than POST_HORIZON_DAYS still counts at
        level 1, and an unproven or refuted one also makes axis 1's floor_met False and so the verdict FAIL.
        D57 equalises the lag inside rank_cmp only; rank_key(card) alone counts every POST by `now`.
      * Draw-3 scoring SERIOUS 2 is closed by D26, not by this docstring: before it, level 1 counted
        refuted alphas only, and S2 measured rank_cmp(unmeasured, measured) = -1 -- not measuring paid. An
        earlier docstring said "not measuring is never rewarded (A5)"; that was false then.
    CONSEQUENCE OF THE ORDER KHOA TICKED, stated so nobody meets it by surprise: level 1 comes first, so
    three proven submissions plus one refuted (P+P+P+R), or plus one unproven (P+P+P+U), rank BELOW a single
    proven one (P).
    """
    lv = _levels_of(card)
    if lv.get("horizon_final") is not True:
        raise NotComparable("not ranked (D27): the card's POST horizon is not final at its seen_until; it is "
                            "comparable from %s ET, graded with data and a clock at or after 00:00 ET that day"
                            % lv.get("comparable_from_et"))
    inf = float("inf")
    ref, rate, a3 = _level1_at(lv, lag_days), lv.get(RANK_ORDER[1]), lv.get(RANK_ORDER[2])
    return (VERDICT_ORDER.get(lv.get("verdict"), len(VERDICT_ORDER)),
            inf if ref is None else ref, inf if rate is None else -rate, inf if a3 is None else -a3)


def rank_cmp(a: dict, b: dict) -> int:
    """-1 when card `a` ranks above card `b`, 1 when below, 0 when level-for-level tied
    (functools.cmp_to_key(rank_cmp) sorts best first). Refuses (NotComparable) when either card's POST
    horizon is not final (D27).

    D57 (Khoa, 2026-09-24 ~02:20; round 4 S2): level 1 is counted on BOTH cards at the same creation-to-POST lag --
    the shorter of the two cards' post_exposure_days, a lag every graded alpha of both cards has had for a POST to
    land and be seen (build_from measures it to seen_until, D27's clock). Round 4 S2 (s2_d49.py): two identical
    cohorts, one unproven alpha each POSTed 20 days after creation, created 09-10 and 09-20 and graded 10-06, read
    level 1 = 1 against 0 and rank_cmp(newer, older) = -1, because only the older alpha's POST had happened (D49 x
    D27). A card with no graded day carries no exposure and no level-1 alpha, so the other card's exposure is the lag.
    When EITHER card carries no lags (hand-built levels, or a card recorded before D57) BOTH are counted raw: the
    lag cannot be equalised, and truncating only the card that has lags would favour it. NOT GIVEN: (1) with three
    or more cards the pairwise lags differ, so rank_cmp need not be transitive and a sort by it need not equal a
    sort by rank_key, which counts every POST by `now`; (2) D57 equalises level 1 only -- a late unproven or refuted
    POST also makes axis 1's floor unmet and the verdict (level 0) FAIL, uncorrected (draw5 scoring M23)."""
    la, lb = (_levels_of(c) for c in (a, b))
    if "level1_post_lag_days" in la and "level1_post_lag_days" in lb:
        exposed = [x for x in (la.get("post_exposure_days"), lb.get("post_exposure_days")) if x is not None]
        lag = min(exposed) if exposed else None
    else:
        lag = None
    ka, kb = rank_key(a, lag), rank_key(b, lag)
    return -1 if ka < kb else (1 if ka > kb else 0)


# ------------------------------------------------------------------------- the version on the stand
#: D30 and draw3_fix scoring 12: a stamp that is NOT the deployed bytes' plain identity never forms a cohort
#: -- the '+'-suffixed forms forge/runner.py's pipeline_version documents ('+MISMATCH:<id>', '+untracked',
#: '+unverified'), D40's '+EXTRAS:<n>', and these marker words. Rows stamped so cannot be attributed to one
#: version's bytes. Draw4_build scoring 3: the same holds for meta.run_config, where recover_orphans writes
#: "ambiguous" (_forms_cohort).
STAMP_MARKERS = ("unknown", "ambiguous")


def plain_stamp(v) -> bool:
    """A pipeline_version that can form a cohort (D30; draw3_fix scoring 12): a non-empty string with no
    '+' suffix that is not a marker word."""
    return isinstance(v, str) and bool(v) and "+" not in v and v not in STAMP_MARKERS


def _forms_cohort(pv, rc) -> bool:
    """D30: a plain pipeline_version with no run_config, or with a plain one. Draw4_build scoring 3 and pipeline
    P2: the marker rule used to apply to pipeline_version only, so forge/offline/recover_orphans.py's
    run_config "ambiguous" (plan entries that agree on the version and differ on run_config) formed the cohort
    (pv, "ambiguous"), which suppressed build()'s one-cohort gap and could be compared."""
    return plain_stamp(pv) and (rc is None or plain_stamp(rc))


def cohort_of(row):
    """(pipeline_version, run_config) of a journal row, or None when it forms no cohort (D30).

    D30 (Khoa, 2026-09-23 ~15:45, implementation note in 00_agreements.md): the runner's normalised argv is
    a SECOND stamp, meta.run_config, so a change of FORGE_ARGS or N starts a new cohort. A row without
    run_config is (pipeline_version, None); one whose run_config is present but is not a plain stamp (not a
    non-empty string, a marker word, or '+'-suffixed; _forms_cohort) forms no cohort, rather than merge silently
    into the None cohort or form one of its own."""
    m = row.get("meta") or {}
    pv, rc = m.get("pipeline_version"), m.get("run_config")
    return (pv, rc) if _forms_cohort(pv, rc) else None


def parse_cohort(version) -> tuple:
    """(pipeline_version, run_config) from "pv", "pv@run_config" or a (pv, rc) pair; ValueError for a stamp
    pair that cannot form a cohort (D30, _forms_cohort). '@' appears in neither a plain stamp nor a sha256
    run_config."""
    pv, rc = (tuple(version) if isinstance(version, (tuple, list)) else
              tuple(version.split("@", 1)) if isinstance(version, str) and "@" in version else (version, None))
    if not _forms_cohort(pv, rc):
        raise ValueError("%r forms no cohort: a suffixed or marker pipeline_version or run_config (%s) never does (D30)"
                         % (version, ", ".join(("+...",) + STAMP_MARKERS)))
    return pv, rc


def cohort_label(cohort) -> str:
    """The label of a cohort: "pv" for (pv, None), "pv@rc" otherwise -- the form parse_cohort reads back."""
    return cohort[0] if cohort[1] is None else "%s@%s" % cohort


def whole_days(first: str, last_exclusive: str) -> list:
    d0 = datetime.date.fromisoformat(first)
    d1 = datetime.date.fromisoformat(last_exclusive)
    return [(d0 + datetime.timedelta(days=i)).isoformat() for i in range((d1 - d0).days)]


def _next_day(d: str) -> str:
    return (datetime.date.fromisoformat(d) + datetime.timedelta(days=1)).isoformat()


def _day_start(d: str) -> float:
    """Epoch seconds of 00:00 America/New_York on ET quota day `d`."""
    return datetime.datetime.combine(datetime.date.fromisoformat(d), datetime.time(0), tzinfo=ET).timestamp()


def current_quota_day(now=None) -> str:
    return SUB.quota_day(now if now is not None else __import__("time").time())


def horizon_final_at(last_day: str) -> float:
    """A4: when every POST that can count for alphas created up to the end of `last_day` has had its
    chance -- the end of that ET day plus POST_HORIZON_DAYS of 86,400 s, the unit _submissions credits in.
    Across a DST change this instant is not an ET midnight (comparable_from)."""
    return _day_start(_next_day(last_day)) + POST_HORIZON_DAYS * DAY_S


def comparable_from(final_at: float) -> str:
    """D27's printed date: the first ET quota day whose 00:00 ET is at or after `final_at`, so a card graded at or
    after 00:00 ET that day (rank_key's promise) is final.

    Draw4_build scoring 5 (p1.py): this was SUB.quota_day(final_at). When the horizon crosses the November change
    the instant is 23:00 EST, so newest day 2026-10-18 printed 2026-11-01 and a card graded 00:00 ET that day still
    raised NotComparable (second derivation: newest + 15 ET calendar days = 2026-11-02). The fix the audit
    suggested, final_at = 00:00 ET of newest + 15 days, would read final ONE HOUR EARLY across the March change
    (EX-ANTE arithmetic: 14 x 86,400 s from 00:00 EST 2027-03-01 is 01:00 EDT 2027-03-15), before the credit
    horizon in _submissions closes; so finality keeps the exact instant and only the printed day moves."""
    d = SUB.quota_day(final_at)
    return d if _day_start(d) >= final_at else _next_day(d)


#: tools/deploy.py DEPLOY_LOG, WATCH ROWS (D16's first-round half): the watch outcomes after which the watched
#: push's code is still what runs -- the round was fine, nothing finished in time, or it failed and no rollback
#: could start.
WATCH_KEEPS_RUNNING = ("watch_ok", "watch_timeout", "watch_not_rolled_back")
#: The watch outcomes that say the first round on the pushed code FAILED (a change failure of that push, for
#: DORA): rolled back, rollback failed, units down after the rollback, or not rolled back.
WATCH_ROUND_FAILED = ("watch_rolled_back", "watch_rollback_failed", "watch_units_down", "watch_not_rolled_back")


def _is_watch(r) -> bool:
    """A watch row (tools/deploy.py DEPLOY_LOG, WATCH ROWS: it carries `watched`, the started_at of the push it
    watched); every outcome in tools/deploy.py WATCH_OUTCOMES starts with "watch_", watch_interrupted included (draw5
    scoring M10: this named `interrupted`, the outcome's name before draw4_build release R1; a row that old is still a
    watch by its `watched` field). A watch row is never a deploy."""
    return "watched" in r or str(r.get("outcome") or "").startswith("watch_")


def live_days(deploys, version, now) -> dict:
    """A3: the whole ET quota days on which `version` was the RUNNING pipeline, from the deploy ledger
    (tools/deploy.py appends one row per attempt to state/deploys.jsonl).

    Draw 2 took exposure from the rows: compare() counted days that carry a row and then graded every
    calendar day between them, and a version card ran from the version's first row to TODAY, so a
    retired version's rate kept falling (20 clean over 5 days read 4.0 PASS on 09-15 and 1.538 FAIL on
    09-23, same rows). Now:
      * a row with outcome "deployed" makes its `pipeline_version` the running one (a row without that
        field makes the running version UNKNOWN from then on);
      * "rolled_back" restores the previous one; any other outcome (rollback_failed, unrecorded,
        units_down, interrupted, unknown) makes it UNKNOWN; "noop" rows are ignored;
      * a WATCH row is never a deploy (draw4_build scoring 1: one watch_ok row an hour after V's deploy took V from
        10 live days to 0, because every outcome not named here made the running version unknown).
        watch_rolled_back puts its `previous_pipeline_version` back; WATCH_KEEPS_RUNNING leaves the running
        version as it was and touches no day; any other watch outcome (watch_rollback_failed, watch_units_down,
        watch_interrupted, unknown) makes it UNKNOWN. That is tools/deploy.py's WATCH ROWS contract (WATCH_OUTCOMES);
      * the join is on pipeline_version ONLY: a ledger row carries no run_config. A (version, run_config)
        cohort's days are narrowed from these by the runner's run_config log (D45, cohort_live_days);
      * every ET day an attempt touched is EXCLUDED for every version -- two versions ran on it -- except
        a "deployed" row that re-deployed the pipeline version already running, and a watch that changed nothing;
      * before the ledger's first row the running version is unknown;
      * the unfinished day `now` falls in is never included.
    When no "deployed" row names `version`, the answer is {"known": False} and callers print "exposure
    unknown" rather than guess.

    WHAT THE LEDGERS HOLD, MEASURED 2026-09-23 (draw-3 scoring MINOR: this docstring said exposure stays
    unknown "until deploy.py writes it", which is not true of every cohort):
      * the MacBook's state/deploys.jsonl holds one row, carrying `version` 8f8b7517b8598d07 and no
        `pipeline_version`; the VPS has no /opt/wq/state/deploys.jsonl at all;
      * the VPS journal's stamped rows all carried pipeline_version ec6a5cd75d58fea2 when read (read-only,
        2026-09-23 ~04:30 ET) -- the id computed by the
        code that preceded round 2's A10 fix. tools/deploy.py's pipeline-identity (A10) comment records
        that the first push with the current code writes a DIFFERENT id for the same bytes, so no ledger
        row will ever name ec6a5cd75d58fea2: that cohort's exposure stays unknown PERMANENTLY. Its axis 1 is
        still graded; it can never carry a rate.

    The days feed ONLY axis 2's rate (draw-3 scoring SERIOUS 1): build_from grades axis 1, and so rank
    level 1, on every stamped row whatever these days say.
    """
    if deploys is None:
        return {"known": False, "days": [], "note": "exposure unknown: no deploy ledger was read"}
    rows = sorted((r for r in deploys if r.get("outcome") and r.get("outcome") != "noop"
                   and isinstance(r.get("finished_at"), (int, float))), key=lambda r: r["finished_at"])
    if not any(r["outcome"] == "deployed" and r.get("pipeline_version") == version for r in rows):
        return {"known": False, "days": [],
                "note": "exposure unknown: the deploy ledger (%d row(s)) records no deploy of pipeline_version %s"
                        % (len(rows), version)}
    today = current_quota_day(now)
    changes, excluded, running = [], set(), None
    for r in rows:
        before = running
        if _is_watch(r):
            if r["outcome"] in WATCH_KEEPS_RUNNING:
                continue
            running = r.get("previous_pipeline_version") if r["outcome"] == "watch_rolled_back" else None
        elif r["outcome"] == "deployed":
            running = r.get("pipeline_version")
        elif r["outcome"] != "rolled_back":
            running = None
        if not (r["outcome"] == "deployed" and running is not None and running == before):
            d0 = SUB.quota_day(r["started_at"] if isinstance(r.get("started_at"), (int, float)) else r["finished_at"])
            excluded.update(whole_days(d0, _next_day(SUB.quota_day(r["finished_at"]))))
        changes.append((r["finished_at"], running))
    days = []
    for d in whole_days(SUB.quota_day(rows[0]["finished_at"]), today):
        start, state = _day_start(d), None
        for ts, v in changes:
            if ts <= start:
                state = v
        if state == version and d not in excluded:
            days.append(d)
    return {"known": True, "days": days, "excluded_deploy_days": sorted(excluded),
            "note": "%d whole ET quota day(s) live per the deploy ledger (deploy days excluded)" % len(days)}


#: D45 (Khoa, 2026-09-23 ~20:15): the runner appends {"at", "pipeline_version", "run_config", "host"} here when it
#: starts with a (pipeline_version, run_config) different from the last row for its host (the shared interface
#: fixed for the draw-4 fix builders). The judge reads it for a cohort's exposure; the deploy ledger's readers
#: never do. Its writer is forge/runner.py main() -> note_run_config() -> record_run_config(), on a live start
#: (draw5 scoring M20: this said "no runner writes it yet"). Read 2026-09-24 on this Mac: the file does not exist.
RUN_CONFIG_LOG = ROOT / "state/forge/run_config_log.jsonl"


def cohort_live_days(deploys, run_config_log, cohort, now) -> dict:
    """D45: the whole ET quota days on which the cohort (pipeline_version, run_config) was RUNNING -- the
    pipeline_version's live days (live_days) on which the run_config log records that run_config for the whole
    day. Draw4_build scoring 2 (p1.py): every cohort of a pipeline_version took ALL of its live days, so (V, r1)
    with one row on 09-10 and (V, r2) with five rows on 09-15..19 each read 10 quota days, and one experiment
    round (vps/c11_run.sh, pow_run.sh or llm_formula_run.sh pass `--plan`, a second run_config) set the main
    cohort's rate denominator.

    Each host's rows form its own timeline (the runner records LIVE starts only, each tagged with its host --
    forge/runner.py record_run_config; draw5 scoring M3: this used to say "a dry run on another machine", which
    records nothing). A day d of the pipeline_version's live days is, for this cohort, the FIRST that applies:
      * UNKNOWN when it ends at or before the log's first row naming the cohort (D45: "days before any transition
        row for a cohort read 'exposure unknown', never a guess") -- EVEN a day the log attributes to another
        run_config (draw5 scoring M19): D45's letter is followed, so such a day reads unknown, not "not the
        cohort's";
      * COUNTED when some host held the cohort ALL day: its recorded state at 00:00 ET of d is the cohort and none of
        its rows falls inside d -- whatever any other host did on d (draw5 scoring M3: this bullet and the next
        overlapped). CONSEQUENCE, named: a host whose last row names the cohort counts it on every later live day,
        so a stale host (a host name that changed, a machine that ran live once) extends the cohort's days
        (reachability SUSPECTED, pipeline M17);
      * EXCLUDED when no host held it all day and some host held it for part of d (its state at 00:00 ET was the
        cohort and a row inside d changed it, or a row naming the cohort falls inside d) -- two run_configs ran on
        it, as live_days excludes a deploy day;
      * otherwise not the cohort's (the log records another run_config for it).
    THIS MODULE'S READING of D45, stated: unknown days are left out of the rate and listed; the card's exposure is
    unknown only when no day is counted and some day is unknown. A (pipeline_version, None) cohort -- rows from a
    runner that stamped no run_config -- keeps the pipeline_version's live days, as before D45 (draw5 scoring M26;
    listed in open_ticks). With no log read, a run_config cohort's exposure is unknown. Log rows after `now` are
    filtered out, and the filter is REDUNDANT, kept as a guard (draw5 scoring M4): every day read ends before the
    day `now` falls in, so a later row changes neither a day's state at 00:00 nor its inside rows, and a first row
    for the cohort after `now` leaves every day unknown exactly as no row does."""
    pv, rc = cohort
    base = live_days(deploys, pv, now)
    if rc is None or not base["known"]:
        return base
    if run_config_log is None:
        return {"known": False, "days": [], "note": "exposure unknown: no run_config log (%s) was read, and D45 takes "
                                                    "a run_config cohort's days from it" % RUN_CONFIG_LOG.name}
    rows = sorted((r for r in run_config_log if isinstance(r, dict) and isinstance(r.get("at"), (int, float))
                   and not isinstance(r.get("at"), bool) and r["at"] <= now
                   and isinstance(r.get("pipeline_version"), str) and isinstance(r.get("run_config"), str)),
                  key=lambda r: r["at"])
    timelines = collections.defaultdict(list)
    for r in rows:
        timelines[r.get("host")].append((r["at"], (r["pipeline_version"], r["run_config"])))
    first = next((r["at"] for r in rows if (r["pipeline_version"], r["run_config"]) == cohort), None)
    counted, mixed, unknown = [], [], []
    for d in base["days"]:
        start, end = _day_start(d), _day_start(_next_day(d))
        if first is None or end <= first:
            unknown.append(d)
            continue
        whole = part = False
        for tl in timelines.values():
            at_start = next((s for t, s in reversed(tl) if t <= start), None)
            inside = [s for t, s in tl if start < t < end]
            if at_start == cohort and not inside:
                whole = True
            elif at_start == cohort or cohort in inside:
                part = True
        if whole:
            counted.append(d)
        elif part:
            mixed.append(d)
    note = "%d whole ET quota day(s) live for this run_config per the deploy ledger and the run_config log (D45)" % len(counted)
    if mixed:
        note += "; %d day(s) on which the run_config changed are excluded" % len(mixed)
    if unknown:
        note += ("; %d live day(s) of the pipeline_version (%s..%s) come before the log's first row for this cohort and "
                 "read exposure unknown: left out of the rate" % (len(unknown), unknown[0], unknown[-1]))
    known = bool(counted) or not unknown
    return {"known": known, "days": counted if known else [], "excluded_deploy_days": base["excluded_deploy_days"],
            "excluded_run_config_days": mixed, "unknown_days": unknown,
            "note": note if known else "exposure unknown: " + note}


def _submissions(graded, accepted, now) -> tuple:
    """({alpha: its first accepted POST that is CREDITED}, {alpha: its first accepted POST by `now`, any lag},
    POSTs with no time).

    A4: a POST is credited (axis 2, the next-window judgement) only if it happened by `now` and within
    POST_HORIZON_DAYS of the alpha's creation; M6: an alpha counts once however many times it was accepted.
    D49 (Khoa, 2026-09-23 ~21:00; round 3 S1): every accepted POST of a graded alpha counts against rank level 1
    whatever its lag -- the second map, which axis 1 grades. Before it, S1's g_late_post.py measured an unproven
    alpha POSTed after 14.05 days costing its version nothing (level 1 fell from 1 to 0), while forge/submit.py's
    eligible() has no age filter. The horizon now bounds credit and finality only."""
    created = {r["alpha"]: _created_ts(r) for r in graded}
    first, posted, untimed = {}, {}, 0
    for h in sorted(accepted, key=lambda h: h.get("posted_at") or 0):
        a, t = h.get("alpha"), h.get("posted_at")
        if a not in created or a in posted:
            continue
        if not isinstance(t, (int, float)) or t <= 0:
            untimed += 1
            continue
        c = created[a]
        if c is None or t > now:
            continue
        posted[a] = h
        if t - c <= POST_HORIZON_DAYS * DAY_S:
            first[a] = h
    return first, posted, untimed


def _grade(days, by_day, accepted, scored, corr, curves, standard, pool, now, meaning=None) -> dict:
    """Axis 1 and the submission set for the rows created on `days` (copies; the caller's rows are
    never mutated). `meaning` = meaning_index() or None. Axis 1 grades every alpha with an accepted POST by `now`
    (D49); `subs`, the credited submissions, only those within POST_HORIZON_DAYS."""
    graded = [dict(r) for d in days for r in by_day.get(d, [])]
    first, posted, untimed = _submissions(graded, accepted, now)
    for r in graded:
        r["_submitted"] = r["alpha"] in posted
    subs = [dict(h, mechanism_key=h.get("mechanism_key") or ((next((r for r in graded if r["alpha"] == a), {})
                                                              .get("meta") or {}).get("mechanism_key")))
            for a, h in first.items()]
    a1 = axis1_product(graded, scored, corr, curves, standard=standard, all_rows=pool, meaning=meaning)
    a1["posted_beyond_the_horizon"] = sorted(set(posted) - set(first))     # D49: graded, never credited
    created = {r["alpha"]: _created_ts(r) for r in graded}
    # D57: each level-1 alpha's creation-to-POST lag, so rank_cmp can count both cards at one lag
    a1["level1_post_lag_days"] = {d["alpha"]: (posted[d["alpha"]]["posted_at"] - created[d["alpha"]]) / DAY_S
                                  for d in a1["detail"] if d["status"] in ("refuted", "unproven")}
    return {"graded": graded, "subs": subs, "untimed": untimed, "a1": a1,
            "statuses": {d["alpha"]: d["status"] for d in a1["detail"]}}


def _visible_at(row, now) -> bool:
    """A row the grading clock can see: created at or before `now`. A row with no parseable creation time
    cannot be shown to precede `now` and is left out (MEASURED 2026-09-23: 0 of the 32,656 scored rows in
    the MacBook's journal copy lack one, so this excludes nothing today)."""
    t = _created_ts(row)
    return t is not None and t <= now


def build_from(rows, scored, corr, history, curves, standard, since=None, until=None, version=None,
               now=None, axis3=None, deploys=None, data_through=None, host=None, meaning=None,
               run_config_log=None) -> dict:
    """PURE: the scorecard from data already in memory. `rows` = one row per alpha id.

    `now` is REQUIRED (A4: compare() read the wall clock, so its verdict depended on when it ran).
    `deploys` = the rows of state/deploys.jsonl, or None when not read: they give a version card its
    exposure (A3) and are reported as DORA (A9); they never enter a value.
    `data_through` = epoch seconds up to which the journal copy is complete (build() passes the file's
    mtime), or None when not stated. `host` = the machine that graded, for provenance only.
    `meaning` = the rows of state/forge/meaning.jsonl, or None when not read (D39; meaning_index).
    `run_config_log` = the rows of state/forge/run_config_log.jsonl, or None when not read: with the deploy
    ledger they give a (pipeline_version, run_config) cohort its exposure (D45, cohort_live_days).

    Window (round 1, S5): whole ET quota days. The current, unfinished quota day is never in the rate --
    a one-minute window used to 'meet' 4 per day. With `version` ("pv", "pv@run_config" or a pair;
    parse_cohort), the cohort is the rows stamped with that (pipeline_version, run_config) (D30); a cohort
    no row carries is an error, not 'all history'.

    DRAW-3 SCORING:
      * SERIOUS 1. Axis 1 (and so rank level 1) grades EVERY cohort row created on a whole quota day in
        [since, until) -- for a version card, every stamped row -- whatever the deploy ledger says. The
        ledger's live days are used ONLY for axis 2's rate: its numerator counts proven clean submissions
        of alphas created on live days, its denominator the live days. S3 measured a refuted submission
        created on V's deploy day reading refuted 0 WITH the ledger and 1 without it, so supplying more
        data hid a refutation.
      * SERIOUS 4 (this module's half). The quota day `data_through` falls in is treated exactly like the
        unfinished day: excluded from axis 1, from every rate and from the next-window judgement. The
        Mac's journal copy ended 2026-09-22T16:04 ET and was graded as if 09-22 were whole. The card
        prints the requested window beside the effective one. A LIMIT, stated: the mtime bounds when rows
        were WRITTEN, not when the alphas were created, and the lag between the two is UNMEASURED; a copy
        made without preserving mtimes (plain cp) moves the cut later than the data.
      * MINOR. The neighbour pool is bounded by `now` (_visible_at): two rows created 09-25 used to flip
        an alpha from unproven to refuted on a card graded 09-20.

    DRAW3_FIX SCORING:
      * 1 / D27. seen_until = min(now, data_through) decides post_horizon.final and the next window's
        horizon (_held_next), so a copy cut 09-15 and graded 09-30 no longer reads final; a card that is
        not final is not ranked, and `comparable_from_et` names the day it can be.
      * 2. window.coverage_gap names the whole days of the window on which the journal holds NO row at all
        (every row of every cohort, provenance's last_row_day): V11, rows to 09-12 and data_through 09-20,
        read a rate over 09-10..09-19 with nothing said. Printed only: whether nothing ran or the copy is
        incomplete cannot be told from the rows (MECHANISM: UNKNOWN), and the rate is unchanged.
      * 6. effective.rate_days / rate_first_day / rate_last_day are None when the exposure is unknown (V3
        printed "rate on 13 day(s)" for a card with no rate).
      * 14, A LIMIT: only the neighbour pool and the meaning rows are bounded by `now`. scored, corr,
        curves and the live hypothesis library are read as they stand at grading time, so re-grading an
        old card with newer stores can move it (round 2's S10-NL "freeze a D10 verdict per alpha at submit
        time" is not built). provenance names them.

    DRAW4_BUILD SCORING:
      * 5. `comparable_from_et` is comparable_from(final_at), the first ET day whose midnight is at or after the
        horizon's end; SUB.quota_day(final_at) printed a day too early across the November change.
      * 6. On a card whose exposure is unknown, window.since and window.quota_days are None, as effective.rate_days
        and axis 2's quota_days already were (p2.py: one such card read quota_days 13 and since 09-10 beside a
        rate_days of None).
    """
    if now is None:
        raise ValueError("build_from is pure: pass `now` (A4 -- a card graded against the wall clock "
                         "changed with the hour it was run)")
    today = current_quota_day(now)
    seen_until = now if data_through is None else min(now, data_through)
    scored_rows = [r for r in rows if r.get("status") in SCORED_STATUS and r.get("checks")]
    wanted = parse_cohort(version) if version else None
    if wanted:
        cohort = [r for r in scored_rows if cohort_of(r) == wanted]
        if not cohort:
            others = sorted({str(c[1]) for c in map(cohort_of, scored_rows) if c and c[0] == wanted[0]})
            raise ValueError("no scored row carries the cohort %r (pipeline_version, run_config)%s" % (
                wanted, "; pipeline_version %s has run_config(s): %s" % (wanted[0], ", ".join(others)) if others else ""))
        how = "meta.pipeline_version + meta.run_config (strong, D30)"
        # S10-NL: the neighbour pool was every scored row of every version, so version B's simulations
        # could refute or prove version A's alphas after the fact. A stamped cohort draws neighbours
        # from its own rows only.
        pool = cohort
    else:
        cohort, how, pool = scored_rows, "ET quota-day window (weak: rows are attributed by date, not by version)", scored_rows
    pool = [r for r in pool if _visible_at(r, now)]      # draw-3 scoring MINOR: nothing after the clock
    midx = meaning_index(meaning, now, _formulas(cohort)) if meaning is not None else None
    by_day = collections.defaultdict(list)
    for r in cohort:
        q = quota_day_of_row(r)
        if q:
            by_day[q].append(r)
    last = min(until or today, today)                    # never the unfinished current day
    cut_day = SUB.quota_day(data_through) if data_through is not None else None
    if cut_day is not None and cut_day < last:
        last = cut_day                                   # SERIOUS 4: nor the day the data was cut on
    covered = min(today, cut_day) if cut_day is not None else today   # first day the data does not cover whole
    graded_days = sorted(d for d in by_day if (since is None or d >= since) and d < last)
    exposure = cohort_live_days(deploys, run_config_log, wanted, now) if wanted else None     # D30, D45
    if exposure is not None and exposure["known"]:
        days = [d for d in exposure["days"] if (since is None or d >= since) and d < last]
    else:
        first = since or (min(by_day) if by_day else today)
        days = whole_days(first, last) if first < last else []
    known = exposure is None or exposure["known"]

    day_set = set(days)
    accepted = [h for h in history if h.get("http") in (200, 201)]
    g = _grade(graded_days, by_day, accepted, scored, corr, curves, standard, pool, now, midx)
    in_rate = {r["alpha"] for d in graded_days if d in day_set for r in by_day[d]}
    posts_in_window = [h for h in accepted if isinstance(h.get("posted_at"), (int, float)) and h["posted_at"] <= now
                       and SUB.quota_day(h["posted_at"]) in day_set]
    held, held_note = _held_next(days, by_day, exposure, covered, today, accepted, scored, corr, curves, standard,
                                 pool, now, seen_until, midx)
    proven = {a for a, s in g["statuses"].items() if s == "proven"}
    a2 = axis2_throughput([r for r in g["graded"] if r["alpha"] in in_rate],
                          [s for s in g["subs"] if s["alpha"] in in_rate], len(days) if known else None, proven,
                          held_next=held, posts_in_window=posts_in_window, statuses=g["statuses"])
    a2["next_window"] = held_note
    # A4: the POST horizon runs from the NEWEST GRADED ROW's day -- the last day an alpha that a POST could
    # still credit was created. Draw 2 ran it from the window's last day, so a card without a ledger
    # (window to yesterday) was censored forever and its final date moved forward every day (draw-3
    # scoring MINOR, S8). No graded row: nothing can still be credited, so the numbers are final.
    # D27 / draw3_fix scoring 1: final is judged at seen_until, never at `now` alone.
    newest = graded_days[-1] if graded_days else None
    final_at = horizon_final_at(newest) if newest else None
    a2["post_horizon"] = {"days": POST_HORIZON_DAYS, "newest_day": newest,
                          "final": final_at is None or seen_until >= final_at,
                          "final_after_et": (datetime.datetime.fromtimestamp(final_at, ET).isoformat(timespec="minutes")
                                             if final_at is not None else None),
                          "seen_until": seen_until,
                          "seen_until_et": datetime.datetime.fromtimestamp(seen_until, ET).isoformat(timespec="minutes"),
                          "comparable_from_et": comparable_from(final_at) if final_at is not None else None,
                          "posts_without_a_time": g["untimed"],
                          # D57: every graded alpha was created before the end of the newest graded day, so each
                          # has had at least this long for a POST to land and be SEEN -- up to seen_until, the
                          # clock D27 already reads POST finality at (a copy cut before `now` shows no later POST)
                          "post_exposure_days": ((seen_until - _day_start(_next_day(newest))) / DAY_S
                                                 if newest else None)}
    axes = {"axis1_product": g["a1"], "axis2_throughput": a2}
    if axis3 is not None:
        axes["axis3_gearing"] = axis3
    card = scorecard(axes)
    day_list = [d for d in (quota_day_of_row(r) for r in rows) if d]
    last_row_day = max(day_list) if day_list else None
    empty = ([d for d in whole_days(_next_day(last_row_day), last) if since is None or d >= since]
             if last_row_day and _next_day(last_row_day) < last else [])
    card["window"] = {"since": days[0] if days and known else None, "until_exclusive": last,
                      "quota_days": len(days) if known else None,
                      "version": cohort_label(wanted) if wanted else None,
                      "cohort": {"pipeline_version": wanted[0], "run_config": wanted[1]} if wanted else None,
                      "excluded_unfinished_day": today,
                      "requested": {"since": since, "until_exclusive": until},
                      "effective": {"rate_days": len(days) if known else None,
                                    "rate_first_day": days[0] if days and known else None,
                                    "rate_last_day": days[-1] if days and known else None,
                                    "axis1_first_day": graded_days[0] if graded_days else None,
                                    "axis1_last_day": newest, "until_exclusive": last},
                      "data_through": data_through,
                      "data_through_et": (datetime.datetime.fromtimestamp(data_through, ET).isoformat(timespec="seconds")
                                          if data_through is not None else None),
                      "excluded_uncovered_day": cut_day if cut_day is not None and cut_day < today else None,
                      "coverage_note": ("the journal copy was cut %s ET; that quota day (%s) is not whole and is "
                                        "excluded like the unfinished day" % (
                                            datetime.datetime.fromtimestamp(data_through, ET).isoformat(timespec="minutes"),
                                            cut_day) if cut_day is not None and cut_day < today else
                                        "data_through not stated: every day before the unfinished one is taken as whole"
                                        if data_through is None else "the data covers every day before the unfinished one"),
                      # draw5 scoring M17: the note said a rate "still counts those days" without intersecting
                      # them with the rate's own days; it now counts the ones that are
                      "coverage_gap": ({"last_row_day": last_row_day, "days": len(empty), "first": empty[0],
                                        "last": empty[-1], "in_rate_days": sum(1 for d in empty if d in day_set),
                                        "note": "the journal holds NO row at all on %d whole day(s) of the window, "
                                                "%s..%s (its last row is on %s): nothing ran, or the copy is "
                                                "incomplete -- the rows cannot say which; %d of those day(s) are "
                                                "among this card's rate days and count in its denominator"
                                                % (len(empty), empty[0], empty[-1], last_row_day,
                                                   sum(1 for d in empty if d in day_set))}
                                       if empty else None)}
    if exposure is not None:
        outside = [d for d in graded_days if d not in day_set]
        card["window"]["exposure"] = {"known": exposure["known"], "note": exposure["note"],
                                      "live_days_without_a_scored_row": sum(1 for d in days if not by_day.get(d))
                                      if exposure["known"] else None,
                                      "rows_outside_exposure": sum(len(by_day[d]) for d in outside)
                                      if exposure["known"] else None,
                                      "submissions_outside_exposure": sum(1 for s in g["subs"] if s["alpha"] not in in_rate)
                                      if exposure["known"] else None,
                                      # draw5 scoring M18: "not live" was only one of three reasons
                                      "graded_by_axis1_not_in_rate": ("rows created on %d day(s) outside the rate's days "
                                                                      "(the version not live all day, a day the "
                                                                      "run_config changed, or a day before the run_config "
                                                                      "log's first row for the cohort, D45) are graded "
                                                                      "by axis 1 and rank level 1, and left out of the "
                                                                      "rate (SERIOUS 1)"
                                                                      % len(outside)) if exposure["known"] else None,
                                      "unknown_days": exposure.get("unknown_days", []),
                                      "excluded_run_config_days": exposure.get("excluded_run_config_days", [])}
    card["version_attribution"] = how
    if deploys is not None:
        dk = dora(deploys, now=now)
        card["dora"] = {"keys": dk, "band": [{"name": n, "ok": ok, "evidence": e} for n, ok, e in dora_checks(dk)],
                        "scored": False, "why": "A9: reported only; a pre-merge gate must not depend on deploy history"}
    card["provenance"] = provenance(now, rows, history, scored, corr, curves, standard, deploys,
                                    data_through=data_through, host=host, meaning=meaning,
                                    run_config_log=run_config_log)
    card["open_ticks"] = open_ticks(card)
    return card


def _held_next(days, by_day, exposure, covered, today, accepted, scored, corr, curves, standard, pool, now,
               seen_until=None, meaning=None) -> tuple:
    """(True / False / "not evaluable", note): D7 as written -- did the rate hold in the NEXT window of
    equal length? Held = the next window also produced at least one PROVEN clean submission (the
    criterion draw 2 applied to the previous window; m1: it counted refuted POSTs as well). Whether
    "hold" should mean a rate test rather than "> 0" is not decided anywhere and is not invented here.
    `covered` is the first quota day the data does not cover whole (the unfinished day, or the day the
    journal copy was cut on, SERIOUS 4): a next window reaching it cannot be judged. D27 / draw3_fix scoring
    1: "no proven clean submission" reads False only when that window's POST horizon has closed by
    `seen_until` = min(now, data_through) (defaults to `now`), not by `now` alone -- adjv1.py: a copy cut
    09-15 and graded 09-30 read False for a next window whose POST landed 09-17, after the cut."""
    seen_until = now if seen_until is None else seen_until
    if not days:
        return "not evaluable", "no graded window"
    n = len(days)
    if exposure is not None and not exposure["known"]:
        return "not evaluable", "exposure unknown, so no next window can be placed"
    if exposure is not None:
        nxt = [d for d in exposure["days"] if d > days[-1]][:n]
        if len(nxt) < n:
            return "not evaluable", "the version was not live for a next window of %d day(s) (it has %d so far)" % (n, len(nxt))
    else:
        start = _next_day(days[-1])
        nxt = whole_days(start, (datetime.date.fromisoformat(start) + datetime.timedelta(days=n)).isoformat())
        if nxt[-1] >= today:
            return "not evaluable", "the next window %s..%s has not finished" % (nxt[0], nxt[-1])
    if nxt[-1] >= covered:
        return "not evaluable", "the next window %s..%s is not wholly covered by the data (cut on %s)" % (nxt[0], nxt[-1], covered)
    if not any(by_day.get(d) for d in nxt):
        return "not evaluable", "no scored row in the next window %s..%s: nothing ran" % (nxt[0], nxt[-1])
    g = _grade(nxt, by_day, accepted, scored, corr, curves, standard, pool, now, meaning)
    k = sum(1 for s in g["subs"] if g["statuses"].get(s["alpha"]) == "proven")
    if k:
        return True, "%d proven clean submission(s) in the next window %s..%s" % (k, nxt[0], nxt[-1])
    if seen_until < horizon_final_at(nxt[-1]):
        return "not evaluable", ("no proven clean submission yet in %s..%s and its POST horizon is still open at "
                                 "seen_until %s ET (D27)" % (nxt[0], nxt[-1], datetime.datetime.fromtimestamp(
                                     seen_until, ET).isoformat(timespec="minutes")))
    return False, "no proven clean submission in the next window %s..%s" % (nxt[0], nxt[-1])


def scorer_sha256() -> str:
    """sha256 of this file's bytes: which scorer produced a card (S10-NL)."""
    return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()


def provenance(now, rows, history, scored, corr, curves, standard, deploys, data_through=None, host=None,
               meaning=None, run_config_log=None) -> dict:
    """S10-NL: a card could not say what produced it, and it changed after the fact. The block names the
    clock it was graded at (passed in, never read), the scorer's bytes, the identity of every input by
    size and by its latest date, the journal copy's cut time, and the machine that graded (`host`, passed
    in by build(); None = not stated). Draw-3 scoring SERIOUS 4 and S10-NL: no machine held all the
    inputs, and a card could not say which machine it came from. Draw3_fix scoring 14: `not_bounded_by_now`
    names the inputs read as they stand at grading time, not as they stood at `now`."""
    days = [d for d in (quota_day_of_row(r) for r in rows) if d]
    posted = [h["posted_at"] for h in history if isinstance(h.get("posted_at"), (int, float)) and h["posted_at"] > 0]
    return {"generated_at": now,
            "generated_at_et": datetime.datetime.fromtimestamp(now, ET).isoformat(timespec="seconds"),
            "host": host,
            "scorer": "forge/offline/benchmark.py", "scorer_sha256": scorer_sha256(),
            "inputs": {"rows": len(rows),
                       "data_through": data_through,
                       "scored_rows": sum(1 for r in rows if r.get("status") in SCORED_STATUS and r.get("checks")),
                       "last_row_day": max(days) if days else None,
                       "history": len(history),
                       "accepted_posts": sum(1 for h in history if h.get("http") in (200, 201)),
                       "last_post_day": SUB.quota_day(max(posted)) if posted else None,
                       "scored": len(scored or {}), "corr": len(corr or {}), "curves": len(curves or {}),
                       "standard": None if standard is None else len(standard),
                       "meaning": None if meaning is None else len(meaning),
                       "run_config_log": None if run_config_log is None else len(run_config_log),
                       "deploys": None if deploys is None else len(deploys)},
            "not_bounded_by_now": ["scored", "corr", "curves", "standard (the live hypothesis library)",
                                   "meaning (bounded by the writer's scored_at, not by when a row was appended; "
                                   "round 4 m4)"]}


def load_curves(alphas, curves_dir=None) -> dict:
    cd = pathlib.Path(curves_dir or (ROOT / "state/pnl_curves"))
    out = {}
    for a in alphas:
        f = cd / ("%s.json" % a)
        if f.exists():
            try:
                out[a] = json.loads(f.read_text())
            except (ValueError, OSError):
                pass
    return out


def load_standard(root=ROOT) -> dict:
    """{composite id: tripped hard gates} for every composite in the live library; a hypothesis id
    that is not a composite is simply absent (its gate reads UNMEASURED).

    FAILS LOUDLY (draw-3 scoring MINOR; round 2 A5, "make load_standard fail loudly"): it used to return {}
    on ANY exception, and after A5 that silently turned every submitted alpha's standard gate to
    UNMEASURED, so every proven count read 0 and the card said nothing about why. A library that does
    not load is now an error naming both directories and the loader's own message. That message names the
    file for a malformed YAML, and does NOT for every failure: the duplicate composite-id error of
    forge/hypotheses.py's load_composites names no file (draw3_fix scoring 11). Library composites only: a
    generated alpha (D39) is graded from load_meaning's rows."""
    from forge import hypotheses as H, standard as ST
    root = pathlib.Path(root)
    lib_dir, comp_dir = root / "forge/hypotheses", root / "forge/composites"
    try:
        comps = H.load_composites(comp_dir, H.load_library(lib_dir))
    except Exception as exc:  # noqa: BLE001 -- re-raised with the paths, never swallowed
        raise RuntimeError("load_standard: the hypothesis standard could not be measured from %s and %s: %s: %s"
                           % (lib_dir, comp_dir, type(exc).__name__, exc)) from exc
    return {c.id: ST.hard_gates(c) for c in comps}


def _jsonl_as_named(p) -> list | None:
    """The JSON lines of the file at `p`, opened AS NAMED; None when `p` is not a file. Draw5 scoring M11 (V5):
    harvest.read_jsonl globs its path, so a ledger under a directory whose name holds `[1]` read is_file True and
    0 rows -- the class read_journal already fixed. A line that does not parse is skipped, as read_jsonl does."""
    p = pathlib.Path(p)
    if not p.is_file():
        return None
    out = []
    with open(p) as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def load_deploys(root=ROOT):
    """The deploy ledger's rows, or None when the file does not exist."""
    return _jsonl_as_named(pathlib.Path(root) / "state/deploys.jsonl")


def load_meaning(path=None):
    """The rows of state/forge/meaning.jsonl (D39; the schema is under MEANING_LEDGER), or None when the
    file does not exist -- "not read", which build_from keeps apart from "read, no row for this alpha"."""
    return _jsonl_as_named(path or MEANING_LEDGER)


def load_run_config_log(path=None):
    """The rows of state/forge/run_config_log.jsonl (D45; RUN_CONFIG_LOG), or None when the file does not exist
    -- "not read", which cohort_live_days keeps apart from "read, no row for this cohort"."""
    return _jsonl_as_named(path or RUN_CONFIG_LOG)


#: Round 3 S10 (the reader's half): the fields of a journal row a card reads, and nothing else. Every function
#: that takes `rows` reads only these -- the row's own keys, `settings` (cell_of, neighbourhood_stability),
#: `meta` (cohort_of, the D39 route, the D24 mechanism key; compare_arms' arm, the randomiser's `arm_by` and
#: `round` (D54, D60), the generator's `gen_route` (D54; draw5 scoring S1 fix item 1) and `seed`, which names a
#: round the randomiser did not stamp when D60 counts it) and each check's name, result and limit
#: (clears_every_binding_check, SUB.corr_lines). A reader added later that needs another field adds it here;
#: test_benchmark pins that a card built from reduced rows equals one built from whole rows.
JOURNAL_KEEP = ("alpha", "status", "dateCreated", "formula", "sharpe")
JOURNAL_KEEP_SETTINGS = ("region", "delay", "universe", "decay", "neutralization", "truncation")
JOURNAL_KEEP_META = ("pipeline_version", "run_config", "hypothesis", "mechanism_key", "arm", "arm_by", "round",
                     "gen_route", "seed")
JOURNAL_KEEP_CHECK = ("name", "result", "limit")


def _reduced(r, shared) -> dict:
    """A journal row reduced to JOURNAL_KEEP*; a sub-map the row does not carry stays absent. A check reduced to
    its name, result and limit is taken from `shared`, so rows holding the same check share ONE dict: nothing in
    this module or in SUB.corr_lines writes to a check (read 2026-09-23), and a reader that did would change every
    row holding it."""
    out = {k: r[k] for k in JOURNAL_KEEP if k in r}
    for key, keep in (("settings", JOURNAL_KEEP_SETTINGS), ("meta", JOURNAL_KEEP_META)):
        if isinstance(r.get(key), dict):
            out[key] = {k: r[key][k] for k in keep if k in r[key]}
        elif key in r:
            out[key] = r[key]
    if "checks" in r:
        checks = r["checks"]
        if isinstance(checks, list):
            checks = [c if not isinstance(c, dict) else _shared_check(c, shared) for c in checks]
        out["checks"] = checks
    return out


def _shared_check(c, shared) -> dict:
    key = tuple((k, c[k]) for k in JOURNAL_KEEP_CHECK if k in c)
    try:
        return shared.setdefault(key, dict(key))
    except TypeError:                          # an unhashable value (a list as `limit`): not shared
        return dict(key)


def read_journal(path) -> tuple:
    """(rows, exists): one row per alpha id, the journal's LAST row winning, each reduced to the fields a card
    reads (_reduced), read line by line.

    Round 3 S10 (/usr/bin/time -l, real build(run_drill=False)): peak RSS was 741 MB on the Mac's 115.7 MB journal
    and 1,938 MB on a 3x synthetic, ~5.2 MB of RSS per MB of journal, while the host journal grows ~48 MB a day
    and D41 runs the judge beside the loop. EX-ANTE from the code: harvest.read_jsonl parsed EVERY line into one
    list before the last-row-wins pass, and every row kept every field. MEASURED 2026-09-23 on this Mac (journal
    115,746,339 bytes, 32,662 alpha ids; tracemalloc, the rows alone): the old reader retained 505 MB, the reduced
    rows 160 MB, and with identical checks shared (755 distinct check dicts) 59 MB. Peak RSS of the whole
    build(run_drill=False) on that journal (/usr/bin/time -l, two runs each): 735.7 and 737.1 MB before, 235.2 and
    234.1 MB after; a later journal moves both. Second derivation: on that journal the date card built from the
    reduced rows equals, as JSON, the card built from the whole rows (three windows), and 37 of 32,656 scored rows
    clear every binding check either way. The path is opened as given: harvest.read_jsonl globbed it, so a journal
    named forge[1].jsonl read 0 rows (draw4_build scoring, verified-not-blocking).
    STILL LINEAR, stated: one reduced row per distinct alpha id is kept, since the neighbour pool needs every row.
    Streaming by quota day (round 3 S10's other option) is not built."""
    p = pathlib.Path(path)
    if not p.is_file():
        return [], False
    latest, shared = {}, {}
    with open(p) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("alpha"):
                latest[r["alpha"]] = _reduced(r, shared)
    return list(latest.values()), True


def load_inputs(journal=None, curves_dir=None) -> dict:
    """Every input build_from() and compare() take, read from disk: one row per alpha id (the journal's
    last row wins; read_journal), the POST history, the scored/corr stores, the accepted alphas' PnL curves, the
    hypothesis standard, the meaning rows (D39), the run_config log (D45) and the deploy ledger -- plus
    `data_through`, the journal copy's mtime (SERIOUS 4: the cut time of the copy, so the day it was cut on is
    never graded as whole).

    Draw3_fix scoring 5: a MISSING journal used to raise FileNotFoundError from stat(), and the CI step that
    runs this scorer ends in `|| true`, which hid the crash. It now reads as no rows, `data_through` None and
    `journal_exists` False; build() turns that into a gap line."""
    path = pathlib.Path(journal or HV.JOURNAL)
    rows, exists = read_journal(path)
    from forge import probe as P
    history = SUB.posted_history()
    posted = {h["alpha"] for h in history if h.get("http") in (200, 201)}
    return {"journal": str(path), "journal_exists": exists, "data_through": path.stat().st_mtime if exists else None,
            "rows": rows, "history": history, "scored": HV.load_scored(), "corr": P.load_corr(),
            "curves": load_curves(posted, curves_dir), "posted": posted, "standard": load_standard(),
            "meaning": load_meaning(), "run_config_log": load_run_config_log(), "deploys": load_deploys()}


def build(journal=None, since=None, until=None, version=None, curves_dir=None, run_drill=True, now=None) -> dict:
    """The scorecard from the files on disk and the wall clock (the only impure part): the clock, the
    host name and the journal copy's mtime are read HERE and passed into build_from as arguments.

    THE GAPS (printed, never scored). Draw3_fix scoring 12: the cohort gap cleared on ANY truthy stamp --
    `unknown`, `+untracked`, `+MISMATCH` -- and on a single cohort, while the VPS held one value and
    compare() could not run. It now counts distinct PLAIN cohorts (D30, cohort_of) among the scored rows,
    with a gap for 0 and a gap for 1. Draw3_fix scoring 5: a journal missing on this host is a gap.
    Draw4_build scoring 6 (p4.py): the no-cohort gap called a row with plain pipeline_version "V" and run_config 5
    one "carrying a suffixed or marker stamp", and said no row carried a plain pipeline_version; it now counts
    rows whose stamp PAIR forms no cohort and says so."""
    now = now if now is not None else __import__("time").time()
    x = load_inputs(journal, curves_dir)
    card = build_from(x["rows"], x["scored"], x["corr"], x["history"], x["curves"], x["standard"], since=since,
                      until=until, version=version, now=now, axis3=axis3_gearing(run_drill=run_drill),
                      deploys=x["deploys"], data_through=x["data_through"], host=socket.gethostname(),
                      meaning=x.get("meaning"), run_config_log=x.get("run_config_log"))
    scored = [r for r in x["rows"] if r.get("status") in SCORED_STATUS and r.get("checks")]
    cohorts = sorted({c for c in map(cohort_of, scored) if c}, key=lambda c: (c[0], str(c[1])))
    unplain = sum(1 for r in scored if (r.get("meta") or {}).get("pipeline_version") and not cohort_of(r))
    generated = sum(1 for r in scored if str((r.get("meta") or {}).get("hypothesis") or "").startswith(GENERATED_PREFIX))
    dk = (card.get("dora") or {}).get("keys") or {}
    no_curve = sorted(x["posted"] - set(x["curves"]))
    card["gaps"] = [g for g in (
        None if x.get("journal_exists", True) else
        "The journal %s does not exist on this host: no row was graded and data_through is not stated." % x["journal"],
        "No scored row of the journal copy %s (cut %s) carries a stamp pair that forms a cohort (%d carry a "
        "meta.pipeline_version whose pair forms none: a suffixed or marker pipeline_version or run_config, or a "
        "run_config that is not a string, D30); attribution is by date and the post-deploy comparison has no "
        "cohorts." % (x["journal"], card["window"]["data_through_et"], unplain) if not cohorts else
        "Exactly one cohort (%s) among the scored rows of %s (cut %s): compare() needs two, so no post-deploy "
        "comparison can run." % (cohort_label(cohorts[0]), x["journal"], card["window"]["data_through_et"])
        if len(cohorts) == 1 else None,
        None if dk.get("status") == "measured" else "DORA is unmeasured: fewer than two recorded deploys.",
        None if not no_curve else "Axis 1's regime gate needs each submitted alpha's PnL curve; %d of %d accepted "
                                  "alpha(s) have none in %s on this host and read UNMEASURED: %s"
                                  % (len(no_curve), len(x["posted"]), curves_dir or (ROOT / "state/pnl_curves"),
                                     ", ".join(no_curve[:8]) + (" ..." if len(no_curve) > 8 else "")),
        None if x.get("meaning") is not None or not generated else
        "%s does not exist on this host: the %d generated (gen:) scored alpha(s) read D10's gate half UNMEASURED "
        "(D39)." % (MEANING_LEDGER, generated),
    ) if g]
    return card


#: A2: every card recorded with --record is APPENDED here, one JSON line each, provenance included.
CARDS_LEDGER = ROOT / "state/benchmark/cards.jsonl"


def _json_safe(x):
    """`x` with every non-finite float replaced by a string ("inf", "-inf", "nan"), so json.dumps can run
    with allow_nan=False. Draw3_fix scoring 7 (V5): a steady curve's regime thirds hold float("inf") (an
    unbounded Sharpe), and the ledger line held the bare token Infinity, which a strict JSON parser rejects."""
    if isinstance(x, float) and not math.isfinite(x):
        return "nan" if math.isnan(x) else ("inf" if x > 0 else "-inf")
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    return x


def record_key(card: dict) -> dict:
    """D41: what makes two recorded cards the SAME record -- the cohort (a version card's (pipeline_version,
    run_config); a date card's requested window), the ET quota day it was graded on, and the host."""
    w, pv = card.get("window") or {}, card.get("provenance") or {}
    return {"cohort": w.get("cohort") or {"date_window": w.get("requested"), "version": w.get("version")},
            "graded_et_day": SUB.quota_day(pv["generated_at"]) if isinstance(pv.get("generated_at"), (int, float)) else None,
            "host": pv.get("host")}


def record_card(card: dict, path=None) -> tuple:
    """A2 (architecture round 2, S10-NL: "no card ledger exists"): append the card as ONE JSON line, and
    return (path, appended?).

    Append-only: an earlier line is never rewritten. A card without provenance is refused -- a ledger line
    that cannot say what produced it is the defect S10-NL named.
    D41 (Khoa, 2026-09-23): IDEMPOTENT per (cohort, graded ET day, host) (record_key): when the ledger
    already holds a card with this key, nothing is appended and `appended` is False. The file is read for
    that under an exclusive lock, so two runs at once cannot both append.
    Draw3_fix scoring 7: the line is strict JSON (_json_safe, allow_nan=False), and when the file's last
    byte is not a newline (an earlier append cut short) one is written first, so this line is whole on its
    own line.

    THE DRAWING'S FINDINGS 8-9 (docs/evalharness/01_architecture.md, draw 4 section 1 "What the judge would grade"
    and section 4 item 2):
      * A RECORDED CARD NAMES ITS COHORT. D1 and D14 grade a pipeline VERSION; wq-judge.sh's `--record` with no
        --version recorded build(version=None), the WEAK date-window card that pools every cohort and every
        unstamped row, filed under {"date_window": {"since": null, ...}}. A card whose window names no
        (pipeline_version, run_config) cohort is now refused here, and main() refuses --record without --version.
        Which cohort the daily judge records is NOT decided here (the drawing: "decided nowhere").
      * RECORDING NEVER ASKS WHETHER THE CARD CAN BE RANKED. At the judge's 00:30 ET clock the newest graded day's
        POST horizon is open, so rank_key() raises NotComparable on every card the judge appends (section 4 item
        2(b)); nothing here calls rank_key, and the line carries rank.comparable_from_et so a reader knows when a
        re-grade of the same cohort can be ranked. A recorded line is never re-graded in place."""
    import fcntl
    if not isinstance(card.get("provenance"), dict):
        raise ValueError("record_card: the card carries no provenance, so it is not recorded")
    if not isinstance((card.get("window") or {}).get("cohort"), dict):
        raise ValueError("record_card: the card names no cohort (a date-window card grades no version, D1/D14), "
                         "so it is not recorded; grade a cohort with --version PV or PV@RUN_CONFIG")
    p = pathlib.Path(path or CARDS_LEDGER)
    p.parent.mkdir(parents=True, exist_ok=True)
    key = record_key(card)
    line = json.dumps(_json_safe(card), default=str, sort_keys=True, allow_nan=False)
    with p.open("a+b") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        for raw in fh:
            try:
                old = json.loads(raw)
            except ValueError:
                continue
            if isinstance(old, dict) and record_key(old) == key:
                return p, False
        fh.seek(0, 2)
        if fh.tell():
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                fh.write(b"\n")
        fh.write(line.encode() + b"\n")
    return p, True


#: Round 3 F1, printed on every compare() result BEFORE its verdict (the version-against-version read-out is
#: not the proof of a mechanism; compare_arms() is, under D47). Draw5 scoring M22: the 0.49-0.56 range was
#: attributed to the bootstrap alone; it spans round 3 F1's three models (architecture_round3.md, F1 table).
COMPARE_IS_NOT_GATE3 = (
    "NOT RULE 2 gate-3 evidence (round 3 F1; D47 superseded D33). Two versions run one after the other, so every "
    "ET day belongs to one arm and the between-day variation of the estimand lands in the comparison: within USA/d1 "
    "the dispersion across days was 11.34 on both the Mac and the host journal copies (95 %% interval [5.4, 37.8]), "
    "and under NO version effect this read-out said better or worse in 0.49-0.56 of placebo draws across three null "
    "models (%s), more days not reducing it. MECHANISM of the day-level variation: UNKNOWN. A branch is proven by "
    "compare_arms() on rounds randomised within each ET day."
    % "a day-block bootstrap of the 9 real days 0.488 at 7 days per arm, 0.501 at 14, 0.486 at 28; gamma-Poisson days "
      "at phi 11.34 0.540 and 0.547; the closed form 2(1 - Phi(1.96 / sqrt(phi))) 0.561")


def compare(rows, history, curves, standard, scored, corr, version_a, version_b, *, now, deploys=None,
            data_through=None, meaning=None, run_config_log=None) -> dict:
    """Post-deploy: did version B do better than version A on the PRE-REGISTERED estimand, WITHIN cell?
    (D24, D28) FOR VERSION AGAINST VERSION ONLY, AND NEVER GATE-3 EVIDENCE (COMPARE_IS_NOT_GATE3, printed first on
    every result): under D47 a branch is proven by compare_arms().

    THE ESTIMAND (ESTIMAND, fixed before any comparison): alphas clearing EVERY binding check per 1,000
    scored alphas. IT IS NOT THE SUBMISSION COUNT, and the output says so. A1: on submissions, at the
    desk's 0.211 per quota day, a version that produced nothing read "worse" after 7 days with
    probability 2.4e-5 -- the comparison was blind for a version's whole lifetime.

    Per arm: the scored alpha ids of the arm's COHORT (D30: `version_a` / `version_b` are "pv",
    "pv@run_config" or a pair, parse_cohort; `versions` is keyed by cohort_label) created on a whole ET
    quota day before the one `now` falls in (and before the day `data_through` falls in, SERIOUS 4); its
    k/n per cell and pooled; an exact Poisson interval per 1,000 on the pooled count (display).

    THE VERDICT (D28, Khoa 2026-09-23 ~15:30): the exact conditional test STRATIFIED BY CELL
    (stratified_rate_test_p over the cells both arms scored in) at ESTIMAND["alpha"]. better / worse only
    when that test is significant AND every cell with at least one event points the same way; otherwise
    indistinguishable, and `why` says which condition failed. AS READ HERE, because the tick's words do not
    settle it (printed in verdict_text, open for Khoa): a cell with an event that ONE arm never scored in
    has no direction, and a tie points no way; either one makes the verdict indistinguishable. `p_value`
    and `rate_ratio_b_over_a` (the Mantel-Haenszel rate ratio over the shared cells -- Rothman, Greenland &
    Lash, Modern Epidemiology, EX-ANTE) are within cell; `pooled` holds the pooled test's p and ratio,
    printed and NEVER deciding. Before D28 the pooled test decided, across cells whose share of a day
    ranged 0.32-0.94 with all 37 events in USA/d1 (draw-3 scoring SERIOUS 6; RULE 0 #6).

    The DESIGN, printed with every result: SEQUENTIAL -- D21 replaces a version wholesale, so there is no
    concurrent control and anything that changed with the calendar is confounded with the version; the
    calendar gap between the windows is printed. The test assumes independent alphas. POST-HOC (X1):
    per-day counts of qualified rows were overdispersed (3,6,12,0,0,1,13,1,1,0). MEASURED 2026-09-23 on the
    forge journal, normalised by each day's scored volume (37 of 32,656 over 10 active days): dispersion
    11.43, chi-square 102.9 on 9 df. Re-measured by the draw3_fix scoring engineer WITHOUT 2026-09-22 -- a day
    the Mac copy covers only to 16:04 ET, which the scorer now excludes (draw3_fix scoring 11): 37 of 31,039
    over 9 days, dispersion 11.99, chi-square 95.96 on 8 df (the same by this module's _dispersion and by an
    exact-fraction recount). That is an OBSERVATION, with three candidate readings: a rate that varies from day
    to day, outcomes clustered within a day, and a cell mix that shifts by day (draw-3 scoring MINOR: this
    paragraph used to name one of them as the finding). ROUND 3 F1 MEASURED WITHIN CELL (re-derived by its
    adjudicator with code independent of this module): inside USA/d1, which holds all 37 events, the dispersion
    is 11.34 on the Mac copy (9 days) and 11.34 on the host copy (10 days), so the third reading does not
    account for it; between rounds WITHIN a day it is 1.03 (chi-square 132.3 on 129 df, POST-HOC) -- a statistic
    with no power at these counts (round 4 F1: its exact within-day null has median 0.666, and 1.03 sits at
    P = 0.108), while the round-weighted statistic reads 2.235 times its null mean (_round_clustering). Which holds
    is UNMEASURED as between the other two readings; MECHANISM: UNKNOWN. The consequence is
    measured, not inferred: under no version effect this sequential read-out says better or worse about half
    the time (COMPARE_IS_NOT_GATE3), so the interval, the p-value and the minimum detectable ratio below are
    too optimistic at that dispersion (draw3_fix scoring 11 had held "too optimistic" back for want of a
    within-cell measurement; round 3 F1 is that measurement). Each arm's per-day counts and dispersion are
    printed; F1's decisive pair (09-04..06 against 09-07..09, stratified p 6.5e-10, "worse") printed 0.09 and
    0.96, because a step BETWEEN windows is invisible to a dispersion computed WITHIN each.

    THE MINIMUM DETECTABLE RATIO is the POOLED test's, at the pooled exposures; the within-cell test's power
    is NOT computed. The two tests are one test when every scored alpha lies in one cell.

    THE VERDICT WORDS STAY "better" / "worse" (draw5 scoring M16, recorded rather than relabelled): D47 superseded
    round 3 F1's item 1 for compare(), which stays for version against version with COMPARE_IS_NOT_GATE3 printed
    BEFORE its verdict; under no effect those words are wrong 0.49-0.56 of the time, and nothing automated reads them.

    The submission reading is SECONDARY and carries no verdict. A4: it counts POSTs within
    POST_HORIZON_DAYS of creation and is withheld ("censored") until that horizon has elapsed, at
    seen_until = min(now, data_through) (D27), for the arm's newest graded day; A3: its per-day rate uses
    the ledger's live days or says "exposure unknown". The primary estimand contains no POST, so the
    horizon does not delay it.
    """
    today = current_quota_day(now)
    cut_day = SUB.quota_day(data_through) if data_through is not None else None
    bound = min(today, cut_day) if cut_day is not None else today
    per = ESTIMAND["per"]
    names = ESTIMAND["binding_checks"]
    ca, cb = parse_cohort(version_a), parse_cohort(version_b)
    arms = {}
    for co in (ca, cb):
        latest = {}
        for r in rows:
            if (cohort_of(r) == co and r.get("status") in SCORED_STATUS
                    and r.get("checks") and r.get("alpha")):
                d = quota_day_of_row(r)
                if d and d < bound:
                    latest[r["alpha"]] = (d, r)
        per_day = collections.defaultdict(lambda: [0, 0])
        per_cell = collections.defaultdict(lambda: [0, 0])
        for d, r in latest.values():
            hit = int(clears_every_binding_check(r, names))
            for bucket in (per_day[d], per_cell[cell_of(r)]):
                bucket[0] += hit
                bucket[1] += 1
        k = sum(x[0] for x in per_day.values())
        n = sum(x[1] for x in per_day.values())
        arms[co] = {"k": k, "n": n, "per_day": dict(sorted(per_day.items())), "per_cell": dict(sorted(per_cell.items()))}
    out = {"estimand": ESTIMAND["name"], "estimand_is_not": ESTIMAND["not_the_submission_count"],
           "not_gate3_evidence": COMPARE_IS_NOT_GATE3,
           "graded_at": now, "excluded_unfinished_day": today,
           "data_through": data_through,
           "excluded_uncovered_day": cut_day if cut_day is not None and cut_day < today else None,
           "versions": {}}
    for co in (ca, cb):
        a = arms[co]
        entry = {"cohort": {"pipeline_version": co[0], "run_config": co[1]},
                 "scored_alphas": a["n"], "clearing_every_binding_check": a["k"], "per_day": a["per_day"],
                 "per_cell": a["per_cell"],
                 "window": [min(a["per_day"]), max(a["per_day"])] if a["per_day"] else None}
        if a["n"]:
            lo, hi = poisson_interval(a["k"], a["n"] / per)
            entry.update({"per_1000": round(a["k"] / a["n"] * per, 3),
                          "exact_95_per_1000": [round(lo, 3), round(hi, 3)],
                          "dispersion_across_days": _dispersion(a["per_day"])})
        out["versions"][cohort_label(co)] = entry
    A, Bv = arms[ca], arms[cb]
    out["cell_mix"] = cell_mix(A["per_cell"], Bv["per_cell"])
    out["cell_mix_differs"] = out["cell_mix"]["differs"]
    if not A["n"] or not Bv["n"]:
        out["verdict"] = "no-data"
        out["why"] = "an arm has no scored alpha of its cohort on a whole ET quota day"
        out["verdict_text"] = verdict_text(out)
        return out
    cells = {}
    for c in sorted(set(A["per_cell"]) | set(Bv["per_cell"])):
        (ka, na), (kb, nb) = A["per_cell"].get(c, (0, 0)), Bv["per_cell"].get(c, (0, 0))
        cells[c] = {"a": [ka, na], "b": [kb, nb], "events": ka + kb,
                    "direction": ("no event" if not ka + kb else "one arm only" if not (na and nb) else
                                  "B higher" if kb * na > ka * nb else "B lower" if kb * na < ka * nb else "equal")}
    shared = [(v["a"][0], v["a"][1], v["b"][0], v["b"][1]) for v in cells.values() if v["a"][1] and v["b"][1]]
    p = stratified_rate_test_p(shared)
    dirs = {v["direction"] for v in cells.values() if v["events"]}
    direction = "better" if dirs == {"B higher"} else "worse" if dirs == {"B lower"} else None
    num = sum(kb * na / (na + nb) for ka, na, kb, nb in shared)
    den = sum(ka * nb / (na + nb) for ka, na, kb, nb in shared)
    ra, rb = A["k"] / A["n"], Bv["k"] / Bv["n"]
    out["cells"] = cells
    out["rate_ratio_b_over_a"] = round(num / den, 3) if den else None
    out["p_value"] = round(p, 5)
    out["alpha"] = ESTIMAND["alpha"]
    out["pooled"] = {"p_value": round(rate_test_p(A["k"], A["n"], Bv["k"], Bv["n"]), 5),
                     "rate_ratio_b_over_a": round(rb / ra, 3) if ra else None,
                     "decides": False, "why": "D28: printed, never deciding"}
    out["verdict"] = "indistinguishable" if p > ESTIMAND["alpha"] or direction is None else direction
    out["why"] = ("the within-cell test is not significant (p = %s > %.2f)" % (out["p_value"], ESTIMAND["alpha"])
                  if p > ESTIMAND["alpha"] else
                  "significant within cell, but the cells with an event do not all point the same way: %s"
                  % ", ".join("%s %s" % (c, v["direction"]) for c, v in cells.items() if v["events"])
                  if direction is None else
                  "significant within cell, and every cell with an event has B %s"
                  % ("higher" if direction == "better" else "lower"))
    out["verdict_text"] = verdict_text(out)
    base = (A["k"] + Bv["k"]) / (A["n"] + Bv["n"])
    mdr = minimum_detectable_ratio(A["n"], Bv["n"], base)
    mdr["baseline_per_1000"] = round(base * per, 3)
    mdr["scope"] = "the POOLED test at the pooled exposures; the within-cell test's power is not computed"
    mdr["statement"] = _mdr_statement(mdr, A["n"], Bv["n"])
    out["minimum_detectable_ratio"] = mdr
    wa, wb = out["versions"][cohort_label(ca)]["window"], out["versions"][cohort_label(cb)]["window"]
    fa, la, fb, lb = (datetime.date.fromisoformat(x) for x in (wa[0], wa[1], wb[0], wb[1]))
    if fb > la:
        gap = (fb - la).days - 1
        said = "B's window starts %d calendar day(s) after A's ends" % gap
    elif fa > lb:
        gap = (fa - lb).days - 1
        said = "B's window ENDS %d calendar day(s) before A's starts" % gap
    else:
        gap = -((min(la, lb) - max(fa, fb)).days + 1)
        said = "the two windows OVERLAP on %d day(s)" % -gap
    out["calendar"] = {"a": wa, "b": wb, "gap_days": gap, "statement": said}
    out["design"] = ("sequential, confounded by calendar date: D21 replaces a version wholesale, so there is no "
                     "concurrent control; the test assumes one rate per arm across days, which the between-day "
                     "dispersion measured in round 3 F1 contradicts (see not_gate3_evidence and dispersion_across_days)")
    out["submissions_secondary"] = {cohort_label(co): _submission_reading(rows, history, curves, standard, scored, corr,
                                                                          co, now, deploys, data_through=data_through,
                                                                          meaning=meaning, run_config_log=run_config_log)
                                    for co in (ca, cb)}
    return out


# --------------------------------------------------- D47, D54, D55, D60: the branch against the incumbent, by round
#: D47 (Khoa, 2026-09-23 ~21:00), SUPERSEDING D33: the branch is proven by randomising ROUNDS within each ET day
#: 50/50 (D53) between the incumbent (`--mode composites`) and the branch; the runner's `--mode randomised` picks a
#: round's arm from sha256("<ET day>:<seed>") (the shared interface). (A, B) = (incumbent, branch); "better" means
#: the branch's rate is higher.
ARMS = ("composites", "gen")
#: D54 and D60 (Khoa, 2026-09-24 ~02:20; round 4 S3): only rounds the randomiser assigned are compared. The runner
#: stamps every construction of a randomised round with meta.arm, meta.arm_by = ARMS_ASSIGNED_BY and meta.round (the
#: round's seed); a round planned with an explicit --mode carries arm_by "explicit". Round 4 S3 (g1_pA.py): recipe
#: rounds of forge/search.py (ROUNDS=1, --mode composites) were stamped arm "composites" and entered arm A, and one
#: 0-hit recipe round a day read "better", p = 0.011. Draw5 scoring M15: vps/forge.env ships `--ab new` and
#: runner.stamp() keeps an arm already set, so rows planned that way read meta.arm "current" / "new"; they are
#: EXCLUDED and counted like every other round the randomiser did not assign (D60), never compared.
ARMS_ASSIGNED_BY = "randomiser"
#: D54 (draw5 scoring S1): in the branch only FRESH generator draws are in the estimand. A D51 neighbour and a D37
#: repair are keyed on the branch's own earlier rows (forge/gen/propose.py), which the incumbent has no counterpart
#: of; counted in arm B they read "better" in 0.285-0.51 of no-effect draws (draw5 scoring S1, V2). They, and a
#: branch row with any other meta.gen_route or none, are reported BESIDE the comparison.
ARMS_FRESH_ROUTE = "fresh"
#: D55 (Khoa, 2026-09-24 ~02:20; round 4 S1): the looks, counted in SHARED days -- whole ET days on which both arms ran
#: a randomiser-assigned round. Look k reads every round up to the (ARMS_LOOK_DAYS[k-1])-th shared day. THIS MODULE'S
#: READING of "every 7 days", open for Khoa (open_ticks): shared days, not calendar days, so a day on which one arm ran
#: no round (an outage, or the coin) spends no look. Round 4 S1 measured daily looks at a fixed 0.05 accumulating
#: 0.131 false verdicts by day 28.
ARMS_LOOK_DAYS = (7, 14, 21, 28)
#: No verdict before the first look (D55). Draw5 scoring M14: the 5 this replaces had no decision on file.
MIN_SHARED_DAYS = ARMS_LOOK_DAYS[0]
#: D55: O'Brien & Fleming (1979) boundaries for 4 equally spaced looks at a total two-sided alpha of 0.05 -- reject at
#: look k when |Z_k| >= C sqrt(4 / k), a CONSTANT boundary C sqrt(4) on the partial-sum scale. C is SOLVED so that the
#: canonical Gaussian random walk (independent, equal information increments) crosses with probability exactly 0.05;
#: three ways, each re-run 2026-09-24 and agreeing:
#:   way 1, the Armitage-McPherson-Rowe recursion by Simpson's rule (scratchpad d6_scoring_ev/obf.py): 2.024296 on a
#:     400-point grid, 2.024295 on 800;
#:   way 2, a Monte Carlo of the walk (same script, 400,000 draws, seed 1) at C = 2.0243: crossing 0.05056 +- 0.00034;
#:   way 3, independent of both (scratchpad d6s_ev/obf_mvn.py): the joint normal law of (Z_1..Z_4), corr sqrt(j / k),
#:     integrated over the continuation box by scipy's multivariate-normal CDF (Genz) and bisected: C = 2.024296,
#:     crossing 0.0500 at it; the same code at one look returns 1.959964 (the control).
#: The tabulated classical value (Jennison & Turnbull 2000, Table 2.3) is 2.024. test_benchmark re-derives ways 1 and 2
#: in the suite, with the standard library only, as this module uses. THIS MODULE'S READING of "O'Brien-Fleming-type":
#: the classical constant boundary above, not a Lan-DeMets spending function (no spending boundary was computed here).
#: LIMIT, stated: the permutation statistic's increments between looks are independent across days (each day is
#: relabelled on its own) but not of equal information, and its p is discrete; the procedure's size is therefore
#: MEASURED (test_benchmark's placebo and generator), not assumed from the Gaussian model.
ARMS_OBF_C = 2.024296
#: The boundaries on the z scale -- 4.0486, 2.8628, 2.3375, 2.0243 -- and the NOMINAL two-sided p a look must reach,
#: 5.153e-05, 0.004199, 0.01942, 0.04294: the form the permutation p is compared in.
ARMS_BOUNDARY_Z = tuple(ARMS_OBF_C * math.sqrt(len(ARMS_LOOK_DAYS) / k) for k in range(1, len(ARMS_LOOK_DAYS) + 1))
ARMS_NOMINAL_P = tuple(math.erfc(z / math.sqrt(2.0)) for z in ARMS_BOUNDARY_Z)
#: The permutation p is a SEQUENTIAL Monte Carlo p-value (Besag & Clifford, Biometrika 1991, 78:301-304; EX-ANTE):
#: relabellings are drawn until ARMS_PERM_EXCEED of them are at least as extreme as the observed statistic (p = that
#: count / the draws) or ARMS_PERM_MAX - 1 are drawn (p = (extreme + 1) / ARMS_PERM_MAX). ARMS_PERM_MAX = 100,000 lets
#: p reach 1e-5, under look 1's nominal 5.15e-5; ARMS_PERM_SEED + the look's index seeds each look, so a card is
#: reproducible. They bound precision and computation, not inference.
ARMS_PERM_EXCEED = 20
ARMS_PERM_MAX = 100_000
ARMS_PERM_SEED = 20260924
#: D54's placebo, MEASURED 2026-09-24 and pinned by forge/tests/test_benchmark.py (seeds and draws declared before any
#: run with them: scratchpad d6s_ev/placebo_declaration.txt): the share of draws reading better or worse under NO
#: effect, every round's arm reassigned by a fair coin over the desk's OWN rounds (the Mac journal copy's 187 rounds of
#: 9 whole ET days, 37 D24 events; test_benchmark.DESK_ROUNDS, derived two ways). What each reads:
#:   desk_days_read_out ................. compare_arms' read-out itself on the 9 real days (4,000 draws). Only look 1
#:                                        (7 shared days, nominal 5.15e-05) is reachable in 9 days, so this is weak;
#:   desk_days_one_look ................. the round-unit test at ONE look at 0.05 over every shared day, the same
#:                                        draws: round 4 F1's placebo, where the alpha-unit test read 0.155;
#:   desk_days_alpha_unit_control ....... that alpha-unit decision on the same draws (the placebo's teeth);
#:   desk_days_resampled_to_28_read_out . the four looks on whole desk days dealt with replacement to 28 shared days
#:                                        (2,000 draws) -- a model of more days like the desk's, not 28 real days;
#:   clustered_generator_* .............. test_benchmark._clustered_rounds (between-day phi 11, within-round clustering
#:                                        5.09 x the exchangeable null against the desk's 2.235), 28 days, 1,000 draws.
#: POST-HOC, read with its noise: one look reads 0.052 and the resampled read-out 0.0525, each within one standard error
#: (0.0035, 0.0049) of 0.05; a 16,000-draw diagnostic of the one-look test read 0.0517 with this fixed permutation seed
#: and 0.0498 with the seed varied per draw. The test is calibrated AT its nominal level: D54's "<= 5 %" holds on the
#: first reading and is NOT SHOWN on the one-look and resampled readings, and no placebo can show it while the design
#: spends exactly 0.05. Whether to design below 0.05 is open for Khoa (open_ticks). MECHANISM of the 0.002 and 0.0025
#: excesses: none claimed -- each is inside the placebo's own sampling error.
ARMS_PLACEBO = {
    "desk_days_read_out": 0.00025,
    "desk_days_one_look": 0.052,
    "desk_days_alpha_unit_control": 0.1565,
    "desk_days_resampled_to_28_read_out": 0.0525,
    "clustered_generator_28_read_out": 0.042,
    "clustered_generator_alpha_unit_control": 0.319,
}
#: PRE-REGISTERED before any arm row existed. D47's first design (the alpha as the unit) was registered 2026-09-23 when
#: the Mac journal copy's 36,855 rows held no meta.arm "composites" or "gen" (None 20,435, current 8,856, new 6,180,
#: typed 980, pow15 150, pow2 150, R/RS/RV 32 each, S 8). THIS amendment (D54, D55, D60) was written 2026-09-24 after a
#: read-only count of the host journal (ssh -n, grep -c) at 2026-09-24T04:20Z: 43,382 lines, 0 carrying arm "gen" or
#: "composites", 0 carrying arm_by, 0 carrying gen_route, 0 carrying round -- so no arm comparison had been, or could
#: have been, read. The estimand is D24's, unchanged (ESTIMAND).
ARMS_DESIGN = {
    "estimand": ESTIMAND["name"],
    "arms": ("meta.arm %r (A, the incumbent) against %r (B, the branch), within ONE pipeline_version; only rounds whose "
             "meta.arm_by is %r (D54, D60), each identified by meta.round; B's estimand rows are those with "
             "meta.gen_route %r, and its other rows are reported beside (D54)"
             % (ARMS[0], ARMS[1], ARMS_ASSIGNED_BY, ARMS_FRESH_ROUTE)),
    "unit": "the ROUND (D54): a randomised round's rows, placed on the ET day of its earliest row; each round "
            "contributes its D24 rate in each cell",
    "stratum": "(ET quota day, cell), cell = <region>/d<delay> (D28), over whole ET days before the one `now` and "
               "`data_through` fall in",
    "test": ("permutation test of the arm labels across the rounds of each ET day, the day's number of B rounds kept. "
             "Statistic S = the sum over B rounds r of e_r, e_r = the sum over cells c of n_rc (k_rc / n_rc - K_dc / "
             "N_dc): the round's D24 rate in each cell against its (day, cell) rate, weighted by its scored count. "
             "Two-sided p = P(|S*| >= |S|) over relabellings, a sequential Monte Carlo p (ARMS_PERM_*)"),
    "looks": ("group-sequential (D55): looks at %s shared whole ET days (both arms ran a round that day), at most %d; "
              "look k reads every round up to its last shared day; O'Brien-Fleming boundary |Z_k| >= %.4f sqrt(%d / k), "
              "read as nominal p %s; total two-sided alpha %.2f"
              % ("/".join(map(str, ARMS_LOOK_DAYS)), len(ARMS_LOOK_DAYS), ARMS_OBF_C, len(ARMS_LOOK_DAYS),
                 "/".join("%.4g" % p for p in ARMS_NOMINAL_P), ESTIMAND["alpha"])),
    "decides": ("better / worse at the FIRST look whose p is at or under its nominal p AND at which every CELL with an "
                "event in a (day, cell) stratum both arms scored in points strictly the same way (a cell's direction: "
                "the sign of the sum over B rounds of its n_rc (k_rc / n_rc - K_dc / N_dc)); that verdict is final. "
                "Withheld before the first look, and after a look without such a crossing while looks remain. "
                "Indistinguishable when the last look has none. Rounds after the last look's day are not read"),
    "alpha": ESTIMAND["alpha"],
    "placebo": ("before any read-out, the desk's own rounds with their arms reassigned at random must read better / "
                "worse at most 5 %% of the time (D54): the Mac journal copy's 187 rounds of 9 whole ET days. MEASURED "
                "(ARMS_PLACEBO, pinned in test_benchmark): this read-out on the 9 days %.5g (only look 1 is reachable "
                "there); the test at one look at 0.05 %.4g (the alpha-unit test it replaced: %.4g); the four looks on "
                "desk days resampled to 28 shared days %.4g -- the last two AT the nominal 0.05, within their sampling "
                "error, so '<= 5 %%' is not shown there while the design spends exactly 0.05 (open_ticks)"
                % (ARMS_PLACEBO["desk_days_read_out"], ARMS_PLACEBO["desk_days_one_look"],
                   ARMS_PLACEBO["desk_days_alpha_unit_control"], ARMS_PLACEBO["desk_days_resampled_to_28_read_out"])),
}


def _arms_census(rows, pipeline_version, bound, now, names) -> dict:
    """compare_arms()'s reading of one pipeline_version's rows created by `now` on whole ET days before `bound`.

    A row is EXCLUDED, and its round counted by reason (D60; draw5 scoring M12: a marker run_config used to be dropped
    uncounted), when its stamp pair forms no cohort (D30), its meta.arm is not in ARMS, its meta.arm_by is not
    ARMS_ASSIGNED_BY, or it has no meta.round; a round whose rows carry different arms is excluded whole. An excluded
    round is named by meta.round, else meta.seed; per reason each round counts once, and the total counts each
    round once whatever reasons its rows fall under. Of an admitted round, a scored row (SCORED_STATUS with a check set) is
    in the ESTIMAND when it is arm A's with no meta.gen_route, or arm B's with meta.gen_route ARMS_FRESH_ROUTE; any other
    scored row is reported BESIDE, keyed "<arm>/<route>" (D54); an unscored row is counted per arm (round 4 m6, design
    04 section 6.4 C9). Returns {"rounds": [(round day, arm, [(row day, cell, k, n)])], "excluded", "beside",
    "unscored"}."""
    latest = {}
    for r in rows:
        m = r.get("meta") or {}
        if m.get("pipeline_version") != pipeline_version or not r.get("alpha") or not _visible_at(r, now):
            continue
        d = quota_day_of_row(r)
        if d and d < bound:
            latest[r["alpha"]] = (d, r)
    excluded = collections.defaultdict(lambda: {"rounds": set(), "rows": 0})
    by_round = collections.defaultdict(list)
    for d, r in latest.values():
        m = r["meta"]
        why = ("run_config %r forms no cohort (D30)" % (m.get("run_config"),) if cohort_of(r) is None else
               "meta.arm %r is not an arm of D47" % (m.get("arm"),) if m.get("arm") not in ARMS else
               "meta.arm_by %r: not assigned by the randomiser (D60)" % (m.get("arm_by"),)
               if m.get("arm_by") != ARMS_ASSIGNED_BY else
               "no meta.round" if m.get("round") is None else None)
        if why:
            excluded[why]["rows"] += 1
            excluded[why]["rounds"].add(str(m.get("round", m.get("seed"))))
        else:
            by_round[str(m["round"])].append((d, r))
    rounds, beside = [], collections.defaultdict(lambda: {"rounds": set(), "rows": 0, "events": 0})
    unscored = collections.Counter()
    for rid, members in sorted(by_round.items()):
        arms = {r["meta"]["arm"] for _, r in members}
        if len(arms) > 1:
            e = excluded["the rows of one meta.round carry different arms"]
            e["rows"] += len(members)
            e["rounds"].add(rid)
            continue
        arm = arms.pop()
        cells = collections.defaultdict(lambda: [0, 0])
        for d, r in members:
            if not (r.get("status") in SCORED_STATUS and r.get("checks")):
                unscored[arm] += 1
                continue
            route = r["meta"].get("gen_route")
            hit = int(clears_every_binding_check(r, names))
            if (route is None) if arm == ARMS[0] else (route == ARMS_FRESH_ROUTE):
                cells[(d, cell_of(r))][0] += hit
                cells[(d, cell_of(r))][1] += 1
            else:
                b = beside["%s/%s" % (arm, route)]
                b["rows"] += 1
                b["events"] += hit
                b["rounds"].add(rid)
        rounds.append((min(d for d, _ in members), arm, [(d, c, k, n) for (d, c), (k, n) in sorted(cells.items())]))
    return {"rounds": sorted(rounds, key=lambda u: (u[0], u[1], u[2])),
            "excluded": {w: {"rounds": len(e["rounds"]), "rows": e["rows"]} for w, e in sorted(excluded.items())},
            # D60's count: DISTINCT rounds -- a round whose rows fall under two reasons is one round, not two
            "excluded_rounds": len(set().union(*(e["rounds"] for e in excluded.values()))),
            "beside": {k: {"rounds": len(v["rounds"]), "scored_rows": v["rows"], "clearing_every_binding_check": v["events"]}
                       for k, v in sorted(beside.items())},
            "unscored": {a: unscored[a] for a in ARMS}}


def _arms_units(rounds, last_day) -> dict:
    """{day: [(arm, {cell: [k, n]})]} of the rounds placed on or before `last_day`, each counting its rows created on or
    before `last_day` (a round that runs past ET midnight is one unit, on the day of its earliest row)."""
    days = collections.defaultdict(list)
    for day, arm, entries in rounds:
        if day > last_day:
            continue
        cells = collections.defaultdict(lambda: [0, 0])
        for d, c, k, n in entries:
            if d <= last_day:
                cells[c][0] += k
                cells[c][1] += n
        days[day].append((arm, dict(cells)))
    return days


def _perm_p(days_e, observed, seed) -> tuple:
    """(two-sided p, relabellings drawn) of the within-day permutation test: `days_e` = [(e values of a day's rounds,
    how many of them are B)]. S* is the sum of the e of a uniformly drawn set of that many rounds per day; a draw is
    extreme when |S*| >= |S| (ties count, which errs toward a larger p). Sequential Monte Carlo (ARMS_PERM_*)."""
    import random
    live = []
    for e, b in days_e:
        if 0 < b < len(e) and any(e):
            m = min(b, len(e) - b)
            live.append((tuple(e), m, 1.0 if m == b else -1.0))     # the day's e sum to 0, so S_B = -S_A
    if not live:
        return 1.0, 0
    target = abs(observed) - 1e-9 * (1.0 + sum(abs(x) for e, _, _ in live for x in e))
    rng = random.Random(seed)
    sample = rng.sample
    extreme = 0
    for i in range(1, ARMS_PERM_MAX):
        s = 0.0
        for e, m, sign in live:
            s += sign * sum(sample(e, m))
        if abs(s) >= target:
            extreme += 1
            if extreme == ARMS_PERM_EXCEED:
                return extreme / i, i
    return (extreme + 1) / ARMS_PERM_MAX, ARMS_PERM_MAX - 1


def _arms_look(days, nominal_p, seed) -> dict:
    """One look of D55 on `days` = _arms_units(): the permutation test (ARMS_DESIGN["test"]), the direction per cell, and
    for display the normal approximation z = S / sqrt(V) with V the relabelling variance of S (a day's b of R rounds
    drawn without replacement: b (R - b) / (R (R - 1)) x the sum of e_r^2), the Mantel-Haenszel ratio over (day, cell)
    strata and each arm's k/n."""
    days_e, observed, var = [], 0.0, 0.0
    excess, events = collections.defaultdict(float), collections.Counter()
    num = den = 0.0
    outside = 0
    tot = {a: [0, 0] for a in ARMS}
    for d, units in sorted(days.items()):
        strata = collections.defaultdict(lambda: [0, 0, 0, 0])
        for arm, cells in units:
            off = 0 if arm == ARMS[0] else 2
            for c, (k, n) in cells.items():
                strata[c][off] += k
                strata[c][off + 1] += n
                tot[arm][0] += k
                tot[arm][1] += n
        e_day = []
        for arm, cells in units:
            e = {c: k - (strata[c][0] + strata[c][2]) * n / (strata[c][1] + strata[c][3])
                 for c, (k, n) in cells.items() if n}
            e_day.append(sum(e.values()))
            if arm == ARMS[1]:
                observed += e_day[-1]
                for c, x in e.items():
                    excess[c] += x
        for c, (ka, na, kb, nb) in strata.items():
            if not ka + kb:
                continue
            if na and nb:
                events[c] += ka + kb
                num += kb * na / (na + nb)
                den += ka * nb / (na + nb)
            else:
                outside += ka + kb
        R, b = len(units), sum(1 for arm, _ in units if arm == ARMS[1])
        days_e.append((e_day, b))
        if 0 < b < R:
            var += b * (R - b) / (R * (R - 1)) * sum(x * x for x in e_day)
    p, draws = _perm_p(days_e, observed, seed)
    cells = {c: {"events": events[c], "excess_b": round(excess[c], 6),
                 "direction": ("B higher" if excess[c] > 1e-9 else "B lower" if excess[c] < -1e-9 else "equal")}
             for c in sorted(events)}
    dirs = {v["direction"] for v in cells.values()}
    direction = "better" if dirs == {"B higher"} else "worse" if dirs == {"B lower"} else None
    return {"p_value": p, "perm_draws": draws, "nominal_p": nominal_p, "crossed": p <= nominal_p,
            "direction": direction, "statistic": round(observed, 6),
            "z_normal_approx": round(observed / math.sqrt(var), 4) if var > 0 else None,
            "cells": cells, "events_outside_shared_strata": outside,
            "rate_ratio_b_over_a": round(num / den, 3) if den else None,
            "rounds": {a: sum(1 for units in days.values() for arm, _ in units if arm == a) for a in ARMS},
            "k_n": {a: list(v) for a, v in tot.items()}}


def _arms_decision(rounds, looks=None, nominal=None) -> dict:
    """D55's group-sequential decision (ARMS_DESIGN["decides"]) on `rounds` = [(round day, arm, [(row day, cell, k,
    n)])], pure: what compare_arms() and the placebo and size simulations in test_benchmark run. `looks` / `nominal`
    default to ARMS_LOOK_DAYS / ARMS_NOMINAL_P; a test passes ((shared days,), (0.05,)) for one fixed look at 0.05.
    Looks are taken in order; the first crossing with every cell agreeing decides and ends the read-out, so a reader
    who calls this every day sees at most len(looks) looks."""
    looks = ARMS_LOOK_DAYS if looks is None else looks
    nominal = ARMS_NOMINAL_P if nominal is None else nominal
    by_day = collections.defaultdict(set)
    for day, arm, _ in rounds:
        by_day[day].add(arm)
    shared = sorted(d for d, a in by_day.items() if len(a) == len(ARMS))
    taken, verdict, why = [], None, None
    for i, need in enumerate(looks):
        if len(shared) < need:
            break
        L = _arms_look(_arms_units(rounds, shared[need - 1]), nominal[i], ARMS_PERM_SEED + i)
        L.update(look=i + 1, shared_days=need, last_day=shared[need - 1])
        taken.append(L)
        if L["crossed"] and L["direction"]:
            verdict = L["direction"]
            why = ("look %d of %d (%d shared days, through %s): p = %.3g at or under its nominal %.3g (O'Brien-Fleming), "
                   "and every cell with an event in a shared stratum has B %s; the read-out stops here"
                   % (i + 1, len(looks), need, L["last_day"], L["p_value"], nominal[i],
                      "higher" if verdict == "better" else "lower"))
            break
    last = taken[-1] if taken else None
    if verdict is None and not taken:
        verdict, why = "withheld", ("%d shared whole ET day(s) (both arms ran a randomiser-assigned round); the first "
                                    "look is at %d (D55)" % (len(shared), looks[0]))
    elif verdict is None:
        state = ("p = %.3g above its nominal %.3g" % (last["p_value"], last["nominal_p"]) if not last["crossed"] else
                 "p = %.3g crossed its nominal %.3g, but the cells with an event do not all point the same way: %s"
                 % (last["p_value"], last["nominal_p"],
                    ", ".join("%s %s" % (c, v["direction"]) for c, v in last["cells"].items())))
        if len(taken) == len(looks):
            verdict, why = "indistinguishable", "the last look (%d of %d, %d shared days, through %s): %s" % (
                last["look"], len(looks), last["shared_days"], last["last_day"], state)
        else:
            verdict, why = "withheld", ("look %d of %d (%d shared days, through %s): %s; the next look is at %d shared "
                                        "days (%d so far)" % (last["look"], len(looks), last["shared_days"],
                                                              last["last_day"], state, looks[len(taken)], len(shared)))
    return {"verdict": verdict, "why": why, "looks": taken, "shared_days": shared,
            "p_value": round(last["p_value"], 6) if last else None,
            "cells": last["cells"] if last else {},
            "events_outside_shared_strata": last["events_outside_shared_strata"] if last else None,
            "rate_ratio_b_over_a": last["rate_ratio_b_over_a"] if last else None}


def _round_clustering(rounds) -> dict | None:
    """Round 4 F1 fix item 3 (replacing the per-round Pearson dispersion, which has no power at these counts): the
    round-weighted statistic sum of e_rc^2 over every (day, cell) with an event, against its mean when the day's events
    are dealt to its scored alphas at random (hypergeometric: n K / N (1 - K / N) (N - n) / (N - 1) per round). A
    ratio above 1 is events clustering inside rounds beyond what exchangeable alphas give -- the reason the round, not
    the alpha, is the unit. On the Mac copy's 187 rounds (9 whole ET days, all 37 events in USA/d1): 72.845 against
    a null mean of 32.594 by this closed form, ratio 2.235 (2026-09-24; second way, no benchmark code, scratchpad
    d6s_ev/clustering_check.py: the same closed form, and 5,000 simulated deals giving a null mean of 32.465 with 4 of
    5,000 at or above 72.845; round 4 F1 read 72.85 against 32.41 from 4,000 deals). A diagnostic, printed, never
    deciding; None when no stratum qualifies. MECHANISM of the clustering: UNKNOWN (round 4 F1's candidates: one
    composite block's settings grid, the allocator's exploit order, platform-side state)."""
    obs = null = 0.0
    # every round and every row: the last day present, not a sentinel date (a synthetic day label such as "d000"
    # sorts above "9999-12-31", and the diagnostic read None on the desk's own rounds)
    last = max([u[0] for u in rounds] + [e[0] for u in rounds for e in u[2]], default="")
    for d, units in _arms_units(rounds, last).items():
        strata = collections.defaultdict(list)
        for _, cells in units:
            for c, (k, n) in cells.items():
                if n:
                    strata[c].append((k, n))
        for c, g in strata.items():
            K, N = sum(k for k, _ in g), sum(n for _, n in g)
            if not K or N < 2:
                continue
            obs += sum((k - K * n / N) ** 2 for k, n in g)
            null += sum(n * K / N * (1 - K / N) * (N - n) / (N - 1) for _, n in g)
    return ({"sum_sq_excess": round(obs, 3), "null_mean_if_alphas_exchangeable": round(null, 3),
             "ratio": round(obs / null, 3)} if null > 0 else None)


#: compare_arms()'s minimum detectable ratio, withheld and said so (round 4 F1 fix item 2, m1): the old arms_mdr()
#: priced the alpha-unit test D54 replaced, and nothing yet prices the round-unit permutation test under D55's looks.
ARMS_MDR_NOTE = ("not computed: the power of the round-level permutation test under D55's looks is UNMEASURED (round 4 "
                 "F1 fix item 2); the alpha-unit MDR printed before D54 described a different test and is withdrawn")


def compare_arms(rows, pipeline_version, *, now, data_through=None) -> dict:
    """D47's read-out as D54, D55 and D60 decide it: within ONE pipeline_version, did the branch's fresh draws clear every
    binding check at a different rate from the incumbent's rounds, rounds having been randomised within each ET day?
    The design (ARMS_DESIGN) was pre-registered before any arm row existed.

    WHY THE ROUND (round 4 F1, FATAL): under no effect the alpha-unit test D47 first used read better / worse in 0.155
    of placebo draws when the desk's own ROUNDS were relabelled and 0.0375 when single ALPHAS were (round 4 F1; 0.1565
    re-measured here, ARMS_PLACEBO) -- the experiment that ties the excess to events clustering inside rounds (the
    round-weighted statistic is 2.235 x its exchangeable-alpha null, _round_clustering). Relabelling whole rounds
    keeps that clustering inside the null. MECHANISM of the clustering: UNKNOWN (round 4 F1's candidates). WHY LOOKS (round 4 S1): daily reads at a
    fixed 0.05 reached 0.131 false verdicts by day 28. WHY ONLY RANDOMISED ROUNDS AND FRESH DRAWS (round 4 S3, draw5
    scoring S1): a hand-run round in arm A, or the branch's own follow-ups in arm B, moved the verdict under no effect.

    Returns the verdict and why, every look taken, each arm's rounds and k/n overall, per round day and per cell, the
    rows reported beside the estimand, the rounds EXCLUDED and why (D60), the unscored rows per arm, and the
    round-clustering diagnostic. "no-data" when an arm has no scored estimand row in an admitted round.

    LIMITS, stated (EX-ANTE, from the code and the statistic's form; none is measured on arm rows, which do not exist):
      * A round is its meta.round (the runner's --seed; vps/forge_loop.sh passes the epoch second, so a loop round's
        is unique). Two randomised rounds planned with the SAME --seed on different days are one unit here.
      * The relabelling holds each round's scored count n_r fixed. If the arms' rounds differ in n (a branch round
        spends slots on neighbour and repair rows, which are beside the estimand), the relabelled variance of S is
        the one for b / R of a day's rounds being B, where the Poisson reading's is the B share of the day's scored
        alphas: at b / R = 0.5 the first is the larger (the test errs conservative); on a day far from 0.5 it can
        be the smaller. How far the size moves at the branch's real n: UNMEASURED.
      * A look already taken is recomputed from the journal at every read: rows written later for its days (a
        recovered orphan, a later journal copy) can move it. Nothing records a look when it is first taken."""
    today = current_quota_day(now)
    cut_day = SUB.quota_day(data_through) if data_through is not None else None
    bound = min(today, cut_day) if cut_day is not None else today
    if not plain_stamp(pipeline_version):
        raise ValueError("%r is not a plain pipeline_version: arms are compared within one deployed tree (D47)"
                         % (pipeline_version,))
    g = _arms_census(rows, pipeline_version, bound, now, ESTIMAND["binding_checks"])
    per = ESTIMAND["per"]
    n_excl = g["excluded_rounds"]
    out = {"estimand": ESTIMAND["name"], "estimand_is_not": ESTIMAND["not_the_submission_count"],
           "design": ARMS_DESIGN, "pipeline_version": pipeline_version, "graded_at": now,
           "excluded_unfinished_day": today, "data_through": data_through,
           "excluded_uncovered_day": cut_day if cut_day is not None and cut_day < today else None,
           "excluded": {"rounds": n_excl, "rows": sum(e["rows"] for e in g["excluded"].values()),
                        "by_reason": g["excluded"]},
           "beside": g["beside"], "arms": {}, "round_clustering": _round_clustering(g["rounds"]),
           "minimum_detectable_ratio": {"note": ARMS_MDR_NOTE}}
    for a in ARMS:
        per_day, per_cell, n_rounds = (collections.defaultdict(lambda: [0, 0]), collections.defaultdict(lambda: [0, 0]),
                                       0)
        for day, arm, entries in g["rounds"]:
            if arm != a:
                continue
            n_rounds += 1
            for _, c, k, n in entries:
                for bucket in (per_day[day], per_cell[c]):
                    bucket[0] += k
                    bucket[1] += n
        k, n = sum(v[0] for v in per_day.values()), sum(v[1] for v in per_day.values())
        out["arms"][a] = {"rounds": n_rounds, "scored_alphas": n, "clearing_every_binding_check": k,
                          "per_1000": round(k / n * per, 3) if n else None,
                          "per_day": {d: list(v) for d, v in sorted(per_day.items())},
                          "per_cell": {c: list(v) for c, v in sorted(per_cell.items())},
                          "dispersion_across_days": _dispersion(per_day),
                          "unscored_rows": g["unscored"][a]}
    if not all(out["arms"][a]["scored_alphas"] for a in ARMS):
        out.update(verdict="no-data", why=(
            "an arm has no scored estimand row in a randomiser-assigned round of pipeline_version %s on a whole ET quota "
            "day; %d round(s) of it are excluded%s" % (pipeline_version, n_excl, (": " + "; ".join(
                "%s (%d round(s), %d row(s))" % (w, e["rounds"], e["rows"]) for w, e in g["excluded"].items()))
                if n_excl else "")))
        return out
    out.update(_arms_decision(g["rounds"]))
    return out


def render_arms(out: dict) -> str:
    """compare_arms()'s result as text: the verdict and why, each arm's rounds and k/n, every look, the cells'
    directions, the rows beside the estimand, and the rounds excluded and why (D60)."""
    L = ["ARM COMPARISON (D47, D54, D55) within pipeline_version %s on the pre-registered estimand: %s"
         % (out["pipeline_version"], out["estimand"]), "  %s" % out["estimand_is_not"], "",
         "  VERDICT  %s: %s" % (out["verdict"], out["why"]), ""]
    for a, e in out["arms"].items():
        L.append("  %-11s %d round(s): %d of %d scored clear every binding check (%s per 1,000); %d unscored row(s); "
                 "dispersion across days %s" % (a, e["rounds"], e["clearing_every_binding_check"], e["scored_alphas"],
                                                e["per_1000"], e["unscored_rows"], e["dispersion_across_days"]))
    for look in out.get("looks") or []:
        L.append("  look %d (%d shared days, through %s): p %.3g (%d relabellings) against nominal %.3g -> %s; z %s; "
                 "Mantel-Haenszel ratio B/A %s; events outside the shared strata %d" % (
                     look["look"], look["shared_days"], look["last_day"], look["p_value"], look["perm_draws"],
                     look["nominal_p"], "CROSSED" if look["crossed"] else "not crossed", look["z_normal_approx"],
                     look["rate_ratio_b_over_a"], look["events_outside_shared_strata"]))
        L += ["      %-10s %s (%d event(s))" % (c, v["direction"], v["events"]) for c, v in look["cells"].items()]
    for k, v in out["beside"].items():
        L.append("  beside the estimand (D54): %s -- %d round(s), %d scored, %d clear every binding check"
                 % (k, v["rounds"], v["scored_rows"], v["clearing_every_binding_check"]))
    ex = out["excluded"]
    L.append("  EXCLUDED from the comparison (D60): %d round(s), %d row(s)%s" % (
        ex["rounds"], ex["rows"], "".join("\n      %s: %d round(s), %d row(s)" % (w, e["rounds"], e["rows"])
                                          for w, e in ex["by_reason"].items())))
    L.append("  round clustering (display): %s" % out["round_clustering"])
    L.append("  placebo (D54): %s" % out["design"]["placebo"])
    L.append("  what it could have seen: %s" % out["minimum_detectable_ratio"]["note"])
    return "\n".join(L)


def cell_of(row) -> str:
    """The cell a scored alpha belongs to, for compare()'s per-cell display: "<region>/d<delay>" from its
    settings -- the split the draw-3 scoring adjudicator measured the confound on (cells.py)."""
    s = row.get("settings") or {}
    return "%s/d%s" % (s.get("region"), s.get("delay"))


#: How cell_mix() decides that two arms' cell mix differs (draw-3 scoring SERIOUS 6, display half).
CELL_MIX_TEST = ("Pearson chi-square test of homogeneity on the 2 x C table of scored alphas per cell per arm "
                 "(cells with no scored alpha in either arm dropped), df = C - 1, flagged at p < ESTIMAND['alpha']")


def cell_mix(per_cell_a: dict, per_cell_b: dict) -> dict:
    """Does the arms' mix of SCORED alphas across cells differ by more than sampling noise? (SERIOUS 6)

    DISPLAY ONLY since D28: this test decides nothing. A mix difference CAN still move compare()'s verdict
    through D28's direction rule (draw4_build scoring 6: this said it could not): a cell with an event that one
    arm never scored in is a mix difference, and compare() reads it "one arm only", so the verdict is
    indistinguishable.

    THE TEST AND WHY IT. A pooled rate is a mix-weighted average of per-cell rates, so a difference in the
    arms' cell mix can bias the POOLED comparison -- and does so only when the per-cell rates also differ
    (draw3_fix scoring 11: this said "confounded exactly when the arms weight the cells differently", which
    is not true when every cell has the same rate). The question asked here is the arms' distributions
    over cells alone, whatever the events do. The chi-square test of homogeneity is
    the standard test of "two multinomial samples share one distribution"; it needs no threshold of its
    own (it reuses ESTIMAND["alpha"]), and it counts a cell present in one arm only as a difference like
    any other. Its known weaknesses, stated: at large n it flags small share differences, which errs
    toward the RULE 0 #6 warning, never away from it; with an expected count under 5 its p-value is only
    approximate (Cochran's rule, EX-ANTE), and `min_expected` is printed so the reader sees when. NOT
    flagged does not make pooling harmless: it means no mix difference was detected."""
    cells = [c for c in sorted(set(per_cell_a) | set(per_cell_b))
             if per_cell_a.get(c, (0, 0))[1] + per_cell_b.get(c, (0, 0))[1] > 0]
    na = sum(per_cell_a.get(c, (0, 0))[1] for c in cells)
    nb = sum(per_cell_b.get(c, (0, 0))[1] for c in cells)
    out = {"test": CELL_MIX_TEST, "cells": cells, "statistic": None, "df": None, "p_value": None,
           "min_expected": None, "differs": False}
    if not na or not nb:
        out["note"] = "an arm has no scored alpha: no mix to compare"
        return out
    if len(cells) < 2:
        out["note"] = "both arms lie in the one cell %s: the mix cannot differ" % cells[0]
        return out
    total, stat, min_e = na + nb, 0.0, float("inf")
    for c in cells:
        col = per_cell_a.get(c, (0, 0))[1] + per_cell_b.get(c, (0, 0))[1]
        for obs, arm_n in ((per_cell_a.get(c, (0, 0))[1], na), (per_cell_b.get(c, (0, 0))[1], nb)):
            e = arm_n * col / total
            stat += (obs - e) ** 2 / e
            min_e = min(min_e, e)
    df = len(cells) - 1
    p = chi2_sf(stat, df)
    out.update({"statistic": stat, "df": df, "p_value": p, "min_expected": round(min_e, 2),
                "differs": p < ESTIMAND["alpha"],
                "note": ("an expected count is under 5: the chi-square p-value is approximate there"
                         if min_e < 5 else None)})
    return out


def verdict_text(out: dict) -> str:
    """The sentence compare() prints for its verdict: the WITHIN-CELL decision (D28) and why, then the
    pooled numbers marked as never deciding, then the cell mix as display. The JSON `verdict` and this text
    come from the same decision (draw3_fix scoring 10: the text used to withhold a verdict the JSON kept)."""
    if out["verdict"] == "no-data":
        return "no-data: " + out["why"]
    cm, po = out["cell_mix"], out["pooled"]
    return ("%s WITHIN CELL (D28): stratified exact test p = %s at alpha %.2f, Mantel-Haenszel ratio B/A %s; %s. "
            "A cell with an event that one arm never scored in, or a tie, points no way and makes the verdict "
            "indistinguishable (this module's reading of D28, open for Khoa). Pooled across cells (printed, never "
            "deciding): p = %s, ratio %s. Cell mix %s (%s)."
            % (out["verdict"], out["p_value"], out["alpha"], out["rate_ratio_b_over_a"], out["why"], po["p_value"],
               po["rate_ratio_b_over_a"], "DIFFERS: the pooled numbers move with it" if cm["differs"] else
               "does not differ detectably", cm.get("note") or "chi-square p = %s" % (
                   "%.3g" % cm["p_value"] if cm["p_value"] is not None else None)))


def _dispersion(per_day: dict):
    """Pearson chi-square / (days - 1) of per-day counts against one binomial rate; None under 2 days or
    no events. About 1 when days differ by chance alone; POST-HOC diagnostic, not a correction."""
    days = [(k, n) for k, n in per_day.values() if n]
    K, N = sum(k for k, _ in days), sum(n for _, n in days)
    if len(days) < 2 or K == 0 or K == N:
        return None
    p = K / N
    return round(sum((k - n * p) ** 2 / (n * p * (1 - p)) for k, n in days) / (len(days) - 1), 2)


def _mdr_statement(mdr: dict, n_a, n_b) -> str:
    if mdr.get("note"):
        return mdr["note"]
    head = ("With %d and %d scored alphas and a pooled base of %.3f per 1,000, the exact test at alpha %.2f "
            "detects with %d %% power" % (n_a, n_b, mdr["baseline_per_1000"], mdr["alpha"], round(mdr["power"] * 100)))
    up = ("a ratio B/A of %.2f or more" % mdr["increase"]) if mdr["increase"] else mdr["increase_note"]
    if mdr["decrease"] is None:
        down = "NO decrease at all -- even a B that clears nothing is missed more often than 1 time in 5"
    elif mdr["decrease"] < 0.005:
        down = "only a total collapse (a B that clears nothing)"
    else:
        down = "a ratio of %.2f or less" % mdr["decrease"]
    return "%s %s, and %s; a smaller change reads 'indistinguishable' more often than not." % (head, up, down)


def _submission_reading(rows, history, curves, standard, scored, corr, version, now, deploys,
                        data_through=None, meaning=None, run_config_log=None) -> dict:
    """The secondary, POST-based reading of one arm (no verdict): proven clean submissions per live day.

    Draw-3 scoring MINOR (S8, S9): without a ledger the card's window ran to yesterday, so the reading was
    "censored" forever with a final date moving forward each day, and the "exposure unknown" branch after
    it could not be reached; the censored note printed the window's end (until_exclusive) as the "newest
    day". Now the horizon runs from the newest GRADED day (build_from), an unknown exposure is reported
    first (there is no rate to censor), and the note names that newest day. D27 / draw3_fix scoring 1:
    "final" is build_from's, judged at seen_until = min(now, data_through)."""
    try:
        card = build_from(rows, scored, corr, history, curves, standard, version=version, now=now, deploys=deploys,
                          data_through=data_through, meaning=meaning, run_config_log=run_config_log)
    except ValueError as exc:
        return {"status": "no-data", "note": str(exc)}
    a2, w = card["axes"]["axis2_throughput"], card["window"]
    ph = a2["post_horizon"]
    if a2["quota_days"] is None:
        return {"status": "exposure unknown", "note": w["exposure"]["note"],
                "proven_clean_submissions": a2["proven_clean_submissions"],
                "post_horizon_final": ph["final"], "final_after_et": ph["final_after_et"]}
    if not w["quota_days"]:
        return {"status": "no-data", "note": "the version was live for no whole ET quota day"}
    if not ph["final"]:
        return {"status": "censored", "final_after_et": ph["final_after_et"],
                "note": "POSTs can still land within the %d-day horizon of the newest graded day %s; no number is "
                        "shown before it closes at seen_until (A4, D27)" % (POST_HORIZON_DAYS, ph["newest_day"])}
    return {"status": "final", "exposure": a2["exposure"], "proven_clean_submissions": a2["proven_clean_submissions"],
            "proven_clean_per_quota_day": a2["proven_clean_per_quota_day"],
            "poisson_95_per_day": a2["poisson_95_per_day"],
            "note": "NOT the estimand; reported without a verdict"}


def open_ticks(card: dict) -> list:
    """The facts Khoa needs for the decisions still OPEN in this scorer, filled in with THIS card's numbers
    (RULE 2; draw-3 scoring, "TICK items"). Printing them changes no verdict and no rank.

    Draw3_fix scoring 9: D26 (level 1 = refuted + unproven), D27 (an open horizon is not ranked), D28
    (within cell) and D29 (the verdict leads) are ticked AND implemented here, so their items are gone; the
    old SERIOUS 2 text ("measuring them could only move it down") was false for the rank anyway -- an alpha
    measured as PROVEN raises level 2. D7's "held" definition is added: it was open and not listed."""
    a2 = (card.get("axes") or {}).get("axis2_throughput") or {}
    rk = card.get("rank") or {}
    return [
        {"item": "level 1 is a raw count",
         "fact": "%s refuted or unproven submitted alpha(s) over %s: a count, not a rate per exposure, so a version "
                 "that ran longer accumulates more." % (rk.get("refuted_or_unproven_submitted"), a2.get("exposure"))},
        {"item": "D7 'held in the next window'",
         "fact": "read as: the next window of equal length produced at least one PROVEN clean submission (this "
                 "card: %s). Whether 'hold' should mean a rate test rather than '> 0' is decided nowhere and is not "
                 "invented here." % (a2.get("sustainability_evidence") or {}).get("held_in_next_window")},
        {"item": "D28 as read here",
         "fact": "compare() reads 'every cell with an event points the same way' strictly: a cell with an event that "
                 "one arm never scored in, or a tie, points no way and makes the verdict indistinguishable."},
        {"item": "D47, D54, D55 as read here",
         "fact": "compare_arms() applies the same-direction rule to CELLS (D28's stratum), each cell's direction summed "
                 "over its (day, cell) strata; events in a stratum only one arm scored in are outside the direction "
                 "rule. A round that runs past ET midnight is one unit, on the day of its earliest row. D55's 'every 7 "
                 "days' is read as SHARED days (both arms ran a randomiser-assigned round), so a one-arm day spends no "
                 "look. The total two-sided alpha is 0.05 exactly (O'Brien-Fleming C = %.4f), and the placebo on the "
                 "desk's own rounds reads AT it: %.4g at one look, %.4g over the four looks on desk days resampled to 28 "
                 "shared days (ARMS_PLACEBO), each within one standard error of 0.05 -- D54's '<= 5 %%' is met by the "
                 "read-out on the 9 real days (%.5g, look 1 only) and NOT SHOWN by these two. Open: accept 'not above "
                 "0.05 beyond its sampling error', or design a total alpha below 0.05 so a placebo can show the "
                 "margin (a cost in power). Each new pipeline_version starts its own read-out, so the false-verdict "
                 "rate over several versions is NOT held at 0.05 (draw5 scoring M13, round 4 S1)."
                 % (ARMS_OBF_C, ARMS_PLACEBO["desk_days_one_look"], ARMS_PLACEBO["desk_days_resampled_to_28_read_out"],
                    ARMS_PLACEBO["desk_days_read_out"])},
        {"item": "POST_HORIZON_DAYS = %d" % POST_HORIZON_DAYS,
         "fact": "a POST-HOC convention, chosen after seeing N = 4 creation-to-POST lags (0.01, 0.77, 0.02, 11.49 d). "
                 "Since D49 it bounds credit and finality only: a later accepted POST still counts against level 1 "
                 "(this card: %d such alpha(s)), so a card read final can still lose a place at level 1, and an "
                 "unproven or refuted late POST also makes axis 1's floor unmet and the verdict FAIL (draw5 scoring "
                 "M23). D57: rank_cmp counts level 1 on both cards at one creation-to-POST lag; rank_key alone "
                 "does not." % len((card.get("axes") or {}).get("axis1_product", {}).get("posted_beyond_the_horizon")
                                   or [])},
        {"item": "D56 as read here",
         "fact": "PBO reads NOT APPLICABLE (printed UNMEASURED, not counted) only for a generated alpha whose pool "
                 "status starts '%s' (fewer than 20 trials); 'pending', 'empty', 'too short' and every library "
                 "alpha stay unmeasured." % PBO_INSUFFICIENT},
        {"item": "watch outcomes in DORA",
         "fact": "dora() counts watch_not_rolled_back as a change failure and watch_interrupted as none (draw5 scoring "
                 "M10): tools/deploy.py says watch_not_rolled_back covers every D43-reported post-dispatch error, "
                 "while watch_interrupted says only that the watch itself failed. Display only (A9)."},
        {"item": "REGIME_SE_MULTIPLE = %.1f" % REGIME_SE_MULTIPLE,
         "fact": "this module's EX-ANTE convention (1.96 rounded); serial independence of daily PnL changes is "
                 "UNMEASURED."},
        {"item": "the exposure rules",
         "fact": "a version's RATE counts only whole ET days the deploy ledger says it ran: every day a deploy "
                 "attempt touched is excluded, a rollback restores the previous version, a noop is ignored, a watch "
                 "row is never a deploy (a watch_rolled_back restores the previous version), the unfinished day and "
                 "the day the data was cut on are excluded. A (pipeline_version, run_config) cohort's days are those "
                 "on which the run_config log records that run_config all day (D45); days before the log's first "
                 "row for the cohort have no known exposure and are left out of the rate -- this module's per-day "
                 "reading of D45 -- and a (pipeline_version, None) cohort keeps every live day of its "
                 "pipeline_version (draw5 scoring M26). Axis 1 and level 1 grade every stamped row regardless "
                 "(SERIOUS 1)."},
    ]


def _days_phrase(qd, since) -> str:
    """The rate's day count in words (draw3_fix scoring 6): None (exposure unknown) and 0 (no whole day)
    are different facts, and V2 printed "no rate (exposure unknown)" and "from None" for a card whose
    exposure was KNOWN to be 0 days."""
    if qd is None:
        return "exposure unknown: no rate"
    if qd == 0:
        return "0 whole ET quota days: no rate"
    return "%d whole ET quota day(s) from %s" % (qd, since)


def render(card: dict) -> str:
    a = card["axes"]
    w = card["window"]
    rk = card["rank"]
    t = a["axis2_throughput"]
    L = ["PIPELINE SCORECARD  %s" % (w.get("version") or "(date window)"),
         "  %s (the unfinished day %s is excluded)   attribution: %s"
         % (_days_phrase(t["quota_days"], w["since"]), w["excluded_unfinished_day"], card["version_attribution"])]
    rq, ef = w.get("requested") or {}, w.get("effective") or {}
    if ef:
        rate_part = ("no rate (exposure unknown)" if ef["rate_days"] is None else
                     "rate on 0 days" if not ef["rate_days"] else
                     "rate on %d day(s) %s..%s" % (ef["rate_days"], ef["rate_first_day"], ef["rate_last_day"]))
        L += ["  window requested: since %s, until %s (exclusive)" % (rq.get("since"), rq.get("until_exclusive")),
              "  window effective: %s; axis 1 on rows of %s..%s; until %s (exclusive)"
              % (rate_part, ef["axis1_first_day"], ef["axis1_last_day"], ef["until_exclusive"]),
              "  data: %s" % w.get("coverage_note")]
    if w.get("coverage_gap"):
        L.append("  data: COVERAGE GAP -- %s" % w["coverage_gap"]["note"])
    if w.get("exposure"):
        L.append("  exposure: %s" % w["exposure"]["note"])
        if w["exposure"].get("graded_by_axis1_not_in_rate"):
            L.append("  exposure: %s" % w["exposure"]["graded_by_axis1_not_in_rate"])
    L += ["", "  VERDICT  %s%s" % (card["verdict"], ("  (floors unmet: %s)" % ", ".join(card["floors_unmet"])) if card["floors_unmet"] else ""),
          "  RANK (D29, D26, D25)  verdict %s | refuted or unproven submitted %s | proven clean per quota day %s | "
          "axis 3 held %s" % (rk.get("verdict"), rk.get("refuted_or_unproven_submitted"),
                             rk.get("proven_clean_per_quota_day"), rk.get("axis3_held_fraction")),
          "  RANK %s" % ("comparable: the POST horizon is final" if rk.get("horizon_final") else
                         "NOT COMPARABLE until %s ET (D27): the POST horizon is not final at seen_until %s"
                         % (rk.get("comparable_from_et"), t["post_horizon"].get("seen_until_et"))), ""]
    p = a["axis1_product"]
    L += ["  AXIS 1  PRODUCT   %s   proven %.3f of submitted   gate coverage %s" % ("FLOOR MET" if p["floor_met"] else "floor unmet",
                                                                                   p["value"], p["gate_coverage"]),
          "    submitted by this version: %d  (%s)" % (p["n"], p["verdict"])]
    for d in p["detail"][:6]:
        skip = d.get("not_applicable") or {}
        bad = [k for k, v in d["gates"].items() if v is False]
        unk = [k for k, v in d["gates"].items() if v is None and k not in skip]
        L.append("      %-10s %-8s%s%s" % (d["alpha"], d["status"], (" FAILS: " + ", ".join(bad)) if bad else "",
                                           (" unmeasured: " + ", ".join(unk)) if unk else ""))
        na = (d.get("standard_route") or {}).get("not_applicable")
        if na:
            L.append("                 %s" % na)
        L += ["                 %s %s" % (k, why) for k, why in skip.items()]            # D56
    rate = ("%.3f per day" % t["proven_clean_per_quota_day"] if t["proven_clean_per_quota_day"] is not None else
            "no rate (exposure unknown)" if t["quota_days"] is None else "no rate (0 whole ET quota days)")
    L += ["", "  AXIS 2  THROUGHPUT  %s" % ("FLOOR MET" if t["floor_met"] else "floor unmet"),
          "    %d PROVEN clean submission(s) over %s = %s   (floor %.1f)   95 %% %s"
          % (t["proven_clean_submissions"], t["exposure"], rate, t["floor"], t["poisson_95_per_day"]),
          "    not counted as clean: %d unproven, %d refuted" % (t["unproven_submissions"], t["refuted_submissions"]),
          "    scored alphas %d (%s per day) | per proven clean submission %s | qualified families %s"
          % (t["scored_alphas"], t["scored_per_quota_day"], t["scored_per_proven_clean_submission"], t["qualified_families"]),
          "    POSTs the submitter made in the window: %d   POST horizon %d d, final at seen_until %s: %s (after %s)"
          % (t["posts_this_version_made"], t["post_horizon"]["days"], t["post_horizon"].get("seen_until_et"),
             t["post_horizon"]["final"], t["post_horizon"]["final_after_et"]),
          "    sustainable: %s  %s" % (t["sustainable"], t["sustainability_evidence"]),
          "    next window: %s" % t["next_window"]]
    if "axis3_gearing" in a:
        g = a["axis3_gearing"]
        L += ["", "  AXIS 3  GEARING  %s   %d of %d measured checks hold" % ("FLOOR MET" if g["floor_met"] else "floor unmet", g.get("held", 0), g.get("of", 0))]
        L += ["      [%s] %s" % ("ok" if f["ok"] else "NO", f["name"]) for f in g.get("fitness_functions", [])]
    if card.get("dora"):
        L.append("  DORA (reported, not scored): %s" % card["dora"]["keys"].get("status"))
    pv = card.get("provenance") or {}
    if pv:
        L += ["", "  graded at %s on host %s by scorer %s on %d row(s), last row day %s" % (
            pv["generated_at_et"], pv.get("host"), pv["scorer_sha256"][:12], pv["inputs"]["rows"],
            pv["inputs"]["last_row_day"])]
    if card.get("gaps"):
        L += ["", "  GAPS THIS SCORECARD DOES NOT HIDE:"] + ["    - %s" % x for x in card["gaps"]]
    if card.get("open_ticks"):
        L += ["", "  FOR KHOA -- open decisions (RULE 2); behaviour unchanged by printing them, facts from this card:"]
        L += ["    - %s: %s" % (t["item"], t["fact"]) for t in card["open_ticks"]]
    return "\n".join(L)


def render_compare(out: dict) -> str:
    """compare()'s result as text: the verdict sentence first, then each arm's k/n overall and per cell, the
    within-cell directions, and the cell mix with its smallest expected count and note (draw3_fix scoring 10:
    min_expected and the note were computed and never printed). Round 3 F1: COMPARE_IS_NOT_GATE3 comes before the
    verdict."""
    L = ["VERSION COMPARISON on the pre-registered estimand: %s" % out["estimand"],
         "  %s" % out["estimand_is_not"], "  %s" % out["not_gate3_evidence"], "",
         "  VERDICT  %s" % out["verdict_text"], ""]
    for v, e in out["versions"].items():
        L.append("  %-20s %d of %d scored clear every binding check%s" % (
            v, e["clearing_every_binding_check"], e["scored_alphas"],
            ("  (%.3f per 1,000, exact 95 %% %s)" % (e["per_1000"], e["exact_95_per_1000"])) if "per_1000" in e else ""))
        L += ["      %-10s %d / %d" % (c, k, n) for c, (k, n) in e["per_cell"].items()]
    if out.get("cells"):
        L += ["", "  within cell (D28):"] + ["      %-10s A %d/%d  B %d/%d  %s" % (c, v["a"][0], v["a"][1], v["b"][0], v["b"][1],
                                                                            v["direction"]) for c, v in out["cells"].items()]
    cm = out["cell_mix"]
    L += ["", "  cell mix differs: %s   (%s; statistic %s, df %s, p %s, min expected %s)%s" % (
        out["cell_mix_differs"], cm["test"], cm["statistic"], cm["df"], cm["p_value"], cm["min_expected"],
        ("  note: %s" % cm["note"]) if cm.get("note") else "")]
    if out.get("minimum_detectable_ratio"):
        m = out["minimum_detectable_ratio"]
        L.append("  what it could have seen (%s): %s" % (m.get("scope"), m["statement"]))
    if out.get("calendar"):
        L += ["  calendar: %s" % out["calendar"]["statement"], "  design: %s" % out["design"]]
    for v, r in (out.get("submissions_secondary") or {}).items():
        L.append("  submissions (secondary, no verdict) %s: %s -- %s" % (v, r.get("status"), r.get("note")))
    return "\n".join(L)


def main(argv=None) -> int:
    import argparse
    import time
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default="", help="first ET quota day, YYYY-MM-DD")
    ap.add_argument("--until", default="", help="ET quota day to stop BEFORE, YYYY-MM-DD")
    ap.add_argument("--version", default="",
                    help="grade the cohort of this pipeline version: PV, or PV@RUN_CONFIG for a stamped run_config (D30)")
    ap.add_argument("--no-drill", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--compare", nargs=2, metavar=("VERSION_A", "VERSION_B"),
                    help="A2: compare two cohorts (PV or PV@RUN_CONFIG) on the pre-registered estimand, within cell "
                         "(D24, D28), instead of grading")
    ap.add_argument("--record", action="store_true",
                    help="A2: append the card, with its provenance, to state/benchmark/cards.jsonl (one JSON line); "
                         "at most one per (cohort, graded ET day, host) (D41); needs --version (a recorded card names "
                         "its cohort)")
    a = ap.parse_args(argv)
    if a.compare:
        if a.record:
            ap.error("--record appends a scorecard; a comparison is printed, not recorded")
        x = load_inputs()
        try:
            out = compare(x["rows"], x["history"], x["curves"], x["standard"], x["scored"], x["corr"], a.compare[0],
                          a.compare[1], now=time.time(), deploys=x["deploys"], data_through=x["data_through"],
                          meaning=x.get("meaning"), run_config_log=x.get("run_config_log"))
        except ValueError as exc:
            ap.error(str(exc))
        print(json.dumps(out, indent=1, default=str) if a.json else render_compare(out))
        return 0
    if a.record and not a.version:
        ap.error("--record needs --version PV or PV@RUN_CONFIG: a recorded card names its cohort (D1, D14); a date-window "
                 "card grades no version")
    card = build(since=a.since or None, until=a.until or None, version=a.version or None, run_drill=not a.no_drill)
    if a.record:
        path, appended = record_card(card)
        print(("recorded in %s" % path) if appended else
              ("NOT recorded: %s already holds a card for this cohort, graded ET day and host (D41); nothing "
               "appended" % path), file=sys.stderr)
    print(json.dumps(card, indent=1, default=str) if a.json else render(card))
    return 0 if card["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
