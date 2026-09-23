"""The hourly link law must SEND a link every hour the session is dead (Khoa 2026-09-04)."""
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import mint_link as ML  # noqa: E402
import outbox as OB  # noqa: E402


def test_budget_resets_on_the_et_day(tmp_path, monkeypatch):
    monkeypatch.setattr(ML, "BUDGET", tmp_path / "b.json")
    now = 1788500000.0
    (tmp_path / "b.json").write_text(json.dumps({"et_day": ML.et_day(now) - 1, "used": 25}))
    left, used, cap = ML.budget_left(now)
    assert used == 0 and left == cap                      # yesterday's 25 do not count today
    assert ML.bump_budget(now) == 1
    b = json.loads((tmp_path / "b.json").read_text())
    assert b["et_day"] == ML.et_day(now) and b["used"] == 1
    assert ML.budget_left(now)[1] == 1
    assert ML.et_day(now) == int((now - 4 * 3600) // 86400)


def test_release_hour_reopens_the_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("WQ_NOTIFY_DIR", str(tmp_path))
    assert OB.once_per_hour("mint") is True
    assert OB.once_per_hour("mint") is False
    assert OB.release_hour("mint") is True
    assert OB.once_per_hour("mint") is True
    assert OB.release_hour("mint") is True and OB.release_hour("mint") is False


def test_live_session_is_refused_before_the_gate(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WQ_NOTIFY_DIR", str(tmp_path))
    monkeypatch.setattr(ML, "session_live", lambda: True)
    monkeypatch.setattr(ML, "live_link", lambda: None)
    assert ML.mint(force=False, quiet=False) == 0
    assert "phien con song" in capsys.readouterr().out
    assert OB.once_per_hour("mint") is True              # the hour was NOT consumed


def test_budget_refusal_gives_the_hour_back(tmp_path, monkeypatch):
    monkeypatch.setenv("WQ_NOTIFY_DIR", str(tmp_path))
    monkeypatch.setattr(ML, "session_live", lambda: False)
    monkeypatch.setattr(ML, "live_link", lambda: None)
    monkeypatch.setattr(ML, "budget_left", lambda now=None: (0, 25, 25))
    assert ML.mint(force=False, quiet=True) == 0
    assert OB.once_per_hour("mint") is True              # refused after taking it -> given back
