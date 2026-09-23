#!/usr/bin/env python3
"""measure_corr_incremental.py — measure prod+self correlation per alpha, append each to
state/funnel/corr_results.jsonl INCREMENTALLY (resumable, survives timeouts). A candidate is
submittable-clean iff prod breach_count==0 (no production alpha correlates >0.7) AND self<0.7.
Usage: python3 tools/measure_corr_incremental.py <id> [<id>...]"""
import pickle, requests, json, time, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/corr_results.jsonl"

def session():
    cookie_path = ROOT / "state/wq_cookies.pkl"
    if not cookie_path.exists():
        sys.exit("not authenticated: state/wq_cookies.pkl missing — run auth first (auth_only.py)")
    c = pickle.load(open(cookie_path, "rb"))
    s = requests.Session()
    if isinstance(c, dict): s.cookies.update(c)
    else:
        for x in c: s.cookies.set_cookie(x)
    return s

def fetch(s, aid, kind, tries=25):
    for _ in range(tries):
        try:
            r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/correlations/{kind}", timeout=45)
        except Exception:
            time.sleep(2); continue
        if r.headers.get("Retry-After"): time.sleep(min(float(r.headers["Retry-After"]), 3)); continue
        if r.status_code == 200 and not r.text: time.sleep(2); continue
        if r.status_code == 200: return r.json()
        return None
    return None

def prod_breach(j):
    """Return the platform's PROD_CORRELATION value -- j['max'] -- and the >0.7 alpha count.

    This used to return the highest non-empty BUCKET EDGE, so every reading was quantised to
    0.7/0.8/0.9/1.0 and disagreed with tools/fetch_prod_corr.prod_maxcorr on the same payload
    (0.8 vs 0.7031 on 3qeeOxlQ, whose rejection quoted value=0.7031). Two readers of one number
    is how a quantised estimate ends up stored in state/funnel/corr_results.jsonl and read back
    as exact -- which is what made four already-dead alphas look like prod 0.70 candidates."""
    if not j: return None, None
    if not j.get("records"): return None, None        # schema present but no rows = NOT measured
    props = [p["name"] for p in j["schema"]["properties"]]; idx = {p: i for i, p in enumerate(props)}
    breach = 0
    for row in j.get("records", []):
        a = row[idx["alphas"]]
        if a and a > 0 and row[idx["max"]] > 0.7: breach += a
    return j.get("max"), breach

def self_max(j):
    if not j: return None
    if not j.get("records"): return None              # schema present but no rows = NOT measured (still computing)
    props = [p["name"] for p in j["schema"]["properties"]]
    ci = props.index("correlation") if "correlation" in props else None
    if ci is None: return None
    vals = [row[ci] for row in j.get("records", []) if row[ci] is not None]
    return max(vals) if vals else None

done = set()
if OUT.exists():
    for line in open(OUT):
        try:
            r = json.loads(line)
            # only a FULLY-measured row (prod breach known AND self fetch ok) is final; a fetch
            # failure on either side must re-measure next run, never lock in as clean.
            if r.get("breach") is not None and r.get("self_ok"):
                done.add(r["alpha"])
        except: pass

s = session()
f = open(OUT, "a")
for aid in sys.argv[1:]:
    if aid in done: continue
    pc, breach = prod_breach(fetch(s, aid, "prod"))
    self_j = fetch(s, aid, "self")
    sc = self_max(self_j)
    # MEASURED means a NUMBER came back. Rows-present is not enough: self_max() returns None on
    # a payload with no `correlation` column or all-null values, and the clean test below reads
    # `sc is None` as a pass.
    self_ok = self_j is not None and bool(self_j.get("records")) and sc is not None
    # clean requires BOTH sides actually measured: prod breach==0 AND self fetched AND self<0.7.
    clean = (breach == 0 and breach is not None and self_ok and (sc is None or sc < 0.7))
    rec = {"alpha": aid, "prod_max": pc, "breach": breach, "self": sc, "self_ok": self_ok, "clean": clean}
    f.write(json.dumps(rec) + "\n"); f.flush()
    print(f"{aid} prod={pc} breach={breach} self={round(sc,3) if sc else sc} self_ok={self_ok} clean={clean}", flush=True)
f.close()
