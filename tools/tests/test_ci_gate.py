"""Suite for tools/ci_gate.py -- the gate a change must clear.

Each test pins a way the gate was found to be able to lie: on 2026-09-23 by its own first three runs, and
then by architecture round 2 (docs/evalharness/audits/architecture_round2.md), whose finding id each
later test names.
"""
import functools
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parents[1])]

import ci_fixture as F  # noqa: E402
import ci_gate as G  # noqa: E402

#: the dangerous flags, assembled: check_no_live reads this very file and would fire on them as test DATA
LIVE, SUBMIT = "--" + "live", "--" + "submit"


def _root(tmp_path, data=False, classification=None, baseline=None, known=None):
    (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
    if data:
        for m in G.DATA_MARKERS:
            (tmp_path / m).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / m).write_text("{}\n")
    if classification is not None:
        (tmp_path / "tools/ci_data_bound.json").write_text(json.dumps(classification))
    if baseline is not None:
        (tmp_path / "tools/ci_baseline.json").write_text(json.dumps(baseline))
    if known is not None:
        (tmp_path / G.KNOWN_RED).write_text(json.dumps({"tests": known}))
    return tmp_path


@functools.lru_cache(maxsize=1)
def _live_card():
    """The truth table as the scorer in this tree decides it (in-process, once per session)."""
    return F.card()


def test_the_tier_is_decided_by_the_presence_of_the_desks_data(tmp_path):
    assert G.tier(_root(tmp_path)) == "hermetic"
    assert G.tier(_root(tmp_path, data=True)) == "data"


def test_the_data_tier_leaves_red_tests_to_the_tests_check(tmp_path):
    root = _root(tmp_path, data=True, classification={"red": ["a::b"]})
    assert G.check_known_red(root)["ok"] is True       # the tests check runs it directly there


def test_the_frozen_cohort_reproduces_the_committed_golden_card():
    """Draw 2: the pre-merge gate judges the scorer, not the journal (round 1, F1)."""
    r = G.check_pinned_scorer()
    assert r["ok"] is True, r["summary"]


def test_a_changed_judgement_is_caught_and_named(tmp_path):
    """A floor, weight or gate changed in the same commit as the pipeline used to pass unseen (round 1, S8).
    Any difference between the scorer's card and the golden card blocks, naming the field."""
    golden = json.loads(G.GOLDEN.read_text())
    golden["constants"]["FLOOR"]["axis2_throughput"] = 3.0          # someone lowered the bar
    fake = tmp_path / "golden.json"
    fake.write_text(json.dumps(golden))
    r = G.check_pinned_scorer(golden_path=fake)
    assert r["ok"] is False and "FLOOR.axis2_throughput" in r["summary"]


def test_a_missing_golden_card_fails_closed(tmp_path):
    r = G.check_pinned_scorer(golden_path=tmp_path / "absent.json")
    assert r["ok"] is False and "no committed golden card" in r["summary"]


def test_the_diff_walks_nested_cards():
    assert G._diff({"a": {"b": 1}}, {"a": {"b": 1}}) == []
    assert G._diff({"a": {"b": 1}}, {"a": {"b": 2}}) == ["a.b: 1 -> 2"]
    assert G._diff({"a": 1}, {"a": 1, "c": 3}) == ["c: None -> 3"]


def test_no_live_flags_a_quota_spending_line_and_ignores_the_guards_about_it(tmp_path):
    (tmp_path / "forge/tests").mkdir(parents=True)
    (tmp_path / "tools/tests").mkdir(parents=True)
    (tmp_path / "forge/tests/test_ok.py").write_text('assert "%s" not in argv\n# never pass %s\n' % (LIVE, LIVE))
    assert G.check_no_live(tmp_path)["ok"] is True
    # the flag is assembled so THIS file does not trip the very check it tests -- which it did on the
    # third Actions run, and which is also the proof that a grep can be walked around (see the gate)
    (tmp_path / "tools/tests/test_bad.py").write_text('run(["runner.py", "%s"])\n' % LIVE)
    r = G.check_no_live(tmp_path)
    assert r["ok"] is False and "test_bad.py:1" in r["summary"]


def test_the_branch_drill_is_reported_not_run_on_a_hosted_runner_never_as_passed_silently(tmp_path):
    r = G.check_branch_drill(_root(tmp_path))
    assert "NOT RUN" in r["summary"]


# ------------------------------------------------------------------------------ A7: the truth table
GATES = ("all_binding_pass", "dsr_ge_095", "pbo_pass", "corr_under_lines", "neighbourhood_stable",
         "regime_stable", "hypothesis_standard_8of8")


def test_the_fixture_is_a_truth_table_of_every_decision_the_scorer_makes():
    """A7: the first fixture was one nine-row cohort, and round 2 measured six scorer edits (both floors
    loosened, DSR 0.95 -> 0.50, compare() hard-wired, DORA's CFR check and the import-cycle check made
    always true) leaving the golden card identical. The card must now reach every decision round 2
    listed: proven / unproven / refuted PER GATE, the unfinished day, WARNING rows, the POST horizon, the
    lexicographic rank on at least three versions including one that adds clean output, compare() on the
    D24 estimand both ways and neither way, and DORA on and off."""
    cases = _live_card()["cases"]
    per = cases["axis1_gates"]["per_alpha"]
    for g in GATES:
        only_false = [a for a, d in per.items() if [k for k, v in d["gates"].items() if v is not True] == [g]
                      and d["gates"][g] is False]
        assert only_false and {per[a]["status"] for a in only_false} == {"refuted"}, g
        if g == "all_binding_pass":
            continue                                   # a check set always yields True or False
        only_none = [a for a, d in per.items() if [k for k, v in d["gates"].items() if v is not True] == [g]
                     and d["gates"][g] is None]
        assert only_none and {per[a]["status"] for a in only_none} == {"unproven"}, g
    assert per["all_gates_pass"]["status"] == "proven"
    w = cases["window"]
    assert w["window"]["until_exclusive"] == w["window"]["excluded_unfinished_day"] == "2026-09-16"
    assert w["graded_submissions"] == ["complete_row", "warning_row"]            # WARNING scored; today not
    early, late = cases["post_horizon"]["graded_2026-09-06"], cases["post_horizon"]["graded_2026-09-25"]
    assert early["post_horizon"]["final"] is False and late["post_horizon"]["final"] is True
    # A4: credited within 14 days; D49: graded by axis 1 (rank level 1) whatever the lag, never credited
    assert late["submissions"] == 4 and late["posted_beyond_the_horizon"] == ["posted_14_days_and_1_hour", "posted_after_20_days"]
    assert set(late["posted_beyond_the_horizon"]) < set(late["graded_by_axis1"]) and late["rank_level_1"] == 6
    rank = cases["rank"]
    assert len(rank["levels"]) >= 3 and rank["rank_cmp"]["PPP vs P"] == -1     # added clean output ranks higher
    assert {c["verdict"] for c in cases["compare"].values()} == {"better", "worse", "indistinguishable", "no-data"}
    assert cases["dora"]["off"]["dora_block"] is False
    # draw-3 ci MINOR: "every band check is seen both ways" -- all three, True on one ledger, False on the other
    healthy, degraded = (dict(map(tuple, cases["dora"][k]["band"])) for k in ("healthy", "degraded"))
    assert len(healthy) == 3 and set(healthy) == set(degraded)
    assert all(healthy.values()) and not any(degraded.values())
    assert len(cases["dora"]["reshipped"]["band"]) == 2          # a re-ship restores nothing: no time to restore
    assert all(cases["dora"][k]["verdict_and_rank_equal_to_off"] for k in ("degraded", "healthy", "reshipped"))


BENCH, SUBMIT_PY = "forge/offline/benchmark.py", "forge/submit.py"
HARVEST_PY, PROBE_PY = "forge/harvest.py", "forge/probe.py"
#: The scorer edits the golden must catch, each (file, target, replacement, THE CASE IT MUST MOVE) applied IN
#: MEMORY to a file of the scorer's import closure. The first six are round 2's A7 table, where they left the
#: golden identical; the rest are one per later decision, named by the finding that introduced it. Draw 3 named
#: axis 1's thresholds, so five targets moved from inline numbers to the constants -- DSR_MIN,
#: NEIGHBOUR_RETENTION_MIN, NEIGHBOURS_MIN, CURVE_POINTS_MIN, CORR_UNDER_LINE (draw3_fix ci 8: this said six) --
#: the draw-3 scoring engineer's replacements, each re-checked here to apply once and move a case.
#: Draw4_build ci 8(c): the test asked only that SOME case move, while ci_fixture said each decision's case "must
#: see" its edit; the fourth element now names that case, and the test runs that case alone under the edit.
MUTANTS = {
    "A7 axis-1 floor: every submitted proven -> none refuted":
        (BENCH, '"floor_met": bool(n) and statuses["proven"] == n,', '"floor_met": bool(n) and statuses["refuted"] == 0,',
         "floors"),
    "A7 axis-2 floor: point rate -> interval upper":
        (BENCH, 'bool(known and days and rate >= FLOOR["axis2_throughput"])', 'bool(known and days and hi >= FLOOR["axis2_throughput"])',
         "floors"),
    "A7 DSR threshold 0.95 -> 0.50": (BENCH, "DSR_MIN = 0.95", "DSR_MIN = 0.50", "axis1_gates"),
    "A7 compare() hard-wired indistinguishable":
        (BENCH, 'out["verdict"] = "indistinguishable" if p > ESTIMAND["alpha"] or direction is None else direction',
         'out["verdict"] = "indistinguishable"', "compare"),
    "A7 DORA change-failure check always true":
        (BENCH, 'd["change_failure_rate"] <= b["change_failure_rate_max"]', 'True', "dora"),
    "A7 import-cycle check always true": (BENCH, 'not cyc["module_level"]', 'True', "axis3_tree"),
    "A7 neighbour retention 0.5 -> 0.05":
        (BENCH, "NEIGHBOUR_RETENTION_MIN = 0.5", "NEIGHBOUR_RETENTION_MIN = 0.05", "axis1_gates"),
    "D3 two neighbours -> one": (BENCH, "NEIGHBOURS_MIN = 2", "NEIGHBOURS_MIN = 1", "axis1_gates"),
    "D3 300 curve points -> 200": (BENCH, "CURVE_POINTS_MIN = 300", "CURVE_POINTS_MIN = 200", "regime"),
    "corr line strict < -> <=": (BENCH, "CORR_UNDER_LINE = operator.lt", "CORR_UNDER_LINE = operator.le", "axis1_gates"),
    "S3-NL thirds judged against 0 standard errors":
        (BENCH, "REGIME_SE_MULTIPLE = 2.0", "REGIME_SE_MULTIPLE = 0.0", "regime"),
    "S3-NL negative-overall flag removed": (BENCH, '"negative-overall" if overall < 0 else ', "", "regime"),
    # the credit horizon's comparison moved into _submissions with D49 (a POST at exactly 14 days is credited)
    "A4 POST credit horizon <= -> <":
        (BENCH, "        if t - c <= POST_HORIZON_DAYS * DAY_S:\n            first[a] = h\n",
         "        if t - c < POST_HORIZON_DAYS * DAY_S:\n            first[a] = h\n", "post_horizon"),
    "S5 the unfinished day counted":
        (BENCH, "last = min(until or today, today)", "last = _next_day(min(until or today, today))", "window"),
    "F3 WARNING rows not scored":
        (BENCH, 'SCORED_STATUS = ("COMPLETE", "WARNING")', 'SCORED_STATUS = ("COMPLETE",)', "window"),
    "A5 unproven counted as clean":
        (BENCH, 'clean = [s for s in submissions if s.get("alpha") in proven_alphas]',
         'clean = [s for s in submissions if statuses.get(s.get("alpha")) != "refuted"]', "floors"),
    # draw 6: D57 changed rank_key's line (level 1 through _level1_at); the edit is the same swap on the new line
    "D25 rank levels 1 and 2 swapped":
        (BENCH, "ref, rate, a3 = _level1_at(lv, lag_days), lv.get(RANK_ORDER[1]), lv.get(RANK_ORDER[2])",
         "rate, ref, a3 = _level1_at(lv, lag_days), lv.get(RANK_ORDER[1]), lv.get(RANK_ORDER[2])", "rank"),
    "D2 axis 3's floor ignored by the verdict":
        (BENCH, 'unmet = [k for k in FLOOR if not (axes.get(k) or {}).get("floor_met")]',
         'unmet = [k for k in ("axis1_product", "axis2_throughput") if not (axes.get(k) or {}).get("floor_met")]', "floors"),
    "S4-NL axis-3 floor >= -> >":
        (BENCH, 'value >= FLOOR["axis3_gearing"]}', 'value > FLOOR["axis3_gearing"]}', "axis3_tree"),
    "S10-NL neighbour pool not restricted to the version":
        (BENCH, "        pool = cohort\n", "        pool = scored_rows\n", "neighbour_pool"),
    "m1 the next window counts refuted POSTs":
        (BENCH, 'k = sum(1 for s in g["subs"] if g["statuses"].get(s["alpha"]) == "proven")', 'k = len(g["subs"])',
         "sustainability"),
    "A3 deploy days not excluded":
        (BENCH, 'if not (r["outcome"] == "deployed" and running is not None and running == before):', "if False:",
         "exposure"),
    # rate_test_p, the POOLED test: since D28 it decides nothing and is printed (compare()'s `pooled`), so the case
    # that sees it is the one that records the pooled p -- compare_within_cell (MEASURED 2026-09-23: case_compare,
    # which this named until draw4_build ci 8(c) made the name binding, does not move)
    "D24 the test's two-sided doubling dropped":
        (BENCH, "return min(1.0, 2.0 * min(sum(pmf[:k_b + 1]), sum(pmf[k_b:])))",
         "return min(1.0, min(sum(pmf[:k_b + 1]), sum(pmf[k_b:])))", "compare_within_cell"),
    # -- draw-3 ci SERIOUS 4: the seven edits that moved no case (docs/evalharness/audits/draw3_build.md, ci)
    "SERIOUS 4 a binding check reads != FAIL (missing or PENDING passes)":
        (BENCH, 'return all(_chk(row, n).get("result") == "PASS" for n in names)',
         'return all(_chk(row, n).get("result") != "FAIL" for n in names)', "axis1_gates"),
    "SERIOUS 4 alpha_status checks unproven before refuted":
        (BENCH, '    if any(v is False for v in gates.values()):\n        return "refuted"\n',
         '    if any(v is None for v in gates.values()):\n        return "unproven"\n'
         '    if any(v is False for v in gates.values()):\n        return "refuted"\n', "axis1_gates"),
    "SERIOUS 4 the self-correlation line dropped":
        (BENCH, "and CORR_UNDER_LINE(p, pl) and CORR_UNDER_LINE(s, sl))", "and CORR_UNDER_LINE(p, pl))", "axis1_gates"),
    "SERIOUS 4 an unknown rate ranked as 0 per day": (BENCH, "inf if rate is None else -rate", "0.0 if rate is None else -rate",
                                                     "rank"),
    "SERIOUS 4 module-test coverage bound 1.0 -> 0.8 (draw 2's value)":
        (BENCH, "MODULE_TEST_COVERAGE_MIN = 1.0", "MODULE_TEST_COVERAGE_MIN = 0.8", "axis3_tree"),
    "SERIOUS 4 curve bound 300 -> 400": (BENCH, "CURVE_POINTS_MIN = 300", "CURVE_POINTS_MIN = 400", "axis1_gates"),
    "SERIOUS 4 curve bound 300 -> 301 (pinned exactly)": (BENCH, "CURVE_POINTS_MIN = 300", "CURVE_POINTS_MIN = 301", "regime"),
    "SERIOUS 4 DORA window 28 -> 7 days":
        (BENCH, "def dora(rows, now=None, window_days=28)", "def dora(rows, now=None, window_days=7)", "dora"),
    # -- draw-3 ci SERIOUS 3: the self line, in the scorer's imports -- invisible to benchmark.py's own hash
    "SERIOUS 3 corr_lines reads the PROD limit for both lines (the audit's edit)":
        (SUBMIT_PY, 'for name in ("PROD_CORRELATION", "SELF_CORRELATION"):', 'for name in ("PROD_CORRELATION", "PROD_CORRELATION"):',
         "axis1_gates"),
    "SERIOUS 3 corr_lines swaps the prod and self limits":
        (SUBMIT_PY, 'for name in ("PROD_CORRELATION", "SELF_CORRELATION"):', 'for name in ("SELF_CORRELATION", "PROD_CORRELATION"):',
         "axis1_gates"),
    "SERIOUS 3 the prod and self readings swapped":
        (BENCH, 'p, s = c.get("prod"), c.get("self")', 'p, s = c.get("self"), c.get("prod")', "axis1_gates"),
    "SERIOUS 3 control: the default line 0.7 -> 0.75":
        (SUBMIT_PY, "CORR_LINE_DEFAULT = 0.7", "CORR_LINE_DEFAULT = 0.75", "axis1_gates"),
    # -- draw3_fix ci 6: the self line compared with <= moved no case (self_corr_exactly_at_the_default_line)
    "draw3_fix ci 6 the self line reads <= (a self reading AT the line passes)":
        (BENCH, "and CORR_UNDER_LINE(p, pl) and CORR_UNDER_LINE(s, sl))", "and CORR_UNDER_LINE(p, pl) and s <= sl)",
         "axis1_gates"),
    # -- the decisions ticked 2026-09-23 (00_agreements.md), one edit or more each, undoing the decision
    "D26 rank level 1 counts refuted only (an unproven submission costs nothing)":
        (BENCH, 'not_proven = a1["refuted"] + a1["unproven"]', 'not_proven = a1["refuted"]', "rank"),
    "D27 a card whose POST horizon is open is ranked":
        (BENCH, 'if lv.get("horizon_final") is not True:', "if False:", "rank_open_horizon"),
    "D27 finality judged at now, not at seen_until = min(now, data_through)":
        (BENCH, "seen_until = now if data_through is None else min(now, data_through)", "seen_until = now",
         "rank_open_horizon"),
    "D28 the pooled test decides":
        (BENCH, "p = stratified_rate_test_p(shared)", 'p = rate_test_p(A["k"], A["n"], Bv["k"], Bv["n"])',
         "compare_within_cell"),
    "D28 cells that disagree ignored (direction from the pooled rates)":
        (BENCH, '    dirs = {v["direction"] for v in cells.values() if v["events"]}\n'
                '    direction = "better" if dirs == {"B higher"} else "worse" if dirs == {"B lower"} else None\n',
         '    dirs = {v["direction"] for v in cells.values() if v["events"]}\n'
         '    direction = "better" if Bv["k"] * A["n"] > A["k"] * Bv["n"] else "worse"\n', "compare_within_cell"),
    "D28 the stratified test's two-sided doubling dropped":
        (BENCH, "return min(1.0, 2.0 * min(sum(dist[:t + 1]), sum(dist[t:])))",
         "return min(1.0, min(sum(dist[:t + 1]), sum(dist[t:])))", "compare_within_cell"),
    "D29 the verdict does not lead the rank":
        (BENCH, 'return (VERDICT_ORDER.get(lv.get("verdict"), len(VERDICT_ORDER)),', "return (0,", "verdict_leads_rank"),
    "D30 run_config ignored: one cohort per pipeline_version":
        (BENCH, "    return (pv, rc) if _forms_cohort(pv, rc) else None\n", "    return (pv, None) if _forms_cohort(pv, rc) else None\n",
         "cohorts"),
    "D30 a '+'-suffixed stamp forms a cohort":
        (BENCH, 'return isinstance(v, str) and bool(v) and "+" not in v and v not in STAMP_MARKERS',
         "return isinstance(v, str) and bool(v) and v not in STAMP_MARKERS", "cohorts"),
    "draw4_build ci 1: a marker pipeline_version (unknown, ambiguous) forms a cohort":
        (BENCH, 'return isinstance(v, str) and bool(v) and "+" not in v and v not in STAMP_MARKERS',
         'return isinstance(v, str) and bool(v) and "+" not in v', "cohorts"),
    "pipeline P2 / scoring 3: a marker or suffixed run_config forms a cohort":
        (BENCH, "return plain_stamp(pv) and (rc is None or plain_stamp(rc))",
         "return plain_stamp(pv) and (rc is None or isinstance(rc, str))", "cohorts"),
    "D39 G1-G3 required of a generated alpha":
        (BENCH, 'MEANING_DECIDABLE = ("G4", "G5", "G6", "G7", "G8")',
         'MEANING_DECIDABLE = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")', "generated_alpha"),
    "D39 a missing meaning row read as a pass":
        (BENCH, "            return None, detail\n", "            return True, detail\n", "generated_alpha"),
    "D39 a meaning row scored after the clock is seen":
        (BENCH, "or t is None or t > now or t < created or", "or t is None or t < created or", "generated_alpha"),
    # -- round 3 S8: which meaning row is graded
    "S8 a row of ANOTHER formula's sha is read":
        (BENCH, " or m.get(\"formula_sha\") != sha:", ":", "generated_alpha"),
    "S8 a row scored before the alpha existed is read":
        (BENCH, "or t is None or t > now or t < created or", "or t is None or t > now or", "generated_alpha"),
    "S8 the LATEST meaning row decides":
        (BENCH, '(t, i) < best[m["alpha"]][0]', '(t, i) > best[m["alpha"]][0]', "generated_alpha"),
    # -- D45: a run_config cohort's days from the run_config log
    "D45 the run_config log ignored (every cohort takes all its version's days)":
        (BENCH, '    if rc is None or not base["known"]:\n        return base\n', "    return base\n", "run_config_exposure"),
    "D45 a day the run_config changed on is counted":
        (BENCH, "        elif part:\n            mixed.append(d)\n", "        elif part:\n            counted.append(d)\n",
         "run_config_exposure"),
    "D45 one timeline for every host (a Mac dry run ends the loop's run_config)":
        (BENCH, 'timelines[r.get("host")].append(', "timelines[None].append(", "run_config_exposure"),
    "D45 days before the cohort's first log row are not 'exposure unknown'":
        (BENCH, "if first is None or end <= first:", "if first is None:", "run_config_exposure"),
    # -- D47: the branch against the incumbent within day (draw 6: the D47 edits whose targets the D54/D55 rewrite of
    # compare_arms removed -- the pooled stratified test, the day minimum, MIN_SHARED_DAYS = 5, the cohort filter and
    # the MDR's pooled base -- are replaced by the D54 / D55 / D60 edits below, each on the code that now decides)
    "D47 cells that disagree ignored (direction from the summed excess)":
        (BENCH, '    dirs = {v["direction"] for v in cells.values()}\n'
                '    direction = "better" if dirs == {"B higher"} else "worse" if dirs == {"B lower"} else None\n',
         '    dirs = {v["direction"] for v in cells.values()}\n'
         '    direction = "better" if sum(v["excess_b"] for v in cells.values()) > 0 else "worse"\n', "compare_arms"),
    "D47 the arms swapped": (BENCH, 'ARMS = ("composites", "gen")', 'ARMS = ("gen", "composites")', "compare_arms"),
    "D47 rows of another pipeline_version read into the arms":
        (BENCH, 'if m.get("pipeline_version") != pipeline_version or not r.get("alpha") or not _visible_at(r, now):',
         'if not r.get("alpha") or not _visible_at(r, now):', "compare_arms"),
    "D47 / D54 the permutation pools the days (every round relabelled across days)":
        (BENCH, "days[day].append((arm, dict(cells)))", 'days["pooled"].append((arm, dict(cells)))', "compare_arms"),
    # -- D54: the round is the unit; only randomiser rounds; fresh draws only in B
    "D54 the ALPHA is the unit (each row its own round)":
        (BENCH, 'by_round[str(m["round"])].append((d, r))', 'by_round[r["alpha"]].append((d, r))', "compare_arms"),
    "D54 / D60 rounds of an explicit --mode admitted":
        (BENCH, 'if m.get("arm_by") != ARMS_ASSIGNED_BY else', "if False else", "compare_arms"),
    "D54 neighbour and repair rows counted in B":
        (BENCH, "if (route is None) if arm == ARMS[0] else (route == ARMS_FRESH_ROUTE):", "if True:", "compare_arms"),
    "D54 a round whose rows carry two arms is kept": (BENCH, "if len(arms) > 1:", "if False:", "compare_arms"),
    # -- D55: group-sequential looks
    "D55 a fixed 0.05 at every look": (BENCH, "nominal = ARMS_NOMINAL_P if nominal is None else nominal",
                                       "nominal = (0.05,) * len(looks) if nominal is None else nominal", "compare_arms"),
    "D55 no stop at a crossing (every look read)":
        (BENCH, '"higher" if verdict == "better" else "lower"))\n            break\n',
         '"higher" if verdict == "better" else "lower"))\n', "compare_arms"),
    "D55 looks count calendar days, not shared ones":
        (BENCH, "shared = sorted(d for d, a in by_day.items() if len(a) == len(ARMS))", "shared = sorted(by_day)",
         "compare_arms"),
    "D55 the first look at 6 shared days": (BENCH, "ARMS_LOOK_DAYS = (7, 14, 21, 28)", "ARMS_LOOK_DAYS = (6, 14, 21, 28)",
                                            "compare_arms"),
    "D55 the first look at 8 shared days": (BENCH, "ARMS_LOOK_DAYS = (7, 14, 21, 28)", "ARMS_LOOK_DAYS = (8, 14, 21, 28)",
                                            "compare_arms"),
    # -- D60: the rounds outside the randomiser are counted, each once
    "D60 an excluded round counted once per reason":
        (BENCH, '"excluded_rounds": len(set().union(*(e["rounds"] for e in excluded.values()))),',
         '"excluded_rounds": sum(len(e["rounds"]) for e in excluded.values()),', "compare_arms"),
    # -- D56: PBO "insufficient" on a generated pool is not applicable
    "D56 off (PBO insufficient counts as unmeasured)":
        (BENCH, 'and str(x.get("pbo_status") or "").startswith(PBO_INSUFFICIENT)) else {})', "and False) else {})",
         "generated_alpha"),
    "D56 a library alpha's insufficient PBO is not applicable too":
        (BENCH, 'if (isinstance(hyp, str) and hyp.startswith(GENERATED_PREFIX) and gates["pbo_pass"] is None',
         'if (gates["pbo_pass"] is None', "generated_alpha"),
    "D56 any pbo_status is not applicable":
        (BENCH, 'and str(x.get("pbo_status") or "").startswith(PBO_INSUFFICIENT)) else {})', ") else {})",
         "generated_alpha"),
    # -- D57: level 1 at equal post-creation exposure
    "D57 off (level 1 counted raw on both cards)":
        (BENCH, "lag = min(exposed) if exposed else None", "lag = None", "rank_equal_exposure"),
    "D57 exposure measured to now, not to seen_until":
        (BENCH, '"post_exposure_days": ((seen_until - _day_start(_next_day(newest))) / DAY_S',
         '"post_exposure_days": ((now - _day_start(_next_day(newest))) / DAY_S', "rank_equal_exposure"),
    # -- D49: a late POST costs rank level 1
    "D49 a POST after the horizon costs rank level 1 nothing (the rule before D49)":
        (BENCH, "        posted[a] = h\n        if t - c <= POST_HORIZON_DAYS * DAY_S:\n            first[a] = h\n",
         "        if t - c <= POST_HORIZON_DAYS * DAY_S:\n            posted[a] = h\n            first[a] = h\n", "post_horizon"),
    # -- draw4_build scoring 1: tools/deploy.py WATCH ROWS
    "scoring 1: a watch row read as a deploy":
        (BENCH, 'return "watched" in r or str(r.get("outcome") or "").startswith("watch_")', "return False", "watch_rows"),
    "scoring 1: watch_ok / timeout / not_rolled_back make the running version unknown":
        (BENCH, 'WATCH_KEEPS_RUNNING = ("watch_ok", "watch_timeout", "watch_not_rolled_back")', "WATCH_KEEPS_RUNNING = ()",
         "watch_rows"),
    "scoring 1: watch_rolled_back restores nothing":
        (BENCH, 'running = r.get("previous_pipeline_version") if r["outcome"] == "watch_rolled_back" else None',
         "running = None", "watch_rows"),
    "scoring 1: a failed first round is no change failure":
        (BENCH, 'fails = [r for r in pushes if r["outcome"] in failed or r.get("started_at") in failed_by_watch]',
         'fails = [r for r in pushes if r["outcome"] in failed]', "watch_rows"),
    "scoring 1: DORA counts watch rows as deploys":
        (BENCH, "    pushes = [r for r in rows if not _is_watch(r)]\n", "    pushes = rows\n", "watch_rows"),
    # -- round 3 S7: the input layer (build() and every reader load_inputs calls)
    "S7 load_inputs keeps the last 7 days of POSTs (the gamer's edit)":
        (BENCH, "    history = SUB.posted_history()\n",
         "    history = [h for h in SUB.posted_history() if (h.get(\"posted_at\") or 0) >= max(\n"
         "        [x.get(\"posted_at\") or 0 for x in SUB.posted_history()] + [0]) - 7 * 86400]\n", "input_layer"),
    "S7 read_journal keeps an alpha's FIRST row":
        (BENCH, 'latest[r["alpha"]] = _reduced(r, shared)', 'latest.setdefault(r["alpha"], _reduced(r, shared))',
         "input_layer"),
    "S7 / S10 the reduced journal row drops sharpe":
        (BENCH, 'JOURNAL_KEEP = ("alpha", "status", "dateCreated", "formula", "sharpe")',
         'JOURNAL_KEEP = ("alpha", "status", "dateCreated", "formula")', "input_layer"),
    "S7 / S10 the reduced journal row drops run_config":
        (BENCH, 'JOURNAL_KEEP_META = ("pipeline_version", "run_config", ', 'JOURNAL_KEEP_META = ("pipeline_version", ',
         "input_layer"),
    "S7 load_inputs states no data_through (the cut day graded as whole)":
        (BENCH, '"data_through": path.stat().st_mtime if exists else None', '"data_through": None', "input_layer"),
    # draw 6 (draw5 scoring M11): the three ledger loaders open their path as named through _jsonl_as_named; the
    # edits are re-anchored on the new bodies, and one more reads through the shared opener itself
    "S7 load_meaning reads nothing":
        (BENCH, "    return _jsonl_as_named(path or MEANING_LEDGER)\n", "    return None\n", "input_layer"),
    "S7 load_run_config_log reads nothing":
        (BENCH, "    return _jsonl_as_named(path or RUN_CONFIG_LOG)\n", "    return None\n", "input_layer"),
    "S7 load_deploys reads nothing":
        (BENCH, '    return _jsonl_as_named(pathlib.Path(root) / "state/deploys.jsonl")\n', "    return None\n", "input_layer"),
    "S7 the ledger opener keeps only the first line (draw5 scoring M11's reader)":
        (BENCH, "                out.append(json.loads(line))\n",
         "                out.append(json.loads(line))\n                break\n", "input_layer"),
    "S7 load_scored keeps an alpha's FIRST scored row (forge/harvest.py)":
        (HARVEST_PY, '                out[r["alpha"]] = r\n', '                out.setdefault(r["alpha"], r)\n', "input_layer"),
    "S7 load_corr lets a later non-number overwrite a reading (forge/probe.py)":
        (PROBE_PY, "                if isinstance(r.get(k), (int, float)):\n", "                if k in r:\n", "input_layer"),
    "S7 posted_history reads a row with no http as an accepted POST (forge/submit.py)":
        (SUBMIT_PY, '"posted_at": r.get("posted_at") or 0, "http": r.get("http"),',
         '"posted_at": r.get("posted_at") or 0, "http": r.get("http") or 201,', "input_layer"),
}


def _swap_in(monkeypatch, rel, src):
    """Execute `src` as the module at `rel` and put it wherever the scorer can reach the real one: in
    sys.modules, as its package's attribute, and as any name of benchmark.py bound to it (SUB, HV)."""
    import importlib
    name = rel[:-3].replace("/", ".")
    real = importlib.import_module(name)
    monkeypatch.setattr(sys, "path", list(sys.path))            # the module's own sys.path inserts are undone
    mod = types.ModuleType(name)
    mod.__file__ = real.__file__
    exec(compile(src, real.__file__, "exec"), mod.__dict__)
    monkeypatch.setitem(sys.modules, name, mod)
    pkg, _, leaf = name.rpartition(".")
    monkeypatch.setattr(importlib.import_module(pkg), leaf, mod)
    bench = importlib.import_module("forge.offline.benchmark")
    for k, v in list(vars(bench).items()):
        if v is real:
            monkeypatch.setattr(bench, k, mod)


def _one_case(name):
    """One case of the truth table as the scorer in memory decides it, JSON-normalised as card() records it."""
    return json.loads(json.dumps(getattr(F, "case_" + name)()))


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_the_golden_catches_every_scorer_edit_round_2_found_invisible(name, monkeypatch):
    """A7: each edit, applied to a file of the scorer in memory (the file untouched, so no hash can be what
    catches it), must move a DECISION on the truth table -- and, since draw4_build ci 8(c), the decision of the
    case it names: that case is run alone under the edit and must differ from the committed truth table's. A
    target that no longer occurs exactly once fails loudly: a mutant that cannot apply would make this test
    vacuous."""
    rel, old, new, case = MUTANTS[name]
    real = _live_card()["cases"][case]                     # BEFORE the swap, or the cache would hold the mutant
    before = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    src = (ROOT / rel).read_text()
    assert src.count(old) == 1, "%s changed under this mutant; update MUTANTS[%r]" % (rel, name)
    _swap_in(monkeypatch, rel, src.replace(old, new))
    assert G._diff(real, _one_case(case)), "case %s did not see: %s" % (case, name)
    assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == before           # only a decision can differ


def test_every_case_is_named_by_a_mutant_and_every_mutant_names_a_case():
    """Draw4_build ci 8(c): a case no edit must move pins nothing anyone checked; a name that is not a case would
    make its mutant's test raise instead of judge."""
    cases = {fn.__name__[len("case_"):] for fn in F.CASES}
    named = {m[3] for m in MUTANTS.values()}
    assert named <= cases and cases - named == set(), (named - cases, cases - named)


#: S8-NL: pinned as LITERALS, written here -- never read from the module, which is what the round-2 tests
#: did (test_benchmark.py read B.FLOOR), so a floor could move with the golden in one re-record.
FLOOR_LITERAL = {"axis1_product": 1.0, "axis2_throughput": 4.0, "axis3_gearing": 1.0}
#: D26 renamed level 1 for what it counts
RANK_ORDER_LITERAL = ["refuted_or_unproven_submitted", "proven_clean_per_quota_day", "axis3_held_fraction"]
#: D2/D6/A5 floor semantics: (verdict, floors unmet) on the boundary cards of case_floors
FLOOR_SEMANTICS_LITERAL = {
    "four_proven_in_one_day": ["PASS", []],                                    # exactly 4.0/day meets
    "three_proven_in_one_day": ["FAIL", ["axis2_throughput"]],                 # 3.0 < 4, though its interval reaches 8.8
    "four_proven_and_one_unproven": ["FAIL", ["axis1_product"]],               # 0 refuted is not enough
    "no_submission": ["FAIL", ["axis1_product", "axis2_throughput"]],
    "four_proven_axis3_six_of_seven": ["FAIL", ["axis3_gearing"]],
    "version_card_exposure_unknown": ["FAIL", ["axis2_throughput"]],           # no rate, no floor
    "version_card_exposure_from_the_ledger": ["PASS", []],
}
#: D25 as ticked, with D26: level 1 (refuted + unproven) first, so P+P+P+R and P+U rank below P; unknown
#: exposure below every rate at its level, a MEASURED rate of 0 ("nothing submitted") included (draw-3 ci
#: SERIOUS 4). Every card reads FAIL, so D29's verdict does not separate them.
BEST_FIRST_LITERAL = ["PPP", "P", "P, axis 3 six of seven", "nothing submitted", "P, exposure unknown", "PPP+R",
                      "P+U", "U"]
#: The constants of the decisions ticked 2026-09-23, pinned by name on the card and here as literals
DECISION_CONSTANTS_LITERAL = {"VERDICT_ORDER": {"PASS": 0, "FAIL": 1},                               # D29
                              "STAMP_MARKERS": ["unknown", "ambiguous"],                            # D30
                              "GENERATED_PREFIX": "gen:",                                           # D39
                              "MEANING_DECIDABLE": ["G4", "G5", "G6", "G7", "G8"],
                              "MEANING_NOT_APPLICABLE": ["G1", "G2", "G3"],
                              "ARMS": ["composites", "gen"],                                        # D47
                              "ARMS_ASSIGNED_BY": "randomiser",                                     # D54, D60
                              "ARMS_FRESH_ROUTE": "fresh",                                          # D54
                              "ARMS_LOOK_DAYS": [7, 14, 21, 28], "MIN_SHARED_DAYS": 7,              # D55
                              "PBO_INSUFFICIENT": "insufficient"}                                   # D56
#: What each decision ticked 2026-09-23 SETTLES, pinned by its outcome on the truth table, as literals for the
#: same reason as the floors: a re-record must not be able to move them with the golden unseen. Draw4_build ci
#: 8(d): this held, under the same heading, outcomes no tick settles; those are READINGS_LITERAL below.
DECISIONS_LITERAL = {
    # D27: refused while open, and still refused graded late on a copy cut before the horizon closed
    "rank_open_horizon": {"open": "NotComparable", "final": [1, 0, -0.5, -1.0], "late_clock_early_cut": "NotComparable",
                          "rank_cmp_open_vs_final": "NotComparable"},
    # D29: PASS above a FAIL whose levels are better
    "verdict_leads_rank": ["PASS", "FAIL, better levels"],
    # D28: within cell; cells that disagree are indistinguishable
    "compare_within_cell": {"simpson": "indistinguishable", "cells_disagree": "indistinguishable", "cells_agree": "better"},
    # D30: two run_config values of one pipeline_version are two cohorts; a suffixed or marker stamp forms none
    "cohorts": {"V@rcA vs V@rcB": "worse", "V vs V@rcA": "indistinguishable", "V@rcA vs V+untracked": "ValueError",
                "V@rcA vs unknown": "ValueError", "V@rcA vs V@ambiguous": "ValueError"},
    "cohorts_formed": {"V@rcA": 200, "V@rcB": 200, "V": 50, "no cohort": 100},
    # D39: proven from the decidable gates with G1-G3 unmeasured; a false gate refutes; unset or no row, unproven;
    # D56: PBO "insufficient" on a GENERATED alpha is not applicable (proven, pbo_pass listed); any other status, or a
    # library alpha, stays unmeasured
    "generated_alpha": {"gen_every_decidable_gate_true": "proven", "gen_g5_false": "refuted", "gen_g6_unset": "unproven",
                        "gen_no_meaning_row": "unproven", "gen_row_scored_after_the_clock": "unproven",
                        "library_composite": "proven", "gen_pbo_insufficient": "proven", "gen_pbo_pending": "unproven",
                        "library_pbo_insufficient": "unproven"},
    "generated_alpha_not_applicable": {"gen_pbo_insufficient": ["pbo_pass"], "gen_pbo_pending": [],
                                       "library_pbo_insufficient": []},
    # D45: rc1 whole days only; a changed day excluded; no log, unknown
    "run_config_exposure": {"V@r1": [6, True], "V@r1, no log read": [None, False], "V, no run_config": [10, True]},
    # D47 as D54 / D55 / D60 decide it: the round the unit, within day; looks at 7/14/21/28 shared days with O'Brien-
    # Fleming boundaries and a stop at the first crossing whose cells agree; only randomiser rounds; fresh draws in B
    "compare_arms": {"placebo_day_heterogeneous": "withheld", "within_day_effect": "better",
                     "look_outside_the_boundary": "withheld", "cells_disagree": "withheld", "six_shared_days": "withheld",
                     "seven_shared_days": "withheld", "no_effect_30_shared_days": "indistinguishable",
                     "explicit_rounds_excluded": "withheld", "neighbour_and_repair_rows_beside": "withheld",
                     "events_cluster_in_rounds": "withheld", "older_ab_arms_only": "no-data"},
    # D55: how many looks each read took -- none before 7 shared days, a stop at the crossing, at most four
    "compare_arms_looks": {"six_shared_days": 0, "seven_shared_days": 1, "within_day_effect": 2,
                           "look_outside_the_boundary": 2, "no_effect_30_shared_days": 4},
    # D60: every round outside the randomiser is excluded and counted, a round under two reasons once
    "compare_arms_excluded_rounds": {"explicit_rounds_excluded": 45, "older_ab_arms_only": 28,
                                     "neighbour_and_repair_rows_beside": 0},
    # D57: level 1 at the shorter post-creation exposure; a card without lags makes both raw
    "rank_equal_exposure": {"graded_2026-10-06": 0, "graded_2026-10-30_copy_cut_2026-10-06": 0,
                            "older_recorded_before_d57": -1},
    # D49: level 1 counts the late POSTs; credit does not
    "post_horizon_graded_2026-09-25": {"rank_level_1": 6, "submissions": 4},
}
#: Outcomes the truth table pins AS THE SCORER DECIDES THEM, which no tick settles (draw4_build ci 8(d)): the
#: scoring engineers' readings, each printed by the scorer as open for Khoa or stated in its docstring. Pinned
#: so they cannot move unseen; NOT endorsed.
READINGS_LITERAL = {
    # D28 as read by compare(): a cell with an event that one arm never scored in has no direction
    "compare_within_cell": {"a_cell_one_arm_never_scored": "indistinguishable"},
    # round 3 S8 as read by meaning_index(): a malformed gate value is not a pass; a row of another formula's sha
    # and a row scored before the alpha existed are ignored; the earliest row decides, a tie by file order
    "generated_alpha": {"gen_malformed_gate_value": "unproven", "gen_only_another_formulas_row": "unproven",
                        "gen_another_formulas_row_beside_its_own": "refuted", "gen_row_scored_before_creation": "unproven",
                        "gen_earliest_row_decides": "refuted", "gen_tie_first_in_file_decides": "refuted"},
    # tools/deploy.py WATCH ROWS as read by live_days() and dora() (draw4_build scoring 1): the live days follow
    # the ledger's written contract; that watch_not_rolled_back is a change failure is dora()'s stated reading
    "watch_rows": {"live_days": {"V": ["2026-09-10", "2026-09-11", "2026-09-13", "2026-09-14"], "W": [],
                                 "X": ["2026-09-16", "2026-09-17"], "Y": []},
                   "dora": {"status": "measured", "deploys": 4, "deploys_per_week": 1.0, "change_failure_rate": 0.5,
                            "time_to_restore_hours_median": 71.0}},
    # draw-5 ci 12: cohort_live_days' reading of D45 (its docstring: THIS MODULE'S READING), not a tick -- a cohort's
    # days before its first log row do not make its card's exposure unknown when some days are known
    "run_config_exposure": {"V@r2": [2, True]},
    # D55 as read by compare_arms (benchmark ARMS_LOOK_DAYS: "THIS MODULE'S READING of 'every 7 days', open for
    # Khoa"): looks count SHARED days, so days only one arm ran spend no look
    "compare_arms": {"shared_days_not_calendar_days": "better"},
}


@pytest.mark.parametrize("which", ["this scorer", "the committed golden card"])
def test_the_floors_their_semantics_and_the_rank_order_are_pinned_as_literals(which):
    card = _live_card() if which == "this scorer" else json.loads(G.GOLDEN.read_text())
    assert card["constants"]["FLOOR"] == FLOOR_LITERAL
    assert card["constants"]["RANK_ORDER"] == RANK_ORDER_LITERAL
    for k, v in DECISION_CONSTANTS_LITERAL.items():
        assert card["constants"][k] == v, k
    assert {k: [v["verdict"], v["floors_unmet"]] for k, v in card["cases"]["floors"].items()} == FLOOR_SEMANTICS_LITERAL
    assert card["cases"]["rank"]["best_first"] == BEST_FIRST_LITERAL
    assert card["cases"]["rank"]["rank_key_agrees_with_rank_cmp"] is True
    c = card["cases"]

    def refusal_or(v):
        """A refusal by its exception's name, anything else as it is."""
        return v.split(":")[0] if isinstance(v, str) else v
    assert {k: refusal_or(v["rank_key"] if isinstance(v, dict) else v)
            for k, v in c["rank_open_horizon"].items()} == DECISIONS_LITERAL["rank_open_horizon"]
    assert c["verdict_leads_rank"]["best_first"] == DECISIONS_LITERAL["verdict_leads_rank"]
    assert {k: v["verdict"] for k, v in c["compare_within_cell"].items()} == dict(
        DECISIONS_LITERAL["compare_within_cell"], **READINGS_LITERAL["compare_within_cell"])
    assert {k: refusal_or(v) if isinstance(v, str) else v["verdict"]
            for k, v in c["cohorts"]["compare"].items()} == DECISIONS_LITERAL["cohorts"]
    assert c["cohorts"]["rows_per_cohort"] == DECISIONS_LITERAL["cohorts_formed"]
    read = c["generated_alpha"]["ledger_read"]
    assert {a: v["status"] for a, v in read.items()} == dict(DECISIONS_LITERAL["generated_alpha"],
                                                            **READINGS_LITERAL["generated_alpha"])
    assert all("not applicable" in v["g1_g3"] for a, v in read.items() if a.startswith("gen_"))
    assert {a: read[a]["not_applicable"] for a in DECISIONS_LITERAL["generated_alpha_not_applicable"]} == \
        DECISIONS_LITERAL["generated_alpha_not_applicable"]
    assert {v["status"] for a, v in c["generated_alpha"]["ledger_not_read"].items() if a.startswith("gen_")} == {"unproven"}
    assert {k: [v["quota_days"], v["exposure"]["known"]] for k, v in c["run_config_exposure"].items()} == \
        dict(DECISIONS_LITERAL["run_config_exposure"], **READINGS_LITERAL["run_config_exposure"])
    arms = c["compare_arms"]
    assert {k: v["verdict"] for k, v in arms.items()} == dict(DECISIONS_LITERAL["compare_arms"],
                                                              **READINGS_LITERAL["compare_arms"])
    assert {k: len(arms[k]["looks"]) for k in DECISIONS_LITERAL["compare_arms_looks"]} == DECISIONS_LITERAL["compare_arms_looks"]
    assert {k: arms[k]["excluded"]["rounds"] for k in DECISIONS_LITERAL["compare_arms_excluded_rounds"]} == \
        DECISIONS_LITERAL["compare_arms_excluded_rounds"]
    assert {k: v["rank_cmp_newer_vs_older"] for k, v in c["rank_equal_exposure"].items()} == \
        DECISIONS_LITERAL["rank_equal_exposure"]
    late = c["post_horizon"]["graded_2026-09-25"]
    assert {k: late[k] for k in ("rank_level_1", "submissions")} == DECISIONS_LITERAL["post_horizon_graded_2026-09-25"]
    assert c["watch_rows"] == READINGS_LITERAL["watch_rows"]
    tree = card["cases"]["axis3_tree"]
    assert [tree["healthy"]["held"], tree["healthy"]["of"], tree["healthy"]["floor_met"]] == [7, 7, True]
    assert tree["broken"]["floor_met"] is False


def test_the_golden_carries_the_scorer_hash_so_an_edit_no_case_reaches_still_blocks(tmp_path):
    """S8-NL: the golden carried no scorer hash, so an edit that reached no case passed silently. The hash
    is re-derived here independently of the fixture, from the file's bytes."""
    golden = json.loads(G.GOLDEN.read_text())
    assert golden["scorer_sha256"] == hashlib.sha256((ROOT / "forge/offline/benchmark.py").read_bytes()).hexdigest()
    assert golden["fixture_sha256"] == hashlib.sha256((ROOT / "tools/ci_fixture.py").read_bytes()).hexdigest()
    assert golden["scorer_closure"] == {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
                                        for rel in golden["scorer_closure"]}
    golden["scorer_sha256"] = "0" * 64                  # a scorer edit whose decisions all stayed the same
    fake = tmp_path / "golden.json"
    fake.write_text(json.dumps(golden))
    r = G.check_pinned_scorer(golden_path=fake)
    assert r["ok"] is False and "scorer_sha256" in r["summary"]


# ------------------------------------------------------------------------------ SERIOUS 3: the whole scorer
def test_an_edit_to_a_module_the_scorer_imports_blocks_and_is_named(tmp_path):
    """Draw-3 ci SERIOUS 3: the edit corr_lines ("PROD_CORRELATION", "SELF_CORRELATION") -> ("PROD_CORRELATION",
    "PROD_CORRELATION") in forge/submit.py changed no case and no hash, so check_pinned_scorer read ok=True.
    The golden now pins every file of the scorer's import closure; a submit.py whose bytes moved is named."""
    golden = json.loads(G.GOLDEN.read_text())
    for rel in ("forge/submit.py", "forge/hypotheses.py", "fingerprint.py", "forge/harvest.py", "forge/standard.py"):
        assert rel in golden["scorer_closure"], rel                      # the files the audit named
    golden["scorer_closure"]["forge/submit.py"] = "0" * 64
    fake = tmp_path / "golden.json"
    fake.write_text(json.dumps(golden))
    r = G.check_pinned_scorer(golden_path=fake)
    assert r["ok"] is False and "scorer_closure.forge/submit.py" in r["summary"]


def test_the_import_closure_is_found_by_the_syntax_tree_with_the_roots_it_derives(tmp_path):
    """SERIOUS 3: the closure is derived, never listed. Module-level and deferred imports, a relative import,
    a package's __init__.py, a tools/ module, and a module found only because a file in the closure put its
    directory on sys.path (the way harness13/massgen/mg/simulate.py reaches tools/funnel/gate_lib.py); a
    stdlib or installed name and a file nothing imports are not in it."""
    files = {
        "forge/__init__.py": "",
        "forge/offline/benchmark.py": "import json\nimport yaml\nfrom forge import harvest as HV\n\n"
                                      "def f():\n    import fingerprint\n    from forge.standard import gates\n",
        "forge/harvest.py": "import pathlib, sys\nROOT = pathlib.Path(__file__).resolve().parents[1]\n"
                            "sys.path.insert(0, str(ROOT / 'tools'))\nfrom forge import dsr\n\ndef g():\n    import layered_sim\n",
        "forge/dsr.py": "X = 1\n",
        "forge/standard.py": "from . import dsr\n\ngates = 1\n",
        "forge/unused.py": "X = 2\n",
        "fingerprint.py": "from operators import ops\n",
        "operators.py": "ops = 1\n",
        # `d` is bound differently in two functions; only h's binding reaches h's sys.path line (MEASURED
        # 2026-09-23 on tools/layered_alpha.py, where _render_gate()'s `d` was read file-wide as the state/layered
        # pool directory load_screens() binds to `d`; draw4_build ci 8(e): this cited both by line number)
        "tools/layered_sim.py": "import pathlib, sys\nPOOL = pathlib.Path(__file__).parent / 'pool'\n\n"
                                "def pool():\n    d = POOL\n    return d\n\n"
                                "def h():\n    d = str(pathlib.Path(__file__).resolve().parent / 'funnel')\n"
                                "    for _p in (d,):\n        sys.path.append(_p)\n    import gate_lib\n",
        "tools/funnel/gate_lib.py": "",
        "tools/not_imported.py": "",
    }
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body)
    c = F.import_closure(root=tmp_path)
    assert c["files"] == sorted(set(files) - {"forge/unused.py", "tools/not_imported.py"})
    assert c["import_roots"] == [".", "tools", "tools/funnel"] and c["unread"] == []
    (tmp_path / "tools/layered_sim.py").write_text("import sys\n\ndef h(p):\n    sys.path.insert(0, p)\n")
    assert F.import_closure(root=tmp_path)["unread"] == ["tools/layered_sim.py:4"]      # named, never guessed


def test_the_closure_follows_every_sys_path_form_and_relative_imports(tmp_path):
    """Draw3_fix ci 7 (fails OPEN): `sys.path += [...]`, `sys.path = [...] + sys.path` and `from sys import path;
    path.insert(...)` each left a module out of the closure with nothing unread, and `self.path.append(...)`
    came out as a bogus unread entry. Draw3_fix ci 6: with `sys.path[...] = [...]` unread, or relative imports
    skipped, the closure test above still passed -- here a module is reachable ONLY through each form, so
    each is held. A write to sys.path the walk cannot evaluate is named, never guessed."""
    files = {
        "forge/__init__.py": "",
        "forge/offline/benchmark.py": "from forge import paths\nfrom . import sibling\nfrom ..lvl2 import z\n",
        "forge/offline/sibling.py": "",
        "forge/lvl2.py": "z = 1\n",
        "forge/paths.py": ("import pathlib, sys\nfrom sys import path as SP\n"
                           "HERE = pathlib.Path(__file__).resolve().parent\n"
                           "sys.path[:0] = [str(HERE / 'slice_dir')]\n"
                           "sys.path += [str(HERE / 'aug_dir')]\n"
                           "sys.path = [str(HERE / 'concat_dir')] + sys.path\n"
                           "SP.insert(0, str(HERE / 'alias_dir'))\n\n\n"
                           "class K:\n    def f(self):\n        self.path.append('nowhere')\n\n\n"
                           "import slicemod, augmod, concatmod, aliasmod\n"),
        **{"forge/%s_dir/%smod.py" % (k, k): "" for k in ("slice", "aug", "concat", "alias")},
    }
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body)
    c = F.import_closure(root=tmp_path)
    assert c["files"] == sorted(files) and c["unread"] == []
    assert c["import_roots"] == [".", "forge/alias_dir", "forge/aug_dir", "forge/concat_dir", "forge/slice_dir"]
    (tmp_path / "forge/paths.py").write_text("import sys\nsys.path = compute()\nsys.path.__iadd__(more)\n")
    assert F.import_closure(root=tmp_path)["unread"] == ["forge/paths.py:2", "forge/paths.py:3"]
    assert F.import_closure(["forge/lvl2.py", "forge/offline/sibling.py"], root=tmp_path)["files"] == \
        ["forge/lvl2.py", "forge/offline/sibling.py"]                   # several entries, one walk


def test_the_real_closure_reads_every_sys_path_entry_and_reproduces_in_the_ci_checkout():
    """SERIOUS 3, on the real tree. Every sys.path entry of the closure is read (else a module could hide
    behind an entry the walk did not understand); every file of it is inside tools/ci_publish.py's SUBSET, so
    the CI checkout holds it and the golden reproduces there; and every repository module the interpreter
    ACTUALLY loads while scoring the truth table is in the closure -- the static walk re-derived a second way."""
    import ci_publish as P
    c = F.import_closure()
    assert c["unread"] == []
    assert [f for f in c["files"] if not any(f == s or f.startswith(s + "/") for s in P.SUBSET)] == []
    # draw3_fix ci 8: inside SUBSET is not enough -- sync() must also COPY it (EXCLUDE drops caches and staged/)
    assert [f for f in c["files"] if not P._synced(f)] == []
    code = ("import sys, json, pathlib; sys.path[:0] = [%r, %r]; import ci_fixture as F; F.card(); root = pathlib.Path(%r).resolve();"
            "print(json.dumps(sorted(pathlib.Path(m.__file__).resolve().relative_to(root).as_posix() for m in list(sys.modules.values())"
            " if getattr(m, '__file__', None) and pathlib.Path(m.__file__).resolve().is_relative_to(root))))"
            % (str(ROOT), str(ROOT / "tools"), str(ROOT)))
    loaded = set(json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                                           cwd=str(ROOT)).stdout.strip().splitlines()[-1])) - {"tools/ci_fixture.py"}
    assert loaded and loaded <= set(c["files"]), sorted(loaded - set(c["files"]))


@pytest.mark.parametrize("rel, old, new, key", [
    (BENCH, "MDR_MAX_EVENTS = 1000", "MDR_MAX_EVENTS = 999", "constants.MDR_MAX_EVENTS"),
    (BENCH, "MDR_MAX_RATIO = 1e4", "MDR_MAX_RATIO = 1e3", "constants.MDR_MAX_RATIO"),
    (BENCH, '"not_the_submission_count": "this is NOT the submission count: a submission also needs the "',
     '"not_the_submission_count": "a submission needs the "', "constants.ESTIMAND.not_the_submission_count"),
])
def test_the_constants_no_case_reaches_are_pinned_by_name(rel, old, new, key, monkeypatch):
    """Draw-3 ci SERIOUS 4: MDR_MAX_* and ESTIMAND["not_the_submission_count"] were missing from the card, and
    no case reaches them (no case comes near 1,000 expected events; no decision reads the text). They are
    pinned by name: an edit moves the card's `constants` -- and only that, which is why the MUTANTS test,
    which asks for a moved CASE, cannot hold them."""
    real = _live_card()
    src = (ROOT / rel).read_text()
    assert src.count(old) == 1
    _swap_in(monkeypatch, rel, src.replace(old, new))
    assert [d.split(":")[0] for d in G._diff(real, F.card())] == [key]


def test_record_refusal_reads_the_same_scorer_the_gate_compares(cached_card):
    """SERIOUS 3: record_refusal compared benchmark.py's hash alone, so a forge/submit.py edit and a fixture
    edit recorded as one diff. Now: any closure file moved AND the fixture moved -> refused, naming the file;
    either alone -> recorded. A golden from before the closure is compared on benchmark.py's hash."""
    g = json.loads(json.dumps(cached_card))
    g["scorer_closure"]["forge/submit.py"] = "a" * 64
    assert G.record_refusal(dict(g), cached_card) is None                                   # scorer alone
    g["fixture_sha256"] = "b" * 64
    why = G.record_refusal(g, cached_card)
    assert why and "forge/submit.py" in why and "commit the scorer change first" in why.lower()
    fixture_only = dict(json.loads(json.dumps(cached_card)), fixture_sha256="b" * 64)
    assert G.record_refusal(fixture_only, cached_card) is None
    legacy = dict(fixture_only)
    del legacy["scorer_closure"]
    assert G.record_refusal(legacy, cached_card) is None                                    # same benchmark.py
    assert G.record_refusal(dict(legacy, scorer_sha256="c" * 64), cached_card) is not None


# ------------------------------------------------------------------------------ S8-NL: the re-record
@pytest.fixture
def cached_card(monkeypatch):
    card = json.loads(json.dumps(_live_card()))
    monkeypatch.setattr(G, "_fixture_card", lambda root=G.ROOT: (json.loads(json.dumps(card)), None))
    return card


def _golden_like(card, tmp_path, **changes):
    g = json.loads(json.dumps(card))
    for k, v in changes.items():
        g[k] = v
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(g, indent=1, sort_keys=True) + "\n")
    return p


def test_record_golden_prints_a_unified_diff_before_it_writes(tmp_path, cached_card):
    """S8-NL: --record-golden wrote the new card and printed it, with no diff."""
    old = json.loads(json.dumps(cached_card))
    old["cases"]["floors"]["three_proven_in_one_day"]["verdict"] = "PASS"   # the judgement the scorer moves
    path = _golden_like(old, tmp_path)
    seen = []
    r = G.record_golden(golden_path=path, out=lambda s: seen.append((s, path.read_text())))
    diff, on_disk_when_printed = seen[0]
    assert diff.startswith("--- golden.json (committed)") and '-    "verdict": "PASS"' in diff and '+    "verdict": "FAIL"' in diff
    assert json.loads(on_disk_when_printed) == old                           # printed BEFORE the write
    assert r["written"] is True and json.loads(path.read_text()) == cached_card


def test_record_golden_refuses_when_the_scorer_and_the_fixture_both_changed(tmp_path, cached_card):
    """S8-NL: cac48d7 changed the scorer, the fixture and the golden in one commit. Both hashes moved since
    the golden was recorded means the diff mixes two causes: refuse, and say to commit the scorer first."""
    both = _golden_like(cached_card, tmp_path, scorer_sha256="a" * 64, fixture_sha256="b" * 64)
    before = both.read_text()
    seen = []
    r = G.record_golden(golden_path=both, out=seen.append)
    assert r["written"] is False and "commit the scorer change first" in r["refused"].lower()
    assert both.read_text() == before and seen[0].startswith("---")          # the diff is still shown
    for moved in ({"scorer_sha256": "a" * 64}, {"fixture_sha256": "b" * 64}):
        assert G.record_golden(golden_path=_golden_like(cached_card, tmp_path, **moved), out=lambda s: None)["written"]


def test_a_golden_that_predates_the_hashes_is_recorded_once_and_then_guarded(tmp_path, cached_card):
    legacy = json.loads(json.dumps(cached_card))
    del legacy["scorer_sha256"], legacy["fixture_sha256"]
    path = _golden_like(legacy, tmp_path)
    seen = []
    assert G.record_golden(golden_path=path, out=seen.append)["written"] is True
    assert any("predates the recorded scorer and fixture hashes" in s for s in seen)
    assert G.record_refusal(json.loads(path.read_text()), dict(cached_card, scorer_sha256="c" * 64,
                                                                fixture_sha256="d" * 64)) is not None


# ------------------------------------------------------------------------------ A8: the known red
D23 = "tools/tests/test_layered.py::test_the_model_names_the_operator_the_platform_named"
D23_TEXT = "AssertionError: 20 journalled warnings the model would not have prevented\nassert 20 == 0"


def test_the_committed_allowance_is_d23s_one_node_id_and_its_failure_text():
    """A8 / D23: one exact node id with its expected failure, in a committed file -- never the
    classification's "red" list, which a re-classification rewrites."""
    assert [(t["node_id"], t["expected_failure"]) for t in G.known_red()] == [(D23, "20 journalled warnings")]


def _result(failures, rc=1, counted=None, stale=None):
    """A failed tests check shaped as check_tests builds it: `incomplete` present and empty (draw4_build ci 3)."""
    return {"name": "tests", "ok": False, "returncode": rc, "failures": [list(f) for f in failures],
            "counted": len(failures) if counted is None else counted, "stale": stale, "incomplete": []}


def test_only_the_listed_node_failing_the_listed_way_is_allowed():
    """A8, round 2's three measured routes: (1) a NEW failure beside the known one; (2) the known test
    failing differently ("54 journalled" instead of "20"); (3) re-classification putting the new failure
    into "red" -- the verdict never reads the classification, so that route no longer exists."""
    ok = G.known_red_verdict(_result([(D23, D23_TEXT)]))
    assert ok["ok"] is True and ok["allowed"] == [D23]
    new = G.known_red_verdict(_result([(D23, D23_TEXT), ("forge/tests/test_submit.py::test_something_new", "boom")]))
    assert new["ok"] is False and new["allowed"] == [] and any("test_something_new -- NEW" in b for b in new["blocking"])
    for other in ("AssertionError: 54 journalled warnings the model would not have prevented",
                  "AssertionError: 120 journalled warnings the model would not have prevented",   # substring trap
                  "AssertionError: the corpus should carry at least the 19 known warning rows, saw 3", ""):
        v = G.known_red_verdict(_result([(D23, other)]))
        assert v["ok"] is False and "failing DIFFERENTLY" in v["blocking"][0], other


def test_a_broken_run_or_a_miscounted_summary_is_never_a_known_red():
    """A8 / m5: the old allowance read a 12-line cap and never compared it with pytest's own count."""
    assert G.known_red_verdict(_result([(D23, D23_TEXT)], rc=2))["ok"] is False         # interrupted
    assert G.known_red_verdict(_result([(D23, D23_TEXT)], counted=2))["ok"] is False    # a failure unread
    assert G.known_red_verdict(_result([]))["ok"] is False                              # nothing read at all
    assert G.known_red_verdict(_result([(D23, D23_TEXT)], stale="moved"))["ok"] is False
    bad = G.known_red_verdict(_result([(D23, D23_TEXT)]), root=Path("/nonexistent"))   # no committed file
    assert bad["ok"] is False and "unreadable" in bad["blocking"][0]


def test_a_result_that_carries_no_incomplete_reading_is_never_a_known_red():
    """Draw4_build ci 3 (fails open, latent): known_red_verdict returned ok=True on a result with no `incomplete`
    key, while the same dict without `counted` blocked. That every collected test ran is shown by the reading;
    its absence shows nothing. Draw-5 ci 3 (REPRODUCED by the adjudicator): `incomplete: None` read as complete;
    anything that is not a list blocks."""
    whole = _result([(D23, D23_TEXT)])
    assert G.known_red_verdict(whole)["ok"] is True                                   # the control
    absent = {k: v for k, v in whole.items() if k != "incomplete"}
    for bad in (absent, dict(whole, incomplete=None), dict(whole, incomplete="")):
        v = G.known_red_verdict(bad)
        assert v["ok"] is False and v["allowed"] == [] and any("no `incomplete` list" in b for b in v["blocking"]), bad
    assert G.known_red_verdict(dict(whole, incomplete=["x"]))["ok"] is False


def test_the_hermetic_tier_blocks_on_the_committed_list_and_on_any_unlisted_measured_red(tmp_path):
    """D23 + A8: a hosted runner cannot run the known-red test, so the committed list blocks in its place;
    a test the classification measured red but the list does not name blocks too (until Khoa ticks it),
    and a missing list fails closed."""
    listed = G.check_known_red(_root(tmp_path / "a", known=[{"node_id": D23, "expected_failure": "20 journalled warnings"}],
                                     classification={"red": [D23]}))
    assert listed["ok"] is False and D23 in listed["summary"] and "NOT in" not in listed["summary"]
    unlisted = G.check_known_red(_root(tmp_path / "b", known=[], classification={"red": ["t/x.py::test_y"]}))
    assert unlisted["ok"] is False and "NOT in tools/ci_known_red.json" in unlisted["summary"] and "test_y" in unlisted["summary"]
    assert G.check_known_red(_root(tmp_path / "c", known=[], classification={"red": []}))["ok"] is True
    missing = G.check_known_red(_root(tmp_path / "d", classification={"red": []}))
    assert missing["ok"] is False and "unreadable" in missing["summary"]


_LONG = "test_the_model_names_the_operator_the_platform_named_in_every_journalled_warning_row"


def _suite(tmp_path, errors=0):
    """A tiny real suite: one failure shaped like D23's (a node id well over 80 columns), plus `errors`
    tests that ERROR at setup, which do not interrupt the run the way an import error would."""
    t = tmp_path / "forge/tests"
    t.mkdir(parents=True)
    (tmp_path / "tools/tests").mkdir(parents=True)
    (t / "test_known.py").write_text(
        "def %s():\n    miss = 20\n    assert miss == 0, '%%d journalled warnings the model would not have prevented' %% miss\n" % _LONG)
    if errors:
        (t / "test_errors.py").write_text(
            "import pytest\n\n@pytest.fixture\ndef broken():\n    raise ImportError('no module named x')\n\n"
            + "".join("def test_e%02d(broken):\n    pass\n\n" % i for i in range(errors)))
    return "forge/tests/test_known.py::" + _LONG


def test_the_real_summary_carries_the_failure_text_and_is_read_whole(tmp_path):
    """A8 + m5, through a REAL pytest run: the summary line of an 80-plus-column node id carries its text
    only because the gate runs pytest with CI=true (MEASURED: without it the line is the node id alone), and
    twelve setup ERRORs before the known failure are all read -- the old 12-line cap let new ones through."""
    node = _suite(tmp_path / "one")
    only = G.check_tests(hermetic_only=False, root=tmp_path / "one")
    assert only["ok"] is False and only["returncode"] == 1 and only["counted"] == 1
    assert only["failures"][0][0] == node and "20 journalled warnings" in only["failures"][0][1]
    known = [{"node_id": node, "expected_failure": "20 journalled warnings"}]
    assert G.known_red_verdict(only, known=known)["ok"] is True
    _suite(tmp_path / "many", errors=12)
    many = G.check_tests(hermetic_only=False, root=tmp_path / "many")
    assert many["counted"] == 13 and len(many["failures"]) == 13
    v = G.known_red_verdict(many, known=known)
    assert v["ok"] is False and sum("NEW" in b for b in v["blocking"]) == 12


# ------------------------------------------------------------------------------ draw3_fix ci 2: a truncated run
def _known_then_new(tmp_path, conftest=None, ini=None, plugin=None):
    """The adjudicator's adjci_xprobe.py suite: the known failure first, a NEW failure after it (the module
    names sort that way), so a run that stops early or selects by name reads the known failure alone."""
    node = _suite(tmp_path)
    (tmp_path / "forge/tests/test_zz_new.py").write_text("def test_zz_new():\n    assert 0, 'boom'\n")
    for name, body in (("conftest.py", conftest), ("pytest.ini", ini), ("truncating_plugin.py", plugin)):
        if body:
            (tmp_path / name).write_text(body)
    return [{"node_id": node, "expected_failure": "20 journalled warnings"}]


@pytest.mark.parametrize("var, value", [("PYTEST_ADDOPTS", "-x"), ("PYTEST_ADDOPTS", "--maxfail=1"),
                                        ("PYTEST_ADDOPTS", "-k known"), ("PYTEST_PLUGINS", "truncating_plugin"),
                                        ("PY_COLORS", "1")])
def test_the_environment_cannot_shorten_the_run_or_hide_its_summary(tmp_path, monkeypatch, var, value):
    """Draw3_fix ci 2: under PYTEST_ADDOPTS=-x, --maxfail=1 and -k known pytest exited 1 with the known failure
    alone, and the verdict allowed it while the NEW failure never ran; PYTEST_PLUGINS can load code that does
    the same (here a plugin setting maxfail); under PY_COLORS=1 no entry of the summary could be read. The
    gate's pytest runs without the first two and with PY_COLORS=0: BOTH failures are read and the NEW one
    blocks."""
    known = _known_then_new(tmp_path, plugin="def pytest_configure(config):\n    config.option.maxfail = 1\n")
    monkeypatch.setenv(var, value)
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert r["counted"] == 2 and len(r["failures"]) == 2 and r["incomplete"] == [], (r["summary"], r["incomplete"])
    v = G.known_red_verdict(r, known=known)
    assert v["ok"] is False and any("test_zz_new -- NEW" in b for b in v["blocking"])


def test_an_ini_files_addopts_cannot_shorten_the_run(tmp_path):
    """Draw3_fix ci 2: `-o addopts=` empties an ini file's addopts (there is no ini in this repository today)."""
    known = _known_then_new(tmp_path, ini="[pytest]\naddopts = -x\n")
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert r["counted"] == 2 and r["incomplete"] == [] and G.known_red_verdict(r, known=known)["ok"] is False


@pytest.mark.parametrize("how, conftest, says", [
    ("maxfail set in code", "def pytest_configure(config):\n    config.option.maxfail = 1\n", "stopping after 1 failures"),
    ("deselected in a hook", "def pytest_collection_modifyitems(config, items):\n"
                             "    gone = [i for i in items if 'zz_new' in i.nodeid]\n"
                             "    config.hook.pytest_deselected(items=gone)\n"
                             "    items[:] = [i for i in items if i not in gone]\n", "1 test(s) deselected, the gate asked for 0"),
    ("dropped in a hook", "def pytest_collection_modifyitems(config, items):\n"
                          "    items[:] = [i for i in items if 'zz_new' not in i.nodeid]\n", "collected 2 and its last line accounts for 1"),
])
def test_a_run_the_tree_itself_shortens_is_never_a_known_red(tmp_path, how, conftest, says):
    """Draw3_fix ci 2, the output half: the environment is not the only way to run part of the suite -- code
    in the tree can (a conftest). When a conftest shortens the run of what pytest COLLECTED, the output says so
    -- a banner, a deselected count the gate did not ask for, fewer outcomes than tests collected -- and the
    known-red verdict refuses. Draw4_build ci 2: this said "whatever shortened it"; narrowing what is COLLECTED
    leaves no trace in the output and is read from the conftests instead (the collect_ignore test below)."""
    known = _known_then_new(tmp_path, conftest=conftest)
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert r["counted"] == 1 and any(says in w for w in r["incomplete"]), r["incomplete"]
    v = G.known_red_verdict(r, known=known)
    assert v["ok"] is False and any("not the whole suite" in b for b in v["blocking"])
    assert G.known_red_verdict(dict(r, incomplete=[]), known=known)["ok"] is True       # the control: only that


def test_a_shortened_run_that_exits_0_is_not_a_pass(tmp_path):
    """Draw3_fix ci 2: dropping the only failing test exits 0; `ok` read the exit code alone."""
    _known_then_new(tmp_path, conftest="def pytest_collection_modifyitems(config, items):\n"
                                       "    items[:] = [i for i in items if 'known' not in i.nodeid and 'zz_new' not in i.nodeid]\n")
    (tmp_path / "forge/tests/test_ok.py").write_text("def test_ok():\n    pass\n")
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert r["returncode"] == 0 and r["ok"] is False and "NOT THE WHOLE SUITE" in r["summary"]


@pytest.mark.parametrize("template, passes", [
    ("cd /opt/wq && %s SUBMITFLAG", True), ("a; %s LIVEFLAG", True), ("x | %s LIVEFLAG", True),     # draw3_fix ci 4
    ("timeout 600 %s LIVEFLAG", True), ("env A=1 B=2 %s SUBMITFLAG", True), ("nohup %s LIVEFLAG", True),
    ("%(script)s LIVEFLAG", True), ("{} SUBMITFLAG --cap 4", True),
    ("no file under %s passes LIVEFLAG", False),                    # prose: its command word is "no"
    ("nothing reachable from CI passes LIVEFLAG or SUBMITFLAG (%s)", False),   # this file's own summary; "(" is no separator
    ("cd /opt/wq\n%s SUBMITFLAG", True), ("nice -n 5 %s LIVEFLAG", True),          # draw4_build ci 6
    ("timeout -s KILL 60 %s LIVEFLAG", True), ("sudo -u wq %s SUBMITFLAG", True),
    ("{} alphas staged; pass SUBMITFLAG to post them", False),       # draw4_build ci 7: the flag is in another command
    ("{} alphas staged; {} SUBMITFLAG", True),                       # the control: there it is the command's own
    ("%s \\\n  SUBMITFLAG --cap 4", True),                           # draw-5 ci 6: a line continuation joins
])
def test_a_template_passes_the_flag_only_when_a_command_word_is_its_placeholder(template, passes):
    """Draw3_fix ci 4: _TEMPLATE_COMMAND read a command word at the start only; it now reads one after && || ;
    | &, behind timeout N and env VAR=value. MEASURED 2026-09-23: with "(" as a separator the gate's own
    summary line was flagged, so "(" is not one. Draw4_build ci 6: a newline separates commands, and nice -n N,
    timeout -s SIG and sudo -u USER are read with their option arguments. Draw4_build ci 7: the flag must be in
    the command whose word is the placeholder."""
    t = template.replace("LIVEFLAG", LIVE).replace("SUBMITFLAG", SUBMIT)      # assembled: see LIVE
    assert G._passes_in_argv(t, "template") is passes


@pytest.mark.parametrize("stdout, deselected, says", [
    ("collected 3 items\n\n=== 3 passed in 0.1s ===\n", 0, None),
    ("collected 2 items\n=== 1 passed, 1 error in 0.1s ===\n", 0, None),
    ("collected 1 item\n=== 1 passed, 1 error in 0.1s ===\n", 0, None),                  # a teardown error counts twice
    ("collected 3 items / 2 deselected / 1 selected\n=== 1 passed, 2 deselected in 0.1s ===\n", 2, None),
    ("collected 3 items / 2 deselected / 1 selected\n=== 1 passed, 2 deselected in 0.1s ===\n", 1, "deselected"),
    ("=== 3 passed in 0.1s ===\n", 0, "no 'collected N items' line"),
    ("collected 3 items\n!!!!!!! KeyboardInterrupt !!!!!!!\n=== 1 passed in 0.1s ===\n", 0, "KeyboardInterrupt"),
    # draw4_build ci 5: K2 (every outcome word is counted), K4 (only the LAST line is read), K5 (fewer deselected
    # than the gate asked for blocks too -- the test is `!=`)
    ("collected 5 items\n=== 1 passed, 2 skipped, 1 xfailed, 1 xpassed in 0.1s ===\n", 0, None),
    ("collected 3 items\na test printed: 1 failed earlier\n=== 2 passed in 0.1s ===\n", 0, "accounts for 2"),
    ("collected 3 items / 1 deselected / 2 selected\n=== 2 passed, 1 deselected in 0.1s ===\n", 2, "1 test(s) deselected, the gate asked for 2"),
])
def test_run_incomplete_reads_the_output_it_is_given(stdout, deselected, says):
    """Draw3_fix ci 2: the reading itself, second-derived on hand-written outputs of the forms pytest 9.1.1
    printed on the probe suites above; `deselected` is what the gate asked for (the hermetic tier's list)."""
    why = G.run_incomplete(stdout, deselected)
    assert (why == []) if says is None else any(says in w for w in why), why


# ------------------------------------------------------------------------------ S6-NL: a stale classification
def _v_lines(nodes, outcome="PASSED"):
    """One line per test as pytest -v prints it (check_tests runs -v since draw-5 ci 2)."""
    return "".join("%s %s [%3d%%]\n" % (n, outcome, 100 * (i + 1) // len(nodes)) for i, n in enumerate(nodes))


def _passing_run(monkeypatch):
    """A whole run as pytest -v prints it without -q: the "collected" line, a line per test, then the outcome line."""
    out = ("collecting ... collected 5 items\n\n" + _v_lines(["tools/tests/test_a.py::t%d" % i for i in range(5)])
           + "====== 5 passed in 0.1s ======\n")
    monkeypatch.setattr(G, "_run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=out, stderr=""))


def test_a_stale_classification_blocks_instead_of_warning(tmp_path, monkeypatch):
    """S6-NL: Actions run 35822646606 printed `[PASS] tests ... WARNING: tests or code changed since the
    classification` -- the hermetic tier skipped a list measured on other code and read green."""
    import ci_classify as CC
    _passing_run(monkeypatch)
    root = _root(tmp_path, classification={"tests_hash": "t", "code_version": "c", "deselect": [], "measured_at": "m"})
    monkeypatch.setattr(CC, "tests_hash", lambda root=None: "t-moved")
    monkeypatch.setattr(CC, "code_version", lambda root=None: "c")
    stale = G.check_tests(hermetic_only=True, root=root)
    assert stale["ok"] is False and "STALE" in stale["summary"] and stale["stale"]
    monkeypatch.setattr(CC, "tests_hash", lambda root=None: "t")
    assert G.check_tests(hermetic_only=True, root=root)["ok"] is True          # current: the run decides
    assert G.check_tests(hermetic_only=True, root=_root(tmp_path / "none"))["ok"] is False   # no classification


def test_the_hermetic_tiers_own_deselections_are_not_a_truncated_run(tmp_path, monkeypatch):
    """Draw3_fix ci 2: the hermetic tier deselects the classification's data-bound tests itself; those, and only
    as many as it asked for, are not a sign of a shortened run. One more deselected than asked blocks."""
    import ci_classify as CC
    monkeypatch.setattr(CC, "tests_hash", lambda root=None: "t")
    monkeypatch.setattr(CC, "code_version", lambda root=None: "c")
    root = _root(tmp_path, classification={"tests_hash": "t", "code_version": "c", "measured_at": "m",
                                           "deselect": ["tools/tests/test_a.py::t1", "tools/tests/test_a.py::t2"]})
    for k, ok in ((2, True), (3, False)):
        out = ("collecting ... collected 7 items / %d deselected / %d selected\n" % (k, 7 - k)
               + _v_lines(["tools/tests/test_b.py::t%d" % i for i in range(7 - k)])
               + "=== %d passed, %d deselected in 0.1s ===\n" % (7 - k, k))
        monkeypatch.setattr(G, "_run", lambda argv, out=out, **kw: subprocess.CompletedProcess(argv, 0, stdout=out, stderr=""))
        r = G.check_tests(hermetic_only=True, root=root)
        assert r["ok"] is ok and (r["incomplete"] == []) is ok, (k, r["incomplete"])


# ------------------------------------------------------------------------------ SERIOUS 7: one test per claim
def test_a_classification_that_cannot_be_verified_counts_as_stale(tmp_path, monkeypatch):
    """Draw-3 ci SERIOUS 7: check_tests says "unverifiable is stale: it blocks", and reverting the handler to
    `pass` left every test green. A hash that cannot be computed must never read as current."""
    import ci_classify as CC
    _passing_run(monkeypatch)
    root = _root(tmp_path, classification={"tests_hash": "t", "code_version": "c", "deselect": [], "measured_at": "m"})
    monkeypatch.setattr(CC, "tests_hash", lambda root=None: "t")

    def cannot(root=None):
        raise OSError("tools/deploy.py unreadable")
    monkeypatch.setattr(CC, "code_version", cannot)
    r = G.check_tests(hermetic_only=True, root=root)
    assert r["ok"] is False and "could not verify" in r["stale"] and "OSError" in r["stale"]


def test_a_failed_tests_check_carries_the_known_red_verdict_and_a_passed_one_none(tmp_path, monkeypatch):
    """SERIOUS 7: check_tests attaching known_red_verdict to a failure is what ci_publish's data_tier reads
    (and it treats a failure with no verdict as red); nothing tested that it is attached."""
    summary = ("collecting ... collected 4 items\n" + _v_lines(["tools/tests/test_a.py::t%d" % i for i in range(3)])
               + _v_lines([D23], "FAILED") + "=" * 20 + " short test summary info " + "=" * 20
               + "\nFAILED %s - %s\n1 failed, 3 passed in 0.10s\n" % (D23, D23_TEXT.split("\n")[0]))
    monkeypatch.setattr(G, "_run", lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout=summary, stderr=""))
    root = _root(tmp_path, known=[{"node_id": D23, "expected_failure": "20 journalled warnings"}])
    r = G.check_tests(hermetic_only=False, root=root)
    assert r["known_red"] == G.known_red_verdict({k: v for k, v in r.items() if k != "known_red"}, root=root)
    assert r["known_red"]["ok"] is True and r["known_red"]["allowed"] == [D23]
    _passing_run(monkeypatch)
    assert "known_red" not in G.check_tests(hermetic_only=False, root=root)


@pytest.mark.parametrize("bad, says", [
    ({"tests": {"node_id": D23, "expected_failure": "x"}}, "no 'tests' list"),                       # not a list
    ({"tests": [{"node_id": "tools/tests/test_layered.py", "expected_failure": "x"}]}, "not an exact pytest node id"),
    ({"tests": [{"node_id": D23, "expected_failure": "   "}]}, "names no expected failure text"),   # empty text
    ({"tests": [{"node_id": D23}]}, "names no expected failure text"),
    ({"tests": ["tools/x.py::t"]}, "is not an object"),                          # draw-3 ci MINOR: AttributeError
])
def test_a_malformed_known_red_list_raises_valueerror_and_every_caller_fails_closed(tmp_path, bad, says):
    """SERIOUS 7: known_red()'s `::` check, its list check and its empty-text check had no test. Each malformed
    list raises ValueError -- the one exception its callers catch -- and so allows nothing anywhere."""
    (tmp_path / "tools").mkdir()
    (tmp_path / G.KNOWN_RED).write_text(json.dumps(bad))
    with pytest.raises(ValueError, match=says):
        G.known_red(tmp_path)
    v = G.known_red_verdict(_result([(D23, D23_TEXT)]), root=tmp_path)
    assert v["ok"] is False and v["allowed"] == [] and "no allowance can apply" in v["blocking"][0]
    assert G.check_known_red(tmp_path)["ok"] is False                  # the hermetic tier: no data markers here


def test_an_exemption_covers_its_exact_line_only(tmp_path, monkeypatch):
    """SERIOUS 7: NO_LIVE_EXEMPT is keyed by path AND the exact stripped line; keyed by the path alone, a
    second line of the same file passing the flag walked through, and nothing tested it. Also: the exempt
    line EDITED is no longer exempt. The list is empty today, so the mechanism is held with an entry of the
    shape the notify_lint one had."""
    exempt_rel, exempt_line = "tools/lint_like.py", 'COMMAND_TOKENS = ("%s", "--override-root")' % SUBMIT
    monkeypatch.setattr(G, "NO_LIVE_EXEMPT", {(exempt_rel, exempt_line): "a membership list, for this test"})
    p = tmp_path / exempt_rel
    p.parent.mkdir(parents=True)
    p.write_text("%s\nrun([%r])\n" % (exempt_line, SUBMIT))
    assert G.check_no_live(tmp_path)["details"] == ["%s:2" % exempt_rel]
    p.write_text(exempt_line.replace(")", ', "--x")', 1) + "\n")
    assert G.check_no_live(tmp_path)["details"] == ["%s:1" % exempt_rel]


# ------------------------------------------------------------------------------ SERIOUS 2: the allowance's reader
def test_the_known_red_file_says_what_the_publish_path_does(monkeypatch):
    """Draw-3 ci SERIOUS 2: tools/ci_known_red.json and the KNOWN_RED comment said the list was "the ONLY
    allowance" while ci_publish.data_tier still allowed by the classification's red list. The claim is held
    true here with the REAL data_tier and the REAL verdict: a failure the classification calls red but the
    list does not name is red; the listed test failing as recorded is allowed and named; a failure that
    carries no verdict is red."""
    import ci_publish as P
    what = json.loads((ROOT / G.KNOWN_RED).read_text())["what"]
    assert "ONLY allowance" in what and "data_tier()" in what and "allows nothing" in what
    assert "every test pytest collected was reported once and counted" in what and "`incomplete`" in what  # draw3_fix ci 2
    assert "the run was the whole suite" not in what and "more tests deselected" not in what   # draw4_build ci 2, 8(a)
    assert "collect_ignore" in what and "installed plugin" in what                  # what it cannot see, named
    # draw-5 ci 1, 2 and 3: "ran" became "reported once and counted"; the ini claim, the list's reach and None
    assert "ran and was counted" not in what and "overridden with pytest's defaults" not in what
    assert "No ini file of the tree is read" in what and "not exhaustive" in what and "must be a list" in what
    monkeypatch.setattr(sys, "path", list(sys.path))               # data_tier inserts DEV/tools
    monkeypatch.setattr(G, "tier", lambda root=None: "data")

    def publish(failures, red, verdict=True):
        """A failed tests check shaped as check_tests builds it, `details` (its log lines) included."""
        r = {"name": "tests", "ok": False, "summary": "tests", "blocking": True, "returncode": 1,
             "details": ["FAILED %s - %s" % (n, t.split("\n")[0]) for n, t in failures][:12],
             "failures": [list(f) for f in failures], "counted": len(failures), "stale": None, "incomplete": []}
        if verdict:
            r["known_red"] = G.known_red_verdict(r)
        monkeypatch.setattr(G, "CHECKS", (lambda: r,))
        monkeypatch.setattr(G, "classification", lambda root=None: {"red": red})
        return P.data_tier(out=lambda *a: None)
    new = ("forge/tests/test_submit.py::test_something_new", "AssertionError: boom")
    assert publish([new], red=[new[0]]) == {"ok": False, "verdict": "red", "known_red": []}
    assert publish([(D23, D23_TEXT)], red=[]) == {"ok": True, "verdict": "known-red-only", "known_red": [D23]}
    assert publish([(D23, D23_TEXT)], red=[D23], verdict=False)["verdict"] == "red"


def test_every_skipped_file_names_its_own_cover_and_the_llm_files_are_not_covered(tmp_path, monkeypatch):
    """S6-NL, then draw-3 ci SERIOUS 6: one string, "tools/ci_publish.py data tier, when run", covered every
    skipped file -- false for the DATA_BOUND tests, which every tier --ignore's, the data tier included.
    Draw3_fix ci 3: they then named the VPS wq-forge-tests.timer, with a result frozen into the constant
    ("last read 2026-09-23, 210 passed") that nothing re-read. Orchestrator decision under D42: they read NOT
    COVERED pre-merge, and no timer, no reading and no count is claimed. Pinned per file, in both tiers, with
    the classification's skips each under its own name."""
    import ci_classify as CC
    _passing_run(monkeypatch)
    monkeypatch.setattr(CC, "tests_hash", lambda root=None: "t")
    monkeypatch.setattr(CC, "code_version", lambda root=None: "c")
    cls = {"tests_hash": "t", "code_version": "c", "measured_at": "m", "ignore_files": ["tools/tests/test_heavy.py"],
           "deselect": ["tools/tests/test_a.py::t1", "tools/tests/test_a.py::t2", "forge/tests/test_b.py::t3"]}
    data = G.check_tests(hermetic_only=False, root=_root(tmp_path / "d"))
    herm = G.check_tests(hermetic_only=True, root=_root(tmp_path / "h", classification=cls))
    assert set(data["not_run"]) == set(G.DATA_BOUND)
    assert set(herm["not_run"]) == set(G.DATA_BOUND) | {"tools/tests/test_heavy.py", "tools/tests/test_a.py (2 test(s))",
                                                         "forge/tests/test_b.py (1 test(s))"}
    for r in (data, herm):
        assert set(r["covered_instead_by"]) == set(r["not_run"])                    # every entry has its own
        for f, where in r["covered_instead_by"].items():
            if f in G.DATA_BOUND:
                assert where.startswith("NOT COVERED pre-merge") and "D42" in where, f
                assert not any(w in where for w in ("timer", "passed", "ci_publish")), f
            else:
                assert "ci_publish.py's data tier" in where, f
    assert set(G.DATA_BOUND) == {"forge/tests/test_llm_author.py", "forge/tests/test_llm_formula.py"}
    printed = []
    G.gate(checks=(lambda: data,), out=printed.append)
    assert any(l.strip().startswith("not run here, NOT COVERED pre-merge") for l in printed)
    assert not any("covered instead by NOT COVERED" in l or "timer" in l for l in printed)


# ------------------------------------------------------------------------------ S7-NL: no live, no submit
def test_no_live_reads_every_python_file_and_workflow_for_both_flags(tmp_path):
    """S7-NL: the scan read only the test directories, only for one flag, line by line. It now reads
    every .py under forge/, tools/ and vps/ and every workflow, for both flags used as ARGUMENTS."""
    files = {
        "forge/spend.py": [
            '"""A docstring may name %(L)s."""',                                         # 1  prose
            "import subprocess",                                                          # 2
            'subprocess.run(["python3", "forge/runner.py", "%(L)s"])',                    # 3  PASSED
            'ap.add_argument("%(L)s", action="store_true", help="spend")',               # 4  the definition
            "# never pass %(L)s here",                                                   # 5  a comment
            'assert "%(S)s" not in cmd',                                                 # 6  a guard
            'if "%(L)s" in sys.argv:',                                                   # 7  a read
            '    print("pass %(L)s to spend")',                                          # 8  prose
            'CMD = "cd /opt/wq && python3 forge/submit.py %(S)s"',                        # 9  PASSED (a command line)
            'ARGV = ["%(S)s", "--cap", "4"]',                                            # 10 PASSED (an argv)
            'assert run(["forge/runner.py", "%(L)s"]) == 0',                             # 11 PASSED: the call runs
            'x = "--liv"',                                                               # 12 not the flag
        ],
        "tools/job.py": ['cmd = f"{py} forge/runner.py %(L)s"'],                          # 1  PASSED
        "vps/hook.py": ['main(["%(S)s"])'],                                              # 1  PASSED
        "vps/broken.py": ["def f(:"],                                                    # cannot be checked
        "tools/notify_lint.py": ['COMMAND_TOKENS = ("%(S)s", "--override-root", "--force-submit")'],   # no longer exempt
        "tools/copy_of_lint.py": ['COMMAND_TOKENS = ("%(S)s", "--override-root", "--force-submit")'],  # never exempt
        "harness/elsewhere.py": ['run(["%(L)s"])'],                                      # outside the scan
        ".github/workflows/ci.yml": ["      # never %(L)s", "        run: python forge/runner.py %(L)s",
                                     "        run: python tools/ci_gate.py  # asserts no %(L)s"],
    }
    for rel, lines in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("\n".join(l % {"L": LIVE, "S": SUBMIT} for l in lines) + "\n")
    r = G.check_no_live(tmp_path)
    assert r["ok"] is False
    assert sorted(r["details"]) == sorted([
        "forge/spend.py:3", "forge/spend.py:9", "forge/spend.py:10", "forge/spend.py:11", "tools/job.py:1",
        "vps/hook.py:1", "vps/broken.py (cannot be checked: SyntaxError)", "tools/copy_of_lint.py:1",
        "tools/notify_lint.py:1", ".github/workflows/ci.yml:2"])
    assert "forge/spend.py:3" in r["summary"]


def test_no_live_reads_the_loaded_conftests_the_scripts_tests_run_and_built_commands(tmp_path):
    """Draw-3 ci SERIOUS 5: a probe tree put the flag in /conftest.py, in a shell script, in "--submit --cap
    4".split(), in a `%` template and in a .format template, and the scan flagged none of them. Now each is
    flagged at its line, a script is read when a test, a loaded conftest or a workflow RUNS it (and so is a
    script that one runs), and what is only NAMED is not read: vps/forge_loop.sh passes --submit legitimately
    on the VPS, and the tests name it as data only."""
    files = {
        "conftest.py": ["import subprocess", 'subprocess.run(["python3", "forge/runner.py", "%(L)s"])'],
        "cyberrisk/tests/conftest.py": ['run(["%(L)s"])'],                   # not loaded by the gate's run
        "forge/tests/test_runs_scripts.py": [
            "import subprocess",                                             # 1
            'subprocess.run(["bash", "tools/x.sh"])',                        # 2  runs x.sh (after a shell)
            'subprocess.run(str(ROOT / "tools/y.sh"))',                      # 3  runs y.sh (a spawner's argument)
            'subprocess.run("cd /opt/wq && ./tools/z.sh", shell=True)',      # 4  runs z.sh (a command line, spawned)
            'ARGV = "%(S)s --cap 4".split()',                                # 5  FLAGGED: split into an argv
            'T1 = "%%s %(L)s" %% script',                                    # 6  FLAGGED: % template
            'T2 = "{} %(S)s --cap 4".format(script)',                        # 7  FLAGGED: .format template
            'T3 = "no file under %%s passes %(L)s" %% d',                    # 8  prose: its command word is "no"
            'assert (ROOT / "vps/forge_loop.sh").exists()',                  # 9  named, not run
            'FILES = {"vps/forge_loop.sh": "#!/bin/bash"}',                  # 10 named, not run
            '"""A docstring: bash vps/forge_loop.sh"""',                     # 11 prose, not run
        ],
        "tools/x.sh": ["#!/bin/bash", "# never %(L)s", "python3 forge/runner.py %(L)s", "bash tools/nested.sh"],
        "tools/y.sh": ["python3 forge/submit.py %(S)s"],
        "tools/z.sh": ["echo quiet"],
        "tools/nested.sh": ["python3 forge/runner.py %(L)s"],
        "vps/forge_loop.sh": ["python3 forge/submit.py %(S)s --cap 4"],
        ".github/workflows/ci.yml": ["jobs:", "      - run: bash .github/scripts/nightly.sh"],
        ".github/scripts/nightly.sh": ["python3 forge/runner.py %(L)s"],
    }
    for rel, lines in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("\n".join(l % {"L": LIVE, "S": SUBMIT} for l in lines) + "\n")
    r = G.check_no_live(tmp_path)
    assert r["ok"] is False
    assert sorted(r["details"]) == sorted([
        "conftest.py:2", "forge/tests/test_runs_scripts.py:5", "forge/tests/test_runs_scripts.py:6",
        "forge/tests/test_runs_scripts.py:7", "tools/x.sh:3", "tools/y.sh:1", "tools/nested.sh:1",
        ".github/scripts/nightly.sh:1"])
    assert r["scripts_read"] == sorted([".github/scripts/nightly.sh", "tools/nested.sh", "tools/x.sh", "tools/y.sh",
                                        "tools/z.sh"])


W_SCRIPTS = ("conftest", "opts", "name", "argv0", "timeout", "dashc", "concat", "split", "async", "helper")


def test_no_live_reads_the_near_variants_the_draw3_fix_audit_found_open(tmp_path):
    """Draw3_fix ci 4 (each gave ok=True on the adjudicator's probe trees), and ci 6 (two lines of the scan that
    no test held): an f-string template, a template after `&&`, `timeout N` and `env`, a shell's options before
    the script, a script path held in a name, argv[0] of an argv handed to a spawner, a script the ROOT
    conftest runs, a script run by a module a test imports, and a module outside forge/, tools/ and vps/ that
    a test imports and that passes the flag. Each is flagged at its line, or its script is read."""
    files = {
        "conftest.py": ["import subprocess", 'subprocess.run(["bash", "tools/w_conftest.sh"])'],
        "forge/tests/test_variants.py": [
            "import subprocess",                                             # 1
            "from forge import helper",                                      # 2  imports a module that runs a script
            "import harness.mod",                                            # 3  imports a module outside the dirs
            'A = f"{script} %(S)s --cap 4"',                                 # 4  FLAGGED: an f-string read whole
            'B = "cd /opt/wq && %%s %(S)s" %% s',                            # 5  FLAGGED: a template after &&
            'C = "timeout 600 %%s %(L)s" %% s',                              # 6  FLAGGED: behind timeout N
            'D = "env A=1 %%s %(S)s --cap 4" %% s',                          # 7  FLAGGED: behind env VAR=value
            'subprocess.run(["bash", "-e", "tools/w_opts.sh"])',             # 8  runs w_opts.sh (after -e)
            'S = "tools/w_name.sh"',                                         # 9
            'subprocess.run(["bash", S])',                                   # 10 runs w_name.sh (a name)
            'subprocess.run(["tools/w_argv0.sh", "--verbose"])',             # 11 runs w_argv0.sh (argv[0])
            'subprocess.run(["timeout", "60", "tools/w_timeout.sh"])',      # 12 runs it behind timeout N
            'subprocess.run(["bash", "-c", "tools/w_dashc.sh --quiet"])',    # 13 runs it: the command line after -c
            'subprocess.run(["bash"] + ["tools/w_concat.sh"])',              # 14 runs it: an argv built with +
            'subprocess.run(shlex.split("bash tools/w_split.sh"))',          # 15 runs it: a split command line
            'asyncio.create_subprocess_exec("tools/w_async.sh")',            # 16 runs it: asyncio's spawner
        ],
        "forge/helper.py": ["import subprocess", "def go():", '    subprocess.run(["bash", "tools/w_helper.sh"])'],
        "harness/mod.py": ['ARGV = ["forge/runner.py", "%(L)s"]'],        # FLAGGED: outside the dirs, imported
        "harness/unimported.py": ['ARGV = ["forge/runner.py", "%(L)s"]'],  # not imported by any test: not read
        **{"tools/w_%s.sh" % k: ["python3 forge/runner.py %(L)s"] for k in W_SCRIPTS},
    }
    for rel, lines in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("\n".join(l % {"L": LIVE, "S": SUBMIT} for l in lines) + "\n")
    r = G.check_no_live(tmp_path)
    shells = sorted("tools/w_%s.sh" % k for k in W_SCRIPTS)
    assert r["scripts_read"] == shells
    assert sorted(r["details"]) == sorted(["forge/tests/test_variants.py:%d" % i for i in (4, 5, 6, 7)]
                                          + ["harness/mod.py:1"] + [s + ":1" for s in shells])


def test_no_live_does_not_read_a_script_named_as_data(tmp_path):
    """Draw3_fix ci 5 (it failed CLOSED): a tuple loop checking exists(), a parametrize list and `assert plan ==
    [...]` each read vps/forge_loop.sh as RUN, and so did command lines held as data -- the three forms this
    very file's probe trees use ("cd /opt/wq && ./tools/z.sh", "bash tools/nested.sh", "- run: bash
    .github/scripts/nightly.sh" as strings in a list). forge_loop.sh passes the flag, so a false read blocks."""
    files = {
        "forge/tests/test_names_it.py": [
            "import pytest",
            'for p in ("vps/forge_loop.sh",):',
            "    assert (ROOT / p).exists()",
            '@pytest.mark.parametrize("p", ["vps/forge_loop.sh"])',
            "def test_p(p):",
            '    assert plan == ["vps/forge_loop.sh"]',
            'LINES = ["cd /opt/wq && ./vps/forge_loop.sh", "bash vps/forge_loop.sh"]',
            'FILES = {".github/workflows/ci.yml": ["      - run: bash vps/forge_loop.sh"]}',
            'CMD = "cd /opt/wq && ./vps/forge_loop.sh"',
        ],
        "vps/forge_loop.sh": ["python3 forge/submit.py %(S)s --cap 4"],
    }
    for rel, lines in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("\n".join(l % {"L": LIVE, "S": SUBMIT} for l in lines) + "\n")
    G.check_no_live(tmp_path)
    n = len(sys.path)
    r = G.check_no_live(tmp_path)
    assert r["ok"] is True and r["scripts_read"] == [], r["details"]
    assert len(sys.path) == n                  # the fixture module is put on sys.path once, not once per file read
    # the control: the same script, RUN, is read and blocks
    (tmp_path / "forge/tests/test_runs_it.py").write_text('import subprocess\nsubprocess.run(CMD, shell=True)\n'
                                                          'CMD = "cd /opt/wq && ./vps/forge_loop.sh"\n')
    r = G.check_no_live(tmp_path)
    assert r["scripts_read"] == ["vps/forge_loop.sh"] and r["details"] == ["vps/forge_loop.sh:1"]


def test_the_workflow_says_what_the_gate_does():
    """Draw-3 ci: .github/workflows/ci.yml said "22 of the 247" tests could not run, that they were covered by
    "the VPS deploy smoke", and that tools/ci_gate.py "blocks on REGRESSION instead (D9)". None was true: the
    covers are the ones check_tests names, and the pre-merge gate pins the scorer because a candidate has no
    output to regress (D14). The comment must name the same covers as the gate. Draw3_fix ci 3 and 8: it
    named the VPS timer (dropped under D42), an unpinned "37 tests", "green publish record" where deploy.py
    also accepts known-red-only, and "(D9 as written)", which read as if D9 forbade the block it asked for."""
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    for false in ("22 of the", "deploy smoke", "blocks on REGRESSION instead", "37 tests", "timer",
                  "(D9 as written)", "no\n# green publish record"):
        assert false not in text, false
    assert "NOT COVERED pre-merge" in G.NOT_COVERED_PRE_MERGE and "NOT COVERED pre-merge" in text and "D42" in text
    assert "ci_publish.py's data tier" in G.COVERED_BY_DATA_TIER and "tools/ci_publish.py's data tier" in text
    assert "green or known-red-only publish record" in text and "D9 asked the gate to block" in text
    assert "D31" in text and "REPORTS" in text
    # draw4_build ci 2: the header claimed "a run that was not the whole suite" blocks; round 3 S6: test files
    assert "whole suite" not in text and "COLLECTED test did not run" in text and "installed plugin" in text
    assert "round 3 S6" in text and "test files no tier runs" in text


# ------------------------------------------------------------------------------ draw3_fix ci 10: 3.13 against 3.14
def _older_python_rejects(files, root, version):
    """[(file, why)] for each file the grammar of `version` does not parse."""
    import ast
    import warnings
    bad = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                  # SyntaxWarnings are not the question here
        for f in files:
            try:
                ast.parse(f.read_text(), str(f), feature_version=version)
            except SyntaxError as exc:
                bad.append((f.relative_to(root).as_posix(), exc.msg))
    return bad


def test_every_published_python_file_parses_under_the_python_the_workflow_pins(tmp_path):
    """Draw3_fix ci 10 (EX-ANTE, not reproduced): Actions pins the Python in ci.yml (3.13) while this machine
    runs 3.14, so a 3.14-only form -- `except A, B:` (PEP 758), a t-string (PEP 750) -- in any published file
    would pass the data tier here and break the hermetic tier there. MEASURED 2026-09-23: 331 files, none.
    The version is READ from the workflow, so the two cannot drift. A LIMIT, stated: feature_version is
    "best-effort" in the ast docs; it caught both forms above on 3.14.0 (the control below), which is all
    this test claims."""
    import re
    import ci_publish as P
    ver = tuple(int(x) for x in re.search(r'python-version:\s*"(\d+)\.(\d+)"',
                                          (ROOT / ".github/workflows/ci.yml").read_text()).groups())
    files = [f for s in P.SUBSET for f in ((ROOT / s).rglob("*.py") if (ROOT / s).is_dir() else [ROOT / s])
             if f.suffix == ".py" and P._synced(f.relative_to(ROOT).as_posix())]
    assert len(files) > 300 and _older_python_rejects(files, ROOT, ver) == []
    if sys.version_info >= (3, 14):                     # the control needs a parser that knows the newer forms
        new = tmp_path / "new.py"
        for form in ("try:\n    pass\nexcept ValueError, TypeError:\n    pass\n", 'x = t"{1}"\n'):
            new.write_text(form)
            assert _older_python_rejects([new], tmp_path, (3, 13)), form


# ------------------------------------------------------------------------------ draw4_build ci 2: what pytest collects
@pytest.mark.parametrize("conftest, name", [
    ('collect_ignore = ["test_zz_new.py"]\n', "collect_ignore"),
    ('collect_ignore_glob = ["*zz*"]\n', "collect_ignore_glob"),
    ("def pytest_ignore_collect(collection_path, config):\n    return 'zz_new' in str(collection_path) or None\n",
     "pytest_ignore_collect"),
    ('pytest_plugins = ["narrowing_plugin"]\n', "pytest_plugins"),
    ("try:\n    from narrowing_plugin import *\nexcept ImportError:\n    pass\n", "star-imports"),
    # draw-5 ci 5: a name bound by an import (a mutant ignoring import bindings survived)
    ("from narrowing_plugin import pytest_ignore_collect\n", "pytest_ignore_collect"),
    # draw-5 ci 1: pytest_pycollect_makeitem narrowed collection (REPRODUCED); the other hooks can (pytest's reference)
    ("def pytest_pycollect_makeitem(collector, name, obj):\n    return [] if name == 'test_zz_new' else None\n",
     "pytest_pycollect_makeitem"),
    ("def pytest_collect_file(file_path, parent):\n    return None\n", "pytest_collect_file"),
    ("def pytest_pycollect_makemodule(module_path, parent):\n    return None\n", "pytest_pycollect_makemodule"),
    ("def pytest_collection(session):\n    return None\n", "pytest_collection"),
    ("def pytest_collect_directory(path, parent):\n    return None\n", "pytest_collect_directory"),
    ("def pytest_make_collect_report(collector):\n    return None\n", "pytest_make_collect_report"),
])
def test_a_conftest_that_can_narrow_collection_is_never_a_known_red(tmp_path, conftest, name):
    """Draw4_build ci 2: a root conftest's collect_ignore and a pytest_ignore_collect hook each gave rc 1, counted 1,
    incomplete [] and an ok known-red verdict while a NEW failure was never collected -- no count in pytest's output
    shows a test it never collected (MEASURED here: the control run below). The loaded conftests are read for the
    names that can narrow collection, and such a run is `incomplete`."""
    known = _known_then_new(tmp_path)
    (tmp_path / "narrowing_plugin.py").write_text(
        "def pytest_ignore_collect(collection_path, config):\n    return 'zz_new' in str(collection_path) or None\n")
    (tmp_path / "forge/tests/conftest.py").write_text(conftest)
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert any(name in w for w in r["incomplete"]), r["incomplete"]
    v = G.known_red_verdict(r, known=known)
    assert v["ok"] is False and any("not the whole suite" in b for b in v["blocking"])
    if name == "collect_ignore":        # the control: without the static read, the run looks whole and is allowed
        assert r["counted"] == 1 and G.run_incomplete(_rerun_stdout(tmp_path), 0) == []
        assert G.known_red_verdict(dict(r, incomplete=[]), known=known)["ok"] is True


def _rerun_stdout(root):
    """pytest's own output for the gate's argv on `root` (the reading run_incomplete gets)."""
    argv = [sys.executable, "-m", "pytest", *G.suite(root), "--no-header", "-rfE", "-p", "no:cacheprovider", "-o", "addopts="]
    return subprocess.run(argv, cwd=str(root), capture_output=True, text=True, env=G._pytest_env()).stdout


@pytest.mark.parametrize("ini", ["[pytest]\npython_files = test_known.py\n", "[pytest]\npython_functions = test_the\n"])
def test_an_ini_files_collection_patterns_cannot_narrow_the_run(tmp_path, ini):
    """Draw4_build ci 2: a pytest.ini `python_files` gave rc 1, counted 1 and an ok verdict with a NEW failure never
    collected. check_tests passes pytest's defaults with -o (PYTHON_FILES ...), so the ini cannot narrow them: both
    failures are collected and the NEW one blocks."""
    known = _known_then_new(tmp_path, ini=ini)
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert r["counted"] == 2 and r["incomplete"] == [], (r["summary"], r["incomplete"])
    assert G.known_red_verdict(r, known=known)["ok"] is False


# ------------------------------------------------------------------------------ draw4_build ci 4: a self-bound name
def test_a_name_bound_to_an_expression_that_holds_it_is_read_not_recursed():
    """Draw4_build ci 4 (fails closed, as a crash): both forms made check_no_live raise RecursionError, with no file
    named. The first now reads the script its argv runs; the second, whose only binding is itself, reads nothing."""
    assert set(G._scripts_python_runs("import subprocess\ncmd = ['bash']\ncmd = cmd + ['tools/x.sh']\nsubprocess.run(cmd)\n")) \
        == {"tools/x.sh"}
    assert G._scripts_python_runs("import subprocess\n\ndef f(cmd):\n    cmd = cmd + ['-v']\n    subprocess.run(cmd)\n") == []


def test_a_file_whose_reading_recurses_is_named_and_blocks_instead_of_crashing_the_gate(tmp_path, monkeypatch):
    """Draw4_build ci 4: the per-file handler caught OSError, SyntaxError and ValueError only, so a RecursionError
    left gate() and ci_publish.data_tier() raising with no file named. Now it is "cannot be checked", and so is the
    tests' import closure when ITS walk recurses."""
    (tmp_path / "forge/tests").mkdir(parents=True)
    (tmp_path / "forge/tests/test_deep.py").write_text("x = 1\n")

    def recurse(source):
        raise RecursionError("maximum recursion depth exceeded")
    monkeypatch.setattr(G, "_scripts_python_runs", recurse)
    r = G.check_no_live(tmp_path)
    assert r["ok"] is False and "forge/tests/test_deep.py (cannot be checked: RecursionError)" in r["details"]
    monkeypatch.setattr(F, "import_closure", lambda *a, **k: recurse(""))
    r = G.check_no_live(tmp_path)
    assert "the import closure of the tests (cannot be followed: RecursionError)" in r["details"]


# ------------------------------------------------------------------------------ draw4_build ci 5 and 6: forms the scan reads
def test_an_unparsable_test_file_is_named_and_the_scan_does_not_raise(tmp_path):
    """Draw4_build ci 5, K3: the closure handler narrowed to another exception survived the whole file. An unparsable
    test file makes the import-closure walk raise SyntaxError: the scan names the file and the closure, and returns."""
    (tmp_path / "forge/tests").mkdir(parents=True)
    (tmp_path / "forge/tests/test_broken.py").write_text("def f(:\n")
    r = G.check_no_live(tmp_path)
    assert r["ok"] is False
    assert "forge/tests/test_broken.py (cannot be checked: SyntaxError)" in r["details"]
    assert "the import closure of the tests (cannot be followed: SyntaxError)" in r["details"]


V_SCRIPTS = ("argv_name", "sudo", "env", "timeout_line", "var_line", "annotated", "kwargs", "sudo_u", "spawnl", "async",
             "absolute", "execv")


def test_no_live_reads_the_forms_the_draw4_audit_found_open(tmp_path):
    """Draw4_build ci 5 (K1: a Name handed to a spawner; K6: the argv launchers) and ci 6 (each read ok=True on the
    adjudicator's probe trees): each script below passes the flag and is RUN by the test file in a form the scan
    did not read; a template held in a name, and a module reached through a sys.path ALIAS, pass it too."""
    files = {
        "forge/tests/test_forms.py": [
            "import asyncio, os, subprocess, sys",                                     # 1
            'ARGV = ["tools/v_argv_name.sh"]',                                         # 2
            "subprocess.run(ARGV)",                                                    # 3  K1: the name is followed
            'subprocess.run(["sudo", "tools/v_sudo.sh"])',                             # 4  K6
            'subprocess.run(["env", "A=1", "tools/v_env.sh"])',                        # 5  K6
            'subprocess.run("timeout 60 tools/v_timeout_line.sh", shell=True)',        # 6
            'subprocess.run("A=1 tools/v_var_line.sh", shell=True)',                   # 7
            'S: str = "tools/v_annotated.sh"',                                         # 8
            'subprocess.run(["bash", S])',                                             # 9
            'subprocess.run(args=["tools/v_kwargs.sh", "--verbose"])',                 # 10 argv[0], by keyword
            'subprocess.run(["sudo", "-u", "wq", "tools/v_sudo_u.sh"])',               # 11
            'os.spawnl(os.P_WAIT, "/bin/bash", "bash", "tools/v_spawnl.sh")',          # 12
            'asyncio.create_subprocess_exec("bash", "tools/v_async.sh")',              # 13
            'subprocess.run(["/opt/wq/tools/v_absolute.sh"])',                         # 14
            'os.execv("/bin/bash", ["bash", "tools/v_execv.sh"])',                     # 15
            'T = "%%s %(S)s --cap 4"',                                                 # 16 FLAGGED: a template in a name
            "P = sys.path",                                                            # 17
            'P.insert(0, "elsewhere")',                                                # 18 an alias of sys.path
            "import aliased",                                                          # 19
        ],
        "elsewhere/aliased.py": ['ARGV = ["forge/runner.py", "%(L)s"]'],            # FLAGGED: reached through the alias
        **{"tools/v_%s.sh" % k: ["python3 forge/runner.py %(L)s"] for k in V_SCRIPTS},
    }
    for rel, lines in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("\n".join(l % {"L": LIVE, "S": SUBMIT} for l in lines) + "\n")
    r = G.check_no_live(tmp_path)
    shells = sorted("tools/v_%s.sh" % k for k in V_SCRIPTS)
    assert r["scripts_read"] == shells and r["closure_unread"] == []
    assert sorted(r["details"]) == sorted(["forge/tests/test_forms.py:16", "elsewhere/aliased.py:1"] + [x + ":1" for x in shells])


def test_the_spawners_are_read_by_where_their_command_is():
    """Draw4_build ci 6: _SPAWN's comment said "their first argument is a command", false for os.spawn* (the mode)
    and the varargs forms. Each family is read at its own position; argv[0] of an l-form or of execv's list (the
    program's own name) is not read as a script."""
    import ast as A

    def argv_of(src):
        call = A.parse(src).body[0].value
        return [[A.unparse(e) for e in c] if isinstance(c, list) else A.unparse(c) for c in G._spawned(call, {})]
    assert argv_of('subprocess.run(["x"])') == ["['x']"] and argv_of('subprocess.run(args="x")') == ["'x'"]
    assert argv_of('os.spawnl(os.P_WAIT, "/bin/sh", "sh", "a.sh")') == [["'/bin/sh'", "'a.sh'"]]
    assert argv_of('os.execl("/bin/sh", "sh", "a.sh")') == [["'/bin/sh'", "'a.sh'"]]
    assert argv_of('asyncio.create_subprocess_exec("sh", "a.sh")') == [["'sh'", "'a.sh'"]]
    assert argv_of('os.spawnv(os.P_WAIT, "/bin/sh", ["sh", "a.sh"])') == [["'/bin/sh'", "'a.sh'"]]
    assert set(G._SPAWN) == set(G._SPAWN_COMMAND) | set(G._SPAWN_VARARGS) | set(G._SPAWN_VECTOR)


def test_the_exemption_list_is_empty_and_the_real_tree_blocks_on_the_loop_a_test_can_reach():
    """The notify_lint exemption (draw3_fix ci 9: an open RULE 2 item, never ticked) is deleted: its owner built the
    token as "--" + "submit", so the real tools/notify_lint.py no longer holds the literal and the scan reads no
    flag in it. Draw-5 ci 13: this test was named "...the real tree passes without it" and never scanned the real
    tree. Draw-5 ci C8 (d): with the deployed layout read, the real tree BLOCKS -- forge/tests/test_search.py imports
    forge/search.py, whose run_recipe() runs forge_loop.sh at its deployed path, vps/forge_loop.sh, which passes
    --live and --submit. Pinned exactly as fail-closed until Khoa ticks how run_recipe is treated (RULE 2: an
    exact-line exemption, run_recipe refusing under pytest, or blocking); the tick changes this test."""
    import re
    assert G.NO_LIVE_EXEMPT == {}
    assert G._flag_lines((ROOT / "tools/notify_lint.py").read_text()) == []
    r = G.check_no_live()
    loop = (ROOT / "vps/forge_loop.sh").read_text().splitlines()
    flagged = ["vps/forge_loop.sh:%d" % i for i, l in enumerate(loop, 1) if G._FLAG.search(re.sub(r"(^|\s)#.*$", "", l))]
    assert len(flagged) == 2 and r["ok"] is False and r["details"] == flagged, r["details"]
    assert "vps/forge_loop.sh" in r["scripts_read"] and r["scripts_unresolved"] == []
    assert "search.py" in (ROOT / "forge/tests/test_search.py").read_text()
    assert 'subprocess.run(["bash", str(ROOT / "forge_loop.sh")]' in (ROOT / "forge/search.py").read_text()


def test_the_workflow_pins_the_pytest_the_output_parsers_were_measured_on():
    """Draw4_build ci 9 (SUSPECTED, not observed): ci.yml installed pytest unpinned while run_incomplete and
    parse_summary read pytest 9.1.1's human-readable output. The pin and the gate's PYTEST_MEASURED are one value."""
    import re
    pins = re.findall(r"pip install [^\n]*\bpytest==(\S+)", (ROOT / ".github/workflows/ci.yml").read_text())
    assert pins == [G.PYTEST_MEASURED] == ["9.1.1"]


# ------------------------------------------------------------------------------ round 3 S6: test files outside TEST_DIRS
def _publish_tree(tmp_path, files):
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body)
    return tmp_path


def test_a_failing_test_file_outside_the_test_dirs_is_run_and_blocks_the_publish(tmp_path, monkeypatch):
    """Round 3 S6, the CI/CD attacker's probe: forge/gen/tests/test_b.py (assert False) lay outside TEST_DIRS, the
    gate's argv gave "2 passed", and the REAL data_tier() returned `known-red-only`, which deploy accepts. It is now
    in the suite, so the tests check fails on it and data_tier() reads red."""
    import ci_publish as P
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {})             # the real list names files this tree lacks
    root = _publish_tree(tmp_path, {"forge/tests/test_ok.py": "def test_ok():\n    pass\n",
                                    "tools/tests/test_ok2.py": "def test_ok2():\n    pass\n",
                                    "forge/gen/tests/test_b.py": "def test_b():\n    assert False, 'a branch test'\n"})
    assert G.suite(root) == ["forge/tests", "tools/tests", "forge/gen/tests/test_b.py"]
    r = G.check_tests(hermetic_only=False, root=root)
    assert r["ok"] is False and [f[0] for f in r["failures"]] == ["forge/gen/tests/test_b.py::test_b"]
    assert G.check_test_files(root)["ok"] is True                                  # it is run: nothing to list
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(G, "tier", lambda root=None: "data")
    monkeypatch.setattr(G, "CHECKS", (lambda: r,))
    assert P.data_tier(out=lambda *a: None) == {"ok": False, "verdict": "red", "known_red": []}


def test_a_test_file_no_tier_runs_blocks_until_it_is_run_moved_or_listed(tmp_path, monkeypatch):
    """Round 3 S6: a test file from which pytest collects nothing (a script, like the 22 tools/funnel ones) and that
    is not listed blocks; listed with a reason it passes and is printed NOT COVERED pre-merge; a listed path that is
    not a test file of the subset blocks, so the list stays the files it describes."""
    root = _publish_tree(tmp_path, {"forge/tests/test_ok.py": "def test_ok():\n    pass\n",
                                    "tools/funnel/test_script.py": "def check():\n    return True\n\n"
                                                                   "if __name__ == '__main__':\n    check()\n"})
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {})
    r = G.check_test_files(root)
    assert r["ok"] is False and r["details"][0].startswith("tools/funnel/test_script.py -- a test file outside")
    assert G.suite(root) == list(G.TEST_DIRS)                                       # pytest would collect nothing
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {"tools/funnel/test_script.py": "a script, for this test"})
    r = G.check_test_files(root)
    assert r["ok"] is True and r["not_run"] == {"tools/funnel/test_script.py": "a script, for this test"}
    assert r["covered_instead_by"]["tools/funnel/test_script.py"].startswith("NOT COVERED pre-merge")
    printed = []
    G.gate(checks=(lambda: r,), out=printed.append)
    assert any("tools/funnel/test_script.py -- a script, for this test" in l for l in printed)
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {"tools/funnel/test_script.py": "x", "tools/gone/test_z.py": "y"})
    r = G.check_test_files(root)
    assert r["ok"] is False and any(d.startswith("tools/gone/test_z.py -- listed") for d in r["details"])


def test_every_test_file_of_the_published_subset_is_run_or_listed_on_the_real_tree():
    """Round 3 S6 on the real tree: every shipped test file outside TEST_DIRS is run or listed, none is neither, the
    list names no file that is gone, and the gate, its no-live scan and the classifier read one suite. Round 4 m11:
    this asserted `== 25` files outside TEST_DIRS, a change detector that turned the data tier red for any new test
    file there; the invariants stay and the literal is gone. Draw 6: the new test files (forge/tests/test_gen_*, and
    the additions to test_harvest and test_submit) are under TEST_DIRS, so check_tests hands them to pytest in both
    tiers."""
    import ci_classify as C
    c = G.classify_test_files()
    assert c["no_tier"] == [] and c["stale_listing"] == [] and c["listed"] == sorted(G.NOT_RUN_OUTSIDE_TEST_DIRS)
    assert len(c["in_test_dirs"]) > 60
    new = ["forge/tests/test_gen_%s.py" % m for m in ("families", "posterior", "productions", "propose", "repair",
                                                       "spend", "state")] + ["forge/tests/test_harvest.py",
                                                                             "forge/tests/test_submit.py"]
    assert [f for f in new if f not in c["in_test_dirs"]] == []
    assert G.suite() == list(G.TEST_DIRS) + c["run_outside"] == C.suites()
    assert all(G.published_test_files().count(f) == 1 for f in c["listed"])
    assert C.ALWAYS_IGNORED == sorted(G.DATA_BOUND)


def test_collectable_reads_what_pytest_would_collect():
    """Round 3 S6: a file counts as run only when pytest can collect a test from it (python_functions "test",
    python_classes "Test", or a unittest TestCase); a script defining check_*() and __main__ is not."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "test_x.py"
        for body, can in (("def test_a():\n    pass\n", True), ("class TestA:\n    def test_a(self):\n        pass\n", True),
                          ("import unittest\nclass Gate(unittest.TestCase):\n    def test_a(self):\n        pass\n", True),
                          ("def check():\n    pass\nif __name__ == '__main__':\n    check()\n", False),
                          ("class Helper:\n    def test_a(self):\n        pass\n", False), ("def f(:\n", True),
                          # draw-5 ci 4 (MEASURED, d6ci_ev/collect_probe) and 5 (a Test class with no test)
                          ("__test__ = False\ndef test_a():\n    pass\n", False),
                          ("class TestA:\n    def __init__(self):\n        pass\n    def test_a(self):\n        pass\n", False),
                          ("class TestA:\n    __test__ = False\n    def test_a(self):\n        pass\n", False),
                          ("import unittest\nclass T(unittest.TestCase):\n    def __init__(self, *a):\n        super().__init__(*a)\n"
                           "    def test_a(self):\n        pass\n", True),
                          ("class TestA:\n    def helper(self):\n        pass\n", False)):
            f.write_text(body)
            assert G.collectable(f) is can, body


# ------------------------------------------------------------------------------ draw4_build ci X2: the classifier's arms
def test_the_classifier_runs_each_arm_the_way_the_gate_runs_pytest(tmp_path, monkeypatch):
    """Draw4_build ci X2 (EX-ANTE, by reading): run_arm() ran pytest with the caller's whole environment and `-q` and
    read no completeness. Under PYTEST_ADDOPTS=-x an arm stopped at its first failure, so the NEW failure was
    classified as nothing; with `-q` the "collected" line is gone and completeness cannot be shown."""
    import ci_classify as C
    _known_then_new(tmp_path)
    monkeypatch.setenv("PYTEST_ADDOPTS", "-x")
    arm = C.run_arm(tmp_path, sys.executable, ["forge/tests", "tools/tests"])
    assert arm["failed"] == {"forge/tests/test_known.py::" + _LONG, "forge/tests/test_zz_new.py::test_zz_new"}
    assert arm["incomplete"] == [], arm["incomplete"]
    (tmp_path / "conftest.py").write_text("def pytest_collection_modifyitems(config, items):\n"
                                          "    items[:] = [i for i in items if 'zz_new' not in i.nodeid]\n")
    assert any("accounts for 1" in w for w in C.run_arm(tmp_path, sys.executable, ["forge/tests", "tools/tests"])["incomplete"])


def test_an_arm_that_did_not_run_every_collected_test_writes_no_classification(tmp_path, monkeypatch):
    """Draw4_build ci X2: a classification whose arm was cut short is not a measurement; INVALID, nothing written."""
    import ci_classify as C
    out = tmp_path / "ci_data_bound.json"
    monkeypatch.setattr(C, "OUT", out)
    monkeypatch.setattr(C, "tests_hash", lambda root=None: "t")
    monkeypatch.setattr(C, "code_version", lambda root=None: "c")
    monkeypatch.setattr(C, "suites", lambda root=None: ["forge/tests"])
    arms = {"clean": {"failed": set(), "collect_errors": set(), "summary": "1 passed", "incomplete": []}}

    def run_arm(cwd, python, suite=None):
        return arms.get("clean") if pathlib_name(cwd) == "clean" else arms["data"]
    pathlib_name = lambda p: Path(p).name                                            # noqa: E731
    monkeypatch.setattr(C, "run_arm", run_arm)
    (tmp_path / "clean").mkdir()
    argv = ["--clean", str(tmp_path / "clean"), "--clean-python", sys.executable]
    arms["data"] = dict(arms["clean"], incomplete=["pytest ended the run early: stopping after 1 failures"])
    assert C.main(argv) == 1 and not out.exists()
    arms["data"] = dict(arms["clean"])
    assert C.main(argv) == 0 and json.loads(out.read_text())["suite"] == ["forge/tests"]      # the control


def test_no_live_follows_the_scripts_a_test_file_outside_the_test_dirs_runs(tmp_path, monkeypatch):
    """Round 3 S6, the scan's half: a test file the suite now runs outside TEST_DIRS is a RUNNER like the ones
    inside -- the scripts it runs, and the modules it imports, are read."""
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {})
    root = _publish_tree(tmp_path, {
        "forge/gen/tests/test_runs.py": "import subprocess\n\ndef test_r():\n    subprocess.run(['bash', 'tools/g.sh'])\n",
        "tools/g.sh": "python3 forge/runner.py %s\n" % LIVE})
    r = G.check_no_live(root)
    assert r["scripts_read"] == ["tools/g.sh"] and r["details"] == ["tools/g.sh:1"]


def test_the_classification_hash_covers_a_test_file_outside_the_test_dirs(tmp_path, monkeypatch):
    """Round 3 S6: the classifier's staleness hash read the two directories; a test file the suite runs outside them
    could change and leave the classification looking current. For a suite of directories only, the hash is the
    bytes it always was."""
    import ci_classify as C
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {})
    root = _publish_tree(tmp_path, {"forge/tests/test_a.py": "def test_a():\n    pass\n",
                                    "forge/gen/tests/test_b.py": "def test_b():\n    pass\n"})
    before = C.tests_hash(root)
    (root / "forge/gen/tests/test_b.py").write_text("def test_b():\n    assert 1\n")
    assert C.tests_hash(root) != before


def test_the_input_layer_case_puts_every_reader_back():
    """Round 3 S7: case_input_layer points build()'s readers at a miniature state; every one must be the scorer's own
    again afterwards, or each case after it (and a card built in the same process) would read the miniature."""
    import importlib
    B = F._scorer()
    P = importlib.import_module("forge.probe")
    before = [B.SUB.posted_history, B.HV.load_scored, P.load_corr, B.load_deploys, B.load_standard, B.MEANING_LEDGER,
              B.RUN_CONFIG_LOG, B.axis3_gearing]
    F.case_input_layer()
    assert [B.SUB.posted_history, B.HV.load_scored, P.load_corr, B.load_deploys, B.load_standard, B.MEANING_LEDGER,
            B.RUN_CONFIG_LOG, B.axis3_gearing] == before


# ------------------------------------------------------------------------------ draw-5 ci C8: the deployed layout
def _loop_tree(tmp_path, run_line):
    """A test file that RUNS a loop script by `run_line`, and vps/forge_loop.sh passing the flag on its line 2."""
    return _publish_tree(tmp_path, {"forge/tests/test_runs_loop.py": "import subprocess\nfrom pathlib import Path\n"
                                                                     "ROOT = Path(__file__).resolve().parents[2]\n"
                                                                     "%s\n" % run_line,
                                    "vps/forge_loop.sh": "#!/bin/bash\npython3 forge/submit.py %s --cap 4\n" % SUBMIT})


@pytest.mark.parametrize("run_line", ['subprocess.run(["bash", "/opt/wq/forge_loop.sh"])',
                                      'subprocess.run(["bash", str(ROOT / "forge_loop.sh")])',
                                      'subprocess.run(["bash", "vps/forge_loop.sh"])'])      # the control
def test_no_live_reads_the_loop_at_its_deployed_path(tmp_path, run_line):
    """Draw-5 ci C8 (a) (REPRODUCED by the adjudicator, probe2.py): a test running `/opt/wq/forge_loop.sh` or
    `ROOT / "forge_loop.sh"` gave ok=True and read nothing, while `vps/forge_loop.sh` blocked. tools/deploy.py PLAN
    ships vps/forge_loop.sh to /opt/wq/forge_loop.sh, where the deploy smoke and wq-forge-tests run the tests, and the
    scan resolved the host path against the repository root. Each form now reads the loop and blocks at its flag."""
    r = G.check_no_live(_loop_tree(tmp_path, run_line))
    assert r["scripts_read"] == ["vps/forge_loop.sh"] and r["details"] == ["vps/forge_loop.sh:2"], r["details"]


def test_the_deployed_layout_is_read_from_the_plan_and_an_unreadable_plan_fails_closed(tmp_path, monkeypatch):
    """Draw-5 ci C8 (a): the host-path mapping is tools/deploy.py PLAN's own (its file entries whose paths differ),
    read from the syntax tree, never a list here. A PLAN that cannot be read blocks, named."""
    import ast as A
    plan = next(A.literal_eval(n.value) for n in A.parse((ROOT / "tools/deploy.py").read_text()).body
                if isinstance(n, A.Assign) and getattr(n.targets[0], "id", None) == "PLAN")
    layout = G._deployed_layout()
    assert layout == {d: s for s, d in plan.items() if not s.endswith("/") and s != d}
    assert layout["forge_loop.sh"] == "vps/forge_loop.sh"
    monkeypatch.setattr(G, "DEPLOY_PY", "tools/no_such_deploy.py")
    r = G.check_no_live(_loop_tree(tmp_path, 'subprocess.run(["bash", "vps/forge_loop.sh"])'))
    assert r["ok"] is False and any(d.startswith("the deployed layout (cannot be read") for d in r["details"])


def test_a_script_run_that_names_no_file_is_named_and_blocks(tmp_path):
    """Draw-5 ci C8 (b): a .sh token found as a RUN that resolved to no file was dropped without a word -- the form
    the loop at its host path took. It is named, with the file that runs it, and it blocks: it cannot be checked.
    The control: the same run of a script that exists, and passes nothing, is read and passes."""
    root = _publish_tree(tmp_path, {"forge/tests/test_runs.py": "import subprocess\nsubprocess.run(['bash', 'tools/gone.sh'])\n",
                                    "tools/here.sh": "echo quiet\n"})
    r = G.check_no_live(root)
    assert r["ok"] is False and r["scripts_unresolved"] == ["tools/gone.sh (run by forge/tests/test_runs.py)"]
    assert r["details"] == ["tools/gone.sh (run by forge/tests/test_runs.py): names no file in the repository or the "
                            "deployed layout (cannot be checked)"]
    (root / "forge/tests/test_runs.py").write_text("import subprocess\nsubprocess.run(['bash', 'tools/here.sh'])\n")
    r = G.check_no_live(root)
    assert r["ok"] is True and r["scripts_read"] == ["tools/here.sh"] and r["scripts_unresolved"] == []


def test_the_c8_texts_say_what_the_scan_does():
    """Draw-5 ci C8 (c): DEPLOYED_ROOT's comment ("the same files as this repository's"), check_no_live's loop-script
    sentence ("NOT read, because nothing here runs them") and forge/search.py sentence ("names no file of this
    repository, so it reads nothing today"), and _scripts_python_runs' "if a test ever RUNS one, it is read" were
    false: the host layout differs, and the scan read nothing at the host path."""
    src = (ROOT / "tools/ci_gate.py").read_text()
    for false in ("the same files as this repository's", "are NOT\n        read, because nothing here runs them",
                  "names no file of this repository, so it reads nothing today",
                  "if a test ever RUNS one, it is read, and it blocks"):
        assert false not in src, false
    assert "fails closed until Khoa ticks" in G.check_no_live.__doc__ and "run_recipe" in G.check_no_live.__doc__


# ------------------------------------------------------------------------------ draw-5 ci MINORs 1-13
def test_an_ini_file_the_tree_holds_is_not_read(tmp_path):
    """Draw-5 ci 1 (REPRODUCED by the adjudicator): a pytest.ini `norecursedirs = sub` -- an option `-o` does not
    override -- gave rc 1, counted 1, incomplete [] and an ok known-red verdict with the NEW failure, in forge/tests/sub,
    never collected. pytest reads no ini file of the tree now (config_args): both failures are read and the NEW one
    blocks, under the same node ids."""
    node = _suite(tmp_path)
    (tmp_path / "forge/tests/sub").mkdir()
    (tmp_path / "forge/tests/sub/test_zz_new.py").write_text("def test_zz_new():\n    assert 0, 'boom'\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\nnorecursedirs = sub\n")
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert r["counted"] == 2 and r["incomplete"] == [], (r["summary"], r["incomplete"])
    assert sorted(f[0] for f in r["failures"]) == [node, "forge/tests/sub/test_zz_new.py::test_zz_new"]
    v = G.known_red_verdict(r, known=[{"node_id": node, "expected_failure": "20 journalled warnings"}])
    assert v["ok"] is False and any("test_zz_new -- NEW" in b for b in v["blocking"])


def test_a_repeated_test_that_stands_in_for_a_new_one_is_never_a_known_red(tmp_path):
    """Draw-5 ci 2 (REPRODUCED by the adjudicator): a conftest's `items[:] = keep + keep` ran the known test twice in
    place of a NEW failure -- collected 2, 2 outcomes, incomplete [] and an ok verdict. check_tests runs pytest -v, and
    a test reported twice is `incomplete`. The control: on the same output, the counts alone show nothing."""
    known = _known_then_new(tmp_path, conftest="def pytest_collection_modifyitems(config, items):\n"
                                               "    keep = [i for i in items if 'zz_new' not in i.nodeid]\n"
                                               "    items[:] = keep + keep\n")
    r = G.check_tests(hermetic_only=False, root=tmp_path)
    assert any("reported more than once" in w for w in r["incomplete"]), r["incomplete"]
    assert G.known_red_verdict(r, known=known)["ok"] is False
    out = "collecting ... collected 2 items\n" + _v_lines([known[0]["node_id"]] * 2, "FAILED") + "=== 2 failed in 0.1s ===\n"
    assert G.run_incomplete(out, 0) == [] and any("more than once" in w for w in G.run_incomplete(out, 0, verbose=True))


@pytest.mark.parametrize("stdout, says", [
    ("collecting ... collected 3 items\n" + "a.py::t1 PASSED [ 33%]\na.py::t2 PASSED [ 66%]\na.py::t3 PASSED [100%]\n"
     "=== 3 passed in 0.1s ===\n", None),
    ("collecting ... collected 2 items\na.py::t1 PASSED [ 50%]\na.py::t1 ERROR [ 50%]\na.py::t2 PASSED [100%]\n"
     "=== 2 passed, 1 error in 0.1s ===\n", None),                          # a teardown error is not a repeat
    ("collecting ... collected 3 items\na.py::t1 PASSED [ 50%]\na.py::t2 PASSED [100%]\na.py::t2 PASSED [100%]\n"
     "=== 3 passed in 0.1s ===\n", "reported more than once"),
    ("collecting ... collected 3 items\n=== 3 passed in 0.1s ===\n", "reported 0 distinct"),     # no per-test line
])
def test_run_incomplete_reads_the_per_test_lines_of_a_verbose_run(stdout, says):
    """Draw-5 ci 2, the reading itself on hand-written -v outputs of the form pytest 9.1.1 printed (d6ci_ev/dup_probe)."""
    why = G.run_incomplete(stdout, 0, verbose=True)
    assert (why == []) if says is None else any(says in w for w in why), why


def test_the_gate_and_the_classifier_run_the_checks_they_name(tmp_path, monkeypatch):
    """Draw-5 ci 5 (surviving mutants): check_test_files removed from CHECKS, its `blocking` set to False, and
    _in_test_dirs read as a bare prefix each left every test green."""
    assert [c.__name__ for c in G.CHECKS] == ["check_no_live", "check_schema", "check_version", "check_fitness",
                                              "check_branch_drill", "check_test_files", "check_tests", "check_known_red",
                                              "check_pinned_scorer"]
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {})
    root = _publish_tree(tmp_path, {"tools/funnel/test_script.py": "def check():\n    return 1\n"})
    r = G.check_test_files(root)
    assert r["ok"] is False and r["blocking"] is True
    assert G._in_test_dirs("forge/tests/test_a.py") and not G._in_test_dirs("forge/testsX/test_a.py")


def test_the_classifier_arm_reads_the_narrowers_and_both_arms(tmp_path, monkeypatch):
    """Draw-5 ci 5: run_arm without _collection_narrowers, and main() reading only the DATA arm's completeness, each
    left every test green. A root conftest's collect_ignore makes an arm incomplete; a CLEAN arm that was cut short
    makes the classification INVALID with nothing written."""
    import ci_classify as C
    _known_then_new(tmp_path, conftest='collect_ignore = ["forge/tests/test_zz_new.py"]\n')
    arm = C.run_arm(tmp_path, sys.executable, ["forge/tests", "tools/tests"])
    assert any("collect_ignore" in w for w in arm["incomplete"]), arm["incomplete"]
    out = tmp_path / "ci_data_bound.json"
    monkeypatch.setattr(C, "OUT", out)
    monkeypatch.setattr(C, "tests_hash", lambda root=None: "t")
    monkeypatch.setattr(C, "code_version", lambda root=None: "c")
    monkeypatch.setattr(C, "suites", lambda root=None: ["forge/tests"])
    whole = {"failed": set(), "collect_errors": set(), "summary": "1 passed", "incomplete": []}
    monkeypatch.setattr(C, "run_arm", lambda cwd, python, suite=None: dict(
        whole, incomplete=["pytest ended the run early: stopping after 1 failures"]) if Path(cwd).name == "clean" else whole)
    (tmp_path / "clean").mkdir()
    assert C.main(["--clean", str(tmp_path / "clean"), "--clean-python", sys.executable]) == 1 and not out.exists()


def test_a_self_bound_argv_is_read_by_one_binding_and_a_cycle_ends():
    """Draw-5 ci 5, the C4 mutants that survived: `seen` not carried down the walk (a two-name cycle then recursed
    until the step budget) and the other end of the binding list taken. The reading pinned: one binding per side of
    a `+`, the first in _bindings' order, which walks statements last to first -- so here the LATER assignment
    (MEASURED 2026-09-24; check_no_live's WHAT THIS IS NOT names what it leaves unread). The control: run(X) reads
    both."""
    assert G._scripts_python_runs("import subprocess\na = b + ['-x']\nb = a + ['-y']\nsubprocess.run(a + ['z'])\n") == []
    two = "import subprocess\nX = ['tools/a.sh']\nX = ['tools/b.sh']\nsubprocess.run(X + ['-v'])\n"
    assert G._scripts_python_runs(two) == ["tools/b.sh"]
    assert sorted(G._scripts_python_runs(two.replace("X + ['-v']", "X"))) == ["tools/a.sh", "tools/b.sh"]


def test_the_spawners_the_draw5_audit_found_unread_are_read(tmp_path):
    """Draw-5 ci 7 (REPRODUCED by the adjudicator): os.posix_spawn and pty.spawn read nothing, and
    `getattr(sys, "path").insert(...)` gave ok=True with nothing unread while `sys.path.insert` blocked."""
    assert G._scripts_python_runs("import os\nos.posix_spawn('tools/x.sh', ['tools/x.sh'], {})\n") == ["tools/x.sh"]
    assert G._scripts_python_runs("import os\nos.posix_spawnp('tools/y.sh', ['y'], {})\n") == ["tools/y.sh"]
    assert G._scripts_python_runs("import pty\npty.spawn(['tools/z.sh'])\n") == ["tools/z.sh"]
    root = _publish_tree(tmp_path, {"forge/tests/test_g.py": "import sys\ngetattr(sys, 'path').insert(0, 'elsewhere')\n"
                                                             "import hidden\n",
                                    "elsewhere/hidden.py": 'ARGV = ["forge/runner.py", "%s"]\n' % LIVE})
    r = G.check_no_live(root)
    assert r["details"] == ["elsewhere/hidden.py:1"] and r["closure_unread"] == []


def test_a_restore_of_a_saved_sys_path_adds_nothing_and_an_unknown_write_is_named(tmp_path):
    """Draw 6: forge/gen/spend.py _predict() does `saved = list(sys.path)` ... `sys.path[:] = saved`, and the scorer's
    closure now reaches it (forge/submit.py imports forge.gen.repair); the walk listed that restore unread, and the
    real closure test requires none. A copy of sys.path restored adds no directory. The control: a write the walk
    cannot evaluate is still named."""
    for i, saved in enumerate(("list(sys.path)", "sys.path[:]", "sys.path.copy()")):
        root = _publish_tree(tmp_path / str(i),
                             {"forge/offline/benchmark.py": "import sys\n\ndef f():\n    saved = %s\n    try:\n"
                                                            "        sys.path.insert(0, 'tools')\n    finally:\n"
                                                            "        sys.path[:] = saved\n" % saved})
        assert F.import_closure(root=root)["unread"] == [], saved
    (root / "forge/offline/benchmark.py").write_text("import sys\n\ndef f(x):\n    sys.path[:] = x\n")
    assert F.import_closure(root=root)["unread"] == ["forge/offline/benchmark.py:4"]


def test_readers_that_crashed_unnamed_now_name_the_file(tmp_path, monkeypatch):
    """Draw-5 ci 8 (REPRODUCED by the adjudicator; each failed closed as a crash): a non-UTF-8 workflow raised
    UnicodeDecodeError out of check_no_live; a conftest too deep to parse raised out of _collection_narrowers; a check
    that raises (a tools/ci_fixture.py that does not parse) left gate() with no verdict. Each is named now, and a
    raising CHECKS entry returns a failed, blocking result -- which ci_publish's data_tier also reads."""
    root = _publish_tree(tmp_path, {"forge/tests/test_ok.py": "def test_ok():\n    pass\n"})
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/bad.yml").write_bytes(b"name: x\n\xff\xfe\n")
    r = G.check_no_live(root)
    assert r["ok"] is False and ".github/workflows/bad.yml (cannot be checked: UnicodeDecodeError)" in r["details"]
    (root / "forge/tests/conftest.py").write_text("x = " + "1+" * 200000 + "1\n")
    said = G._collection_narrowers(root, ["forge/tests"])
    assert len(said) == 1 and said[0].startswith("forge/tests/conftest.py cannot be read (")

    def check_boom():
        raise SyntaxError("tools/ci_fixture.py does not parse")
    printed = []
    assert G.gate(checks=(G._contained(check_boom),), out=printed.append) == 1
    assert any("[FAIL] boom" in l and "SyntaxError" in l for l in printed) and printed[-1].strip() == "VERDICT BLOCKED on boom"
    assert all(hasattr(c, "__wrapped__") for c in G.CHECKS)


def test_the_slow_paths_that_failed_closed_as_hangs_are_bounded():
    """Draw-5 ci 9 (the adjudicator's inputs; re-measured 2026-09-24, d6ci_ev/slow_probe.py): "sudo -u -u ... !" made
    the launcher regex backtrack through every split of its options (17 ms at 22, about x2.5 per two; about 4 s at
    34 before the fix), and k self-rebinds `cmd = cmd + [...]` made the argv walk factorial (0.19 s at k=8, x9 per
    rebind). The options are possessive now, and the walk has a step budget whose overrun is RecursionError, named by
    check_no_live's per-file handler."""
    import time
    line = "sudo" + " -u" * 34 + " !"
    t = time.time()
    G._SH_AT_COMMAND.search(line)
    G._TEMPLATE_COMMAND.match(line)
    assert time.time() - t < 1.0
    src = "import subprocess\ndef f():\n" + "".join("    cmd = cmd + ['-%d']\n" % i for i in range(9)) + "    subprocess.run(cmd)\n"
    t = time.time()
    with pytest.raises(RecursionError):
        G._scripts_python_runs(src)
    assert time.time() - t < 1.0
    assert G.ARGV_WALK_STEPS == 10_000


def test_a_file_listed_as_a_script_that_now_holds_a_test_blocks(tmp_path, monkeypatch):
    """Draw-5 ci 10: the _SCRIPT listing reason ("no test pytest collects") was never re-read against the file, so a
    listed script that gained a test was run by no tier with a false reason. The control: a real script passes."""
    root = _publish_tree(tmp_path, {"tools/funnel/test_s.py": "def check():\n    return 1\n"})
    monkeypatch.setattr(G, "NOT_RUN_OUTSIDE_TEST_DIRS", {"tools/funnel/test_s.py": G._SCRIPT})
    assert G.check_test_files(root)["ok"] is True
    (root / "tools/funnel/test_s.py").write_text("def test_s():\n    assert 0\n")
    r = G.check_test_files(root)
    assert r["ok"] is False and r["details"][0].startswith("tools/funnel/test_s.py -- listed as a script")


def test_the_branch_drill_prints_not_run_not_pass_on_a_hosted_runner(tmp_path):
    """Draw-5 ci 13 / round 3 m17 (REPRODUCED by the adjudicator): in the hermetic tier check_branch_drill returned
    ok=True and gate() printed "[PASS] branch-drill NOT RUN ...". It prints [NOT RUN]; it still does not block
    there (the tier cannot run it; the data tier does)."""
    printed = []
    assert G.gate(checks=(lambda: G.check_branch_drill(_root(tmp_path)),), out=printed.append) == 0
    line = next(l for l in printed if "branch-drill" in l)
    assert line.strip().startswith("[NOT RUN] branch-drill") and "[PASS]" not in line


def test_the_draw5_texts_say_what_the_code_does():
    """Draw-5 ci 1 and 13: sentences that claimed more than the code does, each re-worded. What must be gone, and
    what must now be said."""
    gate = (ROOT / "tools/ci_gate.py").read_text()
    for false in ("so an ini file cannot narrow what is collected",           # the PYTHON_FILES comment
                  "no conftest the run loads can narrow collection:",           # known_red_verdict's bullet
                  "tools/ci_classify.py SUITES all read suite()",              # the TEST_DIRS comment
                  "DATA tier: everything except the 150 MB-at-import LLM files.",     # check_tests
                  "after the placeholder of a `%` / str.format template"):      # _flag_lines, the pre-C6 rule
        assert false not in gate, false
    assert "THE LIST IS NOT EXHAUSTIVE" in gate
    fx = (ROOT / "tools/ci_fixture.py").read_text()
    assert "the one case that reads files." not in fx and '"route": "auto"' not in fx
    import forge.meaning as M
    assert "generated" in M.ROUTES
    doc = F.__doc__
    nr = doc[doc.index("Decisions NOT reached"):]
    assert all(x in nr for x in ("COMPARE_IS_NOT_GATE3", "watch_rollback_failed", "watch_units_down", "ARMS_PLACEBO"))


def test_a_constant_the_scorer_drops_shows_in_the_diff_instead_of_crashing_the_card():
    """Draw 6: the scoring build removed ARMS_MDR_DRAWS / ARMS_MDR_SEED and card() raised AttributeError, so the gate
    said only "the scorer failed on the truth table". A constant the scorer lacks now reads ABSENT on the card."""
    B = types.SimpleNamespace(PRESENT=1)
    assert F._constant(B, "PRESENT") == 1 and F._constant(B, "GONE") == F.ABSENT
    assert F._constant(B, "PRESENT", lambda v: v + 1) == 2


def test_the_libm_values_are_recorded_to_ten_significant_digits():
    """ARMS_NOMINAL_P comes from math.erfc, which Python takes from the platform's C library; the hosted tier is
    Linux (EX-ANTE: its last bit may differ from macOS's; not observed, no Linux run was made). The card records it
    to 10 significant digits, which keeps every figure the design states."""
    B = F._scorer()
    card = _live_card()["constants"]
    assert card["ARMS_NOMINAL_P"] == [float("%.10g" % p) for p in B.ARMS_NOMINAL_P]
    assert [round(p, 9) for p in card["ARMS_NOMINAL_P"]] == [round(p, 9) for p in B.ARMS_NOMINAL_P]
