# Market Data Fetching Analysis & MarketWatcher Design

This document details the analysis of the stock and benchmark data fetching mechanisms in the codebase and provides a detailed implementation design for the new `MarketWatcher` class.

---

## 1. Existing Market Data Fetching and Configuration Patterns

### 1.1 Configuration Mechanism
Market data provider configurations are defined in `tradingagents/default_config.py` as a dictionary named `DEFAULT_CONFIG`. It uses the function `_apply_env_overrides` to dynamically apply environment variable overrides (prefixed with `TRADINGAGENTS_`).

Key configuration fields:
*   **`data_vendors`**: Category-level default vendors for fetching data.
    ```python
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        ...
    }
    ```
*   **`tool_vendors`**: Specific overrides per-tool method (takes precedence over category-level).
*   **`benchmark_ticker`**: Used for benchmark overrides.
*   **`benchmark_map`**: Suffix-to-ticker map to resolve benchmark index automatically (e.g. `""` maps to `"SPY"` for US-listed tickers, `.NS` to `^NSEI` for India, etc.).

### 1.2 Vendor Selection and Routing
The core routing logic resides in `tradingagents/dataflows/interface.py`. Method calls to data tools are routed via `route_to_vendor(method, *args, **kwargs)`:
1.  It resolves the configured vendor list by checking `tool_vendors` and category-level configurations (`data_vendors`).
2.  It parses the vendor chain (e.g., `"yfinance,alpha_vantage"` to try them sequentially in case of rate-limiting/failures).
3.  It resolves the mapped vendor function from `VENDOR_METHODS`. For `"get_stock_data"`, the mapping is:
    *   `"yfinance"` $\rightarrow$ `get_YFin_data_online` (defined in `tradingagents/dataflows/y_finance.py`)
    *   `"alpha_vantage"` $\rightarrow$ `get_alpha_vantage_stock` (defined in `tradingagents/dataflows/alpha_vantage_stock.py`, alias for `get_stock`)
4.  It executes the function and handles exceptions like `VendorRateLimitError`, `VendorNotConfiguredError`, or `NoMarketDataError` gracefully, propagating appropriate sentinel messages if data is unavailable.

### 1.3 Data Provider Call Mechanics

#### A. Yahoo Finance (`yfinance`)
*   **Execution Location**: `tradingagents/dataflows/y_finance.py` and `tradingagents/dataflows/stockstats_utils.py`
*   **Direct Calls**:
    *   Uses `yf.Ticker(canonical)` to instantiate a ticker object.
    *   Calls `yf_retry(lambda: ticker.history(start=start_date, end=end_inclusive))` to fetch historical data.
    *   Uses `yf.download(...)` inside `load_ohlcv` for bulk historical fetches.
*   **Freshness / Look-ahead Controls**:
    *   To prevent look-ahead bias, it filters dataframe rows to exclude dates greater than the requested `curr_date`.
    *   `_assert_ohlcv_not_stale` (in `stockstats_utils.py`) rejects datasets where the latest available row is older than 10 calendar days relative to `curr_date` to prevent using stale datasets.

#### B. AlphaVantage
*   **Execution Location**: `tradingagents/dataflows/alpha_vantage_stock.py` and `tradingagents/dataflows/alpha_vantage_common.py`
*   **Direct Calls**:
    *   Pulls `ALPHA_VANTAGE_API_KEY` from the environment.
    *   Issues HTTP GET requests to `https://www.alphavantage.co/query` with required params (e.g., `function="TIME_SERIES_DAILY_ADJUSTED"`, `datatype="csv"`).
    *   Limits network hangs with a 30-second request timeout.
    *   Checks JSON responses for error/note strings to classify rate limits (`Information` or `Note` mentioning rate limit) vs authentication errors.
    *   Returns raw CSV data filtered by date range via `_filter_csv_by_date_range`.

---

## 2. MarketWatcher.fetch_snapshots Design

### 2.1 Pattern Selection
For implementing `MarketWatcher.fetch_snapshots(watchlist: list[str]) -> dict`, there are two patterns available in the codebase:

1.  **Option A: Leveraging `load_ohlcv` (Recommended)**
    *   **File**: `tradingagents/dataflows/stockstats_utils.py:125`
    *   **Pros**: This utility handles caching (writing/reading CSV files from `.tradingagents/cache`), symbol normalization, stale-data rejection, and look-ahead bias filtering automatically. Since it returns a clean `pd.DataFrame` with standard column names (`Open`, `High`, `Low`, `Close`, `Volume`), extracting data is simple and fast.
2.  **Option B: Using `route_to_vendor("get_stock_data", ...)`**
    *   **File**: `tradingagents/dataflows/interface.py:161`
    *   **Pros**: Respects user-configured overrides (`data_vendors["core_stock_apis"] = "alpha_vantage"`).
    *   **Cons**: Returns CSV strings that must be parsed using `pd.read_csv(io.StringIO(csv))` at the caller level. Different vendors format columns differently (e.g., AlphaVantage returns lowercase columns, Yahoo Finance returns uppercase columns). It also bypasses the core caching and staleness validations present in `load_ohlcv`.

**Conclusion**: Using `load_ohlcv` is the cleanest and most robust pattern for local/backtesting simulation data fetching. However, we should check `get_config()` to allow dynamically resolving the benchmark index (e.g., using `benchmark_ticker` or falling back to `"SPY"`).

---

### 2.2 Proposed Implementation Design

The class will be placed in `gemini_agent/watcher.py` (as specified in the `PROJECT.md` layout contract).

#### Importing Dependencies
```python
from datetime import datetime
import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.symbol_utils import NoMarketDataError
from tradingagents.dataflows.config import get_config
```

#### Class Structure & Signature
The class constructor should accept a configuration dictionary and an optional current execution date (useful for backtesting backpressure and liveness/staleness logic).

```python
class MarketWatcher:
    def __init__(self, config: dict = None, curr_date: str = None):
        """
        Initialize the MarketWatcher.
        
        Args:
            config (dict, optional): Agent config dictionary. Defaults to global config.
            curr_date (str, optional): Target analysis date in YYYY-MM-DD format.
                                       Defaults to current system date.
        """
        self.config = config or get_config()
        self.curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")

    def fetch_snapshots(self, watchlist: list[str]) -> dict:
        """
        Fetches daily market data snapshots for watchlist tickers and the SPY benchmark.
        
        Args:
            watchlist (list[str]): List of ticker symbols to fetch.
            
        Returns:
            dict: Ticker mapping to daily OHLCV snapshots.
        """
        # 1. Resolve benchmark index (default to SPY)
        benchmark = self.config.get("benchmark_ticker") or "SPY"
        
        # 2. Consolidate tickers to fetch, ensuring benchmark is included
        tickers_to_fetch = set(watchlist) | {benchmark}
        
        snapshots = {}
        for ticker in tickers_to_fetch:
            try:
                # 3. Call load_ohlcv using the existing cache-aware pattern
                df = load_ohlcv(ticker, self.curr_date)
                if df is None or df.empty:
                    continue
                
                # 4. Extract the last available trading row on or before self.curr_date
                # load_ohlcv automatically handles look-ahead filtering to <= self.curr_date
                latest_row = df.iloc[-1]
                
                snapshots[ticker] = {
                    "open": float(latest_row["Open"]),
                    "high": float(latest_row["High"]),
                    "low": float(latest_row["Low"]),
                    "close": float(latest_row["Close"]),
                    "volume": float(latest_row["Volume"]),
                    "date": pd.to_datetime(latest_row["Date"]).strftime("%Y-%m-%d")
                }
            except NoMarketDataError as e:
                # Log a warning when a ticker does not have data, but continue fetching others
                print(f"Warning: No market data available for ticker '{ticker}': {e}")
            except Exception as e:
                # Graceful handling of unexpected exceptions
                print(f"Error fetching snapshot for ticker '{ticker}': {e}")
                
        return snapshots
```

#### Output Structure Example
Calling `fetch_snapshots(["AAPL", "MSFT"])` returns:
```json
{
  "AAPL": {
    "open": 175.02,
    "high": 177.30,
    "low": 174.12,
    "close": 176.15,
    "volume": 72000000.0,
    "date": "2026-06-15"
  },
  "MSFT": {
    "open": 420.50,
    "high": 423.00,
    "low": 418.20,
    "close": 422.10,
    "volume": 21000000.0,
    "date": "2026-06-15"
  },
  "SPY": {
    "open": 500.20,
    "high": 502.10,
    "low": 498.50,
    "close": 501.50,
    "volume": 85000000.0,
    "date": "2026-06-15"
  }
}
```

---

## 3. Verification Method

Once implemented, the `MarketWatcher` implementation can be verified using the following unit test structure:

```python
import unittest
from unittest.mock import patch
import pandas as pd
from gemini_agent.watcher import MarketWatcher

class TestMarketWatcher(unittest.TestCase):
    @patch("gemini_agent.watcher.load_ohlcv")
    def test_fetch_snapshots_structure(self, mock_load_ohlcv):
        # Mock DataFrame returned by load_ohlcv
        mock_df = pd.DataFrame({
            "Date": [pd.Timestamp("2026-06-15")],
            "Open": [100.0],
            "High": [105.0],
            "Low": [95.0],
            "Close": [102.0],
            "Volume": [1000000]
        })
        mock_load_ohlcv.return_value = mock_df
        
        watcher = MarketWatcher(curr_date="2026-06-15")
        snapshots = watcher.fetch_snapshots(["AAPL"])
        
        # Verify both target ticker and benchmark SPY exist
        self.assertIn("AAPL", snapshots)
        self.assertIn("SPY", snapshots)
        
        # Verify structure
        for ticker in ["AAPL", "SPY"]:
            self.assertEqual(snapshots[ticker]["open"], 100.0)
            self.assertEqual(snapshots[ticker]["high"], 105.0)
            self.assertEqual(snapshots[ticker]["low"], 95.0)
            self.assertEqual(snapshots[ticker]["close"], 102.0)
            self.assertEqual(snapshots[ticker]["volume"], 1000000.0)
            self.assertEqual(snapshots[ticker]["date"], "2026-06-15")
```
To run the project tests:
```bash
pytest tests/
```
