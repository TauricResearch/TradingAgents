# Trading Entry Points Analysis Module

## Overview

This module provides comprehensive **CALL and PUT option entry point analysis** based on technical indicators, support/resistance levels, and market conditions.

## Key Features

### 1. **Option Type Support**
- **CALL Options** (Bullish Strategy): Entry signals when price is near support with potential upside
- **PUT Options** (Bearish Strategy): Entry signals when price is near resistance with potential downside

### 2. **Entry Point Analysis**
- Identifies optimal entry, stop loss, and take profit levels
- Calculates confidence scores based on multiple signals
- Computes risk-reward ratios for position sizing
- Provides actionable trading recommendations

### 3. **Technical Signals**
The module analyzes:
- **Price Action**: Support/resistance testing, price structure
- **Momentum (RSI)**: Oversold/overbought conditions
- **Volatility (ATR)**: Position sizing and level placement
- **Volume Trends**: Accumulation vs. distribution signals

## Module Structure

```
tradingagents/strategies/
├── __init__.py              # Package exports
├── entry_points.py          # Core entry point functions
└── examples.py              # Usage examples
```

## API Reference

### `find_call_entry_points()`
Identifies bullish entry points for CALL options.

```python
from tradingagents.strategies import find_call_entry_points

call_signal = find_call_entry_points(
    symbol="NIFTY50",
    current_price=24087.65,
    rsi=42.0,
    support_level=24000.00,
    resistance_level=24500.00,
    atr=150.00,
    volume_trend="increasing"
)
```

**CALL Signals Triggered When:**
- Price testing key support level (within 2%)
- RSI oversold (<35) or neutral (<50)
- Volume increasing (institutional accumulation)
- Significant upside to resistance

### `find_put_entry_points()`
Identifies bearish entry points for PUT options.

```python
from tradingagents.strategies import find_put_entry_points

put_signal = find_put_entry_points(
    symbol="NIFTY50",
    current_price=24087.65,
    rsi=42.0,
    support_level=24000.00,
    resistance_level=24500.00,
    atr=150.00,
    volume_trend="decreasing"
)
```

**PUT Signals Triggered When:**
- Price testing key resistance level (within 2%)
- RSI overbought (>65) or upper zone (>50)
- Volume decreasing (institutional distribution)
- Significant downside to support

### `identify_support_resistance()`
Calculates support and resistance levels using pivot point analysis.

```python
from tradingagents.strategies import identify_support_resistance

levels = identify_support_resistance(
    current_price=150.50,
    high_52w=165.00,
    low_52w=135.00,
    recent_highs=[160.00, 158.50, 157.00],
    recent_lows=[140.00, 138.50, 137.00]
)
```

### Data Classes

#### `EntryPoint`
Base class representing a trading entry point.

```python
@dataclass
class EntryPoint:
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: float  # 0.0 to 1.0
    reason: str
    technical_setup: dict
    option_type: OptionType
```

#### `CallEntryPoint` / `PutEntryPoint`
Specialized entry point classes with validation:
- **CALL**: entry_price < take_profit (upside)
- **PUT**: entry_price > take_profit (downside)

## Usage Examples

### Example 1: NIFTY 50 Analysis

Based on TradingView chart from Sep 01, 2026:

```python
from tradingagents.strategies import find_call_entry_points

# Market snapshot
call_signal = find_call_entry_points(
    symbol="NIFTY50",
    current_price=24087.65,
    rsi=42.0,
    support_level=24000.00,
    resistance_level=24500.00,
    atr=150.00,
    volume_trend="increasing"
)

# Output:
# Confidence Score: 70.0%
# Entry Price: $24,075.00
# Stop Loss: $23,850.00
# Take Profit: $24,500.00
# Risk/Reward Ratio: 1:1.89
```

**Recommendation**: Bullish bias with increasing volume suggests CALL options with 1-2 week expiry.

### Example 2: Bearish Reversal Setup

```python
from tradingagents.strategies import find_put_entry_points

# Overbought at resistance with distribution
put_signal = find_put_entry_points(
    symbol="MSFT",
    current_price=320.00,
    rsi=72.0,  # Overbought
    support_level=310.00,
    resistance_level=325.00,
    atr=4.00,
    volume_trend="decreasing"  # Distribution
)

# Confidence Score: 80.0%
# Entry Price: $323.00
# Stop Loss: $329.00
# Take Profit: $310.00
# Risk/Reward Ratio: 1:2.17
```

## Running Examples

Execute the built-in examples:

```bash
cd tradingagents/
python -m strategies.examples
```

Output includes:
1. NIFTY 50 detailed analysis
2. Generic stock examples (bullish and bearish setups)
3. Trading recommendations with specific entry/exit levels

## Integration with Trading Agents

### Adding to Agent Tools

```python
from tradingagents.strategies import make_call_entry_points_tool, make_put_entry_points_tool

# Create tools for agent use
call_tool = make_call_entry_points_tool()
put_tool = make_put_entry_points_tool()

# Add to agent's tool list
tools = [call_tool, put_tool, ... other tools ...]
```

### Agent Usage Pattern

```python
# Agent can call entry point functions directly
signal = find_call_entry_points(
    symbol=stock_symbol,
    current_price=market_data['price'],
    rsi=indicators['rsi'],
    support_level=support,
    resistance_level=resistance,
    atr=indicators['atr'],
    volume_trend=volume_direction
)

# Use recommendation in trading strategy
entry_point = parse_signal(signal)  # CallEntryPoint object
execute_trade(entry_point)
```

## Signal Quality Metrics

### Confidence Scoring

Each entry point receives a confidence score (0.0 - 1.0) based on:

| Signal | Weight | Condition |
|--------|--------|-----------|
| Price at Support/Resistance | 30% | Within 2% of level |
| RSI Condition | 25% | Oversold/Overbought |
| Volume Trend | 25% | Accumulation/Distribution |
| Price Structure | 20% | Significant Risk/Reward |

**Example:** NIFTY50 CALL with 70% confidence = 3/4 signals triggered

### Risk/Reward Ratio

Automatically calculated from entry, stop loss, and take profit:

```
R/R Ratio = (Take Profit - Entry) / (Entry - Stop Loss)
```

**Interpretation:**
- 1:1 = Equal risk and reward
- 1:2 = 2x reward for 1x risk (favorable)
- 1:0.5 = Unfavorable (more risk than reward)

## Chart Analysis: NIFTY 50 Case Study

**Market Context (Sep 01, 2026, 05:25 UTC):**
- Current Price: 24,087.65
- 52-Week High: ~26,000+
- 52-Week Low: ~22,500
- Volume: 94.99M (recent increase)
- Trend: Recovery from downtrend with bullish divergence

**Entry Points Identified:**

1. **CALL Entry (Bullish)**
   - Entry Zone: 24,000-24,075
   - Stop Loss: 23,850 (150 points below support)
   - Take Profit: 24,500 (resistance)
   - Confidence: 70%

2. **PUT Entry (Bearish)**
   - Entry Zone: 24,425-24,500
   - Stop Loss: 24,650
   - Take Profit: 24,000
   - Confidence: 30% (weaker signal)

**Recommendation**: Primary CALL strategy with protective PUTs

## Technical Details

### Price Level Calculation

**CALL Entry Price:**
```python
entry_price = support_level + (atr * 0.5)
```
Entry above support by half ATR ensures confirmation before entry.

**PUT Entry Price:**
```python
entry_price = resistance_level - (atr * 0.5)
```
Entry below resistance by half ATR ensures confirmation before entry.

### Stop Loss & Take Profit

```python
# CALL (Bullish)
stop_loss = support_level - (atr * 1.0)
take_profit = resistance_level

# PUT (Bearish)
stop_loss = resistance_level + (atr * 1.0)
take_profit = support_level
```

## Best Practices

1. **Wait for Confirmation**: Don't enter at exact support/resistance; wait for reversal candle
2. **Volume Confirmation**: Ensure volume increases on breakouts
3. **Multi-Timeframe Check**: Verify signals on higher timeframes (daily/weekly)
4. **Position Sizing**: Use risk/reward ratio to calculate position size
5. **Expiry Selection**: 
   - CALL: 1-2 weeks for theta decay benefit
   - PUT: Protect portfolios with longer dated puts

## Export to Agent System

The module can be integrated into the TradingAgents framework:

```python
from tradingagents.strategies import (
    find_call_entry_points,
    find_put_entry_points,
    identify_support_resistance,
)

# Use in trader.py agent nodes
def trader_node(state, name):
    # Get technical levels from market analyst
    support = state["support_level"]
    resistance = state["resistance_level"]
    
    # Find entry points
    entry_analysis = find_call_entry_points(...)
    
    # Include in trader proposal
    proposal = TraderProposal(
        entry_points=entry_analysis,
        ...
    )
```

## Testing

Run the test suite:

```bash
python -m tradingagents.strategies.examples
```

Verify:
- NIFTY 50 analysis output
- Generic bullish/bearish examples
- Confidence scores and risk/reward calculations

## Version & Dependencies

- Python 3.8+
- Requires: `langchain_core`
- Optional: Integration with `tradingagents` package

## Future Enhancements

- [ ] Multi-timeframe confirmation
- [ ] Options Greeks (Delta, Theta, Vega)
- [ ] Pattern recognition (head-and-shoulders, triangles)
- [ ] Sentiment analysis integration
- [ ] Backtesting framework
- [ ] Real-time TradingView API integration

## License & Attribution

Part of the TradingAgents package.
Created with Chart Analysis from TradingView.

---

For more details, see `tradingagents/strategies/examples.py` for working examples.
