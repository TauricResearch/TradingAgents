"""Tests for the deterministic market-data verification snapshot (#830/#881)."""

from __future__ import annotations

import ast

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.market as market
import tradingagents.dataflows.vendors.yahoo.snapshot as validator
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo.common import price_text


def _sample_ohlcv() -> pd.DataFrame:
    dates = pd.bdate_range("2026-04-01", "2026-05-20")
    closes = [100 + i for i in range(len(dates))]
    return pd.DataFrame({
        "Date": dates,
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1_000_000 + i for i in range(len(dates))],
    })


@pytest.mark.unit
class TestVerifiedSnapshot:
    def test_excludes_future_rows(self, monkeypatch):
        data = pd.concat([
            _sample_ohlcv(),
            pd.DataFrame({"Date": [pd.Timestamp("2026-06-01")], "Open": [999.0],
                          "High": [999.0], "Low": [999.0], "Close": [999.0], "Volume": [999]}),
        ], ignore_index=True)
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)

        snap = validator.build_verified_market_snapshot("COF", "2026-05-13")
        assert "Verified market data snapshot for COF" in snap
        assert "Requested analysis date: 2026-05-13" in snap
        assert "Latest trading row used: 2026-05-13" in snap
        assert "999.00" not in snap          # future row excluded
        assert "boll_lb" in snap             # indicators present

    def test_uses_previous_trading_day_when_date_is_weekend(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        # 2026-05-16 is a Saturday; latest row should be Fri 2026-05-15
        snap = validator.build_verified_market_snapshot("COF", "2026-05-16")
        assert "Latest trading row used: 2026-05-15" in snap
        assert "Recent verified closes" in snap

    def test_raises_when_no_rows_on_or_before_date(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        with pytest.raises(NoMarketDataError):
            validator.build_verified_market_snapshot("COF", "2020-01-01")

    def test_raises_on_empty_data(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: pd.DataFrame())
        with pytest.raises(NoMarketDataError):
            validator.build_verified_market_snapshot("COF", "2026-05-13")

    def test_look_back_window_capped_at_30(self, monkeypatch):
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        snap = validator.build_verified_market_snapshot("COF", "2026-05-20", look_back_days=999)
        # last-N closes table has at most 30 data rows
        close_rows = [ln for ln in snap.splitlines() if ln.startswith("| 2026-")]
        assert 0 < len(close_rows) <= 30


@pytest.mark.unit
class TestTool:
    def test_tool_delegates_to_builder(self, monkeypatch):
        from tradingagents.agents.tools import get_verified_market_snapshot
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: _sample_ohlcv())
        out = get_verified_market_snapshot.invoke(
            {"symbol": "COF", "curr_date": "2026-05-20"}
        )
        assert "Verified market data snapshot for COF" in out


@pytest.mark.unit
class TestPricesKeepTheirDigits:
    """A price prints with its significant digits: a sub-cent coin is not 0.00, a rate keeps its pips."""

    @pytest.mark.parametrize("value, text", [
        (0.00000503123456, "0.00000503123"),
        (1.123456, "1.12346"),
        (763.960022, "763.96"),
        (81074.1875, "81074.19"),
        (100.0, "100.00"),
        (-0.0012345678, "-0.00123457"),
        (0.0, "0.00"),
    ])
    def test_price_text(self, value, text):
        from tradingagents.dataflows.vendors.yahoo.common import price_text
        assert price_text(value) == text

    def test_the_snapshot_shows_a_sub_cent_close(self, monkeypatch):
        data = _sample_ohlcv()
        for col in ("Open", "High", "Low", "Close"):
            data[col] = data[col] * 0.0000001
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)
        text = validator.build_verified_market_snapshot("SHIB-USD", "2026-05-20")
        assert "| Close | 0.0000135 |" in text and "| Close | 0.00 |" not in text

    def test_the_price_table_shows_a_sub_cent_close(self, monkeypatch):
        from tradingagents.dataflows.vendors.yahoo import market

        days = pd.bdate_range("2026-05-11", "2026-05-15")
        frame = pd.DataFrame({"Open": 0.00000501, "High": 0.00000512, "Low": 0.00000499,
                              "Close": 0.00000503, "Volume": 10**9}, index=days)

        class _Ticker:
            def __init__(self, symbol):
                pass

            def history(self, **kwargs):
                return frame

        monkeypatch.setattr(market.yf, "Ticker", _Ticker)
        text = market.get_YFin_data_online("SHIB-USD", "2026-05-11", "2026-05-15")
        assert "0.00000503" in text and ",0.0," not in text


def _bars(count: int, start: str = "2026-01-05") -> pd.DataFrame:
    """``count`` consecutive weekday sessions whose closes are not a straight line."""
    dates = pd.bdate_range(start, periods=count)
    closes = [100 + i + (3 if i % 2 else -3) for i in range(count)]
    return pd.DataFrame({
        "Date": dates,
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1_000_000 + i for i in range(count)],
    })


def _row(snapshot: str, indicator: str) -> str:
    return next(ln for ln in snapshot.splitlines() if ln.startswith(f"| {indicator} |"))


@pytest.mark.unit
class TestIndicatorWarmup:
    """An N-session indicator is reported only once there are N sessions of history.

    stockstats starts each window with the rows it has (min_periods=1), so the
    "200 SMA" of a stock listed 60 sessions ago, or of a run dated near the
    start of the five-year price cache, was the mean of those 60 closes, and
    the snapshot told the model to treat it as the source of truth.
    """

    def test_a_200_session_average_is_not_reported_from_60_sessions(self, monkeypatch):
        data = _bars(60)
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)

        snap = validator.build_verified_market_snapshot("NEWCO", "2026-05-20")

        row = _row(snap, "close_200_sma")
        assert row == "| close_200_sma | N/A (needs 200 sessions, 60 available) |"
        assert price_text(data["Close"].mean()) not in row
        assert _row(snap, "close_50_sma") == (
            f"| close_50_sma | {price_text(data['Close'].tail(50).mean())} |"
        )

    def test_a_full_window_is_reported(self, monkeypatch):
        data = _bars(250)
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d, fill_gaps=True: data)

        snap = validator.build_verified_market_snapshot("OLDCO", "2026-12-31")

        expected = price_text(data["Close"].rolling(200).mean().iloc[-1])
        assert _row(snap, "close_200_sma") == f"| close_200_sma | {expected} |"

    def test_get_indicators_marks_sessions_before_the_window_fills(self, monkeypatch):
        data = _bars(55)
        monkeypatch.setattr(
            market, "load_ohlcv",
            lambda s, d, fill_gaps=True: data[data["Date"] <= pd.Timestamp(d)],
        )
        as_of = data["Date"].iloc[54].strftime("%Y-%m-%d")

        text = market.get_stock_stats_indicators_window("NEWCO", "close_50_sma", as_of, 10)

        lines = dict(ln.split(": ", 1) for ln in text.splitlines() if ln[:4].isdigit())
        sma = data["Close"].rolling(50).mean()
        shown = []
        for session, day in enumerate(data["Date"], start=1):
            value = lines.get(day.strftime("%Y-%m-%d"))
            if value is None:
                continue
            shown.append(session)
            if session < 50:
                assert value == f"N/A: needs 50 sessions of history, {session} available"
            else:
                assert float(value) == pytest.approx(sma.iloc[session - 1])
        assert shown == list(range(47, 56))  # ten calendar days back from session 55

    def test_every_served_indicator_names_the_sessions_it_needs(self):
        # The tool's own refusal lists the indicators it offers the model.
        with pytest.raises(ValueError) as unsupported:
            market.get_stock_stats_indicators_window("X", "not_an_indicator", "2026-05-20", 1)
        served = ast.literal_eval(str(unsupported.value).split("choose from: ", 1)[1])

        assert "close_200_sma" in served
        assert set(served) | set(validator.DEFAULT_SNAPSHOT_INDICATORS) <= set(market._SESSIONS_NEEDED)
