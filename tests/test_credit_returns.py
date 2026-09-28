"""
/**
 * @module: TradingAgents
 * @file: test_credit_returns.py
 * @description: Tests for credit return calculation
 * @author: AI Assistant
 * @created: 2026-09-28T10:56:38
 * @updated: 2026-09-28T10:56:38
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import MagicMock, patch
from tradingagents.graph.trading_graph import TradingAgentsGraph


def test_fetch_credit_returns_calculates_total_return():
    """_fetch_credit_returns should calculate total return from yield change."""
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)

    with patch("tradingagents.graph.trading_graph.get_debenture_quote") as mock_quote:
        mock_quote.side_effect = [
            {"price": 95.0, "yield": 12.0},  # start
            {"price": 96.0, "yield": 11.5},  # end
        ]

        raw_return, alpha, holding_days, resolution_date = graph._fetch_credit_returns(
            "PETR41", "2026-09-01", "^IRFM", holding_days=30
        )

        assert raw_return is not None
        assert isinstance(raw_return, float)
        assert raw_return > 0  # price increased from 95 to 96


def test_fetch_credit_returns_handles_missing_data():
    """_fetch_credit_returns should return None when data is unavailable."""
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)

    with patch("tradingagents.graph.trading_graph.get_debenture_quote") as mock_quote:
        mock_quote.side_effect = [
            {"price": 95.0, "yield": 12.0},  # start
            {},  # end (missing)
        ]

        raw_return, alpha, holding_days, resolution_date = graph._fetch_credit_returns(
            "PETR41", "2026-09-01", "^IRFM", holding_days=30
        )

        assert raw_return is None
