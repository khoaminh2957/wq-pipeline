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
BASELINE = ROOT / "state/ci_baseline.json"


def _run(argv, timeout=1800, cwd=ROOT):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(cwd))


def check_tests(hermetic_only=True) -> dict:
    """Run the suite, and say plainly which part of it did not run."""
    argv = [sys.executable, "-m", "pytest", "forge/tests", "tools/tests", "-q", "--no-header"]
    if hermetic_only:
        for f in DATA_BOUND:
            argv += ["--ignore", f]
    r = _run(argv)
    lines = (r.stdout or "").strip().splitlines()
    tail = lines[-1:] or [""]
    # the first Actions run printed only "5 errors in 2.21s"; the cause had to be reproduced by hand.
    # A gate's log must say WHY it blocked.
    why = [l for l in lines if l.startswith(("FAILED ", "ERROR ")) or "ModuleNotFoundError" in l
           or "ImportError" in l][:12]
    return {"name": "tests", "ok": r.returncode == 0, "summary": tail[0], "details": why,
            "not_run": dict(DATA_BOUND) if hermetic_only else {},
            "covered_instead_by": "the VPS deploy smoke (tools/deploy.py SMOKE), which has the data",
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
            "a = B.axis3_gearing();"
            "bad = [f['name'] for f in a['fitness_functions'] if not f['ok']];"
            "print('%%d/%%d hold%%s' %% (a['held'], a['of'], '' if not bad else '  FAILING: ' + ', '.join(bad)));"
            "sys.exit(0 if a['floor_met'] else 1)" % str(root))
    r = _run([sys.executable, "-c", code])
    return {"name": "fitness", "ok": r.returncode == 0,
            "summary": (r.stdout or r.stderr or "").strip().splitlines()[-1:][0] if (r.stdout or r.stderr) else "",
            "blocking": True}


def check_branch_drill(root=ROOT) -> dict:
    """Grow one real branch on a copy of the library; the real planner must carry it with no code
    edited (forge/offline/branch_drill.py). This is what turns "can the pipeline be extended?" from an
    opinion into a build result, on every commit."""
    code = ("import sys, json; sys.path.insert(0, %r);"
            "from forge.offline import branch_drill as BD;"
            "r = BD.drill();"
            "print('%%s: %%d construction(s), code unchanged=%%s -- %%s' %% (r['status'], r.get('constructions', 0), r.get('code_unchanged'), r['note']));"
            "sys.exit(0 if r['ok'] else 1)" % str(root))
    r = _run([sys.executable, "-c", code])
    return {"name": "branch-drill", "ok": r.returncode == 0,
            "summary": (r.stdout or r.stderr or "").strip().splitlines()[-1:][0] if (r.stdout or r.stderr) else "",
            "blocking": True}


def check_regression(root=ROOT, baseline_path=None) -> dict:
    """D9: block when the composite score falls below the version that is live.

    The FLOOR is reported by the scorecard and never enforced here -- at the measured rate every
    version fails it, and a gate on the floor would freeze development for months. Regression is the
    thing a gate can act on today.
    With no baseline yet, this records one and passes: the first version defines the line.
    """
    bp = pathlib.Path(baseline_path or BASELINE)
    code = ("import sys, json; sys.path.insert(0, %r);"
            "from forge.offline import benchmark as B;"
            "c = B.build();"
            "print(json.dumps({'composite': c['composite_0_100'], 'verdict': c['verdict']}))" % str(root))
    r = _run([sys.executable, "-c", code])
    if r.returncode != 0:
        return {"name": "regression", "ok": False, "summary": "scorecard failed to build: %s"
                % (r.stderr or "")[-200:], "blocking": True}
    try:
        now = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"name": "regression", "ok": False, "summary": "unreadable scorecard", "blocking": True}
    if not bp.exists():
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(json.dumps({**now, "recorded_at": time.time()}, indent=1))
        return {"name": "regression", "ok": True,
                "summary": "no baseline; recorded %.1f as the line to beat" % now["composite"], "blocking": True}
    was = json.loads(bp.read_text())
    fell = now["composite"] < was.get("composite", 0)
    return {"name": "regression", "ok": not fell,
            "summary": "composite %.1f vs baseline %.1f%s" % (now["composite"], was.get("composite", 0),
                                                             "  REGRESSION" if fell else ""),
            "blocking": True}


CHECKS = (check_no_live, check_schema, check_version, check_fitness, check_branch_drill, check_tests, check_regression)


def gate(checks=CHECKS, out=print) -> int:
    results = [c() for c in checks]
    out("CI GATE")
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
    a = ap.parse_args(argv)
    if a.json:
        results = [c() for c in CHECKS]
        print(json.dumps(results, indent=1))
        return 1 if any(r["blocking"] and not r["ok"] for r in results) else 0
    return gate()


if __name__ == "__main__":
    sys.exit(main())
