# Contributing Custom Agents

This guide explains how to create and register third-party trading agents using the generic agent interface.

## Interface Overview

Every agent implements `BaseAgent.analyze(AgentInput) -> AgentOutput`. This contract ensures agents are interchangeable, composable, and benchmarkable.

## Schemas

### AgentInput

```python
from tradingagents.agents import AgentInput

agent_input = AgentInput(
    ticker="AAPL",
    date="2025-01-15",
    context={
        "market_data": "...",
        "news": "...",
        "fundamentals": "...",
        "sentiment": "...",
        "technical_indicators": "...",
    },
)
```

| Field     | Type             | Required | Description                                      |
|-----------|------------------|----------|--------------------------------------------------|
| `ticker`  | `str`            | Yes      | Stock ticker symbol                              |
| `date`    | `str`            | Yes      | Analysis date                                    |
| `context` | `dict[str, str]` | No       | Optional data keyed by category (see keys above) |

### AgentOutput

| Field           | Type                                                        | Required | Description                    |
|-----------------|-------------------------------------------------------------|----------|--------------------------------|
| `rating`        | `"BUY" \| "OVERWEIGHT" \| "HOLD" \| "UNDERWEIGHT" \| "SELL"` | Yes      | 5-tier recommendation          |
| `confidence`    | `float` (0.0–1.0)                                          | Yes      | Confidence in the rating       |
| `price_targets` | `PriceTargets \| None`                                      | No       | Entry, target, and stop-loss   |
| `thesis`        | `str`                                                       | Yes      | One-paragraph investment thesis|
| `risk_factors`  | `list[str]`                                                 | No       | Key risks (defaults to `[]`)   |

### PriceTargets

| Field       | Type    | Description       |
|-------------|---------|-------------------|
| `entry`     | `float` | Entry price       |
| `target`    | `float` | Target price      |
| `stop_loss` | `float` | Stop-loss price   |

## Creating a Custom Agent

Subclass `BaseAgent` and implement `analyze`:

```python
from tradingagents.agents import BaseAgent, AgentInput, AgentOutput

class MyCustomAgent(BaseAgent):
    name: str = "my_custom_agent"

    def __init__(self, llm) -> None:
        self.llm = llm

    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        # Your analysis logic here — call self.llm, fetch data, etc.
        return AgentOutput(
            rating="HOLD",
            confidence=0.75,
            thesis="The stock shows mixed signals...",
            risk_factors=["Sector rotation risk", "Earnings uncertainty"],
        )
```

The `__init__` signature is flexible — the only hard requirement is that `analyze` accepts `AgentInput` and returns `AgentOutput`.

## Registering Your Agent

Use `AgentRegistry` to make your agent discoverable:

```python
from tradingagents.agents import AgentRegistry

registry = AgentRegistry()

# Register a class (lazy instantiation with kwargs)
registry.register("my_custom", MyCustomAgent, llm=my_llm)

# Or register a pre-built instance
agent = MyCustomAgent(llm=my_llm)
registry.register("my_custom", agent)

# Retrieve and use
agent = registry.get("my_custom")
output = agent.analyze(agent_input)

# List all registered agents
print(registry.list())
```

## Benchmarking Your Agent

Compare your agent across LLM backends:

```python
from tradingagents.agents import (
    AgentInput, LLMBackend, benchmark_agent, benchmark_agents,
)

agent_input = AgentInput(ticker="AAPL", date="2025-01-15")

backends = [
    LLMBackend(provider="openai", model="gpt-4o"),
    LLMBackend(provider="anthropic", model="claude-sonnet-4-20250514"),
    LLMBackend(provider="google", model="gemini-2.0-flash"),
]

# Single agent across backends
report = benchmark_agent(MyCustomAgent, agent_input, backends)

# Multiple agents across backends
report = benchmark_agents(
    [MyCustomAgent, FundamentalsAgent],
    agent_input,
    backends,
)

for row in report.summary():
    print(row)
```

Each `BenchmarkResult` contains: `agent_name`, `provider`, `model`, `output`, `elapsed_seconds`, and `error` (if any).

## Checklist

Before submitting a PR with a new agent:

- [ ] Subclasses `BaseAgent`
- [ ] Sets a unique `name` class attribute
- [ ] `analyze()` accepts `AgentInput` and returns `AgentOutput`
- [ ] `rating` uses one of the 5 valid tiers
- [ ] `confidence` is between 0.0 and 1.0
- [ ] Agent is importable and added to `__all__` in `tradingagents/agents/__init__.py`
