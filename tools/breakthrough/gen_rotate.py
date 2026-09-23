#!/usr/bin/env python3
"""Two-category alphas from a RULE, with no field held fixed.

Khoa, 2026-08-02: *"tìm cấu trúc thoả được 2 categories 1 lúc và không cố định bất kì field nào
vì chỉ cần đủ 3 alpha là lại phải đổi cấu trúc"*.

Why fixing a field is fatal, in arithmetic rather than opinion. A pyramid cell closes at 3 alphas.
Submitting one alpha raises every sibling that shares its signal to ~self-correlation, so alphas
built on the same anchor field are ONE family and yield ONE submission however many clear the
gates. A generator that hardcodes its anchor can therefore never fill a cell — it can only ever
contribute a single alpha to it. `gen_anchor.py` has exactly that defect: its 600 NEWSANCHOR rows
all pivot on `all_sessions_vwap`, so they are worth one submit between them. That run is still
useful as a MECHANISM test (does a non-price anchor supply amplitude at all?) and useless as a
source of alphas.

So the structure here is a rule and the fields are arguments:

    anchor  = a fast transform of ANY high-coverage field of cell A
    legs    = role-matched signals from fields of cell B
    result  = exactly {A, B} -> two categories, both credited

and both the anchor field AND the leg fields rotate, so consecutive alphas aimed at the same cell
pair are different families by construction. Every row records `anchor_field`, so family
independence is auditable before a single submit is spent.

The anchor forms all take ONE field, which is what makes them field-agnostic — the price carrier's
`divide(close, open)` needs two related price series, and most cells have no such pair:

    ratio_lag   -rank(divide(X, ts_delay(X, 1)))     today against yesterday
    delta       -rank(ts_delta(X, 1))                 the daily change itself
    deviation   -rank(ts_zscore(X, 20))               distance from its own recent mean
    pair        -rank(divide(X, Y))                   two fields of the same cell, when available

Nothing here asserts WHY an anchor helps; that is O1b in HYPOTHESES.md and is still open. This
file only ensures that if an anchor does help, the result is renewable rather than a single alpha.

  python3 tools/breakthrough/gen_rotate.py --out pool.json --total 3000
"""
import argparse, collections, itertools, json, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "breakthrough"))
sys.path.insert(0, str(ROOT / "tools"))
import gen_pyramid as GP                                            # noqa: E402
import gen_diverse as GD                                            # noqa: E402

OP_LIMIT = 60
# The PV legs H10 measured standalone (2026-08-05), keeping only those at or above the pair every
# pool has used. Median |sharpe| in comment; the four legs below close_vwap cleared 1.58 on 0/12.
PV_LEGS = [("close_delta", "-rank(ts_delta(close, 1))"),          # 1.215
           ("open_vwap",   "-rank(divide(open, vwap))"),          # 1.180
           ("close_lag",   "-rank(divide(close, ts_delay(close, 1)))"),   # 1.025
           ("close_open",  "-rank(divide(close, open))"),         # 1.005
           ("close_vwap",  "-rank(divide(close, vwap))")]         # 0.980
ANCHOR_FORMS = ["ratio_lag", "delta", "deviation", "pair"]
MIN_COVERAGE = 0.85


def anchor_expr(rng, form, x, ty_x, y=None, ty_y=None):
    """One anchor leg from ONE field (or two of the same cell for `pair`)."""
    fx = f"vec_avg({x})" if ty_x == "VECTOR" else x
    if form == "pair" and y:
        fy = f"vec_avg({y})" if ty_y == "VECTOR" else y
        return f"-rank(divide({fx}, {fy}))"
    if form == "delta":
        return f"-rank(ts_delta({fx}, {rng.choice([1, 2, 5])}))"
    if form == "deviation":
        return f"-rank(ts_zscore({fx}, {rng.choice([10, 20, 60])}))"
    return f"-rank(divide({fx}, ts_delay({fx}, {rng.choice([1, 2, 5])})))"


def load_anchor_pool():
    """cell -> [(coverage, field, role, type)] for fields usable as an anchor.

    Written by tools/breakthrough/anchor_candidates (coverage resolved per field from the
    platform). Falls back to the cached fieldmap so this still runs before that scan finishes."""
    p = ROOT / "state/anchor_candidates.json"
    if p.exists():
        try:
            d = json.load(open(p))
            if d:
                return {k: [tuple(x) for x in v] for k, v in d.items()}
        except Exception:
            pass
    fm = json.load(open(ROOT / "state/fieldmap.json"))
    roles = GD.roles()
    out = collections.defaultdict(list)
    for fid, v in fm.items():
        v = v or {}
        cov, cat = v.get("coverage"), v.get("category")
        if not cat or not isinstance(cov, (int, float)) or cov < MIN_COVERAGE:
            continue
        if (roles.get(fid) or {}).get("label") == "META":
            continue
        out[cat].append((round(cov, 3), fid, (roles.get(fid) or {}).get("label"), v.get("type")))
    return dict(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--total", type=int, default=3000)
    ap.add_argument("--tag", default="RT")
    ap.add_argument("--seed", type=int, default=71)
    ap.add_argument("--min-anchors", type=int, default=3,
                    help="a cell needs at least this many DISTINCT anchor fields to be usable as "
                         "an anchor side — below it the pair cannot yield 3 independent alphas")
    # H7 (REFUTED 2026-08-02) is the reason these two exist. A non-PV anchor built from three
    # full-coverage news12 vwap fields added the PV carrier's exact daily churn (turnover 0.1079 vs
    # 0.1080) and none of its return (0/146 over the 1.58 bar, median |sharpe| 0.220 against 0.710).
    # Coverage was verified before that run and dispersion never was. So a rotating-anchor pool must
    # be screened before it is scaled: few enough anchors that each gets a readable sample, and a
    # PV-carrier control in the SAME cells so the comparison does not rest on a remembered number.
    ap.add_argument("--anchors-per-cell", type=int, default=0,
                    help="probe mode: keep only this many anchor fields per cell, so each anchor "
                         "gets enough rows to be judged separately (0 = use all)")
    ap.add_argument("--control", type=int, default=0,
                    help="probe mode: also emit this many PVCARRIER rows over the same leg cells")
    ap.add_argument("--carrier-mix", action="store_true",
                    help="H11: draw the carrier from the PV legs H10 measured, instead of the fixed "
                         "close/open + close/vwap pair every pool has used")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    R = GD.roles()

    fields = GP.load_fields()
    full = GP.full_cells()                       # raises if the counter is unreadable
    anchors = load_anchor_pool()

    legs_by_cell = collections.defaultdict(list)
    for (cn, sn), pool in fields.items():
        if cn in full:
            continue
        for uc, fid, ty in pool:
            if (R.get(fid) or {}).get("label") != "META":
                legs_by_cell[cn].append((uc, fid, ty))

    anchor_cells = {c: [a for a in v if c not in full]
                    for c, v in anchors.items() if c not in full}
    anchor_cells = {c: v for c, v in anchor_cells.items() if len(v) >= args.min_anchors}
    if args.anchors_per_cell:
        anchor_cells = {c: sorted(v, reverse=True)[: args.anchors_per_cell]
                        for c, v in anchor_cells.items()}
    print(f"cells usable as the ANCHOR side (>= {args.min_anchors} distinct anchor fields):")
    for c, v in sorted(anchor_cells.items(), key=lambda kv: -len(kv[1])):
        print(f"   {c:16} {len(v):4} anchor fields")
    if not anchor_cells:
        raise SystemExit("no open cell has enough high-coverage fields to anchor with")

    pairs = [(a, b) for a in anchor_cells for b in legs_by_cell
             if b != a and len(legs_by_cell[b]) >= 8]
    print(f"\n{len(pairs)} (anchor cell, leg cell) pairs available")

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

    per = max(30, args.total // max(1, len(pairs)))
    rows, used_anchor = [], collections.Counter()
    for a, b in pairs:
        av, lv = anchor_cells[a], legs_by_cell[b]
        made = tries = 0
        while made < per and tries < per * 60:
            tries += 1
            # ROTATE the anchor field. Cycling by how often each has been used keeps consecutive
            # alphas for this pair on different anchors, which is what makes them different
            # families rather than one family with three spellings.
            cov, af, arole, aty = min(av, key=lambda x: (used_anchor[x[1]], rng.random()))
            form = rng.choice(ANCHOR_FORMS)
            y = yty = None
            if form == "pair":
                cand = [x for x in av if x[1] != af]
                if not cand:
                    form = "ratio_lag"
                else:
                    _, y, _, yty = rng.choice(cand)
            anc = anchor_expr(rng, form, af, aty, y, yty)

            k = rng.randint(4, 7)
            head = lv[: max(k, len(lv) // 2)]
            if len(head) < k:
                break
            mags = GP.magnitudes(k + 2)
            legs = [anc]
            recipes = []
            for (uc, fid, ty), m in zip(rng.sample(head, k), mags[2:]):
                info = R.get(fid) or {}
                L, r = GD.leg(rng, fid, ty, info.get("label", "LEVEL"), info)
                recipes.append(r)
                legs.append(f"multiply({L}, {m})")
            body = "add(" + ", ".join(legs) + ", filter=true)"
            f = f"zscore(ts_decay_linear({body}, {rng.choice([10, 20, 50])}))"
            if f in seen or GD.op_count(f) > OP_LIMIT:
                continue
            seen.add(f)
            used_anchor[af] += 1
            oid = f"{args.tag}_{a.replace(' ', '')[:4]}{b.replace(' ', '')[:4]}_{made:04d}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(GP.SETTINGS_BASE, decay=rng.choice([4, 6, 10]),
                                          neutralization=rng.choice(["INDUSTRY", "SUBINDUSTRY",
                                                                     "STATISTICAL"]),
                                          truncation=rng.choice([0.01, 0.02, 0.04])),
                         "meta": {"skeleton": f"ROTATE+{form}", "dataset": f"{a}+{b}",
                                  "mechanic": f"{a}+{b}", "anchor_cell": a, "leg_cell": b,
                                  "anchor_field": af, "anchor_form": form,
                                  "legs_used": "|".join(sorted(set(recipes))),
                                  "carrier": False, "combine": "ADDITIVE", "norm": "oneZ",
                                  "power": False, "backfill": "backfilled" in recipes,
                                  "category_target": a, "category_pair": b,
                                  "universe": "TOP3000", "legs": k,
                                  "neutralization": "", "decay": 0, "truncation": 0}})
            made += 1
        print(f"  {a:14} + {b:14} -> {made:4} rows, "
              f"{len({r['meta']['anchor_field'] for r in rows if r['meta']['dataset'] == f'{a}+{b}'})}"
              f" distinct anchors", flush=True)
    # The control. Same skeleton, same leg cells, same weights -- the ONLY difference is that the
    # anchor is the PV carrier instead of a rotated open-cell field, which is the one thing the
    # probe is asking about.
    made = tries = 0
    ctl_cells = sorted({b for _, b in pairs})
    while made < args.control and tries < max(1, args.control) * 60:
        tries += 1
        b = ctl_cells[rng.randrange(len(ctl_cells))]
        lv = legs_by_cell[b]
        k = rng.randint(4, 7)
        head = lv[: max(k, len(lv) // 2)]
        if len(head) < k:
            continue
        mags = GP.magnitudes(k + 2)
        # H11. The fixed pair is `close/open` + `close/vwap`, which H10 ranked 4th and 5th of the
        # nine PV legs it measured standalone (median |sharpe| 1.005 and 0.980, against close_delta
        # 1.215, open_vwap 1.180, close_lag 1.025). `close/open` is also the textbook reversal every
        # competitor runs, and 90.2% of this pipeline's zero-fails die on prod-correlation rather
        # than on any quality gate. Rotating the carrier tests whether the crowding lives there.
        # Only legs H10 measured ABOVE the fixed pair are used -- the three below it
        # (`vwap_zs` 0.590, `close_low` 0.485, `high_low` 0.215, `close_high` 0.130) cleared the
        # 1.58 bar on 0 of 12 variants each and would trade crowding for no signal.
        if args.carrier_mix:
            pair = rng.sample(PV_LEGS, 2)
            legs = [pair[0][1], f"multiply({pair[1][1]}, 0.6)"]
            cname = f"{pair[0][0]}+{pair[1][0]}"
        else:
            legs = list(GP.CARRIER)
            cname = "close_open+close_vwap"
        recipes = []
        for (uc, fid, ty), m in zip(rng.sample(head, k), mags[2:]):
            info = R.get(fid) or {}
            L, r = GD.leg(rng, fid, ty, info.get("label", "LEVEL"), info)
            recipes.append(r)
            legs.append(f"multiply({L}, {m})")
        f = (f"zscore(ts_decay_linear(add({', '.join(legs)}, filter=true), "
             f"{rng.choice([10, 20, 50])}))")
        if f in seen or GD.op_count(f) > OP_LIMIT:
            continue
        seen.add(f)
        oid = f"{args.tag}CTL_{b.replace(' ', '')[:8]}_{made:04d}"
        rows.append({"old_id": oid, "id": oid, "formula": f,
                     "settings": dict(GP.SETTINGS_BASE, decay=rng.choice([4, 6, 10]),
                                      neutralization=rng.choice(["INDUSTRY", "SUBINDUSTRY",
                                                                 "STATISTICAL"]),
                                      truncation=rng.choice([0.01, 0.02, 0.04])),
                     "meta": {"skeleton": "PVCARRIER+oneZ", "dataset": f"PriceVolume+{b}",
                              "mechanic": f"PVCARRIER/{b}", "anchor_cell": "Price Volume",
                              "leg_cell": b, "anchor_field": cname, "anchor_form": "control",
                              "legs_used": "|".join(sorted(set(recipes))), "carrier": True,
                              "combine": "ADDITIVE", "norm": "oneZ", "power": False,
                              "backfill": "backfilled" in recipes,
                              "category_target": b, "category_pair": "Price Volume",
                              "universe": "TOP3000", "legs": k,
                              "neutralization": "", "decay": 0, "truncation": 0}})
        made += 1
    if args.control:
        print(f"  {'CONTROL (PV carrier)':30} -> {made:4} rows over {len(ctl_cells)} leg cells")

    rng.shuffle(rows)
    json.dump(rows, open(args.out, "w"))
    print(f"\nwrote {len(rows)} rows -> {args.out}")
    print(f"  distinct anchor fields used: {len(used_anchor)}")
    print(f"  anchor forms: {dict(collections.Counter(r['meta']['anchor_form'] for r in rows))}")


if __name__ == "__main__":
    main()
