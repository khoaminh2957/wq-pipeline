# evalharness — the funnel as it actually is (measured 2026-09-22 23:35, VPS journal)

Source: `/opt/wq/state/layered/runs/forge.jsonl`, one row per distinct alpha id (last row wins),
`state/forge/corr.jsonl` for the correlation readings, `state/forge/submitted.jsonl` for the POSTs.
Everything below is MEASURED. The section that says UNKNOWN says it because no experiment here
distinguishes the candidates.

## 1. Where the 25,743 scored alphas go

DENOMINATOR, stated before the table (the research brief caught this class of error and I had made it
too): 25,743 is the count of DISTINCT ALPHA IDS carrying a check set, not the count of simulations
spent. Those differ — a simulation that errored, was cancelled, or was re-run against the same
construction spends quota without adding a distinct checked alpha, and no sim-slot ledger exists for
the forge era to reconcile them. Every share below is therefore "per scored alpha"; anyone who needs
"per simulation" must first build that ledger.

| stage | surviving | share of scored alphas |
|---|---|---|
| scored: distinct alpha ids with a check set | 25,743 | 100 % |
| Sharpe at or over the row's own bar | 902 | 3.50 % |
| **every binding check PASS** | **34** | 0.13 % |
| submitted | 3 | 0.012 % |

Binding = LOW_SHARPE, LOW_FITNESS, LOW_SUB_UNIVERSE_SHARPE, IS_LADDER_SHARPE, CONCENTRATED_WEIGHT,
HIGH_TURNOVER, LOW_TURNOVER (`forge/score.py`'s NON_BINDING list, inverted).
The largest single death pattern at the bar is FITNESS + IS_LADDER together: 544 rows, 2.11 % of all scored
alphas — more than every other failure pattern combined.

## 2. The 34 that passed everything are only 7 structural families

Clustered with Khoa's `fingerprint.py` (`StructuralIndex`, the containment + similarity rule he
validated on 20 and then 23 re-simulated alphas):

| family (representative) | alphas | hypothesis |
|---|---|---|
| akLMOLZW | 10 | options_x_short |
| om6AY6Ml | 8 | options_x_short |
| le8A7b1O | 7 | ownmultiple_x_profitability |
| 883RKPpV | 4 | ownmultiple_x_profitability |
| Vk67oQ5V | 3 | usa_insider_x_ivspread_x_profitability |
| rK5RGeqa | 1 | usa_insider_x_ivspread_x_profitability |
| gJboG8mv | 1 | usa_insider_x_ivspread_x_profitability |

**7 families out of 3 hypotheses, from 25,743 scored alphas** — about 3,700 scored alphas per family that
reaches full qualification. Since a submission retires its whole structural family, the number of
families, not the number of qualified alphas, is what the submission count can ever be drawn from.

## 3. Which line actually kills them — the experiment that distinguishes

Of the 31 fully-qualified alphas that were never submitted, every one carries a numeric correlation
reading (none is unmeasured), and:

| breached line | count |
|---|---|
| SELF only — our own three submissions | **0** |
| PROD only — the platform's production book | **29** |
| both | 2 |

PROD median 0.795 against a 0.70 line; SELF median 0.546. SELF ≥ PROD on 1 of 32 readings.

**The binding wall is PROD, and PROD is other people's alphas.** Our own book blocks essentially
nothing — which is unsurprising with three submissions, and will not stay true as the count grows.

**MECHANISM of the high PROD: UNKNOWN.** Candidates, none distinguished by any experiment on file:
(a) the three hypotheses that qualify sit on datasets the platform's crowd already mines heavily;
(b) the constructions are conventional — rank, ts_mean, multiply — so the book they produce resembles
many others regardless of the data; (c) the production book is simply dense enough that any
well-behaved USA/d1 equity alpha correlates with something in it. The one controlled result on file
is that within a single mechanism and a single field set, **neutralisation moved PROD by ~0.19**
(STATISTICAL 0.54 vs SUBINDUSTRY 0.71–0.73, `docs/harness5/round_3/prod_vs_self.md` §3b) — a lever we
hold, whose mechanism is equally UNKNOWN.

## 4. What this does to the agreements

**D18 (the no-reuse rule) references the wrong book, and the record should say so.** Khoa's rule is
"ko tái sử dụng các cấu trúc các alpha đã được nộp" — the structures of *our* submissions, which is
the SELF book. SELF killed 0 of 31. Keeping the rule costs nothing and prevents a wall that will
arrive once the submission count rises, so `forge/novelty.py` stays; but it must not be described as
the lever that unlocks submissions, because the measurement says it is not.

**The lever the measurement does point at** is whatever lowers PROD: settings (neutralisation is the
one measured mover), and genuinely uncrowded data. Neither is established as *causing* low PROD.

**Axis 2's denominator should change.** "Submissions per 5,000 scored alphas" has 3 events in the desk's entire
history and cannot be estimated. "Distinct structural families reaching full qualification per 5,000
scored alphas" has 7, and it measures the quantity that actually bounds submissions. Both should appear on the
scorecard; the second is the one with enough events to move.

## 5. What is NOT established here

- Why PROD is high (§3). No experiment run.
- Whether a family that reads PROD ≥ 0.70 can be moved under the line by settings alone — the ~0.19
  neutralisation effect was measured on one mechanism, n small, and never tested as a remedy.
- Whether the 3,700-scored-alphas-per-family rate is a property of the library or of the allocator; the two
  have never been separated.
