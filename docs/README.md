# DEXAgents 🔗

**Multi-Agent LLM Framework for Decentralized Exchange Trading**

> Fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) adapted for DeFi/On-Chain trading on Solana and EVM networks.

---

## Overview

DEXAgents extends the TradingAgents framework to support decentralized exchange trading. Instead of analysing stocks via traditional finance APIs, the system analyses on-chain tokens using DeFi-native data sources and executes trades directly through DEX aggregators.

```
┌────────────────────────────────────────────────────────┐
│                    Analyst Team                        │
│  Market │ Fundamentals │ News │ Social │ Web Research  │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────┐
│              Researcher Team (Bull/Bear)                │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────┐
│   Trader Agent → Risk Management → Portfolio Manager   │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────┐
│     Execution Engine  (Jupiter / 1inch)                │
│       ├── Solana: JupiterExecutor                      │
│       └── EVM:    OneInchExecutor                      │
└────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.13+
- `uv` (recommended) or `pip`

### Installation

```bash
git clone https://github.com/BrunoNatalicio/DEXAgents.git
cd DEXAgents

# Create virtual environment
uv venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # macOS/Linux

# Install dependencies
uv pip install -r requirements.txt
uv pip install -e .
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your API keys
```

See [docs/configuration.md](docs/configuration.md) for all environment variables.

### Run

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("SOL", "2026-03-11")
print(decision)
```

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed system design.

### Three Scenarios

| Scenario | Status | Description |
|---|---|---|
| 1 — DEX Data Layer | ✅ Complete | DeFi data providers replacing stock APIs |
| 2 — On-Chain Execution | ✅ Complete | Real swaps via Jupiter (Solana) + 1inch (EVM) |
| 3 — Autonomous 24/7 | 🔄 Planned | Trading loop, persistent memory, monitoring |

---

## Data Sources

| Category | Provider | Description |
|---|---|---|
| Token OHLCV | CoinGecko | Price/volume data per token |
| DeFi TVL | DeFiLlama | Total value locked, protocol health |
| DEX Analytics | Birdeye | Solana on-chain token analytics |
| Web Research | Google CSE | DeFi sites: dexscreener, defillama, lunarcrush, etc. |

---

## Execution Engines

| Engine | Chain | Protocol |
|---|---|---|
| `JupiterExecutor` | Solana | Jupiter Aggregator V6 |
| `OneInchExecutor` | Ethereum, Base, Arbitrum, etc. | 1inch V6 API |

---

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Code quality
uv run pre-commit run --all-files
```

See [docs/development.md](docs/development.md) for the full development guide.

---

## Disclaimer

This project is for **research and educational purposes only**. On-chain trading involves real financial risk. Never trade with funds you cannot afford to lose. This is not financial advice.

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
