#!/usr/bin/env python3
"""Three-arm experiment for H7: does the anchor's CATEGORY matter, or only its amplitude?

This is the load-bearing test for the two-category programme. See HYPOTHESES.md H7 / O1b.

The situation it resolves. Carrier-free alphas are not weak everywhere -- across 1,434 rows they
fail `IS_LADDER_SHARPE` LESS often than carried ones (77.7% vs 91.8%), and fifteen cleared the
ladder bar outright at 2.05-3.05. What they fail is `LOW_SHARPE`, on **100.0% of 1,434 rows**.
The signals are persistent enough and too small.

Two explanations survive that observation and no experiment has separated them:
  (a) the anchor supplies AMPLITUDE -- a weight-1.0 leg that moves daily for every name -- and the
      other legs only tilt a book the anchor sizes;
  (b) the non-price fields in these cells are intrinsically slow, and price is incidental.

The arms differ in exactly one thing, the anchor:

  PVCARRIER   -rank(divide(close, open)) + -rank(divide(close, vwap))x0.6   -> joins Price Volume
  NEWSANCHOR  -rank(divide(vec_avg(all_sessions_vwap),
                           vec_avg(afterhours_volume_weighted_avg_price)))  -> joins News
  NOANCHOR    no anchor leg

`all_sessions_vwap` and `afterhours_volume_weighted_avg_price` were resolved from the platform on
2026-08-02: category **News**, dataset news12, coverage **1.00**, type VECTOR. They are two price
measurements of the same name filed outside Price Volume, so the reversal between them is the
carrier's mechanic without the carrier's category. VECTOR type requires `vec_avg` (logic_operators
law 4: VECTOR->MATRIX only through a vec_* reducer, applied to a raw VECTOR field).

If NEWSANCHOR recovers amplitude, a two-category alpha can carry its own amplitude and the
programme is viable. If it fails at ~100% like NOANCHOR, the constraint is the data in these
cells, not the skeleton.

  python3 tools/breakthrough/gen_anchor.py --out pool.json --total 3000
"""
import argparse, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "breakthrough"))
sys.path.insert(0, str(ROOT / "tools"))
import gen_pyramid as GP                                            # noqa: E402
import gen_struct as GS                                             # noqa: E402
import gen_diverse as GD                                            # noqa: E402

PV_CARRIER = list(GP.CARRIER)
NEWS_A = "vec_avg(all_sessions_vwap)"
NEWS_B = "vec_avg(afterhours_volume_weighted_avg_price)"
NEWS_C = "vec_avg(aggregate_sessions_vwap)"
ARMS = ["PVCARRIER", "NEWSANCHOR", "NOANCHOR"]
OP_LIMIT = 60


def anchor_legs(arm, rng):
    """The ONLY thing that differs between arms."""
    if arm == "PVCARRIER":
        return PV_CARRIER
    if arm == "NEWSANCHOR":
        b = rng.choice([NEWS_B, NEWS_C])
        return [f"-rank(divide({NEWS_A}, {b}))",
                f"multiply(-rank(divide({NEWS_A}, ts_delay({NEWS_A}, 1))), 0.6)"]
    return []


def build(rng, picked, arm, R):
    # list(): anchor_legs returns the module-level PV_CARRIER for the control arm, and the append
    # below MUTATED it. The shared list grew by 4-7 entries per call, so after a few hundred rows
    # every control formula was thousands of legs long, blew the operator limit, and was silently
    # discarded -- 3 rows kept out of 2,000 attempts at 15.75 ms each, against 0.04 ms for the
    # arms that happened to build a fresh list.
    legs = list(anchor_legs(arm, rng))
    mags = GP.magnitudes(len(picked) + (2 if legs else 0))
    ms = mags[2:] if legs else mags
    recipes = []
    for (uc, fid, ty), m in zip(picked, ms):
        info = R.get(fid) or {}
        L, r = GD.leg(rng, fid, ty, info.get("label", "LEVEL"), info)
        recipes.append(r)
        legs.append(f"multiply({L}, {m})")
    body = "add(" + ", ".join(legs) + ", filter=true)"
    return (f"zscore(ts_decay_linear({body}, {rng.choice([10, 20, 50])}))",
            sorted(set(recipes)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--total", type=int, default=3000)
    ap.add_argument("--tag", default="AN")
    ap.add_argument("--seed", type=int, default=57)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    R = GD.roles()

    fields = GP.load_fields()
    full = GP.full_cells()
    # NEWSANCHOR already spends one category on News, so its other legs must come from a DIFFERENT
    # open cell or the alpha lands on 3 categories and counts for nothing. Every arm therefore
    # draws from the same non-News open cells, so the arms stay comparable.
    usable = {}
    for (cn, sn), pool in fields.items():
        if cn in full or cn == "News":
            continue
        keep = [(uc, fid, ty) for uc, fid, ty in pool
                if (R.get(fid) or {}).get("label") != "META"]
        if len(keep) >= 8:
            usable[(cn, sn)] = keep
    print(f"cells available to all three arms: {sorted({c for c, _ in usable})}")

    # Dedup on the SAME key preflight uses -- formula AND the settings that materially change the
    # simulated alpha. Excluding on the formula alone is far stricter than the gate it is meant to
    # satisfy, and it starves the control arm: PVCARRIER emits the shape 32,000 staged rows already
    # use, so a formula-only filter rejected almost everything it built (4 of 10 on a smoke run)
    # and the loop burned its whole try budget on collisions.
    def skey(t):
        st = t.get("settings") or {}
        return (re.sub(r"\s+", "", t.get("formula") or ""),) + tuple(
            st.get(k) for k in ("region", "universe", "delay", "neutralization", "decay",
                                "truncation", "maxPosition", "maxTrade", "selectionLimit",
                                "selectionHandling", "lookback"))

    seen = set()
    for p in ROOT.glob("state/**/*targets*.json"):
        try:
            rr = json.load(open(p))
        except Exception:
            continue
        if isinstance(rr, list):
            for r in rr:
                if isinstance(r, dict) and r.get("formula"):
                    seen.add(skey(r))
    print(f"excluding {len(seen)} formula+settings combinations already staged")

    cells = list(usable)
    per = args.total // len(ARMS)
    rows = []
    for arm in ARMS:
        made = tries = 0
        while made < per and tries < per * 80:
            tries += 1
            cn, sn = cells[rng.randrange(len(cells))]
            pool = usable[(cn, sn)]
            k = rng.randint(4, 7)
            head = pool[: max(k, len(pool) // 2)]
            if len(head) < k:
                continue
            f, recipes = build(rng, rng.sample(head, k), arm, R)
            if GD.op_count(f) > OP_LIMIT:
                continue
            st = dict(GP.SETTINGS_BASE, decay=rng.choice([4, 6, 10]),
                      neutralization=rng.choice(["INDUSTRY", "SUBINDUSTRY", "STATISTICAL"]),
                      truncation=rng.choice([0.01, 0.02, 0.04]))
            if skey({"formula": f, "settings": st}) in seen:
                continue
            seen.add(skey({"formula": f, "settings": st}))
            oid = f"{args.tag}{arm[:4]}_{cn.replace(' ', '')[:8]}_{made:04d}"
            cats = cn if arm != "NEWSANCHOR" else f"News+{cn}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": st,
                         "meta": {"skeleton": f"{arm}+oneZ", "dataset": f"{cn}/{sn}",
                                  "mechanic": f"{arm}/{cn}", "arm": arm,
                                  "carrier": arm == "PVCARRIER",
                                  "legs_used": "|".join(recipes),
                                  "combine": "ADDITIVE", "norm": "oneZ", "power": False,
                                  "backfill": "backfilled" in recipes,
                                  "category_target": cn,
                                  "category_pair": "News" if arm == "NEWSANCHOR" else None,
                                  "cells_claimed": cats,
                                  "universe": "TOP3000", "legs": k,
                                  "neutralization": "", "decay": 0, "truncation": 0}})
            made += 1
        print(f"  {arm:11} -> {made} rows from {tries} attempts "
              f"({made/max(1,tries):.0%} kept)", flush=True)
    rng.shuffle(rows)
    json.dump(rows, open(args.out, "w"))
    print(f"\nwrote {len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
