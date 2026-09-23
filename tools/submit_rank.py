#!/usr/bin/env python3
"""submit_rank.py — decide WHICH alpha to spend on a pyramid cell (USA, delay 1).

READ-ONLY. This module imports no HTTP client, holds no session, and contains no POST. It reads
ledgers off disk and returns an order. The irreversible POST belongs to tools/auto_submit.py.

Contract bound by tools/submit_plan.py:
    rank_for_cell(cell, candidates) -> [alpha_id, ...]   best first, refused ids ABSENT.


THE OBJECTIVE, and why it is this one
-------------------------------------
Not "rank alphas by quality". The binding constraint is the SUBMIT CHANNEL, not the gem supply:
state/funnel/winners.csv holds 128 winners over 19 days (2026-07-23..2026-08-10) = 6.7/day, of
which 90 sit in RESERVE unspent, against 0.68-1.6 submits/day actually leaving. So the quantity
being maximised is:

    P(this irreversible POST converts into a filled cell)

and the quantity being protected is the option value of the alpha's MECHANIC, because one submit
adjudicates the whole family (measured: 464 rows of one mechanic -> 26 gems -> 1 submission).

The tier order below is the order in which candidates actually DIE, measured on this repo's own
corpus (re-derivation in harness13/massgen/experiments/SUBMIT_RANK_R10.md):

    axis          pass rate      n     source
    self  < 0.70    61.6%       867    prod_corr_measured.json + funnel/corr_results.jsonl merge
    prod  < 0.70    13.6%       867    same

PROD is 4.5x the filter SELF is, so PROD sorts first. That ratio is an OBSERVATION on this
corpus; no experiment here established why the production book is harder. MECHANISM: UNKNOWN.

Tiers are LEXICOGRAPHIC, not a weighted sum. Nothing measured here establishes an exchange rate
between prod headroom and Sharpe, and a weighted sum would silently invent one -- letting a big
Sharpe buy down a correlation risk that the platform, not the score, adjudicates.


THE TWO LIMITS, and the contradiction that is NOT resolved
----------------------------------------------------------
PROD_LIMIT 0.70   The platform's own rejection of 3qeeOxlQ read `PROD_CORRELATION value=0.7031
                  limit=0.7` (recorded verbatim in tools/fetch_prod_corr.py:prod_maxcorr).
SELF_LIMIT 0.70   SUBMISSION_GATES.md "Self-Correlation ... Threshold 0.7"; enforced fail-closed
                  by tools/submit_alphas.py:_fresh_corr_ok.

COUNTER-EVIDENCE, kept rather than buried: two alphas whose STORED prod value is above 0.70 are
live on the platform -- zqRN8LGE (prod 0.7078) and Xg8oQJRl (prod 0.8, a coarse bucket read, so
its true max is in [0.7, 0.8)). Both appear in state/live_alphas.json and state/active_ids.json,
and Xg8oQJRl's later re-submit was 403 ALREADY_SUBMITTED. SUBMISSION_GATES.md also documents the
correlation tests as CONDITIONAL (test #5 bites only when the alpha additionally misses 1.0x
ISLadder AND runs turnover > 30%).

Candidate explanations, none distinguished by any experiment here:
  (a) the stored 0.7078 was measured AFTER the submit and the reading drifted up (see DRIFT);
  (b) the conditional path -- strong ladder + low turnover clears despite correlation;
  (c) the coarse bucket reading is not the number the platform gated on.
MECHANISM: UNKNOWN.

This module REFUSES at >= 0.70 anyway, and that is a cost asymmetry argument, not a claim about
the platform: a wrong refusal costs a delay, a wrong POST costs the alpha permanently (a 403
adjudicates and spends it). `explain()` prints the counter-evidence so the choice stays visible.


DRIFT: why a stored clean number is not a clean alpha
-----------------------------------------------------
111 alphas carry a prod value BOTH in winners.csv and in the later state/prod_corr_measured.json
re-measurement. 103 identical, 8 changed -- all 8 UPWARD, 6 of them crossing 0.70 from clean to
dirty, 0 crossing the other way. Median |delta| of the movers 0.0662, max 0.1596.

    e7xY9Z7l 0.6048->0.7019   E5ejmAXR 0.6946->0.8542   rKPxYWw9 0.6883->0.7267
    LLdQjaVM 0.6995->0.7329   N1RZ5Azo 0.6982->0.8193   ZYKOeRr3 0.6853->0.7793

DRIFT = 0.0662 is that median, used to band the prod axis: a candidate sitting within one observed
drift step of the limit is ranked below one that is two steps clear. The all-upward asymmetry is an
OBSERVATION (n=8); no experiment distinguished "our own twins went live", "the book grew", and "the
coarse->precise reader change" as its cause. MECHANISM: UNKNOWN.

Neither prod_corr_measured.json nor corr_results.jsonl stores a per-entry TIMESTAMP, so the age of
any single reading is not knowable from disk. Ranking therefore never certifies freshness; the
submit path re-measures (tools/submit_alphas.py:_fresh_corr_ok) and that remains the real check.


THE PRESENCE CONTRACT
---------------------
57.6% of alphas in the winners ledger carry no prod verdict. Absent is neither pass nor fail. An
unmeasured candidate is UNRANKABLE and never appears in the returned order -- it is not sorted last,
it is not there. `explain()` states the measurement cost: 2 authenticated GETs
(/alphas/{id}/correlations/prod and /self), served at 69.8/hour measured over 5,534 served probes
in state/corr_budget.jsonl spanning 79.3h == ~52 s of channel time per alpha.
"""
import csv
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

PROD_LIMIT = 0.70
SELF_LIMIT = 0.70
DRIFT = 0.0662          # median |delta| of the 8 prod readings that moved, of 111 paired
SELF_CLEAR = 0.60       # OPERATOR-CHOSEN, NOT ESTABLISHED: no measurement here sets this split.
LOW_TURNOVER = 0.30     # SUBMISSION_GATES.md test #5 bites only above 30% turnover

WINNERS = ROOT / "state/funnel/winners.csv"
PROD_MEASURED = ROOT / "state/prod_corr_measured.json"
CORR_RESULTS = ROOT / "state/funnel/corr_results.jsonl"
LIVE_IDS = (ROOT / "state/live_alphas.json", ROOT / "state/active_ids.json")
SUBMIT_LOG = ROOT / "state/funnel/submit_log.jsonl"
SUBMITTED_CELLS = ROOT / "state/submitted_cells_today.jsonl"

# Verdict codes. Only RANKABLE is ever returned in an order.
RANKABLE = "RANKABLE"
SPENT = "SPENT"                    # already POSTed; a second POST is a 403 that adjudicates nothing
PROD_MISSING = "PROD_MISSING"      # presence contract: absent is not clean
SELF_MISSING = "SELF_MISSING"
PROD_FAIL = "PROD_FAIL"
SELF_FAIL = "SELF_FAIL"
MECHANIC_DUP = "MECHANIC_DUP"      # this plan already spends a submit on this mechanic

# Tokens that appear in every formula because of the price-volume carrier and the operator
# vocabulary. They carry no mechanic identity, so they are stripped before the mechanic key.
_CARRIER = {"close", "open", "vwap", "high", "low", "volume", "returns", "cap", "adv20", "true"}
_OPS = {"signed_power", "zscore", "ts_decay_linear", "add", "subtract", "multiply", "divide",
        "rank", "ts_delta", "ts_backfill", "ts_zscore", "ts_av_diff", "vec_avg", "sqrt", "filter",
        "ts_mean", "ts_std_dev", "group_neutralize", "winsorize", "scale", "log", "abs",
        "ts_rank", "ts_sum", "if_else", "ts_corr", "ts_regression", "power", "sign", "reverse",
        "ts_max", "ts_min", "ts_product", "densify", "trade_when", "hump", "quantile"}

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")

# The 16 pyramid categories live on USA:1 (state/pyramid_cell_counts.json, endpoint
# /users/self/activities/pyramid-alphas). Used only to READ a cell name out of the ledger's free
# text; the authoritative membership verdict is cell_map.cells_for(), not this.
CATEGORIES = ("Analyst", "Broker", "Earnings", "Fundamental", "Imbalance", "Insiders",
              "Institutions", "Macro", "Model", "News", "Option", "Other", "Price Volume",
              "Risk", "Sentiment", "Short Interest", "Social Media")


# ------------------------------------------------------------------ evidence

def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def _read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def mechanic_of(formula, dataset=""):
    """Identity of the SIGNAL, as the set of non-carrier data fields it reads.

    Two alphas that read the same fields are one mechanic even when their decay, power or weights
    differ: 6XppexRK and mL55V97K differ only in ts_decay_linear(...,20) vs (...,5) and are the
    same insd3_form4 breadth-vs-size signal. Falls back to the dataset label when no formula was
    logged, and returns "" when neither exists -- an unknown mechanic must not collide with
    another unknown mechanic."""
    fields = sorted({t for t in _TOKEN.findall(formula or "")
                     if t not in _OPS and t not in _CARRIER and not t.isdigit()})
    if fields:
        return "+".join(fields)
    d = (dataset or "").strip()
    return d if "(" not in d else ""


def family_of(mechanic):
    """Coarser grouping: the dataset prefix shared by a mechanic's fields.

    `insd3_form4_bvol` and `insd3_form4_bnum` are one family `insd3_form4`. Reported, never used to
    refuse: the family/mechanic distinction is not calibrated by any experiment here."""
    fams = set()
    for f in (mechanic or "").split("+"):
        parts = f.split("_")
        fams.add("_".join(parts[:2]) if len(parts) > 2 else f)
    return "+".join(sorted(x for x in fams if x))


def cells_claimed(category, dataset):
    """Cell names NAMED BY THE LEDGER in either free-text column, as a set.

    The winners ledger puts the cell in different columns depending on which loop wrote the row:
    the 2026-08-10 gen2 batch put "Insiders" in `category`, while the 2026-08-01 funnel rows put
    "News/News Sentiment" in `dataset` and an iteration code ("PX51527r02") in `category`. Exact
    equality on one column silently hides E5ejp6JL, a measured-clean News candidate.

    `category` WINS when it names a category at all, and `dataset` is read only as a fallback,
    because the dataset column also carries free-text hypothesis names: QPGG7gn5's dataset reads
    "H5_news_tone_imbalance", which claims News and Imbalance by pure string accident while its
    category column says Sentiment. Scanning both columns together put one Sentiment alpha into
    three cells' shortlists.

    This is a LEDGER LABEL and explicitly weaker than a platform verdict. submit_plan.py re-checks
    every ranked row against cell_map.cells_for() and drops it if the platform disagrees; that
    check is the one that decides, and this one only decides who gets looked at."""
    def scan(text):
        flat = (text or "").replace("/", " ").replace("+", " ").lower().replace(" ", "")
        return {c for c in CATEGORIES if c.lower().replace(" ", "") in flat}
    return scan(category) or scan(dataset)


def spent_ids():
    """Alphas already POSTed. A second POST buys nothing and 403s."""
    out = set()
    for p in LIVE_IDS:
        v = _read_json(p, [])
        if isinstance(v, list):
            out.update(v)
    for path in (SUBMIT_LOG, SUBMITTED_CELLS):
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if path is SUBMITTED_CELLS or d.get("ok") is True or d.get("status") == 403:
                if d.get("alpha"):
                    out.add(d["alpha"])
    return out


def load_evidence():
    """{alpha_id: record} from the winners ledger, joined to the LATEST correlation measurement.

    winners.csv's own prod_max/self_corr columns are NOT trusted: 6 of the 111 rows carrying both
    are stale on the clean side of 0.70 (see DRIFT above), and the 2026-08-10 gen2 batch wrote a
    per-BATCH self value into the per-alpha column -- 1Yppwox6 reads 0.733 there while its measured
    self_maxcorr is 0.4013. The measurement files win; the CSV number is kept only as `csv_prod`
    so the disagreement stays visible."""
    prod = _read_json(PROD_MEASURED, {})
    fallback = {}
    try:
        for line in CORR_RESULTS.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("alpha"):
                fallback[d["alpha"]] = {"prod_maxcorr": d.get("prod_max"),
                                        "self_maxcorr": d.get("self")}
    except OSError:
        pass

    spent = spent_ids()
    out = {}
    try:
        rows = list(csv.DictReader(open(WINNERS)))
    except OSError:
        return out
    for r in rows:
        aid = (r.get("alpha") or "").strip()
        if not aid:
            continue
        m = prod.get(aid) or fallback.get(aid) or {}
        mech = mechanic_of(r.get("formula", ""), r.get("dataset", ""))
        out[aid] = {
            "alpha": aid,
            "cells": cells_claimed(r.get("category"), r.get("dataset")),
            "dataset": (r.get("dataset") or "").strip(),
            "status": (r.get("status") or "").strip(),
            "sharpe": _num(r.get("sharpe")),
            "fitness": _num(r.get("fitness")),
            "turnover": _num(r.get("turnover")),
            "prod": _num(m.get("prod_maxcorr")),
            "self": _num(m.get("self_maxcorr")),
            "breach": m.get("prod_breach_count"),
            "csv_prod": _num(r.get("prod_max")),
            "mechanic": mech,
            "family": family_of(mech),
            "spent": aid in spent,
        }
    return out


# ------------------------------------------------------------------ verdict + order

def verdict(rec, claimed_mechanics=()):
    """(code, human reason). Only RANKABLE may be spent."""
    if rec.get("spent"):
        return SPENT, "already POSTed — a second POST 403s and adjudicates nothing new"
    mech = rec.get("mechanic")
    if mech and mech in claimed_mechanics:
        return (MECHANIC_DUP,
                f"mechanic already claimed by {claimed_mechanics[mech]} in this plan — one submit "
                "adjudicates the family, the second buys no cell")
    p, s = rec.get("prod"), rec.get("self")
    if p is None:
        return (PROD_MISSING,
                "no measured prod verdict — absent is not clean; 2 GETs (~52s of correlation "
                "channel at the measured 69.8/hour) would decide it")
    if s is None:
        return SELF_MISSING, "no measured self verdict — absent is not clean"
    if s >= SELF_LIMIT:
        return SELF_FAIL, f"self {s:.4f} >= {SELF_LIMIT}"
    if p >= PROD_LIMIT:
        return PROD_FAIL, f"prod {p:.4f} >= {PROD_LIMIT} (platform rejected 3qeeOxlQ at 0.7031)"
    return RANKABLE, f"prod {p:.4f} / self {s:.4f}"


def prod_band(p):
    """0 = two observed drift steps clear of the limit, 1 = one step, 2 = inside one step."""
    if p < PROD_LIMIT - 2 * DRIFT:
        return 0
    if p < PROD_LIMIT - DRIFT:
        return 1
    return 2


def sort_key(rec, novel_families=()):
    """Lexicographic: prod band, then self band, then strength, then mechanic novelty.

    Strength is (turnover under 30%, Sharpe) because SUBMISSION_GATES.md test #5 -- the one that
    makes a correlation conditional rather than fatal -- only engages above 30% turnover. That is
    read off the documented test table (EX-ANTE); no experiment here measured the size of the
    effect."""
    p, s = rec["prod"], rec["self"]
    return (prod_band(p),
            0 if s < SELF_CLEAR else 1,
            0 if (rec.get("turnover") or 1.0) < LOW_TURNOVER else 1,
            -(rec.get("sharpe") or 0.0),
            0 if rec.get("family") in novel_families else 1,
            p, s, rec["alpha"])


def rank(cell, candidates=None, *, evidence=None, claimed_mechanics=None):
    """Full ranking for one cell: (ranked_records, refusals).

    `candidates` is a list of alpha ids, or None for "everything in the ledger whose category is
    this cell". Refusals are returned, never silently dropped, and never sorted into the order."""
    ev = evidence if evidence is not None else load_evidence()
    claimed = dict(claimed_mechanics or {})
    if candidates is None:
        pool = [r for r in ev.values() if cell in r["cells"]]
    else:
        pool = [ev[a] for a in candidates if a in ev and cell in ev[a]["cells"]]

    live_fams = {r["family"] for r in ev.values() if r.get("spent") and r.get("family")}
    novel = {r["family"] for r in pool if r["family"] and r["family"] not in live_fams}

    ranked, refused = [], []
    for rec in pool:
        code, why = verdict(rec, claimed)
        if code == RANKABLE:
            ranked.append(rec)
        else:
            refused.append((rec, code, why))
    ranked.sort(key=lambda r: sort_key(r, novel))

    # De-dup WITHIN the cell too: two variants of one mechanic in one shortlist would let the
    # driver spend the second on the same signal if the first is withheld for any other reason.
    kept, seen = [], {}
    for rec in ranked:
        m = rec["mechanic"]
        if m and m in seen:
            refused.append((rec, MECHANIC_DUP,
                            f"same mechanic as {seen[m]}, ranked above it"))
            continue
        seen[m] = rec["alpha"]
        kept.append(rec)
    return kept, refused


def rank_for_cell(cell, candidates):
    """submit_plan.py contract: ids only, best first, refused ids absent."""
    kept, _ = rank(cell, list(candidates))
    return [r["alpha"] for r in kept]


def plan_shortlists(needs, evidence=None):
    """Shortlists for several cells at once, with mechanic de-dup ACROSS the plan.

    `needs` is {cell: submits_still_required}. Cells are served in ascending need so the cell
    closest to unlocking claims a contested mechanic first -- an ordering choice, not a
    measurement. Returns {cell: {"take": [...], "refused": [...], "short": n}}."""
    ev = evidence if evidence is not None else load_evidence()
    claimed, out = {}, {}
    for cell in sorted(needs, key=lambda c: (needs[c], c)):
        kept, refused = rank(cell, evidence=ev, claimed_mechanics=claimed)
        take = kept[: needs[cell]]
        for rec in take:
            if rec["mechanic"]:
                claimed[rec["mechanic"]] = rec["alpha"]
        out[cell] = {"take": take, "refused": refused + [(r, MECHANIC_DUP, "beyond cell need")
                                                         for r in kept[needs[cell]:]],
                     "short": max(0, needs[cell] - len(take))}
    return out


# ------------------------------------------------------------------ report

def _backlog_state():
    """(backlog size, how many of it now carry a prod number). (0, 0) if the file is absent."""
    bl = _read_json(ROOT / "state/prod_backlog.json", [])
    if not isinstance(bl, list) or not bl:
        return 0, 0
    prod = _read_json(PROD_MEASURED, {})
    have = {k for k, v in prod.items() if (v or {}).get("prod_maxcorr") is not None}
    try:
        for line in CORR_RESULTS.read_text().splitlines():
            try:
                have.add(json.loads(line)["alpha"])
            except (ValueError, KeyError):
                pass
    except OSError:
        pass
    return len(bl), len(set(bl) & have)


def explain(needs, evidence=None):
    ev = evidence if evidence is not None else load_evidence()
    plan = plan_shortlists(needs, ev)
    lines = ["submit_rank — USA delay 1. READ-ONLY; nothing here can POST.", ""]
    unmeasured = [r for r in ev.values() if r["prod"] is None and not r["spent"]]
    lines.append(f"ledger {len(ev)} alphas | {len(unmeasured)} carry NO prod verdict "
                 f"({100.0 * len(unmeasured) / max(1, len(ev)):.1f}%) and are UNRANKABLE: "
                 + (", ".join(r["alpha"] for r in unmeasured) or "none"))
    back, done = _backlog_state()
    if back:
        lines.append(f"beyond the ledger: {back - done} of {back} alphas in "
                     f"state/prod_backlog.json still have no prod number "
                     f"({100.0 * (back - done) / back:.1f}%) = {(back - done) / 69.8:.1f}h of "
                     "correlation channel to clear, at 2 GETs and ~52s per alpha")
    lines.append("")
    lines.append("WHAT THIS RANKING CANNOT KNOW: there is no offline surrogate for PROD "
                 "correlation — the production book is other users' alphas and is not on disk. "
                 "tools/funnel/corr_rank.py predicts SELF only, and 8.0% of its 'clean' calls are "
                 "true breaches, so it ranks and never gates. Every prod number below is a stored "
                 "reading of UNKNOWN AGE (no per-entry timestamp exists), and 6 of 111 such "
                 "readings moved from clean to dirty on re-measurement, 0 the other way.")
    for cell in sorted(plan):
        d = plan[cell]
        lines.append("")
        lines.append(f"== {cell}: needs {needs[cell]}, shortlist {len(d['take'])}"
                     + (f", SHORT BY {d['short']}" if d["short"] else ""))
        if not d["take"]:
            lines.append("   EMPTY — no candidate qualifies. That is a finding, not a failure.")
        for i, r in enumerate(d["take"], 1):
            lines.append(f"   {i}. {r['alpha']}  prod {r['prod']:.4f} (band {prod_band(r['prod'])})"
                         f"  self {r['self']:.4f}  sharpe {r['sharpe']}  turnover {r['turnover']}"
                         f"  mech {r['mechanic'][:60]}")
        for rec, code, why in d["refused"]:
            lines.append(f"   REFUSED {rec['alpha']} [{code}] {why}")
    return "\n".join(lines)


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    needs = {"News": 1, "Insiders": 1, "Sentiment": 2,
             "Social Media": 3, "Short Interest": 3, "Imbalance": 3}
    ev = load_evidence()
    if "--json" in argv:
        plan = plan_shortlists(needs, ev)
        print(json.dumps({c: {"take": [r["alpha"] for r in d["take"]],
                              "short": d["short"],
                              "refused": [[r["alpha"], code, why] for r, code, why in d["refused"]]}
                          for c, d in plan.items()}, indent=2))
    else:
        print(explain(needs, ev))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
