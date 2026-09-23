#!/usr/bin/env python3
"""Bind the literature-derived designs to real field ids and emit a simulatable pool.

The designs in state/novel_designs.json carry <FIELD_n> placeholders. Filling them is not
cosmetic — a design's whole claim rests on the leg being non-monotone, or a second moment, or an
event-clock, and a placeholder filled with the wrong KIND of field silently converts the design
back into the recipe it was meant to differ from.

So binding is by ROLE, read from each field's own description (tools/field_eda.classify), and a
design that asks for a VECTOR field gets a VECTOR field or it is skipped rather than fudged.

Two things this deliberately does NOT do:

  * It does not touch multi-statement designs (those containing ';').

    THE PREMISE FOR THIS WAS FALSE, corrected 2026-08-10. The original text said "Zero of 9,984
    alphas on this account and zero of 65k journal rows have ever used one". Re-measured:

        2,532 of 9,984 alphas (25.4%) carry a multi-statement formula, and 9 of those are
        ACTIVE/SUBMITTED on the live account.

    So the syntax is not untested — it is in production, including in alphas that passed
    submission. The 40 designs held back here were withheld on a number that does not reproduce.
    Whether the 64-operator ceiling counts literal text or the inlined DAG is still UNKNOWN and is
    worth a probe, but "nobody has ever used this" was never true.
  * It does not silently drop a design it cannot fill. Every skip is printed with its reason,
    because a quietly shrunken pool reads as "the idea did not work".

  python3 tools/instantiate_designs.py --region USA --delay 1 --per-design 12
"""
import argparse, collections, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import field_eda
import opcheck                                                       # noqa: E402

RAW_PV = {"open", "close", "high", "low", "vwap", "cap"}               # volume/returns/adv20 banned

SETTINGS = {"instrumentType": "EQUITY", "pasteurization": "ON", "unitHandling": "VERIFY",
            "nanHandling": "OFF", "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

# The recipe measured on the joint objective (zero-fail AND prod<0.70), HARNESS_V2 §14.
NEUTS = ["STATISTICAL", "STATISTICAL", "STATISTICAL", "INDUSTRY"]
DECAYS = [6, 10, 14]
TRUNCS = [0.015, 0.02, 0.05]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="USA")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--universe", default="TOP3000")
    ap.add_argument("--per-design", type=int, default=12)
    ap.add_argument("--designs", default="state/novel_designs.json")
    ap.add_argument("--out", default="state/autoloop/pool_novel.json")
    ap.add_argument("--multi-out", default="state/autoloop/pool_novel_multi.json")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    ops = {o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json"))}
    banned = set(json.load(open(ROOT / "state/banned_fields.json")).get("banned_fields") or [])
    for v in (json.load(open(ROOT / "state/banned_fields.json")).get("by_alpha") or {}).values():
        banned |= set(v)

    cat = field_eda.load_catalogue(args.region, args.delay)
    pool_by_role = collections.defaultdict(list)
    vectors = []
    for fid, f in cat.items():
        if fid in banned or f["type"] == "GROUP" or field_eda.meaningless(f["desc"]):
            continue
        if not isinstance(f["coverage"], (int, float)) or f["coverage"] <= 0.05:
            continue
        role, _unit = field_eda.classify(f["desc"])
        pool_by_role[role].append(fid)
        if f["type"] == "VECTOR":
            vectors.append(fid)
    allf = [x for v in pool_by_role.values() for x in v]
    matrices = [x for x in allf if x not in set(vectors)]
    print(f"{args.region} d{args.delay}: {len(allf)} usable fields "
          f"({len(vectors)} VECTOR) across roles "
          f"{ {k: len(v) for k, v in sorted(pool_by_role.items(), key=lambda x: -len(x[1]))} }")

    designs = json.load(open(ROOT / args.designs))
    rows, multi, skipped = [], [], []
    for d in designs:
        f = d["formula"]
        if ";" in f:
            multi.append(d)
            continue
        called = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", f))
        unk = sorted(c for c in called if c not in ops)
        if unk:
            skipped.append((d["name"], f"unknown operator {unk}"))
            continue
        holes = sorted(set(re.findall(r"<([A-Z_]+\d*)>", f)))
        need_vec = [h for h in holes if "VECTOR" in h]
        n_vec_slots = len(re.findall(r"vec_(?:avg|sum|max|min|stddev|range|count)\s*\(\s*<", f))
        if n_vec_slots and len(vectors) < n_vec_slots:
            skipped.append((d["name"], f"needs {n_vec_slots} VECTOR fields, have {len(vectors)}"))
            continue
        # A design with no placeholders has exactly ONE formula, so asking for 12 instantiations
        # produces 12 identical rows that differ only by a randomly drawn setting -- and whenever
        # two draws collide the batch precheck rejects the whole launch as duplicates. That is how
        # 312 rows made 0 POSTs. Enumerate the settings grid deterministically instead of sampling
        # it, and cap the count at the number of distinct settings the grid can supply.
        grid = [(nt, dc, tr) for nt in dict.fromkeys(NEUTS) for dc in DECAYS for tr in TRUNCS]
        rng.shuffle(grid)
        want = args.per_design if holes else min(args.per_design, len(grid))
        made = 0
        for i in range(want):
            g = f
            used = set()
            ok = True
            for h in holes:
                # A VECTOR field is only legal where the design already wraps the hole in a vec_*
                # reduction; anywhere else it is an ILLEGAL leg (logic_check blocks it) and the
                # design silently becomes something the author did not write. Decide from the
                # SURROUNDING TEXT, not from the placeholder's name -- the author's naming is a
                # hint, the expression is the contract.
                pos = f.find(f"<{h}>")
                ctx = f[max(0, pos - 40):pos]
                in_vec = bool(re.search(r"vec_(avg|sum|max|min|stddev|range|count)\s*\([^()]*$", ctx))
                src = vectors if in_vec else matrices
                cand = [x for x in src if x not in used]
                if not cand:
                    ok = False
                    break
                pick = rng.choice(cand)
                used.add(pick)
                g = g.replace(f"<{h}>", pick)
            if not ok:
                break
            if opcheck.operator_count(g) > opcheck.CEILING:
                continue
            # seed in the id: see gen_shape.py — same collision, same silent skip.
            oid = f"NV{args.seed}{d['family'][:3].upper()}_{re.sub(r'[^A-Za-z0-9]', '', d['name'])[:14]}_{i:02d}"
            rows.append({"old_id": oid, "id": oid, "formula": g,
                         "settings": dict(SETTINGS, region=args.region, delay=args.delay,
                                          universe=args.universe,
                                          neutralization=grid[i % len(grid)][0],
                                          decay=grid[i % len(grid)][1],
                                          truncation=grid[i % len(grid)][2]),
                         "meta": {"design": d["name"][:70], "family": d["family"][:40],
                                  "kind": "novel", "ops": g.count("(")}})
            made += 1
        if made == 0:
            skipped.append((d["name"], "every instantiation exceeded 62 operators"))

    json.dump(rows, open(ROOT / args.out, "w"), indent=1)
    json.dump(multi, open(ROOT / args.multi_out, "w"), indent=1)
    print(f"\n{len(rows)} rows from {len(designs) - len(multi) - len(skipped)} single-statement designs "
          f"-> {args.out}")
    print(f"{len(multi)} MULTI-STATEMENT designs held back -> {args.multi_out} "
          f"(the ';' form has never been simulated on this account)")
    if skipped:
        print(f"\n{len(skipped)} designs skipped, with reasons:")
        for n, why in skipped:
            print(f"   {n[:58]:58} {why}")


if __name__ == "__main__":
    raise SystemExit(main())
