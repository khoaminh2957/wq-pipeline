#!/usr/bin/env python3
"""A candidate must beat its OWN ablations, or it is not a signal.

WHY THIS GATE EXISTS, measured 2026-08-11. `2rppNqbZ` passed everything the pipeline had: 17 checks
with zero failures, IS_LADDER_SHARPE 2.06 over a 2.02 bar, LOW_FITNESS 1.26, prod-correlation 0.650
against a 0.70 line, predicted self-correlation 0.43, and `submit_safety --plan` called it
conflict-free. Every threshold in the system said submit it.

Then the ablations were simulated:

    arm C  the alpha as built                     sharpe 2.18   ladder 2.06
    arm D  the price carrier ALONE, no field      sharpe 3.21   (higher)
    arm B  every field value replaced by a constant, availability pattern only   ladder 2.26 (higher)

The two price legs did all the work. The cell fields contributed no Sharpe; they mainly damped
turnover from 0.75 to 0.10, which is what let the thing through the turnover cap. Three alphas
built this way were already submitted before anyone ran the control.

No additional THRESHOLD would have caught that, because the alpha passed every threshold. What was
missing was a control. So: before a candidate is presentable, its ablations are simulated and it
must beat them.

THE RULE, deliberately strict and stated as a falsifiable claim:

  a candidate PASSES only if   sharpe(C) >= sharpe(D) * MARGIN   and   sharpe(C) >= sharpe(B) * MARGIN

  D  = the same formula with every non-price leg deleted (the carrier alone)
  B  = the same formula with every data field replaced by `add(multiply(field,0),1)`, which is 1
       where the field exists and NaN where it does not, so the legs keep the data-AVAILABILITY
       pattern and carry no signal
  MARGIN default 1.05 — a candidate that merely ties its own ablation is not evidence of a signal

UNKNOWNS, stated rather than buried:
  * MARGIN is a choice, not a measurement. 1.05 is the smallest gap that is not noise on a single
    5-year backtest; nothing here establishes what gap predicts out-of-sample survival.
  * arm A (filter=false) is deliberately NOT part of the rule. It looked decisive and was not: with
    filter=false a name missing ANY leg leaves the sum entirely, so the alpha trades a much smaller
    universe and its collapse is confounded with universe size. It is reported, never gated on.
  * Passing this gate does not make a candidate good. It only means its own carrier does not
    already do the job.

  python3 tools/ablation_gate.py --build 2rppNqbZ E5GGlLgJ     # emit the ablation pool
  python3 tools/ablation_gate.py --judge                       # verdict once they are simulated
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ST = ROOT / "state"
JOURNAL = ST / "resim_results.jsonl"
POOL = ST / "autoloop" / "pool_ablation.json"
VERDICTS = ST / "ablation_verdicts.json"

PRICE = {"close", "open", "vwap", "high", "low", "volume", "returns", "adv20", "cap"}
CARRIER = "-rank(divide(close, open)), multiply(-rank(divide(close, vwap)), 0.6)"
MARGIN = 1.05


def journal_rows(prefixes=("",)):
    out = {}
    with open(JOURNAL, errors="ignore") as f:
        for line in f:
            if not any(p in line for p in prefixes):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            key = d.get("alpha") or d.get("old_id")
            if key:
                out[key] = d
    return out


def data_fields(formula, catalog):
    return sorted({t for t in re.findall(r"\b[a-z][a-z0-9_]{3,}\b", formula)
                   if t in catalog and t not in PRICE})


def load_catalog():
    cat = set()
    p = ROOT / "fetched/rc/fields/USA_TOP3000_d1.jsonl"
    try:
        for line in open(p, errors="ignore"):
            try:
                cat.add(json.loads(line)["id"])
            except Exception:
                continue
    except OSError:
        pass
    return cat


def strip_to_carrier(formula):
    """arm D — keep the wrapper and settings, delete every leg that is not the price carrier."""
    m = re.search(r"add\((.*), filter=true\)", formula, re.S)
    if not m:
        return None
    return formula[:m.start(1)] + CARRIER + formula[m.end(1):]


def availability_only(formula, fields):
    """arm B — 1 where the field exists, NaN where it does not. Availability, zero signal."""
    out = formula
    for f in fields:
        out = re.sub(rf"\b{re.escape(f)}\b", f"add(multiply({f}, 0), 1)", out)
    return out


def build(alpha_ids):
    cat = load_catalog()
    src = journal_rows(tuple(alpha_ids))
    rows, skipped = [], []
    for aid in alpha_ids:
        d = src.get(aid)
        if not d:
            skipped.append((aid, "not in the journal"))
            continue
        fields = data_fields(d["formula"], cat)
        if not fields:
            skipped.append((aid, "no data field — it is already a bare carrier"))
            continue
        carrier = strip_to_carrier(d["formula"])
        if carrier is None:
            skipped.append((aid, "no add(..., filter=true) body to strip"))
            continue
        st = dict(d["settings"])
        st.setdefault("instrumentType", "EQUITY")
        for arm, formula in (("D_carrier_only", carrier),
                             ("B_availability_only", availability_only(d["formula"], fields)),
                             ("A_filter_false", d["formula"].replace("filter=true", "filter=false"))):
            rows.append({"old_id": f"ABL{arm[0]}_{aid}", "id": f"ABL{arm[0]}_{aid}",
                         "formula": formula, "settings": dict(st),
                         "meta": {"kind": "ablation", "arm": arm, "parent": aid,
                                  "family": f"abl:{aid}", "n_data_fields": len(fields)}})
    POOL.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(POOL, "w"), indent=1)
    return rows, skipped


def judge(margin=MARGIN):
    rows = journal_rows(("ABL",))
    arms = {}
    for oid, d in rows.items():
        m = d.get("meta") or {}
        if m.get("kind") != "ablation":
            continue
        arms.setdefault(m["parent"], {})[m["arm"]] = d
    parents = journal_rows(tuple(arms)) if arms else {}

    out = {}
    for parent, a in sorted(arms.items()):
        c = parents.get(parent)
        need = [k for k in ("D_carrier_only", "B_availability_only") if k not in a]
        if c is None or need:
            out[parent] = {"verdict": "UNDECIDED",
                           "why": (f"missing arm(s) {need}" if need else
                                   "the candidate itself is not in the journal"),
                           "note": "UNDECIDED is NOT a pass — nothing may be submitted on it"}
            continue
        sc = c.get("sharpe")
        sd = a["D_carrier_only"].get("sharpe")
        sb = a["B_availability_only"].get("sharpe")
        if not all(isinstance(x, (int, float)) for x in (sc, sd, sb)):
            out[parent] = {"verdict": "UNDECIDED", "why": "a sharpe is missing from an arm"}
            continue
        beats_d = sc >= sd * margin
        beats_b = sc >= sb * margin
        out[parent] = {
            "verdict": "PASS" if (beats_d and beats_b) else "REJECT",
            "sharpe_candidate": sc, "sharpe_carrier_only": sd, "sharpe_availability_only": sb,
            "margin": margin,
            "beats_carrier": beats_d, "beats_availability": beats_b,
            "why": ("the fields add Sharpe over both ablations" if beats_d and beats_b else
                    "the carrier and/or the availability pattern already does the job; the "
                    "fields are decoration"),
            "arm_A_filter_false_reported_not_gated":
                a.get("A_filter_false", {}).get("sharpe"),
        }
    VERDICTS.write_text(json.dumps(out, indent=1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", nargs="*", metavar="ALPHA_ID")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--margin", type=float, default=MARGIN)
    args = ap.parse_args(argv)

    if args.build is not None:
        rows, skipped = build(args.build)
        print(f"{len(rows)} ablation rows -> {POOL.relative_to(ROOT)}")
        for aid, why in skipped:
            print(f"  SKIPPED {aid}: {why}")
        return 0
    if args.judge:
        v = judge(args.margin)
        if not v:
            print("no ablation rows in the journal yet")
            return 1
        for parent, r in v.items():
            if r["verdict"] == "PASS":
                print(f"  PASS      {parent}  candidate {r['sharpe_candidate']:.2f} vs "
                      f"carrier {r['sharpe_carrier_only']:.2f} / avail "
                      f"{r['sharpe_availability_only']:.2f}")
            elif r["verdict"] == "REJECT":
                print(f"  REJECT    {parent}  candidate {r['sharpe_candidate']:.2f} vs "
                      f"carrier {r['sharpe_carrier_only']:.2f} / avail "
                      f"{r['sharpe_availability_only']:.2f} — {r['why']}")
            else:
                print(f"  UNDECIDED {parent}  {r['why']}")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
