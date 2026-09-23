#!/usr/bin/env python3
"""Cross-correlation safety check before submitting — which candidates kill which.

Two different failures are being prevented, and they need different comparisons:

  1. THE PLATFORM REJECTS the alpha, because it correlates >=0.7 with something already in the
     book. Compared against every ACTIVE alpha.
  2. THE SUBMIT IS WASTED, because a candidate submitted earlier the same day raises this one's
     correlation to ~their pairwise value. Compared against the other candidates.

Failure 2 is invisible until it has already happened: correlations against an alpha are only
published once that alpha is IN the book, so the sibling you just destroyed reads clean right up
until you spend the slot on its twin. On 2026-08-01 the queue held 22 gate-passing gems that were
really only 9 independent families -- Institutions alone had 10 gems in 3 families -- so a naive
"submit the four highest sharpe" would have spent a whole day's quota inside one family and
unlocked nothing.

Correlations come from tools/self_corr_predict.py (PnL curves, no submit needed, +-0.022).

Usage:
  python3 tools/submit_safety.py <id> [<id> ...]      candidates to check
  python3 tools/submit_safety.py --plan <id> [...]    also print a maximal conflict-free set
"""
import itertools, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import self_corr_predict as SP                                      # noqa: E402

GATE = 0.7
CURVES = ROOT / "state/pnl_curves"


def active_ids(s):
    """Ids currently IN the book. Only these can cause a platform rejection."""
    out, off = [], 0
    while off < 2000:
        j = s.get("https://api.worldquantbrain.com/users/self/alphas",
                  params={"limit": 50, "offset": off, "status": "ACTIVE"}, timeout=90).json()
        r = j.get("results") or []
        if not r:
            break
        out += [a["id"] for a in r]
        off += 50
        if off >= j.get("count", 0):
            break
    return out


def main(argv):
    plan = "--plan" in argv
    cands = [a for a in argv if a != "--plan"]
    if not cands:
        raise SystemExit("usage: submit_safety.py [--plan] <alphaId> [<alphaId> ...]")
    s = SP._session()
    book = [a for a in active_ids(s) if a not in cands]
    cur = {}
    for a in cands:
        cur[a] = SP.pnl(s, a)
        if not cur[a]:
            print(f"  ! {a}: no PnL curve — cannot be checked, treat as UNSAFE")
    cands = [a for a in cands if cur.get(a)]
    # Book curves are read from cache only. Fetching hundreds of them competes with the sim stream
    # for one rate budget, and a partial comparison that SAYS it is partial beats a complete one
    # that starves the miner.
    have = {f.stem for f in CURVES.glob("*.json")}
    book_ok = [b for b in book if b in have]
    for b in book_ok:
        cur[b] = SP.pnl(None, b)
    missing = len(book) - len(book_ok)

    print(f"\n1) VS THE BOOK — a hit here means the platform rejects the submit")
    print(f"   compared against {len(book_ok)}/{len(book)} ACTIVE alphas"
          f"{f' ({missing} have no cached curve — BLIND SPOT)' if missing else ''}\n")
    print(f"   {'candidate':11} {'max corr':>9}  nearest")
    for a in cands:
        best = (None, -1.0)
        for b in book_ok:
            if not cur.get(b):
                continue
            v, _ = SP.predict(cur[a], cur[b])
            if v is not None and v > best[1]:
                best = (b, v)
        mark = "  <-- WOULD BE REJECTED" if best[1] >= GATE else ""
        print(f"   {a:11} {best[1]:9.4f}  {best[0]}{mark}")

    print(f"\n2) VS EACH OTHER — a hit here means submitting one WASTES the other\n")
    conf = {a: set() for a in cands}
    hits, unknown = [], []
    for a, b in itertools.combinations(cands, 2):
        v, n = SP.predict(cur[a], cur[b])
        if v is None:
            # NOT a pass. predict() returns None when the shared history is under MIN_DAYS, which
            # is 25% of pairs in the current bank (curves come in 2494- and 1236-day flavours).
            # Folding those into "none — every candidate is an independent family" turned an
            # ABSENCE OF MEASUREMENT into a positive claim of independence, and two same-family
            # alphas submitted together waste a slot and the cell it was meant to fill.
            unknown.append((a, b, n))
            continue
        if v >= GATE:
            conf[a].add(b)
            conf[b].add(a)
            hits.append((v, a, b))
    if hits:
        for v, a, b in sorted(hits, reverse=True):
            edge = "  (within tool error of the gate)" if v < GATE + 0.022 else ""
            print(f"   {a:11} x {b:11} {v:.4f}{edge}")
    elif not unknown:
        print("   none — every candidate is an independent family")
    else:
        print("   no measured conflict")
    if unknown:
        print(f"\n   UNMEASURABLE ({len(unknown)} pair(s)) — shared history under "
              f"{SP.MIN_DAYS}d, independence NOT established:")
        for a, b, n in unknown:
            print(f"   {a:11} x {b:11} only {n} common days")

    if plan:
        # Maximal conflict-free set, fewest-conflicts-first. Deterministic and good enough: the
        # graph is small and the tie-break that matters (which CELL an alpha fills) belongs to the
        # caller, not here.
        keep = []
        for a in sorted(cands, key=lambda x: (len(conf[x]), x)):
            if not any(k in conf[a] for k in keep):
                keep.append(a)
        print(f"\n3) CONFLICT-FREE SET: {len(keep)} of {len(cands)}")
        print(f"   {' '.join(keep)}")
        dropped = [a for a in cands if a not in keep]
        if dropped:
            print(f"   dropped as duplicates: {' '.join(dropped)}")
        # "Conflict-free" only means no MEASURED conflict. Say so when the set rests on pairs the
        # predictor could not evaluate, so the caller knows which part of the claim is evidence.
        risky = [(a, b, n) for a, b, n in unknown if a in keep and b in keep]
        if risky:
            print(f"   CAVEAT: {len(risky)} pair(s) inside this set are UNMEASURED — "
                  f"prefer a candidate with a full history where one exists:")
            for a, b, n in risky:
                print(f"      {a} x {b} ({n}d shared)")


if __name__ == "__main__":
    main(sys.argv[1:])
