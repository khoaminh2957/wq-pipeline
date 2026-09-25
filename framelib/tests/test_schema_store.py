import copy
import json

import pytest

from framelib import evidence as EV
from framelib import schema as SC
from framelib import store as ST

SRC = [{"kind": "novel", "path": "novel.jsonl", "sha256": "ab" * 32, "ref": "line 1"}]
NOW = "2026-09-24T07:00:00+00:00"


def _evidence(n_rows=4, n_d24=1):
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
    return SC.new_entry("rank($1)", sources=SRC, built_by="t", built_at=NOW, evidence=_evidence())


def test_new_entries_are_valid_candidates_with_derived_fields():
    for e in (novel(), mined()):
        assert SC.validate(e) == [], e["text"]
        assert e["status"] == "candidate" and e["version"] == 1 and e["approval"] is None
    e = novel()
    assert (e["text"], e["id"], e["windows"]) == ("rank(ts_delta($1,20))", SC.frame_id("rank(ts_delta($1,20))"), [["ts_delta", 20]])
    assert (novel()["provenance"]["origin"], mined()["provenance"]["origin"]) == ("novel", "mined")
    assert mined()["characteristics"]["turnover_class"] == "MID"


@pytest.mark.parametrize("path,value,msg", [
    (("windows",), [["ts_delta", 21]], "windows does not match"),
    (("id",), "Fdeadbeef0000", "id does not match"),
    (("characteristics", "combiner"), "SUM", "characteristics does not match"),
    (("text",), "rank(ts_delta($1, 20))", "text does not match"),
    (("provenance", "sources"), [], "sources is empty"),
    (("provenance", "sources"), [{"kind": "novel", "path": "x"}], "missing ['sha256', 'ref']"),
    (("provenance", "origin"), "mined", "origin 'mined' but the evidence holds"),
    (("settings",), {"source": "guess"}, "settings.source"),
    (("status",), "approved", "status 'approved'"),
    (("version",), 0, "version must be"),
])
def test_validator_refuses_each_tampering(path, value, msg):
    e = novel()
    d = e
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value
    errs = SC.validate(e)
    assert any(msg in x for x in errs), errs


def test_evidence_rates_must_match_their_counts():
    e = mined()
    e["evidence"]["cells"]["USA/d1"]["d24_rate"] = 0.9
    assert any("rate does not match" in x for x in SC.validate(e))
    e = mined()
    e["evidence"]["cells"]["USA/d1"]["n_d24"] = 9
    assert any("counts out of order" in x for x in SC.validate(e))


def _validate_as(e, rounds, approval):
    e["evidence"]["reliability"] = {"verdict": "ROBUST", "method": "leave-dataset-out", "rounds": rounds}
    e["status"] = "validated"
    e["status_history"].append({"status": "validated", "at": NOW, "by": "khoa", "reason": "ticked"})
    e["approval"] = approval
    return SC.validate(e)


ROUND = {"round": 1, "date": "2026-09-30", "cell": "USA/d1", "n_fills": 90, "comparison_arm": "random frame",
         "effect": 0.2, "source": "x.jsonl", "label": "POST-HOC"}


def test_validated_needs_rounds_a_verdict_and_the_operators_tick():
    tick = {"by": "Khoa", "at": NOW, "ref": "AskUserQuestion 2026-09-30"}
    assert _validate_as(mined(), [ROUND] * 3, tick) == []
    assert any("measured rounds" in x for x in _validate_as(mined(), [ROUND] * 2, tick))
    assert any("approval" in x for x in _validate_as(mined(), [ROUND] * 3, None))
    bad = dict(ROUND, comparison_arm=None)
    assert any("missing ['comparison_arm']" in x for x in _validate_as(mined(), [bad] * 3, tick))


def test_history_must_end_with_the_status():
    e = novel()
    e["status"] = "retired"
    assert any("status_history must end" in x for x in SC.validate(e))
    e["status_history"].append({"status": "retired", "at": NOW, "by": "khoa", "reason": "0/90 in round 2"})
    assert SC.validate(e) == []


def test_store_round_trip_index_and_select(tmp_path):
    a, b = novel(), mined()
    pa = ST.save(a, tmp_path)
    ST.save(b, tmp_path)
    before = pa.read_text()
    ST.save(copy.deepcopy(a), tmp_path)
    assert pa.read_text() == before and pa.name == a["id"] + ".json"
    ST.write_index([a, b], tmp_path)
    got = ST.load(tmp_path)
    assert sorted(e["id"] for e in got) == sorted([a["id"], b["id"]])
    idx = json.loads((tmp_path / "INDEX.json").read_text())["index"]
    assert idx["economic_function"] == {"CHANGE": [a["id"]], "LEVEL": [b["id"]]}
    assert [e["id"] for e in ST.select(got, economic_function="CHANGE")] == [a["id"]]


def test_store_refuses_invalid_renamed_and_stale(tmp_path):
    e = novel()
    e["windows"] = []
    with pytest.raises(ST.LibraryError):
        ST.save(e, tmp_path)
    good = novel()
    p = ST.save(good, tmp_path)
    ST.write_index([good], tmp_path)
    assert ST.problems(tmp_path) == {}
    other = mined()
    ST.save(other, tmp_path)
    assert "INDEX.json" in ST.problems(tmp_path)                    # an entry the index does not list
    p.rename(p.with_name("Fwrongname000.json"))
    with pytest.raises(ST.LibraryError, match="is not the entry id"):
        ST.load(tmp_path)


def test_slot_constraints_are_given_not_derived_and_are_checked():
    e = novel()
    e["slots"][0].update({"role": "any level", "constraints": {"kind": ["level"], "unit_eq": "$1"}})
    assert any("unit_eq '$1' is not another slot" in x for x in SC.validate(e))
    e["slots"][0]["constraints"] = {"kind": "level"}
    assert any("must be a non-empty list" in x for x in SC.validate(e))
    e["slots"][0]["constraints"] = {"colour": ["red"]}
    assert any("unknown keys ['colour']" in x for x in SC.validate(e))
    e["slots"][0]["constraints"] = {"kind": ["level"]}
    assert SC.validate(e) == []
    e["slots"][0]["context"] = "VECTOR"
    assert any("slots does not match" in x for x in SC.validate(e))
