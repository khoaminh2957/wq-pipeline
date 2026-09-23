import json

from forge.offline import rung_report as RR

# 2026-09-09 15:00 ET = 19:00 UTC
T = 1_788_980_400.0


def _sim(alpha, created, arm=None, dup=False):
    r = {"alpha": alpha, "dateCreated": created, "meta": {"forge": 1, "arm": arm} if arm else {"forge": 1}}
    return r


def test_report_dedupes_alphas_splits_arms_and_reads_adjudication(tmp_path):
    j = tmp_path / "forge.jsonl"
    rows = [_sim("A", "2026-09-09T02:13:50-04:00", "current"), _sim("B", "2026-09-09T12:00:00-04:00", "new"),
            _sim("B", "2026-09-09T12:00:00-04:00", "new"),          # orphan-recovery duplicate: NOT a second simulation
            _sim("C", "2026-09-09T23:30:00-04:00", "new"),          # 23:30 ET is still 09-09
            _sim("D", "2026-09-10T00:10:00-04:00", "new"),          # 00:10 ET is 09-10
            {"alpha": None, "status": "PARENT-POSTED"}, {"status": "POLL-DEADLINE", "meta": {"arm": "new"}}]
    j.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    led = tmp_path / "submitted.jsonl"
    posted_09 = T                                                   # 15:00 ET on 09-09
    led.write_text("\n".join(json.dumps(r) for r in [
        {"alpha": "B", "http": 201, "posted_at": posted_09, "mechanism_key": "m1#ds1#USA/d1", "datasets": "ds1"},
        {"alpha": "B", "http": 201, "posted_at": posted_09 + 5, "mechanism_key": "m1#ds1#USA/d1"},   # a second 201 row: one submission
        {"kind": "adjudication", "alpha": "B", "status": "ACTIVE"},
        {"alpha": "A", "http": 201, "posted_at": posted_09 + 60, "mechanism_key": "m2#ds2#USA/d1", "arm": "current"},
        {"alpha": "X", "http": 403, "posted_at": posted_09 + 70, "mechanism_key": "m3#ds3#USA/d1"},
        {"alpha": "Y", "http": None, "posted_at": None},
    ]) + "\n")
    rep = {r["day"]: r for r in RR.report(journal=j, ledger=led, now=T)}
    d = rep["2026-09-09"]
    assert d["sims"] == 3 and d["arms"] == {"current": 1, "new": 2}          # B counted once; D is 09-10
    assert d["submitted"] == 2 and d["active"] == 1 and d["unadjudicated"] == 1
    assert d["mechanisms"] == 2 and d["dataset_sets"] == 2
    assert d["by_arm"]["new"] == {"sims": 2, "submitted": 1, "rate_per_5000": 2500.0}
    assert d["by_arm"]["current"] == {"sims": 1, "submitted": 1, "rate_per_5000": 5000.0}
    assert d["rate_per_5000"] == round(2 / 3 * 5000, 2)
    assert d["open"] is True and rep["2026-09-10"]["sims"] == 1 and rep["2026-09-10"]["submitted"] == 0
    assert d["measured"] is False


def test_rung_line_reads_the_named_arm(tmp_path, capsys, monkeypatch):
    rows = [{"day": "2026-09-08", "sims": 4500, "measured": True, "open": False, "submitted": 1, "active": 1, "unadjudicated": 0,
             "mechanisms": 1, "dataset_sets": 1, "rate_per_5000": 1.11, "arms": {"current": 4000, "new": 500},
             "by_arm": {"current": {"sims": 4000, "submitted": 0, "rate_per_5000": 0.0}, "new": {"sims": 500, "submitted": 1, "rate_per_5000": 10.0}}}]
    monkeypatch.setattr(RR, "report", lambda days=10: rows)
    RR.main(["--rung", "1"])
    out = capsys.readouterr().out
    assert "rung 1 (1.50 per 5,000, pooled): FAIL on 2026-09-08 (1.11)" in out
    RR.main(["--rung", "1", "--arm", "new"])
    assert "arm new): PASS on 2026-09-08 (10.00)" in capsys.readouterr().out
