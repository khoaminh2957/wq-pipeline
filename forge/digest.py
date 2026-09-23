"""forge.digest — the daily m12 digest (C24): the forge journal's own 24-hour window, the cells
filled since the last digest, submittable per 1,000 sims, the DSR pass rate, the queue state."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
from forge import cells as C, harvest as HV, probe as P, submit as SUB  # noqa: E402

SNAPSHOT = ROOT / "state/forge/cells_snapshot.json"
DAY_S = 86400


def _ts(row):
    """Journal rows carry an ISO dateCreated; fall back to detect time fields."""
    d = row.get("dateCreated")
    if isinstance(d, str) and len(d) >= 19:
        try:
            t = time.strptime(d[:19], "%Y-%m-%dT%H:%M:%S")
            off = 0
            tail = d[19:]
            if len(tail) >= 6 and tail[0] in "+-":
                off = (int(tail[1:3]) * 3600 + int(tail[4:6]) * 60) * (1 if tail[0] == "+" else -1)
            return time.mktime(t) - off - time.timezone
        except ValueError:
            return None
    return None


def window(rows, scored, corr, posted, now=None, span=DAY_S) -> dict:
    now = now or time.time()
    since = now - span
    recent = {a: r for a, r in rows.items() if (_ts(r) or 0) >= since}
    sc_recent = {a: x for a, x in scored.items() if (x.get("scored_at") or 0) >= since}
    ppass = sum(1 for x in sc_recent.values() if x.get("stage") not in ("fail", "incomplete", None)
                and not str(x.get("stage")).startswith("turnover"))
    cands = sum(1 for x in sc_recent.values() if x.get("stage") == "candidate")
    dsr_rated = sum(1 for x in sc_recent.values() if x.get("stage") in ("candidate", "dsr-fail"))
    measured = sum(1 for a, c in corr.items() if (c.get("read_at") or 0) >= since
                   and all(isinstance(c.get(k), (int, float)) for k in P.KINDS))
    posted_recent = [h for h in posted if (h.get("posted_at") or 0) >= since]
    return {"sims": len(recent), "platform_pass": ppass, "candidates": cands, "dsr_rated": dsr_rated,
            "corr_measured": measured, "posted": len(posted_recent),
            "dsr_rate": (cands / dsr_rated) if dsr_rated else 0.0}


def cells_filled(pair_counts, snapshot_path=SNAPSHOT) -> list:
    """Cells that reached UNLOCK_AT since the last digest; rewrites the snapshot."""
    now_full = sorted("%s/d%d %s" % (r, d, cat) for (r, d), counts in pair_counts.items()
                      for cat, n in counts.items() if int(n) >= C.UNLOCK_AT)
    prev = []
    if pathlib.Path(snapshot_path).exists():
        try:
            prev = json.load(open(snapshot_path))
        except ValueError:
            prev = []
    pathlib.Path(snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    json.dump(now_full, open(snapshot_path, "w"))
    return sorted(set(now_full) - set(prev)) if prev else []


def queue_line(plans_dir=ROOT / "state/forge/plans") -> str:
    plans = sorted(pathlib.Path(plans_dir).glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not plans:
        return "Hàng đợi giả thuyết: chưa có vòng nào."
    p = json.load(open(plans[-1]))
    return ("Hàng đợi giả thuyết: vòng cuối ghép %d/%d từ %d giả thuyết trên %d ô với tới được."
            % (len(p.get("constructions", [])), p.get("n", 0), p.get("hypotheses", 0), p.get("cells_considered", 0)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--send", action="store_true", help="enqueue the message (default: print only — Khoa 2026-09-04: forge notifications off until asked)")
    a = ap.parse_args(argv)
    import msgcat as MC
    import submit_budget as SB
    rows, scored, corr = HV.forge_rows(), HV.load_scored(), P.load_corr()
    posted = SUB.posted_history(ledger=SB.LEDGER)
    pair_counts = C.load_pair_counts(ROOT / "state/pyramid_cell_counts.json")
    elig, _ = SUB.eligible(scored, corr, rows, pair_counts, posted)
    w = window(rows, scored, corr, posted)
    per_1000 = (1000.0 * len(elig) / w["sims"]) if w["sims"] else 0.0
    msg = MC.m12_forge_digest(w["sims"], w["platform_pass"], w["candidates"], w["corr_measured"], len(elig),
                              w["posted"], cells_filled(pair_counts), per_1000, w["dsr_rate"], queue_line())
    body, _ = MC.render(msg)
    print(body)
    if a.send:
        print("enqueued:", MC.send(msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
