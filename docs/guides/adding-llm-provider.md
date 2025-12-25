# Guide: Adding a New LLM Provider

This guide shows you how to add support for a new LLM provider to TradingAgents.

## Overview

Adding a new LLM provider involves:
1. Installing the provider's LangChain integration
2. Adding initialization logic
3. Configuring API keys
4. Testing the integration
5. Updating documentation

## Step 1: Install LangChain Integration

Most providers have official LangChain integrations:

```bash
# Example: Adding Cohere
pip install langchain-cohere

# Example: Adding Mistral
pip install langchain-mistral

# Example: Adding HuggingFace
pip install langchain-huggingface
```

Add the dependency to `requirements.txt`:

```txt
langchain-cohere>=0.1.0
```

## Step 2: Add Initialization Logic

Modify `tradingagents/graph/trading_graph.py`:

```python
# Add import at top of file
from langchain_cohere import ChatCohere  # Example for Cohere

class TradingAgentsGraph:
    def __init__(self, selected_analysts=None, debug=False, config=None):
        # ... existing initialization ...

        # Add your provider to the initialization logic
        elif config["llm_provider"].lower() == "cohere":
            self.deep_thinking_llm = ChatCohere(
                model=config["deep_think_llm"],
                cohere_api_key=os.getenv("COHERE_API_KEY")
            )
            self.quick_thinking_llm = ChatCohere(
                model=config["quick_think_llm"],
                cohere_api_key=os.getenv("COHERE_API_KEY")
            )

        # ... rest of initialization ...
```

## Step 3: Configure API Keys

### Add Environment Variable

Update `.env.example`:

```env
# LLM Provider API Keys
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
COHERE_API_KEY=your_cohere_key_here  # NEW
```

### Validate API Key

Add validation in initialization:

```python
elif config["llm_provider"].lower() == "cohere":
    cohere_key = os.getenv("COHERE_API_KEY")
    if not cohere_key:
        raise ValueError(
            "COHERE_API_KEY environment variable is required when using cohere provider. "
            "Set it with: export COHERE_API_KEY=your_key_here"
        )

    self.deep_thinking_llm = ChatCohere(
        model=config["deep_think_llm"],
        cohere_api_key=cohere_key
    )
```

## Step 4: Update Configuration

Add default configuration for your provider:

```python
# In a configuration example or documentation

config = {
    "llm_provider": "cohere",
    "deep_think_llm": "command-r-plus",  # Cohere model for deep thinking
    "quick_think_llm": "command-r",      # Cohere model for quick tasks
    "backend_url": None  # If provider doesn't need custom endpoint
}
```

## Step 5: Handle Provider-Specific Features

### Custom Headers

Some providers require specific headers:

```python
elif config["llm_provider"].lower() == "cohere":
    default_headers = {
        "X-Client-Name": "TradingAgents"
    }

    self.deep_thinking_llm = ChatCohere(
        model=config["deep_think_llm"],
        cohere_api_key=cohere_key,
        headers=default_headers
    )
```

### Model Name Formats

Handle provider-specific model naming:

```python
def _format_model_name(self, provider: str, model: str) -> str:
    """Format model name based on provider conventions."""
    if provider == "openrouter":
        # OpenRouter uses "provider/model" format
        return model if "/" in model else f"default/{model}"
    elif provider == "cohere":
        # Cohere uses simple model names
        return model.replace("cohere/", "")
    return model
```

### Rate Limiting

Implement provider-specific rate limit handling:

```python
from tradingagents.utils.exceptions import LLMRateLimitError

try:
    response = llm.invoke(messages)
except Exception as e:
    # Map provider-specific errors to unified exceptions
    if "rate_limit" in str(e).lower():
        raise LLMRateLimitError(
            provider="cohere",
            message=str(e),
            retry_after=60  # Default retry time
        )
    raise
```

## Step 6: Add Error Handling

Create unified error handling for your provider:

```python
# In tradingagents/utils/exceptions.py

class CohereLLMError(LLMError):
    """Cohere-specific LLM errors."""
    provider = "cohere"

def handle_cohere_error(error):
    """Convert Cohere errors to unified exceptions."""
    if "rate limit" in str(error).lower():
        return LLMRateLimitError(
            provider="cohere",
            message=str(error),
            retry_after=extract_retry_time(error)
        )
    return CohereLLMError(str(error))
```

## Step 7: Test Integration

Create tests for your provider:

```python
# tests/integration/test_cohere_provider.py

import pytest
import os
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

@pytest.fixture
def cohere_config():
    """Configuration for Cohere provider."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "cohere"
    config["deep_think_llm"] = "command-r-plus"
    config["quick_think_llm"] = "command-r"
    return config

@pytest.fixture
def mock_env_cohere(monkeypatch):
    """Mock Cohere API key."""
    monkeypatch.setenv("COHERE_API_KEY", "test_key")

def test_cohere_initialization(cohere_config, mock_env_cohere):
    """Test Cohere provider can be initialized."""
    ta = TradingAgentsGraph(config=cohere_config)

    assert ta.deep_thinking_llm is not None
    assert ta.quick_thinking_llm is not None

def test_cohere_missing_api_key(cohere_config):
    """Test error when API key is missing."""
    # Don't set COHERE_API_KEY
    with pytest.raises(ValueError, match="COHERE_API_KEY"):
        TradingAgentsGraph(config=cohere_config)

@pytest.mark.integration
def test_cohere_analysis(cohere_config, mock_env_cohere):
    """Test full analysis with Cohere provider."""
    ta = TradingAgentsGraph(
        selected_analysts=["market"],
        config=cohere_config
    )

    # This requires actual API key
    if not os.getenv("COHERE_API_KEY"):
        pytest.skip("COHERE_API_KEY not set")

    state, decision = ta.propagate("NVDA", "2024-05-10")

    assert decision["action"] in ["BUY", "SELL", "HOLD"]
    assert 0.0 <= decision["confidence_score"] <= 1.0
```

## Step 8: Update Documentation

### Update Configuration Guide

Add provider details to `docs/guides/configuration.md`:

```markdown
### Cohere Configuration

```python
config = {
    "llm_provider": "cohere",
    "deep_think_llm": "command-r-plus",
    "quick_think_llm": "command-r"
}
```

Environment:
```bash
export COHERE_API_KEY=your_key_here
```

**Models Available**:
- command-r-plus: Advanced reasoning
- command-r: Fast, cost-effective
- command: Basic model
```

### Update LLM Integration Docs

Add to `docs/architecture/llm-integration.md`:

```markdown
### Cohere
- **Models**: Command-R-Plus, Command-R, Command
- **Strengths**: Fast inference, multilingual support
- **Use Case**: Cost-effective alternative with good performance
- **API Key**: `COHERE_API_KEY`
- **Endpoint**: Built-in
```

## Step 9: Add Example Usage

Create example script `examples/cohere_example.py`:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Configure for Cohere
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "cohere"
config["deep_think_llm"] = "command-r-plus"
config["quick_think_llm"] = "command-r"

# Initialize
ta = TradingAgentsGraph(config=config)

# Run analysis
state, decision = ta.propagate("NVDA", "2024-05-10")

print(f"Decision: {decision['action']}")
print(f"Confidence: {decision['confidence_score']:.2%}")
```

## Provider-Specific Considerations

### OpenAI-Compatible APIs

For OpenAI-compatible APIs (e.g., local models):

```python
elif config["llm_provider"].lower() == "custom_openai":
    from langchain_openai import ChatOpenAI

    self.deep_thinking_llm = ChatOpenAI(
        model=config["deep_think_llm"],
        base_url=config["backend_url"],  # Custom endpoint
        api_key=os.getenv("CUSTOM_API_KEY")
    )
```

### Azure OpenAI

```python
elif config["llm_provider"].lower() == "azure":
    from langchain_openai import AzureChatOpenAI

    self.deep_thinking_llm = AzureChatOpenAI(
        deployment_name=config["deep_think_llm"],
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-15-preview"
    )
```

### HuggingFace

```python
elif config["llm_provider"].lower() == "huggingface":
    from langchain_huggingface import ChatHuggingFace

    self.deep_thinking_llm = ChatHuggingFace(
        model=config["deep_think_llm"],
        huggingfacehub_api_token=os.getenv("HUGGINGFACE_API_KEY")
    )
```

## Best Practices

1. **Follow LangChain Patterns**: Use official LangChain integrations when available
2. **Unified Error Handling**: Map provider errors to TradingAgents exceptions
3. **Environment Variables**: Always use environment variables for API keys
4. **Validation**: Validate API keys before usage
5. **Testing**: Write comprehensive tests for the integration
6. **Documentation**: Update all relevant documentation
7. **Examples**: Provide working examples
8. **Defaults**: Set sensible default models
9. **Rate Limits**: Implement retry logic
10. **Logging**: Add debug logging for troubleshooting

## Troubleshooting

### Import Errors

**Issue**: `ModuleNotFoundError: No module named 'langchain_cohere'`

**Solution**: Install the provider package
```bash
pip install langchain-cohere
```

### API Key Errors

**Issue**: `ValueError: COHERE_API_KEY environment variable is required`

**Solution**: Set the API key
```bash
export COHERE_API_KEY=your_key_here
```

### Model Name Errors

**Issue**: `Invalid model name: 'command-r-plus'`

**Solution**: Check provider documentation for correct model names

### Rate Limit Handling

**Issue**: Provider rate limits not being handled

**Solution**: Implement provider-specific error mapping
```python
except ProviderError as e:
    if "rate limit" in str(e).lower():
        raise LLMRateLimitError(provider="cohere", ...)
```

## See Also

- [LLM Integration Architecture](../architecture/llm-integration.md)
- [Configuration Guide](configuration.md)
- [Error Handling Patterns](error-handling.md)
- [Testing Guide](../testing/writing-tests.md)
