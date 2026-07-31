# TradingAgents

TradingAgents is a multi-agent financial research framework for US equities, China A-shares, Hong Kong stocks, and crypto tickers. This fork combines a 13-role decision workflow with evidence checks, configurable data routing, persistent research artifacts, and a localhost-only web workbench.

It is a research tool, not a broker, portfolio accounting system, or source of investment advice.

## What This Fork Provides

- **Evidence-aware research** with identity checks, source quality controls, and explicit low-confidence or failure states.
- **Native A-share support** through MootDX, Tushare, AKShare, EastMoney, Tencent, and other domestic data paths.
- **Multiple market and news sources** including Yahoo Finance, Alpha Vantage, Tavily, and FRED.
- **Config-first execution** through interactive prompts, environment variables, or a local JSON file.
- **Persistent runs** with reports, decision memory, and optional checkpoint recovery.
- **Local web workbench** for reading analyst reports, debates, tool activity, and the final decision.
- **Analyst presets and delegation hooks** for repeatable research workflows.

## How the 13-Role Workflow Works

```text
Market / Social / News / Fundamentals Analysts
                    ↓
             Evidence Steward
                    ↓
          Bull ↔ Bear Research Debate
                    ↓
             Research Manager
                    ↓
                  Trader
                    ↓
 Aggressive ↔ Conservative ↔ Neutral Risk Debate
                    ↓
             Portfolio Manager
```

The four analysts gather complementary evidence. The Evidence Steward validates the research package before the Bull and Bear researchers debate it. The Research Manager produces an investment plan, the Trader proposes an action, and three risk roles challenge that proposal before the Portfolio Manager returns the final decision.

## Quick Start

### Requirements

- Python 3.10 or newer
- API credentials for the LLM and data services you choose

### Install from source

```bash
git clone https://github.com/david188888/TradingAgents.git
cd TradingAgents
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[china,web]"
```

For a base installation without the China-data and web extras:

```bash
python -m pip install .
```

### Create local configuration

```bash
cp .env.example .env
cp tradingagents.config.example.json tradingagents.local.json
```

Both `.env` and `tradingagents.local.json` are ignored by Git. Add only the credentials and settings you need.

Start the interactive CLI:

```bash
tradingagents
```

## Configuration

You can select providers in three ways:

1. Follow the interactive CLI prompts.
2. Set `TRADINGAGENTS_*` and provider-specific variables in `.env`.
3. Edit `tradingagents.local.json` and pass it with `--config` when needed.

The interactive provider registry currently supports OpenAI, Google, Anthropic, Xiaomi MiMo, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter, Azure OpenAI, and Ollama. Available model IDs and provider defaults change over time; see [`tradingagents/llm_clients/model_catalog.py`](tradingagents/llm_clients/model_catalog.py) and [`tradingagents/default_config.py`](tradingagents/default_config.py) for the code-owned configuration.

Common optional credentials include:

| Purpose | Variables |
| --- | --- |
| LLM provider | `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, and the other provider keys in `.env.example` |
| China market data | `TUSHARE_TOKEN` or `TUSHARE_API_KEY` |
| News search | `TAVILY_API_KEY` or `TAVILY_API_KEYS` |
| US macro data | `FRED_API_KEY` |
| Remote Ollama | `OLLAMA_BASE_URL` |

The Python defaults and the JSON example intentionally serve different entry paths: `DEFAULT_CONFIG` currently uses DeepSeek, while `tradingagents.config.example.json` demonstrates a Xiaomi MiMo configuration. Choose explicitly rather than relying on either example unchanged.

## CLI Usage

```bash
# Historical interactive entry point
tradingagents

# Explicit analysis command
tradingagents analyze

# Enable checkpoint persistence and resume
tradingagents analyze --checkpoint

# Clear saved checkpoints before a run
tradingagents analyze --clear-checkpoints

# Use a specific local JSON configuration
tradingagents analyze --config path/to/config.json

# Validate an analyst preset without starting an LLM run
tradingagents inspect-preset path/to/preset.yaml
```

Checkpoint recovery is opt-in. The CLI remains interactive unless the corresponding values are supplied through configuration or environment variables.

## Local Web Workbench

Install the `web` extra, then run:

```bash
tradingagents web
```

To choose a port and open the browser automatically:

```bash
tradingagents web --port 8000 --open
```

The workbench:

- binds only to `127.0.0.1`;
- uses a React/TypeScript frontend with a FastAPI and SSE backend;
- runs the real TradingAgents graph;
- supports one active analysis at a time while retaining earlier runs; and
- stores run artifacts under `~/.tradingagents/web/runs/<run_id>/`.

The bundled frontend does not require Node.js at runtime. API keys are not included in browser state, event payloads, or stored run history. Remote LLM and data providers still receive the prompts, ticker queries, and source requests required to perform the selected analysis.

## Markets and Ticker Formats

| Market | Example |
| --- | --- |
| US equity | `AAPL` |
| Shanghai A-share | `600519.SS` |
| Shenzhen A-share | `000001.SZ` |
| Hong Kong equity | `0700.HK` |
| Crypto pair | `BTC-USD` |

Data availability depends on the selected vendors, credentials, instrument, and date. A-share users should install the `china` extra and review the China-data documentation below.

## Python API

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["max_debate_rounds"] = 2

graph = TradingAgentsGraph(debug=True, config=config)
_, decision = graph.propagate("600519.SS", "2025-12-31")
print(decision)
```

Use a copied configuration so application-specific changes do not mutate the module-level defaults. Provider credentials can come from the environment or your own configuration loader.

## Persistence and Local Data

By default, TradingAgents keeps local state under `~/.tradingagents/`:

| Data | Default path |
| --- | --- |
| Reports and logs | `~/.tradingagents/logs/` |
| Decision memory | `~/.tradingagents/memory/trading_memory.md` |
| Checkpoints and cached data | `~/.tradingagents/cache/` |
| Web workbench runs | `~/.tradingagents/web/runs/` |

These locations can be changed with the corresponding `TRADINGAGENTS_*` environment variables in `.env.example`.

## Documentation

- [A-share data capabilities](docs/a-share-data-capabilities.md)
- [China data supplements](docs/china-data-supplements.md)
- [Data metadata and tools](docs/data-meta-tools.md)
- [Observability and replay](docs/observability-replay.md)
- [Research delegation](docs/research-delegation.md)
- [Workbench presets](docs/workbench-presets.md)
- [Project changelog](CHANGELOG.md)
- [Detailed roadmap changelog](docs/roadmap/CHANGELOG.md)

## Upstream

This repository originated as a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) and has since added an A-share-first data path, evidence validation, config-first workflows, and a local research workbench.

## License

This project is available under the terms in [LICENSE](LICENSE).
