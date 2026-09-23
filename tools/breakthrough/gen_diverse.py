#!/usr/bin/env python3
"""Break the one grammar this pipeline has been emitting all session, and sweep the space around it.

Everything simulated so far is ONE skeleton with five binary switches on it:

    signed_power(zscore(ts_decay_linear(add(<carrier> + N x +-rank(field) x w), decay)), power)

That uses **11 of the platform's 67 operators**. Untouched: the entire Group family (6), the entire
Logical family (11), and most of Time Series -- ts_zscore, ts_rank, ts_corr, ts_covariance,
ts_quantile, hump, days_from_last_change, trade_when. Whole classes of alpha are unreachable from
that skeleton: nothing peer-relative, nothing mean-reverting, nothing regime-conditional, nothing
built on the relationship BETWEEN two fields.

Two things learned the hard way on 2026-08-02 are built in rather than re-litigated:

  * KEEP A PRICE-VOLUME CARRIER on most rows. OBSERVED, mechanism unknown: carrier-free measured
    0 zero-fail over 2,039 rows spanning all 28 open-cell pairs, median IS_LADDER_SHARPE -0.02
    against 0.53 with the carrier. Why is NOT established -- price persistence, numeric scale and
    a leg-count/role confound are all still consistent with it (see O1 in HYPOTHESES.md). The
    carrier is kept because the regularity predicts, not because it is understood. A carrier-free
    arm remains so the question stays open to measurement.
  * ONE normalizer at the end, weights <=1 and monotone (magnitudes()). Per-leg zscore measured
    0.5% zero-fail against 3.6%, on a grid balanced across all seven cells.

ROLE-AWARE, which is what state/field_roles.json was built for. A field's role decides which
operators MEAN anything on it, so the generator no longer applies ts_delta to a field that is
already a change:

    LEVEL      a stock at a point in time      -> delta, mean-reversion, peer-relative all valid
    FLOW       a rate per period               -> delta is ACCELERATION; abnormality via ts_zscore
    CHANGE     already a difference            -> never difference again (delta_ok is false)
    RATIO      already normalised              -> rank/peer-rank, never re-scale
    SENTIMENT  a signed opinion                -> smooth or take sign, do not rank raw noise
    EVENT      sparse occurrences              -> ts_backfill first, or days_from_last_change
    META       describes the data, not the market -> EXCLUDED outright

Note: the group fields (industry/subindustry/sector/market) carry category PRICE VOLUME, so any
group operator pulls PV into the alpha's cell membership exactly as the carrier does.

  python3 tools/breakthrough/gen_diverse.py --out pool.json --total 10000
"""
import argparse, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "breakthrough"))
sys.path.insert(0, str(ROOT / "tools"))
import gen_pyramid as GP                                            # noqa: E402

CARRIER = GP.CARRIER
NEUTS = ["INDUSTRY", "SUBINDUSTRY", "STATISTICAL", "MARKET"]
DECAYS = [2, 4, 6, 10, 16]
TRUNCS = [0.01, 0.02, 0.04]
# `market` is ONE group, so group_zscore(x, market) == zscore(x) and group_rank(x, market) ==
# rank(x) (logic_operators.md law 4) -- a peer-relative leg over it is a duplicate, not a signal.
# It stays available to group_neutralize only, where MARKET is a real neutralization setting.
GROUPS = ["industry", "subindustry", "sector"]
# group_neutralize is the ONE group op the precheck ties to settings.neutralization, and only
# these three have a matching neutralization value -- `sector` has none, so it can appear in
# group_zscore/group_rank but never in group_neutralize.
# ...and `market` is useless in group_neutralize for the same reason: logic_check flags
# group_*(x, market) as "== the plain cross-sectional op", which the platform's own neutralization
# setting already performs. Only true sub-market partitions add information.
NEUT_GROUPS = ["industry", "subindustry"]
SHORT_D = [5, 10, 20]
LONG_D = [60, 120, 250]

# leg recipes permitted per role -- the whole point of the labels
ROLE_LEGS = {
    "LEVEL":     ["raw", "delta", "revert", "tsrank", "peer", "avdiff"],
    "FLOW":      ["raw", "abnormal", "tsrank", "peer", "delta"],
    "CHANGE":    ["raw", "sign", "tsrank", "peer"],
    "RATIO":     ["raw", "tsrank", "peer", "revert"],
    "SENTIMENT": ["raw", "smooth", "sign", "tsrank"],
    "EVENT":     ["backfilled", "since"],
}


def roles():
    try:
        return json.load(open(ROOT / "state/field_roles.json"))
    except Exception:
        return {}


def leg(rng, fid, ty, role, info):
    """One signal leg, chosen from the recipes that MEAN something for this field's role."""
    base = f"vec_avg({fid})" if ty == "VECTOR" else fid
    choices = list(ROLE_LEGS.get(role, ["raw", "tsrank"]))
    if not info.get("delta_ok", True):
        choices = [c for c in choices if c not in ("delta", "avdiff")]
    r = rng.choice(choices)
    g = rng.choice(GROUPS)
    if r == "raw":
        x = f"rank({base})"
    elif r == "delta":
        x = f"rank(ts_delta({base}, {rng.choice(SHORT_D)}))"
    elif r == "avdiff":
        x = f"rank(ts_av_diff({base}, {rng.choice(SHORT_D)}))"
    elif r == "revert":                       # position in its OWN history, not the market's
        # No embedded minus: the caller applies a random sign, and "-" + "-ts_zscore(...)" emitted
        # `--ts_zscore(...)`, which is not valid FASTEXPR. Direction is discovered by the sweep.
        x = f"rank(ts_zscore({base}, {rng.choice(LONG_D)}))"
    elif r == "abnormal":                     # a FLOW far from its own norm
        x = f"rank(ts_zscore({base}, {rng.choice(LONG_D)}))"
    elif r == "tsrank":                        # percentile within its OWN history, not the market
        x = f"ts_rank({base}, {rng.choice(LONG_D)})"
    elif r == "peer":                          # relative to industry peers, not the whole market
        x = (f"rank(group_zscore({base}, {g}))" if rng.random() < 0.5
             else f"group_rank({base}, {g})")
    elif r == "smooth":
        x = f"rank(ts_mean({base}, {rng.choice(SHORT_D)}))"
    elif r == "sign":
        x = f"multiply(sign({base}), 0.5)"     # sign spans 2, rank spans 1 -- halve to match
    elif r == "backfilled":
        x = f"rank(ts_backfill({base}, {rng.choice([20, 60, 120])}))"
    elif r == "since":
        x = f"rank(days_from_last_change({base}))"      # sign applied by the caller, see `revert`
    else:
        x = f"rank({base})"
    return ("-" if rng.random() < 0.5 else "") + x, r


# EVERY leg must leave this function on the SAME 0..1 scale as rank(). Per OPERATORS.md,
# ts_rank and group_rank return 0..1 but ts_zscore and group_zscore return standard deviations
# (~+-3), so an unwrapped z-score leg at weight 0.5 outweighs a rank leg at weight 1.0 by ~6x.
# That is precisely the failure the leg-scale law names: "magnitudes above 1.0 turned an 8-leg
# ensemble into a 2-leg alpha with six legs of noise". Wrapping the z-scores in rank() keeps the
# meaning (which names are most extreme against their own history / their peers) and the scale.


def weighted(legs, mags):
    return [f"multiply({L}, {m})" for L, m in zip(legs, mags)]


def gate_expr(rng):
    """A regime condition built from price alone, so it costs no extra data category.

    `returns`, `volume` and `adv20` are on state/banned_fields.json -- they belong to alphas
    already submitted, and the standing rule is never to reuse a submitted alpha's field. Close,
    open, high, low, vwap and cap are not banned, so volatility and liquidity are expressed
    through them instead of through the obvious field."""
    kind = rng.choice(["vol", "trend", "range", "size"])
    d = rng.choice(LONG_D)
    if kind == "vol":                       # realised vol from a close-to-close return proxy
        ret = "divide(close, ts_delay(close, 1))"
        return f"less(ts_std_dev({ret}, {d}), ts_mean(ts_std_dev({ret}, 20), {d}))"
    if kind == "trend":
        return f"greater(close, ts_mean(close, {d}))"
    if kind == "range":                     # intraday range as an activity proxy for volume
        rg = "divide(high, low)"
        return f"greater({rg}, ts_mean({rg}, {d}))"
    return f"greater(cap, ts_mean(cap, {d}))"


def build(rng, picked, family, carrier, R):
    """picked = [(uc, fid, ty)]; returns (formula, used_leg_recipes) or None."""
    n = len(picked)
    if n < 4:
        return None
    mags = GP.magnitudes(n + (2 if carrier else 0))
    ms = mags[2:] if carrier else mags
    forced = None
    parts, recipes = [], []
    for (uc, fid, ty), m in zip(picked, ms):
        info = R.get(fid) or {}
        L, r = leg(rng, fid, ty, info.get("label", "LEVEL"), info)
        parts.append((L, m))
        recipes.append(r)
    head = list(CARRIER) if carrier else []

    def block(sel):
        legs = head + weighted([L for L, _ in sel], [m for _, m in sel])
        return "add(" + ", ".join(legs) + ", filter=true)"

    half = max(2, n // 2)
    if family == "ADD":                        # the baseline, kept as a control
        body = block(parts)
    elif family == "GROUPNEUT":                # strip the industry factor from the whole ensemble
        forced = rng.choice(NEUT_GROUPS)       # settings.neutralization must match; see NEUT_GROUPS
        body = f"group_neutralize({block(parts)}, {forced})"
    elif family == "GATED":                    # trade only in the regime where the edge should exist
        body = f"trade_when({gate_expr(rng)}, {block(parts)}, -1)"
    elif family == "BLEND":                    # two different signals, switched by regime
        body = (f"if_else({gate_expr(rng)}, zscore({block(parts[:half])}), "
                f"zscore({block(parts[half:])}))")
    elif family == "PRODUCT":                  # fires only where two independent halves agree
        # logic_operators.md law 6: "Rank both legs to [0,1] before any product." Multiplying two
        # CENTERED z-scores makes negative x negative = positive, so the alpha would go LONG the
        # names both halves rank worst -- the opposite of "both agree".
        body = (f"multiply(rank({block(parts[:half])}), "
                f"rank({block(parts[half:])}), filter=true)")
    elif family == "DIVERGE":                  # the SPREAD between two halves, not their sum
        body = (f"subtract(zscore({block(parts[:half])}), "
                f"zscore({block(parts[half:])}))")
    elif family == "TERM":                     # fast view minus slow view of the same ensemble
        b = block(parts)
        body = f"subtract(ts_mean({b}, {rng.choice(SHORT_D)}), ts_mean({b}, {rng.choice(LONG_D)}))"
    elif family == "COMOVE":                   # how two halves MOVE TOGETHER, a pure relationship
        body = (f"ts_corr(zscore({block(parts[:half])}), zscore({block(parts[half:])}), "
                f"{rng.choice(LONG_D)})")
    else:
        return None

    shape = rng.choice(["decayZ", "decayZ", "winsor", "quantile", "hump", "power", "plain"])
    w = rng.choice([10, 20, 50])
    if shape == "decayZ":
        out = f"zscore(ts_decay_linear({body}, {w}))"
    elif shape == "winsor":
        # logic_operators.md law 5: "the only second layers that pay are non-affine ... winsorize
        # BEFORE zscore". Winsorising AFTER an outermost zscore is an affine-absorbed no-op.
        out = f"zscore(winsorize(ts_decay_linear({body}, {w}), std=4))"
    elif shape == "quantile":
        out = f"quantile(ts_decay_linear({body}, {w}))"
    elif shape == "hump":
        out = f"hump(zscore(ts_decay_linear({body}, {w})), hump=0.01)"
    elif shape == "power":
        out = f"signed_power(zscore(ts_decay_linear({body}, {w})), {rng.choice([1.5, 2.5])})"
    else:
        out = f"zscore({body})"
    return out, shape, sorted(set(recipes)), forced


FAMILIES = ["ADD", "GROUPNEUT", "GATED", "BLEND", "PRODUCT", "DIVERGE", "TERM", "COMOVE"]

# FASTEXPR refuses any expression with more than 64 operators:
#   "Expression with 91 operators exceeds limit of 64"
# This is not a rounding concern, it is a silent SAMPLING BIAS. An interaction leg costs 4
# operators where a plain rank leg costs 1, so the long interaction ensembles ERROR while the
# short ones survive -- 220 of 1,096 interaction rows in the 2026-08-02 journal died this way,
# every one of them ERROR with no alpha id. Every addition-vs-multiplication comparison in this
# project was therefore run on an interaction arm truncated to its SHORTEST members. Reject at 60
# to leave headroom for the settings wrapper.
OP_LIMIT = 60


def op_count(f):
    return len(re.findall(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--total", type=int, default=10000)
    ap.add_argument("--tag", default="DV")
    ap.add_argument("--seed", type=int, default=41)
    ap.add_argument("--carrier-free-share", type=float, default=0.12)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    R = roles()
    print(f"field roles loaded: {len(R)}")

    fields = GP.load_fields()
    full = GP.full_cells()
    want = [(cn, sn) for (cn, sn), pool in fields.items()
            if GP.cell_weight(cn, sn, full=full) > 0 and len(pool) >= 8]
    print(f"open cells to mine: {sorted({cn for cn, _ in want})}")

    # META fields describe the data, not the market: one produced sharpe 11.18 / fitness 14.94,
    # which is an artifact. Drop them before anything is built from them.
    usable = {}
    dropped = 0
    for k in want:
        keep = []
        for uc, fid, ty in fields[k]:
            if (R.get(fid) or {}).get("label") == "META":
                dropped += 1
                continue
            keep.append((uc, fid, ty))
        if len(keep) >= 8:
            usable[k] = keep
    print(f"dropped {dropped} META fields; {len(usable)} buckets usable")
    if not usable:
        raise SystemExit("no usable buckets")

    seen = set()
    for p in ROOT.glob("state/**/*targets*.json"):
        try:
            rr = json.load(open(p))
        except Exception:
            continue
        if isinstance(rr, list):
            for r in rr:
                if isinstance(r, dict) and r.get("formula"):
                    seen.add(r["formula"])
    print(f"excluding {len(seen)} formulas already staged")

    cells = list(usable)
    per = max(50, args.total // len(FAMILIES))
    rows = []
    for fam in FAMILIES:
        made = tries = 0
        while made < per and tries < per * 80:
            tries += 1
            cn, sn = cells[rng.randrange(len(cells))]
            pool = usable[(cn, sn)]
            k = rng.randint(4, 8)
            head = pool[: max(k, len(pool) // 2)]
            if len(head) < k:
                continue
            carrier = rng.random() >= args.carrier_free_share
            built = build(rng, rng.sample(head, k), fam, carrier, R)
            if not built:
                continue
            f, shape, recipes, forced = built
            if f in seen or op_count(f) > OP_LIMIT:
                continue
            seen.add(f)
            oid = f"{args.tag}{fam[:4]}_{cn.replace(' ', '')[:8]}_{made:04d}"
            rows.append({"old_id": oid, "id": oid, "formula": f,
                         "settings": dict(GP.SETTINGS_BASE, decay=rng.choice(DECAYS),
                                          neutralization=(forced.upper() if forced
                                                          else rng.choice(NEUTS)),
                                          truncation=rng.choice(TRUNCS)),
                         "meta": {"skeleton": f"{fam}+{shape}" + ("+carrier" if carrier else ""),
                                  "dataset": f"{cn}/{sn}", "mechanic": f"{cn}/{sn}",
                                  "family": fam, "shape": shape, "carrier": carrier,
                                  "legs_used": "|".join(recipes),
                                  "combine": fam, "norm": "oneZ",
                                  "power": shape == "power", "backfill": "backfilled" in recipes,
                                  "category_target": cn,
                                  "universe": "TOP3000", "legs": k,
                                  "neutralization": "", "decay": 0, "truncation": 0}})
            made += 1
        print(f"  {fam:10} -> {made}")
    rng.shuffle(rows)                      # never let file order decide a tied draw
    json.dump(rows, open(args.out, "w"))
    import collections
    print(f"\nwrote {len(rows)} rows -> {args.out}")
    print("  shapes :", dict(collections.Counter(r["meta"]["shape"] for r in rows)))
    print("  carrier:", dict(collections.Counter(r["meta"]["carrier"] for r in rows)))
    lg = collections.Counter()
    for r in rows:
        for x in r["meta"]["legs_used"].split("|"):
            lg[x] += 1
    print("  leg recipes:", dict(lg.most_common()))


if __name__ == "__main__":
    main()
