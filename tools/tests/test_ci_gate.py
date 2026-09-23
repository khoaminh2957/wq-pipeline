"""Suite for tools/ci_gate.py -- the gate a change must clear.

Each test pins a way the gate was found to be able to lie, on 2026-09-23, by its own first three runs.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ci_gate as G  # noqa: E402


def _root(tmp_path, data=False, classification=None, baseline=None):
    (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
    if data:
        for m in G.DATA_MARKERS:
            (tmp_path / m).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / m).write_text("{}\n")
    if classification is not None:
        (tmp_path / "tools/ci_data_bound.json").write_text(json.dumps(classification))
    if baseline is not None:
        (tmp_path / "tools/ci_baseline.json").write_text(json.dumps(baseline))
    return tmp_path


def test_the_tier_is_decided_by_the_presence_of_the_desks_data(tmp_path):
    assert G.tier(_root(tmp_path)) == "hermetic"
    assert G.tier(_root(tmp_path, data=True)) == "data"


def test_a_measured_red_test_blocks_even_the_tier_that_cannot_run_it(tmp_path):
    """D23: without this, GitHub showed green while a test known to be red existed."""
    root = _root(tmp_path, classification={"red": ["tools/tests/test_x.py::test_y"], "measured_at": "t"})
    r = G.check_known_red(root)
    assert r["ok"] is False and r["blocking"] and "test_y" in r["summary"]
    clean = _root(tmp_path / "b", classification={"red": [], "measured_at": "t"})
    assert G.check_known_red(clean)["ok"] is True


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
    (tmp_path / "forge/tests/test_ok.py").write_text('assert "--live" not in argv\n# never pass --live\n')
    assert G.check_no_live(tmp_path)["ok"] is True
    # the flag is assembled so THIS file does not trip the very check it tests -- which it did on the
    # third Actions run, and which is also the proof that a grep can be walked around (see the gate)
    flag = "--" + "live"
    (tmp_path / "tools/tests/test_bad.py").write_text('run(["runner.py", "%s"])\n' % flag)
    r = G.check_no_live(tmp_path)
    assert r["ok"] is False and "test_bad.py:1" in r["summary"]


def test_the_branch_drill_is_reported_not_run_on_a_hosted_runner_never_as_passed_silently(tmp_path):
    r = G.check_branch_drill(_root(tmp_path))
    assert "NOT RUN" in r["summary"]
