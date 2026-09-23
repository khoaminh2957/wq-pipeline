#!/usr/bin/env python3
"""Generate alphas that fill TWO still-open pyramid cells with ONE submit.

The arithmetic that forces this design (measured, not assumed):

  * An alpha in 2 categories counts for BOTH; an alpha in 3 counts for NONE.
  * Every alpha built on the standard price-volume carrier necessarily joins Price Volume, and
    Price Volume has been full since the start -- confirmed 2026-08-02 when it moved 22 -> 26 on
    four carrier-based submits, exactly +1 each.

  carrier + one open cell   = {PV, A}     -> 2 categories, but PV is full  -> nets ONE cell
  carrier + two open cells  = {PV, A, B}  -> 3 categories                  -> nets NOTHING
  NO carrier + two open cells = {A, B}    -> 2 categories                  -> nets TWO cells

So a two-cell submit MUST be carrier-free. That looked closed: the SX experiment measured 0
zero-fail across ~1650 carrier-free rows (an observation; the reason is not established). But that was one ensemble design with its two PV legs
deleted, not evidence about carrier-free alphas in general -- scanning 914 USA-d1 alphas on the
platform found 35 with no Price Volume field at all, of which 2 clear every hard gate (5.7%,
against 9.3% for the PV-carried ones). Lower, not zero.

The catch this must avoid: a field's category is NOT its dataset name. `fnd65_us5000_cusip_rba`
lives in dataset `fundamental65` and resolves to category **Model** -- which is full. Both
carrier-free passers in the bank turned out to be Other+Model for exactly that reason, so they
still net one cell. Categories here come from GP.load_fields(), which is keyed on the platform's
own category, never on the dataset name.

  python3 tools/breakthrough/gen_paircell.py --out pool.json --total 2400
"""
import argparse, itertools, json, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "breakthrough"))
sys.path.insert(0, str(ROOT / "tools"))
import gen_pyramid as GP                                            # noqa: E402
import gen_struct as GS                                             # noqa: E402
import submit_alphas as SA                                          # noqa: E402


def open_cells():
    """Categories still under 3, including today's submits the counter has not credited."""
    c, _ = SA._cell_counts(SA.session(), "USA", 1)
    c = dict(c or {})
    for k, n in SA._submitted_today_by_cell(c).items():
        c[k] = c.get(k, 0) + n
    return {k: SA.TRIPLE - v for k, v in c.items() if v < SA.TRIPLE}


def build_pair(rng, pool_a, pool_b, combine, power, backfill):
    """One carrier-free ensemble drawing legs from BOTH cells, so it joins both categories.

    Both sides get at least two legs. A single token from one cell would still register the
    category, but a category that contributes almost no signal is how an alpha ends up carrying a
    membership it cannot justify -- and the cell gate counts memberships, not intent."""
    ka = rng.randint(3, 5)
    kb = rng.randint(3, 5)
    if len(pool_a) < ka or len(pool_b) < kb:
        return None
    picked = rng.sample(pool_a[: max(ka, len(pool_a) // 2)], ka) + \
        rng.sample(pool_b[: max(kb, len(pool_b) // 2)], kb)
    mags = GP.magnitudes(ka + kb)
    legs = []
    for (uc, fid, ty), m in zip(picked, mags):
        L = GS.leg(fid, ty, rng, combine == "INTERACT", backfill)
        legs.append(f"multiply({L}, {m})")
    body = "add(" + ", ".join(legs) + ", filter=true)"
    body = f"zscore(ts_decay_linear({body}, {rng.choice(GS.WINDOWS)}))"   # oneZ: measured 3.6% vs 0.5%
    if power:
        body = f"signed_power({body}, {rng.choice(GS.POWERS)})"
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--total", type=int, default=2400)
    ap.add_argument("--tag", default="PC")
    ap.add_argument("--seed", type=int, default=23)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    need = open_cells()
    fields = GP.load_fields()
    by_cell = {}
    for (cn, sn), pool in fields.items():
        if cn in need and len(pool) >= 6:
            by_cell.setdefault(cn, []).extend(pool)
    cells = sorted(by_cell)
    print(f"open cells with a usable field pool: "
          f"{ {c: f'needs {need[c]}, {len(by_cell[c])} fields' for c in cells} }")
    pairs = list(itertools.combinations(cells, 2))
    if not pairs:
        raise SystemExit("fewer than two open cells have field pools -- nothing to pair")
    # Cheapest first: a pair of cells each needing 2 closes both in two submits; a pair of empty
    # cells needs three each. Weight by 1/(a+b) so the near-complete pairs get the most rows.
    wts = [1.0 / (need[a] + need[b]) for a, b in pairs]
    tot_w = sum(wts)

    seen = set()
    for p in ROOT.glob("state/**/*targets*.json"):
        try:
            rr = json.load(open(p))
        except Exception:
            continue
        if isinstance(rr, list):
            for r in rr:
                if isinstance(r, dict) and r.get("formula"):
                    seen.add(r["formula"])
    print(f"excluding {len(seen)} formulas already staged")

    rows = []
    for (a, b), w in zip(pairs, wts):
        want = max(30, int(args.total * w / tot_w))
        made = tries = 0
        while made < want and tries < want * 60:
            tries += 1
            # Draw the axis values ONCE and record the ones actually used. Passing randomised
            # combine/power/backfill into build_pair while writing fixed values into `meta` makes
            # the metadata describe an alpha that was not built: score_axes learns per axis VALUE
            # off that label, so every signed_power row would have taught the loop about
            # power=False and the whole axis would be measured backwards.
            combine = rng.choice(["ADDITIVE", "INTERACT"])
            power = rng.random() < 0.5
            backfill = rng.random() < 0.5
            f = build_pair(rng, by_cell[a], by_cell[b], combine, power, backfill)
            if not f or f in seen:
                continue
            seen.add(f)
            oid = f"{args.tag}_{a[:4]}{b[:4]}_{made:04d}".replace(" ", "")
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(GP.SETTINGS_BASE, decay=rng.choice(GS.DECAYS),
                                          neutralization=rng.choice(GS.NEUTS),
                                          truncation=rng.choice(GS.TRUNCS)),
                         "meta": {"skeleton": f"PAIRCELL+{combine}+oneZ"
                                              + ("+power" if power else "")
                                              + ("+backfill" if backfill else ""),
                                  "dataset": f"{a}+{b}",
                                  "mechanic": f"{a}+{b}", "combine": combine, "norm": "oneZ",
                                  "power": power, "backfill": backfill, "carrier": False,
                                  "category_target": a, "category_pair": b,
                                  "universe": "TOP3000", "legs": 0,
                                  "neutralization": "", "decay": 0, "truncation": 0}})
            made += 1
        print(f"  {a:16} + {b:16} needs {need[a]}+{need[b]} -> {made} rows")
    # SHUFFLE before writing. Rows are generated pair-by-pair, so all Macro pairs land in the
    # first 660 of 2,380 -- and on a brand-new pool every dataset axis value is unscored, so
    # pick_slice's ranking ties and its stable sort falls back to file order. Round 1 of the
    # 2026-08-02 run drew 328 rows that were 100% Macro, the thinnest field pool of the eight, and
    # the 0/228 result read as "carrier-free is dead" when it only measured one corner.
    rng.shuffle(rows)
    json.dump(rows, open(args.out, "w"))
    print(f"\nwrote {len(rows)} carrier-free two-cell rows (shuffled) -> {args.out}")


if __name__ == "__main__":
    main()
