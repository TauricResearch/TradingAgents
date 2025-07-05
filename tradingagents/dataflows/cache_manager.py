#!/usr/bin/env python3
"""
Stock Data Cache Manager
Supports local caching of stock data to reduce API calls and improve response speed
"""

import os
import json
import pickle
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Union
import hashlib


class StockDataCache:
    """Stock Data Cache Manager - Supports optimized caching for US and Chinese stock data"""

    def __init__(self, cache_dir: str = None):
        """
        Initialize cache manager

        Args:
            cache_dir: Cache directory path, defaults to tradingagents/dataflows/data_cache
        """
        if cache_dir is None:
            # Get current file directory
            current_dir = Path(__file__).parent
            cache_dir = current_dir / "data_cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # Create subdirectories - categorized by market
        self.us_stock_dir = self.cache_dir / "us_stocks"
        self.china_stock_dir = self.cache_dir / "china_stocks"
        self.us_news_dir = self.cache_dir / "us_news"
        self.china_news_dir = self.cache_dir / "china_news"
        self.us_fundamentals_dir = self.cache_dir / "us_fundamentals"
        self.china_fundamentals_dir = self.cache_dir / "china_fundamentals"
        self.metadata_dir = self.cache_dir / "metadata"

        # Create all directories
        for dir_path in [self.us_stock_dir, self.china_stock_dir, self.us_news_dir,
                        self.china_news_dir, self.us_fundamentals_dir,
                        self.china_fundamentals_dir, self.metadata_dir]:
            dir_path.mkdir(exist_ok=True)

        # Cache configuration - different TTL settings for different markets
        self.cache_config = {
            'us_stock_data': {
                'ttl_hours': 2,  # US stock data cached for 2 hours (considering API limits)
                'max_files': 1000,
                'description': 'US stock historical data'
            },
            'china_stock_data': {
                'ttl_hours': 1,  # A-share data cached for 1 hour (high real-time requirement)
                'max_files': 1000,
                'description': 'A-share historical data'
            },
            'us_news': {
                'ttl_hours': 6,  # US stock news cached for 6 hours
                'max_files': 500,
                'description': 'US stock news data'
            },
            'china_news': {
                'ttl_hours': 4,  # A-share news cached for 4 hours
                'max_files': 500,
                'description': 'A-share news data'
            },
            'us_fundamentals': {
                'ttl_hours': 24,  # US stock fundamentals cached for 24 hours
                'max_files': 200,
                'description': 'US stock fundamentals data'
            },
            'china_fundamentals': {
                'ttl_hours': 12,  # A-share fundamentals cached for 12 hours
                'max_files': 200,
                'description': 'A-share fundamentals data'
            }
        }

        print(f"📁 Cache manager initialized, cache directory: {self.cache_dir}")
        print(f"🗄️ Database cache manager initialized")
        print(f"   US stock data: ✅ Configured")
        print(f"   A-share data: ✅ Configured")

    def _determine_market_type(self, symbol: str) -> str:
        """Determine market type based on stock symbol"""
        import re

        # Check if it's Chinese A-share (6-digit number)
        if re.match(r'^\d{6}$', str(symbol)):
            return 'china'
        else:
            return 'us'
    
    def _generate_cache_key(self, data_type: str, symbol: str, **kwargs) -> str:
        """Generate cache key"""
        # Create a string containing all parameters
        params_str = f"{data_type}_{symbol}"
        for key, value in sorted(kwargs.items()):
            params_str += f"_{key}_{value}"
        
        # Use MD5 to generate short unique identifier
        cache_key = hashlib.md5(params_str.encode()).hexdigest()[:12]
        return f"{symbol}_{data_type}_{cache_key}"
    
    def _get_cache_path(self, data_type: str, cache_key: str, file_format: str = "json", symbol: str = None) -> Path:
        """Get cache file path - supports market classification"""
        if symbol:
            market_type = self._determine_market_type(symbol)
        else:
            # Try to extract market type from cache key
            market_type = 'us' if not cache_key.startswith(('0', '1', '2', '3', '4', '5', '6', '7', '8', '9')) else 'china'

        # Select directory based on data type and market type
        if data_type == "stock_data":
            base_dir = self.china_stock_dir if market_type == 'china' else self.us_stock_dir
        elif data_type == "news":
            base_dir = self.china_news_dir if market_type == 'china' else self.us_news_dir
        elif data_type == "fundamentals":
            base_dir = self.china_fundamentals_dir if market_type == 'china' else self.us_fundamentals_dir
        else:
            base_dir = self.cache_dir

        return base_dir / f"{cache_key}.{file_format}"
    
    def _get_metadata_path(self, cache_key: str) -> Path:
        """Get metadata file path"""
        return self.metadata_dir / f"{cache_key}_meta.json"
    
    def _save_metadata(self, cache_key: str, metadata: Dict[str, Any]):
        """Save cache metadata"""
        metadata_path = self._get_metadata_path(cache_key)
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Failed to save metadata: {e}")
    
    def _load_metadata(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Load cache metadata"""
        metadata_path = self._get_metadata_path(cache_key)
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load metadata: {e}")
            return None

    def save_stock_data(self, symbol: str, data: Union[str, pd.DataFrame], 
                       start_date: str, end_date: str, data_source: str = "unknown") -> str:
        """
        Save stock data to cache

        Args:
            symbol: Stock symbol
            data: Stock data (string or DataFrame)
            start_date: Start date
            end_date: End date
            data_source: Data source name

        Returns:
            Cache key
        """
        try:
            # Generate cache key
            cache_key = self._generate_cache_key(
                "stock_data", symbol,
                start_date=start_date,
                end_date=end_date,
                data_source=data_source
            )

            # Determine file format and save data
            if isinstance(data, pd.DataFrame):
                # Save DataFrame as pickle for better performance
                cache_path = self._get_cache_path("stock_data", cache_key, "pkl", symbol)
                data.to_pickle(cache_path)
                data_type = "dataframe"
            else:
                # Save string data as JSON
                cache_path = self._get_cache_path("stock_data", cache_key, "json", symbol)
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump({"data": data}, f, ensure_ascii=False, indent=2)
                data_type = "string"

            # Save metadata
            market_type = self._determine_market_type(symbol)
            metadata = {
                "symbol": symbol,
                "data_type": data_type,
                "start_date": start_date,
                "end_date": end_date,
                "data_source": data_source,
                "market_type": market_type,
                "cache_time": datetime.now().isoformat(),
                "file_path": str(cache_path),
                "cache_key": cache_key
            }
            self._save_metadata(cache_key, metadata)

            print(f"💾 Stock data cached: {symbol} ({market_type.upper()}) -> {cache_key}")
            return cache_key

        except Exception as e:
            print(f"❌ Failed to save stock data cache: {e}")
            return None

    def load_stock_data(self, cache_key: str) -> Optional[Union[str, pd.DataFrame]]:
        """
        Load stock data from cache

        Args:
            cache_key: Cache key

        Returns:
            Stock data or None if not found
        """
        try:
            # Load metadata
            metadata = self._load_metadata(cache_key)
            if not metadata:
                print(f"⚠️ Cache metadata not found: {cache_key}")
                return None

            # Get file path
            cache_path = Path(metadata["file_path"])
            if not cache_path.exists():
                print(f"⚠️ Cache file not found: {cache_path}")
                return None

            # Load data based on type
            if metadata["data_type"] == "dataframe":
                data = pd.read_pickle(cache_path)
            else:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    data = json_data["data"]

            print(f"📖 Stock data loaded from cache: {metadata['symbol']} -> {cache_key}")
            return data

        except Exception as e:
            print(f"❌ Failed to load stock data from cache: {e}")
            return None

    def find_cached_stock_data(self, symbol: str, start_date: str, end_date: str, 
                              data_source: str = "unknown") -> Optional[str]:
        """
        Find cached stock data

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            data_source: Data source name

        Returns:
            Cache key if found, None otherwise
        """
        # Generate expected cache key
        cache_key = self._generate_cache_key(
            "stock_data", symbol,
            start_date=start_date,
            end_date=end_date,
            data_source=data_source
        )

        # Check if metadata exists
        metadata = self._load_metadata(cache_key)
        if metadata:
            cache_path = Path(metadata["file_path"])
            if cache_path.exists():
                return cache_key

        return None

    def is_cache_valid(self, cache_key: str, symbol: str = None, data_type: str = "stock_data") -> bool:
        """
        Check if cache is still valid

        Args:
            cache_key: Cache key
            symbol: Stock symbol (for market type determination)
            data_type: Data type

        Returns:
            True if cache is valid, False otherwise
        """
        try:
            # Load metadata
            metadata = self._load_metadata(cache_key)
            if not metadata:
                return False

            # Check if file exists
            cache_path = Path(metadata["file_path"])
            if not cache_path.exists():
                return False

            # Determine market type and get TTL
            if symbol:
                market_type = self._determine_market_type(symbol)
            else:
                market_type = metadata.get("market_type", "us")

            cache_type_key = f"{market_type}_{data_type}"
            if cache_type_key not in self.cache_config:
                cache_type_key = "us_stock_data"  # Default fallback

            ttl_hours = self.cache_config[cache_type_key]["ttl_hours"]

            # Check if cache has expired
            cache_time = datetime.fromisoformat(metadata["cache_time"])
            expiry_time = cache_time + timedelta(hours=ttl_hours)

            is_valid = datetime.now() < expiry_time
            if not is_valid:
                print(f"⏰ Cache expired: {cache_key} (cached at {cache_time}, TTL: {ttl_hours}h)")

            return is_valid

        except Exception as e:
            print(f"❌ Failed to check cache validity: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary containing cache statistics
        """
        try:
            stats = {
                "cache_dir": str(self.cache_dir),
                "total_files": 0,
                "total_size_mb": 0,
                "stock_data_count": 0,
                "news_count": 0,
                "fundamentals_count": 0,
                "us_data_count": 0,
                "china_data_count": 0
            }

            # Count files in each directory
            for dir_path in [self.us_stock_dir, self.china_stock_dir, self.us_news_dir,
                           self.china_news_dir, self.us_fundamentals_dir, 
                           self.china_fundamentals_dir, self.metadata_dir]:
                if dir_path.exists():
                    files = list(dir_path.glob("*"))
                    stats["total_files"] += len(files)
                    
                    # Calculate total size
                    for file_path in files:
                        if file_path.is_file():
                            stats["total_size_mb"] += file_path.stat().st_size / (1024 * 1024)

            # Count by data type
            if self.us_stock_dir.exists():
                stats["stock_data_count"] += len(list(self.us_stock_dir.glob("*")))
                stats["us_data_count"] += len(list(self.us_stock_dir.glob("*")))
            
            if self.china_stock_dir.exists():
                stats["stock_data_count"] += len(list(self.china_stock_dir.glob("*")))
                stats["china_data_count"] += len(list(self.china_stock_dir.glob("*")))

            if self.us_news_dir.exists():
                stats["news_count"] += len(list(self.us_news_dir.glob("*")))
                stats["us_data_count"] += len(list(self.us_news_dir.glob("*")))
            
            if self.china_news_dir.exists():
                stats["news_count"] += len(list(self.china_news_dir.glob("*")))
                stats["china_data_count"] += len(list(self.china_news_dir.glob("*")))

            if self.us_fundamentals_dir.exists():
                stats["fundamentals_count"] += len(list(self.us_fundamentals_dir.glob("*")))
                stats["us_data_count"] += len(list(self.us_fundamentals_dir.glob("*")))
            
            if self.china_fundamentals_dir.exists():
                stats["fundamentals_count"] += len(list(self.china_fundamentals_dir.glob("*")))
                stats["china_data_count"] += len(list(self.china_fundamentals_dir.glob("*")))

            # Round size to 2 decimal places
            stats["total_size_mb"] = round(stats["total_size_mb"], 2)

            return stats

        except Exception as e:
            print(f"❌ Failed to get cache statistics: {e}")
            return {"error": str(e)}

    def cleanup_expired_cache(self):
        """Clean up expired cache files"""
        try:
            cleaned_count = 0
            
            # Check all metadata files
            if self.metadata_dir.exists():
                for metadata_file in self.metadata_dir.glob("*_meta.json"):
                    try:
                        cache_key = metadata_file.stem.replace("_meta", "")
                        
                        # Load metadata
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                        
                        # Check if cache is expired
                        if not self.is_cache_valid(cache_key, metadata.get("symbol"), "stock_data"):
                            # Remove cache file
                            cache_path = Path(metadata["file_path"])
                            if cache_path.exists():
                                cache_path.unlink()
                            
                            # Remove metadata file
                            metadata_file.unlink()
                            cleaned_count += 1
                            print(f"🗑️ Cleaned expired cache: {cache_key}")
                    
                    except Exception as e:
                        print(f"⚠️ Failed to clean cache file {metadata_file}: {e}")
            
            print(f"✅ Cache cleanup completed, removed {cleaned_count} expired files")
            
        except Exception as e:
            print(f"❌ Failed to cleanup cache: {e}")


# Global cache instance
_global_cache = None

def get_cache(cache_dir: str = None):
    """
    Get global cache instance with intelligent cache selection

    This function will automatically choose between:
    1. Integrated cache (with database support) if available
    2. Traditional file cache as fallback

    Args:
        cache_dir: Cache directory path

    Returns:
        Cache instance (IntegratedCacheManager or StockDataCache)
    """
    global _global_cache
    if _global_cache is None:
        # Try to use integrated cache manager first
        try:
            from .integrated_cache import IntegratedCacheManager
            _global_cache = IntegratedCacheManager(cache_dir)
            print("🚀 Using integrated cache manager with database support")
        except ImportError:
            # Fallback to traditional cache
            _global_cache = StockDataCache(cache_dir)
            print("📁 Using traditional file cache")
        except Exception as e:
            # If integrated cache fails, fallback to traditional cache
            print(f"⚠️ Integrated cache initialization failed: {e}")
            print("📁 Falling back to traditional file cache")
            _global_cache = StockDataCache(cache_dir)
    return _global_cache


# Convenience functions
def save_stock_data(symbol: str, data: Union[str, pd.DataFrame], 
                   start_date: str, end_date: str, data_source: str = "unknown") -> str:
    """Save stock data to cache (convenience function)"""
    cache = get_cache()
    return cache.save_stock_data(symbol, data, start_date, end_date, data_source)


def load_stock_data(cache_key: str) -> Optional[Union[str, pd.DataFrame]]:
    """Load stock data from cache (convenience function)"""
    cache = get_cache()
    return cache.load_stock_data(cache_key)


def find_cached_stock_data(symbol: str, start_date: str, end_date: str, 
                          data_source: str = "unknown") -> Optional[str]:
    """Find cached stock data (convenience function)"""
    cache = get_cache()
    return cache.find_cached_stock_data(symbol, start_date, end_date, data_source)


if __name__ == "__main__":
    # Test the cache manager
    print("🧪 Testing Stock Data Cache Manager...")
    
    # Initialize cache
    cache = StockDataCache()
    
    # Test data
    test_data = "Sample stock data for AAPL"
    cache_key = cache.save_stock_data("AAPL", test_data, "2024-01-01", "2024-01-31", "test")
    
    # Load data
    loaded_data = cache.load_stock_data(cache_key)
    print(f"Loaded data: {loaded_data}")
    
    # Check cache validity
    is_valid = cache.is_cache_valid(cache_key, "AAPL")
    print(f"Cache valid: {is_valid}")
    
    # Get statistics
    stats = cache.get_cache_stats()
    print(f"Cache stats: {stats}")
    
    print("✅ Cache manager test completed!")
