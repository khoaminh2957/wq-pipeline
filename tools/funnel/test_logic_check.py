#!/usr/bin/env python3
"""5x regression test for logic_check.py — the pre-sim 3-layer logic gate.
Asserts deterministically: ILLEGAL (phantom op, group_mean 2-arg, trunc>1) blocks;
DANGEROUS (ts_product(returns), 1e-6 epsilon) blocks; USELESS (rank(zscore(x)),
market group) warns-not-blocks (unless --strict); a clean composite PASSes; the real
stage-1 winner formula PASSes. Deterministic across repeats."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import logic_check  # noqa: E402

S = {"region": "CHN", "universe": "TOP2000U", "delay": 1, "truncation": 0.08}

CASES = [
    # (id, formula, settings_override, expected_verdict)
    ("clean", "multiply(rank(mdl175_gainlossvarianceratio60), rank(mdl175_alpha60), filter=false)", {}, "PASS"),
    ("winner", "-rank(ts_backfill(mdl175_gainlossvarianceratio60, 22))", {}, "PASS"),
    ("phantom", "rank(ts_returns(close, 5))", {}, "ILLEGAL"),
    ("groupmean2", "rank(group_mean(mdl175_bp, sector))", {}, "ILLEGAL"),
    ("trunc", "rank(mdl175_bp)", {"truncation": 5.0}, "ILLEGAL"),
    ("tsprod", "rank(ts_product(returns, 10))", {}, "DANGEROUS"),
    ("eps", "divide(mdl175_bp, mdl175_ep + 1e-6)", {}, "DANGEROUS"),
    ("useless", "rank(zscore(mdl175_bp))", {}, "USELESS"),
    ("market", "group_rank(mdl175_bp, market)", {}, "USELESS"),
]


def run_once(i):
    targets = []
    for cid, f, ov, _ in CASES:
        st = dict(S); st.update(ov)
        targets.append({"old_id": cid, "formula": f, "settings": st, "label": "test"})
    res = logic_check.check(targets, strict=False)
    by = {r["id"]: r["verdict"] for r in res["rows"]}
    checks = {}
    for cid, _, _, exp in CASES:
        checks[cid] = by.get(cid) == exp
    checks["blocks ILLEGAL+DANGEROUS only"] = res["n_block"] == sum(
        1 for _, _, _, e in CASES if e in ("ILLEGAL", "DANGEROUS"))
    ok = all(checks.values())
    bad = [k for k, v in checks.items() if not v]
    print(f"RUN {i}: {'PASS' if ok else 'FAIL'}" + ("" if ok else f" | wrong: {bad} | got { {c:by.get(c) for c in bad if c in by} }"))
    return ok


def main():
    r = [run_once(i) for i in range(1, 6)]
    p = sum(r)
    print(f"\n{p}/5 runs PASS")
    sys.exit(0 if p == 5 else 1)


if __name__ == "__main__":
    main()
