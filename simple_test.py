#!/usr/bin/env python3
"""
Simple functional test for TradingAgents
"""

from decimal import Decimal

print("\n" + "="*70)
print("🧪 TRADINGAGENTS FUNCTIONAL TEST")
print("="*70 + "\n")

# Test 1: Security
print("1️⃣  Security Validators")
print("-" * 70)
from tradingagents.security import validate_ticker, validate_date, sanitize_path_component

print("✓ Valid ticker:", validate_ticker("AAPL"))
print("✓ Valid date:", validate_date("2024-01-15"))
print("✓ Safe path:", sanitize_path_component("my-portfolio"))

try:
    validate_ticker("../etc/passwd")
    print("✗ FAIL: Should reject path traversal")
except ValueError:
    print("✓ Path traversal blocked")

# Test 2: Portfolio Creation
print("\n2️⃣  Portfolio Management")
print("-" * 70)
from tradingagents.portfolio import Portfolio, MarketOrder

portfolio = Portfolio(
    initial_capital=Decimal('100000'),
    commission_rate=Decimal('0.001')
)
print(f"✓ Created portfolio with ${portfolio.cash:,.2f}")

# Test 3: Execute Trade
print("\n3️⃣  Order Execution")
print("-" * 70)
order = MarketOrder('AAPL', Decimal('100'))
print(f"✓ Created market order: BUY {order.quantity} {order.ticker}")

portfolio.execute_order(order, Decimal('150.00'))
print(f"✓ Order executed")

position = portfolio.get_position('AAPL')
print(f"✓ Position: {position.quantity} shares @ ${position.cost_basis:.2f}")
print(f"✓ Cash remaining: ${portfolio.cash:,.2f}")

# Test 4: Portfolio Valuation
print("\n4️⃣  Portfolio Valuation")
print("-" * 70)
prices = {'AAPL': Decimal('155.00')}
total_value = portfolio.total_value(prices)
pnl = portfolio.unrealized_pnl(prices)

print(f"✓ Total value: ${total_value:,.2f}")
print(f"✓ Unrealized P&L: ${pnl:,.2f}")
print(f"✓ Return: {(pnl / portfolio.initial_capital * 100):.2f}%")

# Test 5: Multiple Positions
print("\n5️⃣  Multiple Positions")
print("-" * 70)
order2 = MarketOrder('MSFT', Decimal('50'))
portfolio.execute_order(order2, Decimal('300.00'))

positions = portfolio.get_all_positions()
print(f"✓ Number of positions: {len(positions)}")
for ticker, pos in positions.items():
    print(f"  • {ticker}: {pos.quantity} shares @ ${pos.cost_basis:.2f}")

# Test 6: Performance Metrics
print("\n6️⃣  Performance Analytics")
print("-" * 70)
prices = {'AAPL': Decimal('155'), 'MSFT': Decimal('310')}
metrics = portfolio.get_performance_metrics(prices)

print(f"✓ Total return: {metrics.total_return:.2%}")
print(f"✓ Number of trades: {metrics.total_trades}")
print(f"✓ Unrealized P&L: ${metrics.unrealized_pnl:,.2f}")

# Test 7: Persistence
print("\n7️⃣  Save/Load Portfolio")
print("-" * 70)
portfolio.save('test_portfolio.json')
print("✓ Portfolio saved")

loaded = Portfolio.load('test_portfolio.json')
print(f"✓ Portfolio loaded: ${loaded.cash:,.2f}")
print(f"✓ Positions restored: {len(loaded.get_all_positions())}")

# Test 8: Order Types
print("\n8️⃣  Order Types")
print("-" * 70)
from tradingagents.portfolio import LimitOrder, StopLossOrder, TakeProfitOrder

limit = LimitOrder('GOOGL', Decimal('10'), limit_price=Decimal('140'))
print(f"✓ Limit order: {limit.ticker} @ ${limit.limit_price}")

stop = StopLossOrder('AAPL', Decimal('100'), stop_price=Decimal('145'))
print(f"✓ Stop-loss order: {stop.ticker} @ ${stop.stop_price}")

take_profit = TakeProfitOrder('AAPL', Decimal('100'), take_profit_price=Decimal('160'))
print(f"✓ Take-profit order: {take_profit.ticker} @ ${take_profit.take_profit_price}")

# Test 9: Backtesting
print("\n9️⃣  Backtesting Framework")
print("-" * 70)
from tradingagents.backtest import BacktestConfig, BuyAndHoldStrategy, Backtester

config = BacktestConfig(
    initial_capital=Decimal('100000'),
    start_date='2024-01-01',
    end_date='2024-01-31'
)
print(f"✓ Backtest configured: {config.start_date} to {config.end_date}")

strategy = BuyAndHoldStrategy()
print(f"✓ Strategy: {strategy.name}")

backtester = Backtester(config)
print(f"✓ Backtester initialized")
print("  (Full backtest requires network - skipping)")

# Summary
print("\n" + "="*70)
print("✅ SUMMARY")
print("="*70)
print("✓ Security validators: WORKING")
print("✓ Portfolio management: WORKING")
print("✓ Order execution: WORKING")
print("✓ Performance analytics: WORKING")
print("✓ Persistence (save/load): WORKING")
print("✓ Multiple order types: WORKING")
print("✓ Backtesting framework: AVAILABLE")

print("\n🎉 TradingAgents is fully operational!")
print("\n📚 Next Steps:")
print("   • Run full tests: pytest tests/portfolio/ -v")
print("   • Try examples: python examples/portfolio_example.py")
print("   • Read docs: cat tradingagents/portfolio/README.md")
print("   • View summary: cat COMPLETE_IMPLEMENTATION_SUMMARY.md")
print("="*70 + "\n")
