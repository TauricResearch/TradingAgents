"""Backtest metrics: hit rate, edge calibration, growth-rate Sharpe-ish.

Designed to be cheap to recompute as the analyst prompts evolve. All
metrics take a list of ``BacktestRecord`` rows; aggregating happens in
pandas so the same shape works for both single-run and grid-sweep
analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional

import pandas as pd


@dataclass
class BacktestRecord:
    contract_id: str
    decision_date: str
    side: str  # YES / NO / PASS
    p_yes_committee: float
    p_yes_market: float
    edge_bps: float
    confidence: str
    kelly_fraction: float
    stake_usd: float
    settlement_outcome: str  # YES / NO
    realized_pnl_usd: float


def to_df(records: Iterable[BacktestRecord]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in records])


def hit_rate(df: pd.DataFrame) -> float:
    """Share of executed trades that paid out (excluding PASS rows)."""
    executed = df[df["side"] != "PASS"]
    if executed.empty:
        return float("nan")
    wins = (executed["side"] == executed["settlement_outcome"]).sum()
    return float(wins) / len(executed)


def total_pnl_usd(df: pd.DataFrame) -> float:
    return float(df["realized_pnl_usd"].sum())


def kelly_growth_rate(df: pd.DataFrame) -> float:
    """Continuous compounding growth rate: sum(log(1 + return_per_trade)).

    Returns are computed as ``realized_pnl_usd / stake_usd`` for executed
    trades; PASS rows contribute zero. A negative growth rate means the
    sequence eroded bankroll regardless of any individual win streak.
    """
    executed = df[(df["side"] != "PASS") & (df["stake_usd"] > 0)]
    if executed.empty:
        return float("nan")
    rates = executed["realized_pnl_usd"] / executed["stake_usd"]
    rates = rates.where(rates > -1, -0.999999)  # guard log domain
    return float((1 + rates).map(math.log).sum())


def calibration(df: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    """Edge-calibration table: does committee p_yes match realized win rate?

    For each probability bin (e.g. p_yes ∈ [0.55, 0.60)), reports:
      - n_trades
      - mean_p_yes (committee's average estimate)
      - empirical_win_rate (share that resolved in the predicted direction)

    A well-calibrated committee has ``empirical_win_rate ≈ mean_p_yes``
    in every bin (or more precisely: equal to the predicted side
    probability — for NO trades, the predicted probability is 1 - p_yes).
    """
    executed = df[df["side"] != "PASS"].copy()
    if executed.empty:
        return pd.DataFrame(columns=["bin", "n_trades", "mean_p_predicted", "empirical_win_rate"])

    executed["p_predicted"] = executed.apply(
        lambda r: r["p_yes_committee"] if r["side"] == "YES" else (1 - r["p_yes_committee"]),
        axis=1,
    )
    executed["won"] = executed["side"] == executed["settlement_outcome"]

    edges = [i / bins for i in range(bins + 1)]
    executed["bin"] = pd.cut(executed["p_predicted"], bins=edges, include_lowest=True)
    grouped = (
        executed.groupby("bin", observed=False)
        .agg(n_trades=("won", "size"),
             mean_p_predicted=("p_predicted", "mean"),
             empirical_win_rate=("won", "mean"))
        .reset_index()
    )
    return grouped


def summary(df: pd.DataFrame) -> dict:
    """Top-line summary used by the sweep runner / CLI."""
    executed = df[df["side"] != "PASS"]
    return {
        "n_decisions": int(len(df)),
        "n_executed": int(len(executed)),
        "n_passed": int(len(df) - len(executed)),
        "hit_rate": hit_rate(df),
        "total_pnl_usd": total_pnl_usd(df),
        "kelly_growth_rate": kelly_growth_rate(df),
    }
