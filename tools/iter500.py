#!/usr/bin/env python3
"""Report a verdict every 500 simulations, on the objective that actually gates a submission.

Khoa 2026-08-07: *"iteration mỗi 500 sim"*.

The number that matters is neither zero-fail nor production correlation alone — it is the JOINT
event, and today proved why. Six structural arms were tuned on zero-fail; the winner (W=10, 3.24%
within-pool, forty times W=50) turns out to be the WORST window for prod-cleanliness (9.6% against
W=50's 15.5%). Three hours of work optimised a metric that does not gate anything. So every block
here reports:

    dispatched -> evaluable -> zero-fail -> measured -> prod-clean -> JOINT

with the attrition visible at each step, because a rate quoted over the wrong denominator is how
"5% zero-fail" hid a 20-57% error rate underneath it.

A block is not a target. If a block of 500 produces nothing, it says so and names the stage that
ate it; that is the point of the cadence rather than a failure of it.

  python3 tools/iter500.py                 # every block so far, oldest to newest
  python3 tools/iter500.py --block 500 --last 8
"""
import argparse, collections, glob, json, os, pathlib, re, statistics as stt

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load():
    oid2code, oid2set, oid2pool = {}, {}, {}
    for p in glob.glob(str(ROOT / "state/**/*targets*.json"), recursive=True) + \
             glob.glob(str(ROOT / "state/autoloop/pool_*.json")):
        try:
            rows = json.load(open(p))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        nm = os.path.basename(p)
        for r in rows:
            if isinstance(r, dict) and r.get("old_id"):
                oid2code.setdefault(r["old_id"], r.get("formula") or "")
                oid2set.setdefault(r["old_id"], r.get("settings") or {})
                oid2pool.setdefault(r["old_id"], nm)

    corr = {}
    try:
        for a, v in json.load(open(ROOT / "state/prod_corr_measured.json")).items():
            if v.get("prod_maxcorr") is not None:
                corr[a] = (v["prod_maxcorr"], v.get("self_maxcorr"))
    except Exception:
        pass
    for f in ("state/funnel/corr_results.jsonl", "state/funnel/arm_corr.jsonl"):
        try:
            for line in open(ROOT / f):
                d = json.loads(line)
                k = d.get("prod_max") if "prod_max" in d else d.get("prod")
                if k is not None:
                    corr.setdefault(d["alpha"], (k, d.get("self")))
        except Exception:
            pass

    # append order IS time order; the journal has no timestamps
    seq = []
    for line in open(ROOT / "state/resim_results.jsonl"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("old_id") not in oid2code:
            continue
        ck = r.get("checks") or []
        evaluable = bool(ck and any(isinstance(c, dict) for c in ck)) and r.get("status") != "ERROR"
        zf = evaluable and not any(isinstance(c, dict) and c.get("result") == "FAIL" for c in ck)
        pm, sm = corr.get(r.get("alpha"), (None, None))
        s = oid2set[oid2pool and r["old_id"]]
        seq.append({
            "oid": r["old_id"], "alpha": r.get("alpha"), "pool": oid2pool[r["old_id"]],
            "evaluable": evaluable, "zf": zf, "prod": pm, "self": sm,
            "sharpe": r.get("sharpe") if isinstance(r.get("sharpe"), (int, float)) else None,
            "neut": s.get("neutralization"), "W": (lambda m: int(m.group(1)) if m else None)(
                re.search(r"ts_decay_linear\(.*,\s*(\d+)\)\s*\)", oid2code[r["old_id"]])),
        })
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, default=500)
    ap.add_argument("--last", type=int, default=10)
    args = ap.parse_args()

    seq = load()
    n = len(seq)
    blocks = [seq[i:i + args.block] for i in range(0, n, args.block)]
    blocks = [b for b in blocks if len(b) >= args.block // 4]
    show = blocks[-args.last:]

    print(f"{n} journalled rows matched to a formula · blocks of {args.block}\n")
    print(f"{'block':>12} {'eval':>11} {'zero-fail':>13} {'measured':>10} "
          f"{'prod<0.70':>12} {'JOINT':>11}  dominant pool")
    for i, b in enumerate(show):
        start = n - len(show) * args.block + i * args.block
        ev = [x for x in b if x["evaluable"]]
        zf = [x for x in ev if x["zf"]]
        ms = [x for x in b if x["prod"] is not None]
        cl = [x for x in ms if x["prod"] < 0.70]
        jt = [x for x in zf if x["prod"] is not None and x["prod"] < 0.70]
        pool = collections.Counter(x["pool"] for x in b).most_common(1)[0]
        print(f"{max(0,start):6}-{max(0,start)+len(b):5} "
              f"{len(ev):5}/{len(b):<5} "
              f"{len(zf):4} {100*len(zf)/max(1,len(ev)):5.1f}% "
              f"{len(ms):10} "
              f"{len(cl):4} {100*len(cl)/max(1,len(ms)):5.1f}% "
              f"{len(jt):4} {100*len(jt)/max(1,len(ev)):5.2f}%  {pool[0][:26]}")

    print("\nCUMULATIVE, and the stage that eats the most:")
    ev = [x for x in seq if x["evaluable"]]
    zf = [x for x in ev if x["zf"]]
    ms = [x for x in seq if x["prod"] is not None]
    cl = [x for x in ms if x["prod"] < 0.70]
    jt = [x for x in zf if x["prod"] is not None and x["prod"] < 0.70]
    zf_ms = [x for x in zf if x["prod"] is not None]
    print(f"   dispatched      {n:7}")
    print(f"   evaluable       {len(ev):7}  ({100*len(ev)/max(1,n):5.1f}% survive the error stage)")
    print(f"   zero-fail       {len(zf):7}  ({100*len(zf)/max(1,len(ev)):5.1f}% of evaluable)")
    print(f"   ...of those measured for prod: {len(zf_ms)} ({100*len(zf_ms)/max(1,len(zf)):.1f}%)"
          f"  <- the measurement gap")
    print(f"   prod-clean      {len(cl):7}  ({100*len(cl)/max(1,len(ms)):5.1f}% of {len(ms)} measured)")
    print(f"   JOINT (gem)     {len(jt):7}")

    # what the current best-known recipe looks like in the data, so a block can be read against it
    print("\n   joint rate by neutralization (all history, measured rows only):")
    g = collections.defaultdict(lambda: [0, 0])
    for x in zf:
        if x["prod"] is None:
            continue
        g[x["neut"]][0] += 1
        g[x["neut"]][1] += (x["prod"] < 0.70)
    for k in sorted(g, key=lambda x: -(g[x][1] / g[x][0] if g[x][0] else 0)):
        a, b_ = g[k]
        if a < 10:
            continue
        print(f"      {str(k):14} {b_:3}/{a:<4} {100*b_/a:5.1f}%")


if __name__ == "__main__":
    raise SystemExit(main())
