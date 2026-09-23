"""The layered runner must use the platform's real concurrency shape without losing a row.

Every assertion here traces to something that cost this project real simulations or real evidence:

  * ONE POST PER SIMULATION at `--concurrency 8` put 8 in flight. The shape Khoa stated on
    2026-08-12 is **8 multisim parents x 10 children = 80** (OPERATOR-STATED; this repository has
    never measured it, and these tests measure the CLIENT's shape, not the platform's).
  * A CONCURRENT 429 journalled as `POST-429` and skipped burned 200 draws in seconds without
    spending one simulation. It is a WAIT. A DAILY 429 is the opposite: terminal for the day.
  * THE CHILD-ORDER GUARD. `children[i]` is attributed to `group[i]` on request order, an assumption
    no measurement on this machine can verify (`mg/simulate.py` OPEN_QUESTION 5). Against a replay
    that reversed 500 corpus children a FORMULA-ONLY guard refused 438 and let 20 through carrying a
    sibling's alpha id and metrics, and 42 more were never checked because the terminal-ERROR branch
    returned before the guard ran.
  * THE JOURNAL. The previous generation kept a sha256 `old_id` and no formula, and 2,639 simulated
    rows became unanalysable. A crash must cost only the rows still in flight.

NO TEST HERE MAY REACH THE NETWORK. `socket.socket` is monkeypatched to raise for every test in the
file, and `test_the_socket_guard_is_actually_armed` proves the guard fires rather than assuming it.
"""
import json
import time
import pathlib
import socket
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layered_sim as LS  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a test opened a socket")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(autouse=True)
def instant_polls(monkeypatch):
    """The poll cadence is not under test and a real sleep would make these tests useless.

    `poll`/`poll_parent` capture `time.sleep` as a DEFAULT ARGUMENT at def time, so patching the
    time module would not reach them; zeroing the two cadence constants does.
    """
    monkeypatch.setattr(LS, "POLL_FIRST_S", 0)
    monkeypatch.setattr(LS, "POLL_S", 0)


def test_the_socket_guard_is_actually_armed():
    """A fixture that silently failed to apply would make every other test here meaningless."""
    with pytest.raises(AssertionError, match="opened a socket"):
        socket.socket()


# ------------------------------------------------------------------ the fake platform

class FakeResp:
    def __init__(self, status_code, body=None, headers=None, text=""):
        self.status_code, self._body = status_code, body
        self.headers, self.text = headers or {}, text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakePlatform:
    """A WorldQuant that never touches a socket. It records the SHAPE of what the client asked for.

    A parent is IN FLIGHT from the moment its POST is accepted until the client's first poll of it
    returns terminal, which is how `peak_parents` measures what the dispatcher actually held open.
    """

    def __init__(self, *, max_parents=None, child_status="COMPLETE", reverse_children=False,
                 daily_after=None, concurrent_until_free=False, crash_at_post=None,
                 children_returned=None):
        self.max_parents = max_parents
        self.child_status = child_status
        self.reverse_children = reverse_children
        self.daily_after = daily_after                 # 1-based POST index that answers 429 DAILY
        self.concurrent_until_free = concurrent_until_free
        self.crash_at_post = crash_at_post             # 1-based POST index that blows up mid-batch
        self.children_returned = children_returned     # short-count a parent, to test the guard
        self.posts, self.sims, self.parents = [], {}, {}
        self.alpha_of_formula, self.live = {}, set()
        self.peak_parents, self.n_429 = 0, 0

    # -- POST ------------------------------------------------------------------
    def post(self, url, json=None, timeout=None):
        assert url.endswith("/simulations"), url
        self.posts.append(json)
        i = len(self.posts)
        if self.crash_at_post == i:
            raise RuntimeError("the process died mid-batch")
        if self.daily_after == i:
            self.n_429 += 1
            return FakeResp(429, text="SIMULATION_LIMIT_EXCEEDED: DAILY limit reached")
        if self.concurrent_until_free and self.max_parents is not None \
                and len(self.live) >= self.max_parents:
            self.n_429 += 1
            return FakeResp(429, text="CONCURRENT_SIMULATION_LIMIT_EXCEEDED")
        kids = json if isinstance(json, list) else [json]
        purl = "https://api.worldquantbrain.com/simulations/parent%d" % i
        curls = []
        for k, child in enumerate(kids):
            curl = "https://api.worldquantbrain.com/simulations/p%dc%d" % (i, k)
            alpha = "A%dC%d" % (i, k)
            self.sims[curl] = {"status": self.child_status, "alpha": alpha,
                               "regular": child["regular"], "settings": child["settings"],
                               "message": ""}
            self.alpha_of_formula[child["regular"]] = alpha
            curls.append(curl)
        if self.children_returned is not None:
            curls = curls[:self.children_returned]
        if self.reverse_children:
            curls = list(reversed(curls))
        if isinstance(json, list):
            self.parents[purl] = curls
            self.live.add(purl)
            self.peak_parents = max(self.peak_parents, len(self.live))
            return FakeResp(201, headers={"Location": purl})
        # A ONE-ELEMENT GROUP IS POSTED BARE, and the platform hands back the simulation itself.
        self.live.add(curls[0])
        self.peak_parents = max(self.peak_parents, len(self.live))
        return FakeResp(201, headers={"Location": curls[0]})

    # -- GET -------------------------------------------------------------------
    def get(self, url, timeout=None):
        if "/alphas/" in url:
            return FakeResp(200, {"is": {"sharpe": 1.5, "fitness": 1.1, "turnover": 0.3,
                                         "checks": [{"name": "LOW_SHARPE", "result": "PASS"}]}})
        if url in self.parents:
            self.live.discard(url)
            return FakeResp(200, {"status": "COMPLETE", "children": self.parents[url]})
        if url in self.sims:
            self.live.discard(url)
            return FakeResp(200, dict(self.sims[url]))
        return FakeResp(404)


def synthetic(n):
    """Distinct formulas with distinct metas, so a mis-attribution has something to show up in."""
    return [("rank(close - %d)" % i,
             {"arm": "free", "n_legs": 1 + i % 3, "carrier": bool(i % 2),
              "legs": [{"outer": "rank", "inner": ["ts_mean"], "leaf": "close"}]})
            for i in range(n)]


def drive(monkeypatch, tmp_path, platform, n, concurrency=8, children=10):
    monkeypatch.setattr(LS, "load_pools", lambda: ({}, {}, {}))
    # `run` now hands `draw` the factorial cell machinery (assigner / pool_c_kept / gate_pool),
    # so a fake that does not absorb keywords fails for a reason unrelated to what is under test.
    monkeypatch.setattr(LS, "draw", lambda a, b, c, rng, k, **kw: synthetic(k))
    monkeypatch.setattr(LS, "session", lambda: platform)
    out_path = tmp_path / "run.jsonl"
    rows = LS.run(n, seed=1, out_path=out_path, live=True, concurrency=concurrency,
                  children=children, out=lambda *a: None)
    lines = out_path.read_text().splitlines() if out_path.exists() else []
    on_disk = [json.loads(x) for x in lines]
    return rows, on_disk


def children_rows(rows):
    return [r for r in rows if r.get("status") != "PARENT-POSTED"]


# ------------------------------------------------------------------ the shape

def test_eight_parents_of_ten_children_is_eighty_in_flight(monkeypatch, tmp_path):
    """The whole point of the change: 8 POSTs hold 80 simulations, not 8.

    n=200 (20 groups) rather than n=80, so the ceiling is proved by the DISPATCHER holding at 8 and
    not by the batch running out of groups at exactly 8.
    """
    fake = FakePlatform()
    rows, on_disk = drive(monkeypatch, tmp_path, fake, 200, concurrency=8, children=10)

    assert fake.peak_parents == 8, "held %d parents open" % fake.peak_parents
    assert len(fake.posts) == 20
    assert {len(p) for p in fake.posts} == {10}, "every POST body is a list of ten children"
    assert all(isinstance(p, list) for p in fake.posts), "multisim bodies are LISTS"
    assert len(children_rows(rows)) == 200
    assert len(children_rows(on_disk)) == 200


def test_a_group_agrees_on_delay_region_universe(monkeypatch, tmp_path):
    """`MULTISIM_GROUP_KEYS` must hold inside every parent: a mixed-region batch is rejected 400."""
    fake = FakePlatform()
    drive(monkeypatch, tmp_path, fake, 40, concurrency=8, children=10)
    for body in fake.posts:
        keys = {tuple(child["settings"][k] for k in LS.MULTISIM_GROUP_KEYS) for child in body}
        assert len(keys) == 1, keys


def test_a_group_of_one_is_posted_bare_not_as_a_list_of_one(monkeypatch, tmp_path):
    """Whether the platform accepts a one-element LIST is UNKNOWN; `resim_bulk` sends a bare object
    and finding out otherwise would spend a simulation to learn nothing."""
    fake = FakePlatform()
    rows, _ = drive(monkeypatch, tmp_path, fake, 11, concurrency=8, children=10)
    assert [type(p) for p in fake.posts] == [list, dict]
    assert len(children_rows(rows)) == 11


def test_every_child_row_carries_its_own_formula_draw_and_alpha(monkeypatch, tmp_path):
    """The journal requirement, end to end: a row must name the formula, the arm and the full draw,
    and the alpha id it carries must be the one the platform issued FOR THAT FORMULA."""
    fake = FakePlatform()
    rows, on_disk = drive(monkeypatch, tmp_path, fake, 30, concurrency=8, children=10)
    seen = set()
    for r in children_rows(on_disk):
        assert r["formula"] and r["meta"]["arm"] and r["meta"]["legs"]
        assert r["settings"]["region"] == "USA"
        assert r["message"] is not None and "checks" in r
        assert r["alpha"] == fake.alpha_of_formula[r["formula"]], "mis-attributed row"
        assert r["parent_url"] and r["child_index"] is not None
        seen.add(r["formula"])
    assert len(seen) == 30


# ------------------------------------------------------------------ the two 429s

def test_a_concurrent_429_waits_and_loses_no_draw(monkeypatch, tmp_path):
    """Journalling `POST-429` and moving on burned 200 draws in seconds. The platform is saying all
    slots are busy; the answer is to reap one and try the SAME group again."""
    fake = FakePlatform(max_parents=2, concurrent_until_free=True)
    rows, on_disk = drive(monkeypatch, tmp_path, fake, 50, concurrency=8, children=10)

    assert fake.n_429 > 0, "the fake never actually refused a POST"
    assert not [r for r in rows if str(r.get("status", "")).startswith("POST-429")]
    assert len(children_rows(rows)) == 50, "a wait must not cost a draw"
    assert len(children_rows(on_disk)) == 50


def test_a_daily_429_stops_the_run(monkeypatch, tmp_path):
    """Terminal for the day. Re-probing a daily wall burned 4h45m on 2026-08-02."""
    fake = FakePlatform(daily_after=2)
    rows, on_disk = drive(monkeypatch, tmp_path, fake, 50, concurrency=8, children=10)

    assert len(fake.posts) == 2, "it kept POSTing past a DAILY 429"
    assert len(children_rows(rows)) == 10, "the accepted parent must still be drained"
    assert len(children_rows(on_disk)) == 10
    assert not [r for r in rows if str(r.get("status", "")).startswith("POST-429")]


def test_a_refused_post_fans_out_to_every_child(monkeypatch, tmp_path):
    """One `POST-400` row for a group of ten would drop nine formulas out of the evidence base."""
    class Refuser(FakePlatform):
        def post(self, url, json=None, timeout=None):
            self.posts.append(json)
            return FakeResp(400, text="bad request")
    fake = Refuser()
    rows, on_disk = drive(monkeypatch, tmp_path, fake, 10, concurrency=8, children=10)
    bad = [r for r in children_rows(on_disk) if r["status"] == "POST-400"]
    assert len(bad) == 10
    assert len({r["formula"] for r in bad}) == 10


# ------------------------------------------------------------------ the child-order guard

def test_the_guard_refuses_a_reversed_child(monkeypatch, tmp_path):
    """A mix-up files a REAL measurement under the WRONG construction, and both rows look genuine
    afterwards. Fail closed: spend the row, not the truth."""
    fake = FakePlatform(reverse_children=True)
    rows, on_disk = drive(monkeypatch, tmp_path, fake, 10, concurrency=8, children=10)
    kids = children_rows(on_disk)
    assert len(kids) == 10
    assert {r["status"] for r in kids} == {"GUARD-REFUSED"}
    assert not [r for r in kids if r["alpha"]], "a refused child must carry no alpha id"
    assert all("mismatch" in r["message"] for r in kids)


def test_the_guard_runs_on_a_terminal_error_child_too(monkeypatch, tmp_path):
    """42 of 500 reversed children were never checked at all, because the ERROR branch returned
    first. An ERROR filed against the wrong formula re-queues a sibling: the mistake is durable."""
    fake = FakePlatform(reverse_children=True, child_status="ERROR")
    _, on_disk = drive(monkeypatch, tmp_path, fake, 10, concurrency=8, children=10)
    assert {r["status"] for r in children_rows(on_disk)} == {"GUARD-REFUSED"}


def test_the_guard_passes_children_in_request_order(monkeypatch, tmp_path):
    """It must not refuse the honest case: the guard is a comparison, not a veto."""
    fake = FakePlatform()
    _, on_disk = drive(monkeypatch, tmp_path, fake, 10, concurrency=8, children=10)
    assert {r["status"] for r in children_rows(on_disk)} == {"COMPLETE"}


def test_the_guard_is_silent_when_the_platform_echoes_nothing(monkeypatch, tmp_path):
    """No echo means NOTHING IS CHECKED and nothing is claimed — never 'the mapping is correct'."""
    class NoEcho(FakePlatform):
        def get(self, url, timeout=None):
            r = super().get(url, timeout=timeout)
            if url in self.sims:
                body = r.json()
                body.pop("regular"), body.pop("settings")
                return FakeResp(200, body)
            return r
    fake = NoEcho(reverse_children=True)
    _, on_disk = drive(monkeypatch, tmp_path, fake, 10, concurrency=8, children=10)
    assert {r["status"] for r in children_rows(on_disk)} == {"COMPLETE"}


def test_a_short_child_list_attributes_nothing(monkeypatch, tmp_path):
    """Attributing the `min(len)` children that did arrive files every id after the first gap under
    another construction. None is attributed, and the shape reaches the journal."""
    fake = FakePlatform(children_returned=7)
    _, on_disk = drive(monkeypatch, tmp_path, fake, 10, concurrency=8, children=10)
    kids = children_rows(on_disk)
    assert len(kids) == 10
    assert {r["status"] for r in kids} == {"MULTISIM-CHILD-COUNT"}
    assert all("7 of 10" in r["message"] for r in kids)
    assert not [r for r in kids if r["alpha"]]


def test_one_failed_child_does_not_take_its_siblings(monkeypatch, tmp_path):
    """A dead child is that child's own outcome; unwinding the loop would cost nine real results."""
    fake = FakePlatform()
    monkeypatch.setattr(LS, "load_pools", lambda: ({}, {}, {}))
    # `run` now hands `draw` the factorial cell machinery (assigner / pool_c_kept / gate_pool),
    # so a fake that does not absorb keywords fails for a reason unrelated to what is under test.
    monkeypatch.setattr(LS, "draw", lambda a, b, c, rng, k, **kw: synthetic(k))
    monkeypatch.setattr(LS, "session", lambda: fake)
    real_get = fake.get

    def get(url, timeout=None):
        if url.endswith("c3"):
            return FakeResp(200, {"status": "ERROR", "message": "Incompatible unit",
                                  "regular": fake.sims[url]["regular"],
                                  "settings": fake.sims[url]["settings"]})
        return real_get(url, timeout=timeout)
    fake.get = get
    rows = LS.run(10, seed=1, out_path=tmp_path / "r.jsonl", live=True, concurrency=8,
                  children=10, out=lambda *a: None)
    kids = children_rows(rows)
    assert len(kids) == 10
    assert sum(1 for r in kids if r["status"] == "ERROR") == 1
    assert sum(1 for r in kids if r["status"] == "COMPLETE") == 9
    assert [r for r in kids if r["status"] == "ERROR"][0]["message"] == "Incompatible unit"


# ------------------------------------------------------------------ durability

def test_the_parent_handle_reaches_disk_before_the_first_poll(monkeypatch, tmp_path):
    """The window the line exists for is the one where the platform holds ten simulations and NOT
    ONE child row exists. A line written after the poll finishes is worth nothing to it."""
    _, on_disk = drive(monkeypatch, tmp_path, FakePlatform(), 20, concurrency=8, children=10)
    first_parent = next(i for i, r in enumerate(on_disk) if r["status"] == "PARENT-POSTED")
    first_child = next(i for i, r in enumerate(on_disk) if r["status"] != "PARENT-POSTED")
    assert first_parent < first_child
    parents = [r for r in on_disk if r["status"] == "PARENT-POSTED"]
    assert len(parents) == 2
    assert all(len(r["formulas"]) == 10 and r["parent_url"] for r in parents)


def test_a_crash_mid_batch_loses_no_journalled_row(monkeypatch, tmp_path):
    """Flushed per row, not per batch: a crash costs the rows still in flight and nothing that was
    already written. A buffered writer would lose a whole batch of results the platform will not
    repeat for free.

    IT READS THE FILE FROM INSIDE THE RUN, and that is the only version of this test that works.
    Written first as "raise, then read the file afterwards", which PASSED WITH THE FLUSH REMOVED:
    the `with open(...)` block flushes on the way out of the exception, so unwinding hides exactly
    the buffering the test exists to catch. A real crash (`os._exit`, SIGKILL, a VPS reboot) does
    not unwind. Reading mid-run reproduces that, and the mutation now fails as it should.
    """
    fake = FakePlatform(crash_at_post=3)
    monkeypatch.setattr(LS, "load_pools", lambda: ({}, {}, {}))
    # `run` now hands `draw` the factorial cell machinery (assigner / pool_c_kept / gate_pool),
    # so a fake that does not absorb keywords fails for a reason unrelated to what is under test.
    monkeypatch.setattr(LS, "draw", lambda a, b, c, rng, k, **kw: synthetic(k))
    monkeypatch.setattr(LS, "session", lambda: fake)
    out_path = tmp_path / "crash.jsonl"

    seen, real_post = {}, fake.post

    def post(url, json=None, timeout=None):   # `json` is the platform's kwarg name, so the lines
        if len(fake.posts) == 2:              # are read here and parsed outside, where the module
            seen["lines"] = out_path.read_text().splitlines()   # of that name is still visible
        return real_post(url, json=json, timeout=timeout)
    monkeypatch.setattr(fake, "post", post)

    with pytest.raises(RuntimeError, match="died mid-batch"):
        LS.run(50, seed=1, out_path=out_path, live=True, concurrency=1, children=10,
               out=lambda *a: None)

    rows = [json.loads(x) for x in seen["lines"]]
    kids = children_rows(rows)
    assert len(kids) == 20, "the two drained parents were not on disk when the process died"
    assert len({r["formula"] for r in kids}) == 20
    assert all(r["alpha"] == fake.alpha_of_formula[r["formula"]] for r in kids)
    assert kids[-1]["checks"], "the last row on disk is whole, not a half-written line"
    # And the handles for the earlier parents' simulations are recoverable rather than orphaned.
    assert len([r for r in rows if r["status"] == "PARENT-POSTED"]) == 2


# ------------------------------------------------------------------ it still cannot submit

def test_the_multisim_path_contains_no_submit(monkeypatch, tmp_path):
    """A simulation is repeatable; a submission is one irreversible POST and a 403 spends it
    forever. Checked on the live call sequence, not only on the AST."""
    fake = FakePlatform()
    drive(monkeypatch, tmp_path, fake, 20, concurrency=8, children=10)
    assert not [p for p in fake.posts if "submit" in json.dumps(p).lower()]


def test_a_cancelled_child_is_terminal_not_polled_forever():
    """2026-09-06: the platform CANCELLED the tail of an erroring parent; poll() must return at once."""
    class _S:
        def __init__(self): self.n = 0
        def get(self, url, timeout=None):
            self.n += 1
            return FakeResp(200, {"status": "CANCELLED"})
    s = _S()
    st, alpha, polls, _ = LS.poll(s, "https://x/simulations/c1", sleep=lambda _: None, wait_first=False)
    assert (st, alpha, polls, s.n) == ("CANCELLED", None, 1, 1)


def test_poll_returns_at_the_round_deadline_naming_the_unknown_status():
    class _S:
        def get(self, url, timeout=None):
            return FakeResp(200, {"status": "SOMETHING_NEW"})
    st, alpha, polls, msg = LS.poll(_S(), "https://x/simulations/c2", sleep=lambda _: None, wait_first=False,
                                    deadline=time.time() - 1)
    assert (st, alpha, polls) == ("POLL-DEADLINE", None, 1) and "SOMETHING_NEW" in msg
    pst, kids, ppolls, pmsg = LS.poll_parent(_S(), "https://x/simulations/p2", sleep=lambda _: None, wait_first=False,
                                             deadline=time.time() - 1)
    assert (pst, kids, ppolls) == ("POLL-DEADLINE", [], 1) and "SOMETHING_NEW" in pmsg


def test_post_patient_retries_a_transient_error_then_returns():
    calls = []
    class _S:
        def post(self, url, json=None, timeout=None):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("TLS/SSL connection has been closed")
            return FakeResp(201, {"id": "x"})
    r = LS._post_patient(_S(), "https://x/simulations", {"a": 1}, sleep=lambda _: None)
    assert r.status_code == 201 and len(calls) == 3
    class _Dead:
        def post(self, url, json=None, timeout=None):
            raise ConnectionError("down")
    try:
        LS._post_patient(_Dead(), "https://x/simulations", {}, sleep=lambda _: None)
        assert False, "should raise after the last try"
    except ConnectionError:
        pass
