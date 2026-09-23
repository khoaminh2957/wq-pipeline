import json
import time

from forge import submit as SUB

NOW = 1_800_000_000.0


def _row(alpha, pyr=("USA/D1/NEWS",), pyramid_pass=True, prod_limit=None):
    ck = [{"name": "MATCHES_PYRAMID", "result": "PASS" if pyramid_pass else "FAIL",
           "pyramids": [{"name": n, "multiplier": 1.2} for n in pyr]},
          {"name": "PROD_CORRELATION", "result": "PENDING", "limit": prod_limit},
          {"name": "SELF_CORRELATION", "result": "PENDING", "limit": 0.7}]
    return {"alpha": alpha, "checks": ck, "formula": "f(%s)" % alpha, "sharpe": 2.0, "fitness": 1.2, "turnover": 0.1}


def _scored(alpha, hyp="h1", score=0.8, mk=None, stage="candidate", pbo="insufficient (< 20 trials)"):
    return {"alpha": alpha, "hypothesis": hyp, "mechanism_key": mk or ("%s#news29#USA/d1" % hyp), "score": score, "stage": stage,
            "pbo_status": pbo, "pbo_pass": None}


COUNTS = {("USA", 1): {"News": 0, "Model": 22, "Short Interest": 2, "Price Volume": 42}}


def test_corr_lines_and_cell_gain():
    assert SUB.corr_lines(_row("A")) == (0.7, 0.7)
    assert SUB.corr_lines(_row("A", prod_limit=0.65)) == (0.65, 0.7)
    assert SUB.cell_gain([{"name": "USA/D1/NEWS", "multiplier": 1.2}], COUNTS) == 3 * 1.2
    assert SUB.cell_gain([{"name": "USA/D1/MODEL", "multiplier": 1.3}, {"name": "USA/D1/SHORTINTEREST", "multiplier": 1.1}], COUNTS) == 1 * 1.1
    assert SUB.cell_gain([{"name": "USA/D1/PV", "multiplier": 1.1}], COUNTS) == 0
    assert SUB.cell_gain([{"name": "garbage"}], COUNTS) == 0 and SUB.cell_gain(None, COUNTS) == 0


def test_eligibility_reasons():
    scored = {"A": _scored("A"), "B": _scored("B", hyp="h2"), "C": _scored("C", hyp="h3"), "D": _scored("D", hyp="h4"),
              "E": _scored("E", hyp="h5"), "F": _scored("F", hyp="h6", stage="dsr-fail"), "G": _scored("G", hyp="h7"),
              "H": _scored("H", hyp="h1")}
    rows = {a: _row(a) for a in "ABCDEFH"}
    rows["D"] = _row("D", pyramid_pass=False)
    corr = {"A": {"prod": 0.5, "self": 0.3, "read_at": NOW}, "B": {"prod": 0.75, "self": 0.3, "read_at": NOW},
            "C": {"prod": 0.5, "self": "200-empty", "read_at": NOW}, "D": {"prod": 0.5, "self": 0.3, "read_at": NOW},
            "E": {"prod": 0.5, "self": 0.3, "read_at": NOW}, "H": {"prod": 0.5, "self": 0.3, "read_at": NOW}}
    history = [{"alpha": "E", "mechanism_key": "h5#x", "posted_at": NOW - 100, "http": 201},
               {"alpha": "Z", "mechanism_key": "h1#news29#USA/d1", "posted_at": NOW - 3 * 86400, "http": 201}]
    elig, held = SUB.eligible(scored, corr, rows, COUNTS, history, now=NOW)
    # Khoa 2026-09-08: no weekly rule -- h1 posted 3 days ago does not hold A and H
    assert {e["alpha"] for e in elig} == {"A", "H"}
    assert held == {"corr-over-line": 1, "corr-unmeasured": 1, "pyramid-not-pass": 1, "already-posted": 1, "no-journal-row": 1}
    # a sibling over the correlation line is reported as such
    corr["A"] = {"prod": 0.85, "self": 0.85, "read_at": NOW}
    _, held = SUB.eligible(scored, corr, rows, COUNTS, history, now=NOW)
    assert held["corr-over-line"] == 2


def test_daily_diversity_rule_three_dataset_sets_among_four():
    scored = {a: _scored(a, hyp="h1") for a in "AB"}
    scored.update({a: _scored(a, hyp="h2") for a in "CD"})
    for a in "ABCD":
        scored[a]["mechanism_key"] = ("h1#news29#USA/d1" if a in "AB" else "h2#fnd6#USA/d1")
    rows = {a: _row(a) for a in "ABCD"}
    corr = {a: {"prod": 0.5, "self": 0.3, "read_at": NOW} for a in "ABCD"}
    # two of news29 already posted TODAY: a third news29 is held, fnd6 is free
    history = [{"alpha": "X", "mechanism_key": "h1#news29#USA/d1", "posted_at": NOW - 600, "http": 201},
               {"alpha": "Y", "mechanism_key": "h1#news29#USA/d1", "posted_at": NOW - 300, "http": 201}]
    elig, held = SUB.eligible(scored, corr, rows, COUNTS, history, now=NOW)
    assert {e["alpha"] for e in elig} == {"C", "D"} and held["dataset-set-repeated-today"] == 2
    # news29 twice and fnd6 once today: a second fnd6 would make the day 2+2 -> held; a third set is free
    history.append({"alpha": "C", "mechanism_key": "h2#fnd6#USA/d1", "posted_at": NOW - 100, "http": 201})
    scored["E"] = _scored("E", hyp="h3"); scored["E"]["mechanism_key"] = "h3#option8#USA/d1"
    rows["E"] = _row("E"); corr["E"] = {"prod": 0.5, "self": 0.3, "read_at": NOW}
    elig, held = SUB.eligible(scored, corr, rows, COUNTS, history, now=NOW)
    assert {e["alpha"] for e in elig} == {"E"}
    # yesterday's posts do not count
    for h in history:
        h["posted_at"] = NOW - 2 * 86400
    elig, _ = SUB.eligible(scored, corr, rows, COUNTS, history, now=NOW)
    assert {e["alpha"] for e in elig} == {"A", "B", "D", "E"}
    assert SUB.datasets_of("h1#news29|fnd6#USA/d1") == "news29|fnd6" and SUB.datasets_of(None) == ""


def test_order_cells_first_then_score_then_self_and_second_best():
    scored = {"A": _scored("A", "h1", 0.90), "B": _scored("B", "h1", 0.86), "C": _scored("C", "h2", 0.99),
              "D": _scored("D", "h3", 0.60), "E": _scored("E", "h3", 0.60)}
    rows = {"A": _row("A"), "B": _row("B"), "C": _row("C", pyr=("USA/D1/MODEL",)),      # C fills a FULL cell
            "D": _row("D"), "E": _row("E")}
    corr = {a: {"prod": 0.5, "self": s, "read_at": NOW} for a, s in (("A", 0.3), ("B", 0.2), ("C", 0.1), ("D", 0.4), ("E", 0.2))}
    elig, _ = SUB.eligible(scored, corr, rows, COUNTS, [], now=NOW)
    assert [e["alpha"] for e in elig] == ["A", "B", "E", "D", "C"]   # open cell first; score; then self
    assert SUB.choose(elig)["alpha"] == "B"                          # A 0.90 vs B 0.86 within 10% -> second-best
    scored["B"]["score"] = 0.70
    elig, _ = SUB.eligible(scored, corr, rows, COUNTS, [], now=NOW)
    assert SUB.choose(elig)["alpha"] == "A"
    assert SUB.choose([]) is None


def test_history_and_403_budget(tmp_path):
    log = tmp_path / "sub.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    log.write_text(json.dumps({"alpha": "A", "mechanism_key": "h1#x", "posted_at": NOW - 10, "http": 403}) + "\n"
                   + json.dumps({"alpha": "B", "mechanism_key": "h2#x", "posted_at": NOW - 10 * 86400, "http": 403}) + "\n")
    ledger.write_text(json.dumps({"alpha": "C", "stage": "reserved", "reserved_at": NOW - 5}) + "\n"
                      + json.dumps({"alpha": "C", "stage": "posted"}) + "\n")
    hist = SUB.posted_history(paths=(log,), ledger=ledger)
    assert {h["alpha"] for h in hist} == {"A", "B", "C"}
    assert SUB.recent_403(hist, now=NOW) == 1                        # the 10-day-old refusal no longer counts


def test_record_writes_a_full_row(tmp_path):
    pick = {"alpha": "A", "hypothesis": "h1", "mechanism_key": "h1#x", "pyramids": [{"name": "USA/D1/NEWS"}],
            "score": 0.8, "prod": 0.5, "self": 0.3, "row": _row("A"), "lines": (0.7, 0.7), "cell_gain": 3.6, "read_at": NOW}
    SUB.record(pick, 201, "{\"ok\":1}", path=tmp_path / "s.jsonl")
    r = json.loads((tmp_path / "s.jsonl").read_text())
    assert r["alpha"] == "A" and r["http"] == 201 and r["pyramids"] == ["USA/D1/NEWS"] and r["source"] == "forge"


def test_pbo_holds():
    scored = {"A": dict(_scored("A"), pbo_pass=False, pbo_status="ok"), "B": dict(_scored("B", hyp="h2"), pbo_status="pending"),
              "C": dict(_scored("C", hyp="h3"), pbo_status="insufficient (< 20 trials)", pbo_pass=None), "D": dict(_scored("D", hyp="h4"), pbo_status="ok", pbo_pass=True)}
    rows = {a: _row(a) for a in "ABCD"}
    corr = {a: {"prod": 0.5, "self": 0.3, "read_at": NOW} for a in "ABCD"}
    scored["E"] = _scored("E", hyp="h5"); scored["E"].pop("pbo_status"); scored["E"].pop("pbo_pass")   # never judged: held
    rows["E"] = _row("E"); corr["E"] = {"prod": 0.5, "self": 0.3, "read_at": NOW}
    elig, held = SUB.eligible(scored, corr, rows, COUNTS, [], now=NOW)
    assert {e["alpha"] for e in elig} == {"C", "D"} and held["pbo-fail"] == 1 and held["pbo-pending"] == 1 and held["pbo-unjudged"] == 1


def test_diversity_rule_is_a_per_post_test():
    import collections
    # 2+1+1 over a day: the third of one set is refused; a second repeating set is refused
    assert SUB.diversity_ok("a", collections.Counter()) and SUB.diversity_ok("a", collections.Counter(a=1))
    assert not SUB.diversity_ok("a", collections.Counter(a=2))
    assert not SUB.diversity_ok("b", collections.Counter(a=2, b=1)) and SUB.diversity_ok("c", collections.Counter(a=2, b=1))
    # inside ONE invocation the counter advances with each accepted POST: three composites on the same
    # dataset set cannot all go out (before this rule lived only in eligible(), read once per invocation)
    sets = SUB.today_dataset_sets([], NOW)
    elig = [{"alpha": a, "mechanism_key": "c%s#news46|us_short_sale#USA/d1" % a} for a in "123"] + [{"alpha": "4", "mechanism_key": "d#fnd6#USA/d1"}]
    out = []
    while elig:
        pick = elig.pop(0)
        out.append(pick["alpha"])
        sets[SUB.datasets_of(pick["mechanism_key"])] += 1
        elig = [e for e in elig if SUB.diversity_ok(SUB.datasets_of(e["mechanism_key"]), sets)]
    assert out == ["1", "2", "4"]
    assert SUB.today_dataset_sets([{"mechanism_key": "c#x#USA/d1", "http": 201, "posted_at": NOW - 10},
                                   {"mechanism_key": "c#y#USA/d1", "http": 403, "posted_at": NOW - 10},
                                   {"mechanism_key": "c#z#USA/d1", "http": 201, "posted_at": NOW - 3 * 86400}], NOW) == {"x": 1}


def test_reread_after_a_post_and_after_thirty_minutes():
    hist = [{"http": 201, "posted_at": NOW - 100}, {"http": 403, "posted_at": NOW - 50}, {"http": None, "posted_at": NOW - 10}]
    assert SUB.last_accepted_post(hist) == NOW - 100 and SUB.last_accepted_post([]) == 0
    assert not SUB.needs_reread(NOW - 60, NOW, NOW - 100)          # read after the last POST, 1 min old
    assert SUB.needs_reread(NOW - 120, NOW, NOW - 100)             # read BEFORE the last accepted POST
    assert SUB.needs_reread(NOW - 31 * 60, NOW, 0)                 # older than 30 min
    assert SUB.needs_reread(None, NOW, 0)


def test_record_carries_the_arm(tmp_path):
    row = dict(_row("A"), meta={"forge": 1, "arm": "new"})
    pick = {"alpha": "A", "hypothesis": "h1", "mechanism_key": "h1#x", "pyramids": [], "score": 0.8, "prod": 0.5, "self": 0.3,
            "row": row, "lines": (0.7, 0.7), "cell_gain": 0.0, "read_at": NOW}
    SUB.record(pick, 201, "{}", path=tmp_path / "s.jsonl")
    assert json.loads((tmp_path / "s.jsonl").read_text())["arm"] == "new"


# --- the structural no-repeat rule on the submit path (Khoa 2026-09-22, agreements D18) -------------
IV_SUBMITTED = ("multiply(group_rank(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 5), sector), "
                "(1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 5), sector)))")
IV_VARIANT = ("multiply(group_rank(ts_mean(implied_volatility_call_90 - implied_volatility_put_90, 20), industry), "
              "(1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 10), industry)))")
OTHER_FAMILY = "group_rank(ts_rank(operating_income / equity, 252), subindustry)"


def _novelty_case(candidate_formula, submitted_formula=IV_SUBMITTED, submitted_readable=True):
    from forge import novelty as NV
    scored = {"A": _scored("A")}
    rows = {"A": dict(_row("A"), formula=candidate_formula)}
    corr = {"A": {"prod": 0.5, "self": 0.3, "read_at": NOW}}
    # the submit-log row carries the formula, which is where build() reads it from
    history = [{"alpha": "S", "mechanism_key": "h9#x", "posted_at": NOW - 86400, "http": 201,
                "formula": submitted_formula if submitted_readable else None}]
    nov = NV.build(history, rows)
    return SUB.eligible(scored, corr, rows, COUNTS, history, now=NOW, novelty=nov)


def test_a_structural_variant_of_a_submitted_alpha_is_held():
    elig, held = _novelty_case(IV_VARIANT)
    assert elig == [] and held["structure-already-submitted"] == 1


def test_a_different_family_passes_the_novelty_gate_and_carries_its_similarity():
    elig, held = _novelty_case(OTHER_FAMILY)
    assert [e["alpha"] for e in elig] == ["A"]
    assert "structure-already-submitted" not in held
    assert 0.0 <= elig[0]["structural_sim"] < 0.85 and elig[0]["structural_twin"] == "S"


def test_an_incomplete_novelty_index_holds_the_round_instead_of_guessing():
    # the submitted alpha's formula is unreadable -> novelty is UNKNOWN, never "novel"
    elig, held = _novelty_case(OTHER_FAMILY, submitted_readable=False)
    assert elig == [] and held["novelty-index-incomplete"] == 1


def test_a_candidate_with_no_formula_is_held_rather_than_passed():
    from forge import novelty as NV
    scored = {"A": _scored("A")}
    rows = {"A": dict(_row("A"), formula=None)}
    corr = {"A": {"prod": 0.5, "self": 0.3, "read_at": NOW}}
    history = [{"alpha": "S", "http": 201, "posted_at": NOW - 86400, "mechanism_key": "h9#x",
                "formula": IV_SUBMITTED}]
    elig, held = SUB.eligible(scored, corr, rows, COUNTS, history, now=NOW, novelty=NV.build(history, rows))
    assert elig == [] and held["novelty-candidate-unreadable"] == 1


def test_without_a_novelty_index_the_old_behaviour_is_unchanged():
    scored = {"A": _scored("A")}
    rows = {"A": dict(_row("A"), formula=IV_VARIANT)}
    corr = {"A": {"prod": 0.5, "self": 0.3, "read_at": NOW}}
    elig, held = SUB.eligible(scored, corr, rows, COUNTS, [], now=NOW)
    assert [e["alpha"] for e in elig] == ["A"] and elig[0]["structural_sim"] is None


def test_posted_history_carries_the_formula_it_used_to_discard(tmp_path):
    """MEASURED on the VPS 2026-09-22: both submit logs record `formula`, but the projection kept
    only four keys, so novelty could not read mL516W9W's structure and held every candidate."""
    log = tmp_path / "submitted.jsonl"
    log.write_text(json.dumps({"alpha": "mL516W9W", "http": 201, "posted_at": 1.0,
                               "formula": IV_SUBMITTED}) + "\n")
    h = SUB.posted_history(paths=(log,))
    assert h[0]["formula"] == IV_SUBMITTED and h[0]["alpha"] == "mL516W9W"
