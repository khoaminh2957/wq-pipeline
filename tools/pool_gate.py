"""Switch off the pool categories whose pyramid cell is already full.

OPERATOR SPEC (Khoa, 2026-08-15): "trong trường hợp đã full pyramid nào đó thì tắt ngay để ko sim
alpha chứa field của category mà pyramid đã hoàn thiện", with three rulings taken after the cost was
measured:

  1. HARD DISABLE, but WAIVE THE COVERAGE FLOOR for the cells still open, and PRIORITISE them.
  2. If the standing baseline contains a field from a cell that has just filled, END THE CYCLE.
  3. RE-READ THE PYRAMID WHEN A GEM IS FOUND, not every round.

Ruling 3 is better than what I proposed and the reason is worth writing down: the cell counts only
move when WE submit, and the loop submits at most one alpha a day, after a gem. Polling every round
would spend requests to re-read a number that cannot have changed.

WHAT IT COSTS, measured on the live catalogue before any of this shipped:

    fields total              67,205  ->  31,114 after the 0.95 coverage floor
    fields in OPEN cells       2,012  ->   1,196 after the same floor

Ten of sixteen categories are full -- Analyst, Earnings, Fundamental, Institutions, Macro, Model,
Option, Other, Price Volume, Risk -- and they carry 97% of the catalogue. Waiving the floor for the
open cells is what takes the usable pool from 1,196 back to 2,012, and it is defensible precisely
because the floor was an operator decision about pool membership and never a measured finding that
low-coverage fields produce worse alphas (the council tested that and it failed, BACKBONE_V2 K7).

    Sentiment 678 -> 1065   News 367 -> 637   Social Media 93 -> 111
    Short Interest 50 -> 79  Insiders 8 -> 118  Imbalance 0 -> 2

**Imbalance has 2 fields in the whole catalogue and 0 above the floor.** That cell cannot be
unlocked from this pool at any setting, and no amount of simulation will change it. Stated here
because a loop that silently never fills a cell looks identical to one that is trying.

FAIL OPEN, NOT CLOSED, AND THAT IS DELIBERATE. If the counts cannot be read or are missing, NOTHING
is disabled and the caller is told loudly. The two failures are not symmetric: disabling on bad data
silently shrinks the search space by 26x and looks exactly like working, which is this project's
dominant bug class; not disabling merely spends simulations on a cell that is already full, which is
visible in the next report and costs quota, not truth.
"""

import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
COUNTS = ROOT / "state/pyramid_cell_counts.json"

#: EX-ANTE, from the platform's own pyramid documentation: a cell unlocks at 3 alphas.
UNLOCK_AT = 3


def read_counts(path=COUNTS, region="USA", delay=1):
    """(counts, age_s, error). `counts` is None on any doubt -- never an empty book of zeroes."""
    p = pathlib.Path(path)
    if not p.exists():
        return None, None, "no artifact at %s" % p
    try:
        d = json.loads(p.read_text())
    except ValueError as exc:
        return None, None, "unparseable: %s" % exc
    pairs = d.get("pairs") or [d]
    hit = next((x for x in pairs
                if x.get("region") == region and x.get("delay") == delay), None)
    if not hit or not isinstance(hit.get("counts"), dict):
        return None, None, "no counts for %s/d%s" % (region, delay)
    ts = d.get("ts") or hit.get("ts")
    age = (time.time() - ts) if isinstance(ts, (int, float)) else None
    return hit["counts"], age, None


def state(path=COUNTS, region="USA", delay=1, unlock_at=UNLOCK_AT):
    """What is full, what is open, and how badly each open cell still needs alphas.

    Returns a dict with `disabled`, `open`, `needs`, `age_s`, `error`, `ok`. When `ok` is False the
    caller must disable NOTHING -- see the module docstring on why this fails open.
    """
    counts, age, err = read_counts(path, region, delay)
    if counts is None:
        return {"ok": False, "disabled": frozenset(), "open": frozenset(), "needs": {},
                "counts": None, "age_s": None, "error": err}
    disabled = frozenset(k for k, v in counts.items() if isinstance(v, int) and v >= unlock_at)
    open_ = frozenset(k for k in counts if k not in disabled)
    needs = {k: max(unlock_at - counts[k], 0) for k in open_ if isinstance(counts[k], int)}
    return {"ok": True, "disabled": disabled, "open": open_, "needs": needs,
            "counts": counts, "age_s": age, "error": None}


def refresh(path=COUNTS, region="USA", delay=1, session=None):
    """Re-read the cell counts from the platform and rewrite the artifact.

    CALLED WHEN A GEM IS FOUND, not every round -- Khoa's ruling, and it is the right one: the counts
    only move when WE submit, and the loop submits at most one alpha a day after a gem. Polling every
    round would spend requests re-reading a number that cannot have changed.

    Returns (counts, error). On any doubt the artifact is left ALONE: a half-written count book is
    worse than a stale one, because staleness is visible in `describe()` and corruption is not.
    """
    import layered_sim as LS
    s = session or LS.session()
    try:
        r = s.get("%s/users/self/activities/pyramid-alphas" % LS.API, timeout=40)
    except Exception as exc:
        return None, "exception:%s" % type(exc).__name__
    if r.status_code != 200:
        return None, "http:%d" % r.status_code
    try:
        j = r.json()
    except ValueError:
        return None, "unparseable body"
    # The key is `pyramids`, not `results`. Verified against a live 200 rather than assumed:
    # {"pyramids": [{"category": {"id": "pv", "name": "Price Volume"},
    #                "region": "USA", "delay": 0, "alphaCount": 0}, ...]}
    rows = j.get("pyramids") if isinstance(j, dict) else j
    if not isinstance(rows, list):
        return None, "no pyramids list (keys: %s)" % (
            list(j)[:6] if isinstance(j, dict) else type(j).__name__)
    counts = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        # The payload carries EVERY region and delay, so the filter is not optional -- a d0 row
        # borrowed into a d1 count book is exactly the kind of silent mix that fills a cell on paper.
        if row.get("region") != region or row.get("delay") != delay:
            continue
        cat = row.get("category")
        name = cat.get("name") if isinstance(cat, dict) else cat
        if not name:
            continue
        n = row.get("alphaCount")
        if isinstance(n, int):
            counts[name] = n
        else:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None, "no rows matched %s/d%s" % (region, delay)
    p = pathlib.Path(path)
    old = {}
    if p.exists():
        try:
            old = json.loads(p.read_text())
        except ValueError:
            old = {}
    pairs = [x for x in (old.get("pairs") or [])
             if not (x.get("region") == region and x.get("delay") == delay)]
    pairs.append({"region": region, "delay": delay, "counts": counts, "ts": time.time()})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pairs": pairs, "ts": time.time()}, indent=1))
    return counts, None


def category_of(field):
    """The pyramid category name on a catalogue row. The field's `category` is sometimes a dict and
    sometimes a bare string, and the names map 1:1 onto the pyramid cells with no translation."""
    c = field.get("category")
    return c.get("name") if isinstance(c, dict) else c


#: HOW THE DRAW IS SPLIT ACROSS THE OPEN CELLS. Khoa asked whether the proportion can be assigned
#: from how filled each pyramid is (2026-08-15). It can, and it is a named policy rather than a
#: constant buried in a function, because there is no measurement here that says which order is
#: right -- only arguments, and they point different ways.
#:
#:   nearest      w = 1/needs        a cell one alpha short converts a single gem into an UNLOCK.
#:                                   Highest EV per gem, and the default.
#:   filled       w = count + 1      proportional to how filled the cell already is. Same ordering
#:                                   as `nearest` here (needs = 3 - count) but a gentler slope, and
#:                                   the +1 is what stops an empty cell getting ZERO draws and
#:                                   never being worked on at all.
#:   emptiest     w = needs          the opposite bet: put effort where the most work remains.
#:                                   Defensible if a cell at 0 is hard because nobody has tried it.
#:   uniform      w = 1              every open cell equal.
#:
#: In all four, a category's total weight is SHARED among its leaves, so a 1,065-field category does
#: not outdraw a 118-field one on count alone.
#:
#: MECHANISM: UNKNOWN for which ordering finds unlocks fastest. Nothing here has measured whether a
#: one-short cell is easier or harder to fill than an empty one, and the honest position is that the
#: policy is a choice with a stated argument, not a finding.
WEIGHT_POLICIES = {
    "nearest": lambda count, needs: 1.0 / max(needs, 1),
    "filled": lambda count, needs: float(count) + 1.0,
    "emptiest": lambda count, needs: float(max(needs, 1)),
    "uniform": lambda count, needs: 1.0,
}
#: KHOA'S CHOICE, 2026-08-15, made from the measured draw-share table rather than from the argument:
#: `filled`, w = count + 1, "tỉ lệ theo số đã fill". Same ordering as `nearest` here because
#: needs = 3 - count, but a gentler slope -- an empty cell keeps 9.1% instead of 9.5%, and the +1
#: is what stops it dropping to zero and never being worked on.
#:
#: He also chose to KEEP Imbalance in the rotation despite it having 2 fields in the whole catalogue
#: and being unfillable from this pool. So ~9% of every round goes to variants over those two
#: fields. That is a known, priced cost, not an oversight.
#: SUPERSEDED 2026-08-15, later the same day: Khoa asked for the field pick to be "hoàn toàn ngẫu
#: nhiên". That is incompatible with prioritising -- a policy cannot both favour the cells nearest
#: unlocking and draw evenly -- so `uniform` wins and `filled` stays available on the flag.
#:
#: What is given up: under `filled`, News and Insiders (one alpha short each) took ~28% of draws
#: apiece. Under `uniform` every open cell takes 16.7% regardless of how close it is to unlocking.
DEFAULT_POLICY = "uniform"


def draw_weights(fields, st, policy=DEFAULT_POLICY):
    """One weight per field, prioritising the cells nearest to unlocking.

    Khoa asked for the open cells to be PRIORITISED as well as kept. The priority is a CHOICE, not a
    measurement: a category weight of 1/needs puts the most draw on a cell that is one alpha short.
    Within a category every field is equal, and the category's total weight is shared out, so
    Sentiment's 1,065 fields do not drown Insiders' 118 by sheer count.

    MECHANISM: UNKNOWN for whether nearest-to-unlocking is the right order. It is the EV argument --
    a cell one alpha short converts a single gem into an unlock -- but nothing here has measured
    whether such a cell is easier or harder to fill than an empty one.
    """
    if not st.get("ok"):
        return [1.0] * len(fields)
    fn = WEIGHT_POLICIES.get(policy) or WEIGHT_POLICIES[DEFAULT_POLICY]
    by_cat = {}
    for f in fields:
        by_cat.setdefault(category_of(f), []).append(f)
    counts = st.get("counts") or {}
    weights = []
    for f in fields:
        cat = category_of(f)
        n = len(by_cat.get(cat) or [1])
        need = st["needs"].get(cat)
        prio = 1.0 if not need else fn(counts.get(cat, 0), need)
        weights.append(prio / n)
    return weights


def policy_table(fields, st, policies=None):
    """The draw share each policy would give each open cell. Printed rather than argued about."""
    out = {}
    cats = sorted({category_of(f) for f in fields})
    for name in (policies or list(WEIGHT_POLICIES)):
        w = draw_weights(fields, st, name)
        tot = sum(w) or 1.0
        share = {}
        for f, x in zip(fields, w):
            share[category_of(f)] = share.get(category_of(f), 0.0) + x / tot
        out[name] = {c: share.get(c, 0.0) for c in cats}
    return out


def describe(st):
    if not st.get("ok"):
        return ("pyramid gate OFF -- %s. NOTHING is disabled; a silently shrunk pool is worse than "
                "simulating into a full cell." % st.get("error"))
    age = "age unknown" if st.get("age_s") is None else "%.1f days old" % (st["age_s"] / 86400)
    need = ", ".join("%s needs %d" % (k, v) for k, v in sorted(st["needs"].items(),
                                                               key=lambda kv: kv[1]))
    return ("pyramid gate ON (%s): %d cell(s) full and disabled [%s]; open: %s"
            % (age, len(st["disabled"]), ", ".join(sorted(st["disabled"])), need or "none"))


#: SEGMENTS TO ROTATE THROUGH when a cycle ends without a gem. Khoa, 2026-08-15: "trong cycle tới
#: nếu ko tìm ra alpha gem thì rotate qua các region khác để sim và tìm alpha".
#:
#: Only segments whose field catalogue is actually on disk are listed -- a rotation into a region
#: with no catalogue would draw from nothing and read as a dead cycle rather than a missing file.
#:
#: EACH SEGMENT HAS ITS OWN GATE CONSTANT AND ITS OWN PYRAMID COUNTS. `LOW_SUB_UNIVERSE_SHARPE`'s k
#: is 0.433 at USA/TOP3000/d1 and runs 0.295 (IND TOP500) to 0.711 (CHN TOP2000U), so a submit
#: decision taken in a new region on the old constant would be wrong. The rotation changes where we
#: SIMULATE; it does not carry any measured constant across.
#: KHOA, 2026-08-18: "them delay 0 va ngau nhien ko thu tu". Both delays of every region are
#: listed; `available_rotation` drops the ones whose catalogue is not on disk, so ASI/d0 and GLB/d0
#: simply never appear until someone fetches them. The ORDER of this tuple no longer means anything
#: -- `next_segment` draws at random -- but it is kept stable so the filtered list is reproducible.
ROTATION = (
    ("USA", "TOP3000", 1), ("USA", "TOP3000", 0),
    ("EUR", "TOP2500", 1), ("EUR", "TOP2500", 0),
    ("JPN", "TOP1200", 1), ("JPN", "TOP1200", 0),
    ("CHN", "TOP2000U", 1), ("CHN", "TOP2000U", 0),
    ("ASI", "MINVOL1M", 1), ("ASI", "MINVOL1M", 0),
    ("GLB", "TOP3000", 1), ("GLB", "TOP3000", 0),
)


def catalogue_for(region, universe, delay, root=ROOT):
    return root / ("fetched/rc/fields/%s_%s_d%d.jsonl" % (region, universe, delay))


def available_rotation(root=ROOT):
    """The rotation, filtered to segments whose catalogue is on disk."""
    return tuple(x for x in ROTATION if catalogue_for(*x, root=root).exists())


def next_segment(current, root=ROOT, rng=None):
    """A segment to move to, drawn AT RANDOM rather than taken in order.

    Khoa, 2026-08-18. A fixed cycle makes the sequence of segments a function of how many gemless
    stretches have happened, which is not a property of the market -- and it meant a segment that
    happened to sit after a productive one got sampled far more often than one that sat after a
    barren one.

    `current` is always excluded, so this returns a segment that is genuinely different or None if
    there is nowhere else to go. A caller that passes an unknown `current` still gets a valid draw.
    """
    import random as _random
    avail = [x for x in available_rotation(root) if tuple(x) != tuple(current)]
    if not avail:
        return None
    return (rng or _random).choice(avail)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--region", default="USA")
    ap.add_argument("--delay", type=int, default=1)
    a = ap.parse_args()
    st = state(region=a.region, delay=a.delay)
    print(describe(st))
    if st.get("ok"):
        import layered_alpha as LA
        allf = LA.load_fields(region=a.region, delay=a.delay, min_coverage=0.0)
        keep = [f for f in allf if category_of(f) not in st["disabled"]]
        floored = [f for f in keep
                   if isinstance(f.get("coverage"), (int, float)) and f["coverage"] >= 0.95]
        print("pool: %d total -> %d in open cells (%d of them above the 0.95 floor)"
              % (len(allf), len(keep), len(floored)))
        counts = {}
        for f in keep:
            counts[category_of(f)] = counts.get(category_of(f), 0) + 1
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
            print("   %-16s %5d  (needs %s)" % (k, v, st["needs"].get(k, "-")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
