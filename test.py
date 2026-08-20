import time

from tradingagents.dataflows.y_finance import (
    get_stock_stats_indicators_window,
)

print("Testing optimized implementation with 30-day lookback:")
start_time = time.time()
result = get_stock_stats_indicators_window("THYAO.IS", "macd", "2026-08-20", 30)
end_time = time.time()

print(f"Execution time: {end_time - start_time:.2f} seconds")
print(f"Result length: {len(result)} characters")
print(result)
