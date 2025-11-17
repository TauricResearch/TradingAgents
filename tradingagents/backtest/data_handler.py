"""
Historical data management for backtesting.

This module handles loading, validating, and managing historical price data
for backtesting, ensuring data quality and preventing look-ahead bias.
"""

import logging
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
from decimal import Decimal

import pandas as pd
import numpy as np
import yfinance as yf
from tqdm import tqdm

from tradingagents.security.validators import validate_ticker, validate_date
from .config import BacktestConfig, DataSource
from .exceptions import (
    DataError,
    DataNotFoundError,
    DataQualityError,
    DataAlignmentError,
    LookAheadBiasError,
)


logger = logging.getLogger(__name__)


class HistoricalDataHandler:
    """
    Manages historical price data for backtesting.

    This class provides point-in-time data access, ensuring no look-ahead bias
    and handling data quality issues.

    Attributes:
        config: Backtest configuration
        data: Dictionary mapping tickers to DataFrames with OHLCV data
        current_time: Current simulation time (for look-ahead bias prevention)
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize the data handler.

        Args:
            config: Backtest configuration
        """
        self.config = config
        self.data: Dict[str, pd.DataFrame] = {}
        self.current_time: Optional[datetime] = None
        self._cache_dir = Path(config.cache_dir) if config.cache_dir else None

        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info("HistoricalDataHandler initialized")

    def load_data(
        self,
        tickers: Union[str, List[str]],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        validate: bool = True,
    ) -> None:
        """
        Load historical data for one or more tickers.

        Args:
            tickers: Ticker or list of tickers
            start_date: Start date (defaults to config start_date)
            end_date: End date (defaults to config end_date)
            validate: Whether to validate data quality

        Raises:
            DataNotFoundError: If data cannot be loaded
            DataQualityError: If data fails quality checks
        """
        if isinstance(tickers, str):
            tickers = [tickers]

        start_date = start_date or self.config.start_date
        end_date = end_date or self.config.end_date

        logger.info(f"Loading data for {len(tickers)} ticker(s) from {start_date} to {end_date}")

        for ticker in tqdm(tickers, desc="Loading data", disable=not self.config.progress_bar):
            # Validate ticker
            ticker = validate_ticker(ticker)

            # Check cache first
            if self.config.cache_data and self._cache_dir:
                cached_data = self._load_from_cache(ticker, start_date, end_date)
                if cached_data is not None:
                    self.data[ticker] = cached_data
                    logger.debug(f"Loaded {ticker} from cache")
                    continue

            # Load from source
            try:
                data = self._load_from_source(ticker, start_date, end_date)
            except Exception as e:
                logger.error(f"Failed to load data for {ticker}: {e}")
                raise DataNotFoundError(f"Could not load data for {ticker}: {e}")

            # Validate data quality
            if validate:
                self._validate_data(ticker, data)

            # Clean and prepare data
            data = self._prepare_data(data)

            # Store
            self.data[ticker] = data

            # Cache if enabled
            if self.config.cache_data and self._cache_dir:
                self._save_to_cache(ticker, data, start_date, end_date)

        logger.info(f"Successfully loaded data for {len(self.data)} ticker(s)")

    def _load_from_source(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Load data from the configured data source.

        Args:
            ticker: Ticker symbol
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with OHLCV data
        """
        if self.config.data_source == DataSource.YFINANCE:
            return self._load_from_yfinance(ticker, start_date, end_date)
        elif self.config.data_source == DataSource.CSV:
            return self._load_from_csv(ticker, start_date, end_date)
        else:
            raise DataError(f"Unsupported data source: {self.config.data_source}")

    def _load_from_yfinance(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """Load data from Yahoo Finance."""
        # Add buffer to account for data availability
        buffer_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")

        try:
            stock = yf.Ticker(ticker)
            data = stock.history(start=buffer_start, end=end_date, auto_adjust=False)

            if data.empty:
                raise DataNotFoundError(f"No data returned for {ticker}")

            # Standardize column names
            data.columns = [col.lower().replace(' ', '_') for col in data.columns]

            # Ensure we have required columns
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            if not all(col in data.columns for col in required_cols):
                raise DataQualityError(f"Missing required columns for {ticker}")

            return data

        except Exception as e:
            raise DataError(f"Error loading data from yfinance for {ticker}: {e}")

    def _load_from_csv(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """Load data from CSV file."""
        csv_path = Path(self.config.custom_params.get('csv_dir', 'data')) / f"{ticker}.csv"

        if not csv_path.exists():
            raise DataNotFoundError(f"CSV file not found: {csv_path}")

        try:
            data = pd.read_csv(csv_path, index_col=0, parse_dates=True)

            # Filter date range
            data = data[(data.index >= start_date) & (data.index <= end_date)]

            # Standardize column names
            data.columns = [col.lower().replace(' ', '_') for col in data.columns]

            return data

        except Exception as e:
            raise DataError(f"Error loading CSV for {ticker}: {e}")

    def _validate_data(self, ticker: str, data: pd.DataFrame) -> None:
        """
        Validate data quality.

        Args:
            ticker: Ticker symbol
            data: DataFrame to validate

        Raises:
            DataQualityError: If data fails validation
        """
        if data.empty:
            raise DataQualityError(f"Empty data for {ticker}")

        # Check for required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise DataQualityError(f"Missing columns for {ticker}: {missing_cols}")

        # Check for excessive missing data
        missing_pct = data[required_cols].isnull().sum() / len(data) * 100
        high_missing = missing_pct[missing_pct > 10]
        if not high_missing.empty:
            warnings.warn(
                f"High missing data percentage for {ticker}: {high_missing.to_dict()}",
                UserWarning
            )

        # Check for price anomalies
        for col in ['open', 'high', 'low', 'close']:
            if (data[col] <= 0).any():
                raise DataQualityError(f"Non-positive prices found in {col} for {ticker}")

        # Check OHLC relationship
        invalid_ohlc = (
            (data['high'] < data['low']) |
            (data['high'] < data['open']) |
            (data['high'] < data['close']) |
            (data['low'] > data['open']) |
            (data['low'] > data['close'])
        )

        if invalid_ohlc.any():
            warnings.warn(
                f"Invalid OHLC relationships found for {ticker} on {invalid_ohlc.sum()} days",
                UserWarning
            )

        # Check for suspicious price movements
        returns = data['close'].pct_change()
        extreme_returns = returns.abs() > 0.5  # 50% in one day
        if extreme_returns.any():
            warnings.warn(
                f"Extreme price movements (>50%) detected for {ticker} on {extreme_returns.sum()} days",
                UserWarning
            )

        logger.debug(f"Data validation passed for {ticker}")

    def _prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and prepare data for backtesting.

        Args:
            data: Raw data

        Returns:
            Cleaned data
        """
        # Ensure datetime index
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)

        # Sort by date
        data = data.sort_index()

        # Remove duplicates
        data = data[~data.index.duplicated(keep='first')]

        # Forward fill missing data (conservative approach)
        data = data.fillna(method='ffill')

        # Handle any remaining NaNs
        data = data.dropna()

        return data

    def _load_from_cache(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        Load data from cache if available.

        SECURITY: Uses Parquet format instead of pickle to prevent
        arbitrary code execution during deserialization.
        """
        cache_file = self._cache_dir / f"{ticker}_{start_date}_{end_date}.parquet"

        if cache_file.exists():
            try:
                return pd.read_parquet(cache_file)
            except Exception as e:
                logger.warning(f"Failed to load cache for {ticker}: {e}")

        return None

    def _save_to_cache(
        self,
        ticker: str,
        data: pd.DataFrame,
        start_date: str,
        end_date: str
    ) -> None:
        """
        Save data to cache.

        SECURITY: Uses Parquet format instead of pickle to prevent
        arbitrary code execution risks during deserialization.
        """
        cache_file = self._cache_dir / f"{ticker}_{start_date}_{end_date}.parquet"

        try:
            data.to_parquet(cache_file, compression='snappy', index=True)
            logger.debug(f"Cached data for {ticker}")
        except Exception as e:
            logger.warning(f"Failed to save cache for {ticker}: {e}")

    def get_data_at(
        self,
        ticker: str,
        timestamp: datetime,
        lookback: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get historical data up to a specific point in time.

        This method ensures no look-ahead bias by only returning data
        available at the specified timestamp.

        Args:
            ticker: Ticker symbol
            timestamp: Point in time
            lookback: Number of periods to look back (None = all available)

        Returns:
            DataFrame with historical data up to timestamp

        Raises:
            LookAheadBiasError: If timestamp is in the future
            DataNotFoundError: If ticker not loaded
        """
        if ticker not in self.data:
            raise DataNotFoundError(f"Data not loaded for {ticker}")

        if self.current_time and timestamp > self.current_time:
            raise LookAheadBiasError(
                f"Requested timestamp {timestamp} is in the future (current: {self.current_time})"
            )

        # Get data up to timestamp
        data = self.data[ticker]
        historical = data[data.index <= timestamp]

        if lookback:
            historical = historical.tail(lookback)

        return historical.copy()

    def get_price_at(
        self,
        ticker: str,
        timestamp: datetime,
        price_type: str = 'close'
    ) -> Decimal:
        """
        Get price at a specific point in time.

        Args:
            ticker: Ticker symbol
            timestamp: Point in time
            price_type: Type of price ('open', 'high', 'low', 'close')

        Returns:
            Price as Decimal

        Raises:
            DataNotFoundError: If data not available
        """
        data = self.get_data_at(ticker, timestamp, lookback=1)

        if data.empty:
            raise DataNotFoundError(f"No data available for {ticker} at {timestamp}")

        price = data.iloc[-1][price_type]
        return Decimal(str(price))

    def set_current_time(self, timestamp: datetime) -> None:
        """
        Set the current simulation time.

        This is critical for preventing look-ahead bias.

        Args:
            timestamp: Current simulation timestamp
        """
        if self.current_time and timestamp < self.current_time:
            logger.warning(f"Time moving backwards: {self.current_time} -> {timestamp}")

        self.current_time = timestamp
        logger.debug(f"Current time set to {timestamp}")

    def align_data(
        self,
        tickers: Optional[List[str]] = None,
        method: str = 'inner'
    ) -> pd.DataFrame:
        """
        Align data across multiple tickers.

        Args:
            tickers: List of tickers to align (None = all loaded)
            method: Alignment method ('inner', 'outer', 'left', 'right')

        Returns:
            DataFrame with aligned close prices

        Raises:
            DataAlignmentError: If alignment fails
        """
        if tickers is None:
            tickers = list(self.data.keys())

        if not tickers:
            raise DataAlignmentError("No tickers to align")

        try:
            # Get close prices for all tickers
            prices = pd.DataFrame()

            for ticker in tickers:
                if ticker not in self.data:
                    raise DataNotFoundError(f"Data not loaded for {ticker}")

                prices[ticker] = self.data[ticker]['close']

            # Align using specified method
            if method == 'inner':
                prices = prices.dropna()
            elif method == 'outer':
                prices = prices.fillna(method='ffill').fillna(method='bfill')
            elif method in ['left', 'right']:
                raise NotImplementedError(f"Alignment method '{method}' not implemented")
            else:
                raise ValueError(f"Unknown alignment method: {method}")

            logger.info(f"Aligned {len(tickers)} tickers with {len(prices)} periods")
            return prices

        except Exception as e:
            raise DataAlignmentError(f"Failed to align data: {e}")

    def get_trading_days(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DatetimeIndex:
        """
        Get trading days in the backtest period.

        Args:
            start_date: Start date (defaults to config start_date)
            end_date: End date (defaults to config end_date)

        Returns:
            DatetimeIndex of trading days
        """
        start_date = start_date or self.config.start_date
        end_date = end_date or self.config.end_date

        if not self.data:
            raise DataError("No data loaded")

        # Use first ticker's index as reference
        reference_ticker = list(self.data.keys())[0]
        all_dates = self.data[reference_ticker].index

        # Filter to date range
        trading_days = all_dates[
            (all_dates >= start_date) & (all_dates <= end_date)
        ]

        return trading_days

    def check_survivor_bias(self, tickers: List[str]) -> None:
        """
        Warn if using current constituents for historical backtest.

        Args:
            tickers: List of tickers being tested
        """
        warnings.warn(
            "SURVIVOR BIAS WARNING: Ensure the ticker list represents "
            "securities that existed throughout the backtest period. "
            "Using current index constituents for historical backtests "
            "can lead to survivorship bias.",
            UserWarning
        )
        logger.warning("Survivor bias check performed")

    def get_corporate_actions(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get corporate actions (splits, dividends) for a ticker.

        Args:
            ticker: Ticker symbol
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with corporate actions
        """
        if ticker not in self.data:
            raise DataNotFoundError(f"Data not loaded for {ticker}")

        # For yfinance, dividends and splits are included in history
        start_date = start_date or self.config.start_date
        end_date = end_date or self.config.end_date

        try:
            stock = yf.Ticker(ticker)

            # Get splits and dividends
            splits = stock.splits
            dividends = stock.dividends

            # Filter date range
            if not splits.empty:
                splits = splits[(splits.index >= start_date) & (splits.index <= end_date)]

            if not dividends.empty:
                dividends = dividends[(dividends.index >= start_date) & (dividends.index <= end_date)]

            # Combine into single DataFrame
            actions = pd.DataFrame()
            if not splits.empty:
                actions['splits'] = splits
            if not dividends.empty:
                actions['dividends'] = dividends

            return actions

        except Exception as e:
            logger.warning(f"Failed to get corporate actions for {ticker}: {e}")
            return pd.DataFrame()

    def summary(self) -> Dict[str, Any]:
        """
        Get summary of loaded data.

        Returns:
            Dictionary with data summary
        """
        if not self.data:
            return {"tickers": 0, "message": "No data loaded"}

        summary_dict = {
            "tickers": len(self.data),
            "ticker_list": list(self.data.keys()),
        }

        for ticker, data in self.data.items():
            summary_dict[ticker] = {
                "start_date": str(data.index.min().date()),
                "end_date": str(data.index.max().date()),
                "periods": len(data),
                "missing_data_pct": data.isnull().sum().sum() / (len(data) * len(data.columns)) * 100,
            }

        return summary_dict
