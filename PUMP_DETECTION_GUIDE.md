# Pump Detection System

## Overview

The **Pump Detection System** identifies stocks likely to experience sudden price increases (pumps) BEFORE they happen. This gives you early entry opportunities to profit from momentum moves.

## What is a "Pump"?

A pump is a rapid, significant increase in stock price driven by:
- **Volume surge** - Abnormal trading activity (2-10x average volume)
- **Price acceleration** - Quick gains over 1-3 days (5-50% moves)
- **Social buzz** - Heavy discussion on Reddit, Twitter, StockTwits
- **Technical setup** - Stocks bouncing from oversold conditions (RSI < 30)
- **Catalysts** - Upcoming earnings, FDA approval, partnership news

The key to profiting is **identifying these signals BEFORE the pump starts**, not chasing after it's already up 50%.

## How the Detection Works

### Detection Methods

The system uses **5 complementary detection strategies**:

#### 1. Volume Spike Detection
- **What it detects**: Abnormal increase in trading volume
- **Signal**: Volume > 2x average (configurable)
- **Interpretation**: Increased institutional/retail interest, often precedes price moves
- **Tool**: `detect_volume_spike(symbol, curr_date, look_back_days=20, threshold_multiplier=2.0)`

#### 2. Price Acceleration
- **What it detects**: Rapid price gains in recent period
- **Signal**: Recent gains > 5% AND recent gains > 1.5x older gains
- **Interpretation**: Momentum building, potential pump in progress or starting
- **Tool**: `detect_price_acceleration(symbol, curr_date, look_back_days=10)`

#### 3. Social Sentiment Surge
- **What it detects**: Spike in social media mentions and sentiment
- **Signal**: Stock in top trending list on Reddit/Twitter/StockTwits
- **Interpretation**: Retail hype building, retail money may follow
- **Tool**: `detect_social_sentiment_surge(symbol, curr_date)`

#### 4. Oversold Bounce Setup
- **What it detects**: Stocks bouncing from oversold technical conditions
- **Signal**: RSI < 30 (indicator of oversold)
- **Interpretation**: High probability bounce/reversal, often with strong moves
- **Tool**: `detect_oversold_bounce(symbol, curr_date, rsi_threshold=30)`

#### 5. Catalyst Events
- **What it detects**: Upcoming earnings, FDA approvals, partnerships, etc.
- **Signal**: Major event within 3 months
- **Interpretation**: Catalyst drives speculation and trading volume
- **Tool**: `detect_catalyst_event(symbol, curr_date)`

### Pump Score Calculation

All signals are combined into a **Pump Probability Score (0-100)**:

```
Score = 25% (Volume) + 20% (Price) + 15% (Social) + 20% (Technical) + 20% (Catalyst)
```

**Score Interpretation**:
- **70+**: 🔴 **VERY HIGH** pump probability → Strong entry candidate
- **50-69**: 🟠 **HIGH** pump probability → Good entry with risk management
- **30-49**: 🟡 **MODERATE** pump probability → Wait for confirmation
- **<30**: 🟢 **LOW** pump probability → No pump signals detected

## Usage

### Quick Demo (with cached data)

```bash
python pump_detection_demo.py
```

This analyzes cached stock files and shows pump detection scores.

### Live Pump Screening (requires data sources)

#### Analyze specific stock:
```bash
python pump_screening.py --ticker NVDA
```

#### Analyze specific date:
```bash
python pump_screening.py --ticker TSLA --date 2025-12-05
```

#### Full market screening (find pump candidates):
```bash
python pump_screening.py
```

### In Your Trading Agent Code

```python
from tradingagents.agents.pump_detection_agent import create_pump_detection_agent
from tradingagents.agents.utils.pump_detection_tools import (
    detect_volume_spike,
    detect_price_acceleration,
    detect_social_sentiment_surge,
    detect_oversold_bounce,
    detect_catalyst_event,
    calculate_pump_score,
)

# Create agent
pump_detector = create_pump_detection_agent(llm)

# Use in workflow
state = {
    "messages": [],
    "ticker": "NVDA",
    "trade_date": "2025-12-05",
}
result = pump_detector(state)
```

## Pump Trading Strategy

### Entry Rules

1. **Pump Score >= 50**: Consider entry
2. **Multiple signals confirmed**: Volume + Price Acceleration = strong signal
3. **Early position**: Enter in first 5-15% of move
4. **Small size**: 1-2% of portfolio max per trade

### Position Management

```
Entry Price: $100
Stop Loss: $97-98 (2-3% below entry)
Target 1: $105 (5% profit)
Target 2: $110 (10% profit)
Target 3: $115+ (15%+ profit)
```

### Exit Rules

- **❌ Exit on Stop Loss**: Hard stop at 2-3% loss
- **❌ Exit on Volume Collapse**: If volume drops 50%, pump ending
- **❌ Exit at Resistance**: Price hitting resistance level
- **✅ Exit at Targets**: Take profits at 5-10% gains
- **⏸️ Trail Stop**: Move stop to breakeven once +5% profit achieved

## Risk Management

### ⚠️ Critical Rules

1. **Position Size**: Never more than 1-2% per pump trade
2. **Stop Loss**: ALWAYS set at entry, no exceptions
3. **Risk/Reward Ratio**: Min 1:2 (risk $1 to make $2)
4. **Diversification**: Max 3-4 pump trades simultaneously
5. **Account Allocation**: Max 5-10% of portfolio in pump trades total

### Avoid These

- 🚫 **Chasing after 50% gains** - Too late, dumpers coming
- 🚫 **No stop loss** - Pump can reverse quickly
- 🚫 **All-in positions** - One bad pump wipes account
- 🚫 **Holding overnight** - Pumps can reverse in minutes
- 🚫 **Ignoring volume** - Volume collapse = pump ending
- 🚫 **Fighting the trend** - Don't short pumps, ride them

## Pump vs Pump-and-Dump Warning Signs

### Legitimate Pump (Good for trading)
- ✅ Supported by volume surge
- ✅ Following technical setup (oversold bounce)
- ✅ Has catalyst event
- ✅ Social sentiment building gradually
- ✅ Price holds gains or consolidates

### Pump-and-Dump (Dangerous - AVOID)
- ⚠️ Extreme volume spike (5-10x+)
- ⚠️ Penny stock with low liquidity
- ⚠️ Coordinated social media push
- ⚠️ Insider selling after spike
- ⚠️ No fundamental reason for move
- ⚠️ Stock drops 50%+ within days

**Protection**: Use the `detect_pump_and_dump_risk()` tool before entry.

## Available Tools

### Core Detection Tools

| Tool | Purpose | Usage |
|------|---------|-------|
| `detect_volume_spike()` | Find abnormal volume | Identify interest surge |
| `detect_price_acceleration()` | Find rapid gains | Confirm momentum building |
| `detect_social_sentiment_surge()` | Find social buzz | Track retail interest |
| `detect_oversold_bounce()` | Find technical setup | Identify bounce candidates |
| `detect_catalyst_event()` | Find catalysts | Find event-driven moves |
| `calculate_pump_score()` | Calculate probability | Score all signals |

### Agent

| Agent | Purpose |
|-------|---------|
| `create_pump_detection_agent()` | Full pump detection analysis |
| `create_screening_agent()` | Market screening for pump candidates |

## Examples

### Example 1: High Probability Pump

```
🎯 Stock: NVDA

✅ Volume Spike: 3.2x average - DETECTED
✅ Price Acceleration: +12% in 2 days - DETECTED
✅ Social Buzz: Top 5 trending on Reddit - DETECTED
❌ Oversold Bounce: RSI 65 - Not oversold
✅ Catalyst: Earnings next week - DETECTED

Pump Score: 78/100 (VERY HIGH)
Recommendation: STRONG BUY SIGNAL
Entry: Now with 2% stop loss
Targets: $1000, $1050, $1100+
```

### Example 2: Weak Pump Signal

```
🎯 Stock: XYZ

❌ Volume Spike: 1.1x average - Not detected
❌ Price Acceleration: +0.5% - Not detected
✅ Social Buzz: Mentioned on social - DETECTED
✅ Oversold Bounce: RSI 25 - DETECTED
❌ Catalyst: None upcoming - None

Pump Score: 35/100 (MODERATE - WAIT)
Recommendation: HOLD - Wait for volume confirmation
Monitor: Watch for volume spike as entry trigger
```

## Troubleshooting

### "All vendor attempts failed"
- Ensure API keys are set (Alpha Vantage)
- Or ensure cached data exists
- Run `python main_screening.py` first to cache data

### "Insufficient data"
- Stock needs at least 5 days of historical data
- Use longer look_back_days for new stocks

### No social buzz detected
- API rate limits reached
- Stock may not be discussed enough
- Try again after cool-down period

## Best Practices

1. **Always backtest** your pump detection settings
2. **Start small** with 0.5-1% position size
3. **Monitor continuously** - don't leave pump trades unattended
4. **Keep a trading journal** - track which signals work best
5. **Use trailing stops** - protect profits as pump develops
6. **Combine with other analysis** - don't rely solely on pump detection
7. **Review losses** - learn from failed pump trades

## Advanced Customization

### Adjust Detection Thresholds

```python
from tradingagents.agents.utils.pump_detection_tools import detect_volume_spike

# More aggressive (2x volume threshold)
result = detect_volume_spike.invoke({
    "symbol": "NVDA",
    "curr_date": "2025-12-05",
    "threshold_multiplier": 2.0,  # Default
})

# More conservative (3x volume threshold)
result = detect_volume_spike.invoke({
    "symbol": "NVDA",
    "curr_date": "2025-12-05",
    "threshold_multiplier": 3.0,
})
```

### Custom Score Weights

Edit `tradingagents/agents/utils/pump_detection_tools.py`:

```python
weights = {
    "volume_spike": 40,  # Increase from 25 to 40
    "price_acceleration": 20,
    "social_sentiment": 10,  # Decrease from 15 to 10
    "oversold_bounce": 20,
    "catalyst": 10,  # Decrease from 20 to 10
}
```

## Support & Questions

For issues or questions:
1. Check the troubleshooting section above
2. Review the examples
3. Check cached data files exist in `tradingagents/dataflows/data_cache/`
4. Review error messages in terminal output

## Disclaimer

⚠️ **Pump trading is HIGH RISK**. Stocks can:
- Drop as fast as they rose
- Get halted by SEC
- Be delisted
- Never recover

This system is for **experienced traders only**. Use strict risk management and never trade more than you can afford to lose.

**Past performance does not guarantee future results.**
