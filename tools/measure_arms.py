#!/usr/bin/env python3
"""Measure prod/self correlation on a RANDOM sample of every arm, regardless of gate outcome.

This is the process change ITERATIONS.md I3 registered. Every previous correlation experiment in
this project measured only the alphas that passed the simulation gates, which is roughly 2% of
what was simulated -- so an arm that produced no zero-fails looked like an arm that produced no
information, when in fact its prod distribution is exactly the thing under test.

Here a walled arm and a clean arm are equally informative, and the arms stay comparable even when
their gate-pass rates differ by an order of magnitude.

The endpoint is asynchronous and answers `200 + Retry-After + EMPTY BODY` while it has no number
ready. On 2026-08-06 it stayed that way for 600 consecutive polls / 799s on a single alpha, so a
fixed try budget silently writes `None` rows that read like measurements. This script instead
records the outcome of each attempt separately: a measured number, or an explicit stall. Only a
number counts toward the sample.

  python3 tools/measure_arms.py --pool state/autoloop/pool_arms_t3.json --per-arm 30
"""
import argparse, collections, json, pathlib, random, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import submit_alphas as SA                                             # noqa: E402

OUT = ROOT / "state/funnel/arm_corr.jsonl"
API = "https://api.worldquantbrain.com/alphas"


def fetch(s, aid, kind, tries, sleep_cap=3.0):
    """Poll one async correlation payload. Returns (json|None, stalled:bool)."""
    for _ in range(tries):
        try:
            r = s.get(f"{API}/{aid}/correlations/{kind}", timeout=45)
        except Exception:
            time.sleep(2)
            continue
        if r.status_code == 200 and r.text.strip():
            try:
                return r.json(), False
            except Exception:
                return None, False
        if r.status_code in (401, 403):
            return None, False
        ra = r.headers.get("Retry-After")
        time.sleep(min(float(ra), sleep_cap) if ra else 1.0)
    return None, True


def prod_max(j):
    """The gate reads the MAX of the histogram payload, not a breach count."""
    if not j:
        return None, None
    mx = j.get("max")
    recs = j.get("records") or []
    breach = None
    try:
        cols = [c[0] if isinstance(c, list) else c.get("name")
                for c in (j.get("schema") or {}).get("properties", [])]
        if "correlation" in cols and recs:
            i = cols.index("correlation")
            breach = sum(1 for r in recs if isinstance(r[i], (int, float)) and r[i] > 0.7)
    except Exception:
        pass
    if mx is None and recs:
        try:
            mx = max(r[i] for r in recs if isinstance(r[i], (int, float)))
        except Exception:
            mx = None
    return mx, breach


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--per-arm", type=int, default=30)
    ap.add_argument("--tries", type=int, default=40)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    pool = json.load(open(ROOT / args.pool))
    arm_of = {r["old_id"]: r["meta"]["arm"] for r in pool}
    cell_of = {r["old_id"]: r["meta"]["cell"] for r in pool}

    # old_id -> platform alpha id, from the simulation journal
    got = {}
    for line in open(ROOT / "state/resim_results.jsonl"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("old_id") in arm_of and r.get("alpha"):
            got[r["old_id"]] = r["alpha"]
    print(f"pool {len(pool)} rows, {len(got)} simulated so far")

    done = set()
    if OUT.exists():
        for line in open(OUT):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("prod") is not None:
                done.add(d["alpha"])

    by = collections.defaultdict(list)
    for oid, aid in got.items():
        by[arm_of[oid]].append((oid, aid))

    s = SA.session()
    fh = open(OUT, "a")
    tally = collections.Counter()
    for arm in sorted(by):
        rows = by[arm][:]
        rng.shuffle(rows)
        n = 0
        for oid, aid in rows:
            if n >= args.per_arm:
                break
            if aid in done:
                n += 1
                continue
            pj, p_stall = fetch(s, aid, "prod", args.tries)
            sj, s_stall = fetch(s, aid, "self", args.tries)
            pm, br = prod_max(pj)
            sm, _ = prod_max(sj)
            rec = {"alpha": aid, "old_id": oid, "arm": arm, "cell": cell_of[oid],
                   "prod": pm, "breach": br, "self": sm,
                   "stalled": bool(p_stall or s_stall)}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if pm is not None:
                n += 1
                tally[arm] += 1
                print(f"  {arm} {aid} prod={pm} self={sm} breach={br}", flush=True)
            else:
                print(f"  {arm} {aid} {'STALLED' if rec['stalled'] else 'no payload'}", flush=True)
        print(f"{arm}: {n}/{args.per_arm} measured", flush=True)
    fh.close()
    print("\nmeasured per arm:", dict(tally))


if __name__ == "__main__":
    raise SystemExit(main())
