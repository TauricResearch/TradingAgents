"""
/**
 * @module: TradingAgents
 * @file: test_anbima.py
 * @description: Tests for ANBIMA data vendor
 * @author: Maíra Pontin
 * @created: 2026-09-28T10:24:09
 * @updated: 2026-09-28T11:05:32
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import patch, MagicMock
from tradingagents.dataflows.credit.anbima import (
    get_yield_curve,
    get_credit_spreads,
    get_debenture_quote,
    get_ima_b_index,
)


def test_get_yield_curve_returns_dict():
    """get_yield_curve should return dict[maturity_years] = rate_percent."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "yield_curve": {1: 10.5, 2: 11.0, 3: 11.5, 5: 12.0}
        }
        result = get_yield_curve.invoke({})
        assert isinstance(result, dict)
        assert 1 in result
        assert result[1] == 10.5


def test_get_credit_spreads_returns_dict():
    """get_credit_spreads should return dict[maturity_years] = spread_bps."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "credit_spreads": {"PETR": {1: 150, 2: 160, 3: 170}}
        }
        result = get_credit_spreads.invoke({"issuer": "PETR"})
        assert isinstance(result, dict)
        assert 1 in result
        assert result[1] == 150


def test_get_debenture_quote_returns_dict():
    """get_debenture_quote should return dict with price, yield, maturity, coupon, face_value."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "quotes": {"PETR41": {"price": 95.5, "yield": 12.5, "maturity": 3, "coupon": 10.0, "face_value": 1000}}
        }
        result = get_debenture_quote("PETR41")
        assert isinstance(result, dict)
        assert "price" in result
        assert result["price"] == 95.5


def test_get_ima_b_index_returns_list():
    """get_ima_b_index should return list of (date, index_value) tuples."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "ima_b": [("2026-09-01", 1000.0), ("2026-09-02", 1005.0)]
        }
        result = get_ima_b_index()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == ("2026-09-01", 1000.0)
