"""Screening read-out for a frames round (docs/frames/13c_preregistration_r3s.md). Offline, read-only.

    python3 -B framelib/experiments/screen.py --journal frames_r3s.jsonl --plan frames_r3s.plan.json \
        [--recovered recovered.jsonl] --seed 20260928 --out screen.json

Per frame over scored rows: LOW_SHARPE rate, y08 rate, mean y_ratio (clipped +-2.5), all-7-check rows. Eligible:
>= 3 scored rows. Line: top ceil(0.2 x eligible) by (LS rate, mean y_ratio, frame id). Replication set: every frame
above the line plus the same number drawn at random (the given seed) from the eligible frames below it.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import analyse_round as AR   # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--recovered", default="")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    plan = json.loads(pathlib.Path(a.plan).read_text())["constructions"]
    rows = AR._rows(a.recovered)
    rows.update(AR._rows(a.journal))
    per = collections.defaultdict(lambda: {"planned": 0, "scored": 0, "ls": 0, "y08": 0, "d24": 0, "yr": [],
                                           "d24_alphas": [], "status": collections.Counter()})
    for c in plan:
        m = c["meta"]
        r = rows.get(AR._key(c["formula"], c["settings"]))
        o = AR.outcome(r)
        f = per[m["frame_id"]]
        f["planned"] += 1
        f["status"][str(o["status"])] += 1
        if not o["scored"]:
            continue
        f["scored"] += 1
        f["ls"] += o["ls"]
        f["y08"] += o["y08"]
        f["d24"] += o["d24"]
        if o["d24"]:
            f["d24_alphas"].append(o.get("alpha"))
        ch = {x.get("name"): x for x in (r.get("checks") or [])}
        try:
            f["yr"].append(max(-2.5, min(2.5, float(r["sharpe"]) / float((ch.get("LOW_SHARPE") or {}).get("limit")))))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    elig = [k for k, f in per.items() if f["scored"] >= 3]
    key = lambda k: (per[k]["ls"] / per[k]["scored"], statistics.mean(per[k]["yr"]) if per[k]["yr"] else -9.0, k)
    ranked = sorted(elig, key=key, reverse=True)
    top = ranked[: math.ceil(0.2 * len(elig))] if elig else []
    below = [k for k in elig if k not in set(top)]
    rng = random.Random("screen|%d" % a.seed)
    control = rng.sample(below, min(len(top), len(below)))
    tot = collections.Counter()
    for f in per.values():
        for s, n in f["status"].items():
            tot[s] += n
    rep = {"frames": len(per), "eligible": len(elig), "line": len(top), "status": dict(tot),
           "planned": sum(f["planned"] for f in per.values()), "scored": sum(f["scored"] for f in per.values()),
           "ls": sum(f["ls"] for f in per.values()), "y08": sum(f["y08"] for f in per.values()),
           "d24": sum(f["d24"] for f in per.values()),
           "d24_alphas": [x for f in per.values() for x in f["d24_alphas"]],
           "top": [{"frame": k, "scored": per[k]["scored"], "ls": per[k]["ls"], "y08": per[k]["y08"],
                    "mean_yr": round(statistics.mean(per[k]["yr"]), 3) if per[k]["yr"] else None} for k in top],
           "replicate": sorted(top) + sorted(control), "control": sorted(control)}
    txt = json.dumps(rep, indent=1, default=str)
    if a.out:
        pathlib.Path(a.out).write_text(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
