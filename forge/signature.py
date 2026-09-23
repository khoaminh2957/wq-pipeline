"""forge.signature — what makes two alphas "the same idea" for the novelty gate (C12, C19).

A signature is (datasets, transform families, region/delay). It is EX-ANTE policy from operator
semantics and the playbook rule "windows, weights and neutralisation never create low correlation;
only a different data source or economic logic does". Whether it predicts measured self-corr is
the experiment the canary runs; nothing here is a measured mechanism.

Families collapse the ts_* operators so that swapping ts_decay_linear for ts_backfill (both
"smooth") does not count as a new idea, while ts_delta ("change") on the same data does.

Field → dataset: the crawled catalogue is the authority (`field_datasets`); field ids such as
`nws29_frontpage` (dataset news29) or `news_article_count` (news_sentiment_transfer) do NOT carry
their dataset id. The prefix rule is only the fallback for the legacy book (fnd6_, anl4_, ...).
"""
from __future__ import annotations

import json
import re
from collections import Counter

PV_FIELDS = ("close", "open", "high", "low", "volume", "vwap", "returns", "cap", "adv20",
             "sharesout", "dividend", "split")
_FIELD_RE = re.compile(r"\b([a-z]{2,6}\d+_[a-z0-9_]+|" + "|".join(PV_FIELDS) + r")\b")
_TOKEN_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\b(?!\s*\()")
GROUP_FIELDS = {"industry", "subindustry", "sector", "market", "country", "exchange", "currency"}

FAMILY = {
    "smooth": ("ts_backfill", "ts_decay_linear", "ts_decay_exp_window", "ts_mean", "ts_sum", "hump", "group_backfill"),
    "norm": ("ts_rank", "ts_zscore", "ts_scale", "ts_quantile"),
    "change": ("ts_delta", "ts_av_diff", "last_diff_value", "ts_returns", "ts_product"),
    "relate": ("ts_corr", "ts_covariance", "ts_regression", "ts_co_kurtosis", "ts_co_skewness"),
    "vol": ("ts_std_dev", "ts_kurtosis", "ts_skewness", "ts_moment"),
    "timing": ("ts_arg_min", "ts_arg_max", "days_from_last_change", "ts_min", "ts_max", "ts_count_nans"),
    "vector": ("vec_avg", "vec_sum", "vec_count", "vec_max", "vec_min", "vec_stddev", "vec_range"),
}
_OP_FAMILY = {op: fam for fam, ops in FAMILY.items() for op in ops}


def fields(code: str, known=None) -> list:
    """Sorted distinct data fields in a formula. With `known` (catalogue field ids) every
    non-call identifier that is a known field counts; without it the legacy prefix regex is used."""
    if known is not None:
        return sorted(t for t in set(_TOKEN_RE.findall(code or "")) if t in known and t not in GROUP_FIELDS)
    return sorted(set(_FIELD_RE.findall(code or "")))


def datasets(field_list, field_datasets=None) -> list:
    """Dataset ids for the fields: from the catalogue map when given, else the prefix rule
    (`fnd6_x` → fnd6; price-volume names → `pv`)."""
    out = set()
    for f in field_list:
        ds = (field_datasets or {}).get(f)
        if ds is None:
            ds = f.split("_", 1)[0] if "_" in f else "pv"
        out.add(ds)
    return sorted(out)


def families(code: str) -> list:
    """Sorted transform families present in a formula."""
    ops = set(re.findall(r"\b([a-z_]+)\s*\(", code or ""))
    return sorted({_OP_FAMILY[o] for o in ops if o in _OP_FAMILY})


def signature(code: str, region: str, delay, mechanism: str | None = None, field_datasets=None) -> dict:
    """The signature dict; `key` is the novelty key, `mechanism_key` the 1-per-week key (C19)."""
    fl = fields(code, known=field_datasets)
    ds = datasets(fl, field_datasets) or ["pv"]
    fam = families(code)
    cell = "%s/d%s" % (region, delay)
    key = "|".join(ds) + "#" + "+".join(fam) + "#" + cell
    return {"datasets": ds, "fields": fl, "families": fam, "region": region, "delay": delay,
            "key": key, "mechanism": mechanism,
            "mechanism_key": ("%s#%s#%s" % (mechanism, "|".join(ds), cell)) if mechanism else None}


class NoveltyIndex:
    """Signatures of everything already in the book (ACTIVE/submitted). `is_novel` is the hard
    gate; `dataset_load` feeds the soft novelty-distance term of the robust score."""

    def __init__(self, entries=()):
        self._keys = Counter()
        self._load = Counter()
        for e in entries:
            self.add(e)

    @classmethod
    def from_book(cls, book_rows, field_datasets=None):
        """Build from ACTIVE-book rows (`regular.code`, `settings.region/delay`)."""
        idx = cls()
        for a in book_rows:
            st = a.get("settings") or {}
            code = (a.get("regular") or {}).get("code") or ""
            idx.add(signature(code, st.get("region"), st.get("delay"), field_datasets=field_datasets))
        return idx

    @classmethod
    def from_file(cls, path):
        return cls(json.load(open(path)))

    def add(self, sig: dict) -> None:
        self._keys[sig["key"]] += 1
        for d in sig.get("datasets") or []:
            self._load[d] += 1

    def is_novel(self, sig: dict) -> bool:
        return self._keys[sig["key"]] == 0

    def matches(self, sig: dict) -> int:
        return self._keys[sig["key"]]

    def dataset_load(self, dataset: str) -> int:
        """Number of book alphas that use `dataset` (any region/transform)."""
        return self._load[dataset]

    def __len__(self):
        return sum(self._keys.values())
