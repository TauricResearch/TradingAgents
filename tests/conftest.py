import logging
from unittest.mock import MagicMock, patch

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (multi-component)"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as an end-to-end test (full workflow)"
    )
    config.addinivalue_line("markers", "slow: mark test as slow-running (>5s)")
    config.addinivalue_line(
        "markers", "external_api: mark test as requiring external API calls"
    )
    config.addinivalue_line("markers", "llm: mark test as requiring LLM calls")


@pytest.fixture(autouse=True)
def reset_logging_state():
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    tradingagents_logger = logging.getLogger("tradingagents")
    for handler in tradingagents_logger.handlers[:]:
        tradingagents_logger.removeHandler(handler)
    tradingagents_logger.setLevel(logging.NOTSET)

    try:
        import tradingagents.logging as log_module

        log_module._logging_initialized = False
    except ImportError:
        pass

    try:
        from tradingagents import config as main_config

        main_config._settings = None
    except ImportError:
        pass

    yield

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    tradingagents_logger = logging.getLogger("tradingagents")
    for handler in tradingagents_logger.handlers[:]:
        tradingagents_logger.removeHandler(handler)
    tradingagents_logger.setLevel(logging.NOTSET)

    try:
        import tradingagents.logging as log_module

        log_module._logging_initialized = False
    except ImportError:
        pass

    try:
        from tradingagents import config as main_config

        main_config._settings = None
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def reset_config_state():
    try:
        import tradingagents.dataflows.config as config_module

        config_module._config = None
        config_module.DATA_DIR = None
    except ImportError:
        pass

    yield

    try:
        import tradingagents.dataflows.config as config_module

        config_module._config = None
        config_module.DATA_DIR = None
    except ImportError:
        pass


@pytest.fixture
def mock_llm():
    mock = MagicMock()
    mock.invoke.return_value = MagicMock(content="Test LLM response")
    mock.with_structured_output.return_value = mock
    return mock


@pytest.fixture
def sample_config():
    return {
        "llm_provider": "openai",
        "quick_think_llm": "gpt-4o-mini",
        "deep_think_llm": "gpt-4o",
        "backend_url": "https://api.openai.com/v1",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "data_dir": "/tmp/tradingagents_test",
        "results_dir": "/tmp/tradingagents_test/results",
        "discovery_max_results": 10,
    }


@pytest.fixture
def sample_news_article():
    from datetime import datetime, timezone

    return {
        "title": "Test News Article",
        "source": "Test Source",
        "url": "https://example.com/article",
        "published_at": datetime.now(timezone.utc),
        "summary": "Test summary of the article",
    }


@pytest.fixture
def sample_trending_stock():
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "score": 85.5,
        "sentiment": 0.7,
        "mention_count": 150,
        "sector": "technology",
        "event_type": "earnings",
        "news_summary": "Apple reported strong quarterly earnings",
        "source_articles": [],
    }


@pytest.fixture
def mock_openai_client():
    with patch("openai.OpenAI") as mock:
        yield mock


@pytest.fixture
def mock_chromadb():
    with patch("chromadb.Client") as mock:
        yield mock
