# harness5 — round 3 · is the correlation wall field-reuse or PnL resemblance? (2026-09-09 19:40 local)

Khoa's hypothesis: the high correlation is (a) reusing fields that are already in submitted alphas +
(b) a PnL curve that resembles one of the submitted alphas. Tested on the 64 forge alphas that carry a
numeric correlation reading (`state/forge/corr.jsonl`, pulled 19:38). Nothing simulated; arithmetic on
the journal + the USA/d1 field catalogue.

## 1. SELF and PROD are two different checks — the blocker is PROD, not SELF
| alpha | mechanism | PROD | SELF | which line blocks |
|---|---|---|---|---|
| Vk67oQ5V (the new-mechanism pass) | insider × IV-spread × profitability | **0.732** | **0.523** | PROD (0.71); SELF is under 0.70 |

SELF_CORRELATION (SUBMISSION_GATES.md) = correlation to the **user's own previous submissions** (our 2:
vRk095rv, kqVbg1xP). PROD_CORRELATION = correlation to the **platform production book** (every user's
live alphas). Vk67oQ5V reads SELF 0.52 — it does NOT resemble our own submitted alphas above the line.
It is held by PROD 0.73, a book we do not hold the curves for.
Across all 64: PROD > SELF on **57**, median PROD 0.611 vs SELF 0.329. PROD sits ~0.28 above SELF
because the production book is thousands of alphas and ours is two.

## 2. Field reuse (a) is measured NOT to set the number
Same field set, wide PROD range: of the 25 readings with PROD > 0.7, all 25 use option8 (the IV-spread
leg) and 24 use us_short_sale; of the 31 readings with PROD < 0.6, 29 use option8 and 31 use us_short_sale.
**The identical fields (option8 IV-spread + us_short_sale) produce PROD from 0.47 to 0.95.** Binning by the
most-crowded signal field's platform alphaCount gives PROD p50 0.650 at [5k,20k) vs 0.588 at [20k+): no
monotone crowding signal. So reusing a field that appears in the submitted book does not, by itself,
raise PROD; two alphas on the same fields differ in PROD by up to 0.48. MECHANISM: what differs within a
fixed field set is the settings (decay / neutralisation / window) — i.e. the **PnL curve**. This supports
(b) over (a), but it is POST-HOC and confounded (settings and curve move together; not an experiment).

## 3. PnL resemblance (b) is confirmed — for SELF, the check we can see
The two highest SELF readings (0.946, 0.910) are options_x_short alphas — the same mechanism as our
submitted kqVbg1xP. SELF tracks resemblance to our own book exactly as (b) says, and memory
[[pnl-distance-predicts-self-corr]] predicts SELF from the daily-PnL pearson **before** a POST
(0.0662 + 0.9675·pearson, ±0.022). So (b) is right, and we can pre-screen SELF locally and never waste a
POST on a self-corr fail.

## 3a. Khoa's correction (19:50): the hypothesis was about SELF — tested, and (a) fails there too
Field/leg overlap with the two submitted alphas (vRk095rv legs short×profitability×accruals;
kqVbg1xP legs IV-spread×short), against the SELF reading of the other 62 measured alphas:
| overlap with a submitted alpha | n | SELF p50 | SELF range | ≥ 0.70 |
|---|---|---|---|---|
| identical signal-field set (Jaccard 1.0) | 22 | 0.295 | 0.15 – 0.91 | 3 |
| Jaccard 0.7 – 0.8 | 17 | 0.27 | 0.15 – 0.36 | 0 |
| Jaccard 0.3 | 13 | 0.616 | 0.25 – 0.95 | 3 |
| **no shared signal field at all (Jaccard 0.0)** | 1 | **0.852** | | 1 |
| 2 shared legs | 60 | 0.341 | 0.15 – 0.95 | 7 |
| 1 shared leg (Vk67oQ5V) | 1 | 0.523 | | 0 |
**Reusing the submitted alphas' fields does not raise SELF.** Alphas built from the *identical* field
set read SELF 0.15 – 0.91 (p50 0.295, 19 of 22 under the line); the one alpha sharing *no* field with
either submission reads the second-highest SELF on file, 0.852 — it is the same economic signal built
from the other field variants (implied_volatility_*_60 instead of _30, reported_short_sale_* instead of
executed_short_*). So SELF follows the **book the construction produces**, not the field ids in it,
exactly as (b) says and against (a).
CONFOUND, stated before the conclusion: 60 of these 62 readings are one mechanism (options_x_short), so
this measures variation WITHIN a mechanism. Whether field reuse matters ACROSS genuinely different
mechanisms is NOT tested here — there are 2 such points.

## 3b. The 20-row probe (19:51–19:55): PROD on the new mechanism is set by NEUTRALISATION
Correlation read on 20 triple rows spanning the settings grid, no simulations spent. 6 returned inside
the probe's wait (14 were still computing):
| neut | decay | composite | Sharpe | PROD | SELF |
|---|---|---|---|---|---|
| STATISTICAL | 4 | insider triple | 1.75 | **0.537** | 0.35 |
| STATISTICAL | 4 | insider triple | 1.69 | **0.544** | 0.37 |
| STATISTICAL | 8 | insider triple | 1.56 | **0.553** | 0.28 |
| SUBINDUSTRY | 4 | sentiment triple | 1.56 | 0.649 | 0.63 |
| SUBINDUSTRY | 4 | sentiment triple | 1.52 | 0.664 | — |
| SUBINDUSTRY | 8 | insider triple | 1.64 | 0.714 | 0.65 |
| SUBINDUSTRY | 8 | insider triple (Vk67oQ5V) | 1.67 | 0.732 | 0.52 |
**One mechanism, one field set: PROD 0.54 at STATISTICAL and 0.71–0.73 at SUBINDUSTRY.** This is the
controlled version of §2 — the fields are held fixed and the neutralisation alone moves PROD by ~0.19.

## 3c. …and the same setting that clears PROD is the one that fails fitness
The triples' 469 rows by neutralisation × decay:
| neut | decay | n | Sharpe p50 / max | ≥ 1.58 | fitness p50 / max | fit ≥ 1 | ladder PASS | sub PASS | all-binding |
|---|---|---|---|---|---|---|---|---|---|
| STATISTICAL | 4 | 114 | 1.04 / 1.75 | 2 | 0.34 / 0.89 | **0** | 4 | 44 | 0 |
| STATISTICAL | 8 | 115 | 1.10 / 1.56 | 0 | 0.42 / 0.74 | **0** | 3 | 49 | 0 |
| SUBINDUSTRY | 4 | 120 | 0.84 / 1.57 | 0 | 0.37 / 0.86 | 0 | 3 | 50 | 0 |
| SUBINDUSTRY | 8 | 120 | 0.95 / 1.67 | 3 | 0.45 / **1.03** | 1 | 8 | 60 | **1** |
The closest STATISTICAL row is RRV7e8Qo: Sharpe 1.69, turnover 0.121 (already under the 0.125 floor, so
turnover is not a lever), returns 3.50 %, fitness 0.89, fails LOW_FITNESS only, **PROD 0.544**. fitness 1.0
at that Sharpe and the floor needs returns ≥ 0.125 / 1.69² = 4.38 % — i.e. book volatility +25 %, with
nothing else changed. That is the whole remaining gap between this mechanism and a submission.

## 3e. The whole library, ranked by "how far from a submission" (20:05)
USA/d1 rows failing **only** LOW_FITNESS with fitness ≥ 0.80: **53**. Of those, **52 belong to the two
mechanisms already submitted** (options_x_short 26, usa_short_x_profitability_x_accruals 26 — both
HARVESTED, so a pass there is worth nothing). **One** row belongs to a mechanism that has never been
submitted:
| alpha | mechanism | Sharpe | turnover | returns | returns needed | gap | PROD | SELF |
|---|---|---|---|---|---|---|---|---|
| **RRV7e8Qo** | insider × IV-spread × profitability, STATISTICAL decay 4 | 1.69 | 0.121 (under the 0.125 floor) | 3.50 % | 4.38 % | **+25 %** | **0.544** | 0.365 |
This is the single most valuable row in the system: every binding check passes except fitness, both
correlation lines are clear with margin, the mechanism key is new, and its cell (Insiders) is open
(2 of 3). It confirms and updates diagnosis_fitness.md §7's "any fitness lever on the current library
adds 0 submissions" — that was true when it was written; there is now exactly one exception, and it is
the round-1 supply's payoff.

## 3d. Applied 19:58: INDUSTRY added to the three triples' neutralisation grid
EX-ANTE reasoning, written before the rows exist, now SIZED from the journal (20:08):
| | σ (=|returns|/Sharpe) p50 | PROD p50 | PROD range | PROD < 0.71 |
|---|---|---|---|---|
| insider triple, STATISTICAL | 0.0201 (n 32) | 0.544 (n 3) | 0.537–0.553 | 3/3 |
| insider triple, SUBINDUSTRY | 0.0288 (n 18), **+43 %** | 0.723 (n 2) | 0.714–0.732 | **0/2** |
| options×short, STATISTICAL | 0.0205 (n 316) | 0.565 (n 20) | 0.474–0.946 | 13/20 |
| options×short, **INDUSTRY** | 0.0306 (n 212), **+49 %** | **0.650** (n 17) | 0.532–0.809 | **10/17** |
| options×short, SUBINDUSTRY | 0.0293 (n 228) | 0.610 (n 24) | 0.507–0.826 | 14/24 |
So INDUSTRY carries SUBINDUSTRY's book volatility (+43–49 % over STATISTICAL, far more than the +25 %
RRV7e8Qo needs) while its PROD reads under the line on 10 of 17 measured rows, against 0 of 2 for
SUBINDUSTRY on this mechanism. TRANSFER ASSUMPTION, stated: the PROD-by-neutralisation numbers are
measured on options×short, a different mechanism; whether the ordering transfers to the triple is the
experiment. Sharpe cost: diagnosis_fitness.md §5 measures leaving STATISTICAL as free for IV-spread
composites and −0.4 for short-volume ones; the triple is IV-spread, and its SUBINDUSTRY arm already
produced Sharpe 1.67 with fitness 1.03, so the Sharpe side is evidenced, not assumed. The three yaml files went from
`[STATISTICAL, SUBINDUSTRY]` to `[STATISTICAL, SUBINDUSTRY, INDUSTRY]` (166 tests green, shipped to the
VPS 19:59); this is a settings-grid extension inside an existing composite, the grid every other
composite in the library already uses, not a new mechanism. REFUTED if INDUSTRY rows read PROD ≥ 0.71
like SUBINDUSTRY, or fail fitness like STATISTICAL. Read it on the next rounds' rows.

## 3f. First INDUSTRY reading (22:38, n 32) — the σ prediction holds, the Sharpe question is open
| neut | n | Sharpe p50 / max | **σ p50** | fitness p50 / max | fit ≥ 1 | ladder PASS | sub PASS | all-binding |
|---|---|---|---|---|---|---|---|---|
| **INDUSTRY** | 32 | 0.90 / 1.37 | **0.0473** | 0.51 / 0.71 | 0 | 0 | 13 | 0 |
| STATISTICAL | 260 | 1.06 / 1.75 | 0.0207 | 0.37 / 0.89 | 0 | 7 | 108 | 0 |
| SUBINDUSTRY | 278 | 0.88 / 1.67 | 0.0440 | 0.42 / 1.03 | 1 | 11 | 123 | 1 |
CONFIRMED: INDUSTRY carries the book volatility predicted at §3d — σ 0.0473, above SUBINDUSTRY's 0.0440
and +128 % over STATISTICAL, far more than the +25 % RRV7e8Qo needs.
OPEN: no INDUSTRY row has reached the Sharpe bar yet (max 1.37 in 32 draws, against 1.75 in 260
STATISTICAL draws and 1.67 in 278 SUBINDUSTRY draws — the maxima are not comparable at these n).
Fitness follows Sharpe^1.5, so a fitness verdict is a Sharpe verdict and 32 draws cannot give one.
NOT YET MEASURED: no INDUSTRY row carries a correlation reading, so the question the arm exists to
answer — whether INDUSTRY's PROD stays under 0.71 — has no data. Neither of §3d's refutation
conditions has fired. Read again at n ≥ 120.

## 4. The part we cannot see
PROD is against production curves we do not hold. We cannot (i) name which production alpha Vk67oQ5V
resembles, nor (ii) pre-screen PROD before a sim. The PnL-distance predictor works for SELF (our curves)
only. The PROD reading exists only after the sim, ≤ 30 min before a POST (the submitter re-reads it).

## 5. What this says for the plan
- Vk67oQ5V is the first new mechanism over every binding gate; it is blocked by PROD 0.73 on a book we
  can't inspect. The one thing in our control is NOT field reuse (§2) but the mechanism's crowding in
  production — and the three sub-universe triples I promoted at 14:35 ALL carry the option8 IV-spread
  leg, so the user's concern predicts they inherit the same PROD wall even though they fixed
  sub-universe. Vk67oQ5V (one of the three) already reads 0.73. Stated before their day's readings land.
- EX-ANTE-plausible lever, to be MEASURED not asserted: a mechanism built entirely on **uncrowded** legs
  (no option8, no us_short_sale; e.g. the insider field alphaCount 1, or the staged legs on datasets with
  < 100 users) should read lower PROD. §2 warns field identity alone does not guarantee it — so this is
  an experiment, not a prediction: after the measured day, probe PROD on a batch of passers from the
  uncrowded staged mechanisms and compare to the option8 book. This is the round-3 correlation layer
  (03_design R3), now with a concrete first test.
- The 18/21 historical passers reading PROD 0.79–0.85 (01_origins §5.3) are all the option8+short
  mechanism; they are one crowded family, consistent with §2's reading that the family, not the field,
  carries the PROD. SPECULATION until the uncrowded-mechanism probe runs.
