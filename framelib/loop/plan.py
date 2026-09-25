"""framelib.loop.plan -- the round planner of the frames loop (docs/frames/00_decisions.md F5-F10).

One call returns about `--n` (300) constructions for USA/d1/TOP3000 in the dispatcher's shape
({"formula", "settings", "meta"} under "constructions", read by framelib/experiments/vps/dispatch_round.py
--abc). Offline: nothing here simulates, submits or touches the network (RULE 1). Its only writes are the plan
(--out) and the unit blacklist (framelib.loop.availability), which it refreshes from the journals first.

    python3 -B -m framelib.loop.plan --n 300 --out plan.json [--seed S] [--day YYYY-MM-DD] [--state DIR]
        [--evidence state/frames/evidence.jsonl] [--datasets-ok state/frames/datasets_ok.json]
        [--unit-blacklist state/frames/unit_blacklist.json] [--history state/frames/history_usa_d1_top3000.jsonl]
        [--posted-log PATH ...]

ROUTES, per ET day (F8; doc 13 §7). The round's budget (--n, at most MAX_ROWS) is taken in this order:
  pairs       F10. PAIR_SHARE of the round's FILLS run twice, at the frame's own settings profile and at the
              REFERENCE profile, from production frames whose profile differs from the reference (a frame at the
              reference has nothing to pair). Frames drawn as in production below (own Thompson stream and floor).
              Route "production", meta.pair_id / meta.pair_member ("profile" | "reference"). They go first so
              every round carries its share, the first round of a day included; budget they cannot use (no
              pairable frame, no fresh fill) goes on to the routes below.
  replicate   every frame the evidence ledger shows SCREENED YESTERDAY gets PER_FRAME fresh own-role fills,
              less the replicate rows already dispatched today. Before screen because it cannot be done later:
              tomorrow those frames are two days old (DESIGN CHOICE).
  screen      today's cohort of new frames (provenance.origin in NEW_ORIGINS): the frames already begun today,
              then frames with no ledger row at all by (built_at, id), up to NEW_PER_DAY; PER_FRAME fresh
              own-role fills each, less the screen rows already dispatched today.
  production  the rest. Frames: every non-retired library frame that is in neither of today's routes above,
              a new frame only after its replication day. Per fill: Thompson sampling on
              Beta(1 + y08, 1 + scored - y08), summed over the frame's ledger rows (every route and day);
              EXPLORE_SHARE of the fills ignore the posterior and draw a frame uniformly, spread through the
              stream as forge/gen/propose.py spreads D35's floor (fill k explores when fewer than
              EXPLORE_SHARE x (k + 1) earlier fills explored, so any prefix of m fills holds ceil(m / 5)).
              Fill mode per fill: own-role or other-dataset as round1.arm_entries defines them, by a seeded
              coin P_OWN; the other mode when the drawn one has no fresh fill left.
Screen and replicate fills run once, at the frame's profile: PER_FRAME counts rows there, as the ledger does.

SETTINGS (F10). Every row runs at its frame's SETTINGS PROFILE (profile() below): the entry's `settings` block
(source canonical-modal = the historical modal settings of a mined frame, designer = the declared settings of a
novel one), else, for a mutation, its parent's (then the grandparent's ...), else the REFERENCE profile. A profile
written for another region (its `universe` has no USA key) or holding a value USA does not offer (neutralization
outside USA_NEUTRALIZATIONS, decay not an integer in 0..512, truncation outside 0..1) is not used: the
reference is, and the reason is in meta.settings_profile. Region, delay and universe are this planner's cell
(USA, 1, TOP3000) whatever the profile's universe says.

EVERY FILL
  * comes out of framelib.filler (structurally_ok; re-frames to its frame) on the field library pruned to
    today's datasets (framelib.loop.availability = round1.restrict);
  * is FRESH for its frame: none of its fields is in evidence.used_fields(frame) or in an earlier row of
    this plan for that frame, and it is not a formula of the frame's canonical history (round2's exclude);
  * writes no (field, operator) input the platform rejected with "Incompatible unit" (the unit blacklist,
    framelib.loop.availability, learned from the frames journals and persistent);
  * is not a D18 near-duplicate of an accepted POST: forge.gen.spend.d18_refuses, the D36 plan-time rule,
    FAIL-OPEN when the index is incomplete or cannot be built;
  * has a formula no other fill of this plan has (two frames can write one formula: a pinned field and a
    slot share a canonical key).
BLOCKS. dispatch_round.merged groups rows by meta.arm, shuffles each group, cuts it into parents of 10 and trims
it to a multiple of 10. So every purpose comes in whole blocks of BLOCK: meta.arm is the route for replicate,
screen and production rows, and "production-pair-NN" for pair rows, one label per block of PAIRS_PER_BLOCK pairs,
so the shuffle cannot split a pair and both members share a parent. Rows cut here were never dispatched, so
their fields are fresh again next round.
ROUND SIZE. At most MAX_ROWS rows: one dispatch_round chunk (its CHUNK), the size measured to finish inside
layered_sim's MAX_ROUND_S (75 min). POST-HOC, 2026-09-25, FRAMES-R1B and FRAMES-R2 journals (dateCreated of the
scored rows per 300-row chunk, 5th..95th percentile; scratch chunk_spans2.py): the full chunks spanned 22.0, 25.6,
23.8, 18.9 (R1B) and 10.7, 8.8 (R2) minutes; second way, R1B's chunks STARTED 25-30 min apart (07:03, 07:28,
07:58, 08:25 ET). One chunk (R2 #2) reached the deadline with 30 of its 300 rows journalled and 9 parents in
flight -- a stall, not a slow chunk; MECHANISM: UNKNOWN, and whether a smaller chunk would have lost less was not
measured. A larger round is not planned: nothing measured it.

A mined-dropped frame (newframes) has canonical history and is filled as round1 fills a mined frame; a
mutation has none and is filled by its declared constraints, as round1 fills a novel frame.

LABELS (RULE 0). PER_FRAME 8 and NEW_PER_DAY 25: the task and F8. EXPLORE_SHARE 0.20: D35's convention
carried over, an EX-ANTE convention (no data sets the share). PAIR_SHARE 0.25 of the fills: the task's "about a
quarter" (F10 says "a share"); no data sets it. REFERENCE (INDUSTRY, decay 4, truncation 0.08): the task's.
Beta(1, 1): DESIGN CHOICE (D35's uniform start). The posterior counts scored rows only, since y08 is defined on a
scored row (doc 13 §3.1); ERROR and CANCELLED rows do not move it (DESIGN CHOICE); it counts every ledger row of the
frame, pair reference members included (DESIGN CHOICE: the ledger's by_pair_member could leave them out). P_OWN 0.5: DESIGN
CHOICE, a randomised factor so that own-role and other-dataset fills can be compared within frame and day; it
claims nothing about which mode yields more. USA_NEUTRALIZATIONS: EX-ANTE, transcribed from the platform's OPTIONS
/simulations snapshot fetched/rc/settings_options_live.json (2026-08-07). Why any frame or profile does well:
MECHANISM: UNKNOWN.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "tools"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from forge import submit as FS                     # noqa: E402  quota_day, posted_history
from forge.gen import spend as SP                  # noqa: E402  d18_refuses (D36)
from framelib import filler as FI                  # noqa: E402
from framelib import frames as FR                  # noqa: E402
from framelib.experiments import round1 as R1      # noqa: E402
from framelib.loop import availability as AV       # noqa: E402

EXPERIMENT = "FRAMES-LOOP"
CELL = R1.CELL
NEW_ORIGINS = ("mined-dropped", "mutation")
PER_FRAME = 8
NEW_PER_DAY = 25
EXPLORE_SHARE = 0.20
PAIR_SHARE = 0.25
P_OWN = 0.5
PRIOR = (1, 1)
BLOCK = 10
PAIRS_PER_BLOCK = BLOCK // 2
MAX_ROWS = 300
PAIR_ARM = "production-pair-%02d"
REFERENCE = {"neutralization": "INDUSTRY", "decay": 4, "truncation": 0.08}
USA_NEUTRALIZATIONS = frozenset({"NONE", "REVERSION_AND_MOMENTUM", "STATISTICAL", "CROWDING", "FAST", "SLOW",
                                 "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY", "SLOW_AND_FAST"})
PROFILE_SOURCES = ("canonical-modal", "designer")
OWN, OTHER = "own-role", "other-dataset"
FILL_N0, FILL_NMAX = 16, 512
DAY_KEYS = ("day", "et_day", "plan_day")          # the ledger's ET-day key is not fixed by the interface
LEDGER_KEYS = ("frame_id", "route", "n_planned", "n_scored", "y08")
EVIDENCE = ROOT / "state/frames/evidence.jsonl"
HISTORY = ROOT / "state/frames/history_usa_d1_top3000.jsonl"


def et_day(ts=None) -> str:
    """The ET (quota) day a timestamp falls in; now when ts is None."""
    return FS.quota_day(time.time() if ts is None else ts)


def _yesterday(day: str) -> str:
    return (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()


def load_evidence(path=EVIDENCE) -> list:
    """The evidence ledger's rows. A missing file or a line that is not JSON is an error: read as an empty
    ledger, today's cohort would look unscreened and yesterday's would never be replicated."""
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError("evidence ledger %s missing: run python -m framelib.loop.evidence --update first" % p)
    rows = []
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ValueError("%s line %d is not JSON: %s" % (p, i, exc)) from None
    return rows


def ledger(rows) -> dict:
    """frame_id -> {"y08", "scored", "planned": {(ET day, route): n_planned}}. A row without a key the
    planner reads raises: a silently zero count would move the posterior and the day's routes."""
    out = {}
    for r in rows:
        day = next((r[k] for k in DAY_KEYS if r.get(k)), None)
        miss = [k for k in LEDGER_KEYS if k not in r] + ([] if day else ["day"])
        if miss:
            raise ValueError(("evidence row missing %s: %s" % (miss, json.dumps(r, sort_keys=True)))[:400])
        v = out.setdefault(r["frame_id"], {"y08": 0, "scored": 0, "planned": {}})
        v["y08"] += int(r["y08"])
        v["scored"] += int(r["n_scored"])
        k = (str(day), r["route"])
        v["planned"][k] = v["planned"].get(k, 0) + int(r["n_planned"])
    return out


def _is_new(e) -> bool:
    return (e.get("provenance") or {}).get("origin") in NEW_ORIGINS


def stages(entries: dict, led: dict, day: str) -> dict:
    """Today's routes: {"replicate": {fid: due}, "screen": {fid: due}, "production": [fid], "waiting": [fid]}.
    `entries`: id -> entry, retired ones already left out. "waiting": new frames not yet replicated."""
    yday = _yesterday(day)

    def planned(fid, d, route):
        return led.get(fid, {}).get("planned", {}).get((d, route), 0)
    rep = {f: max(0, PER_FRAME - planned(f, day, "replicate")) for f in sorted(entries) if planned(f, yday, "screen")}
    begun = [f for f in sorted(entries) if f not in rep and planned(f, day, "screen")]
    unseen = sorted((f for f in entries if _is_new(entries[f]) and f not in led),
                    key=lambda f: (str((entries[f].get("provenance") or {}).get("built_at") or ""), f))
    cohort = begun + unseen[:max(0, NEW_PER_DAY - len(begun))]
    scr = {f: max(0, PER_FRAME - planned(f, day, "screen")) for f in cohort}
    prod, waiting = [], []
    for f in sorted(entries):
        if f in rep or f in scr:
            continue
        replicated = any(r == "replicate" and d < day for d, r in led.get(f, {}).get("planned", {}))
        (waiting if _is_new(entries[f]) and not replicated else prod).append(f)
    return {"replicate": rep, "screen": scr, "production": prod, "waiting": waiting}


# ---- settings profiles (F10) ------------------------------------------------------------------------------------

def _usable(st: dict):
    """(neutralization, decay, truncation) of a settings block, or a reason it cannot run in USA."""
    uni = st.get("universe")
    if isinstance(uni, dict) and "USA" not in uni:
        return "written for %s" % ",".join(sorted(uni))
    n, d, t = st.get("neutralization"), st.get("decay"), st.get("truncation")
    if n not in USA_NEUTRALIZATIONS:
        return "neutralization %r not offered in USA" % (n,)
    if isinstance(d, bool) or not isinstance(d, (int, float)) or d != int(d) or not 0 <= d <= 512:
        return "decay %r not an integer in 0..512" % (d,)
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 <= t <= 1:
        return "truncation %r not in 0..1" % (t,)
    return {"neutralization": n, "decay": int(d), "truncation": float(t)}


def profile(entry: dict, entries: dict) -> tuple:
    """(profile {neutralization, decay, truncation}, where it came from) for one library entry. `entries`: id ->
    entry, for a mutation's parents."""
    e, seen, via = entry, set(), ""
    while e is not None and e["id"] not in seen:
        seen.add(e["id"])
        st = e.get("settings") or {}
        if st.get("source") in PROFILE_SOURCES:
            got = _usable(st)
            if isinstance(got, str):
                return dict(REFERENCE), "reference: %s%s profile %s" % (via, st["source"], got)
            return got, "%s%s" % (via, st["source"])
        pv = e.get("provenance") or {}
        if pv.get("origin") != "mutation" or not pv.get("parent"):
            break
        via = "parent %s " % pv["parent"]
        e = entries.get(pv["parent"])
    return dict(REFERENCE), "reference: no profile"


def _kind(source: str) -> str:
    """A profile source, for the report: reference / parent / canonical-modal / designer."""
    return source.split(":")[0].split(" ")[0]


def _settings(triple: dict) -> dict:
    return dict(R1.BASE, **triple)


def _round1_view(e: dict) -> dict:
    """round1.arm_entries fills a frame by its canonical history only when origin == "mined"."""
    pv = e.get("provenance") or {}
    return dict(e, provenance=dict(pv, origin="mined")) if pv.get("origin") == "mined-dropped" else e


def _history_formulas(e: dict, h) -> set:
    """The frame's canonical-history formulas (the fills are canonical-key fills, pinned fields included)."""
    if not h:
        return set()
    try:
        key = FR.normalize(e.get("canonical_key") or e["text"])
    except FR.FrameError:
        return set()
    out = set()
    for f in h["fills"]:
        try:
            out.add(key.fill(list(f)))
        except FR.FrameError:
            continue
    return out


class _Supply:
    """The filler's fills of one (frame, mode), in its seeded order, drawn on demand (n doubles). The
    filler's stream is random.Random(seed|text|cell), so a larger n extends a smaller call's list."""

    def __init__(self, entry, fl, seed, exclude):
        self.entry, self.fl, self.seed, self.exclude = entry, fl, seed, exclude
        self.fills, self.pos, self.n, self.done, self.dead = [], 0, 0, False, None

    def _grow(self):
        self.n = 2 * self.n if self.n else FILL_N0
        res = FI.fill(self.entry, self.fl, CELL, n=self.n, seed=self.seed, by="dataset", exclude=self.exclude)
        if res["dead"]:
            self.dead, self.done = res["dead"], True
            return
        self.fills = res["fills"]
        self.done = len(res["fills"]) < self.n or self.n >= FILL_NMAX

    def candidates(self):
        while True:
            while self.pos < len(self.fills):
                self.pos += 1
                yield self.fills[self.pos - 1]
            if self.done:
                return
            self._grow()


class Planner:
    def __init__(self, seed, day, entries: dict, fl, hist: dict, used_fields, structures, blacklist=frozenset()):
        self.seed, self.day, self.entries, self.fl, self.hist = seed, day, entries, fl, hist
        self.used_fields, self.structures, self.blacklist = used_fields, structures, blacklist
        self.rng = random.Random("frames-loop|%s|%s" % (seed, day))
        self._used, self._sup, self.notes, self.formulas, self._prof = {}, {}, {}, set(), {}
        self.report = {"d18_refused": 0, "d18_twins": collections.Counter(), "duplicate_formula": 0,
                       "unit_blacklisted": 0, "unit_hits": collections.Counter(), "dead": {}}

    def used(self, fid) -> set:
        if fid not in self._used:
            self._used[fid] = set(self.used_fields(fid) or ())
        return self._used[fid]

    def profile(self, fid) -> tuple:
        if fid not in self._prof:
            self._prof[fid] = profile(self.entries[fid], self.entries)
        return self._prof[fid]

    def pairable(self, fid) -> bool:
        return self.profile(fid)[0] != REFERENCE

    def supply(self, fid, mode) -> _Supply:
        if (fid, mode) not in self._sup:
            e = self.entries[fid]
            own, other, self.notes[fid] = R1.arm_entries(_round1_view(e), self.fl, self.hist)
            excl = _history_formulas(e, self.hist.get(e.get("canonical_key") or ""))
            self._sup[(fid, OWN)] = _Supply(own, self.fl, self.seed, excl)
            self._sup[(fid, OTHER)] = _Supply(other, self.fl, self.seed, excl)
        return self._sup[(fid, mode)]

    def take(self, fid, mode):
        """The next fresh, unit-clear, D18-clear, plan-unique fill of `fid` in `mode`, or None when there is none."""
        s, used = self.supply(fid, mode), self.used(fid)
        for x in s.candidates():
            if set(x["fill"]) & used:
                continue
            if x["formula"] in self.formulas:
                self.report["duplicate_formula"] += 1
                continue
            hits = AV.blocked(x["formula"], self.blacklist)
            if hits:
                self.report["unit_blacklisted"] += 1
                self.report["unit_hits"].update("%s|%s" % h for h in hits)
                continue
            refused, _sim, twin = SP.d18_refuses(self.structures, x["formula"])
            if refused:
                self.report["d18_refused"] += 1
                self.report["d18_twins"][str(twin)] += 1
                continue
            used.update(x["fill"])
            self.formulas.add(x["formula"])
            return x
        if s.dead:
            self.report["dead"].setdefault(fid, {})[mode] = s.dead
        return None

    def row(self, fid, x, route, mode, arm=None, select=None, pair=None) -> dict:
        """One construction. `pair`: (pair_id, "profile" | "reference")."""
        e = self.entries[fid]
        prof, src = self.profile(fid)
        st = _settings(REFERENCE if pair and pair[1] == "reference" else prof)
        meta = {"experiment": EXPERIMENT, "arm": arm or route, "route": route, "frame_id": fid,
                "frame_version": e.get("version"), "fill": list(x["fill"]), "fill_mode": mode,
                "role_note": self.notes.get(fid), "settings_profile": src, "round_seed": self.seed,
                "plan_day": self.day, "hypothesis": "frames:%s" % fid, "recipe": EXPERIMENT, "region": "USA", "delay": 1}
        if select:
            meta["select"] = select
        if pair:
            meta["pair_id"], meta["pair_member"] = pair
        meta["cand"] = hashlib.sha256(("%s|%s" % (x["formula"], json.dumps(st, sort_keys=True))).encode()).hexdigest()[:12]
        return {"formula": x["formula"], "settings": st, "meta": meta}

    def stream(self, frames, post, want) -> tuple:
        """Up to `want` fills of `frames` by Thompson sampling with the exploration floor:
        ([(fid, fill, mode, select)], frames exhausted on the way)."""
        active, got, n_explore, exhausted = list(frames), [], 0, []
        while len(got) < want and active:
            explore = n_explore < round(EXPLORE_SHARE * (len(got) + 1), 9)
            fid = self.rng.choice(active) if explore else max((self.rng.betavariate(*post[f]), f) for f in active)[1]
            first = OWN if self.rng.random() < P_OWN else OTHER
            for mode in (first, OTHER if first == OWN else OWN):
                x = self.take(fid, mode)
                if x is not None:
                    got.append((fid, x, mode, "explore" if explore else "thompson"))
                    n_explore += explore
                    break
            else:
                active.remove(fid)
                exhausted.append(fid)
        return got, exhausted


def pair_target(budget: int) -> int:
    """Pair fills for a round of `budget` rows: P pairs + S singles = P + S fills and 2P + S = budget rows with
    P = PAIR_SHARE x (P + S), so P = PAIR_SHARE x budget / (1 + PAIR_SHARE), cut to whole pair blocks."""
    p = int(PAIR_SHARE * budget / (1 + PAIR_SHARE))
    return p - p % PAIRS_PER_BLOCK


def build(seed: int, n: int, *, entries, fl, hist: dict, evidence: list, used_fields, structures, day: str,
          blacklist=frozenset()) -> dict:
    """The round's plan. `entries`: library entries; `fl`: the field library, already pruned to today's
    datasets; `hist`: round1.history() of the cell; `evidence`: the ledger's rows; `used_fields(fid)`: the
    fields ever used with that frame; `structures`: forge.novelty.build(...) or None (fail-open);
    `blacklist`: {(field, operator)} never to be written (availability.load_unit_blacklist)."""
    live = {e["id"]: e for e in entries if e.get("status") != "retired"}
    led = ledger(evidence)
    st = stages(live, led, day)
    P = Planner(seed, day, live, fl, hist, used_fields, structures, blacklist)
    rng = P.rng
    rows, rep = {}, {"deferred": {}, "short": {}}
    budget = min(n, MAX_ROWS)
    budget -= budget % BLOCK
    rep["capped"] = [n, MAX_ROWS] if n > MAX_ROWS else None
    post = {f: (PRIOR[0] + led.get(f, {}).get("y08", 0),
                PRIOR[1] + led.get(f, {}).get("scored", 0) - led.get(f, {}).get("y08", 0)) for f in st["production"]}

    # pairs (F10): whole blocks of PAIRS_PER_BLOCK pairs, one dispatcher arm per block
    pairable = [f for f in st["production"] if P.pairable(f)]
    want = pair_target(budget)
    got, pair_exhausted = P.stream(pairable, post, want)
    got = got[:len(got) - len(got) % PAIRS_PER_BLOCK]
    rows["pairs"] = []
    for k, (fid, x, mode, select) in enumerate(got):
        arm, pid = PAIR_ARM % (k // PAIRS_PER_BLOCK), "%s-%03d" % (seed, k)
        rows["pairs"] += [P.row(fid, x, "production", mode, arm, select, (pid, "profile")),
                          P.row(fid, x, "production", mode, arm, select, (pid, "reference"))]
    rep["pairs"] = {"target_fills": want, "fills": len(got), "pairable_frames": len(pairable),
                    "frames": len({g[0] for g in got})}
    budget -= len(rows["pairs"])

    for route in ("replicate", "screen"):
        got_r, order = [], sorted(st[route])
        rng.shuffle(order)
        for fid in order:
            if len(got_r) >= budget:
                break
            k = 0
            while k < st[route][fid]:
                x = P.take(fid, OWN)
                if x is None:
                    break
                got_r.append(P.row(fid, x, route, OWN))
                k += 1
            if k < st[route][fid]:
                rep["short"].setdefault(route, {})[fid] = [st[route][fid], k]
        keep = min(len(got_r), budget)
        keep -= keep % BLOCK
        rows[route] = got_r[:keep]
        rep["deferred"][route] = sum(st[route].values()) - keep
        budget -= keep

    got, exhausted = P.stream(st["production"], post, budget)
    prod = [P.row(fid, x, "production", mode, select=select) for fid, x, mode, select in got]
    rows["production"] = prod[:len(prod) - len(prod) % BLOCK]
    rep["deferred"]["production"] = len(prod) - len(rows["production"])
    constructions = rows["replicate"] + rows["screen"] + rows["pairs"] + rows["production"]
    by_route = collections.Counter(c["meta"]["route"] for c in constructions)
    single = [c for c in constructions if "pair_id" not in c["meta"]]
    rep.update({
        "plan_day": day, "n_requested": n,
        "counts": {r: by_route.get(r, 0) for r in ("replicate", "screen", "production")},
        "fills": {"single": len(single), "paired": len(rows["pairs"]) // 2},
        "frames": {r: len({c["meta"]["frame_id"] for c in rows[r]}) for r in rows},
        "stages": {k: len(v) for k, v in st.items()},
        "due": {r: sum(st[r].values()) for r in ("replicate", "screen")},
        "explore": sum(1 for c in rows["production"] if c["meta"].get("select") == "explore"),
        "profiles": dict(collections.Counter(_kind(P.profile(f)[1]) for f in live)),
        "exhausted": exhausted, "pair_exhausted": pair_exhausted, "waiting": st["waiting"],
        "d18_refused": P.report["d18_refused"], "d18_twins": dict(P.report["d18_twins"]),
        "duplicate_formula": P.report["duplicate_formula"], "unit_blacklisted": P.report["unit_blacklisted"],
        "unit_hits": dict(P.report["unit_hits"]), "dead": P.report["dead"],
        "posterior_top": sorted(([f, a, b] for f, (a, b) in post.items()), key=lambda v: (-v[1] / (v[1] + v[2]), v[0]))[:10],
    })
    return {"experiment": EXPERIMENT, "seed": seed, "cell": CELL, "plan_day": day, "constructions": constructions,
            "report": rep}


def d18_index(paths) -> tuple:
    """(structures, status) for plan-time D18. FAIL-OPEN (D36): an index that cannot be built refuses nothing,
    and one that could not read some POST's formula still refuses the near-duplicates of those it read."""
    try:
        from forge import novelty as NV
        s = NV.build(FS.posted_history(paths=tuple(paths)), {})
    except Exception as exc:  # noqa: BLE001 -- fail-OPEN is the decided behaviour (D36); the reason is reported
        return None, "unavailable (%s: %s): plan-time D18 refuses nothing (fail-OPEN, D36)" % (type(exc).__name__, exc)
    if not s.complete:
        return s, "incomplete: no formula for %s (their near-duplicates are not refused; fail-OPEN, D36)" % s.missing
    return s, "complete: %d accepted POST structure(s)" % len(s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=None, help="default: the current epoch second, recorded in the plan")
    ap.add_argument("--day", default="", help="ET day YYYY-MM-DD; default: today's")
    ap.add_argument("--state", default=str(ROOT / "state"),
                    help="the journals the unit blacklist and evidence.used_fields read")
    ap.add_argument("--evidence", default=str(EVIDENCE))
    ap.add_argument("--datasets-ok", default=str(AV.PATH))
    ap.add_argument("--unit-blacklist", default=str(AV.UNIT_BLACKLIST))
    ap.add_argument("--history", default=str(HISTORY), help="canonical rows (rows_framed.jsonl form) of the cell")
    ap.add_argument("--posted-log", action="append", default=[], help="a submit log besides forge's and climb's")
    a = ap.parse_args(argv)
    from framelib import store
    from framelib.fields import FieldLibrary
    from framelib.loop import evidence as EVL
    if not pathlib.Path(a.history).exists():
        raise SystemExit("canonical history %s missing: own-role fills of mined frames need it" % a.history)
    seed = a.seed if a.seed is not None else int(time.time())
    day = a.day or et_day()
    units = AV.refresh_unit_blacklist(a.state, a.unit_blacklist)
    blacklist = AV.load_unit_blacklist(a.unit_blacklist)
    fl = FieldLibrary.build(cells={CELL})
    avail = AV.prune(fl, a.datasets_ok)
    structures, d18 = d18_index([FS.LOG, FS.CLIMB_LOG] + list(a.posted_log))
    plan = build(seed, a.n, entries=store.load(), fl=fl, hist=R1.history(a.history), evidence=load_evidence(a.evidence),
                 used_fields=lambda f: EVL.used_fields(f, state=a.state), structures=structures, day=day,
                 blacklist=blacklist)
    plan["report"].update({"availability": avail, "d18_index": d18, "unit_blacklist": units})
    pathlib.Path(a.out).write_text(json.dumps(plan))
    rep = plan["report"]
    print("frames plan %s seed %d: %s fills %s frames %s explore %d pairs %s" % (
        day, seed, rep["counts"], rep["fills"], rep["frames"], rep["explore"], rep["pairs"]))
    print("due %s deferred %s short %s dead %d exhausted %d waiting %d capped %s profiles %s" % (
        rep["due"], rep["deferred"], {r: len(v) for r, v in rep["short"].items()}, len(rep["dead"]),
        len(rep["exhausted"]), len(rep["waiting"]), rep["capped"], rep["profiles"]))
    print("D18: %s; refused %d; duplicates %d; unit blacklist %s, blocked %d; availability %s" % (
        d18, rep["d18_refused"], rep["duplicate_formula"], {k: units[k] for k in ("pairs", "new", "unattributed")},
        rep["unit_blacklisted"], avail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
