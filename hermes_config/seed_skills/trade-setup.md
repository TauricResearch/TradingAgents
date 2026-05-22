---
name: trade-setup
description: Framework for identifying, evaluating, and structuring trade setups from TradingAgents analysis output.
tags: [trading, setup, analysis]
version: 1.0.0
protected: false
---

# Trade Setup Evaluation Framework

## Interpreting TradingAgents Output

The `tradingagents_tool` returns a `TraderProposal` with these key fields:

| Field | Type | Meaning |
|---|---|---|
| `signal` | `Buy` / `Hold` / `Sell` | Final trader decision |
| `scenario` | string | Predicted narrative (e.g. "Bull breakout above $185 resistance") |
| `analysts_fired` | list[str] | Which analyst agents contributed a signal |
| `confidence` | float 0–1 | Aggregate confidence from the analyst ensemble |
| `entry_price` | float | Proposed limit entry |
| `stop_loss` | float | Hard stop price |
| `target_price` | float | Take-profit target |

`signal = Hold` is an explicit pass — do not send a Telegram card.

`analysts_fired` shows which sub-agents reached a conclusion. Common values:
- `fundamentals` — earnings, revenue growth, valuation
- `technical` — price action, moving averages, breakout patterns
- `sentiment` — news sentiment, social signal
- `macro` — broad market regime, sector rotation
- `risk` — risk-adjusted position sizing recommendation

---

## Setup Quality Criteria

Evaluate each of these before proceeding to position sizing. A setup needs at
least 3 of the 5 to qualify. A setup with fewer than 3 is a pass — log to
memory and move on.

### 1. Analyst Alignment

Count analysts pointing in the same direction as `signal`. Score:

- 4–5 aligned: strong — proceed
- 3 aligned: acceptable — proceed with reduced confidence note
- 2 or fewer aligned: weak — reject

If `fundamentals` and `technical` both fire in the same direction, that is
the minimum viable combination. Sentiment alone or macro alone is insufficient.

### 2. Regime Fit

Match the macro regime label from `market_data_tool` against the signal type:

| Regime | Favours | Avoid |
|---|---|---|
| Bull Trend | Long breakouts, momentum longs | Short setups |
| Broadening | Growth longs, high-beta | Defensive shorts |
| Bear Trend | Short setups, defensive longs | Momentum longs |
| Contracting | Mean reversion, tight-range plays | Breakouts |
| Sideways | Range plays | Trend-following |

A Buy signal in a Bear Trend regime, or a Sell signal in a Bull Trend regime,
requires explicit memory evidence (≥5 wins in that counter-regime configuration)
to proceed. Without that evidence, reject.

### 3. Risk/Reward Ratio

Calculate R:R from the proposed entry, stop, and target:

```
r_r = (target_price - entry_price) / (entry_price - stop_price)
```

Minimum acceptable R:R = 2.0. Below 2.0: reject the setup. Log the R:R and
rejection reason to memory.

If target is not provided by the analysis, estimate using ATR:
```
target_price = entry_price + (2.5 * atr)
```

### 4. Confidence Threshold

`confidence` from TradingAgents must be ≥ 0.6 to proceed. Below 0.6:
log to memory and reject without sending to Telegram.

### 5. Memory Win Rate

Query FTS5 memory for the last 20 trades matching ticker + regime + signal
direction. If ≥10 trades exist and win rate is below 45%, flag the setup as
"historically weak" in the approval card. Do not auto-reject — the operator
sees the flag and decides.

If fewer than 10 matching trades exist, note "Insufficient history" on the card
with the actual count.

---

## Entry, Stop, and Target Rules

### Entry

Use the `entry_price` from TradingAgents as the limit order price. Do not
adjust upward to chase price. If the current bid/ask spread is wider than 0.3%
of entry price, add a note to the card: "Wide spread — fill uncertainty."

### Stop

Use `stop_loss` directly. Do not widen the stop to fit a larger position size.
If the stop would result in fewer than 1 share at 1% risk, reject the setup —
the dollar risk is too small to size properly.

Stop placement validation:
- Stop must be below entry for long trades (or above for short)
- Stop must not be within 0.5% of entry (too tight — likely to be hit by noise)
- Stop must not be more than 8% from entry (too wide — risk too high per share)

### Target

Use `target_price` if provided. Validate R:R ≥ 2.0. If TradingAgents does not
provide a target, estimate as `entry_price + (2.5 * atr)` and mark it as
"estimated" in the card.

---

## Pre-Telegram Pass/Reject Checklist

Run this checklist in order. On first fail, reject and log — do not continue.

1. `signal == "Buy"` or `signal == "Sell"` (not Hold)
2. Analyst alignment ≥ 3 (with fundamentals or technical in the set)
3. Regime fits signal direction (or memory evidence overrides)
4. R:R ≥ 2.0
5. `confidence >= 0.6`
6. Not within first or last 15 minutes of session
7. Position count < 3 (call `ib_get_positions()`)
8. Daily loss limit not breached (check `daily_snapshots` for today)
9. Risk math works: `floor(risk_dollars / (entry - stop)) >= 1`

If all 9 pass, proceed to position sizing and build the approval card.

---

## Rejection Logging

Every rejection must be recorded to the `trades` table with:
- `outcome = "cancelled"`
- `notes` = reason (e.g. "R:R 1.4 below minimum 2.0", "3 positions open",
  "regime mismatch — Bear Trend with Buy signal, no memory evidence")

This ensures the self-improvement loop can learn which setups consistently
fail the filter and adjust playbook criteria over time.
