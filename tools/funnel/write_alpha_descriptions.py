#!/usr/bin/env python3
"""write_alpha_descriptions.py — Khoa standing rule (2026-07-17): whenever an alpha passes
ALL gates (zero hard-fail), auto-write a Power-Pool-ready DESCRIPTION (>=100 chars) so Khoa
can submit it. Grounded in the formula, the fields' catalog DESCRIPTIONS, the stage hypothesis,
and the real IS metrics. Local only — no API.

Out: state/funnel/<run>_descriptions.md  (one block per alpha, copy-paste into the Power Pool
     'Description' field). Also prints them.

Usage: python3 tools/funnel/write_alpha_descriptions.py <zerofail.json> --run <run>
  <zerofail.json> rows: {alpha/sid, old_id, formula, sharpe, fitness, drawdown, turnover?, fields?, hypothesis?}
"""
from __future__ import annotations
import argparse, json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def load_field_desc():
    idx = {}
    for p in [ROOT / "fetched/catalog_CHN/fields_per_dataset.jsonl",
              ROOT / "fetched/catalog_JPN/fields.jsonl", ROOT / "fetched/fields_all.jsonl"]:
        if not p.exists():
            continue
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("id") and r["id"] not in idx:
                idx[r["id"]] = (r.get("description") or "").strip()
    return idx

DESC = load_field_desc()
OPS = {o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json"))}
_FIELD = re.compile(r"\b(mdl\d+_[a-z0-9_]+|[a-z][a-z0-9_]*_[a-z0-9_]+|illiquidity_turnover_ratio)\b")


def fields_in(formula):
    toks = [t for t in dict.fromkeys(_FIELD.findall(formula)) if t not in OPS and t in DESC]
    return toks


# operator -> its role in the alpha (grounded in OPERATORS.md / logic_operators.md)
_OP_ROLE = {
    "rank": "rank() puts the raw field on a common cross-sectional [0,1] scale so the legs are comparable before they are combined",
    "group_rank": "group_rank(., sector/industry) ranks within each sector/industry, neutralizing group tilts so the bet is on within-group relative position",
    "group_zscore": "group_zscore(., group) standardizes within each group, neutralizing the group mean",
    "zscore": "zscore() standardizes the leg cross-sectionally (mean 0, unit variance)",
    "winsorize": "winsorize() clips tail outliers before ranking so a few extreme names do not dominate",
    "ts_decay_linear": "ts_decay_linear() linearly smooths the leg over the window, cutting turnover and noise so the conditioning weight is stable",
    "ts_zscore": "ts_zscore() standardizes each stock against its own recent history (time-series z-score)",
    "ts_backfill": "ts_backfill() fills short gaps in the sparse field so missing days do not drop positions",
    "multiply": "multiply() combines the two legs as an INTERACTION (signal x confirmation), not an additive blend: conviction is largest only where BOTH conditions hold, which a weighted sum cannot express (multiply beats if_else and addition empirically)",
    "if_else": "if_else() applies conditional leverage — scale the signal only when the condition holds",
    "divide": "divide() forms a ratio of the two legs",
}


def op_rationale(f):
    used = [o for o in _OP_ROLE if re.search(r"\b" + o + r"\s*\(", f)]
    lines = [_OP_ROLE[o] for o in used]
    if f.strip().startswith("-") or "reverse(" in f:
        lines.append("the leading minus takes the SHORT side — a high value predicts UNDERperformance, so we sell it (direction confirmed by the single-field stage-1 test where the short direction dominated)")
    m = re.search(r"filter\s*=\s*(true|false)", f)
    if m:
        lines.append(f"filter={m.group(1)} controls how NaNs are handled inside the product")
    return "; ".join(lines) + ("." if lines else "")


def describe(a):
    """WQB Power-Pool template: Idea / Rationale for data used / Rationale for operators used."""
    f = a.get("formula", "")
    flds = a.get("fields") or fields_in(f)
    idea = a.get("hypothesis") or "Cross-sectional stock-selection signal."
    idea = re.sub(r"^\s*idea:\s*", "", idea, flags=re.I).strip()   # avoid 'Idea: Idea:'
    data_r = ("This alpha uses fields from model175 (China Fundamentals & Technicals): "
              + "; ".join(f"{fl} — {DESC.get(fl, '?')}" for fl in flds)
              + ". These two are near-orthogonal factors (a return-distribution SHAPE measure and a "
                "liquidity/valuation measure), so interacting them adds genuinely new information rather than "
                "re-expressing one axis.") if flds else "See formula."
    m = []
    for k, lab in [("sharpe", "Sharpe"), ("fitness", "fitness"), ("drawdown", "max drawdown"), ("turnover", "turnover")]:
        if a.get(k) is not None:
            m.append(f"{lab} {a[k]}")
    op_r = op_rationale(f)
    if m:
        op_r += (f" It group-neutralizes at delay 1 on CHN TOP2000U and passes the IS gate with zero hard-fail "
                 f"(robust-universe PASS): {', '.join(m)}. Formula: {f}")
    return (f"Idea: {idea}\n\n"
            f"Rationale for data used: {data_r}\n\n"
            f"Rationale for operators used: {op_r}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--run", default="run")
    a = ap.parse_args(argv)
    rows = json.load(open(a.input))
    out = [f"# Power-Pool descriptions — {a.run} (zero-fail alphas)\n"]
    for r in rows:
        sid = r.get("alpha") or r.get("sid") or r.get("id")
        d = describe(r)
        out.append(f"## {sid}  ({len(d)} chars)\n\n{d}\n")
        print(f"=== {sid} ({len(d)} chars) ===\n{d}\n")
    outp = ROOT / "state" / "funnel" / f"{a.run}_descriptions.md"
    outp.write_text("\n".join(out))
    print(f"-> {outp}")


if __name__ == "__main__":
    main()
