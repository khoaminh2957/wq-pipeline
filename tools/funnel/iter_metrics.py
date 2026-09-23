#!/usr/bin/env python3
"""iter_metrics.py — the full measurable panel for one iteration, pre-sim and post-sim, plus the
significance test that decides whether an iteration's gain was real or luck.

Khoa 2026-07-29: every iteration must be strictly better than the last, nothing is finalised
without measuring its output first, and a batch's apparent gain must be checked for luck before
moving on. That requires (a) measuring everything measurable, not just sharpe, and (b) a test that
separates a real shift from sampling noise in a ~180-row batch.

PRE-SIM (no API, computable from the batch file alone):
  n_targets, n_legsets, n_datasets, leg-count distribution, operator/skeleton diversity,
  formula depth, field crowding (userCount / alphaCount medians), field coverage, banned-field
  hits, theme match rate, logic_check severity counts, duplicate rate vs all prior batches.

POST-SIM (from state/resim_results.jsonl + state/prod_corr_measured.json):
  every numeric IS metric (sharpe, fitness, turnover, returns, drawdown, margin, longCount,
  shortCount), every CHECK value and its pass/fail, region-specific gates, zero-fail rate,
  and the two correlation gates (exact prod max, self max).

LUCK TEST:
  Comparing two iterations on a summary statistic is not enough — a 180-row batch has enough
  spread that a better median can arise by chance. `compare()` runs a two-sided permutation test
  (label-shuffling, exact null under exchangeability, no distributional assumption) on the chosen
  metric, and reports effect size plus a bootstrap CI for the difference. An iteration counts as a
  real improvement only if the shift is significant AND the direction holds on the secondary
  metrics, not just the headline one.
"""
from __future__ import annotations
import json, pathlib, re, statistics, random, sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RESULTS = ROOT / "state/resim_results.jsonl"
CORR = ROOT / "state/prod_corr_measured.json"

# gates differ by region — GLB has no IS_LADDER_SHARPE and adds three per-region sharpe floors
# Gate set: ONE definition, gates.py. Previously this file carried its own HARD_USA/HARD_GLB
# literals while four other modules carried different ones, and scoring the same journal with them
# produced different zero-fail counts for the same batch.
from gates import BLOCKING, expected_gates, zero_fail as _gate_zero_fail


def _hard(region):
    """Kept for callers that want a static superset; the real per-segment set comes from
    gates.expected_gates(), which learns from what the platform actually returns."""
    return BLOCKING


def _catalog(region):
    p = ROOT / ("fetched/fields_all.jsonl" if region == "USA" else f"fetched/fields_{region}.jsonl")
    idx = {}
    if p.exists():
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if region == "USA" and r.get("region") != "USA":
                continue
            d = r.get("dataset")
            idx[r.get("id")] = {"uc": r.get("userCount") or 0, "ac": r.get("alphaCount") or 0,
                                "cov": r.get("coverage") or 0,
                                "ds": d.get("id") if isinstance(d, dict) else d}
    return idx


def _add_arity(f):
    """True top-level arity of the outermost add(...).

    `f.count("multiply(") + f.count("-rank(")` double-counts every `multiply(-rank(x), w)` leg, and
    the bias scales with how many negative legs a batch uses — so it inflated exactly the dimension
    being compared (measured 9.0 vs true 8.0 on batch 1, 14.5 vs 11.0 on batch 2)."""
    i = f.find("add(")
    if i < 0:
        return 0
    depth, n, j = 0, 1, i + 4
    while j < len(f):
        ch = f[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
        j += 1
    return n


def presim(batch_path):
    """Everything measurable about a batch BEFORE spending a single simulation."""
    rows = json.load(open(batch_path))
    region = (rows[0]["settings"] or {}).get("region", "USA")
    cat = _catalog(region)
    banned = set(json.load(open(ROOT / "state/banned_fields.json"))["banned_fields"])

    # every prior batch, to measure how much of this one is genuinely new
    prior = set()
    _self = pathlib.Path(batch_path).resolve()      # resolve BOTH sides: a relative argv path
    for p in (ROOT / "state/funnel").glob("*_targets.json"):   # never equals the absolute glob,
        if p.resolve() == _self:                               # so the batch scored 100% duplicate
            continue                                           # against itself
        try:
            for r in json.load(open(p)):
                prior.add("".join(r["formula"].split()))
        except Exception:
            pass

    legcounts, depths, ucs, acs, covs, ops = [], [], [], [], [], Counter()
    dsets, banned_hits, dupes = Counter(), 0, 0
    for r in rows:
        f = r["formula"]
        if "".join(f.split()) in prior:
            dupes += 1
        legcounts.append(_add_arity(f))
        depths.append(max((f[:i].count("(") - f[:i].count(")")) for i in range(len(f))) if f else 0)
        for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*\(", f):
            ops[m.group(1)] += 1
        for fid in set(re.findall(r"\b([a-z][a-z0-9_]{3,})\b(?!\s*\()", f)):
            if fid in banned:
                banned_hits += 1
            meta = cat.get(fid)
            if meta:
                ucs.append(meta["uc"]); acs.append(meta["ac"]); covs.append(meta["cov"])
                dsets[meta["ds"]] += 1

    def med(v):
        return round(statistics.median(v), 4) if v else None

    return {
        "n_targets": len(rows),
        "region": region,
        "universe": (rows[0]["settings"] or {}).get("universe"),
        # include the arm token: keying on (family, k) alone reported batch 2 as 2.25x NARROWER
        # when counting unique formulas shows it is 1.28x wider.
        "n_legsets": len({tuple(r["old_id"].split("_")[1:4]) for r in rows}),
        "n_unique_formulas": len({"".join(r["formula"].split()) for r in rows}),
        "n_datasets": len(dsets),
        "neutralizations": dict(Counter(r["settings"]["neutralization"] for r in rows)),
        "med_legs": med(legcounts),
        "med_depth": med(depths),
        "n_distinct_ops": len(ops),
        "top_ops": dict(ops.most_common(6)),
        "med_field_userCount": med(ucs),
        "med_field_alphaCount": med(acs),
        "med_field_coverage": med(covs),
        "banned_field_hits": banned_hits,
        "duplicate_vs_prior": dupes,
        "novelty_rate": round(1 - dupes / max(len(rows), 1), 4),
    }


def postsim(batch_path, prefix):
    """Every numeric outcome the platform reported for this batch."""
    rows = json.load(open(batch_path))
    region = (rows[0]["settings"] or {}).get("region", "USA")
    hard = _hard(region)
    oids = {r["old_id"] for r in rows}
    corr = json.load(open(CORR)) if CORR.exists() else {}

    recs, per_check = [], defaultdict(list)
    fails = Counter()
    for line in open(RESULTS):
        if prefix not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("old_id") not in oids or not d.get("checks"):
            continue
        present = {c["name"] for c in d["checks"] if isinstance(c, dict)}
        hf = [c["name"] for c in d["checks"]
              if isinstance(c, dict) and c.get("result") == "FAIL" and c["name"] in hard]
        unmeasured = sorted(hard - present)   # absent != passed (the IS_LADDER_SHARPE lesson)
        for n in hf:
            fails[n] += 1
        for c in d["checks"]:
            if isinstance(c, dict) and isinstance(c.get("value"), (int, float)):
                per_check[c["name"]].append(c["value"])
        cv = corr.get(d.get("alpha")) or {}
        recs.append({"alpha": d.get("alpha"), "oid": d["old_id"],
                     "sharpe": d.get("sharpe"), "fitness": d.get("fitness"),
                     "turnover": d.get("turnover"), "returns": d.get("returns"),
                     "drawdown": d.get("drawdown"), "margin": d.get("margin"),
                     "n_hardfail": len(hf), "hardfails": hf,
                     "n_unmeasured": len(unmeasured), "unmeasured": unmeasured,
                     "prod_max": cv.get("prod_maxcorr"), "self_max": cv.get("self_maxcorr")})

    def dist(key):
        v = [r[key] for r in recs if isinstance(r.get(key), (int, float))]
        if not v:
            return None
        v.sort()
        return {"n": len(v), "min": round(v[0], 4), "p25": round(v[len(v) // 4], 4),
                "med": round(statistics.median(v), 4), "p75": round(v[3 * len(v) // 4], 4),
                "max": round(v[-1], 4), "mean": round(statistics.fmean(v), 4)}

    # zero-fail requires every hard gate to have been MEASURED and passed
    zf = [r for r in recs if r["n_hardfail"] == 0 and r["n_unmeasured"] == 0]
    return {
        "n_expected": len(rows),
        "n_simmed": len(recs),
        "n_missing": len(rows) - len(recs),
        "complete": len(recs) == len(rows),
        "zero_fail": len(zf) if recs else None,
        # None, not 0.0: an UNSIMMED batch and a batch where everything failed must never share a
        # headline number. `complete` says whether the batch can be judged at all.
        "zero_fail_rate": round(len(zf) / len(recs), 4) if recs else None,
        "n_rows_with_unmeasured_gate": sum(1 for r in recs if r["n_unmeasured"]),
        "binding_gates": dict(fails.most_common()),
        "sharpe": dist("sharpe"), "fitness": dist("fitness"), "turnover": dist("turnover"),
        "returns": dist("returns"), "drawdown": dist("drawdown"), "margin": dist("margin"),
        "prod_max": dist("prod_max"), "self_max": dist("self_max"),
        # a check whose numeric value appears on only SOME rows (CONCENTRATED_WEIGHT carries a
        # value only when it FAILS) yields a median of the failures alone — flag rather than report.
        "check_medians": {k: round(statistics.median(v), 4)
                          for k, v in sorted(per_check.items()) if len(v) == len(recs)},
        "check_partial_coverage": {k: f"{len(v)}/{len(recs)}"
                                   for k, v in sorted(per_check.items()) if len(v) != len(recs)},
        "_recs": recs,
    }


def compare(a, b, key="sharpe", n_perm=20000, seed=7, n_keys=1):
    """Is b genuinely better than a on `key`, or did it get lucky?

    CLUSTER-LEVEL permutation test. Rows are NOT independent: each unique formula is replicated
    across every neutralization arm. Recomputed ANOVA ICC(1) on the 180-row `gac_` batch gives
    ICC = 0.833 with k0 = 5.0, i.e. a design effect of 1 + (k-1)*ICC = 4.33 at ~5 rows per formula.
    A row-level test therefore treats an effective n of ~39 as if it were 170 and understates the
    p-value by roughly 2x. Here each formula is first reduced to one value (its median), and the
    permutation shuffles whole formulas.

    Tests the MEDIAN, not the mean: the whole panel reports medians, and sim metrics are skewed and
    heavy-tailed, which is an argument against the mean rather than for it.

    `n_keys` applies a Holm-style correction when several metrics are tested together — at 6 keys
    and alpha 0.05 the chance of at least one spurious REAL_IMPROVEMENT is otherwise about 26%.

    Returns a dict that ALWAYS carries p_value and ci95 keys, so a caller can index them without
    guarding for the insufficient-data branch."""
    def clusters(panel):
        by = defaultdict(list)
        for r in panel["_recs"]:
            v = r.get(key)
            if isinstance(v, (int, float)):
                by["_".join(r["oid"].split("_")[1:4])].append(v)
        return [statistics.median(v) for v in by.values() if v]

    x, y = clusters(a), clusters(b)
    base = {"key": key, "n_clusters_a": len(x), "n_clusters_b": len(y),
            "p_value": None, "ci95": [None, None], "diff": None,
            "median_a": None, "median_b": None, "cliffs_delta": None}
    if len(x) < 4 or len(y) < 4:
        return {**base, "verdict": "INSUFFICIENT_DATA"}

    rng = random.Random(seed)
    obs = statistics.median(y) - statistics.median(x)
    pool, n = x + y, len(x)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        if abs(statistics.median(pool[n:]) - statistics.median(pool[:n])) >= abs(obs):
            hits += 1
    p = (hits + 1) / (n_perm + 1)
    p_adj = min(1.0, p * n_keys)          # Holm/Bonferroni-style guard across the metric panel

    boots = []
    for _ in range(4000):
        bx = [rng.choice(x) for _ in x]
        by = [rng.choice(y) for _ in y]
        boots.append(statistics.median(by) - statistics.median(bx))
    boots.sort()
    lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]
    # Cliff's delta: a rank effect size, valid for skewed data (Cohen's d on a pooled SD that
    # includes the between-group shift is not Cohen's d and assumes symmetry we do not have)
    gt = sum(1 for u in y for v in x if u > v)
    lt = sum(1 for u in y for v in x if u < v)
    delta = (gt - lt) / (len(x) * len(y))
    return {**base, "median_a": round(statistics.median(x), 4),
            "median_b": round(statistics.median(y), 4), "diff": round(obs, 4),
            "p_value": round(p, 5), "p_adjusted": round(p_adj, 5),
            "ci95": [round(lo, 4), round(hi, 4)], "cliffs_delta": round(delta, 3),
            "verdict": ("REAL_IMPROVEMENT" if p_adj < 0.05 and lo > 0 else
                        "REAL_REGRESSION" if p_adj < 0.05 and hi < 0 else
                        "LUCK / NOT SIGNIFICANT")}


def compare_paired(panel, arm_a, arm_b, key="sharpe", arm_pos=4, base_pos=(1, 4),
                   n_perm=20000, seed=7, n_keys=1, arm_of=None):
    """PAIRED contrast between two arms of the SAME fully-crossed batch.

    Batches are crossed designs (e.g. 36 formulas x 5 neutralizations), so every arm shares the
    same underlying formulas. Treating the arms as two independent samples throws that pairing
    away: on batch `gac_` the unpaired cluster test returned LUCK for all ten neutralization
    contrasts (p_adj 0.27-1.0), while the paired test on the identical data found SLOW and
    SLOW_AND_FAST cost 0.22-0.34 sharpe at p_adj 0.0005-0.0025. Missing a real effect is as
    damaging as inventing one, and the unpaired test was doing exactly that.

    Pairs rows by the base key (family + legset), then runs an exact-style sign-flip permutation
    on the within-pair differences — the correct null when the pairing is by construction.

    arm_pos  : index into old_id.split("_") holding the arm label
    base_pos : slice bounds of old_id.split("_") identifying the shared base
    """
    # Arm identity comes from `arm_of` (a caller-supplied oid -> arm map, normally built from each
    # row's settings), NEVER from an oid substring. The oid arm token is a 4-character truncation,
    # so `SLOW` and `SLOW_AND_FAST` both render as 'SLOW'; keying on it silently merged the two and
    # last-write-wins discarded all 36 genuine SLOW rows while still reporting a healthy n_pairs=36.
    # Any conclusion drawn that way is about a different arm than the one named.
    a_of, b_of, seen = {}, {}, set()
    for r in panel["_recs"]:
        v = r.get(key)
        if not isinstance(v, (int, float)):
            continue
        arm = (arm_of or {}).get(r["oid"])
        if arm is None:
            parts = r["oid"].split("_")
            if len(parts) <= arm_pos:
                continue
            arm = parts[arm_pos]
        if arm not in (arm_a, arm_b):
            continue
        parts = r["oid"].split("_")
        base = "_".join(parts[base_pos[0]:base_pos[1]])
        if (base, arm) in seen:                      # a collision means the arm key is ambiguous
            return {"key": key, "arm_a": arm_a, "arm_b": arm_b, "n_pairs": 0,
                    "p_value": None, "p_adjusted": None, "ci95": [None, None],
                    "median_diff": None, "b_better": None,
                    "verdict": f"AMBIGUOUS_ARM_KEY (duplicate {base}/{arm})"}
        seen.add((base, arm))
        (a_of if arm == arm_a else b_of)[base] = v
    pairs = [(a_of[k], b_of[k]) for k in a_of.keys() & b_of.keys()]
    out = {"key": key, "arm_a": arm_a, "arm_b": arm_b, "n_pairs": len(pairs),
           "p_value": None, "p_adjusted": None, "ci95": [None, None],
           "median_diff": None, "b_better": None}
    if len(pairs) < 5:
        return {**out, "verdict": "INSUFFICIENT_DATA"}

    diffs = [b - a for a, b in pairs]
    obs = statistics.median(diffs)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_perm):
        flipped = [d if rng.random() < 0.5 else -d for d in diffs]
        if abs(statistics.median(flipped)) >= abs(obs):
            hits += 1
    p = (hits + 1) / (n_perm + 1)
    p_adj = min(1.0, p * n_keys)
    boots = sorted(statistics.median([rng.choice(diffs) for _ in diffs]) for _ in range(4000))
    lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]
    return {**out, "median_diff": round(obs, 4), "p_value": round(p, 5),
            "p_adjusted": round(p_adj, 5), "ci95": [round(lo, 4), round(hi, 4)],
            "b_better": f"{sum(1 for d in diffs if d > 0)}/{len(diffs)}",
            "verdict": ("REAL_IMPROVEMENT" if p_adj < 0.05 and lo > 0 else
                        "REAL_REGRESSION" if p_adj < 0.05 and hi < 0 else
                        "LUCK / NOT SIGNIFICANT")}


if __name__ == "__main__":
    batch, prefix = sys.argv[1], sys.argv[2]
    out = {"presim": presim(batch), "postsim": postsim(batch, prefix)}
    out["postsim"].pop("_recs", None)
    print(json.dumps(out, indent=1))
