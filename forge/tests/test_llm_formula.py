import json

import pytest

from forge.llm import formula as F
from forge.llm import verify as V


@pytest.fixture(scope="module")
def ctx():
    return V.Context()


@pytest.fixture(scope="module")
def ops():
    return F.allowlist()


GOOD = {"id": "credit_rank_vs_group",
        "rationale": "Index funds must hold the name whatever its credit rank says, so they absorb the drift",
        "formula": "group_zscore(ts_mean(mdl28_sm_structural_multiple_credit_structural_country_rank, 20), industry)",
        "neutralization": "SUBINDUSTRY", "decay": 8}


def test_allowlist_is_the_rc85_list_read_from_the_doc(ops):
    """OPERATORS.md says 85 usable operators and 'anything else -> 400 reject'; the prompt and the
    checker must both read that list from the doc rather than carry a copy that can drift."""
    assert len(ops) == 85
    assert {"group_rank", "ts_mean", "multiply", "group_zscore", "trade_when", "hump"} <= ops
    assert "totally_made_up_op" not in ops


def test_a_formula_using_a_never_simulated_operator_is_accepted(ctx, ops):
    """group_zscore is one of the 65 allowlisted operators this desk has never simulated. The point
    of this arm is that such a formula is legal; nothing may refuse it merely for being unfamiliar."""
    v = F.verify_formula(GOOD, ctx, ops)
    assert v["ok"], v["detail"]


def test_an_invented_operator_is_caught(ctx, ops):
    v = F.verify_formula({**GOOD, "formula": "totally_made_up_op(close, 5)"}, ctx, ops)
    assert not v["ok"] and "ops" in v["failed"]


def test_an_invented_field_is_caught(ctx, ops):
    v = F.verify_formula({**GOOD, "formula": "group_zscore(ts_mean(no_such_field_here, 20), industry)"}, ctx, ops)
    assert not v["ok"] and "fields" in v["failed"]
    assert "no_such_field_here" in v["detail"]


def test_a_rationale_with_no_counterparty_is_caught(ctx, ops):
    assert "counterparty" in F.check_rationale("the signal reliably predicts future stock returns well")
    assert F.check_rationale("Retail investors chase the headline and hold the loser") == ""
    v = F.verify_formula({**GOOD, "rationale": "it predicts returns"}, ctx, ops)
    assert not v["ok"] and "rationale" in v["failed"]


def test_bad_settings_are_caught(ctx, ops):
    assert "settings" in F.verify_formula({**GOOD, "neutralization": "MARKET"}, ctx, ops)["failed"]
    assert "settings" in F.verify_formula({**GOOD, "decay": 7}, ctx, ops)["failed"]


def test_parse_formulas_takes_many_blocks_and_drops_malformed_ones():
    reply = ("<think>scratch</think>\n"
             "```yaml formula\nid: a\nrationale: r\nformula: \"rank(close)\"\nneutralization: INDUSTRY\ndecay: 4\n```\n"
             "```yaml formula\nid: b\nrationale: r\nformula: \"rank(open)\"\nneutralization: INDUSTRY\ndecay: 4\n```\n"
             "```yaml formula\nthis is not: [valid\n```\n"
             "```yaml formula\nid: c\n```\n")           # no formula key -> dropped
    got = F.parse_formulas(reply)
    assert [g["id"] for g in got] == ["a", "b"]


def test_build_plan_is_what_runner_plan_expects_and_dedupes(ctx, tmp_path):
    twin = {**GOOD, "id": "same_construction_other_name"}    # identical formula+settings
    other = {**GOOD, "id": "other", "decay": 4}
    p = F.build_plan([GOOD, twin, other], ctx, tmp_path / "plan.json")
    assert p["n"] == 2 and p["allocate"] is False           # the twin collapses; the allocator is bypassed
    on_disk = json.loads((tmp_path / "plan.json").read_text())
    assert on_disk["constructions"][0]["meta"]["arm"] == F.ARM
    for c in on_disk["constructions"]:
        m, s = c["meta"], c["settings"]
        assert m["forge"] == 1 and m["cand"] and m["mechanism_key"] and m["rationale"]
        assert s["region"] == "USA" and s["delay"] == 1 and s["universe"] == "TOP3000"


class _Replay:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages, schema=None):
        self.seen.append(messages[-1]["content"])
        return self.replies.pop(0) if self.replies else ""


def _blocks(items):
    out = []
    for i in items:
        out.append("```yaml formula\nid: %s\nrationale: %s\nformula: \"%s\"\nneutralization: %s\ndecay: %s\n```"
                   % (i["id"], i["rationale"], i["formula"], i["neutralization"], i["decay"]))
    return "\n".join(out)


def test_batch_keeps_the_good_and_repairs_the_rejected(ctx, ops):
    bad = {**GOOD, "id": "bad", "formula": "totally_made_up_op(close, 5)"}
    fixed = {**GOOD, "id": "fixed"}
    model = _Replay([_blocks([GOOD, bad]), _blocks([fixed])])
    kept = F.batch(ctx, model, dataset="model28", n=3, tries=2, ops=ops, guided="off")
    assert sorted(k["id"] for k in kept) == ["credit_rank_vs_group", "fixed"]
    # the repair prompt carries the machine's own words, so the model can act on them
    assert "totally_made_up_op" in model.seen[1]


def test_batch_returns_nothing_for_a_dataset_with_no_signed_fields(ctx, ops):
    assert F.batch(ctx, _Replay([]), dataset="no_such_dataset", n=3, ops=ops, guided="off") == []


# ---- guardrails: constrained decoding makes a whole class of failure unsamplable ---------------

def test_json_schema_pins_the_envelope_and_enumerates_the_retrieved_fields(ctx):
    from forge.llm import retrieve as RT
    rows = RT.shortlist(ctx, dataset="model28", n=5)
    sc = F.json_schema(10, rows)
    item = sc["properties"]["items"]["items"]
    assert item["additionalProperties"] is False               # it cannot invent a key
    assert item["properties"]["neutralization"]["enum"] == list(F.NEUTS)
    assert item["properties"]["decay"]["enum"] == list(F.DECAYS)
    assert item["properties"]["fields_used"]["items"]["enum"] == [r["id"] for r in rows]
    assert item["properties"]["rationale"]["minLength"] >= 40   # no "it predicts returns"


def test_formula_grammar_has_only_real_fields_and_allowlisted_operators(ctx, ops):
    from forge.llm import retrieve as RT
    rows = RT.shortlist(ctx, dataset="model28", n=4)
    g = F.formula_grammar(rows, ops)
    assert g.startswith("root ::= expr")
    for r in rows:
        assert '"%s"' % r["id"] in g
    assert '"group_zscore"' in g and '"ts_mean"' in g
    assert "totally_made_up_op" not in g


def test_parse_json_items_reads_guided_output_and_falls_back_to_blocks():
    guided = json.dumps({"items": [{"id": "a", "formula": "rank(close)"},
                                   {"id": "b", "formula": "rank(open)"}]})
    assert [i["id"] for i in F.parse_json_items(guided)] == ["a", "b"]
    # a host that ignores guided_json still returns fenced blocks; the loop must not care
    blocks = '```yaml formula\nid: z\nrationale: r\nformula: "rank(x)"\n```'
    assert [i["id"] for i in F.parse_json_items(blocks)] == ["z"]
    assert F.parse_json_items("total gibberish") == []


def test_batch_sends_the_schema_when_guided_and_not_when_off(ctx, ops):
    seen = []

    class _M:
        def chat(self, messages, schema=None):
            seen.append(schema)
            return json.dumps({"items": [dict(GOOD)]})

    F.batch(ctx, _M(), dataset="model28", n=2, tries=1, ops=ops, guided="json")
    assert seen[0] and seen[0]["properties"]["items"]["items"]["properties"]["decay"]["enum"]
    seen.clear()

    class _M2:
        def chat(self, messages):                              # a host with no schema support
            return _blocks([GOOD])

    kept = F.batch(ctx, _M2(), dataset="model28", n=2, tries=1, ops=ops, guided="off")
    assert [k["id"] for k in kept] == ["credit_rank_vs_group"]


def test_all_85_operator_signatures_fit_in_the_prompt():
    """The reason there is no vector store: the corpus that decides whether a call is legal is
    ~460 tokens. Retrieval infrastructure for something that fits would be cost with no benefit."""
    sigs, ops = F.signatures(), F.allowlist()
    block = "\n".join(sigs.get(o, o + "(...)") for o in sorted(ops))
    assert len(block) // 4 < 700
    assert "ts_regression(y, x, d" in block and "hump(x, hump = 0.01)" in block
