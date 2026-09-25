"""The pre-registered read-out of a frames round (docs/frames/13a_preregistration_round1.md). Offline, read-only.

    python3 -B framelib/experiments/analyse_round.py --journal frames_r1b.jsonl --plan frames_r1b.plan.json \
        [--recovered recovered.jsonl] [--out report.json]

Every planned construction gets exactly one outcome row: its journal row (the last one for its formula+settings,
from the round's journal, else from recovered.jsonl), or "missing". Status ERROR / CANCELLED / missing counts as a
FAILURE of the primary outcome (13a); the same tables are also printed on scored rows only, labelled POST-HOC.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random

BINDING = ("LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE", "CONCENTRATED_WEIGHT",
           "HIGH_TURNOVER", "LOW_TURNOVER")
FOCUS_DATASETS = ("option3", "option8", "us_short_sale")   # doc 12 B2 / doc 13 reading notes: report every split


def _key(formula: str, settings: dict) -> tuple:
    s = {k: settings.get(k) for k in ("region", "universe", "delay", "neutralization", "decay", "truncation")}
    return (formula.replace(" ", ""), json.dumps(s, sort_keys=True))


def _rows(path):
    out = {}
    if not path or not pathlib.Path(path).exists():
        return out
    for line in open(path, errors="replace"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("status") in (None, "PARENT-POSTED") or not r.get("formula"):
            continue
        st = r.get("settings") or {}
        if isinstance(st, str):
            continue
        out[_key(r["formula"], st)] = r
    return out


def outcome(r) -> dict:
    if r is None:
        return {"status": "missing", "scored": False, "ls": 0, "y08": 0, "d24": 0}
    st = r.get("status")
    scored = st in ("COMPLETE", "WARNING")
    checks = {c.get("name"): c for c in (r.get("checks") or [])}
    ls = int(scored and (checks.get("LOW_SHARPE") or {}).get("result") == "PASS")
    lim = (checks.get("LOW_SHARPE") or {}).get("limit")
    try:
        sh = float(r.get("sharpe"))
        y08 = int(scored and lim is not None and sh >= 0.8 * float(lim))
    except (TypeError, ValueError):
        y08 = 0
    d24 = int(scored and all((checks.get(n) or {}).get("result") == "PASS" for n in BINDING))
    return {"status": st, "scored": scored, "ls": ls, "y08": y08, "d24": d24, "alpha": r.get("alpha"),
            "sharpe": r.get("sharpe")}


def cluster_ratio(xa, ca, xb, cb, n_boot=10000, seed=1):
    """Rate ratio mean(xa)/mean(xb) with a cluster bootstrap (resample clusters within each arm)."""
    def by(x, c):
        g = collections.defaultdict(list)
        for v, k in zip(x, c):
            g[k].append(v)
        return list(g.values())
    ga, gb = by(xa, ca), by(xb, cb)
    ra = sum(xa) / len(xa) if xa else float("nan")
    rb = sum(xb) / len(xb) if xb else float("nan")
    rng = random.Random(seed)
    ratios = []
    for _ in range(n_boot):
        sa = [v for g in (rng.choice(ga) for _ in ga) for v in g]
        sb = [v for g in (rng.choice(gb) for _ in gb) for v in g]
        pa, pb = sum(sa) / len(sa), sum(sb) / len(sb)
        ratios.append(pa / pb if pb > 0 else float("inf"))
    ratios.sort()
    lo, hi = ratios[int(0.025 * n_boot)], ratios[int(0.975 * n_boot) - 1]
    return {"rate_a": ra, "rate_b": rb, "ratio": (ra / rb if rb > 0 else float("inf")), "ci95": [lo, hi],
            "clusters": [len(ga), len(gb)], "n": [len(xa), len(xb)]}


def mcnemar(pairs):
    """Exact two-sided McNemar on (b, c) outcome pairs."""
    n10 = sum(1 for b, c in pairs if b and not c)
    n01 = sum(1 for b, c in pairs if c and not b)
    n = n10 + n01
    if n == 0:
        return {"b_only": 0, "c_only": 0, "p": 1.0}
    k = min(n10, n01)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return {"b_only": n10, "c_only": n01, "p": min(1.0, 2 * p)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--recovered", default="")
    ap.add_argument("--catalogue", default="fetched/rc/fields/USA_TOP3000_d1.jsonl")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    plan = json.loads(pathlib.Path(a.plan).read_text())["constructions"]
    rows = _rows(a.recovered)
    rows.update(_rows(a.journal))                          # the round's own journal wins
    ds = {}
    if pathlib.Path(a.catalogue).exists():
        for line in open(a.catalogue):
            j = json.loads(line)
            ds[j["id"]] = (j.get("dataset") or {}).get("id")
    recs = []
    for c in plan:
        m = c["meta"]
        o = outcome(rows.get(_key(c["formula"], c["settings"])))
        fields = m.get("fill") or [m.get("field"), m.get("field2")]
        focus = any(ds.get(f) in FOCUS_DATASETS for f in fields if f) or any(
            x in (m.get("dataset") or "") for x in FOCUS_DATASETS)
        cluster = m.get("frame_id") if m["arm"] in ("a", "b", "c") else m.get("hypothesis")
        recs.append({**o, "arm": m["arm"], "cluster": cluster, "focus": focus, "fill": tuple(m.get("fill") or ()),
                     "settings": (c["settings"].get("neutralization"), c["settings"].get("decay")),
                     "paired_b": m.get("paired_b")})
    report = {"n_planned": len(recs), "status": {}, "rates": {}, "tests": {}, "focus_split": {}, "settings": {}}
    for arm in "abcd":
        R = [r for r in recs if r["arm"] == arm]
        report["status"][arm] = dict(collections.Counter(str(r["status"]) for r in R))
        sc = [r for r in R if r["scored"]]
        report["rates"][arm] = {"n": len(R), "scored": len(sc),
                                **{k: [sum(r[k] for r in R), round(sum(r[k] for r in R) / max(len(R), 1), 4),
                                       round(sum(r[k] for r in sc) / max(len(sc), 1), 4)] for k in ("ls", "y08", "d24")}}
        report["focus_split"][arm] = {str(f): {"n": len(g), "ls": sum(r["ls"] for r in g), "y08": sum(r["y08"] for r in g)}
                                      for f, g in ((f, [r for r in R if r["focus"] == f]) for f in (True, False))}
        report["settings"][arm] = dict(collections.Counter("%s/%s" % r["settings"] for r in R))

    def arm_vec(arm, k="ls", scored_only=False):
        R = [r for r in recs if r["arm"] == arm and (r["scored"] or not scored_only)]
        return [r[k] for r in R], [r["cluster"] for r in R]
    for k in ("ls", "y08", "d24"):
        xa, ca = arm_vec("a", k)
        xd, cd = arm_vec("d", k)
        xb, cb = arm_vec("b", k)
        report["tests"]["Q-C a/d " + k] = cluster_ratio(xa, ca, xd, cd)
        report["tests"]["Q1 a/b " + k] = cluster_ratio(xa, ca, xb, cb)
    # Q-A: b vs c paired by the same fill and settings
    bidx = {(r["fill"], r["settings"]): r for r in recs if r["arm"] == "b"}
    pairs = [(bidx[(r["fill"], r["settings"])]["ls"], r["ls"]) for r in recs
             if r["arm"] == "c" and (r["fill"], r["settings"]) in bidx]
    report["tests"]["Q-A b vs c ls (McNemar)"] = {**mcnemar(pairs), "pairs": len(pairs)}
    txt = json.dumps(report, indent=1, default=str)
    if a.out:
        pathlib.Path(a.out).write_text(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
