# Entry Points Quick Reference

## Import & Use

```python
from tradingagents.strategies import (
    find_call_entry_points,
    find_put_entry_points,
    identify_support_resistance,
    CallEntryPoint,
    PutEntryPoint,
    OptionType,
)
```

## Minimal Example - CALL Entry Point

```python
# Bullish setup: oversold at support with increasing volume
call = find_call_entry_points(
    symbol="AAPL",
    current_price=150.50,
    rsi=28.0,              # Oversold
    support_level=148.00,
    resistance_level=155.00,
    atr=2.50,
    volume_trend="increasing"
)
print(call)
# Output: Entry Point Report with confidence, levels, and risk/reward
```

## Minimal Example - PUT Entry Point

```python
# Bearish setup: overbought at resistance with decreasing volume
put = find_put_entry_points(
    symbol="MSFT",
    current_price=320.00,
    rsi=72.0,              # Overbought
    support_level=310.00,
    resistance_level=325.00,
    atr=4.00,
    volume_trend="decreasing"
)
print(put)
```

## Parameter Guide

| Parameter | Type | Range | Example | Notes |
|-----------|------|-------|---------|-------|
| `symbol` | str | - | "NIFTY50" | Stock ticker |
| `current_price` | float | >0 | 24087.65 | Current market price |
| `rsi` | float | 0-100 | 42.0 | Relative Strength Index |
| `support_level` | float | >0 | 24000.00 | Key support from TA |
| `resistance_level` | float | >support | 24500.00 | Key resistance from TA |
| `atr` | float | >0 | 150.00 | Average True Range |
| `volume_trend` | str | "increasing", "decreasing", "neutral" | "increasing" | Volume direction |

## RSI Interpretation

| RSI Range | Signal |
|-----------|--------|
| 0-30 | Oversold (potential bounce) |
| 30-50 | Neutral to weak |
| 50-70 | Strong to overbought |
| 70-100 | Overbought (potential pullback) |

## Confidence Score

Score of 70%+ is considered **HIGH CONFIDENCE** entry.

Breakdown:
- **30%** - Price at support/resistance
- **25%** - RSI condition
- **25%** - Volume trend
- **20%** - Price structure/risk-reward

## Trading Decision Matrix

```
RSI < 40 AND Price near Support AND Volume UP
  ➜ CALL Entry (High Probability)

RSI > 60 AND Price near Resistance AND Volume DOWN
  ➜ PUT Entry (High Probability)

RSI 40-60 (Neutral)
  ➜ Wait for clearer setup or reduce position size
```

## Risk Management

### Position Sizing
```
Position Size = Account Risk / (Entry - Stop Loss)
Account Risk = Account * 2%  # Risk 2% per trade
```

### Example Calculation
```
Account: $10,000
Account Risk: $200
Entry: 24,075
Stop Loss: 23,850
Points at Risk: 225

Position Size: $200 / 225 = 0.89 lots
```

### Expiry Selection
- **CALL**: 1-2 weeks (collect theta decay)
- **PUT**: 1 month+ (protection focused)

## Agent Integration

Add to your agent's tools:

```python
from tradingagents.strategies import (
    make_call_entry_points_tool,
    make_put_entry_points_tool,
)

# Create langchain tools
call_tool = make_call_entry_points_tool()
put_tool = make_put_entry_points_tool()

# Add to tools list
tools = [call_tool, put_tool, ...]
```

## Output Format

Every entry point returns formatted text with:

```
Entry Point Report: CALL on NIFTY50
============================================================
Confidence Score: 70.0%
Reason: Price testing key support level; RSI in neutral zone...

Price Levels:
  Entry Price: $24075.00
  Stop Loss:  $23850.00
  Take Profit: $24500.00
  Risk/Reward Ratio: 1:1.89

Technical Setup:
  current_price: 24087.65
  rsi: 42.00
  ...
```

## Common Setups

### Setup 1: Oversold Bounce (CALL)
```python
rsi = 25.0  # Oversold
volume_trend = "increasing"  # Accumulation
# ➜ High confidence CALL at support
```

### Setup 2: Overbought Pullback (PUT)
```python
rsi = 75.0  # Overbought
volume_trend = "decreasing"  # Distribution
# ➜ High confidence PUT at resistance
```

### Setup 3: Breakout Play (CALL)
```python
price_action = "above resistance"
volume_trend = "increasing"  # Confirmation
atr_multiplier = 2.0  # Wide stop loss
# ➜ CALL continuation trade
```

## Debugging Tips

**No Signal Generated?**
- Check if confidence is below 30% (very weak)
- Verify RSI is in extreme zones (0-30 or 70-100)
- Ensure volume_trend matches bias (increasing for CALL)

**Unrealistic Levels?**
- Verify support < current_price < resistance
- Check ATR is calculated correctly (not too large)
- Use 52-week highs/lows for baseline

**High Confidence but Price Moves Against?**
- Markets can override technical signals
- Always use stop loss (no exceptions)
- Consider position size reduction

## Example: Full Trading Workflow

```python
from tradingagents.strategies import find_call_entry_points, find_put_entry_points

# Step 1: Get technical data
data = get_market_data("NIFTY50")
rsi = calculate_rsi(data)
atr = calculate_atr(data)
support, resistance = identify_levels(data)

# Step 2: Find entry points
call_entry = find_call_entry_points(
    symbol="NIFTY50",
    current_price=data['current'],
    rsi=rsi,
    support_level=support,
    resistance_level=resistance,
    atr=atr,
    volume_trend=get_volume_trend(data)
)

# Step 3: Filter by confidence
if "Confidence Score: 70.0%" in call_entry or higher:
    # Step 4: Execute trade
    execute_call_option(
        symbol="NIFTY50",
        quantity=calculate_quantity(call_entry),
        entry_price=extract_entry(call_entry),
        stop_loss=extract_stop(call_entry),
        take_profit=extract_tp(call_entry),
        expiry="1 week"
    )
    # Step 5: Monitor
    watch_for_stop_loss_or_tp()
```

## File Locations

```
tradingagents/strategies/
├── entry_points.py        # Core functions
├── examples.py            # Usage examples
└── __init__.py           # Exports
```

Run examples:
```bash
python -m tradingagents.strategies.examples
```

---

**Last Updated**: Sep 01, 2026
**Version**: 1.0
