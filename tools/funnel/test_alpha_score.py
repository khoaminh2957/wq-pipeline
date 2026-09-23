#!/usr/bin/env python3
"""5x contract tests for alpha_score v2 + the CI gate battery."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools" / "funnel"))
import alpha_score as A
from alpha_score_eval import evaluate


def check():
    e = []
    A._self_test()  # constraints + degeneracy + monotonicity
    rows = [json.loads(l) for l in open(A.RESULTS) if l.strip()]
    rows = [r for r in rows if isinstance(r, dict)]
    sc = A.AlphaScorer.fit(rows, seed=0)
    # Khoa constraints
    if not (min(sc.weights[p] for p in A.PRIORITY) > max(sc.weights[o] for o in A.OTHER)):
        e.append("priority not > others")
    if not (sc.weights["turnover"] >= sc.weights["fitness"] >= sc.weights["returns"] - 1e-9):
        e.append("turnover not hardest")
    # schema-mismatch load raises
    sc.save()
    d = json.load(open(A.SCORER)); d["schema_version"] = 99; json.dump(d, open("/tmp/_bad.json", "w"))
    try:
        A.AlphaScorer.load("/tmp/_bad.json"); e.append("bad schema did not raise")
    except ValueError:
        pass
    A.AlphaScorer.fit(rows, seed=0).save()  # restore good artifact
    # full CI battery must pass
    res = evaluate(rows, sc)
    if not res["pass"]:
        e.append(f"CI gates fail: {[k for k,v in res['gates'].items() if not v]}")
    return e


if __name__ == "__main__":
    for i in range(1, 6):
        er = check()
        print(f"RUN {i}: {'PASS' if not er else 'FAIL -> ' + '; '.join(er)}")
    er = check()
    print(f"\n{'5/5 runs PASS' if not er else 'FAILED: ' + '; '.join(er)}")
    sys.exit(0 if not er else 1)
