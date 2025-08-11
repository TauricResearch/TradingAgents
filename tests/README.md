# TradingAgents Test Suite

This directory contains the comprehensive test suite for the TradingAgents project.

## Directory Structure

```
tests/
├── __init__.py                 # Test package initialization
├── conftest.py                 # Pytest configuration and shared fixtures
├── unit/                       # Unit tests (fast, isolated)
│   ├── __init__.py
│   ├── agents/                 # Tests for agent modules
│   │   ├── __init__.py
│   │   └── test_market_analyst.py
│   ├── dataflows/             # Tests for data processing
│   │   ├── __init__.py
│   │   └── test_finnhub_utils.py
│   └── graph/                 # Tests for graph components
│       ├── __init__.py
│       └── test_trading_graph.py
├── integration/               # Integration tests (slower, end-to-end)
│   ├── __init__.py
│   └── test_full_workflow.py
├── fixtures/                  # Test data and utilities
│   ├── __init__.py
│   └── sample_data.py
└── README.md                  # This file
```

## Test Categories

### Unit Tests (`tests/unit/`)
- **Fast execution** (< 1 second per test)
- **Isolated** - test individual functions/classes
- **Mocked dependencies** - no external API calls
- **High coverage** - test edge cases and error conditions

### Integration Tests (`tests/integration/`)
- **End-to-end workflows** - test complete trading processes
- **Component interaction** - verify modules work together
- **Slower execution** - may take several seconds
- **Realistic scenarios** - use mock data that simulates real conditions

## Running Tests

### Prerequisites

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment** (for tests that need API keys):
   ```bash
   export OPENAI_API_KEY="test-key"
   export FINNHUB_API_KEY="test-key"
   # Tests will use mocked responses, but keys prevent validation errors
   ```

### Quick Commands

```bash
# Run all tests
pytest tests/

# Run only unit tests (fast)
pytest tests/unit/ -m unit

# Run only integration tests
pytest tests/integration/ -m integration

# Run with coverage report
pytest tests/ --cov=tradingagents --cov=cli --cov-report=html

# Run tests in parallel
pytest tests/ -n auto

# Run specific test file
pytest tests/unit/agents/test_market_analyst.py

# Run tests matching pattern
pytest tests/ -k "market_analyst"
```

### Using the Makefile

```bash
# Run unit tests
make test-unit

# Run all tests with coverage
make test-coverage

# Run linting
make lint

# Clean up test artifacts
make clean
```

### Using the Test Runner

```bash
# Run unit tests
python run_tests.py unit

# Run integration tests  
python run_tests.py integration

# Run with coverage
python run_tests.py coverage

# Run specific file
python run_tests.py all --file tests/unit/agents/test_market_analyst.py
```

## Test Configuration

### Pytest Configuration (`pytest.ini`)
- Test discovery patterns
- Coverage settings
- Output formatting
- Timeout settings
- Markers for test categorization

### Coverage Configuration (`.coveragerc`)
- Source code inclusion/exclusion
- Branch coverage enabled
- HTML and XML report generation
- Coverage thresholds

### pyproject.toml Integration
- Tool-specific configurations
- Development dependencies
- Test execution settings

## Writing Tests

### Test Naming Convention
```python
def test_function_name_scenario():
    """Test that function_name handles scenario correctly."""
    # Arrange
    # Act  
    # Assert
```

### Using Fixtures
```python
def test_market_analyst_with_config(sample_config, mock_llm, mock_toolkit):
    """Example of using shared fixtures."""
    # Fixtures are automatically injected
    analyst = create_market_analyst(mock_llm, mock_toolkit)
    # Test logic here...
```

### Parameterized Tests
```python
@pytest.mark.parametrize("ticker,expected", [
    ("AAPL", "BUY"),
    ("TSLA", "HOLD"), 
    ("NVDA", "SELL"),
])
def test_trading_decisions(ticker, expected):
    # Test with multiple inputs
```

### Test Markers
```python
@pytest.mark.unit
def test_fast_unit_test():
    """Fast unit test."""
    pass

@pytest.mark.integration  
def test_slow_integration_test():
    """Slower integration test."""
    pass

@pytest.mark.api
def test_requiring_api_access():
    """Test that needs real API (may be skipped in CI)."""
    pass
```

## Mock Data and Fixtures

### Sample Data Factory
The `tests/fixtures/sample_data.py` module provides:
- **Market data** - OHLCV price data
- **News data** - Financial news articles
- **Financial statements** - Balance sheet, income, cash flow
- **Social sentiment** - Reddit/Twitter posts with sentiment scores
- **Technical indicators** - RSI, MACD, Bollinger Bands, etc.

### Usage Example
```python
from tests.fixtures.sample_data import SampleDataFactory

def test_with_market_data():
    data = SampleDataFactory.create_market_data("AAPL", days=30)
    # Use realistic market data in tests
```

## Best Practices

### 1. Test Structure (AAA Pattern)
```python
def test_example():
    # Arrange - Set up test data and mocks
    config = sample_config()
    mock_llm = Mock()
    
    # Act - Execute the code being tested  
    result = function_under_test(config, mock_llm)
    
    # Assert - Verify the results
    assert result.status == "success"
    mock_llm.invoke.assert_called_once()
```

### 2. Descriptive Test Names
- Use clear, descriptive test function names
- Include the scenario being tested
- Make it easy to understand what failed

### 3. Mock External Dependencies
```python
@patch('tradingagents.dataflows.finnhub_utils.requests')
def test_api_call_handling(mock_requests):
    mock_requests.get.return_value.json.return_value = {"data": "test"}
    # Test logic that doesn't make real API calls
```

### 4. Test Edge Cases
- Empty inputs
- Invalid data formats
- Network timeouts
- API errors
- Boundary conditions

### 5. Keep Tests Independent
- Each test should be able to run in isolation
- Don't rely on test execution order
- Clean up after tests if needed

## Continuous Integration

### GitHub Actions (if added)
```yaml
# Example CI configuration
- name: Run tests
  run: |
    pytest tests/ --cov=tradingagents --junitxml=pytest.xml
    pytest tests/ --cov=tradingagents --cov-report=xml
```

### Coverage Requirements
- Minimum 70% coverage for new code
- Unit tests should achieve >90% coverage
- Integration tests ensure end-to-end functionality

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure you're in the project root
   cd /path/to/TradingAgents
   
   # Install in development mode
   pip install -e .
   ```

2. **API Key Warnings**
   ```bash
   # Set dummy API keys for testing
   export OPENAI_API_KEY="test-key"
   export FINNHUB_API_KEY="test-key"
   ```

3. **Slow Tests**
   ```bash
   # Run only fast unit tests
   pytest tests/unit/ -m unit
   
   # Use parallel execution
   pytest tests/ -n auto
   ```

4. **Coverage Issues**
   ```bash
   # Clean coverage cache
   rm -rf .coverage*
   
   # Regenerate report
   pytest tests/ --cov=tradingagents --cov-report=html
   ```

### Getting Help

- Check test output for detailed error messages
- Use `pytest --lf` to run only the last failed tests
- Use `pytest --pdb` to drop into debugger on failures
- Review the conftest.py file for available fixtures

## Contributing

When adding new tests:

1. **Follow the existing structure**
2. **Add appropriate markers** (`@pytest.mark.unit` etc.)
3. **Include docstrings** explaining what is being tested
4. **Mock external dependencies** 
5. **Test both success and failure cases**
6. **Update this README** if adding new test categories