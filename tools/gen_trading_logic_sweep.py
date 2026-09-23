#!/usr/bin/env python3
"""gen_trading_logic_sweep.py — TRADING-LOGIC strategies (methodology redesign, 2026-07-20).

No papers. Each strategy is a plain market MECHANIC ("when X moves, Y reacts because
[trader behavior]"), mapped to fields whose DESCRIPTION makes the causal read self-evident,
and encoded with the operator that MATCHES the relationship (change=ts_delta, interaction=
multiply, ratio=divide, divergence=subtract-of-ranks, conditioning=trade_when/if_else).
The signal is the RELATIONSHIP, not the level. The sim on BRAIN data — not a citation —
decides. USA d1 TOP3000 to give each mechanic the best chance to reveal signal.
"""
from __future__ import annotations
import json, pathlib, itertools

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/trading_logic_stage1_targets.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

UTIL="mdl177_5shortsentimentfactor_act_util"; FEE="mdl177_5shortsentimentfactor_benchmark_fee"
MILLIQ="mdl177_2_liquidityriskfactor_milliq"; VOLTO="mdl177_2_liquidityriskfactor_volto"
IV1="opt6_vimta1m"; IV2="opt6_vimta2m"; SKEW="opt6_slope"; PV="opt6_pvolu"; CV="opt6_cvolu"
IVHV="opt6_ivhvxernratio"; CORR="opt6_correlspy1m"

STRATS = {
    # panic on volume climax -> bounce
    "S1_panic_rev":   "multiply(rank(-ts_delta(close, 1)), rank(volume/adv20))",
    # rally on FALLING volume = no conviction -> fade (short it)
    "S2_weak_rally":  "reverse(multiply(rank(ts_delta(close, 5)), rank(reverse(ts_delta(volume, 5)))))",
    # implied vol drained + price stayed calm = fear leaving without damage -> recover
    "S3_iv_drain":    "multiply(rank(reverse(ts_delta(opt6_vimta1m, 5))), rank(reverse(abs(ts_delta(close, 5)))))",
    # cheap vol (IV<<realized) AND low put-skew = bullish options setup
    "S4_cheap_vol":   "multiply(rank(reverse(opt6_ivhvxernratio)), rank(reverse(opt6_slope)))",
    # heavy short interest + price turning UP = squeeze fuel
    "S5_squeeze":     "multiply(rank(mdl177_5shortsentimentfactor_act_util), rank(ts_delta(close, 5)))",
    # loan fee spiking (crowded short) + big drop = capitulation -> contrarian long
    "S6_crowded_shrt":"multiply(rank(mdl177_5shortsentimentfactor_benchmark_fee), rank(-ts_delta(close, 10)))",
    # put-heavy flow + price already down = options capitulation -> bounce
    "S7_putcall_cap": "multiply(rank(opt6_pvolu/opt6_cvolu), rank(-ts_delta(close, 5)))",
    # overnight demand persists, intraday move is noise -> long overnight, short intraday
    "S8_on_id_tug":   "subtract(rank(ts_mean(open/ts_delay(close,1) - 1, 5)), rank(ts_mean(close/open - 1, 5)))",
    # illiquid names overshoot (price impact) -> stronger reversal
    "S9_illiq_rev":   "multiply(rank(-ts_delta(close, 5)), rank(mdl177_2_liquidityriskfactor_milliq))",
    # near-term IV fear + price dropped = short-term panic -> resolves -> bounce
    "S10_term_fear":  "multiply(rank(opt6_vimta1m/opt6_vimta2m), rank(-ts_delta(close, 5)))",
    # rising price + rising turnover = accumulation/conviction -> continuation
    "S11_accum_mom":  "multiply(rank(ts_delta(close, 10)), rank(mdl177_2_liquidityriskfactor_volto))",
    # low market-IV-correlation names rising = idiosyncratic strength (not just beta)
    "S12_idio_mom":   "multiply(rank(reverse(opt6_correlspy1m)), rank(ts_delta(close, 5)))",
    # price at top of 20-day range + volume climax = exhaustion -> fade to mean
    "S13_range_fade": "multiply(reverse(rank(ts_zscore(close, 20))), rank(volume/adv20))",
}

def settings(neut, trunc, decay):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
            "decay": decay, "neutralization": neut, "truncation": trunc,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}

rows, seen = [], set()
def add(tag, formula, neut, trunc, decay):
    k = ("".join(formula.split()), neut, trunc, decay)
    if k in seen: return
    seen.add(k)
    oid = f"tl_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut, trunc, decay)})

# 13 strategies x neut{MARKET,INDUSTRY,SUBINDUSTRY} x decay{0,6}  = 78
for name, f in STRATS.items():
    for neut, decay in itertools.product(["MARKET", "INDUSTRY", "SUBINDUSTRY"], [0, 6]):
        add(name, f, neut, 0.05, decay)
# 6 slow/fundamental-mixed strategies x trunc extremes @ INDUSTRY/decay6 = 12  -> 90
for name in ["S3_iv_drain", "S4_cheap_vol", "S5_squeeze", "S6_crowded_shrt", "S9_illiq_rev", "S12_idio_mom"]:
    for trunc in [0.02, 0.08]:
        add(name, STRATS[name], "INDUSTRY", trunc, 6)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
