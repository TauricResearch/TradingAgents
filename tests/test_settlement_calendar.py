"""Settlement measures the benchmark over the instrument's own holding window.

A crypto pair trades every day and its benchmark (SPY by default) trades on
weekdays, so the Nth bar of each series falls on a different date. Alpha has
to compare the two over the same span of the calendar, and the outcome must
be dated when the prices it waited for were out, the point-in-time cutoff for
lessons (#1251).
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import market as yahoo_market
from tradingagents.decision_log import TradingMemoryLog
from tradingagents.graph import settlement

# Crypto: one bar per calendar day, stamped at midnight UTC as Yahoo does.
BTC = pd.Series(
    [100.0 + i for i in range(14)],
    index=pd.date_range("2026-01-03", periods=14, freq="D", tz="UTC"),
)
# SPY: weekday sessions in New York. Flat to Thursday the 8th, then a rally
# after it that a five-day crypto window starting on the 3rd must not see.
SPY = pd.Series(
    {
        "2026-01-02": 400.0, "2026-01-05": 400.0, "2026-01-06": 400.0,
        "2026-01-07": 400.0, "2026-01-08": 404.0, "2026-01-09": 440.0,
        "2026-01-12": 480.0, "2026-01-13": 480.0, "2026-01-14": 480.0,
        "2026-01-15": 480.0, "2026-01-16": 480.0,
    }
)
SPY.index = pd.DatetimeIndex(SPY.index).tz_localize("America/New_York")
# A US stock on the same sessions as SPY.
NVDA = pd.Series(
    [100.0, 100.0, 101.0, 102.0, 103.0, 110.0, 120.0, 120.0, 120.0, 120.0, 120.0],
    index=SPY.index,
)

DECISION = "Rating: Buy\n\nExecutive summary: accumulate."


@pytest.fixture
def yahoo(monkeypatch):
    """Yahoo's daily history, honouring start (inclusive) and end (exclusive)."""
    series = {"BTC-USD": BTC, "SPY": SPY, "NVDA": NVDA}

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, start, end, **kwargs):
            closes = series[self.symbol]
            day = closes.index.tz_localize(None).normalize()
            keep = (day >= pd.Timestamp(start)) & (day < pd.Timestamp(end))
            return pd.DataFrame({"Close": closes[keep]})

    monkeypatch.setattr(yahoo_market.yf, "Ticker", FakeTicker)
    return series


def _log(tmp_path):
    return TradingMemoryLog({"memory_log_path": str(tmp_path / "trading_memory.md")})


def _reflector():
    reflector = MagicMock()
    reflector.reflect_on_final_decision.return_value = "Lesson."
    return reflector


def _settle(tmp_path, ticker, trade_date):
    log = _log(tmp_path)
    log.store_decision(ticker, trade_date, DECISION)
    reflector = _reflector()
    settlement.settle_pending(ticker, log, reflector, {"holding_period_days": 5})
    [entry] = log.load_entries()
    return entry, reflector


def test_crypto_weekend_decision_is_scored_against_the_same_days_of_spy(tmp_path, yahoo):
    # Saturday 3 Jan -> fifth bar after it is Thursday 8 Jan: BTC 100 -> 105.
    # SPY over the same days is its Friday close (400) to Thursday's (404).
    entry, reflector = _settle(tmp_path, "BTC-USD", "2026-01-03")

    assert entry["pending"] is False
    assert entry["resolved"] == "2026-01-08"
    assert entry["raw"] == "+5.0%"
    assert entry["alpha"] == "+4.0%"
    kwargs = reflector.reflect_on_final_decision.call_args.kwargs
    assert kwargs["alpha_return"] == pytest.approx(0.05 - 0.01)


def test_crypto_weekday_decision_ignores_spy_sessions_after_the_exit(tmp_path, yahoo):
    # Monday 5 Jan -> Saturday 10 Jan: BTC 102 -> 107. SPY's last close by
    # then is Friday the 9th (440), not the following Monday's 480.
    entry, _ = _settle(tmp_path, "BTC-USD", "2026-01-05")

    assert entry["raw"] == f"{(107 / 102 - 1) * 100:+.1f}%"
    assert entry["alpha"] == f"{((107 / 102 - 1) - (440 / 400 - 1)) * 100:+.1f}%"


def test_benchmark_not_yet_traded_through_the_exit_stays_pending(monkeypatch, tmp_path, yahoo):
    # Only SPY's sessions to Thursday 8 Jan are published: the crypto window
    # ending Saturday 10 Jan cannot be benchmarked yet, so it waits.
    monkeypatch.setitem(yahoo, "SPY", SPY[:"2026-01-08"])
    entry, reflector = _settle(tmp_path, "BTC-USD", "2026-01-05")

    assert entry["pending"] is True
    reflector.reflect_on_final_decision.assert_not_called()


def test_weekend_exit_lesson_is_not_visible_before_the_benchmark_confirms_it(
    monkeypatch, tmp_path, yahoo
):
    # Monday 5 Jan -> Saturday 10 Jan. With SPY published to Friday the 9th,
    # nothing yet shows that Friday's close ends the window, so the entry
    # waits; Monday the 12th's session settles it. The lesson therefore exists
    # only from the 12th, and a historical run dated Sunday the 11th
    # (create_run_state filters with as_of=trade_date) must not see it.
    log = _log(tmp_path)
    log.store_decision("BTC-USD", "2026-01-05", DECISION)
    config = {"holding_period_days": 5}

    monkeypatch.setitem(yahoo, "SPY", SPY[:"2026-01-09"])
    settlement.settle_pending("BTC-USD", log, _reflector(), config)
    [entry] = log.load_entries()
    assert entry["pending"] is True

    monkeypatch.setitem(yahoo, "SPY", SPY[:"2026-01-12"])
    settlement.settle_pending("BTC-USD", log, _reflector(), config)
    [entry] = log.load_entries()
    assert entry["pending"] is False

    assert log.get_past_context("BTC-USD", as_of="2026-01-10") == ""
    assert log.get_past_context("BTC-USD", as_of="2026-01-11") == ""
    assert "Lesson." in log.get_past_context("BTC-USD", as_of="2026-01-12")
    assert entry["resolved"] == "2026-01-12"
    # Friday's close still ends the benchmark window: +10%, not Monday's +20%.
    assert entry["alpha"] == f"{((107 / 102 - 1) - (440 / 400 - 1)) * 100:+.1f}%"


def test_stock_on_the_benchmark_calendar_is_unchanged(tmp_path, yahoo):
    # NVDA and SPY share sessions: Mon 5 Jan -> Mon 12 Jan, 100 -> 120 vs 400 -> 480.
    entry, _ = _settle(tmp_path, "NVDA", "2026-01-05")

    assert entry["resolved"] == "2026-01-12"
    assert entry["raw"] == "+20.0%"
    assert entry["alpha"] == "+0.0%"
