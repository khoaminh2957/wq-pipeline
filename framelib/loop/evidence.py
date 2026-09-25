"""The frames loop's evidence ledger (docs/frames/00_decisions.md F5-F9). POST-HOC counts, never a verdict.

    python -m framelib.loop.evidence [--state DIR] [--library DIR]            read, print totals, write nothing
    python -m framelib.loop.evidence --update [--state DIR] [--library DIR]   also write everything below

WRITES (--update; every file is rebuilt from the sources, so a second run gives the same bytes):
  state/frames/evidence.jsonl       one line per (frame_id, ET day, route): the ledger
  state/frames/daily.jsonl          one line per ET day: counts per route, all-check passes, submissions (F6 text)
  state/frames/frames_summary.json  per frame: totals, per-route totals, days, and a Beta posterior on y08
  state/frames/plans/<sha16>.json   a copy of the loop's plan file (the dispatcher rewrites it every round)
  library entries                   evidence.live (the schema.py format). status, history, approval and
                                    version are never touched (a status change needs Khoa's tick)
Exit 0; 3 when the ledger was written but a library entry refused the live block (each one is printed).

SOURCES (read-only, under --state, default <repo>/state; on the VPS /opt/wq/state):
  layered/runs/frames_loop.jsonl     the loop journal; its plans are frames_loop.plan.json and the archive
  layered/runs/frames_r1b.jsonl      FRAMES-R1B + its .plan.json -> route "screen" (doc 13 section 0.5: R1 screens)
  layered/runs/frames_r2.jsonl       FRAMES-R2 + its .plan.json  -> route "replicate" (doc 13 section 7.1)
                                     R1B/R2 arms a and b only; arm c (non-library control) and arm d (the
                                     incumbent) are reported per day as "outside_ledger", never as frame evidence
  layered/runs/recovered.jsonl       orphan rows (see "outcome" below)
  layered/runs/frames_*.jsonl        every frames journal, read by used_fields only (a field that ran with a frame
                                     is used, whatever the round): FRAMES-R1 attempt 1 (excluded from evidence,
                                     00_decisions.md), FRAMES-R3S (13c: its own screen and line; outside the
                                     interface's ledger sources) and any later experiment journal
  forge/submitted.jsonl              the POST log framelib/loop/submit.py records in: its rows of source
                                     "frames-loop" are the loop's POSTs, with their http outcome
  submit_budget.jsonl                the shared 4/day ledger: its rows of source "frames_loop_submit" are the loop
                                     submitter's reservations (each made before its POST)

DEFINITIONS (fixed here, from the code that writes each source: EX-ANTE; a dated count quoted in one is POST-HOC):
  construction   (formula without spaces, settings json) exactly as analyse_round._key, within one round:
                 rows and plan entries are matched on (meta.round_seed, key), so a repeat in a later round is
                 its own construction. The constructions of a source = every entry of a plan that RAN (a child
                 row or a PARENT-POSTED formula of its round is in the journal; a dry-run plan never ran) plus
                 every child row with no plan entry (a plan overwritten before --update archived it)
  parent round   a PARENT-POSTED row carries its formulas and no meta; its round is the one round_seed whose
                 constructions hold every one of those formulas (none or several: "parents_unassigned")
  outcome        analyse_round.outcome of the journal's last row; else of a recovered.jsonl row; else "missing".
                 A recovered row is used when the journal has no row, or has a POLL-* row (layered_sim stopped
                 reading that simulation: POLL-DEADLINE "at the round deadline", POLL-EXHAUSTED -- no outcome
                 was read; DESIGN CHOICE, analyse_round lets the journal row win there too). It matches:
                   * a row WITH settings: by analyse_round._key, as analyse_round does;
                   * a row WITHOUT settings -- what tools/recover_harvest.py and tools/recover_parents.py write
                     (settings None; 16,468 of 16,468 rows of recovered.jsonl on 2026-09-25), which analyse_round's
                     key can never match: by (parent_url, formula without spaces), when that parent is a
                     PARENT-POSTED row of this journal assigned to the construction's round, and the formula is
                     one construction of that round (else "recovered_ambiguous", not used: the two members of an
                     F10 pair share formula and parent, so a settings-less row of a pair member is never used)
  n_scored       COMPLETE / WARNING;  n_error  ERROR;  n_cancelled  CANCELLED / CANCELED;  n_missing  no row;
                 n_other  any other status (POST-4xx, AUTH-FAIL, POLL-*, FAIL, GUARD-REFUSED), named in "statuses".
                 n_planned = n_scored + n_error + n_cancelled + n_other + n_missing
  n_unposted     of n_missing: never sent (the dispatcher stopped first: a round deadline, the daily limit, a
                 401/403, a crash). A formula planned k times in a round and named j times by that round's
                 PARENT-POSTED rows has max(0, k - j) unsent constructions, taken from those with no row in plan
                 order (a parent row names formulas, not settings). In the loop k = 1, or 2 for an F10 pair, whose
                 members share a parent (framelib/loop/plan.py), so both are sent or neither. FRAMES-R2: 180 =
                 1,070 planned - 89 parents x 10, after "ROUND DEADLINE at 75 min" in frames-r2.log (2026-09-25).
                 In R1B and R2 no repeated formula spans two frames, so each ledger row's n_unposted is exact; the
                 by_arm split is not where a formula repeats across arms (R2: 131 / 49 here, 130 / 50 by matching
                 each parent to its window of the plan)
  by_pair_member the row's counts split by meta.pair_member (F10: "profile" | "reference"); rows outside a pair
                 are in no member. Counts only: which fill pairs with which is in the journal (meta.pair_id)
  y08 / ls / d24 counts over scored rows (analyse_round.outcome): Sharpe >= 0.8 x its LOW_SHARPE limit /
                 LOW_SHARPE PASS / all 7 binding checks PASS
  day            meta.plan_day (ET) when present, else the most frequent ET date of the round's scored
                 dateCreated, else "unknown" (kept in the ledger, left out of the library block)
  y08_beta       DESIGN CHOICE: prior Beta(1, 1); a = 1 + y08, b = 1 + n_scored - y08 over every route and day.
                 The counts are next to it, so a planner can apply another prior
"""
from __future__ import annotations

import argparse
import collections
import datetime as DT
import hashlib
import json
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

from framelib import store as ST
from framelib.experiments import analyse_round as AR

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
ET = ZoneInfo("America/New_York")
ROUTES = ("screen", "replicate", "production")
LEGACY = (("r1b", "FRAMES-R1B", "screen"), ("r2", "FRAMES-R2", "replicate"))
LIBRARY_ARMS = ("a", "b")
COUNTS = ("n_planned", "n_scored", "n_error", "n_cancelled", "n_other", "n_missing", "n_unposted", "n_recovered",
          "y08", "ls", "d24")
PRIOR = (1, 1)
POLL = "POLL-"                                  # layered_sim: a simulation it stopped reading
POST_SOURCE = "frames-loop"                     # framelib/loop/submit.py SOURCE (its rows in forge/submitted.jsonl)
RESERVE_SOURCE = "frames_loop_submit"           # framelib/loop/submit.py LEDGER_SOURCE (submit_budget.jsonl)
F6_NOTE = ("F6 (docs/frames/00_decisions.md): no control arm runs on these days. Any comparison of these counts "
           "with the incumbent is DESCRIPTIVE (its history, other days), not RULE 2 gate-3 evidence.")
# the comparison schema.py requires in evidence.live. Doc 13 section 2 (recorded before any FRAMES-R2 row);
# re-derived 2026-09-24 from the Mac copy of forge.jsonl with separate code: 1,126 / 9,111 = 0.1236
COMPARISON = {"arm": "incumbent history: forge.jsonl USA/d1/TOP3000, ET days 2026-09-20..2026-09-24, 1,126 y08 of "
                     "9,111 scored rows (doc 13 section 2); other days than the loop's, so DESCRIPTIVE (F6)",
              "y08_rate": 0.1236}


def paths(state=STATE) -> dict:
    s = pathlib.Path(state)
    runs, fr = s / "layered" / "runs", s / "frames"
    return {"runs": runs, "loop": runs / "frames_loop.jsonl", "r1": runs / "frames_r1.jsonl", "r1b": runs / "frames_r1b.jsonl",
            "r2": runs / "frames_r2.jsonl", "recovered": runs / "recovered.jsonl", "ledger": fr / "evidence.jsonl",
            "daily": fr / "daily.jsonl", "summary": fr / "frames_summary.json", "plans": fr / "plans",
            "submit": s / "submit_budget.jsonl", "posted": s / "forge" / "submitted.jsonl"}


def _lines(path):
    p = pathlib.Path(path)
    if not p.exists():
        return
    with open(p, errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                yield r


def _meta(r) -> dict:
    m = r.get("meta")
    return m if isinstance(m, dict) else {}


def et_day(ts):
    """ET date of an ISO timestamp that carries its offset; None when it cannot be told."""
    try:
        t = DT.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(ET).date().isoformat() if t.tzinfo else None


def _nospace(f) -> str:
    return str(f).replace(" ", "")


def _slim(r) -> dict:
    """What the ledger keeps of a row: its outcome, dateCreated and meta (a month of full rows would not fit)."""
    return {"o": AR.outcome(r), "date": r.get("dateCreated"), "meta": _meta(r)}


def _journal(path):
    """((round_seed, key) -> the last child row, slimmed; [(parent_url, [formula])] of its PARENT-POSTED rows).
    Child rows are filtered as analyse_round._rows filters them."""
    rows, parents = {}, []
    for r in _lines(path):
        if r.get("status") == "PARENT-POSTED":
            parents.append((r.get("parent_url"), [_nospace(f) for f in r.get("formulas") or ()]))
            continue
        st = r.get("settings") or {}
        if r.get("status") is None or not r.get("formula") or isinstance(st, str):
            continue
        rows[(_meta(r).get("round_seed"), AR._key(r["formula"], st))] = _slim(r)
    return rows, parents


def recovered_index(path) -> tuple:
    """(by_key, by_parent) of recovered.jsonl, the last row winning as in analyse_round._rows. by_key: rows that
    carry settings, keyed as analyse_round keys them. by_parent: rows without settings, (parent_url, formula)."""
    by_key, by_parent = {}, {}
    for r in _lines(path):
        if r.get("status") in (None, "PARENT-POSTED") or not r.get("formula"):
            continue
        st = r.get("settings")
        if isinstance(st, dict) and st:
            by_key[AR._key(r["formula"], st)] = _slim(r)
        elif not st and r.get("parent_url"):
            by_parent[(r["parent_url"], _nospace(r["formula"]))] = _slim(r)
    return by_key, by_parent


def _source(journal, plan_paths, experiment, legacy_route, recovered, report) -> list:
    rows, parents = _journal(journal)
    plans = []
    for pp in plan_paths:
        plan = json.loads(pathlib.Path(pp).read_text())
        plans.append((pp, [((_meta(c).get("round_seed"), AR._key(c["formula"], c["settings"])), _meta(c))
                           for c in plan.get("constructions") or []]))
    rounds_of = collections.defaultdict(set)                 # formula -> the rounds that hold it
    for rs, key in [k for _, items in plans for k, _ in items] + list(rows):
        rounds_of[key[0]].add(rs)
    posted = collections.defaultdict(list)                   # (round_seed, formula) -> its parents' urls
    for url, forms in parents:
        rs = set.intersection(*(rounds_of.get(f, set()) for f in forms)) if forms else set()
        if len(rs) != 1:
            report["parents_unassigned"] += 1
            continue
        for f in forms:
            posted[(next(iter(rs)), f)].append(url)
    cons = {}
    for pp, items in plans:
        if not any(k in rows or (k[0], k[1][0]) in posted for k, _ in items):
            report["plans_not_run"].append(str(pp))
            continue
        report["plans_counted"].append(str(pp))
        for k, m in items:
            cons.setdefault(k, m)
    for k, r in rows.items():
        cons.setdefault(k, r["meta"])
    days = collections.defaultdict(collections.Counter)
    for (rs, _), r in rows.items():
        d = et_day(r["date"])
        if d:
            days[rs][d] += 1
    modal = {rs: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for rs, c in days.items()}
    per_formula = collections.Counter((rs, key[0]) for rs, key in cons)
    # a formula planned k times in a round and posted j times: k - j of its constructions were never sent (one
    # formula can be planned at several settings, and a parent row names formulas, not settings)
    unsent = {g: max(0, k - len(posted.get(g, ()))) for g, k in per_formula.items()}
    by_key, by_parent = recovered
    out = []
    for (rs, key), m in cons.items():
        f = key[0]
        row, rec = rows.get((rs, key)), False
        if row is None or str(row["o"]["status"]).startswith(POLL):
            hit = by_key.get(key)
            hits = [by_parent[(u, f)] for u in posted.get((rs, f), ()) if (u, f) in by_parent]
            if hit is None and hits:
                if per_formula[(rs, f)] == 1:
                    hit = hits[-1]
                else:
                    report["recovered_ambiguous"] += 1
            if hit is not None:
                row, rec = hit, True
        unposted = row is None and unsent[(rs, f)] > 0
        unsent[(rs, f)] -= unposted
        arm = m.get("arm")
        route = (legacy_route if arm in LIBRARY_ARMS else None) if legacy_route else m.get("route")
        fid = m.get("frame_id")
        out.append({**(row["o"] if row else AR.outcome(None)), "source": experiment, "frame_id": fid, "route": route,
                    "arm": arm, "day": m.get("plan_day") or modal.get(rs) or "unknown",
                    "frame_version": m.get("frame_version"), "fill": [x for x in (m.get("fill") or ()) if x],
                    "recovered": rec, "unposted": unposted, "pair_member": m.get("pair_member"),
                    "in_ledger": bool(fid) and route in ROUTES})
    return out


def _plans(p) -> list:
    """The loop's plan files: the archive and the dispatcher's current one, one per content."""
    seen, out = set(), []
    live = p["loop"].with_suffix(".plan.json")
    for pp in sorted(p["plans"].glob("*.json")) + ([live] if live.exists() else []):
        h = hashlib.sha256(pp.read_bytes()).hexdigest()
        if h not in seen:
            seen.add(h)
            out.append(pp)
    return out


def constructions(state=STATE) -> tuple:
    """(every construction of every source, report of which plan files counted)."""
    p = paths(state)
    recovered = recovered_index(p["recovered"])
    report = {"plans_counted": [], "plans_not_run": [], "parents_unassigned": 0, "recovered_ambiguous": 0}
    recs = _source(p["loop"], _plans(p), "FRAMES-LOOP", None, recovered, report)
    for name, experiment, route in LEGACY:
        if p[name].exists():
            plan = p[name].with_suffix(".plan.json")
            recs += _source(p[name], [plan] if plan.exists() else [], experiment, route, recovered, report)
    return recs, report


def counts(recs) -> dict:
    c = dict.fromkeys(COUNTS, 0)
    for r in recs:
        c["n_planned"] += 1
        st = r["status"]
        k = ("n_scored" if r["scored"] else "n_missing" if st == "missing" else "n_error" if st == "ERROR"
             else "n_cancelled" if st in ("CANCELLED", "CANCELED") else "n_other")
        c[k] += 1
        c["n_unposted"] += int(r["unposted"])
        c["n_recovered"] += int(r["recovered"])
        for x in ("y08", "ls", "d24"):
            c[x] += r[x]
    return c


def _sum(rows) -> dict:
    return {k: sum(r[k] for r in rows) for k in COUNTS}


def ledger_rows(recs) -> list:
    g = collections.defaultdict(list)
    for r in recs:
        if r["in_ledger"]:
            g[(r["day"], r["route"], r["frame_id"])].append(r)
    out = []
    for (day, route, fid), rs in sorted(g.items()):
        arms, members = collections.defaultdict(list), collections.defaultdict(list)
        for r in rs:
            arms[str(r["arm"])].append(r)
            if r["pair_member"]:
                members[str(r["pair_member"])].append(r)
        out.append({"frame_id": fid, "day": day, "route": route, **counts(rs),
                    "statuses": dict(sorted(collections.Counter(str(r["status"]) for r in rs).items())),
                    "by_arm": {a: counts(v) for a, v in sorted(arms.items())},
                    "by_pair_member": {k: counts(v) for k, v in sorted(members.items())},
                    "experiments": sorted({r["source"] for r in rs}),
                    "frame_versions": sorted({r["frame_version"] for r in rs if isinstance(r["frame_version"], int)}),
                    "fields": sorted({f for r in rs for f in r["fill"]}),
                    "d24_alphas": sorted(r["alpha"] for r in rs if r["d24"] and r["alpha"])})
    return out


def outside_rows(recs) -> list:
    g = collections.defaultdict(list)
    for r in recs:
        if not r["in_ledger"]:
            g[(r["day"], "%s/%s" % (r["source"], r["arm"] or r["route"] or "-"))].append(r)
    return [{"day": d, "what": w, **counts(rs)} for (d, w), rs in sorted(g.items())]


def summary(ledger) -> dict:
    """frame_id -> totals, per-route totals, days, fields used, and the y08 Beta posterior (DESIGN CHOICE prior)."""
    by = collections.defaultdict(list)
    for r in ledger:
        by[r["frame_id"]].append(r)
    out = {}
    for fid, rows in sorted(by.items()):
        tot = _sum(rows)
        a, b = PRIOR[0] + tot["y08"], PRIOR[1] + tot["n_scored"] - tot["y08"]
        out[fid] = {"total": tot, "by_route": {rt: _sum([r for r in rows if r["route"] == rt])
                                               for rt in sorted({r["route"] for r in rows})},
                    "days": sorted({r["day"] for r in rows}), "n_fields": len({f for r in rows for f in r["fields"]}),
                    "y08_beta": {"prior": list(PRIOR), "a": a, "b": b, "mean": round(a / (a + b), 4)}}
    return out


def submissions(post_log, budget) -> list:
    """The loop submitter's POSTs (its rows in forge's POST log: ET day of posted_at, http) and reservations (its
    rows in the shared 4/day ledger: their ET date; a reservation is written before its POST)."""
    out = []
    for r in _lines(post_log):
        if r.get("source") == POST_SOURCE and r.get("alpha") and isinstance(r.get("posted_at"), (int, float)):
            out.append({"kind": "post", "day": DT.datetime.fromtimestamp(r["posted_at"], ET).date().isoformat(),
                        "alpha": r["alpha"], "http": r.get("http")})
    for r in _lines(budget):
        if r.get("source") == RESERVE_SOURCE and r.get("alpha") and isinstance(r.get("date"), str):
            out.append({"kind": "reserved", "day": r["date"], "alpha": r["alpha"]})
    return out


def daily(ledger, outside, subs) -> list:
    out = []
    for day in sorted({r["day"] for r in ledger} | {r["day"] for r in outside} | {s["day"] for s in subs}):
        rows = [r for r in ledger if r["day"] == day]
        passes = sorted(a for r in rows for a in r["d24_alphas"])
        posts = [s for s in subs if s["day"] == day and s["kind"] == "post"]
        out.append({"day": day, "label": "DESCRIPTIVE", "note": F6_NOTE,
                    "routes": {rt: dict(_sum([r for r in rows if r["route"] == rt]),
                                        n_frames=len({r["frame_id"] for r in rows if r["route"] == rt}))
                               for rt in sorted({r["route"] for r in rows})},
                    "all_check_passes": {"n": len(passes), "alphas": passes},
                    "submissions": {
                        "n_posted": len(posts), "posted": sorted(s["alpha"] for s in posts),
                        "accepted": sorted(s["alpha"] for s in posts if s["http"] in (200, 201)),
                        "by_http": dict(sorted(collections.Counter(str(s["http"]) for s in posts).items())),
                        "reserved": sorted(s["alpha"] for s in subs if s["day"] == day and s["kind"] == "reserved"),
                        "source": "POSTs: forge/submitted.jsonl rows of source %s (ET day of posted_at); reserved: "
                                  "submit_budget.jsonl rows of source %s" % (POST_SOURCE, RESERVE_SOURCE)},
                    "outside_ledger": {r["what"]: {k: r[k] for k in COUNTS} for r in outside if r["day"] == day}})
    return out


def build(state=STATE) -> dict:
    recs, report = constructions(state)
    ledger = ledger_rows(recs)
    outside = outside_rows(recs)
    p = paths(state)
    return {"ledger": ledger, "outside": outside, "summary": summary(ledger),
            "daily": daily(ledger, outside, submissions(p["posted"], p["submit"])), "report": report}


def live_block(rows, ledger_path, ledger_sha) -> dict:
    """evidence.live in the format schema.py validates. Rows with day "unknown" stay in the ledger only."""
    return {"label": "POST-HOC", "criterion": "y08", "source": {"path": str(ledger_path), "sha256": ledger_sha},
            "comparison": dict(COMPARISON),
            "rows": [{k: v for k, v in r.items() if k != "frame_id"} for r in rows if r["day"] != "unknown"]}


def write_library(ledger, root, ledger_path, ledger_sha) -> dict:
    """Put each frame's ledger rows into its entry's evidence.live; nothing else of the entry changes."""
    by = collections.defaultdict(list)
    for r in ledger:
        by[r["frame_id"]].append(r)
    entries = ST.read_all(root)
    rep = {"written": [], "unchanged": 0, "refused": {}, "not_in_library": []}
    for fid, rows in sorted(by.items()):
        old = entries.get(fid)
        if old is None:
            rep["not_in_library"].append(fid)
            continue
        e = json.loads(json.dumps(old))
        e["evidence"] = dict(e["evidence"] or {}, live=live_block(rows, ledger_path, ledger_sha))
        if ST.dumps(e) == ST.dumps(old):
            rep["unchanged"] += 1
            continue
        try:
            ST.save(e, root)
            rep["written"].append(fid)
        except ST.LibraryError as exc:
            rep["refused"][fid] = exc.problems.get(fid) or [str(exc)]
    return rep


def _write(path, text) -> None:
    p = pathlib.Path(path)
    if p.exists() and p.read_text() == text:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def archive_plan(state=STATE):
    """Copy the loop's current plan into state/frames/plans/<sha256[:16]>.json (once per content)."""
    p = paths(state)
    live = p["loop"].with_suffix(".plan.json")
    if not live.exists():
        return None
    data = live.read_bytes()
    dst = p["plans"] / ("%s.json" % hashlib.sha256(data).hexdigest()[:16])
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dst)
    return dst


def update(state=STATE, library=ST.LIBRARY) -> dict:
    p = paths(state)
    archive_plan(state)
    b = build(state)
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in b["ledger"])
    _write(p["ledger"], text)
    _write(p["daily"], "".join(json.dumps(r, sort_keys=True) + "\n" for r in b["daily"]))
    _write(p["summary"], json.dumps(b["summary"], sort_keys=True, indent=1) + "\n")
    b["library"] = write_library(b["ledger"], library, p["ledger"], hashlib.sha256(text.encode()).hexdigest())
    return b


_USED = {}


def _used_sources(p) -> list:
    """Every frames journal (layered/runs/frames_*.jsonl: the loop, R1 attempt 1, R1B, R2, FRAMES-R3S and any later
    experiment's), then the ledger."""
    return sorted(p["runs"].glob("frames_*.jsonl")) + [p["ledger"]]


def used_fields_map(state=STATE) -> dict:
    """frame_id -> every field used with it: meta.fill of every row of every frames journal (any status; attempt 1
    and experiments outside the ledger included) and the fields of every ledger row (which also holds planned
    constructions that have no row)."""
    p = paths(state)
    out = collections.defaultdict(set)
    for j in _used_sources(p)[:-1]:
        for r in _lines(j):
            m = _meta(r)
            if m.get("frame_id"):
                out[m["frame_id"]].update(f for f in (m.get("fill") or ()) if f)
    for r in _lines(p["ledger"]):
        out[r["frame_id"]].update(r.get("fields") or ())
    return dict(out)


def used_fields(frame_id, state=STATE) -> set:
    """The fields already used with this frame (the planner never reuses one). Re-read when a source changes."""
    p = paths(state)
    sig = tuple((str(x), x.stat().st_size, x.stat().st_mtime_ns) if x.exists() else (str(x),)
                for x in _used_sources(p))
    if _USED.get("sig") != sig:
        _USED.update(sig=sig, map=used_fields_map(state))
    return set(_USED["map"].get(frame_id, ()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="write the ledger, reports, plan archive and library")
    ap.add_argument("--state", default=str(STATE))
    ap.add_argument("--library", default=str(ST.LIBRARY))
    a = ap.parse_args(argv)
    b = update(a.state, a.library) if a.update else build(a.state)
    tot = _sum(b["ledger"]) if b["ledger"] else dict.fromkeys(COUNTS, 0)
    rep = {"written": a.update, "ledger_rows": len(b["ledger"]), "frames": len(b["summary"]), "ledger_totals": tot,
           "outside_ledger": _sum(b["outside"]) if b["outside"] else {}, "days": [d["day"] for d in b["daily"]],
           **b["report"]}
    if a.update:
        lib = b["library"]
        rep["library"] = {"written": len(lib["written"]), "unchanged": lib["unchanged"],
                          "not_in_library": len(lib["not_in_library"]), "refused": lib["refused"]}
    print(json.dumps(rep, indent=1, sort_keys=True))
    if a.update and b["library"]["refused"]:
        print("LIBRARY REFUSED evidence.live for %d entr(ies): %s" % (len(b["library"]["refused"]),
              ", ".join(sorted(b["library"]["refused"]))), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
