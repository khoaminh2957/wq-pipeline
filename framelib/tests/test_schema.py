"""Phase-A audit B3 (docs/frames/12_phaseA_audit.md) and the frames loop's additions to the entry schema.

`validated` needs, over the evidence.live rows of route "production": >= 3 distinct ET days, >= 30 scored
fills whose fields no other live row of the frame used, >= 1 D24 row, a y08 rate above the named comparison
(F7), and Khoa's dated tick. Any approval must be Khoa's and only on an entry that is or was validated; a
reliability round may not repeat or leave its comparison arm unnamed. Every refusal starts from an entry that
validates and breaks one thing, so each test isolates one rule.
"""
import copy

import pytest

from framelib import evidence as EV
from framelib import schema as SC
from framelib import store as ST

NOW = "2026-09-24T07:00:00+00:00"
SRC = [{"kind": "novel", "path": "novel.jsonl", "sha256": "ab" * 32, "ref": "line 1"}]
TICK = {"by": "Khoa", "at": "2026-10-01", "ref": "AskUserQuestion 2026-10-01"}
PARENT = "F0123456789ab"


def _canonical(n_rows=4, n_d24=1):
    cell = {"n_rows": n_rows, "n_fills": n_rows, "n_datasets": 2, "corpus_groups": {"forge": n_rows},
            "n_complete": n_rows, "n_d24": n_d24, "d24_rate": round(n_d24 / n_rows, 4),
            "d24_wilson_lo95": EV.wilson_lower(n_d24, n_rows), "n_with_limit": n_rows, "n_ge_0p8": 2,
            "ge_0p8_rate": round(2 / n_rows, 4), "ge_0p8_wilson_lo95": EV.wilson_lower(2, n_rows),
            "ratio_median": 0.4, "turnover_median": 0.2, "limits": {"1.58": n_rows}, "settings_top": []}
    return {"evidence_version": EV.EVIDENCE_VERSION, "label": "POST-HOC", "source": {"path": "rows", "sha256": "cd" * 32},
            "caveats": list(EV.CAVEATS), "n_rows": n_rows, "n_fills": n_rows, "cells": {"USA/d1": cell},
            "reliability": {"verdict": "UNMEASURED", "method": None, "rounds": []}}


def novel():
    return SC.new_entry("rank(ts_delta($1, 20))", sources=SRC, built_by="t", built_at=NOW)


def mined():
    return SC.new_entry("rank($1)", sources=SRC, built_by="t", built_at=NOW, evidence=_canonical())


def row(day, route="production", n_planned=12, n_scored=11, n_error=0, n_cancelled=1, y08=3, ls=1, d24=0):
    return {"day": day, "route": route, "n_planned": n_planned, "n_scored": n_scored, "n_error": n_error,
            "n_cancelled": n_cancelled, "y08": y08, "ls": ls, "d24": d24, "fields": ["fld_%s_%s" % (day, route)]}


# 3 production days, 33 scored fills, y08 9/33 = 0.2727 against 0.1236, one D24 row
GOOD = [row("2026-09-27", d24=1), row("2026-09-28"), row("2026-09-29")]


def live(rows, rate=0.1236, arm="incumbent history USA/d1/TOP3000 09-20..09-24 (F6: descriptive)"):
    return {"label": "POST-HOC", "criterion": "y08", "source": {"path": "/opt/wq/state/frames/evidence.jsonl", "sha256": "ef" * 32},
            "comparison": {"arm": arm, "y08_rate": rate}, "rows": rows}


def with_live(e, lv):
    e = copy.deepcopy(e)
    e["evidence"] = dict(e["evidence"] or {}, live=lv)
    return e


def validated(e, rows=GOOD, approval=TICK, **kw):
    e = with_live(e, live(copy.deepcopy(rows), **kw))
    e["status"] = "validated"
    e["status_history"].append({"status": "validated", "at": "2026-10-01", "by": "Khoa", "reason": "ticked"})
    e["approval"] = approval
    return e


def only(errs, fragment):
    assert len(errs) == 1 and fragment in errs[0], errs


# ---------------------------------------------------------------- the good path

def test_a_validated_entry_with_live_evidence_and_khoas_tick_is_valid():
    assert SC.validate(validated(novel())) == []                 # evidence = {"live": ...} alone
    assert SC.validate(validated(mined())) == []                 # canonical block + live
    assert SC.validate(validated(mined(), approval=dict(TICK, at=NOW))) == []   # a datetime is a date too


def test_the_current_library_still_validates_and_can_only_be_validated_through_the_new_route():
    lib = ST.load()                                              # raises on any invalid entry
    assert len(lib) >= 100
    for e in lib:
        assert SC.validate(e) == [], e["id"]
        assert SC.validate(validated(e)) == [], e["id"]
        assert any("approval.by" in x for x in SC.validate(validated(e, approval=dict(TICK, by="claude")))), e["id"]
        assert any("distinct production days" in x for x in SC.validate(validated(e, rows=GOOD[:2]))), e["id"]
        assert any("never validated" in x for x in SC.validate(dict(e, approval=TICK))), e["id"]


# ---------------------------------------------------------------- B3 refusals, one rule each

def test_refuses_one_round_copied_three_times():
    errs = SC.validate(validated(mined(), rows=[GOOD[0]] * 3))
    assert any("repeats" in x for x in errs), errs
    assert any("valid evidence.live" in x for x in errs), errs


def test_refuses_fewer_than_three_distinct_production_days():
    rows = [row("2026-09-27", n_scored=16, n_planned=16, n_cancelled=0, y08=5, d24=1),
            row("2026-09-28", n_scored=16, n_planned=16, n_cancelled=0, y08=5),
            row("2026-09-29", route="replicate")]
    only(SC.validate(validated(mined(), rows=rows)), "distinct production days in evidence.live, has 2")


def test_screen_and_replicate_rows_never_count():
    shifted = [dict(r, route="screen") if i == 0 else r for i, r in enumerate(GOOD)]
    shifted += [row("2026-09-26", route="replicate")]
    errs = SC.validate(validated(mined(), rows=shifted))
    assert any("distinct production days in evidence.live, has 2" in x for x in errs), errs
    assert any("D24 row on production days, has 0" in x for x in errs), errs    # GOOD[0]'s D24 is now a screen row
    low = [dict(r, y08=0) for r in GOOD] + [row("2026-09-25", route="screen", n_planned=90, n_scored=90, n_cancelled=0, y08=80)]
    only(SC.validate(validated(mined(), rows=low)), "positive y08 effect")            # pooled with screen it is 80/123


def test_refuses_fewer_than_thirty_fresh_fills():
    rows = [dict(r, n_planned=9, n_scored=9, n_cancelled=0) for r in GOOD]          # 27 fills, y08 9/27
    only(SC.validate(validated(mined(), rows=rows)), "fresh scored fills on production days, has 27")


def test_refuses_no_d24_row():
    only(SC.validate(validated(mined(), rows=[dict(r, d24=0) for r in GOOD])), "D24 row on production days, has 0")


def test_refuses_fills_whose_fields_were_used_with_the_frame_before():
    old = GOOD[0]["fields"][0]
    again = [GOOD[0], dict(GOOD[1], fields=[old, "fld_new"]), GOOD[2]]           # production day 2 reuses day 1's field
    only(SC.validate(validated(mined(), rows=again)), "fresh fills: 1 field(s) of the production rows appear")
    screened = GOOD + [row("2026-09-24", route="screen")]
    screened[-1]["fields"] = [GOOD[2]["fields"][0]]                              # a screen-day field filled again later
    only(SC.validate(validated(mined(), rows=screened)), "(%s)" % GOOD[2]["fields"][0])
    assert SC.validate(with_live(mined(), live(again))) == []                   # checked for validation only


@pytest.mark.parametrize("rate", [0.5, 9 / 33])                  # below, and exactly equal
def test_refuses_an_effect_that_is_not_positive(rate):
    only(SC.validate(validated(mined(), rate=rate)), "positive y08 effect")


def test_refuses_a_negative_effect_like_the_audit_probe():
    only(SC.validate(validated(mined(), rows=[dict(r, y08=0) for r in GOOD])), "positive y08 effect")


@pytest.mark.parametrize("approval,fragment", [
    (dict(TICK, by="claude"), "approval.by 'claude' is refused"),
    (dict(TICK, by="khoa"), "approval.by 'khoa' is refused"),
    (None, "approval.by None is refused"),
    ({k: v for k, v in TICK.items() if k != "at"}, "approval.at"),
    (dict(TICK, at="yesterday"), "approval.at"),
    ({k: v for k, v in TICK.items() if k != "ref"}, "approval.ref"),
])
def test_refuses_any_approval_but_khoas_dated_tick(approval, fragment):
    errs = SC.validate(validated(mined(), approval=approval))
    assert errs and all("approval" in x for x in errs) and any(fragment in x for x in errs), errs


def _retire(e, by="Khoa"):
    e["status"] = "retired"
    e["status_history"].append({"status": "retired", "at": "2026-10-09", "by": by, "reason": "fell below the incumbent"})
    return e


def test_an_approval_on_an_entry_never_validated_is_refused():
    only(SC.validate(dict(mined(), approval=TICK)), "never validated")                 # a candidate
    only(SC.validate(dict(_retire(novel()), approval=TICK)), "never validated")       # retired, never validated
    assert SC.validate(_retire(validated(mined()))) == []                             # the tick stays on retirement


@pytest.mark.parametrize("make", [lambda: dict(mined(), approval=dict(TICK, by="claude")),
                                  lambda: _retire(validated(mined(), approval=dict(TICK, by="claude")))])
def test_an_approval_by_anyone_but_khoa_is_refused_whatever_the_status(make):
    assert any("approval.by 'claude' is refused" in x for x in SC.validate(make()))


@pytest.mark.parametrize("arm", ["none", "None", "", "  "])
def test_refuses_an_unnamed_comparison_arm(arm):
    errs = SC.validate(validated(mined(), arm=arm))
    assert any("comparison.arm" in x for x in errs), errs


RND = {"round": 1, "date": "2026-09-30", "cell": "USA/d1", "n_fills": 90, "comparison_arm": "random frame, same day",
       "effect": 0.2, "source": "x.jsonl", "label": "POST-HOC"}


def _reliability(e, rounds, verdict="ROBUST"):
    e["evidence"]["reliability"] = {"verdict": verdict, "method": "leave-dataset-out", "rounds": rounds}
    return e


def test_refuses_the_audit_vprobe_entry_on_every_count():
    e = _reliability(mined(), [dict(RND, comparison_arm="none", effect=-0.5)] * 3)   # one round x3, effect -0.5
    e["status"] = "validated"
    e["status_history"].append({"status": "validated", "at": NOW, "by": "claude", "reason": "ticked"})
    e["approval"] = {"by": "claude", "at": NOW, "ref": "x"}
    errs = SC.validate(e)
    assert sum("repeats" in x for x in errs) == 2, errs                        # rounds[1] and rounds[2]
    assert sum("comparison_arm 'none'" in x for x in errs) == 3, errs
    assert any("valid evidence.live" in x for x in errs), errs
    assert any("approval.by 'claude' is refused" in x for x in errs), errs


def test_a_robust_reliability_verdict_never_validates_without_the_live_block():
    e = _reliability(mined(), [dict(RND, round=i, date="2026-09-%d" % (27 + i)) for i in range(3)])
    assert SC.validate(e) == []                                                 # a clean block, as a candidate
    e["status"] = "validated"
    e["status_history"].append({"status": "validated", "at": "2026-10-01", "by": "Khoa", "reason": "ticked"})
    e["approval"] = TICK
    only(SC.validate(e), "valid evidence.live")


def test_reliability_rounds_refuse_a_copied_round():
    e = _reliability(mined(), [RND, dict(RND, round=2, date="2026-10-01"), dict(RND)])
    only(SC.validate(e), "reliability.rounds[2]: round 1 of '2026-09-30' repeats")
    assert SC.validate(_reliability(mined(), [RND, dict(RND, date="2026-10-01")])) == []   # same number, other day


@pytest.mark.parametrize("arm", ["none", "None", "  ", 7])
def test_reliability_rounds_refuse_an_unnamed_comparison_arm(arm):
    only(SC.validate(_reliability(mined(), [dict(RND, comparison_arm=arm)])), "rounds[0].comparison_arm")


# ---------------------------------------------------------------- the live block, whatever the status

def test_a_candidate_may_carry_a_live_block_with_or_without_a_canonical_block():
    assert SC.validate(with_live(novel(), live(GOOD))) == []
    assert SC.validate(with_live(mined(), live(GOOD))) == []
    e = with_live(novel(), live(GOOD))
    assert e["characteristics"] == novel()["characteristics"]    # the live block does not move a derived field


@pytest.mark.parametrize("change,fragment", [
    (lambda lv: lv.update(label="EX-ANTE"), "live.label"),
    (lambda lv: lv.update(criterion="ls"), "live.criterion"),
    (lambda lv: lv.update(source={"path": "x"}), "live.source"),
    (lambda lv: lv["comparison"].update(y08_rate=1.5), "y08_rate"),
    (lambda lv: lv["comparison"].update(y08_rate=True), "y08_rate"),
    (lambda lv: lv.pop("comparison"), "live missing ['comparison']"),
    (lambda lv: lv.update(rows={}), "rows must be a list"),
    (lambda lv: lv["rows"][0].pop("fields"), "rows[0] missing ['fields']"),
    (lambda lv: lv["rows"][0].update(day="2026-13-01"), "rows[0].day"),
    (lambda lv: lv["rows"][0].update(day="27/09/2026"), "rows[0].day"),
    (lambda lv: lv["rows"][0].update(day=["2026-09-27"]), "rows[0].day"),        # an error, not a crash
    (lambda lv: lv["rows"][0].update(route="prod"), "rows[0].route"),
    (lambda lv: lv["rows"][0].update(fields="fld"), "rows[0].fields"),
    (lambda lv: lv["rows"][0].update(n_scored=-1), "counts must be ints"),
    (lambda lv: lv["rows"][0].update(y08=True), "counts must be ints"),
    (lambda lv: lv["rows"][0].update(d24=2), "counts out of order"),              # d24 > ls
    (lambda lv: lv["rows"][0].update(y08=12), "counts out of order"),             # y08 > n_scored
    (lambda lv: lv["rows"][0].update(n_error=1), "counts out of order"),          # 11 + 1 + 1 > 12 planned
    (lambda lv: lv["rows"].append(dict(lv["rows"][1])), "repeats"),
])
def test_live_block_structure_is_checked(change, fragment):
    lv = live(copy.deepcopy(GOOD))
    change(lv)
    errs = SC.validate(with_live(mined(), lv))
    assert any(fragment in x for x in errs), errs


# ---------------------------------------------------------------- provenance origins

def _origin(e, origin, **extra):
    e["provenance"].update(origin=origin, **extra)
    return e


def test_mined_dropped_is_accepted_and_must_hold_canonical_rows():
    assert SC.validate(_origin(mined(), "mined-dropped")) == []
    only(SC.validate(_origin(novel(), "mined-dropped")), "origin 'mined-dropped' but the evidence holds 0")


def test_mutation_is_accepted_with_its_parent_and_refused_without():
    assert SC.validate(_origin(novel(), "mutation", parent=PARENT)) == []
    assert SC.validate(_origin(mined(), "mutation", parent=PARENT)) == []       # rows or not
    only(SC.validate(_origin(novel(), "mutation")), "provenance.parent None")
    only(SC.validate(_origin(novel(), "mutation", parent="Fxyz")), "provenance.parent 'Fxyz'")
    e = novel()
    only(SC.validate(_origin(e, "mutation", parent=e["id"])), "not its own")


def test_other_origins_are_still_refused_and_novel_still_holds_no_rows():
    assert any("origin must be one of" in x for x in SC.validate(_origin(novel(), "guess")))
    assert any("origin must be one of" in x for x in SC.validate(_origin(mined(), ["mined"])))   # an error, not a crash
    only(SC.validate(_origin(mined(), "novel")), "origin 'novel' but the evidence holds 4")
