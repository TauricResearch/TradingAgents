# Crypto Backtesting Framework - Phase 3 Implementation Complete ✅

## Overview

Phase 3 of the crypto market migration has been successfully implemented! The TradingAgents framework now has a **complete backtesting infrastructure** tailored for cryptocurrency markets with 24/7 trading, higher volatility, and crypto-specific metrics.

## What's Been Implemented

### 1. **Crypto Backtesting Engine** ✅

#### File: `tradingagents/backtesting/crypto_backtest_engine.py`

**Core backtesting engine with crypto-specific features:**

**Components**:
- `CryptoBacktestEngine` - Main engine class
- `Trade` - Trade execution record
- `Position` - Current position tracking
- `OrderType` - BUY/SELL/HOLD enums

**Features**:
- ✅ 24/7 trade execution (no market hours)
- ✅ Portfolio management (cash + positions)
- ✅ Commission & slippage modeling (0.1% + 0.2%)
- ✅ Stop loss & take profit automation
- ✅ Risk-based position sizing
- ✅ Performance metrics calculation
- ✅ Trade history tracking

**Key Parameters**:
```python
initial_capital=10000        # Starting capital
commission_rate=0.001        # 0.1% (higher than stocks)
slippage_rate=0.002          # 0.2% (higher than stocks)
max_position_size=0.20       # 20% per position
stop_loss_pct=0.15           # 15% stop loss
take_profit_pct=0.30         # 30% take profit
risk_per_trade=0.02          # 2% risk per trade
```

**Usage**:
```python
from tradingagents.backtesting import CryptoBacktestEngine, OrderType

engine = CryptoBacktestEngine(initial_capital=10000)

# Execute trade
trade = engine.execute_trade(
    timestamp=datetime(2024, 1, 1),
    symbol="BTC/USDT",
    order_type=OrderType.BUY,
    price=40000,
    reason="Agent buy signal"
)

# Get metrics
metrics = engine.get_performance_metrics()
```

---

### 2. **Crypto Data Loader** ✅

#### File: `tradingagents/backtesting/crypto_data_loader.py`

**Historical data management for backtesting:**

**Features**:
- ✅ CCXT exchange integration (100+ exchanges)
- ✅ Multiple timeframes (1m to 1w)
- ✅ Data caching (avoid re-downloads)
- ✅ Bull/bear cycle identification
- ✅ Market cycle analysis
- ✅ Volatility calculation

**Built-in Market Cycles**:
```python
CRYPTO_MARKET_CYCLES = {
    'BTC/USDT': [
        {'name': '2017 Bull Run', 'start': '2017-01-01', 'end': '2017-12-17'},
        {'name': '2018 Bear Market', 'start': '2017-12-17', 'end': '2018-12-15'},
        {'name': '2020-2021 Bull Run', 'start': '2020-03-13', 'end': '2021-11-10'},
        {'name': '2022 Bear Market', 'start': '2021-11-10', 'end': '2022-11-21'},
        {'name': '2023-2024 Recovery', 'start': '2023-01-01', 'end': '2024-03-14'},
    ]
}
```

**Usage**:
```python
from tradingagents.backtesting.crypto_data_loader import CryptoDataLoader

loader = CryptoDataLoader(exchange_id='binance')

# Fetch data
df = loader.fetch_ohlcv(
    symbol='BTC/USDT',
    timeframe='1d',
    since=datetime(2024, 1, 1),
    until=datetime(2024, 6, 1)
)

# Identify market cycles
df_with_cycles = loader.identify_market_cycles(df)
cycles = loader.get_historical_cycles(df_with_cycles)
```

---

### 3. **Crypto Strategy Evaluator** ✅

#### File: `tradingagents/backtesting/crypto_strategy_evaluator.py`

**Strategy testing and validation framework:**

**Features**:
- ✅ Single backtest execution
- ✅ Agent-based backtesting
- ✅ Walk-forward testing
- ✅ Strategy comparison
- ✅ Market cycle testing
- ✅ Agent accuracy tracking

**Key Methods**:

**1. run_backtest** - Standard backtest
```python
metrics = evaluator.run_backtest(
    symbol='BTC/USDT',
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 6, 1),
    strategy_func=my_strategy
)
```

**2. run_agent_backtest** - With agent integration
```python
metrics = evaluator.run_agent_backtest(
    symbol='BTC/USDT',
    start_date=start_date,
    end_date=end_date,
    agent_func=crypto_agent_decision_func
)
```

**3. run_walk_forward_test** - Rolling window validation
```python
results = evaluator.run_walk_forward_test(
    symbol='BTC/USDT',
    start_date=start_date,
    end_date=end_date,
    strategy_func=my_strategy,
    train_period_days=90,
    test_period_days=30
)
```

**4. compare_strategies** - Multi-strategy comparison
```python
comparison = evaluator.compare_strategies(
    symbol='BTC/USDT',
    start_date=start_date,
    end_date=end_date,
    strategies={
        'Buy & Hold': buy_hold_strategy,
        'MA Crossover': ma_crossover_strategy,
        'RSI Mean Reversion': rsi_strategy
    }
)
```

**5. test_on_market_cycles** - Cycle-specific testing
```python
results = evaluator.test_on_market_cycles(
    symbol='BTC/USDT',
    strategy_func=my_strategy,
    cycles=CRYPTO_MARKET_CYCLES['BTC/USDT']
)
```

---

### 4. **Agent Integration** ✅

**AgentDecision class for agent-based backtesting:**

```python
from tradingagents.backtesting.crypto_strategy_evaluator import AgentDecision

def crypto_agent_func(timestamp, row):
    """Agent decision function."""
    # Call your crypto agents here
    # onchain_result = onchain_analyst(state)
    # fundamentals_result = fundamentals_analyst(state)
    # technical_result = technical_analyst(state)

    # Aggregate agent signals
    if overall_bullish:
        return AgentDecision(
            signal="BUY",
            confidence=0.85,
            reasoning="Strong bullish signals from agents"
        )
    elif overall_bearish:
        return AgentDecision(
            signal="SELL",
            confidence=0.75,
            reasoning="Bearish signals from agents"
        )
    else:
        return AgentDecision(
            signal="HOLD",
            confidence=0.60,
            reasoning="Mixed signals"
        )
```

---

### 5. **Performance Metrics** ✅

**Comprehensive analytics suite:**

**Metrics Calculated**:
```python
{
    'initial_capital': 10000.00,
    'final_capital': 12500.00,
    'total_return': 0.25,
    'total_return_pct': 25.0,          # Total return %
    'max_drawdown': 0.15,
    'max_drawdown_pct': 15.0,          # Max drawdown %
    'sharpe_ratio': 1.85,              # Risk-adjusted return
    'total_trades': 25,
    'winning_trades': 18,
    'losing_trades': 7,
    'win_rate': 0.72,
    'win_rate_pct': 72.0,              # Win rate %
    'avg_win': 4.5,                    # Avg win %
    'avg_loss': -2.1,                  # Avg loss %
    'profit_factor': 2.14,             # Avg win / Avg loss
    'total_commission_paid': 125.50,
    'total_slippage_cost': 251.00,
}
```

---

## Example Strategies Provided

### 1. Buy and Hold
```python
def buy_and_hold_strategy(timestamp, row, engine):
    if len(engine.positions) == 0:
        return OrderType.BUY, "Initial buy"
    return OrderType.HOLD, "Holding"
```

### 2. Moving Average Crossover
```python
class MovingAverageCrossover:
    def __init__(self, short_window=50, long_window=200):
        ...

    def __call__(self, timestamp, row, engine):
        # Golden cross / Death cross logic
        ...
```

### 3. RSI Mean Reversion
```python
class RSIMeanReversion:
    def __init__(self, period=14, oversold=30, overbought=70):
        ...

    def __call__(self, timestamp, row, engine):
        # Buy oversold, sell overbought
        ...
```

### 4. Simulated Agent Strategy
```python
def simulated_agent_strategy(timestamp, row, engine):
    # Aggregate technical, fundamental, on-chain signals
    ...
```

### 5. Volatility Breakout
```python
class VolatilityBreakout:
    def __init__(self, lookback=20, std_multiplier=2.0):
        ...

    def __call__(self, timestamp, row, engine):
        # Trade breakouts
        ...
```

---

## File Structure

```
TradingAgents/
├── tradingagents/
│   └── backtesting/                              # NEW
│       ├── __init__.py                           # NEW
│       ├── crypto_backtest_engine.py             # NEW - Core engine
│       ├── crypto_data_loader.py                 # NEW - Data management
│       └── crypto_strategy_evaluator.py          # NEW - Strategy testing
├── examples/
│   └── crypto_backtest_examples.py               # NEW - Example strategies
├── test_crypto_backtest.py                       # NEW - Test suite
└── CRYPTO_PHASE3_README.md                       # NEW - This file
```

---

## Quick Start

### Installation

Phase 3 builds on Phases 1 & 2:
```bash
pip install ccxt pandas numpy
```

### Basic Backtest

```python
from tradingagents.backtesting import CryptoBacktestEngine, OrderType
from tradingagents.backtesting.crypto_data_loader import CryptoDataLoader
from tradingagents.backtesting.crypto_strategy_evaluator import CryptoStrategyEvaluator
from datetime import datetime

# 1. Create components
engine = CryptoBacktestEngine(initial_capital=10000)
loader = CryptoDataLoader(exchange_id='binance')
evaluator = CryptoStrategyEvaluator(engine, loader)

# 2. Define strategy
def my_strategy(timestamp, row, engine):
    if len(engine.positions) == 0 and row['close'] < 40000:
        return OrderType.BUY, "Buy below 40k"
    elif len(engine.positions) > 0 and row['close'] > 45000:
        return OrderType.SELL, "Sell above 45k"
    return OrderType.HOLD, "No signal"

# 3. Run backtest
metrics = evaluator.run_backtest(
    symbol='BTC/USDT',
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 6, 1),
    strategy_func=my_strategy
)

# 4. View results
print(f"Total Return: {metrics['total_return_pct']:.2f}%")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
print(f"Win Rate: {metrics['win_rate_pct']:.2f}%")
```

---

## Testing

### Run Test Suite

```bash
python test_crypto_backtest.py
```

**Expected Output**:
```
================================================================================
  CRYPTO BACKTESTING FRAMEWORK TEST SUITE - PHASE 3
================================================================================

✅ PASSED - engine
✅ PASSED - data_loader
✅ PASSED - evaluator
✅ PASSED - agent_decision
✅ PASSED - metrics
✅ PASSED - integration

Results: 6/6 tests passed

🎉 All backtesting framework tests passed! Phase 3 core complete.
```

### Run Example Strategies

```bash
python examples/crypto_backtest_examples.py
```

---

## Integration with Phase 2 Agents

### Integrate Crypto Agents into Backtest

```python
from tradingagents.agents.analysts.onchain_analyst import create_onchain_analyst
from tradingagents.agents.analysts.crypto_fundamentals_analyst import create_crypto_fundamentals_analyst
from tradingagents.agents.analysts.crypto_technical_analyst import create_crypto_technical_analyst
from langchain_openai import ChatOpenAI

# Create agents
llm = ChatOpenAI(model="gpt-4o-mini")
onchain_analyst = create_onchain_analyst(llm)
fundamentals_analyst = create_crypto_fundamentals_analyst(llm)
technical_analyst = create_crypto_technical_analyst(llm)

def agent_based_strategy(timestamp, row, engine):
    """Strategy using crypto agents."""

    # Prepare state for agents
    state = {
        "trade_date": timestamp.strftime("%Y-%m-%d"),
        "company_of_interest": "BTC/USDT",
        "messages": []
    }

    # Get agent decisions
    onchain_result = onchain_analyst(state)
    fundamentals_result = fundamentals_analyst(state)
    technical_result = technical_analyst(state)

    # Aggregate signals (simplified)
    bullish_signals = 0
    bearish_signals = 0

    # Parse agent reports for signals
    # (This would need more sophisticated parsing in production)
    if "BULLISH" in onchain_result.get('onchain_report', ''):
        bullish_signals += 1
    if "BEARISH" in onchain_result.get('onchain_report', ''):
        bearish_signals += 1

    # Make decision
    if bullish_signals > bearish_signals and len(engine.positions) == 0:
        return OrderType.BUY, f"Agent consensus: {bullish_signals} bullish signals"
    elif bearish_signals > bullish_signals and len(engine.positions) > 0:
        return OrderType.SELL, f"Agent consensus: {bearish_signals} bearish signals"

    return OrderType.HOLD, "No clear consensus"

# Run backtest with agents
metrics = evaluator.run_backtest(
    symbol='BTC/USDT',
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 6, 1),
    strategy_func=agent_based_strategy
)
```

---

## Advanced Features

### 1. Walk-Forward Testing

Test strategy robustness with rolling windows:

```python
results = evaluator.run_walk_forward_test(
    symbol='BTC/USDT',
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2024, 1, 1),
    strategy_func=my_strategy,
    train_period_days=90,   # 3 months training
    test_period_days=30     # 1 month testing
)

# Analyze consistency
returns = [r['total_return_pct'] for r in results]
print(f"Average Return: {np.mean(returns):.2f}%")
print(f"Return Std Dev: {np.std(returns):.2f}%")
```

### 2. Strategy Comparison

Compare multiple strategies head-to-head:

```python
strategies = {
    'Buy & Hold': buy_hold_strategy,
    'MA Crossover': MovingAverageCrossover(50, 200),
    'RSI': RSIMeanReversion(14, 30, 70),
    'Agent-Based': agent_based_strategy
}

comparison_df = evaluator.compare_strategies(
    symbol='BTC/USDT',
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 6, 1),
    strategies=strategies
)

# Best strategy by Sharpe ratio
best = comparison_df.loc[comparison_df['sharpe_ratio'].idxmax()]
print(f"Best Strategy: {best['strategy_name']}")
```

### 3. Market Cycle Analysis

Test how strategy performs in bull vs bear markets:

```python
from tradingagents.backtesting.crypto_data_loader import CRYPTO_MARKET_CYCLES

results = evaluator.test_on_market_cycles(
    symbol='BTC/USDT',
    strategy_func=my_strategy,
    cycles=CRYPTO_MARKET_CYCLES['BTC/USDT']
)

# Compare bull vs bear performance
for cycle_name, metrics in results.items():
    print(f"{cycle_name}: {metrics['total_return_pct']:.2f}%")
```

---

## Performance Expectations

### Crypto vs Stock Backtesting

| Metric | Stock Market | Crypto Market |
|--------|-------------|---------------|
| **Sharpe Target** | 1.2+ | 1.5+ (higher volatility) |
| **Max Drawdown** | 15% | 30% (higher tolerance) |
| **Win Rate** | 55-60% | 50-65% (higher variance) |
| **Commission** | 0.05% | 0.1% (higher) |
| **Slippage** | 0.05% | 0.2% (higher) |
| **Trading Hours** | 6.5h/day | 24h/day |

### Realistic Expectations

**Good Performance**:
- Sharpe Ratio: 1.5-2.5
- Max Drawdown: 20-30%
- Win Rate: 55-65%
- Annual Return: 30-100%

**Excellent Performance**:
- Sharpe Ratio: 2.5+
- Max Drawdown: <20%
- Win Rate: 65%+
- Annual Return: 100%+

---

## Known Limitations

1. **Data Quality**: CCXT data may have gaps or inconsistencies
2. **Slippage Modeling**: Simple percentage-based (not order book depth)
3. **Exchange Fees**: Fixed rate (doesn't account for VIP tiers)
4. **Market Impact**: Assumes orders don't move the market
5. **Overnight Gaps**: Crypto doesn't have them, but model is ready if needed

---

## Best Practices

### 1. Data Preparation
- Always cache data for repeated testing
- Validate data quality before backtesting
- Use multiple timeframes for robustness

### 2. Strategy Development
- Start with simple strategies
- Add complexity incrementally
- Test on multiple market conditions

### 3. Validation
- Use walk-forward testing
- Test on unseen data (out-of-sample)
- Validate on different assets (BTC, ETH, SOL)

### 4. Risk Management
- Always use stop losses
- Position size based on risk
- Don't overtrade (commission drag)

### 5. Agent Integration
- Use agent decisions as signals, not certainties
- Combine multiple agent perspectives
- Track agent accuracy over time

---

## Troubleshooting

### Data Loading Issues
```python
# Clear cache if data seems stale
loader.clear_cache()

# Fetch with cache disabled
df = loader.fetch_ohlcv(symbol, timeframe, since, until, use_cache=False)
```

### Performance Issues
```python
# Reduce data range
start_date = datetime(2024, 5, 1)  # Shorter period
end_date = datetime(2024, 6, 1)

# Use daily timeframe instead of hourly
timeframe = '1d'  # Instead of '1h'
```

### Strategy Not Trading
```python
# Add debug prints
def my_strategy(timestamp, row, engine):
    print(f"{timestamp}: Price={row['close']}, Positions={len(engine.positions)}")
    ...
```

---

## Next Steps

### Immediate (Phase 3 Complete)
- ✅ Backtesting engine implemented
- ✅ Data loader with caching
- ✅ Strategy evaluator
- ✅ Agent integration interface
- ✅ Performance metrics

### Phase 4: Paper Trading (4-8 weeks)
- [ ] Live exchange API integration
- [ ] Real-time data streaming
- [ ] Order execution monitoring
- [ ] 24/7 bot operation
- [ ] Performance tracking dashboard

### Phase 5: Live Deployment
- [ ] Real capital allocation
- [ ] Risk management safeguards
- [ ] Monitoring and alerting
- [ ] Portfolio rebalancing
- [ ] Continuous improvement

---

## Summary

✅ **Complete Backtesting Framework**
✅ **5 Example Strategies**
✅ **Agent Integration Ready**
✅ **Comprehensive Testing**
✅ **Production-Ready Code**

**Status**: Phase 3 Complete - Ready for Phase 4 (Paper Trading)

**Date**: October 7, 2025

---

For more information:
- Phase 1: `CRYPTO_PHASE1_README.md` - Data infrastructure
- Phase 2: `CRYPTO_PHASE2_README.md` - Agent adaptation
- Phase 3: `CRYPTO_PHASE3_README.md` - Backtesting framework (this file)
- Migration Plan: `CRYPTO_MIGRATION_PLAN.md` - Full roadmap
