"""Probability of Backtest Overfitting by combinatorially symmetric cross-validation (CSCV).

Bailey, Borwein, López de Prado & Zhu, "The Probability of Backtest Overfitting", J. Computational
Finance 2017 (SSRN 2326253). Agreed as the second OOS-proxy (Khoa 2026-09-08, Q21/Q30): pool = the
DSR pool (hypothesis × region/delay × category, cumulative), S = 16 blocks, PBO ≤ 0.5 to submit.

Algorithm (the paper's, verbatim in structure):
  1. M: T × N matrix of daily PnL (or returns) of the N trials in the pool, dates aligned.
  2. Split the T rows into S contiguous blocks of equal length; for every choice of S/2 blocks as
     the in-sample set J (the remaining S/2 are the out-of-sample set J̄) — C(S, S/2) = 12,870 for
     S = 16 — compute the performance (annualised Sharpe) of every trial IS and OOS.
  3. n* = argmax IS performance; ω̄ = rank of n* among the OOS performances, as a fraction in (0, 1);
     logit λ = ln(ω̄ / (1 − ω̄)).
  4. PBO = share of splits with λ < 0 (the IS-best trial is below the OOS median).

Caveats the paper states: trials should be comparable (same asset universe / period); CSCV assumes
the block structure preserves the dependence; with N small the OOS rank is coarse — we refuse to
judge pools with N < MIN_TRIALS and report "insufficient".
"""
from __future__ import annotations

import itertools
import math

MIN_TRIALS = 20         # the paper says "N >> 10" (Researcher C, 2026-09-08); below this the OOS rank is too coarse
S_DEFAULT = 16
ANNUALISE = math.sqrt(252.0)


def _sharpe(xs) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return (m / math.sqrt(v)) * ANNUALISE if v > 0 else 0.0


def align(curves: dict, min_obs: int = 250, min_cover: float = 0.9) -> tuple:
    """{trial: {date: daily_pnl}} -> (dates, matrix rows-by-date, trial ids kept).
    The date set is the MODAL one (the dates most members share); a member covering less than
    `min_cover` of it is DROPPED rather than allowed to truncate the pool (Researcher C spec)."""
    ids = [k for k, v in curves.items() if v]
    if not ids:
        return [], [], []
    import collections
    count = collections.Counter(d for k in ids for d in curves[k])
    n = len(ids)
    modal = sorted(d for d, c in count.items() if 2 * c >= n)             # dates at least half the pool has (odd N: the majority)
    keep = [k for k in ids if modal and sum(1 for d in modal if d in curves[k]) >= min_cover * len(modal)]
    if not keep:
        return modal, [], []
    common = set(modal)
    for k in keep:
        common &= set(curves[k])
    dates = sorted(common)
    if len(dates) < min_obs:
        return dates, [], keep
    rows = [[curves[k][d] for k in keep] for d in dates]
    return dates, rows, keep


def pbo(rows: list, s: int = S_DEFAULT, max_splits: int | None = None) -> dict:
    """rows: T lists of N daily PnL values (aligned). Returns {"pbo", "n_trials", "splits", "status"}."""
    if not rows:
        return {"pbo": None, "n_trials": 0, "splits": 0, "status": "empty"}
    n = len(rows[0])
    t = len(rows)
    if n < MIN_TRIALS:
        return {"pbo": None, "n_trials": n, "splits": 0, "status": "insufficient (< %d trials)" % MIN_TRIALS}
    if t < s * 10:
        return {"pbo": None, "n_trials": n, "splits": 0, "status": "too short (< %d rows)" % (s * 10)}
    size = t // s
    start = t - size * s                     # the remainder is the OLDEST rows; the newest are kept
    blocks = [rows[start + i * size:start + (i + 1) * size] for i in range(s)]
    # per-block sufficient statistics: sum and sum of squares per trial, so a split's Sharpe is a sum
    stats = []
    for b in blocks:
        sm = [0.0] * n
        sq = [0.0] * n
        for r in b:
            for j, x in enumerate(r):
                sm[j] += x
                sq[j] += x * x
        stats.append((len(b), sm, sq))

    def sharpes(idx) -> list:
        cnt = sum(stats[i][0] for i in idx)
        out = []
        for j in range(n):
            tot = sum(stats[i][1][j] for i in idx)
            tot2 = sum(stats[i][2][j] for i in idx)
            m = tot / cnt
            v = (tot2 - cnt * m * m) / (cnt - 1) if cnt > 1 else 0.0
            out.append((m / math.sqrt(v)) * ANNUALISE if v > 1e-18 else 0.0)
        return out

    combos = itertools.combinations(range(s), s // 2)
    below, total = 0, 0
    for k, js in enumerate(combos):
        if max_splits is not None and k >= max_splits:
            break
        jbar = [i for i in range(s) if i not in js]
        is_ = sharpes(js)
        oos = sharpes(jbar)
        best = max(range(n), key=lambda j: is_[j])
        # OOS rank of the IS-best trial as a fraction in (0, 1); ties share the lower rank
        rank = sum(1 for j in range(n) if oos[j] < oos[best]) + 1
        w = rank / (n + 1.0)
        lam = math.log(w / (1.0 - w))
        below += lam < 0
        total += 1
    return {"pbo": below / total if total else None, "n_trials": n, "splits": total, "status": "ok"}


def evaluate(curves: dict, s: int = S_DEFAULT, threshold: float = 0.5) -> dict:
    dates, rows, ids = align(curves)
    r = pbo(rows, s)
    r.update({"dates": len(dates), "ids": ids, "threshold": threshold,
              "pass": (r["pbo"] is not None and r["pbo"] <= threshold)})
    return r
