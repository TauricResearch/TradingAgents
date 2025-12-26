"""
Shared pytest fixtures for TradingAgents test suite.

This module provides root-level fixtures accessible to all test directories:
- Environment variable mocking (OpenRouter, OpenAI, Anthropic, Google)
- LangChain class mocking
- ChromaDB mocking
- Memory mocking
- OpenAI client mocking
- Temporary directories
- Configuration fixtures

Fixtures are organized by scope:
- function: Default scope, creates new instance per test
- session: Created once per test session (expensive operations)
- module: Created once per test module

See Also:
    tests/unit/conftest.py - Unit-specific fixtures
    tests/integration/conftest.py - Integration-specific fixtures
"""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from tradingagents.default_config import DEFAULT_CONFIG

# Register plugins from sub-conftest files (pytest 9.0+ requires this at root level)
pytest_plugins = ["tests.api.conftest"]


# ============================================================================
# Environment Variable Fixtures
# ============================================================================

@pytest.fixture
def mock_env_openrouter():
    """
    Mock environment with OPENROUTER_API_KEY set.

    Clears all other API keys to ensure isolation.
    Restores original environment after test.

    Scope: function (default)

    Yields:
        None - Environment is modified in-place via patch.dict

    Example:
        def test_openrouter(mock_env_openrouter):
            assert os.getenv("OPENROUTER_API_KEY") == "sk-or-test-key-123"
    """
    with patch.dict(os.environ, {
        "OPENROUTER_API_KEY": "sk-or-test-key-123",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_openai():
    """
    Mock environment with OPENAI_API_KEY set.

    Clears all other API keys to ensure isolation.
    Restores original environment after test.

    Scope: function (default)

    Yields:
        None - Environment is modified in-place via patch.dict

    Example:
        def test_openai(mock_env_openai):
            assert os.getenv("OPENAI_API_KEY") == "sk-test-key-456"
    """
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "sk-test-key-456",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_anthropic():
    """
    Mock environment with ANTHROPIC_API_KEY set.

    Clears all other API keys to ensure isolation.
    Restores original environment after test.

    Scope: function (default)

    Yields:
        None - Environment is modified in-place via patch.dict

    Example:
        def test_anthropic(mock_env_anthropic):
            assert os.getenv("ANTHROPIC_API_KEY") == "sk-ant-test-key-789"
    """
    with patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "sk-ant-test-key-789",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_google():
    """
    Mock environment with GOOGLE_API_KEY set.

    Clears all other API keys to ensure isolation.
    Restores original environment after test.

    Scope: function (default)

    Yields:
        None - Environment is modified in-place via patch.dict

    Example:
        def test_google(mock_env_google):
            assert os.getenv("GOOGLE_API_KEY") == "AIza-test-key-abc"
    """
    with patch.dict(os.environ, {
        "GOOGLE_API_KEY": "AIza-test-key-abc",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_empty():
    """
    Mock environment with all API keys cleared.

    Useful for testing error handling when API keys are missing.
    Restores original environment after test.

    Scope: function (default)

    Yields:
        None - Environment is modified in-place via patch.dict

    Example:
        def test_no_api_keys(mock_env_empty):
            assert os.getenv("OPENAI_API_KEY") is None
            assert os.getenv("OPENROUTER_API_KEY") is None
    """
    with patch.dict(os.environ, {}, clear=True):
        yield


# ============================================================================
# LangChain Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_langchain_classes():
    """
    Mock LangChain chat model classes (ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI).

    Provides mocked instances that avoid actual API calls during testing.
    All mocks return Mock instances when instantiated.

    Scope: function (default)

    Yields:
        dict: Dictionary containing mocked classes:
            - "openai": Mock for ChatOpenAI
            - "anthropic": Mock for ChatAnthropic
            - "google": Mock for ChatGoogleGenerativeAI

    Example:
        def test_llm_init(mock_langchain_classes):
            mocks = mock_langchain_classes
            assert mocks["openai"].called
    """
    with patch("tradingagents.graph.trading_graph.ChatOpenAI") as mock_openai, \
         patch("tradingagents.graph.trading_graph.ChatAnthropic") as mock_anthropic, \
         patch("tradingagents.graph.trading_graph.ChatGoogleGenerativeAI") as mock_google:

        # Configure mocks to return Mock instances
        mock_openai.return_value = Mock()
        mock_anthropic.return_value = Mock()
        mock_google.return_value = Mock()

        yield {
            "openai": mock_openai,
            "anthropic": mock_anthropic,
            "google": mock_google,
        }


# ============================================================================
# ChromaDB Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_chromadb():
    """
    Mock ChromaDB client to avoid actual database operations.

    Provides a mocked client with:
    - get_or_create_collection() method (new API)
    - create_collection() method (legacy API)
    - Collection with count() returning 0

    Scope: function (default)

    Yields:
        Mock: Mocked ChromaDB Client class

    Example:
        def test_chromadb_init(mock_chromadb):
            from tradingagents.agents.utils.memory import chromadb
            client = chromadb.Client()
            collection = client.get_or_create_collection("test")
            assert collection.count() == 0
    """
    with patch("tradingagents.agents.utils.memory.chromadb.Client") as mock:
        client_instance = Mock()
        collection_instance = Mock()
        collection_instance.count.return_value = 0

        # Mock both create_collection (old) and get_or_create_collection (new)
        client_instance.create_collection.return_value = collection_instance
        client_instance.get_or_create_collection.return_value = collection_instance

        mock.return_value = client_instance
        yield mock


# ============================================================================
# Memory Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_memory():
    """
    Mock FinancialSituationMemory to avoid ChromaDB/OpenAI calls.

    Provides a mocked memory instance that avoids actual database
    and API operations during testing.

    Scope: function (default)

    Yields:
        Mock: Mocked FinancialSituationMemory class

    Example:
        def test_memory_usage(mock_memory):
            memory = mock_memory.return_value
            assert memory is not None
    """
    with patch("tradingagents.graph.trading_graph.FinancialSituationMemory") as mock:
        from tradingagents.agents.utils.memory import FinancialSituationMemory
        mock.return_value = Mock(spec=FinancialSituationMemory)
        yield mock


# ============================================================================
# OpenAI Client Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_openai_client():
    """
    Mock OpenAI client for embedding tests.

    Provides a mocked OpenAI client with:
    - embeddings.create() method returning mock embeddings (1536-dimensional)

    Scope: function (default)

    Yields:
        Mock: Mocked OpenAI class

    Example:
        def test_embeddings(mock_openai_client):
            from openai import OpenAI
            client = OpenAI()
            response = client.embeddings.create(input="test", model="text-embedding-ada-002")
            assert len(response.data[0].embedding) == 1536
    """
    with patch("tradingagents.agents.utils.memory.OpenAI") as mock:
        client_instance = Mock()
        mock.return_value = client_instance

        # Mock embedding response
        embedding_response = Mock()
        embedding_response.data = [Mock(embedding=[0.1] * 1536)]
        client_instance.embeddings.create.return_value = embedding_response

        yield mock


# ============================================================================
# Temporary Directory Fixtures
# ============================================================================

@pytest.fixture
def temp_output_dir(tmp_path):
    """
    Create a temporary output directory for test artifacts.

    Automatically cleaned up after test completes.

    Scope: function (default)

    Args:
        tmp_path: pytest's built-in temporary directory fixture

    Yields:
        Path: Path to temporary output directory

    Example:
        def test_file_output(temp_output_dir):
            output_file = temp_output_dir / "result.txt"
            output_file.write_text("test")
            assert output_file.exists()
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    yield output_dir
    # Cleanup is automatic via tmp_path


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def sample_config():
    """
    Create a sample configuration with default settings.

    Provides a complete configuration dict based on DEFAULT_CONFIG
    suitable for testing basic functionality.

    Scope: function (default)

    Returns:
        dict: Configuration dictionary with required keys:
            - llm_provider
            - deep_think_llm
            - quick_think_llm
            - data_vendors
            - backend_url

    Example:
        def test_config_loading(sample_config):
            assert sample_config["llm_provider"] == "openai"
            assert "data_vendors" in sample_config
    """
    config = DEFAULT_CONFIG.copy()
    return config


@pytest.fixture
def openrouter_config():
    """
    Create an OpenRouter-specific configuration.

    Provides a configuration dict set up for OpenRouter provider
    with appropriate model names and backend URL.

    Scope: function (default)

    Returns:
        dict: Configuration dictionary with OpenRouter settings:
            - llm_provider: "openrouter"
            - deep_think_llm: "anthropic/claude-sonnet-4"
            - quick_think_llm: "anthropic/claude-haiku-3.5"
            - backend_url: "https://openrouter.ai/api/v1"

    Example:
        def test_openrouter_setup(openrouter_config):
            assert openrouter_config["llm_provider"] == "openrouter"
            assert "openrouter.ai" in openrouter_config["backend_url"]
    """
    config = DEFAULT_CONFIG.copy()
    config.update({
        "llm_provider": "openrouter",
        "deep_think_llm": "anthropic/claude-sonnet-4",
        "quick_think_llm": "anthropic/claude-haiku-3.5",
        "backend_url": "https://openrouter.ai/api/v1",
    })
    return config


# ============================================================================
# Agent Output Validation Fixtures (Issue #53)
# ============================================================================

@pytest.fixture
def sample_agent_state():
    """
    Create a complete sample agent state for testing.

    Provides a fully populated agent state with all required fields
    including reports, debate states, and final decision.

    Scope: function (default)

    Returns:
        dict: Complete agent state with all fields populated

    Example:
        def test_complete_state(sample_agent_state):
            assert sample_agent_state["company_of_interest"] == "AAPL"
            assert "market_report" in sample_agent_state
    """
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2024-01-15",
        "market_report": """
# Market Analysis for AAPL

## Technical Indicators
Strong bullish momentum with RSI at 55 and MACD showing positive divergence.
Price has broken through key resistance at $175.

## Volume Analysis
Above-average volume on recent upward moves indicates strong buyer interest.
Institutional accumulation pattern observed over the past 2 weeks.

## Price Action
Clear higher highs and higher lows pattern establishing uptrend.
Support level established at $170 with strong buying pressure.
        """ + "Additional detailed analysis. " * 30,
        "sentiment_report": """
# Social Media Sentiment Analysis

## Overall Sentiment
Strongly positive sentiment across major platforms (Twitter, Reddit, StockTwits).
Sentiment score: 8.5/10 based on 10,000+ analyzed posts.

## Key Themes
- New product launch excitement
- Strong quarterly earnings anticipation
- Innovation leadership recognition

## Influencer Activity
Major tech influencers bullish on near-term prospects.
        """ + "More sentiment details. " * 30,
        "news_report": """
# News Analysis

## Recent Headlines
- Major product announcement driving positive coverage
- Analyst upgrades from 3 top firms this week
- Partnership announcements in AI space

## Coverage Tone
85% positive, 10% neutral, 5% negative across 50 major news sources.

## Impact Assessment
News flow strongly supportive of bullish thesis.
        """ + "Additional news analysis. " * 30,
        "fundamentals_report": """
# Fundamental Analysis

## Financial Metrics
| Metric | Value | Industry Avg |
|--------|-------|--------------|
| P/E    | 28    | 25           |
| ROE    | 45%   | 20%          |
| Revenue Growth | 12% | 8%     |

## Balance Sheet
Strong cash position of $150B, low debt-to-equity ratio.

## Earnings Quality
Consistent earnings growth with strong margins.
        """ + "Detailed fundamental analysis. " * 30,
        "investment_debate_state": {
            "history": "Round 1: Bull presents case for strong buy...\nRound 2: Bear raises concerns about valuation...\nRound 3: Bull counters with growth prospects...",
            "count": 3,
            "judge_decision": "BUY: Bulls made a compelling case with strong fundamentals and positive momentum",
            "bull_history": "Strong fundamentals, positive momentum, innovation leadership",
            "bear_history": "Slight valuation concerns, market volatility risk",
            "current_response": "Final recommendation is BUY",
        },
        "risk_debate_state": {
            "history": "Round 1: Risk assessment begins...\nRound 2: Conservative view presented...",
            "count": 2,
            "judge_decision": "BUY: Risk is acceptable given strong fundamentals",
            "risky_history": "High potential upside justifies position",
            "safe_history": "Proceed with caution, good fundamentals",
            "neutral_history": "Balanced risk-reward at current levels",
            "latest_speaker": "neutral",
            "current_risky_response": "Strong buy",
            "current_safe_response": "Moderate buy",
            "current_neutral_response": "Buy with standard position sizing",
        },
        "final_trade_decision": "BUY: Strong consensus across all analysis teams. Fundamentals solid, technicals bullish, sentiment positive. Entry at current levels recommended with standard position sizing.",
        "investment_plan": "Initiate position with 2% portfolio allocation",
        "trader_investment_plan": "Execute market order for calculated position size",
        "sender": "trader",
    }


@pytest.fixture
def sample_agent_state_buy(sample_agent_state):
    """
    Sample agent state with BUY decision.

    Returns complete state configured for BUY scenario.

    Scope: function (default)

    Example:
        def test_buy_scenario(sample_agent_state_buy):
            assert "BUY" in sample_agent_state_buy["final_trade_decision"]
    """
    return sample_agent_state


@pytest.fixture
def sample_agent_state_sell():
    """
    Sample agent state with SELL decision.

    Provides a complete state where all analyses point to SELL.

    Scope: function (default)

    Returns:
        dict: Agent state with SELL decision

    Example:
        def test_sell_scenario(sample_agent_state_sell):
            assert "SELL" in sample_agent_state_sell["final_trade_decision"]
    """
    return {
        "company_of_interest": "TSLA",
        "trade_date": "2024-01-20",
        "market_report": "# Market Analysis\n\nBearish technical pattern with breakdown below support. " + "Detailed analysis. " * 50,
        "sentiment_report": "# Sentiment Analysis\n\nNegative sentiment prevailing across platforms. " + "More details. " * 50,
        "news_report": "# News Report\n\nMultiple negative headlines and analyst downgrades. " + "Additional coverage. " * 50,
        "fundamentals_report": "# Fundamentals\n\nDeteriorating metrics and earnings concerns. " + "Financial details. " * 50,
        "investment_debate_state": {
            "history": "Round 1: Bear presents strong sell case...\nRound 2: Bull unable to counter effectively...",
            "count": 2,
            "judge_decision": "SELL: Bears made compelling case with fundamental concerns",
            "bull_history": "Limited upside potential",
            "bear_history": "Strong downside risk, overvalued",
        },
        "risk_debate_state": {
            "history": "Round 1: Risk analysis shows high downside...",
            "count": 1,
            "judge_decision": "SELL: Exit position to preserve capital",
            "risky_history": "Too risky, exit recommended",
            "safe_history": "Definitely sell",
            "neutral_history": "Sell is prudent",
        },
        "final_trade_decision": "SELL: Consensus to exit position. Fundamentals weak, technicals bearish, sentiment negative.",
    }


@pytest.fixture
def sample_agent_state_hold():
    """
    Sample agent state with HOLD decision.

    Provides a complete state where analyses are mixed, leading to HOLD.

    Scope: function (default)

    Returns:
        dict: Agent state with HOLD decision

    Example:
        def test_hold_scenario(sample_agent_state_hold):
            assert "HOLD" in sample_agent_state_hold["final_trade_decision"]
    """
    return {
        "company_of_interest": "GOOGL",
        "trade_date": "2024-01-22",
        "market_report": "# Market Analysis\n\nMixed signals with consolidation pattern. " + "Technical details. " * 50,
        "sentiment_report": "# Sentiment Analysis\n\nNeutral sentiment, market awaiting catalyst. " + "Sentiment data. " * 50,
        "news_report": "# News Report\n\nBalanced news flow, no major catalysts. " + "News details. " * 50,
        "fundamentals_report": "# Fundamentals\n\nSolid but not compelling, fairly valued. " + "Financial data. " * 50,
        "investment_debate_state": {
            "history": "Round 1: Bull and Bear present balanced views...\nRound 2: No clear winner...\nRound 3: Continued debate...",
            "count": 3,
            "judge_decision": "HOLD: Insufficient conviction either way, maintain position",
            "bull_history": "Some positives but not strong",
            "bear_history": "Some concerns but not severe",
        },
        "risk_debate_state": {
            "history": "Round 1: Risk assessment shows balanced profile...",
            "count": 1,
            "judge_decision": "HOLD: Risk-reward balanced, no action needed",
            "risky_history": "Could go either way",
            "safe_history": "Wait for clarity",
            "neutral_history": "Hold is appropriate",
        },
        "final_trade_decision": "HOLD: Mixed signals across analysis teams. Await further clarity before making move.",
    }


@pytest.fixture
def sample_invest_debate():
    """
    Sample investment debate state.

    Provides a complete investment debate state for isolated testing.

    Scope: function (default)

    Returns:
        dict: Investment debate state (InvestDebateState)

    Example:
        def test_debate(sample_invest_debate):
            assert sample_invest_debate["count"] > 0
    """
    return {
        "history": "Round 1: Bull argues for strong buy based on fundamentals...\nRound 2: Bear raises valuation concerns...\nRound 3: Bull counters with growth prospects...",
        "count": 3,
        "judge_decision": "BUY: Bulls presented stronger evidence",
        "bull_history": "Strong fundamentals, positive technicals, good sentiment",
        "bear_history": "Valuation slightly stretched, some market risk",
        "current_response": "Recommend BUY with conviction",
    }


@pytest.fixture
def sample_risk_debate():
    """
    Sample risk debate state.

    Provides a complete risk debate state for isolated testing.

    Scope: function (default)

    Returns:
        dict: Risk debate state (RiskDebateState)

    Example:
        def test_risk_debate(sample_risk_debate):
            assert sample_risk_debate["count"] > 0
    """
    return {
        "history": "Round 1: Risk analysts evaluate position sizing...\nRound 2: Discussion on risk parameters...",
        "count": 2,
        "judge_decision": "BUY: Risk acceptable with standard position size",
        "risky_history": "Aggressive position justified by strong signals",
        "safe_history": "Conservative position appropriate given uncertainty",
        "neutral_history": "Standard position sizing recommended",
        "latest_speaker": "neutral",
        "current_risky_response": "Take larger position",
        "current_safe_response": "Take smaller position",
        "current_neutral_response": "Standard position is balanced",
    }
