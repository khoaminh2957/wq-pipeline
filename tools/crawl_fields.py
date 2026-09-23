#!/usr/bin/env python3
"""Re-crawl the platform's data-fields for a region/delay into the file the generators read.

Why this exists. `fetched/fields_all.jsonl` was the only field inventory the pipeline had, and on
2026-08-06 it turned out to cover NINE categories when the platform serves fourteen for USA/D1.
The cells that mattered were the ones missing:

    category          crawl file      platform
    imbalance                  0             2
    insiders                   0           185
    shortinterest              0           110
    socialmedia               33           219
    sentiment                 19         1,207
    news                   1,757         2,664

So every pool aimed at Sentiment was drawing from 19 fields out of 1,207, and Insiders and Short
Interest could not be mined at all. That is not a structure problem or a signal problem; it is an
inventory problem, and it explains a stretch of mining that produced strong alphas in the cells it
could see and nothing at all in the cells it could not.

`count` from this endpoint SATURATES AT 10000 — analyst, fundamental, model, pv and other all
report exactly that, which is the cap and not a measurement (the same trap as /data-fields' 10,000
ceiling recorded in the transient-read memory). Paging past it is pointless, so a category at the
cap is crawled to `--max-per-cat` and marked truncated rather than reported as complete.

Rows are written in the same shape `gen_pyramid.load_fields()` expects: `region`, `_delay`,
`category` as {id,name}, `coverage`, `type`, `description`, `dataset`, `subcategory`.

  python3 tools/crawl_fields.py --region USA --delay 1 --cats insiders,sentiment,news
"""
import argparse, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
API = "https://api.worldquantbrain.com/data-fields"
PAGE = 50
CAP = 10000                       # the endpoint's own ceiling; a count equal to it is not a count

NAMES = {"pv": "Price Volume", "socialmedia": "Social Media", "shortinterest": "Short Interest",
         "imbalance": "Imbalance", "insiders": "Insiders", "news": "News", "risk": "Risk",
         "macro": "Macro", "other": "Other", "institutions": "Institutions", "model": "Model",
         "analyst": "Analyst", "earnings": "Earnings", "fundamental": "Fundamental",
         "option": "Option", "sentiment": "Sentiment"}


def crawl(s, cat, region, delay, universe, max_per_cat):
    base = (f"{API}?instrumentType=EQUITY&region={region}&delay={delay}"
            f"&universe={universe}&category={cat}")
    out, off, total = [], 0, None
    while True:
        for attempt in range(4):
            r = s.get(f"{base}&limit={PAGE}&offset={off}", timeout=60)
            if r.status_code == 200 and r.text.strip():
                break
            time.sleep(4 * (attempt + 1))
        else:
            print(f"  {cat}: giving up at offset {off}", flush=True)
            break
        try:
            j = r.json()
        except Exception:
            break
        if total is None:
            total = j.get("count")
        res = j.get("results") or []
        if not res:
            break
        for f in res:
            out.append({"id": f.get("id"), "description": f.get("description") or "",
                        "dataset": f.get("dataset"), "category": {"id": cat, "name": NAMES.get(cat, cat)},
                        "subcategory": f.get("subcategory"), "type": f.get("type"),
                        "coverage": f.get("coverage"), "userCount": f.get("userCount"),
                        "alphaCount": f.get("alphaCount"),
                        "region": region, "_delay": delay, "universe": universe})
        off += PAGE
        if len(out) >= min(max_per_cat, total or max_per_cat):
            break
    return out, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="USA")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--universe", default="TOP3000")
    ap.add_argument("--cats", required=True, help="comma-separated category ids")
    ap.add_argument("--out", default="fetched/fields_all.jsonl")
    ap.add_argument("--max-per-cat", type=int, default=3000)
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    import submit_alphas as SA
    s = SA.session()

    dest = ROOT / args.out
    have = set()
    if dest.exists():
        for line in open(dest):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if isinstance(r, dict) and r.get("id"):
                have.add((r["id"], r.get("region"), r.get("_delay")))
    print(f"{dest}: {len(have)} (id,region,delay) da co")

    added = 0
    with open(dest, "a") as fh:
        for cat in args.cats.split(","):
            cat = cat.strip()
            rows, total = crawl(s, cat, args.region, args.delay, args.universe, args.max_per_cat)
            n = 0
            for r in rows:
                k = (r["id"], r["region"], r["_delay"])
                if k in have:
                    continue
                have.add(k)
                fh.write(json.dumps(r) + "\n")
                n += 1
            added += n
            flag = "  (TRUNCATED at the API cap — count is not a count)" if total == CAP else ""
            print(f"  {cat:16} count={total} crawled={len(rows)} new={n}{flag}", flush=True)
    print(f"\nda them {added} dong moi vao {dest}")


if __name__ == "__main__":
    raise SystemExit(main())
