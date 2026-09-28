"""
/**
 * @module: TradingAgents
 * @file: test_utils.py
 * @description: Tests for CLI utilities (detect_asset_type, filter_analysts)
 * @author: AI Assistant
 * @created: 2026-09-28T10:14:45
 * @updated: 2026-09-28T10:14:45
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
