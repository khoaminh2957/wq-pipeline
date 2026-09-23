# Hypothesis library — authoring rules

One YAML per hypothesis. The loop has no LLM (C7); these files ARE the generator's ideas.

- `source` starts with `EX-ANTE`, `SOURCE`, `POST-HOC` or `SPECULATION` (RULE 0) and names the
  paper or platform fact. A hypothesis written after seeing a result is POST-HOC.
- `mechanism` states who loses money to this alpha and why they keep doing it (`counterparty`).
- `signal.fields` are exact catalogue ids (verified 2026-09-04 against USA_TOP3000_d1). The
  factory keeps only fields present in the target segment's catalogue, so a hypothesis silently
  yields nothing where its dataset is absent — the m13 queue alert reports expansion counts.
- VECTOR fields need `signal.vector` (one of the 7 platform vec ops): counts → `vec_sum` /
  `vec_count`, scores → `vec_avg`, already-aggregated counts of unknown layout → `vec_max`.
- SPARSE signals need `signal.density` (measured on the 2026-09-04 canary: a NaN-for-no-event
  signal ranks into a 3–20-name book and fails CONCENTRATED_WEIGHT): `zero` when a missing
  value IS zero (counts, transaction values), `backfill` (+ `density_window`) when it means
  "no new reading yet" (scores). Dense daily MATRIX fields need nothing.
- Quarterly / slowly-updating fundamentals are carried with `ts_backfill({signal}, w)` inside the
  template (w 63–126); daily model scores use w 5–21.
- Khoa 2026-09-04: dense MATRIX hypotheses first; VECTOR ones live in `later/` until the dense
  ones are validated live. No POST-HOC sign flips: a hypothesis whose sign the data contradicts
  is recorded in 02_design and left alone.
- Templates are ≤ 5 operators per leg (community consensus; complexity is scored, not capped).
  The sign of the bet is written INTO the template (leading `-`), `sign` documents it.
- `delays: [0, 1]` unless the mechanism depends on timing (pre-market news → `[0]`).
- Nothing here has been measured. The canary (200 live sims) and the 10,000-sim milestone are
  the experiments; results are recorded per hypothesis id in the journal `meta`.
