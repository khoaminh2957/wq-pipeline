#!/usr/bin/env python3
"""Measure the correlation backlog — the zero-fail alphas that were never checked.

WHY THIS IS THE HIGHEST-VALUE TOOL IN THE PIPELINE. Measured 2026-08-01 over the whole journal:

    zero-fail alphas found        2203
      correlation measured         435   -> 72 clean (16.6%)
      NEVER measured              1768   -> ~293 clean, at the same rate

Against that, four hours of fresh mining runs ~1381 sims -> ~41 zero-fail -> ~7 clean. The backlog
is worth roughly forty mining runs and it is already paid for. Generation was never the bottleneck;
MEASUREMENT was.

WHY THE BACKLOG EXISTS. /alphas/<id>/correlations/<kind> computes ON DEMAND: the first request
queues the work and answers 200 with an EMPTY body, and the payload is ready ~1-2 minutes later.
driver.py polls for 20-30s and gives up, so a first-look alpha essentially never resolves inside
its own round. Verified by hand on 3qeNwxKz: empty on the request that queued it, full payload one
second into the next request two minutes later.

So this tool does the opposite of polling. It TRIGGERS a whole batch, walks away, and comes back
when the work is done -- turning ~40s of dead waiting per alpha into ~1s.

Politeness: correlation reads and the simulation stream share one rate budget, and running both is
what produces the 429s that degrade into RemoteDisconnected. This yields to state/resim.lock and
sleeps between requests. It is meant to run ALONGSIDE the miner without starving it.

Usage:
  python3 tools/harvest_corr.py                 # whole backlog, resumable
  python3 tools/harvest_corr.py --limit 200     # one bite
  python3 tools/harvest_corr.py --batch 40 --wait 150
"""
import argparse, fcntl, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import gates                                                        # noqa: E402
from fetch_prod_corr import prod_maxcorr, self_maxcorr              # noqa: E402
sys.path.insert(0, str(ROOT / "tools" / "autoloop"))
import driver as _drv                                               # noqa: E402  ledger_write

ST = ROOT / "state"
PC = ST / "prod_corr_measured.json"
JOURNAL = ST / "resim_results.jsonl"
API = "https://api.worldquantbrain.com"


def session():
    import pickle, requests
    s = requests.Session()
    c = pickle.load(open(ST / "wq_cookies.pkl", "rb"))
    if isinstance(c, dict):
        s.cookies.update(c)
    else:
        for x in c:
            s.cookies.set_cookie(x)
    return s


def sim_running():
    """True while a simulation stream holds the lock. flock is released when its holder dies, so a
    stale lock FILE does not count -- only a live holder does."""
    f = ST / "resim.lock"
    if not f.exists():
        return False
    try:
        h = open(f, "a+")
    except OSError:
        return False
    try:
        fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(h, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        h.close()


def is_complete(rec):
    """Both sides measured. Derived from the FIELDS, not from a flag.

    driver.py writes into the same store and knows nothing about `complete`, and 489 entries
    predate the flag entirely. Trusting the flag alone would drag every one of them back into the
    backlog to be re-measured."""
    if not rec:
        return False
    return rec.get("prod_maxcorr") is not None and bool(rec.get("self_measured"))


def backlog():
    """Zero-fail alphas with no correlation on file, newest first — recent alphas matter most
    because a stale alpha's siblings may already be live."""
    store = json.load(open(PC)) if PC.exists() else {}
    seen, out = set(), []
    for line in JOURNAL.open():
        try:
            r = json.loads(line)
        except Exception:
            continue
        a = r.get("alpha")
        # An alpha with only one side measured is NOT done -- it must stay in the backlog.
        if not a or a in seen or is_complete(store.get(a)):
            continue
        ck = {c["name"]: c for c in (r.get("checks") or [])
              if isinstance(c, dict) and "name" in c}
        if not ck:
            continue
        # ANY FAIL, not just the BLOCKING allowlist — see gates.hard_fails.
        if gates.hard_fails(r.get("checks")):
            continue
        seen.add(a)
        out.append((a, {"sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
                        "old_id": r.get("old_id")}))
    out.reverse()
    return out


def trigger(s, aid):
    """Queue both recordsets and hang up. A 200 with an empty body is the point of this call."""
    for kind in ("prod", "self"):
        try:
            s.get(f"{API}/alphas/{aid}/correlations/{kind}", timeout=10)
        except Exception:
            pass


def read_one(s, aid, budget=12.0, have=None):
    """Read whatever is ready, and KEEP IT.

    The two sides do not resolve together: sampling six ripened alphas found prod available on
    three and self on only two. Requiring both threw away every prod measurement whose self was
    still computing and sent the alpha back to the end of the queue, so an alpha could be
    triggered repeatedly and never finish. Partial results now merge into whatever is already on
    file, and `corr_ok` is only decided once both sides are in -- an alpha with one side measured
    is still NOT clean, it is simply further along."""
    out = dict(have or {})
    for kind in ("prod", "self"):
        if kind == "prod" and out.get("prod_maxcorr") is not None:
            continue
        if kind == "self" and out.get("self_measured"):
            continue
        t0, j = time.time(), None
        while time.time() - t0 < budget:
            try:
                r = s.get(f"{API}/alphas/{aid}/correlations/{kind}", timeout=20)
            except Exception:
                time.sleep(2)
                continue
            if r.status_code == 429:
                time.sleep(10)
                continue
            if r.status_code != 200:
                break
            if r.text:
                try:
                    j = r.json()
                except Exception:
                    j = None
                    break
                if isinstance(j, dict) and "schema" in j:
                    break
            time.sleep(2)
        if not (isinstance(j, dict) and j.get("records")):
            continue                              # still computing — keep the other side
        if kind == "prod":
            pc, breach = prod_maxcorr(j)
            if pc is not None:
                out["prod_maxcorr"], out["prod_breach_count"] = pc, breach
        else:
            out["self_maxcorr"] = self_maxcorr(j)
            # Rows came back, but a number may not have. corr_ok below treats a None self as a
            # pass, so flagging "measured" on rows alone reopens the hole.
            out["self_measured"] = out["self_maxcorr"] is not None
    if not out:
        return None
    complete = is_complete(out)
    out["complete"] = complete
    # Never let a half-measured alpha read as clean: the self side is exactly what catches a
    # duplicate of something already live.
    sc = out.get("self_maxcorr")
    out["corr_ok"] = bool(complete and out["prod_maxcorr"] <= 0.7 and (sc is None or sc < 0.7))
    return out


def save(store):
    tmp = PC.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(store, f, indent=1)
    tmp.replace(PC)


TRIG = ST / "corr_triggered.json"


def _load_triggered():
    try:
        return json.load(open(TRIG))
    except Exception:
        return {}


def _save_triggered(d):
    tmp = TRIG.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(d, f)
    tmp.replace(TRIG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=120, help="new alphas triggered per pass")
    ap.add_argument("--ripen", type=float, default=2700.0,
                    help="seconds an alpha must sit after triggering before it is worth reading")
    ap.add_argument("--pass-gap", type=float, default=300.0, help="seconds between passes")
    ap.add_argument("--reads", type=int, default=150,
                    help="max alphas READ per pass — an uncapped read phase never finishes")
    ap.add_argument("--gap", type=float, default=0.4, help="seconds between requests")
    ap.add_argument("--passes", type=int, default=0, help="stop after N passes (0 = forever)")
    ap.add_argument("--ignore-sim", action="store_true", help="do not yield to the sim stream")
    args = ap.parse_args()

    # Continuous cycle, not one shot. The platform computes these recordsets on demand and takes
    # far longer than a round: a 90s wait measured 0/12, while PY round 2 read 19 alphas in 100
    # seconds because round 1 had triggered them ~50 minutes earlier. So each pass READS whatever
    # has ripened and TRIGGERS a fresh batch, and the ripening happens while the miner works.
    # Resumable by design: the triggered set is on disk, so a restart never re-triggers or forgets.
    s = session()
    npass = 0
    while True:
        npass += 1
        store = json.load(open(PC)) if PC.exists() else {}
        trig = _load_triggered()
        now = time.time()

        # Prune ids that were measured elsewhere (the driver measures too). Without this the
        # triggered file only ever grows: 23 already-measured ids were still sitting in it.
        before = len(trig)
        trig = {a: t for a, t in trig.items() if not is_complete(store.get(a))}
        if len(trig) != before:
            print(f"  pruned {before - len(trig)} already-measured ids from the triggered set",
                  flush=True)
        # Cap the read phase and take the OLDEST triggers first. Uncapped, the first pass faced
        # 994 ripe alphas at ~18s each -- 298 minutes in a single phase, during which nothing is
        # written and no new batch is triggered. A pass that never ends is a pass that never saves.
        ripe = sorted((a for a, t in trig.items() if now - t >= args.ripen),
                      key=lambda a: trig[a])[:args.reads]
        meta_by_id = dict(backlog())          # sharpe/fitness/old_id for the ledger row
        read = clean = 0
        for i, aid in enumerate(ripe):
            # Yield to the sim stream OCCASIONALLY, not per alpha. Sleeping 30s before every read
            # while the miner ran turned a 150-alpha pass into 135 minutes -- and the sleep bought
            # nothing: pausing the miner entirely was measured and left correlation availability
            # unchanged at 1/8. A read is one cheap GET; the throttle belongs on the batch.
            if not args.ignore_sim and i % 25 == 0 and sim_running():
                time.sleep(10)
            m = read_one(s, aid, have=store.get(aid))
            if m is None:
                continue
            store[aid] = m
            if is_complete(m):
                trig.pop(aid, None)
                read += 1
            # Checkpoint on WORK DONE. `read % 20` fired on every iteration while read was 0 and
            # never once it started climbing -- exactly backwards.
            if i % 20 == 19:
                save(store)
                _save_triggered(trig)
            if m["corr_ok"]:
                clean += 1
                # Standing rule: every zero-fail winner reaches winners.csv. This tool measures
                # gems the driver never saw, so without this they would be found and then lost --
                # the ledger is what a human picks from later.
                try:
                    _drv.ledger_write(aid, meta_by_id.get(aid, {}), m["prod_maxcorr"],
                                      m.get("self_maxcorr"), m.get("prod_breach_count"),
                                      True, "harvest")
                except Exception as e:
                    print(f"    ! ledger_write failed for {aid}: {str(e)[:60]}", flush=True)
                print(f"    CLEAN {aid}  prod={m['prod_maxcorr']} self={m['self_maxcorr']}",
                      flush=True)
            time.sleep(args.gap)
        if read:
            save(store)

        todo = [a for a, _ in backlog() if a not in trig]
        fresh = todo[:args.batch]
        for aid in fresh:
            trigger(s, aid)
            trig[aid] = time.time()
            time.sleep(args.gap)
        _save_triggered(trig)

        print(f"[pass {npass}] ripe={len(ripe)} read={read} clean={clean} | "
              f"triggered {len(fresh)} new | in-flight={len(trig)} backlog={len(todo)}", flush=True)
        if args.passes and npass >= args.passes:
            break
        if not todo and not trig:
            print("backlog empty", flush=True)
            break
        time.sleep(args.pass_gap)


if __name__ == "__main__":
    main()
