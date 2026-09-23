#!/usr/bin/env python3
"""Re-read journal rows whose check payload was captured before the platform finished adjudicating.

THE DEFECT. A simulation's check set GROWS after the sim completes. Measured 2026-08-09 by
re-reading six alphas whose journal rows carry 8-9 checks: every one now returns 19-20. So the
pipeline records its primary evidence too early, and 9,833 rows carry a payload that was never the
platform's final verdict.

That matters because gate_lib now (correctly) refuses to read a MISSING gate as a passing gate. The
naive consequence would be to discard those rows. The measured consequence is different: re-reading
ten of them that the journal called "no FAIL" on <=9 checks, all ten were still clean at 20 checks.
So the right remedy is to RE-READ, not to discard. (n=10 only rules out "most are false"; it does
not establish the flip rate, which is what this tool measures at scale.)

WHY IT IS CHEAP NOW. `GET /users/self/alphas?limit=100` returns 100 alphas with the full `is` block
and every check with value and limit — one request per hundred alphas instead of one per alpha.

WHY IT APPENDS. state/resim_results.jsonl is append-only and is the one asset that cannot be
regenerated. Readers already key by old_id with last-write-wins (4,868 of 67,430 lines are
re-writes), so a corrected row is written the way the journal already works rather than by
rewriting 115 MB in place.

  python3 tools/backfill_checks.py --dry-run     # measure the flip rate, write nothing
  python3 tools/backfill_checks.py               # append corrected rows
"""
import argparse, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import submit_alphas as SA                                              # noqa: E402
import gate_lib as G                                                    # noqa: E402

API = "https://api.worldquantbrain.com/users/self/alphas"
RESULTS = ROOT / "state/resim_results.jsonl"
# SHARE THE BUDGET, DO NOT YIELD THE WHOLE OF IT.
#
# The first version waited on state/resim.lock so the simulator always had priority. Against a
# feeder that keeps a queue full that is not politeness, it is a deadlock: the crawl never gets a
# turn. Measured instead — the simulator's own request rate over 30 minutes of live running:
#
#     median 23 req/min, peak 39, against an account budget of 60
#
# So there is real headroom and the right move is to take a fixed slice of it rather than all or
# nothing. 15/min keeps the total at 38 typical and 54 at the simulator's peak, both under the
# limit, and puts the ~100 requests this crawl needs inside seven minutes.
#
# (The correlation endpoint is a different story — it has its own much smaller budget and refused
# for over an hour, which is why tools/measure_backlog.py does yield outright.)
RATE = 15.0 / 60.0


_last = [0.0]


def _get(s, params):
    gap = 1.0 / RATE - (time.time() - _last[0])
    if gap > 0:
        time.sleep(gap)
    _last[0] = time.time()
    r = s.get(API, params=params, timeout=90)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def crawl_banded(s, out=None, lo=None, hi=None, depth=0):
    """alpha_id -> is-block, over the WHOLE account, by adaptive is.sharpe bands.

    The endpoint refuses to paginate past the first 1,000 rows OF A GIVEN QUERY:

        offset 900   200  {"count":10000, "results":[...100...]}
        offset 5000  400  ["Cannot display more than the first 1,000 alphas.
                           Apply filters to narrow results and see more."]

    `count` is the size of the match, not what is reachable — so a naive offset walk stops at 1,000
    however large `count` looks. (The audit records this as a 10,000 cap; the reachable cap is
    1,000 per query.)

    `dateCreated>`/`dateCreated<` are ACCEPTED and IGNORED — count stays at the unfiltered 10,000 —
    so they cannot partition. `is.sharpe>` does filter (3,113 for >2.0), so sharpe is the
    partitioning key: take a band, and if it still matches >=1,000, split it and recurse.
    """
    out = {} if out is None else out
    params = {"limit": 1}
    if lo is not None:
        params["is.sharpe>"] = lo
    if hi is not None:
        params["is.sharpe<"] = hi
    code, j = _get(s, params)
    if code != 200 or not isinstance(j, dict):
        return out
    n = j.get("count") or 0
    if n >= 1000 and depth < 8:
        mid = ((lo if lo is not None else -5.0) + (hi if hi is not None else 12.0)) / 2.0
        crawl_banded(s, out, lo, mid, depth + 1)
        crawl_banded(s, out, mid, hi, depth + 1)
        return out
    for off in range(0, min(n, 1000), 100):
        p = dict(params, limit=100, offset=off)
        code, jj = _get(s, p)
        res = (jj or {}).get("results") or [] if isinstance(jj, dict) else []
        if not res:
            break
        for a in res:
            if not isinstance(a, dict):
                continue
            iss = a.get("is") or {}
            if a.get("id") and iss.get("checks"):
                out[a["id"]] = iss
    print(f"  band ({lo},{hi}) n={n} -> {len(out)} total", flush=True)
    return out


def crawl(s, max_pages=110, per=100):
    """Legacy newest-first walk, kept for the <=1,000 case."""
    out, last = {}, 0.0
    for i in range(max_pages):
        gap = 1.0 / RATE - (time.time() - last)
        if gap > 0:
            time.sleep(gap)
        last = time.time()
        try:
            j = s.get(API, params={"limit": per, "offset": i * per,
                                   "order": "-dateCreated"}, timeout=90).json()
        except Exception as e:
            print(f"  page {i}: {type(e).__name__} — stopping crawl here", flush=True)
            break
        # The endpoint answers {"results": [...]} on the normal path and a BARE LIST on at least
        # one offset — indexing "results" on that raised AttributeError and took the whole crawl
        # down at page N, discarding every page already read. An unexpected shape must read as
        # "no rows here", never as a crash.
        if isinstance(j, list):
            res = j
        elif isinstance(j, dict):
            res = j.get("results") or []
        else:
            print(f"  page {i}: unexpected payload {type(j).__name__} — stopping", flush=True)
            break
        if not res:
            break
        for a in res:
            iss = a.get("is") or {}
            if a.get("id") and iss.get("checks"):
                out[a["id"]] = iss
        if (i + 1) % 10 == 0:
            print(f"  crawled {len(out)} alphas ({i + 1} requests)", flush=True)
    return out


def n_adjudicated(checks):
    return len([c for c in (checks or [])
                if isinstance(c, dict) and c.get("result") in ("PASS", "FAIL")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    byid = {}
    for line in open(RESULTS):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("old_id"):
            byid[d["old_id"]] = d
    print(f"journal: {len(byid)} distinct old_id")

    s = SA.session()
    live = crawl_banded(s)
    print(f"platform: {len(live)} alphas with checks\n")

    fixed, gained, flips_to_fail, flips_to_pass = [], 0, 0, 0
    for oid, d in byid.items():
        aid = d.get("alpha")
        if not aid or aid not in live:
            continue
        now = live[aid]
        if n_adjudicated(now.get("checks")) <= n_adjudicated(d.get("checks")):
            continue
        before = G.gate_status(d)["zero_fail"]
        row = dict(d)
        row.update({k: now.get(k) for k in
                    ("sharpe", "fitness", "turnover", "returns", "drawdown") if now.get(k) is not None})
        row["checks"] = [{k: c.get(k) for k in ("name", "result", "value", "limit")}
                         for c in now["checks"]]
        row["backfilled"] = True
        after = G.gate_status(row)["zero_fail"]
        gained += 1
        if before and not after:
            flips_to_fail += 1
        if after and not before:
            flips_to_pass += 1
        fixed.append(row)

    print(f"rows whose payload GREW           {gained}")
    print(f"   zero-fail -> not zero-fail     {flips_to_fail}   (the journal was crediting these)")
    print(f"   not zero-fail -> zero-fail     {flips_to_pass}   (the journal was losing these)")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    with open(RESULTS, "a") as f:
        for r in fixed:
            f.write(json.dumps(r) + "\n")
    print(f"\nappended {len(fixed)} corrected rows to {RESULTS.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
