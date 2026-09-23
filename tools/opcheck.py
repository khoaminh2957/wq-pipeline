#!/usr/bin/env python3
"""Parse OPERATORS.md into a signature table and refuse any formula that violates it.

Khoa 2026-08-08: *"sử dụng file operators.md để đọc lại logic operators, các operators bị
hallucination bắt buộc phải dọn trc khi được apply vào fomular."*

I wrote operator names from memory three separate times in one day and was wrong every time:

    prompt to 10 research agents   23 of the 85 names I listed do not exist
                                   (ts_returns, ts_partial_corr, ts_theilsen, purify, ts_moment,
                                    ts_co_skewness, ts_co_kurtosis, ts_triple_corr, truncate,
                                    clamp, filter, keep, left_tail, right_tail, tail, fraction,
                                    s_log_1p, arc_tan, ts_min, ts_max, ts_argmin, ts_argmax,
                                    ts_decay_exp_window)
    plus four vec_* that do not exist (vec_skewness, vec_kurtosis, vec_percentage, vec_choose)
    gen_shape.py                   ts_kurtosis / ts_min / ts_max — 191 of 416 rows deleted

A research agent caught the first, a gate caught the third. Neither should have had to: the
authoritative reference has been in the repo the whole time. OPERATORS.md and
fetched/rc/operators.json agree exactly — 85 operators, same set, no drift — so OPERATORS.md is
the semantic reference and the json is its name list.

This checks THREE things, in the order they bite:

  1. EXISTENCE  — the operator is one of the 85.
  2. ARITY      — the call has an argument count the documented signature permits, counting
                  optional and named parameters. `ts_delta(x)` is not a typo the platform
                  forgives; it is a 400.
  3. NAMED ARGS — a `name=value` argument is one the signature actually declares. `filter=true`
                  is legal on add/multiply; `useStd=true` is legal on normalize; inventing
                  `window=` on ts_mean is not.

Suggestions are Levenshtein-nearest real names, so a typo reports its fix rather than only its
failure.

  python3 tools/opcheck.py --formula "rank(ts_kurtosis(close, 60))"
  python3 tools/opcheck.py --pool state/autoloop/pool_x.json
"""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD = ROOT / "OPERATORS.md"


def load_signatures():
    """name -> {'min': int, 'max': int|None, 'named': set[str], 'doc': str}, read from OPERATORS.md.

    A signature line looks like `ts_arg_min(x, d)` or `add(x, y, filter=false)` or
    `group_neutralize(x, group)`. Optional parameters appear WITH a default, so an argument
    carrying '=' is optional and also names a legal keyword."""
    md = MD.read_text()
    out = {}
    for m in re.finditer(r"^### `([a-z_0-9]+)`(.*?)(?=^### |\Z)", md, re.M | re.S):
        name, body = m.group(1), m.group(2)
        # The signature sits in a FENCED block, not inline backticks:
        #     ```
        #     ts_arg_min(x, d)
        #     ```
        # Matching only inline backticks parsed 0 signatures and every arity read 0-None, which is
        # a checker that silently checks nothing.
        # A fenced block can hold SEVERAL signatures separated by "or":
        #     ```
        #     bucket(rank(x), range="0, 1, 0.1", skipBoth=False, NaNGroup=False)
        #     or
        #     bucket(rank(x), buckets="2,5,6,7,10", skipBoth=False, NaNGroup=False)
        #     ```
        # A single-line regex matches none of it, reads zero signatures, and then reports that
        # bucket "accepts none" — a checker confidently wrong rather than silent.
        fenced = []
        for blk in re.findall(r"```[a-z]*\s*\n(.*?)```", body, re.S):
            fenced += [ln.strip() for ln in blk.splitlines() if ln.strip()]
        inline = re.findall(r"`([a-z_0-9]+\([^`\n]*\))`", body)
        sigs = [x.strip() for x in fenced + inline if x.strip().startswith(name + "(")]
        if not sigs:
            out[name] = {"min": 0, "max": None, "named": set(), "doc": "(no signature line)"}
            continue
        lo, hi, named = None, 0, set()
        for s in sigs:
            inner = s[len(name) + 1:-1].strip()
            args = [a.strip() for a in _split_top(inner)] if inner else []
            req = sum(1 for a in args if "=" not in a)
            named |= {a.split("=")[0].strip() for a in args if "=" in a}
            lo = req if lo is None else min(lo, req)
            hi = max(hi, len(args))
        first = re.search(r"\n([A-Z][^\n]{20,})", body)
        out[name] = {"min": lo or 0, "max": hi, "named": named,
                     "doc": (first.group(1)[:110] if first else "")}
    return out


def _split_top(s):
    """Split on top-level commas, respecting brackets AND quotes.

    `range="0, 1, 0.1"` carries commas INSIDE a quoted value; splitting on them turns one named
    argument into four positional ones and every bucket() call reads as an arity error. The docs
    use curly quotes, so both forms are honoured."""
    parts, depth, cur, q = [], 0, "", None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in "\"'\u201c\u201d":
            q = {"\u201c": "\u201d"}.get(ch, ch)
            cur += ch
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


CEILING = 62          # margin under the platform's documented 64


def operator_count(formula):
    """A LOWER BOUND on the platform's operator count: function calls plus infix operators.

    The previous check was `formula.count("(") > 62`, which counts open parens. That is neither an
    operator count nor a bound on one: `add(x, y) + multiply(a, b) - 1` has 2 parens and at least 4
    operators, and grouping parens inflate it in the other direction.

    MEASURED 2026-08-09 over the 5,008 journal rows that carry their formula: no formula approaches
    the ceiling by either measure (paren max 54, call+infix max 56), and the 84 ERROR rows top out
    LOWER than the successful ones (45 / 48). So the ceiling has never been observed to bite here
    and this change is precautionary, not a repair of a known loss. What causes those 84 errors is
    MECHANISM: UNKNOWN and is not this.

    The platform's exact counting rule is undocumented here, so this deliberately returns the
    larger of the two measures: over-counting refuses a formula that might have fit, under-counting
    spends a simulation on a 400.
    """
    calls = len(re.findall(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", formula))
    infix = len(re.findall(r"(?<![<>=!])[+\-*/](?![/*])|<=|>=|==|!=|&&|\|\||[<>?:]", formula))
    return max(formula.count("("), calls + infix)


def _lev(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def nearest(name, known, k=3):
    return sorted(known, key=lambda n: (_lev(name, n), n))[:k]


def check(formula, sigs):
    """[(severity, message)] — empty means the formula violates nothing this can see."""
    problems = []
    known = set(sigs)

    # every call site, with its argument list
    for m in re.finditer(r"\b([a-z_][a-z_0-9]*)\s*\(", formula):
        name = m.group(1)
        if name in ("true", "false"):
            continue
        # capture the matching close paren
        i, depth = m.end() - 1, 0
        while i < len(formula):
            if formula[i] == "(":
                depth += 1
            elif formula[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        inner = formula[m.end():i]

        if name not in known:
            problems.append(("HALLUCINATED",
                             f"`{name}` is not one of the 85 operators — nearest real: "
                             f"{', '.join(nearest(name, known))}"))
            continue

        s = sigs[name]
        args = [a.strip() for a in _split_top(inner)] if inner.strip() else []
        pos = [a for a in args if not re.match(r"^[a-zA-Z_][a-zA-Z_0-9]*\s*=", a)]
        kw = {a.split("=")[0].strip() for a in args if re.match(r"^[a-zA-Z_][a-zA-Z_0-9]*\s*=", a)}

        # variadic ops (add/multiply/subtract document "two or more inputs")
        variadic = name in {"add", "multiply", "subtract", "max", "min"}
        if not variadic:
            if len(pos) < s["min"]:
                problems.append(("ARITY", f"`{name}` needs at least {s['min']} positional "
                                          f"arguments, got {len(pos)}"))
            if s["max"] is not None and len(args) > s["max"]:
                problems.append(("ARITY", f"`{name}` takes at most {s['max']} arguments, got "
                                          f"{len(args)}"))
        bad_kw = sorted(kw - s["named"])
        if bad_kw:
            problems.append(("NAMED_ARG", f"`{name}` does not declare {bad_kw}; it accepts "
                                          f"{sorted(s['named']) or 'none'}"))

    if formula.count("(") != formula.count(")"):
        problems.append(("PARENS", f"{formula.count('(')} open vs {formula.count(')')} close"))
    n_ops = operator_count(formula)
    if n_ops > CEILING:
        problems.append(("CEILING", f"{n_ops} operators (calls+infix) — the platform ceiling is 64"))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--formula")
    ap.add_argument("--pool")
    ap.add_argument("--list", action="store_true", help="print the whole signature table")
    args = ap.parse_args()

    sigs = load_signatures()

    if args.list:
        for n in sorted(sigs):
            s = sigs[n]
            rng = f"{s['min']}" if s["max"] == s["min"] else f"{s['min']}-{s['max']}"
            print(f"{n:22} args={rng:8} named={sorted(s['named']) or '-'}")
        print(f"\n{len(sigs)} operators, parsed from OPERATORS.md")
        return 0

    if args.formula:
        p = check(args.formula, sigs)
        if not p:
            print("OK")
            return 0
        for sev, msg in p:
            print(f"{sev:14} {msg}")
        return 1

    if args.pool:
        rows = json.load(open(ROOT / args.pool if not args.pool.startswith("/") else args.pool))
        import collections
        bad = collections.Counter()
        examples = {}
        for r in rows:
            for sev, msg in check(r.get("formula") or "", sigs):
                bad[sev] += 1
                examples.setdefault(msg, r.get("old_id"))
        print(f"{args.pool}: {len(rows)} rows")
        if not bad:
            print("   no operator violations")
            return 0
        for sev, n in bad.most_common():
            print(f"   {sev:14} {n}")
        print()
        for msg, oid in list(examples.items())[:10]:
            print(f"   {oid}: {msg}")
        return 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
