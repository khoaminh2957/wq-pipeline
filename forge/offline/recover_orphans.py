"""Recover the children of forge parents that were posted but never reaped (a crashed round).

MEASURED 2026-09-06 19:58: 117 forge parents (1,170 simulations, spent quota) had no child rows
because the round died on a ReadTimeout after posting them. The platform still holds every
result. A parent row carries only its formulas; the round's plan file (state/forge/plans/<seed>.json)
carries every construction with settings and meta, so a child is attributed by (echoed formula,
echoed settings) — the same discriminators the live child-order guard uses — and journalled as a
normal forge row. Rows that cannot be attributed are written with status ORPHAN-UNMATCHED and no
meta, never guessed. Idempotent: a parent with any child row is skipped.

  venv/bin/python forge/offline/recover_orphans.py [--limit N] [--dry]
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
JOURNAL = ROOT / "state/layered/runs/forge.jsonl"
PLANS = ROOT / "state/forge/plans"
DISCRIMINATORS = ("region", "universe", "delay", "neutralization", "decay", "truncation")
PACE_S = 1.1
ROUND_KEYS = ("seed",)      # per-round bookkeeping in meta; not part of a construction's identity


def _norm(f: str) -> str:
    return re.sub(r"\s+", "", f or "")


def load_plans(plans_dir=PLANS) -> dict:
    """{normalised formula: [construction, ...]} over every plan file."""
    idx = {}
    for p in glob.glob(str(pathlib.Path(plans_dir) / "*.json")):
        try:
            plan = json.load(open(p))
        except ValueError:
            continue
        for c in plan.get("constructions", []):
            idx.setdefault(_norm(c["formula"]), []).append(c)
    return idx


def _identity(c: dict) -> str:
    """What makes two plan entries the SAME simulation: everything except the round that planned it."""
    c = dict(c)
    c["meta"] = {k: v for k, v in (c.get("meta") or {}).items() if k not in ROUND_KEYS}
    return json.dumps(c, sort_keys=True)


def match(construction_index: dict, formula: str, settings: dict):
    """The unique construction whose formula and discriminating settings equal the platform's echo."""
    cands = construction_index.get(_norm(formula), [])
    hits = [c for c in cands if all(str(c["settings"].get(k)) == str((settings or {}).get(k))
                                    for k in DISCRIMINATORS if (settings or {}).get(k) is not None)]
    # The same construction written to two plan files (an experiment's own plan and the runner's
    # copy of it, 2026-09-06 C11) is one construction, not an ambiguity: 10 COMPLETE alphas were
    # filed ORPHAN-UNMATCHED because both files held them.
    # ROUND BOOKKEEPING IS NOT IDENTITY (2026-09-09): `meta.seed` is the round that planned the
    # construction, so the SAME construction re-planned in a later round read as two different
    # candidates and every child of it was filed ORPHAN-UNMATCHED. MEASURED that evening: 131
    # unmatched rows, ALL of them ambiguous, and the differing key was meta.seed on 163 of 187
    # candidate pairs; excluding it alone resolves 111 of the 131. `category` and `arm` are NOT
    # excluded: they change what the row means (the allocator's pair, the A/B arm), so a row
    # ambiguous on those stays unmatched rather than guessed (17 + 3 rows).
    distinct = {_identity(c) for c in hits}
    return hits[0] if len(distinct) == 1 else None


PLATFORM_TERMINAL = {"COMPLETE", "WARNING", "ERROR", "FAIL", "FAILED", "CANCELLED", "CANCELED", "ORPHAN-UNMATCHED"}


def orphans(journal=JOURNAL) -> list:
    """Parents with no child row that carries a platform answer. A child row whose status is this
    machine's own (AUTH-FAIL, POLL-DEADLINE, POLL-EXHAUSTED, MULTISIM-*) says the runner could not
    read the platform, not what the platform said — the parent is still an orphan (2026-09-07)."""
    parents, children = [], set()
    with open(journal) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") == "PARENT-POSTED" and r.get("parent_url"):
                parents.append(r)
            elif r.get("parent_url") and (r.get("alpha") or r.get("status") in PLATFORM_TERMINAL):
                children.add(r["parent_url"])
    return [p for p in parents if p["parent_url"] not in children]


def child_urls(pj: dict) -> list:
    out = []
    for c in pj.get("children") or []:
        url = c if isinstance(c, str) else (c.get("url") or c.get("id") or "")
        if url and not url.startswith("http"):
            url = "https://api.worldquantbrain.com/simulations/" + url
        out.append(url)
    return out


def recover(s, parent: dict, cidx: dict, scrape, get, sleep=time.sleep) -> list:
    """Journal rows for one orphan parent (list may be empty when the parent is not terminal)."""
    r = get(parent["parent_url"])
    if r is None or r.status_code != 200:
        return []
    pj = r.json()
    if (pj.get("status") or "").upper() not in ("COMPLETE", "WARNING", "ERROR", "FAIL", "FAILED"):
        return []
    rows = []
    for i, url in enumerate(child_urls(pj)):
        sleep(PACE_S)
        cr = get(url)
        if cr is None or cr.status_code != 200:
            continue
        rows.append(child_row(cr.json(), url, parent["parent_url"], i, cidx, scrape, sleep))
    return rows


def child_row(cj: dict, url: str, parent_url: str, i: int, cidx: dict, scrape, sleep=time.sleep) -> dict:
    """One journal row from a child simulation's payload (matched to its plan construction or not)."""
    echo = cj.get("regular")
    echo = echo.get("code") if isinstance(echo, dict) else echo
    st = (cj.get("status") or "").upper()
    con = match(cidx, echo or "", cj.get("settings") or {})
    alpha = cj.get("alpha") if st in ("COMPLETE", "WARNING") else None
    rec = {"status": st or "UNKNOWN", "alpha": alpha, "polls": 0, "message": cj.get("message") or "",
           "sim_url": url, "parent_url": parent_url, "child_index": i, "recovered_at": time.time(),
           "formula": (con or {}).get("formula") or echo, "settings": (con or {}).get("settings") or cj.get("settings"),
           "meta": (con or {}).get("meta")}
    if con is None:
        rec["status"] = "ORPHAN-UNMATCHED"
        rec["alpha"] = None
    elif alpha:
        sleep(PACE_S)
        rec.update(scrape(alpha))
    return rec


def unmatched(journal=JOURNAL) -> list:
    """ORPHAN-UNMATCHED rows whose simulation has no attributed row yet."""
    rows, attributed = [], set()
    with open(journal) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") == "ORPHAN-UNMATCHED" and r.get("sim_url"):
                rows.append(r)
            elif r.get("sim_url") and r.get("alpha"):
                attributed.add(r["sim_url"])
    return [r for r in rows if r["sim_url"] not in attributed]


def rematch(rows: list, cidx: dict, scrape, get, sleep=time.sleep) -> list:
    """Second pass over ORPHAN-UNMATCHED rows after the plan index (or match) changed."""
    out = []
    for r in rows:
        if match(cidx, r.get("formula") or "", r.get("settings") or {}) is None:
            continue
        sleep(PACE_S)
        cr = get(r["sim_url"])
        if cr is None or cr.status_code != 200:
            continue
        rec = child_row(cr.json(), r["sim_url"], r.get("parent_url"), r.get("child_index", 0), cidx, scrape, sleep)
        if rec["status"] != "ORPHAN-UNMATCHED":
            out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--rematch", action="store_true", help="retry the ORPHAN-UNMATCHED rows against the current plan files")
    a = ap.parse_args()
    import layered_sim as LS
    orph = orphans()[: a.limit]
    print("orphan parents: %d (limit %d)" % (len(orphans()), a.limit), flush=True)
    if a.dry or not (orph or a.rematch):
        return 0
    s = LS.session()
    LS.keep_jar_fresh(s)
    cidx = load_plans()

    def get(url):
        try:
            return LS._get_patient(s, url, timeout=40)
        except Exception:  # noqa: BLE001
            return None
    if a.rematch:
        todo = unmatched()
        rows = rematch(todo, cidx, lambda aid: LS.scrape(s, aid), get)
        with open(JOURNAL, "a") as jf:
            for rec in rows:
                jf.write(json.dumps(rec) + "\n")
        print("rematch: %d unmatched rows, %d attributed" % (len(todo), len(rows)))
    done = matched = 0
    with open(JOURNAL, "a") as jf:
        for p in orph:
            rows = recover(s, p, cidx, lambda aid: LS.scrape(s, aid), get)
            for rec in rows:
                jf.write(json.dumps(rec) + "\n")
                matched += rec["status"] != "ORPHAN-UNMATCHED"
            jf.flush()
            done += 1
            if done % 10 == 0:
                print("  %d parents, %d children attributed" % (done, matched), flush=True)
    print("recovered: %d parents, %d children attributed" % (done, matched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
