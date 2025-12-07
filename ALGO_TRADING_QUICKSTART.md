# Algo Trading - Quick Start

## What You Built

A complete algorithmic trading system that:
- ✅ **Screens** for stock candidates
- ✅ **Detects** pump signals before they happen
- ✅ **Sizes positions** smartly (8% per stock max)
- ✅ **Manages exits** with profit targets, stop losses, time limits
- ✅ **Trades automatically** with Webull paper trading
- ✅ **Protects portfolio** with guardrails (25% risky max)

## Portfolio Guardrails (Already Built In)

| Guardrail | Limit | Protection |
|-----------|-------|-----------|
| **Max per stock** | 8% | Doesn't bet too much on one stock |
| **Max risky trades** | 25% | Doesn't exceed comfort zone |
| **Max positions** | 10 | Manageable portfolio |
| **Min per trade** | $100 | Only meaningful trades |
| **Max per trade** | $2000 | Reasonable position sizing |

## Exit Strategies (Already Built In)

When to automatically SELL:

1. **Profit Target**: +5% → EXIT
2. **Stop Loss**: -2% → EXIT  
3. **Time Limit**: 5 days → EXIT
4. **Trailing Stop**: 2% from peak → EXIT
5. **Signal Deterioration**: Signal drops below 40 → EXIT

## Quick Start (3 minutes)

### Step 1: Run the Demo (No Setup Needed)
```bash
cd /home/gnara/TradingAgents
python algo_trading_demo.py
```

This demonstrates:
- Position sizing (8% rule in action)
- Exit strategies (profit targets, stops)
- Trade validation
- Complete flow

### Step 2: Set Up Webull (Paper Trading)

1. Go to https://webull.com
2. Create account
3. In settings: Enable **Paper Trading**
4. Get your **Trading PIN** (usually 6 digits)

### Step 3: Configure for Webull

Create `.env` file in project root:
```
WEBULL_EMAIL=your_email@example.com
WEBULL_PASSWORD=your_password
WEBULL_PIN=123456
```

Or set environment variables:
```bash
export WEBULL_EMAIL="your_email@example.com"
export WEBULL_PASSWORD="your_password"
export WEBULL_PIN="123456"
```

### Step 4: Run Real Trading

Option A - In Python script:
```python
from algo_trading_workflow import AlgoTradingBot
import os

bot = AlgoTradingBot(
    portfolio_cash=10000.0,
    paper_trading=True,
    selected_analysts=["market", "social"],
    webull_email=os.getenv("WEBULL_EMAIL"),
    webull_password=os.getenv("WEBULL_PASSWORD"),
    webull_pin=os.getenv("WEBULL_PIN"),
)

# Run 10 iterations (50 minutes with 5-min intervals)
bot.run(iterations=10, interval_seconds=300)

bot.print_summary()
```

Option B - Command line (after setting env vars):
```python
# Edit bottom of algo_trading_workflow.py to use env vars
python algo_trading_workflow.py
```

## How It Works (Example)

```
MINUTE 0: Market opens
  → Screening agent finds NVDA is trending
  → Pump detection: score 82/100
  → Buy signal (>70) ✓
  → Position size: 8% * 82% = 6.5% of portfolio
  → Enter: 4 shares @ $150 = $600

MINUTE 5-25: Monitor position
  → Current price: $155 (+3.3%)
  → Still holding (no exit signal yet)

MINUTE 30: Price jumps to $158
  → P/L: +5.3% ✓ HIT PROFIT TARGET
  → EXIT: Sell 4 shares @ $158
  → Profit: $32 (5.3%)
  → Cash restored to portfolio

MINUTE 35: Ready for next trade
  → Repeat for next signal
```

## Customization Examples

### Conservative (Lower Risk)
```python
bot = AlgoTradingBot(portfolio_cash=10000)

# Tighter exits
bot.exit_strategy.config.profit_target_pct = 3.0   # Take profit at 3%
bot.exit_strategy.config.stop_loss_pct = 1.5       # Stop at 1.5%
bot.exit_strategy.config.max_hold_days = 3         # Hold max 3 days

# Smaller positions
bot.portfolio_manager.max_position_pct = 0.05      # 5% per stock
bot.portfolio_manager.max_risky_pct = 0.15         # 15% risky
bot.portfolio_manager.max_positions = 5            # Max 5 positions
```

### Aggressive (Higher Risk)
```python
bot = AlgoTradingBot(portfolio_cash=10000)

# Wider exits (hold for bigger gains)
bot.exit_strategy.config.profit_target_pct = 10.0  # Hold for 10%
bot.exit_strategy.config.stop_loss_pct = 5.0       # Stop at 5%
bot.exit_strategy.config.max_hold_days = 10        # Hold 10 days

# Larger positions
bot.portfolio_manager.max_position_pct = 0.12      # 12% per stock
bot.portfolio_manager.max_risky_pct = 0.40         # 40% risky
bot.portfolio_manager.max_positions = 15           # Max 15 positions
```

## Monitoring Your Trades

### Check Status
```python
status = bot.get_status()
print(f"Iteration: {status['iteration']}")
print(f"Portfolio: ${status['portfolio']['total_value']:.2f}")
print(f"Positions: {status['portfolio']['num_positions']}")
```

### View Trades
```python
for trade in bot.trade_log:
    if trade['action'] == 'BUY':
        print(f"BUY {trade['shares']}x {trade['ticker']} @ ${trade['price']:.2f}")
    else:
        print(f"SELL {trade['shares']}x {trade['ticker']} @ ${trade['price']:.2f} "
              f"(P/L: ${trade['profit']:.2f})")
```

### Print Summary
```python
bot.print_summary()
# Shows total portfolio value, P/L, number of trades, etc.
```

### Save State
```python
bot.save_state("my_trading_results.json")
# Load later to resume or analyze
```

## Core Files

| File | Purpose |
|------|---------|
| `algo_trading_demo.py` | ← **START HERE** - Run this first |
| `algo_trading_workflow.py` | Main bot orchestrator |
| `tradingagents/strategy/portfolio_manager.py` | Position sizing & limits |
| `tradingagents/strategy/exit_strategy.py` | Profit/loss management |
| `tradingagents/strategy/trade_validator.py` | Pre-flight validation |
| `tradingagents/agents/trader/paper_trading.py` | Webull integration |
| `ALGO_TRADING_GUIDE.md` | Full detailed documentation |

## Common Issues

**Q: Bot places too many trades**
- Lower profit target: `exit_strategy.config.profit_target_pct = 3.0`
- Increase hold time: `exit_strategy.config.max_hold_days = 7`

**Q: Positions too small**
- Increase max position: `portfolio_manager.max_position_pct = 0.12`
- Lower min position: `portfolio_manager.min_position_size = 50.0`

**Q: Too risky**
- Lower max risky: `portfolio_manager.max_risky_pct = 0.15`
- Tighter stop loss: `exit_strategy.config.stop_loss_pct = 1.0`

**Q: Webull login fails**
1. Check email/password in .env
2. Check Trading PIN is correct
3. Check 2FA is enabled on account
4. Try logging in to webull.com manually first

## Safety Tips

1. **Always test in demo mode first** - Run `algo_trading_demo.py` to verify logic
2. **Start with small capital** - Use $500-$1000 first, not $10,000
3. **Monitor first trades** - Watch your first 5-10 trades closely
4. **Adjust based on results** - If win rate is <50%, tighten stops
5. **Never go all-in** - Always keep reserve cash (25% minimum)
6. **Use paper trading first** - Don't use real money until you're profitable

## Next Steps

1. ✅ Run `algo_trading_demo.py` - See how it works
2. ✅ Read `ALGO_TRADING_GUIDE.md` - Full technical details
3. ✅ Set up Webull account - Get paper trading ready
4. ✅ Configure bot - Customize strategy for your risk appetite
5. ✅ Test with small capital - $500-$1000 in paper trading
6. ✅ Monitor daily - Track results, adjust rules
7. ✅ Scale up - Only after consistent profits

## Questions?

Check `ALGO_TRADING_GUIDE.md` for:
- Detailed architecture diagrams
- All configuration options
- Code examples
- Troubleshooting guide

---

**Remember:** Algo trading is powerful but risky. Paper trading lets you learn safely. Start small, monitor closely, and only scale after proven results.

Good luck! 🚀
