"""Reproducible backtest / evaluation harness for the TradingAgents graph.

The paper (arXiv:2412.20138) evaluates TradingAgents over historical
windows, but the repository ships no tool to reproduce that evaluation
(see upstream issues #119 and #1222). This module runs the full graph over
a ticker x date grid, records each run's 5-tier rating, resolves the
realized return and alpha vs the regional benchmark (reusing
``TradingAgentsGraph._fetch_returns``), and summarises directional
accuracy and rating distribution.

Design notes:
- The memory log is disabled by default so a backtest neither pollutes the
  persistent decision log nor spends extra LLM calls on deferred
  reflections; pass a config with ``memory_log_path`` to opt back in.
- A single (ticker, date) failure is recorded as an ERROR row and skipped;
  the rest of the grid still runs.
- LLM calls dominate cost: keep the grid small or use a cheap quick model
  (see ``scripts/backtest.py --help``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

RATINGS_ORDER = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
_LONG_RATINGS = {"Buy", "Overweight"}
_SHORT_RATINGS = {"Sell", "Underweight"}


def generate_dates(start: str, end: str, every_n_days: int = 7) -> list[str]:
    """Uniformly spaced calendar dates in [start, end], inclusive.

    Kept intentionally simple (no exchange-calendar logic): backtests on
    weekends/holidays simply resolve to the latest available trading row
    via the existing OHLCV loaders, so the grid can be any date step.
    """
    if every_n_days < 1:
        raise ValueError("every_n_days must be >= 1")
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    if end_dt < start_dt:
        raise ValueError(f"end ({end}) must not be before start ({start})")
    dates = []
    current = start_dt
    while current <= end_dt:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=every_n_days)
    return dates


def run_backtest(
    tickers: list[str],
    dates: list[str],
    config: dict | None = None,
    holding_days: int = 5,
    asset_type: str = "stock",
    save_dir: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """Run the full graph on a ticker x date grid and summarise outcomes.

    Args:
        tickers: Instruments to analyse (e.g. ``["NVDA", "AAPL"]``).
        dates: Analysis dates as ``YYYY-MM-DD`` strings.
        config: Optional ``TradingAgentsGraph`` config; ``memory_log_path``
            defaults to ``None`` (backtests stay out of the decision log).
        holding_days: Holding period used for realised-return resolution.
        asset_type: ``"stock"`` (default) or ``"crypto"``.
        save_dir: When set, writes ``backtest_results.csv`` and
            ``backtest_summary.md`` into this directory.

    Returns:
        ``(results_df, markdown_summary)``.
    """
    if config is None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["memory_log_path"] = None
    else:
        cfg = dict(config)
        cfg.setdefault("memory_log_path", None)

    graph = TradingAgentsGraph(config=cfg)
    rows: list[dict] = []
    for ticker in tickers:
        benchmark = graph._resolve_benchmark(ticker)
        for date in dates:
            try:
                _, rating = graph.propagate(ticker, date, asset_type=asset_type)
                raw, alpha, days = graph._fetch_returns(
                    ticker, date, holding_days=holding_days, benchmark=benchmark
                )
                rows.append({
                    "ticker": ticker,
                    "date": date,
                    "rating": rating,
                    "raw_return": raw,
                    "alpha_return": alpha,
                    "holding_days": days,
                    "error": "",
                })
            except Exception as exc:  # noqa: BLE001 - one bad cell must not sink the grid
                rows.append({
                    "ticker": ticker,
                    "date": date,
                    "rating": "ERROR",
                    "raw_return": None,
                    "alpha_return": None,
                    "holding_days": None,
                    "error": str(exc),
                })

    df = pd.DataFrame(rows)
    summary = summarize(df)
    if save_dir:
        out = Path(save_dir)
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / "backtest_results.csv", index=False)
        (out / "backtest_summary.md").write_text(summary, encoding="utf-8")
    return df, summary


def _directional_hit(rating: str, alpha) -> bool | None:
    """True when the rating's direction was right (long: alpha>0, short: alpha<0).

    Hold and unresolved rows contribute no directional signal.
    """
    if alpha is None or pd.isna(alpha):
        return None
    if rating in _LONG_RATINGS:
        return bool(alpha > 0)
    if rating in _SHORT_RATINGS:
        return bool(alpha < 0)
    return None


def summarize(df: pd.DataFrame) -> str:
    """Render a markdown summary: rating distribution and directional accuracy."""
    total = len(df)
    errors = int((df.get("rating") == "ERROR").sum()) if "rating" in df else 0
    outcome_rows = df[
        df["rating"].isin(RATINGS_ORDER) & df["alpha_return"].notna()
    ] if "alpha_return" in df else df.iloc[0:0]

    lines = [
        "# Backtest summary",
        "",
        f"- Runs: {total}",
        f"- Errors: {errors}",
        f"- Resolved outcomes (raw + alpha available): {len(outcome_rows)}",
        "",
        "## Rating distribution",
        "",
        "| Rating | Runs | % | Avg raw return | Avg alpha | Directional hit rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for rating in RATINGS_ORDER:
        group = outcome_rows[outcome_rows["rating"] == rating]
        if group.empty:
            continue
        hits = [_directional_hit(rating, a) for a in group["alpha_return"]]
        hit_rate = sum(1 for h in hits if h) / sum(1 for h in hits if h is not None) if any(h is not None for h in hits) else None
        lines.append(
            f"| {rating} | {len(group)} | {100 * len(group) / len(outcome_rows):.1f}% "
            f"| {group['raw_return'].mean():+.2%} | {group['alpha_return'].mean():+.2%} "
            f"| {f'{hit_rate:.0%}' if hit_rate is not None else 'n/a'} |"
        )

    if outcome_rows.empty:
        lines.append("| _(no resolved outcomes)_ | | | | | |")

    overall_hits = [
        h for _, row in outcome_rows.iterrows()
        for h in [_directional_hit(row["rating"], row["alpha_return"])] if h is not None
    ]
    overall_rate = sum(overall_hits) / len(overall_hits) if overall_hits else None

    lines += [
        "",
        "## Overall",
        "",
        f"- Mean raw return: {outcome_rows['raw_return'].mean():+.2%}" if len(outcome_rows) else "- Mean raw return: n/a",
        f"- Mean alpha: {outcome_rows['alpha_return'].mean():+.2%}" if len(outcome_rows) else "- Mean alpha: n/a",
        f"- Directional hit rate (long/short vs benchmark): {f'{overall_rate:.0%}' if overall_rate is not None else 'n/a'}",
        "",
        "> Directional hit rate: Buy/Overweight counts as a hit when alpha > 0;",
        "> Sell/Underweight when alpha < 0. Hold carries no directional signal.",
    ]
    return "\n".join(lines)
