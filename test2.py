import pandas as pd
import yfinance as yf
data = yf.download(
    "AAPL",
    start="2020-01-01",
    end="2023-01-01",
    multi_level_index=False,
    progress=False,
    auto_adjust=True,
)
print("Columns before reset_index:", data.columns)
data = data.reset_index()
print("Columns after reset_index:", data.columns)
