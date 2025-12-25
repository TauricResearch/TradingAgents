# Guide: Adding a New Data Vendor

This guide shows you how to add support for a new data vendor to TradingAgents.

## Overview

Adding a new data vendor involves:
1. Creating the vendor implementation
2. Adding it to the interface router
3. Configuring vendor selection
4. Testing the integration
5. Updating documentation

## Step 1: Create Vendor Implementation

Create a new file in `tradingagents/dataflows/`:

```python
# tradingagents/dataflows/new_vendor.py

from typing import Dict, List, Any
from datetime import datetime

def newvendor_get_stock_data(
    ticker: str,
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """
    Get historical stock data from NewVendor API.

    Args:
        ticker: Stock ticker symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dictionary with stock data
    """
    import requests

    api_key = os.getenv("NEWVENDOR_API_KEY")
    if not api_key:
        raise ValueError("NEWVENDOR_API_KEY environment variable required")

    url = f"https://api.newvendor.com/stocks/{ticker}"
    params = {
        "start": start_date,
        "end": end_date,
        "apikey": api_key
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()

    # Transform to standard format
    return {
        "ticker": ticker,
        "dates": data["timestamps"],
        "open": data["open_prices"],
        "high": data["high_prices"],
        "low": data["low_prices"],
        "close": data["close_prices"],
        "volume": data["volumes"]
    }
```

## Step 2: Add to Interface Router

Modify `tradingagents/dataflows/interface.py`:

```python
from tradingagents.dataflows.new_vendor import (
    newvendor_get_stock_data,
    newvendor_get_fundamentals
)

def get_stock_data(ticker: str, start_date: str, end_date: str):
    """Get stock data with vendor routing."""
    vendor = get_vendor_for_category("core_stock_apis")

    if vendor == "yfinance":
        return yfinance_get_stock_data(ticker, start_date, end_date)
    elif vendor == "alpha_vantage":
        return alphavantage_get_stock_data(ticker, start_date, end_date)
    elif vendor == "newvendor":  # Add new vendor
        return newvendor_get_stock_data(ticker, start_date, end_date)
    elif vendor == "local":
        return local_get_stock_data(ticker, start_date, end_date)
    else:
        raise ValueError(f"Unknown vendor: {vendor}")
```

## Step 3: Configure Vendor Selection

Update configuration to allow vendor selection:

```python
# In usage code
config = DEFAULT_CONFIG.copy()
config["data_vendors"]["core_stock_apis"] = "newvendor"
```

## Step 4: Add Error Handling

Implement vendor-specific error handling:

```python
from tradingagents.dataflows.exceptions import (
    VendorError,
    RateLimitError,
    DataUnavailableError
)

def newvendor_get_stock_data(ticker, start_date, end_date):
    try:
        # API call
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            # Rate limit
            retry_after = int(e.response.headers.get("Retry-After", 60))
            raise RateLimitError(
                vendor="newvendor",
                message="Rate limit exceeded",
                retry_after=retry_after
            )
        elif e.response.status_code == 404:
            # Data not available
            raise DataUnavailableError(
                f"Data not available for {ticker}"
            )
        else:
            raise VendorError(f"NewVendor API error: {e}")

    except requests.exceptions.RequestException as e:
        raise VendorError(f"NewVendor connection error: {e}")
```

## Step 5: Test Integration

Create tests for your vendor:

```python
# tests/integration/test_newvendor.py

import pytest
import os
from tradingagents.dataflows.new_vendor import newvendor_get_stock_data

@pytest.fixture
def mock_newvendor_key(monkeypatch):
    """Mock NewVendor API key."""
    monkeypatch.setenv("NEWVENDOR_API_KEY", "test_key")

def test_newvendor_get_stock_data(mock_newvendor_key):
    """Test NewVendor returns stock data."""
    # This test requires actual API or mocking
    data = newvendor_get_stock_data("NVDA", "2024-01-01", "2024-01-10")

    assert "dates" in data
    assert "close" in data
    assert len(data["close"]) > 0
```

## Step 6: Update Documentation

After implementing the vendor, update the documentation:

1. **Add to data-flow.md**: Document vendor in `docs/architecture/data-flow.md`
2. **Update configuration.md**: Add environment variable requirements
3. **Add API docs**: Document functions in `docs/api/dataflows.md`

## Best Practices

1. **Follow Interface Pattern**: Implement all required methods matching the interface
2. **Error Handling**: Map vendor-specific errors to unified exceptions
3. **Testing**: Write both unit tests (mocked) and integration tests
4. **Rate Limiting**: Implement retry logic with exponential backoff
5. **Caching**: Consider caching responses to reduce API calls
6. **Logging**: Use structured logging for debugging

## Common Patterns

### Handling Pagination

```python
def get_all_pages(endpoint, params):
    """Fetch all pages of paginated API."""
    all_data = []
    page = 1

    while True:
        params["page"] = page
        response = requests.get(endpoint, params=params)
        data = response.json()

        if not data["results"]:
            break

        all_data.extend(data["results"])
        page += 1

    return all_data
```

### Caching Responses

```python
from functools import lru_cache
from datetime import datetime

@lru_cache(maxsize=100)
def cached_get_stock_data(ticker: str, date: str):
    """Cache stock data to reduce API calls."""
    return newvendor_get_stock_data(ticker, date, date)
```

## Troubleshooting

### Import Errors
- Ensure vendor module is in `tradingagents/dataflows/`
- Check `__init__.py` exports the functions

### API Authentication Errors
- Verify environment variable is set correctly
- Check API key has required permissions
- Ensure API key is not expired

### Data Format Mismatches
- Transform vendor response to standard format
- Handle missing fields gracefully
- Validate data types before returning

## See Also

- [Data Flow Architecture](../architecture/data-flow.md)
- [Data Flows API Reference](../api/dataflows.md)
- [Configuration Guide](configuration.md)
- [Error Handling](adding-llm-provider.md#error-handling)
