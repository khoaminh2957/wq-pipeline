#!/usr/bin/env python3
"""END-TO-END ADVERSARIAL REHEARSAL of the automatic submitter (USA, delay 1).

EVERY test runs with `socket.socket` replaced by a raiser, and `test_socket_ban_fires` proves the
ban is real rather than assumed. Nothing here may reach the network, and in particular nothing may
reach POST /alphas/{id}/submit: that request exists once per alpha, and a 403 is the platform
ADJUDICATING it, which permanently destroys the alpha.

All four modules landed and are exercised UNMODIFIED and for real. The only doubles are the ranker
(so a test can aim candidates at a chosen cell) and the live pyramid reading (opening a socket is
forbidden here). Tests named `test_hole_` document behaviour of the landed modules that no guard
stops; they ASSERT the hole, so closing it breaks the test and says so.
"""
import json, pathlib, socket, sys, types
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import submit_plan as SP                                                     # noqa: E402
import pyramid_gate as PG                                                    # noqa: E402
import auto_submit as AS                                                     # noqa: E402
import cell_map as CM                                                        # noqa: E402
import time as _time                                                         # noqa: E402


# ------------------------------------------------------------------ the network is off

class NetworkTouched(AssertionError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise NetworkTouched("a test opened a socket")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_socket_ban_fires():
    with pytest.raises(NetworkTouched):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(NetworkTouched):
        socket.create_connection(("127.0.0.1", 1))


def test_no_transport_object_raises_on_every_verb():
    t = SP.NoTransport()
    for verb in ("post", "get", "put", "request"):
        with pytest.raises(AssertionError, match="reached the network"):
            getattr(t, verb)("https://example.invalid")


# ------------------------------------------------------------------ fixtures

# The live USA d1 state this rehearsal is aimed at. Re-derived two ways: the platform counter in
# state/pyramid_cell_counts.json, and cell_map's R2 (summing memberships over ACTIVE alphas).
LIVE = {"Price Volume": 40, "Model": 19, "Fundamental": 3, "Option": 3, "Analyst": 3, "Other": 3,
        "Earnings": 3, "Risk": 3, "Institutions": 3, "Macro": 3, "News": 2, "Insiders": 2,
        "Sentiment": 1, "Social Media": 0, "Short Interest": 0, "Imbalance": 0}

# Real field ids from fetched/rc/fields/USA_TOP3000_d1.jsonl, the catalog cell_map scores "high".
FIELD = {"News": "news_relevance_score_2", "Insiders": "board_departure_rate_1y_board",
         "Sentiment": "news_sentiment_score", "Social Media": "aggregate_large_target_long_horizon_return",
         "Short Interest": "prior_short_interest_predicted_value", "Imbalance": "imb5_score",
         "Price Volume": "atm_call_option_delta_value"}


def _pool():
    """Real field ids per category, straight from the catalog cell_map scores "high". Distinct
    fields give distinct mechanics (submit_rank.mechanic_of = the set of non-carrier fields), so a
    capacity test measures capacity and not the mechanic guard."""
    import collections
    out = collections.defaultdict(list)
    for line in open(ROOT / "fetched/rc/fields/USA_TOP3000_d1.jsonl"):
        d = json.loads(line)
        c = d.get("category")
        out[c.get("name") if isinstance(c, dict) else c].append(d["id"])
    return {k: sorted(v)[:8] for k, v in out.items()}


POOL = _pool()
SENTIMENT_FIELDS = POOL["Sentiment"]


def distinct(cell, n):
    """Up to n formulas in `cell` with DISTINCT mechanics (mechanic_of = the set of fields read).

    Singles first, then PAIRS, because thin cells exist: Imbalance has exactly 2 fields in the whole
    USA_TOP3000_d1 catalog, so it can express at most C(2,1)+C(2,2) = 3 distinct mechanics. May
    return fewer than n; callers assert on what they need, not on what they asked for."""
    import itertools
    f = POOL[cell]
    out = [f"rank(ts_delta({x},5))" for x in f[:n]]
    for a, b in itertools.combinations(f[:12], 2):
        if len(out) >= n:
            break
        out.append(f"rank(add({a},{b}))")
    return out[:n]


def state(counts=None, age=60.0, source="live", region="USA", delay=1):
    c = dict(LIVE if counts is None else counts)
    return PG.CellState(region, delay, c, _time.time() - age, age, source, 3, None)


def formula(cell, k=0):
    """A one-field formula that cell_map resolves to exactly `cell`, high confidence."""
    return f"rank(ts_delta({FIELD[cell]},{5 + k}))"


def cand(aid, cell, k=0, prod=0.55, self_c=0.40):
    return {"alpha": aid, "prod_max": prod, "self_corr": self_c, "formula": formula(cell, k)}


import submit_rank as SR                                                    # noqa: E402
_REAL_RANK = SR.rank_for_cell


def rank_double(fn):
    """Replace ONLY rank_for_cell on the real module.

    Swapping the whole module out for a stub also removed submit_rank.mechanic_of, which the driver
    depends on — the double would have been testing a different program."""
    SR.rank_for_cell = fn
    sys.modules["submit_rank"] = SR
    return SR


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    SR.rank_for_cell = _REAL_RANK
    monkeypatch.setattr(SP, "KILL", tmp_path / "SUBMIT_KILL")
    monkeypatch.setattr(SP, "SCRATCH_DECISIONS", tmp_path / "decisions.json")
    monkeypatch.setattr(AS, "KILL_SWITCH", tmp_path / "AUTO_SUBMIT_STOP")
    monkeypatch.setattr(AS, "JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr(AS, "DECISIONS", tmp_path / "live_decisions.json")
    yield
    SR.rank_for_cell = _REAL_RANK


def go(cands, cells=None, **kw):
    return SP.run(cands, dry_run=True, cells_state=cells or state(), out=lambda *a: None, **kw)


# ================================================================== the driver

def test_real_chain_plans_and_never_touches_the_network():
    """pyramid_gate + cell_map + auto_submit, all real, one fake ranker. 0 POSTs."""
    cs = [cand("A1", "News"), cand("A2", "Insiders")]
    rank_double(lambda cell, pool: list(pool))
    rows, notes = go(cs)
    assert {r["cell"] for r in rows} == {"News", "Insiders"}
    assert all(r["handoff"] == "planned" for r in rows)
    assert all(r["corr"].startswith("prod ") for r in rows)


def test_missing_piece_refuses_naming_the_seam(monkeypatch):
    """All four landed. Simulate one going away: the driver must name the seam, not degrade."""
    import builtins
    real = builtins.__import__

    def blocked(name, *a, **k):
        if name == "submit_rank":
            raise ImportError("simulated absence")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", blocked)
    monkeypatch.delitem(sys.modules, "submit_rank", raising=False)
    with pytest.raises(SP.Refusal) as e:
        go([cand("A1", "News")])
    assert "submit_rank" in str(e.value)


def test_contract_name_absent_refuses(monkeypatch):
    rank_double(lambda cell, pool: list(pool))
    monkeypatch.delattr(sys.modules["submit_rank"], "rank_for_cell")
    with pytest.raises(SP.Refusal, match="contract name"):
        go([cand("A1", "News")])


# ------------------------------------------------------------------ ATTACK: stale / cached counts

def test_stale_count_refuses():
    rank_double(lambda cell, pool: list(pool))
    with pytest.raises(SP.Refusal, match="stale count"):
        go([cand("A1", "News")], cells=state(age=SP.MAX_COUNT_AGE_S + 60))


def test_cached_source_refuses_even_when_fresh():
    """The on-disk artifact is 60h old and pyramid_gate correctly calls it stale. But a cache
    written 10 minutes ago passes pyramid_gate's age test while saying nothing about NOW."""
    rank_double(lambda cell, pool: list(pool))
    with pytest.raises(SP.Refusal, match="not 'live'"):
        go([cand("A1", "News")], cells=state(age=600, source="cache"))


def test_the_real_on_disk_cache_is_refused_today():
    st = PG.cell_state(session=False)
    assert st.source == "cache"
    assert st.age_s > 6 * 3600, f"artifact age {st.age_s}s — this test's premise moved"
    with pytest.raises(SP.Refusal):
        SP.check_counts(st)


# ------------------------------------------------------------------ ATTACK: cell capacity

def test_full_cell_is_never_planned():
    rank_double(lambda cell, pool: list(pool))
    rows, _ = go([cand("A1", "Price Volume")])
    assert rows == []


def test_last_free_slot_not_double_spent():
    """Insiders is at 2/3 and needs exactly one. Offer it three."""
    rank_double(lambda cell, pool: list(pool))
    rows, _ = go([dict(cand(f"A{i}", "Insiders"), formula=f)
                  for i, f in enumerate(distinct("Insiders", 3))])
    assert len([r for r in rows if r["cell"] == "Insiders"]) == 1


def test_capacity_respected_across_a_multi_slot_cell():
    """Sentiment is at 1/3: exactly two, never three. Distinct mechanics so only capacity binds."""
    rank_double(lambda cell, pool: list(pool) if cell == "Sentiment" else [])
    cs = [dict(cand(f"S{i}", "Sentiment"), formula=f)
          for i, f in enumerate(distinct("Sentiment", 5))]
    rows, _ = go(cs)
    assert len(rows) == 2


# ------------------------------------------------------------------ ATTACK: mechanic collision

def test_two_rows_same_mechanic_are_not_both_planned():
    """Sentiment needs 2. Hand it two alphas that read the SAME field (different decay only).

    The second is DROPPED loudly rather than refusing the whole run: dropping already prevents the
    harm, and a whole-run refusal would let one clash cost the other twelve cells."""
    rank_double(lambda cell, pool: list(pool) if cell == "Sentiment" else [])
    cs = [cand("S1", "Sentiment", k=1), cand("S2", "Sentiment", k=2)]
    assert SP.mechanic_of(cs[0]["formula"]) == SP.mechanic_of(cs[1]["formula"])
    rows, notes = go(cs)
    assert len(rows) == 1
    assert any("DROP S2" in n and "shares mechanic" in n for n in notes)


# ------------------------------------------------------------------ ATTACK: correlation

def test_alpha_with_no_self_corr_is_dropped():
    """auto_submit reads prod_maxcorr only; a missing SELF verdict would sail past it."""
    rank_double(lambda cell, pool: list(pool))
    c = cand("A1", "News")
    c["self_corr"] = None
    rows, notes = go([c])
    assert rows == []
    assert any("no measured SELF verdict" in n for n in notes)


def test_alpha_with_no_prod_corr_is_dropped():
    rank_double(lambda cell, pool: list(pool))
    c = cand("A1", "News")
    c["prod_max"] = None
    rows, notes = go([c])
    assert rows == [] and any("no measured prod" in n for n in notes)


def test_self_corr_over_gate_is_dropped():
    rank_double(lambda cell, pool: list(pool))
    rows, notes = go([cand("A1", "News", self_c=0.99)])
    assert rows == [] and any("0.99" in n for n in notes)


# ------------------------------------------------------------------ ATTACK: guessed category

def test_unresolved_formula_token_is_dropped_not_guessed():
    rank_double(lambda cell, pool: list(pool))
    c = cand("A1", "News")
    c["formula"] = "rank(ts_delta(a_field_that_does_not_exist_anywhere,5))"
    rows, notes = go([c])
    assert rows == [] and any("cell_map refuses" in n for n in notes)


def test_three_cell_alpha_is_dropped_credited_nowhere():
    """cell_map R3: both 3-cell alphas on this account read pyramidThemes.effective == 0. A submit
    on one spends a slot and unlocks nothing."""
    rank_double(lambda cell, pool: list(pool))
    c = cand("A1", "News")
    c["formula"] = (f"add(add({FIELD['News']},{FIELD['Insiders']}),{FIELD['Imbalance']})")
    v = CM.cells_for(c["formula"])
    assert len(v.predicted) >= 3 and v.refuse
    rows, notes = go([c])
    assert rows == [] and any("cell_map refuses" in n for n in notes)


def test_no_formula_on_record_is_dropped():
    rank_double(lambda cell, pool: list(pool))
    c = cand("A1", "News")
    c["formula"] = ""
    rows, notes = go([c])
    assert rows == [] and any("no formula on record" in n for n in notes)


# ------------------------------------------------------------------ ATTACK: scope

def test_out_of_scope_region_refuses_whole_run():
    rank_double(lambda cell, pool: list(pool))
    with pytest.raises(SP.Refusal, match="scoped to USA/1"):
        go([cand("A1", "News")], cells=state(region="EUR"))


def test_out_of_scope_delay_refuses_whole_run():
    rank_double(lambda cell, pool: list(pool))
    with pytest.raises(SP.Refusal, match="scoped to USA/1"):
        go([cand("A1", "News")], cells=state(delay=0))


def test_driver_asks_cell_map_for_usa_d1_only():
    seen = []
    real = CM.cells_for
    try:
        CM.cells_for = lambda code, region="USA", delay=1, universe="TOP3000": (
            seen.append((region, delay)) or real(code, region, delay, universe))
        rank_double(lambda cell, pool: list(pool))
        go([cand("A1", "News")])
    finally:
        CM.cells_for = real
    assert seen and set(seen) == {("USA", 1)}


def test_emitted_decisions_are_all_usa_d1():
    rank_double(lambda cell, pool: list(pool))
    rows, _ = go([cand("A1", "News"), cand("A2", "Insiders")])
    doc = json.loads(SP.SCRATCH_DECISIONS.read_text())
    assert doc["decisions"]
    for d in doc["decisions"].values():
        assert (d["region"], d["delay"]) == ("USA", 1)


# ------------------------------------------------------------------ ATTACK: kill switch

def test_kill_switch_before_planning():
    rank_double(lambda cell, pool: list(pool))
    SP.KILL.write_text("halt")
    with pytest.raises(SP.Refusal, match="kill switch"):
        go([cand("A1", "News")])


def test_auto_submit_kill_switch_also_stops_the_driver():
    """Two switch files exist. An operator who trips auto_submit's must stop the planner too."""
    rank_double(lambda cell, pool: list(pool))
    AS.KILL_SWITCH.write_text("halt")
    with pytest.raises(SP.Refusal, match="kill switch"):
        go([cand("A1", "News")])


def test_kill_switch_tripped_mid_run_stops_the_rest():
    rank_double(lambda cell, pool: list(pool))
    calls = {"n": 0}
    real = SP.kill_engaged

    def flip():
        calls["n"] += 1
        return calls["n"] > 2          # off for pre-flight and row 1, on from row 2
    SP.kill_engaged = flip
    try:
        rows, _ = go([cand("A1", "News"), cand("A2", "Insiders"),
                      dict(cand("A3", "Sentiment"),
                           formula=distinct("Sentiment", 1)[0])])
    finally:
        SP.kill_engaged = real
    assert sum(1 for r in rows if r.get("handoff") == "planned") == 1
    assert any(r.get("handoff", "").startswith("HALTED") for r in rows)


# ------------------------------------------------------------------ ATTACK: the crash window

def test_unresolved_intent_from_a_crash_blocks_that_alpha():
    """A journalled intent with no outcome: the POST may have landed. auto_submit.post_permitted
    is the owner of that rule and the driver defers to it rather than reimplementing it."""
    rank_double(lambda cell, pool: list(pool))
    AS.JOURNAL.write_text(json.dumps({"event": "intent", "alpha": "A1"}) + "\n")
    rows, notes = go([cand("A1", "News")])
    assert rows == []
    assert any("NO recorded outcome" in n for n in notes)


def test_resolved_terminal_intent_also_blocks():
    rank_double(lambda cell, pool: list(pool))
    AS.JOURNAL.write_text(
        json.dumps({"event": "intent", "alpha": "A1"}) + "\n" +
        json.dumps({"event": "outcome", "alpha": "A1", "status": 403,
                    "classification": "spent", "disposition": AS.TERMINAL}) + "\n")
    rows, notes = go([cand("A1", "News")])
    assert rows == [] and any("TERMINAL" in n for n in notes)


# ------------------------------------------------------------------ ATTACK: arming the live tool

def test_driver_refuses_to_write_the_live_decisions_path():
    """Writing state/auto_submit_decisions.json is not reporting, it is ARMING: it is the only
    input `auto_submit --i-am-spending-real-submissions` reads."""
    rank_double(lambda cell, pool: list(pool))
    with pytest.raises(SP.Refusal, match="arm the irreversible tool"):
        go([cand("A1", "News")], decisions_path=AS.DECISIONS)


def test_driver_has_no_live_mode():
    with pytest.raises(SP.Refusal, match="no live mode"):
        SP.run([], dry_run=False)


def test_driver_source_contains_no_http_client():
    src = (ROOT / "tools/submit_plan.py").read_text()
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    code = code.split('"""', 2)[-1]          # drop the module docstring
    assert "import requests" not in code
    assert ".post(" not in code
    assert "http" not in code.lower().replace("https://", "")


def test_ranker_inventing_an_alpha_refuses():
    rank_double(lambda cell, pool: ["GHOST01"])
    with pytest.raises(SP.Refusal, match="not a candidate"):
        go([cand("A1", "News")])


# ================================================================== HOLES IN THE LANDED MODULES
# These assert what the chain DOES today. If a piece is fixed, the test fails and says so.

def _dec(cell, formula_, region="USA", delay=1):
    return {"cell": cell, "region": region, "delay": delay, "reason": "r",
            "formula": formula_, "family": "fam"}


def _ctx(tmp_path, prod=0.1):
    # A CLEAN SELF VERDICT IS PART OF THE FIXTURE, not decoration. `auto_submit` now refuses a
    # missing self reading, so a fixture without one makes every downstream hole test refuse for the
    # WRONG reason -- the chain stops before it ever reaches the hole being probed, and the test
    # reports "FIXED" about a gap that is merely masked. That is a false sense of safety on the
    # irreversible path, which is worse than the hole it hides.
    (tmp_path / "corr.json").write_text(json.dumps(
        {"A1": {"prod_maxcorr": prod, "prod_breach_count": 0,
                "self_maxcorr": 0.31, "self_measured": True}}))
    (tmp_path / "banned.json").write_text(json.dumps({"banned_fields": []}))
    (tmp_path / "ledger.jsonl").write_text("")
    # AND A PERMISSIVE LIVE-CELL CHECKER, for exactly the same reason as the self verdict above.
    # `auto_submit.preflight` now asks `pyramid_gate` for the live count on the irreversible path.
    # Without an injection here that call goes to the network, the socket ban turns it into a
    # refusal, and every test probing a DIFFERENT hole stops before reaching its hole and reports
    # "FIXED". A test that is green because the chain died early is worse than a red one.
    return {"corr": str(tmp_path / "corr.json"), "banned": str(tmp_path / "banned.json"),
            "cell_ok": lambda cell, cfg: (True, f"live cell {cell} at 2/3, needs 1 (INJECTED)"),
            "ledger": str(tmp_path / "ledger.jsonl"), "journal": tmp_path / "j.jsonl",
            "kill": str(tmp_path / "nokill"), "today": "2026-08-13"}


def test_hole_auto_submit_preflight_accepts_a_full_cell(tmp_path):
    """CLOSED 2026-08-13, and it was the most expensive hole in the chain.

    `auto_submit.preflight` trusted the decisions file's word about the cell and never asked the
    live counter, so a decision naming `Price Volume` (live 40, unlocks at 3) reached a POST. It now
    calls `pyramid_gate` on the irreversible path -- which reads the count three times and keeps the
    MAX, because an under-count says a full cell still needs alphas.

    Kept as a regression test rather than deleted: this is the record that the gap existed, and the
    tripwire if the wiring is ever removed. The behavioural half lives in
    `test_auto_submit.py::test_a_full_cell_is_refused_even_when_the_decision_file_says_otherwise`.
    """
    import auto_submit as AS
    src = pathlib.Path(AS.__file__).read_text()
    assert 'checker = ctx.get("cell_ok") or _live_cell_ok' in src
    assert "def _live_cell_ok" in src
    i_use = src.index('ctx.get("cell_ok") or _live_cell_ok')
    i_ret = src.index('return True, f"{corr_note}; {why}"')
    assert i_use < i_ret, "the live cell check must gate the permitting return"

    # and it must actually refuse, not merely be present
    ok, why = AS.preflight(
        "A1",
        {"cell": "Price Volume", "region": "USA", "delay": 1, "reason": "r",
         "formula": "close", "family": "f"},
        {"region": "USA", "delay": 1}, [],
        dict(_ctx(tmp_path),
             cell_ok=lambda c, g: (False, f"live cell check refuses {c}: full 40/3")))
    assert ok is False and "full" in why


def test_hole_auto_submit_accepts_a_cell_the_alpha_does_not_belong_to(tmp_path):
    """The decision says News; the formula is pure Price Volume. preflight never cross-checks the
    formula against the cell, so the label is taken on trust."""
    ok, why = AS.preflight("A1", _dec("News", formula("Price Volume")),
                           {"region": "USA", "delay": 1}, [], _ctx(tmp_path))
    assert ok is True, "FIXED: auto_submit now cross-checks formula vs cell — update this test"
    assert CM.cells_for(formula("Price Volume")).cells == frozenset({"Price Volume"})


def _corr_file(mapping):
    """Write a correlation store to a temp path and return it."""
    import json as _j, tempfile, pathlib as _p
    f = _p.Path(tempfile.mkdtemp()) / "corr.json"
    f.write_text(_j.dumps(mapping))
    return f


def test_hole_auto_submit_has_no_self_correlation_gate(tmp_path):
    """prod 0.10 and self 0.99 is a certain rejection, and a 403 adjudicates. Nothing on the
    auto_submit path reads self-corr at all."""
    ok, why = AS.preflight("A1", _dec("News", formula("News")),
                           {"region": "USA", "delay": 1}, [], _ctx(tmp_path, prod=0.10))
    # (the two pre-fix assertions that stood here -- "ok is True" and "self" absent from the
    # reason -- described the hole and are gone with it; the reason string now names both axes)
    # CLOSED 2026-08-13. This hole was real and is now fixed, so the test is inverted rather than
    # deleted -- it is the record that the gap existed and the tripwire if it ever reopens.
    #
    # The old assertion grepped the whole file for the substring "self", which is a bad instrument
    # twice over: it matched "itself" in an unrelated comment, and it could never have distinguished
    # a real gate from a mention of one. Check the behaviour instead.
    import auto_submit as _AS
    assert _AS.SELF_CORR_MAX == 0.70
    ok, why = _AS.corr_verdict("Z", corr_path=_corr_file(
        {"Z": {"prod_maxcorr": 0.10, "prod_breach_count": 0, "self_maxcorr": 0.95,
               "self_measured": True}}))
    assert ok is False and "self_maxcorr" in why, "a dirty self-correlation must refuse"
    ok2, why2 = _AS.corr_verdict("Z", corr_path=_corr_file(
        {"Z": {"prod_maxcorr": 0.10, "prod_breach_count": 0}}))
    assert ok2 is False and "self" in why2.lower(), "a MISSING self verdict must refuse too"


def test_hole_region_is_a_free_cli_argument_not_a_lock(tmp_path):
    """pyramid_gate hardcodes USA/1 — and is never asked. auto_submit takes --region from argv and
    only checks the decisions file AGREES with it. Two files saying EUR submit into EUR."""
    ok, why = AS.preflight("A1", _dec("News", formula("News"), region="EUR", delay=0),
                           {"region": "EUR", "delay": 0}, [], _ctx(tmp_path))
    assert ok is True, "FIXED: auto_submit now pins the pair — update this test"


def test_hole_stale_counts_are_laundered_by_a_fresh_as_of(tmp_path):
    """THE FRESHNESS LAUNDERING PATH.

    pyramid_gate accepts a CACHED count up to 6h old (STALE_AFTER_S) and its `decide` never tests
    `source`. auto_submit tests the DECISIONS FILE's own as_of against 1h — not the age of the
    counts the decisions were derived from. So counts 5h59m old, written into a decisions file
    stamped `now`, clear both gates. The driver's own check_counts is what refuses it."""
    old = state(age=6 * 3600 - 60, source="cache")
    assert PG.decide("News", old).action == PG.SUBMIT      # gate says go on a 5h59m cache
    import datetime
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             "decisions": {"A1": _dec("News", formula("News"))}}))
    decisions, err = AS.load_decisions(p)
    assert err is None and "A1" in decisions               # submitter sees a "fresh" file
    with pytest.raises(SP.Refusal, match="not 'live'"):    # only this driver stops it
        SP.check_counts(old)


def test_hole_g6_family_key_disagrees_with_the_mechanic_key():
    """TWO IDENTITY KEYS, AND THE CHOICE IS LOAD-BEARING.

    harness.guards.reserve_submit refuses a second submit-test per `family` per platform day, and
    `family` is a free string from the decisions file. `_famof` collapses to the first field token's
    PREFIX, so two alphas filling two DIFFERENT cells key the same and cannot both land today.
    Write submit_rank's fine mechanic there instead and the family cap never binds at all."""
    from harness.guards import _famof
    news, senti = formula("News"), formula("Sentiment")
    assert CM.cells_for(news).cells == frozenset({"News"})
    assert CM.cells_for(senti).cells == frozenset({"Sentiment"})
    assert _famof(news) == _famof(senti) == "news"          # different cells, one G6 family
    assert SP.mechanic_of(news) != SP.mechanic_of(senti)    # ...and two mechanics
    rank_double(lambda cell, pool: list(pool))
    rows, notes = go([dict(cand("N1", "News"), formula=news),
                      dict(cand("S1", "Sentiment"), formula=senti)])
    assert len(rows) == 2
    assert any("G6 COLLISION" in n for n in notes), "the plan must SAY these cannot both land today"


def test_hole_submit_rank_counts_group_operands_as_fields():
    """submit_rank._OPS omits industry/sector/subindustry/market/country, which harness.guards._SKIP
    does list. So the SAME signal neutralized two ways reads as two mechanics, and the mechanic
    de-dup that exists to stop two submits landing on one signal does not fire."""
    import submit_rank as SRm
    for tok in ("industry", "sector", "subindustry", "market", "country"):
        assert tok not in SRm._OPS, f"FIXED: {tok} now skipped — update this test"
    f = FIELD["Sentiment"]
    a = SRm.mechanic_of(f"group_neutralize({f},industry)")
    b = SRm.mechanic_of(f"group_neutralize({f},sector)")
    assert a != b, "same signal, two neutralizations, two mechanic keys"
    assert a == f"industry+{f}" and b == f"{f}+sector"


def test_empty_plan_explains_itself_per_cell():
    """0 rows with no reason is indistinguishable from a broken wire. Every open cell that
    produced nothing must name why."""
    rank_double(lambda cell, pool: [])
    rows, notes = go([cand("A1", "News")])
    assert rows == []
    named = [n for n in notes if "ranker returned NOTHING" in n]
    assert len(named) == 6, f"6 open cells, {len(named)} explained"


def test_real_inventory_plans_zero_and_says_why():
    """END TO END on the actual ledger, real ranker, real cell_map, real gate. The honest answer
    today is ZERO, and every cell carries its cause."""
    rows, notes = SP.run(SP.load_candidates(), dry_run=True,
                         cells_state=state(), out=lambda *a: None)
    assert rows == []
    why = " ".join(notes)
    for cell in ("News", "Insiders", "Sentiment", "Imbalance", "Short Interest", "Social Media"):
        assert cell in why, f"{cell} produced no row and no explanation"
    assert "SPENT" in why or "PROD_FAIL" in why or "CLAIMS" in why


# ================================================================== blast radius

def test_blast_radius_driver_guards_intact():
    """The whole open-cell budget for USA d1 is 13. With guards on, one run plans at most that."""
    rank_double(lambda cell, pool: list(pool))
    need = {c: 3 - n for c, n in LIVE.items() if n < 3}
    assert sum(need.values()) == 13
    cs, i = [], 0
    for cell, n in need.items():
        for f in distinct(cell, n + 2):
            cs.append({"alpha": f"X{i:02d}", "prod_max": 0.55, "self_corr": 0.40, "formula": f})
            i += 1
    rows, _ = go(cs)
    assert len(rows) == 13
    assert len({r["alpha"] for r in rows}) == 13
    assert len({r["mechanic"] for r in rows}) == 13


def test_blast_radius_auto_submit_cap_is_the_only_structural_bound():
    assert AS.MAX_ALPHAS_PER_RUN == 4
    assert AS.MAX_ATTEMPTS_PER_ALPHA == 3
    assert AS.DAILY_SUBMIT_QUOTA == 4
    b = SP.blast_radius()
    assert b["auto_submit run cap"] == 4
    assert b["POST requests at that cap"] == 12


def test_blast_radius_run_cap_holds_when_every_preflight_passes(tmp_path, monkeypatch):
    """Every guard forced open: 40 candidates, preflight always ok, transport always 200.
    The run cap must still stop at 4 alphas."""
    import datetime
    # CORRECTED 2026-08-13. The cap this test pinned counts POSTs that SUCCEED, and a 403 does not
    # succeed -- it ADJUDICATES, spending the alpha forever. So 40 candidates meant 4 accepted and up
    # to 36 destroyed. `MAX_DECISIONS_PER_RUN` now bounds the READ and refuses an oversized list
    # outright, which is why this run POSTs nothing at 40.
    monkeypatch.setattr(AS, "preflight", lambda *a, **k: (True, "forced open"))
    posts = []

    class Yes:
        status_code, text = 200, "{}"

    class T:
        def post(self, url, timeout=None):
            posts.append(url)
            return Yes()

    monkeypatch.setattr(AS, "reserve_submit", lambda a, f: (True, "ok"))
    monkeypatch.setattr(AS, "release_submit", lambda a: None)
    p = tmp_path / "d.json"
    p.write_text(json.dumps({
        "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "decisions": {f"A{i:02d}": _dec("News", formula("News")) for i in range(40)}}))
    res = AS.run({"region": "USA", "delay": 1}, T(), live=True,
                 ctx={"decisions": str(p), "journal": tmp_path / "j.jsonl",
                      "kill": str(tmp_path / "nokill"), "today": "2026-08-13"},
                 out=lambda *a: None, sleep=lambda *a: None)
    assert len(posts) == 0, "an oversized decisions list must be REFUSED, not truncated to 4"
    assert AS.MAX_DECISIONS_PER_RUN == 8
    assert res == [], "a refused run must accept nothing at all"

    # And within the bound the success cap is still the inner limit, so both bounds are pinned here
    # rather than one of them being taken on trust.
    p.write_text(json.dumps({
        "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "decisions": {f"B{i:02d}": _dec("News", formula("News"))
                      for i in range(AS.MAX_DECISIONS_PER_RUN)}}))
    posts.clear()
    res2 = AS.run({"region": "USA", "delay": 1}, T(), live=True,
                  ctx={"decisions": str(p), "journal": tmp_path / "j2.jsonl",
                       "kill": str(tmp_path / "nokill"), "today": "2026-08-13"},
                  out=lambda *a: None, sleep=lambda *a: None)
    assert sum(1 for r in res2 if r.get("result") == "accepted") == AS.MAX_ALPHAS_PER_RUN


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
