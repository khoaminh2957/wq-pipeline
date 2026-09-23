# harness5 round 1 — Verifier audit of the STAGED library (7 composites, 12 legs)

Written 2026-09-09 (local; measured quota day ET 2026-09-09 in progress) by the Verifier, who authored none of the
objects scored. Scope: `forge/composites/staged/*.yaml` (7) and `forge/hypotheses/staged/*.yaml` (12), written
2026-09-08/09 by parallel researchers and unaudited until now. Nothing was simulated, nothing was posted, nothing on
the VPS or in the live `forge/hypotheses/`, `forge/composites/`, or the systemd unit was written (RULE 1; the
VPS was read with `ssh -n … grep` only). Every number below was re-derived from the file named next to it.
Labels: EX-ANTE = derived from code / documentation / a fetched abstract; OBSERVED = counted in a file;
SPECULATION = marked as such; UNKNOWN = no experiment distinguishes the candidates.

Inputs: `fetched/hypothesis_standard.md` L14–22 (the 8 hard gates, read verbatim); `forge/compose.py` L37–41
(combiner arithmetic); `forge/hypotheses.py` (schema, non-recursive `glob("*.yaml")` L217/L229 — staged/ and
pulled/ are invisible to the loader); `forge/standard.py` (`hard_gates`); `forge/typed.py` (`judge`, structural
and full); `fetched/rc/fields/USA_TOP3000_d1.jsonl` (47 field rows); `forge.labels.load()` (label per field);
`fetched/rc/datasets_survey.json` (dataset userCount); `docs/harness5/01_origins.md`, `02_dataset_map.md`,
`round_1.md`, `round_1/audit_hypotheses.md`; VPS `/opt/wq/state/layered/runs/forge.jsonl` (24,238 rows,
read-only, 2026-09-09; 1,070 rows carry `"arm": "new"`); 28 `state/*targets*.json`; `state/banned_fields.json`;
`state/climb/spent_fields.json`; 27 citation URLs fetched by this Verifier (WebFetch for text, `curl -w
%{http_code}` for status).

## 1. Verdict table

Gates: G1 typed mechanism with a middle link · G2 persistent concrete counterparty · G3 citation fetched, construct
matches · G4 regime map reasoned per sub-regime and not a copy · G5 falsifiable, no sign-fishing · G6 construction
(bearish leg ⇒ `[multiply]`, rank-bounded operands, VECTOR/backfill/density rules) · G7 fields exist at USA d1
with the assumed type · G8 no journal / targets / NO_GO collision. P = passes; P* = passes with a wording caveat
named in §4; FIX = tripped on the letter and repaired in staged/.

| # | composite | new leg (dataset; users / alphas) | partner leg | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | verdict | what the Verifier changed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | accruals_x_range_volatility | range_volatility_arbitrage_cost (tech_chart_model; 100 / 200) | usa_accruals_cashflow − | P | P | P | P | P | P | P | P | PROMOTE | nothing |
| 2 | ai_disagreement_x_putpremium | ai_news_score_disagreement (ai_news_scores; 20 / 39) | option_call_put_iv_spread + | P | P | P* | P | P | P | P | P | PROMOTE | `notes` += Miller 1977 is record-only (no abstract exists); Cremers-Weinbaum 2010 contests the ORW reading of the partner's own observable |
| 3 | chartpattern_x_short | chart_continuation_pattern_net (continuation_score; 23 / 66) | short_volume_ratio_informed − | P | P | P* | P | P | P | P | P | PROMOTE (last) | nothing |
| 4 | coverage_x_short | usa_debt_service_coverage (fundamental31; 778 / 3,423) | short_volume_ratio_informed − | P* | P | P | **FIX** | P | P | P | P | PROMOTE after fix | `regimes.covid_2020` "+" → "−" (George-Hwang's own mechanism, §4.4); `notes` block with per-regime reasoning — the file had none and its map was byte-identical to #2's |
| 5 | downgrade_x_short | news_downgrade_recommendation_topic (mmp_nlp_sentiment; 50 / 154) | short_volume_ratio_informed − | P | P | P | P | P | P | P | P | PROMOTE | nothing |
| 6 | netcash_x_insider | net_cash_to_market_equity (multi_horizon_alpha; 34 / 68) | insider_significant_buying_drift + | P* | P | P | P | P | **FIX** | P | P | PROMOTE after fix | `combiners: [multiply, gate]` → `[multiply]` — the gate branch compiles to an insider-half indicator book the library already runs (§4.6) |
| 7 | predsurprise_x_accruals | starmine_predicted_surprise_gap (predictive_starmine; 90 / 271) | usa_accruals_cashflow − | P | P | P | P | P | P | P | P | PROMOTE | nothing |

Leg-file edits: `ai_news_score_disagreement.yaml` notes — the second ai_news_scores journal row uses
`negative_score_confidence_upper_bound_3`, not `positive_score_average_value_3` as written (OBSERVED, §4.2).
**Nothing was pulled**: no composite trips a gate that a YAML line cannot repair, so `staged/pulled/` was not created.
Validation after the edits: the task's load command prints `ok`; `forge.standard.hard_gates` is `[]` for all 7;
`H.load_composites('forge/composites')` still returns 35 and `load_library` 52 — the live loader sees no staged file.

## 2. Cross-cutting findings (the ones that decide the promotion order)

**A. Three of seven new composites sit on the short-volume partner leg.** OBSERVED: `short_volume_ratio_informed`
is already in 6 live composites (options_x_short, short_x_sentiment, newsneg_x_short, ravenpack_x_short,
usa_insider_x_short_x_profitability, usa_short_x_profitability_x_accruals); #3, #4, #5 make it 9 of 42. Two
measured facts about that leg cut opposite ways for the round's target (Q17, distinct mechanisms):
01_origins §2: "every pass came from a composite that contains the short-volume share leg on the one cell
(Short Interest) where that leg is the category leg" (POST-HOC pattern, not a mechanism), and §5.3: "18 of 21
platform passers (86 %) read prod 0.79–0.85 … (SPECULATION: via the short-volume leg shared with vRk095rv)".
So the leg is the only one that has reached the Sharpe bar on USA/d1 AND the one suspected in the correlation
wall. Which effect dominates for a NEW conditioning leg is UNKNOWN — the prod-corr read on the first rows ≥ bar
is the measurement, and it is the reason these three rank below the four composites off that leg.

**B. The IV-spread partner carries a measured death stage.** 01_origins §1: "The IV-spread composites fail
sub-universe on every row ≥ bar (115 / 115); MECHANISM: UNKNOWN." #2 inherits that partner (option8 fields
alphaCount 6,259–7,089 / option3 33–74). Its new leg is on a 20-user dataset; the partner is where it will die
if the pattern holds. Recorded, not predicted.

**C. Regime-map collisions (grep of the `regimes` line over 35 live + 7 staged files, 2026-09-09).** Before
the fix: #4 {0,−,+,+} = #2 {0,−,+,+} — #4 carried no reasoning at all, #2 reasons every sign in `notes`; the
fix in §4.4 re-derives #4's map from its own citation (→ {0,−,−,+}, now unique). Still identical after the
fix: #5 {+,−,0,+} = #7 {+,−,0,+} = live `revisions_x_agreement` {+,−,0,+}. Both #5 and #7 reason each sign
from their own legs in `notes` (different reasons, same signs). Changing a sign to break a collision would be
fabrication (RULE 0); the collision is recorded and the maps stand. 81 maps are possible over 42 files;
some coincidence is expected — the check is against copying, and copying is what #4 showed.

**D. Two composites name one force per leg, not one per composite.** The standard's gate 1 wants the force
"TAGGED exactly one of {risk-premium, behavioral-mispricing, institutional/funding-friction}". #4 (George-Hwang
risk premium on the long leg + informed-flow/slow-holder mispricing on the short leg) and #6 (Palazzo/Simutin
precautionary-savings premium on the cash leg + private information on the insider leg) each state two. Both
say so explicitly (#6: "the cash leg is a claim about compensated aggregate-shock exposure, the insider leg is
a claim about private information"). The schema still has no force field (audit_hypotheses §2, unchanged), so
this remains a wording caveat (P*), not a trip.

**E. The live pre-sim gate passes every rendered candidate; the full judge passes almost none.** OBSERVED by
rendering each composite through `forge.compose.expand` on every USA/d1 cell its legs serve (216–400
candidates each) and running `forge.typed.judge`: structural=True (the gate `forge/runner.py:158` applies) ok
on 100 % of 2,808 candidates; structural=False ok on 0/216 for #1, #3, #4, #5, #7, 0/324 for #2, 201/400 for
#6. Causes: the quarterly-backfill rule (OFF in gate use — refuted 2026-09-07, typed.py L221–225) on the
partner accruals / inst20 fields, and H5 "no stated sign" on fields the label file leaves unstated
(NATR, starmine predicted surprise, dispersion kinds, `reported_short_sale_share_quantity`). The live
option_volatility_smirk leg fails the full judge the same way. Not a gate; recorded so nobody reads the full
judge as a verdict later.

**F. Label slips the authors found and worked around (labels.py is out of scope; none edited):**
`tcm_ta50_d1_natr` sign "+" domain valuation (a volatility field); continuation_score pattern fields domain
"sentiment" (words bullish/bearish); downgrade topic scores sign "+" from the analyst-rating prior (the
description says *downgrade*); `ebitda_to_debt_ratio_3` sign "−" from the leverage prior (debt is the
denominator); `diff_current_vs_hist_pe_ratio` domain "news" (the substring `story` in *history*); other580
`negative_*` counts sign "−" (direction of a holdings change, not a return); option40 30/90-day realized vol
units "ratio"/"annual". Each leg documents its override in `notes`; the structural gate does not read signs,
so none of these blocks a sim. Flagged to the Operator as before.

**G. Pyramid cells (02_dataset_map §3, read 2026-09-08 09:30 UTC).** Open cells among those the staged
composites serve: Insiders (2 / need 1 — #6) and Short Interest (2 / need 1 — #3, #4, #5). #1, #2, #7 land on
Fundamental / Model / Option / Other, all full (≥ 3). A full cell adds no unlock value; whether it changes the
submit class is not established here.

**H. Five staged legs are in no composite** (§5): analyst_bold_estimate_conviction,
etf_holdings_accumulation_reversal, news_tone_disagreement_trna, option_realized_implied_vol_spread,
valuation_own_history_multiple. They load, their citations fetch, and they wait for a partner. Two of the twelve
legs (ai_news_score_disagreement, news_tone_disagreement_trna) are the same construct — within-day dispersion of
a negative-sentiment score — on two vendors; only the first has a composite.

## 3. Citation ledger (this Verifier's own fetches, 2026-09-09; status from `curl -sS -L -w %{http_code}`)

| # | citation (used by) | URL | HTTP | verbatim sentence obtained (WebFetch / OpenAlex inverted index) |
|---|---|---|---|---|
| 1 | Stambaugh, Yu & Yuan (#1) | https://www.nber.org/papers/w18560 | 200 | "The IVOL effect is negative among overpriced stocks but positive among underpriced stocks, with mispricing determined by combining 11 return anomalies." |
| 2 | Ang, Hodrick, Xing & Zhang (#1 leg) | https://www.nber.org/papers/w10852 | 200 | "stocks with high idiosyncratic volatility relative to the Fama and French (1993) model have abysmally low average returns" |
| 3 | Frazzini & Pedersen (#1 leg) | https://www.nber.org/papers/w16601 | 200 | "some investors are prohibited from using leverage … The former investors bid up high-beta assets"; "When funding constraints tighten, betas are compressed towards one, and the return of the BAB factor is low." |
| 4 | Diether, Malloy & Scherbina 2002 JF (#2 leg; trna leg) | https://api.openalex.org/works/W2160275010 | 200 | "We provide evidence that stocks with higher dispersion in analysts' earnings forecasts earn lower future returns than otherwise similar stocks." |
| 5 | Ofek, Richardson & Whitelaw (#2) | https://www.nber.org/papers/w9423 | 200 | "We find that violations of put-call parity are asymmetric in the direction of short sales constraints, their magnitudes are strongly related to the rebate rate spread, and they are maintained even in the presence of transactions costs both in the options and equity lending market." |
| 6 | Miller 1977 JF (#2) | https://api.openalex.org/works/doi:10.1111/j.1540-6261.1977.tb03317.x | 200 | record only — `abstract_inverted_index: null` on OpenAlex (both DOIs); no abstract exists on any index. Q14 read strictly: background, never the evidence |
| 7 | Cremers & Weinbaum 2010 JFQA (#2 partner's own cite) | https://api.openalex.org/works/doi:10.1017/s002210901000013x | 200 | "which cannot be explained by short sale constraints. Rebate rates from the stock lending market directly confirm that our findings are not driven by stocks that are hard to borrow." — contests the ORW reading #2 is written to (§4.2) |
| 8 | Grinblatt & Han (#3) | https://www.nber.org/papers/w8734 | 200 | "stocks with large aggregate unrealized capital gains tend to have higher expected returns than stocks with large aggregate unrealized capital losses" |
| 9 | Lo, Mamaysky & Wang (#3 leg) | https://www.nber.org/papers/w7613 | 200 | "several technical indicators do provide incremental information and may have some practical value" |
| 10 | Boehmer, Jones & Zhang 2008 JF (#3, #4, #5 partner) | https://api.crossref.org/works/10.1111/j.1540-6261.2008.01324.x ; https://ideas.repec.org/a/bla/jfinan/v63y2008i2p491-527.html | 200 / 200 | "Heavily shorted stocks underperform lightly shorted stocks by a risk‐adjusted average of 1.16% over the following 20 trading days (15.6% annualized)." |
| 11 | George & Hwang 2010 JFE (#4) | https://ideas.repec.org/a/eee/jfinec/v96y2010i1p56-79.html | 200 | "The return premiums to low leverage and low distress are significant in raw returns, and even stronger in risk-adjusted returns. When in distress, low-leverage firms suffer more than high-leverage firms as measured by a deterioration in accounting operating performance and heightened exposure to systematic risk." |
| 12 | Christophe, Ferri & Hsieh 2010 JFE (#5) | https://econpapers.repec.org/article/eeejfinec/v_3a95_3ay_3a2010_3ai_3a1_3ap_3a85-106.htm | 200 | "Finally, we present evidence that downgraded stocks with high abnormal short-selling perform poorly over the subsequent six months by comparison with those with low abnormal short-selling." |
| 13 | Womack 1996 JF (#5 leg) | https://api.crossref.org/works/10.1111/j.1540-6261.1996.tb05205.x | 200 | "For buy recommendations, the mean postevent drift is modest (+2.4%) and short‐lived, but for sell recommendations, the drift is larger (−9.1%) and extends for six months." |
| 14 | Jensen 1986 AER (#6) | https://api.openalex.org/works/W3121131820 | 200 | "These conflicts are especially severe in firms with large free cash flows—more cash than profitable investment opportunities." |
| 15 | Penman, Richardson & Tuna 2007 JAR (#6 leg) | https://api.openalex.org/works/doi:10.1111/j.1475-679x.2007.00240.x | 200 | "the enterprise book-to-price is positively related to subsequent stock returns but, conditional upon the book-to-price, the leverage component is negatively associated with future stock returns" |
| 16 | Simutin 2010 FM (#6) | https://api.openalex.org/works/doi:10.1111/j.1755-053x.2010.01109.x | 200 | "I document a positive relationship between corporate excess cash holdings and future stock returns." "Firms with more excess cash have higher market betas and earn lower returns during market downturns." |
| 17 | Palazzo 2012 JFE (#6 leg) | https://ideas.repec.org/a/eee/jfinec/v104y2012i1p162-185.html | 200 | "This precautionary savings motive implies a positive relation between expected equity returns and cash holdings." |
| 18 | Bradshaw, Richardson & Sloan 2001 JAR (#7) | https://api.openalex.org/works/W2076947889 | 200 | both quoted sentences reconstructed verbatim from the inverted index: "We show that analysts' earnings forecasts do not incorporate the predictable future earnings declines associated with high accruals." and "Overall, our evidence indicates that analysts and auditors do not alert investors to the future earnings problems associated with high accruals, thus corroborating previous findings that investors do not appear to anticipate these problems." |
| 19 | Clement & Tse 2005 JF (#7 leg; bold leg) | https://api.openalex.org/works/W2057285392 ; …/doi:10.1111/j.1540-6261.2005.00731.x | 200 / 200 | "(2) bold forecasts are more accurate than herding forecasts"; "Thus, bold forecasts incorporate analysts' private information more completely and provide more relevant information to investors than herding forecasts." |
| 20 | Gleason & Lee 2003 TAR (bold leg) | https://api.openalex.org/works/doi:10.2308/accr.2003.78.1.193 | 200 | "the market does not make a sufficient distinction between revisions that provide new information ("high-innovation" revisions) and revisions that merely move toward the consensus ("low-innovation" revisions)" |
| 21 | Brown, Davies & Ringgenberg (etf leg) | https://api.crossref.org/works/10.1093/rof/rfaa027 | 200 | "A portfolio that is short high-flow ETFs and long low-flow ETFs earns excess returns of 1.1–2.0% per month, consistent with non-fundamental demand distorting asset prices away from fundamental values." |
| 22 | Ben-David, Franzoni & Moussawi 2018 JF (etf leg) | https://api.crossref.org/works/10.1111/jofi.12727 | 200 | "ETF ownership increases the negative autocorrelation in stock prices." — the same abstract also says "stocks with high ETF ownership earn a significant risk premium of up to 56 basis points monthly" (ownership LEVEL, positive; the leg trades accumulation FLOW, bearish — different construct, recorded in §5) |
| 23 | Bali & Hovakimian 2009 MS (rv-iv leg) | https://econpapers.repec.org/RePEc:inm:ormnsc:v:55:y:2009:i:11:p:1797-1812 | 200 | "Portfolio level analyses and firm-level cross-sectional regressions indicate a negative and significant relation between expected returns and the realized-implied volatility spread that can be viewed as a proxy for volatility risk." |
| 24 | Golubov & Konstantinidi (valuation leg) | https://www.aeaweb.org/conference/2018/preliminary/paper/4EQnQ4Dt | 200 (PDF; text via pdftotext) | "The market-to-value component drives all of the value strategy return, while the value-to-book component exhibits no return predictability in either portfolio sorts or firm-level return regressions." |
| 25 | Lakonishok, Shleifer & Vishny (valuation leg) | https://www.nber.org/papers/w4360 | 200 | "This paper provides evidence that value strategies yield higher returns because these strategies exploit the mistakes of the typical investor and not because these strategies are fundamentally riskier." |

Every URL the researchers wrote returned 200 to this Verifier and every quoted sentence was found (the two
BRS 2001 sentences and the second Clement-Tse sentence were confirmed from the raw inverted index after a
first WebFetch reconstruction dropped a word). No fabricated citation. Not re-fetched: Sloan 1996, Hribar-Collins
2002, Lakonishok-Lee 2001, Jeng-Metrick-Zeckhauser 2003, Bernard-Thomas 1989 — partner-leg citations already
in the 2026-09-08 ledger, named as background by the staged files and not as their evidence.

## 4. Evidence per composite

Compiled formulas below are actual `forge.compose.expand` output on USA/d1 (seed 23). Field rows are
`type | coverage | alphaCount | userCount | description` from `USA_TOP3000_d1.jsonl`. Journal counts are
`grep -c -w <field>` over 24,238 rows.

**4.1 accruals_x_range_volatility** — usa_accruals_cashflow (−) × range_volatility_arbitrage_cost (−, new); `[multiply]`.
Fields: `normalized_average_true_range_50d` MATRIX | 1.0 | 0 | 0 | "Normalized Average True Range value calculated
over a 50-day window."; `…_10d` | 1.0 | 0 | 0; `tcm_ta50_d1_natr` | 1.0 | 0 | 0 | "…a volatility indicator measuring
average true range relative to price". No description states a direction; the leg takes −1 from AHXZ/FP (fetched)
and says so; the label's "+" is a slip. Compiled: `multiply((1 - group_rank(ts_rank((income - cashflow_op) / abs(assets), 126), subindustry)), (1 - group_rank(ts_mean(tcm_ta50_d1_natr, 21), sector)))`
→ long low-accrual AND narrow-range; a name failing either is short; the corner (high accrual, wide range) is the
extreme short — matches the text's "the product's short leg … is the corner where both bind". G4: map {+,−,−,+}
unique; `weakens_when` gives the reason for both "−" (junk rallies Feb–Mar 2016 / Apr–Aug 2020 lift the short book;
FP's March-2020 funding tightening) and pre-registers the LONG half as the weak half (SYY: IVOL effect positive among
underpriced names) — the most falsifiable file in the set. G3 construct: the papers measure idiosyncratic volatility
and beta; the leg measures total range within the peer group and says "proxy, not a measured residual". Crowding:
a bare low-vol leg is a crowded classic (haircut applies to the leg alone); the interaction is the claim, and the
new-leg fields have alphaCount 0. Partner fields alphaCount 15,084–169,009 (≥ 750) as the conditioning leg —
same † treatment as audit_hypotheses. G8: 0/0/0 journal, 0 targets, 0 banned; tech_chart_model 1 typed row.
Structural judge 216/216.

**4.2 ai_disagreement_x_putpremium** — ai_news_score_disagreement (−, new) × option_call_put_iv_spread (+); `[multiply]`.
Fields: `negative_score_standard_deviation` MATRIX | 1.0 | 0 | 0 | "Standard deviation of negative sentiment scores
across events for a stock-day in USA (variant prv24, D0), scores in 0–1"; `positive_score_standard_deviation` | 1.0 | 1 | 1;
`negative_sentiment_dispersion_2` | 1.0 | 1 | 1; `positive_score_standard_deviation_5` | 1.0 | 1 | 1. Descriptions
state a dispersion, no direction; the leg takes −1 from Miller/DMS and says the item-to-investor bridge is an
assumption ("MECHANISM OF THE PROXY: UNKNOWN"). Compiled: `multiply((1 - group_rank(ts_mean(negative_score_standard_deviation, 5), industry)), group_rank(ts_mean(opt3_volcallatm - opt3_volputatm, 20), sector))`
→ long agreeing news AND calls rich; the `notes` SEMANTICS CHECK states exactly this arithmetic. G3: DMS and ORW
text-verified; Miller record-only; **Cremers-Weinbaum 2010 — the partner leg's own citation — reads the same spread
the opposite way** ("cannot be explained by short sale constraints … not driven by stocks that are hard to borrow").
Two mechanisms fit the partner observable; the composite is written to ORW's. Added to `notes`; UNKNOWN which holds.
G4: map {0,−,+,+} reasoned per sign in `notes`; identical to #4's staged map (fixed on #4's side). G6: bearish A ⇒
`[multiply]` ✓ (the file's own comment says why). Full judge refuses H5 on dispersion-kind fields in a directional
role — dispersion signed by theory is what DMS did; structural 324/324. G7: cov 1.0, `time: event` on two fields
(no backfill rule attaches to "event"). G8: 0 journal for the four ids; ai_news_scores 2 typed rows on
`positive_score_average_value_3` (sharpe 1.25, gated by a short-flow field — an observation about a different
field) and `negative_score_confidence_upper_bound_3`; the leg's note said both used the first — corrected.
Partner burden §2B. Cells Other / Option, both full.

**4.3 chartpattern_x_short** — chart_continuation_pattern_net (+, new) × short_volume_ratio_informed (−); `[multiply]`.
Fields (8, paired bull/bear): e.g. `avg_similarity_bullish_rectangle` MATRIX | 0.9993 | 1 | 1 | "Average similarity
score to the bullish rectangle pattern."; `mean_bull_pennant_similarity_score` | 0.9992 | 0 | 0 | "…over the 60-day
horizon"; bear mirrors 0.9992–0.9993 | 0 | 0. Same unit (score) on both sides of the subtraction. Compiled:
`multiply(group_rank(ts_mean(avg_similarity_bullish_rectangle - avg_similarity_bearish_rectangle, 5), industry), (1 - group_rank(ts_mean(reported_short_sale_share_quantity / reported_total_trade_share_quantity, 20), sector)))`
→ long bullish shape AND low short share: matches. G1: the leg lists three candidate mechanisms and calls the
choice UNKNOWN — candidate (c), "a nonlinear re-encoding of trailing return and trailing range", would make the
leg momentum × low-vol, and the composite names prod-corr as the deciding measurement. G3 construct: G&H's
regressor is the aggregate unrealized-gain variable, not a chart shape; LMW is pattern recognition on kernel-smoothed
prices. Analogy-level match, stated as such (P*). G4: map {+,−,−,0} reasoned inline, unique. Duplicate check: by the
LABEL domain (sentiment × short) this would collide with live `short_x_sentiment`; the label is the slip (§2F) and by
construct no live composite pairs a price-technical leg with the short leg. 7th composite on the short-volume leg
counting the live six (§2A). G8: 0 journal on all 8; continuation_score 9 typed rows. Structural 324/324.

**4.4 coverage_x_short** — usa_debt_service_coverage (+, new) × short_volume_ratio_informed (−); `[multiply]`.
Fields: `fnd31_ebitdadebt` MATRIX | 0.8379 | 86 | 25 | "TTM EBITDA to long-term Debt…"; `ebitda_to_debt_ratio_3` | 0.86
| 0 | 0 | "Ratio of EBITDA to total debt." Debt in the denominator ⇒ higher = safer ⇒ +1 (the leg's override of the
leverage prior is right). Quarterly ⇒ `ts_backfill` in both templates ✓. Compiled:
`multiply(group_rank(ts_backfill(fnd31_ebitdadebt, 126), industry), (1 - group_rank(ts_mean(reported_short_sale_share_quantity / reported_total_trade_share_quantity, 5), sector)))`
→ long high coverage AND low short share: matches. **G4 tripped on the letter**: the file gave the map with no
reasoning anywhere, and the map was byte-identical to #2's. Re-derived by this Verifier from the composite's own
citation and construct (EX-ANTE, no PnL): value winter 0 (two unmeasured forces), 2016 "−" (short book = levered AND
shorted = the junk-rally bucket), **covid "−"** (George-Hwang: "When in distress, low-leverage firms suffer more than
high-leverage firms" — the long book's premium is paid for an exposure that arrives in the low state; the Apr–Aug
rebound lifts the short book), 2022 "+" (rates raise debt service on thin coverage; the informed short flow sits in
levered names). The author's covid "+" had no stated reason and contradicts the mechanism the file cites.
G1 P*: two forces, one per leg (§2D). Adjacent domain in the live book: smartratios_credit_safety (5 composites) and
credit_language_safety are credit-safety SCORES; this leg is an accounting coverage RATIO; no live safety × short
composite. Author-flagged hazard: zero-debt firms explode the ratio (weakens_when). G8: 0 journal; fundamental31
10 typed rows; 778 users on the dataset (the most-used of the seven). Structural 216/216.

**4.5 downgrade_x_short** — news_downgrade_recommendation_topic (−, new) × short_volume_ratio_informed (−); `[multiply]`.
Fields: `avg_downgrade_topic_score` MATRIX | 0.9025 | 2 | 1 | "Average score for topics indicating a downgrade
recommendation."; `median_…` | 0 | 0; `max_…` | 0 | 0; `max_sell_recommendation_score` | 0 | 0 | "Maximum value of the
sell recommendation topic score in the news sample." Sign −1 from the description (a downgrade), against the label's
analyst-rating "+" prior — documented in the leg. Compiled: `multiply((1 - group_rank(ts_mean(median_downgrade_topic_score, 20), sector)), (1 - group_rank(ts_mean(inst20_sq_sv / inst20_sq_tv, 10), sector)))`
→ long no-downgrade AND low short share; short = heavy downgrade coverage OR heavy shorting, extreme short = both:
the mechanism's last sentence states this arithmetic. G3: CFH 2010 measured the pair itself (downgrades × abnormal
shorting → six-month underperformance) — the strongest conjunction-level citation in the set; construct differs in
that CFH use actual downgrade events and 3-day pre-announcement abnormal shorting, the leg uses a topic score for
downgrade COVERAGE (author: "will also fire on coverage of an avoided or reversed downgrade … UNKNOWN") over a 5–20-day
short-share window. G4: {+,−,0,+} reasoned per sign; collides with #7 and live revisions_x_agreement (§2C). G8:
`avg_downgrade_topic_score` 2 journal hits = ONE typed construction (`rank(ts_zscore(avg_downgrade_topic_score, 252))`,
positive orientation, sharpe 0.17) plus its multisim parent record listing the same formula — verified by reading
both rows; different construct, opposite sign; 0 for the other three ids. Structural 216/216. Cell Short Interest open.

**4.6 netcash_x_insider** — net_cash_to_market_equity (+, new) × insider_significant_buying_drift (+); was `[multiply, gate]`.
Fields: `mid_term_net_cash_to_equity_2` MATRIX | 0.9275 | 0 | 0 | "Net cash (cash and equivalents minus debt) divided
by market value of equity, measured over a medium-term horizon."; `long_term_…_2` | 0.8768 | 0 | 0; `short_term_…_2` |
0.8768; `mid_term_net_cash_to_equity` | 0.8768 | 0 | 0. What "horizon" means for a balance-sheet ratio is UNKNOWN
(the leg says so and dropped the horizon-spread construct as SPECULATION). Sign +1 from PRT 2007 (leverage
component of B/P, sign reversed — exact construct); the leg records the contrary Jensen/Simutin reading as
CONTESTED, which is precisely what the composite conditions on. Compiled multiply:
`multiply(group_rank(ts_mean(long_term_net_cash_to_equity_2, 63), industry), group_rank(ts_sum(add(directional_indicator_2, 0, filter=true), 120), sector))`
→ long cash-rich AND insider-buying: matches. **G6 fixed**: the gate branch compiles to
`if_else(greater(group_rank(ts_sum(add(top_directional_significant_value_1, 0, filter=true), 20), subindustry), 0.5), group_rank(ts_mean(long_term_net_cash_to_equity_2, 21), industry), 0)`
— by compose.py L37–41 (EX-ANTE arithmetic, audit_hypotheses §2A(ii)) the gated-out half sits at 0 and the traded half
has mean +0.5, so after neutralisation the book is an insider-half indicator (a 0.5 step between halves against a
within-half sd ≈ 0.29) with net cash modulating the long side only. That book is what the live library already runs on
this leg: usa_insider_x_ivspread 1,648 rows and usa_insider_x_profitability_x_accruals 550 rows (journal, OBSERVED).
Half of this composite's candidates would have measured a mechanism the book has, not the new one; the round's target
is distinct mechanisms (Q17), so `combiners: [multiply]`. No bearish leg is involved — this is a distinct-mechanism
judgment, not the inversion rule. G4: {0,0,−,+} reasoned per sign, unique; covid "−" from Simutin's measured
downturn behaviour is the same reasoning applied to #4. G8: 0 journal; multi_horizon_alpha 59 typed rows.
Structural 400/400; full judge ok 201/400 (the only staged composite it passes on). Cell Insiders open (2 / need 1).

**4.7 predsurprise_x_accruals** — starmine_predicted_surprise_gap (+, new) × usa_accruals_cashflow (−); `[multiply]`.
Fields: `predicted_surprise_pct_fq1_earnings_3` MATRIX | 0.9905 | 0 | 0 | "Predicted percentage surprise in FQ1
earnings"; `…_fy1_earnings_7` | 0.9872 | 0 | 0; `…_f12m_earnings_3` | 0.9985 | 0 | 0. Sign +1 from the description
(larger = larger expected beat); label unstated (no prior to disagree with). Labels time daily/annual/annual ⇒
`ts_backfill` in every template ✓. Compiled: `multiply(group_rank(ts_backfill(predicted_surprise_pct_f12m_earnings_3, 22), industry), (1 - group_rank(ts_rank((income - cashflow_op) / abs(assets), 252), sector)))`
→ long predicted beat AND low accruals: "keeps only predicted beats that the cash flow can pay for" ✓. G3: BRS 2001
is the conjunction's own evidence (analysts' forecasts omit accrual-driven declines), both quotes verbatim; construct
caveat — BRS describe ALL sell-side forecasts, the leg uses the accuracy-weighted subset minus the mean; the composite's
reading (the omission is the producers' known blind spot, so condition on it) is consistent with BRS, not tested by
them. G4: {+,−,0,+} reasoned per sign; collision with #5 and revisions_x_agreement recorded (§2C). G8: 0 journal for
the three ids; predictive_starmine 42 typed rows; the author dropped `…_fy1_earnings_4` because it and two siblings sit
in `state/banned_fields.json` / `state/climb/spent_fields.json` (old climb ledger; meaning for forge UNKNOWN — swapped,
not argued). Author-flagged overlap: SmartEstimate weights recency too, so the leg may correlate with
analyst_estimate_revision_drift — unmeasured, and the file says drop it if the correlation is high. Structural 216/216.
No short-volume leg, no IV-spread leg; the partner is the leg of both ACTIVE alphas. Cells Model / Fundamental full.

## 5. The five staged legs without a composite (audited, left in staged/)

| leg | dataset (users / journal rows) | citations fetched | construction check | note |
|---|---|---|---|---|
| analyst_bold_estimate_conviction (+) | analyst_revision_horizons (75 / 63 typed) | Clement-Tse ✓, Gleason-Lee ✓ | 4 MATRIX cov 0.9968, alpha 0; quarterly ⇒ ts_backfill ✓; (pos − neg)/(1 + pos + neg) count/count | needs a partner; the author marks the drift mechanism UNKNOWN (under-reaction / premium / vendor leakage) |
| etf_holdings_accumulation_reversal (−) | other580 (79 / 14 typed) | BDR 2020 ✓, BFM 2018 ✓ | 6 MATRIX cov 1.0, alpha 0; (P − N)/(P + N) is 0/0 on a day no ETF changed — unmeasured | BFM's positive "risk premium of up to 56 bp" is for ownership LEVEL; the leg trades accumulation FLOW — different construct, both signs on record |
| news_tone_disagreement_trna (−) | sentiment21 (512 / 101 typed) | DMS 2002 ✓ | 3 MATRIX cov 0.9996, alpha 3–7 | same construct as ai_news_score_disagreement on another vendor; the ts_rank(250) template addresses the coverage-volume confound the author names |
| option_realized_implied_vol_spread (−) | option40 (742 / 1 typed) | Bali-Hovakimian ✓ exact construct and sign | 4 MATRIX cov 0.984; 20/60-day pairs unit-consistent; 30/90 refused by a label slip (disclosed) | the only leg comparing the physical and risk-neutral surfaces; alphaCount 19–105 |
| valuation_own_history_multiple (−) | other685 (64 / 11 typed) | Golubov-Konstantinidi ✓ (PDF), LSV ✓ | 2 MATRIX cov 0.9961, alpha 2–6; template 1 (own-history ts_rank) robust to the near-zero-EPS hazard, template 2 not — stated | Other cell full; the author states the momentum confound before any result |

## 6. Promotion list, ranked by expected distinct-mechanism value

Ranking rule, stated before the list (a Verifier judgment, not a measurement): (i) the domain pair is absent from the
live book; (ii) the partner leg carries no measured death stage (01_origins: short-volume ⇒ prod-corr 0.79–0.85 on
16 passers, SPECULATION via the leg; IV-spread ⇒ LOW_SUB_UNIVERSE 115/115, MECHANISM UNKNOWN); (iii) the mechanism
is stated with its contrary on record; (iv) an open pyramid cell is a tie-break, not a criterion.

| rank | composite | why here | what decides it after the first rows ≥ bar |
|---|---|---|---|
| 1 | predsurprise_x_accruals | new domain pair (analyst predicted surprise × accruals) absent from all 35 live composites; the conjunction has its own citation (BRS 2001); partner = the leg of both ACTIVE alphas; no short-volume or IV-spread leg | correlation with analyst_estimate_revision_drift books |
| 2 | accruals_x_range_volatility | the only volatility leg in the library; the interaction is stated by SYY on the same anomaly family; most falsifiable file (long half pre-registered weak) | whether the long half is flat as pre-registered; robust-universe (liquid names remove the holding-cost conditioning — author's item 4) |
| 3 | netcash_x_insider | new balance-sheet cash leg; Insiders cell open; contrary mechanism (Jensen) on record and conditioned on; fixed to `[multiply]` | insider books never passed (usa_insider_x_ivspread 40 rows ≥ bar, 0 pass — 01_origins) |
| 4 | ai_disagreement_x_putpremium | new disagreement leg on a 20-user dataset; but the partner dies at sub-universe 115/115 and its own citation contests the mechanism | LOW_SUB_UNIVERSE on the first rows ≥ bar |
| 5 | downgrade_x_short | the pair itself is measured (CFH 2010); Short Interest cell open; but 7th–9th composite on the short-volume leg | prod-corr read against the short-volume book |
| 6 | coverage_x_short | coverage ratio is a new leg but adjacent to the live credit-safety legs; short-volume partner; regime map re-derived by the Verifier | prod-corr; whether coverage adds to the profitability × short book (usa_short_x_profitability_x_accruals, 2 passes) |
| 7 | chartpattern_x_short | the leg may be momentum × low-vol re-encoded (author's candidate (c), UNKNOWN); short-volume partner; analogy-level citation | prod-corr with the pre-existing book, as the author says |

Under Q20 (≥ 3 distinct datasets among a day's four), the seven cover eight new datasets; under the desk rule that
one submission retires a family, #3/#4/#5 share the short-volume family with the live book.

## 7. What this audit does not establish

- Whether any composite predicts: nothing was simulated (RULE 1). Every "matches" above is arithmetic on the compiled
  formula against the text, not a return.
- Whether the short-volume leg's correlation reading transfers to a new conditioning leg (§2A) — UNKNOWN until the
  first prod-corr reads.
- The regime signs are EX-ANTE reasoning, including the one this Verifier changed; a regime-audit on PnL is post-sim.
- The force tag still has no schema field; the full typed judge still refuses signed-by-theory dispersion fields;
  the label slips in §2F are still in labels.py — all three carried over from audit_hypotheses §6.11, unchanged.
