"""JSON-based portfolio persistence."""

import json
import os
from dataclasses import asdict
from typing import Optional

from tradingagents.portfolio.state import (
    ClosedTrade,
    Order,
    PortfolioState,
    Position,
)


def _get_portfolio_path(portfolio_id: str, results_dir: str = "./results") -> str:
    portfolio_dir = os.path.join(results_dir, "portfolios")
    os.makedirs(portfolio_dir, exist_ok=True)
    return os.path.join(portfolio_dir, f"{portfolio_id}.json")


def save_portfolio(portfolio: PortfolioState, results_dir: str = "./results") -> str:
    """Save portfolio state to JSON file. Returns the file path."""
    path = _get_portfolio_path(portfolio.portfolio_id, results_dir)
    data = asdict(portfolio)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_portfolio(
    portfolio_id: str = "default",
    results_dir: str = "./results",
    defaults: Optional[dict] = None,
) -> PortfolioState:
    """Load portfolio state from JSON file. Creates new if not found."""
    path = _get_portfolio_path(portfolio_id, results_dir)

    if not os.path.exists(path):
        kwargs = {"portfolio_id": portfolio_id}
        if defaults:
            kwargs.update(defaults)
        return PortfolioState(**kwargs)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Reconstruct nested dataclasses
    positions = {}
    for ticker, pos_data in data.get("positions", {}).items():
        positions[ticker] = Position(**pos_data)

    closed_trades = [
        ClosedTrade(**t) for t in data.get("closed_trades", [])
    ]

    orders_history = [
        Order(**o) for o in data.get("orders_history", [])
    ]

    return PortfolioState(
        portfolio_id=data.get("portfolio_id", portfolio_id),
        total_capital=data.get("total_capital", 100_000_000),
        available_capital=data.get("available_capital", 100_000_000),
        max_positions=data.get("max_positions", 5),
        max_position_pct=data.get("max_position_pct", 0.20),
        positions=positions,
        closed_trades=closed_trades,
        orders_history=orders_history,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )
