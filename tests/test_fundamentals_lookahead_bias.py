"""Look-ahead-bias guard for retro/backtest fundamentals (TradingAgents#21).

History: yfinance statements are keyed by fiscal PERIOD-END date, not the date
results were announced, and Indian companies report 2-4 weeks after quarter
end -- so a "period end <= run date" filter let an unannounced quarter leak
(confirmed live: ICICIBANK.NS on 2026-07-17, a day before its 2026-07-18 Q1
FY27 announcement, already showed that quarter's figures). The fork's first
fixes (#22, #25) embargoed quarter-dependent profile fields and dropped the
newest statement column when an announcement landed after the run date.

Upstream v0.7 then fixed the same leak more strictly for every vendor:
``Ticker.info`` is withheld from any past-dated run (#1300; it has no
historical vintage at all -- PE, market cap and the 52-week range move with
today's quote), and statements dated only by their period are withheld from
past runs, with SEC EDGAR serving US filers as filed. That leaves NSE/BSE
listings with no statements at all in a retro run, so the fork serves a past
run the Yahoo periods whose announcement date -- from Yahoo's earnings
calendar -- falls strictly before the run date, and withholds otherwise.
"""
import unittest
from datetime import date
from unittest import mock

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.fundamentals as fundamentals


def _earnings_dates_df(rows):
    """rows: list of (iso_date_str_with_tz_offset, reported_eps_or_none)."""
    index = pd.to_datetime([r[0] for r in rows], utc=True)
    return pd.DataFrame({"Reported EPS": [r[1] for r in rows]}, index=index)


# Mirrors a real get_earnings_dates() shape: newest first, future rows have
# NaN Reported EPS, past rows have a real value.
_ICICIBANK_LIKE_EARNINGS = _earnings_dates_df([
    ("2026-10-17 06:00:00-04:00", None),
    ("2026-07-18 04:00:00-04:00", 20.42),   # Q1 FY27 (period end 2026-06-30)
    ("2026-04-18 05:00:00-04:00", 18.90),   # Q4 FY26 / FY26 (2026-03-31)
    ("2026-01-17 04:00:00-05:00", 15.62),   # Q3 (2025-12-31)
    ("2025-10-18 05:00:00-04:00", 17.06),   # Q2 (2025-09-30)
])

# A mature company's real calendar: every quarter announced ~30 days after it
# ends, six years deep -- far more announcements than the ~5 statement columns
# yfinance returns (the shape that broke the count-based first fix, #22).
_LONG_HISTORY_EARNINGS = _earnings_dates_df(
    [("2026-10-30 06:00:00-04:00", None)]
    + [((q + pd.Timedelta(days=30)).strftime("%Y-%m-%d 04:00:00-04:00"), 1.0)
       for q in pd.date_range("2020-03-31", "2026-06-30", freq="QE")[::-1]]
)

_QUARTERS = [
    pd.Timestamp("2026-06-30"), pd.Timestamp("2026-03-31"),
    pd.Timestamp("2025-12-31"), pd.Timestamp("2025-09-30"),
]


def _ticker(earnings, **statements):
    ticker_obj = mock.Mock()
    ticker_obj.get_earnings_dates.return_value = earnings
    for attr, data in statements.items():
        setattr(ticker_obj, attr, data)
    return ticker_obj


def _income(ticker_obj, as_of, freq="quarterly", symbol="ICICIBANK.NS"):
    with mock.patch.object(fundamentals.yf, "Ticker", return_value=ticker_obj):
        return fundamentals.get_income_statement(symbol, freq, as_of)


@pytest.mark.unit
class PastRunStatementsTests(unittest.TestCase):
    def test_unannounced_quarter_is_dropped_though_its_period_ended(self):
        data = pd.DataFrame({c: [100.0] for c in _QUARTERS})
        report = _income(_ticker(_ICICIBANK_LIKE_EARNINGS, quarterly_income_stmt=data), "2026-07-17")
        self.assertNotIn("2026-06-30", report)
        for kept in ("2026-03-31", "2025-12-31", "2025-09-30"):
            self.assertIn(kept, report)
        self.assertIn("Point-in-time as of: 2026-07-17", report)

    def test_announcement_day_itself_is_not_yet_known(self):
        # Results can land after the close on the announcement day, after a
        # decision made that session.
        data = pd.DataFrame({c: [100.0] for c in _QUARTERS[:2]})
        ticker_obj = _ticker(_ICICIBANK_LIKE_EARNINGS, quarterly_income_stmt=data)
        self.assertNotIn("2026-06-30", _income(ticker_obj, "2026-07-18"))
        self.assertIn("2026-06-30", _income(ticker_obj, "2026-07-19"))

    def test_annual_statement_is_held_back_until_its_results_are_announced(self):
        # The FY ending 2026-03-31 was announced 2026-04-18: the old code
        # filtered annual statements by period end only and leaked it here.
        data = pd.DataFrame({c: [100.0] for c in (pd.Timestamp("2026-03-31"), pd.Timestamp("2025-03-31"))})
        report = _income(_ticker(_LONG_HISTORY_EARNINGS, income_stmt=data), "2026-04-10", freq="annual")
        self.assertNotIn("2026-03-31", report)
        self.assertIn("2025-03-31", report)

    def test_mature_company_drops_only_the_leaked_column(self):
        cols = _QUARTERS + [pd.Timestamp("2025-06-30")]
        data = pd.DataFrame({c: [100.0] for c in cols})
        report = _income(_ticker(_LONG_HISTORY_EARNINGS, quarterly_income_stmt=data),
                         "2026-07-28", symbol="ASIANPAINT.NS")
        self.assertNotIn("2026-06-30", report)
        self.assertIn("2026-03-31", report)
        self.assertIn("2025-06-30", report)

    def test_no_earnings_calendar_falls_back_to_upstream_withholding(self):
        data = pd.DataFrame({c: [100.0] for c in _QUARTERS})
        ticker_obj = _ticker(None, quarterly_income_stmt=data)
        report = _income(ticker_obj, "2026-07-17")
        self.assertIn("withheld for this date", report)
        self.assertNotIn("2026-03-31", report)

    def test_earnings_calendar_error_falls_back_to_upstream_withholding(self):
        ticker_obj = _ticker(None, quarterly_income_stmt=pd.DataFrame({_QUARTERS[0]: [1.0]}))
        ticker_obj.get_earnings_dates.side_effect = RuntimeError("yahoo down")
        self.assertIn("withheld for this date", _income(ticker_obj, "2026-07-17"))

    def test_nothing_announced_yet_withholds(self):
        data = pd.DataFrame({c: [100.0] for c in _QUARTERS[:1]})
        report = _income(_ticker(_ICICIBANK_LIKE_EARNINGS, quarterly_income_stmt=data), "2026-07-17")
        self.assertIn("withheld for this date", report)


@pytest.mark.unit
class LiveRunAndProfileTests(unittest.TestCase):
    def test_live_run_serves_every_period_without_the_calendar(self):
        data = pd.DataFrame({c: [100.0] for c in _QUARTERS})
        ticker_obj = _ticker(_ICICIBANK_LIKE_EARNINGS, quarterly_income_stmt=data)
        report = _income(ticker_obj, date.today().isoformat())
        self.assertIn("2026-06-30", report)
        ticker_obj.get_earnings_dates.assert_not_called()

    def test_past_run_withholds_the_live_profile_entirely(self):
        # Supersedes the fork's field-level embargo: even fields our old list
        # kept (market cap, 52-week range) move with today's quote.
        with mock.patch.object(fundamentals.yf, "Ticker") as ticker_cls:
            report = fundamentals.get_fundamentals("ICICIBANK.NS", "2026-07-17")
        self.assertIn("withheld for this date", report)
        ticker_cls.assert_not_called()  # guarded before any request


if __name__ == "__main__":
    unittest.main()
