from __future__ import annotations

import argparse
import json
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


RATING_TO_EXPOSURE = {
    "BUY": 1.0,
    "OVERWEIGHT": 0.5,
    "HOLD": 0.0,
    "UNDERWEIGHT": -0.5,
    "SELL": -1.0,
    "NO_TRADE": 0.0,
}


def _fetch_forward_return(symbol: str, trade_date: str, holding_period: int) -> float | None:
    start_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    end_dt = start_dt + timedelta(days=max(holding_period * 3, 10))
    history = yf.Ticker(symbol).history(start=trade_date, end=end_dt.strftime("%Y-%m-%d"))
    if history.empty or "Close" not in history:
        return None

    closes = history["Close"].dropna()
    if len(closes) < 2:
        return None

    entry_price = float(closes.iloc[0])
    exit_index = min(holding_period, len(closes) - 1)
    exit_price = float(closes.iloc[exit_index])
    return (exit_price / entry_price) - 1.0


def _compute_max_drawdown(returns: Iterable[float]) -> float:
    cumulative = pd.Series(list(returns)).fillna(0.0).add(1.0).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative / running_max) - 1.0
    return float(drawdown.min()) if not drawdown.empty else 0.0


def run_walk_forward_evaluation(
    symbols: list[str],
    trade_dates: list[str],
    *,
    holding_period: int = 5,
    benchmark_symbol: str = "SPY",
    graph_config: dict | None = None,
    selected_analysts: list[str] | None = None,
    enable_reflection: bool = False,
) -> dict:
    config = deepcopy(graph_config or DEFAULT_CONFIG)
    graph = TradingAgentsGraph(
        config=config,
        selected_analysts=selected_analysts or ["market", "social", "news", "fundamentals"],
    )

    records: list[dict] = []
    previous_exposure = 0.0

    for trade_date in trade_dates:
        benchmark_return = _fetch_forward_return(benchmark_symbol, trade_date, holding_period)
        for symbol in symbols:
            final_state, rating = graph.propagate(symbol, trade_date)
            asset_return = _fetch_forward_return(final_state["company_of_interest"], trade_date, holding_period)
            if asset_return is None:
                continue

            exposure = RATING_TO_EXPOSURE.get(rating, 0.0)
            strategy_return = exposure * asset_return
            turnover = abs(exposure - previous_exposure)
            previous_exposure = exposure

            if enable_reflection:
                graph.reflect_and_remember(strategy_return)

            country = (final_state.get("instrument_profile") or {}).get("country", "UNKNOWN")
            records.append(
                {
                    "symbol": final_state["company_of_interest"],
                    "input_instrument": final_state.get("input_instrument", symbol),
                    "country": country,
                    "trade_date": trade_date,
                    "rating": rating,
                    "asset_return": asset_return,
                    "strategy_return": strategy_return,
                    "benchmark_return": benchmark_return,
                    "excess_return": None if benchmark_return is None else strategy_return - benchmark_return,
                    "turnover": turnover,
                }
            )

    if not records:
        return {"records": [], "metrics": {}}

    df = pd.DataFrame(records)
    bucket_metrics = df.groupby("rating")["asset_return"].mean().to_dict()
    region_metrics = (
        df.groupby("country")["strategy_return"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "avg_strategy_return"})
        .to_dict(orient="index")
    )

    metrics = {
        "hit_rate": float((df["strategy_return"] > 0).mean()),
        "forward_return_by_rating_bucket": bucket_metrics,
        "turnover": float(df["turnover"].mean()),
        "max_drawdown": _compute_max_drawdown(df["strategy_return"].tolist()),
        "benchmark_excess_return": float(df["excess_return"].dropna().mean()) if df["excess_return"].notna().any() else None,
        "abstain_frequency": float((df["rating"] == "NO_TRADE").mean()),
        "region_split_metrics": region_metrics,
    }
    return {"records": records, "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description="Run a simple walk-forward evaluation for TradingAgents.")
    parser.add_argument("--symbols", nargs="+", required=True, help="Instrument inputs, such as AAPL or 005930")
    parser.add_argument("--trade-dates", nargs="+", required=True, help="Trade dates in YYYY-MM-DD format")
    parser.add_argument("--holding-period", type=int, default=5, help="Forward holding period in trading days")
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker for excess-return comparison")
    parser.add_argument("--enable-reflection", action="store_true", help="Call reflect_and_remember after each evaluated trade")
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    result = run_walk_forward_evaluation(
        symbols=args.symbols,
        trade_dates=args.trade_dates,
        holding_period=args.holding_period,
        benchmark_symbol=args.benchmark,
        enable_reflection=args.enable_reflection,
    )

    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
