"""Why does our generator screen 0% when the corpus screens 14%? A 2x2 that separates the causes.

THE GAP, restated with the right denominator. The number quoted all over this project is "the resim
corpus screens 6.70%". That is the POOLED figure over 69,659 scored rows. Only **11,729** of them
carry a formula AND settings, i.e. are replayable at all, and **that subset screens 14.16%** while
the unreplayable remainder screens 5.18%. So the gap our generator faces is against 14%, not 7%,
and the 2.7x spread INSIDE resim is itself a measurement of the selection candidate.

FOUR CANDIDATES were named for the gap and none has been tested: selection (resim is curated),
settings, grammar, field pool. This file tests the two that a batch can separate, by crossing them:

                          OUR settings              RESIM settings
                   (decay 0, SUBINDUSTRY,        (decay 10, INDUSTRY,
                    truncation 0.05)              truncation 0.02)
    OUR formulas       OF_OS                          OF_RS
    RESIM formulas     RF_OS                          RF_RS

  * `RF_RS` is the POSITIVE CONTROL and the reason this design can be trusted. It re-runs corpus
    formulas under corpus settings, so it must reproduce roughly 14%. If it does not, the replay
    itself is broken and NO other cell may be read.
  * `RF_OS` is the decisive cell. Corpus formulas under our settings: if the rate collapses,
    SETTINGS cause the gap. If it holds, settings are innocent and the cause is grammar or fields.
  * `OF_RS` is its mirror. Our formulas under corpus settings: if the rate rises, settings again;
    if it stays at zero, our LEAVES cannot produce a screener no matter how they are graded.

THE SKELETON IS HELD FIXED, and that is a deliberate narrowing made before the batch ran. 98.3% of
the replayable corpus is the single prefix `signed_power(zscore(ts_decay_linear(...`, which screens
14.33% while all 11 other prefixes in the corpus screen 0.00%. Our `era_b` framework already emits
that prefix and screened 0 of 49 in the first framework batch. So both formula arms use it, and what
varies is the LEAVES and PARAMETERS inside it -- ours against the corpus's.

SAMPLING IS UNCONDITIONAL, and this is the part that is easy to get wrong. Resim formulas are drawn
WITHOUT looking at their outcome. Sampling the screen-passers would guarantee a high RF_RS and prove
nothing but survivorship -- the same error that made "78% of POSTs are accepted" meaningless.

ASSIGNMENT IS WITHIN ONE BATCH, balanced across all four cells, so time of day, market regime and
quota state hit every cell equally.
"""

import argparse
import collections
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import frameworks as FW  # noqa: E402
import layered_alpha as LA  # noqa: E402

RESIM = ROOT / "state/resim_results.jsonl"

#: Our settings, and the corpus's. Only the three fields that actually differ are listed; everything
#: else comes from `layered_sim.SETTINGS` so the two profiles cannot drift apart in some fourth way.
#: TRUNCATION differs too (0.05 vs ~0.02) and had not been noticed before this file -- it rides along
#: with the settings factor and cannot be separated from it here. Stated, not hidden.
PROFILES = {
    "OS": {"decay": 0, "neutralization": "SUBINDUSTRY", "truncation": 0.05},
    "RS": {"decay": 10, "neutralization": "INDUSTRY", "truncation": 0.02},
}

CELLS = ("OF_OS", "OF_RS", "RF_OS", "RF_RS")

SCREEN = {"sharpe": 1.58, "fitness": 1.0, "turnover": (0.01, 0.7)}


def screened(sharpe, fitness, turnover):
    if not all(isinstance(x, (int, float)) for x in (sharpe, fitness, turnover)):
        return None
    lo, hi = SCREEN["turnover"]
    return sharpe > SCREEN["sharpe"] and fitness > SCREEN["fitness"] and lo < turnover < hi


def resim_pool(path=RESIM):
    """Every replayable corpus row: formula + settings present. Outcome is carried along for the
    baseline but is NEVER used to select."""
    out = []
    for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        f, st = r.get("formula"), r.get("settings")
        if f and st:
            out.append({"formula": f, "settings": st,
                        "screened": screened(r.get("sharpe"), r.get("fitness"),
                                             r.get("turnover"))})
    return out


def baseline(pool):
    ok = [r["screened"] for r in pool if r["screened"] is not None]
    return (sum(ok) / len(ok), len(ok)) if ok else (None, 0)


def draw(n, seed, path=RESIM):
    """`n` alphas, balanced across the four cells, each tagged with its cell.

    OUR FORMULAS COME FROM `era_b`, NOT `flat`, AND THE REASON CHANGES WHAT THIS EXPERIMENT IS.
    Measured on the replayable pool before any of this ran: **98.3% of it (11,622 of 11,825) is a
    single 3-level prefix**, `signed_power(zscore(ts_decay_linear(...`. There are 12 distinct
    prefixes in total. That one screens **14.33%**; every other prefix in the corpus screens
    **0.00%**.

    So "the corpus screens 14%" is really "one skeleton screens 14% and nothing else in the corpus
    screens at all". The corpus is not a population of structures -- it is one template with varying
    leaves and parameters. Drawing our arm from `flat` would have confounded SKELETON with LEAVES,
    and the skeleton is not the open question: `era_b` already reproduces that exact prefix, and in
    the first framework batch it screened 0 of 49.

    Holding the skeleton fixed at the corpus's own template turns this into the sharper experiment:
    OUR LEAVES AND PARAMETERS against THEIRS, crossed with the two settings profiles.
    """
    rng = random.Random(seed)
    pool = resim_pool(path)
    if not pool:
        raise SystemExit("no replayable corpus rows in %s" % path)

    ops = LA.load_operators()
    pool_a, pool_b, _dropped = LA.split_layers(ops)
    pool_c = LA.build_pool_c(LA.load_fields(), rng=random.Random(seed))

    cells, seen, out = [], set(), []
    while len(cells) < n:
        block = list(CELLS)
        rng.shuffle(block)
        cells.extend(block)
    for cell in cells[:n * 3]:
        if len(out) >= n:
            break
        src, prof = cell.split("_")
        if src == "RF":
            # UNCONDITIONAL draw -- the outcome is not consulted.
            row = pool[rng.randrange(len(pool))]
            formula = row["formula"]
            meta = {"cell": cell, "source": "resim", "n_legs": formula.count("+") + 1}
        else:
            formula, m = FW.build(FW.BY_NAME["era_b"], pool_a, pool_b, pool_c, rng)
            meta = dict(m)
            meta["cell"], meta["source"] = cell, "ours"
        if formula in seen:
            continue
        seen.add(formula)
        meta["profile"] = prof
        meta["carrier"] = meta.get("carrier_in_formula", LA.carrier_present(formula))
        out.append((formula, meta))
    return out


def settings_for(profile, base):
    st = dict(base)
    st.update(PROFILES[profile])
    return st


def summarise(rows):
    by = collections.defaultdict(list)
    for r in rows:
        cell = (r.get("meta") or {}).get("cell")
        if cell:
            by[cell].append(screened(r.get("sharpe"), r.get("fitness"), r.get("turnover")))
    out = {}
    for cell, vals in by.items():
        ok = [v for v in vals if v is not None]
        out[cell] = {"n": len(vals), "judged": len(ok),
                     "screen": (sum(ok) / len(ok)) if ok else None}
    return out


def verdict(stats, base_rate):
    lines = []
    rf_rs = stats.get("RF_RS")
    if not rf_rs or rf_rs["judged"] < 20:
        return ["NO VERDICT -- the RF_RS positive control has under 20 judged rows. Nothing else "
                "in this table may be read until the replay is shown to work."]
    got = rf_rs["screen"]
    if base_rate and got is not None and got < base_rate / 3:
        lines.append("REPLAY BROKEN -- RF_RS screens %.2f%% against a corpus baseline of %.2f%%. "
                     "The replay does not reproduce the corpus, so the other three cells are "
                     "uninterpretable. Fix this before reading anything else."
                     % (100 * got, 100 * base_rate))
        return lines
    lines.append("CONTROL OK -- RF_RS %.2f%% against corpus baseline %.2f%% (n=%d)"
                 % (100 * got, 100 * (base_rate or 0), rf_rs["judged"]))
    for a, b, msg in (
            ("RF_RS", "RF_OS", "SETTINGS: corpus formulas graded our way"),
            ("OF_OS", "OF_RS", "SETTINGS: our formulas graded the corpus way"),
            ("RF_OS", "OF_OS", "GRAMMAR: both graded our way"),
            ("RF_RS", "OF_RS", "GRAMMAR: both graded the corpus way")):
        x, y = stats.get(a), stats.get(b)
        if not x or not y or min(x["judged"], y["judged"]) < 20:
            lines.append("%-46s NO VERDICT (thin arm)" % msg)
            continue
        lines.append("%-46s %s %.2f%% vs %s %.2f%%"
                     % (msg, a, 100 * (x["screen"] or 0), b, 100 * (y["screen"] or 0)))
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--report", help="score a finished journal instead of drawing")
    a = ap.parse_args()

    pool = resim_pool()
    rate, n_base = baseline(pool)
    print("corpus: %d replayable rows, baseline screen %.2f%% (n=%d judged)"
          % (len(pool), 100 * (rate or 0), n_base))

    if a.report:
        rows = [json.loads(l) for l in pathlib.Path(a.report).read_text().splitlines()
                if l.startswith("{")]
        stats = summarise(rows)
        print("\n%-8s %6s %7s %9s" % ("cell", "n", "judged", "screen"))
        for c in CELLS:
            v = stats.get(c)
            print("%-8s %6s %7s %9s" % (c, v["n"] if v else 0, v["judged"] if v else 0,
                                        ("%.2f%%" % (100 * v["screen"])) if v and v["screen"]
                                        is not None else "--"))
        print()
        for line in verdict(stats, rate):
            print(line)
        return 0

    batch = draw(a.n, a.seed)
    print("drew %d: %s" % (len(batch),
                           dict(sorted(collections.Counter(m["cell"] for _, m in batch).items()))))
    for formula, m in batch[:4]:
        print("  %-6s %s" % (m["cell"], formula[:120]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
