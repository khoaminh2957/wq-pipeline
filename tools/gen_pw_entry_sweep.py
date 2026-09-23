#!/usr/bin/env python3
"""gen_pw_entry_sweep.py — trade_when / if_else ENTRY-timing variants for the
Pontiff-Woodgate share-issuance alpha, on the winning split-immune composite root.

Trading logic, all grounded in the paper:
  age = days_from_last_change(sharesout) = days since the share count last changed
        = the AGE of the last issuance/repurchase corporate action.
  PW Table III documents drift 1 month -> 3 years AFTER the share change, dead after.
  => T-family: ENTER within a window of the event (age small), HOLD through the drift
     (trade_when freezes between events), EXIT (close) when the info is >2-3yr stale.
  => C-family: market-timing mechanism (managers issue after a RUN-UP, repurchase after a
     DECLINE). Take the position only when issuance direction ALIGNS with the prior-window
     price move (opportunistic); de-weight / zero the non-aligned (forced/atypical) names.
  => TC/T5: combine event-entry + opportunistic-selection, and a volume-confirmed event.

Root signal (from the 98-sim winner): reverse(winsorize(adjshr,std=4)), split-immune,
expected sign NEGATIVE (issuers underperform, repurchasers outperform).
"""
from __future__ import annotations
import json, pathlib, itertools

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/pw_entry_stage1_targets.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

D_NEAR, D_FAR, WIN = 126, 357, 231
COMP = (f"ts_delay(log(cap), {D_NEAR}) - ts_delay(log(cap), {D_FAR}) "
        f"- ts_delay(ts_sum(log(1 + returns), {WIN}), {D_NEAR})")
BASE = f"adjshr = {COMP}; sig = reverse(winsorize(adjshr, std=4))"      # no age (C-family)
HEAD = f"{BASE}; age = days_from_last_change(sharesout)"                 # +age (T/TC/T5)
# run-up over the window IMMEDIATELY BEFORE the issuance window [t-588,t-357] (Panel C lead-lag)
RUNUP = f"runup = ts_delay(ts_sum(log(1 + returns), {WIN}), {D_FAR})"

VARIANTS = {
    # T-family: event-timed entry + drift-horizon exit
    "T1_evt_hold":     f"{HEAD}; trade_when(age < 21, sig, -1)",
    "T2_evt_exit2y":   f"{HEAD}; trade_when(age < 21, sig, age > 504)",
    "T3_evt_exit3y":   f"{HEAD}; trade_when(age < 21, sig, age > 756)",
    "T4_evt63_exit2y": f"{HEAD}; trade_when(age < 63, sig, age > 504)",
    # C-family: opportunistic market-timing selection via if_else (no event clock)
    "C1_opp_only":     f"{BASE}; {RUNUP}; aligned = sign(adjshr) == sign(runup); if_else(aligned, sig, 0)",
    "C2_opp_tilt":     f"{BASE}; {RUNUP}; aligned = sign(adjshr) == sign(runup); if_else(aligned, sig, 0.5 * sig)",
    # TC: event entry + opportunistic selection + drift exit (full trading logic)
    "TC1_evt_opp":     f"{HEAD}; {RUNUP}; aligned = sign(adjshr) == sign(runup); trade_when(age < 21, if_else(aligned, sig, 0), age > 504)",
}
# T5: volume-confirmed event (the corporate action hit the tape)
V5 = f"{HEAD}; trade_when(and(less(age, 21), greater(volume, adv20)), sig, age > 504)"

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
    oid = f"pwe_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": settings(neut, trunc, decay)})

NEUT3 = ["SECTOR", "INDUSTRY", "SUBINDUSTRY"]
for name, formula in VARIANTS.items():
    for neut, trunc, decay in itertools.product(NEUT3, [0.02, 0.08], [0, 4]):
        add(name, formula, neut, trunc, decay)           # 7 * 3*2*2 = 84
for neut, decay in itertools.product(NEUT3, [0, 4]):
    add("T5_evt_vol", V5, neut, 0.05, decay)             # 3*2 = 6

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
from collections import Counter
print("by variant:", dict(Counter("_".join(r["old_id"].split("_")[1:-1]) for r in rows)))
