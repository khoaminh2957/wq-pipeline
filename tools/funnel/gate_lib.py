"""gate_lib.py — Python conversion of ALPHA_PIPELINE.md C7 gate logic + the S7
QUALITY-SIGNAL half only.

SCOPE (defect #7, narrowed): this tool ports (a) the C7 zero-fail gate verdict
and (b) the S7 QUALITY signals emitted by `cycle_metrics` (n_gated, n_good,
gate_pass_rate, robust_univ_pass_rate, spread, dd_score, robustness). The S7
RESILIENCE / failure-recovery + budget-ledger accounting lives in the sibling
`resilience_lib.py` (S10-7/9 port); per the S2.7 no-cap ruling (Khoa
2026-07-16) the budget ledger is observational only. See ALPHA_PIPELINE.md
S6/S7/S8 (the region×delay bar table and the cycle-metrics contract).

Rules preserved verbatim from the md:

  * Gate = ZERO-FAIL over WHATEVER checks the platform returns (never a fixed
    name list). Block ONLY on result=='FAIL'; WARNING is non-blocking; PENDING
    is evaluated at submit time (treated non-blocking here).
  * The `checks` field may be full rows [{name,result,value,limit},...] OR a
    PASS-name list ["LOW_SHARPE",...] OR the fetch_gates jsonl dict-form
    {name: result} -> handle ALL THREE (the dict-form is what the live
    funnel_run path feeds — same defect class as S10-26). A bare name list
    means those checks were RETURNED as PASS, so zero-fail holds over them;
    dict-form is normalized to full rows so FAIL/WARNING keep blocking/warning.
  * Short-form artifacts carry a top-level `fails` name-list instead of checks.
    A bare `fail` COUNT with no checks also blocks: fail>0 => zero_fail False
    (S10-25 fix). zero_fail requires POSITIVE evidence: a `fails` key or
    fail==0; a row with only a `pass` count is NOT promoted (v7.1 fix).
  * `good` (S7): zero FAIL rows  OR  (fitness>=1.0 AND full-row checks present
    AND no 5-core check FAILs).  CORE = {LOW_FITNESS, LOW_TURNOVER,
    HIGH_TURNOVER, CONCENTRATED_WEIGHT, LOW_SUB_UNIVERSE_SHARPE}.
  * robustness = renormalized 0.35*gpr + 0.25*rup + 0.20*spread + 0.20*dd_score
    over the non-null components; 0.0 when goods is empty but something gated.
"""
import re
import statistics as st

# C7 / S7 robust-family regex (ALPHA_PIPELINE.md :246 and :426 — byte-identical)
ROB = re.compile(r'LOW_ROBUST_UNIVERSE_|LOW_SUB_UNIVERSE_SHARPE|'
                 r'LOW_INVESTABILITY_CONSTRAINED_SHARPE|IS_LADDER_SHARPE|'
                 r'LOW_2Y_SHARPE|HT_LIQUID_TOP500_TOP200_SHARPE_RATIO')

# S7 :427 — the 5 "core" checks whose FAIL blocks the fitness>=1.0 good-path
CORE = {'LOW_FITNESS', 'LOW_TURNOVER', 'HIGH_TURNOVER',
        'CONCENTRATED_WEIGHT', 'LOW_SUB_UNIVERSE_SHARPE'}

# Checks that must be PRESENT before "no FAIL" means anything.
#
# `zero_fail = len(fails) == 0` reads a MISSING gate as a passing gate. Measured 2026-08-08 over
# 58,383 evaluable rows: 2,496 rows carry no FAIL, but only 1,474 of them actually reported the
# core set — so 1,022 rows, 41% of every zero-fail figure this project has quoted, passed by
# ABSENCE. The independent confirmation is the fitness distribution: the loose set medians 1.17
# against a LOW_FITNESS limit of 1.0, which is impossible for a set that truly cleared it; the
# strict set medians 1.46.
#
# THE SET IS PER-REGION, because the platform's check set is per-region.
#
# The first version of this required one global set including LOW_SUB_UNIVERSE_SHARPE, derived from
# a corpus that is 96% USA d1. Measured across fetched/alphas_all.jsonl (9,984 alphas), gates
# present in >=95% of a region's alphas:
#
#     USA d1  n=9646   CONCENTRATED_WEIGHT HIGH_TURNOVER LOW_FITNESS LOW_SHARPE LOW_TURNOVER
#                      LOW_SUB_UNIVERSE_SHARPE
#     USA d0  n= 338   CONCENTRATED_WEIGHT HIGH_TURNOVER LOW_FITNESS LOW_SHARPE LOW_TURNOVER
#
# LOW_SUB_UNIVERSE_SHARPE is a USA-d1 gate and is NOT reliably present one delay over — so a global
# requirement rejects sound USA d0 rows for lacking a gate their region does not run. The same
# already-known pattern holds elsewhere: LOW_ROBUST_UNIVERSE_SHARPE gates IND d1 and never appears
# in USA d1 at all.
#
# BASE is the intersection over every region measured, and every member is a quality gate. Regions
# with no measured evidence get BASE only: rejecting on a gate we have no reason to believe the
# region runs would repeat, in the other direction, the mistake this whole change exists to fix.
#
# MATCHES_COMPETITION/MATCHES_PYRAMID are >=95% present too and are deliberately excluded — they
# are membership labels, not quality gates, and they differ by fetch path (the platform artifact
# carries COMPETITION, the resim journal carries PYRAMID).
#
# IS_LADDER_SHARPE is also excluded despite being a hard gate: present on 69.6% of journal rows and
# only 40.6% of USA d1 ones, and presence is not monotone in payload size (92.1% of 5-check
# payloads carry it, 33.4% of 15-check ones do). Whether that is a platform applicability rule or a
# fetch artifact is MECHANISM: UNKNOWN, so requiring it would discard rows on a guess.
# `ladder_reported` is returned instead, for callers that need it.
BASE_REQUIRED = {'LOW_SHARPE', 'LOW_FITNESS', 'LOW_TURNOVER', 'HIGH_TURNOVER',
                 'CONCENTRATED_WEIGHT'}
REGION_EXTRA_REQUIRED = {
    ('USA', 1): {'LOW_SUB_UNIVERSE_SHARPE'},
}


def required_present(region, delay):
    """Gates that must be ADJUDICATED before 'no FAIL' can mean 'passed', for this region/delay."""
    try:
        key = (str(region).upper(), int(delay))
    except (TypeError, ValueError):
        return set(BASE_REQUIRED)                    # region unknown -> the conservative floor
    return BASE_REQUIRED | REGION_EXTRA_REQUIRED.get(key, set())

# region x delay LOW_SHARPE bars — GROUND TRUTH verified 2026-07-16
# (platform tightened severity 2026-07-16). Unknown cells -> None.
_LOW_SHARPE_BARS = {
    ('CHN', 0): 3.49,
    ('JPN', 0): 2.69,
    ('CHN', 1): 2.07,
    ('JPN', 1): 1.58,
    ('USA', 1): 1.58,
}


def region_delay_bar(region, delay):
    """LOW_SHARPE bar for a (region, delay) cell, or None if unknown."""
    if region is None or delay is None:
        return None
    try:
        delay = int(delay)
    except (TypeError, ValueError):
        return None
    return _LOW_SHARPE_BARS.get((str(region).upper(), delay))


def _extract_checks(obj):
    """Return the checks list from is.checks or a top-level checks key, else None.

    Normalizes the fetch_gates jsonl dict-form {name: result} to full rows
    [{'name': ..., 'result': ...}] so all downstream logic sees one shape.
    """
    isb = obj.get('is')
    checks = None
    if isinstance(isb, dict) and isb.get('checks') is not None:
        checks = isb['checks']
    elif obj.get('checks') is not None:
        checks = obj['checks']
    if isinstance(checks, dict):
        checks = [{'name': k, 'result': v} for k, v in checks.items()]
    return checks


def _region_delay(obj):
    s = obj.get('settings') or {}
    region = obj.get('region')
    if region is None:
        region = s.get('region')
    delay = obj.get('delay')
    if delay is None:
        delay = s.get('delay')
    return region, delay


def _sharpe(obj):
    if obj.get('sharpe') is not None:
        return obj.get('sharpe')
    isb = obj.get('is')
    if isinstance(isb, dict):
        return isb.get('sharpe')
    return None


def _checks_kind(checks):
    """'full' if list of dicts, 'names' if list of strings, None if empty/absent."""
    if not checks:
        return None
    return 'full' if isinstance(checks[0], dict) else 'names'


def gate_status(alpha_or_row):
    """C7 gate verdict for one alpha/artifact/resim row.

    Returns {zero_fail, n_pass, fails, warns, region_delay_bar, sharpe_margin}.
    Handles full check rows, a bare PASS-name list, and short-form `fails`.
    """
    obj = alpha_or_row
    checks = _extract_checks(obj)
    kind = _checks_kind(checks)
    region, delay = _region_delay(obj)

    missing_core = []
    ladder_reported = False
    need = required_present(region, delay)

    if kind == 'full':
        fails = [c['name'] for c in checks if c.get('result') == 'FAIL']
        warns = [c['name'] for c in checks if c.get('result') == 'WARNING']
        n_pass = sum(1 for c in checks if c.get('result') == 'PASS')
        # A gate that was never reported is NOT a gate that passed. See REQUIRED_PRESENT.
        reported = {c.get('name') for c in checks
                    if isinstance(c, dict) and c.get('result') in ('PASS', 'FAIL')}
        missing_core = sorted(need - reported)
        ladder_reported = 'IS_LADDER_SHARPE' in reported
        zero_fail = not fails and not missing_core
    elif kind == 'names':
        # bare list = names of checks the platform RETURNED as PASS. The same rule applies: a name
        # absent from the list was not adjudicated, so it cannot be counted as cleared.
        fails = []
        warns = []
        n_pass = len(checks)
        reported = set(checks)
        missing_core = sorted(need - reported)
        ladder_reported = 'IS_LADDER_SHARPE' in reported
        zero_fail = not missing_core
    else:
        # no checks returned -> fall back to a short-form `fails` name-list
        fails = list(obj.get('fails') or [])
        warns = []
        p = obj.get('pass')
        n_pass = p if p is not None else 0
        # S10-25 + v7.1 fix: zero_fail needs POSITIVE evidence of zero failure —
        # a `fails` name-list (possibly empty) or an explicit fail count of 0.
        # {'pass': 6, 'fail': 2} is a FAILING alpha; a bare {'pass': 6} with
        # NEITHER key is a degraded artifact and must NOT be promoted (v6.2 S7
        # scored it not-good; re-GET the full artifact per C7).
        f = obj.get('fail')
        if obj.get('fails') is not None:
            zero_fail = len(fails) == 0 and (f is None or f == 0)
        elif f is not None:
            zero_fail = (f == 0)
        else:
            zero_fail = False

    bar = region_delay_bar(region, delay)
    sharpe = _sharpe(obj)
    margin = (sharpe - bar) if (bar is not None and sharpe is not None) else None

    return {
        'zero_fail': zero_fail,
        'n_pass': n_pass,
        'fails': fails,
        'warns': warns,
        'missing_core': missing_core,      # required gates the payload never adjudicated
        'ladder_reported': ladder_reported,
        'region_delay_bar': bar,
        'sharpe_margin': margin,
    }


def _is_gated(obj):
    """True when the row carries ANY gate data (checks, fails, or a fail count)."""
    return (_extract_checks(obj) is not None
            or obj.get('fails') is not None
            or obj.get('fail') is not None
            or obj.get('pass') is not None)


def _robust_applicable(obj):
    """Robust-family names present in the returned check-set (full rows or name list)."""
    checks = _extract_checks(obj)
    kind = _checks_kind(checks)
    if kind == 'full':
        return [c['name'] for c in checks if ROB.search(c.get('name', ''))]
    if kind == 'names':
        return [n for n in checks if ROB.search(n)]
    return []


def _is_good(obj):
    """S7 :444 good-path — mirrors the md expression exactly."""
    if not _is_gated(obj):
        return False
    gs = gate_status(obj)
    checks = _extract_checks(obj)
    has_full = _checks_kind(checks) == 'full'
    fit = obj.get('fitness') or 0
    core_fail = has_full and any(
        c.get('name') in CORE and c.get('result') == 'FAIL' for c in checks)
    return gs['zero_fail'] or (fit >= 1.0 and has_full and not core_fail)


def cycle_metrics(rows, wall_min=None):
    """S7 cycle aggregation over completed alpha rows.

    Each row is a dict carrying gate data (checks/fails) plus optional metrics
    (fitness, sharpe, drawdown, region, delay, universe, class).
    Returns the S7 quality signals: n_good, good_per_min, robustness, etc.
    """
    gated = [r for r in rows if _is_gated(r)]
    goods = [r for r in gated if _is_good(r)]

    gpr = len(goods) / len(gated) if gated else None

    app = [r for r in gated if _robust_applicable(r)]
    rob_fail_n = sum(1 for r in app
                     if any(n in gate_status(r)['fails']
                            for n in _robust_applicable(r)))
    rup = (1 - rob_fail_n / len(app)) if app else None

    dds = [r.get('drawdown') for r in goods
           if r.get('drawdown') not in (None, 0.0)]
    dd_score = (1 - min(1, st.median(dds) / 0.3)) if dds else 0.0

    cells = {(r.get('region'), r.get('delay'), r.get('universe')) for r in goods}
    cls = {r.get('class') for r in goods if r.get('class')}
    sc = min(1, len(cells) / 4) if goods else 0.0
    skl = (min(1, len(cls) / 3) if cls else None) if goods else 0.0
    spread = sc if skl is None else 0.5 * sc + 0.5 * skl

    comp = [(0.35, gpr), (0.25, rup), (0.20, spread), (0.20, dd_score)]
    wsum = sum(w for w, v in comp if v is not None)
    robust = (sum(w * v for w, v in comp if v is not None) / wsum) if wsum else 0.0
    if not goods and gated:
        robust = 0.0

    good_per_min = (len(goods) / wall_min) if wall_min else None

    return {
        'n_gated': len(gated),
        'n_good': len(goods),
        'gate_pass_rate': gpr,
        'robust_univ_pass_rate': rup,
        'robust_univ_n_applicable': len(app),
        'spread_cells': len(cells),
        'spread_classes': len(cls) or None,
        'spread': spread,
        'dd_score': dd_score,
        'good_per_min': good_per_min,
        'robustness': robust,
    }
