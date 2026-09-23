# harness5 — track C: robustness / OOS statistics + BRAIN platform facts

Researcher agent, 2026-09-08. Vetting rule (00_agreements Q14): every source WebFetched today; URL, HTTP
status and verbatim numbers recorded; unfetchable ⇒ dropped, never cited. Labels per RULE 0:
`EX-ANTE` (from the paper/definition before our data), `POST-HOC` (regularity in our data), `SPECULATION`,
`ARITHMETIC` (re-computed here, script in the session log), `UNVERIFIED` (no fetchable source today).

## 0. Fetch ledger

| Source | Attempts (URL → HTTP) | Verdict |
|---|---|---|
| Bailey & López de Prado, *The Deflated Sharpe Ratio* (2014) | SSRN 2460551 → ECONNREFUSED; jpm.pm-research.com/content/40/5/94 → 403; **davidhbailey.com/dhbpapers/deflated-sharpe.pdf → 200** (PDF, text extracted with pdftotext; header: "Journal of Portfolio Management, Forthcoming, 2014", version July 31, 2014) | VETTED |
| Bailey, Borwein, López de Prado, Zhu, *The Probability of Backtest Overfitting* | SSRN 2326253 → ECONNREFUSED; Semantic Scholar DOI 10.21314/JCF.2016.322 → 404; **davidhbailey.com/dhbpapers/backtest-prob.pdf → 200** (revision dated February 27, 2015) | VETTED (the *J. Computational Finance* 2017 citation itself is UNVERIFIED) |
| Harvey, Liu & Zhu, *…and the Cross-Section of Expected Returns* | academic.oup.com/rfs/article/29/1/5/1843824 → page returned navigation only; **nber.org/papers/w20592 → 200** (abstract) | VETTED (NBER WP version) |
| Harvey & Liu, *Backtesting* (2015) | SSRN 2345489 → ECONNREFUSED; jpm.pm-research.com/content/42/1/13 → 403; **people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF → 200** ("FALL 2015", JPM) | VETTED |
| McLean & Pontiff, *Does Academic Research Destroy Stock Return Predictability?* (JF 2016) | onlinelibrary.wiley.com/doi/10.1111/jofi.12365 → 403; ideas.repec.org → "No abstract"; **api.crossref.org/works/10.1111/jofi.12365 → 200** (abstract; JF 71(1) 5–32) | VETTED |
| Novy-Marx & Velikov, *A Taxonomy of Anomalies and their Trading Costs* | academic.oup.com/rfs/article/29/1/104/1843812 → navigation only; **nber.org/papers/w20721 → 200** | VETTED (NBER WP version) |
| López de Prado, *Advances in Financial Machine Learning* (book) | wiley.com → 403; onlinelibrary.wiley.com/doi/book/10.1002/9781119482086 → 403; googleapis books → 429 ×2; openlibrary.org/isbn/… → ECONNRESET; **openlibrary.org/search.json?title=… → 200** (title, author, 2018 only) | EXISTENCE ONLY — no chapter content fetched; nothing from it is used as a fact |
| Arnott, Harvey & Markowitz, *A Backtesting Protocol in the Era of Machine Learning* (JFDS 2019) | SSRN 3275654 → ECONNREFUSED; jfds.pm-research.com → 403; **api.semanticscholar.org DOI 10.3905/jfds.2019.1.064 → 200** (abstract) | VETTED (abstract only; the protocol's items were not on the fetched page) |
| Chincarini, Lazo-Paz, Moneta, *Crowded Spaces and Anomalies* (March 14, 2023) | **carloalberto.org/…/18_Chincarini_Lazo-Paz_Moneta_Crowding_Anomalies_03_14_23.pdf → 200** (text extracted) | VETTED |
| Jensen, Kelly, Pedersen, *Is There a Replication Crisis in Finance?* (JF 2023) | **api.crossref.org/works/10.1111/jofi.13249 → 200** (JF 78(5) 2465–2518) | VETTED |
| Chen & Zimmermann, *Publication Bias in Asset Pricing Research* (arXiv 2209.13623, v3 21 Sep 2023) | **arxiv.org/abs/2209.13623 → 200** | VETTED |
| Chen & Welch, *What Useful Alphas?* (arXiv 2607.06502, 7 Jul 2026) | **arxiv.org/abs/2607.06502 → 200** | VETTED (dated 2026, outside the asked 2023–25 window; included because fetchable and on-topic) |
| Lee, *Not All Factors Crowd Equally* (arXiv 2512.11913) | arxiv.org/abs/2512.11913 → 200, but "Withdrawn by author on 27 December 2025 for major revision" | DROPPED (withdrawn) |

## PART 1 — robustness statistics for unobservable OOS

### 1.1 Our numbers, and one confound found while mapping
- Sharpe bar 1.58 annual. Local transcription of the platform page gives `Sharpe = sqrt(250) * IR`
  (SUBMISSION_GATES.md); `forge/dsr.py` and `forge/pbo.py` annualise with sqrt(252) — irrelevant for rank
  statistics (PBO), 0.4 % on reported annual DSR inputs.
- Pools N = 20–900 trials (hypothesis × region/delay × category, cumulative; `forge/allocate.py::pair_key`).
- T: the task states ≈ 2,493 daily points. **POST-HOC (file inventory, 2026-09-08):** of 2,391 curves in
  `fetched/pnl/`, 2,367 have 1,236 rows (2019-01-02 → 2023-12-29) and only 24 have 2,411–2,586 rows (2014 →
  2023). T = 2,493 therefore describes a 10-year simulation window; the harvested default is 5 years, T ≈
  1,235 after differencing. Every number below is given for both. MECHANISM for the mix (setting drift vs.
  two harvesters): UNKNOWN — not investigated here.
- `ARITHMETIC`: 1.58 annual = 0.0999 daily; t = SR_daily·√T = **4.99 at T = 2,493**, **3.51 at T = 1,235**.
  Harvey–Liu–Zhu's t > 3.0 hurdle corresponds to annual Sharpe 0.95 at T = 2,493 and 1.35 at T = 1,235.

### 1.2 Papers: mechanism → verbatim result → mapping

**1. Deflated Sharpe Ratio (Bailey & López de Prado 2014).** Mechanism: the best of N zero-skill trials has
a positive expected Sharpe; the DSR is the probability that the selected trial's true Sharpe exceeds that
luck ceiling, with a non-normality correction. Verbatim (abstract): "The Deflated Sharpe Ratio (DSR)
corrects for two leading sources of performance inflation: Selection bias under multiple testing and
non-Normally distributed returns." Verbatim (the paper's Python listing, Snippet 1):
`maxZ=(1-emc)*ss.norm.ppf(1-1./numTrials)+emc*ss.norm.ppf(1-1./(numTrials*np.e))`, `emc=0.5772156649`,
`return mu+sigma*maxZ`. The DSR/PSR expression itself (Eq. 2) lost its symbols in PDF extraction; the
fetched text confirms its inputs — "the length of the returns series (T), the variance of the SRs tested
(V[{SR}]), as well as the number of independent trials (N)", plus skewness and kurtosis — but the exact
formula is **not verbatim-verified today**; `forge/dsr.py` implements the standard form. Worked example,
verbatim: "Should the strategist have made his discovery after running only N=46 independent trials, the
investor may have allocated some funds, as [DSR] would have been 0.9505, above the 95% confidence level."
and, with Normal returns, the same DSR is reached "after N=88 independent trials". Appendix A.3, verbatim:
"It is critical to understand that the N used to compute [E[max SR]] corresponds to the number of
independent trials. Suppose that we run M trials, where only N trials are independent, N<M. Clearly, using M
instead of N will overstate [E[max SR]]." — it derives an "implied independent trials" count from the
average pairwise correlation of the trials.
Mapping (`ARITHMETIC` from the fetched formula): luck ceiling in units of √V[SR]: N=20 → 1.90σ, 50 → 2.28σ,
100 → 2.53σ, 300 → 2.90σ, 900 → 3.23σ. `forge/dsr.py::expected_max_sharpe` reproduces the paper's snippet
exactly; V[SR] is taken as IQR/1.349 of the pool's annual Sharpes (repo choice, POST-HOC-motivated, not from
the paper). Open item: the paper's N is *independent* trials; our pools are near-duplicates of one
hypothesis, so N = pool size overstates the ceiling (conservative) — the implied-N correction of A.3 is not
implemented. Direction of that bias is EX-ANTE from the formula; its size in our pools is UNMEASURED.

**2. Probability of Backtest Overfitting / CSCV (Bailey, Borwein, López de Prado, Zhu).** Mechanism: split
the T×N PnL matrix into S blocks, form every half/half split, pick the IS-best trial and read its OOS rank;
PBO is the share of splits where the IS-best is below the OOS median. Verbatim (abstract): "Standard
statistical techniques designed to prevent regression overfitting, such as hold-out, tend to be unreliable
and inaccurate in the context of investment backtests." Verbatim (Algorithm 2.3): "M is therefore a
real-valued matrix of order (T × N). The only conditions we impose are that: i) M is a true matrix, i.e.
with the same number of rows for each column, where observations are synchronous for every row across the N
trials, and ii) the performance evaluation metric used to choose the 'optimal' strategy can be estimated on
subsamples of each column." "we partition M across rows, into an even number S of disjoint submatrices of
equal dimensions." "For instance, if S = 16, we will form 12, 780 combinations." (sic — C(16,8) = 12,870;
the fetched text prints 12,780 twice; the arithmetic is unambiguous). Relative rank "ω̄c := r̄c_n*/(N + 1) ∈
(0, 1)"; "logit λc = ln(ω̄c/(1−ω̄c))"; "φ = ∫_{−∞}^{0} f(λ)dλ. This represents the rate at which optimal IS
strategies underperform the median of the OOS trials." Decision rule, verbatim: "a customary approach would
be to reject models for which PBO is estimated to be greater than 0.05." S, verbatim: "S = 16 we will obtain
12, 780 logits …, and σ[f(λ)] < 0.0045, with less than a 0.01 estimation error at 95% confidence level.
Also, if M contains 4 years of daily data, S = 16 would equate to quarterly partitions, and the serial
correlation structure would be preserved. For these two reasons, we believe that S = 16 is a reasonable
value to use in most cases." N, verbatim: "N must be large enough to provide sufficient granularity to the
values of the relative rank, ωc. If N is too small, ωc will take only a very few values … For example, if
the investor is sensitive to values of φ < 1/10, it is clear that the range of values that the logits can
adopt must be greater than 10, and so N >> 10 is required." T, verbatim: "T should be chosen to be double of
the number of observations used by the investor to choose a model configuration".
Mapping: full specification in §1.3. Note the agreed threshold 0.5 (Q21) is ten times looser than the
paper's 0.05: PBO = 0.5 is the point where IS selection carries no information about OOS rank. That is the
agreement of record; it is not the paper's rule.

**3. Harvey, Liu & Zhu (NBER w20592 / RFS 2016).** Mechanism: multiple-testing hurdle for a newly discovered
factor given hundreds of prior tests, allowing for correlation among tests. Verbatim: "The estimation of our
model suggests that a newly discovered factor needs to clear a much higher hurdle, with a t-ratio greater
than 3.0." Mapping (`ARITHMETIC`): the 1.58 bar is t = 4.99 at T = 2,493 (clears 3.0 with margin) but t =
3.51 at T = 1,235 — the bar is a t-hurdle whose strength depends on the simulation window, and the
platform's IS-Ladder evaluates 2- to 10-year sub-windows (§2.2), i.e. t ≈ 2.2 for the 2-year segment at
Sharpe 2.38.

**4. Harvey & Liu, *Backtesting* (JPM Fall 2015).** Mechanism: convert the Sharpe to a t-ratio, compute the
multiple-testing p-value, convert back → a "haircut Sharpe ratio". Verbatim: "We argue that it is a serious
mistake to use the usual 50% haircut. Our results show that the multiple testing haircut is nonlinear. The
highest Sharpe ratios are only moderately penalized, while the marginal Sharpe ratios are heavily
penalized." Independent-tests example, verbatim: "If N = 10 and we observe a strategy with pS = 0.05, pM =
0.401"; "assuming there are twenty years of monthly returns (T = 240), an annual Sharpe ratio of 0.75 yields
a p-value of 0.0008 for a single test. When N = 200, pM = 0.15, implying an adjusted annual Sharpe ratio of
0.32 through equation 5. Hence, multiple testing with 200 tests reduces the original Sharpe ratio by
approximately 60%". Mapping (`ARITHMETIC`, their Eq. 4 `pM = 1 − (1 − pS)^N`, independence assumed): at T =
2,493 the bar's pS = 6.1e-7 → pM = 1.2e-5 (N=20) … 5.5e-4 (N=900); at T = 1,235 pS = 4.5e-4 → pM = 0.009
(N=20), 0.044 (N=100), 0.125 (N=300), **0.33 (N=900)**. On a 5-year window a 1.58 selected from 900 trials
is not significant at 5 % under independence; correlated trials make pM smaller, by an amount that needs the
pool's correlation matrix (UNMEASURED).

**5. McLean & Pontiff (JF 2016).** Mechanism: compare in-sample, post-sample and post-publication returns of
published predictors. Verbatim: "We study the out-of-sample and post-publication return predictability of 97
variables … Portfolio returns are 26% lower out-of-sample and 58% lower post-publication. The out-of-sample
decline is an upper bound estimate of data mining effects. We estimate a 32% (58%–26%) lower return from
publication-informed trading. Post-publication declines are greater for predictors with higher in-sample
returns, and returns are higher for portfolios concentrated in stocks with high idiosyncratic risk and low
liquidity. Predictor portfolios exhibit post-publication increases in correlations with other
published-predictor portfolios." Mapping: the population is academic predictors, not BRAIN alphas — no
number transfers as a fact. The two transferable structures: the 26 % OOS decline is their upper bound on
data-mining shrinkage (our DSR/PBO address the same quantity); and "post-publication increases in
correlations" is the mechanism the platform prices through PROD_CORRELATION (§2.7). SPECULATION only:
applying 26 % to 1.58 gives 1.17.

**6. Novy-Marx & Velikov (NBER w20721 / RFS 2016).** Verbatim: "Most of the anomalies that we consider with
one-sided monthly turnover lower than 50% continue to generate statistically significant net spreads, at
least when designed to mitigate transaction costs. Few of the strategies with higher turnover do. In all
cases transaction costs reduce the strategies' profitability and its associated statistical significance,
increasing concerns related to data snooping." Mapping: the platform's turnover band 0.01–0.70 is a *daily*
two-sided fraction of the book; 50 %/month one-sided ≈ 2.4 %/day one-sided, so nearly every platform alpha
sits in their "higher turnover" class. Their cost model is not the platform's; the platform's own after-cost
checks (HT_AFTER_COST_SHARPE, ILLIQUID after-cost test) are the binding measure. No number transfers.

**7. Arnott, Harvey & Markowitz (JFDS 2019).** Verbatim: "Machine learning applications often require far
more data than are available in finance, which is of particular concern in longer-horizon investing."
"capital markets reflect the actions of people, who may be influenced by the actions of others and by the
findings of past research." The protocol's numbered items were not on the fetched page — not cited. Mapping:
harness5's Q8 step "EX-ANTE hypotheses before build" and Q29 (hypothesis_standard gates before sim) are the
protocol-shaped controls we already run; nothing quantitative.

**8. 2023–2026 evidence on decay/crowding (four fetched, one dropped).** Jensen–Kelly–Pedersen 2023,
verbatim: "The majority of asset pricing factors (i) can be replicated; (ii) can be clustered into 13 themes
…; (iii) work out-of-sample in a new large data set covering 93 countries; and (iv) have evidence that is
strengthened (not weakened) by the large number of observed factors." Chen–Zimmermann (v3 2023), verbatim:
"the average correction (shrinkage) accounts for only 10 to 15 percent of in-sample mean returns and that
the risk of inference going in the wrong direction (the false discovery rate) is less than 10%."
Chincarini–Lazo-Paz–Moneta 2023 (11 anomalies), verbatim: "we find that our results remain significant after
publication dates"; crowded-quintile FF3 alpha "0.54% (6.48% annualized) with a t-stat of 8.87",
least-crowded "-0.90% (-10.80% annualized)", spread "1.44% (17.28% annualized)". Chen–Welch 2026 (≈200
anomalies), verbatim: median return "48 bp per month" through 2005, "19 bp" post-2005, "26 bp" non-micro, "7
bp" post-2005 and non-micro. Mapping: the literature does not agree on the size of decay (HLZ/MP vs JKP/CZ);
the one regularity common to all four is that post-sample and post-crowding returns are lower than
in-sample. For us this is the case for a proxy (DSR/PBO) rather than a point forecast of OOS Sharpe — no
decay percentage is adopted.

### 1.3 PBO/CSCV specification for our data (compared line-by-line with `forge/pbo.py`, which exists)
1. **Pool** = the DSR pool key `(hypothesis, region/dN, category)`, cumulative over rounds (Q30). Rows =
   every *simulated* member with a harvested PnL curve, gate-passers and failures alike (the paper: "Hiding
   trials will lead to an underestimation of the overfit"; the harness's guided search must contribute "the
   final outcome of each guided search … and not the intermediate steps" — for us each simulated formula is
   a final outcome; resims of the same formula must be de-duplicated to one column).
2. **Matrix M (T × N).** Column = daily PnL = first difference of the cumulative curve in
   `fetched/pnl/<id>.jsonl` (`[date, cum]` rows; the curve starts at 0.0). Align on the intersection of
   dates. NaN/None points are dropped *before* differencing (so a gap merges two days —
   `forge/dsr.py::daily_returns_from_curve`); a column whose date set covers < 90 % of the pool's modal date
   set is **dropped and reported**, not used to shorten the pool. `forge/pbo.py::align` currently intersects
   unconditionally — with the 5-/10-year mix of §1.1 one 10-year member is harmless, one 5-year member
   truncates a 10-year pool to 1,235 rows: change to the drop rule.
3. **S = 16**, blocks of equal length ⌊T/16⌋: T = 2,493 → 155 rows (2,480 used, 13 dropped); T = 1,235 → 77
   rows (1,232 used, 3 dropped). Drop the **oldest** rows; `forge/pbo.py` slices `rows[i*size:(i+1)*size]`
   and so drops the most recent days — reverse that (the platform's ladder weights recency; the choice is
   otherwise arbitrary).
4. **Splits:** all C(16, 8) = **12,870** combinations of 8 IS blocks; OOS = complement; both sides keep
   block order (order is irrelevant for Sharpe, the paper notes it matters for drawdown-type metrics).
5. **Statistic:** per split, annualised Sharpe of every column on IS and OOS; n* = argmax IS; OOS rank r̄ of
   n* with ties given the lower rank; ω̄ = r̄/(N+1); λ = ln(ω̄/(1−ω̄)). **PBO = #{λ < 0}/12,870.** Decision:
   submit-eligible iff PBO ≤ 0.5 (agreement Q21). Report PBO with its binomial s.e. √(p(1−p)/12,870) ≤
   0.0044 — the paper's own accuracy claim — and the count N. `forge/pbo.py` implements steps 4–5 as
   written.
6. **Cost (`ARITHMETIC`):** naive = 12,870 × N × T/2 ≈ 2.9e10 multiply-adds at N = 900, T = 2,493; with
   per-block sums and sums of squares (Sharpe on a union of blocks is a function of the 16 block statistics)
   = 12,870 × 16 × N ≈ 1.9e8 at N = 900 — sub-second in numpy, tens of seconds in pure Python.
   `forge/pbo.py` already uses the block-statistics trick.
7. **Minimum N.** Paper guidance: "N >> 10". For a decision at 0.5 the rank must at least distinguish "above
   median": N ≥ 20 gives ω̄ on a 20-level grid. `forge/pbo.py::MIN_TRIALS = 8` is below the paper's guidance
   — raise to 20 (our stated pool minimum); pools with N < 20 return "insufficient", never a pass. With N <
   10 the logit takes fewer than 10 values and the paper calls f(λ) "too discontinuous" — PBO is meaningless
   there.
8. **Caveats (from the fetched text).** (a) Stationarity: "this procedure only takes into account structural
   breaks as long as they are present in the dataset of length T" — a regime absent from 2014–2023 (or
   2019–2023) is invisible to PBO. (b) Serial dependence: "if the performance measure as a time series has a
   strong autocorrelation, then such a division may obscure the characterization especially when S is large"
   — S = 16 on daily data keeps quarter-length blocks, which the paper considers safe for 4+ years. (c)
   Correlated trials: "it is entirely possible that all the N strategies have high but similar Sharpe
   ratios. Since none of the strategies is clearly better than the rest, PBO will be high" — a pool of
   near-duplicate variants of one formula can show PBO ≈ 0.5 while every member is skilful; conversely
   near-duplicates of the IS-best inflate N without adding independent comparisons (EX-ANTE from the
   definition; magnitude in our pools UNMEASURED). (d) PBO evaluates the *selection process* on the pool,
   not the correctness of the backtest; platform simulation quality is outside its scope. (e) The paper's T
   should be "double" the selection sample; ours is the same sample the gates were graded on — the two
   halves are each half the platform's graded window.

## PART 2 — WorldQuant BRAIN platform facts

### 2.1 What was fetchable today — nothing from platform documentation
- `support.worldquantbrain.com/hc/en-us` and the Submission-Checks article → **403** (WebFetch and curl with
  a browser UA both receive a Cloudflare "Just a moment…" challenge); the Zendesk help-center API
  `/api/v2/help_center/en-us/articles/search.json` → **401**.
- `platform.worldquantbrain.com/learn/documentation/...` → curl 200 but the body is the SPA shell ("index");
  the content is login-gated. WebFetch returned nothing.
- `worldquantbrain.com/consultant` → 200; contains no threshold, quota or pyramid statement (only
  "Accumulate points by submitting your Alphas that meet our submission criteria" and "10,000 points on
  BRAIN and reach gold").
- `api.worldquantbrain.com` without a session: `/operators` 401, `/users/self/activities/pyramid-alphas`
  401, `/data-sets` 429, `/documentation` and `/pyramid-multipliers` 404.
**Consequently every fact below is UNVERIFIED by today's fetch.** Provenance labels: `[TRANSCRIPTION]` =
SUBMISSION_GATES.md, transcribed from Khoa's screenshots of the login-gated page
`learn/documentation/consultant-information/consultant-submission-tests`; `[API-OBSERVED]` = responses of
the authenticated API recorded in this repo's tools/journal; `[OPERATOR]` = Khoa's statement;
`[THIRD-PARTY]` = search snippets from GitHub/Zhihu notes — listed, not used.

### 2.2 Submission checks and thresholds
| Check | Threshold | Provenance |
|---|---|---|
| IS-Ladder (the real Sharpe gate; `LOW_SHARPE`/`LOW_2Y_SHARPE` are its API names) | D1: FAIL_THRESHOLD 1.59; PASS 2.38 for the last 2–5 yrs, 2.22 (6), 2.06 (7), 1.90 (8), 1.74 (9), 1.59 (10). D0: FAIL 2.69; PASS 3.96 (2–5), 3.64, 3.33, 3.17, 2.85, 2.69. "If turnover < 30%, the PASS_THRESHOLDS are multiplied by 0.85 (FAIL_THRESHOLD is NOT)." `Sharpe = sqrt(250) * IR` | `[TRANSCRIPTION]` |
| LOW_FITNESS | 1.0 (USA d1 observed); CHN D1 1.0 / D0 1.5 | `[TRANSCRIPTION]` + `[API-OBSERVED]` |
| LOW_TURNOVER / HIGH_TURNOVER | 0.01 / 0.70 (USA d1); superalphas 2 %–40 % | `[API-OBSERVED]` / `[TRANSCRIPTION]` |
| CONCENTRATED_WEIGHT | max weight > 10 % fails; "too few instruments" fails; 30 % in one stock is the given example | `[TRANSCRIPTION]` |
| LOW_SUB_UNIVERSE_SHARPE | TOPxxx: `subuniverse_sharpe >= 0.75 * sqrt(subuniverse_size / alpha_universe_size) * alpha_sharpe`; non-TOP: ratio 0.295 (ASI MINVOL1M), 0.41 (USA ILLIQUID_MINVOL1M), 0.355 (EUR ILLIQUID_MINVOL1M) | `[TRANSCRIPTION]` |
| LOW_ROBUST_UNIVERSE_SHARPE | ASI: ≥ 90 % of returns and Sharpe retained on the adjusted universe; CHN: ≥ 40 % | `[TRANSCRIPTION]` |
| SELF_CORRELATION | 0.7 against the user's previous submissions | `[TRANSCRIPTION]`; "submittable anyway if Sharpe is ≥ 10 % higher" is `[THIRD-PARTY]` only |
| PROD_CORRELATION | limit 0.7; rejection text `PROD_CORRELATION value=0.7031 limit=0.7` | `[API-OBSERVED]` |
| MATCHES_PYRAMID | PASS/FAIL check name; rule text not transcribed | `[API-OBSERVED]` name only |
| CHN | D1 Sharpe ≥ 2.08, Returns ≥ 8 %, Fitness ≥ 1.0; D0 3.5 / 12 % / 1.5 | `[TRANSCRIPTION]` |
| GLB regional lines | **UNKNOWN** — nothing local, nothing fetched | — |
Result buckets `[API-OBSERVED]`: PASS / WARNING (not blocking) / ERROR / PENDING (correlation, quota, theme
evaluated at submit). Q23 relies on this.

### 2.3 Sub-universe and robust universe — what they mean
`[TRANSCRIPTION]`: sub-universe = the alpha re-run on a smaller, more liquid subset of its universe (a
TOP1000 alpha is retested on its sub-universe); the bar scales with √(size ratio) × the alpha's own Sharpe,
so a higher IS Sharpe *raises* its own sub-universe bar — the test is about consistency across liquidity
tiers, not an absolute level. Robust universe = "the adjusted (more-scalable) universe", with retention
thresholds by region (§2.2). The platform's exact construction of either universe is **UNVERIFIED** (not on
any fetched page).

### 2.4 Pyramid program
- Cell = category × region × delay; the counter is `GET /users/self/activities/pyramid-alphas` (151 cells,
  field `alphaCount`) `[API-OBSERVED]`; one alpha can belong to several cells (`alpha["pyramids"]`, e.g.
  `{"name": "USA/D1/PV", "multiplier": 1.1}`) `[API-OBSERVED]`.
- Multipliers: `state/pyramid_multipliers.json`, "Khoa screenshot 2026-07-16 (UI pyramid table)", e.g. CHN
  Institutions d1 2.0, CHN/JPN Analyst d0 1.9, Fundamental d0 1.9; the file itself warns the table drifts
  against per-field `pyramidMultiplier` in the catalog. `[OPERATOR screenshot]`.
- "A cell unlocks/completes at 3 alphas" and "a 4th alpha is worth nothing": Khoa, 2026-07-31 `[OPERATOR]` —
  encoded as `UNLOCK_AT = 3` in `tools/cell_targets.py`. **UNVERIFIED as a platform rule**; the counter also
  intermittently under-reports (7 reads in 150 s gave two different counts, all HTTP 200) `[API-OBSERVED]`.

### 2.5 Quotas `[API-OBSERVED]`
- Submissions: `REGULAR_SUBMISSION` limit 4, read from `/alphas/<id>/check`; 4 landed on each of
  07-29…08-01. Simulations: 429 `DAILY_SIMULATION_LIMIT_EXCEEDED` on `POST /simulations`; 5,048 alphas
  created in the platform day 2026-08-01. Both counters are US-Eastern calendar days, reset 00:00 ET (04:00
  UTC = 11:00 local), established by an exact 5,048-row match on `dateCreated >= 04:00Z`. The 429 body does
  not reliably distinguish the daily from the concurrent limit. A 403 on submit spends the alpha
  permanently. The ~80-concurrent ceiling and a 25/day auth-link cap are recorded elsewhere as unverified.

### 2.6 Fitness
Formula in local docs and third-party notes: `fitness = sharpe * sqrt(|returns| / max(turnover, 0.125))`.
**Re-derived a second way (POST-HOC, 9/9):** applied to platform-returned (sharpe, turnover, returns)
triples in OPERATORS.md it reproduces the platform's reported fitness to 2 decimals in all 9 cases,
including 4 with turnover < 0.125 where only the floored version matches (e.g. `QPVpQrzQ`: sharpe 0.40,
turnover 0.0072, returns 0.0534 → 0.261 with the floor, 1.089 without; platform says 0.26). The formula is
therefore verified against platform output, though not against a documentation page.

### 2.7 Prod-correlation `[API-OBSERVED]`
`GET /alphas/{id}/correlations/prod` returns a histogram (schema `[min, max, alphas]`, 0.1-wide buckets)
with the true extreme at top level `j['max']`; that number is the gated value (rejection `value=0.7031
limit=0.7` equals `j['max']`). It is recomputed at submit time against a moving book: measured 0.7077 and
0.7078 went ACTIVE, 0.7031 and 0.7320 failed. Against *which* production book and over *what* window:
**UNKNOWN** — no fetched page; "PnL-based, 2-year window" appears only in `[THIRD-PARTY]` notes for
self-correlation. `/correlations/self` returns the user's own alphas with a `correlation` column; max is the
self value.

### 2.8 Agreement with local references
- SUBMISSION_GATES.md: the platform page could not be fetched, so agreement cannot be checked today; its own
  header states it was transcribed from screenshots of the login-gated page. Its "Cluster Test ≥ 1.58 is
  tagging only" and "IS-Ladder 0.85× under 30 % turnover" have no independent local confirmation.
- OPERATORS.md: contains no submission-check thresholds; its simulated examples supplied the 9 fitness
  triples above and the check-name list (`LOW_SHARPE, LOW_TURNOVER, HIGH_TURNOVER, CONCENTRATED_WEIGHT,
  LOW_SUB_UNIVERSE_SHARPE, HT_*, LOW_2Y_SHARPE, MATCHES_CLASSIFICATION, MATCHES_PYRAMID`) — consistent with
  §2.2 names.
- forge/pbo.py docstring cites "J. Computational Finance 2017" — that venue was not verifiable today (the
  fetched PDF is the Feb-2015 revision); the algorithm text there matches the fetched Algorithm 2.3.

## 3. The three platform facts that matter most for 4 submissions/day
1. **Both quotas are per US-Eastern day and both are hard:** 4 `REGULAR_SUBMISSION` and ~5,000 sims, reset
   00:00 ET; a 403 consumes the alpha. Four ACTIVE per day means four *distinct* candidates ready before the
   ET reset, each pre-checked, with no POST into an exhausted quota. `[API-OBSERVED]`
2. **The correlation lines are moving targets:** PROD_CORRELATION is `j['max']` recomputed against the book
   at submit time (0.7031 failed, 0.7078 passed), and SELF_CORRELATION 0.7 tightens with every own
   submission — the four daily submissions must be measured against each other before the first is posted
   (PnL-based self-corr is predictable locally; see memory `pnl-distance-predicts-self-corr`).
   `[API-OBSERVED]`/`[TRANSCRIPTION]`
3. **The Sharpe gate is the IS-Ladder, and turnover < 30 % buys a 0.85× discount on its PASS thresholds**
   (2.38 → 2.02 on D1) while fitness stops rewarding turnover below 0.125 — the pass region is shaped by
   turnover as much as by Sharpe. `[TRANSCRIPTION]`, fitness floor verified 9/9 against platform output.

