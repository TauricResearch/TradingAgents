"""
Crypto Data Loader
Loads historical crypto data for backtesting from CCXT or cached sources
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import ccxt
import os
import json


class CryptoDataLoader:
    """
    Load and manage historical cryptocurrency data for backtesting.

    Supports:
    - CCXT exchange data (live)
    - Cached CSV files
    - Multiple timeframes
    - Multiple symbols
    """

    def __init__(self, exchange_id: str = "binance", cache_dir: str = "./backtest_data"):
        """
        Initialize data loader.

        Args:
            exchange_id: Exchange name (binance, coinbase, kraken)
            cache_dir: Directory for caching downloaded data
        """
        self.exchange_id = exchange_id
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        # Initialize exchange
        try:
            exchange_class = getattr(ccxt, exchange_id)
            self.exchange = exchange_class({
                'enableRateLimit': True,
            })
            self.exchange.load_markets()
        except Exception as e:
            print(f"Warning: Could not initialize {exchange_id} exchange: {e}")
            self.exchange = None

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1d',
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for backtesting.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)
            since: Start date
            until: End date
            use_cache: Use cached data if available

        Returns:
            DataFrame with OHLCV data
        """
        # Check cache first
        cache_file = self._get_cache_filename(symbol, timeframe, since, until)
        if use_cache and os.path.exists(cache_file):
            print(f"Loading cached data from {cache_file}")
            return pd.read_csv(cache_file, parse_dates=['timestamp'], index_col='timestamp')

        if self.exchange is None:
            raise ValueError("Exchange not initialized. Cannot fetch live data.")

        # Convert dates to timestamps
        since_ts = int(since.timestamp() * 1000) if since else None
        until_ts = int(until.timestamp() * 1000) if until else None

        print(f"Fetching {symbol} data from {self.exchange_id}...")

        all_ohlcv = []
        current_since = since_ts

        # Fetch data in batches (exchanges have limits)
        while True:
            try:
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=current_since,
                    limit=1000  # Max per request
                )

                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)

                # Update since for next batch
                current_since = ohlcv[-1][0] + 1

                # Check if we've reached the end
                if until_ts and current_since >= until_ts:
                    break

                # Stop if we got less than requested (reached the end)
                if len(ohlcv) < 1000:
                    break

            except Exception as e:
                print(f"Error fetching data: {e}")
                break

        if not all_ohlcv:
            raise ValueError(f"No data fetched for {symbol}")

        # Convert to DataFrame
        df = pd.DataFrame(
            all_ohlcv,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )

        # Convert timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        # Filter by until date
        if until:
            df = df[df.index <= until]

        # Cache the data
        if use_cache:
            df.to_csv(cache_file)
            print(f"Cached data to {cache_file}")

        return df

    def load_multiple_symbols(
        self,
        symbols: List[str],
        timeframe: str = '1d',
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        use_cache: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Load data for multiple symbols.

        Args:
            symbols: List of trading pairs
            timeframe: Candle timeframe
            since: Start date
            until: End date
            use_cache: Use cached data

        Returns:
            Dictionary of symbol -> DataFrame
        """
        data = {}
        for symbol in symbols:
            try:
                df = self.fetch_ohlcv(symbol, timeframe, since, until, use_cache)
                data[symbol] = df
                print(f"✓ Loaded {len(df)} candles for {symbol}")
            except Exception as e:
                print(f"✗ Failed to load {symbol}: {e}")

        return data

    def get_price_at_time(self, df: pd.DataFrame, timestamp: datetime) -> Optional[float]:
        """
        Get price at specific timestamp.

        Args:
            df: OHLCV DataFrame
            timestamp: Target timestamp

        Returns:
            Close price at timestamp, or None if not found
        """
        if timestamp not in df.index:
            # Find nearest timestamp
            idx = df.index.searchsorted(timestamp)
            if idx >= len(df):
                return None
            timestamp = df.index[idx]

        return df.loc[timestamp, 'close']

    def get_price_range(
        self,
        df: pd.DataFrame,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame:
        """
        Get price data for a date range.

        Args:
            df: OHLCV DataFrame
            start: Start date
            end: End date

        Returns:
            Filtered DataFrame
        """
        return df[(df.index >= start) & (df.index <= end)]

    def calculate_returns(self, df: pd.DataFrame) -> pd.Series:
        """Calculate percentage returns."""
        return df['close'].pct_change()

    def calculate_volatility(self, df: pd.DataFrame, window: int = 30) -> float:
        """
        Calculate annualized volatility.

        Args:
            df: OHLCV DataFrame
            window: Rolling window size

        Returns:
            Annualized volatility
        """
        returns = self.calculate_returns(df)
        # Crypto trades 24/7, so 365 days
        return returns.std() * np.sqrt(365)

    def identify_market_cycles(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Identify bull/bear market cycles.

        Uses simple moving average crossover logic:
        - Bull market: Price > 200 MA
        - Bear market: Price < 200 MA

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with 'market_cycle' column
        """
        df = df.copy()

        # Calculate moving averages
        df['ma_50'] = df['close'].rolling(50).mean()
        df['ma_200'] = df['close'].rolling(200).mean()

        # Determine market cycle
        df['market_cycle'] = 'neutral'
        df.loc[df['close'] > df['ma_200'], 'market_cycle'] = 'bull'
        df.loc[df['close'] < df['ma_200'], 'market_cycle'] = 'bear'

        # Calculate drawdown from ATH
        df['ath'] = df['close'].cummax()
        df['drawdown_from_ath'] = (df['close'] - df['ath']) / df['ath']

        return df

    def get_historical_cycles(self, df: pd.DataFrame) -> List[Dict]:
        """
        Get historical bull/bear cycles with dates and performance.

        Args:
            df: OHLCV DataFrame with market_cycle column

        Returns:
            List of cycle dictionaries
        """
        df_with_cycles = self.identify_market_cycles(df)

        cycles = []
        current_cycle = None
        cycle_start = None

        for timestamp, row in df_with_cycles.iterrows():
            cycle_type = row['market_cycle']

            if cycle_type == 'neutral':
                continue

            if current_cycle is None:
                # Start first cycle
                current_cycle = cycle_type
                cycle_start = timestamp
                start_price = row['close']

            elif cycle_type != current_cycle:
                # Cycle changed
                end_price = row['close']
                cycle_return = (end_price - start_price) / start_price

                cycles.append({
                    'type': current_cycle,
                    'start_date': cycle_start,
                    'end_date': timestamp,
                    'duration_days': (timestamp - cycle_start).days,
                    'start_price': start_price,
                    'end_price': end_price,
                    'return': cycle_return,
                    'return_pct': cycle_return * 100
                })

                # Start new cycle
                current_cycle = cycle_type
                cycle_start = timestamp
                start_price = row['close']

        return cycles

    def _get_cache_filename(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[datetime],
        until: Optional[datetime]
    ) -> str:
        """Generate cache filename."""
        symbol_safe = symbol.replace('/', '_')
        since_str = since.strftime('%Y%m%d') if since else 'start'
        until_str = until.strftime('%Y%m%d') if until else 'end'

        return os.path.join(
            self.cache_dir,
            f"{self.exchange_id}_{symbol_safe}_{timeframe}_{since_str}_{until_str}.csv"
        )

    def clear_cache(self):
        """Clear all cached data files."""
        import shutil
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)
            os.makedirs(self.cache_dir)
        print(f"Cache cleared: {self.cache_dir}")


# Pre-defined market cycles for reference
CRYPTO_MARKET_CYCLES = {
    'BTC/USDT': [
        {
            'type': 'bull',
            'name': '2017 Bull Run',
            'start': '2017-01-01',
            'end': '2017-12-17',
            'peak_price': 19783,
            'notes': 'First major bull run, ICO boom'
        },
        {
            'type': 'bear',
            'name': '2018 Bear Market',
            'start': '2017-12-17',
            'end': '2018-12-15',
            'bottom_price': 3191,
            'notes': 'Crypto winter, -83% from peak'
        },
        {
            'type': 'bull',
            'name': '2020-2021 Bull Run',
            'start': '2020-03-13',
            'end': '2021-11-10',
            'peak_price': 68789,
            'notes': 'Institutional adoption, COVID stimulus'
        },
        {
            'type': 'bear',
            'name': '2022 Bear Market',
            'start': '2021-11-10',
            'end': '2022-11-21',
            'bottom_price': 15476,
            'notes': 'Fed rate hikes, Luna crash, FTX collapse'
        },
        {
            'type': 'bull',
            'name': '2023-2024 Recovery',
            'start': '2023-01-01',
            'end': '2024-03-14',
            'peak_price': 73737,
            'notes': 'ETF approval, halving anticipation'
        },
    ]
}
