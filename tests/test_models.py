"""
/**
 * @module: TradingAgents
 * @file: test_models.py
 * @description: Tests for CLI models (AssetType, AnalystType enums)
 * @author: AI Assistant
 * @created: 2026-09-28T10:11:22
 * @updated: 2026-09-28T10:11:22
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from cli.models import AssetType, AnalystType


def test_asset_type_has_credit():
    """AssetType enum should include CREDIT."""
    assert hasattr(AssetType, "CREDIT")
    assert AssetType.CREDIT.value == "credit"


def test_analyst_type_has_credit_fundamentals():
    """AnalystType enum should include CREDIT_FUNDAMENTALS."""
    assert hasattr(AnalystType, "CREDIT_FUNDAMENTALS")
    assert AnalystType.CREDIT_FUNDAMENTALS.value == "credit_fundamentals"


def test_analyst_type_has_credit_news():
    """AnalystType enum should include CREDIT_NEWS."""
    assert hasattr(AnalystType, "CREDIT_NEWS")
    assert AnalystType.CREDIT_NEWS.value == "credit_news"
