import pytest
from datetime import date, datetime
from unittest.mock import MagicMock


@pytest.mark.unit
def test_assert_no_lookahead_passes_when_all_bars_in_window():
    from tradingagents.backtest.strict_historical import assert_no_lookahead
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(
        ticker="AAPL",
        resolution=Resolution.DAILY,
        bars=[(datetime(2026, 4, 26), 213.0),
              (datetime(2026, 5, 26), 219.0)],
        source="yfinance",
    )
    # cutoff = end of window — bars within OK.
    assert_no_lookahead(b, cutoff=date(2026, 5, 26))


@pytest.mark.unit
def test_assert_no_lookahead_raises_on_future_bar():
    from tradingagents.backtest.strict_historical import (
        assert_no_lookahead, LookaheadDataError,
    )
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(
        ticker="AAPL",
        resolution=Resolution.DAILY,
        bars=[(datetime(2026, 4, 26), 213.0),
              (datetime(2026, 7, 1), 999.0)],   # past the cutoff
        source="evil",
    )
    with pytest.raises(LookaheadDataError) as exc:
        assert_no_lookahead(b, cutoff=date(2026, 5, 26))
    assert "AAPL" in str(exc.value)
    assert "evil" in str(exc.value)


@pytest.mark.unit
def test_strict_chain_wraps_and_asserts():
    """The StrictHistoricalChain returns bars iff every bar is in-window."""
    from tradingagents.backtest.strict_historical import (
        StrictHistoricalChain, LookaheadDataError,
    )
    from tradingagents.backtest.prices import Bars, Resolution

    class GoodInner:
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(datetime(2026, 4, 26), 100.0),
                              (datetime(2026, 5, 26), 110.0)],
                        source="yfinance")

    class CheatingInner:
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(datetime(2099, 1, 1), 999.0)],  # cheat
                        source="liar")

    good = StrictHistoricalChain(GoodInner(), cutoff=date(2026, 5, 26))
    assert good.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                          Resolution.DAILY).source == "yfinance"

    bad = StrictHistoricalChain(CheatingInner(), cutoff=date(2026, 5, 26))
    with pytest.raises(LookaheadDataError):
        bad.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                      Resolution.DAILY)
