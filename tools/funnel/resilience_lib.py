#!/usr/bin/env python3
"""resilience_lib.py — v6.2 S7 RESILIENCE / failure-recovery + budget-ledger
accounting, ported verbatim from the ALPHA_PIPELINE v6.2 heredoc (git
545bac4..HEAD ALPHA_PIPELINE.md :418-511). Completes S10-7/S10-9: gate_lib
carries the S7 QUALITY signals; this module carries the RESILIENCE half and the
(observational-only, per the S2.7 no-cap ruling) budget ledger.

Rules preserved verbatim from the v6.2 code:

  * window w = resim_metrics rows with t0 <= ts <= t1.
  * enc/rec classes: e429_rate (req/refused, code 429, Retry-After > 0 ONLY —
    slot-429s without Retry-After are NOT failures), e401 (req code 401;
    recovered iff a later restart AND orphan_lost==0), e400 (refused code 400;
    recovered iff a later batch_launch), cbreak (circuit_break; recovered iff a
    later 200 req), preflight (outcome not in (None,'ok'); recovered iff a later
    same-probe ok OR a completed API-free fallback i.e. blocked is not None),
    poison (per-old_id over the RESULTS history: any row without an alpha;
    recovered iff any row of that old_id has one).
  * retry_after header is a STRING — cast, TypeError-safe (v6 fix).
  * resilience = 10.0 iff 0 encountered, else round(10*recovered/encountered,1).
    Caps: orphan_lost>0 -> <=6.0; unrecovered rate-429 -> <=3.0; blocked cycle
    -> <=6.0 (a killed cycle may NEVER journal 10.0 — hx2 anti-pattern).
  * budget_day_used = distinct same-day first-launch ids from post-patch-10
    batch_launch rows (ids=[...]) + raw n for pre-patch rows (may double-count
    retries — journal a note); budget_cycle_used = sum of batch_launch n in w.
    METRICS-ONLY: never used to block a launch (S2.7 no-cap, Khoa 2026-07-16).

No WQ API calls; pure arithmetic over journal rows.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

FAILURE_CLASSES = ("e429_rate", "e401", "e400", "poison", "cbreak", "preflight")


def load_jsonl(path):
    """Journal rows (dicts) from a .jsonl path; unparseable lines skipped."""
    rows = []
    try:
        lines = open(path)
    except OSError:
        return rows
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if isinstance(j, dict):
            rows.append(j)
    return rows


def results_hist(results_rows, run=None, target_ids=None):
    """old_id -> [result rows] for ids in this cycle (RUN prefix or targets set)
    — the v6.2 `hist` map the poison class is computed over."""
    hist = {}
    target_ids = target_ids or set()
    for r in results_rows:
        oid = str(r.get("old_id", ""))
        if not oid:
            continue
        if (run and oid.startswith(run)) or oid in target_ids:
            hist.setdefault(oid, []).append(r)
    return hist


def _ra(e):
    """Retry-After header is a STRING — cast (v6 fix: pre-cast code TypeError'd)."""
    try:
        return float(e.get("retry_after") or 0)
    except (TypeError, ValueError):
        return 0


def cycle_resilience(metrics_rows, t0, t1, blocked=None, hist=None):
    """v6.2 S7 RESILIENCE accounting over one cycle window.

    metrics_rows: resim_metrics.jsonl rows (dicts). hist: results_hist() map for
    the poison class (omit -> poison enc/rec = 0). blocked: blocked_reason or
    None. Returns {failures:{cls:{enc,rec}}, orphan_lost, resilience}.
    """
    w = [e for e in metrics_rows if t0 <= e.get("ts", 0) <= t1]

    def later(pred, ts):
        return any(e.get("ts", 0) > ts and pred(e) for e in w)

    ok = lambda e: e.get("ev") == "req" and e.get("code") == 200
    lost = sum(e.get("n", 0) for e in w if e.get("ev") == "orphan_lost")

    enc = {k: 0 for k in FAILURE_CLASSES}
    rec = dict(enc)
    for e in w:
        if e.get("ev") in ("req", "refused") and e.get("code") == 429 and _ra(e) > 0:
            enc["e429_rate"] += 1
            rec["e429_rate"] += later(ok, e["ts"])
        if e.get("ev") == "req" and e.get("code") == 401:
            enc["e401"] += 1
            rec["e401"] += (later(lambda x: x.get("ev") == "restart", e["ts"])
                            and lost == 0)
        if e.get("ev") == "refused" and e.get("code") == 400:
            enc["e400"] += 1
            rec["e400"] += later(lambda x: x.get("ev") == "batch_launch", e["ts"])
        if e.get("ev") == "circuit_break":
            enc["cbreak"] += 1
            rec["cbreak"] += later(ok, e["ts"])
        if e.get("ev") == "preflight" and e.get("outcome") not in (None, "ok"):
            enc["preflight"] += 1
            # recovered = later same-probe ok OR a completed API-free fallback
            rec["preflight"] += later(
                lambda x: x.get("ev") == "preflight"
                and x.get("probe") == e.get("probe")
                and x.get("outcome") == "ok", e["ts"]) or (blocked is not None)

    hist = hist or {}
    pois = [o for o, rs in hist.items() if any(not x.get("alpha") for x in rs)]
    enc["poison"] = len(pois)
    rec["poison"] = sum(1 for o in pois if any(x.get("alpha") for x in hist[o]))

    E = sum(enc.values())
    res = 10.0 if E == 0 else round(10.0 * sum(rec.values()) / E, 1)
    if lost > 0:
        res = min(res, 6.0)
    if enc["e429_rate"] > rec["e429_rate"]:
        res = min(res, 3.0)
    if blocked:
        res = min(res, 6.0)

    return {"failures": {k: {"enc": enc[k], "rec": rec[k]} for k in enc},
            "orphan_lost": lost, "resilience": res}


def budget_cycle_used(metrics_rows, t0, t1):
    """Sims launched inside this cycle window (batch_launch n-sum)."""
    return sum(e.get("n", 0) for e in metrics_rows
               if e.get("ev") == "batch_launch" and t0 <= e.get("ts", 0) <= t1)


def budget_day_used(metrics_rows, midnight_ts=None):
    """Distinct same-day first-launch ids (post-patch-10 batch_launch ids=[...])
    + raw n for pre-patch rows (retry-inflated — note it). METRICS-ONLY (S2.7)."""
    if midnight_ts is None:
        midnight_ts = dt.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
    ids, n = set(), 0
    for e in metrics_rows:
        if e.get("ev") == "batch_launch" and e.get("ts", 0) >= midnight_ts:
            if e.get("ids"):
                ids.update(e["ids"])
            else:
                n += e.get("n", 0)
    return len(ids) + n
