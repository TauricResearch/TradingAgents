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
├── unit/                   # Unit tests (fast, isolated)
│   ├── test_analysts.py
│   ├── test_dataflows.py
│   └── test_utils.py
├── integration/            # Integration tests (medium speed)
│   ├── test_graph.py
│   ├── test_llm_providers.py
│   └── test_data_vendors.py
├── regression/             # Regression tests
│   └── smoke/             # Critical path tests (CI gate)
├── fixtures/              # Shared test fixtures
└── conftest.py            # pytest configuration
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

# Regression tests only
pytest tests/regression/

# Smoke tests (critical path)
pytest -m smoke
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

**Purpose**: Test complete workflows

**Characteristics**:
- Slow (30+ seconds)
- Use real or test LLM APIs
- Validate full system
- Minimal count (critical paths only)

**Example**:
```python
@pytest.mark.integration
def test_full_analysis_workflow():
    """Test complete trading analysis."""
    ta = TradingAgentsGraph()
    state, decision = ta.propagate("NVDA", "2024-05-10")

    assert decision["action"] in ["BUY", "SELL", "HOLD"]
    assert 0.0 <= decision["confidence_score"] <= 1.0
```

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
└── integration/conftest.py  # Integration test specific fixtures
    ├── Live ChromaDB (live_chromadb)
    └── Integration temp directory (integration_temp_dir)
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
