#!/usr/bin/env python3
"""stage3_trigger.py — conditional STAGE-3 escalation trigger for the v7 funnel.

Khoa 2026-07-17: after Stage-2 produces the TOP-9, escalate to Stage-3 (add a
THIRD field, 9x180 sweep) ONLY IF the top-9 contains NO alpha that passes ALL
gates. "Passes ALL gates" == zero-fail over WHATEVER checks the platform
returned for that row (region x delay aware) — the exact C7 verdict already
implemented in gate_lib.gate_status. This tool does not reinvent gate logic; it
counts zero-fail rows and decides.

Pure: should_escalate(top_rows) -> {escalate, n_zero_fail, reason}.
CLI: stage3_trigger.py <top9.json>  (a JSON array of alpha rows, e.g. the
rank_gates *_top9.json output). Exit 0 => escalate (no passing alpha).
Exit 1 => a passing alpha exists, STOP (no escalation).
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gate_lib  # noqa: E402


def _row_id(row):
    return str(row.get("id") or row.get("alpha") or row.get("sid")
               or row.get("old_id") or "")


def should_escalate(top_rows):
    """Pure. Escalate iff NO row zero-fails ALL its returned gates.

    Uses gate_lib.gate_status (region x delay aware C7 verdict). A row counts as
    passing when gate_status(row)['zero_fail'] is True. Returns:
      escalate     : True when zero rows pass (n_zero_fail == 0)
      n_zero_fail  : how many rows passed ALL their returned gates
      reason       : human-readable one-liner (names the passers when any)
    """
    passers = [_row_id(r) for r in top_rows
               if gate_lib.gate_status(r)["zero_fail"]]
    n = len(passers)
    escalate = n == 0
    if escalate:
        reason = (f"0/{len(top_rows)} top rows zero-fail all returned gates "
                  f"-> escalate to STAGE-3")
    else:
        reason = (f"{n}/{len(top_rows)} top rows zero-fail all gates "
                  f"(passing: {', '.join(p for p in passers if p) or '<unnamed>'}) "
                  f"-> STOP, no escalation")
    return {"escalate": escalate, "n_zero_fail": n, "reason": reason}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("top9", help="TOP-9 JSON array (rank_gates *_top9.json)")
    args = ap.parse_args(argv)

    rows = json.loads(pathlib.Path(args.top9).read_text())
    if not isinstance(rows, list):
        ap.error("input must be a JSON array of alpha rows")

    res = should_escalate(rows)
    print(res["reason"])
    return 0 if res["escalate"] else 1


if __name__ == "__main__":
    sys.exit(main())
