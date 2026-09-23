# wq-pipeline — the alpha forge, its scorecard, and the gate between them

An automated research pipeline that constructs equity alpha candidates, simulates them on an external
platform under a hard daily quota, and submits the few that clear every check. This repository holds
the code and the documents; it holds no simulation data and no credentials.

## What is here

| | |
|---|---|
| `forge/` | the pipeline: library → planner → allocator → type gate → harvest → robustness → correlation → submit |
| `forge/offline/benchmark.py` | the three-axis scorecard (product / throughput / gearing) |
| `tools/ci_gate.py` | what a change must clear before it may reach the pipeline |
| `tools/deploy.py` | version identity by content hash, snapshot, smoke, rollback |
| `vps/` | the loop driver and the auth daemon that run on the host |
| `docs/evalharness/` | the agreements of record, the research brief, the measured funnel, the audits |

## The scorecard, and why it reads FAIL

Three axes, each with a **hard floor that cannot be compensated** — a strong axis may never hide a
dead one, which is how most benchmarks quietly stop meaning anything:

1. **Product** — is the alpha robust and trustworthy, with out-of-sample performance never observable?
   Deflated Sharpe, PBO/CSCV, parameter-neighbourhood stability, regime stability, and the hypothesis
   standard's eight hard gates.
2. **Throughput** — four submissions a quota day? how many scored alphas per submission? and is the
   rate sustainable or luck? Answered only when a Wilson interval excludes zero, the submissions span
   more than one mechanism, and the rate held in the previous window too.
3. **Gearing** — can branches be grown onto this pipeline? Architecture fitness functions that fail a
   build, DORA metrics, and a branch drill.

The floor on axis 2 is four submissions per 5,000-simulation day. The measured rate is 0.48. Every
scorecard therefore reads **FAIL**, and it is meant to: the floor states the goal, while the 0–100
composite ranks attempts against each other. The gate blocks on *regression*, never on the floor —
a gate on the floor would freeze all development.

## What the numbers do not say

Out-of-sample performance is never returned by the platform, so every robustness measure here is an
in-sample consistency test. Whether any of them predicts out-of-sample behaviour is **UNKNOWN**, and
the scorecard says so on every run rather than in a footnote.

Rates are per **scored alpha** — a distinct alpha id carrying a check set — never "per simulation".
No sim-slot ledger exists to convert between them.

## Running it

    python3 tools/ci_gate.py            # the gate: tests, no-live, schema, version, fitness, regression
    python3 forge/offline/benchmark.py  # the scorecard for the current tree
    python3 tools/deploy.py version     # what this tree's code hashes to

22 of the 247 tests load a 101 MB label file and a 50 MB field catalogue that cannot live in a git
host. CI runs the other 225 and **names the ones it skipped**; those are covered by the deploy smoke
on the host that has the data.
