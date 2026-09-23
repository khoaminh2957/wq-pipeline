from forge import labels as L


def _row(i, desc, cat="Fundamental", typ="MATRIX", cov=0.95, users=3, ds="fundamental6"):
    return {"id": i, "description": desc, "category": {"name": cat}, "subcategory": {"name": cat}, "type": typ,
            "coverage": cov, "userCount": users, "dataset": {"id": ds}, "region": "USA", "delay": 1}


def test_short_flow_count_gets_the_literature_prior():
    lab = L.label(_row("executed_short_trade_share_count", "Number of shares in executed short sale trades", cat="Short Interest"))
    assert lab["domain"] == "short-flow" and lab["kind"] == "count" and lab["unit"] == "count"
    assert lab["sign"] == "unstated"                       # a count is never given a directional prior
    lab2 = L.label(_row("short_ratio", "Short volume ratio: short volume divided by total volume", cat="Short Interest"))
    assert lab2["kind"] == "ratio" and lab2["sign"] == "-" and lab2["sign_source"] == "domain-prior"


def test_profitability_level_quarterly_currency():
    lab = L.label(_row("operating_profit_3", "Profit from core business operations before interest and taxes."))
    assert (lab["domain"], lab["kind"], lab["unit"], lab["time"], lab["sign"]) == ("profitability", "level", "currency", "quarterly", "+")
    assert lab["directional"] is True and lab["sparsity"] == "dense"


def test_code_and_flag_are_sign_free_and_not_rankable_kinds():
    lab = L.label(_row("nws29_full_significance", "Event importance level code: High, Medium, Low (must decode)", cat="News", typ="VECTOR"))
    assert lab["kind"] == "code" and lab["unit"] == "code" and lab["sign"] == "unstated" and lab["time"] == "event"
    lab = L.label(_row("is_buyback", "Flag whether the company announced a buyback this quarter"))
    assert lab["kind"] == "flag" and lab["unit"] == "bool"


def test_description_direction_beats_the_prior_and_horizon_is_parsed():
    lab = L.label(_row("x", "Accrual quality score; higher values indicate better earnings quality (100 = highest)"))
    assert lab["sign"] == "+" and lab["sign_source"] == "description" and lab["kind"] == "score"
    lab = L.label(_row("y", "120-day close-to-close historical volatility, annualized percent", cat="Earnings"))
    assert lab["kind"] == "dispersion" and lab["horizon_d"] == 120 and lab["sign"] == "unstated" and lab["directional"] is False


def test_ratio_volume_is_unstated_and_nonnegative():
    lab = L.label(_row("pv87_dvp_nugget", "Daily share volume divided by 3-month average daily share volume", cat="Price Volume", cov=0.5, users=42))
    assert lab["domain"] == "volume-activity" and lab["kind"] == "ratio" and lab["sign"] == "unstated"
    assert lab["sparsity"] == "medium" and lab["crowding"] == "used" and lab["horizon_d"] == 90


def test_sample_is_stratified_by_domain():
    labs = {}
    for i in range(30):
        labs["a%d" % i] = {"id": "a%d" % i, "domain": "profitability", "regions": ["USA/d1"]}
        labs["b%d" % i] = {"id": "b%d" % i, "domain": "short-flow", "regions": ["USA/d1"]}
    s = L.sample(labs, "USA", 1, 50, seed=1)
    assert len(s) == 8 and {v["domain"] for v in s} == {"profitability", "short-flow"}


def test_fixes_from_the_first_usa_sample():
    lab = L.label(_row("mdl77_2mqf_fcfsale", "TTM Free Cash Flow-to-TTM Sales: It is defined as the trailing 12-month free cash flow divided by sales", cat="Model"))
    assert lab["kind"] == "ratio" and lab["domain"] == "cashflow" and lab["sign"] == "+"      # was flag / accruals −
    lab = L.label(_row("x", "Net net current assets-to-price ratio calculated as current assets minus liabilities divided by price", cat="Model"))
    assert lab["domain"] == "valuation" and lab["sign"] == "+"                                # cheapness, not leverage −
    lab = L.label(_row("x", "Price-to-earnings ratio based on trailing EPS", cat="Model"))
    assert lab["domain"] == "valuation" and lab["sign"] == "-"
    lab = L.label(_row("snt22_neg_mean", "mean negative sentiment score across all articles for the stock", cat="Sentiment"))
    assert lab["domain"] == "sentiment" and lab["sign"] == "-"
    lab = L.label(_row("x", "The probability that the future trend of Diluted Net Income will move up", cat="Other"))
    assert lab["domain"] == "ml-prediction" and lab["sign"] == "unstated"
    lab = L.label(_row("x", "1 day change of a percentile rank that reflects only the Operating Efficiency factors", cat="Model"))
    assert lab["domain"] != "analyst-rating"
    lab = L.label(_row("x", "Mean Absolute Deviation of scaled actual value of Capital Expenditure", cat="Model"))
    assert lab["kind"] == "dispersion" and lab["sign"] == "unstated"
    lab = L.label(_row("x", "Model assessing the risk from correlated movements in assets.", cat="Other"))
    assert lab["unit"] == "unitless"
    lab = L.label(_row("x", "Standardized unexpected earnings; measure of surprise in reported earnings", cat="Model"))
    assert lab["domain"] == "earnings-event" and lab["sign"] == "+"
    lab = L.label(_row("x", "Common Shares Traded - Annual"))
    assert lab["domain"] == "volume-activity"


def test_second_sample_fixes():
    lab = L.label(_row("ppent", "gross property, plant & equipment."))
    assert lab["domain"] == "investment" and lab["sign"] == "unstated"          # a level is a size, no prior
    lab = L.label(_row("x", "value of annual field: Capital Expenditure % Total Assets"))
    assert lab["domain"] == "investment" and lab["sign"] == "-"                 # the ratio carries the prior
    lab = L.label(_row("x", "Weighted six-month percent change in the 18-month forward consensus revenue (SAL) estimate", cat="Analyst"))
    assert lab["domain"] == "analyst-revision" and lab["sign"] == "+"
    lab = L.label(_row("x", "Ratio of short-term (1-week) delta-adjusted options share volume to the stock's share trading volume", cat="Option"))
    assert lab["domain"] == "option"


def test_third_sample_fixes():
    assert L.label(_row("fnd6_optex", "Options Exercisable (000)"))["domain"] != "option"
    assert L.label(_row("x", "Depreciation/amortization represents sum of depreciation, amortization of intangibles and acquisition costs"))["domain"] != "corporate-event-model"
    assert L.label(_row("x", "Fiscal period end date associated with the accounting-adjusted SG&A"))["kind"] == "code"
    assert L.label(_row("x", "The percentage move for earnings date number back 7", cat="Earnings"))["kind"] == "return"
    assert L.label(_row("x", "Aggregate value of all preferred shares issued by the company.", cat="Model"))["unit"] == "currency"


def test_prior_needs_a_description_domain_and_errors_are_dispersion():
    lab = L.label(_row("actual_month_sum_squared_trade_price", "Sum of squared trade prices over the month", cat="Short Interest"))
    assert lab["domain"] == "short-flow" and lab["sign"] == "unstated"          # coarse domain: no prior
    lab = L.label(_row("x", "Mean absolute error of the model's predicted quarterly EBITDA", cat="Model"))
    assert lab["kind"] == "dispersion" and lab["sign"] == "unstated"


def test_audit_fixes_insider_sentiment_polarity_relevance():
    assert L.label(_row("x", "Highest value among top directional significant insider transactions.", cat="Insiders"))["sign"] == "unstated"
    assert L.label(_row("x", "Ratio of insider purchases to sales for all insiders over the last 250 days.", cat="Insiders"))["sign"] == "+"
    assert L.label(_row("x", "Total value of insider sales in the last 90 days", cat="Insiders"))["sign"] == "-"
    assert L.label(_row("x", "Indicator if any chief officer also serves as chairman.", cat="Insiders"))["kind"] == "flag"
    assert L.label(_row("x", "Normalized difference between bullish and bearish trade volumes for professional customers", cat="Option"))["sign"] == "+"
    assert L.label(_row("x", "Score indicating the relevance of social media activity to market impact", cat="Social Media"))["sign"] == "unstated"
    assert L.label(_row("x", "Sum of squared short sale volumes during the period", cat="Short Interest"))["sign"] == "unstated"
    assert L.label(_row("x", "Rating for company culture and values by the reviewer.", cat="Other"))["domain"] == "employee"


def test_sharpe_is_not_a_pe_ratio_and_borrow_demand_is_short_flow():
    assert L.label(_row("x", "Sharpe ratio for the transaction at checkpoint.", cat="Other"))["domain"] != "valuation"
    v = L.label(_row("x", "Borrow demand rating on a 1-10 scale for a stock (1 = relatively low demand)", cat="Short Interest"))
    assert v["domain"] == "short-flow" and v["sign"] == "-"
    assert L.label(_row("x", "Portfolio return from long-biased signals with small price targets", cat="Model"))["domain"] != "analyst-rating"
    assert L.label(_row("x", "Mean analyst target price for the next 12 months", cat="Analyst"))["domain"] == "analyst-rating"


def test_neutral_sentiment_and_net_cash():
    assert L.label(_row("snt23_neut_mean", "Daily mean of the neutral sentiment scores for a stock", cat="Sentiment"))["sign"] == "unstated"
    assert L.label(_row("x", "Net cash position: cash and equivalents minus total debt, scaled by assets"))["sign"] == "+"


def test_vector_axes_and_per_region_structure():
    v = L.label(_row("x", "Event-level sentiment score per headline", cat="News", typ="VECTOR"))
    assert v["vec_role"] == "event-value" and v["vec_reducers"][0] == "vec_avg" and v["event_stream"] == "news-article"
    v = L.label(_row("x", "Number of shares transacted in the event", cat="Insiders", typ="VECTOR"))
    assert v["vec_role"] == "event-count" and v["vec_after"]["vec_sum"] == "count" and v["event_stream"] == "insider-transaction"
    v = L.label(_row("x", "Flag whether the estimate was revised", cat="Analyst", typ="VECTOR"))
    assert v["vec_role"] == "event-flag" and v["vec_after"]["vec_avg"] == "ratio"
    v = L.label(_row("x", "The currency code (integer) of the dividend", cat="Earnings", typ="VECTOR"))
    assert v["vec_role"] == "event-code" and v["vec_reducers"] == ["vec_count"]
    row = _row("mixed", "Ratio of purchases to sales for the top 5 insiders", cat="Insiders", typ="MATRIX")
    row["_by_region"] = {"EUR/d1": {"structure": "MATRIX", "coverage": 0.9, "sparsity": "dense"}, "USA/d1": {"structure": "VECTOR", "coverage": 0.88, "sparsity": "medium"}}
    v = L.label(row)
    assert v["structure"] == "MATRIX" and L.for_region(v, "USA/d1")["structure"] == "VECTOR" and v["vec_role"] == "event-value"


def test_vector_sample_fixes():
    assert L.label(_row("x", "UTC timestamp when the news item was originally published", cat="News", typ="VECTOR"))["kind"] == "code"
    assert L.label(_row("x", "Fiscal quarter to which the reported EPS relates (1-4)", cat="Earnings", typ="VECTOR"))["kind"] == "code"
    v = L.label(_row("x", "Volume Weighted Average Price. Calculated as an average of execution price, weighted by the number of shares", cat="Other", typ="VECTOR"))
    assert v["kind"] == "level" and v["domain"] == "price-level"
    assert L.label(_row("x", "Minutes taken for price to decrease by five percent after event", cat="News", typ="VECTOR"))["domain"] != "valuation"


def test_vector_sample_second_fixes():
    assert L.label(_row("x", "Main session volume weighted average price", cat="News", typ="VECTOR"))["domain"] == "price-level"
    assert L.label(_row("x", "Common Shares Used to Calculate Earnings Per Share - 12 Months Moving", typ="VECTOR"))["domain"] == "size"
    assert L.label(_row("x", "Third measure of profitability consistency.", cat="Other", typ="VECTOR"))["unit"] == "unitless"
    assert L.label(_row("x", "3m growth in number of US-listed ETFs holding the stock", cat="Risk", typ="VECTOR"))["kind"] == "return"
