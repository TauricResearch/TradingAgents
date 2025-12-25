# LLM Integration Architecture

This document describes how TradingAgents integrates with different Large Language Model (LLM) providers through a unified abstraction layer.

## Overview

TradingAgents supports multiple LLM providers through a flexible configuration system that allows switching between providers without code changes.

## Supported Providers

### OpenAI
- **Models**: GPT-4o, GPT-4o-mini, o4-mini (default), o1-preview
- **Strengths**: Strong reasoning, reliable, extensive fine-tuning
- **Use Case**: Default choice for production
- **API Key**: `OPENAI_API_KEY`
- **Endpoint**: `https://api.openai.com/v1`

### Anthropic
- **Models**: Claude Sonnet 4, Claude Opus 4
- **Strengths**: Strong reasoning, long context windows, excellent instruction following
- **Use Case**: Alternative to OpenAI, good for complex analysis
- **API Key**: `ANTHROPIC_API_KEY`
- **Endpoint**: `https://api.anthropic.com`

### OpenRouter
- **Models**: Unified access to 100+ models from multiple providers
- **Strengths**: Single API for multiple providers, competitive pricing
- **Use Case**: Flexibility, cost optimization, accessing diverse models
- **API Key**: `OPENROUTER_API_KEY` (plus `OPENAI_API_KEY` for embeddings)
- **Endpoint**: `https://openrouter.ai/api/v1`

### Google Generative AI
- **Models**: Gemini 2.0 Flash, Gemini Pro
- **Strengths**: Fast inference, multimodal capabilities
- **Use Case**: Cost-effective alternative, multimodal analysis
- **API Key**: `GOOGLE_API_KEY`
- **Endpoint**: Built-in (no custom endpoint)

### Ollama
- **Models**: Local models (Llama, Mistral, etc.)
- **Strengths**: No API costs, data privacy, offline operation
- **Use Case**: Development, experimentation, privacy-sensitive analysis
- **API Key**: None (local)
- **Endpoint**: `http://localhost:11434/v1`

## Provider Abstraction

### Configuration-Driven Selection

LLM providers are selected through configuration:

```python
config = {
    "llm_provider": "openai",  # Provider selection
    "deep_think_llm": "o4-mini",  # Model for complex reasoning
    "quick_think_llm": "gpt-4o-mini",  # Model for fast tasks
    "backend_url": "https://api.openai.com/v1"
}
```

### Initialization Logic

The `TradingAgentsGraph` class handles provider initialization:

```python
if config["llm_provider"].lower() in ("openai", "ollama"):
    from langchain_openai import ChatOpenAI

    self.deep_thinking_llm = ChatOpenAI(
        model=config["deep_think_llm"],
        base_url=config["backend_url"]
    )
    self.quick_thinking_llm = ChatOpenAI(
        model=config["quick_think_llm"],
        base_url=config["backend_url"]
    )

elif config["llm_provider"].lower() == "anthropic":
    from langchain_anthropic import ChatAnthropic

    self.deep_thinking_llm = ChatAnthropic(
        model=config["deep_think_llm"],
        base_url=config["backend_url"]
    )
    self.quick_thinking_llm = ChatAnthropic(
        model=config["quick_think_llm"],
        base_url=config["backend_url"]
    )

elif config["llm_provider"].lower() == "openrouter":
    from langchain_openai import ChatOpenAI

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY required")

    default_headers = {
        "HTTP-Referer": "https://github.com/TauricResearch/TradingAgents",
        "X-Title": "TradingAgents"
    }

    self.deep_thinking_llm = ChatOpenAI(
        model=config["deep_think_llm"],
        base_url=config["backend_url"],
        api_key=openrouter_key,
        default_headers=default_headers
    )
    self.quick_thinking_llm = ChatOpenAI(
        model=config["quick_think_llm"],
        base_url=config["backend_url"],
        api_key=openrouter_key,
        default_headers=default_headers
    )

elif config["llm_provider"].lower() == "google":
    from langchain_google_genai import ChatGoogleGenerativeAI

    self.deep_thinking_llm = ChatGoogleGenerativeAI(
        model=config["deep_think_llm"]
    )
    self.quick_thinking_llm = ChatGoogleGenerativeAI(
        model=config["quick_think_llm"]
    )
```

Location: `tradingagents/graph/trading_graph.py`

## Model Selection Strategy

### Two-Tier Model Approach

TradingAgents uses two types of LLMs for different tasks:

#### Deep Thinking LLM
- **Purpose**: Complex reasoning, strategic analysis, debate moderation
- **Characteristics**: Larger models, slower, more expensive, higher quality
- **Use Cases**:
  - Researcher debate moderation
  - Trading decision synthesis
  - Risk assessment evaluation
- **Recommended Models**:
  - OpenAI: o4-mini, o1-preview
  - Anthropic: claude-sonnet-4, claude-opus-4
  - OpenRouter: anthropic/claude-sonnet-4.5

#### Quick Thinking LLM
- **Purpose**: Fast analysis, data summarization, routine tasks
- **Characteristics**: Smaller models, faster, cost-effective
- **Use Cases**:
  - Analyst report generation
  - Data interpretation
  - Tool calling
- **Recommended Models**:
  - OpenAI: gpt-4o-mini, gpt-4o
  - Anthropic: claude-sonnet-4
  - OpenRouter: openai/gpt-4o-mini

### Model Selection Guidelines

**For Production:**
```python
config["deep_think_llm"] = "o1-preview"      # Best reasoning
config["quick_think_llm"] = "gpt-4o-mini"    # Cost-effective
```

**For Development/Testing:**
```python
config["deep_think_llm"] = "o4-mini"         # Fast and cheaper
config["quick_think_llm"] = "gpt-4o-mini"    # Consistent quality
```

**For Cost Optimization:**
```python
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "anthropic/claude-sonnet-4.5"
config["quick_think_llm"] = "openai/gpt-4o-mini"
```

## Provider-Specific Configuration

### OpenAI Configuration

```python
config = {
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1"
}
```

Environment:
```bash
export OPENAI_API_KEY=sk-your_key_here
```

### Anthropic Configuration

```python
config = {
    "llm_provider": "anthropic",
    "deep_think_llm": "claude-sonnet-4-20250514",
    "quick_think_llm": "claude-sonnet-4-20250514",
    "backend_url": "https://api.anthropic.com"
}
```

Environment:
```bash
export ANTHROPIC_API_KEY=sk-ant-your_key_here
```

### OpenRouter Configuration

```python
config = {
    "llm_provider": "openrouter",
    "deep_think_llm": "anthropic/claude-sonnet-4.5",
    "quick_think_llm": "openai/gpt-4o-mini",
    "backend_url": "https://openrouter.ai/api/v1"
}
```

Environment:
```bash
export OPENROUTER_API_KEY=sk-or-v1-your_key_here
export OPENAI_API_KEY=sk-your_key_here  # Required for embeddings
```

**Note**: OpenRouter uses `provider/model-name` format:
- `anthropic/claude-sonnet-4.5`
- `openai/gpt-4o`
- `google/gemini-pro`

### Google Generative AI Configuration

```python
config = {
    "llm_provider": "google",
    "deep_think_llm": "gemini-2.0-flash",
    "quick_think_llm": "gemini-2.0-flash"
}
```

Environment:
```bash
export GOOGLE_API_KEY=your_key_here
```

### Ollama Configuration

```python
config = {
    "llm_provider": "ollama",
    "deep_think_llm": "mistral",
    "quick_think_llm": "mistral",
    "backend_url": "http://localhost:11434/v1"
}
```

Prerequisites:
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull mistral

# Start Ollama server
ollama serve
```

## Error Handling

### Rate Limit Handling

Unified rate limit error handling across providers:

```python
from tradingagents.utils.exceptions import LLMRateLimitError

try:
    response = llm.invoke(messages)
except LLMRateLimitError as e:
    print(f"Rate limit hit: {e.message}")
    if e.retry_after:
        print(f"Retry after {e.retry_after} seconds")
```

Location: `tradingagents/utils/exceptions.py`

### Provider-Specific Errors

Each provider may raise different errors:

**OpenAI:**
- `RateLimitError` → Retry after specified time
- `InvalidRequestError` → Check model name, parameters
- `AuthenticationError` → Verify API key

**Anthropic:**
- `RateLimitError` → Retry with backoff
- `InvalidRequestError` → Check message format
- `APIError` → Server-side issues

**OpenRouter:**
- Follows OpenAI error format
- Additional headers required for attribution

### Fallback Strategy

Implement provider fallback for resilience:

```python
providers = ["openai", "anthropic", "openrouter"]

for provider in providers:
    try:
        config["llm_provider"] = provider
        ta = TradingAgentsGraph(config=config)
        result = ta.propagate(ticker, date)
        break
    except LLMRateLimitError:
        continue
```

## Cost Optimization

### Model Cost Comparison

**Deep Thinking Tasks:**
| Provider | Model | Cost/1M Tokens (Input/Output) |
|----------|-------|-------------------------------|
| OpenAI | o4-mini | $1.50 / $6.00 |
| OpenAI | o1-preview | $15.00 / $60.00 |
| Anthropic | claude-sonnet-4 | $3.00 / $15.00 |
| OpenRouter | Varies by model | Check OpenRouter pricing |

**Quick Thinking Tasks:**
| Provider | Model | Cost/1M Tokens (Input/Output) |
|----------|-------|-------------------------------|
| OpenAI | gpt-4o-mini | $0.15 / $0.60 |
| OpenAI | gpt-4o | $2.50 / $10.00 |
| Google | gemini-2.0-flash | Free tier available |
| Ollama | Local models | Free (local) |

### Cost Reduction Strategies

1. **Use Smaller Models for Simple Tasks**
   ```python
   config["quick_think_llm"] = "gpt-4o-mini"  # Instead of gpt-4o
   ```

2. **Reduce Debate Rounds**
   ```python
   config["max_debate_rounds"] = 1  # Instead of 2-3
   ```

3. **Use OpenRouter for Competitive Pricing**
   ```python
   config["llm_provider"] = "openrouter"
   ```

4. **Cache LLM Responses**
   ```python
   # Implemented in agent memory system
   memory.store_analysis(ticker, date, result)
   ```

5. **Use Ollama for Development**
   ```python
   config["llm_provider"] = "ollama"  # No API costs
   ```

## Embeddings

### Embedding Provider

TradingAgents uses OpenAI embeddings for vector storage (memory system):

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
```

**Important**: Even when using non-OpenAI LLM providers (Anthropic, Google, etc.), `OPENAI_API_KEY` is still required for embeddings.

### Alternative Embedding Providers

For fully offline operation, consider:

```python
from langchain_community.embeddings import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
```

Note: This requires updating the memory initialization code.

## Performance Considerations

### Latency

**Provider Latency (Approximate):**
- OpenAI: 1-3 seconds per request
- Anthropic: 1-2 seconds per request
- Google: 0.5-1.5 seconds per request
- OpenRouter: Varies by underlying model
- Ollama: 0.5-5 seconds (depends on local hardware)

### Throughput

**Concurrent Requests:**
- OpenAI: Tier-based limits (20-5000 RPM)
- Anthropic: Tier-based limits (50-2000 RPM)
- OpenRouter: Model-specific limits
- Ollama: Limited by local GPU/CPU

### Caching

LangChain provides built-in caching:

```python
from langchain.cache import SQLiteCache
from langchain.globals import set_llm_cache

set_llm_cache(SQLiteCache(database_path=".langchain.db"))
```

## Best Practices

1. **Set API Keys as Environment Variables**: Never hardcode keys
2. **Use Two-Tier Model Strategy**: Deep/quick thinking separation
3. **Implement Error Handling**: Catch rate limits and retry
4. **Monitor Costs**: Track token usage and expenses
5. **Test with Cheaper Models**: Use o4-mini/gpt-4o-mini for development
6. **Cache When Possible**: Avoid redundant API calls
7. **Use OpenRouter for Flexibility**: Easy switching between providers
8. **Implement Timeouts**: Prevent hanging requests
9. **Log API Usage**: Track which models are called
10. **Consider Local Models**: Ollama for sensitive data or development

## References

- [Multi-Agent System](multi-agent-system.md)
- [Configuration Guide](../guides/configuration.md)
- [Adding LLM Provider Guide](../guides/adding-llm-provider.md)
- [TradingGraph API](../api/trading-graph.md)
