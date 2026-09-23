#!/usr/bin/env python3
"""One machine-readable snapshot of the whole pipeline, plus rule-based alerts.

WHY. Supervising this pipeline currently means parsing 12 driver logs, 11 watchdog logs and 8 state
files by hand -- 67 throwaway parse scripts were written in a single session to answer questions
like "is it stuck" and "why did that round produce nothing". That is the wrong interface for ANY
supervisor. A small local model asked to reason over raw logs will do it badly; the same model
given this snapshot and the alert list can run the monitoring tier reliably. It also makes the
expensive supervisor cheaper, because "sao r" stops costing a log-archaeology session.

Deliberately NO judgement lives here. Every field is measured and every alert is a threshold. What
to DO about an alert is the supervisor's problem -- keeping that boundary is what makes the output
safe to hand to a cheaper model.

  python3 tools/pipeline_status.py            # human summary
  python3 tools/pipeline_status.py --json     # snapshot for a supervisor
  python3 tools/pipeline_status.py --alerts   # only the things that need a decision
"""
import argparse, datetime, fcntl, json, os, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
ST = ROOT / "state"
AL = ST / "autoloop"
sys.path.insert(0, str(ROOT / "tools" / "funnel"))

STALE_JOURNAL_MIN = 20          # no new sim row for this long while a driver is up
DRY_ROUNDS = 3                  # rounds with zero-fails but no clean gem


def _procs(pattern):
    try:
        out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout
        return [int(x) for x in out.split()]
    except Exception:
        return []


def _lock_held():
    f = ST / "resim.lock"
    if not f.exists():
        return None
    try:
        h = open(f, "a+")
    except OSError:
        return None
    try:
        fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(h, fcntl.LOCK_UN)
        return False                       # file exists but nobody holds it = stale
    except OSError:
        return True
    finally:
        h.close()


def _latest_driver_log():
    logs = sorted(AL.glob("driver_*.log"), key=os.path.getmtime)
    return logs[-1] if logs else None


def _run_state():
    log = _latest_driver_log()
    out = {"log": str(log) if log else None, "pids": _procs("autoloop/driver.py"),
           "watchdog_pids": _procs("autoloop/watchdog.py"),
           "sim_pids": _procs("run_multisim.py"), "harvester_pids": _procs("harvest_corr.py")}
    if not log:
        return out
    txt = log.read_text()
    m = re.findall(r"--- ROUND (\d+)/(\d+)\s+size=(\d+)\s+([\d.]+)h left ---", txt)
    if m:
        out["round"], out["rounds_total"] = int(m[-1][0]), int(m[-1][1])
        out["round_size"], out["hours_left"] = int(m[-1][2]), float(m[-1][3])
    tag = re.findall(r"launch=(\d+)", txt)
    out["launch"] = tag[-1] if tag else None
    done = re.findall(r"R(\d+) DONE: zero-fail (\d+)/(\d+) clean (\d+)", txt)
    out["rounds_done"] = [{"round": int(a), "zero_fail": int(b), "n": int(c), "clean": int(d)}
                          for a, b, c, d in done]
    out["finished"] = "=== FINAL ===" in txt
    return out


def _journal_age_min():
    j = ST / "resim_results.jsonl"
    return round((time.time() - j.stat().st_mtime) / 60, 1) if j.exists() else None


def _measurement():
    def _n(p):
        try:
            return len(json.load(open(p)))
        except Exception:
            return 0
    store_p = ST / "prod_corr_measured.json"
    store = json.load(open(store_p)) if store_p.exists() else {}
    return {"measured_total": len(store),
            "clean_total": sum(1 for v in store.values() if v.get("corr_ok")),
            "parked_in_driver": _n(AL / "corr_pending.json"),
            "triggered_in_flight": _n(ST / "corr_triggered.json")}


def _submit():
    out = {"submitted_ok": 0, "quota": None, "cells": None}
    p = ST / "funnel/submit_log.jsonl"
    if p.exists():
        seen = set()
        for line in p.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("ok") and d.get("status") == 200:
                seen.add(d["alpha"])
        out["submitted_ok"] = len(seen)
    try:
        out["quota"] = json.load(open(ST / "submit_quota_seen.json"))
    except Exception:
        pass
    # Read the cell counts LIVE. Nothing refreshes this cache except a submit run, so the status
    # report was answering from a 557-minute-old snapshot on 2026-08-02: it showed Analyst as
    # UNLOCKED when the platform had it at 2/3, and Earnings/Fundamental needing 1 when both
    # needed 2. Planning four irreversible submits off that would have completed ONE cell where
    # two were available.
    counts, age = {}, None
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import submit_alphas as _SA
        counts, src = _SA._cell_counts(_SA.session(), "USA", 1)
        age = 0.0 if src == "live" else None
    except Exception:
        pass
    if not counts:
        try:
            c = json.load(open(ST / "pyramid_cell_counts.json"))
            counts, age = c.get("counts", {}), round((time.time() - c["ts"]) / 60, 1)
        except Exception:
            pass
    if counts:
        # Add cells filled by TODAY's submits that the platform has not credited yet -- the counter
        # flaps back to a lagging replica for minutes after a submit, so without this the report
        # showed Earnings/Fundamental/Institutions as still short right after they were closed.
        try:
            counts = dict(counts)
            for _c, _n in _SA._submitted_today_by_cell(counts).items():
                counts[_c] = counts.get(_c, 0) + _n
        except Exception:
            pass
        # `0 < v < 3` dropped every cell at ZERO -- the eight emptiest cells, the ones with the
        # most room, were the only ones the report never mentioned.
        out["cells"] = {"age_min": age,
                        "unlocked": sorted(k for k, v in counts.items() if v >= 3),
                        "short": {k: 3 - v for k, v in sorted(counts.items()) if v < 3}}
    return out


def _submissions_today():
    """How many submissions the account actually landed in the platform's Eastern day, or None.

    Independent of the per-alpha /check cache, which is written before the submit it belongs to
    completes and therefore under-reports by one after every batch."""
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import submit_alphas as _SA
        from daily_budget import platform_date
        r = _SA.session().get(
            "https://api.worldquantbrain.com/users/self/activities/submissions", timeout=40)
        if r.status_code != 200:
            return None
        today = platform_date()
        return next((v for d, v in r.json()["records"]["records"] if d == today), 0)
    except Exception:
        return None


def alerts(snap):
    """Threshold breaches only. No advice — the supervisor decides what to do."""
    out = []
    r, m = snap["run"], snap["measurement"]
    if len(r["pids"]) > 1:
        out.append({"level": "high", "code": "MULTIPLE_DRIVERS",
                    "detail": f"{len(r['pids'])} drivers alive: {r['pids']}"})
    if r["pids"] and snap["journal_age_min"] is not None \
            and snap["journal_age_min"] > STALE_JOURNAL_MIN:
        out.append({"level": "high", "code": "JOURNAL_STALE",
                    "detail": f"no new sim row for {snap['journal_age_min']}min"})
    # A leftover lock FILE is harmless and must not be alerted on: both stream_busy() and the
    # harvester test the flock, and the kernel drops a flock when its holder exits. Flagging it
    # fired every gap between rounds and would have trained the operator to ignore the alert list.
    # What DOES matter is a lock held by a process that is no longer part of the run — that one
    # really does make the next round wait, so it is reported only when there is no live driver.
    # CORRECTED 2026-08-10. The old test was `lock_held and not run.pids` and it fired at 20:3x
    # while PID 47637 held the lock and was actively simulating -- a false HIGH alert, which is the
    # kind that trains an operator to ignore the list.
    #
    # The premise was wrong, not the threshold: an flock lives on the OPEN FILE DESCRIPTION and the
    # kernel drops it when the holder exits, so lock_held == True ALREADY implies a live holder.
    # An "orphan flock" cannot exist, and no value of run.pids makes it exist. What the alert was
    # reaching for is a holder that is alive but not PROGRESSING, and progress is measured by the
    # journal, not by whether a process labelled "driver" happens to be up.
    if snap["lock_held"] and snap.get("journal_age_min") is not None \
            and snap["journal_age_min"] > STALE_JOURNAL_MIN:
        out.append({"level": "high", "code": "LOCK_HELD_NO_PROGRESS",
                    "detail": f"resim.lock is held but no sim row for "
                              f"{snap['journal_age_min']}min — the holder is stuck, not working"})
    if not r["pids"] and not r.get("finished"):
        out.append({"level": "high", "code": "DRIVER_GONE",
                    "detail": "no driver running and the run never logged FINAL"})
    recent = r.get("rounds_done", [])[-DRY_ROUNDS:]
    if len(recent) == DRY_ROUNDS and sum(x["clean"] for x in recent) == 0 \
            and sum(x["zero_fail"] for x in recent) > 0:
        out.append({"level": "high", "code": "NO_CLEAN_DESPITE_PASSERS",
                    "detail": f"{sum(x['zero_fail'] for x in recent)} zero-fail over "
                              f"{DRY_ROUNDS} rounds produced no measurable gem"})
    # Freshness is part of the fact. The first version fired QUOTA_OPEN off a cached 2/4 while the
    # platform was actually at 4/4 -- a supervisor acting on that would have POSTed into an
    # exhausted quota, and a 403 there is irreversible. Any alert that authorises an ACTION must
    # carry the age of the evidence it rests on, and go silent rather than guess when it is stale.
    # ...and freshness alone is NOT enough, because this cache is fresh AND wrong. It is written
    # from the LAST alpha's /check, which is read BEFORE that alpha's own submit lands -- so after
    # a batch of four it sits at 3/4 with an age of minutes. Measured 2026-08-02: cache PASS 3/4,
    # 10min old, while the submissions feed said 4/4. Confirm against that feed, which counts what
    # the account actually landed inside the Eastern day, before authorising anything.
    q = snap["submit"].get("quota") or {}
    q_age = (time.time() - q["ts"]) / 60 if q.get("ts") else None
    if q.get("result") == "PASS" and snap["measurement"]["clean_total"] > 0:
        landed = _submissions_today()
        if landed is not None and landed >= 4:
            out.append({"level": "low", "code": "QUOTA_SPENT",
                        "detail": f"cache says {q.get('value')}/{q.get('limit')} but the "
                                  f"submissions feed shows {landed}/4 landed today — do not submit"})
        elif q_age is not None and q_age <= 30:
            out.append({"level": "medium", "code": "QUOTA_OPEN",
                        "detail": f"quota {q.get('value')}/{q.get('limit')} "
                                  f"({q_age:.0f}min old), submissions feed {landed}/4 today, "
                                  f"clean gems are banked"})
        else:
            out.append({"level": "low", "code": "QUOTA_UNKNOWN",
                        "detail": f"last quota reading is {q_age:.0f}min old — re-read before "
                                  f"acting" if q_age else "no quota reading on file"})
    if m["parked_in_driver"] > 30:
        out.append({"level": "medium", "code": "PARK_QUEUE_DEEP",
                    "detail": f"{m['parked_in_driver']} alphas waiting on correlation"})
    cells = snap["submit"].get("cells") or {}
    # age_min có mặt nhưng bằng None khi chưa từng đọc pyramid -> None > 180 ném TypeError
    # và làm hỏng toàn bộ --report. Coi "chưa có số" là không cũ.
    if (cells.get("age_min") or 0) > 180:
        out.append({"level": "low", "code": "CELL_COUNTS_STALE",
                    "detail": f"pyramid counts {cells['age_min']:.0f}min old"})
    return out


def _yield_trend():
    """Zero-fail rate per round and cumulative, for the run in the newest driver log.

    A single round's rate is noise; the TREND is what says whether the pool is still right. The
    2026-08-01 collapse from 12.5% to 0.7% was invisible round by round and obvious as a series."""
    log = _latest_driver_log()
    if not log:
        return {}
    txt = log.read_text()
    done = re.findall(r"R(\d+) DONE: zero-fail (\d+)/(\d+) clean (\d+)", txt)
    rounds = [{"r": int(a), "zf": int(b), "n": int(c), "clean": int(d)} for a, b, c, d in done]
    tn = sum(x["n"] for x in rounds)
    tz = sum(x["zf"] for x in rounds)
    return {"rounds": rounds, "sims": tn, "zero_fail": tz,
            "rate": round(tz / tn, 4) if tn else None,
            "clean": sum(x["clean"] for x in rounds)}


def _screen():
    """Progress of the PnL-derived screen over the un-measured backlog."""
    f = ST / "pnl_screen.json"
    if not f.exists():
        return {}
    try:
        d = json.load(open(f))
    except Exception:
        return {}
    # An entry with no pnl_sharpe was never evaluated -- harvest_pnl.py writes {"pnl": false} when
    # the PnL fetch comes back with nothing, and such a row carries no screen_ok key at all.
    # v.get("screen_ok") is None there, which is falsy, so counting it as a failure reported
    # 141/1925 = 7.3% and "last 100 at 0%" when the honest figures were 141/937 = 15.0% and a
    # last-100 window containing exactly ONE screened alpha. Same presence-contract error as the
    # gate payloads: a metric ABSENT from a record is not a metric that failed.
    evaluated = {a: v for a, v in d.items() if isinstance(v.get("pnl_sharpe"), (int, float))}
    ok = [a for a, v in evaluated.items() if v.get("screen_ok")]
    unmeasured = len(d) - len(evaluated)
    recent = [x for x in d.items() if isinstance(x[1].get("pnl_sharpe"), (int, float))][-100:]
    rec_ok = sum(1 for _, v in recent if v.get("screen_ok"))
    return {"screened": len(evaluated), "pass": len(ok), "backlog": len(d),
            "unmeasured": unmeasured,
            "rate": round(len(ok) / len(evaluated), 4) if evaluated else None,
            "recent_n": len(recent),
            "recent_rate": round(rec_ok / len(recent), 4) if recent else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--alerts", action="store_true")
    ap.add_argument("--report", action="store_true",
                    help="everything a status answer needs, in one call")
    args = ap.parse_args()

    snap = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "run": _run_state(), "journal_age_min": _journal_age_min(),
            "lock_held": _lock_held(), "measurement": _measurement(), "submit": _submit()}
    snap["alerts"] = alerts(snap)
    if args.report or args.json:
        snap["yield"] = _yield_trend()
        snap["screen"] = _screen()

    if args.report:
        y, sc = snap["yield"], snap["screen"]
        r, m, sb = snap["run"], snap["measurement"], snap["submit"]
        print(f"RUN      driver={r['pids'] or 'STOPPED'} sim={r['sim_pids'] or 'none'} "
              f"harvester={r['harvester_pids'] or 'none'}")
        if r.get("round"):
            print(f"         round {r['round']}/{r['rounds_total']} "
                  f"{r['hours_left']}h left | journal {snap['journal_age_min']}min old")
        if y.get("rounds"):
            # `rate` is None until a round has scored anything, which is exactly the moment a fresh
            # run is starting -- so formatting it unguarded crashed the whole report precisely when
            # it was most needed. A missing rate is a fact to print, not an error to raise.
            rate = f"{y['rate']:.1%}" if y.get("rate") is not None else "n/a"
            print(f"YIELD    {y['sims']} sims, {y['zero_fail']} zero-fail "
                  f"({rate}), {y['clean']} clean")
            print("         per round: " + "  ".join(
                f"R{x['r']}:{x['zf']}/{x['n']}" for x in y["rounds"][-6:]))
        if sc:
            # Same None trap as YIELD: an empty screen file makes both rates None.
            _r = f"{sc['rate']:.0%}" if sc.get('rate') is not None else "n/a"
            _rr = f"{sc['recent_rate']:.0%}" if sc.get('recent_rate') is not None else "n/a"
            print(f"SCREEN   {sc['screened']} screened, {sc['pass']} pass "
                  f"({_r}); last {sc.get('recent_n', 0)} screened at {_rr}")
            if sc.get("unmeasured"):
                print(f"         {sc['unmeasured']} of {sc['backlog']} in the backlog have NO PnL "
                      f"and were never evaluated — not failures")
        print(f"MEASURE  measured={m['measured_total']} clean={m['clean_total']} "
              f"parked={m['parked_in_driver']}")
        q = sb.get("quota") or {}
        qage = f", {int((time.time()-q['ts'])/60)}min old" if q.get("ts") else ""
        print(f"SUBMIT   {sb['submitted_ok']} live | quota {q.get('value')}/{q.get('limit')}"
              f"{qage}")
        if sb.get("cells"):
            print(f"         unlocked {sb['cells']['unlocked']}")
            print(f"         short    {sb['cells']['short']}")
        if snap["alerts"]:
            for a in snap["alerts"]:
                print(f"ALERT    [{a['level']}] {a['code']}: {a['detail']}")
        else:
            print("ALERT    none")
        return

    if args.alerts:
        print(json.dumps(snap["alerts"], indent=1))
        return
    if args.json:
        print(json.dumps(snap, indent=1))
        return

    r, m, s = snap["run"], snap["measurement"], snap["submit"]
    print(f"RUN      driver={r['pids'] or 'none'} watchdog={r['watchdog_pids'] or 'none'} "
          f"sim={r['sim_pids'] or 'none'} harvester={r['harvester_pids'] or 'none'}")
    if r.get("round"):
        print(f"         round {r['round']}/{r['rounds_total']} size={r['round_size']} "
              f"{r['hours_left']}h left | journal {snap['journal_age_min']}min old")
    for x in r.get("rounds_done", [])[-4:]:
        print(f"         R{x['round']}: {x['zero_fail']}/{x['n']} zero-fail, {x['clean']} clean")
    print(f"MEASURE  measured={m['measured_total']} clean={m['clean_total']} "
          f"parked={m['parked_in_driver']} in-flight={m['triggered_in_flight']}")
    print(f"SUBMIT   ok={s['submitted_ok']} quota={s.get('quota', {}).get('value')}/"
          f"{s.get('quota', {}).get('limit')}")
    if s.get("cells"):
        print(f"         unlocked={s['cells']['unlocked']} short={s['cells']['short']}")
    if snap["alerts"]:
        print("ALERTS")
        for a in snap["alerts"]:
            print(f"  [{a['level']:6}] {a['code']:26} {a['detail']}")
    else:
        print("ALERTS   none")


if __name__ == "__main__":
    main()
