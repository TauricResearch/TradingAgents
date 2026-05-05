"""Regression tests for social media analyst sentiment report completeness."""

import inspect
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage


def test_sentiment_report_is_non_empty_when_llm_returns_blank():
    """Social analyst must never return an empty sentiment_report."""
    from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst

    mock_llm = MagicMock()

    with patch("tradingagents.agents.analysts.social_media_analyst.invoke_with_timeout") as mock_invoke:
        mock_invoke.return_value = (AIMessage(content=""), None)

        with patch("tradingagents.agents.analysts.social_media_analyst.build_sentiment_report_structured") as mock_struct:
            mock_struct.return_value = {}

            with patch("tradingagents.agents.analysts.social_media_analyst.prefetch_tools_parallel") as mock_prefetch:
                mock_prefetch.return_value = {}

                with patch("tradingagents.agents.analysts.social_media_analyst.format_prefetched_context") as mock_format:
                    mock_format.return_value = ""

                    with patch("tradingagents.agents.analysts.social_media_analyst.build_instrument_context") as mock_instrument:
                        mock_instrument.return_value = "Test instrument context"

                        with patch("tradingagents.agents.analysts.social_media_analyst.build_scanner_context_block") as mock_scanner:
                            mock_scanner.return_value = "Test scanner context"

                            node = create_social_media_analyst(mock_llm)
                            state = {
                                "company_of_interest": "AAPL",
                                "trade_date": "2026-05-05",
                                "messages": [],
                                "market_report": "",
                                "sentiment_report": "",
                                "news_report": "",
                                "fundamentals_report": "",
                                "scanner_graph_context_text": "",
                                "macro_regime_report": "",
                            }
                            result = node(state)
                            
                            # Verify sentiment_report is non-empty
                            assert result["sentiment_report"], "sentiment_report must be non-empty"
                            assert len(result["sentiment_report"].strip()) > 10, "sentiment_report must have meaningful content"
                            
                            # Verify fallback contains required elements
                            report = result["sentiment_report"]
                            assert "AAPL" in report, "Report should contain the ticker"
                            assert "Sentiment" in report or "sentiment" in report.lower(), "Report should reference sentiment"
                            assert "neutral" in report or "Directional bias" in report, "Report should state directional bias"
                            assert "confidence" in report.lower(), "Report should mention confidence level"


def test_social_analyst_prompt_mandates_sentiment_direction_format():
    """Social analyst prompt must mandate 'Sentiment direction: BULLISH|BEARISH|NEUTRAL'."""
    import tradingagents.agents.analysts.social_media_analyst as module

    src = inspect.getsource(module)
    assert "REQUIRED SENTIMENT FORMAT" in src
    assert "Sentiment direction: BULLISH" in src
    assert "Sentiment direction: BEARISH" in src
    assert "Sentiment direction: NEUTRAL" in src
