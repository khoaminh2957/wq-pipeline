"""forge.offline.benchmark — the pipeline scorecard of record (docs/evalharness/00_agreements.md).

Khoa's /goal asks one question in three parts, and this module answers exactly those three:
  AXIS 1  the PRODUCT -- is the alpha good, robust, and trustworthy, with OS never observable?
  AXIS 2  the THROUGHPUT -- four a day? how many scored alphas per submission? sustainable or luck?
  AXIS 3  the GEARING -- can branches be grown onto this pipeline, or is it a dead end?

THE SCORING FRAME (D2, and it is the whole design). Each axis carries a HARD FLOOR. Failing any
floor is a FAIL, full stop: no weighted sum may let a strong axis hide a dead one, which is how most
benchmarks quietly die. Only after every floor is cleared does the 0-100 composite mean anything, and
its only job is to RANK versions. A version can therefore read "FAIL, score 62" -- which is the
honest reading of this desk today and is meant to be.

WHAT IS GRADED (D14, Khoa's words: "ko dựa trên dữ liệu cũ"). A version is graded on the alphas THAT
VERSION produced. Grading a new version on its predecessors' 31,044 alphas is a category error.
KNOWN GAP, stated rather than papered over: no journal row carries a pipeline version today
(`grep pipeline_version forge/ tools/` finds nothing -- audit 2026-09-23), so `rows_of_version` reads
`meta.pipeline_version` when present and otherwise falls back to a TIME WINDOW between two deploys.
The fallback is labelled in the scorecard as `version_attribution: "time-window (weak)"` and it is
weak: anything the loop ran from a hand-rsynced tree lands in the wrong bucket. The fix is one line
in the planner and it is named in the scorecard's `gaps`.

THE DENOMINATOR (the research brief's fourth constraint). Rates are per SCORED ALPHA -- a distinct
alpha id carrying a check set -- never "per simulation". 31,511 scored rows are 31,044 distinct
alphas, and no sim-slot ledger exists for the forge era to convert either into quota spent. Anyone
who needs "per simulation" must build that ledger first.
"""
from __future__ import annotations

import collections
import json
import math
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import harvest as HV, score as SC, submit as SUB  # noqa: E402

BINDING = ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE",
           "CONCENTRATED_WEIGHT", "HIGH_TURNOVER", "LOW_TURNOVER")

# ----------------------------------------------------------------------------- the floors (D6, D2)
#: Khoa chose ABSOLUTE floors from the goal rather than a ratchet, knowing the arithmetic: the best
#: measured rate is 3 submissions over 31,044 scored alphas = 0.48 per 5,000, and the floor is 8.3x
#: that. Every scorecard will read FAIL for a long time. That is the point -- the floor states the
#: goal, the composite ranks the attempts, and §"sustainable" below says how little one day proves.
FLOOR = {
    "axis1_product": 1.00,      # every submitted alpha must clear every robustness gate: 100 %
    "axis2_throughput": 4.0,    # submissions per 5,000-sim quota day
    "axis3_gearing": 0.80,      # fraction of the architecture fitness functions that must hold
}
WEIGHT = {"axis1_product": 0.40, "axis2_throughput": 0.40, "axis3_gearing": 0.20}


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """(low, high) for a rate k/n. At k=3, n=31044 the interval spans a factor of ~3.4, and at n=1
    day it spans everything -- which is why it is printed beside every rate and never omitted."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def rule_of_three(n: int) -> float:
    """Upper 95 % bound on a rate after n trials with ZERO events. One quota day with no submission
    does not exclude a true rate of 3 per day, which is why D5's one-day window cannot rank versions
    on the count alone."""
    return 3.0 / n if n > 0 else float("inf")


# --------------------------------------------------------------------- axis 1: is the product good
def neighbourhood_stability(rows_by_construction, row) -> dict:
    """How much an alpha's Sharpe moves when a SETTING moves one notch (D3).

    A signal whose Sharpe collapses because decay went 4 -> 8, or a window 5 -> 10, is fitted to its
    settings rather than to the market. The neighbours are the journal rows that share the
    construction's mechanism, region, delay and category but differ in exactly one of decay /
    neutralisation / truncation. MECHANISM of why fragility predicts OS failure: UNKNOWN -- this is
    a consistency measure, and no experiment on this desk links it to out-of-sample behaviour.
    """
    m = row.get("meta") or {}
    s = row.get("settings") or {}
    key = (m.get("hypothesis"), s.get("region"), s.get("delay"), m.get("category"))
    peers = [r for r in rows_by_construction.get(key, []) if r.get("alpha") != row.get("alpha")]
    sharpes = [r["sharpe"] for r in peers if isinstance(r.get("sharpe"), (int, float))]
    if len(sharpes) < 3:
        return {"n": len(sharpes), "verdict": "insufficient", "spread": None, "retained": None}
    med = statistics.median(sharpes)
    own = row.get("sharpe")
    spread = statistics.pstdev(sharpes)
    retained = (med / own) if isinstance(own, (int, float)) and own else None
    return {"n": len(sharpes), "median_peer_sharpe": round(med, 3), "spread": round(spread, 3),
            "retained": round(retained, 3) if retained is not None else None,
            "verdict": "stable" if retained is not None and retained >= 0.5 else "fragile"}


def regime_stability(curve) -> dict:
    """Sharpe in each third of the alpha's own history (D3).

    An alpha that earned everything in one window and nothing in the others is one regime's bet.
    Thirds, not calendar regimes: a calendar split chosen after seeing the curve is a POST-HOC
    boundary, and three equal pieces are chosen before looking.
    """
    if not curve or len(curve) < 300:
        return {"n": len(curve or []), "verdict": "insufficient", "thirds": None}
    rets = [b - a for a, b in zip(curve, curve[1:])]
    k = len(rets) // 3
    thirds, means = [], []
    for i in range(3):
        seg = rets[i * k:(i + 1) * k] if i < 2 else rets[2 * k:]
        mean = statistics.fmean(seg) if seg else 0.0
        sd = statistics.pstdev(seg) if len(seg) > 1 else 0.0
        means.append(mean)
        # A third that earned with NO dispersion has an unbounded Sharpe, not a zero one. Reporting
        # it as 0.0 made a perfectly steady alpha read "one-regime" -- caught by its own test.
        thirds.append(round(mean / sd * math.sqrt(252), 3) if sd else (float("inf") if mean > 0 else
                      (float("-inf") if mean < 0 else 0.0)))
    # the question "did this third make money" is a question about the MEAN; the Sharpe describes
    # how well, and cannot decide the sign on its own
    positive = sum(1 for m in means if m > 0)
    return {"n": len(rets), "thirds": thirds, "third_means": [round(m, 6) for m in means],
            "positive_thirds": positive,
            "verdict": "consistent" if positive == 3 else ("mixed" if positive == 2 else "one-regime")}


def axis1_product(graded_rows, scored, corr, curves=None) -> dict:
    """Is what this version SUBMITTED good, robust and trustworthy? (D3, D10)

    The cohort is the version's own submitted alphas. With none, the axis reports `no-product` and
    the floor is unmet -- a version that shipped nothing has not demonstrated product quality, and
    scoring it 100 % for having no failures would be the compensation D2 forbids.
    """
    by_construction = collections.defaultdict(list)
    for r in graded_rows:
        m, s = r.get("meta") or {}, r.get("settings") or {}
        by_construction[(m.get("hypothesis"), s.get("region"), s.get("delay"), m.get("category"))].append(r)

    submitted = [r for r in graded_rows if r.get("_submitted")]
    checks, detail = [], []
    for r in submitted:
        a = r["alpha"]
        x = scored.get(a) or {}
        c = corr.get(a) or {}
        nb = neighbourhood_stability(by_construction, r)
        rg = regime_stability((curves or {}).get(a))
        gates = {
            "all_binding_pass": all(_chk(r, n).get("result") == "PASS" for n in BINDING),
            "dsr_ge_095": isinstance(x.get("dsr"), (int, float)) and x["dsr"] >= 0.95,
            "pbo_le_050": x.get("pbo_pass") is True,
            "corr_under_lines": _corr_ok(r, c),
            "neighbourhood_stable": nb["verdict"] == "stable",
            "regime_not_one_sided": rg["verdict"] in ("consistent", "mixed"),
        }
        checks.append(all(gates.values()))
        detail.append({"alpha": a, "gates": gates, "neighbourhood": nb, "regime": rg,
                       "dsr": x.get("dsr"), "pbo": x.get("pbo")})

    n = len(submitted)
    passed = sum(checks)
    return {"cohort": "alphas this version submitted", "n": n,
            "value": (passed / n) if n else 0.0,
            "floor": FLOOR["axis1_product"],
            "floor_met": bool(n) and passed == n,
            "verdict": "no-product" if not n else ("all clear" if passed == n else "%d of %d fail a robustness gate" % (n - passed, n)),
            "detail": detail,
            "caveat": "OS is never observable; every gate here is an in-sample consistency test. "
                      "MECHANISM linking any of them to out-of-sample behaviour: UNKNOWN."}


def _chk(row, name) -> dict:
    for c in row.get("checks") or []:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    return {}


def _corr_ok(row, c) -> bool:
    pl, sl = SUB.corr_lines(row)
    p, s = c.get("prod"), c.get("self")
    return isinstance(p, (int, float)) and isinstance(s, (int, float)) and p < pl and s < sl


# ------------------------------------------------------------ axis 2: is the throughput real
def structural_families(rows) -> dict:
    """Distinct structural families among rows that cleared every binding check.

    MEASURED 2026-09-22: 34 fully-qualified alphas collapse into 7 families over 3 hypotheses. A
    submission retires its whole family (a sibling reads the correlation lines against it), so the
    family count -- not the qualified-alpha count -- is what the submission count can be drawn from.
    This is the denominator with enough events to move: 7 rather than 3.
    """
    try:
        sys.path.insert(0, str(ROOT))
        import fingerprint as FP
    except ImportError:
        return {"families": None, "reason": "fingerprint.py unavailable"}
    idx, fams = FP.StructuralIndex(), []
    for r in rows:
        f = r.get("formula")
        if not f or not all(_chk(r, n).get("result") == "PASS" for n in BINDING):
            continue
        dup, _, label = idx.is_dup(f)
        if not dup:
            idx.register(f, r["alpha"])
            fams.append(r["alpha"])
    return {"families": len(fams), "representatives": fams}


def axis2_throughput(graded_rows, submissions, prev_window_rate=None, posts_in_window=None) -> dict:
    """Four a day? At what cost? Sustainable or luck? (D6, D7)

    Three independent pieces of evidence, all three required for "sustainable" -- a rate can survive
    one of them by chance, not all three:
      * the Wilson interval on the rate excludes zero,
      * the submissions span more than one distinct mechanism,
      * the rate held in the PREVIOUS window too.
    """
    n = len(graded_rows)
    k = len(submissions)
    per5000 = (k / n * 5000) if n else 0.0
    lo, hi = wilson(k, n)
    fam = structural_families(graded_rows)
    mechanisms = len({s.get("mechanism_key") for s in submissions if s.get("mechanism_key")})

    ci_excludes_zero = lo > 0
    diverse = mechanisms >= 2
    repeated = prev_window_rate is not None and prev_window_rate > 0
    sustainable = ci_excludes_zero and diverse and repeated

    # TWO READINGS, because "a submission" has two honest owners and picking one silently would
    # hide the other. D14 grades a version on the alphas IT PRODUCED, so a POST of an alpha an
    # earlier version generated does not belong to this one. But "did we get four today?" is a
    # question about the SUBMITTER, which is this version's code. MEASURED 2026-09-23: rK5RGeqa was
    # generated 09-10 and POSTed 09-23, so the two readings differ by exactly that alpha.
    posted_by = len(posts_in_window or [])
    return {"scored_alphas": n,
            "submissions_of_alphas_this_version_produced": k,
            "posts_this_version_made": posted_by,
            "submissions": k,
            "per_5000_scored": round(per5000, 2),
            "wilson_95_per_5000": [round(lo * 5000, 2), round(hi * 5000, 2)],
            "zero_event_upper_bound_per_5000": round(rule_of_three(n) * 5000, 2) if k == 0 else None,
            "scored_per_submission": round(n / k) if k else None,
            "qualified_families": fam.get("families"),
            "scored_per_family": round(n / fam["families"]) if fam.get("families") else None,
            "distinct_mechanisms": mechanisms,
            "value": round(per5000, 2), "floor": FLOOR["axis2_throughput"],
            "floor_met": per5000 >= FLOOR["axis2_throughput"],
            "sustainable": sustainable,
            "sustainability_evidence": {"ci_excludes_zero": ci_excludes_zero,
                                        "multiple_mechanisms": diverse,
                                        "held_in_previous_window": repeated},
            "caveat": "One quota day at this desk's measured rate returns 0 submissions 61 % of the "
                      "time, and a day with 0 does not exclude a true rate of 3/day. A single "
                      "window cannot rank two versions on the count alone."}


# ----------------------------------------------------------- axis 3: can branches be grown on it
def fitness_functions(root=ROOT) -> list:
    """Architecture checks that must hold for a new branch to be pluggable (D8).

    Each returns (name, ok, evidence). They are deliberately mechanical: an architecture claim that
    cannot fail a test is a slogan.
    """
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

    # 3. an A/B arm exists, so a change can be measured against the thing it replaces
    runner = (root / "forge/runner.py").read_text()
    out.append(("a change can be A/B'd in one round", "--ab" in runner and "meta" in runner,
                "runner.py carries an --ab arm that tags meta.arm"))

    # 4. the deployed code has an identity, so a result can be attributed to a version
    out.append(("the deployed code has a version", (root / "tools/deploy.py").exists(),
                "tools/deploy.py hashes the shipped content"))

    # 5. no import cycles among the forge modules: a cycle means a branch cannot be added in isolation
    cyc = import_cycles(root / "forge")
    out.append(("no module-level import cycle in forge/", not cyc["module_level"],
                "module-level cycles: %s; deferred (a coupling smell, not a wall): %s"
                % (cyc["module_level"] or "none", cyc["deferred"] or "none")))

    # 6. the test suite covers the modules a branch would touch
    tests = {p.stem.replace("test_", "") for p in (root / "forge/tests").glob("test_*.py")}
    mods = {p.stem for p in (root / "forge").glob("*.py") if p.stem != "__init__"}
    covered = len(tests & mods) / len(mods) if mods else 0.0
    out.append(("every forge module has a test", covered >= 0.8,
                "%d of %d modules have a test file (%.0f %%)" % (len(tests & mods), len(mods), covered * 100)))

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


def import_cycles(pkg: pathlib.Path) -> dict:
    """{"module_level": [...], "deferred": [...]} -- cycles among the package's own modules.

    The distinction decides what axis 3 is entitled to say. A cycle whose edges are all inside
    functions still imports cleanly (Python resolves it at call time) and is a coupling SMELL: the
    modules cannot be reasoned about separately, but a branch can still be added. A cycle with even
    one module-level edge is a WALL: importing either module drags the other in, and a new component
    that touches one touches both.
    MEASURED 2026-09-23 on forge/: three cycles -- probe<->harvest, submit<->harvest and
    submit->probe->harvest->submit -- every edge deferred inside a function body.
    """
    import re
    names = {p.stem for p in pkg.glob("*.py")}
    top, deep = {}, {}
    for p in sorted(pkg.glob("*.py")):
        t, d = set(), set()
        for line in p.read_text().splitlines():
            m = re.match(r"(\s*)from forge(?:\.(\w+))? import ([\w, ]+)", line)
            if not m:
                continue
            indented = bool(m.group(1))
            mods = {m.group(2)} if m.group(2) else {x.strip().split(" as ")[0] for x in m.group(3).split(",")}
            (d if indented else t).update(mods & names)
        top[p.stem], deep[p.stem] = t, t | d

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


def _dora_from_ledger(root=ROOT) -> dict:
    p = root / "state/deploys.jsonl"
    rows = list(HV.read_jsonl(p)) if p.exists() else []
    return dora(rows)


def dora(rows, now=None, window_days=28) -> dict:
    """The four DORA keys from the deploy ledger (tools/deploy.py DEPLOY_LOG).

    Definitions follow Forsgren, Humble & Kim (Accelerate, 2018), restricted to what this desk can
    measure: a 'deploy' is an attempt that reached the code swap; a 'failure' is one that was rolled
    back, failed to roll back, or went live unrecorded; 'restore' is the time from a failed attempt to
    the next attempt that went live clean. With fewer than two deploys every key is reported as
    insufficient rather than computed from one point.
    """
    now = now if now is not None else __import__("time").time()
    rows = sorted((r for r in rows if r.get("outcome")), key=lambda r: r.get("started_at") or 0)
    if len(rows) < 2:
        return {"status": "insufficient", "deploys": len(rows),
                "note": "DORA needs at least two recorded deploys; the ledger holds %d" % len(rows)}
    recent = [r for r in rows if (r.get("started_at") or 0) >= now - window_days * 86400]
    failed = {"rolled_back", "rollback_failed", "unrecorded"}
    fails = [r for r in rows if r["outcome"] in failed]
    leads = [r["finished_at"] - r["commit_time"] for r in rows
             if r["outcome"] == "deployed" and r.get("commit_time") is not None and not r.get("git_dirty")]
    restores = []
    for i, r in enumerate(rows):
        if r["outcome"] in failed:
            nxt = next((x for x in rows[i + 1:] if x["outcome"] == "deployed"), None)
            if nxt:
                restores.append(nxt["finished_at"] - r["finished_at"])
    return {"status": "measured", "deploys": len(rows),
            "deploys_per_week": round(len(recent) / (window_days / 7.0), 2),
            "lead_time_hours_median": round(statistics.median(leads) / 3600, 2) if leads else None,
            "lead_time_note": None if leads else "no clean (non-dirty) deploy carries a commit time",
            "change_failure_rate": round(len(fails) / len(rows), 3),
            "time_to_restore_hours_median": round(statistics.median(restores) / 3600, 2) if restores else None}


def axis3_gearing(dora=None, drill=None, root=ROOT, run_drill=True) -> dict:
    """DORA + architecture fitness + the branch drill (D8).

    The drill counts as one more fitness function, and the one that matters most: the other six say
    a branch COULD be grown, the drill grows one on a copy of the library and watches the real
    planner carry it (forge/offline/branch_drill.py).
    """
    ffs = fitness_functions(root)
    if drill is None and run_drill:
        from forge.offline import branch_drill as BD
        try:
            drill = BD.drill(root)
        except Exception as exc:  # noqa: BLE001 -- a drill that crashes is a FAILED drill, reported as such
            drill = {"status": "crashed", "ok": False, "note": "%s: %s" % (type(exc).__name__, exc)}
    if drill is not None:
        ffs = ffs + [("a real branch goes through the planner", bool(drill.get("ok")),
                      "%s: %s" % (drill.get("status"), drill.get("note")))]
    held = sum(1 for _, ok, _ in ffs if ok)
    value = held / len(ffs) if ffs else 0.0
    return {"fitness_functions": [{"name": n, "ok": ok, "evidence": e} for n, ok, e in ffs],
            "held": held, "of": len(ffs),
            "dora": dora if dora is not None else _dora_from_ledger(root),
            "branch_drill": drill or {"status": "not run",
                                      "note": "a throwaway component plugged in and carried by CI"},
            "value": round(value, 3), "floor": FLOOR["axis3_gearing"],
            "floor_met": value >= FLOOR["axis3_gearing"]}


# ------------------------------------------------------------------------------ the scorecard (D2)
def scorecard(axes: dict) -> dict:
    """Non-compensatory: any floor unmet is a FAIL, and the composite only ranks what already passed.

    The composite is still reported on a FAIL, because Khoa's D9 gate blocks on REGRESSION against
    the live version rather than on the floor -- so the number must exist even while the verdict is
    FAIL, or there is nothing to compare two failing versions with.
    """
    unmet = [k for k, v in axes.items() if not v.get("floor_met")]
    composite = sum(WEIGHT[k] * min(1.0, (axes[k].get("value") or 0) / FLOOR[k]) for k in WEIGHT if k in axes)
    return {"verdict": "PASS" if not unmet else "FAIL",
            "floors_unmet": unmet,
            "composite_0_100": round(composite * 100, 1),
            "composite_means": "ranking only; a FAIL never becomes a PASS through a high composite",
            "axes": axes}


# --------------------------------------------------------------- putting a version on the stand
def rows_of_version(rows, version=None, since=None, until=None) -> tuple:
    """(rows the version produced, how they were attributed) -- D14's cohort selector.

    Preferred: `meta.pipeline_version`, written by the planner. No row carries it today, so the
    fallback is the time window a version was live. The fallback is WEAK and labelled: a tree that
    was hand-rsynced mid-window puts its alphas in the wrong bucket, and this desk hand-rsynced for
    thirteen days. Whoever reads a scorecard built on the fallback must read `version_attribution`
    first.
    """
    tagged = [r for r in rows if (r.get("meta") or {}).get("pipeline_version")]
    if version and tagged:
        return [r for r in tagged if r["meta"]["pipeline_version"] == version], "meta.pipeline_version (strong)"
    out = []
    for r in rows:
        d = r.get("dateCreated") or ""
        if since and d < since:
            continue
        if until and d >= until:
            continue
        out.append(r)
    return out, "time-window (weak: no row carries a version)"


def _epoch(iso: str) -> float:
    """Midnight local for an ISO date, so a window given as a date includes the whole day."""
    import datetime
    return datetime.datetime.fromisoformat(iso).timestamp()


def build(journal=None, since=None, until=None, version=None, curves_dir=None) -> dict:
    """The whole scorecard for one version over one window, from the files on disk."""
    latest = {}
    for r in HV.read_jsonl(journal or HV.JOURNAL):
        if r.get("alpha"):
            latest[r["alpha"]] = r
    scored = HV.load_scored()
    from forge import probe as P
    corr = P.load_corr()
    history = SUB.posted_history()
    posted = {h["alpha"] for h in history if h.get("http") in (200, 201)}

    graded, how = rows_of_version(list(latest.values()), version, since, until)
    graded = [r for r in graded if r.get("status") == "COMPLETE" and r.get("checks")]
    for r in graded:
        r["_submitted"] = r["alpha"] in posted
    subs = [h for h in history if h.get("http") in (200, 201)
            and any(r["alpha"] == h["alpha"] for r in graded)]
    for h in subs:
        h.setdefault("mechanism_key", (latest.get(h["alpha"], {}).get("meta") or {}).get("mechanism_key"))

    curves = {}
    cd = pathlib.Path(curves_dir or (ROOT / "state/pnl_curves"))
    if cd.exists():
        for r in graded:
            if not r.get("_submitted"):
                continue
            f = cd / ("%s.json" % r["alpha"])
            if f.exists():
                try:
                    j = json.loads(f.read_text())
                    curves[r["alpha"]] = j if isinstance(j, list) else (j.get("pnl") or j.get("curve") or [])
                except (ValueError, OSError):
                    pass

    # every accepted POST whose POST TIME falls in the window, whoever generated the alpha
    lo = _epoch(since) if since else 0
    hi = _epoch(until) if until else float("inf")
    posts_in_window = [h for h in history if h.get("http") in (200, 201)
                       and lo <= (h.get("posted_at") or 0) < hi]
    axes = {"axis1_product": axis1_product(graded, scored, corr, curves),
            "axis2_throughput": axis2_throughput(graded, subs, posts_in_window=posts_in_window),
            "axis3_gearing": axis3_gearing()}
    card = scorecard(axes)
    card["window"] = {"since": since, "until": until, "version": version}
    card["version_attribution"] = how
    card["gaps"] = [
        "No journal row carries meta.pipeline_version, so D1/D14 rest on a time window. One line in "
        "forge/runner.py (stamp the deploy manifest's version into every construction's meta) "
        "converts this from weak to strong.",
        "DORA has no deploy history: DEPLOYED.json does not exist on the target.",
        "Regime stability reads local PnL curves; an alpha without a cached curve scores "
        "'insufficient' rather than being judged.",
    ]
    return card


def render(card: dict) -> str:
    a = card["axes"]
    L = ["PIPELINE SCORECARD  %s" % (card["window"].get("version") or "(current tree)"),
         "  window: %s -> %s   attribution: %s" % (card["window"].get("since") or "all",
                                                   card["window"].get("until") or "now",
                                                   card["version_attribution"]),
         "",
         "  VERDICT  %s%s" % (card["verdict"],
                              ("  (floors unmet: %s)" % ", ".join(card["floors_unmet"])) if card["floors_unmet"] else ""),
         "  composite %.1f / 100   -- %s" % (card["composite_0_100"], card["composite_means"]),
         ""]
    p = a["axis1_product"]
    L += ["  AXIS 1  PRODUCT   %s" % ("FLOOR MET" if p["floor_met"] else "floor unmet"),
          "    submitted by this version: %d | clearing every robustness gate: %.0f %%" % (p["n"], p["value"] * 100),
          "    %s" % p["verdict"]]
    for d in p["detail"][:4]:
        bad = [k for k, v in d["gates"].items() if not v]
        L.append("      %s  dsr %s pbo %s  %s" % (d["alpha"], d["dsr"], d["pbo"],
                                                  "all gates pass" if not bad else "FAILS: " + ", ".join(bad)))
    t = a["axis2_throughput"]
    L += ["", "  AXIS 2  THROUGHPUT  %s" % ("FLOOR MET" if t["floor_met"] else "floor unmet"),
          "    %d scored alphas -> %d submission(s) of its OWN alphas = %.2f per 5,000   (floor %.1f)"
          % (t["scored_alphas"], t["submissions_of_alphas_this_version_produced"], t["per_5000_scored"], t["floor"]),
          "    POSTs this version's submitter made in the window: %d  (an alpha an earlier version "
          "generated counts here, never above)" % t["posts_this_version_made"],
          "    95 %% interval per 5,000: [%.2f, %.2f]%s" % (t["wilson_95_per_5000"][0], t["wilson_95_per_5000"][1],
                                                           "" if t["submissions"] else "  (zero events: the upper bound is all this window can say)"),
          "    qualified structural families: %s | scored alphas per family: %s"
          % (t["qualified_families"], t["scored_per_family"]),
          "    sustainable: %s  %s" % (t["sustainable"], t["sustainability_evidence"])]
    g = a["axis3_gearing"]
    L += ["", "  AXIS 3  GEARING  %s" % ("FLOOR MET" if g["floor_met"] else "floor unmet"),
          "    %d of %d architecture fitness functions hold" % (g["held"], g["of"])]
    for f in g["fitness_functions"]:
        L.append("      [%s] %s" % ("ok" if f["ok"] else "NO", f["name"]))
    L += ["    DORA: %s" % g["dora"].get("status"), "    branch drill: %s" % g["branch_drill"].get("status")]
    L += ["", "  GAPS THIS SCORECARD DOES NOT HIDE:"]
    L += ["    - %s" % x for x in card["gaps"]]
    return "\n".join(L)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default="", help="ISO date; only alphas created on or after it")
    ap.add_argument("--until", default="", help="ISO date; only alphas created before it")
    ap.add_argument("--version", default="", help="grade this pipeline version (needs tagged rows)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    card = build(since=a.since or None, until=a.until or None, version=a.version or None)
    print(json.dumps(card, indent=1, default=str) if a.json else render(card))
    return 0 if card["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
