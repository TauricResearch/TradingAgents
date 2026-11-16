import pandas as pd

from trader import bars


class Ticker:
    """Stands in for yf.Ticker: the daily series has the candles dated ``days``, or
    asking for it raises ``error``."""

    def __init__(self, days=(), error=None):
        self.days, self.error = list(days), error
        self.asked = []

    def __call__(self, symbol):
        self.symbol = symbol
        return self

    def history(self, **kwargs):
        self.asked.append(kwargs)
        if self.error:
            raise self.error
        index = pd.DatetimeIndex(self.days, tz="UTC")
        return pd.DataFrame({"Close": [80_000.0] * len(index)}, index=index)


def test_the_candle_is_published_once_the_daily_series_has_the_trade_date(monkeypatch):
    ticker = Ticker(["2026-11-11", "2026-11-12"])  # as Yahoo serves it just after midnight
    monkeypatch.setattr(bars.yf, "Ticker", ticker)
    assert not bars.published("BTC-USD", "2026-11-13")
    ticker.days.append("2026-11-13")
    assert bars.published("BTC-USD", "2026-11-13")
    assert ticker.symbol == "BTC-USD" and ticker.asked[-1]["interval"] == "1d"


def test_a_yahoo_that_cannot_be_asked_has_not_published(monkeypatch):
    monkeypatch.setattr(bars.yf, "Ticker", Ticker(error=ConnectionError("Host is down")))
    assert not bars.published("BTC-USD", "2026-11-13")
