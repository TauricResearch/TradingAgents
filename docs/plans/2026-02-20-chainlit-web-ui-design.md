# TradingAgents Chainlit Web UI — Design

## Summary

Add a Chainlit web UI to TradingAgents so it can be deployed on Railway as a web service. Users interact via chat messages (e.g., "Analyze NVDA") and see live agent progress streamed into the browser.

## Architecture

Thin Chainlit wrapper around the existing `TradingAgentsGraph` programmatic API. ~150 lines of new code in a single `app.py`.

## Components

### `app.py` (Chainlit entry point)

- `@cl.on_chat_start` — Welcome message explaining usage (e.g., "Type a ticker like `NVDA` or `Analyze AAPL 2024-12-01`")
- `@cl.on_message` — Parse ticker + optional date from user message, create `TradingAgentsGraph` with Anthropic config, run `propagate()` in debug mode, stream Chainlit `Step` messages for each agent phase, send final decision as formatted message

### `Dockerfile`

- Python 3.13-slim base
- Install requirements.txt
- Expose `$PORT`
- `CMD: chainlit run app.py --host 0.0.0.0 --port $PORT`

### `railway.toml`

- Build from Dockerfile
- Health check on `/`

### Railway Environment Variables

- `ANTHROPIC_API_KEY` — required, for Claude models
- `PORT` — auto-set by Railway

## LLM Configuration

- Provider: `anthropic`
- Quick-think model: `claude-haiku-4-5-20251001`
- Deep-think model: `claude-sonnet-4-5-20241022`
- Data vendor: `yfinance` (no extra API keys needed)

## Data Flow

```
User message: "Analyze NVDA"
  -> Parse: ticker=NVDA, date=today
  -> TradingAgentsGraph(config={anthropic, haiku/sonnet})
  -> graph.propagate("NVDA", "2026-02-20")
     -> Debug stream chunks
     -> Each chunk -> Chainlit Step (Analyst, Research, Trading, Risk, Portfolio)
  -> Final decision -> formatted Chainlit message with markdown
```

## Message Parsing

Simple regex/string parsing:
- `"NVDA"` -> ticker=NVDA, date=today
- `"Analyze AAPL 2024-12-01"` -> ticker=AAPL, date=2024-12-01
- `"What's the outlook for TSLA?"` -> ticker=TSLA, date=today
- Extract uppercase 1-5 letter words as potential tickers

## Deployment

1. Push changes to `github.com/dtarkent2-sys/TradingAgents` main branch
2. Create Railway service from GitHub repo
3. Set `ANTHROPIC_API_KEY` env var
4. Railway auto-deploys, Chainlit serves on assigned PORT
