#!/usr/bin/env python3
"""Screen the backlog from PnL curves instead of waiting on platform correlations.

WHY THIS REPLACES THE CORRELATION HARVEST. Measured 2026-08-01, the two recordsets behave nothing
alike even though they look the same:

    /alphas/<id>/recordsets/pnl        25/25 retrieved on the SECOND request  -- computed on demand
    /alphas/<id>/correlations/<kind>   still PENDING hours later              -- never queued at all

/check returns in one second and still reports SELF_CORRELATION and PROD_CORRELATION as PENDING, so
the platform simply is not scheduling that work for old alphas. Correlations arrive as part of a
SIMULATION, which is why driver.py measures 19 of 20 within its own round while a standalone
harvester hammered 120 alphas for 36 minutes, added one record, and 429'd the account.

So: take what the curve gives, and stop waiting for what will not come. Validated against 111
alphas with both a curve and platform-reported metrics:

    sharpe            median err 0.0037   corr 0.9998   <- effectively exact
    IS_LADDER_SHARPE  median err 0.0241   corr 0.9534   <- the ladder IS the trailing 2-YEAR sharpe
    max drawdown      median err 0.0227   corr 0.8270   <- approximate
    self-correlation  median err 0.0181                 <- 99.2% correct at the 0.7 gate

Three of the four hard gates plus the thing that decides family duplication, none of which needs
the platform. NOT derivable: turnover, returns, prod-correlation, sub-universe sharpe.

An alpha cleared here is SELF-clean, not submittable: prod-correlation is still unknown, and
tools/submit_alphas.py re-measures it for real before any POST. What this buys is knowing which of
~1,700 backlog alphas are even worth that measurement.

  python3 tools/harvest_pnl.py --limit 200
  python3 tools/harvest_pnl.py --loop          # keep going, resumable
"""
import argparse, json, math, pathlib, statistics as st, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import harvest_corr as HC                                           # noqa: E402  backlog/session
import self_corr_predict as SP                                      # noqa: E402

OUT = ROOT / "state/pnl_screen.json"
CURVES = ROOT / "state/pnl_curves"
SHARPE_BAR = 1.58
LADDER_BAR = 2.02      # the turnover<0.30 tier; the strict tier is 2.38
SELF_GATE = 0.7
MIN_DAYS = 600


def curve_metrics(c):
    """sharpe / ladder(2y) / drawdown from a cumulative daily PnL curve."""
    days = sorted(c)
    A = [c[d] for d in days]
    dP = [A[i] - A[i - 1] for i in range(1, len(A))]
    if len(dP) < MIN_DAYS:
        return None
    sd = st.pstdev(dP)
    sharpe = (st.mean(dP) / sd) * math.sqrt(252) if sd else None
    k = int(252 * 2)
    lad = None
    if k < len(dP):
        w = dP[-k:]
        s2 = st.pstdev(w)
        # The ladder is a TRAILING TWO-YEAR sharpe. Reading "trailing N-year" as the longest
        # window scored 0.83 and as the worst window 0.81; two years scores 0.95.
        lad = (st.mean(w) / s2) * math.sqrt(252) if s2 else None
    peak, worst = A[0], 0.0
    for v in A:
        peak = max(peak, v)
        worst = max(worst, peak - v)
    dd = worst / abs(A[-1]) if A[-1] else None
    return {"pnl_sharpe": round(sharpe, 4) if sharpe else None,
            "pnl_ladder2y": round(lad, 4) if lad else None,
            "pnl_drawdown": round(dd, 4) if dd else None,
            "days": len(A)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--gap", type=float, default=0.6)
    args = ap.parse_args()

    s = HC.session()
    book_ids = [f.stem for f in CURVES.glob("*.json")]
    try:
        active = set(json.load(open(ROOT / "state/active_ids.json")))
    except Exception:
        import submit_safety as SS
        active = set(SS.active_ids(s))
        json.dump(sorted(active), open(ROOT / "state/active_ids.json", "w"))
    book = [b for b in book_ids if b in active]
    bookc = {b: SP.pnl(None, b) for b in book}
    bookc = {k: v for k, v in bookc.items() if v}
    print(f"book curves for the self-corr screen: {len(bookc)}", flush=True)

    while True:
        try:
            out = json.load(open(OUT))
        except Exception:
            out = {}
        todo = [a for a, _ in HC.backlog() if a not in out][:args.limit]
        if not todo:
            print("nothing left to screen", flush=True)
            return
        done = passed = 0
        for aid in todo:
            # Two spaced attempts: the FIRST request only queues the computation and answers
            # 200-empty. Reading that as "no curve" is the mistake that hid 25 available curves.
            c = SP.pnl(s, aid, budget=8)
            if not c:
                time.sleep(2)
                c = SP.pnl(s, aid, budget=20)
            if not c:
                out[aid] = {"pnl": False}
                done += 1
                continue
            m = curve_metrics(c) or {}
            mx, partner = 0.0, None
            for b, bc in bookc.items():
                if b == aid:
                    continue
                v, _ = SP.predict(c, bc)
                if v is not None and v > mx:
                    mx, partner = v, b
            m.update({"pnl": True, "self_pred": round(mx, 4), "self_partner": partner})
            m["screen_ok"] = bool(m.get("pnl_sharpe") and m["pnl_sharpe"] >= SHARPE_BAR
                                  and m.get("pnl_ladder2y") and m["pnl_ladder2y"] >= LADDER_BAR
                                  and mx < SELF_GATE)
            out[aid] = m
            done += 1
            if m["screen_ok"]:
                passed += 1
                print(f"  PASS {aid}  sharpe={m['pnl_sharpe']} ladder2y={m['pnl_ladder2y']} "
                      f"self={mx}", flush=True)
            if done % 20 == 0:
                tmp = OUT.with_suffix(".tmp")
                json.dump(out, open(tmp, "w"))
                tmp.replace(OUT)
                print(f"  [{done}/{len(todo)}] screened, {passed} pass", flush=True)
            time.sleep(args.gap)
        tmp = OUT.with_suffix(".tmp")
        json.dump(out, open(tmp, "w"))
        tmp.replace(OUT)
        print(f"pass done: screened {done}, {passed} clear the PnL-derived gates", flush=True)
        if not args.loop:
            return


if __name__ == "__main__":
    main()
