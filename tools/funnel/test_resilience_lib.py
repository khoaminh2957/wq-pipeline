#!/usr/bin/env python3
"""5x regression test for resilience_lib.py — API-free, deterministic.

Fixture: state/benchmark/fixtures/resilience_metrics_slice.jsonl (a saved
resim_metrics.jsonl slice: 3x e401 recovered, 4x e400 recovered, 1 unrecovered
preflight, 89 batch_launch rows) with a golden computed by a DIRECT transcription
of the v6.2 S7 heredoc (git :418-511) — resilience 8.8, budget_cycle 735,
budget_day (fixed midnight) 68. Plus hand-computed synthetic cases for the three
caps (orphan_lost -> <=6.0, unrecovered rate-429 -> <=3.0, blocked -> <=6.0),
the E==0 -> 10.0 rule, the poison class, and the Retry-After string cast.
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import resilience_lib as R

SLICE = ROOT / "state/benchmark/fixtures/resilience_metrics_slice.jsonl"
GOLDEN = json.load(open(ROOT / "state/benchmark/fixtures/resilience_golden.json"))


def check_once():
    problems = []
    rows = R.load_jsonl(SLICE)

    # 1. golden: saved journal slice vs the v6.2 heredoc transcription
    exp = GOLDEN["expect"]
    got = R.cycle_resilience(rows, GOLDEN["t0"], GOLDEN["t1"], blocked=GOLDEN["blocked"])
    for k in ("failures", "orphan_lost", "resilience"):
        if got[k] != exp[k]:
            problems.append(f"golden.{k}: got {got[k]!r} want {exp[k]!r}")
    if R.budget_cycle_used(rows, GOLDEN["t0"], GOLDEN["t1"]) != exp["budget_cycle_used"]:
        problems.append("golden budget_cycle_used mismatch")
    if R.budget_day_used(rows, GOLDEN["midnight_ts"]) != exp["budget_day_used"]:
        problems.append("golden budget_day_used mismatch")

    # 2. E==0 => resilience 10.0
    clean = [{"ev": "req", "code": 200, "ts": 5.0}]
    if R.cycle_resilience(clean, 0, 10)["resilience"] != 10.0:
        problems.append("E==0 must yield 10.0")

    # 3. cap: unrecovered Retry-After-bearing 429 => <=3.0 (header is a STRING)
    r429 = [{"ev": "req", "code": 429, "retry_after": "2914", "ts": 5.0}]
    got429 = R.cycle_resilience(r429, 0, 10)
    if got429["resilience"] > 3.0 or got429["failures"]["e429_rate"] != {"enc": 1, "rec": 0}:
        problems.append(f"unrecovered rate-429 cap broken: {got429}")
    # slot-429 (no Retry-After) is NOT a breaker event
    slot = [{"ev": "refused", "code": 429, "msg": "CONCURRENT", "ts": 5.0, "retry_after": None}]
    if R.cycle_resilience(slot, 0, 10)["failures"]["e429_rate"]["enc"] != 0:
        problems.append("slot-429 wrongly counted as rate failure")

    # 4. cap: orphan_lost>0 => <=6.0 even when every class recovered
    orph = [{"ev": "orphan_lost", "n": 2, "ts": 4.0},
            {"ev": "req", "code": 200, "ts": 6.0}]
    go = R.cycle_resilience(orph, 0, 10)
    if go["resilience"] > 6.0 or go["orphan_lost"] != 2:
        problems.append(f"orphan_lost cap broken: {go}")

    # 5. cap: blocked cycle => <=6.0 (killed cycle may never journal 10.0)
    if R.cycle_resilience(clean, 0, 10, blocked="auth_fail")["resilience"] > 6.0:
        problems.append("blocked-cycle cap broken")

    # 6. poison class over the results hist (per old_id; recovered iff any alpha)
    hist = {"a1": [{"old_id": "a1"}, {"old_id": "a1", "alpha": "SID1"}],
            "a2": [{"old_id": "a2"}],
            "a3": [{"old_id": "a3", "alpha": "SID3"}]}
    gp = R.cycle_resilience([], 0, 10, hist=hist)
    if gp["failures"]["poison"] != {"enc": 2, "rec": 1}:
        problems.append(f"poison class broken: {gp['failures']['poison']}")

    # 7. e401 recovery requires restart AND zero orphans
    e401 = [{"ev": "req", "code": 401, "ts": 3.0}, {"ev": "restart", "ts": 5.0},
            {"ev": "orphan_lost", "n": 1, "ts": 6.0}]
    if R.cycle_resilience(e401, 0, 10)["failures"]["e401"] != {"enc": 1, "rec": 0}:
        problems.append("e401 counted recovered despite orphan loss")

    # 8. budget helpers: post-patch-10 ids=[...] dedupe vs pre-patch raw n
    b = [{"ev": "batch_launch", "ids": ["x", "y"], "n": 2, "ts": 100.0},
         {"ev": "batch_launch", "ids": ["y", "z"], "n": 2, "ts": 200.0},
         {"ev": "batch_launch", "n": 4, "ts": 300.0}]
    if R.budget_day_used(b, 50.0) != 7:  # {x,y,z} + 4
        problems.append(f"budget_day_used {R.budget_day_used(b, 50.0)} != 7")
    if R.budget_cycle_used(b, 150.0, 400.0) != 6:
        problems.append("budget_cycle_used window filter broken")

    return (not problems), "; ".join(problems)


def main():
    outputs, passed = [], 0
    rows = R.load_jsonl(SLICE)
    for i in range(1, 6):
        ok, detail = check_once()
        snap = json.dumps(R.cycle_resilience(rows, GOLDEN["t0"], GOLDEN["t1"]),
                          sort_keys=True)
        outputs.append(snap)
        if ok and snap == outputs[0]:
            passed += 1
            print(f"run {i}: PASS")
        else:
            print(f"run {i}: FAIL — {detail}"
                  + ("" if snap == outputs[0] else " [non-deterministic]"))
    print(f"{passed}/5 runs passed")
    sys.exit(0 if passed == 5 else 1)


if __name__ == "__main__":
    main()
