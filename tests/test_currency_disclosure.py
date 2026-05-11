"""Tests for currency disclosure in fundamentals data + style prompts.

Real bug we hit: PDD's fundamentals analyst computed `$343.1B net cash /
1.48B ADR = $231/share net cash` while the balance-sheet values were
actually in CNY. That bumped the safety margin from a real -22% to a
fake +82% and inverted the buy/skip verdict.

These tests lock in the framework-level safeguards:
1. y_finance.get_fundamentals exposes both currencies and warns on mismatch.
2. Each Alpha Vantage fundamentals wrapper surfaces the reporting currency.
3. Every style prompt instructs the LLM to verify currency before computing
   per-share figures.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# yfinance currency disclosure
# ---------------------------------------------------------------------------


def test_yfinance_fundamentals_includes_both_currencies():
    """The fundamentals header surfaces both financial and trading currency."""
    from tradingagents.dataflows.y_finance import get_fundamentals

    fake_info = {
        "longName": "Test Co",
        "sector": "Tech",
        "marketCap": 100000000000,
        "trailingPE": 15,
        "financialCurrency": "USD",
        "currency": "USD",
    }
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.info = fake_info
        mock_ticker_cls.return_value = mock_ticker

        out = get_fundamentals("AAPL")

    assert "Financial Statement Currency: USD" in out
    assert "Trading Currency: USD" in out


def test_yfinance_fundamentals_warns_on_currency_mismatch():
    """ADR-style mismatches (e.g. PDD: financials in CNY, price in USD) trigger
    a prominent warning at the top of the fundamentals output."""
    from tradingagents.dataflows.y_finance import get_fundamentals

    fake_info = {
        "longName": "Pinduoduo",
        "sector": "Consumer",
        "marketCap": 140000000000,
        "trailingPE": 10,
        "financialCurrency": "CNY",
        "currency": "USD",
    }
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.info = fake_info
        mock_ticker_cls.return_value = mock_ticker

        out = get_fundamentals("PDD")

    # Header surfaces both currencies AND a mismatch warning
    assert "Financial Statement Currency: CNY" in out
    assert "Trading Currency: USD" in out
    assert "Currency mismatch" in out
    # Must specifically call out the per-share trap
    assert "per-share" in out.lower() or "per share" in out.lower()


def test_yfinance_fundamentals_no_warning_when_currencies_match():
    """No mismatch warning for vanilla US companies — keeps the report tidy."""
    from tradingagents.dataflows.y_finance import get_fundamentals

    fake_info = {
        "longName": "Apple",
        "sector": "Tech",
        "marketCap": 3000000000000,
        "trailingPE": 30,
        "financialCurrency": "USD",
        "currency": "USD",
    }
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.info = fake_info
        mock_ticker_cls.return_value = mock_ticker

        out = get_fundamentals("AAPL")

    assert "Currency mismatch" not in out


def test_yfinance_balance_sheet_surfaces_reporting_currency():
    from tradingagents.dataflows.y_finance import get_balance_sheet

    fake_bs = pd.DataFrame(
        {pd.Timestamp("2025-03-31"): [108_900_000_000, 5_400_000_000]},
        index=["Cash", "Total Debt"],
    )
    fake_info = {"financialCurrency": "CNY"}

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_balance_sheet = fake_bs
        mock_ticker.info = fake_info
        mock_ticker_cls.return_value = mock_ticker

        out = get_balance_sheet("PDD")

    assert "Reporting Currency: CNY" in out
    assert "all values below are in CNY" in out


# ---------------------------------------------------------------------------
# Alpha Vantage currency disclosure
# ---------------------------------------------------------------------------


def test_alpha_vantage_overview_surfaces_currency():
    from tradingagents.dataflows.alpha_vantage_fundamentals import get_fundamentals

    with patch(
        "tradingagents.dataflows.alpha_vantage_fundamentals._make_api_request",
        return_value={"Symbol": "PDD", "Currency": "CNY", "Name": "Pinduoduo"},
    ):
        out = get_fundamentals("PDD")

    assert "Reporting Currency: CNY" in out
    assert "Pinduoduo" in out  # original payload preserved


def test_alpha_vantage_balance_sheet_extracts_reported_currency():
    from tradingagents.dataflows.alpha_vantage_fundamentals import get_balance_sheet

    fake_response = {
        "symbol": "PDD",
        "annualReports": [
            {"fiscalDateEnding": "2024-12-31", "reportedCurrency": "CNY", "totalAssets": "500000000000"},
            {"fiscalDateEnding": "2023-12-31", "reportedCurrency": "CNY", "totalAssets": "300000000000"},
        ],
    }
    with patch(
        "tradingagents.dataflows.alpha_vantage_fundamentals._make_api_request",
        return_value=fake_response,
    ):
        out = get_balance_sheet("PDD", curr_date="2025-01-01")

    assert "Reporting Currency: CNY" in out
    # JSON payload should still be embedded so the LLM has the raw data
    assert "annualReports" in out


def test_alpha_vantage_passes_through_string_errors():
    """If the upstream API returns a string error message, don't wrap it
    in misleading currency wording."""
    from tradingagents.dataflows.alpha_vantage_fundamentals import get_fundamentals

    with patch(
        "tradingagents.dataflows.alpha_vantage_fundamentals._make_api_request",
        return_value="Error: rate limit exceeded",
    ):
        out = get_fundamentals("PDD")

    assert "Error: rate limit exceeded" in out
    assert "Reporting Currency:" not in out


# ---------------------------------------------------------------------------
# Style prompts must include the currency-check instruction
# ---------------------------------------------------------------------------


def test_buffett_prompt_has_lens_0_currency_check():
    from tradingagents.agents.analysts.fundamentals_styles.buffett_value import (
        BuffettValueStyle,
    )

    msg = BuffettValueStyle().system_message()
    assert "Currency Sanity Check" in msg
    assert "LENS 0" in msg
    # Specific currencies users will run into
    assert "CNY" in msg
    assert "JPY" in msg
    # Reminder about the 7x trap
    assert "≈7×" in msg or "7x" in msg.lower() or "7×" in msg
    # Verdict table must include currency row
    assert "0. Currency" in msg


def test_comprehensive_prompt_has_currency_check():
    from tradingagents.agents.analysts.fundamentals_styles.comprehensive import (
        ComprehensiveStyle,
    )

    msg = ComprehensiveStyle().system_message()
    assert "CURRENCY CHECK" in msg or "currency check" in msg.lower()
    assert "Financial Statement Currency" in msg
    assert "Trading Currency" in msg


def test_growth_prompt_has_currency_check():
    from tradingagents.agents.analysts.fundamentals_styles.growth import GrowthStyle

    msg = GrowthStyle().system_message()
    assert "CURRENCY CHECK" in msg or "currency check" in msg.lower()
    assert "PEG" in msg  # currency check must specifically call out PEG, the key growth ratio


def test_buffett_prompt_currency_check_appears_before_lens_1():
    """Lens 0 must come BEFORE moat analysis so currency is established
    before any per-share or DCF calculation."""
    from tradingagents.agents.analysts.fundamentals_styles.buffett_value import (
        BuffettValueStyle,
    )

    msg = BuffettValueStyle().system_message()
    pos_lens_0 = msg.find("LENS 0")
    pos_lens_1 = msg.find("LENS 1")
    assert pos_lens_0 != -1 and pos_lens_1 != -1
    assert pos_lens_0 < pos_lens_1
