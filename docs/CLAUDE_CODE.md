# Running TradingAgents inside Claude Code (subscription-powered, no API-key spend)

This guide explains how to drive the full TradingAgents multi-agent pipeline
from **Claude Code**, where **Claude itself plays every agent** (analysts,
researchers, trader, risk debators, portfolio manager) using your Claude
subscription. The framework's data layer is exposed as a local MCP server; the
reasoning is done by Claude. The result: the whole pipeline runs locally with
**zero LLM API-key spend** — only the (mostly free/keyless) data sources are hit.

> This is a research tool, not financial, investment, or trading advice.

## How it works

```
You: /trade NVDA 2026-01-15
        │
        ▼
Claude Code  ──(Workflow: trade-decision)──►  spawns role subagents in order:
        │        resolve identity → 4 analysts (parallel) → bull/bear debate
        │        → research manager → trader → risk debate (aggr/cons/neutral)
        │        → portfolio manager → 5-tier rating
        │
        └──(MCP: tradingagents-data)──►  market / news / fundamentals / macro /
                                          sentiment / prediction-market data
```

- **Data layer** — a local stdio MCP server (`tradingagents-data-mcp`) wrapping
  the existing `tradingagents` data tools. Makes **no** LLM calls.
- **Reasoning layer** — 12 role subagents in `.claude/agents/`, orchestrated
  deterministically by the `.claude/workflows/trade-decision.js` workflow, and
  triggered by the `/trade` slash command.
- **Memory** — decisions are logged to `~/.tradingagents/memory/trading_memory.md`
  (same format as the native pipeline). On the next run for a ticker, realized
  returns are fetched and Claude writes a reflection that feeds the next decision.

## One-time setup

1. **Install** the package with the MCP extra (from the repo root):

   ```bash
   pip install -e ".[mcp]"
   ```

2. **Data keys (optional).** The default data source is yfinance, which needs
   no key. For macro data (FRED) and the optional Alpha Vantage vendor, put free
   keys in a local `.env` (already git-ignored):

   ```
   FRED_API_KEY=...            # https://fredaccount.stlouisfed.org/apikeys
   ALPHA_VANTAGE_API_KEY=...   # https://www.alphavantage.co/support/#api-key
   ```

   The MCP server loads `.env` itself, so keys never need to live in committed
   config.

3. **Register the MCP server** at project scope (writes `.mcp.json`):

   ```bash
   claude mcp add --transport stdio tradingagents-data --scope project -- tradingagents-data-mcp
   ```

   Verify it connects:

   ```bash
   claude mcp list      # tradingagents-data: ... ✓ Connected
   ```

4. **Restart / start Claude Code from the project directory** so it loads the
   project-scoped MCP server and the `.claude/` agents, workflow, and command:

   ```bash
   cd /path/to/TradingAgents
   claude
   ```

## Usage

In Claude Code, run the slash command:

```
/trade NVDA 2026-01-15
```

Arguments (all but the ticker are optional):

```
/trade <TICKER> [YYYY-MM-DD] [analysts] [debate_rounds] [risk_rounds]
```

- **TICKER** — `NVDA`, `0700.HK`, `7203.T`, `BTC-USD`, … (preserve exchange suffix).
- **YYYY-MM-DD** — analysis date; defaults to today.
- **analysts** — comma-separated subset of `market,social,news,fundamentals`
  (default: all four). Use a subset to save subscription usage.
- **debate_rounds** / **risk_rounds** — default `1` each. Higher = deeper (and
  more usage): bull/bear run `2 × debate_rounds` turns; the risk panel runs
  `3 × risk_rounds` turns.

You can also just ask in natural language, e.g.
*"Use trade-decision to analyze AAPL on 2026-03-10 with only the news and
fundamentals analysts."*

### Output

- A headline 5-tier **decision**: Buy / Overweight / Hold / Underweight / Sell.
- The Portfolio Manager's executive summary + investment thesis.
- A full-state JSON saved to
  `~/.tradingagents/logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<DATE>.json`.
- A pending entry appended to the decision log for future reflection.

## Usage / cost notes

- Reasoning runs on your **Claude subscription** (subject to its rate limits),
  not metered API billing. A full run spawns ~13 agent turns plus tool calls.
- To keep usage down: pick fewer analysts, keep rounds at 1, and analyze one
  ticker at a time.
- Data sources are free/keyless (yfinance, Polymarket, Reddit, StockTwits) or
  free-tier (FRED, Alpha Vantage).

## Components

| Path | Role |
|---|---|
| `tradingagents/mcp/data_server.py` | Local stdio MCP server (16 data tools). No LLM calls. |
| `tradingagents/mcp/memory_cli.py` | Decision-log read/write/resolve CLI used by `/trade`. |
| `.claude/agents/*.md` | 12 role subagents (prompts ported from the native pipeline). |
| `.claude/workflows/trade-decision.js` | Deterministic orchestration of the pipeline. |
| `.claude/commands/trade.md` | The `/trade` slash command. |

## Troubleshooting

- **`/trade` not found / MCP tools missing** — start Claude Code from the repo
  root *after* `claude mcp add`, so project config loads. Check `claude mcp list`.
- **Macro data unavailable** — set `FRED_API_KEY` in `.env`.
- **`tradingagents-data-mcp` not found** — re-run `pip install -e ".[mcp]"`.
- **Reproducibility** — like the native framework, runs vary because LLM output
  and live data vary; pin the date to fix the price/indicator window.
