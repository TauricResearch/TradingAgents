# How TradingAgents works with your agentRobin accounts

## What you see on the site

| Field | Meaning |
|-------|---------|
| **Account** | One FakeBroker paper or live Schwab/RH/Alpaca book from agentRobin. Selecting it loads **cash + all positions** as portfolio context. |
| **Ticker** | The **single symbol the agents debate right now**. Not “the whole portfolio.” Example: with FakeAcct.05 holding VOO/SCHD/IXUS/QQQ, set ticker `VOO` to ask “should we buy more / hold / sell VOO?” or set `SPY` to evaluate a new idea against that book. |
| **Analyze** | Runs the multi-agent pipeline (analysts → research → trader → risk → portfolio manager) and saves a report. |

The portfolio snapshot is **context**, not the list of jobs. One click = one ticker recommendation.

## What you get today

1. **Recommendation** — Buy / Hold / Sell (+ reasoning, sizing notes) for that ticker, aware of your cash and other holdings.
2. **Saved report** under TradingAgents results (HTML when the run succeeds).
3. **No automatic broker orders yet** from the web UI. agentRobin already has a gated place path (`tradingagents_bridge.rb place` / FakeBroker paper; live needs `AGENTROBIN_TRADINGAGENTS_ALLOW_LIVE=1`).

## Path to “fully self-managed”

| Stage | Status | What it means |
|-------|--------|----------------|
| A. See books + run research | **Live** | Site + `--account` bridge |
| B. Reliable unattended Analyze | **Fixing** | Site must set date + `TRADINGAGENTS_*` so CLI never prompts |
| C. Review queue | Next | Show last recommendation; human Approve/Reject |
| D. Paper auto-execute | Next | On Approve (or auto), place equity via FakeBroker bridge |
| E. Live auto-execute | Later | Same path with live gate + size/risk caps + kill switch |
| F. Portfolio-wide cadence | Later | Cron/loop: for each account, pick tickers (holdings + watchlist), run, optionally place |

Fully hands-off investing is **not** one Analyze click — it is a scheduled loop with risk limits, paper bake-in first, then gated live.

## Practical use right now

1. Choose **FakeAcct.05** (or a live account).
2. Set ticker to a **holding** you care about (`VOO`) or a **candidate** (`SPY`).
3. Click **Analyze** — wait for status `ok` (LLM runs can take several minutes).
4. Read the log / saved report for the recommendation.
5. Place manually in agentRobin/webbit, or ask for Stage C/D (approve → FakeBroker place) as a follow-up ticket.

## Safety

- Live placement stays off unless you explicitly enable the live gate.
- Paper FakeBroker is the right place to prove the loop before Schwab/RH.
