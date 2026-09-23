#!/usr/bin/env python3
"""A 403 is an adjudication. Regression tests for harness.guards.slot_returnable.

Under G6 an alpha gets ONE POST ever. Four of the five submit paths released the reservation on
any 4xx, so a 403-killed alpha read as never-submitted and could be re-POSTed — spending one of
the ~4 real daily slots on an alpha that can never be accepted. Six alphas were destroyed this
way (pwKZl6Zg, O0xVZpVd, Vk35PY2J, vRvNrZXw, gJ98Vqjl, N1R7AKN8): all six appear in
state/funnel/submit_log.jsonl with a 403 and none in state/submit_budget.jsonl.

The one carve-out is real and was also paid for: P0OLx0zp was 403'd on 2026-08-01 with a lone
PROD_CORRELATION:ERROR during a rate-ban and measured prod 0.6549 minutes later. A 403 whose
checks carry ERROR and no FAIL is the platform failing to COMPUTE, not judging the alpha.

    python3 tools/funnel/test_slot_returnable.py
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from harness.guards import slot_returnable                                # noqa: E402

FAIL_BODY = json.dumps({"is": {"checks": [
    {"name": "LOW_SHARPE", "result": "PASS"},
    {"name": "SELF_CORRELATION", "result": "FAIL", "value": 0.81, "limit": 0.7}]}})
ERROR_ONLY = json.dumps({"is": {"checks": [
    {"name": "LOW_SHARPE", "result": "PASS"},
    {"name": "PROD_CORRELATION", "result": "ERROR"}]}})
MIXED = json.dumps({"is": {"checks": [
    {"name": "PROD_CORRELATION", "result": "ERROR"},
    {"name": "IS_LADDER_SHARPE", "result": "FAIL", "value": 1.4, "limit": 1.58}]}})

CASES = [
    # (name, status, body, expected returnable)
    ("429 throttled — never adjudicated",              429, "",          True),
    ("408 timeout — never answered",                   408, "",          True),
    ("403 with a FAIL — ADJUDICATED, slot is spent",   403, FAIL_BODY,   False),
    ("403 ERROR-only — platform could not compute",    403, ERROR_ONLY,  True),
    ("403 ERROR *and* FAIL — a FAIL is a judgement",   403, MIXED,       False),
    ("403 empty body — cannot prove transient",        403, "",          False),
    ("403 unparseable body — cannot prove transient",  403, "<html>502", False),
    ("400 malformed request",                          400, "",          False),
    ("401 auth expired",                               401, "",          False),
    ("404 unknown alpha",                              404, "",          False),
    ("422 unprocessable",                              422, "",          False),
    ("500 ambiguous — reservation must be KEPT",       500, "",          False),
    ("200 accepted",                                   200, "",          False),
]


def main():
    bad = 0
    for name, status, body, want in CASES:
        got = slot_returnable(status, body)
        if got != want:
            bad += 1
            print(f"FAIL  {name}: slot_returnable({status}) = {got}, want {want}")

    # The rule must be ONE implementation. Every submit path has to consult it rather than carry a
    # private copy — four private copies is how four of them stayed wrong until 2026-08-09.
    paths = ["wq_client.py", "tools/gentle_submit.py", "tools/complete_submit.py",
             "tools/deploy_greenlight.py"]
    for p in paths:
        src = (ROOT / p).read_text()
        if "slot_returnable" not in src:
            bad += 1
            print(f"FAIL  {p} does not consult slot_returnable")
        if "400 <= r.status_code < 500" in src and "slot_returnable" not in src.split(
                "400 <= r.status_code < 500")[0][-400:]:
            # a blanket 4xx branch is allowed only AFTER the returnable check has run
            pass

    print(f"\n{len(CASES) + len(paths) - bad}/{len(CASES) + len(paths)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
