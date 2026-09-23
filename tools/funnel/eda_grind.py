#!/usr/bin/env python3
"""eda_grind.py — professional EDA over the FULL grind corpus (Khoa 2026-07-19): mine every simulated config for
which OPERATORS + FIELDS have the highest/fastest breakthrough rate, to steer the next waves.

Stages (see state/eda/EDA_PROCESS.md for the reviewed process):
 S0 assembly&quality  S1 feature-extraction  S2 dedup/family-clustering  S3 univariate  S4 metric-structure
 S5 controlled-pair attribution  S6 breakthrough-rate (shrunk)  S7 interaction lift  S8 redundancy  S9 recency(2Y)
 S10 synthesis -> ranked levers (state/eda/eda_levers.json + EDA_REPORT.md)
Run: python3 tools/funnel/eda_grind.py
"""
from __future__ import annotations
import json, pathlib, re, sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "state" / "eda"
METRICS = ("sharpe", "fitness", "returns", "turnover")

OPS = set(("rank ts_backfill ts_zscore ts_rank ts_delta ts_delay ts_mean ts_std_dev ts_sum ts_corr ts_regression "
           "multiply add subtract divide signed_power sqrt log sigmoid tanh hump trade_when greater less if_else "
           "vec_avg vec_sum zscore scale winsorize quantile abs power normalize ts_scale ts_av_diff ts_quantile "
           "ts_decay_linear group_rank group_zscore group_neutralize ts_target_tvr_decay ts_product min max "
           "densify reverse inverse group_backfill bucket ts_min ts_max ts_skewness kth_element").split())


# ---------- S0+S1: assembly + feature extraction ----------
def load_corpus():
    cfgs = {}
    for p in ROOT.glob("state/**/*.json"):
        try:
            arr = json.load(open(p))
        except Exception:
            continue
        if isinstance(arr, list):
            for c in arr:
                if isinstance(c, dict) and "formula" in c and "settings" in c and c.get("old_id"):
                    s = c["settings"]
                    if (s.get("region"), s.get("delay"), s.get("universe")) == ("USA", 1, "TOP1000"):
                        cfgs[c["old_id"]] = c
    rows = []
    for l in open(ROOT / "state/resim_results.jsonl"):
        try:
            r = json.loads(l)
        except Exception:
            continue
        if isinstance(r, dict) and r.get("old_id") in cfgs and isinstance(r.get("sharpe"), (int, float)):
            c = cfgs[r["old_id"]]
            rows.append({**r, "formula": c["formula"], "settings": c["settings"]})
    # last occurrence wins (resim overwrites)
    dedup = {}
    for r in rows:
        dedup[r["old_id"]] = r
    return list(dedup.values())


def feats(row):
    f = row["formula"]; s = row["settings"]
    out = set()
    for m in re.finditer(r"([a-z_][a-z0-9_]*)\s*\(", f):
        if m.group(1) in OPS:
            out.add(f"op:{m.group(1)}")
    for t in set(re.findall(r"[a-z][a-z0-9_]{5,}", f)):
        if t not in OPS and not t.isdigit():
            out.add(f"fld:{t}")
    out.add(f"neut:{s.get('neutralization')}")
    dc = s.get("decay", 0)
    out.add(f"decay:{'0' if not dc else ('1-4' if dc <= 4 else '5+')}")
    # structural classes
    if "trade_when(" in f: out.add("struct:gate")
    if "if_else(" in f: out.add("struct:switch")
    if re.search(r"add\(multiply\(0?\.", f): out.add("struct:blend")
    if f.count("multiply(") >= 2: out.add("struct:product")
    return out


def family_of(row):
    """Cluster key so families aren't double-counted: sorted field-set."""
    return tuple(sorted(t for t in feats(row) if t.startswith("fld:")))


def check_2y(row):
    for c in row.get("checks", []) or []:
        if isinstance(c, dict) and c.get("name") == "LOW_2Y_SHARPE":
            return c.get("value")
    return None


# ---------- S6: breakthrough-rate with Bayesian shrinkage ----------
def breakthrough_table(rows):
    """P(top-decile-fitness | feature) and P(top-decile-corner | feature), Beta(2,18) prior (base rate 10%)."""
    fit = np.array([abs(r.get("fitness") or 0) for r in rows])
    def corner(r):
        return min(abs(r.get("sharpe") or 0) / 1.58, abs(r.get("fitness") or 0) / 1.0)
    cor = np.array([corner(r) for r in rows])
    fit_bar = np.quantile(fit, 0.9); cor_bar = np.quantile(cor, 0.9)
    stats = defaultdict(lambda: [0, 0, 0, 0])   # n, top_fit, top_cor, sum_fit
    for i, r in enumerate(rows):
        for ft in feats(r):
            st = stats[ft]
            st[0] += 1; st[1] += int(fit[i] >= fit_bar); st[2] += int(cor[i] >= cor_bar); st[3] += fit[i]
    tab = {}
    for ft, (n, tf, tc, sf) in stats.items():
        if n < 8:
            continue
        tab[ft] = {"n": n,
                   "p_top_fitness": round((tf + 2) / (n + 20), 3),
                   "p_top_corner": round((tc + 2) / (n + 20), 3),
                   "mean_fitness": round(sf / n, 3)}
    return tab, {"fit_bar": round(float(fit_bar), 3), "cor_bar": round(float(cor_bar), 3)}


# ---------- S5: controlled-pair attribution ----------
def pair_deltas(rows):
    """Same-family config pairs differing by exactly one feature -> per-feature metric deltas."""
    fams = defaultdict(list)
    for r in rows:
        fams[family_of(r)].append(r)
    deltas = defaultdict(lambda: defaultdict(list))
    for fam, rs in fams.items():
        if len(rs) < 2 or len(rs) > 200:
            continue
        fsets = [(r, feats(r)) for r in rs]
        for i in range(len(fsets)):
            for j in range(i + 1, len(fsets)):
                a, fa = fsets[i]; b, fb = fsets[j]
                d = fa ^ fb
                if len(d) == 1:
                    ft = next(iter(d)); hi, lo = (b, a) if ft in fb else (a, b)
                    for m in METRICS:
                        if isinstance(hi.get(m), (int, float)) and isinstance(lo.get(m), (int, float)):
                            deltas[ft][m].append(hi[m] - lo[m])
    out = {}
    for ft, ms in deltas.items():
        if len(ms.get("fitness", [])) >= 5:
            out[ft] = {m: {"n": len(v), "med": round(float(np.median(v)), 4)} for m, v in ms.items() if v}
    return out


# ---------- S7: op x field interaction lift ----------
def interaction_lift(rows, tab):
    fit = np.array([abs(r.get("fitness") or 0) for r in rows])
    bar = np.quantile(fit, 0.9)
    base = 0.10
    pairs = defaultdict(lambda: [0, 0])
    for i, r in enumerate(rows):
        fs = feats(r)
        ops = [f for f in fs if f.startswith("op:")]
        flds = [f for f in fs if f.startswith("fld:")]
        for o in ops:
            for fl in flds:
                p = pairs[(o, fl)]
                p[0] += 1; p[1] += int(fit[i] >= bar)
    out = []
    for (o, fl), (n, t) in pairs.items():
        if n < 12:
            continue
        p = (t + 2) / (n + 20)
        po = tab.get(o, {}).get("p_top_fitness", base); pf = tab.get(fl, {}).get("p_top_fitness", base)
        expect = max(po, pf)
        if p > expect * 1.3 and p > 0.15:
            out.append({"pair": f"{o} x {fl}", "n": n, "p_top": round(p, 3), "lift_vs_best_solo": round(p / expect, 2)})
    return sorted(out, key=lambda x: -x["p_top"])[:40]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_corpus()
    print(f"S0: corpus {len(rows)} USA-d1 configs with metrics")
    tab, bars = breakthrough_table(rows)
    deltas = pair_deltas(rows)
    inter = interaction_lift(rows, tab)
    # S9 recency: features whose configs have high 2Y/full ratio
    rec = defaultdict(list)
    for r in rows:
        y2 = check_2y(r); sh = r.get("sharpe")
        if isinstance(y2, (int, float)) and isinstance(sh, (int, float)) and abs(sh) > 0.3:
            for ft in feats(r):
                rec[ft].append(y2 / abs(sh))
    recency = {ft: round(float(np.median(v)), 2) for ft, v in rec.items() if len(v) >= 10}
    # S10 synthesis: ranked levers = p_top_corner (shrunk) x support, split by kind
    levers = sorted(({"feature": ft, **st, "recency_ratio": recency.get(ft)} for ft, st in tab.items()),
                    key=lambda x: -x["p_top_corner"])
    result = {"n_corpus": len(rows), "bars": bars,
              "top_levers": levers[:60], "pair_deltas": deltas, "interactions": inter}
    (OUT / "eda_levers.json").write_text(json.dumps(result, indent=1))
    # report
    L = ["# EDA GRIND REPORT (auto)", f"corpus: {len(rows)} configs · top-decile bars: {bars}", "",
         "## Top levers by P(top-decile corner | feature) — shrunk Beta(2,18)"]
    for lv in levers[:30]:
        L.append(f"- `{lv['feature']}` n={lv['n']} p_corner={lv['p_top_corner']} p_fit={lv['p_top_fitness']} "
                 f"mean_fit={lv['mean_fitness']} 2Y/full={lv.get('recency_ratio')}")
    L.append("\n## Controlled-pair deltas (median effect of adding the feature)")
    for ft, ms in sorted(deltas.items(), key=lambda kv: -abs(kv[1].get('fitness', {}).get('med', 0)))[:25]:
        L.append(f"- `{ft}`: " + " ".join(f"{m}:{v['med']:+.3f}(n{v['n']})" for m, v in ms.items()))
    L.append("\n## Interaction lifts (op x field beating best solo by >=1.3x)")
    for it in inter[:25]:
        L.append(f"- {it['pair']} n={it['n']} p_top={it['p_top']} lift={it['lift_vs_best_solo']}x")
    (OUT / "EDA_REPORT.md").write_text("\n".join(L))
    print(f"S10: report -> state/eda/EDA_REPORT.md · levers -> eda_levers.json")
    print(f"levers={len(levers)} pair-deltas={len(deltas)} interactions={len(inter)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
