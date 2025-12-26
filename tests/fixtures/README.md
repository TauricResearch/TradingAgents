# Test Fixtures

Centralized test fixtures for TradingAgents test suite. This directory provides mock data for stock market OHLCV data, analysis metadata, report sections, API responses, and configurations.

## Directory Structure

```
tests/fixtures/
├── __init__.py              # FixtureLoader class and convenience functions
├── README.md                # This file
├── stock_data/              # Stock market OHLCV data
│   ├── us_market_ohlcv.json
│   ├── cn_market_ohlcv.json
│   └── standardized_ohlcv.json
├── metadata/                # Analysis metadata
│   └── analysis_metadata.json
├── report_sections/         # Complete report sections
│   └── complete_reports.json
├── api_responses/           # Mock API responses
│   └── openai_embeddings.json
└── configurations/          # Configuration examples
    └── default_config.json
```

## Quick Start

### Basic Usage

```python
from tests.fixtures import FixtureLoader

# Load US stock data
df = FixtureLoader.load_us_stock_data()
print(df.head())

# Load Chinese stock data (with Chinese column names)
cn_df = FixtureLoader.load_cn_stock_data()

# Load Chinese stock data (standardized to English)
cn_df_std = FixtureLoader.load_cn_stock_data(standardize=True)

# Load analysis metadata
metadata = FixtureLoader.load_analysis_metadata("complete_analysis")

# Load report sections
sections = FixtureLoader.load_complete_report_sections()

# Load API responses
embedding = FixtureLoader.load_embedding_response()

# Load configuration
config = FixtureLoader.load_default_config("complete_config")
```

### Convenience Functions

```python
# Import convenience functions directly
from tests.fixtures import (
    load_us_stock_data,
    load_cn_stock_data,
    load_analysis_metadata,
    load_complete_report_sections,
    load_embedding_response,
    load_default_config,
)

# Use them directly
df = load_us_stock_data()
metadata = load_analysis_metadata()
```

## Fixture Details

### Stock Data Fixtures

#### US Market Data (`stock_data/us_market_ohlcv.json`)

OHLCV data for AAPL (Apple Inc.) from 2024-11-01 to 2024-11-15.

**Columns**: Date, Open, High, Low, Close, Volume

**Usage**:
```python
# Load main data
df = FixtureLoader.load_us_stock_data()

# Load edge cases
empty = FixtureLoader.load_us_stock_data(edge_case="empty_data")
single = FixtureLoader.load_us_stock_data(edge_case="single_row")
missing_vol = FixtureLoader.load_us_stock_data(edge_case="missing_volume")
out_of_order = FixtureLoader.load_us_stock_data(edge_case="out_of_order_dates")
```

**Edge Cases**:
- `empty_data`: Empty DataFrame for testing empty data handling
- `single_row`: Single row of data
- `missing_volume`: Data with Volume column missing
- `out_of_order_dates`: Dates not in chronological order

#### Chinese Market Data (`stock_data/cn_market_ohlcv.json`)

OHLCV data for 600519.SH (贵州茅台 - Kweichow Moutai) from 2024-11-01 to 2024-11-15.

**Columns (Chinese)**: 日期, 开盘, 最高, 最低, 收盘, 成交量

**Column Mapping**:
- 日期 → Date
- 开盘 → Open
- 最高 → High
- 最低 → Low
- 收盘 → Close
- 成交量 → Volume

**Usage**:
```python
# Load with Chinese column names
cn_df = FixtureLoader.load_cn_stock_data()
print(cn_df.columns)  # ['开盘', '最高', '最低', '收盘', '成交量']

# Load with standardized English column names
cn_df_std = FixtureLoader.load_cn_stock_data(standardize=True)
print(cn_df_std.columns)  # ['Open', 'High', 'Low', 'Close', 'Volume']

# Load edge cases
empty = FixtureLoader.load_cn_stock_data(edge_case="empty_data")
mixed = FixtureLoader.load_cn_stock_data(edge_case="mixed_columns")
```

**Edge Cases**:
- `empty_data`: Empty DataFrame
- `mixed_columns`: Mix of Chinese and English column names

#### Standardized Data (`stock_data/standardized_ohlcv.json`)

Standardized OHLCV data for TSLA from 2024-11-01 to 2024-11-14. Represents data after processing and standardization, ready for technical analysis.

**Usage**:
```python
df = FixtureLoader.load_standardized_stock_data()
```

### Metadata Fixtures

#### Analysis Metadata (`metadata/analysis_metadata.json`)

Metadata for stock analysis reports including ticker, date range, analysts, data vendors, LLM providers, and execution details.

**Available Examples**:
- `complete_analysis`: Full analysis with all sections completed
- `partial_analysis`: Partial analysis with some missing sections
- `multi_ticker_batch`: Batch analysis for multiple tickers
- `chinese_market_analysis`: Chinese market analysis with localization
- `error_scenario`: Failed analysis with error details

**Usage**:
```python
# Complete analysis
metadata = FixtureLoader.load_analysis_metadata("complete_analysis")
print(metadata["ticker"])  # 'AAPL'
print(metadata["status"])  # 'complete'

# Partial analysis
partial = FixtureLoader.load_analysis_metadata("partial_analysis")
print(partial["missing_sections"])  # ['news_report', 'fundamentals_report', ...]

# Error scenario
error = FixtureLoader.load_analysis_metadata("error_scenario")
print(error["error_type"])  # 'DataNotFoundError'
```

### Report Section Fixtures

#### Complete Reports (`report_sections/complete_reports.json`)

Full report sections for comprehensive analysis. Includes all analyst reports from market analysis to final trade decision.

**Available Sections**:
- `market_report`: Technical analysis and market overview
- `sentiment_report`: Social sentiment analysis
- `news_report`: News analysis and impact assessment
- `fundamentals_report`: Fundamental analysis with financials
- `investment_plan`: Long-term investment strategy
- `trader_investment_plan`: Short-term trading plan
- `final_trade_decision`: Executive decision and order details

**Usage**:
```python
# Load all sections
sections = FixtureLoader.load_complete_report_sections()
print(sections["market_report"]["content"][:50])

# Load specific section
market = FixtureLoader.load_report_section("market_report")
print(market["analyst"])  # 'market'
print(market["generated_at"])  # datetime object

# Load partial sections (some None)
partial = FixtureLoader.load_partial_report_sections()
print(partial["market_report"])  # Has content
print(partial["sentiment_report"])  # None
```

### API Response Fixtures

#### OpenAI Embeddings (`api_responses/openai_embeddings.json`)

Mock OpenAI API responses for embedding requests. Useful for testing without making actual API calls.

**Available Examples**:
- `single_text_embedding`: Single embedding response
- `batch_text_embeddings`: Multiple embeddings in one response
- `financial_situation_embedding`: Embedding for financial situation text
- `large_embedding_1536`: Full-size 1536-dimension embedding (truncated in fixture)

**Available Errors**:
- `rate_limit_error`: Rate limit exceeded error
- `invalid_api_key`: Invalid API key error
- `model_not_found`: Model not found error

**Usage**:
```python
# Load embedding response
response = FixtureLoader.load_embedding_response("single_text_embedding")
embedding_vector = response["data"][0]["embedding"]
print(len(embedding_vector))  # 20 (truncated for testing)

# Load batch embeddings
batch = FixtureLoader.load_embedding_response("batch_text_embeddings")
print(len(batch["data"]))  # 3

# Load error response
error = FixtureLoader.load_embedding_error("rate_limit_error")
print(error["error"]["type"])  # 'rate_limit_error'
```

### Configuration Fixtures

#### Default Configurations (`configurations/default_config.json`)

Configuration examples for different scenarios and vendor setups.

**Available Examples**:
- `complete_config`: Full configuration with all options
- `minimal_config`: Minimal required configuration
- `chinese_market_config`: Chinese market-specific configuration
- `high_frequency_config`: High-frequency trading configuration
- `testing_config`: Testing/development configuration

**Vendor-Specific Configs**:
- `alpaca`: Alpaca API configuration
- `alpha_vantage`: Alpha Vantage API configuration
- `akshare`: AKShare (Chinese market) configuration
- `yfinance`: Yahoo Finance configuration

**LLM Provider Configs**:
- `openrouter`: OpenRouter configuration
- `openai`: OpenAI configuration
- `anthropic`: Anthropic configuration
- `ollama`: Ollama (local) configuration

**Usage**:
```python
# Load complete config
config = FixtureLoader.load_default_config("complete_config")
print(config["data_vendor"])  # 'alpaca'

# Load minimal config
minimal = FixtureLoader.load_default_config("minimal_config")

# Load vendor-specific config
alpaca_config = FixtureLoader.load_vendor_config("alpaca")
print(alpaca_config["paper_trading"])  # True

# Load LLM provider config
openrouter = FixtureLoader.load_llm_provider_config("openrouter")
print(openrouter["backend_url"])  # 'https://openrouter.ai/api/v1'
```

## Advanced Usage

### Loading Custom Fixtures

```python
# Load arbitrary JSON fixture
custom_data = FixtureLoader.load_json_fixture("path/to/custom.json")

# Load as DataFrame
df = FixtureLoader.load_dataframe_fixture(
    "path/to/data.json",
    data_key="data",
    date_column="Date",
    set_index=True
)
```

### Datetime Parsing

All datetime strings in JSON fixtures are automatically parsed to Python `datetime` objects. Supports ISO 8601 format:

```json
{
  "generated_at": "2024-12-26T14:30:00",
  "analysis_date": "2024-12-26",
  "created_at": "2024-12-26T10:30:00+08:00"
}
```

After loading:
```python
metadata = FixtureLoader.load_analysis_metadata()
print(type(metadata["generated_at"]))  # <class 'datetime.datetime'>
```

### Working with DataFrames

```python
# Load stock data
df = FixtureLoader.load_us_stock_data()

# Date is already the index
print(df.index.name)  # 'Date'
print(df.index.dtype)  # datetime64[ns]

# Columns are OHLCV
print(df.columns.tolist())  # ['Open', 'High', 'Low', 'Close', 'Volume']

# Ready for technical analysis
df['SMA_20'] = df['Close'].rolling(window=20).mean()
```

### Testing Edge Cases

```python
import pytest

def test_handles_empty_data():
    """Test that function handles empty DataFrame gracefully."""
    empty_df = FixtureLoader.load_us_stock_data(edge_case="empty_data")
    assert empty_df.empty

    result = process_stock_data(empty_df)
    assert result is None or result.empty

def test_handles_missing_volume():
    """Test that function handles missing Volume column."""
    df = FixtureLoader.load_us_stock_data(edge_case="missing_volume")
    assert "Volume" not in df.columns

    # Should not raise error
    result = calculate_indicators(df)
    assert result is not None
```

## Writing Tests with Fixtures

### Basic Test Example

```python
import pytest
from tests.fixtures import FixtureLoader

def test_stock_data_processing():
    """Test stock data processing with fixture."""
    # Arrange
    df = FixtureLoader.load_us_stock_data()

    # Act
    result = process_stock_data(df)

    # Assert
    assert result is not None
    assert len(result) == len(df)
    assert result.index.equals(df.index)
```

### Pytest Fixture Integration

```python
import pytest
from tests.fixtures import FixtureLoader

@pytest.fixture
def us_stock_data():
    """Provide US stock data for tests."""
    return FixtureLoader.load_us_stock_data()

@pytest.fixture
def analysis_metadata():
    """Provide analysis metadata for tests."""
    return FixtureLoader.load_analysis_metadata()

def test_with_fixtures(us_stock_data, analysis_metadata):
    """Test using pytest fixtures."""
    result = analyze_stock(
        data=us_stock_data,
        ticker=analysis_metadata["ticker"]
    )
    assert result["ticker"] == "AAPL"
```

### Parameterized Tests

```python
import pytest
from tests.fixtures import FixtureLoader

@pytest.mark.parametrize("edge_case", [
    "empty_data",
    "single_row",
    "missing_volume",
    "out_of_order_dates"
])
def test_edge_cases(edge_case):
    """Test handling of various edge cases."""
    df = FixtureLoader.load_us_stock_data(edge_case=edge_case)

    # Should not raise exception
    result = process_stock_data(df)

    # Should handle gracefully
    assert result is not None or df.empty
```

### Mocking API Responses

```python
from unittest.mock import patch, MagicMock
from tests.fixtures import FixtureLoader

def test_embedding_api_call():
    """Test embedding API call with mock response."""
    # Load mock response
    mock_response = FixtureLoader.load_embedding_response()

    # Mock the API client
    with patch('openai.OpenAI') as mock_client:
        mock_client.return_value.embeddings.create.return_value = MagicMock(
            **mock_response
        )

        # Test function that uses embeddings
        result = get_text_embedding("test text")

        # Verify
        assert result is not None
        assert len(result) > 0
```

## Best Practices

### 1. Use Fixtures Over Hardcoded Data

**Bad**:
```python
def test_stock_processing():
    df = pd.DataFrame({
        'Date': ['2024-11-01', '2024-11-02'],
        'Close': [100, 101]
    })
    # ...
```

**Good**:
```python
def test_stock_processing():
    df = FixtureLoader.load_us_stock_data()
    # ...
```

### 2. Test Edge Cases

Always test edge cases using the provided edge case fixtures:

```python
def test_empty_data_handling():
    df = FixtureLoader.load_us_stock_data(edge_case="empty_data")
    result = process_data(df)
    assert result is not None  # Should not crash

def test_missing_column_handling():
    df = FixtureLoader.load_us_stock_data(edge_case="missing_volume")
    result = calculate_volume_indicators(df)
    assert result is None or result.empty  # Graceful degradation
```

### 3. Use Appropriate Fixture Type

- **Unit tests**: Use small, focused fixtures (single row, minimal data)
- **Integration tests**: Use complete fixtures (full data range)
- **Performance tests**: Use edge cases (empty data, large datasets)

### 4. Document Custom Fixtures

If you add custom fixtures:

1. Add JSON file to appropriate subdirectory
2. Add loader method to `FixtureLoader` class
3. Add documentation to this README
4. Add usage examples

### 5. Keep Fixtures Realistic

Fixtures should represent realistic data:
- Use actual stock symbols (AAPL, TSLA, 600519.SH)
- Use realistic price ranges and volumes
- Include realistic metadata and timestamps
- Mirror actual API response structures

## Maintenance

### Adding New Fixtures

1. **Create JSON file** in appropriate subdirectory
2. **Follow naming convention**: `{category}_{description}.json`
3. **Include description** field in JSON
4. **Add loader method** to `FixtureLoader` class
5. **Update this README** with usage examples
6. **Add tests** for the new fixture loader

### Modifying Existing Fixtures

1. **Maintain backward compatibility** when possible
2. **Update documentation** if structure changes
3. **Update affected tests**
4. **Consider adding new example** instead of modifying existing

### Versioning

Fixtures are versioned with the project. Breaking changes to fixture structure should:

1. Increment project version
2. Document migration path in CHANGELOG
3. Provide legacy fixtures for compatibility (if needed)

## Troubleshooting

### FileNotFoundError

```python
# Error: FileNotFoundError: Fixture not found
# Solution: Check path is relative to fixtures directory
df = FixtureLoader.load_json_fixture("stock_data/us_market_ohlcv.json")  # Correct
```

### KeyError: 'data'

```python
# Error: KeyError: Key 'data' not found in fixture
# Solution: Specify correct data_key
df = FixtureLoader.load_dataframe_fixture(
    "path/to/file.json",
    data_key="examples"  # Not "data"
)
```

### Datetime Not Parsed

```python
# Dates are strings instead of datetime objects
# Solution: Ensure date format is ISO 8601
# Good: "2024-11-01T00:00:00" or "2024-11-01"
# Bad: "11/01/2024" or "Nov 1, 2024"
```

### Empty DataFrame

```python
# Getting empty DataFrame unexpectedly
# Check if loading edge case by mistake
df = FixtureLoader.load_us_stock_data()  # Main data
df = FixtureLoader.load_us_stock_data(edge_case=None)  # Explicit
```

## Contributing

When contributing new fixtures:

1. Follow existing JSON structure patterns
2. Use UTF-8 encoding (especially for Chinese characters)
3. Format dates as ISO 8601 strings
4. Include both main data and edge cases
5. Add comprehensive docstrings to loader methods
6. Update this README with usage examples
7. Add unit tests for new loader methods

## License

These fixtures are part of the TradingAgents project and are provided for testing purposes only. Stock data is synthetic and should not be used for actual trading decisions.

## See Also

- [Testing Guide](../README.md) - Testing best practices
- [Pytest Documentation](https://docs.pytest.org/) - Pytest framework
- [Pandas Documentation](https://pandas.pydata.org/) - DataFrame operations
