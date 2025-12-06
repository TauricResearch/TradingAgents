# Pump Detection System - Complete Setup Guide

## 📚 What You Get

A complete **AI-powered pump detection system** that identifies stocks likely to pump BEFORE they happen. Get early entry into momentum moves and ride them for 5-50%+ gains.

### Files Created

```
📁 Core System
├── tradingagents/agents/pump_detection_agent.py      # Main agent
├── tradingagents/agents/utils/pump_detection_tools.py # Detection tools
│
📁 Scripts & Tools  
├── pump_screening.py                  # Live pump detection
├── pump_detection_demo.py              # Demo with cached data
├── pump_and_trade_workflow.py          # Integrated trading workflow
│
📁 Documentation
├── PUMP_DETECTION_GUIDE.md             # Full guide (you are here)
├── PUMP_DETECTION_QUICK_REFERENCE.md   # Quick cheat sheet
└── README.md                           # This file
```

## 🚀 Quick Start

### 1. Test with Demo (No API Keys Needed)

```bash
# Analyzes cached stock data with pump detection
python pump_detection_demo.py
```

**Output**: Pump detection scores for available cached stocks.

### 2. Analyze Specific Stock

```bash
# Requires yfinance or Alpha Vantage API
python pump_screening.py --ticker NVDA --date 2025-12-05
```

**Output**: Full pump analysis with score, signals, and trading recommendation.

### 3. Screen Full Market

```bash
# Scans for pump candidates, then analyzes top picks
python pump_screening.py
```

**Output**: Market screening results + pump scores for top candidates.

### 4. Integrated Pump + Trade Workflow

```bash
# Detect pumps, then run full trading analysis
python pump_and_trade_workflow.py --tickers NVDA TSLA AMD --mode pump_first
```

**Output**: Pump detection + technical + fundamental analysis + trading signals.

## 🎯 How It Works

### Detection Strategy

The system uses **5 complementary signals**:

```
1. Volume Spike (25%)       → Is volume 2x+ average?
2. Price Acceleration (20%) → Are recent gains > 5%?
3. Social Sentiment (15%)   → Is stock trending online?
4. Oversold Bounce (20%)    → Is RSI < 30 (bounce setup)?
5. Catalyst Events (20%)    → Any catalyst (earnings, news)?
                    ─────────────────
                    PUMP SCORE (0-100)
```

### Score Interpretation

| Score | Signal | Action |
|-------|--------|--------|
| **70+** | 🔴 VERY HIGH | BUY NOW |
| **50-69** | 🟠 HIGH | BUY with caution |
| **30-49** | 🟡 MODERATE | WAIT for confirmation |
| **<30** | 🟢 LOW | SKIP |

## 💰 Trading Strategy

### Entry Setup

```
Stock Score: >= 50
Position Size: 1-2% of portfolio
Stop Loss: 2-3% below entry
Target 1: 5% gain
Target 2: 10% gain
Target 3: 15%+ gain
```

### Position Management

```
Entry at $100
├─ Stop Loss: $97-98 (Hard stop, no exceptions!)
├─ Target 1: $105 (5%) → Move stop to +2%
├─ Target 2: $110 (10%) → Reduce to 50% position
└─ Target 3: $115+ (15%+) → Trail stop upward
```

### Exit Rules

Exit when:
- ❌ Stop loss hit (2-3% loss)
- ❌ Volume collapse (50% drop)
- ❌ Price hits resistance
- ✅ Profit target reached
- ⏳ Pump shows exhaustion (5+ days)

## ⚠️ Critical Rules

### DO THIS ✅

- ✅ Always set stop loss at entry
- ✅ Use small position sizes (1-2%)
- ✅ Monitor continuously (don't leave unattended)
- ✅ Exit on volume decline
- ✅ Use trailing stops for protection
- ✅ Keep pump trades separate (max 5-10% portfolio)
- ✅ Take profits early (5-10% is good)

### NEVER DO THIS ❌

- ❌ Chase after 50%+ gains
- ❌ Trade without stop loss
- ❌ All-in on pump trades
- ❌ Hold overnight (dump at open)
- ❌ Ignore volume decline
- ❌ Use margin
- ❌ Fight the momentum

## 🛠️ Setup Requirements

### Minimum (Demo Only)

- Python 3.10+
- LangChain installed
- Cached stock data (auto-generated from `main_screening.py`)

```bash
python pump_detection_demo.py  # No API keys needed!
```

### Full System (Live Trading)

#### Option A: yfinance (Recommended - Free)

```bash
pip install yfinance
# No API key needed, just works!
python pump_screening.py --ticker NVDA
```

#### Option B: Alpha Vantage (More data)

```bash
pip install alpha-vantage
export ALPHA_VANTAGE_API_KEY="your_key_here"
python pump_screening.py --ticker NVDA
```

Get free API key: https://www.alphavantage.co/

## 📊 Example Analysis

### Example 1: High Pump Probability

```
Stock: NVDA (2025-12-05)

Volume Spike:        3.2x average ✅ (+25 points)
Price Acceleration:  +12% in 2 days ✅ (+20 points)
Social Buzz:         #1 trending ✅ (+15 points)
Oversold Bounce:     RSI 65 ❌ (-0 points)
Catalyst:            Earnings next week ✅ (+20 points)
                     ────────────────
PUMP SCORE:          80/100 🔴 VERY HIGH

RECOMMENDATION: STRONG BUY SIGNAL
Entry: Now with 2% stop loss
Targets: $955, $1005, $1050+
```

### Example 2: Low Pump Probability

```
Stock: XYZ (2025-12-05)

Volume Spike:        1.1x average ❌ (-0 points)
Price Acceleration:  +0.5% ❌ (-0 points)
Social Buzz:         Not trending ❌ (-0 points)
Oversold Bounce:     RSI 65 ❌ (-0 points)
Catalyst:            None ❌ (-0 points)
                     ────────────────
PUMP SCORE:          0/100 🟢 LOW

RECOMMENDATION: SKIP - Wait for better setup
```

## 🚨 Pump vs Pump-and-Dump

### Legitimate Pump (TRADE THIS) ✅

- Supported by volume surge
- Following technical setup (RSI < 30)
- Has catalyst event
- Social sentiment building gradually
- Price holds or consolidates

### Pump-and-Dump (AVOID THIS) ❌

- Extreme volume spike (5-10x+)
- Penny stock with low liquidity
- Coordinated social media push
- Insider selling at peak
- No fundamental reason
- Stock drops 50%+ within days

**Protection**: Check fundamentals and liquidity before entry.

## 📖 Documentation

### Quick Reference (2-5 minutes)
→ **PUMP_DETECTION_QUICK_REFERENCE.md**

### Full Guide (20-30 minutes)
→ **PUMP_DETECTION_GUIDE.md**

### Code Examples
→ See examples below

## 💻 Code Examples

### Basic Usage

```python
from tradingagents.agents.utils.pump_detection_tools import (
    detect_volume_spike,
    detect_price_acceleration,
    calculate_pump_score,
)

# Detect volume spike
result = detect_volume_spike.invoke({
    "symbol": "NVDA",
    "curr_date": "2025-12-05",
    "threshold_multiplier": 2.0,
})
print(result)

# Detect price acceleration
result = detect_price_acceleration.invoke({
    "symbol": "NVDA",
    "curr_date": "2025-12-05",
    "look_back_days": 10,
})
print(result)

# Calculate pump score
score = calculate_pump_score.invoke({
    "symbol": "NVDA",
    "volume_spike_detected": True,
    "price_acceleration_detected": True,
    "social_sentiment_surge": True,
    "oversold_bounce": False,
    "catalyst_event": True,
})
print(score)
```

### Agent Usage

```python
from langchain_openai import ChatOpenAI
from tradingagents.agents.pump_detection_agent import create_pump_detection_agent

llm = ChatOpenAI(model="gpt-4o-mini")
pump_detector = create_pump_detection_agent(llm)

state = {
    "messages": [],
    "ticker": "NVDA",
    "trade_date": "2025-12-05",
}

result = pump_detector(state)
analysis = result["messages"][-1].content
print(analysis)
```

## 🔧 Advanced Customization

### Adjust Detection Thresholds

Edit `tradingagents/agents/utils/pump_detection_tools.py`:

```python
# Volume threshold (default 2.0x)
threshold_multiplier = 3.0  # More conservative

# Price acceleration threshold (default 5%)
recent_gain_threshold = 10.0  # More conservative

# RSI threshold (default 30)
rsi_threshold = 25  # More aggressive
```

### Custom Score Weights

In `calculate_pump_score()`:

```python
weights = {
    "volume_spike": 40,        # Up from 25
    "price_acceleration": 25,  # Up from 20
    "social_sentiment": 5,     # Down from 15
    "oversold_bounce": 20,
    "catalyst": 10,            # Down from 20
}
```

## 🎓 Learning Path

1. **Read**: PUMP_DETECTION_QUICK_REFERENCE.md (5 min)
2. **Demo**: `python pump_detection_demo.py` (5 min)
3. **Learn**: PUMP_DETECTION_GUIDE.md (30 min)
4. **Practice**: `python pump_screening.py --ticker [YOUR_TICKER]`
5. **Trade**: Start with 0.5-1% position size

## 📊 Performance Metrics (Track These)

Track your pump trading performance:

```
Total Trades:          ____ (target: 20+)
Winning Trades:        ____ (target: >50%)
Avg Win:               ____ (target: 5-15%)
Avg Loss:              ____ (target: <2%)
Win Rate:              ____ (target: >55%)
Risk/Reward Ratio:     ____ (target: >1.5)
Profit Factor:         ____ (target: >2.0)
Max Consecutive Loss:  ____ (target: <3)
```

## 🆘 Troubleshooting

### "All vendor attempts failed"
```bash
# Ensure data sources are available
python main_screening.py  # Cache data first
python pump_detection_demo.py  # Then try demo
```

### "API key not found"
```bash
# Set API key
export ALPHA_VANTAGE_API_KEY="your_key"
python pump_screening.py --ticker NVDA
```

### "Insufficient data"
- Stock needs at least 5 days history
- Try a larger look_back_days
- Try a different stock

## 📞 Support

1. Check the troubleshooting section
2. Read PUMP_DETECTION_GUIDE.md
3. Review examples in code files
4. Check cached data files exist

## ⚖️ Disclaimer

🔴 **Pump trading is HIGH RISK**

- Stocks can drop as fast as they rise
- You can lose 100% of investment
- Not suitable for beginners
- Not guaranteed to be profitable
- Past performance ≠ future results

**Only risk what you can afford to lose.**

## 🎯 Summary

| Item | Details |
|------|---------|
| **Purpose** | Identify pre-pump stocks for early entry |
| **Best For** | Experienced traders, 1-5 day holds |
| **Risk Level** | HIGH (strict risk management required) |
| **Position Size** | 1-2% max per trade, 5-10% total |
| **Stop Loss** | MUST be 2-3% below entry |
| **Profit Target** | 5-15% gains, exit at targets |
| **Time Commitment** | Requires continuous monitoring |
| **Setup Time** | 10 minutes (demo) to 30 minutes (full) |
| **API Cost** | Free (yfinance) or ~$50/month (Alpha Vantage) |

---

**Happy Pump Trading! Remember: Discipline Beats Emotion. Stick to your rules. 📈**
