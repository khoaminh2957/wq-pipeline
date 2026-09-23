#!/usr/bin/env python3
"""third_field_sweep.py — STAGE-3 generator for the ALPHA_PIPELINE v7 funnel.

Conditional escalation (Khoa 2026-07-17): when the TOP-9 stage-2 seeds contain NO
zero-fail alpha, each TOP-9 seed is escalated by adding a THIRD field from the SAME
dataset via a structure that DIFFERS from the seed's, swept over 180 configs
(9 x 180 = 1620 sims -> TOP-27 via rank_gates).

This tool GENERALIZES second_field_sweep: a stage-2 seed is a 2-field expression
`seed_structure(t1(field1), t2(field2))`; here we combine that seed with a 3rd field
`t3(field3)` under `structure3` (multiply / if_else / divide), reusing that module's
transform grammar, SIGN 50/50 axis, config axes (neutralization / pasteurization /
nanHandling / unitHandling / truncation / decay) and coprime-stride sampler. No new
API client — this module is pure like its parent.

  full = [SIGN] structure3( <seed> , t3(field3) [, structure3-enum-param] )
  seed = seed_structure( t1(field1), t2(field2) )        # canonical enum param

Enforced: field3 same dataset as field1/field2 (shared id prefix — S10-21), field3
!= field1/field2, field3 is a MATRIX field (catalog type), structure3 != the seed's
structure, and the emitted formula is NEVER a plain weighted sum (reuse _WSUM guard).
Output rows match the resim_targets.json schema so validate_targets.py passes.

Deterministic: same inputs -> byte-identical output (no RNG).
"""
from __future__ import annotations
import argparse, json, math, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Reuse the stage-2 grammar/axes/sampler wholesale — do NOT duplicate any of it.
from tools.funnel.second_field_sweep import (  # noqa: E402
    STRUCTURES, SIGN, DECAY, TRUNC, PASTEUR, UNIT, NANH, NEUT_BY_REGION,
    transforms, cond_transforms, _WSUM, _mixed_radix, _dataset_prefix, STRIDE_PRIME,
)
# Field-type catalog (id -> {"type": MATRIX/VECTOR/GROUP/...}) — local files only.
from tools.funnel.logic_check import FIELDS  # noqa: E402


def generate(field1: str, field2: str, field3: str, structure3: str, region: str,
             universe: str, delay: int, seed_structure: str, n: int = 180,
             label: str = "stage3") -> list[dict]:
    if structure3 not in STRUCTURES:
        raise ValueError(f"unknown structure3 {structure3!r}; options={list(STRUCTURES)}")
    if seed_structure not in STRUCTURES:
        raise ValueError(f"unknown seed_structure {seed_structure!r}; options={list(STRUCTURES)}")
    # structure3 must add a NEW interaction shape vs the seed — EXCEPT multiply, where
    # multiply(seed, t3(f3)) is a genuine 3-WAY product: richer than the 2-way seed (not a
    # structural duplicate) and it PRESERVES all three legs' magnitudes. (Khoa 2026-07-17: the
    # if_else form collapsed the seed to E·sign(seed), discarding 540 sims of seed tuning; the
    # 3-way multiply is the information-preserving 3rd-field move — logic_operators.md D2/law 6.)
    if structure3 == seed_structure and structure3 != "multiply":
        raise ValueError(f"structure3 must DIFFER from the seed structure {seed_structure!r} "
                         f"(except multiply → genuine 3-way product)")
    if region not in NEUT_BY_REGION:
        raise ValueError(f"no neutralization list for region {region!r}")
    if len({field1, field2, field3}) != 3:
        raise ValueError(f"field1/field2/field3 must be three distinct fields: "
                         f"{field1!r}, {field2!r}, {field3!r}")
    prefixes = {_dataset_prefix(f) for f in (field1, field2, field3)}
    if len(prefixes) != 1:
        raise ValueError(f"all three fields must be from the SAME dataset; prefixes={prefixes}")
    t3type = (FIELDS.get(field3) or {}).get("type")
    if t3type != "MATRIX":
        raise ValueError(f"field3 {field3!r} must be a MATRIX field (catalog type={t3type!r})")

    seed_spec = STRUCTURES[seed_structure]
    out_spec = STRUCTURES[structure3]
    # seed side: reuse the stage-2 build; zero-centered cond pool when the seed is if_else
    f1t = cond_transforms(field1) if seed_spec.get("zero_centered_cond") else transforms(field1)
    f2t = transforms(field2)
    f3t = transforms(field3)
    seed_param = seed_spec["params"][0]           # canonical enum (multiply->filter=false; else None)

    neut = NEUT_BY_REGION[region]
    axes = [f1t, f2t, f3t, out_spec["params"], neut, DECAY, TRUNC, PASTEUR, UNIT, NANH, SIGN]
    radices = [len(a) for a in axes]
    total = math.prod(radices)
    if total < n:
        raise ValueError(f"axis space {total} < requested {n}")
    if math.gcd(STRIDE_PRIME, total) != 1:
        raise AssertionError("stride not coprime to axis space")

    rows, seen = [], set()
    i = 0
    while len(rows) < n:
        idx = (i * STRIDE_PRIME) % total
        i += 1
        d = _mixed_radix(idx, radices)
        seed = seed_spec["build"](f1t[d[0]], f2t[d[1]], seed_param)
        # if_else compares its condition against 0: the seed is a compound signal
        # (a multiply of ranks is positive-cornered -> greater(.,0) degenerate), so
        # zero-center it before use as the condition (v7.1 must-fix, mirrored).
        left = f"zscore({seed})" if structure3 == "if_else" else seed
        core = out_spec["build"](left, f3t[d[2]], out_spec["params"][d[3]])
        formula = SIGN[d[10]] + core
        settings = {
            "instrumentType": "EQUITY",
            "region": region,
            "universe": universe,
            "delay": delay,
            "decay": DECAY[d[5]],
            "neutralization": neut[d[4]],
            "truncation": TRUNC[d[6]],
            "pasteurization": PASTEUR[d[7]],
            "unitHandling": UNIT[d[8]],
            "nanHandling": NANH[d[9]],
            "language": "FASTEXPR",
            "visualization": False,
        }
        k = (re.sub(r"\s+", "", formula), settings["region"], settings["universe"],
             settings["delay"], settings["neutralization"], settings["decay"],
             settings["truncation"], settings["pasteurization"],
             settings["unitHandling"], settings["nanHandling"])
        if k in seen:
            continue
        seen.add(k)
        if _WSUM.match(formula):
            raise AssertionError(f"produced a weighted-sum structure: {formula}")
        rid = f"s3_{structure3}_{len(rows):03d}"
        rows.append({"id": rid, "old_id": rid, "formula": formula,
                     "label": label, "settings": settings})
    return rows


def _cli():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--field1", required=True, help="seed field 1 id")
    ap.add_argument("--field2", required=True, help="seed field 2 id (same dataset)")
    ap.add_argument("--field3", required=True, help="chosen 3rd field id (same dataset, MATRIX)")
    ap.add_argument("--structure3", required=True, choices=list(STRUCTURES))
    ap.add_argument("--seed-structure", required=True, choices=list(STRUCTURES),
                    help="the stage-2 seed's structure (structure3 must differ)")
    ap.add_argument("--region", required=True)
    ap.add_argument("--universe", required=True)
    ap.add_argument("--delay", type=int, required=True)
    ap.add_argument("--n", type=int, default=180)
    ap.add_argument("--label", default="stage3")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = generate(a.field1, a.field2, a.field3, a.structure3, a.region, a.universe,
                    a.delay, a.seed_structure, a.n, a.label)
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1)
    print(f"wrote {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    _cli()
