#!/usr/bin/env python3
"""logic_check.py — pre-sim LOGIC gate (Khoa 2026-07-17). Runs BEFORE every sim.

Three layers, all grounded in logic_operators.md + the field catalogs:
  L1 OPERATOR-USAGE logic  — the logic_operators.md veto checklist (ILLEGAL / DANGEROUS /
                             USELESS composition patterns), encoded as mechanical checks.
  L2 FIELD-DESCRIPTION logic — each field's TYPE (MATRIX/VECTOR/GROUP) and unit/scale from the
                             catalog must match how the formula uses it (VECTOR needs vec_*;
                             GROUP only as a group arg; count/USD denominators need +1 not 1e-6).
  L3 ECONOMIC logic         — traceability: a hypothesis must exist (bank row or --hypotheses);
                             economic SOUNDNESS is the harness debate's job — L3 here only asserts
                             a non-empty hypothesis is attached, and flags MISSING for review.

Verdicts: ILLEGAL / DANGEROUS block the sim; USELESS / REVIEW warn. Pure, deterministic, no API.

Usage:
  python3 tools/funnel/logic_check.py <targets.json> [--catalog auto|PATH] [--strict] [--json OUT]
  # exit 0 iff no ILLEGAL/DANGEROUS (and, with --strict, no USELESS) rows.
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OPS = {o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json"))}

# ---- field catalog: id -> {type, description, coverage} (CHN per-dataset + JPN + USA) ----
def load_fields():
    """Field ids COLLIDE across regions with different types: `trend_strength_score` is VECTOR in
    CHN (pv27) and MATRIX in USA (pv_tech_indicators); same for accounts_receivable_total_3 /
    capital_expenditure_total (CHN china_stock_funda VECTOR vs USA model227 MATRIX). The old flat
    id->meta index was first-write-wins with the CHN catalogs loaded first, so a CHN entry shadowed
    the USA one and a perfectly legal USA formula was reported ILLEGAL ("must reduce with a vec_*
    op"). Keep the flat index as a fallback, and add a (region, id) index so check_row can resolve
    with the target's own region."""
    idx, by_region = {}, {}
    for p in [ROOT / "fetched/catalog_CHN/fields_per_dataset.jsonl",
              ROOT / "fetched/catalog_CHN/fields.jsonl",
              ROOT / "fetched/catalog_JPN/fields.jsonl",
              ROOT / "fetched/fields_all.jsonl"]:
        if not p.exists():
            continue
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            fid = r.get("id")
            if not fid:
                continue
            meta = {"type": r.get("type"), "coverage": r.get("coverage"),
                    "description": (r.get("description") or "")}
            idx.setdefault(fid, meta)
            reg = r.get("region")
            if reg:
                by_region.setdefault((reg, fid), meta)
    return idx, by_region

FIELDS, FIELDS_BY_REGION = load_fields()
GROUP_ARGS = {"market", "sector", "industry", "subindustry", "country", "exchange"}
VEC_OPS = {"vec_avg", "vec_sum", "vec_count", "vec_max", "vec_min", "vec_range", "vec_stddev"}

# ---- L1 operator-usage veto patterns (logic_operators.md) ----
_VEC = r"(?:vec_avg|vec_sum|vec_count|vec_max|vec_min|vec_range|vec_stddev)"
ILLEGAL = [
    (r"\bts_returns\s*\(", "ts_returns does not exist in RC-85 (phantom op)"),
    (r"\bscale_down\s*\(", "scale_down not in the 85-operator set"),
    (r"\bto_nan\s*\(", "to_nan phantom op"),
    (r"\bregression_neut\s*\(", "regression_neut phantom op"),
    (r"\bgroup_mean\s*\(\s*[^,()]+\s*,\s*[^,()]+\s*\)", "group_mean needs 3 args (x, weight, group)"),
    # vec_* reduces a raw VECTOR field ONLY; every operator's output is MATRIX, so vec ops NEVER
    # wrap an operator call (logic_operators.md D4/footnote 17). vec_*( someop( … ) ) = type error.
    (rf"\b{_VEC}\s*\(\s*[a-z_][a-z0-9_]*\s*\(", "vec_* wraps an operator output (MATRIX) — vec ops take a raw VECTOR field only (never nest)"),
]
# signed / near-zero-crossing bases: log/sqrt -> NaN on negatives, inverse -> pole at 0 (D8, fn 10/21)
_SIGNED_BASE = r"(?:ts_delta|ts_av_diff|ts_min_diff|last_diff_value|ts_regression|subtract|reverse|sign|zscore|normalize|ts_zscore|scale|returns)"
DANGEROUS = [
    (r"\bts_product\s*\(\s*returns\b", "ts_product(returns) is financially degenerate (use 1+returns)"),
    (r"\b1e-0*6\b", "epsilon 1e-6 explodes on sparse/count fields (use +1 on count/USD denominators)"),
    (r"\bpower\s*\(\s*returns\b", "power on signed base (returns) -> NaN/blowup"),
    (r"\blog\s*\(\s*rank\s*\(", "log(rank(x)) — rank floor is exactly 0.0 (log 0 = -inf)"),
    (r"\binverse\s*\(\s*rank\s*\(", "inverse(rank(x)) — rank floor 0 -> pole"),
    # log/sqrt/inverse wrapping a signed or zero-crossing producer -> NaN drops half the book / pole
    (rf"\b(?:log|sqrt|inverse)\s*\(\s*{_SIGNED_BASE}\s*\(", "log/sqrt/inverse on a signed / zero-crossing base -> NaN drops names or pole at 0 (D8)"),
    (rf"\b(?:log|sqrt)\s*\(\s*returns\b", "log/sqrt(returns) — signed base -> NaN"),
]
# USELESS: monotone inner under a rank-based outer = portfolio duplicate
_RANK_OUTER = r"(?:rank|quantile|group_rank|-rank)"
_MONOTONE = r"(?:zscore|normalize|winsorize|signed_power|sigmoid|tanh)"
# global (non-group) CS normalizers are mutually redundant & idempotent (law 5 "one final normalizer");
# stacking any two in either order = one portfolio. Group ops EXCLUDED (within-group demeaning is real,
# cross-classifier group stacking is GOOD per D9/fn4); quantile EXCLUDED (gaussian/cauchy reshape is real).
_GNORM = r"(?:rank|zscore|normalize|scale)"
USELESS = [
    (rf"\b{_RANK_OUTER}\s*\(\s*{_MONOTONE}\s*\(", "rank-based outer absorbs a monotone inner (identical portfolio)"),
    (rf"\b{_GNORM}\s*\(\s*{_GNORM}\s*\(", "normalizer∘normalizer (law 5: one final normalizer — stacking global CS normalizers is one portfolio)"),
    (r"\b(?:zscore|normalize|scale)\s*\(\s*(?:group_rank|group_zscore|quantile)\s*\(", "affine normalizer (zscore/normalize/scale) is absorbed over a rank-family inner (law 2) — portfolio = the inner"),
    (r"\bnormalize\s*\(\s*rank\s*\(", "normalize(rank(x)) is an affine no-op on [0,1]"),
    (r"\breverse\s*\(\s*rank\s*\(", "reverse(rank(x)) == -rank(x) (keep one sign-flip)"),
    (r",\s*market\s*\)", "group_*(x, market) == the plain cross-sectional op (market is one group)"),
    (r"\bquantile\s*\([^)]*driver\s*=\s*uniform", "quantile driver=uniform == rank"),
    # same-classifier group nesting: group_X(group_X(...)) collapses / no-op (D9 fn14). Same function only,
    # to avoid flagging cross-classifier group_zscore(group_rank) which is GOOD.
    (r"\bgroup_rank\s*\(\s*group_rank\s*\(", "group_rank(group_rank(…)) — nested same group op (no-op / collapses to finer)"),
    (r"\bgroup_zscore\s*\(\s*group_zscore\s*\(", "group_zscore(group_zscore(…)) — nested same group op"),
    (r"\bgroup_neutralize\s*\(\s*group_(?:neutralize|zscore)\s*\(", "group_neutralize∘demean — same-classifier stack (D9)"),
]

FIELD_RE = re.compile(r"\b([a-z][a-z0-9_]*[0-9a-z])\b")
OPCALL_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\(")


def _split_top_args(s):
    """Split a call's argument string on top-level commas (respecting nested parens)."""
    args, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1; cur.append(ch)
        elif ch == ")":
            depth -= 1; cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur))
    return [a.strip() for a in args]


def _mirror(b, c):
    """True if branch c is the exact negation of branch b (or vice-versa)."""
    nb, nc = re.sub(r"\s+", "", b), re.sub(r"\s+", "", c)
    return (nc == f"reverse({nb})" or nb == f"reverse({nc})"
            or nc == f"-{nb}" or nb == f"-{nc}"
            or nc == f"-1*{nb}" or nc == f"multiply({nb},-1)")


def if_else_mirror(formula):
    """Return the shared branch expr for any if_else whose two VALUE branches are exact
    negations — if_else(cond, E, reverse(E)) ≡ E·sign(cond): the condition's MAGNITUDE is
    discarded, only its sign survives (logic_operators.md D2/D7; multiply(cond,E) dominates)."""
    hits = []
    for m in re.finditer(r"\bif_else\s*\(", formula):
        i = m.end() - 1          # index of the '(' after if_else
        depth = 0
        for j in range(i, len(formula)):
            if formula[j] == "(":
                depth += 1
            elif formula[j] == ")":
                depth -= 1
                if depth == 0:
                    args = _split_top_args(formula[i + 1:j])
                    if len(args) == 3 and _mirror(args[1], args[2]):
                        hits.append(args[1])
                    break
    return hits


def formula_fields(formula):
    """field-like tokens that are NOT operators and NOT group args."""
    toks = set(FIELD_RE.findall(formula))
    ops = set(OPCALL_RE.findall(formula))
    return {t for t in toks if t not in OPS and t not in ops and t not in GROUP_ARGS
            and (t in FIELDS or t.count("_") >= 1)}


def ops_wrapping(formula, fld):
    """Every operator applied to `fld` — SEEING THROUGH an innermost ts_backfill wrapper
    (config_sweep always wraps fields as ts_backfill(field,N), so the meaningful op is the
    NEXT one out). Returns the set of ops directly around the field or around its backfill."""
    ops = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s*\(\s*" + re.escape(fld) + r"\b", formula))
    # if the field is inside ts_backfill(field,N), also grab the op wrapping that backfill call
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*\(\s*ts_backfill\s*\(\s*" + re.escape(fld) + r"\b", formula):
        ops.add(m.group(1))
    return ops


def _raw_arith_unranked(formula, fld, arith, ranks):
    """True if SOME occurrence of `fld` is fed DIRECTLY into an arithmetic op in `arith`
    (optionally through a ts_backfill wrapper) WITHOUT any op in `ranks` enclosing THAT
    occurrence. Per-occurrence: a rank on a DIFFERENT leg — e.g. the second divide in
    multiply(divide(level,close), rank(divide(level,close))) — does NOT launder the raw
    first leg. A TOP-LEVEL rank/zscore over the whole arithmetic (rank(divide(level,close)))
    still clears it, because that rank's span encloses the occurrence."""
    # argument spans (start '(' index, matching ')' index) of every rank-family op call
    rank_spans = []
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*\(", formula):
        if m.group(1) not in ranks:
            continue
        i = m.end() - 1
        depth = 0
        for j in range(i, len(formula)):
            if formula[j] == "(":
                depth += 1
            elif formula[j] == ")":
                depth -= 1
                if depth == 0:
                    rank_spans.append((i, j))
                    break
    fpat = re.escape(fld)
    for aop in arith:
        pat = re.compile(r"\b" + re.escape(aop) + r"\s*\(\s*(?:ts_backfill\s*\(\s*)?(" + fpat + r")\b")
        for m in re.finditer(pat, formula):
            p = m.start(1)
            if not any(i < p < j for i, j in rank_spans):
                return True
    return False


# description-keyword -> field nature (drives the L2 meaning check)
_NATURE = [
    ("CHANGE",     r"\b(change in|delta|difference|growth|momentum|drift|jensen|reversal)\b"),
    # NORMALIZED = ALREADY cross-sectionally standardized (re-ranking is redundant).
    # NB: ratio/rate/yield/per-share are RAW per-stock values that DO need cross-sectional
    #     rank/zscore — they are NOT normalized. Only percentile/z-score/standardized rank forms are.
    ("NORMALIZED", r"\b(percentile|z-?score|standardi[sz]ed to|cross-section(al)? rank|already ranked|winsori[sz]ed rank)\b"),
    ("BOUNDED01",  r"\b(probability|likelihood|percentile|proportion|fraction)\b"),
    ("LEVEL",      r"\b(stock price|market value|capitali[sz]ation|book value|trading volume|shares outstanding|dollar amount|total assets|total revenue)\b"),
    ("NONNEG",     r"\b(variance|volatility|standard deviation|absolute|magnitude|dispersion)\b"),
]


# categorical / enum FLAG fields (e.g. "…- forecast type (revision/new/…)") carry a level noun
# at the START of their description but are small integer TYPE CODES, not levels — the numeric-nature
# semantic checks (esp. the LEVEL arith block) must not apply to them (Khoa 2026-07-24).
_CATEGORICAL = re.compile(r"\bforecast type\b|revision/new")

# A dimensionless RATIO (X divided by Y, per-share, margin, %-of) is already scale-free across
# stocks, so it belongs in arithmetic — the LEVEL tokens inside it (e.g. "total assets"/"total
# revenue"/"book value") are a DENOMINATOR, not the field's own scale. Suppress the LEVEL tag
# when ratio phrasing is present so the L2 arith guard stops false-blocking these (a ratio is
# still NOT normalized — it keeps needing rank/zscore) (Khoa 2026-07-24).
_RATIO = re.compile(r"(divided by|\bratio\b|per share|per dollar|per unit|\bmargin\b|"
                    r"percent(age)? of|% of|fraction of|proportion of|share of|_to_|-to-| to total )")


# "Nth percentile" (e.g. "50th percentile", "95th-percentile") names an AGGREGATION statistic /
# threshold — the MEDIAN (50th) of analyst EPS/FCF estimates, or a 95th-pct similarity threshold —
# which is a RAW UNBOUNDED level, NOT a cross-sectional percentile RANK. Strip it before nature
# tagging so those raw levels aren't false-tagged NORMALIZED/BOUNDED01 (which would drop every
# ts_zscore/ts_rank variant of them from the sweep). Genuine peer-group percentiles ("percentile
# within industry", "0–100 percentile") have no leading digit and keep matching (Khoa 2026-07-24).
_ORDINAL_PCTILE = re.compile(r"\d+(?:st|nd|rd|th)[\s-]*percentile")


def field_nature(desc):
    desc = desc.lower()   # all _NATURE/_RATIO/_CATEGORICAL/_ORDINAL_PCTILE patterns are lowercase literals
    if _CATEGORICAL.search(desc):
        return set()
    desc = _ORDINAL_PCTILE.sub(" ", desc)
    nat = {tag for tag, pat in _NATURE if re.search(pat, desc)}
    if "LEVEL" in nat and _RATIO.search(desc):
        nat.discard("LEVEL")
    return nat


def _snip(desc):
    return (desc[:46] + "…") if len(desc) > 46 else desc


def check_row(t):
    """Return list of (layer, verdict, reason)."""
    f = t.get("formula") or ""
    out = []
    # L1 operator-usage
    for pat, why in ILLEGAL:
        if re.search(pat, f):
            out.append(("L1", "ILLEGAL", why))
    for pat, why in DANGEROUS:
        if re.search(pat, f):
            out.append(("L1", "DANGEROUS", why))
    for pat, why in USELESS:
        if re.search(pat, f):
            out.append(("L1", "USELESS", why))
    if if_else_mirror(f):
        out.append(("L1", "USELESS", "if_else(cond, E, reverse(E)) ≡ E·sign(cond) — the condition's "
                    "magnitude is discarded (only its sign survives); prefer multiply(cond_signal, E) "
                    "which keeps both (logic_operators.md D2/D7)"))
    # settings truncation legality (belt-and-suspenders vs validate_targets)
    tr = (t.get("settings") or {}).get("truncation")
    if isinstance(tr, (int, float)) and tr > 1:
        out.append(("L1", "ILLEGAL", f"truncation {tr} > 1"))
    # L2 field-description logic — does the operator MEAN something given what the field
    # measures (per its own description), or is it just rationalized? (Khoa 2026-07-17)
    region = (t.get("settings") or {}).get("region")
    for fld in sorted(formula_fields(f)):   # sorted -> deterministic finding order (set iteration is hash-seeded)
        # resolve in the target's OWN region first — ids collide across regions with different types
        meta = FIELDS_BY_REGION.get((region, fld)) or FIELDS.get(fld)
        if not meta:
            out.append(("L2", "REVIEW", f"field {fld} not in catalog — verify id/delay"))
            continue
        ftype = (meta.get("type") or "").upper()
        desc = (meta.get("description") or "").lower()
        wraps = ops_wrapping(f, fld)   # every op applied directly to this field
        # ---- type consistency (hard) ----
        if ftype == "VECTOR" and not (wraps & VEC_OPS):
            out.append(("L2", "ILLEGAL", f"{fld} is VECTOR — must reduce with a vec_* op first"))
        if ftype and ftype != "VECTOR" and (wraps & VEC_OPS):
            out.append(("L2", "ILLEGAL", f"{fld} is {ftype} (not a VECTOR) — vec_* ops reduce a raw VECTOR field only"))
        if ftype == "GROUP":
            out.append(("L2", "ILLEGAL", f"{fld} is a GROUP field — only a group argument, never a signal"))
        # ---- description-nature vs operator (meaning vs rationalization) ----
        nat = field_nature(desc)
        if "CHANGE" in nat and (wraps & {"ts_delta", "ts_av_diff", "last_diff_value"}):
            out.append(("L2", "REVIEW", f"{fld} is already a CHANGE ('{_snip(desc)}') — ts_delta double-differences; meaningful only if 2nd-order is intended"))
        if "NORMALIZED" in nat and (wraps & {"zscore", "normalize", "rank", "ts_zscore", "quantile"}):
            out.append(("L2", "USELESS", f"{fld} is already normalized/bounded ('{_snip(desc)}') — re-normalizing adds no cross-sectional info"))
        if "BOUNDED01" in nat and (wraps & {"log", "inverse"}):
            out.append(("L2", "DANGEROUS", f"{fld} is bounded near [0,1] ('{_snip(desc)}') — log/inverse blows up at 0"))
        if "LEVEL" in nat and _raw_arith_unranked(f, fld, {"multiply", "divide", "add", "subtract", "power"}, {"rank", "zscore", "normalize", "quantile", "group_rank", "group_zscore"}):
            out.append(("L2", "DANGEROUS", f"{fld} is a raw LEVEL ('{_snip(desc)}') — feeding it into arithmetic without rank/zscore mixes scales (no cross-sectional meaning)"))
    # L3 economic traceability
    hyp = t.get("hypothesis") or t.get("hypothesis_id") or (t.get("label") or "")
    if not str(hyp).strip():
        out.append(("L3", "REVIEW", "no hypothesis attached (economic traceability) — harness must attach one"))
    return out


def check(targets, strict=False):
    rows = []
    n_block = 0
    for i, t in enumerate(targets):
        tag = t.get("old_id") or t.get("id") or f"row{i}"
        findings = check_row(t)
        verdict = "PASS"
        if any(v == "ILLEGAL" for _, v, _ in findings):
            verdict = "ILLEGAL"
        elif any(v == "DANGEROUS" for _, v, _ in findings):
            verdict = "DANGEROUS"
        elif any(v == "USELESS" for _, v, _ in findings):
            verdict = "USELESS"
        elif any(v == "REVIEW" for _, v, _ in findings):
            verdict = "REVIEW"
        blocking = verdict in ("ILLEGAL", "DANGEROUS") or (strict and verdict == "USELESS")
        if blocking:
            n_block += 1
        rows.append({"id": tag, "verdict": verdict, "blocking": blocking,
                     "findings": [{"layer": l, "verdict": v, "reason": r} for l, v, r in findings]})
    return {"ok": n_block == 0, "n": len(targets), "n_block": n_block, "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets")
    ap.add_argument("--strict", action="store_true", help="also block USELESS rows")
    ap.add_argument("--json", default=None, help="write full report JSON here")
    a = ap.parse_args(argv)
    targets = json.load(open(a.targets))
    if isinstance(targets, dict):
        targets = targets.get("targets") or [targets]
    res = check(targets, strict=a.strict)
    from collections import Counter
    c = Counter(r["verdict"] for r in res["rows"])
    print(f"logic_check: {res['n']} rows | {dict(c)} | blocking={res['n_block']}")
    for r in res["rows"]:
        if r["blocking"]:
            print(f"  BLOCK {r['id']} [{r['verdict']}]: " + "; ".join(f['reason'] for f in r["findings"] if f["verdict"] in ("ILLEGAL", "DANGEROUS")))
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1, ensure_ascii=False)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
