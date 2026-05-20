#!/usr/bin/env python3
"""
compute_pattern_features.py — STL decomposition + 7 structural features.

Reads OHLCV from the prices table (via SQLite), applies STL decomposition,
computes 7 features from the TIME benchmark paper (arXiv:2602.12147), and
writes results as JSON to stdout.

Usage:
  python scripts/py/compute_pattern_features.py AAPL [--db portfolio.db]

Features:
  trend_strength       — ratio of trend variability to total
  trend_linearity      — linear regression R² on trend component
  seasonality_strength — ratio of seasonal variability to total
  seasonality_stability— ACF of seasonal component at period lag
  residual_acf1        — first-order autocorrelation of remainder
  spectral_entropy     — spectral entropy of returns (FFT-based)
  is_stationary        — 1 if ADF p-value < 0.05, 0 otherwise
"""

import json
import sqlite3
import sys
import warnings
from math import log2

import numpy as np
from scipy import stats
from scipy.fft import fft

warnings.filterwarnings("ignore", category=FutureWarning)


def get_price_history(db_path: str, ticker: str, min_bars: int = 252) -> list[float]:
    """Fetch close prices from the prices table, sorted by date ascending."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT close FROM prices WHERE ticker = ? ORDER BY date ASC",
        (ticker,),
    )
    rows = cursor.fetchall()
    conn.close()

    if len(rows) < min_bars:
        raise ValueError(
            f"Insufficient price history for {ticker}: {len(rows)} bars (need {min_bars})"
        )

    return [float(r[0]) for r in rows[-min_bars:]]


def stl_decompose(series: np.ndarray, period: int = 21) -> dict[str, np.ndarray]:
    """Decompose series into trend, seasonal, and residual using STL."""
    from statsmodels.tsa.seasonal import STL

    stl = STL(series, period=period, seasonal=13, robust=True)
    result = stl.fit()
    return {
        "trend": result.trend,
        "seasonal": result.seasonal,
        "residual": result.resid,
    }


def compute_trend_strength(trend: np.ndarray, seasonal: np.ndarray, residual: np.ndarray) -> float:
    """Ratio of trend variance to total variance (after removing seasonal)."""
    detrended = seasonal + residual
    var_trend = float(np.var(trend))
    var_detrended = float(np.var(detrended))
    total = var_trend + var_detrended
    return var_trend / total if total > 0 else 0.0


def compute_trend_linearity(trend: np.ndarray) -> float:
    """R² of linear regression on the trend component."""
    x = np.arange(len(trend))
    mask = ~np.isnan(trend)
    if mask.sum() < 3:
        return 0.0
    slope, intercept, r_value, _p_value, _std_err = stats.linregress(x[mask], trend[mask])
    return float(r_value**2)


def compute_seasonality_strength(
    seasonal: np.ndarray, trend: np.ndarray, residual: np.ndarray
) -> float:
    """Ratio of seasonal variance to total variance (after removing trend)."""
    detrended_seasonal = trend + residual
    var_seasonal = float(np.var(seasonal))
    var_other = float(np.var(detrended_seasonal))
    total = var_seasonal + var_other
    return var_seasonal / total if total > 0 else 0.0


def compute_seasonality_stability(seasonal: np.ndarray, period: int = 21) -> float:
    """Autocorrelation of the seasonal component at the period lag."""
    if len(seasonal) <= period:
        return 0.0
    mask = ~np.isnan(seasonal)
    clean = seasonal[mask]
    if len(clean) <= period:
        return 0.0
    # ACF at lag = period
    x = clean[:-period]
    y = clean[period:]
    if len(x) < 3:
        return 0.0
    corr, _p = stats.pearsonr(x, y)
    return float(corr)


def compute_residual_acf1(residual: np.ndarray) -> float:
    """First-order autocorrelation of the residual component."""
    mask = ~np.isnan(residual)
    clean = residual[mask]
    if len(clean) < 3:
        return 0.0
    x = clean[:-1]
    y = clean[1:]
    corr, _p = stats.pearsonr(x, y)
    return float(corr)


def compute_spectral_entropy(prices: np.ndarray) -> float:
    """Spectral entropy of log returns via FFT."""
    log_returns = np.diff(np.log(prices))
    log_returns = log_returns[~np.isnan(log_returns)]

    if len(log_returns) < 4:
        return 0.0

    spectrum = np.abs(fft(log_returns)) ** 2
    # Use positive frequencies only, excluding DC
    pos_spectrum = spectrum[1 : len(spectrum) // 2 + 1]
    total = pos_spectrum.sum()
    if total == 0:
        return 0.0

    probs = pos_spectrum / total
    probs = probs[probs > 0]  # avoid log(0)
    entropy = -np.sum(probs * np.log2(probs))
    # Normalize by max entropy (uniform distribution)
    max_entropy = log2(len(probs))
    return float(entropy / max_entropy) if max_entropy > 0 else 0.0


def compute_adf_stationarity(prices: np.ndarray, alpha: float = 0.05) -> int:
    """Augmented Dickey-Fuller test. Returns 1 if stationary (p < alpha)."""
    from statsmodels.tsa.stattools import adfuller

    log_prices = np.log(prices)
    log_prices = log_prices[~np.isnan(log_prices)]

    if len(log_prices) < 20:
        return 0

    try:
        result = adfuller(log_prices, maxlag=min(20, len(log_prices) // 4))
        p_value = float(result[1])
        return 1 if p_value < alpha else 0
    except Exception:
        return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: compute_pattern_features.py TICKER [--db path/to/db]", file=sys.stderr)
        sys.exit(1)

    ticker = sys.argv[1]
    db_path = "portfolio.db"

    for i, arg in enumerate(sys.argv):
        if arg == "--db" and i + 1 < len(sys.argv):
            db_path = sys.argv[i + 1]

    try:
        prices = get_price_history(db_path, ticker)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    prices_arr = np.array(prices, dtype=np.float64)

    # STL decomposition (21-day period = ~monthly cycle)
    components = stl_decompose(prices_arr, period=21)

    features = {
        "trend_strength": round(compute_trend_strength(components["trend"], components["seasonal"], components["residual"]), 6),
        "trend_linearity": round(compute_trend_linearity(components["trend"]), 6),
        "seasonality_strength": round(compute_seasonality_strength(components["seasonal"], components["trend"], components["residual"]), 6),
        "seasonality_stability": round(compute_seasonality_stability(components["seasonal"], period=21), 6),
        "residual_acf1": round(compute_residual_acf1(components["residual"]), 6),
        "spectral_entropy": round(compute_spectral_entropy(prices_arr), 6),
        "is_stationary": compute_adf_stationarity(prices_arr),
    }

    print(json.dumps(features))


if __name__ == "__main__":
    main()
