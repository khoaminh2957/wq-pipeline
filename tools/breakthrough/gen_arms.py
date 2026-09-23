#!/usr/bin/env python3
"""Six arms, each breaking exactly ONE constant that every prod-walled alpha shared.

Written for ITERATIONS.md I3/I4. The 19 alphas measured on 2026-08-06 sat at prod 0.7126-0.8999
with not one below the 0.70 gate, and NO structural feature separated them (I2a: the strongest
|pearson| across operator counts and field semantics was 0.31 at N=19, and the feature the story
leaned on pointed the wrong way). They could not be told apart because they shared, with zero
variation, the carrier / the add() skeleton / TOP3000 / the eligible field set. A variable that
never varies cannot be shown to cause anything by slicing the sample it never varies in.

So each arm changes ONE of those and nothing else:

    A0  control        the current recipe
    A1  speed          decay 16/20/26 -- a range no row of the 19 sampled
    A2  skeleton       trade_when regime gating instead of add()
    A3  universe       TOP1000
    A4  carrier        no Price Volume carrier, non-additive
    A5  field set      coverage 0.20-0.90 -- the ~900 event-type fields the >=0.90 filter deleted

Two rules the old generator broke, applied here to every arm so they are constants, not confounds:

1. DATASET STRATIFICATION. `gen_pyramid` sorts by userCount and draws from the least-crowded half,
   which handed 100% of Social Media legs to one dataset and 92% of Insiders to another. A cell
   unlocks at 3 INDEPENDENT alphas and submitting one raises its siblings' self-corr toward 1, so a
   single-dataset pool has a ceiling of one submittable however many rows it holds. Legs are drawn
   round-robin across datasets with a per-dataset cap.

2. NO COVERAGE CLIFF. `coverage >= 0.90` deleted whole datasets -- 315 fields of Transformer Based
   News Sentiment, 260 of Macro Economic Event Data, 129 of MnA Deals, 102 of Finance Creator
   Prediction. Sparseness is what an EVENT dataset looks like; the filter cannot distinguish that
   from a broken field. A0-A4 keep >=0.90 so they stay comparable to the 19; A5 exists to look at
   what was thrown away.
"""
import argparse, collections, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# Which cells to mine is a per-(region,delay) question, not a constant. USA d1 has ten cells
# already unlocked and six hard ones left; every other pair has ALL of its cells open, including
# Price Volume. That matters directly: an alpha built on the standard carrier is
# {Price Volume + one dataset}, so in USA d1 the carrier half is wasted against a cell sitting at
# 37/3, while in a virgin pair the same alpha credits TWO open cells with one irreversible submit.
SHORT_CELLS = ["News", "Sentiment", "Social Media", "Short Interest", "Insiders"]
RAW_OHLC = {"open", "close", "high", "low", "vwap", "volume", "returns", "adv20", "cap"}
BAD_ID = re.compile(r"(_id|_name|_date|_currency|_ticker|_cusip|_isin|_sedol)$", re.I)

# A field is excluded on what its DESCRIPTION says it measures, not on what its id looks like.
# `mws46_storyid_g_ens` reads like an identifier and is a novelty SCORE; `mws42_time` reads fine
# and is a clock reading in HHMMSS. rank() of a calendar date or a lookup code is not a signal, it
# is a number that happens to sort -- exactly the kind of leg the meaning gate exists to stop.
#
# SUBJ anchors at the start so the date/time word has to be what the field IS. An earlier version
# matched anywhere in the first 48 characters and deleted `end_of_day_high_price`
# ("Highest price reached from time of news to session end"), which is a price move that merely
# mentions a time. DATEY then catches date fields that describe themselves mid-sentence
# ("The most recent earnings announcement date ..."), which SUBJ alone misses.
BAD_SUBJ = re.compile(r"^\s*(the\s+)?(utc\s+|publication\s+|expiration\s+|arrival\s+|report\s+)?"
                      r"(date|time|timestamp|datetime|day)\b", re.I)
BAD_DATEY = re.compile(r"\b(announcement|expected|effective|filing|expiration|maturity|payment|"
                       r"record|ex[- ]dividend|start|end)\s+date\b|\bdate\s+(from|of the|for the)\b", re.I)
BAD_DESC = re.compile(r"((topic|category|sector|country|currency|exchange)\s*code|code\s*\(integer\)|"
                      r"must decode|index\s*\(into|\bindex into\b|\bidentifier\b|\bticker\b|"
                      r"\bISIN\b|\bCUSIP\b|\bSEDOL\b|company name)", re.I)


def meaningless(desc):
    """True when ranking this field would order rows by a clock, a calendar or a lookup table."""
    return bool(BAD_SUBJ.search(desc) or BAD_DATEY.search(desc) or BAD_DESC.search(desc))

CARRIER = ["-rank(divide(close, open))", "multiply(-rank(divide(close, vwap)), 0.6)"]

SETTINGS_BASE = {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
                 "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
                 "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
                 "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31",
                 "decay": 6, "neutralization": "INDUSTRY", "truncation": 0.02}

# STATISTICAL 24.1% prod-clean (n=294) vs INDUSTRY 4.3% (n=351) vs SUBINDUSTRY 5.9% (n=136),
# and 26.2% vs 0.0% on the joint objective at W=20. NOT pool-controlled -- only one pool ever
# ran two neutralizations at n>=8 and it had no power (0/9 vs 0/9). So STATISTICAL is weighted
# 4:1:1 rather than used alone: the batch exploits the measured effect AND randomises the
# contrast within one pool, which finally controls it.
NEUTS = ["STATISTICAL", "STATISTICAL", "STATISTICAL", "STATISTICAL",
         "INDUSTRY", "SUBINDUSTRY"]
# 0.01 -> 2.2% prod-clean (n=45) and 0.08 -> 0.0% (n=19) both collapse; 0.015/0.02/0.05
# all sit at 12.6-13.6% (n=175/295/198).
TRUNCS = [0.015, 0.02, 0.05]
DELTA_W = [5, 10, 20, 60]
# WINDOW, chosen on the JOINT objective (zero-fail AND prod<0.70), not on zero-fail alone.
# The two pull opposite ways and I optimised the wrong one for three hours:
#
#   zero-fail (within-pool)   W=10  3.24%   W=20  1.23%   W=50  0.08%
#   prod-clean                W=10  9.6%    W=20 12.4%    W=50 15.5%
#   JOINT under STATISTICAL   W=10 11.4%    W=20 26.2%    W=32 42.9%   W=50 38.1%
#
# A zero-fail alpha that cannot pass production correlation is not a gem, so the joint event is
# the only thing worth counting. W=10 is dropped; W=50 is kept as one draw rather than a third.
WINDOWS = [16, 20, 20, 32, 32, 50]
POWERS = [1.0, 1.5, 2.0]

# Per-arm overrides. Only the listed key differs from A0.
REGION, DELAY, UNIVERSE = "USA", 1, ""

ARMS = {
    "A0": {"decays": [6, 10, 14], "universe": "TOP3000", "skeleton": "add",    "carrier": True,  "cov": (0.90, 1.01)},
    "A1": {"decays": [16, 20, 26], "universe": "TOP3000", "skeleton": "add",  "carrier": True,  "cov": (0.90, 1.01)},
    "A2": {"decays": [4, 6, 10], "universe": "TOP3000", "skeleton": "gate",   "carrier": True,  "cov": (0.90, 1.01)},
    "A3": {"decays": [4, 6, 10], "universe": "TOP1000", "skeleton": "add",    "carrier": True,  "cov": (0.90, 1.01)},
    "A4": {"decays": [4, 6, 10], "universe": "TOP3000", "skeleton": "gate",   "carrier": False, "cov": (0.90, 1.01)},
    "A5": {"decays": [4, 6, 10], "universe": "TOP3000", "skeleton": "add",    "carrier": True,  "cov": (0.20, 0.90)},
    # A6/A7 complete a 2x2 that the first factorial left confounded. Simulation ERRORs tracked
    # carrier presence (20% with, 5% without, z=+4.54 within the gate skeleton) -- but in that
    # same comparison the carrier arm also ran 12 operators to the carrier-free arm's 7, so
    # "has a carrier" and "is longer" were the identical contrast and neither was established.
    #   A6 = NO carrier, LONG   A7 = carrier, SHORT
    # Errors follow the carrier -> A6 low, A7 high.  Errors follow length -> A6 high, A7 low.
    "A6": {"decays": [4, 6, 10], "universe": "TOP3000", "skeleton": "add", "carrier": False,
           "cov": (0.90, 1.01), "legs": (6, 8)},
    # A7 is retained only as the error-rate control it was built to be. On PROD it is the worst
# structure measured: a single dataset leg leaves the bare carrier, 0/27 prod-clean at a
# median prod of 0.957. It must never be scaled up as a production recipe.
    "A7": {"decays": [4, 6, 10], "universe": "TOP3000", "skeleton": "add", "carrier": True,
           "cov": (0.90, 1.01), "legs": (1, 1)},
}


def dsname(v):
    return (v.get("name") or v.get("id")) if isinstance(v, dict) else (v or "?")


def load_fields(cov_lo, cov_hi, region="USA", delay=1, cells=None):
    """cell -> {dataset -> [(userCount, id, type)]}, honest about which datasets exist.

    Banned fields are dropped: a field used by any submitted alpha would raise the new alpha's
    self-correlation against our own live book, which is a different gate from prod but just as
    fatal."""
    d = json.load(open(ROOT / "state/banned_fields.json"))
    banned = set(d.get("banned_fields") or [])
    for v in (d.get("by_alpha") or {}).values():
        banned |= set(v)
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for line in open(ROOT / "fetched/fields_all.jsonl"):
        try:
            f = json.loads(line)
        except Exception:
            continue
        if f.get("region") != region or f.get("_delay") != delay:
            continue
        c = f.get("category")
        cn = c.get("name") if isinstance(c, dict) else c
        if cells and cn not in cells:
            continue
        fid, desc = f.get("id"), f.get("description") or ""
        if not fid or fid in banned or fid in RAW_OHLC:
            continue
        if BAD_ID.search(fid) or meaningless(desc):
            continue
        # A GROUP field is a classification map (sector/industry membership). It is legal ONLY as
        # the `group` argument of a group_* operator, never as a signal -- ranking a sector code
        # orders rows by an arbitrary label. logic_check enforces this and blocked 79 USA d0 rows
        # before a single POST was made; filtering here means the batch is not built wrong in the
        # first place rather than caught at the door.
        if (f.get("type") or "").upper() == "GROUP":
            continue
        cov = f.get("coverage")
        if not isinstance(cov, (int, float)) or not (cov_lo <= cov < cov_hi):
            continue
        out[cn][dsname(f.get("dataset"))].append((f.get("userCount") or 0, fid, f.get("type")))
    for cn in out:
        for ds in out[cn]:
            out[cn][ds].sort()
    return out


_EMP = None


def empirical_scores():
    """field -> zero-fail lift, measured within-pool across the whole simulation journal.

    Selecting on userCount asks "who else trades this"; it never asks "did this field ever help".
    The journal answers the second question directly, and the two disagree sharply: in USA d1 News
    the twelve worst fields by zero-fail lift are all price quantities filed under a News label
    (spy_etf_closing_price_2, vwap_after_session, session_price_range_amt ...) with a zero-fail
    rate of exactly 0.000 across n=15-27 each, while the Ravenpack news-analytics fields carry
    lifts of +0.21 to +0.28. Crowding cannot see that distinction; the journal can.

    Cached: the scan reads ~57k journal rows and every targets file on disk."""
    global _EMP
    if _EMP is None:
        sys.path.insert(0, str(ROOT / "tools"))
        import field_eda
        _EMP = field_eda.load_empirical()
    return _EMP


def pick_stratified(rng, by_ds, k, max_per_ds, emp=None, min_n=15):
    """k legs spread round-robin across datasets, at most max_per_ds from any one.

    This is the I1b fix. Drawing from a globally crowding-sorted list concentrates on whichever
    dataset owns the most zero-userCount fields; a cell needs three INDEPENDENT alphas, so the
    number of distinct datasets in the pool bounds what the pool can ever yield."""
    order = [d for d in by_ds if by_ds[d]]
    if not order:
        return []
    rng.shuffle(order)
    picked, used = [], collections.Counter()
    cursor = {d: 0 for d in order}
    while len(picked) < k:
        progressed = False
        for d in order:
            if len(picked) >= k or used[d] >= max_per_ds:
                continue
            pool = by_ds[d]
            # Order WITHIN the dataset by measured zero-fail lift where the journal has enough
            # rows to speak (n>=min_n), and fall back to crowding order for everything it has
            # never simulated. A field the journal has seen drag is pushed behind every unmeasured
            # one rather than dropped outright -- absence of evidence is not evidence of harm, but
            # measured harm should not outrank an open question.
            if emp:
                def _rank(item):
                    e = emp.get(item[1])
                    if e and e["n"] >= min_n:
                        return (0, -e["zf_lift"])
                    return (1, item[0])          # unmeasured: keep crowding order
                pool = sorted(pool, key=_rank)
            head = pool[: max(3, int(0.6 * len(pool)))]
            if cursor[d] >= len(head):
                continue
            choice = rng.choice(head)
            if choice in picked:
                cursor[d] += 1
                continue
            picked.append(choice)
            used[d] += 1
            progressed = True
        if not progressed:
            break
    return picked


def leg(fid, ty, rng):
    base = f"vec_avg({fid})" if ty == "VECTOR" else fid
    op = rng.choice(["plain", "delta", "avdiff", "zscore"])
    if op == "delta":
        inner = f"ts_delta({base}, {rng.choice(DELTA_W)})"
    elif op == "avdiff":
        inner = f"ts_av_diff({base}, {rng.choice([5, 10, 20])})"
    elif op == "zscore":
        inner = f"ts_zscore({base}, {rng.choice([60, 120, 250])})"
    else:
        inner = base
    return f"{'-' if rng.random() < 0.5 else ''}rank({inner})"


def magnitudes(n):
    out, v = [1.0, 0.6], 0.6
    for _ in range(max(0, n - 2)):
        v = max(0.2, round(v - 0.05, 2))
        out.append(v)
    return out[:n]


def build_add(rng, picked, carrier):
    """The A0 skeleton: weighted additive ensemble under one normalizer."""
    legs = list(CARRIER) if carrier else []
    mags = magnitudes(len(picked) + (2 if carrier else 0))[2 if carrier else 0:]
    for (uc, fid, ty), m in zip(picked, mags):
        legs.append(f"multiply({leg(fid, ty, rng)}, {m})")
    if not carrier:                       # without the carrier the first leg carries weight 1.0
        legs[0] = legs[0].replace(f", {mags[0]})", ", 1.0)", 1)
    body = "add(" + ", ".join(legs) + ", filter=true)"
    return f"signed_power(zscore(ts_decay_linear({body}, {rng.choice(WINDOWS)})), {rng.choice(POWERS)})"


def build_gate(rng, picked, carrier):
    """A2/A4 skeleton: SELECT rather than average.

    An add() of many weak legs is arithmetically a mean, and a mean of many things regresses toward
    whatever is common to them. This structure instead takes ONE signal and switches it on only in
    a regime defined by a SECOND, using trade_when -- so the output is the signal itself on the
    days it is allowed to trade, never a blend. Whether that matters for prod-correlation is the
    open question A2 exists to answer; nothing here asserts it does."""
    sig, gate = picked[0], picked[1]
    s = leg(sig[1], sig[2], rng)
    g_inner = f"vec_avg({gate[1]})" if gate[2] == "VECTOR" else gate[1]
    g = f"ts_zscore({g_inner}, {rng.choice([60, 120, 250])})"
    cmpv = rng.choice([0.0, 0.5, -0.5, 1.0])
    cond = f"{g} {rng.choice(['>', '<'])} {cmpv}"
    core = f"trade_when({cond}, {s}, -1)"
    if carrier:
        # the carrier rides ALONGSIDE the gated signal, still not averaged into it
        core = f"add({core}, multiply({CARRIER[0]}, 0.35), filter=true)"
    return f"signed_power(zscore(ts_decay_linear({core}, {rng.choice(WINDOWS)})), {rng.choice(POWERS)})"


EMP_SCORES = None
SEED = 0


def build_arm(rng, arm, fields, n_per_cell, tag, cells=None):
    cfg = ARMS[arm]
    rows = []
    for cell in (cells or sorted(fields)):
        by_ds = fields.get(cell) or {}
        if not by_ds:
            print(f"  {arm}/{cell}: NO eligible fields at coverage {cfg['cov']}", flush=True)
            continue
        seen, tries = set(), 0
        made = 0
        while made < n_per_cell and tries < n_per_cell * 300:
            tries += 1
            lo, hi = cfg.get("legs", (4, 8))
            k = rng.randint(lo, hi) if cfg["skeleton"] == "add" else 2
            picked = pick_stratified(rng, by_ds, k, max_per_ds=max(1, k // 2),
                                     emp=EMP_SCORES)
            if len(picked) < k:
                continue
            f = (build_add if cfg["skeleton"] == "add" else build_gate)(rng, picked, cfg["carrier"])
            if f.count("(") > 60:                      # FASTEXPR's 64-operator ceiling
                continue
            neut, tr = rng.choice(NEUTS), rng.choice(TRUNCS)
            dec = rng.choice(cfg["decays"])
            key = (f, neut, tr, dec)
            if key in seen:
                continue
            seen.add(key)
            # seed in the id: see gen_shape.py — a bare index collides across runs and the
            # collisions are silently skipped as already-done while the run reports PASS.
            oid = f"{tag}{SEED}{arm}_{cell.replace(' ', '')}_{made:04d}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(SETTINGS_BASE, decay=dec, neutralization=neut,
                                          truncation=tr, universe=UNIVERSE or cfg["universe"],
                                          region=REGION, delay=DELAY),
                         "meta": {"arm": arm, "cell": cell, "skeleton": cfg["skeleton"],
                                  "carrier": cfg["carrier"], "universe": cfg["universe"],
                                  "decay": dec, "neutralization": neut, "truncation": tr,
                                  "coverage_band": list(cfg["cov"]),
                                  "datasets": sorted({d for d in by_ds
                                                      for uc, fid, ty in picked
                                                      if (uc, fid, ty) in by_ds[d]}),
                                  "fields": [fid for _, fid, _ in picked]}})
            made += 1
        print(f"  {arm}/{cell}: {made} rows from {len(by_ds)} datasets", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--arms", default="A0,A1,A2,A3,A4,A5")
    ap.add_argument("--per-cell", type=int, default=40)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--tag", default="AR")
    ap.add_argument("--region", default="USA")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--universe", default="")
    ap.add_argument("--cells", default="", help="comma list; default = every cell with fields")
    # A coverage band is a per-REGION fact, not a constant. 64.7% of the DEU d1 catalogue
    # carries coverage EXACTLY 0 -- catalogued, no data -- so the USA band would sweep those
    # in as if they were fields. A floor above 0 is required; a ceiling is not, because the
    # >=0.90 ceiling is what deleted five whole datasets in USA d1 (ITERATIONS.md I4b).
    ap.add_argument("--no-empirical", action="store_true",
                    help="select on crowding only, ignoring the journal")
    ap.add_argument("--cov-lo", type=float, default=None)
    ap.add_argument("--cov-hi", type=float, default=None)
    args = ap.parse_args()
    global REGION, DELAY, UNIVERSE
    REGION, DELAY, UNIVERSE = args.region, args.delay, args.universe
    global EMP_SCORES, SEED
    SEED = args.seed
    if not args.no_empirical:
        EMP_SCORES = empirical_scores()
        scored = sum(1 for v in EMP_SCORES.values() if v["n"] >= 15)
        print(f"[empirical] {scored} fields have >=15 journal rows and are ranked by measured lift")
    rng = random.Random(args.seed)
    cells = [c.strip() for c in args.cells.split(",") if c.strip()] or None

    cache = {}
    out = []
    for arm in args.arms.split(","):
        arm = arm.strip()
        if arm not in ARMS:
            sys.exit(f"unknown arm {arm}")
        band = ARMS[arm]["cov"]
        if args.cov_lo is not None or args.cov_hi is not None:
            band = (args.cov_lo if args.cov_lo is not None else band[0],
                    args.cov_hi if args.cov_hi is not None else band[1])
        if band not in cache:
            cache[band] = load_fields(*band, region=args.region, delay=args.delay, cells=cells)
            tot = sum(len(v) for c in cache[band].values() for v in c.values())
            print(f"[fields] coverage {band}: {tot} fields across "
                  f"{sum(len(c) for c in cache[band].values())} (cell,dataset) groups", flush=True)
        print(f"[{arm}]", flush=True)
        out += build_arm(rng, arm, cache[band], args.per_cell, args.tag, cells)

    dest = ROOT / args.out
    json.dump(out, open(dest, "w"), indent=1)
    byarm = collections.Counter(r["meta"]["arm"] for r in out)
    print(f"\nwrote {len(out)} rows -> {dest}")
    print("per arm:", dict(byarm))


if __name__ == "__main__":
    raise SystemExit(main())
