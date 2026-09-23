#!/usr/bin/env python3
"""5x test for flex_sweep.py — ANCHORED flexibility (Khoa: tested >=5x; deterministic; anchor variant0=base;
key7-unique; formula-diverse via valves/legs; same-dataset 3rd leg)."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.funnel.flex_sweep import generate, ROOTS, same_dataset_pool


def _k7(r):
    s = r["settings"]
    return ("".join(r["formula"].split()), s["region"], s["universe"], s["delay"],
            s["neutralization"], s["decay"], s["truncation"])


def check():
    e = []
    spec = ROOTS["srl2"]
    pool = same_dataset_pool(spec["dataset"], exclude=spec["exclude"])
    base_core = "multiply(" + ", ".join(spec["core_legs"]) + ", filter=true)"
    sigs = []
    for _ in range(5):
        rows = generate(spec["core_legs"], spec["base_settings"], "USA", "TOP1000", 1, pool, 90, label="t")
        if len(rows) != 90:
            e.append(f"{len(rows)} != 90")
        if len({_k7(r) for r in rows}) != 90:
            e.append("not key7-unique")
        # variant 000 = base verbatim (anchor)
        if rows[0]["formula"] != base_core:
            e.append(f"variant0 not the base core: {rows[0]['formula'][:60]}")
        # the ORIGINAL reversal leg is PRESERVED (never re-transformed to ts_zscore)
        for r in rows:
            if "rank(-mdl177_pricemomemtummodel_indrelrtn5d_)" not in r["formula"]:
                e.append(f"core reversal leg lost/altered: {r['formula'][:70]}"); break
            if "{" in r["formula"]:
                e.append("unfilled"); break
            if "hump(" in r["formula"] and "hump=" not in r["formula"]:
                e.append("hump positional"); break
        # formula diversity: valves + added legs -> several distinct formulas
        nform = len({"".join(r["formula"].split()) for r in rows})
        if nform < 15:
            e.append(f"only {nform} distinct formulas — not flexible")
        # at least some variants add a same-dataset 3rd leg (3+ rank())
        if not any(r["formula"].count("rank(") >= 3 for r in rows):
            e.append("no variant adds a same-dataset 3rd leg")
        # at least some variants have a turnover valve (fixes fitness/after-cost)
        if not any(r["formula"].startswith(("ts_decay_linear", "hump")) for r in rows):
            e.append("no turnover-valve variant")
        sigs.append(json.dumps(rows, sort_keys=True))
    if len(set(sigs)) != 1:
        e.append(f"NON-DETERMINISTIC: {len(set(sigs))}")
    if not pool:
        e.append("same-dataset pool empty")
    return e


if __name__ == "__main__":
    for i in range(1, 6):
        er = check()
        print(f"RUN {i}: {'PASS' if not er else 'FAIL -> ' + '; '.join(er)}")
    er = check()
    print(f"\n{'5/5 runs PASS' if not er else 'FAILED: ' + '; '.join(er)}")
    sys.exit(0 if not er else 1)
