| total_buy_tx_count_10d | insider-flow | count | event-count | vec_sum/vec_count/vec_max | insider-transaction | sparse | Total number of insider purchase transactions over the past 10 days. |
| currency_type_parent_profit_annual12 | analyst-estimate | code | event-code | vec_count | estimate-submission | dense | Integer currency code for the measure, decoded to the reporting currency by date |
| nws12_mainz_mainvwap | volume-activity | level | event-amount | vec_sum/vec_avg/vec_max | news-article | dense | Main session volume weighted average price |
| thirty_day_moving_average_volume_2 | volume-activity | level | event-amount | vec_sum/vec_avg/vec_max | news-article | dense | 30-day moving average session volume |
| nws31_sourcetimestamp_time | news | code | event-code | vec_count | news-article | dense | UTC timestamp when the news item was originally published |
| minutes_to_five_percent_drop_all | price-level | level | event-value | vec_avg/vec_max/vec_min | news-article | medium | Minutes taken for price to decrease by five percent after event (all sessions). |
| eps_fiscal_quarter_fast_d1 | earnings-event | code | event-code | vec_count | filing-line-item | dense | Fiscal quarter to which the reported EPS relates (1-4) |
| anl44_second_en_capex_value | analyst-estimate | level | event-amount | vec_sum/vec_avg/vec_max | estimate-submission | medium | Numeric value of the CAPEX estimate for the current event |
| maximum_analyst_projection | analyst-estimate | level | event-value | vec_avg/vec_max/vec_min | estimate-submission | medium | Highest forecast value among analyst estimates. |
| fnd72_pit_or_cr_a_ev_to_t12m_ebitda | valuation | level | event-value | vec_avg/vec_max/vec_min | filing-line-item | medium | Periodic enterprise value as a multiple of earnings before interest, taxes, depreciation a |
| nws5_eodclose | price-level | level | event-value | vec_avg/vec_max/vec_min | news-article | dense | Close price of the session |
| fnd6_newqeventv110_csh12q | profitability | ratio | event-value | vec_avg/vec_max/vec_min | filing-line-item | medium | Common Shares Used to Calculate Earnings Per Share - 12 Months Moving |
| shareholder_equity_growth_rate_2 | model-other | ratio | event-value | vec_avg/vec_max/vec_min | event | medium | Rate at which shareholder equity is increasing or decreasing over time. |
| short_term_indicators_score_4 | price-technical | level | event-value | vec_avg/vec_max/vec_min | event | dense | Technical indicators measuring short-term trends. |
| anl44_best_px_bps_ratio | analyst-estimate | ratio | event-value | vec_avg/vec_max/vec_min | estimate-submission | medium | best px bps ratio |
| rolling_industry_group_vwap | price-level | level | event-amount | vec_sum/vec_avg/vec_max | event | dense | Volume Weighted Average Price. Calculated as an average of execution price, weight by numb |
| nws12_mainz_2l | price-level | count | event-count | vec_sum/vec_count/vec_max | news-article | dense | Number of minutes that elapsed before price went up 2 percentage points |
| profitability_consistency_factor_3 | profitability | level | event-amount | vec_sum/vec_avg/vec_max | event | dense | Third measure of profitability consistency. |
| pv20_weight | price-technical | coefficient | event-value | vec_avg/vec_max/vec_min | event | medium | Weight assigned to relationships in the USA Re_Llink dataset. |
| preferred_stock_quarterly_value | payout-yield | level | event-amount | vec_sum/vec_avg/vec_max | filing-line-item | medium | Purchase of common and preferred stock during the quarter (cash outflow for share repurcha |
| total_equity_at_risk | volume-activity | level | event-amount | vec_sum/vec_avg/vec_max | option-trade | sparse | Total value or volume of equity at risk (held or awarded shares and options) |
| nws12_afterhsz_prevday | news | return | event-value | vec_avg/vec_max/vec_min | news-article | medium | Percent change between the previous day's open and close |
| extraordinary_item_quarter | fundamental-other | level | event-amount | vec_sum/vec_avg/vec_max | filing-line-item | sparse | Unrestated quarterly income statement amount for Extraordinary Items and Discontinued Oper |
| percent_price_change_30_seconds_post_new | price-technical | return | event-value | vec_avg/vec_max/vec_min | news-article | dense | Price or return data over the last 30 seconds on day 1 in 'All Filter' module |
| fnd72_pit_or_is_a_is_comprehensive_incom | profitability | level | event-amount | vec_sum/vec_avg/vec_max | filing-line-item | dense | Total comprehensive income including net income and other comprehensive income |
| nws73_globalsent_finhypescore | news | score | event-value | vec_avg/vec_max/vec_min | news-article | dense | Global Financial Hype score at the article level (Acuity) |
| median_surprise_value_revenue_annual12 | earnings-event | return | event-value | vec_avg/vec_max/vec_min | estimate-submission | dense | Median surprise (actual minus median estimate) for annual revenue. |
| oth696_productdesignlifecyclemanagement_ | esg | level | event-value | vec_avg/vec_max/vec_min | event | medium | Positive signal for incorporating environmental considerations into product design and lif |
| main_market_equity_value | size | level | event-value | vec_avg/vec_max/vec_min | news-article | dense | Market capitalization for the company at that session |
| rsk82_znorm_etf_us_pop_g3m | growth | count | event-count | vec_sum/vec_count/vec_max | event | dense | 3m growth in number of US-listed ETFs holding the stock |
