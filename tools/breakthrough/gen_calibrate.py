#!/usr/bin/env python3
"""Measure what a market rewards BEFORE building anything on top of it.

The mistake this exists to stop. The working USA d1 recipe is a 2-leg price-volume carrier
(-rank(close/open), -rank(close/vwap)) plus dataset legs, and the carrier is measured to be the
amplitude source: remove it and zero-fail yield goes to 0 (0/190 tonight, 0/2039 historically).
I ported that recipe to USA d0 and to DEU d1 without ever checking that its FOUNDATION pays in
those markets:

    USA d1   median sharpe ~0.55   ->  5% zero-fail
    USA d0   median sharpe  0.55   ->  0/350   (0 zero-fail)
    DEU d1   median sharpe  0.08   ->  0/755   (0 zero-fail)

1,700 simulations to discover that the base signal may not exist there. A 40-row calibration probe
would have said so first, and it is what this generates.

Each probe is ONE primitive under one normalizer, nothing ensembled, so a near-zero Sharpe means
the market does not pay that primitive rather than that a blend was mixed badly. The dataset legs
are deliberately excluded: the question is whether the CARRIER has edge, and mixing data back in
would reintroduce the confound.

  python3 tools/breakthrough/gen_calibrate.py --region DEU --delay 1 --universe TOP500 \
      --out state/autoloop/pool_cal_deu1.json
"""
import argparse, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# Primitives, each a hypothesis about what the market pays. Named so a result reads as an answer.
PRIMS = [
    ("rev_close_open",   "-rank(divide(close, open))"),                    # intraday reversal
    ("rev_close_vwap",   "-rank(divide(close, vwap))"),                    # close vs volume-weighted
    ("rev_close_lag",    "-rank(divide(close, ts_delay(close, 1)))"),      # 1-day reversal
    ("rev_delta1",       "-rank(ts_delta(close, 1))"),                     # 1-day change reversal
    ("mom_delta5",       "rank(ts_delta(close, 5))"),                      # 1-week momentum
    ("mom_delta20",      "rank(ts_delta(close, 20))"),                     # 1-month momentum
    ("rev_ts5",          "-rank(ts_zscore(close, 5))"),                    # short mean-reversion
    ("rev_ts20",         "-rank(ts_zscore(close, 20))"),
    ("vol_intensity",    "rank(divide(volume, ts_mean(volume, 20)))"),     # volume surprise
    ("vol_rev",          "-rank(multiply(returns, rank(volume)))"),        # volume-weighted reversal
    ("hilo_range",       "rank(divide(subtract(high, low), close))"),      # range / realised vol
    ("gap_open",         "-rank(divide(open, ts_delay(close, 1)))"),       # overnight gap reversal
    ("ret_rev1",         "-rank(returns)",),                               # yesterday's return
    ("ret_rev5",         "-rank(ts_sum(returns, 5))"),
    ("liq_adv",          "-rank(adv20)"),                                  # size/liquidity tilt
    ("cap_tilt",         "-rank(cap)"),                                    # size tilt
]

# The same primitive under several neutralizations and decays: a signal can be real and still be
# hidden by a neutralization that removes exactly the exposure it trades.
NEUTS = ["NONE", "INDUSTRY", "SUBINDUSTRY", "MARKET"]
DECAYS = [0, 4, 10]

BASE = {"instrumentType": "EQUITY", "pasteurization": "ON", "unitHandling": "VERIFY",
        "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
        "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31",
        "truncation": 0.08}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--delay", type=int, required=True)
    ap.add_argument("--universe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--neuts", default="NONE,INDUSTRY,SUBINDUSTRY")
    ap.add_argument("--decays", default="0,4")
    ap.add_argument("--tag", default="CAL")
    args = ap.parse_args()

    neuts = [n.strip() for n in args.neuts.split(",") if n.strip()]
    decays = [int(d) for d in args.decays.split(",") if d.strip()]

    # The standing self-correlation rule bans every field used by a SUBMITTED alpha. A calibration
    # probe is never submitted, but the precheck cannot know that and blocks the whole launch on one
    # banned token -- which is how 96 rows made 0 POSTs. Drop the affected primitives here and SAY
    # which ones, because a silently shrunken probe reads as "the market does not pay volume" when
    # the truth is "we never asked".
    import re as _re
    d = json.load(open(ROOT / "state/banned_fields.json"))
    banned = set(d.get("banned_fields") or [])
    for v in (d.get("by_alpha") or {}).values():
        banned |= set(v)
    keep, dropped = [], []
    for name, expr in PRIMS:
        toks = set(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
        hit = sorted(toks & banned)
        (dropped if hit else keep).append((name, expr, hit))
    if dropped:
        print("SKIPPED (banned fields — this probe cannot speak to these families):")
        for name, _e, hit in dropped:
            print(f"   {name:16} uses {hit}")
    PRIMS_USE = [(n, e) for n, e, _h in keep]

    rows, i = [], 0
    for name, expr in PRIMS_USE:
        for neut in neuts:
            for dec in decays:
                oid = f"{args.tag}{args.region}{args.delay}_{name}_{neut[:3]}_{dec}"
                rows.append({
                    "old_id": oid, "id": oid,
                    "formula": expr,
                    "settings": dict(BASE, region=args.region, delay=args.delay,
                                     universe=args.universe, decay=dec, neutralization=neut),
                    "meta": {"probe": name, "neutralization": neut, "decay": dec,
                             "region": args.region, "delay": args.delay,
                             "universe": args.universe, "kind": "calibration"},
                })
                i += 1
    json.dump(rows, open(ROOT / args.out, "w"), indent=1)
    print(f"{len(rows)} calibration probes -> {args.out}")
    print(f"  {len(PRIMS_USE)} primitives x {len(neuts)} neutralizations x {len(decays)} decays")
    print(f"  region={args.region} delay={args.delay} universe={args.universe}")


if __name__ == "__main__":
    raise SystemExit(main())
