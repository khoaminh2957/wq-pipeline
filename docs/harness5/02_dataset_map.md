# harness5 — USA/d1 dataset map for NEW mechanisms (Portfolio agent, 2026-09-08)

Purpose (Q17/Q20 of 00_agreements): raw material for round 1 — which USA/d1 datasets nobody here has
touched, what signed fields they carry, which pyramid cell they fill, and how crowded they are. No
hypothesis is written here; no Sharpe was used to rank anything (RULE 0: labels + literature only; the
journal is read only to define "touched").

## 0. Inputs, definitions, re-derivations
| input | file | date / size |
|---|---|---|
| labels | `fetched/rc/field_labels.jsonl` (`forge.labels.load()`) | 127,642 fields, 83,556 carry `USA/d1` in `regions` |
| USA/d1 catalogue | `fetched/rc/fields/USA_TOP3000_d1.jsonl` | 85,612 fields, crawled 2026-07-15; **0 field ids in more than one dataset** |
| survey | `fetched/rc/datasets_survey.json["USA_TOP3000_d1"]` | 299 datasets (univ1/univ2 excluded → **297**), 2026-09-04 |
| journal | VPS `state/layered/runs/forge.jsonl` (read-only copy) | 19,881 rows; 18,081 with a formula; 17,642 with results; dateCreated 2026-09-04 → 09-08; **USA/d1: 10,686 rows** (10,646 TOP3000 + 40 TOP1000) |
| composites / legs | `forge/composites/*.yaml` (28), `forge/hypotheses/*.yaml` (44) + `later/` (8) | 21 distinct composite datasets, 18 of them in the USA/d1 survey (`fundamental90`, `other401`, `fundamental45` are not) |
| pyramid cells | VPS `state/pyramid_cell_counts.json` | read 2026-09-08 09:30 UTC (`ts` 1788859851) |

Definitions. **Touched** = a dataset owning ≥ 1 field of ≥ 1 journal formula, any region (field → dataset
through the segment's own catalogue; for USA/d0, JPN/d1, EUR TOP1200 and USA TOP1000 — 3,065 rows — no
catalogue is on disk and the labels map was the fallback). **Untouched (tier U)** = 0 journal rows AND in
no composite. **Tier T (typed-only)** = touched only by the typed-grammar A/B arm (980 random-within-grammar
rows, 2026-09-07 09:42–11:24 ET, 02_design §11x–§11y): the dataset was never drawn by a hand-written
hypothesis. **Signed** = label `sign` ∈ {+, −} (source `description` or the EX-ANTE `DOMAIN_SIGN` prior
in `forge/labels.py`). **Dense MATRIX** = `by_region["USA/d1"]` structure MATRIX and coverage ≥ 0.9.

Re-derivations (RULE 0 §5):
- Untouched count: **126** by formula fields; 171 by `meta.dataset` (split on `+`); the 45 extra are all
  tier T (≤ 33 rows each) — datasets that only random typed formulas ever reached. Reported: 126.
- Per-dataset journal rows on USA/d1, meta vs formula: us_short_sale 4,243 / 4,306; news_sentiment_transfer
  3,450 / 3,493; fundamental6 4,251 / 4,294; option8 1,991 / 2,004 (meta names one dataset per leg;
  ensembles and typed rows add fields meta does not list).
- Dense-signed MATRIX total 7,682 by two filter orders; signed total 20,268. Labels' own `dataset` field
  disagrees with the USA/d1 catalogue for 95 fields (39 are `income`/`operating_income`… written as
  `fundamental23` while USA/d1 owns them as `fundamental6`) — every count below uses the **catalogue's** owner;
  the first pass with the labels map had put 4,382 rows on fundamental23 (true: 57) and 9 on fundamental6
  (true: 4,294). One dataset flipped between passes (model27: 2 typed rows → tier T).
- Tiers over the 297: U 126 · T 143 · touched by hand-written hypotheses but in no composite 10 · in a
  composite 18. Of the 126 untouched, **56** have ≥ 1 signed field and only **9** have ≥ 1 signed dense MATRIX field.

Ranking rule (transparent, no Sharpe): tier U before T; then bucket A = ≥ 20 signed dense MATRIX fields,
B = 5–19, C = 1–4, D = 0 dense but ≥ 5 signed (VECTOR / sparse), E = 1–4 signed, F = no sign; inside a
bucket `userCount` ascending (D/E: signed count descending first); then "fills an empty cell".

## 1. Top 40 untouched USA/d1 datasets (tier U: 0 journal rows by both derivations, in no composite)
Columns: cell = pyramid category (alphas in the cell / still needed, UNLOCK_AT 3); users/alphas = platform
crowding; signed = labelled fields (+/−; `desc` = sign read from the description, the rest are priors);
dMs/dM = signed dense MATRIX / dense MATRIX fields; V = VECTOR fields. Best Sharpe: none exists (0 rows).

| # | bk | id — name | cat / sub | cell (n/need) | users / alphas | signed (+/−, desc) | dMs/dM (V) | signed domains |
|---|---|---|---|---|---|---|---|---|
| 1 | A | nlp_news_scores — Transformer-Based News Sentiment Analytics | Other / AI-ML | Other (3/0) | 21 / 32 | 50 (22/28, 28) | 50/84 (0) | sentiment 50 |
| 2 | B | news82 — Sentiment Analysis from DNN | News / News Sentiment | **News (2/1)** | 52 / 324 | 18 (18/0, 0) | 15/20 (0) | sentiment |
| 3 | B | news84 — Headline Sentiment Analysis using DNN | News / News Sentiment | **News (2/1)** | 58 / 102 | 17 (17/0, 0) | 14/20 (0) | sentiment |
| 4 | B | news46 — Relevant News Analytics Data | News / News Sentiment | **News (2/1)** | 324 / 924 | 18 (18/0, 4) | 12/33 (0) | sentiment |
| 5 | B | model37 — Text Mining Data | Model / NLP Models | Model (19/0) | 415 / 4,959 | 38 (2/36, 18) | 5/26 (0) | leverage 25, ml-prediction 9 |
| 6 | B | fundamental13 — Comprehensive Fundamentals Dataset | Fundamental / Fundamental Data | Fundamental (4/0) | 1,422 / 14,869 | 18 (16/2, 0) | 11/28 (0) | profitability 13, earnings-event 3 |
| 7 | B | news18 — Ravenpack News Data | News / News Sentiment | **News (2/1)** | **8,772 / 56,384** | 62 (62/0, 0) | 7/10 (0) | sentiment 61 |
| 8 | C | model12 — Stock Selection Model | Model / Technical Models | Model (19/0) | 265 / 2,103 | 4 (4/0, 4) | 4/5 (0) | price-technical 2, liquidity 1, ml 1 |
| 9 | C | earnings2 — Financial Event Calendar Data | Earnings / Earnings Estimates | Earnings (3/0) | 606 / 2,377 | 4 (4/0, 0) | 2/2 (0) | profitability (all 4 are DATE fields — label slip) |
| 10 | D | news_sentiment_dl — Deep Learning News Sentiment Signals | Other / AI-ML | Other (3/0) | 11 / 17 | 40 (16/24, 24) | 0/0 (88) | sentiment |
| 11 | D | news92 — Standardized Financial News Categorization | News / News Sentiment | **News (2/1)** | 120 / 492 | 38 (38/0, 3) | 0/0 (48) | sentiment |
| 12 | D | news87 — Smart Conference call transcript data | Analyst / Analyst Estimates | Analyst (3/0) | 480 / 2,494 | 36 (22/14, 14) | 0/0 (214) | sentiment 22, analyst-estimate 14 |
| 13 | D | fundamental14 — Audit Analytics Directors Data | Fundamental / Fundamental Models | Fundamental (4/0) | 1,231 / 6,931 | 34 (34/0, 0) | 0/0 (248) | cashflow 16, profitability 14, growth 4 |
| 14 | D | news23 — MnA Deals Data | News / News | **News (2/1)** | 59 / 126 | 23 (21/2, 0) | 0/0 (129) | earnings-event 18, growth 2, leverage 2 |
| 15 | D | event_sentiment_signals — Corporate Event Sentiment Signals | Other / Event Data | Other (3/0) | 24 / 46 | 13 (5/8, 8) | 0/0 (26, cov 0.72) | sentiment 7, other 6 |
| 16 | D | news48 — Global Media News Data | News / News Sentiment | **News (2/1)** | 136 / 331 | 10 (10/0, 1) | 0/0 (22) | sentiment 9, analyst-rating 1 |
| 17 | D | news104 — Archive News Data | News / News | **News (2/1)** | 93 / 244 | 9 (8/1, 4) | 0/0 (32) | sentiment |
| 18 | D | news17 — PR Edition Data | News / News | **News (2/1)** | 259 / 623 | 9 (9/0, 0) | 0/0 (45) | sentiment |
| 19 | D | news_sentiment_nlp — News Sentiment Signal Features | Other / AI-ML | Other (3/0) | 9 / 10 | 8 (6/2, 2) | 0/0 (23) | sentiment 6, news 2 |
| 20 | D | news31 — News Analytics on Equities | News / News | **News (2/1)** | 502 / 2,980 | 7 (4/3, 3) | 0/0 (59) | sentiment |
| 21 | D | filing_sentiment — Regulatory Filing Sentiment Analytics | Other / Event Data | Other (3/0) | 16 / 27 | 6 (5/1, 1) | 0/0 (21) | sentiment |
| 22 | D | forward_beta_risk — Forward Beta Risk Prediction Model | Model / Estimates Models | Model (19/0) | 8 / 13 | 5 (2/3, 3) | 0/0 (28 MATRIX at cov 0.80, 14 V) | ml-prediction 3, analyst-revision 2 |
| 23 | D | forum_sentiment — Global Stock Forum Sentiment Signals | Other / AI-ML | Other (3/0) | 9 / 16 | 5 (5/0, 1) | 0/0 (13) | sentiment 4, valuation 1 |
| 24 | D | other7 — Archive News Data | News / News | **News (2/1)** | 82 / 303 | 5 (4/1, 2) | 0/0 (10) | sentiment |
| 25 | D | other326 — Intermediate Data from Events | Other / Event Data | Other (3/0) | 250 / 1,165 | 5 (5/0, 0) | 0/0 (17 MATRIX not dense, 36 V) | profitability 4, earnings-event 1 |
| 26 | E | equity_forum_data — International Equity Forum Activity | Other / Event Data | Other (3/0) | 0 / 0 | 4 (4/0, 0) | 0/0 (8, cov ≤ 0.58) | sentiment |
| 27 | E | analyst_base_ref — Analyst Estimates Base Reference | Analyst / Analyst Estimates | Analyst (3/0) | 13 / 16 | 4 (4/0, 0) | 0/6 (22) | profitability 2, analyst-revision 2 |
| 28 | E | pv73 — Custom Relationship Data | Price Volume / Relationship | PV (40/0) | 16 / 39 | 4 (4/0, 0) | 0/0 (69) | analyst-rating |
| 29 | E | us_equity_news — US Equity Quantitative News Sentiment | Other / AI-ML | Other (3/0) | 23 / 42 | 4 (3/1, 1) | 0/0 (8) | sentiment 3, news 1 |
| 30 | E | pv109 — Bond Yield Data | Price Volume / Price Volume | PV (40/0) | 27 / 46 | 4 (4/0, 0) | 0/0 (34, cov 0.28) | payout-yield |
| 31 | E | model243 — Combined Alpha Model | Model / Valuation Models | Model (19/0) | 88 / 131 | 4 (4/0, 0) | 0/0 | sentiment |
| 32 | E | earnings_sent_matrix — Global Earnings Call Sentiment Matrix (hyp `earnings_call_tone_drift`, in no composite) | Earnings / Earnings Estimates | Earnings (3/0) | 191 / 492 | 4 (3/1, 3) | 0/0 | sentiment |
| 33 | E | earnings_risk — Earnings Event Risk Model | Other / Analyst Models | Other (3/0) | 3 / 4 | 3 (3/0, 0) | 0/0 (9, cov ≈ 0.3) | earnings-event 2, profitability 1 |
| 34 | E | event_stock_model — Corporate Event Driven Stock Model | Model / ML-AI Models | Model (19/0) | 15 / 26 | 2 (2/0, 0) | 0/0 | profitability |
| 35 | E | other623 — Text Blob News data | Other / Analyst Models | Other (3/0) | 17 / 24 | 2 (2/0, 0) | 0/0 | sentiment |
| 36 | E | analyst92 — Linear, nonlinear, region-specific models | Analyst / Analyst Estimates | Analyst (3/0) | 47 / 116 | 2 (0/2, 1) | 0/0 | news 1, investment 1 |
| 37 | E | analyst34 — Dividend forecasts model | Analyst / Analyst Estimates | Analyst (3/0) | 53 / 150 | 2 (2/0, 0) | 0/0 | payout-yield |
| 38 | E | analyst46 — Analyst Investment insight Data | Analyst / Crowdsourced Estimates | Analyst (3/0) | 81 / 226 | 2 (2/0, 1) | 0/0 | sentiment |
| 39 | E | fundamental69 — Quarterly Fundamental Data | Fundamental / Fundamental Data | Fundamental (4/0) | 102 / 169 | 2 (2/0, 1) | 0/4 | cashflow |
| 40 | E | model141 — Interest Rate Sensitivity Measures | Model / Risk Based Models | Model (19/0) | 211 / 1,087 | 2 (2/0, 0) | 0/0 | payout-yield |

Observation on the labels (not on data): the strictly untouched pool is thin in dense MATRIX signed fields —
9 datasets, 120 fields, 100 of them "sentiment". The rest of the untouched pool is VECTOR (news streams,
transcripts, filings) or has no labelled sign (70 datasets, e.g. `creator_signal_perf`, `board_gov_stats`,
`imbalance5`, `expected_move` with 43 dense MATRIX fields and 1 sign). Under Khoa's 2026-09-04 rule (dense
MATRIX first, VECTOR in `later/`) the near-untouched tier below is the larger dense pool.

### 1b. Tier T — reached only by the typed A/B arm's random draws (no hand-written hypothesis; 1–63 rows)
| id — name | cat | cell (n/need) | users / alphas | dMs/dM | rows USA (all typed) | best Sharpe (any typed row) | signed domains |
|---|---|---|---|---|---|---|---|
| ai_news_scores — (AI news scores) | Other | Other (3/0) | 20 / 39 | 65/105 | 2 | 1.25 | sentiment 65 |
| continuation_score | Price Volume | PV (40/0) | 23 / 66 | 132/560 | 9 | 1.07 | "sentiment" 132 on a PV dataset — label domain to verify |
| multi_horizon_alpha | Model | Model (19/0) | 34 / 68 | 281/517 | 59 | 1.24 | cashflow 115, leverage 99, profitability 96 |
| mmp_nlp_sentiment | Other | Other (3/0) | 50 / 154 | 363/1,616 | 16 | 0.85 | sentiment 345 |
| analyst_revision_horizons | Model | Model (19/0) | 75 / 188 | 194/816 | 63 | 0.86 | analyst-revision 195, analyst-estimate 39 |
| news85 | News | **News (2/1)** | 77 / 130 | 15/20 | 1 | −0.54 | sentiment 18 |
| predictive_starmine | Model | Model (19/0) | 90 / 271 | 589/1,186 | 42 | 1.22 | analyst-revision 273, analyst-estimate 97, profitability 82 |
| news59 | News | **News (2/1)** | 98 / 186 | 47/57 | 7 | 0.33 | profitability 33, earnings-event 22 |
| news97 | News | **News (2/1)** | 114 / 224 | 65/105 | 1 | −0.53 | sentiment 65 |
| other596 | Other | Other (3/0) | 148 / 324 | 260/420 | 6 | 0.19 | sentiment 260 |
The Sharpe column is reported because the task asks for it; it played no part in the order (users ascending
within bucket A/B). A typed-arm row is one random formula, not a test of the dataset (§11y: typed p50 0.11).

## 2. Raw material for the top 12 untouched datasets (fields, literature domain, cross-domain partner)
Sign rationale = the `DOMAIN_SIGN` citation in `forge/labels.py` (EX-ANTE) or the description's own words.
"Partner" = a different, already-labelled domain that existing legs carry with signed dense MATRIX fields on
USA/d1 — profitability / accruals / cashflow (fundamental6/7/72), short-flow (us_short_sale,
short_interest_pred), option IV (option3/8), insider-flow (insider_agg_matrix), analyst-revision
(analyst_factor_signals), leverage/credit (model36) — listed as candidates only; no mechanism is asserted.

1. **nlp_news_scores** (daily MATRIX, cov 0.90, 21 users). `negative_sentiment_average` (−, description:
   "Average negative sentiment score"), `positive_sentiment_average` (+, prior), `negative_sentiment_maximum`
   (−), `negative_sentiment_stddev` (−; kind dispersion). 28 of 50 signs read from the description; the
   dataset separates the positive and negative channels (12 dispersion + 6 count fields unsigned).
   Literature: Tetlock 2007 (media pessimism → short-horizon returns). Partners: short-flow, profitability/accruals, option IV.
2. **news82** (daily means of per-headline scores, MATRIX cov 0.98, 52 users). `mean_headline_sentiment_score`,
   `mean_primary_headline_sentiment`, `mean_secondary_headline_sentiment`, `median_headline_sentiment_score`
   (all +, prior; kind labelled "level"). Two sentiment streams and mean-vs-median of the same day are the
   only structure. Literature: Tetlock 2007. Partners: profitability/accruals, short-flow, analyst-revision.
3. **news84** (press-release events, MATRIX cov 1.00, 58 users). `mean_sentiment_score_transfer`,
   `max_sentiment_score_transfer` ("scale [−1, 1]"), `mean_primary/secondary_sentiment_score_transfer` (+, prior).
   Same construct as news82 on PR events rather than headlines. Partners: as news82; earnings-event (PEAD, Bernard-Thomas 1989).
4. **news46** (RavenPack-derived, MATRIX cov 0.98–1.00, 324 users). `mws46_ravenpack_mean_ssc` (+, description:
   "higher values indicate more positive tone"), `mws46_ravenpack_mean_ess_fast_d1` ("values above 50 indicate
   positive sentiment"), `mws46_ravenpack_sum_ssc`. 6 count fields unsigned (attention). Partners: short-flow, option IV, profitability.
5. **model37** — Text Mining Data (credit-language ranks, MATRIX cov 0.87–0.92, 415 users / 4,959 alphas).
   `default_probability_percent_2` (−, description: "higher values indicate higher credit risk"),
   `balance_sheet_language_score_2`, `legal_obligation_language_score_2`, `profitability_language_score_2`
   (all labelled leverage −, prior, although each description says "higher rank indicates safer credit" —
   the prior and the wording point in OPPOSITE directions; the label file is wrong on these 3 and the
   Researcher must read the description). Literature: Penman-Richardson-Tuna 2007 (leverage −, the labels.py
   prior); the credit-distress literature is for the Researcher to fetch (Q14). Partners: profitability, accruals, short-flow.
6. **fundamental13** — Comprehensive Fundamentals (quarterly MATRIX cov 0.97, 1,422 users). `fnd13_mtps`
   (Pretax Margin, +), `fnd13_rkdincomestatementq_cnin` (Net Income, +), `_tbie` (Net Income Before Taxes),
   `_nibx` (Net Income Before Extra Items) — all profitability priors (Novy-Marx 2013). The 3 "earnings-event"
   fields are `Original Announcement` dates (label slip). Raw levels need a normaliser (ensemble leg-scale law).
   Partners: accruals (income − cash flow, Sloan 1996), analyst-revision, short-flow.
7. **news18** — RavenPack (event MATRIX cov 1.00 on the mean fields, 8,772 users / 56,384 alphas — the most
   crowded dataset in the table). `mean_composite_sentiment_score`, `mean_earnings_evaluation_sentiment`,
   `mean_merger_acquisition_sentiment`, `mean_corporate_action_sentiment` (+, prior) — sentiment split by
   news TOPIC, which none of news82/84/46 has. Partners: earnings-event, short-flow, insider-flow.
8. **model12** — Stock Selection Model (daily percentile components, MATRIX cov 1.00, 265 users).
   `mdl12_factor_momentum_component` (+, description: "higher scores suggesting stronger recent price
   momentum that might persist"), `mdl12_liquidity_shock_component` (+), `mdl12_seasonality_component` (+),
   `mdl12_reversal_component` (labelled + from "higher values suggesting greater expected reversal" — the sign
   for RETURNS is ambiguous; treat as unstated). Literature: none in labels.py for price-technical — the
   momentum / seasonality papers are for the Researcher to fetch (Q14). Partners: profitability, analyst-revision, short-flow.
9. **earnings2** — Financial Event Calendar (606 users). The 4 signed fields are `ern2_earnrelease_d1_calendar_prev/next`
   and `ern2_earnconfcall_d1_calendar_prev/next` — DATES labelled profitability by the coarse rule. No usable
   sign; usable only as a timing gate (days to / since release) around another dataset's signal. Partners: any event-window signal.
10. **news_sentiment_dl** (VECTOR, cov 1.00, 11 users; 88 fields, 40 signed, 24 from the description).
    `mean_negative_word_sentiment_inferess` (−), `max_negative_word_sentiment_inferess` (−),
    `mean_positive_word_sentiment_inferess` (+), `min_positive_word_sentiment_inferess` (+). Needs a `vec_*`
    reducer (`later/` rule). Partners: as nlp_news_scores.
11. **news92** — Standardized Financial News Categorization (VECTOR, cov 1.00, 120 users). `mws92_bbgnews_score_m5`
    (+, description: "[−1, 1]; higher means more positive"), `mws92_djnews_score_m3`, `mws92_dowjones_newswires_score_m1`,
    `mws92_newsquantified_score_m5` — the same headline scored by 5 models across several wires; 8 code fields
    (source/category) unsigned. Partners: short-flow, option IV, earnings-event.
12. **news87** — Smart Conference-call transcript data (VECTOR, cov 0.73, 480 users). `mws87_neg_logit_all` (−,
    description), `mws87_neg_logit_pres` (−), `mws87_corppart_neg_logit_pres` (−), `mws87_sent_score_all` (+,
    prior), `mws87_sent_score_pres` (+). Sections (presentation vs Q&A, corporate vs analyst participants) are
    the structure; 50 count fields unsigned. Literature: Tetlock 2007 (the labels.py prior); earnings-call
    tone papers are for the Researcher to fetch (Q14). Partners: profitability/accruals, analyst-revision, short-flow.

Alternates 13–15 if a slot above is dropped: fundamental14 (Audit Analytics, cashflow/profitability VECTOR,
1,231 users), news23 (M&A deals, earnings-event VECTOR, 59 users), forward_beta_risk (`downside_tail_dependence`
−, `predicted_beta_change_3m`, MATRIX at cov 0.80, 8 users — the only untouched dataset with a risk domain).

## 3. USA/d1 pyramid cells (read 2026-09-08 09:30 UTC; UNLOCK_AT = 3)
| cell | alphas / need | mult | datasets on USA/d1 | filled by a current composite? | untouched / tier-T datasets that could fill it |
|---|---|---|---|---|---|
| Social Media | 0 / **3** | 1.0 | 4 | yes (twitter_sentiment_l2: usa_twitter_x_*) | creator_signal_perf (U, 40 users, 102 VECTOR fields, 0 signed; `later/social_creator_net_bias_contrarian`); socialmedia8/12 (T, 6,161 / 23,080 users) |
| Imbalance | 0 / **3** | 1.0 | 1 | **no** | imbalance5 only (U, 1,364 users, 2 fields: `imb5_mktcap` size, `imb5_score` 0–1 "oil-shock resilience" score, unsigned) |
| Sentiment | 1 / **2** | 1.4 | 10 | yes (news_sentiment_transfer: short_x_sentiment, usa_sentiment_x_*) | sentiment26 (U, 1 sign), sentiment7/27 (U, 0 signs); T: sentiment22/23/21 (229–512 users, 131–158 dense signed each), news_transformer_scores (80 users, 193 signed VECTOR), other553 |
| News | 2 / **1** | 1.2 | 31 | **no** (news29/news73 only in `later/`) | U: news82, news84, news46, news18 (dense MATRIX signed) + news92, news23, news48, news104, news17, news31, other7, news76 (VECTOR); T: news59, news97, news85, news7, news50 |
| Insiders | 2 / **1** | 1.1 | 5 | yes (insider_agg_matrix: usa_insider_x_*) | board_gov_stats (U, 85 users, 39 dense MATRIX, 0 signed — departure rates, connections); T: insiders4/1/3 (398–1,100 users) |
| Short Interest | 2 / **1** | 1.1 | 6 | yes (us_short_sale, short_interest_pred — the 2 ACTIVE alphas and the 16 blocked candidates live here) | shortinterest24 (U, 167 users, 1 field); T: shortinterest29 (92 users, 9 signed VECTOR), shortinterest43 (423 users, 32 dense MATRIX unsigned), shortinterest3 (900 users, 13 signed) |
| full (≥ 3) | PV 40, Model 19, Fundamental 4, Option 4, Analyst 3, Other 3, Earnings 3, Risk 3, Institutions 3, Macro 3 | | | composites cover Fundamental, Model, Analyst, Option, Other, Institutions; none covers PV, Earnings, Risk, Macro | — |

Top-40 datasets that fill a cell **no current composite fills**: the 11 News rows (#2, 3, 4, 7, 11, 14, 16,
17, 18, 20, 24; news76 is #41) → News needs 1; earnings2 and earnings_sent_matrix → Earnings (full);
pv73 / pv109 → PV (full). Imbalance needs 3 and has one 2-field unsigned dataset: **a cell that cannot be
filled from labelled signs** — it needs a sign-free construction or is left. Social Media needs 3 with one
composite family (twitter) whose best rows are 1.29–1.31 (§11w) and one untouched unsigned dataset.

## 4. What is crowded (measured wall: prod-corr ≈ 0.8 on the 16 Short Interest candidates)
Composite datasets with userCount > 200, and the USA/d1 journal rows per dataset (a row counts once for
every composite dataset it uses; the per-dataset sum is 19,648 over 10,686 rows):
| dataset | cat | users / alphas | USA/d1 journal rows | used by |
|---|---|---|---|---|
| fundamental6 | Fundamental | **84,692 / 821,096** | 4,294 | 11 composites (usa_profitability_ratios, usa_accruals_cashflow, usa_rd_intensity) — the profitability/accruals leg of the 2 ACTIVE alphas |
| option8 | Option | **31,231 / 170,386** | 2,004 | 5 IV-spread composites |
| model16 | Model | 4,202 / 9,547 | 0 | quality_x_accruals_composites |
| fundamental7 | Fundamental | 1,959 / 20,694 | 6 | 11 (profitability_classic_ratios …) — reached only on other regions |
| fundamental72 | Fundamental | 662 / 2,771 | 60 | 11 |
| institutions20 | Institutions | 456 / 1,004 | 0 | short_volume_ratio_informed (4 composites) |
| model36 | Model | 260 / 2,727 | 0 | smartratios_credit_safety (5) |
| option3 | Option | 214 / 372 | 1,048 | 5 IV-spread composites |
Quiet composite datasets, by rows: us_short_sale 4,306 rows (56 users; 2 ACTIVE + 16 blocked), news_sentiment_transfer
3,493 (37), twitter_sentiment_l2 2,525 (77), insider_agg_matrix 1,050 (29), short_interest_pred 773 (96).
Not in any composite although named as crowded: **model77** (8,887 users / 150,364 alphas, 3,256 dense MATRIX
fields) — 76 USA/d1 rows, all typed-arm; **pv1** (close/volume/…) appears in **1 of 10,646** USA/d1 rows —
the composites are carrier-free as designed. **fundamental23** (1,499 users): 57 USA/d1 rows, all typed; 207
rows on other regions by the current arm.

## 5. Caveats
- Signs are EX-ANTE labels (description or textbook prior), not measurements; 3 of the 12 datasets above
  carry visible label slips (model37 credit-language ranks, earnings2 dates, fundamental13 announcement dates).
  Nothing in this file says a dataset works.
- The catalogue is 2026-07-15 and the survey 2026-09-04; 9 datasets appear in the labels' USA/d1 regions but
  not in the survey (fundamental90, model14/38/50, pv27, china_*); they are omitted.
- "Untouched" counts journal rows since 2026-09-04 (the forge journal). Older loops (`climb.jsonl`, 63 MB, to
  09-04; August `fact_*`/`loop_*`) were not scanned: a dataset may have been simulated by the climb era.
  MECHANISM for anything here: UNKNOWN until simulated.
