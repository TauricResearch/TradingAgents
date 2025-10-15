"""
Paper Trading Dashboard Demo
Shows real-time monitoring and analytics
"""
import os
import sys
import time

# Add project root to path (go up 3 levels: scripts -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from crypto_trading.src.paper_trading.paper_trading_engine import PaperTradingEngine, OrderSide
from crypto_trading.src.paper_trading.dashboard import PaperTradingDashboard


class DemoStrategy:
    """Simple demo strategy for testing dashboard."""

    def __init__(self):
        self.prices = {}
        self.trade_count = 0

    def __call__(self, engine, symbol, price):
        """Execute demo strategy."""
        # Track prices
        if symbol not in self.prices:
            self.prices[symbol] = []

        self.prices[symbol].append(price)

        # Keep last 10 prices
        if len(self.prices[symbol]) > 10:
            self.prices[symbol] = self.prices[symbol][-10:]

        # Simple momentum strategy
        if len(self.prices[symbol]) >= 5:
            recent_avg = sum(self.prices[symbol][-3:]) / 3
            older_avg = sum(self.prices[symbol][-6:-3]) / 3

            # Buy signal
            if recent_avg > older_avg and symbol not in engine.positions and self.trade_count < 5:
                self.trade_count += 1
                return OrderSide.BUY

            # Sell signal
            if recent_avg < older_avg and symbol in engine.positions:
                return OrderSide.SELL

        return None


def main():
    """Run paper trading demo with dashboard."""
    print("\n" + "="*80)
    print("  PAPER TRADING DASHBOARD DEMO")
    print("="*80)
    print("\nThis demo runs paper trading with real-time dashboard monitoring.")
    print("Duration: 60 seconds")
    print("Symbols: BTC/USDT, ETH/USDT")
    print("Strategy: Simple momentum crossover\n")

    input("Press Enter to start...")

    # Create engine
    engine = PaperTradingEngine(
        exchange_id='binance',
        initial_capital=10000,
        commission_rate=0.001,
        max_position_size=0.15,
        max_daily_loss=0.05,
        stop_loss_pct=0.10,
        take_profit_pct=0.20,
        update_interval=5,  # 5 second updates
        data_dir="./paper_trading_data"
    )

    # Create dashboard
    dashboard = PaperTradingDashboard(engine)

    # Set strategy
    strategy = DemoStrategy()
    engine.set_strategy(strategy)

    # Start paper trading
    symbols = ['BTC/USDT', 'ETH/USDT']
    engine.start(symbols)

    print("\n📊 Dashboard updates every 15 seconds...\n")

    try:
        # Monitor for 60 seconds
        for i in range(4):  # 4 updates over 60 seconds
            time.sleep(15)
            dashboard.print_live_status()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user...")

    # Stop trading
    engine.stop()

    # Print final performance report
    print("\n" + "="*80)
    print("  FINAL PERFORMANCE REPORT")
    print("="*80)
    dashboard.print_performance_report()

    # Export data
    print("\n" + "="*80)
    print("  EXPORTING DATA")
    print("="*80 + "\n")

    dashboard.export_to_csv()
    dashboard.export_portfolio_history()
    html_file = dashboard.generate_html_report()

    print("\n" + "="*80)
    print("  DEMO COMPLETED")
    print("="*80)
    print(f"\n✓ Paper trading completed successfully!")
    print(f"✓ HTML dashboard: {html_file}")
    print(f"✓ Data saved to: ./paper_trading_data/\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
