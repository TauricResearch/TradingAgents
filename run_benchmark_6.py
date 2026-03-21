import pandas as pd
import yfinance as yf
import time
import os

start_date_str = '2020-01-01'
end_date_str = '2023-01-01'
symbol = 'AAPL'

data_file = "test_cache.csv"

start_t = time.time()
data = yf.download(
    symbol,
    start=start_date_str,
    end=end_date_str,
    multi_level_index=False,
    progress=False,
    auto_adjust=True,
)
data = data.reset_index()
# To mimic the current iteration dataframe creation, actually what does it mean?
# "DataFrame creation from iteration"
# If I do `data.to_csv(data_file, index=False)`
# It creates a file.
# Is the iteration about reading back from yf.download()? Wait...
