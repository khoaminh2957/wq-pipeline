"""ON THE VPS: ask the platform whether each field id exists for one (region, universe, delay).

Round 1 (2026-09-24 17:38) showed "Invalid data field" / "unknown variable" errors for fields our catalogue
snapshot lists (fetched/rc/fields/USA_TOP3000_d1.jsonl predates 09-24), and one invalid child cancels its
whole multisim parent. This reads GET /data-fields/<id> for every id given -- an API read, no simulation --
at most one request per ~1.1 s (the account's 60/min bucket is shared with the loop), and writes
{"id", "http", "valid", "at"} lines to --out, resuming from what is already there.

    python -u validate_fields.py --ids ids.txt --out valid.jsonl [--region USA --universe TOP3000 --delay 1]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

WQ = pathlib.Path("/opt/wq")
sys.path[:0] = [str(WQ), str(WQ / "tools")]

BASE = "https://api.worldquantbrain.com"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--region", default="USA")
    ap.add_argument("--universe", default="TOP3000")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--gap", type=float, default=1.1)
    a = ap.parse_args(argv)
    import layered_sim as LS
    s = LS.session()
    done = set()
    out = pathlib.Path(a.out)
    if out.exists():
        for line in out.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("http") in (200, 404):
                done.add(r["id"])
    ids = [i.strip() for i in pathlib.Path(a.ids).read_text().split() if i.strip() and i.strip() not in done]
    print("to check: %d (already done %d)" % (len(ids), len(done)), flush=True)
    params = {"instrumentType": "EQUITY", "region": a.region, "universe": a.universe, "delay": a.delay}
    with open(out, "a") as fh:
        for n, fid in enumerate(ids, 1):
            for attempt in range(6):
                r = s.get("%s/data-fields/%s" % (BASE, fid), params=params, timeout=60)
                if r.status_code == 429:
                    time.sleep(float(r.headers.get("Retry-After", 10) or 10))
                    continue
                break
            if r.status_code == 401:
                print("401: session expired; stopping (resume later)", flush=True)
                return 2
            valid = r.status_code == 200
            if valid:
                try:
                    j = r.json()
                    # a 200 for a field that exists but not in this universe would still be usable only if listed here
                    valid = bool(j.get("id") == fid)
                except ValueError:
                    valid = False
            fh.write(json.dumps({"id": fid, "http": r.status_code, "valid": valid, "at": time.time()}) + "\n")
            fh.flush()
            if n % 100 == 0:
                print("checked %d/%d" % (n, len(ids)), flush=True)
            time.sleep(a.gap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
