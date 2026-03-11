# Roadmap — DEXAgents

## Phase Status

| Phase | Status | Description |
|---|---|---|
| Scenario 1 — DEX Data Layer | ✅ Complete | DeFi-native data providers |
| Scenario 2 — On-Chain Execution | ✅ Complete | Real swaps, portfolio tracking |
| Scenario 3 — Autonomous 24/7 | 🔄 Planned | Always-on trading loop |

---

## Scenario 1 — DEX Data Layer ✅

- [x] CoinGecko provider (token OHLCV, market data)
- [x] DeFiLlama provider (TVL, protocol analytics)
- [x] Birdeye provider (Solana DEX analytics)
- [x] DEX tool wrappers (`get_token_ohlcv`, `get_pool_data`, `get_whale_transactions`)
- [x] Updated `interface.py` vendor routing for DEX providers
- [x] Adapted analyst prompts for DeFi context
- [x] Updated `default_config.py` with DEX settings
- [x] End-to-end pipeline test with real token

---

## Scenario 2 — On-Chain Execution ✅

- [x] `BaseExecutor` abstract class (`TradeOrder`, `TradeResult`)
- [x] `JupiterExecutor` — Solana swaps via Jupiter Aggregator V6
- [x] `OneInchExecutor` — EVM swaps via 1inch V6 API
- [x] `OrderManager` — signal → order conversion with risk limits
- [x] `PortfolioTracker` — on-chain balance and P&L tracking
- [x] `WebResearchAnalyst` — Google CSE search with quota guard
- [x] `GoogleSearchClient` + `QuotaManager` — hard block at daily limit
- [ ] Devnet/testnet integration test with real wallet

---

## Scenario 3 — Autonomous 24/7 🔄 Planned

### Streaming Layer
- [ ] WebSocket connections for real-time price feeds
- [ ] Token alert subscriptions (Birdeye, Pyth)

### Trading Loop
- [ ] Scheduler (APScheduler or Celery)
- [ ] Configurable intervals (e.g. every 15 min per token)
- [ ] Watchlist management

### Persistent Memory
- [ ] PostgreSQL schema for trade history
- [ ] P&L tracking per position
- [ ] Agent memory persistence (LangGraph checkpointing)

### Monitoring
- [ ] Telegram bot for trade alerts
- [ ] Dashboard (FastAPI + simple frontend)
- [ ] Error alerting and dead-man's switch

---

## Technical Debt

| Item | Priority | Notes |
|---|---|---|
| `PortfolioTracker._fetch_token_balances` | High | Stub — needs real Solana RPC + ERC20 calls |
| `PortfolioTracker._fetch_token_prices` | High | Stub — needs Pyth or Birdeye price oracle |
| `JupiterExecutor._confirm_and_parse` | Medium | Stub — needs real confirmation loop |
| `OneInchExecutor._confirm_and_parse` | Medium | Stub — needs `eth_getTransactionReceipt` polling |
| Devnet tests | High | Must test real transaction flow before mainnet |
| Uncomment pytest in CI | Medium | Currently skipped; add after devnet tests pass |
| Token decimals handling | High | Hardcoded 9 (Solana) / 18 (EVM) — need per-token lookup |

---

## Future Ideas

- **Multi-chain portfolio**: Track positions across Solana + EVM simultaneously
- **MEV protection**: Route through Jito (Solana) / Flashbots (EVM)
- **Stop-loss automation**: Autonomous sell triggers on drawdown
- **Backtesting module**: Replay historical DEX data against the agent pipeline
- **Plugin system**: Let users add custom analysts without modifying core
