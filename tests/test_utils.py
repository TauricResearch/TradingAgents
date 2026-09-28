"""
/**
 * @module: TradingAgents
 * @file: test_utils.py
 * @description: Tests for CLI utilities (detect_asset_type, filter_analysts)
 * @author: Maíra Pontin
 * @created: 2026-09-28T10:14:45
 * @updated: 2026-09-28T11:05:32
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from cli.models import AssetType
from cli.utils import detect_asset_type


def test_detect_asset_type_credit_cusip():
    """Debenture CUSIP pattern (4 letters + 2 digits) should be CREDIT."""
    assert detect_asset_type("PETR41") == AssetType.CREDIT
    assert detect_asset_type("VALE32") == AssetType.CREDIT
    assert detect_asset_type("OIBR33") == AssetType.CREDIT


def test_detect_asset_type_brazilian_equity():
    """Brazilian equity (.SA suffix) should be STOCK."""
    assert detect_asset_type("PETR4.SA") == AssetType.STOCK
    assert detect_asset_type("VALE3.SA") == AssetType.STOCK


def test_detect_asset_type_crypto():
    """Crypto suffixes should be CRYPTO."""
    assert detect_asset_type("BTC-USD") == AssetType.CRYPTO
    assert detect_asset_type("ETH-USD") == AssetType.CRYPTO


def test_detect_asset_type_us_equity():
    """US equity (no suffix) should be STOCK."""
    assert detect_asset_type("AAPL") == AssetType.STOCK
    assert detect_asset_type("MSFT") == AssetType.STOCK


from cli.models import AnalystType
from cli.utils import filter_analysts_for_asset_type


def test_filter_analysts_credit_mode():
    """Credit mode should keep only credit fundamentals and credit news."""
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
        AnalystType.CREDIT_FUNDAMENTALS,
        AnalystType.CREDIT_NEWS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, AssetType.CREDIT)
    assert filtered == [AnalystType.CREDIT_FUNDAMENTALS, AnalystType.CREDIT_NEWS]


def test_filter_analysts_crypto_mode():
    """Crypto mode should drop fundamentals (existing behavior)."""
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, AssetType.CRYPTO)
    assert AnalystType.FUNDAMENTALS not in filtered
    assert AnalystType.MARKET in filtered


def test_filter_analysts_stock_mode():
    """Stock mode should keep all analysts (existing behavior)."""
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, AssetType.STOCK)
    assert filtered == all_analysts
