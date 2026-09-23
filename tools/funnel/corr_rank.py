#!/usr/bin/env python3
"""corr_rank.py — RANK unmeasured gems by a predicted SELF-correlation, offline, zero API calls.

THIS IS A RANKER. IT IS NOT A GATE. Read the two paragraphs below before using a number from it.

WHAT IT IS. The platform's self-correlation for an alpha is the maximum Pearson correlation of its
daily PnL against the user's own ACTIVE alphas. Both halves of that are already on disk — the
active list in state/active_ids.json and the PnL curves in fetched/pnl/*.jsonl and
state/pnl_curves/*.json — so the number can be recomputed here with no request to the platform.
Measured 2026-08-12 against the 375 gems that carry a platform-issued self-correlation
(reproduce with --validate; the numbers below ARE that command's output):

    median |error|            0.0000     (66.9% of predictions land within 0.02 of the platform's)
    gate agreement @0.70      88.8%
    DANGEROUS ERRORS          21 of 263 predicted-clean alphas (8.0%) are truly >= 0.70
    worst single error        0.675       (predicted 0.287, platform said 0.962)

WHAT IT CANNOT DO — the part that decides how much this is worth.

  1. It cannot clear an alpha for submission. 8.0% of its "clean" calls are breaches and the error
     is UNBOUNDED, not a tolerance band. Rank with it; measure before you submit.

  2. It says nothing about PROD correlation, which is the binding half. Measured over 836 gems
     carrying both numbers (2026-08-12): 61.5% pass self<0.70 but only 12.7% pass prod<0.70 — prod
     rejects 4.8x more often, and prod cannot be surrogated at all because the production book is
     other users' alphas and is not on disk.

     Self-corr still buys something, and the amount is measured rather than assumed:
         P(prod clean)                = 12.68%
         P(prod clean | self clean)   = 20.04%     lift 1.58x  (bootstrap 95% CI 1.49-1.68)
         recall: 103 of 106 prod-clean gems (97.2%) also pass self<0.70
     So screening on predicted self-corr discards ~38% of the pool while keeping ~97% of the
     prod-clean alphas in it. That is the whole value proposition: a cheap recall-preserving
     pre-filter, never a verdict.
     MECHANISM: UNKNOWN — prod and self correlate at Pearson 0.47 / Spearman 0.35 across those 836
     gems, and no experiment here separates "both load on a common market factor" from "crowded
     signals are crowded everywhere".

  3. The 12.68% base rate above describes the MEASURED set, which was selected by strength, not at
     random. It is not an estimate for the unmeasured backlog.

BOOK DEFINITION IS EMPIRICAL, and it is narrow. Using state/active_ids.json (227 alphas) as the
book gives 88.7% gate agreement; widening it to every alpha with a curve on disk (5,078) collapses
agreement to 32.3%. So the self book is the ACTIVE list, not everything ever simulated.
MECHANISM: UNKNOWN for the residual 11.2% disagreement — errors are two-sided (11.0% of
predictions overshoot by >0.02, 21.5% undershoot), so a merely incomplete book cannot explain it.

Usage:
    python3 tools/funnel/corr_rank.py                  # rank every unmeasured gem
    python3 tools/funnel/corr_rank.py --top 40
    python3 tools/funnel/corr_rank.py --out /tmp/rank.json
    python3 tools/funnel/corr_rank.py --validate       # re-run the accuracy table above
"""
import argparse
import json
import os
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import gate_lib as G                                                    # noqa: E402

ACTIVE = ROOT / "state/active_ids.json"
JOURNAL = ROOT / "state/resim_results.jsonl"
CURVE_DIRS = [(ROOT / "fetched/pnl", ".jsonl"), (ROOT / "state/pnl_curves", ".json")]
CORR_STORES = [ROOT / "state/prod_corr_measured.json",
               ROOT / "state/funnel/corr_results.jsonl",
               ROOT / "state/winner_correlations.json",
               ROOT / "state/funnel/winners.csv"]

DAYS = 984                    # daily returns; 985 curve points
DANGER_RATE = 0.080           # measured 2026-08-12, n=263 predicted-clean, 21 true breaches
GATE = 0.70                   # 0.7031 was rejected by the platform, so the limit is 0.70


def load_curve(aid):
    """Cumulative PnL as {date: value}, from either curve store. None if absent."""
    p = ROOT / f"fetched/pnl/{aid}.jsonl"
    if p.exists():
        out = {}
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r[0]] = r[1]
        return out or None
    p = ROOT / f"state/pnl_curves/{aid}.json"
    if p.exists():
        try:
            return json.load(open(p)) or None
        except Exception:
            return None
    return None


def have_curve():
    ids = set()
    for d, ext in CURVE_DIRS:
        if d.exists():
            ids |= {f[: -len(ext)] for f in os.listdir(d) if f.endswith(ext)}
    return ids


def date_grid(book_curves, days=DAYS):
    """The last `days`+1 trading dates present in >=90% of the book curves.

    A per-pair date intersection gives the same answers (verified: identical median error, gate
    agreement and dangerous-error count) but is O(n*m) date-set work; one shared grid turns the
    whole job into a single matrix product."""
    seen = {}
    for c in book_curves.values():
        for d in c:
            seen[d] = seen.get(d, 0) + 1
    need = 0.9 * len(book_curves)
    return sorted(d for d, n in seen.items() if n >= need)[-(days + 1):]


def zrows(ids, grid):
    """Standardised daily-PnL rows for the ids that cover the whole grid. (matrix, kept_ids)."""
    rows, keep = [], []
    for a in ids:
        c = load_curve(a)
        if not c:
            continue
        try:
            v = np.array([c[d] for d in grid], float)
        except KeyError:
            continue                              # curve does not span the grid -> not comparable
        r = np.diff(v)
        s = r.std()
        if s == 0:
            continue
        rows.append((r - r.mean()) / s)
        keep.append(a)
    return (np.array(rows) if rows else np.zeros((0, len(grid) - 1))), keep


def predict(cand_ids, book_ids, grid):
    """{alpha: (predicted_self_corr, book_alpha)} — max Pearson against the book, self excluded."""
    B, bk = zrows(book_ids, grid)
    C, ck = zrows(cand_ids, grid)
    if not len(B) or not len(C):
        return {}
    R = C @ B.T / B.shape[1]
    bidx = {a: i for i, a in enumerate(bk)}
    out = {}
    for i, a in enumerate(ck):
        r = R[i].copy()
        if a in bidx:
            r[bidx[a]] = -9.0                     # an alpha is not its own neighbour
        j = int(r.argmax())
        out[a] = (float(r[j]), bk[j])
    return out


def gems():
    """Zero-fail alphas from the journal, keyed by platform alpha id (never old_id)."""
    out = {}
    for line in open(JOURNAL):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("alpha")
        if not a:
            continue
        try:
            if G.gate_status(d).get("zero_fail"):
                out[a] = d
        except Exception:
            continue
    return out


def measured():
    """Alpha ids that already carry a platform self-correlation, from ALL FOUR stores.

    There is not one correlation store in this repo, there are four, and a tool that reads one
    re-measures alphas the others already know about."""
    out = {}
    p = ROOT / "state/prod_corr_measured.json"
    if p.exists():
        for a, v in json.load(open(p)).items():
            if isinstance(v.get("self_maxcorr"), (int, float)):
                out[a] = v["self_maxcorr"]
    p = ROOT / "state/funnel/corr_results.jsonl"
    if p.exists():
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if isinstance(d.get("self"), (int, float)):
                out.setdefault(d["alpha"], d["self"])
    p = ROOT / "state/winner_correlations.json"
    if p.exists():
        for a, v in json.load(open(p)).items():
            if isinstance(v.get("self_maxcorr"), (int, float)):
                out.setdefault(a, v["self_maxcorr"])
    p = ROOT / "state/funnel/winners.csv"
    if p.exists():
        import csv
        for r in csv.DictReader(open(p)):
            try:
                out.setdefault(r["alpha"], float(r["self_corr"]))
            except (KeyError, TypeError, ValueError):
                pass
    return out


BANNER = (
    "RANKER, NOT A GATE. {danger:.1%} of predicted-clean calls are real breaches (21/263 measured\n"
    "2026-08-12) and the error is unbounded. Self-corr is also the LESS binding half: 61.5% of\n"
    "measured gems pass self<0.70, only 12.7% pass prod<0.70, and prod has NO offline surrogate.\n"
    "Ranking here raises P(prod clean) from 12.68% to 20.04% (1.58x) while keeping 97.2% of the\n"
    "prod-clean alphas. Measure before submitting. Always."
).format(danger=DANGER_RATE)


def cmd_rank(args):
    gem = gems()
    done = measured()
    curves = have_curve()
    book = [a for a in json.load(open(ACTIVE)) if a in curves]
    todo = [a for a in gem if a not in done and a in curves]
    print(BANNER + "\n")
    print(f"zero-fail gems {len(gem)}   already measured {len([a for a in gem if a in done])}"
          f"   unmeasured {len([a for a in gem if a not in done])}"
          f"   of those with a PnL curve {len(todo)}")
    grid = date_grid({a: load_curve(a) for a in book}, args.days)
    print(f"book {len(book)} active alphas   grid {len(grid)} dates  {grid[0]} .. {grid[-1]}\n")
    pred = predict(todo, book, grid)
    rows = sorted(pred.items(), key=lambda kv: kv[1][0])
    clean = [a for a, (p, _) in rows if p < GATE]
    print(f"ranked {len(rows)}   predicted self<{GATE}: {len(clean)} ({len(clean)/max(len(rows),1):.1%})"
          f"   expected true breaches among them ~{round(len(clean)*DANGER_RATE)}\n")
    print(f"{'rank':>5} {'alpha':10} {'pred_self':>10} {'nearest_book':12} {'sharpe':>7} {'fitness':>8}")
    for i, (a, (p, b)) in enumerate(rows[: args.top], 1):
        d = gem[a]
        print(f"{i:5} {a:10} {p:10.4f} {b:12} {d.get('sharpe', ''):>7} {d.get('fitness', ''):>8}")
    if args.out:
        json.dump({a: {"pred_self_corr": round(p, 4), "nearest_book_alpha": b,
                       "IS_A_RANK_NOT_A_GATE": True, "dangerous_clean_rate": DANGER_RATE}
                   for a, (p, b) in rows}, open(args.out, "w"), indent=1)
        print(f"\nwrote {args.out}  ({len(rows)} rows)")
    return 0


def cmd_validate(args):
    """Re-derive the accuracy table in the docstring against platform-issued self-corrs."""
    import statistics as st
    done = measured()
    gem = gems()
    curves = have_curve()
    book = [a for a in json.load(open(ACTIVE)) if a in curves]
    grid = date_grid({a: load_curve(a) for a in book}, args.days)
    lab = [a for a in done if a in gem and a in curves]
    pred = predict(lab, book, grid)
    err = [pred[a][0] - done[a] for a in pred]
    n = len(pred)
    agree = sum(1 for a in pred if (pred[a][0] < GATE) == (done[a] < GATE)) / n
    pc = [a for a in pred if pred[a][0] < GATE]
    dang = [a for a in pc if done[a] >= GATE]
    print(f"labelled gems with a curve: {n}   book {len(book)}   grid {len(grid)} dates")
    print(f"  median error            {st.median(err):+.4f}")
    print(f"  median |error|          {st.median([abs(e) for e in err]):.4f}")
    print(f"  within 0.02             {sum(1 for e in err if abs(e) <= 0.02)/n:.1%}")
    print(f"  worst |error|           {max(abs(e) for e in err):.4f}")
    print(f"  gate agreement @{GATE}   {agree:.1%}")
    print(f"  DANGEROUS (pred clean, truly dirty)  {len(dang)}/{len(pc)} ({len(dang)/max(len(pc),1):.1%})")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Offline SELF-correlation ranker. Not a gate.")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--days", type=int, default=DAYS)
    ap.add_argument("--out", default="")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    return cmd_validate(args) if args.validate else cmd_rank(args)


if __name__ == "__main__":
    raise SystemExit(main())
