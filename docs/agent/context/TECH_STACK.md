<!-- Last verified: 2026-03-18 -->

# Tech Stack

## Python Version

`>=3.10` (from `pyproject.toml` `requires-python`)

## Core Dependencies

All from `pyproject.toml` `[project.dependencies]`:

| Package | Constraint | Purpose |
|---------|-----------|---------|
| `langchain-core` | `>=0.3.81` | Base LangChain abstractions, messages, tools |
| `langchain-anthropic` | `>=0.3.15` | Anthropic LLM provider |
| `langchain-google-genai` | `>=2.1.5` | Google Gemini LLM provider |
| `langchain-openai` | `>=0.3.23` | OpenAI/xAI/OpenRouter/Ollama LLM provider |
| `langchain-experimental` | `>=0.3.4` | Experimental LangChain features |
| `langgraph` | `>=0.4.8` | Graph-based agent orchestration |
| `yfinance` | `>=0.2.63` | Primary data vendor (stocks, fundamentals, news) |
| `pandas` | `>=2.3.0` | DataFrame operations for financial data |
| `stockstats` | `>=0.6.5` | Technical indicators from OHLCV data |
| `python-dotenv` | `>=1.0.0` | `.env` file loading |
| `typer` | `>=0.21.0` | CLI framework |
| `rich` | `>=14.0.0` | Terminal UI (panels, tables, live display) |
| `requests` | `>=2.32.4` | HTTP client for AV/Finnhub APIs |
| `redis` | `>=6.2.0` | Caching layer |
| `questionary` | `>=2.1.0` | Interactive CLI prompts |
| `backtrader` | `>=1.9.78.123` | Backtesting framework |
| `chainlit` | `>=2.5.5` | Web UI framework |
| `parsel` | `>=1.10.0` | HTML/XML parsing |
| `rank-bm25` | `>=0.2.2` | BM25 text ranking |
| `pytz` | `>=2025.2` | Timezone handling |
| `tqdm` | `>=4.67.1` | Progress bars |
| `typing-extensions` | `>=4.14.0` | Backported typing features |
| `setuptools` | `>=80.9.0` | Package build system |

## Dev Dependencies

From `[dependency-groups]`:

| Package | Constraint | Purpose |
|---------|-----------|---------|
| `pytest` | `>=9.0.2` | Test framework |

## External APIs

| Service | Auth Env Var | Rate Limit | Primary Use |
|---------|-------------|-----------|-------------|
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | 75/min (premium) | Fallback data vendor |
| Finnhub | `FINNHUB_API_KEY` | 60/min (free) | Insider transactions, calendars |
| OpenAI | `OPENAI_API_KEY` | Per plan | Default LLM provider |
| Anthropic | `ANTHROPIC_API_KEY` | Per plan | LLM provider |
| Google | `GOOGLE_API_KEY` | Per plan | LLM provider (Gemini) |
| xAI | `XAI_API_KEY` | Per plan | LLM provider (Grok) |
| OpenRouter | `OPENROUTER_API_KEY` | Per plan | LLM provider (multi-model) |

## LLM Provider Support

| Provider | Config Value | Client Class | Notes |
|----------|-------------|-------------|-------|
| OpenAI | `"openai"` | `ChatOpenAI` | Default. `openai_reasoning_effort` optional. |
| Anthropic | `"anthropic"` | `ChatAnthropic` | — |
| Google | `"google"` | `ChatGoogleGenerativeAI` | `google_thinking_level` optional. |
| xAI | `"xai"` | `ChatOpenAI` | OpenAI-compatible endpoint. |
| OpenRouter | `"openrouter"` | `ChatOpenAI` | OpenAI-compatible endpoint. |
| Ollama | `"ollama"` | `ChatOpenAI` | OpenAI-compatible. Uses configured `base_url`. |

## Project Metadata

- Name: `tradingagents`
- Version: `0.2.1`
- Entry point: `tradingagents = cli.main:app`
- Package discovery: `tradingagents*`, `cli*`
