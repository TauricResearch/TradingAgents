# Historical Memory System

## Overview

The Historical Memory System automatically builds agent memories from historical stock data, eliminating the need for manual feedback. This enables agents to learn from thousands of real market situations and their outcomes.

## How It Works

### Traditional Memory System (Old)
```
1. Run analysis → Make decision
2. Wait for manual input: "This trade returned +15%"
3. Reflect and create memory
4. Store for future use
```
**Problem**: Requires manual feedback for every decision. Not scalable.

### Historical Memory System (New)
```
1. Select historical period (e.g., 2024-01-01)
2. Gather all data that existed on that date:
   - Market conditions
   - News
   - Sentiment
   - Fundamentals
3. Look forward 7 days → Measure actual returns
4. Create memory: (situation at T, outcome at T+7)
5. Repeat for many periods → Build rich memory base
```
**Benefit**: Automatically build thousands of memories from historical data!

---

## Memory Creation Process

For each historical sample:

### 1. **Data Collection** (at time T)
```python
Market Report:
- Stock price: $150.25
- RSI: 65 (bullish)
- MACD: Bullish crossover
- Volume: Above average

News Report:
- Earnings beat expectations by 12%
- New product launch announced
- Positive analyst upgrades

Sentiment Report:
- Reddit: 85% bullish
- Social volume: High

Fundamentals:
- P/E: 25.3
- Revenue growth: 15% YoY
- Strong balance sheet
```

### 2. **Outcome Measurement** (at time T+7 days)
```python
Actual return: +12.5%
```

### 3. **Agent-Specific Memory Creation**

#### Bull Researcher Memory:
```
SUCCESSFUL BULLISH ANALYSIS:
The bullish indicators (earnings beat + positive sentiment +
technical momentum) correctly predicted a +12.5% gain.

Lesson: In similar conditions, advocate strongly for BUY
with high conviction. This combination of signals is reliable.
```

#### Bear Researcher Memory:
```
INCORRECT BEARISH SIGNALS:
Despite any bearish concerns, stock rallied +12.5%.

Lesson: When fundamentals are strong and sentiment positive,
bearish arguments should be cautious. Short-term bearish
technical signals may be overridden by strong fundamentals.
```

#### Trader Memory:
```
TRADING OUTCOME:
Optimal action: BUY (aggressive position)
Stock returned +12.5%

Trading lesson: Strong fundamental catalysts (earnings beats)
combined with positive technical setup warrant 75-100%
position sizing.
```

#### Risk Manager Memory:
```
RISK ASSESSMENT:
Observed volatility: MEDIUM
Post-earnings volatility was managed

Risk lesson: Earnings-driven rallies typically show controlled
risk profile when fundamentals support the move. Standard
position sizing appropriate.
```

---

## Usage

### Step 1: Build Historical Memories

Run the memory builder script:

```bash
python scripts/build_historical_memories.py
```

This will:
- Fetch historical data for major stocks (AAPL, GOOGL, MSFT, NVDA, etc.)
- Sample monthly over past 2 years
- Measure 7-day forward returns for each sample
- Create agent-specific memories
- Save to `data/memories/` directory

**Output**:
```
🧠 Building historical memories for AAPL
   Period: 2023-01-01 to 2025-01-01
   Lookforward: 7 days
   Sampling interval: 30 days

   📊 Sampling 2023-01-01... Return: +3.2%
   📊 Sampling 2023-02-01... Return: -1.5%
   📊 Sampling 2023-03-01... Return: +5.8%
   ...

✅ Created 24 memory samples for AAPL

📊 MEMORY CREATION SUMMARY
   bull             : 360 memories
   bear             : 360 memories
   trader           : 360 memories
   invest_judge     : 360 memories
   risk_manager     : 360 memories

✅ Saved to data/memories/
```

### Step 2: Enable Historical Memories

Update your config to load memories:

```python
# In your script or tradingagents/default_config.py
config = DEFAULT_CONFIG.copy()
config["load_historical_memories"] = True  # Enable loading
config["memory_dir"] = "data/memories"     # Optional: custom path
```

### Step 3: Run Analysis

When you run an analysis, memories are automatically loaded:

```bash
python -m cli.main
```

**Console output**:
```
📚 Loading historical memories from data/memories...
   ✅ bull: Loaded 360 memories from bull_memory_20250125_143022.pkl
   ✅ bear: Loaded 360 memories from bear_memory_20250125_143022.pkl
   ✅ trader: Loaded 360 memories from trader_memory_20250125_143022.pkl
   ✅ invest_judge: Loaded 360 memories from invest_judge_memory_20250125_143022.pkl
   ✅ risk_manager: Loaded 360 memories from risk_manager_memory_20250125_143022.pkl
📚 Historical memory loading complete
```

Now when agents analyze a stock, they retrieve relevant historical memories:

```
Current situation: NVDA showing strong earnings beat,
                  bullish technicals, high social sentiment

Trader retrieves memories:
  - Match 1 (similarity: 0.92): "Similar situation in AAPL 2024-03-15
    led to +15% gain. Aggressive BUY recommended."
  - Match 2 (similarity: 0.88): "GOOGL 2024-06-20 with similar pattern
    returned +12%. Strong conviction warranted."

Trader decision: BUY 100 shares (informed by historical patterns)
```

---

## Configuration Options

### Memory Builder Configuration

Edit `scripts/build_historical_memories.py`:

```python
# Stocks to build memories for
tickers = [
    "AAPL", "GOOGL", "MSFT", "NVDA", "TSLA",  # Tech
    "JPM", "BAC", "GS",                        # Finance
    "XOM", "CVX",                              # Energy
    # Add your preferred tickers
]

# Time period
start_date = "2023-01-01"
end_date = "2025-01-01"

# Lookforward period (days to measure returns)
lookforward_days = 7   # 1 week returns
# Options: 7 (weekly), 30 (monthly), 90 (quarterly)

# Sampling interval
interval_days = 30     # Sample monthly
# Options: 7 (weekly), 14 (bi-weekly), 30 (monthly)
```

### Runtime Configuration

```python
# default_config.py or your custom config
{
    "load_historical_memories": True,  # Load on startup
    "memory_dir": "data/memories",      # Memory directory
}
```

---

## Memory Types by Agent

| Agent | What They Learn | Memory Focus |
|-------|----------------|--------------|
| **Bull Researcher** | Which bullish signals are reliable | Patterns where BUY was correct |
| **Bear Researcher** | Which bearish signals are reliable | Patterns where SELL was correct |
| **Trader** | Optimal trading strategies | Position sizing, entry/exit timing |
| **Research Manager** | How to weigh bull vs bear arguments | Which perspective is more accurate |
| **Risk Manager** | How to assess volatility and risk | Position sizing, stop loss levels |

---

## Advanced Usage

### Custom Memory Building

Build memories programmatically:

```python
from tradingagents.agents.utils.historical_memory_builder import HistoricalMemoryBuilder
from tradingagents.default_config import DEFAULT_CONFIG

builder = HistoricalMemoryBuilder(DEFAULT_CONFIG)

# Build memories for specific stocks
memories = builder.populate_agent_memories(
    tickers=["TSLA", "AMD", "PLTR"],
    start_date="2024-01-01",
    end_date="2024-12-01",
    lookforward_days=14,  # 2-week returns
    interval_days=7       # Weekly samples
)

# Access specific agent memory
bull_memory = memories["bull"]
results = bull_memory.get_memories("Strong earnings beat with momentum", n_matches=3)
```

### Different Time Horizons

Create memories for different strategies:

```python
# Day trading (next day returns)
day_memories = builder.populate_agent_memories(
    tickers=tickers,
    lookforward_days=1,
    interval_days=7
)

# Swing trading (weekly returns)
swing_memories = builder.populate_agent_memories(
    tickers=tickers,
    lookforward_days=7,
    interval_days=14
)

# Position trading (monthly returns)
position_memories = builder.populate_agent_memories(
    tickers=tickers,
    lookforward_days=30,
    interval_days=30
)
```

---

## Benefits

✅ **Automatic**: No manual feedback required
✅ **Scalable**: Build thousands of memories from historical data
✅ **Accurate**: Based on real market outcomes
✅ **Agent-Specific**: Each agent learns what's relevant to their role
✅ **Pattern Recognition**: Agents learn to recognize similar situations
✅ **Continuous Improvement**: Add new historical periods as data becomes available

---

## Comparison: Old vs New

| Aspect | Old System | New System |
|--------|-----------|------------|
| Memory Creation | Manual feedback required | Automatic from historical data |
| Scalability | ~10-20 memories | Thousands of memories |
| Effort | High (manual entry) | Low (one-time script) |
| Coverage | Limited recent periods | 2+ years of market conditions |
| Reliability | Depends on manual input | Based on real outcomes |
| Setup Time | Ongoing | One-time build |

---

## Files Created

```
tradingagents/
├── agents/utils/
│   ├── historical_memory_builder.py   # Core memory builder
│   └── memory.py                       # Memory storage (existing)
├── default_config.py                   # Added memory config
└── graph/
    └── trading_graph.py                # Added memory loading

scripts/
└── build_historical_memories.py        # Memory building script

data/
└── memories/                           # Memory storage
    ├── bull_memory_20250125_143022.pkl
    ├── bear_memory_20250125_143022.pkl
    ├── trader_memory_20250125_143022.pkl
    ├── invest_judge_memory_20250125_143022.pkl
    └── risk_manager_memory_20250125_143022.pkl
```

---

## Next Steps

1. **Build Memories**: Run `python scripts/build_historical_memories.py`
2. **Enable Loading**: Set `load_historical_memories: True` in config
3. **Run Analysis**: Agents now use historical patterns!
4. **Expand Coverage**: Add more tickers, longer periods, different time horizons

Your agents now learn from thousands of real market situations! 🚀
