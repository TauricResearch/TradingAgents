<!-- Last verified: 2026-03-23 -->

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

## AgentOS Frontend Dependencies

From `agent_os/frontend/package.json`:

| Package | Constraint | Purpose |
|---------|-----------|---------|
| `react` | `^18.3.0` | UI framework |
| `react-dom` | `^18.3.0` | React DOM rendering |
| `@chakra-ui/react` | `^2.10.0` | Component library (dark theme) |
| `@emotion/react` | `^11.13.0` | CSS-in-JS for Chakra |
| `@emotion/styled` | `^11.13.0` | Styled components for Chakra |
| `framer-motion` | `^10.18.0` | Animation library (Chakra dependency) |
| `reactflow` | `^11.11.0` | Graph/DAG visualization for agent workflow |
| `axios` | `^1.13.5` | HTTP client for REST API calls |
| `lucide-react` | `^0.460.0` | Icon library |

Dev dependencies: TypeScript `^5.6.0`, Vite `^8.0.1`, ESLint `^8.57.0`, TailwindCSS `^3.4.0`.

## AgentOS Backend Dependencies

From `pyproject.toml` (additions for agent_os):

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework for REST + WebSocket backend |
| `uvicorn` | ASGI server (port 8088) |
| `httpx` | Async HTTP client (used by FastAPI test client) |

## AgentOS Build & Run

| Command | Description |
|---------|-------------|
| `uvicorn agent_os.backend.main:app --host 0.0.0.0 --port 8088` | Start backend |
| `cd agent_os/frontend && npm run dev` | Start frontend (Vite dev server, port 5173) |
| `cd agent_os/frontend && npx vite build` | Production build |
| `cd agent_os/frontend && node_modules/.bin/tsc --noEmit` | TypeScript check |
