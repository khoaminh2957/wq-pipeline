"""Recover the children of forge parents that were posted but never reaped (a crashed round).

MEASURED 2026-09-06 19:58: 117 forge parents (1,170 simulations, spent quota) had no child rows
because the round died on a ReadTimeout after posting them. The platform still holds every
result. A parent row carries only its formulas; the round's plan file (state/forge/plans/<seed>.json)
carries every construction with settings and meta, so a child is attributed by (echoed formula,
echoed settings) — the same discriminators the live child-order guard uses — and journalled as a
normal forge row. Rows that cannot be attributed are written with status ORPHAN-UNMATCHED and no
meta, never guessed. Idempotent: a parent with any child row is skipped.

  venv/bin/python forge/offline/recover_orphans.py [--limit N] [--dry]
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
JOURNAL = ROOT / "state/layered/runs/forge.jsonl"
PLANS = ROOT / "state/forge/plans"
DISCRIMINATORS = ("region", "universe", "delay", "neutralization", "decay", "truncation")
PACE_S = 1.1
# Per-round bookkeeping in meta; not part of a construction's identity. `pipeline_version` joined on
# 2026-09-23: forge/runner.py began stamping the constructions it plans with the deployed version
# (D1/D14; the constructions of a `--plan` round too since draw3_fix pipeline / design stage 0c), and
# the architecture attack (round 1, S1) confirmed with this very match() that a construction planned by
# two versions then read as two candidates -- ambiguous, filed ORPHAN-UNMATCHED, the 2026-09-09 class
# again. The same formula and settings are the same simulation whichever version planned them.
# `run_config` joined with D30 (the runner's arguments, a second stamp beside the version): the same
# construction planned under two FORGE_ARGS is one simulation for the same reason, and without it here
# test_a_construction_planned_under_two_run_configs_is_one_construction reads None (ORPHAN-UNMATCHED).
# `gen_state` joined with architecture round 3 S15: the pass-first generator (docs/evalharness/
# 04_passfirst_design.md section 3.2; forge/gen/state.py) recomputes the loop's state every round and stamps
# its sha256 on every construction as meta.gen_state, so two plan entries of one construction differing in
# seed and gen_state read as two candidates and match() returned None -- ORPHAN-UNMATCHED, the 2026-09-09
# class. S15 asks for "any other per-round key the generator stamps" too. Re-read 2026-09-24 in
# forge/gen/productions.py candidate() and from_row() and forge/gen/propose.py: gen_state is still the one key the
# generator sets per ROUND. `gen_route` ("fresh", "neighbour", "repair": propose.ROUTES) is set per candidate;
# forge/gen/spend.py treats a "neighbour" row apart and D54 counts "fresh" only, so it changes what a row means and
# stays in the identity, as do `arm`, `generator` and the from_row links `repair_of` / `neighbour_of`: one
# construction reached by two routes stays unmatched rather than guessed. `arm` stays OUT by S15's own words: D47
# compares arms.
# `gen_draw` joined with design stage 4: propose stamps it on a fresh draw ("posterior" / "floor"), and which one a
# draw gets is set by its place in the ROUND (propose.py: draw k is a floor draw when fewer than FLOOR_SHARE x (k+1)
# floor draws came before it), so one fresh construction drawn by two rounds -- the same formula and settings from
# two seeds; how often: UNMEASURED -- may carry both values while it is one simulation. No reader keys on it (grep
# 2026-09-24), so it is not guessed either: NONE_WHEN_SEVERAL, below.
# `round` joined with D54 (the runner's `--mode randomised`, shared interface: meta.round = the seed): it is set
# per ROUND exactly as seed is, so without it two plan entries of one construction from two randomised rounds
# read as two candidates (None, ORPHAN-UNMATCHED). `arm_by` ("randomiser" / "explicit") stays IN the identity
# with `arm`: it decides whether a row enters D54's comparison, so a construction planned by a randomised and an
# explicit round stays unmatched rather than guessed.
ROUND_KEYS = ("seed", "pipeline_version", "run_config", "gen_state", "round", "gen_draw")
#: Round bookkeeping match() never takes from hits[0] when the matched entries disagree on it: the row gets None
#: (the comment above AMBIGUOUS_VERSION says why for `round`, D54's unit; `gen_draw` above).
NONE_WHEN_SEVERAL = ("round", "gen_draw")
#: The stamps a cohort is keyed on (D1/D14's version; D30's run_config: a cohort is the pair).
COHORT_KEYS = ("pipeline_version", "run_config")
#: What match() writes into meta.pipeline_version when the plan entries it matched are one construction
#: but were planned by DIFFERENT versions (architecture round 2, A11). Identity ignores the stamp (above),
#: so match() used to return hits[0] and the row inherited whichever plan `glob` listed first. MEASURED
#: by round 2 (v11_orph.py): plans 101.json {A_version} and 202.json {B_version}, glob order
#: ['202.json', '101.json'], recovered meta {'seed': 202, 'pipeline_version': 'B_version'} whichever
#: round POSTed it. Either round could have posted the simulation, so no version is named.
#: FOR THE SCORER: a row carrying this value belongs to NO version's cohort. forge/offline/benchmark.py
#: forms cohorts through cohort_of() and parse_cohort(), and their plain_stamp() refuses this word in
#: meta.pipeline_version (STAMP_MARKERS; read 2026-09-23; draw-4 pipeline 5(d): this sentence used to say the
#: scorer selects "by equality" in build_from and compare); the date-window card (no version) counts every
#: row whatever its stamp. Anything that pools rows by version must drop
#: `meta.pipeline_version == AMBIGUOUS_VERSION` rather than count it as a version of its own.
#: A pre-stamp plan (no pipeline_version) and a stamped one also disagree: that row is ambiguous too.
#: THE ROUND, TOO (draw-3 pipeline MINOR 7). The same branch used to keep hits[0]'s `meta.seed` -- the
#: probe above still read {'seed': 202, ...} -- and forge/offline/ab_report.py:82 groups rows into A/B
#: rounds by meta.seed, so the row joined round 202 on glob order alone. When the matched entries name
#: more than one seed, the row's `meta.seed` is None and every seed is kept in `meta.seed_candidates`,
#: ordered by its JSON text so glob order cannot change the row. None, not the string "ambiguous" the
#: fix was first specified with: MEASURED 2026-09-23 on a scratch journal
#: (rounds 101 and 202 plus one such row), ab_report.report() with seed "ambiguous" raises TypeError at
#: its `sorted(...)` of the round keys (str against int), while with None it drops the row from every
#: round (`if k is not None`) and still counts it in its arm's pooled total.
#: RUN_CONFIG, THE SAME WAY (D30). Entries that agree on the version but name different `run_config`s
#: were one construction planned under two argument sets: `run_config` is written AMBIGUOUS_VERSION, the
#: version is kept, and the seed is handled as above. A reader that pools by the pair must drop a row
#: whose `run_config` is AMBIGUOUS_VERSION exactly as it drops the version. benchmark's cohort_of() and
#: parse_cohort() do, through _forms_cohort() (draw-4 P2, the scoring owner's half; read 2026-09-23 21:40 +07,
#: and pinned from this side by test_a_row_ambiguous_on_either_stamp_forms_no_cohort).
#: OPEN (draw3_fix pipeline 5): entries that agree on BOTH stamps but name several seeds still return
#: hits[0], and the row takes hits[0]'s `meta.seed`, i.e. glob order picks its A/B round.
#: test_a_construction_planned_by_two_versions_is_attributed_to_neither pins that behaviour (`is stamped`).
#: The same holds for `meta.gen_state` (S15, ROUND_KEYS above) in BOTH branches of match(): the A11 branch
#: replaces the stamps, the seed and `round` only, so a recovered row's gen_state is hits[0]'s whenever several
#: differ (no reader keys on gen_state; grep 2026-09-24). `round` (D54) is NOT left to that OPEN: benchmark's
#: arms read-out takes meta.round as the unit of its test and admits a row only with one, so glob order would pick
#: which round -- on which ET day, the test's stratum -- a recovered row counts in. In BOTH branches a row whose
#: matched entries name several rounds gets round None, which that read-out excludes and counts ("no meta.round");
#: `gen_draw` the same way (NONE_WHEN_SEVERAL).
AMBIGUOUS_VERSION = "ambiguous"


def _norm(f: str) -> str:
    return re.sub(r"\s+", "", f or "")


#: The plan files load_plans() reads: the RUNNER's own copies only, `<seed>.json` as forge/runner.py main()
#: names them (`--seed` is an int), never an experiment script's plan (pow.json, c11.json, tvr.json,
#: llmformula*.json). D46 (Khoa 2026-09-23 ~20:15; draw-4 pipeline P1): recover exactly the pair that was
#: dispatched. main() re-stamps a `--plan` round's constructions with the version and run_config that ran
#: them (and an arm where absent) and writes that copy BEFORE it dispatches, so the copy is what was sent.
#: Indexed beside it, the experiment's own plan still named the base row's stamps: the draw-4 adjudicator,
#: with the real main(), match() and child_row(), got (ambiguous, ambiguous) back for a pow-shaped plan,
#: (v-running, ambiguous) for a c11 shape and (ambiguous, ambiguous) for an unstamped llm shape, against
#: (v-running, <its run_config>) dispatched; and an entry the runner gives an arm would not match at all
#: (identity differs). Checked before choosing this over marking the runner's copy (/opt/wq, read 2026-09-23):
#: 221 plan files, 216 of them `<seed>.json`; pow.json's 300 and c11.json's 48 constructions each sit whole in
#: one runner copy (1788939868.json, 1788717789.json), and the 248 of the three llmformula plans were never
#: dispatched (no journal row among 43,114 names one of their formulas; none carries an `llm:` hypothesis).
#: So no dispatched construction on the host was reachable only through an experiment plan. What this gives
#: up: a round whose copy a later round with the same seed overwrote is not found here, and its children are
#: filed ORPHAN-UNMATCHED rather than attributed to an experiment plan's copied stamps.
RUNNER_PLAN = re.compile(r"-?\d+\.json")


def load_plans(plans_dir=PLANS) -> dict:
    """{normalised formula: [construction, ...]} over the runner's plan copies (RUNNER_PLAN)."""
    idx = {}
    for p in glob.glob(str(pathlib.Path(plans_dir) / "*.json")):
        if not RUNNER_PLAN.fullmatch(pathlib.Path(p).name):
            continue
        try:
            plan = json.load(open(p))
        except ValueError:
            continue
        for c in plan.get("constructions", []):
            idx.setdefault(_norm(c["formula"]), []).append(c)
    return idx


def _identity(c: dict) -> str:
    """What makes two plan entries the SAME simulation: everything except the round that planned it."""
    c = dict(c)
    c["meta"] = {k: v for k, v in (c.get("meta") or {}).items() if k not in ROUND_KEYS}
    return json.dumps(c, sort_keys=True)


def match(construction_index: dict, formula: str, settings: dict):
    """The unique construction whose formula and discriminating settings equal the platform's echo."""
    cands = construction_index.get(_norm(formula), [])
    hits = [c for c in cands if all(str(c["settings"].get(k)) == str((settings or {}).get(k))
                                    for k in DISCRIMINATORS if (settings or {}).get(k) is not None)]
    # The same construction written to two plan files (an experiment's own plan and the runner's
    # copy of it, 2026-09-06 C11) is one construction, not an ambiguity: 10 COMPLETE alphas were
    # filed ORPHAN-UNMATCHED because both files held them. (Since D46 load_plans() indexes the runner's
    # copies only, RUNNER_PLAN; the rule still serves one construction in two runner copies.)
    # ROUND BOOKKEEPING IS NOT IDENTITY (2026-09-09): `meta.seed` is the round that planned the
    # construction, so the SAME construction re-planned in a later round read as two different
    # candidates and every child of it was filed ORPHAN-UNMATCHED. MEASURED that evening: 131
    # unmatched rows, ALL of them ambiguous, and the differing key was meta.seed on 163 of 187
    # candidate pairs; excluding it alone resolves 111 of the 131. `category` and `arm` are NOT
    # excluded: they change what the row means (the allocator's pair, the A/B arm), so a row
    # ambiguous on those stays unmatched rather than guessed (17 + 3 rows).
    distinct = {_identity(c) for c in hits}
    if len(distinct) != 1:
        return None
    # A11: one construction, several planning versions -> the version is not known (AMBIGUOUS_VERSION),
    # and neither is the round when the entries name several (MINOR 7, above). A copy, so the plan index
    # every later match reads is never rewritten. The sets are built from JSON text, not the values: a
    # plan that did not come from the runner can carry a list or a dict there, and a set of those raised
    # TypeError (draw-3 pipeline MINOR 7). run_config the same way (D30, above).
    unknown = [k for k in COHORT_KEYS if len({json.dumps((c.get("meta") or {}).get(k), sort_keys=True) for c in hits}) > 1]
    several = [k for k in NONE_WHEN_SEVERAL if len({json.dumps((c.get("meta") or {}).get(k), sort_keys=True) for c in hits}) > 1]
    if unknown:
        meta = dict(hits[0].get("meta") or {}, **dict.fromkeys(unknown, AMBIGUOUS_VERSION))
        seeds = sorted({json.dumps((c.get("meta") or {}).get("seed"), sort_keys=True) for c in hits})
        if len(seeds) > 1:
            meta.update(seed=None, seed_candidates=[json.loads(s) for s in seeds])
        return dict(hits[0], meta=dict(meta, **dict.fromkeys(several)))
    if several:                                 # also where the seed's OPEN keeps hits[0]'s seed
        return dict(hits[0], meta=dict(hits[0].get("meta") or {}, **dict.fromkeys(several)))
    return hits[0]


PLATFORM_TERMINAL = {"COMPLETE", "WARNING", "ERROR", "FAIL", "FAILED", "CANCELLED", "CANCELED", "ORPHAN-UNMATCHED"}


def orphans(journal=JOURNAL) -> list:
    """Parents with no child row that carries a platform answer. A child row whose status is this
    machine's own (AUTH-FAIL, POLL-DEADLINE, POLL-EXHAUSTED, MULTISIM-*) says the runner could not
    read the platform, not what the platform said — the parent is still an orphan (2026-09-07)."""
    parents, children = [], set()
    with open(journal) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") == "PARENT-POSTED" and r.get("parent_url"):
                parents.append(r)
            elif r.get("parent_url") and (r.get("alpha") or r.get("status") in PLATFORM_TERMINAL):
                children.add(r["parent_url"])
    return [p for p in parents if p["parent_url"] not in children]


def child_urls(pj: dict) -> list:
    out = []
    for c in pj.get("children") or []:
        url = c if isinstance(c, str) else (c.get("url") or c.get("id") or "")
        if url and not url.startswith("http"):
            url = "https://api.worldquantbrain.com/simulations/" + url
        out.append(url)
    return out


def recover(s, parent: dict, cidx: dict, scrape, get, sleep=time.sleep) -> list:
    """Journal rows for one orphan parent (list may be empty when the parent is not terminal)."""
    r = get(parent["parent_url"])
    if r is None or r.status_code != 200:
        return []
    pj = r.json()
    if (pj.get("status") or "").upper() not in ("COMPLETE", "WARNING", "ERROR", "FAIL", "FAILED"):
        return []
    rows = []
    for i, url in enumerate(child_urls(pj)):
        sleep(PACE_S)
        cr = get(url)
        if cr is None or cr.status_code != 200:
            continue
        rows.append(child_row(cr.json(), url, parent["parent_url"], i, cidx, scrape, sleep))
    return rows


def child_row(cj: dict, url: str, parent_url: str, i: int, cidx: dict, scrape, sleep=time.sleep) -> dict:
    """One journal row from a child simulation's payload (matched to its plan construction or not)."""
    echo = cj.get("regular")
    echo = echo.get("code") if isinstance(echo, dict) else echo
    st = (cj.get("status") or "").upper()
    con = match(cidx, echo or "", cj.get("settings") or {})
    alpha = cj.get("alpha") if st in ("COMPLETE", "WARNING") else None
    rec = {"status": st or "UNKNOWN", "alpha": alpha, "polls": 0, "message": cj.get("message") or "",
           "sim_url": url, "parent_url": parent_url, "child_index": i, "recovered_at": time.time(),
           "formula": (con or {}).get("formula") or echo, "settings": (con or {}).get("settings") or cj.get("settings"),
           "meta": (con or {}).get("meta")}
    if con is None:
        rec["status"] = "ORPHAN-UNMATCHED"
        rec["alpha"] = None
    elif alpha:
        sleep(PACE_S)
        rec.update(scrape(alpha))
    return rec


def unmatched(journal=JOURNAL) -> list:
    """ORPHAN-UNMATCHED rows whose simulation has no attributed row yet."""
    rows, attributed = [], set()
    with open(journal) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") == "ORPHAN-UNMATCHED" and r.get("sim_url"):
                rows.append(r)
            elif r.get("sim_url") and r.get("alpha"):
                attributed.add(r["sim_url"])
    return [r for r in rows if r["sim_url"] not in attributed]


def rematch(rows: list, cidx: dict, scrape, get, sleep=time.sleep) -> list:
    """Second pass over ORPHAN-UNMATCHED rows after the plan index (or match) changed."""
    out = []
    for r in rows:
        if match(cidx, r.get("formula") or "", r.get("settings") or {}) is None:
            continue
        sleep(PACE_S)
        cr = get(r["sim_url"])
        if cr is None or cr.status_code != 200:
            continue
        rec = child_row(cr.json(), r["sim_url"], r.get("parent_url"), r.get("child_index", 0), cidx, scrape, sleep)
        if rec["status"] != "ORPHAN-UNMATCHED":
            out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--rematch", action="store_true", help="retry the ORPHAN-UNMATCHED rows against the current plan files")
    a = ap.parse_args()
    import layered_sim as LS
    orph = orphans()[: a.limit]
    print("orphan parents: %d (limit %d)" % (len(orphans()), a.limit), flush=True)
    if a.dry or not (orph or a.rematch):
        return 0
    s = LS.session()
    LS.keep_jar_fresh(s)
    cidx = load_plans()

    def get(url):
        try:
            return LS._get_patient(s, url, timeout=40)
        except Exception:  # noqa: BLE001
            return None
    if a.rematch:
        todo = unmatched()
        rows = rematch(todo, cidx, lambda aid: LS.scrape(s, aid), get)
        with open(JOURNAL, "a") as jf:
            for rec in rows:
                jf.write(json.dumps(rec) + "\n")
        print("rematch: %d unmatched rows, %d attributed" % (len(todo), len(rows)))
    done = matched = 0
    with open(JOURNAL, "a") as jf:
        for p in orph:
            rows = recover(s, p, cidx, lambda aid: LS.scrape(s, aid), get)
            for rec in rows:
                jf.write(json.dumps(rec) + "\n")
                matched += rec["status"] != "ORPHAN-UNMATCHED"
            jf.flush()
            done += 1
            if done % 10 == 0:
                print("  %d parents, %d children attributed" % (done, matched), flush=True)
    print("recovered: %d parents, %d children attributed" % (done, matched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
