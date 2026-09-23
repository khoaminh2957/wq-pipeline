#!/usr/bin/env python3
"""Absence is not a pass. Regression tests for gate_lib.gate_status presence handling.

Measured 2026-08-08: 1,022 of 2,496 "zero-fail" rows (41%) carried no FAIL only because the gate
that would have failed them was never in the payload. The tell was the fitness distribution — a
set that genuinely cleared LOW_FITNESS (limit 1.0) cannot median 1.17.

    python3 tools/funnel/test_gate_lib_presence.py
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gate_lib as G

FULL = sorted(G.required_present("USA", 1))


def row(checks, **kw):
    # The required set is per-region (USA d1 adds LOW_SUB_UNIVERSE_SHARPE to the base five), so a
    # row with no region is graded against the conservative floor and cannot exercise the extra.
    return dict(checks=checks, sharpe=2.0, fitness=1.5, region="USA", delay=1, **kw)


def full(results=None, extra=()):
    """A payload adjudicating every REQUIRED_PRESENT gate; `results` overrides individual ones."""
    results = results or {}
    out = [{"name": n, "result": results.get(n, "PASS")} for n in FULL]
    out += list(extra)
    return out


CASES = []


def case(name, obj, want_zf, want_missing=None):
    CASES.append((name, obj, want_zf, want_missing))


# --- the happy path still works -------------------------------------------------------------
case("complete payload, all PASS", row(full()), True, [])
case("complete payload + extra PASS gates", row(full(extra=[
    {"name": "IS_LADDER_SHARPE", "result": "PASS"},
    {"name": "LOW_2Y_SHARPE", "result": "PASS"}])), True, [])
case("WARNING is not a FAIL", row(full(extra=[
    {"name": "HIGH_CORRELATION", "result": "WARNING"}])), True, [])

# --- the bug this file exists for ------------------------------------------------------------
for g in FULL:
    missing = [c for c in full() if c["name"] != g]
    case(f"{g} never reported -> NOT zero-fail", row(missing), False, [g])

case("empty check list is not a pass", row([]), False, None)
case("only two gates reported", row([{"name": "LOW_SHARPE", "result": "PASS"},
                                     {"name": "LOW_FITNESS", "result": "PASS"}]), False, None)

# --- real FAILs still block ------------------------------------------------------------------
case("one FAIL among a complete set", row(full({"LOW_FITNESS": "FAIL"})), False, [])
case("FAIL *and* a missing gate", row([c for c in full({"LOW_SHARPE": "FAIL"})
                                       if c["name"] != "HIGH_TURNOVER"]), False, ["HIGH_TURNOVER"])

# --- bare name-list form (platform returns names of PASSing checks) ---------------------------
case("name-list, complete", row(list(FULL)), True, [])
case("name-list, missing one", row([n for n in FULL if n != "LOW_TURNOVER"]),
     False, ["LOW_TURNOVER"])
case("name-list, empty", row([]), False, None)

# --- degenerate payloads that must never be promoted -----------------------------------------
case("unknown result strings are not adjudications",
     row([{"name": n, "result": "PENDING"} for n in FULL]), False, None)
case("checks present but nameless", row([{"result": "PASS"} for _ in FULL]), False, None)


def main():
    bad = 0
    for name, obj, want_zf, want_missing in CASES:
        g = G.gate_status(obj)
        got_zf = g["zero_fail"]
        ok = got_zf == want_zf
        if ok and want_missing is not None:
            ok = g.get("missing_core") == want_missing
        if not ok:
            bad += 1
            print(f"FAIL  {name}")
            print(f"      want zero_fail={want_zf} missing={want_missing}")
            print(f"      got  zero_fail={got_zf} missing={g.get('missing_core')}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
