"""framelib.loop.submit -- the frames loop's submit step (F9). The only code of the frames loop that POSTs.

    python -m framelib.loop.submit [--journal state/layered/runs/frames_loop.jsonl] [--cap 4] [--submit]

Without --submit nothing is POSTed, no session is opened, no budget slot is reserved and no correlation is read
from the platform: it prints what it would POST. main(journal, submit=..., cap=...) returns the ids it POSTed.

WHAT AUTHORISES IT. Khoa F9 (docs/frames/00_decisions.md, 2026-09-24 ~20:15 +07): frame alphas are submitted
automatically once they pass the D39 decidable gates of forge/meaning.py, and every other submit rule stays -- D18
novelty (fail-closed), the correlation lines with a fresh re-read, the shared 4/day ledger, the 403 budget. Every
route below fails CLOSED: a reading that is missing, unreadable or raises is a hold, never a POST.

CANDIDATES. The last row per alpha id of the loop journal whose meta says experiment FRAMES-LOOP and carries a
frame_id, at D24 as framelib/experiments/analyse_round.outcome reads it (status COMPLETE or WARNING, each of the
7 BINDING checks PASS). Rows of the experiment rounds (FRAMES-R1, -R1B, -R2) are never candidates: F3 gives them
no submit step, Khoa ticks each.

GATES, per candidate, in this order (the cheap local ones first, the platform read last, just before the POST):
  1  one POST per alpha, ever: forge.submit.posted_history (both POST logs and the budget ledger's reservations).
  2  MATCHES_PYRAMID PASS on the row (forge/submit.py C21).
  3  Q20 diversity (forge.submit.diversity_ok, per POST): at most 2 of an ET day's POSTs share a dataset set and
     only one set may repeat. A frame row carries no mechanism key, so its dataset set is built here: the sorted
     catalogue dataset ids of every field of the formula (operators.fields_in, GROUP fields left out), joined by
     '|' -- the middle part of forge's key 'name#ds1|ds2#cell'. A field the catalogue snapshot does not hold (or
     a snapshot absent) holds the row ('dataset-set-unreadable'); such a field also reads G7 false below.
  4  D18: forge.novelty over every accepted POST; an incomplete index holds every candidate, a structural twin of
     a POST is held, a candidate whose structure cannot be read is held.
  5  D39/D52: forge.submit.meaning_gate -- forge.meaning.score, the row appended to state/forge/meaning.jsonl, POST
     only when every decidable gate (G4's leg clause, G5-G8) is exactly true (G1-G3 too when the row inherited a
     composite's text), and the recorded row for (alpha, formula sha) reads true as well.
With --submit only:
  6  403 budget: more than forge.submit.MAX_403_PER_WEEK refusals in 7 days -> nothing is POSTed.
  7  the submit flock (forge.submit.SUBMIT_LOCK, the lock forge/submit.py and tools/climb_submit.py take), THEN
     the shared budget,
     tools/submit_budget.remaining_today(session) capped by --cap; unreadable -> nothing is POSTed. (forge reads
     the budget before taking the lock; here the read is inside it, so no other submitter can POST between the
     count and the POST.)
  8  per pick: a FRESH correlation reading, every time, right before its POST -- forge.probe.read for prod and
     self (never the stored reading); numeric and under forge.submit.corr_lines(row) or the pick is held for this
     invocation. A numeric reading is appended to state/forge/corr.jsonl, as forge/submit.py does.
  9  a reservation row in the shared budget ledger, then the POST (tools/climb_submit.post), then the row in
     state/forge/submitted.jsonl (forge.submit.record's keys, source "frames-loop", plus frame_id, frame_version,
     route) so posted_history, forge.novelty and forge.meaning see it (forge/probe.py reads no POST log), then
     the m6 announce.
 10  after an ACCEPTED POST (200/201): the diversity count, S11 (below; read only while a slot is left), and
     D18 registration -- the POSTed structure is registered and every queued twin dropped; a POST with no
     formula to register stops the run.
 11  any other answer stops the run; the ledger keeps the slot. forge/submit.py stops on a 403 or an unknown
     outcome (the POST raised) and goes on after any other code (a 429, a 5xx); here those stop too, because
     each is recorded and reserved like a POST (posted_history then reads the alpha as POSTed, ever), and this
     step does not know which of them the platform adjudicated.

S11 -- PREDICTOR, NOT THE ONE-POST FALLBACK. After each accepted POST, every remaining pick whose PnL-predicted
SELF against the POSTed alpha is at or over the pick's SELF line is held for this invocation. Predictor:
tools/self_corr_predict.predict on the two PnL curves, each the cached curve (state/pnl_curves) or else fetched by
GET through self_corr_predict.pnl, which caches it (frame rows are not harvested, so their curves are not cached
beforehand). No curve, no number, or an exception holds the pick: in the worst case this route POSTs ONE alpha per
invocation. POST-HOC: the predictor's accuracy (max |err| 4.9e-5 over 136 pairs, its own docstring) was measured
on climb/forge alphas; on frame alphas it is UNMEASURED. S11 looks at the POSTs of this invocation only, as in
forge/submit.py; a POST made by an earlier invocation is covered by the fresh platform reading alone.

REACHABLE ON REAL ROWS? POST-HOC, descriptive, 2026-09-25 (scratch reach.py, host copies of frames_r1b.jsonl,
frames_r2.jsonl and fetched/rc/fields/USA_TOP3000_d1.jsonl, no platform call): gate 3's dataset set read for
1,430 of 1,430 scored frame rows (every field in the host snapshot); forge.meaning.score read every decidable gate
true on 666 of 1,430 (holds: G6 false 719, G4 false 116, G5 false 22, G8 false 7, G4 null 7; ledgers limited to
those two journals, no NO_GO bank, no composites). The D18 index over the host's two POST logs is complete (5
accepted POSTs, each with its formula) without the journal fallback. So neither gate holds every frame alpha
by construction. Neither round had a D24 row, so no frame alpha has yet met this route end to end.

ORDER. C20's keys that a frame row has: open pyramid cells first (forge.submit.cell_gain, need x multiplier, on
state/pyramid_cell_counts.json; unreadable counts give every row 0 -- an ordering, never a hold), then the lower
stored SELF reading (the probe's corr.jsonl; none sorts last), then the alpha id.

forge/submit.py RULES NOT APPLIED HERE -- not in F9's list, named for Khoa (RULE 2 gate 5), none decided here:
  * stage == candidate's DSR >= 0.95 and the PBO holds: they need forge/harvest.py's pools and curves, and frame
    rows are not harvested; holding on "unjudged", as forge does, would hold every frame alpha forever (F9
    unreachable).
  * D51 (two one-setting neighbours): its text scopes it to gen: rows, and the frames planner simulates no
    neighbours, so applying it would also hold every frame alpha forever. F10 (2026-09-25 ~14:30) says "D51's
    neighbour check runs one setting away from the profile" but does not say the submit step waits for it: an
    open question for Khoa's tick, not decided here.
  * C16 second-best and C20's robust score: a frame row has no harvest score.
  * the one-mechanism-key-per-invocation drop: D18 registration and S11 are the in-invocation guards here.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from forge import cells as C, harvest as HV, novelty as NV, probe as P, submit as SUB  # noqa: E402  (puts tools/ on sys.path)
from framelib.experiments import analyse_round as AR  # noqa: E402
import operators as OPS  # noqa: E402  -- repo root; the field reader forge.novelty's fingerprint uses
import self_corr_predict as SCP  # noqa: E402  -- tools/

EXPERIMENT = "FRAMES-LOOP"
LOOP_JOURNAL = ROOT / "state/layered/runs/frames_loop.jsonl"
#: where forge/submit.py records its own POSTs, and the climb's log posted_history also reads
POST_LOG = SUB.LOG
CLIMB_LOG = SUB.CLIMB_LOG
CORR = P.CORR
CURVES = HV.CURVES
FIELDS_DIR = ROOT / "fetched/rc/fields"
PAIR_COUNTS = ROOT / "state/pyramid_cell_counts.json"
SOURCE = "frames-loop"
LEDGER_SOURCE = "frames_loop_submit"
CURVE_BUDGET_S = 45.0          # forge/harvest.py's --budget default for one PnL recordset
SLEEP = time.sleep             # named so the fake-transport tests do not sleep


# ------------------------------------------------------------------------------------------- reading
def candidates(journal) -> tuple:
    """(rows, cands): rows = {alpha: last loop row}; cands = the rows at D24 (analyse_round.outcome)."""
    rows = {}
    for r in HV.read_jsonl(journal):
        m = r.get("meta") if isinstance(r.get("meta"), dict) else {}
        if r.get("alpha") and m.get("experiment") == EXPERIMENT and m.get("frame_id"):
            rows[r["alpha"]] = r
    return rows, {a: r for a, r in rows.items() if AR.outcome(r)["d24"] == 1}


def _cell(settings) -> tuple:
    s = settings if isinstance(settings, dict) else {}
    return s.get("region"), s.get("universe"), s.get("delay")


def field_rows(cell, names, fields_dir=None) -> dict:
    """{field id: catalogue row} for `names` from fetched/rc/fields/<R>_<U>_d<D>.jsonl (streamed; {} if absent)."""
    region, universe, delay = cell
    want, out = set(names), {}
    if not want or None in cell:
        return out
    path = pathlib.Path(fields_dir or FIELDS_DIR) / ("%s_%s_d%d.jsonl" % (region, universe, int(delay)))
    if not path.exists():
        return out
    with open(path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("id") in want:
                out[r["id"]] = r
    return out


def dataset_set(formula, cat) -> str | None:
    """'ds1|ds2' over every non-GROUP field of `formula`; None when a field is not in `cat` or has no dataset id."""
    ids = set()
    for f in OPS.fields_in(formula or ""):
        r = cat.get(f)
        if r is None:
            return None
        if r.get("type") == "GROUP":
            continue
        ds = r.get("dataset")
        ds = ds.get("id") if isinstance(ds, dict) else None
        if not ds:
            return None
        ids.add(ds)
    return "|".join(sorted(ids)) or None


def _pyramids(row):
    """(MATCHES_PYRAMID passed?, its pyramids list)."""
    for c in row.get("checks") or []:
        if isinstance(c, dict) and c.get("name") == "MATCHES_PYRAMID":
            return c.get("result") == "PASS", c.get("pyramids") or []
    return False, []


# ------------------------------------------------------------------------------------------- gates
def eligible(cands, history, novelty, meaning, cats, pair_counts, stored, now=None) -> tuple:
    """(queue in POST order, Counter of hold reasons) over the local gates 1-5 of the module docstring."""
    now = now or time.time()
    posted = {h["alpha"] for h in history}
    today = SUB.today_dataset_sets(history, now)
    out, held = [], collections.Counter()
    for a in sorted(cands):
        row = cands[a]
        if a in posted:
            held["already-posted"] += 1
            continue
        ok, pyr = _pyramids(row)
        if not ok:
            held["pyramid-not-pass"] += 1
            continue
        st = row.get("settings") or {}
        ds = dataset_set(row.get("formula"), cats.get(_cell(st)) or {})
        if ds is None:
            held["dataset-set-unreadable"] += 1
            continue
        if not SUB.diversity_ok(ds, today):
            held["dataset-set-repeated-today"] += 1
            continue
        if not novelty.complete:
            held["novelty-index-incomplete"] += 1
            continue
        repeat, sim, twin = novelty.verdict(row.get("formula") or "")
        if repeat is None:
            held["novelty-candidate-unreadable"] += 1
            continue
        if repeat:
            held["structure-already-submitted"] += 1
            continue
        why = meaning(a, row)
        if why:
            held[why] += 1
            continue
        m = row.get("meta") or {}
        hyp = m.get("hypothesis") or "frames:%s" % m["frame_id"]
        s = stored.get(a) or {}
        out.append({"alpha": a, "row": row, "hypothesis": hyp, "frame_id": m["frame_id"], "route": m.get("route"),
                    "mechanism_key": "%s#%s#%s/d%s" % (hyp, ds, st.get("region"), st.get("delay")),
                    "datasets": ds, "pyramids": pyr, "cell_gain": SUB.cell_gain(pyr, pair_counts),
                    "lines": SUB.corr_lines(row), "prod": s.get("prod"), "self": s.get("self"),
                    "structural_sim": sim, "structural_twin": twin})
    out.sort(key=lambda e: (-e["cell_gain"], e["self"] if isinstance(e["self"], (int, float)) else float("inf"),
                            e["alpha"]))
    return out, held


def pnl_twin_hold(posted_alpha, queue, curve_of, predict) -> tuple:
    """S11 -> (kept, Counter): hold each queued pick whose predicted SELF against `posted_alpha` is at or over its
    own SELF line ('s11-pnl-twin'); no curve ('s11-curve-absent'), no number ('s11-unpredictable') or an
    exception ('s11-error:<class>', every pick) holds too. An empty queue reads no curve."""
    kept, held = [], collections.Counter()
    if not queue:
        return kept, held
    try:
        posted = curve_of(posted_alpha)
        if not (isinstance(posted, dict) and posted):
            return [], collections.Counter({"s11-curve-absent": len(queue)} if queue else {})
        for e in queue:
            mine = curve_of(e["alpha"])
            if not (isinstance(mine, dict) and mine):
                held["s11-curve-absent"] += 1
                continue
            v, _n = predict(mine, posted)
            if not isinstance(v, (int, float)):
                held["s11-unpredictable"] += 1
            elif v >= e["lines"][1]:
                held["s11-pnl-twin"] += 1
            else:
                kept.append(e)
    except Exception as exc:  # noqa: BLE001 -- fail closed: every queued pick is held
        return [], collections.Counter({"s11-error:%s" % type(exc).__name__: len(queue)})
    return kept, held


# ------------------------------------------------------------------------------------------- writing
def record(pick, http, body, path=None) -> None:
    """One row per POST, where forge/submit.py records its own, with forge.submit.record's keys."""
    row, m = pick["row"], pick["row"].get("meta") or {}
    p = pathlib.Path(path or POST_LOG)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({
            "alpha": pick["alpha"], "formula": row.get("formula"), "hypothesis": pick["hypothesis"],
            "arm": m.get("arm"), "mechanism_key": pick["mechanism_key"], "datasets": pick["datasets"],
            "pyramids": [q.get("name") for q in pick["pyramids"] if isinstance(q, dict)],
            "score": None, "prod_corr": pick["prod"], "self_corr": pick["self"],
            "sharpe": row.get("sharpe"), "fitness": row.get("fitness"), "turnover": row.get("turnover"),
            "http": http, "body": body, "posted_at": time.time(), "source": SOURCE,
            "frame_id": pick["frame_id"], "frame_version": m.get("frame_version"), "route": pick["route"]}) + "\n")


def _fresh(s, alpha) -> dict:
    """{prod, self}: forge.probe.read for each kind now; a value, or the reason string when none came."""
    out = {}
    for kind in P.KINDS:
        SLEEP(P.PACE_S)
        v, why = P.read(s, alpha, kind, sleep=SLEEP)
        out[kind] = v if v is not None else why
    return out


def _post_loop(s, queue, remaining, nov, history, SB, CS) -> list:
    posted, held = [], collections.Counter()
    today = SUB.today_dataset_sets(history, time.time())
    curves = {}

    def curve_of(a):
        if a not in curves:
            curves[a] = HV.cached_curve(a, curves_dir=CURVES) or SCP.pnl(s, a, budget=CURVE_BUDGET_S)
        return curves[a]
    while remaining > 0 and queue:
        pick, queue = queue[0], queue[1:]
        fresh = _fresh(s, pick["alpha"])
        numeric = all(isinstance(fresh[k], (int, float)) and not isinstance(fresh[k], bool) for k in P.KINDS)
        if numeric:
            P.append_corr([dict(fresh, alpha=pick["alpha"], read_at=time.time(), source="frames-submit-reread")],
                          path=CORR)
        pl, sl = pick["lines"]
        if not numeric:
            held["corr-fresh-unread"] += 1
            print("  %s: fresh correlation reading %s -- held for now" % (pick["alpha"], fresh))
            continue
        if not (fresh["prod"] < pl and fresh["self"] < sl):
            held["corr-over-line"] += 1
            print("  %s: fresh reading prod %s self %s against lines %s -- held" % (pick["alpha"], fresh["prod"], fresh["self"], (pl, sl)))
            continue
        pick["prod"], pick["self"] = fresh["prod"], fresh["self"]
        print("\nPOSTING %s (frame %s, prod %.3f, self %.3f, gain %.2f) -- irreversible" % (
            pick["alpha"], pick["frame_id"], pick["prod"], pick["self"], pick["cell_gain"]))
        try:
            SB.LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with SB.LEDGER.open("a") as fh:
                fh.write(json.dumps({"date": SB.platform_date(), "alpha": pick["alpha"], "source": LEDGER_SOURCE,
                                     "stage": "reserved", "reserved_at": time.time()}) + "\n")
        except OSError as exc:
            print("REFUSING TO POST: could not reserve a slot in the shared ledger (%s)" % exc)
            break
        http, body = CS.post(pick["alpha"], session=s)
        posted.append(pick["alpha"])
        record(pick, http, body)
        print("HTTP %s\n%s" % (http, (body or "")[:1500]))
        try:
            import msgcat as MC
            MC.send(MC.m6_post_outcome(pick["alpha"], http, time.time(), exc_class=(None if http is not None else "post-raised")))
        except Exception as exc:  # noqa: BLE001
            print("NOTIFY FAILED (%s: %s) -- the POST above still happened" % (type(exc).__name__, exc))
        remaining -= 1
        if http not in (200, 201):
            print("stopping after HTTP %s (not 200/201); the ledger holds the slot" % http)
            break
        today[pick["datasets"]] += 1
        queue = [e for e in queue if SUB.diversity_ok(e["datasets"], today)]
        if remaining > 0:                  # S11 reads curves only while another POST is possible
            queue, twins = pnl_twin_hold(pick["alpha"], queue, curve_of, SCP.predict)
            held.update(twins)
        if not nov.register(pick["row"].get("formula") or "", pick["alpha"]):
            print("  novelty: %s has no formula to register -- stopping rather than risk a twin" % pick["alpha"])
            break
        queue = [e for e in queue if nov.verdict(e["row"].get("formula") or "")[0] is False]
    if held:
        print("held while posting: %s" % dict(held))
    return posted


# ------------------------------------------------------------------------------------------- main
def main(journal=None, submit=False, cap=4) -> list:
    """Run the submit step over `journal` (default LOOP_JOURNAL); returns the alpha ids POSTed (any outcome)."""
    import submit_budget as SB
    rows, cands = candidates(journal or LOOP_JOURNAL)
    history = SUB.posted_history(paths=(POST_LOG, CLIMB_LOG), ledger=SB.LEDGER)
    nov = NV.build(history, rows)
    names = collections.defaultdict(set)
    for r in cands.values():
        names[_cell(r.get("settings"))].update(OPS.fields_in(r.get("formula") or ""))
    cats = {cell: field_rows(cell, ns) for cell, ns in names.items()}
    try:
        pair_counts = C.load_pair_counts(PAIR_COUNTS)
    except (OSError, ValueError, KeyError, TypeError):
        pair_counts = {}
    queue, held = eligible(cands, history, nov, SUB.meaning_gate(), cats, pair_counts, P.load_corr(CORR))
    print("frames submit: %d loop row(s), %d at D24, %d eligible; held %s; novelty index over %d POST(s)%s" % (
        len(rows), len(cands), len(queue), dict(held), len(nov),
        "" if nov.complete else ", FORMULA MISSING for %s" % nov.missing))
    for e in queue:
        print("  %-10s frame %s route %s gain %.2f stored prod %s self %s datasets %s" % (
            e["alpha"], e["frame_id"], e["route"], e["cell_gain"], e["prod"], e["self"], e["datasets"]))
    if not submit:
        print("would POST, in this order, each only after a fresh correlation reading under its lines, the shared "
              "budget, the 403 budget and S11: %s" % ([e["alpha"] for e in queue] or "nothing"))
        print("nothing posted. --submit is the only path that POSTs.")
        return []
    n403 = SUB.recent_403(history)
    if n403 > SUB.MAX_403_PER_WEEK:
        print("HOLD-FOR-APPROVAL: %d refusals (403) in the last 7 days exceed the budget of %d. Nothing posted."
              % (n403, SUB.MAX_403_PER_WEEK))
        return []
    if not queue:
        print("nothing eligible; nothing posted")
        return []
    import fcntl
    import layered_sim as LS
    import climb_submit as CS
    s = LS.session()
    with open(SUB.SUBMIT_LOCK, "a+") as lockf:
        try:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another submitter holds %s; refusing to POST" % SUB.SUBMIT_LOCK)
            return []
        try:
            budget = SB.remaining_today(session=s)
            remaining = min(int(budget.get("remaining") or 0), cap)
        except Exception as exc:  # noqa: BLE001
            print("REFUSING TO POST: shared submit budget unreadable (%s: %s)" % (type(exc).__name__, exc))
            return []
        print("shared budget: %s" % budget.get("why"))
        if remaining <= 0:
            print("no submit slot left today; nothing posted")
            return []
        return _post_loop(s, queue, remaining, nov, history, SB, CS)


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)  # `--sub` is not `--submit`
    ap.add_argument("--journal", default=None, help="the loop journal (default state/layered/runs/frames_loop.jsonl)")
    ap.add_argument("--submit", action="store_true", help="ACTUALLY POST. Irreversible: a 403 spends the alpha forever.")
    ap.add_argument("--cap", type=int, default=4, help="max POSTs this invocation (the shared daily budget still binds)")
    a = ap.parse_args(argv)
    posted = main(a.journal, submit=a.submit, cap=a.cap)
    print("posted %d%s" % (len(posted), (": " + ", ".join(posted)) if posted else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
