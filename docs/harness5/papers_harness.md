# harness5 — track A digest: self-improving multi-agent harnesses (vetted 2026-09-08)

Purpose: ground the 5-agent / 5-round harness (Researcher, Builder, Verifier, Operator, Portfolio; steps
diagnose → EX-ANTE hypotheses → build+tests → live A/B → audit+ship; `docs/harness5/00_agreements.md`) in
papers that were actually fetched. Backbone of record: MetaGPT SOP roles (Q10) + an AlphaEvolve-style
live-measured breakthrough gate. Evaluator = the platform (≈5,000 sims per quota day; a round = 1 day).

## Vetting rule and what "fetched" means here
- Q14: every abstract page was WebFetched; URL + verbatim text recorded; unfetchable ⇒ dropped, never cited.
- WebFetch does not surface the numeric HTTP code on a successful fetch; **OK** below means the page's
  title, author list and abstract were returned. Redirects and retries are stated where they happened.
- Every number in this file is copied from the fetched abstract page. Numbers that live only in a paper's
  body (e.g. MetaGPT's executability scores, MAP-Elites coverage figures, Self-Refine's per-task deltas,
  quoted in `docs/harness13/PAPERS.md`) are **not used here** because they were not on the fetched page.
- Dropped: **none** of the 28 candidates. Not attempted (so not citable): Alpha-GPT / AutoAlpha / McLean-Pontiff.

## Vetting table (28 papers; quotes are verbatim from the fetched abstract)
| # | Paper | Authors (first) | Year | URL | Fetch | Verbatim from abstract |
|---|---|---|---|---|---|---|
| 1 | MetaGPT | Hong … Schmidhuber | 2023 | arxiv.org/abs/2308.00352 | OK | "cascading hallucinations caused by naively chaining LLMs"; "encodes Standardized Operating Procedures (SOPs) into prompt sequences"; result stated only as "more coherent solutions than previous chat-based multi-agent systems" — **no number on the page** |
| 2 | AlphaEvolve | Novikov … Balog (DeepMind) | 2025 | arxiv.org/abs/2506.13131 | OK | "continuously receiving feedback from one or more evaluators"; "multiply two 4×4 complex-valued matrices using 48 scalar multiplications; offering the first improvement, after 56 years, over Strassen's algorithm" |
| 3 | Darwin Gödel Machine | Zhang, Hu, Lu, Lange, Clune | 2025 | arxiv.org/abs/2505.22954 | OK | "empirically validates each change using coding benchmarks"; "SWE-bench from 20.0% to 50.0%, and on Polyglot from 14.2% to 30.7%"; "sandboxing, human oversight" |
| 4 | ADAS (Meta Agent Search) | Hu, Lu, Clune | 2024 | arxiv.org/abs/2408.08435 | OK | "a meta agent iteratively programs interesting new agents based on an ever-growing archive of previous discoveries"; "maintain superior performance even when transferred across domains and models" — **no number** |
| 5 | STOP | Zelikman, Lorch, Mackey, Kalai | 2023 | arxiv.org/abs/2310.02304 | OK | "seed 'improver' that improves an input program according to a given utility function"; "this is not full recursive self-improvement"; "evaluate the frequency with which the generated code bypasses a sandbox" — **no number** |
| 6 | Reflexion | Shinn … Yao | 2023 | arxiv.org/abs/2303.11366 | OK | "maintain their own reflective text in an episodic memory buffer"; "91% pass@1 accuracy on the HumanEval coding benchmark, surpassing the previous state-of-the-art GPT-4 that achieves 80%" |
| 7 | Self-Refine | Madaan … Clark | 2023 | arxiv.org/abs/2303.17651 | OK | "uses a single LLM as the generator, refiner, and feedback provider"; "7 diverse tasks"; "improving by ~20% absolute on average in task performance" |
| 8 | AI Scientist-v2 | Yamada … Ha | 2025 | arxiv.org/abs/2504.08066 | OK | "progressive agentic tree-search methodology managed by a dedicated experiment manager agent"; "three fully autonomous manuscripts"; "one manuscript achieved high enough scores to exceed the average human acceptance threshold" |
| 9 | FunSearch | Romera-Paredes … Fawzi | 2023 (Nature, 14 Dec) | nature.com/articles/s41586-023-06924-6 | OK after 303→302 redirect via idp.nature.com; final page returned the article | "pairing a pretrained LLM with a systematic evaluator"; "confabulations (or hallucinations), which can result in them making plausible but incorrect statements"; "searches for programs that describe how to solve a problem, rather than what the solution is" — **no number** |
| 10 | Voyager | Wang … Anandkumar | 2023 | arxiv.org/abs/2305.16291 | OK | "an ever-growing skill library of executable code"; "3.3x more unique items, travels 2.3x longer distances, and unlocks key tech tree milestones up to 15.3x faster than prior SOTA" |
| 11 | Eureka | Ma … Anandkumar | 2023 | arxiv.org/abs/2310.12931 | OK | "evolutionary optimization over reward code"; "29 open-source RL environments that include 10 distinct robot morphologies, Eureka outperforms human experts on 83% of the tasks, leading to an average normalized improvement of 52%" |
| 12 | Promptbreeder | Fernando … Rocktäschel | 2023 | arxiv.org/abs/2309.16797 | OK | "mutates a population of task-prompts, and subsequently evaluates them for fitness on a training set"; mutation "governed by mutation-prompts that the LLM generates" — **no number** |
| 13 | SWE-agent | Yang … Press | 2024 | arxiv.org/abs/2405.15793 | OK | "custom agent-computer interface (ACI)"; "pass@1 rate of 12.5% and 87.7%" (SWE-bench, HumanEvalFix) |
| 14 | Agent Laboratory | Schmidgall … Barsoum | 2025 | arxiv.org/abs/2501.04227 | OK | "Human involvement, providing feedback at each stage, significantly improves the overall quality of research"; "an 84% decrease compared to previous autonomous research methods" |
| 15 | Large Language Monkeys | Brown … Mirhoseini | 2024 | arxiv.org/abs/2407.21787 | OK on 2nd attempt (1st = tool-side timeout, not HTTP) | "coverage … scales with the number of samples over four orders of magnitude"; "often log-linear"; "from 15.9% with one sample to 56% with 250 samples"; without verifiers "majority voting and reward models) plateau beyond several hundred samples" |
| 16 | MAP-Elites | Mouret, Clune | 2015 | arxiv.org/abs/1504.04909 | OK | "a map of high-performing solutions at each point in a space defined by dimensions of variation that a user gets to choose"; "either positively or, equally of interest, negatively" — **no number** |
| 17 | TextGrad | Yuksekgonul … Zou | 2024 | arxiv.org/abs/2406.07496 | OK | "backpropagates textual feedback"; GPQA "from 51% to 55%"; "20% relative performance gain in optimizing LeetCode-Hard" |
| 18 | GEPA | Agrawal … Khattab | 2025 | arxiv.org/abs/2507.19457 | OK | "combine complementary lessons from the Pareto frontier of its own attempts"; "outperforms GRPO by 6% on average and by up to 20%, while using up to 35x fewer rollouts" |
| 19 | ShinkaEvolve | Lange, Imajuku, Cetin | 2025 | arxiv.org/abs/2509.19349 | OK | "a parent sampling technique balancing exploration and exploitation, code novelty rejection-sampling … and a bandit-based LLM ensemble selection strategy"; "circle packing solution using only 150 samples" |
| 20 | LATS | Zhou … Wang | 2023 | arxiv.org/abs/2310.04406 | OK | "integrate Monte Carlo Tree Search"; "pass@1 accuracy (92.7%) for programming on HumanEval with GPT-4" |
| 21 | Tree of Thoughts | Yao … Narasimhan | 2023 | arxiv.org/abs/2305.10601 | OK | "Game of 24, while GPT-4 with chain-of-thought prompting only solved 4% of tasks, our method achieved a success rate of 74%" |
| 22 | Mind Evolution | Lee … Chen | 2025 | arxiv.org/abs/2501.09891 | OK | "Controlling for inference cost, … significantly outperforms other inference strategies such as Best-of-N and Sequential Revision"; "more than 98% of the problem instances" |
| 23 | QuantAgent | Wang, Yuan, Ni, Guo | 2024 | arxiv.org/abs/2402.03755 | OK | "two-layer feedback loop"; "in the outer loop, these responses are tested in real-world scenarios to automatically enhance the knowledge base" — **no number** |
| 24 | RD-Agent(Q) | Li … Bian (Microsoft) | 2025 | arxiv.org/abs/2505.15155 | OK | "multi-armed bandit scheduler for adaptive direction selection"; "up to 2X higher annualized returns than classical factor libraries using 70% fewer factors" |
| 25 | AlphaAgent | Tang … Lin | 2025 | arxiv.org/abs/2502.16789 | OK | "(i) originality enforcement through a similarity measure based on abstract syntax trees (ASTs) against existing alphas, (ii) hypothesis-factor alignment … (iii) complexity control"; "CSI 500 and US S&P 500 markets over the past four years" — **no number** |
| 26 | LLMs Cannot Self-Correct Reasoning Yet | Huang … Zhou | 2023 | arxiv.org/abs/2310.01798 | OK | "LLMs struggle to self-correct their responses without external feedback, and at times, their performance even degrades after self-correction" — **no number** |
| 27 | MAST — Why Do Multi-Agent LLM Systems Fail? | Cemri … Stoica | 2025 | arxiv.org/abs/2503.13657 | OK | "1600+ annotated traces collected across 7 popular MAS frameworks"; "14 unique modes, clustered into 3 categories: (i) system design issues, (ii) inter-agent misalignment, and (iii) task verification"; "kappa = 0.88" |
| 28 | Chain-of-Verification | Dhuliawala … Weston | 2023 | arxiv.org/abs/2309.11495 | OK | "(iii) answers those questions independently so the answers are not biased by other responses"; "decreases hallucinations across a variety of tasks" — **no number** |

## Digest — (a) mechanism, (b) the paper's own result, (c) what it implies here
Setting facts used in (c), all from `00_agreements.md` / forge state, none from a paper: quota ≈ 5,000 sims/day;
A/B 50/50 on the same cells (Q24) ⇒ ≈ 2,500 sims per arm; blocks of 10 per composite (Khoa's tick A3) ⇒
≈ 250 composites per arm-day; baseline 0.22 submitted per 1,000 sims (Q3); loop is deterministic, no LLM (Q11).
**Every (c) is an analogy unless it says otherwise** — no fetched paper measured a 1-day round on a live platform.

### A. Backbone and inter-agent hallucination
- **MetaGPT** (a) SOPs as prompt sequences; assembly-line roles; intermediate results verified by the next role.
  (b) Abstract: "more coherent solutions" — no number. (c) Organising structure only (as the memory note already
  says). What it prescribes: each role hands the next a fixed artifact, not prose. Here: hypotheses file → code diff
  + test log → audit table → measured-day record → submit ledger. SPECULATION that this raises submissions/day.
- **MAST** (a) taxonomy of MAS failures from traces. (b) "14 unique modes … 3 categories … kappa = 0.88".
  (c) Use the three categories as the Verifier's audit checklist per round: spec/design failure, inter-agent
  misalignment (e.g. Builder implements a different hypothesis than Researcher wrote), task verification
  (round declared done without the rung test). Adopt the checklist; its effect here is unmeasured.
- **Cannot Self-Correct** (a) intrinsic self-correction without external feedback. (b) "at times, their
  performance even degrades". (c) The Verifier never asks an agent to re-read and re-judge its own output. Every
  check resolves to an oracle: a journal line, a test run, a sim result, a fetched page. This is a ban, not a tool.
- **Chain-of-Verification** (a) plan verification questions, answer them independently of the draft. (b) "decreases
  hallucinations" — no number. (c) Factored verification: the Verifier receives each claim ALONE (number + file +
  line) without the Builder/Researcher rationale, and re-derives it. Matches RULE 0 §5 (re-derive a second way).
- **Agent Laboratory / AI Scientist-v2** (a) staged research pipelines; human feedback per stage (AL); tree-search
  over experiments under an experiment-manager (AIS-v2). (b) AL: "84% decrease" in expense, "Human involvement …
  significantly improves"; AIS-v2: 1 of 3 manuscripts over the acceptance threshold. (c) Supports Q29 (Khoa sees
  the hypothesis table, sims start without a tick) and Q12 (auto-ship, inform after). Cost result irrelevant here
  (Q11: no paid API in the loop). AIS-v2's tree search is per-experiment; our "experiment" is a whole quota day —
  branching factor is the number of arms, which Q24 fixes at 2.

### B. Evaluator-grounded evolutionary search (the AlphaEvolve-style gate)
- **FunSearch** (a) LLM proposes programs; a deterministic evaluator scores; a program database keeps the best.
  (b) No number on the page; the design claim is "pairing a pretrained LLM with a systematic evaluator" against
  "confabulations". (c) The platform is the evaluator; nothing an agent writes is a score. The database (formula,
  settings, parent, score, cell) is LLM-free and belongs in the deterministic loop. Already the shape of
  `forge/` harvest + `mechanism_key`.
- **AlphaEvolve** (a) evolutionary coding agent, "continuously receiving feedback from one or more evaluators".
  (b) "48 scalar multiplications … first improvement, after 56 years, over Strassen's algorithm". (c) The abstract
  gives no ablation separating the LLM mutation operator from the database, so whether the database alone
  transfers to a no-LLM loop is **UNKNOWN**. The transferable part is the gate: a change counts only when the
  evaluator says so — Q4's rung ladder is exactly that gate.
- **ShinkaEvolve** (a) parent sampling (explore/exploit), code-novelty rejection sampling, bandit over LLMs.
  (b) "circle packing solution using only 150 samples". (c) Two of the three are LLM-free and fit Q11: (i) parent
  sampling over the archive of measured composites instead of uniform draws; (ii) novelty rejection — do not
  simulate a composite whose signature is a near-duplicate of a measured one (forge already refuses > 1 shared
  leg with a POSTed alpha). 150 samples is circle packing, not BRAIN; do not carry the number over.
- **MAP-Elites** (a) archive keyed by user-chosen descriptors; keep the best per cell. (b) No number on the page;
  claim: illuminates performance "either positively or, equally of interest, negatively". (c) The pyramid cells ×
  dataset are the descriptors (Portfolio already ranks by empty cells). The "negatively" half is the failure use:
  a cell whose best after N sims is far under the bar is data (forge's DEAD-at-40, backtested by the project as
  saving 24% of sims with 0 later passes — that is a POST-HOC backtest, not this paper's number).
- **Eureka** (a) evolutionary search over reward code with an RL evaluator in the loop. (b) "outperforms human
  experts on 83% of the tasks … average normalized improvement of 52%". (c) Closest published analogue of
  "code → expensive evaluator → keep best → mutate"; evaluator there is RL training, also slow. Supports keeping
  the mutation in the code artefact (composites library), not in the prompt.
- **Large Language Monkeys** (a) repeated independent sampling; coverage vs samples. (b) "log-linear"; "15.9% with
  one sample to 56% with 250 samples"; without verifiers, selection "plateau[s] beyond several hundred samples".
  (c) We HAVE a verifier, so breadth of distinct candidates is the right use of quota, and the coverage curve
  (cumulative distinct passing mechanisms vs sims) is the thing to log per day. Whether our curve is log-linear
  is unmeasured — the 09-07 allocator day was 4,462 sims → 0 pass, so the curve can be flat.
- **Mind Evolution** (a) generate–recombine–refine with an evaluator, cost-controlled. (b) beats "Best-of-N and
  Sequential Revision" at equal cost; "> 98%". (c) Compare arms at equal sims (Q24 does). Recombination of two
  measured composites is a legal LLM-free move (forge/ensemble.py exists; measured 4 ensembles, 0 pass).

### C. Self-modification of the harness itself
- **Darwin Gödel Machine** (a) archive of agents; sample a parent, propose a code change, keep it only if the
  benchmark improves. (b) "20.0% to 50.0%" SWE-bench; "14.2% to 30.7%" Polyglot; "sandboxing, human oversight".
  (c) The round loop of Q16 ("one measured layer replaced per round") is DGM at N = 5 with the rung test as the
  benchmark. DGM's benchmark has hundreds of items; ours is an integer 0–4 per day — see §"Power" below.
- **STOP** (a) an improver program improves programs under a utility function, then improves itself. (b) No number;
  "not full recursive self-improvement"; measures sandbox-bypass frequency. (c) For Q12 (auto-ship when the gate
  passes): ship only through tests + a revert path, and log any change that touches quota/submit/auth code as a
  sandbox-relevant change. The Builder must not edit the gate it is measured by (RULE 2 gate 5 precedent).
- **ADAS** (a) meta agent programs new agents from an archive. (b) No number. (c) Design-time only (Q11). Its one
  transferable claim — designs "maintain superior performance even when transferred" — is unmeasured here.
- **Promptbreeder / GEPA / TextGrad** (a) evolve prompts (PB, self-referential mutation-prompts); reflect on
  trajectories and combine Pareto-frontier lessons (GEPA); backpropagate textual feedback (TextGrad).
  (b) PB: no number; GEPA: "up to 35x fewer rollouts", "+6% … up to 20%" vs GRPO; TextGrad: "51% to 55%",
  "20% relative". (c) All three optimise LLM prompts; our loop has none (Q11). What survives: GEPA's rule of
  keeping the Pareto frontier of attempts (not just the best) and reading lessons from failures in words — that
  is the Researcher's diagnose step, run on the journal once per round, by hand.

### D. Memory, reflection, tree search, tooling
- **Reflexion** (a) verbal reflection on external feedback into an episodic memory buffer. (b) "91% pass@1 …
  GPT-4 … 80%". (c) Keep a per-round, per-failing-gate post-mortem (`round_k.md`), written from sim results only.
  Reflection on non-executed feedback is banned by #26. Effect on submissions/day: unmeasured.
- **Self-Refine** (a) one LLM generates, critiques, refines. (b) "~20% absolute on average" over 7 tasks.
  (c) Prose-only (round records, hypotheses text). Never as a scorer of alphas — the same LLM as judge and author
  is exactly the loop #26 warns about.
- **Voyager** (a) skill library of executable, composable code + iterative prompting on execution errors.
  (b) "3.3x … 2.3x … 15.3x faster". (c) The composites library IS the skill library; each composite carries its
  measured stats and lineage, and new composites are built from measured legs (forge does this).
- **ToT / LATS** (a) explicit search over intermediate steps; LATS adds MCTS + environment feedback. (b) ToT:
  "4% → 74%" on Game of 24; LATS: "92.7%" HumanEval. (c) Their branching happens inside one cheap call. Here a
  branch costs sims; the analogue is the allocator's block-of-10 per composite (one expansion), then re-select.
- **SWE-agent** (a) an agent-computer interface designed for the model: file viewer, edit, test run.
  (b) "12.5% and 87.7%". (c) Builder productivity lever: `forge` tests + `recover_orphans` + a one-command dry run
  are the ACI. Unmeasured here; the paper's claim is that interface design changes agent behaviour.

### E. Quant alpha-mining agents
- **QuantAgent** (a) inner loop refines from a knowledge base; outer loop tests in "real-world scenarios" and
  writes back. (b) No number. (c) Same two-loop shape as design-time agents (inner) + platform day (outer).
- **RD-Agent(Q)** (a) Research stage (hypotheses from domain priors) → Development (code) → feedback; bandit over
  directions. (b) "up to 2X … using 70% fewer factors". (c) forge/allocate.py is that bandit; the project's own
  measurement (09-07, 4,462 sims) found **no difference** vs baseline. The paper's 2X is a backtest vs factor
  libraries, not passes per sim on a platform — do not expect it to transfer.
- **AlphaAgent** (a) AST-similarity originality vs existing alphas; hypothesis–factor alignment; complexity cap.
  (b) No number on the page. (c) All three are LLM-free at run time and map to existing gates (signature novelty,
  hypothesis_standard, op cap). Its decay claim was measured on CSI 500 / S&P 500, not on prod-corr vs a book.

## Answers to the four questions (labelled)
- **How many candidates per round.** EX-ANTE arithmetic: ≈ 250 composites × 10 sims per arm-day. No fetched paper
  gives a count for our base rate. Papers say how to spend it: distinct parents from the archive (Shinka, MAP-Elites),
  breadth over revision because a verifier exists (Monkeys), equal-cost arms (Mind Evolution).
- **Power of the rung test (EX-ANTE arithmetic, Poisson, from Q3–Q5, re-derived in Python 2026-09-08).** Baseline
  λ = 1.1/day: P(≥ 2 on one day) = 0.30, so an unchanged generator "passes" rung 1 three days in ten. On the A/B
  half-day arm (λ = 0.55, scaled ×2): P(reads ≥ 2) = 0.42. A generator truly at rung 5 (λ = 2 per half-day arm)
  reads ≥ 4 only 59% of days. One measured day cannot separate rung k from rung k−1; DGM/Reflexion do not have
  this problem because their benchmarks have hundreds of items. Mitigation is not in any paper: log the
  higher-N funnel counts (rows ≥ Sharpe bar, binding PASS, corr PASS, DSR PASS, ACTIVE) per arm per day as
  leading indicators; the rung stays the only truth, and Q7's two retries are the only replication we have.
- **Use of failures.** Reflexion/GEPA-style written post-mortems from executed feedback only (#6, #18, #26);
  MAP-Elites' "negatively" (#16): a cell's measured ceiling is a fact that steers the allocator (DEAD-at-40);
  novelty rejection (#19, #25): never re-simulate a near-duplicate of a failed or posted formula.
- **Cascading hallucination.** Fixed artifact hand-offs (#1); factored checks with the claim alone (#28); no
  self-judging (#26, #7); MAST's three categories as the audit list (#27); every number in a round record must
  string-match a journal line (RULE 0 §4) — that last rule is ours, not a paper's.
- **What to log.** Program database (#9, #2, #3): formula, settings, parent, cell, arm, round, every metric, and
  the day's coverage curve (#15); per-gate post-mortem (#6); archive lineage so a passing mechanism is
  replayable (#3); allocator/bandit stats (#24, #19); sandbox-relevant code changes (#5).

## Architecture proposal, grounded
| Paper → mechanism | Where it sits in harness5 | Status |
|---|---|---|
| #1 MetaGPT → SOP roles, fixed artifacts between roles | All 5 roles; hand-off schema per step | ratified backbone (Q10); effect unmeasured |
| #2 AlphaEvolve / #9 FunSearch → evaluator is the only score; program database | Step 4 live A/B; Operator + ledger | ratified gate (Q4/Q10); DB = forge harvest |
| #3 DGM → keep a change only if the benchmark improves; archive lineage | Step 5 audit+ship; Q16 one layer per round | Q12 auto-ship; N = 5 rounds |
| #5 STOP → sandbox-bypass accounting | Verifier flags changes touching quota/submit/auth | to build (grep-level check) |
| #6 Reflexion / #18 GEPA → post-mortem from executed feedback; keep the Pareto frontier | Step 1 diagnose (Researcher writes `round_k.md` §1) | design-time only (Q11) |
| #16 MAP-Elites / #15 Monkeys → cell archive; coverage curve | Portfolio (cells), Operator (curve per arm-day) | forge cells exist; curve logging to build |
| #19 Shinka / #25 AlphaAgent → parent sampling; novelty rejection; AST originality | Deterministic loop: allocator + signature gate | partly exists (signature, > 1 shared leg rule) |
| #24 RD-Agent(Q) → research/dev/feedback + bandit | Researcher/Builder split; forge/allocate.py | allocator measured: no difference (09-07) |
| #26 / #28 / #27 → no self-judging; factored claims; MAST checklist | Verifier, step 5 | to adopt; effect unmeasured |
| #13 SWE-agent / #10 Voyager → ACI; executable skill library | Builder tooling; composites library | exists in forge |
| #14 Agent Laboratory → human feedback per stage | Khoa's tick points (Q12, Q29) | ratified |

Roles → mechanisms. **Researcher**: #24 research stage, #25 hypothesis alignment, #6/#18 diagnose from the journal;
output = EX-ANTE hypothesis table (predicted sign, cell, datasets, source). **Builder**: #13 ACI, #10 library,
#3/#5 one code layer with tests and a revert; output = diff + test log. **Verifier**: #28 claim-alone re-derivation,
#26 ban on self-judging, #27 checklist, hypothesis_standard 8 gates (Q29); output = audit table, each claim → line.
**Operator**: #9/#2 evaluator loop on the VPS, #15 coverage curve, #19/#24 deterministic allocator; output =
measured-day record with arm labels and funnel counts. **Portfolio**: #16 cell archive, #25 originality vs posted,
corr lines + DSR/PBO (track C); output = submit ledger with `mechanism_key` and datasets (Q6, Q20).

Steps → mechanisms. 1 diagnose: #6, #18, #27, #3 lineage. 2 EX-ANTE hypotheses: #24, #25, #1 artifact schema.
3 build+tests: #13, #3, #5. 4 live A/B: #2/#9 gate, #22 equal-cost arms, #15 curve, #19 sampling. 5 audit+ship:
#28, #26, #3 keep-if-better, #14 human-in-stage (Khoa informed after, Q12).

### SPECULATION — no fetched paper measured any of these in a setting like ours
1. That fixed-artifact hand-offs (#1) or factored verification (#28) change submissions/day at all.
2. That archive parent-sampling / novelty rejection (#19) raises passes per 1,000 sims on BRAIN (Shinka's 150
   samples is circle packing; the project's own bandit allocator measured 0 difference).
3. That a post-mortem written by design-time agents (#6) transfers into a loop that has no LLM to read it (Q11):
   the transfer path is a hand-written deterministic rule per round, and that path is untested.
4. That AST originality (#25) lowers prod-corr against the platform book; the paper measured decay on CSI 500 /
   S&P 500 with no platform correlation gate.
5. That five DGM-style keep-if-better rounds (#3) converge when the benchmark is an integer 0–4 per day with the
   pass-by-chance rates above; MECHANISM of any observed rung gain: UNKNOWN until the funnel counts move with it.
6. Whether AlphaEvolve's database (#2) matters without its LLM mutation operator — no ablation on the fetched page.
