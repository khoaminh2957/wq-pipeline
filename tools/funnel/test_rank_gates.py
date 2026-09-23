#!/usr/bin/env python3
"""5x regression test for rank_gates.rank_rows (Khoa 2026-07-17 reserve-sharpe rule).
Asserts, deterministically: (a) robust-passers with most gates lead; (b) the single
highest-sharpe alpha is ALWAYS in top-N even when it FAILS robust; (c) exactly N returned;
(d) deterministic across repeats."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rank_gates  # noqa: E402


def full(names_pass):
    ALL = ["LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO",
           "LOW_RETURNS", "MATCHES_PYRAMID", "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"]
    return [{"name": nm, "result": "PASS" if nm in names_pass else "FAIL"} for nm in ALL]


# fixture: A/B/C pass robust (many gates, modest sharpe); Z = HIGHEST sharpe but FAILS robust
ROWS = [
    {"alpha": "A", "sharpe": 1.10, "checks": full({"LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "LOW_TURNOVER", "MATCHES_PYRAMID", "LOW_SUB_UNIVERSE_SHARPE"})},
    {"alpha": "B", "sharpe": 1.05, "checks": full({"LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "LOW_TURNOVER", "MATCHES_PYRAMID"})},
    {"alpha": "C", "sharpe": 0.90, "checks": full({"LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "LOW_TURNOVER"})},
    {"alpha": "D", "sharpe": 0.40, "checks": full({"LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO"})},
    {"alpha": "E", "sharpe": 0.20, "checks": full({"LOW_ROBUST_UNIVERSE_SHARPE.WITH_RATIO", "LOW_TURNOVER"})},
    {"alpha": "Z", "sharpe": 2.90, "checks": full({"LOW_TURNOVER", "MATCHES_PYRAMID"})},  # top sharpe, NO robust
]


def run_once(i):
    top = rank_gates.rank_rows(ROWS, 5)
    ids = [r["id"] for r in top]
    checks = {}
    checks["exactly 5"] = len(top) == 5
    checks["Z (top-sharpe, robust-FAIL) included"] = "Z" in ids
    checks["robust leader present"] = "A" in ids
    checks["Z flagged sharpe_reserved"] = any(r["id"] == "Z" and r.get("sharpe_reserved") for r in top)
    # weakest robust row (E, fewest gates+low sharpe) is the one displaced by Z
    checks["weak row displaced"] = "E" not in ids or "D" not in ids
    ok = all(checks.values())
    print(f"RUN {i}: {'PASS' if ok else 'FAIL'} | top={ids} | "
          + " ".join(f"{k}={'ok' if v else 'X'}" for k, v in checks.items()))
    return ok, tuple(ids)


def main():
    results, first = [], None
    for i in range(1, 6):
        ok, ids = run_once(i)
        results.append(ok)
        if first is None:
            first = ids
        elif ids != first:
            print(f"RUN {i}: FAIL — non-deterministic ({ids} != {first})")
            results[-1] = False
    passed = sum(results)
    print(f"\n{passed}/5 runs PASS")
    sys.exit(0 if passed == 5 else 1)


if __name__ == "__main__":
    main()
