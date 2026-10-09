"""get_dividend_history: dividend per share history, growth, yield and payout.

All yfinance access is mocked. The fixture mimics a Bursa bank: an interim and
a final dividend each year, ex-dates in Kuala Lumpur time, one cut year, and a
dividend dated after the analysis date that must never leak into the report.
"""
from __future__ import annotations

from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows import interface, y_finance
from tradingagents.dataflows.symbol_utils import NoMarketDataError

_CURR = "2026-06-30"


def _history(payments: dict[str, float], closes: dict[str, float] | None = None) -> pd.DataFrame:
    dates = sorted(set(payments) | set(closes or {}))
    index = pd.DatetimeIndex(dates).tz_localize("Asia/Kuala_Lumpur")
    return pd.DataFrame(
        {
            "Close": [(closes or {}).get(d, 10.0) for d in dates],
            "Dividends": [payments.get(d, 0.0) for d in dates],
        },
        index=index,
    )


def _bank_payments() -> dict[str, float]:
    payments = {}
    for year in range(2016, 2026):
        interim, final = 0.25, 0.30
        if year == 2020:  # pandemic-style cut
            interim, final = 0.10, 0.15
        payments[f"{year}-09-01"] = interim
        payments[f"{year}-05-10"] = final
    payments["2026-05-08"] = 0.32
    payments["2026-09-01"] = 0.28  # after _CURR: must not appear
    return payments


def _cashflow() -> pd.DataFrame:
    cols = pd.to_datetime(["2023-12-31", "2024-12-31", "2026-12-31"])
    return pd.DataFrame(
        [[-6_000_000_000, -6_500_000_000, -9_999_000_000],
         [10_000_000_000, 10_000_000_000, 11_111_000_000]],
        index=["Cash Dividends Paid", "Net Income From Continuing Operations"],
        columns=cols,
    )


def _run(hist, cashflow=None, curr_date=_CURR, years=10):
    ticker = mock.MagicMock()
    ticker.history.return_value = hist
    ticker.cashflow = _cashflow() if cashflow is None else cashflow
    with mock.patch.object(y_finance.yf, "Ticker", return_value=ticker), \
         mock.patch.object(y_finance, "yf_retry", lambda fn: fn()):
        return y_finance.get_dividend_history("1155.KL", curr_date, years)


@pytest.mark.unit
class TestDividendHistory:
    def test_annual_totals_and_cut_detection(self):
        out = _run(_history(_bank_payments()))
        assert "| 2019 | 0.55 | 2 |" in out
        assert "| 2020 | 0.25 | 2 | -54.5% |" in out
        assert "| 2021 | 0.55 | 2 | +120.0% |" in out
        # The oldest year in the window is complete, not a half year that
        # fakes a +120% "hike" in the year after it.
        assert "| 2016 | 0.55 | 2 | n/a |" in out
        assert "| 2017 | 0.55 | 2 | +0.0% |" in out
        assert "Years with a lower total than the year before: 2020 (-54.5%)" in out

    def test_no_look_ahead(self):
        out = _run(_history(_bank_payments()))
        assert "2026-09-01" not in out
        assert "0.28" not in out
        # Fiscal period ending after curr_date is dropped from the payout table.
        assert "2026-12-31" not in out
        assert "| 2026 (YTD, partial) | 0.32 | 1 | — |" in out

    def test_ttm_yield_streak_and_cagr(self):
        closes = {"2026-06-29": 11.0}
        out = _run(_history(_bank_payments(), closes))
        # TTM window (2025-06-30, 2026-06-30]: 2025-09-01 0.25 + 2026-05-08 0.32
        assert "Trailing 12-month DPS: 0.57 (2 payment(s))" in out
        assert "Trailing dividend yield: 5.18%" in out
        assert "on close of 11 at 2026-06-29" in out
        assert "Consecutive complete years with a dividend: 10" in out
        assert "5-year DPS CAGR (2020→2025): +17.1% a year" in out
        assert "Latest ex-date: 2026-05-08 (0.32 per share)" in out

    def test_cash_payout_ratio(self):
        out = _run(_history(_bank_payments()))
        assert "| 2023-12-31 | 6,000,000,000 | 10,000,000,000 | 60.0% |" in out
        assert "| 2024-12-31 | 6,500,000,000 | 10,000,000,000 | 65.0% |" in out

    def test_gap_year_is_not_compared_across_the_gap(self):
        payments = {"2021-05-10": 0.20, "2023-05-10": 0.10}
        out = _run(_history(payments, {"2026-06-29": 5.0}))
        assert "| 2023 | 0.1 | 1 | n/a (no dividend in 2022) |" in out
        assert "Years with a lower total than the year before: none in range" in out
        assert "Consecutive complete years with a dividend: 0" in out

    def test_non_payer_is_reported_not_raised(self):
        out = _run(_history({}, {"2026-06-29": 5.0}))
        assert "No cash dividends recorded" in out
        assert "do not infer a yield" in out

    def test_missing_cashflow_degrades(self):
        out = _run(_history(_bank_payments()), cashflow=pd.DataFrame())
        assert "Cash payout ratio: unavailable" in out
        assert "## Annual dividends" in out

    def test_empty_history_is_no_data(self):
        with pytest.raises(NoMarketDataError):
            _run(pd.DataFrame())


@pytest.mark.unit
class TestDividendRouting:
    def test_has_its_own_category(self):
        assert interface.get_category_for_method("get_dividend_history") == "dividend_data"
        assert "yfinance" in interface.VENDOR_METHODS["get_dividend_history"]

    def test_alpha_vantage_fundamentals_does_not_break_dividends(self):
        from tradingagents.dataflows.config import get_config, set_config

        original = get_config()["data_vendors"]
        try:
            set_config({"data_vendors": {"fundamental_data": "alpha_vantage", "dividend_data": "yfinance"}})
            with mock.patch.dict(
                interface.VENDOR_METHODS["get_dividend_history"],
                {"yfinance": lambda *a: "ok"},
            ):
                assert interface.route_to_vendor("get_dividend_history", "1155.KL", _CURR, 10) == "ok"
        finally:
            set_config({"data_vendors": original})

    def test_fundamentals_analyst_has_the_tool(self):
        from pathlib import Path

        src = (Path(interface.__file__).resolve().parents[1]
               / "agents" / "analysts" / "fundamentals_analyst.py").read_text()
        assert "get_dividend_history" in src
