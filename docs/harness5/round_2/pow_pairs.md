# harness5 — round 2 · POW: paired signed_power twins (run 2026-09-09 14:50–15:03 local, VPS)

Khoa's tick (14:50): "Chạy ngay hôm nay". 300 sims through `forge/offline/pow_pairs.py build` →
`--plan state/forge/plans/pow.json` (driver `vps/pow_run.sh`, wq-forge stopped at its round boundary
and restarted by trap). Design and predictions were written in the module docstring BEFORE the run.

## Design (paired)
150 base rows from the journal (USA/d1, COMPLETE, Sharpe ≥ 1.4, no prior wrap, distinct constructions):
50 `usa_short_x_profitability_x_accruals` (pure-σ case, turnover ≈ 0.10), 50 `options_x_short` at
STATISTICAL (positive control), 50 `ravenpack_x_short` (the round-1 bar-reacher). Each base got two
twins with identical settings: `signed_power(f, 1.5)` (arm pow15) and `signed_power(f, 2)` (arm pow2).
The base is the journal row itself (simulations are deterministic: diagnosis_ladder.md §3c). All 300
twins landed COMPLETE.

## Predictions (EX-ANTE, diagnosis_fitness.md §7 L1) vs result
| | predicted | pow15 measured (n 150) | pow2 measured (n 150) |
|---|---|---|---|
| σ = \|returns\|/Sharpe, Δ p50 | +10 % / +20 % | **+4.9 %** [IQR +3.7, +7.6] | **+10.6 %** [+9.0, +17.7] |
| Sharpe Δ p50 | within ±0.1 | **−0.11** [−0.17, −0.04] | **−0.23** [−0.31, −0.10] |
| fitness Δ p50 | ×1.05 / ×1.10 | **−0.06** | **−0.13** |
| rows with fitness ≥ 1 (base → twin) | rise | 14 → 1 | 14 → 0 |
| all-binding passes (base → twin) | rise | 2 → 0 | 2 → 0 |
| CONCENTRATED_WEIGHT fails | 0 | 0 | 0 |

Per stratum (pow15 / pow2): options×short σ +4.4 % / +10.3 %, Sharpe −0.18 / −0.31, fit≥1 13→1 / 13→0,
ladder window cleared 10→0 / 10→0; usa_short σ +9.0 % / +20.2 %, Sharpe −0.11 / −0.25, fit≥1 1→0 / 1→0;
ravenpack σ +3.4 % / +6.5 %, Sharpe −0.02 / −0.07, fitness −0.01 / −0.04.
Sub-universe PASS rose 83 → 99 / 104 (options×short 8→14/17, ravenpack 25→35/37, usa_short 50→50):
the lever is NOT σ-free on that check, contrary to the §6 expectation. Pattern, MECHANISM UNKNOWN.

## Verdict
**REFUTED on its own pre-stated criteria** (σ gain < 5 % at y 1.5; Sharpe p50 falls 0.11–0.23; fitness
falls; all-binding passes fall 2 → 0). fitness = Sharpe^1.5·√(σ/max(tvr, 0.125)): the Sharpe loss (−7 %
to −14 % at Sharpe 1.6) outweighs the σ gain (+5 % to +11 %) at both powers, on all three mechanisms.
signed_power as a fitness lever is DEAD; R17/R18/R23's "unresolved" at n 40 is resolved at n 150 pairs.
The tail-concentration route to σ is closed; the only measured large σ lever remains the
neutralisation choice (diagnosis_fitness.md §3), which is mechanism-specific in its Sharpe cost.

Side observation (POST-HOC, not a lever): sub-universe retention rose under signed_power on the IV
and tone mechanisms. A σ-free check moved with a σ lever, so "σ-free" was a wrong EX-ANTE reading of
that check; recorded for the sub-universe diagnosis (round_2/subuniverse.md §5), no mechanism claimed.
