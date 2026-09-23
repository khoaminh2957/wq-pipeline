#!/usr/bin/env python3
"""Run every pre-dispatch gate at GENERATION time, so a pool never leaves a generator unlaunchable.

Four batches died at the door in two days, each on a different gate, each costing hours:

    validate_targets  region DEU rejected      a settings cache two regions out of date
    logic_check       79 rows                  GROUP classification fields used as signals
    precheck          140 rows                 banned fields (returns/volume) in a calibration probe
    precheck          312 rows                 duplicate formula+settings inside one batch

Each was fixed where it happened and nowhere else. The audit named the pattern — a fix applied in
one place but not its siblings — and then it happened a fourth time. The fix is not another patch:
it is running the SAME gates a launch runs, at the moment the pool is written, so the generator
cannot emit something the dispatcher will refuse.

Reports what it removed and why. A silently shrunken pool reads as "the idea did not work".

  python3 tools/gate_pool.py state/autoloop/pool_x.json            # report only
  python3 tools/gate_pool.py state/autoloop/pool_x.json --fix      # rewrite without the failures
"""
import argparse, collections, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def norm(f):
    return re.sub(r"\s+", "", f or "")


import opcheck                                                          # noqa: E402
SIGS = opcheck.load_signatures()


def gate(rows):
    """(kept, dropped[(old_id, reason)]) — pure, API-free, and the same rules the launcher applies."""
    ops = {o["name"] for o in json.load(open(ROOT / "fetched/rc/operators.json"))}
    bf = json.load(open(ROOT / "state/banned_fields.json"))
    banned = set(bf.get("banned_fields") or [])
    for v in (bf.get("by_alpha") or {}).values():
        banned |= set(v)

    # field types, so a VECTOR field outside a vec_* reduction is caught here rather than by
    # logic_check after the pool has already been queued
    ftype = {}
    for line in open(ROOT / "fetched/fields_all.jsonl"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("id"):
            ftype.setdefault(d["id"], (d.get("type") or "").upper())

    kept, dropped, seen = [], [], {}
    for r in rows:
        f = r.get("formula") or ""
        oid = r.get("old_id")
        s = r.get("settings") or {}

        # Operator existence, arity and named arguments, all read from OPERATORS.md rather than
        # from a name list — a name that exists can still be called with the wrong argument count,
        # and the platform answers that with a 400 rather than a hint.
        probs = opcheck.check(f, SIGS)
        if probs:
            dropped.append((oid, "; ".join(f"{k}: {v}" for k, v in probs[:2])))
            continue

        called = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", f))
        toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", f)) - called
        hit = sorted(toks & banned)
        if hit:
            dropped.append((oid, f"banned field {hit[:3]}"))
            continue

        # A GROUP field is ILLEGAL as a signal and LEGAL as the group argument of a group_* call.
        # Deciding on the field's TYPE alone flags `group_backfill(x, subindustry, 1)` — correct
        # usage — and would have deleted 36 valid rows. Position in the expression is the contract,
        # not the type. (I made the identical mistake on VECTOR ten minutes earlier: the rule is
        # always "where does it sit", never "what is it".)
        # Both of these ask "which call encloses this token?", and both used to answer it with a
        # fixed-width text window. Measured 2026-08-09 over 266 pool files / 155,012 rows: 685 GROUP
        # drops and 1,915 VECTOR drops, and logic_check.check_row() disagreed with ALL of them.
        #
        #   GROUP  looked back 300 characters for "group_...(" . An ensemble formula puts the group
        #          argument 700+ chars after its opener, so the opener fell outside the window and
        #          every correct `group_rank(<750 chars of legs>, industry)` was deleted.
        #   VECTOR matched the field id WITHOUT word boundaries, so a phantom hit inside a LONGER
        #          field id (mean_merger_acquisition_sentiment contains merger_acquisition_sentiment)
        #          was checked against the wrong 40-char context and failed.
        #
        # Widening the window is not the fix either — an unbounded lookback makes
        # `add(group_rank(x, industry), subindustry)` pass, turning a false positive into a false
        # negative. The question is structural, so resolve the ENCLOSING CALL by matching parens.
        def _enclosing(expr, pos):
            """(callee_name, arg_index) for the innermost call containing offset `pos`."""
            depth, i = 0, pos - 1
            while i >= 0:
                ch = expr[i]
                if ch == ")":
                    depth += 1
                elif ch == "(":
                    if depth == 0:
                        j = i - 1
                        while j >= 0 and (expr[j].isalnum() or expr[j] == "_"):
                            j -= 1
                        name = expr[j + 1:i]
                        argi = expr.count(",", i, pos) - _commas_in_nested(expr, i, pos)
                        return name, argi
                    depth -= 1
                i -= 1
            return None, 0

        def _commas_in_nested(expr, open_i, pos):
            """Commas belonging to nested calls, which must not count toward the arg index."""
            n, depth = 0, 0
            for k in range(open_i + 1, pos):
                c = expr[k]
                if c in "([":
                    depth += 1
                elif c in ")]":
                    depth -= 1
                elif c == "," and depth > 0:
                    n += 1
            return n

        bad_group = []
        for t in toks:
            if ftype.get(t) != "GROUP":
                continue
            for m in re.finditer(rf"\b{re.escape(t)}\b", f):
                callee, argi = _enclosing(f, m.start())
                # legal only as a non-first argument of a group_* call
                if not (callee and callee.startswith("group_") and argi >= 1):
                    bad_group.append(t)
                    break
        if bad_group:
            dropped.append((oid, f"GROUP field used as a signal {bad_group[:2]}"))
            continue

        VEC_OPS = {"vec_avg", "vec_sum", "vec_max", "vec_min", "vec_stddev", "vec_range",
                   "vec_count"}
        bad_vec = []
        for t in toks:
            if ftype.get(t) != "VECTOR":
                continue
            for m in re.finditer(rf"\b{re.escape(t)}\b", f):
                callee, _ = _enclosing(f, m.start())
                if callee not in VEC_OPS:
                    bad_vec.append(t)
                    break
        if bad_vec:
            dropped.append((oid, f"VECTOR field not reduced by vec_* {bad_vec[:2]}"))
            continue

        if opcheck.operator_count(f) > opcheck.CEILING:
            dropped.append((oid, f"{opcheck.operator_count(f)} operators exceeds the 64 ceiling"))
            continue

        key = (norm(f), s.get("region"), s.get("delay"), s.get("universe"),
               s.get("neutralization"), s.get("decay"), s.get("truncation"))
        if key in seen:
            dropped.append((oid, f"duplicate formula+settings of {seen[key]}"))
            continue
        seen[key] = oid
        kept.append(r)

    return kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pool")
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    rows = json.load(open(ROOT / args.pool if not args.pool.startswith("/") else args.pool))
    kept, dropped = gate(rows)

    print(f"{args.pool}: {len(rows)} -> {len(kept)}  ({len(dropped)} dropped)")
    if dropped:
        why = collections.Counter(re.sub(r"\[.*|\{.*", "", d[1]).strip() for d in dropped)
        for k, v in why.most_common():
            print(f"   {v:5}  {k}")

    # heterogeneous batches are rejected 400 by the platform, so say it here rather than at launch
    grp = collections.Counter((r["settings"].get("region"), r["settings"].get("delay"),
                               r["settings"].get("universe")) for r in kept)
    if len(grp) > 1:
        print(f"\n   WARNING: {len(grp)} distinct (region,delay,universe) groups — a multi-sim batch "
              f"must be homogeneous. Split before dispatch: {dict(grp)}")

    if args.fix and dropped:
        json.dump(kept, open(ROOT / args.pool if not args.pool.startswith("/") else args.pool, "w"),
                  indent=1)
        print(f"\n   rewrote {args.pool} with {len(kept)} rows")

    # the two real gates still run — this is a pre-filter, never a replacement for them
    for tool in ("tools/validate_targets.py", "tools/funnel/logic_check.py"):
        r = subprocess.run([sys.executable, str(ROOT / tool), args.pool],
                           capture_output=True, text=True, cwd=ROOT)
        tail = [l for l in r.stdout.strip().splitlines() if l.strip()][-1:] or ["(no output)"]
        print(f"   {pathlib.Path(tool).name:22} {tail[0][:96]}")
    return 0 if not dropped else 0


if __name__ == "__main__":
    raise SystemExit(main())
