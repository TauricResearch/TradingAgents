"""Quick dashboard test"""
import os
import sys

# Add project root to path (go up 3 levels: scripts -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from crypto_trading.src.paper_trading.paper_trading_engine import PaperTradingEngine, OrderSide
from crypto_trading.src.paper_trading.dashboard import PaperTradingDashboard

# Create engine
engine = PaperTradingEngine(initial_capital=10000, data_dir='./test_dashboard')

# Simulate some trading
engine.current_prices = {'BTC/USDT': 50000, 'ETH/USDT': 3000}
engine._place_buy_order('BTC/USDT', 50000, 'Test buy')
engine._place_buy_order('ETH/USDT', 3000, 'Test buy')

# Update prices (profitable)
engine.current_prices = {'BTC/USDT': 52000, 'ETH/USDT': 3100}
engine._update_portfolio_value()

# Sell one position
engine._place_sell_order('BTC/USDT', 52000, 'Test sell')

# Create dashboard
dashboard = PaperTradingDashboard(engine)

# Print status
dashboard.print_live_status()

# Get metrics
metrics = dashboard.get_performance_metrics()
print(f'\n✓ Dashboard test passed')
print(f'✓ Total return: {metrics["total_return"]:.2%}')
print(f'✓ Total trades: {metrics["total_trades"]}')
print(f'✓ Win rate: {metrics["win_rate_pct"]:.1f}%')

print('\n✓ All dashboard features working!')
