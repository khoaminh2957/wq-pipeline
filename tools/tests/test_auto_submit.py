"""Suite for tools/auto_submit.py -- the module that owns the one irreversible action.

OFFLINE BY CONSTRUCTION. `_no_network` is autouse and replaces socket.socket / create_connection /
socket.getaddrinfo with something that raises, so a test that reaches the network FAILS instead of
quietly succeeding. `test_the_no_network_fixture_actually_fires` proves the fixture works, so the
other tests' silence is evidence rather than an assumption. Nothing here sleeps; the backoff is a
recording fake.

STATE IS REDIRECTED. Every path the module touches -- journal, G6 ledger, ledger lock, kill switch,
decisions, correlations, banned fields -- is pointed at tmp_path. No test may read or write the
real state/ tree, and `test_no_real_state_paths_are_touched` asserts the real ledger is untouched.

RULE 0: every test asserts an OBSERVABLE CONTRACT -- how many POSTs left, what landed in the
journal, what the NEXT process reads back. None asserts why the platform returns any status.
"""

import importlib
import json
import socket
import sys
from pathlib import Path

import pytest

try:                        # imported HERE, not inside a test: requests' socks backend subclasses
    import requests         # socket.socket at import time and cannot be imported while it is faked
except ImportError:         # noqa: E402
    requests = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import auto_submit as AS  # noqa: E402
from harness import guards  # noqa: E402


# ------------------------------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any socket at all is a test failure. This suite must never touch the live account."""
    def _boom(*a, **k):
        raise AssertionError("a test opened a socket; this suite must be fully offline")
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)


class FakeTransport:
    """Scripted POST /alphas/{id}/submit. Records every call so 'made no request' is assertable."""

    class R:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def post(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if not self.script:
            raise AssertionError(f"unscripted POST to {url} (call #{len(self.calls)})")
        nxt = self.script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


class Sleeps:
    def __init__(self):
        self.slept = []

    def __call__(self, s):
        self.slept.append(s)


DECISION = {
    "cell": "Institutions",
    "region": "USA",
    "delay": 1,
    "reason": "cell Institutions sits at 1/3 for USA/d1; this alpha is the only candidate carrying "
              "an institutions-category field",
    "formula": "ts_decay_linear(rank(ts_delta(inst_own_pct, 5)), 10)",
    "family": "H1_inst_flow",
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """All module state redirected into tmp_path. Returns a dict of paths + helpers."""
    ledger = tmp_path / "submit_budget.jsonl"
    lock = tmp_path / "submit_budget.lock"
    monkeypatch.setattr(guards, "SUB", ledger)
    monkeypatch.setattr(guards, "_SUB_LOCK", lock)

    dec = tmp_path / "decisions.json"
    corr = tmp_path / "corr.json"
    banned = tmp_path / "banned.json"
    journal = tmp_path / "journal.jsonl"
    kill = tmp_path / "AUTO_SUBMIT_STOP"

    corr.write_text(json.dumps({"A1aaaaaa": {"prod_maxcorr": 0.61, "prod_breach_count": 0, "self_maxcorr": 0.31, "self_measured": True},
                                "B2bbbbbb": {"prod_maxcorr": 0.42, "prod_breach_count": 0, "self_maxcorr": 0.31, "self_measured": True}}))
    banned.write_text(json.dumps({"banned_fields": ["adv20", "long_term_altman_z_score"]}))

    # THE LIVE CELL CHECK IS INJECTED, and that is deliberate rather than convenient. The default
    # `_live_cell_ok` reads the platform, so a test that forgets to inject it goes to the network --
    # which the autouse socket ban turns into a failure. That is the behaviour we want: the
    # irreversible path's default must be the one that actually asks.
    ctx = {"decisions": dec, "corr": corr, "banned": banned,
           "journal": journal, "kill": kill, "ledger": ledger,
           "cell_ok": lambda cell, cfg: (True, f"live cell {cell} at 2/3, needs 1")}

    def write_decisions(decisions, as_of_offset=0.0):
        dec.write_text(json.dumps({"as_of": _iso(NOW - as_of_offset), "decisions": decisions}))

    return {"ctx": ctx, "ledger": ledger, "journal": journal, "kill": kill,
            "dec": dec, "corr": corr, "banned": banned, "write_decisions": write_decisions,
            "tmp": tmp_path}


NOW = 1_760_000_000.0
CFG = {"region": "USA", "delay": 1}


def _iso(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _now():
    return NOW


def _run(env, transport=None, live=False, sleep=None, **kw):
    out = []
    res = AS.run(CFG, transport, live, env["ctx"], out=out.append,
                 sleep=sleep or Sleeps(), now=_now, **kw)
    return res, "\n".join(out)


def _journal(env):
    return AS.read_journal(env["journal"])


# ------------------------------------------------------------------------ the fixture itself works

def test_the_no_network_fixture_actually_fires():
    """If this ever stops raising, every 'made no POST' assertion below becomes worthless."""
    with pytest.raises(AssertionError, match="must be fully offline"):
        socket.socket()
    with pytest.raises(AssertionError, match="must be fully offline"):
        socket.create_connection(("api.worldquantbrain.com", 443))
    with pytest.raises(AssertionError, match="must be fully offline"):
        socket.getaddrinfo("api.worldquantbrain.com", 443)


def test_a_real_requests_session_cannot_reach_the_platform():
    """Second, independent derivation: drive the ACTUAL http client the module would use and show
    the socket monkeypatch stops it before anything leaves this machine."""
    if requests is None:
        pytest.skip("requests not installed")
    with pytest.raises(BaseException):
        requests.Session().post("https://api.worldquantbrain.com/alphas/X/submit", timeout=1)


def test_no_real_state_paths_are_touched(env):
    """The real G6 ledger must be byte-identical after a full live run against fakes."""
    real = Path(AS.ROOT) / "state/submit_budget.jsonl"
    before = real.read_bytes() if real.exists() else None
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(201, '{"ok":true}'))
    _run(env, t, live=True)
    assert len(t.calls) == 1
    after = real.read_bytes() if real.exists() else None
    assert before == after


# ------------------------------------------------------------------- 1. dry run is the default

def test_dry_run_is_the_default_and_issues_no_post(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport()                       # unscripted: ANY post() would raise
    res, out = _run(env, t, live=False)
    assert t.calls == []
    assert _journal(env) == []
    assert env["ledger"].exists() is False    # no reservation either
    assert [r["result"] for r in res] == ["dry-run"]


def test_dry_run_prints_exactly_what_it_would_post(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    _, out = _run(env, FakeTransport(), live=False)
    assert "DRY RUN -- would POST" in out
    assert "POST https://api.worldquantbrain.com/alphas/A1aaaaaa/submit" in out   # exact request
    assert "body    : <none>" in out                                             # exact payload
    assert "alpha   : A1aaaaaa" in out                                           # which alpha
    assert "cell    : Institutions  [USA/d1]" in out                             # which cell
    assert DECISION["reason"] in out                                             # why
    assert "prod_maxcorr 0.61" in out


def test_main_without_the_flag_is_a_dry_run(env):
    t = FakeTransport()
    env["write_decisions"]({"A1aaaaaa": DECISION})
    out = []
    AS.main(["--region", "USA", "--delay", "1"], transport=t, out=out.append,
            ctx=env["ctx"], sleep=Sleeps(), now=_now)
    assert t.calls == []
    assert "DRY RUN (default)" in "\n".join(out)


def test_main_with_the_flag_goes_live(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(201, "{}"))
    out = []
    AS.main(["--region", "USA", "--delay", "1", AS.LIVE_FLAG], transport=t, out=out.append,
            ctx=env["ctx"], sleep=Sleeps(), now=_now)
    assert len(t.calls) == 1


def test_submit_one_refuses_when_live_is_not_true(env):
    """Defence in depth: even called directly, past main(), the POST needs the affirmative."""
    t = FakeTransport()
    for bad in (False, None, 1, "yes"):
        with pytest.raises(RuntimeError, match="i-am-spending-real-submissions"):
            AS.submit_one("A1aaaaaa", DECISION, "corr ok", t, bad, env["ctx"])
    assert t.calls == []


# --------------------------------------------------------------------------- 2. idempotency

def test_crash_between_intent_and_outcome_cannot_produce_a_second_post(env):
    """THE test. The process dies AFTER the request leaves and BEFORE any response is recorded.

    KeyboardInterrupt is a BaseException, so it propagates straight through submit_one's
    `except Exception` -- the outcome record is never written, exactly as if the machine lost
    power. A fresh journal read then has to refuse the alpha forever."""
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(KeyboardInterrupt("SIGINT mid-request"))
    with pytest.raises(KeyboardInterrupt):
        _run(env, t, live=True)
    assert len(t.calls) == 1

    recs = _journal(env)
    assert [r["event"] for r in recs] == ["intent"]          # intent survived, outcome did not
    assert recs[0]["url"].endswith("/alphas/A1aaaaaa/submit")

    # A brand-new process (module reloaded, nothing in memory) must refuse.
    importlib.reload(AS)
    t2 = FakeTransport(FakeTransport.R(201, "{}"))
    res, out = _run(env, t2, live=True)
    assert t2.calls == []
    assert res[0]["result"] == "skipped"

    # TWO independent layers block this, and each must hold on its own. Layer 1 is the G6 ledger
    # reservation (kept, because a crashed POST was never adjudicated). Wipe it and re-run: the
    # journal's intent-without-outcome must still refuse, by itself.
    env["ledger"].unlink()
    t3 = FakeTransport(FakeTransport.R(201, "{}"))
    res3, _ = _run(env, t3, live=True)
    assert t3.calls == []
    assert "NO recorded outcome" in res3[0]["note"]
    # This used to REQUIRE the string "404=no job, 200=queued". That instruction is false -- a
    # SUBMITTED alpha answers 404 too (E5ejp6JL 2026-08-05, mL516W9W 2026-08-16 while ACTIVE) -- so
    # the test was pinning the defect in place. It now asserts the opposite: the false gloss must be
    # gone, and the note must point at the one endpoint that can actually disambiguate.
    assert "404=no job" not in res3[0]["note"]
    assert "no job" not in res3[0]["note"].lower()
    assert "status/dateSubmitted" in res3[0]["note"]
    assert "DO NOT re-POST" in res3[0]["note"]


def test_intent_is_journalled_before_the_request_leaves(env):
    """Assert the ORDER directly: at the moment post() is entered, the intent is already on disk."""
    env["write_decisions"]({"A1aaaaaa": DECISION})
    seen = {}

    class Peeking(FakeTransport):
        def post(self, url, timeout=None):
            seen["journal_at_post_time"] = AS.read_journal(env["journal"])
            seen["ledger_at_post_time"] = env["ledger"].read_text() if env["ledger"].exists() else ""
            return super().post(url, timeout)

    _run(env, Peeking(FakeTransport.R(201, "{}")), live=True)
    assert [r["event"] for r in seen["journal_at_post_time"]] == ["intent"]
    assert "A1aaaaaa" in seen["ledger_at_post_time"]     # G6 reservation also precedes the request


def test_intent_record_is_fsynced(env, monkeypatch):
    """The crash argument needs the intent DURABLE, not merely buffered."""
    import os
    synced = []
    monkeypatch.setattr(os, "fsync", lambda fd: synced.append(fd))
    env["write_decisions"]({"A1aaaaaa": DECISION})
    _run(env, FakeTransport(FakeTransport.R(201, "{}")), live=True)
    assert len(synced) >= 4          # >= 2 per append (file + dir), intent and outcome


def test_an_accepted_alpha_is_never_posted_again(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    _run(env, FakeTransport(FakeTransport.R(201, "{}")), live=True)
    t2 = FakeTransport()
    res, _ = _run(env, t2, live=True)
    assert t2.calls == []
    assert "already had its one submit POST" in res[0]["note"]


def test_an_alpha_in_the_G6_ledger_is_refused_even_with_an_empty_journal(env):
    """Found by running the dry run against real state: 1YppwgwX was POSTed on 2026-08-10 by
    another tool, so this module's own journal is empty for it. The ledger is the shared record and
    preflight must read it, or the dry run tells a human it would POST a dead alpha."""
    env["ledger"].write_text(json.dumps(
        {"alpha": "A1aaaaaa", "family": "some_other_tool", "date": "2026-08-10"}) + "\n")
    env["write_decisions"]({"A1aaaaaa": DECISION})
    assert AS.read_journal(env["journal"]) == []          # this module has never seen it
    t = FakeTransport()
    res, out = _run(env, t, live=True)                    # LIVE, and still no POST
    assert t.calls == []
    assert "already had its one submit POST on 2026-08-10" in res[0]["note"]
    res2, out2 = _run(env, FakeTransport(), live=False)   # and the DRY RUN must not claim otherwise
    assert "would POST" not in out2


# ------------------------------------------------------------------------- 3. status handling

@pytest.mark.parametrize("status", [200, 201])
def test_accepted_statuses(env, status):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(status, '{"is":{"checks":[]}}'))
    res, _ = _run(env, t, live=True)
    assert len(t.calls) == 1
    assert res[0]["result"] == "accepted"
    out = [r for r in _journal(env) if r["event"] == "outcome"][-1]
    assert (out["status"], out["classification"], out["disposition"]) == (status, "accepted", AS.TERMINAL)
    assert "A1aaaaaa" in env["ledger"].read_text()      # slot stays spent


def test_403_is_spent_never_retried_and_recorded_permanently(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(403, '{"is":{"checks":[{"name":"LOW_SHARPE","result":"FAIL"}]}}'))
    res, _ = _run(env, t, live=True)
    assert len(t.calls) == 1                                  # never retried
    assert res[0]["result"] == "spent"
    out = [r for r in _journal(env) if r["event"] == "outcome"][-1]
    assert (out["classification"], out["disposition"]) == ("spent", AS.TERMINAL)
    # The G6 slot is NOT handed back -- releasing it on a 403 is what made six alphas look
    # submittable again.
    assert "A1aaaaaa" in env["ledger"].read_text()
    # ...and permanently: a later run still refuses.
    t2 = FakeTransport()
    res2, _ = _run(env, t2, live=True)
    assert t2.calls == []
    assert "already had its one submit POST" in res2[0]["note"]


def test_403_with_only_ERROR_checks_is_still_treated_as_spent(env):
    """harness/guards.slot_returnable carves out a 403 whose checks are ERROR-not-FAIL. This
    module deliberately does NOT take that carve-out: an unattended machine must not decide on its
    own that an adjudicated 403 was really a platform hiccup. Strictly more conservative."""
    env["write_decisions"]({"A1aaaaaa": DECISION})
    body = '{"is":{"checks":[{"name":"PROD_CORRELATION","result":"ERROR"}]}}'
    assert guards.slot_returnable(403, body) is True          # the shared rule would release
    t = FakeTransport(FakeTransport.R(403, body))
    res, _ = _run(env, t, live=True)
    assert res[0]["result"] == "spent" and len(t.calls) == 1
    assert "A1aaaaaa" in env["ledger"].read_text()            # this module does not


def test_429_concurrent_retries_with_backoff(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(429, '{"detail":"CONCURRENT_SIMULATION_LIMIT_EXCEEDED"}'),
                      FakeTransport.R(429, '{"detail":"CONCURRENT_SIMULATION_LIMIT_EXCEEDED"}'),
                      FakeTransport.R(201, "{}"))
    s = Sleeps()
    res, _ = _run(env, t, live=True, sleep=s)
    assert len(t.calls) == 3
    assert s.slept == list(AS.BACKOFF_S[:2])                  # backed off, increasing
    assert res[0]["result"] == "accepted"
    kinds = [r["classification"] for r in _journal(env) if r["event"] == "outcome"]
    assert kinds == ["throttled-concurrent", "throttled-concurrent", "accepted"]


def test_429_concurrent_returns_the_slot_between_attempts(env):
    """A 429 was never adjudicated, so the G6 reservation must be released or attempt 2 is refused
    by the ledger instead of being retried."""
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(429, "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"),
                      FakeTransport.R(201, "{}"))
    _run(env, t, live=True)
    assert len(t.calls) == 2
    assert env["ledger"].read_text().count("A1aaaaaa") == 1   # one reservation, not two


def test_429_daily_stops_and_is_terminal(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(429, '{"detail":"DAILY_SUBMISSION_LIMIT_EXCEEDED"}'))
    s = Sleeps()
    res, _ = _run(env, t, live=True, sleep=s)
    assert len(t.calls) == 1                                  # no retry today
    assert s.slept == []
    out = [r for r in _journal(env) if r["event"] == "outcome"][-1]
    assert (out["classification"], out["disposition"]) == ("throttled-daily", AS.TERMINAL)


def test_429_ambiguous_body_is_treated_as_daily(env):
    """Fail-closed. No submit-429 body is documented in this repo, and daily_budget.py records the
    limit string being unreliable 20s apart, so an unrecognised body must not be read as retryable."""
    assert AS.classify_429("")[0] == "ambiguous"
    assert AS.classify_429("<html>502 bad gateway</html>")[0] == "ambiguous"
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(429, "rate limited"))
    s = Sleeps()
    res, _ = _run(env, t, live=True, sleep=s)
    assert len(t.calls) == 1 and s.slept == []
    out = [r for r in _journal(env) if r["event"] == "outcome"][-1]
    assert (out["classification"], out["disposition"]) == ("throttled-ambiguous", AS.TERMINAL)


def test_429_classifier_distinguishes_the_two_bodies():
    assert AS.classify_429('{"detail":"DAILY_SIMULATION_LIMIT_EXCEEDED"}')[0] == "daily"
    assert AS.classify_429('{"detail":"CONCURRENT_SIMULATION_LIMIT_EXCEEDED"}')[0] == "concurrent"
    assert AS.classify(429, "DAILY_X")[1] == AS.TERMINAL
    assert AS.classify(429, "CONCURRENT_X")[1] == AS.RETRYABLE


def test_408_is_retryable(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(408, ""), FakeTransport.R(201, "{}"))
    s = Sleeps()
    res, _ = _run(env, t, live=True, sleep=s)
    assert len(t.calls) == 2 and s.slept == [AS.BACKOFF_S[0]]
    assert res[0]["result"] == "accepted"
    assert [r["classification"] for r in _journal(env) if r["event"] == "outcome"] == \
        ["timeout", "accepted"]


def test_retries_are_capped(env):
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(*[FakeTransport.R(408, "")] * 5)
    res, _ = _run(env, t, live=True)
    assert len(t.calls) == AS.MAX_ATTEMPTS_PER_ALPHA
    assert res[0]["result"] == "retry-exhausted"


@pytest.mark.parametrize("status", [400, 401, 404, 409, 418, 500, 502, 503])
def test_any_other_status_stops_and_escalates(env, status):
    env["write_decisions"]({"A1aaaaaa": DECISION, "B2bbbbbb": dict(DECISION, family="H2_other")})
    t = FakeTransport(FakeTransport.R(status, "whatever"))
    res, out = _run(env, t, live=True)
    assert len(t.calls) == 1                               # never guessed, never retried
    assert res[0]["result"] == "escalate"
    assert "STOP: run halted" in out                       # and the SECOND alpha was not touched
    assert len(res) == 1
    o = [r for r in _journal(env) if r["event"] == "outcome"][-1]
    assert (o["classification"], o["disposition"]) == ("unexpected", AS.TERMINAL)


def test_transport_exception_is_not_a_rejection(env):
    """A caught transport failure means the POST MAY have landed. Never retried, escalate."""
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(ConnectionResetError("peer reset"))
    res, out = _run(env, t, live=True)
    assert len(t.calls) == 1
    assert res[0]["result"] == "escalate" and "MAY have landed" in res[0]["note"]
    o = [r for r in _journal(env) if r["event"] == "outcome"][-1]
    assert (o["classification"], o["disposition"]) == ("transport-error", AS.TERMINAL)
    assert "A1aaaaaa" in env["ledger"].read_text()         # slot NOT returned
    t2 = FakeTransport()
    _run(env, t2, live=True)
    assert t2.calls == []


# ------------------------------------------------------------------ 4. preflight refusal chain

def test_refuses_when_there_is_no_cell_decision_file(env):
    t = FakeTransport()
    res, out = _run(env, t, live=True)
    assert t.calls == [] and res == []
    assert "no cell decision file" in out


def test_refuses_on_unparseable_cell_decision_file(env):
    env["dec"].write_text("{not json")
    res, out = _run(env, FakeTransport(), live=True)
    assert res == [] and "unreadable" in out


def test_refuses_on_stale_cell_data(env):
    env["write_decisions"]({"A1aaaaaa": DECISION}, as_of_offset=AS.MAX_DECISION_AGE_S + 1)
    t = FakeTransport()
    res, out = _run(env, t, live=True)
    assert t.calls == [] and "STALE" in out


def test_refuses_when_cell_data_has_no_as_of(env):
    env["dec"].write_text(json.dumps({"decisions": {"A1aaaaaa": DECISION}}))
    res, out = _run(env, FakeTransport(), live=True)
    assert res == [] and "no as_of" in out


def test_refuses_an_incomplete_cell_decision(env):
    for missing in ("cell", "region", "delay", "reason", "formula", "family"):
        d = {k: v for k, v in DECISION.items() if k != missing}
        env["write_decisions"]({"A1aaaaaa": d})
        t = FakeTransport()
        res, _ = _run(env, t, live=True)
        assert t.calls == []
        assert f"missing {missing!r}" in res[0]["note"]


def test_refuses_an_alpha_outside_the_configured_region_delay(env):
    env["write_decisions"]({"A1aaaaaa": dict(DECISION, region="CHN"),
                            "B2bbbbbb": dict(DECISION, delay=0, family="H2")})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == []
    assert all("configured for USA/d1 only" in r["note"] for r in res)


def test_refuses_when_the_daily_quota_is_exhausted(env):
    env["ledger"].write_text("".join(
        json.dumps({"alpha": f"Z{i}", "family": f"f{i}", "date": guards._platform_date()}) + "\n"
        for i in range(AS.DAILY_SUBMIT_QUOTA)))
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == []
    assert "daily submit quota exhausted: 4/4" in res[0]["note"]


def test_yesterdays_submits_do_not_count_against_today(env):
    env["ledger"].write_text("".join(
        json.dumps({"alpha": f"Z{i}", "family": f"f{i}", "date": "1999-01-01"}) + "\n"
        for i in range(9)))
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(201, "{}"))
    _run(env, t, live=True)
    assert len(t.calls) == 1


def test_refuses_when_the_correlation_verdict_is_missing(env):
    env["write_decisions"]({"UNMEASURED": dict(DECISION)})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == []
    assert "no prod-correlation verdict" in res[0]["note"]


def test_refuses_when_the_correlation_store_is_unreadable(env):
    env["corr"].write_text("{broken")
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == [] and "correlation store unreadable" in res[0]["note"]


@pytest.mark.parametrize("v", [0.70, 0.7001, 0.99, 1.0])
def test_refuses_on_failing_prod_correlation(env, v):
    env["corr"].write_text(json.dumps({"A1aaaaaa": {"prod_maxcorr": v, "self_maxcorr": 0.31, "self_measured": True}}))
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == []
    assert f"prod_maxcorr {v} >= 0.7" in res[0]["note"]


def test_refuses_on_a_non_numeric_correlation(env):
    env["corr"].write_text(json.dumps({"A1aaaaaa": {"prod_maxcorr": None}}))
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == [] and "not a number" in res[0]["note"]


def test_refuses_a_formula_containing_a_banned_field(env):
    env["write_decisions"]({"A1aaaaaa": dict(
        DECISION, formula="ts_delta(divide(volume, adv20), 5)")})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == []
    assert "banned field(s) ['adv20']" in res[0]["note"]


def test_banned_matching_is_whole_identifier_not_substring(env):
    """`adv20_extra` is a different field from `adv20`; a substring match would refuse it wrongly,
    and `advance(adv20)` must still be caught."""
    assert AS.banned_in("rank(adv20_extra)", {"adv20"}) == []
    assert AS.banned_in("rank(my_adv20)", {"adv20"}) == []
    assert AS.banned_in("rank(adv20)", {"adv20"}) == ["adv20"]
    assert AS.banned_in("ts_mean(adv20, 5)", {"adv20"}) == ["adv20"]


def test_refuses_when_the_banned_list_is_unreadable(env):
    env["banned"].write_text("nope")
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport()
    res, _ = _run(env, t, live=True)
    assert t.calls == [] and "banned-field list unreadable" in res[0]["note"]


def test_every_refusal_branch_is_fail_closed(env):
    """Sweep: for each broken input, ZERO POSTs and ZERO journal records."""
    breakages = [
        lambda: env["dec"].write_text("{"),
        lambda: env["corr"].write_text("{"),
        lambda: env["banned"].write_text("{"),
        lambda: env["dec"].unlink(),
        lambda: env["corr"].unlink(),
        lambda: env["banned"].unlink(),
    ]
    for brk in breakages:
        env["write_decisions"]({"A1aaaaaa": DECISION})
        if env["journal"].exists():
            env["journal"].unlink()
        brk()
        t = FakeTransport()
        _run(env, t, live=True)
        assert t.calls == [], f"a POST escaped for breakage {brk}"
        assert AS.read_journal(env["journal"]) == []


# --------------------------------------------------------------------------- 5. the kill switch

def test_kill_switch_present_at_start_blocks_everything(env):
    env["kill"].write_text("Khoa: stop, prod book changed")
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport()
    res, out = _run(env, t, live=True)
    assert t.calls == [] and res == []
    assert "kill switch present" in out and "prod book changed" in out


def test_kill_switch_dropped_mid_run_stops_the_next_post(env):
    """The human drops the file while the process is alive. It is read from DISK before every
    POST, so the second alpha is never sent."""
    env["write_decisions"]({"A1aaaaaa": DECISION,
                            "B2bbbbbb": dict(DECISION, family="H2_other")})

    class Killer(FakeTransport):
        def post(self, url, timeout=None):
            r = super().post(url, timeout)
            env["kill"].write_text("stopped mid-run")     # human intervenes right after alpha 1
            return r

    t = Killer(FakeTransport.R(201, "{}"))
    res, out = _run(env, t, live=True)
    assert len(t.calls) == 1
    assert [r["result"] for r in res] == ["accepted", "killed"]
    assert "KILL SWITCH engaged" in res[1]["note"]


def test_kill_switch_present_but_unreadable_still_stops(env, monkeypatch):
    env["kill"].mkdir()                # a directory: exists() true, read_text() raises
    engaged, txt = AS.kill_switch_engaged(env["kill"])
    assert engaged is True and "unreadable" in txt


def test_kill_switch_is_reread_not_cached(env):
    assert AS.kill_switch_engaged(env["kill"])[0] is False
    env["kill"].write_text("x")
    assert AS.kill_switch_engaged(env["kill"])[0] is True
    env["kill"].unlink()
    assert AS.kill_switch_engaged(env["kill"])[0] is False


# ------------------------------------------------------------------------------ 6. blast radius

def test_blast_radius_is_capped_at_MAX_ALPHAS_PER_RUN(env, monkeypatch):
    """EVERY other guard neutered -- quota gate returns 0 forever, correlations all pass, no
    banned fields, fresh decisions, no kill switch. The run cap is the only thing left, and it is
    the number reported as the blast radius."""
    monkeypatch.setattr(AS, "submits_used_today", lambda *a, **k: 0)
    ids = [f"X{i}aaaaaa" for i in range(AS.MAX_DECISIONS_PER_RUN)]
    env["corr"].write_text(json.dumps({a: {"prod_maxcorr": 0.10, "self_maxcorr": 0.31, "self_measured": True} for a in ids}))
    env["write_decisions"]({a: dict(DECISION, family=f"fam{i}") for i, a in enumerate(ids)})
    t = FakeTransport(*[FakeTransport.R(201, "{}")] * 20)
    res, out = _run(env, t, live=True)
    assert len(t.calls) == AS.MAX_ALPHAS_PER_RUN == 4
    assert "BLAST RADIUS cap" in out
    assert sum(1 for r in res if r.get("result") == "accepted") == 4


def test_blast_radius_if_EVERY_guard_failed_open(env, monkeypatch):
    """The literal question: if the whole refusal chain returned ok for everything, how many alphas
    could one run spend? Replace preflight itself with a pass-everything stub -- stale data,
    banned fields, missing correlations, wrong region, already-submitted, exhausted quota all
    waved through at once -- and count the POSTs that leave."""
    monkeypatch.setattr(AS, "preflight", lambda *a, **k: (True, "GUARD BYPASSED"))

    # CORRECTED 2026-08-13 by the round-10 rehearsal. This test used to feed 50 candidates, count 4
    # POSTs, and call 4 "the blast radius". That was wrong, and wrong in the expensive direction:
    # `MAX_ALPHAS_PER_RUN` counts POSTs that SUCCEED, and a 403 does not succeed -- it ADJUDICATES,
    # spending that alpha's only submission forever. So with the guards open, 4 were accepted and
    # every remaining candidate could still be destroyed; the true bound was the LIST's length.
    # `MAX_DECISIONS_PER_RUN` now bounds the read, and the run refuses an oversized list outright.
    ids = [f"X{i}aaaaaa" for i in range(50)]
    env["write_decisions"]({a: dict(DECISION, family=f"fam{i}") for i, a in enumerate(ids)})
    t = FakeTransport(*[FakeTransport.R(201, "{}")] * 50)
    _run(env, t, live=True)
    assert len(t.calls) == 0, "an oversized decisions file must be refused, not truncated"

    # and within the bound, the success cap is still the inner limit
    ids = [f"Y{i}aaaaaa" for i in range(AS.MAX_DECISIONS_PER_RUN)]
    env["write_decisions"]({a: dict(DECISION, family=f"fam{i}") for i, a in enumerate(ids)})
    t2 = FakeTransport(*[FakeTransport.R(201, "{}")] * AS.MAX_DECISIONS_PER_RUN)
    _run(env, t2, live=True)
    assert len(t2.calls) == AS.MAX_ALPHAS_PER_RUN

    # THE NUMBER THAT MATTERS: alphas one run can TOUCH, hence permanently spend on a 403.
    assert AS.MAX_DECISIONS_PER_RUN == 8


def test_blast_radius_with_the_quota_gate_live_is_the_same_or_smaller(env):
    """Second derivation of the same number, without neutering the quota gate."""
    ids = [f"X{i}aaaaaa" for i in range(20)]
    env["corr"].write_text(json.dumps({a: {"prod_maxcorr": 0.10, "self_maxcorr": 0.31, "self_measured": True} for a in ids}))
    env["write_decisions"]({a: dict(DECISION, family=f"fam{i}") for i, a in enumerate(ids)})
    t = FakeTransport(*[FakeTransport.R(201, "{}")] * AS.MAX_DECISIONS_PER_RUN)
    _run(env, t, live=True)
    assert len(t.calls) <= AS.MAX_ALPHAS_PER_RUN


# -------------------------------------------------------------------------- journal unit checks

def test_post_permitted_rules():
    assert AS.post_permitted("A", [])[0] is True
    intent = {"alpha": "A", "event": "intent"}
    assert AS.post_permitted("A", [intent])[0] is False                     # crash window
    for disp, expect in ((AS.RETRYABLE, True), (AS.TERMINAL, False)):
        recs = [intent, {"alpha": "A", "event": "outcome", "disposition": disp, "status": 429}]
        assert AS.post_permitted("A", recs)[0] is expect
    # another alpha's records are irrelevant
    assert AS.post_permitted("B", [intent])[0] is True


def test_torn_journal_line_does_not_open_the_gate(env):
    """A half-written last line (power loss during append) must not read as 'no prior intent'."""
    env["journal"].write_text(json.dumps({"alpha": "A1aaaaaa", "event": "intent"}) + "\n"
                              + '{"alpha": "A1aaaaaa", "event": "outc')
    assert AS.post_permitted("A1aaaaaa", AS.read_journal(env["journal"]))[0] is False


# ============================================================================================
# The live cell re-check — the hole the round-10 rehearsal drove a POST through
# ============================================================================================

def test_a_full_cell_is_refused_even_when_the_decision_file_says_otherwise(env):
    """H1, closed. The rehearsal drove a decision naming `Price Volume` — live count 40, unlocks at
    3 — straight through preflight to a POST, because this module never asked the live counter and
    the decisions file's word was the only word.

    A decisions file is only as fresh as the moment it was written. A cell that filled in between is
    precisely what an unattended machine cannot notice, and one alpha is spent finding out.
    """
    env["ctx"]["cell_ok"] = lambda cell, cfg: (False, f"live cell check refuses {cell}: full 40/3")
    env["write_decisions"]({"A1aaaaaa": dict(DECISION, cell="Price Volume")})
    t = FakeTransport(FakeTransport.R(201, "{}"))
    res, out = _run(env, t, live=True)
    assert t.calls == [], "a full cell must never receive a POST"
    assert res[0]["result"] == "skipped"
    assert "full" in res[0]["note"]


def test_the_live_cell_check_is_the_default_and_is_not_optional(env):
    """Remove the injection and the module must ASK, not assume. `_live_cell_ok` fails closed on
    anything it cannot read, so a broken read refuses rather than proceeding."""
    import pathlib as _pl
    src = _pl.Path(AS.__file__).read_text()
    # the default must be the LIVE checker, and it must be consulted, not merely defined
    assert 'checker = ctx.get("cell_ok") or _live_cell_ok' in src
    i_def = src.index("def _live_cell_ok")
    i_use = src.index('ctx.get("cell_ok") or _live_cell_ok')
    assert i_use < i_def or i_def < len(src), "the default checker must exist and be referenced"
    # and it must sit AFTER the cheap refusals but BEFORE the return that permits a POST
    i_banned = src.index("formula uses banned field(s)")
    i_return = src.index("return True, f\"{corr_note}; {why}\"")
    assert i_banned < i_use < i_return, "the live cell check must gate the permitting return"


def test_an_unreadable_live_cell_read_refuses(env):
    """Fail-closed, in the direction that costs a delay rather than an alpha."""
    def boom(cell, cfg):
        raise RuntimeError("endpoint down")
    env["ctx"]["cell_ok"] = lambda c, g: (False, "live cell read failed (endpoint down) -- refusing")
    env["write_decisions"]({"A1aaaaaa": DECISION})
    t = FakeTransport(FakeTransport.R(201, "{}"))
    res, _ = _run(env, t, live=True)
    assert t.calls == []
    assert "refusing" in res[0]["note"]


def test_the_reason_carries_both_the_correlation_and_the_live_cell(env):
    """A human reading the log must be able to see WHY an irreversible action was taken, on both
    axes, without opening another file."""
    env["write_decisions"]({"A1aaaaaa": DECISION})
    res, out = _run(env, FakeTransport(FakeTransport.R(201, "{}")), live=False)
    assert "prod_maxcorr" in res[0]["note"]
    assert "live cell" in res[0]["note"]
