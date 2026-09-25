# 12 — Phase A audit: what survived re-measurement

2026-09-24. Role: adjudicator for phase A. Inputs: the three audit reports (`audit_data.md`,
`audit_code.md`, `audit_rule0.md` in `$SCRATCH/frames/`), docs 10 and 11, `RECONCILIATION.md`, the
local raw copies in `$SCRATCH/frames/data/`, and `framelib/`. `$SCRATCH` =
`/private/tmp/claude-501/-Users-kanenguyen-Projects--worldquant-wq-pipeline/822757b8-b9d3-46ed-9802-93fbfbd128e6/scratchpad`.

I re-derived each finding that affects a decision with my own code (`$SCRATCH/frames/adjudicator/`, §7),
reading canonical rows, raw copies and framelib read-only. Nothing was simulated, nothing touched the
VPS, no `--live`/`--submit`, and no framelib or forge code was changed (RULE 1, RULE 2). The only repo
write is this file.

Labels (RULE 0): **EX-ANTE** from documentation, code or definitions; **POST-HOC** a regularity
measured in data; **SPECULATION** neither. Every number of mine below is POST-HOC. Where a reason for
a pattern was not separated by an experiment it reads **MECHANISM: UNKNOWN**. Unless a line says
otherwise, the cell is forge × USA/d1/TOP3000 (29,597 rows, 8,229 frames, 1,085 with ≥ 4 fills,
1,257 LOW_SHARPE passes, 37 d24; my recount matches doc 10 exactly).

---

## 0. Verdict on one screen

1. **Established (POST-HOC, one cell, one 20-day sim era, IS metrics only):** frame scores reproduce
   across disjoint subsets of *near-synonym* fills, and the direction survives standardising by
   day × neutralization × decay × truncation. The library's 100 entries are structurally fillable.
2. **Not established:** that a frame stays good on different *data* (every pass but 24 carries one of
   three datasets), in market time, against the current generator, for d24, in any other cell, or for
   any of the 57 novel frames. Steps 2–3 of Khoa's hypothesis ("bền hay chỉ ăn may", library of
   proven frames) have not been run: there has never been a live round.
3. **The headline "about 4×" is inflated.** Within strata it is about 3× (2.6×–10× across the two
   truncation values); the frame-only lift is not identified between about 2.7× and 4.5×. It is a
   ranking lift among frames the forge already re-filled, not an improvement rate over the generator.
4. **Three BLOCKERs, eight SERIOUS, the rest MINOR (§3).** Two blockers are text corrections that the
   live design depends on; one is a validator hole that must be closed before any round result is
   written into the library.
5. **Use for the live rounds: yes as the list of frames to test and as the fill machinery; no as
   evidence that any frame is durable (§5).** The discovery numbers may be used for sizing only in
   their corrected form. Everything still goes to Khoa as tick questions and runs on the VPS.

---

## 1. What phase A established

| # | claim | status after adjudication | my re-derivation |
|---|---|---|---|
| E1 | Canonical dataset (66,058 rows / 33,007 frame_keys) is a faithful build of the raw copies | REPRODUCED (data auditor, own parser, 0 differences); my cell counts equal doc 10 §1 | `forge1.py` |
| E2 | Split-half reliability of frame scores across fills, forge cell | REPRODUCED by two auditors (0.643 / 0.589) | — |
| E3 | Field-disjoint split: 406 frames splittable | REPRODUCED: 406 | `dsdisj.py` (own union-find) |
| E4 | Early→late on new field ids, 614 frames | REPRODUCED: 614 frames, Spearman 0.745 (way B); top 20% late pass 22.3% vs 5.05% | `v6.py` |
| E5 | The direction of E4 and of leave-fields-out survives day × settings standardisation | REPRODUCED: O/E ratio 3.08 (V6, mine); 3.5–3.6 LOFO (two auditors, independent code) | `v6.py` |
| E6 | The frame carries information beyond its shape, mainly for pass | REPRODUCED: pass split-half 0.48–0.49 observed vs 0.31–0.34 within-shape null (null max 0.39 of 40); y_ratio 0.588 vs 0.539 (null max 0.575) | `shape_null.py` |
| E7 | All 100 library entries validate; suite passes | REPRODUCED: `store.load` 100 entries, all `candidate`; `pytest framelib/tests` 115 passed | inline |
| E8 | Library fills pass forge's structural gate | REPRODUCED with a new seed (424242): 300/300 fills pass `TY.judge(..., structural=True)` on the full label file, the same call `forge/runner.py plan()` makes; 300/300 re-frame to their own frame; 300/300 fields in the cell catalogue; 0 dead frames | `fillcheck.py` |

---

## 2. What phase A did not establish

| question (Khoa's words) | status | why |
|---|---|---|
| Does a frame stay good "khi thay field" on **different data**? | NOT MEASURED | 1,233 of 1,257 passes (98.1%) contain an option3, option8 or us_short_sale field (slot or condition). Eligible frames with no such field: **0 passes in 5,672 rows (442 frames)**. MH ratio within day × settings 30.6 (mine) / 30.2 (rule0). All 860 candidate rows contain one; 37 of 77 candidates pin the IV pair in the frame text. Of the 406 field-disjoint splittable frames, **288 have no dataset-disjoint split**; 39 of 77 candidates never had a field-disjoint test. MECHANISM: UNKNOWN (frame, data, hand-written hypothesis or allocator — not separable). |
| "Bền" in **market time** | NOT MEASURED | "Days", "early/late", "chronological" are simulation dates; every metric is in-sample. |
| Is each **frame** not luck? | ASSERTED more than measured | C1 assumes exchangeable fills (doc 10 itself says they are not); C2's "400 splits" are 3–10 distinct splits for 43 of 77 candidates (n = 4/5/6 fills: 14/15/14 frames); the permutation null only rules out pure noise. |
| **"Tỉ lệ cải thiện tăng bao nhiêu"** vs today's generator | NOT ANSWERABLE from history | No randomized comparison arm ever ran; the 4× compares against allocator-selected re-filled frames. |
| **d24 / submittable** | OUT OF REACH | 20 of 1,023 d24 rows sit in frames with ≥ 4 fills (forge 19/37, resim 1/150, layered 0/712, climb 0/124). Among LOW_SHARPE passers, candidates pass LOW_SUB_UNIVERSE_SHARPE 27/274 (9.9%) vs 363/983 (36.9%) for others (MH 0.39 mine / 0.50 rule0); IS_LADDER 87/274 vs 289/983 (MH 0.86 / 0.93). MECHANISM: UNKNOWN. |
| Other cells, other eras | NOT MEASURABLE | 0 shared frames across eras; every other forge cell has 0 passes. |
| The 57 novel frames | NOTHING MEASURED | Never simulated. Their slot constraints ("field phù hợp") come from SPECULATION rationales matched against regex-derived labels. |
| The library **as the filler fills it today** | OUTSIDE ALL MEASURED RANGES | Mined entries declare no slot constraints. My 215 mined sample fills (seed 99): **0 inside the historic field pool**; the 18 IV-pinned frames keep the ingredient 90/90, the other 25 mined frames only **8/125 (6%)**. |

---

## 3. Surviving defects, ranked, with the exact fix

Severity is judged against one use: designing the live rounds and, later, promoting frames.

### BLOCKER

| id | where | defect (re-derived) | exact fix |
|---|---|---|---|
| B1 | doc 10 §0.2, §4.3 and the VN summary bullet 2; feeds §6 sizing | "4.4× … the historical answer to 'tỉ lệ cải thiện tăng bao nhiêu'" is a raw pass share pooled across day × settings. Mine (V6): raw 4.43×; top frames' late rows at truncation 0.15: 63.7% vs 32.7% for the rest; within 0.08: 10.1% vs 1.2% (8.7×); within 0.15: 29.3% vs 11.2% (2.6×); O/E 3.08. Both auditors agree (3.1× / 2.7× early→late, 3.5–3.6× LOFO). The comparison arm is re-filled frames, not the generator. | Replace the sentence with: "Among frames the forge had already re-filled, the top 20% by train score pass 23.1% of unseen-field test fills vs 5.3% (4.4× raw, pooled across day × settings). Standardised within day × neut × decay × trunc it is about 3× (2.6×–10× within one truncation value); the frame-only lift is not identified between about 2.7× and 4.5×. It is a ranking lift among re-filled frames, not an improvement rate over the generator (Q5)." Same change in the VN bullet ("gấp khoảng 3 lần sau khi chuẩn hoá theo ngày và settings; chưa so với generator"). Mark "(5–95%)" in §4.3 as "spread over 300 partitions of the same rows, not a confidence interval". |
| B2 | doc 10 §0.1, §0.3, §4.4, VN bullet 1; doc 11 §5 | The ingredient confound (§2 row 1) is reported nowhere. "Khung tốt vẫn tốt khi thay field" was measured only on fields from the same role pools, with the option/short-sale data always present. The library's unconstrained filler strips that data from 25 of 43 mined frames. | Doc 10 §0.1 and VN bullet 1: "Within one cell, frame rankings reproduce across other field ids from the same role pools. 1,233 of 1,257 passes contain an option3/option8/us_short_sale field; eligible frames without one passed 0 of 5,672 rows. MECHANISM: UNKNOWN." Add the 288/406 dataset-disjoint and 39/77 never-field-tested counts to §4.4 "Not established". Doc 11 §5: add the 8/125 figure. Live design: record, for every fill, whether it carries one of the three datasets, and randomize it as a factor (doc 10 §6 arms (b)/(c)). |
| B3 | `framelib/schema.py` `validate`, the RULE 2 surface | Shown in memory on a real entry (`vprobe.py`): status `validated` with **one round copied 3 times, effect −0.5, approval `{"by": "claude"}`** returns no error. The validator also accepts `comparison_arm: "none"`. Latent: 0 of 100 entries are validated. | In the `validated` branch: refuse unless (1) `len({(r["round"], r["date"]) for r in rounds}) == len(rounds) >= MIN_ROUNDS`; (2) every `r["effect"]` is a number > 0; (3) every `r["comparison_arm"]` not in `("", "none")`; (4) `approval["by"]` is in an `APPROVERS` constant that Khoa sets (RULE 2: his tick, not an agent's). Refuse an `approval` block on a non-validated entry. One test per rule, each with a failing and a passing entry. Must land before the first live round writes a `reliability` block. |

### SERIOUS

| id | where | defect (re-derived) | exact fix |
|---|---|---|---|
| S1 | doc 10 §4.2, §1 | "643 frames, Spearman 0.674; shape 0.844" is not determined by the data. In the late period **0 of 2,980 frames ran under two truncation values** (whole cell: 70 frames ever did), so the late-only way-A fit is rank-deficient. Mine: 643 frames, unadjusted 0.707, whole-cell way B 0.635; shifting the unidentified late truncation effect 0 → 0.5 moves it 0.61 → 0.70 → 0.48. Auditor: 0.37 (min-norm) to 0.74. Layered days 08-13 and 08-17 are also unidentified (no multi-day frame touches them). | Replace with "NOT DETERMINED: 0.37–0.74 by adjustment method (0.707 unadjusted)". In §1 way A, list the unidentified contrasts (late truncation; layered 08-13, 08-17; USA/d0; EUR) and delete "each stratum effect is estimated within frames that ran in several strata" for them. |
| S2 | doc 10 §0.7, §5; doc 11 §0 | The C1 count is Monte Carlo noise at the BH line. Stored p-values of ranks 80–95 sit 1–2 MC standard errors (≈0.00014) from the line; shifting all p by ±1/±2 SE gives 87/91 and 80/78 frames. The auditor's exact FFT tail gives 85 frames / 36 shapes, containing all 77. | Report "77–91 frames (exact tail: 85 / 36 shapes)" and keep reading it at family level. Compute C1 with the exact tail (convolution) or ≥ 10⁷ draws. |
| S3 | doc 10 §0.6, §4.1, §7 | Layered: 1,418 of 1,449 passes (97.9%) and all 712 d24 rows are on 2026-08-14. "0.54% vs 18.7%" is pooled across days: 08-14 1.2% (≥ 4 fills) vs 45.3% (1 fill); 08-15 0.34% vs 0.23% (reversed). "Pass r −0.027, no reliability" rests on 22 passes. Layered V4 day-disjoint is **−0.49 under day-mean adjustment, +0.42 unadjusted** (way A 0.45), so §7's "no sign changes" is false. | §0.6/§4.1: "not estimable (22 passes in 21 frames)"; give the within-day rates. §7: "no sign change except layered V4 (way B −0.49)". Why 08-14 differs: MECHANISM: UNKNOWN. |
| S4 | doc 10 §3 | "That is the allocation of §2.2 seen from the other side" states a mechanism with no experiment. In layered the first-fill score correlates **negatively** with later fills (mine −0.10 raw; rule0 −0.198 adjusted), forge positively (+0.21 raw / +0.159 adjusted); layered multi-fill frames have 1–2 slots (143 / 98) vs a median 3 for one-fill frames. | Replace with "Why: MECHANISM: UNKNOWN; in layered the allocation sign is opposite." |
| S5 | doc 10 §0.1, §0.7, §4 title, §4.1 V3/V4 | "Luck test" and "different days / chronological" name more than was measured (§2 rows 2–3). | "Luck test" → "exceeds a random fill of the cell under exchangeability". "Different days" → "different simulation days, same IS window". Add the C2 distinct-split counts. |
| S6 | doc 10 §6 Q8 → doc 11 F3, §2.1 | "Small" hides ~30% of pass reliability: 0.539 → 0.388 (quant, p < 1/400); mine 0.49 → 0.34. Doc 11 used F3 (y_ratio only) to drop 34 window variants. | Doc 10 Q8: "−28% of pass reliability (0.539 → 0.388)". Doc 11 F3: add the pass numbers and say F3 holds for y_ratio, not for pass; §2.1: "the history partly tells window variants apart on pass". Keep the drop as Khoa's choice (question 1), not as a consequence of F3. |
| S7 | doc 10 §6 sizing; doc 11 §2.4 | The sizing uses the pooled 5.3% base, the inflated lift (B1) and frames as independent clusters; the mined side has 43 frames in 34 shapes / 6 structures. | Redo: base rate from the arm's own day × settings; planning effect from the within-stratum lift, taking the low end (2.6×); cluster = shape (or structure), ICC from the pass split-half at that level; outcome = the full binding set (d24, LOW_SUB_UNIVERSE), not LOW_SHARPE alone (§2 row 5). |
| S8 | `framelib/build.py` `gather()` | Slot-spec **keys** are renumbered (`n.renumbered(k)`), the `unit_eq` **value** is not, so a designer template whose slots are renumbered gets a constraint pointing at the wrong slot, silently. Latent: the 3 current `unit_eq` entries (F976eee838986, Fc56ef19203ad, Fe174cd280385) renumber by identity (checked against designer lines 36, 53, 52). | In `add()`, after computing `specs`: for each spec with `constraints.unit_eq = "$j"`, set it to `"$%d" % n.renumbered(j)` and raise `FrameError` if that is `None`. Test with a template whose slots are written out of order. |

### MINOR

| id | where | defect | fix |
|---|---|---|---|
| M1 | RECONCILIATION §7.5 | Both WjAR7Q1P lines **have** a `parent_url`, and they differ (`…/simulations/1DP3Qu2Ee4Fca8L1btKdnuI9`, `…/2DUlew1ul4XzbpZmzLhFeKa`); 1-based lines are 9,867 and 10,322. | Correct the text; record the two parent URLs as the lead for resolving the formula. |
| M2 | RECONCILIATION R15 | 42,410 counts eligible lines; kept rows carrying both sources = **39,390**, all agree. | Change the population label. |
| M3 | RECONCILIATION §7.7 | 13 of the top-20 frames by fills have one operator; 7 have 2–4; two hold one small-corpus TOP3000 row. | Reword. |
| M4 | doc 10 §1 | Layered USA/d1 spans 08-13..08-17 (08-18 is JPN only). | Correct. |
| M5 | `audit_data.md` F4; doc 10 §2.1; `audit_rule0.md` H5 | Correction of an auditor claim: forge and recovered raw rows **do** record a window — the IS_LADDER_SHARPE check's dates. In the cell, 28,410 rows end in 2024-01 (2024-01-02 is the USA value in forge); **1,168 rows in 260 frames end earlier (1,150 in 2021)**, and they hold 0 passes, 0 candidates, 0 d24. Resim rows record `startDate 2019-01-01, endDate 2023-12-31` in settings. So "not in the data" and "every sim scores the same IS window (EX-ANTE)" are imprecise. MECHANISM of the earlier windows: UNKNOWN. | Doc 10 §2.1: state the ladder-date distribution; carry the ladder end date into canonical rows; in live rounds record it per fill. |
| M6 | RULE 0 labels | Doc 10 §0.3 "close substitutes. EX-ANTE" → POST-HOC reading, statistical closeness unmeasured. Doc 11 §7 "function (EX-ANTE …)": the library stores `function` unlabelled (only `computes` carries EX-ANTE; checked in `Fc4515145fc41.json`: "neglect emphasis …"). Designer NF06 labels "the platform rescales the book daily" EX-ANTE with no document (the only "book size" text in OPERATORS.md is `scale()`'s description). Doc 10 §2.1 "64% … composition" is a ratio of two ranges. Doc 11 F4 "removes", §2.4 "independent". RECONCILIATION §1/§3: B subclasses `forge.typed.Parser` and C uses `forge.typed.parse`, so "C vs B 0 differences" is not independent support. | Relabel as listed in `audit_rule0.md` §7 (rows M-10a, R11-2, D1, D2, D3, L-10b, L-11a, L-11b, L-R1). |
| M7 | framelib code | `_check_evidence` returns early on the **shared** `errs` list, so any earlier error hides all evidence errors. `store.problems` accepts a missing INDEX.json (`if ip.exists()`). With no USA d0 catalogue in `fetched/rc/fields/`, `fl.ids_in` returns `{}` and the filler reports "fixed field absent" for 12 mined frames' USA/d0 cell. Presence is per cell, not per universe (latent; ILLIQUID_MINVOL1M only). | Use a local `miss` list in `_check_evidence`; add "INDEX.json missing" to `problems`; in `fill`, `if cell not in fl.catalogue: dead = ["no catalogue for %s" % cell]`. |
| M8 | framelib tests | Test gaps, code correct today: C17 `vec_after` (my count: dropping it flips the gate on `rank(vec_avg(f))` for 403 of 16,347 USA/d1 VECTOR fields; auditor 452 on its formula set; the example `competitive_advantage_indicator` reproduces), F01 (`random.Random(str)` is deterministic; no cross-process test), B09, C02, R19, and the filler/validator survivors (`len(fills) == n`, in-call duplicates, dead frame yields 0 fills, `by` modes). | Add those assertions; a subprocess test under two PYTHONHASHSEED values; a vec_after-sensitive field in the compat sample; slot names that do not collapse `$11` into `$1`+`1`. |

---

## 4. Findings dropped or corrected on re-measurement

- **Dropped:** the data auditor's "no other corpus records a window at all" (F4) — forge and
  recovered rows carry IS_LADDER dates (M5).
- **Numbers that did not reproduce, conclusion kept:** rule0 H3's "−0.198" and its multi-fill
  first-fill means (−0.047 / −0.221 / −0.339). My raw first-fill definition gives −0.099 and
  0.074 / −0.026 / 0.007; only the sign (negative in layered, positive in forge) reproduces. The
  label fix (S4) does not depend on the magnitude.
- **Stratum-dependent magnitudes, direction kept:** rule0's MH ratios (ladder 0.93, LOW_SUB_UNIVERSE
  0.50, LOW_FITNESS 2.04, ingredient 30.2) are 0.86, 0.39, 5.29, 30.6 on my strata. Cite directions,
  not these values.
- **Rule0 D1's "grep finds nothing":** OPERATORS.md does mention book size (for `scale()`), but not
  daily platform rescaling; the relabel stands.
- **Not re-derived by me (reported by one auditor only, not decision-relevant):** the mutation score
  (78.7%, 477 survivors) and the 146 guard reversions; the normal-approximation count (2 under way B,
  23 under way A); LOFO 43 vs 44 of 44; the 61 skeletons.

---

## 5. May the library and the discovery numbers be used to design the live rounds?

**The 100-frame library: yes, as the list of frames to test and as the fill engine. No, as evidence.**
- Fillability is established (E8). Being in the library says nothing about performance: 57 frames
  were never simulated, and the 43 mined ones are POST-HOC, in-sample, one cell.
- Mined frames must be filled in two declared modes, as separate arms: historic role pools (needs
  the builder change doc 11 §6 Q2 names) and gate-legal fields. Record per fill whether one of the
  three datasets is present (B2). Without that factor, a failure of the 25 unpinned mined frames
  cannot be told apart from the data leaving.
- No entry may change status until B3 is fixed; S8 must be fixed before the next build that adds
  designer frames.

**The discovery numbers: only in corrected form.**
- Usable: which families and frames to include; the within-stratum effect (about 3×, plan for 2.6×);
  the within-shape pass increment (S6) as a reason to test windows × groups inside a shape.
- Not usable: "4.4×" as the effect (B1); "0.674" (S1); "77" as an exact count (S2); layered "no
  reliability" (S3); doc 10 §6's 320 fills / 60 frames (S7).
- Design constraints that follow from what was measured: all arms on the same days and settings,
  truncation fixed or balanced across arms (S1, B1); a current-generator arm, which is the only arm
  that answers "tỉ lệ cải thiện tăng bao nhiêu"; outcome = full binding set including d24; the IS
  ladder window recorded per fill (M5).

**RULE 2 status.** The frame library is an open item: gates 3–4 (proof over many live rounds against
an arm without it, and solving the stated problem) have not started. The live design goes to Khoa as
tick questions, runs on the VPS (RULE 1), and nothing here runs live.

---

## 6. Re-derivation ledger (auditor claim → my value)

| claim | auditor | mine | script |
|---|---|---|---|
| passes with ingredient | 1,233 / 1,257 | 1,233 / 1,257 | forge1.py |
| eligible no-ingredient passes | 0 / 5,672 (442 frames) | 0 / 5,672 (442); frame-level 0 / 5,662 (435) | forge1.py |
| candidates: rows, passes, d24, rows with ingredient | 860 / 274 / 14 / 860 | same | forge1.py |
| candidates field_testable False | 39 | 39 | forge1.py |
| candidates with 4 / 5 / 6 fills | 14 / 15 / 14 | same | forge1.py |
| field-disjoint splittable / no dataset-disjoint split | 406 / 288 | 406 / 288 | dsdisj.py |
| d24 in ≥ 4-fill frames | 20 / 1,023 | 20 / 1,023; forge d24 in one-fill frames 17 / 37 | misc1.py |
| layered 08-14 share of passes, d24 | 97.9%, 712 / 712 | 1,418 / 1,449, 712 / 712 | misc1.py |
| layered within-day 08-14, 08-15 | 45.3% vs 1.2%; 0.23% vs 0.34% | same | misc1.py |
| layered V4 way B | −0.485 | −0.488 (unadjusted +0.424) | lay_v4.py |
| late frames with two truncations | 0 | 0 of 2,980 | v6.py |
| early/late 643 frames unadjusted | 0.707 | 0.707 | xera.py |
| V6 trunc-0.15 share top vs rest | 67.6% vs 32.0% | 63.7% vs 32.7% | v6.py |
| V6 within-truncation lifts | 10.0× / 2.8× | 8.7× / 2.6× | v6.py |
| V6 O/E | 3.1× (data), 2.69× (rule0) | 3.08× | v6.py |
| within-shape pass null | 0.539 → 0.388 (quant) | 0.491 → 0.337 raw; 0.484 → 0.308 way B | shape_null.py |
| BH count fragility | 85 exact vs 77 MC | 78–91 under ±2 MC SE on stored p | inline on `q4_all_eligible.pkl` |
| R15 kept rows | 39,390 | 39,390 (42,410 lines) | r15.py |
| WjAR7Q1P parent_url | both present, differ | both present, differ; lines 9,867 / 10,322 | grep |
| validator accepts copied rounds / effect −0.5 / "claude" | yes | yes | vprobe.py |
| unit_eq value not renumbered | yes, latent | yes by reading; 3 entries identity | inline |
| no USA d0 catalogue | yes | yes (`fetched/rc/fields/` has USA_TOP3000_d1 only) | ls |
| library fills pass the runner gate | 500 / 500 | 300 / 300 (seed 424242) | fillcheck.py |
| mined fills inside historic pool | 0 / 430 (curator) | 0 / 215; ingredient kept 90/90 pinned, 8/125 unpinned | minedfill.py |
| IS_LADDER dates in raw | "no window recorded" | 28,410 rows end in 2024-01; 1,168 end earlier, 0 passes | ladwin.py |

---

## 7. Files

`$SCRATCH/frames/adjudicator/` (57 MB): `load.py` (own row table from canonical), `forge1.py`,
`misc1.py`, `v6.py`, `xera.py`, `lay_v4.py`, `shape_null.py`, `dsdisj.py`, `alloc.py`, `r15.py`,
`ladwin.py`, `vprobe.py`, `fillcheck.py`, `minedfill.py`. The vec_after count, the BH fragility and
the unit_eq check ran inline. Run each as
`PYTHONDONTWRITEBYTECODE=1 python3 -B <script>` from that directory.

---

**Tóm tắt cho Khoa (tiếng Việt).**
- Đã chứng minh (POST-HOC, 1 ô USA/d1/TOP3000, 20 ngày forge, chỉ số IS): xếp hạng khung lặp lại khi
  đổi sang field gần đồng nghĩa, kể cả sau khi chuẩn hoá theo ngày và settings. 100 khung trong thư
  viện đều lắp field được và qua cổng cấu trúc của forge (300/300 fill kiểm lại).
- Chưa chứng minh: khung có bền khi đổi sang **dữ liệu khác** hay không. 1.233/1.257 alpha qua
  LOW_SHARPE đều dùng field option3/option8/us_short_sale; khung không có các field đó qua 0/5.672.
  Chưa có so sánh với generator hiện tại, chưa có d24, chưa có ô khác, 57 khung mới chưa sim lần nào.
- Con số "gấp 4 lần" bị thổi phồng: chuẩn hoá theo ngày và settings thì còn khoảng 3 lần (2,6–10 lần
  tuỳ truncation), và đó là so với các khung đã được forge sim lại, không phải so với generator.
- Lỗi chặn: (1) sửa con số 4 lần; (2) ghi rõ nhiễu do dataset option/short-sale; (3) validator hiện
  cho phép "validated" với 1 vòng chép 3 lần, hiệu ứng âm và người duyệt là "claude" — phải sửa trước
  khi ghi kết quả vòng live nào vào thư viện.
- Thư viện dùng được làm danh sách khung để thử trong vòng live; không dùng làm bằng chứng. Thiết kế
  vòng live phải: cùng ngày và settings cho mọi nhánh, có nhánh generator hiện tại, ghi field
  option/short-sale như một yếu tố, đo cả d24. Chạy trên VPS và chờ Khoa tick.
