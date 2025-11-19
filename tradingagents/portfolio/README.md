# Portfolio Management System

A comprehensive, production-ready portfolio management system for the TradingAgents framework.

## Overview

This module provides complete portfolio management capabilities including position tracking, order execution, risk management, performance analytics, and seamless integration with the TradingAgents multi-agent framework.

## Features

### Core Portfolio Management
- **Position Tracking**: Track long and short positions with cost basis, P&L, and market value
- **Cash Management**: Automatic cash balance management with commission handling
- **Order Execution**: Support for multiple order types (market, limit, stop-loss, take-profit)
- **Trade History**: Complete audit trail of all executed trades
- **Thread-Safe**: Concurrent operations supported with proper locking

### Risk Management
- **Position Size Limits**: Configurable maximum position size as % of portfolio
- **Sector Concentration**: Limit exposure to specific sectors
- **Drawdown Monitoring**: Track and limit maximum drawdown
- **Cash Reserve Requirements**: Maintain minimum cash reserves
- **VaR Calculation**: Value at Risk calculation using historical simulation
- **Position Sizing**: Calculate optimal position sizes based on risk parameters

### Performance Analytics
- **Returns Calculation**: Daily, cumulative, and annualized returns
- **Risk Metrics**: Sharpe ratio, Sortino ratio, maximum drawdown
- **Trade Statistics**: Win rate, profit factor, average win/loss
- **Equity Curve**: Track portfolio value over time
- **Monthly Returns**: Breakdown of returns by month
- **Rolling Metrics**: Rolling Sharpe ratio and other time-series metrics

### Persistence
- **JSON Export/Import**: Save and load portfolio state
- **SQLite Database**: Advanced persistence with historical tracking
- **CSV Export**: Export trade history to CSV
- **Snapshot Management**: Create and manage portfolio snapshots

### TradingAgents Integration
- **Decision Execution**: Execute trading decisions from agents
- **Portfolio Context**: Provide portfolio state to agents for decision-making
- **Batch Operations**: Execute multiple trades efficiently
- **Rebalancing**: Automated portfolio rebalancing to target weights

## Installation

The portfolio module is part of the TradingAgents package:

```bash
cd /home/user/TradingAgents
pip install -e .
```

## Quick Start

### Basic Usage

```python
from tradingagents.portfolio import Portfolio, MarketOrder
from decimal import Decimal

# Create a portfolio
portfolio = Portfolio(
    initial_capital=Decimal('100000.00'),
    commission_rate=Decimal('0.001')  # 0.1% commission
)

# Execute a buy order
buy_order = MarketOrder('AAPL', Decimal('100'))
portfolio.execute_order(buy_order, current_price=Decimal('150.00'))

# Check portfolio value
current_prices = {'AAPL': Decimal('155.00')}
total_value = portfolio.total_value(current_prices)
print(f"Portfolio Value: ${total_value:,.2f}")

# Execute a sell order
sell_order = MarketOrder('AAPL', Decimal('-100'))
portfolio.execute_order(sell_order, current_price=Decimal('160.00'))

# Get performance metrics
metrics = portfolio.get_performance_metrics()
print(f"Total Return: {metrics.total_return:.2%}")
print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
print(f"Win Rate: {metrics.win_rate:.2%}")
```

### Using Different Order Types

```python
from tradingagents.portfolio import LimitOrder, StopLossOrder, TakeProfitOrder

# Limit order - only execute at specified price or better
limit_order = LimitOrder(
    ticker='GOOGL',
    quantity=Decimal('50'),
    limit_price=Decimal('2000.00')
)

# Stop-loss order - close position if price drops
stop_order = StopLossOrder(
    ticker='AAPL',
    quantity=Decimal('-100'),
    stop_price=Decimal('145.00')
)

# Take-profit order - close position at profit target
take_profit = TakeProfitOrder(
    ticker='AAPL',
    quantity=Decimal('-100'),
    target_price=Decimal('160.00')
)
```

### Risk Management

```python
from tradingagents.portfolio import Portfolio, RiskLimits

# Create portfolio with custom risk limits
risk_limits = RiskLimits(
    max_position_size=Decimal('0.15'),      # 15% max per position
    max_sector_concentration=Decimal('0.25'), # 25% max per sector
    max_drawdown=Decimal('0.20'),            # 20% max drawdown
    min_cash_reserve=Decimal('0.10')         # 10% minimum cash
)

portfolio = Portfolio(
    initial_capital=Decimal('100000.00'),
    risk_limits=risk_limits
)

# Risk checks are automatically enforced on all trades
# Will raise RiskLimitExceededError if limits are violated
```

### Performance Analytics

```python
# Get comprehensive performance metrics
metrics = portfolio.get_performance_metrics(
    risk_free_rate=Decimal('0.02')  # 2% annual risk-free rate
)

print(f"Total Return: {metrics.total_return:.2%}")
print(f"Annualized Return: {metrics.annualized_return:.2%}")
print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
print(f"Sortino Ratio: {metrics.sortino_ratio:.2f}")
print(f"Max Drawdown: {metrics.max_drawdown:.2%}")
print(f"Win Rate: {metrics.win_rate:.2%}")
print(f"Profit Factor: {metrics.profit_factor:.2f}")

# Get equity curve
equity_curve = portfolio.get_equity_curve()
for date, value in equity_curve[-5:]:
    print(f"{date}: ${value:,.2f}")
```

### Saving and Loading Portfolio State

```python
# Save portfolio state
portfolio.save('my_portfolio.json')

# Load portfolio state
from tradingagents.portfolio import Portfolio
loaded_portfolio = Portfolio.load('my_portfolio.json')

# Save to SQLite database
from tradingagents.portfolio import PortfolioPersistence
persistence = PortfolioPersistence('./portfolio_data')
portfolio_data = portfolio.to_dict()
persistence.save_to_sqlite(portfolio_data, 'portfolio.db')

# Export trades to CSV
persistence.export_to_csv(
    [trade.to_dict() for trade in portfolio.trade_history],
    'trades.csv'
)
```

### TradingAgents Integration

```python
from tradingagents.portfolio import TradingAgentsPortfolioIntegration

# Create integration layer
integration = TradingAgentsPortfolioIntegration(portfolio)

# Execute agent decision
decision = {
    'action': 'buy',
    'ticker': 'AAPL',
    'quantity': 100,
    'order_type': 'market',
    'reasoning': 'Strong bullish sentiment from analysts'
}

current_prices = {'AAPL': Decimal('150.00')}
result = integration.execute_agent_decision(decision, current_prices)

if result['status'] == 'success':
    print(f"Executed: {result['action']} {result['ticker']}")
else:
    print(f"Failed: {result['error']}")

# Get portfolio context for agents
context = integration.get_portfolio_context(current_prices)
print(f"Total Value: ${context['total_value']}")
print(f"Cash: ${context['cash']}")
print(f"Positions: {len(context['positions'])}")

# Rebalance portfolio
target_weights = {
    'AAPL': Decimal('0.40'),
    'GOOGL': Decimal('0.30'),
    'MSFT': Decimal('0.30')
}
results = integration.rebalance_portfolio(target_weights, current_prices)
```

## Architecture

### Module Structure

```
tradingagents/portfolio/
├── __init__.py           # Public API exports
├── portfolio.py          # Core Portfolio class
├── position.py           # Position tracking
├── orders.py             # Order types and execution
├── risk.py               # Risk management
├── analytics.py          # Performance analytics
├── persistence.py        # State persistence
├── integration.py        # TradingAgents integration
└── exceptions.py         # Custom exceptions
```

### Key Classes

- **Portfolio**: Main portfolio management class
- **Position**: Represents a single security position
- **Order**: Base class for all order types
- **MarketOrder**, **LimitOrder**, **StopLossOrder**, **TakeProfitOrder**: Order implementations
- **RiskManager**: Risk limit enforcement and calculations
- **PerformanceAnalytics**: Performance metric calculations
- **PortfolioPersistence**: Save/load portfolio state
- **TradingAgentsPortfolioIntegration**: Integration with TradingAgents framework

## Security

The portfolio system integrates with TradingAgents security features:

- **Input Validation**: All inputs validated using `tradingagents.security` validators
- **Ticker Validation**: Prevents path traversal and injection attacks
- **Decimal Arithmetic**: Uses Decimal type to avoid floating-point precision issues
- **Path Sanitization**: All file paths sanitized before use
- **Thread Safety**: Proper locking for concurrent operations

## Testing

Comprehensive test suite included:

```bash
# Run all portfolio tests
cd /home/user/TradingAgents
python -m pytest tests/portfolio/ -v

# Run specific test file
python -m pytest tests/portfolio/test_portfolio.py -v

# Run with coverage
python -m pytest tests/portfolio/ --cov=tradingagents.portfolio --cov-report=html
```

## Performance Considerations

- **Efficient Lookups**: Positions stored in dictionary for O(1) access
- **Lazy Calculation**: Metrics calculated on-demand, not stored
- **Thread-Safe**: Uses RLock for concurrent operations
- **Decimal Precision**: Avoids floating-point errors in financial calculations

## Limitations and Future Improvements

### Current Limitations
- No support for options, futures, or other derivatives
- No multi-currency support
- No tax-lot tracking for partial sales
- No margin account support

### Planned Improvements
- Advanced order types (trailing stop, OCO orders)
- Multi-currency support
- Tax-lot accounting
- Margin and leverage support
- Options and derivatives
- Real-time price feed integration
- Webhook notifications for trade events

## API Reference

### Portfolio

```python
class Portfolio:
    def __init__(
        self,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal('0.001'),
        risk_limits: Optional[RiskLimits] = None,
        persist_dir: Optional[str] = None
    )

    def execute_order(self, order: Order, current_price: Decimal, check_risk: bool = True) -> None
    def get_position(self, ticker: str) -> Optional[Position]
    def get_all_positions(self) -> Dict[str, Position]
    def total_value(self, prices: Optional[Dict[str, Decimal]] = None) -> Decimal
    def unrealized_pnl(self, prices: Dict[str, Decimal]) -> Decimal
    def realized_pnl(self) -> Decimal
    def get_performance_metrics(self, risk_free_rate: Decimal = Decimal('0.02')) -> PerformanceMetrics
    def get_equity_curve(self) -> List[Tuple[datetime, Decimal]]
    def save(self, filename: str = 'portfolio_state.json') -> None
    @classmethod
    def load(cls, filename: str = 'portfolio_state.json', persist_dir: Optional[str] = None) -> 'Portfolio'
```

### Position

```python
class Position:
    def __init__(
        self,
        ticker: str,
        quantity: Decimal,
        cost_basis: Decimal,
        sector: Optional[str] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None
    )

    def market_value(self, current_price: Decimal) -> Decimal
    def unrealized_pnl(self, current_price: Decimal) -> Decimal
    def unrealized_pnl_percent(self, current_price: Decimal) -> Decimal
    def should_trigger_stop_loss(self, current_price: Decimal) -> bool
    def should_trigger_take_profit(self, current_price: Decimal) -> bool
```

### Orders

```python
class MarketOrder(Order):
    def __init__(self, ticker: str, quantity: Decimal)

class LimitOrder(Order):
    def __init__(self, ticker: str, quantity: Decimal, limit_price: Decimal)

class StopLossOrder(Order):
    def __init__(self, ticker: str, quantity: Decimal, stop_price: Decimal)

class TakeProfitOrder(Order):
    def __init__(self, ticker: str, quantity: Decimal, target_price: Decimal)
```

## Contributing

When contributing to the portfolio module:

1. Add comprehensive tests for new features
2. Use type hints on all functions
3. Follow Google-style docstrings
4. Validate all inputs using security validators
5. Use Decimal for all monetary calculations
6. Ensure thread-safety for shared state
7. Update this README with new features

## License

This module is part of the TradingAgents framework. See the main LICENSE file for details.

## Support

For issues or questions:
- Check the examples in `/home/user/TradingAgents/examples/portfolio_example.py`
- Review test cases in `/home/user/TradingAgents/tests/portfolio/`
- See main TradingAgents documentation

## Version History

### 1.0.0 (2024-11-14)
- Initial release
- Core portfolio management
- Position tracking
- Order execution (market, limit, stop-loss, take-profit)
- Risk management and limits
- Performance analytics
- Persistence (JSON, SQLite)
- TradingAgents integration
- Comprehensive test suite
