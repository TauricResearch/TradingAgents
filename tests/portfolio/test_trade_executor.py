"""Tests for tradingagents/portfolio/trade_executor.py.

Uses MagicMock for PortfolioRepository — no DB connection required.

Run::

    pytest tests/portfolio/test_trade_executor.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from tradingagents.portfolio.models import Holding, Portfolio, PortfolioSnapshot
from tradingagents.portfolio.exceptions import (
    InsufficientCashError,
    InsufficientSharesError,
)
from tradingagents.portfolio.trade_executor import TradeExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_holding(ticker, shares=10.0, avg_cost=100.0, sector="Technology"):
    return Holding(
        holding_id="h-" + ticker,
        portfolio_id="p1",
        ticker=ticker,
        shares=shares,
        avg_cost=avg_cost,
        sector=sector,
    )


def _make_portfolio(cash=50_000.0, total_value=60_000.0):
    p = Portfolio(
        portfolio_id="p1",
        name="Test",
        cash=cash,
        initial_cash=100_000.0,
    )
    p.total_value = total_value
    p.equity_value = total_value - cash
    p.cash_pct = cash / total_value if total_value else 1.0
    return p


def _make_snapshot():
    return PortfolioSnapshot(
        snapshot_id="snap-1",
        portfolio_id="p1",
        snapshot_date="2026-01-01T00:00:00Z",
        total_value=60_000.0,
        cash=50_000.0,
        equity_value=10_000.0,
        num_positions=1,
        holdings_snapshot=[],
    )


def _make_repo(portfolio=None, holdings=None, snapshot=None):
    repo = MagicMock()
    repo.get_portfolio_with_holdings.return_value = (
        portfolio or _make_portfolio(),
        holdings or [],
    )
    repo.take_snapshot.return_value = snapshot or _make_snapshot()
    return repo


_DEFAULT_CONFIG = {
    "max_positions": 15,
    "max_position_pct": 0.15,
    "max_sector_pct": 0.35,
    "min_cash_pct": 0.05,
}

PRICES = {"AAPL": 150.0, "MSFT": 300.0}


# ---------------------------------------------------------------------------
# SELL tests
# ---------------------------------------------------------------------------


def test_execute_sell_success():
    """Successful SELL calls batch_remove_holdings and is in executed_trades."""
    repo = _make_repo()
    # Mock batch_remove_holdings to return a tuple of (executed, failed)
    repo.batch_remove_holdings.return_value = (
        [{"action": "SELL", "ticker": "AAPL", "shares": 5.0, "price": 150.0, "rationale": "Stop loss"}],
        []
    )
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [{"ticker": "AAPL", "shares": 5.0, "rationale": "Stop loss"}],
        "buys": [],
    }
    result = executor.execute_decisions("p1", decisions, PRICES)

    repo.batch_remove_holdings.assert_called_once()
    args, kwargs = repo.batch_remove_holdings.call_args
    assert args[0] == "p1"
    assert args[1] == [{"ticker": "AAPL", "shares": 5.0, "price": 150.0, "rationale": "Stop loss"}]

    assert len(result["executed_trades"]) == 1
    assert result["executed_trades"][0]["action"] == "SELL"
    assert result["executed_trades"][0]["ticker"] == "AAPL"
    assert len(result["failed_trades"]) == 0


def test_execute_sell_missing_price():
    """SELL with no price in prices dict → failed_trade."""
    repo = _make_repo()
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [{"ticker": "NVDA", "shares": 5.0, "rationale": "Stop loss"}],
        "buys": [],
    }
    result = executor.execute_decisions("p1", decisions, PRICES)

    repo.remove_holding.assert_not_called()
    assert len(result["failed_trades"]) == 1
    assert result["failed_trades"][0]["ticker"] == "NVDA"


def test_execute_sell_insufficient_shares():
    """SELL that fails due to logic in batch_remove_holdings → failed_trade."""
    repo = _make_repo()
    repo.batch_remove_holdings.return_value = (
        [],
        [{"action": "SELL", "ticker": "AAPL", "reason": "Hold 10.0 shares of AAPL, cannot sell 999.0"}]
    )
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [{"ticker": "AAPL", "shares": 999.0, "rationale": "Exit"}],
        "buys": [],
    }
    result = executor.execute_decisions("p1", decisions, PRICES)

    assert len(result["failed_trades"]) == 1
    assert "cannot sell 999.0" in result["failed_trades"][0]["reason"]


# ---------------------------------------------------------------------------
# BUY tests
# ---------------------------------------------------------------------------


def test_execute_buy_success():
    """Successful BUY calls add_holding and is in executed_trades."""
    portfolio = _make_portfolio(cash=50_000.0, total_value=60_000.0)
    repo = _make_repo(portfolio=portfolio)
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [],
        "buys": [{"ticker": "MSFT", "shares": 10.0, "sector": "Technology", "rationale": "Growth"}],
    }
    result = executor.execute_decisions("p1", decisions, PRICES)

    repo.add_holding.assert_called_once_with("p1", "MSFT", 10.0, 300.0, sector="Technology", stop_loss=None, take_profit=None)
    assert len(result["executed_trades"]) == 1
    assert result["executed_trades"][0]["action"] == "BUY"


def test_execute_buy_missing_price():
    """BUY with no price in prices dict → failed_trade."""
    repo = _make_repo()
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [],
        "buys": [{"ticker": "TSLA", "shares": 5.0, "sector": "Automotive", "rationale": "EV"}],
    }
    result = executor.execute_decisions("p1", decisions, PRICES)

    repo.add_holding.assert_not_called()
    assert len(result["failed_trades"]) == 1
    assert result["failed_trades"][0]["ticker"] == "TSLA"


def test_execute_buy_constraint_violation():
    """BUY exceeding max_positions → failed_trade with constraint violation."""
    # Fill portfolio to max positions (15)
    holdings = [
        _make_holding(f"T{i}", shares=10, avg_cost=100, sector="Technology")
        for i in range(15)
    ]
    portfolio = _make_portfolio(cash=5_000.0, total_value=20_000.0)
    repo = _make_repo(portfolio=portfolio, holdings=holdings)
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [],
        "buys": [{"ticker": "NEWT", "shares": 5.0, "sector": "Healthcare", "rationale": "New"}],
    }
    result = executor.execute_decisions("p1", decisions, {**PRICES, "NEWT": 50.0})

    repo.add_holding.assert_not_called()
    assert len(result["failed_trades"]) == 1
    assert result["failed_trades"][0]["reason"] == "Constraint violation"


# ---------------------------------------------------------------------------
# Ordering and snapshot
# ---------------------------------------------------------------------------


def test_execute_decisions_sells_before_buys():
    """SELLs are always executed before BUYs."""
    portfolio = _make_portfolio(cash=50_000.0, total_value=60_000.0)
    repo = _make_repo(portfolio=portfolio)
    repo.batch_remove_holdings.return_value = (
        [{"action": "SELL", "ticker": "AAPL", "shares": 5.0, "price": 150.0, "rationale": "Exit"}],
        []
    )
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [{"ticker": "AAPL", "shares": 5.0, "rationale": "Exit"}],
        "buys": [{"ticker": "MSFT", "shares": 3.0, "sector": "Technology", "rationale": "Add"}],
    }
    executor.execute_decisions("p1", decisions, PRICES)

    # Verify call order: batch_remove_holdings before add_holding
    call_order = [c[0] for c in repo.method_calls if c[0] in ("batch_remove_holdings", "add_holding")]
    assert call_order.index("batch_remove_holdings") < call_order.index("add_holding")


def test_execute_decisions_takes_snapshot():
    """take_snapshot is always called at end of execution."""
    repo = _make_repo()
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {"sells": [], "buys": []}
    result = executor.execute_decisions("p1", decisions, PRICES)

    repo.take_snapshot.assert_called_once_with("p1", PRICES)
    assert "snapshot" in result
    assert result["snapshot"]["snapshot_id"] == "snap-1"


# ---------------------------------------------------------------------------
# Stop loss / take profit tests
# ---------------------------------------------------------------------------


def test_execute_buy_with_stop_loss_and_take_profit():
    """BUY with stop_loss and take_profit passes them to add_holding and executed_trades."""
    portfolio = _make_portfolio(cash=50_000.0, total_value=60_000.0)
    repo = _make_repo(portfolio=portfolio)
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [],
        "buys": [{
            "ticker": "MSFT",
            "shares": 5.0,
            "sector": "Technology",
            "rationale": "Breakout",
            "stop_loss": 270.0,
            "take_profit": 360.0,
        }],
    }
    result = executor.execute_decisions("p1", decisions, PRICES)

    repo.add_holding.assert_called_once_with(
        "p1", "MSFT", 5.0, 300.0,
        sector="Technology",
        stop_loss=270.0,
        take_profit=360.0,
    )
    assert len(result["executed_trades"]) == 1
    trade = result["executed_trades"][0]
    assert trade["stop_loss"] == 270.0
    assert trade["take_profit"] == 360.0


def test_execute_buy_without_risk_levels_stores_none():
    """BUY with no stop_loss/take_profit stores None for both fields."""
    portfolio = _make_portfolio(cash=50_000.0, total_value=60_000.0)
    repo = _make_repo(portfolio=portfolio)
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [],
        "buys": [{"ticker": "MSFT", "shares": 5.0, "sector": "Technology", "rationale": "Entry"}],
    }
    result = executor.execute_decisions("p1", decisions, PRICES)

    trade = result["executed_trades"][0]
    assert trade["stop_loss"] is None
    assert trade["take_profit"] is None
