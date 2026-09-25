# frames — Khoa's decisions (ticks)

## F1–F4 (Khoa, 2026-09-24 ~17:00 +07), before live round 1

- **F1 — round 1 has four arms, about 320 alphas each (~1,300 sims), randomised within the same day and
  settings:** (a) library frames x unseen fields from their own role pools; (b) library frames x fields of
  the same slot kind from OTHER datasets; (c) non-library frames x the same fields as (b); (d) the current
  generator. Size from docs/frames/10_frames_discovery.md §6 (5 % vs 15 % LOW_SHARPE pass, ICC 0.32,
  design effect 2.3, >= 60 frames per arm).
- **F2 — the incumbent loop pauses while an experiment round runs** (stopped at a round boundary, restarted
  after, as vps/c11_run.sh does); the rest of the day's quota stays with it.
- **F3 — experiment rounds have NO submit step.** An experiment alpha that clears every check (correlation
  included) is listed with its decidable gates, and Khoa ticks each one before any POST. Experiment rows go
  to their own journal so the incumbent's harvest and submit never see them.
- **F4 — round 1 now, round 2 tomorrow** (replication on FRESH fields for frames above and below the line,
  to measure regression to the mean), then one round a day adding new frames, until a pre-registered
  boundary is crossed.

- Round 1 pre-registration: docs/frames/13a_preregistration_round1.md, sha256 b45ea1ecdfe8df87fdbac23380770005be976f626d16b2e78972245102ce2531, written 2026-09-24 17:02:36 +0700 before any round-1 row existed (driver waiting for auth since 17:01:51).

## Round 1, attempt 1 aborted; attempt 2 = FRAMES-R1B (2026-09-24 ~17:55 +07), recorded BEFORE any R1B row

- Attempt 1 (FRAMES-R1, journal frames_r1.jsonl) started dispatching 17:3x and was stopped by the orchestrator at
  17:39. Observed: children failing with "Invalid data field" (fnd65_* fields: 404 on GET /data-fields/<id>) and
  "unknown variable" (ml_factor_proj: dataset not offered for USA/TOP3000/d1 today; creditworthiness_letter_rating_
  numeric_main from arm d, the incumbent's own library), and every such child cancelled its whole multisim parent,
  siblings from other arms included (both first parents: 1 ERROR + 9 CANCELLED). Its rows are EXCLUDED from every
  pre-registered analysis and reported separately.
- Fixes, none of which touches the pre-registered questions, outcomes or tests (13a):
  1. the field library is pruned to the 293 datasets GET /data-sets offers for USA/TOP3000/d1 today (5,696
     catalogue fields removed); a random 120 of the 933 plan fields then all resolved in today's catalogue
     (GET /data-fields?dataset.id=..&search=..), 0 not found;
  2. every multisim parent holds ONE arm (blocks of 10 of one arm, blocks shuffled), so a cancellation stays
     inside the arm that caused it; each arm is trimmed to a multiple of 10;
  3. new seed 20260925 (plan_abc_v2: a 320, b 316, c 262; d planned at run time), journal frames_r1b.jsonl.

- Round 1 (FRAMES-R1B) read out 2026-09-24 ~20:00 in docs/frames/20_round1_result.md. Doc 13 (governs round 2 onward), sha256 466c0c1b717ef8b421f16cdfd05126d0e9750480e0ee1a4a3abaa71e904deafd, recorded 2026-09-24 19:53 +0700, before any round-2 row.

- Round 2 plan (FRAMES-R2): plan_abc_FRAMES-R2.json sha256 6ebed3db39126cb74a4e326d7547a42e83753ac9f8b5255d2f7d26433e4ef13b — a 680 own-role fills over 85 frames (15 frames had fewer than 8 fresh own-role fills), b 392 other-dataset fills over 100 frames; every fill fresh (no field used with that frame in R1B, not in history); dataset-availability filter as R1B; single-arm parents. Scheduled on the host for 2026-09-25 11:05 +07 (systemd timer frames-r2), after the quota reset; the driver waits for auth. Recorded 2026-09-24 19:55 +0700, before any R2 row.

## F5–F8 (Khoa, 2026-09-24 ~20:15 +07), after the round-1 read-out

- **F5 — the frame library REPLACES the current pipeline** ("Thay pipeline hiện tại bằng thư viện khung và cải
  tiến + tích trữ + tạo mới"): the incumbent forge loop is stopped entirely; the quota goes to a frames loop that
  keeps improving the library, accumulating evidence and alphas, and creating new frames.
- **F6 — no control arm.** Consequence stated on the tick and recorded here: with no incumbent running on the same
  days, the proof criterion below can only be computed against the incumbent's HISTORY; the round-3 audit measured
  that a sequential (different-day) comparison reads better/worse ~50 % of the time under no effect. Every
  comparison with the incumbent from now on is DESCRIPTIVE, not RULE 2 gate-3 evidence. The only same-day
  comparison on file is round 1 (docs/frames/20_round1_result.md).
- **F7 — proof criterion (doc 13 Q4 A):** gate 3 = y08 (Sharpe >= 0.8 x its bar) better with a lower bound >= 1.5x;
  gate 4 = all 7 binding checks better; tested y08 -> LOW_SHARPE -> D24. Under F6 it has no same-day comparator.
- **F8 — 25 new frames a day**, screened on day t and replicated on fresh fields on day t+1 (doc 13 Q7 A).
- **F9 — frame alphas are submitted automatically once they pass the D39 decidable gates** (forge/meaning.py), after
  that route is wired into the frames loop's submit step and tested; until then nothing is POSTed. Every other
  submit rule stays: D18 novelty (fail-closed), the correlation lines with a fresh re-read, the shared 4/day ledger,
  the 403 budget.

## F10 (Khoa, 2026-09-25 ~14:30 +07): a frame carries its own settings, checked in pairs

- Each library frame carries a SETTINGS PROFILE (neutralization, decay, truncation), starting from its historical
  modal settings (mined frames) or the designer's declared settings (novel), and learned over rounds. A share of
  every round's fills runs as PAIRS -- the same fields at the frame's own profile and at a reference profile --
  so the loop can tell whether an advantage belongs to the structure or to the settings. D51's neighbour check
  runs one setting away from the profile.
- Evidence behind the question (POST-HOC, 20_round1_result.md N2 and a history count on 2026-09-25): all four of
  the incumbent's round-1 LOW_SHARPE passes used settings outside the grid arms a–c were limited to (truncation
  0.15 / decay 16); in the forge history truncation 0.15 was only ever used with option/short-sale fields
  (y08 33.7 % at 0.15 vs 21.4 % at 0.08 for those fields; LOW_SHARPE 7.0 % vs 7.6 %), and only 4 frames ever ran
  at both truncations, so the history cannot separate frame from settings. MECHANISM: UNKNOWN.

## F11–F13 (Khoa, 2026-09-25 ~15:50 +07): frames from the 245 submitted alphas

Measured before the tick (read-only API, 2026-09-25 15:4x): the account holds 245 ACTIVE alphas (submitted
2026-03..09; 243 USA, 2 JPN); FRAME SPEC v1 gives 233 distinct frames from the 236 that parse (9 do not), 226
shapes; 1 is in the 100-frame library and 7 in the canonical corpus. Their settings are mostly SECTOR / SUBINDUSTRY /
INDUSTRY with decay 10–20; universes TOP3000 135, TOP500 49, TOP2000 46, TOP1000 6, TOP200 3.

- **F11 — screen all of them in the first one or two days:** each frame, at its OWN settings (F10), gets 4 fresh
  fills (~930 sims); frames above the screening line are replicated on fresh fields the next day; then the loop
  returns to 25 new frames a day (F8).
- **F12 — fields come only from datasets the original submitted alpha did not use**, so the D18 fingerprint differs
  and self-correlation with the original stays low (Khoa's no-reuse rule).
- **F13 — a frame keeps its original universe** as part of its settings profile; field availability is checked for
  that universe.

- FRAMES-R3S pre-registration: docs/frames/13c_preregistration_r3s.md sha256 482e06ae807060a8c6203d6574b15dcdfe34c7e05fb3049556fd152e246edf8a; plan sha256 c4cfcec822153137414dd44c0c7816ac7063833e36d6577a3846796df74a4300; recorded 2026-09-25 15:40 +0700, before any R3S row.

## FRAMES-R3S deviation: a top-up screen, FRAMES-R3SB (recorded 2026-09-25 16:18 +0700, before any R3SB row)

- R3S (16:06–16:14) scored only 340 of 720: 46 fills used catalogue-type GROUP fields in signal slots, the platform
  rejected each ("Incompatible unit ... found Unit[Group:1]"; 47 ERROR) and every rejection cancelled its parent
  (303 CANCELLED, 30 FAIL). forge.typed's structural gate let them through. Only 49 of 184 frames reached the
  pre-registered 3 scored rows.
- Fix: GROUP-type fields never fill a slot (a frame's group arguments are its verbatim group tokens). The 135 frames
  with fewer than 3 scored rows get 4 NEW fresh fills each (540 sims, seed 20260929), same rules otherwise (13c).
  The screen is read on R3S + R3SB rows together; the line, the replication and the test stay as 13c fixed them.
  Plan sha256 4c30ce4adfae73f5d4d71afc6c049c5a2d9fda0a6727413877d2d8f349092f40.

## F14 (Khoa, 2026-09-25 ~17:00 +07): replicate the screen AND add a same-dataset arm

After R3S+R3SB (docs/frames/22_r3s_result.md: 0.84 % y08 with other-dataset fields), the next ET day runs:
(1) the pre-registered replication of 13c (the 37 frames above the line + 37 random below, 4 fresh OTHER-dataset
fills each); (2) a new arm on the SAME 74 frames: 4 fills each with DIFFERENT fields from the SAME datasets the
original alpha used (per slot), at the same settings; and self-correlation of that arm's y08 rows against their
original submitted alpha is read, so the cost of the no-reuse rule is measured, not assumed.

- FRAMES-R4 pre-registration: docs/frames/13d_preregistration_r4.md sha256 8e144d1751ab0d57986e15ac91c2780e193f68992832be45417e1b28bf1a204d; plan sha256 e4e38a63b4409fe549c410931648c22583f91ba66c43784d63d86e2b9b2cd48e (rep 296, same 216); timer 2026-09-26 11:05 +07; recorded 2026-09-25 17:06 +0700, before any R4 row.
