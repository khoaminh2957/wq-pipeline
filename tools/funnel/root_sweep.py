#!/usr/bin/env python3
"""root_sweep.py — STAGE-1 sweep for a FIXED multi-leg root alpha (Khoa 2026-07-17, 3-root process).

The v7 config_sweep builds single-field transform variants; the new Stage-0 roots are already the
BEST 2-leg operator expression of a hypothesis (S4.0 Dim 5), so Stage 1 keeps the FORMULA STRUCTURE
fixed and sweeps the CONFIG: neutralization × truncation × decay × pasteurization × unitHandling ×
nanHandling, plus any small formula KNOBS the root's construction rationale named (e.g. the ts_zscore
window, the multiply filter). Region/universe/delay fixed. Deterministic (coprime-stride mixed-radix,
no RNG) — same inputs → byte-identical output.

  formula = template.format(**{knob: value})     # knobs the rationale said to probe
  settings = fixed cell + swept {neut, trunc, decay, past, unit, nan}

Output rows match resim_targets.json so validate_targets/logic_check/run_multisim accept them.
"""
from __future__ import annotations
import argparse, json, math, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# reuse the stage-2 config axes + sampler wholesale
from tools.funnel.second_field_sweep import (  # noqa: E402
    NEUT_BY_REGION, DECAY, TRUNC, PASTEUR, UNIT, NANH, _mixed_radix, STRIDE_PRIME,
)


def generate(root_id: str, template: str, knobs: dict | None, region: str, universe: str,
             delay: int, n: int = 180, label: str = "root_stage1") -> list[dict]:
    if region not in NEUT_BY_REGION:
        raise ValueError(f"no neutralization list for region {region!r}")
    knobs = knobs or {}
    knob_names = list(knobs)
    knob_axes = [knobs[k] for k in knob_names]
    neut = NEUT_BY_REGION[region]
    axes = knob_axes + [neut, DECAY, TRUNC, PASTEUR, UNIT, NANH]
    radices = [len(a) for a in axes]
    total = math.prod(radices)
    if total < n:
        raise ValueError(f"axis space {total} < requested {n}")
    if math.gcd(STRIDE_PRIME, total) != 1:
        raise AssertionError("stride not coprime to axis space")

    rows, seen, i = [], set(), 0
    while len(rows) < n:
        idx = (i * STRIDE_PRIME) % total
        i += 1
        d = _mixed_radix(idx, radices)
        kv = {name: knobs[name][d[j]] for j, name in enumerate(knob_names)}
        formula = template.format(**kv) if kv else template
        off = len(knob_names)
        settings = {
            "instrumentType": "EQUITY", "region": region, "universe": universe, "delay": delay,
            "neutralization": neut[d[off]],
            "decay": DECAY[d[off + 1]],
            "truncation": TRUNC[d[off + 2]],
            "pasteurization": PASTEUR[d[off + 3]],
            "unitHandling": UNIT[d[off + 4]],
            "nanHandling": NANH[d[off + 5]],
            "language": "FASTEXPR", "visualization": False,
        }
        k = (re.sub(r"\s+", "", formula), settings["neutralization"], settings["decay"],
             settings["truncation"], settings["pasteurization"], settings["unitHandling"],
             settings["nanHandling"])
        if k in seen:
            continue
        seen.add(k)
        rid = f"{root_id}_s1_{len(rows):03d}"
        rows.append({"id": rid, "old_id": rid, "formula": formula, "label": label, "settings": settings})
    return rows


# ---- the 3 Khoa-approved roots (2026-07-17). neutralization is SWEPT (not baked into the formula) ----
ROOTS = {
    "newsflow_A": {
        "template": "multiply(rank(mean_event_novelty_score), rank(-mean_event_sentiment_score))",
        "knobs": {},
    },
    "srl2": {
        "template": ("multiply(rank(-mdl177_pricemomemtummodel_indrelrtn5d_), "
                     "rank(ts_zscore(mdl77_liquidityriskfactor_milliq, {W})), filter={F})"),
        "knobs": {"W": [63, 126, 252], "F": ["true", "false"]},
    },
    "opt_ivrv": {
        "template": ("subtract(regression_proj(rank(opt6_vim6), rank(opt6_vhslcd252)), "
                     "rank(opt6_vim6))"),
        "knobs": {},
    },
    # v2 (Khoa 2026-07-17): dispersion × reversal-carrier (Miller/DMS overpricing; reuses v1's zero-fail leg)
    "dsp_dmsrev": {
        "template": ("multiply(rank(-fy2_eps_estimate_dispersion), "
                     "rank(-mdl177_pricemomemtummodel_indrelrtn5d_), filter=true)"),
        "knobs": {},
    },
    # v3 (Khoa 2026-07-17): short-interest CHANGE × borrow-fee (short-crowding/limits-to-arb; LOW turnover
    # ~0.1-0.2 -> better max-position/max-trade investability than the reversal family)
    "si_demandshift": {
        "template": ("reverse(multiply(rank(mdl77_liquidityriskfactor_monchgsip), "
                     "rank(mdl177_5shortsentimentfactor_benchmark_fee), filter=true))"),
        "knobs": {},
    },
    # v5 (Khoa-approved 2026-07-18): 3 ORTHOGONAL roots to break the LOW_2Y(2022-23)+LOW_SUB_UNIVERSE wall.
    # 6 disjoint datasets, 3 distinct forces, NO shared reversal leg (unlike srl2/dsp). Fields grep-verified USA d1.
    # ROOT 1 credit-distress x momentum (panel 3/3, construction 0.88, LOW turnover ~0.06-0.15):
    "v5_distress": {
        "template": ("multiply(rank(-ts_backfill(annualized_pd_1_year_jm5, 66)), "
                     "rank(mdl77_pricemomentumfactor_actrtn12m))"),
        "knobs": {},
    },
    # ROOT 2 option informed-pessimism: put-skew CONFIRMED by put-heavy flow (panel 3/3; theme-risk -> in-expr decay 12):
    "v5_optskew": {
        "template": ("-multiply(rank(ts_decay_linear(forecasted_put_call_slope, 12)), "
                     "rank(ts_decay_linear(divide(opt6_pvolu, add(add(opt6_pvolu, opt6_cvolu), 1)), 12)))"),
        "knobs": {},
    },
    # ROOT 3 analyst revision-momentum x news-sentiment confirm (panel 3/3, thinnest 2Y; LOW turnover):
    "v5_revision": {
        "template": ("multiply(rank(ts_backfill(one_month_change_mean_earnings_estimate_scaled_price, 20)), "
                     "rank(ts_backfill(mean_earnings_evaluation_sentiment, 20)))"),
        "knobs": {},
    },
}


def _cli():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, choices=list(ROOTS))
    ap.add_argument("--region", default="USA")
    ap.add_argument("--universe", default="TOP1000")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--n", type=int, default=180)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = ROOTS[a.root]
    rows = generate(a.root, spec["template"], spec["knobs"], a.region, a.universe, a.delay, a.n)
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1)
    print(f"wrote {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    _cli()
