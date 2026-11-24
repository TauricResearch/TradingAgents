---
name: sector-review
description: One sector over a window: its performance against the market, where it stands in the sector rotation, its leading and lagging companies on fundamentals, and the spread of valuations within it. Use it when the user asks how a sector is doing, whether it is leading or lagging the market, or which companies lead it.
metadata:
  group: Markets
---

A sector review looks at one sector over a window the question sets: how it has done against the market, where it stands among the other sectors, which companies lead it on results, and how the market values them. It is good when price performance, fundamentals and valuation are kept apart and then read together, since a sector can rally on rising multiples while its earnings stall.

The sector's ETF (XLK for information technology, XLF for financials; markets sectors lists all eleven) and SPY, fetched together with price_history, give the performance over the window: returns_risk sets their returns, volatility and drawdowns side by side, and beta measures the sector against the market. indicators on the ETF and on SPY, over a year of their bars, show whether each is above or below its 200-day average and how RSI has moved, as context for rotation. markets sectors and sector_rotation give where the sector ranks in the latest session, with the leading and lagging sectors and the risk-on or risk-off reading they imply. screen ranks the sector's companies by a statement line for a fiscal year, or by its change from the year before (revenue, operating income), which shows who leads and who lags on results. profile places the leaders by size and sub-industry, and comps, for one of them against a few others of its sub-industry, shows the spread of multiples.

The rankings in markets describe one session, so a trend over the window comes from the price history. A sector ETF weights its holdings by market value, so its largest companies drive much of its return. screen reads filed annual statements for the fiscal year named, which can be well behind the price; the latest year most companies have filed is the fair one, and companies without a value are counted in the result rather than ranked.
