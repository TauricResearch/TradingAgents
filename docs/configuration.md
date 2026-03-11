# Configuration Reference — DEXAgents

All configuration is via environment variables in `.env` or shell exports.

---

## LLM Providers

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | One required | OpenAI GPT models |
| `GOOGLE_API_KEY` | One required | Google Gemini models |
| `ANTHROPIC_API_KEY` | One required | Anthropic Claude models |
| `XAI_API_KEY` | One required | xAI Grok models |
| `OPENROUTER_API_KEY` | One required | OpenRouter (multi-model) |

Configure the active provider in `default_config.py` or at runtime:
```python
config["llm_provider"] = "openai"  # openai, google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-4o"
config["quick_think_llm"] = "gpt-4o-mini"
```

---

## DEX Data Providers (Scenario 1)

| Variable | Required | Description |
|---|---|---|
| `COINGECKO_API_KEY` | No | CoinGecko Pro key (free tier available) |
| `BIRDEYE_API_KEY` | Yes | Birdeye Solana analytics |

> DeFiLlama requires no API key.

---

## On-Chain Execution (Scenario 2)

### Solana

| Variable | Required | Description |
|---|---|---|
| `SOLANA_RPC_URL` | Yes | RPC endpoint (default: mainnet-beta) |
| `SOLANA_PRIVATE_KEY` | Yes | Wallet private key (base58) — **never commit!** |

> Recommended RPC: Helius, Alchemy, or QuickNode for production.

### EVM (Ethereum / Base / Arbitrum)

| Variable | Required | Description |
|---|---|---|
| `ETH_RPC_URL` | Yes | EVM RPC endpoint |
| `ETH_PRIVATE_KEY` | Yes | Wallet private key (hex) — **never commit!** |
| `ONEINCH_API_KEY` | Yes | 1inch API key (free at dev.1inch.io) |

---

## Google Custom Search (Web Research Analyst)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_SEARCH_API_KEY` | Yes | — | Google Cloud API key |
| `GOOGLE_SEARCH_ENGINE_ID` | Yes | — | Custom Search Engine ID (`cx`) |
| `GOOGLE_SEARCH_DAILY_LIMIT` | No | `95` | Hard cap on queries/day |

> **Free tier:** 100 queries/day. The default limit of 95 leaves a 5-query safety margin.
> To increase: enable billing in Google Cloud Console and raise `GOOGLE_SEARCH_DAILY_LIMIT`.

---

## Infrastructure (Scenario 3)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379`) |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot for alerts |
| `TELEGRAM_CHAT_ID` | No | Target chat for alerts |

---

## Runtime Configuration (`default_config.py`)

```python
DEFAULT_CONFIG = {
    # LLM
    "llm_provider": "openai",
    "deep_think_llm": "gpt-4o",
    "quick_think_llm": "gpt-4o-mini",

    # Debate rounds
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,

    # Data vendors (stock layer, legacy)
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    },
}
```
