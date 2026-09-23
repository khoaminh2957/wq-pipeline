#!/usr/bin/env python3
"""gen_pyramid.py — fill EMPTY pyramid cells while KEEPING the price-volume carrier.

Khoa 2026-07-30: break the concentration of the book (Model 18, PV 12, News 2, Other 1,
Fundamental 1 across 215 ACTIVE alphas; every other USA/D1 cell is empty).

The reframe that makes this tractable — measured from /users/self/alphas, not assumed:

  An alpha belongs to MULTIPLE pyramids at once.
      Xg8oQJRl  pyramids = ['USA/D1/PV', 'USA/D1/NEWS', 'USA/D1/MODEL']   carrier = True
  It keeps the carrier verbatim and still lands in NEWS, purely because its non-carrier legs are
  nws18_* fields. Three cells from one alpha.

So the earlier plan -- drop the carrier to escape Price Volume -- was solving a problem that does
not exist, and it was aimed at a measured dead zone. On USA/TOP3000/delay 1:

      carrier-free : 0 zero-fail out of 908 rows   (median fitness 0.01-0.13)
      with carrier : 601 zero-fail out of 4822

The 0.18% carrier-free rate quoted earlier came ENTIRELY from CHN TOP2000U delay 0 and JPN
TOP1600 delay 0 rows -- a different region and a different delay, both out of scope.

Strategy here: keep the proven carrier, draw every non-carrier leg from ONE target category, and
pick target categories by pyramid MULTIPLIER (from /users/self/activities/pyramid-multipliers):

      Sentiment 1.5 (empty) | Option 1.3 (empty) | Analyst 1.3 (empty) | Earnings 1.3 (empty)
      Risk 1.2 (empty)      | News 1.2 (only 2)  | Model 1.4 (18)      | Price Volume 1.1 (12)

Grammar is Xg8oQJRl's, which is also the measured 47.95% cell: signed_power + zscore +
ts_decay_linear + add + one normalizer throughout, weights a monotone ladder <= 1.0, carrier as
legs 1-2 verbatim.
"""
import json, re, pathlib, argparse, random, time

ROOT = pathlib.Path("/Users/kanenguyen/wq_pipeline")

# Empty or near-empty USA/D1 cells, weighted by pyramid multiplier. Sentiment leads on both
# multiplier (1.5) and on being the only design that survived adversarial refutation.
# Stratify on (category, SUBCATEGORY) -- 26 distinct mechanics on USA d1 -- not on category.
# Measured 2026-07-30: an Analyst-only pool used 461 distinct fields with a median of ZERO shared
# fields between any two rows, yet every gem it produced correlated with the others (prod == self
# on all of them). Field diversity does not buy signal diversity: different analyst fields measure
# the same thing. And once one alpha of a signal family is submitted the rest of that family dies
# -- five banked gems went from prod 0.60-0.69 to 0.73-1.00 the moment their siblings went live.
# So the quantity that decides how many alphas are SUBMITTABLE is the number of distinct
# mechanics, not the number of gate-passers. 464 rows of one mechanic yielded exactly 1.
STRATIFY_SUBCATEGORY = True
# This run is for the mechanics that have NOT had a fair sample. Tally after ~1100 simulated
# rows: Model/ML-AI 4 clean gems, Fundamental/Fundamental 1, Option/Option 1 -- those three are
# already producing and get almost nothing here. Eighteen other mechanics have between 4 and 46
# rows apiece and zero verdicts; none of them can be called dead on that evidence.
# Final pass: the small mechanics never got a fair sample. Their 20-row quota was the max(20,...)
# floor in this file, not a shortage of fields -- Institutions has 37 usable fields and produced a
# CLEAN gem from its first 6 rows. Mechanics already at 0.75+ best-prod after 39-74 rows
# (Model/Reversion, Earnings Estimates, Price Volume) look genuinely crowded rather than
# under-sampled, so they step aside for the ones that have never been tried properly.
# Data-driven: weight = clean-gem rate shrunk toward the global mean (K=120) so a 1-in-21 and a
# 4-in-275 are compared on equal footing, and a 0-in-25 keeps a floor of 0.4 rather than dying.
# Target PYRAMID CELLS, not sub-mechanics. Live cell counts (USA d1): Model 20, Price Volume 16,
# Analyst 2, News 2, Other 1, Fundamental 1, and TEN cells empty. Splitting budget across Model's
# seven sub-mechanics fed one already-full cell; a category's sub-mechanics all land in the SAME
# pyramid cell, so they add no coverage.
#
# Of the ten empty cells, four already have a banked gem (Option, Earnings, Risk, Institutions --
# they need quota, not more mining) and two are unreachable: Insiders has 17 fields but none at
# coverage >= 0.9, Imbalance has no USA-d1 fields at all.
#
# That leaves exactly four empty cells worth simulating for:
# REWEIGHTED 2026-07-31, after Khoa explained what a pyramid is FOR: money is negligible, the
# point is Genius rank, and a cell UNLOCKS at exactly 3 alphas. So the multiplier is irrelevant
# to allocation and cell occupancy is everything -- budget belongs to whichever cell is FEWEST
# alphas away from 3, because that is the cheapest unlock. Platform counts
# (/users/self/activities/pyramid-alphas, USA d1) and the alphas still to MINE per cell:
#
#   Analyst 2/3 -> mine 1      Fundamental 1/3, Other 1/3          -> mine 2
#   Earnings/Risk/Option/Institutions 0/3 but a gem is banked      -> mine 2
#   News/Sentiment/SocialMedia/ShortInterest/Macro 0/3, none banked -> mine 3
#   Model 18/3 and Price Volume 14/3 are DONE -- every further row there buys nothing.
#
# Weight below is the per-SUBCATEGORY share, already divided by how many subcategories the
# category has: subcategories of one category all land in the SAME cell, so a 3-subcategory
# category would otherwise draw 3x the budget of a 1-subcategory one for the same single cell.
#
# RE-WEIGHTED AGAIN 2026-07-31 23:40, now on ~1,980 rows of MEASURED zero-fail yield rather than
# on distance-to-3 alone. Distance was the right first cut but it treated all cells as equally
# minable, and they are not:
#
#   cell           rows   zf    rate     still need   SIMS PER UNLOCK
#   Institutions    141   13   9.2%          2              22
#   Analyst         332   13   3.9%          1              26
#   Fundamental     233    6   2.6%          2              77
#   Earnings        196    5   2.6%          2              77
#   Risk            181    5   2.8%          3             107
#   News             60    1   1.7%          2             118
#   Sentiment        71    0   0.0%          3             210+
#   Other           216    0   0.0%          2             400+
#   Option          207    1   0.5%          3             600
#
# Weight is 1/(sims per unlock). Under the old table Other and Option drew 423 rows between them
# for the two most expensive cells while Institutions -- the cheapest -- drew 141. Note Other and
# Sentiment are NOT written off: 216 and 71 rows without a zero-fail bound their rate, they do not
# prove it is zero, and a mechanic has come back from a worse-looking sample before. They are
# funded at a level that matches what they have earned.
#
# RE-WEIGHTED 2026-08-01 09:30. The measured-yield table above is still right, but it is no longer
# what limits progress: the BANK now holds enough INDEPENDENT families (checked with
# tools/submit_safety.py, not by counting gems) to take Analyst, Earnings, Fundamental and
# Institutions to 3/3. Mining them further cannot raise the rank -- a cell stops at 3.
#
#   covered by the bank, weight 0   Analyst  Earnings  Fundamental  Institutions
#   already unlocked, weight 0      Model    Price Volume
#   still short of supply           News 2  Risk 2  Other 1  Macro 2  Option 3
#                                   Sentiment 3  Social Media 3  Short Interest 3
#
# ("still short" counts INDEPENDENT FAMILIES needed, not alphas: 10 Institutions gems collapsed to
# 3 families, so gem count badly overstates supply.)
#
# These are the expensive cells -- the cheap ones are done. Weighting is families-needed x measured
# rate, with an explicit premium for the barely-sampled ones: Short Interest and Social Media have
# 30-34 rows each, which bounds nothing, while Sentiment (147 rows, 0) and Option (207, 1) have
# actually been looked at and earn less.
BOOST = {
    "Earnings/Earnings": 6.754,
    "News/News Sentiment": 6.259,
    "Institutions/Institutions": 5.882,
    "Fundamental/Fundamental Data": 3.846,
    "Fundamental/Fundamental": 1.691,
    "Earnings/Earnings Estimates": 1.29,
    "Risk/Risk": 0.926,
    "Option/Option": 0.332,
    "Other/Other": 0.25,
    "News/News": 0.25,
    "Macro/Macro": 0.25,
    "Option/Option Analytics": 0.167,
    "Option/Option Volatility": 0.167,
    "Sentiment/Sentiment": 0.167,
    "Social Media/Social Media": 0.167,
    "Short Interest/Short Interest": 0.167,
    "Model/Risk Based Models": 0.0,
    "Model/Risk Models": 0.0,
    "Model/Technical Models": 0.0,
    "Analyst/Analyst Estimates": 0.0,
    "Analyst/Analyst": 0.0,
    "Price Volume/Relationship": 0.0,
    "Price Volume/Price Volume": 0.0,
    "Model/ML/AI Models": 0.0,
    "Model/Valuation Models": 0.0,
    "Model/Model": 0.0,
    "Model/Reversion Models": 0.0
}


def full_cells(region="USA", delay=1):
    """Categories already holding 3 alphas. Empty set if unreadable.

    The live counter alone is not enough right after a submit. Taking the max of 3 reads defends
    against the endpoint's intermittent under-reporting, but on 2026-08-02 all three reads landed
    on the lagging replica minutes after four submits, so this returned the PRE-submit picture and
    a freshly generated pool aimed 1,526 of 4,800 rows at three cells that had just closed. Add
    what the local ledger says we submitted today; the baseline in that ledger makes the
    adjustment cancel itself once the platform catches up."""
    # FAIL CLOSED. Returning an empty set on an unreadable counter means "no cell is full", which
    # is the most dangerous default available: it lets a generator aim a whole pool at cells that
    # are already closed. Observed 2026-08-02 -- a rate-limited read produced a pool listing
    # Analyst, Earnings and Fundamental as minable minutes after all three had been filled.
    # An empty set is only ever returned when the platform genuinely reports no full cell.
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tools"))
    import submit_alphas as _SA
    c, src = _SA._cell_counts(_SA.session(), region, delay)
    if not c:
        raise RuntimeError(f"pyramid cell counts unreadable ({src}) — refusing to guess which "
                           f"cells are open; a wrong answer here aims the whole pool at full cells")
    c = dict(c)
    try:
        for k, n in _SA._submitted_today_by_cell(c).items():
            c[k] = c.get(k, 0) + n
    except Exception:
        pass                     # the pending overlay is a refinement, not the authority
    full = {k for k, v in c.items() if v >= _SA.TRIPLE}

    # HIGH-WATER MARK. The overlay above only covers cells filled TODAY, so a cell filled on an
    # earlier day is defended by nothing but the live read -- and that read is a lagging replica
    # that under-reports about 1 time in 7. Measured 2026-08-02 20:2x: two calls three minutes
    # apart returned {Analyst, Earnings, Fundamental, Institutions, Model, Price Volume} and a set
    # missing the first three, and the pool generated from the short read put 213 of 800 rows on
    # closed cells. Union in every cell seen full recently.
    #
    # The error is deliberately one-directional. Wrongly calling a cell full only withholds mining
    # from it; wrongly calling it open aims a whole pool at a cell that cannot pay (1,526 rows on
    # 2026-08-02, 213 here). The 24h expiry is what stops that bias becoming permanent: cells do
    # normally only fill, but an alpha CAN be decommissioned, and a stale entry then self-heals
    # within a day instead of hiding the cell forever.
    hw_path, now = ROOT / "state/full_cells_highwater.json", time.time()
    try:
        hw = json.load(open(hw_path))
    except Exception:
        hw = {}
    key = f"{region}/{delay}"
    prev = {k: t for k, t in (hw.get(key) or {}).items() if now - t < 86400}
    full |= set(prev)
    prev.update({k: now for k in full})
    hw[key] = prev
    try:
        json.dump(hw, open(hw_path, "w"))
    except Exception:
        pass                     # persistence is a defence, not a precondition
    return full


def cell_weight(cn, sn, full=None):
    """THE single rule for how much to mine a (category, sub-mechanic) bucket.

    It lived in three places with two different answers: gen_pyramid read a key missing from BOOST
    as 1.0 ("average, mine it") while gen_struct.py and classify_fields.py read the same missing
    key as 0 ("never mine it"). Same dict, same key, opposite behaviour -- so a mechanic BOOST had
    not been retargeted for was mined by one generator and invisible to the other.

    An UNLOCKED cell is 0 whatever BOOST says: BOOST is a hand-rewritten dict and goes stale the
    moment a submit lands, which is precisely when it matters most. A cell holding 3 alphas is not
    a weighting question."""
    if cn in (full if full is not None else full_cells()):
        return 0.0
    return BOOST.get(f"{cn}/{sn}", 1.0)


# Every pyramid category the platform serves for USA/D1. Insiders and Imbalance were absent until
# 2026-08-06 and their absence was silent: load_fields() drops anything not listed here, so two
# cells of the pyramid were unmineable by construction and looked merely empty. The field crawl
# that day showed insiders holds 185 fields and imbalance exactly 2 -- so Insiders was always
# minable and nothing had ever aimed at it.
# Multipliers mirror the neighbouring cells; the value only weights the draw and a wrong guess
# costs sampling emphasis, not correctness.
TARGETS = {"Analyst": 1.3, "Earnings": 1.3, "Option": 1.3, "Sentiment": 1.5, "Risk": 1.2,
           "News": 1.2, "Social Media": 1.1, "Model": 1.4, "Fundamental": 1.1, "Other": 1.5,
           "Institutions": 1.0, "Short Interest": 1.1, "Macro": 1.1, "Price Volume": 1.1,
           "Insiders": 1.2, "Imbalance": 1.2}

CARRIER = ["-rank(divide(close, open))", "multiply(-rank(divide(close, vwap)), 0.6)"]

BAD_ID = re.compile(r"(iso|isin|_fkey|country|currency|crncy|_code$|timestamp|_utc|"
                    r"fiscal_(qtr|yr)_period|_id$|sedol|cusip|ticker|exchange)", re.I)
BAD_DESC = re.compile(r"(identifier|iso |code\b|timestamp|date of|name of|"
                      r"initialization constraint)", re.I)
RAW_OHLC = {"close", "open", "high", "low", "vwap", "volume", "returns", "adv20", "cap"}

SETTINGS_BASE = {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
                 "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
                 "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
                 "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

# Measured on USA/TOP3000/d1: window 50 -> 86.4% (n=59), 32 -> 75.0% (n=56), 20 is the reference
# winner's own cell; exponent 3.5 -> 55.8% (n=172), 3.0 -> 47.7%, 2.5 is the winner's. Both lists
# include the winner's values -- excluding them once cost three rounds of searching a space with
# the known answer removed.
WINDOWS = [50, 50, 32, 32, 20, 20, 16]
POWERS = [3.5, 3.5, 3.0, 2.5, 2.5]
NEUTS = ["INDUSTRY", "INDUSTRY", "SUBINDUSTRY", "STATISTICAL"]
TRUNCS = [0.02, 0.02, 0.015, 0.05]
DECAYS = [6, 6, 6, 4, 14]
LEG_OPS = ["plain", "delta", "avdiff"]
DELTA_W = [5, 10, 20, 60]


def load_fields():
    d = json.load(open(ROOT / "state/banned_fields.json"))
    banned = set(d.get("banned_fields") or [])
    for v in (d.get("by_alpha") or {}).values():
        banned |= set(v)
    out = {}
    for line in open(ROOT / "fetched/fields_all.jsonl"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("region") != "USA" or d.get("_delay") != 1:
            continue
        c = d.get("category")
        cn = c.get("name") if isinstance(c, dict) else c
        if cn not in TARGETS:
            continue
        fid, ds = d["id"], d.get("description") or ""
        if fid in banned or fid in RAW_OHLC or BAD_ID.search(fid) or BAD_DESC.search(ds):
            continue
        if (d.get("coverage") or 0) < 0.90:
            continue
        sc = d.get("subcategory")
        sn = (sc.get("name") if isinstance(sc, dict) else sc) or cn
        out.setdefault((cn, sn), []).append((d.get("userCount") or 0, fid, d.get("type")))
    for k in out:
        out[k].sort()                      # least-crowded first
    return {k: v for k, v in out.items() if isinstance(k, tuple) and len(v) >= 8}


def leg(fid, ty, rng):
    """One non-carrier leg, in the reference winner's own op set.

    rank() throughout -- one normalizer per formula, because rank spans [0,1] while zscore spans
    ~[-3,3] and mixing them lets the zscore legs dominate before weights apply."""
    base = f"vec_avg({fid})" if ty == "VECTOR" else fid
    op = rng.choice(LEG_OPS)
    if op == "delta":
        inner = f"ts_delta({base}, {rng.choice(DELTA_W)})"
    elif op == "avdiff":
        inner = f"ts_av_diff({base}, {rng.choice([5, 10, 20])})"
    else:
        inner = base
    sign = "-" if rng.random() < 0.5 else ""
    return f"{sign}rank({inner})"


def magnitudes(n):
    """Monotone non-increasing ladder starting at 1.0, floor 0.2 -- the reference winner's shape
    (1.0, 0.6, 0.6, 0.55, 0.5, 0.45, 0.4, 0.4, 0.4). Magnitudes above 1.0 turned an 8-leg
    ensemble into a 2-leg alpha with six legs of noise."""
    out, v = [1.0, 0.6], 0.6
    for _ in range(max(0, n - 2)):
        v = max(0.2, round(v - 0.05, 2))
        out.append(v)
    return out[:n]


def build(rng, cat, pool, n, tag):
    rows, seen = [], set()
    if len(pool) < 3:
        return rows
    tries = 0
    while len(rows) < n and tries < n * 400:
        tries += 1
        k = rng.randint(4, 9)                       # non-carrier legs
        head = pool[: max(k, len(pool) // 2)]       # stay in the least-crowded half
        if len(head) < k:
            continue
        picked = rng.sample(head, k)
        mags = magnitudes(k + 2)[2:]                # first two magnitudes belong to the carrier
        legs = list(CARRIER)
        for (uc, fid, ty), m in zip(picked, mags):
            legs.append(f"multiply({leg(fid, ty, rng)}, {m})")
        w, p = rng.choice(WINDOWS), rng.choice(POWERS)
        body = "add(" + ", ".join(legs) + ", filter=true)"
        f = f"signed_power(zscore(ts_decay_linear({body}, {w})), {p})"
        neut, tr, dec = rng.choice(NEUTS), rng.choice(TRUNCS), rng.choice(DECAYS)
        key = (f, neut, tr, dec)
        if key in seen:
            continue
        seen.add(key)
        oid = f"{tag}_{cat.replace(' ', '')}_{len(rows):03d}"
        rows.append({"old_id": oid, "id": oid, "formula": f,
                     "settings": dict(SETTINGS_BASE, decay=dec, neutralization=neut,
                                      truncation=tr),
                     "meta": {"skeleton": "signedpower>zscore>tsdecaylinear", "dataset": cat,
                              "neutralization": neut, "decay": dec, "universe": "TOP3000",
                              "legs": k, "truncation": tr, "category_target": cat,
                              "multiplier": TARGETS[cat],
                              "fields": [fid for _, fid, _ in picked]}})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", default="PY")
    ap.add_argument("--total", type=int, default=1300)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    fields = load_fields()

    # Budget is BOOST alone -- i.e. purely how close the cell is to unlocking at 3 alphas.
    # It used to be multiplied by TARGETS[cn] (the payout multiplier) and by the category's field
    # count, which is why Sentiment took 30% of round 1: 233 fields x multiplier 1.5. Neither
    # factor belongs here. Payout is negligible next to Genius rank, and a big field pool only has
    # to be large enough to build n distinct rows -- it is not evidence the cell is worth mining.
    full = full_cells()
    per = {k: cell_weight(*k, full=full) for k in fields}
    per = {k: v for k, v in per.items() if v > 0}      # weight 0 = unlocked cell, mine nothing
    if full:
        print(f"  skipping unlocked cells: {sorted(full)}")
    tot = sum(per.values()) or 1
    rows = []
    for mi, ((cn, sn), wt) in enumerate(sorted(per.items(), key=lambda kv: -kv[1])):
        n = max(20, int(args.total * wt / tot))
        # index the tag: truncating the subcategory name collided ("Fundamental" and
        # "Fundamental Data" both became "Fundamenta"), producing duplicate old_ids and a
        # 75-error validate. The mechanic name lives in meta; the id only needs to be unique.
        tag = f"{args.tag}m{mi:02d}"
        got = build(rng, cn, fields[(cn, sn)], n, tag)
        for g in got:
            g["meta"]["mechanic"] = f"{cn}/{sn}"
            g["meta"]["dataset"] = f"{cn}/{sn}"      # the knowledge axis learns per MECHANIC
        rows += got
        if len(got) < n:
            print(f"  {cn}/{sn}: {len(got)}/{n} from {len(fields[(cn,sn)])} fields")

    for r in rows:
        toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", r["formula"]))
        assert {"close", "open", "vwap"} <= toks, f"{r['old_id']} lost the carrier"
    p = pathlib.Path(args.out)
    tmp = p.with_suffix(".tmp")
    json.dump(rows, open(tmp, "w"), indent=1)
    tmp.replace(p)
    from collections import Counter
    print(f"wrote {len(rows)} rows -> {p}")
    print("  by target cell:", dict(Counter(r["meta"]["category_target"] for r in rows)))


if __name__ == "__main__":
    main()
