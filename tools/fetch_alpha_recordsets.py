#!/usr/bin/env python3
"""Khoa standing rule: after EVERY sim, always fetch the FULL analysis chart set for each alpha —
PnL curve + all recordsets in the Brain analysis panel (Performance / Coverage / Average Size /
PnL / Sharpe / Abs Average Value, grouped by capitalization / sector / industry).

Discovers the available recordset slugs from the API (no guessing), then fetches each.
Single stream, async-retry (WQ returns empty 200 while it computes the recordset), 429/401-aware.

Out:  fetched/recordsets/<alpha_id>/<slug>.json        (raw recordset json)
      fetched/pnl/<alpha_id>.jsonl                     (pnl mirrored to the [date,pnl] format)
      fetched/recordsets/<alpha_id>/_index.json        (slugs fetched + row counts)

Usage:
  python tools/fetch_alpha_recordsets.py A1b2C3 D4e5F6 ...        # explicit ids
  python tools/fetch_alpha_recordsets.py --from state/batch4_ranked.json   # all 'alpha' ids in file
"""
import sys, json, time, pickle, pathlib
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config

B = config.WQ_API
OUT = pathlib.Path(__file__).resolve().parent.parent / "fetched"
(OUT / "recordsets").mkdir(parents=True, exist_ok=True)
(OUT / "pnl").mkdir(parents=True, exist_ok=True)
MIN_GAP = 0.45
MAX_429 = 6

# S2.0 patch 5: 5 core slugs always return; the 14 grouped slugs 404 until the alpha has a
# SESSION_COMMS-recorded UI-open — fetch them ONLY with --grouped (driver decides at 0 GETs).
CORE_SLUGS = ["pnl", "sharpe", "turnover", "daily-pnl", "yearly-stats"]
GROUPED_SLUGS = [
    "coverage", "coverage-by-sector", "coverage-by-industry",
    "average-size-by-capitalization", "average-size-by-sector", "average-size-by-industry",
    "pnl-by-capitalization", "pnl-by-sector", "pnl-by-industry",
    "sharpe-by-capitalization", "sharpe-by-sector", "sharpe-by-industry",
    "average-value-by-sector", "average-value-by-industry",
]

s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(config.COOKIE_PATH, "rb")))
_last = [0.0]; _n429 = [0]


def get(path):
    for _ in range(30):
        dt = time.time() - _last[0]
        if dt < MIN_GAP:
            time.sleep(MIN_GAP - dt)
        _last[0] = time.time()
        try:
            r = s.get(B + path, timeout=40)
        except Exception:
            time.sleep(4); continue
        if r.status_code == 429:
            _n429[0] += 1
            if _n429[0] > MAX_429:
                raise SystemExit(f"CIRCUIT-BREAK: {_n429[0]}x429 — stop to avoid hard ban")
            w = float(r.headers.get("Retry-After", 8) or 8)
            if w > 600: raise SystemExit("RATE-BAN — S2.5 runbook")
            print(f"    429 #{_n429[0]}, wait {w:.0f}s", flush=True); time.sleep(w + 2); continue
        if r.status_code == 401:
            raise SystemExit("401 — session expired; re-auth (biometric) and rerun")
        return r
    return None


def fetch_recordset(aid, slug, tries=12):
    """WQ computes recordsets async → empty 200 until ready. Retry until 'records' non-empty."""
    for _ in range(tries):
        r = get(f"/alphas/{aid}/recordsets/{slug}")
        if r is None:
            return None
        if r.status_code == 404:
            return "404"
        if r.status_code == 200 and (r.text or "").strip():
            try:
                j = r.json()
                recs = j.get("records") if isinstance(j, dict) else j
                if recs:
                    return j
            except Exception:
                pass
        time.sleep(5)
    return "empty"


def mirror_pnl(aid, j):
    """Save pnl recordset to the canonical fetched/pnl/<id>.jsonl [date, pnl] format."""
    recs = j.get("records") if isinstance(j, dict) else j
    if not recs:
        return
    with open(OUT / "pnl" / f"{aid}.jsonl", "w") as f:
        for row in recs:
            # pnl records are typically [date, pnl] or [date, pnl, ...]; keep first two cols
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                f.write(json.dumps([row[0], row[1]]) + "\n")


def main(ids, grouped=False):
    # S2.0 patch 5: _n429 is global per run (never reset per alpha); no discovery GET.
    slugs = CORE_SLUGS + (GROUPED_SLUGS if grouped else [])
    for aid in ids:
        d = OUT / "recordsets" / aid; d.mkdir(parents=True, exist_ok=True)
        print(f"[{aid}] {len(slugs)} recordsets ({'core+grouped' if grouped else 'core'})", flush=True)
        index = {}
        for slug in slugs:
            res = fetch_recordset(aid, slug)
            if isinstance(res, dict) or isinstance(res, list):
                json.dump(res, open(d / f"{slug}.json", "w"), ensure_ascii=False)
                recs = res.get("records") if isinstance(res, dict) else res
                n = len(recs or [])
                index[slug] = n
                if slug == "pnl":
                    mirror_pnl(aid, res)
                print(f"    {slug}: {n} rows", flush=True)
            else:
                index[slug] = res  # "404" / "empty" / None
                print(f"    {slug}: {res}", flush=True)
        json.dump(index, open(d / "_index.json", "w"), indent=1)
        print(f"[{aid}] done -> {d}", flush=True)
    print("RECORDSETS-FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    grouped = "--grouped" in args
    args = [a for a in args if a != "--grouped"]
    if not args:
        raise SystemExit("usage: fetch_alpha_recordsets.py [--grouped] <id...> | --from <ranked.json>")
    if args[0] == "--from":
        rows = json.load(open(args[1]))
        ids = [r.get("alpha") or r.get("sid") or r.get("id") for r in rows]
        ids = [i for i in ids if i]
    else:
        ids = args
    main(ids, grouped=grouped)
