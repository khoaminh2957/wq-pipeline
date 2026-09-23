import json
import time

import pytest

from forge.llm import author as A
from forge.llm import verify as V


# ---- sign_verdict: the one check that carries a financial judgement ---------------------------

def test_sign_verdict_passes_when_the_label_file_has_no_opinion():
    assert V.sign_verdict(1, {}, "")[0] is True
    assert V.sign_verdict(-1, {"sign": "unstated", "sign_source": "unstated"}, "")[0] is True


def test_sign_verdict_passes_on_agreement():
    assert V.sign_verdict(1, {"sign": "+", "sign_source": "description"}, "")[0] is True
    assert V.sign_verdict(-1, {"sign": "-", "sign_source": "description"}, "")[0] is True


def test_sign_verdict_blocks_a_silent_contradiction_of_the_field_description():
    ok, why = V.sign_verdict(-1, {"sign": "+", "sign_source": "description"}, "", "some_field")
    assert ok is False and "DESCRIPTION" in why


def test_sign_verdict_accepts_a_contradiction_the_notes_own():
    lab = {"sign": "+", "sign_source": "description"}
    assert V.sign_verdict(-1, lab, "some_field reads higher = safer, so the leg is short", "some_field")[0] is True
    assert V.sign_verdict(-1, lab, "this overrides the label file: the description is about risk", "x")[0] is True


def test_sign_verdict_lets_a_domain_prior_be_contradicted():
    """The insider-flow prior was MEASURED wrong and removed from labels.py on 2026-09-07; a prior
    that cannot be contradicted by a better-informed leg is unfalsifiable."""
    ok, _ = V.sign_verdict(-1, {"sign": "+", "sign_source": "domain-prior"}, "", "f")
    assert ok is True


# ---- parsing the model's reply ----------------------------------------------------------------

def test_parse_extracts_both_blocks_and_ignores_commentary():
    reply = ("Sure, here you go.\n```yaml leg\nid: my_leg\nfamily: tone\n```\n"
             "and the composite:\n```yaml composite\nid: my_comp\narm: new\n```\nHope that helps!")
    leg, comp = A.parse(reply)
    assert "id: my_leg" in leg and "id: my_comp" in comp
    assert A._ids(leg, comp) == ("my_leg", "my_comp")


def test_parse_returns_none_when_the_model_did_not_comply():
    assert A.parse("I cannot do that.") == (None, None)
    assert A.parse("```yaml leg\nid: only_one\n```")[1] is None


# ---- the wire, both formats, because the host is rented and its server is not our choice -------

def _fake_urlopen(captured, payload):
    class _R:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner):
            return json.dumps(payload).encode()

    def _open(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        captured["headers"] = dict(req.headers)
        return _R()
    return _open


def test_openai_wire_format(monkeypatch):
    cap = {}
    monkeypatch.setattr(A.urllib.request, "urlopen",
                        _fake_urlopen(cap, {"choices": [{"message": {"content": "hello"}}]}))
    m = A.Model("Qwen/Qwen2.5-72B-Instruct-AWQ", "http://1.2.3.4:8000/", api="openai", api_key="tok")
    assert m.chat([{"role": "user", "content": "hi"}]) == "hello"
    assert cap["url"] == "http://1.2.3.4:8000/v1/chat/completions"
    assert cap["body"]["max_tokens"] == 4000
    assert cap["headers"]["Authorization"] == "Bearer tok"


def test_ollama_wire_format(monkeypatch):
    cap = {}
    monkeypatch.setattr(A.urllib.request, "urlopen",
                        _fake_urlopen(cap, {"message": {"content": "hello"}}))
    m = A.Model("qwen2.5:7b-instruct", "http://localhost:11434", api="ollama")
    assert m.chat([{"role": "user", "content": "hi"}]) == "hello"
    assert cap["url"] == "http://localhost:11434/api/chat"
    assert "Authorization" not in cap["headers"]


# ---- the loop itself, against the real repo state ---------------------------------------------

@pytest.fixture(scope="module")
def ctx():
    return V.Context()


class _Replay:
    """A model that replays canned replies, so the loop is tested without a GPU."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages):
        self.seen.append(messages[-1]["content"])
        return self.replies.pop(0) if self.replies else ""


def _blocks(leg_yaml, comp_yaml):
    return "```yaml leg\n%s\n```\n```yaml composite\n%s\n```" % (leg_yaml, comp_yaml)


GOOD_LEG = """id: llm_test_capex_intensity
family: investment_test
category: Fundamental
title: Capital spending intensity
mechanism: >
  A firm spending far above its own history on plant and equipment is building capacity that has to
  be financed and depreciated before it earns anything, and investors extrapolate the growth story
  instead of the financing cost, so the price gives the excess back over the following quarters.
counterparty: growth-chasing retail investors and index funds that buy on capacity announcements
sign: -1
source: "EX-ANTE — Titman Wei Xie 2004, firms that raise capital expenditure abnormally underperform"
datasets: [fundamental6]
signal:
  fields: [capex]
template: "-group_rank(ts_mean(ts_backfill({signal}, 63), {w}), {group})"
params:
  w: [20, 60]
  group: [subindustry, industry]
settings:
  neutralization: [SUBINDUSTRY, INDUSTRY]
  decay: [4, 8]
  truncation: 0.08
regions: [USA]
delays: [1]
notes: >
  capex is quarterly so the template backfills it; the label file leaves the sign unstated and the
  direction here is Titman-Wei-Xie's, stated before any simulation.
"""

BAD_LEG = GOOD_LEG.replace("fields: [capex]", "fields: [this_field_does_not_exist]")

GOOD_COMP = """id: llm_test_capex_x_shortflow
title: Overbuilding that informed sellers also dislike
arm: new
legs: [llm_test_capex_intensity, short_volume_ratio_informed]
families: [investment_test, short]
combiners: [multiply]
mechanism: >
  Heavy capital spending is a financing burden the market extrapolates as growth, and short sellers
  are the one group paid to read the financing statement; when both say the same thing the capacity
  story is being sold by the people who checked it, and the drift is down.
counterparty: growth-chasing retail investors and index funds that hold the capacity story
source: "EX-ANTE — Titman Wei Xie 2004; Boehmer Jones Zhang 2008 on informed short selling"
regimes: {value_winter_2014_2020: "-", momentum_crash_2016: "+", covid_2020: "0", rate_shock_2022: "+"}
strongest_in: mid caps with liquid borrow and a real capital budget
weakens_when: a capex cycle is policy-subsidised so the financing cost does not bind
settings:
  neutralization: [SUBINDUSTRY, INDUSTRY]
  decay: [4, 8]
  truncation: 0.08
notes: >
  value_winter '-' because the winter rewarded asset-light compounders and this shorts asset-heavy
  names; momentum_crash_2016 '+' because the junk rally lifted the over-builders it is short;
  covid_2020 '0' because capital budgets were suspended and the signal goes stale both ways;
  rate_shock_2022 '+' because a higher discount rate is exactly the financing cost this trades.
"""


def test_verify_accepts_a_well_formed_mechanism_and_names_every_check(ctx, tmp_path):
    lp, cp = tmp_path / "leg.yaml", tmp_path / "comp.yaml"
    lp.write_text(GOOD_LEG)
    cp.write_text(GOOD_COMP)
    v = V.verify(lp, cp, ctx)
    assert [c["name"] for c in v["checks"]] == ["schema", "fields", "density", "sign", "renders",
                                                "typed", "standard", "distinct"]
    assert v["ok"], V.report(v)


def test_verify_catches_an_invented_field_id(ctx, tmp_path):
    lp, cp = tmp_path / "leg.yaml", tmp_path / "comp.yaml"
    lp.write_text(BAD_LEG)
    cp.write_text(GOOD_COMP)
    v = V.verify(lp, cp, ctx)
    assert not v["ok"] and "fields" in v["failed"]
    assert "this_field_does_not_exist" in V.report(v)


def test_propose_keeps_a_passing_proposal_and_leaves_it_staged(ctx, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "STAGED_LEGS", tmp_path / "legs")
    monkeypatch.setattr(A, "STAGED_COMPS", tmp_path / "comps")
    r = A.propose(ctx, _Replay([_blocks(GOOD_LEG, GOOD_COMP)]), dataset="fundamental6", tries=2)
    assert r["ok"] and r["attempts"] == 1
    assert (tmp_path / "legs/llm_test_capex_intensity.yaml").exists()
    assert (tmp_path / "comps/llm_test_capex_x_shortflow.yaml").exists()


def test_propose_repairs_once_then_keeps(ctx, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "STAGED_LEGS", tmp_path / "legs")
    monkeypatch.setattr(A, "STAGED_COMPS", tmp_path / "comps")
    model = _Replay([_blocks(BAD_LEG, GOOD_COMP), _blocks(GOOD_LEG, GOOD_COMP)])
    r = A.propose(ctx, model, dataset="fundamental6", tries=3)
    assert r["ok"] and r["attempts"] == 2
    # an invented field id cascades: nothing usable is left for forge.factory to render from
    assert r["history"][0]["failed"] == ["fields", "renders"]
    # the repair prompt must carry the machine's own words, not a summary of them
    assert "this_field_does_not_exist" in model.seen[1]


def test_propose_drops_a_proposal_that_never_passes_and_stages_nothing(ctx, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "STAGED_LEGS", tmp_path / "legs")
    monkeypatch.setattr(A, "STAGED_COMPS", tmp_path / "comps")
    r = A.propose(ctx, _Replay([_blocks(BAD_LEG, GOOD_COMP)] * 2), dataset="fundamental6", tries=2)
    assert not r["ok"] and len(r["history"]) == 2
    assert not list((tmp_path / "legs").glob("*.yaml"))


def test_propose_survives_a_model_that_ignores_the_output_format(ctx, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "STAGED_LEGS", tmp_path / "legs")
    monkeypatch.setattr(A, "STAGED_COMPS", tmp_path / "comps")
    r = A.propose(ctx, _Replay(["I am unable to comply.", "Still not complying."]),
                  dataset="fundamental6", tries=2)
    assert not r["ok"] and [h["failed"] for h in r["history"]] == [["format"], ["format"]]


def test_propose_many_runs_mechanisms_concurrently_and_survives_one_that_throws(ctx, monkeypatch, tmp_path):
    """A rented GPU is paid by the second, so mechanisms go out together; and one bad dataset must
    not take the batch down with it."""
    monkeypatch.setattr(A, "STAGED_LEGS", tmp_path / "legs")
    monkeypatch.setattr(A, "STAGED_COMPS", tmp_path / "comps")
    import threading
    live, peak, lock = [0], [0], threading.Lock()

    class _Slow:
        def chat(self, messages):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.05)
            with lock:
                live[0] -= 1
            if "boom" in messages[-1]["content"]:
                raise RuntimeError("endpoint died")
            return _blocks(GOOD_LEG, GOOD_COMP)

    datasets = ["fundamental6"] * 6
    out = A.propose_many(ctx, _Slow(), datasets, tries=1, concurrency=6)
    assert len(out) == 6
    assert peak[0] > 1, "mechanisms were serialised; the GPU would be idle"


def test_propose_many_reports_a_dataset_with_no_signed_fields_instead_of_raising(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "STAGED_LEGS", tmp_path / "legs")
    monkeypatch.setattr(A, "STAGED_COMPS", tmp_path / "comps")
    out = A.propose_many(ctx, _Replay([]), ["no_such_dataset_at_all"], tries=1, concurrency=2)
    assert out[0]["ok"] is False and "no signed fields" in out[0]["why"]


def test_parse_strips_a_reasoning_model_scratchpad_before_finding_the_blocks():
    """Qwen3.8 thinks before it answers. vLLM's --reasoning-parser should split that off, but the
    server is a rented box we did not configure, so the parser must not depend on the flag."""
    reply = ("<think>Let me pick a field. ```yaml leg\nid: decoy\n``` no, wrong one.</think>\n"
             "```yaml leg\nid: real_leg\n```\n```yaml composite\nid: real_comp\n```")
    leg, comp = A.parse(reply)
    assert A._ids(leg, comp) == ("real_leg", "real_comp")


def test_thinking_is_off_by_default_and_can_be_turned_back_on(monkeypatch):
    """MEASURED 2026-09-19: Qwen3.8-27B-FP8 burned all 8,000 completion tokens on reasoning and
    returned content of length 0 on the real prompt, so 12 of 12 mechanisms failed on 'format'.
    Filling a template needs no chain of thought."""
    cap = {}
    monkeypatch.setattr(A.urllib.request, "urlopen",
                        _fake_urlopen(cap, {"choices": [{"message": {"content": "ok"}}]}))
    A.Model("m", "http://h:8000").chat([{"role": "user", "content": "x"}])
    assert cap["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    A.Model("m", "http://h:8000", thinking=True).chat([{"role": "user", "content": "x"}])
    assert "chat_template_kwargs" not in cap["body"]


# ---- field selection no longer ranks by crowding (Khoa tick 2026-09-20) ------------------------

def test_shortlist_does_not_rank_by_crowding():
    """MEASURED 2026-09-20 on 102 rows carrying both a correlation reading and a known field
    crowding: pearson(log10 userCount, PROD) = -0.001, pearson(log10 alphaCount, PROD) = +0.003.
    Crowding does not predict correlation. Ranking ascending on it put the LLM arm on fields of
    median 9 users against the library's 3,249, cost ~0.4 Sharpe p50, and left it holding 0 of the
    27 rows that reached the bar that day. A regression here is that whole cost coming back."""
    from forge.llm import retrieve as RT
    ctx = V.Context()
    rows = RT.shortlist(ctx, n=60)
    assert rows, "no signed fields at all -- the fixture is wrong, not the ordering"
    users = [r["users"] for r in rows]
    assert users != sorted(users), "shortlist is still ordered emptiest-first"
    cov = [r["coverage"] or 0 for r in rows]
    assert cov == sorted(cov, reverse=True), "ordering must be by coverage, best first"


def test_the_dataset_pool_is_no_longer_capped_at_200_users():
    """The cap is what kept the author off every field that has ever cleared the Sharpe bar; it
    stays available as an argument, but nothing passes it by default."""
    from forge.llm import retrieve as RT
    ctx = V.Context()
    assert not hasattr(RT, "datasets_by_crowding"), "the crowding-first picker must be gone, not shadowed"
    wide = RT.datasets_for_author(ctx)
    tight = RT.datasets_for_author(ctx, max_users=200)
    assert len(wide) > len(tight), "the default pool must be strictly wider than the old capped one"
    assert max(d["users"] for d in wide) > 200, "the default pool must reach the crowded datasets"
    signed = [d["signed"] for d in wide]
    assert signed == sorted(signed, reverse=True), "most material first"


def test_the_author_pool_refuses_a_price_carrier_C30():
    """C30 says no price carrier as a base, and forge/compose.py justifies itself with 'the library
    has none'. That held only because nothing had written one: six pv datasets (pv87 2,316 signed
    fields, pv64, pv48, pv20, pv109, pv73) sat inside the author's pool the whole time, every one of
    them under the old 200-user cap. Lifting the cap moved pv87 to rank 1, which would have turned a
    dormant hole into a certainty. The filter is on the dataset id, matching forge/ensemble.py."""
    from forge.llm import retrieve as RT
    ctx = V.Context()
    assert RT.is_price_volume("pv87") and not RT.is_price_volume("fundamental28")
    for d in RT.datasets_for_author(ctx):
        assert not d["dataset"].startswith("pv"), d["dataset"]
    assert RT.shortlist(ctx, dataset="pv87", n=20) == [], "naming a pv dataset outright must yield nothing"
