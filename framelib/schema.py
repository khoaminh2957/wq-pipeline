"""The library entry: its fields, how each derived field is computed, and the validator.

ENTRY (one JSON file per frame):
  schema_version   SCHEMA_VERSION
  id               "F" + sha1(text)[:12]; a different text is a different frame
  version          int >= 1; the builder bumps it whenever anything but `provenance.built_at` changes
  text             the frame in normal form (frames.py), slots $1..$n
  --- derived from text (the validator re-derives each and refuses a mismatch) ---
  canonical_key    FRAME SPEC v1 frame_key (pinned fields become slots)
  shape            canonical_key with numbers as '#'
  slots            [{"slot": "$k", "context": MATRIX|VECTOR|GROUP, "positions": [[op, arg], ...]}], each optionally
                   with a GIVEN "role" (text) and "constraints" (compat.CONSTRAINT_KEYS; lists of allowed
                   values, exclude_datasets, vec_reducers_all, unit_eq "$j") from the proposal
  pinned           {canonical index: field}; cond_fields; groups; windows [[op, d], ...]
  characteristics  taxonomy.classify(text, evidence); family = combiner.conditioning.economic_function
  --- given ---
  settings         {"neutralization", "decay", "truncation", "universe": {region: u}, "source", ...} or {"source": "none"}
  provenance       {"origin": mined|novel|mined-dropped|mutation, "sources": [{"kind", "path", "sha256", "ref", ...}],
                   "built_by", "built_at"}, plus "parent" (a frame id) for a mutation
                   origin: "mined" iff the canonical corpus holds >= 1 row of this frame, "novel" iff it holds
                   none; "mined-dropped" (a mined frame the curator left out of the first 100) must hold >= 1
                   row too; "mutation" (made from its parent frame by the frames loop) may hold rows or not
  evidence         null, or evidence.block(...) (POST-HOC observed counts per cell, plus `reliability`), or
                   {"live": ...} alone for a frame with no canonical block; either form may carry `live`:
    live           the frames loop's rows of this frame (evidence ledger, one row per ET day and route), POST-HOC:
                   {"label": "POST-HOC", "criterion": "y08" (F7), "source": {"path", "sha256"},
                    "comparison": {"arm": what the y08 rate is compared with (F6: descriptive), "y08_rate": 0..1},
                    "rows": [{"day": "YYYY-MM-DD" (ET), "route": screen|replicate|production, "n_planned",
                              "n_scored", "n_error", "n_cancelled", "y08", "ls", "d24" (counts), "fields": [ids]}]}
  status           candidate | validated | retired
  status_history   [{"status", "at", "by", "reason"}], last entry == status
  approval         null, or {"by", "at", "ref"} -- the operator's tick (CLAUDE.md RULE 2). Whatever the status, a
                   non-null approval must be Khoa's dated tick (by in APPROVERS, at a date, ref), and it is refused
                   on an entry whose status_history never held `validated` (12 B3: an approval records that tick)
  notes            free text for humans

  evidence.reliability.rounds (canonical block; nothing writes rounds yet): each (round, date) at most once and
                   each comparison_arm naming an arm (not empty, not 'none') -- 12 B3's copied rounds and arm "none"

STATUS RULES (validate() enforces them):
  candidate  the default for every built entry
  validated  (phase-A audit B3; doc 13 section 7.3 and tick question Q5 option A) counted over evidence.live rows
             of route "production" only -- screen and replicate rows selected the frame, so they never count:
             >= MIN_ROUNDS distinct ET days, >= MIN_FRESH_FILLS scored fills, >= MIN_D24 D24 rows, and a
             y08 rate (sum y08 / sum n_scored) strictly above comparison.y08_rate; AND approval.by in APPROVERS
             with approval.at a date and approval.ref. The three numbers are Q5 option A as written in doc 13;
             00_decisions.md records no tick on Q5, so they remain a DECISION FOR KHOA, not measured numbers.
             Fresh: no field of a production row appears in any other live row of the frame (the planner's rule:
             a field is used with a frame at most once). A row lists its fields as a set, so a reuse inside one
             (day, route) row is not visible here, and neither is a reuse of a canonical-history field.
  retired    the last status_history entry states a reason
"""
from __future__ import annotations

import collections
import datetime as DT
import hashlib
import re

from framelib import compat as CM
from framelib import evidence as EV
from framelib import frames as FR
from framelib import taxonomy as TX

SCHEMA_VERSION = 1
STATUSES = ("candidate", "validated", "retired")
ORIGINS = ("mined", "novel", "mined-dropped", "mutation")
HOLDS_ROWS = {"mined": True, "novel": False, "mined-dropped": True}   # mutation: either
MIN_ROUNDS = 3
MIN_FRESH_FILLS = 30
MIN_D24 = 1
APPROVERS = ("Khoa",)
CRITERION = "y08"
ROUTES = ("screen", "replicate", "production")
LIVE_KEYS = ("label", "criterion", "source", "comparison", "rows")
LIVE_COUNTS = ("n_planned", "n_scored", "n_error", "n_cancelled", "y08", "ls", "d24")
LIVE_ROW_KEYS = ("day", "route") + LIVE_COUNTS + ("fields",)
DERIVED = ("canonical_key", "shape", "slots", "pinned", "cond_fields", "groups", "windows")
REQUIRED = ("schema_version", "id", "version", "text") + DERIVED + (
    "characteristics", "settings", "provenance", "evidence", "status", "status_history", "approval", "notes")
SLOT_GIVEN = ("role", "constraints")
SETTINGS_KEYS = ("neutralization", "decay", "truncation", "universe", "source", "n_rows", "n_modal")


def frame_id(text: str) -> str:
    return "F" + hashlib.sha1(text.encode()).hexdigest()[:12]


def derive(text: str, evidence=None) -> dict:
    """Every field that is a function of the text (and, for turnover_class, of the evidence)."""
    n = FR.normalize(text)
    return {"id": frame_id(n.text), "text": n.text, "canonical_key": n.key, "shape": n.shape, "slots": n.slots,
            "pinned": {str(i): f for i, f in sorted(n.pinned.items())}, "cond_fields": list(n.cond_fields),
            "groups": list(n.groups), "windows": [list(w) for w in n.windows],
            "characteristics": TX.classify(n, evidence)}


def new_entry(text: str, *, sources: list, built_by: str, built_at: str, evidence=None, settings=None,
              slot_specs: dict | None = None, notes: str = "") -> dict:
    """slot_specs: {slot number: {"role": str, "constraints": {...}}} for the normal-form slots."""
    e = {"schema_version": SCHEMA_VERSION, "version": 1}
    e.update(derive(text, evidence))
    for k, spec in sorted((slot_specs or {}).items()):
        e["slots"][k - 1].update({x: spec[x] for x in SLOT_GIVEN if spec.get(x)})
    e.update({"settings": settings or {"source": "none"},
              "provenance": {"origin": "mined" if evidence and evidence.get("n_rows") else "novel",
                             "sources": list(sources), "built_by": built_by, "built_at": built_at},
              "evidence": evidence, "status": "candidate",
              "status_history": [{"status": "candidate", "at": built_at, "by": built_by, "reason": "built"}],
              "approval": None, "notes": notes})
    return e


def _check_evidence(ev, errs):
    for k in ("evidence_version", "label", "source", "n_rows", "n_fills", "cells", "reliability", "caveats"):
        if k not in ev:
            errs.append("evidence.%s missing" % k)
    if errs:
        return
    if ev["label"] != "POST-HOC":
        errs.append("evidence.label must be POST-HOC")
    if ev["evidence_version"] != EV.EVIDENCE_VERSION:
        errs.append("evidence_version %r is not %d; rebuild" % (ev["evidence_version"], EV.EVIDENCE_VERSION))
    for k in ("path", "sha256"):
        if not ev["source"].get(k):
            errs.append("evidence.source.%s missing" % k)
    if sum(c["n_rows"] for c in ev["cells"].values()) != ev["n_rows"]:
        errs.append("evidence: cell rows do not add up to n_rows")
    for cell, c in ev["cells"].items():
        if not (0 <= c["n_d24"] <= c["n_complete"] <= c["n_rows"]) or not (0 <= c["n_ge_0p8"] <= c["n_with_limit"] <= c["n_rows"]):
            errs.append("evidence.%s: counts out of order" % cell)
            continue
        if c["n_fills"] > c["n_rows"]:
            errs.append("evidence.%s: n_fills > n_rows" % cell)
        want = (round(c["n_d24"] / c["n_complete"], 4) if c["n_complete"] else None,
                EV.wilson_lower(c["n_d24"], c["n_complete"]),
                round(c["n_ge_0p8"] / c["n_with_limit"], 4) if c["n_with_limit"] else None,
                EV.wilson_lower(c["n_ge_0p8"], c["n_with_limit"]))
        if (c["d24_rate"], c["d24_wilson_lo95"], c["ge_0p8_rate"], c["ge_0p8_wilson_lo95"]) != want:
            errs.append("evidence.%s: a rate does not match its counts" % cell)
    rel = ev["reliability"]
    if rel.get("verdict") not in EV.VERDICTS:
        errs.append("reliability.verdict %r not in %s" % (rel.get("verdict"), EV.VERDICTS))
    elif rel["verdict"] != "UNMEASURED":
        if not rel.get("method"):
            errs.append("reliability: a verdict needs a method")
        seen = set()
        for i, r in enumerate(rel.get("rounds") or []):
            miss = [k for k in EV.ROUND_KEYS if r.get(k) in (None, "")]
            if miss:
                errs.append("reliability.rounds[%d] missing %s" % (i, miss))
                continue
            if not _names_arm(r["comparison_arm"]):
                errs.append("reliability.rounds[%d].comparison_arm %r must name what the effect is compared with (12 B3)"
                            % (i, r["comparison_arm"]))
            key = (repr(r["round"]), repr(r["date"]))
            if key in seen:
                errs.append("reliability.rounds[%d]: round %r of %r repeats (12 B3: a copied round is not a new round)"
                            % (i, r["round"], r["date"]))
            seen.add(key)


def _names_arm(x) -> bool:
    return isinstance(x, str) and x.strip().lower() not in ("", "none")


def _is_count(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def _is_day(x) -> bool:
    try:
        return isinstance(x, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", x)) and bool(DT.date.fromisoformat(x))
    except ValueError:
        return False


def _is_date(x) -> bool:
    try:
        return isinstance(x, str) and bool(DT.datetime.fromisoformat(x))
    except ValueError:
        return False


def _check_live(lv, errs):
    """The structure of evidence.live, whatever the status."""
    if not isinstance(lv, dict):
        errs.append("evidence.live must be an object")
        return
    miss = [k for k in LIVE_KEYS if k not in lv]
    if miss:
        errs.append("evidence.live missing %s" % miss)
        return
    if lv["label"] != "POST-HOC":
        errs.append("evidence.live.label must be POST-HOC")
    if lv["criterion"] != CRITERION:
        errs.append("evidence.live.criterion must be %r (F7)" % CRITERION)
    if not (isinstance(lv["source"], dict) and all(lv["source"].get(k) for k in ("path", "sha256"))):
        errs.append("evidence.live.source needs path and sha256")
    cmp_ = lv["comparison"] if isinstance(lv["comparison"], dict) else {}
    arm, rate = cmp_.get("arm"), cmp_.get("y08_rate")
    if not _names_arm(arm):
        errs.append("evidence.live.comparison.arm must name what the rate is compared with (not empty, not 'none')")
    if not (isinstance(rate, (int, float)) and not isinstance(rate, bool) and 0 <= rate <= 1):
        errs.append("evidence.live.comparison.y08_rate must be a number in [0, 1]")
    if not isinstance(lv["rows"], list):
        errs.append("evidence.live.rows must be a list")
        return
    seen = set()
    for i, r in enumerate(lv["rows"]):
        at = "evidence.live.rows[%d]" % i
        miss = [k for k in LIVE_ROW_KEYS if k not in r] if isinstance(r, dict) else list(LIVE_ROW_KEYS)
        if miss:
            errs.append("%s missing %s" % (at, miss))
            continue
        if not _is_day(r["day"]):
            errs.append("%s.day %r is not a date YYYY-MM-DD" % (at, r["day"]))
        if r["route"] not in ROUTES:
            errs.append("%s.route %r not in %s" % (at, r["route"], ROUTES))
        if not (isinstance(r["fields"], list) and all(isinstance(f, str) and f for f in r["fields"])):
            errs.append("%s.fields must be a list of field ids" % at)
        key = (repr(r["day"]), repr(r["route"]))
        if key in seen:
            errs.append("%s: day %r route %r repeats (one row per ET day and route)" % (at, r["day"], r["route"]))
        seen.add(key)
        if not all(_is_count(r[k]) for k in LIVE_COUNTS):
            errs.append("%s: counts must be ints >= 0" % at)
        elif not (r["d24"] <= r["ls"] <= r["n_scored"] and r["y08"] <= r["n_scored"]
                  and r["n_scored"] + r["n_error"] + r["n_cancelled"] <= r["n_planned"]):
            errs.append("%s: counts out of order" % at)


def _check_validated(e, live_ok, errs):
    """B3: what a `validated` entry must hold. live_ok: evidence.live exists and passed _check_live."""
    if not live_ok:
        errs.append("validated needs a valid evidence.live block (the frames loop's rows)")
    else:
        lv = e["evidence"]["live"]
        prod = [r for r in lv["rows"] if r["route"] == "production"]
        days = {r["day"] for r in prod}
        n = sum(r["n_scored"] for r in prod)
        d24 = sum(r["d24"] for r in prod)
        if len(days) < MIN_ROUNDS:
            errs.append("validated needs >= %d distinct production days in evidence.live, has %d" % (MIN_ROUNDS, len(days)))
        if n < MIN_FRESH_FILLS:
            errs.append("validated needs >= %d fresh scored fills on production days, has %d" % (MIN_FRESH_FILLS, n))
        if d24 < MIN_D24:
            errs.append("validated needs >= %d D24 row on production days, has %d" % (MIN_D24, d24))
        rate = sum(r["y08"] for r in prod) / n if n else None
        if rate is None or rate <= lv["comparison"]["y08_rate"]:
            errs.append("validated needs a positive y08 effect (F7): production y08 rate %s vs comparison %s"
                        % (None if rate is None else round(rate, 4), lv["comparison"]["y08_rate"]))
        uses = collections.Counter(f for r in lv["rows"] for f in set(r["fields"]))
        reused = sorted({f for r in prod for f in r["fields"] if uses[f] > 1})
        if reused:
            errs.append("validated needs fresh fills: %d field(s) of the production rows appear in another live row of "
                        "this frame (%s)" % (len(reused), ", ".join(reused[:5])))


def _check_tick(ap, errs):
    """RULE 2: the only approval the schema accepts is Khoa's dated tick, whatever the status."""
    ap = ap if isinstance(ap, dict) else {}
    if ap.get("by") not in APPROVERS:
        errs.append("approval.by %r is refused: an approval is Khoa's tick (RULE 2), approvers %s"
                    % (ap.get("by"), APPROVERS))
    if not _is_date(ap.get("at")):
        errs.append("approval.at must be the date of the tick, got %r" % ap.get("at"))
    if not ap.get("ref"):
        errs.append("approval.ref must say where the tick is recorded")


def validate(e: dict) -> list:
    """All the reasons this entry is invalid (empty list = valid)."""
    errs = ["missing key %s" % k for k in REQUIRED if k not in e]
    if errs:
        return errs
    if e["schema_version"] != SCHEMA_VERSION:
        return ["schema_version %r is not %d" % (e["schema_version"], SCHEMA_VERSION)]
    if not isinstance(e["version"], int) or isinstance(e["version"], bool) or e["version"] < 1:
        errs.append("version must be an int >= 1")
    try:
        d = derive(e["text"], e["evidence"])
    except FR.FrameError as exc:
        return errs + ["text: %s" % exc]
    stored = dict(e, slots=[{k: v for k, v in s.items() if k not in SLOT_GIVEN} for s in e["slots"]])
    for k in ("id", "text") + DERIVED + ("characteristics",):
        if stored[k] != d[k]:
            errs.append("%s does not match the text (stored %r, derived %r)" % (k, e[k], d[k]))
    for i, sl in enumerate(e["slots"], 1):
        cons = sl.get("constraints")
        if cons is None:
            continue
        if not isinstance(cons, dict) or set(cons) - set(CM.CONSTRAINT_KEYS):
            errs.append("slots[$%d].constraints: unknown keys %s" % (i, sorted(set(cons or {}) - set(CM.CONSTRAINT_KEYS))))
            continue
        for key, val in cons.items():
            if key == "unit_eq":
                if not (isinstance(val, str) and re.fullmatch(r"\$\d+", val) and 1 <= int(val[1:]) <= len(e["slots"])
                        and int(val[1:]) != i):
                    errs.append("slots[$%d].constraints.unit_eq %r is not another slot" % (i, val))
            elif not (isinstance(val, list) and val and all(isinstance(x, str) for x in val)):
                errs.append("slots[$%d].constraints.%s must be a non-empty list of strings" % (i, key))
    for dim, allowed in TX.DIMENSIONS.items():
        if e["characteristics"].get(dim) not in allowed:
            errs.append("characteristics.%s %r not in the taxonomy" % (dim, e["characteristics"].get(dim)))
    st = e["settings"]
    if not isinstance(st, dict) or st.get("source") not in ("none", "canonical-modal", "designer"):
        errs.append("settings.source must be none | canonical-modal | designer")
    elif set(st) - set(SETTINGS_KEYS):
        errs.append("settings has unknown keys %s" % sorted(set(st) - set(SETTINGS_KEYS)))
    pv = e["provenance"]
    if pv.get("origin") not in ORIGINS:
        errs.append("provenance.origin must be one of %s" % (ORIGINS,))
    if not pv.get("sources"):
        errs.append("provenance.sources is empty: an entry must say where it came from")
    for i, s in enumerate(pv.get("sources") or []):
        miss = [k for k in ("kind", "path", "sha256", "ref") if not s.get(k)]
        if miss:
            errs.append("provenance.sources[%d] missing %s" % (i, miss))
    for k in ("built_by", "built_at"):
        if not pv.get(k):
            errs.append("provenance.%s missing" % k)
    ev = e["evidence"]
    mined = bool(ev and ev.get("n_rows"))
    if pv.get("origin") in ORIGINS and HOLDS_ROWS.get(pv.get("origin"), mined) != mined:
        errs.append("provenance.origin %r but the evidence holds %s canonical rows" % (pv.get("origin"), ev.get("n_rows") if ev else 0))
    if pv.get("origin") == "mutation" and not (isinstance(pv.get("parent"), str) and re.fullmatch(r"F[0-9a-f]{12}", pv["parent"])
                                               and pv["parent"] != e["id"]):
        errs.append("provenance.parent %r: a mutation must name its parent frame id (not its own)" % pv.get("parent"))
    live_ok = False
    if ev is not None:
        if set(ev) != {"live"}:
            _check_evidence(ev, errs)
        if "live" in ev:
            live_errs = []
            _check_live(ev["live"], live_errs)
            errs.extend(live_errs)
            live_ok = not live_errs
    if e["status"] not in STATUSES:
        errs.append("status %r not in %s" % (e["status"], STATUSES))
    hist = e["status_history"]
    if not hist or hist[-1].get("status") != e["status"]:
        errs.append("status_history must end with the current status")
    for i, h in enumerate(hist or []):
        miss = [k for k in ("status", "at", "by", "reason") if not h.get(k)]
        if miss:
            errs.append("status_history[%d] missing %s" % (i, miss))
    if e["status"] == "validated":
        _check_validated(e, live_ok, errs)
    if e["status"] == "validated" or e["approval"] is not None:
        _check_tick(e["approval"], errs)
    if e["approval"] is not None and e["status"] != "validated" and not any(
            isinstance(h, dict) and h.get("status") == "validated" for h in hist or []):
        errs.append("approval is set on an entry that was never validated: an approval records Khoa's tick on "
                    "`validated` (12 B3)")
    return errs
