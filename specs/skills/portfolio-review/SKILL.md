---
name: portfolio-review
description: How a set of holdings behaves together: weights and concentration, correlation, combined volatility, drawdown and tail risk, each holding's share of the risk, and beta against a benchmark, with alternative weightings when asked. Use it when the user asks how risky or diversified a portfolio is, what drives its risk, how its holdings work together, or how other weights would compare.
metadata:
  group: Risk
---

A portfolio review looks at holdings as one position, where weights and correlation decide the risk more than any single holding does. It is good when it shows where the risk actually sits: a holding with a modest weight can carry a large share of the variance, and holdings that move together diversify less than their count suggests.

The weights are the user's, by value; when the user gives share counts, each holding's value is its shares times the latest price from quote, worked out through calc. Daily bars for every holding and the benchmark (SPY for US stocks), fetched together with price_history over a common period such as a year, are the evidence. In the next step portfolio_risk takes them referenced whole with the weights: returns over the windows, volatility, the deepest drawdown, one-day VaR and expected shortfall, Sharpe, Sortino and Calmar, the correlation matrix, each holding's share of the variance, the effective number of holdings by weight and by risk, and beta against the benchmark. A Treasury bill yield from macro_series gives the risk-free rate, and returns_risk on the same bars shows each holding alone beside the whole.

To see alternatives, optimize_portfolio gives the weights the history implies for the least volatile mix, equal risk contributions or the highest Sharpe, and portfolio_risk measures any of them on the same bars. Minimum variance and risk parity rest on the covariance alone; maximum Sharpe and the frontier also rest on mean returns, which are noisy and may not repeat, so these weights read as what the window implied, as analysis rather than a recommendation. Every figure describes its window, on the dates all holdings share, at constant weights rebalanced daily, as the result states; a holding with a short history shortens the window for all of them.
