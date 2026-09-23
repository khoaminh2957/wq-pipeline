# Redesign — 01. Requirements fixed by Khoa's 30 answers (2026-08-31)

Every line is an operator decision, quoted or paraphrased from the tick answers. Nothing here is
mine. Where an answer changed a previous ruling, the newer one stands.

## Objective (C1–C4)
- **Success = number of submittable alphas + pyramid cells unlocked.** OS survival cannot be
  observed on this platform for consultants (C25: "OS sẽ ko hiện nên ko thể đo") — so OS quality
  is a HYPOTHESIS backed only by ex-ante robustness proxies, never a measured label.
- Fill **4 submits/day** when eligible stock exists; standards are never lowered to fill.
- Sim budget: **up to the full 5,000/day** (the shortfall so far was auth coverage, not policy).
- Judge by **data milestones, not calendar**: after **10,000 sims: ≥ 10 submittable AND ≥ 2 new
  pyramid cells**; below that I report and propose fix/kill via tick.

## Generation (C5–C8)
- **Hypothesis first, then directed search.** Every alpha starts from a written economic
  hypothesis; search is a small neighbourhood around it.
- **No hard complexity cap**; complexity is penalised through DSR and novelty scoring.
- **No LLM in the running loop.** The pipeline must run fully automatically without me; my job
  is to build it, then occasionally inspect, improve, fix. Therefore hypotheses are authored
  OFFLINE into a machine-readable library the engine expands deterministically.
- **Keep the infrastructure** (auth chain, notifier, sim runner, submit chain, recorder); replace
  the generator and the scoring entirely (climb, ladder, seven moves retire).

## Data & regions (C9–C12)
- Prefer **uncrowded datasets, weighted 1/√users**; crowded datasets allowed only with a distinct
  economic logic.
- **Multi-region driven by EMPTY pyramid cells** (region, delay, category with alphaCount < 3).
- **d0 and d1 equally**: every hypothesis is tried on both delays.
- **Hard novelty filter before sim**: a candidate whose signature (dataset + mechanism) matches a
  submitted/ACTIVE alpha is not simulated.

## Robustness scoring (C13–C16)
- **DSR ≥ 0.95 is a hard gate** before correlation measurement and before submission
  (N = candidates in the same selection pool; PnL from recordsets; skew/kurtosis corrected).
- Platform gate **PASS is sufficient** — no extra margin demanded on sub-universe/ladder.
- Turnover target **2–25%**; a candidate above 25% is retried with decay before it is dropped.
- **Second-best rule**: within one hypothesis, if the top two configs differ by < 10%, the
  second-best is the one submitted.

## Correlation & portfolio (C17–C20)
- Measure correlation on **every** candidate that passed DSR + novelty; no fixed cap; re-read
  ~120 s after trigger (measured compute time) instead of a fixed 900 s.
- Submit **everything under the platform's prod-corr line**; queue ordered by lower corr first.
- **Max 1 submit per signature (dataset + mechanism) per week.**
- Submit order: **empty pyramid cells first, then robustness score.**

## Automation & operations (C21–C24)
- Unattended submit rule = all gates PASS + corr under lines + DSR ≥ 0.95 + MATCHES_PYRAMID PASS +
  1/signature/week + second-best rule. Nothing more.
- Auth: **one stable URL on the VPS** (long random path) that redirects to the live persona link,
  minting on the spot if none is live; mitigations = long token + mint cap.
- **CDP survey of the platform UI comes BEFORE building** — Khoa re-enables the Chrome extension.
- Notifications: auth link (hourly law), m6 on every POST, **one daily digest at 11:00**
  (submits, pyramid cells, sims, submittable/1,000 sims, DSR stats), and **hypothesis-queue
  alerts** (new batch loaded / queue running low). No OS-decay alert (unmeasurable).

## Evaluation & testing (C25–C28)
- OS cannot be observed → no OS tracking module; robustness proxies only, labelled as proxies.
- **Replace outright**; the control is the measured baseline in 00_baseline_and_research.md.
- **Canary**: the first 200 live sims run with Khoa watching before unattended mode.
- **Daily regression tests on the VPS** with a Discord alert on failure.

## Risk & prohibitions (C29–C30)
- **≤ 1 lost slot (403) per week is acceptable**; beyond that the submitter switches to
  hold-for-approval and reports. Read corr immediately before POST (reading ≤ 30 min old).
- **No price carrier (close/open) as a base.**
- **No paid LLM API calls inside the running loop.**
- Otherwise: my call, within the 29 answers above.
