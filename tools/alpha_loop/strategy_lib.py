#!/usr/bin/env python3
"""strategy_lib.py — GENERALIZED trading-logic strategy generator (dataset-agnostic).

Core of the alpha-loop skill. Encodes the ratified trading-logic methodology
(fetched/trading_logic_methodology.md): a market mechanic = a RELATIONSHIP between fields,
expressed with the operator that matches it. Generalizes past pv1 by:
  1. classifying every field of ANY dataset into a ROLE from its description,
  2. filling relationship TEMPLATES with role-matched fields,
  3. emitting both signs (a wrong ex-ante sign is a data discovery, not sign-fishing).

Validated mechanics that win on BRAIN data: CHANGE/interaction/divergence/mean-reversion
(NOT raw level/state). Templates below are those shapes, dataset-independent.
"""
from __future__ import annotations
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CATALOG = ROOT / "fetched/fields_all.jsonl"          # USA (the default region)


def use_region(region="USA"):
    """Point the generator at another region's catalog.

    Field ids are NOT portable across regions (Khoa 2026-07-29). Measured USA vs GLB: of 28,333
    GLB fields only 1,813 ids exist in USA at all, and among those 6 have a different TYPE
    (`pv13_new_*l_scibr` is GROUP in USA, MATRIX in GLB), 3 sit in a different dataset, and 440
    differ in coverage by more than 0.2. Generating GLB alphas off the USA catalog would both hide
    26,520 fields and mis-type the ones it did see.

    Returns the catalog path in use so a caller can assert which region it is generating for."""
    global CATALOG
    CATALOG = ROOT / ("fetched/fields_all.jsonl" if region == "USA"
                      else f"fetched/fields_{region}.jsonl")
    if not CATALOG.exists():
        raise FileNotFoundError(
            f"no catalog for region {region} at {CATALOG} — run "
            f"tools/fetch_region_catalog.py {region} 1 first")
    return CATALOG

# STANDING RULE (Khoa 2026-07-24): a field used in ANY SUBMITTED alpha is BANNED forever — never
# reuse it (field-level reuse = self-correlation with the live book). Includes the OHLCV carrier
# (returns/volume/adv20) once any live alpha used it, which forces genuinely-independent structures.
def _load_banned():
    p = ROOT / "state/banned_fields.json"
    if not p.exists():
        return set()                                   # first run / no bans yet: empty is correct
    # File PRESENT -> it must parse. A partial write (non-atomic regeneration) or corruption must
    # FAIL CLOSED: returning an empty set here would silently disable the standing self-correlation
    # ban and let live-submitted-alpha fields re-enter new formulas. Raise instead of failing open.
    return set(json.load(open(p)).get("banned_fields", []))
BANNED = _load_banned()

def has_banned(formula):
    """True if the formula references any banned field (exact token match)."""
    return any(re.search(r"\b" + re.escape(b) + r"\b", formula) for b in BANNED)

# ---- role classifier: description keywords -> role tags -------------------------------
FLOW_KW   = ("volume", "turnover", "count", "number of", "buzz", "mentions", "activity",
             "trading", "volu", "straddle", "strangle", "shares traded", "utilization")
LEVEL_KW  = ("price", "close", "implied volatility", "rate", "ratio", "score", "level",
             "mean", "median", "estimate", "income", "assets", "margin", "yield", "slope",
             "spread", "probability", "valuation", "value", "moving average")
CHANGE_KW = ("change", "growth", "revision", "momentum", "delta", "acceleration", "trend")
SENT_KW   = ("sentiment", "bullish", "bearish", "positive", "negative", "impact", "skew",
             "surprise", "optimism", "pessimism")

# word-boundaried keyword match (+ optional plural). Raw substring `k in d` misfires: 'count'
# hits account/discount, 'rate' hits accelerate/corporate/aggregate, 'mean' hits meaning, etc.
def _kw_re(kws):
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")s?\b")
FLOW_RE, LEVEL_RE, CHANGE_RE, SENT_RE = map(_kw_re, (FLOW_KW, LEVEL_KW, CHANGE_KW, SENT_KW))

def classify(desc: str) -> set:
    d = (desc or "").lower()
    tags = set()
    if FLOW_RE.search(d):   tags.add("FLOW")
    if CHANGE_RE.search(d): tags.add("CHANGE")
    if SENT_RE.search(d):   tags.add("SENT")
    if LEVEL_RE.search(d):  tags.add("LEVEL")
    if not tags: tags.add("LEVEL")
    return tags

# junk / non-continuous fields: flags, categorical type-vectors, ids, dummies — a ts_delta
# of these is meaningless. Excluded from the continuous-signal pools.
JUNK_KW = ("flag", "dummy", " id ", "identifier", "categor", "type vector", "vector of type",
           "grouping", "which type", "classification code", "boolean", "indicator variable",
           "iso code", "country code", "currency code", "ticker", "sector code", "exchange code",
           # data-PROVENANCE / meta fields describe HOW a value was produced, not a market quantity;
           # ts_delta/rank of them is meaningless and produces lookahead-ish artifacts (iter22:
           # quarterly_value_estimation_method_fast_d1 sh=11.18 fit=14.94 — a confidence level, not alpha).
           # NARROW phrases only (avoid over-excluding legit fields like "confidence interval of forecast").
           "confidence/inference", "inference level", "estimation method", "means more estimated",
           "directly reported", "data quality", "reporting lag")

def _is_junk(fid: str, desc: str) -> bool:
    d = (desc or "").lower()
    if any(k in d for k in JUNK_KW): return True
    if re.search(r"(_flag|_id|_type|_code|_iso|_ticker)(_\w+)?$", fid): return True
    return False

def load_dataset(dataset: str, delay: int = 1, min_cov: float = 0.90, ac_lo: int = 8):
    """Return {role: [ (id, type, cov, ac) ]} for one dataset at a delay. Keeps continuous,
    well-covered fields. alphaCount is NOT a hard cap — crowding matters for theme/novelty,
    not for whether a mechanic works (the pv1 winners use max-crowded close/volume) — it is
    only a soft SORT preference (see rankpool). ac_lo drops untested/near-empty fields."""
    # Single catalog pass builds BOTH the strict pool and the relaxed pool at once. A field that
    # clears the strict cov/ac gate goes to strict; anything clearing the relaxed coverage floor
    # goes to relaxed (superset). This avoids re-reading/re-parsing the whole 10MB catalog a second
    # time — the old two-call form re-parsed it on every generation where any role was empty, which
    # is 61/79 datasets (roles like SENT/CHANGE are empty at ANY threshold), filling nothing.
    rmc = min(min_cov, 0.50)                                 # relaxed coverage floor; relaxed al = 0
    def collect():
        strict  = {"FLOW": [], "LEVEL": [], "CHANGE": [], "SENT": []}
        relaxed = {"FLOW": [], "LEVEL": [], "CHANGE": [], "SENT": []}
        for line in open(CATALOG):
            try: r = json.loads(line)
            except: continue          # skip blank/truncated rows in append-only catalog (cf. loop.read_results)
            d = r.get("dataset")
            did = d.get("id") if isinstance(d, dict) else d   # rich (dict) or flat (str) schema
            if r.get("_delay", r.get("delay", 1)) != delay or did != dataset:
                continue
            if r.get("type") not in ("MATRIX", "VECTOR"): continue
            fid = r.get("id")
            if not fid: continue                            # skip partial/malformed catalog rows
            desc = r.get("description", "")
            if fid in BANNED: continue                      # never reuse a submitted-alpha field
            if _is_junk(fid, desc): continue
            cov = r.get("coverage") or 0
            ac = r.get("alphaCount") or 0
            if cov < rmc: continue                          # below even the relaxed floor -> useless
            entry = (fid, r.get("type"), cov, ac)
            for role in classify(desc):
                if cov >= min_cov and ac >= ac_lo:
                    strict[role].append(entry)
                relaxed[role].append(entry)                 # cov>=rmc guaranteed above; relaxed al=0
        return strict, relaxed
    roles, relaxed = collect()
    # Uncrowded datasets (the ORTHOGONAL ones we want for low prod-corr) have alphaCount~0 and
    # sub-0.90 coverage, so the strict gate rejects most fields. alphaCount is a soft crowding
    # prior, NOT a mechanic-validity gate (see docstring); low coverage only means fewer names
    # traded. Relax PER-EMPTY-ROLE, not all-or-nothing: when only a handful of fields clear 0.90
    # they land in ONE role (e.g. fundamental2 has exactly 1 field >=0.90 -> FLOW), and an
    # `if not any()` gate would see that role non-empty and SUPPRESS the relax entirely, starving
    # the other ~765 sub-0.90 fields down to ~3 near-identical carrier ensembles. Fill only the
    # roles strict left EMPTY from the relaxed pool; roles that already hold strict fields are left
    # untouched, so populated/crowded datasets (all roles filled) skip this and never drift.
    if not all(roles.values()):
        for role, fields in roles.items():
            if not fields:
                roles[role] = relaxed[role]
    return roles

def scalar(field_type: str, fid: str) -> str:
    """A VECTOR field must be aggregated to a scalar before operators apply."""
    return f"vec_avg({fid})" if field_type == "VECTOR" else fid

# ---- relationship templates (dataset-independent shapes) ------------------------------
# Each returns a list of (tag, formula) given field pickers. d = lookback in trading days.
def t_reversal(X, IN, d):
    # X's recent move FADES, confirmed by intensity IN (overreaction reversal)
    return [("rev", f"multiply(rank(-ts_delta({X}, {d})), rank({IN}))")]

def t_overreact(X, IN, d):
    # a move ON intensity is an overreaction -> fade the whole thing
    return [("ovr", f"reverse(multiply(rank(ts_delta({X}, {d})), rank({IN})))")]

def t_zrev(X, IN, w):
    # X far from its own w-day mean + intensity -> mean-revert
    return [("zrev", f"multiply(reverse(rank(ts_zscore({X}, {w}))), rank({IN}))")]

def t_change_mom(X, Y, d):
    # two quantities accelerating together -> continuation
    return [("mom", f"multiply(rank(ts_delta({X}, {d})), rank(ts_delta({Y}, {d})))")]

def t_divergence(X, Y, d):
    # X rising while Y falling (positioning/behaviour divergence)
    return [("div", f"subtract(rank(ts_delta({X}, {d})), rank(ts_delta({Y}, {d})))")]

def t_ratio_rev(X, Y, IN, d):
    # the X/Y ratio's recent move fades, confirmed by intensity
    return [("rrev", f"multiply(rank(-ts_delta(divide({X}, {Y}), {d})), rank({IN}))")]

def t_sent_fade(S, IN, d):
    # extreme sentiment on heavy intensity -> crowded -> fade
    return [("sfade", f"reverse(multiply(rank({S}), rank({IN})))"),
            ("sride", f"multiply(rank(ts_delta({S}, {d})), rank({IN}))")]

# OHLCV family — raw price/volume fields everyone uses -> high PROD-CORRELATION. LIMIT them
# (Khoa 2026-07-21): the ensemble should lean on ORTHOGONAL non-OHLCV legs to survive prod-corr.
OHLCV = {"open", "high", "low", "close", "volume", "returns", "vwap", "adv20", "cap"}
# SYNTHETIC carrier (audit 2026-07-24): returns/volume/adv20 are BANNED (used by live alphas), which
# 100%-dropped the fitness-producing light-carrier ensemble -> yield collapse. Reconstruct the SAME
# microstructure reversal signal from UNBANNED OHLC tokens (close/open/high/low/vwap/cap are NOT
# banned) so the ensemble survives the ban and fitness climbs off the ~0.9 purity ceiling.
MIN_CARRIER = ["-rank(ts_av_diff(close, 5))"]                                  # close mean-reversion (returns-proxy)
LIGHT_CARRIER = ["-rank(divide(close, open))", "multiply(-rank(divide(close, vwap)), 0.6)"]  # intraday reversal + vwap dev
CARRIER = [
    "-rank(divide(close, open))", "multiply(-rank(ts_av_diff(close, 5)), 0.7)",
    "multiply(-rank(divide(close, vwap)), 0.6)", "multiply(-rank(ts_delta(close, 5)), 0.5)",
    "multiply(rank(ts_std_dev(high, 20)), 0.4)", "multiply(-rank(divide(low, close)), 0.4)",
]

def _ds_leg(role, expr, w):
    # a dataset field -> one weighted ±rank micro-signal leg, by its role
    if role == "CHANGE":  return f"multiply(rank(ts_delta({expr}, 10)), {w})"       # accel -> momentum
    if role == "SENT":    return f"multiply(rank({expr}), {w})"                      # sentiment level
    if role == "FLOW":    return f"multiply(rank({expr}/ts_mean({expr}, 20)), {w})"  # relative intensity
    return f"multiply(-rank(ts_av_diff({expr}, 5)), {w})"                            # LEVEL -> mean-reversion

def t_ensemble(ds_legs, carrier="none", decay=20, power=2.5):
    """The DOMINANT structure of the WQB book (learned 2026-07-21): a weighted ADDITIVE
    ENSEMBLE of orthogonal ±rank micro-signals -> ts_decay_linear (smooth) -> zscore (normalize)
    -> signed_power (tail-shape). ds_legs = dataset-specific ORTHOGONAL legs (low prod-corr).
    carrier: 'none' (0 OHLCV, best for prod-corr — the DEFAULT), 'light' (2 OHLCV legs), or
    'full' (pv1-only fallback). Khoa 2026-07-21: LIMIT OHLCV to survive PROD_CORRELATION."""
    base = {"full": CARRIER, "light": LIGHT_CARRIER, "min": MIN_CARRIER, "none": []}[carrier]
    legs = [l for l in (base + ds_legs) if not has_banned(l)]   # per-leg ban: one banned leg no longer kills the whole ensemble
    if len(legs) < 3: return []
    inner = f"add({', '.join(legs)}, filter=true)"
    sig = f"zscore(ts_decay_linear({inner}, {decay}))"
    if power and power != 1: sig = f"signed_power({sig}, {power})"
    tag = f"ens{ {'none':'P','min':'M','light':'L','full':'C'}[carrier] }_d{decay}_p{str(power).replace('.','')}"
    return [(tag, sig)]


def gen_strategies(dataset: str, n: int = 90, delay: int = 1, seed: int = 7, knowledge=None):
    """Emit up to n deduped trading-logic strategies for `dataset` using role-matched fields.
    If `knowledge` (from knowledge.py) is given, the skill's learned priors bias generation:
    proven WINNERS are seeded first, known-negative templates are pre-flipped, and dead fields
    are pruned / good fields preferred. Deterministic (coprime-stride selection, no RNG)."""
    try:
        import knowledge as _kb
    except Exception:
        _kb = None
    k = knowledge if knowledge is not None else (_kb.load() if _kb else None)
    good, dead = (_kb.field_prefs(dataset, k) if (_kb and k) else (set(), set()))
    def flipped(tmpl, f):
        if _kb and k and _kb.sign_flip_for(dataset, tmpl, k):
            return f"reverse({f})" if not f.startswith("reverse(") else f[8:-1]
        return f
    roles = load_dataset(dataset, delay)
    flow  = roles["FLOW"]; level = roles["LEVEL"]; change = roles["CHANGE"]; sent = roles["SENT"]
    # intensity source: prefer a FLOW field; else a normalized LEVEL as pseudo-intensity
    def sc(e): return scalar(e[1], e[0])
    def norm_intensity(e):
        s = sc(e); return f"{s}/ts_mean({s}, 20)"      # relative intensity (un-ranked; template ranks)
    def pick_intensity(exclude_id):
        for e in intens:
            if e[0] != exclude_id: return e
        return intens[0] if intens else None
    # rank pools canonical-first: coverage desc, then well-established (ac desc). The best
    # microstructure fields (close, volume) ARE the most-used — mechanic discovery wants them;
    # crowding is a theme/novelty concern handled downstream, not here. Learned priors:
    # prune DEAD fields, bump GOOD fields to the front.
    def rankpool(pool):
        # DEMOTE dead fields (sort last), don't DELETE them (B1 verified): deletion means a dead field
        # is never re-emitted -> never re-observed -> can never earn back a good score -> the pool
        # drains toward empty and the loop silently starves. Keeping them sampleable preserves recovery.
        return sorted(pool, key=lambda e: (e[0] in dead, 0 if e[0] in good else 1, -e[2], -e[3]))
    level = rankpool(level); flow = rankpool(flow); change = rankpool(change); sent = rankpool(sent)

    intens = flow[:6] if flow else level[:4]
    strategies = []  # (tag, formula)
    D = [1, 5, 21]        # include the FAST (1-day) reversal — the strongest pv1 mechanic

    # === ENSEMBLE (the WQB book's dominant structure) — emitted FIRST, highest value.
    # Khoa 2026-07-21: LIMIT OHLCV to cut PROD-CORRELATION -> lead with the OHLCV-free 'none'
    # carrier (pure dataset legs); 'light' (2 OHLCV legs) only as a fallback for thin datasets.
    ws = [0.6, 0.55, 0.5, 0.45, 0.4, 0.4, 0.4]
    ds_legs = []
    for role, pool in (("SENT", sent), ("CHANGE", change), ("LEVEL", level), ("FLOW", flow)):
        for e in pool[:3]:
            if len(ds_legs) >= 7: break
            if e[0] in OHLCV: continue                      # skip raw OHLCV fields as legs
            ds_legs.append(_ds_leg(role, sc(e), ws[len(ds_legs)]))
    if dataset == "pv1":
        # pv1 is entirely OHLCV -> only a full-carrier microstructure ensemble is possible;
        # flag it as high-prod-corr by tag (ensC). Prefer non-pv1 datasets for submittable ensembles.
        for decay, power in ((20, 2.5), (45, 2.5), (20, 1)):
            strategies += t_ensemble([], carrier="full", decay=decay, power=power)
    else:
        # LIGHT carrier (2 OHLCV legs) + orthogonal dataset legs is the prod-corr sweet spot:
        # OHLCV-free purity kills the edge (tested: max sharpe ~0.9, 0 zero-fail), full-OHLCV is
        # prod-correlated. Light dilutes the crowded OHLCV signal with orthogonal legs. PRIMARY.
        for decay, power in ((20, 2.5), (45, 2.5), (20, 1)):
            strategies += t_ensemble(ds_legs, carrier="light", decay=decay, power=power)
        for decay in (20, 45):                                   # pure (lowest corr) as an option
            strategies += t_ensemble(ds_legs, carrier="none", decay=decay, power=2.5)

    # reversal / overreaction / zrev: level field x a DIFFERENT intensity field
    for i, X in enumerate(level[:8]):
        IN = pick_intensity(X[0])
        if IN is None: break
        for d in D:
            strategies += t_reversal(sc(X), norm_intensity(IN), d)
            strategies += t_overreact(sc(X), norm_intensity(IN), d)
        strategies += t_zrev(sc(X), norm_intensity(IN), 21)

    # change-momentum / divergence across distinct level/change fields
    pool = (change + level)
    for i in range(min(6, len(pool) - 1)):
        X, Y = pool[i], pool[i + 1]
        if X[0] == Y[0]: continue
        strategies += t_change_mom(sc(X), sc(Y), 10)
        strategies += t_divergence(sc(X), sc(Y), 10)

    # ratio reversal across level pairs
    for i in range(min(4, len(level) - 1)):
        X, Y = level[i], level[i + 1]
        IN = intens[i % len(intens)] if intens else None
        if X[0] == Y[0] or IN is None: continue
        strategies += t_ratio_rev(sc(X), sc(Y), norm_intensity(IN), 10)

    # sentiment fade/ride
    for i, S in enumerate(sent[:4]):
        IN = intens[i % len(intens)] if intens else None
        if IN is None: break
        strategies += t_sent_fade(sc(S), norm_intensity(IN), 10)

    # dedup formulas; apply learned SIGN FLIPS per template; seed proven WINNERS first.
    out, seen = [], set()
    if _kb and k:
        for w in _kb.seeds_for(dataset, k):
            if has_banned(w["formula"]): continue          # never re-emit a banned-field seed
            kk = "".join(w["formula"].split())
            if kk in seen: continue
            seen.add(kk); out.append((f"{dataset[:6]}_seed", w["formula"]))
    for tag, f in strategies:
        f = flipped(tag, f)
        if has_banned(f): continue                         # drop any formula using a submitted-alpha field
        kk = "".join(f.split())
        if kk in seen: continue
        seen.add(kk); out.append((f"{dataset[:6]}_{tag}", f))
        if len(out) >= n: break
    return out


if __name__ == "__main__":
    import sys
    ds = sys.argv[1] if len(sys.argv) > 1 else "option6"
    for tag, f in gen_strategies(ds, n=20):
        print(f"{tag:16} {f}")
