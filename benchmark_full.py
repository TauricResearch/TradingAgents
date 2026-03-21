import pandas as pd
import yfinance as yf
import os
import time
from typing import Annotated

# Let's mock _clean_dataframe
def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    df = data.copy()
    df.columns = [str(c).lower() for c in df.columns]

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])

    price_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    if price_cols:
        df[price_cols] = df[price_cols].apply(pd.to_numeric, errors="coerce")

    if "close" in df.columns:
        df = df.dropna(subset=["close"])

    if price_cols:
        df[price_cols] = df[price_cols].ffill().bfill()

    return df

def _clean_dataframe_optimized(data: pd.DataFrame) -> pd.DataFrame:
    df = data.copy()
    df.columns = df.columns.astype(str).str.lower()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])

    price_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    if price_cols:
        df[price_cols] = df[price_cols].apply(pd.to_numeric, errors="coerce")

    if "close" in df.columns:
        df = df.dropna(subset=["close"])

    if price_cols:
        df[price_cols] = df[price_cols].ffill().bfill()

    return df

start_date_str = '2020-01-01'
end_date_str = '2023-01-01'
symbol = 'AAPL'

data = yf.download(
    symbol,
    start=start_date_str,
    end=end_date_str,
    multi_level_index=False,
    progress=False,
    auto_adjust=True,
)
data = data.reset_index()

import time

iterations = 100

start = time.time()
for _ in range(iterations):
    _ = _clean_dataframe(data)
t1 = time.time() - start

start = time.time()
for _ in range(iterations):
    _ = _clean_dataframe_optimized(data)
t2 = time.time() - start

print(f"Original _clean_dataframe: {t1:.4f} s")
print(f"Optimized _clean_dataframe: {t2:.4f} s")
