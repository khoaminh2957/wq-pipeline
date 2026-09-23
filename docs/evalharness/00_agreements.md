# evalharness — the agreements of record (Khoa, 2026-09-22)

The /goal: a multi-agent harness that builds (a) a PIPELINE EVALUATION SYSTEM producing a concrete
benchmark on three axes, and (b) a big-tech-grade CI/CD system, with the architecture drawn, attacked
and redrawn until it stops yielding defects. Every agent carries an expert job description; every new
module is examined by at least three independent hallucination auditors.

Twenty-one decisions, each a tick or a written instruction. Nothing below is my inference unless it
says so.

## The benchmark

| # | decision | Khoa's answer |
|---|---|---|
| D1 | What receives the final grade | A **pipeline VERSION**, scored over the quota days it runs |
| D2 | How the three axes combine | **Hard floor per axis, no compensation**; clearing all floors then yields a 0–100 score for ranking |
| D5 | Days per official scorecard | **1 quota day** |
| D6 | Where the floors sit | **Absolute, from the goal: 4 submitted alphas per quota day** |
| D14 | Which alphas are graded | **Only alphas the graded version itself produced** — "ko dựa trên dữ liệu cũ" (written instruction, not a tick) |

**The arithmetic consequence, stated before building (D5 × D6).** The best measured rate is 3
submissions over 31,044 simulations = 0.48 per 5,000-sim day; the floor is 8.3× that. Under a Poisson
rate of 0.5/day a single day returns 0 submissions 61 % of the time, and by the rule of three a day
with 0 events does not exclude a true rate as high as 3/day. So: every scorecard will read FAIL for
the foreseeable future, and a one-day count cannot by itself separate version A from version B.
Khoa accepted this knowingly. The reconciliation, agreed: **the floor decides PASS/FAIL and will say
FAIL honestly; the 0–100 score still ranks versions; the uncertainty is printed on the card.**

## The three axes

| axis | what it answers | decided content |
|---|---|---|
| 1 — product | is the alpha good, robust, trustworthy, with OS never observable | D3: DSR + PBO/CSCV + **parameter-neighbourhood stability** + **regime/subperiod stability**. D10: trustworthiness also requires the **8 hard gates of `fetched/hypothesis_standard.md`** — under D17 these are scored AFTER the alpha passes, not before it is simulated |
| 2 — throughput | 4 per day? how many sims per submittable alpha? sustainable or luck? | D7: all three of **Wilson confidence interval on the rate**, **distinct mechanisms among the submissions**, and **the rate holding in the next window** |
| 3 — CI/CD meshing | can branches be grown onto this pipeline, or is it a dead end | D8: **DORA four keys** + **architecture fitness functions** + **a real branch drill every release** (a throwaway component is actually plugged in and CI must carry it) |

## CI/CD

| # | decision | Khoa's answer |
|---|---|---|
| D4 | CI authority | **Block merge + auto-deploy to the VPS when green + rollback** |
| D9 | What the gate blocks on | **Regression** against the live version, plus tests/lint/schema. The 4/day floor is REPORTED, never used to block — otherwise nothing could ever merge |
| D13 | Where CI runs | **A new GitHub private repository + GitHub Actions** |
| D16 | Rollback trigger | **Post-deploy smoke test fails, or the first simulation round crashes** — before any quota is spent |

Infrastructure facts measured 2026-09-22 that constrain D13: there is **no git remote at all** today;
`.git` is 1.4 GB over 6,983 tracked files; the largest tracked file is 49.8 MB (GitHub's hard limit is
100 MB); the 84 MB journal is untracked. A credential scan of every tracked file found **no real
secret** — the two pattern hits are explicitly fake (`FAKE_URL`, "dummy webhook").

## The harness that builds it

| # | decision | Khoa's answer |
|---|---|---|
| D11 | Scale | **~40 agents per phase**, phases sequential, Khoa reviews between phases |
| D12 | Unit of hallucination audit | **Each new MODULE (file + its tests)**, examined by three independent auditors with DIFFERENT lenses: one against the specification, one re-deriving the arithmetic and running the tests, one hunting unstated assumptions and edge cases |
| D15 | When the architecture is finished | **Two consecutive adversarial rounds that find no new defect** |

## The goal amendment (Khoa, 2026-09-22, mid-session)

> "giờ sẽ ưu tiên việc tạo ra alpha submittable trước rồi sau đó mới kiểm tra nó có nghĩa hay ko …
> ưu tiên số 1 là tạo ra nhiều alpha có thể nộp được + ko tái sử dụng các cấu trúc các alpha
> (field + cách sài hàm giống) đã được nộp"

This REVERSES the desk's standing order, and the reversal is recorded rather than quietly applied.
It overrides memory `description-first-alpha-workflow` ("no hypothesis = no sim") and moves
`hypothesis-quality-standard`'s 8 gates from a pre-simulation gate to a post-pass score.

| # | decision | Khoa's answer |
|---|---|---|
| D17 | Order | **Pass first, judge meaning after.** Passes and is meaningful → submit at once; passes but meaning is unclear → weigh it |
| D18 | The no-reuse rule | **Khoa's own `fingerprint.py`**, which he asked me to find rather than invent a rule |
| D19 | Meaning threshold | **8/8 gates → submit automatically; 5–7 → Khoa ticks; under 5 → do not submit** |
| D20 | Generator freedom | **Free within the typed grammar (H1 units, H2 kinds, H4 vector — these are platform 400-errors, not economics), with a feedback loop toward passing.** The hypothesis requirement is dropped |
| D21 | Arms | **Replace wholesale — the entire quota goes to the new branch**, no 50/50 control |

### Evidence placed on the table before implementing D17, both directions

FOR: the binding wall is not the Sharpe bar but fitness / ladder / sub-universe and then correlation,
and fitness is pure arithmetic (Sharpe^1.5·√(σ/max(turnover, 0.125))) that no economic story improves;
the platform allows 85 operators and this desk has ever simulated **20** (`llm_author.md` §7).

AGAINST: the random-within-grammar generator lost **5 of 5** live A/B rounds, 0.1 % of its rows reaching
the Sharpe bar against 2.6 % for the hand-written library (`docs/redesign/02_design.md` §11y).
**MECHANISM: UNKNOWN** — no experiment distinguishes whether it lost for want of economics, for want of
a feedback loop toward passing, or because that grammar was itself too narrow. D20's generator has the
feedback loop the refuted one lacked, so the 5/5 result does not refute D17; it warns that *blind*
generation dies.

### A correction I owe the record (RULE 0 #7)

Earlier this session I told Khoa that "reusing fields does not set the correlation" and that his
no-reuse rule was therefore aimed at the wrong lever. **That was overstated and is withdrawn.** My
2026-09-09 measurement had 60 of its 62 correlation readings inside ONE mechanism, so it established
only that *within* a mechanism the field identity explains nothing and the settings do. `fingerprint.py`
measures *across* mechanisms on a 2,664-alpha pool and finds field-family Jaccard predicting PnL
correlation ≈ 0.61 and operator-multiset cosine ≈ 0.37, validated on 20 and then 23 re-simulated alphas,
flagging 10/10 known PnL-correlated pairs (0.68–0.94) with no false positives across families. The two
measurements answer different questions and do not conflict. Khoa's rule is evidence-backed.

### `fingerprint.py` as it stands (read 2026-09-22, 138 lines, NOT wired into `forge/`)

`structural_signature(formula) -> (field_families, operator_multiset)`, with `canon_field` collapsing
the horizon suffix so `implied_volatility_call_90` and `_150` are one family. `near_duplicate` fires
when field containment ≥ 0.85 AND operator cosine ≥ 0.75 (the "same core bet plus an add-on" cousin),
or when 0.6·Jaccard + 0.4·cosine ≥ 0.85 (the blatant parameter/horizon variant). `StructuralIndex`
registers what has been submitted and rejects the rest of that structural family. Numeric parameters
and neutralisation are deliberately excluded from the coarse hash so their variants share a bucket.
Verified by me on 2026-09-22: a horizon+window+group variant of one IV-spread formula scores 1.000 and
is caught; an IV-spread against a profitability ratio scores 0.200 and is not.

## Open items found while building, not yet decided

**Two tests have been red for weeks and nothing reported it.** `tools/tests/test_layered_sim.py::
test_a_crash_mid_batch_loses_no_journalled_row` fails: it asserts the dispatcher raises RuntimeError
mid-batch and it does not raise. Both `tools/layered_sim.py` and its test were last modified
2026-09-08 18:39, so the failure long predates this session — MEASURED by mtime and by the fact that
nothing in this session touched either file. The full suite is 1,024 tests, of which 1,023 pass; the
215-test `forge/tests` subset that everyone runs by hand is entirely green, which is why nobody saw it.

The CI gate's FIRST run (2026-09-23) found a second one:
`tools/tests/test_layered.py::test_the_model_names_the_operator_the_platform_named` asserts the
operator model would have prevented every journalled warning and finds 20 it would not. That file was
last modified 2026-08-13 -- SIX WEEKS red. Its traceback still names `/Users/kanenguyen/wq_pipeline/`,
the path this repository moved away from, so it may be reading a stale tree as well.

This is the argument for the CI the goal asks for, stated as a measurement rather than a principle:
the desk's manual habit cannot see a red test outside the subset it habitually runs, and the very
first automated run found two that had been invisible for two and six weeks. The gate blocked the
commit of the person who wrote it, which is the only way to know a gate works.

It also constrains the CI design. A gate on the FULL suite would be red on the first commit, so one
of three things must be true before CI can enforce green: the dispatcher test is fixed, or it is
explicitly quarantined with an expiry (the Google TAP practice for known-flaky tests), or the gate
starts on `forge/tests` and widens. Khoa decides; nothing here picks one.

The failing test guards a real property — that a crash mid-batch loses no journalled row — on the one
file that spends quota. Fixing it is not cosmetic, and it is not in this session's scope.

## Correction (2026-09-23 09:05): the quiet-hours rule was only one-third implemented

Khoa, 2026-09-22 23:4x: "các khoảng từ 1-6h sẽ ko tự spam link và số link đó để dành vào những trường
hợp cần thiết". I implemented it in `vps/auth_daemon.py:mint_gap()` and reported it as done. It was not.
There are THREE routine minters, and only one passes through that function:

| minter | passes through the daemon's mint_gap? |
|---|---|
| `auth_daemon.py` | yes |
| `wq-mint.timer` → `tools/mint_link.py --quiet`, every **minute** | no |
| `forge_loop.sh:47` → `tools/mint_link.py --quiet`, every round while auth is dead | no |

MEASURED: the mint budget went from 14 (after the operator's forced mint at 23:25) to 22 by 09:00 — 8
routine mints, against at most 4 the rule allows (the session was alive until ~03:28, then quiet until
06:00, leaving only the 06/07/08/09 hours). The sentence "daemon không còn tự mint trong khung đó" was true
of the daemon and false of what Khoa asked for; it is withdrawn.

Fix, shipped 09:05: the rule now also lives in `tools/mint_link.mint()`, the one function every routine
minter calls, placed BEFORE the hourly gate so a quiet-hours refusal never burns the hour for another
minter. `--force` (the operator asking) is untouched. A test fails if the two copies of the window ever
disagree. First night it can be observed: 2026-09-23 01:00–06:00; the check is the mint budget, which
should not move inside that window unless Khoa forces a link.
