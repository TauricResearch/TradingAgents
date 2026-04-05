import time
from tradingagents.dataflows.binance import get_binance_klines, get_binance_indicators_window

print("Testing Binance klines:")
start = time.time()
result = get_binance_klines("BTCUSDT", "2024-10-01", "2024-11-01")
print(f"Execution time: {time.time() - start:.2f}s")
print(f"Result length: {len(result)} characters")
print(result[:500])

print("\nTesting Binance indicators (MACD, 30-day lookback):")
start = time.time()
result = get_binance_indicators_window("BTCUSDT", "macd", "2024-11-01", 30)
print(f"Execution time: {time.time() - start:.2f}s")
print(result)
