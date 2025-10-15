"""
Paper Trading Runner
Run live paper trading with real-time data
"""
import sys
import os
import time
import signal

# Add project root to path (go up 3 levels: scripts -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from crypto_trading.src.paper_trading.paper_trading_engine import PaperTradingEngine, OrderSide


# ============================================================================
# EXAMPLE STRATEGIES
# ============================================================================

class SimpleMovingAverageStrategy:
    """Simple moving average crossover for paper trading."""

    def __init__(self, short_window=20, long_window=50):
        self.short_window = short_window
        self.long_window = long_window
        self.price_history = {}

    def __call__(self, engine, symbol, current_price):
        """Execute strategy logic."""
        # Initialize price history for symbol
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        # Add current price
        self.price_history[symbol].append(current_price)

        # Keep only needed history
        if len(self.price_history[symbol]) > self.long_window:
            self.price_history[symbol] = self.price_history[symbol][-self.long_window:]

        # Need enough data
        if len(self.price_history[symbol]) < self.long_window:
            return None

        # Calculate moving averages
        prices = self.price_history[symbol]
        short_ma = sum(prices[-self.short_window:]) / self.short_window
        long_ma = sum(prices[-self.long_window:]) / self.long_window

        # Golden cross - buy signal
        if short_ma > long_ma and symbol not in engine.positions:
            return OrderSide.BUY

        # Death cross - sell signal
        elif short_ma < long_ma and symbol in engine.positions:
            return OrderSide.SELL

        return None


class MomentumStrategy:
    """Momentum-based strategy."""

    def __init__(self, lookback=10, threshold=0.05):
        self.lookback = lookback
        self.threshold = threshold
        self.price_history = {}

    def __call__(self, engine, symbol, current_price):
        """Execute strategy logic."""
        # Initialize
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(current_price)

        if len(self.price_history[symbol]) > self.lookback + 1:
            self.price_history[symbol] = self.price_history[symbol][-(self.lookback + 1):]

        if len(self.price_history[symbol]) < self.lookback:
            return None

        # Calculate momentum
        momentum = (self.price_history[symbol][-1] - self.price_history[symbol][-self.lookback]) / self.price_history[symbol][-self.lookback]

        # Strong momentum - buy
        if momentum > self.threshold and symbol not in engine.positions:
            return OrderSide.BUY

        # Momentum reversal - sell
        elif momentum < -self.threshold and symbol in engine.positions:
            return OrderSide.SELL

        return None


class RSIStrategy:
    """RSI mean reversion strategy."""

    def __init__(self, period=14, oversold=30, overbought=70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.price_history = {}

    def calculate_rsi(self, prices):
        """Calculate RSI."""
        if len(prices) < self.period + 1:
            return 50

        gains = []
        losses = []

        for i in range(1, self.period + 1):
            change = prices[-i] - prices[-i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def __call__(self, engine, symbol, current_price):
        """Execute strategy logic."""
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(current_price)

        if len(self.price_history[symbol]) > self.period + 10:
            self.price_history[symbol] = self.price_history[symbol][-(self.period + 10):]

        rsi = self.calculate_rsi(self.price_history[symbol])

        # Oversold - buy
        if rsi < self.oversold and symbol not in engine.positions:
            return OrderSide.BUY

        # Overbought - sell
        elif rsi > self.overbought and symbol in engine.positions:
            return OrderSide.SELL

        return None


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run paper trading."""
    print("\n" + "="*80)
    print("  CRYPTO PAPER TRADING - LIVE SIMULATION")
    print("="*80)
    print("\nThis runs live paper trading with real-time market data.")
    print("No real money is at risk - this is a simulation.\n")

    print("Requirements:")
    print("  ✓ CCXT installed (pip install ccxt)")
    print("  ✓ Internet connection")
    print("  ✓ Press Ctrl+C to stop gracefully\n")

    # Configuration
    print("Configuration:")
    print("  Exchange: Binance")
    print("  Symbols: BTC/USDT, ETH/USDT")
    print("  Initial Capital: $10,000")
    print("  Update Interval: 60 seconds")
    print("  Strategy: MA Crossover (20/50)")
    print()

    input("Press Enter to start paper trading...")

    # Create engine
    engine = PaperTradingEngine(
        exchange_id='binance',
        initial_capital=10000,
        commission_rate=0.001,
        max_position_size=0.20,
        max_daily_loss=0.05,
        stop_loss_pct=0.15,
        take_profit_pct=0.30,
        update_interval=60  # 1 minute updates
    )

    # Set strategy
    strategy = SimpleMovingAverageStrategy(short_window=20, long_window=50)
    engine.set_strategy(strategy)

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n\nReceived interrupt signal...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Start paper trading
    symbols = ['BTC/USDT', 'ETH/USDT']
    engine.start(symbols)

    # Keep main thread alive
    try:
        while engine.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop()

    print("\nPaper trading stopped.")
    print("Data saved to: ./paper_trading_data/\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
