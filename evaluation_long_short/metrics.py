"""
Evaluation metrics for trading strategies.
Implements: Cumulative Return, Annualized Return, Sharpe Ratio, Maximum Drawdown
"""

import pandas as pd
import numpy as np
from typing import Dict


def _require_cols(df: pd.DataFrame, cols):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Portfolio missing columns: {missing}")


def calculate_cumulative_return(portfolio: pd.DataFrame) -> float:
    """CR% = (V_end / V_start - 1) * 100"""
    _require_cols(portfolio, ["portfolio_value"])
    v_start = float(portfolio["portfolio_value"].iloc[0])
    v_end = float(portfolio["portfolio_value"].iloc[-1])
    if v_start <= 0:
        return 0.0
    return (v_end / v_start - 1.0) * 100.0


def calculate_annualized_return(portfolio: pd.DataFrame, trading_days: int | None = None) -> float:
    """AR% = ((V_end / V_start) ** (1/years) - 1) * 100 with 252 trading days/year."""
    _require_cols(portfolio, ["portfolio_value"])
    v_start = float(portfolio["portfolio_value"].iloc[0])
    v_end = float(portfolio["portfolio_value"].iloc[-1])
    if v_start <= 0 or v_end <= 0:
        return 0.0
    if trading_days is None:
        trading_days = len(portfolio)
    years = trading_days / 252.0
    if years <= 0:
        return 0.0
    return ((v_end / v_start) ** (1.0 / years) - 1.0) * 100.0


def calculate_sharpe_ratio(portfolio: pd.DataFrame, risk_free_rate: float = 0.02) -> float:
    """
    SR = (E[r] - r_f) / stdev(r), where r are *daily* strategy returns,
    annualized using 252 trading days (paper S1.2.3).
    """
    _require_cols(portfolio, ["strategy_return"])
    r = portfolio["strategy_return"].dropna().astype(float)
    if len(r) < 2 or r.std() == 0:
        return 0.0
    mean_ann = r.mean() * 252.0
    std_ann = r.std(ddof=1) * np.sqrt(252.0)
    if std_ann == 0:
        return 0.0
    return (mean_ann - risk_free_rate) / std_ann


def calculate_maximum_drawdown(portfolio: pd.DataFrame) -> float:
    """MDD% = max drawdown on portfolio_value (peak->trough) * 100"""
    _require_cols(portfolio, ["portfolio_value"])
    values = portfolio["portfolio_value"].astype(float)
    running_max = values.cummax()
    drawdown = (values - running_max) / running_max
    return float(drawdown.min() * -100.0)


def calculate_win_rate(portfolio: pd.DataFrame) -> float:
    """% days where strategy_return > 0"""
    _require_cols(portfolio, ["strategy_return"])
    r = portfolio["strategy_return"].dropna()
    if len(r) == 0:
        return 0.0
    return 100.0 * (r > 0).sum() / len(r)


def calculate_profit_factor(portfolio: pd.DataFrame) -> float:
    """Gross profit / gross loss on daily returns (informative extra metric)."""
    _require_cols(portfolio, ["strategy_return"])
    r = portfolio["strategy_return"].dropna()
    gp = r[r > 0].sum()
    gl = -r[r < 0].sum()
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return float(gp / gl)


def calculate_all_metrics(portfolio: pd.DataFrame, risk_free_rate: float = 0.02) -> Dict[str, float]:
    return {
        "Cumulative Return (%)": calculate_cumulative_return(portfolio),
        "Annualized Return (%)": calculate_annualized_return(portfolio),
        "Sharpe Ratio": calculate_sharpe_ratio(portfolio, risk_free_rate),
        "Maximum Drawdown (%)": calculate_maximum_drawdown(portfolio),
        # Extras (not in table but handy)
        "Win Rate (%)": calculate_win_rate(portfolio),
        "Profit Factor": calculate_profit_factor(portfolio),
    }


def print_metrics(metrics: Dict[str, float], strategy_name: str = "Strategy"):
    print(f"\n{'='*60}")
    print(f"{strategy_name} Performance Metrics")
    print(f"{'='*60}")
    for k, v in metrics.items():
        if "Ratio" in k or "Factor" in k:
            print(f"{k:30s}: {v:8.2f}")
        else:
            print(f"{k:30s}: {v:8.2f}%")
    print(f"{'='*60}\n")


def create_comparison_table(all_metrics: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame(all_metrics).T
    df = df.round(2)
    if "Sharpe Ratio" in df.columns:
        df = df.sort_values("Sharpe Ratio", ascending=False)
    return df
