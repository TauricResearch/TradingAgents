# NIFTY 50 Live Options Trader Setup Guide

## Overview

The `nifty50_trader.py` script is a **live trading bot** that:
- Fetches real-time market data from your broker
- Calculates technical indicators (RSI, ATR, support/resistance)
- Analyzes CALL and PUT entry signals
- Automatically executes options trades
- Monitors active positions

## Quick Start (Mock Broker)

Test without real money:

```bash
python nifty50_trader.py --broker mock
```

**Output:**
- Fetches simulated NIFTY50 data
- Generates trading signals
- Shows entry/stop/target levels
- Demonstrates trade execution flow

## Setup with Zerodha (Live Trading)

### 1. Install Dependencies

```bash
pip install kiteconnect
```

### 2. Get Zerodha API Credentials

1. Go to [Zerodha Kite](https://kite.zerodha.com/)
2. Log in with your account
3. Create an API app:
   - Visit [Kite Console](https://kite.zerodha.com/)
   - Create new app (get API Key)
   - Generate access token from login flow

### 3. Set Environment Variables

```bash
# Linux/Mac
export BROKER_API_KEY="your_api_key"
export BROKER_ACCESS_TOKEN="your_access_token"

# Windows
set BROKER_API_KEY=your_api_key
set BROKER_ACCESS_TOKEN=your_access_token
```

Or pass directly:

```bash
python nifty50_trader.py \
  --broker zerodha \
  --api-key "your_api_key" \
  --access-token "your_access_token"
```

### 4. Run Live Trader

```bash
python nifty50_trader.py --broker zerodha
```

## How It Works

### 1. Fetch Market Data
```python
[DATA] NIFTY50 - 2026-09-01T01:39:51.094267
       Price: 24,087.65 (Bid: 24086.00, Ask: 24089.00)
```
Gets real-time bid/ask/high/low/volume from broker.

### 2. Calculate Technicals
```python
[TECH] RSI: 42.0
       ATR: 150.00
       Support: 24,000.00
       Resistance: 24,500.00
       Volume: increasing
```
Analyzes momentum, volatility, and key levels.

### 3. Generate Signals
```python
[CALL] Confidence: 70.0%
       Entry: 24,075.00
       Stop: 23,850.00
       Target: 24,500.00

[PUT] Confidence: 30.0%
      (too weak)
```
Uses entry points module to identify opportunities.

### 4. Execute Trade (if >75% confidence)
```python
[ORDER] BUY CALL
        Entry: 24,075.00
        Stop: 23,850.00
        Target: 24,500.00
        Quantity: 1 lot

[OK] Trade executed: 123456789
```
Places live order through broker API.

### 5. Monitor Positions
```python
[123456789] CALL BUY
           Entry: 24,075.00
           Stop: 23,850.00
           Target: 24,500.00
           Status: ACCEPTED
```
Tracks open orders and P&L.

## Command Line Options

```bash
python nifty50_trader.py [OPTIONS]

Options:
  --broker {mock,zerodha}     Broker to use (default: mock)
  --api-key KEY               Broker API key
  --access-token TOKEN        Broker access token
  --help                      Show this help
```

## Configuration

### Modify Trade Parameters

Edit `nifty50_trader.py`:

```python
class NIFTY50Trader:
    def execute_trade(self, ...):
        quantity = 1  # Change from 1 to other values
        
        # Modify confidence threshold
        # Currently 75% - change to suit your strategy
```

### Adjust Signal Thresholds

In `run_once()`:

```python
if option_type:
    # Change from 75 to another value
    # Higher = fewer trades but higher quality
    # Lower = more trades but higher risk
```

## Real-World Workflow

### Morning Setup
```bash
# 1. Start the trader
python nifty50_trader.py --broker zerodha

# 2. Monitor console output for signals
# 3. Verify signals before auto-execution
# 4. Keep eye on open positions
```

### During Trading
```bash
# Check active positions
# Monitor P&L (profit/loss)
# Set alerts for target/stop levels
# Adjust position size based on account
```

### Close of Day
```bash
# Review trade log
# Calculate daily P&L
# Prepare for next day
```

## Important: Risk Management

### Position Sizing

Current: 1 lot per trade

**Recommended calculation:**
```
Position Size = (Account Size × Risk%) / (Entry - Stop)

Example:
  Account: Rs. 100,000
  Risk: 2% = Rs. 2,000
  Entry: 24,075
  Stop: 23,850
  Points at risk: 225
  
  Position = 2,000 / 225 = 8.9 lots
```

### Stop Losses

**ALWAYS SET STOP LOSS**
- Current: ATR-based calculation
- Never trade without one
- Market gaps can blow through stops

### Target Profits

**Know your target before entering**
- Current: Support/resistance based
- 1.5x to 2x risk is ideal
- Take profits in tranches

## Troubleshooting

### "Authentication failed"
- Check API key is correct
- Verify access token is valid
- Ensure token hasn't expired
- Check network connection

### "Failed to fetch market data"
- Symbol might be wrong
- Market might be closed
- Token might have expired
- Zerodha server issue

### "Failed to place order"
- Insufficient margin
- Market order outside trading hours
- Position limit reached
- Order parameters invalid

### "No clear signal (need >75%)"
- Market is indecisive
- Wait for clearer setup
- Reduce confidence threshold temporarily
- Check chart manually

## Integration with TradingAgents

The trader uses `tradingagents` modules:

```python
from tradingagents.strategies import find_call_entry_points, find_put_entry_points
from tradingagents.brokers import get_broker, Order
```

Can integrate into your main trading system:

```python
# In your agent
trader = NIFTY50Trader(broker_type="zerodha")
trader.authenticate(credentials)
trader.run_once()  # Single cycle
```

## Advanced: Custom Strategies

### Extend for Multiple Symbols

```python
class MultiSymbolTrader(NIFTY50Trader):
    def __init__(self, symbols: list):
        super().__init__()
        self.symbols = symbols
    
    def run_all_symbols(self):
        for symbol in self.symbols:
            self.symbol = symbol
            self.run_once()
```

### Add Risk Management

```python
def check_daily_limit(self):
    """Don't trade after losing X% today."""
    daily_loss = sum(t['pnl'] for t in self.trade_log if t['status'] == 'CLOSED')
    if daily_loss < -500:  # Stop after -500 rupees loss
        return False
    return True
```

### Scheduled Execution

Use `schedule` library:

```bash
pip install schedule
```

```python
import schedule
import time

schedule.every().day.at("09:15").do(trader.run_once)
while True:
    schedule.run_pending()
    time.sleep(60)
```

## Safety Reminders

1. **Paper Trade First**
   - Start with mock broker
   - Verify signals manually
   - Build confidence

2. **Small Position Sizes**
   - Start with 1 lot
   - Increase gradually
   - Never go all-in

3. **Monitor Actively**
   - Don't automate completely
   - Review trades daily
   - Adjust as needed

4. **Know Your Broker**
   - Read margin requirements
   - Understand fees
   - Know circuit breakers

5. **Have an Exit Plan**
   - Set stops BEFORE entering
   - Know your target
   - Don't hold till expiry

## Support for Other Brokers

Currently supports: **Zerodha, Mock**

To add your broker:

1. Subclass `BrokerAPI`
2. Implement required methods
3. Add to `get_broker()` factory

```python
class MyBroker(BrokerAPI):
    def authenticate(self, credentials):
        # Your auth logic
        pass
    
    def get_market_data(self, symbol):
        # Fetch from your broker
        pass
    
    # ... other methods
```

## File Structure

```
nifty50_trader.py          Main trading bot
tradingagents/
├── strategies/
│   ├── entry_points.py    Signal generation
│   └── examples.py        Usage examples
└── brokers/
    └── __init__.py        Broker integrations
```

## Performance Monitoring

Track your results:

```python
# In trade_log
{
    "timestamp": "2026-09-01T09:30:00",
    "order_id": "123456",
    "type": "CALL",
    "action": "BUY",
    "entry": 24075.00,
    "stop": 23850.00,
    "target": 24500.00,
    "status": "FILLED",
    "pnl": 425.00,  # Add this
    "pnl_percent": 1.76,
}
```

## Next Steps

1. **Test with mock broker**
   ```bash
   python nifty50_trader.py --broker mock
   ```

2. **Set up Zerodha credentials**
   - Get API key
   - Generate access token

3. **Start paper trading**
   - Run live trader
   - Verify signals manually
   - Monitor positions

4. **Optimize strategy**
   - Adjust confidence threshold
   - Modify position sizing
   - Test different signals

---

**Remember**: This is a tool for analysis and education. Always trade responsibly and within your risk tolerance.
