"""Pytest configuration and shared fixtures for TradingAgents tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_llm():
    """Mock LLM for testing without API calls."""
    return MagicMock()


@pytest.fixture
def sample_agent_state():
    """Sample agent state for testing.

    Returns:
        Dictionary with AgentState fields for use in tests.
    """
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2024-01-15",
        "messages": [],
        "sender": "",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "investment_plan": "",
        "trader_investment_plan": "",
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "final_trade_decision": "",
    }


@pytest.fixture
def sample_market_data():
    """Sample market data for testing.

    Returns:
        Dictionary with OHLCV market data for use in tests.
    """
    return {
        "ticker": "AAPL",
        "date": "2024-01-15",
        "open": 185.0,
        "high": 187.5,
        "low": 184.2,
        "close": 186.5,
        "volume": 50000000,
    }


@pytest.fixture
def sample_config():
    """Sample configuration for testing.

    Returns:
        Dictionary with default config values for use in tests.
    """
    return {
        "project_dir": "/tmp/tradingagents",
        "results_dir": "/tmp/results",
        "data_cache_dir": "/tmp/data_cache",
        "llm_provider": "openai",
        "deep_think_llm": "gpt-4o",
        "quick_think_llm": "gpt-4o-mini",
        "backend_url": "https://api.openai.com/v1",
        "google_thinking_level": None,
        "openai_reasoning_effort": None,
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "max_recur_limit": 100,
        "data_vendors": {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        },
        "tool_vendors": {},
    }


@pytest.fixture
def sample_situations():
    """Sample financial situations for memory testing.

    Returns:
        List of (situation, recommendation) tuples.
    """
    return [
        (
            "High volatility in tech sector with increasing institutional selling",
            "Reduce exposure to high-growth tech stocks. Consider defensive positions.",
        ),
        (
            "Strong earnings report beating expectations with raised guidance",
            "Consider buying on any pullbacks. Monitor for momentum continuation.",
        ),
        (
            "Rising interest rates affecting growth stock valuations",
            "Review duration of fixed-income positions. Consider value stocks.",
        ),
        (
            "Market showing signs of sector rotation with rising yields",
            "Rebalance portfolio to maintain target allocations.",
        ),
    ]
