"""framelib/loop/evidence.py on synthetic journals: the evidence ledger, used_fields, the per-frame summary,
the daily report and evidence.live in the library. Nothing here reads the VPS or the network."""
import hashlib
import json
import shutil

import pytest

from framelib import schema as SC
from framelib import store as ST
from framelib.loop import evidence as LE

BINDING = ["LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE", "CONCENTRATED_WEIGHT",
           "HIGH_TURNOVER", "LOW_TURNOVER"]
DAY = "2026-09-26"
_REAL = ST.read_all()
MINED = sorted(i for i, e in _REAL.items() if e["provenance"]["origin"] == "mined" and e["evidence"])[0]
NOVEL = sorted(i for i, e in _REAL.items() if e["provenance"]["origin"] == "novel" and e["evidence"] is None)[0]
OTHER = sorted(i for i in _REAL if i not in (MINED, NOVEL))[0]
FC = "F0000000000fc"                        # a frame the library does not hold
ZERO = dict.fromkeys(LE.COUNTS, 0)


def con(fid, i, route="screen", seed=11, day=DAY, **meta):
    m = {"experiment": "FRAMES-LOOP", "frame_id": fid, "frame_version": 1, "fill": ["f_%s_%d" % (fid, i)],
         "route": route, "round_seed": seed, "plan_day": day, "arm": route}
    m.update(meta)
    return {"formula": "rank(ts_delta(f_%s_%d, 5))" % (fid, i),
            "settings": {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "INDUSTRY",
                         "decay": 4, "truncation": 0.08, "instrumentType": "EQUITY"}, "meta": m}


def child(c, status, alpha=None, sharpe=None, ls="FAIL", all_pass=False, date="2026-09-26T10:00:00-04:00", formula=None,
          url="https://x/p"):
    r = {"status": status, "alpha": alpha, "formula": formula or c["formula"], "meta": c["meta"],
         "settings": c["settings"], "parent_url": url, "message": ""}
    if status in ("COMPLETE", "WARNING"):
        checks = [{"name": n, "result": "PASS" if all_pass else "FAIL", "limit": 1.58 if n == "LOW_SHARPE" else 1.0}
                  for n in BINDING]
        if not all_pass:
            checks[0]["result"] = ls
        r.update(sharpe=sharpe, checks=checks, dateCreated=date)
    return r


def parent(cs, url="https://x/p"):
    return {"status": "PARENT-POSTED", "parent_url": url, "n_children": len(cs), "formulas": [c["formula"] for c in cs]}


def harvested(c, status, url, alpha=None, sharpe=None):
    """A recovered row as tools/recover_harvest.py writes it: no settings, no meta, its parent's url."""
    return dict(child(c, status, alpha, sharpe, url=url), settings=None, meta=None, recovered=True)


def put(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def plan(path, cons, seed=11):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seed": seed, "constructions": cons}))


def counts(**kw):
    return dict(ZERO, **kw)


def ledger_key(rows):
    return {(r["frame_id"], r["day"], r["route"]): r for r in rows}


@pytest.fixture()
def state(tmp_path):
    """One loop round (seed 11, plan_day 2026-09-26), a dry-run plan in the archive, R1B, attempt 1, recovered."""
    s = tmp_path / "state"
    runs = s / "layered" / "runs"
    fa = [con(MINED, i) for i in range(8)] + [con(MINED, 100)]
    fb = [con(NOVEL, i) for i in range(6)]
    ex = con(NOVEL, 9, route="explore")                                 # a route outside the three: not evidence
    fc = [con(FC, i, route="replicate") for i in range(2)]
    p1 = [fa[0]] + fa[1:6] + fb[0:4]                        # one parent: 1 ERROR cancels its 9 siblings
    p2 = [fa[6], fb[4], fc[0]]
    rows = [parent(p1), child(fa[0], "ERROR")] + [child(c, "CANCELLED") for c in p1[1:]]
    rows += [parent(p2), child(fa[6], "COMPLETE", "A1", 2.0, all_pass=True), child(fb[4], "WARNING", "A2", 1.0),
             child(fc[0], "COMPLETE", "A3", 1.3), dict(child(fb[5], "POST-400"), body="refused"),
             parent([ex]), child(ex, "CANCELLED")]
    put(runs / "frames_loop.jsonl", rows)
    plan(runs / "frames_loop.plan.json", p1 + p2 + [fa[7], fc[1], fb[5], ex])   # fa[7]: recovered only; fc[1]: missing
    plan(s / "frames" / "plans" / "dryrun.json", [fa[8]], seed=99)       # a dry run: no row, no parent
    put(runs / "recovered.jsonl", [
        child(fa[7], "COMPLETE", "A4", 1.5, formula="rank( ts_delta( f_%s_7 , 5 ) )" % MINED) | {"meta": None},
        child(fa[6], "ERROR") | {"meta": None}])                         # the journal's own row wins over this
    r1b = [dict(con(MINED, 50), meta=dict(con(MINED, 50)["meta"], arm="a", experiment="FRAMES-R1")),
           dict(con(NOVEL, 51), meta={"arm": "c", "frame_id": "nonlib:abc", "fill": ["g1"]}),
           dict(con(NOVEL, 52), meta={"arm": "d", "hypothesis": "incumbent"})]
    for c in r1b:
        c["meta"].pop("plan_day", None)
        c["meta"].pop("round_seed", None)
        c["meta"].pop("route", None)
    put(runs / "frames_r1b.jsonl", [parent(r1b), child(r1b[0], "COMPLETE", "B1", 0.5, date="2026-09-25T02:30:00+00:00"),
                                    child(r1b[1], "CANCELLED"), child(r1b[2], "ERROR")])
    plan(runs / "frames_r1b.plan.json", r1b, seed=20260925)
    put(runs / "frames_r1.jsonl", [child(dict(con(MINED, 60), meta={"frame_id": MINED, "fill": ["f_attempt1"]}), "CANCELLED")])
    put(s / "submit_budget.jsonl", [{"date": DAY, "alpha": "A1", "source": "frames_loop_submit", "stage": "reserved"},
                                    {"date": DAY, "alpha": "A2", "source": "frames_loop_submit", "stage": "reserved"},
                                    {"date": DAY, "alpha": "ZZ9", "source": "forge_submit", "stage": "reserved"}])
    put(s / "forge" / "submitted.jsonl", [                              # 2026-09-27 02:00 UTC = 09-26 22:00 ET
        {"alpha": "A1", "http": 201, "posted_at": 1790474400.0, "source": "frames-loop", "frame_id": MINED},
        {"alpha": "A2", "http": 403, "posted_at": 1790474500.0, "source": "frames-loop", "frame_id": NOVEL},
        {"alpha": "ZZ9", "http": 201, "posted_at": 1790474400.0, "source": "forge"}])
    return s


@pytest.fixture()
def lib(tmp_path):
    root = tmp_path / "library"
    (root / "frames").mkdir(parents=True)
    for fid in (MINED, NOVEL, OTHER):
        shutil.copy(ST.frames_dir() / ("%s.json" % fid), root / "frames")
    ST.write_index(list(ST.read_all(root).values()), root)
    return root


def test_counts_per_frame_day_route_with_a_cancelled_parent_and_a_recovered_row(state):
    led = ledger_key(LE.build(state)["ledger"])
    fa, fb, fc = led[(MINED, DAY, "screen")], led[(NOVEL, DAY, "screen")], led[(FC, DAY, "replicate")]
    assert {k: fa[k] for k in LE.COUNTS} == counts(n_planned=8, n_scored=2, n_error=1, n_cancelled=5, n_recovered=1,
                                                    y08=2, ls=1, d24=1)
    assert {k: fb[k] for k in LE.COUNTS} == counts(n_planned=6, n_scored=1, n_cancelled=4, n_other=1)
    assert fb["statuses"] == {"CANCELLED": 4, "POST-400": 1, "WARNING": 1}
    assert {k: fc[k] for k in LE.COUNTS} == counts(n_planned=2, n_scored=1, n_missing=1, n_unposted=1, y08=1)
    assert fa["statuses"] == {"CANCELLED": 5, "COMPLETE": 2, "ERROR": 1} and fa["d24_alphas"] == ["A1"]
    assert fa["fields"] == sorted("f_%s_%d" % (MINED, i) for i in range(8)) and fa["experiments"] == ["FRAMES-LOOP"]
    assert fa["frame_versions"] == [1] and not any(r["route"] == "explore" for r in led.values())
    for r in led.values():
        assert r["n_planned"] == r["n_scored"] + r["n_error"] + r["n_cancelled"] + r["n_other"] + r["n_missing"]


def test_legacy_journals_route_day_and_arms_outside_the_ledger(state):
    b = LE.build(state)
    r1b = ledger_key(b["ledger"])[(MINED, "2026-09-24", "screen")]      # 02:30 UTC on 09-25 is 22:30 ET on 09-24
    assert {k: r1b[k] for k in LE.COUNTS} == counts(n_planned=1, n_scored=1) and r1b["by_arm"] == {"a": counts(n_planned=1, n_scored=1)}
    assert r1b["experiments"] == ["FRAMES-R1B"]
    assert not any(r["frame_id"] == "nonlib:abc" for r in b["ledger"])
    day = {d["day"]: d for d in b["daily"]}["2026-09-24"]
    assert day["outside_ledger"] == {"FRAMES-R1B/c": counts(n_planned=1, n_cancelled=1),
                                     "FRAMES-R1B/d": counts(n_planned=1, n_error=1)}


def test_a_dry_run_plan_is_not_counted_and_a_posted_parent_without_children_is(tmp_path):
    s = tmp_path / "state"
    runs = s / "layered" / "runs"
    lost = [con(FC, i, seed=21) for i in range(2)]
    put(runs / "frames_loop.jsonl", [parent(lost)])                     # posted; the children never came back
    plan(runs / "frames_loop.plan.json", lost, seed=21)
    plan(s / "frames" / "plans" / "dry.json", [con(FC, 9, seed=22)], seed=22)
    b = LE.build(s)
    assert [{k: r[k] for k in LE.COUNTS} for r in b["ledger"]] == [counts(n_planned=2, n_missing=2)]
    assert b["report"]["plans_not_run"] == [str(s / "frames" / "plans" / "dry.json")]


def test_rounds_are_matched_on_round_seed_not_on_the_formula_alone(tmp_path):
    s = tmp_path / "state"
    runs = s / "layered" / "runs"
    first, again = con(FC, 1, seed=31, day="2026-09-26"), con(FC, 1, seed=32, day="2026-09-27")
    put(runs / "frames_loop.jsonl", [parent([first]), child(first, "CANCELLED"), parent([again]),
                                     child(again, "COMPLETE", "A9", 0.2)])
    plan(s / "frames" / "plans" / "r31.json", [first], seed=31)
    plan(s / "frames" / "plans" / "r32.json", [again], seed=32)
    led = ledger_key(LE.build(s)["ledger"])
    assert {k: led[(FC, "2026-09-26", "screen")][k] for k in LE.COUNTS} == counts(n_planned=1, n_cancelled=1)
    assert {k: led[(FC, "2026-09-27", "screen")][k] for k in LE.COUNTS} == counts(n_planned=1, n_scored=1)


def loop_state(tmp_path, rows, cons, seed, recovered=()):
    s = tmp_path / "state"
    runs = s / "layered" / "runs"
    put(runs / "frames_loop.jsonl", rows)
    plan(runs / "frames_loop.plan.json", cons, seed=seed)
    put(runs / "recovered.jsonl", list(recovered))
    return s


def test_a_harvested_row_without_settings_is_matched_through_its_parent_in_this_journal(tmp_path):
    cs = [con(FC, i, seed=71) for i in range(3)]
    s = loop_state(tmp_path, [parent(cs[:2], "https://x/p1"), child(cs[0], "CANCELLED", url="https://x/p1"),
                              parent([cs[2]], "https://x/p2")], cs, 71,
                   [harvested(cs[1], "COMPLETE", "https://x/p1", "R1", 1.5),          # its parent is this journal's
                    harvested(cs[2], "COMPLETE", "https://x/elsewhere", "R2", 1.5)])  # a parent of another journal
    [r] = LE.build(s)["ledger"]
    assert {k: r[k] for k in LE.COUNTS} == counts(n_planned=3, n_scored=1, n_cancelled=1, n_missing=1, n_recovered=1, y08=1)
    from framelib.experiments import analyse_round as AR                # its key cannot match (settings None)
    assert AR._key(cs[1]["formula"], cs[1]["settings"]) not in AR._rows(s / "layered" / "runs" / "recovered.jsonl")


def test_a_poll_row_yields_to_a_recovered_row_and_counts_as_other_without_one(tmp_path):
    cs = [con(FC, i, seed=72) for i in range(2)]
    s = loop_state(tmp_path, [parent(cs, "https://x/p3")] + [child(c, "POLL-DEADLINE", url="https://x/p3") for c in cs],
                   cs, 72, [harvested(cs[0], "WARNING", "https://x/p3", "R3", 0.1)])
    [r] = LE.build(s)["ledger"]
    assert {k: r[k] for k in LE.COUNTS} == counts(n_planned=2, n_scored=1, n_other=1, n_recovered=1)
    assert r["statuses"] == {"POLL-DEADLINE": 1, "WARNING": 1}


def test_one_formula_at_two_settings_is_unposted_by_count_and_its_harvested_row_is_ambiguous(tmp_path):
    a, c = con(FC, 1, seed=73), con(FC, 2, seed=73)
    b = dict(a, settings=dict(a["settings"], decay=8))                   # a's formula again, other settings
    s = loop_state(tmp_path, [parent([a, c], "https://x/p4")], [a, b, c], 73,   # posted once; no child row came back
                   [harvested(a, "COMPLETE", "https://x/p4", "R4", 2.0)])        # a's or b's? a parent row cannot say
    bl = LE.build(s)
    [r] = bl["ledger"]
    assert {k: r[k] for k in LE.COUNTS} == counts(n_planned=3, n_missing=3, n_unposted=1)
    assert bl["report"]["recovered_ambiguous"] == 2


def test_f10_pair_members_are_split_and_a_harvested_pair_row_is_not_used(tmp_path):
    pair = dict(route="production", arm="production-pair-01", pair_id="p1")
    p = con(FC, 1, seed=74, pair_member="profile", **pair)
    q = dict(con(FC, 1, seed=74, pair_member="reference", **pair))
    q["settings"] = dict(q["settings"], decay=8)                          # same fill and formula, reference settings
    single = con(FC, 2, seed=74, route="production")
    s = loop_state(tmp_path, [parent([p, q, single], "https://x/p5"), child(p, "COMPLETE", "P1", 1.5, url="https://x/p5"),
                              child(single, "COMPLETE", "S1", 0.1, url="https://x/p5")], [p, q, single], 74,
                   [harvested(q, "COMPLETE", "https://x/p5", "Q1", 2.0)])        # profile's or reference's? cannot say
    b = LE.build(s)
    [r] = b["ledger"]
    assert {k: r[k] for k in LE.COUNTS} == counts(n_planned=3, n_scored=2, n_missing=1, y08=1)
    assert r["by_pair_member"] == {"profile": counts(n_planned=1, n_scored=1, y08=1), "reference": counts(n_planned=1, n_missing=1)}
    assert set(r["by_arm"]) == {"production", "production-pair-01"} and b["report"]["recovered_ambiguous"] == 1


def test_a_parent_belongs_to_the_round_whose_plan_holds_all_its_formulas(tmp_path):
    s = tmp_path / "state"
    x1, y1 = con(FC, 1, seed=81), con(FC, 2, seed=81)
    x2, z2 = con(FC, 1, seed=82, day="2026-09-27"), con(FC, 3, seed=82, day="2026-09-27")   # x again, never run
    put(s / "layered" / "runs" / "frames_loop.jsonl", [parent([x1, y1]), parent([con(FC, 9)])])  # 2nd: in no plan
    plan(s / "frames" / "plans" / "r81.json", [x1, y1], seed=81)
    plan(s / "frames" / "plans" / "r82.json", [x2, z2], seed=82)
    b = LE.build(s)
    assert b["report"]["plans_not_run"] == [str(s / "frames" / "plans" / "r82.json")]
    assert b["report"]["parents_unassigned"] == 1
    assert [(r["day"], {k: r[k] for k in LE.COUNTS}) for r in b["ledger"]] == [(DAY, counts(n_planned=2, n_missing=2))]


def test_a_row_whose_plan_was_never_archived_is_still_counted(tmp_path):
    s = tmp_path / "state"
    c = con(FC, 3, seed=41)
    put(s / "layered" / "runs" / "frames_loop.jsonl", [parent([c]), child(c, "COMPLETE", "A7", 1.4)])
    b = LE.build(s)
    assert [{k: r[k] for k in LE.COUNTS} for r in b["ledger"]] == [counts(n_planned=1, n_scored=1, y08=1)]


def test_the_plan_archive_keeps_a_round_after_the_dispatcher_rewrites_its_plan(state, lib):
    LE.update(state, lib)
    nxt = con(FC, 7, seed=12, day="2026-09-27")
    runs = state / "layered" / "runs"
    with open(runs / "frames_loop.jsonl", "a") as fh:
        fh.write(json.dumps(parent([nxt])) + "\n" + json.dumps(child(nxt, "CANCELLED")) + "\n")
    plan(runs / "frames_loop.plan.json", [nxt], seed=12)
    led = ledger_key(LE.update(state, lib)["ledger"])
    assert {k: led[(FC, DAY, "replicate")][k] for k in LE.COUNTS} == counts(n_planned=2, n_scored=1, n_missing=1,
                                                                           n_unposted=1, y08=1)
    assert led[(FC, "2026-09-27", "screen")]["n_cancelled"] == 1


def test_used_fields_covers_every_journal_row_and_every_planned_construction(state, lib):
    LE.update(state, lib)
    want = {"f_%s_%d" % (MINED, i) for i in range(8)} | {"f_%s_50" % MINED, "f_attempt1"}
    assert LE.used_fields(MINED, state) == want                         # not f_..._100: the dry run never ran
    assert LE.used_fields(FC, state) == {"f_%s_0" % FC, "f_%s_1" % FC}  # f_..._1 was planned and has no row
    extra = con(MINED, 200, seed=13)
    with open(state / "layered" / "runs" / "frames_loop.jsonl", "a") as fh:
        fh.write(json.dumps(child(extra, "ERROR")) + "\n")
    assert "f_%s_200" % MINED in LE.used_fields(MINED, state)           # re-read once a source changed
    r3s = con(MINED, 300, seed=None)
    r3s["meta"] = {"experiment": "FRAMES-R3S", "arm": "s", "frame_id": MINED, "fill": ["f_r3s"]}
    put(state / "layered" / "runs" / "frames_r3s.jsonl", [child(r3s, "COMPLETE", "S3", 0.2)])
    assert "f_r3s" in LE.used_fields(MINED, state)                     # a new experiment journal: its fields are used
    assert not any("FRAMES-R3S" in r["experiments"] for r in LE.build(state)["ledger"])   # but it is not ledger evidence


def test_summary_carries_the_counts_and_a_beta_posterior_on_y08(state):
    sm = LE.build(state)["summary"][MINED]
    assert sm["total"]["n_scored"] == 3 and sm["total"]["y08"] == 2      # 2 of the loop round + 1 of R1B
    assert sm["y08_beta"] == {"prior": [1, 1], "a": 3, "b": 2, "mean": 0.6}
    assert sm["days"] == ["2026-09-24", DAY] and list(sm["by_route"]) == ["screen"]


def test_daily_report_counts_routes_passes_and_submissions_and_says_it_is_descriptive(state):
    day = {d["day"]: d for d in LE.build(state)["daily"]}[DAY]
    assert day["routes"]["screen"]["n_planned"] == 14 and day["routes"]["screen"]["n_frames"] == 2
    assert day["routes"]["replicate"]["n_planned"] == 2
    assert day["all_check_passes"] == {"n": 1, "alphas": ["A1"]}
    sub = day["submissions"]                                          # ZZ9 is forge's, not the loop's
    assert (sub["n_posted"], sub["posted"], sub["accepted"], sub["by_http"]) == (2, ["A1", "A2"], ["A1"], {"201": 1, "403": 1})
    assert sub["reserved"] == ["A1", "A2"]
    assert day["label"] == "DESCRIPTIVE" and "DESCRIPTIVE" in day["note"] and "F6" in day["note"]
    assert day["outside_ledger"] == {"FRAMES-LOOP/explore": counts(n_planned=1, n_cancelled=1)}


def test_submission_sources_are_the_loop_submitters_own_tags():
    from framelib.loop import submit as LS
    assert (LE.POST_SOURCE, LE.RESERVE_SOURCE) == (LS.SOURCE, LS.LEDGER_SOURCE)


def test_library_gets_evidence_live_and_nothing_else_changes(state, lib):
    before = ST.read_all(lib)
    other_bytes = (ST.frames_dir(lib) / ("%s.json" % OTHER)).read_bytes()
    b = LE.update(state, lib)
    after = ST.read_all(lib)
    ST.load(lib)                                                      # every entry validates; INDEX.json not stale
    for fid in (MINED, NOVEL):
        for k in ("status", "status_history", "approval", "version", "text", "characteristics", "provenance"):
            assert after[fid][k] == before[fid][k], (fid, k)
        assert SC.validate(after[fid]) == []
    old_ev = before[MINED]["evidence"]
    assert {k: v for k, v in after[MINED]["evidence"].items() if k != "live"} == old_ev
    assert set(after[NOVEL]["evidence"]) == {"live"}
    lv = after[MINED]["evidence"]["live"]
    ledger = (state / "frames" / "evidence.jsonl").read_bytes()
    assert lv["source"] == {"path": str(state / "frames" / "evidence.jsonl"), "sha256": hashlib.sha256(ledger).hexdigest()}
    assert lv["comparison"] == LE.COMPARISON and lv["comparison"]["y08_rate"] == 0.1236 and lv["criterion"] == "y08"
    assert lv["rows"] == [{k: v for k, v in r.items() if k != "frame_id"} for r in b["ledger"] if r["frame_id"] == MINED]
    assert (ST.frames_dir(lib) / ("%s.json" % OTHER)).read_bytes() == other_bytes
    assert b["library"]["not_in_library"] == [FC] and sorted(b["library"]["written"]) == sorted([MINED, NOVEL])


def test_a_row_with_an_unknown_day_stays_in_the_ledger_and_out_of_the_library_block(tmp_path, lib):
    s = tmp_path / "state"
    c = con(MINED, 5, seed=51)
    c["meta"].pop("plan_day")
    put(s / "layered" / "runs" / "frames_loop.jsonl", [parent([c]), child(c, "CANCELLED")])
    b = LE.update(s, lib)
    assert [r["day"] for r in b["ledger"]] == ["unknown"]
    assert b["library"]["refused"] == {} and ST.read_all(lib)[MINED]["evidence"]["live"]["rows"] == []


def test_update_is_idempotent(state, lib):
    LE.update(state, lib)
    files = sorted(p for p in list((state / "frames").rglob("*")) + list(lib.rglob("*")) if p.is_file())
    first = {p: p.read_bytes() for p in files}
    second = LE.update(state, lib)
    assert sorted(p for p in list((state / "frames").rglob("*")) + list(lib.rglob("*")) if p.is_file()) == files
    assert {p: p.read_bytes() for p in files} == first
    assert second["library"]["written"] == [] and len(list((state / "frames" / "plans").glob("*.json"))) == 2


def test_a_refused_library_entry_is_reported_and_exits_3(state, lib, capsys):
    p = ST.frames_dir(lib) / ("%s.json" % MINED)
    e = json.loads(p.read_text())
    e["status"] = "validated"                                         # invalid already: no tick, no live rows
    e["status_history"].append({"status": "validated", "at": "2026-09-26", "by": "x", "reason": "x"})
    p.write_text(ST.dumps(e))
    raw = p.read_bytes()
    assert LE.main(["--update", "--state", str(state), "--library", str(lib)]) == 3
    assert "LIBRARY REFUSED" in capsys.readouterr().err and MINED in json.loads((state / "frames" / "frames_summary.json").read_text())
    assert p.read_bytes() == raw and (state / "frames" / "evidence.jsonl").exists()
