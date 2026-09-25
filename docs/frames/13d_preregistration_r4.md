# FRAMES-R4 pre-registration — replication of the submitted-frame screen, and the same-dataset arm (F14)

Written 2026-09-25 ~17:15 +07, before any R4 row. Sha256 recorded in 00_decisions.md. Runs the next ET day (timer
2026-09-26 11:05 +07), no submit step, no incumbent (F5).

## Arms (same 74 frames: the 37 above 13c's line + 37 drawn below it, seed 20260928)

| arm | fills | planned |
|---|---|---|
| rep | 4 fresh fills per frame from datasets the original alpha did NOT use (13c's replication, F12) | 296 over 74 frames |
| same | 4 fills per frame from the SAME dataset as the original field, slot by slot, never an original field (F14) | 216 over 54 frames (19 frames had fewer than 4 such fills, 1 none) |

Every row keeps its frame's original settings and universe (F10, F13). GROUP-type fields never fill a slot.

## Tests (fixed now)

1. **13c's claim (robust vs luck), on arm rep:** a frame is robust when it was above the line on day 1 and is strictly
   above the replication-day median of the 74 replicated frames by (LOW_SHARPE rate, mean Sharpe/limit, id);
   the robust count is compared with a permutation null (replication scores shuffled across the 74 frames, 10,000),
   one-sided p < 0.05.
2. **F14's question (does the dataset carry the signal?):** within the frames that have >= 2 scored rows in BOTH
   arms, the per-frame difference in y08 rate (same minus rep), sign-flip permutation over frames (10,000),
   two-sided p < 0.05; the mean difference with a frame-bootstrap 95 % interval. Printed beside it: the same on
   mean Sharpe/limit.
3. **The cost of the no-reuse rule (reported, not tested):** for every arm-same row at or above 0.8 x its bar, the
   platform SELF-correlation against its original submitted alpha where the probe returns it, and the share at or
   over the SELF line.
Rows that do not score count as failures and are reported per arm.
