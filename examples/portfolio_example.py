"""
Comprehensive Portfolio Management System Example

This example demonstrates all major features of the TradingAgents
portfolio management system.
"""

from decimal import Decimal
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from tradingagents.portfolio import (
    Portfolio,
    MarketOrder,
    LimitOrder,
    StopLossOrder,
    TakeProfitOrder,
    RiskLimits,
    TradingAgentsPortfolioIntegration,
)


def example_basic_trading():
    """Example 1: Basic Trading Operations"""
    print("\n" + "="*80)
    print("Example 1: Basic Trading Operations")
    print("="*80)

    # Create a portfolio with $100,000 initial capital
    portfolio = Portfolio(
        initial_capital=Decimal('100000.00'),
        commission_rate=Decimal('0.001')  # 0.1% commission
    )

    print(f"Initial Portfolio:")
    print(f"  Cash: ${portfolio.cash:,.2f}")
    print(f"  Total Value: ${portfolio.total_value():,.2f}")

    # Execute a buy order
    print("\n--- Buying 100 shares of AAPL at $150.00 ---")
    buy_order = MarketOrder('AAPL', Decimal('100'))
    portfolio.execute_order(buy_order, current_price=Decimal('150.00'))

    print(f"After Purchase:")
    print(f"  Cash: ${portfolio.cash:,.2f}")
    print(f"  Positions: {list(portfolio.positions.keys())}")

    # Check position details
    aapl_position = portfolio.get_position('AAPL')
    print(f"\nAAPL Position:")
    print(f"  Quantity: {aapl_position.quantity}")
    print(f"  Cost Basis: ${aapl_position.cost_basis}")
    print(f"  Total Cost: ${aapl_position.total_cost():,.2f}")

    # Price goes up
    print("\n--- Price moves to $160.00 ---")
    current_prices = {'AAPL': Decimal('160.00')}
    unrealized_pnl = portfolio.unrealized_pnl(current_prices)
    total_value = portfolio.total_value(current_prices)

    print(f"Unrealized P&L: ${unrealized_pnl:,.2f}")
    print(f"Total Value: ${total_value:,.2f}")
    print(f"Return: {((total_value - portfolio.initial_capital) / portfolio.initial_capital):.2%}")

    # Sell position
    print("\n--- Selling 100 shares of AAPL at $160.00 ---")
    sell_order = MarketOrder('AAPL', Decimal('-100'))
    portfolio.execute_order(sell_order, current_price=Decimal('160.00'))

    realized_pnl = portfolio.realized_pnl()
    print(f"Realized P&L: ${realized_pnl:,.2f}")
    print(f"Final Cash: ${portfolio.cash:,.2f}")
    print(f"Trade History: {len(portfolio.trade_history)} completed trades")

    return portfolio


def example_order_types():
    """Example 2: Different Order Types"""
    print("\n" + "="*80)
    print("Example 2: Different Order Types")
    print("="*80)

    portfolio = Portfolio(
        initial_capital=Decimal('100000.00'),
        commission_rate=Decimal('0.001')
    )

    # Market Order - executes immediately
    print("\n--- Market Order ---")
    market_order = MarketOrder('AAPL', Decimal('100'))
    portfolio.execute_order(market_order, Decimal('150.00'))
    print(f"Executed market order at $150.00")

    # Limit Order - only executes at specified price or better
    print("\n--- Limit Order ---")
    limit_order = LimitOrder('GOOGL', Decimal('50'), limit_price=Decimal('2000.00'))

    # Try at higher price - won't execute
    print(f"Current price $2050.00 - can execute: {limit_order.can_execute(Decimal('2050.00'))}")

    # Try at limit price - will execute
    print(f"Current price $2000.00 - can execute: {limit_order.can_execute(Decimal('2000.00'))}")
    portfolio.execute_order(limit_order, Decimal('2000.00'))

    # Add stop-loss to AAPL position
    print("\n--- Adding Stop-Loss Protection ---")
    aapl_position = portfolio.get_position('AAPL')
    aapl_position.stop_loss = Decimal('145.00')  # 3.3% stop-loss
    aapl_position.take_profit = Decimal('165.00')  # 10% take-profit

    print(f"AAPL Position protected with:")
    print(f"  Stop-Loss: ${aapl_position.stop_loss}")
    print(f"  Take-Profit: ${aapl_position.take_profit}")

    # Check for triggers
    print("\n--- Checking Triggers at $144.00 ---")
    prices = {'AAPL': Decimal('144.00'), 'GOOGL': Decimal('2000.00')}
    stop_loss_orders = portfolio.check_stop_loss_triggers(prices)

    if stop_loss_orders:
        print(f"Stop-loss triggered for {stop_loss_orders[0].ticker}!")
        # In production, you would execute these orders
        # portfolio.execute_order(stop_loss_orders[0], prices['AAPL'])

    return portfolio


def example_risk_management():
    """Example 3: Risk Management"""
    print("\n" + "="*80)
    print("Example 3: Risk Management")
    print("="*80)

    # Create portfolio with strict risk limits
    risk_limits = RiskLimits(
        max_position_size=Decimal('0.15'),        # 15% max per position
        max_sector_concentration=Decimal('0.25'),  # 25% max per sector
        max_drawdown=Decimal('0.20'),             # 20% max drawdown
        min_cash_reserve=Decimal('0.10')          # 10% minimum cash
    )

    portfolio = Portfolio(
        initial_capital=Decimal('100000.00'),
        commission_rate=Decimal('0.001'),
        risk_limits=risk_limits
    )

    print("Risk Limits:")
    print(f"  Max Position Size: {portfolio.risk_manager.limits.max_position_size:.1%}")
    print(f"  Max Sector Concentration: {portfolio.risk_manager.limits.max_sector_concentration:.1%}")
    print(f"  Max Drawdown: {portfolio.risk_manager.limits.max_drawdown:.1%}")
    print(f"  Min Cash Reserve: {portfolio.risk_manager.limits.min_cash_reserve:.1%}")

    # Calculate position size using risk management
    print("\n--- Position Sizing ---")
    entry_price = Decimal('150.00')
    stop_loss_price = Decimal('145.00')
    risk_per_trade = Decimal('0.02')  # 2% risk per trade

    position_size = portfolio.risk_manager.calculate_position_size(
        portfolio.total_value(),
        risk_per_trade,
        entry_price,
        stop_loss_price
    )

    print(f"Entry Price: ${entry_price}")
    print(f"Stop-Loss Price: ${stop_loss_price}")
    print(f"Risk Per Trade: {risk_per_trade:.1%}")
    print(f"Calculated Position Size: {position_size} shares")

    # Execute with calculated size
    order = MarketOrder('AAPL', position_size)
    portfolio.execute_order(order, entry_price)

    position_value = position_size * entry_price
    portfolio_value = portfolio.total_value()
    position_pct = position_value / portfolio_value

    print(f"\nPosition Value: ${position_value:,.2f}")
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"Position Size: {position_pct:.2%} of portfolio")

    # Try to violate position size limit
    print("\n--- Testing Position Size Limit ---")
    try:
        # This would create a position > 15% of portfolio
        oversized_order = MarketOrder('GOOGL', Decimal('100'))
        portfolio.execute_order(oversized_order, Decimal('2000.00'))
    except Exception as e:
        print(f"Order rejected: {e}")

    return portfolio


def example_performance_analytics():
    """Example 4: Performance Analytics"""
    print("\n" + "="*80)
    print("Example 4: Performance Analytics")
    print("="*80)

    portfolio = Portfolio(
        initial_capital=Decimal('100000.00'),
        commission_rate=Decimal('0.001')
    )

    # Simulate a series of trades
    trades = [
        ('AAPL', Decimal('100'), Decimal('150.00'), Decimal('160.00')),
        ('GOOGL', Decimal('50'), Decimal('2000.00'), Decimal('2100.00')),
        ('MSFT', Decimal('200'), Decimal('300.00'), Decimal('295.00')),  # Loss
        ('TSLA', Decimal('75'), Decimal('200.00'), Decimal('220.00')),
    ]

    print("Simulating trades...")
    for ticker, quantity, buy_price, sell_price in trades:
        # Buy
        buy_order = MarketOrder(ticker, quantity)
        portfolio.execute_order(buy_order, buy_price)

        # Sell
        sell_order = MarketOrder(ticker, -quantity)
        portfolio.execute_order(sell_order, sell_price)

        trade = portfolio.trade_history[-1]
        print(f"  {ticker}: {trade.pnl:+,.2f} ({trade.pnl_percent:+.2%})")

    # Get performance metrics
    print("\n--- Performance Metrics ---")
    metrics = portfolio.get_performance_metrics()

    print(f"Total Return: {metrics.total_return:+.2%}")
    print(f"Annualized Return: {metrics.annualized_return:+.2%}")
    print(f"Total Trades: {metrics.total_trades}")
    print(f"Winning Trades: {metrics.winning_trades}")
    print(f"Losing Trades: {metrics.losing_trades}")
    print(f"Win Rate: {metrics.win_rate:.2%}")
    print(f"Profit Factor: {metrics.profit_factor:.2f}")
    print(f"Average Win: ${metrics.average_win:,.2f}")
    print(f"Average Loss: ${metrics.average_loss:,.2f}")
    print(f"Largest Win: ${metrics.largest_win:,.2f}")
    print(f"Largest Loss: ${metrics.largest_loss:,.2f}")
    print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"Sortino Ratio: {metrics.sortino_ratio:.2f}")
    print(f"Max Drawdown: {metrics.max_drawdown:.2%}")
    print(f"Volatility: {metrics.volatility:.2%}")

    # Show equity curve
    print("\n--- Equity Curve (last 5 points) ---")
    equity_curve = portfolio.get_equity_curve()
    for date, value in equity_curve[-5:]:
        print(f"  {date.strftime('%Y-%m-%d %H:%M:%S')}: ${value:,.2f}")

    return portfolio


def example_persistence():
    """Example 5: Saving and Loading Portfolio"""
    print("\n" + "="*80)
    print("Example 5: Persistence")
    print("="*80)

    # Create and trade
    portfolio = Portfolio(
        initial_capital=Decimal('100000.00'),
        commission_rate=Decimal('0.001')
    )

    portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))
    portfolio.execute_order(MarketOrder('GOOGL', Decimal('50')), Decimal('2000.00'))

    print(f"Original Portfolio:")
    print(f"  Cash: ${portfolio.cash:,.2f}")
    print(f"  Positions: {list(portfolio.positions.keys())}")

    # Save to JSON
    filename = 'example_portfolio.json'
    portfolio.save(filename)
    print(f"\nSaved portfolio to {filename}")

    # Load from JSON
    loaded_portfolio = Portfolio.load(filename)
    print(f"\nLoaded Portfolio:")
    print(f"  Cash: ${loaded_portfolio.cash:,.2f}")
    print(f"  Positions: {list(loaded_portfolio.positions.keys())}")

    # Verify they match
    assert loaded_portfolio.cash == portfolio.cash
    assert len(loaded_portfolio.positions) == len(portfolio.positions)
    print("\n✓ Portfolio state successfully preserved")

    # Save to SQLite
    from tradingagents.portfolio import PortfolioPersistence
    persistence = PortfolioPersistence('./portfolio_data')

    portfolio_data = portfolio.to_dict()
    persistence.save_to_sqlite(portfolio_data, 'example_portfolio.db')
    print(f"\nSaved to SQLite database: example_portfolio.db")

    # Export trades to CSV
    if portfolio.trade_history:
        persistence.export_to_csv(
            [trade.to_dict() for trade in portfolio.trade_history],
            'example_trades.csv'
        )
        print("Exported trade history to CSV: example_trades.csv")

    return portfolio


def example_tradingagents_integration():
    """Example 6: TradingAgents Integration"""
    print("\n" + "="*80)
    print("Example 6: TradingAgents Integration")
    print("="*80)

    portfolio = Portfolio(
        initial_capital=Decimal('100000.00'),
        commission_rate=Decimal('0.001')
    )

    # Create integration layer
    integration = TradingAgentsPortfolioIntegration(portfolio)

    # Simulate agent decisions
    current_prices = {
        'AAPL': Decimal('150.00'),
        'GOOGL': Decimal('2000.00'),
        'MSFT': Decimal('300.00')
    }

    # Decision 1: Buy AAPL
    print("\n--- Agent Decision 1: Buy AAPL ---")
    decision1 = {
        'action': 'buy',
        'ticker': 'AAPL',
        'quantity': 100,
        'order_type': 'market',
        'reasoning': 'Strong bullish sentiment from technical and fundamental analysis'
    }

    result = integration.execute_agent_decision(decision1, current_prices)
    print(f"Status: {result['status']}")
    print(f"Action: {result['action']} {result['ticker']}")
    print(f"Quantity: {result['quantity']}")
    print(f"Price: ${result['price']}")

    # Decision 2: Buy GOOGL with limit order
    print("\n--- Agent Decision 2: Buy GOOGL (Limit Order) ---")
    decision2 = {
        'action': 'buy',
        'ticker': 'GOOGL',
        'quantity': 50,
        'order_type': 'limit',
        'limit_price': Decimal('2000.00'),
        'reasoning': 'Value opportunity identified'
    }

    result = integration.execute_agent_decision(decision2, current_prices)
    print(f"Status: {result['status']}")

    # Get portfolio context for agents
    print("\n--- Portfolio Context for Agents ---")
    context = integration.get_portfolio_context(current_prices)

    print(f"Total Value: ${context['total_value']}")
    print(f"Cash: ${context['cash']} ({context['cash_pct']})")
    print(f"Invested: ${context['invested_value']}")
    print(f"Unrealized P&L: ${context['unrealized_pnl']}")
    print(f"Total Return: {context['total_return']}")
    print(f"Number of Positions: {context['num_positions']}")

    print("\nPositions:")
    for pos in context['positions']:
        print(f"  {pos['ticker']}: {pos['quantity']} shares @ ${pos['cost_basis']}")
        if 'unrealized_pnl' in pos:
            print(f"    P&L: ${pos['unrealized_pnl']} ({pos['unrealized_pnl_pct']})")

    # Rebalance portfolio
    print("\n--- Rebalancing Portfolio ---")
    target_weights = {
        'AAPL': Decimal('0.40'),
        'GOOGL': Decimal('0.30'),
        'MSFT': Decimal('0.30')
    }

    print("Target Weights:")
    for ticker, weight in target_weights.items():
        print(f"  {ticker}: {weight:.1%}")

    rebalance_results = integration.rebalance_portfolio(target_weights, current_prices)

    print(f"\nRebalancing completed: {len(rebalance_results)} trades executed")
    for result in rebalance_results:
        if result['status'] == 'success':
            print(f"  {result['action']} {result['ticker']}: {result['quantity']} shares")

    # Get execution history
    print("\n--- Execution History ---")
    history = integration.get_execution_history(limit=5)
    print(f"Last {len(history)} executions recorded")

    return portfolio, integration


def main():
    """Run all examples"""
    print("\n" + "="*80)
    print("TradingAgents Portfolio Management System - Comprehensive Examples")
    print("="*80)

    try:
        # Run each example
        portfolio1 = example_basic_trading()
        portfolio2 = example_order_types()
        portfolio3 = example_risk_management()
        portfolio4 = example_performance_analytics()
        portfolio5 = example_persistence()
        portfolio6, integration = example_tradingagents_integration()

        print("\n" + "="*80)
        print("All Examples Completed Successfully!")
        print("="*80)

        print("\nKey Takeaways:")
        print("1. Easy to use API for portfolio management")
        print("2. Multiple order types with proper execution logic")
        print("3. Comprehensive risk management and limits")
        print("4. Detailed performance analytics and metrics")
        print("5. Flexible persistence options (JSON, SQLite, CSV)")
        print("6. Seamless integration with TradingAgents framework")

        print("\nNext Steps:")
        print("- Review the source code in tradingagents/portfolio/")
        print("- Check out the test suite in tests/portfolio/")
        print("- Read the README at tradingagents/portfolio/README.md")
        print("- Integrate with your TradingAgents strategies")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
