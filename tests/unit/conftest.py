"""Shared mock factories for unit tests.

Network is blocked by pytest-socket (--disable-socket in addopts).
No test in tests/unit/ can hit a real API.
"""

import json
import pandas as pd
import pytest
from unittest.mock import MagicMock


# -- yfinance mock factories --


@pytest.fixture
def mock_yf_screener():
    """Pre-built yfinance screener mock."""

    def _make(quotes):
        return {"quotes": quotes}

    return _make


@pytest.fixture
def mock_yf_download():
    """Pre-built yfinance download mock returning a MultiIndex DataFrame."""

    def _make(symbols, periods=5, base_price=100.0):
        idx = pd.date_range("2024-01-04", periods=periods, freq="B")
        data = {s: [base_price + i for i in range(periods)] for s in symbols}
        df = pd.DataFrame(data, index=idx)
        df.columns = pd.MultiIndex.from_product([["Close"], symbols])
        return df

    return _make


# -- Alpha Vantage mock factories --


@pytest.fixture
def mock_av_request():
    """Pre-built Alpha Vantage _rate_limited_request mock."""

    def _make(responses: dict):
        """responses: {function_name: return_value} or callable."""

        def fake(function_name, params=None, **kwargs):
            if callable(responses.get(function_name)):
                return responses[function_name](params)
            return json.dumps(responses.get(function_name, {}))

        return fake

    return _make


# -- LLM mock factories --


@pytest.fixture
def mock_llm():
    """Pre-built LLM mock that returns canned responses."""

    def _make(content="Mocked LLM response."):
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content=content)
        llm.ainvoke.return_value = MagicMock(content=content)
        return llm

    return _make
