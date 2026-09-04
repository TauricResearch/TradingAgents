# Coordinated Options-Wheel Design

## Goal

Add an options-wheel sleeve to the existing seven-symbol Alpaca strategy without
changing the analysis graph. The sleeve may collect option premium when a fresh
TradingAgents decision supports the trade, but it must share one view of capital,
positions, open orders, and risk with the equity rebalancer.

The strategy cannot guarantee or maximize profit. Cash-secured puts add downside
and assignment risk, while covered calls exchange some upside for premium. The
implementation objective is controlled premium income within the existing
portfolio risk policy.

## Scope and Activation

- Alpaca is the only broker in this version.
- The configured seven-symbol equity watchlist is the complete options universe.
- Implementation and validation start in Alpaca paper mode.
- Paper options order submission remains disabled until an open-market dry run is
  reviewed and separately approved.
- Live-compatible code may be present, but live options require a later explicit
  acknowledgement and are not activated by this work.
- No naked options, multi-leg spreads, market option orders, forced liquidation,
  or account-wide fresh-start behavior is allowed.

## Existing Flow

`AutomationCycleService` rotates through two or three symbols per analysis batch.
When all seven decisions are fresh, it creates signed conviction targets, applies
portfolio risk sizing, reconciles equity positions and open orders, and may submit
Alpaca orders.

The analysis graph and its prompts remain unchanged. Options orchestration is
inserted around allocation and execution, not inside
`TradingAgentsGraph.propagate()`.

The previously reviewed wheel implementation is a source for tested selection,
reconciliation, quote-validation, and order-idempotency behavior. It is not run as
a second autonomous account controller because it assumes full portfolio control
and rejects equity shorts, which would conflict with this strategy.

## Decision Policy

New option entries require a fresh decision for the underlying and no unresolved
equity or option order for that symbol.

### Cash-Secured Puts

A new cash-secured put is eligible only when:

- the decision is `Buy` or `Overweight`;
- there is no long or short equity position, short option, or pending order for
  the underlying;
- assignment would remain within the target direction and all capital and risk
  limits; and
- the symbol passes quote, liquidity, expiration, earnings, and contract filters.

Assignment creates a long share lot owned by the wheel sleeve. It does not trigger
an additional equity purchase.

### Covered Calls

A new covered call is eligible only when:

- the account has at least 100 unencumbered long shares per contract;
- the shares are explicitly reserved before order submission;
- the decision is `Hold` or `Underweight`, avoiding an upside cap during a strong
  `Buy` or `Overweight` decision;
- the decision is not `Sell`; and
- the strike is no lower than the verified share cost basis and passes all other
  contract filters.

The equity rebalancer cannot sell reserved shares while the covered call or its
opening order remains active. A `Sell` decision suppresses new calls and defers
sale of any encumbered shares until the option is closed, expires, or is assigned.

## Contract Selection

The first version preserves the reviewed wheel thresholds:

- one contract per underlying;
- 14 through 28 calendar days to expiration;
- absolute delta from 0.15 through 0.30;
- open interest strictly greater than 100;
- annualized yield strictly greater than 0.04 and less than 1.00;
- score strictly greater than 0.05;
- quote age no greater than five minutes; and
- no new short-option entry within seven calendar days of earnings.

Quotes must have positive, uncrossed bid and ask prices with aware, non-future
timestamps. Missing, stale, or inconsistent data rejects the contract rather than
being repaired or estimated.

Selection retains the reviewed score:

```text
annualized yield = (bid / strike) * (365 / (DTE + 1))
score = (1 - absolute delta) * (250 / (DTE + 5)) * (bid / strike)
```

The highest-scoring eligible contract is selected per underlying. Orders use a
reviewable limit price derived from a valid bid/ask pair and `DAY` duration.

## Capital Ownership

The wheel sleeve has a hard maximum exposure of 20% of current account equity.
Wheel exposure is the sum of:

- strike collateral for open and pending short puts; and
- current market value of share lots reserved for open and pending covered calls.

The limit applies across the full seven-symbol universe, not separately to every
symbol. Each underlying is also limited to one active wheel contract.

Short-put collateral is unavailable to equity purchases. Covered shares remain
part of equity exposure but are unavailable to equity sales. Reservations are
derived from broker positions and open orders on every cycle and recorded in the
automation database for auditability; local state never overrides the broker.

No new option entry is submitted in the same cycle as an equity order for the
same symbol. Position-reducing equity orders are reconciled before capital is
considered available for a later option entry.

## Portfolio Risk Integration

The approved equity risk policy remains:

- 15% target annualized forecast volatility;
- 20% maximum annualized forecast volatility; and
- 2.0 times account equity maximum gross exposure.

Open and proposed options contribute delta-equivalent underlying exposure:

```text
option exposure = signed contracts * delta * 100 * underlying price
```

For each underlying, option exposure is combined with its equity target before
the portfolio return series and forecast volatility are calculated. Gross
exposure conservatively includes the absolute delta-equivalent value of option
legs in addition to equity exposure. Full put collateral is enforced separately
by the wheel allocation and buying-power checks.

If option Greeks, prices, aligned equity history, account values, or reservation
state are unavailable or invalid, new entries fail closed. Existing short options
may still be monitored and closed through validated risk-reducing orders.

## Scheduling and Lifecycle

The existing 15-minute scheduler remains the only account-level scheduler.

Every open-market cycle:

1. Reconcile account positions and all open equity and option orders.
2. Reconstruct covered-share and short-put collateral reservations.
3. Manage existing short options, including the reviewed 50% premium profit
   target and stale strategy-order handling.
4. Run the normal analysis or position task that is due.
5. Recalculate combined equity and option risk before any new exposure.

New wheel entries are considered once per trading day at or after 10:00 a.m.
America/New_York. A durable date marker prevents restarts from opening a second
daily entry. Management and risk-reducing exits continue every 15 minutes while
the market is open.

Around expiration or assignment, an option disappearance enters a settling state.
No new order for that underlying is allowed until Alpaca reports the resulting
cash, shares, and orders consistently.

## Earnings Data

A daily pre-market refresh writes the configured seven symbols' next earnings
dates, source, and retrieval timestamp to a local cache. The cache must be from
the configured source, less than 24 hours old, and contain an unambiguous future
date for the symbol. Missing, stale, unsupported, or conflicting earnings data
blocks new entries for that symbol without blocking monitoring or risk-reducing
exits.

## Execution Safety

- The broker endpoint is verified before any option submission.
- Automatic options execution has its own setting and defaults to false.
- Live options require both the existing live-trading acknowledgement and a
  separate exact options acknowledgement.
- Deterministic client order IDs and persisted intent states prevent duplicate
  submissions after retries or restarts.
- Ambiguous submission responses are reconciled by client order ID and fail
  closed if Alpaca cannot establish a unique result.
- Only orders created by this strategy may be cancelled as stale.
- A process lock prevents overlapping account cycles.
- Logs and reports never contain credentials.

## Configuration

The new environment-backed settings are:

- `TRADINGAGENTS_OPTIONS_ENABLED=false`
- `TRADINGAGENTS_OPTIONS_AUTO_EXECUTE=false`
- `TRADINGAGENTS_OPTIONS_MAX_EQUITY_FRACTION=0.20`
- `TRADINGAGENTS_OPTIONS_ENTRY_TIME_ET=10:00`
- `TRADINGAGENTS_OPTIONS_EARNINGS_PATH=<local cache path>`
- `TRADINGAGENTS_LIVE_OPTIONS_ACK=`

Contract and safety thresholds remain code constants in the first version. They
are not exposed as additional knobs because they are part of the reviewed policy.

## Code Boundaries

- `tradingagents/options.py`: pure option policy, contract filtering, exposure,
  reservations, and lifecycle calculations.
- `tradingagents/execution.py`: Alpaca option positions, contracts, snapshots,
  and limit-order mapping.
- `tradingagents/automation.py`: shared account reconciliation, risk sequencing,
  daily entry gate, and intent submission.
- `tradingagents/automation_state.py`: option intents, reservations, and daily
  entry marker.
- `tradingagents/default_config.py`: environment defaults and overrides.
- `.env.example` and `README.md`: behavior, setup, activation, and risk warnings.
- Focused tests cover pure policy, broker mapping, lifecycle state, portfolio risk,
  failure suppression, and duplicate prevention.

## Verification and Activation Gates

Implementation follows test-driven development. Before paper options are enabled:

1. Stop the current paper LaunchAgent so it cannot load partial code.
2. Run the complete TradingAgents suite, focused option tests, compilation, and
   `git diff --check`.
3. Refresh earnings data for exactly the configured seven symbols.
4. Run an open-market dry run with automatic option execution disabled.
5. Verify contract timestamps, earnings, DTE, delta, open interest, yield, score,
   strike, limit price, reservations, combined forecast volatility, gross
   exposure, and buying power.
6. Confirm zero option submissions and cancellations during the dry run.
7. Present the dry-run tickets and calculations for separate activation approval.

Live options activation is a later, independent gate after sustained paper-mode
observation. Approval of this design does not authorize live option orders.
