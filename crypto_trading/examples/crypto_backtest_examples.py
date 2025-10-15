"""
Example strategies for crypto backtesting
Demonstrates various trading strategies and agent integration
"""
import sys
import os
# Add project root to path (go up 3 levels: examples -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from datetime import datetime, timedelta
from crypto_trading.src.backtesting.crypto_backtest_engine import CryptoBacktestEngine, OrderType
from crypto_trading.src.backtesting.crypto_data_loader import CryptoDataLoader
from crypto_trading.src.backtesting.crypto_strategy_evaluator import CryptoStrategyEvaluator, AgentDecision


# ============================================================================
# EXAMPLE 1: Buy and Hold Strategy
# ============================================================================

def buy_and_hold_strategy(timestamp, row, engine):
    """
    Simple buy and hold strategy.
    Buy once at the start, hold until end.
    """
    if len(engine.positions) == 0:
        return OrderType.BUY, "Initial buy - Buy and Hold"
    return OrderType.HOLD, "Holding position"


# ============================================================================
# EXAMPLE 2: Moving Average Crossover
# ============================================================================

class MovingAverageCrossover:
    """MA crossover strategy with state."""

    def __init__(self, short_window=50, long_window=200):
        self.short_window = short_window
        self.long_window = long_window
        self.prices = []

    def __call__(self, timestamp, row, engine):
        """Execute strategy."""
        self.prices.append(row['close'])

        if len(self.prices) < self.long_window:
            return OrderType.HOLD, "Warming up indicators"

        # Calculate MAs
        short_ma = sum(self.prices[-self.short_window:]) / self.short_window
        long_ma = sum(self.prices[-self.long_window:]) / self.long_window

        # Golden cross (buy signal)
        if short_ma > long_ma and len(engine.positions) == 0:
            return OrderType.BUY, f"Golden cross: MA{self.short_window} > MA{self.long_window}"

        # Death cross (sell signal)
        elif short_ma < long_ma and len(engine.positions) > 0:
            return OrderType.SELL, f"Death cross: MA{self.short_window} < MA{self.long_window}"

        return OrderType.HOLD, "No crossover signal"


# ============================================================================
# EXAMPLE 3: RSI Mean Reversion
# ============================================================================

class RSIMeanReversion:
    """RSI-based mean reversion strategy."""

    def __init__(self, period=14, oversold=30, overbought=70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.prices = []

    def calculate_rsi(self):
        """Calculate RSI."""
        if len(self.prices) < self.period + 1:
            return 50  # Neutral

        gains = []
        losses = []

        for i in range(1, self.period + 1):
            change = self.prices[-i] - self.prices[-i-1]
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

    def __call__(self, timestamp, row, engine):
        """Execute strategy."""
        self.prices.append(row['close'])

        rsi = self.calculate_rsi()

        # Oversold - buy signal
        if rsi < self.oversold and len(engine.positions) == 0:
            return OrderType.BUY, f"RSI oversold: {rsi:.1f}"

        # Overbought - sell signal
        elif rsi > self.overbought and len(engine.positions) > 0:
            return OrderType.SELL, f"RSI overbought: {rsi:.1f}"

        return OrderType.HOLD, f"RSI neutral: {rsi:.1f}"


# ============================================================================
# EXAMPLE 4: Simulated Agent Strategy
# ============================================================================

def simulated_agent_strategy(timestamp, row, engine):
    """
    Simulated crypto agent decision-making.
    Mimics multi-signal analysis from agents.
    """
    price = row['close']

    # Simulate technical analysis
    sma_50 = row.get('sma_50', price)
    technical_signal = 1 if price > sma_50 else -1

    # Simulate fundamental analysis (price-based proxy)
    fundamental_signal = 1 if price < 42000 else -1  # Undervalued below 42k

    # Simulate on-chain sentiment (mock)
    onchain_signal = 1  # Assume bullish on-chain

    # Aggregate signals
    total_signal = technical_signal + fundamental_signal + onchain_signal
    confidence = abs(total_signal) / 3.0

    # Make decision
    if total_signal >= 2 and len(engine.positions) == 0:
        return OrderType.BUY, f"Agent BUY: {total_signal}/3 bullish signals (conf: {confidence:.0%})"

    elif total_signal <= -2 and len(engine.positions) > 0:
        return OrderType.SELL, f"Agent SELL: {total_signal}/3 bearish signals (conf: {confidence:.0%})"

    return OrderType.HOLD, f"Agent HOLD: Mixed signals {total_signal}/3"


# ============================================================================
# EXAMPLE 5: Volatility Breakout
# ============================================================================

class VolatilityBreakout:
    """Trade breakouts based on volatility."""

    def __init__(self, lookback=20, std_multiplier=2.0):
        self.lookback = lookback
        self.std_multiplier = std_multiplier
        self.prices = []

    def __call__(self, timestamp, row, engine):
        """Execute strategy."""
        self.prices.append(row['close'])

        if len(self.prices) < self.lookback:
            return OrderType.HOLD, "Building history"

        recent_prices = self.prices[-self.lookback:]
        mean_price = sum(recent_prices) / len(recent_prices)

        # Calculate standard deviation
        variance = sum((p - mean_price) ** 2 for p in recent_prices) / len(recent_prices)
        std = variance ** 0.5

        upper_band = mean_price + (std * self.std_multiplier)
        lower_band = mean_price - (std * self.std_multiplier)

        current_price = row['close']

        # Breakout above upper band
        if current_price > upper_band and len(engine.positions) == 0:
            return OrderType.BUY, f"Breakout above ${upper_band:.0f}"

        # Breakdown below lower band
        elif current_price < lower_band and len(engine.positions) > 0:
            return OrderType.SELL, f"Breakdown below ${lower_band:.0f}"

        return OrderType.HOLD, f"Price in range ${lower_band:.0f}-${upper_band:.0f}"


# ============================================================================
# EXAMPLE 6: Example Agent Function (for agent_backtest)
# ============================================================================

def example_agent_function(timestamp, row):
    """
    Example agent function that returns AgentDecision.
    This would be replaced by actual agent calls.
    """
    price = row['close']

    # Simple logic for demonstration
    if price < 40000:
        return AgentDecision(
            signal="BUY",
            confidence=0.8,
            reasoning="Price below key support at $40k. Strong buying opportunity."
        )
    elif price > 48000:
        return AgentDecision(
            signal="SELL",
            confidence=0.75,
            reasoning="Price approaching resistance at $48k. Take profits."
        )
    else:
        return AgentDecision(
            signal="HOLD",
            confidence=0.6,
            reasoning="Price in consolidation range. Wait for clearer signal."
        )


# ============================================================================
# RUNNING EXAMPLES
# ============================================================================

def run_example_backtest():
    """Run example backtests with different strategies."""
    print("\n" + "=" * 80)
    print("  CRYPTO BACKTESTING EXAMPLES")
    print("=" * 80)

    # Setup
    print("\n📊 Setting up backtest environment...")
    engine = CryptoBacktestEngine(initial_capital=10000)
    loader = CryptoDataLoader(exchange_id='binance')
    evaluator = CryptoStrategyEvaluator(engine, loader)

    print("✅ Environment ready\n")

    # Define test period
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 6, 1)
    symbol = 'BTC/USDT'

    print(f"Backtest Configuration:")
    print(f"  Symbol: {symbol}")
    print(f"  Period: {start_date.date()} to {end_date.date()}")
    print(f"  Initial Capital: ${engine.initial_capital:,.2f}")
    print(f"  Commission: {engine.commission_rate:.2%}")
    print(f"  Slippage: {engine.slippage_rate:.2%}\n")

    # Available strategies
    strategies = {
        '1. Buy and Hold': buy_and_hold_strategy,
        '2. MA Crossover (50/200)': MovingAverageCrossover(50, 200),
        '3. RSI Mean Reversion': RSIMeanReversion(14, 30, 70),
        '4. Simulated Agent': simulated_agent_strategy,
        '5. Volatility Breakout': VolatilityBreakout(20, 2.0),
    }

    print("📋 Available Strategies:")
    for name in strategies.keys():
        print(f"   {name}")

    print("\nℹ️  To run full backtest with real data:")
    print("   1. Ensure CCXT is installed: pip install ccxt")
    print("   2. Ensure internet connection")
    print("   3. Run: evaluator.run_backtest(symbol, start_date, end_date, strategy)")

    print("\n✅ Example strategies loaded and ready to test\n")


if __name__ == "__main__":
    run_example_backtest()
