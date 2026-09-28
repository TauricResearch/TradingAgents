"""
/**
 * @module: TradingAgents
 * @file: test_interface.py
 * @description: Tests for data vendor interface
 * @author: AI Assistant
 * @created: 2026-09-28T10:29:25
 * @updated: 2026-09-28T10:32:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import sys
from unittest.mock import MagicMock

# Mock heavy dependencies before importing interface
_mock = MagicMock()
for mod in [
    "yfinance",
    "yfinance.exceptions",
    "alpha_vantage",
    "alpha_vantage.foreign_exchange",
    "stockstats",
]:
    if mod not in sys.modules:
        sys.modules[mod] = _mock

import pytest
from tradingagents.dataflows.interface import VENDOR_LIST, TOOLS_CATEGORIES


def test_anbima_in_vendor_list():
    """ANBIMA should be in VENDOR_LIST."""
    assert "anbima" in VENDOR_LIST


def test_credit_data_in_tools_categories():
    """credit_data should be in TOOLS_CATEGORIES."""
    assert "credit_data" in TOOLS_CATEGORIES
    assert "tools" in TOOLS_CATEGORIES["credit_data"]
    assert "get_yield_curve" in TOOLS_CATEGORIES["credit_data"]["tools"]
    assert "get_credit_spreads" in TOOLS_CATEGORIES["credit_data"]["tools"]
    assert "get_debenture_quote" in TOOLS_CATEGORIES["credit_data"]["tools"]
    assert "get_ima_b_index" in TOOLS_CATEGORIES["credit_data"]["tools"]
