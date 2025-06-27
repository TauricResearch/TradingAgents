"""
Time Series Cache System for Financial Data
Handles intelligent caching of financial API data with time series optimization
"""

import os
import sqlite3
import pandas as pd
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Union
from pathlib import Path
import pickle
from dataclasses import dataclass
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataType(Enum):
    """Supported data types for caching"""
    OHLCV = "ohlcv"           # Open, High, Low, Close, Volume data
    NEWS = "news"             # News articles
    FUNDAMENTALS = "fundamentals"  # Financial statements
    INDICATORS = "indicators"  # Technical indicators
    INSIDER = "insider"       # Insider transactions
    SENTIMENT = "sentiment"   # Sentiment data
    ECONOMIC = "economic"     # Economic indicators


@dataclass
class CacheEntry:
    """Represents a cached data entry"""
    symbol: str
    data_type: DataType
    start_date: datetime
    end_date: datetime
    cache_path: str
    last_updated: datetime
    metadata: Dict[str, Any]


class TimeSeriesCache:
    """
    Intelligent time series cache for financial data
    
    Features:
    - Detects overlapping date ranges to minimize API calls
    - Handles multiple data types (OHLCV, news, fundamentals, etc.)
    - Stores data in efficient time-indexed formats
    - Supports both CSV and SQLite storage
    - Provides cache statistics and management
    """
    
    def __init__(self, cache_dir: str = None):
        """Initialize the time series cache"""
        if cache_dir is None:
            from .config import get_config
            config = get_config()
            cache_dir = os.path.join(config.get("data_cache_dir", "data_cache"), "time_series")
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize cache database
        self.db_path = self.cache_dir / "cache_index.db"
        self._init_database()
        
        # Cache statistics
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls_saved": 0,
            "data_merged": 0
        }
        
    def _init_database(self):
        """Initialize SQLite database for cache management"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    cache_path TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    metadata TEXT,
                    UNIQUE(symbol, data_type, start_date, end_date)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_type_date 
                ON cache_entries(symbol, data_type, start_date, end_date)
            """)
            
    def _generate_cache_key(self, symbol: str, data_type: DataType, 
                          start_date: datetime, end_date: datetime, **kwargs) -> str:
        """Generate unique cache key for data"""
        key_data = f"{symbol}_{data_type.value}_{start_date.date()}_{end_date.date()}"
        if kwargs:
            key_data += "_" + "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()[:16]
    
    def _get_cache_path(self, symbol: str, data_type: DataType, cache_key: str) -> Path:
        """Get cache file path"""
        type_dir = self.cache_dir / data_type.value
        type_dir.mkdir(exist_ok=True)
        return type_dir / f"{symbol}_{cache_key}.parquet"
    
    def check_cache_coverage(self, symbol: str, data_type: DataType, 
                           start_date: datetime, end_date: datetime) -> Tuple[List[Tuple[datetime, datetime]], List[CacheEntry]]:
        """
        Check what date ranges are already cached and what gaps need to be filled
        
        Returns:
            - List of date ranges that need to be fetched from API
            - List of existing cache entries that cover parts of the requested range
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT symbol, data_type, start_date, end_date, cache_path, last_updated, metadata
                FROM cache_entries 
                WHERE symbol = ? AND data_type = ? 
                AND end_date >= ? AND start_date <= ?
                ORDER BY start_date
            """, (symbol, data_type.value, start_date.isoformat(), end_date.isoformat()))
            
            cached_entries = []
            for row in cursor.fetchall():
                entry = CacheEntry(
                    symbol=row[0],
                    data_type=DataType(row[1]),
                    start_date=datetime.fromisoformat(row[2]),
                    end_date=datetime.fromisoformat(row[3]),
                    cache_path=row[4],
                    last_updated=datetime.fromisoformat(row[5]),
                    metadata=json.loads(row[6]) if row[6] else {}
                )
                cached_entries.append(entry)
        
        if not cached_entries:
            return [(start_date, end_date)], []
        
        # Find gaps in coverage
        gaps = []
        current_start = start_date
        
        for entry in cached_entries:
            entry_start = max(entry.start_date, start_date)
            entry_end = min(entry.end_date, end_date)
            
            # Gap before this entry
            if current_start < entry_start:
                gaps.append((current_start, entry_start - timedelta(days=1)))
            
            current_start = max(current_start, entry_end + timedelta(days=1))
        
        # Gap after last entry
        if current_start <= end_date:
            gaps.append((current_start, end_date))
        
        return gaps, cached_entries
    
    def get_cached_data(self, symbol: str, data_type: DataType, 
                       start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """Retrieve cached data for the specified date range"""
        gaps, cached_entries = self.check_cache_coverage(symbol, data_type, start_date, end_date)
        
        if gaps:  # Has gaps, can't return complete cached data
            return None
        
        if not cached_entries:
            return None
        
        # Load and combine all relevant cached data
        dfs = []
        for entry in cached_entries:
            try:
                cache_path = Path(entry.cache_path)
                if cache_path.exists():
                    df = pd.read_parquet(cache_path)
                    
                    # Filter to requested date range
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
                    elif 'timestamp' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]
                    
                    dfs.append(df)
                    
            except Exception as e:
                logger.warning(f"Failed to load cached data from {entry.cache_path}: {e}")
                continue
        
        if not dfs:
            return None
        
        # Combine dataframes
        combined_df = pd.concat(dfs, ignore_index=True)
        
        # Remove duplicates based on date/timestamp
        date_col = 'date' if 'date' in combined_df.columns else 'timestamp'
        if date_col in combined_df.columns:
            combined_df = combined_df.drop_duplicates(subset=[date_col]).sort_values(date_col)
        
        self.stats["cache_hits"] += 1
        return combined_df
    
    def cache_data(self, symbol: str, data_type: DataType, data: pd.DataFrame,
                  start_date: datetime, end_date: datetime, **metadata) -> str:
        """Cache data with time series optimization"""
        
        # Ensure data has proper date column
        date_col = None
        for col in ['date', 'timestamp', 'Date', 'Timestamp']:
            if col in data.columns:
                date_col = col
                break
        
        if date_col is None:
            raise ValueError("Data must have a date/timestamp column")
        
        # Standardize date column
        data[date_col] = pd.to_datetime(data[date_col])
        
        # Generate cache key
        cache_key = self._generate_cache_key(symbol, data_type, start_date, end_date, **metadata)
        cache_path = self._get_cache_path(symbol, data_type, cache_key)
        
        # Save data to parquet for efficiency
        try:
            data.to_parquet(cache_path, index=False)
            
            # Update database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cache_entries 
                    (symbol, data_type, start_date, end_date, cache_path, last_updated, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol, 
                    data_type.value,
                    start_date.isoformat(),
                    end_date.isoformat(),
                    str(cache_path),
                    datetime.now().isoformat(),
                    json.dumps(metadata)
                ))
                
            logger.info(f"Cached {len(data)} records for {symbol} {data_type.value} ({start_date.date()} to {end_date.date()})")
            return str(cache_path)
            
        except Exception as e:
            logger.error(f"Failed to cache data: {e}")
            raise
    
    def fetch_with_cache(self, symbol: str, data_type: DataType, 
                        start_date: datetime, end_date: datetime,
                        fetch_function, **fetch_kwargs) -> pd.DataFrame:
        """
        Fetch data with intelligent caching
        
        Args:
            symbol: Symbol to fetch
            data_type: Type of data
            start_date, end_date: Date range
            fetch_function: Function to call for API data (should return DataFrame)
            **fetch_kwargs: Additional arguments for fetch function
        """
        
        # Check what's already cached
        gaps, cached_entries = self.check_cache_coverage(symbol, data_type, start_date, end_date)
        
        if not gaps:
            # Everything is cached
            cached_data = self.get_cached_data(symbol, data_type, start_date, end_date)
            if cached_data is not None:
                logger.info(f"Cache hit: {symbol} {data_type.value} ({start_date.date()} to {end_date.date()})")
                return cached_data
        
        # Need to fetch some data
        self.stats["cache_misses"] += 1
        
        # Fetch missing data
        new_data_frames = []
        for gap_start, gap_end in gaps:
            logger.info(f"Fetching {symbol} {data_type.value} from API: {gap_start.date()} to {gap_end.date()}")
            
            try:
                # Call the provided fetch function
                gap_data = fetch_function(symbol, gap_start, gap_end, **fetch_kwargs)
                
                if gap_data is not None and not gap_data.empty:
                    new_data_frames.append(gap_data)
                    
                    # Cache the new data
                    self.cache_data(symbol, data_type, gap_data, gap_start, gap_end, **fetch_kwargs)
                    
            except Exception as e:
                logger.error(f"Failed to fetch data for gap {gap_start} to {gap_end}: {e}")
                continue
        
        # Combine cached and new data
        all_data_frames = []
        
        # Add cached data
        for entry in cached_entries:
            try:
                cached_df = pd.read_parquet(entry.cache_path)
                # Filter to requested range
                date_col = 'date' if 'date' in cached_df.columns else 'timestamp'
                if date_col in cached_df.columns:
                    cached_df[date_col] = pd.to_datetime(cached_df[date_col])
                    cached_df = cached_df[
                        (cached_df[date_col] >= start_date) & 
                        (cached_df[date_col] <= end_date)
                    ]
                all_data_frames.append(cached_df)
            except Exception as e:
                logger.warning(f"Failed to load cached data: {e}")
        
        # Add new data
        all_data_frames.extend(new_data_frames)
        
        if not all_data_frames:
            return pd.DataFrame()
        
        # Combine and deduplicate
        result_df = pd.concat(all_data_frames, ignore_index=True)
        date_col = 'date' if 'date' in result_df.columns else 'timestamp'
        if date_col in result_df.columns:
            result_df = result_df.drop_duplicates(subset=[date_col]).sort_values(date_col)
        
        self.stats["api_calls_saved"] += len(cached_entries)
        return result_df
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cache_entries")
            total_entries = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT data_type, COUNT(*) FROM cache_entries GROUP BY data_type")
            by_type = dict(cursor.fetchall())
        
        # Calculate cache directory size
        total_size = sum(f.stat().st_size for f in self.cache_dir.rglob("*") if f.is_file())
        
        return {
            "total_cache_entries": total_entries,
            "entries_by_type": by_type,
            "cache_size_mb": total_size / (1024 * 1024),
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["cache_misses"],
            "hit_ratio": self.stats["cache_hits"] / max(1, self.stats["cache_hits"] + self.stats["cache_misses"]),
            "api_calls_saved": self.stats["api_calls_saved"]
        }
    
    def clear_cache(self, symbol: str = None, data_type: DataType = None, 
                   older_than_days: int = None):
        """Clear cache entries based on criteria"""
        conditions = []
        params = []
        
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
            
        if data_type:
            conditions.append("data_type = ?")
            params.append(data_type.value)
            
        if older_than_days:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            conditions.append("last_updated < ?")
            params.append(cutoff_date.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        with sqlite3.connect(self.db_path) as conn:
            # Get paths of files to delete
            cursor = conn.execute(f"SELECT cache_path FROM cache_entries WHERE {where_clause}", params)
            paths_to_delete = [row[0] for row in cursor.fetchall()]
            
            # Delete files
            for path in paths_to_delete:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to delete cache file {path}: {e}")
            
            # Delete database entries
            cursor = conn.execute(f"DELETE FROM cache_entries WHERE {where_clause}", params)
            deleted_count = cursor.rowcount
            
        logger.info(f"Cleared {deleted_count} cache entries")
        return deleted_count


# Global cache instance
_cache_instance = None

def get_cache() -> TimeSeriesCache:
    """Get or create the global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = TimeSeriesCache()
    return _cache_instance


# Convenience functions for different data types
def fetch_ohlcv_with_cache(symbol: str, start_date: datetime, end_date: datetime, 
                          fetch_function, **kwargs) -> pd.DataFrame:
    """Fetch OHLCV data with caching"""
    cache = get_cache()
    return cache.fetch_with_cache(symbol, DataType.OHLCV, start_date, end_date, fetch_function, **kwargs)


def fetch_news_with_cache(symbol: str, start_date: datetime, end_date: datetime,
                         fetch_function, **kwargs) -> pd.DataFrame:
    """Fetch news data with caching"""
    cache = get_cache()
    return cache.fetch_with_cache(symbol, DataType.NEWS, start_date, end_date, fetch_function, **kwargs)


def fetch_fundamentals_with_cache(symbol: str, start_date: datetime, end_date: datetime,
                                 fetch_function, **kwargs) -> pd.DataFrame:
    """Fetch fundamentals data with caching"""
    cache = get_cache()
    return cache.fetch_with_cache(symbol, DataType.FUNDAMENTALS, start_date, end_date, fetch_function, **kwargs)


if __name__ == "__main__":
    # Example usage and testing
    cache = TimeSeriesCache()
    print("Cache statistics:", cache.get_cache_stats()) 