#!/usr/bin/env python3
"""Learn which ALPHA STRUCTURES actually win, from the platform's own bank.

The pipeline has been generating one grammar all session:

    signed_power(zscore(ts_decay_linear(add(<carrier> + N x +-rank(field) x w), decay)), power)

an ADDITIVE ensemble of signed ranks behind a fixed price-volume carrier. It works, but it is one
point in a large space, and it was chosen by history rather than by comparison.

Meanwhile the bank contains alphas clearing every hard gate with a completely different grammar:

    add( multiply(zscore(multiply( rank(ts_backfill(LEVEL, 5)),
                                   rank(ts_delta(ts_backfill(CHANGE, 5), 1)) )), w), ... )

That one MULTIPLIES a level by its own change instead of adding independent signals, z-scores each
leg separately instead of once at the end, and backfills for sparse data. Thirteen of them reach
ladder 2.4-3.5 with no OHLCV token at all.

So: stop inventing structures and measure the ones that already exist. This extracts a structural
SIGNATURE from each alpha's code -- the operator skeleton, how legs combine, whether it uses
backfill, neutralisation, decay -- joins it to the platform's own metrics, and ranks signatures by
what they actually produce.

  python3 tools/structure_mine.py --pages 40
  python3 tools/structure_mine.py --pages 40 --out state/structures.json
"""
import argparse, collections, json, pathlib, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "funnel"))
import gates                                                        # noqa: E402
import submit_alphas as SA                                          # noqa: E402

API = "https://api.worldquantbrain.com/users/self/alphas"
LADDER_BAR = 2.02

# Operators worth recording as structural features. Anything else is treated as a field token.
OPS = ["signed_power", "ts_decay_linear", "ts_backfill", "group_neutralize", "ts_rank",
       "ts_delta", "ts_av_diff", "ts_zscore", "ts_mean", "ts_std_dev", "ts_corr", "ts_sum",
       "ts_regression", "zscore", "rank", "winsorize", "normalize", "quantile",
       "trade_when", "if_else", "vec_avg", "power", "sign", "log", "scale",
       "multiply", "divide", "subtract", "add", "hump", "ts_scale"]


def signature(code):
    """A structural fingerprint: which operators, how the top level combines, leg shape.

    Deliberately ignores WHICH fields are used — the question here is what SHAPE wins, and field
    choice is answered separately by the cell targeting."""
    c = re.sub(r"\s+", "", code)
    present = tuple(sorted(o for o in OPS if re.search(rf"\b{o}\(", c)))
    top = "?"
    m = re.match(r"^(?:alpha\s*=\s*)?([a-z_]+)\(", c)
    if m:
        top = m.group(1)
    # Multiplicative INTERACTION: a multiply whose two arguments are both ranked signals.
    # `[^)]*` cannot express this -- the arguments are nested calls like rank(ts_backfill(x,5)) --
    # so the first version of this detector matched nothing and every alpha was labelled ADDITIVE,
    # which silently answered the one question the scan exists to ask. Scan with a depth counter.
    interact = False
    for m in re.finditer(r"multiply\(", c):
        i, depth, args, start = m.end(), 1, [], m.end()
        while i < len(c) and depth:
            if c[i] == "(":
                depth += 1
            elif c[i] == ")":
                depth -= 1
                if depth == 0:
                    args.append(c[start:i])
            elif c[i] == "," and depth == 1:
                args.append(c[start:i])
                start = i + 1
            i += 1
        if len(args) >= 2 and all(a.startswith(("rank(", "-rank(", "ts_rank(")) for a in args[:2]):
            interact = True
            break
    # per-leg zscore vs one normaliser at the end
    per_leg_z = len(re.findall(r"zscore\(multiply\(", c))
    legs = len(re.findall(r"multiply\((?:zscore|-?rank|ts_)", c))
    return {"top": top, "ops": present, "interaction": interact,
            "per_leg_zscore": per_leg_z, "legs": legs,
            "backfill": "ts_backfill(" in c, "neutralize": "group_neutralize(" in c,
            "decay": "ts_decay_linear(" in c, "power": "signed_power(" in c}


def key(sig):
    """Short human-readable label for a signature class."""
    bits = []
    bits.append("INTERACT" if sig["interaction"] else "ADDITIVE")
    bits.append("perlegZ" if sig["per_leg_zscore"] >= 2 else "oneZ")
    if sig["backfill"]:
        bits.append("backfill")
    if sig["neutralize"]:
        bits.append("groupneut")
    if sig["decay"]:
        bits.append("decay")
    if sig["power"]:
        bits.append("power")
    return "+".join(bits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=40)
    ap.add_argument("--per", type=int, default=50)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    s = SA.session()
    stats = collections.defaultdict(lambda: {"n": 0, "clean": 0, "lad": [], "sharpe": [],
                                             "examples": []})
    n = 0
    for i in range(args.pages):
        r = s.get(API, params={"limit": args.per, "offset": i * args.per,
                               "status": "UNSUBMITTED", "is.sharpe>": 1.0,
                               "order": "-is.sharpe"}, timeout=90)
        if r.status_code != 200:
            time.sleep(4)
            continue
        res = (r.json() or {}).get("results") or []
        if not res:
            break
        for a in res:
            st = a.get("settings") or {}
            if st.get("region") != "USA" or st.get("delay") != 1:
                continue
            code = (a.get("regular") or {}).get("code", "")
            if not code:
                continue
            n += 1
            isb = a.get("is") or {}
            ck = {c["name"]: c for c in isb.get("checks", []) if isinstance(c, dict)}
            lad = (ck.get("IS_LADDER_SHARPE") or {}).get("value")
            ok = (not gates.hard_fails(isb.get("checks"))
                  and isinstance(lad, (int, float)) and lad >= LADDER_BAR)
            k = key(signature(code))
            d = stats[k]
            d["n"] += 1
            if isinstance(lad, (int, float)):
                d["lad"].append(lad)
            if isb.get("sharpe") is not None:
                d["sharpe"].append(isb["sharpe"])
            if ok:
                d["clean"] += 1
                if len(d["examples"]) < 2:
                    d["examples"].append({"id": a["id"], "ladder": lad,
                                          "sharpe": isb.get("sharpe"), "code": code[:300]})
        time.sleep(0.3)

    import statistics as stt
    rows = []
    for k, d in stats.items():
        if d["n"] < 15:
            continue
        rows.append((k, d["n"], d["clean"], d["clean"] / d["n"],
                     stt.median(d["lad"]) if d["lad"] else 0,
                     stt.median(d["sharpe"]) if d["sharpe"] else 0, d["examples"]))
    rows.sort(key=lambda r: -r[3])
    print(f"scanned {n} USA-d1 alphas\n")
    print(f"{'structure':44} {'n':>5} {'clean':>6} {'rate':>7} {'medLad':>7} {'medSh':>6}")
    for k, cnt, cl, rate, ml, ms, _ in rows:
        print(f"{k:44} {cnt:5} {cl:6} {rate:6.1%} {ml:7.2f} {ms:6.2f}")
    if args.out:
        json.dump([{"structure": k, "n": c, "clean": cl, "rate": rate,
                    "med_ladder": ml, "med_sharpe": ms, "examples": ex}
                   for k, c, cl, rate, ml, ms, ex in rows], open(args.out, "w"), indent=1)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
