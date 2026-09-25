"""forge.submit — the submitter (design §8). Chooses what to POST among scored candidates with
measured correlations. The POST, the shared-ledger reservation, the flock and the m6 announce reuse
tools/climb_submit.py, tools/submit_budget.py and tools/msgcat.py unchanged.

ELIGIBLE (C21 — nothing more, nothing less, for a library composite; D39 amends C21 for a generated one, below):
  stage == candidate (platform PASS, turnover band, DSR >= 0.95)
  ∧ prod and self correlation MEASURED and under the platform lines (row limits, else 0.7)
  ∧ MATCHES_PYRAMID PASS on the row
  ∧ mechanism_key not POSTed in the last 7 days (C19)      ∧ alpha never POSTed (one POST, ever)
ORDER (C20): open pyramid cells first (need × multiplier), then robust score, then lower self corr.
SECOND-BEST (C16): within the winner's hypothesis, top two scores within 10% → the second is posted.
403 BUDGET (C29): more than MAX_403_PER_WEEK refusals in 7 days → hold-for-approval, nothing posted.
FRESH CORR (C29): a reading older than 30 min is re-read right before the POST; a re-read that is
empty or over a line skips that candidate for now.

GENERATED CANDIDATES (meta.hypothesis "gen:<family>", the judge's own test, benchmark.GENERATED_PREFIX;
either the scored record or the journal row saying so is enough). Every gate above runs for them
unchanged; AFTER all of them, three more, each failing closed (a hold, never a POST):
  D51        'd51-neighbours-pending' until the journal holds two one-setting neighbours of the row with a
             numeric Sharpe -- forge.gen.repair.existing_neighbours, the loop's copy of the judge's rule
             (benchmark.neighbourhood_stability, with the row's own version-card cohort as the planner
             counts it), so submit and the D51 planner cannot disagree on "two". Their values are not
             read: the judge grades robustness. A D51 neighbour row is itself `gen:` and meets the same
             hold (round 4 m19: C16 could POST a neighbour the judge reads UNPROVEN). Checked before
             meaning because meaning is the costly step (design 04 section 4.2: "anything costly only for
             alphas that are otherwise POSTable").
  D39/D52    forge.meaning.score, the row appended to state/forge/meaning.jsonl (forge.meaning.append).
             POST only when every decidable gate (G4's leg clause, G5-G8) is exactly true; G1-G3 are "not
             applicable" (D39) unless the row inherited a composite's text (inherited_from set), and then
             they must be true too (the task's reading of "not applicable unless inherited"; POST-HOC, the
             Mac library 2026-09-24: 0 of 94 composites carry a false G1-G3, so today this clause moves no
             verdict). The hold names each gate that is not true ('meaning:G4=false,G7=null'). append keeps
             the EARLIEST row per (alpha, formula sha), the one the judge grades (benchmark.meaning_index),
             so that recorded row must read true as well ('meaning-recorded:...'). Scoring that raises
             holds with the exception's class.
  S11        round 3 S11: after each ACCEPTED POST, every remaining generated pick whose PnL-predicted SELF
             against the just-POSTed alpha (tools/self_corr_predict.predict on the cached curves,
             forge.harvest.cached_curve; nothing is fetched) is at or over its SELF line is held for this
             invocation. No curve or no prediction holds too: no reading is not a verdict. Library picks
             are not touched (they behave as before this rule). POST-HOC, host read-only 2026-09-24: 37 of
             37 candidates and 4 of 5 accepted POSTs (not the climb-era mL516W9W) had a cached curve, and
             144 of 144 candidate x POST pairs gave a number (9 at >= 0.7), so the fail-closed branches are
             not what decides today.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
from forge import cells as C, harvest as HV, probe as P  # noqa: E402

LOG = ROOT / "state/forge/submitted.jsonl"
CLIMB_LOG = ROOT / "state/climb/submitted.jsonl"
CORR_LINE_DEFAULT = 0.7
WEEK_S = 7 * 86400
CORR_MAX_AGE_S = 30 * 60
MAX_403_PER_WEEK = 1
SECOND_BEST_TOL = 0.10
CAT_ALIAS = {"PV": "PRICEVOLUME"}
#: named so the fake-transport tests can run main() where /var/lock does not exist (macOS); the value is unchanged
SUBMIT_LOCK = "/var/lock/wq_submit.lock"
#: D39: benchmark.GENERATED_PREFIX, restated (the judged does not import the judge, Draw 4).
GENERATED_PREFIX = "gen:"
D51_PENDING = "d51-neighbours-pending"
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def corr_lines(row) -> tuple:
    """(prod_line, self_line) from the row's own check limits when numeric, else the default."""
    out = []
    ck = {c.get("name"): c for c in (row.get("checks") or []) if isinstance(c, dict)}
    for name in ("PROD_CORRELATION", "SELF_CORRELATION"):
        lim = (ck.get(name) or {}).get("limit")
        out.append(float(lim) if isinstance(lim, (int, float)) else CORR_LINE_DEFAULT)
    return tuple(out)


def posted_history(paths=(LOG, CLIMB_LOG), ledger=None) -> list:
    """Every POST this pipeline knows of: [{alpha, mechanism_key, posted_at, http, formula}]. The
    shared budget ledger contributes reservations (alpha + time) so a crash mid-POST still counts.

    `formula` is carried through because both logs already record the exact string that was POSTed
    and this projection used to drop it -- which left `forge.novelty` unable to read the structure of
    mL516W9W (climb era, no journal row) and, failing closed, holding every candidate forever.
    MEASURED on the VPS 2026-09-22."""
    out = []
    for p in paths:
        for r in HV.read_jsonl(p):
            if r.get("alpha"):
                out.append({"alpha": r["alpha"], "mechanism_key": r.get("mechanism_key"),
                            "posted_at": r.get("posted_at") or 0, "http": r.get("http"),
                            "formula": r.get("formula")})
    if ledger is not None:
        for r in HV.read_jsonl(ledger):
            if r.get("alpha") and r.get("stage") == "reserved":
                out.append({"alpha": r["alpha"], "mechanism_key": None,
                            "posted_at": r.get("reserved_at") or 0, "http": None})
    return out


def recent_403(history, now=None) -> int:
    now = now or time.time()
    return sum(1 for h in history if h.get("http") == 403 and now - (h.get("posted_at") or 0) <= WEEK_S)


def _norm(cat: str) -> str:
    c = "".join(ch for ch in str(cat).upper() if ch.isalnum())
    return CAT_ALIAS.get(c, c)


def cell_gain(pyramids, pair_counts) -> float:
    """Max over the alpha's cells of need × multiplier, need from the platform counter."""
    best = 0.0
    for p in pyramids or []:
        name = p.get("name") if isinstance(p, dict) else p
        mult = float(p.get("multiplier") or 1.0) if isinstance(p, dict) else 1.0
        try:
            region, d, cat = name.split("/")
            delay = int(d.lstrip("Dd"))
        except (ValueError, AttributeError):
            continue
        counts = pair_counts.get((region, delay), {})
        need = 0
        for k, v in counts.items():
            if _norm(k) == _norm(cat):
                need = max(0, C.UNLOCK_AT - int(v))
                break
        best = max(best, need * mult)
    return best


def quota_day(ts: float) -> str:
    """The platform's quota day (resets 00:00 America/New_York) that a timestamp falls in."""
    import datetime
    import zoneinfo
    return datetime.datetime.fromtimestamp(ts, zoneinfo.ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def datasets_of(mechanism_key: str | None) -> str:
    """The dataset part of a mechanism key: 'comp#ds1|ds2#USA/d1' -> 'ds1|ds2'."""
    parts = (mechanism_key or "").split("#")
    return parts[1] if len(parts) >= 2 else ""


def today_dataset_sets(history, now) -> collections.Counter:
    """{dataset set: accepted POSTs today (ET)} from the POST history."""
    today = quota_day(now)
    return collections.Counter(datasets_of(h.get("mechanism_key")) for h in history
                               if h.get("http") in (200, 201) and quota_day(h.get("posted_at") or 0) == today)


def diversity_ok(ds: str, today_sets) -> bool:
    """Khoa Q20 as a rule on one more POST: at most 2 of a day's submissions share a dataset set,
    and only one set may repeat -- so 4 submissions span >= 3 distinct sets (2+1+1). The same test
    runs before EVERY POST, including the second, third and fourth of one invocation."""
    n = today_sets.get(ds, 0)
    return not (n >= 2 or (n == 1 and any(v >= 2 for v in today_sets.values())))


def last_accepted_post(history) -> float:
    """posted_at of the latest accepted POST (200/201); 0 when none."""
    return max((h.get("posted_at") or 0 for h in history if h.get("http") in (200, 201)), default=0)


def needs_reread(read_at, now, last_post_at) -> bool:
    """A correlation reading is re-read right before the POST when it is older than CORR_MAX_AGE_S
    OR older than the last accepted POST: an alpha that went ACTIVE after the reading is not in it,
    and its siblings read self-corr 0.79-0.97 against it (qMWbdlmv vs vRk095rv: 0.9668, 22 re-reads
    on the VPS log). Necessary, not sufficient -- the platform may answer from its own cache."""
    read_at = read_at or 0
    return (now - read_at > CORR_MAX_AGE_S) or (read_at <= last_post_at)


def is_generated(x, row) -> bool:
    """D39's test on the scored record OR the journal row: either saying gen: applies the stricter gates."""
    return any(str(h or "").startswith(GENERATED_PREFIX) for h in (x.get("hypothesis"), (row.get("meta") or {}).get("hypothesis")))


def neighbour_index(rows) -> dict:
    """{forge.gen.repair.formula_key: [journal rows]}, the index existing_neighbours reads (as gen.state builds it)."""
    from forge.gen import repair as RP
    out = {}
    for r in rows.values():
        if r.get("alpha") and r.get("formula"):
            out.setdefault(RP.formula_key(r), []).append(r)
    return out


def d51_ready(row, index) -> bool:
    """D51: the journal holds RP.NEIGHBOURS (2) one-setting neighbours of `row` with a numeric Sharpe."""
    from forge.gen import repair as RP
    return len(RP.existing_neighbours(row, index)) >= RP.NEIGHBOURS


def meaning_reasons(mrow) -> list:
    """['G4=false', 'G7=null', ...]: the gates of a meaning row that keep a generated alpha from POSTing.
    D39: every decidable gate (G4-G8) must be exactly true; G1-G3 only when the row inherited a composite's
    text. A value that is not exactly true / false reads null, as benchmark._standard_gate reads it."""
    from forge import meaning as M
    gates = mrow.get("gates") if isinstance(mrow.get("gates"), dict) else {}
    want = M.DECIDABLE + (M.NOT_APPLICABLE if mrow.get("inherited_from") else ())
    return ["%s=%s" % (g, "false" if gates.get(g) is False else "null") for g in want if gates.get(g) is not True]


def meaning_gate(path=None, clock=time.time):
    """gate(alpha, row) -> None when D39 lets a generated alpha POST, else the hold reason. Scores with
    forge.meaning.score, appends the row (path None = meaning.LEDGER), and requires both the fresh row and
    the ledger's standing row for (alpha, formula sha) to pass meaning_reasons. forge.meaning is imported,
    and the journal-wide ledgers read, at the first call only, so a round with no generated candidate
    reads nothing new. The catalogue is read per candidate with `only` = every identifier in the formula
    (a superset of its fields, so no field of it reads missing: draw5 meaning M6). main() builds it before
    the --submit check, so a dry run appends rows too: a row records a scoring, not a POST."""
    cache = {}

    def gate(alpha, row):
        formula, settings = row.get("formula"), row.get("settings")
        if not (isinstance(formula, str) and formula and isinstance(settings, dict)):
            return "meaning-unscorable"
        try:
            from forge import meaning as M
            if "ledgers" not in cache:
                cache["ledgers"] = M.load_ledgers()
            cell = (settings.get("region"), settings.get("universe"), settings.get("delay"))
            cat = None if None in cell else M.load_catalogue(*cell, only=set(_IDENT.findall(formula)))
            mrow = M.score(formula, row.get("meta") or {}, cat, cache["ledgers"], alpha=alpha, settings=settings,
                           scored_at=clock())
            ledger, appended = M.append(mrow, path)
            standing = mrow if appended else next(
                (r for r in HV.read_jsonl(ledger) if isinstance(r, dict) and r.get("alpha") == alpha
                 and r.get("formula_sha") == mrow["formula_sha"]), None)
        except Exception as exc:  # noqa: BLE001 -- a hold, named and printed; never a POST
            print("  %s: meaning scoring raised %s: %s -- held" % (alpha, type(exc).__name__, exc))
            return "meaning-error:%s" % type(exc).__name__
        bad = meaning_reasons(mrow)
        if bad:
            return "meaning:" + ",".join(bad)
        if standing is None:
            return "meaning-recorded-row-unread"
        bad = meaning_reasons(standing)
        return ("meaning-recorded:" + ",".join(bad)) if bad else None
    return gate


def pnl_twin_hold(posted_alpha, elig, curve_of=None, predict=None):
    """Round 3 S11 -> (kept, Counter of hold reasons). After an accepted POST of `posted_alpha`, each
    remaining GENERATED entry is held when its predicted SELF against it is at or over the entry's own
    SELF line ('s11-pnl-twin'), when either cached curve is absent ('s11-curve-absent'), when the
    predictor gives no number ('s11-unpredictable') or raises ('s11-error:<class>'). Library entries pass
    through untouched, and with no generated entry left nothing is read."""
    kept, held = [], collections.Counter()
    if not any(is_generated(e, e["row"]) for e in elig):
        return list(elig), held
    try:
        curve_of = curve_of or HV.cached_curve
        if predict is None:
            import self_corr_predict as SCP
            predict = SCP.predict
        posted = curve_of(posted_alpha)
        for e in elig:
            if not is_generated(e, e["row"]):
                kept.append(e)
                continue
            mine = curve_of(e["alpha"])
            if not (isinstance(posted, dict) and posted and isinstance(mine, dict) and mine):
                held["s11-curve-absent"] += 1
                continue
            v, _n = predict(mine, posted)
            if not isinstance(v, (int, float)):
                held["s11-unpredictable"] += 1
            elif v >= e["lines"][1]:
                held["s11-pnl-twin"] += 1
            else:
                kept.append(e)
    except Exception as exc:  # noqa: BLE001 -- fail closed: every generated entry is held
        held = collections.Counter({"s11-error:%s" % type(exc).__name__: sum(1 for e in elig if is_generated(e, e["row"]))})
        kept = [e for e in elig if not is_generated(e, e["row"])]
    return kept, held


def eligible(scored, corr, rows, pair_counts, history, now=None, novelty=None, meaning=None):
    """(eligible list sorted for POST order, Counter of hold reasons).
    Khoa 2026-09-08 (harness5 Q19/Q20): the one-mechanism-per-week rule is GONE; the correlation
    lines alone separate siblings. In its place a DIVERSITY rule per quota day: at most 2 of a day's
    submissions may share a dataset set, and only one dataset set may repeat — so 4 submissions span
    ≥ 3 distinct dataset sets (2+1+1).
    `meaning`: meaning_gate()'s gate; None holds every generated candidate ('meaning-not-scored')."""
    now = now or time.time()
    posted_alphas = {h["alpha"] for h in history}
    today_sets = today_dataset_sets(history, now)
    out, held = [], collections.Counter()
    nb = None
    for a, x in scored.items():
        if x.get("stage") != "candidate":
            continue
        row = rows.get(a)
        if not row:
            held["no-journal-row"] += 1
            continue
        if a in posted_alphas:
            held["already-posted"] += 1
            continue
        if not any(isinstance(c, dict) and c.get("name") == "MATCHES_PYRAMID" and c.get("result") == "PASS"
                   for c in row.get("checks") or []):
            held["pyramid-not-pass"] += 1
            continue
        cr = corr.get(a, {})
        prod, self_ = cr.get("prod"), cr.get("self")
        if not (isinstance(prod, (int, float)) and isinstance(self_, (int, float))):
            held["corr-unmeasured"] += 1
            continue
        pl, sl = corr_lines(row)
        if prod >= pl or self_ >= sl:
            held["corr-over-line"] += 1
            continue
        # PBO (CSCV) of the candidate's pool (Khoa Q21): a failed pool is held; "insufficient" (N < 20)
        # does not block (00_agreements); "pending" waits for the curves the next harvest fetches;
        # NO verdict at all is held too (adversarial review 2026-09-08: a harvest killed before the
        # PBO stage must not let a candidate through unjudged).
        if x.get("pbo_pass") is False:
            held["pbo-fail"] += 1
            continue
        if x.get("pbo_status") is None:
            held["pbo-unjudged"] += 1
            continue
        if x.get("pbo_status") == "pending":
            held["pbo-pending"] += 1
            continue
        if not diversity_ok(datasets_of(x.get("mechanism_key")), today_sets):
            held["dataset-set-repeated-today"] += 1
            continue
        # Khoa 2026-09-22 (D18): never submit the structural family of something already submitted.
        # The index is built from the POSTed alphas' own formulas; an index that could not read one of
        # them does not mean "novel", so the whole round is held rather than risk a repeat (see
        # forge/novelty.py). On the VPS, against the complete journal, that branch is not expected to fire.
        if novelty is not None:
            if not novelty.complete:
                held["novelty-index-incomplete"] += 1
                continue
            repeat, sim, twin = novelty.verdict(row.get("formula") or "")
            if repeat is None:                       # no formula on the candidate: unknown, not novel
                held["novelty-candidate-unreadable"] += 1
                continue
            if repeat:
                held["structure-already-submitted"] += 1
                continue
            structural_sim = (sim, twin)
        else:
            structural_sim = (None, None)
        # D51, then D39/D52, for a generated candidate only (module docstring); library rows skip both
        if is_generated(x, row):
            if nb is None:
                nb = neighbour_index(rows)
            if not d51_ready(row, nb):
                held[D51_PENDING] += 1
                continue
            why = meaning(a, row) if meaning is not None else "meaning-not-scored"
            if why:
                held[why] += 1
                continue
        pyr = []
        for c in row.get("checks") or []:
            if isinstance(c, dict) and c.get("name") == "MATCHES_PYRAMID":
                pyr = c.get("pyramids") or []
        out.append({"alpha": a, "hypothesis": x.get("hypothesis"), "mechanism_key": x.get("mechanism_key"),
                    "score": float(x.get("score") or 0), "prod": prod, "self": self_, "read_at": cr.get("read_at") or 0,
                    "pyramids": pyr, "cell_gain": cell_gain(pyr, pair_counts), "row": row, "lines": (pl, sl),
                    "structural_sim": structural_sim[0], "structural_twin": structural_sim[1]})
    out.sort(key=lambda e: (-e["cell_gain"], -e["score"], e["self"]))
    return out, held


def choose(elig):
    """First in POST order, with the second-best rule applied inside its hypothesis (C16)."""
    if not elig:
        return None
    top = elig[0]
    same = sorted((e for e in elig if e["hypothesis"] == top["hypothesis"]), key=lambda e: -e["score"])
    if len(same) >= 2 and same[0]["score"] > 0 and (same[0]["score"] - same[1]["score"]) / same[0]["score"] < SECOND_BEST_TOL:
        return same[1]
    return top


def record(pick, http, body, path=LOG):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = pick["row"]
    with p.open("a") as fh:
        fh.write(json.dumps({
            "alpha": pick["alpha"], "formula": row.get("formula"), "hypothesis": pick["hypothesis"],
            "arm": (row.get("meta") or {}).get("arm"),
            "mechanism_key": pick["mechanism_key"], "datasets": datasets_of(pick["mechanism_key"]),
            "pyramids": [q.get("name") for q in pick["pyramids"]],
            "score": pick["score"], "prod_corr": pick["prod"], "self_corr": pick["self"],
            "sharpe": row.get("sharpe"), "fitness": row.get("fitness"), "turnover": row.get("turnover"),
            "http": http, "body": body, "posted_at": time.time(), "source": "forge"}) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)  # S7-NL: `--sub` is not `--submit`
    ap.add_argument("--submit", action="store_true", help="ACTUALLY POST. Irreversible: a 403 spends the alpha forever.")
    ap.add_argument("--cap", type=int, default=4, help="max POSTs this invocation (the shared daily budget still binds)")
    a = ap.parse_args(argv)
    import layered_sim as LS
    import submit_budget as SB
    import climb_submit as CS
    scored, corr, rows = HV.load_scored(), P.load_corr(), HV.forge_rows()
    pair_counts = C.load_pair_counts(ROOT / "state/pyramid_cell_counts.json")
    history = posted_history(ledger=SB.LEDGER)
    from forge import novelty as NV
    nov = NV.build(history, rows)
    print("forge submit: novelty index over %d submitted structure(s)%s" % (
        len(nov), "" if nov.complete else "; FORMULA MISSING for %s -- holding the round" % nov.missing))
    elig, held = eligible(scored, corr, rows, pair_counts, history, novelty=nov, meaning=meaning_gate())
    print("forge submit: %d candidate(s) scored, %d eligible; held %s" % (
        sum(1 for x in scored.values() if x.get("stage") == "candidate"), len(elig), dict(held)))
    for e in elig[:8]:
        print("  %-10s gain %.2f score %.3f prod %.3f self %.3f struct-sim %s %s %s" % (
            e["alpha"], e["cell_gain"], e["score"], e["prod"], e["self"],
            ("%.2f vs %s" % (e["structural_sim"], e["structural_twin"])) if e.get("structural_sim") else "-",
            e["hypothesis"], [q.get("name") for q in e["pyramids"]]))
    if not a.submit:
        print("nothing posted. --submit is the only path that POSTs.")
        return 0
    n403 = recent_403(history)
    if n403 > MAX_403_PER_WEEK:
        print("HOLD-FOR-APPROVAL: %d refusals (403) in the last 7 days exceed the budget of %d (C29). Nothing posted." % (n403, MAX_403_PER_WEEK))
        return 3
    s = LS.session()
    try:
        budget = SB.remaining_today(session=s)
    except Exception as exc:  # noqa: BLE001
        print("REFUSING TO POST: shared submit budget unreadable (%s: %s)" % (type(exc).__name__, exc))
        return 1
    print("shared budget: %s" % budget["why"])
    remaining = min(int(budget.get("remaining") or 0), a.cap)
    if remaining <= 0:
        print("no submit slot left today; nothing posted")
        return 0
    import fcntl
    lockf = open(SUBMIT_LOCK, "a+")
    try:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another submitter holds /var/lock/wq_submit.lock; refusing to POST")
        return 0
    posted = 0
    last_post_at = last_accepted_post(history)
    today_sets = today_dataset_sets(history, time.time())
    while remaining > 0:
        pick = choose(elig)
        if not pick:
            break
        elig = [e for e in elig if e["alpha"] != pick["alpha"]]
        if needs_reread(pick["read_at"], time.time(), last_post_at):
            fresh = {}
            for kind in P.KINDS:
                time.sleep(P.PACE_S)
                v, why = P.read(s, pick["alpha"], kind)
                fresh[kind] = v if v is not None else why
            numeric = all(isinstance(fresh[k], (int, float)) for k in P.KINDS)
            if numeric:
                # a complete fresh reading supersedes the stored one (load_corr keeps the last numeric
                # value); otherwise the stored value would say "under the line" round after round
                P.append_corr([dict(fresh, alpha=pick["alpha"], read_at=time.time(), source="submit-reread")])
            pl, sl = pick["lines"]
            if not (numeric and fresh["prod"] < pl and fresh["self"] < sl):
                print("  %s: stale reading re-read as %s -- skipped for now" % (pick["alpha"], fresh))
                continue
            pick["prod"], pick["self"] = fresh["prod"], fresh["self"]
        # the same mechanism must not be posted twice in one invocation either
        elig = [e for e in elig if e["mechanism_key"] != pick["mechanism_key"]]
        print("\nPOSTING %s (prod %.3f, self %.3f, gain %.2f) -- irreversible" % (pick["alpha"], pick["prod"], pick["self"], pick["cell_gain"]))
        try:
            SB.LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with SB.LEDGER.open("a") as fh:
                fh.write(json.dumps({"date": SB.platform_date(), "alpha": pick["alpha"], "source": "forge_submit",
                                     "stage": "reserved", "reserved_at": time.time()}) + "\n")
        except OSError as exc:
            print("REFUSING TO POST: could not reserve a slot in the shared ledger (%s)" % exc)
            return 1
        http, body = CS.post(pick["alpha"], session=s)
        record(pick, http, body)
        print("HTTP %s\n%s" % (http, (body or "")[:1500]))
        try:
            import msgcat as MC
            MC.send(MC.m6_post_outcome(pick["alpha"], http, time.time(), exc_class=(None if http is not None else "post-raised")))
        except Exception as exc:  # noqa: BLE001
            print("NOTIFY FAILED (%s: %s) -- the POST above still happened" % (type(exc).__name__, exc))
        posted += 1
        remaining -= 1
        if http in (200, 201):
            last_post_at = time.time()
            today_sets[datasets_of(pick["mechanism_key"])] += 1
            elig = [e for e in elig if diversity_ok(datasets_of(e["mechanism_key"]), today_sets)]
            # round 3 S11: a SELF read minutes after a POST is not trusted (04 section 3.6: 6 of 8 low), and a
            # gen:<family> key drops no PnL sibling, so a generated twin of this alpha is held by prediction
            elig, twins = pnl_twin_hold(pick["alpha"], elig)
            if twins:
                print("  S11: held %s against %s" % (dict(twins), pick["alpha"]))
            # D18 inside one invocation: this alpha's structural family is now submitted, so drop the
            # rest of it from the queue. Without this, two twins POST in the same run -- the exact
            # shape of the diversity bug fixed on 2026-09-09 (code review F4), re-found by audit.
            if nov is not None and nov.register(pick["row"].get("formula") or "", pick["alpha"]):
                before = len(elig)
                elig = [e for e in elig if nov.verdict(e["row"].get("formula") or "")[0] is False]
                if before != len(elig):
                    print("  novelty: dropped %d queued alpha(s) sharing %s's structure" % (before - len(elig), pick["alpha"]))
            else:
                print("  novelty: %s has no formula to register -- stopping rather than risk a twin" % pick["alpha"])
                break
        if http is None or http == 403:
            print("stopping after an unknown outcome or a refusal; the ledger holds the slot")
            break
    print("posted %d" % posted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
