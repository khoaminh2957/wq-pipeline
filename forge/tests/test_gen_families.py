"""forge.gen.families: Khoa's fingerprint family (D36, D38), held equal to fingerprint.StructuralIndex."""
import random

import fingerprint as FP
from forge.gen import families as FM
from forge.tests.test_gen_productions import POSTS, _draws


def _variants():
    """Parameter / horizon / group / neutralisation-free variants of the POSTs, and cross-family mixes."""
    k = POSTS["kqVbg1xP"]
    out = [k.replace("_30", "_60"), k.replace(", 5)", ", 20)").replace("sector", "industry"),
           k.replace("implied_volatility_put_30", "operating_income"),
           POSTS["rK5RGeqa"].replace("directional_significant_value_1", "directional_significant_value_7"),
           "rank(operating_income / assets)", "rank(implied_volatility_call_30 - implied_volatility_put_30)",
           "rank(close)", "group_rank(ts_mean(volume, 5), sector)"]
    return out


def test_the_index_agrees_with_structural_index_on_every_pair_drawn():
    """Whether a formula is a near-duplicate of anything registered: FamilyIndex.nearest vs StructuralIndex.is_dup,
    and the family returned is the most similar near-duplicate (brute force), earliest on a tie."""
    formulas = list(POSTS.values()) + _variants() + [c["formula"] for c, _ in _draws(400, seed=21)]
    rng = random.Random(22)
    rng.shuffle(formulas)
    reg, queries = formulas[:220], formulas[:40] + formulas[220:] + _variants()
    si, fi = FP.StructuralIndex(), FM.FamilyIndex()
    for i, f in enumerate(reg):
        si.register(f, "f%d" % i)
        fi.add(f, "f%d" % i)
    n_dup = 0
    for q in queries:
        fam, _ = fi.nearest(q)
        assert (fam is not None) == si.is_dup(q)[0], q
        if fam is not None:
            n_dup += 1
            sig = FP.structural_signature(q)
            best = max((FP.similarity(sig, s), -i) for i, (s, _) in enumerate(si.seen) if FP.near_duplicate(sig, s))
            assert fam == "f%d" % -best[1]
    assert n_dup >= 40                                   # the registered 40 at least, so the test has teeth


def test_a_horizon_window_group_variant_joins_and_another_bet_founds():
    """00_agreements.md, fingerprint as it stands: a horizon+window+group variant of one IV-spread formula is caught;
    an IV-spread against a profitability ratio is not."""
    fi = FM.FamilyIndex()
    fi.add(POSTS["kqVbg1xP"], "kq")
    v = POSTS["kqVbg1xP"].replace("_30", "_90").replace(", 5)", ", 10)").replace("subindustry", "industry")
    assert fi.assign(v) == ("kq", False)
    fi.add("rank(implied_volatility_call_30 - implied_volatility_put_30)", "iv")
    other = "rank(operating_income / assets)"
    fam, founded = fi.assign(other)
    assert founded and fam == FM.family_id(other) and fam not in ("kq", "iv")


def test_the_registry_keeps_each_rows_planned_family_and_prefers_the_nearest():
    a = "multiply(rank(g01_f01 - g01_f07), rank(g02_f03))"
    b = "multiply(rank(g01_f01 - g01_f07), group_rank(g02_f03, sector))"
    rows = {"A": {"alpha": "A", "formula": a, "meta": {"hypothesis": "gen:famA"}},
            "B": {"alpha": "B", "formula": b, "meta": {"hypothesis": "gen:famB"}},
            "L": {"alpha": "L", "formula": "rank(close)", "meta": {"hypothesis": "usa_short"}}}
    fi = FM.FamilyIndex.from_rows(rows)
    assert len(fi) == 2 and fi.families == {"famA": 1, "famB": 1}
    assert fi.nearest(a)[0] == "famA" and fi.nearest(b)[0] == "famB"      # identical: similarity 1.0 wins
    assert FM.family_of(rows["A"]) == "famA" and FM.family_of(rows["L"]) is None
    assert FM.family_of({"meta": {"hypothesis": "gen:"}}) is None


def test_family_id_is_the_formula_without_whitespace_and_copy_is_independent():
    assert FM.family_id("rank( x )") == FM.family_id("rank(x)") != FM.family_id("rank(y)")
    fi = FM.FamilyIndex()
    fi.add("rank(g01_f01)", "x")
    cp = fi.copy()
    cp.add("group_rank(g05_f02, sector)", "y")
    assert len(fi) == 1 and len(cp) == 2 and "y" not in fi.families and fi.digest() != cp.digest()
    fi.add("rank(  g01_f01 )", "z")                                     # the same formula again: ignored
    assert len(fi) == 1


def test_a_core_plus_add_on_cousin_joins_by_fingerprints_containment_clause():
    """fingerprint's first clause ("same core bet plus an add-on", containment >= 0.85 and cosine >= 0.75) fires
    where the similarity clause alone (0.6 x Jaccard + 0.4 x cosine >= 0.85) does not."""
    core = "rank(implied_volatility_call_30 - implied_volatility_put_30)"
    cousin = "multiply(rank(implied_volatility_call_30 - implied_volatility_put_30), rank(operating_income))"
    a, b = FP.structural_signature(core), FP.structural_signature(cousin)
    assert FP.near_duplicate(a, b) and FP.similarity(a, b) < FP.SIM_THRESHOLD
    fi, si = FM.FamilyIndex(), FP.StructuralIndex()
    fi.add(cousin, "c")
    si.register(cousin, "c")
    assert fi.nearest(core)[0] == "c" and si.is_dup(core)[0] is True
    wide_a = "rank(fa + fb + fc + fd + fe + ff + fg)"
    wide_b = "rank(fa + fb + fc + fd + fe + ff + fz)"                     # containment 6/7 = 0.857: just over 0.85
    assert FP.near_duplicate(FP.structural_signature(wide_a), FP.structural_signature(wide_b))
    fi.add(wide_b, "w")
    si.register(wide_b, "w")
    assert fi.nearest(wide_a)[0] == "w" and si.is_dup(wide_a)[0] is True


def test_the_registry_digest_names_the_family_of_each_member():
    """Draw-5 gen N5 (exec F06): the digest is over (fingerprint, family) pairs, so the same formulas under other
    families give another digest (and so another meta.gen_state)."""
    a, b = FM.FamilyIndex(), FM.FamilyIndex()
    a.add("rank(g01_f01)", "x")
    b.add("rank(g01_f01)", "y")
    assert a.digest() != b.digest()
    c = FM.FamilyIndex()
    c.add("rank(g01_f01)", "x")
    assert a.digest() == c.digest()
