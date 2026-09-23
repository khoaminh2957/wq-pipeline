import json

from forge import probe as P


class _Resp:
    def __init__(self, code=200, text="", headers=None):
        self.status_code, self.text, self.headers = code, text, headers or {}

    def json(self):
        return json.loads(self.text)


class _Session:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, timeout=30):
        self.calls.append(url)
        aid, kind = url.rsplit("/", 3)[1], url.rsplit("/", 1)[1]
        return self.answers.get((aid, kind), _Resp(200, ""))


def test_read_variants():
    s = _Session({("A", "prod"): _Resp(200, json.dumps({"max": 0.61, "records": []})),
                  ("A", "self"): _Resp(200, ""),
                  ("B", "prod"): _Resp(429, "", {"Retry-After": "7"}),
                  ("B", "self"): _Resp(200, "not json")})
    assert P.read(s, "A", "prod") == (0.61, "ok")
    # an empty 200 means the platform QUEUED the calculation; `read` retries before reporting it,
    # and the reason names how long it waited instead of asserting a state of the alpha
    v, why = P.read(s, "A", "self", sleep=lambda _: None)
    assert v is None and why.startswith("200-empty after 5 tries")
    # `read` waits out a 429 before giving up, so this one spends its retries first
    assert P.read(s, "B", "prod", sleep=lambda _: None) == (None, "http:429 Retry-After=7")
    assert P.read(s, "B", "self")[1].startswith("200-unparseable")


def test_an_empty_200_is_retried_and_the_value_is_taken_when_it_arrives():
    """MEASURED 2026-09-23: rK5RGeqa answered empty on two consecutive submit rounds and was skipped;
    calling again returned prod 0.6524, under the line. The endpoint is asynchronous -- the first GET
    starts the calculation. Giving up on the first empty body cost a submittable alpha."""
    class _Async:
        """Empty until the Nth call, then the payload -- the platform's own shape."""

        def __init__(self, empties, value):
            self.n, self.empties, self.value = 0, empties, value

        def get(self, url, timeout=None):
            self.n += 1
            return _Resp(200, "" if self.n <= self.empties else json.dumps({"max": self.value}))

    s = _Async(empties=2, value=0.6524)
    assert P.read(s, "rK5RGeqa", "prod", sleep=lambda _: None) == (0.6524, "ok")
    assert s.n == 3                                     # two empties, then the answer

    # and it still gives up rather than looping for ever
    forever = _Async(empties=99, value=0.1)
    v, why = P.read(forever, "X", "prod", sleep=lambda _: None)
    assert v is None and why.startswith("200-empty after 5 tries")
    assert forever.n == 5


def test_pending_and_sweep_do_not_retrigger_stored_values(tmp_path):
    scored = {"A": {"alpha": "A", "stage": "candidate", "score": 0.7},
              "B": {"alpha": "B", "stage": "candidate", "score": 0.9},
              "C": {"alpha": "C", "stage": "dsr-fail", "score": 0.95},
              "D": {"alpha": "D", "stage": "candidate", "score": 0.5}}
    corr_file = tmp_path / "corr.jsonl"
    corr_file.write_text(json.dumps({"alpha": "D", "prod": 0.5, "self": "200-empty", "read_at": 1}) + "\n"
                         + json.dumps({"alpha": "D", "prod": "http:429", "self": 0.2, "read_at": 2}) + "\n")
    corr = P.load_corr(corr_file)
    assert corr["D"] == {"prod": 0.5, "self": 0.2, "read_at": 2}      # values merge across readings
    todo = [x["alpha"] for x in P.pending(scored, corr)]
    assert todo == ["B", "A"]                                           # D complete, C not a candidate
    s = _Session({("B", "prod"): _Resp(200, json.dumps({"max": 0.55})), ("A", "self"): _Resp(200, json.dumps({"max": 0.3}))})
    corr["A"] = {"prod": 0.66}
    rows = P.sweep(s, ["A", "B"], corr, sleep=lambda _: None)
    by = {r["alpha"]: r for r in rows}
    assert by["A"]["prod"] == 0.66 and by["A"]["self"] == 0.3         # stored prod not re-requested
    assert by["B"]["prod"] == 0.55 and str(by["B"]["self"]).startswith("200-empty after")
    assert not any(u.endswith("/A/correlations/prod") for u in s.calls)


def test_append_corr_supersedes_the_stored_reading(tmp_path):
    f = tmp_path / "corr.jsonl"
    P.append_corr([{"alpha": "A", "prod": 0.5, "self": 0.3, "read_at": 1}], path=f)
    P.append_corr([{"alpha": "A", "prod": 0.9668, "self": 0.9668, "read_at": 2, "source": "submit-reread"}], path=f)
    assert P.load_corr(f)["A"] == {"prod": 0.9668, "self": 0.9668, "read_at": 2}



# ---- the shared 60/min bucket and the 4 h session (both measured 2026-09-21) -------------------

class _Scripted:
    """A session that answers a fixed sequence, so a retry can be observed."""

    def __init__(self, seq):
        self.seq, self.calls = list(seq), 0

    def get(self, url, timeout=30):
        self.calls += 1
        return self.seq.pop(0) if self.seq else _Resp(200, json.dumps({"max": 0.5}))


def test_a_429_is_waited_out_and_retried():
    """MEASURED 2026-09-21: a 109-alpha batch drew 243 429s and landed 0 of 109, while a 27-alpha
    batch an hour earlier landed 17 of 27. The difference was only LENGTH -- the forge loop polls
    simulations from the same 60/min bucket, so a probe pacing at 1.1 s (~55/min) overflows it
    whenever the loop runs. A 429 is the bucket asking us to wait, never a verdict on the alpha."""
    slept = []
    s = _Scripted([_Resp(429, "", {"Retry-After": "3"}), _Resp(200, json.dumps({"max": 0.61}))])
    assert P.read(s, "A", "prod", sleep=slept.append) == (0.61, "ok")
    assert slept == [4.0] and s.calls == 2


def test_a_429_that_never_clears_gives_up_after_its_tries():
    s = _Scripted([_Resp(429, "", {"Retry-After": "1"})] * 5)
    v, why = P.read(s, "A", "prod", sleep=lambda _: None, tries=3)
    assert v is None and why.startswith("http:429") and s.calls == 3


def test_a_missing_retry_after_header_still_backs_off():
    slept = []
    s = _Scripted([_Resp(429, "", {}), _Resp(200, json.dumps({"max": 0.4}))])
    assert P.read(s, "A", "prod", sleep=slept.append)[0] == 0.4
    assert slept == [6.0]          # the 5 s default plus the 1 s margin


def test_the_sweep_stops_on_the_first_401_instead_of_burning_the_batch():
    """The session is 4 h and non-renewable, so once it expires every further call 401s too.
    Carrying on wrote 193 reason strings in one run, each of which a later reader then has to tell
    apart from a real answer."""
    said = []
    s = _Scripted([_Resp(401, "", {})] * 6)
    rows = P.sweep(s, ["a1", "a2", "a3"], {}, sleep=lambda _: None, out=said.append)
    assert len(rows) == 1 and str(rows[0]["prod"]).startswith("http:401")
    assert "auth dead" in said[0]


def test_a_reason_string_is_never_loaded_back_as_a_value(tmp_path):
    """So a rate-limited or auth-dead alpha stays PENDING and is read again later, instead of being
    recorded as measured-and-failed -- the [[transient-read-as-truth]] class."""
    p = tmp_path / "corr.jsonl"
    p.write_text(json.dumps({"alpha": "a1", "prod": "http:429 ...", "self": "200-empty (computing)"}) + "\n"
                 + json.dumps({"alpha": "a2", "prod": 0.5, "self": 0.3}) + "\n")
    got = P.load_corr(p)
    assert "prod" not in got["a1"] and "self" not in got["a1"]
    assert got["a2"]["prod"] == 0.5 and got["a2"]["self"] == 0.3
