import pytest
from datetime import datetime, date


@pytest.mark.unit
def test_resolution_enum_values():
    from tradingagents.backtest.prices import Resolution
    assert Resolution.DAILY.value == "1d"
    assert Resolution.ONE_MIN.value == "1m"


@pytest.mark.unit
def test_bars_dataclass_round_trip():
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(
        ticker="AAPL",
        resolution=Resolution.DAILY,
        bars=[(datetime(2026, 4, 26), 213.45), (datetime(2026, 4, 27), 214.10)],
        source="yfinance",
    )
    assert b.ticker == "AAPL"
    assert b.resolution is Resolution.DAILY
    assert len(b.bars) == 2
    assert b.bars[0][1] == pytest.approx(213.45)
    assert b.source == "yfinance"


@pytest.mark.unit
def test_bars_is_frozen():
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(ticker="A", resolution=Resolution.DAILY, bars=[], source="x")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        b.ticker = "B"  # type: ignore


@pytest.mark.unit
def test_price_data_unavailable_is_exception():
    from tradingagents.backtest.prices import PriceDataUnavailable
    assert issubclass(PriceDataUnavailable, Exception)
    err = PriceDataUnavailable("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                                tried_sources=["yfinance", "polygon"])
    assert "AAPL" in str(err)
    assert err.tried_sources == ["yfinance", "polygon"]


@pytest.mark.unit
def test_price_source_protocol_has_required_attrs():
    """A class with name/supports/get_bars should satisfy the Protocol."""
    from tradingagents.backtest.prices import PriceSource, Resolution, Bars

    class FakeSource:
        name = "fake"
        supports = {Resolution.DAILY}
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution, bars=[], source=self.name)

    # Protocol is runtime-checkable in F2 — this should pass without raising.
    src: PriceSource = FakeSource()
    assert src.name == "fake"
    assert src.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY).source == "fake"


@pytest.mark.unit
def test_fallback_chain_returns_first_successful_source():
    from tradingagents.backtest.prices import (
        Bars, PriceFallbackChain, Resolution
    )
    from datetime import datetime as dt

    class Failing:
        name = "failing"
        supports = {Resolution.DAILY}
        def get_bars(self, *a, **kw):
            raise RuntimeError("simulated failure")

    class Working:
        name = "working"
        supports = {Resolution.DAILY}
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(dt(2026, 4, 26), 100.0)], source=self.name)

    chain = PriceFallbackChain([Failing(), Working()])
    result = chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                             Resolution.DAILY)
    assert result.source == "working"


@pytest.mark.unit
def test_fallback_chain_skips_sources_that_do_not_support_resolution():
    from tradingagents.backtest.prices import (
        Bars, PriceFallbackChain, Resolution
    )

    class DailyOnly:
        name = "daily_only"
        supports = {Resolution.DAILY}
        called = False
        def get_bars(self, *a, **kw):
            self.called = True
            raise AssertionError("should have been skipped")

    class MinuteCapable:
        name = "minute_capable"
        supports = {Resolution.ONE_MIN}
        def get_bars(self, ticker, start, end, resolution):
            from datetime import datetime as dt
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(dt(2026, 4, 26, 9, 30), 100.0)],
                        source=self.name)

    daily_only = DailyOnly()
    chain = PriceFallbackChain([daily_only, MinuteCapable()])
    chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 4, 26),
                    Resolution.ONE_MIN)
    assert daily_only.called is False


@pytest.mark.unit
def test_fallback_chain_raises_when_all_sources_fail():
    from tradingagents.backtest.prices import (
        PriceDataUnavailable, PriceFallbackChain, Resolution
    )

    class Failing:
        name = "f1"
        supports = {Resolution.DAILY}
        def get_bars(self, *a, **kw):
            raise RuntimeError("nope")

    class Failing2:
        name = "f2"
        supports = {Resolution.DAILY}
        def get_bars(self, *a, **kw):
            raise RuntimeError("also nope")

    chain = PriceFallbackChain([Failing(), Failing2()])
    with pytest.raises(PriceDataUnavailable) as exc_info:
        chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY)
    assert exc_info.value.tried_sources == ["f1", "f2"]


@pytest.mark.unit
def test_fallback_chain_empty_raises_immediately():
    from tradingagents.backtest.prices import (
        PriceDataUnavailable, PriceFallbackChain, Resolution
    )
    chain = PriceFallbackChain([])
    with pytest.raises(PriceDataUnavailable):
        chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY)
