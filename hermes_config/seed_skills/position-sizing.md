---
name: position-sizing
description: Position sizing formulas for risk-based order calculation.
tags: [trading, position-sizing, risk]
version: 1.0.0
protected: false
---

# Position Sizing

## Primary Method — Risk-Based Sizing

This is the only sizing method. Position size is derived from the dollar
amount you are willing to lose if the stop is hit, not from a fixed share
count or a percentage of portfolio.

```
risk_dollars = account_equity * risk_pct
shares       = floor(risk_dollars / (entry_price - stop_price))
```

Default `risk_pct` = 0.01 (1%). This default is set in Hermes config
(`risk.default_pct`) and enforced by `risk-rules.md`. Do not exceed it.

`account_equity` must be fetched live from `ib_get_account_value()` at the
time of card generation. Never use a stale value.

---

## Worked Example

```
account_equity = $100,000
risk_pct       = 0.01
risk_dollars   = $100,000 * 0.01 = $1,000

entry_price    = $185.00
stop_price     = $178.50
stop_distance  = $185.00 - $178.50 = $6.50

shares         = floor($1,000 / $6.50)
               = floor(153.85)
               = 153

position_value = 153 * $185.00 = $28,305
risk_check     = 153 * $6.50   = $994.50   ✓ (≤ $1,000)
```

Always verify: `shares * (entry_price - stop_price) <= risk_dollars`. The
floor operation guarantees this, but include the check explicitly in code to
catch floating-point edge cases.

---

## Volatility Adjustment

If the ticker's Average True Range (ATR, 14-period) exceeds 2% of the current
price, the stop distance is likely to be whipsawed. Reduce the position by 50%:

```
atr_pct = atr_14 / current_price

if atr_pct > 0.02:
    shares = floor(shares * 0.5)
```

Minimum after reduction: 1 share. If `floor(shares * 0.5) < 1`, reject the
setup — the stock is too volatile to size safely within the 1% limit.

Note this reduction on the Telegram card: "Position halved — ATR {atr_pct:.1%}
exceeds 2% volatility threshold."

ATR is provided by `market_data_tool`. Do not estimate it.

---

## Liquidity Check

Position value must not exceed 1% of the ticker's average daily volume (ADV)
in dollar terms, to avoid meaningful market impact:

```
adv_dollars    = avg_daily_volume * avg_price   # 20-day average
max_by_liq     = adv_dollars * 0.01

position_value = shares * entry_price

if position_value > max_by_liq:
    shares = floor(max_by_liq / entry_price)
```

If the liquidity-adjusted share count is less than the risk-adjusted share
count, use the lower value. If it falls to 0, reject the setup and log:
"Rejected — liquidity insufficient for minimum viable position."

This check is rarely triggered for liquid US equities but is a hard guard
against micro-cap setups that slip through the analyst filter.

---

## Rounding Rules

1. Always round **down** to whole shares (`floor()`). Never round up.
2. Minimum position size: **1 share**. If the formula yields 0 shares after
   all adjustments, the setup is not viable — reject it.
3. Do not trade fractional shares even if the broker supports them. Whole
   shares only, for clean stop management.

---

## Sizing Sequence

Apply adjustments in this order:

```
1. risk_shares    = floor(risk_dollars / stop_distance)
2. vol_shares     = floor(risk_shares * 0.5)  if atr_pct > 0.02
                  = risk_shares               otherwise
3. liq_shares     = floor(max_by_liq / entry_price)
4. final_shares   = min(vol_shares, liq_shares)
5. if final_shares < 1: reject
```

Log each step in the trade record's `notes` field so the self-improvement
loop can identify patterns where sizing consistently reduces to minimum.

---

## Output to Telegram Card

The approval card must show:

```
Shares:   153
Risk:     $994  (1.0% of $99.4k equity)
```

If volatility or liquidity adjustments were applied, add a line:

```
Adjustment: Position halved — ATR 2.4% above threshold
```

or:

```
Adjustment: Liquidity cap applied — ADV $4.2M, max position $42k
```

---

## What This Skill Does Not Cover

- Stop placement — that is determined by `trade-setup.md` and TradingAgents output
- Whether to take the trade — that is `trade-setup.md`
- Hard limits on total risk — those are in `risk-rules.md` (protected)

This skill is purely mechanical: given entry, stop, ATR, ADV, and account
equity, it produces a share count. Nothing more.
