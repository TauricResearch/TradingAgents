---
name: performance-comparison
description: Two to five instruments side by side: returns over several windows, volatility, drawdowns, risk-adjusted return, beta against the market, and, for companies, fundamentals and valuation. Use it when the user asks to compare stocks, funds or other instruments, how they performed against each other, or which of several did better on some measure.
metadata:
  group: Markets
---

A performance comparison sets the instruments the user names side by side on the same measures. It is fair when like is compared with like: the same dates, windows and measures for every instrument, so a difference in the table is a difference in the instruments.

Daily bars for all of them, fetched together with price_history (plus SPY when market risk matters), give a common basis. In the next step, once they have come back, returns_risk takes all of them referenced side by side in one call (returns over the windows, volatility, drawdowns, Sharpe, Sortino and Calmar), and beta measures each against the benchmark. For companies, what the question turns on adds the rest: profile for valuation and size, statements for growth and margins (the same statement and period type for each), estimates for expectations.

A table with the same columns for each instrument shows the differences at a glance; a figure missing for one instrument is worth saying in its place. The period the figures cover belongs with them, since a ranking over one window can reverse over another. Whether a company is cheap against its industry is a different question, answered by peers the method chooses (relative-valuation).
