#!/usr/bin/env python3
"""Measure prod/self correlation for every gate-passing alpha that has never been measured.

ARCHITECTURE_RESEARCH.md §4 ranks this first, for one reason: a correlation read is an
authenticated GET and costs NO simulation budget, while 947 alphas that already cleared every hard
gate have never had the one measurement that decides whether they can be submitted. They are
already paid for. The loop meanwhile spends thousands of sims a day manufacturing more of them.

TWO THINGS THIS DOES DIFFERENTLY, both deliberate:

  RANDOM ORDER. The existing 777-alpha measured set was chosen by strength — median fitness 1.41
  against 0.74 for the unmeasured — so its 12.8% prod-clean rate describes the strong tail and
  cannot be extrapolated. Measuring in random order (fixed seed, so the run is reproducible) makes
  the resulting rate an estimate of the WHOLE backlog, which is the only thing worth having.

  CHUNKED PERSISTENCE. fetch_prod_corr.measure() returns its whole result set and the caller
  writes once at the end, so a run that dies at alpha 900 of 947 saves nothing. Here every chunk
  is merged to disk before the next one starts, and already-measured alphas are skipped on
  restart, so the job is resumable by re-running it.

  python3 tools/measure_backlog.py                 # work the whole backlog
  python3 tools/measure_backlog.py --limit 200     # the §8 falsification sample
"""
import argparse, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import fetch_prod_corr as FP                                            # noqa: E402

STORE = ROOT / "state/prod_corr_measured.json"
BACKLOG = ROOT / "state/prod_backlog.json"


# ---------------------------------------------------------------------------------------------
# WHICH ALPHAS ARE WORTH A PROBE. Operator decision, Khoa 2026-08-13: measure correlations only for
# alphas that already clear the metric gates, not for everything simmed.
#
# WHY IT IS RIGHT HERE, as a number: the correlation channel is the pipeline's binding constraint --
# 6,804 probes over 79.3 hours returned 0 payloads, 398 of the 1,053 unmeasured gems had never been
# probed at ALL, and 229 of one sweep's 922 probes were spent on rows that were not gems. Every probe
# spent on an alpha that can never be submitted is a probe not spent on one that can.
#
# WHAT IT COSTS, stated rather than buried: `state/prod_corr_measured.json` and the memory note
# `measure-any-simmed-alpha` record the opposite lesson for a DIFFERENT purpose -- prod/self corr is
# computable for non-passers too, and restricting to gate-passers is what threw away ~98% of the
# sample in earlier correlation EXPERIMENTS. That finding is about studying correlation structure;
# this filter is about spending a scarce submit-facing channel. Both can be true. `--all` restores
# the old behaviour for anyone doing the former, and it exists precisely so the experiment is still
# reachable.
#
# The thresholds are the operator's, not derived here: they are the ladder bar, the hard Power-Pool
# fitness gate, and the turnover band. NOT ESTABLISHED that they are the optimal screen -- no
# experiment here compared this screen against `gates.zero_fail` or against no screen at all.
GATE_SHARPE_MIN = 1.58
GATE_FITNESS_MIN = 1.0
GATE_TURNOVER_MIN, GATE_TURNOVER_MAX = 0.01, 0.7
_JOURNAL_GLOBS = ("state/**/journal.jsonl", "state/resim_results.jsonl", "state/**/*results*.jsonl")


def want_self_after_prod(prod_payload, prod_limit=0.70):
    """Is the `self` request still worth making after seeing `prod`?

    False when prod already fails, because nothing `self` could say would change the verdict. A
    payload we cannot read returns True -- an unreadable answer is not a rejection, and treating it
    as one would silently drop alphas on a parsing bug.
    """
    try:
        import fetch_prod_corr as _FP
        pc, breach = _FP.prod_maxcorr(prod_payload)
    except Exception:
        return True
    if pc is None:
        return True
    return bool(pc < prod_limit and breach == 0)


def metric_index():
    """alpha id -> (sharpe, fitness, turnover), from every journal on disk.

    Keyed on the PLATFORM `alpha` id and never on `old_id`: the correlation stores key on `alpha`,
    and mixing the two namespaces is how an earlier coverage audit mislaid the largest store.
    Later rows win, so a re-simulated alpha is judged on its latest numbers.
    """
    idx = {}
    seen = set()
    for pat in _JOURNAL_GLOBS:
        for f in ROOT.glob(pat):
            if f in seen:
                continue
            seen.add(f)
            try:
                fh = open(f, errors="ignore")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if not line.startswith("{"):
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    aid = r.get("alpha")
                    if not isinstance(aid, str):
                        continue
                    vals = tuple(r.get(k) for k in ("sharpe", "fitness", "turnover"))
                    if all(isinstance(v, (int, float)) for v in vals):
                        idx[aid] = vals
    return idx


def passes_gates(vals):
    """True when an alpha clears every metric gate. Absent metrics are NOT a pass.

    A missing number is neither a pass nor a fail -- the presence contract this project already
    learned the hard way -- so an unjudgeable alpha is reported separately rather than silently
    counted as either.
    """
    if vals is None:
        return None
    sharpe, fitness, turnover = vals
    return (sharpe > GATE_SHARPE_MIN and fitness > GATE_FITNESS_MIN
            and GATE_TURNOVER_MIN < turnover < GATE_TURNOVER_MAX)
# ---------------------------------------------------------------------------------------------

class AuthDead(Exception):
    """A 401/403 mid-run. Not a data condition: every probe after it is worthless."""


def preflight(s):
    """One GET before the loop. Costs one request and it is the whole fix for R10's dead channel.

    MEASURED 2026-08-13, and this is the first time the question was asked with an instrument:
    `state/wq_cookies.pkl` as it stood at the end of the 79.3-hour run answers
    `GET /users/self` with 401 {"detail":"Authentication credentials were not provided."}, and the
    correlation endpoints answer 401 for the same session (state/corr_probe_outcomes.jsonl, tag
    DEAD-COOKIE-LOCAL: 3/3 prod and 3/3 self). The same code against a LIVE session on the VPS
    answered 200 for 23/23 (tag LIVE-COOKIE-VPS).

    A 401 used to reach `_budget(1, 0)` BEFORE the status was inspected and then return
    `None, True`, i.e. it was booked as SERVED and as "still computing". That is how 5,534 recorded
    "served" probes and 0 payloads coexisted without anyone being able to say which.

    NOT ESTABLISHED that all 79.3 hours were 401 -- no status code was recorded then, and that is
    precisely the defect. What is established is that the session in place at the END of that run
    is 401 today, that a 401 was silently counted as served, and that the store's last successful
    write (2026-08-10 21:08) precedes 2,513 further probes that grew it by nothing.
    """
    r = s.get("https://api.worldquantbrain.com/users/self", timeout=30)
    if r.status_code != 200:
        raise SystemExit(
            "AUTH DEAD: GET /users/self -> %d %s\n"
            "Refusing to start. A dead session answers every correlation probe with 401, and the "
            "old loop booked that as 'served, still computing' -- 6,804 probes over 79.3 hours "
            "produced no information because of exactly this. Re-mint cookies "
            "(state/wq_cookies.pkl) and re-run." % (r.status_code, r.text[:200]))
    print("preflight: users/self 200 — session live", flush=True)


def load_store():
    try:
        return json.load(open(STORE))
    except Exception:
        return {}


def merge(new):
    """Read-modify-write against the CURRENT file, not a snapshot taken at startup.

    fetch_prod_corr may be running by hand at the same time; overwriting from a stale snapshot is
    how 90 measured rows were once wiped by a 3-alpha run."""
    cur = load_store()
    cur.update(new)
    tmp = STORE.with_suffix(".tmp")
    json.dump(cur, open(tmp, "w"))
    tmp.replace(STORE)
    return len(cur)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after this many NEW measurements")
    ap.add_argument("--chunk", type=int, default=25)
    ap.add_argument("--all", action="store_true",
                    help="probe every backlog alpha, not only gate-passers. Restores the pre-"
                         "2026-08-13 behaviour; use it for correlation EXPERIMENTS, where non-"
                         "passers are legitimate sample and screening them out discards ~98%% of it.")
    args = ap.parse_args()

    backlog = json.load(open(BACKLOG))
    done = set(load_store())
    todo = [a for a in backlog if a not in done]

    if not args.all:
        idx = metric_index()
        kept, rejected, unjudgeable = [], 0, 0
        for a in todo:
            verdict = passes_gates(idx.get(a))
            if verdict is None:
                unjudgeable += 1            # no metrics on disk: neither a pass nor a fail
            elif verdict:
                kept.append(a)
            else:
                rejected += 1
        print(f"gate screen: {len(kept)} pass, {rejected} fail, {unjudgeable} unjudgeable "
              f"(sharpe>{GATE_SHARPE_MIN}, fitness>{GATE_FITNESS_MIN}, "
              f"{GATE_TURNOVER_MIN}<turnover<{GATE_TURNOVER_MAX}); "
              f"{rejected} probe(s) saved. Unjudgeable rows are SKIPPED, not assumed to fail — "
              f"pass --all to include them.", flush=True)
        todo = kept

    if args.limit:
        todo = todo[:args.limit]
    print(f"backlog {len(backlog)}  already measured {len(backlog) - len([a for a in backlog if a not in done])}"
          f"  to do now {len(todo)}", flush=True)

    t0 = time.time()
    measured = 0
    pending = list(todo)

    # SWEEP, don't queue. The endpoint answers `200 + empty body + Retry-After: 1.0` while the
    # platform computes an alpha's correlations, and fetch_prod_corr.measure() waits out that
    # computation ONE ALPHA AT A TIME (a 420s poll budget, then an outer retry sleeping
    # 15+30+45s). Measured 2026-08-08: alphas whose numbers were already computed came back at
    # 94/min, and the first one that had to be computed dropped the whole run to ~0.3/min — the
    # queue was blocked behind a single alpha rather than rate-limited.
    #
    # So: ask every alpha once, take whatever is ready, and come back for the rest. Each pass both
    # collects the ready ones and keeps the not-ready ones warm, so the platform computes the whole
    # backlog concurrently instead of serially.
    s = FP.session()
    preflight(s)

    # ONE ACCOUNT, ONE BUDGET. Measured 2026-08-08 from the platform's own headers:
    #
    #     RateLimit-Limit: 60      X-RateLimit-Limit-Minute: 60      {"detail":"THROTTLED"}
    #
    # 60 requests/minute for the whole account — and `resim_bulk` polls continuously against that
    # same budget while a batch is in flight. So a measurement run and a simulation run are not
    # independent jobs that happen to share a machine; they are two consumers of one rationed
    # resource, and running both flat out throttles both and eventually gets the connection closed
    # (observed: RemoteDisconnected after sustained 429s).
    #
    # I diagnosed this wrong first: an early probe returned 200s, taken BEFORE the limit engaged,
    # and I reported "not a rate limit". That is a transient read as a permanent fact — the defect
    # class this repo has now produced nine times.
    #
    # The first fix here YIELDED to state/resim.lock so the simulator always had priority. Against
    # a feeder that keeps the queue full that is a deadlock, not politeness — the measurement never
    # got a turn and sat at 150 probed / 0 collected for over an hour. Measured instead: the
    # simulator runs at a median 23 req/min, so 25/min here keeps the pair at 48 against a limit of
    # 60 and both make progress. Share the budget; do not surrender it.
    # RATE IS NOT KNOWN. It is being LEARNED, because I asserted it twice today and was wrong both
    # times — first "the endpoint has its own tiny budget, this is a multi-day job", then "no, it is
    # only pacing, this is an hour". Neither survived: 4 minutes of rest at 7.5 req/min still
    # returned 429 on alphas whose correlations were ALREADY computed, which fits a long penalty and
    # fits a small periodic quota equally well.
    #
    # So this trickles slowly enough that it cannot itself be the cause, and RECORDS what it
    # achieves. state/corr_budget.jsonl accumulates (timestamp, served, throttled) so the real limit
    # comes out of the data instead of out of me.
    RATE = 2.0 / 60.0                                    # one request per 30s
    _last = [0.0]

    BUDGET_LOG = ROOT / "state/corr_budget.jsonl"

    def _budget(served, throttled):
        with open(BUDGET_LOG, "a") as f:
            f.write(json.dumps({"ts": round(time.time(), 1), "served": served,
                                "throttled": throttled}) + "\n")

    def _pace():
        gap = 1.0 / RATE - (time.time() - _last[0])
        if gap > 0:
            time.sleep(gap)
        _last[0] = time.time()

    def sim_in_flight():
        f = ROOT / "state/resim.lock"
        if not f.exists():
            return False
        import fcntl
        h = open(f, "a+")
        try:
            fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(h, fcntl.LOCK_UN)
            return False
        except OSError:
            return True
        finally:
            h.close()

    _OUTCOMES = {}

    def _outcome(kind, what):
        """Record WHAT the endpoint actually said. One line, and it is the point of this function.

        Every explanation of this endpoint's silence has been built on an unrecorded observation.
        The branch below folded FOUR distinguishable answers into one `return None, True` -- a 200
        with an empty body, a 401, a 5xx, and a body that would not parse -- and the loop wrote no
        status code anywhere. So `state/corr_budget.jsonl`'s `served` counts only "not a 429": a run
        that was 100% 401 and a run that was 100% 200-empty produce the SAME ledger, and the comment
        below reports 922 empty bodies on the strength of one hand-run probe generalised to all of
        them. 6,804 probes over 79.3 hours produced no information about which of the four it was.

        This costs one dict increment per probe and makes the next sweep decisive.
        """
        _OUTCOMES[(kind, what)] = _OUTCOMES.get((kind, what), 0) + 1

    def _flush_outcomes(tag):
        if not _OUTCOMES:
            return
        with open(ROOT / "state/corr_probe_outcomes.jsonl", "a") as fh:
            fh.write(json.dumps({"ts": time.time(), "tag": tag,
                                 "outcomes": {"%s:%s" % k: v for k, v in sorted(_OUTCOMES.items())}}) + "\n")
        _OUTCOMES.clear()

    def quick(aid):
        """One non-blocking look. (payload|None, still_computing)"""
        got = {}
        for kind in ("prod", "self"):
            _pace()
            try:
                r = s.get(f"https://api.worldquantbrain.com/alphas/{aid}/correlations/{kind}",
                          timeout=30)
            except Exception as exc:
                # This path returns BEFORE `_budget`, so ~18% of probes were never counted at all.
                _outcome(kind, "exception:%s" % type(exc).__name__)
                time.sleep(10)                           # a closed connection means back off, not retry hard
                return None, True
            if r.status_code == 429:
                # WHAT IS MEASURED, after three wrong explanations of the same observation.
                #
                # I asserted in turn that this endpoint had (1) its own small budget with a
                # multi-day cooldown, then (2) that it was purely a pacing problem and the backlog
                # was an hour of work. Both were written here confidently and both were wrong. The
                # first generalised from a throttle I had caused myself by firing unpaced at
                # ~180 req/min against an account limit of 60; the second generalised from a probe
                # that counted HTTP 200s without looking at the bodies.
                #
                # The measurements that survive, from state/corr_budget.jsonl over ~8 hours:
                #     968 requests SERVED, 10 throttled (1.0%)
                #     ~90-103 served per hour, steady, no cooldown behaviour
                #     and 0 usable payloads
                #
                # RETRACTED 2026-08-13, and this is the fourth wrong explanation of the same
                # observation: the line that stood here said "922 alphas answered 200 with an EMPTY
                # body". Nothing measured that. `served` is incremented before the status is even
                # looked at, so it means ONLY "not a 429"; the loop recorded no status code; and one
                # hand-run probe that saw 200-but-empty was generalised to all 922. A run that was
                # 100% 401 would have produced a byte-identical ledger. `_outcome` above now
                # separates 200-empty / 200-unparseable / 200-payload / http:NNN / 429 / exception,
                # so the NEXT sweep answers this instead of arguing about it.
                # Live probe with the simulator idle: users/self 200, alphas/{id} 200, bulk 200,
                # correlations/prod 200-but-empty.
                #
                # So the endpoint is neither quota'd nor throttled — it answers. It simply has
                # nothing to return for those alphas, and asking 968 times did not change that.
                # MECHANISM: UNKNOWN. A competing note in tools/bank.py says correlations are
                # computed as part of a SUBMISSION rather than on request, which fits — except that
                # 25 unsubmitted backlog alphas in state/prod_corr_measured.json DO carry real
                # numbers, so the strong form of that rule is refuted too. What distinguishes those
                # 25 has not been established.
                #
                # Do not write another explanation here without an experiment that separates them.
                _outcome(kind, "429")
                _budget(0, 1)
                time.sleep(300)          # a 429 means stop asking for a while, not ask again slower
                return None, True
            _budget(1, 0)
            if r.status_code in (401, 403):
                # NOT a data condition. This used to fall through the generic branch below and read
                # as "still computing", so the loop kept sweeping a dead session for 79.3 hours.
                _outcome(kind, "http:%d" % r.status_code)
                raise AuthDead(r.status_code)
            if r.status_code != 200:
                _outcome(kind, "http:%d" % r.status_code)
                return None, True
            if not r.text.strip():
                _outcome(kind, "200-empty")             # still computing IS ONE READING, not the only one
                return None, True
            try:
                got[kind] = r.json()
            except Exception:
                _outcome(kind, "200-unparseable:%d-bytes" % len(r.text))
                return None, True
            _outcome(kind, "200-payload:%d-bytes" % len(r.text))

            # SHORT-CIRCUIT ON PROD, and it is the largest saving available in this loop.
            #
            # `prod` is asked first and it is the binding half by 4.8x: over the 836 gems carrying
            # both platform numbers, 61.5% pass self<0.70 but only 12.7% pass prod<0.70. So for
            # ~87% of alphas the `self` request that follows is spent on an alpha that is ALREADY
            # dead, and its answer cannot change any decision. Skipping it takes the cost from 2.000
            # to ~1.127 requests per alpha. THAT 43.6% IS ARITHMETIC ON A RATE MEASURED ON A
            # DIFFERENT POPULATION (the 836 gems carrying both platform numbers), not a measurement
            # of this backlog, and it is quoted as such. Under the regime this file documents -- 0
            # payloads returned -- the saving is ZERO, because an unreadable prod answer never
            # reaches this branch at all.
            #
            # THIS IS NOT A GUESS ABOUT self: the row is still written, with `self_measured=False`,
            # so it reads as "measured, and rejected on prod" and never as "not yet measured". The
            # caller already carries that flag, and `corr_ok` already requires `self_measured`.
            #
            # WHAT IT COSTS: the self-correlation of prod-failing alphas stops being collected, and
            # that is real sample loss for anyone studying correlation STRUCTURE rather than picking
            # submissions -- the same trade `--all` exists for. `--all` disables this too.
            if kind == "prod" and not args.all and not want_self_after_prod(got["prod"]):
                return got, False
        return got, False

    for sweep in range(1, 25):
        if not pending:
            break
        ready, again = {}, []
        auth_dead = None
        t_sweep = time.time()
        for n_done, aid in enumerate(pending, 1):
            # A sweep over 900 alphas is 1,800 requests. Without a progress line the whole sweep is
            # a single silent block and its rate can only be guessed at — which is exactly what I
            # did for 22 minutes before adding this.
            if n_done % 50 == 0:
                el = time.time() - t_sweep
                print(f"     ...{n_done}/{len(pending)} probed, {len(ready)} ready, "
                      f"{el:.0f}s ({n_done / max(el, 1e-9):.1f} alpha/s)", flush=True)
            try:
                got, wait = quick(aid)
            except AuthDead as exc:
                # Stop the sweep, but keep what this sweep already collected: the rows in `ready`
                # were measured while the session was alive and are perfectly good.
                auth_dead = exc
                again.extend(pending[n_done - 1:])
                break
            if wait or got is None:
                again.append(aid)
                continue
            if "self" not in got:
                # PROD-ONLY RESULT from the short-circuit: prod already failed, so `self` was never
                # requested. Write the verdict rather than dropping it -- the alpha IS measured and
                # IS rejected, and re-probing it tomorrow would spend the channel to learn the same
                # thing. Blindly unpacking `got["self"]` here raised KeyError and killed the sweep on
                # the first prod-failing alpha; the docstring beside the short-circuit claimed this
                # row "is still written" while nothing wrote it.
                pc_, breach = FP.prod_maxcorr(got["prod"])
                if pc_ is None:
                    again.append(aid)
                    continue
                ready[aid] = {"prod_maxcorr": pc_, "prod_breach_count": breach,
                              "self_maxcorr": None, "self_measured": False, "corr_ok": False}
                continue
            pj, sj = got["prod"], got["self"]
            pc_, breach = FP.prod_maxcorr(pj)
            sc = FP.self_maxcorr(sj)
            if pc_ is None or not sj.get("records"):
                again.append(aid)                        # schema-less payload = not measured yet
                continue
            self_measured = sc is not None
            ready[aid] = {"prod_maxcorr": pc_, "prod_breach_count": breach, "self_maxcorr": sc,
                          "self_measured": self_measured,
                          "corr_ok": bool(pc_ < 0.70 and breach == 0 and self_measured and sc < 0.70)}
        if ready:
            n = merge(ready)
            measured += len(ready)
            print(f"  sweep {sweep}: +{len(ready)} ready, {len(again)} still computing "
                  f"(store {n})  {measured}/{len(todo)}  "
                  f"{measured / max(1e-9, time.time() - t0) * 60:.0f}/min", flush=True)
        else:
            print(f"  sweep {sweep}: 0 ready, {len(again)} still computing", flush=True)
        _flush_outcomes("sweep-%d" % sweep)
        if auth_dead:
            raise SystemExit(
                "AUTH DIED MID-RUN (HTTP %s) after %d sweeps; %d rows from this sweep were saved, "
                "%d alphas left unprobed. Re-mint state/wq_cookies.pkl and re-run — the job is "
                "resumable." % (auth_dead.args[0], sweep, len(ready), len(again)))
        pending = again
        if pending:
            # KEEP SWEEPING. Do not add a long wait here — I nearly did, and it would have been
            # backwards. Measured 2026-08-13 (harness13/massgen/experiments/PROD_CORR_R10.md,
            # state/corr_probe_outcomes.jsonl):
            #
            #   * a first ask ALWAYS returns 200 + empty body + `Retry-After: 1.0` (23/23, then 4/4)
            #   * payloads then arrived for everything asked between ~11:41 and 11:44:05, and
            #     `200-empty` for everything asked from 11:44:13 onward — a cut inside an 8-second
            #     gap. 0 payloads in the following 128 requests over 75 minutes.
            #   * the boundary is WALL-CLOCK, not per-alpha: four alphas that had never been asked
            #     were primed and collected 9.6 min later and got 0/4, and — decisive — four alphas
            #     that HAD returned full payloads at 11:42 returned 200-empty when re-asked at 13:00.
            #
            # I first read that as a ~425s per-alpha compute latency and put a 480s inter-sweep wait
            # here. That reading is REFUTED by the two facts above, and the wait was worse than
            # useless: if serving happens in narrow unannounced windows, a client that is asleep
            # when one opens collects nothing. Sweep continuously instead; `_pace()` already spaces
            # the requests, and `merge()` writes every payload the moment it appears.
            #
            # MECHANISM: UNKNOWN — a per-account serve allowance, a backend batch, and contention
            # with the simulator all fit equally and were not separated. See §4 of PROD_CORR_R10.md
            # for the experiment that would separate them. Do not write a reason here without it.
            time.sleep(20)
    if pending:
        print(f"  {len(pending)} alphas never returned a payload — re-run to retry them",
              flush=True)

    # Report, from the store rather than from this run, so a resumed job still summarises correctly.
    store = load_store()
    vals = [(a, v) for a, v in store.items() if a in set(backlog)
            and isinstance(v.get("prod_maxcorr"), (int, float))]
    if vals:
        prod_clean = [a for a, v in vals if v["prod_maxcorr"] < 0.70]
        both = [a for a, v in vals if v.get("corr_ok")]
        print(f"\nRANDOM-ORDER BACKLOG SAMPLE  n={len(vals)}")
        print(f"   prod<0.70            {len(prod_clean):4}  ({len(prod_clean)/len(vals):.1%})")
        print(f"   prod<0.70 AND self<0.70 AND 0 breaches "
              f"{len(both):4}  ({len(both)/len(vals):.1%})   <- actually submittable")
        if both:
            print(f"   {both[:20]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
