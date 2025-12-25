# Writing Tests

Guide for writing effective tests for TradingAgents.

## Test Structure

### Basic Test Pattern

```python
def test_function_name_scenario_expected():
    """Test description."""
    # Arrange - Set up test data
    input_data = prepare_test_data()

    # Act - Execute the code being tested
    result = function_under_test(input_data)

    # Assert - Verify the result
    assert result == expected_value
```

### Test Class Pattern

```python
class TestComponentName:
    """Test suite for ComponentName."""

    def test_initialization(self):
        """Test component can be initialized."""
        component = ComponentName()
        assert component is not None

    def test_specific_behavior(self):
        """Test specific behavior works correctly."""
        component = ComponentName()
        result = component.method()
        assert result == expected
```

## Unit Test Examples

### Testing Analyst Initialization

```python
from tradingagents.agents.analysts.market_analyst import MarketAnalyst
from unittest.mock import Mock

def test_market_analyst_initialization():
    """Test MarketAnalyst can be initialized."""
    # Arrange
    llm = Mock()
    tools = []

    # Act
    analyst = MarketAnalyst(llm, tools)

    # Assert
    assert analyst.name == "market"
    assert analyst.llm == llm
    assert analyst.tools == {}
```

### Testing with Mocked LLM

```python
def test_analyst_generates_report():
    """Test analyst generates analysis report."""
    # Arrange
    llm = Mock()
    llm.invoke.return_value = Mock(
        content="Technical analysis shows bullish trend..."
    )

    tools = [Mock(name="get_stock_data")]
    analyst = MarketAnalyst(llm, tools)

    # Act
    report = analyst.analyze("NVDA", "2024-05-10")

    # Assert
    assert "bullish" in report.lower()
    assert llm.invoke.called
```

### Testing Data Flows

```python
from tradingagents.dataflows.yfinance import yfinance_get_stock_data

def test_yfinance_get_stock_data():
    """Test yfinance returns stock data in correct format."""
    # Act
    data = yfinance_get_stock_data("NVDA", "2024-01-01", "2024-01-10")

    # Assert
    assert "dates" in data
    assert "close" in data
    assert len(data["close"]) > 0
    assert all(isinstance(price, (int, float)) for price in data["close"])
```

## Integration Test Examples

### Testing Graph Workflow

```python
import pytest
from tradingagents.graph.trading_graph import TradingAgentsGraph

@pytest.fixture
def minimal_config():
    """Minimal configuration for testing."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 1
    return config

def test_graph_propagation(minimal_config):
    """Test graph can run full propagation."""
    # Arrange
    ta = TradingAgentsGraph(
        selected_analysts=["market"],
        config=minimal_config
    )

    # Act
    state, decision = ta.propagate("NVDA", "2024-05-10")

    # Assert
    assert decision is not None
    assert decision["action"] in ["BUY", "SELL", "HOLD"]
    assert 0.0 <= decision["confidence_score"] <= 1.0
```

### Testing LLM Provider Integration

```python
@pytest.fixture
def openrouter_config():
    """Configuration for OpenRouter provider."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openrouter"
    config["deep_think_llm"] = "anthropic/claude-sonnet-4.5"
    return config

@pytest.fixture
def mock_env_openrouter(monkeypatch):
    """Mock OpenRouter API key."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")

def test_openrouter_initialization(openrouter_config, mock_env_openrouter):
    """Test OpenRouter provider can be initialized."""
    ta = TradingAgentsGraph(config=openrouter_config)

    assert ta.deep_thinking_llm is not None
    assert ta.quick_thinking_llm is not None
```

## Using Fixtures

### Simple Fixture

```python
@pytest.fixture
def sample_stock_data():
    """Sample stock data for testing."""
    return {
        "dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "close": [150.0, 151.0, 152.0],
        "volume": [1000000, 1100000, 1200000]
    }

def test_using_fixture(sample_stock_data):
    """Test using a fixture."""
    assert len(sample_stock_data["close"]) == 3
```

### Fixture with Cleanup

```python
@pytest.fixture
def temp_cache_dir(tmp_path):
    """Temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    yield cache_dir

    # Cleanup happens automatically with tmp_path
```

### Parametrized Fixture

```python
@pytest.fixture(params=["openai", "anthropic", "google"])
def llm_provider(request):
    """Test with multiple LLM providers."""
    return request.param

def test_provider_initialization(llm_provider):
    """Test all providers can be initialized."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = llm_provider

    # Skip if API key not available
    if llm_provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    ta = TradingAgentsGraph(config=config)
    assert ta.deep_thinking_llm is not None
```

## Mocking

### Mocking LLM Responses

```python
from unittest.mock import Mock, patch

def test_with_mocked_llm():
    """Test with mocked LLM responses."""
    llm = Mock()
    llm.invoke.return_value = Mock(content="Mocked response")

    analyst = Analyst(llm)
    response = analyst.analyze("NVDA", "2024-05-10")

    assert "Mocked response" in response
    llm.invoke.assert_called_once()
```

### Mocking Data Vendors

```python
@patch('tradingagents.dataflows.yfinance.yfinance_get_stock_data')
def test_with_mocked_data(mock_get_stock_data):
    """Test with mocked data vendor."""
    # Setup mock
    mock_get_stock_data.return_value = {
        "dates": ["2024-01-01"],
        "close": [150.0]
    }

    # Test
    data = get_stock_data("NVDA", "2024-01-01", "2024-01-01")

    assert data["close"] == [150.0]
    mock_get_stock_data.assert_called_once()
```

### Mocking Environment Variables

```python
def test_with_mocked_env(monkeypatch):
    """Test with mocked environment variables."""
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test_key")

    # Now environment variables are set for this test
    assert os.getenv("OPENAI_API_KEY") == "test_key"
```

## Test Markers

### Marking Tests

```python
@pytest.mark.smoke
def test_critical_path():
    """Critical path test."""
    pass

@pytest.mark.integration
def test_integration_workflow():
    """Integration test."""
    pass

@pytest.mark.slow
def test_expensive_operation():
    """Slow test."""
    pass

@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    """Test for future feature."""
    pass
```

### Conditional Skip

```python
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
def test_requiring_api_key():
    """Test that requires API key."""
    pass
```

## Parameterized Tests

### Simple Parameterization

```python
@pytest.mark.parametrize("ticker,expected_valid", [
    ("NVDA", True),
    ("AAPL", True),
    ("INVALID123", False),
    ("", False),
])
def test_ticker_validation(ticker, expected_valid):
    """Test ticker validation with multiple inputs."""
    result = validate_ticker(ticker)
    assert result == expected_valid
```

### Multiple Parameters

```python
@pytest.mark.parametrize("provider,model", [
    ("openai", "gpt-4o-mini"),
    ("anthropic", "claude-sonnet-4-20250514"),
    ("google", "gemini-2.0-flash"),
])
def test_llm_provider_models(provider, model):
    """Test different provider/model combinations."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = provider
    config["quick_think_llm"] = model

    ta = TradingAgentsGraph(config=config)
    assert ta.quick_thinking_llm is not None
```

## Error Testing

### Testing Exceptions

```python
def test_missing_api_key_raises_error():
    """Test error when API key is missing."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openai"

    # Clear environment variable
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            TradingAgentsGraph(config=config)
```

### Testing Error Messages

```python
def test_invalid_ticker_error_message():
    """Test error message for invalid ticker."""
    with pytest.raises(ValueError) as exc_info:
        validate_ticker("123INVALID")

    assert "Invalid ticker format" in str(exc_info.value)
```

## Best Practices

1. **Clear Test Names**: Use descriptive names following `test_<what>_<scenario>_<expected>`
2. **One Assertion Per Test**: Focus on single behavior
3. **Use Fixtures**: Avoid code duplication in setup
4. **Mock External Dependencies**: Don't hit real APIs in unit tests
5. **Test Edge Cases**: Include boundary conditions
6. **Document Complex Tests**: Add docstrings explaining what's being tested
7. **Keep Tests Fast**: Unit tests should run in <1 second
8. **Independent Tests**: Each test should run in isolation
9. **Meaningful Assertions**: Assert specific values, not just "not None"
10. **Clean Up**: Use fixtures for setup/teardown

## Common Patterns

### Testing Configuration

```python
def test_configuration_override():
    """Test configuration can be overridden."""
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 5

    ta = TradingAgentsGraph(config=config)

    assert ta.config["max_debate_rounds"] == 5
```

### Testing State Management

```python
def test_agent_state_update():
    """Test agent state is updated correctly."""
    state = AgentState(ticker="NVDA", date="2024-05-10")

    state.analyst_reports["market"] = "Test report"

    assert "market" in state.analyst_reports
    assert state.analyst_reports["market"] == "Test report"
```

### Testing Retry Logic

```python
def test_retry_on_rate_limit():
    """Test retry logic on rate limit error."""
    from tradingagents.utils.exceptions import LLMRateLimitError

    llm = Mock()
    llm.invoke.side_effect = [
        LLMRateLimitError(provider="openai", retry_after=1),
        Mock(content="Success")
    ]

    # Function should retry and succeed
    result = function_with_retry(llm)

    assert "Success" in result
    assert llm.invoke.call_count == 2
```

## See Also

- [Testing Overview](README.md)
- [Running Tests](running-tests.md)
- [Test Organization Best Practices](../../.claude/skills/testing-guide/docs/test-organization-best-practices.md)
