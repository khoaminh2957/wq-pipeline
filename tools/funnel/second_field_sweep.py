#!/usr/bin/env python3
"""second_field_sweep.py — STAGE-2 generator for the ALPHA_PIPELINE v7 funnel.

Given ONE top-5 root alpha (its root field + fixed region/universe/delay) and a
CHOSEN second field id from the SAME dataset plus a target STRUCTURE that DIFFERS
from the root's structure, mechanically emit 180 unique valid FASTEXPR config
variants that combine field1+field2 in that structure. (region, universe, delay)
are held fixed; everything else is swept: the per-field single-field transform
grammar, neutralization / pasteurization / nanHandling / unitHandling (ALL legal
values derived from fetched/rc/settings_options.json — S10-19/S10-16), truncation,
decay, and structure-level enum params (multiply filter=false/true per the FULL
documented signature multiply(x, y, ..., filter=false) — S10-18 / Khoa rule).

The SECOND-field CHOICE + STRUCTURE are decided upstream (the .md/LLM); this tool
does the deterministic 180-sweep only. Both fields MUST come from the SAME dataset
(enforced via shared field-id prefix — S10-21). Output rows match the
resim_targets.json schema ({id, old_id, formula, label, settings}) so
validate_targets.py passes and resim_bulk.py can run them as 10 multi-sims x 10.

Deterministic: same inputs -> byte-identical output every run (no RNG). Coverage
of every swept axis is guaranteed by a coprime-stride mixed-radix sampler.
"""
from __future__ import annotations
import argparse, json, math, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# ---- swept setting axes: ALL legal values derived from settings_options.json --
_CH = json.load(open(ROOT / "fetched/rc/settings_options.json"))["actions"]["POST"]["settings"]["children"]
NEUT_BY_REGION = {r: [c["value"] for c in v]
                  for r, v in _CH["neutralization"]["choices"]["instrumentType"]["EQUITY"]["region"].items()}
PASTEUR = [c["value"] for c in _CH["pasteurization"]["choices"]]
NANH = [c["value"] for c in _CH["nanHandling"]["choices"]]
UNIT = [c["value"] for c in _CH["unitHandling"]["choices"]]  # single legal value today; auto-expands

DECAY = [0, 4, 8, 16, 32, 64]                     # within settings range [0,512]
TRUNC = [0.0, 0.02, 0.05, 0.08, 0.1, 0.15]        # within settings range [0,1]
GROUPS = ["sector", "industry"]
LOOKBACK = {"short": 5, "mid": 22}

# ---- single-field transform grammar -----------------------------------------
def transforms(field: str) -> list[str]:
    """Ordered pool of single-field transform instances applied to `field`.
    Every operator is in the RC allowlist and every call uses the FULL documented
    signature; enum/bool params (winsorize std, ts_decay_linear dense,
    normalize useStd) are swept as variants. No degenerate self-args."""
    s, m = LOOKBACK["short"], LOOKBACK["mid"]
    return [
        f"rank({field})",
        f"zscore({field})",
        f"normalize({field}, useStd=false)",
        f"normalize({field}, useStd=true)",
        f"winsorize({field}, std=2)",              # std swept (S10-18)
        f"winsorize({field}, std=4)",
        # (removed reverse(rank(x)) 2026-07-17: per-leg sign-flip is redundant with the SIGN axis —
        #  for a multiply, negating one leg == negating the product == the global '-'. logic_matrix
        #  audit flagged it as a portfolio-duplicate on 243/1620 stage-3 variants.)
        f"ts_rank({field}, {s})",
        f"ts_rank({field}, {m})",
        f"ts_zscore({field}, {m})",
        f"ts_backfill({field}, {m})",
        f"ts_delta({field}, {s})",
        f"ts_delta({field}, {m})",
        f"ts_decay_linear({field}, 10, dense=false)",  # dense swept
        f"ts_decay_linear({field}, {m}, dense=true)",
        f"group_rank({field}, {GROUPS[0]})",
        f"group_rank({field}, {GROUPS[1]})",
        f"group_zscore({field}, {GROUPS[0]})",
    ]

# if_else compares its condition against 0, so the condition transform MUST be
# zero-centered: rank/ts_rank/group_rank output in [0,1] (greater(.,0) true for
# every stock but the minimum) and reverse(rank) in [-1,0] (always false) — those
# collapse the alpha to a single-field f2 (v7.1 must-fix). Conditions are
# therefore restricted to the sign-carrying transforms below.
_ZERO_CENTERED_PREFIXES = ("zscore(", "normalize(", "ts_zscore(", "ts_delta(",
                           "group_zscore(")


def cond_transforms(field: str) -> list[str]:
    """Zero-centered subset of transforms(field) — legal if_else conditions."""
    return [t for t in transforms(field) if t.startswith(_ZERO_CENTERED_PREFIXES)]


# ---- structures: combine two transformed fields, NEVER a plain weighted sum --
# Each structure enumerates its own enum-param variants (Khoa general rule:
# emitted calls match the FULL documented signature; enum params get swept).
STRUCTURES = {
    # multiply(x, y, ..., filter=false) — filter swept
    "multiply": {"params": ["filter=false", "filter=true"],
                 "build": lambda t1, t2, p: f"multiply({t1}, {t2}, {p})"},
    # if_else(cond, expr1, expr2) — cond restricted to zero-centered transforms
    "if_else":  {"params": [None], "zero_centered_cond": True,
                 "build": lambda t1, t2, p: f"if_else(greater({t1}, 0), {t2}, reverse({t2}))"},
    # divide(x, y)
    "divide":   {"params": [None],
                 "build": lambda t1, t2, p: f"divide({t1}, {t2})"},
}
# The stage-1 root is (by construction) a single-field / weighted-composite
# structure; all three options above are interaction structures that differ from
# it. A plain weighted sum is never emitted (asserted below).

_WSUM = re.compile(r"^\s*[\d.]+\s*\*.+\+\s*[\d.]+\s*\*")  # a*f1 + b*f2 pattern
SIGN = ["", "-"]                # Khoa 2026-07-17: sweep the combined-signal SIGN 50/50
                                # (stage-1 proved direction matters; a multiply of two ranks is
                                # positive-cornered, so half the book needs the short direction)
STRIDE_PRIME = 999983


_DS_MAP = None


def _dataset_of(field: str):
    """Resolve a field's real dataset id from the catalogs (model77 fields are named
    descriptively with no common name-prefix, so the old split('_') heuristic was wrong)."""
    global _DS_MAP
    if _DS_MAP is None:
        _DS_MAP = {}
        import pathlib
        base = pathlib.Path(__file__).resolve().parent.parent.parent
        for p in ["fetched/catalog_CHN/fields_per_dataset.jsonl", "fetched/catalog_JPN/fields.jsonl",
                  "fetched/fields_all.jsonl"]:
            fp = base / p
            if not fp.exists():
                continue
            for line in open(fp):
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                fid = r.get("id"); d = r.get("dataset")
                did = d.get("id") if isinstance(d, dict) else d
                if fid and did and fid not in _DS_MAP:
                    _DS_MAP[fid] = did
    return _DS_MAP.get(field)


def _dataset_prefix(field: str) -> str:
    # prefer the catalog dataset.id; fall back to the name-prefix only if unknown
    return _dataset_of(field) or field.split("_", 1)[0]


def _mixed_radix(n: int, radices: list[int]) -> list[int]:
    out = []
    for r in reversed(radices):
        out.append(n % r)
        n //= r
    return list(reversed(out))


def generate(field1: str, field2: str, structure: str, region: str, universe: str,
             delay: int, root_structure: str | None = None, n: int = 180,
             label: str = "stage2") -> list[dict]:
    if structure not in STRUCTURES:
        raise ValueError(f"unknown structure {structure!r}; options={list(STRUCTURES)}")
    if root_structure is not None and structure == root_structure:
        raise ValueError(f"structure must DIFFER from root structure {root_structure!r}")
    if region not in NEUT_BY_REGION:
        raise ValueError(f"no neutralization list for region {region!r}")
    if field1 == field2:
        raise ValueError("field1 and field2 must be different fields")
    if _dataset_prefix(field1) != _dataset_prefix(field2):
        raise ValueError(f"field2 {field2!r} is not from the same dataset as field1 "
                         f"{field1!r} (prefixes {_dataset_prefix(field1)!r} vs "
                         f"{_dataset_prefix(field2)!r}); stage 2 requires the SAME dataset")

    spec = STRUCTURES[structure]
    f1t = (cond_transforms(field1) if spec.get("zero_centered_cond")
           else transforms(field1))
    f2t = transforms(field2)
    neut = NEUT_BY_REGION[region]
    axes = [f1t, f2t, spec["params"], neut, DECAY, TRUNC, PASTEUR, UNIT, NANH, SIGN]
    radices = [len(a) for a in axes]
    total = math.prod(radices)
    if total < n:
        raise ValueError(f"axis space {total} < requested {n}")
    if math.gcd(STRIDE_PRIME, total) != 1:
        raise AssertionError("stride not coprime to axis space")

    rows, seen = [], set()
    i = 0
    # coprime stride guarantees n distinct indices spread across ALL axes
    while len(rows) < n:
        idx = (i * STRIDE_PRIME) % total
        i += 1
        d = _mixed_radix(idx, radices)
        formula = SIGN[d[9]] + spec["build"](f1t[d[0]], f2t[d[1]], spec["params"][d[2]])
        settings = {
            "instrumentType": "EQUITY",
            "region": region,
            "universe": universe,
            "delay": delay,
            "decay": DECAY[d[4]],
            "neutralization": neut[d[3]],
            "truncation": TRUNC[d[5]],
            "pasteurization": PASTEUR[d[6]],
            "unitHandling": UNIT[d[7]],
            "nanHandling": NANH[d[8]],
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
        rid = f"s2_{structure}_{len(rows):03d}"
        rows.append({"id": rid, "old_id": rid, "formula": formula,
                     "label": label, "settings": settings})
    return rows


def _cli():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--field1", required=True, help="root field id")
    ap.add_argument("--field2", required=True, help="chosen second field id (same dataset)")
    ap.add_argument("--structure", required=True, choices=list(STRUCTURES))
    ap.add_argument("--root-structure", default=None,
                    help="root alpha's structure (must differ from --structure)")
    ap.add_argument("--region", required=True)
    ap.add_argument("--universe", required=True)
    ap.add_argument("--delay", type=int, required=True)
    ap.add_argument("--n", type=int, default=180)  # Khoa 2026-07-17
    ap.add_argument("--label", default="stage2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = generate(a.field1, a.field2, a.structure, a.region, a.universe, a.delay,
                    a.root_structure, a.n, a.label)
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1)
    print(f"wrote {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    _cli()
