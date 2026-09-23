"""Refresh state/pyramid_cell_counts.json from the platform's own counter (design §2: the
activity counter is the ONLY source of alphaCount). Schema "pairs" (what forge.cells reads):
  {"pairs": [{"region", "delay", "granularity": "category", "counts": {category: alphaCount}, "source": "live", "reads": 1}], "ts": ...}
Runs on the VPS with the cookie jar; called by forge_loop.sh after every POST and once a day.
The climb's crawler (harness13/crawl_pyramid.py) runs in a SIMULATED fixture mode and must not be
used for this — measured 2026-09-06: it printed "SIMULATED-FIXTURE(counts of USA d1 read 2026-08-10)".
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
PATH = ROOT / "state/pyramid_cell_counts.json"
ENDPOINT = "/users/self/activities/pyramid-alphas"


def pairs_from_payload(payload) -> list:
    """Every (region, delay) pair with its {category: alphaCount}; raises on a malformed row so a
    dropped row can never read as an empty cell."""
    rows = payload.get("pyramids") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("payload carries no 'pyramids' list")
    by = {}
    for i, row in enumerate(rows):
        cat = row.get("category")
        name = cat.get("name") if isinstance(cat, dict) else cat
        region, delay, n = row.get("region"), row.get("delay"), row.get("alphaCount")
        if not name or not region or delay is None or not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError("pyramids[%d] incomplete: %r" % (i, row))
        counts = by.setdefault((str(region), int(delay)), {})
        counts[str(name)] = max(int(n), counts.get(str(name), 0))
    return [{"region": r, "delay": d, "granularity": "category", "counts": c, "source": "live", "reads": 1}
            for (r, d), c in sorted(by.items())]


def write(pairs: list, path=PATH) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".cells_")
    with open(fd, "w") as fh:
        json.dump({"pairs": pairs, "ts": time.time()}, fh)
    pathlib.Path(tmp).replace(path)


def main() -> int:
    import layered_sim as LS
    s = LS.session()
    r = s.get(LS.API + ENDPOINT, timeout=30)
    if r.status_code != 200:
        print("pyramid refresh: HTTP %d, file untouched" % r.status_code)
        return 1
    pairs = pairs_from_payload(r.json())
    write(pairs)
    usa = next((p["counts"] for p in pairs if p["region"] == "USA" and p["delay"] == 1), {})
    print("pyramid refresh: %d pairs written; USA/d1 empty cells: %s" % (
        len(pairs), sorted(k for k, v in usa.items() if v < 3)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
