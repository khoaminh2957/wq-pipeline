"""Field labels — the typed vocabulary of the forge (Khoa 2026-09-07 19:30, ticked).

Every MATRIX/VECTOR field in the catalogue gets a label on each axis below, derived ONLY from
(1) the platform's description, (2) the field's type and its dataset's category/subcategory, and
(3) statistics the catalogue already carries (coverage, userCount). Nothing here reads a simulated
alpha (Khoa's tick: "không phải từ alpha đã sim"). Each label names the rule that produced it, so a
wrong label can be traced to one line of this file.

AXES
  domain      what the number is about (profitability, short-flow, iv-skew, ...); fine domain from
              description keywords, else the coarse (category, subcategory) domain
  kind        code | flag | score | count | ratio | return | dispersion | days | coefficient | level
              (precedence: code, flag, count, leading-dispersion, score, return, ratio, dispersion, days, coefficient, level)
  unit        code | bool | score | count | ratio | percent | return | days | currency | shares |
              price | unitless
  time        daily | event | monthly | quarterly | annual   (dataset cadence, overridden by words)
  horizon_d   look-back / look-ahead window named in the description, in days (None if absent)
  sparsity    dense (coverage >= 0.9) | medium (>= 0.5) | sparse
  structure   MATRIX | VECTOR
  crowding    untouched (userCount 0) | light (<= 20) | used (<= 200) | crowded
  sign        + | - | unstated, with sign_source = description | domain-prior | unstated
              EX-ANTE priors live in DOMAIN_SIGN with their textbook rationale; a field whose
              description states the direction overrides the prior. Never from data.
  directional True when the quantity can be negative (returns, income, sentiment, deltas)
  by_region   {"USA/d1": {structure, coverage, sparsity}} — 199 fields are VECTOR in one region and
              MATRIX in another (buy_sell_ratio_top5_60d_filled: VECTOR in USA/CHN, MATRIX in EUR/ASI;
              an `add` on it errored on 2026-09-07 "does not support event inputs"); the top-level
              structure/sparsity are the first region's, readers must prefer the cell's entry
VECTOR axes (Khoa 2026-09-07 21:20 "gán thêm nhãn vector"): an event stream is read only through a
reducer, and which reducer is meaningful depends on what one event's number is:
  vec_role     event-value (a per-event score / ratio / return: average, max or min are meaningful,
               a sum is not) | event-amount (a per-event currency / share amount: sum, average, max)
               | event-count (a per-event count: sum, count, max) | event-flag (0/1: sum = how many,
               avg = share) | event-code (a code / date / id: only how many events)
  vec_reducers the reducers allowed, in preference order; vec_after = the kind each one yields
  event_stream news-article | transcript | estimate-submission | insider-transaction | social-post |
               option-trade | filing-line-item | event
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIELDS_DIR = ROOT / "fetched/rc/fields"
OUT = ROOT / "fetched/rc/field_labels.jsonl"

# ---------------------------------------------------------------- domain rules (description first)
# (regex on the lower-cased description, fine domain). Order matters: first hit wins.
DOMAIN_RULES = [
    (r"^(the )?(volume weighted average price|vwap|close price|closing price|open price|opening price|high price|low price|last price|mid price)|volume[- ]weighted average price|\bvwap\b", "price-level"),
    (r"shares used to calculate|shares used in|weighted average shares|share count used", "size"),
    (r"short (sale|sell|interest|volume|trade)|shares? shorted|days to cover|utili[sz]ation|borrow (demand|rate|cost|fee)|shares on loan|securities lending|loan rate", "short-flow"),
    (r"implied volatility|iv\b|call.*put|put.*call|skew|option (volume|open interest|contract|maturity|delta|implied)|options (share )?volume|put-call|call-put|open interest|delta-adjusted|at-the-money|moneyness", "option"),
    (r"insider|officer|director.*(buy|sell|transaction)|form 4", "insider-flow"),
    (r"institution|13f|ownership|holdings? (by|of)|fund holding", "institutional-holdings"),
    (r"sentiment|tone|bullish|bearish|positive.*negative|optimis|pessimis", "sentiment"),
    (r"tweet|twitter|reddit|social|stocktwits|buzz|mention", "social"),
    (r"news|headline|article|story|press release|event (count|importance|significance)", "news"),
    (r"predict|prediction|probability|likelihood|neural|deep learning|cnn|lstm|embedding|latent|eigen|component|feature", "ml-prediction"),
    (r"earnings (surprise|announce|call|date|move|effect)|announcement|surprise", "earnings-event"),
    (r"employee|headcount|hiring|job|glassdoor|workforce|reviewer|culture and values|work-life|ceo approval", "employee"),
    (r"recommend|upgrade|downgrade|(analyst|broker|consensus|street).{0,40}(rating|target)|(rating|target).{0,40}(analyst|broker|consensus|street)", "analyst-rating"),
    (r"revision|revised|change in .{0,40}(estimate|consensus|forecast)|estimate (change|momentum)|(estimate|consensus|forecast)s? (raised|lowered|up|down)\b", "analyst-revision"),
    (r"(standard deviation|dispersion|std|range|high|low) of .*(estimate|forecast|consensus)|estimate.*(dispersion|std|stddev)", "analyst-dispersion"),
    (r"number of (analyst|estimate|broker)|estimate count|count of (analyst|estimate)|analysts? (covering|following)", "analyst-coverage"),
    (r"estimat|forecast|consensus|expected (eps|revenue|earnings)|guidance", "analyst-estimate"),
    (r"accrual|non-?cash|income minus cash|earnings minus cash", "accruals"),
    (r"cash ?flow|operating cash|free cash|fcf", "cashflow"),
    (r"to[- ]price\b|/ ?price\b|price[- ]to[- ](book|earnings|sales|cash|ebitda|revenue|value|nav|fcf|dividend|tangible|intrinsic)|price/|\bp/e\b|\bpe ratio|ev/|enterprise value|book[- ]to[- ]market|earnings yield|multiple\b", "valuation"),
    (r"capex|capital expenditure|investment in|asset growth|ppe\b|property,? plant", "investment"),
    (r"dividend|payout|buyback|repurchase|yield\b", "payout-yield"),
    (r"debt|leverage|liabilit|interest coverage|solvency|credit", "leverage"),
    (r"current ratio|quick ratio|working capital|liquidity", "liquidity-fund"),
    (r"margin|roe\b|roa\b|roic|return on|profitab|\bprofit\b|operating (income|profit)|net income|ebit|gross profit|earnings\b", "profitability"),
    (r"revenue|sales|turnover \(|top ?line", "sales"),
    (r"growth|yoy|year[- ]over[- ]year|qoq|quarter[- ]over[- ]quarter", "growth"),
    (r"book value|valuation", "valuation"),
    (r"market cap|capitali[sz]ation|size\b|total assets|shares outstanding|float", "size"),
    (r"beta|factor (exposure|loading)|exposure to|risk model|idiosyncratic|specific return|residual", "risk-factor"),
    (r"volatil|std dev|standard deviation|variance|realized", "volatility"),
    (r"bid[- ]ask|spread|illiquid|amihud|turnover ratio|dollar volume", "liquidity-trade"),
    (r"volume|traded (shares|quantity)|shares traded|share quantity|trade count|number of trades", "volume-activity"),
    (r"momentum|return|moving average|rsi|macd|oscillator|breakout|technical", "price-technical"),
    (r"\bvwap|open price|close price|closing price|high price|low price|\bprice\b", "price-level"),
    (r"esg|environment|governance|controvers|board structure|board of directors", "esg"),
    (r"macro|gdp|inflation|cpi|unemployment|interest rate|fx|exchange rate|currency rate", "macro"),
    (r"^(?!.*(depreciation|amortization)).*(acquisition|m&a|merger|takeover|bankrupt|default probability|distress)", "corporate-event-model"),
    (r"dummy|placeholder|reference", "meta"),
]
COARSE_DOMAIN = {           # (category, subcategory) -> domain when no description rule fires
    ("Fundamental", None): "fundamental-other", ("Analyst", None): "analyst-estimate",
    ("Price Volume", None): "price-technical", ("Model", None): "model-other", ("Other", None): "other",
    ("News", None): "news", ("Sentiment", None): "sentiment", ("Risk", None): "risk-factor",
    ("Earnings", None): "earnings-event", ("Option", None): "option", ("Insiders", None): "insider-flow",
    ("Institutions", None): "institutional-holdings", ("Social Media", None): "social", ("Macro", None): "macro",
    ("Short Interest", None): "short-flow", ("Imbalance", None): "order-imbalance", ("Broker", None): "analyst-estimate",
}

# EX-ANTE sign priors by domain: the direction the textbook anomaly literature gives, used only when
# the description does not state one. Domains absent here are "unstated" (sign-free roles only).
DOMAIN_SIGN = {
    "profitability": ("+", "Novy-Marx 2013 gross profitability; Fama-French RMW: higher profitability → higher returns"),
    "accruals": ("-", "Sloan 1996: high accruals (income − cash flow) → lower returns"),
    "cashflow": ("+", "Sloan 1996 / Hou-Xue-Zhang q-factors: cash-flow-based profitability → higher returns"),
    "earnings-event": ("+", "Bernard-Thomas 1989 PEAD: positive earnings surprise → post-announcement drift up (returns/SUE only; counts, days, dispersion carry no sign)"),
    "investment": ("-", "Titman-Wei-Xie 2004 / Fama-French CMA: high asset growth & capex → lower returns"),
    "short-flow": ("-", "Asquith-Pathak-Ritter 2005, Boehmer-Jones-Zhang 2008: heavy shorting → lower returns"),
    "analyst-revision": ("+", "Givoly-Lakonishok 1979, Chan-Jegadeesh-Lakonishok 1996: upward revisions → higher returns"),
    "analyst-rating": ("+", "Womack 1996: upgrades / better recommendations → higher returns"),
    "sentiment": ("+", "Tetlock 2007: positive text sentiment → higher short-horizon returns"),
    "social": ("+", "Same construct as sentiment; weaker literature (Chen et al. 2014 Seeking Alpha)"),
    "payout-yield": ("+", "Litzenberger-Ramaswamy 1979; buyback anomaly Ikenberry 1995"),
    "leverage": ("-", "Penman-Richardson-Tuna 2007: leverage component of book-to-price is priced negatively"),
    "growth": ("+", "Only for estimate/sales growth read as improvement; asset growth is under investment (−)"),
}
# a raw amount in these domains is a size, not a signal (gross PP&E is not asset growth; total debt is not leverage)
LEVEL_NO_PRIOR = {"investment", "leverage", "payout-yield", "growth"}
# a description that states the direction beats the prior
SIGN_WORDS = [
    # orientation of a valuation ratio: cheapness (X-to-price, yield) is + (Fama-French HML); expensiveness (price-to-X) is −
    (r"to[- ]price\b|/ ?price\b|earnings yield|cash ?flow yield|book[- ]to[- ]market|dividend yield", "+"),
    (r"price[- ]to[- ](book|earnings|sales|cash|ebitda|revenue|value|nav|fcf|dividend|tangible|intrinsic)|price/|\bp/e\b|\bpe ratio|ev/|enterprise value (to|/)|price[- ]earnings|price[- ]book", "-"),
    # insider flow: the direction must be in the words (Seyhun 1986, Lakonishok-Lee 2001: net buying +)
    (r"insider.*(purchase|buy|bought|net buy)|(purchase|buy|bought).*insider|net insider (buy|purchas)", "+"),
    (r"^(?!.*(purchase|buy|bought)).*(insider.*(sale|sell|sold)|(sale|sell|sold).*insider)", "-"),
    # polarity of a sentiment measure: "bullish minus bearish" is +, "bearish minus bullish" is −, one-sided by its word
    (r"bullish.*(minus|less|-|and|vs).*bearish|positive.*(minus|less|-).*negative", "+"),
    (r"bearish.*(minus|less|-|and|vs).*bullish|negative.*(minus|less|-).*positive", "-"),
    (r"^(?!.*(positive|bullish)).*(negative|bearish|pessimis)", "-"),
    (r"net cash\b|cash minus debt|negative net debt", "+"),
    (r"(higher|larger|greater) (values? |scores? )?(indicat|mean|suggest|=|imply|correspond).*(positive|bullish|better|strong|favou?rable|higher return|outperform)", "+"),
    (r"(higher|larger|greater) (values? |scores? )?(indicat|mean|suggest|=|imply|correspond).*(negative|bearish|worse|weak|unfavou?rable|lower return|underperform|risk)", "-"),
    (r"100 = (highest|most|best)|1 = highest|higher is better|positive values? (indicat|mean)", "+"),
    (r"100 = (lowest|least|worst)|higher is worse|negative values? (indicat|mean)", "-"),
]

KIND_RULES = [      # precedence order
    ("code", r"\bcode\b|identifier|\bid\b|categor|alphanumeric|must decode|label for|class label|ticker|\bname\b|period end date|fiscal period end|\bdate associated|timestamp|date when|\(1-4\)|(quarter|period|year) to which|\bisin\b|\bcusip\b|\bsedol\b"),
    ("flag", r"\bflag\b|whether|\bbinary\b|indicator (of|that|for|if)|dummy variable|1 if|0 if|true if|boolean"),
    ("level", r"^(the )?(volume weighted average price|vwap|close price|closing price|open price|opening price|high price|low price|market capitali[sz]ation)"),
    ("return", r"^(the )?(\d+\w* |\w+-\w+ )?(growth|change|percent change|pct change|delta|difference|increase|decrease) (in|of) (the )?number"),
    ("count", r"number of (?!days)|\bcount\b|\bcounts\b|how many"),
    ("dispersion", r"^(the |a )?(mean absolute deviation|mean absolute error|mean squared error|root mean|standard deviation|std\.? ?dev|stddev|dispersion|variance|volatility|range|kurtosis|skewness|coefficient of variation)|\bmae\b|\brmse\b|absolute error|prediction error|squared|sum of squares"),
    ("score", r"percentile|\bscore\b|\brank\b|\bindex\b|\bscaled\b|z-?score|probabilit|likelihood|confidence|quantile|decile|\brating\b|normalized|standardi[sz]ed"),
    ("return", r"\breturns?\b|growth|change in|(percentage|percent|pct|price) move|percent change|yoy|qoq|delta\b|momentum|revision|surprise|diff(erence)? (between|from)"),
    ("ratio", r"\bratio\b|(?<!close)(?<!open)(?<!high)(?<!low)(?<!date)(?<!day)(?<!year)(?<!quarter)(?<!month)(?<!week)(?<!peak)(?<!trough)-to-|/ ?[a-z]|divided by|per share|\bover\b|relative to|as a (percent|fraction|share) of|yield\b|margin\b|turnover\b|\s%\s|% of|% total|percent of"),
    ("dispersion", r"standard deviation|std\.? ?dev|stddev|dispersion|variance|volatil|\brange\b|spread between|kurtosis|skewness|absolute deviation|\bmad\b"),
    ("days", r"\bdays? (since|until|to|from|before|after)\b|number of days|day count|time since|\bage\b|days_from"),
    ("coefficient", r"\bbeta\b|coefficient|loading|exposure|weight\b|elasticity|correlation"),
]
UNIT_BY_KIND = {"code": "code", "flag": "bool", "score": "score", "count": "count", "ratio": "ratio", "return": "return",
                "dispersion": "unitless", "days": "days", "coefficient": "unitless"}
LEVEL_UNIT_RULES = [
    ("percent", r"percent|\bpct\b|%"),
    ("currency", r"usd|dollar|\beur\b|\bjpy\b|currency|in (millions|thousands)|revenue|income|cash|liabilit|debt|equity|capital|sales|expense|profit|ebit|\bcost|market cap|book value|total assets|net assets|amount|value of (all|the|total)|preferred stock|common stock"),
    ("shares", r"\bshares\b|share (count|quantity)|units? traded|volume\b"),
    ("price", r"\bprice\b|\bvwap\b|closing|close price|open price|high price|low price|\bnav\b"),
]
NONNEG_KINDS = {"count", "days", "code", "flag"}
MONEY_CATS = {"Fundamental", "Analyst", "Earnings", "Insiders", "Institutions", "Broker", "Model", "Price Volume"}
NONNEG_WORDS = r"volume|volatil|standard deviation|variance|\bprice\b|shares|count|number of|market cap|total assets|revenue|sales"
CADENCE = {"Fundamental": "quarterly", "Institutions": "quarterly", "Analyst": "event", "Earnings": "event", "News": "event",
           "Insiders": "event", "Social Media": "daily", "Sentiment": "daily", "Price Volume": "daily", "Model": "daily",
           "Option": "daily", "Risk": "daily", "Short Interest": "daily", "Macro": "monthly", "Imbalance": "daily",
           "Broker": "event", "Other": "daily"}
CADENCE_WORDS = [("annual", r"\bannual|fiscal year|\byearly|12[- ]month|ttm|trailing twelve"),
                 ("quarterly", r"quarter|fiscal|10-q|10-k|balance sheet|income statement"),
                 ("monthly", r"\bmonthly|month[- ]end"), ("event", r"announce|event|filing|transaction|headline|article")]
VEC_ROLE = {          # kind -> (role, [(reducer, kind after)])
    "code": ("event-code", [("vec_count", "count")]),
    "days": ("event-code", [("vec_count", "count")]),
    "flag": ("event-flag", [("vec_sum", "count"), ("vec_avg", "ratio"), ("vec_count", "count")]),
    "count": ("event-count", [("vec_sum", "count"), ("vec_count", "count"), ("vec_max", "count")]),
}
EVENT_STREAM = [("transcript", r"transcript|earnings call|conference call|q&a|question"),
                ("news-article", r"news|headline|article|story|press release"),
                ("insider-transaction", r"insider|form 4|officer|director"),
                ("estimate-submission", r"estimate|forecast|consensus|analyst|broker|revision|surprise"),
                ("social-post", r"tweet|twitter|reddit|social|post"),
                ("option-trade", r"option|call|put|contract"),
                ("filing-line-item", r"fiscal|quarter|annual|10-k|10-q|balance sheet|income statement|filing")]
STREAM_BY_CAT = {"News": "news-article", "Analyst": "estimate-submission", "Broker": "estimate-submission", "Insiders": "insider-transaction",
                 "Social Media": "social-post", "Option": "option-trade", "Fundamental": "filing-line-item", "Earnings": "estimate-submission"}


def vector_axes(kind: str, unit: str, cat: str, d: str) -> dict:
    if kind in VEC_ROLE:
        role, red = VEC_ROLE[kind]
    elif kind == "level" and unit in ("currency", "shares"):
        role, red = "event-amount", [("vec_sum", "level"), ("vec_avg", "level"), ("vec_max", "level")]
    else:
        role, red = "event-value", [("vec_avg", kind), ("vec_max", kind), ("vec_min", kind)]
    stream = next((nm for nm, pat in EVENT_STREAM if re.search(pat, d)), None) or STREAM_BY_CAT.get(cat, "event")
    return {"vec_role": role, "vec_reducers": [r for r, _ in red], "vec_after": dict(red), "event_stream": stream}


HORIZON = re.compile(r"(\d+)\s*-?\s*(d\b|day|days|w\b|week|weeks|m\b|month|months|q\b|quarter|quarters|y\b|yr|year|years)")
HDAYS = {"d": 1, "day": 1, "days": 1, "w": 7, "week": 7, "weeks": 7, "m": 30, "month": 30, "months": 30,
         "q": 91, "quarter": 91, "quarters": 91, "y": 365, "yr": 365, "year": 365, "years": 365}


# DOMAIN_RULES and SIGN_WORDS are written (pattern, label) for readability; _first takes (label, pattern)
DOMAIN_RULES = [(lab, pat) for pat, lab in DOMAIN_RULES]
SIGN_WORDS = [(lab, pat) for pat, lab in SIGN_WORDS]


def _first(rules, text):
    for label, pat in rules:
        if re.search(pat, text):
            return label, pat
    return None, None


def label(row: dict) -> dict:
    """Labels for one catalogue row (description + type + category + coverage + userCount)."""
    d = (row.get("description") or "").lower()
    cat = (row.get("category") or {}).get("name") if isinstance(row.get("category"), dict) else row.get("category")
    sub = (row.get("subcategory") or {}).get("name") if isinstance(row.get("subcategory"), dict) else row.get("subcategory")
    why = {}
    dom, pat = _first(DOMAIN_RULES, d)
    if dom is None:
        dom = COARSE_DOMAIN.get((cat, None), "other")
        why["domain"] = "coarse:%s/%s" % (cat, sub)
    else:
        why["domain"] = "desc:%s" % pat[:30]
    kind, kpat = _first(KIND_RULES, d)
    if kind is None:
        kind, kpat = "level", "default"
    why["kind"] = kpat[:30]
    unit = UNIT_BY_KIND.get(kind)
    if unit is None:
        unit, upat = _first(LEVEL_UNIT_RULES, d)
        if unit == "currency" and (cat not in MONEY_CATS or re.search(r"\b(measure|factor|indicator|signal|score) of\b|consistency|quality|stability", d)) \
                and not re.search(r"usd|dollar|currency|in (millions|thousands)|amount", d):
            unit, upat = "unitless", "currency-needs-money-category"     # an ML "risk from assets" is not a dollar amount
        unit = unit or "unitless"
        why["unit"] = (upat or "default")[:30]
    time_ = CADENCE.get(cat, "daily")
    for t, pat_t in CADENCE_WORDS:
        if re.search(pat_t, d):
            time_ = t
            why["time"] = pat_t[:30]
            break
    m = HORIZON.search(d)
    horizon = int(m.group(1)) * HDAYS[m.group(2)] if m else None
    cov = row.get("coverage")
    sparsity = "dense" if (cov or 0) >= 0.9 else "medium" if (cov or 0) >= 0.5 else "sparse"
    users = row.get("userCount") or 0
    crowding = "untouched" if users == 0 else "light" if users <= 20 else "used" if users <= 200 else "crowded"
    sign, spat = _first(SIGN_WORDS, d)
    if sign:
        src = "description"
        why["sign"] = spat[:30]
    elif dom in DOMAIN_SIGN and why["domain"].startswith("desc:") and kind not in ("code", "flag", "count", "dispersion", "days", "coefficient") \
            and not (kind == "level" and dom in LEVEL_NO_PRIOR) \
            and not (dom in ("sentiment", "social") and not re.search(r"sentiment|tone|bullish|bearish|positive|negative|optimis|pessimis", d)) \
            and not (dom in ("sentiment", "social") and re.search(r"neutral|objectiv|subjectiv|uncertain", d)):
        # the prior needs a domain READ FROM THE DESCRIPTION; a domain inherited from the dataset's
        # category (coarse) says nothing about what this particular number is
        sign, src = DOMAIN_SIGN[dom][0], "domain-prior"
        why["sign"] = DOMAIN_SIGN[dom][1][:40]
    else:
        sign, src = "unstated", "unstated"
    directional = kind in ("return", "coefficient") or (kind == "level" and not re.search(NONNEG_WORDS, d)) \
        or (kind == "score" and re.search(r"sentiment|tone|z-?score|surprise|net\b", d) is not None)
    out = {"id": row["id"], "dataset": (row.get("dataset") or {}).get("id"), "category": cat, "subcategory": sub,
           "structure": row.get("type"), "domain": dom, "kind": kind, "unit": unit, "time": time_, "horizon_d": horizon,
           "sparsity": sparsity, "coverage": cov, "crowding": crowding, "users": users, "sign": sign, "sign_source": src,
           "directional": bool(directional), "description": row.get("description") or "", "why": why,
           "regions": sorted({row.get("region")} - {None}), "by_region": row.get("_by_region") or {}}
    if row.get("type") == "VECTOR" or any(v.get("structure") == "VECTOR" for v in out["by_region"].values()):
        out.update(vector_axes(kind, unit, cat, d))
    return out


def catalogue_rows(fields_dir=FIELDS_DIR):
    seen = {}
    for f in sorted(glob.glob(str(pathlib.Path(fields_dir) / "*.jsonl"))):
        for line in open(f):
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("type") not in ("MATRIX", "VECTOR"):
                continue
            key = "%s/d%s" % (j.get("region"), j.get("delay"))
            cov = j.get("coverage") or 0
            entry = {"structure": j.get("type"), "coverage": cov, "sparsity": "dense" if cov >= 0.9 else "medium" if cov >= 0.5 else "sparse"}
            if j["id"] in seen:
                seen[j["id"]]["_regions"].add(key)
                seen[j["id"]]["_by_region"].setdefault(key, entry)
                continue
            j["_regions"] = {key}
            j["_by_region"] = {key: entry}
            seen[j["id"]] = j
    return seen


def build(out_path=OUT, fields_dir=FIELDS_DIR) -> dict:
    rows = catalogue_rows(fields_dir)
    counts = collections.defaultdict(collections.Counter)
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        for r in rows.values():
            lab = label(r)
            lab["regions"] = sorted(r["_regions"])
            fh.write(json.dumps(lab, ensure_ascii=False) + "\n")
            for ax in ("domain", "kind", "unit", "time", "sparsity", "sign", "sign_source", "crowding"):
                counts[ax][lab[ax]] += 1
    return {"fields": len(rows), "counts": {k: dict(v.most_common()) for k, v in counts.items()}}


def load(path=OUT) -> dict:
    out = {}
    with open(path) as fh:
        for line in fh:
            try:
                j = json.loads(line)
            except ValueError:
                continue
            out[j["id"]] = j
    return out


def for_region(v: dict, key: str) -> dict:
    """The label as it holds in one region/delay (structure and sparsity differ by region)."""
    o = v.get("by_region", {}).get(key)
    return dict(v, **o) if o else v


def sample(labels: dict, region: str, delay: int, n: int, seed: int, vector_only: bool = False) -> list:
    key = "%s/d%d" % (region, delay)
    pool = [for_region(v, key) for v in labels.values() if key in v.get("regions", [])]
    if vector_only:
        pool = [v for v in pool if v["structure"] == "VECTOR"]
    rng = random.Random(seed)
    rng.shuffle(pool)
    # stratify: at most 4 per domain so the sample spans the vocabulary
    per, out = collections.Counter(), []
    for v in pool:
        if per[v["domain"]] < 4:
            out.append(v)
            per[v["domain"]] += 1
        if len(out) >= n:
            break
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("build", "sample", "field"))
    ap.add_argument("--region", default="USA")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--id", default="")
    ap.add_argument("--vector", action="store_true", help="sample only VECTOR fields and show the vector axes")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        s = build()
        print("labelled %d fields" % s["fields"])
        for ax, c in s["counts"].items():
            print("  %-12s %s" % (ax, dict(list(c.items())[:14])))
        return 0
    labels = load()
    if a.cmd == "field":
        print(json.dumps(labels.get(a.id), ensure_ascii=False, indent=1))
        return 0
    for v in sample(labels, a.region, a.delay, a.n, a.seed, vector_only=a.vector):
        if a.vector:
            print("| %s | %s | %s | %s | %s | %s | %s | %s |" % (v["id"][:40], v["domain"], v["kind"], v.get("vec_role"), "/".join(v.get("vec_reducers", [])),
                                                            v.get("event_stream"), v["sparsity"], v["description"][:90].replace("|", "/")))
            continue
        print("| %s | %s | %s | %s | %s | %s | %s%s | %s | %s |" % (
            v["id"][:40], v["domain"], v["kind"], v["unit"], v["time"], v["sparsity"], v["sign"],
            "" if v["sign_source"] != "domain-prior" else " (prior)", v["structure"], v["description"][:90].replace("|", "/")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
