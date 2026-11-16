"""Simulating a backtest's ratings as a portfolio, on fixed prices (no network)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.memory import TradingMemoryLog
from tradingagents.simulate import signals_from_log, simulate, target_weights

pytest.importorskip("vectorbt")

DAYS = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"])
CLOSE = pd.DataFrame({"NVDA": [100.0, 100.0, 110.0, 110.0, 121.0]}, index=DAYS)


def _log(tmp_path, rows):
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    for ticker, date, decision in rows:
        log.store_decision(ticker, date, decision)
    return tmp_path / "m.md"


@pytest.mark.unit
def test_a_rating_fills_on_the_first_bar_after_its_date(tmp_path):
    signals = signals_from_log(_log(tmp_path, [
        ("NVDA", "2026-01-05", "Rating: Buy\n\nx"),
        ("NVDA", "2026-01-06", "Rating: Hold\n\nx"),
        ("NVDA", "2026-01-07", "Rating: Sell\n\nx"),
    ]))
    size = target_weights(signals, CLOSE)

    assert size["NVDA"].tolist()[1] == 1.0          # Buy on the 5th fills on the 6th
    assert pd.isna(size["NVDA"].tolist()[2])        # Hold places no order
    assert size["NVDA"].tolist()[3] == 0.0          # Sell on the 7th fills on the 8th


@pytest.mark.unit
def test_the_portfolio_holds_between_buy_and_sell(tmp_path):
    log = _log(tmp_path, [
        ("NVDA", "2026-01-05", "Rating: Buy\n\nx"),
        ("NVDA", "2026-01-06", "Rating: Hold\n\nx"),
        ("NVDA", "2026-01-07", "Rating: Sell\n\nx"),
    ])
    pf = simulate(log, close=CLOSE, init_cash=10_000, fees=0.0)

    # Bought at 100 on the 6th, sold at 110 on the 8th; the rise to 121 is missed.
    assert pf.final_value()["NVDA"] == pytest.approx(11_000)


@pytest.mark.unit
def test_a_rating_with_no_later_bar_is_not_traded(tmp_path):
    signals = signals_from_log(_log(tmp_path, [("NVDA", "2026-01-09", "Rating: Buy\n\nx")]))
    assert target_weights(signals, CLOSE)["NVDA"].isna().all()


@pytest.mark.unit
def test_a_log_with_no_rated_decision_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no rated decisions"):
        simulate(_log(tmp_path, [("NVDA", "2026-01-05", "no rating here")]), close=CLOSE)
