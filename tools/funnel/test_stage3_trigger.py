#!/usr/bin/env python3
"""5x regression test for stage3_trigger.should_escalate (Khoa 2026-07-17).

Deterministically asserts:
  (a) a top-9 with ONE zero-fail row  -> escalate=False (a passing alpha exists);
  (b) an all-failing top-9            -> escalate=True  (no passing alpha);
  (c) n_zero_fail is the exact passer count;
  (d) CLI exit codes: 1 when a passer exists, 0 when escalating;
  (e) deterministic across repeats.
No API — local fixtures only."""
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stage3_trigger  # noqa: E402


def full(names_pass, names_fail):
    return ([{"name": n, "result": "PASS"} for n in names_pass]
            + [{"name": n, "result": "FAIL"} for n in names_fail])


# 8 rows each carry a FAIL; 1 row (P) zero-fails all returned checks.
PASS_ROW = {"alpha": "P", "sharpe": 3.6, "region": "CHN", "delay": 0,
            # The base gate set must be ADJUDICATED for "zero-fail" to mean anything
            # (gate_lib.required_present). Listing three of five tested absence, not passing.
            "checks": full(["LOW_SHARPE", "LOW_TURNOVER", "LOW_FITNESS",
                            "HIGH_TURNOVER", "CONCENTRATED_WEIGHT"], [])}


def fail_row(i):
    return {"alpha": f"F{i}", "sharpe": 2.0, "region": "CHN", "delay": 0,
            "checks": full(["LOW_TURNOVER"], ["LOW_ROBUST_UNIVERSE_SHARPE"])}


TOP9_WITH_PASSER = [PASS_ROW] + [fail_row(i) for i in range(8)]
TOP9_ALL_FAIL = [fail_row(i) for i in range(9)]


def _cli_exit(rows):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(rows, f)
        path = f.name
    return subprocess.run([sys.executable, str(HERE / "stage3_trigger.py"), path]).returncode


def run_once(i):
    a = stage3_trigger.should_escalate(TOP9_WITH_PASSER)
    b = stage3_trigger.should_escalate(TOP9_ALL_FAIL)
    checks = {
        "passer -> no escalate": a["escalate"] is False,
        "passer n_zero_fail==1": a["n_zero_fail"] == 1,
        "all-fail -> escalate": b["escalate"] is True,
        "all-fail n_zero_fail==0": b["n_zero_fail"] == 0,
        "cli passer exit 1": _cli_exit(TOP9_WITH_PASSER) == 1,
        "cli all-fail exit 0": _cli_exit(TOP9_ALL_FAIL) == 0,
    }
    ok = all(checks.values())
    print(f"RUN {i}: {'PASS' if ok else 'FAIL'} | "
          + " ".join(f"{k}={'ok' if v else 'X'}" for k, v in checks.items()))
    return ok


def main():
    passed = sum(run_once(i) for i in range(1, 6))
    print(f"\n{passed}/5 runs PASS")
    sys.exit(0 if passed == 5 else 1)


if __name__ == "__main__":
    main()
