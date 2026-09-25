"""tools.ci_gate — the checks a change must clear before it may reach the pipeline (D4, D9).

Khoa's D9 asked for a gate that blocks on REGRESSION against the live version, plus tests, lint and
schema. The regression half is NOT in this gate (round 2, A2): under D14 a candidate version has
produced no rows at merge time, so the pre-merge gate pins the SCORER instead (check_pinned_scorer),
and judging a version's output is benchmark.compare(), after it has run -- which nothing calls yet.
The 4-per-day floor is REPORTED and never blocks, because at the measured rate every version fails it
and a gate on the floor would freeze all development. That asymmetry is the design, not a compromise.

WHY THIS FILE EXISTS RATHER THAN A PILE OF YAML STEPS. Every check here runs identically on a laptop,
on the VPS and inside GitHub Actions, so "it passed on my machine" and "it passed in CI" are the same
sentence. The Actions workflow is a thin caller; the judgement lives here where it can be tested.

WHAT IT CANNOT DO, STATED RATHER THAN HIDDEN. Some tests load `fetched/rc/field_labels.jsonl` (101 MB),
a field catalogue (50 MB) or the desk's journal. None of it can live in a GitHub repository -- the hard
limit is 100 MB per file -- so a hosted runner cannot execute them. This gate therefore reports THREE
things, never one: tests that passed, tests that could not run here, and, FILE BY FILE, where each is
covered instead -- tools/ci_publish.py's data tier for the tests the classification measured data-bound --
or that it is NOT COVERED pre-merge: the two LLM files, which no tier here runs (round 2, S6-NL: this used
to say "the VPS deploy smoke" and "MacBook pre-push", neither of which ran them; draw-3 ci SERIOUS 6: then
"the data tier" for all of them, which skips the LLM files too; draw3_fix ci 3: then the VPS
wq-forge-tests.timer, with a reading frozen into a constant that nothing re-read -- dropped by the
orchestrator decision under D42). A gate that printed "N passed" while silently running fewer would be
lying in the most damaging way available to it, and so would a pytest run that stopped early and still
exited 1 (draw3_fix ci 2). Before anything reads a run, check_tests shows that every test pytest COLLECTED
ran and was counted, and that nothing it can read narrowed what pytest collects (run_incomplete,
_collection_narrowers). Draw4_build ci 2: this said "the run was the whole suite", which is more than those
readings show -- what they cannot see is named in check_tests.

WHICH TEST FILES (round 3 S6). The suite is no longer two directories by fiat: every test file of the
published subset is found and classified (check_test_files) -- run by the tests check (suite()), or listed in
NOT_RUN_OUTSIDE_TEST_DIRS with its reason and printed NOT COVERED pre-merge. An unlisted test file from which
pytest can collect nothing blocks, so no test file is carried to GitHub without a tier running it or a line
saying no tier does.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import functools
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The directories check_tests always hands pytest. Round 3 S6: they used to BE the suite, so a test file outside
#: them ran in no tier -- the CI/CD attacker's forge/gen/tests/test_b.py (assert False) left the real data_tier()
#: reading `known-red-only`, which deploy accepts. suite() now adds every unlisted test file of the published
#: subset outside them; check_no_live, _loaded_conftests and tools/ci_classify.py suites() all read suite()
#: (draw-5 ci 13: this named the classifier's old SUITES constant).
TEST_DIRS = ("forge/tests", "tools/tests")
#: pytest's own default `python_files`, `python_classes` and `python_functions` (pytest 9.1.1). check_tests passes
#: them with -o (draw4_build ci 2: a pytest.ini `python_files` gave rc 1, counted 1 and an ok known-red verdict
#: while a NEW failure went uncollected), and published_test_files() finds test files by the same patterns. The -o
#: alone did not make the tree's ini harmless -- draw-5 ci 1: its `norecursedirs` still narrowed collection, and
#: this comment said "an ini file cannot narrow what is collected"; pytest now reads no ini file of the tree
#: (config_args).
PYTHON_FILES = ("test_*.py", "*_test.py")
PYTHON_CLASSES, PYTHON_FUNCTIONS = "Test", "test"
#: Round 3 S6: the test files of the published subset outside TEST_DIRS that NO tier runs, each with why. The
#: audit asked the owner to decide for each "run, move or list"; until that decision these are LISTED, never
#: run by this gate, and printed NOT COVERED pre-merge on every run. What was read before listing them
#: (2026-09-23, EX-ANTE from the files; none was run as a test or a script for this list -- `pytest
#: --collect-only`, which imports each, is the only execution, in scratch copies):
#:   * 22 are SCRIPTS: each runs from `if __name__ == "__main__"` (read) and defines no function pytest collects
#:     (MEASURED: `pytest --collect-only` over them in a copy with the desk's data collected 0 tests from each).
#:     Several write outside a temporary directory (read from the tests): state/funnel and state/benchmark
#:     through funnel_run.py --dry-run and config_sweep.py --out-dir, and
#:     /private/tmp/claude-501/-Users-kanenguyen-wq-pipeline/, the repository's old path.
#:     test_run_multisim.py calls run_multisim.live_launch() on an illegal batch and passes only if the precheck
#:     stops it; if the precheck broke, the next step is the one that launches tools/resim_bulk.py (RULE 1).
#:   * 3 define pytest tests (MEASURED in the same copy: 49, 8 and 6 collected). tools/autoloop/test_pipeline.py
#:     is the retired auto-submit path's suite: its tests call tools/autoloop/driver.py submit() with the
#:     module's subprocess replaced by a fake. Whether a tier runs it where the platform credential lives is the
#:     submit-authority question, not a test-infrastructure one.
#:   * In a copy WITHOUT the desk's data, 12 of the 25 fail at import (fetched/rc/*.json, state/benchmark/fixtures).
#: Adding a file here is an edit to the judge with a reason; a listed path that is no longer a test file of the
#: subset blocks (check_test_files), so the list is always exactly the unrun files.
_SCRIPT = ("a script run from __main__, no test pytest collects (round 3 S6: not run by any tier until the owner "
           "decides run, move or list)")
NOT_RUN_OUTSIDE_TEST_DIRS = {
    "tools/autoloop/test_pipeline.py": "49 pytest tests of the retired auto-submit path; they call "
                                       "tools/autoloop/driver.py submit() with its subprocess replaced by a fake -- "
                                       "running them where the credential lives is Khoa's call (round 3 S6)",
    "tools/funnel/test_fault_injection.py": "8 pytest tests of tools/funnel validators; needs fetched/rc/operators.json "
                                            "at import (round 3 S6: not run until the owner decides)",
    "tools/funnel/test_gate_gap.py": "6 pytest tests of tools/funnel/gate_gap.py (round 3 S6: not run until the owner "
                                     "decides)",
    **{"tools/funnel/%s.py" % n: _SCRIPT for n in (
        "test_alpha_score", "test_boost_metric", "test_config_sweep", "test_corr_rank", "test_flex_sweep",
        "test_funnel_run", "test_funnel_stage3", "test_gate_lib", "test_gate_lib_presence", "test_logic_check",
        "test_rank27", "test_rank_gates", "test_regime_audit", "test_resilience_lib", "test_root_sweep",
        "test_second_field_sweep", "test_slot_returnable", "test_stage3_example_spec", "test_stage3_trigger",
        "test_third_field_sweep", "test_version_gate")},
    "tools/funnel/test_run_multisim.py": "a script (run from __main__, no pytest test) that calls "
                                         "run_multisim.live_launch() on an illegal batch; a precheck regression would "
                                         "reach the step that launches tools/resim_bulk.py (RULE 1; round 3 S6)",
}


def _publish_module():
    """tools/ci_publish.py of THIS tree: SUBSET and the sync's filter _synced, which define what CI carries."""
    if str(ROOT / "tools") not in sys.path:
        sys.path.insert(0, str(ROOT / "tools"))
    import ci_publish
    return ci_publish


def _in_test_dirs(rel: str) -> bool:
    return any(rel == d or rel.startswith(d + "/") for d in TEST_DIRS)


def published_test_files(root=ROOT) -> list:
    """Round 3 S6: every file of the published subset -- tools/ci_publish.py SUBSET, through the sync's own filter
    (_synced), the set sync() copies to GitHub -- whose name pytest collects by default (PYTHON_FILES)."""
    P = _publish_module()
    root = pathlib.Path(root)
    out = set()
    for s in P.SUBSET:
        src = root / s
        for p in (sorted(q for q in src.rglob("*") if q.is_file()) if src.is_dir() else [src] if src.is_file() else []):
            if src.is_dir() and not P._synced(p.relative_to(src).as_posix()):
                continue
            if any(fnmatch.fnmatchcase(p.name, g) for g in PYTHON_FILES):
                out.add(p.relative_to(root).as_posix())
    return sorted(out)


def _sets_test_false(body) -> bool:
    """`__test__ = False` among these statements: pytest then collects nothing from the module or class."""
    return any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__test__" for t in n.targets)
               and isinstance(n.value, ast.Constant) and n.value.value is False for n in body)


def collectable(path) -> bool:
    """Whether pytest can collect a test from this file, read from its syntax tree: a module-level function named
    test*, or a class named Test* (or deriving from a *TestCase) holding one. A file that does not parse reads
    True -- pytest will try it, and its collection error blocks the run. Draw-5 ci 4 (MEASURED 2026-09-24, pytest
    9.1.1, scratchpad d6ci_ev/collect_probe): a module setting `__test__ = False`, a Test* class setting it, and a
    Test* class defining `__init__` ("cannot collect ... __init__ constructor", a warning) each collect nothing, and
    read False here; a unittest TestCase defining `__init__` IS collected."""
    try:
        tree = ast.parse(pathlib.Path(path).read_text())
    except (OSError, SyntaxError, ValueError):
        return True
    if _sets_test_false(tree.body):
        return False
    fn = (ast.FunctionDef, ast.AsyncFunctionDef)
    for n in tree.body:
        if isinstance(n, fn) and n.name.startswith(PYTHON_FUNCTIONS):
            return True
        if not isinstance(n, ast.ClassDef) or _sets_test_false(n.body):
            continue
        testcase = any((b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")).endswith("TestCase")
                       for b in n.bases)
        if (testcase or (n.name.startswith(PYTHON_CLASSES) and not any(isinstance(m, fn) and m.name == "__init__"
                                                                        for m in n.body))) \
                and any(isinstance(m, fn) and m.name.startswith(PYTHON_FUNCTIONS) for m in n.body):
            return True
    return False


def classify_test_files(root=ROOT) -> dict:
    """Round 3 S6: every test file of the published subset, each in exactly one class:
      in_test_dirs   under TEST_DIRS: run by check_tests;
      run_outside    outside them, unlisted, and pytest can collect a test from it: suite() hands it to pytest;
      listed         in NOT_RUN_OUTSIDE_TEST_DIRS: run by no tier, printed with its reason;
      no_tier        outside, unlisted, and pytest collects nothing from it: no tier runs it -- BLOCKS;
    plus `stale_listing`, listed paths that are no longer a test file of the subset -- BLOCKS."""
    root = pathlib.Path(root)
    out = {"in_test_dirs": [], "run_outside": [], "listed": [], "no_tier": []}
    files = published_test_files(root)
    for rel in files:
        key = ("in_test_dirs" if _in_test_dirs(rel) else "listed" if rel in NOT_RUN_OUTSIDE_TEST_DIRS
               else "run_outside" if collectable(root / rel) else "no_tier")
        out[key].append(rel)
    out["stale_listing"] = sorted(set(NOT_RUN_OUTSIDE_TEST_DIRS) - set(files))
    return out


def suite(root=ROOT) -> list:
    """The paths check_tests hands pytest: TEST_DIRS, then every test file outside them that is neither listed nor
    uncollectable (classify_test_files `run_outside`). One function for the gate, its no-live scan and
    tools/ci_classify.py (round 3 S6: "derive TEST_DIRS, SUITES and the smoke's path from one function"; the
    deploy smoke's path is tools/deploy.py's, another owner's)."""
    return list(TEST_DIRS) + classify_test_files(root)["run_outside"]
#: Test files that need production data too large for a git host. Named individually so that adding
#: one is a deliberate act with a reason, never a wildcard that quietly grows.
DATA_BOUND = {
    "forge/tests/test_llm_author.py": "forge/llm/verify.py loads fetched/rc/field_labels.jsonl (101 MB)",
    "forge/tests/test_llm_formula.py": "same Context(): field_labels.jsonl + a 50 MB field catalogue",
}
CLASSIFIED = ROOT / "tools/ci_data_bound.json"
#: The files whose presence makes this the DATA tier (the MacBook, the VPS). A hosted runner has none of
#: them, and the gate then runs the HERMETIC tier: the tests measured to need no data. The measurement
#: is tools/ci_classify.py -- a two-arm experiment, never a hand-written list.
DATA_MARKERS = ("state/layered/runs/forge.jsonl", "fetched/rc/fields/USA_TOP3000_d1.jsonl")


def tier(root=ROOT) -> str:
    return "data" if all((root / m).exists() for m in DATA_MARKERS) else "hermetic"


def classification(root=ROOT) -> dict:
    try:
        return json.loads((root / "tools/ci_data_bound.json").read_text())
    except (OSError, ValueError):
        return {}


#: Round 2, A8: the ONE committed allowance a failing test has (Khoa's D23), by exact node id and
#: expected failure text. Its one consumer is tools/ci_publish.py data_tier(), which reads the verdict
#: check_tests attaches -- r["known_red"]["ok"] and ["allowed"] -- and nothing else; a failed tests check
#: that carries no verdict is red there. The classification's "red" list is a measurement: check_known_red
#: BLOCKS on it and nothing allows by it. Draw-3 ci SERIOUS 2: this comment said the same while data_tier
#: still allowed by the classification's red list and the 12-line `details`; it became true with the
#: draw-3 release fix to data_tier, and test_ci_gate.py now runs the real data_tier to hold it true.
KNOWN_RED = "tools/ci_known_red.json"


def known_red(root=ROOT) -> list:
    """The committed known-red entries, validated. Raises ValueError when the file is missing or malformed,
    so a broken allowance allows nothing (every caller fails closed). Draw-3 ci MINOR: an entry that was
    not an object (`{"tests": ["x::t"]}`) raised AttributeError, which no caller catches."""
    try:
        data = json.loads((pathlib.Path(root) / KNOWN_RED).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("%s unreadable: %s" % (KNOWN_RED, exc)) from None
    tests = data.get("tests") if isinstance(data, dict) else None
    if not isinstance(tests, list):
        raise ValueError("%s has no 'tests' list" % KNOWN_RED)
    for t in tests:
        if not isinstance(t, dict):
            raise ValueError("%s: entry %r is not an object with node_id and expected_failure" % (KNOWN_RED, t))
        node, text = t.get("node_id"), t.get("expected_failure")
        if not (isinstance(node, str) and "::" in node):
            raise ValueError("%s: %r is not an exact pytest node id (file::test)" % (KNOWN_RED, node))
        if not (isinstance(text, str) and text.strip()):
            raise ValueError("%s: %s names no expected failure text" % (KNOWN_RED, node))
    return tests


def _run(argv, timeout=1800, cwd=ROOT, env=None):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(cwd), env=env)


_COUNTED = re.compile(r"(\d+) (?:failed|errors?)\b")


def parse_summary(stdout: str) -> tuple:
    """([[node id, failure text], ...], the failed + error count pytest's last line states or None).

    Read from the WHOLE short test summary (round 2, m5: a 12-line cap let new failures through behind
    eleven import errors). A failure's text runs from " - " to the next entry; the last line is the
    count, so the two can be checked against each other.
    """
    lines = (stdout or "").strip().splitlines()
    head = next((i for i, l in enumerate(lines) if "short test summary info" in l), None)
    entries = []
    if head is not None:
        for l in lines[head + 1:-1]:
            if l.startswith(("FAILED ", "ERROR ")):
                node, _, text = l.split(" ", 1)[1].partition(" - ")
                entries.append([node.strip(), text])
            elif entries:
                entries[-1][1] += "\n" + l
    counts = _COUNTED.findall(lines[-1]) if lines else []
    return entries, (sum(int(n) for n in counts) if lines else None)


def _says(expected: str, text: str) -> bool:
    """`expected` appears in `text` as a whole phrase: "20 journalled warnings" is NOT in "120 journalled
    warnings" (a substring test would have allowed it)."""
    return re.search(r"(?<![\w.])%s(?!\w)" % re.escape(expected), text or "") is not None


def known_red_verdict(result: dict, known=None, root=ROOT) -> dict:
    """A8: may a PUBLISH go past this failed tests check? {"ok", "allowed", "blocking", "why"}.

    Round 2 measured three ways the old allowance (the classification's "red" list, matched on node id
    alone) let failures through: a re-classification put every new failure into "red"; the known test
    failing with 54 warnings instead of 20 was allowed; a 12-line cap hid new failures. Now a failure is
    allowed only when ALL of these hold, and anything else blocks:
      * its exact node id is listed in tools/ci_known_red.json, and its text says the listed failure;
      * pytest exited 1 (tests failed) -- an interrupted, crashed or empty run is never a known red;
      * every test pytest collected was reported once and counted, and no conftest the run loads binds a name
        that can narrow collection (NARROWING_NAMES, which is not exhaustive; draw-5 ci 1: this said "can narrow
        collection" of every conftest): check_tests' `incomplete` is a LIST and empty (draw3_fix ci 2: under -x, --maxfail or -k, rc 1 with the
        known test alone was allowed while a NEW failure went unrun; draw4_build ci 3: a result with no
        `incomplete` key read as complete -- absence now blocks, as a missing `counted` already did; draw-5 ci 3:
        so did `incomplete: None`);
      * every entry of the summary was read, and their number equals the count on pytest's last line;
      * the tests check did not also fail for a stale classification (S6-NL). This one can fire only in
        the HERMETIC tier -- check_tests sets `stale` only there -- and ci_publish consumes the verdict only
        in the data tier, where the classification skips nothing (draw-3 ci MINOR; kept for any caller
        that reads the verdict of a hermetic run).
    The GATE still blocks on a known red (D23: CI keeps blocking); this verdict is for tools/ci_publish.py.
    """
    if result.get("ok"):
        return {"ok": True, "allowed": [], "blocking": [], "why": "no failure"}
    blocking = []
    try:
        listed = {t["node_id"]: t["expected_failure"] for t in (known_red(root) if known is None else known)}
    except ValueError as exc:
        listed = {}
        blocking.append("no allowance can apply: %s" % exc)
    if result.get("stale"):
        blocking.append("the classification is stale: %s" % result["stale"])
    if not isinstance(result.get("incomplete"), list):
        # draw-5 ci 3: `incomplete: None` read as complete, as an absent key did before draw4_build ci 3
        blocking.append("the result carries no `incomplete` list (%r): that every collected test ran cannot be shown "
                        "(draw4_build ci 3, draw-5 ci 3)" % (result.get("incomplete", "absent"),))
    elif result["incomplete"]:
        blocking.append("the run was not the whole suite (draw3_fix ci 2): %s" % "; ".join(result["incomplete"]))
    rc = result.get("returncode")
    if rc != 1:
        blocking.append("pytest exited %s, not 1: an interrupted, crashed or empty run is never a known red" % rc)
    failures = result.get("failures") or []
    if not failures:
        blocking.append("no failing test could be read from pytest's short summary")
    elif result.get("counted") != len(failures):
        blocking.append("the summary lists %d failure(s) but pytest's last line counts %s"
                        % (len(failures), result.get("counted")))
    allowed = []
    for node, text in failures:
        if node not in listed:
            blocking.append("%s -- NEW: not in %s" % (node, KNOWN_RED))
        elif not _says(listed[node], text):
            blocking.append("%s -- listed, but failing DIFFERENTLY: expected %r, got %r"
                            % (node, listed[node], (text or "").split("\n", 1)[0][:160]))
        else:
            allowed.append(node)
    ok = not blocking
    return {"ok": ok, "allowed": allowed if ok else [], "blocking": blocking,
            "why": ("only known red, each failing as recorded in %s: %s" % (KNOWN_RED, ", ".join(allowed))) if ok
                   else "%d reason(s) to block" % len(blocking)}


#: Where each test the gate does not run IS run (S6-NL; draw-3 ci SERIOUS 6). One sentence used to cover
#: every skipped file -- "the data tier" -- and it was false for the two DATA_BOUND files, which are
#: --ignore'd in EVERY tier, the data tier included, so ci_publish skips them too.
#:
#: The DATA_BOUND files are NOT COVERED pre-merge. Orchestrator decision under D42 (00_agreements.md): the
#: gate no longer cites the VPS wq-forge-tests.timer as covering them. Nothing reads that timer's result,
#: and it tests the DEPLOYED tree, not the candidate. Draw3_fix ci 3: the constant here said "last read
#: 2026-09-23, 210 passed" and the gate printed it on every run, a reading frozen at the hour it was typed.
#: Reading the timer's result would be a new mechanism (RULE 2) and is not built.
NOT_COVERED_PRE_MERGE = ("NOT COVERED pre-merge: no tier of this gate runs it, and the gate reads no other "
                         "run of it (orchestrator decision under D42)")
#: Round 3 S6: the test files listed in NOT_RUN_OUTSIDE_TEST_DIRS (check_test_files prints each with its reason).
NOT_COVERED_UNTIL_DECIDED = ("NOT COVERED pre-merge: no tier of this gate runs it (round 3 S6: listed in "
                             "NOT_RUN_OUTSIDE_TEST_DIRS until the owner decides run, move or list)")
#: The classification's data-bound tests: the data tier runs the whole suite with no classification skips,
#: and tools/ci_publish.py runs the data tier before every publish (D31).
COVERED_BY_DATA_TIER = "tools/ci_publish.py's data tier, which runs it before every publish"


#: Draw3_fix ci 2 (the adjudicator's adjci_xprobe.py): pytest takes options from the environment, and with
#: the known test failing first and a NEW failure after it, PYTEST_ADDOPTS=-x, --maxfail=1 and -k known each
#: gave rc 1 with only the known failure read -- a run of PART of the suite that the known-red verdict
#: allowed. PYTEST_PLUGINS can load code that does the same. Both are dropped from pytest's environment,
#: and `-o addopts=` empties an ini file's addopts. PY_COLORS=0: with PY_COLORS=1 the summary carried ANSI
#: codes and no entry could be read (that one failed closed).
PYTEST_ENV_DROPPED = ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")
#: the pytest whose human-readable output run_incomplete and parse_summary were measured on (2026-09-23, this
#: Mac). Draw4_build ci 9 (SUSPECTED, not observed): ci.yml installed pytest unpinned; it now installs this
#: version, and test_ci_gate.py holds the two equal. A different pytest on a laptop is not refused here.
PYTEST_MEASURED = "9.1.1"
#: a session banner pytest prints when it ends a run early: "!!!! stopping after 1 failures !!!!",
#: "!!!! Interrupted: 1 error during collection !!!!", "!!!! KeyboardInterrupt !!!!"
_ABORT_BANNER = re.compile(r"^!{3,} .* !{3,}$")
#: under -v pytest prints "collecting ... collected N items" (MEASURED 2026-09-24, pytest 9.1.1)
_COLLECTED = re.compile(r"^(?:collecting \.\.\. )?collected (\d+) items?\b")
_OUTCOME = re.compile(r"(\d+) (passed|failed|skipped|xfailed|xpassed|errors?|deselected)\b")
#: one -v line per test phase that reports: "<node id> PASSED   [ 50%]" (a teardown error adds "<node id> ERROR")
_PROGRESS = re.compile(r"^(\S.*?::\S.*?) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)(?:\s+\[\s*\d+%\])?$")


def _pytest_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in PYTEST_ENV_DROPPED}
    env.update(CI="true", PY_COLORS="0")
    return env


#: Draw-5 ci 1 (REPRODUCED by the adjudicator): a pytest.ini `norecursedirs = sub` narrowed what was collected, an
#: ini option `-o` did not override, and the run read rc 1, counted 1, incomplete [] and an ok known-red verdict with
#: a NEW failure never collected. pytest now reads NO ini file of the tree: `-c` names an empty one written for the
#: run, and --rootdir / --confcutdir are the tree's root, which keeps the node ids and the conftests loaded as before
#: (MEASURED 2026-09-24 on a probe suite, scratchpad d6ci_ev/ini_probe.py: with the ini, 2 collected; with these
#: arguments, 3 and the NEW failure read, node ids unchanged).
def config_args(root, tmpdir) -> list:
    ini = pathlib.Path(tmpdir) / "pytest.ini"
    ini.write_text("[pytest]\n")
    root = str(pathlib.Path(root).resolve())
    return ["-c", str(ini), "--rootdir", root, "--confcutdir", root]


def run_incomplete(stdout: str, deselected_by_gate: int, verbose: bool = False) -> list:
    """Why this pytest run did not run and count every test it COLLECTED, or [] (draw3_fix ci 2). Read from the
    output itself, because the environment is not the only way to shorten a run -- a conftest can set
    maxfail or deselect in a hook:
      * a session banner ("stopping after N failures", "Interrupted", "KeyboardInterrupt");
      * a deselected count DIFFERENT from the one the gate asked for (the classification's list, hermetic tier
        only). Draw4_build ci 8(a): this said "more tests deselected"; the test is `!=`, and fewer blocks as well
        -- `--deselect` matches node ids by prefix, so a count that differs means the selection is not the one
        the gate wrote (C5: a test holds the fewer side);
      * fewer outcomes on pytest's last line than the "collected N items" line (a test that errors in
        teardown is counted twice, so only FEWER is a gap);
      * no "collected" line at all: completeness cannot be shown, and that blocks too;
      * with `verbose` (check_tests runs pytest -v, one line per test): a node id REPORTED MORE THAN ONCE with an
        outcome other than ERROR, or fewer distinct node ids than tests collected and not deselected. Draw-5 ci 2
        (REPRODUCED): a conftest's `items[:] = keep + keep` ran the known test twice in place of a NEW one, and every
        count above matched. A teardown error adds an ERROR line to a test that passed, so ERROR is not a repeat;
        no per-test line at all is a gap. Where the hook came from does not matter: this reads what pytest ran.
    `-q` is not passed, because it drops the "collected" line. WHAT THIS CANNOT SEE: tests pytest never
    collected -- a conftest's collect_ignore or pytest_ignore_collect removes files before "collected N" is
    printed (draw4_build ci 2, measured with a probe suite). _collection_narrowers reads the conftests for
    those; the tree's ini files are not read at all (config_args)."""
    lines = (stdout or "").strip().splitlines()
    why = ["pytest ended the run early: %s" % l.strip("! ") for l in lines if _ABORT_BANNER.match(l.strip())]
    collected = next((int(m.group(1)) for m in map(_COLLECTED.match, lines) if m), None)
    outcomes = {}
    for n, word in _OUTCOME.findall(lines[-1] if lines else ""):
        outcomes[word.rstrip("s") if word.startswith("error") else word] = int(n)
    if outcomes.get("deselected", 0) != deselected_by_gate:
        why.append("%d test(s) deselected, the gate asked for %d" % (outcomes.get("deselected", 0), deselected_by_gate))
    if collected is None:
        why.append("no 'collected N items' line: the run cannot be shown to be the whole suite")
    elif sum(outcomes.values()) < collected:
        why.append("pytest collected %d and its last line accounts for %d: tests were not run"
                   % (collected, sum(outcomes.values())))
    if verbose:
        seen, repeated = set(), []
        for m in map(_PROGRESS.match, lines):
            if m and m.group(2) != "ERROR":
                (repeated if m.group(1) in seen else []).append(m.group(1))
                seen.add(m.group(1))
            elif m:
                seen.add(m.group(1))
        if repeated:
            why.append("%d test(s) reported more than once (%s): a repeated test can stand in for one never run"
                       % (len(repeated), ", ".join(sorted(set(repeated))[:4])))
        if collected is not None and len(seen) < collected - outcomes.get("deselected", 0):
            why.append("pytest collected %d, %d deselected, and reported %d distinct test(s): tests were not run"
                       % (collected, outcomes.get("deselected", 0), len(seen)))
    return why


#: Draw4_build ci 2: names a conftest can define to narrow what pytest COLLECTS, which no count in the output
#: shows (collection happens before "collected N items"). MEASURED on a probe suite (pytest 9.1.1):
#: `collect_ignore = ["test_zz.py"]` in forge/tests/conftest.py printed "1 passed" with rc 0 and the failing
#: test_zz.py never collected. `pytest_plugins` is here because the modules it loads may define the same hooks
#: and are not read. Draw-5 ci 1: a conftest `pytest_pycollect_makeitem` narrowed collection the same way (REPRODUCED
#: by the adjudicator), and pytest_collect_directory, pytest_make_collect_report and pytest_collection can too (EX-ANTE,
#: pytest's hook reference); they are read now. THE LIST IS NOT EXHAUSTIVE: a conftest that narrows collection by
#: other code -- editing config.args or an ini value in pytest_configure, say -- is NOT read, and neither is an
#: installed plugin (entry point). A hook that drops or repeats COLLECTED items (pytest_collection_modifyitems) is read
#: from the output instead (run_incomplete).
NARROWING_NAMES = ("collect_ignore", "collect_ignore_glob", "pytest_ignore_collect", "pytest_collect_file",
                   "pytest_pycollect_makemodule", "pytest_plugins", "pytest_pycollect_makeitem",
                   "pytest_collect_directory", "pytest_make_collect_report", "pytest_collection")


def _collection_narrowers(root, paths) -> list:
    """"<conftest> defines <name>" for each NARROWING_NAMES name bound in the module scope of a conftest.py that
    pytest loads for a run over `paths` (_loaded_conftests) -- by def, class, assignment or import, under an `if`
    or `try` as well -- and for a star import (its names cannot be read). A conftest that does not parse is named."""
    root = pathlib.Path(root)
    F = _fixture_module()
    out = []
    for c in _loaded_conftests(root, paths):
        rel = c.relative_to(root).as_posix()
        try:
            tree = ast.parse(c.read_text())
        except (OSError, SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            # draw-5 ci 8: a 200k-term `1+` chain raised RecursionError and 50k unary minuses MemoryError, unnamed
            out.append("%s cannot be read (%s): whether it narrows collection is unknown" % (rel, type(exc).__name__))
            continue
        names = set()
        for n in [tree] + list(F._own_nodes(tree)):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(n.name)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                names.add(n.id)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                if any(a.name == "*" for a in n.names):
                    out.append("%s star-imports %s: the names it binds cannot be read" % (rel, getattr(n, "module", "")))
                names |= {a.asname or a.name.split(".")[0] for a in n.names}
        out += ["%s defines %s, which can narrow what pytest collects" % (rel, x) for x in NARROWING_NAMES if x in names]
    return out


def check_tests(hermetic_only=None, root=ROOT) -> dict:
    """Run the suite for this tier, and say plainly which part of it did not run and why.

    DATA tier: suite() -- TEST_DIRS and every unlisted collectable test file outside them -- except the 150
    MB-at-import LLM files; the test files listed in NOT_RUN_OUTSIDE_TEST_DIRS are not run either, and
    check_test_files prints them (draw-5 ci 13: this said "everything except the LLM files"). HERMETIC tier:
    additionally skips every test tools/ci_classify.py MEASURED as data-bound (fails without the data, passes with
    it). A test measured RED -- failing even with the data -- is never skipped anywhere.

    `not_run` maps each skipped FILE to why, and `covered_instead_by` maps the same keys to where it is run
    instead (draw-3 ci SERIOUS 6: one string used to cover them all). Deselected tests are grouped by file.

    S6-NL: a STALE classification BLOCKS. It used to print a WARNING beside a PASS (Actions run
    35822646606), so the hermetic tier skipped a list measured on other code and still read green.

    pytest runs with CI=true, as it does on GitHub Actions. MEASURED 2026-09-23 (pytest 9.1.1): without
    it the short summary trims each failure to the terminal width, and the known-red test's node id alone
    is 81 characters (draw3_fix ci 8: this said 83), so its line carried NO failure text on the MacBook --
    A8's text match could never hold there, and the gate would read differently on a laptop and in Actions.

    Draw3_fix ci 2: pytest's environment drops PYTEST_ENV_DROPPED and `-o addopts=` is passed, and
    `incomplete` (run_incomplete) names every sign in the output that a collected test did not run or was not
    counted. An incomplete run is never ok, and the known-red verdict never allows one.

    WHAT `incomplete` CAN AND CANNOT SHOW (draw4_build ci 2: this said "the run was the whole suite"). It shows
    that every test pytest COLLECTED was reported once and counted (run_incomplete; pytest runs -v so each test's
    line can be read -- draw-5 ci 2). What pytest collects is guarded, not proven: no ini file of the tree is read
    (config_args), python_files / python_classes / python_functions are pytest's defaults (-o), and a loaded
    conftest that binds a NARROWING_NAMES name (collect_ignore, pytest_ignore_collect, ...) is `incomplete` too
    (_collection_narrowers). NOT detected: an installed plugin, or conftest code that narrows collection some
    other way (NARROWING_NAMES is not exhaustive).

    Round 3 S6: pytest is handed suite(root) -- TEST_DIRS plus every unlisted test file outside them that pytest
    can collect from -- not TEST_DIRS alone. A suite that cannot be derived blocks.
    """
    root = pathlib.Path(root)
    hermetic = (tier(root) == "hermetic") if hermetic_only is None else hermetic_only
    try:
        paths, narrowing = suite(root), None
    except Exception as exc:  # noqa: BLE001 -- a suite that cannot be derived is never "the suite"
        paths, narrowing = list(TEST_DIRS), "the suite could not be derived (%s: %s)" % (type(exc).__name__, exc)
    argv = [sys.executable, "-m", "pytest", *paths, "--no-header", "-rfE", "-p", "no:cacheprovider", "-o", "addopts=",
            "-o", "python_files=" + " ".join(PYTHON_FILES), "-o", "python_classes=" + PYTHON_CLASSES,
            "-o", "python_functions=" + PYTHON_FUNCTIONS]
    for f in DATA_BOUND:
        argv += ["--ignore", f]
    skipped = {}
    stale = None
    deselected = 0
    if hermetic:
        cls = classification(root)
        for f in cls.get("ignore_files", []):
            argv += ["--ignore", f]
            skipped[f] = "fails at import without the desk's data (measured %s)" % cls.get("measured_at")
        per_file = {}
        for n in cls.get("deselect", []):
            argv += ["--deselect", n]
            deselected += 1
            per_file[n.split("::", 1)[0]] = per_file.get(n.split("::", 1)[0], 0) + 1
        for f, k in sorted(per_file.items()):
            skipped["%s (%d test(s))" % (f, k)] = "measured data-bound (classification %s)" % cls.get("measured_at")
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            import ci_classify as CC
            if cls and (cls.get("tests_hash") != CC.tests_hash(root) or cls.get("code_version") != CC.code_version(root)):
                stale = "tests or code changed since the classification; re-measure it (tools/ci_classify.py)"
        except Exception as exc:  # noqa: BLE001 -- unverifiable is stale: it blocks
            stale = "could not verify the classification is current (%s)" % type(exc).__name__
        if not cls:
            stale = "no classification file; every data-bound test will fail here"
    with tempfile.TemporaryDirectory(prefix="wq-ci-ini-") as d:
        r = _run(argv + ["-v"] + config_args(root, d), cwd=root, env=_pytest_env())
    lines = (r.stdout or "").strip().splitlines()
    tail = [(lines[-1:] or [""])[0].strip("= ")]
    incomplete = (run_incomplete(r.stdout, deselected, verbose=True) + _collection_narrowers(root, paths)
                  + ([narrowing] if narrowing else []))
    # the first Actions run printed only "5 errors in 2.21s"; the cause had to be reproduced by hand.
    # A gate's log must say WHY it blocked.
    why = [l for l in lines if l.startswith(("FAILED ", "ERROR ")) or "ModuleNotFoundError" in l
           or "ImportError" in l][:12]
    failures, counted = parse_summary(r.stdout)
    not_run = dict(DATA_BOUND)
    not_run.update(skipped)
    covered = {f: NOT_COVERED_PRE_MERGE if f in DATA_BOUND else COVERED_BY_DATA_TIER for f in not_run}
    out = {"name": "tests", "ok": r.returncode == 0 and stale is None and not incomplete,
           "summary": "[%s tier] %s%s%s" % ("hermetic" if hermetic else "data", tail[0],
                                            ("  BLOCKED, STALE CLASSIFICATION: " + stale) if stale else "",
                                            ("  BLOCKED, NOT THE WHOLE SUITE: " + "; ".join(incomplete)) if incomplete else ""),
           "details": why, "not_run": not_run, "covered_instead_by": covered,
           "returncode": r.returncode, "failures": failures, "counted": counted, "stale": stale,
           "incomplete": incomplete, "blocking": True}
    if not out["ok"]:
        out["known_red"] = known_red_verdict(out, root=root)
    return out


def check_test_files(root=ROOT) -> dict:
    """Round 3 S6: every test file CI carries is run by a tier or listed with why -- never neither.

    The finding: TEST_DIRS, tools/ci_classify.py SUITES and the deploy smoke all passed explicit directories, so a
    failing test file anywhere else was run by no tier and the publish went through (the CI/CD attacker ran the
    real data_tier() on forge/gen/tests/test_b.py: `known-red-only`). Now (classify_test_files):
      * a test file outside TEST_DIRS that pytest can collect from is RUN -- suite() hands it to check_tests, so
        when it fails, the tests check blocks;
      * one listed in NOT_RUN_OUTSIDE_TEST_DIRS is printed NOT COVERED pre-merge with its reason;
      * one that is neither -- no test pytest collects, not listed -- BLOCKS here: no tier runs it;
      * a listed path that is no longer a test file of the subset BLOCKS too, so the list stays the set of files
        it describes.
    Deciding the listed files (run, move or list) is the owner's; this check only makes the decision visible."""
    try:
        c = classify_test_files(root)
    except Exception as exc:  # noqa: BLE001 -- test files that cannot be found cannot be shown to be run
        return {"name": "test-files", "ok": False, "blocking": True,
                "summary": "the published subset's test files could not be found: %s: %s" % (type(exc).__name__, exc)}
    root = pathlib.Path(root)
    bad = (["%s -- a test file outside %s from which pytest collects no test, and not listed in "
            "NOT_RUN_OUTSIDE_TEST_DIRS: no tier runs it (round 3 S6); make it a pytest file, move it, or list it "
            "with a reason" % (f, " and ".join(TEST_DIRS)) for f in c["no_tier"]]
           + ["%s -- listed in NOT_RUN_OUTSIDE_TEST_DIRS but no longer a test file of the published subset: "
              "delete the entry" % f for f in c["stale_listing"]]
           # draw-5 ci 10: the _SCRIPT reason ("no test pytest collects") was never re-read against the file
           + ["%s -- listed as a script from which pytest collects no test, but it now holds one: run it, or list it "
              "with a true reason" % f for f in c["listed"]
              if NOT_RUN_OUTSIDE_TEST_DIRS[f] == _SCRIPT and collectable(root / f)])
    listed = {f: NOT_RUN_OUTSIDE_TEST_DIRS[f] for f in c["listed"]}
    n = sum(len(c[k]) for k in ("in_test_dirs", "run_outside", "listed", "no_tier"))
    return {"name": "test-files", "ok": not bad, "blocking": True, "details": bad,
            "summary": ("%d test file(s) in the published subset: %d under %s and %d outside them run by the tests "
                        "check%s; %d listed as run by no tier" % (
                            n, len(c["in_test_dirs"]), " and ".join(TEST_DIRS), len(c["run_outside"]),
                            (" (%s)" % ", ".join(c["run_outside"])) if c["run_outside"] else "", len(listed)))
                       + ("" if not bad else "  BLOCKED: %d file(s) no tier runs or stale entries" % len(bad)),
            "not_run": listed, "covered_instead_by": {f: NOT_COVERED_UNTIL_DECIDED for f in listed}}


#: S7-NL: the directories whose Python the no-live scan reads -- the pipeline, its tools and the VPS side.
NO_LIVE_DIRS = ("forge", "tools", "vps")
#: the two flags that spend: simulations (forge/runner.py, tools/layered_sim.py) and an irreversible POST
#: (forge/submit.py, tools/climb_submit.py). Written as patterns, never as the bare flags, so that this
#: file does not trip its own scan.
_FLAG = re.compile(r"(?<![\w-])--(?:live|submit)(?![\w-])")
_EXACT = re.compile(r"--(?:live|submit)(?:=.*)?", re.S)
_COMMAND = re.compile(r"(?:\.py|\.sh|\bpython[\d.]*|\s-m\s+[\w.]+)\b.*?(?<![\w-])--(?:live|submit)(?![\w-])", re.S)
#: Lines the scan reads as passing a flag but that pass nothing, each with why, keyed by path and the EXACT
#: stripped line: an edit to the line voids its exemption and the scan fires again. Adding one is an edit to
#: the judge, in the open, with a reason -- never a comment in the judged file.
#:
#: EMPTY since 2026-09-23 ~23:10 +07, which closes the open RULE 2 item draw3_fix ci 9 named: the one entry
#: (tools/notify_lint.py COMMAND_TOKENS, never ticked) was deleted once that file's owner built the token as
#: "--" + "submit" -- re-read then, the literal is gone and the real tree's scan passes without it
#: (test_the_exemption_list_is_empty_and_the_real_tree_passes_without_it).
NO_LIVE_EXEMPT = {}


def _passes_a_flag(node, parents) -> bool:
    """Is this string constant, which holds a flag, PASSED as an argument? Walk up to the first node that
    decides: a bare string statement (a docstring or a note) is not; a comparison or an assertion reads the
    flag and cannot pass it ("--live" not in cmd); a call passes it -- unless the call is add_argument,
    which DEFINES the flag; anything a statement holds as data (assigned, returned, iterated) is passed.
    A call inside an assert still runs, so `assert run([.., flag])` is passed, not asserted."""
    child, p = node, parents.get(node)
    while p is not None:
        if isinstance(p, ast.Expr) and isinstance(child, (ast.Constant, ast.JoinedStr)):
            return False
        if isinstance(p, (ast.Compare, ast.Assert)):
            return False
        if isinstance(p, ast.Call):
            f = p.func
            return (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)) != "add_argument"
        if isinstance(p, ast.stmt):
            return True
        child, p = p, parents.get(p)
    return True


#: a %-format or str.format placeholder. In a command template it stands for the script or interpreter, so
#: "%s --live" % script passes the flag exactly as f"{script} --live" does. An f-string is read as ONE
#: template, "{}" standing for each value (_template_of; draw3_fix ci 4: its literal part " --submit --cap 4"
#: alone is not the flag, and f"{script} --submit --cap 4" passed).
_PLACEHOLDER = r"(?:%(?:\(\w+\))?[-#0 +]*\d*(?:\.\d+)?[sdrfi]|\{[^{}]*\})"
#: a shell, by path or by name
_SHELL = r"(?:(?:/usr)?/bin/)?(?:ba|z|da)?sh"
#: The words that may stand before a command, each with the single-letter options that TAKE an argument (read
#: from their manuals: sudo -u USER, -g GROUP, ...; timeout -s SIGNAL, -k DURATION; nice -n N; env -u NAME,
#: -C DIR, -S STRING). Draw4_build ci 6: `sudo -u wq x.sh` read "wq" as the command, `nice -n 5 %s` and `timeout
#: -s KILL 60 %s` were not read at all. One table for argv lists (_argv_scripts) and for shell text (_LAUNCHER).
LAUNCHER_OPTION_ARGS = {"sudo": "ugCDhpRrTU", "nice": "n", "env": "uCS", "timeout": "sk",
                        "exec": "", "nohup": "", "setsid": ""}


def _opts(word):
    """A launcher's options, POSSESSIVE (`*+`, Python 3.11+). Draw-5 ci 9 (the adjudicator's input): "sudo -u -u ...
    !" can be split into options two ways at every "-u", and the search backtracked through all of them -- 7 ms at
    20 options, 17 ms at 22, about x2.5 per two (re-measured 2026-09-24, scratchpad d6ci_ev/slow_probe.py). Taken
    possessively, the options are read once, greedily; a line whose option ARGUMENT is the script (`sudo -u x.sh`,
    malformed: -u takes a user) no longer reads x.sh."""
    takes = LAUNCHER_OPTION_ARGS.get(word, "")
    return r"(?:\s+-[%s]\s+\S+|\s+-\S+)*+" % takes if takes else r"(?:\s+-\S+)*+"


#: what may stand before a command word in shell text: a LAUNCHER_OPTION_ARGS word and its options (timeout also
#: takes its DURATION), source / . / a shell and their options, and VAR=value assignments (draw3_fix ci 4:
#: `timeout N` and `env` were not read; draw4_build ci 6: `A=1 x.sh`, `timeout 60 x.sh` in a command line)
_LAUNCHER = r"(?:(?:%s|(?:source|\.|%s)(?:\s+-\S+)*+|timeout%s\s+\d\S*|\w+=\S*)\s+)" % (
    "|".join("%s%s" % (w, _opts(w)) for w in LAUNCHER_OPTION_ARGS if w != "timeout"), _SHELL, _opts("timeout"))
#: what separates the commands of one line of shell: && || ; | & and a NEWLINE (draw4_build ci 6: a template whose
#: commands were separated by "\n" was read as one command). "(" is NOT one: MEASURED 2026-09-23, with it this
#: file's own summary "... passes --live or --submit (%s)" % read was flagged.
_SEPARATOR = r"&&|\|\||[;|&\n]"
#: one COMMAND of a template whose command word -- behind any launcher -- is filled in by a placeholder.
#: MEASURED 2026-09-23 on the adjudicator's copy: "a placeholder anywhere before the flag" flagged the old gate's
#: own prose summary, "no Python file under %s ... passes --live or --submit (...)". Draw3_fix ci 4: anchored at
#: the start of the whole string only, it missed "cd /opt/wq && %s --submit" % s.
_TEMPLATE_COMMAND = re.compile(r"^\s*%s*\S*%s" % (_LAUNCHER, _PLACEHOLDER))


def _template_passes(value: str) -> bool:
    """Some COMMAND of `value` (split at _SEPARATOR) has a placeholder as its command word AND holds the flag.
    Draw4_build ci 7 (fails closed; a regression of draw3_fix ci 4): the flag and the placeholder were looked for
    in the whole string, so the prose f"{n} alphas staged; pass --submit to post them" was flagged -- its
    placeholder is the first command's word and its flag is in the second, whose word is "pass".
    Draw-5 ci 6 (a regression of C6, which made a newline a separator): a backslash-newline is a shell LINE
    CONTINUATION, so it is joined before the split -- "%s \\<newline>  --submit --cap 4" read False. (A non-raw
    Python literal drops `\\<newline>` itself; what reaches here is written `\\\\\\n` or raw.)"""
    value = value.replace("\\\n", " ")
    return any(_FLAG.search(c) and _TEMPLATE_COMMAND.match(c) for c in re.split(_SEPARATOR, value))


def _argv_source(node, parents):
    """How a string constant becomes a command (draw-3 ci SERIOUS 5): "split" when it is split into an argv
    ("--submit --cap 4".split(), shlex.split(...)), "template" when it is the template of `%` or
    str.format, else None."""
    p = parents.get(node)
    if isinstance(p, ast.Attribute) and p.value is node and isinstance(parents.get(p), ast.Call) \
            and parents[p].func is p and p.attr in ("split", "format"):
        return "split" if p.attr == "split" else "template"
    if isinstance(p, ast.BinOp) and isinstance(p.op, ast.Mod) and p.left is node:
        return "template"
    if isinstance(p, ast.Call) and p.args and p.args[0] is node and isinstance(p.func, ast.Attribute) \
            and p.func.attr == "split" and getattr(p.func.value, "id", None) == "shlex":
        return "split"
    return None


def _passes_in_argv(value: str, how) -> bool:
    """A split string passes a flag when one of its tokens IS the flag; any other string does when one of its
    commands has a placeholder as its command word and holds the flag (_template_passes: the script it will be
    filled with). A template of prose -- "no file under %s passes --live" -- starts with a word and is not read
    as passing it; a template that names its script ("python3 %s --live") is already read by _COMMAND.
    Draw4_build ci 6: only the left operand of `%` and the receiver of .format were read as templates, so
    `T = "%s --live"; T % s` walked through; a string whose command word is a placeholder is a template
    wherever it stands."""
    if how == "split":
        return any(_EXACT.fullmatch(t) for t in value.split())
    return _template_passes(value)


def _template_of(n) -> str:
    """An f-string as the template it is: its literal parts, with "{}" where a value is formatted in."""
    return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)


def _flag_lines(source: str) -> list:
    """Line numbers where a string passes --live or --submit: the flag alone (an argv element), after a
    script in a command line ("... forge/submit.py --submit"), as a token of a string split into an argv
    (draw-3 ci SERIOUS 5), or in a COMMAND of a template whose command word, behind any launcher, is a
    placeholder -- a %-format or str.format string wherever it stands (draw4_build ci 6), an f-string read whole
    with "{}" for each value (draw3_fix ci 4), the commands split at && || ; | & and a newline, a backslash-newline
    joined (_template_passes; draw4_build ci 7, draw-5 ci 13: this said "after the placeholder" of the whole
    string, the rule before C6). Prose that merely names the flag ("pass --live to spend") is none of these and is
    not read as passing it."""
    tree = ast.parse(source)
    parents = {ch: n for n in ast.walk(tree) for ch in ast.iter_child_nodes(n)}
    hits = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            value, how = n.value, _argv_source(n, parents)
        elif isinstance(n, ast.JoinedStr):
            value, how = _template_of(n), "template"
        else:
            continue
        if (_EXACT.fullmatch(value.strip()) or _COMMAND.search(value) or _passes_in_argv(value, how)) \
                and _passes_a_flag(n, parents):
            hits.add(n.lineno)
    return sorted(hits)


# ------------------------------------------------------- draw-3 ci SERIOUS 5: the shell a test can reach
#: a .sh path at COMMAND position in a line of shell: first on the line, or after ; & | ( or a backtick,
#: behind any _LAUNCHER (draw4_build ci 6: `timeout 60 x.sh`, `A=1 x.sh` and `sudo -u wq x.sh` were not read), as
#: a relative path or an absolute one (_resolve_script maps the deployed tree's prefix)
_SH_AT_COMMAND = re.compile(r"(?:^|[;&|(`])\s*%s*((?:\.{0,2}/)?[\w./-]*\w\.sh)(?![\w.-])" % _LAUNCHER)
_SH_WORD = re.compile(r"^%s$" % _SHELL)
_SH_PATH = re.compile(r"^(?:\.{0,2}/)?[\w./-]*\w\.sh$")
#: The standard library's process spawners, by where their command is. Draw4_build ci 6: one set said "their first
#: argument is a command", which is false for os.spawn* (the first is the MODE) and for the varargs forms (the
#: program, then each argument separately), so `os.spawnl(os.P_WAIT, "/bin/bash", "bash", "x.sh")` and
#: `create_subprocess_exec("bash", "x.sh")` read nothing.
#:   COMMAND   the first positional argument, or `args=`, is the command: an argv, a command line or a path;
#:   VARARGS   {name: index of the program}: the program, then its argv[0] (exec*/spawn* l-forms, which the
#:             program ignores as a word) or its first argument (create_subprocess_exec), then the rest;
#:   VECTOR    {name: index of the program}: the program, then an argv whose [0] is the program's own name.
#: Draw-5 ci 7: os.posix_spawn / posix_spawnp (VECTOR: path, argv, env) and pty.spawn (COMMAND: its argv first) read
#: nothing; "spawn" is read by name, so any call named spawn with a command first is read (pexpect.spawn too).
_SPAWN_COMMAND = frozenset(("run", "call", "check_call", "check_output", "Popen", "system", "popen", "getoutput",
                            "getstatusoutput", "create_subprocess_shell", "spawn"))
_SPAWN_VARARGS = {"execl": 0, "execle": 0, "execlp": 0, "execlpe": 0, "spawnl": 1, "spawnle": 1, "spawnlp": 1,
                  "spawnlpe": 1, "create_subprocess_exec": 0}
_SPAWN_VECTOR = {"execv": 0, "execve": 0, "execvp": 0, "execvpe": 0, "spawnv": 1, "spawnve": 1, "spawnvp": 1,
                 "spawnvpe": 1, "posix_spawn": 0, "posix_spawnp": 0}
_SPAWN = _SPAWN_COMMAND | set(_SPAWN_VARARGS) | set(_SPAWN_VECTOR)
#: the words an argv may start with before its command (LAUNCHER_OPTION_ARGS: each takes options, some of which
#: take an argument; env also takes VAR=value words, timeout a duration)
_ARGV_LAUNCHERS = frozenset(LAUNCHER_OPTION_ARGS)
#: tools/deploy.py REMOTE: the deployed tree on the host (draw4_build ci 6: an absolute path such as /opt/wq/tools/x.sh
#: named no repository file). It is NOT laid out as this repository is (draw-5 ci C8; the earlier comment said "the
#: same files as this repository's"): tools/deploy.py PLAN ships vps/forge_loop.sh as /opt/wq/forge_loop.sh, and
#: likewise every other file entry whose two paths differ -- _deployed_layout() reads that mapping.
DEPLOYED_ROOT = "/opt/wq"
DEPLOY_PY = "tools/deploy.py"


def _call_name(f):
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _fixture_module():
    """tools/ci_fixture.py of THIS tree (the gate's, whatever root is scanned): its scoped name bindings and
    its import-closure walk. Put on sys.path once."""
    if str(ROOT / "tools") not in sys.path:
        sys.path.insert(0, str(ROOT / "tools"))
    import ci_fixture
    return ci_fixture


def _path_constant(e):
    """The string a path expression ends in -- "x.sh", ROOT / "x.sh", str(...), Path(...), f"{ROOT}/x.sh" --
    or None."""
    if isinstance(e, ast.Constant) and isinstance(e.value, str):
        return e.value
    if isinstance(e, ast.JoinedStr) and e.values and isinstance(e.values[-1], ast.Constant):
        return e.values[-1].value
    if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Div):
        return _path_constant(e.right)
    if isinstance(e, ast.Call) and _call_name(e.func) in ("str", "fspath", "Path", "PurePath") and len(e.args) == 1:
        return _path_constant(e.args[0])
    return None


def _bound(e, env, depth=0) -> list:
    """What an expression can be: itself, or -- a Name -- every expression it is bound to in `env`, followed
    the way tools/ci_fixture.py _path_values follows its names (draw3_fix ci 4: `S = "tools/x.sh";
    run(["bash", S])` was not read)."""
    if isinstance(e, ast.Name) and depth < 8:
        return [x for v in env.get(e.id, []) for x in _bound(v, env, depth + 1)]
    return [e]


def _strings(e, env) -> list:
    """The strings an argv element or a command can be: a path expression's last constant, an f-string's
    template, a Name's bound values."""
    out = []
    for v in _bound(e, env):
        if isinstance(v, ast.JoinedStr):
            out.append(_template_of(v))
        s = _path_constant(v)
        if s is not None:
            out.append(s)
    return out


def _command_line_scripts(text: str) -> list:
    return [m.group(1) for line in text.splitlines() for m in _SH_AT_COMMAND.finditer(line)]


#: Draw-5 ci 9 (the adjudicator's input, re-measured 2026-09-24): k rebinds `cmd = cmd + [...]` with no other binding
#: make _argv_elements try every order of them -- 0.023 s at k=7, 0.19 s at k=8, about x9 per rebind -- a hang that
#: failed closed only at the job's timeout. One walk may take this many steps; past it, RecursionError, which
#: check_no_live's per-file handler names "cannot be checked" and blocks on. MEASURED 2026-09-24: the real tree's
#: largest file takes 27 steps in all (scratchpad d6ci_ev/slow_probe.py).
ARGV_WALK_STEPS = 10_000


def _argv_elements(v, env, seen=frozenset(), budget=None):
    """The elements of an argv expression -- a list or tuple, or a `+` of them whose sides may be names -- or None.

    Draw4_build ci 4 (fails closed, as a crash): `cmd = ["bash"]; cmd = cmd + ["x.sh"]` and `def f(cmd): cmd = cmd
    + ["-v"]` bind `cmd` to an expression that contains `cmd`, and this walk followed it until RecursionError,
    which no handler caught. An expression already on the walk's path is not entered again, and each side of a
    `+` takes the first of its bindings that yields elements -- so the first form reads ["bash", "x.sh"] and the
    second, whose only binding is itself, reads nothing. A walk longer than ARGV_WALK_STEPS raises RecursionError
    (draw-5 ci 9)."""
    budget = [ARGV_WALK_STEPS] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0:
        raise RecursionError("an argv expression takes more than %d steps to follow (draw-5 ci 9)" % ARGV_WALK_STEPS)
    if id(v) in seen:
        return None
    seen = seen | {id(v)}
    if isinstance(v, (ast.List, ast.Tuple)):
        return list(v.elts)
    if isinstance(v, ast.BinOp) and isinstance(v.op, ast.Add):
        out = []
        for side in (v.left, v.right):
            got = next((e for e in (_argv_elements(x, env, seen, budget) for x in _bound(side, env)) if e is not None),
                       None)
            if got is None:
                return None
            out += got
        return out
    return None


def _argv_scripts(elts, env, from_start=True) -> list:
    """The .sh an argv runs. With `from_start` (the argv handed to a spawner) its command word counts --
    argv[0], after any _ARGV_LAUNCHERS word and its options (an option LAUNCHER_OPTION_ARGS says takes an
    argument skips that argument too: `sudo -u wq x.sh`, draw4_build ci 6), env's VAR=value words and timeout's
    duration. Anywhere, the word after a shell counts once the shell's options are skipped (`bash -e x.sh`,
    draw3_fix ci 4), and after `-c` the next word is read as a command line."""
    words = [_strings(e, env) for e in elts]
    first = lambda i: (words[i][0].strip() if i < len(words) and words[i] else "")          # noqa: E731
    out, starts = [], []
    if from_start:
        i = 0
        while first(i) in _ARGV_LAUNCHERS:
            launcher, i = first(i), i + 1
            while True:
                w = first(i)
                if len(w) == 2 and w[0] == "-" and w[1] in LAUNCHER_OPTION_ARGS[launcher]:
                    i += 2                                        # the option and its argument
                elif w.startswith("-") or (launcher == "env" and re.match(r"^\w+=", w)):
                    i += 1
                else:
                    break
            if launcher == "timeout":
                i += 1                                            # its duration
        starts.append(i)
    starts += [i + 1 for i in range(len(words)) if _SH_WORD.match(first(i))]
    for i in starts:
        if _SH_WORD.match(first(i)):
            i += 1
        while first(i).startswith("-"):
            opt, i = first(i), i + 1
            if not opt.startswith("--") and opt.endswith("c"):
                out += [s for text in (words[i] if i < len(words) else []) for s in _command_line_scripts(text)]
                i = len(words)
        if i < len(words):
            out += words[i]
    return out


def _spawned(call, env) -> list:
    """What a standard-library spawner call runs, as a list of candidates: each an argv (a list of expressions)
    or a single expression (a command line, a path, or an argv expression to be followed). Draw4_build ci 6:
    `run(args=[...])` and the spawn/varargs forms (see _SPAWN_COMMAND)."""
    name = _call_name(call.func)
    args = list(call.args)
    if name in _SPAWN_COMMAND:
        cmd = args[0] if args else next((k.value for k in call.keywords if k.arg == "args"), None)
        return [] if cmd is None else [cmd]
    at = _SPAWN_VARARGS.get(name, _SPAWN_VECTOR.get(name))
    if at is None or len(args) <= at:
        return []
    program = args[at]
    if name in _SPAWN_VARARGS:
        rest = args[at + 1:] if name == "create_subprocess_exec" else args[at + 2:]
        return [[program] + rest]
    vec = args[at + 1] if len(args) > at + 1 else None
    tails = [e for v in (_bound(vec, env) if vec is not None else []) for e in [_argv_elements(v, env)] if e is not None]
    return [[program] + t[1:] for t in tails] or [[program]]


def _scripts_python_runs(source: str) -> list:
    """The .sh paths a Python file RUNS, read from its syntax tree (draw3_fix ci 4 and 5):
      * what a standard-library spawner runs (_spawned; a Name followed to what it is bound to, per scope, as
        tools/ci_fixture.py reads names -- annotated assignments included, draw4_build ci 6): an argv's command
        word or the script after its shell (_argv_scripts), a command line's scripts at command position, or a
        bare script path;
      * the word after a shell in ANY list or tuple (`["bash", "x.sh"]` is an argv wherever it stands).
    DATA IS NOT A RUN. Draw3_fix ci 5 (fails closed): argv[0] of every list, and every command-line string a
    statement held, were read as runs, so a tuple loop checking exists(), a parametrize list, `assert plan
    == ["vps/forge_loop.sh"]`, and test_ci_gate.py's own probe strings ("cd /opt/wq && ./tools/z.sh") each
    read a script. MEASURED 2026-09-23: the tests name vps/forge_loop.sh and vps/c11_run.sh only as data;
    those scripts pass --submit legitimately on the VPS. When a test, or a module a test imports, RUNS one --
    at its repository path or at its deployed one (check_no_live resolves both; draw-5 ci C8: this sentence said
    "if a test ever RUNS one, it is read", while the deployed path read nothing) -- it is read and it blocks:
    MEASURED 2026-09-24, forge/search.py run_recipe() runs forge_loop.sh at its deployed path.
    A command line handed to a function that is NOT a standard-library spawner (a wrapper of one's own) is
    read only when it is a list naming a shell."""
    tree = ast.parse(source)
    F = _fixture_module()
    found = []
    module_env = F._bindings(tree)
    for scope in [tree] + [n for n in ast.walk(tree) if isinstance(n, F._SCOPES)]:
        env = module_env if scope is tree else dict(module_env, **F._bindings(scope))
        for n in F._own_nodes(scope):
            if isinstance(n, ast.Call) and _call_name(n.func) in _SPAWN:
                for cand in _spawned(n, env):
                    if isinstance(cand, list):
                        found += _argv_scripts(cand, env)
                        continue
                    for v in _bound(cand, env):
                        elts = _argv_elements(v, env)
                        if elts is not None:
                            found += _argv_scripts(elts, env)
                            continue
                        if isinstance(v, ast.Call) and _call_name(v.func) == "split":     # "...".split(), shlex.split(...)
                            v = v.args[0] if v.args and isinstance(v.func, ast.Attribute) and \
                                getattr(v.func.value, "id", None) == "shlex" else getattr(v.func, "value", v)
                        for text in _strings(v, env):
                            found += [text.strip()] if _SH_PATH.match(text.strip()) else _command_line_scripts(text)
            elif isinstance(n, (ast.List, ast.Tuple)):
                found += _argv_scripts(n.elts, env, from_start=False)
    return [p.strip() for p in found if p and _SH_PATH.match(p.strip())]


def _scripts_shell_runs(text: str) -> list:
    """The .sh paths a shell script or a workflow runs: a path at command position on a line with its
    comment dropped (a workflow's `run:` / `- run: |` prefix is dropped first)."""
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:-\s+)?(?:run:\s*)?(?:[|>][-+]?\s*$)?", "", re.sub(r"(^|\s)#.*$", "", line))
        out += [m.group(1) for m in _SH_AT_COMMAND.finditer(line)]
    return out


def _deployed_layout(root=ROOT) -> dict:
    """{path under DEPLOYED_ROOT: repository path} for every FILE entry of tools/deploy.py PLAN whose two paths differ
    ("forge_loop.sh": "vps/forge_loop.sh", ...), read from the syntax tree of `root`'s tools/deploy.py -- deploy.py is
    not imported or run. Directory entries ("forge/": "forge/") ship a tree at its own path and need no mapping.
    Draw-5 ci C8: the scan resolved `/opt/wq/forge_loop.sh` and `ROOT / "forge_loop.sh"` (ROOT is /opt/wq on the
    host) against the repository root, where no forge_loop.sh is, and dropped the token unnamed. Raises ValueError
    when PLAN cannot be read as a literal: the caller fails closed."""
    try:
        tree = ast.parse((pathlib.Path(root) / DEPLOY_PY).read_text())
        plan = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "PLAN" for t in n.targets))
    except (OSError, SyntaxError, ValueError, StopIteration) as exc:
        raise ValueError("%s PLAN cannot be read as a literal (%s)" % (DEPLOY_PY, type(exc).__name__)) from None
    return {dst: src for src, dst in plan.items() if not src.endswith("/") and src != dst}


def _resolve_script(token: str, root: pathlib.Path, near: pathlib.Path, layout=None) -> list:
    """Every repository file a script token can name, in either layout it runs in: tried against the repository root
    (the cwd of the gate and of Actions), the invoking file's directory, and -- through `layout`, the deployed tree's
    mapping (_deployed_layout) -- the repository file shipped to that path on the host; [] when it names none.
    An absolute path names a repository file when it lies inside the repository or under DEPLOYED_ROOT, the host's
    deployed tree (draw4_build ci 6: `/opt/wq/tools/x.sh` read nothing). Any other leading "/" is dropped and the
    rest tried as before: it is how the last constant of f"{ROOT}/tools/x.sh" reads. Draw-5 ci C8: a token is read
    in BOTH layouts, because a test runs from the repository here and from /opt/wq in the deploy smoke and the daily
    wq-forge-tests run -- `/opt/wq/forge_loop.sh` and `ROOT / "forge_loop.sh"` are vps/forge_loop.sh there."""
    root_r = root.resolve()
    if token.startswith(DEPLOYED_ROOT + "/"):
        token = token[len(DEPLOYED_ROOT) + 1:]
    elif token.startswith("/") and pathlib.Path(token).is_file() and pathlib.Path(token).resolve().is_relative_to(root_r):
        return [pathlib.Path(token).resolve()]
    rel = token[2:] if token.startswith("./") else token.lstrip("/")
    out = []
    for p in [base / rel for base in (root, near)] + ([root / layout[rel]] if rel in (layout or {}) else []):
        p = p.resolve()
        if p.is_file() and p.is_relative_to(root_r) and p not in out:
            out.append(p)
    return out


def _loaded_conftests(root: pathlib.Path, paths=None) -> list:
    """The conftest.py files pytest loads for check_tests' run over `paths` (default suite(root)): one in each
    directory from the root down to each path -- a test FILE's own directory for a file (round 3 S6) -- and any
    below a directory. Draw-3 ci SERIOUS 5: /conftest.py sits outside forge/, tools/ and vps/ and was never
    read. Other conftests in the repository (cyberrisk/tests/) are not loaded by that run and are not read."""
    root = pathlib.Path(root)
    out = set()
    for d in (suite(root) if paths is None else paths):
        p = pathlib.PurePosixPath(d)
        parts = p.parts if (root / d).is_dir() else p.parent.parts
        out.update(c for c in (root.joinpath(*parts[:i], "conftest.py") for i in range(len(parts) + 1)) if c.is_file())
        if (root / d).is_dir():
            out.update((root / d).rglob("conftest.py"))
    return sorted(out)


def check_no_live(root=ROOT) -> dict:
    """Nothing reachable from CI may spend platform quota or POST (RULE 1).

    S7-NL (round 2; round 1's S7 had not landed): the scan read only the test directories, only for
    `--live`, line by line. It now reads EVERY .py under forge/, tools/ and vps/ and every workflow file,
    for `--live` AND `--submit` used as ARGUMENTS -- read from the syntax tree, so a comment, a docstring,
    an assertion, a `not in` guard and the add_argument that defines the flag are not uses -- and names
    each offender as file:line. A .py that does not parse cannot be checked and blocks. Workflow files are
    read line by line with YAML comments dropped.

    Draw-3 ci SERIOUS 5 (round 1's scope, architecture_round1.md:404, had not landed): a probe tree put the
    flag in /conftest.py, in a shell script, in "--submit --cap 4".split(), in a `%` template and in a
    .format template, and none was flagged. The scan now also reads
      * the conftest.py files pytest loads for check_tests' run (_loaded_conftests);
      * every shell script a test, one of those conftests, a module they import, or a workflow RUNS, and
        every script those run (_scripts_python_runs, _scripts_shell_runs), line by line with comments
        dropped. A script token is read in BOTH layouts it runs in -- the repository here, and the deployed
        tree on the host, where the deploy smoke and the daily wq-forge-tests run the same tests from /opt/wq
        (_resolve_script through _deployed_layout, tools/deploy.py PLAN; draw-5 ci C8: `/opt/wq/forge_loop.sh`
        and `ROOT / "forge_loop.sh"` named no repository file and were dropped unnamed, and this text said
        the loop scripts were "NOT read, because nothing here runs them"). A RUN token that names no file in
        either layout cannot be checked and BLOCKS (`scripts_unresolved`);
      * argv built by .split() / shlex.split() and commands built by `%`, str.format or an f-string.
    WHAT THE REAL TREE READS, MEASURED 2026-09-24: forge/tests/test_search.py imports forge/search.py, whose
    run_recipe() runs `bash ROOT/forge_loop.sh` -- vps/forge_loop.sh on the host, which passes --live and
    --submit (they are its job on the VPS). So the real tree BLOCKS here, on vps/forge_loop.sh's two lines, and
    fails closed until Khoa ticks how that call is treated (draw-5 ci C8 (d), RULE 2): an exact-line
    NO_LIVE_EXEMPT entry with its reason; run_recipe refusing to run under pytest (forge/search.py's owner); or
    it stays blocking. No test calls run_recipe today; the block is on what the tests can REACH.
    Draw3_fix ci 4 (each gave ok=True on a probe tree): f"{script} --submit --cap 4", "cd /opt/wq && %s
    --submit" % s, ["bash", "-e", "tools/x.sh"], S = "tools/x.sh"; run(["bash", S]), and a test importing
    harness/mod.py that passes the flag. The last is why the scan now walks the IMPORT CLOSURE of the test
    files and loaded conftests (tools/ci_fixture.py import_closure): a module they import is read for the
    flag even outside forge/, tools/ and vps/, and the scripts it runs are followed. A sys.path entry
    that walk cannot evaluate is NAMED in `closure_unread` (a module behind it is not read) and does not
    block: MEASURED 2026-09-24, three exist -- tools/ci_classify.py code_version() (`root` is a parameter),
    tools/watchdog.py climb_tick() (os.path.join(ROOT, ...), a form the walk does not evaluate) and
    forge/gen/spend.py _predict() (`sys.path[:] = saved`, which restores the path).

    Draw4_build ci 6 (each read ok=True on the adjudicator's probe trees), now read: a template whose commands
    are separated by a newline, `nice -n 5 %s`, `timeout -s KILL 60 %s`, a template held in a name (`T = "%s
    <flag>"; T % s`: a string whose command word is a placeholder is a template wherever it stands);
    run("timeout 60 x.sh", shell=True) and run("A=1 x.sh", shell=True); an annotated assignment (`S: str = ...`)
    and run(args=[...]); ["sudo", "-u", "wq", ...]; os.spawnl(os.P_WAIT, ...) and create_subprocess_exec("bash",
    ...) (_spawned); an absolute /opt/wq/... path (_resolve_script). Draw4_build ci 4: a name bound to an
    expression that contains it no longer recurses (_argv_elements), and a file whose reading raises
    RecursionError anyway is named "cannot be checked" and blocks, instead of crashing the gate unnamed.

    Draw-5 ci 7: os.posix_spawn / posix_spawnp and pty.spawn (or any call named `spawn`) are read as spawners
    now, and `getattr(sys, "path").insert(...)` as a sys.path write (ci_fixture._is_sys_path_expr).

    WHAT THIS IS NOT. It is a tripwire against ACCIDENT, not a proof: a flag assembled from parts
    ("--" + "live") walks around it -- this gate's own tests do exactly that to avoid tripping it -- and
    it fires on the flag used as test DATA. A Python file that a workflow runs outside forge/, tools/ and
    vps/ and that no test imports is not read, nor is a script whose path is built at run time, nor a
    command line handed as a string to a wrapper that is not a standard-library spawner, nor a spawner
    reached through an alias (`from subprocess import run as go`), nor a launcher outside
    LAUNCHER_OPTION_ARGS (`ionice`, `stdbuf`, `xargs` ...), nor a command whose separator is "(" or "$(".
    Draw-5 ci 7: each side of an argv `+` takes ONE binding of a name -- the first that yields elements in the
    order ci_fixture._bindings returns them, which walks a scope's statements last to first -- so
    `X = ["tools/a.sh"]` then `if c: X = ["tools/b.sh"]` then run(X + ["-v"]) reads b.sh only, while run(X)
    reads both (MEASURED 2026-09-24). The structural protections of RULE 1 are elsewhere: a hosted runner
    holds no platform credential and so cannot POST at all, and the parsers that define these flags refuse
    abbreviations (allow_abbrev=False, the parser half of S7-NL).
    """
    root = pathlib.Path(root)
    offenders = []

    def unreadable(p, exc):
        offenders.append("%s (cannot be checked: %s)" % (p.relative_to(root), type(exc).__name__))

    def exempt_filter(rel, text, lines):
        return ["%s:%d" % (rel, i) for i in lines if (rel, text[i - 1].strip()) not in NO_LIVE_EXEMPT]

    try:
        paths = suite(root)                    # round 3 S6: the test files outside TEST_DIRS the gate runs too
    except Exception as exc:  # noqa: BLE001 -- a suite that cannot be derived: scan the fixed dirs and block
        paths = list(TEST_DIRS)
        offenders.append("the test suite (cannot be derived: %s)" % type(exc).__name__)
    conftests = set(_loaded_conftests(root, paths))
    tests = {p for d in paths for p in ((root / d).rglob("*.py") if (root / d).is_dir() else [root / d])
             if p.is_file()}
    F = _fixture_module()
    try:
        closure = F.import_closure(sorted(p.relative_to(root).as_posix() for p in tests | conftests), root)
        runners = {root / f for f in closure["files"]}
        closure_unread = closure["unread"]
    except (OSError, SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        offenders.append("the import closure of the tests (cannot be followed: %s)" % type(exc).__name__)
        runners, closure_unread = tests | conftests, []
    python = sorted({p for d in NO_LIVE_DIRS for p in (root / d).rglob("*.py")} | conftests | runners)
    runs, files = [], 0                       # (script token, the file that runs it, that file's repository path)
    for p in python:
        rel = str(p.relative_to(root))
        try:
            source = p.read_text()
            lines = _flag_lines(source)
            if p in runners:                   # the tests, the loaded conftests and every module they import
                runs += [(s, p.parent, rel) for s in _scripts_python_runs(source)]
        except (OSError, SyntaxError, ValueError, RecursionError, MemoryError) as exc:   # draw4_build ci 4, draw-5 ci 8
            unreadable(p, exc)
            continue
        files += 1
        offenders += exempt_filter(rel, source.splitlines(), lines)
    workflows = sorted((root / ".github").rglob("*.yml")) + sorted((root / ".github").rglob("*.yaml"))
    for p in workflows:
        try:
            body = p.read_text()
        except (OSError, ValueError) as exc:          # draw-5 ci 8: a non-UTF-8 workflow raised UnicodeDecodeError
            unreadable(p, exc)
            continue
        runs += [(s, p.parent, str(p.relative_to(root))) for s in _scripts_shell_runs(body)]
        for i, line in enumerate(body.splitlines(), 1):
            if _FLAG.search(re.sub(r"(^|\s)#.*$", "", line)):
                offenders.append("%s:%d" % (p.relative_to(root), i))
    try:
        layout = _deployed_layout()
    except ValueError as exc:                          # draw-5 ci C8: without the host layout a host path reads nothing
        offenders.append("the deployed layout (cannot be read: %s)" % exc)
        layout = {}
    scripts, unresolved = {}, []
    while runs:
        token, near, by = runs.pop()
        found = _resolve_script(token, root, near, layout)
        if not found:                                  # draw-5 ci C8 (b): named, never dropped
            unresolved.append("%s (run by %s)" % (token, by))
        for p in found:
            if p in scripts:
                continue
            rel = str(p.relative_to(root.resolve()))
            try:
                body = p.read_text()
            except (OSError, ValueError) as exc:
                offenders.append("%s (cannot be checked: %s)" % (rel, type(exc).__name__))
                scripts[p] = rel
                continue
            scripts[p] = rel
            runs += [(s, p.parent, rel) for s in _scripts_shell_runs(body)]
            lines = [i for i, line in enumerate(body.splitlines(), 1) if _FLAG.search(re.sub(r"(^|\s)#.*$", "", line))]
            offenders += exempt_filter(rel, body.splitlines(), lines)
    # draw-5 ci C8 (b): a script that is RUN and names no file cannot be checked, and it BLOCKS, as an unreadable file
    # does: the token C8 found dropped unnamed was the loop itself at its host path. MEASURED 2026-09-24 on the real
    # tree: none.
    unresolved = sorted(set(unresolved))
    offenders += ["%s: names no file in the repository or the deployed layout (cannot be checked)" % u for u in unresolved]
    outside = len([p for p in runners if p.relative_to(root).parts[0] not in NO_LIVE_DIRS and p not in conftests])
    read = ("%d Python (the conftests pytest loads and %d file(s) outside %s that the tests import among them), "
            "%d workflow, %d shell script(s) a test, a module it imports or a workflow runs%s%s"
            % (files, outside, "/".join(NO_LIVE_DIRS), len(workflows), len(scripts),
               (": " + ", ".join(sorted(scripts.values()))) if scripts else "",
               ("; %d sys.path entr(ies) of the tests' import closure not evaluated, a module behind one is not "
                "read: %s" % (len(closure_unread), ", ".join(closure_unread))) if closure_unread else ""))
    return {"name": "no-live", "ok": not offenders, "blocking": True, "details": offenders, "scripts_read": sorted(scripts.values()),
            "closure_unread": closure_unread, "scripts_unresolved": unresolved,
            "summary": ("nothing reachable from CI passes --live or --submit (%s)" % read) if not offenders
                       else "--live/--submit passed as an argument at %s" % ", ".join(offenders[:8])}


def check_schema(root=ROOT) -> dict:
    """Every library YAML must load through the real loader, not merely parse as YAML.

    A composite that parses but names a leg that does not exist is a round that plans nothing, and
    the loop reports that as an ordinary empty round.
    """
    code = ("import sys; sys.path.insert(0, %r);"
            "from forge import hypotheses as H;"
            "lib = H.load_library('forge/hypotheses');"
            "c = H.load_composites('forge/composites', lib);"
            "print('%%d legs, %%d composites' %% (len(lib), len(c)))" % str(root))
    r = _run([sys.executable, "-c", code])
    return {"name": "schema", "ok": r.returncode == 0,
            "summary": (r.stdout or r.stderr or "").strip().splitlines()[-1:][0] if (r.stdout or r.stderr) else "",
            "blocking": True}


def check_version(root=ROOT) -> dict:
    """The tree must be able to state its own version, or D1 and D14 have no referent."""
    code = ("import sys; sys.path.insert(0, %r + '/tools');"
            "import deploy as D;"
            "m = D.manifest();"
            "print('%%s (%%d files)' %% (m['version'], m['files']))" % str(root))
    r = _run([sys.executable, "-c", code])
    return {"name": "version", "ok": r.returncode == 0,
            "summary": (r.stdout or r.stderr or "").strip(), "blocking": True}


def check_fitness(root=ROOT) -> dict:
    """The architecture fitness functions -- axis 3 of the benchmark, run as a gate.

    This is what makes "can a branch be grown onto this pipeline?" a build failure rather than an
    opinion: if a change introduces a module-level import cycle, or takes the A/B arm away, or leaves
    a new module untested, the gate says so on the commit that did it.
    """
    code = ("import sys; sys.path.insert(0, %r);"
            "from forge.offline import benchmark as B;"
            "a = B.axis3_gearing(run_drill=%r);"
            "bad = [f['name'] for f in a['fitness_functions'] if not f['ok']];"
            "print('%%d/%%d hold%%s' %% (a['held'], a['of'], '' if not bad else '  FAILING: ' + ', '.join(bad)));"
            "sys.exit(0 if a['floor_met'] else 1)" % (str(root), tier(root) == "data"))
    # the branch drill is data-bound (its own check reports that on a hosted runner); running it inside
    # the fitness count here would score a missing catalogue as "no branch can be grown"
    r = _run([sys.executable, "-c", code])
    return {"name": "fitness", "ok": r.returncode == 0,
            "summary": (r.stdout or r.stderr or "").strip().splitlines()[-1:][0] if (r.stdout or r.stderr) else "",
            "blocking": True}


def check_branch_drill(root=ROOT) -> dict:
    """Grow one real branch on a copy of the library; the real planner must carry it with no code
    edited (forge/offline/branch_drill.py). This is what turns "can the pipeline be extended?" from an
    opinion into a build result, on every commit.

    DATA-BOUND, measured with an audit hook: the planner opens the 50 MB field catalogue and the 110 MB
    journal (it reads what was already simulated). On a hosted runner the check is REPORTED as not run
    and why -- never as a pass: gate() prints it [NOT RUN] (`not_run_here`; draw-5 ci 13 / round 3 m17: it
    printed [PASS]). It does not block there -- the tier cannot run it, and ci_publish's data tier does.
    """
    if tier(root) != "data":
        return {"name": "branch-drill", "ok": True, "blocking": True, "not_run_here": True,
                "summary": "NOT RUN on this tier: the planner needs %s; runs in the data tier" % " + ".join(DATA_MARKERS)}
    code = ("import sys, json; sys.path.insert(0, %r);"
            "from forge.offline import branch_drill as BD;"
            "r = BD.drill();"
            "print('%%s: %%d construction(s), code unchanged=%%s -- %%s' %% (r['status'], r.get('constructions', 0), r.get('code_unchanged'), r['note']));"
            "sys.exit(0 if r['ok'] else 1)" % str(root))
    r = _run([sys.executable, "-c", code])
    return {"name": "branch-drill", "ok": r.returncode == 0,
            "summary": (r.stdout or r.stderr or "").strip().splitlines()[-1:][0] if (r.stdout or r.stderr) else "",
            "blocking": True}


def check_known_red(root=ROOT) -> dict:
    """A test MEASURED red in the data tier blocks EVERY tier, including one that cannot run it.

    Khoa 2026-09-23 (D23): leave the unit-model test red and let CI block. That test fails only WITH
    the desk's data; a hosted runner cannot see it, so without this check GitHub would show green while
    a known red test exists -- the lying green tick this whole gate is built against. In the data tier
    the tests check itself runs it and blocks; here the committed record blocks in its place.

    Round 2, A8: the record that blocks here is the COMMITTED list, tools/ci_known_red.json, and also any
    test the classification measured red that the list does not name -- a newly measured red test is not
    allowed anywhere until Khoa ticks it into the list. Both only ever BLOCK; neither is an allowance.
    A missing or malformed list blocks too.
    """
    if tier(root) == "data":
        return {"name": "known-red", "ok": True, "blocking": True,
                "summary": "data tier: red tests are run directly by the tests check (judged against %s)" % KNOWN_RED}
    try:
        listed = [t["node_id"] for t in known_red(root)]
    except ValueError as exc:
        return {"name": "known-red", "ok": False, "blocking": True, "summary": str(exc)}
    cls = classification(root)
    unlisted = [n for n in (cls.get("red") or []) if n not in listed]
    said = []
    if listed:
        said.append("%d test(s) red in the data tier per %s (D23): %s" % (len(listed), KNOWN_RED, ", ".join(listed)))
    if unlisted:
        said.append("%d measured red (classification %s) and NOT in %s, so not allowed anywhere: %s"
                    % (len(unlisted), cls.get("measured_at"), KNOWN_RED, ", ".join(unlisted)))
    return {"name": "known-red", "ok": not said, "blocking": True,
            "summary": "; ".join(said) or "none listed, none measured (classification %s)" % cls.get("measured_at")}


GOLDEN = ROOT / "tools/ci_golden_card.json"


def _fixture_card(root=ROOT) -> tuple:
    """(card, None) or (None, why): the truth table in tools/ci_fixture.py scored by the scorer at `root`,
    in a fresh interpreter -- the same way for the gate and for --record-golden, so what is recorded is
    exactly what is checked."""
    code = ("import sys, json; sys.path[:0] = [%r, %r];"
            "import ci_fixture as F; print(json.dumps(F.card(), sort_keys=True))" % (str(root), str(root / "tools")))
    r = _run([sys.executable, "-c", code], cwd=root)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout or "")[-300:]
    return json.loads((r.stdout or "").strip().splitlines()[-1]), None


def check_pinned_scorer(root=ROOT, golden_path=None) -> dict:
    """Draw 2 (round 1, F1 + S8): the pre-merge gate judges what a DIFF can change -- including the
    scorer. The truth table in tools/ci_fixture.py must reproduce the committed golden card exactly.

    What this REPLACED, and why: a regression check on the composite over the live journal. Under D14 a
    candidate version has produced no rows at merge time, so no diff could move axes 1-2; the number
    moved only as the journal grew, and an unchanged tree read 25.4 on the VPS against a committed 25.5
    -- a gate that blocks nothing it should and something it should not. Judging a VERSION's output is
    benchmark.compare(), after it has run.

    Round 2 (A7, S8-NL): the card is a truth table -- one case per decision the audits listed -- and carries
    the sha256 of the fixture and of the scorer, so a scorer edit that reaches no case still blocks until
    the golden is re-recorded (with its diff printed) and committed. Draw-3 ci SERIOUS 3: "the scorer" was
    benchmark.py's bytes alone, and an edit to forge/submit.py's corr_lines passed with ok=True; it is now
    benchmark.py and every repository file it imports (`scorer_closure`, ci_fixture.import_closure), so an
    edit to any of them names its path in the difference.
    """
    gp = pathlib.Path(golden_path or GOLDEN)
    now, err = _fixture_card(root)
    if err is not None:
        return {"name": "pinned-scorer", "ok": False, "blocking": True,
                "summary": "the scorer failed on the truth table: %s" % err[-200:]}
    try:
        want = json.loads(gp.read_text())
    except (OSError, ValueError):
        return {"name": "pinned-scorer", "ok": False, "blocking": True,
                "summary": "no committed golden card; run `python3 tools/ci_gate.py --record-golden`, read the "
                           "diff, and commit tools/ci_golden_card.json"}
    diffs = _diff(want, now)
    return {"name": "pinned-scorer", "ok": not diffs, "blocking": True,
            "summary": ("the truth table reproduces the golden card (%d cases; scorer sha256 %s and the %d files "
                        "of its import closure unchanged)"
                        % (len(now["cases"]), now["scorer_sha256"][:12], len(now.get("scorer_closure") or {})))
                       if not diffs else
                       "the scorer's judgement or identity CHANGED (%d difference(s)): %s -- re-record with "
                       "`python3 tools/ci_gate.py --record-golden`, read its diff, commit the golden on its own"
                       % (len(diffs), "; ".join(d[:160] for d in diffs[:4])),
            "details": diffs[:12]}


def _diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), "%s.%s" % (path, k) if path else str(k))
        return out
    return [] if a == b else ["%s: %r -> %r" % (path, a, b)]


def scorer_moved(golden, card) -> list:
    """The scorer files whose bytes differ between the golden and this card, by path (added and removed
    files included). The scorer is the `scorer_closure` -- benchmark.py and every repository file it imports
    (draw-3 ci SERIOUS 3); a golden recorded before the closure existed is compared on benchmark.py's hash
    alone, the only scorer identity it holds."""
    scorer = card.get("scorer", "forge/offline/benchmark.py")
    moved = set() if golden.get("scorer_sha256") == card["scorer_sha256"] else {scorer}
    if golden.get("scorer_closure") is not None:
        a, b = golden["scorer_closure"], card.get("scorer_closure") or {}
        moved |= {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    return sorted(moved)


def record_refusal(golden, card) -> str | None:
    """S8-NL: why --record-golden must NOT write this card over this golden, or None.

    Refused when BOTH the scorer and the fixture (tools/ci_fixture.py) differ from the bytes the golden
    recorded: the diff would then mix two causes, and nobody could say which moved a judgement. cac48d7
    changed the scorer, the fixture and the golden in ONE commit. "The scorer" is the same set the gate
    compares -- benchmark.py and its whole import closure (scorer_moved; draw-3 ci SERIOUS 3: this read
    benchmark.py alone, so an edit to forge/submit.py and the fixture recorded as one diff). A golden that
    predates the recorded hashes has nothing to compare with; this recording establishes them.
    This guards the RECORDING TOOL, not the file (JSON anyone can write): what makes a re-record visible
    is the diff printed here and again by tools/ci_publish.py."""
    if not golden or golden.get("scorer_sha256") is None:
        return None
    moved = scorer_moved(golden, card)
    if moved and golden.get("fixture_sha256") != card["fixture_sha256"]:
        return ("the scorer (%d file(s) moved: %s) AND tools/ci_fixture.py (%s -> %s) both changed since the golden "
                "card was recorded, so this diff mixes a scorer change with a fixture change. Commit the scorer "
                "change first: put the committed fixture back, re-record (the diff is then the scorer's alone), "
                "commit that golden on its own; then restore the fixture change and re-record."
                % (len(moved), ", ".join(moved[:6]) + (" ..." if len(moved) > 6 else ""),
                   str(golden.get("fixture_sha256"))[:12], card["fixture_sha256"][:12]))
    return None


def record_golden(root=ROOT, golden_path=None, out=print) -> dict:
    """Re-record the golden card: print the unified diff against the golden on disk (the one the gate
    compares with, and the one that is committed) BEFORE writing, then write -- unless record_refusal()
    refuses. {"written", "refused", "diff", "card"}. S8-NL: it used to write and print the new card with
    no diff, so a re-record that absorbed a changed judgement read like any other."""
    gp = pathlib.Path(golden_path or GOLDEN)
    card, err = _fixture_card(root)
    if err is not None:
        out("the scorer failed on the truth table; nothing written:\n%s" % err)
        return {"written": False, "refused": "the scorer failed on the truth table", "diff": "", "card": None}
    try:
        old_text = gp.read_text()
        golden = json.loads(old_text)
    except (OSError, ValueError):
        old_text, golden = "", None
    new_text = json.dumps(card, indent=1, sort_keys=True) + "\n"
    diff = "".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True),
                                        fromfile="%s (committed)" % gp.name, tofile="%s (this scorer)" % gp.name))
    out(diff if diff else "no difference: the golden card already equals this scorer's card")
    if golden is None:
        out("(no readable golden card on disk: everything above is new)")
    elif golden.get("scorer_sha256") is None:
        out("(the golden on disk predates the recorded scorer and fixture hashes; this recording establishes them)")
    elif golden.get("scorer_closure") is None:
        out("(the golden on disk predates the scorer's import closure: compared on benchmark.py's hash alone; this "
            "recording establishes the closure, %d files)" % len(card.get("scorer_closure") or {}))
    refused = record_refusal(golden, card)
    if refused:
        out("REFUSED, nothing written: " + refused)
        return {"written": False, "refused": refused, "diff": diff, "card": card}
    gp.write_text(new_text)
    out("wrote %s: %d cases, scorer sha256 %s (+%d files in its import closure), fixture sha256 %s -- read the diff "
        "above, then commit the golden on its own" % (gp, len(card["cases"]), card["scorer_sha256"][:12],
                                                     len(card.get("scorer_closure") or {}) - 1, card["fixture_sha256"][:12]))
    return {"written": True, "refused": None, "diff": diff, "card": card}


def _contained(check):
    """`check`, returning a failed, BLOCKING result that names the check and the exception when it raises, instead of
    raising. Draw-5 ci 8 (REPRODUCED by the adjudicator): a tools/ci_fixture.py that does not parse made
    check_no_live and check_tests raise SyntaxError, and gate() printed no verdict at all; tools/ci_publish.py
    data_tier() calls each CHECKS entry too, so the containment is here, on the entries, not in gate()."""
    @functools.wraps(check)
    def run(*a, **k):
        try:
            return check(*a, **k)
        except Exception as exc:  # noqa: BLE001 -- a check that cannot finish cannot pass
            return {"name": check.__name__[len("check_"):].replace("_", "-"), "ok": False, "blocking": True,
                    "summary": "the check raised %s: %s" % (type(exc).__name__, str(exc)[:200]),
                    "details": ["%s raised %s; nothing it checks can be shown to hold" % (check.__name__, type(exc).__name__)]}
    return run


CHECKS = tuple(map(_contained, (check_no_live, check_schema, check_version, check_fitness, check_branch_drill,
                                check_test_files, check_tests, check_known_red, check_pinned_scorer)))


def gate(checks=CHECKS, out=print) -> int:
    results = [c() for c in checks]
    out("CI GATE  (%s tier)" % tier())
    for r in results:
        out("  [%s] %-11s %s" % ("NOT RUN" if r.get("not_run_here") else "PASS" if r["ok"] else "FAIL", r["name"],
                                 r["summary"]))
        for line in (r.get("details") or []) if not r["ok"] else []:
            out("        %s" % line[:180])
        kr = r.get("known_red")
        if kr:
            out("        %s" % ("allowance (A8): " + kr["why"] if kr["ok"] else
                                "no allowance applies (A8): %s" % "; ".join(kr["blocking"][:4]))[:400])
        where = {}
        for f, why in (r.get("not_run") or {}).items():
            where.setdefault(r["covered_instead_by"][f], []).append("%s -- %s" % (f, why))
        for w, entries in where.items():
            out("        not run here, %s:" % (w if w.startswith("NOT COVERED") else "covered instead by " + w))
            for e in entries:
                out("            %s" % e)
    blocking = [r for r in results if r["blocking"] and not r["ok"]]
    out("")
    out("  VERDICT %s%s" % ("PASS" if not blocking else "BLOCKED",
                            "" if not blocking else " on " + ", ".join(r["name"] for r in blocking)))
    return 1 if blocking else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record-golden", action="store_true",
                    help="re-record tools/ci_golden_card.json from the truth table: prints the diff first, and "
                         "refuses when the scorer and the fixture both changed (S8-NL)")
    a = ap.parse_args(argv)
    if a.record_golden:
        return 0 if record_golden()["written"] else 1
    if a.json:
        results = [c() for c in CHECKS]
        print(json.dumps(results, indent=1))
        return 1 if any(r["blocking"] and not r["ok"] for r in results) else 0
    return gate()


if __name__ == "__main__":
    sys.exit(main())
