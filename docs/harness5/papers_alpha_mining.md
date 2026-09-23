# harness5 — Track B digest: automated / agentic alpha-mining papers (vetted 2026-09-08)

Purpose: what the literature offers a **deterministic generator + judge on WorldQuant BRAIN** whose measured
bottlenecks (task brief) are (1) fitness / ladder / sub-universe checks after Sharpe is reached, (2) prod-correlation
with the platform book (~0.8 for siblings of a submitted mechanism), (3) the number of DISTINCT mechanisms.
Target: 4 ACTIVE submissions per 5,000-sim day (00_agreements Q1–Q2). Runtime is deterministic, no LLM (Q11):
every LLM-in-the-loop mechanism below transfers only as **structure** for the generator/judge, never as running code.

Vetting (Q14): every abstract page was WebFetched (content read) and then `curl`ed for the HTTP code. Numbers and
sentences in quotes are verbatim from the fetched abstract; nothing else in this file is a paper's claim.
Labels: EX-ANTE = the paper measured it, in its own setting; POST-HOC = a regularity in our journal; SPECULATION =
neither. "(c) transfer" paragraphs are my reasoning and carry their own label.

## 0. Vetting register

| # | Paper | Authors, year | URL | HTTP | Verbatim from the fetched abstract |
|---|---|---|---|---|---|
| 1 | AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay | Tang, Chen, Yang, Mai, Zheng, Wang, Chen, Lin, 2025 | https://arxiv.org/abs/2502.16789 | 200 | "consistently delivering significant alpha in Chinese CSI 500 and US S&P 500 markets over the past four years" |
| 2 | QuantAgent: Seeking Holy Grail in Trading by Self-Improving LLM | Wang, Yuan, Ni, Guo, 2024 | https://arxiv.org/abs/2402.03755 | 200 | "two-layer loop"; no numeric result in abstract |
| 3 | R&D-Agent-Quant (RD-Agent(Q)) | Li, Yang, Yang, Xu, Wang, Liu, Bian, 2025 | https://arxiv.org/abs/2505.15155 | 200 | "up to 2X higher annualized returns than classical factor libraries using 70% fewer factors" |
| 4 | R&D-Agent: An LLM-Agent Framework Towards Autonomous Data Science | Yang et al. (16 authors), 2025 | https://arxiv.org/abs/2505.14738 | 200 | "achieving 35.1% any medal rate" on MLE-Bench; "two phases and six components" |
| 5 | Towards Data-Centric Automatic R&D (RD2Bench) — the 2404.11276 in the brief is this benchmark, not the agent | Chen et al., 2024 | https://arxiv.org/abs/2404.11276 | 200 | "RD2Bench is very challenging to the state-of-the-art (SOTA) large language model (LLM) named GPT-4" |
| 6 | AlphaForge: A Framework to Mine and Dynamically Combine Formulaic Alpha Factors | Shi, Song, Zhang, Shi, Luo, Ao, Arian, Seco, 2024 | https://arxiv.org/abs/2406.18394 | 200 | "generative-predictive neural network to generate factors"; no numeric result in abstract |
| 7 | Generating Synergistic Formulaic Alpha Collections via RL (AlphaGen) | Yu, Xue, Ao, Pan, He, Tu, He, 2023 | https://arxiv.org/abs/2306.12964 | 200 | "directly uses the performance of the downstream combination model to optimize the alpha generator"; no numbers |
| 8 | Alpha-GPT: Human-AI Interactive Alpha Mining | Wang, Yuan, Zhou, Ni, Shum, Guo, 2023 | https://arxiv.org/abs/2308.00016 | 200 | "via a number of alpha mining experiments"; no numbers |
| 9 | Alpha-GPT 2.0: Human-in-the-Loop AI for Quantitative Investment | Yuan, Wang, Guo, 2024 | https://arxiv.org/abs/2402.09746 | 200 | "Human-in-the-Loop strategy throughout the entire quantitative investment pipeline"; no numbers |
| 10 | 101 Formulaic Alphas | Kakushadze, 2016 | https://arxiv.org/abs/1601.00991 | 200 | "average holding period approximately ranges 0.6-6.4 days"; "average pair-wise correlation ... 15.9%"; "turnover has poor explanatory power for alpha correlations" |
| 11 | Performance v. Turnover: A Story by 4,000 Alphas | Kakushadze, Tulchinsky, 2015/16 | https://arxiv.org/abs/1509.08110 | 200 | "C ~ 1/T"; "return R has no statistically significant dependence on the turnover T"; "R ~ V^X ... X is around 0.8-0.85 for holding periods up to 10 days" |
| 12 | QuantaAlpha: An Evolutionary Framework for LLM-Driven Alpha Mining | Han et al. (17 authors), 2026 | https://arxiv.org/abs/2602.07085 | 200 | "IC of 0.0472 with ARR of 4.68% and MDD of 11.8%"; "40.28% and 19.1% cumulative excess return over four years" (CSI 500 / S&P 500 transfer) |
| 13 | Navigating the Alpha Jungle: An LLM-Powered MCTS Framework for Formulaic Factor Mining | Shi, Duan, Li, 2025 | https://arxiv.org/abs/2505.11122 | 200 | "a frequent subtree avoidance mechanism is introduced to enhance search diversity and prevent formulaic homogenization"; no numbers |
| 14 | AlphaEval: A Comprehensive and Efficient Evaluation Framework for Formula Alpha Mining | Ding et al., 2025 | https://arxiv.org/abs/2508.13174 | 200 | "backtest-free"; "five complementary dimensions: predictive power, stability, robustness to market perturbations, financial logic, and diversity"; "evaluation consistency comparable to comprehensive backtesting" |
| 15 | Alpha-R1: Alpha Screening with LLM Reasoning via RL | Jiang et al., 2025 | https://arxiv.org/abs/2512.23515 | 200 | "an 8B-parameter reasoning model trained via reinforcement learning for context-aware alpha screening" |
| 16 | AlphaLogics: A Market Logic-Driven Multi-Agent System | Weng, Zhang, Wang, Xia, 2026 | https://arxiv.org/abs/2603.20247 | 200 | "refining each market logic by aggregating the backtest outcomes of its guided factors"; CSI 500 and S&P 500; no numbers |
| 17 | RiskMiner: Discovering Formulaic Alphas via Risk Seeking MCTS | Ren, Zhou, Jiang, Liang, Wang, Peng, 2024 | https://arxiv.org/abs/2402.07080 | 200 | "risk-seeking policy explicitly optimizes the best-case performance rather than average outcomes"; "two real-world stock sets" |
| 18 | AlphaQCM: Alpha Discovery in Finance with Distributional RL | Zhu, Zhu, ICML 2025 (PMLR 267) | https://proceedings.mlr.press/v267/zhu25ag.html | 200 | "non-stationary and reward-sparse Markov decision process"; "particularly when dealing with large datasets comprising numerous stocks" |
| 19 | AlphaPROBE: Alpha Mining via Principled Retrieval and On-graph Biased Evolution | Guo et al., 2026 | https://arxiv.org/abs/2602.11917 | 200 | "Bayesian Factor Retriever ... posterior probability model"; "three major Chinese stock market datasets against 8 competitive baselines" |
| 20 | AlphaSchema: Exploring the Space of Trading Semantics for LLM-Based Alpha Mining | Yi, Yang, Jin, Li, Li, 2026 | https://arxiv.org/abs/2607.26642 | 200 | "schema plan composed of Event, Context, Qualities, Direction, and Output"; "learn a surrogate model over the semantic space"; "largely robust to the choice of LLM" |
| 21 | AgonAlpha: Autonomous Alpha Discovery via Prompt Economy and Scalable Agentic Search | Ye, Sun, Ren, Yu, Yi, Yang, 2026 | https://arxiv.org/abs/2608.11250 | 200 | "Independent deployments on WorldQuant BRAIN produced SPECTACULAR-grade alphas across five users and six model backends, with Fitness reaching 9.50 and Sharpe reaching 3.48" |
| 22 | Cognitive Alpha Mining via LLM-Driven Code-Based Evolution (CogAlpha) | Liu et al., 2025 | https://arxiv.org/abs/2511.18850 | 200 | "Experiments on 5 stock datasets from 3 stock markets"; no numeric result |
| 23 | AlphaBench: Benchmarking LLMs in Formulaic Alpha Factor Mining | Luo, Ko, Chen, Sun, Zhang, Liu, ICLR 2026 | https://iclr.cc/virtual/2026/poster/10008434 | 200 | "three core tasks, including factor generation, factor evaluation, and factor searching"; "persistent challenges in robustness, search efficiency, and practical usability" |

**Fetched but NOT citable for results:** Chain-of-Alpha (Cao, 2025, https://arxiv.org/abs/2508.06312, HTTP 200). Both
versions are marked withdrawn: "This version has been removed by arXiv administrators as the submitter did not have the
rights to agree to the license at the time of submission". Mechanism noted below for completeness; no result is cited.
**DROPPED (no fetchable page after three searches):** "FAMA" (cited second-hand as "Li et al. 2024b" in other papers'
related-work sections; no arXiv id or publisher page found). Never cited here.

## 1. Reading frame — what every paper's evaluator is, and what ours is

All 23 evaluate with an **offline backtest they own** (IC / RankIC / backtest return on CSI 300/500, S&P 500, or
MLE-Bench for #4), with **no evaluation budget stated in any abstract**. RL papers (#7, #17, #18) and MCTS papers
(#13, #17) need thousands to millions of evaluations per run by construction. Ours: the evaluator is the platform's
check set, one evaluation = one sim, 5,000/day, concurrency-capped, and the pass condition is a conjunction
(binding checks + DSR + prod < 0.71 + self < 0.70 + pyramid, Q2), not a scalar. **No abstract reports the metric we
are ranked on — passing submissions per evaluation budget.** #21 is the only one whose evaluator is BRAIN itself, and
its abstract reports maxima (Fitness 9.50, Sharpe 3.48), not yield, prod-corr, or submissions per day.

## 2. Per-paper digest — (a) generate / select, (b) own result verbatim, (c) transfer to BRAIN

### A. LLM-agent generators (structure transfers; the LLM does not — Q11)

**#1 AlphaAgent.** (a) LLM proposes hypothesis → factor; three regularisers: "(i) originality enforcement through a
similarity measure based on abstract syntax trees (ASTs) against existing alphas, (ii) hypothesis-factor alignment via
LLM-evaluated semantic consistency ..., (iii) complexity control via AST-based structural constraints". (b) "consistently
delivering significant alpha in Chinese CSI 500 and US S&P 500 markets over the past four years"; no IC/Sharpe in
abstract. (c) Transfers: an **AST-distance gate against our own submitted set** is computable pre-sim and deterministic.
Does NOT transfer: their "existing alphas" are their own pool; the BRAIN book is hidden, so AST distance to our set
addresses self-corr, and whether it predicts prod-corr is SPECULATION (no experiment here relates AST distance to the
platform's prod-corr). Their evaluator is an unlimited offline backtest.

**#2 QuantAgent.** (a) "inner loop, the agent refines its responses by drawing from its knowledge base ... outer loop,
these responses are tested in real-world scenarios to automatically enhance the knowledge base". (b) No numbers;
"capability in uncovering viable financial signals". (c) Transfers as a **judge-side ledger**: each sim's check
outcomes update a table keyed by mechanism, which the deterministic generator reads. The "provable efficiency"
claim depends on repeated real-world tests; with 5,000 sims/day the outer loop is the scarce step.

**#3 RD-Agent(Q).** (a) Research stage (hypotheses "based on domain priors") → Co-STEER code agent → backtest →
feedback, "with a multi-armed bandit scheduler for adaptive direction selection". (b) "up to 2X higher annualized
returns than classical factor libraries using 70% fewer factors". (c) Transfers: **MAB over directions with sims as
arm pulls** — the only paper mechanism that is literally a budget allocator. Does NOT transfer: factor-model
co-optimisation (BRAIN scores each alpha alone, no downstream model), and "2X returns with 70% fewer factors" is
a portfolio metric, not a pass-rate.

**#12 QuantaAlpha.** (a) Each end-to-end run is a trajectory; "trajectory-level mutation and crossover"; "enforces
semantic consistency across hypothesis, factor expression, and executable code, and constrains the complexity and
redundancy of the generated factor to mitigate crowding". (b) "IC of 0.0472 with ARR of 4.68% and MDD of 11.8%" (CSI
300, GPT-5.2); "40.28% and 19.1% cumulative excess return over four years" on CSI 500 / S&P 500 transfer.
(c) Transfers: complexity + redundancy limits as generator constraints. Their "mitigate crowding" is asserted as a
design goal in the abstract; whether a complexity cap lowers BRAIN prod-corr is SPECULATION. Trajectory evolution
needs many full runs = many evaluations.

**#13 LLM-MCTS ("Alpha Jungle").** (a) LLM refines formulas inside MCTS; "guidance of MCTS exploration by rich,
quantitative feedback from financial backtesting of each candidate factor"; "frequent subtree avoidance mechanism ...
prevent formulaic homogenization". (b) No numbers. (c) Transfers: **frequent-subtree avoidance** is a pure
generator-side rule — ban sub-expressions that dominate our simulated corpus (cf. memory "grep the generator first":
corpus frequency measures OUR generator). MCTS at 5,000 sims/day is feasible only for shallow trees.

**#16 AlphaLogics.** (a) "(i) Market Logic Mining: reverse-extracting market logic from historical factor libraries";
(ii) logics guide factor generation; "(iii) ... refining each market logic by aggregating the backtest outcomes of its
guided factors". (b) "consistently improves predictive metrics and risk-adjusted returns over representative baselines"
on CSI 500 / S&P 500; no numbers. (c) Transfers directly to the distinct-mechanism guardrail (Q6): **credit and retire
at the logic (mechanism_key) level**, scored by the aggregated platform outcomes of its children. A logic whose
children are all prod-corr siblings is retired as a unit. Their logic library is LLM-written; ours would be the
hypothesis ledger.

**#20 AlphaSchema.** (a) "schema plan composed of Event, Context, Qualities, Direction, and Output, specifying the
semantics of a candidate factor before implementation"; "evaluated rewards are accumulated to learn a surrogate model
over the semantic space"; selection balances "global exploration, surrogate-guided exploitation, and local mutation".
(b) No numbers; "implementations of the same schema plans by different LLMs exhibit comparable predictive quality".
(c) The closest fit to a deterministic generator: the schema is an **enumerable space**, so (1) a distinct mechanism
is a distinct schema point, (2) a surrogate over schema coordinates trained on our sim logs can predict pass
probability before a sim. Their surrogate targets IC-type reward; ours would target the Q2 conjunction — SPECULATION
until trained and measured on our journal.

**#19 AlphaPROBE.** (a) Factor pool as a DAG; "Bayesian Factor Retriever that identifies high-potential seeds by
balancing exploitation and exploration through a posterior probability model, and a DAG-aware Factor Generator that
leverages the full ancestral trace". (b) "three major Chinese stock market datasets against 8 competitive baselines";
gains in "predictive accuracy, return stability and training efficiency". (c) Transfers: keep the **lineage DAG of
every simmed alpha** and let seed selection down-weight a whole subtree once its leaves are siblings. Requires a
per-node reward — ours is the check vector, which the abstract's posterior model does not cover (SPECULATION).

**#21 AgonAlpha.** (a) Searches "frozen research artifacts---hypotheses, executable expressions, platform evidence,
rationales, and review status---rather than formulas alone"; "a fresh-context adversarial reviewer with re-execution and veto authority, and
pending-aware parallel budget allocation". (b) "Independent deployments on WorldQuant BRAIN produced SPECTACULAR-grade
alphas across five users and six model backends, with Fitness reaching 9.50 and Sharpe reaching 3.48". (c) The only
paper with BRAIN as evaluator. Transfers: **pending-aware budget allocation** (concurrency-capped sims) and an
adversarial re-executing reviewer (our Verifier role, Q9). Does NOT answer our question: maxima over five users are
not submissions per 5,000-sim day; prod-corr and distinct-mechanism counts are absent from the abstract.

**#22 CogAlpha.** (a) "code-level alpha representation with LLM-driven reasoning and evolutionary search". (b) "5
stock datasets from 3 stock markets"; no numbers. (c) Code-level representation does not map onto BRAIN's expression
language; low transfer.

**#8/#9 Alpha-GPT / 2.0.** (a) Human-in-the-loop prompt framework translating quant ideas to alphas. (b) No numbers.
(c) Nothing operational for a deterministic loop; the "idea → formula" step is Q29's hypothesis-first gate.

**Chain-of-Alpha (withdrawn).** Dual chain (generation + optimisation) using backtest feedback. Not cited for results.

### B. RL / search generators (reward definitions transfer; the search does not)

**#7 AlphaGen.** (a) RL generator whose reward is "the contribution to the combination models' performance" — the
marginal gain of the pool, not standalone score. (b) No numbers. (c) The **reward definition** transfers: score a
candidate by what it adds to the submitted set, i.e. penalise self-corr with our own alphas (computable pre-submit
from PnL curves, memory "PnL distance predicts self-corr"). The pool that matters for prod-corr is the platform's
hidden book, which no local reward sees — SPECULATION that pool-marginal reward lowers prod-corr. RL needs unlimited
evaluations.

**#6 AlphaForge.** (a) "generative-predictive neural network to generate factors ... while concurrently preserving
diversity"; combination model "incorporates the temporal performance of factors for selection and dynamically adjusts
the weights". (b) No numbers. (c) The **predictive half** is a pre-evaluation surrogate — the same object as a pre-sim
fitness/turnover predictor trained on our sim logs. Dynamic weighting has no counterpart (BRAIN submits single alphas).

**#17 RiskMiner.** (a) "reward-dense Markov Decision Process ... risk-seeking Monte Carlo Tree Search"; "explicitly
optimizes the best-case performance rather than average outcomes"; considers correlation within the collection.
(b) "outperforms all state-of-the-art benchmarks on two real-world stock sets". (c) The objective matches ours: a
submission day is a **max over candidates, not a mean**, so directions with high outcome variance are worth pulls.
SPECULATION for BRAIN. MCTS evaluation count does not transfer.

**#18 AlphaQCM.** (a) Distributional RL; Q-network + quantile network; variance-guided exploration under a
"non-stationary and reward-sparse" MDP. (b) "significantly outperforms its competitors, particularly when dealing with
large datasets comprising numerous stocks". (c) Only the principle (explore by variance) transfers; the method needs
millions of evaluations.

### C. Evaluation / screening

**#14 AlphaEval.** (a) "backtest-free" screen on "predictive power, stability, robustness to market perturbations,
financial logic, and diversity". (b) "evaluation consistency comparable to comprehensive backtesting". (c) Four of the
five dimensions need the price data locally; on BRAIN only **financial logic and diversity** are data-free pre-sim.
Their consistency claim is against their backtest, not against a platform check set — SPECULATION for us.

**#15 Alpha-R1.** (a) "8B-parameter reasoning model trained via reinforcement learning for context-aware alpha
screening", "activating or deactivating factors". (b) "consistently outperforms benchmark strategies". (c) Screens for
regime relevance, not platform checks; and it is a runtime LLM (Q11). Low transfer.

**#23 AlphaBench / #5 RD2Bench / #4 R&D-Agent.** Benchmarks and an MLE framework. (b) #23: LLMs face "persistent
challenges in robustness, search efficiency, and practical usability"; #5: "very challenging to ... GPT-4"; #4:
"35.1% any medal rate". (c) A caution for design-time agents (Builder output must be test-verified, Q9), not a lever.

### D. Turnover / fitness empirics on WorldQuant's own alphas (EX-ANTE for BRAIN, closest population available)

**#11 Performance v. Turnover.** (b) "4,000 real-life trading portfolios (U.S. equities) with holding periods of about
0.7-19 trading days"; "C ~ 1/T"; "return R has no statistically significant dependence on the turnover T"; "R ~ V^X
... X is around 0.8-0.85 for holding periods up to 10 days". (c) With fitness = Sharpe·sqrt(|R| / max(T, 0.125))
(definition as used in this repo's boost-fitness skill), R independent of T means **lowering turnover raises fitness
with no expected return cost on this population** — the turnover denominator is a pure penalty. R ~ V^0.8 says the
returns term scales with volatility; whether higher-vol universes cost the sub-universe/robust checks is unmeasured.

**#10 101 Formulaic Alphas.** (b) "average holding period approximately ranges 0.6-6.4 days"; "average pair-wise
correlation of these alphas is low, 15.9%"; "turnover has poor explanatory power for alpha correlations". (c) A
**negative lever**: turnover is not a decorrelation axis. That the 101 formulas are crowded on BRAIN is SPECULATION.

## 3. Levers for distinct passing mechanisms — ranked

Rank = (fit to a deterministic generator) × (addresses a measured bottleneck) × (evidence strength). Every item is
EX-ANTE only in the paper's setting; none was measured on BRAIN except where #21 is named.

**(1) Generating NEW mechanisms, not variants**
1. **Schema-space generation** (#20): enumerate Event × Context × Qualities × Direction × Output; a mechanism_key is a
   schema point; sample schemas first, formulas second. EX-ANTE (their setting). Fits Q17 (untouched datasets = new
   Context/Event values) and Q20.
2. **Logic-level credit and retirement** (#16): aggregate child outcomes per logic; retire a logic, not a formula, when
   its children are siblings. EX-ANTE.
3. **Frequent-subtree avoidance + AST originality** (#13, #1): ban dominant sub-expressions of our own corpus; reject
   candidates within an AST distance of the submitted set. EX-ANTE for diversity of formulas; SPECULATION that it
   yields distinct mechanism_keys rather than syntactically different siblings.
4. **Lineage-DAG seed selection** (#19): down-weight subtrees whose leaves failed prod-corr. EX-ANTE.
5. **MAB / pending-aware budget over directions** (#3, #21): allocate the 5,000 sims across mechanism families by
   observed pass-rate with exploration; #21 ran on BRAIN but reports maxima only. EX-ANTE (#3 on backtests).

**(2) Decorrelating from a crowded book**
6. **Pool-marginal reward** (#7): rank candidates by gain to our own submitted set (self-corr via PnL distance).
   EX-ANTE for their pool; SPECULATION for the hidden platform book — no paper measures against an external book.
7. **Complexity / redundancy caps "to mitigate crowding"** (#12, #1): SPECULATION for prod-corr; the abstract asserts
   the goal, the effect on an external book is not reported.
8. **Do not use turnover as a decorrelation lever** (#10): "turnover has poor explanatory power for alpha
   correlations". EX-ANTE on 101 WorldQuant-style alphas.
9. Untouched datasets (Q17) — none of the 23 papers tests dataset novelty against a crowded book; SPECULATION, ours.

**(3) Predicting fitness / turnover before simulating**
10. **Turnover → fitness relation** (#11): R has no dependence on T on 4,000 WorldQuant alphas, so a lower-turnover
    variant is expected to raise fitness at equal Sharpe·√R; predicts which sibling to sim first. EX-ANTE.
11. **Surrogate over schema coordinates / generative-predictive net** (#20, #6): train on our sim logs to predict the
    Q2 conjunction per schema point before spending a sim. EX-ANTE that a surrogate tracks an IC-type reward;
    SPECULATION that it tracks a platform check conjunction (internal prior: memory "alpha-harness" reports a
    shadow-sim surrogate at grouped-CV AUC 0.965 — not re-verified in this document).
12. **Data-free screens** (#14): financial-logic and diversity dimensions only; SPECULATION for platform checks.
13. **Risk-seeking allocation** (#17): pull directions by best-case, not mean; SPECULATION.

## 4. What does NOT transfer, in one place
- Any mechanism whose search is the LLM at runtime (#1, #2, #12, #13, #15, #16, #19, #20, #21, #22) — Q11.
- Any RL/MCTS search that needs unlimited evaluations (#7, #13, #17, #18) — only their reward/objective definitions.
- Factor-model co-optimisation and dynamic pool weighting (#3, #6, #7) — BRAIN evaluates single alphas.
- IC / ARR / medal-rate results (#3, #4, #12) — none is a pass-rate against a platform check conjunction.
- #21's Fitness 9.50 / Sharpe 3.48 are maxima across five users; they are not evidence about yield per sim.
