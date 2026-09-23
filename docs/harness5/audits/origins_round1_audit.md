# harness5 — audit of 01_origins.md and round_1.md (Auditor, 2026-09-09 13:40–15:00 local)

Role: hallucination check of two documents written by other agents. Nothing here audits the
auditor's own work. RULE 0 labels apply to every line. Nothing was simulated; the VPS was read over
`ssh -n` / `scp` (pull only), nothing was written there; no file under `forge/hypotheses`,
`forge/composites`, the unit or the VPS was touched.

## Method (so the table can be re-run)
- Sources pulled 2026-09-09 13:39 local: `/opt/wq/state/layered/runs/forge.jsonl` (24,504 lines),
  `state/forge/{scored,corr,submitted}.jsonl`, `state/forge/loop.log`, `state/forge/recover.log`,
  `state/layered/runs/climb.jsonl`, `state/harness13/{sim_ceiling/result.json, sim_ceiling2.log,
  crawl_fields_status.json}`, the unit file and `journalctl -u wq-forge`. Local: `state/harness13/
  gate_runs.jsonl`, `harness/data/*.json`, `harness13/`, `docs/redesign/02_design.md`, `00_baseline`.
- **Snapshot rule.** 01_origins says it read a 19,881-line journal at 09-08 16:39. The journal is
  append-only; the first 19,881 lines reproduce every §1 count exactly (17,484 / 598 / 21 / 3,019 …),
  so that prefix IS the snapshot. `scored.jsonl` was cut at `scored_at ≤ 09-08 16:39 local`
  (epoch 1,788,860,340). round_1's warm-up is the ET-09-08 quota day, complete in the full file.
- **Own pass rule** (not `forge.score`): a binding check = any check whose name is not in the
  NON_BINDING list; FAIL / WARNING / ERROR on a binding check → fail; a non-PASS binding check →
  incomplete; else pass. Cross-check: 0 mismatches against `scored.jsonl` stages on 21,479 alphas.
- **Own bar rule**: the row's `LOW_SHARPE.limit`. **Own day rule**: `dateCreated` → America/New_York
  date, one row per distinct alpha id (last row wins). Scripts: scratchpad `audit/{funnel,
  corr_scored,round1,looplog}.py` (session-local; the rules above are the whole method).

Verdicts: **CONFIRMED** = my number equals the doc's; **WRONG** = differs, correction applied in
place with a dated note; **UNVERIFIABLE** = no source I could read reproduces it. (precision) =
confirmed but the wording was loosened/tightened in place.

## A. 01_origins.md

### Header, summary table, ranked bottlenecks (lines 10–35)
| claim | my derivation | verdict |
|---|---|---|
| 2 / 17,484 = 0.11 per 1,000; 0.22 on 9,079 rows; gap 4–7× | 0.114; 0.220; 0.8/0.22 = 3.6, 0.8/0.11 = 7.3 | CONFIRMED |
| harness v0: 26 batch files, 2,101 planned entries | 26 `harness/data/sim_ready*.json`, 2,101 list entries | CONFIRMED |
| harness v0: iter1 1/90; iter2 60.6 %; iter3 33/90, 27/27 crowded | `iter1_breakthrough.json` "1.1% (1/90)", memory "2 PASS(60.6%)", `iter3_breakthrough.json` "33/90", "27/27 (100%)" | CONFIRMED |
| 3 ACTIVE on 07-23 (gJ9mPgGl, 9q7JLQLe, MPLkl7mk) | iter14_SUBMITTED 2026-07-23T04:01:50; iter17_SUBMITTED2 2026-07-23T08:08; winners.csv MPLkl7mk 2026-07-23 LIVE | CONFIRMED |
| ≈ 1.4 per 1,000 planned entries | 3 / 2,101 = 1.43 | CONFIRMED |
| harness13: 1,120 children accepted 08-12; 2,000 on 08-13; 2 gems / 2,000 = 0.10 %; 0 submissions | `sim_ceiling/result.json` children_accepted 1,120; `sim_ceiling2.log` GEM_YIELD 2/2000; `submitted.jsonl` has only forge rows | CONFIRMED |
| climb: 21,972 distinct alphas with checks; 1,665 ≥ bar; 873 pass (retro rule); 12 quota days | climb.jsonl: 22,371 rows with checks → 21,972 ids; 1,665 ≥ own LOW_SHARPE limit; 873 pass by my rule; 12 ET dates (08-14 … 09-04) | CONFIRMED |
| climb: 56 correlation reads, prod median 0.90, 0 submissions in 3 weeks | quoted from 00_baseline §A1–A2 lines 18–25 (a document, not a journal I re-derived) | CONFIRMED as quote; not re-derived |
| forge: 598 ≥ own bar → 21 pass; 2 ACTIVE; 19 of 21 one mechanism; 18 of 21 over the line; 335 of 337 pairs | 598; 21; ledger http 201 ×2 (vRk095rv, kqVbg1xP); 19 options_x_short; 18 with prod ≥ 0.79; 337 pairs, 2 passing | CONFIRMED |
| 16,886 / 17,484 = 96.6 % | 17,484 − 598 = 16,886; 96.58 % | CONFIRMED |
| 577 / 598 = 96.5 % | 598 − 21 = 577; 96.49 % | CONFIRMED |
| 18 / 21 = 86 %; 19 / 21 = 90 % | 85.7 %; 90.5 % | CONFIRMED |
| 2 of 4 full days ≥ 4,000; auth-dead 355 / 1,070 min; ≈ 3,600 sims not run 09-04/05 | days 4,824 & 5,048 ≥ 4,000, 3,019 & 3,375 not; loop.log "auth dead before round" lines 71 (09-05) / 214 (09-06), 280 of 284 gaps = 5 min → 355 / 1,070; (5,000−3,019)+(5,000−3,375) = 3,606 | CONFIRMED |
| DSR 21/21; weekly rule held qMWbdlmv; §11a 41 of 47 ACTIVE refused at N = 300 | 21 candidates DSR 0.99610–0.9999992; qMWbdlmv = usa_short mechanism, prod 0.53 / self 0.27, never posted; 02_design §11a lines 167–168 "6 pass … 41 fail" of 47 | CONFIRMED |

### §1 funnel (lines 37–128)
| claim | my derivation | verdict |
|---|---|---|
| journal 19,881 lines | prefix reproduces every count | CONFIRMED |
| 18,061 child rows carry an `alpha`; 17,642 checks; 419 without (96/141/89/40/25/20/8) | 18,061 rows carry the `alpha` KEY, of which 414 are `null` (failed POSTs) and 17,647 a real id; 17,642 with checks; 419 without: ORPHAN-UNMATCHED 141, AUTH-FAIL 96, ERROR 89, FAIL 40, CANCELLED 25, POLL-* 20, COMPLETE 4 + GUARD-REFUSED 3 + WARNING 1 = 8 | CONFIRMED (precision: "carry the key", not "an alpha") |
| 158 ids twice → 17,484 distinct | 158 ids appear twice among rows with checks, all with identical dateCreated (83 on ET 09-06, 75 on 09-07; 155 of the pairs = original + orphan-recovered row); 17,484 distinct | CONFIRMED |
| scored.jsonl 17,269 distinct; fail 17,243 / candidate 21 / incomplete 5 | scored_at ≤ cut: 17,269; 17,243 / 21 / 5 | CONFIRMED |
| pass 21 by two derivations, identical set | my rule: 21, same 21 ids | CONFIRMED |
| 687 ≥ 1.58, 89 on d0 cells with bar 2.69 | 687; 89, all delay 0 | CONFIRMED |
| every binding pass = 21, all USA/d1 Short Interest | 21, cell counter {USA/d1 Short Interest: 21} | CONFIRMED |
| DSR 0.996–0.99999 | 0.99610 – 0.9999992 | CONFIRMED |
| 63 alphas read, 262 corr lines | 262 lines; 74 alpha ids attempted, 63 with a numeric read | CONFIRMED (precision) |
| under both lines 3 (vRk095rv, qMWbdlmv, kqVbg1xP); other 18 read prod 0.79–0.85 | latest numeric read per alpha: exactly those 3 under 0.71/0.70; the 18 read prod 0.7902–0.852 | CONFIRMED |
| POSTed 2 → ACTIVE, 67 % | ledger: 2 × http 201, 2 adjudication ACTIVE; 2/3 | CONFIRMED |
| per ET day sims 3,019 / 3,375 / 4,824 / 5,048 / 1,218; ≥ bar 119 / 114 / 265 / 82 / 18; pass 3 / 6 / 12 / 0 / 0 | identical (distinct ids by dateCreated ET) | CONFIRMED |
| §11o 3,019 / 3,370 / 989, passes 3/6/9; §11w 9,079 / 21 / 475, allocator 4,462 / 0 | quoted correctly from 02_design; my recount of the §11w baseline window (dateCreated < 09-06 21:10 local, C11 rows out): 9,076 / 474 ≥ 1.58 / 21 pass — within 3 rows | CONFIRMED |
| 09-05 gained 5 rows from orphan recovery | 5 recovered rows carry an ET-09-05 dateCreated | CONFIRMED |
| no pass since 09-06 21:10 local | last pass dateCreated 09-06 08:36 ET = 19:36 local | CONFIRMED |
| measured-day submissions 0 and 0; by POST time 1 and 0 | kqVbg1xP posted 09-06 06:19 ET (alpha created 09-05) | CONFIRMED |
| per-cell table (10 rows) | every sims / ≥ bar / pass number identical; Short Interest 5.82 = 21/3,607·1,000 | CONFIRMED |
| "USA/d0 (4 cells) 1,430" | USA/d0 cells at the snapshot: Sentiment 440, Option 380, Other 340, Insiders 230, Fundamental 40 = 1,430 over **5** cells | **WRONG** → 5 cells (corrected) |
| "all other cells (9) 447" | JPN/d0 Fundamental 130, JPN/d1 News 60, IND/d1 Fund 50, CHN/d1 News 40, CHN/d1 Fund 40, JPN/d0 News 37, JPN/d1 Other 30, CHN/d0 News 20, JPN/d0 Model 20, JPN/d1 Analyst 20 = 447 over **10** cells | **WRONG** → 10 cells (corrected) |
| USA/d1 10,420 (59.6 %); outside 7,064 (40.4 %) produced 0 rows at bar; per-day 958+1,680+2,975+3,908+899 | 10,420 / 59.6 %; 7,064 / 40.4 %; 0 rows ≥ own bar outside USA/d1; per-day sum 10,420 | CONFIRMED |
| **"40 % of sims went to cells with 0 rows at their bar"** | cells with 0 rows at bar: 22 of 26, holding 7,064 sims = 40.4 % — the same set as "outside USA/d1" because all 4 USA/d1 cells have rows at bar and no other cell does | CONFIRMED |
| failing checks on the 598: LOW_FITNESS 447 / SUB 389 / LADDER 347; sole 79 / 64 / 8; CONCENTRATED_WEIGHT & HIGH_TURNOVER 1 each | identical (the two 1s are the same row) | CONFIRMED |
| IS_LADDER limits 1.58 (9,929) / 2.02 (469) / 2.37 (3) | on USA/d1 rows at the snapshot: 9,929 / 469 / 3 (+19 None) | CONFIRMED (they are USA/d1 counts) |
| sub-universe limit seen −0.66 … 0.90 | USA/d1 rows at snapshot: −0.66 … 0.90 (all rows: −1.78 … 0.90; the 598: 0.68 … 0.90) | CONFIRMED |
| failure sets 180 / 101 / 86 / 79 / 64 / 58 / 8; exactly-one 151; 598−21−64−8−58 = 447 | identical; 151; 447 | CONFIRMED |
| by-hypothesis table (6 rows, n / pass / fit / sub / lad / p50s) | options 342/19/200/273/182, p50 0.95/1.565/0.65/0.157/0.049; usa_short 140/2/132/0/85, 0.86/1.53/1.185/0.103/0.034; sentiment 40/0/40/40/32; insider 40/0/39/40/16; twitter 30/0/30/30/27; shortsurprise 5 + typed 1 = 6/0/6/6/5 — all match to the printed rounding | CONFIRMED |
| **fitness = Sharpe·√(\|returns\|/max(turnover, 0.125)); max error 0.005 on 140 rows; Sharpe 1.6 needs returns ≥ 4.9 %** | max abs error 0.0049 on the 140 usa_short rows and 0.0050 on all 17,465 rows with the three fields; 0.125/1.6² = 0.0488 | CONFIRMED (identity holds on every row, not only 140) |
| IV-spread rows fail sub-universe 115/115 | 115 rows with "ivspread" ≥ bar, 115 fail LOW_SUB_UNIVERSE_SHARPE | CONFIRMED; MECHANISM: UNKNOWN stands |

### §2 where the sims went (lines 130–162)
| claim | my derivation | verdict |
|---|---|---|
| 232 hypotheses, 337 pairs; passing mechanism keys 2 (19 + 2), both with us_short_sale | 232; 337; keys `options_x_short#option8\|us_short_sale#USA/d1` 19, `usa_short_x_profitability_x_accruals#fundamental6\|us_short_sale#USA/d1` 2 | CONFIRMED |
| **21 passes = 2 mechanism keys** | 21 passers → 2 distinct `meta.mechanism_key`; also 2 distinct hypotheses and 1 cell | CONFIRMED |
| 15,577 sims (89.1 %) on the 335 never-passing pairs; 17,484 − 1,159 − 748 | 15,577; 89.1 %; passing-pair sims 1,159 and 748 | CONFIRMED |
| largest-pairs table (11 rows) | every sims / ≥ bar / pass / best matches; intangibles(+accruals,+safety) = 651+634+529 = 1,814; JPN 458+399+439 = 1,296 best 0.84; d0 ivspread 1,210 | CONFIRMED except the next row |
| "usa_*_x_ivspread · USA/d0 (5 cells, bar 2.69) 1,210" | 5 pairs (sentiment×Sentiment 330, insider×Other 290, insider×Option 250, insider×Insiders 210, sentiment×Option 130) on **4** d0 cells | **WRONG** → 5 pairs on 4 cells (corrected) |
| arms: standing 15,462 (646 ≥ 1.58, 21 pass); current 1,050 (32, 0); typed 919 (1, 0); C11 53 (8, 0) | identical (C11 = arms R 15 + RS 14 + RV 16 + S 8 = 53, 8 ≥ 1.58 all in S) | CONFIRMED |
| other three USA/d1 cells 6,813 sims, 111 ≥ bar, 0 pass | 6,813 / 111 / 0 | CONFIRMED |
| candidates (i)–(iii) "none is established" | no experiment separates them; correctly left open | CONFIRMED (MECHANISM: UNKNOWN stands) |

### §3 harness v0 (lines 164–208)
| claim | my derivation | verdict |
|---|---|---|
| memory quotes (AUC 0.965, 62 %, 13×; 1.1 %, 55.8 %, 0.438, 0 %) | verbatim in `memory/alpha-harness.md` lines 29–34 and `iter1_breakthrough.json` | CONFIRMED |
| 0.965 → 0.949 (formula-join, 1,004 old_ids) → 0.944 (field-swap, ledger B8) | memory line 62–63 "1,004 old_ids … 0.949"; `iter_ledger.jsonl` B8 "0.965→0.944" | CONFIRMED |
| HARNESS_DESIGN caveats (wrong label; blind where the gate is decided) | lines 66–67 verbatim | CONFIRMED |
| iteration 2 seeded from 566 zero-fail structures, 60.6 % | `iter2_breakthrough.json` "mutate 566 known zero-fail winners"; memory "2 PASS(60.6%)" | CONFIRMED |
| iter3 prod-corr 0.9 / 0.8, none clean; FINAL joint ceiling 0.93 of bar | `iter3_breakthrough.json` prod_corr "0.9 … 0.8 — none clean"; FINAL_REPORT "peak 0.93 of bar" | CONFIRMED |
| "three submit tests pinned fitness ≥ 1.0 hard, IS_LADDER dynamic" | FINAL_REPORT: "2 live submit-tests pin the EXACT bar" and "3 live submit ground-truths"; the fitness/ladder sentence is verbatim | CONFIRMED (count reads 2 or 3 depending on the FINAL_REPORT field) |
| ≤ 90 sims per batch, single-stream, on the Mac | design text; batch files ≤ 90 entries each | CONFIRMED |
| "MECHANISM: UNKNOWN" for the 1/90 (a)/(b)/(c) | no arm ran the seeded generator without the surrogate — correctly open | CONFIRMED |

### §4 harness13 (lines 210–247)
| claim | my derivation | verdict |
|---|---|---|
| `harness13/` 30 entries | `ls -A harness13 \| wc -l` = 28 locally and 28 on the VPS | **WRONG** → 28 (corrected) |
| 10 frozen test files, R2 suite sha 40ab3963… | gate_runs R2 "over 10 suite files"; suite_sha256_locked 40ab3963ff03… | CONFIRMED |
| run_massgen.py 85 KB; 4 fidelity audits; 85 experiment cards | 85,669 bytes; FIDELITY_AUDIT{,_2,_3,_4}.md; `massgen/experiments` 85 entries locally (34 on the VPS) | CONFIRMED |
| DECISIONS: VPS 160.25.88.163, E1–E4 | DECISIONS.md lines 133, 140, 158, 193, 218 | CONFIRMED |
| gate ledger 40 entries; R1 PASS, R2 lock, R3 PASS, R4 exit 1, R5 exit 0, R6 exit 1; counts 15/8/7/5/3/2 | 40; last exit_code per round 0/1/0/1/0/1 (R2's three entries: 0, 0, 1); counts identical | CONFIRMED |
| crawl_fields 1,772 calls, 6 written, 4 failed, quoted note | `crawl_fields_status.json` identical | CONFIRMED |
| crawl_pyramid fixture only, "SIMULATED" throughout | `r4/crawl_pyramid_dryrun.json` 34 × "SIMULATED" in 871 lines | CONFIRMED |
| massgen run 1: 08-12 16:50–18:00 UTC, 360 POSTs, 140 / 220 (401), 1,120 children, STOPPED_NOT_429, 3 probes "no live session" | `result.json` identical | CONFIRMED |
| run 2: GEM 2/2000 = 0.10 %, MECHANIC 1/2000, Wilson [0.03 %, 0.36 %], DEFF 14.3; further run at 21.5 h left, no headline; journal 3,650 rows | log lines 24–30; "run 2, offset=93688, 21.50h left" is the last run header, no RUN REPORT after it; `sim_ceiling2/journal.jsonl` 3,650 lines | CONFIRMED |
| baseline 600 / 27,826 = 2.156 % | `harness13/massgen/SPEC.md` line 73 | CONFIRMED |
| climb 21,972 / 1,665 / 873 / 12 days; 00_baseline 10,159 / 56 / 0.90 / 0 | as above | CONFIRMED |

### §5 bottlenecks (lines 249–290)
| claim | my derivation | verdict |
|---|---|---|
| #1 second derivation §11w 9,079 / 475 (5.2 %) + 4,462 / 142 (3.2 %) + A/B 1,440 / 27 (1.9 %) | ratios 5.23 / 3.18 / 1.88 %; the three windows are §11w/§11y quotes (they sum to 14,981, not a partition of 17,484 — the 09-07 19:05 → 09-08 16:39 standing rows and C11 are outside them) | CONFIRMED as quotes; "same band" is a judgement (1.9 % vs 5.2 % is 2.7×) |
| #1 40.4 % on cells with 0 rows at bar; construction ladder 0.46 → 0.89 → 1.11 never run on USA/d1 | 40.4 % as above; §11l text; no USA/d1 rows carry the ladder recipes | CONFIRMED |
| #2 447 / 389 / 347; sole 79 / 64 / 8; 180 fail all three; R14/R15 no gain | identical; §11l R14 fitness p50 0.52 → 0.45, R15 max 1.47 | CONFIRMED |
| #3 18 of 21 read 0.79–0.85; "6 of the 16 siblings read 0.79–0.83 before kqVbg1xP was posted"; C11 residual p50 0.44 | 18, 0.7902–0.852; 6 siblings read before posted_at 1788689963 at 0.7902–0.8262, 12 after — the pair had 19 passers (18 siblings) at this snapshot, 16 was §11s's 09-06 count; C11 arm R: 15 rows, Sharpe p50 0.42 (§11u said 0.44 — rounding / row set) | CONFIRMED (precision on "16") |
| #4 19 of 21 → one POST; per-1k 25.4 / 1.73 / 0; fair baseline 0 / 7,223; allocator 0 / 4,462 | 19/748 = 25.4, 2/1,159 = 1.73; §11w quotes | CONFIRMED |
| #5 auth-dead 71 / 214 lines → 355 / 1,070 min; §11s 355 / 1,010 within 6 % | 71 / 214; 1,070 vs 1,010 = 5.9 % | CONFIRMED |
| #5 09-06 17:14 ReadTimeout orphaned 1,170 sims (878 recovered) | first ReadTimeout inside the 17:05 round; 22 non-zero exits on 09-06; `recover.log` first run "120 parents, 878 children attributed" — later runs recovered more: 1,120 recovered rows with checks carry a dateCreated in 09-06 17:00–21:30 local (of the 1,170) + 141 ORPHAN-UNMATCHED | CONFIRMED (878 = first recovery run; 1,120 by the snapshot) |
| #5 "the 09-07 01:53 DAILY line made the loop sleep 84,880 s" | the "sleeping 84880s" line is stamped 11:30:17 on 09-07, after the reset; forge_loop.sh's comment and §11v: the 01:53 DAILY line was still inside the loop's grep window; next round header 13:57 → ≈ 2.5 h lost, not 23.6 h | CONFIRMED mechanism; precision added (the sleep was issued 11:30, cost ≈ 2.5 h) |
| #5 ≈ 3,600 × 0.11–0.22 / 1,000 ≈ 0.4–0.8 | 0.40–0.79 | CONFIRMED |
| not binding: DSR 21/21; pool spreads 0.16–0.27 annual; weekly rule 1 of 3; GUARD/UNITS 3 and 0 | 21/21; GUARD-REFUSED 3 rows, no UNITS status; qMWbdlmv; **pool spreads**: not re-derived (needs the DSR pool variance; candidates' sr0_annual read 0.25–1.01) | CONFIRMED except "pool spreads 0.16–0.27": UNVERIFIABLE here |

## B. round_1.md

| claim | my derivation | verdict |
|---|---|---|
| Step 1: "2026-09-06 (4,907 sims …), 2026-09-07 (5,123 sims)" | rows-with-checks by ET day are 4,907 / 5,123 (rung_report's rule: journal rows) but **distinct alpha ids** are 4,824 / 5,048 — the 83 + 75 orphan-recovered alphas sit twice in the journal; 01_origins (same section, cited as the source) says 4,824 / 5,048 | **WRONG** as "sims" → 4,824 / 5,048 distinct (corrected); rung_report over-counts by the 158 duplicates |
| Step 1: 1 submission on 09-06 by POST time; 1 mechanism | kqVbg1xP posted 09-06 06:19 ET | CONFIRMED |
| Step 1: 96.6 % / 96.5 % / 18 of 21 / 2 keys | as in A | CONFIRMED |
| Step 2 table: datasets and userCounts (21 / 52 / 58 / 324 / 415 / 265 / 120 / 480) | identical to 02_dataset_map.md (its crawl of 09-08); my local catalogue (`fetched/rc/datasets_USA_TOP3000_d1.jsonl`, 07-15) reads 15 / 48 / 52 / 316 / 397 / 260 / 119 / 477 — older file, counts rise over time | CONFIRMED against the stated source; live value not re-read |
| Step 2: settings grid STATISTICAL/INDUSTRY/SUBINDUSTRY × decay 4/8 × trunc 0.08 | new-arm rows: exactly those 6 combinations (161–207 rows each), truncation 0.08 only | CONFIRMED |
| Verifier verdicts: newsneg and transcriptneg combiners [multiply] only; 7 composites run | `forge/composites/{newsneg_x_short,transcriptneg_x_revision}.yaml` combiners [multiply]; 7 yaml files carry `arm: new`; journal new-arm hypotheses = the same 7; `headline_x_momentum_gate` absent | CONFIRMED |
| "the 8 composites are 6 mechanism keys" | under 00_agreements' definition (composite id + datasets + cell) the 7 live composites read **7 distinct `mechanism_key`s** in the journal (the pulled 8th would be an 8th); "6" counts leg-family pairings (two tone×short, two tone×profitability) | **WRONG** as "mechanism keys" → 8 keys / 6 pairings (corrected) |
| "all 22 new-leg fields exist at USA d1"; "journal/targets collisions 0" | not re-derived (needs the field catalogue by leg; out of the journal's reach) | UNVERIFIABLE |
| Step 3: "152 tests green" | VPS `tests.log`: 147 passed (earlier), 154 passed 09-09 10:30; local `pytest forge/tests` 163 now; no record of the 09-08 build's count | UNVERIFIABLE (count moves with each commit) |
| Step 3: structural gate live since 09-07 | 02_design §11z ticked 09-07 22:10; `dryrun_gate9.txt` 09-07 22:50 | CONFIRMED |
| Step 4: dry-run seed 23 at 19:05: 290 = current 150 (40 / 40 / 70) + new 140 (News 60 / SI 40 / Model 20 / Analyst 20) | `state/forge/dryrun_r1.txt` (mtime 18:23): 290; by arm current 150 / new 140; cells Social 60 + Sentiment 60 + Insiders 20 + SI 50 + News 60 + Model 20 + Analyst 20 (SI 50 = 40 new + 10 current); first live round 22372 "by arm {'current': 150, 'new': 140}" | CONFIRMED (the file is stamped 18:23, not 19:05) |
| Step 4: confound — arms not on the same cells | new-arm cells: Short Interest 640, Fundamental 160, News 120, Analyst 50, Model 40; current: Social Media 660, Sentiment 648, Insiders 220, Short Interest 110 — overlap only on Short Interest | CONFIRMED |
| STARTED 18:45; unit switched to `--ab new`; restart at the round boundary ~19:00 | unit `FORGE_ARGS=… --ab new`; journalctl: STOP consumed 18:59:02, service restarted 19:00:03; first new-arm dateCreated 19:06:35 local | CONFIRMED |
| Measured day = ET 09-09 = local 09-09 11:00 → 09-10 11:00 | ET = UTC−4, local = UTC+7 | CONFIRMED (EX-ANTE arithmetic) |
| Warm-up: "rounds every ~13 min" | 12 post-switch round headers 19:00 → 21:10: gaps 13.9, 13.7, 13.1, 12.2, 16.4, 10.7, 9.5, 9.5, 10.6, 10.4, 10.4 min — median 10.7 | CONFIRMED loosely → written as 10–14 min |
| **"quota spent 21:57"** | DAILY_SIMULATION_LIMIT_EXCEEDED at the 21:10:31 round, "daily quota spent; sleeping 50036s" at 21:10:59 (50,036 s → 11:05 next day); last ET-09-08 dateCreated 21:08:44 local; nothing in the log at 21:5x | **WRONG** → 21:10 (corrected) |
| day total 4,996 (2,348 pre-switch, current 1,638, new 1,010) | ET 09-08 distinct alphas 4,996: no arm 2,348 (of which 180 landed after 18:42 from the last pre-switch round), current 1,638, new 1,010; no duplicate ids on this day | CONFIRMED |
| submissions 0 in both arms | ledger unchanged (2 rows, 09-04 / 09-06); loop.log "posted 0" every round | CONFIRMED |
| **A/B row "current 2,690 / 0.77 / 1.36 / 1.86 / 64 (2.4 %)"** | recount by meta.arm × dateCreated: current arm on ET 09-08 = **1,638 rows, p50 0.76 / p90 1.34 / max 1.86, 32 ≥ 1.58 (2.0 %)**; 2,690 / 64 is ab_report's POOLED current arm = 1,638 + 1,049 (ET 09-07, the typed A/B's current arm, 32 ≥ 1.58, on a different pairing) + 3 rows dated ET 09-06 | **WRONG** as the day's arm → 1,638 / 32 (2.0 %) (corrected; pooled figure kept as a note) |
| A/B row "new 1,010 / 0.75 / 1.46 / 1.86 / 53 (5.2 %) / 0" | 1,010; 0.75 / 1.46 / 1.86; 53; 5.2 %; 0 pass | CONFIRMED |
| "fails on the ≥ 1.58 rows: LOW_FITNESS, IS_LADDER" (current) | current 09-08 ≥ 1.58 rows: LOW_SUB_UNIVERSE_SHARPE 32/32, LOW_FITNESS 30, IS_LADDER 19 (pooled: 71 / 69 / 52) | **WRONG** → sub-universe first (corrected) |
| same for new | new: IS_LADDER 53/53, LOW_FITNESS 53/53, LOW_SUB_UNIVERSE 30 | CONFIRMED (precision added) |
| per composite: ravenpack 400 / p50 1.18 / max 1.86 / 53 ≥ 1.58 / fitness max 0.81 / turnover p50 0.16; newsneg 240 / 0.62 / 1.30; multiwire 80 / 0.99; headline 80 / 0.91; prtone 80 / 0.75; creditlang 80 / 0.69; transcript 50 / 0.50 | identical (turnover p50 0.159) | CONFIRMED |
| "the last four will be DEAD at 40–60 sims under the allocator" | `forge/allocate.py`: DEAD = sims ≥ 40 and best < 1.0 (d1 scale 1); multiwire's max 0.99 also qualifies → **five** | **WRONG** → the last five (corrected) |
| "reaches the Sharpe bar at 2× the current arm's rate" | arm level 5.2 % vs 2.0 % same-day (2.6×; vs the pooled 2.4 %: 2.2×); ravenpack alone 53/400 = 13.3 % (6.6×) | CONFIRMED (arm-level; precision added) |
| **"fitness 0.81 at turnover 0.16 needs returns ≈ 4.6 % at Sharpe 1.7 (it has ≈ 3.3 %)"** | the fitness-0.81 row is O0rZgaQb: Sharpe 1.65, turnover 0.105 (→ floor 0.125), returns 3.04 % → needs 0.125/1.65² = 4.59 %. At the sentence's own inputs (Sharpe 1.7, turnover 0.16) the need is 0.16/1.7² = **5.5 %**. The 53 rows ≥ 1.58: median Sharpe 1.63, turnover 0.206, returns 3.17 %, fitness 0.66 → need 0.206/1.63² = **7.8 %** | **WRONG** as stated (mixed inputs) → corrected with the row's and the medians' arithmetic |
| "MECHANISM of the fitness ceiling: the platform formula (verified)" | identity max error 0.005 on 17,465 rows | CONFIRMED (an identity, not a mechanism claim) |
| "bottleneck #2 of 01_origins" | yes, fitness / sub-universe / ladder on rows ≥ bar | CONFIRMED |

## C. Observations the documents do not contain (POST-HOC, for the record; no mechanism claimed)
1. `forge/offline/rung_report.py` counts journal rows, not distinct alpha ids; 158 orphan-recovered
   alphas appear twice (83 on ET 09-06, 75 on 09-07). Its "sims" column over-reads those days by
   1.7 % / 1.5 %; the Q6 "≥ 4,000 sims" guardrail should be read on distinct ids. The ET-09-08 day
   has no duplicates (4,996 either way).
2. Three current-arm rows carry an ET-09-06 dateCreated with seeds from 09-07 / 09-08
   (9qV65wQr, KPOwRQ6k, 1Yxn5Pm6, none flagged recovered). MECHANISM: UNKNOWN; candidates: the
   platform returning an older alpha for an identical (formula, settings), or orphan re-attribution.
   They do not move any count above.
3. At 13:39 local on 09-09 the measured day (ET 09-09) held 405 distinct alphas (current 300 / new
   105, 7 / 5 ≥ 1.58, 0 pass) — the loop ran 2 rounds after the 11:00 reset and was then waiting on
   auth ("auth dead or under 40 min before round" from 11:05). Reported, not scored.
4. The 09-08 evening rounds ended at 21:10 on the DAILY limit; the "quota spent" sleep is now
   computed from the round's own output (forge_loop.sh), so the 09-07 11:30 failure mode is closed.

## D. Corrections applied in place (dated 2026-09-09)
01_origins.md: (1) "USA/d0 (4 cells)" → 5 cells; (2) "all other cells (9)" → 10; (3) "USA/d0 (5
cells, bar 2.69)" → 5 pairs on 4 cells; (4) "harness13/, 30 entries" → 28; (5) "18,061 child rows
carry an alpha" → carry the `alpha` key (414 null); (6) "63 alphas read" → 63 numeric of 74
attempted; (7) "6 of the 16 siblings" → 16 at §11s's count, 18 at this snapshot; (8) the 84,880 s
sleep: issued 11:30 after the reset, ≈ 2.5 h lost.
round_1.md: (1) 4,907 / 5,123 → 4,824 / 5,048 distinct alphas, with the duplicate note; (2) "quota
spent 21:57" → 21:10; (3) "~13 min" → 10–14 min (median 10.7); (4) current-arm row 2,690 / 64
(2.4 %) → same-day 1,638 / 32 (2.0 %), pooled figure kept as a note; (5) current fails →
sub-universe 32/32 first; new fails → ladder 53/53, fitness 53/53, sub 30; (6) "last four DEAD" →
last five (multiwire 0.99); (7) fitness arithmetic rewritten with the actual row and the medians;
(8) "6 mechanism keys" → 8 keys under the fixed definition, 6 leg-family pairings; (9) "2×" given
its two readings (arm 2.6×, ravenpack alone 6.6×).
