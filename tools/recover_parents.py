"""Harvest simulations that were already paid for and never collected. Costs no quota.

WHY THIS EXISTS, this time. `_child_row` indexed `meta["n_legs"]` directly. A climb row has no such
key, so the line raised on the FIRST harvested child of every round: the parents had already been
posted, the ten simulations under each had already been spent, and the round then died before
collecting any of them. The loop restarted and did it again -- fourteen times in twenty-five
minutes, **81 parents, 810 simulations**, of which 13 rows carry a result.

Nothing is lost, only unclaimed. Every abandoned row journals `parent_url`, the platform keeps the
finished parents, and re-reading them is a GET. This is the same route that once recovered 1,496
rows at zero quota cost.

THE THREE WAYS THIS HAS BEEN GOT WRONG BEFORE, all of them here as code rather than as advice:

  * `poll_parent` returns child IDs, not URLs. Treating them as URLs yields a 404 per child, and
    the original attempt swallowed it in a bare `except Exception: continue` and reported a clean
    zero. Children are resolved through `child_url()`.
  * A shared `requests.Session` across threads produced silent cross-talk. This runs single
    threaded; it is a GET loop and there is nothing to gain by racing it.
  * The journal key is `formulas` on a parent row, not `group`. Reading the wrong key harvested
    nothing and looked like the platform had lost the work.

**IT NEVER POSTS.** Recovery is reading. A test walks the module for POST verbs.
"""

import argparse
import glob
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layered_sim as LS  # noqa: E402


def orphans(patterns):
    """Every journalled parent that never produced a child row, newest first.

    A parent is orphaned when its url appears on a PARENT-POSTED (or POLL-EXHAUSTED) row and no row
    in the same files carries that url as `parent_url` with a real status.
    """
    posted, harvested = {}, set()
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
                if not line.startswith("{"):
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                url = r.get("parent_url") or r.get("sim_url")
                if not url:
                    continue
                if r.get("status") in ("PARENT-POSTED", "POLL-EXHAUSTED"):
                    posted[url] = {"formulas": r.get("formulas") or [],
                                   "n_children": r.get("n_children"), "file": path}
                elif r.get("parent_url"):
                    harvested.add(r["parent_url"])
    return {u: v for u, v in posted.items() if u not in harvested}


def recover(out_path, patterns, limit=None, out=print):
    todo = orphans(patterns)
    out("%d orphaned parent(s) carrying up to %d simulations"
        % (len(todo), sum(v.get("n_children") or 0 for v in todo.values())))
    if not todo:
        return 0

    s = LS.session()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_rows = 0
    with out_path.open("a") as jf:
        for i, (url, info) in enumerate(sorted(todo.items())):
            if limit and i >= limit:
                break
            # `wait_first=False`: these parents were posted long ago. The initial sleep exists to
            # avoid asking a fresh handle a question whose answer cannot have changed yet, and that
            # reason does not apply to a parent from an hour ago.
            st, children, polls, msg = LS.poll_parent(s, url, wait_first=False)
            if st == "AUTH-FAIL":
                out("  AUTH-FAIL at parent %d -- stopping, nothing is lost" % i)
                break
            if not children:
                out("  %-16s %s  (no children named) %s" % (st, url[-24:], msg[:60]))
                continue
            forms = info.get("formulas") or []
            for k, child in enumerate(children):
                curl = LS.child_url(child)
                cst, alpha, cpolls, cmsg = LS.poll(s, curl, wait_first=False)
                rec = {"status": cst, "alpha": alpha, "polls": polls + cpolls, "message": cmsg,
                       "sim_url": curl, "parent_url": url, "child_index": k,
                       "formula": forms[k] if k < len(forms) else None,
                       "meta": {"move": "recovered", "source_file": info.get("file")},
                       "settings": None, "recovered_at": time.time()}
                if alpha:
                    rec.update(LS.scrape(s, alpha))
                jf.write(json.dumps(rec) + "\n")
                jf.flush()
                n_rows += 1
            out("  %-16s %s -> %d child rows" % (st, url[-24:], len(children)))
    out("recovered %d row(s) into %s at zero quota cost" % (n_rows, out_path))
    return n_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--glob", action="append",
                    default=None, help="journal glob(s) to scan; repeatable")
    ap.add_argument("--out", default=str(ROOT / "state/layered/runs/recovered.jsonl"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--list", action="store_true", help="show what would be recovered and exit")
    a = ap.parse_args()

    pats = a.glob or [str(ROOT / "state/layered/runs/climb_*.jsonl"),
                      str(ROOT / "state/layered/runs/gap_*.jsonl")]
    if a.list:
        todo = orphans(pats)
        print("%d orphaned parent(s), up to %d simulations"
              % (len(todo), sum(v.get("n_children") or 0 for v in todo.values())))
        for u, v in sorted(todo.items())[:20]:
            print("  %s  n_children=%s  %s" % (u[-30:], v.get("n_children"),
                                               pathlib.Path(v["file"]).name))
        return 0
    recover(pathlib.Path(a.out), pats, limit=a.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
