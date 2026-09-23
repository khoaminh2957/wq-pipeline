#!/usr/bin/env python3
"""Crawl the data-field inventory for EVERY (region, delay) the pyramid actually has cells in.

Why this is the first thing that has to happen. The pyramid is 211 cells across 16 (region, delay)
pairs, of which 10 are unlocked and all 10 sit in USA d1. The local field inventory covers exactly
two of those pairs -- USA d1 (23,041 rows) and USA d0 (2,377) -- so 14 pairs holding 181 open cells
cannot have a single alpha generated for them. No simulation budget, no structure work and no
correlation measurement matters until this file has rows for them.

The per-pair category list comes from the LIVE pyramid payload, not from a hardcoded list: JPN and
ASI carry a `broker` category that USA does not, and USA/DEU/GBR carry `option` where ASI does not.
Crawling a category a region does not have wastes calls; missing one a region does have silently
removes a whole cell from reach, which is the same failure as the `coverage >= 0.90` filter that
deleted five datasets outright (ITERATIONS.md I4b).

`count` from /data-fields saturates at 10000. A category reporting exactly that is truncated at
--max-per-cat and flagged, never recorded as a complete census.

  python3 tools/crawl_all_regions.py --plan state/crawl_plan.json --max-per-cat 1200
"""
import argparse, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="state/crawl_plan.json")
    ap.add_argument("--max-per-cat", type=int, default=1200)
    ap.add_argument("--skip", default="USA:1", help="comma list of region:delay already crawled")
    ap.add_argument("--universe", default="")
    args = ap.parse_args()

    skip = set()
    for s in args.skip.split(","):
        if ":" in s:
            r, d = s.split(":")
            skip.add((r.strip(), int(d)))

    plan = json.load(open(ROOT / args.plan))
    # Universe differs by region and a wrong one returns an empty crawl rather than an error.
    # These are the defaults the platform offers per region; TOP3000 does not exist outside USA.
    UNI = {"USA": "TOP3000", "GLB": "TOP3000", "EUR": "TOP2500", "ASI": "MINVOL1M",
           "CHN": "TOP2000U", "JPN": "TOP1600", "DEU": "TOP500", "GBR": "TOP500",
           "IND": "TOP500", "MEA": "TOP200", "AMR": "TOP600", "KOR": "TOP600",
           "TWN": "TOP500", "HKG": "TOP500"}

    for p in plan:
        key = (p["region"], p["delay"])
        if key in skip:
            print(f"== skip {key[0]} d{key[1]} (already have it)", flush=True)
            continue
        uni = args.universe or UNI.get(p["region"], "TOP500")
        print(f"\n== {p['region']} d{p['delay']} universe={uni} "
              f"({len(p['cats'])} categories)", flush=True)
        cmd = [sys.executable, str(ROOT / "tools/crawl_fields.py"),
               "--region", p["region"], "--delay", str(p["delay"]),
               "--universe", uni, "--cats", ",".join(p["cats"]),
               "--max-per-cat", str(args.max_per_cat)]
        try:
            subprocess.run(cmd, cwd=ROOT, timeout=3600)
        except subprocess.TimeoutExpired:
            print(f"   TIMEOUT on {key} -- moving on, partial rows are kept", flush=True)
        time.sleep(3)


if __name__ == "__main__":
    raise SystemExit(main())
