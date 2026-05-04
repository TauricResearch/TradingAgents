# How A Ticker Report Is Generated

This document explains the report workflow from the perspective of a financial analyst. It avoids implementation detail and focuses on what each stage contributes to the investment decision.

## 1. Choose The Ticker And Analysis Date

The report starts with a specific security and a specific analysis date.

The ticker tells the system what company, ETF, or listed instrument to analyze. The analysis date anchors the report to a point in time.

Why this matters: markets move quickly. A recommendation without a date is hard to evaluate because prices, news, earnings expectations, and sentiment may have changed.

## 2. Select The Analyst Coverage Areas

The user chooses which analyst perspectives to include:

- Market analysis: choose this when timing, trend, momentum, volatility, support/resistance, or recent price behavior matters. This is especially useful for short-term trades, entry/exit discipline, and checking whether the market is confirming or rejecting the investment thesis.
- Social sentiment analysis: choose this when positioning, crowd behavior, retail attention, investor mood, or narrative risk may affect the ticker. This is useful for stocks with heavy public discussion, meme risk, sharp sentiment swings, or event-driven volatility.
- News analysis: choose this when recent catalysts may change the outlook. This is useful around earnings, guidance updates, product news, management changes, regulation, macro shocks, sector moves, insider transactions, or any situation where the latest information may matter more than historical data.
- Fundamentals analysis: choose this when the business itself needs to be evaluated. This is useful for medium- and long-term views, valuation work, quality assessment, earnings durability, margin trends, balance sheet risk, cash flow strength, and comparing price action against underlying performance.

Why this matters: different investment questions require different evidence. A short-term trade may lean more heavily on market data and news flow. A longer-term view usually needs fundamentals and business quality.

## 3. Select The Research Depth

The user chooses how deep the research process should be.

A shallow run is faster and cheaper. A deeper run gives the research and risk teams more room to debate, challenge assumptions, and refine the recommendation.

Why this matters: not every idea deserves the same amount of work. A quick screen and a high-conviction portfolio decision should not use the same research budget.

## 4. Generate The Market Report

The market analyst reviews price action and technical indicators.

This can include trend, momentum, moving averages, volatility, and other market-based signals.

Why this matters: even a strong company can be a poor entry if price action is weak, crowded, extended, or breaking down. The market report helps separate investment thesis from timing.

## 5. Generate The Sentiment Report

The sentiment analyst reviews public tone around the ticker.

This may include investor discussion, media tone, social attention, and shifts in bullish or bearish commentary.

Why this matters: sentiment helps explain positioning and near-term risk. A stock can move because expectations change before fundamentals show up in reported numbers.

## 6. Generate The News Report

The news analyst reviews company-specific and broader market news.

This can include earnings events, management commentary, regulation, sector developments, macro news, insider transactions, and other current catalysts.

Why this matters: news provides context for recent price movement and highlights catalysts that may change the risk/reward profile.

## 7. Generate The Fundamentals Report

The fundamentals analyst reviews company financials and business quality.

This can include revenue, margins, cash flow, balance sheet strength, earnings quality, growth, profitability, and valuation context.

Why this matters: fundamentals help determine whether a price move is supported by business performance. This is especially important for medium- and long-term investment decisions.

## 8. Combine The Analyst Reports

After the selected analyst reports are generated, the system has a multi-angle evidence base.

The reports are not treated as final answers. They become inputs for the research debate.

Why this matters: individual reports can be incomplete or biased toward their data source. Combining them creates a more balanced investment picture.

## 9. Run The Bull Case

The bull researcher argues why the ticker may be attractive.

This side emphasizes upside drivers, positive catalysts, favorable data, improving trends, and reasons the market may be underestimating the opportunity.

Why this matters: a disciplined bull case makes the upside explicit. It helps the analyst understand what must go right for the trade or investment to work.

## 10. Run The Bear Case

The bear researcher argues why the ticker may be unattractive or risky.

This side emphasizes downside risks, valuation concerns, weak data, negative catalysts, competitive threats, balance sheet concerns, and reasons the market may be too optimistic.

Why this matters: the bear case prevents the report from becoming a confirmation exercise. It forces the investment idea to survive a direct challenge.

## 11. Form The Research Manager View

The research manager reviews the bull and bear arguments and produces an investment plan.

This is the first synthesis step. It weighs the evidence and turns the debate into a directional view.

Why this matters: analysts need judgment, not just information. The research manager stage explains which side of the debate is more persuasive and why.

## 12. Convert The View Into A Trading Plan

The trader converts the research view into an actionable trading proposal.

This may include the intended action, rationale, entry considerations, risk controls, monitoring points, and conditions that would change the view.

Why this matters: a good thesis still needs execution discipline. The trading plan connects research to a practical decision.

## 13. Review The Plan Through Risk Lenses

The risk team reviews the proposed trade from multiple perspectives:

- Aggressive: focuses on capturing upside
- Conservative: focuses on protecting capital
- Neutral: balances opportunity and downside

Why this matters: risk is not one-dimensional. A position can look attractive to a growth-oriented investor and unsuitable to a capital-preservation mandate.

## 14. Produce The Portfolio Manager Decision

The portfolio manager reviews the full workflow and produces the final decision.

This decision reflects the analyst reports, bull and bear debate, trader proposal, and risk review.

Why this matters: the final recommendation should not come from one model response or one data source. It should represent a structured investment process.

## 15. Save The Report

When saving is enabled, the system writes the report to organized files.

The saved output includes:

- Analyst reports
- Research debate
- Trading plan
- Risk discussion
- Portfolio manager decision
- Complete report in Markdown
- Complete report in HTML

Why this matters: saved reports create an audit trail. They make it easier to review the recommendation later, compare it with actual performance, and understand what information was available at the time.

## 16. Use The Report As Decision Support

The report is intended to support analyst judgment, not replace it.

The analyst should review:

- Whether the data sources are relevant and current
- Whether the bull and bear cases address the real drivers
- Whether the trading plan matches the mandate
- Whether the risk controls are specific enough
- Whether any important catalyst or constraint is missing

Why this matters: the system structures the research process, but the analyst remains responsible for validating assumptions, checking data quality, and deciding whether the recommendation fits the portfolio.

## Practical Reading Order

For a fast review, read the report in this order:

1. Portfolio manager decision
2. Trading plan
3. Research manager view
4. Bear case
5. Bull case
6. Analyst reports
7. Risk discussion

Why this order helps: start with the conclusion, then inspect the reasoning. If the conclusion is not supported by the evidence, the report should be challenged before use.
