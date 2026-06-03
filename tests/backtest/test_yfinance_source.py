import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_yfinance_source_supports_only_daily():
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    s = YFinanceSource()
    assert s.name == "yfinance"
    assert s.supports == {Resolution.DAILY}


@pytest.mark.unit
def test_yfinance_source_returns_bars(monkeypatch):
    """When yf.Ticker(...).history returns a DataFrame, we extract Close bars."""
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    import pandas as pd

    fake_index = pd.DatetimeIndex(
        [pd.Timestamp("2026-04-26"), pd.Timestamp("2026-04-27")]
    )
    fake_df = pd.DataFrame({"Close": [213.45, 214.10]}, index=fake_index)

    mock_history = MagicMock(return_value=fake_df)
    mock_ticker = MagicMock(history=mock_history)
    with patch("yfinance.Ticker", return_value=mock_ticker):
        s = YFinanceSource()
        bars = s.get_bars("AAPL", date(2026, 4, 26), date(2026, 4, 27),
                          Resolution.DAILY)

    assert bars.ticker == "AAPL"
    assert bars.source == "yfinance"
    assert len(bars.bars) == 2
    assert bars.bars[0][1] == pytest.approx(213.45)
    assert bars.bars[1][1] == pytest.approx(214.10)


@pytest.mark.unit
def test_yfinance_source_one_min_raises(monkeypatch):
    """ONE_MIN is unsupported; yfinance is limited to ~7 days at 1m."""
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    s = YFinanceSource()
    with pytest.raises(NotImplementedError):
        s.get_bars("AAPL", date(2026, 4, 26), date(2026, 4, 27),
                    Resolution.ONE_MIN)


@pytest.mark.unit
def test_yfinance_source_empty_dataframe_raises():
    """Empty history (delisted / future / vendor error) must raise."""
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    import pandas as pd

    mock_history = MagicMock(return_value=pd.DataFrame())
    mock_ticker = MagicMock(history=mock_history)
    with patch("yfinance.Ticker", return_value=mock_ticker):
        s = YFinanceSource()
        with pytest.raises(RuntimeError, match="empty"):
            s.get_bars("ZZZZ", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY)
