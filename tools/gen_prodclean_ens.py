#!/usr/bin/env python3
"""gen_prodclean_ens.py — untried lever: ensemble the PROVEN prod-clean rare signals (the A17YGP7d
family, measured 0-9 prod-breaches) for BREADTH -> lift sharpe past 1.58 while staying prod-corr<0.7.
Single ones capped ~sharpe 1.0-1.26; combining independent prod-clean signals is the untried path to
a STRONG submittable. Non-pv1 (also theme-eligible). Sweeps universe/decay/neut."""
import json, pathlib, itertools
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/prodclean_ens_targets.json"

def z(expr):  # the shared transform used by the drive book: backfill -> ts_zscore
    return f"ts_zscore(ts_backfill({expr}, 20), 60)"

# prod-clean signal ATOMS (from the drive candidates that measured low prod-corr), each a ±rank leg
ATOMS = [
    ("rat",  f"rank({z('rp_nip_ratings / (unsystematic_risk_last_360_days + 1)')})", 0.7),
    ("sent", f"rank({z('scl12_sentiment')})", 0.6),
    ("buzz", f"rank({z('scl12_buzz / (unsystematic_risk_last_90_days + 1)')})", 0.5),
    ("skew", f"rank({z('implied_volatility_call_60 - implied_volatility_put_60')})", 0.5),
    ("pred", f"rank({z('likelihood_fifth_quantile_five_day_bucket_zero_32')})", 0.5),
    ("anl",  f"rank(ts_delta(ts_backfill(analyst_upward_revision_count_fq1_earnings_30d, 20), 20))", 0.4),
]

def ensemble(legs, decay, power, group=None):
    inner = "add(" + ", ".join(f"multiply({e}, {w})" for _, e, w in legs) + ", filter=true)"
    return f"signed_power(zscore(ts_decay_linear({inner}, {decay})), {power})"

def settings(univ, neut):
    return {"instrumentType":"EQUITY","region":"USA","universe":univ,"delay":1,"decay":0,
            "neutralization":neut,"truncation":0.05,"pasteurization":"ON","unitHandling":"VERIFY",
            "nanHandling":"OFF","maxTrade":"OFF","maxPosition":"OFF","language":"FASTEXPR",
            "visualization":False,"startDate":"2019-01-01","endDate":"2023-12-31"}

rows, seen = [], set()
def add(tag, formula, univ, neut):
    k = ("".join(formula.split()), univ, neut)
    if k in seen: return
    seen.add(k); oid = f"pce_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(univ, neut)})

# leg-sets: all 6, and best-5/best-4 subsets (drop the weakest to reduce dilution — round-1 lesson)
LEGSETS = {"all6": ATOMS, "top5": ATOMS[:5], "top4": ATOMS[:4],
           "no_pred": [a for a in ATOMS if a[0] != "pred"]}
for name, legs in LEGSETS.items():
    for univ in ("TOP1000", "TOP3000"):
        for decay in (10, 20):
            for power in (2.0, 2.5):
                f = ensemble(legs, decay, power)
                for neut in ("SUBINDUSTRY", "INDUSTRY"):
                    add(f"{name}_{univ[3:]}_d{decay}", f, univ, neut)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
