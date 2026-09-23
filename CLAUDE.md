## RULE 0 — NEVER RATIONALIZE. ANYTHING. EVER.

**This rule comes before every other rule in this file, and before any task.**

Rationalizing means: seeing a number, then inventing a mechanism that would explain it, and
stating that mechanism as if it were a finding. It is the most damaging thing possible here,
because a rationalization is indistinguishable from a discovery when you read it back later — it
sounds explained, it gets written into a file, and every decision after it is built on nothing.

**The rules, operationally:**

1. **An observation is not an explanation.** "Removing the carrier drops median ladder from 0.53
   to −0.02" is an observation. "The carrier carries the ladder" is a story. Report the first.
   Write **MECHANISM: UNKNOWN** for the second unless an experiment distinguished the candidates.

2. **Label every claim by its origin, honestly:**
   - `EX-ANTE` — derived from documentation or semantics BEFORE the relevant data existed.
   - `POST-HOC` — a regularity observed in data. A pattern, never an explanation.
   - `SPECULATION` — no documentation, no data. Say so; do not dress it as a mechanism.
   A hypothesis written after seeing the result is POST-HOC no matter when the file was saved.

3. **When several mechanisms fit, list them all and say none is established.** Do not pick the
   most plausible one. Plausibility is not evidence, and it is exactly what makes a
   rationalization convincing.

4. **Never write a mechanism into a file** — code comment, memory, .md — without naming the
   experiment that produced it. If no experiment did, the file says UNKNOWN.

5. **Your own measurements are suspect first.** Before reporting a finding, re-derive it a second
   way. Four "serious bugs" on 2026-08-02 were the auditor's error: counting rows with incomplete
   check sets as passes; counting alphas submitted before the pyramid program existed; a test
   regex that was wrong; and iterating raw journal lines instead of keying by `old_id`. Each
   looked conclusive and each dissolved on re-measurement.

6. **Report the confound before the conclusion.** Raw pooling reversed the sign of a real result
   (3.38% vs 4.86% raw; 4.16% vs 3.05% within cell). If a comparison has not been pooled within
   the confounding variable, it has no verdict yet.

7. **When corrected, say what was wrong and drop it.** No defending the earlier framing.

**The test:** for any sentence stating why something happens, can you name the experiment whose
result would have been different if the claim were false? If not, delete the sentence.

---

## RULE 1 — SIMULATIONS RUN ON THE VPS. NEVER ON THIS MACBOOK.

**Operator instruction, Khoa, 2026-08-14:** "máy macbook hiện tại của tôi ko dùng để sim alpha, tất
cả phải được thực hiện ở trên vps".

The MacBook is for writing code, running tests, and analysing journals. It does **not** POST
simulations. Anything that spends platform quota — `layered_sim.py --live`, the climb loop, the
gap-2x2 batch, any funnel or resim run — executes on the VPS (`root@160.25.88.163`, `/opt/wq`).

Operationally this means:

- Ship the code first (`scp`/`rsync` to `/opt/wq`), then start the loop **there** with `setsid` or
  `nohup` so it survives the ssh session.
- Locally, `--live` is not to be passed. A dry run (no `--live`) is fine anywhere: it draws and
  prints and spends nothing.
- The health report and the Discord monitor read VPS state. If they say "NOT producing" while a
  local process is running, **the report is right and the local process is the thing that is
  wrong** — that is exactly the confusion this rule removes.
- One loop at a time, holding a lock. Three simultaneous `layered_sim` processes once ran for
  2h46m unnoticed.

---

## RULE 2 — A NEW MECHANISM IS NOT SHIPPED UNTIL IT IS PROVEN, AND KHOA TICKS IT.

**Operator instruction, Khoa, 2026-08-18:** "khi xây dựng pipeline thì luôn tìm ra các cơ chế mới
thì phải xác định được mục đích chính của nó và tại sao nó xuất hiện nhưng phải được kiểm chứng là
hiệu quả đột phá trong nhiều vòng và đã giải quyết được vấn đề đặt ra ở mục đích và đã kiểm tra
không hề có xung đột với các cấu trúc đã tồn tại và trước khi đưa tôi duyệt câu hỏi bằng cách tick".

This rule exists because of what happened on the day it was written. Two mechanisms went into the
live loop with none of it done:

* the **deep seeder** was added on the argument that structural depth clears `IS_LADDER_SHARPE`.
  Measured afterwards, depth makes that gate **SCORED** (2.5% → 93.3%), not **PASSED** — median
  |sharpe| 0.27 for a deep seed against 1.91 for something the climb reached by growing. My own
  measurement refuted my own reason, and the mechanism had already been running for days.
* the **seven-move set** shipped with weights `34/34/12/7/6/3/4` that were a guess wearing the
  costume of caution. No measurement supported any of the seven numbers.

Both were caught by Khoa asking, not by me checking.

### The five gates. All of them, in order, before the mechanism runs live.

1. **PURPOSE.** One sentence: what problem does this solve? If the problem cannot be stated
   without naming the mechanism, there is no problem — there is a solution looking for one.
2. **PROVENANCE.** Why did this appear *now*? Which measurement, failure, or operator instruction
   produced it? "It seemed like it would help" is the answer that produced the deep seeder.
3. **PROOF ACROSS MANY ROUNDS.** Not one round, not a synthetic harness, not an offline
   simulation of the generator. The mechanism must be measured **live, over multiple cycles,
   against the arm that does not have it**, and the effect must be large enough to see — Khoa's
   word is "đột phá", and a difference that needs a careful eye is not that. State N, state the
   comparison arm, state the effect size. An A/B that was never run is not evidence.
4. **IT SOLVED THE STATED PROBLEM.** Gate 3 proves *something changed*. This gate asks whether the
   thing that changed is the thing named in gate 1. The deep seeder passed "something changed"
   easily: the ladder gate went from 2.5% to 93.3% scored. It failed this gate, because the purpose
   was to PASS the gate, not to be graded on it.
5. **NO CONFLICT WITH WHAT ALREADY EXISTS.** Name every existing rule, gate, filter and state field
   the mechanism touches, and show it does not quietly disable one. The precedents are on file:
   adding "every gate must be SCORED" to the correlation rule made tier 3 mathematically
   unreachable (0 of 28,330 rows) and gem production stopped; clearing `gemless_streak` on a phase
   reset made segment rotation unreachable. Both looked like additions. Both were deletions.

### Then, and only then

Present it to Khoa as **tick questions** (`AskUserQuestion`) — never as a paragraph asking for a
yes. Each question states what the mechanism does, and each option is a real alternative he can
choose, including turning it off. He ticks; then it ships.

**A mechanism already running that has not passed these gates is not grandfathered.** It is an open
item, and it is named as one when reporting status.

---


1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.