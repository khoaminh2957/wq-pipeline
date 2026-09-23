#!/usr/bin/env python3
"""driver.py — the unattended 10-round alpha search. One process, one wall-clock deadline.

Khoa 2026-07-29: run end to end for 4 hours, 10 self-improving rounds, no permission prompts,
no idle waiting, no hand-offs. Every previous attempt broke at a hand-off: a stage finished, a
report was produced, and the chain stopped until a human said "tiep". So there are no stages here
that end in a report -- a round always ends by starting the next round.

Per round:
  1. PULL the next slice from the pre-generated candidate pool, biased by the knowledge file
  2. PRECHECK + SIM (blocking, single stream -- the account allows one)
  3. SCORE with the canonical gate module, which blocks on ANY platform FAIL (tools/funnel/gates.py)
  4. MEASURE prod/self correlation for every gate-passer IMMEDIATELY -- the measurement window
     closes: every successful read this project has made happened minutes after its own batch
  5. LOG winners/near-misses, then SUBMIT anything clean up to the remaining daily budget
  6. LEARN: score every axis (skeleton, dataset, neutralization, decay, universe, leg count) by
     what it actually produced this round, write knowledge.json, and let it steer the next round

Deadline governs everything. Rounds shrink to fit the time left rather than overrunning it.

Usage: python3 tools/autoloop/driver.py --pool <pool.json> --hours 4 --rounds 10
"""
from __future__ import annotations
import argparse, json, csv, subprocess, sys, time, pathlib, fcntl, datetime, statistics, traceback
from collections import defaultdict

ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
sys.path.insert(0, str(ROOT / "tools"))
import gates                                    # noqa: E402  canonical gate definition
from fetch_prod_corr import prod_maxcorr, self_maxcorr   # noqa: E402
import daily_budget as DB                      # noqa: E402  eastern-day simulation cap

ST = ROOT / "state"
AL = ST / "autoloop"
KNOW = AL / "knowledge.json"
LEDGER = AL / "rounds.jsonl"
WIN, NEAR = ST / "funnel/winners.csv", ST / "funnel/near_misses.csv"
PC = ST / "prod_corr_measured.json"
DAILY_CAP = 4
API = "https://api.worldquantbrain.com"

# Axes the knowledge file scores. Each candidate carries these in `meta` so a round's outcome can
# be attributed back to the choices that produced it.
AXES = ("skeleton", "dataset", "neutralization", "decay", "universe", "legs", "truncation")
# No single mechanic may take more than this share of a round's exploit budget.
MECHANIC_CAP = 0.30
# ...and no single CATEGORY may exceed this, since its sub-mechanics share a signal source.
CATEGORY_CAP = 0.35
# `dataset` picks the pyramid cell -- the objective -- so it must not be averaged flat against
# settings axes like decay or truncation. See pick_slice.val().
DATASET_WEIGHT = 6.0


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------- session / auth
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


def ensure_auth(max_wait_s=1800):
    """Never die on a 401. Re-arm the persona flow and keep polling until Khoa taps the link.

    Returns True once authed, False if the wait budget runs out. The URL is printed AND left in
    state/persona_url.txt so it can be surfaced without this process being in the foreground."""
    import requests
    try:
        if session().get(f"{API}/users/self", timeout=20).status_code == 200:
            return True
    except Exception:
        pass
    log("AUTH: 401 -- re-arming persona flow")
    subprocess.Popen([sys.executable, str(ROOT / "tools/auth_only.py")],
                     stdout=open(ST / "auth_only.out", "w"), stderr=subprocess.STDOUT)
    deadline = time.time() + max_wait_s
    shown = None
    while time.time() < deadline:
        try:
            url = (ST / "persona_url.txt").read_text().strip()
            if url != shown:
                shown = url
                log(f"AUTH: TAP THIS -> {url}")
        except Exception:
            pass
        time.sleep(15)
        try:
            if session().get(f"{API}/users/self", timeout=20).status_code == 200:
                log("AUTH: restored")
                return True
        except Exception:
            continue
    log("AUTH: still unauthenticated after the wait budget")
    return False


# --------------------------------------------------------------------------- knowledge
def load_knowledge():
    if KNOW.exists():
        try:
            return json.load(open(KNOW))
        except Exception:
            pass
    return {"round": 0, "scores": {a: {} for a in AXES}, "history": []}


def score_axes(rows, measured):
    """Value of each axis VALUE this round.

    An axis value is worth what it produced, in this order of importance: a clean gem (gate-pass
    AND prod-corr <= 0.7) is the product; a gate-pass with a breached correlation is a near miss;
    everything else is scored on how close it came to IS_LADDER_SHARPE, falling back to fitness.

    Ladder is the right partial-credit signal because it is the binding gate: across the journal,
    0 of 5,775 ladder-FAIL rows are zero-fail, and the rule is a clean threshold (PASS iff value
    > 1.58, no counterexamples in 7,302 rows). It is driven by fitness (r=+0.77) and returns
    (r=+0.59) and is INDEPENDENT of turnover (r=-0.01).

    Deliberately not scored: raw sharpe. Sharpe above ~2.5 is exactly where prod-correlation
    breaches, so rewarding it steers the search into the wall it is trying to get around."""
    tally = {a: defaultdict(lambda: [0.0, 0]) for a in AXES}
    for r in rows:
        m = r.get("meta") or {}
        ok = r.get("_pass")
        aid = r.get("_alpha")
        # NOT `m` -- that name already holds this row's META, and the axis loop below
        # reads m.get(axis). Shadowing it silently zeroed every tally and disabled learning.
        mc = (measured.get(aid) or {}) if aid else {}
        pc, sc = mc.get("prod_maxcorr"), mc.get("self_maxcorr")
        if ok and pc is not None and pc <= 0.7:
            v = 10.0
        elif ok:
            # A gate-pass that breaches is worth something, but NOT a flat 3. Rewarding bare
            # gate-passing let the loop climb 2.9% -> 4.6% -> 8.0% while every measured passer
            # breached (median prod 0.777, min 0.729) and self-correlations ran 0.73-0.82 -- it had
            # converged on one duplicated family. Self-correlation is the marker of that
            # convergence, so it is priced in: a passer that duplicates what we already have is
            # worth barely more than a near-miss.
            v = 3.0
            if isinstance(sc, (int, float)) and sc >= 0.7:
                v = 1.0
            if isinstance(pc, (int, float)):
                v *= max(0.3, min(1.0, (0.85 - pc) / 0.15))   # 0.70 -> full, 0.85+ -> floor
        else:
            lad = r.get("_ladder")
            v = (min(1.0, max(0.0, lad / 1.58)) if isinstance(lad, (int, float))
                 else min(1.0, (r.get("_fitness") or 0.0)))
        for a in AXES:
            if m.get(a) is None:
                continue
            cell = tally[a][str(m[a])]
            cell[0] += v
            cell[1] += 1
    # SHRINK toward the round's own mean by sample size. A raw mean treats 6 observations and 234
    # observations as equally trustworthy: Institutions/Institutions scored 0.27 off 6 rows (one of
    # which was a CLEAN gem) while Model/ML-AI scored 0.61 off 234, so the exploit list locked the
    # small mechanic out permanently and its 121 pooled rows were never drawn. Explore only rescues
    # axis values that are UNSCORED, not ones scored badly on a tiny sample. Pulling low-n cells
    # toward neutral keeps them in contention until they have actually been tried.
    K0 = 12.0
    out = {}
    for a, d in tally.items():
        tot_s = sum(x[0] for x in d.values())
        tot_n = sum(x[1] for x in d.values()) or 1
        prior = tot_s / tot_n
        out[a] = {k: round((s + prior * K0) / (n + K0), 4) for k, (s, n) in d.items() if n >= 3}
    return out


def merge_knowledge(k, fresh, rnd):
    """Exponential blend so one lucky round cannot capture the search.

    Khoa's standing instruction from the previous goal: check whether a round's measurement was
    luck before acting on it. A 0.6/0.4 blend against the running score is that check made
    structural -- an axis has to keep performing across rounds to keep its weight."""
    for a in AXES:
        prev = k["scores"].setdefault(a, {})
        for val, s in fresh.get(a, {}).items():
            prev[val] = round(0.6 * prev.get(val, s) + 0.4 * s, 4)
    k["round"] = rnd
    return k


# --------------------------------------------------------------------------- pool selection
def _stratify(cands):
    """Order unscored candidates by a STRIDE through the pool, preserving bucket proportions.

    Two wrong versions preceded this one. File order made round 1 a single bucket (120/120
    STATISTICAL) -- one-armed, nothing to compare. Round-robin over
    (skeleton, neutralization, dataset) cells then over-corrected: it equalises CELLS, and the 5%
    explore bucket holds ~90 one-row skeleton chains against a handful of cells in the five
    evidence-backed buckets, so explore captured most of round 1 -- which is why the first 80
    scored rows had a median sharpe of 0.03.

    The pool is already written bucket-by-bucket in the intended proportions, so walking it with a
    stride samples every bucket in proportion AND spreads across the diversity inside each one.
    Deterministic, and it needs no bucket label in the metadata."""
    n = len(cands)
    if n < 4:
        return list(cands)
    stride = max(2, int(n ** 0.5))
    while stride < n and not _coprime(stride, n):
        stride += 1                              # coprime with n => the walk visits every index once
    if not _coprime(stride, n):
        return list(cands)
    return [cands[(i * stride) % n] for i in range(n)]


def _coprime(a, b):
    while b:
        a, b = b, a % b
    return a == 1


def _dead_cells():
    """Categories already holding 3 alphas. Fails OPEN: an unreadable counter must not empty the
    draw, and the submit-side cell gate still fails closed on the irreversible action."""
    try:
        import submit_alphas as SA
        counts, _ = SA._cell_counts(SA.session(), "USA", 1)
        counts = dict(counts or {})
        # Include cells filled by TODAY's submits that the platform has not credited yet -- pyramid
        # credit follows the alpha going ACTIVE, so a cell closed minutes ago still reads short and
        # the miner would spend the rest of a 5000-sim day on it.
        for c, n in SA._submitted_today_by_cell(counts).items():
            counts[c] = counts.get(c, 0) + n
        return {k for k, v in counts.items() if v >= 3}
    except Exception:
        return set()


def pick_slice(pool, used_ids, n, knowledge):
    """Take the n best-scoring unused candidates, with a fixed exploration share.

    70% exploit (rank by the knowledge score of the candidate's axis values), 30% explore (round
    robin over axis values the knowledge file has never scored). Without the explore share the
    loop converges onto whatever won round 1 and stops discovering, which is how the previous
    iterations plateaued."""
    sc = knowledge.get("scores", {})
    avail = [c for c in pool if c["old_id"] not in used_ids]
    if not avail:
        return []

    def val(c):
        """Weighted mean over the axes, NOT a flat one.

        `dataset` is not a setting like the others -- it decides which PYRAMID CELL the alpha can
        fill, which is the objective itself. A flat mean divides its signal by seven and buries it:
        measured 2026-08-01 on pool_x8, cell scores collapsed into 0.3096-0.3312 (a 0.02 spread)
        while the dataset axis alone spanned 0.35-0.55 (0.20). News/News Sentiment ranked SECOND on
        the dataset axis and DEAD LAST overall, so 665 News rows -- the best-yielding cell at 13.6%
        zero-fail -- were never drawn across three rounds and the round yield fell to 0.7%."""
        m = c.get("meta") or {}
        num = den = 0.0
        for a in AXES:
            if m.get(a) is None:
                continue
            v = sc.get(a, {}).get(str(m[a]))
            if v is None:
                continue
            w = DATASET_WEIGHT if a == "dataset" else 1.0
            num += v * w
            den += w
        return num / den if den else None

    scored = [(val(c), c) for c in avail]
    known = sorted([x for x in scored if x[0] is not None], key=lambda x: -x[0])
    unknown = _stratify([c for v, c in scored if v is None])
    n_exploit = int(n * 0.7)

    # CAP the exploit share per mechanic. Stratifying the POOL is not enough: once one axis value
    # scores high the ranked exploit list is entirely that value, and the round collapses onto it.
    # Measured 2026-07-30: round 2 drew 154 of 155 rows from Fundamental/Fundamental alone, exactly
    # the single-family concentration that made an earlier run produce 26 gems worth 1 submission.
    # Submitting one alpha kills its whole family, so a round spent inside one family is worth at
    # most one alpha however many gate-passers it yields.
    # The cap applies to the WHOLE slice, not just the exploit half: an uncapped explore share or
    # backfill re-concentrates it. First pass fills under the cap from exploit-then-explore; a
    # second pass relaxes the cap only if the slice cannot otherwise be filled.
    cap = max(3, int(n * MECHANIC_CAP))
    cat_cap = max(6, int(n * CATEGORY_CAP))
    mech = lambda c: str((c.get("meta") or {}).get("dataset"))
    # Cap the CATEGORY too, not just the mechanic. `Model` owns seven sub-mechanics and `Earnings`
    # two, so a per-mechanic cap of 30% let one category take 40% (round 2) then 53% (round 3) --
    # and a category's sub-mechanics share a signal source, which is what actually decides how many
    # submittable alphas a round can yield.
    per, per_cat, out, seen = defaultdict(int), defaultdict(int), [], set()
    for c in [c for _, c in known] + unknown:
        if len(out) >= n:
            break
        k = mech(c)
        kc = k.split("/")[0]
        if per[k] >= cap or per_cat[kc] >= cat_cap or c["old_id"] in seen:
            continue
        per[k] += 1
        per_cat[kc] += 1
        seen.add(c["old_id"])
        out.append(c)
    if len(out) < n:                    # pool too thin under the cap -- fill the remainder freely
        for c in [c for _, c in known] + unknown:
            if len(out) >= n:
                break
            if c["old_id"] not in seen:
                seen.add(c["old_id"])
                out.append(c)
    return out[:n]


# --------------------------------------------------------------------------- sim
def stream_busy():
    try:
        f = open(ST / "resim.lock", "a+")
    except OSError:
        return True
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        f.close()


def run_sim(batch_path, stall=600):
    """Simulate one batch. `stall` is how long run_multisim tolerates SILENCE before giving up.

    It used to be 1800s, and that is pure waiting whenever a batch does not complete: PE round 3
    journaled 83/93 and then sat for the full 30 minutes before declaring failure, on a run that
    only had 1.56h left. Measured behaviour of a healthy batch is 113-191 rows in 15-23 minutes
    with tail gaps around 35s, so 600s is still ~17x the largest normal gap. Nothing is lost by
    cutting it: the grace loop right after this call keeps re-harvesting for another ~6 minutes and
    stops after 45s of no new rows, which is what actually recovers stragglers."""
    for _ in range(90):
        if not stream_busy():
            break
        time.sleep(20)
    r = subprocess.run([sys.executable, str(ROOT / "tools/funnel/run_multisim.py"), "--sweep",
                        "--stall-timeout", str(stall), str(batch_path)],
                       capture_output=True, text=True)
    tail = ((r.stdout or "") + (r.stderr or "")).strip()[-400:]
    log(f"SIM: {tail.splitlines()[-1] if tail else 'no output'}")
    return r.returncode == 0, tail


def harvest(prefix, oids):
    out = {}
    for line in open(ST / "resim_results.jsonl"):
        if prefix not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("old_id") in oids and d.get("checks"):
            out[d["old_id"]] = d
    return out


# --------------------------------------------------------------------------- correlation
def fetch_corr(s, aid, kind, budget=90.0):
    t0 = time.time()
    while time.time() - t0 < budget:
        try:
            r = s.get(f"{API}/alphas/{aid}/correlations/{kind}", timeout=30)
        except Exception:
            time.sleep(3)
            continue
        # Retry-After may be an HTTP-date, not a number; float() would raise and lose the round.
        try:
            ra = float(r.headers.get("Retry-After") or 0) or None
        except ValueError:
            ra = None
        if r.status_code == 429:
            time.sleep(min(ra or 15, 30))
            continue
        if r.text:
            try:
                j = r.json()
            except Exception:
                return None
            if isinstance(j, dict) and "schema" in j:
                return j
            time.sleep(min(ra or 2, 5))            # valid JSON but not a payload = still computing
            continue
        time.sleep(min(ra or 1, 3))
    return None


PEND = AL / "corr_pending.json"
MAX_PARK_TRIES = 3        # rounds an unmeasurable alpha may be retried before it is dropped
BREAK_AFTER = 3           # consecutive measurement misses that mean the service, not the alpha


def measure(passers, res_by_alpha, fresh_budget=20.0, aged_budget=60.0):
    """Measure every gate-passer now; an unmeasured alpha stays UNKNOWN, never a pass.

    Correlations are computed lazily and are almost never ready seconds after a sim, so the old
    flat 90s-per-fetch budget spent 180s per alpha to print UNMEASURED: rounds 2 and 3 of the
    2026-07-31 run burned 27 minutes that way, on the critical path, for nothing. Fresh alphas now
    get a short look, and whatever is still unmeasured is PARKED and retried at the top of the next
    round, by which point it is ~25 minutes older and far more likely to resolve. That trades dead
    waiting for real coverage -- and coverage, not generation, is what limits yield.

    The AGED budget was left at 90s in the first version of this fix, on the theory that an older
    alpha deserves a longer look. It does not: a correlation either exists or is still being
    computed, so polling 90s instead of 30s buys almost nothing while costing 3 minutes per alpha
    (90s x prod + 90s x self). PX round 5 sat 33 minutes on 11 parked ids for exactly this reason --
    the same dead-wait the fresh budget was cut to remove, merely moved onto the other branch. What
    actually resolves a parked alpha is the NEXT ROUND, not a longer wait inside this one."""
    s = session()
    store = json.load(open(PC)) if PC.exists() else {}
    try:
        pending = json.load(open(PEND))
    except Exception:
        pending = {}
    fresh = set(passers)
    # Aged first: they have had a whole round to become available, and they are the cheap wins.
    order = ([(a, aged_budget) for a in pending if a not in fresh]
             + [(a, fresh_budget) for a in passers])
    # Parking must be BOUNDED. An id that can never resolve would otherwise be retried at the full
    # aged budget every round forever -- two stray test fixtures left in this file cost 6 minutes a
    # round before they were spotted. Three rounds is well past the point where a real correlation
    # becomes available; after that the alpha is dropped and simply stays unmeasured.
    clean, measured = [], []
    # CIRCUIT BREAKER. Correlation availability is an all-or-nothing property of the service, not
    # of the individual alpha: when it is computing, EVERY id comes back empty. Paying the full
    # budget per alpha to rediscover that costs 41s each -- PU round 1 spent 12 minutes on 18
    # consecutive misses. After a few in a row, park the remainder for free and let the next round
    # try again. Skipped ids must NOT burn a park try, or an outage would exhaust MAX_PARK_TRIES
    # and drop perfectly good alphas that were never actually looked at.
    # The breaker exists to stop paying a full budget for 18 consecutive FRESH misses. It must not
    # apply to the parked ones: there are only ever a handful, they are the cheap wins, and the
    # premise that availability is "all-or-nothing across the service" is measurably false --
    # probing the six alphas parked by SY round 5, Xgojp8km resolved in 35s (prod 0.6767 breach 0,
    # self 0.6572, a CLEAN gem) while two others returned nothing in 90s. Skipping it cost a gem
    # that reached neither ledger. Budgets raised too: 35s beat both the old 20s and 30s ceilings.
    aged_ids = {a for a in pending if a not in fresh}
    misses = 0
    for aid, budget in order:
        if misses >= BREAK_AFTER and aid not in aged_ids:
            # Skipping the probe ENTIRELY was a mistake in the first version of this breaker.
            # These recordsets are computed ON DEMAND: the first request queues the work and
            # returns 200 with an empty body, and the data is ready ~1-2 minutes later. A skipped
            # alpha therefore never gets its computation started, so it parks forever and is
            # eventually dropped by MAX_PARK_TRIES having never once been looked at. Verified by
            # hand on 3qeNwxKz: empty on the probe that queued it, full payload 1 second into the
            # next request. So still fire ONE request per skipped id and hang up immediately --
            # ~1s instead of 41s, and next round finds the answer waiting.
            for kind in ("prod", "self"):
                try:
                    s.get(f"{API}/alphas/{aid}/correlations/{kind}", timeout=10)
                except Exception:
                    pass
            prev = pending.get(aid) or {}
            pending[aid] = {"row": res_by_alpha.get(aid) or prev.get("row") or {},
                            "tries": prev.get("tries", 0)}
            continue
        pc, breach = prod_maxcorr(fetch_corr(s, aid, "prod", budget))
        sj = fetch_corr(s, aid, "self", budget)
        sc = self_maxcorr(sj)
        # `records: []` is the platform saying STILL COMPUTING, and `[] is not None`. Guarding on
        # `is None` let an unmeasured self-correlation through as a pass, which is the exact defect
        # submit_alphas._fresh_corr_ok was fixed for (it burned e7x0G7ag and YPggJ8p6). Truthiness,
        # not identity: no rows means not measured, and not measured is never clean.
        if pc is None or not (sj and sj.get("records")):
            # Park it with its result row so the next round can retry without re-deriving context.
            prev = pending.get(aid) or {}
            tries = prev.get("tries", 0) + 1
            if tries > MAX_PARK_TRIES:
                pending.pop(aid, None)
                log(f"  {aid} UNMEASURED after {MAX_PARK_TRIES} rounds -- dropped from the queue")
                continue
            pending[aid] = {"row": res_by_alpha.get(aid) or prev.get("row") or {}, "tries": tries}
            log(f"  {aid} UNMEASURED -- parked, try {tries}/{MAX_PARK_TRIES} ({len(pending)} pending)")
            misses += 1
            if misses == BREAK_AFTER:
                log(f"  correlation service looks down ({misses} misses in a row) -- "
                    f"parking the rest of this round's queue without paying for them")
            continue
        # Read the result row BEFORE dropping it from the parked set: an alpha carried over from an
        # earlier round is not in this round's res_by_alpha, and losing its sharpe/fitness/mechanic
        # here would send it to submit() with no mechanic to dedupe on.
        misses = 0
        d = res_by_alpha.get(aid) or (pending.get(aid) or {}).get("row") or {}
        pending.pop(aid, None)
        # `sc is None` is NOT a pass, whatever the old expression said -- and the comment eight
        # lines up already said so ("not measured is never clean") while the code disagreed.
        # self_maxcorr() returns None even with records present when the payload carries no
        # `correlation` column or every value is null, which is the same hole that was closed in
        # submit_alphas._fresh_corr_ok. It has never fired here (all 42 None-self alphas in the
        # store were already rejected on prod), but a false corr_ok writes submittable=yes into
        # winners.csv and that ledger is what future tap-submits are picked from.
        ok = pc <= 0.7 and sc is not None and sc < 0.7
        store[aid] = {"prod_maxcorr": pc, "prod_breach_count": breach, "self_maxcorr": sc,
                      "self_measured": True, "corr_ok": ok}
        tmp = PC.with_suffix(".tmp")           # atomic: a crash mid-write must not truncate the store
        with open(tmp, "w") as f:
            json.dump(store, f, indent=1)
        tmp.replace(PC)
        measured.append((aid, d))
        log(f"  {aid:10} prod={pc} self={sc} sh={d.get('sharpe')} fit={d.get('fitness')}"
            f"{' *** CLEAN' if ok else ''}")
        if ok:
            clean.append((pc, aid, d))
    tmp = PEND.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(pending, f)
    tmp.replace(PEND)
    return clean, store, measured


HDR = ["date", "iter", "alpha", "dataset", "category", "sharpe", "fitness", "turnover",
       "warnings", "prod_max", "breach", "self_corr", "submittable", "status", "neut", "decay",
       "formula"]


def ledger_write(aid, d, pc, sc, breach, ok, tag, dataset=None):
    # Learning the header from the first DATA row silently dropped every winner whenever the file
    # was empty or header-only. The standing rule is that every winner MUST reach the ledger, so
    # the header is declared here and the file is created if missing.
    if not WIN.exists() or not WIN.read_text().strip():
        with open(WIN, "w", newline="") as f:
            csv.writer(f).writerow(HDR)
    hdr = HDR
    def _ids(path):
        try:
            return {r["alpha"] for r in csv.DictReader(open(path))}
        except Exception:
            return set()
    in_win, in_near = _ids(WIN), _ids(NEAR)
    # Dedupe per DESTINATION, not across both. Checking the union meant an alpha first written to
    # near_misses (prod-walled at the time) could never be promoted once it measured clean: five
    # clean gems were missing from winners.csv for exactly this reason, and the standing rule is
    # that every winner reaches that file. A near-miss becoming a winner is a real transition --
    # correlations move as the book changes -- so only a duplicate of the SAME verdict is skipped.
    if (ok and aid in in_win) or ((not ok) and aid in in_near):
        return
    # `dataset` is the G6 per-family/day throttle key (submit_alphas._family_of reads this column).
    # Writing a truncated old_id here made the key meaningless: seven gems that were ALL model27
    # split into families `..._decorr_02/05/06/08`, so the throttle fired on unrelated alphas and
    # let same-dataset ones through. It must be the real dataset.
    row = {"date": str(datetime.date.today()), "iter": tag, "alpha": aid,
           "dataset": dataset or str(d.get("old_id", ""))[:24], "category": tag,
           "sharpe": d.get("sharpe"), "fitness": d.get("fitness"), "turnover": d.get("turnover"),
           "warnings": "", "prod_max": pc, "breach": breach, "self_corr": sc,
           "submittable": "yes" if ok else "no", "status": "RESERVE" if ok else "prod-walled",
           "neut": "", "decay": "", "formula": str(d.get("old_id", ""))}
    with open(WIN if ok else NEAR, "a", newline="") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        csv.writer(f).writerow([row.get(k, "") for k in hdr])
        fcntl.flock(f, fcntl.LOCK_UN)


def budget_used():
    today = DB.platform_date()          # the platform's day is US EASTERN, not UTC -- see there
    n = 0
    try:
        for l in open(ST / "submit_budget.jsonl"):
            if l.strip() and json.loads(l).get("date") == today:
                n += 1
    except Exception:
        pass
    return n


def submit(clean):
    """Submit cheapest-correlation first, ONE per distinct formula.

    Near-duplicates are worse than useless: iter49 produced three alphas that differed only in an
    inert truncation setting, all three were submitted, and all three burned their single lifetime
    POST (rule G6) on the same rejection. One representative per formula, and the rest are banked."""
    done, seen_formula = [], set()
    for pc, aid, d in sorted(clean):
        if budget_used() >= DAILY_CAP:
            log(f"  daily cap reached -- {aid} banked")
            break
        # Key on the FORMULA TEXT. Keying on the old_id minus its trailing index kept the settings
        # tokens (`..._d6_t2_000` -> `..._d6_t2`), so three alphas differing only in an inert
        # truncation still counted as three families -- exactly the case this guard exists to stop.
        # Journal rows carry no `formula` (verified: the key is absent from every row), so
        # one_round injects it from the batch file; the fallback strips a purely-numeric tail so a
        # missing formula still collapses `..._061/062/063` into one family rather than three.
        # Dedupe on MECHANIC, not formula. Submitting one alpha kills its whole signal family --
        # five banked gems went from prod 0.60-0.69 to 0.73-1.00 the moment their siblings went
        # live -- so two different formulas from one mechanic are worth one submission, not two.
        # Formula-level dedupe let a round spend every slot inside a single family.
        key = d.get("mechanic") or d.get("formula")
        if not key:
            parts = (d.get("old_id") or aid).rsplit("_", 1)
            key = parts[0] if len(parts) == 2 and parts[1].isdigit() else (d.get("old_id") or aid)
        if key in seen_formula:
            log(f"  {aid} skipped: same mechanic as one already submitted this round")
            continue
        seen_formula.add(key)
        log(f">>> submitting {aid} (prod {pc}, sh {d.get('sharpe')}, fit {d.get('fitness')})")
        r = subprocess.run([sys.executable, str(ROOT / "tools/submit_alphas.py"), aid],
                           capture_output=True, text=True)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        log("    " + out[:300].replace("\n", " | "))
        # NOT `"SUBMITTED" in out`: the platform's rejection body contains the check name
        # ALREADY_SUBMITTED, which contains the substring, so a 403 scored as a win and was
        # counted in the round report and in the knowledge weights.
        if "SUBMITTED ✓" in out and "REJECTED" not in out:
            done.append(aid)
    return done


# --------------------------------------------------------------------------- round
def one_round(rnd, pool, used, knowledge, size, args, launch):
    # The launch token makes tags unique per process. Without it a watchdog restart replays
    # ALr01..., collides with guard G5 (old_id prefixes must be unique against the resim journal),
    # and re-sims already-spent work.
    tag = f"{args.tag}{launch}r{rnd:02d}"
    # Drop candidates aimed at cells that are already FULL. pick_slice ranks by measured yield, so
    # it keeps drawing the historically best cell long after 3 alphas have closed it -- and a 4th
    # alpha in a closed cell is worth nothing (the whole point of pyramid targeting). Earnings,
    # Fundamental and Institutions hold 68% of the current BOOST weight and all three close on
    # 2026-08-02's submits, so without this the next full day of a 5000-sim cap mines dead cells.
    dead = _dead_cells()
    # A row is dead only when EVERY cell it can fill is full. Testing `category_target` alone was
    # right while each alpha targeted one cell, but a paircell row carries `category_pair` too:
    # a Macro+News row whose Macro side closed still fills News, and dropping it would throw away
    # a live candidate. Conversely a row whose only cell is full is worth nothing.
    def _targets(c):
        m = c.get("meta") or {}
        return {m.get("category_target"), m.get("category_pair")} - {None}

    live = [c for c in pool if _targets(c) - dead]
    if dead:
        log(f"R{rnd}: cells full {sorted(dead)} -- {len(pool)-len(live)} rows dropped from the draw")
    cand = pick_slice(live or pool, used, size, knowledge)
    if not cand:
        log("pool exhausted")
        return None
    for c in cand:
        c["old_id"] = c["id"] = f"{tag}_{c['old_id']}"
        used.add(c["old_id"])
    bp = AL / f"{tag}_targets.json"
    json.dump(cand, open(bp, "w"), indent=1)

    pf = subprocess.run([sys.executable, str(ROOT / "tools/autoloop/preflight.py"), str(bp)],
                        capture_output=True, text=True)
    log(f"R{rnd}: {len(cand)} candidates -- preflight: "
        f"{((pf.stdout or '').strip().splitlines() or ['(no output)'])[-1]}")
    if pf.returncode != 0:
        # A refused batch never ran, so it must go BACK to the pool. Without this one colliding
        # row costs the whole slice: PD rounds 1-6 on 2026-08-02 burned 2,323 candidates and
        # journalled ZERO, destroying the entire paircell pool without simulating any of it.
        for c in cand:
            used.discard(c["old_id"])
            c["old_id"] = c["id"] = c["old_id"].split("_", 1)[1]
        bp.unlink(missing_ok=True)
        log(f"R{rnd}: preflight refused -- returned all {len(cand)} candidates to the pool")
        # The return code was previously ignored and the batch was simulated anyway -- the exact
        # hole preflight exists to plug. An aborted round costs one round; a bad batch costs POSTs.
        return {"round": rnd, "n": len(cand), "scored": 0, "zero_fail": 0, "measured": 0,
                "clean": 0, "submitted": [], "med_sharpe": 0.0, "med_fitness": 0.0,
                "med_ladder": None, "ladder_pass": 0, "ladder_n": 0, "med_returns": 0.0,
                "med_drawdown": 0.0, "top_blockers": [], "best_axis": {},
                "note": "preflight abort: " + (pf.stdout or "")[-300:]}

    run_sim(bp)
    oids = {c["old_id"] for c in cand}
    res = harvest(tag + "_", oids)
    # The platform keeps finishing simulations AFTER run_multisim's stall timeout fires. On
    # 2026-07-30 round 1 logged "journaled 0/239" and gave up, yet 50 rows landed in the journal
    # minutes later -- scored as nothing, and the knowledge file learned that every axis in them
    # was worthless. Harvesting once, immediately, throws away work that is already paid for.
    # Keep re-reading while the count is still climbing.
    if len(res) < len(oids):
        stalls = 0
        for _ in range(24):                      # up to ~6 min of grace
            time.sleep(15)
            again = harvest(tag + "_", oids)
            if len(again) > len(res):
                res, stalls = again, 0
            else:
                stalls += 1
                if stalls >= 3:                  # 45s with no new row = genuinely done
                    break
            if len(res) >= len(oids):
                break
    log(f"R{rnd}: journaled {len(res)}/{len(cand)}")
    # A candidate is spent when the PLATFORM ran it, not when we dispatched it. `used.add` happens
    # before the POST, so a round the platform refuses -- daily cap, 401 mid-flight -- burned its
    # slice forever: rounds 10 and 12 on 2026-08-02 marked 338 rows spent while creating zero
    # alphas (last alpha created 17:40 ET, R10 launched at 17:45). Give the unsimulated ones back,
    # with their original untagged ids, so the next round can pick them up.
    unrun = [c for c in cand if c["old_id"] not in res]
    for c in unrun:
        used.discard(c["old_id"])
        c["old_id"] = c["id"] = c["old_id"].split("_", 1)[1]
    if unrun:
        log(f"R{rnd}: returned {len(unrun)} unsimulated candidates to the pool")
        # The targets FILE has to shrink with them. preflight's duplicate check scans every
        # state/**/*targets*.json on the assumption that "a batch staged under a second name has
        # already been run" -- which is exactly what releasing breaks. Leaving the full file on
        # disk made the released rows permanently unstageable: rounds 1 and 2 of the SY run both
        # aborted with 158/210 and 219/219 duplicates against SX rounds 10 and 12, the two rounds
        # that had created nothing at all. Rewrite the file to what actually ran, or drop it.
        try:
            ran = [c for c in cand if c["old_id"] in res]
            if ran:
                json.dump(ran, open(bp, "w"), indent=1)
            else:
                bp.unlink(missing_ok=True)
            # state/resim_targets.json is the run_multisim working copy and it is scanned by
            # validate_targets too. It self-heals on the next successful dispatch, but until then
            # it blocks the rows this round just released -- that is the second failure that
            # aborted SY round 1. Clear it when it still holds THIS batch.
            # state/resim_targets.json is run_multisim's working COPY of the batch and the
            # duplicate check scans it too, so it must shrink with the release -- pruning only the
            # round's own file was not enough. SZ round 1 journalled 197 of 216, released 19, and
            # every one of those 19 stayed listed here; round 2 drew them back, preflight called
            # them duplicates, and the whole 216-row round was refused.
            rt = ST / "resim_targets.json"
            if rt.exists():
                try:
                    held = json.load(open(rt))
                    ran_ids = {c["old_id"] for c in cand if c["old_id"] in res}
                    mine = {f"{tag}_{c['old_id']}" for c in unrun} | ran_ids
                    kept = [r for r in held
                            if not isinstance(r, dict) or r.get("old_id") not in mine
                            or r.get("old_id") in ran_ids]
                    if len(kept) != len(held):
                        json.dump(kept, open(rt, "w"))
                        log(f"R{rnd}: pruned resim_targets.json {len(held)} -> {len(kept)}")
                except Exception:
                    pass
        except Exception as e:
            log(f"R{rnd}: could not prune the targets file ({str(e)[:60]})")
    if not res:
        # Every key the caller reads must be present: main() logged rep['med_fitness'] OUTSIDE the
        # try/except, so a round that journalled nothing -- the commonest failure -- raised a
        # KeyError and killed the whole 4-hour run.
        return {"round": rnd, "n": len(cand), "scored": 0, "zero_fail": 0, "measured": 0,
                "clean": 0, "submitted": [], "med_sharpe": 0.0, "med_fitness": 0.0,
                "med_ladder": None, "ladder_pass": 0, "ladder_n": 0, "med_returns": 0.0,
                "med_drawdown": 0.0, "top_blockers": [], "best_axis": {},
                "note": "no rows journaled"}

    meta_by_oid = {c["old_id"]: c.get("meta", {}) for c in cand}
    formula_by_oid = {c["old_id"]: c.get("formula") for c in cand}
    rows, passers, res_by_alpha = [], [], {}
    for oid, d in res.items():
        d["formula"] = formula_by_oid.get(oid)      # journal rows carry no formula; submit() needs it
        d["mechanic"] = (meta_by_oid.get(oid) or {}).get("dataset")   # submit() dedupes on this
        p, failed, missing = gates.zero_fail(d)
        lad = next((c.get("value") for c in (d.get("checks") or [])
                    if isinstance(c, dict) and c.get("name") == "IS_LADDER_SHARPE"), None)
        rows.append({"meta": meta_by_oid.get(oid, {}), "_pass": p, "_alpha": d.get("alpha"),
                     "_fitness": d.get("fitness"), "_sharpe": d.get("sharpe"), "_ladder": lad,
                     "_returns": d.get("returns"), "_drawdown": d.get("drawdown"),
                     "_failed": failed + missing})
        if d.get("alpha"):
            res_by_alpha[d["alpha"]] = d
        if p and d.get("alpha"):
            passers.append(d["alpha"])

    blockers = Counter_(r["_failed"] for r in rows)
    log(f"R{rnd}: zero-fail {len(passers)}/{len(res)} | top blockers {blockers[:5]}")

    # Always call measure, even with no passer this round: the parked queue from earlier rounds
    # still has to be drained, and gating on `passers` would strand it forever.
    clean, store, measured = measure(passers, res_by_alpha)
    # Ledger EVERY alpha measured in this call, not just this round's passers -- an alpha parked
    # two rounds ago and resolved now is exactly the winner the standing rule says must be logged.
    for aid, row in measured:
        m = store.get(aid)
        if m:
            ledger_write(aid, row, m["prod_maxcorr"], m["self_maxcorr"],
                         m["prod_breach_count"], m["corr_ok"], tag,
                         dataset=(meta_by_oid.get(row.get("old_id")) or {}).get("dataset"))
    if args.no_submit and clean:
        log(f"--no-submit: {len(clean)} clean alpha(s) banked, quota left to the planned batch")
    submitted = submit(clean) if clean and not args.no_submit else []

    fresh = score_axes(rows, store)
    merge_knowledge(knowledge, fresh, rnd)
    json.dump(knowledge, open(KNOW, "w"), indent=1)

    fits = [r["_fitness"] or 0 for r in rows]
    lads = [r["_ladder"] for r in rows if isinstance(r["_ladder"], (int, float))]
    rep = {"round": rnd, "tag": tag, "n": len(cand), "scored": len(res),
           "zero_fail": len(passers), "measured": len(store), "clean": len(clean),
           "submitted": submitted,
           "med_sharpe": round(statistics.median([r["_sharpe"] or 0 for r in rows]), 3),
           "med_fitness": round(statistics.median(fits), 3),
           # the binding gate: track it explicitly so a round that improves nothing else but moves
           # the ladder distribution up is still visible as progress
           "med_ladder": round(statistics.median(lads), 3) if lads else None,
           "ladder_pass": sum(1 for x in lads if x > 1.58),
           "ladder_n": len(lads),
           "med_returns": round(statistics.median([r["_returns"] or 0 for r in rows]), 4),
           "med_drawdown": round(statistics.median([r["_drawdown"] or 0 for r in rows]), 4),
           "top_blockers": blockers[:8],
           "best_axis": {a: sorted(knowledge["scores"].get(a, {}).items(),
                                   key=lambda kv: -kv[1])[:3] for a in AXES},
           "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rep) + "\n")
    return rep


def Counter_(lists):
    c = defaultdict(int)
    for l in lists:
        for x in l:
            c[x] += 1
    return sorted(c.items(), key=lambda kv: -kv[1])


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--hours", type=float, default=4.0)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--tag", default="AL")
    ap.add_argument("--no-submit", action="store_true",
                    help="find and bank, never POST. Use when the day's 4 submit slots are already "
                         "committed to a verified set: the driver submits its OWN round's finds, "
                         "so a relaunch racing a planned batch can spend the quota on unverified "
                         "alphas and cost the cells the batch was chosen to unlock.")
    ap.add_argument("--min-size", type=int, default=60)
    ap.add_argument("--max-size", type=int, default=400)
    args = ap.parse_args()

    AL.mkdir(parents=True, exist_ok=True)
    pool = json.load(open(args.pool))
    knowledge = load_knowledge()
    launch = f"{int(time.time()) % 100000:05d}"
    # Survive a restart: candidates already spent in an earlier launch must not be re-picked.
    used = set()
    spent = AL / "spent_ids.json"
    if spent.exists():
        try:
            # one_round rewrites each candidate's old_id to "<tag><round>_<original>", and that
            # tagged form is what lands in spent_ids. The pool on disk still holds the ORIGINAL
            # ids, so comparing the two forms never matched across a restart and the driver
            # re-picked candidates it had already simulated -- every round then aborted on
            # duplicates. Store both forms so the match works either way.
            raw = set(json.load(open(spent)))
            used = raw | {x.split("_", 1)[1] for x in raw if "_" in x}
        except Exception:
            pass
    # The JOURNAL is the other authority on what is spent, and it is the one that survives the
    # release path above: a round that journals 170/179 releases the 9 stragglers, and any of them
    # whose rows land after the 6-minute grace loop would otherwise be re-simulated -- paying twice
    # out of a hard 5000/day cap. A row in the journal is done, whatever spent_ids says.
    pool_ids = {c["old_id"] for c in pool}
    try:
        for line in open(ST / "resim_results.jsonl", errors="ignore"):
            if '"checks"' not in line:
                continue
            try:
                o = json.loads(line).get("old_id") or ""
            except Exception:
                continue
            base = o.split("_", 1)[1] if "_" in o else o
            if base in pool_ids:
                used.add(base)
    except Exception:
        pass
    # SWEEP THE WRECKAGE OF PREVIOUS RUNS. A killed or aborted round leaves its `*_targets.json`
    # behind, preflight's duplicate check reads every such file as history, and the next round's
    # draw therefore collides with work that never happened -- which aborts that round, which
    # leaves ANOTHER file. On 2026-08-05 that spiral cost the last hour of a four-hour window:
    # QD, QE, QF, KP and QG each ran to "total simmed 0", every one blocked by its predecessor's
    # corpse. A staged file whose rows are ALL absent from the journal represents zero simulated
    # work and must not be allowed to veto anything.
    try:
        journaled = set()
        with open(ROOT / "state/resim_results.jsonl") as fh:
            for line in fh:
                i = line.find('"old_id"')
                if i < 0:
                    continue
                j = line.find('"', i + 10)
                k = line.find('"', j + 1)
                if k > j:
                    journaled.add(line[j + 1:k])
        swept = 0
        for p in (ROOT / "state/autoloop").glob("*_targets.json"):
            try:
                rows = json.load(open(p))
            except Exception:
                continue
            if not isinstance(rows, list) or not rows:
                continue
            if any(isinstance(r, dict) and r.get("old_id") in journaled for r in rows):
                continue                      # some of it really ran -- it is genuine history
            p.unlink()
            swept += 1
        # The SHARED working file too. run_multisim copies each launch into state/resim_targets.json,
        # so a killed round leaves its rows there as well -- and preflight reads that file as history
        # exactly like the per-round ones. Sweeping only the per-round files fixed half the problem:
        # on 2026-08-06 the very next launch still aborted, this time colliding with 400 rows of a
        # round that had journalled nothing. Rows that DID run stay; they are real history.
        live = ROOT / "state/resim_targets.json"
        try:
            rows = json.load(open(live))
            if isinstance(rows, list) and rows:
                keep = [r for r in rows if isinstance(r, dict) and r.get("old_id") in journaled]
                if len(keep) != len(rows):
                    json.dump(keep, open(live, "w"))
                    log(f"swept {len(rows) - len(keep)} never-simulated row(s) out of "
                        f"resim_targets.json (kept {len(keep)} that really ran)")
        except Exception:
            pass
        if swept:
            log(f"swept {swept} stranded targets file(s) from aborted runs -- they blocked "
                f"preflight with work that never happened")
    except Exception as e:
        log(f"targets sweep skipped ({str(e)[:60]})")

    deadline = time.time() + args.hours * 3600
    log(f"START: pool={len(pool)} rounds={args.rounds} deadline={args.hours}h "
        f"launch={launch} already-spent={len(used)}")

    reports = []
    # A round is consumed by SIMULATING, never by failing to authenticate. As a `for` loop over
    # range(rounds), the `continue` below advanced the counter every time ensure_auth() gave up,
    # so a dead cookie ate the whole budget without a single simulation: on 2026-08-03 the session
    # expired at 15:53 and rounds 2-12 were each spent on a 30-minute auth wait, leaving 319 of
    # 4,326 available sims used. The deadline check still bounds the loop, so a session that never
    # comes back exits on time rather than spinning.
    rnd, stalled = 0, 0
    while rnd < args.rounds:
        left = deadline - time.time()
        if left <= 0:
            log(f"DEADLINE reached after {rnd} rounds ({stalled} auth stalls)")
            break
        rnd += 1
        # Size the round to the time left rather than to a fixed count: throughput is measured at
        # ~8.5 sims/min, so a fixed slice would either overrun the deadline or leave it unused.
        rounds_left = args.rounds - rnd + 1
        size = int(max(args.min_size, min(args.max_size, (left / rounds_left) / 60 * 8.0)))
        # Count what is left IN THIS POOL, not the size of the global spent set: `used` carries
        # ids from every pool this session has run, and storing both the tagged and untagged form
        # of each doubled it. On a 2055-row pool with 2118 spent ids the old expression went to
        # -63 and the driver declared "pool exhausted" before simulating a single row.
        remaining = sum(1 for c in pool if c["old_id"] not in used)
        size = min(size, remaining)
        if size <= 0:
            log("pool exhausted")
            break
        # The platform caps simulations per EASTERN day. Dispatching past it does not queue, it is
        # refused with a 429 that looks exactly like the concurrency 429, so on 2026-08-02 the
        # driver spent 4h45m retrying rounds that could never run. Ask before dispatching.
        try:
            bud = DB.budget()
            if bud["remaining"] is not None and bud["remaining"] <= 0:
                nap = bud["seconds_to_reset"] + 60
                if nap > left:
                    log(f"DAILY LIMIT: {bud['used']}/{bud['cap']} used, resets in "
                        f"{nap/3600:.1f}h -- past the deadline, stopping")
                    break
                log(f"DAILY LIMIT: {bud['used']}/{bud['cap']} used -- sleeping "
                    f"{nap/60:.0f}min to the reset")
                time.sleep(nap)
                continue
            if bud["remaining"] is not None:
                size = min(size, bud["remaining"])
        except Exception as e:
            log(f"daily-budget check failed ({str(e)[:60]}) -- proceeding")
        log(f"--- ROUND {rnd}/{args.rounds}  size={size}  {left/3600:.2f}h left ---")
        if not ensure_auth():
            rnd -= 1                       # an auth stall is not a round; give the slot back
            stalled += 1
            log(f"cannot authenticate -- round not consumed ({stalled} stalls so far)")
            continue
        try:
            rep = one_round(rnd, pool, used, knowledge, size, args, launch)
            json.dump(sorted(used), open(spent, "w"))   # tagged + original, see load
        except Exception:
            # A crash in one round must not end the run: the whole point of this driver is that it
            # keeps going for the full window without a human restarting it.
            log("ROUND FAILED:\n" + traceback.format_exc()[-900:])
            continue
        if rep is None:
            break
        reports.append(rep)
        # .get() everywhere: reporting must never be the thing that kills the run.
        log(f"R{rnd} DONE: zero-fail {rep.get('zero_fail')}/{rep.get('scored')} "
            f"clean {rep.get('clean')} submitted {rep.get('submitted')} "
            f"medFit {rep.get('med_fitness')} medLadder {rep.get('med_ladder')} "
            f"ladderPass {rep.get('ladder_pass')}/{rep.get('ladder_n')}"
            + (f"  [{rep['note']}]" if rep.get("note") else ""))

    log("=== FINAL ===")
    for r in reports:
        log(f"  R{r.get('round'):2}  n={r.get('scored'):4}  zf={r.get('zero_fail'):3}  "
            f"clean={r.get('clean'):2}  medSh={r.get('med_sharpe')}  medFit={r.get('med_fitness')}  "
            f"lad={r.get('med_ladder')} ladPass={r.get('ladder_pass')}/{r.get('ladder_n')}  "
            f"sub={r.get('submitted')}")
    json.dump(reports, open(AL / "final_report.json", "w"), indent=1)
    log(f"total simmed {sum(r['scored'] for r in reports)} | "
        f"zero-fail {sum(r['zero_fail'] for r in reports)} | "
        f"clean {sum(r['clean'] for r in reports)} | "
        f"submitted {sum(len(r['submitted']) for r in reports)}")


if __name__ == "__main__":
    main()
