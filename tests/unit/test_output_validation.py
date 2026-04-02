"""Unit tests for output validation utilities."""

import pytest
from tradingagents.agents.utils.output_validation import (
    validate_ticker_relevance,
    validate_news_analysis,
    validate_news_analysis_detailed,
    format_validation_warning,
)


class TestValidateTickerRelevance:
    def test_passes_for_valid_output(self):
        """Test validation passes for output with sufficient ticker mentions."""
        output = """
        RIG Analysis:
        Transocean (RIG) received a downgrade from Clarksons on 2026-03-15.
        RIG stock declined 5.2% following the announcement.
        Tudor Capital was identified as a forced seller of RIG shares.
        According to the article, RIG faces headwinds from declining day rates.
        """
        
        is_valid, reason = validate_ticker_relevance(output, "RIG", min_mentions=3)
        
        assert is_valid
        assert "Valid" in reason
    
    def test_fails_for_insufficient_mentions(self):
        """Test validation fails when ticker mentioned too few times."""
        output = """
        The energy sector faces challenges.
        Offshore drilling remains under pressure.
        Portfolio diversification is recommended.
        """
        
        is_valid, reason = validate_ticker_relevance(output, "RIG", min_mentions=3)
        
        assert not is_valid
        assert "mentioned only" in reason
        assert "hallucinated" in reason.lower()
    
    def test_fails_for_missing_article_references(self):
        """Test validation fails when no article references present."""
        output = """
        RIG is a company. RIG operates in energy. RIG trades on NYSE.
        RIG has various risk factors. RIG may face challenges.
        """
        
        is_valid, reason = validate_ticker_relevance(output, "RIG", check_article_refs=True)
        
        assert not is_valid
        assert "citation" in reason.lower() or "source" in reason.lower()
    
    def test_detects_article_references(self):
        """Test validation recognizes various article reference patterns."""
        patterns = [
            "According to Reuters on 2026-03-15...",
            "Bloomberg reported the stock fell...",
            "Reuters said the deal was completed...",
            "Source: Bloomberg, March 15, 2026",
            "The report dated 03/15/2026 stated...",
        ]
        
        for pattern in patterns:
            output = f"RIG RIG RIG {pattern} RIG details about the company."
            is_valid, _ = validate_ticker_relevance(output, "RIG", min_mentions=3)
            assert is_valid, f"Failed to recognize pattern: {pattern}"
    
    def test_case_insensitive_ticker_matching(self):
        """Test ticker matching is case-insensitive."""
        output = "rig RIG Rig RiG analysis"
        is_valid, _ = validate_ticker_relevance(output, "RIG", min_mentions=3, check_article_refs=False)
        assert is_valid


class TestValidateNewsAnalysis:
    def test_passes_for_valid_news_analysis(self):
        """Test validation passes for proper news analysis."""
        output = """
        RIG News Analysis - 2026-03-31
        
        1. Clarksons Downgrade (2026-03-15):
           - Transocean (RIG) downgraded to Sell
           - Target price reduced to $4.50 (-15%)
           - Analyst cited declining day rates affecting RIG margins
        
        2. Unusual Options Activity:
           - RIG put volume: 50.2% above average
           - According to market data, RIG 30-day IV elevated to 52%
        
        3. Tudor Capital Position:
           - Report dated 2026-03-20 shows Tudor as forced seller
           - RIG position: 8.2M shares (down from 15M)
           - Source: Form 13F filing
        
        Summary: RIG faces multiple headwinds with specific price targets.
        """
        
        is_valid, reason = validate_news_analysis(output, "RIG")
        
        assert is_valid
        assert "Valid" in reason
    
    def test_fails_for_generic_portfolio_advice(self):
        """Test validation fails for generic portfolio strategy hallucination."""
        output = """
        RIG Portfolio Strategy
        
        IX. Asset Allocation
        Diversify your portfolio across multiple asset classes.
        Consider your risk tolerance and investment horizon.
        
        X. Risk Management
        Implement dollar-cost averaging for long-term growth.
        Regular rebalancing strategy maintains target allocation.
        Portfolio diversification reduces unsystematic risk.
        """
        
        is_valid, reason = validate_news_analysis(output, "RIG")
        
        assert not is_valid
        assert "hallucinated" in reason.lower() or "mentioned only" in reason.lower()
    
    def test_fails_for_missing_quantitative_data(self):
        """Test validation fails when no numbers or dates present."""
        output = """
        RIG faced challenges recently. The company received negative coverage.
        Analysts are concerned about the RIG outlook. RIG shares declined.
        Market sentiment remains bearish on RIG in the energy sector.
        RIG management is addressing operational issues with the fleet.
        """

        is_valid, reason = validate_news_analysis(output, "RIG")

        assert not is_valid
        assert (
            "numbers" in reason.lower()
            or "dates" in reason.lower()
            or "mentioned only" in reason.lower()
            or "citation" in reason.lower()
        )
    
    def test_recognizes_quantitative_data(self):
        """Test validation recognizes various numeric formats."""
        numeric_patterns = [
            ("$4.50 target price", True),
            ("declined 5.2%", True),
            ("down 15%", True),
            ("$75.50/barrel", True),
            ("2026-03-15", True),
            ("03/15/2026", True),
        ]
        
        for pattern, should_have_numbers in numeric_patterns:
            output = f"RIG RIG RIG {pattern} RIG RIG analysis RIG report"
            is_valid, reason = validate_news_analysis(output, "RIG")
            # Should pass because it has numbers/dates + ticker mentions
            assert is_valid or "numbers" not in reason.lower(), f"Failed on: {pattern}"
    
    def test_minimum_ticker_mentions_higher_than_basic_validation(self):
        """Test news analysis requires more mentions than basic validation."""
        # This would pass basic validation (3 mentions) but fail news validation (5 mentions)
        output = """
        RIG company analysis dated 2026-03-15.
        According to reports, RIG stock declined $2.50.
        RIG target price: $4.50 per share.
        """
        
        is_valid, reason = validate_news_analysis(output, "RIG")
        
        # Should fail because news analysis requires 5+ mentions
        assert not is_valid
        assert "mentioned only" in reason

    def test_fails_for_unknown_explicit_source(self):
        output = """
        RIG News Analysis - 2026-03-31
        - RIG fell 4.5% on 2026-03-31 after Scout Money reported insider pressure.
        - According to Scout Money on 2026-03-31, RIG options flow turned negative.
        - RIG now trades near $4.50 and RIG implied volatility rose 12%.
        - RIG management faces funding pressure while RIG sentiment remains weak.
        """

        result = validate_news_analysis_detailed(output, "RIG")

        assert not result.is_valid
        assert result.code == "unknown_source"
        assert "Scout Money" in result.reason

    def test_fails_for_missing_scanner_citation(self):
        output = """
        RIG News Analysis - 2026-03-31
        - RIG smart money activity turned negative on 2026-03-31 with unusual volume.
        - RIG institutional flow deteriorated by 18% while RIG put volume increased 22%.
        - Reuters reported RIG dayrates remain under pressure on 2026-03-31.
        - RIG now trades near $4.50 and RIG remains under review.
        """

        result = validate_news_analysis_detailed(output, "RIG")

        assert not result.is_valid
        assert result.code == "missing_scanner_citation"

    def test_fails_for_scanner_sec_conflation(self):
        output = """
        RIG News Analysis - 2026-03-31
        - RIG showed insider buying in the smart money scanner.
        - [Source: Finviz Smart Money Scanner | Scan Date: 2026-03-31] confirms SEC Form 4 insider buying for RIG.
        - Reuters reported RIG contract dayrates weakened on 2026-03-31.
        - RIG trades at $4.50 and RIG volatility rose 10% while RIG sentiment deteriorated.
        """

        result = validate_news_analysis_detailed(output, "RIG")

        assert not result.is_valid
        assert result.code == "scanner_sec_conflation"


class TestFormatValidationWarning:
    def test_formats_warning_banner(self):
        """Test warning banner is properly formatted."""
        output = "Original output text"
        ticker = "RIG"
        reason = "Insufficient ticker mentions"
        
        result = format_validation_warning(output, ticker, reason)
        
        # Should include warning marker
        assert "⚠️" in result
        assert "WARNING" in result.upper()
        
        # Should include ticker and reason
        assert ticker in result
        assert reason in result
        
        # Should include original output
        assert "Original output text" in result
        
        # Warning should come before original output
        warning_pos = result.index("⚠️")
        output_pos = result.index("Original output text")
        assert warning_pos < output_pos
    
    def test_preserves_original_output(self):
        """Test original output is preserved intact."""
        output = "Line 1\nLine 2\nLine 3"
        result = format_validation_warning(output, "RIG", "Test reason")
        
        # Original output should be present exactly
        assert "Line 1\nLine 2\nLine 3" in result


class TestValidationEdgeCases:
    def test_handles_empty_output(self):
        """Test validation handles empty output gracefully."""
        is_valid, reason = validate_ticker_relevance("", "RIG")
        assert not is_valid
        assert "Empty" in reason
    
    def test_handles_empty_ticker(self):
        """Test validation handles empty ticker gracefully."""
        is_valid, reason = validate_ticker_relevance("Some output", "")
        assert not is_valid
        assert "Empty" in reason
    
    def test_handles_none_inputs(self):
        """Test validation handles None inputs gracefully."""
        is_valid, reason = validate_ticker_relevance(None, "RIG")
        assert not is_valid
        
        is_valid, reason = validate_ticker_relevance("Output", None)
        assert not is_valid
    
    def test_word_boundary_matching(self):
        """Test ticker matching respects word boundaries."""
        # "TRIGGER" contains "RIG" but shouldn't count as a mention
        output = """
        The TRIGGER for this analysis is RIGID market conditions.
        However, RIG stock specifically faces challenges.
        RIG is mentioned here correctly.
        """
        
        is_valid, reason = validate_ticker_relevance(output, "RIG", min_mentions=2, check_article_refs=False)
        
        # Should only count the 2 standalone "RIG" mentions, not TRIGGER or RIGID
        assert is_valid  # Has exactly 2 valid mentions


class TestValidationScenarios:
    """Real-world validation scenarios based on actual issues."""
    
    def test_detects_rig_hallucination_case(self):
        """Test the actual RIG hallucination case that motivated this fix."""
        # This is the type of output that was produced instead of news analysis
        hallucinated_output = """
        IX. Portfolio Risk Management Strategy
        
        A well-diversified portfolio should include a mix of asset classes.
        Consider your investment horizon when selecting securities.
        Regular rebalancing maintains target allocations.
        
        Risk tolerance varies by investor based on age and goals.
        Dollar-cost averaging can reduce timing risk over long periods.
        
        X. Asset Allocation Guidelines
        
        Equities should comprise 60-80% for growth-oriented portfolios.
        Fixed income provides stability and income generation.
        Alternative investments offer diversification benefits.
        """
        
        is_valid, reason = validate_news_analysis(hallucinated_output, "RIG")
        
        # Should definitively fail this hallucination
        assert not is_valid
        assert "generic portfolio strategy" in reason.lower() or "mentioned only" in reason
    
    def test_accepts_proper_news_analysis(self):
        """Test a proper news analysis passes validation."""
        proper_output = """
        ## RIG News Analysis - Week of 2026-03-24
        
        ### 1. Clarksons Downgrade (March 15, 2026)
        - Transocean (RIG) downgraded from Hold to Sell
        - Price target: $4.50 (previously $5.25, -14.3%)
        - Rationale: "Declining day rates in ultra-deepwater segment affecting RIG profitability"
        - Source: Clarksons Platou Securities analyst report
        
        ### 2. Unusual Options Activity (March 18-20, 2026)
        - RIG put volume: 50.2% above 30-day average
        - March 20 $5 strikes seeing elevated activity
        - 30-day implied volatility: 52% (vs. 38% historical)
        - Data source: Market analytics platforms
        
        ### 3. Tudor Capital Forced Seller (March 20, 2026)
        - Tudor reducing RIG position from 15.0M to 8.2M shares (-45.3%)
        - Characterized as "forced seller" per 13F filing
        - RIG declined 3.2% on March 20 following disclosure
        
        ### Impact Summary
        | Factor | Impact | Magnitude |
        |--------|--------|-----------|
        | Analyst downgrade | Negative | -14.3% PT cut |
        | Options positioning | Bearish | +50.2% put vol |
        | Institutional selling | Negative | -6.8M shares |
        
        RIG faces converging negative catalysts with quantified impact on valuation.
        """
        
        is_valid, reason = validate_news_analysis(proper_output, "RIG")
        
        # Should pass all validation checks
        assert is_valid, f"Valid output failed validation: {reason}"
