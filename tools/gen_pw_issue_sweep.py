#!/usr/bin/env python3
"""gen_pw_issue_sweep.py — paper-faithful stage-1 sweep for Pontiff-Woodgate (2008)
share issuance. Every FORMULA is a grounded variant of the paper's tested construct;
only settings (neutralization x truncation x decay) and a small set of paper-grounded
shape/carrier legs vary. Emits homogeneous USA/TOP3000/delay1 rows, dedups, validates.

Measure axes (both grounded in the paper):
  comp   = Daniel-Titman split-immune identity over PW's ISSUE(-17,-6) window:
           adjshr = dlog(cap)[t-126..t-357] - sum log(1+returns) over the same window.
           Splits cancel by construction (cap invariant, returns split-adjusted); escapes
           Law-1 (built from raw pv1 fields, not a re-rank of a pre-built score). WINNER.
  vendor = reverse(winsorize(ts_delay(chgshare,126))) — the paper's Eq.2 via the vendor's
           precomputed 1-yr share change; fidelity benchmark (tests vendor split-adjustment).

Transform: the paper trades the WINSORIZED LINEAR level (Fama-MacBeth slope validates the
magnitude; ~24% zero-issuance mass sits at TRUE NEUTRAL, not a mid-rank tie). Expected sign
NEGATIVE (issuers underperform, repurchasers outperform) -> reverse().
"""
from __future__ import annotations
import json, pathlib, itertools

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "state/funnel/pw_issue_stage1_targets.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# --- paper windows (trading days): ISSUE(-17,-6) = shares at t-126 vs t-357, window 231d
D_NEAR, D_FAR, WIN = 126, 357, 231

# split-immune Daniel-Titman composite over the PW window
COMP = (f"adjshr = ts_delay(log(cap), {D_NEAR}) - ts_delay(log(cap), {D_FAR}) "
        f"- ts_delay(ts_sum(log(1 + returns), {WIN}), {D_NEAR})")

def comp_pure(std):
    return f"{COMP}; reverse(winsorize(adjshr, std={std}))"

def vendor_pure(std):
    return f"reverse(winsorize(ts_delay(mdl177_2_deepvaluemodel_chgshare, {D_NEAR}), std={std}))"

def comp_ff2008(std):
    # FF2008 non-monotonicity: small positive issuance earns POSITIVE returns; short only the
    # extreme-issuer tail (top quintile), long all repurchasers (adjshr<0), zero the benign middle.
    return (f"{COMP}; sig = reverse(winsorize(adjshr, std={std})); "
            f"if_else(rank(adjshr) > 0.8, sig, if_else(adjshr < 0, sig, 0))")

def comp_carrier(std):
    # Dim-6 liquidity-orthogonal carrier on liquid names: 1-month reversal (flow family, never
    # value/size/vol). Signed issuance level x [0,1] reversal-confirmation rank (Law-6 safe).
    return (f"{COMP}; sig = reverse(winsorize(adjshr, std={std})); "
            f"conf = rank(reverse(ts_sum(returns, 21))); multiply(sig, conf)")

def settings(neut, trunc, decay):
    return {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
        "decay": decay, "neutralization": neut, "truncation": trunc,
        "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
        "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
        "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31",
    }

rows, seen = [], set()
def add(tag, formula, neut, trunc, decay):
    s = settings(neut, trunc, decay)
    k = ("".join(formula.split()), neut, trunc, decay)
    if k in seen:
        return
    seen.add(k)
    oid = f"pw_{tag}_{len(rows):03d}"
    rows.append({"old_id": oid, "id": oid, "formula": formula + "\n", "settings": s})

# ---- Block A: composite PURE across the full robustness grid (the star) ---------------
NEUT4 = ["MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"]
for neut, trunc, decay in itertools.product(NEUT4, [0.02, 0.05, 0.08, 0.10], [0, 4, 8, 12]):
    add("comp", comp_pure(4), neut, trunc, decay)                       # 4*4*4 = 64

# ---- Block B: composite winsorize-std sweep at mid settings ---------------------------
for std, neut, decay in itertools.product([3, 5], ["SECTOR", "INDUSTRY"], [0, 4]):
    add(f"comp_s{std}", comp_pure(std), neut, 0.05, decay)              # 2*2*2 = 8

# ---- Block C: vendor benchmark (tests vendor split-adjustment) ------------------------
for neut, trunc, decay in itertools.product(NEUT4, [0.05, 0.08], [0, 4]):
    add("vendor", vendor_pure(4), neut, trunc, decay)                  # 4*2*2 = 16

# ---- Block D: FF2008 extreme-tail shape (composite) -----------------------------------
for neut, decay in itertools.product(["MARKET", "SECTOR", "INDUSTRY"], [0, 4]):
    add("ff08", comp_ff2008(4), neut, 0.05, decay)                     # 3*2 = 6

# ---- Block E: liquidity-orthogonal carrier (composite x 1-mo reversal) ----------------
for neut, decay in itertools.product(["SECTOR", "INDUSTRY"], [0, 4]):
    add("carrier", comp_carrier(4), neut, 0.05, decay)                 # 2*2 = 4

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
from collections import Counter
c = Counter(r["old_id"].split("_")[1] for r in rows)
print("by block:", dict(c))
