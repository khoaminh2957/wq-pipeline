"""tools.ci_fixture — the scorer's TRUTH TABLE, pinned by tools/ci_golden_card.json (draw 2 F1/S8;
architecture round 2 A7 and S8-NL).

A pre-merge gate cannot grade the pipeline's output -- under D14 a candidate version has produced no
rows at merge time -- so what it CAN grade is the scorer itself. This file feeds
forge.offline.benchmark frozen, synthetic inputs and records what the scorer DECIDED on each; the card
must equal the committed golden card (tools/ci_gate.py check_pinned_scorer).

ROUND 2, A7: the first fixture was one cohort of nine rows. Applied to benchmark.py in memory, every edit
in round 2's table but one left the golden card identical -- both hard floors swapped for looser
predicates (together they turned the real 2026-09-04 card from FAIL to PASS), the DSR threshold
0.95 -> 0.50, compare() hard-wired to "indistinguishable", DORA's change-failure check made always true,
the import-cycle check made always true. A golden card pins only the decisions some case reaches. So
this is a TRUTH TABLE: one case per decision the audits listed (see below), named for the decision it
reaches, and
tools/tests/test_ci_gate.py re-applies round 2's edits (and a few more) to the scorer and requires
every one of them to move a case outcome, not merely the hash.

The card also carries the sha256 of this file and of EVERY repository file the scorer imports (S8-NL;
draw-3 ci SERIOUS 3): an edit to the scorer that no case reaches still changes the card, so no scorer
edit passes the gate without a re-record, and `python3 tools/ci_gate.py --record-golden` prints the diff
of that re-record before writing it. SERIOUS 3 measured why benchmark.py's own hash was not enough: part
of the scorer's decisions live in the modules it imports (forge/submit.py's corr_lines and quota_day,
forge/hypotheses.py, fingerprint.py), and the edit corr_lines ("PROD_CORRELATION", "SELF_CORRELATION")
-> ("PROD_CORRELATION", "PROD_CORRELATION") changed no case and no hash, so check_pinned_scorer read
ok=True. The set is found by an AST walk (import_closure), never listed by hand, and case_axis1_gates now
has self-correlation cases on which that edit, the reverse swap and a dropped self line all move a status.

WHAT THIS PROVES AND WHAT IT DOES NOT. It proves the scorer's decisions did not CHANGE unseen. It does
not prove they are RIGHT: the inputs are synthetic and the golden card was recorded from the scorer it
guards. Axis 1's thresholds are named constants in benchmark.py since draw 3 (DSR_MIN, NEIGHBOUR_RETENTION_MIN,
NEIGHBOURS_MIN, CURVE_POINTS_MIN, CORR_UNDER_LINE); each is pinned twice, by name in `constants` and by a
case on either side of it (a threshold moved with a case on neither side would move only the name).

"ONE CASE PER DECISION" MEANS THE DECISIONS LISTED BY THE AUDITS, not every branch of benchmark.py. Draw-3
ci SERIOUS 4 found seven edits that moved no case; each now has a case that it moves, and
tools/tests/test_ci_gate.py MUTANTS applies each one:
  * a binding check read `!= "FAIL"` instead of `== "PASS"` (a missing or PENDING check passes) --
    binding_check_missing, binding_check_pending;
  * alpha_status testing unproven before refuted -- one_gate_false_one_unmeasured;
  * the self-correlation line dropped -- self_corr_over_the_default_line;
  * an unknown rate ranked as 0/day -- case_rank's "nothing submitted" (a MEASURED 0.0) against "P, exposure
    unknown" (draw4_build ci 8(b): this named "U", which D26 moved to level 1 = 1);
  * the module-test coverage bound (0.8 -> 0.5 in draw 2; MODULE_TEST_COVERAGE_MIN = 1.0 now) --
    case_axis3_tree's four_of_five_modules_tested sits at 0.8, so any bound at or below 0.8 moves it. A
    bound in (0.8, 1.0) does NOT move a case: only the pinned constant catches it;
  * the curve bound 300 -> 400 -- curve_of_300_points (with curve_of_299_points, it pins 300 exactly);
  * DORA's window 28 -> 7 days -- case_dora's ledgers change deploys_per_week under it.
Draw3_fix ci 6 found one more: the self line compared with `<=` -- self_corr_exactly_at_the_default_line.

THE DECISIONS KHOA TICKED ON 2026-09-23 (docs/evalharness/00_agreements.md), one case each, and each with
an edit in tools/tests/test_ci_gate.py MUTANTS that must move THAT case. Draw4_build ci 8(c): this said so
while the MUTANTS test asked only that SOME case move (the D29 edit moves rank_open_horizon as well as
verdict_leads_rank); every MUTANTS entry now names the case it must move, and the test fails when that case
does not move, whatever else does:
  * D26, rank level 1 = refuted + UNPROVEN submitted -- case_rank ("P+U" below "P");
  * D27, a card whose POST horizon is not final at seen_until is not ranked -- case_rank_open_horizon;
  * D28, the estimand compared WITHIN cell, disagreeing cells INDISTINGUISHABLE -- case_compare_within_cell;
  * D29, the verdict leads the rank (PASS above FAIL) -- case_verdict_leads_rank;
  * D30, a cohort is (pipeline_version, run_config): two run_config values are two cohorts, a suffixed or
    marker stamp -- in pipeline_version or run_config -- is none -- case_cohorts;
  * D39, a generated alpha's gate half comes from its meaning row of its own formula, G1-G3 not applicable --
    case_generated_alpha (round 3 S8's rows);
  * D45, a run_config cohort's days come from the runner's run_config log -- case_run_config_exposure;
  * D47, the branch against the incumbent within ET day (compare_arms) -- case_compare_arms;
  * D49, every accepted POST counts against rank level 1 whatever its lag -- case_post_horizon.
THE DECISIONS KHOA TICKED ON 2026-09-24 ~02:20 (after architecture round 4), the same way:
  * D54, D47's unit is the ROUND, only randomiser-assigned rounds count, and the branch counts fresh draws only --
    case_compare_arms: events_cluster_in_rounds (the unit), explicit_rounds_excluded (the randomiser), and
    neighbour_and_repair_rows_beside (fresh draws);
  * D55, group-sequential looks at 7/14/21/28 shared days with O'Brien-Fleming boundaries -- case_compare_arms:
    within_day_effect (a look INSIDE its boundary, and the stop) against look_outside_the_boundary, the first
    look pinned from both sides by six_shared_days and seven_shared_days, and no_effect_30_shared_days (at most
    four looks);
  * D56, PBO "insufficient" on a generated pool reads not applicable -- case_generated_alpha's gen_pbo_* rows;
  * D57, rank level 1 at equal post-creation exposure -- case_rank_equal_exposure;
  * D60, rounds outside the randomiser are excluded and COUNTED -- case_compare_arms' `excluded` on every entry.
And two readings the draw-4 audits required: tools/deploy.py's WATCH ROWS (a watch row is never a deploy) --
case_watch_rows; and round 3 S7, the scorer's INPUT layer (build(), load_inputs and every reader it calls, on
a miniature state/ in a temporary directory) -- case_input_layer, the one case whose scorer READS a state/ (draw-5
ci 13: this said "the one case that reads files", but case_axis3_tree copies one real forge/hypotheses YAML into
its synthetic tree).
Decisions NOT reached by any case, stated rather than implied, each pinned by name only in `constants`: the exact
test's minimum-detectable-ratio search limits (MDR_MAX_EVENTS, MDR_MAX_RATIO -- no case comes near 1,000 expected
events); the ESTIMAND's descriptive text (only its `name` also shows in case_compare); COMPARE_IS_NOT_GATE3, a
printed sentence; ARMS_PLACEBO, ARMS_OBF_C and ARMS_PERM_* (test_benchmark measures and re-derives them; a case
reaches the boundaries only through ARMS_NOMINAL_P); and, of WATCH_ROUND_FAILED, watch_rollback_failed and
watch_units_down (case_watch_rows' ledger holds neither; draw-5 ci 13).

Nothing here reads the wall clock, the desk's journal, the network or the desk's deploy ledger: every `now` is
fixed, and case_input_layer reads only the miniature files it writes to a temporary directory.
"""
from __future__ import annotations

import ast
import contextlib
import datetime
import functools
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import zoneinfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
ET = zoneinfo.ZoneInfo("America/New_York")
DAY = 86400.0

#: The binding checks, WRITTEN OUT rather than read from the scorer: the fixture's inputs are frozen, so a
#: name added to benchmark.BINDING makes every row here fail it and the golden card moves.
BINDING_NAMES = ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE",
                 "CONCENTRATED_WEIGHT", "HIGH_TURNOVER", "LOW_TURNOVER")
PASS = [{"name": n, "result": "PASS"} for n in BINDING_NAMES]
#: hypothesis id -> tripped hard gates of the standard (D10). "h_unknown" is deliberately absent: its gate
#: reads UNMEASURED.
STANDARD = {"h_ok": [], "h_bad": [[2, "counterparty names no agent class"]]}
#: Axis 3 on every card but the axis-3 case is passed in at a fixed value: it measures a TREE, not a
#: cohort, and the tree it measures is the one case axis3_tree builds.
AXIS3_MET = {"value": 1.0, "floor_met": True}
AXIS3_SIX_OF_SEVEN = {"value": 0.857, "floor_met": False}

#: Curve shapes: (drift, swing) per third; each day's PnL change is drift + swing, then drift - swing,
#: alternating, so a third's mean is its drift and its standard error is about swing / sqrt(140).
STEADY = ((1.0, 0.5), (1.0, 0.5), (1.0, 0.5))
CURVES = {
    "consistent": STEADY,
    "mixed_third_within_2_se": ((1.0, 0.5), (1.0, 0.5), (0.05, 1.0)),    # 0.05 < 2 x ~0.085: flat
    "losing_third_curve_up": ((1.0, 0.5), (1.0, 0.5), (-0.5, 0.5)),      # ends 210 above its start
    "negative_overall_no_losing_third": ((-0.05, 1.0),) * 3,            # every third flat, ends -21
    "flat_flat_losing": ((0.01, 1.0), (0.01, 1.0), (-1.0, 0.5)),         # round 2's shape
    "one_regime": ((1.0, 0.5), (0.0, 0.5), (0.0, 0.5)),
}


def _scorer():
    sys.path.insert(0, str(ROOT))
    from forge.offline import benchmark as B
    return B


def _ts(day, hour=12):
    """Epoch seconds of `hour`:00 America/New_York on `day`."""
    return datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time(hour), tzinfo=ET).timestamp()


def _curve(thirds, points=421):
    """A {date: cumulative PnL} curve -- the real cache format -- from (drift, swing) per third."""
    d0, v, out = datetime.date(2019, 1, 2), 0.0, {}
    for i in range(points):
        m, s = thirds[min(i * 3 // points, 2)]
        v += m + (s if i % 2 == 0 else -s)
        out[(d0 + datetime.timedelta(days=i)).isoformat()] = round(v, 6)
    return out


_MISSING = object()
#: the settings a neighbour changes, one knob each (D3's definition of a true neighbour)
_KNOBS = ({"decay": 8}, {"neutralization": "SUBINDUSTRY"}, {"truncation": 0.05})


class _Desk:
    """The inputs of one synthetic cohort: journal rows, POSTs and the per-alpha measurements."""

    def __init__(self):
        self.rows, self.scored, self.corr, self.history, self.curves = [], {}, {}, [], {}

    def alpha(self, alpha, day, kind="P", post=0.1, version=None, status="COMPLETE", hour=12, checks=None,
              dsr=0.97, pbo=True, prod=0.5, self_corr=0.4, neighbours=None, curve=STEADY, hyp=None, own=1.8,
              run_config=None, pbo_status=None):
        """kind P = PROVEN (two true neighbours, a steady curve, DSR/PBO/corr passing, admissible
        hypothesis), U = UNPROVEN (no neighbours), R = REFUTED (its hypothesis trips a hard gate). Any
        keyword overrides one input. `post` = days from creation to an accepted POST (None: never
        POSTed). `neighbours` = sharpes, or (sharpe, settings) pairs to place a row by hand. `prod` None =
        no correlation reading at all; `self_corr` None = a prod reading with no self reading. `run_config`
        stamps meta.run_config (D30's second stamp). `pbo_status` is the scored store's `pbo_status`, the
        text forge/pbo.py writes beside a missing PBO ("insufficient (< 20 trials)", D56)."""
        meta = {"hypothesis": hyp or ("h_bad" if kind == "R" else "h_ok"), "mechanism_key": "m_%s" % alpha}
        if version:
            meta["pipeline_version"] = version
        if run_config is not None:
            meta["run_config"] = run_config
        settings = {"region": "USA", "delay": 1, "universe": "TOP3000", "decay": 4, "neutralization": "INDUSTRY",
                    "truncation": 0.08}
        base = {"status": status, "checks": PASS if checks is None else checks, "formula": "rank(%s)" % alpha,
                "dateCreated": datetime.datetime.fromtimestamp(_ts(day, hour), ET).isoformat(), "meta": meta}
        self.rows.append(dict(base, alpha=alpha, sharpe=own, settings=settings))
        if neighbours is None:
            neighbours = () if kind == "U" else (1.7, 1.6)
        for i, nb in enumerate(neighbours):
            sharpe, knob = nb if isinstance(nb, tuple) else (nb, _KNOBS[i])
            self.rows.append(dict(base, alpha="%s_n%d" % (alpha, i + 1), sharpe=sharpe, settings=dict(settings, **knob),
                                  checks=PASS, status="COMPLETE"))
        x = {}
        if dsr is not _MISSING:
            x["dsr"] = dsr
        if pbo is not _MISSING:
            x["pbo_pass"] = pbo
        if pbo_status is not None:
            x["pbo_status"] = pbo_status
        self.scored[alpha] = x
        if prod is not None:
            self.corr[alpha] = {"prod": prod} if self_corr is None else {"prod": prod, "self": self_corr}
        if curve is not None:
            self.curves[alpha] = curve if isinstance(curve, dict) else _curve(curve)
        if post is not None:
            self.post(alpha, _ts(day, hour) + post * DAY)
        return self

    def post(self, alpha, at, http=201):
        self.history.append({"alpha": alpha, "http": http, "posted_at": at, "mechanism_key": None})
        return self

    def card(self, now, axis3=AXIS3_MET, **kw):
        return _scorer().build_from(self.rows, self.scored, self.corr, self.history, self.curves, STANDARD,
                                    now=now, axis3=dict(axis3) if axis3 is not None else None, **kw)


def _outcome(c) -> dict:
    """What a card DECIDED: verdict, floors, rank levels, window and the two product axes."""
    a1, a2 = c["axes"]["axis1_product"], c["axes"]["axis2_throughput"]
    return {"verdict": c["verdict"], "floors_unmet": c["floors_unmet"], "rank": c["rank"],
            "window": {k: c["window"][k] for k in ("since", "until_exclusive", "quota_days", "excluded_unfinished_day")},
            "axis1": {"n": a1["n"], "value": a1["value"], "floor_met": a1["floor_met"],
                      "status_counts": a1["status_counts"], "gate_coverage": a1["gate_coverage"]},
            "axis2": {k: a2[k] for k in ("quota_days", "exposure", "scored_alphas", "submissions_of_alphas_this_version_produced",
                                         "proven_clean_submissions", "unproven_submissions", "refuted_submissions",
                                         "proven_clean_per_quota_day", "poisson_95_per_day", "floor_met", "sustainable")}}


def _per_alpha(c) -> dict:
    return {d["alpha"]: {"status": d["status"], "gates": d["gates"]} for d in c["axes"]["axis1_product"]["detail"]}


# --------------------------------------------------------------------------------------- the cases
def case_axis1_gates() -> dict:
    """PROVEN / UNPROVEN / REFUTED per gate (D3, D10, A5): for each of the seven gates, one submitted alpha
    where ONLY that gate reads False (refuted) and one where ONLY that gate is unmeasured (unproven); the
    binding gate cannot be unmeasured. Plus a case on each side of every threshold, and (draw-3 ci SERIOUS 3
    and 4) the cases that the audit's invisible edits move:
      * a binding check ABSENT from the check set, and one reading PENDING: a check that did not read PASS
        has not passed (RULE 0 #5: "counting rows with incomplete check sets as passes");
      * one gate False AND another unmeasured: refuted, because a failure is known whatever is missing;
      * the SELF-correlation line, three ways: over the default line; under the default but over its own
        SELF_CORRELATION row limit; and a PROD_CORRELATION row limit that must bind the prod reading only.
        On these, corr_lines reading PROD twice, the two names swapped, the two readings swapped and the
        self comparison dropped each move a status;
      * a prod reading with no self reading. The draw-3 scorer read it as a FAILED gate (refuted); since the
        draw3_fix scoring task _corr_ok is three-valued and it reads UNMEASURED (unproven): nothing was
        measured to fail. The golden moved with that edit, which is what this case was for;
      * (draw3_fix ci 6) a self reading exactly AT the default line: a reading at the line fails
        (CORR_UNDER_LINE is strict), and `s <= sl` on the self line moved no case before this one."""
    d, day = _Desk(), "2026-09-10"
    d.alpha("all_gates_pass", day)
    # -- only this gate False
    d.alpha("binding_fails", day, checks=[dict(c, result="FAIL") if c["name"] == "LOW_FITNESS" else c for c in PASS])
    d.alpha("dsr_fails", day, dsr=0.5)
    d.alpha("pbo_fails", day, pbo=False)
    d.alpha("corr_fails", day, prod=0.75)
    d.alpha("neighbourhood_fails", day, neighbours=(0.1, 0.2))
    d.alpha("regime_fails", day, curve=CURVES["flat_flat_losing"])
    d.alpha("standard_fails", day, hyp="h_bad")
    # -- only this gate unmeasured
    d.alpha("dsr_unmeasured", day, dsr=_MISSING)
    d.alpha("pbo_unmeasured", day, pbo=_MISSING)
    d.alpha("corr_unmeasured", day, prod=None)
    d.alpha("neighbourhood_unmeasured", day, neighbours=())
    d.alpha("regime_unmeasured", day, curve=None)
    d.alpha("standard_unmeasured", day, hyp="h_unknown")
    # -- the inline thresholds, one case each side
    d.alpha("dsr_exactly_0_95", day, dsr=0.95)
    d.alpha("dsr_0_9499", day, dsr=0.9499)
    d.alpha("corr_exactly_at_the_line", day, prod=0.70)
    d.alpha("corr_just_under_the_line", day, prod=0.6999)
    d.alpha("corr_under_default_over_row_limit", day, prod=0.55,
            checks=PASS + [{"name": "PROD_CORRELATION", "result": "PASS", "limit": 0.5}])
    d.alpha("neighbours_retain_exactly_half", day, own=2.0, neighbours=(1.0, 1.0))
    d.alpha("neighbours_retain_0_49", day, own=2.0, neighbours=(0.98, 0.98))
    d.alpha("one_neighbour_only", day, neighbours=(1.7,))
    d.alpha("two_rows_differing_in_two_knobs", day,
            neighbours=((1.7, {"decay": 8, "truncation": 0.05}), (1.6, {"neutralization": "SUBINDUSTRY", "decay": 16})))
    d.alpha("curve_of_299_points", day, curve=dict(list(_curve(STEADY).items())[:299]))
    d.alpha("curve_of_300_points", day, curve=dict(list(_curve(STEADY).items())[:300]))
    # -- draw-3 ci SERIOUS 4: a binding check that did not read PASS, and the order of alpha_status
    fitness_dropped = [c for c in PASS if c["name"] != "LOW_FITNESS"]
    d.alpha("binding_check_missing", day, checks=fitness_dropped)
    d.alpha("binding_check_pending", day, checks=fitness_dropped + [{"name": "LOW_FITNESS", "result": "PENDING"}])
    d.alpha("one_gate_false_one_unmeasured", day, dsr=0.5, pbo=_MISSING)
    # -- draw-3 ci SERIOUS 3: the self-correlation line
    d.alpha("self_corr_over_the_default_line", day, prod=0.5, self_corr=0.75)
    d.alpha("self_corr_over_its_own_row_limit", day, prod=0.5, self_corr=0.4,
            checks=PASS + [{"name": "SELF_CORRELATION", "result": "PASS", "limit": 0.3}])
    d.alpha("prod_row_limit_does_not_bind_self", day, prod=0.4, self_corr=0.6,
            checks=PASS + [{"name": "PROD_CORRELATION", "result": "PASS", "limit": 0.5}])
    d.alpha("self_corr_unmeasured_prod_measured", day, prod=0.5, self_corr=None)
    d.alpha("self_corr_exactly_at_the_default_line", day, prod=0.5, self_corr=0.70)
    c = d.card(_ts("2026-09-11", 15))
    a1 = c["axes"]["axis1_product"]
    return {"per_alpha": _per_alpha(c), "status_counts": a1["status_counts"], "value": a1["value"],
            "floor_met": a1["floor_met"], "gate_coverage": a1["gate_coverage"]}


def case_regime() -> dict:
    """regime_stability's verdict order (S3-NL): negative-overall, losing-third, consistent, mixed,
    one-regime; each third judged against REGIME_SE_MULTIPLE standard errors; under CURVE_POINTS_MIN (300)
    points unmeasured -- 299 is unmeasured and 300 is measured, so the bound is pinned exactly (draw-3 ci
    SERIOUS 4: with cases only at 299 and 421, moving it to 400 changed nothing)."""
    B = _scorer()
    out = {name: {k: B.regime_stability(_curve(shape))[k] for k in ("verdict", "labels", "winning_thirds")}
           for name, shape in CURVES.items()}
    out["curve_of_299_points"] = {"verdict": B.regime_stability(list(_curve(STEADY).values())[:299])["verdict"]}
    out["curve_of_300_points"] = {"verdict": B.regime_stability(list(_curve(STEADY).values())[:300])["verdict"]}
    out["passing_verdicts"] = list(B.REGIME_PASS)
    return out


def case_window() -> dict:
    """Whole ET quota days (round 1 S5, F3): the unfinished day `now` falls in is excluded, a WARNING row
    is scored and can be a proven submission, an ERROR row and a row with no check set are not scored."""
    d = _Desk()
    d.alpha("warning_row", "2026-09-14", status="WARNING")
    d.alpha("complete_row", "2026-09-15")
    d.alpha("error_row", "2026-09-14", status="ERROR", post=None, neighbours=())
    d.alpha("no_check_set", "2026-09-14", checks=[], post=None, neighbours=())
    d.alpha("created_on_the_unfinished_day", "2026-09-16", hour=9, post=0.05)      # POSTed 10:12, before now
    c = d.card(_ts("2026-09-16", 15))
    out = _outcome(c)
    out["graded_submissions"] = sorted(_per_alpha(c))
    out["posts_this_version_made"] = c["axes"]["axis2_throughput"]["posts_this_version_made"]
    return out


def case_post_horizon() -> dict:
    """A4 and M6: a POST is CREDITED (axis 2) only by `now` and within POST_HORIZON_DAYS of creation; an alpha
    counts once however many times it was accepted; a POST with no time is counted as such, never credited; a
    rejected POST is never a submission. Graded twice: before the horizon closes and after.

    D49 (Khoa, 2026-09-23 ~21:00; round 3 S1): every accepted POST by `now` counts against rank level 1 of the
    version that created the alpha, whatever its lag -- so posted_14_days_and_1_hour and posted_after_20_days are
    GRADED by axis 1 (`graded_by_axis1`, `rank_level_1`) and listed `posted_beyond_the_horizon`, and never
    credited (`submissions`). Before D49 an unproven alpha POSTed after 14.05 days cost its version nothing.
    Every alpha here is unproven (no neighbours), so level 1 is the count of graded POSTed alphas."""
    d, day = _Desk(), "2026-09-01"
    for a, lag in (("posted_same_day", 0.1), ("posted_at_exactly_14_days", 14.0),
                   ("posted_14_days_and_1_hour", 14.0 + 1 / 24), ("posted_after_the_first_now", 6.0),
                   ("posted_after_20_days", 20.0)):
        d.alpha(a, day, kind="U", post=lag)
    d.alpha("posted_twice", day, kind="U", post=0.1).post("posted_twice", _ts(day) + 0.2 * DAY)
    d.alpha("post_without_a_time", day, kind="U", post=None).post("post_without_a_time", None)
    d.alpha("post_at_time_zero", day, kind="U", post=None).post("post_at_time_zero", 0)
    d.alpha("post_rejected_403", day, kind="U", post=None).post("post_rejected_403", _ts(day) + 0.1 * DAY, http=403)
    out = {}
    for label, now in (("graded_2026-09-06", _ts("2026-09-06", 12)), ("graded_2026-09-25", _ts("2026-09-25", 12))):
        c = d.card(now, since=day, until="2026-09-02")
        out[label] = {"graded_by_axis1": sorted(_per_alpha(c)),
                      "posted_beyond_the_horizon": c["axes"]["axis1_product"]["posted_beyond_the_horizon"],
                      "rank_level_1": c["rank"]["refuted_or_unproven_submitted"],
                      "submissions": c["axes"]["axis2_throughput"]["submissions_of_alphas_this_version_produced"],
                      "post_horizon": c["axes"]["axis2_throughput"]["post_horizon"]}
    return out


def case_floors() -> dict:
    """D2 / D6 / A5: the hard floors and the verdict, at and around each boundary. Axis 1 needs EVERY
    submitted alpha proven (an unproven one with no refuted one still fails it); axis 2 needs a POINT rate
    of at least 4 proven clean submissions per quota day (an interval reaching 4 is not enough); a card
    with no submission has no product; unknown exposure cannot meet axis 2; axis 3 can fail alone."""
    day, now = "2026-09-18", _ts("2026-09-19", 15)

    def desk(proven, unproven=0, version=None):
        d = _Desk()
        for i in range(proven):
            d.alpha("p%d" % i, day, version=version)
        for i in range(unproven):
            d.alpha("u%d" % i, day, kind="U", version=version)
        return d
    ledger = [{"outcome": "deployed", "pipeline_version": "V", "version": "tree-V", "started_at": _ts("2026-09-17", 10) - 600,
               "finished_at": _ts("2026-09-17", 10), "commit_time": None, "git_dirty": False}]
    cards = {
        "four_proven_in_one_day": desk(4).card(now),
        "three_proven_in_one_day": desk(3).card(now),
        "four_proven_and_one_unproven": desk(4, 1).card(now),
        "no_submission": desk(0, 0).alpha("never_posted", day, post=None).card(now),
        "four_proven_axis3_six_of_seven": desk(4).card(now, axis3=AXIS3_SIX_OF_SEVEN),
        "version_card_exposure_unknown": desk(4, version="V").card(now, version="V"),
        "version_card_exposure_from_the_ledger": desk(4, version="V").card(now, version="V", deploys=ledger),
    }
    return {k: _outcome(c) for k, c in cards.items()}


def case_rank() -> dict:
    """D25: versions ranked LEXICOGRAPHICALLY -- (1) fewer refuted + unproven submitted (D26), (2) more proven
    clean per quota day, (3) axis 3 -- with no weight, after the verdict (D29; every card here reads FAIL);
    an unmeasured level ranks below every measured one. Adding proven output raises the rank; an unproven
    submission now costs a place at level 1 (D26: "P+U" below "P", and "U" below "nothing submitted"); a
    refuted one drops the card below every card with fewer, however much proven output it has (P+P+P+R
    below P, as ticked).

    Graded at 2026-10-10, after the POST horizon of the newest row (09-22, final 10-07) has closed, with the
    windows ending where they did (until 09-23): D27 refuses to rank a card whose horizon is still open, and
    the old clock (09-23) now raises NotComparable (draw3_fix scoring engineer's report; case_rank_open_horizon
    pins the refusal).

    "nothing submitted" has a MEASURED rate of 0.0 and level 1 = 0; "P, exposure unknown" has no rate.
    Draw-3 ci SERIOUS 4: with no measured-zero card, ranking an unknown rate as 0/day changed nothing. "U"
    was that card until D26 gave it level 1 = 1, which sets it apart at level 1 before its rate is read, so
    the measured zero at level 1 = 0 is now "nothing submitted". It must rank above the unknown card, and the
    two must not tie."""
    B = _scorer()
    days, now = ("2026-09-21", "2026-09-22"), _ts("2026-10-10", 15)
    until = "2026-09-23"

    def desk(kinds, version=None):
        d = _Desk()
        for i, k in enumerate(kinds):
            d.alpha("%s%d" % (k.lower(), i), days[i % 2], kind=k, version=version)
        return d
    cards = {
        "P": desk("P").card(now, since=days[0], until=until),
        "P+U": desk("PU").card(now, since=days[0], until=until),
        "PPP": desk("PPP").card(now, since=days[0], until=until),
        "PPP+R": desk("PPPR").card(now, since=days[0], until=until),
        "P, axis 3 six of seven": desk("P").card(now, since=days[0], until=until, axis3=AXIS3_SIX_OF_SEVEN),
        "P, exposure unknown": desk("P", version="VU").card(now, version="VU", until=until),
        "U": desk("U").card(now, since=days[0], until=until),
        "nothing submitted": _Desk().alpha("never_posted", days[0], post=None).card(now, since=days[0], until=until),
    }
    names = list(cards)
    by_cmp = sorted(names, key=functools.cmp_to_key(lambda a, b: B.rank_cmp(cards[a], cards[b])))
    by_key = sorted(names, key=lambda n: B.rank_key(cards[n]))
    pairs = (("P", "P+U"), ("PPP", "P"), ("PPP+R", "P"), ("P, axis 3 six of seven", "P"),
             ("P, exposure unknown", "P, axis 3 six of seven"), ("P, exposure unknown", "PPP+R"),
             ("U", "P, exposure unknown"), ("nothing submitted", "P, exposure unknown"), ("U", "nothing submitted"))
    return {"levels": {n: c["rank"] for n, c in cards.items()},
            "verdicts": {n: c["verdict"] for n, c in cards.items()},
            "best_first": by_cmp, "rank_key_agrees_with_rank_cmp": by_key == by_cmp,
            "rank_cmp": {"%s vs %s" % p: B.rank_cmp(cards[p[0]], cards[p[1]]) for p in pairs}}


def _rank_or_refusal(B, *cards):
    """rank_key of one card, or rank_cmp of two, as JSON -- or the refusal D27 gives instead."""
    try:
        return list(B.rank_key(cards[0])) if len(cards) == 1 else B.rank_cmp(*cards)
    except B.NotComparable as exc:
        return "NotComparable: " + str(exc)


def case_rank_open_horizon() -> dict:
    """D27 (Khoa, 2026-09-23 ~15:30): a card whose POST horizon has not closed is NOT RANKED -- rank_key and
    rank_cmp refuse it and name the ET day from which it can be compared. Before D27 a live version ranked
    below an identical retired one only because its POSTs had not landed yet (round 2's A4 bias).

    One proven submission created 2026-09-21 (horizon final at 2026-10-06 00:00 ET), graded three ways:
      open                  at 09-23: not final, refused;
      final                 at 10-10 (window unchanged, until 09-23): ranked;
      late_clock_early_cut  at 10-30 but with data_through 09-24: finality is judged at seen_until =
                            min(now, data_through) (draw3_fix scoring 1), so still refused -- a copy cut
                            before the horizon closed cannot show the POSTs that landed after the cut.
    And rank_cmp of the open card against the final one refuses as well."""
    B = _scorer()

    def graded(now, **kw):
        return _Desk().alpha("p0", "2026-09-21").card(now, since="2026-09-21", until="2026-09-23", **kw)
    cards = {"open": graded(_ts("2026-09-23", 15)), "final": graded(_ts("2026-10-10", 15)),
             "late_clock_early_cut": graded(_ts("2026-10-30", 15), data_through=_ts("2026-09-24", 12))}
    out = {n: {"horizon_final": c["rank"]["horizon_final"], "comparable_from_et": c["rank"]["comparable_from_et"],
               "rank_key": _rank_or_refusal(B, c)} for n, c in cards.items()}
    out["rank_cmp_open_vs_final"] = _rank_or_refusal(B, cards["open"], cards["final"])
    return out


def case_rank_equal_exposure() -> dict:
    """D57 (Khoa, 2026-09-24 ~02:20; round 4 S2): rank_cmp counts rank level 1 on both cards at EQUAL post-creation
    exposure -- only the POSTs that came within the same lag from creation on both sides, the lag being the shorter of
    the two cards' post_exposure_days (build_from measures it to seen_until = min(now, data_through)). Round 4 S2's
    pair: two identical date cards, one UNPROVEN alpha each, POSTed 20 days after creation; "older" created 09-10,
    "newer" 09-20. Graded three ways:
      graded_2026-10-06                older POSTed 09-30 (level 1 = 1), newer's POST not yet made (0); exposures
                                       25.6 and 15.6 days, so both count at 15.6: level 1 = 0 each, TIED. Before
                                       D57 the newer card ranked above (rank_cmp -1) only for being younger;
      graded_2026-10-30_copy_cut_2026-10-06  the same cards graded later on a copy cut 10-06 that shows older's POST
                                       and not newer's: exposure is measured to the cut, not to `now`, so still TIED;
      older_recorded_before_d57        the older card without its lags (a card recorded before D57): the lag cannot be
                                       equalised, so BOTH are counted raw -- 0 against 1, newer above (rank_cmp -1)."""
    B = _scorer()

    def card(day, until, now, post=20.0, **kw):
        return _Desk().alpha("u", day, kind="U", post=post).card(now, since=day, until=until, **kw)

    def levels(c):
        return {k: c["rank"].get(k) for k in ("refuted_or_unproven_submitted", "level1_post_lag_days",
                                              "post_exposure_days", "horizon_final")}
    at, late, cut = _ts("2026-10-06", 15), _ts("2026-10-30", 15), _ts("2026-10-06", 15)
    pairs = {"graded_2026-10-06": (card("2026-09-10", "2026-09-11", at), card("2026-09-20", "2026-09-21", at)),
             "graded_2026-10-30_copy_cut_2026-10-06": (card("2026-09-10", "2026-09-11", late, data_through=cut),
                                                       card("2026-09-20", "2026-09-21", late, post=None, data_through=cut))}
    older = json.loads(json.dumps(pairs["graded_2026-10-06"][0]))
    for k in ("level1_post_lag_days", "post_exposure_days"):
        older["rank"].pop(k, None)
    pairs["older_recorded_before_d57"] = (older, pairs["graded_2026-10-06"][1])
    return {label: {"older": levels(o), "newer": levels(n), "rank_cmp_newer_vs_older": _rank_or_refusal(B, n, o)}
            for label, (o, n) in pairs.items()}


def case_verdict_leads_rank() -> dict:
    """D29 (Khoa, 2026-09-23 ~15:45): the verdict leads the rank -- PASS before FAIL, then the D25/D26
    levels. "PASS" meets every floor with 4 proven clean submissions on one day; "FAIL, better levels" has 5
    and misses only the axis-3 floor (six of seven). On levels 1-3 alone the FAIL card ranks first (level 2,
    5.0 against 4.0); with the verdict leading, the PASS card does. Both are graded after their POST horizon
    closed (D27)."""
    B = _scorer()
    now, day = _ts("2026-10-10", 15), "2026-09-18"

    def desk(n):
        d = _Desk()
        for i in range(n):
            d.alpha("p%d" % i, day)
        return d
    cards = {"PASS": desk(4).card(now, until="2026-09-19"),
             "FAIL, better levels": desk(5).card(now, until="2026-09-19", axis3=AXIS3_SIX_OF_SEVEN)}
    return {"levels": {n: c["rank"] for n, c in cards.items()},
            "best_first": sorted(cards, key=functools.cmp_to_key(lambda a, b: B.rank_cmp(cards[a], cards[b]))),
            "rank_cmp_pass_vs_fail": B.rank_cmp(cards["PASS"], cards["FAIL, better levels"])}


def _arm(version, days, n_per_day, k_per_day):
    """Scored rows stamped with `version`: on each day the first k clear every binding check."""
    rows = []
    for day, k in zip(days, k_per_day):
        for i in range(n_per_day):
            rows.append({"alpha": "%s_%s_%03d" % (version, day, i), "status": "WARNING" if i % 10 == 9 else "COMPLETE",
                         "checks": PASS if i < k else [dict(PASS[0], result="FAIL")] + PASS[1:],
                         "dateCreated": "%sT12:00:00-04:00" % day, "formula": "rank(%s_%d)" % (version, i),
                         "settings": {"region": "USA", "delay": 1}, "meta": {"pipeline_version": version}})
    return rows


def case_compare() -> dict:
    """D24: compare() on the PRE-REGISTERED estimand (alphas clearing every binding check per 1,000 scored)
    with the exact conditional test at alpha 0.05 -- a better, a worse, an indistinguishable and a no-data
    pair; WARNING rows are in the denominator, the unfinished day and unscored rows are not. The deploy
    ledger gives each arm its live days, so the secondary POST reading (no verdict) is final for the arm
    whose horizon has closed and censored for the others (A4)."""
    B = _scorer()
    now = _ts("2026-09-20", 15)
    rows = (_arm("v16", ["2026-09-01", "2026-09-02"], 100, [8, 8]) + _arm("v04", ["2026-09-05", "2026-09-06"], 100, [2, 2])
            + _arm("v14", ["2026-09-10", "2026-09-11"], 100, [7, 7]))
    rows += [dict(rows[0], alpha="v16_on_the_unfinished_day", dateCreated="2026-09-20T09:00:00-04:00"),
             dict(rows[0], alpha="v16_error_row", status="ERROR")]
    ledger = [_deploy("deployed", day, pv=v) for day, v in (("2026-08-31", "v16"), ("2026-09-04", "v04"),
                                                           ("2026-09-09", "v14"), ("2026-09-12", "v99"))]
    out = {}
    for label, a, b in (("better", "v04", "v16"), ("worse", "v16", "v04"), ("indistinguishable", "v16", "v14"),
                        ("no_data", "v16", "never_stamped")):
        r = B.compare(rows, [], {}, STANDARD, {}, {}, a, b, now=now, deploys=ledger)
        o = {"verdict": r["verdict"], "estimand": r["estimand"],
             "arms": {v: {k: r["versions"][v].get(k) for k in ("scored_alphas", "clearing_every_binding_check",
                                                                "per_1000", "exact_95_per_1000")} for v in (a, b)}}
        if r["verdict"] != "no-data":
            m = r["minimum_detectable_ratio"]
            o.update({"p_value": r["p_value"], "rate_ratio_b_over_a": r["rate_ratio_b_over_a"],
                      "minimum_detectable_ratio": {"increase": m["increase"], "decrease": m["decrease"]},
                      "calendar_gap_days": r["calendar"]["gap_days"],
                      "submission_reading": {v: r["submissions_secondary"][v]["status"] for v in (a, b)}})
        out[label] = o
    return out


def _cell_rows(version, cells, run_config=None, tag=None):
    """Scored rows of one cohort, cell by cell: `cells` = [(region, day, n scored, k clearing every binding
    check)]; the cell is "<region>/d1" (benchmark.cell_of). `run_config` None leaves meta.run_config out."""
    rows, tag = [], tag or version
    meta = {"pipeline_version": version}
    if run_config is not None:
        meta["run_config"] = run_config
    for region, day, n, k in cells:
        for i in range(n):
            rows.append({"alpha": "%s_%s_%s_%04d" % (tag, region, day, i), "status": "COMPLETE",
                         "checks": PASS if i < k else [dict(PASS[0], result="FAIL")] + PASS[1:],
                         "dateCreated": "%sT12:00:00-04:00" % day, "formula": "rank(%s_%s_%d)" % (tag, region, i),
                         "settings": {"region": region, "delay": 1}, "meta": dict(meta)})
    return rows


def case_compare_within_cell() -> dict:
    """D28 (Khoa, 2026-09-23 ~15:30): D24's estimand is compared WITHIN each cell; better / worse only when the
    stratified exact test is significant AND every cell with an event points the same way; otherwise
    INDISTINGUISHABLE. Before it the pooled test decided across cells whose share of a day ranged 0.32-0.94
    (draw-3 scoring SERIOUS 6; RULE 0 #6). Arm A on 09-01, arm B on 09-05, graded 09-20; (k, n) per cell:
      simpson          USA A 10/100, B 81/900; EUR A 9/900, B 0/100. Pooled, B is 4.3x A (p < 1e-5); within
                       cell B is LOWER in both, and the stratified test is not significant: indistinguishable.
                       A verdict taken from the POOLED test reads "worse" here;
      cells_disagree   USA A 100/1000, B 200/1000; EUR A 50/1000, B 20/1000: significant (p ~ 3e-4), but USA
                       says B higher and EUR B lower: indistinguishable. A direction read from the pooled
                       rates reads "better";
      cells_agree      USA A 20/1000, B 60/1000; EUR A 2/1000, B 8/1000: better (the control: within cell can
                       say better);
      a_cell_one_arm_never_scored  USA as cells_agree; ASI A 1/100 and B none: that cell has an event and no
                       direction, so indistinguishable -- the scoring engineer's reading of D28, printed on
                       every compare() as open for Khoa; pinned as it decides, not endorsed."""
    B = _scorer()
    now = _ts("2026-09-20", 15)
    pairs = {
        "simpson": ([("USA", "2026-09-01", 100, 10), ("EUR", "2026-09-01", 900, 9)],
                    [("USA", "2026-09-05", 900, 81), ("EUR", "2026-09-05", 100, 0)]),
        "cells_disagree": ([("USA", "2026-09-01", 1000, 100), ("EUR", "2026-09-01", 1000, 50)],
                           [("USA", "2026-09-05", 1000, 200), ("EUR", "2026-09-05", 1000, 20)]),
        "cells_agree": ([("USA", "2026-09-01", 1000, 20), ("EUR", "2026-09-01", 1000, 2)],
                        [("USA", "2026-09-05", 1000, 60), ("EUR", "2026-09-05", 1000, 8)]),
        "a_cell_one_arm_never_scored": ([("USA", "2026-09-01", 1000, 20), ("ASI", "2026-09-01", 100, 1)],
                                        [("USA", "2026-09-05", 1000, 60)]),
    }
    out = {}
    for label, (a, b) in pairs.items():
        r = B.compare(_cell_rows("va", a) + _cell_rows("vb", b), [], {}, STANDARD, {}, {}, "va", "vb", now=now)
        out[label] = {"verdict": r["verdict"], "p_value": r["p_value"], "rate_ratio_b_over_a": r["rate_ratio_b_over_a"],
                      "pooled": {k: r["pooled"][k] for k in ("p_value", "rate_ratio_b_over_a", "decides")},
                      "cells": {c: [v["a"], v["b"], v["direction"]] for c, v in r["cells"].items()}}
    return out


def _outcome_or_refusal(fn):
    try:
        return fn()
    except ValueError as exc:
        return "ValueError: " + str(exc)


def case_cohorts() -> dict:
    """D30 (Khoa, 2026-09-23 ~15:45; implemented as a second stamp, 00_agreements.md): a cohort is the pair
    (meta.pipeline_version, meta.run_config), so the same deployed bytes run with two argument sets are two
    cohorts; a row with no run_config is (pv, None); a '+'-suffixed or marker stamp, and a run_config that is
    not a non-empty string, form NO cohort. One pipeline_version V:
      V@rcA  200 scored on 09-01/02, 16 clearing;   V@rcB  200 on 09-05/06, 4 clearing;
      V      50 on 09-08 with no run_config;       V+untracked  50 on 09-09;   V with run_config 7  10 on 09-10;
      pipeline_version "unknown" and "ambiguous", 10 each on 09-11 (the STAMP_MARKERS words);
      V with run_config "ambiguous" 10, and with run_config "rc+x" 10, on 09-12.
    compare(V@rcA, V@rcB) reads "worse" on two cohorts of ONE pipeline_version; a version card of V@rcA
    grades rcA's rows only; "V+untracked", "unknown" and "V@ambiguous" are refused wherever a cohort is asked for.
    Draw4_build ci 1: no row carried a marker word, and dropping `v not in STAMP_MARKERS` from plain_stamp moved
    no case; the marker rows are here for that edit. Draw4_build scoring 3 / pipeline P2: the marker rule now
    applies to run_config too (recover_orphans writes "ambiguous"); the "ambiguous" and "rc+x" run_config rows are
    here for that half."""
    B = _scorer()
    now = _ts("2026-09-20", 15)
    rows = (_cell_rows("V", [("USA", "2026-09-01", 100, 8), ("USA", "2026-09-02", 100, 8)], run_config="rcA", tag="V_rcA")
            + _cell_rows("V", [("USA", "2026-09-05", 100, 2), ("USA", "2026-09-06", 100, 2)], run_config="rcB", tag="V_rcB")
            + _cell_rows("V", [("USA", "2026-09-08", 50, 1)], tag="V_none")
            + _cell_rows("V+untracked", [("USA", "2026-09-09", 50, 1)], tag="V_untracked")
            + _cell_rows("V", [("USA", "2026-09-10", 10, 1)], run_config=7, tag="V_rc_not_a_string")
            + _cell_rows("unknown", [("USA", "2026-09-11", 10, 1)], tag="pv_marker_unknown")
            + _cell_rows("ambiguous", [("USA", "2026-09-11", 10, 1)], tag="pv_marker_ambiguous")
            + _cell_rows("V", [("USA", "2026-09-12", 10, 1)], run_config="ambiguous", tag="V_rc_marker_ambiguous")
            + _cell_rows("V", [("USA", "2026-09-12", 10, 1)], run_config="rc+x", tag="V_rc_suffixed"))
    counts = {}
    for r in rows:
        c = B.cohort_of(r)
        label = B.cohort_label(c) if c else "no cohort"
        counts[label] = counts.get(label, 0) + 1
    out = {"rows_per_cohort": counts, "compare": {}, "version_card": {}}
    for a, b in (("V@rcA", "V@rcB"), ("V", "V@rcA"), ("V@rcA", "V+untracked"), ("V@rcA", "unknown"),
                 ("V@rcA", "V@ambiguous")):
        def run(a=a, b=b):
            r = B.compare(rows, [], {}, STANDARD, {}, {}, a, b, now=now)
            return {"verdict": r["verdict"], "arms": {k: [v["scored_alphas"], v["clearing_every_binding_check"]]
                                                      for k, v in r["versions"].items()}}
        out["compare"]["%s vs %s" % (a, b)] = _outcome_or_refusal(run)
    for v in ("V@rcA", "V", "V+untracked", "ambiguous", "V@ambiguous"):
        def card(v=v):
            c = B.build_from(rows, {}, {}, [], {}, STANDARD, version=v, now=now)
            return {"version": c["window"]["version"], "cohort": c["window"]["cohort"],
                    "scored_alphas": c["axes"]["axis2_throughput"]["scored_alphas"]}
        out["version_card"][v] = _outcome_or_refusal(card)
    return out


def _formula_sha(formula) -> str:
    """sha256 of the formula TEXT, the key the meaning ledger's writer stamps (D39; the draw-4 fix builders'
    shared interface). Computed HERE, not by benchmark.formula_sha: an edit to the scorer's hash is then SEEN
    by case_generated_alpha, not mirrored into the rows it reads."""
    return hashlib.sha256(formula.encode("utf-8")).hexdigest()


def case_generated_alpha() -> dict:
    """D39 (Khoa, 2026-09-23 ~17:20): a GENERATED alpha (meta.hypothesis "gen:...") takes D10's gate half from
    its row in state/forge/meaning.jsonl: PROVEN on it when every decidable gate (G4's leg clause, G5-G8) is
    exactly true, REFUTED when one is false, UNPROVEN when one is unset or malformed or the row is missing.
    G1-G3 need prose a generated formula does not have: recorded "not applicable" and never make it unproven.
    A library composite still reads load_standard (the fixture's STANDARD). Every alpha here passes every other
    gate, so its status is decided by this gate alone. Graded with the ledger read and with it not read (None).

    WHICH ROW IS GRADED (round 3 S8, as benchmark.meaning_index reads it since the draw-4 fix): only a row whose
    formula_sha is the sha256 of THIS alpha's formula text, scored at or after the alpha's creation and by `now`;
    of those, the EARLIEST decides (a tie: the first in the file). Draw-4 scoring's cross-module report: the
    rows here carried placeholder shas (s1..s7), which that reader rightly ignores, so every generated alpha read
    "no row" and the D39 cases stopped deciding anything; they now carry the real sha (_formula_sha). The S8 rows:
      gen_only_another_formulas_row           a row for ANOTHER formula's sha (S8: read proven): no row;
      gen_another_formulas_row_beside_its_own the other formula's all-true row and its own G5-false row: refuted;
      gen_row_scored_before_creation          all true, scored an hour before the alpha existed (S8: scored_at=1);
      gen_earliest_row_decides                G5 false, then all true a minute later (S8: the later row won);
      gen_tie_first_in_file_decides           the same two rows at the same second: the first in the file.
    `gen_malformed_gate_value` and the two tie/order rules are the scorer's READING, pinned as it decides; D39
    does not settle them.

    D56 (Khoa, 2026-09-24 ~02:20; round 4 S5): PBO "insufficient" on a GENERATED alpha reads NOT APPLICABLE --
    printed unmeasured, never counted against the version -- because a D38 family pool holds at most 12 settings
    and PBO needs 20. Each alpha below has an all-true meaning row of its own and passes every other gate, so PBO
    alone decides it:
      gen_pbo_insufficient       generated, no PBO, pbo_status "insufficient (< 20 trials)": PROVEN, pbo_pass
                                 listed not applicable and left out of gate_coverage;
      gen_pbo_pending            generated, no PBO, pbo_status "pending": UNPROVEN (only "insufficient" is D56's);
      library_pbo_insufficient   a library composite, no PBO, "insufficient": UNPROVEN (D56 names generated pools).
    `gate_coverage` is the card's measured share of gates, which D56 computes without the not-applicable one."""
    day, now = "2026-09-10", _ts("2026-09-11", 15)
    t0, created = _ts(day, 18), _ts(day, 12)
    insufficient = "insufficient (< 20 trials)"

    def gates(**kw):
        return dict({"G1": None, "G2": None, "G3": None, "G4": True, "G5": True, "G6": True, "G7": True, "G8": True}, **kw)
    OWN, OTHER = "own", "other"
    rows = {"gen_every_decidable_gate_true": [(OWN, gates(), t0)],
            "gen_g5_false": [(OWN, gates(G5=False), t0)],
            "gen_g6_unset": [(OWN, gates(G6=None), t0)],
            "gen_no_meaning_row": [],
            "gen_row_scored_after_the_clock": [(OWN, gates(), _ts("2026-09-12", 12))],
            "gen_only_another_formulas_row": [(OTHER, gates(), t0)],
            "gen_another_formulas_row_beside_its_own": [(OTHER, gates(), t0), (OWN, gates(G5=False), t0 + 60)],
            "gen_row_scored_before_creation": [(OWN, gates(), created - 3600)],
            "gen_earliest_row_decides": [(OWN, gates(G5=False), t0), (OWN, gates(), t0 + 60)],
            "gen_tie_first_in_file_decides": [(OWN, gates(G5=False), t0), (OWN, gates(), t0)],
            "gen_malformed_gate_value": [(OWN, gates(G7="yes"), t0)],
            # D56: an all-true row of its own; the PBO reading decides
            "gen_pbo_insufficient": [(OWN, gates(), t0)], "gen_pbo_pending": [(OWN, gates(), t0)]}
    pbo = {"gen_pbo_insufficient": insufficient, "gen_pbo_pending": "pending"}
    d = _Desk()
    for alpha in rows:
        d.alpha(alpha, day, hyp="gen:family_" + alpha,
                **({"pbo": _MISSING, "pbo_status": pbo[alpha]} if alpha in pbo else {}))
    d.alpha("library_composite", day, hyp="h_ok")
    d.alpha("library_pbo_insufficient", day, hyp="h_ok", pbo=_MISSING, pbo_status=insufficient)
    sha = {OWN: lambda a: _formula_sha("rank(%s)" % a), OTHER: lambda a: _formula_sha("rank(%s_other)" % a)}
    # route "generated": a value of forge/meaning.py ROUTES (draw5 meaning, routed to this file: "auto" is not one)
    meaning = [{"alpha": a, "formula_sha": sha[which](a), "gates": g, "route": "generated", "scorer": "fixture",
                "scored_at": t} for a, rs in rows.items() for which, g, t in rs]
    out = {"gate_coverage": {}}
    for label, m in (("ledger_read", meaning), ("ledger_not_read", None)):
        c = d.card(now, meaning=m)
        out[label] = {x["alpha"]: {"status": x["status"], "gate": x["gates"]["hypothesis_standard_8of8"],
                                   "route": x["standard_route"]["route"],
                                   "g1_g3": x["standard_route"].get("not_applicable"),
                                   "note": x["standard_route"].get("note"),
                                   "graded_row_sha_is_its_own": (x["standard_route"].get("formula_sha")
                                                                 == _formula_sha("rank(%s)" % x["alpha"]))
                                   if "formula_sha" in x["standard_route"] else None,
                                   "not_applicable": sorted(x.get("not_applicable") or {})}
                      for x in c["axes"]["axis1_product"]["detail"]}
        out["gate_coverage"][label] = c["axes"]["axis1_product"]["gate_coverage"]
    return out


def _deploy(outcome, day, hour=10, pv="V"):
    return {"outcome": outcome, "pipeline_version": pv, "version": "tree-" + pv, "started_at": _ts(day, hour) - 600,
            "finished_at": _ts(day, hour), "commit_time": None, "git_dirty": False}


def case_dora() -> dict:
    """A9: DORA is REPORTED on a card and never scored. OFF (no ledger read): no DORA block. ON: the keys
    and the band are printed, and the verdict and the rank are exactly those of the OFF card.

    Three ledgers, graded at 2026-09-25 15:00 ET with dora()'s 28-day window. HEALTHY meets all three band
    checks, DEGRADED misses all three, so every band check is seen both ways. Draw-3 ci MINOR: the old text
    said this while deploys/week read True in both ledgers and time-to-restore appeared once; after the
    draw-3 scorer (noop skipped, a restore only on a version change) time-to-restore appeared nowhere.
      healthy    10 deploys, one rolled back and restored by a NEW version an hour later: CFR 0.1,
                 2.5 a week, 1 h to restore;
      degraded   3 deploys (its `noop` row is not a deploy), one rolled back, restored by a new version
                 30 h later: CFR 0.333, 0.75 a week, 30 h;
      reshipped  as degraded, but the deploy after the rollback re-ships the version already running: no
                 restore, so time-to-restore is not measured and its band check is absent.
    All of healthy's and degraded's deploys but two fall more than 7 days before `now`, so the 28-day window
    shrunk to 7 moves deploys_per_week on both (draw-3 ci SERIOUS 4)."""
    d = _Desk().alpha("p0", "2026-09-24")
    now = _ts("2026-09-25", 15)
    off = d.card(now)
    healthy = [_deploy("deployed", "2026-09-%02d" % dd, pv="H%02d" % dd) for dd in (1, 4, 7, 10, 13, 16, 19, 22)]
    healthy += [_deploy("rolled_back", "2026-09-14", pv="H14"), _deploy("deployed", "2026-09-14", hour=11, pv="H14b")]
    ledgers = {
        "healthy": healthy,
        "degraded": [_deploy("deployed", "2026-09-10", pv="V1"), _deploy("rolled_back", "2026-09-12", pv="V2"),
                     _deploy("deployed", "2026-09-13", hour=16, pv="V3"), _deploy("noop", "2026-09-20", pv="V3")],
        "reshipped": [_deploy("deployed", "2026-09-10", pv="V1"), _deploy("rolled_back", "2026-09-12", pv="V2"),
                      _deploy("deployed", "2026-09-13", hour=16, pv="V1")],
    }
    out = {"off": {"dora_block": "dora" in off, "verdict": off["verdict"], "rank": off["rank"]}}
    for name, ledger in ledgers.items():
        c = d.card(now, deploys=ledger)
        k = c["dora"]["keys"]
        out[name] = {"keys": {x: k.get(x) for x in ("status", "deploys", "deploys_per_week", "change_failure_rate",
                                                     "time_to_restore_hours_median")},
                     "band": [[b["name"], b["ok"]] for b in c["dora"]["band"]], "scored": c["dora"]["scored"],
                     "verdict_and_rank_equal_to_off": c["verdict"] == off["verdict"] and c["rank"] == off["rank"]}
    return out


def case_sustainability() -> dict:
    """D7 as written (S9-NL, m1): 'held' = the NEXT window of equal length also produced a PROVEN clean
    submission; a refuted POST there does not count; a window that cannot be judged says "not evaluable",
    never False. The graded window is 09-02 with two proven submissions of two mechanisms."""
    def desk():
        return _Desk().alpha("base_a", "2026-09-02").alpha("base_b", "2026-09-02")
    late = _ts("2026-09-30", 12)
    cases = {
        "next_window_has_a_proven_submission": (desk().alpha("next_p", "2026-09-03"), late),
        "next_window_has_only_a_refuted_submission": (desk().alpha("next_r", "2026-09-03", kind="R"), late),
        "next_window_unposted_and_its_horizon_open": (desk().alpha("next_p", "2026-09-03", post=None), _ts("2026-09-06", 12)),
        "next_window_not_finished": (desk(), _ts("2026-09-03", 15)),
        "nothing_ran_in_the_next_window": (desk(), late),
    }
    out = {}
    for name, (d, now) in cases.items():
        a2 = d.card(now, since="2026-09-02", until="2026-09-03")["axes"]["axis2_throughput"]
        out[name] = {"held_in_next_window": a2["sustainability_evidence"]["held_in_next_window"],
                     "sustainable": a2["sustainable"], "next_window": a2["next_window"]}
    return out


def case_neighbour_pool() -> dict:
    """S10-NL: a VERSION card draws neighbours from that version's own rows; the weak date card pools every
    row. Version VB's later, fragile neighbours refute VA's alpha on the date card only."""
    d = _Desk().alpha("va_alpha", "2026-09-08", version="VA", neighbours=())
    for i, (sharpe, knob) in enumerate(((0.1, {"decay": 8}), (0.2, {"neutralization": "SUBINDUSTRY"}))):
        d.rows.append(dict(d.rows[0], alpha="vb_neighbour_%d" % i, sharpe=sharpe, dateCreated="2026-09-12T12:00:00-04:00",
                           settings=dict(d.rows[0]["settings"], **knob), meta={"hypothesis": "h_ok", "pipeline_version": "VB"}))
    now = _ts("2026-09-20", 12)
    return {"date_card": _per_alpha(d.card(now, since="2026-09-08"))["va_alpha"],
            "version_card_VA": _per_alpha(d.card(now, version="VA"))["va_alpha"]}


def case_exposure() -> dict:
    """A3: a version card's days are the ET days the deploy ledger says it was RUNNING -- deploy days
    excluded, a rollback restores the previous version, a failed rollback makes it unknown, a re-deploy of
    the running version is no change, a `noop` is ignored -- and a retired version's card does not decay."""
    B = _scorer()
    ledger = [_deploy("deployed", "2026-09-01", pv="A"), _deploy("deployed", "2026-09-03", pv="A"),
              _deploy("rolled_back", "2026-09-05", pv="B"), _deploy("deployed", "2026-09-08", pv="B"),
              _deploy("rollback_failed", "2026-09-12", pv="C"), _deploy("noop", "2026-09-10", pv="B")]
    now = _ts("2026-09-15", 12)
    out = {"live_days": {v: B.live_days(ledger, v, now)["days"] for v in ("A", "B", "C")},
           "known": {v: B.live_days(ledger, v, now)["known"] for v in ("A", "B", "C")},
           "no_ledger_known": B.live_days(None, "A", now)["known"]}
    d = _Desk()
    for i in range(8):
        d.alpha("v%d" % i, "2026-09-%02d" % (20 + i // 2), version="V")
    retire = [_deploy("deployed", "2026-09-19", pv="V"), _deploy("deployed", "2026-09-25", pv="W")]
    for label, at in (("graded_2026-09-26", _ts("2026-09-26", 15)), ("graded_2026-10-20", _ts("2026-10-20", 15))):
        a2 = d.card(at, version="V", deploys=retire)["axes"]["axis2_throughput"]
        out["retired_version_" + label] = {"quota_days": a2["quota_days"], "rate": a2["proven_clean_per_quota_day"]}
    return out


def _runlog(day, hour, rc, host="vps", pv="V"):
    """A row of state/forge/run_config_log.jsonl (D45; the draw-4 shared interface): {at, pipeline_version,
    run_config, host}."""
    return {"at": _ts(day, hour), "pipeline_version": pv, "run_config": rc, "host": host}


def case_run_config_exposure() -> dict:
    """D45 (Khoa, 2026-09-23 ~20:15): a (pipeline_version, run_config) cohort's live days are the pipeline_version's
    live days (the deploy ledger) on which the runner's run_config log records that run_config -- for the WHOLE
    day, on some host; a day the run_config changed on is excluded; days before the log's first row for the
    cohort read "exposure unknown", never a guess. Draw4_build scoring 2: every cohort of a version took ALL its
    live days, so one experiment round's run_config set the main cohort's rate denominator.

    V deployed 2026-09-09 10:00 (live 09-10..09-19, graded 09-20 15:00). The log: the VPS holds r1 from 09-09
    11:00, r2 from 09-14 12:00, r1 again from 09-17 12:00; the Mac logs r9 on 09-12 12:00 (a dry run elsewhere
    must not end the loop's run_config -- each host is its own timeline). So:
      V@r1   whole days 09-10..13 and 09-18..19 (6); 09-14 and 09-17 excluded (changed on them);
      V@r2   whole days 09-15..16 (2); 09-14 and 09-17 excluded; 09-10..13 come before its first row: unknown;
      V@r1 with no log read: exposure unknown (D45 takes a run_config cohort's days from the log);
      V (rows with no run_config): the pipeline_version's own 10 live days, as before D45.
    Proven alphas: r1 on 09-10, 09-13, 09-14 and 09-18 (the 09-14 one is graded by axis 1 and left out of the
    rate); r2 on 09-15; V (no run_config) on 09-11."""
    now = _ts("2026-09-20", 15)
    ledger = [_deploy("deployed", "2026-09-09", pv="V")]
    runlog = [_runlog("2026-09-09", 11, "r1"), _runlog("2026-09-12", 12, "r9", host="mac"),
              _runlog("2026-09-14", 12, "r2"), _runlog("2026-09-17", 12, "r1")]
    d = _Desk()
    for day in ("2026-09-10", "2026-09-13", "2026-09-14", "2026-09-18"):
        d.alpha("r1_" + day, day, version="V", run_config="r1")
    d.alpha("r2_2026-09-15", "2026-09-15", version="V", run_config="r2")
    d.alpha("none_2026-09-11", "2026-09-11", version="V")
    out = {}
    for label, version, log in (("V@r1", "V@r1", runlog), ("V@r2", "V@r2", runlog), ("V@r1, no log read", "V@r1", None),
                                ("V, no run_config", "V", runlog)):
        c = d.card(now, version=version, deploys=ledger, run_config_log=log)
        w, a2 = c["window"], c["axes"]["axis2_throughput"]
        out[label] = {"quota_days": w["quota_days"], "since": w["since"],
                      "exposure": {k: w["exposure"][k] for k in ("known", "unknown_days", "excluded_run_config_days",
                                                                 "rows_outside_exposure")},
                      "proven_clean_per_quota_day": a2["proven_clean_per_quota_day"], "graded": sorted(_per_alpha(c))}
    return out


#: tools/deploy.py WATCH_OUTCOMES, the `running_after` a watch row carries (read 2026-09-23; the scorer does not read
#: the field -- it is here so the rows have the contract's shape)
_WATCH_RUNNING_AFTER = {"watch_ok": "watched", "watch_timeout": "watched", "watch_not_rolled_back": "watched",
                        "watch_rolled_back": "previous", "watch_rollback_failed": "unknown",
                        "watch_units_down": "unknown", "watch_interrupted": "unknown"}


def _watch(outcome, day, pv, previous=None, hour=11):
    """A watch row of tools/deploy.py DEPLOY_LOG (WATCH ROWS): `watched` = the started_at of the push _deploy() wrote
    on `day` at 10:00; version / pipeline_version are the watched push's, previous_* what a rollback restores."""
    return {"outcome": outcome, "watched": _ts(day, 10) - 600, "pipeline_version": pv, "version": "tree-" + pv,
            "previous_pipeline_version": previous, "previous_version": ("tree-" + previous) if previous else None,
            "running_after": _WATCH_RUNNING_AFTER[outcome], "started_at": _ts(day, 10) + 300,
            "finished_at": _ts(day, hour), "commit_time": None, "git_dirty": False}


def case_watch_rows() -> dict:
    """tools/deploy.py DEPLOY_LOG, WATCH ROWS (D16's first-round half as D43 narrows it): a WATCH ROW IS NEVER A
    DEPLOY. Draw4_build scoring 1 (SERIOUS): one watch_ok row an hour after V's deploy took V from 10 live days to
    0, and dora() read 4 deploys and CFR 0.25 on [deploy, deploy, watch_ok, watch interrupted]. The reading pinned:
    watch_ok / watch_timeout / watch_not_rolled_back leave the running version as it was; watch_rolled_back puts
    previous_pipeline_version back and makes the push it names a change failure; any other watch outcome makes the
    running version unknown; watch_not_rolled_back is a change failure too (WATCH_ROUND_FAILED), and
    watch_interrupted is not. Graded 2026-09-22 15:00 on the ledger
      V pushed 09-09 + watch_ok;             W pushed 09-12 + watch_rolled_back (to V);
      X pushed 09-15 + watch_not_rolled_back; Y pushed 09-18 + watch_interrupted.
    Live days: V 09-10, 11, 13, 14; W none; X 09-16, 17; Y none (unknown after the interrupted watch). DORA: 4
    deploys, CFR 0.5 (W and X), 71 h to restore each."""
    ledger = [_deploy("deployed", "2026-09-09", pv="V"), _watch("watch_ok", "2026-09-09", "V"),
              _deploy("deployed", "2026-09-12", pv="W"), _watch("watch_rolled_back", "2026-09-12", "W", previous="V"),
              _deploy("deployed", "2026-09-15", pv="X"), _watch("watch_not_rolled_back", "2026-09-15", "X", previous="V"),
              _deploy("deployed", "2026-09-18", pv="Y"), _watch("watch_interrupted", "2026-09-18", "Y", previous="X")]
    B, now = _scorer(), _ts("2026-09-22", 15)
    k = B.dora(ledger, now=now)
    return {"live_days": {v: B.live_days(ledger, v, now)["days"] for v in ("V", "W", "X", "Y")},
            "dora": {x: k.get(x) for x in ("status", "deploys", "deploys_per_week", "change_failure_rate",
                                           "time_to_restore_hours_median")}}


def _round_rows(pv, rounds, run_config="rc"):
    """Scored rows of one pipeline_version for D47 / D54 / D60, round by round. `rounds` = [(day, arm, arm_by, round,
    [(gen_route, region, n scored, k clearing every binding check)])]. Each row is stamped as forge/runner.py stamps a
    construction (the shared interface): meta.arm; meta.arm_by -- "randomiser" for a round `--mode randomised`
    assigned, "explicit" for an explicit --mode, None to leave it out as rows planned before D54 do; meta.round, the
    round's seed (None leaves it out); meta.seed; and meta.gen_route (None leaves it out, as the incumbent's rows
    carry none). ONE run_config for every row: the runner leaves --seed out of run_config, so a randomised loop is
    one D30 cohort (the draw-6 pipeline and scoring reports, read from forge/runner.py)."""
    rows = []
    for day, arm, arm_by, rnd, parts in rounds:
        for route, region, n, k in parts:
            for i in range(n):
                meta = {"pipeline_version": pv, "run_config": run_config, "arm": arm, "seed": rnd}
                for key, v in (("arm_by", arm_by), ("round", rnd), ("gen_route", route)):
                    if v is not None:
                        meta[key] = v
                rows.append({"alpha": "%s_%s_%s_%s_%s_%s_%03d" % (pv, day, rnd, arm, route, region, i), "status": "COMPLETE",
                             "checks": PASS if i < k else [dict(PASS[0], result="FAIL")] + PASS[1:],
                             "dateCreated": "%sT12:00:00-04:00" % day, "formula": "rank(%s_%s_%s_%d)" % (rnd, route, region, i),
                             "settings": {"region": region, "delay": 1}, "meta": meta})
    return rows


def _arms_day(i) -> str:
    """The i-th ET day of the arms cases: 2026-08-01 onward, so 30 whole days end before the 09-20 grading."""
    return (datetime.date(2026, 8, 1) + datetime.timedelta(days=i)).isoformat()


#: a day's two randomiser rounds, 10 scored alphas each in USA/d1: (k of A, k of B) by the day's sign
_SIGN = {1: (1, 3), -1: (3, 1), 0: (1, 1)}


def _pairs(signs, first=0, n=10, a_parts=(), b_parts=()):
    """One randomiser round per arm on each day: +1 = B clears 3 of n and A 1, -1 = the reverse, 0 = 1 each. A round
    is named by its seed, 2 x the day's index (A) and that + 1 (B). `a_parts` / `b_parts` add parts to every A / B
    round (a neighbour row, a second cell)."""
    out = []
    for j, s in enumerate(signs):
        a, b = _SIGN[s]
        out += [(_arms_day(first + j), "composites", "randomiser", 2 * (first + j), [(None, "USA", n, a)] + list(a_parts)),
                (_arms_day(first + j), "gen", "randomiser", 2 * (first + j) + 1, [("fresh", "USA", n, b)] + list(b_parts))]
    return out


def _arms_outcome(r) -> dict:
    """What compare_arms() DECIDED: the verdict; each arm's [k, n, rounds]; every look taken as [look, shared days,
    its last day, p, crossed, direction]; the last look's direction per cell; the rows and rounds EXCLUDED and why
    (D60), the rows reported BESIDE the estimand (D54) and the unscored rows per arm; the round-clustering ratio.
    Read with .get: a key the scorer does not return reads None, so a change of shape shows in the diff instead of
    as a crash of the whole truth table."""
    ex = r.get("excluded") or {}
    rc = r.get("round_clustering")
    return {"verdict": r["verdict"],
            "arms": {a: [e.get("clearing_every_binding_check"), e.get("scored_alphas"), e.get("rounds")]
                     for a, e in (r.get("arms") or {}).items()},
            "looks": [[L.get("look"), L.get("shared_days"), L.get("last_day"), L.get("p_value"), L.get("crossed"),
                       L.get("direction")] for L in r.get("looks") or []],
            "cells": {c: v.get("direction") for c, v in (r.get("cells") or {}).items()},
            "excluded": {"rounds": ex.get("rounds"), "rows": ex.get("rows"),
                         "by_reason": {w: [e.get("rounds"), e.get("rows")] for w, e in (ex.get("by_reason") or {}).items()}},
            "beside": {k: [v.get("rounds"), v.get("scored_rows"), v.get("clearing_every_binding_check")]
                       for k, v in (r.get("beside") or {}).items()},
            "unscored": {a: e.get("unscored_rows") for a, e in (r.get("arms") or {}).items()},
            "round_clustering_ratio": rc.get("ratio") if isinstance(rc, dict) else rc}


def case_compare_arms() -> dict:
    """D47 (Khoa, 2026-09-23 ~21:00, superseding D33) as D54, D55 and D60 (Khoa, 2026-09-24 ~02:20) decide it: rounds
    are randomised within each ET day between the incumbent (meta.arm "composites", A) and the branch ("gen", B), and
    compare_arms() reads it with the ROUND as the unit -- a permutation of arm labels across the rounds of each ET day
    (D54) -- at looks on the 7th, 14th, 21st and 28th shared day with O'Brien-Fleming boundaries, stopping at the first
    crossing whose cells all agree (D55); only rounds the randomiser assigned are compared, and the others are counted
    (D54, D60); in B only fresh generator draws are in the estimand, neighbour and repair rows beside it (D54).
    Round 4 F1: with the ALPHA as the unit, the desk's own rounds relabelled read better / worse 0.155 of the time.

    Rows are stamped as the runner stamps them (_round_rows). Unless said, a day has one randomiser round per arm, 10
    scored alphas each in USA/d1, and its sign (_SIGN) says which clears 3 and which 1. Graded 09-20; the days start
    08-01. Each p is the scorer's sequential Monte Carlo p (fixed seed); "exact" below is the relabelling law:
      placebo_day_heterogeneous  14 shared days; on the even days the rate is about 10 % for BOTH arms but B scored 5x
                                 as many (A 20 with 2, B 100 with 11); on the odd days the rate is 0 and A scored 5x.
                                 Within each day the arms agree (exact p 2/128 at both looks): WITHHELD after look 2.
                                 A test that pools the days reads B far above A (the day-conditioning pin);
      within_day_effect          21 days, B higher on 13 of the first 14 and on 3 of the next 7: exact p 0.0018 at
                                 look 2, INSIDE its nominal 0.0042: BETTER at look 2, and the read-out stops (look 3's
                                 day exists and is not read);
      look_outside_the_boundary  14 days, B higher on 12: exact p 0.013 at look 2, OUTSIDE its nominal 0.0042 though
                                 under 0.05: WITHHELD (the next look is at 21);
      cells_disagree             14 days in USA and EUR; B higher in USA and lower in EUR on 13 days, the reverse on the
                                 14th: p crosses at look 2, but the cells point opposite ways: WITHHELD;
      six_shared_days            6 days, every day B higher: WITHHELD, no look taken (the first is at 7);
      seven_shared_days          7 days, the same: look 1 taken (exact p 2/128 against 5.2e-05): WITHHELD;
      no_effect_30_shared_days   30 days alternating: four looks, none crossing: INDISTINGUISHABLE; days 29-30 are
                                 after the last look and not read;
      shared_days_not_calendar_days  14 shared days (B higher on all but the 4th) and 4 days on which only A ran two
                                 randomiser rounds: looks count SHARED days, so look 2 reads all 14: BETTER. Counting
                                 calendar days instead, look 2 would read 11 shared days (exact p 0.012): withheld --
                                 THIS MODULE'S READING of "every 7 days", open for Khoa (benchmark ARMS_LOOK_DAYS);
      older_ab_arms_only         rows of the older --ab arms ("current" / "new", no arm_by, no round) and randomiser
                                 rows of ANOTHER pipeline_version: nothing to compare, NO-DATA, the W rows EXCLUDED
                                 and counted;
      explicit_rounds_excluded   14 days with no effect (A and B each 1 of 10) plus, each day, 3 rounds of an explicit
                                 --mode composites (search recipes: arm_by "explicit", 0 of 10): WITHHELD; the 42
                                 explicit rounds EXCLUDED and counted, with a round whose rows carry two arms, a
                                 randomiser row with no meta.round, and one round whose rows fall under two reasons
                                 (counted once in the total). Admitted, the 0-hit rounds would make B read better;
      neighbour_and_repair_rows_beside  14 days with no effect in the fresh draws; every B round also carries 4
                                 neighbour rows clearing 4 and 4 repair rows clearing 3, and one B round 2 rows with no
                                 gen_route: WITHHELD, those rows BESIDE; counted in B, they would read better;
      events_cluster_in_rounds   14 days, 4 alphas a round; B higher on 11 days (B 3 of 4, A 0) and lower on 3: per
                                 ROUND the exact p is 0.057, WITHHELD after look 2. With the ALPHA as the unit the
                                 same rows read better at look 2 (round 4 F1's excess, in one case)."""
    B = _scorer()
    now = _ts("2026-09-20", 15)
    H, L, E = 1, -1, 0
    placebo = []
    for j in range(14):
        (na, ka), (nb, kb) = ((20, 2), (100, 11)) if j % 2 == 0 else ((100, 0), (20, 0))
        placebo += [(_arms_day(j), "composites", "randomiser", 2 * j, [(None, "USA", na, ka)]),
                    (_arms_day(j), "gen", "randomiser", 2 * j + 1, [("fresh", "USA", nb, kb)])]
    disagree = []
    for j in range(14):
        (ua, ea), (ub, eb) = ((0, 1), (3, 0)) if j < 13 else ((3, 0), (0, 1))
        disagree += [(_arms_day(j), "composites", "randomiser", 2 * j, [(None, "USA", 10, ua), (None, "EUR", 10, ea)]),
                     (_arms_day(j), "gen", "randomiser", 2 * j + 1, [("fresh", "USA", 10, ub), ("fresh", "EUR", 10, eb)])]
    calendar, shared_signs, j = [], [H, H, H, L] + [H] * 10, 0
    for i in range(18):
        if i in (3, 7, 11, 15):                          # a day on which the coin gave both rounds to A
            calendar += [(_arms_day(i), "composites", "randomiser", 100 + 2 * i, [(None, "USA", 10, 1)]),
                         (_arms_day(i), "composites", "randomiser", 101 + 2 * i, [(None, "USA", 10, 1)])]
        else:
            calendar += [(d, arm, by, 200 + rnd, parts) for d, arm, by, rnd, parts in _pairs([shared_signs[j]], first=i)]
            j += 1
    older = [dict(r, meta={k: v for k, v in dict(r["meta"], arm={"composites": "current", "gen": "new"}[r["meta"]["arm"]]).items()
                           if k not in ("arm_by", "round")})
             for r in _round_rows("W", _pairs([H] * 14))] + _round_rows("W2", _pairs([H] * 14))
    explicit = _pairs([E] * 14) + [(_arms_day(j), "composites", "explicit", 1000 + 3 * j + x, [(None, "USA", 10, 0)])
                                   for j in range(14) for x in range(3)]
    explicit += [(_arms_day(0), "composites", "randomiser", 2000, [(None, "USA", 5, 1)]),   # one round, two arms
                 (_arms_day(0), "gen", "randomiser", 2000, [("fresh", "USA", 5, 1)]),
                 (_arms_day(1), "gen", "randomiser", None, [("fresh", "USA", 3, 3)]),       # no meta.round
                 (_arms_day(2), "composites", "explicit", 2001, [(None, "USA", 3, 0)]),     # one round, two reasons
                 (_arms_day(2), "current", "randomiser", 2001, [(None, "USA", 3, 0)])]
    beside = _pairs([E] * 14, b_parts=[("neighbour", "USA", 4, 4), ("repair", "USA", 4, 3)])
    beside += [(_arms_day(0), "gen", "randomiser", 1, [(None, "USA", 2, 2)])]
    cluster = []
    for j, s in enumerate([H, H, L, H, H, L, H, H, H, H, H, L, H, H]):
        a, b = (0, 3) if s == H else (3, 0)
        cluster += [(_arms_day(j), "composites", "randomiser", 2 * j, [(None, "USA", 4, a)]),
                    (_arms_day(j), "gen", "randomiser", 2 * j + 1, [("fresh", "USA", 4, b)])]
    specs = {"placebo_day_heterogeneous": placebo,
             "within_day_effect": _pairs([H] * 13 + [L] + [H, L, H, L, H, L, L]),
             "look_outside_the_boundary": _pairs([H] * 12 + [L, L]),
             "cells_disagree": disagree,
             "six_shared_days": _pairs([H] * 6), "seven_shared_days": _pairs([H] * 7),
             "no_effect_30_shared_days": _pairs([H, L] * 15),
             "shared_days_not_calendar_days": calendar,
             "explicit_rounds_excluded": explicit,
             "neighbour_and_repair_rows_beside": beside,
             "events_cluster_in_rounds": cluster}
    out = {label: _arms_outcome(B.compare_arms(_round_rows("W", spec), "W", now=now)) for label, spec in specs.items()}
    out["older_ab_arms_only"] = _arms_outcome(B.compare_arms(older, "W", now=now))
    return out


# ------------------------------------------------------------------ round 3 S7: the scorer's input layer
def _jsonl(path, rows, extra_lines=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows) + "".join(extra_lines))


@contextlib.contextmanager
def _readers_at(tmp):
    """Point every reader build() calls at the miniature state under `tmp`, and put each back afterwards.

    Only WHERE they read changes: each stand-in calls the scorer's own reader -- looked up when the case runs, so
    a mutant tools/tests/test_ci_gate.py swapped in is the one that runs -- with the miniature path, since
    load_standard, load_deploys, posted_history, load_scored and load_corr take their paths as defaults bound at
    import. MEANING_LEDGER and RUN_CONFIG_LOG are read at call time and are set. axis3_gearing is replaced by a
    fixed value: it measures the TREE, not the inputs (case_axis3_tree pins it). THE LIMIT THAT FOLLOWS: an edit
    to a reader's DEFAULT PATH moves no case -- the file's hash in scorer_closure still moves."""
    B = _scorer()
    import importlib
    P = getattr(importlib.import_module("forge"), "probe", None) or importlib.import_module("forge.probe")
    st = tmp / "state"
    real = {"ph": B.SUB.posted_history, "ls": B.HV.load_scored, "lc": P.load_corr, "ld": B.load_deploys,
            "lstd": B.load_standard}
    patches = [(B.SUB, "posted_history", lambda *a, **k: real["ph"](paths=(st / "forge/submitted.jsonl",
                                                                            st / "climb/submitted.jsonl"))),
               (B.HV, "load_scored", lambda *a, **k: real["ls"](st / "forge/scored.jsonl")),
               (P, "load_corr", lambda *a, **k: real["lc"](st / "forge/corr.jsonl")),
               (B, "load_deploys", lambda *a, **k: real["ld"](tmp)),
               (B, "load_standard", lambda *a, **k: real["lstd"](tmp)),
               (B, "MEANING_LEDGER", st / "forge/meaning.jsonl"),
               (B, "RUN_CONFIG_LOG", st / "forge/run_config_log.jsonl"),
               (B, "axis3_gearing", lambda *a, **k: dict(AXIS3_MET))]
    saved = [(obj, name, getattr(obj, name)) for obj, name, _ in patches]
    try:
        for obj, name, value in patches:
            setattr(obj, name, value)
        yield B
    finally:
        for obj, name, value in reversed(saved):
            setattr(obj, name, value)


def _miniature_state(tmp):
    """The files build() reads, written under `tmp` in the formats the desk writes them (read 2026-09-23 from
    state/forge/submitted.jsonl, scored.jsonl, corr.jsonl, state/pnl_curves and the shared interfaces of the
    draw-4 fix builders). One cohort V@rc1 (plus one V@rc2 alpha); V deployed 2026-09-09 10:00; rc1 logged 11:00."""
    st = tmp / "state"
    settings = {"region": "USA", "delay": 1, "universe": "TOP3000", "decay": 4, "neutralization": "INDUSTRY",
                "truncation": 0.08}
    fitness_fails = [dict(c, result="FAIL") if c["name"] == "LOW_FITNESS" else c for c in PASS]

    def row(alpha, day, hour=12, status="COMPLETE", checks=PASS, hyp=None, rc="rc1", sharpe=1.8, knob=None, formula=None):
        return {"alpha": alpha, "status": status, "checks": checks, "sharpe": sharpe,
                "formula": formula or "rank(%s)" % alpha, "settings": dict(settings, **(knob or {})),
                "dateCreated": datetime.datetime.fromtimestamp(_ts(day, hour), ET).isoformat(),
                "meta": {"pipeline_version": "V", "run_config": rc, "hypothesis": hyp or "gen:fam_" + alpha,
                         "mechanism_key": "m_" + alpha, "planner_note": "not read by the scorer"},
                "raw": {"a field read_journal drops": list(range(20))}}

    def neighbours(alpha, day):
        return [row("%s_n%d" % (alpha, i + 1), day, sharpe=sh, knob=kb, formula="rank(%s)" % alpha, hyp="gen:fam_" + alpha)
                for i, (sh, kb) in enumerate(((1.7, {"decay": 8}), (1.6, {"neutralization": "SUBINDUSTRY"})))]
    journal = [
        # repeated rows: the journal's LAST row of an alpha is the one graded (read_journal)
        row("in_proven", "2026-09-14", status="ERROR", checks=[]), row("in_proven", "2026-09-14"),
        *neighbours("in_proven", "2026-09-14"),
        row("in_last_row_fails", "2026-09-13"), row("in_last_row_fails", "2026-09-13", checks=fitness_fails),
        *neighbours("in_last_row_fails", "2026-09-13"),
        row("in_old_post", "2026-09-10"), *neighbours("in_old_post", "2026-09-10"),
        row("in_climb_post", "2026-09-12", hyp="h_lib"), *neighbours("in_climb_post", "2026-09-12"),
        row("in_rejected", "2026-09-12"),
        row("in_created_on_the_cut_day", "2026-09-18", hour=9), *neighbours("in_created_on_the_cut_day", "2026-09-18"),
        row("in_other_cohort", "2026-09-14", rc="rc2"),
    ]
    _jsonl(st / "layered/runs/forge.jsonl", journal, extra_lines=("{not json\n", "[1, 2]\n"))
    os.utime(st / "layered/runs/forge.jsonl", (_ts("2026-09-18", 16), _ts("2026-09-18", 16)))   # data_through
    posts = [{"alpha": a, "http": http, "posted_at": _ts(day, hour), "mechanism_key": "m_" + a, "formula": "rank(%s)" % a}
             for a, day, hour, http in (("in_proven", "2026-09-14", 18, 201), ("in_last_row_fails", "2026-09-13", 18, 201),
                                        ("in_old_post", "2026-09-10", 13, 201), ("in_rejected", "2026-09-12", 18, 403),
                                        ("in_created_on_the_cut_day", "2026-09-18", 10, 201),
                                        ("in_other_cohort", "2026-09-14", 18, 201))]
    posts.append({"kind": "adjudication", "alpha": "in_proven", "at": _ts("2026-09-14", 19), "status": "ACTIVE"})
    _jsonl(st / "forge/submitted.jsonl", posts)
    _jsonl(st / "climb/submitted.jsonl", [{"alpha": "in_climb_post", "http": 200, "posted_at": _ts("2026-09-12", 18)}])
    posted = ("in_proven", "in_last_row_fails", "in_old_post", "in_climb_post", "in_created_on_the_cut_day",
              "in_other_cohort", "in_rejected")
    _jsonl(st / "forge/scored.jsonl", [{"alpha": "in_proven", "dsr": 0.5, "pbo_pass": False}]
           + [{"alpha": a, "dsr": 0.97, "pbo_pass": True} for a in posted])            # the last row of an alpha wins
    _jsonl(st / "forge/corr.jsonl", [{"alpha": a, "read_at": _ts("2026-09-15", 9), "prod": 0.5, "self": 0.4} for a in posted]
           + [{"alpha": "in_proven", "read_at": _ts("2026-09-15", 10), "prod": "200-empty (computing)",
               "self": "200-empty (computing)"}])                                      # a value once read is kept
    for a in posted:
        if a != "in_old_post":                                                         # its regime reads unmeasured
            (st / "pnl_curves").mkdir(parents=True, exist_ok=True)
            (st / "pnl_curves" / ("%s.json" % a)).write_text(json.dumps(_curve(STEADY)))
    decidable = {"G1": None, "G2": None, "G3": None, "G4": True, "G5": True, "G6": True, "G7": True, "G8": True}
    _jsonl(st / "forge/meaning.jsonl", [{"alpha": a, "formula_sha": _formula_sha("rank(%s)" % a), "gates": decidable,
                                         "inherited_from": None, "route": "generated", "scorer": "fixture",
                                         "scored_at": _ts("2026-09-18", 20)}
                                        for a in posted if a != "in_climb_post"])
    _jsonl(st / "forge/run_config_log.jsonl", [_runlog("2026-09-09", 11, "rc1"), _runlog("2026-09-14", 11, "rc2", host="mac")])
    _jsonl(st / "deploys.jsonl", [_deploy("deployed", "2026-09-09", pv="V")])
    for d in ("forge/hypotheses", "forge/composites"):
        (tmp / d).mkdir(parents=True, exist_ok=True)                                  # an EMPTY library: see the case


def case_input_layer() -> dict:
    """Round 3 S7: the truth table never entered the scorer's INPUT layer -- the fixture fed build_from() directly,
    so an edit to load_inputs, read_journal or a reader it calls moved no case (the gamer's edit, load_inputs
    keeping the last 7 days of POSTs, took the real Mac card's level 1 from 4 to 1 and moved nothing). This case
    runs benchmark.build(), and so load_inputs and every reader, on a miniature state/ written to a temporary
    directory (_miniature_state; the readers pointed at it by _readers_at). Graded 2026-09-19 15:00 as the version
    card V@rc1, the journal copy cut 2026-09-18 16:00 (its mtime):
      in_proven                  two journal rows (ERROR, then COMPLETE): the last is graded; two scored rows (DSR 0.5,
                                 then 0.97) and two corr rows (numbers, then "200-empty (computing)"): the last score
                                 and the numbers are kept; a meaning row of its own formula; an adjudication row in
                                 the POST log that is not a POST. PROVEN;
      in_last_row_fails          its last journal row fails LOW_FITNESS: REFUTED;
      in_old_post                POSTed 7 days and 21 hours before the newest POST, no PnL curve: UNPROVEN;
      in_climb_post              POSTed only in state/climb/submitted.jsonl; a library hypothesis (h_lib) and an
                                 EMPTY library, so its standard gate reads unmeasured: UNPROVEN;
      in_rejected                a 403: not a submission, not graded;
      in_created_on_the_cut_day  created on 09-18, the day the copy was cut: excluded like the unfinished day;
      in_other_cohort            rc2: not graded on V@rc1's card.
    Plus a line that is not JSON and one that is not an object (skipped). The rate: rc1 held 09-10..09-17 whole
    (the run_config log; a Mac row for rc2 does not end it), 8 days, 1 proven clean.

    WHAT IT DOES NOT PIN: load_standard runs, but on an empty library, so how it reads real composites is not
    pinned here (the live library is not the scorer's and would move the golden on every edit); a reader's
    default path (_readers_at); the host name."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="wq-fixture-inputs-"))
    try:
        _miniature_state(tmp)
        with _readers_at(tmp) as B:
            try:
                c = B.build(journal=tmp / "state/layered/runs/forge.jsonl", version="V@rc1",
                            curves_dir=tmp / "state/pnl_curves", run_drill=False, now=_ts("2026-09-19", 15))
            except ValueError as exc:
                return {"refused": "ValueError: " + str(exc).replace(str(tmp), "<miniature>")}
        out = _outcome(c)
        out.update({"per_alpha": _per_alpha(c),
                    "posted_beyond_the_horizon": c["axes"]["axis1_product"]["posted_beyond_the_horizon"],
                    "exposure": {k: c["window"]["exposure"][k] for k in ("known", "unknown_days", "excluded_run_config_days")},
                    "data_through_et": c["window"]["data_through_et"],
                    "excluded_uncovered_day": c["window"]["excluded_uncovered_day"],
                    "inputs": c["provenance"]["inputs"],
                    "gaps": [g.replace(str(tmp), "<miniature>") for g in c["gaps"]]})
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


#: a runner whose REAL parser offers an --ab arm and hands it to plan(ab=...), which is what axis 3's A/B
#: check reads (benchmark._ab_arm_is_real); it is only ever imported, and main() stops inside parsing
_RUNNER = '''import argparse


def plan(ab=None):
    return ab


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--plan")
    ap.add_argument("--ab", choices=["old", "new"], default="old")
    a = ap.parse_args(argv)
    return plan(ab=a.ab)
'''


def _tree(root, kind):
    f = root / "forge"
    for sub in ("hypotheses", "composites", "tests"):
        (f / sub).mkdir(parents=True)
    if kind in ("healthy", "four_of_five_modules_tested"):
        # one REAL leg, copied: a hand-written one would break on a schema change that is not the scorer's
        leg = sorted((ROOT / "forge/hypotheses").glob("*.yaml"))[0]
        shutil.copy(leg, f / "hypotheses" / leg.name)
        (f / "composites" / "c.yaml").write_text("")
        (f / "runner.py").write_text(_RUNNER)
        (f / "a.py").write_text("X = 1\n")
        (f / "tests" / "test_runner.py").write_text("from forge import runner\n\ndef test_r():\n    assert runner\n")
        (f / "tests" / "test_a.py").write_text("from forge import a\n\ndef test_a():\n    assert a.X\n")
        (root / "tools").mkdir()
        (root / "tools" / "deploy.py").write_text("")
        if kind == "four_of_five_modules_tested":
            # runner, a, b, c tested and d not: coverage 4/5 = 0.8 exactly
            for m in ("b", "c"):
                (f / ("%s.py" % m)).write_text("X = 1\n")
                (f / "tests" / ("test_%s.py" % m)).write_text("from forge import %s\n\ndef test_%s():\n    assert %s.X\n" % (m, m, m))
            (f / "d.py").write_text("X = 1\n")
        return
    (f / "a.py").write_text("from forge import b\n")
    (f / "b.py").write_text("from forge import a\n")
    (f / "c.py").write_text("def f():\n    from forge import d\n")
    (f / "d.py").write_text("def g():\n    from forge import c\n")
    (f / "tests" / "test_a.py").write_text("from forge import a\n\ndef test_a():\n    assert a\n")
    (f / "tests" / "test_b.py").write_text("")                          # an empty test file covers nothing


def case_axis3_tree() -> dict:
    """D8 / S4-NL: axis 3's fitness functions on two small synthetic trees, so every predicate is reached
    both ways. HEALTHY: a YAML library, a runner with a real --ab arm, a deploy.py, no import cycle, every
    module tested -- 7 of 7, the floor (1.0) met. BROKEN: no library, no runner, no deploy.py, one
    MODULE-LEVEL import cycle (a wall) and one DEFERRED cycle (a smell), one module of four with a real
    test -- the floor unmet. FOUR_OF_FIVE_MODULES_TESTED: healthy plus three modules, one untested, so the
    coverage is 0.8 -- the draw-2 bound. Draw-3 ci SERIOUS 4: with coverage only at 1.0 and 0.25, the bound
    moved 0.8 -> 0.5 changed nothing; at 0.8 every bound at or below 0.8 moves the check. The drill is
    passed in (it needs the desk's data)."""
    B = _scorer()
    out = {}
    for name in ("healthy", "broken", "four_of_five_modules_tested"):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="wq-fixture-axis3-"))
        try:
            _tree(tmp, name)
            g = B.axis3_gearing(drill={"status": "fixture", "ok": True, "note": "not run"}, root=tmp, run_drill=False)
            cyc = B.import_cycles(tmp / "forge")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        out[name] = {"checks": [[x["name"], x["ok"]] for x in g["fitness_functions"]], "held": g["held"],
                     "of": g["of"], "value": g["value"], "floor_met": g["floor_met"], "import_cycles": cyc}
    return out


CASES = (case_axis1_gates, case_regime, case_window, case_post_horizon, case_floors, case_rank, case_compare,
         case_dora, case_sustainability, case_neighbour_pool, case_exposure, case_axis3_tree,
         # the decisions ticked 2026-09-23 (D26 is case_rank's, D49 case_post_horizon's)
         case_rank_open_horizon, case_verdict_leads_rank, case_compare_within_cell, case_cohorts, case_generated_alpha,
         case_run_config_exposure, case_compare_arms,
         # draw4_build scoring 1 (tools/deploy.py WATCH ROWS) and round 3 S7 (the input layer)
         case_watch_rows, case_input_layer,
         # the decisions ticked 2026-09-24 (D54, D55 and D60 are case_compare_arms', D56 case_generated_alpha's)
         case_rank_equal_exposure)


def sha256(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- the scorer's identity
SCORER = "forge/offline/benchmark.py"


def _module_files(dotted: str, roots) -> list:
    """The repository files importing `dotted` could execute, one per import root that has it (Python runs
    the first on sys.path; every match is kept, since the order depends on which module ran first). []
    for a standard-library or installed module, or a directory with no __init__.py (a namespace package
    runs no code of its own)."""
    parts = dotted.split(".")
    out = []
    for r in roots:
        base = r.joinpath(*parts)
        out += [f for f in (base.with_suffix(".py"), base / "__init__.py") if f.is_file()]
    return out


def _path_values(e, env, here, root, depth=0) -> set:
    """The paths a path EXPRESSION can take, evaluated without running it, over the grammar the pipeline's
    sys.path lines use: __file__, pathlib.Path(..), str(..), os.fspath(..), .resolve(), .absolute(),
    .parent, .parents[N], os.path.dirname/abspath/realpath(..), X / "const", `a or b` (each operand that can
    be evaluated: forge/runner.py pipeline_version()'s `Path(root or ROOT)` is ROOT when called with no root),
    and a name bound to one of these in `env` -- the scope the caller passes, which _sys_path_entries builds
    from the statement's own function and the module (a for-loop variable takes each element of its tuple;
    draw3_fix ci 8: this said "bound anywhere in the file", which the per-function scoping contradicts).
    Anything else: set()."""
    if depth > 12:
        return set()
    ev = lambda x: _path_values(x, env, here, root, depth + 1)            # noqa: E731
    if isinstance(e, ast.BoolOp) and isinstance(e.op, ast.Or):
        return set().union(*[ev(v) for v in e.values])
    if isinstance(e, ast.Name):
        return {here} if e.id == "__file__" else set().union(*[ev(v) for v in env.get(e.id, [])]) if env.get(e.id) else set()
    if isinstance(e, ast.Constant) and isinstance(e.value, str):
        return {pathlib.Path(e.value) if e.value.startswith("/") else root / e.value}
    if isinstance(e, ast.Attribute) and e.attr == "parent":
        return {p.parent for p in ev(e.value)}
    if isinstance(e, ast.Subscript) and isinstance(e.value, ast.Attribute) and e.value.attr == "parents" \
            and isinstance(e.slice, ast.Constant) and isinstance(e.slice.value, int):
        return {p.parents[e.slice.value] for p in ev(e.value.value) if e.slice.value < len(p.parents)}
    if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Div) and isinstance(e.right, ast.Constant) \
            and isinstance(e.right.value, str):
        return {p / e.right.value for p in ev(e.left)}
    if isinstance(e, ast.Call):
        f = e.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if name in ("resolve", "absolute") and isinstance(f, ast.Attribute) and not e.args:
            return ev(f.value)
        if name in ("Path", "PurePath", "str", "fspath", "abspath", "realpath", "normpath") and len(e.args) == 1:
            return ev(e.args[0])
        if name == "dirname" and len(e.args) == 1:
            return {p.parent for p in ev(e.args[0])}
    return set()


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _own_nodes(scope):
    """The nodes of one scope, not descending into a nested function or class (they have their own)."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, _SCOPES):
            stack.extend(ast.iter_child_nodes(n))


def _bindings(scope) -> dict:
    """{name: [value expressions]} assigned in this scope; a for-loop variable is bound to each element.
    Draw4_build ci 6: an annotated assignment (`S: str = "tools/x.sh"`) bound nothing, so tools/ci_gate.py's
    no-live scan did not follow the name; it binds like a plain one."""
    env = {}
    for n in _own_nodes(scope):
        if isinstance(n, ast.AnnAssign) and n.value is not None and isinstance(n.target, ast.Name):
            env.setdefault(n.target.id, []).append(n.value)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    env.setdefault(t.id, []).append(n.value)
        elif isinstance(n, ast.For) and isinstance(n.target, ast.Name):
            env.setdefault(n.target.id, []).extend(n.iter.elts if isinstance(n.iter, (ast.Tuple, ast.List)) else [n.iter])
    return env


#: list methods of sys.path that add no directory; any OTHER method called on sys.path is listed unread
_SYS_PATH_READS = frozenset(("remove", "pop", "index", "count", "copy", "clear", "sort", "reverse"))


def _sys_names(tree) -> tuple:
    """({names bound to the sys module}, {names bound to sys.path itself}): `import sys [as S]` and `from sys
    import path [as P]`, anywhere in the file (draw3_fix ci 7), and -- draw4_build ci 6 -- a name ASSIGNED one
    of those (`S = sys`, `P = sys.path`, `Q = P`), followed until nothing new is bound: `P = sys.path;
    P.insert(0, "harness")` put harness/ on the path and was neither read nor listed unread. Draw-5 ci 7: so did
    `getattr(sys, "path").insert(...)` (ok=True, nothing unread); `getattr(<sys>, "path")` now reads as sys.path
    (_is_sys_path_expr). NOT read: the sys module or its path reached by any other expression
    (`importlib.import_module("sys")`, `getattr(sys, name)` with a name that is not the constant "path")."""
    mods, paths = set(), set()
    assigns = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.asname or a.name for a in n.names if a.name == "sys"}
        elif isinstance(n, ast.ImportFrom) and n.module == "sys" and not n.level:
            paths |= {a.asname or a.name for a in n.names if a.name == "path"}
        elif isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None:
            assigns += [(t.id, n.value) for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
                        if isinstance(t, ast.Name)]
    while True:
        new_mods = {t for t, v in assigns if isinstance(v, ast.Name) and v.id in mods} - mods
        new_paths = {t for t, v in assigns if (isinstance(v, ast.Name) and v.id in paths)
                     or _is_sys_path_expr(v, mods, set())} - paths
        if not new_mods and not new_paths:
            return mods, paths
        mods |= new_mods
        paths |= new_paths


def _is_sys_path_expr(x, mods, aliases) -> bool:
    """`<sys>.path`, `getattr(<sys>, "path")` (draw-5 ci 7), or a name bound to sys.path, for the sys module's names
    `mods` and sys.path's names `aliases` (_sys_names)."""
    if isinstance(x, ast.Attribute) and x.attr == "path" and isinstance(x.value, ast.Name) and x.value.id in mods:
        return True
    if isinstance(x, ast.Call) and getattr(x.func, "id", None) == "getattr" and len(x.args) >= 2 \
            and isinstance(x.args[0], ast.Name) and x.args[0].id in mods \
            and isinstance(x.args[1], ast.Constant) and x.args[1].value == "path":
        return True
    return isinstance(x, ast.Name) and x.id in aliases


def _added_parts(e, is_sys_path) -> list:
    """The expressions a whole-list write to sys.path adds: each element of every list or tuple concatenated
    in `e`, sys.path itself -- or, as _sys_path_entries passes the predicate, a saved copy of it -- skipped
    (`[a] + sys.path`, `sys.path[:] = saved`); any other operand whole, to be evaluated or listed unread."""
    if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
        return _added_parts(e.left, is_sys_path) + _added_parts(e.right, is_sys_path)
    if is_sys_path(e):
        return []
    return list(e.elts) if isinstance(e, (ast.List, ast.Tuple)) else [e]


def _sys_path_entries(path: pathlib.Path, root: pathlib.Path) -> tuple:
    """({directories this file puts on sys.path}, [file:line of each entry that could not be evaluated]).
    Reads, in every scope of the file: sys.path.insert / .append / .extend, `sys.path[...] = [...]`,
    `sys.path = [...] + sys.path`, `sys.path += [...]`, and each of them through `from sys import path [as
    P]` or `import sys as S`. Draw3_fix ci 7: the last three forms and the alias each left a module out of the
    closure with nothing unread, and `self.path.append(...)` came out as a bogus unread entry -- the object
    must now be the sys module by name. A method of sys.path that is neither one that adds a directory nor
    one of _SYS_PATH_READS is listed unread (it may add one).

    A name is looked up in the statement's own function and at module level. MEASURED 2026-09-23: looking
    names up across the whole file read tools/layered_alpha.py _render_gate()'s `d` (its own directory) as
    ALSO the state/layered pool directory load_screens() binds to `d`."""
    tree = ast.parse(path.read_text(), str(path))
    module_env = _bindings(tree)
    mods, aliases = _sys_names(tree)

    def is_sys_path(x):
        return _is_sys_path_expr(x, mods, aliases)

    def is_copy(x, env, depth=0):
        """A copy of sys.path -- list(sys.path), sys.path[:], sys.path.copy() -- or a name every binding of which is
        one. Draw 6: forge/gen/spend.py _predict() saves `saved = list(sys.path)` and restores `sys.path[:] = saved`;
        a restore puts back only directories already on the path, which the walk read when they were added, so it
        adds none -- and it was listed unread, which test_ci_gate requires to be empty for the scorer's closure."""
        if isinstance(x, ast.Call) and getattr(x.func, "id", None) == "list" and len(x.args) == 1:
            return is_sys_path(x.args[0])
        if isinstance(x, ast.Subscript) and isinstance(x.slice, ast.Slice) and not any(
                (x.slice.lower, x.slice.upper, x.slice.step)):
            return is_sys_path(x.value)
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "copy" and not x.args:
            return is_sys_path(x.func.value)
        return isinstance(x, ast.Name) and depth < 8 and bool(env.get(x.id)) and all(
            is_copy(v, env, depth + 1) for v in env[x.id])
    found, unread = set(), []
    where = lambda n: "%s:%d" % (path.relative_to(root).as_posix(), n.lineno)          # noqa: E731
    for scope in [tree] + [n for n in ast.walk(tree) if isinstance(n, _SCOPES)]:
        env = module_env if scope is tree else dict(module_env, **_bindings(scope))
        skip = lambda x, env=env: is_sys_path(x) or is_copy(x, env)                     # noqa: E731
        for n in _own_nodes(scope):
            parts = []
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and is_sys_path(n.func.value):
                m = n.func.attr
                if m in ("insert", "append"):
                    parts = n.args[1:2] if m == "insert" else n.args[:1]
                elif m == "extend" and n.args:
                    parts = _added_parts(n.args[0], skip)
                elif m not in _SYS_PATH_READS:
                    unread.append(where(n))
            elif isinstance(n, ast.Assign) and any(is_sys_path(t.value if isinstance(t, ast.Subscript) else t)
                                                   for t in n.targets):
                parts = _added_parts(n.value, skip)
            elif isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Add) and is_sys_path(n.target):
                parts = _added_parts(n.value, skip)
            for x in parts:
                got = _path_values(x, env, path, root)
                if not got:
                    unread.append(where(n))
                found |= got
    return {p.resolve() for p in found}, unread


def _imported_names(path: pathlib.Path, root: pathlib.Path) -> set:
    """Every dotted name an import statement ANYWHERE in `path` asks Python for: module level, inside a
    function, under try/except or `if TYPE_CHECKING:` alike -- a deferred import still runs when the
    scorer calls that function. Each package on the way counts (importing forge.x runs forge/__init__.py),
    and `from p import n` counts p.n as well as p, since n may be a submodule."""
    out = set()
    for n in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:                                  # relative: from the importing file's own package
                pkg = list(path.relative_to(root).parent.parts)
                pkg = pkg[:len(pkg) - (n.level - 1)]
                base = ".".join(pkg + ([n.module] if n.module else []))
            else:
                base = n.module
            mods = [base] + ["%s.%s" % (base, a.name) for a in n.names if a.name != "*"]
        else:
            continue
        for m in mods:
            parts = m.split(".")
            out.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return out


def import_closure(entry=SCORER, root=ROOT) -> dict:
    """Draw-3 ci SERIOUS 3: `entry` and every repository file it imports, transitively, found by reading
    the syntax trees (nothing is imported or run). {"files", "import_roots", "unread"}, paths relative to
    `root`. `entry` is one path or a list of them (draw3_fix ci 4: tools/ci_gate.py check_no_live walks the
    closure of every test file and loaded conftest in one pass).

    Why transitive and why deferred imports count: the scorer's decisions are made by whatever code it
    calls. MEASURED 2026-09-23 on the dev tree: benchmark.py imports forge.harvest and forge.submit at module
    level, and fingerprint, forge.hypotheses, forge.standard, forge.probe and forge.offline.branch_drill
    inside functions; branch_drill imports forge.runner. CONSEQUENCE, stated so nobody meets it by surprise:
    an edit to ANY file in the closure moves the golden card's identity and blocks the gate until the golden
    is re-recorded; the re-record's diff names exactly which files moved.

    THE IMPORT ROOTS ARE DERIVED TOO, not listed. A name is looked up in every directory some file of the
    closure puts on sys.path (_sys_path_entries), and the walk repeats until no new directory appears. The
    first version searched a hand-kept ("", "tools") and MISSED tools/funnel/gate_lib.py,
    tools/funnel/precheck_lib.py and tools/autoloop/driver.py, which files in the closure import after
    putting tools/funnel and tools/autoloop on sys.path (the module-level loop of
    harness13/massgen/mg/simulate.py, tools/submit_budget.py check_banned(), the module level of
    tools/self_corr_predict.py; draw3_fix ci 8: cited by line, and one line had moved). A sys.path entry the
    evaluator cannot read is listed in `unread` -- it may hide modules -- and test_ci_gate.py requires the
    list to be empty on the real tree."""
    root = pathlib.Path(root).resolve()
    entries = [entry] if isinstance(entry, str) else list(entry)
    roots, unread = {root}, set()
    while True:
        seen, todo = set(), [root / e for e in entries]
        while todo:
            p = todo.pop()
            if p in seen:
                continue
            seen.add(p)
            for m in _imported_names(p, root):
                todo += [f.resolve() for f in _module_files(m, sorted(roots)) if f.resolve() not in seen]
        found = set()
        for p in seen:
            dirs, bad = _sys_path_entries(p, root)
            # inside the repository only (an entry outside it -- tools/autoloop/driver.py still names the old
            # /Users/kanenguyen/wq_pipeline -- holds no repository module); whether the directory EXISTS is
            # not asked, so a directory present on one machine only cannot change the card
            found |= {d for d in dirs if d.is_relative_to(root)}
            unread.update(bad)
        if found <= roots:
            break
        roots |= found
    rel = lambda p: p.relative_to(root).as_posix()                        # noqa: E731
    return {"files": sorted(rel(p) for p in seen), "import_roots": sorted(rel(r) for r in roots),
            "unread": sorted(unread)}


#: What a constant reads on the card when the scorer does not define it. Draw 6: the scoring build removed
#: ARMS_MDR_DRAWS and ARMS_MDR_SEED, and card() raised AttributeError -- the gate then printed "the scorer failed on
#: the truth table" and no difference at all, so which decisions moved could only be seen with a scratch stand-in.
#: A removed constant now reads this marker and shows in the diff like any other moved value.
ABSENT = "<not defined by the scorer>"
#: Values the scorer COMPUTES from libm transcendental functions (math.erfc), recorded to 10 significant digits.
#: EX-ANTE (Python's math module docs: its functions are thin wrappers of the platform C library): the last bit of
#: erfc may differ between macOS's libm and glibc, and the hosted tier runs on Linux; 10 digits keep every value the
#: design states (5.153e-05 ...) and drop only that bit. Nothing was observed to differ: no Linux run was made.
_SIGNIFICANT = "%.10g"


def _constant(B, name, fn=None):
    """benchmark.<name> as the card records it (through `fn` when given), or ABSENT."""
    if not hasattr(B, name):
        return ABSENT
    v = getattr(B, name)
    return fn(v) if fn else v


def card() -> dict:
    """The truth table as the scorer decides it today, with the identity of the scorer and of this file:
    `scorer_sha256` is benchmark.py's own bytes (the hash every scorecard prints in its provenance), and
    `scorer_closure` is {path: sha256} for benchmark.py and every repository file it imports (SERIOUS 3),
    with the import roots the walk derived and any sys.path entry it could not read beside it."""
    B = _scorer()
    closure = import_closure()
    C = lambda name, fn=None: _constant(B, name, fn)                                   # noqa: E731
    digits = lambda v: [float(_SIGNIFICANT % x) for x in v]                            # noqa: E731
    out = {"scorer": SCORER, "scorer_sha256": B.scorer_sha256(),
           "scorer_closure": {rel: sha256(ROOT / rel) for rel in closure["files"]},
           "scorer_closure_import_roots": closure["import_roots"], "scorer_closure_unread": closure["unread"],
           "fixture": "tools/ci_fixture.py", "fixture_sha256": sha256(__file__),
           "constants": {"FLOOR": C("FLOOR"), "RANK_ORDER": C("RANK_ORDER"), "VERDICT_ORDER": C("VERDICT_ORDER"),
                         "BINDING": C("BINDING"),
                         "SCORED_STATUS": C("SCORED_STATUS"), "POST_HORIZON_DAYS": C("POST_HORIZON_DAYS"),
                         "REGIME_SE_MULTIPLE": C("REGIME_SE_MULTIPLE"), "REGIME_PASS": C("REGIME_PASS"),
                         "DORA_BAND": C("DORA_BAND"),
                         # axis 1's thresholds, named since draw 3 (each also has a case on either side)
                         "DSR_MIN": C("DSR_MIN"), "NEIGHBOUR_RETENTION_MIN": C("NEIGHBOUR_RETENTION_MIN"),
                         "NEIGHBOURS_MIN": C("NEIGHBOURS_MIN"), "CURVE_POINTS_MIN": C("CURVE_POINTS_MIN"),
                         "CORR_UNDER_LINE": C("CORR_UNDER_LINE", lambda f: f.__name__),
                         "CORR_LINE_DEFAULT": B.SUB.CORR_LINE_DEFAULT,
                         "MODULE_TEST_COVERAGE_MIN": C("MODULE_TEST_COVERAGE_MIN"),
                         # draw-3 ci SERIOUS 4: missing from the card; no case reaches the MDR search limits
                         "MDR_MAX_EVENTS": C("MDR_MAX_EVENTS"), "MDR_MAX_RATIO": C("MDR_MAX_RATIO"),
                         # D24 is PRE-REGISTERED: every field is pinned, not_the_submission_count included
                         "ESTIMAND": C("ESTIMAND", dict),
                         # D30 and D39, by name beside their cases (case_cohorts, case_generated_alpha)
                         "STAMP_MARKERS": C("STAMP_MARKERS"), "GENERATED_PREFIX": C("GENERATED_PREFIX"),
                         "MEANING_DECIDABLE": C("MEANING_DECIDABLE"), "MEANING_NOT_APPLICABLE": C("MEANING_NOT_APPLICABLE"),
                         # D56, beside case_generated_alpha
                         "PBO_INSUFFICIENT": C("PBO_INSUFFICIENT"),
                         # the watch-row contract's two sets, beside case_watch_rows
                         "WATCH_KEEPS_RUNNING": C("WATCH_KEEPS_RUNNING"), "WATCH_ROUND_FAILED": C("WATCH_ROUND_FAILED"),
                         # D47 / D54 / D55 / D60: the arms, who assigned a round, the estimand's branch route, the
                         # looks and their boundaries, the permutation's precision, the placebo readings and the
                         # withdrawn MDR's note, and the design PRE-REGISTERED before any arm row existed -- every
                         # field pinned, as ESTIMAND's are (draw 6: ARMS_MDR_DRAWS / ARMS_MDR_SEED were removed)
                         "ARMS": C("ARMS"), "ARMS_ASSIGNED_BY": C("ARMS_ASSIGNED_BY"),
                         "ARMS_FRESH_ROUTE": C("ARMS_FRESH_ROUTE"), "ARMS_LOOK_DAYS": C("ARMS_LOOK_DAYS"),
                         "MIN_SHARED_DAYS": C("MIN_SHARED_DAYS"), "ARMS_OBF_C": C("ARMS_OBF_C"),
                         "ARMS_BOUNDARY_Z": C("ARMS_BOUNDARY_Z", digits), "ARMS_NOMINAL_P": C("ARMS_NOMINAL_P", digits),
                         "ARMS_PERM_EXCEED": C("ARMS_PERM_EXCEED"), "ARMS_PERM_MAX": C("ARMS_PERM_MAX"),
                         "ARMS_PERM_SEED": C("ARMS_PERM_SEED"), "ARMS_PLACEBO": C("ARMS_PLACEBO"),
                         "ARMS_MDR_NOTE": C("ARMS_MDR_NOTE"), "ARMS_DESIGN": C("ARMS_DESIGN", dict),
                         # round 3 F1: printed before every compare() verdict
                         "COMPARE_IS_NOT_GATE3": C("COMPARE_IS_NOT_GATE3"),
                         # round 3 S10: the journal fields a card reads (case_input_layer reads through them)
                         "JOURNAL_KEEP": C("JOURNAL_KEEP"), "JOURNAL_KEEP_SETTINGS": C("JOURNAL_KEEP_SETTINGS"),
                         "JOURNAL_KEEP_META": C("JOURNAL_KEEP_META"), "JOURNAL_KEEP_CHECK": C("JOURNAL_KEEP_CHECK")},
           "cases": {fn.__name__[len("case_"):]: fn() for fn in CASES}}
    return json.loads(json.dumps(out))
