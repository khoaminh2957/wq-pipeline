"""Measure prod/self correlation for the deduplicated climb candidates. READ ONLY, never posts.

TWO PHASES, AND THE WAIT BETWEEN THEM IS THE POINT (Khoa, 2026-08-14: "thử tăng thời gian chờ prod
corr lên và ko làm gì hết trong lúc chờ").

The first GET on `/alphas/{id}/correlations/{kind}` does not return a correlation -- it returns HTTP
200 with an EMPTY BODY and starts the platform computing. All twelve of the first probe came back
that way, which is not a failure; it is work beginning. A second read minutes later returned real
numbers (prod 0.5056-0.6640, self 0.185-0.248).

So: TRIGGER every candidate, then WAIT doing nothing at all, then READ. Simulating during the wait
would spend quota to produce more candidates for a channel that is already the bottleneck.

DEDUPLICATED on Khoa's instruction: 752 candidates collapse to 77 distinct signals, because a hill
climb grows ONE baseline and consecutive rounds differ by a single wrapper over the same data. A
probe on the 40th reshape answers the same question as the 1st.
"""
import json, sys, time, pathlib
sys.path.insert(0, "tools")
import climb as C, layered_sim as LS

N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
WAIT_S = int(sys.argv[2]) if len(sys.argv) > 2 else 900     # 15 min, was an immediate re-read
PACE_S = 1.1                                                # 60 req/min is the account limit


def read(s, aid, kind):
    try:
        r = s.get("%s/alphas/%s/correlations/%s" % (LS.API, aid, kind), timeout=30)
    except Exception as exc:
        return None, "exception:%s" % type(exc).__name__
    if r.status_code != 200:
        # RECORD THE HEADERS, DO NOT GUESS. This symptom has been explained wrongly twice in this
        # repo and PIPELINE.md keeps it at MECHANISM: UNKNOWN. r.headers was being discarded, so no
        # 429 in the entire record carries the one thing that would settle it.
        h = {k: v for k, v in r.headers.items()
             if k.lower().startswith(("ratelimit", "x-ratelimit", "retry-after"))}
        if h:
            return None, "http:%d %s" % (r.status_code, ";".join("%s=%s" % kv for kv in sorted(h.items())))
        return None, "http:%d no-rate-headers" % r.status_code
    body = r.text or ""
    if not body.strip():
        return None, "200-empty (computing)"
    try:
        j = r.json()
    except ValueError:
        return None, "200-unparseable:%dB" % len(body)
    if isinstance(j, dict) and "max" in j:
        return j["max"], "ok"
    return None, "payload:%dB-no-max" % len(body)


reps, total = C.candidate_reps()
reps = reps[:N]
print("candidates %d -> signals %d; probing %d, wait %d s between phases"
      % (total, len(C.candidate_reps()[0]), len(reps), WAIT_S), flush=True)
s = LS.session()
LS.keep_jar_fresh(s)   # a 60-target probe runs ~40 min; a tap mid-run must be picked up

print("--- phase 1: trigger ---", flush=True)
pending, early = [], []
for r in reps:
    aid = r["alpha"]
    got = {}
    for kind in ("prod", "self"):
        time.sleep(PACE_S)
        v, why = read(s, aid, kind)
        if v is not None:
            got[kind] = v
    if len(got) < 2:
        pending.append(aid)
    else:
        # RECORD IT HERE, not only in phase 2. Phase 1 was printing values and throwing them away,
        # so an alpha whose correlations were ALREADY computed never reached the store -- which is
        # how `88pYR1gz` stayed the announced "best alpha" while its prod correlation was 1.0.
        row = {"alpha": aid, "fitness": r.get("fitness"), "sharpe": r.get("sharpe"),
               "read_at": time.time()}
        row.update(got)
        early.append(row)
        print("  %-10s already computed: prod %s self %s" % (aid, got.get("prod"), got.get("self")),
              flush=True)
print("triggered %d, %d already had values" % (len(pending), len(reps) - len(pending)), flush=True)
if early:
    pathlib.Path("state/climb").mkdir(parents=True, exist_ok=True)
    with open("state/climb/probe.jsonl", "a") as fh:
        for row in early:
            fh.write(json.dumps(row) + "\n")
    print("stored %d value(s) found in phase 1" % len(early), flush=True)

# PHASE 2 IS NOW OPTIONAL, AND WAIT_S=0 SKIPS IT ENTIRELY.
#
# Measured 2026-08-16: in one run 21 of 21 alphas returned a REAL correlation in phase 1 and
# 200-empty 900 s later in phase 2. About 95%% of every correlation this pipeline has ever measured
# came from phase 1; the whole wait produced roughly 4 of 83. The block also costs the round >=900 s
# of doing nothing -- forty such blocks logged -- while 81 of 111 queued signals had never been
# probed even once, because the slice was a fixed top-30.
#
# Khoa, 2026-08-16: drop the wait and widen the slice, both. Phase 1 has already been written to
# disk above, so exiting here loses nothing.
if WAIT_S <= 0:
    print("--- phase 2 SKIPPED (WAIT_S=0); phase-1 values are already stored ---", flush=True)
    raise SystemExit(0)

if pending:
    print("--- waiting %d s, doing nothing ---" % WAIT_S, flush=True)
    time.sleep(WAIT_S)

print("--- phase 2: read ---", flush=True)
out = []
for r in reps:
    aid = r["alpha"]
    row = {"alpha": aid, "fitness": r.get("fitness"), "sharpe": r.get("sharpe"),
           "read_at": time.time()}
    for kind in ("prod", "self"):
        time.sleep(PACE_S)
        v, why = read(s, aid, kind)
        row[kind] = v if v is not None else why
    print("  %-10s fit %-6s prod %-22s self %s"
          % (aid, row.get("fitness"), row.get("prod"), row.get("self")), flush=True)
    out.append(row)

pathlib.Path("state/climb").mkdir(parents=True, exist_ok=True)
with open("state/climb/probe.jsonl", "a") as fh:
    for row in out:
        fh.write(json.dumps(row) + "\n")

vals = [r["prod"] for r in out if isinstance(r.get("prod"), (int, float))]
still = sum(1 for r in out if isinstance(r.get("prod"), str) and "computing" in r["prod"])
print("\nmeasured %d of %d; %d still computing" % (len(vals), len(out), still))
if vals:
    vals.sort()
    print("prod-corr min %.4f median %.4f max %.4f" % (vals[0], vals[len(vals)//2], vals[-1]))
    print("under the 0.71 try/skip line: %d of %d" % (sum(1 for v in vals if v < C.PROD_CORR_MAX),
                                                      len(vals)))
