# Algo Trading System - Complete Guide

## Overview

A complete algorithmic trading system that combines your multi-agent AI analysis with automated trade execution, position management, and risk controls.

**Key Features:**
- ✅ Screen stocks and detect pump signals
- ✅ Automatic position sizing (8% max per stock)
- ✅ Portfolio limits (25% max in risky trades)
- ✅ Profit targets & stop losses
- ✅ Time-based position exits
- ✅ Webull paper trading integration
- ✅ Full audit trail of all trades

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         ALGO TRADING BOT (Main Orchestrator)             │
└─────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │   Analysis   │    │  Portfolio   │    │   Execution  │
  │   (LangGraph)│    │  Manager     │    │   (Webull)   │
  │              │    │              │    │              │
  │ • Screening  │    │ • Position   │    │ • Buy/Sell   │
  │ • Pump Det.  │    │   sizing     │    │ • Orders     │
  │ • Signals    │    │ • Limits     │    │ • Account    │
  │              │    │ • Tracking   │    │   info       │
  └──────────────┘    └──────────────┘    └──────────────┘
         │                    │                    │
         └────────────────────┴────────────────────┘
                        │
                        ▼
              ┌──────────────────────┐
              │  Exit Strategy       │
              │                      │
              │ • Profit targets     │
              │ • Stop losses        │
              │ • Time limits        │
              │ • Trailing stops     │
              └──────────────────────┘
```

## Core Components

### 1. Portfolio Manager (`tradingagents/strategy/portfolio_manager.py`)

Manages position sizing and portfolio constraints.

**Key Settings:**
- `max_position_pct`: Max 8% per stock
- `max_risky_pct`: Max 25% in risky trades (pump/momentum)
- `max_positions`: Max 10 open positions
- `min_position_size`: Min $100 per trade
- `max_position_size`: Max $2000 per trade

**Methods:**
```python
# Calculate position size based on signal strength
position = pm.calculate_position_size(
    current_price=150.0,
    signal_score=75.0,  # 0-100
    position_type="pump"
)

# Add a position
pm.add_position(
    ticker="NVDA",
    shares=10,
    entry_price=150.0,
    signal_score=75.0,
    position_type="pump"
)

# Close a position
result = pm.close_position(
    ticker="NVDA",
    exit_price=158.0,
    reason="profit_target"
)

# Get status
status = pm.get_portfolio_status()
# Returns: {
#   "total_value": 10500.0,
#   "cash": 8700.0,
#   "positions_value": 1800.0,
#   "num_positions": 2,
#   "cash_utilization": 17.1%,
#   "risky_exposure": 12.5%
# }
```

**How Position Sizing Works:**

1. Max position = 8% of portfolio
2. Scaled by signal strength: position = max * (signal_score / 100)
3. Capped by min ($100) and max ($2000)
4. Check if enough cash available
5. For risky trades: check doesn't exceed 25% risky limit

Example:
- Portfolio: $10,000
- Max position: $800 (8%)
- Signal score: 75% → position = $800 * 0.75 = $600
- Stock price: $150 → shares = 4

### 2. Exit Strategy (`tradingagents/strategy/exit_strategy.py`)

Automatically exits positions when:

**Default Settings:**
- **Profit Target**: 5% gain → SELL
- **Stop Loss**: 2% loss → SELL
- **Max Hold**: 5 days → SELL (even if break-even)
- **Trailing Stop**: 2% from peak → SELL
- **Signal Deterioration**: Signal drops below 40 → SELL (for pump trades)

**Example:**
```python
exit = ExitStrategy()

# Check if should exit
signal = exit.evaluate_exit(
    ticker="NVDA",
    current_price=158.0,
    entry_price=150.0,
    entry_date=datetime.now(),
    signal_score=35.0,
    position_type="pump"
)

# Returns: {
#   "exit_signal": True,
#   "reason": "profit_target",  # or "stop_loss", "time_limit", etc.
#   "exit_price": 158.0,
#   "pnl_pct": 5.3%
# }

# Get targets
targets = exit.get_exit_targets(entry_price=150.0)
# Returns: {
#   "profit_target": 157.50,   # +5%
#   "stop_loss": 147.00,       # -2%
#   "trailing_stop_trigger": 147.00
# }
```

### 3. Trade Validator (`tradingagents/strategy/trade_validator.py`)

Pre-flight checks before executing any trade.

**Validates:**
- Sufficient funds
- Position size constraints
- Price sanity (no >50% jumps)
- Liquidity

```python
validator = TradeValidator()

# Validate buy
result = validator.validate_buy_order(
    ticker="NVDA",
    shares=10,
    price=150.0,
    available_cash=8700.0,
    portfolio_value=10000.0,
    max_position_pct=0.08
)
# Returns: {"is_valid": True, "order_value": 1500.0, ...}

# Validate sell
result = validator.validate_sell_order(
    ticker="NVDA",
    shares=10,
    price=158.0,
    position_shares=10,
    position_value=1500.0
)
```

### 4. Paper Trading (`tradingagents/agents/trader/paper_trading.py`)

Webull integration for paper trading execution.

**Setup:**
```bash
pip install webull
```

**Usage:**
```python
from tradingagents.agents.trader.paper_trading import PaperTrader

# Initialize
trader = PaperTrader(
    email="your_email@example.com",
    password="your_password",
    is_paper=True
)

# Login
trader.login()

# Get trade token (required once per session)
trader.get_trade_token(pin="123456")

# Buy
trader.place_buy_order(
    ticker="NVDA",
    quantity=10,
    limit_price=150.0
)

# Sell
trader.place_sell_order(
    ticker="NVDA",
    quantity=10,
    limit_price=158.0
)

# Get positions
positions = trader.get_positions()

# Get account balance
account = trader.get_account_balance()
# Returns: {
#   "account_value": 10500.0,
#   "cash": 8700.0,
#   "buying_power": 34800.0
# }

# Get quote
quote = trader.get_stock_quote("NVDA")
# Returns: {"price": 150.25, "bid": 150.20, "ask": 150.30}
```

## Main Workflow

### 1. Demo Mode (No Authentication)

Test without Webull credentials:

```python
from algo_trading_workflow import AlgoTradingBot

# Create bot in demo mode
bot = AlgoTradingBot(
    portfolio_cash=10000.0,
    paper_trading=False,  # Demo mode
    selected_analysts=["market"]
)

# Run single iteration
bot.run_iteration()

# Check status
print(bot.get_status())

# View summary
bot.print_summary()
```

### 2. Paper Trading Mode (Webull Connected)

Live paper trading with real data:

```python
import os

# Set environment variables
os.environ["WEBULL_EMAIL"] = "your_email@example.com"
os.environ["WEBULL_PASSWORD"] = "your_password"

bot = AlgoTradingBot(
    portfolio_cash=10000.0,
    paper_trading=True,
    selected_analysts=["market", "social", "news"],
    webull_email=os.environ.get("WEBULL_EMAIL"),
    webull_password=os.environ.get("WEBULL_PASSWORD"),
    webull_pin="123456"  # Trading PIN
)

# Run continuously (5 min intervals)
bot.run(iterations=-1, interval_seconds=300)
```

### 3. Run Specific Iterations

```python
# Run 10 iterations (50 min total)
bot.run(iterations=10, interval_seconds=300)

# Print summary
bot.print_summary()

# Save state
bot.save_state("my_trading_state.json")
```

## Trade Flow Example

Let's say you're running the bot on NVDA:

```
1. SCREENING (find candidates)
   → NVDA identified as trending

2. PUMP DETECTION (analyze opportunity)
   → Pump score: 82/100
   → Signal type: "pump"

3. ENTRY DECISION
   → Signal >= 70? YES
   → Position size = 8% * (82/100) = $656 → 4 shares @ $150

4. POSITION ADDED
   → Portfolio: $9,400 cash, 4 NVDA shares

5. MONITORING (continuous)
   → Current: $158
   → P/L: +5.3% → HIT PROFIT TARGET → EXIT
   → Profit: $32
   
   OR if:
   → Current: $147
   → P/L: -2.0% → HIT STOP LOSS → EXIT
   → Loss: $12
   
   OR if:
   → 5 days passed → HIT TIME LIMIT → EXIT
   → P/L: -1.5% → Loss: $9

6. POSITION CLOSED
   → Trade recorded
   → Cash restored
   → Ready for next trade
```

## Risk Management Summary

| Constraint | Limit | Why |
|-----------|-------|-----|
| Max position | 8% | Doesn't bet too much on one stock |
| Max risky | 25% | Doesn't exceed comfort zone for high-risk trades |
| Max positions | 10 | Not too many to manage |
| Stop loss | 2% | Cuts losses quickly |
| Profit target | 5% | Takes gains before reversal |
| Max hold | 5 days | Doesn't hold momentum trades too long |
| Trailing stop | 2% | Exits if momentum reverses |

## Monitoring & Debugging

### Check Bot Status
```python
status = bot.get_status()
print(status)
# {
#   "iteration": 12,
#   "portfolio": {...},
#   "trades": 8,
#   "paper_trading": True
# }
```

### View Trade Log
```python
for trade in bot.trade_log:
    print(f"{trade['action']} {trade['shares']}x {trade['ticker']} @ ${trade['price']:.2f}")
```

### View Portfolio Positions
```python
portfolio = bot.portfolio_manager.get_portfolio_status()
for ticker, position in portfolio['positions'].items():
    print(f"{ticker}: {position['shares']} shares @ ${position['entry_price']:.2f}")
```

### Load Previous State
```python
import json

with open("trading_bot_state.json") as f:
    state = json.load(f)

print(f"Previous portfolio value: ${state['portfolio']['cash']:.2f}")
print(f"Total trades: {len(state['trades'])}")
```

## Configuration Examples

### Conservative Strategy (Lower Risk)
```python
AlgoTradingBot(
    portfolio_cash=10000.0,
    selected_analysts=["market", "news", "fundamentals"],  # Skip social
    webull_pin="123456"
)

# Modify exit strategy
bot.exit_strategy.config.profit_target_pct = 3.0  # Take profit at 3%
bot.exit_strategy.config.stop_loss_pct = 1.5     # Stop at 1.5%
bot.exit_strategy.config.max_hold_days = 3       # Hold max 3 days

# Modify portfolio constraints
bot.portfolio_manager.max_position_pct = 0.05    # 5% max per stock
bot.portfolio_manager.max_risky_pct = 0.15       # 15% in risky
bot.portfolio_manager.max_positions = 5          # Only 5 positions
```

### Aggressive Strategy (Higher Risk)
```python
AlgoTradingBot(
    portfolio_cash=10000.0,
    selected_analysts=["market", "social"],  # Include social signals
    webull_pin="123456"
)

# Modify exit strategy
bot.exit_strategy.config.profit_target_pct = 10.0  # Hold for bigger gains
bot.exit_strategy.config.stop_loss_pct = 5.0      # Wider stop
bot.exit_strategy.config.max_hold_days = 10       # Hold longer

# Modify portfolio constraints
bot.portfolio_manager.max_position_pct = 0.12     # 12% max per stock
bot.portfolio_manager.max_risky_pct = 0.40        # 40% in risky
bot.portfolio_manager.max_positions = 15          # More positions
```

## Troubleshooting

### Webull Login Issues
```python
# Check credentials
if not bot.paper_trader.is_authenticated:
    print("Not authenticated with Webull")
    bot._setup_paper_trading(pin="123456")

# Check trade token
try:
    bot.paper_trader.get_trade_token(pin="123456")
except Exception as e:
    print(f"Trade token error: {e}")
```

### Position Not Sizing Correctly
```python
# Debug position calculation
position = bot.portfolio_manager.calculate_position_size(
    current_price=150.0,
    signal_score=75.0,
    position_type="pump"
)

if not position:
    print("Position sizing returned None - check constraints")
    status = bot.portfolio_manager.get_portfolio_status()
    print(f"Cash: ${status['cash']:.2f}")
    print(f"Positions: {status['num_positions']}/{status['max_positions']}")
```

### Order Failing to Execute
```python
# Validate before placing
validation = bot.validator.validate_buy_order(
    ticker="NVDA",
    shares=4,
    price=150.0,
    available_cash=bot.portfolio_manager.cash,
    portfolio_value=bot.portfolio_manager.portfolio_value
)

if not validation['is_valid']:
    print(f"Validation failed: {validation['issues']}")
```

## Next Steps

1. **Test in Demo Mode**: Run `algo_trading_workflow.py` to see how it works
2. **Set Up Webull Account**: Create paper trading account at webull.com
3. **Configure Strategy**: Customize portfolio limits and exit rules
4. **Start Paper Trading**: Connect Webull credentials and run
5. **Monitor Closely**: Check daily results and adjust rules
6. **Scale to Live**: Only after consistent profitability in paper trading

## Files Reference

| File | Purpose |
|------|---------|
| `algo_trading_workflow.py` | Main bot orchestrator |
| `tradingagents/strategy/portfolio_manager.py` | Position sizing & limits |
| `tradingagents/strategy/exit_strategy.py` | Profit/loss management |
| `tradingagents/strategy/trade_validator.py` | Pre-flight checks |
| `tradingagents/agents/trader/paper_trading.py` | Webull integration |

---

**Remember:** Paper trading is a great learning tool, but it's not perfect. Real trading has slippage, spreads, and execution delays. Start small, monitor closely, and only trade with money you can afford to lose.

Good luck! 🚀
