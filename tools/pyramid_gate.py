#!/usr/bin/env python3
"""pyramid_gate.py — DECIDE whether an alpha's category advances an unlocked pyramid cell.

THIS MODULE NEVER SUBMITS. It contains no POST, no submit endpoint, no write to any platform
resource. It reads `GET /users/self/activities/pyramid-alphas` and returns a Decision object. The
POST is owned elsewhere (tools/submit_alphas.py). Keeping the decider POST-free is the point: a
submit is irreversible — one POST per alpha, and a 403 permanently spends that alpha's only
submission — so the thing that decides must be safe to run in a loop, in a test, or by mistake.

THE OPERATOR'S RULE (Khoa, 2026-08-13), verbatim:
    "nếu full thì ko nộp, nếu gần đủ như 2/3 hay 3/3 thì nộp luôn"
That sentence is literally self-contradictory: 3/3 IS full, so it is both the excluded case and an
included one. AMBIGUITY RECORDED, NOT RESOLVED SILENTLY. Both readings collapse onto the same
behaviour, which is what is implemented here:
    submit only into cells with alphaCount < UNLOCK_AT; priority to those nearest UNLOCK_AT;
    never into a cell at alphaCount >= UNLOCK_AT.
If Khoa ever means something else by "3/3", this docstring is the place the disagreement surfaces.

SCOPE: ONE region and ONE delay — USA, delay 1 (REGION/DELAY below). Every other (region, delay)
pair is a HARD REFUSAL, not a fallback. The endpoint returns all 211 cells across 16 pairs; the
scope is a deliberate narrowing by the operator, so widening it must be an edit, never an argument
a caller can slip past.

MEASURED, USA d1, 2026-08-13, from the live endpoint via the VPS session (211 rows, 16 pairs):
    Price Volume 40 | Model 19 | Fundamental 3 | Option 3 | Analyst 3 | Other 3
    Earnings 3 | Risk 3 | Institutions 3 | Macro 3 | News 2 | Insiders 2
    Sentiment 1 | Social Media 0 | Short Interest 0 | Imbalance 0
Six cells sit below 3; 13 alphas in total would unlock every one of them; News and Insiders each
need exactly ONE. Re-derived three ways and identical in all three: (a) the live payload above,
(b) state/pyramid_cell_counts.json written 2026-08-10 by harness13/crawl_pyramid.py, (c) the count
tools/health_report.py:cells_short() computes from that artifact. Three consecutive live reads six
seconds apart on 2026-08-13 were byte-identical to each other.

WHAT THIS MODULE DOES NOT ESTABLISH:
  - WHY a cell unlocks at 3. UNLOCK_AT = 3 is EX-ANTE, taken from the platform's own pyramid
    documentation and the project note pyramid-cell-ev-targeting. No experiment here tested it.
  - WHY the endpoint intermittently under-reported on 2026-08-02 (see MAX-OF-N below).
    MECHANISM: UNKNOWN.
  - Whether a submit into a 2/3 cell actually unlocks it. That is the platform's adjudication,
    observable only after a POST this module does not make.
"""

from __future__ import annotations

import json
import pathlib
import re
import time
from typing import NamedTuple, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------------------------- constants

REGION = "USA"          # the ONE configured region. Anything else is refused.
DELAY = 1               # the ONE configured delay.
UNLOCK_AT = 3           # EX-ANTE, from platform documentation: a pyramid cell unlocks at 3 alphas.

API = "https://api.worldquantbrain.com"
PYRAMID_PATH = "/users/self/activities/pyramid-alphas"

CACHE_PATH = ROOT / "state/pyramid_cell_counts.json"

# A count older than this makes every decision REFUSE. Value INHERITED from the 6-hour cache TTL
# already used by tools/submit_alphas.py:_cell_counts; it was not derived from any measurement of
# how fast cells actually fill. Treat the number itself as SPECULATION and the refusal as policy.
STALE_AFTER_S = 6 * 3600

# MAX-OF-N. POST-HOC, recorded in tools/submit_alphas.py from 2026-08-02: polling this endpoint
# seven times with no submission in between returned Analyst 3 / Earnings 2 / Price Volume 22 on
# six reads and Analyst 2 / Earnings 1 / Price Volume 18 on the seventh. MECHANISM: UNKNOWN. The
# two error directions are not symmetric, so the guard is not either: an UNDER-count says a full
# cell still needs alphas and lets an irreversible submit be spent on nothing, while an OVER-count
# only withholds a submit until the next read. Merge several reads by MAX; bias high.
# Three reads on 2026-08-13 agreed exactly — one clean observation does not retire the guard.
READS = 3
PAUSE_S = 6.0

# category id -> display name, as returned by the endpoint on 2026-08-13 (17 distinct categories
# across all 16 pairs; USA d1 carries 16 of them — "Broker" is not a USA d1 cell). Only "pv" is
# not recoverable from the name by normalisation, but the whole map is kept so a caller may pass
# either form. Membership in this map is NOT permission: a category must also be a live cell of
# the configured pair, or it is refused.
CATEGORY_IDS = {
    "analyst": "Analyst", "broker": "Broker", "earnings": "Earnings",
    "fundamental": "Fundamental", "imbalance": "Imbalance", "insiders": "Insiders",
    "institutions": "Institutions", "macro": "Macro", "model": "Model", "news": "News",
    "option": "Option", "other": "Other", "pv": "Price Volume", "risk": "Risk",
    "sentiment": "Sentiment", "shortinterest": "Short Interest", "socialmedia": "Social Media",
}

SUBMIT = "SUBMIT"
HOLD = "HOLD"


class PyramidPayloadError(ValueError):
    """The response could not be trusted. Never downgraded to a partial count."""


# ---------------------------------------------------------------------------------- result types

class CellNeed(NamedTuple):
    category: str
    count: int
    needs: int          # alphas still required to reach UNLOCK_AT


class CellState(NamedTuple):
    """What the counter said, how old it is, and where it came from. `counts` is None when nothing
    trustworthy was obtained — that is a refusal input, never an empty book of zeroes."""
    region: str
    delay: int
    counts: Optional[dict]
    ts: Optional[float]         # when the counts were observed (epoch seconds)
    age_s: Optional[float]      # how old they were when this state was built
    source: str                 # "live" | "cache" | "unavailable"
    reads: int
    error: Optional[str]

    def is_stale(self, max_age_s: float = STALE_AFTER_S) -> bool:
        """Unknown age counts as stale. Fail closed."""
        return self.age_s is None or self.age_s > max_age_s

    def marker(self, max_age_s: float = STALE_AFTER_S) -> str:
        """The loud staleness marker. A submit decision taken on a stale count is how a cell gets
        over-filled, so the age is never optional in the caller's view of this object."""
        if self.counts is None:
            return f"!! NO CELL DATA ({self.source}: {self.error or 'unknown'})"
        age = "age UNKNOWN" if self.age_s is None else f"{self.age_s / 60:.0f}min old"
        if self.is_stale(max_age_s):
            return (f"!! STALE {self.source} {age} (threshold {max_age_s / 60:.0f}min) "
                    f"— decisions REFUSE")
        return f"{self.source} {age}"


class Decision(NamedTuple):
    """SUBMIT or HOLD, and every number the reason rests on.

    Never a bare bool: a caller that cannot print WHY it is about to spend an irreversible submit
    is a caller that should not have one. `__bool__` raises for the same reason — `if decide(...)`
    would read HOLD as true and submit."""
    action: str
    reason: str
    category: Optional[str]
    count: Optional[int]
    needs: Optional[int]
    age_s: Optional[float]
    source: str
    stale: bool

    def __bool__(self):
        raise TypeError("Decision has no truth value; test `d.action == pyramid_gate.SUBMIT` "
                        "and print d.explain(). `if decide(...)` would submit on HOLD.")

    def explain(self) -> str:
        cnt = "?" if self.count is None else f"{self.count}/{UNLOCK_AT}"
        need = "?" if self.needs is None else str(self.needs)
        age = "age UNKNOWN" if self.age_s is None else f"{self.age_s / 60:.0f}min"
        return (f"{self.action}  {self.category or '<no category>'}  cell {cnt}  "
                f"needs {need} more  [{self.source}, {age}"
                f"{', STALE' if self.stale else ''}]  — {self.reason}")


def _hold(reason, *, category=None, count=None, needs=None, cells=None, max_age_s=STALE_AFTER_S):
    age = cells.age_s if isinstance(cells, CellState) else None
    src = cells.source if isinstance(cells, CellState) else "none"
    stale = cells.is_stale(max_age_s) if isinstance(cells, CellState) else True
    return Decision(HOLD, reason, category, count, needs, age, src, stale)


# --------------------------------------------------------------------------------------- parsing

def parse_pyramids(payload, region=REGION, delay=DELAY):
    """One endpoint response -> {category name: alphaCount} for ONE (region, delay).

    Raises PyramidPayloadError on anything it cannot fully account for. A row silently dropped here
    would read downstream as an EMPTY CELL, and empty is the direction that spends a submit."""
    if not isinstance(payload, dict) or not isinstance(payload.get("pyramids"), list):
        raise PyramidPayloadError("response carries no 'pyramids' list")
    out = {}
    for i, row in enumerate(payload["pyramids"]):
        if not isinstance(row, dict):
            raise PyramidPayloadError(f"pyramids[{i}] is a {type(row).__name__}, expected an object")
        cat = row.get("category")
        name = cat.get("name") if isinstance(cat, dict) else cat
        r, d, n = row.get("region"), row.get("delay"), row.get("alphaCount")
        if not name or not r or d is None or not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise PyramidPayloadError(
                f"pyramids[{i}] incomplete: category={cat!r} region={r!r} delay={d!r} "
                f"alphaCount={n!r}")
        if str(r) != str(region) or int(d) != int(delay):
            continue
        # A repeated (pair, category) is not expected. If one arrives, keep the HIGH value, for the
        # same asymmetry as MAX-OF-N. MECHANISM: UNKNOWN — never observed on this endpoint.
        out[str(name)] = max(int(n), out.get(str(name), 0))
    if not out:
        raise PyramidPayloadError(f"response held no rows for {region} delay {delay}")
    return out


def _merge_max(readings):
    keys = set().union(*readings)
    return {k: max(r.get(k, 0) for r in readings) for k in keys}


# ---------------------------------------------------------------------------------- live + cache

def _default_session():
    """The read-only session. Returns None rather than raising: no cookie is a cache-fallback
    condition, not a crash. This session is used for GET only, here and nowhere else."""
    try:
        import pickle

        import requests
        c = pickle.load(open(ROOT / "state/wq_cookies.pkl", "rb"))
        s = requests.Session()
        if isinstance(c, dict):
            s.cookies.update(c)
        else:
            for x in c:
                s.cookies.set_cookie(x)
        return s
    except Exception:
        return None


def _read_cache(cache_path, region, delay, now):
    """Fallback to disk. Reads BOTH artifact shapes: the `pairs` list written by
    harness13/crawl_pyramid.py (schema pyramid_cell_counts/2, all 16 pairs) and the flat
    region/delay/counts block tools/submit_alphas.py maintains for the legacy reader.

    This module deliberately does NOT write this file. Two owners on one path already clobbered it
    once (2026-08-10 20:03: a fresh 16-pair artifact was overwritten by a single-pair one 26
    seconds later). Refreshing the artifact belongs to its crawler; this is a reader."""
    doc = json.loads(pathlib.Path(cache_path).read_text())
    top_ts = doc.get("ts")
    for p in (doc.get("pairs") or []):
        if p.get("region") == region and int(p.get("delay", -1)) == int(delay):
            counts = p.get("counts")
            if not isinstance(counts, dict) or not counts:
                raise PyramidPayloadError("cached pair carries no counts")
            ts = p.get("ts") or top_ts
            age = None if ts is None else max(0.0, now() - float(ts))
            return CellState(region, delay, dict(counts), ts, age, "cache", 0, None)
    if doc.get("region") == region and int(doc.get("delay", -1)) == int(delay):
        counts = doc.get("counts")
        if isinstance(counts, dict) and counts:
            age = None if top_ts is None else max(0.0, now() - float(top_ts))
            return CellState(region, delay, dict(counts), top_ts, age, "cache", 0, None)
    raise PyramidPayloadError(f"cache holds no {region} delay {delay} pair")


def cell_state(region=REGION, delay=DELAY, *, session=None, reads=READS, pause_s=PAUSE_S,
               cache_path=CACHE_PATH, now=time.time, sleep=time.sleep):
    """Live alphaCount per pyramid cell, with a cached fallback and a visible age.

    GET only. Never raises for a network or payload failure — it degrades to the cache and, failing
    that, to counts=None, which `decide` refuses. The caller always gets an age; a decision taken
    on a count of unknown age is refused, not guessed.

    `region`/`delay` are free here on purpose: the artifact holds all 16 pairs and reporting them
    is harmless. The single-pair SCOPE is enforced in `decide`, where the irreversible act is.

    `session=False` skips the network entirely (cache only). `session=None` builds the default
    read-only session from the cookie jar, or falls back to the cache if there is no usable jar."""
    s = session if session is not None else _default_session()
    seen, err = [], None
    if s:
        for i in range(max(1, int(reads))):
            try:
                r = s.get(API + PYRAMID_PATH, timeout=60)
                if getattr(r, "status_code", None) == 200:
                    seen.append(parse_pyramids(r.json(), region, delay))
                else:
                    err = f"HTTP {getattr(r, 'status_code', '?')}"
            except PyramidPayloadError as e:
                err = f"payload: {e}"
            except Exception as e:                       # network, json, anything
                err = f"{type(e).__name__}: {e}"
            if i + 1 < max(1, int(reads)):
                sleep(pause_s)
    else:
        err = "no session"

    if seen:
        t = now()
        return CellState(region, delay, _merge_max(seen), t, 0.0, "live", len(seen), None)

    try:
        st = _read_cache(cache_path, region, delay, now)
        return st._replace(error=err)
    except Exception as e:
        return CellState(region, delay, None, None, None, "unavailable", 0,
                         f"{err or 'no live read'}; cache: {e}")


# -------------------------------------------------------------------------------------- deciding

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def resolve_category(alpha_category, counts):
    """Category label (display name OR platform id) -> the exact key in `counts`, or None.

    None means REFUSE. Being a known platform category is not enough: it must be a live cell of
    this pair. 'Broker' is a real category id and is not a USA d1 cell, so it resolves to None."""
    if alpha_category is None or not isinstance(alpha_category, str):
        return None
    n = _norm(alpha_category)
    if not n:
        return None
    by_norm = {_norm(k): k for k in counts}
    if n in by_norm:
        return by_norm[n]
    alias = CATEGORY_IDS.get(n)
    if alias and _norm(alias) in by_norm:
        return by_norm[_norm(alias)]
    return None


def decide(alpha_category, cells, *, max_age_s=STALE_AFTER_S):
    """SUBMIT or HOLD for one alpha's category against live cell state. FAILS CLOSED everywhere.

    The cost asymmetry sets every default: a wrong HOLD costs one retyped command; a wrong SUBMIT
    permanently spends an alpha's only submission and one of four daily slots. So every unknown —
    off-scope pair, unknown category, stale count, missing count, unparseable payload — is HOLD.

    HARD REFUSALS:
      1. cells is not a CellState                     -> HOLD
      2. (region, delay) != the configured pair       -> HOLD
      3. no counts at all (empty/unparseable/no data) -> HOLD
      4. counts older than max_age_s, or age unknown  -> HOLD
      5. category unknown for this pair               -> HOLD
      6. cell already at alphaCount >= UNLOCK_AT      -> HOLD
    """
    if not isinstance(cells, CellState):
        return _hold(f"cell state is {type(cells).__name__}, not CellState")

    if cells.region != REGION or int(cells.delay) != int(DELAY):
        return _hold(f"out of scope: gate is configured for {REGION} delay {DELAY} only, "
                     f"got {cells.region} delay {cells.delay}", cells=cells, max_age_s=max_age_s)

    if not isinstance(cells.counts, dict) or not cells.counts:
        return _hold(f"no cell data ({cells.source}: {cells.error or 'empty payload'})",
                     cells=cells, max_age_s=max_age_s)

    if cells.is_stale(max_age_s):
        age = "unknown" if cells.age_s is None else f"{cells.age_s / 60:.0f}min"
        return _hold(f"stale cell data: age {age} > {max_age_s / 60:.0f}min threshold "
                     f"({cells.source}) — refuse rather than guess",
                     cells=cells, max_age_s=max_age_s)

    key = resolve_category(alpha_category, cells.counts)
    if key is None:
        return _hold(f"unknown category {alpha_category!r} for {REGION} delay {DELAY}; "
                     f"known: {', '.join(sorted(cells.counts))}", cells=cells, max_age_s=max_age_s)

    count = cells.counts[key]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return _hold(f"unusable count {count!r} for {key}", category=key,
                     cells=cells, max_age_s=max_age_s)

    needs = UNLOCK_AT - count
    if needs <= 0:
        return _hold(f"cell already at {count}/{UNLOCK_AT} — full, a submit here unlocks nothing",
                     category=key, count=count, needs=0, cells=cells, max_age_s=max_age_s)

    return Decision(SUBMIT,
                    f"cell at {count}/{UNLOCK_AT}, {needs} more to unlock",
                    key, count, needs, cells.age_s, cells.source, False)


def priority(cells, *, max_age_s=STALE_AFTER_S):
    """Cells worth a submit, most urgent first. Empty list when the state is not trustworthy.

    OBJECTIVE: maximise CELLS UNLOCKED PER SUBMIT. A submit into a 2/3 cell unlocks a cell
    immediately; the same submit into a 0/3 cell unlocks nothing and needs two more after it. So
    the key is `needs` ascending — fewest alphas still required first — with the category name as a
    deterministic tie-break so the order is reproducible across runs.

    WHAT IT IS NOT OPTIMISING: expected money. Cell multipliers are ignored entirely. The project's
    own note (pyramid-cell-ev-targeting) records that the payout is negligible next to the Genius
    rank, which turns on cells UNLOCKED, not on which cells. Ranking by multiplier would put a rich
    0/3 cell ahead of a 2/3 cell and spend a submit that unlocks nothing.
    It is also not optimising alpha QUALITY, gate pass, or correlation — those are other modules'
    gates, and this one is silent on them."""
    if not isinstance(cells, CellState) or not isinstance(cells.counts, dict) or not cells.counts:
        return []
    if cells.region != REGION or int(cells.delay) != int(DELAY) or cells.is_stale(max_age_s):
        return []
    out = [CellNeed(k, v, UNLOCK_AT - v) for k, v in cells.counts.items()
           if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < UNLOCK_AT]
    return sorted(out, key=lambda c: (c.needs, c.category))


# ------------------------------------------------------------------------------------------- cli

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Pyramid cell gate — DECIDES, never submits.")
    ap.add_argument("category", nargs="?", help="alpha category name or id, e.g. News / news / pv")
    ap.add_argument("--offline", action="store_true", help="cache only, no network")
    ap.add_argument("--max-age-min", type=float, default=STALE_AFTER_S / 60)
    a = ap.parse_args(argv)

    max_age = a.max_age_min * 60
    st = cell_state(session=False if a.offline else None)
    print(f"{REGION} delay {DELAY}  ·  {st.marker(max_age)}")
    p = priority(st, max_age_s=max_age)
    if p:
        print("priority (fewest alphas still needed first — unlocks per submit):")
        for c in p:
            print(f"  {c.category:<16} {c.count}/{UNLOCK_AT}  needs {c.needs}")
    else:
        print("priority: (none — state not trustworthy, or every cell unlocked)")
    if a.category:
        print(decide(a.category, st, max_age_s=max_age).explain())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
