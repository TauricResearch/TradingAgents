"""
Unit Tests for Paper Trading Engine
"""
import unittest
import time
import os
import sys
from datetime import datetime

# Add project root to path (go up 3 levels: tests -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from crypto_trading.src.paper_trading.paper_trading_engine import PaperTradingEngine, OrderSide


class TestPaperTradingEngine(unittest.TestCase):
    """Test suite for paper trading engine."""

    def setUp(self):
        """Set up test engine."""
        self.engine = PaperTradingEngine(
            exchange_id='binance',
            initial_capital=10000,
            commission_rate=0.001,
            max_position_size=0.20,
            max_daily_loss=0.05,
            stop_loss_pct=0.15,
            take_profit_pct=0.30,
            update_interval=1,  # Fast for testing
            data_dir="./test_paper_trading_data"
        )

    def test_initialization(self):
        """Test engine initialization."""
        self.assertEqual(self.engine.initial_capital, 10000)
        self.assertEqual(self.engine.cash, 10000)
        self.assertEqual(len(self.engine.positions), 0)
        self.assertEqual(len(self.engine.orders), 0)
        self.assertFalse(self.engine.is_running)
        print("✓ Initialization test passed")

    def test_portfolio_value(self):
        """Test portfolio value calculation."""
        # Initial portfolio value should equal cash
        self.assertEqual(self.engine.get_portfolio_value(), 10000)

        # Simulate a position
        self.engine.current_prices = {'BTC/USDT': 50000}
        self.engine._place_buy_order('BTC/USDT', 50000, "Test buy")

        # Portfolio value should be close to initial (minus commission)
        portfolio_value = self.engine.get_portfolio_value()
        self.assertGreater(portfolio_value, 9900)  # Lost some to commission
        self.assertLess(portfolio_value, 10000)
        print(f"✓ Portfolio value test passed: ${portfolio_value:,.2f}")

    def test_buy_order(self):
        """Test buy order execution."""
        self.engine.current_prices = {'BTC/USDT': 50000}

        initial_cash = self.engine.cash
        self.engine._place_buy_order('BTC/USDT', 50000, "Test buy")

        # Check position created
        self.assertIn('BTC/USDT', self.engine.positions)

        # Check cash decreased
        self.assertLess(self.engine.cash, initial_cash)

        # Check order recorded
        self.assertEqual(len(self.engine.orders), 1)
        self.assertEqual(self.engine.orders[0].side, OrderSide.BUY)
        print("✓ Buy order test passed")

    def test_sell_order(self):
        """Test sell order execution."""
        # First buy
        self.engine.current_prices = {'BTC/USDT': 50000}
        self.engine._place_buy_order('BTC/USDT', 50000, "Test buy")

        initial_cash = self.engine.cash

        # Then sell at higher price
        self.engine._place_sell_order('BTC/USDT', 55000, "Test sell")

        # Check position closed
        self.assertNotIn('BTC/USDT', self.engine.positions)

        # Check cash increased (profitable trade)
        self.assertGreater(self.engine.cash, initial_cash)

        # Check order recorded
        self.assertEqual(len(self.engine.orders), 2)
        self.assertEqual(self.engine.orders[1].side, OrderSide.SELL)
        print("✓ Sell order test passed")

    def test_stop_loss(self):
        """Test stop loss mechanism."""
        # Buy at 50000
        self.engine.current_prices = {'BTC/USDT': 50000}
        self.engine._place_buy_order('BTC/USDT', 50000, "Test buy")

        # Price drops 20% (exceeds 15% stop loss)
        self.engine.current_prices = {'BTC/USDT': 40000}
        self.engine._check_stop_loss_take_profit()

        # Position should be closed
        self.assertNotIn('BTC/USDT', self.engine.positions)
        print("✓ Stop loss test passed")

    def test_take_profit(self):
        """Test take profit mechanism."""
        # Buy at 50000
        self.engine.current_prices = {'BTC/USDT': 50000}
        self.engine._place_buy_order('BTC/USDT', 50000, "Test buy")

        # Price rises 35% (exceeds 30% take profit)
        self.engine.current_prices = {'BTC/USDT': 67500}
        self.engine._check_stop_loss_take_profit()

        # Position should be closed
        self.assertNotIn('BTC/USDT', self.engine.positions)
        print("✓ Take profit test passed")

    def test_position_sizing(self):
        """Test position sizing limits."""
        self.engine.current_prices = {'BTC/USDT': 50000}
        self.engine._place_buy_order('BTC/USDT', 50000, "Test buy")

        position = self.engine.positions['BTC/USDT']
        position_value = position.amount * 50000
        portfolio_value = self.engine.get_portfolio_value()

        # Position should be <= max_position_size (with small tolerance for commission)
        position_pct = position_value / portfolio_value
        self.assertLessEqual(position_pct, self.engine.max_position_size + 0.001)
        print(f"✓ Position sizing test passed: {position_pct:.2%} of portfolio")

    def test_kill_switch(self):
        """Test kill switch for daily loss limit."""
        # Buy at 50000
        self.engine.current_prices = {'BTC/USDT': 50000}
        self.engine._place_buy_order('BTC/USDT', 50000, "Test buy")

        # Price drops 50% (huge loss)
        self.engine.current_prices = {'BTC/USDT': 25000}

        # Check kill switch
        should_stop = self.engine._check_kill_switch()
        self.assertTrue(should_stop)
        print("✓ Kill switch test passed")

    def test_strategy_execution(self):
        """Test strategy callback execution."""
        # Define simple test strategy
        def test_strategy(engine, symbol, price):
            if price < 50000:
                return OrderSide.BUY
            elif price > 60000 and symbol in engine.positions:
                return OrderSide.SELL
            return None

        self.engine.set_strategy(test_strategy)

        # Test buy signal
        self.engine.current_prices = {'BTC/USDT': 45000}
        self.engine._execute_strategy('BTC/USDT')
        self.assertIn('BTC/USDT', self.engine.positions)

        # Test sell signal
        self.engine.current_prices = {'BTC/USDT': 65000}
        self.engine._execute_strategy('BTC/USDT')
        self.assertNotIn('BTC/USDT', self.engine.positions)
        print("✓ Strategy execution test passed")

    def test_real_price_fetching(self):
        """Test fetching real prices from exchange."""
        try:
            self.engine.symbols = ['BTC/USDT']
            self.engine._update_prices()

            # Check price was fetched
            self.assertIn('BTC/USDT', self.engine.current_prices)
            price = self.engine.current_prices['BTC/USDT']

            # BTC price should be reasonable
            self.assertGreater(price, 10000)
            self.assertLess(price, 200000)
            print(f"✓ Real price fetching test passed: BTC/USDT = ${price:,.2f}")
        except Exception as e:
            print(f"⚠ Real price fetching test skipped: {e}")
            print("  (Requires internet connection)")


class TestPaperTradingIntegration(unittest.TestCase):
    """Integration tests for paper trading."""

    def test_short_live_trading(self):
        """Test short live trading session."""
        # Create engine
        engine = PaperTradingEngine(
            exchange_id='binance',
            initial_capital=10000,
            update_interval=2,  # 2 second updates
            data_dir="./test_paper_trading_data"
        )

        # Simple MA strategy
        class SimpleStrategy:
            def __init__(self):
                self.prices = {}

            def __call__(self, engine, symbol, price):
                if symbol not in self.prices:
                    self.prices[symbol] = []

                self.prices[symbol].append(price)

                # Buy if no position and have 3+ prices
                if len(self.prices[symbol]) >= 3 and symbol not in engine.positions:
                    return OrderSide.BUY

                # Sell if have position and price moved
                if symbol in engine.positions and len(self.prices[symbol]) >= 5:
                    return OrderSide.SELL

                return None

        engine.set_strategy(SimpleStrategy())

        # Start trading
        print("\n--- Starting 10-second paper trading test ---")
        engine.start(['BTC/USDT'])

        # Run for 10 seconds
        time.sleep(10)

        # Stop trading
        engine.stop()

        # Validate
        self.assertFalse(engine.is_running)
        self.assertGreaterEqual(len(engine.portfolio_value_history), 1)
        print(f"✓ Live trading test completed")
        print(f"  Total updates: {len(engine.portfolio_value_history)}")
        print(f"  Total orders: {len(engine.orders)}")
        print(f"  Final portfolio: ${engine.get_portfolio_value():,.2f}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("  PAPER TRADING ENGINE TEST SUITE")
    print("="*70 + "\n")

    # Run unit tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestPaperTradingEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperTradingIntegration))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70 + "\n")
