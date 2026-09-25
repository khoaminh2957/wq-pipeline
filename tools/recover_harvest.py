"""Harvest, in parallel, the simulations that were dispatched and never read.

WHY THEY EXIST: `layered_sim.py` was shipped to the VPS calling a 3-argument `child_mismatch` while
the VPS `simulate.py` still held the 2-argument definition. The TypeError fired inside `_reap` --
AFTER the POST, BEFORE the harvest -- so 25 consecutive batches POSTed ten children each and read
none. `PARENT-POSTED` rows kept appearing, so the loop looked alive for 1h47m.

THE DATA IS NOT LOST. Every parent handle was journalled with its ten formulas BEFORE the first
poll, which is why that line exists. A spot check GET on 5 parents found 5/5 COMPLETE, 50/50
children terminal, and all four settings arms present in the platform's own echo.

WHY PARALLEL: the serial version timed out at 10 minutes having read a handful of parents. Each
child is one GET and they are independent, so the wall clock is a thread-count problem, not a
platform one. Capped well under the account's 60 req/min shared limit.

META IS GONE and is not reconstructed. The journal kept formula strings, not the per-leg draw, so a
recovered row can be scored on metrics and CANNOT enter any structural comparison. Re-running the
composer to re-derive meta would be a guess wearing a record's clothes.
"""
import concurrent.futures as cf
import glob
import json
import sys
import threading

sys.path.insert(0, "/opt/wq/tools")
sys.path.insert(0, "/opt/wq")
import layered_sim as L

OUT = "/opt/wq/state/layered/runs/recovered.jsonl"
WORKERS = 12

# ALREADY-HARVESTED PARENTS ARE SKIPPED. Re-polling them costs nothing on the platform but
# doubles rows in the journal, and a duplicated row is a silently inflated denominator.
done = set()
try:
    for line in open(OUT, errors="ignore"):
        if line.startswith("{"):
            try:
                done.add(json.loads(line).get("parent_url"))
            except ValueError:
                pass
except OSError:
    pass

parents, seen = [], set(x for x in done if x)
for f in sorted(glob.glob("/opt/wq/state/layered/runs/*.jsonl")):
    for line in open(f, errors="ignore"):
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("status") == "PARENT-POSTED" and r.get("parent_url") and r.get("formulas"):
            if r["parent_url"] not in seen:
                seen.add(r["parent_url"])
                parents.append(r)
print("  %d parent handles, %d child formulas" % (
    len(parents), sum(len(p["formulas"]) for p in parents)), flush=True)

# ONE SESSION PER THREAD. Twelve workers sharing a single `requests.Session` harvested ZERO rows in
# twelve minutes while a single direct GET on the same parent answered COMPLETE with ten children in
# 1.1 s. `Session` is not thread-safe: its connection pool serialises the workers against each
# other, so the parallelism was nominal. Thread-local sessions is the fix; the shared cookie jar is
# read once and copied, so no additional auth happens.
_tl = threading.local()


def sess():
    if not hasattr(_tl, "s"):
        _tl.s = L.session()
    return _tl.s


lock = threading.Lock()
jf = open(OUT, "a")
stats = {"alive": 0, "gone": 0, "rows": 0}


def one_parent(p):
    try:
        s = sess()
        pst, children, _polls, msg = L.poll_parent(s, p["parent_url"], wait_first=False)
    except Exception as e:
        with lock:
            stats["gone"] += 1
        return
    g = p["formulas"]
    if not children or len(children) != len(g):
        with lock:
            stats["gone"] += 1
        return
    with lock:
        stats["alive"] += 1
    for fm, ref in zip(g, children):
        # `poll_parent` hands back child IDs, not urls. Passing one straight to `poll` raises
        # `MissingSchema` -- which the bare `except Exception: continue` below swallowed, so the
        # harvest reported ZERO rows with no error anywhere. `child_url` is the function the normal
        # dispatch path already uses for exactly this.
        url = L.child_url(ref)
        if not url:
            continue
        try:
            st, aid, np_, m2 = L.poll(s, url, wait_first=False)
        except Exception as e:
            with lock:
                if stats["rows"] == 0 and stats.setdefault("shown", 0) < 3:
                    stats["shown"] += 1
                    print("  child poll failed: %s: %s" % (type(e).__name__, e), flush=True)
            continue
        row = {"status": st, "alpha": aid, "polls": np_, "message": m2, "sim_url": url,
               "parent_url": p["parent_url"], "formula": fm, "meta": None, "recovered": True}
        if aid:
            try:
                row.update(L.scrape(s, aid))
            except Exception:
                pass
        with lock:
            jf.write(json.dumps(row) + "\n")
            jf.flush()
            stats["rows"] += 1
            if stats["rows"] % 100 == 0:
                print("  ...%d rows harvested" % stats["rows"], flush=True)


with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
    list(ex.map(one_parent, parents))
jf.close()
print("  parents held %d | gone %d | ROWS HARVESTED %d"
      % (stats["alive"], stats["gone"], stats["rows"]), flush=True)
