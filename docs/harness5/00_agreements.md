# harness5 — agreements of record (Khoa's 30 answers, 2026-09-08 00:10–00:40)

Goal (Khoa, /goal 2026-09-08): a harness built on the most advanced harness papers, 5 agents running
concurrently in different roles, 5 self-improvement rounds, to rebuild the pipeline; investigate the
origins thoroughly; research every relevant paper for an architectural breakthrough; a complete
automated system; target **4 alphas submitted per 5,000-sim quota day**, with every robustness
requirement met and the ability to perform out of sample although OS is not observable.

## Benchmark and improvement
| # | Question | Answer of record |
|---|---|---|
| Q1 | benchmark | **submissions per quota day** (reset 00:00 ET = 11:00 local); target = 4 |
| Q2 | "submitted" | POSTed and **ACTIVE**, through the current gates: binding checks PASS, DSR ≥ 0.95 cumulative pool, prod < 0.71 & self < 0.70, MATCHES_PYRAMID PASS |
| Q3 | baseline | the historical **0.22 per 1,000 sims** (≈ 1.1 per 5,000-sim day) |
| Q4 | a round is an improvement when | it reaches its rung on the **5-rung ladder 0.3 → 0.4 → 0.55 → 0.7 → 0.8 per 1,000 sims**, i.e. per 5,000-sim day: **1.5 → 2 → 2.75 → 3.5 → 4** (rung k measured as the mean over the round's quota days; a day with < 4,000 sims does not count, Q6) |
| Q5 | evidence per round | **1 quota day (≈ 5,000 sims)** |
| Q6 | guardrails (must not regress) | **distinct mechanisms among submitted alphas does not fall**; **≥ 4,000 sims/day** (quota ≥ 80 % used). Standing constraints, not guardrails: no 403, no submit outside the authorised class |
| Q7 | a round misses its rung | fix and re-measure the same round, **at most 2 retries**, then stop and report to Khoa |
| Q8 | inside a round | **5 steps: diagnose (journal) → EX-ANTE hypotheses → build + tests → live A/B → hallucination audit + ship** |

## Harness architecture
| # | Question | Answer of record |
|---|---|---|
| Q9 | the 5 concurrent agents | **Researcher** (papers, platform docs → EX-ANTE hypotheses), **Builder** (code + tests), **Verifier** (adversarial: tests, hallucination, RULE 0), **Operator** (VPS runs, measurement, A/B), **Portfolio** (robustness, corr, DSR/PBO, pyramid cells, what to submit) |
| Q10 | backbone | **MetaGPT** SOP roles + standardised hand-offs (ratified 2026-08-13) **+ AlphaEvolve-style live-measured breakthrough gate** (the evaluator is the only truth) |
| Q11 | LLM placement | **design time only** — the 5 agents are Claude subagents; the running loop stays deterministic, no LLM, no paid API (C7/C30 stand) |
| Q12 | who ships a round's mechanism | **the harness ships automatically when the round's measured gate passes, Khoa is informed after** — Khoa's amendment of RULE 2 for this harness's rounds; revocable by him at any time |

## Research
| # | Question | Answer of record |
|---|---|---|
| Q13 | paper tracks | all four: **harness/multi-agent self-improvement**; **agent/LLM alpha mining**; **robustness/OOS statistics**; **BRAIN platform documents** |
| Q14 | vetting | **WebFetch every abstract; record URL + verbatim numbers; unfetchable ⇒ dropped, never cited** |
| Q15 | origins | **yes: a root-cause document measured from the journal, before round 1** (harness v0 surrogate, harness13, forge) |
| Q16 | base | **evolve `forge/`, one measured layer replaced per round** |

## Alpha supply
| # | Question | Answer of record |
|---|---|---|
| Q17 | round-1 lever | **new mechanisms from untouched datasets, each with an EX-ANTE hypothesis** |
| Q18 | scope | **USA/d1 first; another region opens when USA/d1 has ≥ 2 passing mechanisms** |
| Q19 | submission policy | **drop the 1-mechanism-per-week rule; keep only the correlation lines** (Khoa's change to the C21 auto-submit class; DSR pool and second-best rule unchanged) |
| Q20 | diversity | **≥ 3 distinct datasets among the 4 submissions of a day** |

## Robustness / OOS
| # | Question | Answer of record |
|---|---|---|
| Q21 | OOS-proxy before submit | **DSR ≥ 0.95 cumulative pool** (in use) **+ PBO (CSCV) ≤ 0.5 on the PnL matrix of the same pool** (to build) |
| Q22 | after submission | **ledger + daily read of platform status/grade; no inferred OS metric** |
| Q23 | WARNING on non-binding checks | **allowed; only binding checks must PASS** |
| Q24 | sim budget per measured day | **A/B 50/50 on the same cells**; the rung is read on the new arm scaled to 5,000 sims |
| Q30 | PBO parameters | **pool = the DSR pool (hypothesis × region/delay × category, cumulative), S = 16** |

## Operations
| # | Question | Answer of record |
|---|---|---|
| Q25 | auth | **unchanged: ask for a link only when the session is about to end** (Khoa taps) |
| Q26 | notifications | **this chat only; no Discord** |
| Q27 | schedule | **1 week, pressed** |
| Q28 | early stop | **none — all 5 rounds run** |
| Q29 | hypotheses before sim | **Verifier scores against hypothesis_standard (8 hard gates); Khoa gets a summary table; simulation starts without waiting for a tick** |

## Derived definitions (fixed here so no round can drift)
- **Rung test for round k**: on the round's measured quota day(s), new-arm submissions scaled to a
  5,000-sim day ≥ rung_k, AND both guardrails hold. A day with < 4,000 sims is not a measured day.
- **Distinct mechanism** = distinct `mechanism_key` (composite id + datasets + cell); **distinct
  dataset** = the dataset ids of the submitted formula's fields (signature.datasets).
- **PBO (CSCV)**: per pool, the daily-PnL matrix of every simulated member (T × N), S = 16
  contiguous blocks, all C(16, 8) = 12,870 IS/OOS splits; PBO = share of splits in which the IS-best
  member's OOS rank logit < 0. Requires the PnL curve of every pool member (harvest already fetches).
- **Round record**: `docs/harness5/round_k.md` with the 5 steps, the numbers, and the audit.

## Known limitation of the benchmark (Researcher A, EX-ANTE arithmetic, 2026-09-08 17:30)
The rung test is an integer 0–4 count per day. At the baseline rate λ ≈ 1.1/day an UNCHANGED
generator reads ≥ 2 (rung 1) on ~30 % of days; on a half-day A/B arm it reads rung 1 by chance ~42 %
of the time; a true rung-5 generator reads ≥ 4 on only ~59 % of days. One measured day cannot
separate adjacent rungs. Khoa chose 1 day per round (Q5) knowing the schedule (Q27); so every round
ALSO logs the higher-N funnel per arm-day as leading indicators — rows ≥ bar, binding PASS, DSR
PASS, corr PASS, ACTIVE, distinct mechanisms — and the round record states the rung verdict AND
the funnel. The rung stays the only truth; the funnel says whether the rung reading was luck.
