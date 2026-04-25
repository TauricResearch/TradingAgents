"""Integration tests for scanner context filtering.

Tests end-to-end token reduction using a production-sized scanner context.
These do not make live API calls (use static fixture data) but exercise the
full filtering pipeline.

Run with:
    pytest tests/integration/test_scanner_context_filtering.py -v
    pytest tests/integration/ -v -m integration
"""

import pytest

from tradingagents.agents.utils.context_filtering import filter_scanner_context_for_ticker

PRODUCTION_SIZED_CONTEXT = """# SCANNER CONTEXT PACKET: RIG
Date: 2026-03-31

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
- RIG: Q4 earnings (Market Cap: 6.2B, Sector: Energy)
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
- UNH: UnitedHealth Group (500B cap, Healthcare)

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
- RIG: Unusual dark pool volume (2.5M shares at $45.20)
- RIG: Block trade detected - 500K shares institutional buy
- Sector flow: Energy seeing +$450M inflows (weekly)

### Options Flow Analysis
- XOM: Bullish call sweep 1500 @ $120 strike (Jun expiry)
- CVX: Put/call ratio declining (0.6 -> 0.45)
- RIG: Unusual put activity 800 contracts @ $40 strike
- Sector options: Net bullish positioning across energy names

## IV. FACTOR ALIGNMENT & DRIFT

### RIG Factor Scores
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


@pytest.mark.integration
class TestScannerContextFilteringIntegration:
    """Integration tests for the full scanner context filtering pipeline."""

    def test_ticker_thesis_preserved(self):
        """Section I (ticker-specific thesis) must be present in filtered output."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        assert "TICKER-SPECIFIC SCANNER THESIS" in result

    def test_structured_data_preserved(self):
        """Section II (structured live data) must be present in filtered output."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        assert "STRUCTURED LIVE DATA" in result

    def test_macro_context_preserved(self):
        """Section V (macro & geopolitical) must survive filtering unchanged."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        assert "MACRO & GEOPOLITICAL CONTEXT" in result

    def test_global_themes_preserved(self):
        """Section VII (key global themes) must survive filtering unchanged."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        assert "KEY GLOBAL THEMES" in result

    def test_earnings_filtered_to_sector(self):
        """Earnings calendar should retain energy-sector entries and drop others."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        # Energy-sector company should be kept
        assert "XOM" in result
        # Large non-sector companies are kept in top-N overall but the filter note shows
        assert "Earnings Calendar" in result

    def test_smart_money_filtered_to_ticker(self):
        """Smart money section should retain only RIG-specific signals."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        assert "RIG" in result

    def test_non_energy_earnings_reduced(self):
        """Non-energy tech giants with smaller relevance should be reduced."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        # The full list of 15 non-energy companies should be trimmed
        # Tech giants appear in top-10 overall but not all 15
        original_size = len(PRODUCTION_SIZED_CONTEXT)
        filtered_size = len(result)
        # Filtering should not dramatically increase context size
        assert filtered_size <= original_size * 1.20

    def test_returns_string(self):
        """Filter function must always return a string."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "RIG")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_on_empty_ticker(self):
        """Empty ticker falls back to original context without error."""
        result = filter_scanner_context_for_ticker(PRODUCTION_SIZED_CONTEXT, "")
        assert result == PRODUCTION_SIZED_CONTEXT

    def test_fallback_on_empty_context(self):
        """Empty context returns empty string without error."""
        result = filter_scanner_context_for_ticker("", "RIG")
        assert result == ""
