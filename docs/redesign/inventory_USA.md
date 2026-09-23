
# USA_TOP3000_d1 | News  (31 datasets, multiplier 1.2)

## news29 — Significant Developments Data  users=19 alphas=27 fields=12 on_disk=12 types={'VECTOR': 12} subcat=News coverage=0.8088
   This dataset provides concise, real-time summaries of major company news and market-moving events, systematically tagged by topic and significance. Covering a wide range of event types—such as mergers, acquisitions, product launches, regulatory actions, earnings guidance, and management changes—it enables users to filter out noise and focus on impactful developments. Each event is categorized by i
   - company_event_description_text_full      VECTOR The full narrative or detailed description of a company event or news story.
   - company_event_headline_text_full         VECTOR The complete headline or summary text for a company event or news item.
   - company_event_structured_fields_full     VECTOR All structured data fields and tags associated with a company event, including topics, codes, and attributes.
   - event_secondary_topic_code               VECTOR Code representing the second-tier subcategory of the event; must be decoded via overlay
   - event_tertiary_topic_code                VECTOR Third-level event topic/category code (integer), for further sub-classification, must decode
   - nws29_frontpage                          VECTOR Flag indicating if the news item was featured on a Reuters front-page story (1 = yes, 0 = no)
   - nws29_full_frontpage                     VECTOR Binary indicator (1/0) for whether the event/news was featured on Reuters front page
   - nws29_full_significance                  VECTOR Event importance level code: High, Medium, Low relevance to market (must decode)
   - nws29_full_topic1                        VECTOR Code representing the main category of the event; must be decoded via overlay (e.g. M&A, regulatory, etc.)
   - nws29_significance                       VECTOR Level of importance for the development (1 = High, 2 = Medium, 3 = Low)
   - nws29_topic1                             VECTOR Main topic code or parent category of the development
   - nws29_topic2                             VECTOR Second-tier topic code linked (mapped) to the parent topic

## news55 — Intermediate News Data  users=32 alphas=67 fields=6 on_disk=6 types={'VECTOR': 6} subcat=News coverage=1.0
   The Dow Jones and Reuters News Feed dataset is a comprehensive, real-time and historical text news archive that combines coverage from Dow Jones Newswires and Reuters NewsScope. It includes headlines, full story bodies, alerts, updates, and corrections, all tagged with rich metadata such as tickers, topic codes, product codes, and company identifiers. The dataset covers a broad universe of compani
   - mws55_relavence                          VECTOR Number of unique US-listed equities linked to the event (event scope; 1=single-stock, >1=multi-stock)
   - mws55_source1                            VECTOR Primary vendor/source index (into SourceIx) that disseminated the event
   - mws55_source2                            VECTOR Secondary vendor/source index (into SourceIx) that disseminated the event
   - mws55_source3                            VECTOR Tertiary vendor/source index (into SourceIx) that disseminated the event
   - mws55_time                               VECTOR Canonical event timestamp stored as an integer, to be interpreted according to TIME_SOURCE
   - mws55_time_source                        VECTOR Vendor/source index (into SourceIx) specifying which vendor’s timestamp defines TIME and its interpretation

## news51 — Aggregated News Data  users=43 alphas=161 fields=15 on_disk=15 types={'VECTOR': 15} subcat=News coverage=0.9803
   The Bloomberg Real Time News Analytics dataset provides comprehensive, real-time coverage of global financial news, blogs, and sentiment analytics as seen on the Bloomberg Terminal. It aggregates content from Bloomberg’s own newsrooms, TV, radio, and over 30,000 external sources, delivering both raw news text and structured metadata such as tickers, topics, sentiment scores, market-moving indicato
   - mws51_bbgnews_frequency_length           VECTOR Length of the news article in characters or words, per Bloomberg convention
   - mws51_bbgnews_frequency_public_time      VECTOR Publication time of the article in HHMMSS format, vendor-local interpretation
   - mws51_bbgnews_frequency_relevance        VECTOR Vendor-assigned importance or priority score for the article, decoded by local/codebook conventions
   - mws51_bznews_frequency_length            VECTOR Length of the news article, typically measured in characters or words (vendor-specific)
   - mws51_bznews_frequency_public_time       VECTOR Time when the news article was published, in HHMMSS format
   - mws51_bznews_frequency_relevance         VECTOR Vendor-assigned score quantifying the importance or priority of the news article
   - mws51_bznews_location_length             VECTOR Length of the news article, usually measured in number of characters or words, depending on vendor encoding
   - mws51_bznews_location_public_time        VECTOR Time when the article was published (HHMMSS format)
   - mws51_bznews_location_relevance          VECTOR Numerical score or code indicating the importance or relevance of the article, assigned by Benzinga
   - mws51_djnews_frequency_length            VECTOR Length of the article, as measured in characters or words, according to vendor-specific conventions
   - mws51_djnews_frequency_public_time       VECTOR Publication time of the news article in HHMMSS format
   - mws51_djnews_frequency_relevance         VECTOR A vendor-assigned score indicating the news article's perceived importance or priority level, interpreted via 
   - mws51_djnews_location_length             VECTOR Length of the article, typically measured in characters or words, based on vendor encoding
   - mws51_djnews_location_public_time        VECTOR Time the article was published, encoded as integer in HHMMSS format

## news73 — Story by Story Sentiment  users=52 alphas=103 fields=22 on_disk=22 types={'VECTOR': 22} subcat=News coverage=1.0
   This dataset provides sentiment analysis at the individual news story level, offering granular sentiment scores such as positivity, negativity, fear, financial up/down, hype, volatility, certainty, and uncertainty for each news article. The data is available intraday, daily, and hourly, and covers thousands of securities across major global regions. By tracking sentiment shifts in real time and at
   - nws73_djnindustry                        VECTOR Dow Jones news industry tag(s)
   - nws73_djnsubject                         VECTOR Dow Jones news subject tag(s)
   - nws73_entitiescounter                    VECTOR Dictionary of recognized financial entities in the story mapped to their mention counts
   - nws73_entitiessent_certaintypartscr      VECTOR List of per-entity certainty partial sentiment scores, ordered to entitiesCounter_str
   - nws73_entitiessent_fearpartscr           VECTOR List of per-entity fear partial sentiment scores, ordered to entitiesCounter_str
   - nws73_entitiessent_findownpartscr        VECTOR List of per-entity financial down/negative directional partial sentiment scores, ordered to entitiesCounter_st
   - nws73_entitiessent_finhypepartscr        VECTOR Per-entity Financial Hype partial score vector, aligned with entitiesCounter_str
   - nws73_entitiessent_finuppartscr          VECTOR List of per-entity financial up/upgrade partial sentiment scores, ordered to entitiesCounter_str
   - nws73_entitiessent_finvolatilepartscr    VECTOR List of per-entity financial volatility partial sentiment scores, ordered to entitiesCounter_str
   - nws73_entitiessent_negativepartscr       VECTOR List of per-entity negative partial sentiment scores, ordered to entitiesCounter_str
   - nws73_entitiessent_positivepartscr       VECTOR List of per-entity positive partial sentiment scores, ordered to entitiesCounter_str
   - nws73_entitiessent_uncertaintypartscr    VECTOR List of per-entity uncertainty partial sentiment scores, ordered to entitiesCounter_str
   - nws73_globalsent_certaintyscore          VECTOR Global Certainty score at the article level
   - nws73_globalsent_fearscore               VECTOR Document-level fear sentiment score

# USA_TOP3000_d1 | Sentiment  (10 datasets, multiplier 1.4)

## news_sentiment_transfer — Transferred News Sentiment Analytics  users=37 alphas=82 fields=23 on_disk=23 types={'MATRIX': 20, 'VECTOR': 3} subcat=Sentiment coverage=0.947
   This dataset provides sentiment analytics for financial news by transferring sentiment scores from a comprehensive news sentiment source to a major financial news feed using advanced machine learning techniques. It covers global equities and commodities, offering asset-level sentiment classifications (positive, neutral, negative) for news items, along with relevance, novelty, and volume metrics. B
   - news_article_count                       MATRIX Total number of news articles considered for the entity.
   - news_sentiment_score                     VECTOR Overall sentiment value derived from news articles for an entity.
   - normalized_news_article_count            MATRIX Number of news articles normalized for comparison across entities.
   - primary_sentiment_average                MATRIX Mean value of the primary sentiment scores for the entity.
   - primary_sentiment_maximum                MATRIX Maximum value observed in the primary sentiment scores.
   - primary_sentiment_middle_value           MATRIX Median value of the primary sentiment scores for the entity.
   - primary_sentiment_minimum                MATRIX Minimum value observed in the primary sentiment scores.
   - primary_sentiment_skewness_2             MATRIX Skewness statistic of the primary sentiment values for the entity.
   - primary_sentiment_total_2                MATRIX Sum of all primary sentiment values for the entity over the period.
   - primary_sentiment_value                  VECTOR Main sentiment score calculated for the entity from news data.
   - secondary_sentiment_average              MATRIX Mean value of the secondary sentiment scores for the entity.
   - secondary_sentiment_maximum              MATRIX Maximum value observed in the secondary sentiment scores.
   - secondary_sentiment_middle_value         MATRIX Median value of the secondary sentiment scores for the entity.
   - secondary_sentiment_minimum              MATRIX Minimum value observed in the secondary sentiment scores.

## news_transformer_scores — Transformer Based News Sentiment Scores  users=80 alphas=179 fields=315 on_disk=315 types={'MATRIX': 315} subcat=Sentiment coverage=0.7773
   This dataset provides daily sentiment scores derived from financial news articles using a custom transformer-based natural language processing model. Covering a broad universe of equities and ETFs, it quantifies news impact by assigning sentiment values in a structured matrix format, enabling researchers to analyze the relationship between news flow and subsequent price movements. By offering gran
   - negative_sentiment_average_10            MATRIX Average negative sentiment score across all applicable news items for the stock during the main (regular-hours
   - negative_sentiment_average_11            MATRIX Mean negative sentiment score across items for the stock during the post-market session that day (scores 0-1)
   - negative_sentiment_average_12            MATRIX Average negative sentiment score across all pre-market news items for the stock on that day (0 to 1 scale)
   - negative_sentiment_average_2             MATRIX Mean value of negative sentiment scores in main session.
   - negative_sentiment_average_7             MATRIX Average negative sentiment score for the stock during the pre-market session on the day (variant 4), aggregate
   - negative_sentiment_average_8             MATRIX Average negative sentiment score across Benzinga NewsQuantified items for the stock during the main trading se
   - negative_sentiment_average_9             MATRIX Average negative sentiment score for the stock during the post-market session on that day, aggregated across r
   - negative_sentiment_average_post          MATRIX Average (mean) negative sentiment score across Benzinga NewsQuantified items for the stock during the post-mar
   - negative_sentiment_average_pre5          MATRIX Average negative sentiment score across the stock’s pre-market news items for the day (0–1 scale)
   - negative_sentiment_confidence_base       MATRIX Lower bound of the approximately 95% confidence interval for the negative sentiment mean during the main sessi
   - negative_sentiment_confidence_base_2     MATRIX Lower bound of confidence interval for negative sentiment in post-market.
   - negative_sentiment_confidence_base_3     MATRIX Lower bound of the approximate 95% confidence interval for the mean negative sentiment across pre-market news 
   - negative_sentiment_confidence_base_4     MATRIX Lower endpoint of the approximate 95% confidence interval for the mean negative sentiment score for the stock’
   - negative_sentiment_confidence_base_5     MATRIX Approximate 95% confidence interval lower bound for the mean negative sentiment score for the stock during the

## sentiment22 — News Sentiment Scores  users=229 alphas=429 fields=210 on_disk=210 types={'MATRIX': 210} subcat=Sentiment coverage=0.9996
   This dataset provides comprehensive, real-time financial news coverage for North American markets, including equities, commodities, forex, fixed income, and ETFs. It features detailed tagging by ticker, sector, region, and event type, enabling granular analysis of market-moving events such as earnings announcements, analyst rating changes, insider transactions, M&A activity, and regulatory actions
   - snt22_2dts_gen_166                       MATRIX 2-day time series general sentiment .
   - snt22_2dts_sop_154                       MATRIX 2-day time series sum of positive sentiment .
   - snt22_2dts_tuen_150                      MATRIX 2-day time series total of neutral sentiment .
   - snt22_2neg_conf_low                      MATRIX Lower bound of the 95% confidence interval for negative sentiment for the stock-day, computed as neg_mean − 1.
   - snt22_2neg_conf_low_161                  MATRIX negative sentiment lower confidence bound.
   - snt22_2neg_conf_up                       MATRIX Upper bound of the 95% confidence interval for negative sentiment for the stock-day, computed as neg_mean + 1.
   - snt22_2neg_conf_up_151                   MATRIX negative sentiment upper confidence bound.
   - snt22_2neg_max                           MATRIX Maximum negative sentiment score among news articles for the stock on that day
   - snt22_2neg_max_162                       MATRIX negative sentiment maximum value.
   - snt22_2neg_mean                          MATRIX Mean negative sentiment score across all news articles for the stock on that day; higher values indicate more 
   - snt22_2neg_mean_168                      MATRIX negative sentiment mean value.
   - snt22_2neg_median                        MATRIX Median of negative sentiment scores across news articles for the stock on that day
   - snt22_2neg_median_156                    MATRIX negative sentiment median value.
   - snt22_2neg_min                           MATRIX Minimum negative sentiment score among news articles for the stock on that day

## other553 — Financial Opinion Mining  users=239 alphas=445 fields=74 on_disk=74 types={'MATRIX': 33, 'VECTOR': 41} subcat=Sentiment coverage=0.7386
   This dataset focuses on financial opinion mining from various text-based sources such as earnings calls, news, and social media. It aims to extract potential signals by performing deep analysis, considering financial characteristics and correlations among different data sources. The methodology involves advanced feature extraction, sentiment scoring using word embeddings, semi-supervised/transfer 
   - oth553_a_avgnumericpos                   MATRIX Average numerical position in financial text.
   - oth553_a_avgsentlen                      MATRIX Average sentence length in financial text.
   - oth553_a_blamecnt                        MATRIX Count of blame-related terms in financial text.
   - oth553_a_invblamecnt                     MATRIX Count of blame-related terms in financial text.
   - oth553_a_numericcnt                      MATRIX Count of numerical values in financial text.
   - oth553_a_passiveratio                    MATRIX Ratio of passive voice in financial text.
   - oth553_a_polycnt                         MATRIX Count of polysyllabic words in financial text.
   - oth553_a_poscnt                          MATRIX Count of positive terms in financial text.
   - oth553_a_wordcnt                         MATRIX Total word count in financial text.
   - oth553_eps_analyst                       VECTOR Number of analysts providing earnings per share estimates.
   - oth553_eps_answer_ratio                  VECTOR Ratio of answers in earnings call transcripts related to earnings per share.
   - oth553_eps_estvalue                      VECTOR Value of current earnings per share estimates.
   - oth553_eps_isprevspeak                   VECTOR Indicator if there was previous speech related to earnings per share.
   - oth553_eps_poscnt                        VECTOR Positive sentiment count related to earnings per share.

# USA_TOP3000_d1 | Social Media  (4 datasets, multiplier 1.0)

## creator_signal_perf — Finance Creator Prediction Performance  users=40 alphas=78 fields=102 on_disk=102 types={'VECTOR': 102} subcat=Social Media coverage=0.6562
   This dataset aggregates and analyzes stock price predictions made by prominent finance content creators across platforms such as Twitter, YouTube, and select Discord channels. Using AI-driven natural language processing and computer vision, it extracts directional signals (long/short), confidence scores, and performance metrics for each creator and asset. The data includes detailed accuracy statis
   - aggregate_large_target_long_horizon_return VECTOR Aggregate portfolio return using large price targets and extended timeframes.
   - aggregate_large_target_long_horizon_return_2 VECTOR Aggregate portfolio return using large price targets and extended timeframes.
   - aggregate_medium_target_mid_horizon_return VECTOR Aggregate portfolio return using medium price targets and mid-range timeframes.
   - aggregate_medium_target_mid_horizon_return_2 VECTOR Aggregate portfolio return using medium price targets and mid-range timeframes.
   - aggregate_prediction_accuracy_score      VECTOR Weighted score reflecting overall prediction accuracy and volume.
   - aggregate_prediction_accuracy_score_2    VECTOR Weighted score reflecting overall prediction accuracy and volume.
   - aggregate_small_target_quick_horizon_gain VECTOR Portfolio return using small price targets and short time horizons across all assets.
   - aggregate_small_target_quick_horizon_return VECTOR Aggregate portfolio return using small price targets and short timeframes.
   - asset_aggregate_portfolio_return         VECTOR Total percentage return for an asset using all price and time targets.
   - asset_aggregate_portfolio_return_2       VECTOR Total percentage return for an asset using all price and time targets.
   - asset_correct_long_predictions_count     VECTOR Number of correct long-biased predictions for a specific asset.
   - asset_correct_long_predictions_count_2   VECTOR Number of correct long-biased predictions for a specific asset.
   - asset_correct_short_predictions_count    VECTOR Number of correct short-biased predictions for a specific asset.
   - asset_correct_short_predictions_count_2  VECTOR Number of correct short-biased predictions for a specific asset.

## twitter_sentiment_l2 — Twitter Sentiment Signal Aggregation  users=77 alphas=148 fields=95 on_disk=95 types={'MATRIX': 95} subcat=Social Media coverage=0.979
   This dataset provides advanced, aggregated sentiment signals for equities by processing and filtering Twitter activity data. It applies multiple relevance filters to reduce noise and enhance the reliability of sentiment indicators, offering various levels of sentiment aggregation. By leveraging real-time and historical social media sentiment, the dataset helps identify shifts in market mood and po
   - aggregated_sentiment_value_1             MATRIX Aggregated sentiment value derived from social media sources, method 1.
   - aggregated_sentiment_value_10            MATRIX Aggregated sentiment value derived from social media sources, method 10.
   - aggregated_sentiment_value_11            MATRIX Aggregated sentiment value derived from social media sources, method 11.
   - aggregated_sentiment_value_12            MATRIX Aggregated sentiment value derived from social media sources, method 12.
   - aggregated_sentiment_value_13            MATRIX Aggregated sentiment value derived from social media sources, method 13.
   - aggregated_sentiment_value_14            MATRIX Aggregated sentiment value derived from social media sources, method 14.
   - aggregated_sentiment_value_15            MATRIX Aggregated sentiment value derived from social media sources, method 15.
   - aggregated_sentiment_value_16            MATRIX Aggregated sentiment value derived from social media sources, method 16.
   - aggregated_sentiment_value_17            MATRIX Aggregated sentiment value derived from social media sources, method 17.
   - aggregated_sentiment_value_18            MATRIX Aggregated sentiment value derived from social media sources, method 18.
   - aggregated_sentiment_value_2             MATRIX Aggregated sentiment value derived from social media sources, method 2.
   - aggregated_sentiment_value_3             MATRIX Aggregated sentiment value derived from social media sources, method 3.
   - aggregated_sentiment_value_4             MATRIX Aggregated sentiment value derived from social media sources, method 4.
   - aggregated_sentiment_value_5             MATRIX Aggregated sentiment value derived from social media sources, method 5.

## socialmedia8 — Social Media Data for Equity  users=6161 alphas=16311 fields=4 on_disk=4 types={'MATRIX': 4} subcat=Social Media coverage=0.9999
   This dataset provides quantitative sentiment metrics for US equities based on Twitter messages, covering the Russell 3000 universe since December 2011. It includes a suite of S-Factors such as S-Score (normalized sentiment), S-Volume (tweet volume), S-Dispersion (source diversity), S-Buzz (abnormal activity), and S-Delta (sentiment trend), all calculated using both unweighted and exponentially wei
   - snt_social_value                         MATRIX Z-score of sentiment
   - snt_social_value_fast_d1                 MATRIX Z-score of sentiment
   - snt_social_volume                        MATRIX Normalized tweet volume
   - snt_social_volume_fast_d1                MATRIX Normalized tweet volume

## socialmedia12 — Sentiment Data for Equity  users=23080 alphas=57531 fields=18 on_disk=18 types={'VECTOR': 6, 'MATRIX': 12} subcat=Social Media coverage=0.9855
   This dataset aggregates and analyzes social media posts and news articles related to financial markets, covering thousands of sources and several years of historical data. It quantifies market sentiment and buzz for individual assets, sectors, and indices using advanced natural language processing and machine learning techniques. The data includes sentiment scores, buzz indicators, and trading sig
   - scl12_alltype_buzzvec                    VECTOR sentiment volume
   - scl12_alltype_sentvec                    VECTOR sentiment
   - scl12_alltype_typevec                    VECTOR instrument type index
   - scl12_buzz                               MATRIX relative sentiment volume
   - scl12_buzz_fast_d1                       MATRIX relative sentiment volume
   - scl12_buzzvec                            VECTOR Vector representing the volume of social media sentiment/mentions related to the instrument
   - scl12_sentiment                          MATRIX sentiment
   - scl12_sentiment_fast_d1                  MATRIX sentiment
   - scl12_sentvec                            VECTOR Vector representing the sentiment score (bullish/bearish/neutral) derived from social media data for the instr
   - scl12_typevec                            VECTOR Vector containing the type indices identifying the categories of instruments in the dataset
   - snt_buzz                                 MATRIX Negative relative sentiment volume measure for current day, with missing values filled as 0
   - snt_buzz_bfl                             MATRIX Negative relative sentiment volume measure for current day, with missing values filled as 1
   - snt_buzz_bfl_fast_d1                     MATRIX Negative relative sentiment volume measure for current day, with missing values filled as 1
   - snt_buzz_fast_d1                         MATRIX Negative relative sentiment volume measure for current day, with missing values filled as 0

# USA_TOP3000_d1 | Insiders  (5 datasets, multiplier 1.1)

## insider_agg_matrix — Smart Insider Transaction Aggregates  users=29 alphas=39 fields=17 on_disk=17 types={'MATRIX': 17} subcat=Insider Data coverage=0.7716
   This dataset provides a structured, matrix-format view of insider trading activity, where individual transactions by company insiders are aggregated and filtered using advanced methodologies. By summarizing key metrics such as average shares bought or sold, and applying smart filters to highlight the most relevant transactions, the dataset enables researchers and investors to efficiently identify 
   - directional_indicator_2                  MATRIX A metric indicating the overall direction or bias of enhanced insider activity.
   - directional_significant_value_1          MATRIX Highest value among directional significant insider transactions.
   - directional_significant_value_2          MATRIX Second highest value among directional significant insider transactions.
   - directional_significant_value_3          MATRIX Third highest value among directional significant insider transactions.
   - directional_significant_value_4          MATRIX Fourth highest value among directional significant insider transactions.
   - significant_value_1                      MATRIX Value of the most significant insider transaction.
   - significant_value_2                      MATRIX Value of the second most significant insider transaction.
   - significant_value_3                      MATRIX Value of the third most significant insider transaction.
   - significant_value_4                      MATRIX Value of the fourth most significant insider transaction.
   - top_directional_significant_value_1      MATRIX Highest value among top directional significant insider transactions.
   - top_directional_significant_value_2      MATRIX Second highest value among top directional significant insider transactions.
   - top_directional_significant_value_3      MATRIX Third highest value among top directional significant insider transactions.
   - top_directional_significant_value_4      MATRIX Fourth highest value among top directional significant insider transactions.
   - top_significant_value_1                  MATRIX Highest value among top significant insider transactions.

## board_gov_stats — US Board Governance and Leadership Metrics  users=85 alphas=177 fields=46 on_disk=46 types={'MATRIX': 46} subcat=Insider Data coverage=0.9197
   This dataset provides daily, firm-level statistics on the structure, composition, and dynamics of company boards and senior management teams for publicly listed US companies. It aggregates detailed person- and board-level data into metrics such as board size, independence, gender diversity, director and executive tenure, turnover rates, and network connectivity (interlocks with other firms). Addit
   - aggregate_external_connections           MATRIX Total number of external company connections across board and management.
   - board_departure_rate_1y_board            MATRIX Proportion of board members who left in the past year.
   - board_departure_rate_3m_management       MATRIX Proportion of management members who left in the past three months.
   - board_departure_rate_6m_management       MATRIX Proportion of management members who left the board in the past six months.
   - board_external_connection_count          MATRIX Total number of external company connections held by board members.
   - board_join_rate_1y_board                 MATRIX Proportion of board members who joined in the past year.
   - board_join_rate_3m_management            MATRIX Proportion of management members who joined the board in the past three months.
   - board_join_rate_6m_management            MATRIX Proportion of management members who joined the board in the past six months.
   - board_member_count_2                     MATRIX Number of board members in the company.
   - ceo_chairman_duality_flag                MATRIX Indicator if the CEO also serves as chairman of the board.
   - ceo_gender_flag                          MATRIX Binary indicator for CEO gender (1=male, 0=female).
   - ceo_tenure_days                          MATRIX Number of days the CEO has held the CEO position.
   - chairman_tenure_days                     MATRIX Number of days the chairman has held the chairman position.
   - chief_officer_chairman_flag              MATRIX Indicator if any chief officer also serves as chairman.

## insiders4 — Edgar forms data  users=398 alphas=1422 fields=16 on_disk=16 types={'MATRIX': 1, 'VECTOR': 15} subcat=Insider Data coverage=0.6374
   This dataset contains comprehensive SEC filing information sourced from EDGAR, including annual and quarterly reports (10-K, 10-Q), insider transactions (Form 4), institutional holdings (13F), IPO registrations (S-1), and other regulatory filings. It provides detailed metadata such as company identifiers, transaction details, ownership changes, and event classifications. By analyzing these filings
   - board_membership_indicator               MATRIX Flag indicating whether the individual is a member of the company’s board.
   - executive_department_label               VECTOR A label or tag indicating the department associated with the executive.
   - executive_position_label                 VECTOR A label or tag describing the executive’s position or function.
   - insd4_bonus                              VECTOR Bonus compensation amount
   - insd4_frequency_reportlen                VECTOR Length of the 8-K report
   - insd4_location_reportlen                 VECTOR Length of the 8-K report
   - insd4_nonequity_plan                     VECTOR Non-equity incentive plan compensation amount
   - insd4_option_awards                      VECTOR Value of option awards granted
   - insd4_other                              VECTOR Other information
   - insd4_pension_nqdc                       VECTOR Change in pension value and nonqualified deferred compensation earnings
   - insd4_quarter_value                      VECTOR Quarter value information
   - insd4_salary                             VECTOR Base salary amount
   - insd4_stock_awards                       VECTOR Value of stock awards granted
   - insd4_total                              VECTOR Total compensation amount

## insiders1 — Global Insider Trading Data  users=958 alphas=3685 fields=45 on_disk=45 types={'MATRIX': 26, 'VECTOR': 19} subcat=Insider Data coverage=0.601
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RIC) and Bloomberg Identifiers (BBID), serving as a cross-reference for security identifiers across two major financial data platforms. It is essential for researchers, portfolio managers, and quantitative analysts who need to integrate or reconcile data from both Refinitiv and Bloomberg sources. By enabling accurate a
   - buy_to_sell_amount_ratio_1mo             MATRIX Ratio of insider purchase value to sell value over the past month.
   - buy_to_sell_amount_ratio_1wk             MATRIX Ratio of insider purchase value to sell value over the past week.
   - buy_to_sell_amount_ratio_1yr             MATRIX Ratio of insider purchase value to sell value over the past year.
   - buy_to_sell_amount_ratio_2mo             MATRIX Ratio of insider purchase value to sell value over the past two months.
   - buy_to_sell_amount_ratio_2wk             MATRIX Ratio of insider purchase value to sell value over the past two weeks.
   - buy_to_sell_amount_ratio_6mo             MATRIX Ratio of insider purchase value to sell value over the past half year.
   - buy_to_sell_amount_ratio_qtr             MATRIX Ratio of insider purchase value to sell value over the past quarter.
   - buy_to_total_amount_ratio_1mo            MATRIX Ratio of insider purchase value to total transaction value over the past month.
   - buy_to_total_amount_ratio_1wk            MATRIX Ratio of insider purchase value to total transaction value over the past week.
   - buy_to_total_amount_ratio_1yr            MATRIX Ratio of insider purchase value to total transaction value over the past year.
   - buy_to_total_amount_ratio_2mo            MATRIX Ratio of insider purchase value to total transaction value over the past two months.
   - buy_to_total_amount_ratio_2wk            MATRIX Ratio of insider purchase value to total transaction value over the past two weeks.
   - buy_to_total_amount_ratio_6mo            MATRIX Ratio of insider purchase value to total transaction value over the past half year.
   - buy_to_total_amount_ratio_qtr            MATRIX Ratio of insider purchase value to total transaction value over the past quarter.

# USA_TOP3000_d1 | Short Interest  (6 datasets, multiplier 1.1)

## us_short_sale — US Equity Short Sale Volume  users=56 alphas=94 fields=4 on_disk=4 types={'MATRIX': 4} subcat=Short Sale Models coverage=1.0
   This dataset provides comprehensive daily and monthly records of short sale activity across major US equity markets, including aggregate short sale volumes and total trading volumes for all exchange-listed securities. It includes detailed trade-by-trade data such as transaction time, price, and share count for each short sale, enabling granular analysis of market sentiment and trading behavior. By
   - aggregate_executed_trade_share_count     MATRIX Total number of shares traded during regular trading hours.
   - executed_short_trade_share_count         MATRIX Total number of shares sold short during regular trading hours.
   - reported_short_sale_share_quantity       MATRIX Aggregate quantity of shares sold short across all included markets.
   - reported_total_trade_share_quantity      MATRIX Aggregate quantity of shares traded across all included markets.

## shortinterest29 — Group Short Sale Data  users=92 alphas=179 fields=32 on_disk=32 types={'MATRIX': 32} subcat=Short Sale Models coverage=0.8838
   This dataset provides detailed records of short sale activity for US-listed equities, including daily and monthly short sale volumes, execution times, and trade sizes for each security. It captures the number of shares sold short, whether the trades are exempt from certain regulations, and the market center where each trade occurred. By analyzing patterns in short sale volume and timing, investors
   - actual_month_short_volume                MATRIX Calendar-month aligned count of short sale trade events aggregated across all venues for a specific security
   - actual_month_short_volume_count          MATRIX Monthly count of volume records for the true calendar month
   - actual_month_sum_short_volume            MATRIX Monthly total short sale volume for the true calendar month
   - actual_month_sum_squared_short_volume    MATRIX Monthly sum of squared short sale volumes for the true calendar month
   - actual_month_sum_squared_trade_price     MATRIX Monthly sum of squared short sale principal values for the true calendar month
   - actual_month_sum_trade_price             MATRIX Monthly total principal value for the true calendar month
   - actual_month_sum_trade_price_times_volume MATRIX Monthly aggregate of short sale principal value multiplied by volume for the true calendar month
   - actual_month_trade_price_count           MATRIX Monthly count of principal value records for the true calendar month
   - amex_actual_month_short_volume           MATRIX Calendar-month aligned count of short sale trades/events for AMEX venue
   - amex_short_volume                        MATRIX Raw count of short sale trades/events for AMEX venue in the reporting period
   - arca_actual_month_short_volume           MATRIX Shares sold short on ARCA for the true calendar month.
   - arca_short_volume                        MATRIX Total shares sold short in trades executed on ARCA.
   - short_sale_volume                        MATRIX Total number of shares sold short in the trade.
   - short_volume_count                       MATRIX Count of volume records in the period

## short_interest_pred — Short Interest Forecast Signals  users=96 alphas=199 fields=10 on_disk=10 types={'MATRIX': 10} subcat=Short Sale Models coverage=0.9987
   This dataset provides predictive signals for short interest levels in equities, aiming to forecast tomorrow’s short interest using a formulaic approach. The predictions are derived from historical short interest data combined with price and volume information, allowing for timely insights into potential changes in market sentiment and short-selling activity. By anticipating shifts in short interes
   - prior_short_interest_predicted_change    MATRIX The predicted change in short interest from the previous period.
   - prior_short_interest_predicted_value     MATRIX The predicted value of short interest for the previous period based on historical data.
   - prior_short_interest_surprise_amount     MATRIX The magnitude of deviation between actual and predicted short interest for the previous period.
   - prior_short_interest_surprise_ratio      MATRIX The ratio of actual to predicted short interest for the previous period, indicating deviation.
   - prior_short_interest_surprise_value      MATRIX The difference between actual and predicted short interest for the previous period.
   - short_interest_predicted_change          MATRIX The predicted change in short interest for the current period.
   - short_interest_predicted_value           MATRIX Model’s next-day forecast of short interest in market value (dollars)
   - short_interest_surprise_amount           MATRIX The difference between actual and predicted short interest for the current period.
   - short_interest_surprise_ratio            MATRIX The ratio of actual to predicted short interest for the current period.
   - short_interest_surprise_value            MATRIX The difference between actual and predicted short interest for the current period.

## shortinterest24 — Short Sale Circuit Breaker Data  users=167 alphas=434 fields=1 on_disk=1 types={'MATRIX': 1} subcat=Short Sale Models coverage=0.2573
   This dataset tracks stocks subject to trading restrictions under Regulation SHO, specifically those that have triggered short sale restrictions due to excessive short selling activity. It includes details such as trigger times, market categories, turnover ratios, and in-sample returns, providing a comprehensive view of short interest dynamics and regulatory interventions. By analyzing these events
   - shrt24_triggertime_2                     MATRIX Time when the short sale circuit breaker was triggered for the security (D1 - previous day)

# USA_TOP3000_d1 | Imbalance  (1 datasets, multiplier 1.0)

## imbalance5 — Oil Price Resilience Scores  users=1364 alphas=3863 fields=2 on_disk=2 types={'MATRIX': 2} subcat=Imbalance Models coverage=0.8669
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RIC) and Bloomberg Identifiers (BBID), facilitating seamless integration and cross-referencing of securities across two major financial data platforms. By enabling accurate identification and linkage of securities, the dataset supports portfolio managers, analysts, and researchers in consolidating data from multiple so
   - imb5_mktcap                              MATRIX Market capitalization of security in regional currency units
   - imb5_score                               MATRIX SHIELD-OIL composite score (0-1) indicating resilience/advantage in oil shock regimes

# USA_TOP3000_d1 | Institutions  (4 datasets, multiplier 1.0)

## fund_holdings_panel — Global Institutional Fund Holdings  users=111 alphas=261 fields=30 on_disk=30 types={'VECTOR': 30} subcat=Ownership Models coverage=0.996
   This dataset provides daily, account-level insights into the holdings and transactions of major institutional investors, including mutual funds, ETFs, asset managers, pension funds, and insurance companies. It features detailed tables on daily trades, holdings, and the size of the investment account panel, with metrics such as conviction holdings, boundary trades, significant transactions, and con
   - boundary_transaction_total               VECTOR Number of boundary transactions (new position initiations or complete liquidations) across all fund accounts o
   - boundary_transaction_total_active        VECTOR Number of boundary transactions across fund accounts (introductions of new positions or complete liquidations)
   - boundary_transaction_usd_value           VECTOR Total USD value of boundary transactions (entries into new positions or complete liquidations) across all acco
   - boundary_transaction_usd_value_active    VECTOR Dollar value of boundary transactions in USD
   - herfindahl_index_holdings                VECTOR Herfindahl-Hirschman Index of holdings concentration based on account weights
   - herfindahl_index_holdings_active         VECTOR Herfindahl-Hirschman Index of holdings weights across accounts (0 to 1)
   - herfindahl_index_transactions            VECTOR Herfindahl-Hirschman Index of trade value concentration across transacting accounts (0 to 1, higher means more
   - herfindahl_index_transactions_active     VECTOR Herfindahl-Hirschman Index concentration measure based on distribution of transaction value across accounts
   - holder_account_total                     VECTOR Number of distinct investment accounts or funds holding the ISIN on the date
   - holder_account_total_active              VECTOR Number of distinct accounts holding this ISIN on the date
   - holding_value_distribution_score         VECTOR Concentration of holdings value across accounts, a custom crowding metric
   - holding_value_distribution_score_active  VECTOR Concentration of holdings value across accounts; higher values indicate more crowding among holders
   - large_trade_count_50bps                  VECTOR Number of transactions where the trade value exceeds 0.5% of the respective fund’s AUM
   - large_trade_count_50bps_active           VECTOR Count of transactions with transaction value greater than 0.5% of the fund’s AUM

## institutions20 — Short Sale Volume Data  users=456 alphas=1004 fields=17 on_disk=17 types={'MATRIX': 17} subcat=Ownership Models coverage=0.9804
   This dataset provides detailed information on short sale trading activity for U.S. equities, including metrics such as short volume, short exempt volume, total trade volume, and trade-level details like symbol, date, time, size, and price. The data is sourced from multiple trade reporting facilities and covers regular trading hours, offering a comprehensive view of short selling across major U.S. 
   - aggregate_trade_share_count_regular_hours MATRIX Total shares traded during regular market hours for the symbol on the reported facility, including both long a
   - executed_short_position_share_sum        MATRIX Shares executed as short sales during regular market hours, including those marked short sale exempt
   - exempt_short_trade_share_total           MATRIX Shares within ShortVolume executed under a short sale exemption during regular market hours
   - inst20_ra_sev                            MATRIX No field description
   - inst20_ra_sv                             MATRIX No field description
   - inst20_ra_tv                             MATRIX No field description
   - inst20_sq_market                         MATRIX Reporting Facility identifier
   - inst20_sq_sev                            MATRIX Total shares executed under a short sale exemption during regular trading hours, reported to the FINRA/Nasdaq 
   - inst20_sq_sv                             MATRIX Total shares executed as short sales during regular trading hours, including those marked as short sale exempt
   - inst20_sq_tv                             MATRIX Total shares traded (all executions, short and long) during regular trading hours, reported to the FINRA/Nasda
   - inst20_yx_market                         MATRIX Reporting Facility identifier
   - inst20_yx_sev                            MATRIX Shares reported as short-sale exempt trades during regular trading hours on the FINRA/NYSE TRF (a subset of Sh
   - inst20_yx_sv                             MATRIX Total shares reported as short sales during regular trading hours on the FINRA/NYSE TRF, including the subset 
   - inst20_yx_tv                             MATRIX Total shares of all executed trades (short and long) during regular trading hours reported to the FINRA/NYSE T

## institutions18 — Ownership Model Data  users=590 alphas=2194 fields=17 on_disk=17 types={'VECTOR': 2, 'MATRIX': 15} subcat=Ownership Models coverage=0.8055
   This dataset provides comprehensive global coverage of equity ownership by institutions, mutual funds, and insiders/stakeholders, with detailed position-level data for each security and holder. It includes both summary and granular holdings, sourced from regulatory filings such as SEC 13F, UK Share Register, and other international disclosures. The data tracks current and historical positions, mar
   - equity_fund_reported_shares_count        VECTOR Amount of holdings (e.g., shares or units) shown in a specific stock fund report
   - fund_equity_reported_shares_held         VECTOR Holdings (share or unit amount) in the fund stock report
   - fund_report_date_association             MATRIX Mapping or association between funds and their respective report dates.
   - inst18_fundownershipv2_cur_holding       MATRIX Current number of shares held by the fund
   - inst18_fundownershipv2_cur_mv            MATRIX Current market value of shares held by the fund
   - inst18_fundownershipv2_num_held          MATRIX Number of shareholding positions (distinct funds or entities) reported for the security
   - inst18_fundownershipv2_pct_held          MATRIX Current percentage of outstanding shares held by the fund
   - inst18_fundownershipv2_pre_holding       MATRIX Previous number of shares held by the fund
   - inst18_fundownershipv2_vm_erp            MATRIX Previous market value of shares held by the fund
   - inst18_instownership_cur_holding         MATRIX Number of shares currently held by the entity at the current reported time
   - inst18_instownership_cur_mv              MATRIX Total market value of shares currently held by the entity at the reported time
   - inst18_instownership_num_held            MATRIX Total number of entities (holders) that own the security at the reported time
   - inst18_instownership_pct_held            MATRIX Percentage of total shares outstanding held by all filing entities in aggregate
   - inst18_instownership_pre_holding         MATRIX Number of shares held by the entity at the previous (last reported) time

## institutions6 — Institutions and Beneficial Stake Ownership  users=699 alphas=3224 fields=22 on_disk=22 types={'MATRIX': 22} subcat=Ownership Models coverage=1.0
   This dataset provides comprehensive information on global equity ownership by institutions, mutual funds, and beneficial stakeholders. It includes current and historical holdings data from over 50,000 portfolios and companies across 70 countries, with more than 10 years of history. Key fields cover shares held, percent of shares outstanding, report dates, aggregated statistics, and investor profil
   - aggregate_equity_value_all_owners        MATRIX Aggregate dollar value of shares of the security held by all owners, with duplication between child and parent
   - aggregate_equity_value_institutions      MATRIX Aggregate dollar value of shares of the security currently held by all institutional investors at the reportin
   - aggregate_share_count_all_owners         MATRIX Aggregate number of shares of the security held by all owners, with duplication between child and parent owner
   - aggregate_share_count_institutions       MATRIX Total number of shares of the security currently held by all institutional investors at the reporting date
   - count_institutional_buyers_security      MATRIX Number of institutional investors who purchased shares of the security during the reporting period
   - count_institutional_holders_security     MATRIX Number of institutional investors currently holding shares (with holdings greater than zero) for the security 
   - count_institutional_sellers_security     MATRIX Number of institutional investors who sold shares of the security during the reporting period
   - inst6_num_of_institutional_buyers        MATRIX Number of institutional investors who purchased shares of the security during the reporting period
   - inst6_num_of_institutional_holders       MATRIX Number of institutional investors holding shares greater than zero in the security at the given time
   - inst6_num_of_institutional_sellers       MATRIX Number of institutional investors who sold shares of the security during the reporting period
   - inst6_num_of_institutional_shares_bought MATRIX Total number of shares of the security purchased by institutional investors during the reporting period
   - inst6_num_of_institutional_shares_sold   MATRIX Total number of shares of the security sold by institutional investors during the reporting period
   - inst6_total_share_held_by_owners         MATRIX Aggregate number of shares of the security held by all owners with duplicate holdings between parent and child
   - inst6_total_shares_held_by_institutions  MATRIX Aggregate number of shares of the security currently held by institutional investors

# USA_TOP3000_d1 | Earnings  (9 datasets, multiplier 1.2)

## earnings_sent_matrix — Global Earnings Call Sentiment Matrix  users=191 alphas=492 fields=7 on_disk=7 types={'MATRIX': 7} subcat=Earnings Estimates coverage=0.7
   This dataset provides a structured, matrix-format aggregation of global company earnings call transcripts, focusing on sentiment and topic analytics. It leverages advanced natural language processing to extract and quantify positive, neutral, and negative sentiment probabilities from management presentations and Q&A sessions, across over 200 thematic topics. The data is filtered and enhanced with 
   - intraday_delay_indicator                 MATRIX A code indicating whether the data is updated intraday or with a delay.
   - likelihood_of_neutral_tone               MATRIX Model-estimated probability [0–1] that the intraday transcript slice has neutral sentiment; sums with the othe
   - negative_sentiment_probability_3         MATRIX Model-estimated probability [0–1] that the intraday transcript slice has negative sentiment; designed to sum t
   - overall_sentiment_score                  MATRIX Categorical sentiment label derived by argmax over Prob_POS, Prob_NTR, Prob_NEG; typically -1 negative, 0 neut
   - positive_sentiment_probability_3         MATRIX Model-estimated probability [0–1] that the intraday transcript slice has positive sentiment; part of the three
   - sentiment_weighting_method1              MATRIX Aggregate transcript tone score computed via method 1; higher values indicate more positive sentiment for the 
   - sentiment_weighting_method2              MATRIX Alternative aggregate transcript tone score computed via method 2; higher values indicate more positive sentim

## earnings_chart_dl — Deep Learning Earnings Chart Predictions  users=234 alphas=484 fields=100 on_disk=100 types={'MATRIX': 100} subcat=Earnings Estimates coverage=0.991
   This dataset leverages deep learning techniques to analyze financial time series charts, specifically focusing on earnings calendar events. By converting historical price and earnings data into images, it utilizes pre-trained convolutional neural networks to predict future stock returns over multiple horizons. The dataset includes quantile-based rankings, probability assignments, and risk-adjusted
   - close_return_quantile_1_1day             MATRIX Continuous predicted 1-day forward close-to-close return from the earnings calendar CNN prediction model
   - high_return_quantile_1_1day              MATRIX Assignment of the stock to quantile 1 based on predicted high-to-high 1-day return.
   - likelihood_quantile_5_group_0_50day_return MATRIX Log-probability confidence (log-softmax) of the stock-date belonging to quantile 0 (0-based) out of 5 quantile
   - likelihood_quantile_5_group_2_50day_return MATRIX Log-probability confidence (log-softmax) of the stock-date belonging to quantile 2 (0-based) out of 5 quantile
   - low_return_quantile_1_1day               MATRIX Assignment of the stock to quantile 1 based on predicted low-to-low 1-day return.
   - open_return_quantile_1_1day              MATRIX Assignment of the stock to quantile 1 based on predicted open-to-open 1-day return.
   - prob_quantile_2_bucket_0_10day_return    MATRIX Log-probability (log-softmax confidence) that the stock-date belongs to the bottom half quantile (index 0) in 
   - prob_quantile_2_bucket_0_20day_return    MATRIX Log-probability that the stock-date belongs to the lower half (quantile 0) in a 2-quantile forward return pred
   - prob_quantile_2_bucket_0_50day_return    MATRIX Log-probability confidence (log-softmax) of the stock-date belonging to quantile 0 (0-based) out of 2 quantile
   - prob_quantile_2_bucket_0_5day_return     MATRIX Log-probability (log-softmax) confidence that the stock is in the 0th quantile bucket (lowest half) for 2-way 
   - prob_quantile_2_bucket_0_5day_volatility MATRIX Log-probability of belonging to the bottom half quantile (quantile 0 of 2) for 5-day forward return prediction
   - prob_quantile_2_bucket_1_10day_return    MATRIX Log-probability confidence for being in the top half quantile (quantile 1 out of 2) for 10-day forward return 
   - prob_quantile_2_bucket_1_20day_return    MATRIX Log-probability (log-softmax confidence) that the stock-date belongs to the upper half (quantile 1) in a 2-qua
   - prob_quantile_2_bucket_1_50day_return    MATRIX Log-probability confidence (log-softmax) of the stock-date belonging to quantile 1 (0-based) out of 2 quantile

## earnings5 — Earnings Date Breaks  users=287 alphas=900 fields=5 on_disk=5 types={'VECTOR': 5} subcat=Earnings Estimates coverage=0.9396
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RICs) and Bloomberg IDs for financial securities. It consolidates identifier information from both Bloomberg and Refinitiv, enabling users to cross-reference securities across these two major data platforms. The mapping is essential for integrating and reconciling datasets that use different identifier systems, facilit
   - earnings_date_deviation_score            VECTOR Z-score of the confirmed date versus issuer’s last 5 years for the same quarter: (confirmed date − mean) / sta
   - ern5_change_time                         VECTOR Time when the change was recorded (HHMMSS)
   - ern5_fiscal_year                         VECTOR Reporting fiscal year for the earnings period
   - ern5_total_days_changed                  VECTOR Signed number of days between the current scheduled earnings date and the first date projected by WSH for the 
   - event_time_marker                        VECTOR Time-of-day classification for the announcement: Before Market=0, During Market=1, After Market=2, Unspecified

## earnings27 — Earnings Update Emails Data  users=392 alphas=1496 fields=14 on_disk=14 types={'VECTOR': 14} subcat=Earnings Estimates coverage=0.2734
   This dataset compiles analyst communications following company earnings releases, focusing on the sentiment and key financial metrics discussed in these emails. By classifying messages based on keywords such as guidance, EBIT, EBITDA, and EPS, and providing an overall sentiment score for each email, the dataset offers a unique perspective on market reactions and analyst outlooks. The information c
   - ern27_atlas_unit_name                    VECTOR Atlas unit name
   - ern27_clean_content                      VECTOR Cleaned email body content with stop words removed and normalized
   - ern27_clean_subject                      VECTOR cleaned subject of the email with removing the stop words
   - ern27_earnings                           VECTOR Count of words related to earnings themes, e.g., earning, earnings, profit, income
   - ern27_email_content                      VECTOR Raw email body content as captured, unprocessed
   - ern27_email_from                         VECTOR raw encoded text for the sender of the email
   - ern27_email_received                     VECTOR UTC timestamp when the system or vendor received the email
   - ern27_expectations                       VECTOR Count of words related to expectations, e.g., expectations, expected, consensus, expectation
   - ern27_is_multiple_ticker                 VECTOR is there different ticker for the company
   - ern27_negative                           VECTOR Count of negative sentiment words in the email subject/body, e.g., sell, miss, lower, weak, weaker
   - ern27_neutral                            VECTOR Count of neutral or mixed sentiment words, e.g., inline, neutral, mixed
   - ern27_positive                           VECTOR Count of positive sentiment words in the email subject/body, e.g., buy, beat, strong, solid, better, ahead, hi
   - ern27_revenue                            VECTOR Count of words related to revenue themes, e.g., sales, revenue, revenues, topline
   - ern27_vendor_bank                        VECTOR the sender entity of the email

# USA_TOP3000_d1 | Option  (6 datasets, multiplier 1.3)

## order_flow_imb — Institutional Order Flow Imbalance  users=79 alphas=223 fields=120 on_disk=120 types={'MATRIX': 120} subcat=Option Analytics coverage=0.8092
   This dataset provides a comprehensive view of order flow imbalances across various market participant classes, including firms, brokers, dealers, market makers, customers, and professional customers. It quantifies the net difference between bullish and bearish option trading activity for each group, using normalized metrics based on the volume and number of trades. By distinguishing between buy an
   - broker_dealer_bearish_contracts_noto     MATRIX Total contracts from selling calls and buying puts by brokers and dealers, showing negative sentiment.
   - broker_dealer_bearish_trade_count        MATRIX Number of bearish trades (selling calls and buying puts) by brokers and dealers.
   - broker_dealer_bearish_trade_count_ise    MATRIX Number of bearish trades (selling calls and buying puts) by brokers and dealers, based on ISE data.
   - broker_dealer_bearish_trade_count_noto   MATRIX Number of bearish trades (selling calls and buying puts) by brokers and dealers, based on NOTO data.
   - broker_dealer_bearish_trade_count_otm    MATRIX Number of bearish trades (selling calls and buying puts) by brokers and dealers, for out-of-the-money contract
   - broker_dealer_bearish_vol                MATRIX Total volume of bearish trades (selling calls and buying puts) by brokers and dealers.
   - broker_dealer_bearish_vol_ise            MATRIX Total volume of bearish trades (selling calls and buying puts) by brokers and dealers, based on ISE data.
   - broker_dealer_bearish_vol_otm            MATRIX Total volume of bearish trades (selling calls and buying puts) by brokers and dealers, for out-of-the-money co
   - broker_dealer_bullish_contracts_noto     MATRIX Total contracts from buying calls and selling puts by brokers and dealers, showing positive sentiment.
   - broker_dealer_bullish_trade_count        MATRIX Number of bullish trades (buying calls and selling puts) by brokers and dealers.
   - broker_dealer_bullish_trade_count_ise    MATRIX Number of bullish trades (buying calls and selling puts) by brokers and dealers, based on ISE data.
   - broker_dealer_bullish_trade_count_otm    MATRIX Number of bullish trades (buying calls and selling puts) by brokers and dealers, for out-of-the-money contract
   - broker_dealer_bullish_trades_noto        MATRIX Count of trades from buying calls and selling puts by brokers and dealers, reflecting positive sentiment.
   - broker_dealer_bullish_vol                MATRIX Total volume of bullish trades (buying calls and selling puts) by brokers and dealers.

## option3 — Equity Options Moneyness Aggregates  users=214 alphas=372 fields=20 on_disk=20 types={'MATRIX': 20} subcat=Option coverage=0.8801
   This dataset provides intermediate, derived metrics on implied volatility and pricing for US equity options, sourced from comprehensive historical options data. It includes key option sensitivities (Greeks), interpolated volatility surfaces, and standardized pricing information, enabling detailed analysis of market expectations and risk sentiment. By capturing nuanced changes in implied volatility
   - opt3_openintecallatm                     MATRIX Daily aggregated open interest for at-the-money call options for the stock
   - opt3_openintecallitm                     MATRIX Daily aggregated open interest for in-the-money call options for the stock
   - opt3_openintecallotm                     MATRIX Daily aggregated open interest for out-of-the-money call options for the stock
   - opt3_openinteputatm                      MATRIX Daily aggregated open interest for at-the-money put options for the stock
   - opt3_openinteputitm                      MATRIX Daily aggregated open interest for in-the-money put options for the stock
   - opt3_openinteputotm                      MATRIX Daily aggregated open interest for out-of-the-money put options for the stock
   - opt3_volcallatm                          MATRIX Implied volatility of at-the-money call options
   - opt3_volcallitm                          MATRIX Implied volatility of in-the-money call options
   - opt3_volcallotma                         MATRIX Implied volatility of out-of-the-money call options (ask)
   - opt3_volcallotmb                         MATRIX Implied volatility of out-of-the-money call options (bid)
   - opt3_volputatm                           MATRIX Implied volatility of at-the-money put options
   - opt3_volputitm                           MATRIX Implied volatility of in-the-money put options
   - opt3_volputotma                          MATRIX Implied volatility of out-of-the-money put options (ask)
   - opt3_volputotmb                          MATRIX Implied volatility of out-of-the-money put options (bid)

## option40 — Options Analytics Data  users=742 alphas=2658 fields=208 on_disk=208 types={'MATRIX': 208} subcat=Option Analytics coverage=0.9755
   This dataset provides daily historical and option-implied volatility metrics for over 2,500 US equities, including close-to-close and Parkinson historical volatilities across multiple time horizons, as well as at-the-money implied volatilities for calls, puts, and their averages. It also features skew steepness indicators, offering insight into the volatility term structure and skew for each stock
   - call_option_delta_convexity_152d         MATRIX Rate of change in a call option's delta with respect to the underlying price, 152 days to expiration.
   - call_option_delta_convexity_365d         MATRIX Gamma (sensitivity of delta to price changes) of the standardized call option at 365 days to expiry on the Opt
   - call_option_delta_convexity_547d         MATRIX Gamma (second derivative of option price with respect to underlying price) for the 547-day tenor call option
   - call_option_exercise_price_182d          MATRIX Strike price corresponding to the standardized call option gridpoint at 182 days to expiry
   - call_option_exercise_price_273d          MATRIX Strike price corresponding to the 273-day tenor call option gridpoint
   - call_option_exercise_price_730d          MATRIX Strike price corresponding to the standardized call option gridpoint at 730 days to expiry
   - call_option_implied_volatility_122d      MATRIX Implied volatility from OptionMetrics IvyDB US standardized surface for the 122-day tenor call at the ATM/forw
   - call_option_implied_volatility_91d       MATRIX Implied volatility for call options at 91 days to expiry from the OptionMetrics standardized surface (annualiz
   - call_option_market_value_182d            MATRIX Call option premium (price) at 182 days to expiry from the standard surface
   - call_option_market_value_273d            MATRIX Option premium (price) for call options at 273 days to expiry from the OptionMetrics standardized surface
   - call_option_market_value_30d             MATRIX Option premium (price) of the standardized call at 30 days to expiry on the OptionMetrics standard surface
   - call_option_market_value_365d            MATRIX Option premium (price) for call options at 365 days to expiry from the OptionMetrics standardized surface
   - call_option_market_value_60d             MATRIX Option premium (price) for the standard 60-day tenor call option from the OptionMetrics surface
   - call_option_market_value_91d             MATRIX Call option premium (price) at 91 days to expiry from the standard surface

## option6 — Forecasted Volatility for Equity Options  users=1863 alphas=18843 fields=133 on_disk=133 types={'MATRIX': 133} subcat=Option Volatility coverage=0.9616
   This dataset provides comprehensive forecasts of option volatility metrics for all US-listed stocks, ETFs, and equity indices. It includes predictions for the next 20 days of historical and implied volatility, long-term at-the-money implied volatility, and detailed measures of volatility skew and curvature across strikes. The data also covers relationships with major benchmarks like SPY and relate
   - opt6_1000dorhv                           MATRIX 1000-day realized historical intraday volatility based on open-high-low-close prices
   - opt6_10dorhv                             MATRIX 10-day realized historical intraday volatility based on open-high-low-close prices
   - opt6_120dorhv                            MATRIX 120-day open-high-low-close realized historical volatility
   - opt6_1dorhv                              MATRIX The 1-day historical intraday volatility
   - opt6_20div                               MATRIX 20-day interpolated implied at-the-money volatility (calendar day)
   - opt6_20dorhv                             MATRIX 20-day historical intraday volatility based on open-high-low-close prices
   - opt6_252dorhv                            MATRIX The 252-day historical intraday volatility
   - opt6_2rtscf                              MATRIX Goodness of fit metric for the 20-day volatility forecast compared to the actual future 20-day realized volati
   - opt6_30div                               MATRIX The 20-day interpolated implied volatility.
   - opt6_500dorhv                            MATRIX The 500-day historical intraday volatility
   - opt6_5dorhv                              MATRIX 5-day historical realized volatility using open-high-low-close prices
   - opt6_60div                               MATRIX Interpolated implied volatility for a 60-day expiry
   - opt6_60dorhv                             MATRIX The 60-day historical intraday volatility
   - opt6_90div                               MATRIX 90-day interpolated implied volatility

# USA_TOP3000_d1 | Risk  (7 datasets, multiplier 1.1)

## mfm_model_output — Multi Factor Model Universal Output  users=144 alphas=308 fields=117 on_disk=117 types={'MATRIX': 117} subcat=Risk Models coverage=0.9963
   This dataset provides the output of proprietary multi-factor risk models in a standardized format compatible with widely used risk models such as Barra and Uber. It enables portfolio managers and researchers to access daily, point-in-time factor exposures, risk estimates, and groupings for US equities, facilitating integration with simulation and portfolio construction tools. The dataset leverages
   - aerospace_defense_score                  MATRIX Score indicating exposure to aerospace and defense sector.
   - airline_industry_score                   MATRIX Daily exposure of each stock to the Airlines industry factor in the MFMCR universal risk model
   - aluminum_steel_producers_score           MATRIX Score indicating exposure to aluminum and steel production sector.
   - apparel_accessories_score                MATRIX Score reflecting exposure to apparel and accessories sector.
   - automobile_manufacturing_score           MATRIX Score reflecting exposure to automobile manufacturing sector.
   - banking_services_score                   MATRIX Daily stock exposures to the Banks industry factor
   - beverage_tobacco_score                   MATRIX Score indicating exposure to beverage and tobacco sector.
   - biotechnology_life_sciences_score        MATRIX Score reflecting exposure to biotechnology and life sciences sector.
   - broad_market_factor_score_2              MATRIX Daily stock exposures to the broad Market factor
   - building_products_score                  MATRIX Daily stock exposures to the Building Products industry factor
   - chemicals_sector_score                   MATRIX Daily stock exposures to the Chemicals industry factor
   - commercial_equipment_score               MATRIX Score indicating exposure to commercial equipment and supplies sector.
   - communication_services_score             MATRIX Score reflecting exposure to communication services sector.
   - computer_electronics_score               MATRIX Score reflecting exposure to computer and electronics manufacturing sector.

## risk65 — ETF Risk Model Data  users=252 alphas=411 fields=6 on_disk=6 types={'MATRIX': 6} subcat=Risk Models coverage=0.9743
   This dataset provides comprehensive quantitative analytics and classification details for US-listed Exchange-Traded Funds (ETFs). It includes a wide array of metrics such as risk scores, reward scores, technical and fundamental factor scores (e.g., P/E, P/B, dividend yield), sentiment indicators (put/call ratio, short interest, implied volatility), quality and diversification measures, and detaile
   - rsk65_mfm_etfm3_dsrt_intermediate        MATRIX Instrument Specific Returns
   - rsk65_mfm_etfm3_srisk                    MATRIX Instrument idiosyncratic/specific risk estimate for the ETF in the ETFM3 model
   - rsk65_mfm_etfm4_dsrt_intermediate        MATRIX Instrument Specific Returns
   - rsk65_mfm_etfm4_srisk                    MATRIX Instrument-specific idiosyncratic risk estimates for ETFM4
   - rsk65_trsd_3mfte_mfm                     MATRIX Instrument-specific residual returns unexplained by the model factors
   - rsk65_trsd_4mfte_mfm                     MATRIX Instrument-specific residual returns (specific returns) for each ETF in the ETFM4 model

## risk72 — Specific return of extended factors  users=564 alphas=2408 fields=3 on_disk=3 types={'MATRIX': 3} subcat=Risk Factors coverage=0.6956
   This is a specific returns dataset based on in-house risk model. This dataset provides specific returns output useful for creating Risk Handled Alphas neutral to all risk factors within the model.
   - rsk72_top1000_dsrt                       MATRIX Daily reproducible specific returns in % units
   - rsk72_top2000_dsrt                       MATRIX Daily reproducible specific returns in % units
   - rsk72_top3000_dsrt                       MATRIX Daily reproducible specific returns in % units

## risk59 — Securities Lending and Short Market Dynamics Dataset  users=840 alphas=4619 fields=16 on_disk=16 types={'VECTOR': 16} subcat=Risk Models coverage=0.9303
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RIC) and Bloomberg Identifiers for financial securities. By linking these two widely used security identifiers, the dataset enables seamless integration and cross-referencing of data from Bloomberg and Refinitiv platforms. This mapping is essential for data normalization, portfolio management, and research workflows th
   - rsk59_bid_rate                           VECTOR Market composite lending fee earned by long holders for existing shares on loan, annualized percent
   - rsk59_crowded_score                      VECTOR Proprietary score of short-side crowdedness based on short interest, float, and liquidity factors
   - rsk59_daystocover10day                   VECTOR Estimated days to cover calculated as real-time short interest divided by 10-day average daily trading volume
   - rsk59_daystocover30day                   VECTOR Estimated days to cover calculated as real-time short interest divided by 30-day average daily trading volume
   - rsk59_daystocover90day                   VECTOR Estimated days to cover calculated as real-time short interest divided by 90-day average daily trading volume
   - rsk59_dtcdailychg                        VECTOR Day-over-day percentage change in the number of days to cover all short positions
   - rsk59_dtcweeklychg                       VECTOR Week-over-week percentage change in the number of days to cover all short positions
   - rsk59_indicativeavailability             VECTOR S3 projected available lendable quantity of the security
   - rsk59_last_rate                          VECTOR Market composite lending fee for incremental shares loaned on that date (spot rate), percent
   - rsk59_offer_rate                         VECTOR Market composite financing fee paid by shorts for existing positions, annualized percent
   - rsk59_s3utilization                      VECTOR Ratio of real-time short interest to total lendable quantity (utilization of borrow supply)
   - rsk59_short_interest                     VECTOR Real-time short interest expressed as number of shares
   - rsk59_short_momentum                     VECTOR Momentum indicator measuring daily shorting and covering activity relative to market float
   - rsk59_shortinterestnotional              VECTOR Real-time short interest multiplied by security price, in USD

# USA_TOP3000_d1 | Macro  (2 datasets, multiplier 1.1)

## macro63 — Index Reconstitution Data  users=140 alphas=402 fields=3 on_disk=3 types={'MATRIX': 3} subcat=Macroeconomic Activities coverage=1.0
   This dataset provides comprehensive information on global index reconstitution events, including the addition and deletion of stocks or companies from various equity indexes, their respective weight percentages, and detailed hedge ratio data. It covers dynamic and static hedge ratios for both indexes and currencies, as well as currency pair exposures and effective dates. The dataset also includes 
   - mcr63_ldi_membership                     MATRIX Index membership flag for the WisdomTree WTLDI index on the date (1 = included, 0 = not included)
   - mcr63_mdi_membership                     MATRIX Membership flag indicating whether the security is included in the WTMDI index on the given date (1=included, 
   - mcr63_sdi_membership                     MATRIX Index membership flag indicating whether the security is included in the WisdomTree WTSDI index on the given d

## other551 — Alpha Toolkit Dataset  users=810 alphas=5611 fields=33 on_disk=33 types={'MATRIX': 33} subcat=Macroeconomic Activities coverage=1.0
   This dataset provides robust tools and supporting data for ETF alpha research, including clustering, universe selection, and residual return analysis, enabling researchers to focus on generating excess returns without rebuilding foundational infrastructure.
   - oth551_aev_2r                            MATRIX Daily R-squared value of VEA returns relative to its benchmark index.
   - oth551_beta_iwm                          MATRIX Daily beta of IWM relative to its benchmark index.
   - oth551_beta_mtum                         MATRIX Daily beta of MTUM relative to its benchmark index.
   - oth551_beta_qqq                          MATRIX Daily beta of QQQ relative to its benchmark index.
   - oth551_beta_qual                         MATRIX Daily beta of QUAL relative to its benchmark index.
   - oth551_beta_size                         MATRIX Daily beta of SIZE relative to its benchmark index.
   - oth551_beta_spy                          MATRIX Daily beta of SPY relative to its benchmark index.
   - oth551_beta_usmv                         MATRIX Daily beta of USMV relative to its benchmark index.
   - oth551_beta_vea                          MATRIX Daily beta of VEA relative to its benchmark index.
   - oth551_beta_vlue                         MATRIX Daily beta of VLUE relative to its benchmark index.
   - oth551_beta_vt                           MATRIX Daily beta of VT relative to its benchmark index.
   - oth551_beta_vwo                          MATRIX Daily beta of VWO relative to its benchmark index.
   - oth551_mwi_2r                            MATRIX Daily R-squared value of IWM returns relative to its benchmark index.
   - oth551_owv_2r                            MATRIX Daily R-squared value of VWO returns relative to its benchmark index.

# USA_TOP3000_d0 | News  (24 datasets, multiplier 1.6)

## news29 — Significant Developments Data  users=3 alphas=3 fields=7 on_disk=7 types={'VECTOR': 7} subcat=News coverage=0.687
   This dataset provides concise, real-time summaries of major company news and market-moving events, systematically tagged by topic and significance. Covering a wide range of event types—such as mergers, acquisitions, product launches, regulatory actions, earnings guidance, and management changes—it enables users to filter out noise and focus on impactful developments. Each event is categorized by i
   - company_event_description_text_full_refresh VECTOR The full narrative or detailed description of a company event or news story in the full refresh dataset.
   - company_event_headline_text_full_refresh VECTOR The complete headline or summary text for a company event or news item in the full refresh dataset.
   - company_event_structured_fields_full_refresh VECTOR All structured data fields and tags associated with a company event, including topics, codes, and attributes, 
   - event_secondary_topic_code               VECTOR Code representing the second-tier subcategory of the event; must be decoded via overlay
   - nws29_full_frontpage                     VECTOR Binary indicator (1/0) for whether the event/news was featured on Reuters front page
   - nws29_full_significance                  VECTOR Event importance level code: High, Medium, Low relevance to market (must decode)
   - nws29_full_topic1                        VECTOR Code representing the main category of the event; must be decoded via overlay (e.g. M&A, regulatory, etc.)

## news82 — Sentiment Analysis from DNN  users=5 alphas=5 fields=23 on_disk=23 types={'MATRIX': 20, 'VECTOR': 3} subcat=News Sentiment coverage=0.9776
   This dataset leverages neural network models to transfer sentiment scoring methodologies from one news headline dataset to another, specifically mapping sentiment from RavenPack headlines onto Benzinga news headlines. By learning how sentiment is constructed in the source dataset and applying it to the target dataset, it generates new, consistent sentiment scores for Benzinga news articles. This a
   - headline_news_article_count              MATRIX Raw number of Benzinga headlines per stock-day in the D1 window
   - maximum_headline_sentiment_score         MATRIX Daily maximum of the primary per-headline sentiment scores across all Benzinga headlines mapped to each stock-
   - maximum_primary_headline_sentiment       MATRIX Daily maximum of stream 1 sentiment scores across all D1 Benzinga headlines for a stock-day
   - maximum_secondary_headline_sentiment     MATRIX Daily maximum of stream 2 sentiment scores across all D1 Benzinga headlines for a stock-day
   - mean_headline_sentiment_score            MATRIX Daily mean of the primary sentiment scores across all D1 Benzinga headlines for a stock-day
   - mean_primary_headline_sentiment          MATRIX Daily mean of stream 1 sentiment scores across all D1 Benzinga headlines for a stock-day
   - mean_secondary_headline_sentiment        MATRIX Daily mean of stream 2 sentiment scores across all D1 Benzinga headlines for a stock-day
   - median_headline_sentiment_score          MATRIX Daily median of the primary per-headline sentiment scores for each stock based on D1 Benzinga headlines
   - median_primary_headline_sentiment        MATRIX Daily median of the alternative sentiment1 per-headline scores across all Benzinga headlines mapped to each st
   - median_secondary_headline_sentiment      MATRIX Daily median of stream 2 sentiment scores across all D1 Benzinga headlines for a stock-day
   - minimum_headline_sentiment_score         MATRIX Daily minimum of the primary sentiment scores across all D1 Benzinga headlines for a stock-day
   - minimum_primary_headline_sentiment       MATRIX Daily minimum of the alternative sentiment1 per-headline scores across all Benzinga headlines mapped to each s
   - minimum_secondary_headline_sentiment     MATRIX Daily minimum of stream 2 sentiment scores across all D1 Benzinga headlines for a stock-day
   - mws82_sentiment                          VECTOR Primary per-headline sentiment score inferred for each D1 Benzinga headline, roughly on a -1 to 1 scale

## news42 — US/AMR news data  users=7 alphas=7 fields=5 on_disk=5 types={'VECTOR': 5} subcat=News coverage=0.9663
   This dataset provides a comprehensive, real-time feed of financial news and market-moving events across North America, covering equities, commodities, forex, fixed income, and alternative assets. It includes detailed metadata tagging by ticker, sector, region, and event type, enabling granular analysis of news impact on specific securities and market segments. The dataset features analyst rating c
   - mws42_body                               VECTOR Integer key that references the corresponding bodyString
   - mws42_headline                           VECTOR Integer key that references the corresponding headlineString
   - mws42_relatednum                         VECTOR Number of related instruments/tickers associated with the story
   - mws42_time                               VECTOR Publication time of the news item in HHMMSS (24h) format, Eastern Time
   - mws42_transmission                       VECTOR Unique story transmission identifier used for deduplication/versioning and tracking updates/corrections

## news38 — News Analytic Model Data  users=9 alphas=11 fields=14 on_disk=14 types={'VECTOR': 14} subcat=News coverage=0.9028
   This dataset delivers real-time and historical financial news, blogs, and sentiment analytics sourced from thousands of global websites and media outlets. It includes structured metadata such as headlines, story content, assigned and derived tickers/topics, market-moving potential indicators, sentiment scores, readership metrics, and corporate event details. Advanced natural language processing an
   - market_impact_indicator                  VECTOR Indicator of the news story's potential to move markets.
   - mws38_action                             VECTOR News action
   - mws38_entitlement                        VECTOR News entitlement ID (EID)
   - mws38_related_num                        VECTOR Number of stocks related to or affected by the news
   - mws38_relevances                         VECTOR Degree of relevance the news is to the corresponding stock
   - mws38_time                               VECTOR News time
   - mws38_uniq_action                        VECTOR News action
   - mws38_uniq_entitlement                   VECTOR News entitlement ID (EID)
   - mws38_uniq_hotlevel                      VECTOR News hotlevel (all 0)
   - mws38_uniq_related_num                   VECTOR Number of stocks related to or affected by the news
   - mws38_uniq_relevances                    VECTOR Degree of relevance the news is to the corresponding stock
   - mws38_uniq_time                          VECTOR News time
   - mws38_uniq_version                       VECTOR News version
   - mws38_version                            VECTOR News version

# USA_TOP3000_d0 | Sentiment  (7 datasets, multiplier 1.8)

## news_sentiment_transfer — Transferred News Sentiment Analytics  users=5 alphas=7 fields=23 on_disk=23 types={'MATRIX': 20, 'VECTOR': 3} subcat=Sentiment coverage=0.9026
   This dataset provides sentiment analytics for financial news by transferring sentiment scores from a comprehensive news sentiment source to a major financial news feed using advanced machine learning techniques. It covers global equities and commodities, offering asset-level sentiment classifications (positive, neutral, negative) for news items, along with relevance, novelty, and volume metrics. B
   - news_article_count                       MATRIX Total number of news articles considered for the entity.
   - news_sentiment_score                     VECTOR Overall sentiment value derived from news articles for an entity.
   - normalized_news_article_count            MATRIX Number of news articles normalized for comparison across entities.
   - primary_sentiment_average                MATRIX Mean value of the primary sentiment scores for the entity.
   - primary_sentiment_maximum                MATRIX Maximum value observed in the primary sentiment scores.
   - primary_sentiment_middle_value           MATRIX Median value of the primary sentiment scores for the entity.
   - primary_sentiment_minimum                MATRIX Minimum value observed in the primary sentiment scores.
   - primary_sentiment_skewness_2             MATRIX Skewness statistic of the primary sentiment values for the entity.
   - primary_sentiment_total_2                MATRIX Sum of all primary sentiment values for the entity over the period.
   - primary_sentiment_value                  VECTOR Main sentiment score calculated for the entity from news data.
   - secondary_sentiment_average              MATRIX Mean value of the secondary sentiment scores for the entity.
   - secondary_sentiment_maximum              MATRIX Maximum value observed in the secondary sentiment scores.
   - secondary_sentiment_middle_value         MATRIX Median value of the secondary sentiment scores for the entity.
   - secondary_sentiment_minimum              MATRIX Minimum value observed in the secondary sentiment scores.

## sentiment23 — Textual Sentiment Analysis Data  users=61 alphas=88 fields=210 on_disk=210 types={'MATRIX': 210} subcat=Sentiment coverage=1.0
   This dataset provides daily sentiment scores for financial news headlines, generated by an in-house transformer-based natural language processing (NLP) model. It covers a wide range of companies and regions, offering granular sentiment classifications (positive, negative, neutral) along with confidence levels and descriptive statistics. The data is updated daily and structured in a matrix format, 
   - snt23_2dts_gen_234                       MATRIX General sentiment score.
   - snt23_2dts_sop_242                       MATRIX Sentiment daily time series value.
   - snt23_2dts_tuen_244                      MATRIX Sentiment daily time series value.
   - snt23_2neg_conf_low                      MATRIX Lower bound of the 95% confidence interval for the mean negative sentiment score for the stock on that date; m
   - snt23_2neg_conf_low_237                  MATRIX Confidence level of sentiment.
   - snt23_2neg_conf_up                       MATRIX Upper bound of the 95% confidence interval for the mean negative sentiment score for the stock on that date; m
   - snt23_2neg_conf_up_252                   MATRIX Confidence level of sentiment.
   - snt23_2neg_max                           MATRIX Maximum negative sentiment score across all stories for the stock on that date; unit: proportion 0–1
   - snt23_2neg_max_248                       MATRIX Maximum negative sentiment value.
   - snt23_2neg_mean                          MATRIX Average negative sentiment score across all stories for the stock on that date; unit: proportion 0–1
   - snt23_2neg_mean_243                      MATRIX Average negative sentiment value.
   - snt23_2neg_median                        MATRIX Median negative sentiment score across all stories for the stock on that date; unit: proportion 0–1
   - snt23_2neg_median_239                    MATRIX Median negative sentiment value.
   - snt23_2neg_min                           MATRIX Minimum negative sentiment score across all Inferess-linked news stories for the stock on that date (same-day 

## sentiment22 — News Sentiment Scores  users=62 alphas=96 fields=210 on_disk=210 types={'MATRIX': 210} subcat=Sentiment coverage=0.9995
   This dataset provides comprehensive, real-time financial news coverage for North American markets, including equities, commodities, forex, fixed income, and ETFs. It features detailed tagging by ticker, sector, region, and event type, enabling granular analysis of market-moving events such as earnings announcements, analyst rating changes, insider transactions, M&A activity, and regulatory actions
   - snt22_2dts_gen_234                       MATRIX 2-day time series general sentiment .
   - snt22_2dts_sop_243                       MATRIX 2-day time series sum of positive sentiment .
   - snt22_2dts_tuen_237                      MATRIX 2-day time series total of neutral sentiment .
   - snt22_2neg_conf_low                      MATRIX Lower bound of the 95% confidence interval for negative sentiment for the stock-day, computed as neg_mean − 1.
   - snt22_2neg_conf_low_250                  MATRIX negative sentiment lower confidence bound.
   - snt22_2neg_conf_up                       MATRIX Upper bound of the 95% confidence interval for negative sentiment for the stock-day, computed as neg_mean + 1.
   - snt22_2neg_conf_up_236                   MATRIX negative sentiment upper confidence bound.
   - snt22_2neg_max                           MATRIX Maximum negative sentiment score among news articles for the stock on that day
   - snt22_2neg_max_246                       MATRIX negative sentiment maximum value.
   - snt22_2neg_mean                          MATRIX Mean negative sentiment score across all news articles for the stock on that day; higher values indicate more 
   - snt22_2neg_mean_233                      MATRIX negative sentiment mean value.
   - snt22_2neg_median                        MATRIX Median of negative sentiment scores across news articles for the stock on that day
   - snt22_2neg_median_235                    MATRIX negative sentiment median value.
   - snt22_2neg_min                           MATRIX Minimum negative sentiment score among news articles for the stock on that day

## other553 — Financial Opinion Mining  users=83 alphas=147 fields=33 on_disk=33 types={'MATRIX': 33} subcat=Sentiment coverage=0.7934
   This dataset focuses on financial opinion mining from various text-based sources such as earnings calls, news, and social media. It aims to extract potential signals by performing deep analysis, considering financial characteristics and correlations among different data sources. The methodology involves advanced feature extraction, sentiment scoring using word embeddings, semi-supervised/transfer 
   - oth553_a_avgnumericpos                   MATRIX Average numerical position in financial text.
   - oth553_a_avgsentlen                      MATRIX Average sentence length in financial text.
   - oth553_a_blamecnt                        MATRIX Count of blame-related terms in financial text.
   - oth553_a_invblamecnt                     MATRIX Count of blame-related terms in financial text.
   - oth553_a_numericcnt                      MATRIX Count of numerical values in financial text.
   - oth553_a_passiveratio                    MATRIX Ratio of passive voice in financial text.
   - oth553_a_polycnt                         MATRIX Count of polysyllabic words in financial text.
   - oth553_a_poscnt                          MATRIX Count of positive terms in financial text.
   - oth553_a_wordcnt                         MATRIX Total word count in financial text.
   - oth553_p_avgnumericpos                   MATRIX Average numerical position in financial text.
   - oth553_p_avgsentlen                      MATRIX Average sentence length in financial text.
   - oth553_p_blamecnt                        MATRIX Count of blame-related terms in financial text.
   - oth553_p_invblamecnt                     MATRIX Count of blame-related terms in financial text.
   - oth553_p_numericcnt                      MATRIX Count of numerical values in financial text.

# USA_TOP3000_d0 | Social Media  (3 datasets, multiplier 1.4)

## creator_signal_perf — Finance Creator Prediction Performance  users=34 alphas=62 fields=102 on_disk=102 types={'VECTOR': 102} subcat=Social Media coverage=0.6835
   This dataset aggregates and analyzes stock price predictions made by prominent finance content creators across platforms such as Twitter, YouTube, and select Discord channels. Using AI-driven natural language processing and computer vision, it extracts directional signals (long/short), confidence scores, and performance metrics for each creator and asset. The data includes detailed accuracy statis
   - aggregate_large_target_long_horizon_return VECTOR Aggregate portfolio return using large price targets and extended timeframes.
   - aggregate_large_target_long_horizon_return_2 VECTOR Aggregate portfolio return using large price targets and extended timeframes.
   - aggregate_medium_target_mid_horizon_return VECTOR Aggregate portfolio return using medium price targets and mid-range timeframes.
   - aggregate_medium_target_mid_horizon_return_2 VECTOR Aggregate portfolio return using medium price targets and mid-range timeframes.
   - aggregate_prediction_accuracy_score      VECTOR Weighted score reflecting overall prediction accuracy and volume.
   - aggregate_prediction_accuracy_score_2    VECTOR Weighted score reflecting overall prediction accuracy and volume.
   - aggregate_small_target_quick_horizon_gain VECTOR Portfolio return using small price targets and short time horizons across all assets.
   - aggregate_small_target_quick_horizon_return VECTOR Aggregate portfolio return using small price targets and short timeframes.
   - asset_aggregate_portfolio_return         VECTOR Total percentage return for an asset using all price and time targets.
   - asset_aggregate_portfolio_return_2       VECTOR Total percentage return for an asset using all price and time targets.
   - asset_correct_long_predictions_count     VECTOR Number of correct long-biased predictions for a specific asset.
   - asset_correct_long_predictions_count_2   VECTOR Number of correct long-biased predictions for a specific asset.
   - asset_correct_short_predictions_count    VECTOR Number of correct short-biased predictions for a specific asset.
   - asset_correct_short_predictions_count_2  VECTOR Number of correct short-biased predictions for a specific asset.

## socialmedia8 — Social Media Data for Equity  users=222 alphas=364 fields=2 on_disk=2 types={'MATRIX': 2} subcat=Social Media coverage=1.0
   This dataset provides quantitative sentiment metrics for US equities based on Twitter messages, covering the Russell 3000 universe since December 2011. It includes a suite of S-Factors such as S-Score (normalized sentiment), S-Volume (tweet volume), S-Dispersion (source diversity), S-Buzz (abnormal activity), and S-Delta (sentiment trend), all calculated using both unweighted and exponentially wei
   - snt_social_value                         MATRIX Z-score of sentiment
   - snt_social_volume                        MATRIX Normalized tweet volume

## socialmedia12 — Sentiment Data for Equity  users=546 alphas=1011 fields=9 on_disk=9 types={'MATRIX': 6, 'VECTOR': 3} subcat=Social Media coverage=1.0
   This dataset aggregates and analyzes social media posts and news articles related to financial markets, covering thousands of sources and several years of historical data. It quantifies market sentiment and buzz for individual assets, sectors, and indices using advanced natural language processing and machine learning techniques. The data includes sentiment scores, buzz indicators, and trading sig
   - scl12_buzz                               MATRIX relative sentiment volume
   - scl12_buzzvec                            VECTOR Vector representing the volume of social media sentiment/mentions related to the instrument
   - scl12_sentiment                          MATRIX sentiment
   - scl12_sentvec                            VECTOR Vector representing the sentiment score (bullish/bearish/neutral) derived from social media data for the instr
   - scl12_typevec                            VECTOR Vector containing the type indices identifying the categories of instruments in the dataset
   - snt_buzz                                 MATRIX Negative relative sentiment volume measure for current day, with missing values filled as 0
   - snt_buzz_bfl                             MATRIX Negative relative sentiment volume measure for current day, with missing values filled as 1
   - snt_buzz_ret                             MATRIX negative return of relative sentiment volume
   - snt_value                                MATRIX Negative sentiment score/indicator for current day, with missing values filled as 0

# USA_TOP3000_d0 | Insiders  (2 datasets, multiplier 1.5)

## insider_agg_matrix — Smart Insider Transaction Aggregates  users=4 alphas=8 fields=34 on_disk=34 types={'MATRIX': 34} subcat=Insider Data coverage=0.7672
   This dataset provides a structured, matrix-format view of insider trading activity, where individual transactions by company insiders are aggregated and filtered using advanced methodologies. By summarizing key metrics such as average shares bought or sold, and applying smart filters to highlight the most relevant transactions, the dataset enables researchers and investors to efficiently identify 
   - avg_buy_shares                           MATRIX Mean shares bought by all directors
   - avg_secondary_buy_shares                 MATRIX Mean shares bought directly by directors
   - avg_secondary_sell_shares                MATRIX Mean shares sold directly by directors
   - avg_secondary_top_buy_shares             MATRIX Mean shares bought directly by executives
   - avg_secondary_top_sell_shares            MATRIX Mean shares sold directly by executives
   - avg_sell_shares                          MATRIX Mean shares sold by all directors
   - avg_top_buy_shares                       MATRIX Mean shares bought by all executives
   - avg_top_sell_shares                      MATRIX Mean shares sold by all executives
   - directional_indicator                    MATRIX A metric indicating the overall direction or bias of insider activity.
   - directional_indicator_2                  MATRIX A metric indicating the overall direction or bias of enhanced insider activity.
   - directional_significant_value_1          MATRIX Highest value among directional significant insider transactions.
   - directional_significant_value_2          MATRIX Second highest value among directional significant insider transactions.
   - directional_significant_value_3          MATRIX Third highest value among directional significant insider transactions.
   - directional_significant_value_4          MATRIX Fourth highest value among directional significant insider transactions.

## insiders1 — Global Insider Trading Data  users=161 alphas=386 fields=9 on_disk=9 types={'VECTOR': 9} subcat=Insider Data coverage=0.755
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RIC) and Bloomberg Identifiers (BBID), serving as a cross-reference for security identifiers across two major financial data platforms. It is essential for researchers, portfolio managers, and quantitative analysts who need to integrate or reconcile data from both Refinitiv and Bloomberg sources. By enabling accurate a
   - insd1_gvkey                              VECTOR Compustat Global Company Identifier (Global Value Key) for the issuer
   - insd1_holdings                           VECTOR Total equity share holdings of the insider after the transaction
   - insd1_price                              VECTOR Transaction price per share; if a range was reported, this is the minimum price
   - insd1_shares                             VECTOR Number of shares (or units) traded in the transaction
   - insd1_tradesignificance                  VECTOR Significance score of the trade (1 = low significance, 3 = high significance)
   - insd1_value                              VECTOR Total value of the transaction in original currency
   - insd1_valueeur                           VECTOR Total value of the transaction in Euro
   - max_trade_price                          VECTOR Maximum transaction price per share when a price range was reported
   - transaction_currency_code                VECTOR Three-letter ISO currency code of the transaction’s currency

# USA_TOP3000_d0 | Short Interest  (2 datasets, multiplier 1.4)

## shortinterest3 — Securities Lending Files Data  users=30 alphas=55 fields=41 on_disk=41 types={'VECTOR': 41} subcat=Short Sale Models coverage=0.9759
   This dataset provides comprehensive global coverage of securities lending activity across equities and fixed income instruments in over 110 countries. It aggregates transaction-level data from lending agents, third-party lenders, and beneficial owners, as well as borrowing activity from prime brokers and asset managers. Key fields include loan volumes, loan rates (average, min, max, and dispersion
   - available_market_value_usd               VECTOR USD market value of the units reported as available to lend for this group
   - available_share_count                    VECTOR Number of units (shares or par value) reported as available to lend for this group
   - average_loan_duration_days               VECTOR Weighted average age of loans in this group, measured in days
   - average_loan_duration_days_intra         VECTOR Weighted average age of the loans in this group, in days
   - average_loan_duration_days_main          VECTOR The weighted average age of loans in this primary key group, measured in days
   - intraday_average_loan_age                VECTOR Weighted average age of the loans in this primary key group, measured in days
   - intraday_loan_rate_volatility            VECTOR Standard deviation of loan rates across transactions in this primary key group
   - intraday_loaned_market_value_usd         VECTOR Market value in US dollars of the units lent in transactions that fit this primary key group
   - intraday_loaned_share_count              VECTOR Number of units (shares or par value) lent in transactions that fit this primary key group
   - intraday_max_loan_rate                   VECTOR Maximum loan rate observed among the loans/transactions in this primary key group
   - intraday_mean_loan_rate                  VECTOR Weighted average loan rate across all relevant transactions in this primary key group
   - intraday_min_loan_rate                   VECTOR Minimum loan rate observed among the loans/transactions in this primary key group for the as-of snapshot
   - intraday_transaction_count               VECTOR Number of loan transactions that fit this primary key group
   - loan_rate_volatility                     VECTOR The standard deviation of loan rates for all transactions in this primary key group

## shortinterest24 — Short Sale Circuit Breaker Data  users=85 alphas=137 fields=1 on_disk=1 types={'MATRIX': 1} subcat=Short Sale Models coverage=0.2553
   This dataset tracks stocks subject to trading restrictions under Regulation SHO, specifically those that have triggered short sale restrictions due to excessive short selling activity. It includes details such as trigger times, market categories, turnover ratios, and in-sample returns, providing a comprehensive view of short interest dynamics and regulatory interventions. By analyzing these events
   - shrt24_triggertime                       MATRIX Time when the short sale circuit breaker was triggered for the security (D0 - current day)

# USA_TOP3000_d0 | Institutions  (2 datasets, multiplier 1.3)

## fund_holdings_panel — Global Institutional Fund Holdings  users=6 alphas=11 fields=30 on_disk=30 types={'VECTOR': 30} subcat=Ownership Models coverage=0.9709
   This dataset provides daily, account-level insights into the holdings and transactions of major institutional investors, including mutual funds, ETFs, asset managers, pension funds, and insurance companies. It features detailed tables on daily trades, holdings, and the size of the investment account panel, with metrics such as conviction holdings, boundary trades, significant transactions, and con
   - boundary_transaction_total               VECTOR Number of boundary transactions (new position initiations or complete liquidations) across all fund accounts o
   - boundary_transaction_total_active        VECTOR Number of boundary transactions across fund accounts (introductions of new positions or complete liquidations)
   - boundary_transaction_usd_value           VECTOR Total USD value of boundary transactions (entries into new positions or complete liquidations) across all acco
   - boundary_transaction_usd_value_active    VECTOR Dollar value of boundary transactions in USD
   - herfindahl_index_holdings                VECTOR Herfindahl-Hirschman Index of holdings concentration based on account weights
   - herfindahl_index_holdings_active         VECTOR Herfindahl-Hirschman Index of holdings weights across accounts (0 to 1)
   - herfindahl_index_transactions            VECTOR Herfindahl-Hirschman Index of trade value concentration across transacting accounts (0 to 1, higher means more
   - herfindahl_index_transactions_active     VECTOR Herfindahl-Hirschman Index concentration measure based on distribution of transaction value across accounts
   - holder_account_total                     VECTOR Number of distinct investment accounts or funds holding the ISIN on the date
   - holder_account_total_active              VECTOR Number of distinct accounts holding this ISIN on the date
   - holding_value_distribution_score         VECTOR Concentration of holdings value across accounts, a custom crowding metric
   - holding_value_distribution_score_active  VECTOR Concentration of holdings value across accounts; higher values indicate more crowding among holders
   - large_trade_count_50bps                  VECTOR Number of transactions where the trade value exceeds 0.5% of the respective fund’s AUM
   - large_trade_count_50bps_active           VECTOR Count of transactions with transaction value greater than 0.5% of the fund’s AUM

## institutions6 — Institutions and Beneficial Stake Ownership  users=334 alphas=870 fields=11 on_disk=11 types={'MATRIX': 11} subcat=Ownership Models coverage=1.0
   This dataset provides comprehensive information on global equity ownership by institutions, mutual funds, and beneficial stakeholders. It includes current and historical holdings data from over 50,000 portfolios and companies across 70 countries, with more than 10 years of history. Key fields cover shares held, percent of shares outstanding, report dates, aggregated statistics, and investor profil
   - inst6_num_of_institutional_buyers        MATRIX Number of institutional investors who purchased shares of the security during the reporting period
   - inst6_num_of_institutional_holders       MATRIX Number of institutional investors holding shares greater than zero in the security at the given time
   - inst6_num_of_institutional_sellers       MATRIX Number of institutional investors who sold shares of the security during the reporting period
   - inst6_num_of_institutional_shares_bought MATRIX Total number of shares of the security purchased by institutional investors during the reporting period
   - inst6_num_of_institutional_shares_sold   MATRIX Total number of shares of the security sold by institutional investors during the reporting period
   - inst6_total_share_held_by_owners         MATRIX Aggregate number of shares of the security held by all owners with duplicate holdings between parent and child
   - inst6_total_shares_held_by_institutions  MATRIX Aggregate number of shares of the security currently held by institutional investors
   - inst6_value_held_by_institutions         MATRIX Aggregate dollar value of shares of the security currently held by institutional investors
   - inst6_value_held_by_owners               MATRIX Aggregate dollar value of shares of the security held by all owners with duplication between parent and child 
   - inst6_value_of_institutional_shares_bought MATRIX Aggregate dollar value of shares of the security purchased by institutional investors during the reporting per
   - inst6_value_of_institutional_shares_sold MATRIX Aggregate dollar value of shares of the security sold by institutional investors during the reporting period

# USA_TOP3000_d0 | Earnings  (5 datasets, multiplier 1.4)

## earnings_sent_matrix — Global Earnings Call Sentiment Matrix  users=10 alphas=33 fields=7 on_disk=7 types={'MATRIX': 7} subcat=Earnings Estimates coverage=0.7006
   This dataset provides a structured, matrix-format aggregation of global company earnings call transcripts, focusing on sentiment and topic analytics. It leverages advanced natural language processing to extract and quantify positive, neutral, and negative sentiment probabilities from management presentations and Q&A sessions, across over 200 thematic topics. The data is filtered and enhanced with 
   - intraday_delay_indicator                 MATRIX A code indicating whether the data is updated intraday or with a delay.
   - likelihood_of_neutral_tone               MATRIX Model-estimated probability [0–1] that the intraday transcript slice has neutral sentiment; sums with the othe
   - negative_sentiment_probability_3         MATRIX Model-estimated probability [0–1] that the intraday transcript slice has negative sentiment; designed to sum t
   - overall_sentiment_score                  MATRIX Categorical sentiment label derived by argmax over Prob_POS, Prob_NTR, Prob_NEG; typically -1 negative, 0 neut
   - positive_sentiment_probability_3         MATRIX Model-estimated probability [0–1] that the intraday transcript slice has positive sentiment; part of the three
   - sentiment_weighting_method1              MATRIX Aggregate transcript tone score computed via method 1; higher values indicate more positive sentiment for the 
   - sentiment_weighting_method2              MATRIX Alternative aggregate transcript tone score computed via method 2; higher values indicate more positive sentim

## earnings5 — Earnings Date Breaks  users=84 alphas=122 fields=5 on_disk=5 types={'VECTOR': 5} subcat=Earnings Estimates coverage=0.9403
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RICs) and Bloomberg IDs for financial securities. It consolidates identifier information from both Bloomberg and Refinitiv, enabling users to cross-reference securities across these two major data platforms. The mapping is essential for integrating and reconciling datasets that use different identifier systems, facilit
   - earnings_date_deviation_score            VECTOR Z-score of the confirmed date versus issuer’s last 5 years for the same quarter: (confirmed date − mean) / sta
   - ern5_change_time                         VECTOR Time when the change was recorded (HHMMSS)
   - ern5_fiscal_year                         VECTOR Reporting fiscal year for the earnings period
   - ern5_total_days_changed                  VECTOR Signed number of days between the current scheduled earnings date and the first date projected by WSH for the 
   - event_time_marker                        VECTOR Time-of-day classification for the announcement: Before Market=0, During Market=1, After Market=2, Unspecified

## earnings7 — Horizon Earnings and Calendar North America  users=89 alphas=161 fields=20 on_disk=20 types={'VECTOR': 20} subcat=Earnings Estimates coverage=0.7047
   This dataset provides concise, real-time summaries of major company news events that are likely to impact market prices. Each event is tagged by topic, significance level, and includes a headline and detailed description, covering a wide range of corporate actions such as mergers, acquisitions, product launches, regulatory changes, earnings guidance, and more. The data is structured for easy integ
   - confcall_financial_year                  VECTOR Fiscal year for which the conference call is relevant or reported
   - confcall_fiscal_quarter                  VECTOR Fiscal quarter (1-4) for which the conference call pertains
   - dividend_amount_original_currency        VECTOR The currency code (integer) representing the original currency in which the dividend amount is declared
   - dividend_payment_frequency_2             VECTOR How often the dividend is paid (e.g., annual, quarterly) as an integer frequency code
   - earnings_announcement_time_of_day        VECTOR Numeric code indicating the expected time of day when the earnings announcement is scheduled (e.g., before mar
   - earnings_date_fiscal_quarter             VECTOR Numeric value (1-4) indicating which fiscal quarter the earnings date pertains to
   - earnings_date_fiscal_year                VECTOR Numeric value representing the fiscal year associated with the scheduled or reported earnings event
   - eps_fiscal_quarter                       VECTOR Fiscal quarter to which the reported EPS relates (1-4)
   - eps_fiscal_year                          VECTOR Fiscal year to which the reported EPS relates
   - eps_original_currency                    VECTOR Currency code for the original currency in which EPS was reported
   - ern7_co_spe                              VECTOR Reported earnings per share in original currency
   - ern7_div_amount                          VECTOR Dividend amount paid per share in the issuer's local currency
   - ern7_div_amount_oc                       VECTOR dividend amount
   - ern7_div_amount_usd                      VECTOR Dividend amount paid per share, converted into US dollars

## earnings6 — International Findings Data  users=276 alphas=643 fields=68 on_disk=68 types={'VECTOR': 68} subcat=Earnings Estimates coverage=0.9659
   This dataset offers daily snapshots of international corporate events, including earnings announcements, conference calls, dividend declarations, shareholder meetings, and other key financial events. It provides detailed metadata such as event status, timing, fiscal period, and confirmation level, along with links to press releases and filings. By tracking the timing and revisions of earnings date
   - eps_change_absolute_value                VECTOR The absolute change in earnings per share compared to the previous period.
   - eps_change_percentage_value              VECTOR The percentage change in earnings per share compared to the previous period.
   - ern6_1q                                  VECTOR Earnings date for the 1st quarter (may be historical)
   - ern6_1q_13                               VECTOR Earnings Date for 1st quarter - may be historical
   - ern6_2q                                  VECTOR Earnings date for the 2nd quarter (may be historical)
   - ern6_2q_14                               VECTOR Earnings Date for 2nd quarter - may be historical
   - ern6_3q                                  VECTOR Earnings date for the 3rd quarter (may be historical)
   - ern6_3q_15                               VECTOR Earnings Date for 3rd quarter - may be historical
   - ern6_4q                                  VECTOR Earnings date for the 4th quarter (may be historical)
   - ern6_4q_16                               VECTOR Earnings Date for 4th quarter - may be historical
   - ern6_actual_currenty_49                  VECTOR Actual Currencyy
   - ern6_actual_eps                          VECTOR Reported non-GAAP diluted (or basic if diluted unavailable) EPS
   - ern6_actual_eps_67                       VECTOR The diluted (or basic if diluted not provided) non-GAAP EPS as reported in the press release or filing
   - ern6_actual_fiscal_year                  VECTOR Fiscal year corresponding to the actual earnings release (YYYY)

# USA_TOP3000_d0 | Option  (2 datasets, multiplier 1.7)

## option6 — Forecasted Volatility for Equity Options  users=274 alphas=652 fields=131 on_disk=131 types={'MATRIX': 131} subcat=Option Volatility coverage=0.9742
   This dataset provides comprehensive forecasts of option volatility metrics for all US-listed stocks, ETFs, and equity indices. It includes predictions for the next 20 days of historical and implied volatility, long-term at-the-money implied volatility, and detailed measures of volatility skew and curvature across strikes. The data also covers relationships with major benchmarks like SPY and relate
   - opt6_1000dorhv                           MATRIX 1000-day realized historical intraday volatility based on open-high-low-close prices
   - opt6_10dorhv                             MATRIX 10-day realized historical intraday volatility based on open-high-low-close prices
   - opt6_120dorhv                            MATRIX 120-day open-high-low-close realized historical volatility
   - opt6_1dorhv                              MATRIX The 1-day historical intraday volatility
   - opt6_20div                               MATRIX 20-day interpolated implied at-the-money volatility (calendar day)
   - opt6_20dorhv                             MATRIX 20-day historical intraday volatility based on open-high-low-close prices
   - opt6_252dorhv                            MATRIX The 252-day historical intraday volatility
   - opt6_2rtscf                              MATRIX Goodness of fit metric for the 20-day volatility forecast compared to the actual future 20-day realized volati
   - opt6_30div                               MATRIX The 20-day interpolated implied volatility.
   - opt6_500dorhv                            MATRIX The 500-day historical intraday volatility
   - opt6_5dorhv                              MATRIX 5-day historical realized volatility using open-high-low-close prices
   - opt6_60div                               MATRIX Interpolated implied volatility for a 60-day expiry
   - opt6_60dorhv                             MATRIX The 60-day historical intraday volatility
   - opt6_90div                               MATRIX 90-day interpolated implied volatility

## option8 — Volatility Data  users=2915 alphas=6179 fields=64 on_disk=64 types={'MATRIX': 64} subcat=Option Volatility coverage=0.9697
   This dataset provides comprehensive daily volatility metrics for over 2,500 US equities, including both historical and option-implied volatilities across multiple time horizons. It features close-to-close and Parkinson historical volatility calculations, as well as at-the-money implied volatilities for calls, puts, and their averages, spanning durations from 10 to 1080 calendar days. Additionally,
   - historical_volatility_10                 MATRIX Historical close-to-close volatility for approximately 10 calendar days
   - historical_volatility_120                MATRIX Historical close-to-close volatility for approximately 120 calendar days
   - historical_volatility_150                MATRIX Historical close-to-close volatility for approximately 150 calendar days
   - historical_volatility_180                MATRIX Historical close-to-close volatility for approximately 180 calendar days
   - historical_volatility_20                 MATRIX Historical close-to-close volatility for approximately 20 calendar days
   - historical_volatility_30                 MATRIX Historical close-to-close volatility for approximately 30 calendar days
   - historical_volatility_60                 MATRIX Historical close-to-close volatility for approximately 60 calendar days
   - historical_volatility_90                 MATRIX Historical close-to-close volatility for approximately 90 calendar days
   - implied_volatility_call_10               MATRIX Implied volatility of the at-the-money call for the stock with an expiration 10 calendar days from the measure
   - implied_volatility_call_1080             MATRIX Implied volatility of the at-the-money call for the stock with an expiration 1080 calendar days from the measu
   - implied_volatility_call_120              MATRIX Implied volatility of the at-the-money call for the stock with an expiration 120 calendar days from the measur
   - implied_volatility_call_150              MATRIX Implied volatility of the at-the-money call for the stock with an expiration 150 calendar days from the measur
   - implied_volatility_call_180              MATRIX Implied volatility of the at-the-money call for the stock with an expiration 180 calendar days from the measur
   - implied_volatility_call_20               MATRIX Implied volatility of the at-the-money call for the stock with an expiration 20 calendar days from the measure

# USA_TOP3000_d0 | Risk  (2 datasets, multiplier 1.1)

## risk59 — Securities Lending and Short Market Dynamics Dataset  users=40 alphas=82 fields=16 on_disk=16 types={'VECTOR': 16} subcat=Risk Models coverage=0.9806
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RIC) and Bloomberg Identifiers for financial securities. By linking these two widely used security identifiers, the dataset enables seamless integration and cross-referencing of data from Bloomberg and Refinitiv platforms. This mapping is essential for data normalization, portfolio management, and research workflows th
   - rsk59_bid_rate                           VECTOR Market composite lending fee earned by long holders for existing shares on loan, annualized percent
   - rsk59_crowded_score                      VECTOR Proprietary score of short-side crowdedness based on short interest, float, and liquidity factors
   - rsk59_daystocover10day                   VECTOR Estimated days to cover calculated as real-time short interest divided by 10-day average daily trading volume
   - rsk59_daystocover30day                   VECTOR Estimated days to cover calculated as real-time short interest divided by 30-day average daily trading volume
   - rsk59_daystocover90day                   VECTOR Estimated days to cover calculated as real-time short interest divided by 90-day average daily trading volume
   - rsk59_dtcdailychg                        VECTOR Day-over-day percentage change in the number of days to cover all short positions
   - rsk59_dtcweeklychg                       VECTOR Week-over-week percentage change in the number of days to cover all short positions
   - rsk59_indicativeavailability             VECTOR S3 projected available lendable quantity of the security
   - rsk59_last_rate                          VECTOR Market composite lending fee for incremental shares loaned on that date (spot rate), percent
   - rsk59_offer_rate                         VECTOR Market composite financing fee paid by shorts for existing positions, annualized percent
   - rsk59_s3utilization                      VECTOR Ratio of real-time short interest to total lendable quantity (utilization of borrow supply)
   - rsk59_short_interest                     VECTOR Real-time short interest expressed as number of shares
   - rsk59_short_momentum                     VECTOR Momentum indicator measuring daily shorting and covering activity relative to market float
   - rsk59_shortinterestnotional              VECTOR Real-time short interest multiplied by security price, in USD

## risk60 — Securities Lending Insight Data  users=754 alphas=1984 fields=5 on_disk=5 types={'VECTOR': 5} subcat=Risk Models coverage=1.0
   This dataset provides a comprehensive mapping between Reuters Instrument Codes (RIC) and Bloomberg Identifiers (BBID) for global securities. It enables seamless integration and reconciliation of security data across different financial platforms and data sources. By facilitating accurate cross-referencing, the dataset supports portfolio management, trade processing, and data aggregation tasks. Whi
   - lending_fee_bid_rate                     VECTOR Composite lending fee (annualized) at which long inventory is lent
   - rsk60_crowding                           VECTOR Signed daily indicator of shorting activity (positive = increased shorting/crowding, negative = covering/decro
   - rsk60_datatime                           VECTOR Vendor timestamp in HHMMSS for the snapshot, used to order intraday prints
   - rsk60_last                               VECTOR Most recent borrow/lend rate observed at the snapshot time
   - rsk60_offer                              VECTOR Composite borrow fee (annualized) paid by the short seller