"""Unit tests for output validation utilities."""

import pytest

from tradingagents.agents.utils.output_validation import (
    build_market_report_structured,
    extract_allowed_sources_from_context,
    extract_explicit_sources,
    filter_news_report_by_provenance,
    format_validation_warning,
    infer_macro_regime_from_prefetched_report,
    render_structured_news_payload,
    sanitize_structured_news_payload,
    validate_news_analysis,
    validate_news_analysis_detailed,
    validate_structured_news_payload,
    validate_ticker_relevance,
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
        is_valid, _ = validate_ticker_relevance(
            output, "RIG", min_mentions=3, check_article_refs=False
        )
        assert is_valid


class TestMarketStructuredContract:
    def test_infer_macro_regime_from_prefetched_report(self):
        assert (
            infer_macro_regime_from_prefetched_report("## Risk-On\nMarket is RISK-ON.") == "risk_on"
        )
        assert infer_macro_regime_from_prefetched_report("[Error] failed fetch") == "unknown"
        assert infer_macro_regime_from_prefetched_report("") == "unknown"
        # Regression: "0 risk-off signals" in a RISK-ON report must not flip the result.
        risk_on_with_counter = (
            "## Regime: RISK-ON\n"
            "Macro regime: **RISK-ON** (score +3/6). "
            "3 risk-on signals, 0 risk-off signals, 3 neutral."
        )
        assert infer_macro_regime_from_prefetched_report(risk_on_with_counter) == "risk_on"
        # Table-row format used by macro_regime_report.
        assert infer_macro_regime_from_prefetched_report("| Regime | **RISK-OFF** |") == "risk_off"

    def test_build_market_report_structured_completed(self):
        structured = build_market_report_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            market_report="- AAPL held support at $190.25\n\n| Level | Value |\n|---|---|\n| Support | $190.25 |",
            macro_regime_report="## Risk-Off\nMarket is RISK-OFF.",
        )

        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "market_summary_v1"
        assert structured["macro_regime"] == "risk_off"
        assert "$190.25" in structured["key_levels"]
        assert structured["key_metrics"]["summary_table_rows"] >= 2

    def test_build_market_report_structured_ignores_legacy_abort_marker(self):
        structured = build_market_report_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            market_report="[CRITICAL ABORT] Reason: Trading halted pending delisting",
            macro_regime_report="## Transition\nMarket is TRANSITION.",
        )

        assert structured["status"] == "completed"
        assert structured["abort_reason"] == ""
        assert structured["macro_regime"] == "transition"


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

        for pattern, _should_have_numbers in numeric_patterns:
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

    def test_accepts_explicit_source_present_in_prefetched_context(self):
        output = """
        BP News Analysis - 2026-03-31
        - BP gained 18.27% in March 2026 according to AD HOC NEWS on 2026-03-31.
        - BP remained supported by Brent crude at $109.18 while BP faced de-escalation risk.
        - AD HOC NEWS reported BP portfolio optimization remained in focus on 2026-03-31.
        - BP now trades with elevated event sensitivity and BP mentions remained concentrated in energy coverage.
        """
        context = """
        {
          "feed": [
            {"source": "AD HOC NEWS", "source_domain": "AD HOC NEWS"},
            {"source": "MarketBeat", "source_domain": "MarketBeat"}
          ]
        }
        """

        result = validate_news_analysis_detailed(
            output,
            "BP",
            allowed_source_names=extract_allowed_sources_from_context(context),
        )

        assert result.is_valid, result.reason

    def test_fails_for_internal_prompt_header_cited_as_source(self):
        output = """
        CSTM News Analysis - 2026-04-02
        - According to Macro Regime Classification on 2026-04-02, CSTM should remain cautious.
        - CSTM traded with materials support while CSTM remained sensitive to aluminum pricing.
        - Macro Regime Classification reported mixed breadth and CSTM retained event sensitivity.
        - CSTM valuation stayed in focus and CSTM sentiment remained tied to $109.58 WTI crude.
        """

        result = validate_news_analysis_detailed(output, "CSTM")

        assert not result.is_valid
        assert result.code == "unknown_source"
        assert "Macro Regime Classification" in result.reason

    def test_extract_explicit_sources_ignores_generic_company_phrases(self):
        output = """
        CSTM News Analysis - 2026-04-02
        - The Company reported on 2026-04-02 that CSTM demand improved 8%.
        - The Report noted on 2026-04-02 that CSTM held support near $48.02.
        - Reuters reported on 2026-04-02 that CSTM shipments improved 8%.
        """

        sources = extract_explicit_sources(output)

        assert "The Company" not in sources
        assert "The Report" not in sources
        assert "Reuters" in sources

    def test_generic_company_phrase_does_not_trigger_unknown_source_failure(self):
        output = """
        CSTM News Analysis - 2026-04-02
        - The Company reported on 2026-04-02 that CSTM demand improved 8%.
        - CSTM traded near $48.02 while CSTM sentiment remained tied to materials demand.
        - Reuters reported on 2026-04-02 that CSTM shipments improved 8%.
        - CSTM remained in focus while CSTM coverage stayed active.
        """

        result = validate_news_analysis_detailed(
            output,
            "CSTM",
            allowed_source_names={"Reuters"},
        )

        assert result.is_valid, result.reason

    def test_can_skip_provenance_checks_for_pre_fact_checker_validation(self):
        output = """
        CSTM News Analysis - 2026-04-02
        - According to Macro Regime Classification on 2026-04-02, CSTM held support near $48.02 while CSTM remained active.
        - CSTM traded with materials support and CSTM remained sensitive to aluminum pricing.
        - CSTM valuation stayed in focus while CSTM sentiment remained tied to $109.58 WTI crude.
        """

        result = validate_news_analysis_detailed(
            output,
            "CSTM",
            enforce_provenance=False,
        )

        assert result.is_valid, result.reason

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

    def test_fails_for_scanner_sec_conflation_when_terms_are_far_apart_in_same_bullet(self):
        output = """
        RIG News Analysis - 2026-03-31
        - [Source: Finviz Smart Money Scanner | Scan Date: 2026-03-31] RIG showed insider buying in the smart money scanner,
          with unusually strong volume and follow-through in related flow metrics across the session, while later in the same
          bullet the draft incorrectly labels that scanner evidence as SEC Form 4 confirmation for RIG.
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


class TestProvenanceFiltering:
    def test_filter_news_report_by_provenance_removes_unknown_source_bullets(self):
        output = """
        CSTM News Analysis - 2026-04-02
        - Reuters reported on 2026-04-02 that CSTM demand improved 8%.
        - Scout Money reported on 2026-04-02 that CSTM faced undisclosed pressure.
        - Bloomberg reported on 2026-04-01 that CSTM retained pricing support at $48.02.
        """

        sanitized, removed = filter_news_report_by_provenance(
            output,
            allowed_source_names={"Reuters", "Bloomberg"},
        )

        assert "Scout Money" not in sanitized
        assert len(removed) == 1


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

    def test_extract_allowed_sources_from_context_reads_json_fields(self):
        context = """
        {
          "feed": [
            {"source": "AD HOC NEWS", "source_domain": "AD HOC NEWS"},
            {"source": "24/7 Wall St.", "source_domain": "24/7 Wall St."}
          ]
        }
        """

        allowed = extract_allowed_sources_from_context(context)

        assert "AD HOC NEWS" in allowed
        assert "24/7 Wall St" in allowed

    def test_word_boundary_matching(self):
        """Test ticker matching respects word boundaries."""
        # "TRIGGER" contains "RIG" but shouldn't count as a mention
        output = """
        The TRIGGER for this analysis is RIGID market conditions.
        However, RIG stock specifically faces challenges.
        RIG is mentioned here correctly.
        """

        is_valid, reason = validate_ticker_relevance(
            output, "RIG", min_mentions=2, check_article_refs=False
        )

        # Should only count the 2 standalone "RIG" mentions, not TRIGGER or RIGID
        assert is_valid  # Has exactly 2 valid mentions


class TestStructuredNewsValidation:
    def test_validates_structured_payload(self):
        output = """
        {
          "ticker": "RIG",
          "report_title": "RIG News Analysis",
          "claims": [
            {"claim": "RIG dayrates weakened 4% on 2026-03-31.", "source": "Reuters", "published_at": "2026-03-31", "evidence_id": "art_rig_001"},
            {"claim": "RIG backlog remained under pressure on 2026-03-31.", "source": "Reuters", "published_at": "2026-03-31", "evidence_id": "art_rig_002"},
            {"claim": "RIG put activity increased 12% on 2026-03-31.", "source": "Reuters", "published_at": "2026-03-31", "evidence_id": "art_rig_003"}
          ],
          "summary_table": []
        }
        """

        result = validate_structured_news_payload(output, "RIG")

        assert result.is_valid, result.reason
        assert result.payload["ticker"] == "RIG"

    def test_sanitizes_structured_payload_by_evidence_id(self):
        payload = {
            "ticker": "CSTM",
            "report_title": "CSTM News Analysis",
            "claims": [
                {
                    "claim": "CSTM demand improved 8% on 2026-04-02.",
                    "source": "Reuters",
                    "published_at": "2026-04-02",
                    "evidence_id": "art_reuters_001",
                },
                {
                    "claim": "CSTM faced hidden pressure on 2026-04-02.",
                    "source": "Scout Money",
                    "published_at": "2026-04-02",
                    "evidence_id": "art_fake_001",
                },
            ],
            "summary_table": [],
        }

        class Record:
            evidence_id = "art_reuters_001"
            source = "Reuters"
            published_at = "2026-04-02"

        sanitized, removed = sanitize_structured_news_payload(
            payload,
            ticker="CSTM",
            allowed_source_names={"Reuters"},
            allowed_evidence_ids={"art_reuters_001"},
            evidence_records_by_id={"art_reuters_001": Record()},
        )

        assert len(sanitized["claims"]) == 1
        assert sanitized["claims"][0]["source"] == "Reuters"
        assert removed[0]["reason"] == "unknown_evidence_id"

    def test_renders_structured_payload_to_markdown(self):
        rendered = render_structured_news_payload(
            {
                "ticker": "CSTM",
                "report_title": "CSTM News Analysis",
                "claims": [
                    {
                        "claim": "CSTM demand improved 8% on 2026-04-02.",
                        "source": "Reuters",
                        "published_at": "2026-04-02",
                        "evidence_id": "art_reuters_001",
                    }
                ],
                "summary_table": [],
            },
            "CSTM",
        )

        assert "CSTM News Analysis" in rendered
        assert "[Source: Reuters | Published: 2026-04-02]" in rendered


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


class TestSentimentStructuredContract:
    def test_build_completed(self):
        from tradingagents.agents.utils.output_validation import build_sentiment_report_structured

        structured = build_sentiment_report_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            sentiment_report="- AAPL headline sentiment is BULLISH with +15.5% improvement this week.\n- Coverage intensity: 23 articles from 9 outlets.\n- Reddit posts: positive.",
        )
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "sentiment_summary_v1"
        assert structured["sentiment_direction"] == "bullish"
        assert structured["key_metrics"]["report_char_count"] > 0

    def test_build_empty(self):
        from tradingagents.agents.utils.output_validation import build_sentiment_report_structured

        structured = build_sentiment_report_structured(
            ticker="MSFT",
            as_of_date="2026-04-03",
            sentiment_report="",
        )
        assert structured["status"] == "empty"
        assert structured["ticker"] == "MSFT"

    def test_build_timeout_fallback(self):
        from tradingagents.agents.utils.output_validation import build_sentiment_report_structured

        structured = build_sentiment_report_structured(
            ticker="TSLA",
            as_of_date="2026-04-03",
            sentiment_report="Some partial output",
            is_timeout_fallback=True,
        )
        assert structured["status"] == "timeout_fallback"

    def test_bearish_direction_detected(self):
        from tradingagents.agents.utils.output_validation import build_sentiment_report_structured

        structured = build_sentiment_report_structured(
            ticker="XYZ",
            as_of_date="2026-04-03",
            sentiment_report="- Sentiment is BEARISH. NEGATIVE outlook across forums. PESSIMISTIC coverage.",
        )
        assert structured["sentiment_direction"] == "bearish"


class TestInvestmentPlanStructuredContract:
    def test_build_completed_buy(self):
        from tradingagents.agents.utils.output_validation import build_investment_plan_structured

        structured = build_investment_plan_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            investment_plan="- Strongest Bull Evidence: Revenue +12.4% YoY (HIGH)\n- Recommendation: BUY\n- Rationale: Strong earnings momentum (HIGH)",
        )
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["recommendation"] == "BUY"
        assert structured["key_metrics"]["high_confidence_claims"] >= 2

    def test_build_completed_sell(self):
        from tradingagents.agents.utils.output_validation import build_investment_plan_structured

        structured = build_investment_plan_structured(
            ticker="XYZ",
            as_of_date="2026-04-03",
            investment_plan="- Recommendation: SELL\n- Rationale: Margin contraction -5.0% (MED)",
        )
        assert structured["recommendation"] == "SELL"

    def test_build_empty(self):
        from tradingagents.agents.utils.output_validation import build_investment_plan_structured

        structured = build_investment_plan_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            investment_plan="",
        )
        assert structured["status"] == "empty"

    def test_build_investment_plan_raises_on_ambiguous_input(self):
        """Test that ambiguous non-empty input raises ActionExtractionError."""
        from tradingagents.agents.utils.output_validation import (
            ActionExtractionError,
            build_investment_plan_structured,
        )

        ambiguous = "The committee considered the matter. Bears say caution. Bulls say proceed. Outcome: deferred."
        with pytest.raises(ActionExtractionError) as exc_info:
            build_investment_plan_structured(
                ticker="XYZ",
                as_of_date="2026-05-03",
                investment_plan=ambiguous,
            )
        assert "action_extraction_failed" in str(exc_info.value)


class TestTraderPlanStructuredContract:
    def test_build_completed_with_entry_and_stop(self):
        from tradingagents.agents.utils.output_validation import build_trader_plan_structured

        structured = build_trader_plan_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            trader_plan=(
                "- Research Manager's Verdict: BUY\n"
                "- Entry Setup: $192.50 technical breakout\n"
                "- Risk Parameters: Stop-loss at $183.00, take-profit $210.00\n"
                "- Catalyst Timeline: Earnings 2026-05-01 per scanner\n"
                "- FINAL TRANSACTION PROPOSAL: **BUY**"
            ),
        )
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["final_action"] == "BUY"
        assert structured["key_metrics"]["entry_setup_present"] is True
        assert structured["key_metrics"]["stop_loss_present"] is True
        assert structured["key_metrics"]["take_profit_present"] is True
        assert structured["key_metrics"]["catalyst_dates_present"] is True

    def test_build_empty(self):
        from tradingagents.agents.utils.output_validation import build_trader_plan_structured

        structured = build_trader_plan_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            trader_plan="",
        )
        assert structured["status"] == "empty"
        assert structured["final_action"] == "HOLD"

    def test_build_trader_plan_raises_on_ambiguous_input(self):
        """Test that ambiguous non-empty input raises ActionExtractionError."""
        from tradingagents.agents.utils.output_validation import (
            ActionExtractionError,
            build_trader_plan_structured,
        )

        ambiguous = "The committee saw mixed signals. Technical indicators are unclear. Outcome: uncertain."
        with pytest.raises(ActionExtractionError) as exc_info:
            build_trader_plan_structured(
                ticker="XYZ",
                as_of_date="2026-05-03",
                trader_plan=ambiguous,
            )
        assert "action_extraction_failed" in str(exc_info.value)


class TestRiskSynthesisStructuredContract:
    def test_build_completed(self):
        from tradingagents.agents.utils.output_validation import build_risk_synthesis_structured

        structured = build_risk_synthesis_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            risk_synthesis=(
                "- Key Agreements: All three analysts agree on stop-loss discipline.\n"
                "- Disagreements: Aggressive analyst disagrees with conservative on upside.\n"
                "- Material Risks: volatility risk, downside of -8.5% if support breaks.\n"
                "RECOMMENDATION: BUY with tight risk controls."
            ),
        )
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["consensus_direction"] == "BUY"
        assert structured["key_metrics"]["agreement_mentions"] >= 1
        assert structured["key_metrics"]["risk_mentions"] >= 1

    @pytest.mark.parametrize(
        ("label", "direction"),
        [
            ("BALANCED ASSESSMENT", "BUY"),
            ("Balanced Assessment", "SELL"),
            ("balanced assessment", "HOLD"),
        ],
    )
    def test_balanced_assessment_infers_explicit_direction(self, label, direction):
        from tradingagents.agents.utils.output_validation import build_risk_synthesis_structured

        structured = build_risk_synthesis_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            risk_synthesis=f"{label}: {direction} with explicit risk controls.",
        )

        assert structured["consensus_direction"] == direction

    def test_build_empty(self):
        from tradingagents.agents.utils.output_validation import build_risk_synthesis_structured

        structured = build_risk_synthesis_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            risk_synthesis="",
        )
        assert structured["status"] == "empty"

    def test_build_risk_synthesis_raises_on_ambiguous_input(self):
        """Test that ambiguous non-empty input raises ActionExtractionError."""
        from tradingagents.agents.utils.output_validation import (
            ActionExtractionError,
            build_risk_synthesis_structured,
        )

        ambiguous = "The committee debated extensively. Multiple viewpoints were presented. No consensus reached."
        with pytest.raises(ActionExtractionError) as exc_info:
            build_risk_synthesis_structured(
                ticker="XYZ",
                as_of_date="2026-05-03",
                risk_synthesis=ambiguous,
            )
        assert "action_extraction_failed" in str(exc_info.value)


class TestFinalDecisionStructuredContract:
    def test_build_completed_buy(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        structured = build_final_decision_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            final_decision=(
                "- Action: BUY 200 shares of AAPL at $192.50\n"
                "- Position size: 5% of portfolio\n"
                "- Stop-loss: $183.00\n"
                "- Take-profit: $210.00"
            ),
        )
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["action"] == "BUY"
        assert structured["key_metrics"]["stop_loss_present"] is True
        assert structured["key_metrics"]["take_profit_present"] is True
        assert structured["key_metrics"]["position_size_present"] is True
        assert len(structured["decision_excerpt"]) > 0

    def test_build_empty(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        structured = build_final_decision_structured(
            ticker="AAPL",
            as_of_date="2026-04-03",
            final_decision="",
        )
        assert structured["status"] == "empty"
        assert structured["action"] == "HOLD"

    def test_build_final_decision_raises_on_ambiguous_input(self):
        """Test that ambiguous non-empty input raises ActionExtractionError."""
        from tradingagents.agents.utils.output_validation import (
            ActionExtractionError,
            build_final_decision_structured,
        )

        ambiguous = "The portfolio manager reviewed all data. Various factors were considered. Decision pending further analysis."
        with pytest.raises(ActionExtractionError) as exc_info:
            build_final_decision_structured(
                ticker="XYZ",
                as_of_date="2026-05-03",
                final_decision=ambiguous,
            )
        assert "action_extraction_failed" in str(exc_info.value)

    def test_decision_excerpt_truncated(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        long_text = "ACTION: BUY\n" + "A" * 500
        structured = build_final_decision_structured(
            ticker="XYZ",
            as_of_date="2026-04-03",
            final_decision=long_text,
        )
        assert len(structured["decision_excerpt"]) <= 200

    def test_build_final_decision_structured_does_not_treat_selloff_as_sell(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        report = (
            "RIG experienced an energy selloff, but the final rating is Buy. "
            "Rating: Buy. Stop-loss at $3.80. Target price at $6.00."
        )

        structured = build_final_decision_structured(
            ticker="RIG",
            as_of_date="2026-04-28",
            final_decision=report,
        )

        assert structured["action"] == "BUY"

    def test_build_final_decision_structured_prefers_final_transaction_proposal(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        report = (
            "The bear case says sell if dayrates weaken. "
            "FINAL TRANSACTION PROPOSAL: **HOLD** until earnings confirm guidance."
        )

        structured = build_final_decision_structured(
            ticker="RIG",
            as_of_date="2026-04-28",
            final_decision=report,
        )

        assert structured["action"] == "HOLD"

    def test_build_final_decision_structured_uses_word_boundaries(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        report = "The company completed a buyback. Rating: Hold."

        structured = build_final_decision_structured(
            ticker="AAPL",
            as_of_date="2026-04-28",
            final_decision=report,
        )

        assert structured["action"] == "HOLD"


class TestNewsStructuredContract:
    """Test suite for build_news_report_structured canonical normalizer."""

    def test_build_news_report_structured_completed(self):
        """Test completed status with verified claims."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        payload = {
            "ticker": "MRVL",
            "report_title": "MRVL News Analysis",
            "claims": [
                {
                    "claim": "Marvell received upgrade from Barclays",
                    "source": "Barron's",
                    "published_at": "2026-04-09",
                    "evidence_id": "art_123",
                },
                {
                    "claim": "MRVL announces new AI chip",
                    "source": "Reuters",
                    "published_at": "2026-04-10",
                    "evidence_id": "art_456",
                },
            ],
            "summary_table": [],
        }

        result = build_news_report_structured(
            ticker="MRVL",
            as_of_date="2026-04-10",
            payload=payload,
            status="completed",
        )

        assert result["status"] == "completed"
        assert result["contract_version"] == "news_report_v1"
        assert result["key_metrics"]["claim_count"] == 2
        assert result["key_metrics"]["evidence_ids"] == 2
        assert result["key_metrics"]["removed_claims"] == 0

    def test_build_news_report_structured_empty(self):
        """Test empty status with no claims."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        result = build_news_report_structured(
            ticker="LWLG",
            as_of_date="2026-04-10",
            payload={"ticker": "LWLG", "claims": [], "summary_table": []},
            status="empty",
        )

        assert result["status"] == "empty"
        assert result["contract_version"] == "news_report_v1"
        assert result["key_metrics"]["claim_count"] == 0

    def test_build_news_report_structured_strips_null_scan_date(self):
        """Test that scan_date is stripped from non-scanner claims."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        payload = {
            "claims": [
                {
                    "claim": "Article claim",
                    "source": "Reuters",
                    "published_at": "2026-04-10",
                    "evidence_id": "art_123",
                    "scan_date": None,  # Should be stripped
                },
            ],
            "summary_table": [],
        }

        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload=payload,
            status="completed",
        )

        assert "scan_date" not in result["claims"][0]
        assert result["claims"][0]["evidence_id"] == "art_123"

    def test_build_news_report_structured_retains_scanner_scan_date(self):
        """Test that scan_date is retained for scanner claims."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        payload = {
            "claims": [
                {
                    "claim": "Smart money detected unusual activity",
                    "source": "Finviz Smart Money Scanner",
                    "scan_date": "2026-04-10",
                    "published_at": "",
                    "evidence_id": "",
                },
            ],
            "summary_table": [],
        }

        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload=payload,
            status="completed",
        )

        assert result["claims"][0]["scan_date"] == "2026-04-10"
        assert (
            "evidence_id" not in result["claims"][0] or result["claims"][0].get("evidence_id") == ""
        )

    def test_build_news_report_structured_computes_key_metrics(self):
        """Test key_metrics computation."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        removed = [{"claim": "Rejected claim"}]
        payload = {
            "claims": [
                {
                    "claim": "C1",
                    "source": "S1",
                    "published_at": "2026-04-10",
                    "evidence_id": "art_1",
                },
                {
                    "claim": "C2",
                    "source": "S2",
                    "published_at": "2026-04-10",
                    "evidence_id": "art_2",
                },
                {
                    "claim": "C3",
                    "source": "S3",
                    "published_at": "2026-04-10",
                    "evidence_id": "art_1",
                },  # Duplicate evidence_id
            ],
            "summary_table": [
                {
                    "date": "2026-04-10",
                    "event": "E1",
                    "metric": "M",
                    "value": "V",
                    "source": "S1",
                    "evidence_id": "art_1",
                },
                {
                    "date": "2026-04-10",
                    "event": "E2",
                    "metric": "M",
                    "value": "V",
                    "source": "S2",
                    "evidence_id": "art_2",
                },
            ],
            "below_min_claims": True,
        }

        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload=payload,
            status="completed",
            removed_claims=removed,
        )

        assert result["key_metrics"]["claim_count"] == 3
        assert result["key_metrics"]["summary_rows"] == 2
        assert result["key_metrics"]["evidence_ids"] == 2  # Unique count
        assert result["key_metrics"]["removed_claims"] == 1
        assert result["key_metrics"]["below_min_claims"] is True

    def test_build_news_report_structured_survives_malformed_payload(self):
        """Test defensive behavior with malformed payload."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        # Malformed claim entry (not a dict) - should fail
        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload={"claims": ["not a dict"], "summary_table": []},
            status="completed",
        )
        assert result["status"] == "invalid_structured_payload"
        assert "Malformed claim entry" in result["abort_reason"]

        # Malformed summary_table entry (not a dict) - should fail
        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload={"claims": [], "summary_table": ["not a dict"]},
            status="completed",
        )
        assert result["status"] == "invalid_structured_payload"
        assert "Malformed summary_table entry" in result["abort_reason"]

        # None payload with completed status - converts to {} and returns completed with 0 claims
        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload=None,
            status="completed",
        )
        assert result["contract_version"] == "news_report_v1"
        assert result["status"] == "completed"
        assert result["key_metrics"]["claim_count"] == 0

    def test_build_news_report_structured_rejects_unknown_status(self):
        """Test that non-canonical status is rejected."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload={"claims": [], "summary_table": []},
            status="timeout_fallback",  # Non-canonical for news
        )

        assert result["status"] == "invalid_structured_payload"
        assert "Non-canonical status" in result["abort_reason"]

    def test_build_news_report_structured_requires_article_evidence_id(self):
        """Test that non-scanner claims must have evidence_id."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        payload = {
            "claims": [
                {
                    "claim": "Article without evidence ID",
                    "source": "Reuters",
                    "published_at": "2026-04-10",
                    "evidence_id": "",  # Missing!
                },
            ],
            "summary_table": [],
        }

        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload=payload,
            status="completed",
        )

        assert result["status"] == "invalid_structured_payload"
        assert "evidence_id" in result["abort_reason"]

    def test_build_news_report_structured_omits_blank_scanner_optional_fields(self):
        """Test that blank optional scanner fields are omitted."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        payload = {
            "claims": [
                {
                    "claim": "Scanner claim",
                    "source": "Finviz Smart Money Scanner",
                    "scan_date": "2026-04-10",
                    "published_at": "",  # Blank optional
                    "evidence_id": "",  # Blank optional
                },
            ],
            "summary_table": [],
        }

        result = build_news_report_structured(
            ticker="TEST",
            as_of_date="2026-04-10",
            payload=payload,
            status="completed",
        )

        claim = result["claims"][0]
        assert claim["scan_date"] == "2026-04-10"
        # Blank optional fields should be omitted, not included as empty strings
        assert "published_at" not in claim or claim.get("published_at") == ""
        assert "evidence_id" not in claim or claim.get("evidence_id") == ""

    def test_regression_news_status_never_null(self):
        """Regression test: news_report_structured.status must never be null."""
        from tradingagents.agents.utils.output_validation import build_news_report_structured

        # Test all canonical statuses
        for status in [
            "completed",
            "empty",
            "invalid_structured_payload",
            "missing_structured_payload",
            "aborted",
        ]:
            result = build_news_report_structured(
                ticker="TEST",
                as_of_date="2026-04-10",
                payload={},
                status=status,
            )
            assert result["status"] in {
                "completed",
                "empty",
                "invalid_structured_payload",
                "missing_structured_payload",
                "aborted",
            }
            assert result["contract_version"] == "news_report_v1"
            assert isinstance(result["key_metrics"], dict)
            assert isinstance(result["key_metrics"]["claim_count"], int)
