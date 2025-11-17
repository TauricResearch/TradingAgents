# TradingAgents Test Suite

Comprehensive, production-ready test suite for TradingAgents using TDD best practices.

## Overview

This test suite provides thorough coverage of the new TradingAgents features including:
- LLM Factory (multi-provider support)
- Broker Integration (base and Alpaca)
- Web Interface (Chainlit)

## Test Files

### 1. `test_llm_factory.py`
Tests for the LLM factory that supports OpenAI, Anthropic, and Google providers.

**Coverage:**
- Provider validation and error handling
- Model recommendations for each provider
- LLM creation with various configurations
- Environment variable handling
- Backend URL configuration
- Error cases (missing API keys, invalid providers)

**Test Count:** 40 tests

**Key Features:**
- All external API calls are mocked
- No real API keys required
- Fast execution (< 1s per test)
- Parametrized tests for multiple providers
- Tests all three providers: OpenAI, Anthropic, Google

### 2. `test_base_broker.py`
Tests for the abstract broker interface and data structures.

**Coverage:**
- Order enumerations (OrderSide, OrderType, OrderStatus)
- BrokerOrder dataclass with all order types
- BrokerPosition dataclass
- BrokerAccount dataclass
- Exception hierarchy
- Convenience methods (buy_market, sell_market, buy_limit, sell_limit)
- Abstract interface compliance

**Test Count:** 25+ tests

**Key Features:**
- Tests all order types: market, limit, stop, stop-limit
- Tests fractional shares
- Tests all exception types
- Parametrized tests for enums

### 3. `test_alpaca_broker.py`
Tests for Alpaca broker integration with complete API mocking.

**Coverage:**
- Broker initialization (with credentials and env vars)
- Connection management
- Account operations
- Position operations (single and multiple)
- Order submission (all types)
- Order cancellation
- Order retrieval
- Current price fetching
- Error handling (network errors, insufficient funds, etc.)
- Helper methods for type conversion

**Test Count:** 40+ tests

**Key Features:**
- All Alpaca API calls are mocked using `requests` mock
- Tests both paper and live trading URLs
- Tests insufficient funds error
- Tests network errors
- Tests 404 responses
- Fast, no network calls
- Parametrized tests for status conversion

### 4. `test_web_app.py`
Tests for the Chainlit web interface.

**Coverage:**
- Command parsing (analyze, buy, sell, portfolio, account, etc.)
- Session state management
- Input validation
- Broker integration
- TradingAgents integration
- Error handling
- Message formatting
- Provider switching

**Test Count:** 50+ tests

**Key Features:**
- Chainlit module is mocked
- Tests all commands
- Tests error cases
- Tests fractional shares
- Parametrized tests for commands

## Shared Test Utilities

### `conftest.py`
Provides shared fixtures and utilities:

**Fixtures:**
- `clean_environment`: Auto-use fixture that cleans environment
- `mock_env_vars`: Common environment variables
- `sample_broker_account`: Sample account data
- `sample_broker_position`: Sample position data
- `sample_positions_list`: List of positions
- `sample_market_order`: Market order fixture
- `sample_limit_order`: Limit order fixture
- `sample_filled_order`: Filled order fixture
- `connected_broker`: Fully configured mock broker
- `mock_trading_graph`: Mock TradingAgents graph

**Utilities:**
- `MockBrokerFactory`: Factory for creating different broker mocks
- `AlpacaResponseMocks`: Factory for Alpaca API responses
- `OrderBuilder`: Fluent interface for building test orders
- `BrokerAssertions`: Helper class for common assertions

## Running Tests

### Run All Tests
```bash
pytest tests/
```

### Run Specific Test File
```bash
pytest tests/test_base_broker.py
pytest tests/brokers/test_alpaca_broker.py
pytest tests/test_llm_factory.py
pytest tests/test_web_app.py
```

### Run Tests by Marker
```bash
# Run only unit tests
pytest -m unit

# Run only broker tests
pytest -m broker

# Run only LLM tests
pytest -m llm

# Skip slow tests
pytest -m "not slow"
```

### Run with Coverage
```bash
# Generate HTML coverage report
pytest --cov=tradingagents --cov-report=html

# Generate terminal report
pytest --cov=tradingagents --cov-report=term-missing

# With minimum coverage threshold
pytest --cov=tradingagents --cov-fail-under=90
```

### Run Tests in Parallel
```bash
# Install pytest-xdist first
pip install pytest-xdist

# Run with 4 workers
pytest -n 4
```

## Test Configuration

### `pytest.ini`
Configuration file with:
- Test discovery patterns
- Custom markers (unit, integration, slow, broker, llm, web)
- Logging configuration
- Coverage settings
- Warning filters

### Markers
- `unit`: Unit tests (isolated components)
- `integration`: Integration tests (multiple components)
- `slow`: Slow-running tests (> 1 second)
- `broker`: Broker-related tests
- `llm`: LLM factory tests
- `web`: Web interface tests
- `requires_api_key`: Tests needing real API keys
- `requires_network`: Tests needing network access

## Test Quality Standards

All tests follow these standards:
- **Fast**: Each test runs in < 1 second
- **Isolated**: Tests don't depend on each other
- **Repeatable**: Tests give same results every run
- **Self-checking**: Tests include clear assertions
- **Timely**: Tests written alongside code

### Mocking Strategy
- External APIs are always mocked
- No network calls in tests
- No real API keys required
- Mock at the integration boundary

### Test Structure
```python
def test_feature_name():
    # Arrange: Set up test data and mocks
    ...

    # Act: Execute the code under test
    ...

    # Assert: Verify the results
    ...
```

## Coverage Goals

Target coverage: **> 90%**

Current coverage by module:
- `llm_factory.py`: ~95% (all major paths)
- `brokers/base.py`: ~98% (comprehensive)
- `brokers/alpaca_broker.py`: ~92% (all API operations)
- `web_app.py`: ~85% (all commands and error paths)

## Areas Difficult to Test

1. **Actual API Calls**: All mocked for speed and reliability
2. **Chainlit UI Rendering**: UI library internals not tested
3. **Network Timeouts**: Would slow down test suite
4. **Rate Limiting**: Behavior depends on external service

## Dependencies

Test dependencies (from requirements.txt or pyproject.toml):
```
pytest>=6.0
pytest-cov>=2.0
pytest-asyncio>=0.18.0 (for async tests)
pytest-mock>=3.0 (optional, for advanced mocking)
pytest-xdist>=2.0 (optional, for parallel execution)
```

## Continuous Integration

Tests are designed to run in CI environments:
- No environment setup required
- Fast execution (< 60 seconds for full suite)
- Clear error messages
- Exit codes for pass/fail

### Example GitHub Actions
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install -e ".[test]"
      - run: pytest --cov=tradingagents --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## Best Practices

1. **Write Tests First**: Follow TDD - write test, see it fail, make it pass
2. **One Assertion Per Test**: Tests should verify one thing
3. **Clear Test Names**: Test name should describe what it tests
4. **Use Fixtures**: Reuse test data and setup via fixtures
5. **Mock External Dependencies**: Keep tests fast and reliable
6. **Test Edge Cases**: Include boundary conditions and error cases
7. **Parametrize When Appropriate**: Use `@pytest.mark.parametrize` for similar tests

## Troubleshooting

### Tests Not Found
```bash
# Make sure pytest can find tests
pytest --collect-only
```

### Import Errors
```bash
# Install package in development mode
pip install -e .
```

### Module Not Found
```bash
# Check Python path
python -c "import sys; print(sys.path)"
```

### Slow Tests
```bash
# Run with durations report
pytest --durations=10
```

## Contributing

When adding new features:
1. Write tests first (TDD)
2. Aim for > 90% coverage
3. Mock external dependencies
4. Add parametrized tests for multiple inputs
5. Update this README with new test files

## Contact

For questions about the test suite, check:
- Test file docstrings
- Individual test docstrings
- `conftest.py` fixture documentation
