#!/usr/bin/env python3
"""The submittable bank, read from the PLATFORM rather than from our own journal.

WHY THIS SUPERSEDES THE JOURNAL SCAN. `GET /users/self/alphas` returns, per alpha and in bulk, the
entire `is` block — sharpe, fitness, turnover, returns, drawdown — plus all 19 checks with their
values, and it FILTERS SERVER-SIDE. Measured 2026-08-01:

    our journal knows                             2,203 zero-fail
    platform, UNSUBMITTED, is.sharpe>1.58          6,785
    ...and is.fitness>1.0                          5,283   of which ~73% clear every hard gate

The journal only holds what this session's tools happened to record. The platform holds every alpha
ever simulated, including everything from earlier tools and sessions, and it already computed the
metrics we were re-deriving from PnL curves — IS_LADDER_SHARPE comes back as a value, so there is
no need to reconstruct it.

TWO TRAPS THIS ENCODES.

Rank by LADDER, never by sharpe. Ordering by `-is.sharpe` puts degenerate alphas on top: the first
page returned sharpe 15.19 / fitness 17.72 / ladder 0.0, which the platform will reject on submit.
The ladder is the binding gate (0 of 5,775 ladder-FAIL rows was ever zero-fail), so it is the
ranking key.

Screen with gates.hard_fails, never with a BLOCKING allowlist. IS_LADDER_SHARPE is a hard gate but
is NOT in BLOCKING, so `[n for n in BLOCKING if ...]` silently passes ladder failures — 7% of a
500-alpha sample.

What the platform will NOT give: SELF_CORRELATION and PROD_CORRELATION read PENDING on all 600
unsubmitted alphas sampled, and stay that way — correlations are computed as part of a SUBMISSION,
not on request. Self-correlation therefore still comes from tools/self_corr_predict.py (PnL curves,
+-0.018); prod-correlation is only knowable at submit time.

  CONTRADICTED IN PART, 2026-08-10. The 600-alpha sample above still reproduces at scale — 922
  unsubmitted backlog alphas answered 200 with an EMPTY body across 968 requests over 8 hours, and
  asking repeatedly never resolved them. But "only knowable at submit time" is too strong: 25
  unsubmitted alphas from that same backlog carry real prod numbers in
  state/prod_corr_measured.json (e.g. Vk3GgWJA 0.962, 1YzzAWzK 0.856), measured while they were
  UNSUBMITTED. So correlations are sometimes computable on request and usually are not, and what
  separates the two cases is MECHANISM: UNKNOWN. Treat an empty body as "no data available now",
  never as "this alpha has no correlation" — and never plan a workflow that depends on the backlog
  becoming measurable, which is the mistake that cost a day here.

  python3 tools/bank.py                    # top of the bank by ladder
  python3 tools/bank.py --pages 20 --out state/bank.json
"""
import argparse, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import gates                                                        # noqa: E402
import submit_alphas as SA                                          # noqa: E402

API = "https://api.worldquantbrain.com/users/self/alphas"
LADDER_BAR = 2.02      # turnover<0.30 tier; the strict tier is 2.38


def fetch(s, pages=10, per=50, sharpe=1.58, fitness=1.0, region="USA", delay=1):
    """Pull UNSUBMITTED alphas that already clear the two headline gates, server-side."""
    out, seen = [], set()
    for i in range(pages):
        params = {"limit": per, "offset": i * per, "status": "UNSUBMITTED",
                  "is.sharpe>": sharpe, "is.fitness>": fitness, "order": "-is.sharpe"}
        try:
            j = s.get(API, params=params, timeout=90).json()
        except Exception:
            break
        res = j.get("results") or []
        if not res:
            break
        for a in res:
            if a["id"] in seen:
                continue
            seen.add(a["id"])
            st = a.get("settings") or {}
            if st.get("region") != region or st.get("delay") != delay:
                continue
            isb = a.get("is") or {}
            ck = {c["name"]: c for c in isb.get("checks", []) if isinstance(c, dict)}
            fails = gates.hard_fails(isb.get("checks"))
            lad = (ck.get("IS_LADDER_SHARPE") or {}).get("value")
            out.append({"id": a["id"], "sharpe": isb.get("sharpe"),
                        "fitness": isb.get("fitness"), "turnover": isb.get("turnover"),
                        "returns": isb.get("returns"), "drawdown": isb.get("drawdown"),
                        "ladder": lad, "fails": fails,
                        "code": (a.get("regular") or {}).get("code", "")})
        time.sleep(0.4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--per", type=int, default=50)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    s = SA.session()
    rows = fetch(s, pages=args.pages, per=args.per)
    clean = [r for r in rows if not r["fails"]
             and isinstance(r["ladder"], (int, float)) and r["ladder"] >= LADDER_BAR]
    # Ladder first — see the module docstring on why sharpe is the wrong key.
    clean.sort(key=lambda r: -(r["ladder"] or 0))
    print(f"pulled {len(rows)} USA-d1 UNSUBMITTED past sharpe>1.58 & fitness>1.0")
    print(f"  clear EVERY hard gate incl. ladder>={LADDER_BAR}: {len(clean)} "
          f"({len(clean)/len(rows):.0%})" if rows else "  nothing returned")
    if args.out:
        json.dump(clean, open(args.out, "w"))
        print(f"  wrote {args.out}")
    print(f"\n{'alpha':10} {'ladder':>7} {'sharpe':>7} {'fitness':>8} {'turnover':>9}")
    for r in clean[:args.top]:
        print(f"{r['id']:10} {r['ladder']:7.2f} {r['sharpe']:7.2f} {r['fitness']:8.2f} "
              f"{r['turnover']:9.4f}")


if __name__ == "__main__":
    main()
