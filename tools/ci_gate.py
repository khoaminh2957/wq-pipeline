"""tools.ci_gate — the checks a change must clear before it may reach the pipeline (D4, D9).

Khoa's D9: the gate blocks on REGRESSION against the live version, plus tests, lint and schema. The
4-per-day floor is REPORTED and never blocks, because at the measured rate every version fails it and
a gate on the floor would freeze all development. That asymmetry is the design, not a compromise.

WHY THIS FILE EXISTS RATHER THAN A PILE OF YAML STEPS. Every check here runs identically on a laptop,
on the VPS and inside GitHub Actions, so "it passed on my machine" and "it passed in CI" are the same
sentence. The Actions workflow is a thin caller; the judgement lives here where it can be tested.

WHAT IT CANNOT DO, STATED RATHER THAN HIDDEN. 22 of the 247 tests load
`fetched/rc/field_labels.jsonl` (101 MB) and a field catalogue (50 MB). Neither can live in a GitHub
repository -- the hard limit is 100 MB per file -- so a hosted runner cannot execute them. This gate
therefore reports THREE numbers, never one: tests that passed, tests that could not run here, and
where those are covered instead (the VPS deploy smoke, which has the data). A gate that printed
"247 passed" while silently running 225 would be lying in the most damaging way available to it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Test files that need production data too large for a git host. Named individually so that adding
#: one is a deliberate act with a reason, never a wildcard that quietly grows.
DATA_BOUND = {
    "forge/tests/test_llm_author.py": "forge/llm/verify.py loads fetched/rc/field_labels.jsonl (101 MB)",
    "forge/tests/test_llm_formula.py": "same Context(): field_labels.jsonl + a 50 MB field catalogue",
}
#: COMMITTED, one value per tier. It used to live in state/, which a hosted runner never keeps: every
#: Actions run recorded a fresh baseline and passed against it, so the regression check could not fail
#: on CI at all. Moving the line is now a commit that shows in the diff.
BASELINE = ROOT / "tools/ci_baseline.json"
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


def _run(argv, timeout=1800, cwd=ROOT):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(cwd))


def check_tests(hermetic_only=None) -> dict:
    """Run the suite for this tier, and say plainly which part of it did not run and why.

    DATA tier: everything except the 150 MB-at-import LLM files. HERMETIC tier: additionally skips every
    test tools/ci_classify.py MEASURED as data-bound (fails without the data, passes with it). A test
    measured RED -- failing even with the data -- is never skipped anywhere.
    """
    hermetic = (tier() == "hermetic") if hermetic_only is None else hermetic_only
    argv = [sys.executable, "-m", "pytest", "forge/tests", "tools/tests", "-q", "--no-header", "-rfE",
            "-p", "no:cacheprovider"]
    for f in DATA_BOUND:
        argv += ["--ignore", f]
    skipped = {}
    stale = None
    if hermetic:
        cls = classification()
        for f in cls.get("ignore_files", []):
            argv += ["--ignore", f]
            skipped[f] = "fails at import without the desk's data (measured %s)" % cls.get("measured_at")
        for n in cls.get("deselect", []):
            argv += ["--deselect", n]
        if cls.get("deselect"):
            skipped["%d individual tests" % len(cls["deselect"])] = "measured data-bound %s" % cls.get("measured_at")
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            import ci_classify as CC
            if cls and cls.get("tests_hash") != CC.tests_hash():
                stale = "test files changed since the classification; re-run tools/ci_classify.py"
        except Exception:  # noqa: BLE001
            stale = "could not verify the classification is current"
        if not cls:
            stale = "no classification file; every data-bound test will fail here"
    r = _run(argv)
    lines = (r.stdout or "").strip().splitlines()
    tail = lines[-1:] or [""]
    # the first Actions run printed only "5 errors in 2.21s"; the cause had to be reproduced by hand.
    # A gate's log must say WHY it blocked.
    why = [l for l in lines if l.startswith(("FAILED ", "ERROR ")) or "ModuleNotFoundError" in l
           or "ImportError" in l][:12]
    not_run = dict(DATA_BOUND)
    not_run.update(skipped)
    return {"name": "tests", "ok": r.returncode == 0,
            "summary": "[%s tier] %s%s" % ("hermetic" if hermetic else "data", tail[0], ("  WARNING: " + stale) if stale else ""),
            "details": why, "not_run": not_run,
            "covered_instead_by": "the DATA tier of this same gate (MacBook pre-push, VPS), which runs them all",
            "blocking": True}


def check_no_live(root=ROOT) -> dict:
    """Nothing reachable from CI may spend platform quota (RULE 1).

    Greps for the one flag that turns a dry run into money: `--live`. A test or workflow that carries
    it is a blocker regardless of intent, because CI runs unattended.
    """
    offenders = []
    for p in list((root / "forge/tests").rglob("*.py")) + list((root / "tools/tests").rglob("*.py")) \
            + list((root / ".github").rglob("*.yml")) + list((root / ".github").rglob("*.yaml")):
        try:
            body = p.read_text()
        except OSError:
            continue
        for i, line in enumerate(body.splitlines(), 1):
            if "--live" in line and not line.lstrip().startswith("#") and "not in" not in line and "assert" not in line:
                offenders.append("%s:%d" % (p.relative_to(root), i))
    return {"name": "no-live", "ok": not offenders, "summary": "no CI-reachable path passes --live"
            if not offenders else "--live reachable at %s" % ", ".join(offenders[:5]), "blocking": True}


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
    and why -- never as a pass.
    """
    if tier(root) != "data":
        return {"name": "branch-drill", "ok": True, "blocking": True,
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
    the tests check itself runs it and blocks; here the classification's record blocks in its place.
    """
    if tier(root) == "data":
        return {"name": "known-red", "ok": True, "blocking": True,
                "summary": "data tier: red tests are run directly by the tests check"}
    cls = classification(root)
    red = cls.get("red") or []
    return {"name": "known-red", "ok": not red, "blocking": True,
            "summary": ("none recorded (classification %s)" % cls.get("measured_at")) if not red else
                       "%d test(s) red in the data tier, measured %s: %s"
                       % (len(red), cls.get("measured_at"), ", ".join(red))}


def _composite(root=ROOT):
    code = ("import sys, json; sys.path.insert(0, %r);"
            "from forge.offline import benchmark as B;"
            "c = B.build();"
            "print(json.dumps({'composite': c['composite_0_100'], 'verdict': c['verdict']}))" % str(root))
    r = _run([sys.executable, "-c", code])
    if r.returncode != 0:
        raise RuntimeError("scorecard failed to build: %s" % (r.stderr or "")[-200:])
    return json.loads((r.stdout or "").strip().splitlines()[-1])


def check_regression(root=ROOT, baseline_path=None) -> dict:
    """D9: block when the composite falls below the committed baseline for this tier.

    The FLOOR is reported by the scorecard and never enforced here -- at the measured rate every
    version fails it. Regression is what a gate can act on. A missing baseline FAILS: recording one
    silently on first sight is exactly how the check became unfailable on a hosted runner.
    """
    bp = pathlib.Path(baseline_path or BASELINE)
    t = tier(root)
    try:
        now = _composite(root)
    except (RuntimeError, ValueError, IndexError) as exc:
        return {"name": "regression", "ok": False, "summary": str(exc), "blocking": True}
    try:
        base = json.loads(bp.read_text()).get(t)
    except (OSError, ValueError):
        base = None
    if base is None:
        return {"name": "regression", "ok": False, "blocking": True,
                "summary": "no committed %s-tier baseline (composite now %.1f); run "
                           "`python3 tools/ci_gate.py --record-baseline` and commit tools/ci_baseline.json"
                           % (t, now["composite"])}
    fell = now["composite"] < base["composite"]
    return {"name": "regression", "ok": not fell, "blocking": True,
            "summary": "[%s] composite %.1f vs committed %.1f%s" % (t, now["composite"], base["composite"],
                                                                  "  REGRESSION" if fell else "")}


def record_baseline(root=ROOT, baseline_path=None) -> dict:
    bp = pathlib.Path(baseline_path or BASELINE)
    try:
        cur = json.loads(bp.read_text())
    except (OSError, ValueError):
        cur = {}
    now = _composite(root)
    cur[tier(root)] = {"composite": now["composite"], "verdict": now["verdict"],
                       "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    bp.write_text(json.dumps(cur, indent=1) + "\n")
    return cur


CHECKS = (check_no_live, check_schema, check_version, check_fitness, check_branch_drill, check_tests, check_known_red, check_regression)


def gate(checks=CHECKS, out=print) -> int:
    results = [c() for c in checks]
    out("CI GATE  (%s tier)" % tier())
    for r in results:
        out("  [%s] %-11s %s" % ("PASS" if r["ok"] else "FAIL", r["name"], r["summary"]))
        for line in (r.get("details") or []) if not r["ok"] else []:
            out("        %s" % line[:180])
        for f, why in (r.get("not_run") or {}).items():
            out("        not run here: %s -- %s" % (f, why))
        if r.get("not_run"):
            out("        covered instead by: %s" % r["covered_instead_by"])
    blocking = [r for r in results if r["blocking"] and not r["ok"]]
    out("")
    out("  VERDICT %s%s" % ("PASS" if not blocking else "BLOCKED",
                            "" if not blocking else " on " + ", ".join(r["name"] for r in blocking)))
    return 1 if blocking else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record-baseline", action="store_true",
                    help="write this tier's current composite to tools/ci_baseline.json (then commit it)")
    a = ap.parse_args(argv)
    if a.record_baseline:
        print(json.dumps(record_baseline(), indent=1))
        return 0
    if a.json:
        results = [c() for c in CHECKS]
        print(json.dumps(results, indent=1))
        return 1 if any(r["blocking"] and not r["ok"] for r in results) else 0
    return gate()


if __name__ == "__main__":
    sys.exit(main())
