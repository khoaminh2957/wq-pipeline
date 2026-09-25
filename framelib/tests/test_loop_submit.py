"""framelib.loop.submit on a FAKE TRANSPORT only: every hold path, the budget, the novelty registration, and that
nothing POSTs without --submit.

No test here can reach the platform. The session factory (layered_sim), the POST (climb_submit.post), the shared
budget (submit_budget) and the notifier (msgcat) are fake modules in sys.modules; the correlation and PnL reads run
the REAL forge.probe.read and self_corr_predict.pnl against a fake session whose post() raises. The repo-root
conftest also refuses any real HTTP POST for the whole pytest process."""
import fcntl
import itertools
import json
import random
import sys
import time
import types

import pytest

from forge import meaning as M, submit as SUB
from framelib.experiments import analyse_round as AR
from framelib.loop import submit as FS
import self_corr_predict as SCP

REAL_MEANING_GATE = SUB.meaning_gate
_SUBMIT = "--" + "submit"          # built, never written whole (tools/ci_gate.py's no-live scan convention)

GST = {"region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "INDUSTRY", "decay": 4, "truncation": 0.08}
# formulas with pairwise DISJOINT fields (so forge.novelty never calls two of them twins) and their dataset sets
F1 = "group_rank(ts_rank(operating_income / equity, 252), subindustry)"          # fundamental6
F2 = "rank(ts_mean(snt1_d1_nettargetpercent, 20))"                                # sentiment1
F3 = "ts_zscore(news_sentiment_score, 60)"                                        # news12
F4 = "rank(ts_delta(anl4_eps_mean, 5))"                                           # analyst4
F5 = "group_rank(ts_mean(close / volume, 10), industry)"                          # pv1
F6 = "rank(ts_delta(assets / liabilities, 20))"                                   # fundamental6
F_UNKNOWN = "ts_rank(field_not_in_the_catalogue, 20)"
IV_SUBMITTED = ("multiply(group_rank(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 5), sector), "
                "(1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 5), sector)))")
IV_VARIANT = ("multiply(group_rank(ts_mean(implied_volatility_call_90 - implied_volatility_put_90, 20), industry), "
              "(1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 10), industry)))")
# vRk1J2jd's formula; with the synthetic catalogue below the real forge.meaning.score reads G4-G8 true when one
# leg is uncrowded and G4 false when every leg is crowded (forge/tests/test_submit.py's case)
VR = ("multiply((1 - group_rank(ts_rank(ts_backfill(diff_current_vs_hist_price_ratio_earnings, 21), 252), industry)), "
      "group_rank(ts_backfill(operating_income / assets, 126), industry))")
VR_LABELS = {
    "diff_current_vs_hist_price_ratio_earnings": {"domain": "valuation", "kind": "ratio", "unit": "ratio", "sign": "-", "sign_source": "description", "time": "annual", "sparsity": "dense", "structure": "MATRIX"},
    "operating_income": {"domain": "profitability", "kind": "level", "unit": "currency", "sign": "+", "sign_source": "domain-prior", "time": "quarterly", "sparsity": "medium", "structure": "MATRIX"},
    "assets": {"domain": "size", "kind": "level", "unit": "currency", "sign": "unstated", "sign_source": "unstated", "time": "quarterly", "sparsity": "medium", "structure": "MATRIX"}}
UNCROWDED = {"diff_current_vs_hist_price_ratio_earnings": 2, "operating_income": 67731, "assets": 169009}
CROWDED = dict(UNCROWDED, diff_current_vs_hist_price_ratio_earnings=500)
LEDGERS = {"journal": {}, "posts": [], "post_rows": {}, "nogo": [], "nogo_source": "test",
           "composites": {"verdicts": {}, "index": []}}
FIELD_DS = {"operating_income": "fundamental6", "equity": "fundamental6", "assets": "fundamental6",
            "liabilities": "fundamental6", "snt1_d1_nettargetpercent": "sentiment1", "news_sentiment_score": "news12",
            "anl4_eps_mean": "analyst4", "close": "pv1", "volume": "pv1",
            "implied_volatility_call_30": "option8", "implied_volatility_put_30": "option8",
            "implied_volatility_call_90": "option8", "implied_volatility_put_90": "option8",
            "executed_short_trade_share_count": "us_short_sale", "aggregate_executed_trade_share_count": "us_short_sale",
            "diff_current_vs_hist_price_ratio_earnings": "model16"}
DAYS = ["d%04d" % i for i in range(1000)]           # the predictor needs >= 900 shared days


def _catalogue(counts):
    """A stand-in for forge.meaning.load_catalogue(region, universe, delay, only=...)."""
    return lambda region, universe, delay, only=None: {
        "region": region, "universe": universe, "delay": int(delay), "labels": VR_LABELS, "source": "test",
        "fields": {f: {"alphaCount": c, "type": "MATRIX"} for f, c in counts.items()}}


def _daily(seed):
    rnd = random.Random(seed)
    return [rnd.gauss(0, 1) for _ in DAYS]


def _cum(xs):
    return dict(zip(DAYS, itertools.accumulate(xs)))


def _twin(daily):
    rnd = random.Random(1)
    return [x + rnd.gauss(0, 0.1) for x in daily]


class _Resp:
    def __init__(self, code, text="", headers=None):
        self.status_code, self.text, self.headers = code, text, headers or {}

    def json(self):
        return json.loads(self.text)


class _Session:
    """GET only: /alphas/<a>/correlations/<kind> and /alphas/<a>/recordsets/pnl from the env's tables."""
    def __init__(self, env):
        self.env = env

    def get(self, url, timeout=None):
        self.env.gets.append(url)
        a, rest = url.split("/alphas/")[1].split("/", 1)
        if rest.startswith("correlations/"):
            v = (self.env.corr.get(a) or {}).get(rest.split("/")[1], 0.3)
            if v is None:
                return _Resp(500)
            if v == "":
                return _Resp(200, "")
            return _Resp(200, json.dumps({"max": v, "records": []}))
        if rest == "recordsets/pnl":
            c = self.env.curves.get(a)
            if c is None:
                return _Resp(404)
            return _Resp(200, json.dumps({"schema": {"properties": [{"name": "date"}, {"name": "pnl"}]},
                                          "records": [[d, v] for d, v in sorted(c.items())]}))
        raise AssertionError("unexpected GET %s" % url)

    def post(self, *a, **k):
        raise AssertionError("the session never POSTs here; climb_submit.post is the transport")


class _Env:
    def __init__(self, tmp, monkeypatch):
        self.tmp, self.mp = tmp, monkeypatch
        self.rows, self.corr, self.curves, self.http = [], {}, {}, {}
        self.transport, self.sends, self.gets, self.budget_calls = [], [], [], 0
        self.sessions = 0
        self.budget = {"remaining": 4, "why": "fake budget"}
        self.journal = tmp / "frames_loop.jsonl"
        self.post_log = tmp / "forge_submitted.jsonl"
        self.climb_log = tmp / "climb_submitted.jsonl"
        self.corr_path = tmp / "corr.jsonl"
        self.cached = tmp / "pnl_curves"
        self.cached.mkdir()
        fields = tmp / "fields"
        fields.mkdir()
        with open(fields / "USA_TOP3000_d1.jsonl", "w") as fh:
            for f, ds in FIELD_DS.items():
                fh.write(json.dumps({"id": f, "type": "MATRIX", "dataset": {"id": ds, "name": ds}}) + "\n")
            for g in ("sector", "industry", "subindustry"):
                fh.write(json.dumps({"id": g, "type": "GROUP", "dataset": {"id": "pv13"}}) + "\n")
        for name, val in (("LOOP_JOURNAL", self.journal), ("POST_LOG", self.post_log), ("CLIMB_LOG", self.climb_log),
                          ("CORR", self.corr_path), ("CURVES", self.cached), ("FIELDS_DIR", fields),
                          ("PAIR_COUNTS", tmp / "pyramid_cell_counts.json"), ("SLEEP", lambda s: None)):
            monkeypatch.setattr(FS, name, val)
        monkeypatch.setattr(SUB, "SUBMIT_LOCK", str(tmp / "wq_submit.lock"))
        monkeypatch.setattr(FS.P, "PACE_S", 0)
        monkeypatch.setattr(SCP, "CACHE", tmp / "pnl_fetched")
        monkeypatch.setattr(M, "LEDGER", tmp / "meaning.jsonl")
        monkeypatch.setattr(SUB, "meaning_gate", lambda *a, **k: (lambda alpha, row: None))
        env = self

        def session():
            env.sessions += 1
            return _Session(env)

        def remaining_today(session=None):
            env.budget_calls += 1
            if isinstance(env.budget, Exception):
                raise env.budget
            return env.budget

        def post(alpha, session=None):
            assert isinstance(session, _Session)
            env.transport.append(alpha)
            code = env.http.get(alpha, 201)
            return code, ("EXCEPTION Timeout -- OUTCOME UNKNOWN" if code is None else "{}")
        self.sb = self._fake("submit_budget", LEDGER=tmp / "submit_budget.jsonl", platform_date=lambda: "2026-09-24",
                             remaining_today=remaining_today)
        self._fake("layered_sim", session=session)
        self._fake("climb_submit", post=post)
        self._fake("msgcat", send=lambda msg: env.sends.append(msg),
                   m6_post_outcome=lambda alpha, http, t, exc_class=None: {"alpha": alpha, "http": http})

    def _fake(self, name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        self.mp.setitem(sys.modules, name, mod)
        return mod

    def add(self, alpha, formula, fail=None, experiment="FRAMES-LOOP", status="WARNING", pyramid=True,
            pyramids=("USA/D1/FUNDAMENTAL",), prod_limit=None, self_limit=0.7, frame="Fx", curve=True):
        ck = [{"name": n, "result": "FAIL" if n == fail else "PASS", "limit": 1.0, "value": 2.0} for n in AR.BINDING]
        ck += [{"name": "MATCHES_PYRAMID", "result": "PASS" if pyramid else "FAIL",
                "pyramids": [{"name": p, "multiplier": 1.2} for p in pyramids]},
               {"name": "PROD_CORRELATION", "result": "PENDING", "limit": prod_limit},
               {"name": "SELF_CORRELATION", "result": "PENDING", "limit": self_limit}]
        meta = {"experiment": experiment, "frame_version": 1, "fill": [], "route": "screen", "round_seed": 7,
                "plan_day": "2026-09-24"}
        if frame:
            meta["frame_id"] = frame
        self.rows.append({"status": status, "alpha": alpha, "formula": formula, "settings": dict(GST), "meta": meta,
                          "sharpe": 2.0, "fitness": 1.2, "turnover": 0.1, "checks": ck})
        if curve:
            self.curves[alpha] = _cum(_daily(alpha))

    def history(self, alpha, http, formula=None, key=None, age_s=0.0, path=None):
        with open(path or self.post_log, "a") as fh:
            fh.write(json.dumps({"alpha": alpha, "formula": formula, "mechanism_key": key, "http": http,
                                 "posted_at": time.time() - age_s, "source": "forge"}) + "\n")

    def run(self, submit=True, cap=4):
        self.transport.clear()
        with open(self.journal, "w") as fh:
            for r in self.rows:
                fh.write(json.dumps(r) + "\n")
        return FS.main(str(self.journal), submit=submit, cap=cap)

    def ledger_rows(self):
        p = self.sb.LEDGER
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def env(tmp_path, monkeypatch):
    return _Env(tmp_path, monkeypatch)


# --------------------------------------------------------------------------- --submit is the only path that POSTs
def test_nothing_posts_without_submit_and_the_dry_run_opens_no_session(env, capsys):
    env.add("A", F1)
    assert env.run(submit=False) == []
    out = capsys.readouterr().out
    assert "would POST" in out and "['A']" in out and "nothing posted" in out
    assert env.transport == [] and env.sessions == 0 and env.gets == [] and env.budget_calls == 0
    assert env.ledger_rows() == [] and not env.post_log.exists()
    assert FS.cli(["--journal", str(env.journal)]) == 0 and env.transport == []
    with pytest.raises(SystemExit):                     # allow_abbrev=False: `--sub` is not `--submit`
        FS.cli(["--journal", str(env.journal), "--sub"])
    assert env.transport == []
    assert env.run(submit=True) == ["A"] == env.transport          # control: A was POSTable all along
    env.transport.clear()
    assert FS.cli(["--journal", str(env.journal), _SUBMIT]) == 0   # the flag itself; A is now already POSTed
    assert env.transport == []


# --------------------------------------------------------------------------- candidates
def test_only_frames_loop_rows_at_d24_are_candidates(env):
    env.add("A", F1)
    env.add("B", F2, fail="IS_LADDER_SHARPE")                      # 6 of 7 binding checks
    env.add("C", F3, experiment="FRAMES-R1B")                      # an experiment round (F3: no submit step)
    env.add("D", F4, frame=None)                                   # stamped FRAMES-LOOP but no frame id
    env.add("E", F5, status="ERROR")                               # not scored
    assert env.run() == ["A"]


# --------------------------------------------------------------------------- local gates
def test_an_alpha_posted_or_reserved_before_and_a_pyramid_fail_are_held(env, capsys):
    env.add("A", F1)
    env.add("B", F2)
    env.add("C", F3, pyramid=False)
    env.add("D", F4)
    env.history("A", 403)                                          # refused: its one lifetime POST is spent
    with open(env.sb.LEDGER, "w") as fh:                           # B: a reservation with no logged outcome
        fh.write(json.dumps({"date": "2026-09-23", "alpha": "B", "stage": "reserved", "reserved_at": time.time()}) + "\n")
    assert env.run() == ["D"]
    out = capsys.readouterr().out
    assert "'already-posted': 2" in out and "'pyramid-not-pass': 1" in out


def test_q20_diversity_holds_a_third_post_of_a_dataset_set_and_a_second_repeat_inside_the_run(env, capsys):
    env.history("H1", 201, formula="rank(hist_one)", key="h#option8|us_short_sale#USA/d1")
    env.history("H2", 201, formula="rank(ts_mean(hist_two, 5))", key="h#option8|us_short_sale#USA/d1")
    env.add("A", IV_SUBMITTED)                                     # option8|us_short_sale: 2 today already
    env.add("B", F1)                                               # fundamental6: none today -> POSTed
    env.add("C", F6)                                               # fundamental6: one after B, and a set repeats
    env.add("D", F_UNKNOWN)                                        # its field is not in the catalogue
    assert env.run() == ["B"]
    out = capsys.readouterr().out
    assert "'dataset-set-repeated-today': 1" in out and "'dataset-set-unreadable': 1" in out
    rec = json.loads(env.post_log.read_text().splitlines()[-1])
    assert rec["alpha"] == "B" and rec["datasets"] == "fundamental6" and rec["mechanism_key"] == "frames:Fx#fundamental6#USA/d1"


def test_the_dataset_set_leaves_group_fields_out_and_reads_none_without_a_dataset_id():
    cat = {"close": {"type": "MATRIX", "dataset": {"id": "pv1"}}, "country": {"type": "GROUP", "dataset": {"id": "pv13"}},
           "anl4_eps_mean": {"type": "MATRIX", "dataset": {"id": "analyst4"}}, "orphan": {"type": "MATRIX", "dataset": {}}}
    assert FS.dataset_set("group_rank(ts_delta(anl4_eps_mean, 5) / close, country)", cat) == "analyst4|pv1"
    assert FS.dataset_set("rank(orphan)", cat) is None


def test_d18_holds_a_structural_twin_of_a_post_and_an_incomplete_index_holds_every_candidate(env, capsys):
    env.history("H", 201, formula=IV_SUBMITTED, age_s=10 * 86400)
    env.add("A", IV_VARIANT)
    env.add("B", F1)
    assert env.run() == ["B"]
    assert "'structure-already-submitted': 1" in capsys.readouterr().out
    env.history("H2", 201, formula=None, age_s=10 * 86400)         # an accepted POST whose structure is unreadable
    env.add("C", F2)
    assert env.run() == []
    assert "'novelty-index-incomplete'" in capsys.readouterr().out
    assert env.sessions == 1                                       # nothing eligible: no session was opened


def test_a_candidate_whose_structure_the_index_cannot_read_is_held(env):
    env.add("A", F1)
    unreadable = types.SimpleNamespace(complete=True, verdict=lambda formula: (None, 0.0, None))
    cell = ("USA", "TOP3000", 1)
    cats = {cell: FS.field_rows(cell, ["operating_income", "equity"])}
    assert FS.eligible({"A": env.rows[0]}, [], unreadable, lambda a, r: None, cats, {}, {}) == (
        [], {"novelty-candidate-unreadable": 1})


def test_d18_registers_each_accepted_post_and_drops_its_queued_twin(env, capsys):
    env.add("A", IV_SUBMITTED)
    env.add("B", IV_VARIANT)                                       # a twin of A; neither was ever POSTed
    env.add("C", F1)
    assert env.run() == ["A", "C"]
    # the next invocation reads the POST from the log it was recorded in: A already POSTed, B its twin
    assert env.run() == []
    out = capsys.readouterr().out
    assert "'already-posted': 2" in out and "'structure-already-submitted': 1" in out


def test_meaning_scores_with_the_real_scorer_records_the_row_and_posts_only_on_all_true(env, monkeypatch, capsys):
    monkeypatch.setattr(SUB, "meaning_gate", REAL_MEANING_GATE)
    monkeypatch.setattr(M, "load_ledgers", lambda: LEDGERS)
    monkeypatch.setattr(M, "load_catalogue", _catalogue(CROWDED))
    env.add("G", VR)
    assert env.run() == []
    assert "'meaning:G4=false': 1" in capsys.readouterr().out
    rows = [json.loads(x) for x in (env.tmp / "meaning.jsonl").read_text().splitlines()]
    assert [(r["alpha"], r["gates"]["G4"]) for r in rows] == [("G", False)]
    env.add("H", VR)                                               # a fresh alpha, one uncrowded leg
    monkeypatch.setattr(M, "load_catalogue", _catalogue(UNCROWDED))
    assert env.run() == ["H"]
    # G now scores all-true, but its RECORDED row (the earliest, the one the judge grades) reads G4 false
    assert "'meaning-recorded:G4=false': 1" in capsys.readouterr().out
    rows = [json.loads(x) for x in (env.tmp / "meaning.jsonl").read_text().splitlines()]
    assert [r["alpha"] for r in rows] == ["G", "H"] and all(v is True for k, v in rows[1]["gates"].items() if k in M.DECIDABLE)


def test_meaning_scoring_that_raises_holds(env, monkeypatch, capsys):
    monkeypatch.setattr(SUB, "meaning_gate", REAL_MEANING_GATE)
    monkeypatch.setattr(M, "load_ledgers", lambda: LEDGERS)

    def boom(*a, **k):
        raise RuntimeError("catalogue unreadable")
    monkeypatch.setattr(M, "load_catalogue", boom)
    env.add("G", VR)
    assert env.run() == []
    assert "'meaning-error:RuntimeError': 1" in capsys.readouterr().out


# --------------------------------------------------------------------------- 403 budget, shared budget, lock
def test_more_than_one_403_in_seven_days_holds_everything(env, capsys):
    env.add("A", F1)
    env.history("X1", 403, age_s=2 * 86400)
    assert env.run() == ["A"]                                      # one refusal is inside the budget
    env.rows.clear()
    env.add("B", F2)
    env.history("X2", 403, age_s=86400)
    assert env.run() == []
    assert "HOLD-FOR-APPROVAL" in capsys.readouterr().out and env.budget_calls == 1


def test_shared_budget_zero_unreadable_and_cap(env, capsys):
    env.add("A", F1)
    env.add("B", F2)
    env.budget = {"remaining": 0, "why": "4/4 used"}
    assert env.run() == []
    assert "no submit slot left today" in capsys.readouterr().out
    env.budget = RuntimeError("feed down")
    assert env.run() == []
    assert "REFUSING TO POST: shared submit budget unreadable" in capsys.readouterr().out
    env.budget = {"remaining": 4, "why": "fake"}
    assert env.run(cap=1) == ["A"]
    rows = env.ledger_rows()
    assert len(rows) == 1 and {k: rows[0][k] for k in ("date", "alpha", "source", "stage")} == {
        "date": "2026-09-24", "alpha": "A", "source": "frames_loop_submit", "stage": "reserved"}


def test_the_remaining_budget_binds_and_every_post_reserves_its_slot_first(env):
    env.add("A", F1)
    env.add("B", F2)
    env.add("C", F3)
    env.budget = {"remaining": 2, "why": "2/4 used"}
    assert env.run() == ["A", "B"]
    assert [(r["alpha"], r["stage"]) for r in env.ledger_rows()] == [("A", "reserved"), ("B", "reserved")]


def test_an_unwritable_ledger_refuses_to_post(env, capsys):
    env.add("A", F1)
    (env.tmp / "not_a_dir").write_text("x")
    env.sb.LEDGER = env.tmp / "not_a_dir" / "submit_budget.jsonl"
    assert env.run() == [] and env.transport == []
    assert "could not reserve a slot" in capsys.readouterr().out


def test_another_submitter_holding_the_lock_blocks_the_post_and_the_budget_read(env, capsys):
    env.add("A", F1)
    with open(SUB.SUBMIT_LOCK, "a+") as other:
        fcntl.flock(other.fileno(), fcntl.LOCK_EX)
        assert env.run() == []
    assert "another submitter holds" in capsys.readouterr().out
    assert env.transport == [] and env.budget_calls == 0
    assert env.run() == ["A"]                                      # the lock released: control


# --------------------------------------------------------------------------- the fresh correlation reading
def test_the_fresh_reading_decides_under_the_rows_own_lines(env, capsys):
    with open(env.corr_path, "w") as fh:                           # the stored readings say the OPPOSITE of fresh
        for a, v in (("A", 0.3), ("B", 0.3), ("C", 0.3), ("D", 0.3), ("E", 0.3), ("F", 0.9), ("G", 0.3)):
            fh.write(json.dumps({"alpha": a, "prod": v, "self": v, "read_at": time.time()}) + "\n")
    env.add("A", F1)
    env.corr["A"] = {"prod": 0.75, "self": 0.2}                   # over the PROD line
    env.add("B", F2)
    env.corr["B"] = {"prod": 0.2, "self": 0.71}                   # over the SELF line
    env.add("C", F3)
    env.corr["C"] = {"prod": None, "self": 0.2}                   # HTTP 500
    env.add("D", F4, prod_limit=0.65)
    env.corr["D"] = {"prod": 0.68, "self": 0.2}                   # under 0.7, over the row's own 0.65
    env.add("G", IV_SUBMITTED)
    env.corr["G"] = {"prod": "", "self": 0.2}                     # 200 with an empty body, five times
    env.add("E", F5)
    env.corr["E"] = {"prod": 0.5, "self": 0.4}
    env.add("F", F6)
    env.corr["F"] = {"prod": 0.2, "self": 0.2}                    # stored 0.9, fresh 0.2
    assert env.run() == ["E", "F"]
    out = capsys.readouterr().out
    assert "'corr-over-line': 3" in out and "'corr-fresh-unread': 2" in out
    fresh = [json.loads(x) for x in env.corr_path.read_text().splitlines() if "frames-submit-reread" in x]
    assert sorted(r["alpha"] for r in fresh) == ["A", "B", "D", "E", "F"]
    rec = {json.loads(x)["alpha"]: json.loads(x) for x in env.post_log.read_text().splitlines()}
    assert (rec["E"]["prod_corr"], rec["E"]["self_corr"]) == (0.5, 0.4)


def test_each_platform_read_is_paced_as_the_probe_paces(env, monkeypatch):
    waits = []
    monkeypatch.setattr(FS, "SLEEP", waits.append)
    monkeypatch.setattr(FS.P, "PACE_S", 1.1)
    env.add("A", F1)
    assert env.run() == ["A"]
    assert waits == [1.1, 1.1]                                     # prod, then self


# --------------------------------------------------------------------------- S11
def test_s11_holds_a_predicted_pnl_twin_and_anything_it_cannot_read(env, capsys):
    a = _daily("A")
    env.add("A", F1)
    with open(env.cached / "A.json", "w") as fh:                   # A's curve cached; the others fetched by GET
        json.dump(_cum(a), fh)
    del env.curves["A"]
    env.add("B", F2)
    env.curves["B"] = _cum(_twin(a))                               # A's PnL twin
    env.add("C", F3, curve=False)                                  # GET answers 404
    env.add("D", F4)
    env.curves["D"] = dict.fromkeys(DAYS, 0.0)                     # frozen: the predictor refuses it
    env.add("E", F5)
    assert env.run() == ["A", "E"]
    out = capsys.readouterr().out
    assert "'s11-pnl-twin': 1" in out and "'s11-curve-absent': 1" in out and "'s11-unpredictable': 1" in out
    assert (SCP.CACHE / "E.json").exists()                         # a fetched curve is cached for the next reader


def test_s11_at_the_line_holds_and_no_posted_curve_means_one_post(env, capsys):
    a = _daily("A")
    twin = _twin(a)
    v = SCP.predict(_cum(twin), _cum(a))[0]
    assert v >= 0.99
    env.add("A", F1)
    env.curves["A"] = _cum(a)
    env.add("B", F2, self_limit=v)                                 # predicted exactly AT its SELF line
    env.curves["B"] = _cum(twin)
    env.corr["B"] = {"prod": 0.2, "self": 0.2}
    assert env.run() == ["A"]
    assert "'s11-pnl-twin': 1" in capsys.readouterr().out
    env.rows.clear()
    env.add("P", F3, curve=False)                                  # the POSTed alpha's own curve is unreadable
    env.add("Q", F4)
    assert env.run() == ["P"]
    assert "'s11-curve-absent': 1" in capsys.readouterr().out


def test_s11_a_predictor_that_raises_holds_every_remaining_pick(env, monkeypatch, capsys):
    env.add("A", F1)
    env.add("B", F2)
    env.add("C", F3)

    def bad(*a):
        raise ValueError("bad curve")
    monkeypatch.setattr(SCP, "predict", bad)
    assert env.run() == ["A"]
    assert "'s11-error:ValueError': 2" in capsys.readouterr().out


# --------------------------------------------------------------------------- outcomes, record, notify, order
def test_any_answer_but_200_or_201_stops_the_run(env):
    env.add("A", F1)
    env.add("B", F2)
    env.http["A"] = 403
    assert env.run() == ["A"]
    env.rows.clear()
    env.add("C", F3)
    env.add("D", F4)
    env.http["C"] = None
    assert env.run() == ["C"]
    env.rows.clear()
    env.add("E", F5)
    env.add("F", F6)
    env.http["E"] = 429                                            # neither accepted nor a refusal: stops too
    assert env.run() == ["E"]
    assert [json.loads(x)["http"] for x in env.post_log.read_text().splitlines()] == [403, None, 429]
    assert [r["alpha"] for r in env.ledger_rows()] == ["A", "C", "E"]   # each kept its reserved slot


def test_no_pnl_curve_is_read_once_no_further_post_is_possible(env):
    env.add("A", F1)
    assert env.run() == ["A"]                                      # nothing left in the queue
    env.rows.clear()
    env.add("B", F2)
    env.add("C", F3)
    env.budget = {"remaining": 1, "why": "3/4 used"}               # a queue left, but no slot
    assert env.run() == ["B"]
    assert env.gets and not [u for u in env.gets if "recordsets/pnl" in u]


def test_a_notifier_that_raises_loses_neither_the_record_nor_the_run(env, capsys):
    env.add("A", F1)
    env.add("B", F2)

    def down(msg):
        raise ConnectionError("notifier down")
    env.mp.setattr(sys.modules["msgcat"], "send", down)
    assert env.run() == ["A", "B"]
    assert [json.loads(x)["alpha"] for x in env.post_log.read_text().splitlines()] == ["A", "B"]
    assert capsys.readouterr().out.count("NOTIFY FAILED (ConnectionError") == 2


def test_every_post_is_recorded_in_forges_log_with_forges_keys_and_announced(env, tmp_path):
    env.add("A", F1)
    assert env.run() == ["A"]
    rec = json.loads(env.post_log.read_text())
    forge_pick = {"alpha": "Z", "row": {"formula": "f", "meta": {}}, "hypothesis": "h", "mechanism_key": "h#d#USA/d1",
                  "pyramids": [], "score": 0.5, "prod": 0.1, "self": 0.1}
    SUB.record(forge_pick, 201, "", path=tmp_path / "forge_shape.jsonl")
    assert set(json.loads((tmp_path / "forge_shape.jsonl").read_text())) <= set(rec)
    assert (rec["alpha"], rec["http"], rec["formula"], rec["source"], rec["frame_id"], rec["route"]) == (
        "A", 201, F1, "frames-loop", "Fx", "screen")
    assert rec["pyramids"] == ["USA/D1/FUNDAMENTAL"] and (rec["prod_corr"], rec["self_corr"]) == (0.3, 0.3)
    hist = SUB.posted_history(paths=(env.post_log, env.climb_log))
    assert [h["alpha"] for h in hist] == ["A"] and FS.NV.build(hist, {}).verdict(F1)[0] is True
    assert env.sends == [{"alpha": "A", "http": 201}]


def monkeypatch_counts(env, counts):
    (env.tmp / "pyramid_cell_counts.json").write_text(json.dumps({"pairs": [{"region": "USA", "delay": 1, "counts": counts}]}))


def test_open_pyramid_cells_first_then_the_lower_stored_self(env):
    env.add("A", F1, pyramids=("USA/D1/FUNDAMENTAL",))
    env.add("B", F2, pyramids=("USA/D1/SENTIMENT",))
    monkeypatch_counts(env, {"Fundamental": 9, "Sentiment": 1})   # B's cell still needs 2
    env.budget = {"remaining": 1, "why": "3/4 used"}
    assert env.run() == ["B"]
    env.rows.clear()
    (env.tmp / "pyramid_cell_counts.json").unlink()               # unreadable counts: gain 0 for all
    env.add("C", F3)
    env.add("D", F4)
    with open(env.corr_path, "w") as fh:
        fh.write(json.dumps({"alpha": "C", "prod": 0.2, "self": 0.5}) + "\n")
        fh.write(json.dumps({"alpha": "D", "prod": 0.2, "self": 0.1}) + "\n")
    assert env.run() == ["D"]
