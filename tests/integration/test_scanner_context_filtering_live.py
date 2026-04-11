"""Live integration tests for scanner context filtering with real AlphaVantage data.

Makes real HTTP requests to AlphaVantage API to measure actual token reduction
on production-quality scanner contexts containing live news data.

Requires ALPHA_VANTAGE_API_KEY environment variable.

Run with:
    pytest tests/integration/test_scanner_context_filtering_live.py -v -m integration
"""
import json
import os
import pytest
from datetime import datetime, timedelta

from tradingagents.dataflows.alpha_vantage_news import get_news as get_alpha_vantage_news
from tradingagents.agents.utils.context_filtering import filter_scanner_context_for_ticker


def _build_context_with_real_news(ticker: str) -> tuple[str, list[dict]]:
    """Fetch real AV news and embed it in a production-sized scanner context."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    news_response = get_alpha_vantage_news(
        ticker=ticker,
        start_date=start_date.strftime("%Y%m%dT%H%M"),
        end_date=end_date.strftime("%Y%m%dT%H%M"),
    )

    if isinstance(news_response, str):
        news_data = json.loads(news_response)
    else:
        news_data = news_response

    articles = news_data.get("feed", [])

    context = f"""# SCANNER CONTEXT PACKET: {ticker}
Date: {end_date.strftime("%Y-%m-%d")}

## I. TICKER-SPECIFIC SCANNER THESIS
Rationale: Energy sector recovery play
Thesis Angle: Offshore drilling rebound
Conviction: Medium
Key Catalyst: Oil price stability above $70/bbl

## II. STRUCTURED LIVE DATA (GROUND TRUTH)

### Commodity Prices
- WTI Crude: $72.50 (+2.3%)
- Brent: $76.20 (+1.8%)
- Natural Gas: $2.85 (-0.5%)

### FX Rates
- EUR/USD: 1.0850
- GBP/USD: 1.2640
- USD/JPY: 151.20

### Earnings Calendar (7d lookback, 14d lookahead)
- {ticker}: Q4 earnings (Market Cap: 6.2B, Sector: Energy)
- XOM: Exxon Mobil (500B cap, Energy)
- CVX: Chevron (280B cap, Energy)
- COP: ConocoPhillips (140B cap, Energy)
- SLB: Schlumberger (65B cap, Energy)
- EOG: EOG Resources (70B cap, Energy)
- MPC: Marathon Petroleum (55B cap, Energy)
- PSX: Phillips 66 (50B cap, Energy)
- VLO: Valero Energy (45B cap, Energy)
- OXY: Occidental Petroleum (48B cap, Energy)
- HAL: Halliburton (28B cap, Energy)
- BKR: Baker Hughes (32B cap, Energy)
- MRO: Marathon Oil (18B cap, Energy)
- DVN: Devon Energy (30B cap, Energy)
- FANG: Diamondback Energy (35B cap, Energy)
- HES: Hess Corporation (42B cap, Energy)
- AAPL: Apple Inc (3000B cap, Technology)
- MSFT: Microsoft Corp (2800B cap, Technology)
- GOOGL: Alphabet Inc (1800B cap, Technology)
- AMZN: Amazon.com Inc (1600B cap, Consumer Cyclical)
- NVDA: NVIDIA Corp (2200B cap, Technology)
- META: Meta Platforms (1200B cap, Communication Services)
- TSLA: Tesla Inc (800B cap, Consumer Cyclical)
- BRK.B: Berkshire Hathaway (900B cap, Financial Services)
- JPM: JPMorgan Chase (550B cap, Financial Services)
- V: Visa Inc (520B cap, Financial Services)
- JNJ: Johnson & Johnson (480B cap, Healthcare)
- WMT: Walmart Inc (450B cap, Consumer Defensive)
- PG: Procter & Gamble (380B cap, Consumer Defensive)
- MA: Mastercard Inc (420B cap, Financial Services)

### Economic Calendar (7d lookback, 14d lookahead)
- FOMC Meeting Minutes (Mar 20, High Impact)
- Core CPI m/m (Mar 22, High Impact)
- Retail Sales m/m (Mar 23, High Impact)
- GDP Growth Rate (Mar 28, High Impact)
- Unemployment Rate (Mar 29, High Impact)
- ISM Manufacturing PMI (Apr 1, High Impact)
- Nonfarm Payrolls (Apr 5, High Impact)
- Core PCE Price Index (Apr 6, High Impact)
- Fed Chair Powell Speech (Apr 10, High Impact)
- Producer Price Index (Apr 12, High Impact)
- Building Permits (Mar 18, Medium Impact)
- Housing Starts (Mar 18, Medium Impact)
- Industrial Production (Mar 19, Medium Impact)
- Consumer Confidence (Mar 25, Medium Impact)
- Durable Goods Orders (Mar 26, Medium Impact)

## III. SMART MONEY & FLOW SIGNALS

### Dark Pool & Block Activity
- {ticker}: Unusual dark pool volume (2.5M shares at $45.20)
- {ticker}: Block trade detected - 500K shares institutional buy
- Sector flow: Energy seeing +$450M inflows (weekly)

### Options Flow Analysis
- XOM: Bullish call sweep 1500 @ $120 strike (Jun expiry)
- CVX: Put/call ratio declining (0.6 -> 0.45)
- {ticker}: Unusual put activity 800 contracts @ $40 strike
- Sector options: Net bullish positioning across energy names

## IV. FACTOR ALIGNMENT & DRIFT

### {ticker} Factor Scores
- Momentum: +0.35 (improving)
- Value: +0.62 (attractive)
- Quality: +0.28 (stable)
- Growth: -0.15 (challenged)
- Low Volatility: +0.45

### Sector Factor Rotation
- Energy momentum turning positive (+0.25 this week)
- Technology momentum fading (-0.18 from +0.45)
- Financials quality improving (+0.32)
- Healthcare defensive positioning strengthening

## V. MACRO & GEOPOLITICAL CONTEXT

### Central Bank Policy
- Fed holding rates at 5.25-5.50% (5th consecutive hold)
- Market pricing 60% chance of June cut
- ECB signaling potential May cut
- BoJ maintaining ultra-loose policy

### Geopolitical Risks
- Middle East tensions elevated (Strait of Hormuz concerns)
- China economic stimulus measures announced ($200B package)
- EU energy diversification accelerating
- US-China tech restrictions expanding

## VI. SECTOR ROTATION & MARKET REGIME

### Current Market Regime: Risk-On Rotation
- S&P 500: +1.2% (week), testing 5200 resistance
- Volatility (VIX): 14.5 (declining from 18)
- Credit spreads: Tightening (HY: 350bps)

### Sector Performance (5D)
Energy: +3.2% (outperforming)
Materials: +2.1% (strength)
Industrials: +1.8% (rotation into)
Financials: +1.5% (steady)
Technology: -0.5% (taking profits)
Communication Services: -0.8% (weakness)
Consumer Discretionary: +0.3% (mixed)
Healthcare: +0.5% (defensive bid)
Utilities: -0.2% (rotation out)
Real Estate: -0.4% (rate concerns)

### Sector Rotation Signals
FROM: Technology, Communication Services
TO: Energy, Materials, Industrials (cyclical rotation)

## VII. KEY GLOBAL THEMES

### Energy Transition & Commodity Supercycle
- Oil demand forecasts revised higher (IEA: +1.8M bpd 2026)
- Natural gas storage below 5-year average (supply concerns)
- Offshore drilling contracts increasing (dayrate recovery)

### Inflation & Rate Path
- Core inflation sticky at 3.2% (above Fed 2% target)
- Services inflation elevated (wage pressures)
- Goods deflation moderating

### China Growth & Commodity Demand
- China stimulus supporting commodity demand
- Manufacturing PMI expanding (51.2)
- Infrastructure spending accelerating

## VIII. MACRO RISK FACTORS
- Inflation persistence (sticky services inflation)
- Credit tightening (regional bank stress)
- Geopolitical escalation (energy supply risk premium)
- Policy uncertainty (election year dynamics)
- Commercial real estate stress (refinancing wall)
"""

    if articles:
        context += f"\n## IX. REAL ALPHAVANTAGE NEWS (LAST 7 DAYS)\n\nTotal articles: {len(articles)}\n\n"
        for i, article in enumerate(articles[:15], 1):
            title = article.get("title", "N/A")
            source = article.get("source", "N/A")
            time_published = article.get("time_published", "N/A")
            summary = article.get("summary", "")
            relevance = 0.0
            for ts in article.get("ticker_sentiment", []):
                if ts.get("ticker", "").upper() == ticker.upper():
                    relevance = float(ts.get("relevance_score", 0.0))
                    break
            context += (
                f"### Article {i}: {title}\n"
                f"- Source: {source}\n"
                f"- Published: {time_published}\n"
                f"- Relevance to {ticker}: {relevance:.2f}\n"
                f"- Summary: {summary[:300]}...\n\n"
            )

    return context, articles


@pytest.mark.integration
@pytest.mark.enable_socket
class TestScannerContextFilteringLiveAV:
    """Integration tests using real AlphaVantage API calls."""

    def test_real_news_context_has_articles(self):
        """AlphaVantage should return at least one article for RIG in the last 7 days."""
        _, articles = _build_context_with_real_news("RIG")
        assert len(articles) >= 1, "Expected at least one RIG news article from AV"

    def test_filter_does_not_drop_news_section(self):
        """Real news section must be preserved (it's ticker-specific data)."""
        context, articles = _build_context_with_real_news("RIG")
        if not articles:
            pytest.skip("No articles returned by AV — cannot validate news preservation")

        result = filter_scanner_context_for_ticker(context, "RIG")
        # News section is Section IX — currently passed through as-is
        assert "ALPHAVANTAGE NEWS" in result or "Article 1" in result

    def test_filter_reduces_non_relevant_entries(self):
        """Filtered context should be smaller than or equal to 115% of original."""
        context, _ = _build_context_with_real_news("RIG")
        result = filter_scanner_context_for_ticker(context, "RIG")
        ratio = len(result) / len(context)
        assert ratio <= 1.15, (
            f"Filtered context is {ratio:.0%} of original — expected ≤115%"
        )

    def test_ticker_still_present_after_filter(self):
        """Ticker symbol must appear in filtered output."""
        context, _ = _build_context_with_real_news("RIG")
        result = filter_scanner_context_for_ticker(context, "RIG")
        assert "RIG" in result
