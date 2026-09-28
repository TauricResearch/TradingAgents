"""
/**
 * @module: TradingAgents
 * @file: anbima.py
 * @description: ANBIMA data vendor (yield curve, credit spreads, indicative quotes, IMA-B index)
 * @author: Maíra Pontin
 * @created: 2026-09-28T10:24:09
 * @updated: 2026-09-28T11:29:39
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import logging
from typing import Annotated, Dict, List, Tuple

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _fetch_anbima_data() -> dict:
    """Fetch data from ANBIMA API or website.

    TODO: Implement actual ANBIMA API client or web scraper.
    For now, return mock data for testing.

    ANBIMA provides:
    - Yield curve (zero rates by maturity)
    - Credit spreads vs CDI
    - Indicative quotes for benchmark debentures
    - IMA-B index daily values
    """
    # Mock implementation for testing
    return {
        "yield_curve": {1: 10.5, 2: 11.0, 3: 11.5, 5: 12.0, 10: 13.0},
        "credit_spreads": {
            "PETR": {1: 150, 2: 160, 3: 170, 5: 180},
            "VALE": {1: 120, 2: 130, 3: 140, 5: 150},
        },
        "quotes": {
            "PETR41": {"price": 95.5, "yield": 12.5, "maturity": 3, "coupon": 10.0, "face_value": 1000},
            "VALE32": {"price": 98.0, "yield": 11.5, "maturity": 2, "coupon": 9.5, "face_value": 1000},
        },
        "ima_b": [
            ("2026-09-01", 1000.0),
            ("2026-09-02", 1005.0),
            ("2026-09-03", 1010.0),
        ],
    }


@tool
def get_yield_curve() -> Dict[int, float]:
    """Fetch ANBIMA yield curve (zero rates by maturity).

    Returns:
        dict[maturity_years] = rate_percent
        Example: {1: 10.5, 2: 11.0, 3: 11.5}
    """
    data = _fetch_anbima_data()
    return data.get("yield_curve", {})


@tool
def get_credit_spreads(issuer: Annotated[str, "issuer code, e.g. PETR, VALE"]) -> Dict[int, float]:
    """Fetch credit spread vs CDI for issuer's debentures.

    Args:
        issuer: Issuer code (e.g., "PETR", "VALE")

    Returns:
        dict[maturity_years] = spread_bps
        Example: {1: 150, 2: 160, 3: 170}
    """
    data = _fetch_anbima_data()
    spreads = data.get("credit_spreads", {})
    return spreads.get(issuer, {})


@tool
def get_debenture_quote(cusip: str) -> dict:
    """Fetch indicative quote for specific debenture.

    Args:
        cusip: Debenture CUSIP (e.g., "PETR41")

    Returns:
        dict with keys: price, yield, maturity, coupon, face_value
        Example: {"price": 95.5, "yield": 12.5, "maturity": 3, "coupon": 10.0, "face_value": 1000}
    """
    data = _fetch_anbima_data()
    quotes = data.get("quotes", {})
    return quotes.get(cusip, {})


@tool
def get_ima_b_index() -> List[Tuple[str, float]]:
    """Fetch IMA-B index daily values.

    Returns:
        list of (date, index_value) tuples
        Example: [("2026-09-01", 1000.0), ("2026-09-02", 1005.0)]
    """
    data = _fetch_anbima_data()
    return data.get("ima_b", [])
