# Structured Output Implementation Guide

This guide shows how to use structured outputs in TradingAgents to eliminate manual parsing and improve reliability.

## Overview

Structured outputs use Pydantic schemas to ensure LLM responses match expected formats. This eliminates:
- Manual JSON parsing
- String manipulation errors
- Type validation issues
- Response format inconsistencies

## Available Schemas

Located in `tradingagents/schemas/llm_outputs.py`:

- **TradeDecision**: Trading decisions (BUY/SELL/HOLD) with rationale
- **TickerList**: List of validated ticker symbols
- **MarketMovers**: Market gainers and losers
- **InvestmentOpportunity**: Ranked investment opportunities
- **RankedOpportunities**: Multiple opportunities with market context
- **DebateDecision**: Research manager debate decisions
- **RiskAssessment**: Risk management decisions

## Usage Examples

### Basic Usage

```python
from tradingagents.schemas import TickerList
from tradingagents.utils.structured_output import get_structured_llm

# Configure LLM for structured output
structured_llm = get_structured_llm(llm, TickerList)

# Get structured response
response = structured_llm.invoke([HumanMessage(content=prompt)])

# Response is a dict matching the schema
tickers = response.get("tickers", [])
```

### Discovery Graph Example

```python
# Before (manual parsing):
response = llm.invoke([HumanMessage(content=prompt)])
content = response.content.replace("```json", "").replace("```", "").strip()
movers = json.loads(content)  # Can fail!

# After (structured output):
from tradingagents.schemas import MarketMovers

structured_llm = llm.with_structured_output(
    schema=MarketMovers.model_json_schema(),
    method="json_schema"
)
response = structured_llm.invoke([HumanMessage(content=prompt)])
movers = response.get("movers", [])  # Always valid!
```

### Trade Decision Example

```python
from tradingagents.schemas import TradeDecision

structured_llm = get_structured_llm(llm, TradeDecision)

prompt = "Based on this analysis, should I buy AAPL?"
response = structured_llm.invoke(prompt)

# Guaranteed structure:
decision = response["decision"]  # "BUY", "SELL", or "HOLD"
rationale = response["rationale"]  # string
confidence = response["confidence"]  # "high", "medium", or "low"
key_factors = response["key_factors"]  # list of strings
```

## Implementation Checklist

When adding structured outputs to a new area:

1. **Define Schema**: Create or use existing Pydantic model in `schemas/llm_outputs.py`
2. **Update Prompt**: Modify prompt to request JSON output matching schema
3. **Configure LLM**: Use `with_structured_output()` or `get_structured_llm()`
4. **Access Response**: Use dict access instead of parsing
5. **Remove Parsing**: Delete old JSON parsing, regex, or string manipulation code

## Current Implementation Status

✅ **Implemented**:
- Discovery Graph ticker extraction (Reddit, Twitter)
- Discovery Graph market movers parsing

🔄 **Recommended Next**:
- Trader final decision extraction
- Research manager debate decisions
- Risk manager assessments
- Discovery ranker output

## Benefits

- **Type Safety**: Pydantic validates all fields
- **No Parsing Errors**: No more `json.loads()` failures
- **Better Prompts**: Schema defines exact output format
- **Easier Testing**: Mock responses match schema
- **Self-Documenting**: Schema shows expected structure

## Adding New Schemas

1. Define in `tradingagents/schemas/llm_outputs.py`:

```python
class MySchema(BaseModel):
    field1: str = Field(description="What this field contains")
    field2: Literal["option1", "option2"] = Field(description="Limited choices")
    field3: List[str] = Field(description="List of items")
```

2. Export in `tradingagents/schemas/__init__.py`

3. Use in your code:

```python
from tradingagents.schemas import MySchema

structured_llm = llm.with_structured_output(
    schema=MySchema.model_json_schema(),
    method="json_schema"
)
```

## Provider Support

Structured outputs work with:
- ✅ OpenAI (GPT-4, GPT-3.5)
- ✅ Google (Gemini models)
- ✅ Anthropic (Claude models)
- ✅ Local models via Ollama/OpenRouter

All use the same `with_structured_output()` API.
