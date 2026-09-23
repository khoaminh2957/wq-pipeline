# harness5 — design of record (2026-09-08 18:30)

Inputs: `00_agreements.md` (Khoa's 30 answers), `01_origins.md` (measured bottlenecks),
`papers_harness.md` (28 vetted), `papers_alpha_mining.md` (23 vetted), `papers_robustness.md`
(11 vetted + platform facts by provenance), `02_dataset_map.md` (untouched USA/d1 datasets).
Every design choice below names its origin: MEASURED (01_origins / journal), EX-ANTE (a vetted paper or
platform fact), or SPECULATION (nobody measured it in a setting like ours).

## 1. What the harness must move, in the order the candidates die (MEASURED, 01_origins)
| # | where candidates die | number | lever class | round |
|---|---|---|---|---|
| 1 | Sharpe under the cell bar | 96.6 % of 17,484; 40 % of sims on cells with 0 rows at bar | new MECHANISMS on USA/d1 only; no sims on cells with no bar-crossing (already: d0 off, allocator) | R1 |
| 2 | fitness / sub-universe / ladder on rows ≥ bar | 96.5 % of 598; fitness = returns ceiling below 12.5 % turnover; IV-spread 115/115 sub-universe | turnover/returns shaping; sub-universe diagnosis (MECHANISM UNKNOWN) | R2 |
| 3 | correlation lines | 18/21 passers 0.79–0.85, with the pre-existing book | mechanisms on uncrowded datasets (crowding = userCount); day's four measured against each other before the first POST | R1, R3 |
| 4 | mechanism collapse | 21 passes = 2 keys, one short-volume leg | distinct-mechanism guardrail; mechanism-level credit/retirement | R1–R5 |
| 5 | quota unspent | 2 of 4 days ≥ 4,000 sims | session guard (done), auth idle = Khoa's taps (Q25: unchanged) | — |

## 2. Architecture (EX-ANTE: MetaGPT SOP roles; AlphaEvolve/FunSearch evaluator-as-truth; DGM keep-only-if-better)
Five roles, one SOP each, standardised hand-off artifacts (a role reads only artifacts, never another
role's chat), and a Verifier that never judges its own work (Chain-of-Verification; "LLMs cannot
self-correct" — both vetted).

| role | input artifact | output artifact | hard rule |
|---|---|---|---|
| Researcher | 01_origins, 02_dataset_map, papers_*, labels, hypothesis_standard | `round_k/hypotheses.yaml` (EX-ANTE: mechanism, counterparty, sign with citation, regimes, fields by label) | no journal Sharpe in the hypothesis text (RULE 0) |
| Builder | hypotheses.yaml, forge/ | code + tests (pytest green), composites/*.yaml, plan dry-run | one measured layer per round (Q16); RULE 1 |
| Verifier | everything the other four wrote | `round_k/audit.md`: each claim → journal line / test / sim id or REFUTED; hypothesis_standard 8 gates per hypothesis | never audits its own output; refutations go to the modules, not to a file only |
| Operator | plan, VPS | A/B day (50/50 same cells), `rung_report`, `ab_report`, funnel per arm-day | never starts a round with < 40 min session; nothing on the MacBook spends |
| Portfolio | scored, corr, PnL curves, pyramid counts | DSR + PBO verdicts, the day's four (mutual corr pre-screen), cell gains, submission order | C21 class only; second-best rule; ≥ 3 dataset sets/day |

Orchestration (this session): rounds are sequential; inside a round the five run concurrently where
inputs allow (Researcher ∥ Portfolio ∥ Operator-baseline while Builder builds; Verifier last).

## 3. The round protocol (Q8), with its gates
1. **Diagnose** (Verifier + Operator, ≤ 2 h): funnel of the last measured day per stage and per cell;
   the single largest death stage becomes the round's target. Artifact `round_k/diagnosis.md`.
2. **Hypothesise** (Researcher, ≤ 3 h): EX-ANTE mechanisms for that stage; each scored by the Verifier
   on hypothesis_standard's 8 hard gates before a sim (Q29); Khoa gets the summary table; no tick wait.
3. **Build + test** (Builder, ≤ 4 h): the one layer; pytest green locally and on the VPS; dry-run plan.
4. **Live A/B** (Operator, 1 quota day): `--ab <arm>` 50/50 on the same cells; the new arm is tagged
   `meta.arm`; rung read on the new arm scaled to 5,000 sims; guardrails read the same day.
5. **Audit + ship** (Verifier, then this session): every number re-derived; hallucination check of the
   round record; if rung_k AND guardrails hold → the arm becomes the default (Q12: automatic, Khoa
   informed); else retry ≤ 2 (Q7). Artifact `round_k.md` = the five steps with numbers.

Gate arithmetic (EX-ANTE, 00_agreements "known limitation"): one day cannot separate adjacent rungs;
the funnel per arm-day (rows ≥ bar, binding PASS, DSR PASS, corr PASS, ACTIVE, distinct mechanisms)
is logged every round as the leading indicator, and a rung pass with a funnel that did not move is
reported as "rung passed, funnel flat" — not as an improvement of the mechanism.

## 4. Evaluator and archive (EX-ANTE: FunSearch/AlphaEvolve program database; MAP-Elites cells)
- The only score is the live platform + the ledger: `forge/offline/rung_report.py` (submissions per
  quota day, sims, mechanisms, dataset sets, arms), `forge/offline/ab_report.py` (per arm per round).
- The archive is the journal (`state/layered/runs/forge.jsonl`, 17k+ rows) + `state/forge/scored.jsonl`
  + `corr.jsonl` + `submitted.jsonl`; the allocator's pair states are the MAP-Elites cells
  (hypothesis × cell), with DEAD/HARVESTED/NEAR_MISS as the per-cell verdicts.
- Coverage curve logged per arm-day: cumulative distinct passing mechanisms vs sims.

## 5. Runtime pipeline (deterministic, Q11) and the layer each round may replace (Q16)
```
labels (127,642 fields, EX-ANTE)  →  hypotheses/composites (EX-ANTE)  →  planner+allocator+structural gate
   →  dispatcher (VPS)  →  harvest (checks, DSR, PnL)  →  probe (prod/self corr)  →  portfolio (PBO, day's four)  →  submit (C21)
```
| round | layer (candidate, decided by that round's diagnosis) | EX-ANTE basis | measured risk |
|---|---|---|---|
| R1 | supply: new mechanisms from untouched USA/d1 datasets (02_dataset_map); schema-space generation over labelled fields | AlphaSchema/AlphaLogics (structure only); labels' literature signs | typed A/B lost 5/5 rounds with random-within-grammar: hypotheses must be hand-written per mechanism, not sampled |
| R2 | fitness shaping: turnover floor 12.5 % → returns lever; decay/smoothing grid per mechanism; sub-universe diagnosis | Kakushadze–Tulchinsky: returns independent of turnover (4,000 alphas) | R14/R15 measured: turnover halved, fitness unchanged |
| R3 | correlation: the day's four pre-screened for mutual corr from PnL curves (0.0662 + 0.9675·pearson, ±0.022 memory) before the first POST; prod-corr read ≤ 30 min before POST | platform: SELF_CORRELATION tightens with every own submission | siblings of a posted mechanism 0.8 regardless |
| R4 | robustness + scheduler: PBO wired into harvest/submit (pool N ≥ 20); four pre-checked candidates ready before the 11:00 reset | Bailey et al. 2017; quota resets 00:00 ET | PBO undefined for pools N < 20 |
| R5 | coverage: second region when USA/d1 has ≥ 2 passing mechanisms (Q18); mechanism-level retirement | MAP-Elites coverage | GLB/JPN/EUR measured 0 at bar so far |

## 6. What is NOT in the harness (and why)
- No learned surrogate for pass prediction: harness v0 measured OOS AUC 0.438 after in-distribution
  0.965 (01_origins); the labelled-vocabulary generator lost 5/5 A/B rounds (02_design §11y).
- No LLM at runtime (Q11); no notification channel but this chat (Q26).
- No early stop (Q28); no change to auth (Q25).

## 6a. PBO wiring (built 2026-09-08 20:30, adversarially reviewed by a 3-lens / 2-refuter workflow, 27 findings)
`forge/pbo.py` + `harvest.pool_pbo` + `submit.eligible`: per DSR pool, one column per DISTINCT
construction (resims collapse), curves from `state/pnl_curves` then the platform (fetch budget per
harvest RUN, default 150), a verdict only when the pool is COMPLETE (every member's curve in hand or
recorded unfetchable in `state/forge/pbo_unfetchable.json`), re-issued every run because the pool is
cumulative, rows written per pool (crash-safe); submit holds `pbo-fail`, `pbo-pending` and
`pbo-unjudged`; "insufficient" (N < 20) does not hold (Q21). Review findings accepted as CAVEATS, not
fixed: (a) a pool of near-identical siblings with equal skill gives PBO ≈ 0.5 by construction — the
≤ 0.5 rule sits at the null, so PBO separates "worse than a coin" from "not worse", nothing finer;
(b) the paper's statistic selects the IS-argmax-Sharpe trial while the harness selects by platform
pass + robust score — the PBO is the pool's, not the candidate's; (c) T ≈ 1,235 for 5-year sims →
77-row blocks; (d) modal-date alignment drops members covering < 90 % of the modal dates.

## 7. Confounds to state in every round record
- Half-day A/B arms read the rung by luck ~42 % of the time at baseline (00_agreements).
- A new mechanism's first day has N < 20 in its DSR/PBO pool: DSR uses the cumulative pool as ticked;
  PBO reports "insufficient" and does NOT block (documented, not a pass).
- Any change to the loop (session guard, gate) between the baseline days and the round days is a
  confound on the day-to-day comparison; the A/B inside a day is the controlled comparison.
