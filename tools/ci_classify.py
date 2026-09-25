"""tools.ci_classify — MEASURE which tests need the desk's data, instead of listing them by hand.

WHY THIS EXISTS. The first two GitHub Actions runs showed that much of tools/tests was written against
the desk's live data -- the real journal, the real submit ledger, the real platform catalogue -- and
cannot run on a clean runner. A test that fails on a clean runner is either DATA-BOUND or GENUINELY
RED, and the two must never be confused: deselecting a red test as "data-bound" is how a gate learns to
lie. So the classification is an experiment with two arms, run on the same code:

    arm DATA   this working tree, with state/ and fetched/ present
    arm CLEAN  a clone of the pipeline repository, with neither

    data-bound  = fails in CLEAN, passes in DATA        -> hosted CI skips it, NAMED, with the reason
    red         = fails in DATA                         -> never skipped; it blocks everywhere
    hermetic    = passes in CLEAN                       -> hosted CI runs it

The result is written to tools/ci_data_bound.json with the method and the timestamp, and
tools/ci_gate.py reads it. Re-run this whenever tests change; the gate compares a CONTENT hash of the
test files with the one recorded here and BLOCKS when they differ (S6-NL; mtimes mean nothing on a fresh
clone).

Draw4_build ci X2 (EX-ANTE, by reading; the draw3_fix ci 2 class): each arm ran pytest with the caller's whole
environment and `-q`, and read no completeness -- so PYTEST_ADDOPTS=-x could end an arm at its first failure,
and a test that never ran was classified as neither red nor data-bound. Each arm now runs pytest the way
tools/ci_gate.py check_tests does (its environment, `-o` overrides, no ini file of the tree -- ci_gate.config_args,
draw-5 ci 1 -- and no `-q`), and an arm whose run was not complete by that gate's own readings (run_incomplete,
_collection_narrowers) makes the classification INVALID: nothing is written. Round 3 S6: the suite is
ci_gate.suite(), the same paths the gate hands pytest. NOT the gate's: the arms do not run -v, so a test REPORTED
TWICE (draw-5 ci 2) is read by check_tests only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "tools/ci_data_bound.json"
sys.path.insert(0, str(ROOT / "tools"))
import ci_gate as G  # noqa: E402 -- the suite, its environment and its completeness readings are the gate's


def suites(root=ROOT) -> list:
    """The paths both arms hand pytest: ci_gate.suite(), TEST_DIRS plus every unlisted test file outside them that
    pytest can collect from (round 3 S6: "derive TEST_DIRS, SUITES and the smoke's path from one function"; this
    was the literal ["forge/tests", "tools/tests"])."""
    return G.suite(root)


# never collected by either arm: they need 150 MB of data at import and are listed in ci_gate.DATA_BOUND
ALWAYS_IGNORED = ["forge/tests/test_llm_author.py", "forge/tests/test_llm_formula.py"]

_LINE = re.compile(r"^(FAILED|ERROR) (\S+)")


def run_arm(cwd: pathlib.Path, python: str, suite=None) -> dict:
    """{'failed': set(nodeids), 'collect_errors': set(files), 'summary': str, 'incomplete': [why]} for one arm, run
    on `suite` (default suites(ROOT)). `--continue-on-collection-errors` stays: a file that fails at import is what
    this arm measures. `incomplete` is ci_gate's reading of the same output (run_incomplete, the gate asked for no
    deselection) plus the conftests of `cwd` that can narrow collection (_collection_narrowers)."""
    suite = suites(ROOT) if suite is None else list(suite)
    argv = [python, "-m", "pytest", *suite, "--no-header", "-rfE", "-p", "no:cacheprovider",
            "--continue-on-collection-errors", "-o", "addopts=",
            "-o", "python_files=" + " ".join(G.PYTHON_FILES), "-o", "python_classes=" + G.PYTHON_CLASSES,
            "-o", "python_functions=" + G.PYTHON_FUNCTIONS]
    for f in ALWAYS_IGNORED:
        argv += ["--ignore", f]
    # draw-5 ci 1: no ini file of the tree is read, as in check_tests (ci_gate.config_args), so both arms collect
    # what the gate collects
    with tempfile.TemporaryDirectory(prefix="wq-ci-ini-") as d:
        r = subprocess.run(argv + G.config_args(cwd, d), cwd=str(cwd), capture_output=True, text=True, timeout=3600,
                           env=G._pytest_env())
    failed, collect = set(), set()
    for line in (r.stdout or "").splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        node = m.group(2)
        if "::" in node:
            failed.add(node)
        else:
            collect.add(node)            # a whole file failed to import
    tail = [l for l in (r.stdout or "").splitlines() if re.search(r"\d+ (passed|failed)", l)]
    return {"failed": failed, "collect_errors": collect, "summary": tail[-1] if tail else "",
            "incomplete": G.run_incomplete(r.stdout, 0) + G._collection_narrowers(pathlib.Path(cwd), suite)}


def classify(data: dict, clean: dict) -> dict:
    red = sorted(data["failed"] | data["collect_errors"])
    data_bound_nodes = sorted(clean["failed"] - data["failed"])
    data_bound_files = sorted(clean["collect_errors"] - data["collect_errors"])
    return {"red": red, "deselect": data_bound_nodes, "ignore_files": data_bound_files}


def tests_hash(root=ROOT) -> str:
    """Content hash of every test file the classification covers -- mtimes are useless on a fresh checkout. Every
    test_*.py under a suite DIRECTORY, and each suite path that is a file (round 3 S6's test files outside
    TEST_DIRS); for a suite of directories only, the same bytes are hashed as before S6, so this hash moves only
    when such a file joins the suite."""
    import hashlib
    root = pathlib.Path(root)
    h = hashlib.sha256()
    for d in suites(root):
        for p in (sorted((root / d).rglob("test_*.py")) if (root / d).is_dir() else [root / d] if (root / d).is_file() else []):
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def code_version(root=ROOT) -> str:
    """Hash of every shipped file. Round 1: the staleness hash covered the tests only, so a code change
    that made a hermetic test data-bound (or red) left the classification looking current."""
    sys.path.insert(0, str(root / "tools"))
    import deploy as D
    # the classification's own output is not code under test: hashing it made every classification
    # stale the moment it was written (the first publish run showed exactly that warning on CI)
    fmap = {k: v for k, v in D.file_map(root).items() if k != "tools/ci_data_bound.json"}
    return D.version_id(D.content_hashes(fmap))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clean", required=True, help="path to a clean clone of the pipeline repository")
    ap.add_argument("--clean-python", required=True, help="the clean clone's interpreter (a bare venv)")
    a = ap.parse_args(argv)
    t0 = time.time()
    # The hash is taken BEFORE the arms run and again AFTER. MEASURED 2026-09-23: the fourth run
    # started at 10:09, test_deploy.py was edited at ~10:30 while it ran, and the hash -- then taken
    # only at the end -- certified test files neither arm had executed. A classification whose inputs
    # moved under it is not a measurement; nothing is written.
    before, code_before = tests_hash(), code_version()
    suite = suites(ROOT)                    # one suite for both arms: the same tests, measured two ways
    data = run_arm(ROOT, sys.executable, suite)
    clean = run_arm(pathlib.Path(a.clean), a.clean_python, suite)
    after, code_after = tests_hash(), code_version()
    if before != after or code_before != code_after:
        print("INVALID: test files changed while the arms ran (%s -> %s); nothing written" % (before, after))
        return 1
    short = ["%s arm: %s" % (name, w) for name, arm in (("DATA", data), ("CLEAN", clean)) for w in arm["incomplete"]]
    if short:
        # X2: an arm that did not run every collected test cannot say which tests are red or data-bound
        print("INVALID: an arm did not run and count every collected test; nothing written\n  " + "\n  ".join(short))
        return 1
    c = classify(data, clean)
    record = {
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seconds": round(time.time() - t0),
        "method": "two-arm run of the same code: DATA (working tree with state/ and fetched/) vs CLEAN "
                  "(fresh clone, bare venv with pytest+pyyaml+requests). data-bound = fails CLEAN and "
                  "passes DATA; red = fails DATA.",
        "tests_hash": before, "code_version": code_before, "suite": suite,
        "arm_data": data["summary"], "arm_clean": clean["summary"],
        **c,
    }
    OUT.write_text(json.dumps(record, indent=1) + "\n")
    print("DATA : %s" % data["summary"])
    print("CLEAN: %s" % clean["summary"])
    print("red (blocks everywhere): %d" % len(c["red"]))
    for n in c["red"]:
        print("   ", n)
    print("data-bound tests: %d | data-bound files (fail at import): %d" % (len(c["deselect"]), len(c["ignore_files"])))
    print("written:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
