"""Suite for tools/pyramid_gate.py — the pyramid cell gate that DECIDES and never submits.

OFFLINE BY CONSTRUCTION. `_no_network` is autouse and replaces socket.socket with something that
raises, so a test that reaches the network FAILS instead of quietly passing. Time is a fake
counter; nothing sleeps, so the 6-hour staleness window is exercised in microseconds.

The central fixture is the REAL payload: 16 USA-delay-1 cells as the live endpoint returned them
on 2026-08-13, cross-checked against state/pyramid_cell_counts.json and against the count
tools/health_report.py:cells_short() derives from it. The decisions asserted below are therefore
assertions about the actual account, not about a toy.

RULE 0: every test asserts an OBSERVABLE CONTRACT — which request was made, what the decision was,
what number it rested on. None asserts why the platform counts what it counts.
"""

import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyramid_gate as pg  # noqa: E402


# ------------------------------------------------------------------------------------- the payload

# MEASURED 2026-08-13, GET /users/self/activities/pyramid-alphas, USA delay 1. The live response
# carried 211 rows over 16 (region, delay) pairs; these are the 16 rows of the configured pair.
REAL_USA_D1 = {
    "Price Volume": 40, "Model": 19, "Fundamental": 3, "Option": 3, "Analyst": 3, "Other": 3,
    "Earnings": 3, "Risk": 3, "Institutions": 3, "Macro": 3, "News": 2, "Insiders": 2,
    "Sentiment": 1, "Social Media": 0, "Short Interest": 0, "Imbalance": 0,
}
CATEGORY_ID = {v: k for k, v in pg.CATEGORY_IDS.items()}

# The eight cells sitting exactly at the unlock threshold. A submit into any of them unlocks
# nothing, so all eight must HOLD.
AT_THRESHOLD = ["Fundamental", "Option", "Analyst", "Other", "Earnings", "Risk",
                "Institutions", "Macro"]


def payload(counts=None, *, region="USA", delay=1, extra_pairs=True):
    """The endpoint's own shape: {"pyramids": [{category:{id,name}, region, delay, alphaCount}]}."""
    counts = REAL_USA_D1 if counts is None else counts
    rows = [{"category": {"id": CATEGORY_ID.get(k, pg._norm(k)), "name": k},
             "region": region, "delay": delay, "alphaCount": v} for k, v in counts.items()]
    if extra_pairs:
        # Other pairs are always present in the real response and must never leak into the count.
        rows += [{"category": {"id": "pv", "name": "Price Volume"},
                  "region": "USA", "delay": 0, "alphaCount": 0},
                 {"category": {"id": "news", "name": "News"},
                  "region": "EUR", "delay": 1, "alphaCount": 7}]
    return {"pyramids": rows}


# ------------------------------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any socket at all is a test failure."""
    def _boom(*a, **k):
        raise AssertionError("a test opened a socket; this suite must be fully offline")
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


class FakeClock:
    def __init__(self, t=1_786_000_000.0):
        self.t = float(t)

    def now(self):
        return self.t

    def advance(self, s):
        self.t += float(s)
        return self.t


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """Scripted GETs. Records every call, so 'made no request' and 'made N requests' are both
    assertable, and refuses to serve anything but the pyramid URL."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, **kw):
        assert url == pg.API + pg.PYRAMID_PATH, f"unexpected URL {url}"
        self.calls.append(url)
        if not self.script:
            raise AssertionError("unscripted request")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def nosleep():
    return lambda *_a, **_k: None


@pytest.fixture
def fresh(clock):
    """A trustworthy live state: exactly the real counts, zero seconds old."""
    return pg.CellState("USA", 1, dict(REAL_USA_D1), clock.now(), 0.0, "live", 3, None)


def cache_file(tmp_path, counts=None, ts=1_786_000_000.0, *, region="USA", delay=1, schema2=True):
    p = tmp_path / "pyramid_cell_counts.json"
    counts = REAL_USA_D1 if counts is None else counts
    if schema2:
        doc = {"schema": "pyramid_cell_counts/2", "ts": ts,
               "pairs": [{"region": "ASI", "delay": 1, "counts": {"Model": 0}},
                         {"region": region, "delay": delay, "counts": dict(counts), "ts": ts}]}
    else:  # the flat legacy block tools/submit_alphas.py writes
        doc = {"region": region, "delay": delay, "ts": ts, "counts": dict(counts)}
    p.write_text(json.dumps(doc))
    return p


# =========================================================== 1. the real payload, exact decisions

def test_news_and_insiders_submit(fresh):
    """The two cells one alpha away from unlocking. This is the whole point of the module."""
    for cat in ("News", "Insiders"):
        d = pg.decide(cat, fresh)
        assert d.action == pg.SUBMIT, d.explain()
        assert d.count == 2 and d.needs == 1
        assert d.category == cat


def test_the_eight_threshold_cells_hold(fresh):
    for cat in AT_THRESHOLD:
        d = pg.decide(cat, fresh)
        assert d.action == pg.HOLD, d.explain()
        assert d.count == 3 and d.needs == 0
        assert "full" in d.reason


def test_price_volume_holds(fresh):
    d = pg.decide("Price Volume", fresh)
    assert d.action == pg.HOLD
    assert d.count == 40 and d.needs == 0


def test_model_holds(fresh):
    assert pg.decide("Model", fresh).action == pg.HOLD


def test_under_threshold_cells_submit(fresh):
    """Sentiment 1/3 and the three 0/3 cells are below the threshold, so the rule admits them —
    at lower priority, which is `priority`'s job, not `decide`'s."""
    for cat, count in (("Sentiment", 1), ("Social Media", 0),
                       ("Short Interest", 0), ("Imbalance", 0)):
        d = pg.decide(cat, fresh)
        assert d.action == pg.SUBMIT, d.explain()
        assert (d.count, d.needs) == (count, 3 - count)


def test_every_real_cell_is_decided(fresh):
    """No cell of the configured pair falls through to an unknown-category refusal."""
    verdicts = {c: pg.decide(c, fresh).action for c in REAL_USA_D1}
    assert sum(v == pg.SUBMIT for v in verdicts.values()) == 6
    assert sum(v == pg.HOLD for v in verdicts.values()) == 10


def test_thirteen_alphas_unlock_the_region(fresh):
    """Independent re-derivation of the headline number from the same fixture."""
    assert sum(c.needs for c in pg.priority(fresh)) == 13


def test_category_id_accepted_as_well_as_name(fresh):
    assert pg.decide("news", fresh).action == pg.SUBMIT
    assert pg.decide("pv", fresh).action == pg.HOLD
    assert pg.decide("socialmedia", fresh).category == "Social Media"
    assert pg.decide("short interest", fresh).category == "Short Interest"


# ================================================================= 2. priority: unlocks per submit

def test_priority_is_needs_ascending(fresh):
    p = pg.priority(fresh)
    assert [c.category for c in p] == ["Insiders", "News", "Sentiment",
                                       "Imbalance", "Short Interest", "Social Media"]
    assert [c.needs for c in p] == [1, 1, 2, 3, 3, 3]


def test_priority_excludes_unlocked_cells(fresh):
    names = {c.category for c in pg.priority(fresh)}
    assert not names & set(AT_THRESHOLD)
    assert "Price Volume" not in names and "Model" not in names


def test_priority_ignores_multipliers_it_never_sees(fresh):
    """The ordering is a pure function of the counts. There is no multiplier input to smuggle in
    expected money, which is what the objective deliberately does not optimise."""
    assert pg.priority(fresh) == pg.priority(fresh._replace(source="cache", reads=1))


def test_priority_is_empty_when_state_untrustworthy(clock, fresh):
    assert pg.priority(fresh._replace(counts=None)) == []
    assert pg.priority(fresh._replace(age_s=pg.STALE_AFTER_S + 1)) == []
    assert pg.priority(fresh._replace(region="EUR")) == []
    assert pg.priority(None) == []


# ========================================================================== 3. hard refusals

def test_refuse_other_region_or_delay(fresh):
    for st in (fresh._replace(region="EUR"), fresh._replace(delay=0),
               fresh._replace(region="CHN", delay=0)):
        d = pg.decide("News", st)
        assert d.action == pg.HOLD
        assert "out of scope" in d.reason


def test_refuse_full_cell_even_when_overfull(fresh):
    d = pg.decide("Price Volume", fresh)
    assert d.action == pg.HOLD and d.needs == 0


def test_refuse_unknown_category(fresh):
    for bad in ("Broker", "Crypto", "", "   ", None, 7, ["News"]):
        d = pg.decide(bad, fresh)
        assert d.action == pg.HOLD, f"{bad!r} was not refused"
        assert d.category is None


def test_broker_is_a_real_platform_category_and_still_refused(fresh):
    """Being in CATEGORY_IDS is not permission: Broker is not a USA d1 cell."""
    assert "broker" in pg.CATEGORY_IDS
    assert pg.decide("Broker", fresh).action == pg.HOLD


def test_refuse_stale_data(fresh):
    d = pg.decide("News", fresh._replace(age_s=pg.STALE_AFTER_S + 1, source="cache"))
    assert d.action == pg.HOLD and "stale" in d.reason and d.stale is True


def test_boundary_of_staleness(fresh):
    assert pg.decide("News", fresh._replace(age_s=pg.STALE_AFTER_S)).action == pg.SUBMIT
    assert pg.decide("News", fresh._replace(age_s=pg.STALE_AFTER_S + 0.001)).action == pg.HOLD


def test_refuse_unknown_age(fresh):
    """Age None is not 'fresh'. Fail closed."""
    d = pg.decide("News", fresh._replace(age_s=None, ts=None))
    assert d.action == pg.HOLD and "stale" in d.reason


def test_caller_may_tighten_the_threshold(fresh):
    assert pg.decide("News", fresh._replace(age_s=600), max_age_s=1800).action == pg.SUBMIT
    assert pg.decide("News", fresh._replace(age_s=600), max_age_s=300).action == pg.HOLD


def test_refuse_empty_or_missing_counts(fresh):
    for st in (fresh._replace(counts=None, source="unavailable", error="cache: gone"),
               fresh._replace(counts={}), fresh._replace(counts="Price Volume 40")):
        d = pg.decide("News", st)
        assert d.action == pg.HOLD
        assert "no cell data" in d.reason


def test_refuse_non_cellstate(fresh):
    for junk in (None, {}, dict(REAL_USA_D1), "News"):
        assert pg.decide("News", junk).action == pg.HOLD


def test_refuse_unusable_count(fresh):
    for bad in (-1, None, "2", 2.0, True):
        st = fresh._replace(counts={**REAL_USA_D1, "News": bad})
        assert pg.decide("News", st).action == pg.HOLD, f"count {bad!r} was not refused"


def test_decision_has_no_truth_value(fresh):
    """`if decide(...)` would read HOLD as true and spend a submit. It must raise instead."""
    d = pg.decide("Price Volume", fresh)
    assert d.action == pg.HOLD
    with pytest.raises(TypeError):
        bool(d)
    with pytest.raises(TypeError):
        if d:  # noqa: SIM103
            pass


def test_explain_prints_the_numbers(fresh):
    txt = pg.decide("News", fresh).explain()
    assert "SUBMIT" in txt and "News" in txt and "2/3" in txt and "needs 1" in txt


# ================================================================= 4. payload parsing, fail closed

def test_parse_real_payload_scoped_to_the_pair():
    assert pg.parse_pyramids(payload()) == REAL_USA_D1


def test_parse_rejects_garbage():
    for bad in (None, [], "pyramids", {}, {"pyramids": {}}, {"pyramids": ["x"]},
                {"pyramids": [{"category": {"id": "news"}, "region": "USA",
                               "delay": 1, "alphaCount": 2}]},
                {"pyramids": [{"category": {"id": "news", "name": "News"}, "region": "USA",
                               "delay": 1, "alphaCount": None}]},
                {"pyramids": [{"category": {"id": "news", "name": "News"}, "region": "USA",
                               "delay": 1, "alphaCount": -1}]},
                {"pyramids": [{"category": {"id": "news", "name": "News"}, "region": "USA",
                               "delay": 1, "alphaCount": "2"}]}):
        with pytest.raises(pg.PyramidPayloadError):
            pg.parse_pyramids(bad)


def test_parse_rejects_a_payload_with_no_rows_for_the_pair():
    with pytest.raises(pg.PyramidPayloadError):
        pg.parse_pyramids(payload(region="EUR", extra_pairs=False))


def test_parse_keeps_the_high_value_on_a_duplicate_row():
    p = payload({"News": 1}, extra_pairs=False)
    p["pyramids"].append({"category": {"id": "news", "name": "News"},
                          "region": "USA", "delay": 1, "alphaCount": 2})
    assert pg.parse_pyramids(p)["News"] == 2


# ================================================================= 5. cell_state: live and cache

def test_live_reads_are_merged_by_max(clock, nosleep):
    """The 2026-08-02 under-report: one low read must not be able to pull a cell down, because an
    under-count is the direction that spends a submit on a full cell."""
    under = dict(REAL_USA_D1, **{"Analyst": 2, "Earnings": 1, "Price Volume": 18})
    s = FakeSession([_Resp(200, payload()), _Resp(200, payload(under)), _Resp(200, payload())])
    st = pg.cell_state(session=s, now=clock.now, sleep=nosleep)
    assert len(s.calls) == 3
    assert st.source == "live" and st.reads == 3 and st.age_s == 0.0
    assert st.counts == REAL_USA_D1
    assert pg.decide("Analyst", st).action == pg.HOLD      # the under-read must not open it


def test_live_ignores_other_pairs(clock, nosleep):
    s = FakeSession([_Resp(200, payload())] * 3)
    st = pg.cell_state(session=s, now=clock.now, sleep=nosleep)
    assert set(st.counts) == set(REAL_USA_D1)              # no EUR/d0 rows leaked in


def test_partial_failure_still_yields_live_state(clock, nosleep):
    s = FakeSession([_Resp(500, {}), ConnectionError("reset"), _Resp(200, payload())])
    st = pg.cell_state(session=s, now=clock.now, sleep=nosleep)
    assert st.source == "live" and st.reads == 1
    assert pg.decide("News", st).action == pg.SUBMIT


def test_falls_back_to_cache_when_every_read_fails(tmp_path, clock, nosleep):
    cache = cache_file(tmp_path, ts=clock.now() - 3600)
    s = FakeSession([_Resp(401, {})] * 3)
    st = pg.cell_state(session=s, cache_path=cache, now=clock.now, sleep=nosleep)
    assert st.source == "cache" and st.age_s == pytest.approx(3600)
    assert "401" in (st.error or "")
    assert pg.decide("News", st).action == pg.SUBMIT       # 1h old is inside the window


def test_cache_older_than_the_threshold_refuses(tmp_path, clock, nosleep):
    cache = cache_file(tmp_path, ts=clock.now() - pg.STALE_AFTER_S - 60)
    st = pg.cell_state(session=FakeSession([_Resp(401, {})] * 3), cache_path=cache,
                       now=clock.now, sleep=nosleep)
    assert st.is_stale()
    assert "STALE" in st.marker()
    d = pg.decide("News", st)
    assert d.action == pg.HOLD and "stale" in d.reason


def test_cache_reads_the_flat_legacy_block(tmp_path, clock, nosleep):
    cache = cache_file(tmp_path, ts=clock.now() - 60, schema2=False)
    st = pg.cell_state(session=False, cache_path=cache, now=clock.now, sleep=nosleep)
    assert st.counts == REAL_USA_D1 and st.source == "cache"


def test_cache_falls_back_to_top_level_ts_when_the_pair_has_none(tmp_path, clock, nosleep):
    """The crawler writes per-pair counts with only a document-level ts. Age must still be known,
    because an unknown age refuses."""
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"ts": clock.now() - 120,
                             "pairs": [{"region": "USA", "delay": 1,
                                        "counts": dict(REAL_USA_D1)}]}))
    st = pg.cell_state(session=False, cache_path=p, now=clock.now, sleep=nosleep)
    assert st.age_s == pytest.approx(120)


def test_no_session_and_no_cache_is_unavailable(tmp_path, clock, nosleep):
    st = pg.cell_state(session=False, cache_path=tmp_path / "missing.json",
                       now=clock.now, sleep=nosleep)
    assert st.counts is None and st.source == "unavailable"
    assert "NO CELL DATA" in st.marker()
    assert pg.decide("News", st).action == pg.HOLD


def test_unparseable_live_payload_falls_through_to_refusal(tmp_path, clock, nosleep):
    s = FakeSession([_Resp(200, {"pyramids": "nope"})] * 3)
    st = pg.cell_state(session=s, cache_path=tmp_path / "missing.json",
                       now=clock.now, sleep=nosleep)
    assert st.counts is None
    assert "payload" in (st.error or "")
    assert pg.decide("News", st).action == pg.HOLD


def test_cache_holding_a_different_pair_is_not_used(tmp_path, clock, nosleep):
    cache = cache_file(tmp_path, region="EUR", ts=clock.now())
    st = pg.cell_state(session=False, cache_path=cache, now=clock.now, sleep=nosleep)
    assert st.counts is None and st.source == "unavailable"


def test_session_false_makes_no_request(tmp_path, clock, nosleep):
    st = pg.cell_state(session=False, cache_path=cache_file(tmp_path, ts=clock.now()),
                       now=clock.now, sleep=nosleep)
    assert st.source == "cache"


def test_cell_state_never_raises(tmp_path, clock, nosleep):
    """Any failure it can be handed must degrade to a refusable state, not an exception, or the
    caller's error path becomes the submit path."""
    for script in ([RuntimeError("boom")] * 3, [_Resp(200, ValueError("bad json"))] * 3,
                   [_Resp(429, {})] * 3):
        st = pg.cell_state(session=FakeSession(script), cache_path=tmp_path / "none.json",
                           now=clock.now, sleep=nosleep)
        assert st.counts is None
        assert pg.decide("News", st).action == pg.HOLD


def test_cell_state_does_not_write_the_shared_artifact(tmp_path, clock, nosleep):
    """Two owners on one path clobbered this artifact once already (2026-08-10). This module is a
    reader; the file's bytes must be identical after a live read."""
    cache = cache_file(tmp_path, ts=clock.now())
    before = cache.read_bytes()
    pg.cell_state(session=FakeSession([_Resp(200, payload())] * 3), cache_path=cache,
                  now=clock.now, sleep=nosleep)
    assert cache.read_bytes() == before


def test_module_contains_no_submit_path():
    """The decider must stay POST-free: a submit is irreversible and this file is run casually.

    Checked on the AST, not on the text, so prose about tools/submit_alphas.py does not trip it and
    a real call cannot hide inside a comment-shaped line."""
    import ast
    tree = ast.parse(Path(pg.__file__).read_text())
    writes = [n.attr for n in ast.walk(tree)
              if isinstance(n, ast.Attribute) and n.attr in {"post", "put", "patch", "delete"}]
    assert writes == [], f"write-verb call in a decider: {writes}"
    urls = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and "submit" in n.value.lower()
            and (n.value.startswith("/") or "http" in n.value.lower())]
    assert urls == [], f"submit-shaped URL literal: {urls}"


# ================================================== 6. cross-check against the real on-disk artifact

def test_real_artifact_parses_into_a_usable_pair():
    """Second derivation from a different source than the fixture. Structural only — the counts
    themselves move as cells fill, and pinning them here would make a real submit break the suite."""
    real = pg.CACHE_PATH
    if not real.exists():
        pytest.skip("state/pyramid_cell_counts.json not present")
    st = pg.cell_state(session=False, cache_path=real)
    assert st.source == "cache", st.error
    assert set(st.counts) == set(REAL_USA_D1), "USA d1 category set changed"
    assert all(isinstance(v, int) and v >= 0 for v in st.counts.values())
    assert st.age_s is not None and st.age_s >= 0
