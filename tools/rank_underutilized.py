#!/usr/bin/env python3
"""rank_underutilized.py — from the full USA TOP1000 d1 catalog, rank datasets by an
UNDER-UTILIZATION score (low userCount = low prod-corr) balanced against usable signal
(enough well-covered continuous fields), and list each winner's best fields for alpha-building.

Under-util score = usable_field_count / log1p(userCount) — many good fields, few users.
Prints the top datasets and, for each, its best MATRIX fields (cov>=0.9, sorted by low
alphaCount then high coverage). Reads state/all_fields_usa_top1000_d1.jsonl (+ dataset meta).
"""
import json, math, re, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIELDS = ROOT / "state/all_fields_usa_top1000_d1.jsonl"
META = ROOT / "state/usa_top1000_d1_datasets.json"

def usable(f):
    return (f.get("type") == "MATRIX" and (f.get("coverage") or 0) >= 0.90
            and not re.search(r"(_flag|_id|_type|_code)$", f["id"]))

def main(top_n=25, min_fields=4):
    meta = {d["id"]: d for d in json.load(open(META))}
    byds = collections.defaultdict(list)
    for line in open(FIELDS):
        try: f = json.loads(line)
        except: continue
        byds[f["dataset"]].append(f)
    rows = []
    for ds, fs in byds.items():
        good = [f for f in fs if usable(f)]
        if len(good) < min_fields: continue
        users = (meta.get(ds, {}).get("userCount") or 0)
        score = len(good) / math.log1p(users + 1)
        rows.append((score, ds, len(good), users, meta.get(ds, {}).get("name", ""), good))
    rows.sort(reverse=True)
    print(f"# under-utilized datasets (usable_fields / log1p(users)), from {len(byds)} crawled\n")
    for score, ds, nf, users, name, good in rows[:top_n]:
        print(f"{ds:22} score={score:5.1f} usable={nf:4} users={users:6} | {name[:44]}")
    print("\n# best fields of the TOP-5 under-utilized datasets (for alpha legs):")
    for score, ds, nf, users, name, good in rows[:5]:
        good.sort(key=lambda f: ((f.get("alphaCount") or 0), -(f.get("coverage") or 0)))
        print(f"\n## {ds} (users={users}, {nf} usable)")
        for f in good[:8]:
            print(f"   {f['id']:40} aC={f.get('alphaCount')} cov={f.get('coverage')} | {f['description'][:44]}")

if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 25)
