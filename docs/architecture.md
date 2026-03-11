# Architecture — DEXAgents

## System Overview

DEXAgents is a **multi-agent LLM framework** built on [LangGraph](https://github.com/langchain-ai/langgraph). It orchestrates specialized AI agents that collaboratively analyse DeFi tokens and execute on-chain trades.

The system follows a **pipeline architecture**: analysts produce reports → researchers debate → trader decides → execution engine acts.

---

## Agent Pipeline

```
Input: token_address, chain, date
          │
          ▼
┌─────────────────────────────────────────┐
│              ANALYST TEAM               │
│                                         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │   Market    │  │  Fundamentals    │  │
│  │  Analyst    │  │    Analyst       │  │
│  └─────────────┘  └──────────────────┘  │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │    News     │  │  Social Media    │  │
│  │  Analyst    │  │    Analyst       │  │
│  └─────────────┘  └──────────────────┘  │
│  ┌──────────────────────────────────┐   │
│  │     Web Research Analyst         │   │
│  │  (Google CSE - DeFi sites)       │   │
│  └──────────────────────────────────┘   │
└─────────────────┬───────────────────────┘
                  │ analyst reports
                  ▼
┌─────────────────────────────────────────┐
│             RESEARCHER TEAM             │
│        Bull Research ↔ Bear Research    │
│            (structured debate)          │
└─────────────────┬───────────────────────┘
                  │ research consensus
                  ▼
┌─────────────────────────────────────────┐
│              TRADER AGENT               │
│     Generates trade proposal (BUY /     │
│     SELL / HOLD + amount + rationale)   │
└─────────────────┬───────────────────────┘
                  │ trade proposal
                  ▼
┌─────────────────────────────────────────┐
│           RISK MANAGEMENT               │
│   Evaluates: volatility, liquidity,     │
│   position size, max drawdown limits    │
└─────────────────┬───────────────────────┘
                  │ risk-adjusted order
                  ▼
┌─────────────────────────────────────────┐
│          PORTFOLIO MANAGER              │
│     Final approve / reject              │
└─────────────────┬───────────────────────┘
                  │ approved order
                  ▼
┌─────────────────────────────────────────┐
│          EXECUTION ENGINE               │
│                                         │
│  JupiterExecutor  │  OneInchExecutor    │
│  (Solana)         │  (EVM chains)       │
└─────────────────────────────────────────┘
```

---

## Module Structure

```
tradingagents/
├── agents/
│   ├── analysts/
│   │   ├── market_analyst.py         # Token price/volume (DeFi adapted)
│   │   ├── fundamentals_analyst.py   # Protocol fundamentals
│   │   ├── news_analyst.py           # Crypto news analysis
│   │   ├── social_media_analyst.py   # Community sentiment
│   │   └── web_research_analyst.py   # Google CSE DeFi search ← NEW
│   ├── researchers/                  # Bull/bear debate agents
│   ├── trader/                       # Trading decision agent
│   ├── risk_mgmt/                    # Risk evaluation
│   └── managers/                     # Portfolio management
│
├── dataflows/
│   ├── interface.py                  # Vendor routing layer
│   ├── google_search_tools.py        # Google CSE + quota guard ← NEW
│   ├── y_finance.py                  # Stock data (legacy)
│   └── alpha_vantage.py              # Stock data (legacy)
│
├── execution/                        # On-chain execution ← NEW
│   ├── base_executor.py              # BaseExecutor, TradeOrder, TradeResult
│   ├── jupiter_executor.py           # Solana swaps via Jupiter V6
│   ├── oneinch_executor.py           # EVM swaps via 1inch V6
│   └── order_manager.py             # Signal → TradeOrder converter
│
├── portfolio/                        # Portfolio tracking ← NEW
│   └── portfolio_tracker.py          # On-chain balance + P&L
│
├── graph/
│   └── trading_graph.py              # LangGraph orchestration
│
└── default_config.py                 # Default configuration
```

---

## Data Flow: Analyst Team

Each analyst receives a token identifier and returns a structured text report.

### Web Research Analyst (DeFi-native)

Uses **Google Custom Search Engine** restricted to curated DeFi sites:

| Category | Sites |
|---|---|
| Security | honeypot.is, tokensniffer.com |
| News | coindesk.com, theblock.co, cryptopanic.com, bloomberg.com |
| Analytics | defillama.com, dune.com, geckoterminal.com, dexscreener.com, bubblemaps.io |
| Sentiment | lunarcrush.com |
| Markets | polymarket.com, hyperliquid.xyz, coinglass.com |
| Governance | snapshot.org, tally.xyz |

**Quota guard:** Hard limit at `GOOGLE_SEARCH_DAILY_LIMIT` (default: 95). Gracefully degrades to partial results if quota is exhausted mid-analysis.

---

## Execution Layer

### JupiterExecutor (Solana)

Flow:
1. `GET /v6/quote` — get best swap route
2. `POST /v6/swap` — get serialized transaction
3. Deserialize with `solders` → sign with keypair
4. Submit via Solana RPC `send_transaction`

### OneInchExecutor (EVM)

Flow:
1. `GET /swap/v6.0/{chainId}/quote` — get price estimate
2. `GET /swap/v6.0/{chainId}/swap` — get calldata + gas
3. Build EIP-155 transaction → sign with `web3.eth.account`
4. Broadcast via `eth_sendRawTransaction`

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **TDD for all new code** | Execution is financial-critical; untested code is unacceptable |
| **Mock network in tests** | Jupiter/1inch APIs are blocked in CI; all HTTP mocked with `unittest.mock` |
| **Quota guard hard block** | API cost caps are non-negotiable; `QuotaExceededError` prevents overruns |
| **Graceful degradation** | Partial results are better than crashing the analysis pipeline |
| **`uv` for dependencies** | Speed + reproducibility vs `pip` |
| **Worktree per feature** | Isolates development without stashing WIP; see `using-git-worktrees` skill |
