# Mock Trading System - Complete Guide

## Overview

The Mock Trading System is an autonomous trading simulator that:
- Starts with **$1000 initial capital**
- Makes daily buy/sell decisions using **TradingAgentsGraph AI analysis**
- Runs automatically via **scheduled daily execution**
- Tracks all transactions in **local SQLite database**
- Calculates **P&L and performance metrics**
- Prepares data for **Hindsight RL training**

## Architecture

### Core Components

#### 1. **Database** (`database.py`)
- **SQLite schema** with 8 tables:
  - `portfolios`: Portfolio state and metadata
  - `transactions`: All buy/sell operations with order status
  - `holdings`: Current stock positions
  - `daily_snapshots`: End-of-day portfolio state
  - `ai_decisions`: Trading signals from TradingAgentsGraph
  - `reflections`: Hindsight RL learnings
  - `corporate_actions`: Stock splits, dividends
  - `benchmark_data`: SPY/benchmark prices

- **Key Features**:
  - Auto-increment IDs
  - Foreign key constraints
  - Indexed for performance
  - In-memory or persistent storage

#### 2. **Portfolio Manager** (`portfolio_manager.py`)
- Manages positions and cash balance
- Calculates unrealized/realized P&L
- Updates prices for mark-to-market valuation
- Tracks metrics: returns %, alpha, Sharpe ratio

#### 3. **Order Manager** (`order_manager.py`)
- Order lifecycle: **PENDING → FILLED/PARTIALLY_FILLED/REJECTED**
- **Slippage calculation** and tolerance checking
- **Price types**: OPEN, CLOSE, VWAP, LAST
- Auto-expiring orders (1-hour default)
- Partial fill support

#### 4. **Corporate Actions Handler** (`corporate_actions.py`)
- **Stock splits**: Auto-adjust holdings quantities and avg_buy_price
- **Reverse splits**: Handle consolidations
- **Dividends**: Add cash to portfolio
- Retroactive adjustment for historical splits

#### 5. **Async Analyzer** (`async_analyzer.py`)
- Non-blocking AI analysis via **threading**
- Decouples analysis timing from execution
- Queue multiple tickers in parallel
- Tracks analysis latency
- Background execution without blocking

#### 6. **AI Decision Maker** (`decision_maker.py`)
- Wraps **TradingAgentsGraph** for analysis
- Converts AI signals to trading actions
- **Position sizing** based on portfolio risk
- Manages decision cache

#### 7. **Reward Calculator** (`reward_calculator.py`)
- **Reward types**:
  - **Benchmark Alpha**: Return - SPY return (basis points)
  - **Absolute Return**: Position P&L %
  - **Sharpe Ratio**: Risk-adjusted return
  - **Information Ratio**: Active alpha / tracking error
- Evaluates decision quality retrospectively
- Outperformance tracking vs benchmark

#### 8. **Benchmark Tracker** (`benchmark_tracker.py`)
- Fetches real **SPY daily returns**
- Calculates cumulative alpha
- Tracks **win rate** (days beating benchmark)
- Information ratio & tracking error

#### 9. **Trading Scheduler** (`scheduler.py`)
- **Two-phase execution**:
  1. **Analysis Phase** (09:30): Queue all AI analyses asynchronously
  2. **Execution Phase** (14:00): Execute trades using cached decisions
- APScheduler-based cron scheduling
- Handles variable analysis completion times

#### 10. **Trading Engine** (`engine.py`)
- Integrates all components
- Real prices via **yfinance**
- Order routing to OrderManager
- Portfolio updates
- Daily snapshots

## Workflow

```
Daily at 09:30 (Analysis Phase)
  ├─ Queue TradingAgentsGraph.propagate() for each ticker (async)
  ├─ Analyses run in background (5-30 minutes each)
  └─ Results cached when ready

Daily at 14:00 (Execution Phase)
  ├─ Retrieve cached AI decisions
  ├─ Apply position sizing (2% risk per trade)
  ├─ Create orders (PENDING state)
  ├─ Execute orders:
  │  ├─ Check slippage tolerance
  │  ├─ Validate available volume
  │  └─ Transition to FILLED/PARTIAL/REJECTED
  ├─ Update portfolio holdings
  ├─ Log transaction to database
  ├─ Apply corporate actions (splits, dividends)
  └─ Create daily snapshot + calculate alpha

End-of-Day
  ├─ Calculate unrealized P&L
  ├─ Compare to benchmark (SPY)
  ├─ Store reflection for Hindsight RL
  └─ Prepare next day's analysis
```

## Usage

### Starting the System

```bash
# Start mock trading with default settings
tradingagents mock-trade start

# Start with custom parameters
tradingagents mock-trade start \
  --capital 5000 \
  --analysis-time 09:30 \
  --execution-time 14:00 \
  --watchlist "NVDA,AAPL,TSLA" \
  --db ~/.tradingagents/my_backtest.db
```

### Checking Status

```bash
# View current portfolio
tradingagents mock-trade status

# Output:
# Portfolio ID: 1
# Initial Capital: $1,000.00
# Current Balance: $1,245.50
# Cash Available: $150.00
# 
# Holdings:
# NVDA: 5 shares @ $100 avg, current $105 → +$25 unrealized
# AAPL: 10 shares @ $150 avg, current $155 → +$50 unrealized
```

### Generating Reports

```bash
# View 7-day performance report
tradingagents mock-trade report

# Export to CSV
tradingagents mock-trade report --days 30 --output performance.csv

# Output:
# Date        | Portfolio Value | Daily Return | Alpha
# 2025-01-01  | $1,010.50       | +1.05%       | +0.15%
# 2025-01-02  | $1,008.30       | -0.22%       | -0.52%
# ...
```

### Stopping System

```bash
tradingagents mock-trade stop
```

## Key Features

### 1. Order Execution Model

**States**:
- `PENDING`: Awaiting execution
- `FILLED`: Fully executed at reference price
- `PARTIALLY_FILLED`: Partial volume filled (liquidity constraints)
- `REJECTED`: Slippage exceeded tolerance or insufficient volume

**Example**:
```python
order = engine.create_buy_order("NVDA", 10, PriceType.CLOSE, ref_price=100.0)

# Reference: $100, accept up to 2% slippage
# Actual fill: $101.50 (1.5% slippage) ✓ FILLED
# Actual fill: $103.00 (3.0% slippage) ✗ REJECTED
```

### 2. Async Analysis Execution

**Problem**: TradingAgentsGraph analysis takes 5-30 minutes. If queued at 09:30, market closes before decision completes.

**Solution**: 
- 09:30: Queue analysis asynchronously (non-blocking)
- 14:00: Use cached result from whenever analysis finished
- Capture analysis latency for performance measurement

```python
# Start analysis at 09:30
task_id = decision_maker.queue_analysis("NVDA", "2025-01-15")

# 14:00: Decision already cached and ready
decision = decision_maker.get_cached_decision(task_id)
if decision:
    engine.execute_order(...)
```

### 3. Corporate Actions

**Stock Split Handling**:
```python
# Before: 100 shares @ $150 avg
# Event: 10:1 split (each share → 10 new shares)
# After: 1000 shares @ $15 avg
# Portfolio value unchanged: $15,000
```

**Dividend Handling**:
```python
# 100 shares @ $150 = $15,000 position
# Dividend: $1 per share = $100 cash
# Portfolio value increases to $15,100
```

### 4. Reward Functions

**For Training Hindsight RL**:

**Option 1: Benchmark Alpha**
```
Reward = (Decision Return % - SPY Return %) × 100 basis points
Example: Position +10%, SPY +2% → Alpha = +800 bp
```

**Option 2: Absolute Return**
```
Reward = Decision Return % (simple)
Example: Position closed at +10% → Reward = +10%
```

**Option 3: Sharpe Ratio**
```
Reward = (Annual Mean Return - Risk-Free Rate) / Annual Volatility
Captures risk-adjusted performance
```

### 5. Performance Metrics

**Daily Tracking**:
- Portfolio Value (NAV)
- Daily Return %
- Cumulative Return %
- Dividend Income
- Alpha vs Benchmark

**Period Stats**:
- Win Rate: % of days beating SPY
- Tracking Error: Volatility of alpha
- Information Ratio: Alpha / Tracking Error
- Cumulative Alpha: Sum of daily alpha

## Database Schema

### portfolios table
```sql
id, initial_capital, current_balance, cash_available, 
date_created, date_last_updated, status
```

### transactions table
```sql
id, portfolio_id, transaction_type (BUY/SELL),
ticker, quantity_requested, quantity_filled,
order_status (PENDING/FILLED/PARTIAL/REJECTED),
price_type (OPEN/CLOSE/VWAP/LAST),
price_per_share, total_value, slippage_pct, fees,
timestamp, execution_timestamp, expiry_timestamp, 
ai_decision_id
```

### ai_decisions table
```sql
id, portfolio_id, ticker, decision (BUY/SELL/HOLD),
confidence_score, reasoning,
analysis_start_time, analysis_end_time,
executed, execution_status,
execution_price, realized_pl,
reward_score, reward_type (BENCHMARK_ALPHA/ABSOLUTE_RETURN/SHARPE_RATIO)
```

### daily_snapshots table
```sql
id, portfolio_id, date,
total_portfolio_value, cash_balance, total_invested,
daily_return, cumulative_return,
dividend_income, benchmark_return, alpha
```

## Hindsight RL Integration

### Reward Dataset Preparation

After 1 week of trading (or when ready):

```python
# Export decisions with outcomes
from tradingagents.mock_trading import RewardCalculator

rc = RewardCalculator()

# For each closed position:
decisions_with_rewards = []
for decision in db.get_closed_decisions():
    reward = rc.calculate_reward(
        decision_id=decision.id,
        reward_type=RewardType.BENCHMARK_ALPHA,
        benchmark_returns=spy_daily_returns
    )
    decisions_with_rewards.append({
        "decision": decision.reasoning,  # AI analysis text
        "action": decision.decision,      # BUY/SELL/HOLD
        "reward": reward,                 # Numerical reward signal
        "confidence": decision.confidence_score,
    })

# Use for Hindsight RL training
from tradingagents.hindsight_rl import HindsightRLTrainer

trainer = HindsightRLTrainer(decisions_with_rewards)
trainer.train()  # Fine-tune TradingAgentsGraph
```

### Reflection Loop

After each closed position:
```python
reflection = {
    "decision_id": 123,
    "entry_decision": "Buy NVDA due to positive sentiment",
    "entry_price": $100,
    "exit_price": $110,
    "reward": +10.0,  # %
    "outperformed_benchmark": True,
    "lessons": [
        "Positive sentiment + tech uptrend = strong signal",
        "Held position for 5 days = good timing"
    ]
}
```

## Configuration

### Defaults
- Initial Capital: **$1,000**
- Max Risk/Trade: **2% of portfolio**
- Max Position: **10% of portfolio**
- Order Expiry: **1 hour**
- Slippage Tolerance: **1%**
- Benchmark: **SPY**
- Analysis Time: **09:30 ET**
- Execution Time: **14:00 ET**

### Override via CLI
```bash
tradingagents mock-trade start \
  --capital 10000 \
  --analysis-time 08:00 \
  --execution-time 16:00 \
  --watchlist "QQQ,SPY,IWM"
```

## Troubleshooting

### Issue: "No analysis results when executing"
- **Solution**: Increase execution time buffer (e.g., 14:00 for 09:30 start)
- Check analysis latency: `analyzer.get_analysis_latency_stats()`

### Issue: "Order rejected due to slippage"
- **Solution**: Increase tolerance or use VWAP instead of CLOSE
- Check market conditions: `engine.get_current_price("NVDA")`

### Issue: "Corporate action not applied"
- **Solution**: Ensure action date before checkpoint date
- Manually apply: `corporate_actions_handler.apply_stock_split(...)`

### Issue: "Database locked"
- **Solution**: Only one process should access database
- Use different db paths for parallel backtests

## Performance Tips

1. **Async Analysis**: Use AsyncAnalyzer for non-blocking analysis
2. **Caching**: Decision cache reduces redundant queries
3. **Batch Updates**: Update prices once per day
4. **Indexing**: Database creates auto-indexes on foreign keys
5. **Slippage Model**: Realistic slippage improves Hindsight RL training

## Next Steps: Hindsight RL

Once 1+ weeks of data collected:

1. **Export Dataset**: `hindsight_dataset.csv` with decision + reward
2. **Analyze Patterns**: Identify high-reward decision templates
3. **Train Model**: Fine-tune TradingAgentsGraph weights
4. **Validate**: Compare new model on unseen test set
5. **Deploy**: Use improved model for live trading

## Support

- Issues: Check logs in `~/.tradingagents/logs/`
- Database: `~/.tradingagents/mock_trading.db`
- Reports: Export CSV for Excel analysis

## License

Part of TradingAgents framework - see main LICENSE
