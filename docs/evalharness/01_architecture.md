# evalharness — architecture, draw 1 (2026-09-23)

This is the first drawing, written to be attacked. D15 says it is finished when two consecutive
adversarial rounds find no new defect; one round has not yet run against it.

## 1. The three systems and what separates them

```
            ┌──────────────────────────── THE PIPELINE (what is judged) ────────────────────────────┐
            │  library YAML → planner → allocator → type gate → dispatcher → harvest → robustness   │
            │       ↑            │                                              │          │        │
            │   fingerprint ─────┘ (pre-sim novelty)                            ↓          ↓        │
            │                                                     correlation probe → submitter     │
            └────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                 │ writes: journal, scored, corr, submit ledger
                                                 ↓
            ┌──────────────────── THE SCORECARD (forge/offline/benchmark.py) ──────────────────────┐
            │  axis 1 product      axis 2 throughput      axis 3 gearing                           │
            │  DSR · PBO ·         per 5,000 scored ·     fitness functions ·                      │
            │  neighbourhood ·     Wilson · families ·    DORA · branch drill                      │
            │  regime · 8 gates    diversity · repeat                                              │
            │                    ↓ hard floors, no compensation ↓                                  │
            │                 verdict PASS/FAIL  +  composite 0–100 (ranking only)                 │
            └────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                 │ the composite is the gate's regression signal
                                                 ↓
            ┌──────────────────────── THE GATE (tools/ci_gate.py) ─────────────────────────────────┐
            │  no-live · schema · version · fitness · tests · regression                           │
            │        ↓ PASS                                                                        │
            │  tools/deploy.py: existence probe → snapshot → rsync → smoke → manifest → restart    │
            │        ↓ smoke red                                                                    │
            │  rollback: extract first, then remove only what was genuinely new                     │
            └──────────────────────────────────────────────────────────────────────────────────────┘
```

The separation that matters: **the thing judged never imports the thing judging it.** `forge/` has no
dependency on `benchmark.py` or `ci_gate.py`, so the scorecard cannot influence what it scores. The
arrow from the scorecard to the gate carries one number, the composite, and that number can only
block a merge — never change a simulation.

## 2. Why each piece is where it is

| piece | why not somewhere else |
|---|---|
| the scorecard reads FILES, not the live loop | the loop must be scoreable after the fact, from any machine, and a scorer that has to be running when the thing happens measures only what it was awake for |
| the gate is a Python module, not YAML steps | the same command must give the same verdict on a laptop, on the host and in Actions; a gate that only exists inside a CI runner teaches people to distrust it |
| the version is a content hash | a tag is a promise someone remembers to keep; the bytes are what ran. `/opt/wq` is not a git repo and drifted 13 days without anything reporting it |
| the version is stamped by the PLANNER | the alternative — attributing by time window — puts a hand-rsynced tree's alphas in the wrong bucket, which is exactly what this desk did for 13 days |
| deploy refuses while a round dispatches | swapping code under a live round produces alphas that no version can claim, which destroys D14 |
| the novelty index fails closed | an index that could not read a submission does not mean "novel"; a submission slot is one of four in a day |

## 3. The flows that are not obvious from the diagram

**A submission has two owners.** The alpha was produced by the version that planned it; the POST was
made by the version whose submitter ran. `rK5RGeqa` was generated 09-10 and POSTed 09-23. Axis 2
reports both and collapses neither, because D14 asks the first question and "did we get four today?"
asks the second.

**The correlation probe is asynchronous and the pipeline did not know it.** `GET
/alphas/{id}/correlations/{kind}` answers 200-with-an-empty-body while it computes and returns the
payload on a later call. `forge/probe.py` treated the empty body as an answer, so an alpha whose
correlations were both comfortably under the lines was skipped every round. Measured 2026-09-23;
`read()` now retries.

**The gate's regression signal is the only part of the scorecard that can stop anything**, and it
compares against a recorded baseline rather than against the floor. At a measured 0.48 submissions
per 5,000 against a floor of 4, a gate on the floor would block every merge for months.

## 4. What this drawing does NOT yet contain

- **DORA has no data.** Lead time, deploy frequency, change-failure rate and MTTR need at least two
  recorded deploys, and `DEPLOYED.json` does not exist on the host because `tools/deploy.py push` has
  never been allowed to run.
- **The branch drill is not implemented.** Axis 3 scores the fitness functions alone, so it is
  currently answering "is the architecture extensible in principle" rather than "did a real branch go
  through the gate this release".
- **The deploy half of CI/CD is not wired to Actions.** Deliberate: `tools/deploy.py` has failed two
  audits (91 defects) and must not be driven unattended against the host that holds the only journal.
- **The Actions workflow is not in `.github/`.** The OAuth token lacks the `workflow` scope, so the
  file sits at `ci_pending/ci.yml` in the pushed repository until that scope is granted.
- **22 of 247 tests cannot run on a hosted runner.** They need a 101 MB label file and a 50 MB
  catalogue. The gate names them rather than hiding the gap.

## 5. The attack surface for the next adversarial round

Where I expect a reviewer to find something, written before they look:

1. The scorecard reads the journal by alpha id with "last row wins". Orphan recovery writes second
   rows. Does any axis double-count, and is the dedupe the same one `rung_report` uses?
2. `axis1_product` scores only what a version SUBMITTED. With zero submissions the floor is unmet —
   but is "no product" really the same verdict as "bad product", and does the composite treat them
   identically?
3. The composite divides by the floor. An axis whose floor is 4 and whose value is 40 clamps to 1.0,
   so ten times the goal and exactly the goal score the same. Is that intended? It hides progress
   above the line.
4. `neighbourhood_stability` groups peers by (hypothesis, region, delay, category) — which is not the
   same key the allocator uses, and not the mechanism key either. A third key for the same idea.
5. `check_no_live` greps for a string. A test that builds the flag from parts passes the check.
6. `check_regression` writes the baseline on first run, so the first run can never fail it, and
   nothing stops a change from rewriting `state/ci_baseline.json` to lower the bar.
