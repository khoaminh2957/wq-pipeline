"""forge.gen.posterior -- what the loop learns from and how (docs/evalharness/04_passfirst_design.md §3.1-3.2).

THE REWARD (D34, Khoa 2026-09-23 ~17:20, Q2 option a): y = 1 when a row's Sharpe is at least 0.8 x ITS OWN
LOW_SHARPE limit, read from the row's check set; y = 0 otherwise. The reward depends on the row alone, so
the same row can never earn 1 and later 0 (§3.1: the drafts' family-aware reward drifted by its own
definition, RULE 0 audit A3). A row with no numeric LOW_SHARPE limit or no numeric Sharpe (ERROR, still
pending) is not an observation and updates nothing -- it is neither a 1 nor a 0.

HARVEST-PASS IS A DIFFERENT THING, KEPT APART (§0). `harvest_pass` = `score.platform_verdict` reads pass:
every check outside score.NON_BINDING is PASS, which includes UNITS, LOW_2Y_SHARPE, the regional lines and
D0_SUBMISSION. It is what the spending rules (PASSED_BLOCK), the repair trigger (D37) and the D51
neighbours key on. §7 stage 2's test text says "a UNITS-warned row that clears the 7 checks gives y = 0";
that text was written while Q2 was open and describes y = harvest-pass (Q2 c; under (b), "at most one
binding check fails", the same row reads 1 -- re-read in §8 on 2026-09-24, the spec auditor's reading). Under
D34 as ticked, y reads the Sharpe line only, so such a row is y = 1 when its Sharpe clears 0.8 x the line
and it is NOT a harvest-pass; forge/tests/test_gen_posterior.py pins both halves.

A LIMIT ON d0 (draw-5 gen N7, EX-ANTE from score.platform_verdict plus a journal count). D0_SUBMISSION is
not in score.NON_BINDING, so a PENDING reading makes a row "incomplete", never a pass; on the Mac journal
copy it reads PENDING on all 1,637 distinct alphas that carry it, all of them delay 0 (re-derived 2026-09-24,
two ways agreeing; 1,647 of the lines, the adjudicator's unit). So on d0 harvest-pass, the D37 trigger
(which needs nothing pending) and the D51 neighbours cannot fire, and PASSED_BLOCK never starts. No live
effect while the loop runs `--delays 1`. Whether PENDING should block harvest-pass on d0 is Khoa's call.

THE UPDATE (§3.2). One Beta posterior per level of each production in productions.PRODUCTIONS and one per
dataset: alpha = 1 + sum(y), beta = 1 + sum(1 - y) over the rows that USED the level (a row counts once per
level, however many of its legs used it). Beta(1, 1) is D35's uniform start ("priors start uniform ...
read as the design's option (b)"), not the library counts of §2.3. Recomputed from the journal every round
(the state rule of §3.2), which is the "once per round after harvest" update without a state file.
No discounting (§3.2: the within-cell rate fell 11-fold across 09-11 for reasons unknown; nothing here
assumes stationarity, and nothing corrects for its absence either).

Every generated row counts, whatever route made it (fresh -- posterior or floor --, D37 repair, D51
neighbour): §3.2 says "over the rows that used the level". A repair or neighbour row re-uses its base row's
structure, and draws, repairs and neighbours all take their settings from the same 3 x 2 x 2 SETTINGS
levels, so one structure is observed at most 12 times per (formula, region, delay, universe) (draw-5 gen
N6: this read "1 + 11 + 2", which double-counts the neighbours inside the grid). That weighting follows from
the text and is named here, not measured.

ONE ROUND'S WEIGHTS. Each level's weight is theta ~ Beta(alpha, beta), drawn ONCE per round from the round's
seeded rng -- the rule §3.2 states for datasets ("theta_d drawn once per round"), applied to the structure
levels too, because the design names no other draw rule for them (a choice, stated). A floor draw ignores
all of it: uniform over every level, TIER_U included, and dataset multiplier 1 (D35, §3.2).
"""
from __future__ import annotations

from forge import score as SC
from forge.gen import productions as P

#: D34: the share of the row's own LOW_SHARPE limit at which y turns 1.
Y_FRACTION = 0.8


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x


def y(row) -> int | None:
    """D34's reward for one journal row: 1, 0, or None (not an observation). The comparison is made at
    10 decimals: 0.8 x 1.58 is 1.2640000000000002 in binary floating point, and the platform reports Sharpe
    to 2 decimals, so a row AT the line must read 1."""
    ck = SC.checks(row).get("LOW_SHARPE") or {}
    limit = ck.get("limit")
    sharpe = row.get("sharpe") if _num(row.get("sharpe")) else ck.get("value")
    if not _num(limit) or not _num(sharpe):
        return None
    return 1 if round(float(sharpe), 10) >= round(Y_FRACTION * float(limit), 10) else 0


def harvest_pass(row) -> bool:
    """§0's harvest-pass: `score.platform_verdict` reads pass (a WARNING on any binding check, UNITS
    included, is not a pass)."""
    return SC.platform_verdict(row)[0] == "pass"


def is_generated(row) -> bool:
    """A row this generator made: its hypothesis is a `gen:<family>` key (D38, §3.3)."""
    return str((row.get("meta") or {}).get("hypothesis") or "").startswith("gen:")


def _key(prod, level) -> str:
    return "%s=%s" % (prod, level)


def levels_used(row) -> set:
    """{"PROD=level"} for every production level the row used: its ALPHA shape, each leg's SIG / TS /
    TIER_U / SCORE / G / windows, and its settings. Only levels of the grammar count; anything else is
    ignored rather than invented."""
    m = row.get("meta") or {}
    out = set()
    if m.get("gen_alpha") in P.ALPHA:
        out.add(_key("ALPHA", m["gen_alpha"]))
    for leg in m.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        if leg.get("sig") in P.SIG:
            out.add(_key("SIG", leg["sig"]))
        if leg.get("ts") in P.TS or leg.get("ts") == P.TS_TIER_U:
            out.add(_key("TS", leg["ts"]))
        if leg.get("tier_u") in P.TIER_U:
            out.add(_key("TIER_U", leg["tier_u"]))
        if leg.get("score") in P.SCORE:
            out.add(_key("SCORE", leg["score"]))
        if leg.get("group") in P.GROUPS:
            out.add(_key("G", leg["group"]))
        for w in leg.get("windows") or []:
            if isinstance(w, (list, tuple)) and len(w) == 2 and w[0] in ("W_SHORT", "W_LONG", "W_EVENT") \
                    and _num(w[1]) and int(w[1]) in P.PRODUCTIONS[w[0]]:
                out.add(_key(w[0], int(w[1])))
    s = row.get("settings") or {}
    if s.get("neutralization") in P.NEUT:
        out.add(_key("NEUT", s["neutralization"]))
    if _num(s.get("decay")) and int(s["decay"]) in P.DECAY:
        out.add(_key("DECAY", int(s["decay"])))
    if _num(s.get("truncation")) and float(s["truncation"]) in P.TRUNC:
        out.add(_key("TRUNC", float(s["truncation"])))
    return out


def datasets_used(row) -> set:
    return {leg.get("dataset") for leg in ((row.get("meta") or {}).get("legs") or [])
            if isinstance(leg, dict) and leg.get("dataset")}


class Posterior:
    """Beta counts per level and per dataset, from generated journal rows. Pure."""

    def __init__(self, rows=()):
        self.levels, self.datasets = {}, {}
        self.n_rows, self.n_obs = 0, 0
        for r in (rows.values() if isinstance(rows, dict) else rows):
            if not is_generated(r):
                continue
            self.n_rows += 1
            v = y(r)
            if v is None:
                continue
            self.n_obs += 1
            for k in levels_used(r):
                a, b = self.levels.get(k, (1, 1))
                self.levels[k] = (a + v, b + 1 - v)
            for d in datasets_used(r):
                a, b = self.datasets.get(d, (1, 1))
                self.datasets[d] = (a + v, b + 1 - v)

    def level(self, prod, level) -> tuple:
        return self.levels.get(_key(prod, level), (1, 1))

    def dataset(self, ds) -> tuple:
        return self.datasets.get(ds, (1, 1))

    def as_json(self) -> dict:
        return {"levels": {k: list(v) for k, v in sorted(self.levels.items())},
                "datasets": {k: list(v) for k, v in sorted(self.datasets.items())}}


def round_weights(post: Posterior, rng, datasets) -> tuple:
    """(W, theta) for one round's posterior draws: theta ~ Beta(alpha, beta) per level of every production
    and per dataset in `datasets`, each drawn once, in a fixed order. TIER_U is left out: the floor is its
    only route (D35)."""
    W = {prod: {lv: rng.betavariate(*post.level(prod, lv)) for lv in levels} for prod, levels in P.PRODUCTIONS.items()}
    theta = {d: rng.betavariate(*post.dataset(d)) for d in sorted(datasets)}
    return W, theta


def floor_weights() -> tuple:
    """(W, None) for a floor draw: uniform over every level, TIER_U reachable as one TS alternative, base
    field weights (no dataset multiplier)."""
    W = {prod: {lv: 1.0 for lv in levels} for prod, levels in P.PRODUCTIONS.items()}
    W["TS"][P.TS_TIER_U] = 1.0
    return W, None
