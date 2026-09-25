"""forge.gen.productions -- the pass-first grammar (docs/evalharness/04_passfirst_design.md §2.2) as data,
and one seeded draw from it. Pure: no file, no network, no clock; one rng state gives one draw.

WHAT IS TICKED (docs/evalharness/00_agreements.md). D20: the generator is free within the typed grammar and
judged by the pre-simulation structural gate, `runner.structurally_ok` = `typed.judge(..., structural=True)`,
which enforces H1 units, H2 kinds, H3 bounded operands and H4 vector / density (design §2.1; the code
enforces H3 although D20's text does not list it, and the design shows the grammar never trips it). D35:
every level below starts from a uniform prior (forge/gen/posterior.py), the §2.3 exclusions are kept, and a
20 % exploration floor, the only route to TIER_U, draws from base weights (forge/gen/propose.py).

TYPED BY CONSTRUCTION, NOT BY REJECTION. The old typed arm (forge/grammar.py) drew freely and let the full
judge refuse. Here every choice is restricted to what the structural gate accepts given what was already
drawn, each restriction read from forge/typed.py:
  H1  a spread or a ratio pairs fields of ONE unit; a denominator is a scale kind (level, count, ratio,
      dispersion: `Judge.infer`, divide branch)
  H2  a CHANGE operator (ts_delta, last_diff_value, ts_av_diff, ts_min_diff, ts_min_max_diff) never
      takes a ratio, score, flag or code (`typed.NON_DIFF`)
  H4  a VECTOR field is read through its first labelled reducer (as grammar.leg does); a sparse field
      sits under ts_backfill or add(., 0, filter=true), the grammar's two density routes
So a refusal by the structural gate is a bug in this file; propose() counts it and never ships the row.

DEPTH. §2.2 caps DEPTH at 6 and §2.3 excludes depth >= 7 (0 passes in 934 rows). Depth here is the nesting
of operator nodes in `typed.parse`'s tree, leaves 0 -- the definition the design's own count used
(scratchpad passfirst/load.py:depth). The four accepted forge POSTs read 6, 5, 5, 5 on it (measured
2026-09-23 on state/forge/submitted.jsonl). A leg that would push its alpha past 6 is redrawn, so the
level mix is the grammar's conditional on depth <= 6, not its unconditional one; that conditioning is the
exclusion itself.

TWO CHOICES THIS FILE MAKES THAT NO TICK NAMES, each stated so it can be corrected:
  * later legs come from domains the earlier legs did not use, as grammar.compose does (design §5.2:
    "draws a category-serving first leg as grammar.compose does"); D39's decidable G6 needs >= 2 legs from
    different domains, so an alpha without it could never be auto-submitted.
  * a multi-field SIG takes its orientation from its FIRST field (FIELD_a): the design says "the field's
    description sign" and a spread has two fields. `sign_field` records which field it was.
"""
from __future__ import annotations

import bisect
import hashlib

from forge import grammar as GR
from forge import typed as T
from forge.factory import DEFAULT_SETTINGS, MAX_OPS, candidate_id, op_count
from forge.signature import signature

#: §2.2, verbatim levels. A level is the unit a posterior is kept on (§3.2).
ALPHA = ("conf2", "conf3", "gate")
SIG = ("single", "spread", "ratio", "spread_ratio")
TS = ("ts_mean", "ts_rank", "ts_backfill", "ts_sum_event", "ts_zscore", "ts_delta", "none")
SCORE = ("group_rank", "rank", "ts_rank")
GROUPS = ("sector", "industry", "subindustry")
W_SHORT = (5, 10, 20)
W_LONG = (126, 252)
W_EVENT = (20, 60, 120)
NEUT = ("STATISTICAL", "INDUSTRY", "SUBINDUSTRY")
DECAY = (4, 8)
TRUNC = (0.08, 0.15)
#: §2.3: "ts_backfill window fixed at 126" (186 of 187 126->252 pairs kept every check result).
BACKFILL_W = 126
#: The productions a posterior is kept on, in a fixed order (every draw walks them in this order, so one
#: seed gives one draw).
PRODUCTIONS = {"ALPHA": ALPHA, "SIG": SIG, "TS": TS, "SCORE": SCORE, "G": GROUPS, "W_SHORT": W_SHORT,
               "W_LONG": W_LONG, "W_EVENT": W_EVENT, "NEUT": NEUT, "DECAY": DECAY, "TRUNC": TRUNC}
#: §2.2 TIER_U := "any other unary time-series operator forge.typed classifies (SMOOTH, DISPERSION,
#: CHANGE), with a window from W_SHORT or W_LONG". Derived, not chosen: (typed.SMOOTH | DISPERSION | CHANGE)
#: minus the TS levels above, kept only where fetched/rc/operators.json (the platform's list for this
#: account, 85 operators, 2026-07-15) defines it as `op(x, d)` with every further argument defaulted.
#: Left out, each by that rule: ts_step (no x), hump and ts_target_tvr_decay (no d), kth_element (k has no
#: default), vec_stddev / vec_range (not time series), ts_returns, ts_kurtosis, ts_moment, ts_min, ts_max
#: and ts_decay_exp_window (not in the platform's list). forge/tests/test_gen_productions.py re-derives this from
#: operators.json when the file is present. operators.json gives `level: None` for ts_entropy,
#: ts_min_max_diff, ts_min_max_cps, ts_min_diff and ts_skewness (ALL for the rest); what None means for
#: access is UNKNOWN. §2.3 says the eleven were "never simulated by this desk; drawn only through the
#: floor"; the journal says otherwise for two (draw-5 gen N6, re-derived 2026-09-24 read-only on the Mac copy
#: of state/layered/runs/forge.jsonl, 36,855 lines, 32,662 distinct alphas, typed.parse and a word-boundary
#: regex agreeing): ts_delay appears in 227 alphas (247 of the 32,820 lines with an alpha, the adjudicator's
#: unit) and ts_decay_linear in 176; the other nine, the five level-None ones among them, in 0.
TIER_U = ("last_diff_value", "ts_av_diff", "ts_decay_linear", "ts_delay", "ts_entropy", "ts_min_diff",
          "ts_min_max_cps", "ts_min_max_diff", "ts_product", "ts_skewness", "ts_std_dev")
#: The TS alternative that stands for TIER_U(SIG) in a floor draw (§2.2: one alternative of TS).
TS_TIER_U = "tier_u"
MAX_DEPTH = 6
#: A leg's depth budget per ALPHA shape, so the whole alpha stays <= MAX_DEPTH: conf2 multiply(L, L);
#: conf3 multiply(multiply(L, L), L); gate if_else(greater(L, 0.5), L, 0).
LEG_DEPTH = {"conf2": (5, 5), "conf3": (4, 4, 5), "gate": (4, 5)}
#: §2.3 exclusions (D35 keeps them; each a zero-pass count, not a prior). The grammar cannot produce any
#: of them; `exclusion_reason` is the tripwire that proves it on every row.
EXCLUDED_OPS = {"signed_power": "§2.3: signed_power as a wrapper, 0 of 300 twins converted",
                "vector_neut": "§2.3: vector_neut, all-binding broken 16/0 over 41 pairs",
                "reverse": "§2.3: a negated leg (0 Sharpe-bar rows in 2,557 negated gate payoffs)"}
EXCLUDED_DECAY = {16: "§2.3: decay 16, 0 passes in 746 rows"}
SCALE_KINDS = {"level", "count", "ratio", "dispersion"}      # typed: a divide's denominator
ARM = "gen"                     # runner.stamp sets meta.arm only where it is absent (setdefault), so this stays
GENERATOR = "forge.gen"
LEG_TRIES = 40                  # redraws of one leg before the whole alpha is redrawn
FIELD_TRIES = 60                # redraws of a field whose domain an earlier leg already used


def effective(v: dict) -> tuple:
    """(kind, unit, token) of a labelled field as the structural gate will type it: a VECTOR field is read
    through its first labelled reducer (grammar.leg's default), with typed's kind-after-reducer rule.
    None when the structural gate refuses that token outright: a VECTOR field whose first reducer is
    vec_stddev / vec_range. typed.Judge.infer reaches both through its DISPERSION branch first (typed.DISPERSION
    holds them), which reads the raw VECTOR argument outside a vec_* role and refuses it -- H4 "VECTOR field
    ... used outside vec_*", measured 2026-09-24 on a synthetic label for rank(r(f)), rank(r(f) - g) and
    rank(r(f) / abs(g)). This used to return ("dispersion", the field's unit), which FieldPool could offer as
    a ratio denominator (draw-5 gen N10: effective() and typed disagreed; latent, 0 such labels per the
    auditors). forge/tests/test_gen_productions.py holds every reducer of typed.VEC to typed's own reading."""
    if v.get("structure") != "VECTOR":
        return v["kind"], v["unit"], v["id"]
    red = (v.get("vec_reducers") or ["vec_avg"])[0]
    if red in T.DISPERSION:
        return None
    kind = (v.get("vec_after") or {}).get(red) or ("count" if red == "vec_count" else v["kind"])
    return kind, ("count" if kind == "count" else v["unit"]), "%s(%s)" % (red, v["id"])


def depth(node) -> int:
    """Nesting of operator nodes in a typed.parse tree (leaves 0), keyword arguments included."""
    if node.op is None:
        return 0
    return 1 + max((depth(c) for c in list(node.args) + list(node.kw.values())), default=0)


def _ops(node, out) -> set:
    if node.op is not None:
        out.add(node.op)
        for c in list(node.args) + list(node.kw.values()):
            _ops(c, out)
    return out


def exclusion_reason(formula: str, settings: dict):
    """The §2.3 exclusion a construction hits, or None. Depth > MAX_DEPTH counts as one (§2.3: depth >= 7)."""
    try:
        tree = T.parse(formula)
    except ValueError as exc:
        return "unparseable: %s" % exc
    for op in sorted(_ops(tree, set()) & set(EXCLUDED_OPS)):
        return EXCLUDED_OPS[op]
    try:
        if int(settings.get("decay")) in EXCLUDED_DECAY:
            return EXCLUDED_DECAY[int(settings.get("decay"))]
    except (TypeError, ValueError):
        return "decay %r is not a level" % (settings.get("decay"),)
    if depth(tree) > MAX_DEPTH:
        return "§2.3: depth %d > %d" % (depth(tree), MAX_DEPTH)
    return None


def structurally_ok(formula: str, settings: dict, labels: dict) -> tuple:
    """(ok, first hard reason) -- the call `runner.plan`'s `structurally_ok` makes, argument for argument
    (forge/tests/test_gen_propose.py runs the runner's own closure on every draw to hold the two together)."""
    v = T.judge(formula, labels, "%s/d%s" % (settings.get("region"), settings.get("delay")), structural=True)
    return v["ok"], (v["hard"][0] if v["hard"] else None)


class FieldPool:
    """The labelled fields one region/delay offers the grammar, with grammar.Pool's roles and base weight.

    Primary fields (FIELD_a of a leg): the fields of `grammar.Pool.directional` whose effective kind after a
    VECTOR reducer is still directional (grammar.leg drops a reduced "count"). For USA/d1 on the Mac label
    file Pool.directional holds 19,596 fields in 187 datasets (design §2.4), and so do the primaries:
    re-counted 2026-09-24, every directional field there keeps a directional kind (draw-5 gen N6 had read the
    19,596 as Pool.directional's, not re-derived). Partners (FIELD_b, FIELD_c) come from `Pool.all` of the
    SAME dataset (§2.2), never a flag or a code. A field `effective` reads as None is neither. The base draw
    weight is `Pool.weight` (C9: 1/sqrt(users+1), x0.7 unless dense, / numbered-family size)."""

    def __init__(self, labels: dict, region: str, delay: int):
        self._pool = GR.Pool(labels, region, delay)
        self.key = self._pool.key
        self.region, self.delay = region, int(delay)
        self.primaries = sorted((v for v in self._pool.directional
                                 if (effective(v) or (None,))[0] in GR.DIRECTIONAL_KINDS), key=lambda v: v["id"])
        self._partners = {}                                   # (dataset, effective unit) -> [(field, is scale)]
        for v in sorted(self._pool.all, key=lambda v: v["id"]):
            e = effective(v)
            if e is None:
                continue
            kind, unit, _ = e
            if v.get("dataset") and kind not in ("flag", "code") and unit not in ("code", "bool"):
                self._partners.setdefault((v["dataset"], unit), []).append((v, kind in SCALE_KINDS))
        self.datasets = sorted({v["dataset"] for v in self.primaries if v.get("dataset")})
        self._cum = {}

    def base(self, v: dict) -> float:
        return self._pool.weight(v)

    def _table(self, category, theta):
        """(fields, cumulative weights) for one category (None: every primary) under one dataset multiplier
        map (None: the base weights). Cached per call site's theta object, i.e. once per round and mode."""
        key = (category, id(theta))
        if key not in self._cum:
            items = [v for v in self.primaries if category is None or v.get("category") == category]
            cum, total = [], 0.0
            for v in items:
                total += self.base(v) * (1.0 if theta is None else theta.get(v.get("dataset"), 1.0))
                cum.append(total)
            self._cum[key] = (items, cum, theta)          # theta kept alive so id() is not reused
        return self._cum[key]

    def serves(self, category) -> bool:
        """Whether any primary field fills `category` (the first leg must; design §5.2)."""
        return bool(self._table(category, None)[0])

    def pick(self, rng, category, theta, used_domains):
        """One primary field, weight base x theta_d, from `category` (None: any), avoiding used domains by
        redrawing (an exact conditional draw). None when nothing can be drawn."""
        items, cum, _ = self._table(category, theta)
        if not items or cum[-1] <= 0:
            return None
        for _ in range(FIELD_TRIES):
            v = items[min(bisect.bisect_right(cum, rng.random() * cum[-1]), len(items) - 1)]
            if v.get("domain") not in used_domains:
                return v
        return None

    def partner(self, rng, a, exclude, scale_only):
        """A field of a's dataset with a's effective unit (H1); a scale kind when it divides (H1)."""
        opts = [v for v, is_scale in self._partners.get((a.get("dataset"), effective(a)[1]), ())
                if v["id"] not in exclude and (is_scale or not scale_only)]
        if not opts:
            return None
        return rng.choices(opts, weights=[self.base(v) for v in opts], k=1)[0]


def choose(rng, weights: dict, allowed=None):
    """One level from {level: weight} (insertion order is the level order), restricted to `allowed`."""
    levels = [k for k in weights if allowed is None or k in allowed]
    ws = [max(0.0, float(weights[k])) for k in levels]
    if not levels or sum(ws) <= 0:
        return None
    return rng.choices(levels, weights=ws, k=1)[0]


def _ts_allowed(level, kind, sparse) -> bool:
    if sparse:                                   # H4: only the two density routes
        return level in ("ts_backfill", "ts_sum_event")
    if level == "ts_delta":                      # H2
        return kind not in T.NON_DIFF
    if level == TS_TIER_U:
        return bool(_tier_u_ops(kind))
    return True


def _tier_u_ops(kind) -> list:
    return [op for op in TIER_U if not (op in T.CHANGE and kind in T.NON_DIFF)]


def _window(rng, W, prod):
    return prod, choose(rng, W[prod])


def draw_leg(rng, pool: FieldPool, W: dict, theta, category, used_domains, budget):
    """One LEG (§2.2) or None. `W` = {production: {level: weight}} for this draw's mode; `theta` = dataset
    multipliers (None in a floor draw); `budget` = the leg's depth budget (LEG_DEPTH)."""
    shape = choose(rng, W["SIG"])
    a = pool.pick(rng, category, theta, used_domains)
    if a is None or shape is None:
        return None
    fields = [a]
    if shape in ("spread", "spread_ratio"):
        b = pool.partner(rng, a, {a["id"]}, scale_only=False)
        if b is None:
            return None
        fields.append(b)
    if shape in ("ratio", "spread_ratio"):
        c = pool.partner(rng, a, {f["id"] for f in fields}, scale_only=True)
        if c is None:
            return None
        fields.append(c)
    toks = [effective(f)[2] for f in fields]
    sig = {"single": "%s", "spread": "%s - %s", "ratio": "%s / %s",
           "spread_ratio": "(%s - %s) / abs(%s)"}[shape] % tuple(toks)
    kind = "ratio" if shape in ("ratio", "spread_ratio") else effective(a)[0]
    sparse = any(f.get("sparsity") == "sparse" for f in fields)
    ts = choose(rng, W["TS"], {lv for lv in W["TS"] if _ts_allowed(lv, kind, sparse)})
    if ts is None:
        return None
    windows, tier_u = [], None
    if ts == "ts_mean" or ts == "ts_delta":
        windows.append(_window(rng, W, "W_SHORT"))
        x = "%s(%s, %d)" % (ts, sig, windows[-1][1])
    elif ts in ("ts_rank", "ts_zscore"):
        windows.append(_window(rng, W, "W_LONG"))
        x = "%s(%s, %d)" % (ts, sig, windows[-1][1])
    elif ts == "ts_backfill":
        x = "ts_backfill(%s, %d)" % (sig, BACKFILL_W)
    elif ts == "ts_sum_event":
        windows.append(_window(rng, W, "W_EVENT"))
        x = "ts_sum(add(%s, 0, filter=true), %d)" % (sig, windows[-1][1])
    elif ts == TS_TIER_U:
        tier_u = rng.choice(_tier_u_ops(kind))
        w = rng.choice(W_SHORT + W_LONG)               # "a window from W_SHORT or W_LONG", floor only
        windows.append(("W_SHORT" if w in W_SHORT else "W_LONG", w))
        x = "%s(%s, %d)" % (tier_u, sig, w)
    else:
        x = sig
    score = choose(rng, W["SCORE"])
    group = None
    if score == "group_rank":
        group = choose(rng, W["G"])
        s = "group_rank(%s, %s)" % (x, group)
    elif score == "rank":
        s = "rank(%s)" % x
    else:
        windows.append(_window(rng, W, "W_LONG"))
        s = "ts_rank(%s, %d)" % (x, windows[-1][1])
    if a.get("sign_source") == "description" and a.get("sign") in ("+", "-"):
        orientation, source = a["sign"], "description"
    else:                                               # §2.2: "else a fair coin" (SPECULATION, recorded)
        orientation, source = ("+" if rng.random() < 0.5 else "-"), "coin"
    formula = s if orientation == "+" else "(1 - %s)" % s
    if depth(T.parse(formula)) > budget:
        return None
    return {"formula": formula, "field": a["id"], "fields": [f["id"] for f in fields], "dataset": a.get("dataset"),
            "domain": a.get("domain"), "sig": shape, "ts": ts, "tier_u": tier_u, "windows": [list(w) for w in windows],
            "score": score, "group": group, "orientation": orientation, "sign_source": source, "sign_field": a["id"]}


def draw(rng, pool: FieldPool, W: dict, theta, category):
    """One ALPHA (§2.2) whose first leg serves `category` (design §5.2) -- {"formula", "alpha", "legs"} --
    or None when this pool cannot serve the category or every retry failed."""
    shape = choose(rng, W["ALPHA"])
    if shape is None:
        return None
    legs = []
    for i, budget in enumerate(LEG_DEPTH[shape]):
        leg = None
        for _ in range(LEG_TRIES):
            leg = draw_leg(rng, pool, W, theta, category if i == 0 else None, {L["domain"] for L in legs}, budget)
            if leg is not None:
                break
        if leg is None:
            return None
        legs.append(leg)
    f = [L["formula"] for L in legs]
    if shape == "conf2":
        formula = "multiply(%s, %s)" % (f[0], f[1])
    elif shape == "conf3":
        formula = "multiply(multiply(%s, %s), %s)" % (f[0], f[1], f[2])
    else:
        formula = "if_else(greater(%s, 0.5), %s, 0)" % (f[0], f[1])
    if op_count(formula) > MAX_OPS:
        return None
    return {"formula": formula, "alpha": shape, "legs": [{k: v for k, v in L.items() if k != "formula"} for L in legs]}


def draw_settings(rng, W: dict, region: str, universe: str, delay: int) -> dict:
    """§2.2 SETTINGS: neutralization, decay, truncation from their levels; region/universe/delay = the cell."""
    return dict(DEFAULT_SETTINGS, region=region, universe=universe, delay=int(delay),
                neutralization=choose(rng, W["NEUT"]), decay=int(choose(rng, W["DECAY"])),
                truncation=float(choose(rng, W["TRUNC"])))


def formula_sha(formula: str) -> str:
    """sha256 of the formula text as written (the shared meaning.jsonl interface, D39)."""
    return hashlib.sha256((formula or "").encode()).hexdigest()


#: The meta keys a row-derived candidate (a D37 repair or a D51 neighbour) takes from its base row; every
#: other key (pipeline_version, run_config, seed, cand, signature, mechanism_key, forge) belongs to the run
#: that made the base row, and runner._construction / runner.stamp write this run's.
CARRIED_META = ("hypothesis", "composite", "arm", "generator", "gen_alpha", "combiner", "legs", "families",
                "category", "region", "delay", "field", "field2", "dataset", "field_type", "sign")


def candidate(core: dict, settings: dict, category: str, family: str, route: str, gen_state: str,
              field_datasets=None, draw_mode=None) -> dict:
    """The §4.1 candidate contract: id, formula, settings, meta (hypothesis = gen:<family>, the key
    harvest.pool_key's DSR pool (D38), C16 and mechanism_key read; category; field; legs with orientation and
    sign_source; arm; generator; gen_state; gen_route; composite = 1) and a signature built with the
    catalogue's field_datasets. `route` is meta.gen_route ("fresh" for a grammar draw, propose.ROUTES);
    `draw_mode`, when given, is meta.gen_draw ("posterior" or "floor": which weights drew it).

    THE QUARANTINE IS NOT KEYED HERE (round 4 m22, correcting this docstring and design §3.3's copy of it).
    Families are singletons on the real labels (draw-5 gen G3), so a hypothesis-keyed quarantine sees a new
    key on almost every draw: pf_e5 (round 4, the auditor's run, not re-derived here) gave 4 FAIL rows of one
    field under 4 singleton families 0 dead keys, where one hypothesis gave 1. D36 ticked the quarantine keyed
    (cell, field); design 04 §4.1 places it in the runner's `fill_gen` (stage 4), and nothing in forge/gen
    writes or reads a (cell, field) key."""
    legs = core["legs"]
    hyp = "gen:" + family
    meta = {"hypothesis": hyp, "composite": 1, "arm": ARM, "generator": GENERATOR, "gen_state": gen_state,
            "gen_route": route, "gen_alpha": core["alpha"], "combiner": "gate" if core["alpha"] == "gate" else "multiply",
            "legs": legs, "families": [L["domain"] for L in legs], "category": category,
            "region": settings["region"], "delay": int(settings["delay"]), "field": legs[0]["field"],
            "field2": legs[1]["field"], "dataset": "+".join(sorted({L["dataset"] for L in legs if L.get("dataset")})),
            "field_type": "GEN", "sign": 1}
    if draw_mode is not None:
        meta["gen_draw"] = draw_mode
    return {"id": candidate_id(core["formula"], settings), "formula": core["formula"], "settings": settings, "meta": meta,
            "signature": signature(core["formula"], settings["region"], settings["delay"], mechanism=hyp,
                                   field_datasets=field_datasets)}


def from_row(row: dict, settings: dict, route: str, gen_state: str, field_datasets=None, **link) -> dict:
    """A candidate that re-simulates a journal row's formula under other settings (D37 repair, D51
    neighbour): the row's generator meta, this round's gen_state and route, and the link to the row."""
    m = row.get("meta") or {}
    meta = {k: m[k] for k in CARRIED_META if k in m}
    meta.update(gen_state=gen_state, gen_route=route, arm=ARM, generator=GENERATOR, **link)
    formula = row["formula"]
    return {"id": candidate_id(formula, settings), "formula": formula, "settings": settings, "meta": meta,
            "signature": signature(formula, settings.get("region"), settings.get("delay"), mechanism=meta.get("hypothesis"),
                                   field_datasets=field_datasets)}
