"""forge.offline.survey_datasets — GET /data-sets for every pyramid pair (region, delay) that has a
field catalogue on disk and is not yet in fetched/rc/datasets_survey.json. Runs on the VPS with
the existing cookie jar; writes after every segment. ~5 pages of 50 per segment, 1.1 s apart.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import layered_sim as LS  # noqa: E402

API = "https://api.worldquantbrain.com"
OUT = ROOT / "fetched/rc/datasets_survey.json"
SEG_RE = re.compile(r"^([A-Z]+)_(.+)_d([01])$")


def _size(universe: str) -> int:
    m = re.search(r"TOP(\d+)", universe)
    if m:
        return int(m.group(1))
    return 100_000 if universe == "MINVOL1M" else 10_000


def pairs_on_disk() -> dict:
    segs = {}
    for p in (ROOT / "fetched/rc/fields").glob("*_d[01].jsonl"):
        m = SEG_RE.match(p.stem)
        if m:
            segs.setdefault((m.group(1), int(m.group(3))), []).append(m.group(2))
    return segs


def fetch(s, region, delay, universe):
    out, offset = [], 0
    while True:
        r = s.get(API + "/data-sets", params={"instrumentType": "EQUITY", "region": region, "delay": delay,
                                              "universe": universe, "limit": 50, "offset": offset}, timeout=60)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 5))
            continue
        r.raise_for_status()
        j = r.json()
        res = j.get("results") or []
        out.extend(res)
        offset += len(res)
        if not res or offset >= int(j.get("count") or 0):
            return out
        time.sleep(1.1)


def main() -> int:
    survey = json.load(open(OUT)) if OUT.exists() else {}
    have_region_universe = {}
    for seg in survey:
        m = SEG_RE.match(seg)
        if m:
            have_region_universe.setdefault(m.group(1), m.group(2))
    s = LS.session()
    LS.keep_jar_fresh(s)
    todo = []
    for (region, delay), universes in sorted(pairs_on_disk().items()):
        universe = have_region_universe.get(region) if have_region_universe.get(region) in universes else max(universes, key=_size)
        seg = "%s_%s_d%d" % (region, universe, delay)
        if seg not in survey:
            todo.append((seg, region, delay, universe))
    print("segments to fetch:", [t[0] for t in todo])
    for seg, region, delay, universe in todo:
        try:
            rows = fetch(s, region, delay, universe)
        except Exception as e:  # noqa: BLE001
            print("%s: FAILED %s" % (seg, e))
            continue
        survey[seg] = rows
        OUT.write_text(json.dumps(survey))
        cats = {}
        for r in rows:
            c = r.get("category"); c = c.get("name") if isinstance(c, dict) else c
            cats[c] = cats.get(c, 0) + 1
        print("%s: %d datasets, %d categories" % (seg, len(rows), len(cats)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
