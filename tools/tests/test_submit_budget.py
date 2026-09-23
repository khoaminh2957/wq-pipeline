"""Suite for tools/submit_budget.py.

WHAT THESE TESTS ARE FOR. Three refusals stand between the auto-submitter and an irreversible
mistake, and each one has already failed in this repo in a way a test would have caught:

  * the daily count returning 0-used when it could not read anything (a full allowance out of an
    absent file), which is the shape of the 2026-07-30 reading that cost le391QLA and Vk35LRM0;
  * a banned-field guard with no caller -- confirmed on 2026-08-13, where a wall function existed,
    its reader was wired, and nothing ever wrote it;
  * a family rule whose key degenerates to the alpha id so that it never collides.

So every test below asserts a REFUSAL, or asserts that a number came from a source rather than
from a default. OFFLINE BY CONSTRUCTION: no test opens a socket, and the only session used is a
stub.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import submit_budget as SB                                              # noqa: E402

DAY = "2026-08-13"


def _ledger(tmp_path, rows):
    p = tmp_path / "submit_budget.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def _banned(tmp_path, fields, by_alpha=None):
    p = tmp_path / "banned_fields.json"
    p.write_text(json.dumps({"banned_fields": list(fields), "by_alpha": by_alpha or {}}))
    return p


class _Session:
    """Minimal stand-in for requests.Session. Never touches a socket."""

    def __init__(self, status=200, payload=None, boom=None):
        self.status_code, self._payload, self._boom = status, payload, boom

    def get(self, url, timeout=None):
        if self._boom:
            raise self._boom
        return self

    def json(self):
        return self._payload


# ---------------------------------------------------------------- daily quota

def test_absent_ledger_cannot_establish_a_count(tmp_path):
    """An unreadable ledger is not an empty one."""
    used, why = SB.ledger_used(DAY, path=tmp_path / "nope.jsonl")
    assert used is None
    assert "cannot establish" in why


def test_absent_ledger_and_no_session_fails_closed_to_zero(tmp_path):
    b = SB.remaining_today(session=None, day=DAY, path=tmp_path / "nope.jsonl")
    assert b["remaining"] == 0
    assert b["used"] is None
    assert b["authoritative"] is False
    assert "NO SOURCE READABLE" in b["why"]


def test_empty_ledger_is_a_real_zero_not_a_failure(tmp_path):
    """The distinction the module exists to make: no rows today != cannot read."""
    p = _ledger(tmp_path, [{"alpha": "a1", "family": "f1", "date": "2026-08-12"}])
    b = SB.remaining_today(session=None, day=DAY, path=p)
    assert b["used"] == 0 and b["remaining"] == SB.CAP


def test_four_rows_today_leaves_nothing(tmp_path):
    p = _ledger(tmp_path, [{"alpha": f"a{i}", "family": f"f{i}", "date": DAY} for i in range(4)])
    assert SB.remaining_today(session=None, day=DAY, path=p)["remaining"] == 0


def test_remaining_never_goes_negative(tmp_path):
    p = _ledger(tmp_path, [{"alpha": f"a{i}", "family": f"f{i}", "date": DAY} for i in range(9)])
    b = SB.remaining_today(session=None, day=DAY, path=p)
    assert b["used"] == 9 and b["remaining"] == 0


def test_malformed_line_counts_as_used_not_skipped(tmp_path):
    """harness/guards.submit_allowed() skips a bad line; for a per-alpha lock that is right and
    here it is wrong. A line we cannot parse may be today's fourth submit."""
    p = tmp_path / "submit_budget.jsonl"
    p.write_text(json.dumps({"alpha": "a1", "family": "f1", "date": DAY}) + "\n"
                 + "{not json at all\n")
    used, why = SB.ledger_used(DAY, path=p)
    assert used == 2, why
    assert "unparseable" in why


def test_row_without_a_date_counts_as_used(tmp_path):
    p = _ledger(tmp_path, [{"alpha": "a1", "family": "f1"}])
    assert SB.ledger_used(DAY, path=p)[0] == 1


def test_platform_reading_overrides_a_lower_ledger(tmp_path):
    """The 2026-07-30 shape: our ledger said 3/4, the platform said 4/4, and two alphas died.
    `used` must be the max of the sources, never the ledger alone."""
    p = _ledger(tmp_path, [{"alpha": f"a{i}", "family": f"f{i}", "date": DAY} for i in range(3)])
    s = _Session(payload={"records": {"records": [[DAY, 4]]}})
    b = SB.remaining_today(session=s, day=DAY, path=p)
    assert b["used"] == 4 and b["remaining"] == 0 and b["authoritative"] is True


def test_platform_lower_than_ledger_does_not_hand_slots_back(tmp_path):
    """A source can miss a submission; none can invent one. The max is the only safe reading."""
    p = _ledger(tmp_path, [{"alpha": f"a{i}", "family": f"f{i}", "date": DAY} for i in range(4)])
    s = _Session(payload={"records": {"records": [[DAY, 1]]}})
    assert SB.remaining_today(session=s, day=DAY, path=p)["remaining"] == 0


def test_unreadable_platform_falls_back_to_ledger_and_says_so(tmp_path):
    p = _ledger(tmp_path, [{"alpha": "a1", "family": "f1", "date": DAY}])
    s = _Session(boom=OSError("connection reset"))
    b = SB.remaining_today(session=s, day=DAY, path=p)
    assert b["remaining"] == 3
    assert b["authoritative"] is False, "a ledger-only reading must not claim authority"


def test_platform_date_is_eastern_not_local_or_utc():
    """The whole rollover discipline rests on this: a local day straddles two Eastern days, which
    is why 9 rows appeared under 2026-07-30 without ever breaching a cap of 4."""
    import datetime
    from zoneinfo import ZoneInfo
    got = SB.platform_date()
    now = datetime.datetime.now(datetime.timezone.utc)
    assert got == now.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def test_the_cap_is_the_platforms_own_number():
    assert SB.CAP == 4
    cache = ROOT / "state/submit_quota_seen.json"
    if cache.exists():
        assert json.loads(cache.read_text())["limit"] == SB.CAP


# ---------------------------------------------------------------- banned fields

def test_banned_field_is_refused(tmp_path):
    """The core refusal. `adv20` is really in state/banned_fields.json, burnt by 0mM8r3L2."""
    p = _banned(tmp_path, ["adv20", "returns"])
    ok, why = SB.check_banned("rank(ts_delta(adv20, 5))", path=p)
    assert ok is False
    assert "adv20" in why


def test_clean_formula_passes(tmp_path):
    p = _banned(tmp_path, ["adv20"])
    ok, why = SB.check_banned("rank(ts_delta(close, 5))", path=p)
    assert ok is True, why


def test_operator_name_colliding_with_a_ban_is_not_a_field(tmp_path):
    """Extraction is precheck_lib's, so `rank` as an operator must not trip a ban on a field
    called `rank`. Without this the guard refuses everything and gets switched off."""
    p = _banned(tmp_path, ["rank"])
    assert SB.check_banned("rank(close)", path=p)[0] is True


def test_missing_ban_list_raises_rather_than_reading_as_empty(tmp_path):
    """precheck_lib returns an empty set when the file is absent -- fine for a reversible sim,
    never on the submit path, where it converts 'could not check' into 'nothing is banned'."""
    with pytest.raises(FileNotFoundError):
        SB.load_banned(path=tmp_path / "nope.json")


def test_corrupt_ban_list_raises(tmp_path):
    p = tmp_path / "banned_fields.json"
    p.write_text("{ truncated")
    with pytest.raises(ValueError):
        SB.load_banned(path=p)


def test_ban_list_is_read_per_call_not_cached_at_import(tmp_path):
    """precheck_lib binds BANNED at module import, so a submitter running for hours never sees a
    field burnt in the meantime."""
    p = _banned(tmp_path, [])
    assert SB.check_banned("rank(close)", path=p)[0] is True
    p.write_text(json.dumps({"banned_fields": ["close"], "by_alpha": {}}))
    assert SB.check_banned("rank(close)", path=p)[0] is False


def test_coverage_reports_landed_alphas_absent_from_the_ban_list(tmp_path):
    log = tmp_path / "submit_log.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in [
        {"alpha": "OLD1", "ok": True, "status": 200, "body": ""},
        {"alpha": "NEW1", "ok": True, "status": 200, "body": ""},
        {"alpha": "DEAD", "ok": False, "status": 403, "body": ""},
    ]))
    p = _banned(tmp_path, ["adv20"], by_alpha={"OLD1": ["adv20"]})
    covered, landed, missing = SB.banned_coverage(log=log, path=p)
    assert covered == {"OLD1"}
    assert landed == {"OLD1", "NEW1"}, "a 403 never landed and must not be expected in the list"
    assert missing == ["NEW1"]


def test_the_real_ban_list_is_stale_against_the_real_submit_log():
    """Not a synthetic case. This is the live state of the repo, and it is why preflight refuses:
    the file has no writer anywhere in the tree and stopped tracking on 2026-07-29."""
    covered, landed, missing = SB.banned_coverage()
    assert len(landed) > len(covered), "if this ever fails, a writer appeared — update the module"
    assert missing, "ban list unexpectedly current; re-check the coverage measurement"


# ---------------------------------------------------------------- family

def test_family_sibling_is_refused(tmp_path):
    p = _ledger(tmp_path, [{"alpha": "SIB1", "family": "news18", "date": "2026-08-01"}])
    ok, why = SB.check_family("NEW1", "news18", path=p)
    assert ok is False
    assert "SIB1" in why


def test_family_rule_is_lifetime_not_same_day(tmp_path):
    """harness/guards.submit_allowed() scopes the cap to `date == today`, so it only delays a
    sibling. The rule asked for here refuses regardless of age."""
    p = _ledger(tmp_path, [{"alpha": "SIB1", "family": "news18", "date": "2026-01-01"}])
    assert SB.check_family("NEW1", "news18", path=p)[0] is False


def test_an_alpha_is_not_its_own_sibling(tmp_path):
    """A re-check on an already-reserved alpha must fail on the G6 per-alpha rule, not on a
    spurious family collision with itself."""
    p = _ledger(tmp_path, [{"alpha": "A1", "family": "news18", "date": DAY}])
    assert SB.check_family("A1", "news18", path=p)[0] is True


def test_distinct_family_passes(tmp_path):
    p = _ledger(tmp_path, [{"alpha": "SIB1", "family": "news18", "date": DAY}])
    assert SB.check_family("NEW1", "insiders7", path=p)[0] is True


def test_the_deployed_family_key_never_collides_on_the_real_ledger():
    """The measurement behind check_family's docstring: replaying all 49 rows through the key
    submit_alphas._family_of() actually produces -- alpha id whenever the dataset cell holds a
    '/'-bearing category label -- yields 49 distinct keys, so the shipped cap refuses nothing."""
    rows = [json.loads(l) for l in SB.LEDGER.read_text().splitlines() if l.strip()]
    keys = [r["alpha"] if "/" in r["family"] else r["family"] for r in rows]
    assert len(set(keys)) == len(rows), "a collision appeared — re-derive the family finding"


# ---------------------------------------------------------------- the call site

def test_preflight_refuses_a_banned_field(tmp_path):
    """The guard is reachable from the path that runs, not only from its own test."""
    led = _ledger(tmp_path, [])
    ban = _banned(tmp_path, ["adv20"], by_alpha={})
    ok, reasons = SB.preflight("A1", "rank(adv20)", "fam1", ledger=led, banned=ban)
    assert ok is False
    assert any(r.startswith("BANNED:") for r in reasons), reasons


def test_preflight_refuses_an_exhausted_quota(tmp_path):
    led = _ledger(tmp_path, [{"alpha": f"a{i}", "family": f"f{i}", "date": SB.platform_date()}
                             for i in range(4)])
    ban = _banned(tmp_path, [])
    ok, reasons = SB.preflight("A1", "rank(close)", "fam1", ledger=led, banned=ban)
    assert ok is False
    assert any(r.startswith("QUOTA:") for r in reasons), reasons


def test_preflight_refuses_a_family_sibling(tmp_path):
    led = _ledger(tmp_path, [{"alpha": "SIB1", "family": "fam1", "date": "2026-07-01"}])
    ban = _banned(tmp_path, [])
    ok, reasons = SB.preflight("A1", "rank(close)", "fam1", ledger=led, banned=ban)
    assert ok is False
    assert any(r.startswith("FAMILY:") for r in reasons), reasons


def test_preflight_refuses_a_stale_ban_list(tmp_path):
    """A list that omits submitted alphas cannot prove a formula is clean, so it refuses."""
    led = _ledger(tmp_path, [])
    ban = _banned(tmp_path, [], by_alpha={})
    log = tmp_path / "submit_log.jsonl"
    log.write_text(json.dumps({"alpha": "NEW1", "ok": True, "status": 200, "body": ""}) + "\n")
    old, SB.SUBMIT_LOG = SB.SUBMIT_LOG, log
    try:
        ok, reasons = SB.preflight("A1", "rank(close)", "fam1", ledger=led, banned=ban)
    finally:
        SB.SUBMIT_LOG = old
    assert ok is False
    assert any(r.startswith("BANNED-STALE:") for r in reasons), reasons


def test_preflight_clears_when_every_guard_passes(tmp_path):
    led = _ledger(tmp_path, [])
    ban = _banned(tmp_path, ["adv20"], by_alpha={})
    log = tmp_path / "submit_log.jsonl"
    log.write_text("")
    old, SB.SUBMIT_LOG = SB.SUBMIT_LOG, log
    try:
        ok, reasons = SB.preflight("A1", "rank(close)", "fam1", ledger=led, banned=ban)
    finally:
        SB.SUBMIT_LOG = old
    assert ok is True, reasons


def test_preflight_reports_every_refusal_not_just_the_first(tmp_path):
    """A caller that fixes one refusal and re-POSTs into a second is spending attempts to
    discover what one call could have told it."""
    led = _ledger(tmp_path, [{"alpha": "SIB1", "family": "fam1", "date": SB.platform_date()},
                             *({"alpha": f"a{i}", "family": f"f{i}", "date": SB.platform_date()}
                               for i in range(3))])
    ban = _banned(tmp_path, ["adv20"], by_alpha={})
    ok, reasons = SB.preflight("A1", "rank(adv20)", "fam1", ledger=led, banned=ban)
    assert ok is False
    kinds = {r.split(":")[0] for r in reasons}
    assert {"QUOTA", "BANNED", "FAMILY"} <= kinds, reasons


def test_module_never_posts():
    """Read-only by construction. No POST verb anywhere in the module."""
    src = (ROOT / "tools/submit_budget.py").read_text()
    assert ".post(" not in src
    assert "submit_one" not in src
