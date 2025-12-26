# Testing Overview

TradingAgents uses a comprehensive testing strategy to ensure code quality and reliability.

## Testing Philosophy

Our testing approach combines:
- **Unit Tests**: Fast, isolated tests for individual components
- **Integration Tests**: Tests for component interactions
- **End-to-End Tests**: Full workflow validation
- **Regression Tests**: Prevent fixed bugs from returning

## Test Structure

```
tests/
├── __init__.py                  # Package initialization
├── conftest.py                  # Root-level fixtures and configuration
├── unit/                        # Unit tests (fast, isolated)
│   ├── __init__.py
│   ├── conftest.py              # Unit test specific fixtures
│   ├── test_conftest_hierarchy.py
│   ├── test_documentation_structure.py
│   ├── test_exceptions.py
│   ├── test_logging_config.py
│   └── test_report_exporter.py
├── integration/                 # Integration tests (medium speed)
│   ├── __init__.py
│   ├── conftest.py              # Integration test specific fixtures
│   ├── test_akshare.py
│   ├── test_cli_error_handling.py
│   └── test_openrouter.py
├── e2e/                         # End-to-end tests (slow, complete workflows)
│   ├── __init__.py
│   ├── conftest.py              # E2E-specific fixtures
│   ├── README.md                # E2E testing guidelines
│   └── test_deepseek.py
└── CHROMADB_COLLECTION_TESTS.md # ChromaDB test documentation
```

## Running Tests

### All Tests

```bash
pytest tests/
```

### Specific Test Categories

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# End-to-end tests only
pytest tests/e2e/ -m e2e
```

### With Coverage

```bash
pytest tests/ --cov=tradingagents --cov-report=html
```

### Specific Test File

```bash
pytest tests/unit/test_analysts.py -v
```

### Specific Test Function

```bash
pytest tests/unit/test_analysts.py::test_market_analyst_initialization -v
```

## Test Categories

### Unit Tests

**Purpose**: Test individual functions and classes in isolation

**Characteristics**:
- Fast (<1 second per test)
- No external dependencies
- Use mocks for LLMs and data vendors
- High coverage target (90%+)

**Example**:
```python
def test_analyst_initialization():
    """Test analyst can be initialized."""
    llm = Mock()
    tools = []

    analyst = MarketAnalyst(llm, tools)

    assert analyst.name == "market"
    assert analyst.llm == llm
```

### Integration Tests

**Purpose**: Test component interactions

**Characteristics**:
- Medium speed (1-30 seconds)
- May use test APIs or mocks
- Validate workflows
- Coverage target (70%+)

**Example**:
```python
def test_data_vendor_integration():
    """Test data vendor can provide data."""
    interface = DataInterface()
    data = interface.get_stock_data("NVDA", "2024-01-01", "2024-01-10")

    assert "close" in data
    assert len(data["close"]) > 0
```

### End-to-End Tests

**Purpose**: Test complete workflows from a user's perspective

**Characteristics**:
- Slow (multiple seconds to minutes)
- Use real or test APIs with realistic data
- Validate complete system integration
- Focus on critical user journeys
- Minimal count (most expensive tests to run)

**Location**: `tests/e2e/`

**Marker**: `@pytest.mark.e2e`

**Example**:
```python
import pytest

pytestmark = pytest.mark.e2e

def test_complete_data_workflow(e2e_environment):
    """
    Test complete workflow: data ingestion → analysis → report.

    This test validates the entire user journey from fetching market data
    to generating a trading report.
    """
    # Arrange: Set up data source
    # Act: Execute complete workflow
    # Assert: Validate final report output
    pass
```

See [E2E Testing Guide](../../tests/e2e/README.md) for detailed guidelines and examples.

## Test Fixtures and conftest.py Hierarchy

TradingAgents uses a hierarchical conftest.py structure to organize fixtures by test scope:

### Fixture Organization

```
tests/
├── conftest.py              # Root fixtures - accessible to all tests
│   ├── Environment fixtures (mock_env_openrouter, mock_env_openai, etc.)
│   ├── LangChain mocking (mock_langchain_classes)
│   ├── ChromaDB mocking (mock_chromadb)
│   ├── Memory mocking (mock_memory)
│   ├── Configuration fixtures (sample_config, openrouter_config)
│   └── Temporary directory fixtures (temp_output_dir)
├── unit/conftest.py         # Unit test specific fixtures
│   ├── Data vendor mocking (mock_akshare, mock_yfinance)
│   ├── Sample data (sample_dataframe)
│   ├── Time mocking (mock_time_sleep)
│   ├── HTTP mocking (mock_requests)
│   └── Subprocess mocking (mock_subprocess)
├── integration/conftest.py  # Integration test specific fixtures
│   ├── Live ChromaDB (live_chromadb)
│   └── Integration temp directory (integration_temp_dir)
└── e2e/conftest.py          # End-to-end test specific fixtures
    └── E2E environment setup (e2e_environment)
```

### Root-Level Fixtures (tests/conftest.py)

Available to all tests in any subdirectory:

**Environment Variable Fixtures**:
- `mock_env_openrouter` - Sets OPENROUTER_API_KEY, clears others
- `mock_env_openai` - Sets OPENAI_API_KEY, clears others
- `mock_env_anthropic` - Sets ANTHROPIC_API_KEY, clears others
- `mock_env_google` - Sets GOOGLE_API_KEY, clears others
- `mock_env_empty` - Clears all API keys (for error testing)

**Mocking Fixtures**:
- `mock_langchain_classes` - Mocks ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI
- `mock_chromadb` - Mocks ChromaDB Client with get_or_create_collection()
- `mock_memory` - Mocks FinancialSituationMemory
- `mock_openai_client` - Mocks OpenAI client with embeddings

**Configuration Fixtures**:
- `sample_config` - Default configuration for testing
- `openrouter_config` - OpenRouter-specific configuration

**Utility Fixtures**:
- `temp_output_dir` - Temporary directory for test artifacts

### Unit Test Fixtures (tests/unit/conftest.py)

Only available in `tests/unit/` directory:

- `mock_akshare` - Mocks akshare data vendor
- `mock_yfinance` - Mocks yfinance data vendor
- `sample_dataframe` - Sample stock data DataFrame
- `mock_time_sleep` - Mocks time.sleep for retry tests
- `mock_requests` - Mocks HTTP requests module
- `mock_subprocess` - Mocks subprocess module

### Integration Test Fixtures (tests/integration/conftest.py)

Only available in `tests/integration/` directory:

- `live_chromadb` - Live ChromaDB instance (session-scoped)
- `integration_temp_dir` - Temporary directory with cleanup

### End-to-End Test Fixtures (tests/e2e/conftest.py)

Only available in `tests/e2e/` directory:

- `e2e_environment` - Complete environment setup for end-to-end testing with all dependencies initialized

### Using Fixtures

```python
# Root-level fixture available to all tests
def test_openrouter_env(mock_env_openrouter):
    """Test using environment fixture."""
    import os
    assert os.getenv("OPENROUTER_API_KEY") is not None

# Unit-specific fixture only available in tests/unit/
def test_akshare_mock(mock_akshare):
    """Test data vendor mocking."""
    mock_akshare.stock_us_hist.return_value = pd.DataFrame(...)
    # Use the mock

# Integration-specific fixture only available in tests/integration/
def test_chromadb_integration(live_chromadb):
    """Test with real ChromaDB instance."""
    collection = live_chromadb.get_or_create_collection("test")
    assert collection is not None
```

### Fixture Scope and Lifetime

- **function** (default) - Created fresh for each test
- **session** - Created once for entire test session (only live_chromadb)
- **module** - Created once per test file

Environment fixtures use `patch.dict()` to automatically restore environment after each test.

## Writing Tests

See [Writing Tests Guide](writing-tests.md) for detailed patterns and examples.

## Coverage Goals

- **Overall**: 80%+
- **Unit Tests**: 90%+
- **Integration Tests**: 70%+
- **Critical Paths**: 100%

## Continuous Integration

Tests run automatically on:
- Pull requests
- Pushes to main branch
- Pre-commit hooks (optional)

## Best Practices

1. **Write Tests First**: TDD approach when possible
2. **One Assertion**: Focus tests on single behaviors
3. **Clear Names**: `test_<function>_<scenario>_<expected>`
4. **Use Fixtures**: DRY principle for setup
5. **Mock External Calls**: Don't hit real APIs in unit tests
6. **Fast Tests**: Keep unit tests under 1 second
7. **Isolation**: Tests should not depend on each other
8. **Documentation**: Add docstrings to complex tests

## See Also

- [Running Tests](running-tests.md)
- [Writing Tests](writing-tests.md)
- [Test Organization Best Practices](../architecture/multi-agent-system.md#testing)
