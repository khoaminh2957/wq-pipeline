# harness5 — round 2 diagnosis: the fitness ceiling (Researcher, 2026-09-09 14:30 local)

Sources, read-only: VPS `state/layered/runs/forge.jsonl` (24,750 lines; 22,084 distinct alphas with
checks after keying by `alpha`, last row wins; platform `dateCreated` 2026-09-04 01:55 → 2026-09-09
03:08 ET), VPS `state/forge/corr.jsonl` (262 lines, 74 alphas), `docs/redesign/02_design.md`
§11l–§11u, `OPERATORS.md`, `SUBMISSION_GATES.md`, `forge/score.py`. Nothing was simulated; nothing
was written on the VPS; nothing in `forge/hypotheses`, `forge/composites`, the unit or the loop was
touched. Every count below was derived twice (both routes stated). Labels per RULE 0: **MEASURED**,
**EX-ANTE**, **POST-HOC** (a regularity, never an explanation), **SPECULATION**; mechanisms not
separated by an experiment are **UNKNOWN**. Binding-check rule = `forge/score.py` NON_BINDING
(SELF/PROD/POWER_POOL corr, MATCHES_*, CLUSTER_TEST, DATA_DIVERSITY, OSMOSIS_ALLOCATION,
REGULAR_SUBMISSION); `OSMOSIS_ALLOCATION` reads WARNING on 22,084 / 22,084 rows and is non-binding
by that list, so it is not a new wall.

## 1. The fitness identity, restated as a book-volatility bar (EX-ANTE arithmetic, verified)

Platform fitness = Sharpe · √(|returns| / max(turnover, 0.125)). MEASURED: max |error| 0.0050,
p99 0.0049 on 13,633 USA/d1 rows (same ±0.005 as 01_origins on 140 rows). Since annual returns =
Sharpe · σ where σ is the book's annualised PnL volatility, the identity is

    fitness = Sharpe^1.5 · √(σ / max(turnover, 0.125))
    fitness ≥ 1  ⇔  Sharpe ≥ (max(turnover, 0.125) / σ)^(1/3)

"Returns at equal Sharpe" IS σ. Consequences (arithmetic, not mechanism):
- Sharpe carries exponent 1.5, σ and turnover 0.5: +10 % Sharpe = +15 % fitness; +10 % σ = +5 %.
- Sharpe needed for fitness ≥ 1 at turnover ≤ 0.125: σ 0.018 → 1.91; 0.020 → 1.84; 0.025 → 1.71;
  0.030 → 1.61; **0.0316 → 1.58** (fitness stops binding at the cell bar); 0.040 → 1.46.
  At turnover 0.21 (ravenpack rows over the bar): σ 0.019 → 2.23; 0.030 → 1.91; 0.040 → 1.74.
- Below turnover 0.125 the only levers are Sharpe and σ (01_origins §1 said this for usa_short);
  ABOVE 0.125 turnover is still a lever worth √(turnover/0.125) — see §2, 80 % of the failing rows.

σ is a far tighter statistic than Sharpe (MEASURED, rows Sharpe > 0.5): IQR/median of σ inside a
(hypothesis, neutralisation) cell 0.03–0.13 (options×short 0.07/0.13/0.09; ravenpack 0.03/0.11/0.09;
usa_short STATISTICAL 0.08) against 0.22–0.28 for Sharpe. A 40-draw arm reads a 10 % σ change; it
cannot read a 0.1 Sharpe change (02_design §11l: a 20-draw Sharpe median wobbles ±0.4).

## 2. The measured funnel at the fitness stage (USA/d1, journal to 2026-09-09 03:08 ET)

| stage | rows | of previous | second derivation |
|---|---|---|---|
| USA/d1 simulated with checks | 14,660 | — | 02_dataset_map counted 10,686 at 09-08 09:30 UTC; +3,974 since |
| Sharpe ≥ 1.58 | 715 | 4.9 % | 01_origins 598 at 09-08 16:39 local; +117 since (round-1 arms) |
| LOW_FITNESS not PASS | 562 | 78.6 % | by check `value` < 1.0: 562; by journal `fitness` < 1.0: 562; by the formula: 566 (4 rows at the 0.995–1.005 rounding boundary) |
| fitness PASS | 153 | 21.4 % | 142 options×short, 8 usa_short×prof×accr, 3 insider×ivspread |
| … and IS_LADDER + SUB_UNIVERSE + CONCENTRATED + HIGH_TURNOVER pass | 21 | 13.7 % | 01_origins: 21 (no new pass since 09-06 21:10) |
| rows over the bar failing ONLY fitness (ladder, sub, conc, turnover pass) | 79 | — | 598 − 21 − 64 − 8 − 58 = 447 fitness fails in 01_origins ⇒ 79 sole (their table); here 100 rows have every other binding check PASS, 21 of them pass fitness |

The 562 failing rows (MEASURED): fitness p50 0.81, Sharpe p50 1.67, turnover p50 0.176, returns p50
3.75 %, required/actual returns p50 1.51 [p25 1.26, p75 2.06]. **Only 20.1 % sit at turnover ≤ 0.125**;
for the other 80 % turnover is still a live factor. Among the 79 sole-fitness rows (usa_short 53,
options×short 26; STATISTICAL 55): σ multiplier needed at held Sharpe and turnover (1/fitness)² p50
1.35 [1.23, 1.45]; 57 % have turnover > 0.125 and cutting turnover to the floor alone would pass 28 %.

Per hypothesis over the bar (n / fitness fails / p50 fitness / turnover / returns / σ / max fitness):

| hypothesis | n | fit fail | fit | tvr | ret | σ | max fit | ladder pass | sub pass |
|---|---|---|---|---|---|---|---|---|---|
| options_x_short | 342 | 200 | 0.95 | 0.157 | 0.049 | 0.0287 | 1.24 | 0.47 | 0.20 |
| usa_short_x_profitability_x_accruals | 140 | 132 | 0.86 | 0.103 | 0.034 | 0.0206 | 1.03 | 0.39 | 1.00 |
| usa_insider_x_ivspread | 66 | 63 | 0.80 | 0.191 | 0.046 | 0.0280 | 1.07 | 0.53 | ≈0 |
| **ravenpack_x_short** (round-1 `new`) | 62 | 62 | 0.68 | 0.211 | 0.032 | 0.0192 | 0.81 | **0.00** | 0.43 |
| usa_sentiment_x_ivspread | 61 | 61 | 0.68 | 0.257 | 0.044 | 0.0271 | 0.82 | 0.26 | ≈0 |
| usa_twitter_x_ivspread | 35 | 35 | 0.59 | 0.323 | 0.044 | 0.0269 | 0.74 | 0.09 | ≈0 |
| usa_shortsurprise_x_ivspread | 8 | 8 | 0.78 | 0.195 | 0.046 | 0.0285 | 0.93 | — | — |

ravenpack_x_short against round_1.md (n 400 / 53 ≥ 1.58 / fitness max 0.81 / turnover p50 0.16 at
22:35 on 09-08): now n 480 / 62 / 0.81 / 0.161 — consistent, grown. Only its STATISTICAL rows reach
the bar (60 of 159; INDUSTRY 1 of 172, SUBINDUSTRY 1 of 149).

**The wall behind the fitness wall (MEASURED).** Every ravenpack row over the bar fails
IS_LADDER_SHARPE: 0 / 60 by result, 0 / 60 by `value ≥ limit`; ladder value p50 0.98 [p25 0.85,
p75 1.17, max 1.49] against limit 1.58 (year-2 window 2022-01-03 → 2024-01-02). Unconditionally the
ladder/full-Sharpe ratio for ravenpack is 0.95 (n 480), so the rows selected at ≥ 1.58 are the ones
whose Sharpe sits in the early years (ratio 0.60 on the 60). Sub-universe passes 43 % (value p50
0.695 vs limit 0.71). A σ or turnover lever leaves a trailing-window Sharpe unchanged by
construction; **with fitness solved, ravenpack's expected passes stay 0 until the ladder moves.**
MECHANISM of the recent-window weakness: UNKNOWN (candidates, none tested: signal decay after 2022;
crowding of news46, 324 users; a 2022–2023 regime the tone×short-flow composite does not carry).
The same pattern on the other STATISTICAL bar-reachers: options×short STATISTICAL ladder pass 10 %
(value p50 1.23) vs its INDUSTRY 54 % / SUBINDUSTRY 69 % (value 2.07 / 2.15 against the year-3
limit 2.02); usa_short 39 %.

**Where fitness is the SOLE remaining wall: 79 rows, two mechanism keys, both already HARVESTED**
(vRk095rv, kqVbg1xP posted; one submission per mechanism). Sensitivity on the 100 rows that pass
every other binding check, at held Sharpe and turnover (arithmetic on existing rows):

| σ × | fitness passers of 715 | all-binding of 100 | same, turnover → 0.125 |
|---|---|---|---|
| 1.00 | 149 (153 by check) | 21 | 43 |
| 1.10 | 193 | 27 | 53 |
| 1.20 | 253 | 34 | 61 |
| 1.35 | 349 | 59 | 74 |
| 1.50 | 429 | 86 | 96 |

None of these adds a submission on the current library (same two keys, over the correlation lines
18/21). The fitness lever pays only on a NEW mechanism that reaches the bar with ladder and
sub-universe intact — and round 1's one bar-reacher does not.

## 3. What co-varies with |returns| at equal Sharpe (USA/d1, Sharpe ≥ 1.4, n 1,543) — POST-HOC

Three derivations per covariate: (A) p50 returns inside Sharpe bins 1.4–1.6 / 1.6–1.8 / ≥ 1.8;
(B) p50 σ = returns/Sharpe (Sharpe-free by identity; OLS gives log-returns ∝ log-Sharpe with slope
1.001 ± 0.032, so σ and Sharpe are unrelated in this range); (C) OLS of log returns on log Sharpe +
dummies (n 520 rows with the modal levels, R² 0.936; coefficients are log-ratios vs the base level).

| covariate | levels (n) | (A) returns by Sharpe bin | (B) σ p50 | (C) OLS | verdict |
|---|---|---|---|---|---|
| **neutralisation** | STATISTICAL 754 / SUBINDUSTRY 616 / INDUSTRY 173 | 0.030 / 0.034 / 0.039 vs 0.042 / 0.048 / 0.058 vs 0.044 / 0.050 / 0.057 | **0.0200 / 0.0281 / 0.0300** | +0.32 (t 35) / +0.40 (t 41) | the dominant σ term: **+40–55 %** |
| book breadth (long+short) | ≥ 3,100: 751 / 2,800–3,100: 253 / 2,000–2,800: 503 / < 2,000: 36 | 0.030 / 0.043 / 0.041 / 0.054 (bin 1) | 0.0200 / 0.0288 / 0.0280 / 0.0350 | log names −0.36 (t −9) | **not identified**: names ≡ neutralisation (STATISTICAL 3,125 on every row; INDUSTRY 2,793; SUBINDUSTRY 2,677) |
| combiner | multiply 900 / gate 643 | 0.031 / 0.038 (bin 1) | 0.0211 / 0.0259 raw; **within hypothesis × neut gate is 4–7 % LOWER** | −0.077 (t −13) | gate is not a σ lever (the zeroed half is refilled by neutralisation, round_1 audit) |
| truncation | 0.08: 784 / 0.15: 745 / 0.20: 14 | 0.030 / 0.038 / 0.033 (bin 1), 0.046 / 0.041 (bin 2) | 0.0209 / 0.0252 / 0.0218 raw; 0.0204 / 0.0206 inside usa_short | −0.04 (t −6) | dead: not binding on 2,700–3,125-name books (CONCENTRATED_WEIGHT PASS 715 / 715) |
| decay (platform) | 4: 825 / 8: 715 | 0.035 / 0.036 | 0.0227 / 0.0258 raw; 0.0287 / 0.0287 inside options×short | +0.01 (t 2) | no σ effect; a turnover lever (§5) |
| group inside group_rank | sector 178 / industry 189 / subindustry 154 / mixed 1,021 | 0.033 / 0.036 / 0.034 | 0.0213 / 0.0249 / 0.0254 | −0.02 / −0.08 vs sector | ≤ 8 %, sign against sector; not a lever |
| leg count | 2: 1,269 / 3: 274 | 0.038 / 0.031 | 0.0268 / 0.0205 raw | +0.026 per leg net | raw difference is usa_short (STATISTICAL, 3 legs); net ≈ 0 |
| window w (ts_mean) | w ≤ 5: 929 / 10: 429 / ≥ 20: 185 | 0.036 / 0.035 / 0.032 | 0.0254 / 0.0231 / 0.0207 raw; **0.0198 / 0.0200 / 0.0200 inside options×short STATISTICAL** | — | σ flat; turnover 0.188 → 0.157 → 0.127 — a turnover lever only |
| universe | TOP3000 1,538 / TOP1000 5 (R21 n 40 all-Sharpe) | — | R21 0.0239 vs like-for-like R16/R22 0.0202 (+18 %) | — | Sharpe p50 1.20 vs 1.25–1.49 at n 40 (02_design R21 "below") |
| hypothesis | 7 with n ≥ 40 | 0.029–0.041 (bin 1) | 0.0193–0.0280 | — | entirely explained by its neutralisation mix (next table) |

Stratified within hypothesis × combiner (rows ≥ 1.4; σ p50 [p25, p75]; STATISTICAL → INDUSTRY /
SUBINDUSTRY):

| hypothesis · combiner | STATISTICAL | INDUSTRY | SUBINDUSTRY | Sharpe p50 S / I / Sub (conditional) |
|---|---|---|---|---|
| options×short · multiply | 0.0205 [0.0200, 0.0209] n 98 | 0.0311 [0.0305, 0.0331] n 67 | 0.0301 [0.0294, 0.0307] n 85 | 1.75 / 1.74 / 1.76 |
| options×short · gate | 0.0193 n 76 | 0.0288 n 96 | 0.0278 n 83 | 1.53 / 1.58 / 1.58 |
| insider×ivspread · multiply | 0.0221 n 47 | — | 0.0314 n 72 | 1.54 / — / 1.58 |
| sentiment×ivspread · multiply | 0.0204 n 15 | — | 0.0281 n 95 | 1.46 / — / 1.53 |
| ravenpack×short · gate | 0.0189 n 57 | 0.0325 n 9 | 0.0316 n 8 | 1.59 / 1.46 / 1.46 |
| usa_short×prof×accr · multiply | 0.0205 n 274 | (no row ≥ 1.4) | (no row ≥ 1.4) | 1.58 / — / — |

The regularity, all rows Sharpe > 0.3, hypotheses with n ≥ 30: **under STATISTICAL σ p50 lies in
0.0183–0.0222 for 14 of 14 hypotheses (median of medians 0.0198); under INDUSTRY/SUBINDUSTRY
0.0273–0.0514 for 16 of 16 (median 0.0324).** σ under STATISTICAL does not depend on the fields.
MECHANISM: UNKNOWN. Candidates (none tested): (i) STATISTICAL removes variance along statistical
risk factors that INDUSTRY leaves in the book, and that variance carries no return; (ii) the names
INDUSTRY drops (3,125 → 2,793) are the low-vol ones; (iii) rank weights on a 3,125-name book under
a full factor neutralisation leave ≈ 2 % idiosyncratic σ whatever the signal. R21 (TOP1000, 1,035
names) read +18 % σ, not the +73 % of an equal-weight idiosyncratic book at a third of the names, so
(iii) alone is not it. The platform's definition of STATISTICAL is not in the repo's docs.

Second regularity, POST-HOC: the Sharpe cost of leaving STATISTICAL depends on the mechanism
(unconditional p50 / p90, rows ≥ 1.58 per 1,000):
- short-volume-leg composites lose ≈ 0.4–0.5: ravenpack×short 1.51 / 1.68 (377 /1k) → INDUSTRY 1.08 /
  1.31 (6 /1k); usa_short×prof×accr 1.37 / 1.68 (230 /1k) → 0.97 / 1.16 (0); newsneg×short 0.96 →
  0.49; short×sentiment 0.83 → 0.67; twitter×profitability 0.88 → 0.59.
- IV-spread composites lose nothing or gain: options×short 1.51 / 1.93 (411 /1k) → INDUSTRY 1.54 /
  1.77 (464) / SUBINDUSTRY 1.57 / 1.81 (494), with fitness pass over the bar 13 → 60 → 69 and
  all-binding passes 2 → 7 → 10; insider×iv 0.93 → SUBINDUSTRY 1.20; sentiment×iv 0.98 → 1.31.
MECHANISM: UNKNOWN. This is why 17 of the 21 passers are INDUSTRY/SUBINDUSTRY options×short at
Sharpe 1.64–1.87 (σ 0.029–0.035) while the 4 STATISTICAL passers needed Sharpe 1.85–2.08 (σ 0.020–
0.021) — the arithmetic of §1, not a finding about the signals.

## 4. Cost side of the σ levers (POST-HOC; rows ≥ 1.58 inside options×short, the one mechanism with both arms at the bar)

| arm | n | fitness pass | IS_LADDER pass | SUB_UNIVERSE pass | CONCENTRATED pass | σ | prod-corr read (n) |
|---|---|---|---|---|---|---|---|
| STATISTICAL | 99 | 0.13 | 0.10 | 0.21 | 1.00 | 0.0201 | 0.565 p50, 0.47–0.95 (20) |
| INDUSTRY | 115 | 0.52 | 0.54 | 0.18 | 1.00 | 0.0302 | 0.650, 0.53–0.81 (17) |
| SUBINDUSTRY | 128 | 0.54 | 0.69 | 0.21 | 1.00 | 0.0294 | 0.610, 0.51–0.83 (24) |

No measured cost on sub-universe or concentration; ladder passes MORE under INDUSTRY/SUBINDUSTRY
here (opposite of a cost; MECHANISM UNKNOWN). Prod-corr: ranges overlap, n ≤ 24, and the readings
were taken against a book that changed on 09-06 (kqVbg1xP posted; 02_design §11s) — no verdict. The
pooled table (all hypotheses) shows sub-universe 0.55 STATISTICAL vs 0.19 INDUSTRY: that is usa_short
(sub 1.00, STATISTICAL-only over the bar) — a hypothesis confound, not a neutralisation effect.

## 5. Already measured — levers not to propose again (02_design §11l–§11u, re-read from the journal)

| recipe (n) | what | measured | verdict on σ / fitness |
|---|---|---|---|
| R14 (40) decay 16/32 | turnover 0.121 → 0.062 | fitness 0.52 → 0.45, Sharpe max 1.67 → 1.53 | dead below the 0.125 floor (identity) |
| R15 (40) ts_decay_linear(10) | smoothing | max 1.47 | dead, same reason |
| R16 (40) truncation 0.15 | cap 8 % → 15 % | σ 0.0202 vs 0.0204; two rows fail only fitness 0.87 | not binding; dead |
| R17 (40) signed_power(·, 2) | tail stretch | **σ 0.0246 vs R16 0.0202 (+22 %)**, Sharpe p50 1.17 vs 1.25, max 1.46 vs 1.67, fitness p50 0.55 vs 0.56 | σ gain is outside the σ noise (IQR/med 0.08); the Sharpe cost is a 40-vs-40 read inside the ±0.3 wobble — **UNRESOLVED**, not dead; net fitness flat at this n |
| R18 (40) power 2 + trunc 0.15 | both | σ 0.0252, Sharpe p50 1.14, fitness 0.53 / max 0.80 | as R17 |
| R23 (40) signed_power 1.5 + trunc 0.2 | milder | σ 0.0222 (+10 %), Sharpe p50 1.26 / max 1.62, fitness p50 0.58 / max 0.85, CONCENTRATED PASS 40/40 | as R17; the doc only queued it, this is its first record |
| R19 (40) MARKET / CROWDING / SLOW_AND_FAST | other neutralisations | σ 0.034 / 0.028 / 0.020 but Sharpe p50 1.03 / 0.90 / 0.54 | dead on Sharpe (n 10–17) |
| R20 (58) group = sector | Sharpe 1.67, fitness 1.03 | σ 0.0209 — a Sharpe effect, and §11s found it not general | not a σ lever |
| R21 (40) TOP1000 | universe | σ +18 %, Sharpe p50 1.20 | dead on Sharpe at n 40 (one pair) |
| C11 arm S (8 pairs) | STATISTICAL on INDUSTRY formulas | Sharpe Δ −0.05, fitness 0.75–0.93, ladder 8/8 fail | the §3 regularity at n 8 |
| B6 settings prior (§11r) | STATISTICAL > INDUSTRY on every USA cell | Sharpe only; σ never read | §3 shows the fitness side is the reverse |
| skills boost-fitness / boost-returns | decay, hump, truncation, "less clipping" | turnover / concentration levers | dead below the floor; truncation not binding |

## 6. Operator semantics (EX-ANTE, from OPERATORS.md and SUBMISSION_GATES.md) — what moves σ at an unchanged ordering, and what it costs

- `signed_power(x, y)` = sign(x)·|x|^y. y > 1 stretches the tails of the position vector: the sum
  of |w| is renormalised by the platform, so the largest names gain weight, the effective number of
  names 1/Σw² falls, σ rises. Ordering unchanged. Sharpe: NOT constant EX-ANTE — it moves with how
  the signal's information is distributed across the ranks (unknown sign). Costs: CONCENTRATED_WEIGHT
  (max weight 10 %, SUBMISSION_GATES) — measured PASS 120/120 at y = 1.5–2 on 3,125-name books;
  IS_LADDER is a trailing-window Sharpe, so it moves with Sharpe, not with σ; LOW_SUB_UNIVERSE limit
  = 0.75·√(sub/alpha)·alpha_Sharpe is also σ-free, but a stretch that lands unevenly across
  sub-universes changes it (unmeasured). This is the one σ transform with a measured gain.
- `power(x, y)`: unsigned; fractional y on a signed input is NaN (the docs' own example failed);
  usable only before neutralisation on a non-negative product of ranks, where it equals signed_power.
- `scale(x, scale, longscale, shortscale)`: rescales Σ|x| to a constant. The platform normalises the
  book anyway → relative weights unchanged → σ unchanged. longscale ≠ shortscale creates a net
  long/short imbalance that the neutralisation removes. Dead as a returns lever.
- truncation (setting): caps one name's |weight| at that fraction of the book. With 2,700–3,125
  names the largest weight is far under 8 % (CONCENTRATED PASS 715/715; R16 σ unchanged). Not
  binding, hence not a lever, in either direction, on these books.
- `winsorize(x, std)`: clamps beyond ±std·σ → SHRINKS the tails → σ down. Wrong direction for
  returns; it is a CONCENTRATED_WEIGHT remedy if a power lever ever trips that check.
- rank → `zscore` on a leg: keeps the raw tail shape → heavier tails than a uniform rank → σ up,
  by an amount that depends on the field's distribution. Measured only on the typed-grammar rows
  (Sharpe ≈ 0.1, n 12–36 per pair; σ lower there): no read on a bar-reaching mechanism.
- window / decay / ts_decay_linear / hump: average positions over time → turnover down, σ ≈ flat
  (measured: σ 0.0198–0.0200 across w 5/10/20). Their fitness value is √(turnover/0.125) while
  turnover > 0.125 and zero below; their Sharpe cost is mechanism-specific (measured on ravenpack,
  §7 L3).
- neutralisation STATISTICAL vs INDUSTRY/SUBINDUSTRY: a platform setting, definition not in the repo;
  measured σ +40–55 %; Sharpe effect mechanism-specific (§3).

## 7. Levers, ranked, with the A/B each would need (expected effect stated BEFORE any run)

Success metric for every arm (Q24, 03_design §3): on the same cells and mechanisms, per 1,000 sims —
rows ≥ 1.58 AND fitness ≥ 1 AND ladder AND sub-universe PASS (all-binding), plus σ p50, Sharpe p50,
turnover p50 per arm. Fitness alone is not the metric: fitness ∝ Sharpe^1.5 and a lever that buys
5 % σ while costing 5 % Sharpe is a loss.

**L1 — signed_power(composite, y) before neutralisation.** [**REFUTED 2026-09-09 15:03, 300 paired sims: σ +4.9 % / +10.6 %, Sharpe −0.11 / −0.23, fitness −0.06 / −0.13, all-binding 2→0 — round_2/pow_pairs.md**] EX-ANTE (§6) + POST-HOC σ (+10–22 %,
R17/R18/R23). Arm `pow15` / `pow2` vs `base`, 150 draws per arm, on usa_short×prof×accr (σ 0.0207,
turnover 0.10 — a pure-σ case; 53 sole-fitness rows) and on options×short STATISTICAL (positive
control). Expected: σ +10 % (y 1.5) / +20 % (y 2) at p50, IQR-tight; fitness × 1.05 / × 1.10 at held
Sharpe; Sharpe p50 within ±0.1 of base (150/arm reads ±0.04). Refuted if σ gain < 5 %, or Sharpe
p50 falls > 0.15, or all-binding passes per 1,000 do not rise. Cost checks to log: CONCENTRATED_WEIGHT
(expect PASS), sub-universe pass rate (expect unchanged; no EX-ANTE guarantee). Caveat: on the
current library this adds passes to two HARVESTED keys, i.e. 0 submissions; its value is as a
default for NEW mechanisms, so the arm must also run on the next new composite that reaches 1.4.

**L2 — neutralisation as a per-mechanism choice, not a per-cell prior.** POST-HOC (§3): σ +40–55 %
under INDUSTRY/SUBINDUSTRY on every mechanism; Sharpe cost 0 on IV-spread composites, −0.4–0.5 on
short-volume-leg composites. Not a new operator — the library grid already draws all three, and
the 17 INDUSTRY/SUBINDUSTRY passers came from it. The lever is allocation: after a mechanism's first
20 draws per neutralisation, drop the arm whose (Sharpe needed by §1 − Sharpe p90) is largest.
Expected: sims on dead (mechanism, neut) pairs fall ≈ 1/3 with no loss of bar-reachers (ravenpack
INDUSTRY+SUBINDUSTRY: 321 sims, 2 rows ≥ 1.58). Refuted if any pair dropped at 20 draws later shows
a bar-reacher rate ≥ 100 /1k on the kept arm's cell. Conflicts to check (RULE 2 gate 5): B6's
untick, the allocator's DEAD/NEAR_MISS states, DSR pool composition (fewer sims → smaller pool).
Confound: a 20-draw read of Sharpe p90 is noisy (±0.4 at the median; the tail is worse).

**L3 — turnover to the 0.125 floor on mechanisms above it (ravenpack 0.17–0.21; IV-spread 0.15–0.35).**
EX-ANTE worth √(tvr/0.125) = × 1.30 at 0.21. MEASURED on ravenpack STATISTICAL, unconditional:
tone window 5 → 10 → 20: Sharpe p50 1.61 → 1.52 → 1.40, rows ≥ 1.58 per 1,000 719 → 309 → 43,
turnover 0.217 → 0.161 → 0.134, σ flat 0.019; decay 4 → 8: Sharpe 1.55 → 1.50, 453 → 288 /1k,
turnover 0.183 → 0.163. Fitness p50 0.61–0.66 under every window pair; max 0.81. On its rows over
the bar: turnover → 0.125 alone gives fitness p50 0.82 and 0 % ≥ 1; with σ × 1.2 also, 12 %; with
σ × 1.5, 57 % — and the ladder is 0/60 regardless. Verdict: on ravenpack no single lever passes
fitness, the stack that would costs the Sharpe tail, and the ladder stays. Not proposed as an arm.

**L4 — rank → zscore (or raw) legs.** SPECULATION on magnitude (EX-ANTE direction only, §6). Arm
`zleg` on options×short STATISTICAL, 150 draws; expected σ +10–30 % with an unknown Sharpe change;
refuted if σ gain < 5 % or CONCENTRATED_WEIGHT starts failing. Rank order after L1's result.

**Dead, do not re-run:** truncation (any value); scale; winsorize (wrong direction); platform decay
16/32 or ts_decay_linear on mechanisms at turnover ≤ 0.125; gate as a concentration device (σ
−4–7 % inside neut); group choice (≤ 8 %); universe TOP1000 (one n-40 pair, Sharpe lower — a
retry would need 150/arm and is not worth the round's budget); MARKET / CROWDING / SLOW_AND_FAST.

**What round 2 is actually looking at (MEASURED, not a lever):** the round-1 arm's one bar-reacher
dies at ladder AND fitness AND (57 %) sub-universe; the 79 sole-fitness rows belong to two already
submitted keys. The fitness stage, corrected for that, is a σ stage whose only measured large lever
is the neutralisation choice, already in the grid. The diagnosis therefore does not support a
round-2 layer built on fitness alone; it supports L1 as a cheap σ default (300 sims to prove or
refute) and L2 as an allocator rule, both measured on all-binding passes per 1,000, and it names
the ladder (recent-window Sharpe) as the next unmeasured wall for new mechanisms.

## 8. Confounds and limits of this document

1. Hypothesis × neutralisation are collinear at the bar: usa_short reaches 1.58 only under
   STATISTICAL, ravenpack likewise; the neutralisation cost/benefit is read within options×short
   (both arms at the bar) and extrapolated nowhere.
2. Book breadth is not identified separately from neutralisation (names is a deterministic function
   of the neut setting in this journal). Any "fewer names → higher σ" reading is the neut reading.
3. §3's first table conditions on Sharpe ≥ 1.4 (selection); the within-hypothesis σ reads use the
   same rows, but σ is Sharpe-independent (OLS slope 1.00), so the selection does not bias σ. The
   Sharpe columns in those tables are conditional and must not be read as Sharpe effects; the
   unconditional Sharpe effects are the per-hypothesis p50/p90 in §3 and the ravenpack windows in §7.
4. Recipe rows R16–R23 are one composite (usa_short) at STATISTICAL with industry/subindustry
   groups; their σ deltas are like-for-like (R16 control), their Sharpe deltas are 40-vs-40 draws.
5. The fitness boundary: 4 rows differ between the check verdict and the formula at 0.995–1.005.
6. Prod-corr by neutralisation (n 17–24) mixes readings before and after kqVbg1xP's POST.
7. The journal projection keys by alpha id, last row wins (158 orphan-recovered duplicates in
   01_origins; here 22,242 rows → 22,084 alphas). Counts differ from 01_origins by the 117 rows ≥
   1.58 simulated since 09-08 16:39 (round-1 warm-up and the measured day so far).
8. Nothing here says WHY STATISTICAL books carry σ ≈ 0.020 or why the short-volume leg loses Sharpe
   off STATISTICAL; both are listed with candidate mechanisms and no experiment. Any sentence in a
   later file that states either as a mechanism without naming its experiment is a rationalisation.
