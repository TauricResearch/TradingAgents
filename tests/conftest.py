"""Pytest configuration and shared fixtures for TradingAgents tests."""

import os
import tempfile
from unittest.mock import Mock

import pytest

from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def sample_config():
    """Provide a test configuration."""
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "online_tools": False,  # Use offline tools for testing
            "max_debate_rounds": 1,  # Limit rounds for faster tests
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4o-mini",
            "quick_think_llm": "gpt-4o-mini",
            "project_dir": "/tmp/test_tradingagents",
        },
    )
    return config


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    mock = Mock()
    mock.model_name = "test-model"
    mock.invoke.return_value = Mock(content="Test response")
    mock.bind_tools.return_value = mock
    return mock


@pytest.fixture
def sample_ticker():
    """Sample stock ticker for testing."""
    return "AAPL"


@pytest.fixture
def sample_trade_date():
    """Sample trade date for testing."""
    return "2024-05-10"


@pytest.fixture
def sample_agent_state():
    """Sample agent state for testing."""
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2024-05-10",
        "messages": [],
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": [],
            "bear_history": [],
            "history": [],
            "current_response": "",
            "judge_decision": "",
        },
        "trader_investment_plan": "",
        "risk_debate_state": {
            "risky_history": [],
            "safe_history": [],
            "neutral_history": [],
            "history": [],
            "judge_decision": "",
        },
        "investment_plan": "",
        "final_trade_decision": "",
    }


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_toolkit():
    """Mock toolkit with all necessary methods."""
    toolkit = Mock()
    toolkit.config = {"online_tools": False}

    # Create mock functions with proper __name__ attributes
    def mock_get_YFin_data():
        return "Mock YFin data"

    def mock_get_YFin_data_online():
        return "Mock YFin data online"

    def mock_get_stockstats_indicators_report():
        return "Mock stockstats report"

    def mock_get_stockstats_indicators_report_online():
        return "Mock stockstats report online"

    def mock_get_reddit_stock_info():
        return "Mock reddit stock info"

    def mock_get_stock_news_openai():
        return "Mock stock news"

    def mock_get_finnhub_news():
        return "Mock finnhub news"

    def mock_get_reddit_news():
        return "Mock reddit news"

    def mock_get_global_news_openai():
        return "Mock global news"

    def mock_get_google_news():
        return "Mock google news"

    def mock_get_fundamentals_openai():
        return "Mock fundamentals"

    def mock_get_finnhub_company_insider_sentiment():
        return "Mock insider sentiment"

    def mock_get_finnhub_company_insider_transactions():
        return "Mock insider transactions"

    def mock_get_simfin_balance_sheet():
        return "Mock balance sheet"

    def mock_get_simfin_cashflow():
        return "Mock cashflow"

    def mock_get_simfin_income_stmt():
        return "Mock income statement"

    # Assign the mock functions to the toolkit
    toolkit.get_YFin_data = Mock(side_effect=mock_get_YFin_data)
    toolkit.get_YFin_data.name = "get_YFin_data"
    toolkit.get_YFin_data.__name__ = "get_YFin_data"

    toolkit.get_YFin_data_online = Mock(side_effect=mock_get_YFin_data_online)
    toolkit.get_YFin_data_online.name = "get_YFin_data_online"
    toolkit.get_YFin_data_online.__name__ = "get_YFin_data_online"

    toolkit.get_stockstats_indicators_report = Mock(
        side_effect=mock_get_stockstats_indicators_report
    )
    toolkit.get_stockstats_indicators_report.name = "get_stockstats_indicators_report"
    toolkit.get_stockstats_indicators_report.__name__ = "get_stockstats_indicators_report"

    toolkit.get_stockstats_indicators_report_online = Mock(
        side_effect=mock_get_stockstats_indicators_report_online
    )
    toolkit.get_stockstats_indicators_report_online.name = (
        "get_stockstats_indicators_report_online"
    )
    toolkit.get_stockstats_indicators_report_online.__name__ = (
        "get_stockstats_indicators_report_online"
    )

    toolkit.get_reddit_stock_info = Mock(side_effect=mock_get_reddit_stock_info)
    toolkit.get_reddit_stock_info.name = "get_reddit_stock_info"
    toolkit.get_reddit_stock_info.__name__ = "get_reddit_stock_info"

    toolkit.get_stock_news_openai = Mock(side_effect=mock_get_stock_news_openai)
    toolkit.get_stock_news_openai.name = "get_stock_news_openai"
    toolkit.get_stock_news_openai.__name__ = "get_stock_news_openai"

    toolkit.get_finnhub_news = Mock(side_effect=mock_get_finnhub_news)
    toolkit.get_finnhub_news.name = "get_finnhub_news"
    toolkit.get_finnhub_news.__name__ = "get_finnhub_news"

    toolkit.get_reddit_news = Mock(side_effect=mock_get_reddit_news)
    toolkit.get_reddit_news.name = "get_reddit_news"
    toolkit.get_reddit_news.__name__ = "get_reddit_news"

    toolkit.get_global_news_openai = Mock(side_effect=mock_get_global_news_openai)
    toolkit.get_global_news_openai.name = "get_global_news_openai"
    toolkit.get_global_news_openai.__name__ = "get_global_news_openai"

    toolkit.get_google_news = Mock(side_effect=mock_get_google_news)
    toolkit.get_google_news.name = "get_google_news"
    toolkit.get_google_news.__name__ = "get_google_news"

    toolkit.get_fundamentals_openai = Mock(side_effect=mock_get_fundamentals_openai)
    toolkit.get_fundamentals_openai.name = "get_fundamentals_openai"
    toolkit.get_fundamentals_openai.__name__ = "get_fundamentals_openai"

    toolkit.get_finnhub_company_insider_sentiment = Mock(
        side_effect=mock_get_finnhub_company_insider_sentiment
    )
    toolkit.get_finnhub_company_insider_sentiment.name = (
        "get_finnhub_company_insider_sentiment"
    )
    toolkit.get_finnhub_company_insider_sentiment.__name__ = (
        "get_finnhub_company_insider_sentiment"
    )

    toolkit.get_finnhub_company_insider_transactions = Mock(
        side_effect=mock_get_finnhub_company_insider_transactions
    )
    toolkit.get_finnhub_company_insider_transactions.name = (
        "get_finnhub_company_insider_transactions"
    )
    toolkit.get_finnhub_company_insider_transactions.__name__ = (
        "get_finnhub_company_insider_transactions"
    )

    toolkit.get_simfin_balance_sheet = Mock(side_effect=mock_get_simfin_balance_sheet)
    toolkit.get_simfin_balance_sheet.name = "get_simfin_balance_sheet"
    toolkit.get_simfin_balance_sheet.__name__ = "get_simfin_balance_sheet"

    toolkit.get_simfin_cashflow = Mock(side_effect=mock_get_simfin_cashflow)
    toolkit.get_simfin_cashflow.name = "get_simfin_cashflow"
    toolkit.get_simfin_cashflow.__name__ = "get_simfin_cashflow"

    toolkit.get_simfin_income_stmt = Mock(side_effect=mock_get_simfin_income_stmt)
    toolkit.get_simfin_income_stmt.name = "get_simfin_income_stmt"
    toolkit.get_simfin_income_stmt.__name__ = "get_simfin_income_stmt"

    return toolkit


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "close": 150.0,
        "high": 155.0,
        "low": 148.0,
        "volume": 1000000,
        "date": "2024-05-10",
    }


@pytest.fixture
def sample_financial_data():
    """Sample financial data for testing."""
    return {
        "revenue": 100000000,
        "net_income": 20000000,
        "assets": 500000000,
        "liabilities": 200000000,
        "period": "annual",
        "date": "2024-05-10",
    }


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch, temp_data_dir):
    """Set up test environment variables and directories."""
    # Set test environment variables
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test-secret")

    # Create test data directories
    data_cache_dir = os.path.join(temp_data_dir, "dataflows", "data_cache")
    os.makedirs(data_cache_dir, exist_ok=True)

    finnhub_dir = os.path.join(data_cache_dir, "finnhub_data")
    os.makedirs(finnhub_dir, exist_ok=True)

    # Create subdirectories for different data types
    for data_type in ["news_data", "insider_trans", "SEC_filings", "fin_as_reported"]:
        os.makedirs(os.path.join(finnhub_dir, data_type), exist_ok=True)


@pytest.fixture
def mock_memory():
    """Mock financial situation memory."""
    memory = Mock()
    memory.add_memory = Mock()
    memory.get_memory = Mock(return_value="")
    memory.clear_memory = Mock()
    return memory


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (slow)",
    )
    config.addinivalue_line("markers", "unit: mark test as unit test (fast)")
    config.addinivalue_line("markers", "api: mark test as requiring API access")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on location."""
    for item in items:
        # Add unit marker to tests in unit/ directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Add integration marker to tests in integration/ directory
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
