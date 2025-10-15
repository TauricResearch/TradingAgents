"""
24/7 Crypto Trading Bot
Production deployment for continuous paper trading
"""
import sys
import os

# Add project root to path (go up 3 levels: scripts -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from crypto_trading.src.paper_trading.paper_trading_engine import PaperTradingEngine, OrderSide
from crypto_trading.src.paper_trading.dashboard import PaperTradingDashboard
from crypto_trading.src.paper_trading.bot_manager import BotManager


# ============================================================================
# PRODUCTION STRATEGY
# ============================================================================

class MultiIndicatorStrategy:
    """
    Production-grade multi-indicator strategy.

    Combines:
    - Moving average crossover
    - RSI oversold/overbought
    - Volume confirmation
    """

    def __init__(
        self,
        short_window: int = 20,
        long_window: int = 50,
        rsi_period: int = 14,
        rsi_oversold: int = 30,
        rsi_overbought: int = 70
    ):
        self.short_window = short_window
        self.long_window = long_window
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

        # Price history
        self.price_history = {}

    def calculate_rsi(self, prices):
        """Calculate RSI."""
        if len(prices) < self.rsi_period + 1:
            return 50

        gains = []
        losses = []

        for i in range(1, self.rsi_period + 1):
            change = prices[-i] - prices[-i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / self.rsi_period
        avg_loss = sum(losses) / self.rsi_period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def __call__(self, engine, symbol, current_price):
        """Execute strategy."""
        # Initialize history
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(current_price)

        # Keep needed history
        if len(self.price_history[symbol]) > self.long_window + 10:
            self.price_history[symbol] = self.price_history[symbol][-(self.long_window + 10):]

        # Need enough data
        if len(self.price_history[symbol]) < self.long_window:
            return None

        prices = self.price_history[symbol]

        # Calculate indicators
        short_ma = sum(prices[-self.short_window:]) / self.short_window
        long_ma = sum(prices[-self.long_window:]) / self.long_window
        rsi = self.calculate_rsi(prices)

        # BUY CONDITIONS
        # 1. Golden cross (short MA > long MA)
        # 2. RSI oversold
        # 3. No existing position
        if (short_ma > long_ma and
            rsi < self.rsi_oversold and
            symbol not in engine.positions):
            return OrderSide.BUY

        # SELL CONDITIONS
        # 1. Death cross (short MA < long MA) OR
        # 2. RSI overbought
        # 3. Have existing position
        if symbol in engine.positions:
            if short_ma < long_ma or rsi > self.rsi_overbought:
                return OrderSide.SELL

        return None


# ============================================================================
# CONFIGURATION
# ============================================================================

BOT_CONFIG = {
    # Engine settings
    'exchange_id': 'binance',
    'initial_capital': 10000,
    'commission_rate': 0.001,
    'max_position_size': 0.15,      # 15% per position
    'max_daily_loss': 0.05,         # 5% daily loss limit
    'stop_loss_pct': 0.10,          # 10% stop loss
    'take_profit_pct': 0.25,        # 25% take profit
    'update_interval': 60,          # 60 second updates

    # Bot manager settings
    'max_retries': 10,
    'retry_delay': 300,             # 5 minutes
    'health_check_interval': 300,   # 5 minutes
    'daily_report_time': '00:00',   # Midnight UTC

    # Trading symbols
    'symbols': ['BTC/USDT', 'ETH/USDT', 'BNB/USDT'],

    # Strategy settings
    'strategy': {
        'short_window': 20,
        'long_window': 50,
        'rsi_period': 14,
        'rsi_oversold': 30,
        'rsi_overbought': 70,
    }
}


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run 24/7 crypto trading bot."""
    print("\n" + "="*80)
    print("  24/7 CRYPTO PAPER TRADING BOT")
    print("="*80)
    print("\nProduction-grade paper trading bot for continuous operation.")
    print("\nConfiguration:")
    print(f"  Exchange:          {BOT_CONFIG['exchange_id']}")
    print(f"  Symbols:           {', '.join(BOT_CONFIG['symbols'])}")
    print(f"  Initial Capital:   ${BOT_CONFIG['initial_capital']:,.2f}")
    print(f"  Update Interval:   {BOT_CONFIG['update_interval']}s")
    print(f"  Max Position Size: {BOT_CONFIG['max_position_size']:.1%}")
    print(f"  Stop Loss:         {BOT_CONFIG['stop_loss_pct']:.1%}")
    print(f"  Take Profit:       {BOT_CONFIG['take_profit_pct']:.1%}")
    print(f"  Daily Loss Limit:  {BOT_CONFIG['max_daily_loss']:.1%}")
    print("\nStrategy:")
    print(f"  Type:              Multi-Indicator (MA + RSI)")
    print(f"  MA Short/Long:     {BOT_CONFIG['strategy']['short_window']}/{BOT_CONFIG['strategy']['long_window']}")
    print(f"  RSI Period:        {BOT_CONFIG['strategy']['rsi_period']}")
    print("\nFeatures:")
    print("  ✓ 24/7 operation")
    print("  ✓ Automatic error recovery")
    print("  ✓ Health monitoring")
    print("  ✓ Daily reports")
    print("  ✓ Graceful shutdown (Ctrl+C)")
    print("\nData:")
    print("  Logs:              ./logs/")
    print("  Trading Data:      ./paper_trading_data/")
    print()

    input("Press Enter to start bot...")

    # Create engine
    engine = PaperTradingEngine(
        exchange_id=BOT_CONFIG['exchange_id'],
        initial_capital=BOT_CONFIG['initial_capital'],
        commission_rate=BOT_CONFIG['commission_rate'],
        max_position_size=BOT_CONFIG['max_position_size'],
        max_daily_loss=BOT_CONFIG['max_daily_loss'],
        stop_loss_pct=BOT_CONFIG['stop_loss_pct'],
        take_profit_pct=BOT_CONFIG['take_profit_pct'],
        update_interval=BOT_CONFIG['update_interval'],
        data_dir="./paper_trading_data"
    )

    # Create dashboard
    dashboard = PaperTradingDashboard(engine)

    # Create strategy
    strategy = MultiIndicatorStrategy(**BOT_CONFIG['strategy'])
    engine.set_strategy(strategy)

    # Create bot manager
    bot_manager = BotManager(
        engine=engine,
        dashboard=dashboard,
        max_retries=BOT_CONFIG['max_retries'],
        retry_delay=BOT_CONFIG['retry_delay'],
        health_check_interval=BOT_CONFIG['health_check_interval'],
        daily_report_time=BOT_CONFIG['daily_report_time'],
        log_dir="./logs"
    )

    # Start bot
    print("\n🚀 Starting bot...\n")
    bot_manager.start(BOT_CONFIG['symbols'])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nShutdown requested by user...")
        sys.exit(0)
    except Exception as e:
        print(f"\n🚨 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
