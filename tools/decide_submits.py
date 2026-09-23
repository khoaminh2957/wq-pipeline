#!/usr/bin/env python3
"""Write `state/auto_submit_decisions.json` — the missing producer, and the only writer of it.

WHAT THIS CLOSES. Round 10 built four pieces of an automatic submitter and every one of them
worked, but `auto_submit.py` reads exactly one input and **nothing wrote it**, so the machine was
inert. This is that writer. It is deliberately the LAST piece, because a producer that guesses is
worse than no producer at all: `auto_submit` fails closed on a missing file and POSTs nothing, but
it trusts a file that exists.

THE RULE, from the operator (Khoa, 2026-08-13): a FULL cell gets nothing; a cell close to unlocking
gets a submit. Scope is one region and one delay — USA, delay 1.

His wording, "nếu full thì ko nộp, nếu gần đủ như 2/3 hay 3/3 thì nộp luôn", is literally
self-contradictory (3/3 IS full). Both readings collapse to the same behaviour — a cell with
`alphaCount < 3` may receive, a cell at 3 or above may not — so nothing here had to be guessed. The
ambiguity is recorded rather than silently resolved, and this docstring is where a future
disagreement should surface.

WHAT IT REFUSES TO DECIDE, each because getting it wrong spends an alpha forever:

  * an alpha whose cell mapping is not `high` confidence
  * an alpha touching THREE OR MORE cells. Measured (`cell_map` R3, n=2): such an alpha is credited
    to NO cell at all — `pyramidThemes.effective == 0`, and summing memberships reproduces the
    platform counter exactly only when those two are excluded. **n=2 is a thin reed for a rule that
    refuses 44.6% of held formulas**, and the one experiment that would settle it is a submit, which
    is the operator's call and not this file's.
  * an alpha with no correlation verdict, or a stale one. PROD binds 4.8x harder than SELF and has
    no offline surrogate; stored prod readings drift ONE-DIRECTIONALLY UPWARD (8 of 111 changed, 8
    of 8 up, 6 crossing 0.70 clean→dirty, median |Δ| 0.0662), so an old clean reading is not a clean
    alpha.
  * a second alpha of a mechanic already spoken for in this same plan.

WHAT IT DOES NOT KNOW. Whether a submit into a 2/3 cell actually unlocks it is platform
adjudication, observable only after a POST. Whether the 0.70 prod line is hard is contested: a
0.7031 was rejected verbatim, but two alphas above 0.70 are live. This file refuses at 0.70 on cost
asymmetry — a wrong refusal costs a delay, a wrong POST costs the alpha — and says so rather than
letting the number harden into folklore. MECHANISM: UNKNOWN for both.
"""
import argparse
import collections
import datetime
import glob
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cell_map                                                        # noqa: E402
import pyramid_gate                                                    # noqa: E402
from funnel import gates                                               # noqa: E402

OUT = ROOT / "state/auto_submit_decisions.json"
CORR = ROOT / "state/prod_corr_measured.json"
REGION, DELAY = "USA", 1
UNLOCKS_AT = 3
PROD_MAX = SELF_MAX = 0.70

#: How old a stored correlation reading may be. Deliberately tighter than it sounds generous: the
#: measured drift is one-directional upward with a median magnitude of 0.0662, which is larger than
#: most candidates' margin to the wall, and NO per-entry timestamp exists — only the file's mtime.
#: So this ages the FILE, and a candidate whose margin is under the drift is refused outright.
CORR_MAX_AGE_S = 6 * 3600
MIN_MARGIN = 0.0662


def _submitted_ids():
    out = set()
    for f in ("state/submit_budget.jsonl", "state/funnel/submit_log.jsonl"):
        p = ROOT / f
        if not p.exists():
            continue
        for line in p.read_text(errors="ignore").splitlines():
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            for k in ("alpha", "alpha_id", "id", "old_id"):
                if isinstance(r.get(k), str):
                    out.add(r[k])
    return out


def _journal_rows():
    """alpha id -> its most recent journal row, across every journal on disk.

    Later rows win: a re-simulated alpha must be judged on its latest numbers, not its first.
    """
    rows = {}
    seen = set()
    for pat in ("state/**/journal.jsonl", "state/resim_results.jsonl", "state/**/*results*.jsonl"):
        for f in glob.glob(str(ROOT / pat), recursive=True):
            if f in seen:
                continue
            seen.add(f)
            try:
                fh = open(f, errors="ignore")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if not line.startswith("{"):
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(r.get("alpha"), str):
                        rows[r["alpha"]] = r
    return rows


def _formulas():
    out = {}
    for pat in ("state/**/*targets*.json", "state/**/pool_*.json"):
        for f in glob.glob(str(ROOT / pat), recursive=True):
            try:
                j = json.loads(pathlib.Path(f).read_text(errors="ignore"))
            except (ValueError, OSError):
                continue
            rows = j if isinstance(j, list) else (j.get("rows") or j.get("alphas") or [])
            if not isinstance(rows, list):
                continue
            for r in rows:
                if isinstance(r, dict) and isinstance(r.get("old_id"), str):
                    fm = r.get("formula")
                    if not fm and isinstance(r.get("regular"), str):
                        fm = r["regular"]
                    if fm:
                        out[r["old_id"]] = fm
    return out


def corr_ok(alpha, store, file_age_s):
    """(ok, why). Absent is neither pass nor fail — it is a refusal with its own reason."""
    if file_age_s > CORR_MAX_AGE_S:
        return False, "correlation store is %.1fh old (limit %.0fh)" % (
            file_age_s / 3600.0, CORR_MAX_AGE_S / 3600.0)
    row = store.get(alpha)
    if not isinstance(row, dict):
        return False, "no correlation verdict"
    p, s = row.get("prod_maxcorr"), row.get("self_maxcorr")
    if not isinstance(p, (int, float)) or isinstance(p, bool):
        return False, "prod verdict missing or non-numeric"
    if row.get("prod_breach_count"):
        return False, "prod_breach_count %s > 0" % row["prod_breach_count"]
    if not isinstance(s, (int, float)) or isinstance(s, bool) or row.get("self_measured") is False:
        return False, "self verdict missing or non-numeric"
    if p >= PROD_MAX:
        return False, "prod %.4f >= %.2f" % (p, PROD_MAX)
    if s >= SELF_MAX:
        return False, "self %.4f >= %.2f" % (s, SELF_MAX)
    # THE MARGIN RULE. A reading whose distance to the wall is smaller than the measured drift is
    # not evidence of a clean alpha; it is evidence that we measured it a while ago.
    if PROD_MAX - p < MIN_MARGIN:
        return False, ("prod %.4f is within the measured drift (%.4f) of the %.2f wall -- "
                       "re-measure before spending a submit" % (p, MIN_MARGIN, PROD_MAX))
    return True, "prod %.4f / self %.4f, margin %.4f" % (p, s, PROD_MAX - p)


def build(cells, *, now=None):
    """(decisions, rejections). Pure over its inputs so the whole thing is testable offline."""
    now = now if now is not None else time.time()
    counts = cells.counts or {}
    short = {c: UNLOCKS_AT - n for c, n in counts.items() if n < UNLOCKS_AT}

    store = {}
    age = float("inf")
    if CORR.exists():
        try:
            store = json.loads(CORR.read_text())
            age = now - CORR.stat().st_mtime
        except (ValueError, OSError):
            store = {}

    submitted = _submitted_ids()
    rows = _journal_rows()
    formulas = _formulas()

    rej = collections.Counter()
    scored = []
    for alpha, row in rows.items():
        if alpha in submitted:
            rej["already submitted"] += 1
            continue
        passed, _failed, _missing = gates.zero_fail(row)
        if not passed:
            rej["not a gem"] += 1
            continue
        fm = formulas.get(row.get("old_id", ""))
        if not fm:
            rej["no formula on disk"] += 1
            continue
        v = cell_map.cells_for(fm, region=REGION, delay=DELAY)
        cs = tuple(sorted(getattr(v, "cells", None) or []))
        if getattr(v, "confidence", "unknown") != "high":
            rej["cell mapping not high-confidence"] += 1
            continue
        if len(cs) >= 3:
            rej["3+ cells -> credited nowhere (n=2)"] += 1
            continue
        target = [c for c in cs if c in short]
        if not target:
            rej["fills no short cell"] += 1
            continue
        ok, why = corr_ok(alpha, store, age)
        if not ok:
            # Bucket by CLASS, not by the reason's full text. Keying on the whole string put every
            # distinct breach count in its own row and turned a summary into a list.
            if "breach" in why:
                cls = "prod breaches > 0"
            elif "within the measured drift" in why:
                cls = "prod margin < measured drift %.4f" % MIN_MARGIN
            elif why.startswith("prod "):
                cls = "prod >= %.2f" % PROD_MAX
            elif why.startswith("self "):
                cls = "self >= %.2f" % SELF_MAX
            else:
                cls = why
            rej["correlation: " + cls] += 1
            continue
        mech = (row.get("meta") or {}).get("mechanic") or row.get("old_id")
        # Nearest-to-unlocking cell first; that is what one submit buys.
        cell = min(target, key=lambda c: short[c])
        scored.append((short[cell], -(row.get("fitness") or 0), alpha, cell, mech, fm, why))

    scored.sort()
    decisions, spoken_for, filled = {}, set(), collections.Counter()
    for needs, _negfit, alpha, cell, mech, fm, why in scored:
        if mech in spoken_for:
            rej["mechanic already in this plan"] += 1
            continue
        if filled[cell] >= short[cell]:
            rej["cell already satisfied by this plan"] += 1
            continue
        spoken_for.add(mech)
        filled[cell] += 1
        decisions[alpha] = {
            "cell": cell, "region": REGION, "delay": DELAY, "formula": fm, "family": str(mech),
            "reason": "%s at %d/%d, needs %d; %s" % (cell, counts.get(cell, 0), UNLOCKS_AT,
                                                     needs, why),
        }
    return decisions, rej


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help="write the decisions file. Without it nothing is written and the plan is "
                         "only printed -- auto_submit fails closed on a missing file, so not "
                         "writing is always the safe outcome.")
    ap.add_argument("--offline", action="store_true", help="use the cached cell counts")
    args = ap.parse_args()

    cells = pyramid_gate.cell_state(REGION, DELAY, session=None) if args.offline else \
        pyramid_gate.cell_state(REGION, DELAY)
    marker = pyramid_gate.marker(cells) if hasattr(pyramid_gate, "marker") else ""
    if marker:
        print(marker)
    if not cells.counts:
        print("REFUSED: no cell counts (%s) -- not writing" % (cells.error or "unknown"))
        return 2

    decisions, rej = build(cells)
    print("cells %s/d%d  source=%s  age=%ss" % (REGION, DELAY, cells.source, int(cells.age_s or 0)))
    for c, n in sorted(cells.counts.items(), key=lambda kv: kv[1]):
        if n < UNLOCKS_AT:
            print("   short: %-16s %d/%d" % (c, n, UNLOCKS_AT))
    print("candidates refused:")
    for why, n in rej.most_common():
        print("   %-46s %d" % (why, n))
    print("PLAN: %d decision(s)" % len(decisions))
    for a, d in decisions.items():
        print("   %-12s -> %-16s %s" % (a, d["cell"], d["reason"]))

    if not decisions:
        print("nothing to write")
        return 0
    if not args.write:
        print("(dry run -- pass --write to produce %s)" % OUT)
        return 0
    OUT.write_text(json.dumps({
        "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "decisions": decisions}, indent=2))
    print("wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
