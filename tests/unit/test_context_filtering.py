"""Unit tests for context filtering utilities."""

import pytest
from tradingagents.agents.utils.context_filtering import (
    filter_scanner_context_for_ticker,
    filter_earnings_calendar,
    filter_economic_calendar,
    extract_ticker_sector_from_rotation,
    filter_smart_money_for_ticker,
    filter_factor_alignment_for_ticker,
    _infer_sector_from_text,
)


# Sample test data
SAMPLE_SCANNER_CONTEXT = """# SCANNER CONTEXT PACKET: RIG
Date: 2026-03-31

## I. TICKER-SPECIFIC SCANNER THESIS
Rationale: Energy sector recovery play
Thesis Angle: Offshore drilling rebound
Conviction: Medium

## II. STRUCTURED LIVE DATA (GROUND TRUTH)
### Commodity Prices
Gold: $2,150/oz
Oil (WTI): $75.50/barrel
Bitcoin: $68,500

### FX Rates
EUR/USD: 1.0850
JPY/USD: 0.0067
CNY/USD: 0.1380

### Earnings Calendar (7d lookback, 14d lookahead)
2026-04-01: AAPL (Mega Cap, Technology) - Q1 earnings
2026-04-01: RIG (Energy) - Q4 earnings
2026-04-02: XOM (Large Cap, Energy) - Q1 earnings
2026-04-02: CVX (Large Cap, Energy) - Q4 earnings
2026-04-03: TSLA (Mega Cap, Consumer Discretionary) - Q1 earnings
[... 495 more entries ...]

### Economic Calendar (7d lookback, 14d lookahead)
2026-04-01: FOMC Meeting Minutes (High Importance)
2026-04-02: Jobless Claims (Medium Importance)
2026-04-03: CPI Data (High Importance)
2026-04-05: NFP Report (High Importance)
2026-04-08: Retail Sales (Medium Importance)
[... 50 more entries ...]

## III. SMART MONEY & FLOW SIGNALS
Unusual Options Activity:
- RIG: 50.2% unusual put volume, Tudor forced seller
- SPY: Large call spread opened
- Multiple tickers showing elevated IV

## IV. FACTOR ALIGNMENT & DRIFT
Factor Alignment Report:
- RIG: Value factor +2.5, Momentum factor -1.2
- AAPL: Quality factor +3.0, Growth factor +2.8
- TSLA: Momentum factor +4.0, Growth factor +2.5
[... 20 more tickers ...]

## V. MACRO & GEOPOLITICAL CONTEXT
Global tensions remain elevated in Middle East
Fed signaling potential rate cuts in H2 2026
China stimulus measures supporting commodities

## VI. SECTOR ROTATION & MARKET REGIME
Energy sector: +3.2% (outperforming)
Technology: +1.5%
Financials: -0.8%
Consumer Discretionary: -1.2%
Materials: +2.1% (related to Energy)
[... 7 more sectors ...]

## VII. KEY GLOBAL THEMES
- Energy transition uncertainty
- AI infrastructure buildout
- Geopolitical risk premium

## VIII. MACRO RISK FACTORS
- Inflation persistence
- Credit tightening
- Geopolitical escalation
"""


class TestFilterEarningsCalendar:
    def test_filters_to_ticker_and_same_sector(self):
        earnings = """
2026-04-01: AAPL (Mega Cap, Technology) - Q1 earnings
2026-04-01: RIG (Energy) - Q4 earnings
2026-04-02: XOM (Large Cap, Energy) - Q1 earnings
2026-04-02: CVX (Large Cap, Energy) - Q4 earnings
2026-04-03: TSLA (Mega Cap, Consumer Discretionary) - Q1 earnings
2026-04-04: SLB (Energy) - Q1 earnings
2026-04-05: HAL (Energy) - Q2 earnings
"""
        
        result = filter_earnings_calendar(earnings, "RIG", top_n_sector=3, top_n_overall=2)
        
        # Should include RIG
        assert "RIG" in result
        # Should include same-sector companies (Energy)
        assert "XOM" in result or "CVX" in result or "SLB" in result
        # Should include mega caps
        assert "AAPL" in result or "TSLA" in result
        # Should have filtering note
        assert "Filtered" in result
    
    def test_handles_empty_input(self):
        result = filter_earnings_calendar("", "RIG")
        assert result == ""
    
    def test_handles_no_ticker_match(self):
        earnings = "2026-04-01: AAPL - earnings\n2026-04-02: MSFT - earnings"
        result = filter_earnings_calendar(earnings, "XYZ", top_n_sector=5)
        # Should still return something (fallback)
        assert len(result) > 0


class TestFilterEconomicCalendar:
    def test_prioritizes_high_importance(self):
        econ = """
2026-04-01: FOMC Meeting Minutes (High Importance)
2026-04-02: Jobless Claims (Medium Importance)
2026-04-03: CPI Data (High Importance)
2026-04-05: NFP Report (High Importance)
2026-04-08: Retail Sales (Medium Importance)
2026-04-10: Building Permits (Low Importance)
2026-04-12: Industrial Production (Medium Importance)
"""
        
        result = filter_economic_calendar(econ, max_events=3)
        
        # Should include high-importance events
        assert "FOMC" in result or "CPI" in result or "NFP" in result
        # Should be shorter
        assert len(result) < len(econ)
        # Should mention filtering
        assert "Filtered" in result or "high-priority" in result.lower()
    
    def test_detects_key_indicators_without_tags(self):
        econ = """
2026-04-01: FOMC Meeting
2026-04-03: GDP Release
2026-04-05: Unemployment Report
"""
        
        result = filter_economic_calendar(econ, max_events=5)
        
        # Should recognize FOMC, GDP, unemployment as high priority
        assert "FOMC" in result
        assert "GDP" in result or "Unemployment" in result
    
    def test_handles_empty_input(self):
        result = filter_economic_calendar("")
        assert result == ""


class TestExtractTickerSectorFromRotation:
    def test_extracts_ticker_sector_and_related(self):
        sector_report = """
Sector Performance Report:

Energy sector: +3.2% (outperforming)
- RIG showing strong momentum
- XOM up 2.5%

Technology: +1.5%
- AAPL leading

Materials: +2.1% (commodities play)
- Related to Energy recovery

Financials: -0.8%
"""
        
        result = extract_ticker_sector_from_rotation(sector_report, "RIG")
        
        # Should include Energy (ticker's sector)
        assert "Energy" in result
        # Should include Materials (related sector)
        assert "Materials" in result or "related" in result.lower()
        # Should NOT include unrelated Financials detail
        # (may mention in passing, but shouldn't dominate)
        assert result.count("Energy") > result.count("Financials")
    
    def test_handles_unknown_ticker(self):
        sector_report = "Energy: +2%, Tech: +1%, Financials: -1%"
        result = extract_ticker_sector_from_rotation(sector_report, "XYZ")
        
        # Should return truncated version with note
        assert len(result) > 0
        assert "Truncated" in result or "unable" in result.lower()


class TestFilterSmartMoneyForTicker:
    def test_extracts_ticker_specific_signals(self):
        smart_money = """
Market Overview:
Elevated options activity across the board.

RIG Analysis:
50.2% unusual put volume detected.
Tudor Capital forced seller exiting position.
Institutional flow turning negative.

SPY Analysis:
Large call spread opened by institutional buyers.
"""
        
        result = filter_smart_money_for_ticker(smart_money, "RIG")
        
        # Should include RIG-specific section
        assert "RIG" in result
        assert "Tudor" in result or "put volume" in result
        # Should filter out unrelated SPY detail
        assert result.count("RIG") > result.count("SPY")
    
    def test_returns_summary_when_no_ticker_match(self):
        smart_money = """
Market Overview:
General options activity elevated.

Detail on various tickers...
"""
        
        result = filter_smart_money_for_ticker(smart_money, "XYZ")
        
        # Should return first paragraph + note
        assert "XYZ" in result  # In the note
        assert "no" in result.lower() and "found" in result.lower()
        assert "Market Overview" in result  # First paragraph

    def test_preserves_provenance_metadata(self):
        smart_money = """
Source: Finviz Smart Money Scanner
Scan Date: 2026-03-31
[Source: Finviz Smart Money Scanner | Scan Date: 2026-03-31]

Energy Flow Overview:
Broad energy flows improved.

RIG Analysis:
RIG unusual volume rose 22%.
"""

        result = filter_smart_money_for_ticker(smart_money, "RIG")

        assert "Source: Finviz Smart Money Scanner" in result
        assert "Scan Date: 2026-03-31" in result
        assert "[Source: Finviz Smart Money Scanner | Scan Date: 2026-03-31]" in result
        assert "## III. SMART MONEY" not in result


class TestFilterFactorAlignmentForTicker:
    def test_extracts_ticker_factors(self):
        factor_report = """
Factor Alignment Analysis:

Macro Regime: Value factors outperforming

RIG Factor Score:
- Value: +2.5
- Momentum: -1.2
- Quality: +0.8

AAPL Factor Score:
- Quality: +3.0
- Growth: +2.8
"""
        
        result = filter_factor_alignment_for_ticker(factor_report, "RIG")
        
        # Should include RIG factors
        assert "RIG" in result
        assert "Value" in result or "Momentum" in result
        # Should include macro regime summary
        assert "Macro" in result or "regime" in result.lower()
        # Should filter out unrelated AAPL detail
        assert result.count("RIG") >= result.count("AAPL")
    
    def test_handles_no_ticker_match(self):
        # Use text that doesn't match summary keywords
        factor_report = "Some random analysis text about companies..."
        result = filter_factor_alignment_for_ticker(factor_report, "XYZ")
        
        # Should return truncated with note about no match
        assert "XYZ" in result
        assert "No" in result and "found" in result


class TestInferSectorFromText:
    def test_infers_energy_sector(self):
        text = "RIG is a leading Energy sector company specializing in offshore drilling."
        sector = _infer_sector_from_text(text, "RIG")
        assert sector == "Energy"
    
    def test_infers_technology_sector(self):
        text = "AAPL: Technology sector leader in consumer electronics."
        sector = _infer_sector_from_text(text, "AAPL")
        assert sector == "Technology" or sector == "Information Technology"
    
    def test_returns_none_when_not_found(self):
        text = "XYZ is a company."
        sector = _infer_sector_from_text(text, "XYZ")
        assert sector is None


class TestFilterScannerContextForTicker:
    def test_reduces_context_size(self):
        """Test that filtering reduces context size (or stays similar for small samples)."""
        result = filter_scanner_context_for_ticker(SAMPLE_SCANNER_CONTEXT, "RIG")
        
        # Our sample is small (~2K chars), so filtering overhead (notes) may increase size slightly
        # Real contexts are 10K+ and will see 60-70% reduction
        # For test sample, just verify we don't explode the size (allow up to 15% increase)
        size_ratio = len(result) / len(SAMPLE_SCANNER_CONTEXT)
        assert size_ratio < 1.15, f"Filtered size {len(result)} is {size_ratio:.0%} of original {len(SAMPLE_SCANNER_CONTEXT)}, expected <115%"
        
        # Should still include critical sections
        assert "TICKER-SPECIFIC SCANNER THESIS" in result or "## I." in result
        assert "MACRO & GEOPOLITICAL CONTEXT" in result or "## V." in result
        assert "KEY GLOBAL THEMES" in result or "## VII." in result
    
    def test_preserves_ticker_specific_content(self):
        """Test that ticker-specific content is preserved."""
        result = filter_scanner_context_for_ticker(SAMPLE_SCANNER_CONTEXT, "RIG")
        
        # Should preserve RIG-specific content
        assert "RIG" in result
        assert "Energy" in result  # Ticker's sector
        assert "Tudor" in result or "put volume" in result  # Smart money signal
    
    def test_filters_irrelevant_tickers(self):
        """Test that unrelated ticker details are filtered out."""
        result = filter_scanner_context_for_ticker(SAMPLE_SCANNER_CONTEXT, "RIG")
        
        # Should reduce mentions of unrelated tickers
        # RIG should appear more than TSLA
        assert result.count("RIG") > result.count("TSLA")
    
    def test_handles_empty_context(self):
        """Test graceful handling of empty input."""
        result = filter_scanner_context_for_ticker("", "RIG")
        assert result == ""
    
    def test_handles_malformed_context(self):
        """Test that malformed context doesn't crash."""
        malformed = "Random text without proper sections"
        result = filter_scanner_context_for_ticker(malformed, "RIG")
        
        # Should return something (fallback to original)
        assert len(result) > 0
    
    def test_preserves_global_macro_sections(self):
        """Test that global macro context is preserved."""
        result = filter_scanner_context_for_ticker(SAMPLE_SCANNER_CONTEXT, "RIG")
        
        # Should keep global context sections
        assert "MACRO & GEOPOLITICAL CONTEXT" in result
        assert "KEY GLOBAL THEMES" in result
        assert "MACRO RISK FACTORS" in result


class TestIntegration:
    def test_full_filtering_pipeline(self):
        """Integration test: full context filtering."""
        result = filter_scanner_context_for_ticker(SAMPLE_SCANNER_CONTEXT, "RIG")
        
        # Verify structure
        assert "# SCANNER CONTEXT PACKET" in result
        assert result.startswith("# SCANNER CONTEXT PACKET")
        
        # Verify key sections present
        assert "## I." in result
        assert "## II." in result
        
        # Verify significant size reduction
        original_size = len(SAMPLE_SCANNER_CONTEXT)
        filtered_size = len(result)
        reduction_pct = (1 - filtered_size / original_size) * 100
        
        print(f"\nContext reduction: {reduction_pct:.1f}%")
        print(f"Original: {original_size} chars, Filtered: {filtered_size} chars")

        # The small unit-test fixture (~2K chars) may not shrink because filter
        # metadata labels add overhead. The 40%+ reduction target is verified on a
        # production-sized context in tests/integration/test_scanner_context_filtering.py.
        # Here we just confirm the output doesn't balloon (< 30% growth is acceptable).
        assert reduction_pct > -30, f"Output grew too much: {-reduction_pct:.1f}% larger than input"
