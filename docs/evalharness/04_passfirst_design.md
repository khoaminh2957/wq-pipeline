# evalharness — the pass-first branch, one merged design (2026-09-23)

Author role: chief architect of the forge pipeline. This file merges three drafts (quant: what passes;
search: the feedback loop; systems: integration and the meaning router) into one design, after three
audits (data re-derivation, code references, RULE 0). **It is a design. It ships nothing.** No
repository file other than this one was written, nothing was simulated, no `--live` or `--submit` was
passed, and the VPS was only read (`ssh -n -o BatchMode=yes`, two read-only calls: `grep` of `loop.log`
and `journalctl` for the STOP events; then `ls` of the two stop files, `systemctl show`, `tail` of
`loop.log`). Every mechanism below is a PROPOSAL
under RULE 2. None of it runs before Khoa ticks the questions in §8.

**Why this exists (provenance of the document itself).** Khoa's goal amendment, verbatim: "bổ sung
thêm vào goal: giờ sẽ ưu tiến việc tạo ra alpha submittable trước rồi sau đó mới kiểm tra nó có nghĩa
hay ko, nếu nó vô tình có nghĩa và pass thì nộp luôn còn ko thì cân nhắc mức độ có nghĩa của nó mà nộp
(ưu tiên số 1 là tạo ra nhiều alpha có thể nộp được + ko tái sử dụng các cấu trúc các alpha (field +
cách sài hàm giống) đã được nộp)". The ticked decisions it produced are D17–D21, D24 and D28 in
`00_agreements.md`. D26–D32 were ticked while the drafts were being written; none of the three drafts
cites them (code audit A9). This design does.

## 0. Conventions, labels and how the numbers were checked

**Labels.** `EX-ANTE` = derived from documentation, code semantics or arithmetic, not from outcome data.
`POST-HOC` = a regularity in the journal; it explains nothing. `SPECULATION` = neither; labelled so
nobody builds on it. `RECOMMENDATION` = a design choice of mine, not a finding; it ships only if Khoa
ticks it. Where a sentence would say why something happens and no experiment separated the candidates,
it says **MECHANISM: UNKNOWN**.

**Two meanings of "pass", kept apart (code audit A1, RULE 0 audit A10).**
- `D24-pass`: every name in `benchmark.ESTIMAND["binding_checks"]` reads PASS (LOW_SHARPE, LOW_FITNESS,
  LOW_SUB_UNIVERSE_SHARPE, IS_LADDER_SHARPE, CONCENTRATED_WEIGHT, HIGH_TURNOVER, LOW_TURNOVER). This is
  the numerator of D24 and is frozen.
- `harvest-pass`: `score.platform_verdict` reads pass, meaning every check outside `NON_BINDING` is PASS.
  That set also holds LOW_2Y_SHARPE, the regional lines, UNITS and D0_SUBMISSION.
- On today's journal the two select the same 37 ids (both audits). They diverge on any row where UNITS,
  a regional line or a d0 flag binds. D24 would count such a row; harvest stages it `fail` and the
  submitter never sees it. **The feedback loop in §3 therefore learns from `harvest-pass`, and D24 is
  reported as pre-registered.** The daily count of rows that are D24-pass but not harvest-pass is printed
  beside D24.

**Submittable** = harvest-pass, inside the turnover band, DSR and PBO as `harvest` stages them, PROD and
SELF read numerically under the line, not a D18 near-duplicate of an accepted POST, MATCHES_PYRAMID PASS,
and every other `submit.eligible` rule. This is what Khoa's "alpha có thể nộp được" means operationally.

**Data.** The VPS journal snapshot the drafts used (40,292 lines, copied 08:20 UTC), `corr.jsonl`,
`submitted.jsonl`, the climb submit log; scored = latest row per alpha id with status COMPLETE or
WARNING and a check set.

**My own second-way checks (RULE 0 #5).** Every draft number this design carries was reproduced by at
least one audit, or is replaced by the audit's value. Numbers that originate in an audit are cited to it
by item, and where that audit derived them only one way the text says so. The ones below I also
re-derived myself, with code that imports neither the drafts' nor the
auditors' scripts (`$SP/arch/verify.py`, `conc.py`, `mdr.py`, where `$SP` is the session scratchpad
`/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad`):

| quantity | my value | agrees with |
|---|---|---|
| scored; D24-pass | 35,763; 37 | quant, search, both audits |
| USA/d1/TOP3000 rows and passes; other cells | 26,742 and 37; 9,021 rows, 0 passes | quant §2, data audit |
| USA/d1/TOP3000 D24-pass rate before 09-11 / on 09-11 / after (ET creation day) | 35/19,406 = 1.80 · 1/1,080 = 0.93 · 1/6,256 = 0.16 per 1,000 | data audit Y6 |
| accepted forge POSTs | vRk095rv, kqVbg1xP, vRk1J2jd, rK5RGeqa = 4; per 5,000 USA/d1 scored 0.748, per 5,000 all-cell scored 0.559 | data audit S1 |
| typed arm (09-07): rows, Sharpe-bar rows, passes, CONCENTRATED_WEIGHT FAIL | 919, 1, 0, 397 (43.2 %) | quant §7, systems F10, data audit |
| passes with a numeric PROD; PROD < 0.70 at the latest reading; on any reading | 37; 4 (the 4 POSTs); 5 | data audit Q5 |
| fingerprint families among the 37 (Khoa's `StructuralIndex`, creation order); D18 flags among the 33 unposted | 9; 10 | quant §6, search F3 |
| max scored per ET day | 5,048 | search F1 |
| `typed.judge(..., structural=True)` refuses `multiply(foo, bar)` with H3, and `if_else(greater(rank(foo),0.5), foo, 0)` with H3 | yes, called directly | code audit A3 |
| wq-forge restarts itself after a consumed STOP_FORGE | 6 STOP lines in `loop.log`; 5 "Scheduled restart job" lines in the unit journal (09-06 20:02, 09-07 14:18 / 19:18 / 20:34, 09-08 19:00, +07) | code audit A8 (4), data audit Y3 (5) |

The two new measurements this design adds (§2.5, §2.2) are each derived two ways and say so.

---

## 1. RULE 2 gate 1 (PURPOSE) and gate 2 (PROVENANCE)

### 1.1 Purpose, in one sentence that does not name the mechanism

**Raise the number of distinct submittable alphas per ET quota day, none of them a structural repeat of
an accepted submission, from what the pipeline has measured toward Khoa's four.**

What "has measured" means, with the confound first (RULE 0 #6):

- `POST-HOC`, library era, within USA/d1/TOP3000 (the only cell with any pass): 4 accepted POSTs in 26,742
  scored = **0.75 per 5,000**. The all-cell figure (0.56) mixes in 9,021 rows from 11 cells that never
  reached the Sharpe bar, and the loop runs USA/d1 only (FORGE_ARGS verified read-only today). On the
  within-cell figure the goal is about **5.3×** away, not the 8× search stated (data audit S1).
- `POST-HOC`, the same cell after 2026-09-11 (ET): 1 D24-pass in 6,256 scored (gJboG8mv, PROD 0.7516, not
  submittable) and **0 submittable**. The last submittable alpha was created 2026-09-11 01:32 ET
  (rK5RGeqa).
- `POST-HOC`: the budget per quota day is not 5,000. It peaked at 5,048 (09-07); the median whole day on
  the VPS is 3,197; 09-12..09-19 had zero rounds (auth outages; RULE 0 audit S19 kept this after testing
  it against `loop.log`).

### 1.2 Provenance: why now

1. **Operator instruction.** D17 (pass first, judge meaning after), D18 (no-reuse = Khoa's
   `fingerprint.py`, enforced at submit by `forge/novelty.py`), D19 (8/8 → auto, 5–7 → tick, < 5 → no),
   D20 (generator free within the typed grammar, feedback toward passing, hypothesis requirement
   dropped), D21 (replace wholesale), D24 (versions compared on D24-passes per 1,000 scored), D28 (within
   each cell).
2. **The incumbent's yield fell.** `POST-HOC`: within USA/d1/TOP3000 the D24-pass rate went
   1.80 → 0.93 → 0.16 per 1,000 across 09-11 (table in §0). **MECHANISM: UNKNOWN.** Candidates no
   experiment has separated:
   - (a) HARVESTED retiring the passing hypotheses. `EX-ANTE` (the rule blocks a hypothesis pair after a
     POST) with a `POST-HOC` match: the three hypotheses POSTed before 09-11 received 0 rows after it
     (RULE 0 audit Y3).
   - (b) the nine-day auth outage followed by a different hypothesis mix (1,550 rows of new hypotheses;
     RULE 0 audit Y3, one way).
   - (c) something inside usa_insider_x_ivspread_x_profitability, whose own rate also fell; unexplained.
   - (d) platform drift. The LOW_SHARPE 1.58, LOW_FITNESS 1.0 and HIGH_TURNOVER limits are identical on
     every ET day 09-04..09-23 (RULE 0 audit a07, one way), which rules out a change of those limits only; metric
     drift is unmeasured.
3. **The bank is empty.** `POST-HOC`: all 33 unposted D24-passes read PROD ≥ 0.70 at their latest
   reading. 7 of them were read before their hypothesis's own POST or 0.04 h after it; the pairwise PnL
   predictor puts those 7 at 0.73–0.84 against our POSTs, so the defensible split today is **23 PROD
   only, 10 PROD and SELF** (RULE 0 audit A2), not the drafts' 30/3. MECHANISM of the high PROD: UNKNOWN.
4. **Blind generation already failed once.** `POST-HOC`: the typed grammar (`forge/grammar.py`) lost
   **7 of 7** paired rounds on 09-07: 1 Sharpe-bar row in 919 against 32 in 1,050 for the current arm. The
   record's "5 of 5" (`00_agreements.md`, D17 evidence) is stale (code audit B1-Q20, data audit Q9).
   MECHANISM: UNKNOWN (want of economics, want of feedback, or a grammar too narrow; the record says so).
5. **Nothing implements D20 yet.** D21 hands the whole quota to a branch that does not exist. The three
   drafts of 2026-09-23 are the first design; this file merges them.

---

## 2. The grammar and its measured priors

### 2.1 What the pre-simulation type gate actually enforces

D20's text lists H1 (units), H2 (kinds) and H4 (vector/density). The code enforces more:

- `runner.structurally_ok` calls `typed.judge(..., structural=True)`, which also enforces **H3**
  (multiply and if_else take bounded operands; if_else needs a logical condition). `EX-ANTE`, confirmed
  by calling the function on three formulas (§0) and by the code audit (A3).
- The old typed arm did not use that gate at all: `grammar.expand` calls the **full** judge, H1–H6,
  including H5 (sign role) and H6 (orientation) (code audit A3b).

RECOMMENDATION: the new generator is judged by `structurally_ok` only (H1–H4 as the code has them), the
same gate the incumbent passes through. Every production in §2.2 feeds multiply/if_else with a score
(`group_rank`, `rank`, `ts_rank`, `1 − score`), so **H3 never binds on this grammar**: keeping or
dropping H3 changes nothing it generates, and no behaviour changes. The discrepancy between D20's text
and the code is a record item for the owner of `00_agreements.md`, not a tick.

### 2.2 The productions

The skeleton is quant's §7, with every audit correction applied. Frequency in this table measures the
hand library, which authored every row (memory `grep-the-generator-first`); it is evidence about what
the library tried, not about the platform.

```
ALPHA   := CONF2 | CONF3 | GATE
CONF2   := multiply(LEG, LEG)
CONF3   := multiply(multiply(LEG, LEG), LEG)
GATE    := if_else(greater(LEG, 0.5), LEG, 0)
LEG     := SCORE | (1 - SCORE)            orientation: the field's description sign where the label file
                                           has one (sign_source = description), else a fair coin
SCORE   := group_rank(TS, G) | rank(TS) | ts_rank(TS, W_LONG)
G       := sector | industry | subindustry
TS      := ts_mean(SIG, W_SHORT) | ts_rank(SIG, W_LONG) | ts_backfill(SIG, 126)
         | ts_sum(add(SIG, 0, filter=true), W_EVENT) | ts_zscore(SIG, W_LONG) | ts_delta(SIG, W_SHORT) | SIG
         | TIER_U(SIG)                     reached only through the exploration floor (§3.3)
TIER_U  := any other unary time-series operator `forge.typed` classifies (SMOOTH, DISPERSION, CHANGE),
           with a window from W_SHORT or W_LONG
SIG     := FIELD | FIELD_a - FIELD_b | FIELD_a / FIELD_b | (FIELD_a - FIELD_b) / abs(FIELD_c)
           two- and three-field SIG draws its fields from ONE dataset, subject to H1/H2/H4
W_SHORT := 5 | 10 | 20     W_LONG := 126 | 252     W_EVENT := 20 | 60 | 120
SETTINGS: neutralization ∈ {STATISTICAL, INDUSTRY, SUBINDUSTRY}; decay ∈ {4, 8};
          truncation ∈ {0.08, 0.15}; region/universe/delay = the cell being filled (USA/d1/TOP3000)
DEPTH   <= 6, and factory.MAX_OPS as today
```

The two choices in the skeleton that are mine, not quant's, each with its evidence:

- **SIG fields from one dataset.** `POST-HOC`, derived two ways (a regex over the formulas, and a walk of
  `forge.typed.parse` trees against the catalogue's dataset map): every one of the 37 passes has at least
  one within-leg arithmetic on two or more fields, and all **65** such nodes pair fields from **one**
  dataset (option8 call−put IV, us_short_sale short/total volume, fundamental6 ratios); 0 cross
  datasets. 4 hypotheses, all hand-authored, so this is what the library wrote. MECHANISM: UNKNOWN.
- **Orientation.** Quant's grammar takes a leg's orientation from the label sign. Where the label file
  has no description sign, a fair coin decides; that is SPECULATION with one purpose: it records
  `sign_source`, so D19's G5 can later tell a description-signed leg from a coin-signed one (§4.2).
- **Truncation {0.08, 0.15}.** `grammar.TRUNC` is 0.08, so the old grammar cannot reproduce the first
  ACTIVE submission (vRk095rv), which came from recipe R20 (`--neut STATISTICAL --truncation 0.15 --decay 4
  --group sector`; code audit A2). The effect of truncation is `UNMEASURED` (9 matched pairs). Offering
  both levels is SPECULATION with that one reason.

### 2.3 Priors: counts, never chosen numbers

A prior for a production level is the hypothesis-level Beta mean **(1 + H_near) / (2 + H)**, where H is
the number of hypotheses that drew the level and H_near the number with at least one row failing at most
one binding check. `POST-HOC`, library era, USA/d1/TOP3000. The two conventions inside it (Beta(1,1)
pseudo-counts, and "≤ 1 fail" as the success event) are choices, not measurements (RULE 0 audit Q14).
The hypothesis is the unit because rows inside a hypothesis are not independent. The data audit
re-derived H, H_near, H_pass and every Beta mean identically with its own parser (`a7_struct2.py`).

| level | Beta mean | H / H_near / H_pass | what else is known, corrected by the audits |
|---|---|---|---|
| ALPHA: 2-leg / 3-leg / gate | 0.043 / 0.027 / 0.041 | 113/4/2 · 145/3/2 · 47/1/0 (the 2- and 3-leg counts include gate rows) | Inside options_x_short, the only randomised combiner contrast: multiply 19/362 against gate 0/341 grid rows, one-sided Fisher p = 2.6e-6 (data audit Q4; the draft's 19/407 included 45 C11 rows); by formula 15/215 against 0/208, p = 3.0e-5 (RULE 0 audit E). One hypothesis. Hypothesis-level counts cannot separate the combiners (RULE 0 audit Q5) |
| SCORE: group_rank / rank / ts_rank | 0.031 / 0.007 / 0.009 | 252/7/4 · 136/0/0 · 114/0/0 | rank and ts_rank rows are mostly the typed arm: confounded with its field vocabulary |
| TS: ts_mean / ts_rank / ts_backfill / ts_sum-event / ts_zscore / ts_delta / none | 0.034 / 0.156 / 0.025 / 0.158 / 0.011 / 0.024 / 0.017 | 203/6 · 30/4 · 161/3 · 17/2 · 90/0 · 40/0 · 113/1 | a longer ts_mean lost LOW_SHARPE in 6–7 of 6–7 hypotheses (p 0.016/0.031), which does not survive a multiplicity correction over 55 sign tests (data audit Q11) |
| SIG: spread+ratio / ratio / spread / single field | 0.238 / 0.019 / 0.231 / 0.006 | 19/4 · 101/1 · 11/2 · 178/0 | "single field" is mostly the typed arm: confounded |
| G: sector / industry / subindustry | uniform | — | subindustry→sector repaired LOW_SUB_UNIVERSE +19/−7 hypotheses (p 0.029); not significant after multiplicity (data audit Q11) |
| neutralization | uniform | — | **no effect established**: STATISTICAL against the rest, exact Fisher per passing hypothesis p = 0.50, 0.17, 1.00, and 0.046 in the opposite direction (RULE 0 audit A8). Quant's "hypothesis-specific" reason is dropped; the two usa_short passes are one hand recipe, not a grid contrast (code audit A2, data audit Q8) |
| decay 4 / 8 | uniform | — | 19/1,506 against 18/1,306 within the 4 passing hypotheses |
| ts_backfill window | fixed at 126 | 187 pairs | 186 of 187 126→252 pairs keep every check result; metrics move only in the last reported digit (data audit Q2) |
| TIER_U operators | none | 0 | never simulated by this desk; drawn only through the floor |

**Exclusions** (levels given zero prior weight; the exploration floor does not reach them either), each
`POST-HOC` with its N:

- `signed_power` as a wrapper: 0 of 300 twins converted, Sharpe fell at both powers (reproduced).
- `vector_neut` against a posted formula: **41 pairs, 1 hypothesis**, all-binding broken **16/0** (data
  audit Q1 corrected the draft's 54/2/0-of-23).
- decay 16: 0 passes in 746 rows (9 hypotheses).
- a negated payoff leg inside a gate (`-group_rank(…)` as the then-branch): 2,557 rows in 4 hypotheses,
  0 Sharpe-bar rows. The draft called this "reverse of a whole composite"; no journal formula contains
  `reverse(` (data audit Q6). Confounded with the gate combiner and those 4 hypotheses.
- depth ≥ 7: 0 passes in 934 rows (949 with the data audit's parser).

### 2.4 The field pool and the cell

- `POST-HOC`: `grammar.Pool` for USA/d1 holds 19,596 directional fields in 187 datasets and 33 domains
  (reproduced). The base draw weight is `1/√(users+1)`, ×0.7 unless dense, ÷ numbered-family size (code
  audit Q13). That weight is the record's C9 ("uncrowded datasets, weighted 1/√users") and stays the base.
- `POST-HOC`: every Sharpe-bar row in the forge era is in USA/d1/TOP3000; option8 and us_short_sale exist
  only in the USA/d1 catalogue (RULE 0 audit E). The other cells' 0 of 9,021 is confounded with the
  libraries they were fed. RECOMMENDATION: the branch fills the cells the incumbent's FORGE_ARGS already
  name (`--order USA/d1,d1 --delays 1`); moving cells is a separate decision, and under D28 a new cell is
  a new comparison.

### 2.5 The concentration failure the grammar inherits

`POST-HOC`, 09-07, same day and categories as the library arms: the typed arm failed
CONCENTRATED_WEIGHT on **43.2 %** of rows against 7.0 % and 8.5 %. Two candidate explanations are now
measured and neither separates it:

- **Coverage:** depends on which coverage source is used. Catalogue coverage gives 44.9 / 43.8 / 41.1 %
  across bands; `field_labels.jsonl` coverage gives 34.0 / 50.5 / 53.3 %, a gradient opposite to "thin
  fields" (data audit Q12).
- **The leg normaliser** (new measurement, derived two ways: my regex, and Khoa's
  `fingerprint.op_multiset`): typed rows whose legs use `group_rank` only fail 43.9 % (166/378); `rank`
  without `group_rank` 40.9 % (36/88); both 42.7 % (187/438). Library rows the same day, all
  `group_rank`, fail 9.1 % (374/4,129). So "use group_rank" is not the difference.

**MECHANISM: UNKNOWN.** The grammar above draws from the same pool the typed arm did, so it may inherit
this. No offline measurement can see CONCENTRATED_WEIGHT; it is the first alarm of the live canary (§7,
stage 5).

---

## 3. The feedback loop

### 3.1 What it learns from: a per-row signal that depends only on the row

The row's reward `y` is computed from the row's own check set and nothing else. This is deliberate:

- Search's reward also set y = 0 for rows in an already-won family, so the same row could earn 1 and
  later 0. That makes the reward non-stationary by construction, and search's "no drift, discounting
  would only discard data" was then false on its own definition (RULE 0 audit A3). A row-only y removes
  that source of drift.
- Search's "the novelty correction keeps the bandit from paying for IV-spread legs" is refuted
  in-sample: 2,032 of 2,990 (68 %) at-bar IV-spread rows are not a fingerprint near-dup of any pass and
  would still pay (RULE 0 audit A6). Novelty belongs in the spending rules (§3.4), not in y.

The candidate signals, with the arithmetic of how fast each can move a posterior (`EX-ANTE` arithmetic on
`POST-HOC` rates):

| y = 1 when | library-era rate, USA/d1 | blind typed rate | events on a 3,197-row day at those rates |
|---|---|---|---|
| Sharpe ≥ 0.8 × the row's own LOW_SHARPE limit | ≈ 157 per 1,000 without the POW rows (data audit S6); 155 per 1,000 within USA/d1/TOP3000, typed and signed_power rows removed (my count, 3,948 / 25,403) | 5.4 per 1,000 (5 / 919) | ≈ 500 / ≈ 17 |
| at most one binding check fails (harvest-pass definition) | 232 / 26,742 = 8.7 per 1,000 | 0 of 919 | ≈ 28 / ≈ 0 |
| harvest-pass | 37 / 26,742 = 1.4 per 1,000 | 0 of 919 | ≈ 4 / ≈ 0 |

Evidence that a dense early signal points toward later passes: `POST-HOC`, in-sample. "Most binding
checks cleared in the first 20 rows" ranked the passing hypotheses first (AUC 1.000 on 74), but 2 of the
4 positives had the pass itself inside the window. With those removed, **2 prospective positives**
remain (AUC 1.000 and 0.986 on 72 units; data audit Q10, RULE 0 audit A7). This supports a dense signal;
it does not prove one. Which signal to use is Q2.

### 3.2 What it updates, and how

- **Structure arms.** One Beta posterior per level of each production in §2.2 (ALPHA, SCORE, G, TS, SIG,
  W, the settings). Start: the §2.3 counts, pseudo-counts capped per Q3.
- **Dataset arms.** One Beta posterior θ_d per dataset. A field's draw weight becomes
  `pool.weight(field) × θ_d`, θ_d drawn once per round. Dataset, not field, is the unit: at 5,000 sims ×
  about 2.3 legs a day gives ≈ 60 observations per dataset against < 1 per field (`EX-ANTE` arithmetic,
  reproduced by the data audit).
- **Update.** α ← α + Σy, β ← β + Σ(1 − y) over the rows that used the level, once per round after
  `harvest`. That is one step per 300 sims, ≈ 11 steps on a median day and ≈ 17 on a full one.
- **Exploration floor.** 20 % of each round's draws ignore the posteriors and use the base weights; that
  share is also the only route to TIER_U. The 20 % is SPECULATION: a posterior learns nothing about a
  level it never draws, and no data sets the share.
- **No discounting, no stationarity claim.** The within-cell pass rate fell 11-fold across 09-11 for
  reasons unknown (§1.2), so "the rate does not drift" is not assumed (search F18/§7 dropped). The
  feedback-off arm of §6 doubles as the drift detector: both arms share the same days, so a fall in the
  off arm is drift, not learning.
- **State.** The loop's state is a pure function of the journal, `corr.jsonl` and the submit logs,
  recomputed each round (the pattern `allocate.pair_states` already uses), so a crash loses nothing and
  no new state file exists. Its sha256 is stamped on every construction as `meta.gen_state` for
  stratification. This settles the search/systems contradiction (RULE 0 audit D.5).
- **The 1/√users preference (C9).** θ_d multiplies the base weight and can cancel C9's preference for
  uncrowded datasets. By how much is UNMEASURED; stage 2 (§7) measures it offline by replaying
  library-era posteriors. If it cancels, that is a conflict with a requirement of record and goes to
  Khoa, whatever Q3 says (RULE 0 audit C7).

### 3.3 Family identity

A family is Khoa's fingerprint family: a new candidate joins the nearest registered family if
`fingerprint.StructuralIndex.is_dup` fires, else it founds one. Assigned at plan time, deterministic
given the journal. `meta.hypothesis = "gen:<family-id>"`, so every rule that keys on `hypothesis`
(quarantine, DSR pools, submit's C16 second-best, `mechanism_key`) sees a stable key.

Known limits, `POST-HOC`: fingerprint and PnL disagree on 126 of 666 pass pairs (91 PnL ≥ 0.70 but not
near-dups, 35 near-dups under 0.70; search F14, reproduced). The standing example is vRk095rv/qMWbdlmv,
similarity 0.733, SELF 0.9668; the two formulas differ only in the short-volume field pair (N = 1,
MECHANISM: UNKNOWN). Family counts under the union of fingerprint and PnL depend on the clustering rule
(6 greedy, 4 by connected components; data audit S8).

### 3.4 Spending rules per family (the allocator's rules, re-keyed)

**The gap (RULE 2 gate 5).** DEAD_SIMS 40 (Khoa, 09-06), LADDER_DEAD (ticked 09-09 14:50), PASSED_BLOCK 40
(ticked 09-09 20:12), NEAR_MISS, HARVESTED, `overlap_blocked` and `harvest.quarantine` are all keyed on the
library's hypothesis or composite. On generated rows they never fire: typed rows form 254 allocator pair
keys, only 3 with ≥ 40 rows (data audit Q7, RULE 0 audit a11); `AL.order` only schedules composite
objects (code audit Y44); quarantine keys would be 755 with a median of 1 row, 20 able to reach
`QUARANTINE_MIN = 4` (RULE 0 audit a17, one way). **Under D21 "only for the new branch" means "everywhere"**
(RULE 0 audit C1), so leaving them keyed as they are is a deletion of four ticked rules. Q4 decides.

RECOMMENDATION (Q4 option a), each rule named with the finding that motivated it:

| rule today | re-keyed as | why |
|---|---|---|
| DEAD_SIMS 40 / DEAD_BEST, LADDER_DEAD | per fingerprint family, same constants | keeps Khoa's ticked stop rules alive. The unit transfer from hypothesis to fingerprint family is untested (RULE 0 audit Q18); stage 2 replays it on the library journal before anything ships |
| PASSED_BLOCK 40 | ≤ 40 further sims per family after its first harvest-pass | keeps the ticked number. POST-HOC reason siblings are worth a few sims: the three within-hypothesis PROD crossings on file were between different formulas (kqVbg1xP 0.54 against siblings 0.79–0.83; vRk1J2jd 0.68 against 0.76–0.82; rK5RGeqa 0.65 against 0.72–0.75; RULE 0 audit A1) |
| HARVESTED | a candidate that is a D18 near-dup of an accepted POST is not simulated (plan time) | HARVESTED blocked a whole pair; this blocks only the structure. **Fail-open at plan time** when the index is incomplete: the reason D18 fails closed is that "a submission slot is one of four in a day" (`forge/novelty.py` docstring); at plan time the stake is quota, and D18 at submit stays fail-closed and unchanged. This is an added rule, not "Khoa's rule moved earlier" (RULE 0 audit S16/C5). Size: 573 rows (1.6 %) of the whole journal were repeats of a POST made before they were created, all 09-04..09-09; in systems' cited window it would have saved 0 (data audit Y1, one way) |
| after a POST, siblings | a family whose 984-day PnL correlation with an accepted POST is ≥ 0.70 gets no further sims | the predictor reproduces platform SELF to ≤ 1e-4 in 7 of 8 cases and 0.0001 in the 8th (search F13, data audit S3). It is a **spend-stop, not a kill**: the family's alphas stay eligible, and submit's own re-read decides (RULE 0 audit C9 — the correlation lines at submit are a reversible filter) |
| quarantine | key (cell, field) | the rule's purpose is a FIELD the platform refuses in a cell (`harvest.quarantine` docstring: fnd90_game_optimism_gma on JPN/d0). EX-ANTE |
| `overlap_blocked` | subsumed by the HARVESTED row above | its stated intent is quota (≈ 15 % of sims on siblings, `allocate.py:4-8`); D18 at submit does not serve it (RULE 0 audit Y13) |

**Dropped from the drafts' spending rules:**
- The PROD-REPAIR arm and K3 (a settings grid on a passing formula until PROD < 0.70; stop at min PROD
  ≥ 0.90). 24 formulas have ≥ 2 settings variants with a PROD reading and **0 of 24 straddle 0.70**; the
  0.195 "range" was a spread of per-neutralization medians, raw ranges reach 0.436, and "consistent with
  every family" was vacuous (RULE 0 audit A1, data audit S5).
- K1's permanent closure of a region: about 90 % of regions would close at 20 draws (search's own
  arithmetic), which can starve a pyramid category (RULE 0 audit C11). The posterior with a floor does
  the same shrinking without a zero.
- K5 "a banked family gets nothing": it left no backup when the pre-POST re-read or D19 holds the alpha
  (RULE 0 audit C10). PASSED_BLOCK governs instead.

### 3.5 The repair queue (near-passers)

A trigger is a row that fails exactly one harvest-pass check (Q5 offers the ≤ 2 variant). Its repair is
the row's **settings grid**: the other neutralization × decay × truncation combinations, ≤ 11 new sims,
each once (simulation is deterministic on the 4 duplicate pairs on file, all from one day 1.1–2.6 h apart;
RULE 0 audit Q7). Repair takes at most 10 % of a round (SPECULATION: a guard against the 1,500-row family
of search F19). Each trigger is coin-flipped into repair or no repair, independently of the §6 arm, so the
queue carries its own control.

What the evidence does and does not say, `POST-HOC`:

- Later settings-siblings of a trigger row passed at 37.8 per 1,000 distinct rows against 0.6 per 1,000
  for other rows (9 passes each; 5 of the 9 counted in both; cross-cell siblings included; data audit S4).
  The 9 are **9 alphas from 6 formulas in 2 hypotheses** (RULE 0 audit A5). Quant's own reading stands:
  "not a transferable repair law".
- "Repair is worth more per sim than explore" is dropped: the two numerators share the same pass
  families, the comparison sets a conditional yield against an unconditional one, and search's cap of
  150 is contradicted by its own marginal yields (RULE 0 audit A4). The coin flip exists because nothing
  on file answers this.
- Supply at library-era rates: ≈ 43 triggers per 5,000; at the post-09-11 rate ≈ 10; blind typed 0 of 919.
  The queue may be empty for days, and that is itself a reading.

### 3.6 After a pass: correlation

- **The probe is unchanged.** It reads `stage == candidate` (harvest-pass, turnover band, DSR ≥ 0.95, PBO
  not False), 60 per round. All 37 passes were read, p50 0.22 h after creation (search F12, reproduced).
  It depends on the DSR pool (Q6): a pool definition that fails every generated alpha leaves the probe
  nothing to read and the submitter nothing to post.
- **SELF right after a POST is not trusted.** 6 of 8 readings taken 0.033–0.042 h after a POST read below
  the exact pairwise correlation with that POST (rK5Rbkla 0.4421 against 0.7979). MECHANISM: UNKNOWN —
  (a) the book includes a POST after a lag, (b) a SELF value computed before the POST was served, (c)
  other (data audit §5). The spend-stop in §3.4 is computed locally and is indifferent to which.
- **"Not yet" is never a verdict.** 429, 200-empty and 401 leave a family's state unchanged, as
  `probe.read` already does (memory `transient-read-as-truth`).

### 3.7 Meaning stays out of the reward

D17 read literally: the generator is steered toward passing only. D19's score is computed after the pass
and gates submission (§4); it does not feed the posteriors. (Search Q11 option c would reintroduce a
meaning preference into generation; it is not offered.)

---

## 4. Integration, the D19 router and the tick queue

### 4.1 Where the generator plugs in

```
forge_loop.sh round (systemd wq-forge, flock, ~22-35 min)
  refresh_cells → runner.plan(--mode gen): cells → [gen.propose: posteriors + families + spending rules]
      → made_ids → quarantine (cell, field) → structurally_ok (H1-H4) → PreSimGate.check → _construction (stamp)
  → LS.run → recover_orphans → harvest (verdict, band, DSR, PBO, meaning rule-part) → probe (bg)
  → submit (meaning route, approvals, AUTO_SUBMIT_STOP, then every existing gate)
```

- **The candidate contract** is systems §1.1: `id`, `formula`, `settings`, `meta` (`hypothesis =
  gen:<family>`, `category`, `field`, `legs` with `orientation` and `sign_source`, `arm`, `generator`,
  `gen_state`, `composite = 1`) and `signature` built with the catalogue's `field_datasets` (else its keys
  never match the active book). `_construction()` is the single stamper.
- **The pre-sim chain must be the composite chain.** `fill_typed` and the ensemble `fill` skip quarantine
  and `structurally_ok` today (code audit Y23). `fill_gen` runs made_ids → quarantine →
  `structurally_ok` → `PreSimGate.check`, the order `_composite_block` uses.
- **Stamping.** D30 (runner argv in the version) is ticked but not yet in `runner.pipeline_version`
  (read today). It must land before the first gen row, or one version id covers two generators.
  `--plan` rows must have the stamp **overwritten**: the arm-driver plans copy the base row's
  `pipeline_version`, so `setdefault` would keep the wrong one (code audit A6).
- **Ordering constraint.** `EX-ANTE`: `submit.py --submit --cap 4` runs every round and has no meaning
  gate (systems F22, code audit Y21). The meaning router must be live before, or in the same deploy as,
  `--mode gen`; otherwise a generated alpha that clears the correlation lines is POSTed with D19 silently
  deleted.
- **The incumbent stays shippable.** `--mode composites`, the library and `--ab` stay in the tree: axis 3's
  fitness function `_ab_arm_is_real` needs `--ab`, and flipping FORGE_ARGS back is the L0 rollback.
- **Arm drivers.** `vps/pow_run.sh`, `c11_run.sh` and `llm_formula_run.sh` stop wq-forge and run the loop
  with `--plan`, submit included (systems F21, code audit Y20). D21 gives the whole quota to the new
  branch, so by D21's own text they do not run; keeping any of them is a D21 amendment for Khoa.

### 4.2 D19: the 8 gates after a pass

The standard was written as a pre-simulation gate on written prose ("it never runs after a sim",
`fetched/hypothesis_standard.md`, the plug-in section). D17 reverses the order on purpose. What that
leaves decidable, `EX-ANTE` from the gate texts:

| gate | decidable from formula + labels + catalogue + ledgers? | note |
|---|---|---|
| G1 typed mechanism | no (needs prose) | form checks only |
| G2 persistent counterparty | no | form checks only |
| G3 grounded citation | no | a citation found after the pass is the failure the gate exists to stop |
| G4 regime validity | half: "every leg alphaCount ≥ 200" is decidable. "a ≥ 750 field as PRIMARY" is not: read as "any field", it trips 37 of 37 passes, including all 4 submissions (systems F14; the catalogue on the Mac is dated 07-15, on the VPS 08-12, the conclusion unchanged). The per-sub-regime sign map is prose | a measured regime reading from the PnL curve would be a different test |
| G5 sign discipline | yes for legs whose orientation came from a description sign: `forge/llm/verify.sign_verdict` | a loop steered toward passing is a sign-fishing search by construction, so this gate discriminates here (SPECULATION: never measured on a gen row) |
| G6 construction | yes: ≥ 2 legs from different domains, a conditioning combiner, bounded operands, no ts_delta on a delta kind | overlaps H2/H3 |
| G7 data existence / PIT | existence yes; point-in-time: SPECULATION that a simulation at delay 1 shows it (RULE 0 audit Y6) | |
| G8 history collision | yes: journal duplicate, D18, the NO_GO / TESTED-* ledgers | |

**The arithmetic consequence, stated before any tick (`EX-ANTE`).** Scored by rule, a generated passer
reaches at most 4 of 8 (5 if G4's leg clause counts as the gate). **It can never reach 8/8, so D19's
automatic branch never fires, and every generated alpha that clears the rule gates reaches Khoa as a
5–7 tick, or is refused as < 5** if undecidable gates count as failed. The routes that would put text
behind G1–G3:

- **Library match.** Inherit the prose of an authored composite the passer is a near-dup of. For
  generated rows this is empty in practice: 1 of 920 typed rows, and 0 of the 5 at ≥ 0.8·bar, is a
  near-dup of any library composite (RULE 0 audit Y8, one way). It is offered, not recommended.
- **Hosted LLM writes G1–G4 after the pass.** Every such text is POST-HOC by construction: a mechanism
  written to explain a result already seen, which RULE 0 forbids stating as a finding and the standard's
  Dim 7 forbids as provenance ("not a field-scan reverse-engineered into a story"). It also conflicts with
  C7 ("No LLM in the running loop"). The form checks pass 94 of 94 hand-written composites (systems F13),
  so an 8/8 from this route would mean "a well-formed story could be written".
- **Khoa scores by hand** = the tick queue.

Which route, and how an undecidable gate counts, is Q7. Where it runs: the rule part in `harvest` for
every candidate (cheap, and benchmark axis 1 can read it); anything costly only for alphas that are
otherwise POSTable (correlation read and under both lines, D18 novel, MATCHES_PYRAMID, PBO not failed,
diversity OK). Output: `state/forge/meaning.jsonl`, one row per (alpha, formula sha) with each gate's
value (true / false / null), its evidence and label, `route`, `scorer`, `scored_at`. D19 amends the
record's C21 ("Unattended submit rule = … Nothing more"); the record should say so.

### 4.3 The tick queue for 5–7

1. `submit.py` meets an otherwise-eligible alpha with `route == tick` and no valid approval: it holds it
   (`held["meaning-awaiting-tick"]`) and appends it to `state/forge/tick_queue.jsonl` with the formula,
   settings, the gate table with evidence and labels, PROD/SELF with `read_at`, cell gain, the D18
   nearest twin and similarity, `pipeline_version`, `queued_at`.
2. One outbox message, "N alphas await a tick" (a new msgcat type).
3. Khoa opens a session; the session reads the queue read-only and asks one `AskUserQuestion` per alpha
   (submit / do not submit / hold). **Only Khoa's own tick** makes an approval, written by a one-purpose
   CLI (`forge/offline/tick.py approve <alpha> --formula-sha <sha>`) recording decision, time and `via`.
   No agent message is Khoa's consent (memory `submit-authority-boundary`).
4. `submit.py` honours an approval only if the alpha id and formula sha match and it has not expired. At
   POST time **every** gate runs again: fresh correlation re-read, novelty against today's POSTs,
   diversity, the 403 budget, the shared 4/day ledger. An approval permits a POST; it waives nothing.
5. A "do not submit" tick is final for that formula sha; an expired approval re-queues the alpha once.

Stated, not hidden: any process with shell access to `/opt/wq` can append to an approvals file, and
nothing here authenticates Khoa. The controls are procedural (one writer CLI, the `via` field, and the
standing rule that agents never run `tick.py approve` without a tick visible in the same session).

**Stop controls.** `forge/submit.py` does not read `state/AUTO_SUBMIT_STOP`; only `tools/auto_submit.py`
does (systems F17, code audit Y16). The file does not exist on the VPS today (read-only `ls`), so wiring
it changes nothing until someone creates it. `STOP_FORGE` is **not** a kill switch under `Restart=always`:
the loop consumes it, exits 0, and systemd restarts it 60 s later (5 automatic restarts in the unit
journal; §0). `Restart=on-failure` is not offered: `forge_loop.sh` also exits 0 when another copy holds
the flock or the climb lock is held, and under `on-failure` either would leave wq-forge down (code audit
A7). `systemctl stop` (+ `disable`) remains the real stop.

### 4.4 What the scorecard does with a generated alpha today

`benchmark.load_standard` maps composite ids only, so a `gen:` alpha reads
`hypothesis_standard_8of8 = None` and is never PROVEN. Axis 2 counts only PROVEN submissions, so **every
generated submission adds 0 to the 4/day floor**, and once D26 lands (rank level 1 counts REFUTED +
UNPROVEN) each one counts against the version (code audit A5). The benchmark must read `meaning.jsonl`
before the first generated submission. `MODULE_TEST_COVERAGE_MIN = 1.0`: every new module
(`forge/gen/*`, `forge/meaning.py`, `forge/offline/tick.py`) needs its own `test_<module>.py` or axis 3
fails outright (code audit A4; systems' "≥ 80 %" was wrong).

---

## 5. RULE 2 gate 5: every existing rule, gate and state field touched

"Keeps working" means the rule still fires on generated rows with its original purpose. A row that
removes or disables something says **DELETION** in capitals, so it cannot become the next silent one.

### 5.1 Pre-simulation

| existing | source | effect of this design |
|---|---|---|
| `factory.MAX_OPS`, journal duplicate `candidate_id`, round budget | `gates.PreSimGate` | unchanged |
| active-book `NoveltyIndex` (exact key `datasets\|families#cell`) | `gates.PreSimGate`, `fetched/rc/active_book.json` | unchanged if `signature` uses the catalogue `field_datasets`. The book file exists on the VPS (dated 09-04) and is absent on the Mac, so a local dry run has an empty index (code audit Y40) |
| structural gate H1, H2, H3, H4-vector, H4-density (Khoa tick 09-07) | `runner.structurally_ok` | unchanged; the grammar never trips H3 (§2.1). Known gap D23 (the typed gate passed 12 formulas the platform flagged for UNITS; left red by Khoa) — which is also why §0 keeps harvest-pass and D24-pass apart |
| full judge H5/H6 | `grammar.expand` (typed arm only, not running under today's FORGE_ARGS) | not used by the new generator; no live gate is removed |
| `forge.standard` admissibility (pre-sim) | `runner.plan`: `ST.admissible(c)` | **DELETION for the new branch, deliberate (D17, D20)**; the standard moves to §4.2 |
| quarantine | `harvest.quarantine` | re-keyed (cell, field) under Q4(a); under Q4(d) it never fires on gen rows (**DELETION**) |
| D18 | `forge/novelty.py` at submit | unchanged at submit (fail-closed). Plan-time use under Q4(a) is fail-open and is an ADDED rule (§3.4) |

### 5.2 Allocation

| existing | effect |
|---|---|
| DEAD_SIMS 40, LADDER_DEAD, PASSED_BLOCK 40, NEAR_MISS, UNTRIED_BLOCK, HARVESTED, cold cells (`forge/allocate`) | keyed on library hypotheses; never fire on gen rows. Re-keyed under Q4(a); **DELETION** of Khoa-ticked rules under Q4(d). NEAR_MISS and UNTRIED_BLOCK are replaced by the posterior and the repair queue under every option; named here as replaced |
| `overlap_blocked` | subsumed by plan-time D18 under Q4(a); **DELETION** otherwise (its purpose is quota, and D18 at submit saves none) |
| cell cap 60 per round, block 20, `--order`, `--delays`, full USA/d1 cells reachable | `fill_gen` charges the same `taken` counter and walks the same ordered cells |
| pyramid refresh every round and after an accepted POST | unchanged; the generator reads `C.targets()` and draws a category-serving first leg as `grammar.compose` does |
| category coverage | the posterior can starve a category a few datasets serve; the floor prevents a zero; stage 2 measures the drawn category mix (RULE 0 audit C11) |
| RULE 2 non-grandfathering | LADDER_DEAD's 58 % saving is an in-sample figure whose live measurement ("sims per pass with vs without", `allocate.py`) is still pending (RULE 0 audit Q11). Re-keying it does not make it proven; it stays an open item |

### 5.3 Post-simulation and correlation

| existing | effect |
|---|---|
| `score.platform_verdict` (every non-NON_BINDING check; WARNING disqualifies) | unchanged; it is the harvest-pass the loop learns from |
| turnover band 2–25 % (C15) | unchanged |
| DSR ≥ 0.95, pool N = rows sharing `harvest.pool_key` (C13) | **the pool definition decides whether DSR passes anything** (Q6). Per family × cell × category (what `pool_key` gives once `hypothesis = gen:<family>`): small N, SR0 near 0, the correction nearly free (typed pools p50 1 member; search F21). Per generator × cell × day: N ≈ 3,000–5,000, SR0 ≈ 1.59–1.61 with the robust IQR sd 0.437 (not 0.52; data audit Y4), so a Sharpe ≈ 2.15 is needed (SR0 + `DSR_MARGIN` 0.54), above all four forge submissions (1.66, 1.85, 1.91, 2.01) |
| PBO/CSCV; "insufficient" (N < 20) does not block | with family pools most are < 20, so **PBO becomes non-binding for the new branch** under Q6(a). Named, not hidden |
| probe: candidates only, 60 per round, the shared 60 req/min bucket | unchanged; depends on Q6 (§3.6). Measured today: 1,012 PROD attempts, 10.6 % numeric, 45.8 % 429 |
| curves for DSR | fetched only for in-band platform passes (code audit S20); the §3.4 spend-stop needs no more than that |

### 5.4 Submit

| existing | effect |
|---|---|
| correlation lines (row limit, else 0.7); re-read if > 30 min old or older than the last accepted POST | unchanged; the binding safety net behind D18 |
| MATCHES_PYRAMID PASS; D18 fail-closed with `register` after each POST; diversity ≤ 2 per dataset set per day; 403 budget; shared 4/day ledger + lock | unchanged. `datasets_of(mechanism_key)` works for `gen:` keys |
| C16 second-best within `hypothesis` | becomes second-best within a fingerprint family |
| C20 order (cell gain, robust score, lower SELF) | unchanged; ticked alphas are ordered with the rest under Q8(a) |
| NEW: meaning route, approvals, `AUTO_SUBMIT_STOP` | §4.2–4.3; each is a tick |

### 5.5 Benchmark, CI, deploy, desk rules

| existing | effect |
|---|---|
| D24 numerator (frozen 7 checks) | unchanged; reported beside the count of D24-pass rows harvest rejects (§0) |
| D28 (D24 within each cell) | the branch is one cell today, so within-cell and pooled coincide; any cell move starts a separate comparison. `compare()` still pools at read time (code audit A9) |
| D30 (argv into the version) | must be implemented before the first gen row (§4.1) |
| axis 1 / axis 2 / D26 | §4.4: blocked until the benchmark reads `meaning.jsonl` |
| axis 3: `--ab`, library present, `MODULE_TEST_COVERAGE_MIN = 1.0`, no module-level import cycle | keep `--ab` and the library; a test file per new module; `meaning` imports nothing from `submit` |
| branch drill (`plan(only=[drill])` in the default mode) | `gen` is a new mode value; the default stays `composites` |
| deploy smoke hard-codes the planner args (systems F19); no D16 first-round trigger (F18) | both must be fixed before stage 5, or a crash in `--mode gen` passes the smoke and is caught only after quota is spent. D16 "before any quota is spent" holds only for a planner crash |
| `deploy.py push` refuses without a publish record | except under `--force-unpublished`, which D32 keeps (code audit Y34) |
| memory `description-first-alpha-workflow`, `hypothesis-quality-standard` | overridden by D17, already recorded as a reversal in `00_agreements.md` |
| memory `always-90-sims` | a round is 300; unaffected |
| C9 (uncrowded datasets, 1/√users) | base weight kept; the θ_d multiplier can cancel it (§3.2); measured in stage 2, conflict goes to Khoa |

---

## 6. The proof plan for RULE 2 gates 3 and 4

### 6.1 What needs proof, and what cannot get it

| mechanism | can gate 3 be met? | how |
|---|---|---|
| M1 the feedback loop (posteriors) against the same grammar with posteriors frozen at the prior | yes, inside the branch | round-level randomisation (§6.2) |
| M2 the repair queue | yes, inside the branch | coin flip per trigger (§3.5) |
| M3 the re-keyed spending rules (Q4) | not live: a stopped family produces no rows to compare | offline replay on the library journal only (stage 2). They re-key rules Khoa already ticked; that is continuity evidence, not a gate-3 proof, and it stays an open item |
| M4 library-count priors against uniform | not separately | both §6.2 arms share the priors; separating them would need a third arm and would cut power (§6.3). Named as unproven |
| the branch against the library (D21) | no concurrent control by D21 | sequential under D24/D28, reported. A stamped incumbent window barely exists (1,188 stamped ids, less than one day; systems F4, reproduced), so any sequential verdict is weak; the unstamped history cannot be used (D14; code audit A11 on search's K6) |

**Whether randomising inside the branch is a "control arm" D21 excluded is Khoa's call.** Quant and search
treated it as inside D21, systems as outside it (code audit C.2, RULE 0 audit D.3). Q1 asks it directly.

### 6.2 The design (Q1 option a)

- **Unit.** A round (300 sims). Each round is assigned feedback-on or feedback-off by a pre-registered
  RNG keyed on the round seed, so the assignment is reproducible. Both arms run the same code, version
  and grammar; the arm is stamped as `meta.arm` (`gen-on`, `gen-off`), repair rows as `gen-repair` with
  their own coin.
- **Why rounds.** Both arms share the same days, so day-level confounds cancel in expectation: auth
  outages and truncated days (1,200–5,048 scored per day), platform drift, incumbent exhaustion, and
  day-level overdispersion (φ = 11.8 on 10 whole VPS days; data audit Y5). Round-level clustering is
  UNMEASURED.
- **Pre-registered estimands** (committed before the first gen row; systems §6.1 with the audits):
  - Primary, gate 3: D24 within USA/d1/TOP3000 (D28), per arm, **with its label: it is not the
    submission count.**
  - Secondary S1: distinct fingerprint families with a D24-pass, per 1,000 scored.
  - Secondary S2: such families never seen before the branch's first day.
  - Gate 4, S3: distinct families that are **submittable** (harvest-pass, read under both correlation
    lines, D18 novel), per 1,000 scored, reported with the probe's coverage.
- **Test.** Exact conditional binomial on the two arms' counts (`benchmark.rate_test_p` semantics), rounds
  as the unit for any variance estimate.
- **Decision rule (RECOMMENDATION; Khoa's "đột phá" is his word to define).** Gate 3 is met when the
  on-arm's D24 rate is at least **2×** the off-arm's with two-sided p < 0.05 at the horizon. Gate 4 is met
  when S3 is also higher in the on-arm and the on-arm has produced at least one submittable family the
  off-arm did not. A D24 gain with no S3 gain is a Goodhart result and fails gate 4, as the deep seeder
  failed it in RULE 2's own history.
- **Alarms, never automatic actions (D21 holds):** see stage 5 in §7.
- **Interference, named.** Families, caps and the plan-time D18 are shared across arms: a family the
  on-arm exhausts is closed to the off-arm too. The direction of the resulting bias is UNKNOWN.

### 6.3 N and power

Days are whole ET quota days with at least one round; the per-day volume is the VPS median 3,197 (and
5,000 for comparison). MDR = smallest rate ratio detected with power 0.8 at two-sided α 0.05, computed two
ways: `benchmark.minimum_detectable_ratio` and my own exact conditional-binomial power (they agree to
within 1 %). The φ column divides exposures by 11.8, a crude upper bound; it overstates the problem for a
within-day design and is printed so nobody reads the Poisson column as the whole truth.

| horizon | off-arm share | base rate assumed for the off arm | expected off-arm events | MDR (Poisson) | MDR (÷ φ) |
|---|---|---|---|---|---|
| 10 days × 3,197 | 0.5 | library-era D24, 1.38 per 1,000 | 22 | **2.07×** | 6.8× |
| 10 days × 3,197 | 0.5 | post-09-11 D24, 0.16 per 1,000 | 2.6 | 5.6× | 39× |
| 10 days × 3,197 | 0.2 | library-era D24 | 8.8 | 2.45× | 9.7× |
| 20 days × 3,197 | 0.5 | library-era D24 | 44 | 1.71× | 4.5× |
| 20 days × 3,197 | 0.5 | post-09-11 D24 | 5.1 | 3.8× | 21× |
| 10 days × 5,000 | 0.5 | library-era D24 | 35 | 1.82× | 5.1× |
| 10 days × 3,197 | 0.5 | ≤ 1-fail rows, 8.7 per 1,000 | 139 | 1.37× | 2.6× |

- **If the off arm produces nothing** (the blind typed arm had 0 passes in 919), the ratio is undefined
  and the test reduces to a count: the on-arm needs **≥ 6 events** at a 50/50 split, or **≥ 17** at 80/20,
  before p ≤ 0.025 (`EX-ANTE`: 0.5^6 = 0.016, 0.8^17 = 0.023). This corrects search's "fewer days would
  do", and drops its sentence that low power is "the right kind of evidence" for "đột phá" (RULE 0 audit
  S17).
- **S3 (gate 4) is far sparser.** The library era made 4 submittable families in 26,742 USA/d1 rows
  (0.15 per 1,000): about 2.4 expected per arm in 10 days at 50/50. Gate 4 will usually need 20 days, and
  a null at 10 days reads INDISTINGUISHABLE, not "no effect".
- **The base rate of the new grammar is UNKNOWN.** Every row above assumes the off arm runs at a
  library-era or post-09-11 rate; the only typed data (0 of 919) says it could be lower.

### 6.4 Confounds (listed before any conclusion; none measured as a cause)

| # | confound | status under round randomisation |
|---|---|---|
| C1 | platform drift (limits, definitions, data refresh) | limits stable 09-04..09-23 (RULE 0 audit a07); shared by both arms |
| C2 | incumbent exhaustion | irrelevant inside the branch; decisive for any sequential branch-vs-library reading |
| C3 | cell mix | one cell; any move is a new comparison (D28) |
| C4 | settings mix | both arms draw the same settings levels at the start; the on-arm learns them away — that is the effect, not a confound |
| C5 | learning within the version | the treatment itself; `meta.gen_state` stratifies it |
| C6 | family clustering / Goodhart | S1–S3 |
| C7 | inheritance from the library | S2 |
| C8 | auth-truncated days | shared by both arms |
| C9 | ERROR / 400 rows are not "scored", so a generator that wastes sims is not penalised; no per-sim ledger exists (`02_funnel_baseline.md` §1) | report ERROR and structure-refused counts per arm beside every rate |
| C10 | other quota spenders | arm drivers do not run under D21 (§4.1) |
| C11 | pipeline fixes during the window | frozen window: no probe, harvest or submit changes inside it unless part of the version |
| C12 | overdispersion | day-level shared; round-level UNMEASURED |
| C13 | interference between arms | §6.2 |

---

## 7. Staged build plan (each stage testable offline; quota is spent only in stage 5, after the ticks)

Every code change ships with a test that **fails on the unmodified file**: copy the file to scratch, run
the test against the original, see it fail, restore, `cmp`. None of these tests exists yet.

| stage | what | owner | offline test that must fail first |
|---|---|---|---|
| 0a | record corrections: "5 of 5" → 7 of 7; D20's H list against the code's H3; D19 amends C21 | owner of `00_agreements.md` | — (text) |
| 0b | D30: argv into `pipeline_version` | runner / release | two argv values give two ids |
| 0c | `--plan` rows: stamp overwritten, not `setdefault` | runner | a plan row carrying a base row's version is re-stamped |
| 0d | smoke runs the production args; D16 first-round watch | release (`tools/deploy.py`) | `test_smoke_uses_production_args`; a fake log with `round exit 1` triggers rollback |
| 0e | benchmark reads `meaning.jsonl` for non-composite hypotheses (axis 1, axis 2, D26) | benchmark | a `gen:` alpha with an 8/8 meaning row is not `None` on axis 1 |
| 1 | pre-registration file: estimands, arms, assignment RNG, horizon, test, decision rule, alarms | architect, Khoa ticks | — committed before any gen row; its hash is quoted in the first report |
| 2 | `forge/gen/`: productions, priors, posterior update, family assignment, spending rules, arm assignment — pure functions, no network | generator owner | contract test (every key of §4.1; `signature.key` equals `signature.signature(...)["key"]`); 10,000 seeded draws: 0 H3 refusals, 0 exact repeats, identical output for the same seed; posterior arithmetic on synthetic rows; y computed from `score.platform_verdict` (a UNITS-warned row that clears the 7 checks gives y = 0) |
| 2r | offline **replays** on the library journal (no quota) | generator owner | (i) DEAD / LADDER_DEAD / PASSED_BLOCK keyed by fingerprint family: rows saved, passes lost (tests RULE 0 audit Q18); (ii) plan-time D18 refusal rate; (iii) userCount distribution of drawn datasets under library-count posteriors against base weights (C9); (iv) drawn category mix (C11); (v) quarantine (cell, field) coverage. Each prints a number that goes to Khoa before stage 5 |
| 3 | `forge/meaning.py`, harvest rule-part, submit routing, `tick_queue.jsonl`, `forge/offline/tick.py`, `AUTO_SUBMIT_STOP` in `forge/submit.py` | submit owner | fake transport: 8 → auto, 5–7 → held without an approval, < 5 → held; an undecidable gate counts as Q7 says; an approval with the wrong formula sha is refused; `AUTO_SUBMIT_STOP` blocks a POST (fails today); every gate re-runs after an approval. **Deployed before or with stage 4** (§4.1 ordering) |
| 4 | `runner --mode gen`, `fill_gen` with the composite pre-sim chain; `meta.arm`, `meta.gen_state` | runner owner | a candidate duplicating a journal id is refused; a structurally refused candidate is counted; arm stamped; then a **local dry run** with the production args (no `--live`, RULE 1) that prints the plan |
| 5 | attended deploy by the release owner; first-round watch; the live window of §6 | release; Khoa watches | alarms, pre-registered, **report only**: (a) round exit RC ∉ {0, 2} or a planner traceback → D16 rollback; (b) structure_refused ≥ 90 % of a round's draws; (c) CONCENTRATED_WEIGHT FAIL ≥ 25 % over the first 600 gen rows (typed blind 43.2 %, library 7–9 %); (d) 0 rows at ≥ 0.8·bar in the first 1,000 gen rows (at the blind typed rate of 5.4 per 1,000 that happens with probability e^−5.4 ≈ 0.005). The thresholds are SPECULATION, fixed before data |
| 6 | read-out at the pre-registered horizon; Khoa ticks keep / revert per mechanism | architect → Khoa | — |

---

## 8. Questions for Khoa to tick

Every question describes a mechanism designed here and not shipped. None has passed gates 3–4. Every
option list includes "off". The drafts' duplicate questions are merged (code audit C.4): DSR pool (search
Q10 + systems Q6 → Q6), D18 before simulating (search Q8 + systems Q5 → Q4), the family / secondary
estimand (quant Q5 + search Q1 + systems Q11 → Q1 and §6.2), the gate-3 proof (quant Q6 + search Q12 +
systems Q9 → Q1), the kill unit (quant Q3 + search Q5 → Q4), the repair trigger (quant Q4 + search Q3/Q4 →
Q5).

**Q1. How is the feedback loop proven under D21 (RULE 2 gate 3), and is randomising inside the new branch allowed?**
- (a) Inside the branch, round by round, 50/50 feedback-on against feedback-off (posteriors frozen at the prior); repair coin-flipped per trigger; read at 10 whole quota days; D24 within USA/d1 is primary, S1/S2/S3 pre-registered, gate 3 at ≥ 2× with p < 0.05, gate 4 on S3. Detects ≥ 2.07× at the library-era rate, ≥ 5.6× at the post-09-11 rate.
- (b) The same at 80/20 (80 % of rounds learn): less quota on the frozen arm, detects ≥ 2.45× / 7.8×, and needs ≥ 17 events if the frozen arm makes none.
- (c) No randomisation: sequential incumbent → branch under D24/D28, after at least 7 stamped whole days of the incumbent (stamping began 2026-09-23 02:30 ET; 1,188 stamped ids at the audit's read); cross-time confounds stay.
- (d) Off: build no feedback loop; the branch runs the grammar with fixed priors (this leaves D20's "feedback loop toward passing" undelivered).

**Q2. What does the loop learn from (the per-row signal y)?**
- (a) Sharpe ≥ 0.8 × the row's own LOW_SHARPE limit: about 17 events a day at the blind typed rate, about 500 at the library rate.
- (b) At most one binding check fails (harvest definition): about 28 a day at the library rate, about 0 at the blind typed rate.
- (c) Harvest-pass only: about 4 a day at the library rate; too sparse to steer within a day.
- (d) Off: no learning (same as Q1 d).

**Q3. What does the grammar start from?**
- (a) The library's hypothesis-level counts (§2.3) with pseudo-counts capped at 10 per level, the §2.3 exclusions, a 20 % exploration floor that also reaches the operators this desk has never simulated (TIER_U).
- (b) Uniform over every level, the same exclusions and floor.
- (c) As (a) but without TIER_U (only operators the library used).
- (d) Off: keep `forge/grammar.py`'s current fixed draws (gate 30 %, 3 legs 30 %, truncation 0.08, full judge H1–H6).

**Q4. Which spending rules does the new branch run, and on what unit? (Today's allocator rules and quarantine never fire on generated rows.)**
- (a) Re-key DEAD_SIMS 40, LADDER_DEAD and PASSED_BLOCK 40 on your fingerprint family; replace HARVESTED/overlap by refusing, before simulation, a D18 near-dup of an accepted POST (fail-open at plan time, D18 at submit unchanged); stop spending on a family whose PnL correlation with an accepted POST is ≥ 0.70 (its alphas stay eligible); quarantine on (cell, field).
- (b) The same without the plan-time D18 refusal (D18 at submit only).
- (c) The same rules keyed on (cell, dataset pair, combiner) instead of the fingerprint family.
- (d) Off: code as it is — on the new branch DEAD, LADDER_DEAD, PASSED_BLOCK, HARVESTED, overlap and quarantine are deleted in effect.

**Q5. Repair queue for near-passers?**
- (a) On: a row failing exactly one check gets its settings grid (≤ 11 sims, each once), ≤ 10 % of a round, half the triggers repaired by coin flip.
- (b) On as (a), with the trigger widened to ≤ 2 fails and Sharpe ≥ 0.9·bar.
- (c) On as (a), plus quant's structural moves (group → sector, neutralisation → INDUSTRY, a shorter ts_mean), none of which survives a multiplicity correction.
- (d) Off.

**Q6. Which trials form the DSR pool for a generated alpha?**
- (a) Its fingerprint family × cell × category (what the code does once `hypothesis = gen:<family>`): small pools, a correction near zero, PBO mostly "insufficient".
- (b) Everything the generator ran in that cell that quota day (N ≈ 3,000–5,000): needs Sharpe ≈ 2.15, above all four past forge submissions.
- (c) Everything the branch has run in that cell (N grows without bound; SR0 ≈ 1.74–1.80 at 30,000–36,000 trials, depending on whose Sharpe spread is used).
- (d) Off: DSR not applied to generated alphas (the probe then reads every in-band platform pass).

**Q7. D19 after the pass: who supplies gates G1–G4, and how does an undecidable gate count?**
- (a) Rules score G5–G8 and G4's leg clause; G1–G3 are undecidable, and any undecidable gate sends the alpha to your tick queue (no generated alpha auto-submits; one failing rule gate → do not submit).
- (b) As (a), plus: a passer that is a near-dup of a hand-written composite inherits that composite's pre-written text and can reach 8/8 (about 1 in 920 generated rows would qualify).
- (c) A hosted LLM writes G1–G4 after the pass, labelled POST-HOC (conflicts with C7 "no LLM in the running loop" and with the standard's description-first rule).
- (d) Off: no router; every eligible alpha is POSTed as today (D19 deleted).

**Q8. How does a 5–7 alpha reach you, and how do you stop submissions?**
- (a) Queue file + one Discord notice + your tick in a Claude session, written by `tick.py` (keyed to alpha and formula sha, valid 72 h, every gate re-run at POST, ordered with the rest by C20); `forge/submit.py` also honours `state/AUTO_SUBMIT_STOP`.
- (b) As (a), but valid 24 h and 8/8 alphas always POST first.
- (c) Queue file only, no notice; `AUTO_SUBMIT_STOP` wired.
- (d) Off: 5–7 is treated as "do not submit", no queue, no new stop file (`systemctl stop` stays the only stop).

---

## 9. Dropped and corrected claims

Every claim the audits did not reproduce, or that stated a mechanism no experiment established, is
listed with what replaces it. "Dropped" means it appears nowhere above; "corrected" means the audit's
value is used above.

### 9.1 From quant.md

| # | draft claim | disposition | source |
|---|---|---|---|
| 1 | vector_neut: 54 pairs, 2 hypotheses, all-binding broken 0/23 | corrected: 41 pairs, 1 hypothesis, 16/0 | data Q1 |
| 2 | ts_backfill 126→252 "changed nothing in 187 of 187" | corrected: 186/187 keep every check; metrics move in the last digit | data Q2 |
| 3 | gate→multiply "same legs", 3,590 pairs, SUB 396/800 | corrected: 1,713 exact-leg pairs (10 hypotheses), SUB 32/108 | data Q3 |
| 4 | multiply 19/407 vs gate 0/341, p 7.8e-6 | corrected: 19/362, p 2.6e-6 | data Q4, RULE 0 Q6 |
| 5 | "exactly one pass per hypothesis read PROD < 0.70" | corrected: at the latest reading only; 5 of 37 on any reading | data Q5, RULE 0 Q8 |
| 6 | "reverse(…) of a whole composite" excluded | corrected: a negated gate payoff leg; no `reverse(` in the journal | data Q6 |
| 7 | typed: 188 keys, 4 ≥ 40, 552 rows | corrected: 254 pair keys, 3 ≥ 40, 716 rows | data Q7, RULE 0 Q13 |
| 8 | settings grid "quasi-randomized"; "usa_short passes only under STATISTICAL" | dropped as a contrast: both passes are recipe R20 | data Q8, code A2 |
| 9 | "the best neutralization is hypothesis-specific" | dropped (no effect established) | RULE 0 A8 |
| 10 | the blind grammar "lost 5 of 5" | corrected: 7 of 7 | data Q9, code Q20 |
| 11 | early signal "ranked the 4 passing hypotheses 1–4, AUC 1.000" | corrected: 2 of 4 positives leak; 2 prospective positives | data Q10, RULE 0 A7 |
| 12 | three pair effects "robust" | corrected: none survives a multiplicity correction | data Q11 |
| 13 | typed concentration "coverage does not explain it"; "30–66 % per operator" | corrected: depends on the coverage source; the operator figure had no script; the normaliser measured here does not separate it | data Q12, §2.5 |
| 14 | "D24's estimand inherits UNITS and D0" | dropped (false); the latent divergence kept in §0 | code A1, RULE 0 A10 |
| 15 | fitness formula "EX-ANTE from SUBMISSION_GATES.md" | corrected: the file has no such formula; the identity holds POST-HOC | code A10 |
| 16 | ladder "PASS 2.38, FAIL 1.59" | corrected: 2.38 only for years 2–5 | code Q6 |
| 17 | "rule of three allows up to 0.06 %" in GLB | dropped: wrong unit (hypotheses, 3/13) | RULE 0 Q2 |
| 18 | "the reported limit is rounded" | dropped: MECHANISM UNKNOWN | RULE 0 Q1 |
| 19 | early stop "the same kind of evidence as LADDER-DEAD" | dropped (appeal to precedent) | RULE 0 Q11 |
| 20 | Q3(a) "saved 20,643 rows" attached to a fingerprint-family unit | corrected: measured on the hypothesis unit; transfer tested in stage 2r | RULE 0 Q18 |
| 21 | "≈ 43 near-passers per 5,000 … a small share" for the new generator | relabelled: library-era; blind typed 0/919 | RULE 0 Q15 |
| 22 | 5 % floor, 5 % cap, 5-day read-out unlabelled; "overturn within one day" | relabelled SPECULATION; replaced by §6.3's computed horizons | RULE 0 Q17, Q19 |
| 23 | "EX-ANTE: the signal is dense" | relabelled POST-HOC | RULE 0 Q10 |
| 24 | "measured by hypotheses, multiply does not beat gate" | corrected: hypothesis counts cannot separate them | RULE 0 Q5 |
| 25 | grammar "subject to H1, H2, H4"; field weight "1/√(users+1)" | corrected: H3 also enforced, the typed arm used H1–H6; the weight has two more factors | code A3, Q13 |

### 9.2 From search.md

| # | draft claim | disposition | source |
|---|---|---|---|
| 26 | "4/day needs about 8×"; "the two routes agree" | corrected: ≈ 5.3× within USA/d1; the chain is a decomposition, not a second way | data S1, RULE 0 S14 |
| 27 | aggressive kill rule 0.98 per 1,000 (3.9×), "lost 5" | corrected: keys mixed; 1.22 (4.9×) on the hypothesis key; mechanism key loses 4 | data S2 |
| 28 | predictor "a lower bound on SELF" (1 of 48 exceeds the prediction) | corrected: the prediction exceeded the platform by 0.002 | data S3 |
| 29 | repair value 40.9 vs 0.5 per 1,000 | corrected: 37.8 vs 0.6 distinct; 9 alphas, 6 formulas, 2 hypotheses | data S4, RULE 0 A5 |
| 30 | PROD range 0.195 → K3 = 0.90; siblings as "extra PROD tickets because PROD varies" | dropped: 0 of 24 settings variants straddle 0.70; PROD-REPAIR and K3 removed | data S5, RULE 0 A1 |
| 31 | library comparator 357 / 166 / 98.6 per 1,000 | corrected: 350 / 157 / 89 without POW | data S6 |
| 32 | POW "29 bases … 9 at power 1.5" | corrected: 31 bases, 8 | data S7 |
| 33 | "6 families under the union" | corrected: 4 by connected components | data S8 |
| 34 | "a region's rate does not drift"; "discounting would only discard data" | dropped (SPECULATION; the reward drifted by its own definition) | data S9, RULE 0 A3 |
| 35 | rounds "every ~27–35 min" | corrected: 22 min also seen | data S10 |
| 36 | "30 PROD only, 3 both" | corrected: 23 and 10 | RULE 0 A2 |
| 37 | "repair is worth more per sim"; cap 150; "forcing 2,500 sims … falls to 1.64" | dropped; replaced by the per-trigger coin flip | RULE 0 A4, S5 |
| 38 | "the novelty correction keeps the bandit from paying for IV legs" | dropped (refuted in-sample, 68 %) | RULE 0 A6 |
| 39 | "PROD is not stationary, because it is other people's book" | dropped; "a banked alpha stays submittable for days" relabelled N = 1 | RULE 0 A9, S11 |
| 40 | "the POST was not yet in the platform's book" | relabelled: MECHANISM UNKNOWN, three candidates | RULE 0 S12, data §5 |
| 41 | "a loop rewarded per pass mines siblings" (ownmultiple, 11 passes) | relabelled: 40 of 50 sims came from PASSED_BLOCK; no pass-rewarded loop has run | RULE 0 S1 |
| 42 | "D18 and SELF retire a whole family" | relabelled: EX-ANTE for D18 near-dups only; data: D18 flags 10 of 33 | RULE 0 S2 |
| 43 | "D18 at plan time adds no rule" | dropped: it is an added rule (§3.4) | RULE 0 S16, C5 |
| 44 | "đột phá, so an effect only these sizes can show is the right evidence"; "fewer days would do" | dropped; §6.3 gives the zero-control arithmetic | RULE 0 S17 |
| 45 | Q14(b) "avoids likely PnL twins" | dropped (SPECULATION; no curves for trigger rows); journal seeding not offered (D14) | RULE 0 S18 |
| 46 | K6 exact test against the unstamped history | dropped: `compare()` cannot run it and D14 forbids it | code A11 |
| 47 | "the curve is already fetched for every platform pass" | corrected: in-band passes only | code S20 |
| 48 | 60 % explore floor unlabelled | dropped with the priority split; §3.2's 20 % floor is labelled SPECULATION | RULE 0 S15 |
| 49 | pwPdngaq / A10VndQR as a typed-key HARVESTED case | corrected: library rows; HARVESTED blocks the whole pair | code S26 |

### 9.3 From systems.md

| # | draft claim | disposition | source |
|---|---|---|---|
| 50 | 93 of 6,866 rows repeat a submitted alpha; plan-time D18 "~1.4 % of simulations" | corrected: 0 were created after their twin's POST, so 0 saved in that window; 573 (1.6 %) over the whole journal, all 09-04..09-09 | data Y1 |
| 51 | new families on "7 distinct days" | corrected: 6 ET days | data Y2 |
| 52 | STOP_FORGE restart "seen twice" | corrected: at least 4 STOP→restart sequences (both audits), 5 automatic restarts in the unit journal (§0) | code A8, data Y3 |
| 53 | DSR "sd 0.52" | corrected: IQR sd 0.437 | data Y4 |
| 54 | φ 11.43; 3,197 per day | corrected: 11.99 on 9 whole local days, 11.80 on 10 whole VPS days; 3,197 holds on the VPS whole days | data Y5 |
| 55 | "0.13 per 1,000 after 09-11 against 1.03" | corrected: within USA/d1/TOP3000 1.80 / 0.93 / 0.16 | data Y6 |
| 56 | "the measured wall is PROD, not the binding checks" | relabelled: the binding checks removed 35,896 of 35,933; the last filter on the passes was PROD in 33 of 33 | RULE 0 Y1 |
| 57 | G7 "yes, by construction" | relabelled SPECULATION for point-in-time | RULE 0 Y6 |
| 58 | "fingerprint misses synonym-field twins" | relabelled: one twin that differs only in the short-volume field pair, N = 1 | RULE 0 Y7 |
| 59 | option A "conflicts: none; reproduces today's behaviour" | corrected: for generated rows it is nearly empty (1 of 920) | RULE 0 Y8 |
| 60 | "meaning effort before the correlation read is spent on alphas PROD kills" | relabelled SPECULATION for the new generator | RULE 0 Y9 |
| 61 | `pair_states` classifies generated families "unchanged"; quarantine "works" | corrected: classification yes, scheduling no; quarantine keys p50 1 | code Y44, RULE 0 Y11, Y12 |
| 62 | `overlap_blocked`: "D18 at submit covers the intent" | dropped: its intent is quota | RULE 0 Y13 |
| 63 | "every forge module has a test (≥ 80 %)" | corrected: the minimum is 1.0 | code A4 |
| 64 | `--plan` stamp with `setdefault` | corrected: must overwrite | code A6 |
| 65 | Q8(b) `Restart=on-failure` | dropped: exit-0 paths would leave wq-forge down | code A7 |
| 66 | Q7 FORGE_ARGS in the version; power on the pooled estimand | dropped as ticks: D30 and D28 decided them | code A9, RULE 0 Y15 |
| 67 | "every producer hands the same dict to the same chain" | corrected: `fill_typed` and the ensemble `fill` skip quarantine and the structure gate | code Y23 |
| 68 | "push refuses without a publish record" | corrected: except `--force-unpublished` (D32) | code Y34 |
| 69 | catalogue and pool figures "today" | corrected: Mac copies dated 07-15 and 09-22; VPS values differ, conclusions unchanged | code Y13, Y14 |
| 70 | C4 "neutralisation moved PROD by ~0.19" | relabelled "PROD differed by"; settings-only spread ≤ 0.151 | RULE 0 Y5 |
| 71 | C1 "not yet checked" | updated: limits identical 09-04..09-23 | RULE 0 Y4 |
| 72 | F23's consequence (axis 1 only) | widened: axis 2 and D26 too (§4.4) | code A5 |

### 9.4 Kept for Khoa, not a claim

systems.md discloses a RULE 1 breach by its author: a 127 MB copy of the journal to `/dev/shm` on the
VPS at about 08:30 UTC, removed about a minute later (`ls` of `/dev/shm` empty, confirmed by the code
audit, Y54). Its effect on the live loop during that minute is UNMEASURED (RULE 0 audit Y16).
