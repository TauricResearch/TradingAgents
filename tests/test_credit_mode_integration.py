"""
/**
 * @module: TradingAgents
 * @file: test_credit_mode_integration.py
 * @description: Integration tests for credit mode
 * @author: Maíra Pontin
 * @created: 2026-09-28T11:02:30
 * @updated: 2026-09-28T11:05:32
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from cli.models import AssetType, AnalystType
from cli.utils import detect_asset_type, filter_analysts_for_asset_type


def test_credit_mode_end_to_end():
    """End-to-end test: detect credit ticker, filter analysts, verify credit mode."""
    # Detect asset type
    ticker = "PETR41"
    asset_type = detect_asset_type(ticker)
    assert asset_type == AssetType.CREDIT

    # Filter analysts
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
        AnalystType.CREDIT_FUNDAMENTALS,
        AnalystType.CREDIT_NEWS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, asset_type)

    # Verify only credit analysts remain
    assert len(filtered) == 2
    assert AnalystType.CREDIT_FUNDAMENTALS in filtered
    assert AnalystType.CREDIT_NEWS in filtered
    assert AnalystType.MARKET not in filtered
    assert AnalystType.SOCIAL not in filtered


def test_brazilian_equity_not_credit():
    """Brazilian equity (.SA suffix) should be STOCK, not CREDIT."""
    ticker = "PETR4.SA"
    asset_type = detect_asset_type(ticker)
    assert asset_type == AssetType.STOCK


def test_us_equity_not_credit():
    """US equity should be STOCK, not CREDIT."""
    ticker = "AAPL"
    asset_type = detect_asset_type(ticker)
    assert asset_type == AssetType.STOCK
