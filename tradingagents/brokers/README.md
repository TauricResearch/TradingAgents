# TradingAgents Broker Integrations

Connect TradingAgents to real trading platforms for paper and live trading.

## 🎯 Why Use Broker Integrations?

- **Paper Trading**: Practice strategies with real market data, zero risk
- **Live Trading**: Execute real trades when your strategy is ready
- **Automation**: Let TradingAgents manage your portfolio 24/7
- **Multi-Platform**: Support for multiple brokers and platforms

## 📋 Supported Brokers

### Alpaca (Recommended for Beginners)

✅ **FREE paper trading**
✅ Easy API setup
✅ Real market data
✅ No minimum deposit
✅ Great documentation

**Perfect for**: Testing strategies, learning to trade, development

### Interactive Brokers (Coming Soon)

- Professional platform
- Low commissions
- Global markets access
- Advanced order types

**Perfect for**: Experienced traders, international markets

## 🚀 Quick Start: Alpaca Paper Trading

### 1. Sign Up (FREE!)

Visit [alpaca.markets](https://alpaca.markets) and create an account.

### 2. Get API Keys

1. Log in to your Alpaca dashboard
2. Navigate to "Paper Trading" section
3. Generate API keys (Key ID and Secret Key)

### 3. Configure Environment

Add to your `.env` file:

```bash
# Alpaca Paper Trading (FREE!)
ALPACA_API_KEY=your_key_id_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_PAPER_TRADING=true
```

### 4. Run Example

```bash
python examples/paper_trading_alpaca.py
```

## 💡 Usage Examples

### Basic Trading

```python
from tradingagents.brokers import AlpacaBroker
from tradingagents.brokers.base import BrokerOrder, OrderSide, OrderType
from decimal import Decimal

# Connect to paper trading
broker = AlpacaBroker(paper_trading=True)
broker.connect()

# Check account
account = broker.get_account()
print(f"Buying Power: ${account.buying_power}")

# Buy 10 shares of AAPL
order = BrokerOrder(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=Decimal("10"),
    order_type=OrderType.MARKET
)

executed = broker.submit_order(order)
print(f"Order ID: {executed.order_id}")

# Check positions
positions = broker.get_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.quantity} shares, P&L: ${pos.unrealized_pnl}")
```

### TradingAgents Integration

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.brokers import AlpacaBroker

# Initialize TradingAgents
ta = TradingAgentsGraph()

# Connect to broker
broker = AlpacaBroker(paper_trading=True)
broker.connect()

# Analyze stock
final_state, signal = ta.propagate("NVDA", "2024-05-10")

# Execute signal
if signal == "BUY":
    order = broker.buy_market("NVDA", Decimal("5"))
    print(f"Bought NVDA: {order.order_id}")
elif signal == "SELL":
    position = broker.get_position("NVDA")
    if position:
        order = broker.sell_market("NVDA", position.quantity)
        print(f"Sold NVDA: {order.order_id}")
```

### Advanced Order Types

```python
from decimal import Decimal

# Limit Order (buy at specific price)
order = broker.buy_limit(
    symbol="TSLA",
    quantity=Decimal("5"),
    limit_price=Decimal("250.00")
)

# Stop Loss (sell if price drops)
from tradingagents.brokers.base import BrokerOrder, OrderSide, OrderType

stop_loss = BrokerOrder(
    symbol="TSLA",
    side=OrderSide.SELL,
    quantity=Decimal("5"),
    order_type=OrderType.STOP,
    stop_price=Decimal("240.00")
)
broker.submit_order(stop_loss)

# Take Profit (sell at target)
take_profit = BrokerOrder(
    symbol="TSLA",
    side=OrderSide.SELL,
    quantity=Decimal("5"),
    order_type=OrderType.LIMIT,
    limit_price=Decimal("275.00")
)
broker.submit_order(take_profit)
```

## 🏗️ Architecture

### BaseBroker Interface

All broker implementations inherit from `BaseBroker` and provide:

**Account Management:**
- `get_account()` - Account info and buying power
- `get_positions()` - All current positions
- `get_position(symbol)` - Specific position

**Order Management:**
- `submit_order(order)` - Place an order
- `cancel_order(order_id)` - Cancel pending order
- `get_order(order_id)` - Check order status
- `get_orders(status, limit)` - List orders

**Market Data:**
- `get_current_price(symbol)` - Latest price

**Convenience Methods:**
- `buy_market(symbol, quantity)` - Quick market buy
- `sell_market(symbol, quantity)` - Quick market sell
- `buy_limit(symbol, quantity, price)` - Quick limit buy
- `sell_limit(symbol, quantity, price)` - Quick limit sell

### Data Models

**BrokerOrder:**
```python
@dataclass
class BrokerOrder:
    symbol: str
    side: OrderSide  # BUY or SELL
    quantity: Decimal
    order_type: OrderType  # MARKET, LIMIT, STOP, STOP_LIMIT
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: str = "day"  # day, gtc, ioc, fok
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
```

**BrokerPosition:**
```python
@dataclass
class BrokerPosition:
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal
    cost_basis: Decimal
```

**BrokerAccount:**
```python
@dataclass
class BrokerAccount:
    account_number: str
    cash: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    equity: Decimal
    currency: str = "USD"
    pattern_day_trader: bool = False
```

## 🔒 Security Best Practices

1. **Never commit API keys** - Use `.env` file (already in `.gitignore`)
2. **Use paper trading first** - Test thoroughly before live trading
3. **Set position limits** - Protect against runaway algorithms
4. **Monitor continuously** - Check logs and positions regularly
5. **Start small** - Begin with minimal capital

## 🐛 Troubleshooting

### Connection Errors

**Problem:** `ConnectionError: Invalid API credentials`

**Solution:**
1. Check API keys are correct in `.env`
2. Ensure no extra spaces in keys
3. Verify you're using paper trading keys for paper mode
4. Regenerate keys if needed

### Order Failures

**Problem:** `InsufficientFundsError`

**Solution:**
1. Check buying power: `account.buying_power`
2. Paper accounts start with $100,000 (default)
3. Reduce order quantity

**Problem:** `OrderError: Order rejected`

**Solution:**
1. Check market is open (9:30 AM - 4:00 PM ET, weekdays)
2. Verify ticker symbol is valid
3. Check order parameters (price, quantity)

### Market Hours

Stock markets are closed:
- Weekends
- US holidays
- Before 9:30 AM ET
- After 4:00 PM ET

Use `time_in_force="gtc"` (good-til-canceled) for orders outside hours.

## 📊 Complete Example

See `examples/tradingagents_with_alpaca.py` for a full integration example showing:

1. TradingAgents analysis
2. Signal generation
3. Order execution
4. Position tracking
5. Performance monitoring

## 🎓 Next Steps

1. **Learn the API**: Run `examples/paper_trading_alpaca.py`
2. **Test Strategies**: Use paper trading to validate
3. **Monitor Performance**: Track P&L and metrics
4. **Refine Approach**: Iterate based on results
5. **Go Live**: When confident, switch to live trading

## 📚 Resources

- [Alpaca API Docs](https://alpaca.markets/docs/)
- [TradingAgents Portfolio System](../portfolio/README.md)
- [Backtesting Framework](../backtest/README.md)

## ⚠️ Disclaimer

Trading involves risk. Paper trading results do not guarantee live trading success. Always:

- Start with small positions
- Use stop losses
- Diversify holdings
- Never invest more than you can afford to lose
- Understand the risks before trading

This software is for educational purposes. Not financial advice.
