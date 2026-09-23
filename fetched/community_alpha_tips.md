# Cách cải thiện Alpha — tổng hợp CÓ KIỂM CHỨNG từ community WorldQuant BRAIN

> **Nguồn:** các bài post lượt vote cao nhất trên support.worldquantbrain.com (chủ đề cải thiện alpha), lấy qua CDP (đăng nhập session).
>
> **Chống hallucination (3 lớp):** mỗi ý bắt buộc (1) kèm *quote nguyên văn* từ bài; (2) quote được kiểm tra **tồn tại thật trong source bằng thuật toán** (so khớp chuỗi, không phải AI phán); (3) qua **2 vòng verify độc lập** về độ trung thực (ý không được nói quá / bịa số liệu so với quote.)
>
> **Thống kê lọc:** 156 ý trích → **154** quote khớp source (2 quote bịa bị loại tự động) → **84** ý qua cả 2 vòng verify. File này chỉ giữ 84 ý đã kiểm chứng.

> Mỗi ý ghi kèm quote gốc + link bài + số vote để bạn tự truy nguồn.


---


## Tăng Sharpe  (6 ý)

- **Scale positions by each asset's volatility to keep a consistent risk level.**
  > "Scale your positions based on the volatility of each asset to maintain a consistent risk level."
  — [How do you get a higher Sharpe?](https://support.worldquantbrain.com/hc/en-us/community/posts/8123350778391-How-do-you-get-a-higher-Sharpe) · 165 votes

- **Backtest to target a Sharpe ratio above 1.4**
  > "Backtest rigorously to target a Sharpe ratio >1.4"
  — [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes

- **Reduce volatility by identifying the source of noise (market swings, sector exposure, unstable stocks).**
  > "To reduce volatility, identify where the noise is coming from. Market swings, sector exposure, or unstable stocks can all inflate risk."
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes

- **Improve Sharpe via better signals, stronger neutralization, and lower turnover to reduce noise and volatility.**
  > "Sharpe improves by better signals, stronger neutralization, and lower turnover reducing noise and volatility."
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes

- **Improve Sharpe by strengthening signal quality, diversifying independent alphas, and controlling exposure and transaction costs.**
  > "improve Sharpe by strengthening signal quality, diversifying independent alphas, and controlling exposure and transaction costs"
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes

- **For a better Sharpe, the alpha must have low noise and higher returns.**
  > "for a better sharpe,alpha must have low noise,and higher returns"
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes


## Tăng Fitness  (3 ý)

- **Enhance fitness by increasing the Sharpe ratio (or Returns) and reducing Turnover.**
  > "you can enhance fitness by increasing the Sharpe ratio (or Returns) and reducing Turnover"
  — [🖊️ Passing Submission Test: How to improve Fitness](https://support.worldquantbrain.com/hc/en-us/community/posts/30873523677847--Passing-Submission-Test-How-to-improve-Fitness) · 55 votes

- **Improve one factor (Sharpe or Returns) first, then reduce turnover to reach desirable fitness.**
  > "focus on improving one factor first, such as the Sharpe ratio or Returns, and then reducing turnover to achieve a desirable fitness level"
  — [🖊️ Passing Submission Test: How to improve Fitness](https://support.worldquantbrain.com/hc/en-us/community/posts/30873523677847--Passing-Submission-Test-How-to-improve-Fitness) · 55 votes

- **Target a desirable fitness level of ideally above 0.8.**
  > "achieve a desirable fitness level (ideally >0.8)"
  — [🖊️ Passing Submission Test: How to improve Fitness](https://support.worldquantbrain.com/hc/en-us/community/posts/30873523677847--Passing-Submission-Test-How-to-improve-Fitness) · 55 votes


## Kiểm soát Turnover  (11 ý)

- **Increase alpha turnover — higher turnover means more trading and potentially higher returns.**
  > "Increase the turnover of your alphas — higher turnover means more trading and potentially higher returns."
  — [[BRAIN TIPS] 5 ways to potentially increase returns of an alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/8833033953559--BRAIN-TIPS-5-ways-to-potentially-increase-returns-of-an-alpha) · 158 votes

- **Increasing decay reduces turnover and typically increases fitness too.**
  > "increasing decay reduced turnover, and typically increased fitness also"
  — [🖊️ Passing Submission Test: How to improve Fitness](https://support.worldquantbrain.com/hc/en-us/community/posts/30873523677847--Passing-Submission-Test-How-to-improve-Fitness) · 55 votes

- **Analyze turnover distribution to find signals losing SAC to excessive transaction costs**
  > "I start by analyzing turnover distribution—many otherwise solid signals lose SAC due to excessive transaction costs"
  — [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes

- **Examine signal rank stability across horizons to find decay windows that preserve edge while cutting cost**
  > "examining the stability of signal rank across different horizons helps identify decay windows that preserve edge while minimizing cost"
  — [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes

- **Reduce turnover below 25% using low decay (0-5) to lower trading costs**
  > "Reduce turnover (<25%) with low decay (0–5) to lower trading costs"
  — [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes

- **group_neutralize by a broader sector/country while group_rank by a specific sub-industry isolates idiosyncratic signal without blowing up turnover.**
  > "group_neutralize` by a broader sector or country index while `group_rank`ing by a specific sub-industry is a great way to isolate idiosyncratic signal without blowing up your turnover"
  — [[Tip] Group operators are your neutralization scalpel](https://support.worldquantbrain.com/hc/en-us/community/posts/41657167469207--Tip-Group-operators-are-your-neutralization-scalpel) · 51 votes

- **Consider region-specific turnover control, e.g. APAC may need stricter management than USA**
  > "does APAC require stricter turnover management compared to USA universes?"
  — [Improving Turnover Control Without Losing Performance](https://support.worldquantbrain.com/hc/en-us/community/posts/35241496329879-Improving-Turnover-Control-Without-Losing-Performance) · 50 votes

- **Apply ts_decay_linear to smooth positions; longer decay windows reduce turnover since new information has less effect.**
  > "ts_decay_linear(x, d, dense=false) → Linear decay reduces the impact of older signals, smoothing positions. Using shorter decay windows increases turnover because new information has more effect."
  — [Tips on reducing turnover](https://support.worldquantbrain.com/hc/en-us/community/posts/39813699758487-Tips-on-reducing-turnover) · 45 votes

- **Use ts_decay_exp_window with a larger factor for slower response, which lowers turnover.**
  > "ts_decay_exp_window(x, d, factor=f) → Exponential decay; smaller factor = faster response = higher turnover."
  — [Tips on reducing turnover](https://support.worldquantbrain.com/hc/en-us/community/posts/39813699758487-Tips-on-reducing-turnover) · 45 votes

- **Use ts_delta_limit to restrict change in position relative to volume; lowering limit_volume reduces turnover.**
  > "ts_delta_limit(x, y, limit_volume=0.1) → Restricts change in position relative to some volume. Increasing limit_volume allows bigger moves → higher turnover."
  — [Tips on reducing turnover](https://support.worldquantbrain.com/hc/en-us/community/posts/39813699758487-Tips-on-reducing-turnover) · 45 votes

- **Wrap the signal in trade_when to only trade when a condition is met; tightening conditions reduces turnover.**
  > "trade_when(x, y, z) → Only executes trades when a condition is met. Loosening conditions (or removing unnecessary filters) increases turnover."
  — [Tips on reducing turnover](https://support.worldquantbrain.com/hc/en-us/community/posts/39813699758487-Tips-on-reducing-turnover) · 45 votes


## Giảm Production Correlation  (6 ý)

- **Combine components before ranking with scaling, e.g. rank(zscore(x) + zscore(y)), to avoid single-component dominance.**
  > "Prefer: rank(zscore(x) + zscore(y)) Avoid dominance from a single component"
  — [REDUCING PROD CORRELATION](https://support.worldquantbrain.com/hc/en-us/community/posts/39850218694551-REDUCING-PROD-CORRELATION) · 72 votes

- **Mix cross-sectional (relative value) signals with time-series (momentum/mean-reversion) signals for structurally different risk drivers.**
  > "Combine signals that exploit cross-sectional dispersion (relative value) with those that exploit time-series patterns (momentum/mean-reversion). These have structurally different risk drivers."
  — [REDUCING PROD CORRELATION](https://support.worldquantbrain.com/hc/en-us/community/posts/39850218694551-REDUCING-PROD-CORRELATION) · 72 votes

- **Use regime-conditional construction: build alphas that activate in different market states (low-vol vs high-vol, trending vs mean-reverting).**
  > "Build alphas that activate in different market states (e.g., low-vol vs. high-vol, trending vs. mean-reverting). This forces structural differentiation at the source."
  — [REDUCING PROD CORRELATION](https://support.worldquantbrain.com/hc/en-us/community/posts/39850218694551-REDUCING-PROD-CORRELATION) · 72 votes

- **Use correlation heatmaps or Prod_corr constraints to select low-correlated alphas for the portfolio**
  > "using correlation heatmaps or Prod_corr constraints to select a set of low-correlated alphas"
  — [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes

- **Continuously prune underperformers and rotate in fresh orthogonal signals**
  > "Continuously prune underperformers and rotate in fresh, orthogonal signals"
  — [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes

- **Test group_rank(signal, subindustry) followed by a different neutralization group when the original idea has high self-correlation.**
  > "combinations like `group_rank(signal, subindustry)` followed by a different neutralization group easier to test, especially when the original idea has high self-correlation"
  — [[Tip] Group operators are your neutralization scalpel](https://support.worldquantbrain.com/hc/en-us/community/posts/41657167469207--Tip-Group-operators-are-your-neutralization-scalpel) · 51 votes


## Neutralization  (12 ý)

- **Neutralize shared exposures with group_neutralize(alpha, subindustry) to remove common drivers across alphas.**
  > "group_neutralize(alpha, subindustry),removes common drivers across alphas"
  — [REDUCING PROD CORRELATION](https://support.worldquantbrain.com/hc/en-us/community/posts/39850218694551-REDUCING-PROD-CORRELATION) · 72 votes

- **Improve fitness through neutralization such as market and subindustry.**
  > "I improved my fitness through neutralization, such as market and subindustry"
  — [🖊️ Passing Submission Test: How to improve Fitness](https://support.worldquantbrain.com/hc/en-us/community/posts/30873523677847--Passing-Submission-Test-How-to-improve-Fitness) · 55 votes

- **Apply neutralization to remove industry, beta, or value factors and make the alpha cleaner and more balanced.**
  > "Applying Neutralization helps make our alpha cleaner and more balanced by removing factors such as industry, beta, or value."
  — [Using Neutralization](https://support.worldquantbrain.com/hc/en-us/community/posts/35106324044823-Using-Neutralization) · 55 votes

- **Avoid over-neutralizing, since aggressive neutralization can eliminate signals the market genuinely values.**
  > "If we neutralize too aggressively, we might end up eliminating signals that the market genuinely values."
  — [Using Neutralization](https://support.worldquantbrain.com/hc/en-us/community/posts/35106324044823-Using-Neutralization) · 55 votes

- **Use scale() to normalize values for comparability across securities**
  > "scale(): Normalize values for comparability across securities."
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Dividing by the sum of absolute alphas forces total alpha to zero and splits investment equally long/short.**
  > "divided by the sum of the absolute values of the alphas to ensure the total sum of the alpha values is zero and the total investment is equally divided between long and short positions"
  — [[BRAIN TIPS ] How does neutralization work?](https://support.worldquantbrain.com/hc/en-us/community/posts/9121204386071--BRAIN-TIPS-How-does-neutralization-work) · 53 votes

- **Rank with group_rank on liquidity/size buckets to control the size component without a separate market neutralization step.**
  > "group_rank(my_signal, bucket(ts_mean(volume, 20), 5)) — this ranks stocks within similar liquidity tiers, which naturally controls for the size-related component of the signal without needing a separate market neutralization step"
  — [[Tip] Group operators are your neutralization scalpel](https://support.worldquantbrain.com/hc/en-us/community/posts/41657167469207--Tip-Group-operators-are-your-neutralization-scalpel) · 51 votes

- **Use group_neutralize to remove industry/size/style bias so the signal reflects stock-specific effects, not group effects**
  > "removes group-level bias (industry, size, style, etc.) from a series x"
  — [Beginner’s Guide to the group_neutralize Operator](https://support.worldquantbrain.com/hc/en-us/community/posts/34282935746839-Beginner-s-Guide-to-the-group-neutralize-Operator) · 49 votes

- **Use neutralization to control exposures and stabilize performance.**
  > "Techniques like neutralization can help control these exposures and stabilize performance."
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes

- **Neutralize unwanted sector or factor exposures without sacrificing legitimate alpha sources.**
  > "identifying and neutralizing unwanted sector or factor exposures without accidentally sacrificing legitimate alpha sources"
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes

- **Use neutralization settings to reduce exposure to overall market risk or specific groups**
  > "Use neutralization settings to reduce exposure to overall market risk or specific groups."
  — [🖊️ Passing Submission Test: How to improve Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/30873458756375--Passing-Submission-Test-How-to-improve-Sharpe) · 41 votes

- **Use group_operator together with neutralization**
  > "Use group_operator and neutralization."
  — [🖊️ Passing Submission Test: How to improve Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/30873458756375--Passing-Submission-Test-How-to-improve-Sharpe) · 41 votes


## Chống overfitting & Robustness  (21 ý)

- **Keep operators per alpha around 5 or below to force clarity, parsimony, and economic intuition.**
  > "Keeping this number around 5 or below forces you to focus on clarity, parsimony, and economic intuition rather than overcomplicating signals."
  — [A GUIDE ON OPERATORS PER ALPHA;YOU'LL LOVE IT!](https://support.worldquantbrain.com/hc/en-us/community/posts/39984614202647-A-GUIDE-ON-OPERATORS-PER-ALPHA-YOU-LL-LOVE-IT) · 166 votes

- **Use fewer operators to reduce overfitting by limiting unnecessary degrees of freedom.**
  > "Fewer operators reduce overfitting by limiting unnecessary degrees of freedom."
  — [A GUIDE ON OPERATORS PER ALPHA;YOU'LL LOVE IT!](https://support.worldquantbrain.com/hc/en-us/community/posts/39984614202647-A-GUIDE-ON-OPERATORS-PER-ALPHA-YOU-LL-LOVE-IT) · 166 votes

- **Lower operator count often yields more orthogonal and diversified signals.**
  > "Lower operator count often leads to more orthogonal and diversified signals."
  — [A GUIDE ON OPERATORS PER ALPHA;YOU'LL LOVE IT!](https://support.worldquantbrain.com/hc/en-us/community/posts/39984614202647-A-GUIDE-ON-OPERATORS-PER-ALPHA-YOU-LL-LOVE-IT) · 166 votes

- **Start simple for robustness; add complexity for return but watch for overfitting.**
  > "A simple prediction model is often more robust, but the performance may be low, while a more complex model will often generate a higher return, but beware of overfitting"
  — [How do you get a higher Sharpe?](https://support.worldquantbrain.com/hc/en-us/community/posts/8123350778391-How-do-you-get-a-higher-Sharpe) · 165 votes

- **Validate on out-of-sample datasets so the alpha generalizes to unseen data.**
  > "Ensure that your alpha generalizes well to unseen data by validating on out-of-sample datasets."
  — [How do you get a higher Sharpe?](https://support.worldquantbrain.com/hc/en-us/community/posts/8123350778391-How-do-you-get-a-higher-Sharpe) · 165 votes

- **Apply a simple moving-average timing overlay to avoid large drawdowns in momentum portfolios.**
  > "using a simple moving average timing strategy could avoid the large drawdowns in momentum portfolios"
  — [Research Paper 07: Relative Strength Strategies for Investing](https://support.worldquantbrain.com/hc/en-us/community/posts/15602317429655-Research-Paper-07-Relative-Strength-Strategies-for-Investing) · 74 votes

- **Add a trend-following parameter to dynamically hedge the portfolio, cutting both volatility and drawdown.**
  > "The addition of a trend-following parameter to dynamically hedge the portfolio decreases both volatility and drawdown"
  — [Research Paper 07: Relative Strength Strategies for Investing](https://support.worldquantbrain.com/hc/en-us/community/posts/15602317429655-Research-Paper-07-Relative-Strength-Strategies-for-Investing) · 74 votes

- **Start simple: test one core insight first, then gradually layer additional signals**
  > "start simple—test one core insight first, then gradually layer additional signals"
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Start with the core signal before adding extra features to see its standalone strength**
  > "starting with the core signal before adding extra features—this way you can clearly see its standalone strength"
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Incorporate cross-validation across sub-universes to ensure the strategy generalizes beyond sample conditions.**
  > "incorporating cross-validation across sub-universes to ensure the strategy generalizes beyond the sample conditions"
  — [How to Use Academic Research to Build Alpha Strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34176521864983-How-to-Use-Academic-Research-to-Build-Alpha-Strategies-in-WorldQuant-BRAIN) · 50 votes

- **Avoid using too small groups because they are unstable**
  > "Avoid too small groups (unstable)."
  — [Beginner’s Guide to the group_neutralize Operator](https://support.worldquantbrain.com/hc/en-us/community/posts/34282935746839-Beginner-s-Guide-to-the-group-neutralize-Operator) · 49 votes

- **Prefer the second-best config over the best, since it tends to overfit less.**
  > "the second best often has less overfitting tendency"
  — [How can you avoid overfitting?](https://support.worldquantbrain.com/hc/en-us/community/posts/8209806533015-How-can-you-avoid-overfitting) · 46 votes

- **Improve alphas by refining the underlying idea, not by adding or fitting parameters, factors, or reversion elements.**
  > "try to focus on improving them by refining your ideas, not by adding or fitting parameters, factors or reversion elements"
  — [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes

- **Avoid stacking extra parameters, factors, and mean-reversion rules, since they capture noise not persistent edge.**
  > "overfit by adding extra parameters, factors, or mean-reversion rules until backtests look great. Usually, this captures noise, not persistent edge"
  — [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes

- **Prefer fewer knobs with stronger logic.**
  > "Fewer knobs, stronger logic"
  — [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes

- **Seek clearer causal intuition, cleaner data, and robust implementation over cosmetic complexity that flatters simulations.**
  > "Great quant research seeks clearer causal intuition, cleaner data, and robust implementation, not cosmetic complexity that flatters historical simulations"
  — [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes

- **If a strategy needs ten knobs and filters to look good in simulation, it's a historical artifact, not robust; focus on the causal mechanism.**
  > "If a strategy requires ten different "knobs" and filters to look good in a simulation, it’s not a robust strategy, it's just a historical artifact. Focus on the causal mechanism, not the parameter tuning"
  — [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes

- **Build strong alphas from better market intuition and robust hypotheses, not from piling on parameters that only improve backtests.**
  > "Strong alphas come from better market intuition and robust hypotheses, not from piling on parameters that only improve backtests"
  — [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes

- **Prefer simpler models because they tend to be more stable.**
  > "Simpler models tend to be more stable."
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes

- **Experiment with operator combinations and settings, but beware it moves toward overfitting**
  > "Experiment with different operator combinations and settings, but it will bring you closer to overfitting."
  — [🖊️ Passing Submission Test: How to improve Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/30873458756375--Passing-Submission-Test-How-to-improve-Sharpe) · 41 votes

- **Keep the idea simple; avoid combining more than 3 datafields in one alpha**
  > "Keep the idea as simple as possible, it will be difficult for beginners to combine >3 datafields in 1 alpha."
  — [🖊️ Passing Submission Test: How to improve Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/30873458756375--Passing-Submission-Test-How-to-improve-Sharpe) · 41 votes


## Ý tưởng tín hiệu & Operators  (23 ý)

- **When combining two signals, aim for complementarity, not redundancy.**
  > "The goal is complementarity, not redundancy."
  — [A GUIDE ON OPERATORS PER ALPHA;YOU'LL LOVE IT!](https://support.worldquantbrain.com/hc/en-us/community/posts/39984614202647-A-GUIDE-ON-OPERATORS-PER-ALPHA-YOU-LL-LOVE-IT) · 166 votes

- **For vector datafields, include a mandatory reduction step like vec_avg or vec_sum.**
  > "vector datafields, where an additional reduction step is mandatory (e.g., vec_avg, vec_sum)"
  — [A GUIDE ON OPERATORS PER ALPHA;YOU'LL LOVE IT!](https://support.worldquantbrain.com/hc/en-us/community/posts/39984614202647-A-GUIDE-ON-OPERATORS-PER-ALPHA-YOU-LL-LOVE-IT) · 166 votes

- **Prefer longer-persistence signals since they often have higher returns.**
  > "Signals with longer persistence (holding time) often have higher returns."
  — [How do you get a higher Sharpe?](https://support.worldquantbrain.com/hc/en-us/community/posts/8123350778391-How-do-you-get-a-higher-Sharpe) · 165 votes

- **Explore less-competitive markets like smaller-cap stocks or niche regions.**
  > "Explore markets with less competition, such as smaller-cap stocks or niche regions."
  — [How do you get a higher Sharpe?](https://support.worldquantbrain.com/hc/en-us/community/posts/8123350778391-How-do-you-get-a-higher-Sharpe) · 165 votes

- **Add volume data to a momentum signal to refine its prediction.**
  > "Add volume data to refine the prediction of strong momentum."
  — [How do you get a higher Sharpe?](https://support.worldquantbrain.com/hc/en-us/community/posts/8123350778391-How-do-you-get-a-higher-Sharpe) · 165 votes

- **Use lower decay values in the alpha settings.**
  > "Use lower decay values in the alpha settings."
  — [[BRAIN TIPS] 5 ways to potentially increase returns of an alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/8833033953559--BRAIN-TIPS-5-ways-to-potentially-increase-returns-of-an-alpha) · 158 votes

- **Work on more liquid (smaller) universes in the alpha settings.**
  > "Work on more liquid (smaller) universes in the alpha settings."
  — [[BRAIN TIPS] 5 ways to potentially increase returns of an alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/8833033953559--BRAIN-TIPS-5-ways-to-potentially-increase-returns-of-an-alpha) · 158 votes

- **Use fundamental-based alphas, which tend to have more returns than regular operator ones.**
  > "the fundamental based alphas is way more returns than regular operators ones"
  — [[BRAIN TIPS] 5 ways to potentially increase returns of an alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/8833033953559--BRAIN-TIPS-5-ways-to-potentially-increase-returns-of-an-alpha) · 158 votes

- **Incorporate the dividend datafield from Price Volume Data for Equity into the strategy.**
  > "dividends  	  dividend  	  Price Volume Data for Equity"
  — [Research Paper 07: Relative Strength Strategies for Investing](https://support.worldquantbrain.com/hc/en-us/community/posts/15602317429655-Research-Paper-07-Relative-Strength-Strategies-for-Investing) · 74 votes

- **Use delta() to measure changes over time, e.g. 5-day change in options exercised**
  > "delta(): Measure changes over time (e.g., 5-day change in options exercised)."
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Use rank() to rank securities by a chosen metric**
  > "rank(): Rank securities by a chosen metric (e.g., insider buying trend)."
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Use reverse() for mean-reversion strategies**
  > "reverse(): Useful for mean-reversion strategies."
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Refine by adjusting parameters or incorporating additional factors**
  > "Refine by adjusting parameters or incorporating additional factors."
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Build a family of alphas from one research idea by experimenting with different operators or combining datasets**
  > "a single paper can generate multiple Alpha variations if you experiment with different operators or combine with other datasets in BRAIN"
  — [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes

- **Apply smoothing operators like ts_decay_linear or ts_mean to reduce unnecessary rebalancing**
  > "Applying smoothing operators (e.g., ts_decay_linear, ts_mean) or conditional execution rules (like trade_when) can reduce unnecessary rebalancing"
  — [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes

- **Use reverse() to test mean-reversion strategies.**
  > "reverse() → Tests mean reversion strategies"
  — [How to Use Academic Research to Build Alpha Strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34176521864983-How-to-Use-Academic-Research-to-Build-Alpha-Strategies-in-WorldQuant-BRAIN) · 50 votes

- **Choose method: 'mean' subtracts the group mean while 'zscore' rescales within groups**
  > ""mean" subtracts group mean; "zscore" rescales within groups."
  — [Beginner’s Guide to the group_neutralize Operator](https://support.worldquantbrain.com/hc/en-us/community/posts/34282935746839-Beginner-s-Guide-to-the-group-neutralize-Operator) · 49 votes

- **Test transformations in isolation first (e.g., ts_rank on one field) before combining across datasets**
  > "test transformations in isolation first (e.g., just ts_rank on one field) before combining across datasets"
  — [Beginner’s Guide to the group_neutralize Operator](https://support.worldquantbrain.com/hc/en-us/community/posts/34282935746839-Beginner-s-Guide-to-the-group-neutralize-Operator) · 49 votes

- **Instead of choosing between 4- and 6-day decays, blend them (use 5 or average the two).**
  > "you can use 5 or simply take the alpha average of 4 and 6 days"
  — [How can you avoid overfitting?](https://support.worldquantbrain.com/hc/en-us/community/posts/8209806533015-How-can-you-avoid-overfitting) · 46 votes

- **Use standard lookback periods (5,20,60,252) and stop excessively fine-tuning parameters like powers.**
  > "Use normal look back periods like 5,20,60,252 in your alpha and also stop fine tuning parameters like powers etc. excessively"
  — [How can you avoid overfitting?](https://support.worldquantbrain.com/hc/en-us/community/posts/8209806533015-How-can-you-avoid-overfitting) · 46 votes

- **Base alphas on a better idea about how markets work rather than endless model tweaking.**
  > "A strong alpha usually comes from a better idea about how markets work, not from endlessly tweaking a model"
  — [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes

- **Boost returns by improving prediction through combining different data sources (price/volume, fundamentals, analyst data).**
  > "That can come from combining different data sources—price/volume for short-term signals or fundamentals and analyst data for longer horizons"
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes

- **Use ts_operator and vary the lookback to find the best parameter**
  > "Use ts_operator and change lookback to find the best parameter."
  — [🖊️ Passing Submission Test: How to improve Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/30873458756375--Passing-Submission-Test-How-to-improve-Sharpe) · 41 votes


## Submission (chung)  (2 ý)

- **Adjust parameters or test alternative factors to improve results.**
  > "Adjust parameters or test alternative factors to improve results"
  — [How to Use Academic Research to Build Alpha Strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34176521864983-How-to-Use-Academic-Research-to-Build-Alpha-Strategies-in-WorldQuant-BRAIN) · 50 votes

- **Make progress by experimenting, learning from others, and consistently refining your approach.**
  > "Progress comes from experimenting, learning from others, and consistently refining your approach."
  — [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes


---

## Nguồn (bài đã trích)

- [A GUIDE ON OPERATORS PER ALPHA;YOU'LL LOVE IT!](https://support.worldquantbrain.com/hc/en-us/community/posts/39984614202647-A-GUIDE-ON-OPERATORS-PER-ALPHA-YOU-LL-LOVE-IT) · 166 votes
- [How do you get a higher Sharpe?](https://support.worldquantbrain.com/hc/en-us/community/posts/8123350778391-How-do-you-get-a-higher-Sharpe) · 165 votes
- [[BRAIN TIPS] 5 ways to potentially increase returns of an alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/8833033953559--BRAIN-TIPS-5-ways-to-potentially-increase-returns-of-an-alpha) · 158 votes
- [Research Paper 07: Relative Strength Strategies for Investing](https://support.worldquantbrain.com/hc/en-us/community/posts/15602317429655-Research-Paper-07-Relative-Strength-Strategies-for-Investing) · 74 votes
- [REDUCING PROD CORRELATION](https://support.worldquantbrain.com/hc/en-us/community/posts/39850218694551-REDUCING-PROD-CORRELATION) · 72 votes
- [🖊️ Passing Submission Test: How to improve Fitness](https://support.worldquantbrain.com/hc/en-us/community/posts/30873523677847--Passing-Submission-Test-How-to-improve-Fitness) · 55 votes
- [Using Neutralization](https://support.worldquantbrain.com/hc/en-us/community/posts/35106324044823-Using-Neutralization) · 55 votes
- [How to use research papers to generate alpha strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34251253793687-How-to-use-research-papers-to-generate-alpha-strategies-in-WorldQuant-BRAIN) · 54 votes
- [[BRAIN TIPS ] How does neutralization work?](https://support.worldquantbrain.com/hc/en-us/community/posts/9121204386071--BRAIN-TIPS-How-does-neutralization-work) · 53 votes
- [Improving alpha](https://support.worldquantbrain.com/hc/en-us/community/posts/34156828733591-Improving-alpha) · 52 votes
- [[Tip] Group operators are your neutralization scalpel](https://support.worldquantbrain.com/hc/en-us/community/posts/41657167469207--Tip-Group-operators-are-your-neutralization-scalpel) · 51 votes
- [Improving Turnover Control Without Losing Performance](https://support.worldquantbrain.com/hc/en-us/community/posts/35241496329879-Improving-Turnover-Control-Without-Losing-Performance) · 50 votes
- [How to Use Academic Research to Build Alpha Strategies in WorldQuant BRAIN](https://support.worldquantbrain.com/hc/en-us/community/posts/34176521864983-How-to-Use-Academic-Research-to-Build-Alpha-Strategies-in-WorldQuant-BRAIN) · 50 votes
- [Beginner’s Guide to the group_neutralize Operator](https://support.worldquantbrain.com/hc/en-us/community/posts/34282935746839-Beginner-s-Guide-to-the-group-neutralize-Operator) · 49 votes
- [How can you avoid overfitting?](https://support.worldquantbrain.com/hc/en-us/community/posts/8209806533015-How-can-you-avoid-overfitting) · 46 votes
- [Tips on reducing turnover](https://support.worldquantbrain.com/hc/en-us/community/posts/39813699758487-Tips-on-reducing-turnover) · 45 votes
- [Alpha Ideas Matter the Most](https://support.worldquantbrain.com/hc/en-us/community/posts/40008701513367-Alpha-Ideas-Matter-the-Most) · 42 votes
- [Tips to improving Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/39951558129175-Tips-to-improving-Sharpe) · 41 votes
- [🖊️ Passing Submission Test: How to improve Sharpe](https://support.worldquantbrain.com/hc/en-us/community/posts/30873458756375--Passing-Submission-Test-How-to-improve-Sharpe) · 41 votes