# harness5 — round 2 diagnosis: the IS-ladder wall (this session, 2026-09-09 14:30 local)

Source: `state/layered/runs/forge.jsonl` pulled 14:18 local (25,035 rows, 22,130 distinct alphas),
USA/d1 COMPLETE rows with checks: **11,298** (one row per alpha id, last row wins). Every number
below is re-derivable from that file with the rules stated; nothing here was simulated.

## 1. The rule, decoded from 11,298 check rows (API-OBSERVED, not documentation)
`IS_LADDER_SHARPE` reports one rung: `{result, year, startDate, endDate, limit, value}`.
| (result, year, limit) | n | value range | turnover range | window |
|---|---|---|---|---|
| FAIL, 2, 1.58 | 10,068 | −3.8 … 1.58 | 0.03 … 1.68 | 2022-01-03 → 2024-01-02 |
| WARNING, 2, 1.58 | 429 | −0.29 … 1.57 | | same |
| PASS, 3, 2.02 | 302 | 2.02 … 2.84 | 0.06 … 0.28 | 2021-01-03 → 2024-01-02 |
| FAIL, 5, 1.58 | 115 | 1.26 … 1.58 | | 2019 → 2024 |
| PASS, 2, 2.02 | 87 | 2.02 … 2.38 | 0.07 … 0.30 | 2022 → 2024 |
| FAIL, 3/4/6/7/8, 1.58 | 86 / 72 / 73 / 3 / 2 | | | |
| PASS, 4, 2.02 | 14 | | | |
| PASS, 2, 2.37 | 2 | 2.39 … 2.47 | 0.32 … 0.40 | |

Reading (pattern, consistent with SUBMISSION_GATES.md "iterative 2→10 years; turnover < 30 % gets a
0.85× discount"): the check walks trailing windows ending **2024-01-02**; the first window is the
2-year one (2022-01-03 → 2024-01-02) with limit 1.58; a row that fails there reports year 2. Rows
that PASS report a value ≥ 2.02 (= 0.85 × 2.37) at turnover < 0.30, or ≥ 2.37 above it. **Every one
of the 18 all-binding passers on USA/d1 carries a ladder value of 2.02–2.35.** The 5-year
LOW_SHARPE line 1.58 is therefore not the Sharpe bar a submission needs: the trailing 2022–2024
window must clear 1.58 AND a 2- or 3-year window must clear 2.02.
MECHANISM of the platform rule beyond this: UNKNOWN (the doc's exact rung schedule is not on file).

Definition used below: **y2pass** = ladder result PASS, or a FAIL/WARNING reported at year ≥ 3 (the
2-year window was cleared). 800 of 11,298 rows are y2pass.

## 2. Where the ladder kills (MEASURED)
Rows ≥ 1.58 (5-year): 539. Failing-check patterns among them (CLUSTER_TEST is non-binding, omitted):
| pattern | n |
|---|---|
| ladder + fitness + sub-universe | 210 |
| fitness + sub-universe | 82 |
| sub-universe only | 63 |
| ladder + fitness | 62 |
| ladder + sub-universe | 52 |
| fitness only | 49 |
| none (all-binding pass) | 18 |
| ladder only | 3 |
Ladder fails 327 / 539 rows at the bar (61 %); it is the sole failure on 3.

Per composite (USA/d1): n · rows ≥ 1.58 · y2pass · y2pass ∧ ≥ 1.58 · all-binding · best y2 value
| composite | n | ≥1.58 | y2pass | both | pass | y2 max |
|---|---|---|---|---|---|---|
| short_x_sentiment | 2,485 | 0 | 0 | 0 | 0 | 1.25 |
| usa_twitter_x_profitability | 2,141 | 0 | 91 | 0 | 0 | 2.31 |
| usa_twitter_x_ivspread | 810 | 28 | 83 | 7 | 0 | 2.47 |
| usa_short_x_profitability_x_accruals | 801 | 57 | 176 | 26 | 0 | 2.37 |
| usa_sentiment_x_ivspread | 750 | 51 | 133 | 27 | 0 | 2.28 |
| usa_insider_x_ivspread | 729 | 52 | 83 | 38 | 0 | 2.38 |
| options_x_short | 663 | 311 | 218 | 167 | **18** | 2.19 |
| usa_shortsurprise_x_ivspread | 540 | 7 | 0 | 0 | 0 | 1.30 |
| ravenpack_x_short (round-1 arm) | 300 | 33 | **0** | 0 | 0 | 1.57 |
| newsneg_x_short (round-1 arm) | 280 | 0 | 0 | 0 | 0 | 1.20 |
| others (≤ 500 each) | | 0 | ≤ 5 | 0 | 0 | ≤ 1.58 |

OBSERVATION: the round-1 bar-reacher (news46 tone × short-flow) never clears the 2022–2024 window
in 300 rows (best 1.57); the composites that do clear it AND the 5-year bar (five of them, 265 rows)
die at fitness / sub-universe, except options_x_short.

## 3. Two POST-HOC regularities and one refutation
**a. Per leg** (composite rows with Sharpe ≥ 1.3; a row counts once per leg it contains):
| leg | n | y2pass rate |
|---|---|---|
| sentiment_weekly_continuation | 247 | 0.42 |
| insider_significant_buying_drift | 204 | 0.40 |
| usa_accruals_cashflow | 184 | 0.40 |
| option_call_put_iv_spread | 1,251 | 0.37 |
| usa_profitability_ratios | 206 | 0.35 |
| short_volume_ratio_informed | 858 | 0.34 |
| social_twitter_sentiment_continuation | 223 | 0.26 |
| news_ravenpack_composite_tone | 124 | **0.00** |
| short_interest_surprise | 61 | **0.00** |
| news_negative_tone_nlp | 6 | 0.00 |
Pattern, not mechanism: the two legs added after the original library (news46 tone, short-interest
surprise) never clear the 2-year window in any composite. MECHANISM: UNKNOWN. Candidates, none tested:
the 2022–2024 window is where those datasets' coverage or the tone's information changed; the
composite's other leg dominates; chance at n 61–124 (a 0/124 against a base rate 0.35 is not chance).

**b. Regime maps do not predict the window.** Every composite's EX-ANTE `regimes.rate_shock_2022`
sign vs its year-2 ladder value on rows ≥ 1.3: '+' composites — options_x_short p50 1.26 (20 rows
≥ 1.58 of 337), usa_short p50 1.31 (16/124), ravenpack 1.03 (0/124), shortsurprise×IV 0.74 (0/52);
'0' composites — insider×IV 1.35 (11/133), sentiment×IV 1.31 (18/156), twitter×IV 1.25 (7/157).
The '0' group clears the 2022–2024 window as often as the '+' group. **REFUTED as a screen:** the
maps carry no measured information about the ladder. They stay in the files as the standard's
EX-ANTE reasoning; they must not be used to rank composites.

**c. Simulations are deterministic.** 4 constructions simulated twice under different alpha ids
(2026-09-06) returned identical Sharpe / fitness / turnover. A paired design against journal
originals is valid (no re-simulation of the control is needed).

## 4. A retrospective allocator rule (POST-HOC, in-sample; NOT shipped — RULE 2)
Rule tested on the journal: after a composite's first 40 USA/d1 rows (by dateCreated), if **no row
has cleared the 2-year window**, stop simulating it.
| composite | n | y2 cleared by row 40? | later all-binding passes |
|---|---|---|---|
| short_x_sentiment | 2,485 | no (1.02) | 0 |
| usa_twitter_x_profitability | 2,141 | no (0.82) | 0 (cleared later, 91 rows; 0 at bar) |
| usa_shortsurprise_x_ivspread | 540 | no (0.64) | 0 |
| usa_sentiment_x_profitability_x_accruals | 500 | no (1.19) | 0 |
| usa_shortsurprise_x_profitability | 440 | no (1.07) | 0 |
| ravenpack_x_short | 300 | no (1.57) | 0 |
| newsneg_x_short | 280 | no (1.09) | 0 |
| prtone / transcript / creditlang | 90 / 50 / 80 | no | 0 |
| options_x_short | 663 | yes (2.06) | 18 |
| usa_short / sentiment×IV / insider×IV / twitter×IV / insider×prof×accr / headline / multiwire | | yes (1.58) | 0 |
Sims the rule would have stopped: ≈ 6,500 of 11,298 (58 %); all-binding passes it would have lost:
0. This is in-sample on the same rows (the rule was written after seeing them) and the 5 composites
that cleared year 2 at row 40 without ever passing show the rule is a necessary screen, not a
sufficient one. It is a candidate for a tick, with a live measurement (sims per all-binding pass,
rounds with vs without), not a shipped mechanism.

## 5. What this changes for round 2
- The fitness diagnosis (diagnosis_fitness.md §7) already shows a σ lever adds 0 submissions on the
  current library; this document adds that the round-1 mechanism cannot pass regardless of σ.
- A new mechanism needs, on the same row: 5-year Sharpe ≥ 1.58, 2022–2024 Sharpe ≥ 1.58, a 2- or
  3-year window ≥ 2.02 (turnover < 0.30), fitness ≥ 1, sub-universe retention ≥ 0.433, then prod and
  self correlation < 0.7. In 22,130 simulated alphas exactly one composite has done the first five.
- Supply is the lever with measured headroom: the promoted composites (7, 14:27 today) and the three
  sub-universe triples pair new legs with the legs whose y2pass rate is 0.35–0.42 (§3a). Whether that
  rate transfers is the measurement, not a prediction.
