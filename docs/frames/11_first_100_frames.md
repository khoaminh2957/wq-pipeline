# 11 — The first 100 frames: library candidates

2026-09-24. Role: library curator. The library is `framelib/library/`: 100 entries, all with
status `candidate` and reliability `UNMEASURED`. It was built with the architect's own builder
(`framelib.build`) and checked with its validator (`framelib.store`). No framelib code was changed.
Nothing was simulated, nothing touched the VPS, and nothing runs live (RULE 1, RULE 2). Scripts and
outputs are in `$CUR` =
`/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad/frames/curator/`
(§9).

Labels (RULE 0):
- **EX-ANTE**: from definitions, code or frame text.
- **POST-HOC**: a regularity measured in data, never an explanation.
- **SPECULATION**: neither.

No sentence below says why a frame scores what it scores. Wherever that question comes up, the
answer is **MECHANISM: UNKNOWN**.

---

## 0. Summary

1. **The mix: 43 mined frames and 57 novel frames.**
   - The 43 mined frames cover all 34 mined shapes and all 6 of the quant's families.
   - The 57 novel frames are every designer frame: 21 designer families, 57 distinct shapes.
2. **The mined side is narrow.** Its 77 candidates are 6 structures, repeated with different group
   tokens and windows (EX-ANTE, from the texts). One frame per shape keeps every structure. The frames
   dropped differ from a kept frame only in their windows.
3. **Most of the library has no evidence yet.** 57 of the 100 frames have never been simulated.
   Khoa's step 1 asks for frames whose simulated results beat the others. Only the 43 mined frames
   have any result, and it is in-sample and from one cell (§2).
4. **Rule change after the checks (POST-HOC).** The first rule (v1) dropped 7 of the 10 frames that
   hold a d24 row: 11 of the 14 d24 rows among the candidates.
   - I revised it (v2) to keep all 10.
   - The d24 rows are kept as records. They are not used to rank frames, since each frame has 1 to 3.
   - v1 is saved next to v2 in `$CUR`.
5. **Every check passes.**
   - All 100 entries validate, and INDEX.json is current.
   - 1,000 sample fills (10 per frame, seed 7): all 1,000 pass `framelib.compat.structurally_ok` and
     all 1,000 pass the real `forge.runner.plan` closure.
   - The same 1,000 fills re-frame to their own frame and use fields that are in the catalogue.
   - No frame came up dead or short of fills.
   - The historic formulas pass the current gate too: 480 of 480 rows of the mined frames, and 57 of
     57 designer sample formulas.
6. **The sample fills are not the historic fills.**
   - The 43 mined frames were filled in history from 47 fields in 9 datasets.
   - Their library entries declare no slot constraints. So the filler draws from any field the gate
     admits.
   - Result: 0 of the 430 mined sample fills lie inside the historic pool. The frames' evidence does
     not cover such fills. This is the quant's open question Q1 (§5).
7. **Functions missing from the library (EX-ANTE axes, POST-HOC counts; §3):**
   - weighted-sum ensembles (the layered-era form);
   - dispersion and count/timing as the outer function;
   - two or more conditions in one frame;
   - group slots, which the gate cannot fill;
   - 42 of the 85 documented operators;
   - every cell except USA/EUR/GLB/ASI d1.
8. **Nothing is validated.** Moving any frame past `candidate` needs the live rounds of RULE 2 and
   Khoa's tick. The step-2 live-test sizing in doc 10 §6 (≥ 60 frames per arm) counts frames as
   independent clusters. Neither 43 nor 77 mined frames gives more than 34 shapes, so the sizing has
   to be redone (§2.4).

**Tóm tắt cho Khoa (tiếng Việt).**
- Thư viện có đúng 100 khung, trạng thái `candidate`: 43 khung khai thác từ lịch sử và 57 khung mới
  do designer thiết kế.
- 77 khung khai thác thực chất chỉ là 6 cấu trúc, được lặp lại với nhóm (industry/sector/subindustry)
  và cửa sổ khác nhau.
  - Tôi giữ mỗi hình dạng (shape) 1 khung, tức 34 khung, cộng thêm các khung từng có alpha qua đủ 7
    check (d24) và 1 khung để đủ 100.
  - Các khung bị bỏ chỉ khác khung được giữ ở cửa sổ.
- 57 khung mới chưa từng được sim. Đây là đầu vào của bước 1, chưa phải kết quả của bước 1.
- 1.000 fill mẫu đều qua cổng cấu trúc của forge. Nhưng fill mẫu của khung khai thác dùng field ngoài
  nhóm field lịch sử (0/430 fill nằm trong nhóm), nên bằng chứng cũ không áp dụng cho chúng.
- Còn thiếu các chức năng sau:
  - ensemble có trọng số;
  - khung dùng độ phân tán hoặc đếm/thời gian làm hàm ngoài cùng;
  - khung có nhiều điều kiện;
  - slot là nhóm;
  - 42 toán tử;
  - các ô ngoài d1 của USA/EUR/GLB/ASI.
- Chưa khung nào được xác nhận. Bước 2 cần vòng live trên VPS và Khoa tick (§6).

---

## 1. Inputs and build

| input | what | sha256 (first 12) | count |
|---|---|---|---|
| `docs/frames/10_frames_discovery.md` | the quant's doc | — | 0 frames. Its §5 writes families with a bare `$`, so the builder finds no spans. The architect reported the same. |
| `$SCRATCH/frames/quant/out/q4_candidates.csv` | the quant's per-frame list, which §5 points to | `267186e1782a` | 77 rows with candidate = True |
| `$SCRATCH/frames/designer/novel_frames.jsonl` | the designer's frames | `e8cdb27cfc10` | 57 lines |
| `$SCRATCH/frames/canonical/rows_framed.jsonl` | evidence source (FRAME SPEC v1) | `ffc469471c1f` | 66,058 rows |

- **Build.** `python3 -B -m framelib.build … --out $CUR/lib134 --now 2026-09-24T08:00:00+00:00` gives
  134 proposals → 134 entries, 0 errors: 77 mined and 57 novel.
  - Second way: the ids are the same 134 as in the architect's own scratch build (`architect/lib_all`).
- **Selection.** `$CUR/select.py` picks 100 of the 134 and saves them with `framelib.store.save`,
  which validates each entry, then writes INDEX.json with `store.write_index`.
  - Each entry is the builder's output byte for byte, except `notes`. `notes` says why the curator
    kept the frame.
  - The provenance still points to the original input files, their sha256 and their row or line.
- **Rebuild behaviour, EX-ANTE from `build.py` and measured by a dry run.** The builder never deletes,
  and it carries `notes` over. Rerunning the full build on `framelib/library` gives **100 unchanged
  + 34 new**. So a rebuild without a filter would bring back the 34 frames dropped here.

---

## 2. The mix: 43 mined + 57 novel, and why

### 2.1 Facts the choice rests on

| # | fact | label | how it was checked |
|---|---|---|---|
| F1 | The 77 mined candidates fall in 34 shapes. The shapes fall in 6 structures (the quant's families Q1–Q6), and shapes within a structure differ only in their group tokens. | EX-ANTE (texts) | Abstracting group tokens and slot numbers gives 6 classes. They match the quant's `q6_candidate_families.csv` string for string. |
| F2 | Frames of one shape differ only in their windows. The other constants (0.5 and 0 in Q2/Q3, 1 in Q1/Q4, 0 in Q5) are the same everywhere. | EX-ANTE (texts) | The tuple of non-window numbers is constant in all 34 of 34 shapes. |
| F3 | Frames of the same shape carry nearly the same score. Shuffling fills among frames of one shape keeps split-half r at 0.606 of 0.641 (way A) and 0.551 of 0.589 (way B). | POST-HOC. The quant's measurement (doc 10 §2.3), not re-derived here. | — |
| F4 | One submission removes its whole signal family: "464 rows of one mechanic = 26 gems but 1 submission". | POST-HOC. An earlier project measurement (memory note "submittable = distinct mechanics"), not re-derived here. | — |
| F5 | The 57 novel frames are 57 distinct shapes in 21 designer families. None of their frame keys, shapes or skeletons is in canonical. | EX-ANTE (designer's novelty check) | The builder produced 57 distinct ids. |
| F6 | Of the 77 candidates, 10 frames hold d24 rows: 14 rows, all in Q1, all at MONTH horizon, 1–3 rows per frame. | POST-HOC, in-sample | Counted from `rows_framed.jsonl`; matches the q4 column on 43 of 43 kept frames. |

How F3 enters the choice: given F3 (POST-HOC), the history barely tells a window variant apart
from the kept frame of its shape, while each novel frame adds a structure the library does not have
(F5). F3 is a regularity. Why same-shape frames score alike: **MECHANISM: UNKNOWN**.

### 2.2 The rule

Only v1 was fixed before the checks. v2 was written after them (§0 point 4).
- **Novel:** all 57.
- **Mined (a), 34 frames:** one per shape, the highest `eb_post` (the quant's empirical-Bayes
  posterior). Ties go to more fills, then to id.
- **Mined (b), 8 frames:** every other mined frame with at least one d24 row (F6). This was added in
  v2 because v1 dropped 7 of the 10 d24 frames (11 of 14 rows).
  - The d24 row counts are in-sample, and each frame has 1–3.
  - They are kept as the only full-pass records among the candidates, not as a ranking.
- **Mined (c), 1 frame:** `F3b9da4509541`, the top horizon contrast by `eb_post` among 19 shapes that
  have one. It is there only to reach 100; the number 1 is forced by the target.

In-sample, and only as a description (this is the data that selected the frames):

| | frames | USA/d1 rows | LOW_SHARPE pass | d24 |
|---|---|---|---|---|
| kept 43 | 43 | 452 | 163 | 14 |
| dropped 34 | 34 | 408 | 111 | 0 |

The kept row is counted twice and agrees: from the raw rows (`verify.py`) and from the q4 CSV. The
dropped IDs are listed in `$CUR/selection.json`.

### 2.3 Other mixes, and what they would buy

| mix | for | against |
|---|---|---|
| **43 + 57 (this one)** | Every mined shape and structure, every designer family, and every d24 record. | 57 frames have no simulated result, so step 1 read literally ("frames that simmed better") is not met for them. |
| 77 + 23 | Every frame with a history. Closest to step 1 as written. | 34 extra frames that differ from kept ones only in windows (F2, F3). It drops 34 designer structures, leaving about one frame per designer family. |
| 50/50 or anything else | — | No measurement picks the number. |

This choice is Khoa's to make (§6, question 1). No experiment separates these options. Only a live
round that compares arms can do that.

### 2.4 Consequence for the step-2 live test (EX-ANTE arithmetic on POST-HOC inputs)

Doc 10 §6 sizes each arm at about 320 fills in ≥ 60 frames. That uses a frame-level intraclass
correlation of 0.32, which treats frames as independent clusters.
- The mined candidates have 34 shapes in 6 structures (F1).
- Frames of one shape score alike (F3).

So the mined side gives at most 34 independent shape-clusters, with 43 frames or with all 77. The
sizing has to be redone with the shape, or the structure, as the cluster before any live round is
proposed.

---

## 3. Coverage: which functions are in, which are missing

The axes are the architect's taxonomy, which is EX-ANTE: each value is a function of the text. The
counts are POST-HOC counts of this library.

| axis | all 100 | mined 43 | novel 57 |
|---|---|---|---|
| combiner | SINGLE 38, PRODUCT 25, SWITCH 20, SPREAD 5, SUM 5, OTHER 3, RELATION 3, RATIO 1 | PRODUCT 25, SINGLE 18 | SINGLE 20, SWITCH 20, SPREAD 5, SUM 5, OTHER 3, RELATION 3, RATIO 1 |
| conditioning | IF_ELSE 48, NONE 44, TRADE_WHEN 8 | IF_ELSE 18, NONE 25 | IF_ELSE 30, NONE 19, TRADE_WHEN 8 |
| condition input | FIXED 48, NONE 44, SLOT 6, MIXED 2 | FIXED 18, NONE 25 | FIXED 30, NONE 19, SLOT 6, MIXED 2 |
| economic function (outermost) | LEVEL 94, CO_MOVEMENT 3, CHANGE 2, MIXED 1 | LEVEL 43 | LEVEL 51, CO_MOVEMENT 3, CHANGE 2, MIXED 1 |
| horizon | MONTH 30, YEAR 23, DAYS 16, QUARTER 16, NONE 14, MULTIYEAR 1 | MONTH 26, DAYS 14, YEAR 3 | YEAR 20, QUARTER 16, NONE 14, MONTH 4, DAYS 2, MULTIYEAR 1 |
| grouping | TOKEN 69, NONE 31 | TOKEN 43 | TOKEN 26, NONE 31 |
| slot contexts | MATRIX 191 slots, VECTOR 2 | MATRIX only | MATRIX + 2 VECTOR |
| turnover class (POST-HOC, per cell) | MID 32, HIGH 7, LOW 2, MIXED 2, UNKNOWN 57 | as left | UNKNOWN 57 (never simulated) |
| taxonomy families | 17 | 2 (PRODUCT.NONE.LEVEL 25, SINGLE.IF_ELSE.LEVEL 18) | 16 |
| cells (settings) | USA/d1 95, EUR/d1 2, GLB/d1 2, ASI/d1 1 | USA/d1 43 | USA/d1 52, EUR 2, GLB 2, ASI 1 |
| operators | 43 of the 85 in operators.json, none outside it | 11 (a subset of the novel set) | 43 |

The `economic_function` axis puts 94 of 100 frames in LEVEL, so it barely separates this set. The
architect saw the same on 134 frames. The source families separate the frames better.

**Source families covered.**
- **Quant structures, library / candidates:**
  - Q1 17/31: rank(spread) × (1 − rank(ratio));
  - Q2 9/22: 60-day call−put IV gate on a ranked mean;
  - Q3 9/15: the same with 30-day IV;
  - Q4 4/5: rank(backfilled mean) × (1 − rank(ratio));
  - Q5 3/3: three-leg product;
  - Q6 1/1: rank × rank(spread).
- **Designer families, all 21, as frames:**
  - segment-routing 6; market-regime 5; orthogonalize 5; price-state-trigger 5; event-window 4;
  - agreement 3; group-broadcast 3; tail-shaping 3; bucket-neutral 3;
  - trend-estimation 2; self-calibrating 2; flow-confirmation 2; event-dispersion 2; freshness 2;
    anchor-conditioned 2; option-regime 2; carrier-plus-gated-leg 2;
  - uncertainty-conditioned 1; turnover-shaping 1; seasonality 1; country-relative 1.
- **Checks the designer aims frames at (SPECULATION, the designer's label):**
  - LOW_SUB_UNIVERSE: NF11, NF18, NF49, NF51, NF56;
  - CONCENTRATED_WEIGHT: NF41, NF42;
  - HIGH_TURNOVER: NF40.

**Missing, with the reason each one is missing.** Each reason is a fact about the inputs, not a
judgement that the function is bad.

| missing | reason |
|---|---|
| WEIGHTED_SUM combiner (multi-leg ensembles, the layered-era form) | POST-HOC (doc 10 §0.6): all 712 layered-era d24 rows are in frames filled once. Such a frame has no within-frame variance, so it cannot be ranked or luck-tested and is never a candidate. The designer drew none. |
| MULTI conditioning (≥ 2 if_else / trade_when); a CONSTANT condition | No candidate or designer frame has one. |
| DISPERSION and COUNT_TIMING as the outermost function of a leg (ts_std_dev, ts_skewness, ts_entropy, ts_count_nans, ts_arg_max, days_from_last_change, …) | days_from_last_change (6 frames), ts_std_dev (2) and vec_count (1) appear, but in no frame is one of them the outermost function of a leg. |
| Group slots (grouping SLOT / BOTH) | EX-ANTE, from the architect's direct calls: structurally_ok refuses a data GROUP field in a group position, so no group slot can be filled under the current gate. |
| VECTOR slots, beyond 2 | Only NF32 and NF33 have a VECTOR slot; they use vec_avg, vec_count, vec_max and vec_min. EX-ANTE (designer and architect, from direct calls): the gate refuses vec_stddev and vec_range on every VECTOR field, so those two reducers cannot be used. vec_sum was not drawn. |
| 42 of 85 operators | Arithmetic: inverse, max, min, power, signed_power, sqrt. Cross-sectional: normalize, quantile, scale, vector_proj, winsorize. Group: group_backfill, group_cartesian_product, group_extra, group_mean, group_scale. Logical: and, or, not, not_equal, greater_equal, less_equal, is_nan. Special: inst_pnl. Time series: hump, kth_element, ts_arg_max, ts_arg_min, ts_av_diff, ts_count_nans, ts_covariance, ts_decay_linear, ts_entropy, ts_min_diff, ts_min_max_cps, ts_min_max_diff, ts_product, ts_scale, ts_skewness. Vector: vec_range, vec_stddev, vec_sum. Some are refused by the gate (group_mean, group_cartesian_product, group_extra, inst_pnl, vec_stddev and vec_range on VECTOR fields; designer §12, EX-ANTE); the rest were simply not drawn. |
| Cells: JPN, CHN, IND, any d0, EUR/GLB/ASI beyond 5 novel frames | POST-HOC (doc 10 §1): every forge cell other than USA/d1 had 0 LOW_SHARPE passes, so no mined frame exists there. The 5 novel non-USA frames have no evidence either. |
| Mined frames outside 9 datasets and 11 operators | POST-HOC: the historic fills of the 43 mined frames use 47 fields in 9 datasets: continuation_score, fundamental6, insider_agg_matrix, news46, news_sentiment_transfer, option3, option8, twitter_sentiment_l2, us_short_sale. |

---

## 4. Checks (each number two ways where a second way exists)

| check | result | second way |
|---|---|---|
| Every entry validates (`schema.validate`), file name = id, INDEX.json current | `python3 -B -m framelib.store` → 100 files, 0 invalid | `store.load` inside `verify.py` raises on any problem; it did not |
| Library = the selection | `diff -r` of `$CUR/lib100` (written by the same script) against `framelib/library`: identical except the pre-existing `.gitkeep` | — |
| framelib test suite with the library filled | `pytest framelib/tests`: 115 passed | — |
| Sample fills (10 per frame, seed 7, `by="dataset"`, each frame in its own cell) | 1,000 fills; 0 dead frames; 0 frames short of 10 | — |
| … pass structurally_ok | 1,000 / 1,000 via `framelib.compat.structurally_ok` (framelib's label records) | 1,000 / 1,000 via the **real closure** taken from `forge.runner.plan`, bound to `forge.labels.load`. That is the gate forge applies before a simulation. Refusal counter: empty. |
| … re-frame to their own frame (key and fill) | 1,000 / 1,000 | — |
| … use fields present in the cell's catalogue | 1,000 / 1,000 | — |
| Draws rejected on the way to 1,000 | 165: "$4 no compatible field given the earlier slots" 117, "$3 …" 30, "$5 …" 15, repeated field 2, duplicate 1 | — |
| Determinism | Same seed, fresh library object, second run: `samples.jsonl` and the per-frame report are byte-identical | — |
| Historic formulas of the 43 mined frames under today's gate | 480 / 480 rows (452 USA/d1 + 28 USA/d0) pass the real closure | — |
| Designer sample formulas | 57 / 57 pass the real closure | The designer's own two routes (57/57) |
| Evidence, USA/d1 rows, fills, LOW_SHARPE PASS, d24 per mined frame | recounted from `rows_framed.jsonl`: equal to the q4 CSV on 43 / 43 for each of the four | equal to the entry's evidence block on 43 / 43, per cell |

**One of my own counts was wrong first (RULE 0.5).** The first recount, on the v1 selection, gave
rows ≠ q4 on 15 frames and fills ≠ q4 on 4. The cause was in my counting, not in the data: I had pooled the frame's rows
across cells. 12 of the 43 kept frames also ran in USA/d0 (28 rows, 0 LOW_SHARPE passes against the
2.69 bar). The q4 CSV counts USA/d1 only. Counted per cell, every number matches. The USA/d0 rows
appear in the evidence column as a separate cell.

---

## 5. What the sample fills are, and what they are not

- **Mined frames declare no slot constraints.** EX-ANTE, from `framelib/build.py`: the builder takes
  slot roles and constraints only from the designer's file, never from the discovery CSV. So for a
  mined frame the filler draws from every field the gate admits.
  - Measured: 0 of the 430 mined sample fills lie entirely inside the 47-field historic pool; 5 touch
    it at all.
  - Example (frame 1): in history, `$1−$2` was call IV − put IV or a bullish − bearish pattern score.
    In the sample it is `anl11_empposcorregsubsecperc − min_similarity_continuation_v_bottom`.
- **What that means.** The mined frames' POST-HOC evidence covers their historic role pools only, and
  those pools were near-synonyms (doc 10 §0.3). Whether the evidence holds for gate-legal fields from
  other roles is doc 10's Q1, and it is untested. The sample fills show that the frames are
  structurally fillable. They say nothing about performance.
- **Adding constraints by hand is not a curator edit.** EX-ANTE, from `build.py`: on a rebuild the
  builder copies only status, status_history, approval and notes from an existing entry. Hand-written
  slot constraints would be replaced and the version bumped. Giving mined frames role pools means
  changing the builder (for example, reading them from the historic fills), and that is Khoa's call
  (§6, question 2).
- **Novel frames:** 77 of their slots carry the designer's constraints (kind, unit, domain, …). All 57
  frames have at least one constrained slot. Their samples follow those constraints.

---

## 6. Decisions for Khoa (to be put as tick questions; I did not ask them)

1. **Mix.**
   - (A) 43 mined + 57 novel: this library.
   - (B) 77 mined + 23 novel: every frame with a history, one novel frame per designer family plus 2.
   - (C) Another split.
2. **Slot pools for mined frames in step 2.**
   - (A) Historic role pools only (47 fields, 9 datasets): doc 10 arm (a).
   - (B) Any gate-legal field: today's filler, doc 10 arm (b).
   - (C) Both, as separate arms.

   (A) and (C) need a builder change.
3. **d24 records.**
   - (A) Keep rule v2: the 8 extra d24 frames.
   - (B) Go back to v1: 9 horizon contrasts, which drops 11 of the 14 d24 rows.
4. **The 5 non-USA novel frames** (NF39, NF54, NF55, NF56, NF57), in cells where forge had 0
   LOW_SHARPE passes.
   - (A) Keep them in round 1.
   - (B) Defer them.
5. **The step-2 sizing:** redo it with the shape or the structure as the cluster (§2.4) before any live
   round is proposed.

Status of the mechanism under RULE 2: the frame library is an open item. It has not passed gates 3–4
(proof across many live rounds against an arm without it, and solving the stated problem). No entry
can be `validated` until those rounds exist, `MIN_ROUNDS` is set by Khoa, and he ticks.

---

## 7. The 100 frames

Order: mined frames by quant structure and `eb_post`, then novel frames by designer id. The id is
the library id (`framelib/library/frames/<id>.json`). The full frame texts are in Appendix A.

**Function column.**
- Mined frames use shorthand, EX-ANTE from the text:
  - `rk[g](x)` = group_rank(x, g), with g one of ind / sec / subind;
  - `meanN` = ts_mean over N days; `sumN` = ts_sum; `tsrankN` = ts_rank; `backfillN` = ts_backfill;
  - `IVcall60 − IVput60` = the pinned fields implied_volatility_call_60 − implied_volatility_put_60.
- Novel frames use the designer's function line verbatim (the designer labels "computes" EX-ANTE and
  every rationale SPECULATION).

**Family column.** The library taxonomy family, then the source family: Q1–Q6 for mined frames (§3),
the designer family for novel ones.

**Provenance column.**
- `rep` = representative of its shape;
- `d24-record, shape of X` = kept under rule (b), in the same shape as representative X;
- `horizon contrast→X` = rule (c).

**Evidence column: mined** (all POST-HOC, in-sample: these rows selected the frame; caveats C1–C4
of `framelib/evidence.py` apply).
- `USA/d1 f fills · r rows`: its canonical rows in the quant's cell.
- `LS pass`: rows with LOW_SHARPE PASS.
- `d24`: rows passing all 7 binding checks.
- `EB m±s`: the quant's posterior of sharpe/limit under the eligible-frame prior (cell μ 0.542).
- `p`: the quant's Monte Carlo luck p-value (criterion C1, before FDR).
- `LOFO k/s`: partitions in which the frame was evaluable on unseen fields / share with its test fills
  above the test mean. It is not calibrated by a null (doc 10 §5); `–` means not evaluable.
- `tvr`: median turnover of its USA/d1 rows.
- `USA/d0 …`: rows in another cell.
- `gate 10/10`: the curator's sample fills passing the real forge closure.

**Evidence column: novel.**
- `none (never simulated)`.
- `gate`: the curator's 10 sample fills; `designer 60/60`: the designer's random fills.
- `judge`: the full typed judge on the designer's sample fill. It is stricter than the gate and only
  informational:
  - H6 = orientation undefined, including frames that flip sign by design;
  - H5 = returns or close carry no stated sign;
  - H4 = an annual field without backfill.
- The cell.
- `spec-v1 divergence`: NF01 and NF03 reuse the earnings clock in trade_when's exit, so their canonical
  key has one more slot than the design.

| # | id | function (EX-ANTE: what it computes) | family (library · source) | provenance | evidence |
|---|---|---|---|---|---|
| 1 | `Fb5b3aef4138a` | rk[ind](mean5($1−$2)) × (1 − rk[sec](mean10($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 2 · rep | USA/d1 5 fills · 10 rows · LS pass 8 · d24 0 · EB 0.90±0.07 · p 1e-05 · LOFO – · tvr 0.1678 · gate 10/10 |
| 2 | `F066d4521eacf` | rk[sec](mean5($1−$2)) × (1 − rk[ind](mean5($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 3 · rep | USA/d1 4 fills · 8 rows · LS pass 2 · d24 0 · EB 0.87±0.07 · p 2e-05 · LOFO – · tvr 0.1731 · gate 10/10 |
| 3 | `Fcc903fa0fc8a` | rk[ind](mean5($1−$2)) × (1 − rk[subind](mean10($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 4 · rep | USA/d1 5 fills · 7 rows · LS pass 3 · d24 0 · EB 0.87±0.07 · p 2e-05 · LOFO – · tvr 0.1825 · gate 10/10 |
| 4 | `Ff9dcf8d23b62` | rk[ind](mean5($1−$2)) × (1 − rk[ind](mean5($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 7 · rep | USA/d1 6 fills · 12 rows · LS pass 5 · d24 0 · EB 0.84±0.06 · p 2e-05 · LOFO – · tvr 0.1729 · gate 10/10 |
| 5 | `F4656fef93d5f` | rk[sec](mean5($1−$2)) × (1 − rk[sec](mean5($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 15 · rep | USA/d1 10 fills · 13 rows · LS pass 5 · d24 0 · EB 0.81±0.05 · p 1e-05 · LOFO 36/86% · tvr 0.1787 · gate 10/10 |
| 6 | `F90584e714637` | rk[sec](mean5($1−$2)) × (1 − rk[subind](mean20($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 20 · rep | USA/d1 5 fills · 11 rows · LS pass 3 · d24 1 · EB 0.80±0.07 · p 4e-04 · LOFO – · tvr 0.1413 · gate 10/10 |
| 7 | `F73ae8ae60d31` | rk[sec](mean10($1−$2)) × (1 − rk[sec](mean10($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 21 · d24-record, shape of F4656fef93d5f | USA/d1 4 fills · 7 rows · LS pass 4 · d24 1 · EB 0.79±0.07 · p 9e-04 · LOFO – · tvr 0.1404 · gate 10/10 |
| 8 | `Fac8049da8f31` | rk[sec](mean10($1−$2)) × (1 − rk[subind](mean5($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 22 · d24-record, shape of F90584e714637 | USA/d1 7 fills · 11 rows · LS pass 4 · d24 1 · EB 0.79±0.06 · p 1e-04 · LOFO – · tvr 0.1436 · gate 10/10 |
| 9 | `F9b677a9ff6ea` | rk[subind](mean10($1−$2)) × (1 − rk[subind](mean5($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 36 · rep | USA/d1 7 fills · 11 rows · LS pass 4 · d24 1 · EB 0.78±0.06 · p 3e-04 · LOFO 8/100% · tvr 0.1502 · gate 10/10 |
| 10 | `F467b95837848` | rk[subind](mean10($1−$2)) × (1 − rk[subind](mean20($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 41 · d24-record, shape of F9b677a9ff6ea | USA/d1 4 fills · 9 rows · LS pass 3 · d24 1 · EB 0.77±0.07 · p 2e-03 · LOFO – · tvr 0.1232 · gate 10/10 |
| 11 | `F9279ac781c9b` | rk[subind](mean5($1−$2)) × (1 − rk[ind](mean20($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 47 · rep | USA/d1 11 fills · 21 rows · LS pass 6 · d24 0 · EB 0.76±0.05 · p 8e-05 · LOFO 26/96% · tvr 0.1405 · gate 10/10 |
| 12 | `F3e1b26968a4e` | rk[sec](mean10($1−$2)) × (1 − rk[ind](mean20($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 52 · d24-record, shape of F066d4521eacf | USA/d1 4 fills · 8 rows · LS pass 2 · d24 1 · EB 0.76±0.07 · p 3e-03 · LOFO – · tvr 0.1235 · gate 10/10 |
| 13 | `F2ac6c8193251` | rk[subind](mean10($1−$2)) × (1 − rk[sec](mean10($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 54 · rep | USA/d1 5 fills · 12 rows · LS pass 4 · d24 0 · EB 0.76±0.07 · p 2e-03 · LOFO – · tvr 0.1285 · gate 10/10 |
| 14 | `Fba81db302090` | rk[ind](mean10($1−$2)) × (1 − rk[subind](mean5($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 57 · d24-record, shape of Fcc903fa0fc8a | USA/d1 5 fills · 12 rows · LS pass 4 · d24 2 · EB 0.75±0.07 · p 3e-03 · LOFO – · tvr 0.1477 · gate 10/10 |
| 15 | `F589c0bcb31a6` | rk[sec](mean5($1−$2)) × (1 − rk[sec](mean20($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 62 · d24-record, shape of F4656fef93d5f | USA/d1 5 fills · 10 rows · LS pass 3 · d24 2 · EB 0.75±0.07 · p 3e-03 · LOFO – · tvr 0.1141 · gate 10/10 |
| 16 | `F4cc0ec931f03` | rk[subind](mean10($1−$2)) × (1 − rk[sec](mean20($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 71 · d24-record, shape of F2ac6c8193251 | USA/d1 6 fills · 14 rows · LS pass 6 · d24 3 · EB 0.73±0.06 · p 4e-03 · LOFO – · tvr 0.1202 · gate 10/10 |
| 17 | `F1861b442e931` | rk[subind](mean10($1−$2)) × (1 − rk[sec](mean5($3/$4))) | PRODUCT.NONE.LEVEL · Q1 | mined · q4_candidates.csv row 72 · d24-record, shape of F2ac6c8193251 | USA/d1 9 fills · 20 rows · LS pass 4 · d24 1 · EB 0.73±0.05 · p 1e-03 · LOFO 62/100% · tvr 0.1411 · gate 10/10 |
| 18 | `Fc16b45d541e3` | if rk[subind](mean5(IVcall60−IVput60)) > 0.5: rk[ind](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 6 · rep | USA/d1 7 fills · 12 rows · LS pass 8 · d24 0 · EB 0.85±0.06 · p 1e-05 · LOFO 136/100% · tvr 0.272 · gate 10/10 |
| 19 | `F30846af33819` | if rk[subind](mean5(IVcall60−IVput60)) > 0.5: rk[sec](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 12 · rep | USA/d1 6 fills · 7 rows · LS pass 5 · d24 0 · EB 0.82±0.06 · p 8e-05 · LOFO – · tvr 0.2488 · USA/d0 6 rows, 0 pass · gate 10/10 |
| 20 | `Fa223ada10703` | if rk[sec](mean5(IVcall60−IVput60)) > 0.5: rk[ind](mean5($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 16 · rep | USA/d1 8 fills · 13 rows · LS pass 5 · d24 0 · EB 0.81±0.06 · p 2e-05 · LOFO 239/100% · tvr 0.3228 · USA/d0 2 rows, 0 pass · gate 10/10 |
| 21 | `F6f1e11f44ba3` | if rk[sec](mean5(IVcall60−IVput60)) > 0.5: rk[sec](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 18 · rep | USA/d1 5 fills · 6 rows · LS pass 3 · d24 0 · EB 0.80±0.07 · p 3e-04 · LOFO – · tvr 0.2329 · gate 10/10 |
| 22 | `F0d3e65f27080` | if rk[ind](mean5(IVcall60−IVput60)) > 0.5: rk[sec](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 19 · rep | USA/d1 8 fills · 14 rows · LS pass 3 · d24 0 · EB 0.80±0.06 · p 4e-05 · LOFO 234/100% · tvr 0.2676 · USA/d0 1 rows, 0 pass · gate 10/10 |
| 23 | `Fc458fc433207` | if rk[sec](mean5(IVcall60−IVput60)) > 0.5: rk[subind](mean5($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 23 · rep | USA/d1 7 fills · 12 rows · LS pass 4 · d24 0 · EB 0.79±0.06 · p 1e-04 · LOFO 115/100% · tvr 0.2901 · USA/d0 1 rows, 0 pass · gate 10/10 |
| 24 | `F6da9d7a16f9e` | if rk[subind](mean5(IVcall60−IVput60)) > 0.5: rk[subind](mean3($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 28 · rep | USA/d1 5 fills · 7 rows · LS pass 5 · d24 0 · EB 0.79±0.07 · p 7e-04 · LOFO 198/100% · tvr 0.4129 · gate 10/10 |
| 25 | `Faa8883d32a0b` | if rk[ind](mean5(IVcall60−IVput60)) > 0.5: rk[ind](mean5($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 38 · rep | USA/d1 8 fills · 15 rows · LS pass 1 · d24 0 · EB 0.78±0.06 · p 2e-04 · LOFO 239/100% · tvr 0.3178 · USA/d0 2 rows, 0 pass · gate 10/10 |
| 26 | `Ffd345db42f35` | if rk[ind](mean5(IVcall60−IVput60)) > 0.5: rk[subind](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q2 | mined · q4_candidates.csv row 63 · rep | USA/d1 5 fills · 6 rows · LS pass 1 · d24 0 · EB 0.75±0.07 · p 3e-03 · LOFO 108/100% · tvr 0.2795 · USA/d0 2 rows, 0 pass · gate 10/10 |
| 27 | `Fb47d32662b9a` | if rk[ind](mean5(IVcall30−IVput30)) > 0.5: rk[ind](mean3($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 8 · rep | USA/d1 6 fills · 9 rows · LS pass 6 · d24 0 · EB 0.83±0.06 · p 4e-05 · LOFO 226/100% · tvr 0.4281 · gate 10/10 |
| 28 | `Ffb6c4f50947f` | if rk[ind](mean5(IVcall30−IVput30)) > 0.5: rk[sec](mean5($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 11 · rep | USA/d1 9 fills · 17 rows · LS pass 7 · d24 0 · EB 0.82±0.05 · p 2e-05 · LOFO 227/100% · tvr 0.3424 · USA/d0 2 rows, 0 pass · gate 10/10 |
| 29 | `Fef466309a133` | if rk[sec](mean5(IVcall30−IVput30)) > 0.5: rk[sec](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 17 · rep | USA/d1 7 fills · 12 rows · LS pass 6 · d24 0 · EB 0.81±0.06 · p 8e-05 · LOFO 198/100% · tvr 0.2918 · USA/d0 5 rows, 0 pass · gate 10/10 |
| 30 | `F4b4fb591b1e4` | if rk[subind](mean5(IVcall30−IVput30)) > 0.5: rk[ind](mean5($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 24 · rep | USA/d1 6 fills · 9 rows · LS pass 5 · d24 0 · EB 0.79±0.06 · p 3e-04 · LOFO – · tvr 0.3368 · USA/d0 2 rows, 0 pass · gate 10/10 |
| 31 | `F02987d813aed` | if rk[subind](mean5(IVcall30−IVput30)) > 0.5: rk[sec](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 25 · rep | USA/d1 4 fills · 7 rows · LS pass 4 · d24 0 · EB 0.79±0.07 · p 1e-03 · LOFO – · tvr 0.2941 · gate 10/10 |
| 32 | `Fd39b2833c3c6` | if rk[subind](mean5(IVcall30−IVput30)) > 0.5: rk[subind](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 31 · rep | USA/d1 9 fills · 12 rows · LS pass 4 · d24 0 · EB 0.78±0.05 · p 7e-05 · LOFO 237/100% · tvr 0.2818 · gate 10/10 |
| 33 | `F7f09a7cb01a7` | if rk[ind](mean5(IVcall30−IVput30)) > 0.5: rk[subind](mean5($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 45 · rep | USA/d1 7 fills · 10 rows · LS pass 4 · d24 0 · EB 0.77±0.06 · p 4e-04 · LOFO 113/100% · tvr 0.3474 · USA/d0 1 rows, 0 pass · gate 10/10 |
| 34 | `F4f6ae9c88031` | if rk[sec](mean5(IVcall30−IVput30)) > 0.5: rk[ind](mean3($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 50 · rep | USA/d1 4 fills · 8 rows · LS pass 4 · d24 0 · EB 0.76±0.07 · p 3e-03 · LOFO 91/100% · tvr 0.4163 · gate 10/10 |
| 35 | `Ff632191d6dd4` | if rk[sec](mean5(IVcall30−IVput30)) > 0.5: rk[subind](mean10($1)), else 0 | SINGLE.IF_ELSE.LEVEL · Q3 | mined · q4_candidates.csv row 69 · rep | USA/d1 7 fills · 10 rows · LS pass 1 · d24 0 · EB 0.73±0.06 · p 2e-03 · LOFO 193/100% · tvr 0.2658 · USA/d0 1 rows, 0 pass · gate 10/10 |
| 36 | `F6282cce63c38` | rk[subind](mean5(backfill5($1))) × (1 − rk[subind](mean10($2/$3))) | PRODUCT.NONE.LEVEL · Q4 | mined · q4_candidates.csv row 5 · rep | USA/d1 4 fills · 8 rows · LS pass 5 · d24 0 · EB 0.87±0.07 · p 2e-05 · LOFO 155/100% · tvr 0.2045 · gate 10/10 |
| 37 | `F79fc7c57ee17` | rk[subind](mean5(backfill5($1))) × (1 − rk[ind](mean5($2/$3))) | PRODUCT.NONE.LEVEL · Q4 | mined · q4_candidates.csv row 9 · rep | USA/d1 4 fills · 5 rows · LS pass 2 · d24 0 · EB 0.82±0.07 · p 2e-04 · LOFO 155/100% · tvr 0.2775 · gate 10/10 |
| 38 | `F3c74db484f58` | rk[ind](mean5(backfill5($1))) × (1 − rk[ind](mean5($2/$3))) | PRODUCT.NONE.LEVEL · Q4 | mined · q4_candidates.csv row 14 · rep | USA/d1 4 fills · 11 rows · LS pass 3 · d24 0 · EB 0.81±0.07 · p 4e-04 · LOFO 155/100% · tvr 0.2572 · gate 10/10 |
| 39 | `F3b9da4509541` | rk[ind](mean5(backfill5($1))) × (1 − rk[ind](mean20($2/$3))) | PRODUCT.NONE.LEVEL · Q4 | mined · q4_candidates.csv row 26 · horizon contrast→F3c74db484f58 | USA/d1 4 fills · 8 rows · LS pass 3 · d24 0 · EB 0.79±0.07 · p 1e-03 · LOFO 155/100% · tvr 0.2154 · gate 10/10 |
| 40 | `Fa22e41a552e8` | rk[sec](sum60($1, NaN→0)) × rk[subind](mean20($2−$3)) × rk[ind](tsrank126($4/$5)) | PRODUCT.NONE.LEVEL · Q5 | mined · q4_candidates.csv row 10 · rep | USA/d1 4 fills · 5 rows · LS pass 1 · d24 0 · EB 0.82±0.07 · p 2e-04 · LOFO – · tvr 0.0974 · gate 10/10 |
| 41 | `Fd53091ea0b53` | rk[ind](sum20($1, NaN→0)) × rk[sec](mean10($2−$3)) × rk[ind](tsrank126($4/$5)) | PRODUCT.NONE.LEVEL · Q5 | mined · q4_candidates.csv row 42 · rep | USA/d1 5 fills · 6 rows · LS pass 1 · d24 0 · EB 0.77±0.07 · p 1e-03 · LOFO – · tvr 0.1095 · gate 10/10 |
| 42 | `F3aa9bc7acdd6` | rk[ind](sum60($1, NaN→0)) × rk[sec](mean10($2−$3)) × rk[subind](tsrank252($4/$5)) | PRODUCT.NONE.LEVEL · Q5 | mined · q4_candidates.csv row 44 · rep | USA/d1 4 fills · 5 rows · LS pass 0 · d24 0 · EB 0.77±0.07 · p 2e-03 · LOFO – · tvr 0.0928 · gate 10/10 |
| 43 | `F0a1a4543f44e` | rk[ind](mean10($1)) × rk[sec](mean5($2−$3)) | PRODUCT.NONE.LEVEL · Q6 | mined · q4_candidates.csv row 78 · rep | USA/d1 13 fills · 22 rows · LS pass 2 · d24 0 · EB 0.68±0.05 · p 3e-03 · LOFO 192/100% · tvr 0.2454 · USA/d0 3 rows, 0 pass · gate 10/10 |
| 44 | `F218ba3275a27` | event-window drift: refresh a quarterly change within 3 days of the earnings release, hold, go flat after day 60 | SINGLE.TRADE_WHEN.CHANGE · event-window | novel · novel_frames.jsonl line 1 (NF01) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 · spec-v1 divergence |
| 45 | `Ffa3625746f8e` | pre-announcement emphasis: full weight on a predicted-surprise score in the last weeks before the next release, half weight otherwise | SWITCH.IF_ELSE.LEVEL · event-window | novel · novel_frames.jsonl line 2 (NF02) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 46 | `F5c09fdbbd596` | earnings-announcement-return drift: enter on the 2-day announcement move the day after the release, exit after day 60 | SINGLE.TRADE_WHEN.LEVEL · event-window | novel · novel_frames.jsonl line 3 (NF03) | none (never simulated) · gate 10/10 + designer 60/60 · judge H5 · USA/d1 · spec-v1 divergence |
| 47 | `F0ec368224298` | post-release emphasis: an industry-relative fundamental level at full weight in the 20 days after the release, half weight later | SWITCH.IF_ELSE.LEVEL · event-window | novel · novel_frames.jsonl line 4 (NF04) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 48 | `Fc5e731809311` | market-trend sign switch: ride the signal after a 120-day market rise, fade it after a fall | SWITCH.IF_ELSE.LEVEL · market-regime | novel · novel_frames.jsonl line 5 (NF05) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 49 | `F7abfda17cb67` | market-volatility leg switch: a defensive leg when 20-day market vol is above its 250-day mean, an offensive leg otherwise | SWITCH.IF_ELSE.LEVEL · market-regime | novel · novel_frames.jsonl line 6 (NF06) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 50 | `F946abbd10f3e` | cross-sectional dispersion leg switch: a stock-specific leg when return dispersion across stocks is high, a slow leg otherwise | SWITCH.IF_ELSE.LEVEL · market-regime | novel · novel_frames.jsonl line 7 (NF07) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 51 | `F9a18b421bbab` | breadth sign switch: ride the signal when most stocks rose over 20 days, fade it otherwise | SWITCH.IF_ELSE.LEVEL · market-regime | novel · novel_frames.jsonl line 8 (NF08) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 52 | `F7daa9fbe65e4` | beta-orthogonal peer-relative signal: industry z-score with its projection on a beta loading removed | RELATION.NONE.LEVEL · orthogonalize | novel · novel_frames.jsonl line 9 (NF09) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 53 | `F78a3802f05f8` | style-purified signal: two style loadings projected out in sequence | RELATION.NONE.LEVEL · orthogonalize | novel · novel_frames.jsonl line 10 (NF10) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 54 | `Fa4e48379e71d` | size-residual signal: cross-sectional regression on log size, keep the residual | SPREAD.NONE.LEVEL · orthogonalize | novel · novel_frames.jsonl line 11 (NF11) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 55 | `F571f621e1220` | idiosyncratic field deviation: time-series residual of a field on its own industry mean | RELATION.NONE.CO_MOVEMENT · orthogonalize | novel · novel_frames.jsonl line 12 (NF12) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 56 | `F2ce52853bc80` | fundamental-implied valuation residual: valuation minus what profitability predicts across stocks | SPREAD.NONE.LEVEL · orthogonalize | novel · novel_frames.jsonl line 13 (NF13) | none (never simulated) · gate 10/10 + designer 60/60 · judge H4 · USA/d1 |
| 57 | `F19147c0a90d0` | standardized trend slope of a slow field (regression on a day counter) | SINGLE.NONE.CO_MOVEMENT · trend-estimation | novel · novel_frames.jsonl line 14 (NF14) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 58 | `F6e8b1b710304` | trend-quality gate: trade the slope only where the fit R-squared is in the top half | SINGLE.IF_ELSE.CO_MOVEMENT · trend-estimation | novel · novel_frames.jsonl line 15 (NF15) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 59 | `F2acae07a0528` | self-calibrating sign: use the field long or short as its own trailing 250-day correlation with next-day returns says | SWITCH.IF_ELSE.LEVEL · self-calibrating | novel · novel_frames.jsonl line 16 (NF16) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 60 | `F726b20a89951` | industry-pooled self-calibrating sign: the sign comes from the industry-mean trailing correlation | SWITCH.IF_ELSE.LEVEL · self-calibrating | novel · novel_frames.jsonl line 17 (NF17) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 61 | `F73facd31adf9` | size-segment routing: one leg for the largest 30% of names, another for the rest | SWITCH.IF_ELSE.LEVEL · segment-routing | novel · novel_frames.jsonl line 18 (NF18) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 62 | `F90ea5e89399f` | coverage-segment routing: a revision leg where many analysts estimate EPS, a fundamental leg where few do | SWITCH.IF_ELSE.LEVEL · segment-routing | novel · novel_frames.jsonl line 19 (NF19) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 63 | `F27b013044905` | volatility-dependent sign: fade the signal in the top-third most volatile names, ride it elsewhere | SWITCH.IF_ELSE.LEVEL · segment-routing | novel · novel_frames.jsonl line 20 (NF20) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 64 | `F97dee83dead1` | short-crowding filter: stand aside (neutral 0.5) where the short-interest rank is above 80 | SINGLE.IF_ELSE.LEVEL · segment-routing | novel · novel_frames.jsonl line 21 (NF21) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 65 | `Fc4515145fc41` | neglect emphasis: full weight in the bottom 30% institutional ownership, half weight elsewhere | SWITCH.IF_ELSE.LEVEL · segment-routing | novel · novel_frames.jsonl line 22 (NF22) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 66 | `F077e2cb6ed0b` | two-view consensus: trade the combined rank of two views only where both sit on the same side of their medians, neutral where they disagree | SUM.IF_ELSE.LEVEL · agreement | novel · novel_frames.jsonl line 23 (NF23) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 67 | `F83220be66e3e` | multi-horizon trend agreement: trade the 60-day change only where the 5-day change has the same sign | SINGLE.IF_ELSE.CHANGE · agreement | novel · novel_frames.jsonl line 24 (NF24) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 68 | `F6cd9e1d1107c` | divergence-triggered convergence: reposition only when a fundamental view and 120-day price performance disagree by more than half the cross-section | SPREAD.TRADE_WHEN.LEVEL · agreement | novel · novel_frames.jsonl line 25 (NF25) | none (never simulated) · gate 10/10 + designer 60/60 · judge H5 · USA/d1 |
| 69 | `F1796d81631e5` | attention-confirmed update: refresh an information signal only on days volume exceeds 1.5x its 20-day average | SINGLE.TRADE_WHEN.LEVEL · flow-confirmation | novel · novel_frames.jsonl line 26 (NF26) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 70 | `Fbba079cb8335` | neglect-conditioned emphasis: full weight when 5-day volume runs below 0.7x the 20-day average, half weight otherwise | SWITCH.IF_ELSE.LEVEL · flow-confirmation | novel · novel_frames.jsonl line 27 (NF27) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 71 | `F19ef9670687d` | shock-day re-evaluation: refresh a valuation signal only on days the stock moves more than 2 sigma | SINGLE.TRADE_WHEN.LEVEL · price-state-trigger | novel · novel_frames.jsonl line 28 (NF28) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 72 | `Ff84a3e6605aa` | quiet-day update: refresh a signal only on days the stock's move is under 0.5 sigma | SINGLE.TRADE_WHEN.LEVEL · price-state-trigger | novel · novel_frames.jsonl line 29 (NF29) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 73 | `F4da2c812b764` | per-stock vol-expansion sign switch: fade the signal when 20-day vol exceeds 120-day vol, ride it otherwise | SWITCH.IF_ELSE.LEVEL · price-state-trigger | novel · novel_frames.jsonl line 30 (NF30) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 74 | `F2a9a6e94d8e8` | idiosyncratic-name emphasis: full weight where the 60-day correlation with the equal-weight market is under 0.3 | SWITCH.IF_ELSE.LEVEL · price-state-trigger | novel · novel_frames.jsonl line 31 (NF31) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 75 | `F805d739c54f2` | event-agreement gate: trade the average of an event stream only where the spread of its event values (max - min) is below the median | SINGLE.IF_ELSE.LEVEL · event-dispersion | novel · novel_frames.jsonl line 32 (NF32) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 76 | `F04bbee8ae111` | news-surge repositioning: refresh on the tone of an event stream when the 5-day news-item count is 2 sigma above its 60-day norm | SINGLE.TRADE_WHEN.LEVEL · event-dispersion | novel · novel_frames.jsonl line 33 (NF33) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 77 | `Fd0896b7b9062` | low-uncertainty revision: trade an estimate's 120-day z-score only where analyst dispersion is below median | SINGLE.IF_ELSE.LEVEL · uncertainty-conditioned | novel · novel_frames.jsonl line 34 (NF34) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 78 | `Fb2d1899db078` | self-clocked freshness: full weight for 10 days after the field's own last change, half weight afterwards | SWITCH.IF_ELSE.LEVEL · freshness | novel · novel_frames.jsonl line 35 (NF35) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 79 | `F976eee838986` | update-size yield: the size of the last change in a quarterly currency item, scaled by market value | RATIO.NONE.MIXED · freshness | novel · novel_frames.jsonl line 36 (NF36) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 80 | `Fb6da2bec8da1` | industry rotation: rank industries by the mean standardized fundamental of their members | SPREAD.NONE.LEVEL · group-broadcast | novel · novel_frames.jsonl line 37 (NF37) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 81 | `Fd8628f66fb1c` | own + peer two-leg: industry-mean leg plus 0.6 x within-industry deviation leg | SUM.NONE.LEVEL · group-broadcast | novel · novel_frames.jsonl line 38 (NF38) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 82 | `Fe70d906fee51` | sector rotation: rank sectors by the mean 250-day z-score of a fundamental across their members | SPREAD.NONE.LEVEL · group-broadcast | novel · novel_frames.jsonl line 39 (NF39) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · EUR/d1 |
| 83 | `Fa241acdc0590` | turnover-targeted fast signal: a subindustry rank of a 20-day z-score run through ts_target_tvr_decay at target 0.15 | SINGLE.NONE.LEVEL · turnover-shaping | novel · novel_frames.jsonl line 40 (NF40) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 84 | `F633a72402d22` | anti-concentration soft cap: sigmoid of an industry z-score keeps some magnitude but bounds the tails | SINGLE.NONE.LEVEL · tail-shaping | novel · novel_frames.jsonl line 41 (NF41) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 85 | `F71afd8265279` | outlier-robust time surprise: tanh of a 60-day z-score, then subindustry de-meaned | SINGLE.NONE.LEVEL · tail-shaping | novel · novel_frames.jsonl line 42 (NF42) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 86 | `F5610a8b920c5` | gaussianized time percentile: 250-day ts_quantile, then industry z-score | SINGLE.NONE.LEVEL · tail-shaping | novel · novel_frames.jsonl line 43 (NF43) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 87 | `Fd9c39249ee55` | annual same-month seasonality: sum of the field over the matching 21-day windows one and two years back | SUM.NONE.LEVEL · seasonality | novel · novel_frames.jsonl line 44 (NF44) | none (never simulated) · gate 10/10 + designer 60/60 · judge H5 · USA/d1 |
| 88 | `F68644f72155e` | distress-conditioned quality: quality ranking only inside the 30% of names whose close sits lowest in its own 250-day distribution | SINGLE.IF_ELSE.LEVEL · anchor-conditioned | novel · novel_frames.jsonl line 45 (NF45) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 89 | `F75da61e36f49` | 52-week-high anchor emphasis: full weight on a revision signal in the 30% of names whose close sits highest in its own 250-day distribution, half weight elsewhere | SWITCH.IF_ELSE.LEVEL · anchor-conditioned | novel · novel_frames.jsonl line 46 (NF46) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 90 | `F7bdd19ffc91c` | variance-premium emphasis: full weight where 120-day implied vol exceeds realized vol, half weight otherwise | SWITCH.IF_ELSE.LEVEL · option-regime | novel · novel_frames.jsonl line 47 (NF47) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 91 | `F25892c5f71f7` | event-risk stand-aside: neutral where the 30-day implied vol is above the 360-day implied vol (inverted term structure) | SINGLE.IF_ELSE.LEVEL · option-regime | novel · novel_frames.jsonl line 48 (NF48) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · USA/d1 |
| 92 | `F69236990eecb` | size-decile standardization: a 250-day z-score, z-scored again inside size deciles | OTHER.NONE.LEVEL · bucket-neutral | novel · novel_frames.jsonl line 49 (NF49) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 93 | `Fb7839b8ffbe5` | rank within volatility quintile | OTHER.NONE.LEVEL · bucket-neutral | novel · novel_frames.jsonl line 50 (NF50) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 94 | `F03b09c6ed8ec` | industry-then-liquidity neutralization: industry de-mean, then de-mean inside liquidity quintiles | OTHER.NONE.LEVEL · bucket-neutral | novel · novel_frames.jsonl line 51 (NF51) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · USA/d1 |
| 95 | `Fe174cd280385` | light carrier plus an attention-gated information leg at 0.6 | SUM.IF_ELSE.LEVEL · carrier-plus-gated-leg | novel · novel_frames.jsonl line 52 (NF52) | none (never simulated) · gate 10/10 + designer 60/60 · judge H5 · USA/d1 |
| 96 | `Fc56ef19203ad` | light carrier plus an earnings-clock leg: a fundamental level at 0.6 weight within 20 days of the release, neutral otherwise | SUM.IF_ELSE.LEVEL · carrier-plus-gated-leg | novel · novel_frames.jsonl line 53 (NF53) | none (never simulated) · gate 10/10 + designer 60/60 · judge H5 · USA/d1 |
| 97 | `F8e6f66619180` | country-then-industry relative: a 250-day z-score de-meaned by country, then ranked within industry | SINGLE.NONE.LEVEL · country-relative | novel · novel_frames.jsonl line 54 (NF54) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · GLB/d1 |
| 98 | `Fdbee1d61f40d` | country-trend sign switch: each country's own 60-day market trend decides ride or fade | SWITCH.IF_ELSE.LEVEL · market-regime | novel · novel_frames.jsonl line 55 (NF55) | none (never simulated) · gate 10/10 + designer 60/60 · judge H6 · GLB/d1 |
| 99 | `F39aeba50087d` | liquidity-segment routing: one leg in the more liquid half by adv20, another in the less liquid half | SWITCH.IF_ELSE.LEVEL · segment-routing | novel · novel_frames.jsonl line 56 (NF56) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · EUR/d1 |
| 100 | `F041679f42cfe` | country-relative shock-day re-evaluation: refresh a within-country rank only on 2-sigma move days | SINGLE.TRADE_WHEN.LEVEL · price-state-trigger | novel · novel_frames.jsonl line 57 (NF57) | none (never simulated) · gate 10/10 + designer 60/60 · judge ok · ASI/d1 |

---

## 8. Appendix A: frame texts (normal form, slots $1..$n)

1. `Fb5b3aef4138a` `multiply(group_rank(ts_mean(subtract($1,$2),5),industry),subtract(1,group_rank(ts_mean(divide($3,$4),10),sector)))`
2. `F066d4521eacf` `multiply(group_rank(ts_mean(subtract($1,$2),5),sector),subtract(1,group_rank(ts_mean(divide($3,$4),5),industry)))`
3. `Fcc903fa0fc8a` `multiply(group_rank(ts_mean(subtract($1,$2),5),industry),subtract(1,group_rank(ts_mean(divide($3,$4),10),subindustry)))`
4. `Ff9dcf8d23b62` `multiply(group_rank(ts_mean(subtract($1,$2),5),industry),subtract(1,group_rank(ts_mean(divide($3,$4),5),industry)))`
5. `F4656fef93d5f` `multiply(group_rank(ts_mean(subtract($1,$2),5),sector),subtract(1,group_rank(ts_mean(divide($3,$4),5),sector)))`
6. `F90584e714637` `multiply(group_rank(ts_mean(subtract($1,$2),5),sector),subtract(1,group_rank(ts_mean(divide($3,$4),20),subindustry)))`
7. `F73ae8ae60d31` `multiply(group_rank(ts_mean(subtract($1,$2),10),sector),subtract(1,group_rank(ts_mean(divide($3,$4),10),sector)))`
8. `Fac8049da8f31` `multiply(group_rank(ts_mean(subtract($1,$2),10),sector),subtract(1,group_rank(ts_mean(divide($3,$4),5),subindustry)))`
9. `F9b677a9ff6ea` `multiply(group_rank(ts_mean(subtract($1,$2),10),subindustry),subtract(1,group_rank(ts_mean(divide($3,$4),5),subindustry)))`
10. `F467b95837848` `multiply(group_rank(ts_mean(subtract($1,$2),10),subindustry),subtract(1,group_rank(ts_mean(divide($3,$4),20),subindustry)))`
11. `F9279ac781c9b` `multiply(group_rank(ts_mean(subtract($1,$2),5),subindustry),subtract(1,group_rank(ts_mean(divide($3,$4),20),industry)))`
12. `F3e1b26968a4e` `multiply(group_rank(ts_mean(subtract($1,$2),10),sector),subtract(1,group_rank(ts_mean(divide($3,$4),20),industry)))`
13. `F2ac6c8193251` `multiply(group_rank(ts_mean(subtract($1,$2),10),subindustry),subtract(1,group_rank(ts_mean(divide($3,$4),10),sector)))`
14. `Fba81db302090` `multiply(group_rank(ts_mean(subtract($1,$2),10),industry),subtract(1,group_rank(ts_mean(divide($3,$4),5),subindustry)))`
15. `F589c0bcb31a6` `multiply(group_rank(ts_mean(subtract($1,$2),5),sector),subtract(1,group_rank(ts_mean(divide($3,$4),20),sector)))`
16. `F4cc0ec931f03` `multiply(group_rank(ts_mean(subtract($1,$2),10),subindustry),subtract(1,group_rank(ts_mean(divide($3,$4),20),sector)))`
17. `F1861b442e931` `multiply(group_rank(ts_mean(subtract($1,$2),10),subindustry),subtract(1,group_rank(ts_mean(divide($3,$4),5),sector)))`
18. `Fc16b45d541e3` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),subindustry),0.5),group_rank(ts_mean($1,10),industry),0)`
19. `F30846af33819` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),subindustry),0.5),group_rank(ts_mean($1,10),sector),0)`
20. `Fa223ada10703` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),sector),0.5),group_rank(ts_mean($1,5),industry),0)`
21. `F6f1e11f44ba3` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),sector),0.5),group_rank(ts_mean($1,10),sector),0)`
22. `F0d3e65f27080` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),industry),0.5),group_rank(ts_mean($1,10),sector),0)`
23. `Fc458fc433207` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),sector),0.5),group_rank(ts_mean($1,5),subindustry),0)`
24. `F6da9d7a16f9e` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),subindustry),0.5),group_rank(ts_mean($1,3),subindustry),0)`
25. `Faa8883d32a0b` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),industry),0.5),group_rank(ts_mean($1,5),industry),0)`
26. `Ffd345db42f35` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_60,implied_volatility_put_60),5),industry),0.5),group_rank(ts_mean($1,10),subindustry),0)`
27. `Fb47d32662b9a` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),industry),0.5),group_rank(ts_mean($1,3),industry),0)`
28. `Ffb6c4f50947f` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),industry),0.5),group_rank(ts_mean($1,5),sector),0)`
29. `Fef466309a133` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),sector),0.5),group_rank(ts_mean($1,10),sector),0)`
30. `F4b4fb591b1e4` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),subindustry),0.5),group_rank(ts_mean($1,5),industry),0)`
31. `F02987d813aed` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),subindustry),0.5),group_rank(ts_mean($1,10),sector),0)`
32. `Fd39b2833c3c6` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),subindustry),0.5),group_rank(ts_mean($1,10),subindustry),0)`
33. `F7f09a7cb01a7` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),industry),0.5),group_rank(ts_mean($1,5),subindustry),0)`
34. `F4f6ae9c88031` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),sector),0.5),group_rank(ts_mean($1,3),industry),0)`
35. `Ff632191d6dd4` `if_else(greater(group_rank(ts_mean(subtract(implied_volatility_call_30,implied_volatility_put_30),5),sector),0.5),group_rank(ts_mean($1,10),subindustry),0)`
36. `F6282cce63c38` `multiply(group_rank(ts_mean(ts_backfill($1,5),5),subindustry),subtract(1,group_rank(ts_mean(divide($2,$3),10),subindustry)))`
37. `F79fc7c57ee17` `multiply(group_rank(ts_mean(ts_backfill($1,5),5),subindustry),subtract(1,group_rank(ts_mean(divide($2,$3),5),industry)))`
38. `F3c74db484f58` `multiply(group_rank(ts_mean(ts_backfill($1,5),5),industry),subtract(1,group_rank(ts_mean(divide($2,$3),5),industry)))`
39. `F3b9da4509541` `multiply(group_rank(ts_mean(ts_backfill($1,5),5),industry),subtract(1,group_rank(ts_mean(divide($2,$3),20),industry)))`
40. `Fa22e41a552e8` `multiply(multiply(group_rank(ts_sum(add($1,0,filter=true),60),sector),group_rank(ts_mean(subtract($2,$3),20),subindustry)),group_rank(ts_rank(divide($4,$5),126),industry))`
41. `Fd53091ea0b53` `multiply(multiply(group_rank(ts_sum(add($1,0,filter=true),20),industry),group_rank(ts_mean(subtract($2,$3),10),sector)),group_rank(ts_rank(divide($4,$5),126),industry))`
42. `F3aa9bc7acdd6` `multiply(multiply(group_rank(ts_sum(add($1,0,filter=true),60),industry),group_rank(ts_mean(subtract($2,$3),10),sector)),group_rank(ts_rank(divide($4,$5),252),subindustry))`
43. `F0a1a4543f44e` `multiply(group_rank(ts_mean($1,10),industry),group_rank(ts_mean(subtract($2,$3),5),sector))`
44. `F218ba3275a27` `trade_when(less(days_from_last_change(ern2_earnrelease_d1_calendar_prev),3),group_rank(ts_delta(ts_backfill($1,60),63),industry),greater(days_from_last_change(ern2_earnrelease_d1_calendar_prev),60))`
45. `Ffa3625746f8e` `if_else(greater(days_from_last_change(ern2_earnrelease_d1_calendar_prev),50),rank($1),add(multiply(rank($1),0.5),0.25))`
46. `F5c09fdbbd596` `trade_when(equal(days_from_last_change(ern2_earnrelease_d1_calendar_prev),1),rank(ts_sum($1,2)),greater(days_from_last_change(ern2_earnrelease_d1_calendar_prev),60))`
47. `F0ec368224298` `if_else(less(days_from_last_change(ern2_earnrelease_d1_calendar_prev),20),group_rank(ts_backfill($1,60),industry),add(multiply(group_rank(ts_backfill($1,60),industry),0.5),0.25))`
48. `Fc5e731809311` `if_else(greater(ts_sum(subtract(returns,group_neutralize(returns,market)),120),0),rank($1),subtract(1,rank($1)))`
49. `F7abfda17cb67` `if_else(greater(ts_std_dev(subtract(returns,group_neutralize(returns,market)),20),ts_mean(ts_std_dev(subtract(returns,group_neutralize(returns,market)),20),250)),rank($1),rank($2))`
50. `F946abbd10f3e` `if_else(greater(ts_zscore(ts_mean(subtract(abs(group_neutralize(returns,market)),group_neutralize(abs(group_neutralize(returns,market)),market)),5),250),1),rank($1),rank($2))`
51. `F9a18b421bbab` `if_else(greater(ts_mean(subtract(sign(returns),group_neutralize(sign(returns),market)),20),0),rank($1),subtract(1,rank($1)))`
52. `F7daa9fbe65e4` `rank(vector_neut(group_zscore(ts_backfill($1,60),industry),$2))`
53. `F78a3802f05f8` `rank(vector_neut(vector_neut(zscore(ts_backfill($1,60)),$2),$3))`
54. `Fa4e48379e71d` `rank(subtract(zscore($1),regression_proj(zscore($1),zscore(log($2)))))`
55. `F571f621e1220` `rank(ts_regression(ts_backfill($1,60),subtract(ts_backfill($1,60),group_neutralize(ts_backfill($1,60),industry)),250,rettype=0))`
56. `F2ce52853bc80` `rank(subtract(zscore($1),regression_proj(zscore($1),zscore($2))))`
57. `F19147c0a90d0` `rank(ts_regression(ts_zscore(ts_backfill($1,60),250),ts_step(1),120,rettype=2))`
58. `F6e8b1b710304` `if_else(greater(rank(ts_regression(ts_backfill($1,60),ts_step(1),120,rettype=6)),0.5),rank(ts_regression(ts_zscore(ts_backfill($1,60),250),ts_step(1),120,rettype=2)),0.5)`
59. `F2acae07a0528` `if_else(greater(ts_corr(ts_delay(ts_backfill($1,20),1),returns,250),0),rank(ts_backfill($1,20)),subtract(1,rank(ts_backfill($1,20))))`
60. `F726b20a89951` `if_else(greater(subtract(ts_corr(ts_delay(ts_backfill($1,20),1),returns,250),group_neutralize(ts_corr(ts_delay(ts_backfill($1,20),1),returns,250),industry)),0),rank(ts_backfill($1,20)),subtract(1,rank(ts_backfill($1,20))))`
61. `F73facd31adf9` `if_else(greater(rank(cap),0.7),rank($1),rank($2))`
62. `F90ea5e89399f` `if_else(greater(rank(anl4_fs_detail_estimates_basic_qf_delay1_v4_nd_eps_number),0.5),rank($1),rank($2))`
63. `F27b013044905` `if_else(greater(rank(historical_volatility_120),0.67),subtract(1,rank($1)),rank($1))`
64. `F97dee83dead1` `if_else(less(mdl10_short_rank,80),rank($1),0.5)`
65. `Fc4515145fc41` `if_else(less(rank(mdl10_inst_ownership),0.3),rank($1),add(multiply(rank($1),0.5),0.25))`
66. `F077e2cb6ed0b` `if_else(equal(greater(rank($1),0.5),greater(rank($2),0.5)),rank(add(rank($1),rank($2))),0.5)`
67. `F83220be66e3e` `if_else(equal(sign(ts_delta(ts_backfill($1,20),5)),sign(ts_delta(ts_backfill($1,20),60))),rank(ts_delta(ts_backfill($1,20),60)),0.5)`
68. `F6cd9e1d1107c` `trade_when(greater(abs(subtract(rank($1),rank(ts_sum($2,120)))),0.5),subtract(rank($1),rank(ts_sum($2,120))),reverse(1))`
69. `F1796d81631e5` `trade_when(greater(divide(volume,adv20),1.5),group_rank(ts_zscore(ts_backfill($1,20),60),industry),reverse(1))`
70. `Fbba079cb8335` `if_else(less(divide(ts_mean(volume,5),adv20),0.7),rank($1),add(multiply(rank($1),0.5),0.25))`
71. `F19ef9670687d` `trade_when(greater(abs(ts_zscore(returns,20)),2),rank($1),reverse(1))`
72. `Ff84a3e6605aa` `trade_when(less(abs(ts_zscore(returns,20)),0.5),group_rank($1,subindustry),reverse(1))`
73. `F4da2c812b764` `if_else(greater(ts_std_dev(returns,20),ts_std_dev(returns,120)),subtract(1,rank($1)),rank($1))`
74. `F2a9a6e94d8e8` `if_else(less(ts_corr(returns,subtract(returns,group_neutralize(returns,market)),60),0.3),rank($1),add(multiply(rank($1),0.5),0.25))`
75. `F805d739c54f2` `if_else(less(rank(subtract(vec_max($1),vec_min($1))),0.5),rank(vec_avg($1)),0.5)`
76. `F04bbee8ae111` `trade_when(greater(ts_zscore(ts_sum(vec_count(nws12_allz_provider),5),60),2),rank(ts_backfill(vec_avg($1),5)),reverse(1))`
77. `Fd0896b7b9062` `if_else(less(rank(mdl177_2_earningmomentumfactor400_stdevfy2epsp),0.5),group_rank(ts_zscore(ts_backfill($1,20),120),industry),0.5)`
78. `Fb2d1899db078` `if_else(less(days_from_last_change($1),10),group_rank(ts_backfill($1,60),industry),add(multiply(group_rank(ts_backfill($1,60),industry),0.5),0.25))`
79. `F976eee838986` `rank(divide(subtract(ts_backfill($1,60),last_diff_value(ts_backfill($1,60),250)),$2))`
80. `Fb6da2bec8da1` `rank(subtract(ts_zscore(ts_backfill($1,60),250),group_neutralize(ts_zscore(ts_backfill($1,60),250),industry)))`
81. `Fd8628f66fb1c` `add(rank(subtract(ts_zscore(ts_backfill($1,60),250),group_neutralize(ts_zscore(ts_backfill($1,60),250),industry))),multiply(rank(group_neutralize(ts_zscore(ts_backfill($1,60),250),industry)),0.6))`
82. `Fe70d906fee51` `rank(subtract(ts_zscore(ts_backfill($1,60),250),group_neutralize(ts_zscore(ts_backfill($1,60),250),sector)))`
83. `Fa241acdc0590` `ts_target_tvr_decay(group_rank(ts_zscore($1,20),subindustry),lambda_min=0,lambda_max=1,target_tvr=0.15)`
84. `F633a72402d22` `sigmoid(group_zscore(ts_backfill($1,60),industry))`
85. `F71afd8265279` `group_neutralize(tanh(ts_zscore(ts_backfill($1,20),60)),subindustry)`
86. `F5610a8b920c5` `group_zscore(ts_quantile(ts_backfill($1,60),250),industry)`
87. `Fd9c39249ee55` `rank(add(ts_delay(ts_sum($1,21),231),ts_delay(ts_sum($1,21),483)))`
88. `F68644f72155e` `if_else(less(rank(ts_rank(close,250)),0.3),rank($1),0.5)`
89. `F75da61e36f49` `if_else(greater(rank(ts_rank(close,250)),0.7),rank($1),add(multiply(rank($1),0.5),0.25))`
90. `F7bdd19ffc91c` `if_else(greater(implied_volatility_call_120,historical_volatility_120),rank($1),add(multiply(rank($1),0.5),0.25))`
91. `F25892c5f71f7` `if_else(greater(implied_volatility_call_30,implied_volatility_call_360),0.5,rank($1))`
92. `F69236990eecb` `group_zscore(ts_zscore(ts_backfill($1,60),250),densify(bucket(rank($2),range="0.1,1,0.1")))`
93. `Fb7839b8ffbe5` `group_rank(ts_backfill($1,60),densify(bucket(rank($2),range="0.2,1,0.2")))`
94. `F03b09c6ed8ec` `group_neutralize(group_neutralize(rank(ts_backfill($1,60)),industry),densify(bucket(rank($2),range="0.2,1,0.2")))`
95. `Fe174cd280385` `add(reverse(rank(divide($1,$2))),multiply(if_else(greater(divide(volume,adv20),1.5),rank($3),0.5),0.6))`
96. `Fc56ef19203ad` `add(reverse(rank(divide($1,$2))),multiply(if_else(less(days_from_last_change(ern2_earnrelease_d1_calendar_prev),20),group_rank(ts_backfill($3,60),industry),0.5),0.6))`
97. `F8e6f66619180` `group_rank(group_neutralize(ts_zscore(ts_backfill($1,60),250),country),industry)`
98. `Fdbee1d61f40d` `if_else(greater(ts_sum(subtract(returns,group_neutralize(returns,country)),60),0),rank($1),subtract(1,rank($1)))`
99. `F39aeba50087d` `if_else(greater(rank(adv20),0.5),rank($1),rank($2))`
100. `F041679f42cfe` `trade_when(greater(abs(ts_zscore(returns,20)),2),group_rank(ts_backfill($1,60),country),reverse(1))`

---

## 9. Files and commands

Repo (all new, untracked, nothing committed):
- `framelib/library/frames/<id>.json`: 100 entries.
- `framelib/library/INDEX.json`: every id filed under each taxonomy axis, plus status.
- `docs/frames/11_first_100_frames.md`: this file.

No other repo file was touched.

`$CUR` (scratch, 2.8 MB):

| file | what |
|---|---|
| `lib134/` | the full build: 77 mined + 57 novel, fixed `--now` |
| `select.py`, `selection.json` | rule v2 and its output (the reason for every kept id; the dropped ids) |
| `select_v1.py`, `selection_v1.json` | rule v1, kept for the record |
| `lib100/` | the same 100 entries written to scratch; `diff -r` against the repo library is empty |
| `verify.py`, `verify.json`, `verify_perframe.json`, `samples.jsonl` | §4: validation, 1,000 sample fills with four checks, historic formulas, evidence recount |
| `coverage.py`, `coverage.json` | §3: axes, source families, operators, cells |
| `roles.py`, `roles.json` | the historic fields of each mined slot, with catalogue descriptions |
| `make_table.py`, `table.md` | §7 and Appendix A |

Commands:

```
python3 -B -m framelib.store                          # validate the library (exit 1 on any problem)
python3 -B $CUR/verify.py framelib/library 10         # the §4 checks (about 16 s, one process)
python3 -B -m framelib.build --canonical $SCRATCH/frames/canonical \
    --novel $SCRATCH/frames/designer/novel_frames.jsonl \
    --discovery docs/frames/10_frames_discovery.md --discovery $SCRATCH/frames/quant/out/q4_candidates.csv \
    --out $CUR/lib134 --now 2026-09-24T08:00:00+00:00  # the full 134-entry build (writes scratch only)
python3 -B $CUR/select.py --write                     # rule v2 -> framelib/library
```
