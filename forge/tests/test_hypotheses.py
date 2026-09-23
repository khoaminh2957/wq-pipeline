import textwrap

import pytest

from forge import hypotheses as H

GOOD = textwrap.dedent("""
    id: news_frontpage_attention_v1
    category: News
    title: Front-page attention shock reverses
    mechanism: Front-page coverage draws attention buying that reverses over the next week.
    counterparty: Attention-driven retail buyers.
    sign: -1
    source: "EX-ANTE — Barber & Odean 2008 (attention), Tetlock 2007 (media)"
    datasets: [news29]
    signal:
      fields: [nws29_frontpage, nws29_full_frontpage]
      vector: vec_sum
    template: "-group_rank(ts_sum({signal}, {w}), {group})"
    params:
      w: [3, 5, 10]
      group: [subindustry, industry]
    settings:
      neutralization: [SUBINDUSTRY, INDUSTRY]
      decay: [0, 4]
      truncation: 0.08
    regions: any
    delays: [0, 1]
""")


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_load_good(tmp_path):
    h = H.load_file(_write(tmp_path, "a.yaml", GOOD))
    assert h.id == "news_frontpage_attention_v1" and h.category == "News" and h.sign == -1
    assert h.placeholders() == {"signal", "w", "group"}
    assert h.signal["vector"] == "vec_sum" and h.delays == [0, 1] and h.regions == "any"


@pytest.mark.parametrize("edit,msg", [
    (("category: News", "category: Newz"), "unknown category"),
    (("sign: -1", "sign: 0"), "sign must be"),
    (('source: "EX-ANTE', 'source: "I think'), "RULE 0"),
    (("vector: vec_sum", "vector: vec_median"), "not a vec_"),
    (("{w}", "{window}"), "placeholders without params"),
    (("w: [3, 5, 10]", "w: []"), "non-empty list"),
    (("delays: [0, 1]", "delays: [0, 2]"), "delays must be"),
    (("title: Front", "bogus: Front"), "unknown keys"),
])
def test_validation_errors(tmp_path, edit, msg):
    text = GOOD.replace(*edit)
    assert text != GOOD
    with pytest.raises(H.HypothesisError, match=msg):
        H.load_file(_write(tmp_path, "b.yaml", text))


def test_template_must_use_signal(tmp_path):
    text = GOOD.replace("ts_sum({signal}, {w})", "ts_sum(close, {w})")
    with pytest.raises(H.HypothesisError, match="must use"):
        H.load_file(_write(tmp_path, "c.yaml", text))


def test_library_sorted_and_unique(tmp_path):
    _write(tmp_path, "z.yaml", GOOD.replace("news_frontpage_attention_v1", "zzz"))
    _write(tmp_path, "a.yaml", GOOD)
    lib = H.load_library(tmp_path)
    assert [h.id for h in lib] == ["news_frontpage_attention_v1", "zzz"]
    assert H.categories(lib) == {"News"}
    _write(tmp_path, "dup.yaml", GOOD)
    with pytest.raises(H.HypothesisError, match="duplicate"):
        H.load_library(tmp_path)


def test_signal2_validation(tmp_path):
    base = GOOD.replace("  vector: vec_sum\n", "  vector: vec_sum\nsignal2:\n  fields: [only_one]\n")
    assert base != GOOD
    with pytest.raises(H.HypothesisError, match="pair 1:1"):
        H.load_file(_write(tmp_path, "s2a.yaml", base))
    paired = GOOD.replace("  vector: vec_sum\n", "  vector: vec_sum\nsignal2:\n  fields: [a, b]\n")
    with pytest.raises(H.HypothesisError, match="does not use"):
        H.load_file(_write(tmp_path, "s2b.yaml", paired))
    ok = paired.replace("ts_sum({signal}, {w})", "ts_sum({signal} - {signal2}, {w})")
    h = H.load_file(_write(tmp_path, "s2c.yaml", ok))
    assert h.signal2 == {"fields": ["a", "b"]} and "signal2" in h.placeholders()
    lst = GOOD.replace("category: News", "category: [News, Sentiment]")
    assert H.load_file(_write(tmp_path, "s2d.yaml", lst)).categories() == ["News", "Sentiment"]


def test_density_validation(tmp_path):
    bad = GOOD.replace("  vector: vec_sum\n", "  vector: vec_sum\n  density: sparse\n")
    with pytest.raises(H.HypothesisError, match="density must be"):
        H.load_file(_write(tmp_path, "d1.yaml", bad))
    bad = GOOD.replace("  vector: vec_sum\n", "  vector: vec_sum\n  density: backfill\n  density_window: 0\n")
    with pytest.raises(H.HypothesisError, match="density_window"):
        H.load_file(_write(tmp_path, "d2.yaml", bad))
    ok = GOOD.replace("  vector: vec_sum\n", "  vector: vec_sum\n  density: zero\n")
    assert H.load_file(_write(tmp_path, "d3.yaml", ok)).signal["density"] == "zero"


def test_template_list_validation(tmp_path):
    ok = GOOD.replace('template: "-group_rank(ts_sum({signal}, {w}), {group})"',
                      'template:\n  - "-group_rank(ts_sum({signal}, {w}), {group})"\n  - "-group_rank(ts_rank({signal}, {w}), {group})"')
    h = H.load_file(_write(tmp_path, "t1.yaml", ok))
    assert len(h.templates()) == 2 and h.placeholders() == {"signal", "w", "group"}
    bad = GOOD.replace('template: "-group_rank(ts_sum({signal}, {w}), {group})"',
                       'template:\n  - "-group_rank(ts_sum({signal}, {w}), {group})"\n  - "rank(close)"')
    with pytest.raises(H.HypothesisError, match="every template"):
        H.load_file(_write(tmp_path, "t2.yaml", bad))
