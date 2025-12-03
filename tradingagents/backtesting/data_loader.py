import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd
import yfinance as yf
from stockstats import wrap

from tradingagents.models.market_data import (
    OHLCV,
    HistoricalDataRequest,
    HistoricalDataResponse,
    OHLCVBar,
    TechnicalIndicators,
)

logger = logging.getLogger(__name__)


class DataLoader:
    def __init__(self, cache_dir: str | None = None):
        self.cache_dir = cache_dir
        self._cache: dict[str, pd.DataFrame] = {}

    def load_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> OHLCV:
        ticker = ticker.upper()
        cache_key = f"{ticker}_{start_date}_{end_date}_{interval}"

        if cache_key in self._cache:
            df = self._cache[cache_key]
        else:
            df = self._fetch_from_yfinance(ticker, start_date, end_date, interval)
            self._cache[cache_key] = df

        bars = self._dataframe_to_bars(df)
        return OHLCV(ticker=ticker, bars=bars, interval=interval)

    def load_historical_data(
        self,
        request: HistoricalDataRequest,
    ) -> HistoricalDataResponse:
        ohlcv = self.load_ohlcv(
            request.ticker,
            request.start_date,
            request.end_date,
            request.interval,
        )

        indicators = []
        if request.include_indicators and ohlcv.bars:
            indicators = self._calculate_indicators(
                request.ticker,
                request.start_date,
                request.end_date,
            )

        return HistoricalDataResponse(
            request=request,
            ohlcv=ohlcv,
            indicators=indicators,
            source="yfinance",
        )

    def _fetch_from_yfinance(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        interval: str,
    ) -> pd.DataFrame:
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

        df = yf.download(
            ticker,
            start=start_str,
            end=end_str,
            interval=interval,
            multi_level_index=False,
            progress=False,
            auto_adjust=False,
        )

        if df.empty:
            logger.warning(
                "No data returned for %s from %s to %s", ticker, start_date, end_date
            )
            return pd.DataFrame()

        df = df.reset_index()
        return df

    def _dataframe_to_bars(self, df: pd.DataFrame) -> list[OHLCVBar]:
        if df.empty:
            return []

        bars = []
        for _, row in df.iterrows():
            timestamp = row.get("Date") or row.get("Datetime")
            if isinstance(timestamp, str):
                timestamp = pd.to_datetime(timestamp)
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if timestamp.tzinfo is not None:
                timestamp = timestamp.replace(tzinfo=None)

            bar = OHLCVBar(
                timestamp=timestamp,
                open=Decimal(str(round(row["Open"], 4))),
                high=Decimal(str(round(row["High"], 4))),
                low=Decimal(str(round(row["Low"], 4))),
                close=Decimal(str(round(row["Close"], 4))),
                volume=int(row["Volume"]),
                adjusted_close=Decimal(str(round(row["Adj Close"], 4)))
                if "Adj Close" in row
                else None,
            )
            bars.append(bar)

        return bars

    def _calculate_indicators(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[TechnicalIndicators]:
        lookback_start = start_date - timedelta(days=250)
        cache_key = f"{ticker}_{lookback_start}_{end_date}_1d"

        if cache_key in self._cache:
            df = self._cache[cache_key]
        else:
            df = self._fetch_from_yfinance(ticker, lookback_start, end_date, "1d")
            self._cache[cache_key] = df

        if df.empty:
            return []

        stock = wrap(df.copy())

        stock["close_20_sma"]
        stock["close_50_sma"]
        stock["close_200_sma"]
        stock["close_10_ema"]
        stock["close_20_ema"]
        stock["rsi_14"]
        stock["macd"]
        stock["macds"]
        stock["macdh"]
        stock["boll"]
        stock["boll_ub"]
        stock["boll_lb"]
        stock["atr_14"]
        stock["mfi_14"]

        indicators = []
        for _, row in stock.iterrows():
            timestamp = row.get("Date") or row.get("Datetime")
            if isinstance(timestamp, str):
                timestamp = pd.to_datetime(timestamp)
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if timestamp.tzinfo is not None:
                timestamp = timestamp.replace(tzinfo=None)

            if timestamp.date() < start_date or timestamp.date() > end_date:
                continue

            ind = TechnicalIndicators(
                timestamp=timestamp,
                ticker=ticker,
                sma_20=self._safe_decimal(row.get("close_20_sma")),
                sma_50=self._safe_decimal(row.get("close_50_sma")),
                sma_200=self._safe_decimal(row.get("close_200_sma")),
                ema_10=self._safe_decimal(row.get("close_10_ema")),
                ema_20=self._safe_decimal(row.get("close_20_ema")),
                rsi_14=self._safe_decimal(row.get("rsi_14")),
                macd=self._safe_decimal(row.get("macd")),
                macd_signal=self._safe_decimal(row.get("macds")),
                macd_histogram=self._safe_decimal(row.get("macdh")),
                bollinger_middle=self._safe_decimal(row.get("boll")),
                bollinger_upper=self._safe_decimal(row.get("boll_ub")),
                bollinger_lower=self._safe_decimal(row.get("boll_lb")),
                atr_14=self._safe_decimal(row.get("atr_14")),
                mfi_14=self._safe_decimal(row.get("mfi_14")),
            )
            indicators.append(ind)

        return indicators

    @staticmethod
    def _safe_decimal(value) -> Decimal | None:
        if value is None or pd.isna(value):
            return None
        return Decimal(str(round(float(value), 4)))

    def get_price_on_date(
        self,
        ticker: str,
        target_date: date,
        ohlcv: OHLCV | None = None,
    ) -> Decimal | None:
        if ohlcv is None:
            ohlcv = self.load_ohlcv(
                ticker, target_date - timedelta(days=5), target_date
            )

        target_datetime = datetime.combine(target_date, datetime.min.time())
        bar = ohlcv.get_bar(target_datetime)

        if bar:
            return bar.close

        for b in reversed(ohlcv.bars):
            if b.timestamp.date() <= target_date:
                return b.close

        return None

    def get_prices_dict(
        self,
        tickers: list[str],
        target_date: date,
    ) -> dict[str, Decimal]:
        prices = {}
        for ticker in tickers:
            price = self.get_price_on_date(ticker, target_date)
            if price is not None:
                prices[ticker] = price
        return prices

    def get_trading_days(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        ohlcv = self.load_ohlcv(ticker, start_date, end_date)
        return [bar.timestamp.date() for bar in ohlcv.bars]

    def clear_cache(self):
        self._cache.clear()
