# 10 — Frames discovery: which frames beat the others, and is the advantage skill or luck

2026-09-24. Role: senior quant researcher. Input: the signed canonical dataset only
(`frames/canonical/rows_framed.jsonl`, 66,058 rows, 33,007 frame_keys). Nothing was simulated, nothing
touched the VPS, nothing runs live (RULE 1, RULE 2). Scripts and outputs:
`$SCRATCH/frames/quant/`, listed in §8. `$SCRATCH` =
`/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad`.

Labels (RULE 0): **EX-ANTE** = from documentation or definitions before looking at these results;
**POST-HOC** = a regularity measured here, never an explanation; **SPECULATION** = neither.
Wherever a reason for a pattern is not tested by an experiment, it reads **MECHANISM: UNKNOWN**.

---

## 0. The answer on one screen

Khoa's hypothesis: build frames, keep the ones that do better on IS, check across many fields that it
is not luck, store them in a library, then fill them with suitable fields.

1. **Within one cell and one era, frame rankings are reliable across fields. POST-HOC.** In
   USA/d1/TOP3000, forge era: 1,085 frames have ≥ 4 distinct fills. Split each frame's fills in two
   halves at random and score each half; the frame scores agree across halves with
   r = 0.643 (way A) / 0.589 (way B). The permutation null is 0.001, and its 99th percentile is 0.078.
   - The agreement survives halves that share **no field** (0.752 / 0.676, 406 frames).
   - It survives halves drawn on **different days** (0.583 / 0.486, 914 frames).
   - It survives ranking on one set of fields and testing on fields never seen
     (Spearman 0.776 / 0.713).
2. **The gain on unseen fields is large, but only inside the curated field pools. POST-HOC.** Pick
   the top 20% of frames on one half of the fields. On fields they never saw, their LOW_SHARPE pass
   share is 23.1% / 21.8%, against 5.3% for all frames tested the same way (4.4× / 4.1×). The
   early→late test gives a similar gap: 27.3% / 23.5% for the top frames against 5.8% / 5.0%. It
   ranks frames on 09-04..09-11 and scores them on 09-20..09-24 fills that share no field with the
   early ones. This is the historical answer to "tỉ lệ cải thiện tăng bao nhiêu", and every caveat
   in points 3–5 and §2 applies to it.
3. **"Unseen fields" were close substitutes. EX-ANTE, from the catalogue descriptions.**
   - In the median eligible frame, the most varied slot saw only 4 distinct fields.
   - 702 of 1,085 frames have a slot with ≤ 3 fields.
   - In the surviving frames the alternatives are:
     - "shares sold short, regular hours" vs "across all markets";
     - 30-day ATM call IV (option8) vs ATM call IV (option3);
     - twitter sentiment "method 1…18".

   Nothing in the history tests a frame on fields outside the role it was written for.
4. **Most of the reliable variance sits above the frame. POST-HOC.**
   - **Shape level** (the same operators with other windows): shuffling fills among frames of the
     same shape keeps r at 0.606 of the 0.641 observed (way B: 0.551 of 0.589).
   - **Dataset level:** shuffling fills among frames that use the same set of datasets keeps
     0.430 of 0.643 (way B: 0.359 of 0.589).

   So a large part of what looks like a "frame effect" is shape or dataset. Which of the operator
   template, the datasets or the hand-written hypothesis carries it: **MECHANISM: UNKNOWN.**
5. **Replication across eras cannot be tested. POST-HOC count.** The forge era (USA/d1/TOP3000)
   and the layered/climb era (USA/d1/?) share:
   - 0 frame_keys, 0 shape_keys and 0 operator multisets;
   - 1 operator set, which has fewer than 5 fills.

   Forge and resim share 0 at every level above the root operator.
6. **In the layered era the result is weaker, and the productive frames were never re-filled.
   POST-HOC.**
   - Split-half r for sharpe is 0.356 / 0.269. For LOW_SHARPE pass it is −0.027: no reliability.
   - All 712 layered d24 rows sit in frames that were filled **once**.
   - Frames with ≥ 4 fills pass 0.54% of the time, against 18.7% for frames filled once.
7. **Candidates: 77 frames in 34 shapes and 6 families, with 68 of the 77 in 3 families. POST-HOC.**
   - They pass a luck test (Monte Carlo, FDR 5%), random, field-disjoint and day-disjoint splits,
     and a chronological check.
   - Run on 10 permuted copies of the data, the same pipeline passes 0 frames each time.
   - The count depends on the tail model. A Monte Carlo tail passes 82 (way A) or 65 (way B) at
     the first step; a normal approximation passes 2.
   - It is a short list of hypothesis families, not a library of 100 frames.
8. **Not answerable from history (§6):**
   - transfer to fields outside the role pools;
   - transfer to other cells: every other forge cell has 0 LOW_SHARPE passes;
   - d24 and submission-level outcomes: d24 is 37 rows in the whole cell, and correlation is not in
     the data;
   - the causal gain against the current generator.

   Each needs a randomized live arm. §6 gives the questions and the sizes.

**Tóm tắt cho Khoa (tiếng Việt).**
- Trong cùng một ô (USA/d1/TOP3000, thời kỳ forge), khung tốt vẫn tốt khi thay field. Tương quan
  giữa hai nửa field là 0,64, còn ngẫu nhiên chỉ 0,00. Kết quả vẫn giữ khi hai nửa không chung
  field nào, hoặc khác ngày.
- Chọn 20% khung tốt nhất trên một nửa field rồi thử trên field chưa thấy: tỉ lệ qua LOW_SHARPE là
  khoảng 22–23%, so với 5,3%, tức gấp khoảng 4 lần.
- Nhưng các field "mới" chỉ là field gần như đồng nghĩa trong cùng vai trò. Phần lớn độ bền nằm ở
  mức hình dạng khung và bộ dataset, không phải ở con số cụ thể của khung.
- Không có khung nào chung giữa các thời kỳ, nên chưa thể kiểm chứng chéo thời kỳ.
- Dữ liệu cũ chỉ cho khoảng 77 khung, thuộc 6 họ (3 họ chính), chưa phải 100 khung.
- Phần còn lại phải đo bằng vòng live có ngẫu nhiên hoá (§6), chạy trên VPS và chờ Khoa tick.

---

## 1. Data, cells, outcomes, adjustment

**Cells, not pooled (RULE 0.6).** Each cell is `REGION/dN/universe × era`. Frame_keys never cross
eras here, so the rankings are per era.

| cell (era) | rows | frames | frames ≥ 2 fills | ≥ 4 fills | LOW_SHARPE pass | d24 | adjustment factors |
|---|---|---|---|---|---|---|---|
| USA/d1/TOP3000 (forge, 09-04..09-24) | 29,597 | 8,229 | 3,315 | 1,085 | 1,257 (4.25%) | 37 | day, neutralization, decay, truncation |
| USA/d1/TOP3000 (resim, undated) | 11,726 | 10,548 | 62 | 19 | 1,933 (16.5%) | 150 | neutralization, decay, truncation |
| USA/d1/? (layered era = recovered, 08-13..08-18) | 11,953 | 7,994 | 368 | 241 | 1,449 (12.1%) | 712 | day only (settings unrecorded) |
| GLB/d1/MINVOL1M (forge) | 5,698 | 2,902 | 684 | 35 | **0** | 0 | day, neut, decay |
| JPN/d1/TOP1200 (forge) | 1,466 | 511 | 248 | 46 | **0** | 0 | day, neut, decay |
| USA/d0/TOP3000 (forge; limit 2.69) | 1,430 | 497 | 235 | 21 | **0** | 0 | day, neut, decay, trunc |
| JPN/d1/? (recovered) | 1,866 | 1,398 | 140 | 60 | 4 | 0 | day |
| EUR/d1/TOP2500 (forge) | 520 | 399 | 18 | 0 | **0** | 0 | day, neut, decay |
| EUR/d1/? (recovered) | 879 | 859 | 14 | 0 | 11 | 0 | day |

- **USA/d1/? is its own cell.** EX-ANTE, `tools/layered_sim.py` defaults to TOP3000, but these
  rows carry no settings. `tools/recover_harvest.py` says "four settings arms" existed and
  "META IS GONE", so the universe is not known.
- **Other rows were not ranked:**
  - climb_rescored: 127 rows, 124 of them d24, picked (EX-ANTE);
  - the small batch files: 278 rows, all frames filled once.

**Outcomes.** The two outcomes were fixed before ranking; the clip was not.
- `y_ratio = sharpe / LOW_SHARPE limit`, clipped to ±2.5.
  - The clip was added **after** the first ranking run, which gave a within-frame variance of 30.5
    in layered USA. It was added before any robustness test was run.
  - The clip hits 19 layered USA rows, 7 JPN rows and 4 EUR rows, and 0 forge or resim rows.
  - The layered cell holds degenerate rows (sharpe 592.48, and ±11.18 with turnover 1.0).
  - Within a cell the limit is constant, so `y_ratio` ranks the same as sharpe.
- `y_pass = LOW_SHARPE == PASS`.
- d24 is reported as counts only, because it is too sparse to rank on: 37 rows in forge USA.

**Unit inside a frame:** a distinct fill. Rows of the same fill under several settings are
averaged.

**Adjustment, two ways:**
- **Way A:** additive fixed effects for day, neutralization, decay and truncation, fitted jointly
  with a frame effect by backfitting. Each stratum effect is then estimated *within* frames that ran
  in several strata: 53.1% of forge USA frames ran under ≥ 2 settings, and 33.5% on ≥ 2 days.
- **Way B:** subtract the raw mean of the full day × neut × decay × trunc stratum, with no frame
  term.

Way A and B rankings agree (Spearman over frames with ≥ 2 fills): 0.965 in forge USA, 0.917 in resim,
0.823 in layered USA.

---

## 2. Confounds, measured before any conclusion (task item 3)

**2.1 Days differ.**

Day dispersion (χ²/df), two ways:

| rate | forge, all cells | forge USA/d1/TOP3000 |
|---|---|---|
| d24, Pearson χ²/df | 11.91 | 11.73 |
| d24, deviance/df (second way) | 7.66 | 8.53 |
| LOW_SHARPE pass, Pearson χ²/df | 27.75 | 51.06 |
| LOW_SHARPE pass, deviance/df | 26.51 | 44.58 |

- The "~11" in the brief matches d24 under the Pearson statistic.
- Forge USA day pass rates run from 1.8% to 13.0%.
- The layered USA cell has only 5 days, with LOW_SHARPE dispersion 722.
- **Raw day means vs within-frame day effects:**
  - Raw day means of `y_ratio` span 0.367–0.613 (range 0.246).
  - Way-A day effects, estimated *within* frames, span −0.028 to +0.061 (range 0.089).
  - So about 64% of the raw day spread moves with *which frames ran that day*: composition.
  - That is an observation; why the generators ran what they ran on which day is **UNKNOWN**.
  - Whether the platform's IS window moved between 08-13 and 09-24 is not in the data
    (**SPECULATION** that it could matter).

**2.2 Fills were allocated, not drawn at random.**
- A frame's first-fill score predicts how many more fills it got: Spearman 0.159 (way A) and
  0.150 (way B). Within the day of the first fill the median is 0.086, over 11 days.
- By quintile of first score:
  - mean later fills: 0.55, 1.14, 1.52, 1.34, 1.02 (the relation is not monotone);
  - share re-filled: 25%, 32%, 48%, 51%, 45%.
- Re-filled when the first fill passed: 48.9%; when it failed: 39.7%.
- EX-ANTE, `forge/search.py` recipe R13 says "exploit the best GLB composite … (selection effect
  noted)".
- Consequence: a frame's full-sample mean mixes the data that selected it with the data that
  followed. The chronological tests (§4.1 V3, §4.2) use only the later fills as the outcome.

**2.3 Forge frames came from hand-written hypotheses.** Canonical rows carry no hypothesis label, so
two proxies stand in for it: the shape_key, and the set of datasets a fill uses. Split-half r in
forge USA:

| split-half r | observed (A / B) | within-shape null (A / B) | within-dataset-set null (A / B) |
|---|---|---|---|
| y_ratio | 0.643 / 0.589 | 0.606 / 0.551 | 0.430 / 0.359 |
| LOW_SHARPE pass | 0.536 / 0.491 | 0.388 / 0.333 | 0.200 / 0.203 |

- The within-shape null (way A) is computed on the 1,028 frames in shapes that have ≥ 2 eligible
  frames. Against their own observed r of 0.641, p = 0.028 for y_ratio and p ≤ 0.0025 for pass.
- The frame therefore carries information beyond its dataset set (p ≤ 0.005), and a little beyond
  its shape, mostly for the pass outcome.
- The frames themselves are few: 253 shapes and 34 dataset sets cover all 1,085 eligible frames.
- The ~2/3 of reliability reproduced by dataset sets is a statistical statement.
  **MECHANISM: UNKNOWN**, and the hypothesis text, the datasets and the templates cannot be
  separated here.

**2.4 Field pools are small, and most fields belong to one frame.**
- Forge USA has 1,774 fields. 80.3% of them appear in exactly one frame_key.
- A few hub fields appear in thousands: fundamental23 `assets` in 2,687 frames, `income` 2,637,
  `operating_income` 2,283.
- Eligible frames: in the median frame the most-varied slot has 4 distinct fields and the
  least-varied has 3.

**2.5 Settings.** Way-A within-frame settings effects on `y_ratio`, POST-HOC:
- truncation 0.15: +0.111; truncation 0.08: −0.034;
- STATISTICAL: +0.032; INDUSTRY: −0.038; SUBINDUSTRY: −0.008;
- decay 16: −0.124;
- CROWDING, MARKET and SLOW_AND_FAST: −0.15 to −0.50, but on 10–17 rows each.

Both ways adjust for these. Settings recipes and frames are partly collinear (EX-ANTE: `forge/search.py`
R14–R18 changed settings on one composite), so any per-frame settings interaction stays in the frame
score.

**2.6 The eras are selected samples** (from the reconciliation):
- resim: 11,726 framed rows of 69,448 eligible;
- climb_rescored: picked candidates;
- layered USA: universe unknown.

No comparison below pools eras.

---

## 3. Ranking within cell, with empirical-Bayes shrinkage (task item 1)

### The model

Continuous outcome:
- m_f = mean of the frame's fill-level adjusted `y_ratio` over its n_f fills.
- m_f | θ_f ~ N(θ_f, σ_w²/n_f), with σ_w² = pooled within-frame between-fill variance.
- Prior θ_f ~ N(μ, τ²). μ and τ² are fitted by maximum marginal likelihood, and τ² a second way by
  DerSimonian–Laird.
- Posterior = μ + B_f (m_f − μ), where B_f = τ²/(τ² + σ_w²/n_f).

**Which prior.** Fitted on all frames of a cell (mostly frames filled once), the prior does not fit
the frames that have several fills:

| cell | prior | τ² ML / DL | σ_w² | implied split-half r | observed r |
|---|---|---|---|---|---|
| forge USA/d1/TOP3000 | all 8,229 frames | 0.1075 / 0.0815 | 0.0277 | 0.916 | 0.645 |
| forge USA/d1/TOP3000 | 1,085 frames with ≥ 4 fills | **0.0182 / 0.0183** | 0.0321 | **0.614** | 0.645 |
| layered USA/d1/? | all 7,994 frames | 0.319 / 0.257 | 0.105 | 0.932 | 0.355 |
| layered USA/d1/? | 241 frames with ≥ 4 fills | **0.0129 / 0.0122** | 0.107 | **0.353** | 0.355 |

- The mean cross-half covariance, which estimates τ² empirically, is 0.0185 in forge and 0.0132 in
  layered.
- Frames filled once are about 6× (forge) and 25× (layered) more dispersed than frames filled ≥ 4
  times. That is the allocation of §2.2 seen from the other side.
- The eligible-frame prior is used for everything below, with μ = 0.542 in forge USA. A frame filled
  once has no within-frame variance, so it cannot be ranked by this model or tested for luck. It is
  listed only in `q1_top25_per_cell.csv`, under the all-frame prior, and is **not** a candidate.

**Binary outcome (LOW_SHARPE pass), relative-rate shrinkage.**
- O_f ~ Poisson(E_f · RR_f), with RR_f ~ Gamma(a, a) (prior mean 1).
- E_f comes from a main-effects logistic model with no frame term (way A) or from stratum means
  (way B).
- a is fitted by the negative-binomial marginal likelihood: 0.192 (A) / 0.243 (B) in forge USA,
  which means strong heterogeneity.
- Second way: an unadjusted Beta-binomial fitted by ML gives α = 0.072, β = 1.50 (prior mean 4.58%).
  Its rank agreement with the relative-rate posterior is Spearman 0.843 (frames with ≥ 2 fills).
- In resim and layered cells most frames have one row, so the heterogeneity is not identified:
  a → 10⁵–10⁶.
- An earlier way-A version used an additive linear-probability model. It went negative in some
  strata and was dropped.

### Top frames, USA/d1/TOP3000 forge (≥ 4 fills, eligible-frame prior)

Posterior is on `y_ratio`, cell μ = 0.542.

| frame_key | fills | rows | passes | d24 | mean sharpe | raw mean | B | posterior ± sd |
|---|---|---|---|---|---|---|---|---|
| `multiply(group_rank(ts_mean(subtract($1,$2),5),industry),subtract(1,group_rank(ts_mean(divide($3,$4),10),sector)))` | 5 | 10 | 8 | 0 | 1.81 | 1.032 | 0.74 | 0.905 ± 0.069 |
| `multiply(group_rank(ts_mean(subtract($1,$2),5),sector),subtract(1,group_rank(ts_mean(divide($3,$4),5),industry)))` | 4 | 8 | 2 | 0 | 1.42 | 1.016 | 0.69 | 0.871 ± 0.075 |
| `multiply(group_rank(ts_mean(subtract($1,$2),5),industry),subtract(1,group_rank(ts_mean(divide($3,$4),10),subindustry)))` | 5 | 7 | 3 | 0 | 1.61 | 0.984 | 0.74 | 0.869 ± 0.069 |
| `multiply(group_rank(ts_mean(ts_backfill($1,5),5),subindustry),subtract(1,group_rank(ts_mean(divide($2,$3),10),subindustry)))` | 4 | 8 | 5 | 0 | 1.48 | 1.008 | 0.69 | 0.866 ± 0.075 |
| `multiply(group_rank(ts_mean(subtract($1,$2),10),sector),subtract(1,group_rank(ts_mean(divide($3,$4),10),subindustry)))` | 5 | 15 | 7 | 0 | 1.50 | 0.955 | 0.74 | 0.848 ± 0.069 |
| `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),subindustry),0.5),group_rank(ts_mean($1,10),industry),0)` | 7 | 12 | 8 | 0 | 1.62 | 0.923 | 0.80 | 0.847 ± 0.061 |
| `multiply(group_rank(ts_mean(subtract($1,$2),5),industry),subtract(1,group_rank(ts_mean(divide($3,$4),5),industry)))` | 6 | 12 | 5 | 0 | 1.33 | 0.925 | 0.77 | 0.838 ± 0.064 |
| `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),industry),0.5),group_rank(ts_mean($1,3),industry),0)` | 6 | 9 | 6 | 0 | 1.61 | 0.908 | 0.77 | 0.825 ± 0.064 |
| `multiply(group_rank(ts_mean(ts_backfill($1,5),5),subindustry),subtract(1,group_rank(ts_mean(divide($2,$3),5),industry)))` | 4 | 5 | 2 | 0 | 1.44 | 0.947 | 0.69 | 0.823 ± 0.075 |
| `multiply(multiply(group_rank(ts_sum(add($1,0,filter=true),60),sector),group_rank(ts_mean(subtract($2,$3),20),subindustry)),group_rank(ts_rank(divide($4,$5),126),industry))` | 4 | 5 | 1 | 0 | 1.36 | 0.945 | 0.69 | 0.822 ± 0.075 |

### Other cells

Top frames and priors are in `q6_rankings_eligible_prior.json`. What they show, POST-HOC:
- **Layered USA/d1/?** The best multi-fill frames are one-operator frames:
  - `ts_arg_min(divide($1,$2),20)`, posterior 0.189;
  - `ts_arg_max($1,250)`, 0.177;
  - `ts_sum($1,120)`, 0.170.

  All are far below any pass: the cell's multi-fill frames pass 0.54% of the time.
- **GLB/d1/MINVOL1M, JPN/d1/TOP1200, USA/d0/TOP3000, EUR/d1/TOP2500 (forge):** these rank frames on
  sharpe, but **0 rows pass LOW_SHARPE** in any of them. The best USA/d0 frames reach mean sharpe
  1.4–1.5 against a limit of 2.69. A ranking there says which frames are least far from the bar,
  not which frames pass.
- **Resim USA/d1/TOP3000:** 19 frames have ≥ 4 fills, each a large ensemble template. The top one
  has a posterior of 0.597.

---

## 4. Is the advantage real or luck? (task item 2)

### 4.1 Split-half reliability over fields

Each eligible frame's distinct fills are partitioned at random into two halves, 400 times. The score
is the correlation of half-scores across frames. Null N1 permutes fill values across frames 400
times; p ≤ 1/401 whenever the observed r exceeds every permuted r.

| cell | frames | y_ratio r (5–95%) | Spearman–Brown | N1 null q99 | pass r | pass null q99 |
|---|---|---|---|---|---|---|
| forge USA/d1/TOP3000 | 1,085 | **0.643** (0.619–0.670) | 0.783 | 0.078 | **0.536** | 0.069 |
| layered USA/d1/? | 241 | **0.356** (0.292–0.425) | 0.525 | 0.152 | **−0.027** (Spearman 0.149) | 0.313 |
| forge GLB/d1/MINVOL1M | 35 | 0.846 | 0.916 | 0.375 | no passes | — |
| forge JPN/d1/TOP1200 | 46 | 0.741 | 0.851 | 0.309 | no passes | — |
| forge USA/d0/TOP3000 | 21 | 0.364 (p = 0.065) | 0.534 | 0.484 | no passes | — |
| layered JPN/d1/? | 60 | 0.187 (p = 0.105) | 0.315 | 0.305 | — | — |
| resim USA/d1/TOP3000 | 19 | 0.756 | 0.861 | 0.503 | 0.313 (p = 0.135) | 0.556 |

**Split variants** (forge USA; way A / way B = an independent implementation). Each removes one
thing the two halves could share besides the frame.

| variant | frames | y_ratio r | pass r |
|---|---|---|---|
| V1 random, on the frames V2 can split | 406 | 0.788 | 0.609 |
| **V2 field-disjoint**: halves share no field (union-find over fields) | 406 | **0.752 / 0.676** | 0.639 |
| **V4 day-disjoint**: all fills of a day in one half | 914 | **0.583 / 0.486** | 0.360 / 0.359 |
| V5 settings-disjoint (the halves share fills, so this tests settings, not fields) | 2,173 | 0.902 | 0.529 |
| **V3 chronological**: first half of fills vs later half | 1,085 | **0.568** | 0.442 |

- **657 of the 1,085 frames cannot be split field-disjointly.** Every pair of their fills is linked
  through a shared field.
- **V3, regression to the mean:**
  - The slope of the later half on the first half is 0.459.
  - The top 20% by first half kept **54%** of their gap to the cell mean in the later half: 0.843 →
    0.696, against a mean of 0.523.
  - For the pass outcome they kept 42%.
- **Layered USA:**
  - V2 gives 0.349 and V4 gives 0.449.
  - In V3 the top 20% kept 31% of their gap.
  - The pass r is about −0.03 in every variant.

### 4.2 Cross-era replication

The same class is looked for in two eras; each era is adjusted inside its own cell and centred on its
own mean. Classes run from L0 to L5:
- L0: frame_key;
- L1: shape;
- L2: shape with slots and group tokens abstracted;
- L3: operator multiset;
- L4: operator set;
- L5: root operator.

| pair | L0 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|
| forge vs layered (any fills) | 0 | 0 | 0 | 0 | 1 | 4 |
| forge vs resim | 0 | 0 | 0 | 0 | 0 | 3 |
| layered vs resim | 0 | 0 | 0 | 0 | 0 | 9 (8 with ≥ 5 fills: Spearman 0.357, p = 0.21) |

**Across eras there is nothing to replicate.** No structural class is shared with enough fills. The
second way, a direct set intersection in `verify.py`, gives 0 / 0 / 0 frame_keys.

**Within forge**, the only temporal split available is early (09-04..09-11) vs late (09-20..09-24),
across an 8-day gap:
- 1,476 frame_keys ran in both periods.
- On the 643 frames with ≥ 2 fills in each, Spearman is 0.674. At shape level it is 0.844
  (366 shapes).
- **V6** keeps only late fills that share no field with the frame's early fills:

| V6 frames kept | way | frames | Spearman early vs late | late pass, top 20% by early | late pass, all |
|---|---|---|---|---|---|
| ≥ 1 fill each | A, fill level | 614 | **0.796** (perm p ≤ 0.0005) | **27.3%** | 5.8% |
| ≥ 1 fill each | B, row level | 614 | 0.745 | 23.5% | 5.0% |
| ≥ 2 fills each | A | 173 | 0.795 | 31.7% | 7.1% |

### 4.3 Leave-fields-out: rank on some fields, test on unseen ones

Every field (or whole dataset) goes to side A or B at random, over 300 partitions.
- A fill whose fields are all on A trains; a fill whose fields are all on B tests.
- A frame needs ≥ 2 fills on each side to be evaluable.
- Lift = LOW_SHARPE pass share on the test fills of the top 20% frames (ranked by train score),
  divided by the pass share of all evaluable frames.
- The paired null picks a random 20% of the evaluable frames.

| cell, unit | evaluable frames (median) | Spearman train→test | top 20% test pass | all evaluable | lift (5–95%) | random 20% lift |
|---|---|---|---|---|---|---|
| forge USA, field (A) | 268 | **0.776** | **23.1%** | 5.3% | **4.41** (3.44–5.14) | 1.00 (q95 1.67) |
| forge USA, field (B: salted-hash partitions, independent code) | — | 0.713 | 21.8% | 5.3% | 4.12 | — |
| forge USA, field, 21 hub fields exempt | 447 | 0.692 | 9.1% | 1.3% | 6.81 (5.61–7.92) | 0.95 |
| forge USA, **dataset** | 1 (only 144 of 300 partitions have ≥ 10) | 0.645 | 25.2% | 8.9% | 2.98 (1.67–4.16) | 1.00 |
| layered USA, field (A / B) | 165 | 0.291 / 0.259 | 0.8% / 1.0% | 0.5% / 0.6% | 1.54 / 1.71 (q05 = 0) | 0.92 |

- **The dataset-level test covers one role only:** 170 frames were ever evaluable. All sit in the
  sentiment-slot families, where the slot switches between `twitter_sentiment_l2` and
  `news_sentiment_transfer`. That is the only cross-dataset transfer in the history.
- Resim, GLB, JPN and USA/d0 have too few evaluable frames: fewer than 10 in every partition.

### 4.4 What §4 establishes, and what it does not

- **Established, POST-HOC, in forge USA/d1/TOP3000:** frame scores computed on different fields,
  different days, or earlier vs later fills agree far beyond the permutation nulls. Selecting on one
  set of fields picks frames that also pass more often on fields they never saw.
- **Not established:**
  - that the operators, rather than the dataset set or shape, carry the effect (§2.3);
  - that it holds outside the curated role pools (§0 point 3);
  - that it holds in another era (§4.2) or another cell;
  - that it holds for d24 (37 rows).

---

## 5. Candidate frames whose advantage survives (task item 4)

**Criteria** (in `q4_candidates.py`):
- **C0:** ≥ 4 fills.
- **C1:** a luck test. p = P(mean of n fills drawn from all 17,395 fills of the cell ≥ the frame's
  mean), by Monte Carlo with 200k draws per n, kept at Benjamini–Hochberg FDR 5%.
- **C2:** in ≥ 90% of 400 random splits, both halves sit above the cell's fill mean (0.469).
- **C3:** every testable one of the field-disjoint and day-disjoint splits agrees in ≥ 80% of 100
  splits, and at least one of them is testable.
- **C4:** the later half of the fills is above the cell mean.

A first version used "top 10% of eligible frames" as C1. The permutation null passed 71–88 frames
through it, against 99 observed, so it measured nothing and was replaced. That is recorded, not
hidden.

**Results:**
- Funnel: 1,085 eligible → C1 82 → C2 82 → C3 77 → C4 **77 frames, 34 shapes**.
- The same pipeline on 10 permuted datasets passes **0, 0, 0, 0, 0, 0, 0, 0, 0, 0** frames.
- **C1 depends on the tail model.** The pool of fills is left-skewed and bounded above: fill-level
  `y_ratio` has max 1.30 and min −1.11.
  - Monte Carlo on way B values passes 65 frames (40 shapes).
  - A normal approximation passes 2.
  - An independent Monte Carlo re-check reproduces the stored p-values: 5.3e-5 vs 4.5e-5, and
    1.8e-3 vs 1.9e-3.
  - The normal tail overstates the upper-tail p by 5–10×.
  - **The count of 65–82 still assumes fills are exchangeable across frames, which §2.3–2.4
    contradict.** Read the list at family level.
- Leave-fields-out, not calibrated by the null: 44 of the 77 are evaluable in ≥ 10 partitions, and
  all 44 have their test fills above the test mean in ≥ 80% of those partitions.
- **In-sample and therefore biased:** the candidates' own rows pass 274/860 (31.9%) and include
  14 d24 rows. Eligible non-candidates pass 2.65%. Use §4.2 and §4.3, not this, for the size of
  the gain.

**The 77 candidates in 6 families.** A family is the L2 class, with groups and windows abstracted.
Descriptions of the slots are EX-ANTE, from the USA_TOP3000_d1 catalogue; why the families score
higher is **MECHANISM: UNKNOWN**.

| family | frames | shapes | fills | rows | passes (in-sample) | d24 | slot roles (catalogue) |
|---|---|---|---|---|---|---|---|
| `multiply(group_rank(ts_mean(subtract($,$),#),G),subtract(#,group_rank(ts_mean(divide($,$),#),G)))` | 31 | 9 | 209 | 411 | 122 | 14 | $1−$2 = call−put ATM IV (option8/option3) or bullish−bearish pattern similarity (continuation_score); $3/$4 = shares sold short / shares traded (us_short_sale, 2 sources each) |
| `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),#),G),#),group_rank(ts_mean($,#),G),#)` | 22 | 9 | 141 | 216 | 67 | 0 | condition = 60-day call−put IV; $1 = twitter sentiment "method k" |
| same, 30-day IV condition | 15 | 9 | 98 | 158 | 67 | 0 | same roles |
| `multiply(group_rank(ts_mean(ts_backfill($,#),#),G),subtract(#,group_rank(ts_mean(divide($,$),#),G)))` | 5 | 3 | 20 | 37 | 14 | 0 | $1 = RavenPack sentiment (2 fields); $2/$3 = short / traded shares |
| three-leg `multiply(multiply(group_rank(ts_sum(add($,#,filter=true),#),G),…),group_rank(ts_rank(divide($,$),#),G))` | 3 | 3 | 13 | 16 | 2 | 0 | directional signal × call−put IV × operating_income/assets |
| `multiply(group_rank(ts_mean($,#),G),group_rank(ts_mean(subtract($,$),#),G))` | 1 | 1 | 13 | 22 | 2 | 0 | sentiment × call−put IV |

Evidence per frame (all 77): `q4_candidates.csv`. It lists fills, rows, passes, d24, mean, p_luck,
the random-, field- and day-split shares, the later-half mean, the EB posterior and the
leave-fields-out record.
- `eb_post` uses the eligible-frame prior. Across the 77 candidates it runs 0.678–0.905
  (cell μ = 0.542), with posterior sd 0.047–0.075 and P(θ > μ) ≥ 0.998 under the model.
- The model assumes fills are independent given the frame, which §2.4 contradicts.
- The all-frame prior's posterior is kept as `eb_post_allframe_prior`.

- **SPECULATION, flagged as such:** candidates drawn from 3 families will be correlated with each
  other. A library filled from them may hit self-correlation and "one submit kills its whole signal
  family" (memory note on distinct mechanics). Nothing in canonical measures correlation, so this is
  a risk, not a finding.
- No candidate exists in any other cell: every other forge cell has 0 passes, and the layered
  multi-fill frames have no pass reliability.

---

## 6. What the history cannot answer, so the live rounds must (task item 5)

| # | question | why the data cannot answer it |
|---|---|---|
| Q1 | Does a library frame keep its advantage on fields **outside the role it was written for**, i.e. the "field library → frame library" step? | Fills were near-synonyms from hand-picked pools: median 4 fields in the most-varied slot. The only cross-dataset evidence is twitter ↔ news sentiment (§4.3). |
| Q2 | Is it the **operators**, the dataset set, or the hypothesis? | Frames, shapes, dataset sets and hypotheses are nested. The dataset-set null reproduces about 2/3 of the reliability (§2.3). No frame was run on another family's fields. |
| Q3 | Does a frame replicate **across eras or cells**? | 0 shared frames at L0–L3 between eras (§4.2). Every other forge cell has 0 passes. |
| Q4 | How much does a frame library raise **d24 / submittable yield**, not just LOW_SHARPE? | d24 is 37 rows in forge USA, 14 of them in the candidates, in-sample. Prod/self correlation is not in canonical. |
| Q5 | The **causal** gain against the current generator | Fills were allocated adaptively (§2.2), and there was never a randomized comparison arm. |
| Q6 | Does the advantage **decay** as a frame is used (saturation, family kill after a submit)? | Frames have ≤ 24 fills and no submission outcomes. |
| Q7 | Do frames filled **once** (all 712 layered d24 rows) have robust structures? | They were never re-filled, so there is no within-frame variance. |
| Q8 | Do the windows and group tokens inside a shape matter? | The frame-within-shape increment is small and seen mainly on pass (0.388 → 0.539). It needs a factorial design, not observational data. |

**The shape of a live test** is given for sizing only. It is RULE 2 material: nothing ships and
nothing runs until Khoa ticks it, and it runs on the VPS (RULE 1).
- **Arms, randomized within the same day and the same settings:**
  - (a) candidate frames × unseen fields from their own role pools;
  - (b) candidate frames × fields of the same slot kind from **other** datasets (Q1);
  - (c) eligible non-candidate frames × the same fields as (b) (Q2);
  - (d) the current generator (Q5).
- **Size**, derived from the POST-HOC measurements above:
  - The historical base is 5.3% (evaluable test fills); the historical top-20% rate is 21.8–23.1%.
  - Telling 5% from 15% (half the historical lift) at α = 0.05 and power 0.8 needs about 140 fills
    per arm if fills were independent.
  - Fills cluster by frame. The pass ICC is about 0.32 (from split-half r = 0.536 at a mean half
    size of 2.5 fills, via Spearman–Brown). With 5 fills per frame the design effect is about 2.3,
    so **about 320 fills per arm, in ≥ 60 frames**.
  - That is about 4 multisim batches of 90 per arm.
- The day dispersion (χ²/df 51 on LOW_SHARPE) means every arm must run on the same days. A
  comparison across days has no verdict.

---

## 7. Every headline number, two ways

Way 1 is the `q*.py` code on the pandas cache with way-A adjustment. Way 2 is `verify.py`: json read,
plain dicts, way-B adjustment, its own random streams, hash partitions and p-value method.

| number | way 1 | way 2 |
|---|---|---|
| forge USA rows / frames / passes / d24 | 29,597 / 8,229 / 1,257 / 37 | identical |
| layered USA rows / frames / passes / d24 | 11,953 / 7,994 / 1,449 / 712 | identical |
| eligible frames (≥ 4 fills), forge / layered | 1,085 / 241 | 1,085 / 241 |
| day dispersion d24, forge all cells | 11.91 (Pearson) | 11.91 (recount); 7.66 (deviance/df) |
| day dispersion LOW_SHARPE, forge USA | 51.06 | 51.06 (recount); 44.58 (deviance/df) |
| split-half r, forge y_ratio / pass | 0.643 / 0.536 | 0.589 / 0.491 |
| split-half r, layered y_ratio / pass | 0.356 / −0.027 | 0.269 / −0.027 |
| permutation null, forge y_ratio | 0.001 | 0.0005 |
| field-disjoint split r, forge | 0.752 | 0.676 |
| day-disjoint split r, forge y_ratio / pass | 0.583 / 0.360 | 0.486 / 0.359 |
| within-shape null r, y_ratio / pass | 0.606 / 0.388 | 0.551 / 0.333 (the shape-level split-half itself: 0.797 over 196 shapes) |
| within-dataset-set null r, y_ratio / pass | 0.430 / 0.200 | 0.359 / 0.203 |
| leave-fields-out Spearman, forge | 0.776 | 0.713 |
| leave-fields-out top-20% vs evaluable pass | 23.1% vs 5.3% (4.41×) | 21.8% vs 5.3% (4.12×) |
| leave-fields-out Spearman, layered | 0.291 | 0.259 |
| early→late, new fields: frames, Spearman | 614, 0.796 | 614, 0.745 |
| early→late, late pass top 20% vs all | 27.3% vs 5.8% | 23.5% vs 5.0% |
| EB τ², eligible forge prior | 0.0182 (ML) | 0.0183 (DerSimonian–Laird); 0.0185 (cross-half covariance) |
| EB-implied vs observed split-half r | 0.614 | 0.645 observed |
| candidates passing C1 | 82 (Monte Carlo, way A) | 65 (Monte Carlo, way B); 2 (normal tail, rejected by the MC re-check) |
| allocation Spearman (first score vs later fills) | 0.159 | 0.150 |
| frame_keys shared across eras | 0 | 0 |

- Where the two ways differ, way B is lower on every reliability number by 0.03–0.10. No sign
  changes, and no conclusion flips.
- The candidate count is the one number whose size depends on the method. §5 says so and reads it
  at family level.

---

## 8. Files

Scripts are in `$SCRATCH/frames/quant/`, and outputs in `out/`.

| script | output | what |
|---|---|---|
| `load.py`, `common.py` | `rows.pkl` | loader; the outcomes, adjustments and EB functions |
| `q1_rank.py` | `q1_rank.json`, `q1_top25_per_cell.csv`, `rank_*.pkl` | per-cell EB ranking under the all-frame prior, both adjustments, binary shrinkage |
| `q6_tables.py` | `q6_rankings_eligible_prior.json`, `q6_candidate_families.csv` | ranking under the eligible-frame prior; family table |
| `q2_splithalf.py` | `q2_splithalf.json` | V1, N1, N2, V2, V3 per cell |
| `q2_splithalf_extra.py` | `q2_splithalf_extra.json` | V1s, V2, V4, V5, V6 |
| `q2_lofo.py` | `q2_lofo.json`, `q2_lofo_perframe.pkl` | leave-fields-out, 3 variants |
| `q2_crossera.py` | `q2_crossera.json` | L0–L5 overlap and correlation; forge early vs late |
| `q3_confounds.py` | `q3_confounds.json` | day dispersion, allocation, dataset-set null, pools, settings |
| `q4_candidates.py` | `q4_summary.json`, `q4_candidates.csv`, `q4_all_eligible.pkl` | C0–C4 and the permutation null |
| `q5_calibration.py` | `q5_calibration.json` | EB-implied vs observed reliability |
| `verify.py` | `verify.json` | the second way for §7 |

**Open items carried forward:**
1. Recover the 57,722 resim formulas; this is a reconciliation open item.
2. Hypothesis labels. Forge journal `meta.recipe` exists outside canonical, and would let §2.3
   stratify on the hypothesis instead of its proxies.
3. The §6 live design, to go to Khoa as tick questions.
