"""get_valuation_history: dividend yield, P/B and P/E against their own history.

All yfinance access is mocked. The fixture is built so the right answers are
round numbers: a steady 10.00 close and 0.50 a year of dividends (5% yield),
P/B 1.0x and P/E 10x through history, then a drop to 8.00 at the analysis date
(6.25% yield, 0.80x, 8x), so every metric should read "cheap vs own history".

Shares are reported on each fiscal year's own basis while Yahoo's closes are
adjusted for every later split, including one after the analysis date; P/B
only comes out at 1.0x if old share counts are restated to that basis.
"""
from __future__ import annotations

from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows import interface, y_finance

_CURR = "2026-06-30"


def _history(dividends: bool = True, start: str = "2015-01-31") -> pd.DataFrame:
    rows = {}
    for d in pd.date_range(start, "2026-05-31", freq="ME"):
        rows[d] = [10.0, 0.0, 0.0]
    if dividends:
        for year in range(pd.Timestamp(start).year, 2027):
            for md in ("05-10", "09-01"):
                d = pd.Timestamp(f"{year}-{md}")
                if d >= pd.Timestamp(start) and d <= pd.Timestamp(_CURR):
                    rows[d] = [10.0, 0.25, 0.0]
        rows[pd.Timestamp("2026-09-01")] = [99.0, 5.0, 0.0]  # after _CURR
    rows[pd.Timestamp("2025-01-15")] = [10.0, 0.0, 2.0]   # 2-for-1 before _CURR
    rows[pd.Timestamp("2026-06-29")] = [8.0, 0.0, 0.0]    # latest close
    rows[pd.Timestamp("2026-08-03")] = [99.0, 0.0, 1.5]   # bonus issue after _CURR
    index = pd.DatetimeIndex(sorted(rows)).tz_localize("Asia/Kuala_Lumpur")
    return pd.DataFrame(
        [rows[d.tz_localize(None)] for d in index],
        index=index,
        columns=["Close", "Dividends", "Stock Splits"],
    )


def _statements():
    ends = pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31", "2026-05-31"])
    income = pd.DataFrame([[300.0] * 5], index=["Net Income Common Stockholders"], columns=ends)
    # Pre-2025 years report pre-split shares; FY2025 reports post-split 200.
    balance = pd.DataFrame(
        [[3000.0] * 5, [100.0, 100.0, 100.0, 200.0, 200.0]],
        index=["Common Stock Equity", "Ordinary Shares Number"],
        columns=ends,
    )
    return income, balance


def _run(hist, statements=True, years=10):
    ticker = mock.MagicMock()
    ticker.history.return_value = hist
    if statements:
        ticker.income_stmt, ticker.balance_sheet = _statements()
    else:
        ticker.income_stmt = ticker.balance_sheet = pd.DataFrame()
    with mock.patch.object(y_finance.yf, "Ticker", return_value=ticker), \
         mock.patch.object(y_finance, "yf_retry", lambda fn: fn()):
        return y_finance.get_valuation_history("1155.KL", _CURR, years)


def _row(out: str, name: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(f"| {name}"))


@pytest.mark.unit
class TestValuationHistory:
    def test_current_values_and_verdicts(self):
        out = _run(_history())
        yld, pb, pe = (_row(out, n) for n in ("Dividend yield", "Price / book", "Price / earnings"))
        assert "| 6.25% |" in yld and "cheap vs own history" in yld
        assert "| 0.80x |" in pb and "cheap vs own history" in pb
        assert "| 8.00x |" in pe and "cheap vs own history" in pe
        assert "higher than 0% of months" in pb
        assert "higher than 100% of months" not in yld  # current is the max, not above it
        assert "| 5.00% (" in yld  # median-ish average stays near 5%

    def test_yield_band_spans_the_full_window(self):
        out = _run(_history())
        # 10 years back from 2026-06-30, monthly; P/B only from FY2022 + 2 months.
        assert "2016-07→2026-06, 120 months" in _row(out, "Dividend yield")
        assert "2023-02→2026-06, 41 months" in _row(out, "Price / book")

    def test_shares_restated_for_later_splits(self):
        out = _run(_history())
        # 100 pre-split shares × 2 (2025) × 1.5 (2026, after _CURR) = 300.
        assert "| 2022-12-31 | 2023-02-28 | 300 | 3,000 | 300 |" in out
        assert "| 2025-12-31 | 2026-02-28 | 300 | 3,000 | 300 |" in out
        assert "| 2024-12-31 | 10 | 5.00% | 1.00x | 10.00x |" in out

    def test_yield_needs_a_full_year_of_prices(self):
        out = _run(_history(start="2016-01-31"))
        # Prices start 2016-01, so the first full trailing-12-month yield is 2017-01.
        assert "2017-01→2026-06" in _row(out, "Dividend yield")

    def test_no_look_ahead(self):
        out = _run(_history())
        assert "2026-05-31 |" not in out.split("## Fiscal years used")[1]  # public 2026-07-31
        assert "| 99 |" not in out
        assert "2026-08" not in out and "2026-09" not in out

    def test_statements_unavailable_keeps_yield_band(self):
        out = _run(_history(), statements=False)
        assert "| 6.25% |" in _row(out, "Dividend yield")
        assert "annual statements unavailable" in _row(out, "Price / book")
        assert "## Fiscal years used" not in out

    def test_non_payer(self):
        out = _run(_history(dividends=False))
        assert "no dividends recorded" in _row(out, "Dividend yield")
        assert "| 0.80x |" in _row(out, "Price / book")

    def test_short_history_is_flagged(self):
        out = _run(_history(start="2025-12-31"), statements=False)
        assert "not enough history" in _row(out, "Dividend yield")


@pytest.mark.unit
class TestValuationRouting:
    def test_has_its_own_category(self):
        assert interface.get_category_for_method("get_valuation_history") == "valuation_data"
        assert "valuation_data" in interface.OPTIONAL_CATEGORIES

    def test_fundamentals_analyst_has_the_tool(self):
        from pathlib import Path

        src = (Path(interface.__file__).resolve().parents[1]
               / "agents" / "analysts" / "fundamentals_analyst.py").read_text()
        assert "get_valuation_history" in src
