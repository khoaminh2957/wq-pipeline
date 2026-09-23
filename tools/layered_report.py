#!/usr/bin/env python3
"""What did the layered draw actually buy? Read run journals and answer by STRUCTURE and by FACTOR.

This exists because the previous generation could not answer it. Its journal kept `old_id` — a
sha256 of the formula, not invertible — and discarded the formula itself, so 2,639 simulated rows
were unanalysable after the fact. `layered_sim.py` records the whole draw, and this reads it back.

WHAT IT REFUSES TO DO. It reports rates with their denominators and their uncertainty, and it does
not rank structures by a point estimate. Gems in this project cluster hard (design effect ~14.3 on
the gem indicator), a batch of a few hundred holds a handful of positives at best, and a table of
"best operator" sorted by a 2-of-7 rate is a rationalisation with a header row. Where a comparison
has too few positives to separate, it says so instead of sorting.

THE FACTORIAL (PREREG_P1 §3.2, ratified by Khoa 2026-08-13). Four factors land at once — D field
screen, C market gate, U unit model, S stage-rule removal. In a balanced 2^4 every main-effect
contrast uses ALL rows split in half, so one batch buys four attributions at the price of one. The
previous version of this file hard-required exactly two `meta['arm']` levels and printed "only one
arm present" when handed 16 cells (INTEGRATION_P1R1 S7) — a false sentence with no contrast behind
it. Factor levels are now read per row and each row enters all four contrasts.

THE VERDICT IS ALWAYS WITHIN-BATCH. A factor whose ON rows live in one journal and OFF rows in
another is confounded with time of day, market regime and quota state, which is the exact
comparison HARNESS_SOP.md forbids. Such a factor is reported NO VERDICT — IDENTIFIED ONLY BETWEEN
BLOCKS. Round-over-round median still prints, as a MONITOR with no verdict authority: under a true
null it fires 47.8% of the time at n=40 (PREREG_P1 §H1).
"""
import argparse
import collections
import json
import math
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from funnel import gates                                               # noqa: E402

GATE_SHARPE, GATE_FITNESS = 1.58, 1.0
GATE_TO_LO, GATE_TO_HI = 0.01, 0.7

# The three refusals of HARNESS_SOP.md, as live constants. They are read at RUNTIME by the code
# below, so a test that sets them to 0 changes the output — the point of `tools/tests/
# test_layered_report.py`, after three separate guard tests passed while only grepping this file
# for strings.
MIN_JUDGEABLE_PER_ARM = 20          # fewer per side -> NO VERDICT
MIN_SCREEN_PASSERS = 10             # fewer in total -> no rate comparison
Z = 1.96

#: Six factors since round 3. E and W were added because round 3 measured two differences no
#: POOL change can reach: 83.3% of clean historical alphas wrap the whole ensemble in one
#: normaliser (0 of ours did), and the clean corpus's defining property is a leaf FREQUENCY
#: (carrier 0.863 there; 0.003 under a uniform draw from either pool). A factor missing from
#: this list is a factor the report silently never analyses.
FACTORS = ("D", "C", "U", "S", "E", "W")
FACTOR_DESC = {
    "D": "layer-D field screen (coverage/variation/meaning)",
    "C": "layer-C market gate (trade_when / if_else)",
    "U": "per-operator unit model",
    "S": "ordered-stage rule REMOVED",
    "E": "one normaliser wraps the WHOLE ensemble (83.3% of clean historical alphas do; 0 of ours"
         " did, because the join line had nothing after it -- no pool change can produce it)",
    "W": "layer C drawn FREQUENCY-WEIGHTED from the clean corpus instead of uniformly (measured:"
         " carrier 0.003 uniform vs 0.637 weighted; the clean corpus's defining property is a"
         " frequency, so a uniform vocabulary swap changes nothing)",
}
# Legacy single-arm vocabularies. The baseline corpus carries {ordered,free} and round 1 carries
# {units,control}; both are single factors of the 2^4, so they pool by factor instead of colliding
# as four "arms" (INTEGRATION_P1R1 S9).
LEGACY_ARM = {"units": ("U", 1), "control": ("U", 0),
              "free": ("S", 1), "ordered": ("S", 0)}

METRICS = ("sharpe", "fitness", "turnover", "|returns|")

# fitness = sharpe * sqrt(|returns| / max(turnover, 0.125)), verified exact on 69,659 rows.
# fitness >= 1.0 at sharpe 1.58 therefore needs |returns| >= 0.4006 * max(turnover, 0.125), whose
# floor is 0.4006 * 0.125 = 5.01%. A factor that moves sharpe and not |returns| cannot open the
# fitness gate; that is arithmetic, not a mechanism.
FITNESS_RETURNS_FLOOR = 0.0501
# Pre-declared, not chosen after seeing the data: 0.125 is the fitness denominator's floor, 0.70
# the gate's upper turnover bound, 0.30 the midpoint of the admissible band.
TURNOVER_BANDS = ((0.0, 0.125), (0.125, 0.30), (0.30, 0.70), (0.70, float("inf")))
HL_PAIR_CAP = 4_000_000


def load(path):
    rows = []
    for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def wilson(k, n, z=Z):
    """A rate with a 95% interval. A bare percentage over 7 rows is not a measurement."""
    if not n:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def screened(r):
    s, f, t = r.get("sharpe"), r.get("fitness"), r.get("turnover")
    if not all(isinstance(v, (int, float)) for v in (s, f, t)):
        return None                                  # unjudgeable: neither a pass nor a fail
    return s > GATE_SHARPE and f > GATE_FITNESS and GATE_TO_LO < t < GATE_TO_HI


def is_gem(r):
    if not r.get("checks"):
        return None
    passed, _failed, missing = gates.zero_fail(r)
    return None if missing else bool(passed)


def metric(r, name):
    """One metric off a row, or None if it is not numeric. `|returns|` is the fitness identity's
    quantity, so it is a first-class metric here rather than something to be inferred."""
    v = r.get("returns") if name == "|returns|" else r.get(name)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return abs(v) if name == "|returns|" else v


def _level(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return 1 if v else 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "on", "true", "yes"):
            return 1
        if s in ("0", "off", "false", "no"):
            return 0
    return None


def cell_of(r):
    """Factor levels for one row, from whichever of the three shapes the producer wrote.

    1. `meta['factors'] = {"D":1,"C":0,...}`   preferred
    2. `meta['cell'] = "D1C0U1S1"`             any order, case-insensitive
    3. `meta['arm']` in the legacy vocabularies, which each name ONE factor

    A factor absent from all three is UNKNOWN for that row and the row is excluded from that
    factor's contrast only — never from the other three. That is what makes a pooled read of two
    corpora with different arm vocabularies legal.
    """
    m = r.get("meta") or {}
    out = {}
    f = m.get("factors")
    if isinstance(f, dict):
        for k, v in f.items():
            k = str(k).strip().upper()
            lv = _level(v)
            if k in FACTORS and lv is not None:
                out[k] = lv
    cell = m.get("cell")
    if isinstance(cell, str):
        # The class is built from FACTORS, so adding a factor cannot leave the parser silently
        # blind to it -- a hardcoded [DCUS] would have read E and W as absent on every row.
        for k, v in re.findall(r"([%s])\s*([01])" % "".join(FACTORS), cell.upper()):
            out.setdefault(k, int(v))
    arm = m.get("arm")
    if isinstance(arm, str) and arm.strip().lower() in LEGACY_ARM:
        k, v = LEGACY_ARM[arm.strip().lower()]
        out.setdefault(k, v)
    return out


# ---- statistics ---------------------------------------------------------------------------
# scipy is not imported. These are re-derived here so the report runs anywhere, and
# `test_layered_report.py` checks both against scipy when scipy is installed (RULE 0 §5: derive it
# a second way before reporting it).

def mannwhitney(xs, ys):
    """Two-sided Mann-Whitney U, normal approximation with tie and continuity correction.

    A test of DOMINANCE, not means and not medians. `wilcoxon-is-not-a-mean-test` records that on
    skewed payoffs every random control passes a rank test read as a mean test.
    """
    n1, n2 = len(xs), len(ys)
    if not n1 or not n2:
        return (float("nan"), float("nan"))
    allv = sorted([(v, 0) for v in xs] + [(v, 1) for v in ys])
    ranks = [0.0] * len(allv)
    ties = 0.0
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        rk = (i + j) / 2.0 + 1.0
        t = j - i + 1
        ties += t ** 3 - t
        for q in range(i, j + 1):
            ranks[q] = rk
        i = j + 1
    r1 = sum(rk for rk, (_v, g) in zip(ranks, allv) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    n = n1 + n2
    mu = n1 * n2 / 2.0
    var = n1 * n2 / 12.0 * ((n + 1) - ties / (n * (n - 1.0))) if n > 1 else 0.0
    if var <= 0:
        return (u1, 1.0)
    z = (abs(u1 - mu) - 0.5) / math.sqrt(var)
    z = max(z, 0.0)
    return (u1, math.erfc(z / math.sqrt(2)))


def hl_shift(xs, ys, rng_seed=0):
    """Hodges-Lehmann shift ON-OFF (median of pairwise differences) with a distribution-free
    rank-based 95% CI. Not a bootstrap: the CI is read off the sorted pairwise differences at the
    index the Mann-Whitney null puts there, which needs one sort instead of 2,000 refits."""
    n, m = len(xs), len(ys)
    if not n or not m:
        return None
    note = ""
    if n * m > HL_PAIR_CAP:
        cap = int(math.sqrt(HL_PAIR_CAP))
        rng = random.Random(rng_seed)
        xs = rng.sample(list(xs), min(n, cap))
        ys = rng.sample(list(ys), min(m, cap))
        n, m = len(xs), len(ys)
        note = " (seeded %dx%d subsample)" % (n, m)
    d = sorted(x - y for x in xs for y in ys)
    nm = n * m
    shift = d[nm // 2] if nm % 2 else (d[nm // 2 - 1] + d[nm // 2]) / 2.0
    k = nm / 2.0 - Z * math.sqrt(nm * (n + m + 1) / 12.0)
    ki = int(math.floor(k))
    if ki < 0 or ki >= nm // 2:
        return (shift, d[0], d[-1], note + " (CI wider than the observed pairs)")
    return (shift, d[ki], d[nm - 1 - ki], note)


def holm(pvals):
    """Holm-Bonferroni step-down adjusted p-values, monotone by construction."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    adj = [1.0] * len(pvals)
    running = 0.0
    for rank, i in enumerate(idx):
        running = max(running, min(1.0, (len(pvals) - rank) * pvals[i]))
        adj[i] = running
    return adj


def med(vs):
    v = sorted(vs)
    return v[len(v) // 2] if v else None


def by(rows, keyfn, label, out):
    """Rate table for one structural axis, with denominators and intervals, never a bare ranking."""
    buckets = collections.defaultdict(lambda: [0, 0, 0])   # n, screened, gems
    for r in rows:
        k = keyfn(r)
        if k is None:
            continue
        b = buckets[k]
        b[0] += 1
        if screened(r):
            b[1] += 1
        if is_gem(r):
            b[2] += 1
    if not buckets:
        return
    total_pos = sum(b[1] for b in buckets.values())
    out("\n  %s" % label)
    if total_pos < 5:
        out("    %d screen-passers across %d buckets -- TOO FEW TO SEPARATE. Counts only, no ranking."
            % (total_pos, len(buckets)))
    for k in sorted(buckets, key=lambda x: (-buckets[x][1], str(x))):
        n, sc, gm = buckets[k]
        p, lo, hi = wilson(sc, n)
        out("    %-24s n=%-5d screen=%-4d %5.1f%% [%4.1f-%4.1f]  gems=%d"
            % (str(k), n, sc, 100 * p, 100 * lo, 100 * hi, gm))


# ---- the factorial ------------------------------------------------------------------------

def split(rows, f):
    """(ON rows, OFF rows, UNKNOWN count) for one factor, and the blocks that identify it."""
    on, off, unknown = [], [], 0
    for r in rows:
        lv = cell_of(r).get(f)
        if lv is None:
            unknown += 1
        elif lv:
            on.append(r)
        else:
            off.append(r)
    return on, off, unknown


def identifying_blocks(rows, f):
    """Blocks holding BOTH levels of f. A factor identified in no single block is confounded with
    whatever differs between blocks, and HARNESS_SOP.md forbids that comparison outright."""
    seen = collections.defaultdict(set)
    for r in rows:
        lv = cell_of(r).get(f)
        if lv is not None:
            seen[r["_block"]].add(lv)
    return sorted(b for b, lv in seen.items() if len(lv) == 2)


def contrast(on, off, name):
    """One metric, one factor. Returns None when either side is below the refusal floor."""
    xs = [v for v in (metric(r, name) for r in on) if v is not None]
    ys = [v for v in (metric(r, name) for r in off) if v is not None]
    d = {"metric": name, "n_on": len(xs), "n_off": len(ys),
         "med_on": med(xs), "med_off": med(ys), "p": None, "hl": None}
    if min(len(xs), len(ys)) < MIN_JUDGEABLE_PER_ARM:
        return d
    _u, p = mannwhitney(xs, ys)
    d["p"] = p
    d["hl"] = hl_shift(xs, ys)
    return d


def factorial(rows, out):
    """Four main effects x four metrics. Every row enters four comparisons, which is exactly what
    makes the factorial free (PREREG_P1 §3.2)."""
    out("\n=== MAIN-EFFECT CONTRASTS — balanced 2^4, pooled ON vs OFF, every row in all four ===")
    cells = collections.Counter(
        "".join("%s%d" % (f, cell_of(r)[f]) for f in FACTORS if f in cell_of(r)) or "(none)"
        for r in rows)
    out("  cells present: %d  %s" % (len(cells), dict(cells.most_common(8))))

    results, tests = {}, []
    for f in FACTORS:
        on, off, unk = split(rows, f)
        blocks = identifying_blocks(rows, f)
        rec = {"on": on, "off": off, "unknown": unk, "blocks": blocks, "rows": {}, "dropped": 0}
        if blocks:
            keep = set(blocks)
            on2 = [r for r in on if r["_block"] in keep]
            off2 = [r for r in off if r["_block"] in keep]
            rec["dropped"] = (len(on) - len(on2)) + (len(off) - len(off2))
            on, off = on2, off2
            rec["on"], rec["off"] = on, off
        for name in METRICS:
            c = contrast(on, off, name)
            rec["rows"][name] = c
            if c["p"] is not None and blocks:
                tests.append((f, name, c["p"]))
        results[f] = rec

    adj16 = holm([p for _f, _m, p in tests]) if tests else []
    adj4 = {}
    for name in METRICS:
        fam = [(i, p) for i, (_f, m_, p) in enumerate(tests) if m_ == name]
        if fam:
            for (i, _p), a in zip(fam, holm([p for _i, p in fam])):
                adj4[i] = a
    holm16 = {(f, m_): adj16[i] for i, (f, m_, _p) in enumerate(tests)}
    holm4 = {(f, m_): adj4[i] for i, (f, m_, _p) in enumerate(tests)}

    out("  MULTIPLICITY: 4 factors x 4 metrics = 16 tests. Holm-Bonferroni over the family of 16 is"
        " applied (p_h16);")
    out("    PREREG_P1 §6.7 specifies Holm within each endpoint across the 4 factors, which is"
        " strictly less conservative; it is")
    out("    reported as p_h4 so the two are not confused. %d of 16 tests were computable."
        % len(tests))
    out("  fitness >= %.1f at sharpe %.2f needs |returns| >= %.2f%% (identity floor at turnover"
        " %.3f)." % (GATE_FITNESS, GATE_SHARPE, 100 * FITNESS_RETURNS_FLOOR, 0.125))

    for f in FACTORS:
        rec = results[f]
        on, off, blocks = rec["on"], rec["off"], rec["blocks"]
        out("\n  FACTOR %s — %s" % (f, FACTOR_DESC[f]))
        out("    rows ON=%d OFF=%d  level-UNKNOWN=%d (excluded from %s only)"
            % (len(on), len(off), rec["unknown"], f))
        if not on and not off:
            out("    NOT ASSIGNED in this corpus -- no contrast. (An unassigned factor is not a"
                " null result.)")
            continue
        if not blocks:
            out("    NO VERDICT: IDENTIFIED ONLY BETWEEN BLOCKS. No single batch holds both levels,"
                " so the contrast is")
            out("      confounded with time of day, regime and quota state -- the before/after"
                " comparison HARNESS_SOP.md forbids.")
            continue
        out("    identifying blocks (both levels present): %s%s"
            % (", ".join(blocks),
               "   [%d rows dropped: they sit in blocks holding only one level]" % rec["dropped"]
               if rec["dropped"] else ""))
        out("    %-10s %6s %6s %9s %9s %11s %-21s %8s %8s %8s"
            % ("metric", "n_ON", "n_OFF", "med_ON", "med_OFF", "HL(ON-OFF)", "95% CI",
               "p_raw", "p_h16", "p_h4"))
        for name in METRICS:
            c = rec["rows"][name]
            if c["p"] is None:
                out("    %-10s %6d %6d %9s %9s   NO VERDICT: need >= %d judgeable rows per arm"
                    % (name, c["n_on"], c["n_off"],
                       "%.4f" % c["med_on"] if c["med_on"] is not None else "-",
                       "%.4f" % c["med_off"] if c["med_off"] is not None else "-",
                       MIN_JUDGEABLE_PER_ARM))
                continue
            sh, lo, hi, note = c["hl"]
            out("    %-10s %6d %6d %9.4f %9.4f %11.4f [%8.4f,%8.4f] %8.4f %8.4f %8.4f%s"
                % (name, c["n_on"], c["n_off"], c["med_on"], c["med_off"], sh, lo, hi,
                   c["p"], holm16[(f, name)], holm4[(f, name)], note))
        out("      Mann-Whitney p above is DOMINANCE, not means. HL is a shift with a"
            " distribution-free CI.")

        # The fitness gate cannot open on sharpe alone. Print the arithmetic rather than leaving it
        # to be inferred.
        ron = med([v for v in (metric(r, "|returns|") for r in on) if v is not None])
        roff = med([v for v in (metric(r, "|returns|") for r in off) if v is not None])
        if ron is not None and roff is not None:
            verdict = ("BOTH CLEAR" if min(ron, roff) >= FITNESS_RETURNS_FLOOR else
                       "ON CLEARS, OFF DOES NOT" if ron >= FITNESS_RETURNS_FLOOR else
                       "OFF CLEARS, ON DOES NOT" if roff >= FITNESS_RETURNS_FLOOR else
                       "NEITHER ARM CLEARS -- a sharpe move here cannot open the fitness gate")
            out("      med|returns| ON=%.4f OFF=%.4f vs the %.4f floor: %s"
                % (ron, roff, FITNESS_RETURNS_FLOOR, verdict))

        # Screen rate, with the SOP's second refusal.
        jon = [r for r in on if screened(r) is not None]
        joff = [r for r in off if screened(r) is not None]
        ka = sum(1 for r in jon if screened(r))
        kb = sum(1 for r in joff if screened(r))
        if ka + kb >= MIN_SCREEN_PASSERS and jon and joff:
            pa, pb = ka / len(jon), kb / len(joff)
            out("      screen rate ON %d/%d=%.2f%% vs OFF %d/%d=%.2f%%  difference %.2f pp"
                % (ka, len(jon), 100 * pa, kb, len(joff), 100 * pb, 100 * (pa - pb)))
        else:
            out("      screen-passers %d+%d -- TOO FEW to compare rates (need %d); metrics only."
                % (ka, kb, MIN_SCREEN_PASSERS))

        # Sign stability across blocks: PREREG §4.2 requires the sign not to reverse between blocks.
        if len(blocks) > 1:
            signs = []
            for b in blocks:
                xs = [v for v in (metric(r, "sharpe") for r in on if r["_block"] == b) if v is not None]
                ys = [v for v in (metric(r, "sharpe") for r in off if r["_block"] == b) if v is not None]
                h = hl_shift(xs, ys) if xs and ys else None
                signs.append((b, None if h is None else h[0]))
            txt = "  ".join("%s=%s" % (b, "-" if s is None else "%+.3f" % s) for b, s in signs)
            got = {s > 0 for _b, s in signs if s is not None and s != 0}
            out("      per-block HL on sharpe: %s%s"
                % (txt, "   SIGN REVERSED ACROSS BLOCKS -> NO VERDICT (PREREG §4.2)"
                   if len(got) > 1 else ""))
    return results


def c_turnover_confound(results, out):
    """`trade_when` is DOCUMENTED as cutting turnover, so a gate can raise fitness by shrinking the
    fitness denominator with no signal improvement at all. The C contrast on fitness is therefore
    reported pooled WITHIN turnover bands, or it has no verdict."""
    rec = results.get("C")
    out("\n=== C x TURNOVER — the confound, stated before the conclusion (RULE 0 §6) ===")
    out("  EX-ANTE, from documentation, not from this data: fetched/community_alpha_tips.md:99-100")
    out('    "Wrap the signal in trade_when ... tightening conditions reduces turnover."')
    out("  fitness = sharpe * sqrt(|returns| / max(turnover, 0.125)): cutting turnover raises"
        " fitness with the signal unchanged.")
    if not rec or not rec["blocks"] or not rec["on"] or not rec["off"]:
        out("  C is not identified within a block in this corpus -- nothing to pool. NO VERDICT.")
        return
    tc = rec["rows"]["turnover"]
    if tc["p"] is not None:
        out("  C on TURNOVER: HL %+.4f [%.4f,%.4f] p=%.4f  (the confound's own size)"
            % (tc["hl"][0], tc["hl"][1], tc["hl"][2], tc["p"]))
    fc = rec["rows"]["fitness"]
    if fc["p"] is not None:
        out("  C on FITNESS, RAW POOLED: HL %+.4f [%.4f,%.4f] p=%.4f"
            % (fc["hl"][0], fc["hl"][1], fc["hl"][2], fc["p"]))
    out("    ^ RAW, NOT A VERDICT: it mixes the turnover channel with any signal change.")
    out("  C on FITNESS, pooled WITHIN turnover band:")
    any_band = False
    for lo, hi in TURNOVER_BANDS:
        inb = lambda r: (lambda t: t is not None and lo <= t < hi)(metric(r, "turnover"))  # noqa: E731
        on = [r for r in rec["on"] if inb(r)]
        off = [r for r in rec["off"] if inb(r)]
        c = contrast(on, off, "fitness")
        tag = "[%.3f,%s)" % (lo, "inf" if hi == float("inf") else "%.3f" % hi)
        if c["p"] is None:
            out("    band %-16s n_ON=%-4d n_OFF=%-4d  NO VERDICT: need >= %d judgeable rows per arm"
                % (tag, c["n_on"], c["n_off"], MIN_JUDGEABLE_PER_ARM))
            continue
        any_band = True
        out("    band %-16s n_ON=%-4d n_OFF=%-4d  HL %+.4f [%.4f,%.4f]  p=%.4f (DOMINANCE)"
            % (tag, c["n_on"], c["n_off"], c["hl"][0], c["hl"][1], c["hl"][2], c["p"]))
    if not any_band:
        out("  C ON FITNESS: NO VERDICT — not poolable within turnover band at this n. The raw"
            " contrast above is confounded")
        out("    with turnover by construction and MECHANISM IS UNKNOWN: signal improvement and"
            " denominator shrinkage both fit.")


def monitor_round_over_round(blocks, out):
    """Prints. Never decides."""
    out("\n=== ROUND-OVER-ROUND MEDIAN — MONITOR ONLY, NO VERDICT AUTHORITY ===")
    out("  Under a true null (no change at all) 'median improved' fires 47.8% of the time at n=40"
        " (PREREG_P1 §H1),")
    out("  and it is the before/after shape HARNESS_SOP.md forbids. Reported for drift, never used"
        " to confirm or revert.")
    prev = None
    for name, rows in blocks:
        vs = [v for v in (metric(r, "sharpe") for r in rows) if v is not None]
        m = med(vs)
        d = "" if (prev is None or m is None) else "   delta %+.4f vs previous block" % (m - prev)
        out("  %-28s n=%-5d median sharpe %s%s"
            % (name, len(vs), "-" if m is None else "%.4f" % m, d))
        if m is not None:
            prev = m


def report(blocks, out=print):
    """blocks: list of (block_label, rows). One block = one batch/round."""
    term = []
    for name, rows in blocks:
        for r in rows:
            if r.get("status") in ("COMPLETE", "WARNING"):
                r["_block"] = name
                term.append(r)
    allrows = [r for _n, rows in blocks for r in rows]
    st = collections.Counter(r.get("status") for r in allrows)
    judged = [r for r in term if screened(r) is not None]
    sc = [r for r in judged if screened(r)]
    gems = [r for r in term if is_gem(r)]

    out("rows %d  %s" % (len(allrows), dict(st.most_common())))
    out("blocks %d: %s" % (len(blocks), ", ".join("%s(%d)" % (n, len(r)) for n, r in blocks)))
    out("terminal %d | judgeable %d | screen-passers %d | gems %d"
        % (len(term), len(judged), len(sc), len(gems)))
    if judged:
        p, lo, hi = wilson(len(sc), len(judged))
        out("screen rate %.2f%%  95%% CI [%.2f, %.2f]" % (100 * p, 100 * lo, 100 * hi))

    vals = sorted(v for v in (metric(r, "sharpe") for r in term) if v is not None)
    if vals:
        out("sharpe  median %.3f  p90 %.3f  max %.3f  (n=%d)"
            % (vals[len(vals) // 2], vals[int(0.9 * len(vals))], vals[-1], len(vals)))

    # UNIT WARNINGS, counted rather than eyeballed. `unitHandling: VERIFY` does not block a result,
    # but a message like
    #     Incompatible unit for input of "add" at index 1, expected "Unit[]", found "Unit[CSPrice:1]"
    # says the platform saw a price-unit leg added to a unitless one -- adding apples to metres. It
    # is a direct consequence of drawing the outer operator at random: `rank(x)` is unitless while
    # `ts_mean(close, 20)` still carries price.
    msgs = [r for r in term if (r.get("message") or "").strip()]
    unit = [r for r in msgs if "Incompatible unit" in r["message"]]
    if term:
        pu, lou, hiu = wilson(len(unit), len(term))
        out("\nunit-incompatibility warnings: %d/%d = %.1f%% [%.1f-%.1f]"
            % (len(unit), len(term), 100 * pu, 100 * lou, 100 * hiu))
        heads = collections.Counter()
        for r in unit:
            t = r["message"]
            i = t.find('input of "')
            heads[t[i + 10:t.find('"', i + 10)] if i >= 0 else "?"] += 1
        for k, v in heads.most_common(6):
            out("    at operator %-14s %d" % (k, v))
        other = collections.Counter(
            (r["message"].split(".")[0])[:70] for r in msgs if r not in unit)
        for k, v in other.most_common(4):
            out("    other message  %-58s %d" % (k, v))

    results = factorial(term, out)
    c_turnover_confound(results, out)
    monitor_round_over_round([(n, [r for r in rows if r.get("status") in ("COMPLETE", "WARNING")])
                              for n, rows in blocks], out)

    m = lambda r: (r.get("meta") or {})                                # noqa: E731

    # THE SETTINGS AXIS, which is NOT one of the four factors: this generator screens 0/129 while
    # the older `resim` corpus screens 4,664/69,659 = 6.70%, and that corpus ran decay 6-14 with
    # STATISTICAL/INDUSTRY. `decay=0` + SUBINDUSTRY was reasoning, never measured.
    arms_s = collections.defaultdict(list)
    for r in term:
        if m(r).get("settings_arm"):
            arms_s[m(r)["settings_arm"]].append(r)
    if arms_s:
        out("\n  SETTINGS AXIS (descriptive; not a factor of the 2^4)")
        for k in sorted(arms_s):
            rs = arms_s[k]
            js = [x for x in rs if screened(x) is not None]
            sc_ = [x for x in js if screened(x)]
            p_, lo_, hi_ = wilson(len(sc_), len(js))
            out("    %-9s n=%-4d medSharpe=%-7s medFitness=%-7s med|returns|=%-8s screen=%d %4.1f%% [%.1f-%.1f]"
                % (k, len(rs),
                   "%.3f" % med([v for v in (metric(x, "sharpe") for x in rs) if v is not None])
                   if any(metric(x, "sharpe") is not None for x in rs) else "-",
                   "%.3f" % med([v for v in (metric(x, "fitness") for x in rs) if v is not None])
                   if any(metric(x, "fitness") is not None for x in rs) else "-",
                   "%.4f" % med([v for v in (metric(x, "|returns|") for x in rs) if v is not None])
                   if any(metric(x, "|returns|") is not None for x in rs) else "-",
                   len(sc_), 100 * p_, 100 * lo_, 100 * hi_))
        if min(len(v) for v in arms_s.values()) < MIN_JUDGEABLE_PER_ARM:
            out("    NO VERDICT: fewer than %d rows in some arm." % MIN_JUDGEABLE_PER_ARM)

    by(term, lambda r: m(r).get("arm"), "by LEGACY ARM LABEL", out)
    by(term, lambda r: m(r).get("settings_arm"), "by SETTINGS ARM", out)
    by(term, lambda r: m(r).get("n_legs"), "by LEG COUNT (layer A combination size)", out)
    by(term, lambda r: len((m(r).get("legs") or [{}])[0].get("inner") or []),
       "by DEPTH of the first leg's layer-B chain", out)
    by(term, lambda r: m(r).get("carrier"), "by CARRIER present", out)
    by(term, lambda r: (m(r).get("legs") or [{}])[0].get("leaf_kind"),
       "by LEAF KIND (raw field vs economic ratio)", out)
    by(term, lambda r: (m(r).get("legs") or [{}])[0].get("outer"),
       "by OUTER operator of the first leg", out)

    if gems:
        out("\n  GEMS")
        for r in gems:
            out("    %s legs=%s carrier=%s sharpe=%s fitness=%s"
                % (r.get("alpha"), m(r).get("n_legs"), m(r).get("carrier"),
                   r.get("sharpe"), r.get("fitness")))
            out("      %s" % (r.get("formula") or "")[:220])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("journal", nargs="+",
                    help="one or more run journals; each is one block (round/batch)")
    args = ap.parse_args()
    blocks = []
    for p in args.journal:
        rows = load(p)
        for r in rows:
            b = (r.get("meta") or {}).get("round")
            r["_block_hint"] = b
        hints = {r.get("_block_hint") for r in rows}
        if len(hints) > 1 or (hints and None not in hints):
            for h in sorted(x for x in hints if x is not None):
                blocks.append((str(h), [r for r in rows if r.get("_block_hint") == h]))
            rest = [r for r in rows if r.get("_block_hint") is None]
            if rest:
                blocks.append((pathlib.Path(p).stem, rest))
        else:
            blocks.append((pathlib.Path(p).stem, rows))
    report(blocks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
