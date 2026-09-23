#!/usr/bin/env python3
"""ab_process.py — turn the file-read A/B workflow result into a legal, tagged sim-target set.
old_id = ab_<c|t>_r<round>_<i>. Drops illegal formulas (unknown operator / illegal settings /
unbalanced parens) so the batch precheck won't block; reports per-group drop counts (drop rate is
itself a generation-quality signal). Usage: python3 tools/ab_process.py <workflow_output.json>"""
import json, re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools/funnel"))
import precheck_lib as pc

LEGAL_OPS = pc._load_ops()
FIELDS = set()
for line in open(ROOT / "state/all_fields_usa_top1000_d1.jsonl"):
    try: FIELDS.add(json.loads(line)["id"])
    except: pass
# non-field bare tokens that legitimately appear (grouping keys, param names, literals)
NONFIELD = {"subindustry","industry","sector","market","country","exchange","std","driver",
            "sigma","gaussian","uniform","cauchy","useStd","limit","scale","true","false","d1"}

def ops_in(formula):
    return set(re.findall(r"([a-z_][a-z0-9_]*)\s*\(", formula))

def fields_in(formula):
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", formula))
    return {t for t in toks if t not in LEGAL_OPS and t not in NONFIELD and not t.isdigit()}

def legal(formula, settings):
    if formula.count("(") != formula.count(")"): return "unbalanced parens"
    bad = ops_in(formula) - LEGAL_OPS
    if bad: return f"unknown ops {sorted(bad)}"
    badf = fields_in(formula) - FIELDS
    if badf: return f"unknown fields {sorted(badf)[:3]}"
    errs = pc.settings_legality(settings, formula, "x")
    if errs: return errs[0]
    return None

def settings(neut, decay):
    return {"instrumentType":"EQUITY","region":"USA","universe":"TOP1000","delay":1,
            "decay":int(decay) if str(decay).lstrip('-').isdigit() else 0,
            "neutralization":neut,"truncation":0.05,"pasteurization":"ON","unitHandling":"VERIFY",
            "nanHandling":"OFF","maxTrade":"OFF","maxPosition":"OFF","language":"FASTEXPR",
            "visualization":False,"startDate":"2019-01-01","endDate":"2023-12-31"}

obj = json.load(open(sys.argv[1]))
res = obj.get("result") if isinstance(obj, dict) else obj
if isinstance(res, str): res = json.loads(res)

targets, dropped = [], {"control":0, "treatment":0}
kept = {"control":0, "treatment":0}
for grp in res:
    g = grp["group"]; r = grp["round"]; tag = "c" if g == "control" else "t"
    for i, a in enumerate(grp.get("alphas", [])):
        f = (a.get("formula") or "").strip()
        st = settings(a.get("neut", "SUBINDUSTRY"), a.get("decay", 0))
        why = legal(f, st) if f else "empty"
        if why:
            dropped[g] += 1; continue
        oid = f"ab_{tag}_r{r}_{i:02d}"
        targets.append({"old_id":oid, "id":oid, "formula":f + "\n", "settings":st})
        kept[g] += 1
json.dump(targets, open(ROOT / "state/funnel/ab_targets.json", "w"), indent=1)
print(f"kept control={kept['control']} treatment={kept['treatment']}  (dropped illegal: control={dropped['control']} treatment={dropped['treatment']})")
print(f"-> state/funnel/ab_targets.json ({len(targets)} rows)")
