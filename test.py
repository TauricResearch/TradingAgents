import time
from tradingagents.dataflows.y_finance import get_YFin_data_online, get_stock_stats_indicators_window, get_balance_sheet as get_yfinance_balance_sheet, get_cashflow as get_yfinance_cashflow, get_income_statement as get_yfinance_income_statement, get_insider_transactions as get_yfinance_insider_transactions

print("Testing optimized implementation with 30-day lookback:")
start_time = time.time()
result = get_stock_stats_indicators_window("AAPL", "macd", "2024-11-01", 30)
end_time = time.time()

print(f"Execution time: {end_time - start_time:.2f} seconds")
print(f"Result length: {len(result)} characters")
print(result)
