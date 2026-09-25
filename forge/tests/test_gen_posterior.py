"""forge.gen.posterior: D34's reward, §0's harvest-pass, and the Beta arithmetic of §3.2 on synthetic rows."""
import random

from forge.gen import posterior as PO
from forge.gen import productions as P
from forge.offline import benchmark as BM

BINDING = BM.ESTIMAND["binding_checks"]


def checks(limit=1.58, sharpe=1.9, extra=(), fail=()):
    out = [{"name": n, "result": "FAIL" if n in fail else "PASS"} for n in BINDING]
    for c in out:
        if c["name"] == "LOW_SHARPE":
            c.update(limit=limit, value=sharpe)
    out += [{"name": "SELF_CORRELATION", "result": "PENDING"}, {"name": "REGULAR_SUBMISSION", "result": "PENDING"}]
    return out + [dict(c) for c in extra]


def leg(sig="spread", ts="ts_mean", score="group_rank", group="sector", windows=(("W_SHORT", 10),), dataset="ds1", tier_u=None):
    return {"sig": sig, "ts": ts, "tier_u": tier_u, "score": score, "group": group, "windows": [list(w) for w in windows],
            "dataset": dataset}


def row(alpha, sharpe, limit=1.58, hyp="gen:fam000000001", legs=None, shape="conf2", settings=None, **kw):
    s = dict({"region": "USA", "delay": 1, "neutralization": "INDUSTRY", "decay": 4, "truncation": 0.08}, **(settings or {}))
    return dict({"alpha": alpha, "sharpe": sharpe, "status": "COMPLETE", "settings": s,
                 "checks": checks(limit, sharpe), "formula": "f_" + alpha,
                 "meta": {"hypothesis": hyp, "gen_alpha": shape, "legs": legs or [leg(), leg(sig="single", dataset="ds2")]}},
                **kw)


def test_y_is_sharpe_against_0_8_of_the_rows_own_limit_at_the_line():
    assert PO.y(row("a", 1.27)) == 1 and PO.y(row("a", 1.26)) == 0
    assert PO.y(row("a", 1.264)) == 1                         # 0.8 x 1.58 = 1.2640000000000002 in floats
    assert PO.y(row("a", 2.16, limit=2.69)) == 1 and PO.y(row("a", 2.15, limit=2.69)) == 0
    assert PO.y(row("a", 1.3, limit=1.58)) == 1 and PO.y(row("a", 1.3, limit=2.69)) == 0   # its OWN limit
    assert PO.y(row("a", -1.9)) == 0


def test_y_is_none_when_the_row_is_not_an_observation():
    assert PO.y({"status": "ERROR", "alpha": None}) is None
    r = row("a", 1.9)
    r["checks"] = [c for c in r["checks"] if c["name"] != "LOW_SHARPE"]
    assert PO.y(r) is None
    r = row("a", None)
    r["checks"][0]["value"] = None
    assert PO.y(r) is None
    r = row("a", 1.9)
    [c for c in r["checks"] if c["name"] == "LOW_SHARPE"][0]["limit"] = None
    assert PO.y(r) is None


def test_a_units_warned_row_that_clears_the_seven_binding_checks():
    """§0: D24-pass (the 7 binding checks) and harvest-pass (every non-NON_BINDING check) differ exactly here.
    D34's y reads the Sharpe line only, so this row is y = 1, D24-pass, and NOT a harvest-pass."""
    r = row("u", 1.9)
    r["checks"].append({"name": "UNITS", "result": "WARNING"})
    d24 = all(c["result"] == "PASS" for c in r["checks"] if c["name"] in BINDING)
    assert d24 and PO.y(r) == 1 and PO.harvest_pass(r) is False
    r["checks"] = [c for c in r["checks"] if c["name"] != "UNITS"]
    assert PO.harvest_pass(r) is True


def test_posterior_counts_are_one_plus_y_and_one_plus_one_minus_y_per_level():
    rows = {"a": row("a", 1.9), "b": row("b", 0.5), "c": row("c", 1.5)}
    rows["d"] = row("d", 1.9, hyp="usa_short_x_profitability")        # library row: ignored
    rows["e"] = row("e", 1.9)
    rows["e"]["checks"] = []                                             # no observation: ignored
    post = PO.Posterior(rows)
    assert post.n_rows == 4 and post.n_obs == 3
    assert post.level("SIG", "spread") == (3, 2)          # y = 1, 0, 1 on top of Beta(1, 1)
    assert post.level("SIG", "single") == (3, 2)          # a second leg: counted once per row
    assert post.level("G", "sector") == (3, 2)            # both legs use sector: still once per row
    assert post.level("ALPHA", "conf2") == (3, 2) and post.level("ALPHA", "gate") == (1, 1)
    assert post.level("W_SHORT", 10) == (3, 2) and post.level("W_SHORT", 5) == (1, 1)
    assert post.level("NEUT", "INDUSTRY") == (3, 2) and post.level("DECAY", 4) == (3, 2)
    assert post.level("TRUNC", 0.08) == (3, 2) and post.level("TRUNC", 0.15) == (1, 1)
    assert post.dataset("ds1") == (3, 2) and post.dataset("ds2") == (3, 2) and post.dataset("zz") == (1, 1)


def test_levels_used_reads_only_grammar_levels():
    r = row("a", 1.0, legs=[leg(ts="tier_u", tier_u="ts_std_dev", windows=(("W_LONG", 252),)),
                             leg(ts="ts_sum_event", windows=(("W_EVENT", 60), ("W_LONG", 999)), score="rank", group=None)],
            shape="gate", settings={"decay": 16, "truncation": 0.05})
    got = PO.levels_used(r)
    assert {"ALPHA=gate", "TS=tier_u", "TIER_U=ts_std_dev", "W_LONG=252", "TS=ts_sum_event", "W_EVENT=60",
            "SCORE=rank", "NEUT=INDUSTRY"} <= got
    assert not {"W_LONG=999", "DECAY=16", "TRUNC=0.05"} & got


def test_round_weights_are_seeded_and_follow_the_evidence_and_leave_tier_u_to_the_floor():
    rows = {"w%d" % i: row("w%d" % i, 1.9, legs=[leg(ts="ts_zscore", windows=(("W_LONG", 126),))]) for i in range(200)}
    rows.update({"l%d" % i: row("l%d" % i, 0.1, legs=[leg(ts="ts_delta", dataset="ds9")]) for i in range(200)})
    post = PO.Posterior(rows)
    W1, th1 = PO.round_weights(post, random.Random(4), ["ds1", "ds9"])
    W2, th2 = PO.round_weights(post, random.Random(4), ["ds9", "ds1"])
    assert W1 == W2 and th1 == th2                         # one seed, one draw, whatever the input order
    assert W1["TS"]["ts_zscore"] > 0.9 > 0.1 > W1["TS"]["ts_delta"]
    assert set(W1["TS"]) == set(P.TS) and set(W1) == set(P.PRODUCTIONS)
    Wf, none = PO.floor_weights()
    assert none is None and Wf["TS"][P.TS_TIER_U] == 1.0
    assert all(v == 1.0 for prod in Wf.values() for v in prod.values())


def test_harvest_pass_reads_incomplete_as_no_pass():
    """Draw-5 gen N5 (Q06): a PENDING binding check, or no checks at all, is "incomplete" -- never a pass. On
    d0 this is why harvest-pass cannot fire while D0_SUBMISSION reads PENDING (N7; module text)."""
    r = row("p", 1.9)
    assert PO.harvest_pass(r) is True
    r["checks"].append({"name": "D0_SUBMISSION", "result": "PENDING"})
    assert PO.harvest_pass(r) is False
    assert PO.harvest_pass(dict(row("q", 1.9), checks=[])) is False
    fail = row("f", 1.9)
    fail["checks"][1]["result"] = "FAIL"
    assert PO.harvest_pass(fail) is False
