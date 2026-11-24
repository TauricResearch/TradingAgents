---
name: risk-assessment
description: The risks of holding one stock or other instrument: price risk (volatility, drawdowns, VaR, risk-adjusted return, beta against the market), balance-sheet health, and the events that could move it, with what would change the view. Use it when the user asks how risky a holding is, about its downside, or what could make it lose.
metadata:
  group: Risk
---

A risk assessment weighs what could go wrong with holding an instrument, and what would show it early. It is good when it fits the instrument and separates the kinds of risk: how the price has behaved, how sound the balance sheet is, and which events lie ahead. An ETF, a future or a crypto pair has no balance sheet, so its assessment rests on price and events.

A year of daily bars for the instrument and its benchmark (SPY for a US stock), fetched together with price_history, feeds returns_risk and beta in the next step: volatility (the last 20 sessions against the year), the deepest drawdown with its dates and whether it recovered, one-day VaR and expected shortfall, Sortino and Calmar, and beta with its standard error. Sortino counts only downside volatility, which suits an instrument whose swings are lopsided; Calmar sets the annualized return against the deepest drawdown, the loss a holder actually sat through. A Treasury bill yield from macro_series gives the risk-free rate, in percent a year. For a company, statements show debt against cash, interest cover and free cash flow, and how they changed; news and estimates show event risk: the next earnings date, guidance, litigation, regulation.

Historical measures describe the window they come from, which is how they read best, rather than as forecasts. A holding inside a portfolio also carries risk through what it moves with, which a portfolio review measures (portfolio-review).
