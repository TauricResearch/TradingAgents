"""Live check of the Portfolio Manager claim check (fit 4) against real Jev.

Run from the repo root, with the jev extra installed and TYPESAFE_API_KEY set:

    python scripts/jev_claim_check_live.py

It makes one Jev request per claim (10) and one per checkable claim and routed
section (the four reports split into 5 sections). It prints each claim's
judgments, the block appended to the decision, and the signal before and after.
Record the results under "Fit 4 as built" in docs/jev-use-cases.md.

Hand-written analyst reports and a Portfolio Manager decision with three planted
failures:
  1. a contradicted fact  - "gross margin expanded to 76%" (reports: fell to 71.2%)
  2. an invented fact     - a Microsoft supply agreement no report mentions
  3. an invented figure   - free cash flow of $19.2 billion (reports: $13.5 billion)
Expected: (1) contradicted, (2) not found, (3) figure listed, and the decision
sent to REVIEW. The supported claims, the debate remarks and the plan should
come out supported or not checkable.
"""

from __future__ import annotations

import time
from collections import Counter

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision
from tradingagents.agents.utils import claim_check as cc
from tradingagents.agents.utils.jev import jev_client
from tradingagents.agents.utils.rating import extract_rating
from tradingagents.graph.signal_processing import SignalProcessor

MARKET = """# NVDA Technical Analysis (week to 2026-09-22)

## Price action
NVDA closed the week at $118.40, up 3.1% on the week, recovering from a low of $109.85 on
Monday. Volume was 14% above its 20-day average on the two up days, which suggests
accumulation rather than short covering. The stock is back above its 50-day SMA ($114.20)
and its 200-day SMA ($106.75); the 50-day is still above the 200-day, so the long-term
uptrend that began in April is intact.

## Momentum
RSI(14) stands at 61.4, rising but not overbought. MACD crossed above its signal line on
Wednesday and the histogram turned positive for the first time in three weeks. The
Bollinger Bands are narrowing (bandwidth 8.2%, the lowest since June), which often precedes
a larger move in either direction.

## Volatility and levels
ATR(14) is $4.10, about 3.5% of price. Support sits at $110 (last week's low and the lower
band) and then at the 200-day SMA near $106.75. Resistance is at $122.50, the August high;
a close above it would open the way to the all-time high of $135.60.

| Indicator | Value | Read |
|---|---|---|
| Close | $118.40 | above 50- and 200-day SMA |
| RSI(14) | 61.4 | rising, not overbought |
| MACD | bullish crossover | first in 3 weeks |
| ATR(14) | $4.10 | 3.5% of price |
| Support / resistance | $110 / $122.50 | |
"""

FUNDAMENTALS = """# NVIDIA Corporation: Fundamentals

## Latest quarter (Q2 FY2027, reported 2026-08-27)
Revenue was $46.7 billion, up 56% year over year and 6% sequentially. Data-center revenue
was $41.1 billion, up 56% year over year, and now makes up 88% of the total. Gaming revenue
was $4.3 billion. The company guided Q3 revenue to $54.0 billion, plus or minus 2%.

## Margins
GAAP gross margin fell to 71.2% from 75.1% a year earlier, as the ramp of the new Blackwell
Ultra systems carried higher initial costs and an inventory charge of $1.1 billion.
Management expects gross margin to recover into the mid-70s by the end of the fiscal year.
Operating margin was 60.8%, down from 62.1%.

## Cash flow and balance sheet
Operating cash flow was $15.4 billion and free cash flow $13.5 billion in the quarter. The
company holds $56.8 billion in cash and marketable securities against $8.5 billion of debt.
It returned $10.0 billion to shareholders through buybacks and dividends, and the board
added $60 billion to the repurchase authorization.

## Valuation
At $118.40 the stock trades at 38.2x trailing earnings and 29.5x forward earnings, against
a five-year average forward P/E of 36x. EV/sales is 17.3x.

| Metric | Q2 FY2027 | Q2 FY2026 |
|---|---|---|
| Revenue ($B) | 46.7 | 30.0 |
| Data center ($B) | 41.1 | 26.3 |
| Gross margin | 71.2% | 75.1% |
| Free cash flow ($B) | 13.5 | 13.5 |
"""

NEWS = """# News and macro (week to 2026-09-22)

## Company news
Nvidia and Oracle announced an expanded partnership under which Oracle Cloud will deploy
additional Blackwell Ultra clusters in 2027. Reuters reported that Nvidia is designing a
lower-power data-center chip for the Chinese market to comply with current US export rules;
the company declined to comment. Two sell-side firms raised their price targets after the
quarter; none changed their rating.

## Industry
Hyperscaler capital expenditure guidance for 2026 was raised again in the latest round of
earnings, with the four largest cloud providers now expected to spend a combined $420 billion.
AMD said its MI400 accelerator remains on schedule for 2027.

## Macro
The Federal Reserve cut its policy rate by 25 basis points to 3.75-4.00% on 2026-09-17 and
signalled one more cut this year. US CPI rose 2.7% year over year in August. Prediction
markets price a 68% chance of a further cut in December. The 10-year Treasury yield ended the
week at 3.92%.
"""

SENTIMENT = """**Overall Sentiment:** **Mildly Bullish** (score 6.4/10, confidence medium)

**Basis:** 24 of 41 news and social items kept (dropped: 15 about something else; 2 repeats of
an earlier item); the header is computed from per-item stance judgments (TypeSafe Jev).

News coverage was constructive after the Oracle partnership and the price-target increases.
StockTwits was split, with bulls pointing to the MACD crossover and bears to the margin
decline. Reddit posts focused on the China chip report and were mostly neutral.
"""

THESIS = """The bull case carried the debate: the aggressive analyst's evidence on demand was stronger than the conservative analyst's valuation worries.
- Data-center revenue grew 56% year over year to $41.1 billion and now makes up 88% of sales.
- Gross margin expanded to 76% on pricing power, showing the Blackwell ramp is already paying off.
- Free cash flow reached $19.2 billion in the quarter, funding the enlarged buyback.
- Microsoft signed a multi-year supply agreement for Blackwell Ultra systems last week.
- The stock is back above its 50-day and 200-day moving averages, and MACD has turned positive.
- The Fed cut rates by 25 basis points, which supports long-duration growth stocks.
- At 29.5x forward earnings the stock trades below its five-year average multiple.
- Last time we sold too early on a margin scare; the lesson is not to overreact to one quarter.
- We will add on dips toward $110 and would reconsider below the 200-day average."""

DECISION = render_pm_decision(PortfolioDecision(
    rating=PortfolioRating.BUY,
    executive_summary="Buy: build a 4% position in two tranches, the first now and the second on a dip toward $110.",
    investment_thesis=THESIS,
    price_target=140.0,
    time_horizon="6-9 months",
))

REPORTS = {"market": MARKET, "sentiment": SENTIMENT, "news": NEWS, "fundamentals": FUNDAMENTALS}
INSTRUMENT = {"ticker": "NVDA", "name": "NVIDIA Corporation", "classification": "Technology / Semiconductors"}


class Counting:
    """Wraps the client to count requests by question set."""

    def __init__(self, client):
        self.client = client
        self.counts = Counter()

    def system_one(self, state, questions):
        self.counts["relation" if "relation" in questions else "claim"] += 1
        return self.client.system_one(state=state, questions=questions)


def main():
    client = jev_client()
    if client is None:
        raise SystemExit("Jev is off: set TYPESAFE_API_KEY and install the jev extra.")
    for name, text in REPORTS.items():
        sections = cc.split_sections(name, text)
        print(f"{name}: {len(text)} chars, {len(sections)} sections "
              f"{[(s.heading, len(s.text)) for s in sections]}")

    with client:
        counting = Counting(client)
        start = time.monotonic()
        check = cc.run_check(counting, DECISION, {k: v.strip() for k, v in REPORTS.items()}, INSTRUMENT)
        elapsed = time.monotonic() - start

    print(f"\nmodel: {client._config.default_model}")
    print(f"requests: {dict(counting.counts)} in {elapsed:.1f} s\n")
    for r in check.results:
        top = sorted(r.sources.items(), key=lambda kv: -kv[1])
        print(f"[{r.verdict:13}] checkable {r.checkable:.2f}  p {r.probability:.2f}  "
              f"{r.section.label if r.section else '-'}")
        print(f"    {r.claim}")
        print(f"    source: {', '.join(f'{k} {v:.2f}' for k, v in top)}"
              + (f"   figures in no report: {list(r.figures)}" if r.figures else ""))

    block = cc.render_claim_check(check, extract_rating(DECISION))
    full = f"{DECISION}\n\n{block}"
    print("\n" + block)
    print(f"\nrating before: {extract_rating(DECISION)}  signal after: {SignalProcessor().process_signal(full)}")


if __name__ == "__main__":
    main()
