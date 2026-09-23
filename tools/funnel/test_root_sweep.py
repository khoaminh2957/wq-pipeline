#!/usr/bin/env python3
"""5x determinism + invariant test for root_sweep.py (Khoa: any .py tested >=5x)."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tools.funnel.root_sweep import generate, ROOTS


def check():
    errs = []
    sigs = []
    for _ in range(5):
        allrows = []
        for rid, spec in ROOTS.items():
            rows = generate(rid, spec["template"], spec["knobs"], "USA", "TOP1000", 1, 180)
            if len(rows) != 180:
                errs.append(f"{rid}: {len(rows)} rows != 180")
            # unique (formula+settings) keys
            keys = {(r["formula"], json.dumps(r["settings"], sort_keys=True)) for r in rows}
            if len(keys) != 180:
                errs.append(f"{rid}: {len(keys)} unique != 180 (dupes)")
            # every row is the fixed template (knobs substituted) — leg fields present
            for r in rows:
                if rid == "srl2" and "ts_zscore(mdl77_liquidityriskfactor_milliq" not in r["formula"]:
                    errs.append(f"{rid}: lost milliq leg: {r['formula'][:60]}"); break
                if "{" in r["formula"] or "}" in r["formula"]:
                    errs.append(f"{rid}: unfilled knob: {r['formula'][:60]}"); break
                s = r["settings"]
                if s["region"] != "USA" or s["universe"] != "TOP1000" or s["delay"] != 1:
                    errs.append(f"{rid}: cell drift {s}"); break
            allrows += rows
        sigs.append(json.dumps(allrows, sort_keys=True))
    if len(set(sigs)) != 1:
        errs.append(f"NON-DETERMINISTIC: {len(set(sigs))} distinct outputs across 5 runs")
    # srl2 knob coverage: all 3 windows + both filters appear
    srl2 = generate("srl2", ROOTS["srl2"]["template"], ROOTS["srl2"]["knobs"], "USA", "TOP1000", 1, 180)
    for w in ("63", "126", "252"):
        if not any(f", {w})" in r["formula"] for r in srl2):
            errs.append(f"srl2: window {w} missing from sweep")
    for f in ("filter=true", "filter=false"):
        if not any(f in r["formula"] for r in srl2):
            errs.append(f"srl2: {f} missing from sweep")
    return errs


if __name__ == "__main__":
    for i in range(1, 6):
        e = check()
        print(f"RUN {i}: {'PASS' if not e else 'FAIL -> ' + '; '.join(e)}")
    e = check()
    print(f"\n{'5/5 runs PASS' if not e else 'FAILED: ' + '; '.join(e)}")
    sys.exit(0 if not e else 1)
