#!/usr/bin/env python3
"""logic_matrix.py — EXHAUSTIVE operator×operator and operator×field logic audit
(Khoa 2026-07-17 goal: "kiểm tra hàng loạt kết hợp logic triệt để cách sử dụng
operators với operators và operators với field").

What it does, deterministically and with NO API:
  1. op×op  — build outer(inner(FIELD)) for EVERY ordered pair of the 85 RC operators,
              run it through logic_check L1 (operator-composition layer), and compare the
              verdict to the logic_operators.md ground-truth 9×9 family matrix.
  2. op×field — for a representative real field of every catalog NATURE
                (CHANGE / NORMALIZED / BOUNDED01 / LEVEL / NONNEG / plain) and every field
                TYPE (MATRIX / VECTOR / GROUP), apply each operator and run logic_check L2.
  3. veto-checklist — encode each ILLEGAL/DANGEROUS/USELESS bullet from logic_operators.md
                as a concrete formula and measure logic_check's catch-rate.

Output = a coverage report that surfaces exactly two failure modes:
  GAP  (under-block): ground truth says ILLEGAL/DANGEROUS/USELESS, logic_check lets it PASS.
  FP   (over-block):  ground truth says GOOD, logic_check flags it.

Deterministic: same inputs -> byte-identical output (sorted, no RNG, no clock).

Usage:
  python3 tools/funnel/logic_matrix.py [--out state/funnel/logic_matrix_report.md] [--json OUT]
"""
from __future__ import annotations
import argparse, json, pathlib, sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import logic_check as lc

OPS = sorted(o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json")))

# ---- family membership (grounded in logic_operators.md 9×9 header) -------------------
FAMILY = {
    # rankCS = rank/quantile/group_rank (matrix explicitly groups group_rank here)
    "rank": "rankCS", "quantile": "rankCS", "group_rank": "rankCS",
    # shapeCS = zscore/normalize/scale/winsorize
    "zscore": "shapeCS", "normalize": "shapeCS", "scale": "shapeCS", "winsorize": "shapeCS",
    # tsSmooth = ts_mean/ts_decay_linear/ts_backfill (+ passthrough time ops)
    "ts_mean": "tsSmooth", "ts_decay_linear": "tsSmooth", "ts_backfill": "tsSmooth",
    "ts_sum": "tsSmooth", "ts_delay": "tsSmooth", "ts_target_tvr_decay": "tsSmooth",
    "group_backfill": "tsSmooth",
    # tsChange = ts_delta/ts_regression/last_diff_value (+ diff family)
    "ts_delta": "tsChange", "ts_regression": "tsChange", "last_diff_value": "tsChange",
    "ts_av_diff": "tsChange", "ts_min_diff": "tsChange", "days_from_last_change": "tsChange",
    "ts_min_max_diff": "tsChange", "ts_step": "tsChange",
    # tsShape = ts_rank/ts_quantile/ts_zscore/ts_scale
    "ts_rank": "tsShape", "ts_quantile": "tsShape", "ts_zscore": "tsShape", "ts_scale": "tsShape",
    # group = the remaining group_*
    "group_zscore": "group", "group_neutralize": "group", "group_mean": "group",
    "group_scale": "group", "group_extra": "group", "group_cartesian_product": "group",
    "bucket": "group",
    # vector = vec_*
    "vec_avg": "vector", "vec_sum": "vector", "vec_count": "vector", "vec_max": "vector",
    "vec_min": "vector", "vec_range": "vector", "vec_stddev": "vector",
    # cond = if_else/trade_when/comparisons/logicals
    "if_else": "cond", "trade_when": "cond", "greater": "cond", "greater_equal": "cond",
    "less": "cond", "less_equal": "cond", "equal": "cond", "not_equal": "cond",
    "and": "cond", "or": "cond", "not": "cond", "is_nan": "cond",
    # arithRisk = power/log/sqrt/inverse/divide/sigmoid/tanh/abs (+ arithmetic)
    "power": "arithRisk", "log": "arithRisk", "sqrt": "arithRisk", "inverse": "arithRisk",
    "divide": "arithRisk", "sigmoid": "arithRisk", "tanh": "arithRisk", "abs": "arithRisk",
    "signed_power": "arithRisk", "add": "arithRisk", "subtract": "arithRisk",
    "multiply": "arithRisk", "max": "arithRisk", "min": "arithRisk", "reverse": "arithRisk",
    "sign": "arithRisk", "densify": "arithRisk",
    # other (moments/2-series/special) — enumerated but not matrix-scored
    "ts_std_dev": "other", "ts_skewness": "other", "ts_entropy": "other", "ts_corr": "other",
    "ts_covariance": "other", "ts_count_nans": "other", "ts_product": "other",
    "ts_arg_max": "other", "ts_arg_min": "other", "ts_min_max_cps": "other",
    "hump": "other", "kth_element": "other", "inst_pnl": "other",
    "regression_proj": "other", "vector_neut": "other", "vector_proj": "other",
}
for o in OPS:
    FAMILY.setdefault(o, "other")

# ---- call templates: op(primary_arg, <fixed extra args>) -----------------------------
# secondary operands use a real, plain field so the FORMULA parses; L1 findings are
# filtered to operator-composition only, so the 2nd field does not contaminate op×op.
_SEC = "volume"
_GRP = "sector"
def _t(op):
    T = {
        "rank": f"rank(%s)", "zscore": "zscore(%s)", "normalize": "normalize(%s)",
        "scale": "scale(%s)", "winsorize": "winsorize(%s,std=4)", "quantile": "quantile(%s)",
        "group_rank": f"group_rank(%s,{_GRP})", "group_zscore": f"group_zscore(%s,{_GRP})",
        "group_neutralize": f"group_neutralize(%s,{_GRP})", "group_mean": f"group_mean(%s,1,{_GRP})",
        "group_scale": f"group_scale(%s,{_GRP})", "group_extra": f"group_extra(%s,1,{_GRP})",
        "group_backfill": f"group_backfill(%s,{_GRP},20)",
        "group_cartesian_product": f"group_cartesian_product(%s,industry)",
        "bucket": 'bucket(%s,range="0,1,0.1")',
        "ts_mean": "ts_mean(%s,22)", "ts_sum": "ts_sum(%s,22)", "ts_delay": "ts_delay(%s,5)",
        "ts_decay_linear": "ts_decay_linear(%s,10)", "ts_backfill": "ts_backfill(%s,22)",
        "ts_target_tvr_decay": "ts_target_tvr_decay(%s,0.1)",
        "ts_delta": "ts_delta(%s,5)", "ts_regression": f"ts_regression(%s,{_SEC},22)",
        "last_diff_value": "last_diff_value(%s,63)", "ts_av_diff": "ts_av_diff(%s,22)",
        "ts_min_diff": "ts_min_diff(%s,22)", "days_from_last_change": "days_from_last_change(%s)",
        "ts_min_max_diff": "ts_min_max_diff(%s,22)", "ts_step": "ts_step(%s,22)",
        "ts_rank": "ts_rank(%s,22)", "ts_quantile": 'ts_quantile(%s,22,driver="gaussian")',
        "ts_zscore": "ts_zscore(%s,22)", "ts_scale": "ts_scale(%s,22)",
        "ts_std_dev": "ts_std_dev(%s,22)", "ts_skewness": "ts_skewness(%s,22)",
        "ts_entropy": "ts_entropy(%s,22)", "ts_corr": f"ts_corr(%s,{_SEC},22)",
        "ts_covariance": f"ts_covariance(%s,{_SEC},22)", "ts_count_nans": "ts_count_nans(%s,22)",
        "ts_product": "ts_product(%s,22)", "ts_arg_max": "ts_arg_max(%s,22)",
        "ts_arg_min": "ts_arg_min(%s,22)", "ts_min_max_cps": "ts_min_max_cps(%s,22)",
        "hump": "hump(%s,0.01)", "kth_element": "kth_element(%s,5)",
        "power": "power(%s,2)", "log": "log(%s)", "sqrt": "sqrt(%s)", "inverse": "inverse(%s)",
        "divide": f"divide(%s,{_SEC})", "sigmoid": "sigmoid(%s)", "tanh": "tanh(%s)",
        "abs": "abs(%s)", "signed_power": "signed_power(%s,0.5)", "add": f"add(%s,{_SEC})",
        "subtract": f"subtract(%s,{_SEC})", "multiply": f"multiply(%s,{_SEC})",
        "max": f"max(%s,{_SEC})", "min": f"min(%s,{_SEC})", "reverse": "reverse(%s)",
        "sign": "sign(%s)", "densify": "densify(%s)",
        # non-mirror branches so op×op tests generic cond-wrapping (GOOD); the mirror
        # anti-pattern is tested explicitly in the checklist.
        "if_else": f"if_else(greater(%s,0),{_SEC},close)",
        "trade_when": f"trade_when(greater({_SEC},0),%s,-1)", "not": "not(%s)",
        "greater": "greater(%s,0)", "greater_equal": "greater_equal(%s,0)",
        "less": "less(%s,0)", "less_equal": "less_equal(%s,0)", "equal": "equal(%s,0)",
        "not_equal": "not_equal(%s,0)", "and": f"and(greater(%s,0),greater({_SEC},0))",
        "or": f"or(greater(%s,0),greater({_SEC},0))", "is_nan": "is_nan(%s)",
        "vec_avg": "vec_avg(%s)", "vec_sum": "vec_sum(%s)", "vec_count": "vec_count(%s)",
        "vec_max": "vec_max(%s)", "vec_min": "vec_min(%s)", "vec_range": "vec_range(%s)",
        "vec_stddev": "vec_stddev(%s)",
        "regression_proj": f"regression_proj(%s,{_SEC})", "vector_neut": f"vector_neut(%s,{_SEC})",
        "vector_proj": f"vector_proj(%s,{_SEC})", "inst_pnl": "inst_pnl(%s)",
    }
    return T.get(op, f"{op}(%s)")

def build(outer, inner, field):
    return _t(outer) % (_t(inner) % field)

# ---- ground-truth 9×9 family matrix (logic_operators.md "Composition matrix") ---------
# rows = inner family, cols = outer family. Verdicts: GOOD / COND / USELESS / DANGEROUS / ILLEGAL
FAMS = ["rankCS", "shapeCS", "tsSmooth", "tsChange", "tsShape", "group", "vector", "cond", "arithRisk"]
MATRIX = {
    "rankCS":   ["USELESS","USELESS","GOOD","GOOD","GOOD","COND","ILLEGAL","GOOD","COND"],
    "shapeCS":  ["USELESS","COND","GOOD","GOOD","GOOD","COND","ILLEGAL","GOOD","COND"],
    "tsSmooth": ["GOOD","GOOD","COND","GOOD","GOOD","GOOD","ILLEGAL","GOOD","COND"],
    "tsChange": ["GOOD","GOOD","GOOD","COND","GOOD","GOOD","ILLEGAL","GOOD","DANGEROUS"],
    "tsShape":  ["COND","GOOD","GOOD","GOOD","COND","GOOD","ILLEGAL","GOOD","COND"],
    "group":    ["COND","COND","GOOD","GOOD","GOOD","COND","ILLEGAL","GOOD","COND"],
    "vector":   ["GOOD","GOOD","GOOD","COND","GOOD","GOOD","ILLEGAL","GOOD","COND"],
    "cond":     ["COND","COND","GOOD","GOOD","GOOD","GOOD","ILLEGAL","GOOD","GOOD"],
    "arithRisk":["USELESS","COND","COND","COND","USELESS","COND","ILLEGAL","COND","DANGEROUS"],
}
def expected(inner_fam, outer_fam):
    if inner_fam not in MATRIX or outer_fam not in FAMS:
        return None
    return MATRIX[inner_fam][FAMS.index(outer_fam)]

FLAGGED = {"ILLEGAL", "DANGEROUS", "USELESS"}

# ---- PRECISE known-bad predicates (grounded in specific footnotes, not coarse cells) --
# The 9×9 matrix summarizes whole family cells; e.g. arithRisk→arithRisk="DANGEROUS" but
# abs(abs(x)) is only idempotent-USELESS, not a crash. So a matrix "gap" is a REAL defect
# only if the *specific* op-pair matches a precise footnote rule below. Otherwise the matrix
# is coarser than reality and the pair is benign — not a checker bug.
_VECO = {"vec_avg", "vec_sum", "vec_count", "vec_max", "vec_min", "vec_range", "vec_stddev"}
_RISK = {"log", "sqrt", "inverse"}
_SIGNED = {"ts_delta", "ts_av_diff", "ts_min_diff", "last_diff_value", "ts_regression",
           "subtract", "reverse", "sign", "zscore", "normalize", "ts_zscore", "scale"}
_GN = {"rank", "zscore", "normalize", "scale"}
_RKO = {"rank", "quantile", "group_rank"}
_MONO = {"zscore", "normalize", "winsorize", "signed_power", "sigmoid", "tanh"}

def precise_bad(outer, inner):
    """(class, reason) if the specific pair matches a precise footnote rule, else None."""
    if outer in _VECO:
        return "ILLEGAL", "vec_* on operator output (fn17)"
    if outer in _RISK and inner in _SIGNED:
        return "DANGEROUS", "log/sqrt/inverse on signed/zero-crossing base (fn10/21)"
    if outer in _GN and inner in _GN:
        return "USELESS", "normalizer∘normalizer (law 5)"
    if outer in {"zscore", "normalize", "scale"} and inner in {"group_rank", "group_zscore", "quantile"}:
        return "USELESS", "affine normalizer absorbed over rank-family inner (law 2)"
    if outer in _RKO and inner in _MONO:
        return "USELESS", "rank-based absorbs monotone inner (law 1)"
    if outer in ("group_rank", "group_zscore") and inner == outer:
        return "USELESS", "nested same group op (fn14)"
    return None


def l1_verdict(formula):
    """Run logic_check but keep only operator-composition (L1) findings, so op×op is
    isolated from field-nature (L2) and hypothesis (L3) noise."""
    findings = [f for f in lc.check_row({"formula": formula, "label": "x"}) if f[0] == "L1"]
    for order in ("ILLEGAL", "DANGEROUS", "USELESS"):
        if any(v == order for _, v, _ in findings):
            return order, findings
    return "OK", findings


def op_by_op():
    """Enumerate every ordered operator pair; classify each mismatch as a REAL defect
    (matches a precise footnote rule but logic_check passes it) vs COARSE (matrix cell
    over-generalizes; the specific pair is benign) vs FP (matrix GOOD, checker flags)."""
    rows, real_gaps, coarse, fps = [], [], [], []
    NEUTRAL = "operating_income"     # plain MATRIX field, no strong nature keyword
    for outer in OPS:
        for inner in OPS:
            formula = build(outer, inner, NEUTRAL)
            got, findings = l1_verdict(formula)
            exp = expected(FAMILY[inner], FAMILY[outer])
            pb = precise_bad(outer, inner)
            rec = {"outer": outer, "inner": inner, "outer_fam": FAMILY[outer],
                   "inner_fam": FAMILY[inner], "formula": formula, "got": got,
                   "expected_family": exp, "precise": pb[1] if pb else None,
                   "why": "; ".join(r for _, _, r in findings) or None}
            rows.append(rec)
            if pb and got == "OK":
                rec["precise_class"] = pb[0]
                real_gaps.append(rec)          # a precise known-bad the checker misses
            elif exp in FLAGGED and pb is None and got == "OK":
                coarse.append(rec)             # matrix coarser than reality — benign pair
            if exp == "GOOD" and got in FLAGGED:
                fps.append(rec)
    return rows, real_gaps, coarse, fps


# ---- op×field: representative field per (type, nature) --------------------------------
def _rep_fields():
    """Pick a DISTINCT real catalog field for each nature/type. Prefer SINGLE-nature fields
    so each row isolates one nature (some fields legitimately carry several — e.g. a
    'change in percentile rank' is CHANGE+NORMALIZED+BOUNDED01 at once)."""
    reps = {}
    for fid, meta in sorted(lc.FIELDS.items()):
        desc = (meta.get("description") or "").lower()
        typ = (meta.get("type") or "").upper()
        nats = lc.field_nature(desc)
        if typ == "VECTOR":
            reps.setdefault("VECTOR", fid); continue
        if typ == "GROUP":
            reps.setdefault("GROUP", fid); continue
        if typ not in ("MATRIX", "", None) or not desc:
            continue
        if len(nats) == 1:
            reps.setdefault(next(iter(nats)), fid)
        elif not nats:
            reps.setdefault("plain", fid)
    return reps


# operators whose meaning on a field is worth auditing (the ones L2 knows about + neighbours)
_FIELD_OPS = ["rank", "zscore", "normalize", "quantile", "ts_rank", "ts_zscore", "ts_delta",
              "ts_av_diff", "last_diff_value", "log", "inverse", "sqrt", "power",
              "multiply", "divide", "add", "subtract", "group_rank", "vec_avg", "signed_power"]

def op_by_field():
    reps = _rep_fields()
    rows = []
    for label, fid in sorted(reps.items()):
        for op in _FIELD_OPS:
            formula = _t(op) % fid
            findings = [f for f in lc.check_row({"formula": formula, "label": "x"}) if f[0] == "L2"]
            verdict = "OK"
            for order in ("ILLEGAL", "DANGEROUS", "USELESS", "REVIEW"):
                if any(v == order for _, v, _ in findings):
                    verdict = order
                    break
            rows.append({"nature": label, "field": fid, "op": op, "formula": formula,
                         "verdict": verdict,
                         "why": "; ".join(r for _, _, r in findings) or None})
    return reps, rows


# ---- veto-checklist catch-rate: concrete formula per known-bad bullet -----------------
# (formula, expected_class, human_tag). If logic_check's verdict class != expected -> a GAP.
CHECKLIST = [
    # ILLEGAL
    ("rank(ts_returns(close,5))", "ILLEGAL", "ts_returns phantom op"),
    ("scale_down(rank(close))", "ILLEGAL", "scale_down phantom op"),
    ("group_mean(operating_income,sector)", "ILLEGAL", "group_mean 2-arg"),
    ("truncation>1", "ILLEGAL", "truncation>1 (settings)"),
    # DANGEROUS
    ("ts_product(returns,22)", "DANGEROUS", "ts_product(returns)"),
    ("power(returns,2)", "DANGEROUS", "power(returns)"),
    ("log(rank(operating_income))", "DANGEROUS", "log(rank)"),
    ("inverse(rank(operating_income))", "DANGEROUS", "inverse(rank)"),
    ("divide(operating_income,add(assets,1e-6))", "DANGEROUS", "+1e-6 epsilon"),
    # USELESS
    ("rank(zscore(operating_income))", "USELESS", "rank(monotone) — zscore"),
    ("rank(winsorize(operating_income,std=4))", "USELESS", "rank(winsorize)"),
    ("rank(signed_power(operating_income,0.5))", "USELESS", "rank(signed_power)"),
    ("normalize(rank(operating_income))", "USELESS", "normalize(rank)"),
    ("reverse(rank(operating_income))", "USELESS", "reverse(rank)"),
    ("group_rank(operating_income,market)", "USELESS", "group_*(x,market)"),
    ("quantile(operating_income,driver=uniform)", "USELESS", "quantile driver=uniform"),
    # patterns added 2026-07-17 from this audit
    ("vec_avg(ts_backfill(sales_vector,22))", "ILLEGAL", "vec_* on operator output"),
    ("vec_max(zscore(operating_income))", "ILLEGAL", "vec_* on top of an operator output"),
    ("log(subtract(close,vwap))", "DANGEROUS", "log on signed base"),
    ("sqrt(ts_delta(close,5))", "DANGEROUS", "sqrt on signed change"),
    ("inverse(zscore(operating_income))", "DANGEROUS", "inverse on zero-crossing zscore"),
    ("divide(operating_income,add(assets,1e-6))", "DANGEROUS", "1e-6 epsilon via add()"),
    ("group_rank(group_rank(operating_income,sector),sector)", "USELESS", "nested same group op"),
    ("normalize(group_rank(operating_income,sector))", "USELESS", "normalizer∘normalizer"),
    ("scale(rank(operating_income))", "USELESS", "normalizer∘normalizer (scale∘rank)"),
    ("if_else(greater(zscore(operating_income),0),rank(sales),reverse(rank(sales)))",
     "USELESS", "if_else mirror-branch sign-collapse"),
]
def checklist_catch():
    rows = []
    for formula, exp, tag in CHECKLIST:
        if formula == "truncation>1":
            findings = lc.check_row({"formula": "rank(operating_income)",
                                     "settings": {"truncation": 1.5}, "label": "x"})
        else:
            findings = lc.check_row({"formula": formula, "label": "x"})
        cls = "OK"
        for order in ("ILLEGAL", "DANGEROUS", "USELESS"):
            if any(v == order for _, v, _ in findings):
                cls = order
                break
        rows.append({"tag": tag, "formula": formula, "expected": exp, "got": cls,
                     "caught": cls == exp,
                     "why": "; ".join(r for _, _, r in findings) or None})
    return rows


def render(rows_oo, real_gaps, coarse, fps, reps, rows_of, chk):
    L = []
    L.append("# Logic-combination audit — operator×operator & operator×field\n")
    L.append(f"Operators enumerated: {len(OPS)}  |  op×op pairs: {len(rows_oo)}  "
             f"(= {len(OPS)}²)\n")

    # checklist catch-rate
    caught = sum(1 for r in chk if r["caught"])
    L.append(f"## 1. Veto-checklist catch-rate: {caught}/{len(chk)} known-bad patterns caught\n")
    L.append("| known-bad pattern | expected | logic_check | caught |")
    L.append("|---|---|---|---|")
    for r in chk:
        L.append(f"| `{r['formula']}` — {r['tag']} | {r['expected']} | {r['got']} | "
                 f"{'✅' if r['caught'] else '❌ GAP'} |")
    L.append("")

    # op×op — real defects vs coarse-cell vs FP
    L.append(f"## 2. op×op audit: {len(real_gaps)} REAL defects, {len(fps)} false-positives, "
             f"{len(coarse)} coarse-cell (matrix over-generalizes — benign)\n")
    L.append("### REAL defects — a *precise* footnote rule says bad, but logic_check PASSES")
    if real_gaps:
        by = defaultdict(list)
        for g in real_gaps:
            by[(g.get("precise_class"), g["precise"])].append(g)
        L.append("| class | precise rule | count | example formula |")
        L.append("|---|---|---|---|")
        for (cls, why), gl in sorted(by.items(), key=lambda kv: str(kv[0])):
            L.append(f"| {cls} | {why} | {len(gl)} | `{gl[0]['formula']}` |")
    else:
        L.append("_none — every precise known-bad pattern is now caught._")
    L.append("")
    L.append("### False-positives — family matrix says GOOD, logic_check FLAGS")
    if fps:
        by = defaultdict(list)
        for g in fps:
            by[(g["inner_fam"], g["outer_fam"], g["got"])].append(g)
        L.append("| inner_fam → outer_fam | logic_check | count | example | reason |")
        L.append("|---|---|---|---|---|")
        for (inf, ouf, got), gl in sorted(by.items()):
            L.append(f"| {inf} → {ouf} | {got} | {len(gl)} | `{gl[0]['formula']}` | {gl[0]['why']} |")
    else:
        L.append("_none — no GOOD family-cell composition is wrongly blocked._")
    L.append("")
    L.append("### Coarse-cell (NOT defects) — the 9×9 matrix marks the whole cell bad, but the")
    L.append("specific pair is benign (e.g. `abs(abs(x))` is idempotent-useless, not a crash;")
    L.append("`rank(abs(x))` folds sign so it is NOT a monotone duplicate). Left unblocked on purpose.")
    if coarse:
        by = Counter((g["inner_fam"], g["outer_fam"], g["expected_family"]) for g in coarse)
        L.append("")
        L.append("| inner_fam → outer_fam | matrix cell | benign pairs |")
        L.append("|---|---|---|")
        for (inf, ouf, exp), n in sorted(by.items()):
            L.append(f"| {inf} → {ouf} | {exp} | {n} |")
    L.append("")

    # op×field
    L.append("## 3. op×field (L2 field-description logic)\n")
    L.append(f"Representative fields: " + ", ".join(f"**{k}**=`{v}`" for k, v in sorted(reps.items())))
    L.append("")
    flagged = [r for r in rows_of if r["verdict"] != "OK"]
    L.append(f"{len(flagged)}/{len(rows_of)} op×field combos flagged by L2.\n")
    L.append("| nature | op | verdict | reason |")
    L.append("|---|---|---|---|")
    for r in sorted(flagged, key=lambda r: (r["nature"], r["op"])):
        L.append(f"| {r['nature']} (`{r['field']}`) | `{r['op']}` | {r['verdict']} | {r['why']} |")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "state/funnel/logic_matrix_report.md"))
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    rows_oo, real_gaps, coarse, fps = op_by_op()
    reps, rows_of = op_by_field()
    chk = checklist_catch()
    report = render(rows_oo, real_gaps, coarse, fps, reps, rows_of, chk)

    outp = pathlib.Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(report)
    caught = sum(1 for r in chk if r["caught"])
    print(f"checklist caught {caught}/{len(chk)} | op×op REAL-defects={len(real_gaps)} "
          f"FPs={len(fps)} coarse-cell={len(coarse)} | "
          f"op×field flagged={sum(1 for r in rows_of if r['verdict']!='OK')}/{len(rows_of)}")
    print(f"-> {outp}")
    if a.json:
        json.dump({"checklist": chk, "real_gaps": real_gaps, "coarse": coarse,
                   "fps": fps, "op_field": rows_of}, open(a.json, "w"), indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
