#!/usr/bin/env python3
"""fetch_prod_corr.py — MEASURE prod (and self) correlation for simmed alphas. Khoa 2026-07-21:
prod-corr must be FETCHED after every sim, never assumed from field choice — a "low-OHLCV"
alpha can still have PnL that correlates ~0.9 with the production book. Gate: max corr < 0.7.

Usage: python3 tools/fetch_prod_corr.py <alpha_id> [<alpha_id> ...]
The prod endpoint returns a HISTOGRAM of |corr| vs all production alphas; the alpha's max
prod-corr = the highest bucket that still holds production alphas. self returns the user's own
most-correlated alphas (max of the 'correlation' column). Async: retry on Retry-After.
"""
import pickle, requests, json, time, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

def session():
    c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
    s = requests.Session()
    if isinstance(c, dict): s.cookies.update(c)
    else:
        for x in c: s.cookies.set_cookie(x)
    return s

def _fetch(s, aid, kind, budget_s=420):
    """Poll until the platform finishes computing, bounded by TIME not iteration count.

    The endpoint answers 200 + `Retry-After: 1.0` + empty body while it computes. The old loop
    gave up after 40 iterations (~40-120s), which is enough when the account is idle but not
    while a 180-sim sweep is running: every correlation read during deep_mine returned None,
    including QP99gYLM's — an alpha that is already LIVE and had measured cleanly hours before.
    Those Nones read downstream as "not measurable", so the strongest candidates of the sweep were
    silently written off. A wall-clock budget keeps polling as long as the server keeps asking."""
    deadline = time.time() + budget_s
    while time.time() < deadline:
        r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/correlations/{kind}", timeout=60)
        if r.headers.get("Retry-After"):
            time.sleep(min(float(r.headers["Retry-After"]), 3)); continue
        if r.status_code == 200 and not r.text:          # 200-empty = still computing async
            time.sleep(2); continue
        if r.status_code == 200 and r.text: return r.json()
        if r.status_code == 429:
            # RATE LIMIT, not "no data". Returning None here made a throttled read indistinguishable
            # from an unmeasurable alpha, so a 180-sim sweep running alongside the measurement wrote
            # off its own strongest candidates as unmeasured. Back off and keep trying.
            time.sleep(min(float(r.headers.get("Retry-After", 30)), 60))
            continue
        return None
    return None

def prod_maxcorr(j):
    """EXACT max prod correlation (the platform's PROD_CORRELATION value) + the count of prod
    alphas in buckets above 0.7.

    The prod payload is a HISTOGRAM — its schema is [min, max, alphas] with 0.1-wide buckets —
    and it carries the true extremes at the TOP level as j['max'] / j['min']. The old code
    returned the highest non-empty BUCKET EDGE, so every reading was quantised to 0.7/0.8/0.9/1.0
    and the real number was invisible. Verified against the platform: 3qeeOxlQ's rejection said
    `PROD_CORRELATION value=0.7031 limit=0.7`, and j['max'] for it is exactly 0.7031, while the
    bucket edge said 0.8. The gate is on this single number, not on the bucket or on any count."""
    # A 200 can carry a JSON body that is not a correlation payload at all — e.g.
    # {"message": "API rate limit exceeded"}. Indexing j["schema"] on that raises KeyError and
    # takes down the caller mid-batch, so an unexpected shape must read as UNMEASURED, not crash.
    if not isinstance(j, dict) or "schema" not in j or "properties" not in (j.get("schema") or {}):
        return None, None
    props = [p["name"] for p in j["schema"]["properties"]]; idx = {p: i for i, p in enumerate(props)}
    breach = 0
    for row in j.get("records", []):
        a = row[idx["alphas"]]
        if a and a > 0 and row[idx["max"]] > 0.7:
            breach += a
    return j.get("max"), breach

def self_maxcorr(j):
    if not isinstance(j, dict) or "schema" not in j: return None
    if not j.get("records"): return None      # schema present but no rows = NOT measured (still computing)
    props = [p["name"] for p in j["schema"]["properties"]]; ci = props.index("correlation") if "correlation" in props else None
    if ci is None: return None
    vals = [row[ci] for row in j.get("records", []) if row[ci] is not None]
    return max(vals) if vals else None

def measure(aids):
    s = session(); out = {}
    print(f"{'alpha':11}{'prodCorr':10}{'>0.7 count':11}{'selfCorr':10}{'submittable(<0.7)':18}")
    for aid in aids:
        # A freshly-simmed alpha returns 200 with `records: []` while the platform is still
        # computing its correlations. _fetch only retries a 200 with an EMPTY BODY, so that case
        # fell through as "not measured" — and 10 of deep_mine's 14 zero-fails (including every
        # one of the strongest) read as unknown right after their sweep. Unknown is not walled:
        # retry a few times before giving up, then still fail closed.
        for attempt in range(4):
            prod_j, self_j = _fetch(s, aid, "prod"), _fetch(s, aid, "self")
            if (prod_j or {}).get("records") and (self_j or {}).get("records") is not None:
                break
            if attempt < 3:
                time.sleep(15 * (attempt + 1))
        pc, breach = prod_maxcorr(prod_j)
        sc = self_maxcorr(self_j)
        # self is MEASURED only if the fetch returned rows; None = fetch error, records==[] = async
        # still-computing. Both are fail-closed (mirror the canonical measure_corr_incremental guard),
        # so an unmeasured self-corr can't slip through as a false self<0.7 PASS (B10 O6).
        # MEASURED means self_maxcorr returned a NUMBER, not merely that rows came back.
        # self_maxcorr() also returns None on a payload with records but no `correlation`
        # column, or with every value null -- and every consumer then reads `sc is None` as
        # "no conflict". Records-present was the shared root of that hole across five files.
        self_measured = self_j is not None and bool(self_j.get("records")) and sc is not None
        ok = (pc is not None and breach == 0 and self_measured and (sc is None or sc < 0.7))
        out[aid] = {"prod_maxcorr": pc, "prod_breach_count": breach, "self_maxcorr": sc,
                    "self_measured": self_measured, "corr_ok": ok}
        reason = 'YES' if ok else ('NO — self not measured (fetch/empty)' if not self_measured else 'NO — corr>0.7')
        print(f"{aid:11}{str(round(pc,3) if pc is not None else pc):10}{str(breach):11}"
              f"{str(round(sc,3) if sc is not None else sc):10}{reason}")
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: fetch_prod_corr.py <alpha_id> ..."); sys.exit(1)
    res = measure(sys.argv[1:])
    # MERGE, don't overwrite: a later run measuring 3 alphas used to wipe the other 90 measured
    # earlier in the same sweep, so their rows could never be logged to the winner/near-miss ledgers.
    out = ROOT / "state/prod_corr_measured.json"
    prev = {}
    if out.exists():
        try: prev = json.load(open(out))
        except Exception: prev = {}
    prev.update(res)
    json.dump(prev, open(out, "w"), indent=1)
    print(f"\nsaved -> state/prod_corr_measured.json ({len(res)} updated, {len(prev)} total)")
