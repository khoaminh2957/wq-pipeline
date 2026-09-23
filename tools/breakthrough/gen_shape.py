#!/usr/bin/env python3
"""Deep sweep on the only two structures out of 26 that showed signal.

The 26 literature-derived designs collectively LOST to the existing recipe — 1 zero-fail in 270
evaluable rows (0.4%) against 3.6%, median Sharpe 0.590 against 0.890. Two rows of that table did
not follow the rest:

    D8  Extremum timing / path shape   n=12  median Sharpe 1.58  max 1.71   zero-fail 0
    D7  Story-level VECTOR dispersion  n=12  median Sharpe 0.85  max 2.21   zero-fail 1

D8's median sits ON the 1.58 gate — half its instantiations clear a bar the batch medians 0.59
against, and higher than the production recipe's 0.890. At n=12 that is a lead, not a finding.

What the two share is that neither reads a LEVEL. D8 reads WHEN the extremum happened
(ts_arg_min/ts_arg_max) and the shape of the path (ts_skewness, ts_min_diff on a reversed series);
D7 reads the DISPERSION of an intraday distribution (vec_stddev, vec_range) rather than its mean.
Every leg in the production recipe is a level or a change in a level.

**MECHANISM: UNKNOWN.** "Shape rather than level" is a description of what the two have in common,
observed after seeing the table — it is POST-HOC and it is not an explanation of why either would
decorrelate from a production book. This sweep exists to find out whether the n=12 lead survives,
not to confirm a story.

The sweep varies the axes the two designs never explored: the extremum WINDOW (the original used a
single 250/20 pair), which order statistic is read, the smoothing window, and the settings grid.

  python3 tools/breakthrough/gen_shape.py --out state/autoloop/pool_shape.json --per 8
"""
import argparse, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import field_eda
import opcheck                                                       # noqa: E402

CARRIER = "-rank(divide(close, open)), multiply(-rank(divide(close, vwap)), 0.6)"

# D8 axis: WHERE in the window the extremum sat, and how the path got there.
# The original fixed (250, 20); nothing established those are the right horizons.
LONG_W = [120, 250, 500]
SHORT_W = [10, 20, 60]
SKEW_W = [60, 120, 250]

# D7 axis: which second moment of the intraday distribution, and how long it is smoothed.
VEC_OPS = ["vec_stddev", "vec_range", "vec_count", "vec_max", "vec_min"]
SMOOTH = [5, 10, 20]

NEUTS = ["STATISTICAL", "STATISTICAL", "STATISTICAL", "INDUSTRY"]
DECAYS = [6, 10, 14]
TRUNCS = [0.015, 0.02, 0.05]
WINDOWS = [16, 20, 24, 32]
POWERS = [0.7, 1.0, 1.5]

SETTINGS = {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}


def shape_legs(rng):
    """D8 family: timing of extrema plus path asymmetry. No leg reads a level."""
    lw, sw, kw = rng.choice(LONG_W), rng.choice(SHORT_W), rng.choice(SKEW_W)
    ret = "divide(close, ts_delay(close, 1))"
    pool = [
        f"multiply(rank(subtract(ts_arg_min(close, {lw}), ts_arg_max(close, {lw}))), 0.9)",
        f"multiply(rank(subtract(ts_arg_max(close, {sw}), ts_arg_min(close, {sw}))), 0.6)",
        f"multiply(-rank(ts_skewness({ret}, {kw})), 0.5)",
        # ts_kurtosis / ts_min / ts_max do NOT exist on this account -- I wrote them from memory
        # for the third time today. The platform's own list has ts_min_max_diff (x minus the
        # midpoint of its range, scaled) and ts_min_max_cps (the range-position itself), which is
        # exactly the "where in its own range does today sit" quantity this leg wanted.
        f"multiply(rank(ts_min_max_cps(close, {lw})), 0.45)",
        f"multiply(-rank(ts_min_max_diff(close, {lw})), 0.5)",
        f"multiply(rank(ts_rank(divide(subtract(high, low), close), {sw})), 0.4)",
        f"multiply(-rank(ts_std_dev({ret}, {kw})), 0.4)",
    ]
    rng.shuffle(pool)
    return pool[:rng.randint(4, 6)], {"long_w": lw, "short_w": sw, "skew_w": kw}


def disp_legs(rng, vecs):
    """D7 family: second moments of an intraday distribution, never its mean."""
    sm = rng.choice(SMOOTH)
    legs, used = [], []
    for w in (0.9, 0.7, 0.55, 0.45):
        cand = [v for v in vecs if v not in used]
        if not cand:
            break
        f = rng.choice(cand)
        used.append(f)
        op = rng.choice(VEC_OPS)
        sign = "-" if rng.random() < 0.5 else ""
        legs.append(f"multiply({sign}rank(ts_mean(ts_backfill({op}({f}), 20), {sm})), {w})")
    return legs, {"smooth": sm, "vec_fields": used}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="state/autoloop/pool_shape.json")
    ap.add_argument("--per", type=int, default=8)
    ap.add_argument("--seed", type=int, default=88)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    banned = set(json.load(open(ROOT / "state/banned_fields.json")).get("banned_fields") or [])
    for v in (json.load(open(ROOT / "state/banned_fields.json")).get("by_alpha") or {}).values():
        banned |= set(v)
    cat = field_eda.load_catalogue("USA", 1)
    vecs = [fid for fid, f in cat.items()
            if f["type"] == "VECTOR" and fid not in banned
            and not field_eda.meaningless(f["desc"])
            and isinstance(f["coverage"], (int, float)) and f["coverage"] > 0.05]
    print(f"{len(vecs)} usable VECTOR fields for the dispersion family")

    rows, seen = [], set()
    grid = [(n, d, t, w, p) for n in dict.fromkeys(NEUTS) for d in DECAYS
            for t in TRUNCS for w in WINDOWS for p in POWERS]
    rng.shuffle(grid)

    for fam in ("shape", "disp"):
        made = 0
        tries = 0
        while made < args.per * 26 and tries < args.per * 400:
            tries += 1
            legs, meta = (shape_legs(rng) if fam == "shape" else disp_legs(rng, vecs))
            if len(legs) < 3:
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
            # old_id must be unique across RUNS, not just within one pool. A bare running index
            # made pool_shape (seed 88) and pool_shape2 (seed 404) collide on 208 ids carrying
            # DIFFERENT formulas: resim_bulk skipped all 208 as already-done, the run reported
            # "PASS: journaled 572/572" having simulated 364, and every later join returns the
            # OLD run's formula for those ids. Seed in the id makes a re-run a new experiment.
            oid = f"SH{args.seed}{fam[:2].upper()}_{made:04d}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(SETTINGS, neutralization=n_, decay=d_, truncation=t_),
                         "meta": {"family": f"shape:{fam}", "kind": "shape-sweep",
                                  "W": w_, "power": p_, **meta}})
            made += 1
        print(f"  {fam}: {made} rows")

    json.dump(rows, open(ROOT / args.out, "w"), indent=1)
    print(f"\n{len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
