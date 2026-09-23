#!/usr/bin/env python3
"""alpha_score.py — v2.0.0 — production ML composite SCORER for USA-d1 alpha quality (Khoa 2026-07-18).

Built from a 7-expert ML-lifecycle panel + lead synthesis (full workflow, nothing skipped). Scores each simmed
alpha by a single DESIGNED, monotone-by-construction composite in [0,100] over the gate metrics, to drive a
monotonic ceiling-climb. It is NOT a supervised regressor — the panel proved on the real data that the only
available label (gates_passed) is degenerate (81% in {3,4}, max 6/8, 0 full-battery passes), circular (Spearman
dominated by sub_universe +0.70, itself a counted gate), and anti-aligned with Khoa's turnover-hardest mandate.

Khoa HARD CONSTRAINTS (guaranteed BY CONSTRUCTION + runtime asserts, never by a learner):
  - weights of {fitness, returns, turnover} STRICTLY LARGER than every other metric;
  - turnover PENALIZED HARDEST (weight 5.0) + CONVEX (^2) + monotone-down above the LOW_TURNOVER 0.01 no-trade floor;
  - fitness & returns REWARDED MOST (4.0); score ∈ [0,100].

Fatal v1 bug this fixes (panel-verified): v1 ranked a NULL all-zero alpha above 84% of real alphas (turnover-lower-is-
better with NO floor gave a no-trade alpha the max weight-5 reward). v2 adds a turnover FLOOR band + a ceiling-validity
gate: dead/implausible alphas are still SCORED (within-round rank resolution) but can NEVER raise the monotonic ceiling.

Stages: 0 snapshot/repro · 1 clean funnel · 2 feature extract · 3 leak-safe CDF norm · 4 composite+asserts ·
5 OTHER weights (desk prior) · 6 degeneracy/ceiling gate · (eval: alpha_score_eval.py) · 8 record_round contract ·
9 versioned save/load + model card. See state/funnel/alpha_scorer.CARD.md.
"""
from __future__ import annotations
import hashlib, json, os, pathlib, re, sys
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RESULTS = ROOT / "state/resim_results.jsonl"
SCORER = ROOT / "state/funnel/alpha_scorer.json"
CEILING = ROOT / "state/funnel/ceiling_score.json"
SCHEMA_VERSION = 3
MODEL_VERSION = "2.1.0"                                          # v2.1 = decorrelated OTHER block
SEED = 0

# ---- Stage 4/5: metrics, orientation, weights (Khoa constraints) ----
PRIORITY = ("fitness", "returns", "turnover")
# `sharpe` DROPPED from the scored feature set (v2.1): it is 0.98-correlated with fitness (fitness =
# sharpe·√(|ret|/max(tvr,0.125)) already contains it) — its residual is 97.6% noise, so scoring it double-REWARDS
# profitability. It is STILL gated by LOW_SHARPE and by ceiling_eligible's -0.5<=sharpe<=1.7 band (we stop double-
# rewarding, not gating). `robust` DROPPED earlier (0.1% coverage).
OTHER = ("sharpe_2y", "sub_universe", "drawdown")
FEATURES = list(PRIORITY) + list(OTHER)
# Decorrelation: {sharpe_2y, sub_universe} are residualized against the PRIORITY profitability anchor so they
# contribute only info fitness/returns don't already capture (cross-redundancy 0.64 -> 0.12; satellite-profitability
# corr sharpe_2y 0.68->0.07, sub_universe 0.75->0.14). drawdown kept raw (genuinely independent).
RESID_ANCHOR = ("fitness", "returns")
RESID_METRICS = ("sharpe_2y", "sub_universe")
RESID_WINSOR = (1, 99)
DECORR_MAX_CORR = 0.35
HIGHER_BETTER = {"fitness": True, "returns": True, "turnover": False, "sharpe": True,
                 "sharpe_2y": True, "sub_universe": True, "drawdown": False}
PRIORITY_W = {"turnover": 5.0, "fitness": 4.0, "returns": 4.0}  # turnover hardest; fitness/returns rewarded most
OTHER_BUDGET = 3.0                                              # split over 4 others -> each ~0.75 < 4 (constraint)
TURNOVER_CONVEX = 2.0
LOW_TURNOVER_FLOOR = 0.01                                       # a no-trade alpha (tvr<0.01) fails LOW_TURNOVER
# Fitness = Sharpe*sqrt(|Returns|/Max(Turnover,0.125)) -> the denominator is FLOORED at 0.125, so turnover BELOW 0.125
# gives NO extra fitness leverage (Khoa 2026-07-18). Turnover reward is therefore FLAT on [floor, 0.125] (not lower-is-
# better), then CONVEX-DECREASING to 0 at the HIGH_TURNOVER gate.
TURNOVER_FLAT = 0.125                                           # fitness denominator floor: no reward for tvr < this
HIGH_TURNOVER_GATE = 0.70                                       # turnover reward hits 0 here (HIGH_TURNOVER fail)
WINSOR = (1, 99)
N_KNOTS = 1001
# Gate set: ONE definition, tools/funnel/gates.py. This literal was copied here and in
# four other files; the copies disagreed (this one had a tuple of 8, ordered differently), so the same journal
# scored to different zero-fail counts depending on which file did the scoring.
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent.parent / "tools" / "funnel"))
from gates import BLOCKING as HARD_GATES
# region tokens that mark a non-USA-d1 config in the old_id
NON_USA_RE = re.compile(r"(CHN|JPN|KOR|HKG|EUR|TWN|ASI|TOP2000U|TOP1600|TOPDIV)")
CHN_PREFIXES = ("live1", "g5b")
DEAD_BATCH_PREFIXES = ("live2",)  # unconfirmed-region null-experiment batch: excluded from CDF fit + ceiling-ineligible


# ================= Stage 1: data cleaning funnel =================
def root_of(old_id):
    """Group key: strip trailing nested sweep indices (live2_s3_016_145 -> live2_s3; clim1_038 -> clim1)."""
    return re.sub(r"(_\d+)+$", "", old_id or "") or (old_id or "?")


_USA_D1_ROOTS = None
def _usa_d1_roots():
    """WHITELIST of roots whose targets confirm EVERY config is exactly (region=USA, universe=TOP1000, delay=1).
    Leak-safe by construction: closes the delay-0/CHN leak (resim rows carry no region/delay of their own, and a
    CHN config's old_id may have no region token, e.g. hx2/hx3/c3_model175 using CHN-only mdl175 fields). A root of
    unknown provenance (not in any targets file) or ANY non-USA-d1-delay-1 config is EXCLUDED."""
    global _USA_D1_ROOTS
    if _USA_D1_ROOTS is None:
        p = ROOT / "state/funnel/usa_d1_roots.json"
        _USA_D1_ROOTS = set(json.load(open(p))) if p.exists() else set()
    return _USA_D1_ROOTS


def is_usa_d1(row):
    """USA delay=1 TOP1000 membership — WHITELIST-based (leak-safe): root must be targets-confirmed all-USA-d1-delay-1,
    not region-tagged, and sharpe<=2.0 (belt-and-suspenders vs another-cell)."""
    oid = row.get("old_id") or ""
    if NON_USA_RE.search(oid):
        return False
    if root_of(oid) not in _usa_d1_roots():
        return False
    sh = row.get("sharpe")
    return sh is not None and sh <= 2.0


def is_cdf_fit_eligible(row):
    """Rows used to FIT the empirical-CDF (the modeling distribution): USA-d1, real metrics, not a dead batch."""
    if not is_usa_d1(row):
        return False
    if (row.get("old_id") or "").startswith(DEAD_BATCH_PREFIXES):
        return False
    if row.get("fitness") is None or row.get("turnover") is None:
        return False
    return (row.get("turnover") or 0) >= LOW_TURNOVER_FLOOR   # exclude no-trade rows from the fit distribution


# ================= Stage 2: feature extraction =================
def extract(row):
    ch = {}
    for c in row.get("checks", []) or []:
        if isinstance(c, dict) and "name" in c:
            ch[c["name"]] = c

    def cv(name):
        v = ch.get(name, {}).get("value")
        return v if isinstance(v, (int, float)) else None
    return {"fitness": row.get("fitness"), "returns": row.get("returns"), "turnover": row.get("turnover"),
            "sharpe": row.get("sharpe"), "drawdown": row.get("drawdown"),
            "sharpe_2y": cv("LOW_2Y_SHARPE"), "sub_universe": cv("LOW_SUB_UNIVERSE_SHARPE")}


def gates_passed(row):
    ch = {c["name"]: c.get("result") for c in row.get("checks", []) if isinstance(c, dict) and "name" in c}
    return sum(1 for g in HARD_GATES if ch.get(g) == "PASS")


# ================= Stages 3-6: the scorer =================
class AlphaScorer:
    def __init__(self, knots=None, weights=None, scale=100.0, meta=None, resid=None):
        self.knots = knots or {}          # {metric: 1001-knot sorted array} (leak-safe, TRAIN-root CDF)
        self.weights = weights or {}
        self.scale = scale
        self.meta = meta or {}
        self.resid = resid or {}          # {metric: {coef:[b0,b_fit,b_ret], lo, span}} — TRAIN-fit residual models

    # ---- Stage 3: leak-safe percentile norm (winsorized empirical CDF) + turnover floor/convex ----
    def _norm(self, metric, x):
        if x is None:
            return 0.5
        q = self.knots.get(metric)
        if not q:
            return 0.5
        if metric == "turnover":
            return self._turnover_norm(x)
        p = float(np.searchsorted(q, x, side="right")) / len(q)     # percentile ∈ [0,1]
        return p if HIGHER_BETTER[metric] else (1.0 - p)

    @staticmethod
    def _turnover_norm(x):
        """Aligned to the fitness formula (Max(Turnover,0.125)): flat max reward on [0.01,0.125] (no leverage below
        0.125), convex-decreasing to 0 at the HIGH_TURNOVER gate 0.70, and 0 below the no-trade floor 0.01."""
        if x < LOW_TURNOVER_FLOOR:
            return 0.0                                               # no-trade dead alpha
        if x <= TURNOVER_FLAT:
            return 1.0                                               # flat: turnover below 0.125 gives no extra benefit
        if x >= HIGH_TURNOVER_GATE:
            return 0.0
        frac = (x - TURNOVER_FLAT) / (HIGH_TURNOVER_GATE - TURNOVER_FLAT)   # 0..1 across (0.125, 0.70]
        return (1.0 - frac) ** TURNOVER_CONVEX                        # convex decreasing

    def _resid_norm(self, metric, m):
        """The metric's percentile MINUS its profitability-anchor prediction (fitted on TRAIN), winsor-linear renormed
        to [0,1]. Monotone in the metric (slope 1/span, clip only flattens) and, by the fit-time feedback assert,
        monotone-safe for the anchor metrics too."""
        rm = self.resid[metric]
        base = self._norm(metric, m.get(metric))
        anchor = (rm["coef"][0] + rm["coef"][1] * self._norm("fitness", m.get("fitness"))
                  + rm["coef"][2] * self._norm("returns", m.get("returns")))
        return float(np.clip((base - anchor - rm["lo"]) / rm["span"], 0.0, 1.0))

    def score(self, row):
        m = extract(row)
        num = 0.0
        for k in self.weights:
            term = self._resid_norm(k, m) if (k in RESID_METRICS and k in self.resid) else self._norm(k, m.get(k))
            num += self.weights[k] * term
        den = sum(self.weights.values())
        return round(self.scale * num / den, 3)

    # ---- Stage 6: ceiling-validity gate (dead/implausible alphas can be scored but NEVER raise the ceiling) ----
    @staticmethod
    def ceiling_eligible(row):
        if not is_usa_d1(row):
            return False
        if (row.get("old_id") or "").startswith(DEAD_BATCH_PREFIXES):
            return False
        m = extract(row)
        if any(m.get(k) is None for k in ("fitness", "returns", "turnover", "sharpe")):
            return False
        tv, ret, sh, dd = m["turnover"], m["returns"], m["sharpe"], (m.get("drawdown") or 0)
        return (LOW_TURNOVER_FLOOR <= tv <= 0.70) and (ret >= 0.01) and (-0.5 <= sh <= 1.7) and (dd <= 0.60)

    # ---- Stages 0-5: fit ----
    @classmethod
    def fit(cls, rows, seed=SEED, report=False, data_snapshot=None):
        from sklearn.model_selection import GroupShuffleSplit
        rng = np.random.default_rng(seed)
        clean = [r for r in rows if is_cdf_fit_eligible(r)]
        groups = np.array([root_of(r.get("old_id")) for r in clean])
        # leak-safe: fit CDF knots on TRAIN roots only (held-out test roots never touch the normalizer)
        gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
        tr_idx, te_idx = next(gss.split(clean, groups=groups))
        assert not (set(groups[tr_idx]) & set(groups[te_idx])), "train/test roots must be disjoint (no leakage)"
        train = [clean[i] for i in tr_idx]
        allm = [extract(r) for r in train]
        # priority-metric coverage must be 100% on train (hard-fail otherwise)
        for k in PRIORITY:
            cov = sum(1 for mm in allm if isinstance(mm.get(k), (int, float))) / max(1, len(allm))
            assert cov >= 0.999, f"priority metric {k} coverage {cov:.3f} < 1.0 — cannot fit"
        knots, coverage = {}, {}
        for k in FEATURES:
            vals = np.array([v for v in (mm.get(k) for mm in allm) if isinstance(v, (int, float))], float)
            coverage[k] = round(len(vals) / max(1, len(allm)), 3)
            if len(vals):
                lo, hi = np.percentile(vals, WINSOR)
                vals = np.clip(vals, lo, hi)
                knots[k] = np.quantile(np.sort(vals), np.linspace(0, 1, N_KNOTS)).tolist()  # 1001-knot compaction
        # Stage 5: OTHER weights = desk prior (equal split of the budget). Constraint-safe by construction.
        ow = OTHER_BUDGET / len(OTHER)
        w = dict(PRIORITY_W)
        for k in OTHER:
            w[k] = float(min(ow, min(PRIORITY_W.values()) - 1e-6))
        # Khoa asserts
        assert min(w[p] for p in PRIORITY) > max(w[o] for o in OTHER), "priority weights must exceed others"
        assert w["turnover"] >= w["fitness"] and w["turnover"] >= w["returns"], "turnover must be penalized hardest"
        meta = {"schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION, "seed": seed,
                "n_clean": len(clean), "n_train": len(train), "n_test": len(te_idx),
                "n_roots": len(set(groups)), "coverage": coverage, "weights": w,
                "data_snapshot": data_snapshot or {},
                "env": {"numpy": np.__version__}}
        try:
            import sklearn, scipy
            meta["env"].update({"sklearn": sklearn.__version__, "scipy": scipy.__version__})
        except Exception:
            pass
        obj = cls(knots=knots, weights=w, meta=meta)
        # ---- decorrelation: residualize the OTHER satellites against the PRIORITY profitability anchor (TRAIN only) ----
        colf = lambda k: np.array([obj._norm(k, mm.get(k)) for mm in allm])
        Xr = np.column_stack([np.ones(len(allm)), colf("fitness"), colf("returns")])
        resid = {}
        for k in RESID_METRICS:
            coef = np.linalg.lstsq(Xr, colf(k), rcond=None)[0]      # [b0, b_fit, b_ret]
            r = colf(k) - Xr @ coef
            plo, phi = np.percentile(r, RESID_WINSOR)
            span = phi - plo
            if span < 1e-6:                                        # satellite ~perfectly explained -> no independent
                resid[k] = {"coef": [0.5, 0.0, 0.0], "lo": 0.0, "span": 1.0}   # info: neutral term, zero feedback
            else:
                resid[k] = {"coef": [float(x) for x in coef], "lo": float(plo), "span": float(span)}
        obj.resid = resid
        # ANALYTIC MONOTONICITY GUARANTEE (hard Khoa-#4 assert): the residual terms' feedback on each anchor metric
        # must not exceed that metric's own weight, else the score could be non-monotone in fitness/returns.
        for ai, a in enumerate(RESID_ANCHOR, start=1):
            fb = sum(w[k] * abs(resid[k]["coef"][ai]) / resid[k]["span"] for k in RESID_METRICS)
            assert w[a] >= fb, f"residual feedback on {a} ({fb:.3f}) exceeds weight {w[a]} — monotonicity not guaranteed"
        meta["decorr"] = {"resid_feedback": {a: round(sum(w[k] * abs(resid[k]["coef"][ai]) / resid[k]["span"]
                          for k in RESID_METRICS), 3) for ai, a in enumerate(RESID_ANCHOR, start=1)}}
        if report:
            print(f"  fit: {len(clean)} clean USA-d1 rows | train {len(train)}/{len(te_idx)} test | {meta['n_roots']} roots")
            print(f"  coverage: {coverage} | resid feedback: {meta['decorr']['resid_feedback']}")
        return obj

    # ---- Stage 9: versioned atomic save / schema-checked load ----
    def save(self, path=SCORER):
        d = {"schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
             "knots": self.knots, "weights": self.weights, "scale": self.scale, "meta": self.meta,
             "resid": self.resid}
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = str(path) + ".tmp"
        json.dump(d, open(tmp, "w"))
        os.replace(tmp, path)
        # immutable per-version copy
        vdir = ROOT / "state/funnel/scorers"
        vdir.mkdir(parents=True, exist_ok=True)
        json.dump(d, open(vdir / f"alpha_scorer_v{MODEL_VERSION}.json", "w"))

    @classmethod
    def load(cls, path=SCORER):
        d = json.load(open(path))
        if d.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"scorer schema {d.get('schema_version')} != expected {SCHEMA_VERSION} — refit")
        return cls(knots=d["knots"], weights=d["weights"], scale=d.get("scale", 100.0), meta=d.get("meta"), resid=d.get("resid"))


def data_snapshot(path=RESULTS):
    raw = open(path, "rb").read()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "row_count": raw.count(b"\n"), "path": str(path)}


# ================= Stage 8: monotonic-ceiling contract =================
def record_round(round_label, rows, scorer=None):
    """Single ceiling entrypoint: filter USA-d1 + ceiling_eligible, take best eligible score, update ceiling ONLY
    upward (monotonic, asserted), atomic append-only ledger, climb-health counter. Returns (ceiling, best_id, accepted)."""
    scorer = scorer or AlphaScorer.load()
    eligible = [r for r in rows if AlphaScorer.ceiling_eligible(r)]
    scored = [(scorer.score(r), r.get("old_id") or r.get("alpha")) for r in eligible]
    st = json.load(open(CEILING)) if CEILING.exists() else {"ceiling": -1e9, "rounds": [], "rounds_since_improvement": 0}
    if scored:
        best_score, best_id = max(scored)
    else:
        best_score, best_id = None, None
    accepted = best_score is not None and best_score > st["ceiling"]
    if accepted:
        st["ceiling"], st["ceiling_id"] = best_score, best_id
        st["rounds_since_improvement"] = 0
    else:
        st["rounds_since_improvement"] = st.get("rounds_since_improvement", 0) + 1
    st["rounds"].append({"round": round_label, "n_eligible": len(eligible), "batch_best": best_score,
                         "batch_best_id": best_id, "ceiling_after": st["ceiling"], "accepted": accepted,
                         "scorer_version": MODEL_VERSION})
    ceils = [r["ceiling_after"] for r in st["rounds"]]
    assert all(ceils[i] <= ceils[i + 1] for i in range(len(ceils) - 1)), "ceiling must be monotonic non-decreasing"
    tmp = str(CEILING) + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, CEILING)
    # auto-refresh the full climb measurement (all metrics + velocities) after every round (Khoa 2026-07-18)
    try:
        import climb_metrics
        climb_metrics.run()
    except Exception:
        pass
    return st["ceiling"], best_id, accepted


# ================= self-test =================
def _self_test():
    import random
    random.seed(0)
    global _USA_D1_ROOTS
    _saved_wl = _USA_D1_ROOTS
    _USA_D1_ROOTS = {f"r{j}" for j in range(10)}   # inject synthetic roots into the whitelist for the test
    rows = []
    for i in range(300):
        root = f"r{i // 30}"                      # 10 roots × 30 configs (group structure)
        nz = lambda a: random.uniform(-a, a)      # noise so satellites aren't perfectly collinear (real data isn't)
        rows.append({"old_id": f"{root}_{i%30:03d}", "sharpe": 0.3 + 0.004 * i + nz(0.1),
                     "fitness": 0.2 + 0.003 * i, "returns": 0.01 + 0.0003 * i,
                     "turnover": 0.5 - 0.001 * i, "drawdown": 0.15 + nz(0.05),
                     "checks": [{"name": "LOW_2Y_SHARPE", "value": 0.5 + 0.003 * i + nz(0.3), "result": "PASS" if i > 150 else "FAIL"},
                                {"name": "LOW_SUB_UNIVERSE_SHARPE", "value": 0.4 + nz(0.25), "result": "PASS"}]})
    sc = AlphaScorer.fit(rows, report=False)
    # (1) Khoa constraints
    assert min(sc.weights[p] for p in PRIORITY) > max(sc.weights[o] for o in OTHER)
    assert sc.weights["turnover"] >= sc.weights["fitness"] >= sc.weights["returns"] - 1e-9
    # (2) DEGENERACY: null all-zero must NOT beat the real median and must be ceiling-ineligible (the v1 bug)
    null = {"old_id": "null_000", "sharpe": 0, "fitness": 0, "returns": 0, "turnover": 0, "drawdown": 0, "checks": []}
    real_scores = sorted(sc.score(r) for r in rows)
    med = real_scores[len(real_scores) // 2]
    assert sc.score(null) < med, (sc.score(null), med)
    assert not AlphaScorer.ceiling_eligible(null), "null alpha must be ceiling-ineligible"
    # (3) turnover monotone-down above the floor
    def tv_score(tv):
        return sc.score({"turnover": tv, "fitness": 0.5, "returns": 0.05, "sharpe": 1.0, "drawdown": 0.1,
                         "checks": [{"name": "LOW_2Y_SHARPE", "value": 1.0}]})
    seq = [tv_score(t) for t in [0.02, 0.1, 0.3, 0.6]]
    assert all(seq[i] >= seq[i + 1] - 1e-9 for i in range(len(seq) - 1)), seq
    # (4) fitness/returns monotone-up
    def fit_score(f):
        return sc.score({"turnover": 0.1, "fitness": f, "returns": 0.05, "sharpe": 1.0, "drawdown": 0.1, "checks": []})
    assert fit_score(0.2) < fit_score(0.9)
    _USA_D1_ROOTS = _saved_wl                       # restore the real whitelist (no test/serve global bleed)
    print(f"alpha_score v{MODEL_VERSION} self-test PASS | w={ {k: round(v,2) for k,v in sc.weights.items()} } | "
          f"null={sc.score(null)} (<med {med}) | turnover-monotone-down ✓")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["fit", "score", "self-test", "snapshot"])
    ap.add_argument("--results", default=str(RESULTS))
    a = ap.parse_args(argv)
    if a.cmd == "self-test":
        _self_test(); return 0
    if a.cmd == "snapshot":
        print(json.dumps(data_snapshot(a.results), indent=1)); return 0
    rows = [json.loads(l) for l in open(a.results) if l.strip()]
    rows = [r for r in rows if isinstance(r, dict)]
    if a.cmd == "fit":
        sc = AlphaScorer.fit(rows, report=True, data_snapshot=data_snapshot(a.results)); sc.save()
        print(f"weights: { {k: round(v,3) for k,v in sc.weights.items()} }")
        print(f"priority>others = {min(sc.weights[p] for p in PRIORITY) > max(sc.weights[o] for o in OTHER)} | "
              f"snapshot {sc.meta['data_snapshot']['sha256'][:12]} rows={sc.meta['data_snapshot']['row_count']}")
        return 0
    if a.cmd == "score":
        sc = AlphaScorer.load()
        clean = [r for r in rows if is_usa_d1(r) and r.get("sharpe") is not None]
        scored = sorted(((sc.score(r), r.get("old_id"), AlphaScorer.ceiling_eligible(r)) for r in clean), reverse=True)
        print(f"scored {len(clean)} USA-d1 sims. top-5: {[(s, i, 'elig' if e else 'INELIG') for s,i,e in scored[:5]]}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
