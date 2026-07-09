# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgents is a LangGraph-based multi-agent LLM financial trading analysis framework. This is **David's fork**, optimized primarily for the **China A-share market** as the main use case, with A-share data providers (tushare/akshare), Tavily news curation, an Evidence Steward gate, and other enhancements on top of upstream (TauricResearch/TradingAgents). Non-A-share tickers (US/crypto/commodity/forex) are supported but secondary.

## Common Commands

```bash
# Install (dev mode)
pip install -e .                          # base install
pip install -e ".[china]"                 # with A-share data sources (akshare, tushare)

# CLI entry
tradingagents                            # interactive CLI
tradingagents analyze                    # jump straight to analysis
python -m cli.main                       # equivalent

# Tests
pytest                                    # all tests
pytest -m unit                            # unit tests only
pytest -m integration                     # integration tests (require external services)
pytest -m smoke                           # smoke tests
pytest tests/path/to/test_file.py         # single test file
pytest -k "test_name_pattern"             # filter by name

# Docker
docker compose up tradingagents           # run tradingagents service
docker compose --profile ollama up        # with local Ollama
```

## Core Architecture

### LangGraph Pipeline Flow

```
START → Analyst Team (sequential, configurable: market/social/news/fundamentals)
  → Evidence Steward (assesses evidence quality; enriches via Tavily if thin)
  → Bull Researcher ↔ Bear Researcher (multi-round debate, judged by Research Manager)
  → Trader (produces transaction proposal)
  → Aggressive ↔ Conservative ↔ Neutral (risk management 3-way debate)
  → Portfolio Manager (structured final decision: Buy/Overweight/Hold/Underweight/Sell)
  → END
```

Key concepts:
- **Two LLM paths**: `deep_thinking_llm` (Research Manager and Portfolio Manager) and `quick_thinking_llm` (all other agents), both created in `TradingAgentsGraph.__init__`
- **Each Analyst node** is 3 sub-nodes: agent → conditional edge → tool node (loop) or clear node (proceed), defined in `GraphSetup.setup_graph()`
- **AgentState** (`tradingagents/agents/utils/agent_states.py`) is the single shared TypedDict state flowing through the entire graph — all agent outputs are written into it
- **Checkpoint/Resume**: via `langgraph-checkpoint-sqlite`, one SQLite DB per ticker; a crashed run can resume from the last successful node on the same ticker+date
- **Memory Log**: `TradingMemoryLog` persists decision logs; on the next same-ticker run, deferred reflection runs (fetch realized returns → LLM reflection → store for future agents)

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `tradingagents/graph/` | LangGraph orchestration: graph construction, conditional routing, state propagation, checkpoint, reflection, signal processing |
| `tradingagents/agents/` | All LLM agent implementations + tool methods + Pydantic structured-output schemas |
| `tradingagents/dataflows/` | Data ingestion layer: vendor fallback chains, A-share supplementation, news curation, consistency/credibility detection |
| `tradingagents/llm_clients/` | LLM provider abstraction: factory pattern routing to OpenAI-compatible / Anthropic / Google / Azure |
| `tradingagents/default_config.py` | **Single source of truth for all configuration**, supports `TRADINGAGENTS_*` env-var overrides |
| `cli/` | Typer + Rich interactive CLI |
| `tests/` | pytest suite (40 test files), conftest auto-injects dummy API keys |

### Data Fetching Fallback Chain

Data calls route through `tradingagents/dataflows/interface.py` → `route_to_vendor()`:
- **Core stock data**: yfinance → tushare → akshare → alpha_vantage
- **A-share handling**: auto-supplements tushare/akshare when yfinance coverage is insufficient
- **News**: multi-source parallel fetch → deduplication → credibility scoring → cross-source consistency detection → curated output
- Each tool method can be individually vendor-configured; tool-level config takes precedence over category-level

### LLM Provider Support

`factory.py` dispatches by provider name:
- OpenAI-compatible protocol: openai, xai, deepseek, qwen, glm, minimax, ollama, openrouter → `OpenAIClient`
- Anthropic protocol: anthropic, mimo → `AnthropicClient`
- Google Gemini: google → `GoogleClient`
- Azure OpenAI: azure → `AzureOpenAIClient`

### Fork-Specific Features (vs upstream)

1. **A-share support**: `tradingagents/dataflows/china_data.py`, auto-supplements yfinance gaps with tushare/akshare
2. **Tavily news**: `tradingagents/dataflows/tavily_news.py`, news data source
3. **Evidence Steward**: `tradingagents/agents/evidence_steward.py`, assesses evidence quality, enriches via Tavily when insufficient
4. **News Advisor**: LLM-driven coverage gap analysis + targeted search
5. **Credibility Scoring**: `tradingagents/dataflows/credibility.py`, news source credibility scoring
6. **Cross-source Consistency**: `tradingagents/dataflows/consistency.py`, cross-source consistency detection
7. **Market Data Validator**: `tradingagents/dataflows/market_data_validator.py`
8. **Symbol Normalization**: `tradingagents/dataflows/symbol_utils.py`

## Design Principles

- **First-principles reasoning**: When making design decisions, derive from fundamental requirements and constraints rather than mimicking existing implementations
- **Stop and ask when uncertain**: If anything is unclear or unconfirmed, pause and clarify before proceeding — never assume
- **Single source of truth for config**: All configurable items must be managed through `default_config.py`'s `DEFAULT_CONFIG` dict + `_ENV_OVERRIDES` mapping
- **Structured output**: Research Manager / Trader / Portfolio Manager use Pydantic schemas to constrain LLM output; `render_*` functions convert back to markdown for downstream consumers
- **Fail-open on data**: Data fetch failures do not block the pipeline; after fallback chain exhaustion, a `NO_DATA_AVAILABLE` sentinel is returned so agents report unavailability rather than fabricating data
- **A-share-first identity resolution**: A-share tickers resolve identity via the local 3-tier chain (tushare -> akshare -> yfinance) in `resolve_canonical_company_profile()`; non-A-share tickers use upstream `resolve_instrument_identity()` (yfinance). The branch lives in `TradingAgentsGraph.resolve_instrument_context()`. Never bypass the local chain for A-shares - yfinance coverage is poor and often returns wrong/English names.
