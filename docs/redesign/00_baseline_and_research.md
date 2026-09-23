# Redesign — 00. Measured baseline + research synthesis (2026-08-31)

Every number below was measured on this project's own journals (43,178 rows with alpha+formula)
or quoted from a named source. Labels: MEASURED / SOURCE / NOT ESTABLISHED. Nothing here is a
mechanism unless an experiment is named.

## A. What the current pipeline is, measured

### A1. The funnel (MEASURED, journal, all time)
| segment | rows | screen-pass* | tier3+ | tier4 (submittable) |
|---|---|---|---|---|
| USA/TOP3000 (funnel era) | 13,037 | 31.9% | 2,402 | 176 (mostly one lineage) |
| unlabelled (old funnel) | 20,048 | 29.5% | 4,935 | 78 |
| JPN/TOP1200 (climb era) | 8,655 | **0.64%** | 27 | **0** |
| EUR/TOP2500 (climb era) | 1,438 | 1.67% | 12 | 0 |
*screen = sharpe>1.58 ∧ fitness>1.0 ∧ 0.01<turnover<0.7.

- Screen-passers all time: 10,159. Correlation readings ever obtained: **56**. Tier-4 distinct: 9,
  all one USA lineage from 2026-08-14, already submitted. **Submissions from the climb generator in
  three weeks: 0.**
- Weekly yield (screen-pass per 1,000 sims): wk33 342.7 (old ensemble funnel, USA) → wk34 1.0 →
  wk35 27.5 → wk36 6.8 (random-grammar climb, JPN/EUR).

### A2. The wall is CORRELATION, not the screen (MEASURED)
- prod-corr on the 56 measured: median **0.90**, p10 0.57, under the 0.71 line: 10 (18%).
- self-corr: median 0.90, under 0.70: 11 (20%).
- By family the medians are identical (anl 0.90, fnd 0.90, oth 0.91): variants of one mechanic are
  all crowded together. The outliers that passed (0.42–0.57) were different mechanics, not
  different parameters. (Matches the gold-medal playbook: "windows/weights/neutralization never
  create low correlation; only a different data source or economic logic does.")
- Measurement capacity is the second wall: 60 reads per probe cycle, results EXPIRE server-side
  and a GET restarts the compute (measured 2026-08-29), 900 s waits — 56 readings in total against
  10,159 screen-passers.

### A3. Complexity (MEASURED, with the confound stated)
Screen-pass by operator count (calls+infix, calibrated to the platform's own count):
0–4 ops 0.6% · 5–9 6.0% · 10–14 30% · 15–19 47% · **20–24 68.6%** · 25–29 11% · 30+ ≈0%.
CONFOUND: the 15–24 band is the old funnel's carrier+ensemble family on USA, which passes the
screen and then fails correlation (A2). The 9 real tier-4s sit at 11–23 ops but are ensembles of
SIMPLE legs (each leg ~3–5 ops). Beyond 25 ops the pass rate collapses regardless of era, and the
platform hard-refuses >64 (found 2026-08-30, ~260 wasted POSTs).

### A4. Data families (MEASURED, era-confounded)
anl 57.8% · mdl 47.5% · oth 43.0% · fnd 37.4% screen-pass, versus snt 0.19%, rsk 0.14%, ern 0.0%,
mcr 0.0%, pv 1.4%. Direction agrees with the playbook (fundamental/analyst ≫ technical/sentiment);
magnitude is inflated by the ensemble era.

### A5. Crowding is visible in the catalogue (MEASURED, fetched/rc, 251 datasets with counts)
`fundamental6`: 54,187 users / 173,629 alphas. Dozens of datasets have **users = 1**, e.g.
chart_return_model (248 fields), earningscall_embed (515), finnews_nlp_scores (105),
biasfree_analyst (54), analyst_base_ref (28). Playbook memory: "uncrowded-TYPE dataset + light
carrier + decay≈16 → 2 submittable gems". NOT ESTABLISHED at scale — that is the experiment.

### A6. What works (MEASURED this week)
Infrastructure is now solid: auth chain auto-recovers on one tap, hourly link law (one shared
lock), notifier edge-triggered, ladder honest (0.74→1.05→1.22 after purging self-poison), unit
errors 10.9%→0.02%, 7 moves live, speed ×3.1 (2,692 sims/4h), operator cap, auto-submit wired
with m6 announce, adjudication recorder. The generator is the weak part, not the plumbing.

## B. Research synthesis (SOURCE-labelled)

1. **Complexity predicts out-of-sample decay.** Falck, Rej, Thesmar 2021 (arXiv 2105.01380):
   OOS Sharpe ≈ 0.57 × IS (43% haircut; median discount 0.55). Decay predictors: number of
   operations in the signal; std of IS Sharpe when 10% of stocks are dropped (100 draws);
   Sharpe change when the 0.1% most impactful observations are removed; shorter samples. IS t-stat
   is a WEAK predictor. Publication year alone explains 30% of decay variance.
2. **Community consensus (support.worldquantbrain.com, 166-vote post):** ≤5 operators per alpha;
   fewer knobs, stronger logic; ≤3 datafields; prefer the second-best config; validate across
   sub-universes.
3. **Gold-medal playbook (QuantML-Research/wq-alpha-research, 4 days, zero human):** templates
   like `group_rank(ts_rank(operating_income/equity,126), subindustry)` (3 ops); pass rates by
   data type: fundamental 40% > mixed 12.7% > technical 5.3%; LOW_SHARPE is 90.7% of failures;
   fitness failures are turnover in disguise (decay is the lever); self-corr must be on DAILY PnL
   changes; low correlation needs a different data source, never a parameter change; 201 ≠ live,
   verify status==ACTIVE.
4. **Deflated Sharpe Ratio** (Bailey & López de Prado 2014): with N trials,
   SR₀ = √V[SR]·((1−γ)·Z⁻¹(1−1/N) + γ·Z⁻¹(1−1/(N·e))), γ=0.5772;
   DSR = Z[(SR̂−SR₀)·√(T−1) / √(1−γ̂₃·SR̂+(γ̂₄−1)/4·SR̂²)]. Selecting the max of 300 draws per
   round IS a multiple-testing problem; DSR gives the luck-only ceiling to beat.
5. **AlphaAgent** (arXiv 2502.16789): regularise search with symbolic length + parameter count,
   originality vs an alpha zoo (largest common AST subtree), hypothesis–formula consistency;
   maintained IC ≈0.02 where baselines decayed to ≈0.
6. **AlphaSAGE** (arXiv 2509.25055): GFlowNets sample a DIVERSE set instead of one mode;
   novelty reward R_NOV = 1 − max|IC(α, library)|; MaxLen ≈20 tokens; dedup by AST structure.
7. **AlphaBench** (ICLR 2026): LLMs are reliable generators (validity >80%) but near-random
   zero-shot evaluators — the backtest must be the only judge; population search with ≈20
   candidates per round is the best cost/quality point; vanilla prompts suffice.
8. **Platform facts already in repo:** SUBMISSION_GATES.md (verbatim tests: IS-ladder, weight,
   sub-universe, self-corr, cluster), hypothesis_standard.md (8 hard gates + 7 dims),
   community_alpha_tips.md (84 verified tips), OPERATORS.md (85 ops).

## C. Diagnosis (POST-HOC pattern; the experiments are the redesign)
The climb generator searches a random grammar over random fields with no economic hypothesis, no
notion of novelty against the production book, and no correlation budget; it produces either
screen-fails (JPN/EUR, ~1%) or crowded screen-passers (USA, prod 0.90). Everything upstream of the
generator (auth, speed, ladder, submit) now works. The redesign must change WHAT is generated and
HOW it is judged, not how fast it is simulated.
