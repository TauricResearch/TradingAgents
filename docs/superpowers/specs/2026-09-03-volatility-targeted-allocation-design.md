# Volatility-Targeted Allocation Design

## Goal

Make the existing seven-symbol strategy more aggressive while limiting forecast
annualized portfolio volatility to 20%. The operating target is 15%, leaving a
buffer for estimation error, fills, and price movement.

This is a forecast constraint, not a guarantee that subsequently realized
volatility will remain below 20%.

## Existing Flow

The analysis graph remains unchanged. Each completed batch stores its ratings;
when all seven ratings are fresh, `AutomationCycleService` converts them to
signed conviction targets, reconciles positions and open orders, checks buying
power, and optionally submits Alpaca orders.

Volatility sizing will be inserted between conviction target creation and
position reconciliation. No analyst, debate, report, scheduler, or order
idempotency behavior changes.

## Risk Parameters

- Target annualized forecast volatility: `0.15`.
- Maximum annualized forecast volatility: `0.20`.
- Maximum gross exposure: `2.0` times account equity.
- Return lookback: 60 trading days.
- Minimum aligned return observations: 40.
- Return definition: close-to-close simple daily returns.
- Annualization factor: square root of 252.

The three policy values are environment-backed:

- `TRADINGAGENTS_TARGET_VOLATILITY=0.15`
- `TRADINGAGENTS_MAX_VOLATILITY=0.20`
- `TRADINGAGENTS_MAX_GROSS_LEVERAGE=2.0`

Configuration validation requires
`0 < target_volatility <= max_volatility <= 0.20` and
`1.0 <= max_gross_leverage <= 2.0`.

## Market Data

`AlpacaBroker` will request the seven symbols' daily IEX bars in one batched
request using its existing Alpaca stock-data client. It will return aligned
closing-price histories without exposing credentials. This first version is
limited to the current all-equity watchlist; unsupported asset classes fail
closed instead of silently using a different volatility model.

At least 41 aligned closes are required to produce 40 returns. Missing, stale,
non-positive, or non-finite prices make the risk estimate unavailable.

## Forecast Calculation

For each target and each aligned date:

1. Divide signed target notional by account equity to obtain the target weight.
2. Multiply each symbol's daily return by its signed weight.
3. Sum the weighted returns to obtain the daily portfolio return.
4. Calculate sample standard deviation and multiply by `sqrt(252)`.

This directly includes correlations and long/short offsets without constructing
or storing a separate covariance matrix.

## Target Scaling

The existing conviction allocator first creates the baseline signed targets,
including the `$70,000` maximum-cash-reserve rule.

The risk layer then applies one common non-negative scale factor to every
non-zero target, preserving rating directions and relative conviction weights:

```text
volatility scale = target volatility / baseline forecast volatility
gross scale limit = (maximum gross leverage * equity) / baseline gross notional
applied scale = min(volatility scale, gross scale limit)
```

The scaled targets must have forecast volatility no greater than 15%, and
therefore below the 20% maximum, subject to ordinary numeric tolerance. The
2-times-equity gross ceiling applies even when Alpaca reports greater buying
power.

If the baseline forecast is above the target, targets are reduced. If it is
below the target, targets are increased until the 15% target or the gross
ceiling is reached. Risk control takes precedence over the cash-reserve target;
scaling down may leave more than `$70,000` cash. Scaling up may use margin and
produce negative cash, as already authorized, but cannot exceed the gross or
broker buying-power limits.

## Failure Behavior

The automatic rebalance is suppressed when:

- risk data is unavailable or insufficient;
- account equity is non-positive;
- calculated volatility is zero or non-finite;
- the forecast or scaled targets contain invalid numeric values; or
- the scaled orders exceed Alpaca buying power.

Suppression records a clear cycle outcome and submits no orders. Existing
positions are not liquidated solely because market data is unavailable; doing
so could remove a hedge and increase risk.

## Files and Responsibilities

- `tradingagents/risk.py`: pure forecast and target-scaling calculations.
- `tradingagents/execution.py`: batched Alpaca daily-close retrieval.
- `tradingagents/automation.py`: configuration validation and insertion of the
  risk step before reconciliation.
- `tradingagents/default_config.py`: environment overrides and defaults.
- `.env.example` and `README.md`: configuration and behavior documentation.
- Existing focused test modules: calculation, configuration, broker mapping,
  failure suppression, and end-to-end cycle coverage.

## Verification and Activation

Implementation follows test-driven development. Tests will cover proportional
scaling up, scaling down, the 20% limit, the 2-times-equity ceiling, signed
weight preservation, insufficient observations, invalid prices, and suppressed
execution on risk-data failure.

Before restarting automation:

1. Stop the current paper LaunchAgent so it cannot load partially changed code.
2. Run the focused automation and execution suite plus compilation and
   `git diff --check`.
3. Run a no-order calculation against the paper account and report baseline
   forecast volatility, scale factor, scaled gross exposure, and projected
   buying-power usage.
4. Set the three environment values above.
5. Restart only the Alpaca paper service and verify fresh task timestamps,
   broker connectivity, and no startup errors.

No live-account activation is included. The same deterministic controls will
apply if live mode is separately enabled through the existing acknowledgment
gate.
