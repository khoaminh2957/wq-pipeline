#!/usr/bin/env python3
"""arch_validate.py — decide whether a new alpha-generation architecture is GENUINELY better than
the incumbent, or only looks better.

Written against a session's worth of confirmed measurement lies (histogram bucket edge read as the
max; HTTP 429 read as "not measurable"; a short poll read as REJECTED; a region's non-existent gate
used as the zero-fail rule; a 10,000-row API cap reported as the true total; an unsimulated batch
reporting zero_fail_rate 0.0). The single design rule here is: EVERY branch that cannot support a
conclusion must SAY SO rather than emit a number.

  VERDICTS
    REAL               pre-registered primary shifted, at a design that was powered to detect it
    LUCK               powered to detect the declared effect, did not see it (or saw it only in the
                       top tail, which is one alpha, not an architecture)
    INSUFFICIENT_POWER the design could not have detected the declared effect; no verdict is owed
    REFUSED            the data cannot support any verdict at all (unsimulated, mutated batch,
                       incomparable arms, differential attrition, no pre-registration)

  WHY A SURROGATE ENDPOINT
    The endpoint that matters is submittables per simulation. Measured across the 84 batches on
    disk it runs 0-3% for discovery batches. Detecting a true DOUBLING of a 1.5% rate at 80% power
    needs ~1,533 independent rows per arm; rows are not independent (measured ICC of the binary
    zero-fail indicator over 1,145 formula clusters = 0.807, k0 = 3.75, design effect 3.22), so the
    real requirement is ~4,900 simulated rows PER ARM — 27 full 180-row batches per arm. That is
    unaffordable, so the primary endpoint here is WORST_SLACK.

    WORST_SLACK is not a proxy chosen for convenience: zero-fail is a deterministic threshold of it.
    For each row, worst_slack = min over the hard gates of the normalized signed margin
    ((value-limit)/|limit| for LOW_* gates, (limit-value)/|limit| for HIGH_*), so
        zero_fail  <=>  worst_slack >= 0
    exactly, whenever every hard gate was measured. Any stochastic-dominance shift in worst_slack
    therefore weakly moves the zero-fail rate in the same direction — that is an identity, not a
    correlation. The empirical corroboration (that there is enough mass near the threshold for the
    link to bite) is `arch_validate.py surrogate`: across the 84 on-disk batches Spearman between a
    batch's worst_slack distribution and its zero-fail rate is +0.72 (median), +0.79 (p90).

  WHAT THIS FILE DELIBERATELY DOES NOT DO
    It never simulates, never submits, and never writes to any pipeline state other than its own
    pre-registration records under state/funnel/prereg/.
"""
from __future__ import annotations
import argparse, hashlib, json, math, pathlib, random, statistics, sys, time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RESULTS = ROOT / "state/resim_results.jsonl"
PREREG_DIR = ROOT / "state/funnel/prereg"

# Mirrors tools/funnel/iter_metrics.py. GLB adds three per-region sharpe floors and has no
# IS_LADDER_SHARPE — using IS_LADDER_SHARPE as the GLB zero-fail rule is the exact bug this file
# exists to make impossible, so the gate set is derived from the region, never assumed.
HARD_USA = {"LOW_SHARPE", "LOW_FITNESS", "LOW_2Y_SHARPE", "HIGH_TURNOVER", "LOW_TURNOVER",
            "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"}
HARD_GLB = HARD_USA | {"LOW_GLB_AMER_SHARPE", "LOW_GLB_EMEA_SHARPE", "LOW_GLB_APAC_SHARPE"}
HIGH_IS_BAD = {"HIGH_TURNOVER", "CONCENTRATED_WEIGHT"}

MIN_CLUSTERS = 12        # below this the permutation null is so coarse that one cluster moves it
GATE_COVERAGE = 0.95     # a gate counts as "measured for this arm" at this row fraction


# ----------------------------------------------------------------------------- loading / joining

def _load_results():
    """old_id -> last result row. Rows are classified, never silently dropped."""
    out = {}
    for line in open(RESULTS):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("old_id"):
            out[d["old_id"]] = d
    return out


def _row_state(d):
    """NOT_SIMULATED / ERROR / LEGACY_SCHEMA / OK — 'not yet run' must never read as 'failed'."""
    if d is None:
        return "NOT_SIMULATED"
    ck = d.get("checks")
    if not ck:
        return "ERROR"                       # simulated, platform returned no checks
    if not any(isinstance(c, dict) for c in ck):
        return "LEGACY_SCHEMA"               # older name-only schema: unusable, not a failure
    return "OK"


def _slack(c):
    """Normalized signed margin. >= 0 means the gate is satisfied. None means NOT MEASURABLE."""
    n, v, l, r = c["name"], c.get("value"), c.get("limit"), c.get("result")
    if isinstance(v, (int, float)) and isinstance(l, (int, float)) and l != 0:
        return (l - v) / abs(l) if n in HIGH_IS_BAD else (v - l) / abs(l)
    if n == "CONCENTRATED_WEIGHT":
        # the platform reports a value only on breach (1,442 of 21,195 rows), so the margin of a
        # passing row is genuinely unknown; a nominal +/-0.25 keeps it from dominating min()
        if r == "PASS":
            return 0.25
        if r in ("FAIL", "WARNING"):
            return -0.25
    return None


def _violated(c):
    """Numeric truth, not the result STRING. 2,363 rows on disk carry result=='WARNING' on a hard
    gate whose value is on the wrong side of its own limit (943 LOW_FITNESS, 802 LOW_SHARPE,
    607 LOW_2Y_SHARPE, 11 CONCENTRATED_WEIGHT). Counting only result=='FAIL' scores those as
    passes — iter38_targets.json reports 90/90 zero-fail that way at a median fitness of 0.81
    against a hard bar of 1.0."""
    s = _slack(c)
    if s is not None:
        return s < 0
    return c.get("result") in ("FAIL", "ERROR")


def _cluster(old_id):
    """Formula cluster = the tokens before the arm token: <prefix>_<family>_<k>_<skeleton>_<ARM>_<n>.
    Settings sweeps replicate one formula across every arm, so rows are pseudo-replicates and the
    unit of independent information is the cluster, not the row."""
    return "_".join(old_id.split("_")[1:4])


def load_arm(batch_path, prefix, results):
    """Everything the validator knows about one arm, with every row accounted for."""
    rows = json.load(open(batch_path))
    settings0 = rows[0].get("settings") or {}
    region = settings0.get("region", "USA")
    hard_all = HARD_GLB if region == "GLB" else HARD_USA

    states, recs, wrong_prefix = Counter(), [], 0
    for r in rows:
        oid = r["old_id"]
        if not oid.startswith(prefix):
            wrong_prefix += 1
            continue
        d = results.get(oid)
        st = _row_state(d)
        states[st] += 1
        if st == "OK":
            recs.append((r, d))

    n_claimed = sum(1 for r in rows if r["old_id"].startswith(prefix))
    arm = {
        "batch_file": str(pathlib.Path(batch_path)),
        "sha256": hashlib.sha256(open(batch_path, "rb").read()).hexdigest(),
        "prefix": prefix,
        "n_targets": len(rows),
        "n_in_prefix": n_claimed,
        "n_rows_not_in_prefix": wrong_prefix,
        "row_states": dict(states),
        "n_usable": len(recs),
        "usable_rate": round(len(recs) / n_claimed, 4) if n_claimed else None,
        "region": region,
        "universe": settings0.get("universe"),
        "delay": settings0.get("delay"),
        "decay": settings0.get("decay"),
        "truncation": settings0.get("truncation"),
        "startDate": settings0.get("startDate"),
        "endDate": settings0.get("endDate"),
        "arms": sorted({(r.get("settings") or {}).get("neutralization") for r in rows
                        if r["old_id"].startswith(prefix)}),
        "families": sorted({r["old_id"].split("_")[1] for r in rows
                            if r["old_id"].startswith(prefix)}),
    }
    # The whole pseudo-replication correction rests on the old_id naming convention. Verify it
    # against the formulas rather than trusting it: on disk, testrun_*/mine_r0/iter24/38/39/41 all
    # collapse to n_clusters == 1 for 90-180 rows, and live1_* explode to n_clusters == n_rows.
    # Either way the design effect would be silently wrong, so it is checked, not assumed.
    inpfx = [r for r in rows if r["old_id"].startswith(prefix)]
    n_clusters = len({_cluster(r["old_id"]) for r in inpfx})
    n_formulas = len({"".join(r["formula"].split()) for r in inpfx})
    arm["n_clusters_from_old_id"] = n_clusters
    arm["n_unique_formulas"] = n_formulas
    arm["cluster_key_matches_formulas"] = (n_clusters == n_formulas)
    if n_clusters != n_formulas:
        arm["cluster_key_warning"] = (
            f"old_id slice [1:4] yields {n_clusters} clusters but the batch has {n_formulas} "
            f"unique formulas; the cluster unit does not equal the formula unit, so the "
            f"design-effect correction is over- or under-applied")
    if not recs:
        arm.update(gates_measured=[], gates_unmeasured=sorted(hard_all), per_row=[])
        return arm

    # a gate is MEASURED for this arm only if the platform actually returned it; absence is never
    # read as a pass (the IS_LADDER_SHARPE lesson) and never read as a fail either — it is reported
    cov = {}
    for g in hard_all:
        cov[g] = sum(1 for _, d in recs
                     if any(isinstance(c, dict) and c["name"] == g for c in d["checks"])) / len(recs)
    measured = sorted(g for g, v in cov.items() if v >= GATE_COVERAGE)

    per_row = []
    for r, d in recs:
        chk = {c["name"]: c for c in d["checks"] if isinstance(c, dict)}
        sl, unmeasured = [], []
        for g in measured:
            s = _slack(chk[g]) if g in chk else None
            (sl.append(s) if s is not None else unmeasured.append(g))
        nfail = sum(1 for g in measured if g in chk and _violated(chk[g])) + len(unmeasured)
        per_row.append({
            "oid": r["old_id"], "cluster": _cluster(r["old_id"]),
            "arm": (r.get("settings") or {}).get("neutralization"),
            "worst_slack": (min(sl) if sl and not unmeasured else None),
            "n_unmeasured": len(unmeasured), "n_hardfail": nfail,
            "zero_fail": 1.0 if (sl and not unmeasured and min(sl) >= 0) else 0.0,
            "sharpe": d.get("sharpe"), "fitness": d.get("fitness"),
            "turnover": d.get("turnover"), "returns": d.get("returns"),
        })
    arm.update(gates_measured=measured, gates_unmeasured=sorted(set(hard_all) - set(measured)),
               gate_coverage={g: round(v, 3) for g, v in sorted(cov.items())}, per_row=per_row)
    return arm


# --------------------------------------------------------------------------------- cluster stats

def cluster_values(arm, key, arms_filter=None, cluster_filter=None):
    by = defaultdict(list)
    for r in arm["per_row"]:
        if arms_filter and r["arm"] not in arms_filter:
            continue
        if cluster_filter and not cluster_filter(r["cluster"]):
            continue
        v = r.get(key)
        if isinstance(v, (int, float)):
            by[r["cluster"]].append(v)
    return {k: statistics.median(v) for k, v in by.items() if v}, by


def icc1(groups):
    """One-way random-effects ICC(1) + the average cluster size k0 it implies. Measured, never
    assumed: batch-level ICC of sharpe on disk ranges 0.00 to 0.998, so any hardcoded design effect
    would be wrong for most batches."""
    g = [v for v in groups if len(v) >= 2]
    if len(g) < 2:
        return None, len(g), 1.0
    a, N = len(g), sum(len(v) for v in g)
    gm = sum(sum(v) for v in g) / N
    msb = sum(len(v) * (statistics.fmean(v) - gm) ** 2 for v in g) / (a - 1)
    msw = (sum(sum((x - statistics.fmean(v)) ** 2 for x in v) for v in g) / (N - a)) if N > a else 0.0
    k0 = (N - sum(len(v) ** 2 for v in g) / N) / (a - 1)
    den = msb + (k0 - 1) * msw
    if den == 0:
        return None, a, k0
    return max(0.0, min(1.0, (msb - msw) / den)), a, k0


# -------------------------------------------------------------------------------------- the test

def _median(v):
    return statistics.median(v)


def perm_test(x, y, n_perm=20000, seed=7, stat=_median):
    """Two-sided permutation test on cluster-level values. Exact null under exchangeability, no
    distributional assumption, and — critically — the permuted unit is the cluster, so a batch that
    is 180 rows over 36 formulas is treated as 36 pieces of information, not 180."""
    rng = random.Random(seed)
    obs = stat(y) - stat(x)
    pool, n = list(x) + list(y), len(x)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        if abs(stat(pool[n:]) - stat(pool[:n])) >= abs(obs) - 1e-12:
            hits += 1
    return obs, (hits + 1) / (n_perm + 1)


def boot_ci(x, y, n_boot=4000, seed=11, stat=_median):
    """Percentile bootstrap over CLUSTERS. Reported as an interval, never used as the sole gate:
    at ~36 clusters a percentile interval on a difference of medians under-covers on lumpy data."""
    rng = random.Random(seed)
    d = []
    for _ in range(n_boot):
        d.append(stat([rng.choice(y) for _ in y]) - stat([rng.choice(x) for _ in x]))
    d.sort()
    return d[int(0.025 * len(d))], d[int(0.975 * len(d))]


def cliffs_delta(x, y):
    gt = sum(1 for u in y for v in x if u > v)
    lt = sum(1 for u in y for v in x if u < v)
    return (gt - lt) / (len(x) * len(y))


def holm(pvals):
    """Real Holm step-down, not p*m. Uniformly more powerful than Bonferroni at the same FWER."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m, adj, running = len(pvals), [0.0] * len(pvals), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        adj[i] = running
    return adj


# ------------------------------------------------------------------------------ power arithmetic

Z = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}


def n_two_prop(p1, p2, alpha=0.05, power=0.80):
    """Independent rows per arm for a two-sided two-proportion test."""
    if p2 == p1:
        return float("inf")
    za, zb = 1.9600 if alpha == 0.05 else 2.5758, Z[power]
    pbar = (p1 + p2) / 2
    a = za * math.sqrt(2 * pbar * (1 - pbar))
    b = zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return (a + b) ** 2 / (p2 - p1) ** 2


def mde_two_prop(p1, n_eff, alpha=0.05, power=0.80):
    """Smallest p2 > p1 detectable at `power` with n_eff INDEPENDENT rows per arm."""
    lo, hi = p1, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        (lo, hi) = (mid, hi) if n_two_prop(p1, mid, alpha, power) > n_eff else (lo, mid)
    return hi


def surrogate_power(x_clusters, n_b, delta, alpha=0.05, n_sim=400, n_perm=2000, seed=5):
    """A-priori power of the cluster permutation test to detect a shift of `delta` in the surrogate,
    computed by RESAMPLING THE INCUMBENT ARM'S OWN cluster distribution at the realized cluster
    counts. This is design power at the declared effect — not post-hoc power at the observed effect,
    which is a restatement of the p-value and tells you nothing."""
    if len(x_clusters) < 4 or n_b < 4:
        return None
    rng = random.Random(seed)
    rej = 0
    for _ in range(n_sim):
        a = [rng.choice(x_clusters) for _ in range(len(x_clusters))]
        b = [rng.choice(x_clusters) + delta for _ in range(n_b)]
        _, p = perm_test(a, b, n_perm=n_perm, seed=rng.randrange(1 << 30))
        rej += (p < alpha)
    return rej / n_sim


# ------------------------------------------------------------------------------ pre-registration

def prereg_write(args):
    PREREG_DIR.mkdir(parents=True, exist_ok=True)
    results = _load_results()
    rec = {"id": args.id, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "hypothesis": args.hypothesis,
           "primary_metric": args.primary, "direction": args.direction,
           "declared_mde": args.mde, "alpha": args.alpha, "min_power": args.min_power,
           "secondary_metrics": args.secondary.split(",") if args.secondary else [],
           "holdout": args.holdout, "holdout_seed": args.holdout_seed, "arms": {}}
    for name, spec in (("incumbent", args.incumbent), ("challenger", args.challenger)):
        path, prefix = spec.split("::")
        p = ROOT / path if not pathlib.Path(path).is_absolute() else pathlib.Path(path)
        tgt = json.load(open(p))
        oids = [r["old_id"] for r in tgt if r["old_id"].startswith(prefix)]
        simmed = sum(1 for o in oids if _row_state(results.get(o)) != "NOT_SIMULATED")
        rec["arms"][name] = {"batch_file": str(p), "prefix": prefix, "n_targets": len(oids),
                             "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
                             "n_simulated_at_prereg": simmed}
    body = json.dumps(rec, sort_keys=True).encode()
    rec["record_sha256"] = hashlib.sha256(body).hexdigest()
    out = PREREG_DIR / f"{args.id}.json"
    if out.exists() and not args.force:
        sys.exit(f"REFUSED: pre-registration {args.id} already exists. Rewriting it after seeing "
                 f"results is exactly what pre-registration prevents. Use a new --id.")
    json.dump(rec, open(out, "w"), indent=1, sort_keys=True)
    ch = rec["arms"]["challenger"]
    print(json.dumps(rec, indent=1, sort_keys=True))
    if ch["n_simulated_at_prereg"] > 0:
        print(f"\nWARNING: {ch['n_simulated_at_prereg']}/{ch['n_targets']} challenger rows were "
              f"ALREADY simulated when this was registered. The verdict will be marked "
              f"CONTAMINATED and can never read REAL.", file=sys.stderr)
    return rec


def prereg_load(pid):
    p = PREREG_DIR / f"{pid}.json"
    if not p.exists():
        return None
    return json.load(open(p))


def _holdout_filter(pre):
    """Deterministic split-half over formula CLUSTERS, keyed by the pre-registration id. The half
    that renders the verdict is fixed before any result is seen, so a metric that only works on the
    convenient half cannot be presented as a confirmation. Splitting on clusters (not rows) keeps
    every arm of a formula on the same side — splitting on rows would put the same formula in both
    halves and make the 'holdout' a copy of the training set.

    Returns (verdict_half, exploration_half) predicates, or (None, None) when no holdout was
    declared. Halving the clusters costs power; `power_at_declared_mde` is computed on the half that
    actually renders the verdict, so the cost shows up in the verdict rather than being hidden."""
    if not pre or pre.get("holdout") != "split_half":
        return None, None
    seed = str(pre.get("holdout_seed") or pre["id"])

    def side(cluster, want):
        h = hashlib.sha256(f"{seed}|{cluster}".encode()).hexdigest()
        return (int(h[:8], 16) % 2 == 0) == want
    return (lambda c: side(c, True)), (lambda c: side(c, False))


# ------------------------------------------------------------------------------------- comparing

# Two kinds of problem, deliberately kept apart:
#   BLOCKING  — the numbers cannot be computed at all (nothing simulated, incomparable endpoints).
#   INTEGRITY — the numbers CAN be computed but nothing about the process protects them from
#               selection bias, so they are printed and labelled exploratory, never promoted to a
#               verdict. Hiding them would invite the analyst to recompute them by hand, unlabelled.
REFUSALS = []


def _refuse(code, msg, blocking=True):
    REFUSALS.append({"code": code, "blocking": blocking, "detail": msg})


def _blocking():
    return [r for r in REFUSALS if r["blocking"]]


def compare_arms(a, b, pre, n_perm, seed):
    REFUSALS.clear()      # module-level accumulator: a second call must not inherit the first's
    primary = (pre or {}).get("primary_metric", "worst_slack")
    alpha = (pre or {}).get("alpha", 0.05)
    min_power = (pre or {}).get("min_power", 0.80)
    declared_mde = (pre or {}).get("declared_mde")
    direction = (pre or {}).get("direction", "greater")
    panel = [primary] + [m for m in (pre or {}).get("secondary_metrics", []) if m != primary]

    # ---- refusal gates, evaluated before any number is computed -------------------------------
    if not pre:
        _refuse("NO_PREREGISTRATION",
                "no pre-registration record; batches here are designed AFTER seeing the previous "
                "batch's results, so an un-registered metric choice is indistinguishable from a "
                "post-hoc one. Run `arch_validate.py prereg` before simulating the challenger.",
                blocking=False)
    else:
        for name, arm in (("incumbent", a), ("challenger", b)):
            rec = pre["arms"][name]
            if rec["sha256"] != arm["sha256"]:
                _refuse("BATCH_MUTATED",
                        f"{name} batch file changed since pre-registration "
                        f"({rec['sha256'][:12]} -> {arm['sha256'][:12]}); the rows being scored are "
                        f"not the rows that were declared", blocking=False)
        if pre["arms"]["challenger"]["n_simulated_at_prereg"] > 0:
            _refuse("CONTAMINATED_PREREG",
                    f"{pre['arms']['challenger']['n_simulated_at_prereg']} of "
                    f"{pre['arms']['challenger']['n_targets']} challenger rows were already "
                    f"simulated when the hypothesis was declared, so the hypothesis could have "
                    f"been read off the answer", blocking=False)

    for name, arm in (("incumbent", a), ("challenger", b)):
        st = arm["row_states"]
        if arm["n_usable"] == 0:
            _refuse("NOT_SIMULATED" if st.get("NOT_SIMULATED") else "NO_USABLE_ROWS",
                    f"{name} has 0 usable rows out of {arm['n_in_prefix']}; row states {st}. "
                    f"NOT_SIMULATED is not a result — it is the absence of one.")

    if a["region"] != b["region"] or a["universe"] != b["universe"]:
        _refuse("INCOMPARABLE_UNIVERSE",
                f"{a['region']}/{a['universe']} vs {b['region']}/{b['universe']}: different gate "
                f"sets and different sub-universe limits, so the endpoints are not the same "
                f"quantity")
    for f in ("delay", "startDate", "endDate"):
        if a.get(f) != b.get(f):
            _refuse("INCOMPARABLE_SETTINGS", f"{f}: {a.get(f)} vs {b.get(f)}")

    common_gates = sorted(set(a["gates_measured"]) & set(b["gates_measured"]))
    if a["n_usable"] and b["n_usable"] and set(a["gates_measured"]) != set(b["gates_measured"]):
        _refuse("GATE_SET_MISMATCH",
                f"incumbent measured {sorted(set(a['gates_measured']) - set(b['gates_measured']))} "
                f"that the challenger did not, and vice versa "
                f"{sorted(set(b['gates_measured']) - set(a['gates_measured']))}. A zero-fail rate "
                f"over 6 gates is not comparable to one over 7; on disk, LOW_2Y_SHARPE is returned "
                f"for some batches and not others, which alone flips a batch from 0%% to 100%%.")

    if a["n_usable"] and b["n_usable"]:
        ur = abs((a["usable_rate"] or 0) - (b["usable_rate"] or 0))
        if ur > 0.10:
            _refuse("DIFFERENTIAL_ATTRITION",
                    f"usable-row rates differ by {ur:.0%} ({a['usable_rate']:.0%} vs "
                    f"{b['usable_rate']:.0%}); the arm whose worst alphas failed to simulate would "
                    f"win on survivorship alone")

    for name, arm in (("incumbent", a), ("challenger", b)):
        if arm.get("cluster_key_warning"):
            _refuse("CLUSTER_KEY_UNVERIFIED", f"{name}: {arm['cluster_key_warning']}",
                    blocking=False)

    common_arms = sorted(set(a["arms"]) & set(b["arms"]))
    arm_note = None
    if set(a["arms"]) != set(b["arms"]):
        arm_note = (f"neutralization arms differ ({a['arms']} vs {b['arms']}); restricting BOTH "
                    f"arms to the {len(common_arms)} shared ones. Unequal arm counts also give "
                    f"cluster medians unequal sampling variance, which breaks exchangeability.")
        if len(common_arms) < 2:
            _refuse("NO_COMMON_ARMS", "fewer than 2 shared neutralization arms")

    out = {"primary_metric": primary, "alpha": alpha, "direction": direction,
           "declared_mde": declared_mde, "min_power": min_power,
           "common_gates": common_gates, "common_arms": common_arms, "arm_note": arm_note,
           "exploratory_only": bool([r for r in REFUSALS if not r["blocking"]])}
    if _blocking():
        out["note"] = "no statistics computed: " + ", ".join(r["code"] for r in _blocking())
        return out

    cf, explore = _holdout_filter(pre)
    out["holdout"] = ((pre or {}).get("holdout") or "none")

    # ---- the endpoint that actually matters, and the power it would have needed ---------------
    _, zx_groups = cluster_values(a, "zero_fail", common_arms)
    _, zy_groups = cluster_values(b, "zero_fail", common_arms)
    rows_a = [r for r in a["per_row"] if r["arm"] in common_arms]
    rows_b = [r for r in b["per_row"] if r["arm"] in common_arms]
    zf_a = sum(r["zero_fail"] for r in rows_a) / len(rows_a)
    zf_b = sum(r["zero_fail"] for r in rows_b) / len(rows_b)
    icc_z, _, k0_z = icc1(list(zx_groups.values()) + list(zy_groups.values()))
    deff = 1 + (k0_z - 1) * icc_z if icc_z is not None else 1.0
    base = zf_a if zf_a > 0 else 0.015          # a 0/180 arm gives no rate; use the corpus baseline
    n_eff = len(rows_a) / deff
    out["true_endpoint"] = {
        "zero_fail_rate_incumbent": round(zf_a, 4), "zero_fail_rate_challenger": round(zf_b, 4),
        "n_rows_per_arm": len(rows_a),
        "ICC_zero_fail": None if icc_z is None else round(icc_z, 3),
        "mean_cluster_size_k0": round(k0_z, 2), "design_effect": round(deff, 2),
        "effective_n_per_arm": round(n_eff, 1),
        "baseline_used_for_power": round(base, 4),
        "n_rows_needed_per_arm_to_detect_doubling": round(n_two_prop(base, 2 * base) * deff),
        "batches_of_180_needed_per_arm": round(n_two_prop(base, 2 * base) * deff / 180, 1),
        "min_detectable_rate_at_this_n": round(mde_two_prop(base, n_eff), 4),
        "min_detectable_multiple": round(mde_two_prop(base, n_eff) / base, 1),
    }

    # ---- the surrogate: zero_fail is a threshold of it, so a shift here IS the mechanism -------
    tests, pvals = [], []
    for key in panel:
        xs, _ = cluster_values(a, key, common_arms, cf)
        ys, _ = cluster_values(b, key, common_arms, cf)
        x, y = list(xs.values()), list(ys.values())
        rec = {"metric": key, "n_clusters_a": len(x), "n_clusters_b": len(y)}
        if len(x) < MIN_CLUSTERS or len(y) < MIN_CLUSTERS:
            rec.update(status="TOO_FEW_CLUSTERS", note=f"need >= {MIN_CLUSTERS} clusters per arm")
            tests.append(rec)
            pvals.append(1.0)
            continue
        obs, p = perm_test(x, y, n_perm=n_perm, seed=seed)
        lo, hi = boot_ci(x, y, seed=seed + 1)
        # a shift in the DISTRIBUTION is the claim; a shift only in the maximum is one lucky alpha
        _, p_max = perm_test(x, y, n_perm=n_perm, seed=seed + 2, stat=max)
        rec.update(status="OK", median_a=round(statistics.median(x), 4),
                   median_b=round(statistics.median(y), 4), diff=round(obs, 4),
                   p_value=round(p, 5), ci95=[round(lo, 4), round(hi, 4)],
                   cliffs_delta=round(cliffs_delta(x, y), 3),
                   frac_b_above_median_a=round(
                       sum(1 for v in y if v > statistics.median(x)) / len(y), 3),
                   max_a=round(max(x), 4), max_b=round(max(y), 4),
                   p_value_max_statistic=round(p_max, 5))
        if key == primary and declared_mde is not None:
            rec["power_at_declared_mde"] = surrogate_power(x, len(y), declared_mde, alpha)
        tests.append(rec)
        pvals.append(p)
    if explore is not None:
        # the half the verdict is NOT taken from, reported so the two can be eyeballed for
        # consistency. It can never change the verdict — that is the whole point of declaring
        # which half counts before the results exist.
        xe = list(cluster_values(a, primary, common_arms, explore)[0].values())
        ye = list(cluster_values(b, primary, common_arms, explore)[0].values())
        if len(xe) >= 4 and len(ye) >= 4:
            obs_e, p_e = perm_test(xe, ye, n_perm=n_perm, seed=seed + 3)
            out["exploration_half"] = {"metric": primary, "n_clusters_a": len(xe),
                                       "n_clusters_b": len(ye), "diff": round(obs_e, 4),
                                       "p_value": round(p_e, 5), "counts_toward_verdict": False}
        else:
            out["exploration_half"] = {"status": "TOO_FEW_CLUSTERS",
                                       "n_clusters_a": len(xe), "n_clusters_b": len(ye),
                                       "counts_toward_verdict": False}

    for rec, padj in zip(tests, holm(pvals)):
        rec["p_holm"] = round(padj, 5)
    out["tests"] = tests
    return out


def verdict(out):
    if REFUSALS:
        # Integrity failures do not stop the arithmetic, but they do stop the conclusion: a result
        # that was not declared in advance cannot be told apart from a post-hoc pick.
        return "REFUSED", [f"{r['code']}: {r['detail']}" for r in REFUSALS]
    prim = next((t for t in out.get("tests", []) if t["metric"] == out["primary_metric"]), None)
    if prim is None or prim.get("status") != "OK":
        return "REFUSED", ["PRIMARY_METRIC_UNTESTABLE"]
    reasons = []
    pw = prim.get("power_at_declared_mde")
    if out["declared_mde"] is None:
        return "REFUSED", ["NO_DECLARED_MDE"]
    if pw is None or pw < out["min_power"]:
        return "INSUFFICIENT_POWER", [
            f"design power to detect the declared MDE of {out['declared_mde']} is "
            f"{'unknown' if pw is None else f'{pw:.2f}'} at {prim['n_clusters_a']} vs "
            f"{prim['n_clusters_b']} clusters, below the pre-registered {out['min_power']}. "
            f"Neither 'better' nor 'not better' is supported; run more clusters (more formulas), "
            f"not more arms (more arms only add pseudo-replicates)."]
    sig = prim["p_holm"] < out["alpha"]
    want_up = out["direction"] == "greater"
    dir_ok = (prim["diff"] > 0) if want_up else (prim["diff"] < 0)
    ci_ok = (prim["ci95"][0] > 0) if want_up else (prim["ci95"][1] < 0)
    if sig and dir_ok and ci_ok:
        return "REAL", [f"cluster permutation p_holm={prim['p_holm']}, "
                        f"Cliff's delta={prim['cliffs_delta']}, "
                        f"bootstrap CI {prim['ci95']} excludes 0, power {pw:.2f}"]
    if prim["p_value_max_statistic"] < out["alpha"] and not sig:
        return "LUCK", ["only the MAXIMUM cluster differs (p_max="
                        f"{prim['p_value_max_statistic']}); the distribution did not move "
                        f"(p_holm={prim['p_holm']}). One good alpha is not an architecture."]
    reasons.append(f"p_holm={prim['p_holm']} at power {pw:.2f}: the design could have seen the "
                   f"declared effect and did not")
    if sig and not ci_ok:
        reasons.append(f"permutation significant but the bootstrap CI {prim['ci95']} straddles 0")
    return "LUCK", reasons


# ------------------------------------------------------------------------------------ subcommand

def cmd_verdict(args):
    results = _load_results()
    pre = prereg_load(args.prereg) if args.prereg else None
    if args.prereg and pre is None:
        print(json.dumps({"verdict": "REFUSED",
                          "reasons": [f"pre-registration '{args.prereg}' not found in {PREREG_DIR}"]},
                         indent=1))
        return 2
    ipath, iprefix = args.incumbent.split("::")
    cpath, cprefix = args.challenger.split("::")
    a = load_arm(ROOT / ipath if not pathlib.Path(ipath).is_absolute() else ipath, iprefix, results)
    b = load_arm(ROOT / cpath if not pathlib.Path(cpath).is_absolute() else cpath, cprefix, results)
    out = compare_arms(a, b, pre, args.n_perm, args.seed)
    v, reasons = verdict(out)
    report = {
        "verdict": v, "reasons": reasons,
        "refusals": REFUSALS,
        "prereg": None if not pre else {k: pre[k] for k in
                                        ("id", "created_utc", "hypothesis", "primary_metric",
                                         "direction", "declared_mde", "alpha", "min_power",
                                         "holdout", "record_sha256")},
        "incumbent": {k: v2 for k, v2 in a.items() if k != "per_row"},
        "challenger": {k: v2 for k, v2 in b.items() if k != "per_row"},
        "analysis": out,
    }
    print(json.dumps(report, indent=1, default=str))
    return 0 if v in ("REAL", "LUCK") else 1


def cmd_power(args):
    print(f"Two-sided two-proportion test, alpha={args.alpha}, power={args.power}.")
    print(f"Design effect applied: {args.deff} (measured ICC of the binary zero-fail indicator "
          f"over on-disk clusters = 0.807 at k0 = 3.75).\n")
    print(f"{'baseline':>10}{'doubled':>10}{'n_indep/arm':>13}{'n_rows/arm':>12}{'180-batches/arm':>17}")
    for p1 in (0.005, 0.01, 0.015, 0.02, 0.03, 0.05):
        n = n_two_prop(p1, 2 * p1, args.alpha, args.power)
        print(f"{p1:>10.3f}{2*p1:>10.3f}{n:>13.0f}{n*args.deff:>12.0f}{n*args.deff/180:>17.1f}")
    print(f"\nWhat a single {args.n} -row arm can actually see "
          f"(effective n = {args.n/args.deff:.0f} independent rows):")
    print(f"{'baseline':>10}{'min detectable':>16}{'multiple':>11}")
    for p1 in (0.005, 0.01, 0.015, 0.02, 0.03, 0.05):
        m = mde_two_prop(p1, args.n / args.deff, args.alpha, args.power)
        print(f"{p1:>10.3f}{m:>16.4f}{m/p1:>11.1f}x")


def cmd_surrogate(args):
    """Evidence that worst_slack is a legitimate stand-in for the true endpoint, from the batches
    already on disk. The link is definitional (zero_fail <=> worst_slack >= 0); this measures
    whether the link has empirical bite across real batches."""
    import glob
    results = _load_results()
    rows = []
    for p in sorted(glob.glob(str(ROOT / "state/funnel/*_targets.json"))):
        try:
            tgt = json.load(open(p))
        except Exception:
            continue
        if not isinstance(tgt, list) or not tgt or "old_id" not in tgt[0]:
            continue
        arm = load_arm(p, tgt[0]["old_id"].split("_")[0] + "_", results)
        pr = [r for r in arm["per_row"] if r["worst_slack"] is not None]
        if len(pr) < 40:
            continue
        ws = sorted(r["worst_slack"] for r in pr)
        cl, _ = cluster_values(arm, "worst_slack")
        rows.append({"file": pathlib.Path(p).name, "n": len(pr), "n_clusters": len(cl),
                     "gates": len(arm["gates_measured"]),
                     "zero_fail_rate": sum(r["zero_fail"] for r in pr) / len(pr),
                     "med_ws": ws[len(ws) // 2], "p90_ws": ws[int(0.9 * len(ws))],
                     "cl_med_ws": statistics.median(list(cl.values()))})

    def spearman(u, v):
        def rank(z):
            s = sorted(range(len(z)), key=lambda i: z[i])
            r, i = [0.0] * len(z), 0
            while i < len(s):
                j = i
                while j + 1 < len(s) and z[s[j + 1]] == z[s[i]]:
                    j += 1
                for k in range(i, j + 1):
                    r[s[k]] = (i + j) / 2 + 1
                i = j + 1
            return r
        ru, rv, n = rank(u), rank(v), len(u)
        mu, mv = sum(ru) / n, sum(rv) / n
        num = sum((x - mu) * (y - mv) for x, y in zip(ru, rv))
        den = math.sqrt(sum((x - mu) ** 2 for x in ru) * sum((y - mv) ** 2 for y in rv))
        return num / den if den else 0.0

    y = [r["zero_fail_rate"] for r in rows]
    print(json.dumps({
        "n_batches": len(rows),
        "n_batches_with_nonzero_zero_fail": sum(1 for v in y if v > 0),
        "identity": "zero_fail <=> worst_slack >= 0 when every hard gate is measured",
        "spearman_vs_zero_fail_rate": {
            k: round(spearman([r[k] for r in rows], y), 3)
            for k in ("med_ws", "p90_ws", "cl_med_ws")},
    }, indent=1))
    if args.verbose:
        for r in sorted(rows, key=lambda r: -r["zero_fail_rate"]):
            print(f"{r['file']:<38}{r['n']:>5}{r['n_clusters']:>5}{r['gates']:>4}"
                  f"{r['zero_fail_rate']:>8.3f}{r['med_ws']:>9.3f}{r['p90_ws']:>9.3f}")


def cmd_selftest(args):
    """Synthetic end-to-end checks: a known shift must read REAL, a null must read LUCK, a design
    too small must read INSUFFICIENT_POWER, and an unsimulated challenger must read REFUSED. Runs
    against a temporary results file; touches nothing in state/."""
    import tempfile, shutil
    global RESULTS, PREREG_DIR
    real_results, real_prereg = RESULTS, PREREG_DIR
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="arch_validate_selftest_"))
    ok = True
    try:
        PREREG_DIR = tmp / "prereg"
        rng = random.Random(1)
        base = {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1,
                "decay": 6, "truncation": 0.05, "startDate": "2019-01-01", "endDate": "2023-12-31"}
        ARMS = ["INDUSTRY", "SUBINDUSTRY", "STATISTICAL", "MARKET"]

        def make(prefix, n_clusters, shift, spread=0.35):
            tgts, rows = [], []
            for c in range(n_clusters):
                mu = rng.gauss(-0.45 + shift, spread)
                for ai, arm in enumerate(ARMS):
                    oid = f"{prefix}fam_k{c:02d}_SK{c%3}_{arm[:4]}_{c*10+ai}"
                    tgts.append({"old_id": oid, "id": None, "formula": f"f{c}",
                                 "settings": {**base, "neutralization": arm}})
                    sh = 1.58 * (1 + mu + rng.gauss(0, 0.05))
                    rows.append({"old_id": oid, "alpha": oid, "sharpe": round(sh, 3),
                                 "fitness": round(1.0 * (1 + mu), 3), "turnover": 0.2,
                                 "checks": [
                                     {"name": "LOW_SHARPE", "result": "PASS", "value": round(sh, 3),
                                      "limit": 1.58},
                                     {"name": "LOW_FITNESS", "result": "PASS",
                                      "value": round(1.0 * (1 + mu), 3), "limit": 1.0},
                                     {"name": "LOW_TURNOVER", "result": "PASS", "value": 0.2,
                                      "limit": 0.01},
                                     {"name": "HIGH_TURNOVER", "result": "PASS", "value": 0.2,
                                      "limit": 0.7},
                                     {"name": "CONCENTRATED_WEIGHT", "result": "PASS"},
                                     {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS",
                                      "value": round(sh * 0.9, 3), "limit": 0.8},
                                     {"name": "LOW_2Y_SHARPE", "result": "PASS", "value": round(sh, 3),
                                      "limit": 1.58}]})
            return tgts, rows

        def run(name, ncl_a, ncl_b, shift, mde, expect, simulate_b=True, ncl_small=None):
            global RESULTS
            ta, ra = make("A_", ncl_a, 0.0)
            tb, rb = make("B_", ncl_b, shift)
            json.dump(ta, open(tmp / f"{name}_a.json", "w"))
            json.dump(tb, open(tmp / f"{name}_b.json", "w"))
            RESULTS = tmp / f"{name}_res.jsonl"
            with open(RESULTS, "w") as f:                       # incumbent only, as at prereg time
                for r in ra:
                    f.write(json.dumps(r) + "\n")
            ns = argparse.Namespace(
                id=name, hypothesis="synthetic", incumbent=f"{tmp/f'{name}_a.json'}::A_",
                challenger=f"{tmp/f'{name}_b.json'}::B_", primary="worst_slack",
                secondary="", direction="greater", mde=mde, alpha=0.05, min_power=0.80,
                holdout="none", holdout_seed=None, force=True)
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                prereg_write(ns)
            if simulate_b:                                      # challenger simulated AFTER prereg
                with open(RESULTS, "a") as f:
                    for r in rb:
                        f.write(json.dumps(r) + "\n")
            pre = json.load(open(PREREG_DIR / f"{name}.json"))
            results = _load_results()
            A = load_arm(tmp / f"{name}_a.json", "A_", results)
            B = load_arm(tmp / f"{name}_b.json", "B_", results)
            out = compare_arms(A, B, pre, 4000, 7)
            v, why = verdict(out)
            good = (v == expect)
            print(f"  [{'ok ' if good else 'FAIL'}] {name:<22} -> {v:<18} (expected {expect})")
            if not good:
                print(f"        {why}")
            return good

        print("arch_validate selftest")
        ok &= run("shift_real", 55, 55, 0.45, 0.30, "REAL")
        ok &= run("null_luck", 55, 55, 0.00, 0.30, "LUCK")
        ok &= run("too_small", 13, 13, 0.30, 0.10, "INSUFFICIENT_POWER")
        ok &= run("unsimulated", 40, 40, 0.30, 0.20, "REFUSED", simulate_b=False)
        print("SELFTEST", "PASS" if ok else "FAIL")
    finally:
        RESULTS, PREREG_DIR = real_results, real_prereg
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prereg", help="declare the hypothesis and decision rule BEFORE simulating")
    p.add_argument("--id", required=True)
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--incumbent", required=True, help="path/to/batch.json::prefix_")
    p.add_argument("--challenger", required=True, help="path/to/batch.json::prefix_")
    p.add_argument("--primary", default="worst_slack")
    p.add_argument("--secondary", default="sharpe,fitness")
    p.add_argument("--direction", default="greater", choices=["greater", "less"])
    p.add_argument("--mde", type=float, required=True,
                   help="smallest shift in the primary metric worth acting on")
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--min-power", dest="min_power", type=float, default=0.80)
    p.add_argument("--holdout", default="none", choices=["none", "split_half"])
    p.add_argument("--holdout-seed", dest="holdout_seed", default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=prereg_write)

    p = sub.add_parser("verdict", help="render REAL / LUCK / INSUFFICIENT_POWER / REFUSED")
    p.add_argument("--incumbent", required=True, help="path/to/batch.json::prefix_")
    p.add_argument("--challenger", required=True, help="path/to/batch.json::prefix_")
    p.add_argument("--prereg", default=None)
    p.add_argument("--n-perm", dest="n_perm", type=int, default=20000)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=cmd_verdict)

    p = sub.add_parser("power", help="sample size / minimum detectable effect for the true endpoint")
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--power", type=float, default=0.80, choices=[0.80, 0.90, 0.95])
    p.add_argument("--deff", type=float, default=3.22)
    p.add_argument("--n", type=float, default=180)
    p.set_defaults(func=cmd_power)

    p = sub.add_parser("surrogate", help="evidence that worst_slack stands in for zero-fail")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_surrogate)

    p = sub.add_parser("selftest", help="synthetic REAL / LUCK / INSUFFICIENT_POWER / REFUSED checks")
    p.set_defaults(func=cmd_selftest)

    args = ap.parse_args()
    rc = args.func(args)
    sys.exit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
