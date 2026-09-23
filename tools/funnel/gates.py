#!/usr/bin/env python3
"""gates.py — THE definition of a passing simulation. One place, derived from platform data.

Before this module the rule lived as a copied literal in eight files that disagreed, and the
disagreement was not academic: scored over `state/resim_results.jsonl`, the scratchpad runners'
rule reported 32 / 25 / 6 / 7 / 22 zero-fails for iterations 42-46 while a presence-checking rule
reported 0 for every one of them.

Both were wrong, in opposite directions:

* The runner rule counted a hard gate that the platform never returned as PASSED. That is the
  IS_LADDER_SHARPE mistake in another costume.
* The presence-checking rule counted an absent gate as NOT MEASURED and therefore not passed —
  which declares most USA TOP3000 alphas unpassable, even though three alphas from those very
  batches (zqRN8LGE, KPE7nLX8, e7xG3nrM) were submitted and are ACTIVE.

The resolution is that gate applicability is a property of the SEGMENT, not a constant. Measured
presence of LOW_2Y_SHARPE: GLB/TOPDIV3000 180/180, CHN/TOP2000U ~99%, USA/TOP1000 2864/4818,
USA/TOP3000 1073/4034, USA/TOP2000 0/96. So the required set is learned from what the platform
actually returns for that (region, universe, delay), and a gate is only "missing" if it is normally
present for that segment.
"""
from __future__ import annotations
import json
import os, pathlib, time
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RESULTS = ROOT / "state/resim_results.jsonl"

# Gates that BLOCK submission when they FAIL. Everything else the platform returns is a WARNING,
# a tag, or is evaluated at submit time (SELF_CORRELATION / PROD_CORRELATION / DATA_DIVERSITY /
# REGULAR_SUBMISSION are always PENDING pre-submit and can never be scored here).
BLOCKING = {
    "LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
    "LOW_SUB_UNIVERSE_SHARPE", "CONCENTRATED_WEIGHT", "LOW_2Y_SHARPE", "LOW_RETURNS",
    # GLB-only: each demands sharpe >= 1 in that region separately
    "LOW_GLB_AMER_SHARPE", "LOW_GLB_EMEA_SHARPE", "LOW_GLB_APAC_SHARPE",
    # Region-specific, added 2026-08-12. Each is present on 100% of the rows of the segments that
    # have it -- never intermittent -- across 3,882 occurrences in 2,454 rows over ASI TOP500 d1,
    # CHN TOP2000U d0/d1, IND TOP500 d1 and JPN TOP1600 d0/d1. Outside BLOCKING, `expected_gates`
    # could never learn them as required, so an ERROR or PENDING on one read as satisfied.
    #
    # VERDICT CHANGE FROM ADDING THEM: ZERO. 1,835 gems before and after, derived twice -- a full
    # re-score of all 78,319 journal rows, and an enumeration of the four channels through which
    # `zero_fail` can differ (undecided-now-blocks 0, WARNING-breach 0, newly-required-but-absent 0,
    # fail-closed-guard-loosens 0). The closest row is four gates away from being a gem. USA blast
    # radius is zero by four measures: 0 of 53,526 USA journal rows, 0 of 9,984 platform alphas.
    # Applied now, before the first experiment freezes this file, precisely because it costs nothing
    # today -- which is exactly how a latent hole ships.
    "LOW_ROBUST_UNIVERSE_SHARPE", "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO",
    "LOW_ROBUST_UNIVERSE_RETURNS", "LOW_ASI_JPN_SHARPE",
    "LOW_INVESTABILITY_CONSTRAINED_SHARPE",
}
# Present in results but never blocking: WARNING-class, tag-class, or region-inapplicable.
# HT_LIQUID_TOPDIV3000_SHARPE is here because across 180 GLB rows it appeared on 15 and was
# WARNING on all 15; IS_LADDER_SHARPE because it does not exist on GLB at all.
_PRESENCE_MIN = 0.80          # a gate counts as "expected" for a segment above this rate

# Gates where a value BELOW the limit is the failure; the rest fail above it.
_LOWER_IS_FAIL = {"LOW_SHARPE", "LOW_FITNESS", "LOW_2Y_SHARPE", "LOW_SUB_UNIVERSE_SHARPE",
                  "LOW_TURNOVER", "LOW_RETURNS",
                  "LOW_GLB_AMER_SHARPE", "LOW_GLB_EMEA_SHARPE", "LOW_GLB_APAC_SHARPE",
                  # The same five names as the BLOCKING addition above, and BOTH lists are required.
                  # They are all LOW_* gates, so adding them to BLOCKING alone would leave the
                  # WARNING branch testing `value > limit` — backwards, marking a breach as clean and
                  # a clean value as a breach. Zero exposure today because the platform has never
                  # returned WARNING on any of the five, which is precisely why the wrong version
                  # would have shipped unnoticed.
                  "LOW_ROBUST_UNIVERSE_SHARPE", "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO",
                  "LOW_ROBUST_UNIVERSE_RETURNS", "LOW_ASI_JPN_SHARPE",
                  "LOW_INVESTABILITY_CONSTRAINED_SHARPE"}
# The platform returns WARNING (not FAIL) on sharpe/fitness/2Y when IS_LADDER_SHARPE can waive
# them -- see tools/funnel/submittable.py, ladder ground truth 2026-07-23. Below the waiver bar a
# WARNING whose value is on the wrong side of its own limit is a genuine block.
_LADDER_WAIVER = 2.02

_cache = {}


_OID_SEG = None

# Every filename pattern that can define a batch. ONE source, because the two places that walk these
# files must never disagree: the index builder and the change detector below.
#
# `pool_*.json` was added 2026-08-12 after measuring what its absence cost. The feeder writes 205
# pool files carrying old_id and a full settings dict, and the glob matched only *targets*.json, so
# 6,357 rows of the journal resolved to "<unknown segment>". An unknown segment can never pass, so
# those rows sat in the denominator and could never reach the numerator: 97 alphas that are zero-fail
# by this module's own definition had been simulated, adjudicated as unknown, and never staged.
# Measured twice, independently, both giving +97 gems / +6,357 adjudicated.
#
# This is the same defect one variant later. The 2026-07-30 fix generalised the DIRECTORY (state/**
# instead of state/funnel/) and left the filename alone; the scar is in _segment's docstring below.
# Adding a pattern here is now the whole change, which is why the patterns live in one tuple.
_BATCH_GLOBS = ("state/**/*targets*.json", "state/**/pool_*.json")


def _batch_files():
    seen = set()
    for pat in _BATCH_GLOBS:
        for f in ROOT.glob(pat):
            if f not in seen:
                seen.add(f)
                yield f


def _oid_segment_index():
    """old_id -> (region, universe, delay), read from the TARGETS files.

    The journal does not carry settings — verified: 0 of 21,809 rows with checks have a `settings`
    key. Defaulting to ('USA','TOP3000',1) therefore collapsed every segment into one bucket and
    scored GLB rows against gates learned from USA. The segment has to come from the batch file
    that defined the row."""
    global _OID_SEG
    if _OID_SEG is None:
        _OID_SEG = {}
        # Walk state/** , not just state/funnel/. Batches written anywhere else (tools/autoloop
        # writes to state/autoloop/) resolved to "<unknown segment>", and an unknown segment can
        # never pass -- so a whole run could score 0 zero-fail with nothing actually wrong with it.
        for f in _batch_files():
            try:
                for r in json.load(open(f)):
                    st = r.get("settings") or {}
                    _OID_SEG[r.get("old_id")] = (st.get("region", "USA"),
                                                 st.get("universe", "TOP3000"),
                                                 st.get("delay", 1))
            except Exception:
                pass
    return _OID_SEG


_TARGETS_SIG = None
_TARGETS_CHECKED_AT = 0.0
_RECHECK_EVERY_S = 20.0


def _targets_changed():
    """Has the set of target files (name + mtime) changed since the index was built?

    Throttled by wall clock. The signature itself needs a stat of every targets file, so calling it
    on every index miss made scoring the whole journal (~22k rows, most of them from batches whose
    files are long gone) do millions of stats -- a 2-minute scoring run instead of seconds. A new
    batch file appears at most once per round, so re-checking every 20s catches it in time while
    keeping the miss path free."""
    global _TARGETS_SIG, _TARGETS_CHECKED_AT
    now = time.monotonic()
    if _TARGETS_SIG is not None and now - _TARGETS_CHECKED_AT < _RECHECK_EVERY_S:
        return False
    _TARGETS_CHECKED_AT = now
    sig = frozenset((str(f), f.stat().st_mtime_ns) for f in _batch_files())
    if sig == _TARGETS_SIG:
        return False
    _TARGETS_SIG = sig
    return True


def _segment(row):
    st = row.get("settings")
    if st:
        return (st.get("region", "USA"), st.get("universe", "TOP3000"), st.get("delay", 1))
    oid = row.get("old_id")
    seg = _oid_segment_index().get(oid)
    if seg is None and oid and _targets_changed():
        # The index is built once per process, but a long-running driver writes a NEW batch file
        # every round -- so every round after the one that first populated the cache resolved to
        # "<unknown segment>" and could never pass. Round 2 of the 2026-07-30 run discarded 4
        # genuine zero-fails this way. Rebuild on a miss -- but ONLY when the set of target files
        # on disk has actually changed, otherwise every genuinely-unknown old_id triggers a full
        # rescan and scoring a batch goes quadratic.
        global _OID_SEG
        _OID_SEG = None
        seg = _oid_segment_index().get(oid)
    return seg or (None, None, None)   # UNKNOWN, never a silent USA default


def expected_gates(segment, results_path=None):
    """Which BLOCKING gates does the platform actually return for this segment?

    Learned from the journal rather than declared, so a gate the platform does not run for a
    segment is neither silently passed nor counted as an unmeasured failure.

    THE CACHE IS KEYED ON THE JOURNAL'S STATE, not on the segment alone. It used to key on the
    segment and ignore `results_path` entirely, and it was never invalidated, so within one process
    the answer was frozen at whatever the file said the first time anyone asked. Two consequences,
    both demonstrated 2026-08-12:

      * A run that touches a VIRGIN segment caches `(set(), 0)` — no gate evidence — and keeps
        returning it however many rows land afterwards. The same row scored gem before a restart and
        non-gem after, with nothing but the restart between them.
      * A long run is exactly where this bites. The first experiment spends ~3,000 simulations in one
        process over several hours, appending to this very file the whole time.

    Cheap because `_PRESENCE_MIN` is a ratio over the file: the signature is one `stat`, and the
    expensive walk only re-runs when the file actually grew. Same shape as `_targets_changed` below,
    for the same reason."""
    # LATE-BOUND, not `results_path=RESULTS` in the signature. A default argument is evaluated once
    # at definition time, so the old form froze the module's journal path at import and rebinding
    # `gates.RESULTS` — the obvious way to point this module at a test journal — silently did
    # nothing. Two test fixtures worked around it by priming the cache under one path and reading it
    # back under another, which only worked because the cache key ignored the path: they depended on
    # the defect fixed above. Binding here makes `gates.RESULTS = other` mean what it looks like.
    results_path = results_path if results_path is not None else RESULTS
    try:
        st = os.stat(results_path)
        sig = (st.st_size, st.st_mtime_ns)
    except OSError:
        sig = None
    key = (segment, str(results_path), sig)
    if key in _cache:
        return _cache[key]
    seen, total = defaultdict(int), 0
    for line in open(results_path):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if not d.get("checks"):
            continue
        if _segment(d) != segment:
            continue
        # A row whose checks are bare gate-NAME strings can raise the denominator but can never
        # raise the numerator (the loop below only counts dicts), so 614 legacy rows diluted every
        # segment they touched. CHN/TOP2000U/0 measured 16 dict rows against 28 total = 0.571 max
        # attainable presence, below _PRESENCE_MIN, so expected_gates returned an EMPTY set and
        # zero_fail then certified rows with no gate evidence at all. Denominator must match the
        # numerator.
        if not any(isinstance(c, dict) for c in d["checks"]):
            continue
        total += 1
        for c in d["checks"]:
            if isinstance(c, dict) and c.get("name") in BLOCKING:
                seen[c["name"]] += 1
    out = {g for g, n in seen.items() if total and n / total >= _PRESENCE_MIN}
    _cache[key] = (out, total)
    return out, total


def hard_fails(checks):
    """Every check the platform marked FAIL — the ANY-FAIL rule, without needing a segment.

    zero_fail() is the full verdict and needs the row's segment to know which gates SHOULD be
    present. Callers that only have a check list (the platform's /users/self/alphas listing, an
    ad-hoc scan) need the same rule in a form they can use, and writing it by hand goes wrong the
    same way every time: `[n for n in BLOCKING if ...]` walks the allowlist and therefore misses
    IS_LADDER_SHARPE, which is not in BLOCKING but is a hard gate — 0 of 5,775 ladder-FAIL rows
    were ever zero-fail. Two tools in this repo had that bug and undercounted by 7%.
    """
    return [c.get("name") for c in (checks or [])
            if isinstance(c, dict) and c.get("result") == "FAIL"]


def zero_fail(row, segment=None):
    """(passed, failed_gates, missing_gates) for one journal row.

    passed  -> no BLOCKING gate FAILED, and no gate that this segment normally returns is absent.
    missing -> gates the segment normally returns but this row does not carry: a data problem,
               reported separately so it can never masquerade as a pass OR as a failure.
    """
    checks = row.get("checks") or []
    if not checks:
        return False, [], ["<no checks>"]
    seg = segment or _segment(row)
    if seg == (None, None, None):
        return False, [], ["<unknown segment: old_id not in any targets file>"]
    exp, _ = expected_gates(seg)
    present = {c["name"] for c in checks if isinstance(c, dict)}
    ladder = next((c.get("value") for c in checks
                   if isinstance(c, dict) and c.get("name") == "IS_LADDER_SHARPE"), None)
    waived = isinstance(ladder, (int, float)) and ladder >= _LADDER_WAIVER
    failed = []
    for c in checks:
        if not isinstance(c, dict):
            continue
        name, res, v, lim = c.get("name"), c.get("result"), c.get("value"), c.get("limit")
        # ANY hard FAIL blocks, whether or not the name is in BLOCKING. Skipping unlisted names was
        # the allowlist trap: iter49's pwKZl6Zg / O0xVZpVd / Vk35PY2J each carried
        # `IS_LADDER_SHARPE FAIL value=1.4 limit=1.58` in their own journal row, scored (True, []),
        # and were submitted -- three 403s, and under G6 each alpha gets one POST ever, so all three
        # are permanently unsubmittable. The platform has already decided on a FAIL; there is
        # nothing left to interpret, and an unanticipated gate name must not read as a pass.
        # (Regression: all 5 LIVE alphas carry zero FAILs, so this rejects none of them.)
        if res == "FAIL":
            failed.append(name)
            continue
        if name not in BLOCKING:
            continue
        # A WARNING is NOT automatically a pass. 2,363 journal rows carry WARNING on a hard gate
        # whose value sits on the wrong side of its own limit -- scoring those as passes made
        # iter38 read 90/90 zero-fail at a median fitness of 0.81 against a hard bar of 1.0.
        if res == "WARNING" and isinstance(v, (int, float)) and isinstance(lim, (int, float)):
            breached = v < lim if name in _LOWER_IS_FAIL else v > lim
            if breached and not waived:
                failed.append(name + "(WARN)")
        elif res not in ("PASS", "WARNING"):
            # ERROR / PENDING / a missing result key are NOT verdicts -- the gate was never
            # decided. Falling through counted them as satisfied, which is the same
            # unanticipated-value-reads-as-success shape as the IS_LADDER_SHARPE allowlist hole.
            # These are real: the journal carries LOW_FITNESS ERROR 125x and
            # LOW_SUB_UNIVERSE_SHARPE ERROR 144x. An undecided hard gate must read as UNKNOWN.
            failed.append(f"{name}({res})")
    missing = sorted(exp - present)
    # FAIL CLOSED ON NO EVIDENCE. `exp` is learned from the journal, so a segment with too few
    # rows -- or one never seen at all -- yields an empty required set, and `missing` is then
    # empty for a row that adjudicated NOTHING. Measured 2026-08-09: 16 live journal rows scored
    # (True, [], []) with no blocking gate decided, including hx1_revconf_rk at sharpe -0.38 /
    # fitness -0.13. That verdict feeds driver.py's passers -> measure -> submit path, so it is a
    # false positive pointing at an irreversible action.
    #
    # A pass needs positive evidence, which is the rule gate_lib.BASE_REQUIRED already applies.
    if not (present & BLOCKING):
        return False, failed, ["<no blocking gate adjudicated>"]
    return (not failed and not missing), failed, missing
