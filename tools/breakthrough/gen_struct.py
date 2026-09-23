#!/usr/bin/env python3
"""Generate alphas across a CONTROLLED grid of structures, to find out which shape actually wins.

The pipeline has been emitting one grammar all session and never compared it to anything. Mining
924 platform alphas (tools/structure_mine.py) showed it is not the best one available:

    ADDITIVE+oneZ+decay                            16 alphas   68.8% clear every gate
    INTERACT+perlegZ+backfill                      24          41.7%
    ADDITIVE+oneZ+decay+power   <- what we emit    94          35.1%
    ADDITIVE+oneZ+backfill+groupneut+decay+power  323           0.0%

The last row is the important one: 323 alphas stacking every operator produced NOTHING. More
machinery is not more signal.

So this sweeps five binary axes over the SAME field pools, so a difference in outcome is a
difference in structure and not in dataset:

    combine    ADDITIVE  (sum of independent +-rank legs)
               INTERACT  (rank(LEVEL) x rank(ts_delta(LEVEL)) -- a level times its own change)
    norm       oneZ      (one zscore at the very end)
               perlegZ   (zscore each leg before weighting)
    power      signed_power(...) on/off
    backfill   ts_backfill(field, 5) on/off
    carrier    the price-volume carrier on/off

INTERACT is the one with a real economic reading: a level only matters when it is MOVING, so
multiplying rank(level) by rank(change) fires only when both agree, instead of letting a stale
level contribute forever the way a summed leg does.

  python3 tools/breakthrough/gen_struct.py --out pool.json --total 9600
"""
import argparse, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "breakthrough"))
import gen_pyramid as GP                                            # noqa: E402

CARRIER = GP.CARRIER
NEUTS = ["INDUSTRY", "SUBINDUSTRY", "STATISTICAL"]
DECAYS = [4, 6, 14]
TRUNCS = [0.015, 0.02, 0.05]
WINDOWS = [20, 50]
POWERS = [1.5, 2.5]
DELTA_W = [1, 5, 10]


def leg(fid, ty, rng, interact, backfill):
    base = f"vec_avg({fid})" if ty == "VECTOR" else fid
    if backfill:
        base = f"ts_backfill({base}, 5)"
    if interact:
        # LEVEL x its own CHANGE: fires only when the level is both extreme and moving.
        d = rng.choice(DELTA_W)
        inner = f"multiply(rank({base}), rank(ts_delta({base}, {d})))"
    else:
        op = rng.choice(["plain", "delta", "avdiff"])
        if op == "delta":
            inner = f"rank(ts_delta({base}, {rng.choice(DELTA_W)}))"
        elif op == "avdiff":
            inner = f"rank(ts_av_diff({base}, {rng.choice([5, 10, 20])}))"
        else:
            inner = f"rank({base})"
    sign = "-" if rng.random() < 0.5 else ""
    return f"{sign}{inner}"


def build_one(rng, pool, combine, norm, power, backfill, carrier):
    k = rng.randint(4, 8)
    head = pool[: max(k, len(pool) // 2)]
    if len(head) < k:
        return None
    picked = rng.sample(head, k)
    mags = GP.magnitudes(k + (2 if carrier else 0))
    legs = list(CARRIER) if carrier else []
    ms = mags[2:] if carrier else mags
    for (uc, fid, ty), m in zip(picked, ms):
        L = leg(fid, ty, rng, combine == "INTERACT", backfill)
        legs.append(f"multiply(zscore({L}), {m})" if norm == "perlegZ"
                    else f"multiply({L}, {m})")
    body = "add(" + ", ".join(legs) + ", filter=true)"
    w = rng.choice(WINDOWS)
    if norm == "oneZ":
        body = f"zscore(ts_decay_linear({body}, {w}))"
    else:
        body = f"ts_decay_linear({body}, {w})"
    if power:
        body = f"signed_power({body}, {rng.choice(POWERS)})"
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--total", type=int, default=9600)
    ap.add_argument("--tag", default="SX")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--proven", action="store_true",
                    help="only the axes still in question (see the grid comment)")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    fields = GP.load_fields()
    # Only cells that still need alphas — a structure win on an unlocked cell buys nothing.
    full = GP.full_cells()
    want = [(cn, sn) for (cn, sn), pool in fields.items()
            if GP.cell_weight(cn, sn, full=full) > 0 and len(pool) >= 8]
    if not want:
        want = [k for k, v in fields.items() if len(v) >= 8]
    # --proven restricts the sweep to the axes still in question. Measured over 1,567 rows on
    # 2026-08-02, with the grid balanced across all seven cells so the comparison is not a cell mix:
    #   carrier   True 3.3% zero-fail | False 0/1650 across two experiments  -> settled
    #   norm      oneZ 3.6%           | perlegZ 0.5%                          -> settled
    #   power     off  3.1%           | on  1.9%     -- small, keep measuring
    #   backfill  off  2.7%           | on  2.3%     -- null, keep measuring
    #   combine   raw 2.2 vs 4.4% but WITHIN cell only +0.4-0.6pp             -- keep measuring
    # Re-running the settled two costs 3/4 of a hard 5000-sim day to re-derive a known answer.
    norms = ("oneZ",) if args.proven else ("oneZ", "perlegZ")
    carriers = (True,) if args.proven else (True, False)
    grid = [(c, n, p, b, ca)
            for c in ("ADDITIVE", "INTERACT")
            for n in norms
            for p in (True, False)
            for b in (True, False)
            for ca in carriers]
    per = max(40, args.total // len(grid))
    # Seed `seen` with every formula ALREADY staged in a targets file. preflight aborts a whole
    # round if it finds a single already-staged row, so a handful of collisions in a large pool is
    # not a rounding error -- 23 collisions in 4,800 rows works out to ~1 landmine per 200-row
    # round, i.e. nearly every round of the run aborted before simulating anything.
    rows, seen = [], set()
    import glob as _glob
    for _p in _glob.glob(str(ROOT / "state/**/*targets*.json"), recursive=True):
        try:
            _rr = json.load(open(_p))
        except Exception:
            continue
        if isinstance(_rr, list):
            for _r in _rr:
                if isinstance(_r, dict) and _r.get("formula"):
                    seen.add(_r["formula"])
    print(f"  excluding {len(seen)} formulas already staged in historical targets files")
    for gi, (c, n, p, b, ca) in enumerate(grid):
        made = 0
        tries = 0
        while made < per and tries < per * 60:
            tries += 1
            cn, sn = want[rng.randrange(len(want))]
            f = build_one(rng, fields[(cn, sn)], c, n, p, b, ca)
            if not f or f in seen:
                continue
            seen.add(f)
            oid = f"{args.tag}g{gi:02d}_{cn.replace(' ','')}_{made:04d}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(GP.SETTINGS_BASE, decay=rng.choice(DECAYS),
                                          neutralization=rng.choice(NEUTS),
                                          truncation=rng.choice(TRUNCS)),
                         "meta": {"skeleton": f"{c}+{n}" + ("+power" if p else "")
                                              + ("+backfill" if b else "")
                                              + ("+carrier" if ca else ""),
                                  "dataset": f"{cn}/{sn}", "mechanic": f"{cn}/{sn}",
                                  "combine": c, "norm": n, "power": p, "backfill": b,
                                  "carrier": ca, "category_target": cn,
                                  "universe": "TOP3000", "legs": 0,
                                  "neutralization": "", "decay": 0, "truncation": 0}})
            made += 1
        print(f"  {c:8} {n:7} power={p!s:5} backfill={b!s:5} carrier={ca!s:5} -> {made}")
    rng.shuffle(rows)          # same head-order collapse as gen_paircell -- see the note there
    json.dump(rows, open(args.out, "w"))
    print(f"\nwrote {len(rows)} rows across {len(grid)} structures (shuffled) -> {args.out}")


if __name__ == "__main__":
    main()
