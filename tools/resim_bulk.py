#!/usr/bin/env python3
"""Bulk RE-SIM runner v5 — redesigned for maximum throughput (10-agent design round).

Round-1 changes vs v4:
  R1.1 slot-429s surface to launch logic: hold-at-cap + timed re-probe (+1 every 5 min)
  R1.2 age-gated polling (first probe 90s, then 120s young / 25s old) — frees ~60 req/min
  R1.3 inflight persisted atomically; orphans ADOPTED on restart
  R1.4 failure journal + one singleton retry per failed alpha
  R1.5 LPT batch composition (slowest universes + longest formulas first)
  R1.6 metrics journal state/resim_metrics.jsonl (req kinds, batch lifecycle, 5-min window)
  R1.7 fcntl single-process lock, gate jitter, 5xx circuit breaker

Round-2 knobs (apply only on metric triggers): MAX_TRY_CONC 20->30, stats deferral,
MIN_GAP 0.35, Retry-After-driven polling, priority scheduler.
"""
from __future__ import annotations
import json, time, pickle, pathlib, os, sys, random, fcntl
from collections import deque
from urllib.parse import urljoin
import requests

H = "https://api.worldquantbrain.com"
ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")
ST = ROOT / "state"
BATCH = 10
MAX_TRY_CONC = 20
MIN_GAP = 0.5
MAX_INFLIGHT_AGE = 5400            # per-parent deadline (s): drain a stuck/vanished parent so the
                                   # run can't hang forever. Well above a full run's 57-71 min, and a
                                   # single parent is a small subset of that -> can't false-kill.
UNI_COST = {"TOP3000": 3, "TOP2000": 2, "TOP1000": 1.5, "TOPSP500": 1, "TOP500": 1, "TOP200": 0.5}

# ---- R1.7 single-process lock (audit 2026-07-24) ----
# Single non-blocking flock, PID-stamped for a clear error. A killed/orphaned holder can NOT strand
# the next stage: flock AUTO-RELEASES when the holder process dies, so a failed LOCK_NB acquire always
# means a LIVE holder -> refuse (surfacing its pid). We deliberately do NOT reclaim on a runtime
# threshold (see below): that would kill healthy long runs and could target a reused pid.
_lockf = open(ST / "resim.lock", "a+")
def _try_flock():
    try:
        fcntl.flock(_lockf, fcntl.LOCK_EX | fcntl.LOCK_NB); return True
    except OSError:
        return False
if not _try_flock():
    # The live holder stamps its pid a few statements AFTER acquiring the flock, so a read here
    # can land in that window (empty file / mid-truncate) and see pid=None. Re-read briefly to let
    # it finish stamping — purely to make the refusal diagnostic accurate; the refusal itself is
    # already correct (a failed LOCK_NB always means a live holder).
    _info = {}
    for _ in range(20):
        try:
            _lockf.seek(0); _info = json.loads(_lockf.read() or "{}")
        except Exception:
            _info = {}
        if _info.get("pid"):
            break
        time.sleep(0.05)
    # flock AUTO-RELEASES when the holder process dies, so a failed acquire ALWAYS means a LIVE
    # holder -> correctly refuse. NO SIGKILL reclaim: killing on a 30-min TOTAL-runtime threshold
    # would kill healthy long runs (real ones take 57-71 min) and could hit a reused pid (B1 verified).
    raise SystemExit(f"another resim process (pid={_info.get('pid')}) holds state/resim.lock — refusing to double-run")
_lockf.seek(0); _lockf.truncate()
_lockf.write(json.dumps({"pid": os.getpid(), "ts": time.time()})); _lockf.flush()

# ---- R1.6 metrics ----
_met = open(ST / "resim_metrics.jsonl", "a", buffering=1)


def emit(ev, **kw):
    _met.write(json.dumps({"ev": ev, "ts": round(time.time(), 1), **kw}) + "\n")


s = requests.Session(); s.headers.update({"Connection": "close"})
s.cookies.update(pickle.load(open(ST / "wq_cookies.pkl", "rb")))
_last = [0.0]
_5xx = deque()                    # R1.7 circuit breaker window


def req(method, url, max_attempts=40, retry_429=True, kind="other", **kw):
    for attempt in range(max_attempts):
        dt = time.time() - _last[0]
        gate_ms = max(0.0, MIN_GAP - dt)
        time.sleep(gate_ms + random.uniform(0.05, 0.25))          # R1.7 jitter
        _last[0] = time.time()
        t0 = time.time()
        try:
            r = s.request(method, url if url.startswith("http") else H + url, timeout=40, **kw)
        except Exception:
            time.sleep(4); continue
        emit("req", kind=kind, code=r.status_code, lat_ms=round((time.time() - t0) * 1000),
             gate_ms=round(gate_ms * 1000), attempt=attempt,
             **({"retry_after": r.headers.get("Retry-After")} if r.status_code == 429 else {}))
        if r.status_code == 429:
            if not retry_429:
                return r
            ra = float(r.headers.get("Retry-After") or 0)
            if ra > 600: raise SystemExit("RATE-BAN — S2.5 runbook")
            time.sleep(max(ra, 1.0) + 0.5); continue
        if r.status_code >= 500:
            now = time.time()
            _5xx.append(now)
            while _5xx and now - _5xx[0] > 120:
                _5xx.popleft()
            if len(_5xx) >= 5:                                     # circuit breaker
                emit("circuit_break", n5xx=len(_5xx))
                time.sleep(300 + random.uniform(0, 30)); _5xx.clear()
            else:
                time.sleep(4 + min(attempt, 20))
            continue
        if r.status_code == 401:
            raise SystemExit("401 — rerun tools/auth_only.py + biometric")
        return r
    raise RuntimeError(f"exhausted retries: {url}")


def payload(a):
    st = dict(a["settings"] or {})
    st.setdefault("language", "FASTEXPR")
    st["visualization"] = False
    return {"type": "REGULAR", "settings": st, "regular": a["formula"]}


# ---- targets + journal (R1.4 semantics) ----
targets = json.load(open(ST / "resim_targets.json"))

# ---- OPERATOR GATE: the last line before anything reaches the platform ----------------------
# Khoa 2026-08-08: an operator check must run BEFORE a formula is applied. tools/gate_pool.py does
# this at generation time, but a generation-time check is advisory -- it only runs if whoever
# built the pool remembered to run it, and on 2026-08-08 a pool reached this file with ts_kurtosis,
# ts_min and ts_max in it (191 of 416 rows), all three invented from memory. Two other batches had
# already died at the door the same way.
#
# So the same table is enforced HERE, where nothing can route around it. A hallucinated operator,
# a wrong argument count or an undeclared named parameter costs a 400 per row and a batch that
# journals nothing; refusing to launch costs a re-generate.
#
# The check is API-free and reads OPERATORS.md, which agrees exactly with the RC allowlist
# (85 operators, no drift). It never SILENTLY drops a row -- it refuses the launch and names every
# offender, because a quietly shrunken batch reads as "the idea did not work".
try:
    sys.path.insert(0, str(ROOT / "tools"))
    import opcheck as _opc
    _sigs = _opc.load_signatures()
    _bad = []
    for _a in targets:
        _p = _opc.check(_a.get("formula") or "", _sigs)
        if _p:
            _bad.append((_a.get("id"), _p[0]))
    if _bad:
        print(f"OPERATOR GATE: refusing to launch — {len(_bad)}/{len(targets)} targets violate "
              f"the OPERATORS.md signature table", flush=True)
        _seen = set()
        for _oid, (_sev, _msg) in _bad[:12]:
            if _msg in _seen:
                continue
            _seen.add(_msg)
            print(f"   {_oid}: {_sev} {_msg}", flush=True)
        if len(_bad) > 12:
            print(f"   ... and {len(_bad) - 12} more", flush=True)
        raise SystemExit(2)
    print(f"OPERATOR GATE: {len(targets)} targets clean against OPERATORS.md "
          f"({len(_sigs)} operators)", flush=True)
except SystemExit:
    raise
except Exception as _e:
    # An unreadable reference must not become a silent bypass, but it also must not stop a run
    # whose formulas may be perfectly fine -- say so loudly and continue.
    print(f"OPERATOR GATE: could not run ({str(_e)[:90]}) — proceeding UNCHECKED", flush=True)
by_id = {a["id"]: a for a in targets}


def _treatment(oid):
    """The TREATMENT that produced this row, written into the row itself.

    Audited 2026-08-08: `settings` appeared in 0 of 65,196 journal rows. Every analysis therefore
    recovers it by globbing 366 *targets*.json files, and 11,766 evaluable rows -- 26% of the
    evidence base, carrying 716 zero-fails -- resolve to nothing and are silently dropped. The
    dropped arm is not a random sample of the kept one: it runs 6.09% zero-fail against the kept
    arm's 3.90%, so every headline rate this project has quoted is the low side of a join-based
    exclusion.

    An experiment record that does not contain its own treatment is not an experiment record.
    `by_id` is already in scope at the write site; there was never a reason not to write it."""
    a = by_id.get(oid) or {}
    st = a.get("settings") or {}
    out = {}
    if st:
        # the settings that change the simulated alpha; the rest are constant across this repo
        out["settings"] = {k: st.get(k) for k in
                           ("region", "delay", "universe", "neutralization", "decay", "truncation",
                            "startDate", "endDate", "maxPosition", "maxTrade")
                           if st.get(k) is not None}
    if a.get("formula"):
        out["formula"] = a["formula"]
    if isinstance(a.get("meta"), dict):
        # Everything the generator labelled, MINUS bulk. The first version of this allowlisted
        # seven key names and that reproduced, one level down, the exact defect it was written to
        # fix: gen_shape wrote {W, family, kind, long_w, power, short_w, skew_w} and the journal
        # kept {kind}. The six dropped keys were the swept INDEPENDENT VARIABLES, so 780 rows
        # cannot answer the question they were run to answer.
        # A generator knows which axes it varied; this writer does not and cannot. So the rule is
        # keep-by-default, drop only what is provably redundant (formula/settings live at the top
        # level) or unbounded (a value long enough to bloat every row).
        out["meta"] = {k: v for k, v in a["meta"].items()
                       if k not in ("formula", "settings") and len(str(v)) < 400}
    return out
# R1.5 LPT: slowest first within each delay. Multi-sim batches must be HOMOGENEOUS in
# (delay, region, universe) — mixed-region batches are rejected 400 (found with CHN/JPN pyramid
# set; the old 725-set was all-USA so delay-only grouping never hit this). Sort groups them.
targets.sort(key=lambda a: ((a.get("settings") or {}).get("delay", 1),
                            (a.get("settings") or {}).get("region", ""),
                            (a.get("settings") or {}).get("universe", ""),
                            -len(a.get("formula") or "")))
done, failed_once = set(), set()
res_path = ST / "resim_results.jsonl"
if res_path.exists():
    for l in open(res_path):
        try:
            j = json.loads(l)
        except Exception:
            continue
        if j.get("alpha") or j.get("retried"):
            done.add(j["old_id"])
        else:
            failed_once.add(j["old_id"])
res_f = open(res_path, "a")

# ---- R1.3 inflight persistence + adoption ----
INF_PATH = ST / "resim_inflight.json"
inflight = {}                     # url -> {ids, t0, next, polls, single}


def save_inflight():
    tmp = ST / "resim_inflight.tmp"
    json.dump({u: m["ids"] for u, m in inflight.items()}, open(tmp, "w"))
    os.replace(tmp, INF_PATH)


adopted_ids = set()
if INF_PATH.exists():
    try:
        prev = json.loads(INF_PATH.read_text())
    except Exception:
        prev = {}
    for url, ids in prev.items():
        try:
            g = req("GET", url, max_attempts=4, kind="adopt")
        except RuntimeError:
            continue
        if g.status_code == 200:
            inflight[url] = {"ids": ids, "t0": time.time() - 300, "next": time.time() + 10,
                             "polls": 0, "single": len(ids) == 1}
            adopted_ids.update(ids)
            emit("orphan_adopted", url=url, n=len(ids))
        else:
            emit("orphan_lost", url=url, code=g.status_code, n=len(ids))
    save_inflight()

queue = [a for a in targets if a["id"] not in done and a["id"] not in adopted_ids]
singles = [by_id[i] for i in failed_once if i in by_id and i not in adopted_ids]  # R1.4 one retry
retry_ids = {a["id"] for a in singles}
queue = [a for a in queue if a["id"] not in retry_ids]
print(f"targets={len(targets)} done={len(done)} adopted={len(adopted_ids)} "
      f"retry-singles={len(singles)} queue={len(queue)}", flush=True)
emit("restart", adopted=len(adopted_ids), queue=len(queue), singles=len(singles))

ceiling = None
launch_holdoff = 0.0
next_probe = float("inf")
last_good = 0
launched = finished = failed = 0
completions = deque()             # timestamps for 5-min window KPI
t_start = time.time()


def launch_one():
    """Launch one batch (or one retry single). Returns True if launched."""
    global ceiling, launch_holdoff, next_probe, launched, last_good
    now = time.time()
    if now < launch_holdoff:
        return False
    # R2.A: retries are re-batched (multi-sim), never 1-sim parents — but only once
    # the main queue is empty, so fresh work keeps priority
    src = queue if queue else singles
    if not src:
        return False
    is_retry = src is singles
    def gkey(a):
        s = a.get("settings") or {}
        return (s.get("delay"), s.get("region"), s.get("universe"))
    k0 = gkey(src[0])
    group = []
    while src and len(group) < BATCH and gkey(src[0]) == k0:
        group.append(src.pop(0))
    body = payload(group[0]) if len(group) == 1 else [payload(a) for a in group]
    try:
        r = req("POST", "/simulations", json=body, max_attempts=4, retry_429=False, kind="launch")
    except RuntimeError:
        (singles if is_retry else queue)[0:0] = group
        return False
    if r.status_code in (200, 201):
        loc = r.headers.get("Location")
        url = urljoin(H, loc) if loc and loc.startswith("/") else loc
        if not url:
            (singles if is_retry else queue)[0:0] = group
            return False
        inflight[url] = {"ids": [a["id"] for a in group], "t0": time.time(),
                         "next": time.time() + 90, "polls": 0, "single": len(group) == 1,
                         "retry": is_retry}
        save_inflight()
        launched += len(group)
        last_good = max(last_good, len(inflight))
        emit("batch_launch", n=len(group), inflight=len(inflight), queue=len(queue))
        return True
    msg = (r.text or "")[:200].replace("\n", " ")
    if (400 <= r.status_code < 500 and r.status_code != 429
            and "CONCURRENT" not in msg.upper() and "LIMIT" not in msg.upper()):
        # S2.0 patch 4: quarantine non-429 4xx rejections — never re-insert at queue head
        emit("refused", code=r.status_code, msg=msg[:120], inflight=len(inflight))
        try:
            pois = json.load(open(ST / "resim_poison.json"))
        except Exception:
            pois = []
        pois.append({"ts": round(time.time(), 1), "code": r.status_code, "msg": msg,
                     "ids": [a.get("id") for a in group]})
        json.dump(pois, open(ST / "resim_poison.json", "w"), indent=1)
        print(f"QUARANTINE {len(group)} sims -> state/resim_poison.json "
              f"({r.status_code}: {msg[:100]})", flush=True)
        return False
    (singles if is_retry else queue)[0:0] = group
    if r.status_code == 429 or "CONCURRENT" in msg.upper() or "LIMIT" in msg.upper():
        # "LIMIT" matches BOTH CONCURRENT_SIMULATION_LIMIT_EXCEEDED (clears in minutes) and
        # DAILY_SIMULATION_LIMIT_EXCEEDED (clears at midnight ET), and the message alternates
        # between the two on identical requests -- measured 2026-08-02, four probes 20s apart gave
        # DAILY, CONCURRENT, CONCURRENT, CONCURRENT with the daily allowance exhausted. So do not
        # branch on the text: COUNT what the account created in the Eastern window. Re-probing a
        # daily wall every 5 minutes is what burned 4h45m that morning, and it recurs on the last
        # round of every day once the round overshoots the remaining allowance.
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            from daily_budget import budget as _dbudget, mark_daily_limit as _dmark
            _b = _dbudget()
            # The COUNT alone is not enough, and 2026-08-06 proved it: it read 3966/5000 with 1034
            # "remaining" while every POST came back DAILY_SIMULATION_LIMIT_EXCEEDED, because the
            # count measures alphas CREATED and the ceiling counts simulations ATTEMPTED -- errors
            # and retries spend the allowance without producing an alpha. Three rounds POSTed into
            # that wall for 2h19m with the guard reporting headroom the whole time.
            # An explicit DAILY message is not a diagnosis of WHICH limit fired (the text alternates
            # on identical requests) but the platform never emits it while the day is open, so
            # recording it can only end the day early -- never extend it past the ceiling.
            if "DAILY" in msg.upper():
                _dmark(_b.get("window_start_utc"))
                _b = _dbudget()
            if _b.get("remaining") == 0:
                queue.clear()
                singles.clear()
                emit("daily_cap", used=_b.get("used"), resets_in=_b.get("seconds_to_reset"))
                print(f"DAILY CAP REACHED ({_b.get('used')}/{_b.get('cap')}); resets in "
                      f"{_b.get('seconds_to_reset', 0)/3600:.1f}h -- draining in-flight and "
                      f"stopping instead of re-probing a wall that will not move", flush=True)
                return False
        except Exception:
            pass                       # unreadable budget -> fall through to the concurrency path
        ceiling = max(len(inflight), 1)
        ra = float(r.headers.get("Retry-After") or 0)
        launch_holdoff = time.time() + max(ra, 60)
        next_probe = time.time() + 300
        emit("refused", code=r.status_code, msg=msg[:120], inflight=len(inflight))
        print(f"HOLD-AT-CAP: ceiling={ceiling} batches ({ceiling*BATCH} sims); "
              f"re-probe in 5min", flush=True)
    else:
        emit("refused", code=r.status_code, msg=msg[:120], inflight=len(inflight))
        print(f"launch rejected {r.status_code}: {msg[:100]}", flush=True)
        launch_holdoff = time.time() + 30
    return False


_BULK = {}                 # alpha_id -> metrics, from the paginated bulk read
_BULK_AT = [0.0]           # last refresh, so a run of misses cannot become a refresh storm
_BULK_MIN_GAP = 45.0


def _bulk_refresh(pages=2, per=100):
    """One request per 100 alphas instead of one per alpha.

    Measured 2026-08-08 over 169,190 logged requests: `child` 40.5%, **`alpha` 35.6%**, `poll`
    18.6%, `launch` 5.0%. The `alpha` leg is one GET per simulated alpha whose only purpose is to
    read metrics the platform will also hand over in bulk:

        GET /users/self/alphas?limit=100&order=-dateCreated
        -> 100 alphas, each with the full `is` block and all 17 checks WITH value and limit

    So a 208-row pool costs 3 requests here instead of 208. That matters because the account budget
    is 60 requests/minute for everything — simulation polling and correlation reads included — so
    request count is a shared scarce resource, not a local efficiency concern.

    Deliberately NOT filtered by `is.sharpe>`/`is.fitness>` even though the endpoint supports it
    server-side. Filtering to gate-passers would save nothing further (the page count is the same)
    and would discard the metrics of every non-passer — and non-passers are the majority of the
    evidence base that the surrogate and every field/settings comparison are fitted on.
    """
    if time.time() - _BULK_AT[0] < _BULK_MIN_GAP:
        return
    _BULK_AT[0] = time.time()
    for i in range(pages):
        try:
            g = req("GET", "/users/self/alphas", kind="bulk",
                    params={"limit": per, "offset": i * per, "order": "-dateCreated"})
            res = (g.json() or {}).get("results") or []
        except Exception:
            return
        if not res:
            return
        for a in res:
            iss = a.get("is") or {}
            if not a.get("id") or not iss:
                continue
            _BULK[a["id"]] = {
                "sharpe": iss.get("sharpe"), "fitness": iss.get("fitness"),
                "turnover": iss.get("turnover"), "returns": iss.get("returns"),
                "drawdown": iss.get("drawdown"),
                "checks": [{k: c.get(k) for k in ("name", "result", "value", "limit")}
                           for c in (iss.get("checks") or [])]}


def resolve_alpha(alpha_id):
    hit = _BULK.get(alpha_id)
    if hit is None:
        _bulk_refresh()                              # a miss means the batch is newer than the cache
        hit = _BULK.get(alpha_id)
    if hit is not None:
        return hit
    # Fall back to the single read. A miss must degrade to the OLD behaviour, never to an empty
    # row: an empty result journals as if it were a measurement, and it is not.
    try:                                             # B2-parity: req() was OUTSIDE the try — an
        ga = req("GET", f"/alphas/{alpha_id}", kind="alpha")  # exhausted-retry RuntimeError here
        aj = ga.json(); iss = aj.get("is") or {}     # crashed poll_all mid-batch, dropping buffered
        #                                              rows. Now -> {} (row keeps alpha_id, no metrics).
        return {"sharpe": iss.get("sharpe"), "fitness": iss.get("fitness"),
                "turnover": iss.get("turnover"), "returns": iss.get("returns"),
                "drawdown": iss.get("drawdown"),
                "checks": [{k: c.get(k) for k in ("name", "result", "value", "limit")}
                           for c in (iss.get("checks") or [])]}
    except Exception:
        # An empty result is journalled as if it were a measurement, and it is not: the alpha
        # exists on the platform with every metric, we simply failed to READ it once. Those rows
        # then sit in the denominator of any rate and silently corrupt structural comparisons --
        # 220 of 1,096 interaction rows were `<no checks>`, which flipped an addition-vs-
        # multiplication verdict. Record the id so it can be re-read later at zero simulation cost.
        try:
            p = ST / "resolve_pending.json"
            q = json.load(open(p)) if p.exists() else []
            if alpha_id not in q:
                q.append(alpha_id)
                json.dump(q, open(p, "w"))
        except Exception:
            pass
        return {"_resolve_failed": True}


def poll_all():
    global finished, failed
    now = time.time()
    for url in list(inflight):
        m = inflight[url]
        if now < m["next"]:
            continue
        try:                                 # B2-parallel: req() was UNGUARDED here — an exhausted
            r = req("GET", url, kind="poll")  # poll retry (2-3min network/API blackout) raised
        except RuntimeError:                  # RuntimeError out of poll_all -> out of the main loop
            m["next"] = now + 60              # -> whole run dies mid-flight. Now: back off and re-poll
            continue                          # next iteration; MAX_INFLIGHT_AGE still drains a dead url.
        m["polls"] += 1
        try:
            j = r.json()
        except Exception:
            j = {}
        status = (j.get("status") or "").upper()
        if status not in ("COMPLETE", "WARNING", "ERROR", "FAIL", "FAILED"):
            age = now - m["t0"]
            if age > MAX_INFLIGHT_AGE:
                # deadline guard: a parent that never reaches a terminal status (purged/404 or
                # perpetually pending) would otherwise be re-polled forever and the main loop
                # `while queue or inflight or singles` would never exit. Record its ids as failed
                # so inflight drains and the run can complete.
                emit("inflight_expired", url=url, age_s=round(age), polls=m["polls"],
                     code=r.status_code, n=len(m["ids"]))
                for oid in m["ids"]:
                    res_f.write(json.dumps({"old_id": oid, "alpha": None, "status": "EXPIRED",
                                            **_treatment(oid)}) + "\n")
                    failed += 1
                res_f.flush(); os.fsync(res_f.fileno())
                del inflight[url]
                save_inflight()
                continue
            m["next"] = now + (25 if age > 300 else 120)          # R1.2 age gate
            continue
        # terminal
        old_ids = m["ids"]
        rows = []
        if m.get("single"):
            alpha_id = j.get("alpha")
            st_ = {}
            if alpha_id:
                st_ = resolve_alpha(alpha_id)
            rows.append({"old_id": old_ids[0], "alpha": alpha_id, "status": status,
                         **({"retried": True} if m.get("retry") else {}), **st_})
        else:
            children = j.get("children") or []
            pairs = zip(old_ids, children) if len(children) == len(old_ids) \
                else [(oid, None) for oid in old_ids]
            retried = {"retried": True} if m.get("retry") else {}
            for oid, ch in pairs:
                alpha_id, st_, why = None, {}, None
                if ch:
                    cu = ch if isinstance(ch, str) and ch.startswith("http") else f"{H}/simulations/{ch}"
                    try:                                     # B2 fix: req() was OUTSIDE the try — a
                        g = req("GET", cu, kind="child")     # RuntimeError here crashed the whole batch,
                        cj = g.json()                        # losing buffered rows. Now an exhausted
                        alpha_id = cj.get("alpha")           # child -> alpha=None (retry path handles it).
                        if not alpha_id:                     # R2.B: capture the real error
                            why = str(cj.get("message") or cj.get("errors")
                                      or cj.get("detail") or "")[:160] or None
                    except Exception:
                        pass
                if alpha_id:
                    st_ = resolve_alpha(alpha_id)
                rows.append({"old_id": oid, "alpha": alpha_id, "status": status,
                             **({"why": why} if why else {}), **retried,
                             **_treatment(oid), **st_})
        for row in rows:
            res_f.write(json.dumps(row) + "\n")
            if row.get("alpha"):
                finished += 1
                completions.append(time.time())
            else:
                failed += 1
                if row["old_id"] in by_id and row["old_id"] not in failed_once \
                        and not row.get("retried"):
                    failed_once.add(row["old_id"])
                    singles.append(by_id[row["old_id"]])           # R1.4 one retry
        res_f.flush(); os.fsync(res_f.fileno())
        emit("batch_done", n=len(old_ids), lat_s=round(now - m["t0"]), polls=m["polls"],
             status=status, inflight=len(inflight) - 1)
        del inflight[url]
        save_inflight()
        launch_one()                                # R2.C: refill the freed slot immediately


last_report = 0.0
while queue or inflight or singles:
    now = time.time()
    cap = ceiling if ceiling else MAX_TRY_CONC
    if ceiling and now >= next_probe and (queue or singles):
        cap = ceiling + 1                                           # R1.1 timed re-probe
        next_probe = now + 300
    n_new = 0
    while (queue or singles) and len(inflight) < cap and n_new < 2:  # gentle escalation
        if not launch_one():
            break
        n_new += 1
        if ceiling and len(inflight) > ceiling:
            ceiling = len(inflight)                                 # probe succeeded
            next_probe = time.time() + 60                           # fast ladder on success
            emit("ceiling", batches=ceiling)
    poll_all()
    if now - last_report > 60:
        last_report = now
        while completions and now - completions[0] > 300:
            completions.popleft()
        rate5 = len(completions) / 5.0
        remaining = len(queue) + len(singles) + sum(len(m["ids"]) for m in inflight.values())
        eta = remaining / rate5 if rate5 > 0 else float("inf")
        print(f"[{(now-t_start)/60:6.1f}m] inflight={len(inflight)} | done={finished} "
              f"failed={failed} queue={len(queue)} singles={len(singles)} | "
              f"{rate5:.1f} sims/min (5m window) | ETA {eta:.0f}m", flush=True)
        emit("window", sims_min5=round(rate5, 2), inflight=len(inflight),
             queue=len(queue), done=finished, failed=failed)
    time.sleep(3)

print(f"RESIM COMPLETE: done={finished} failed={failed} in {(time.time()-t_start)/60:.0f}m "
      f"(ceiling={ceiling})", flush=True)
emit("complete", done=finished, failed=failed, minutes=round((time.time() - t_start) / 60))
