# 🚀 ALGO TRADING SYSTEM - START HERE

## What You Have

A **complete, production-ready algorithmic trading system** with:
- ✅ Automatic stock screening
- ✅ Pump signal detection (pre-pump opportunities)
- ✅ Intelligent position sizing
- ✅ Automatic profit-taking and stop losses
- ✅ Portfolio risk management (8% per stock, 25% risky max)
- ✅ Webull paper trading integration
- ✅ Full audit trail and reporting

## Right Now: Run the Demo (2 minutes)

No setup required. See it in action:

```bash
python algo_trading_demo.py
```

This shows:
1. **Position Sizing** - How much to buy based on signal strength
2. **Exit Strategy** - When to sell (profit target, stop loss, time limit)
3. **Trade Validation** - Safety checks before each trade
4. **Paper Trading** - How to connect to Webull
5. **Complete Flow** - Real trading scenario: buy → monitor → sell

## The Guardrails (Your Safety Net)

| Rule | Limit | Why |
|------|-------|-----|
| **Max per stock** | 8% | Don't bet too much on one stock |
| **Max risky trades** | 25% | Don't exceed your risk appetite |
| **Profit target** | +5% | Take gains at 5% |
| **Stop loss** | -2% | Cut losses quickly at 2% |
| **Max hold time** | 5 days | Don't hold too long |
| **Trailing stop** | 2% from peak | Exit if momentum reverses |

## The Flow (What Happens Automatically)

```
┌─────────────────────────────────────────┐
│ MINUTE 0: New trading signal arrives    │
│ Pump score: 82/100 for NVDA             │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ Calculate position size                 │
│ 8% × 82% = 6.5% of portfolio            │
│ → Buy 4 shares @ $150 = $600            │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ Validate order                          │
│ • Enough cash? YES                      │
│ • Within 8% rule? YES                   │
│ • Valid price? YES                      │
│ → EXECUTE BUY                           │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ MINUTE 30: Monitor position             │
│ Price moved from $150 → $158            │
│ Profit: +5.3% ✓ HIT PROFIT TARGET      │
│ → EXECUTE SELL                          │
│ Profit: $32                             │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ Portfolio restored, ready for next trade│
└─────────────────────────────────────────┘
```

## Quick 3-Step Setup

### Step 1: Test Locally (Now)
```bash
python algo_trading_demo.py
```
Runs immediately, no setup needed.

### Step 2: Create Webull Account (This Week)
1. Go to webull.com
2. Create account
3. Enable "Paper Trading" in settings
4. Get your Trading PIN (6 digits)

### Step 3: Run Paper Trading (This Week)
```python
from algo_trading_workflow import AlgoTradingBot

bot = AlgoTradingBot(
    portfolio_cash=10000.0,
    paper_trading=True,
    webull_email="your_email@example.com",
    webull_password="your_password",
    webull_pin="123456"
)

# Run continuously
bot.run(iterations=-1, interval_seconds=300)  # Every 5 min
```

## How It Works: Real Example

**Scenario:** Screening detects NVDA pump opportunity

| Step | Action | Details |
|------|--------|---------|
| 1️⃣ | **Signal** | NVDA pump score: 82/100 |
| 2️⃣ | **Size** | Position = 8% × 82% = 6.5% → 4 shares |
| 3️⃣ | **Check** | Validate: funds ✓, limits ✓, price ✓ |
| 4️⃣ | **Buy** | 4 shares @ $150 = $600 |
| 5️⃣ | **Wait** | Monitor for exit signals... |
| 6️⃣ | **Monitor** | Price: $150→$155→$158 (P/L: +5.3%) |
| 7️⃣ | **Exit** | Profit target hit! → Sell at $158 |
| 8️⃣ | **Result** | Profit: $32 (5.3%) 🎯 |
| 9️⃣ | **Repeat** | Ready for next signal |

## The Documents

| Doc | Purpose | Read Time |
|-----|---------|-----------|
| `START_HERE.md` | ← You are here | 5 min |
| `ALGO_TRADING_QUICKSTART.md` | Quick reference | 10 min |
| `ALGO_TRADING_SUMMARY.txt` | Implementation details | 15 min |
| `ALGO_TRADING_GUIDE.md` | Complete technical guide | 30 min |

## Customization Examples

### Conservative (Lower Risk)
```python
bot.exit_strategy.config.profit_target_pct = 3.0    # Take at 3%
bot.exit_strategy.config.stop_loss_pct = 1.5        # Stop at 1.5%
bot.exit_strategy.config.max_hold_days = 3          # Hold 3 days

bot.portfolio_manager.max_position_pct = 0.05       # 5% per stock
bot.portfolio_manager.max_risky_pct = 0.15          # 15% risky
bot.portfolio_manager.max_positions = 5             # 5 max positions
```

### Aggressive (Higher Risk)
```python
bot.exit_strategy.config.profit_target_pct = 10.0   # Hold for 10%
bot.exit_strategy.config.stop_loss_pct = 5.0        # Stop at 5%
bot.exit_strategy.config.max_hold_days = 10         # Hold 10 days

bot.portfolio_manager.max_position_pct = 0.12       # 12% per stock
bot.portfolio_manager.max_risky_pct = 0.40          # 40% risky
bot.portfolio_manager.max_positions = 15            # 15 max positions
```

## What's Inside (Technical)

```
tradingagents/
├── strategy/
│   ├── portfolio_manager.py      ← Position sizing logic
│   ├── exit_strategy.py          ← Profit/loss triggers
│   └── trade_validator.py        ← Order safety checks
└── agents/trader/
    └── paper_trading.py          ← Webull connection

Root:
├── algo_trading_workflow.py      ← Main bot (use this!)
├── algo_trading_demo.py          ← Start with this!
├── requirements.txt              ← Added webull
└── [Docs]
```

## Common Questions

**Q: Is this ready to use right now?**
A: YES! Run `python algo_trading_demo.py` to see it work immediately.

**Q: Do I need real money?**
A: NO! Use Webull's paper trading (simulated money). Learn first, trade real money later.

**Q: How much money to start?**
A: Paper trading is free. Real trading: start with $500-$1000, never risk more.

**Q: Can I change the guardrails?**
A: YES! Every setting is customizable (position size, exits, limits).

**Q: What if I want to try different strategies?**
A: Just change the parameters and run again. No code changes needed.

**Q: How often does it trade?**
A: Every 5 minutes (customizable). With 8% max per stock, ~5-10 positions per 5-min cycle.

**Q: How long to see results?**
A: Paper trading: 20-30 trades to validate strategy (1-2 weeks)
   Real trading: only after proving profitable on paper

## Risk Warning ⚠️

- **Paper trading is NOT real trading** - There's slippage, spreads, and execution delays in real trading
- **Start small** - Use $500-$1000 in paper first, then real
- **Monitor closely** - Watch your first 10-20 trades
- **Never go all-in** - Keep 25% cash reserve minimum
- **Algo trading is risky** - Only risk money you can afford to lose

## Your Next 3 Actions

1. ✅ **Right now** (2 min): `python algo_trading_demo.py`
2. ✅ **Today** (15 min): Read `ALGO_TRADING_QUICKSTART.md`
3. ✅ **This week** (1 hr): Set up Webull and run first paper trade

---

## Questions?

- **How to use**: See `ALGO_TRADING_QUICKSTART.md`
- **Technical details**: Read `ALGO_TRADING_GUIDE.md`
- **Implementation notes**: Check `ALGO_TRADING_SUMMARY.txt`
- **Code examples**: Run `python algo_trading_demo.py`

---

## You're All Set! 🎯

Your complete algo trading system is ready. The guardrails are built in. The paper trading integration is ready. 

**Next step:** Run the demo!

```bash
python algo_trading_demo.py
```

Good luck with your trading! 🚀

---

*Built with intelligent position sizing, multi-condition exits, and comprehensive risk management.*
