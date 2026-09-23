# harness5 round 1 — Verifier audit of the 8 `arm: new` composites against the 8 hard gates

Written 2026-09-08 by the Verifier (not the author of any object scored). Objects: 8 new legs + 8 composites
dated 2026-09-08 18:40, partner legs already in the library. Nothing was simulated or posted (RULE 1). Every
number below was re-derived from the file named next to it; labels: EX-ANTE = derived from code/documentation,
OBSERVED = counted in a file, SPECULATION = marked as such.

Inputs: fetched/hypothesis_standard.md L14-22 (gates, read verbatim), forge/compose.py (combiner semantics),
forge/hypotheses.py (schema), fetched/rc/fields/USA_TOP3000_d1.jsonl (field rows), forge.labels (label file),
fetched/rc/datasets_survey.json[USA_TOP3000_d1] (dataset counts), VPS /opt/wq/state/layered/runs/forge.jsonl read-only
(20,781 rows, 64 MB, last row 2026-09-08T07:20:33-04:00, 0 rows with `"arm": "new"`), state/*targets*.json (27 files),
citation records via OpenAlex / Semantic Scholar / Crossref (publisher pages all returned 403; SSRN resolves to 127.0.0.1 here).

## 1. Verdict table

| composite | new leg (dataset; users/alphas) | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| newsneg_x_short | news_negative_tone_nlp (nlp_news_scores; 21/32) | P* | P | P (cite fix) | P | P | **TRIP gate branch** / P multiply | P | P | **FIX: combiners → [multiply]**, then SIM |
| headline_x_profitability | news_headline_tone_benzinga (news82; 52/324) | P* | P | P | P† | P | P | P | P | SIM |
| prtone_x_accruals | news_pr_event_tone (news84; 58/102) | P* | P | P (venue fix) | P† | P | P | P | P | SIM (+fix) |
| ravenpack_x_short | news_ravenpack_composite_tone (news46; 324/924) | P* | P | P | P | P | P (density fix) | P | P | SIM (+fix) |
| creditlang_x_accruals | credit_language_safety (model37; 415/4,959) | P* (wording) | P | P | P† | P | P | P | P | SIM (+fix) |
| headline_x_momentum_gate | model12_momentum_component (model12; 265/2,103) as gate | P* | P (fix) | P | P (map contradicts weakens_when) | P | P (indicator-dominated, §2A) | P | P | **FIX before SIM** |
| multiwire_x_profitability | news_multiwire_headline_tone (news92 VECTOR; 120/492) | **FIX** (no force named) | P | P | P† | P | P | P | P | SIM after text fix |
| transcriptneg_x_revision | transcript_negative_logit (news87 VECTOR; 480/2,494) | P* | P | P (Price 2012 record-only) | P | P | **TRIP gate branch** / P multiply | P (cov 0.71–0.73) | P | **FIX: combiners → [multiply]**, then SIM |

P* — passes on substance; the force tag {risk-premium / behavioral-mispricing / institutional-friction} that gate 1 requires
is not a field in the YAML schema (forge/hypotheses.py REQUIRED / dataclass — an extra key raises "unknown keys"), so no
composite in the library, current arm included, carries one; I inferred the tag from the text (all eight: behavioral
mispricing via slow diffusion / under-reaction). † — partner leg fundamental6 fields have alphaCount 15,084–169,009 (≥ 750);
they are the conditioning leg, not the primary bet, and the "every leg ≥ 200" clause is not met (new-leg fields ≤ 67).
No composite trips a gate on the letter of §1 of the standard; the two TRIPs are of one compiled branch (§2A).

## 2. Cross-cutting findings

**A. `gate` combiner semantics (EX-ANTE, read from forge/compose.py `combine`, L37-41).**
`combine(a, b, "gate") = if_else(greater(B⁺, 0.5), A, 0)` where B⁺ = positive form of the PARTNER (a `-group_rank` leg becomes
`(1 - group_rank)`) and A = the new leg's formula UNCHANGED, leading "-" included. Two consequences:
(i) the condition is always "partner says GOOD". For a story "bearish A confirmed by bearish B" that is inverted:
newsneg_x_short trades negative tone only among the LESS-shorted half; transcriptneg_x_revision trades negative call tone only
among the UPWARD-revision half. (ii) STATISTICAL/INDUSTRY/SUBINDUSTRY neutralization demeans the output. The gated-out half sits
at exactly 0; the traded half has mean +0.5 (A = +rank) or −0.5 (A = −rank). After demeaning, the gated-out half is uniformly
SHORT for a positive A and uniformly LONG for a negative A. So newsneg_x_short's gate branch longs the more-shorted half and
transcriptneg_x_revision's longs the downward-revision half — each the opposite of the partner paper's documented sign
(BJZ 2008: "Heavily shorted stocks underperform lightly shorted stocks by a risk-adjusted average of 1.16% over the following
20 trading days"; CJL 1996: "Past return and past earnings surprise each predict large drifts in future returns"). For the
five positive-A composites the same arithmetic makes the gate branch a partner-half indicator (profitable / low-accrual /
less-shorted / high-momentum half; a 0.5 step between halves against a within-half sd ≈ 0.29 under uniform ranks) with tone
modulating the long side only. This is a property of the harness combiner — 25 of 36 library composites list `gate`, 17 of 28
in the current arm — not of the Researcher's text; the two bearish-A composites are the only ones where it reverses a cited
sign. The multiply-vs-if_else gap the standard measured on model77 (1.95 vs 1.58) was not re-examined here.

**B. Distinct-mechanism supply (the round's purpose, Q17).** OBSERVED: 8 composites = 6 mechanism keys. tone × short-flow
appears twice (#1 nlp_news_scores, #4 news46); tone × profitability twice (#2 news82, #7 news92). Families were named apart
(tone / tone_multiwire / tone_negative / tone_composite) so the code's cross-family check passes; by the desk rule
(one submit retires a family) they are one key each. news82's leg is used by #2 and #6. Five of eight new legs are a news-tone score.

**C. Regime maps.** All eight composites carry the identical map {value_winter +, momentum_crash_2016 0, covid_2020 +,
rate_shock_2022 +}. Gate 4 asks that a map be stated; it is. OBSERVED: boilerplate. headline_x_momentum_gate's map
(covid_2020 "+", 2016 "0") contradicts its own weakens_when ("momentum crashes (2009, 2016, 2020)").

**D. Label file vs description.** forge.labels gives the model37 credit-language fields sign "−" (rule `(higher|larger|greater) (value`
fired on "higher scores indicate lower credit risk") and files news87 under domain analyst-estimate / event_stream
estimate-submission. The Researcher's overrides (model37 "+", news87 = call tone) follow the description wording; the label
rules are the errors (out of scope here, flagged to the Operator).

**E. Journal collision.** The substring count `negative_sentiment_average` = 2 is `negative_sentiment_average_post`
(dataset news_transformer_scores, typed arm, alpha pwP8MgpX, sharpe 0.36, 2026-09-07) — a different field. `grep -c -w`
for all 22 new-leg fields = 0; state/*targets*.json = 0 for all 22; journal rows with arm=new = 0. Nothing spent yet.
Partner fields are in use (substring rows: executed_short_trade_share_count 2,718; cashflow_op 2,575; operating_income 3,672),
so novelty rests on the new leg, which the pre-sim signature gate (forge/gates.py) checks per candidate.

**F. Q14 (unfetchable ⇒ dropped).** Every citation's bibliographic record was fetched (HTTP 200 on ≥ 1 index) — no fabricated
citation. Abstract TEXT was obtained for 12 of 18; for the five Elsevier papers (Chan 2003, Price 2012, ERR 2012, Novy-Marx 2013,
FF 2015) and Bernard-Thomas 1989 all three indexes carry no abstract and the publisher page is 403. Read strictly, Q14 drops those
six from source lines. Consequence per composite: none loses its last text-verified citation except the CONSTRUCT citation of
the transcript leg (Price 2012) and the news-vs-no-news claim of #6 (Chan 2003) — fixes in §5.

## 3. Citation fetch ledger

| # | citation (used by) | fetched at | HTTP | status | verbatim sentence / note |
|---|---|---|---|---|---|
| 1 | Tetlock 2007 JF (#1 #2 #4 #7) | api.openalex.org/works?search=Giving Content to Investor Sentiment | 200 (Wiley 403) | text | "I find that high media pessimism predicts downward pressure on market prices followed by a reversion to fundamentals" — MARKET level (WSJ column vs Dow); legs are firm-level |
| 2 | Tetlock, Saar-Tsechansky & Macskassy 2008 JF (#2 #3 #4 #7) | api.openalex.org/works/https://doi.org/10.1111/j.1540-6261.2008.01362.x | 200 (Wiley 403; S2 200 abstract null) | text | "(2) firms' stock prices briefly underreact to the information embedded in negative words" |
| 3 | Bernard & Thomas 1989, cited "JAE" (#3) | api.crossref.org/works/10.2307/2491062; OpenAlex; S2 | 200 (JSTOR error page) | record | venue = Journal of Accounting Research, not JAE; indexes hold keywords only |
| 4 | Campbell, Hilscher & Szilagyi 2008 JF (#5) | api.semanticscholar.org …DOI:10.1111/j.1540-6261.2008.01416.x; OpenAlex | 200 (Wiley 403) | text | "Since 1981, financially distressed stocks have delivered anomalously low returns." |
| 5 | Dichev 1998 JF (#5) | api.openalex.org/works/https://doi.org/10.1111/0022-1082.00046 | 200 (Wiley 403) | text | "Surprisingly, firms with high bankruptcy risk earn lower than average returns since 1980." |
| 6 | Jegadeesh & Titman 1993 JF (#6) | api.openalex.org/works/https://doi.org/10.1111/j.1540-6261.1993.tb04702.x | 200 (Wiley 403) | text | "strategies which buy stocks that have performed well in the past and sell stocks that have performed poorly in the past generate significant positive returns over 3‐to 12‐month holding periods" |
| 7 | Chan 2003 JFE (#6) | api.crossref.org/works/10.1016/s0304-405x(03)00146-6; OpenAlex; S2 | 200 (ScienceDirect 403) | record | title/venue/year verified; abstract withheld by publisher on all three indexes |
| 8 | Price, Doran, Peterson & Bliss 2012 JBF (#8) | api.crossref.org/works/10.1016/j.jbankfin.2011.10.013; OpenAlex; S2 | 200 (ScienceDirect 403) | record | title verified ("...incremental informativeness of textual tone"); abstract withheld |
| 9 | Mayew & Venkatachalam 2012 JF (#8) | api.openalex.org/works/https://doi.org/10.1111/j.1540-6261.2011.01705.x | 200 (Wiley 403) | text | "We measure managerial affective states during earnings conference calls by analyzing conference call audio files using vocal emotion analysis software." — VOCAL construct, not the textual logit |
| 10 | Boehmer, Jones & Zhang 2008 JF (#1 #4, partner) | api.semanticscholar.org …DOI:10.1111/j.1540-6261.2008.01324.x; OpenAlex | 200 (Wiley 403) | text | "Heavily shorted stocks underperform lightly shorted stocks by a risk-adjusted average of 1.16% over the following 20 trading days (15.6% annualized)." |
| 11 | Engelberg, Reed & Ringgenberg 2012 JFE (#1) | api.crossref.org/works/10.1016/j.jfineco.2012.03.001; OpenAlex; S2 | 200 (ScienceDirect 403) | record | title verified; abstract withheld |
| 12 | Novy-Marx 2013 JFE (#2 #7, partner) | api.crossref.org/works/10.1016/j.jfineco.2013.01.003; OpenAlex; S2 | 200 (ScienceDirect 403) | record | title verified; abstract withheld |
| 13 | Sloan 1996 TAR (#3 #5, partner) | api.openalex.org/works?search=…&filter=publication_year:1996 → doi 10.2308/tar-9608042309 | 200 (JSTOR 403) | text | "Investigates whether stock prices reflect information about future corporate earnings contained in accrual and cash flow components of currents earnings." (index summary) |
| 14 | Chan, Jegadeesh & Lakonishok 1996 JF (#8, partner) | api.crossref.org/works/10.1111/j.1540-6261.1996.tb05222.x; OpenAlex | 200 (Wiley 403) | text | "Past return and past earnings surprise each predict large drifts in future returns after controlling for the other." |
| 15 | Diether, Lee & Werner 2009 RFS (partner short leg) | api.openalex.org/works/https://doi.org/10.1093/rfs/hhn047 | 200 (OUP page truncated) | text | "Short sellers increase their trading following positive returns and they correctly predict future negative abnormal returns." |
| 16 | Fama & French 2015 JFE (partner profitability leg) | api.crossref.org/works/10.1016/j.jfineco.2014.10.010; OpenAlex | 200 (ScienceDirect 403) | record | title verified; abstract withheld |
| 17 | Hribar & Collins 2002 JAR (partner accruals leg) | api.openalex.org/works?search=Errors in Estimating Accruals | 200 (Wiley 403) | text | "studies using a balance sheet approach to test for earnings management are potentially contaminated by measurement error in accruals estimates" |
| 18 | Gleason & Lee 2003 TAR (partner revisions leg) | api.openalex.org/works/https://doi.org/10.2308/accr.2003.78.1.193 | 200 (AAA 403; S2 abstract null) | text | "the market does not make a sufficient distinction between revisions that provide new information ... and revisions that merely move toward the consensus" |
| R1 | Larcker & Zakolyukina 2012 JAR (replacement candidate, #8) | api.openalex.org/works/https://doi.org/10.1111/j.1475-679X.2012.00450.x | 200 | text | "We estimate linguistic‐based classification models of deceptive discussions during quarterly earnings conference calls." |
| R2 | Loughran & McDonald 2011 JF (replacement candidate, textual tone) | api.openalex.org/works/https://doi.org/10.1111/j.1540-6261.2010.01625.x | 200 | text | "Previous research uses negative word counts to measure the tone of a text." |

Four DOIs I typed from memory returned 404 on Semantic Scholar (Tetlock 2007, Chan 2003, CJL 1996, Hribar-Collins 2002);
each resolved by title search — Verifier error, not a citation defect.

## 4. Evidence per composite (field rows from USA_TOP3000_d1.jsonl: type | coverage | alphaCount | userCount | description)

**#1 newsneg_x_short** — legs news_negative_tone_nlp (−) × short_volume_ratio_informed (−); combiners [multiply, gate].
Fields: negative_sentiment_average MATRIX | 0.9017 | 2 | 2 | "Average negative sentiment score."; negative_sentiment_average_3 | 0.9017 | 0 | 0 |
"Average negative sentiment score for the stock on that day, aggregated from mapped stories"; negative_sentiment_average_5 | 0.9017 | 1 | 1 |
"...based on mapped Bloomberg market-moving news stories". Partner: executed_short_trade_share_count MATRIX 1.0 | 10 | 7;
reported_short_sale_share_quantity 1.0 | 11 | 6; inst20_sq_sv 1.0 | 150 | 118; denominators 10 / 13 / 437 alphas.
Sign: a NEGATIVE channel, leg −1, template `-group_rank(ts_mean(add(x,0,filter=true), w), g)` → short the most negative: consistent;
zero-fill correct (no negative story = 0). Compiled multiply: `multiply((1 - group_rank(ts_mean(add(negative_sentiment_average, 0, filter=true), 3), subindustry)), (1 - group_rank(ts_mean(executed_short_trade_share_count / aggregate_executed_trade_share_count, 5), subindustry)))`
→ long least-negative AND least-shorted; any name failing either channel is shorted equally — the text's "only one channel fires → down-weighted"
is not what the product does (both corners get 0). Direction consistent with the mechanism; text needs the mirror. Compiled gate:
`if_else(greater((1 - group_rank(short ratio)), 0.5), -group_rank(neg tone), 0)` → inverted (§2A). Citations: Tetlock 2007 text
(market-level; the firm-level negative-word construct is TSM 2008, not cited by this leg), BJZ 2008 text, ERR 2012 record.
Journal exact 0; targets 0. Dim 5: multiply of two [0,1] ranks, cross-family, confirmation on the clean corner — fits; gate does not.

**#2 headline_x_profitability** — news_headline_tone_benzinga (+) × usa_profitability_ratios (+); [multiply, gate].
Fields: mean_headline_sentiment_score MATRIX | 0.9814 | 1 | 1 | "Daily mean of the primary sentiment scores across all D1 Benzinga headlines for a stock-day";
median_headline_sentiment_score | 0.9814 | 0 | 0; mean_primary_headline_sentiment | 0.9814 | 0 | 0 ("stream 1 sentiment scores"). The descriptions do not
state which direction is positive; the label's "+" is a domain prior (Tetlock 2007), so the leg's +1 is convention, declared ex ante.
Partner fundamental6 (84,692 users / 821,096 alphas): operating_income 67,731; income 15,084; assets 169,009; equity 27,790 (all cov 0.5).
Compiled multiply: `multiply(group_rank(ts_mean(add(mean_headline_sentiment_score, 0, filter=true), 3), subindustry), group_rank(ts_rank(operating_income / assets, 126), subindustry))`
→ long positive tone AND profitable: matches the text. Gate branch = profitable-half indicator + tone on the long side (§2A(ii)).
Citations: Tetlock 2007 text, TSM 2008 text, Novy-Marx 2013 record. Journal exact 0; targets 0. Dim 5: fits (tone × profitability, both rank-bounded, confirmation).

**#3 prtone_x_accruals** — news_pr_event_tone (+) × usa_accruals_cashflow (−); [multiply, gate].
Fields: mean_sentiment_score_transfer MATRIX | 1.0 | 5 | 5 | "Daily mean of base sentiment scores across PR events (often weighted by article importance)";
mean_primary_sentiment_score_transfer | 1.0 | 3 | 3; max_sentiment_score_transfer | 1.0 | 2 | 2. Direction not stated; +1 by convention. Partner: income, cashflow_op (23,095), assets.
Compiled multiply: `multiply(group_rank(ts_mean(add(mean_sentiment_score_transfer, 0, filter=true), 5), subindustry), (1 - group_rank(ts_rank((income - cashflow_op) / abs(assets), 126), subindustry)))`
→ long positive PR tone AND low accruals: matches "keeps the credible positive announcements". Gate: tone traded in the low-accrual half — matches.
Citations: Sloan 1996 text, Bernard-Thomas 1989 record (venue JAR; PEAD is earnings-surprise drift — the leg uses it as analogy, the construct
citation is TSM 2008 via the leg, text). Journal exact 0; targets 0. Dim 5: fits.

**#4 ravenpack_x_short** — news_ravenpack_composite_tone (+) × short_volume_ratio_informed (−); [multiply, gate].
Fields: mws46_ravenpack_mean_ssc MATRIX | 1.0 | 58 | 24 | "Mean Composite Sentiment Score (0–100) ... higher values indicate more positive sentiment";
mws46_ravenpack_mean_ssc_fast_d1 | 1.0 | 3 | 3 | same description. Sign +1 consistent with the description. Compiled multiply:
`multiply(group_rank(ts_mean(add(mws46_ravenpack_mean_ssc, 0, filter=true), 5), subindustry), (1 - group_rank(ts_mean(short ratio, 5), subindustry)))`
→ long positive tone AND low shorting: matches "informed channels agree". Gate: tone traded in the less-shorted half — matches "short sellers absent".
Field-nature caveat: on a 0–100 scale with 50 = neutral, `density: zero` maps any missing stock-day to the most-negative end, not to "no news";
catalog coverage 1.0 says few or no gaps at USA d1, but the choice is wrong in kind → fix to `backfill` (§5). Citations: Tetlock 2007 text, BJZ 2008 text.
Journal exact 0; targets 0. Same mechanism key as #1 (§2B). Dim 5: fits.

**#5 creditlang_x_accruals** — credit_language_safety (+) × usa_accruals_cashflow (−); [multiply, gate].
Fields: balance_sheet_language_score MATRIX | 0.878 | 3 | 3 | "Global 1–100 rank based on language related to how the company structures its debt, stock, and
accounts; higher scores indicate lower credit risk"; legal_obligation_language_score | 0.878 | 2 | 2 | "...agreements with partners or financiers; higher scores
indicate lower credit risk"; profitability_language_score | 0.878 | 6 | 5 | "...earnings and profitability; higher scores indicate lower credit risk".
Sign +1 = long safest credit: consistent with the description and with CHS 2008 / Dichev 1998 (text, ledger 4-5); the label file's "−" is the label's error (§2D).
Compiled multiply: `multiply(group_rank(ts_mean(balance_sheet_language_score, 20), subindustry), (1 - group_rank(ts_rank((income - cashflow_op) / abs(assets), 126), subindustry)))`
→ long safe AND low accruals: matches. group_rank of a global 1–100 rank adds nothing alone (Law 1) — acceptable as a leg. Mechanism wording
"distress-averse ... investors under-price [quality]" is backwards (a distress-averse investor bids safe names UP); the counterparty line has it right.
Both legs are slow (filings language, quarterly fundamentals): cadence + decay 4/8 — LOW_TURNOVER risk unmeasured. Citations: CHS 2008 text, Sloan 1996 text.
Journal exact 0; targets 0. Dim 5: fits.

**#6 headline_x_momentum_gate** — news_headline_tone_benzinga (+) gated by model12_momentum_component (+); [gate] only.
Fields: mdl12_factor_momentum_component MATRIX | 0.9966 | 550 | 93 | "A percentile-ranked score (1-100) representing short-term momentum signals for a stock,
with higher scores suggesting stronger recent price momentum that might persist"; mdl12_seasonality_component | 0.9966 | 725 | 118 | "...seasonal or
calendar-based effects..." (the leg lists it, the mechanism text names momentum only). Compiled: `if_else(greater(group_rank(ts_mean(mdl12_factor_momentum_component, 5), subindustry), 0.5), group_rank(ts_mean(add(mean_headline_sentiment_score, 0, filter=true), 3), subindustry), 0)`
→ after demeaning: long book ⊂ top-momentum half, short book ≈ bottom-momentum half plus low-tone names in the top half — EX-ANTE a short-term-momentum
indicator book modulated by tone (§2A(ii)); the text's "negative tone with negative momentum" short corner is not expressed at all. Gate 4 on the letter:
map stated; 550/725 < 750; news82 leg ≤ 1 alpha so not every leg ≥ 200. Map contradicts weakens_when (§2C). Counterparty "index funds that rebalance
mechanically" does not lose to news under-reaction. Citations: JT 1993 text; Chan 2003 record (its construct is news-day vs no-news-day price moves,
not a momentum level — analogy). Journal exact 0; targets 0. Dim 5: gate-only, indicator-dominated; a `multiply` branch would express "tone in the
direction of momentum" on the long side.

**#7 multiwire_x_profitability** — news_multiwire_headline_tone (+, VECTOR) × usa_profitability_ratios (+); [multiply, gate].
Fields: mws92_bbgnews_score_m5 VECTOR | 1.0 | 10 | 9 | "Bounded continuous sentiment score in [-1, 1] for the headline; higher means more positive and suitable
for aggregation"; mws92_inferess_v2_score_m3 VECTOR | 0.9928 | 27 | 7 | "...higher means more positive sentiment; typical range about -19 to 21";
mws92_bbgnews_score_m3 VECTOR | 1.0 | 67 | 9 | "Sentiment score based on Model 3 evaluation of given news item" (direction not stated). `vector: vec_avg` declared;
compiled leg `group_rank(ts_mean(add(vec_avg(mws92_bbgnews_score_m5), 0, filter=true), 3), subindustry)` — zero-fill correct for a signed score.
Multiply with profitability as #2. Mechanism text is a construction description ("cleaner tone measure ... VECTOR stream, averaged per day") — no force,
no counterparty link inside the composite text (the leg supplies slow diffusion) → gate 1 FIX. Citations: Tetlock 2007 text, TSM 2008 text (leg), Novy-Marx 2013 record.
Journal exact 0; targets 0. Same mechanism key as #2 (§2B). Dim 5: fits.

**#8 transcriptneg_x_revision** — transcript_negative_logit (−, VECTOR) × analyst_estimate_revision_drift (+); [multiply, gate].
Fields: mws87_neg_logit_all VECTOR | 0.7304 | 32 | 22 | "The Negative Logit of ALL"; mws87_neg_logit_pres VECTOR | 0.7304 | 152 | 31 | "The negative logit of
presentation."; mws87_analyst_neg_logit_qa VECTOR | 0.7066 | 111 | 59 | "The Negative Logit of Sell Side Analysts in Q_A". `vector: vec_avg`, `density: backfill`,
window 63 (quarterly calls) declared; sign −1 (short most negative) consistent with "Negative Logit". Partner analyst_factor_signals (140 users / 297 alphas;
15 fields match the pattern at USA d1). Compiled multiply: `multiply((1 - group_rank(ts_backfill(vec_avg(mws87_neg_logit_all), 63), subindustry)), group_rank(ts_backfill(<x>_estimate_change_1m, 5), subindustry))`
→ long least-negative calls AND upward revisions; the text's "negative call + downward revisions" corner gets 0, the same as a negative call with upward
revisions. Compiled gate: `if_else(greater(group_rank(revision), 0.5), -group_rank(neg logit), 0)` → negative tone traded only in the UPWARD-revision half;
after demeaning the downward-revision half is LONG — inverted vs CJL 1996 / Gleason-Lee 2003 (§2A). Gate 7: coverage 0.71–0.73 → roughly a quarter of
names stay NaN after the 63-day backfill and drop out of the product (OBSERVED from the catalog; book-concentration effect unmeasured); the catalog lists
the fields at delay 1; the leg does not assert PIT. Citations: Price 2012 record only (the leg's construct citation), Mayew-Venkatachalam 2012 text
(vocal, not textual), CJL 1996 text. Journal exact 0; targets 0. Dim 5: multiply fits (call tone × revisions, cross-family); gate does not.

## 5. PULL before simulation

- No composite trips a hard gate on the letter of the standard; nothing is pulled outright.
- The `gate` branch of **newsneg_x_short** and **transcriptneg_x_revision** must not run (§2A: it longs the more-shorted / the
  downward-revised half — the opposite of the cited sign). If the one-line edit below is not on /opt/wq before the first arm=new
  batch, PULL both composites for that batch rather than spend ~half their candidates on an inverted construct.
- **headline_x_momentum_gate** should not run as written (gate-only ⇒ momentum-indicator book; map contradicts its own attenuation
  condition; shares its leg with #2). PULL until the edits below are applied; if the Operator wants 6 distinct keys rather than 8
  files (§2B), this is the one to drop.

## 6. FIX suggested (exact YAML edits)

1. forge/composites/newsneg_x_short.yaml: `combiners: [multiply, gate]` → `combiners: [multiply]`. Mechanism last sentence →
   "The compiled product multiply(1 − rank(neg tone), 1 − rank(short share)) is long the names that are both least negatively covered and
   least shorted; a name failing either channel is shorted."
2. forge/composites/transcriptneg_x_revision.yaml: `combiners: [multiply, gate]` → `combiners: [multiply]`. Mechanism last sentence →
   "The product is long the calls that sound least negative and are followed by upward revisions; a name failing either is shorted."
3. forge/hypotheses/news_negative_tone_nlp.yaml `source`: append "; Tetlock, Saar-Tsechansky & Macskassy 2008 JF (fraction of negative words in
   firm-specific news; prices briefly under-react)" — Tetlock 2007 is the market-level construct.
4. forge/hypotheses/news_pr_event_tone.yaml `source`: "Bernard & Thomas 1989 JAE" → "Bernard & Thomas 1989 JAR (Supplement)".
5. forge/hypotheses/transcript_negative_logit.yaml `source`: append "; Larcker & Zakolyukina 2012 JAR (linguistic models of quarterly earnings
   conference calls)" — the only text-verified textual-call citation; keep Price 2012 (record verified). Optionally Loughran & McDonald 2011 JF.
6. forge/hypotheses/news_ravenpack_composite_tone.yaml: `density: zero` → `density: backfill` + `density_window: 5` (50 = neutral on the 0–100 scale; 0 is the most negative value).
7. forge/composites/headline_x_momentum_gate.yaml: `regimes: {..., momentum_crash_2016: "-", covid_2020: "-", ...}` (consistent with weakens_when);
   counterparty: delete "; index funds that rebalance mechanically"; `combiners: [gate]` → `combiners: [multiply, gate]` so a rank-product branch exists.
8. forge/hypotheses/model12_momentum_component.yaml: `fields: [mdl12_factor_momentum_component, mdl12_seasonality_component]` → `fields: [mdl12_factor_momentum_component]`
   (seasonality has no mechanism sentence; alphaCount 725 sits at the 750 line).
9. forge/composites/multiwire_x_profitability.yaml mechanism: insert after the first clause "— the same slow-diffusion under-reaction as
   headline_x_profitability: growth-chasing investors under-weight the profits that positive news confirms —".
10. forge/composites/creditlang_x_accruals.yaml mechanism: "that distress-averse and accrual-naive investors under-price" → "left under-priced because
    yield-seeking holders over-pay for distressed equity and accrual-naive investors over-pay for accrual-driven earnings".
11. Harness, not round-1 YAML (Operator): (a) compose.combine("gate") should condition on the partner's positive form AND place the new leg's positive
    form inside the if_else (re-orienting afterwards) — until then `gate` is unsafe for any bearish A and is an indicator book for any A; (b) the gate-1
    force tag has no schema field, so standard.py cannot check it; (c) labels.py sign rule mis-reads "higher … lower credit risk" (model37) and files news87 as
    analyst estimates.
