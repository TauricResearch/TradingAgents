"""Live check of the fit 5 report-feature questions against real Jev.

Run from the repo root, with the jev extra installed and TYPESAFE_API_KEY set:

    python scripts/jev_report_features_live.py [runs]

This does not test whether the features predict outcomes; that needs a settled
backtest and `tradingagents learn`. It tests that each question reads what it
asks about: three hand-written runs for one ticker, the same documents written
bullish, mixed and bearish, each with a known answer per question. It makes one
request per run and document (3 x 7), repeated `runs` times (default 3), with no
cache, and prints each column per run. Record the results under "Fit 5 as
built" in docs/jev-use-cases.md.

Expected, per question: the bullish (A) and bearish (B) runs sit on the sides
named below, and the mixed run (C) in between for the Scores, except
sentiment_extremity: it has no direction, so the calm, evenly split C is lowest.
"""

from __future__ import annotations

import sys
import time
from statistics import mean

from tradingagents.agents.jev import jev_client
from tradingagents.report_features import QUESTIONS, Decision, extract_features

# ---------------------------------------------------------------------------
# A: bullish
# ---------------------------------------------------------------------------

A = {
    "market": """# NVDA technical analysis (week to 2026-09-22)
NVDA rose 9% on the week to a record close of $142.10 and has made higher highs and higher
lows for eight straight weeks. It trades well above its 50-day SMA ($124.30) and its
200-day SMA ($108.90), and the 50-day is rising steeply. Volume on the up days ran 40%
above average. The trend is clearly bullish.

RSI(14) is 77, deep in overbought territory, and the price is 14% above the 50-day, the
widest gap this year. After a run this sharp, a pullback toward $130 would be normal before
the uptrend resumes.""",
    "fundamentals": """# NVIDIA fundamentals
Revenue grew 68% year on year to $46.7 billion in the latest quarter, accelerating from 55%
the quarter before. Gross margin expanded to 75.1% from 72.4%, and operating cash flow rose
to $24.1 billion. The company holds $52 billion in cash against $8.5 billion of debt.

Valuation: at 31x forward earnings the stock trades below its five-year average and at a
discount to its high-growth peers once growth is taken into account (PEG 0.8 against a peer
median of 1.4). We consider it attractively priced.""",
    "sentiment": """**Overall Sentiment:** Mildly Bullish (score 6.6/10, confidence medium)
News headlines lean positive, led by coverage of the data-center ramp. StockTwits posts are
more bullish than bearish (about 60% bullish), mostly calm discussion of earnings
expectations, and Reddit threads are constructive without hype.""",
    "news": """# News (week to 2026-09-22)
- NVIDIA won a multi-year, $20 billion supply agreement with a major cloud provider, the
  largest in its history.
- Two brokers raised their price targets after checks showed Blackwell demand ahead of supply.
- NVIDIA reports quarterly results next Wednesday; the options market implies a large move.
Macro: inflation cooled for a third month and the Fed signalled cuts, a supportive backdrop
for growth stocks, and semiconductor demand indicators are rising.""",
    "research_debate": """Bull: Demand is running ahead of supply: the $20 billion contract, 68%
revenue growth and the margin expansion are all in the reported numbers, and the valuation is
below its own history.
Bear: Growth this fast cannot last forever, and customers may build their own chips.
Bull: Custom chips have been talked about for years, yet NVIDIA's share of AI spending rose
again this quarter; the bear offers no evidence the shift is happening now.
Bear: I concede the near-term numbers are strong; my concern is only the distant future.""",
    "risk_debate": """Aggressive: The earnings report next week is a catalyst with the demand
evidence on our side; a full position is justified.
Conservative: The stock is overbought after an 8-week run, so size carefully.
Aggressive: Overbought conditions have persisted through this whole trend, and the balance
sheet carries no risk. The downside case rests on a pullback, not on a thesis break.
Neutral: The conservative point about entry is fair, but the risks raised are timing risks
that a stop at $128 covers. The upside argument is better supported.""",
    "decision": """**Rating**: Buy

**Executive Summary**: Buy NVDA now. The evidence is clear-cut: accelerating revenue,
expanding margins, a record contract and a valuation below its history.

**Investment Thesis**: Every analyst report supports the call, and the bear case offered no
evidence against it. We are confident the earnings report will confirm the demand ramp.""",
}

# ---------------------------------------------------------------------------
# B: bearish
# ---------------------------------------------------------------------------

B = {
    "market": """# NVDA technical analysis (week to 2026-09-22)
NVDA fell 12% on the week to $88.40, its lowest close in a year, and has made lower highs
and lower lows for seven weeks. It trades well below its 50-day SMA ($104.60) and its
200-day SMA ($112.30), and the 50-day crossed below the 200-day. Volume on the down days ran
60% above average. The trend is clearly bearish.

RSI(14) is 21, deeply oversold, and the price is 15% below the 50-day. After a fall this
steep, a reflex rebound toward $95 is likely before sellers return.""",
    "fundamentals": """# NVIDIA fundamentals
Revenue fell 18% year on year to $22.1 billion, the second straight decline, and the company
cut its outlook. Gross margin collapsed to 58% from 71% on inventory write-downs, and
operating cash flow turned negative. Debt rose to $31 billion after a debt-funded
acquisition, against $9 billion of cash, and interest costs now absorb a third of operating
income; the company is burning cash.

Valuation: even after the fall the stock trades at 62x forward earnings, far above its
history and its peers. The price still assumes a return to rapid growth that nothing in the
numbers supports; we consider the valuation stretched.""",
    "sentiment": """**Overall Sentiment:** Strongly Bearish (score 1.4/10, confidence high)
Headlines are uniformly negative. StockTwits is 85% bearish, with posts calling the stock a
collapsing bubble, and several Reddit threads describe panic selling and capitulation, with
users posting losses and vowing never to buy it again.""",
    "news": """# News (week to 2026-09-22)
- NVIDIA's largest customer cancelled orders worth $6 billion and moved to its own chips.
- Regulators opened an antitrust investigation into the company's sales practices.
- Four brokers downgraded the stock to Sell.
Macro: rates rose again as inflation re-accelerated, and new export restrictions cut off
sales to several markets; the sector backdrop is a clear headwind for the company.""",
    "research_debate": """Bull: The company has recovered from downturns before, and AI is a
long-term trend.
Bear: The reported numbers show revenue falling, margins collapsing and cash burn, the largest
customer has left, and the valuation is still far above its history. The bull cites no
evidence that demand is returning.
Bull: A rebound could come if the customer returns.
Bear: That is a hope, not evidence; nothing in the reports suggests it.""",
    "risk_debate": """Aggressive: The stock is oversold, so a rebound trade could work.
Conservative: The balance sheet is weakening, the cash burn and the antitrust case are
unanswered risks, and a falling knife can fall further.
Aggressive: I accept the fundamentals are poor; this would only be a short-term trade.
Neutral: The aggressive side has conceded the thesis. The risks are serious and nobody has
answered them; caution clearly wins.""",
    "decision": """**Rating**: Underweight

**Executive Summary**: Reduce NVDA, although this is a close call: the stock is deeply
oversold and a rebound is possible.

**Investment Thesis**: The fundamentals have weakened, but the picture could change quickly
if orders return, and several caveats apply: the oversold reading, possible policy support,
and the risk of selling at the low. We would revisit the call on any sign of stabilisation.""",
}

# ---------------------------------------------------------------------------
# C: mixed
# ---------------------------------------------------------------------------

C = {
    "market": """# NVDA technical analysis (week to 2026-09-22)
NVDA was flat on the week at $118.20 and has traded between $112 and $124 for two months. It
sits between its 50-day SMA ($119.10) and its 200-day SMA ($115.40), and both are flat.
Volume is near average. RSI(14) is 51 and MACD is near zero. There is no clear trend; the
signals are mixed.""",
    "fundamentals": """# NVIDIA fundamentals
Revenue grew 4% year on year to $30.2 billion, in line with the prior quarter. Gross margin
was 71%, unchanged, and operating cash flow was steady. Cash of $30 billion comfortably covers
$9 billion of debt.

Valuation: at 34x forward earnings the stock trades in line with its five-year average and
with its peers; we see it as fairly valued.""",
    "sentiment": """**Overall Sentiment:** Neutral (score 5.0/10, confidence medium)
Headlines are balanced. StockTwits posts split roughly evenly between bulls and bears, and
Reddit discussion is sparse and calm.""",
    "news": """# News (week to 2026-09-22)
- NVIDIA launched a mid-range data-center card, broadly as expected.
- One broker raised its target and another lowered it.
- The company presents at an industry conference next month, where it may update its roadmap.
Macro: economic data were mixed and rate expectations were unchanged; the backdrop is neutral
for the sector.""",
    "research_debate": """Bull: Demand is stable and margins are holding at 71%.
Bear: Growth has slowed to 4%, so there is little to drive the stock.
Bull: Slower growth is already in the price at an average multiple.
Bear: Fair, but there is no catalyst either. Both sides have a point; neither case is
clearly stronger.""",
    "risk_debate": """Aggressive: The range could break upward on the conference.
Conservative: It could equally break down; the risks and the upside look similar.
Neutral: Both sides are right that the range could break either way. The argument ends even:
neither the risk nor the upside is better supported.""",
    "decision": """**Rating**: Hold

**Executive Summary**: Hold NVDA. The call is clear, with some caveats: the fundamentals are
stable, and the valuation is fair.

**Investment Thesis**: Growth is steady but slow, sentiment is balanced, and the stock is
range-bound. The conference next month could change the picture, but for now a Hold fits the
evidence.""",
}

# Which run should score higher on each question: "A>B" or "A<B".
EXPECTED = {
    "price_trend": "A>B", "overbought": "A>B", "oversold": "A<B",
    "fundamentals_trend": "A>B", "valuation_stretch": "A<B", "balance_sheet_risk": "A<B",
    "sentiment_tone": "A>B", "sentiment_extremity": "A<B",
    "news_tone": "A>B", "catalyst_proximity": "A>B", "macro_headwind": "A<B",
    "bull_bear_balance": "A>B", "risk_debate_asymmetry": "A>B", "conviction": "A>B",
}
SCORES = {q.id for q in QUESTIONS if len(q.columns) == 2}


def _fmt(values) -> str:
    return " ".join(f"{x:.2f}" for x in values)


def main(runs: int = 3) -> None:
    decisions = [Decision("NVDA", "2026-09-22", "2026-09-29", r, r, 0.0, docs)
                 for r, docs in (("Buy", A), ("Underweight", B), ("Hold", C))]
    client = jev_client()
    if client is None:
        sys.exit("Set TYPESAFE_API_KEY and install the jev extra first.")

    results = []  # per run: rows for A, B, C
    with client:
        for run in range(runs):
            started = time.perf_counter()
            extraction = extract_features(client, decisions)
            took = time.perf_counter() - started
            results.append(extraction.rows)
            print(f"run {run + 1}: {extraction.requests} requests in {took:.1f} s, "
                  f"models {sorted(extraction.models)}")

    held = 0
    print(f"\n{'question':24} {'expected':8}  {'A (bullish)':>20}  {'C (mixed)':>20}  "
          f"{'B (bearish)':>20}  held  C between")
    for q in QUESTIONS:
        a, b, c = ([rows[i][q.id] for rows in results] for i in (0, 1, 2))
        order = EXPECTED[q.id]
        ok = all((x > y) if order == "A>B" else (x < y) for x, y in zip(a, b, strict=True))
        between = all(min(x, y) <= z <= max(x, y) for x, y, z in zip(a, b, c, strict=True))
        held += ok
        print(f"{q.id:24} {order:8}  {_fmt(a):>20}  {_fmt(c):>20}  {_fmt(b):>20}  "
              f"{'yes' if ok else 'NO':4}  {('yes' if between else 'no') if q.id in SCORES else '-'}")
        if q.id in SCORES:
            sd = [rows[i][f'{q.id}_sd'] for rows in results for i in range(3)]
            print(f"{'':24} {'spread':8}  mean sd {mean(sd):.2f}, max {max(sd):.2f}")
    print(f"\n{held} of {len(QUESTIONS)} questions ordered A and B as expected on every run.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
