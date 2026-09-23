# The hosted-LLM alpha author (built 2026-09-19)

Khoa's /goal, 2026-09-19: *"bắt đầu xây dựng lại hệ thống tự động đào alpha mới bằng host 1 LLM
chuyên để tạo alpha dựa trên dữ liệu có sẵn, tạo các cơ chế để LLM reasoning tài chính và cấu tạo
alpha chuẩn xác hơn."*

## 1. What the model is for, and what it is NOT for (MEASURED)

| measurement | source | what it decides |
|---|---|---|
| the random-within-grammar generator lost **5 of 5** live A/B rounds: 0.1 % of its rows reached the Sharpe bar against 2.6 % for the hand-written library | docs/redesign/02_design.md §11y | the model must produce **economics**, not formula strings |
| the only new mechanism ever to clear every binding platform check (Vk67oQ5V) came from a hand-written EX-ANTE hypothesis | docs/harness5/round_1.md | the output unit is a mechanism: a force, a counterparty, a sign, a citation |
| the 67-composite library already renders **32,624** distinct formulas on USA/d1 alone, against a ~5,000/day quota | measured 2026-09-19, `forge.compose.expand` over every cell | formula VOLUME is worthless; the quota binds, not the generator |
| one mechanism has historically absorbed up to **3,115** simulations (short_x_sentiment) | journal, 24,992 alphas | **10–17 new mechanisms per day** saturate a full quota day |
| 45 Claude agents produced 22 mechanisms in 2.5 h and **3 died on session limits** | 2026-09-09 workflow | the value of a hosted model is continuity and cost, not throughput |

So: the model replaces the *agents*, not the grammar. Ten good mechanisms a day is a full day's quota.

## 2. The accuracy mechanisms — each aimed at a failure the model actually makes

The model is never trusted and never grades itself ("LLMs cannot self-correct", vetted in
`papers_harness.md`). `forge/llm/verify.py` decides, in 0.046 s per candidate, with no simulation:

| check | what it decides | the failure it removes |
|---|---|---|
| `schema` | both YAMLs load through `forge.hypotheses` | invented schema keys, invented template syntax |
| `fields` | every field id is in the region catalogue with the assumed structure | **invented field ids** (the dominant small-model failure) |
| `density` | coverage < 0.50 needs a density rule; quarterly/annual needs `ts_backfill` | a gap read as the most negative value |
| `sign` | the leg's direction against the label file's reading of its own fields | a sign asserted from nothing |
| `renders` | `forge.compose` really produces a candidate, and **names the precondition that failed** | a leg that compiles to nothing |
| `typed` | `forge.typed` structural judge — the live pre-sim gate (H1 units, H2 kinds, H4 vector) | dividing a ratio by a currency |
| `standard` | the 8 hard gates of `fetched/hypothesis_standard.md` | vague economics, missing counterparty, undated citation |
| `distinct` | the family pair is new to the library | a sibling, which reads prod-corr 0.79–0.85 and can never be submitted |

Two design decisions worth stating, both grounded rather than guessed:

- **Reused fields are reported, never refused.** We MEASURED that field reuse sets neither
  correlation: the identical field set spans PROD 0.47–0.95 and SELF 0.15–0.91, and the one alpha
  sharing *no* field with a submission read the second-highest SELF on file
  (`round_3/prod_vs_self.md` §2, §3a). Refusing on it would refuse on a non-effect.
- **A `domain-prior` sign may be contradicted; a `description` sign may not, silently.** The
  insider-flow prior was measured wrong and removed from `labels.py` on 2026-09-07, so a prior that
  no better-informed leg can overturn is unfalsifiable. A field's own description is a fact, so
  contradicting it requires the `notes` block to say why. One line in `verify.sign_verdict` flips
  this if Khoa wants it stricter.

**Retrieval, not recall** (`forge/llm/retrieve.py`): every field id, the exact pyramid category
names, every partner leg and every already-used family pair are put IN the prompt. The model chooses
among facts; it never types an identifier from memory.

**Repair, not self-assessment**: on a trip, `verify.report()` goes back to the model verbatim, and
the proposal is re-graded. Nothing is kept on the model's own say-so.

## 3. Calibration — the bar, measured

Running the grader over the **hand-written** library: **40 of 67 composites pass all eight checks.**
The grader is therefore neither trivial nor impossible, and it found real defects in the live
library: three composites render **zero** constructions on USA/d1 today
(`financing_x_bloat`, `insider_x_accruals`, `tone_x_profitability`) — `insider_x_accruals` has never
produced a single journal row. Why `financing_x_bloat` rendered 579 rows historically and renders
none now is **MECHANISM: UNKNOWN** (candidates: a changed leg, a catalogue field withdrawn since the
2026-07-15 crawl, or those rows came from another cell).

## 4. Why the host is rented, not local (MEASURED 2026-09-19)

`qwen2.5:7b-instruct` on the M4 Pro, given the retrieved fields, the exact category list and three
repair rounds per mechanism: **0 of 3 kept**, ~20 s per attempt. The failures were capability, not
information:

- invented template syntax — `"{signal.vader_compound_sentiment_score}"` where the schema takes `{signal}`
- a citation placeholder left in — `"EX-ANTE — <NAME> (2023)"`
- a mechanism that restates the signal — "positive sentiment precedes price increases" — with no middle link

Repair rounds did not converge; attempt 2 often broke something attempt 1 had right. Khoa's decision,
2026-09-19: **rent the GPU, do not host on the laptop.**

## 5. Renting it — the operational recipe

Pricing checked 2026-09-19: RTX 4090 **$0.29–0.59/hr** typical (some listings from $0.16), A100 80GB
**from $1.09/hr**, interruptible 30–50 % cheaper, **billed per second**.

At 10–17 surviving mechanisms/day and a pass rate still to be measured, the batch is roughly
**3 GPU-hours/day** — so **$1–3/day**, because the box is spun up for the batch and killed after.
Do not rent by the month.

```bash
# on the rented box (vLLM image, one GPU):
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-72B-Instruct-AWQ \   # 1x A100 80GB;  Qwen/Qwen3-32B-AWQ fits a 4090
  --max-model-len 16384 --port 8000

# from here, before spending a batch:
python3 -m forge.llm.author --probe --host http://<vast-ip>:8000 --model Qwen/Qwen2.5-72B-Instruct-AWQ

# the batch itself (writes only into forge/*/staged/, the live loop never sees it):
python3 -m forge.llm.author --host http://<vast-ip>:8000 \
  --model Qwen/Qwen2.5-72B-Instruct-AWQ --n 20 --tries 3
```

`--api ollama` switches the wire format if the box serves ollama instead.

## 6. What is NOT yet established

- The pass rate of any model above 7B on these checks: **unmeasured**. It is the number that decides
  the GPU tier, and the first batch measures it.
- Whether an LLM-written mechanism reaches the Sharpe bar at the rate a Claude-agent-written one does:
  **unmeasured**, and only a live A/B answers it (the staged library is the arm).
- The verifier grades *form and grounding*. It cannot grade whether the economics are true. Nothing
  in it predicts a return, and no claim here says it does.

## 7. The formula arm (built 2026-09-19, Khoa's tick: measure both, do not argue)

### Why it exists — the measurement that justifies it
| fact | number | source |
|---|---|---|
| operators the platform allows (RC-85; anything else is a 400 reject) | **85** | `OPERATORS.md` quick index |
| operators this desk has EVER simulated | **20** | 18,796 USA formulas in the journal |
| of the 1,025 rows that reached the Sharpe bar | `ts_mean` 100 %, `group_rank` 100 %, `multiply` 71 % | same |
| shapes `forge/compose.py` can produce | **2** (`multiply(A+,B+)`, `if_else(greater(B+,.5),A,0)`) | the code |

So 65 operators and every non-trivial skeleton are unexplored, and the mechanism arm cannot reach
them *by construction*. Whether that space holds anything is UNKNOWN — this arm measures it.

### What it gives up, stated before any result
A bare expression has no economics to grade, so the 8 hard gates do not apply. That is exactly the
gap between the hand-written library (2.6–3.2 % of rows at the bar) and the random-within-grammar
generator (0.1 %, 0 platform passes in 920 sims). Each expression therefore carries a one-line
rationale, and `check_rationale` refuses one that names no counterparty. Six checks apply, not eight:
operator on the allowlist · field exists · ≤ 62 operators · rationale names a counterparty ·
settings valid · `forge.typed` structural judge.

### How it runs
`forge/llm/formula.py` writes a plan JSON for `forge/runner.py --plan` — the path C11 and POW used,
so the live planner and allocator are untouched. `vps/llm_formula_run.sh` drives it. The arm is
tagged `meta.arm = "llmformula"` and read by `ab_report` against the mechanism arm on the same day.
`ab_report.ARMS` had a hardcoded three-arm list that would have dropped this arm SILENTLY; it is now
a named constant with a test, because an uncounted experiment reads as "no rows", not "not counted".

## 8. RAG and guardrails (2026-09-19) — what was built, and what was deliberately not

**No vector store, and the reason is a measurement.** Everything that decides whether the model can
write a legal call already fits in the prompt:
| corpus | prompt cost |
|---|---|
| all 85 operator signatures, read from `OPERATORS.md` | **~460 tokens** |
| 24 retrieved fields with labels and descriptions | ~1,500 tokens |
| category names + 62 used family pairs | ~300 tokens |
Retrieval infrastructure for a corpus that fits in 2,300 tokens would be cost with no benefit. What
the retrieval layer does instead is *structured filtering* — by dataset, by crowding, by cell.

**Constrained decoding is the guardrail that matters** (`guided_json`, vLLM ≥ 0.8.5, xgrammar):
| failure a 7B actually made here | before | with the schema |
|---|---|---|
| did not emit the blocks | caught, one repair round | **unsamplable** |
| invented a schema key | caught | **unsamplable** (`additionalProperties: false`) |
| `neutralization` / `decay` invalid | caught | **unsamplable** (enum) |
| empty rationale ("it predicts returns") | caught | **unsamplable** (`minLength: 40`) |
| named a field not in the table | caught | **unsamplable** (enum of the retrieved ids) |

`formula_grammar()` is the second tier: a GBNF where field ids and operator names are terminals, so
an expression using an invented field or an off-list operator is unrepresentable. It removes two of
the six checks by construction. **UNTESTED against a live server** as of 2026-09-19 — it is behind a
flag and `guided_json` is the default.

One gap this work closed in itself: the formula prompt originally gave the model 85 operator NAMES
and no argument lists, so for the 65 it has never seen used it would have guessed signatures and
earned 400s. It now carries the real signature of each.


## 9. First live session (2026-09-19/20): what the model actually does

**Model of record: `Qwen/Qwen3.8-27B-FP8`** on a rented RTX 6000 Ada (48 GB), vLLM, FP8.

| measurement | value |
|---|---|
| proposals kept through all 8 checks | **23 of 128 = 18 %** |
| throughput | 4.4 mechanisms/min at 20-24 concurrent; 276 tok/s aggregate at 12 |
| cost of a day's supply (10-17 mechanisms) | **~$0.20** |
| formula arm | **124 expressions**, 40 distinct operators, **21 never simulated before** |

### Four defects found and fixed, each by measurement not guesswork
1. **vast.ai silently creates a STOPPED instance** when scheduling fails; `success: False` in the
   create response is the signal and "an instance exists" does not refute it. Fix: `--cancel-unavail`.
2. **Mamba cache crash-loop.** Qwen3.8's GDN linear attention needs one cache block per decode
   sequence; 48 GB at util 0.92 holds 241 and vLLM defaults `max_num_seqs` to 256, so the engine
   crash-looped every ~100 s. Fix: `--max-num-seqs 128`.
3. **Thinking mode ate the whole budget.** On the real 3,353-token prompt the model spent ALL 8,000
   completion tokens on reasoning and returned `content` of length ZERO — 12 of 12 mechanisms failed
   on "format" for that alone, at ~358 s each. Fix: `chat_template_kwargs: {"enable_thinking": false}`.
   **274 s -> 32 s per call.**
4. **A skeleton prompt is not an example.** The model omitted the `template:` key — 32 of 83 trips.
   Replacing the placeholder skeleton with one fully worked leg took the pass rate **5 % -> 15 %**.

### Bonsai 2 27B: tested and rejected (2026-09-20)
PrismML's ternary compression of this very model, $0.50/M output against $1.80/M, and its own
announcement claims instruction-following "slightly ahead" of the base. On OUR task, same datasets,
same prompt, same 8 checks: **0 of 20 kept**, against 18 % for the base. If it were as good as the
base, P(0 in 20) = 0.019 — so this is evidence, not luck. It IS faster (8.1 vs 4.4 mechanisms/min).
Getting there cost $0.89 across four rentals, every failure infrastructural and each one different:
host CDI broken · image pull stuck 17 min at 0 bytes · vast ran the image in `ssh` runtype so the
entrypoint never started · **CUDA Error 804** (host driver 570.169 against the container's CUDA 13.0).
The repacked repo also ships without `preprocessor_config.json`; it must be copied from the base model.

**Rental recipe that works** (all four constraints learned the hard way): `--cancel-unavail`;
`cuda_max_good >= 13.1`; sort offers by **download bandwidth**, not price, because a short batch pays
the pull cost either way; and pass `--args` or the image runs as an ssh box instead of a server.
