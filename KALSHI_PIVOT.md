# Kalshi Prediction Markets Pivot — Design Doc

**Status:** In-progress on branch `feat/kalshi-prediction-markets`
**Started:** 2026-05-05

This document captures design decisions for repurposing TradingAgents (originally a multi-agent equity research framework) into a daily-horizon Kalshi crypto prediction-market trading system.

---

## Strategic thesis

TradingAgents was open-sourced in late April 2026 and accumulated >70k GitHub stars. Kalshi has been live for ~3 months under retail-dominated conditions — no institutional trading desks have moved in yet. The edge: bring **institutional-grade deliberative AI agent analysis** (4-analyst committee + bull/bear debate + risk panel + structured Portfolio Manager output) to a venue where the competition is mostly retail gut-calls and meme-driven trading.

**Implication for design**: Preserve the depth of the agent committee. At a 24-hour decision horizon, latency is not a constraint, so we keep all the deliberative machinery that gives the system its edge. Trimming for "speed" would defeat the thesis.

---

## V1 scope

- **Asset**: BTC only (extend later)
- **Markets**: Kalshi daily BTC contracts (binary YES/NO settling against Coinbase BTC-USD index)
- **Decision cadence**: One decision per daily contract, executed within user's preferred 7–10am ET window
- **Modes**: `paper` (default, full pipeline + decision but no order placement) and `live` (places real orders) — switchable via config flag
- **Position management v1**: Hold to settlement, no early exits (add Phase 2)
- **Reflection**: When contract resolves, fetch settlement → append outcome to memory log

---

## Architecture decisions

### Full pivot, not parallel

The equity path (yfinance / Alpha Vantage / Fundamentals analyst / 5-day holding / Buy/Hold/Sell schema) is **removed**, not toggled. Rationale: keeping both modes alive doubles the maintenance surface and the agent prompts diverge enough that conditional logic everywhere would be a mess.

### kalshi-trader is read-only reference

`~/code/kalshi-trader` is a stable production 15-min crypto bot. It is **never modified** during this pivot. We lift code patterns (Kalshi API auth, order ledger schema, sizing skeleton, backtest harness) **into TradingAgents**, keeping the original repo untouched.

### Coinbase, not Kraken, for price data

Kalshi BTC daily contracts settle against the Coinbase BTC-USD index. Using Coinbase as our internal price source eliminates basis risk between our analysis and the resolution venue. (kalshi-trader uses Kraken because its 15-min strategy doesn't care about the few-bps difference; for daily directional bets, the difference can matter.)

### Agent committee retained, slot-by-slot reassigned

| Original (equity) | Pivoted (Kalshi crypto) |
|---|---|
| Market Analyst | BTC technicals (daily/4h/1h indicators) |
| News Analyst | Crypto news (RSS aggregation) |
| Sentiment Analyst | Reddit + CoinMarketCap community sentiment + funding/fear-greed |
| Fundamentals Analyst | **Repurposed as On-chain Analyst** (free sources only) |
| Bull/Bear Researchers | Reframed as "YES contract is mispriced cheap" vs "NO contract is mispriced cheap" |
| Trader | Outputs target side + size pre-risk-review |
| Risk Debaters (Aggressive/Conservative/Neutral) | Argue Kelly stake fraction given confidence |
| Portfolio Manager | Outputs final `MarketDecision` (replaces `PortfolioDecision`) |

### New decision schema: `MarketDecision`

Replaces `PortfolioDecision`. Pydantic-validated, structured-output via existing provider-native pathways.

Fields:
- `p_yes: float` — agent's probability estimate for YES outcome (0–1)
- `market_p_yes: float` — current Kalshi YES mid-price (0–1)
- `edge_bps: float` — derived: `(p_yes - market_p_yes) × 10000`
- `recommended_side: Literal["YES", "NO", "PASS"]`
- `confidence: Literal["low", "medium", "high"]`
- `kelly_fraction: float` — fractional Kelly stake size (0–1) of bankroll
- `executive_summary: str`
- `investment_thesis: str`
- `key_risks: str`

---

## Data sources (Phase 1)

| Layer | Source | Auth | Cost |
|---|---|---|---|
| Spot price + OHLCV | Coinbase Advanced Trade API | none (public) | free |
| Kalshi market data | Kalshi public REST | none for read | free |
| Crypto news | RSS aggregation: CoinDesk, CoinTelegraph, The Block, Decrypt | none | free |
| Reddit | PRAW | Reddit app (client ID + secret) | free |
| CMC sentiment | CoinMarketCap API | API key (free tier) | free |
| On-chain | blockchain.com + mempool.space + Dune | Dune API key (free tier) | free |
| Twitter/X | _deferred to v1.1_ | Basic tier $200/mo | n/a |

---

## Execution layer (Phase 3)

Ported from kalshi-trader (read-only reference) into `tradingagents/execution/`:

- `kalshi_client.py` — auth (RSA private key + API key ID), `place_order`, `cancel_order`, `poll_fills`
- `order_ledger.py` — SQLite schema for end-to-end order tracking (submit time, first fill, full fill, status)
- `reconciler.py` — fill tracking with daily-horizon polling cadence (30s–1min vs kalshi-trader's 3s)
- `sizing.py` — Kelly stake using LLM-provided edge + confidence directly (skip kalshi-trader's bucketed empirical model)

### Safety configuration

- `paper_mode: bool = True` (default ON)
- `TRADINGAGENTS_LIVE_DISABLED=1` env var — short-circuits to paper regardless of config
- `--live` CLI flag required to enable live trading
- `max_stake_usd` and `max_daily_loss_usd` hard caps

---

## Phase plan

| Phase | Scope | Status |
|---|---|---|
| 0 | Strip equity path | done |
| 1 | Crypto + Kalshi data layer | done |
| 2 | `MarketDecision` schema + analyst rewires | done |
| 3 | Execution layer (paper + live) | done |
| 4 | Run loop + CLI (`tradingagents kalshi-run`) | done |
| 5 | Backtest harness scaffolding | done |

Phase 5 ships scaffolding only — running a real backtest sweep (30+ historical contracts × full agent pipeline = hundreds of LLM calls) is intentional, not a side-effect. Use `tradingagents.backtest.sweep.run_sweep(contracts=..., grid=...)` when you've allocated budget.

## How to use it (quick reference)

**Paper mode (default — safe to run anytime, real LLM cost only):**

```bash
tradingagents kalshi-run KXBTCD-26MAY05-T100000 --date 2026-05-05
```

**Live mode (real money — requires three concurrent unlocks):**

1. `paper_mode=False` in your config (e.g. via env var or a custom config file).
2. `TRADINGAGENTS_LIVE_DISABLED` env var unset.
3. `--live` flag on the CLI.

```bash
TRADINGAGENTS_LIVE_DISABLED=  tradingagents kalshi-run KXBTCD-26MAY05-T100000 --live
```

Any one of those missing → run downgrades to paper automatically (with a clear log message).

**Settlement reflection (run after the contract resolves):**

```bash
tradingagents kalshi-settle
```

Walks open ledger rows, fetches Kalshi settlement state, computes realized P&L, marks rows `settled` in the ledger.

## Required env vars

- `OPENAI_API_KEY` (or your provider's key)
- `KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` — for Kalshi market reads + live order placement (missing creds yield a clear "missing-creds" message and the pipeline degrades gracefully)
- `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` (optional — sentiment analyst falls back if missing)
- `CMC_API_KEY` (optional — sentiment analyst falls back if missing)

---

## Open questions / deferred

- **Twitter/X integration** — deferred to v1.1; cost ($200/mo Basic tier) doesn't justify v1 inclusion
- **Glassnode/CryptoQuant on-chain** — paid tiers; v1 uses free on-chain sources (blockchain.com, mempool.space, Dune)
- **Multi-asset support** (ETH, SOL, etc.) — v2; v1 is BTC-only
- **Intraday re-evaluation** — deferred; v1 makes one decision per daily contract during 7–10am ET window
- **Early exit logic** — deferred; v1 holds to settlement
- **Real backtest sweep** — scaffolded in Phase 5, run later when budget allocated
