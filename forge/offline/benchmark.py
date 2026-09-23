"""forge.offline.benchmark — the pipeline scorecard of record (docs/evalharness/00_agreements.md).

Khoa's /goal asks one question in three parts, and this module answers exactly those three:
  AXIS 1  the PRODUCT -- is the alpha good, robust, and trustworthy, with OS never observable?
  AXIS 2  the THROUGHPUT -- four a day? how many scored alphas per submission? sustainable or luck?
  AXIS 3  the GEARING -- can branches be grown onto this pipeline, or is it a dead end?

DRAW 2 (docs/evalharness/01_architecture.md), after adversarial round 1 found the composite unable to
rank, axis 1 structurally zero, axis 2 in the wrong unit and the pre-merge gate grading the journal
instead of the diff. What changed in structure:
  * `build_from()` is PURE -- rows, scores, curves in; a card out. `build()` only reads files. So the
    scorer can be run on a FROZEN fixture and pinned by a golden card (tools/ci_gate.py), and a change to
    any floor, weight or gate shows in the diff of that golden file.
  * `compare()` judges a VERSION after it has run: cohorts stamped with meta.pipeline_version, equal
    numbers of ET quota days, Poisson intervals, and a verdict that is allowed to be "indistinguishable".
  * Days are ET QUOTA days (the platform resets at 00:00 America/New_York), whole days only.

THE SCORING FRAME (D2). Each axis carries a HARD FLOOR; failing any floor is a FAIL, whatever the
others score. The composite only RANKS: per axis s = min(value / floor, 2), composite = 100·Σ w·s / 2,
so meeting a floor contributes half that axis's weight and twice the floor contributes all of it. It
is monotone in clean output and does not saturate at the floor (round 1, F4).

WHAT IS GRADED (D14, "ko dựa trên dữ liệu cũ"): the rows the graded version produced. With a version
id, by `meta.pipeline_version`; without one, by the ET quota-day window, labelled WEAK.

THE DENOMINATOR: rows scored = distinct alpha ids carrying a check set with status COMPLETE or WARNING
(round 1: WARNING rows are 16 % of the journal and include the first ACTIVE submission). No sim-slot
ledger exists to convert scored alphas into quota spent.
"""
from __future__ import annotations

import collections
import datetime
import json
import math
import pathlib
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

# ----------------------------------------------------------------------------- the floors (D6, D2)
#: Khoa chose ABSOLUTE floors from the goal (D6). The best measured rate is ~0.5 submissions per quota
#: day; the axis-2 floor is 4. Every card reads FAIL for a long time -- the floor states the goal, the
#: composite ranks attempts. Changing any number here changes the pinned golden card (tools/ci_gate.py).
FLOOR = {
    "axis1_product": 1.00,      # every submitted alpha PROVEN: every robustness gate measured and passed
    "axis2_throughput": 4.0,    # clean submissions per ET quota day
    "axis3_gearing": 0.80,      # fraction of the measured architecture checks that hold
}
WEIGHT = {"axis1_product": 0.40, "axis2_throughput": 0.40, "axis3_gearing": 0.20}
#: An UNPROVEN alpha (no gate failed, at least one could not be measured) counts half in axis 1's value.
#: A convention, not a measurement: it keeps "we could not look" apart from both "it passed" and "it
#: failed". It never affects the floor, which requires every alpha PROVEN.
UNPROVEN_CREDIT = 0.5
#: DORA thresholds for axis 3: the "high performer" band of Forsgren, Humble & Kim, Accelerate (2018) and
#: the State of DevOps report of the same series. EX-ANTE, taken from the literature, not fitted here.
DORA_BAND = {"change_failure_rate_max": 0.15, "time_to_restore_hours_max": 24.0, "deploys_per_week_min": 1.0}


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


def _poisson_cdf(k: int, lam: float) -> float:
    term, total = math.exp(-lam), math.exp(-lam)
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return total


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


# --------------------------------------------------------------------- axis 1: is the product good
def _norm_formula(f) -> str:
    return "".join((f or "").split())


def neighbourhood_stability(rows_by_formula, row) -> dict:
    """Sharpe of the alpha's TRUE one-setting neighbours (D3).

    Round 1 (S2): the first version compared an alpha with its whole hypothesis group -- every leg, every
    window -- which measures the hypothesis, not the alpha's sensitivity to its own settings. A true
    neighbour has the SAME formula and region/delay/universe and differs in exactly ONE of decay,
    neutralisation, truncation. Fewer than two such neighbours is UNMEASURED, never a pass and never a
    fail. MECHANISM linking settings-fragility to OS failure: UNKNOWN.
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
    if len(peers) < 2 or not isinstance(own, (int, float)) or own == 0:
        return {"n": len(peers), "verdict": "unmeasured", "retained": None}
    retained = statistics.median(peers) / own
    return {"n": len(peers), "median_neighbour_sharpe": round(statistics.median(peers), 3),
            "retained": round(retained, 3), "verdict": "stable" if retained >= 0.5 else "fragile"}


def curve_values(curve) -> list:
    """Cumulative PnL as an ordered list. Round 1 (F2): every cached curve is a {date: cumulative} dict,
    and the first version turned each into [] -- axis 1 read 'insufficient' for every alpha."""
    if isinstance(curve, dict):
        return [curve[k] for k in sorted(curve)]
    return list(curve or [])


def regime_stability(curve) -> dict:
    """Did each third of the alpha's own history make money? (D3). Thirds are chosen before looking,
    unlike a calendar regime split drawn after seeing the curve. Positivity is judged on the MEAN; a
    third with gains and no dispersion has an unbounded Sharpe, not a zero one."""
    vals = curve_values(curve)
    if len(vals) < 300:
        return {"n": len(vals), "verdict": "unmeasured", "thirds": None}
    rets = [b - a for a, b in zip(vals, vals[1:])]
    k = len(rets) // 3
    thirds, means = [], []
    for i in range(3):
        seg = rets[i * k:(i + 1) * k] if i < 2 else rets[2 * k:]
        mean = statistics.fmean(seg) if seg else 0.0
        sd = statistics.pstdev(seg) if len(seg) > 1 else 0.0
        means.append(mean)
        thirds.append(round(mean / sd * math.sqrt(252), 3) if sd else
                      (float("inf") if mean > 0 else (float("-inf") if mean < 0 else 0.0)))
    positive = sum(1 for m in means if m > 0)
    return {"n": len(rets), "thirds": thirds, "positive_thirds": positive,
            "verdict": "consistent" if positive == 3 else ("mixed" if positive == 2 else "one-regime")}


def _chk(row, name) -> dict:
    for c in row.get("checks") or []:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    return {}


def _corr_ok(row, c) -> bool:
    pl, sl = SUB.corr_lines(row)
    p, s = c.get("prod"), c.get("self")
    return isinstance(p, (int, float)) and isinstance(s, (int, float)) and p < pl and s < sl


def alpha_status(gates: dict) -> str:
    """proven (every gate measured and passed) / refuted (any gate failed) / unproven (none failed,
    some could not be measured). A gate value of None means UNMEASURED."""
    if any(v is False for v in gates.values()):
        return "refuted"
    return "proven" if all(v is True for v in gates.values()) else "unproven"


def axis1_product(graded_rows, scored, corr, curves=None, standard=None, all_rows=None) -> dict:
    """Is what this version SUBMITTED good, robust and trustworthy? (D3, D10)

    Gates per submitted alpha, each True / False / None (unmeasured): every binding platform check PASS;
    DSR ≥ 0.95; PBO pass; both correlation lines clear; true-neighbour stability; regime stability; and
    D10's eight hard gates of the hypothesis standard (round 1: they were missing).
    `standard` maps hypothesis id -> list of tripped gates ([] = admissible), or is None (unmeasured).
    `all_rows` is the pool neighbours are drawn from (the whole journal, not only this cohort).
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
        trips = (standard or {}).get(hyp) if standard is not None else None
        gates = {
            "all_binding_pass": all(_chk(r, n).get("result") == "PASS" for n in BINDING),
            "dsr_ge_095": (x["dsr"] >= 0.95) if isinstance(x.get("dsr"), (int, float)) else None,
            "pbo_pass": x.get("pbo_pass") if isinstance(x.get("pbo_pass"), bool) else None,
            "corr_under_lines": _corr_ok(r, c) if isinstance(c.get("prod"), (int, float)) else None,
            "neighbourhood_stable": None if nb["verdict"] == "unmeasured" else nb["verdict"] == "stable",
            "regime_not_one_sided": None if rg["verdict"] == "unmeasured" else rg["verdict"] != "one-regime",
            "hypothesis_standard_8of8": None if trips is None else not trips,
        }
        st = alpha_status(gates)
        statuses[st] += 1
        detail.append({"alpha": a, "status": st, "gates": gates, "neighbourhood": nb, "regime": rg,
                       "dsr": x.get("dsr"), "pbo": x.get("pbo"), "hypothesis": hyp})
    n = len(submitted)
    value = (statuses["proven"] + UNPROVEN_CREDIT * statuses["unproven"]) / n if n else 0.0
    measured = sum(1 for d in detail for v in d["gates"].values() if v is not None)
    total = sum(len(d["gates"]) for d in detail)
    return {"cohort": "alphas this version submitted", "n": n, "status_counts": dict(statuses),
            "value": round(value, 4), "floor": FLOOR["axis1_product"],
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

# ------------------------------------------------------------ axis 2: is the throughput real
def quota_day_of_row(r):
    """ET quota day of a journal row, from its platform timestamp; None when absent or unparseable."""
    d = r.get("dateCreated")
    if not d:
        return None
    try:
        return datetime.datetime.fromisoformat(str(d).replace("Z", "+00:00")).astimezone(ET).date().isoformat()
    except ValueError:
        return None


def axis2_throughput(graded_rows, submissions, days, clean_alphas, prev_rate=None, posts_in_window=None) -> dict:
    """Four a day? At what cost? Sustainable or luck? (D6, D7)

    Unit (round 1, F3): CLEAN submissions per whole ET quota day -- the floor's own unit. Clean = the
    alpha was not refuted by axis 1 (a submitted alpha that fails a robustness gate does not count as
    throughput; round 1 found junk scoring above nothing). Sustainable needs all three independent
    pieces of evidence: the Poisson interval excludes zero, the clean submissions span ≥ 2 mechanisms,
    and the previous window of the same length also produced a clean submission.
    """
    n = len(graded_rows)
    clean = [s for s in submissions if s.get("alpha") in clean_alphas]
    k = len(clean)
    rate = k / days if days else 0.0
    lo, hi = poisson_interval(k, days)
    fam = structural_families(graded_rows)
    mechanisms = len({s.get("mechanism_key") for s in clean if s.get("mechanism_key")})
    ev = {"interval_excludes_zero": lo > 0, "two_or_more_mechanisms": mechanisms >= 2,
          "held_in_previous_window": prev_rate is not None and prev_rate > 0}
    return {"quota_days": days, "scored_alphas": n,
            "submissions_of_alphas_this_version_produced": len(submissions),
            "clean_submissions": k,
            "posts_this_version_made": len(posts_in_window or []),
            "clean_per_quota_day": round(rate, 3),
            "poisson_95_per_day": [round(lo, 3), round(hi, 3) if hi != float("inf") else None],
            "scored_per_clean_submission": round(n / k) if k else None,
            "scored_per_quota_day": round(n / days, 1) if days else None,
            "qualified_families": fam.get("families"),
            "scored_per_family": round(n / fam["families"]) if fam.get("families") else None,
            "distinct_mechanisms": mechanisms,
            "value": round(rate, 3), "floor": FLOOR["axis2_throughput"],
            "floor_met": days > 0 and rate >= FLOOR["axis2_throughput"],
            "sustainable": all(ev.values()), "sustainability_evidence": ev,
            "caveat": "At ~0.5 submissions per quota day, one day returns 0 about 61 % of the time; the "
                      "interval, not the count, is what a single window can support."}


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


def dora_checks(d: dict) -> list:
    """DORA keys as axis-3 checks when measured (round 1: DORA was reported but never in the value)."""
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


def axis3_gearing(dora=None, drill=None, root=ROOT, run_drill=True) -> dict:
    """Architecture fitness + the branch drill + DORA (D8). Every check that could be MEASURED counts
    equally; one that could not (the drill without data, DORA with < 2 deploys) is reported, not scored."""
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
    d = dora if dora is not None else _dora_from_ledger(root)
    ffs = ffs + dora_checks(d)
    held = sum(1 for _, ok, _ in ffs if ok)
    value = held / len(ffs) if ffs else 0.0
    return {"fitness_functions": [{"name": n, "ok": ok, "evidence": e} for n, ok, e in ffs],
            "held": held, "of": len(ffs), "dora": d,
            "branch_drill": drill or {"status": "not run"},
            "value": round(value, 3), "floor": FLOOR["axis3_gearing"],
            "floor_met": value >= FLOOR["axis3_gearing"]}


# ------------------------------------------------------------------------------ the scorecard (D2)
def scorecard(axes: dict) -> dict:
    """Non-compensatory verdict; monotone, non-saturating composite that only RANKS."""
    unmet = [k for k in WEIGHT if k in axes and not axes[k].get("floor_met")]
    comp = sum(WEIGHT[k] * min((axes[k].get("value") or 0) / FLOOR[k], 2.0) for k in WEIGHT if k in axes) / 2
    return {"verdict": "PASS" if not unmet else "FAIL", "floors_unmet": unmet,
            "composite_0_100": round(comp * 100, 1),
            "composite_means": "ranking only: meeting a floor = half that axis's weight, twice the floor = all of it; "
                               "a FAIL never becomes a PASS through a high composite",
            "axes": axes}


# ------------------------------------------------------------------------- the version on the stand
def whole_days(first: str, last_exclusive: str) -> list:
    d0 = datetime.date.fromisoformat(first)
    d1 = datetime.date.fromisoformat(last_exclusive)
    return [(d0 + datetime.timedelta(days=i)).isoformat() for i in range((d1 - d0).days)]


def current_quota_day(now=None) -> str:
    return SUB.quota_day(now if now is not None else __import__("time").time())


def build_from(rows, scored, corr, history, curves, standard, since=None, until=None, version=None,
               now=None, axis3=None) -> dict:
    """PURE: the scorecard from data already in memory. `rows` = one row per alpha id.

    Window (round 1, S5): whole ET quota days. The current, unfinished quota day is never in the rate --
    a one-minute window used to 'meet' 4 per day. With `version`, the cohort is the rows stamped with it;
    a version no row carries is an error, not 'all history'.
    """
    today = current_quota_day(now)
    scored_rows = [r for r in rows if r.get("status") in SCORED_STATUS and r.get("checks")]
    if version:
        cohort = [r for r in scored_rows if (r.get("meta") or {}).get("pipeline_version") == version]
        if not cohort:
            raise ValueError("no scored row carries pipeline_version %r" % version)
        how = "meta.pipeline_version (strong)"
    else:
        cohort, how = scored_rows, "ET quota-day window (weak: rows are attributed by date, not by version)"
    by_day = collections.defaultdict(list)
    for r in cohort:
        q = quota_day_of_row(r)
        if q:
            by_day[q].append(r)
    first = since or (min(by_day) if by_day else today)
    last = min(until or today, today)                    # never the unfinished current day
    days = whole_days(first, last) if first < last else []
    graded = [r for d in days for r in by_day.get(d, [])]

    accepted = [h for h in history if h.get("http") in (200, 201)]
    posted = {h["alpha"] for h in accepted}
    for r in graded:
        r["_submitted"] = r["alpha"] in posted
    ids = {r["alpha"] for r in graded}
    subs = [dict(h, mechanism_key=h.get("mechanism_key") or ((next((r for r in graded if r["alpha"] == h["alpha"]), {})
                                                              .get("meta") or {}).get("mechanism_key")))
            for h in accepted if h["alpha"] in ids]
    posts_in_window = [h for h in accepted if SUB.quota_day(h.get("posted_at") or 0) in set(days)]

    a1 = axis1_product(graded, scored, corr, curves, standard=standard, all_rows=scored_rows)
    clean = {d["alpha"] for d in a1["detail"] if d["status"] != "refuted"}
    prev_rate = None
    if days:
        prev_days = whole_days((datetime.date.fromisoformat(days[0]) - datetime.timedelta(days=len(days))).isoformat(), days[0])
        prev_rows = [r for d in prev_days for r in by_day.get(d, [])]
        prev_ids = {r["alpha"] for r in prev_rows}
        if prev_rows:
            prev_clean = [h for h in accepted if h["alpha"] in prev_ids]
            prev_rate = len(prev_clean) / len(prev_days)
    a2 = axis2_throughput(graded, subs, len(days), clean, prev_rate=prev_rate, posts_in_window=posts_in_window)
    axes = {"axis1_product": a1, "axis2_throughput": a2}
    if axis3 is not None:
        axes["axis3_gearing"] = axis3
    card = scorecard(axes)
    card["window"] = {"since": days[0] if days else None, "until_exclusive": last, "quota_days": len(days),
                      "version": version, "excluded_unfinished_day": today}
    card["version_attribution"] = how
    return card


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
    that is not a composite is simply absent (its gate reads UNMEASURED)."""
    try:
        from forge import hypotheses as H, standard as ST
        lib = H.load_library(root / "forge/hypotheses")
        return {c.id: ST.hard_gates(c) for c in H.load_composites(root / "forge/composites", lib)}
    except Exception:  # noqa: BLE001 -- the gate is then unmeasured, never passed
        return {}


def build(journal=None, since=None, until=None, version=None, curves_dir=None, run_drill=True) -> dict:
    """The scorecard from the files on disk (the only impure part)."""
    latest = {}
    for r in HV.read_jsonl(journal or HV.JOURNAL):
        if r.get("alpha"):
            latest[r["alpha"]] = r
    from forge import probe as P
    history = SUB.posted_history()
    posted = {h["alpha"] for h in history if h.get("http") in (200, 201)}
    card = build_from(list(latest.values()), HV.load_scored(), P.load_corr(), history,
                      load_curves(posted, curves_dir), load_standard(), since=since, until=until,
                      version=version, axis3=axis3_gearing(run_drill=run_drill))
    tagged = sum(1 for r in latest.values() if (r.get("meta") or {}).get("pipeline_version"))
    card["gaps"] = [g for g in (
        None if tagged else "No journal row carries meta.pipeline_version yet (the stamping runner is not deployed); "
                            "attribution is by date and the post-deploy comparison has no cohorts.",
        None if card["axes"]["axis3_gearing"]["dora"].get("status") == "measured" else
        "DORA is unmeasured: fewer than two recorded deploys.",
        "Axis 1's regime gate needs each submitted alpha's PnL curve; a curve absent from state/pnl_curves "
        "reads UNMEASURED (the submitted alphas' curves live on the VPS).",
    ) if g]
    return card


def compare(rows, history, curves, standard, scored, corr, version_a, version_b) -> dict:
    """Post-deploy: did version B produce clean submissions faster than version A? (Draw 2)

    Each cohort is the rows its version stamped. The comparison uses the SAME number of whole ET quota
    days for both -- each version's first d days, d the smaller count -- so a version is never judged on
    more exposure than the other. The verdict is 'better'/'worse' only when the two Poisson intervals do
    not overlap; otherwise 'indistinguishable', which at this desk's rate is the usual honest answer.
    """
    res = {}
    for v in (version_a, version_b):
        vrows = [r for r in rows if (r.get("meta") or {}).get("pipeline_version") == v
                 and r.get("status") in SCORED_STATUS and r.get("checks")]
        days = sorted({quota_day_of_row(r) for r in vrows if quota_day_of_row(r)} - {current_quota_day()})
        res[v] = {"rows": vrows, "days": days}
    d = min(len(res[version_a]["days"]), len(res[version_b]["days"]))
    out = {"quota_days_each": d, "versions": {}}
    if d == 0:
        out["verdict"] = "no-data"
        return out
    for v in (version_a, version_b):
        use = set(res[v]["days"][:d])
        card = build_from([r for r in res[v]["rows"] if quota_day_of_row(r) in use], scored, corr, history,
                          curves, standard, since=min(use),
                          until=(datetime.date.fromisoformat(max(use)) + datetime.timedelta(days=1)).isoformat())
        a2 = card["axes"]["axis2_throughput"]
        out["versions"][v] = {"clean_per_quota_day": a2["clean_per_quota_day"],
                              "poisson_95_per_day": a2["poisson_95_per_day"], "clean_submissions": a2["clean_submissions"]}
    ia, ib = out["versions"][version_a]["poisson_95_per_day"], out["versions"][version_b]["poisson_95_per_day"]
    hi_a = ia[1] if ia[1] is not None else float("inf")
    hi_b = ib[1] if ib[1] is not None else float("inf")
    out["verdict"] = ("better" if ib[0] > hi_a else "worse" if hi_b < ia[0] else "indistinguishable")
    return out


def render(card: dict) -> str:
    a = card["axes"]
    w = card["window"]
    L = ["PIPELINE SCORECARD  %s" % (w.get("version") or "(date window)"),
         "  %d whole ET quota day(s) from %s (the unfinished day %s is excluded)   attribution: %s"
         % (w["quota_days"], w["since"], w["excluded_unfinished_day"], card["version_attribution"]),
         "", "  VERDICT  %s%s" % (card["verdict"], ("  (floors unmet: %s)" % ", ".join(card["floors_unmet"])) if card["floors_unmet"] else ""),
         "  composite %.1f / 100   -- %s" % (card["composite_0_100"], card["composite_means"]), ""]
    p = a["axis1_product"]
    L += ["  AXIS 1  PRODUCT   %s   value %.3f   gate coverage %s" % ("FLOOR MET" if p["floor_met"] else "floor unmet",
                                                                        p["value"], p["gate_coverage"]),
          "    submitted by this version: %d  (%s)" % (p["n"], p["verdict"])]
    for d in p["detail"][:6]:
        bad = [k for k, v in d["gates"].items() if v is False]
        unk = [k for k, v in d["gates"].items() if v is None]
        L.append("      %-10s %-8s%s%s" % (d["alpha"], d["status"], (" FAILS: " + ", ".join(bad)) if bad else "",
                                           (" unmeasured: " + ", ".join(unk)) if unk else ""))
    t = a["axis2_throughput"]
    L += ["", "  AXIS 2  THROUGHPUT  %s" % ("FLOOR MET" if t["floor_met"] else "floor unmet"),
          "    %d clean submission(s) over %d quota day(s) = %.3f per day   (floor %.1f)   95 %% %s"
          % (t["clean_submissions"], t["quota_days"], t["clean_per_quota_day"], t["floor"], t["poisson_95_per_day"]),
          "    scored alphas %d (%s per day) | per clean submission %s | qualified families %s"
          % (t["scored_alphas"], t["scored_per_quota_day"], t["scored_per_clean_submission"], t["qualified_families"]),
          "    POSTs the submitter made in the window: %d" % t["posts_this_version_made"],
          "    sustainable: %s  %s" % (t["sustainable"], t["sustainability_evidence"])]
    if "axis3_gearing" in a:
        g = a["axis3_gearing"]
        L += ["", "  AXIS 3  GEARING  %s   %d of %d measured checks hold" % ("FLOOR MET" if g["floor_met"] else "floor unmet", g["held"], g["of"])]
        L += ["      [%s] %s" % ("ok" if f["ok"] else "NO", f["name"]) for f in g["fitness_functions"]]
        L.append("    DORA: %s" % g["dora"].get("status"))
    if card.get("gaps"):
        L += ["", "  GAPS THIS SCORECARD DOES NOT HIDE:"] + ["    - %s" % x for x in card["gaps"]]
    return "\n".join(L)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default="", help="first ET quota day, YYYY-MM-DD")
    ap.add_argument("--until", default="", help="ET quota day to stop BEFORE, YYYY-MM-DD")
    ap.add_argument("--version", default="", help="grade the rows stamped with this pipeline version")
    ap.add_argument("--no-drill", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    card = build(since=a.since or None, until=a.until or None, version=a.version or None, run_drill=not a.no_drill)
    print(json.dumps(card, indent=1, default=str) if a.json else render(card))
    return 0 if card["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
