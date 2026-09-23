#!/usr/bin/env python3
"""gen_batch.py — build a homogeneous sim batch of trading-logic strategies for one or more
datasets, sweeping settings. Used by the alpha-loop. Emits validated USA d1 targets.

Usage:
  python3 tools/alpha_loop/gen_batch.py --datasets option6,analyst4,earnings4,socialmedia12 \
      --universe TOP3000 --per 5 --out state/funnel/al_test_targets.json
"""
from __future__ import annotations
import argparse, json, pathlib, itertools, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import strategy_lib as sl

def settings(neut, trunc, decay, universe):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": universe, "delay": 1,
            "decay": decay, "neutralization": neut, "truncation": trunc,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

def build(datasets, per, universe, neuts, decays, trunc):
    rows, seen = [], set()
    for ds in datasets:
        strats = sl.gen_strategies(ds, n=per * 3)          # over-generate, settings-sweep trims
        # spread each strategy across every setting combo, until the per-dataset cap of
        # `per*len(combos)` rows is hit.
        combos = list(itertools.product(neuts, decays))
        cap = per * len(combos)
        ds_start = len(rows)
        for (tag, f) in strats:
            if len(rows) - ds_start >= cap: break            # cap per dataset
            for (neut, decay) in combos:
                if len(rows) - ds_start >= cap: break
                k = ("".join(f.split()), neut, trunc, decay)
                if k in seen: continue
                seen.add(k)
                oid = f"al_{tag}_{len(rows):03d}"
                rows.append({"old_id": oid, "id": oid, "formula": f + "\n",
                             "settings": settings(neut, trunc, decay, universe)})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", required=True)
    ap.add_argument("--universe", default="TOP3000")
    ap.add_argument("--per", type=int, default=6, help="strategies per dataset (before settings sweep)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    datasets = [d.strip() for d in a.datasets.split(",") if d.strip()]
    neuts = ["MARKET", "INDUSTRY", "SUBINDUSTRY"]; decays = [0, 6]
    rows = build(datasets, a.per, a.universe, neuts, decays, 0.05)
    json.dump(rows, open(a.out, "w"), indent=1)
    from collections import Counter
    c = Counter(r["old_id"].split("_")[1] for r in rows)
    print(f"wrote {len(rows)} rows -> {a.out}")
    print("by dataset-tag:", dict(c))

if __name__ == "__main__":
    main()
