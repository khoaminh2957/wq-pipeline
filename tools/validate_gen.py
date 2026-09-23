#!/usr/bin/env python3
"""Validate + dedup session-generated formulas before simulating.
Reads state/gen_candidates.json (list of {formula,thesis,theme,...}) ->
state/gen_shortlist.json (sim-ready, deduped vs portfolio + each other).
Checks: operators in allowlist, none in blocklist, no degenerate self-arg,
structural near-dup vs existing portfolio + within batch."""
import csv, json, re, sys
from pathlib import Path
sys.path.insert(0, "/Users/kanenguyen/wq_pipeline")
from operators import ALLOWLIST, BLOCKLIST, operators_in, blocklist_violations, unknown_operators
from fingerprint import structural_signature, near_duplicate

ST = Path("/Users/kanenguyen/wq_pipeline/state")
CSV = "/Users/kanenguyen/Downloads/IQC Submit Ready — acc1 - d0_alphas (1).csv"
PORT = ["9qRq6579","pw7OYAOq","MPxmvnl6","XgKKqm9z","LLk2QRq9","wpelNN62","3qAxLZr0"]
GROUPS = {"subindustry","industry","sector","market","exchange","country"}
EXTRA_OK = {"add","subtract","multiply","divide","power","max","min"}  # arithmetic always allowed

def main():
    cands = json.load(open(ST/"gen_candidates.json"))
    Cmap = {r["alpha_id"]: r for r in csv.DictReader(open(CSV))}
    port_sigs = [structural_signature(Cmap[p]["formula"]) for p in PORT if p in Cmap]
    kept, rejected = [], []
    batch_sigs = []
    for i, c in enumerate(cands):
        f = (c.get("formula") or "").strip()
        if not f:
            rejected.append((c.get("theme"), "empty")); continue
        bad = blocklist_violations(f)
        unknown = [u for u in unknown_operators(f) if u not in EXTRA_OK]
        if bad:
            rejected.append((c.get("theme"), f"blocklist:{bad}")); continue
        if unknown:
            rejected.append((c.get("theme"), f"unknown_ops:{unknown}")); continue
        # degenerate self-arg: ts_regression(X,X) / divide(X,X) / subtract(X,X) / ts_corr(X,X)
        if re.search(r"(ts_regression|ts_corr|divide|subtract)\(\s*([a-z0-9_]+)\s*,\s*\2\s*[,)]", f):
            rejected.append((c.get("theme"), "self-arg degenerate")); continue
        sig = structural_signature(f)
        if any(near_duplicate(sig, ps) for ps in port_sigs):
            rejected.append((c.get("theme"), "dup vs portfolio")); continue
        if any(near_duplicate(sig, bs) for bs in batch_sigs):
            rejected.append((c.get("theme"), "dup within batch")); continue
        batch_sigs.append(sig)
        kept.append({"id": f"gen_{c.get('theme','x')}_{i}", "formula": f, "thesis": c.get("thesis",""),
                     "theme": c.get("theme",""), "region":"USA","universe":"TOP3000",
                     "neut":"SUBINDUSTRY","decay":6,"trunc":0.08})
    json.dump(kept, open(ST/"gen_shortlist.json","w"))
    print(f"candidates={len(cands)} kept={len(kept)} rejected={len(rejected)}")
    from collections import Counter
    print("reject reasons:", dict(Counter(r[1].split(':')[0] for r in rejected)))
    for k in kept: print(f"  KEEP [{k['theme']}] {k['formula'][:90]}")

if __name__ == "__main__":
    main()
