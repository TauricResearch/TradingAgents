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
