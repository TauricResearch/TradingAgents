# Memory Configuration Guide

## Parameter Selection for Different Trading Strategies

### Quick Reference Table

| Strategy | `lookforward_days` | `interval_days` | Memories/Year | Best For |
|----------|-------------------|-----------------|---------------|----------|
| **Day Trading** | 1 | 1 | ~250 | Intraday momentum, catalysts |
| **Swing Trading (Short)** | 3-5 | 7 | ~52 | Week-long trends |
| **Swing Trading** | 7 | 7 | ~52 | Weekly momentum |
| **Position Trading** | 30 | 30 | ~12 | Monthly fundamentals |
| **Long-term Investing** | 90 | 90 | ~4 | Quarterly value |
| **Annual Investing** | 365 | 90 | ~4 | Yearly performance |

---

## Understanding the Parameters

### 1. `lookforward_days` - Return Measurement Horizon

**What it does**: Determines how far into the future we look to measure if a decision was successful.

**Example**:
```python
Date: 2024-01-15
Stock: AAPL at $180
Situation: Strong earnings, bullish technicals

lookforward_days = 7
→ Check price on 2024-01-22: $195
→ Return: +8.3%
→ Memory: "This pattern led to +8.3% in 1 week"

lookforward_days = 30
→ Check price on 2024-02-15: $205
→ Return: +13.9%
→ Memory: "This pattern led to +13.9% in 1 month"
```

**How to choose**:

- **Match your holding period**: If you typically hold stocks for 2 weeks, use `lookforward_days=14`
- **Match your profit targets**: If you target 5-10% gains in a week, use `lookforward_days=7`
- **Match your risk tolerance**: Shorter horizons = more volatile, longer = smoother

### 2. `interval_days` - Sampling Frequency

**What it does**: Determines how often we create a memory sample.

**Example**:
```python
Period: 2024-01-01 to 2024-12-31 (365 days)

interval_days = 7 (weekly)
→ Samples: Jan 1, Jan 8, Jan 15, Jan 22, ...
→ Total: ~52 samples per stock

interval_days = 30 (monthly)
→ Samples: Jan 1, Feb 1, Mar 1, Apr 1, ...
→ Total: ~12 samples per stock
```

**How to choose**:

- **More samples = better learning**, but slower to build and more API costs
- **Market volatility**: Volatile markets → sample more frequently (7-14 days)
- **Data availability**: Some data sources may be rate-limited → larger intervals
- **Computational budget**: More samples = longer build time

---

## Strategy-Specific Recommendations

### 📈 Day Trading

**Goal**: Capture next-day momentum and intraday catalysts

```python
lookforward_days = 1      # Next day returns
interval_days = 1         # Daily samples (or 7 for weekly)
```

**What agents learn**:
- "After earnings beat + gap up, next day typically +2-3%"
- "High volume breakout → next day continuation 70% of time"
- "Morning dip + positive news → recovery same day"

**Best tickers**: High volume, volatile stocks (SPY, QQQ, TSLA, NVDA)

**Trade-offs**:
- ✅ Captures short-term patterns
- ❌ Very expensive (1 year = 250 samples × 10 stocks = 2,500 API calls)
- ❌ More noise, short-term randomness

**Recommendation**: Use `interval_days=7` instead of 1 to reduce costs while still capturing patterns

---

### 📊 Swing Trading

**Goal**: Capture weekly trends and momentum

```python
lookforward_days = 7      # 1-week returns
interval_days = 7         # Weekly samples
```

**What agents learn**:
- "Earnings beat + bullish MACD → +8% average in 1 week"
- "Bearish divergence + overbought RSI → -5% drop within 7 days"
- "Strong sector rotation + momentum → sustained weekly gains"

**Best tickers**: Liquid, trending stocks (AAPL, GOOGL, MSFT, NVDA, TSLA)

**Trade-offs**:
- ✅ Good balance of data quantity and quality
- ✅ Captures momentum and short-term fundamentals
- ✅ Reasonable API costs (52 samples/year)

**Recommendation**: **Best default choice** for most users

---

### 📅 Position Trading

**Goal**: Capture monthly fundamentals and trends

```python
lookforward_days = 30     # Monthly returns
interval_days = 30        # Monthly samples
```

**What agents learn**:
- "Revenue growth >20% + P/E <25 → +15% avg monthly return"
- "Sector headwinds + declining margins → avoid, -10% monthly"
- "Strong balance sheet + positive guidance → sustained monthly gains"

**Best tickers**: Fundamentally strong, large-cap stocks

**Trade-offs**:
- ✅ Low API costs (12 samples/year)
- ✅ Filters out short-term noise
- ✅ Focuses on fundamentals
- ❌ Fewer memories = less learning
- ❌ Misses short-term opportunities

**Recommendation**: Good for fundamental-focused strategies

---

### 📆 Long-term Investing

**Goal**: Capture quarterly/annual value trends

```python
lookforward_days = 90     # Quarterly returns (or 365 for annual)
interval_days = 90        # Quarterly samples
```

**What agents learn**:
- "Consistent earnings growth + moat → +25% quarterly average"
- "High debt + declining revenue → avoid, underperforms market"
- "Market leadership + innovation → sustained long-term outperformance"

**Best tickers**: Blue chips, value stocks (BRK.B, JPM, JNJ, PG, V)

**Trade-offs**:
- ✅ Very low API costs (4 samples/year)
- ✅ Focuses on long-term fundamentals
- ✅ Smooths out volatility
- ❌ Very few memories (4/year × 10 stocks = 40 total)
- ❌ Not useful for active trading

**Recommendation**: Only for true long-term buy-and-hold strategies

---

## Multi-Strategy Approach

**Best practice**: Build memories for **multiple strategies** and switch based on market conditions.

### Example: Comprehensive Setup

```python
# 1. Build swing trading memories (primary)
swing_memories = builder.populate_agent_memories(
    tickers=["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"],
    lookforward_days=7,
    interval_days=7,
    start_date="2023-01-01",
    end_date="2025-01-01"
)
# Save to: data/memories/swing_trading/

# 2. Build position trading memories (secondary)
position_memories = builder.populate_agent_memories(
    tickers=["AAPL", "GOOGL", "MSFT", "JPM", "JNJ"],
    lookforward_days=30,
    interval_days=30,
    start_date="2023-01-01",
    end_date="2025-01-01"
)
# Save to: data/memories/position_trading/

# 3. Use swing for active trades, position for core holdings
```

### When to Use Each:

| Market Condition | Strategy | Memory Set |
|-----------------|----------|------------|
| **High volatility** | Day/Swing | `lookforward_days=1-7` |
| **Trending market** | Swing | `lookforward_days=7` |
| **Range-bound** | Position | `lookforward_days=30` |
| **Bull market** | Swing/Position | `lookforward_days=7-30` |
| **Bear market** | Position/Long-term | `lookforward_days=30-90` |

---

## Advanced Configurations

### Earnings-Focused Memories

Capture post-earnings performance:

```python
# Sample around earnings dates
lookforward_days = 7      # 1 week post-earnings
interval_days = 90        # Quarterly (around earnings)
```

**What it captures**: Earnings reaction patterns

---

### Catalyst-Driven Memories

Capture event-driven moves:

```python
lookforward_days = 3      # Short-term catalyst impact
interval_days = 14        # Bi-weekly to catch various catalysts
```

**What it captures**: FDA approvals, product launches, analyst upgrades

---

### Hybrid Approach

Create memories for multiple horizons:

```python
# Short-term patterns
builder.populate_agent_memories(
    tickers=tickers,
    lookforward_days=7,
    interval_days=7,
    # Save to: memories/short_term/
)

# Long-term patterns
builder.populate_agent_memories(
    tickers=tickers,
    lookforward_days=30,
    interval_days=30,
    # Save to: memories/long_term/
)

# Load both: agents see patterns across time horizons
```

---

## Cost vs. Benefit Analysis

### API Call Estimates

For **10 tickers** over **2 years**:

| Config | Samples/Stock | Total Samples | API Calls* | Build Time** |
|--------|--------------|---------------|------------|--------------|
| Daily (1, 1) | ~500 | 5,000 | ~20,000 | 2-4 hours |
| Weekly (7, 7) | ~104 | 1,040 | ~4,160 | 30-60 min |
| Monthly (30, 30) | ~24 | 240 | ~960 | 10-20 min |
| Quarterly (90, 90) | ~8 | 80 | ~320 | 5-10 min |

*API calls = samples × 4 (market, news, sentiment, fundamentals) + returns
**Estimates vary based on API rate limits

### Recommended Starting Point

**For most users**:
```python
lookforward_days = 7      # Weekly horizon
interval_days = 14        # Bi-weekly samples
# Good balance: ~52 samples/year, manageable costs
```

**Why**:
- ✅ Enough memories for learning (~520 total for 10 stocks)
- ✅ Reasonable API costs
- ✅ Captures both short-term patterns and fundamentals
- ✅ Fast to build (20-30 minutes)

---

## Validation & Testing

### How to Know if Your Settings Are Good

After building memories, test them:

```python
# Build memories
memories = builder.populate_agent_memories(
    tickers=["AAPL"],
    lookforward_days=7,
    interval_days=14,
    start_date="2024-01-01",
    end_date="2024-12-01"
)

# Test retrieval
test_situations = [
    "Strong earnings beat with bullish technicals",
    "High valuation with negative sentiment",
    "Sector weakness with bearish momentum"
]

for situation in test_situations:
    results = memories["trader"].get_memories(situation, n_matches=3)
    print(f"\nQuery: {situation}")
    for i, r in enumerate(results, 1):
        print(f"  Match {i} (similarity: {r['similarity_score']:.2f})")
        print(f"  {r['recommendation'][:100]}...")
```

**Good signs**:
- ✅ Similarity scores >0.7 for relevant queries
- ✅ Recommendations make sense for the query
- ✅ Diverse outcomes (not all BUY or all SELL)

**Bad signs**:
- ❌ All similarity scores <0.5
- ❌ Recommendations don't match the query
- ❌ All memories say the same thing

→ If bad, try adjusting `interval_days` or adding more tickers

---

## Summary: Decision Tree

```
What's your trading style?
│
├─ Hold <1 week (Day/Swing)
│  ├─ lookforward_days: 1-7
│  └─ interval_days: 7-14
│
├─ Hold 1-4 weeks (Swing/Position)
│  ├─ lookforward_days: 7-30
│  └─ interval_days: 14-30
│
├─ Hold 1-3 months (Position)
│  ├─ lookforward_days: 30-90
│  └─ interval_days: 30
│
└─ Hold >3 months (Long-term)
   ├─ lookforward_days: 90-365
   └─ interval_days: 90
```

---

## Quick Start Commands

### Swing Trading (Recommended Default)
```bash
python scripts/build_strategy_specific_memories.py
# Choose option 2: Swing Trading
```

### Custom Configuration
```python
from tradingagents.agents.utils.historical_memory_builder import HistoricalMemoryBuilder

builder = HistoricalMemoryBuilder(config)

memories = builder.populate_agent_memories(
    tickers=["YOUR", "TICKERS"],
    start_date="2023-01-01",
    end_date="2025-01-01",
    lookforward_days=7,    # <-- Your choice
    interval_days=14       # <-- Your choice
)
```

---

## Conclusion

**TLDR**:
- **`lookforward_days`**: Match your typical holding period
- **`interval_days`**: Balance between data quantity and API costs
- **Default recommendation**: `lookforward_days=7, interval_days=14`
- **Use strategy-specific builder** for pre-optimized configurations

Your memories will be as good as your parameter choices! 🎯
