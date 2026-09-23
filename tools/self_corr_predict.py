#!/usr/bin/env python3
"""Predict self-correlation between two alphas from their PnL curves alone — no submit needed.

Why this exists: submitting an alpha raises every sibling's correlation to ~self-corr, so the
number of SUBMITTABLE alphas equals the number of distinct signal families, not the number of
gate-passers. Until now that was only discoverable AFTER spending an irreversible submit. The
platform does publish pairwise self-correlations, but only against alphas already in the book.

Validated 2026-07-31 on 175 platform-labelled pairs (self-corr 0.235-0.987):

    Khoa's hypothesis, sum|cumA(t)-cumB(t)|      Spearman -0.290   right sign, weak
    ...same on daily PnL, each scaled by its sd  Spearman -0.890   near-deterministic
    pearson(daily PnL)                           Spearman +0.934

The raw cumulative form is weak because the API's curve is CUMULATIVE and therefore carries the
alpha's scale: two alphas booking very different totals sit far apart in L1 however closely they
move together. Removing scale is what makes the relationship sharp.

On the FULL history plain daily Pearson sits a uniform -0.05 below the platform's number, and that
offset was calibrated out with `0.0662 + 0.9675 * pearson`, held-out max |err| 0.087.

**Superseded 2026-08-03.** The offset was not a property of Pearson needing calibration; it was the
wrong window. Correlating over the last 984 trading days instead of all 2493 removes it entirely
and no calibration is needed: max |err| 4.9e-5 over 136 labelled pairs, 136/136 at the 0.7 gate.
Details, the window sweep, and what remains UNDECIDABLE about the window are in predict().

LIMIT 1 -- a FROZEN curve, not merely a short one. The five worst errors in the original study
(~0.54) all involved `Vk2p1aew`, whose 1236 days include 1200 with zero PnL change; 38 cached
curves carry >600 unchanged days after 2020. Correlating against a near-constant series is
meaningless and predict() now refuses it explicitly rather than relying on MIN_DAYS to catch it.

LIMIT 2 -- this reproduces a PAIRWISE number. The platform's per-alpha `self_corr` is the MAX over
the whole ACTIVE book, which on 2026-08-03 held **231** alphas while `state/submit_budget.jsonl`
listed 38. Taking a max over the local ledger answers a different question and gave median |err|
0.053 with 10 missed breaches; for "will this alpha pass the self-corr gate", read the platform.

Usage: python3 tools/self_corr_predict.py <alphaA> <alphaB> [<alphaC> ...]
       (with 3+ ids it prints the full pairwise matrix)
"""
import itertools, json, math, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "autoloop"))

API = "https://api.worldquantbrain.com"
CACHE = ROOT / "state/pnl_curves"
WINDOW_DAYS = 984        # the window the platform correlates over -- swept, not assumed; see predict()
MIN_DAYS = 900           # a shorter common window than this cannot fill WINDOW_DAYS


def _session():
    import driver as D
    return D.session()


def pnl(s, aid, budget=90.0):
    """{date: cumulative_pnl}, cached — a finished curve never changes.

    The recordset endpoint answers 200 with an EMPTY body while it is still computing, so an
    empty response is not an error and must not be cached as one."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{aid}.json"
    if f.exists():
        try:
            return json.load(open(f))
        except Exception:
            pass
    t0 = time.time()
    while time.time() - t0 < budget:
        try:
            r = s.get(f"{API}/alphas/{aid}/recordsets/pnl", timeout=30)
        except Exception:
            time.sleep(3)
            continue
        try:
            ra = float(r.headers.get("Retry-After") or 0) or None
        except ValueError:
            ra = None
        if r.status_code == 429:
            time.sleep(min(ra or 15, 30))
            continue
        if r.status_code != 200:
            return None
        if r.text:
            try:
                j = r.json()
            except Exception:
                return None
            if isinstance(j, dict) and j.get("records"):
                cols = [p["name"] for p in j["schema"]["properties"]]
                di, pi = cols.index("date"), cols.index("pnl")
                out = {rec[di]: rec[pi] for rec in j["records"]}
                json.dump(out, open(f, "w"))
                return out
        time.sleep(min(ra or 2, 5))
    return None


def _pearson(x, y):
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def predict(curve_a, curve_b):
    """-> (self_corr, n_days_used) or (None, n) when the curves cannot support a number.

    NOT a prediction any more -- a reproduction, on the data measured so far.

    MEASURED 2026-08-03. Sweeping the correlation window against platform-labelled pairs, the error
    collapses at ONE window length and nowhere else:

        window          max |err| vs the platform's published number
        2493 days       0.047        <- what this file used to do
        1000 days       0.0115
        984 days        0.00005
        965 days        0.0029

    At N=984, plain Pearson with no calibration at all reproduces the platform to max |err| 4.9e-5
    over 136 labelled pairs, 136/136 correct at the 0.7 gate -- below the 4-decimal precision the
    platform reports at. Held out on 66 pairs from 14 alphas not used to find the window: median
    2.3e-5. If the platform were not using a ~984-day window, no N would produce that collapse.

    What used to be here was `0.0662 + 0.9675 * pearson(FULL history)`, max |err| 4.1e-2. Refitting
    that slope on fresh pairs returns 0.9903 and a pure constant offset scores identically, so the
    slope was never carrying information -- the same finding from the other side.

    WHAT THE WINDOW ACTUALLY IS: **UNDECIDABLE on available data.** N=984 trading days back lands on
    2020-01-02, so "the last 984 trading days", "everything from 2020-01-01", and "the last 4
    calendar years" select an IDENTICAL set of days here. All 1,279 cached curves end on 2023-12-29
    (two start dates, one end date), so nothing separates them. This implements the COUNT, because
    the count is what the sweep measured; the date reading was an inference and is not used.

    THE EXPERIMENT THAT WOULD SEPARATE THEM: simulate one alpha with a different `endDate` (e.g.
    2022-12-31) and read its published self-correlation. Count predicts a window opening ~2019-01;
    a fixed 2020-01-01 start predicts ~750 days; 4-calendar-years predicts ~1008. One sim."""
    days = sorted(set(curve_a) & set(curve_b))[-WINDOW_DAYS:]
    if len(days) < MIN_DAYS:
        return None, len(days)
    A = [curve_a[d] for d in days]
    B = [curve_b[d] for d in days]
    dA = [A[i] - A[i - 1] for i in range(1, len(A))]
    dB = [B[i] - B[i - 1] for i in range(1, len(B))]
    # A FROZEN curve is not a short curve, and MIN_DAYS only caught these by accident. Vk2p1aew
    # holds 1236 days of which 1200 have zero PnL change; correlating against a near-constant
    # series produced the five worst errors in the whole study (~0.54 each) and every one of them
    # involved that single alpha. 38 cached curves carry more than 600 unchanged days after 2020.
    for d in (dA, dB):
        if sum(1 for v in d if v == 0) > 0.2 * len(d):
            return None, len(days)
    p = _pearson(dA, dB)
    if p is None:
        return None, len(days)
    return round(max(-1.0, min(1.0, p)), 4), len(days)


def main(ids):
    s = _session()
    curves = {}
    for a in ids:
        c = pnl(s, a)
        if not c:
            print(f"  {a}: PnL unavailable")
        else:
            curves[a] = c
    ok = [a for a in ids if a in curves]
    print(f"{'A':10} {'B':10} {'pred self-corr':>14} {'days':>6}")
    for a, b in itertools.combinations(ok, 2):
        v, n = predict(curves[a], curves[b])
        flag = "" if v is None else ("  <-- >=0.7, same family" if v >= 0.7 else "")
        print(f"{a:10} {b:10} {('n/a' if v is None else f'{v:.4f}'):>14} {n:6}{flag}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip().splitlines()[-2].strip())
    main(sys.argv[1:])
