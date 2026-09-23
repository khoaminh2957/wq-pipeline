import pytest

from forge import signature as S

BOOK_FND = ("add(multiply(zscore(ts_decay_linear(ts_backfill(fnd6_ceqq, 60), 10)), 0.5), "
            "rank(ts_backfill(anl4_eps_ftm, 20)))")
NEWS = "group_rank(ts_delta(vec_avg(news29_neg_score), 5), subindustry)"


def test_fields_and_datasets():
    assert S.fields(BOOK_FND) == ["anl4_eps_ftm", "fnd6_ceqq"]
    assert S.datasets(S.fields(BOOK_FND)) == ["anl4", "fnd6"]
    assert S.datasets(S.fields("rank(divide(close, open))")) == ["pv"]
    assert S.datasets([]) == []


def test_families_collapse_operators():
    assert S.families(BOOK_FND) == ["smooth"]
    assert S.families(NEWS) == ["change", "vector"]
    assert S.families("rank(close)") == []


def test_signature_keys():
    sig = S.signature(BOOK_FND, "USA", 1)
    assert sig["key"] == "anl4|fnd6#smooth#USA/d1"
    assert sig["mechanism_key"] is None
    sig2 = S.signature(NEWS, "USA", 1, mechanism="news_neg_shock_v1")
    assert sig2["key"] == "news29#change+vector#USA/d1"
    assert sig2["mechanism_key"] == "news_neg_shock_v1#news29#USA/d1"
    assert S.signature("rank(close)", "EUR", 0)["datasets"] == ["pv"]


def test_index_hard_gate_and_load():
    book = [
        {"regular": {"code": BOOK_FND}, "settings": {"region": "USA", "delay": 1}},
        {"regular": {"code": "rank(ts_backfill(fnd6_saleq, 5))"}, "settings": {"region": "USA", "delay": 1}},
    ]
    idx = S.NoveltyIndex.from_book(book)
    assert len(idx) == 2
    assert idx.dataset_load("fnd6") == 2 and idx.dataset_load("anl4") == 1 and idx.dataset_load("news29") == 0
    # same data + same family + same cell -> not novel, even with a different field/window
    same = S.signature("zscore(ts_decay_linear(fnd6_atq, 30))", "USA", 1)
    assert not idx.is_novel(same) and idx.matches(same) == 1
    # same data, different transform family -> novel; same everything on another cell -> novel
    assert idx.is_novel(S.signature("rank(ts_delta(fnd6_saleq, 5))", "USA", 1))
    assert idx.is_novel(S.signature("rank(ts_backfill(fnd6_saleq, 5))", "EUR", 1))
    assert idx.is_novel(S.signature(NEWS, "USA", 1))


def test_index_roundtrip_from_file(tmp_path):
    import json
    entries = [S.signature(BOOK_FND, "USA", 1), S.signature(NEWS, "USA", 1)]
    p = tmp_path / "sig.json"
    p.write_text(json.dumps(entries))
    idx = S.NoveltyIndex.from_file(p)
    assert len(idx) == 2 and not idx.is_novel(entries[1])


def test_catalogue_aware_fields_and_datasets():
    fd = {"nws29_frontpage": "news29", "news_article_count": "news_sentiment_transfer", "close": "pv1"}
    code = "group_rank(ts_delta(vec_sum(nws29_frontpage), 5), industry) / rank(news_article_count)"
    assert S.fields(code, known=fd) == ["news_article_count", "nws29_frontpage"]
    assert S.datasets(S.fields(code, known=fd), fd) == ["news29", "news_sentiment_transfer"]
    sig = S.signature(code, "USA", 1, mechanism="m", field_datasets=fd)
    assert sig["key"] == "news29|news_sentiment_transfer#change+vector#USA/d1"
    # without the catalogue the prefix rule mis-assigns nws29 and misses news_article_count entirely
    assert S.signature(code, "USA", 1)["datasets"] == ["nws29"]
    assert S.fields("rank(close) + rank(open)", known=fd) == ["close"]


def test_group_fields_are_not_data_fields():
    fd = {"nws29_frontpage": "news29", "industry": "pv1", "subindustry": "pv1"}
    sig = S.signature("group_rank(ts_delta(vec_sum(nws29_frontpage), 5), industry)", "USA", 1, field_datasets=fd)
    assert sig["datasets"] == ["news29"] and sig["fields"] == ["nws29_frontpage"]
