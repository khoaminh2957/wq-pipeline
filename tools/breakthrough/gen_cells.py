#!/usr/bin/env python3
"""Generate alphas AIMED AT A PYRAMID CELL, rather than at the zero-fail rate.

WHY THIS EXISTS. Measured 2026-08-09: of 59 fully-clean, never-submitted alphas, exactly ONE fills
a cell that is still short. All 59 join Price Volume (37/3) because they are built on the pv
carrier, and beyond that they only touch Earnings (3/3) and Institutions (3/3).

OVERSTATED, corrected 2026-08-10. This used to read "The 3,120 simulations run this session could
not have filled a cell no matter how good they were — the whole batch was aimed at the wrong
objective." Re-measured: 1,418 of those 3,120 rows DO reference a short-cell field, and 14 of the
batch's 109 zero-fail rows do. The batch was not incapable of filling a cell; it was heavily
WEIGHTED away from that — a much weaker claim, and not on its own a reason to abandon the family.
What the 59-alpha measurement supports is only what it says: among alphas that were both clean and
never submitted, one filled a short cell.

    cells still short (USA d1):  Imbalance 0/3  Insiders 0/3  Sentiment 0/3
                                 Short Interest 0/3  Social Media 0/3  News 2/3

A cell unlocks at a COUNT of 3, so sharpe 3.36 and sharpe 1.60 are worth exactly the same. The
deliverable is COVERAGE, and coverage requires the alpha to USE a field from the short category.

STRUCTURE — not invented here, and deliberately so:

  * LIGHT CARRIER + orthogonal dataset legs. Measured ladder: full-OHLCV ensembles score high and
    correlate; OHLCV-free tops out around 0.9 with no edge; two carrier legs plus many orthogonal
    legs is the sweet spot. Carrier-free was 0/2039 zero-fail with median ladder -0.02 against
    0.53 with a carrier, so the carrier stays even though Price Volume is already full — an alpha
    joins several cells at once and the pv membership is simply ignored.
  * ONE normalizer, weights <= 1 and monotone (the leg-scale law: 0/754 -> 18/164 zero-fail).
  * VECTOR fields only ever inside a vec_* reduction.
  * Both signs emitted where the sign is not implied by the field description — a wrong ex-ante
    sign is a data discovery, not sign-fishing, but only if it is registered as a pair.
  * decay near 16 and STATISTICAL neutralization weighted 4:1, the combination that produced the
    two submittable low-prod gems.

  python3 tools/breakthrough/gen_cells.py --cell "Short Interest" --out state/autoloop/pool_si.json
  python3 tools/breakthrough/gen_cells.py --all --per 40
"""
import argparse, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import opcheck                                                          # noqa: E402

TARGETS = ROOT / "state/cell_target_fields.json"

# two legs, real close/open, exactly as the leg-scale law requires
CARRIER = "-rank(divide(close, open)), multiply(-rank(divide(close, vwap)), 0.6)"

VEC_RED = ["vec_avg", "vec_sum", "vec_max", "vec_stddev", "vec_range"]

SETTINGS = {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

NEUTS = ["STATISTICAL", "STATISTICAL", "STATISTICAL", "STATISTICAL", "INDUSTRY", "SUBINDUSTRY"]
DECAYS = [10, 16, 16, 22]
TRUNCS = [0.015, 0.02, 0.05]
WINDOWS = [16, 20, 32]
POWERS = [0.7, 1.0]


def leg(fid, ftype, rng, w):
    """One orthogonal leg. A VECTOR field is reduced first; a MATRIX field is read directly.

    The transform is chosen from a small set that each mean something different about a signal —
    a level, its change, its rank within its own history, its deviation from its own mean — rather
    than a random operator, so a leg that works says which of those the data rewarded."""
    if (ftype or "").upper() == "VECTOR":
        base = f"{rng.choice(VEC_RED)}({fid})"
    else:
        base = fid
    base = f"ts_backfill({base}, 20)"
    form = rng.choice([
        f"rank({base})",                                   # the level, cross-sectionally
        f"rank(ts_delta({base}, {rng.choice([5, 10, 21])}))",   # its change
        f"ts_rank({base}, {rng.choice([60, 120, 250])})",       # where it sits in its own history
        f"rank(ts_zscore({base}, {rng.choice([20, 60])}))",     # deviation from its own mean
    ])
    sign = "-" if rng.random() < 0.5 else ""
    return f"multiply({sign}{form}, {w})"


def build(fields, rng, n_legs):
    picks = rng.sample(fields, min(n_legs, len(fields)))
    weights = [0.9, 0.75, 0.6, 0.5, 0.4, 0.35][:len(picks)]
    return [leg(f[0], f[1], rng, w) for f, w in zip(picks, weights)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--per", type=int, default=40, help="alphas per cell")
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=901)
    args = ap.parse_args()

    tf = json.load(open(TARGETS))
    cells = list(tf) if args.all else [args.cell]
    grid = [(n, d, t, w, p) for n in NEUTS for d in DECAYS for t in TRUNCS
            for w in WINDOWS for p in POWERS]

    rows, seen = [], set()
    for cell in cells:
        fields = [f for f in tf.get(cell, []) if f[0]]
        if not fields:
            print(f"{cell:16} NO USABLE FIELDS — skipped")
            continue
        rng = random.Random(args.seed + hash(cell) % 1000)
        rng.shuffle(grid)
        made, tries = 0, 0
        # A cell with two fields cannot support six-leg ensembles; scale the ask to the supply
        # rather than emitting near-duplicates that the precheck will reject as a batch.
        lo, hi = (1, min(2, len(fields))) if len(fields) < 4 else (3, 6)
        while made < args.per and tries < args.per * 60:
            tries += 1
            legs = build(fields, rng, rng.randint(lo, hi))
            if not legs:
                continue
            body = "add(" + CARRIER + ", " + ", ".join(legs) + ", filter=true)"
            n_, d_, t_, w_, p_ = grid[made % len(grid)]
            f = f"signed_power(zscore(ts_decay_linear({body}, {w_})), {p_})"
            if opcheck.operator_count(f) > opcheck.CEILING:
                continue
            key = (re.sub(r"\s+", "", f), n_, d_, t_)
            if key in seen:
                continue
            seen.add(key)
            oid = f"CELL{args.seed}{re.sub(r'[^A-Za-z]', '', cell)[:4].upper()}_{made:04d}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(SETTINGS, neutralization=n_, decay=d_, truncation=t_),
                         "meta": {"kind": "cell-target", "cell": cell, "family": f"cell:{cell}",
                                  "W": w_, "power": p_, "n_legs": len(legs)}})
            made += 1
        print(f"{cell:16} {made:4} rows from {len(fields)} fields")

    out = args.out or f"state/autoloop/pool_cells_{args.seed}.json"
    json.dump(rows, open(ROOT / out, "w"), indent=1)
    print(f"\n{len(rows)} rows -> {out}")


if __name__ == "__main__":
    raise SystemExit(main())
