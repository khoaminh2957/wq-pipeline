# harness5 — round 2 · the sub-universe wall (Portfolio, 2026-09-09 14:30 local)

Every number below was read from the VPS journal over `ssh -n` (READ-ONLY: `state/layered/runs/forge.jsonl`
24,268 lines, `state/forge/scored.jsonl`, `state/forge/corr.jsonl`; copied to the scratchpad and analysed
there) and re-derived a second way where stated. Labels per CLAUDE.md RULE 0: **MEASURED** (a count from the
journal), **API-OBSERVED** (a platform response recorded in the journal), **EX-ANTE**, **POST-HOC** (a pattern
— never an explanation), **SPECULATION**, **UNVERIFIED** (asserted somewhere, not fetchable today). No
simulation was run; nothing was written on the VPS; no yaml, unit or arm was touched.

## 0. Summary
- The check is `sub_universe_sharpe ≥ limit` with **`limit = round(0.4330 × Sharpe, 2)` on 13,971 / 13,971
  USA/d1 TOP3000 rows (max deviation 0.000)** — API-OBSERVED. 0.4330 = 0.75·√(1000/3000). The same shape
  holds on every universe with a universe-specific constant (§2). So the test is a **retention** test: the
  alpha must keep ≥ 43.3 % of its own Sharpe on the platform's sub-universe.
- 01_origins reproduced on the same window (dateCreated < 2026-09-08 05:39 ET): **598 rows ≥ 1.58, 389 fail
  sub-universe, IV-spread composites 115 / 115**. Now (journal to 09-09 13:14): 698 ≥ bar, 465 fail, IV-spread
  **161 / 161**.
- What fails and what does not (retention = sub/Sharpe on 6,330 USA/d1 rows with Sharpe ≥ 0.8; line 0.433):
  every composite whose IV-spread leg (option8 / option3) is paired with a sentiment, insider, twitter or
  short-interest-prediction leg has **median retention −0.05…0.12 and pass 0–3 %**; the same IV leg paired
  with short-volume share (`options_x_short`) 0.34 / 13 %; every composite containing a **fundamental6**
  (profitability / accruals) leg 0.63–0.82 / 84–100 % — five partners, five times. Neutralization, group,
  decay and combiner do **not** move retention inside the IV-spread composites (§4). Truncation is 100 %
  confounded with hypothesis (IV-spread composites ran only at 0.15, everything else at 0.08) and the one
  within-hypothesis series says it is worth ≈ 0.03 (§4.4).
- **"Sub-universe Sharpe = the Sharpe of the same formula re-simulated on TOP1000" is REFUTED as an identity**:
  10 formula+settings pairs simulated on both universes — the TOP1000 simulation's Sharpe exceeds the TOP3000
  row's sub-universe value in 10 / 10 (by 0.03–0.61). What the platform computes is **UNVERIFIED**.
- Robust universe: `LOW_ROBUST_UNIVERSE_*` checks appear on CHN (100 rows) and IND (60) journal rows only,
  never on USA/d1 (14,110 rows) — API-OBSERVED. It is not a USA/d1 gate. Its definition: UNVERIFIED.
- **MECHANISM of the IV-spread × {sentiment, insider, twitter} failure: UNKNOWN** (candidates and the
  separating experiments in §5).
- One lever, A/B-testable on the same three cells (§6): a **third leg from the fundamental6 family** on the
  IV-spread composites. EX-ANTE expected effect: sub-universe PASS on rows ≥ 1.58 from 0 / 161 to ≥ 50 %;
  falsified if < 20 % with N ≥ 30 rows at the bar. Stated before any simulation.

## 1. What the platform says — and what could be fetched
Attempted today (all READ-ONLY): `support.worldquantbrain.com/hc/en-us/search?query=sub-universe` → **403**
(Cloudflare); `zhuanlan.zhihu.com/p/1915099506304849861` → 403; `blog.csdn.net/Zaralike/article/details/144935941`
→ 521; `medium.com/@mapongo/...simulation-environment-settings` → connection refused (twice);
`github.com/alexisdpc/WorldQuant-alpha-trading`, `github.com/QuantML-Research/wq-alpha-research`,
`jglazar.github.io/projects/wq_project/`, `pypi.org/project/pyworldquant/` → fetched, **none defines the check**
(pyworldquant lists the name `LOW_SUB_UNIVERSE_SHARPE` in an example output, nothing more). Search snippets
(THIRD-PARTY, not fetched as pages): "Sub-universe Sharpe is intended to avoid liquidity issues, for example if
you tested on TOP3000, the platform needs to retest performance on TOP1000" (Medium snippet); "the sub-universe
Sharpe threshold scales with sub-universe size" (search summary). **Neither may be stated as fact.**

Local transcription (`docs/harness5/papers_robustness.md` §2.2–2.3, from Khoa's screenshots of the login-gated
consultant page — `[TRANSCRIPTION]`, UNVERIFIED): `subuniverse_sharpe >= 0.75 * sqrt(subuniverse_size /
alpha_universe_size) * alpha_sharpe`; non-TOP universes use flat ratios 0.295 (ASI MINVOL1M), 0.41 (USA
ILLIQUID_MINVOL1M), 0.355 (EUR ILLIQUID_MINVOL1M); robust universe = "the adjusted (more-scalable) universe".

## 2. What the journal shows about the rule (API-OBSERVED, two derivations)
Every row carries `{"name": "LOW_SUB_UNIVERSE_SHARPE", "result", "limit", "value"}`. 21,435 of 21,454 distinct
forge alphas with checks have numeric value and limit (PASS 11,977 / FAIL 9,458).

**Derivation A — quantiles of limit/Sharpe per (region, universe, delay), |Sharpe| > 0.3:**

| region / universe / delay | n | limit ÷ Sharpe p10 / p50 / p90 | implied sub-universe size if the transcription's 0.75·√ rule holds |
|---|---|---|---|
| USA TOP3000 d1 | 12,818 | 0.429 / **0.433** / 0.438 | 1,000 |
| USA TOP3000 d0 | 1,327 | 0.430 / 0.433 / 0.437 | 1,000 |
| GLB MINVOL1M d1 | 2,837 | 0.344 / 0.350 / 0.356 | non-TOP flat ratio (transcription lists 0.355 for EUR ILLIQUID_MINVOL1M; GLB not listed) |
| JPN TOP1200 d1 / d0 | 510 / 74 | 0.604 / 0.611 / 0.622 | ≈ 800 |
| EUR TOP2500 d1 | 260 | 0.512 / 0.519 / 0.529 | ≈ 1,200 |
| CHN TOP2000U d1 / d0 | 67 / 20 | 0.709 / 0.712 / 0.714 | ≈ 1,800 |
| GLB TOP3000 d1 | 57 | 0.606 / 0.613 / 0.618 | ≈ 2,000 |
| USA TOP1000 d1 | 40 | 0.527 / 0.531 / 0.533 | ≈ 500 |
| IND TOP500 d1 | 21 | 0.288 / 0.295 / 0.306 | flat 0.295 (equals the transcription's ASI MINVOL1M ratio) |
| EUR TOP1200 d1 | 12 | 0.600 / 0.606 / 0.618 | ≈ 800 |

**Derivation B — exact reproduction:** on all 13,971 USA/d1 TOP3000 rows, `limit == round(0.4330127 × sharpe,
2)` within 0.01 in **13,971 / 13,971** (max deviation 0.000; the p10–p90 spread in A is the 2-decimal rounding
of both numbers). Negative-Sharpe rows carry a negative limit and read FAIL when `value < limit`.

What this establishes: the **shape** (limit proportional to the alpha's own Sharpe, one constant per universe)
and the **constants**. The constants are *consistent with* the transcription's formula at the implied sizes
(1,000 / 500 / 800 / 1,200 / 1,800 / 2,000) — POST-HOC consistency, not a verification of the formula or of what
the sub-universe contains.

**Identity test (MEASURED):** 10 `usa_short_x_profitability_x_accruals` constructions (same formula,
neutralization, decay, truncation) were simulated on both TOP3000 and TOP1000:

| alpha (TOP3000 row) | TOP3000 Sharpe | its sub-universe value | TOP1000 re-sim Sharpe | re-sim − sub |
|---|---|---|---|---|
| j23LmL3E | 1.50 | 1.20 | 1.37 | +0.17 |
| KPOeaqPz | 1.14 | 0.46 | 0.94 | +0.48 |
| 78ZOXOgZ | 1.66 | 1.37 | 1.47 | +0.10 |
| 78ZOXO02 | 1.66 | 1.25 | 1.51 | +0.26 |
| vRk0zN6r | 1.45 | 0.73 | 1.35 | +0.62 |
| Vk6nl82M | 1.69 | 1.06 | 1.30 | +0.24 |
| 3q9d6dxe | 1.57 | 1.26 | 1.46 | +0.20 |
| 883A6gO7 | 1.46 | 0.86 | 1.47 | +0.61 |
| RRVXakLd | 1.58 | 1.24 | 1.27 | +0.03 |
| 1YxvmvVQ | 1.55 | 1.15 | 1.24 | +0.09 |

10 / 10 re-sims are higher than the sub-universe value. So whatever the platform computes, it is **not** a fresh
TOP1000 simulation with the alpha's settings. Candidates (none established): the TOP3000 book's positions
restricted to the sub-universe names without re-neutralisation/re-ranking; a different 1,000-name set; a
different window. **UNKNOWN.** Consequence for §6: the sub-universe value of an IV-spread row is *not* a
prediction of what that formula would score if simulated on TOP1000.

## 3. Reproduction of 01_origins and the current state (MEASURED)
Window `dateCreated < 2026-09-08T05:39 ET` (= 16:39 local, the origins read): USA/d1 TOP3000 rows 10,363;
≥ 1.58: **598**; sub-universe FAIL among them **389**; by hypothesis (n, fail): options_x_short 342 / 273;
usa_short_x_profitability_x_accruals 140 / **0**; usa_insider_x_ivspread 40 / 40; usa_sentiment_x_ivspread
40 / 40; usa_twitter_x_ivspread 30 / 30; usa_shortsurprise_x_ivspread 5 / 5; typed 1 / 1 → IV-spread
composites **115 / 115**. All three origins numbers reproduce exactly.

Now (journal to 09-09 13:14 local; 13,971 USA/d1 TOP3000 rows): ≥ 1.58 = **698**, sub FAIL **465**.

| hypothesis (rows ≥ 1.58 now) | n | sub FAIL | p50 sub-universe Sharpe | p50 retention |
|---|---|---|---|---|
| options_x_short | 342 | 273 | 0.65 | 0.371 |
| usa_short_x_profitability_x_accruals | 140 | 0 | 1.18 | 0.702 |
| usa_insider_x_ivspread | 61 | 61 | 0.06 | 0.036 |
| usa_sentiment_x_ivspread | 59 | 59 | 0.05 | 0.029 |
| ravenpack_x_short (round-1 `new` arm) | 54 | 30 | 0.69 | 0.423 |
| usa_twitter_x_ivspread | 33 | 33 | 0.22 | 0.130 |
| usa_shortsurprise_x_ivspread | 8 | 8 | 0.38 | 0.237 |

The IV-spread rows at the bar have a sub-universe Sharpe of ≈ 0.05: on the platform's sub-universe these
books have **no** Sharpe, not a reduced one. The same holds off the bar: over all 870 / 849 / 1,010 rows of the
sentiment / insider / twitter IV composites the sub value is p10 / p50 / p90 = −0.39 / −0.09 / 0.23,
−0.25 / 0.01 / 0.28, −0.30 / 0.01 / 0.29 while their Sharpe is 1.13 / 1.05 / 1.04 at p50. corr(sub, Sharpe)
across rows: 0.41 / 0.21 / 0.66 for the three IV composites vs 0.73–0.77 for options_x_short and
usa_short_x_profitability_x_accruals (a higher-Sharpe IV-composite row is barely more likely to have any
sub-universe Sharpe).

## 4. Which constructions fail and which do not (POST-HOC patterns; retention = sub/Sharpe on USA/d1 TOP3000 rows with Sharpe ≥ 0.8, n = 6,330; "pass" = retention ≥ 0.433)

### 4.1 By signature (datasets · shape) — the dominant split
| signature | n | p25 / p50 / p75 retention | pass |
|---|---|---|---|
| fundamental6 \| short_interest_pred · norm+smooth | 18 | 0.784 / 0.820 / 0.898 | 100 % |
| fundamental6 \| twitter_sentiment_l2 · norm+smooth | 489 | 0.648 / 0.768 / 0.872 | 96 % |
| fundamental6 \| insider_agg_matrix · norm+smooth | 65 | 0.624 / 0.707 / 0.800 | 95 % |
| fundamental6 \| us_short_sale · norm+smooth | 992 | 0.565 / 0.655 / 0.748 | 93 % |
| fundamental6 \| short_interest_pred · smooth | 32 | 0.522 / 0.585 / 0.625 | 78 % |
| news46 \| us_short_sale · smooth | 395 | 0.455 / 0.535 / 0.602 | 79 % |
| fundamental6 \| twitter_sentiment_l2 · smooth | 308 | 0.394 / 0.478 / 0.583 | 65 % |
| news_sentiment_transfer \| us_short_sale · smooth | 985 | 0.268 / 0.429 / 0.851 | 50 % |
| option8 \| us_short_sale · smooth | 464 | 0.309 / 0.358 / 0.407 | 16 % |
| option3 \| us_short_sale · smooth | 239 | 0.252 / 0.305 / 0.368 | 8 % |
| nlp_news_scores \| us_short_sale · smooth | 88 | 0.156 / 0.218 / 0.310 | 7 % |
| option8 \| short_interest_pred · smooth | 176 | −0.044 / 0.115 / 0.230 | 2 % |
| option8 \| twitter_sentiment_l2 · smooth | 588 | −0.031 / 0.075 / 0.175 | 1 % |
| insider_agg_matrix \| option8 · smooth | 477 | −0.069 / 0.039 / 0.172 | 0 % |
| news_sentiment_transfer \| option8 · smooth | 551 | −0.142 / −0.035 / 0.065 | 0 % |
| option3 \| twitter_sentiment_l2 · smooth | 146 | −0.110 / 0.000 / 0.119 | 0 % |
| insider_agg_matrix \| option3 · smooth | 97 | −0.154 / −0.024 / 0.097 | 1 % |
| news_sentiment_transfer \| option3 · smooth | 152 | −0.346 / −0.124 / 0.089 | 5 % |

Second derivation of the split, by `meta.dataset`: option8/option3 with sentiment / insider / twitter /
short_interest_pred: 0 %, 0 %, 1 %, 1 %, 0 %, 2 %, 5 % (n 97–588); option8/option3 with us_short_sale 16 % /
8 %; fundamental6 with any partner 78–100 %. ✔

Reading it as observations only: (i) the IV-spread leg is in both the worst rows (with sentiment/insider/
twitter) and a middling one (with short-volume share) — the leg alone does not fix the outcome; (ii) the
sentiment / insider / twitter legs are in the worst rows (with IV) and in good ones (with fundamental6:
0.71–0.77) — those legs alone do not fix it either; (iii) **the product** IV × {sentiment, insider, twitter}
is what retains nothing. No experiment has separated why.

### 4.2 Neutralization and group — no effect inside a hypothesis
Pooled, neutralization looks decisive (INDUSTRY 64 % pass, STATISTICAL 43 %, SUBINDUSTRY 30 %) and so does
the `group_rank` group (industry|subindustry 46 % … subindustry 40 %). Both are confounds of *which
hypotheses use which grid*. Within a hypothesis:

| hypothesis | neutralization × group cells (n ≥ 8) | retention p50 range | pass range |
|---|---|---|---|
| usa_sentiment_x_ivspread | 8 cells, n 42–95 | −0.19 … +0.04 | 0–4 % |
| usa_insider_x_ivspread | 6 cells, n 83–112 | −0.07 … +0.10 | 0–1 % |
| usa_twitter_x_ivspread | 8 cells, n 46–93 | 0.01 … 0.11 | 0–2 % |
| options_x_short | 8 cells, n 45–59 | 0.29 … 0.39 | 10–21 % |
| usa_short_x_profitability_x_accruals | 8 cells, n 48–190 | 0.61 … 0.69 | 79–100 % |

The IV-spread composites only ever ran STATISTICAL and SUBINDUSTRY (their yaml grid); INDUSTRY is untested on
them — but on options_x_short, which ran all three, INDUSTRY (0.34–0.36) is not different from the others.

### 4.3 Decay, turnover, long/short counts, combiner
- **Decay 4 vs 8** within every hypothesis: retention differs by ≤ 0.03 (IV composites −0.04 / −0.05, 0.04 /
  0.02, 0.08 / 0.05; options 0.36 / 0.33; usa_short 0.66 / 0.66). Decay 16 / 32 exist only on usa_short and
  insider×prof (0.60–0.70) — same band as their decay 4 / 8.
- **Turnover** within hypothesis (bins < 0.10 … ≥ 0.30): the IV composites sit at ≈ 0 in every bin
  (sentiment −0.10 / −0.04 / −0.01 / −0.13; insider −0.04 / 0.02 / 0.07 / 0.02 / −0.33; twitter 0.06 / 0.03 /
  0.06 / 0.07). options_x_short rises with turnover: 0.30 (< 0.10, 0 % pass) → 0.32 → 0.37 → 0.40 (0.20–0.30,
  33 % pass). usa_short is flat 0.65–0.67. The pooled "low turnover passes more" (74 % at < 0.10) is again the
  hypothesis mix.
- **longCount + shortCount** (TOP3000 rows p50 2,814): the IV composites hold *more* names than the passers
  (sentiment×IV 3,112, twitter×IV 3,112, insider×IV 2,793 vs usa_short 3,125, options 2,882, twitter×prof
  2,503). Breadth of the book does not separate them. The counts are whole-universe counts; the journal does
  not say how many of those names lie in the sub-universe.
- **Combiner** (`multiply(A⁺, B⁺)` vs `gate = if_else(greater(B⁺, 0.5), A, 0)`), within hypothesis: IV
  composites gate / multiply = −0.00 / −0.10, 0.01 / 0.04, 0.11 / 0.01 (pass 0–3 % either way); options 0.34 /
  0.34. The combiner matters elsewhere — short_x_sentiment gate 0.89 (100 %) vs multiply 0.29 (14 %),
  twitter×prof 0.71 vs 0.54 — but not on the IV-spread composites. Rows ≥ bar in the IV composites: 65 gate +
  96 multiply, all 161 FAIL.
- **Leg count**: every forge composite is two legs except the fundamental6 triples (short×prof×accruals,
  insider×prof×accruals, sentiment×prof×accruals). Three-leg rows: retention 0.63–0.71 — but the third leg is
  always fundamental6, so leg count and family are confounded here.

### 4.4 Truncation — fully confounded, and the one within-hypothesis series says ≈ 0.03
Pooled: truncation 0.08 → p50 0.534 (62 % pass), 0.15 → 0.050 (10 %). But the IV-spread composites carry
`truncation: 0.15` in their yaml and ran **only** at 0.15 (703 + 574 + 734 + 182 rows); every other composite ran
at 0.08. The only hypothesis simulated at several truncations is usa_short_x_profitability_x_accruals: 0.08 →
0.66 (n 697, 95 %), 0.15 → 0.63 (256, 89 %), 0.20 → 0.78 (39, 85 %). If truncation 0.15 were what removes the
sub-universe Sharpe, that series would have dropped from 0.66 toward 0; it moved −0.03. So truncation is not
established as the mechanism, and re-running the IV composites at 0.08 is predicted (EX-ANTE from this
series) to move retention by ≈ 0.03, i.e. to leave them at 0 / N. Worth a 60-sim probe (§6.3) because the
interaction on *these* composites was never measured; not worth a day.

### 4.5 Arms and cells (for the round record)
Arm retention (Sharpe ≥ 0.8): standing rows 0.385 (45 % pass, n 4,429); A/B `current` 0.151 (23 %, n 1,361 —
this arm is 70 IV-spread constructions per round); `new` 0.503 (66 %, n 488; ravenpack_x_short 79 %,
newsneg_x_short 7 %). Cells: Short Interest 0.484 (56 %), Social Media 0.349 (44 %), Sentiment 0.183 (25 %),
Insiders 0.063 (10 %), News 0.664 (88 %, n 16).

## 5. Candidate mechanisms — none established; MECHANISM: UNKNOWN
For "IV-spread × {sentiment, insider, twitter} has no Sharpe on the sub-universe":
1. **The product's Sharpe comes from names outside the sub-universe** (small caps where firm-level
   sentiment / insider / twitter signals are stronger and IV spreads wider). Separating experiment: simulate
   20 of the ≥-bar IV rows on `universe: TOP1000` (60 sims). If their TOP1000 Sharpe is ≈ 0 the candidate
   survives; if ≥ 1.0 it is refuted (and §2 says the sub value is not that number, so this is a real test).
2. **Truncation 0.15 on a product of two ranks concentrates weight in a way the sub-universe book cannot
   carry.** Separating experiment: the same 20 rows at truncation 0.08 (60 sims). §4.4 predicts ≈ 0.03.
3. **The sub-universe evaluation re-ranks / re-neutralises within the smaller set and the IV × tone product
   has no cross-section there.** Not separable from (1) without knowing the platform's construction (§2
   identity test shows the sub value ≠ a re-simulation).
4. **Option coverage**: option8 fields exist only for optionable names; whether the sub-universe is where
   they are dense or sparse is unknown. SPECULATION; no journal field measures it.
None of the four is favoured here. Plausibility is not evidence.

## 6. The lever (one), its EX-ANTE expected effect, and the A/B
### 6.1 Lever: a third leg from the fundamental6 family on the IV-spread composites, same three cells
The strongest regularity in §4 is that a fundamental6 leg (usa_profitability_ratios / usa_accruals_cashflow)
sits in every high-retention composite — five different partners (us_short_sale 0.66, twitter 0.66–0.77,
insider_agg_matrix 0.71, short_interest_pred 0.63–0.82) — and the composites that reach the Sharpe bar on the
Sentiment / Insiders / Social Media cells are exactly the IV-spread ones (161 rows ≥ 1.58; the fundamental6
pairs on those cells have 0 rows ≥ 1.58: twitter×prof max 1.41 in 2,381 sims, insider×prof×accruals max 1.25
in 490, sentiment×prof×accruals max 0.82 in 540). The untested cell is the triple:

```
usa_sentiment_x_ivspread_x_profitability   legs [sentiment_weekly_continuation, option_call_put_iv_spread, usa_profitability_ratios]
usa_insider_x_ivspread_x_profitability     legs [insider_significant_buying_drift, option_call_put_iv_spread, usa_profitability_ratios]
usa_twitter_x_ivspread_x_profitability     legs [social_twitter_sentiment_continuation, option_call_put_iv_spread, usa_profitability_ratios]
combiners [multiply]   (compose.py: a third leg is always multiplied)   settings: neutralization [STATISTICAL, SUBINDUSTRY], decay [4, 8], truncation 0.08
```
(leg ids as in the existing `usa_*_x_ivspread.yaml` files, verified.) Truncation 0.08
rather than 0.15 so the arm matches every other composite; §4.4 says this choice is worth ≈ 0.03 and it is
stated here so it cannot be read as the mechanism afterwards. An accruals variant (`usa_accruals_cashflow` as
the third leg) is the alternate if profitability is refused by the structural gate. These go to
`forge/composites/staged/` — nothing in `forge/composites/` is changed by this document.

Purpose (gate 1): rows at the Sharpe bar on the Sentiment / Insiders / Social Media cells that also pass
LOW_SUB_UNIVERSE_SHARPE — today 0 / 161. Provenance (gate 2): §3–§4 of this document, measured 2026-09-09.

### 6.2 EX-ANTE expectation (written before any simulation of the triple)
- Primary: among new-arm rows with Sharpe ≥ 1.58, **LOW_SUB_UNIVERSE_SHARPE PASS ≥ 50 %** (the fundamental6
  composites sit at 78–100 %; half of that band is the "đột phá" line). Refuted if < 20 % with N ≥ 30 rows at
  the bar; inconclusive if N < 30.
- Secondary (the cost): rows ≥ 1.58 per 1,000 sims on the triple vs the current IV pairs (161 / 3,329 = 48 per
  1,000 over the four IV composites; sentiment×IV 59 / 870 = 68). A third rank multiplied in has lowered the
  Sharpe of every fundamental6 pair on these cells to < 1.42 max; the triple keeps the IV leg, so the prior is
  in between. If rows ≥ bar fall below 10 per 1,000 the lever is not a route to submissions even if the
  primary holds.
- What it does **not** fix: the IV rows at the bar fail LOW_FITNESS ≥ 97 % (01_origins: 40/40, 39/40, 30/30;
  fitness = Sharpe·√(|returns| / max(turnover, 0.125)); their returns p50 4.4–4.5 % at turnover 0.19–0.32) and
  IS_LADDER 40–90 % (32/40, 16/40, 27/30). The
  sub-universe is one of three heads of bottleneck #2; this lever is scored on its own head only.

### 6.3 A/B design (Q24: 50 / 50 on the same cells)
- Arm A (current): the three IV pairs as they run (70 constructions / round). Arm B (new): the three triples,
  same cells, same draw count, tag `meta.arm = subu3`. One quota day; the rung is not the metric for this
  layer — the funnel row "≥ bar ∧ sub PASS" per arm per 1,000 sims is, plus the primary/secondary above.
- Probes, ≤ 120 sims, **diagnostics not levers**, run first if the Operator has the slack: (a) 20 IV rows at
  the bar re-simulated on TOP1000 (mechanism candidate 1); (b) the same 20 at truncation 0.08 (candidate 2;
  prediction ≈ +0.03). Both are settings-only, no yaml change; both answer §5, neither reaches a submission.
- Gate 5 (no conflict): the triple is a new mechanism key on the same cells; it touches no gate, no allocator
  state, no submit rule. The structural gate H1/H2/H4 must accept a 3-rank product (usa_short's triple already
  passes it). The DSR pool is per (hypothesis, cell), so the triple starts a new pool (N small, documented).

## 7. What this document does not establish
- What the sub-universe is or how the platform scores it (§2: shape and constants only; identity refuted).
- Why IV × tone products lose all Sharpe there (§5: four candidates, zero experiments).
- Whether the triple reaches the Sharpe bar at all (§6.2 secondary) — the A/B measures it.
