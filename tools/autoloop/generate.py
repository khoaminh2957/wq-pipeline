#!/usr/bin/env python3
"""generate.py — evidence-weighted candidate-alpha generator for the autoloop.

Emits USA/TOP3000 delay-1 FASTEXPR target rows (old_id/id/formula/settings/meta) ready for
tools/validate_targets.py, the sim queue and tools/autoloop/driver.py (which scores `meta`).

Usage:
  python3 tools/autoloop/generate.py --n 3000 --out state/autoloop/pool_main.json --seed 1
  python3 tools/autoloop/generate.py --n 600 --out pool_backup.json --seed 99 \
      --exclude-formulas state/autoloop/pool_main.json
  python3 tools/autoloop/generate.py --n 3000 --out o.json --knowledge state/autoloop/knowledge.json

Rows are allocated across measured-productive buckets (see BUCKETS); dead cells are simply
not generated. TWO documented deviations from the allocation brief:

 1. n_prims=6 (close+open+vwap+volume+returns+adv20) is NOT buildable: volume, returns and
    adv20 are all in state/banned_fields.json (burnt by submitted alpha 0mM8r3L2) and a
    submitted alpha's fields can never be reused. The prims bucket therefore carries the 5
    legal primitives close+open+high+low+vwap (cap excluded: 0.12x lift).
 2. fields_all.jsonl tags each dataset with the ONE universe its crawl ran under, so
    model354/model227/model237/predictive_starmine/multi_horizon_alpha are tagged TOP1000.
    That tag is a crawl artifact, not availability: 408 TOP3000 targets in state/ that use
    mdl354_/mdl227_/mdl237_ fields simulated fine (7 errors). Fields are therefore filtered on
    region/delay/coverage only, per spec — not on the catalogued universe.
"""
from __future__ import annotations
import argparse, glob, json, os, pathlib, random, re, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIELDS_PATH = ROOT / "fetched/fields_all.jsonl"
BANNED_PATH = ROOT / "state/banned_fields.json"

UNIVERSE = "TOP3000"          # measured: USA/TOP1000 is 12/13780 zero-fail -> TOP3000 only
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ---------------------------------------------------------------- banned fields
def load_banned(path=BANNED_PATH) -> set:
    d = json.load(open(path))
    return set(d["banned_fields"] if isinstance(d, dict) else d)


def banned_hits(formula: str, banned) -> list:
    """Banned tokens present in `formula`, matched at IDENTIFIER level.

    A banned name that only appears as a substring of a longer field id
    (e.g. 'volume' inside 'snt_social_volume') is NOT a hit — only whole tokens.
    """
    return sorted({t for t in IDENT.findall(formula) if t in banned})


# ---------------------------------------------------------------- field catalog
# volume / returns / adv20 are BANNED; cap is excluded (measured 0.12x lift).
PV1_CARRIER = ["close", "high", "low", "open", "vwap"]
GROUPS = ["market", "sector", "industry", "subindustry"]

# D4: fields that are IDENTIFIERS, CODES or TIMESTAMPS rather than measurements. A ts_delta of an
# ISO country code or a UTC timestamp is pure noise, so they never become legs. Kept deliberately
# tight — '<x>_country_rank' / 'country_percentile_rank_*' ARE real signals and must survive.
NONSIGNAL_DESC = re.compile(
    r"utc (date|timestamp)|date and time of the earnings call|ingestion timestamp"
    r"|publication timestamp|^(home|pricing|iso) currency|currency code|^country$|country code"
    r"|two-letter iso code|unique (numeric )?identifier|unique security identifier"
    r"|identifier key|internal identifier|stock ticker symbol|ticker and exchange code"
    r"|exchange the stock is traded|derived by cusip|country region of registrant"
    r"|country of company incorporation|registrant location country|mail state country", re.I)
NONSIGNAL_ID = re.compile(
    r"(_utc|_utc_fast_d\d)$|_crncy_iso$|_currency_code(_\w+)?$"
    r"|_cur_fiscal_(qtr|year)_period$|_fkey$|country$")


def is_signal_field(fid, description):
    """False for identifier/code/timestamp fields — they carry no cross-sectional signal."""
    return not (NONSIGNAL_ID.search(fid) or NONSIGNAL_DESC.search(description or ""))


def load_fields(banned, path=FIELDS_PATH):
    """-> {by_ds, ftype, pv1, uncrowded}. USA, delay 1, coverage >= 0.7, not banned."""
    by_ds, ftype, pv1, users = {}, {}, [], {}
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("region") != "USA" or r.get("delay") != 1 or (r.get("coverage") or 0) < 0.7:
            continue
        if r["id"] in banned or r.get("type") not in ("MATRIX", "VECTOR"):
            continue
        if not is_signal_field(r["id"], r.get("description")):
            continue
        ds = (r.get("dataset") or {}).get("id")
        if ds == "pv1":
            if r["id"] in PV1_CARRIER and r["id"] not in pv1:
                pv1.append(r["id"])
        elif ds and r["id"] not in ftype:
            by_ds.setdefault(ds, []).append(r["id"])
            ftype[r["id"]] = r["type"]
            users.setdefault(ds, []).append(r.get("userCount") or 0)
    by_ds = {k: sorted(v) for k, v in sorted(by_ds.items())}
    # "uncrowded model datasets": the model* families nobody is using (median userCount 0)
    uncrowded = [d for d in by_ds if d.startswith("model")
                 and sorted(users[d])[len(users[d]) // 2] == 0]
    owner = {f: d for d, fs in by_ds.items() for f in fs}
    return {"by_ds": by_ds, "ftype": ftype, "pv1": sorted(pv1),
            "uncrowded": uncrowded, "owner": owner}


# ---------------------------------------------------------------- diversity axes
# Leg grammar is copied from the measured 67.85%-zero-fail news18 family:
#   carrier pair -> then one-dataset legs, each rank()-normalized, magnitudes a decaying ladder.
LEG_WINDOWS = [5, 10, 20, 60]              # D2: >=2 everywhere; winner uses 5 and 10
LEG_OPS = ["bare", "ts_delta", "ts_av_diff"]        # exactly the winner's per-leg ops
NORM = "rank"                              # D5: ONE normalizer per formula, and it is rank
# D1: a leg may only enter add() if its outermost op puts it on a comparable scale.
NORMALIZERS = ("rank", "zscore", "ts_zscore", "ts_rank", "group_rank")
SIGNS = [1, -1]                            # D6: direction is free, magnitude is not
LADDER_STEPS = [0, 0, 0.05, 0.05, 0.1, 0.15]        # decay of the magnitude ladder
LADDER_FLOOR = 0.2
# D7: the proven microstructure carrier — intraday reversal, negated. Verbatim, always legs 1-2.
CARRIER_LEGS = ["-rank(divide(close, open))", "multiply(-rank(divide(close, vwap)), 0.6)"]
CARRIER_FIELDS = ["close", "open", "vwap"]
CONDS = ["zs", "tsrank", "delta"]
# surviving settings axes only (SLOW/FAST/NONE/CROWDING neut, trunc>=0.08, decay>=26 and 7-10
# are all measured 0-yield and are never generated)
NEUTS = ["INDUSTRY", "STATISTICAL", "SUBINDUSTRY", "SECTOR", "MARKET"]
DECAYS = [0, 4, 5, 6, 14, 20]
TRUNCS = [0.01, 0.015, 0.02, 0.05]
# free-exploration wrappers (no reverse/hump/winsorize/group_neutralize — all measured 0-yield)
EXPLORE_SKELS = ["zscore", "rank", "ts_rank", "ts_zscore", "ts_decay_linear",
                 "signed_power", "group_rank", "trade_when", "if_else"]

# Repeated entries = weight. Journal stats say decay-window 50 > 32 >> 16 and exponent 3.5 > 3.0,
# but the 67.85% winner sits at 20 / 2.5 — both cells are reachable, weighted toward the stats.
W50 = [50, 50, 32, 32, 20, 20, 16]
P35 = [3.5, 3.5, 3.0, 2.5, 2.5]

# struct: S = signed_power>zscore>ts_decay_linear grammar (needs vec_avg), D = decay-wrapped
# without signed_power, V = vector_neut, X = free explore chain.
BUCKETS = [
    dict(name="decorr", share=0.30, struct="D", ds="uncrowded",
         neut=["STATISTICAL"], decay=[6], trunc=[0.05],
         legs=list(range(4, 12)), win=W50),
    dict(name="grammarS", share=0.25, struct="S", ds=["news18", "predictive_starmine"],
         neut=["INDUSTRY"], decay=[6], trunc=[0.02],
         legs=list(range(6, 13)), win=W50, pw=P35),
    dict(name="ladder", share=0.15, struct="S", ds=["news18", "predictive_starmine"],
         neut=["INDUSTRY"], decay=[6], trunc=[0.015, 0.01],
         legs=list(range(6, 13)), win=W50, pw=P35),
    dict(name="prims", share=0.15, struct="S", ds=None,
         neut=["INDUSTRY"], decay=[6], trunc=[0.05],
         legs=list(range(6, 13)), win=W50, pw=P35),
    dict(name="vecneut", share=0.10, struct="V",
         ds=["multi_horizon_alpha", "predictive_starmine"],
         neut=["INDUSTRY"], decay=[6], trunc=[0.05], legs=list(range(4, 12))),
    dict(name="explore", share=0.05, struct="X", ds=None,
         neut=NEUTS, decay=DECAYS, trunc=TRUNCS,
         legs=list(range(3, 13)), win=W50, pw=P35),
]


class Sampler:
    """Uniform sampling, biased by an optional knowledge file.

    knowledge = {"good": {"<axis>:<value>": weight, ...}, "bad": ["<axis>:<value>" | "<value>"]}
    """

    def __init__(self, rng, knowledge=None):
        k = knowledge or {}
        self.rng = rng
        self.good = k.get("good") or {}
        self.bad = set(k.get("bad") or [])

    def keep(self, axis, v):
        return f"{axis}:{v}" not in self.bad and str(v) not in self.bad

    def pick(self, axis, options):
        opts = [o for o in options if self.keep(axis, o)] or list(options)
        w = [max(0.0, float(self.good.get(f"{axis}:{o}", 1.0))) for o in opts]
        if sum(w) <= 0:
            w = [1.0] * len(opts)
        return self.rng.choices(opts, weights=w)[0]


def num(x):
    return f"{x:g}"


# ---------------------------------------------------------------- formula pieces
def base_of(f, ftype):
    """VECTOR fields only enter an expression through vec_avg."""
    return f"vec_avg({f})" if ftype.get(f) == "VECTOR" else f


def make_core(s, f, ftype):
    """One signed, rank-normalized leg body — no weight yet. Winner's op set only."""
    x = base_of(f, ftype)
    op = s.pick("legop", LEG_OPS)
    core = f"{NORM}({x})" if op == "bare" else \
        f"{NORM}({op}({x}, {s.pick('legwin', LEG_WINDOWS)}))"
    return ("-" if s.pick("sign", SIGNS) < 0 else "") + core


def magnitudes(s, n):
    """D6: monotone non-increasing ladder, starts at 1.0, never exceeds it.
    Legs 1-2 are the carrier pair, whose magnitudes are fixed at 1.0 and 0.6."""
    out, w = [], 1.0
    for i in range(n):
        if i == 1:
            w = 0.6
        elif i > 1:
            w = max(LADDER_FLOOR, round(w - s.pick("step", LADDER_STEPS), 2))
        out.append(w)
    return out


def make_cond(s, field, ftype):
    x = base_of(field, ftype)
    kind = s.pick("cond", CONDS)
    w = s.pick("win", [20, 60, 120, 250])
    if kind == "zs":
        return f"abs(ts_zscore({x}, {w})) > 1"
    if kind == "tsrank":
        return f"ts_rank({x}, {w}) > 0.7"
    return f"ts_delta({x}, {w}) > 0"


def make_risk_expr(s):
    """A slow price/risk exposure for vector_neut to project out. Never the carrier itself."""
    kind = s.pick("riskkind", ["level", "vol", "trend"])
    if kind == "level":
        return "rank(ts_mean(close, 250))"
    if kind == "vol":
        return f"rank(ts_std_dev(close, {s.pick('riskwin', [60, 120])}))"
    return f"rank(ts_delta(close, {s.pick('riskwin', [60, 120])}))"


def pick_dataset(s, b, pools):
    spec = b["ds"]
    if spec is None:
        pool = sorted(pools["by_ds"])
    elif spec == "uncrowded":
        # the three measured-best decorrelation datasets, weighted, plus the other uncrowded ones
        pool = ["model354", "model227", "model237"] * 2 + pools["uncrowded"]
        pool = [d for d in pool if d in pools["by_ds"]]
    else:
        pool = [d for d in spec if d in pools["by_ds"]]
    return s.pick("ds", pool)


def compose(s, b, expr, cond_field, ftype):
    """Wrap the add() ensemble in the bucket's structure. -> (formula, skeleton signature)"""
    st = b["struct"]
    if st == "S":
        return (f"signed_power(zscore(ts_decay_linear({expr}, {s.pick('win', b['win'])})), "
                f"{num(s.pick('pw', b['pw']))})", "signedpower>zscore>tsdecaylinear")
    if st == "D":
        e = f"ts_decay_linear({expr}, {s.pick('win', b['win'])})"
        if s.pick("dz", [0, 1]):
            return f"zscore({e})", "zscore>tsdecaylinear"
        return e, "tsdecaylinear"
    if st == "V":
        return f"vector_neut({expr}, {make_risk_expr(s)})", "vectorneut"
    chain = []                                              # X: free explore chain
    for _ in range(s.pick("layers", [1, 2, 3])):
        k = s.pick("skel", [x for x in EXPLORE_SKELS if x not in chain] or ["zscore"])
        chain.append(k)
        if k == "ts_rank":
            expr = f"ts_rank({expr}, {s.pick('win', [10, 20, 60, 120, 250])})"
        elif k == "ts_zscore":
            expr = f"ts_zscore({expr}, {s.pick('win', [20, 60, 120, 250])})"
        elif k == "ts_decay_linear":
            expr = f"ts_decay_linear({expr}, {s.pick('win', b['win'])})"
        elif k == "signed_power":
            expr = f"signed_power({expr}, {num(s.pick('pw', b['pw']))})"
        elif k == "group_rank":
            expr = f"group_rank({expr}, {s.pick('group', GROUPS)})"
        elif k == "trade_when":
            expr = f"trade_when({make_cond(s, cond_field, ftype)}, {expr}, -1)"
        elif k == "if_else":
            expr = f"if_else({make_cond(s, cond_field, ftype)}, {expr}, multiply({expr}, -1))"
        else:
            expr = f"{k}({expr})"
    # signature reads outermost -> innermost (chain is built innermost-first)
    return expr, ">".join(k.replace("_", "") for k in reversed(chain))


def build_row(s, b, pools):
    """-> (formula, partial meta) for one candidate, or None if it degenerated.

    Structure copied from the measured winner: carrier pair, then one-dataset rank legs on a
    decaying magnitude ladder, all inside a single add(..., filter=true)."""
    ftype = pools["ftype"]
    ds = pick_dataset(s, b, pools)
    fields = pools["by_ds"][ds]
    n_legs = s.pick("legs", b["legs"])

    cores = [make_core(s, s.rng.choice(fields), ftype) for _ in range(n_legs - len(CARRIER_LEGS))]
    cores = list(dict.fromkeys(cores))   # identical legs would be degenerate self-args
    if not cores:
        return None
    mags = magnitudes(s, len(CARRIER_LEGS) + len(cores))
    legs = list(CARRIER_LEGS) + [f"multiply({c}, {num(w)})" for c, w in zip(cores, mags[2:])]

    expr = "add(" + ", ".join(legs) + ", filter=true)"
    formula, skel = compose(s, b, expr, s.rng.choice(fields), ftype)
    return formula, {"skeleton": skel, "dataset": ds, "legs": len(legs)}


def make_settings(s, b):
    return {"instrumentType": "EQUITY", "region": "USA", "universe": UNIVERSE, "delay": 1,
            "decay": s.pick("decay", b["decay"]),
            "neutralization": s.pick("neut", b["neut"]),
            "truncation": s.pick("trunc", b["trunc"]),
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": "OFF", "maxPosition": "OFF", "language": "FASTEXPR",
            "visualization": False, "startDate": "2019-01-01", "endDate": "2023-12-31"}


# ---------------------------------------------------------------- dedup / exclude
def row_key(formula, st):
    return (re.sub(r"\s+", "", formula), st.get("universe"), st.get("neutralization"),
            st.get("decay"), st.get("truncation"))


def history_keys():
    """Every (formula, settings) already staged in state/, i.e. exactly what validate_targets.py
    checks a new batch against. Generating a collision would fail the acceptance test."""
    keys = set()
    for p in glob.glob(str(ROOT / "state/*targets*.json")) + \
            glob.glob(str(ROOT / "state/resim_targets_*.bak")):
        try:
            rows = json.load(open(p))
        except Exception:
            continue
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and r.get("formula") and r.get("settings"):
                    keys.add(row_key(r["formula"], r["settings"]))
    return keys


def load_exclude(path):
    """JSON list of already-run (formula, settings): target rows, or [formula, settings] pairs.
    -> (set of full keys, set of formulas excluded regardless of settings)"""
    keys, formulas = set(), set()
    if not path:
        return keys, formulas
    for r in json.load(open(path)):
        if isinstance(r, dict):
            f, st = r.get("formula"), r.get("settings")
        elif isinstance(r, (list, tuple)) and r:
            f, st = r[0], (r[1] if len(r) > 1 else None)
        else:
            f, st = (r if isinstance(r, str) else None), None
        if not f:
            continue
        if st:
            keys.add(row_key(f, st))
        else:
            formulas.add(re.sub(r"\s+", "", f))
    return keys, formulas


# ---------------------------------------------------------------- main entry
def quotas(n):
    q = {b["name"]: int(n * b["share"]) for b in BUCKETS}
    q[BUCKETS[0]["name"]] += n - sum(q.values())
    return q


def generate(n, seed=0, exclude=None, knowledge=None,
             fields_path=FIELDS_PATH, banned_path=BANNED_PATH):
    """-> list of n unique target rows, allocated across BUCKETS. A bucket that cannot fill its
    quota spills into the others; profile() reports any such shortfall."""
    banned = load_banned(banned_path)
    pools = load_fields(banned, fields_path)
    if not pools["by_ds"]:
        raise RuntimeError(f"no eligible USA d1 fields in {fields_path}")
    if any(f in banned for f in CARRIER_FIELDS):
        raise RuntimeError(f"the proven carrier needs {CARRIER_FIELDS}, but "
                           f"{sorted(set(CARRIER_FIELDS) & banned)} is banned — carrier must be "
                           f"re-derived before generating")
    kn = json.load(open(knowledge)) if knowledge and pathlib.Path(knowledge).exists() else None
    s = Sampler(random.Random(seed), kn)
    ex_keys, ex_formulas = load_exclude(exclude)
    ex_keys |= history_keys()

    quota = quotas(n)
    rows, seen = [], set()

    def fill(b, want):
        got, attempts, cap = 0, 0, 60 * want + 3000
        while got < want and attempts < cap:
            attempts += 1
            built = build_row(s, b, pools)
            if not built:
                continue
            formula, meta = built
            st = make_settings(s, b)
            k = row_key(formula, st)
            if k in seen or k in ex_keys or k[0] in ex_formulas:
                continue
            hits = banned_hits(formula, banned)
            if hits:
                raise RuntimeError(f"banned field(s) leaked into a formula: {hits}")
            seen.add(k)
            meta.update(neutralization=st["neutralization"], decay=st["decay"],
                        universe=st["universe"], truncation=st["truncation"])
            oid = f"ap{seed}_{b['name']}_{len(rows):04d}"
            rows.append({"old_id": oid, "id": oid, "formula": formula,
                         "settings": st, "meta": meta})
            got += 1
        return got

    for b in BUCKETS:
        fill(b, quota[b["name"]])
    # a bucket that could not fill spills into the next-best (table order = descending yield)
    while len(rows) < n:
        added = sum(fill(b, n - len(rows)) for b in BUCKETS if len(rows) < n)
        if not added:
            raise RuntimeError(f"could only build {len(rows)} unique rows out of {n} requested; "
                               f"widen the axes or lower --n")
    return rows


def profile(rows):
    buckets = Counter(r["old_id"].split("_")[1] for r in rows)
    m = lambda k: Counter(r["meta"][k] for r in rows)
    print(f"rows: {len(rows)}")
    print(f"per-bucket: {dict(buckets.most_common())}")
    for name, want in quotas(len(rows)).items():
        if buckets[name] < want:
            print(f"  SHORTFALL {name}: built {buckets[name]} of {want} "
                  f"— remainder refilled from other buckets")
    skel, ds, neut, legs = m("skeleton"), m("dataset"), m("neutralization"), m("legs")
    print(f"distinct skeletons: {len(skel)} -> {dict(skel.most_common())}")
    print(f"distinct datasets: {len(ds)} -> {dict(ds.most_common(20))}")
    print(f"distinct neutralizations: {len(neut)} -> {dict(neut.most_common())}")
    print(f"distinct leg counts: {len(legs)} -> {dict(sorted(legs.items()))}")
    print(f"distinct decays: {dict(sorted(m('decay').items()))}")
    print(f"distinct truncations: {dict(sorted(m('truncation').items()))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exclude-formulas", default=None)
    ap.add_argument("--knowledge", default=None)
    a = ap.parse_args()
    rows = generate(a.n, seed=a.seed, exclude=a.exclude_formulas, knowledge=a.knowledge)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # the driver may be reading this path mid-run: write beside it, then rename atomically so a
    # partial file is never observed.
    tmp = out.with_suffix(out.suffix + ".tmp")
    json.dump(rows, open(tmp, "w"), indent=1)
    os.replace(tmp, out)
    print(f"wrote {len(rows)} rows -> {a.out}")
    profile(rows)


if __name__ == "__main__":
    sys.exit(main())
