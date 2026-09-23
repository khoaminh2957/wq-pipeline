#!/usr/bin/env python3
"""fetch_pnl_curves.py — fetch the daily PnL (equity) curve of a set of alphas so we can SEE how operators
reshape the curve (drawdown depth/duration, tail days, smoothness, recency), not just the summary metrics.
(Khoa 2026-07-18: "cào cả đường pnl của mỗi alpha để xem thử các operators tác động như thế nào đối với nó".)

Reuses the saved-cookie + async-empty-200 retry pattern (tools/refetch_pnl.py). NO auth, NO re-sim.
Input: a targets json [{round, old_id, alpha}, ...]. Output: state/funnel/pnl_curves.json keyed by old_id.
Usage: python3 tools/funnel/fetch_pnl_curves.py <targets.json>
"""
from __future__ import annotations
import json, pathlib, pickle, socket, sys, time
import requests

socket.setdefaulttimeout(40)
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
H = "https://api.worldquantbrain.com"
OUT = ROOT / "state/funnel/pnl_curves.json"
STATUS = ROOT / "state/funnel/pnl_fetch_status.json"


def _status(**k):
    STATUS.write_text(json.dumps(k))


def fetch_one(s, aid, attempts=15, sleep=6):
    """Fetch one alpha's PnL, retrying past the async-empty-200 while WQ computes it. Returns dict or None."""
    for _ in range(attempts):
        try:
            g = s.get(f"{H}/alphas/{aid}/recordsets/pnl", timeout=40)
        except Exception:
            time.sleep(sleep); continue
        if g.status_code == 401:
            return "AUTH"
        if g.status_code == 200 and (g.text or "").strip():
            try:
                j = g.json()
                recs = j.get("records") if isinstance(j, dict) else j
                if recs:
                    return {"schema": j.get("schema") if isinstance(j, dict) else None, "records": recs}
            except Exception:
                pass
        time.sleep(sleep)
    return None


def main(targets_path):
    targets = json.load(open(targets_path))
    s = requests.Session(); s.headers.update({"Connection": "close"})
    s.cookies.update(pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb")))
    have = json.load(open(OUT)) if OUT.exists() else {}
    _status(stage="start", total=len(targets), have=len(have))
    got = 0
    for i, t in enumerate(targets):
        oid, aid, rnd = t["old_id"], t["alpha"], t.get("round")
        if oid in have and have[oid].get("records"):
            got += 1; continue
        r = fetch_one(s, aid)
        if r == "AUTH":
            _status(stage="AUTH_FAIL", total=len(targets), got=got, at=oid)
            print("AUTH_FAIL — cookie expired; relaunch auth_only.py"); return 2
        if r:
            have[oid] = {"round": rnd, "alpha": aid, **r}
            got += 1
            OUT.write_text(json.dumps(have))
        _status(stage="fetching", total=len(targets), got=got, i=i + 1, last=oid, ok=bool(r))
    _status(stage="DONE", total=len(targets), got=got)
    print(f"DONE — {got}/{len(targets)} PnL curves saved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
