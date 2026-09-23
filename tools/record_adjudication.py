#!/usr/bin/env python3
"""Record the platform's adjudication of every POSTed alpha into the submitted ledger.

WHY: notify_lint's standing finding -- the one real submission (mL516W9W, http=201) is ACTIVE on
the platform and no file on either machine records that. A 404 from /alphas/{id}/submit is the
union of "never POSTed" and "POSTed, landed, finished", so without this record an operator holding
the ledger and a 404 could be led to re-POST -- the 403 that spends the alpha forever.

The only disambiguator is GET /alphas/{id} -> status / dateSubmitted, so that is what is written.
READ ONLY against the platform; appends `adjudication` rows to the ledger, never rewrites.
"""
import json
import pathlib
import sys
import time

# Every ledger that records a POST: the climb's and, since 2026-09-04, the forge's (forge/submit.py).
LEDGERS = (pathlib.Path("/opt/wq/state/climb/submitted.jsonl"),
           pathlib.Path("/opt/wq/state/forge/submitted.jsonl"))

# A status the platform will not change again. Everything else is a snapshot of an alpha still being
# adjudicated, and must be read again.
#
# MEASURED 2026-09-20: vRk1J2jd was POSTed on 09-10 and this tool recorded `UNSUBMITTED` -- the state
# it was in for the minutes before the platform finished. Because ANY adjudication row used to mean
# "done", that snapshot was never revisited, and for ten days the ledger said the alpha had been
# refused. It is ACTIVE, stage OS, fitness 1.16 -- the strongest alpha this desk holds and the first
# one the new supply chain produced. A transient condition was written down as a permanent fact.
TERMINAL = {"ACTIVE", "DECOMMISSIONED", "EXPIRED", "REJECTED", "FAILED"}


def pending(rows) -> set:
    """Alphas with an accepted POST whose LAST recorded adjudication is not terminal (or absent)."""
    posted = {r["alpha"] for r in rows if r.get("alpha") and r.get("http") in (200, 201)}
    last = {}
    for r in rows:                                  # file order: the last row for an alpha wins
        if r.get("kind") == "adjudication" and r.get("alpha"):
            last[r["alpha"]] = (r.get("status") or "").upper()
    return {a for a in posted if last.get(a) not in TERMINAL}


def main():
    todo, n_posted = [], 0
    s = None
    for LEDGER in LEDGERS:
        if not LEDGER.exists():
            continue
        rows = []
        for ln in LEDGER.read_text().splitlines():
            try:
                rows.append(json.loads(ln))
            except ValueError:
                pass
        n_posted += len({r["alpha"] for r in rows if r.get("alpha") and r.get("http") in (200, 201)})
        todo.extend((aid, LEDGER) for aid in sorted(pending(rows)))
    if not todo:
        print("adjudication: nothing to record (%d posted, all terminal)" % n_posted)
        return 0
    sys.path.insert(0, "/opt/wq/tools")     # imported here, not at module load, so `pending` is testable anywhere
    import layered_sim as LS

    s = LS.session()
    for aid, LEDGER in todo:
        r = s.get("%s/alphas/%s" % (LS.API, aid), timeout=30)
        if r.status_code != 200:
            print("adjudication: %s -> HTTP %d, not recording" % (aid, r.status_code))
            continue
        j = r.json()
        rec = {"kind": "adjudication", "alpha": aid, "at": time.time(),
               "status": j.get("status"), "stage": j.get("stage"), "dateSubmitted": j.get("dateSubmitted"),
               "dateCreated": j.get("dateCreated"), "grade": j.get("grade")}
        with LEDGER.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        final = (j.get("status") or "").upper() in TERMINAL
        print("adjudication: %s status=%s stage=%s -- recorded%s"
              % (aid, j.get("status"), j.get("stage"), "" if final else " (not terminal; will re-read)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
