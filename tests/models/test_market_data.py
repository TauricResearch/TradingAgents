from datetime import datetime, date
from decimal import Decimal

import pytest

from tradingagents.models.market_data import (
    OHLCVBar,
    OHLCV,
    TechnicalIndicators,
    MarketSnapshot,
    HistoricalDataRequest,
    HistoricalDataResponse,
)


class TestOHLCVBar:
    def test_valid_bar(self):
        bar = OHLCVBar(
            timestamp=datetime(2024, 1, 15, 9, 30),
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("99.00"),
            close=Decimal("103.50"),
            volume=1000000,
        )
        assert bar.open == Decimal("100.00")
        assert bar.high == Decimal("105.00")
        assert bar.volume == 1000000

    def test_bar_with_adjusted_close(self):
        bar = OHLCVBar(
            timestamp=datetime(2024, 1, 15),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("103"),
            volume=1000000,
            adjusted_close=Decimal("102.50"),
        )
        assert bar.adjusted_close == Decimal("102.50")

    def test_invalid_negative_price(self):
        with pytest.raises(ValueError):
            OHLCVBar(
                timestamp=datetime(2024, 1, 15),
                open=Decimal("-100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=1000000,
            )

    def test_invalid_negative_volume(self):
        with pytest.raises(ValueError):
            OHLCVBar(
                timestamp=datetime(2024, 1, 15),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=-1000,
            )


class TestOHLCV:
    @pytest.fixture
    def sample_bars(self):
        return [
            OHLCVBar(
                timestamp=datetime(2024, 1, 15),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=1000000,
            ),
            OHLCVBar(
                timestamp=datetime(2024, 1, 16),
                open=Decimal("103"),
                high=Decimal("108"),
                low=Decimal("102"),
                close=Decimal("107"),
                volume=1200000,
            ),
            OHLCVBar(
                timestamp=datetime(2024, 1, 17),
                open=Decimal("107"),
                high=Decimal("110"),
                low=Decimal("105"),
                close=Decimal("109"),
                volume=900000,
            ),
        ]

    def test_ohlcv_creation(self, sample_bars):
        ohlcv = OHLCV(ticker="AAPL", bars=sample_bars)
        assert ohlcv.ticker == "AAPL"
        assert len(ohlcv.bars) == 3
        assert ohlcv.interval == "1d"
        assert ohlcv.currency == "USD"

    def test_start_end_dates(self, sample_bars):
        ohlcv = OHLCV(ticker="AAPL", bars=sample_bars)
        assert ohlcv.start_date == datetime(2024, 1, 15)
        assert ohlcv.end_date == datetime(2024, 1, 17)

    def test_empty_ohlcv(self):
        ohlcv = OHLCV(ticker="AAPL", bars=[])
        assert ohlcv.start_date is None
        assert ohlcv.end_date is None

    def test_get_bar(self, sample_bars):
        ohlcv = OHLCV(ticker="AAPL", bars=sample_bars)
        bar = ohlcv.get_bar(datetime(2024, 1, 16))
        assert bar is not None
        assert bar.close == Decimal("107")

    def test_get_bar_not_found(self, sample_bars):
        ohlcv = OHLCV(ticker="AAPL", bars=sample_bars)
        bar = ohlcv.get_bar(datetime(2024, 1, 20))
        assert bar is None

    def test_slice(self, sample_bars):
        ohlcv = OHLCV(ticker="AAPL", bars=sample_bars)
        sliced = ohlcv.slice(datetime(2024, 1, 15), datetime(2024, 1, 16))
        assert len(sliced.bars) == 2
        assert sliced.ticker == "AAPL"

    def test_invalid_ticker(self):
        with pytest.raises(ValueError):
            OHLCV(ticker="", bars=[])


class TestTechnicalIndicators:
    def test_valid_indicators(self):
        indicators = TechnicalIndicators(
            timestamp=datetime(2024, 1, 15),
            ticker="AAPL",
            sma_50=Decimal("150.00"),
            rsi_14=Decimal("65.5"),
            macd=Decimal("2.5"),
        )
        assert indicators.sma_50 == Decimal("150.00")
        assert indicators.rsi_14 == Decimal("65.5")

    def test_rsi_bounds(self):
        with pytest.raises(ValueError):
            TechnicalIndicators(
                timestamp=datetime(2024, 1, 15),
                ticker="AAPL",
                rsi_14=Decimal("150"),
            )

    def test_mfi_bounds(self):
        with pytest.raises(ValueError):
            TechnicalIndicators(
                timestamp=datetime(2024, 1, 15),
                ticker="AAPL",
                mfi_14=Decimal("-10"),
            )


class TestMarketSnapshot:
    def test_snapshot_change_calculation(self):
        bar = OHLCVBar(
            timestamp=datetime(2024, 1, 15),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("103"),
            volume=1000000,
        )
        snapshot = MarketSnapshot(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 15),
            bar=bar,
            prev_close=Decimal("100"),
        )
        assert snapshot.change == Decimal("3")
        assert snapshot.change_percent == Decimal("3")

    def test_snapshot_no_prev_close(self):
        bar = OHLCVBar(
            timestamp=datetime(2024, 1, 15),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("103"),
            volume=1000000,
        )
        snapshot = MarketSnapshot(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 15),
            bar=bar,
        )
        assert snapshot.change is None
        assert snapshot.change_percent is None


class TestHistoricalDataRequest:
    def test_valid_request(self):
        request = HistoricalDataRequest(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        assert request.ticker == "AAPL"
        assert request.include_indicators is True

    def test_invalid_date_range(self):
        with pytest.raises(ValueError):
            HistoricalDataRequest(
                ticker="AAPL",
                start_date=date(2024, 6, 30),
                end_date=date(2024, 1, 1),
            )
