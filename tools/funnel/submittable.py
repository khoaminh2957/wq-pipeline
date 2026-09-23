#!/usr/bin/env python3
"""submittable.py — v3 CORRECTED win-condition (2026-07-18).

v1/v2 crowned an alpha "zero-fail" when it had no hard FAIL among sim WARNINGS — but that definition
(a) counts LOW_SHARPE=WARNING as OK and (b) OMITS IS_LADDER_SHARPE, so it cannot fail on the gate that
actually decides the Sharpe/recency submission. srl2 (O0Zlk5xv, sharpe 1.11) was crowned champion though
1.11 < IS-Ladder FAIL_THRESHOLD 1.59, which is very likely a ladder fail — but note that is an INFERENCE:
in state/resim_results.jsonl srl2's IS_LADDER_SHARPE is ABSENT (never evaluated), so a LIVE submission
check is the only proof. (The 180 IS_LADDER FAILs in that file are v5_distress+v5_optskew junk roots, NOT srl2.)

v3 defines SUBMITTABLE by the REAL binding gates, explicitly:
  1. IS_LADDER_SHARPE PASS            (the recency ladder — the true sharpe gate, not WARNING-masked)
  2. LOW_SUB_UNIVERSE_SHARPE PASS     (breadth)
  3. CONCENTRATED_WEIGHT / weight PASS
  4. no OTHER hard FAIL               (real zero-fail)
  5. book-corr gate PASS              (maxcorr < 0.7 vs the 189-book; corr_check.py)   [if PnL available]
  6. theme match                      (theme_check.py)                                  [if provided]
LOW_SHARPE alone may be WARNING (the platform allows it) — but IS_LADDER is the hard recency gate and is
NOT waivable. CRITICAL: a gate that was never evaluated is ABSENT, which is UNKNOWN, NOT a FAIL — the
verdict is then "unresolved", never a false "non-submittable" on missing telemetry.

Pure/deterministic. Usage:
  submittable.py <resim_results.jsonl> [--book ...] [--corr-threshold 0.7]
  python: verdict(row, book_ids=None, ...) -> {submittable, blockers:[...], ...}
"""
from __future__ import annotations
import argparse, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))

# Gates that must be PASS to SUBMIT to Power Pool. Khoa 2026-07-18 ground truth: the real submit error is
# "Sharpe < 1.58" — a WARNING on LOW_SHARPE/LOW_2Y_SHARPE (i.e. sharpe below the 1.58 bar) BLOCKS submission
# even though the SIM reports fails=[] ("zero-fail"). So WARNING on these is NOT submittable — they must PASS.
MUST_PASS_TO_SUBMIT = ("LOW_SHARPE", "LOW_2Y_SHARPE")
# breadth/weight also must PASS (FAIL blocks anyway; PASS in live data)
MUST_PASS_TO_SUBMIT += ("LOW_SUB_UNIVERSE_SHARPE", "CONCENTRATED_WEIGHT")
# LOW_FITNESS is a HARD Power-Pool gate — Khoa ground truth 2026-07-18: alpha 9q7Z9N02 (sh1.61,2Y2.11) was
# REJECTED on LOW_FITNESS (fitness 0.52 < 1.0). It is NOT waivable. Must PASS (>=1.0).
MUST_PASS_TO_SUBMIT += ("LOW_FITNESS",)
# LADDER ESCAPE (platform ground truth 2026-07-23): IS_LADDER_SHARPE PASS (>=2.02) keeps weak
# sharpe/fitness/2Y as non-blocking WARNINGs at submit (A17YGP7d: only theme FAILed). Without it they
# HARDEN to FAIL (A17alXOR, ladder ~1.5: 403 LOW_SHARPE/LOW_FITNESS/LOW_2Y_SHARPE).
# Real bar: (sharpe>=1.58 AND fitness>=1.0 AND 2Y ok) OR IS_LADDER_SHARPE>=2.02; PLUS theme + prod<0.7 + self<0.7.
LADDER_WAIVES = ("LOW_SHARPE", "LOW_2Y_SHARPE", "LOW_FITNESS")
# other checks: only a hard FAIL blocks; WARNING is fine
WAIVABLE_WARN = ("CLUSTER_TEST", "HT_TURNOVER", "HT_AFTER_COST_SHARPE", "HT_LIQUID_TOP200_SHARPE",
                 "HT_INVESTABLE_MAX_POSITION_SHARPE", "HT_INVESTABLE_MAX_TRADE_SHARPE",
                 "HT_HIGH_TURNOVER_RETURNS_RATIO", "HT_PNL_REALIZATION_HORIZON", "OSMOSIS_ALLOCATION",
                 "HT_ORTHOGONAL_RAM_NEUTRALIZATION")
# checks resolved only at submit-time — not a sim blocker, evaluated separately (live-fetch confirmed set)
PENDING = ("SELF_CORRELATION", "PROD_CORRELATION", "POWER_POOL_CORRELATION", "REGULAR_SUBMISSION",
           "DATA_DIVERSITY", "MATCHES_THEMES")


def _checks_map(row):
    out = {}
    for c in row.get("checks", []) or []:
        if isinstance(c, dict) and "name" in c:
            out[c["name"]] = c.get("result")
    return out


def verdict(row, book_ids=None, corr_threshold=0.7, require_theme=True):
    """Return the submittability verdict, ALIGNED TO THE PLATFORM's real definition (ladder ground truth
    2026-07-23: sharpe/fitness/2Y WARNINGs BLOCK unless IS_LADDER_SHARPE>=2.02 waives them).

      SUBMITTABLE (True)      -> every MUST_PASS gate (LOW_SHARPE, LOW_2Y_SHARPE, LOW_FITNESS,
                                 LOW_SUB_UNIVERSE_SHARPE, CONCENTRATED_WEIGHT) is PASS; OR, if
                                 IS_LADDER_SHARPE==PASS (>=2.02), a WARNING on the ladder-waivable
                                 sharpe/fitness/2Y gates is tolerated; AND no other IS-check FAILs;
                                 AND book-corr < threshold (or unknown). PENDING submit-checks (theme,
                                 self/prod corr) are LISTED, not blockers — they resolve at submit.
      NON_SUBMITTABLE (False) -> a must-pass gate is WARNING/FAIL and not ladder-waived, OR any other
                                 IS-check FAILs, OR book-corr >= threshold.
      UNRESOLVED (None)       -> the row carries no checks at all (cannot judge)."""
    ch = _checks_map(row)
    if not ch:
        return {"alpha": row.get("alpha"), "old_id": row.get("old_id"), "sharpe": row.get("sharpe"),
                "submittable": None, "status": "UNRESOLVED", "blockers": [], "pending": []}
    # SUBMIT rule (Khoa ground truth): the sharpe gates must PASS (WARNING = sharpe < 1.58 = blocked); any
    # other IS-check FAIL also blocks; WARNING elsewhere is fine; PENDING resolves at submit.
    blockers = []
    unresolved = []
    ladder_pass = ch.get("IS_LADDER_SHARPE") == "PASS"   # >=2.02 -> weak-metric WARNINGs stay non-blocking
    for g in MUST_PASS_TO_SUBMIT:
        r = ch.get(g)
        if r is None:                           # gate never evaluated -> UNKNOWN, not a silent green-light
            if ladder_pass and g in LADDER_WAIVES:
                continue                        # ladder>=2.02 covers weak sharpe/fitness/2Y even when absent
            unresolved.append(f"{g}=ABSENT")    # binding gate unevaluated -> verdict is UNRESOLVED, not PASS
        elif r != "PASS":                       # WARNING or FAIL on a must-pass gate blocks (below the bar)
            if ladder_pass and g in LADDER_WAIVES and r == "WARNING":
                continue                        # A17YGP7d precedent: ladder>=2.02 keeps these soft
            blockers.append(f"{g}={r}")
    for n, r in ch.items():
        # A check in PENDING is waived only while its result is literally "PENDING"; a RESOLVED FAIL on
        # SELF/PROD/POWER_POOL_CORRELATION, DATA_DIVERSITY, or REGULAR_SUBMISSION is a real submit blocker
        # (the old `n not in PENDING` here silently ignored a corr FAIL). MATCHES_THEMES stays theme-gated below.
        # IS_LADDER_SHARPE is an ESCAPE signal (waives weak sharpe/fitness/2Y when PASS), never a standalone
        # blocker: a FAIL on it must not block an alpha that already satisfies the primary disjunct
        # (sharpe>=1.58 AND fitness>=1.0 AND 2Y ok) per the OR-bar above.
        if (r == "FAIL" and n not in MUST_PASS_TO_SUBMIT and n not in WAIVABLE_WARN
                and n != "MATCHES_THEMES" and n != "IS_LADDER_SHARPE"):
            blockers.append(f"{n}=FAIL")
    pending = [n for n in PENDING if ch.get(n) == "PENDING"]
    # book-correlation gate (real submit test; compute if PnL available)
    corr_detail = None
    aid = row.get("alpha") or row.get("alphaId") or row.get("sid")
    if book_ids and aid:
        try:
            import corr_check
            ok, corr_detail = corr_check.corr_gate(aid, book_ids, corr_threshold)
            if ok is False:
                blockers.append(f"BOOK_CORR={corr_detail.get('max_abs')}>{corr_threshold}")
        except Exception as e:  # noqa: BLE001
            corr_detail = {"error": str(e)}
    if require_theme and ch.get("MATCHES_THEMES") == "FAIL":
        blockers.append("MATCHES_THEMES=FAIL")
    if blockers:                                # a concrete WARNING/FAIL is decisive over an absent gate
        status, submittable = "NON_SUBMITTABLE", False
    elif unresolved:                            # no blocker, but a binding gate was never evaluated
        status, submittable = "UNRESOLVED", None
    else:
        status, submittable = "SUBMITTABLE", True
    return {
        "alpha": aid, "old_id": row.get("old_id"), "sharpe": row.get("sharpe"),
        "submittable": submittable, "status": status, "blockers": blockers,
        "unresolved": unresolved,
        "pending_at_submit": pending, "book_corr": corr_detail,
        "low_2y": ch.get("LOW_2Y_SHARPE"), "low_sharpe": ch.get("LOW_SHARPE"),
    }


def _self_test():
    # srl2 at 1.11: LOW_SHARPE/LOW_2Y=WARNING (below the 1.58 bar) -> NOT submittable (Khoa ground truth)
    srl2_real = {"alpha": "O0Zlk5xv", "sharpe": 1.11, "checks": [
        {"name": "LOW_SHARPE", "result": "WARNING"}, {"name": "LOW_2Y_SHARPE", "result": "WARNING"},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "MATCHES_THEMES", "result": "PENDING"}, {"name": "SELF_CORRELATION", "result": "PENDING"}]}
    v = verdict(srl2_real)
    assert v["submittable"] is False and any("LOW_SHARPE" in b for b in v["blockers"]), v
    # 9q7Z9N02 ground truth (2026-07-18): all sharpe gates PASS but LOW_FITNESS 0.52 -> REJECTED at submit.
    # fitness is a HARD must-pass gate; WARNING on it blocks.
    rejected_9q7 = {"alpha": "9q7Z9N02", "sharpe": 1.61, "checks": [
        {"name": "LOW_SHARPE", "result": "PASS"}, {"name": "LOW_2Y_SHARPE", "result": "PASS"},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "LOW_FITNESS", "result": "WARNING", "value": 0.52}, {"name": "MATCHES_THEMES", "result": "PENDING"}]}
    vr = verdict(rejected_9q7)
    assert vr["submittable"] is False and any("LOW_FITNESS" in b for b in vr["blockers"]), vr
    # a genuine full-passer (all 5 MUST_PASS incl LOW_FITNESS PASS) -> SUBMITTABLE (pending listed)
    good = {"alpha": "X", "sharpe": 1.7, "checks": [
        {"name": "LOW_SHARPE", "result": "PASS"}, {"name": "LOW_2Y_SHARPE", "result": "PASS"},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "LOW_FITNESS", "result": "PASS", "value": 1.2}, {"name": "MATCHES_THEMES", "result": "PENDING"}]}
    vg = verdict(good)
    assert vg["submittable"] is True and "MATCHES_THEMES" in vg["pending_at_submit"], vg
    # A17YGP7d ground truth (2026-07-23): weak sharpe(1.0)/fitness(0.54) WARNINGs do NOT block because
    # IS_LADDER_SHARPE=2.08>=2.02 PASSED — only theme FAILed at live submit.
    a17ygp7d = {"alpha": "A17YGP7d", "sharpe": 1.0, "checks": [
        {"name": "IS_LADDER_SHARPE", "result": "PASS", "value": 2.08},
        {"name": "LOW_SHARPE", "result": "WARNING"}, {"name": "LOW_2Y_SHARPE", "result": "WARNING"},
        {"name": "LOW_FITNESS", "result": "WARNING", "value": 0.54},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "MATCHES_THEMES", "result": "PENDING"}]}
    vl = verdict(a17ygp7d)
    assert vl["submittable"] is True and not vl["blockers"], vl
    # A17alXOR ground truth (2026-07-23): same weak metrics WITHOUT ladder pass (~1.5<2.02) -> 403
    # FAILs=[LOW_SHARPE, LOW_FITNESS, LOW_2Y_SHARPE]; WARNINGs harden, submit blocked.
    a17alxor = {"alpha": "A17alXOR", "sharpe": 1.54, "checks": [
        {"name": "LOW_SHARPE", "result": "WARNING"}, {"name": "LOW_2Y_SHARPE", "result": "WARNING"},
        {"name": "LOW_FITNESS", "result": "WARNING"},
        {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"}, {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
        {"name": "MATCHES_THEMES", "result": "PENDING"}]}
    vx = verdict(a17alxor)
    assert vx["submittable"] is False and len(vx["blockers"]) == 3, vx
    # no checks -> UNRESOLVED
    assert verdict({"alpha": "Z", "checks": []})["submittable"] is None
    print("submittable self-test PASS (bar: [sharpe>=1.58 AND fitness>=1.0 AND 2Y ok] OR IS_LADDER_SHARPE>=2.02)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", nargs="?", help="resim_results.jsonl (one alpha row per line)")
    ap.add_argument("--book", default=str(ROOT / "state/submitted_all_live.json"))
    ap.add_argument("--corr-threshold", type=float, default=0.7)
    ap.add_argument("--no-corr", action="store_true", help="skip the book-corr gate")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if not a.results:
        ap.error("results file required (or --self-test)")
    book = None if a.no_corr else [x["id"] for x in json.load(open(a.book)) if isinstance(x, dict) and "id" in x]
    rows = [json.loads(l) for l in open(a.results) if l.strip()]
    sub = [verdict(r, book, a.corr_threshold) for r in rows]
    n_sub = sum(1 for s in sub if s["submittable"] is True)
    n_unres = sum(1 for s in sub if s["submittable"] is None)
    n_non = sum(1 for s in sub if s["submittable"] is False)
    print(f"{len(rows)} alphas -> SUBMITTABLE={n_sub}  NON_SUBMITTABLE={n_non}  UNRESOLVED={n_unres} (v3 real-gate def)")
    for s in sub:
        if s["submittable"] is True:
            print(f"  SUBMITTABLE {s['alpha']} sharpe={s['sharpe']}")
    from collections import Counter
    bc = Counter(b.split("=")[0] for s in sub for b in s["blockers"])
    ur = Counter(u.split("=")[0] for s in sub for u in s.get("unresolved", []))
    print("  blocker freq:", dict(bc))
    print("  unresolved freq:", dict(ur))
    return 0


if __name__ == "__main__":
    sys.exit(main())
