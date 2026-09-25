# Round 1 result — FRAMES-R1B (2026-09-24, 17:5x–19:51 +07)

Read-out per docs/frames/13a_preregistration_round1.md (sha256 b45ea1ec…, recorded before any row). Attempt 1
(FRAMES-R1) was aborted and is excluded (00_decisions.md). Script: framelib/experiments/analyse_round.py;
inputs: /opt/wq/state/layered/runs/frames_r1b.jsonl, its .plan.json, recovered.jsonl (copied 19:5x).

## What ran

1,210 planned constructions, USA/d1/TOP3000, one day, arms shuffled in single-arm parents of 10.

| arm | planned | scored (COMPLETE+WARNING) | ERROR | CANCELLED | missing |
|---|---|---|---|---|---|
| a library frame x own-role fields | 320 | 308 | 0 | 12 | 0 |
| b library frame x other-dataset fields | 310 | 247 | 7 | 56 | 0 |
| c non-library frame x b's fields (paired) | 260 | 225 | 6 | 29 | 0 |
| d the current generator | 320 | 306 | 10 | 4 | 0 |

## The pre-registered answers

Primary outcome = LOW_SHARPE PASS; failures include ERROR / CANCELLED / missing (13a).

| arm | LOW_SHARPE PASS | rate (planned) | rate (scored) |
|---|---|---|---|
| a | 2 | 0.63 % | 0.65 % |
| b | 4 | 1.29 % | 1.62 % |
| c | 3 | 1.15 % | 1.33 % |
| d | 4 | 1.25 % | 1.31 % |

- **Q-C (does the library raise the rate against the current generator?) — NOT SHOWN.** a/d = 0.50, 95 %
  cluster-bootstrap interval [0, ∞): 2 vs 4 events cannot bound a ratio. The pre-registered claim needed the
  lower bound above 1; it is not.
- **Q-A (library frame vs non-library frame on the SAME fields) — NOT SHOWN.** 251 pairs; discordant 3 (b only)
  vs 1 (c only); exact McNemar p = 0.625.
- **Q1 (own-role fields vs other datasets), reported without a claim:** a/b = 0.48, interval [0, 3.89].
- **All 7 binding checks (D24): 0 in every arm.** No alpha of this round is submittable; the correlation probe
  had nothing to read.
- **Q-B (robust or luck) is not answered by round 1** (13a); round 2 re-fills every frame on fresh fields.

Secondary outcome, Sharpe >= 0.8 x its LOW_SHARPE limit (y08), same method:

| arm | y08 | rate (planned) |
|---|---|---|
| a | 35 | 10.9 % |
| b | 12 | 3.9 % |
| c | 13 | 5.0 % |
| d | 27 | 8.4 % |

a/d = 1.30, interval [0.53, 7.02] (covers 1). a/b = 2.83, interval [1.42, 6.57].

## POST-HOC observations (after the data; none is an explanation)

1. **The option/short-sale factor splits every arm.** Split by whether any field ANYWHERE in the formula (slots
   and preset condition fields) is from option3, option8 or us_short_sale:

   | arm | with those fields: n, y08 share, median Sharpe/limit | without: n, y08 share, median Sharpe/limit |
   |---|---|---|
   | a | 147, 21.5 %, −0.04 | 173, 2.4 %, 0.04 |
   | b | 69, 16.7 %, 0.60 | 241, 1.6 %, 0.01 |
   | c | 78, 8.5 %, 0.45 | 182, 4.5 %, 0.22 |
   | d | 80, 31.2 %, 0.68 | 240, 1.3 %, 0.38 |

   Inside the "with" stratum the library (a) is BELOW the current generator (21.5 % vs 31.2 %); inside "without"
   it is above (2.4 % vs 1.3 %). The strata are not balanced across arms (a has 147/320 "with", d 80/320).
   The split the phase-A audit found in the history (doc 12, B2: 1,233 of 1,257 historical passes used these
   datasets) appears again in live data. MECHANISM: UNKNOWN. (The analyse_round.py "focus" field only reads slot
   fields and misses preset condition fields; this table recomputes it from the formula text.)
2. **The historical "4.4x / 22 % on unseen fields" did not appear.** The discovery's top frames passed
   LOW_SHARPE on 21.8–23.1 % of unseen fills in the history; here the library's own-role arm passed 0.63 %.
   The phase-A audit had already warned that the history's "unseen" fields were near-synonyms from hand-picked
   pools and that the figure was pooled across days and settings (doc 12, B1). Which of those, or something
   else, makes the gap: UNKNOWN.
3. **Loss to errors differs by arm:** b lost 20 % of its planned alphas (7 ERROR, 56 CANCELLED), c 13 %,
   d 4 %, a 4 %. The failures count against the arm (13a); the scored-only rates are printed beside them.
4. **Power.** With 2–4 LOW_SHARPE events per arm, no ratio on the primary outcome can be bounded in one round;
   doc 13 (written before any R1 row) moves the primary to y08 for rounds 2+ for this reason.

## What round 1 establishes

Nothing in favour of the hypothesis on the pre-registered tests: no rate gain of library frames over the
current generator, and no gain of library frames over non-library frames on the same fields. The one large,
repeated regularity is the dataset family, not the frame.

## Doc 13's reading notes on round 1 (pre-declared "printed beside", computed 2026-09-25 ~13:50)

Counts are (events, rows, rate). None of these changes 13a's verdicts above.

| note | what | arm a | arm d |
|---|---|---|---|
| N1 | d restricted to its USA/TOP3000 rows (60 of d's 320 rows were GLB/MINVOL1M) | LS 2/320 = 0.63 %, y08 35/320 = 10.9 % | LS 4/260 = 1.54 %, y08 27/260 = 10.4 % |
| N2 | d restricted to a's settings support (INDUSTRY/SUBINDUSTRY/STATISTICAL x decay 4/8 x truncation 0.08) | LS 0.63 %, y08 10.9 % | **LS 0/205, y08 9/205 = 4.4 %** |
| N4 | ingredient stratum (option3/option8/us_short_sale anywhere in the formula), d USA rows | with: LS 1/147, y08 21.1 %; without: LS 1/173, y08 2.3 % | with: LS 4/80, y08 30.0 %; without: LS 0/180, y08 1.7 % |
| N5 | b vs c McNemar on the 178 ingredient-concordant pairs | LS: b only 2, c only 1, p = 1.0; y08: b only 5, c only 3, p = 0.73 | |

POST-HOC, from N2: **all four of arm d's LOW_SHARPE passes, and 18 of its 27 y08 rows, came from settings OUTSIDE
the grid arms a–c were drawn from** (truncation 0.15 or decay 16). Inside the same settings support, arm a's rates
are above arm d's (y08 10.9 % vs 4.4 %). So round 1's a-vs-d comparison is confounded by settings as well as by the
ingredient mix. Which of truncation, decay or the incumbent's hypotheses carries it: MECHANISM: UNKNOWN. The mined
frames' own modal settings (framelib entries, settings.source = canonical-modal) often carry truncation 0.15, and
the round-1 grid excluded it — a design limitation of round 1, recorded here, not a result.
