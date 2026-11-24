---
name: dcf-valuation
description: An intrinsic value for a company from a discounted cash flow, with every assumption stated and a sensitivity grid. Use it when the user asks what a company is worth, whether it is over- or undervalued on fundamentals, or for a DCF.
metadata:
  group: Valuation
---

A DCF turns stated assumptions into a value, so the assumptions are the substance: each one with its value and where it came from or why it was chosen. A good one lets the reader change any assumption in their head and see what follows.

The inputs come from profile (market cap, debt, cash, shares), the annual cash flow statement (for trailing twelve months, the last four quarters summed with calc and given as base_fcf), a year of daily bars for the company and SPY, and the 10-year Treasury yield from macro_series. Beta against SPY comes from the two price histories once they have come back. dcf then takes the profile and the cash flow statement referenced whole, with the discount inputs: the 10-year yield as the risk-free rate, the beta, an equity risk premium (4 to 6% is the usual range), a pre-tax cost of debt (interest paid over debt, or the risk-free rate plus a spread) and the tax rate. Growth stages follow the company's recent growth (statements, estimates).

Terminal growth above long-run nominal growth (2 to 3%) would have the company outgrow the economy forever, which is why it stays at or below it. The sensitivity grid shows which assumption moves the value most, and the price today implies what would have to be true; both tell the reader more than a single number, which is why a DCF reads as a range under its assumptions rather than a price target. A company with negative free cash flow needs explicit flows year by year, justified or flagged.
