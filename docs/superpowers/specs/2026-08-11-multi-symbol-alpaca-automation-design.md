# Multi-Symbol Alpaca Automation Design

## Objective

Extend TradingAgents with non-interactive, scheduled multi-symbol orchestration while
preserving the existing single-symbol analysis graph. The first execution adapter supports
Alpaca paper and live accounts. Automatic allocation may create long or short equity targets,
subject to Alpaca's asset capabilities, and may use at most 30% of current positive account
cash as gross target notional.

## Scope

This change will:

- Require exactly seven unique symbols from environment-backed configuration.
- Analyze two or three symbols per batch in persistent round-robin order.
- Run eligible analysis and position tracking every 30 minutes by default.
- Turn the graph's five-tier rating into conviction-weighted target positions.
- Reconcile Alpaca positions and open orders toward those targets.
- Support Alpaca paper and live credentials without silently switching environments.
- Preserve the existing interactive single-symbol CLI and graph implementation.
- Document configuration, one-shot batch use, local scheduling, paper mode, and live mode.

This change will not add another broker adapter, rewrite the LangGraph workflow, provide a web
dashboard, bypass Alpaca's asset restrictions, or guarantee fills or profitability.

## Architecture

The implementation adds orchestration around `TradingAgentsGraph.propagate()`:

1. Configuration parses and validates the watchlist, cadence, state path, allocation cap, and
   Alpaca execution mode from environment variables.
2. A batch runner selects the next persisted two- or three-symbol partition and invokes the
   existing graph sequentially once per symbol.
3. A SQLite state store records the batch cursor, latest decisions, cycle status, position
   snapshots, and order intents.
4. A deterministic allocator converts fresh decisions for all seven symbols into target
   notionals capped by the configured cash fraction.
5. An Alpaca adapter validates the account and assets, obtains positions and open orders, and
   submits only the delta required to approach each target.
6. A scheduler invokes this cycle every configured interval and uses Alpaca market state to
   avoid running equity work while the equity market is closed.

No graph node or graph edge changes. The interactive `tradingagents analyze` command retains
its current behavior.

## Configuration

The following values are added to `DEFAULT_CONFIG` and participate in the existing
`TRADINGAGENTS_*` environment override mechanism:

| Environment variable | Default | Rule |
| --- | --- | --- |
| `TRADINGAGENTS_WATCHLIST` | empty | Comma-separated, exactly seven non-empty unique symbols |
| `TRADINGAGENTS_BATCH_SIZE` | `3` | Must be `2` or `3` |
| `TRADINGAGENTS_ANALYSIS_INTERVAL_MINUTES` | `30` | Positive integer |
| `TRADINGAGENTS_POSITION_INTERVAL_MINUTES` | `30` | Positive integer |
| `TRADINGAGENTS_MAX_CASH_ALLOCATION` | `0.30` | Greater than zero and no greater than `0.30` |
| `TRADINGAGENTS_DECISION_MAX_AGE_MINUTES` | `120` | Positive integer; safely covers the 90-minute seven-symbol rotation |
| `TRADINGAGENTS_REBALANCE_THRESHOLD_USD` | `10.00` | Non-negative minimum target delta submitted |
| `TRADINGAGENTS_AUTOMATION_STATE_PATH` | `~/.tradingagents/automation/state.db` | SQLite state file |
| `TRADINGAGENTS_AUTO_EXECUTE` | `false` | Analysis and order planning run, but orders are not submitted when false |
| `TRADINGAGENTS_ALPACA_MODE` | `paper` | Exactly `paper` or `live` |
| `TRADINGAGENTS_LIVE_TRADING_ACK` | empty | Must equal `I_UNDERSTAND_LIVE_ORDERS` before live submission |

Alpaca credentials use `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. Paper and live credentials are
different; the operator supplies credentials matching `TRADINGAGENTS_ALPACA_MODE`. The adapter
selects Alpaca's endpoint from the mode rather than accepting an arbitrary trading base URL.

The `.env.example` documents all values but leaves the watchlist, credentials, auto-execute,
and live acknowledgment inactive.

## Batch Selection

The configured watchlist order is authoritative. It is partitioned once per cycle rotation:

- Batch size `3`: partitions contain `3, 2, 2` symbols.
- Batch size `2`: partitions contain `2, 2, 3` symbols.

The next partition index is stored in SQLite only after the batch finishes. A failed symbol is
recorded, while the remaining symbols still run. The failed decision is not replaced with a
fabricated rating.

Each symbol is analyzed sequentially. The runner detects the existing stock or crypto asset
mode and uses the existing analyst filtering rules. Within one batch it constructs at most one
graph for each required analyst set and reuses that graph sequentially for matching symbols.
`propagate(ticker, trade_date, asset_type)` stays unchanged.

## Scheduling and Market Eligibility

`tradingagents batch` executes the next eligible batch once. It is suitable for cron or another
external scheduler and exits successfully without analysis when no configured market is open.

`tradingagents automate` runs a local foreground loop. It aligns cycles to the configured
intervals and acquires a SQLite lease before each due analysis or position task so a foreground
process and a cron invocation cannot execute the same task concurrently. Analysis and position
tracking keep independent last-run timestamps; when their configured intervals differ, the loop
wakes for whichever task is due first.

For Alpaca US equities, the adapter's market clock controls eligibility. Equity analysis,
allocation, execution, and position snapshots occur only while that market is open. Alpaca
crypto is eligible continuously. A batch processes two or three eligible symbols when at least
two are eligible; a lone eligible symbol waits for the next cycle rather than violating the
batch-size invariant. The persisted cursor prevents skipped closed-market symbols from being
lost.

Analysis uses the current calendar date reported by the broker clock. Position snapshots use
broker timestamps and are written on the 30-minute position cadence.

## Decision Freshness and Warm-Up

Every completed analysis stores the symbol, rating, analysis timestamp, analysis date, and a
reference to the generated report. Trading is disabled during initial warm-up until all seven
symbols have successful decisions no older than
`TRADINGAGENTS_DECISION_MAX_AGE_MINUTES`.

After warm-up, every cycle uses the latest fresh decision for all seven symbols, including the
five symbols not analyzed in that cycle. If any decision is missing or stale, the cycle records
the reason and submits no orders. It continues position tracking and analysis so freshness can
recover naturally.

## Conviction Allocation

Ratings map deterministically to signed conviction scores:

| Rating | Score |
| --- | ---: |
| Buy | `+1.0` |
| Overweight | `+0.5` |
| Hold | `0.0` |
| Underweight | `-0.5` |
| Sell | `-1.0` |

At the start of each allocation cycle:

1. Read current Alpaca account cash.
2. Set the gross budget to `max(cash, 0) * max_cash_allocation`.
3. Divide that budget among non-zero scores in proportion to their absolute values.
4. Apply the score sign to obtain long or short target notional.

Therefore, the sum of absolute target notionals never exceeds 30% of current positive cash. If
all ratings are Hold or cash is non-positive, every target is zero. Existing positions above the
new target are reduced; the allocator never adds a fresh percentage on top of prior positions.

The 30% value is both the default and a validation ceiling. Configuration may lower it but may
not raise it in this implementation.

## Position Reconciliation and Orders

The Alpaca adapter returns account data, asset capabilities, current positions, and open orders
through small internal data objects so allocation tests do not import the SDK.

For each target, reconciliation calculates the signed difference between target notional and
effective exposure. Effective exposure includes the current position plus outstanding open-order
quantity valued with the same current reference price. Deltas below
`TRADINGAGENTS_REBALANCE_THRESHOLD_USD` are ignored.

Before submission, the adapter verifies:

- The account is active and not trading-blocked.
- The configured environment matches the intended paper or live client.
- The asset is active and tradable.
- Short targets are submitted only for assets Alpaca marks shortable.
- Quantity respects fractionability and minimum increments.
- Buying power is sufficient for the proposed order.
- The order would not cause aggregate target gross notional to exceed the cycle budget.

Unsupported targets are skipped and their budget is not redistributed. In particular, Alpaca
crypto is not shortable, so a negative crypto target produces a recorded capability error and no
order.

Orders are market orders with the time-in-force supported by the asset class. Each order has a
deterministic client order ID derived from the cycle, symbol, side, and target. Before retrying an
uncertain submission, the adapter queries that client order ID. This prevents a network timeout
from blindly duplicating an order.

`TRADINGAGENTS_AUTO_EXECUTE=false` produces and persists the full order plan without submission.
Paper submission requires `TRADINGAGENTS_AUTO_EXECUTE=true` and paper credentials. Live
submission additionally requires `TRADINGAGENTS_ALPACA_MODE=live` and the exact live
acknowledgment value. Missing or contradictory settings stop the cycle before order submission.

## Failure Behavior

- Configuration errors fail before graph or broker calls.
- One symbol analysis failure does not prevent remaining symbols from being analyzed, but stale
  or missing decisions prevent all trading for that cycle.
- Broker read failures prevent allocation and order submission for that cycle.
- An individual capability rejection skips only that target without redistributing its weight.
- An ambiguous order response is resolved by client order ID before any retry.
- Process overlap is prevented by a time-bounded SQLite cycle lease.
- No error path changes paper mode to live, live mode to paper, or dry-run mode to submission.
- The scheduler logs cycle outcomes and continues on the next interval unless configuration is
  invalid, in which case it exits for operator correction.

## Files and Interfaces

Expected production changes are limited to:

- `tradingagents/default_config.py`: new typed defaults and environment validation support.
- `tradingagents/automation.py`: watchlist parsing, partition selection, orchestration, and CLI-
  independent cycle service.
- `tradingagents/automation_state.py`: SQLite persistence and cycle lease.
- `tradingagents/allocation.py`: rating-to-target and reconciliation calculations.
- `tradingagents/execution.py`: broker-neutral internal protocol plus the Alpaca implementation.
- `tradingagents/scheduler.py`: one-shot and foreground-loop scheduling.
- `cli/main.py`: thin `batch` and `automate` commands.
- `pyproject.toml`: an optional Alpaca dependency extra.
- `.env.example` and `README.md`: configuration and operating instructions.

No existing graph module is expected to change.

## Testing

Tests use real allocation, partitioning, state, and scheduling code with fake graph and broker
boundaries. The default suite never calls an LLM, network, or brokerage endpoint and never
submits an order.

Coverage includes:

- Watchlist cardinality, uniqueness, whitespace handling, and invalid configuration.
- Deterministic `3, 2, 2` and `2, 2, 3` rotations with persisted cursor recovery.
- Rating weights, long/short signs, Hold behavior, non-positive cash, and the 30% hard ceiling.
- Warm-up and stale-decision trade suppression.
- Target-delta reconciliation with positions and open orders.
- Dry-run, paper, live acknowledgment, blocked-account, untradable, and unshortable behavior.
- Crypto symbol conversion and crypto short rejection.
- Market-open eligibility and the 30-minute scheduler cadence.
- Cycle lease behavior and deterministic order IDs.
- Regression coverage showing the existing single-symbol CLI and graph path remain intact.

An optional manually invoked paper-account smoke check may perform read-only account, clock,
asset, and position calls. Order submission is not part of automated verification.

## Documentation and Operation

The README will show:

1. Installing the optional Alpaca dependency.
2. Configuring exactly seven symbols and the analysis model settings through `.env`.
3. Running `tradingagents batch` in dry-run mode.
4. Running `tradingagents automate` locally.
5. Enabling Alpaca paper submission.
6. Reviewing persisted decisions and position snapshots.
7. Enabling live mode only after paper verification, with its explicit acknowledgment.
8. A cron example that calls the one-shot command every 30 minutes while relying on the command's
   own market-open and overlap checks.

The documentation will state that language-model decisions are non-deterministic, market orders
can fill differently from their reference prices, paper results differ from live execution, and
Alpaca remains the final authority on tradability, shortability, buying power, and order acceptance.
