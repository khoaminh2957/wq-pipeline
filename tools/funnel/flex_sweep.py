#!/usr/bin/env python3
"""flex_sweep.py — FLEXIBLE stage-1 variant generator (Khoa 2026-07-17). Replaces the FIXED settings-only
sweep: instead of one frozen formula swept over settings, it builds 180 DIVERSE FORMULA variants grounded in
(a) OPERATOR-usage logic (logic_operators.md), (b) each field's DESCRIPTION/nature (logic_check.field_nature),
and (c) SAME-DATASET field additions, aimed at pushing ALL metrics up (sharpe, fitness, 2Y, sub-universe,
after-cost, investability) — not just settings.

Levers (all deterministic, coprime-stride sampled):
  1. per-leg transform chosen by FIELD NATURE (CHANGE -> rank/ts_rank; LEVEL/NONNEG -> ts_zscore-then-rank;
     already-normalized -> plain rank) + optional per-leg turnover valve (ts_decay_linear on the leg).
  2. optional 3rd leg = a FRESH field from the SAME DATASET (liquid-carrier / confirmation), always same-dataset
     first (Khoa) — lifts sub-universe / TOP200 / robustness.
  3. whole-signal turnover valve (ts_decay_linear / hump) -> cuts turnover -> fixes fitness / after-cost / max-trade/position.
  4. settings: neutralization breadth × truncation × decay × pasteurization × nanHandling.

The structure stays a CONFIRMATION multiply (Law 6). Field-nature veto (no ts_delta on a CHANGE field, no
re-normalize of a NORMALIZED field) is enforced so every variant is MEANINGFUL, not rationalized.
"""
from __future__ import annotations
import argparse, json, math, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.funnel.second_field_sweep import (  # noqa: E402
    NEUT_BY_REGION, DECAY, TRUNC, PASTEUR, UNIT, NANH, _mixed_radix, STRIDE_PRIME,
)
from tools.funnel.logic_check import FIELDS, field_nature  # noqa: E402

_ZW = [63, 126, 252]   # ts_zscore windows for LEVEL fields (own-history deviation)
_RW = [10, 22]         # ts_rank windows


def _nature_of(field):
    meta = FIELDS.get(field) or {}
    return field_nature((meta.get("description") or "").lower())


def leg_transforms(field, sign):
    """Nature-aware [0,1]-bounded leg expressions for a signed field (Law 1 + field-description logic)."""
    f = f"{sign}{field}" if sign == "-" else field
    nat = _nature_of(field)
    out = []
    if "LEVEL" in nat or "NONNEG" in nat:
        # a raw LEVEL must become an own-history deviation before it means anything cross-sectionally
        for w in _ZW:
            out.append(f"rank(ts_zscore({f}, {w}))")
        out.append(f"rank(ts_rank({f}, 22))")
    elif "NORMALIZED" in nat:
        out.append(f"rank({f})")           # already normalized -> plain rank; do NOT re-standardize
    else:  # CHANGE / plain / signed
        out.append(f"rank({f})")
        out.append(f"rank(ts_decay_linear({f}, 4))")   # per-leg turnover valve
        out.append(f"rank(ts_decay_linear({f}, 8))")
        out.append(f"rank(winsorize({f}, std=4))")     # tail control -> fitness
        for w in _RW:
            out.append(f"rank(ts_rank({f}, {w}))")
    return out or [f"rank({f})"]


# whole-signal turnover valves (cut turnover -> fix fitness/after-cost/investable)
_WHOLE = ["{X}", "ts_decay_linear({X}, 4)", "ts_decay_linear({X}, 8)", "hump({X}, hump=0.01)"]


def generate(core_legs: list[str], base_settings: dict, region: str, universe: str, delay: int,
             same_ds_pool: list[str] | None = None, n: int = 90, label: str = "flex") -> list[dict]:
    """ANCHORED flexibility (Khoa 2026-07-17): the core_legs (the EXACT working leg expressions of the base
    alpha) are KEPT — we do NOT re-transform them (that diverges from the peak). variant 000 = the base
    verbatim. We flex only the PERIPHERY that pushes the fixable metrics: a whole-signal turnover valve
    (decay/hump -> fitness/after-cost/investable), an optional SAME-DATASET 3rd leg (liquid carrier ->
    sub-universe/TOP200), and settings (neut breadth × trunc × decay × past × nan)."""
    if len(core_legs) < 2:
        raise ValueError("need >=2 core legs")
    core = f"multiply({', '.join(core_legs)}, filter=true)"
    pool = [""] + list(same_ds_pool or [])
    neut = NEUT_BY_REGION[region]

    def _full(s):
        return {"instrumentType": "EQUITY", "region": region, "universe": universe, "delay": delay,
                "neutralization": s.get("neutralization", neut[0]), "decay": s.get("decay", 0),
                "truncation": s.get("truncation", 0.0), "pasteurization": s.get("pasteurization", PASTEUR[0]),
                "unitHandling": UNIT[0], "nanHandling": s.get("nanHandling", NANH[0]),
                "language": "FASTEXPR", "visualization": False}

    rows, seen, i = [], set(), 0
    # variant 000 = base verbatim (anchor — flex never regresses below the working config)
    bset = _full(base_settings)
    rows.append({"id": f"{label}_000", "old_id": f"{label}_000", "formula": core, "label": label, "settings": bset})
    seen.add((re.sub(r"\s+", "", core), region, universe, delay,
              bset["neutralization"], bset["decay"], bset["truncation"]))

    axes = [pool, _WHOLE, neut, TRUNC, DECAY, PASTEUR, NANH]
    radices = [len(a) for a in axes]
    total = math.prod(radices)
    if math.gcd(STRIDE_PRIME, total) != 1:
        raise AssertionError("stride not coprime")
    while len(rows) < n:
        idx = (i * STRIDE_PRIME) % total
        i += 1
        d = _mixed_radix(idx, radices)
        p = pool[d[0]]
        legs = list(core_legs)
        if p:                       # add a SAME-dataset liquid-carrier / confirmation leg (nature-aware)
            legs.append(leg_transforms(p, "+")[0])
        body = f"multiply({', '.join(legs)}, filter=true)"
        whole = _WHOLE[d[1]]
        formula = whole.format(X=body)
        decay = DECAY[d[4]]
        if whole.startswith("ts_decay_linear"):
            decay = 0
        settings = {
            "instrumentType": "EQUITY", "region": region, "universe": universe, "delay": delay,
            "neutralization": neut[d[2]], "decay": decay, "truncation": TRUNC[d[3]],
            "pasteurization": PASTEUR[d[5]], "unitHandling": UNIT[0],
            "nanHandling": NANH[d[6]], "language": "FASTEXPR", "visualization": False,
        }
        k = (re.sub(r"\s+", "", formula), region, universe, delay,
             settings["neutralization"], settings["decay"], settings["truncation"])
        if k in seen:
            continue
        seen.add(k)
        rows.append({"id": f"{label}_{len(rows):03d}", "old_id": f"{label}_{len(rows):03d}",
                     "formula": formula, "label": label, "settings": settings})
    return rows


# ---- same-dataset FRESH liquid-carrier pools (Khoa: always prefer same dataset) ----
def same_dataset_pool(dataset: str, region="USA", delay=1, exclude=(), max_ac=200, n=12):
    """Fresh (alphaCount<=max_ac), well-covered MATRIX fields from `dataset` — candidate 3rd legs."""
    import json as _j
    cands = []
    for line in open(ROOT / "fetched/fields_all.jsonl"):
        try:
            x = _j.loads(line)
        except Exception:
            continue
        if x.get("region") != region or x.get("delay") != delay or x.get("type") != "MATRIX":
            continue
        d = x.get("dataset") or {}
        if (d.get("id") if isinstance(d, dict) else d) != dataset:
            continue
        fid = x.get("id")
        ac = x.get("alphaCount") or 0
        cov = x.get("coverage") or 0
        if fid in exclude or ac > max_ac or cov < 0.9:
            continue
        cands.append((ac, fid))
    cands.sort()
    return [f for _, f in cands[:n]]


ROOTS = {
    # the 2 live alphas' EXACT working cores (Khoa 2026-07-17) — anchor + flex periphery. exclude_fields =
    # the fields already in the core (so the same-dataset 3rd leg is genuinely additional).
    "srl2": {"core_legs": ["rank(-mdl177_pricemomemtummodel_indrelrtn5d_)",
                           "rank(ts_zscore(mdl77_liquidityriskfactor_milliq, 252))"],
             "base_settings": {"neutralization": "STATISTICAL", "decay": 0, "truncation": 0.05,
                               "pasteurization": "OFF", "nanHandling": "OFF"},
             "dataset": "model77",
             "exclude": ["mdl177_pricemomemtummodel_indrelrtn5d_", "mdl77_liquidityriskfactor_milliq"]},
    "dsp":  {"core_legs": ["rank(-fy2_eps_estimate_dispersion)",
                           "rank(-mdl177_pricemomemtummodel_indrelrtn5d_)"],
             "base_settings": {"neutralization": "CROWDING", "decay": 0, "truncation": 0.1,
                               "pasteurization": "OFF", "nanHandling": "OFF"},
             "dataset": "model77",
             "exclude": ["fy2_eps_estimate_dispersion", "mdl177_pricemomemtummodel_indrelrtn5d_"]},
}


def _cli():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, choices=list(ROOTS))
    ap.add_argument("--region", default="USA"); ap.add_argument("--universe", default="TOP1000")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--n", type=int, default=90)  # Khoa: 90/batch = 9 multi-sim x 10 single (fills the ceiling)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = ROOTS[a.root]
    pool = same_dataset_pool(spec["dataset"], a.region, a.delay, exclude=spec["exclude"])
    rows = generate(spec["core_legs"], spec["base_settings"], a.region, a.universe, a.delay,
                    pool, a.n, label=f"flex{a.root}")
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1)
    print(f"wrote {len(rows)} flexible variants -> {a.out} (same-dataset pool: {len(pool)} fields)")


if __name__ == "__main__":
    _cli()
