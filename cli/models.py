"""
/**
 * @module: TradingAgents
 * @file: models.py
 * @description: Core enum definitions for asset and analyst types
 * @author: Maíra Pontin
 * @created: 2024-01-01T00:00:00
 * @updated: 2026-09-28T10:11:22
 * @version: 1.1.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    # Wire value stays "social" for saved-config and string-keyed-caller
    # back-compat; the user-facing label is "Sentiment Analyst".
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    CREDIT_FUNDAMENTALS = "credit_fundamentals"  # NEW
    CREDIT_NEWS = "credit_news"  # NEW


class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
    CREDIT = "credit"  # NEW
