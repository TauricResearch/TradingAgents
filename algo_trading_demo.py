"""
Algo Trading Demo - Standalone (no API keys required)

Demonstrates all core components of the algo trading system
without needing to initialize the full analysis graph.

Run: python algo_trading_demo.py
"""

from datetime import datetime, timedelta
from tradingagents.strategy.portfolio_manager import PortfolioManager
from tradingagents.strategy.exit_strategy import ExitStrategy, ExitConfig
from tradingagents.strategy.trade_validator import TradeValidator
from tradingagents.agents.trader.paper_trading import PaperTrader


def demo_portfolio_manager():
    """Demonstrate portfolio management"""
    print("\n" + "="*70)
    print("DEMO 1: Portfolio Management")
    print("="*70)
    
    pm = PortfolioManager(
        portfolio_cash=10000.0,
        max_position_pct=0.08,
        max_risky_pct=0.25,
        max_positions=10,
    )
    
    print(f"\nStarting portfolio: ${pm.cash:.2f}")
    print(f"Max position per stock: {pm.max_position_pct*100:.0f}%")
    print(f"Max risky exposure: {pm.max_risky_pct*100:.0f}%")
    print(f"Max positions: {pm.max_positions}")
    
    # Simulate screening detects NVDA with pump score 82
    print("\n--- Signal: NVDA pump detected (score: 82) ---")
    
    position_size = pm.calculate_position_size(
        current_price=150.0,
        signal_score=82.0,
        position_type="pump"
    )
    
    if position_size:
        print(f"Position size calculated:")
        print(f"  • Shares: {position_size['shares']}")
        print(f"  • Value: ${position_size['position_value']:.2f}")
        print(f"  • Signal multiplier: {position_size['signal_multiplier']:.1%}")
        
        pm.add_position(
            ticker="NVDA",
            shares=position_size['shares'],
            entry_price=150.0,
            signal_score=82.0,
            position_type="pump"
        )
        print(f"✓ Position added to portfolio")
    
    # Detect second signal: TSLA (weaker signal)
    print("\n--- Signal: TSLA momentum detected (score: 45) ---")
    
    position_size = pm.calculate_position_size(
        current_price=250.0,
        signal_score=45.0,
        position_type="momentum"
    )
    
    if position_size:
        print(f"Position size: {position_size['shares']} shares (${position_size['position_value']:.2f})")
        pm.add_position(
            ticker="TSLA",
            shares=position_size['shares'],
            entry_price=250.0,
            signal_score=45.0,
            position_type="momentum"
        )
        print(f"✓ Position added to portfolio")
    
    # Check portfolio status
    status = pm.get_portfolio_status()
    print(f"\n--- Portfolio Status ---")
    print(f"Total value: ${status['total_value']:.2f}")
    print(f"Cash: ${status['cash']:.2f}")
    print(f"Positions value: ${status['positions_value']:.2f}")
    print(f"Number of positions: {status['num_positions']}")
    print(f"Cash utilization: {status['cash_utilization']:.1f}%")
    print(f"Risky exposure: {status['risky_exposure']:.1f}%")
    
    # Try to add a third position that violates limits
    print("\n--- Attempting risky position (would exceed limits) ---")
    
    position_size = pm.calculate_position_size(
        current_price=80.0,
        signal_score=90.0,
        position_type="pump"
    )
    
    if position_size:
        print(f"Position would be: {position_size['shares']} shares (${position_size['position_value']:.2f})")
        print(f"✓ Size-limiting worked - prevents portfolio overload")


def demo_exit_strategy():
    """Demonstrate exit management"""
    print("\n" + "="*70)
    print("DEMO 2: Exit Strategy Management")
    print("="*70)
    
    exit_strat = ExitStrategy(
        ExitConfig(
            profit_target_pct=5.0,
            stop_loss_pct=2.0,
            max_hold_days=5,
            trailing_stop_pct=2.0,
        )
    )
    
    print(f"\nExit strategy config:")
    print(f"  • Profit target: +{exit_strat.config.profit_target_pct}%")
    print(f"  • Stop loss: -{exit_strat.config.stop_loss_pct}%")
    print(f"  • Max hold: {exit_strat.config.max_hold_days} days")
    print(f"  • Trailing stop: {exit_strat.config.trailing_stop_pct}%")
    
    entry_price = 150.0
    targets = exit_strat.get_exit_targets(entry_price)
    print(f"\nEntry: ${entry_price:.2f}")
    print(f"Profit target: ${targets['profit_target']:.2f}")
    print(f"Stop loss: ${targets['stop_loss']:.2f}")
    print(f"Trailing stop trigger: ${targets['trailing_stop_trigger']:.2f}")
    
    # Scenario 1: Price rises to profit target
    print(f"\n--- Scenario 1: Price rises to ${158:.2f} ---")
    signal = exit_strat.evaluate_exit(
        ticker="NVDA",
        current_price=158.0,
        entry_price=150.0,
        entry_date=datetime.now(),
        signal_score=75.0,
        position_type="pump"
    )
    if signal and signal['exit_signal']:
        print(f"EXIT SIGNAL: {signal['reason'].upper()}")
        print(f"  P/L: {signal['pnl_pct']:.1f}%")
        print(f"Exit price: ${signal['exit_price']:.2f}")
    
    # Scenario 2: Price falls to stop loss
    print(f"\n--- Scenario 2: Price falls to ${147:.2f} ---")
    signal = exit_strat.evaluate_exit(
        ticker="NVDA",
        current_price=147.0,
        entry_price=150.0,
        entry_date=datetime.now(),
        signal_score=75.0,
        position_type="pump"
    )
    if signal and signal['exit_signal']:
        print(f"EXIT SIGNAL: {signal['reason'].upper()}")
        print(f"  P/L: {signal['pnl_pct']:.1f}%")
        print(f"Exit price: ${signal['exit_price']:.2f}")
    
    # Scenario 3: Time limit exceeded
    print(f"\n--- Scenario 3: Held for {exit_strat.config.max_hold_days + 1} days ---")
    old_date = datetime.now() - timedelta(days=6)
    signal = exit_strat.evaluate_exit(
        ticker="NVDA",
        current_price=149.0,
        entry_price=150.0,
        entry_date=old_date,
        signal_score=75.0,
        position_type="pump"
    )
    if signal and signal['exit_signal']:
        print(f"EXIT SIGNAL: {signal['reason'].upper()}")
        print(f"  Hold days: {signal['hold_days']}")
        print(f"Exit price: ${signal['exit_price']:.2f}")


def demo_trade_validator():
    """Demonstrate trade validation"""
    print("\n" + "="*70)
    print("DEMO 3: Trade Validation")
    print("="*70)
    
    validator = TradeValidator()
    
    print(f"\n--- Validating BUY Order (Valid) ---")
    result = validator.validate_buy_order(
        ticker="NVDA",
        shares=4,
        price=150.0,
        available_cash=8000.0,
        portfolio_value=10000.0,
        max_position_pct=0.08
    )
    if result['is_valid']:
        print(f"✓ VALID")
        print(f"  Order value: ${result['order_value']:.2f}")
        print(f"  Shares: {result['shares']}")
    
    print(f"\n--- Validating BUY Order (Insufficient Funds) ---")
    result = validator.validate_buy_order(
        ticker="NVDA",
        shares=100,
        price=150.0,
        available_cash=8000.0,
        portfolio_value=10000.0,
    )
    if not result['is_valid']:
        print(f"✗ INVALID")
        for issue in result['issues']:
            print(f"  • {issue}")
    
    print(f"\n--- Validating SELL Order (Valid) ---")
    result = validator.validate_sell_order(
        ticker="NVDA",
        shares=4,
        price=158.0,
        position_shares=4,
        position_value=600.0
    )
    if result['is_valid']:
        print(f"✓ VALID")
        print(f"  Order value: ${result['order_value']:.2f}")
        print(f"  Profit: ${158 * 4 - 150 * 4:.2f}")


def demo_paper_trading():
    """Demonstrate paper trading interface"""
    print("\n" + "="*70)
    print("DEMO 4: Paper Trading Interface")
    print("="*70)
    
    # Create demo trader (no auth required)
    trader = PaperTrader.demo_mode()
    print(f"\n✓ Paper trader initialized (demo mode)")
    print(f"  Authenticated: {trader.is_authenticated}")
    print(f"  Paper trading: {trader.is_paper}")
    
    print(f"\nAvailable methods:")
    print(f"  • place_buy_order(ticker, quantity, limit_price)")
    print(f"  • place_sell_order(ticker, quantity, limit_price)")
    print(f"  • get_positions()")
    print(f"  • get_account_balance()")
    print(f"  • get_orders()")
    print(f"  • get_stock_quote(ticker)")
    print(f"  • cancel_order(order_id)")
    
    print(f"\n--- To use real trading ---")
    print(f"1. Create Webull account at webull.com")
    print(f"2. Enable paper trading in account settings")
    print(f"3. Set environment variables:")
    print(f"   export WEBULL_EMAIL='your_email@example.com'")
    print(f"   export WEBULL_PASSWORD='your_password'")
    print(f"4. Create trader with your credentials:")
    print(f"   trader = PaperTrader(")
    print(f"       email='your_email@example.com',")
    print(f"       password='your_password',")
    print(f"       is_paper=True")
    print(f"   )")
    print(f"5. Login and get trade token:")
    print(f"   trader.login()")
    print(f"   trader.get_trade_token(pin='123456')")


def demo_complete_flow():
    """Demonstrate complete trading flow"""
    print("\n" + "="*70)
    print("DEMO 5: Complete Trading Flow")
    print("="*70)
    
    print(f"\nSimulating a complete algo trading scenario...\n")
    
    pm = PortfolioManager(portfolio_cash=10000.0)
    exit_strat = ExitStrategy()
    validator = TradeValidator()
    
    # Step 1: Screening detects opportunity
    print("STEP 1: Stock Screening")
    print("  └─ NVDA identified as trending (pump score: 82)")
    
    # Step 2: Calculate position size
    print("\nSTEP 2: Position Sizing")
    position = pm.calculate_position_size(150.0, 82.0, "pump")
    print(f"  └─ Buy {position['shares']} shares @ $150 = ${position['position_value']:.2f}")
    
    # Step 3: Validate order
    print("\nSTEP 3: Order Validation")
    validation = validator.validate_buy_order(
        "NVDA", position['shares'], 150.0,
        pm.cash, pm.portfolio_value
    )
    if validation['is_valid']:
        print(f"  └─ ✓ Order approved")
    
    # Step 4: Execute buy
    print("\nSTEP 4: Execute BUY")
    pm.add_position("NVDA", position['shares'], 150.0, 82.0, "pump")
    print(f"  └─ Bought {position['shares']} shares")
    
    # Step 5: Monitor position
    print("\nSTEP 5: Monitor Position (price moves to $158)")
    exit_signal = exit_strat.evaluate_exit(
        "NVDA", 158.0, 150.0, datetime.now(), 82.0, "pump"
    )
    if exit_signal and exit_signal['exit_signal']:
        print(f"  └─ Exit signal: {exit_signal['reason'].upper()}")
        print(f"  └─ Profit: {exit_signal['pnl_pct']:.1f}%")
    
    # Step 6: Execute sell
    print("\nSTEP 6: Execute SELL")
    result = pm.close_position("NVDA", 158.0, "profit_target")
    if result:
        print(f"  └─ Sold {position['shares']} shares @ $158")
        print(f"  └─ Profit: ${result['profit']:.2f} ({result['profit_pct']:.1f}%)")
    
    # Step 7: Review status
    print("\nSTEP 7: Portfolio Status")
    status = pm.get_portfolio_status()
    print(f"  └─ Total value: ${status['total_value']:.2f}")
    print(f"  └─ Cash: ${status['cash']:.2f}")
    print(f"  └─ Open positions: {status['num_positions']}")


def main():
    """Run all demos"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*15 + "ALGO TRADING SYSTEM - COMPONENT DEMO" + " "*17 + "║")
    print("╚" + "="*68 + "╝")
    
    demo_portfolio_manager()
    demo_exit_strategy()
    demo_trade_validator()
    demo_paper_trading()
    demo_complete_flow()
    
    print("\n" + "="*70)
    print("✅ ALL DEMOS COMPLETED")
    print("="*70)
    print("\nNext steps:")
    print("  1. Read ALGO_TRADING_GUIDE.md for complete documentation")
    print("  2. Set up Webull account for paper trading")
    print("  3. Run: python algo_trading_workflow.py (after setting API keys)")
    print()


if __name__ == "__main__":
    main()
