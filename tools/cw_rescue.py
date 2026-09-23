"""CONCENTRATED_WEIGHT: the bar is 0.1, and the council's best claim caps at 0.5.

READ THIS BEFORE USING ANY S1 RESULT. I wrote this file to harvest what looked like free gems --
115 alphas in `fetched/alphas_all.jsonl` that fail CONCENTRATED_WEIGHT and pass every other scored
gate, 45 SPECTACULAR and 44 EXCELLENT, fitness >= 1.0 on 115 of 115, median fitness 2.42. The plan
was to re-simulate the 102 running `neutralization=NONE` under a group neutralization, because S1 --
the one council claim that made a risky prediction and survived it -- proves a group neutralization
caps the metric at 0.5.

THE PLAN WAS WRONG, AND THE ERROR WAS MINE. **The gate's limit is 0.1.** S1's cap is 0.5. Capping a
metric at five times its own bar clears nothing.

Re-derived two ways before this file was rewritten:
  * `fetched/alphas_all.jsonl`, 9,984 rows: every populated CONCENTRATED_WEIGHT limit is 0.1
    (441 of 441).
  * `state/resim_results.jsonl`, 78,319 lines / 69,262 scored rows: same, 1,938 of 1,938, and the
    LOWEST value ever recorded as FAIL is exactly 0.100000.

The 13 rows this tool first reported as "S1 counterexamples" were nothing of the kind. Their values
are 0.5, 0.5, 0.5, 0.5, 0.471875, 0.190426, 0.154103, 0.121096 -- every one at or under 0.5, exactly
as S1 predicts, and every one over 0.1, so every one FAILs. S1 was never contradicted; my reading of
the gate was.

AND THE SETTING DOES NOT HELP AT THE REAL BAR. Fail rates by neutralization KIND over the resim
corpus: GROUP 22/5,809 = 0.38%, RISK-FACTOR 15/5,922 = 0.25%. The risk-factor kind -- the one S1's
own negative control says does NOT cap -- fails slightly LESS. Whatever clears this gate, S1 is not
it. MECHANISM: UNKNOWN.

Book size is not the answer either: the 441 failures run from book 0 to a p90 of 1,117 names, so
this is about the weight DISTRIBUTION and not the name count. `limit` is populated only on failing
rows, so a pass/fail comparison on that field is not available and no split here has a control.

WHAT SURVIVES. S1 remains true and remains the best-evidenced claim in the project -- 0 violations
in 1,266 group-neutralized rows across USA/EUR/ASI, maxima piled at 0.500007, and a negative control
that holds (risk-factor neutralizations do NOT cap: 8 of 390 above 0.5001, max 1.0). It is simply
true about a threshold nobody is graded against. That is the same class as the exponent lever:
significant, replicated, and useless.

This tool now reports the population and refuses to propose a fix it cannot justify. It never POSTs.
"""

import argparse
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "fetched/alphas_all.jsonl"

TARGET = "CONCENTRATED_WEIGHT"

#: Group neutralizations partition the book, so S1's two-name floor applies and caps the metric at
#: 0.5. Risk-factor neutralizations do not partition anything and do not cap -- that asymmetry is
#: S1's negative control and it holds. NEITHER kind is known to clear the 0.1 bar.
GROUP_NEUT = ("SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET")


def rows(path=SRC):
    for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
        if line.startswith("{"):
            try:
                yield json.loads(line)
            except ValueError:
                continue


def gate_limit(path=SRC):
    """Every distinct limit the platform has ever reported for this gate, with counts.

    Populated only on failing rows in both corpora, so this establishes the bar and CANNOT be used
    to compare passes against failures.
    """
    seen = collections.Counter()
    for r in rows(path):
        ch = r.get("checks")
        if not isinstance(ch, list):
            continue
        for c in ch:
            if isinstance(c, dict) and c.get("name") == TARGET:
                seen[c.get("limit")] += 1
    return seen


def blocked_only_by_cw(path=SRC):
    """Alphas whose ONLY failing scored check is CONCENTRATED_WEIGHT.

    A row whose `checks` is missing or in the bare-name shape is skipped, never counted as a pass --
    614 rows at the head of the resim journal list the checks that PASSED, inverted polarity, and
    reading them naively makes every conclusion backwards.
    """
    out = []
    for r in rows(path):
        ch = r.get("checks")
        if not isinstance(ch, list):
            continue
        recs = {c["name"]: c for c in ch if isinstance(c, dict) and c.get("name")}
        if TARGET not in recs:
            continue
        if sorted(n for n, c in recs.items() if c.get("result") == "FAIL") == [TARGET]:
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", help="write the blocked population as JSONL, for whoever finds a lever")
    a = ap.parse_args()

    src = pathlib.Path(a.src)
    n_rows = sum(1 for _ in src.read_text(errors="ignore").splitlines())
    limits = gate_limit(src)
    real = {k: v for k, v in limits.items() if k is not None}
    print("PINNED %d rows of %s" % (n_rows, src.name))
    print("%s limits reported by the platform: %s" % (TARGET, real or "none populated"))
    if set(real) == {0.1}:
        print("  -> THE BAR IS 0.1. S1's group-neutralization cap is 0.5, i.e. 5x the bar. "
              "Satisfying S1 does not clear this gate.")

    cands = blocked_only_by_cw(src)
    print("\n%d alphas fail %s and pass every other scored gate" % (len(cands), TARGET))
    print("grades: %s" % dict(collections.Counter(r.get("grade") for r in cands).most_common()))
    fit = [r["fitness"] for r in cands if isinstance(r.get("fitness"), (int, float))]
    if fit:
        fit.sort()
        print("fitness >= 1.0 on %d of %d, median %.2f" % (sum(1 for f in fit if f >= 1.0),
                                                           len(fit), fit[len(fit) // 2]))
    by = collections.Counter((r.get("settings") or {}).get("neutralization") for r in cands)
    print("their current neutralization: %s" % dict(by.most_common()))
    grouped = sum(v for k, v in by.items() if k in GROUP_NEUT)
    print("  -> %d of them ALREADY run a group neutralization and still fail, which is the direct "
          "demonstration that the 0.5 cap is not the 0.1 bar." % grouped)

    vals = []
    for r in cands:
        for c in (r.get("checks") or []):
            if isinstance(c, dict) and c.get("name") == TARGET \
                    and isinstance(c.get("value"), (int, float)):
                vals.append(((r.get("settings") or {}).get("neutralization"), c["value"]))
    if vals:
        g = sorted(v for k, v in vals if k in GROUP_NEUT)
        n = sorted(v for k, v in vals if k not in GROUP_NEUT)
        if g:
            print("  values under a group neutralization: max %.6f (S1 predicts <= 0.5)" % max(g))
        if n:
            print("  values without one:                  max %.6f" % max(n))

    print("\nNO FIX IS PROPOSED. At the real bar the two neutralization kinds are indistinguishable "
          "in the resim corpus (GROUP 22/5,809 = 0.38%, RISK 15/5,922 = 0.25%), and book size does "
          "not separate the failures (book 0 to p90 1,117). MECHANISM: UNKNOWN.")

    if a.out:
        p = pathlib.Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as fh:
            for r in cands:
                fh.write(json.dumps({
                    "id": r.get("id"), "formula": r.get("formula"),
                    "settings": r.get("settings"),
                    "metrics": {k: r.get(k) for k in
                                ("sharpe", "fitness", "turnover", "margin", "grade",
                                 "longCount", "shortCount")},
                }) + "\n")
        print("wrote the %d blocked alphas -> %s (a population to study, not a queue to submit)"
              % (len(cands), p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
