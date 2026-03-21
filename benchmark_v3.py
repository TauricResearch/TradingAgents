import yfinance as yf
import pandas as pd
import time
import os

symbol = 'AAPL'
start_date_str = '2020-01-01'
end_date_str = '2023-01-01'

# The issue description says:
# Missing optimization on DataFrame creation from iteration
# It's generally recommended to pass data structures optimally when generating Pandas dataframes to avoid overhead.
