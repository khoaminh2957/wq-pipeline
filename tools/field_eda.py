#!/usr/bin/env python3
"""Profile fields BEFORE selecting them, and make every filter stage report what it removed.

Why this exists. Every filter in the old pipeline was silent, and each silent one cost real work:

  * `coverage >= 0.90` deleted FIVE whole datasets in USA d1 -- 315 fields of Transformer Based
    News Sentiment, 260 of Macro Economic Event Data, 129 of MnA Deals, 102 of Finance Creator
    Prediction, 17 of Smart Insider. ~900 fields no generator ever saw. The arm built only from
    that deleted band matched the control's yield exactly (7/128 vs 8/154).
  * Sorting by crowding and taking the least-crowded half handed Social Media 100% of its legs to
    one dataset and Insiders 92.3% to another -- a hard ceiling of ONE submittable per cell,
    because a cell needs three INDEPENDENT alphas.
  * 64.7% of the DEU d1 catalogue reads coverage EXACTLY 0. Catalogued, no data. A USA-tuned band
    sweeps those in as though they were fields.

None of those were visible until someone went looking. So each stage here returns
(kept, dropped, profile) and the profile is printed: a filter that removes a whole dataset says so.

FOUR INDEPENDENT BRANCHES, each answering a different question about a field:

  A  CATALOGUE   what the platform says it is    coverage, userCount, alphaCount, type, dataset
  B  SEMANTIC    what its DESCRIPTION says it measures    role, unit, event-vs-level
  C  EMPIRICAL   what 57k simulations say it did    sharpe lift, zero-fail lift, prod-clean lift
  D  SELECTION   combine A+B+C into a ranked draw, stratified across datasets

Branch C is the one that cannot be faked: it is measured on this account's own history rather than
inferred from metadata. Its weakness is attribution -- a field appears in a formula alongside 1-8
others, so a single field's contribution is noisy. It is therefore computed WITHIN pool and cell
(so pool-level effects cancel), reported with n, and never used alone below n=15.

  python3 tools/field_eda.py --region USA --delay 1                    # full profile
  python3 tools/field_eda.py --region DEU --delay 1 --cell News --top 30
  python3 tools/field_eda.py --region USA --delay 1 --json out.json    # machine-readable
"""
import argparse, collections, glob, json, math, os, pathlib, re, statistics as stt, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

RAW_PV = {"open", "close", "high", "low", "vwap", "volume", "returns", "adv20", "cap"}

# ---------------------------------------------------------------- branch B: semantic
# A field's ROLE decides which operator can make MEANING of it. A LEVEL ranked cross-sectionally is
# a static tilt with no timing; the same level under ts_delta is a change. An EVENT field is sparse
# by nature and its zero days are information, not gaps.
ROLE_PATTERNS = [
    ("EVENT",     r"\b(announce|event|filing|deal|merger|acquisition|split|dividend declar|"
                  r"guidance|upgrade|downgrade|initiation|halt|offering|IPO|bankrupt)\w*\b"),
    ("SENTIMENT", r"\b(sentiment|tone|polarity|bullish|bearish|positive|negative|opinion|"
                  r"emotion|buzz|attention)\w*\b"),
    ("COUNT",     r"\b(number of|count|total number|frequency|how many|volume of (articles|stories|mentions))\b"),
    ("CHANGE",    r"\b(change|growth|delta|revision|surprise|difference|increase|decrease|"
                  r"momentum|trend|shift)\w*\b"),
    ("RATIO",     r"\b(ratio|per share|margin|yield|percent|percentage|rate|proportion|share of|"
                  r"relative to|divided by)\b"),
    ("FLOW",      r"\b(flow|inflow|outflow|traded|turnover|transaction|purchase|sale|sold|bought|"
                  r"lending|borrow|short volume)\w*\b"),
    ("LEVEL",     r"\b(value|amount|price|level|balance|outstanding|total|capitalization|"
                  r"score|rank|index|estimate)\w*\b"),
]
UNIT_PATTERNS = [
    ("CURRENCY", r"\b(USD|EUR|dollar|currency units|in millions|in thousands|monetary)\b"),
    ("PERCENT",  r"\b(percent|percentage|%|basis point|bps)\b"),
    ("COUNT",    r"\b(number of|count|total number|shares|contracts)\b"),
    ("SCORE",    r"\b(score|index|rank|rating|probability|0-1|0 to 1|z-score|standardi[sz]ed)\b"),
    ("RATIO",    r"\b(ratio|per share|margin|yield|multiple)\b"),
]


def classify(desc):
    """(role, unit) inferred from the description. First pattern wins -- ordered most specific
    first, because 'earnings surprise value' is a CHANGE before it is a LEVEL."""
    d = desc or ""
    role = next((r for r, p in ROLE_PATTERNS if re.search(p, d, re.I)), "UNKNOWN")
    unit = next((u for u, p in UNIT_PATTERNS if re.search(p, d, re.I)), "UNKNOWN")
    return role, unit


# A field whose description names a clock, a calendar or a lookup table is not a signal --
# ranking it orders rows by an arbitrary label. Anchored at the START so a price move that merely
# mentions a time survives ("Highest price reached from time of news to session end").
BAD_SUBJ = re.compile(r"^\s*(the\s+)?(utc\s+|publication\s+|expiration\s+|arrival\s+|report\s+)?"
                      r"(date|time|timestamp|datetime|day)\b", re.I)
BAD_DATEY = re.compile(r"\b(announcement|expected|effective|filing|expiration|maturity|payment|"
                       r"record|ex[- ]dividend|start|end)\s+date\b|\bdate\s+(from|of the|for the)\b", re.I)
BAD_DESC = re.compile(r"((topic|category|sector|country|currency|exchange)\s*code|code\s*\(integer\)|"
                      r"must decode|index\s*\(into|\bindex into\b|\bidentifier\b|\bticker\b|"
                      r"\bISIN\b|\bCUSIP\b|\bSEDOL\b|company name)", re.I)


def meaningless(desc):
    d = desc or ""
    return bool(BAD_SUBJ.search(d) or BAD_DATEY.search(d) or BAD_DESC.search(d))


def dsname(v):
    return (v.get("name") or v.get("id")) if isinstance(v, dict) else (v or "?")


# ---------------------------------------------------------------- branch A: catalogue
def load_catalogue(region, delay):
    out = {}
    for line in open(ROOT / "fetched/fields_all.jsonl"):
        try:
            f = json.loads(line)
        except Exception:
            continue
        if f.get("region") != region or f.get("_delay") != delay or not f.get("id"):
            continue
        c = f.get("category")
        out[f["id"]] = {
            "id": f["id"],
            "cell": (c.get("name") if isinstance(c, dict) else c) or "?",
            "dataset": dsname(f.get("dataset")),
            "type": (f.get("type") or "").upper(),
            "coverage": f.get("coverage"),
            "userCount": f.get("userCount"),
            "alphaCount": f.get("alphaCount"),
            "desc": f.get("description") or "",
        }
    return out


# ---------------------------------------------------------------- branch C: empirical
def load_empirical():
    """field -> stats, measured WITHIN pool so pool-level effects cancel.

    A field never appears alone: it sits in a formula with 1-8 other legs, so this is a noisy
    attribution and is reported as such. What makes it usable is the within-pool contrast -- for
    each pool, compare formulas that contain the field against formulas from the SAME pool that do
    not, then average those contrasts. A field that only ever appears in one strong pool cannot
    look good by inheriting that pool's mean."""
    oid2code, oid2pool = {}, {}
    for p in glob.glob(str(ROOT / "state/**/*targets*.json"), recursive=True) + \
             glob.glob(str(ROOT / "state/autoloop/pool_*.json")):
        try:
            rows = json.load(open(p))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        name = os.path.basename(p)
        for r in rows:
            if isinstance(r, dict) and r.get("old_id") and r.get("formula"):
                oid2code.setdefault(r["old_id"], r["formula"])
                oid2pool.setdefault(r["old_id"], name)

    res = {}
    for line in open(ROOT / "state/resim_results.jsonl"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("old_id") in oid2code:
            res[r["old_id"]] = r          # last row carrying checks wins

    corr = {}
    try:
        for a, v in json.load(open(ROOT / "state/prod_corr_measured.json")).items():
            if v.get("prod_maxcorr") is not None:
                corr[a] = v["prod_maxcorr"]
    except Exception:
        pass

    # per pool: the rows, and for each field the rows containing it
    pool_rows = collections.defaultdict(list)
    field_rows = collections.defaultdict(lambda: collections.defaultdict(list))
    for oid, r in res.items():
        if not isinstance(r.get("sharpe"), (int, float)):
            continue
        ck = r.get("checks") or []
        zf = bool(ck and any(isinstance(c, dict) for c in ck)
                  and not any(isinstance(c, dict) and c.get("result") == "FAIL" for c in ck))
        clean = corr.get(r.get("alpha"))
        rec = (abs(r["sharpe"]), zf, clean)
        pool = oid2pool[oid]
        pool_rows[pool].append(rec)
        toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", oid2code[oid])) - RAW_PV
        for t in toks:
            if re.fullmatch(r"[a-z][a-z0-9_]{3,}", t):
                field_rows[t][pool].append(rec)

    stats = {}
    for fid, pools in field_rows.items():
        lifts_sh, lifts_zf, n_tot, zf_hits, clean_hits, clean_n = [], [], 0, 0, 0, 0
        for pool, rows in pools.items():
            base = pool_rows[pool]
            if len(rows) < 3 or len(base) - len(rows) < 3:
                continue
            wit_sh = stt.mean(x[0] for x in rows)
            wo = [x for x in base if x not in rows]          # identity-based; fine for tuples here
            if len(wo) < 3:
                continue
            lifts_sh.append(wit_sh - stt.mean(x[0] for x in wo))
            lifts_zf.append(sum(1 for x in rows if x[1]) / len(rows)
                            - sum(1 for x in wo if x[1]) / len(wo))
            n_tot += len(rows)
            zf_hits += sum(1 for x in rows if x[1])
            for x in rows:
                if x[2] is not None:
                    clean_n += 1
                    clean_hits += (x[2] < 0.70)
        if not lifts_sh:
            continue
        stats[fid] = {
            "n": n_tot,
            "n_pools": len(lifts_sh),
            "sharpe_lift": round(stt.mean(lifts_sh), 4),
            "zf_lift": round(stt.mean(lifts_zf), 4),
            "zf_rate": round(zf_hits / n_tot, 4) if n_tot else None,
            "prod_clean_rate": round(clean_hits / clean_n, 4) if clean_n >= 5 else None,
            "prod_clean_n": clean_n,
        }
    return stats


# ---------------------------------------------------------------- branch D: staged selection
def stage(name, fields, predicate, log):
    """Apply one filter and RECORD what it removed, by dataset. A stage that deletes an entire
    dataset must say the dataset's name -- that is the failure `coverage >= 0.90` hid five times."""
    kept, dropped = {}, {}
    for fid, f in fields.items():
        (kept if predicate(f) else dropped)[fid] = f
    by_ds_before = collections.Counter(f["dataset"] for f in fields.values())
    by_ds_after = collections.Counter(f["dataset"] for f in kept.values())
    wiped = sorted(d for d in by_ds_before if by_ds_after.get(d, 0) == 0)
    log.append({
        "stage": name,
        "in": len(fields), "kept": len(kept), "dropped": len(dropped),
        "datasets_before": len(by_ds_before), "datasets_after": len(by_ds_after),
        "datasets_wiped": wiped,
        "wiped_field_count": sum(by_ds_before[d] for d in wiped),
    })
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="USA")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--cell", default="")
    ap.add_argument("--cov-lo", type=float, default=0.05)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--min-n", type=int, default=15, help="min journal rows before empirical stats are trusted")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    cat = load_catalogue(args.region, args.delay)
    if not cat:
        sys.exit(f"no catalogue rows for {args.region} d{args.delay} — crawl it first")
    if args.cell:
        cat = {k: v for k, v in cat.items() if v["cell"] == args.cell}

    print(f"=== {args.region} d{args.delay}"
          f"{' · ' + args.cell if args.cell else ''} — {len(cat)} catalogued fields ===\n")

    # ---- branch A: catalogue shape
    cov = [f["coverage"] for f in cat.values() if isinstance(f["coverage"], (int, float))]
    zero = sum(1 for c in cov if c == 0)
    print("BRANCH A — catalogue")
    if cov:
        print(f"   coverage   exactly 0: {zero} ({100*zero/len(cov):.1f}%)   "
              f"median(>0): {stt.median([c for c in cov if c > 0]):.3f}")
    uc = [f["userCount"] for f in cat.values() if isinstance(f["userCount"], (int, float))]
    if uc:
        uc.sort()
        print(f"   userCount  median {stt.median(uc):.0f}   p90 {uc[int(.9*len(uc))-1]:.0f}   max {max(uc)}")
    print(f"   types      {dict(collections.Counter(f['type'] for f in cat.values()).most_common())}")
    print(f"   datasets   {len(set(f['dataset'] for f in cat.values()))}\n")

    # ---- branch B: semantic
    for f in cat.values():
        f["role"], f["unit"] = classify(f["desc"])
    print("BRANCH B — semantic (from the DESCRIPTION, not the id)")
    print(f"   roles  {dict(collections.Counter(f['role'] for f in cat.values()).most_common())}")
    print(f"   units  {dict(collections.Counter(f['unit'] for f in cat.values()).most_common())}\n")

    # ---- branch D: staged selection, each stage reporting its attrition
    log = []
    sel = cat
    sel = stage("drop GROUP type (group-arg only, never a signal)", sel,
                lambda f: f["type"] != "GROUP", log)
    sel = stage("drop meaningless (clock / calendar / lookup code)", sel,
                lambda f: not meaningless(f["desc"]), log)
    sel = stage(f"coverage > {args.cov_lo} (catalogued-but-empty)", sel,
                lambda f: isinstance(f["coverage"], (int, float)) and f["coverage"] > args.cov_lo, log)
    print("BRANCH D — staged selection, with what each stage removed")
    for s in log:
        line = (f"   {s['stage']:52} {s['in']:5} -> {s['kept']:5}"
                f"   datasets {s['datasets_before']:3} -> {s['datasets_after']:3}")
        if s["datasets_wiped"]:
            line += f"\n      WIPED {len(s['datasets_wiped'])} dataset(s), {s['wiped_field_count']} fields: " \
                    + ", ".join(s["datasets_wiped"][:4]) + ("..." if len(s["datasets_wiped"]) > 4 else "")
        print(line)
    print()

    # ---- branch C: empirical, joined onto the survivors
    emp = load_empirical()
    joined = 0
    for fid, f in sel.items():
        e = emp.get(fid)
        if e and e["n"] >= args.min_n:
            f.update(e)
            joined += 1
    print(f"BRANCH C — empirical, from the simulation journal ({joined}/{len(sel)} fields have n>={args.min_n})")
    ranked = sorted((f for f in sel.values() if f.get("n")), key=lambda f: -f["zf_lift"])
    if ranked:
        print(f"\n   TOP {args.top} by zero-fail lift (within-pool contrast):")
        print(f"   {'field':38} {'n':>5} {'pools':>6} {'zfLift':>8} {'shLift':>8} {'zfRate':>7} {'prodClean':>10}  dataset")
        for f in ranked[:args.top]:
            pc = f"{f['prod_clean_rate']:.2f}({f['prod_clean_n']})" if f.get("prod_clean_rate") is not None else "-"
            print(f"   {f['id'][:38]:38} {f['n']:5} {f['n_pools']:6} {f['zf_lift']:+8.4f} "
                  f"{f['sharpe_lift']:+8.4f} {f['zf_rate']:7.3f} {pc:>10}  {f['dataset'][:26]}")
        print(f"\n   BOTTOM {min(args.top, len(ranked))} — fields that DRAG:")
        for f in ranked[-args.top:][::-1]:
            print(f"   {f['id'][:38]:38} {f['n']:5} {f['n_pools']:6} {f['zf_lift']:+8.4f} "
                  f"{f['sharpe_lift']:+8.4f} {f['zf_rate']:7.3f}  {f['dataset'][:26]}")
    else:
        print("   no field reaches the n threshold in this slice — the journal has not "
              "simulated this region/cell enough to say anything")

    if args.json:
        json.dump({"region": args.region, "delay": args.delay, "cell": args.cell,
                   "stages": log, "fields": list(sel.values())},
                  open(ROOT / args.json, "w"), indent=1)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    raise SystemExit(main())
