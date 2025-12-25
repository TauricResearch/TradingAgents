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

## Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

```python
@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    llm = Mock()
    llm.invoke.return_value = Mock(content="Test response")
    return llm

@pytest.fixture
def mock_data_tools():
    """Mock data access tools."""
    return {
        "get_stock_data": Mock(return_value={"close": [150, 151, 152]}),
        "get_indicators": Mock(return_value={"RSI": {"rsi": [65]}}),
    }

@pytest.fixture
def test_config():
    """Test configuration."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 1
    return config
```

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
