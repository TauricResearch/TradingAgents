"""
/**
 * @module: TradingAgents
 * @file: __init__.py
 * @description: Credit data vendor module (ANBIMA, CVM)
 * @author: Maíra Pontin
 * @created: 2026-09-28T10:24:09
 * @updated: 2026-09-28T11:05:32
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

from .anbima import (
    get_yield_curve,
    get_credit_spreads,
    get_debenture_quote,
    get_ima_b_index,
)

__all__ = [
    "get_yield_curve",
    "get_credit_spreads",
    "get_debenture_quote",
    "get_ima_b_index",
]
