"""Tests for tradingagents/portfolio/models.py.

Tests the four dataclass models: Portfolio, Holding, Trade, PortfolioSnapshot.

Coverage targets:
- to_dict() / from_dict() round-trips
- enrich() computed-field logic
- Edge cases (zero cost basis, zero portfolio value)

Run::

    pytest tests/portfolio/test_models.py -v
"""

from __future__ import annotations

import pytest

from tradingagents.portfolio.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    Trade,
)


# ---------------------------------------------------------------------------
# Portfolio round-trip
# ---------------------------------------------------------------------------


def test_portfolio_to_dict_round_trip(sample_portfolio):
    """Portfolio.to_dict() -> Portfolio.from_dict() must be lossless."""
    d = sample_portfolio.to_dict()
    restored = Portfolio.from_dict(d)
    assert restored.portfolio_id == sample_portfolio.portfolio_id
    assert restored.name == sample_portfolio.name
    assert restored.cash == sample_portfolio.cash
    assert restored.initial_cash == sample_portfolio.initial_cash
    assert restored.currency == sample_portfolio.currency
    assert restored.created_at == sample_portfolio.created_at
    assert restored.updated_at == sample_portfolio.updated_at
    assert restored.report_path == sample_portfolio.report_path
    assert restored.metadata == sample_portfolio.metadata


def test_portfolio_to_dict_excludes_runtime_fields(sample_portfolio):
    """to_dict() must not include computed fields (total_value, equity_value, cash_pct)."""
    d = sample_portfolio.to_dict()
    assert "total_value" not in d
    assert "equity_value" not in d
    assert "cash_pct" not in d


def test_portfolio_from_dict_defaults_optional_fields():
    """from_dict() must tolerate missing optional fields."""
    minimal = {
        "portfolio_id": "pid-1",
        "name": "Minimal",
        "cash": 1000.0,
        "initial_cash": 1000.0,
    }
    p = Portfolio.from_dict(minimal)
    assert p.currency == "USD"
    assert p.created_at == ""
    assert p.updated_at == ""
    assert p.report_path is None
    assert p.metadata == {}


# ---------------------------------------------------------------------------
# Holding round-trip
# ---------------------------------------------------------------------------


def test_holding_to_dict_round_trip(sample_holding):
    """Holding.to_dict() -> Holding.from_dict() must be lossless."""
    d = sample_holding.to_dict()
    restored = Holding.from_dict(d)
    assert restored.holding_id == sample_holding.holding_id
    assert restored.portfolio_id == sample_holding.portfolio_id
    assert restored.ticker == sample_holding.ticker
    assert restored.shares == sample_holding.shares
    assert restored.avg_cost == sample_holding.avg_cost
    assert restored.sector == sample_holding.sector
    assert restored.industry == sample_holding.industry


def test_holding_to_dict_excludes_runtime_fields(sample_holding):
    """to_dict() must not include current_price, current_value, weight, etc."""
    d = sample_holding.to_dict()
    for field in ("current_price", "current_value", "cost_basis",
                  "unrealized_pnl", "unrealized_pnl_pct", "weight"):
        assert field not in d


# ---------------------------------------------------------------------------
# Trade round-trip
# ---------------------------------------------------------------------------


def test_trade_to_dict_round_trip(sample_trade):
    """Trade.to_dict() -> Trade.from_dict() must be lossless."""
    d = sample_trade.to_dict()
    restored = Trade.from_dict(d)
    assert restored.trade_id == sample_trade.trade_id
    assert restored.portfolio_id == sample_trade.portfolio_id
    assert restored.ticker == sample_trade.ticker
    assert restored.action == sample_trade.action
    assert restored.shares == sample_trade.shares
    assert restored.price == sample_trade.price
    assert restored.total_value == sample_trade.total_value
    assert restored.trade_date == sample_trade.trade_date
    assert restored.rationale == sample_trade.rationale
    assert restored.signal_source == sample_trade.signal_source
    assert restored.stop_loss == sample_trade.stop_loss
    assert restored.take_profit == sample_trade.take_profit
    assert restored.metadata == sample_trade.metadata


def test_trade_stop_loss_take_profit_round_trip(sample_portfolio_id):
    """Trade with stop_loss and take_profit serialises and deserialises correctly."""
    trade = Trade(
        trade_id="t-risk-1",
        portfolio_id=sample_portfolio_id,
        ticker="NVDA",
        action="BUY",
        shares=10.0,
        price=800.0,
        total_value=8_000.0,
        stop_loss=720.0,
        take_profit=960.0,
    )
    d = trade.to_dict()
    assert d["stop_loss"] == 720.0
    assert d["take_profit"] == 960.0

    restored = Trade.from_dict(d)
    assert restored.stop_loss == 720.0
    assert restored.take_profit == 960.0


def test_trade_stop_loss_take_profit_default_none(sample_trade):
    """Trade defaults stop_loss and take_profit to None when not provided."""
    assert sample_trade.stop_loss is None
    assert sample_trade.take_profit is None
    d = sample_trade.to_dict()
    assert d["stop_loss"] is None
    assert d["take_profit"] is None


def test_trade_from_dict_missing_risk_levels_defaults_none():
    """from_dict() gracefully handles missing stop_loss/take_profit keys."""
    data = {
        "trade_id": "t-1",
        "portfolio_id": "p-1",
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 5.0,
        "price": 150.0,
        "total_value": 750.0,
    }
    trade = Trade.from_dict(data)
    assert trade.stop_loss is None
    assert trade.take_profit is None


# ---------------------------------------------------------------------------
# PortfolioSnapshot round-trip
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_round_trip(sample_snapshot):
    """PortfolioSnapshot.to_dict() -> PortfolioSnapshot.from_dict() round-trip."""
    d = sample_snapshot.to_dict()
    restored = PortfolioSnapshot.from_dict(d)
    assert restored.snapshot_id == sample_snapshot.snapshot_id
    assert restored.portfolio_id == sample_snapshot.portfolio_id
    assert restored.snapshot_date == sample_snapshot.snapshot_date
    assert restored.total_value == sample_snapshot.total_value
    assert restored.cash == sample_snapshot.cash
    assert restored.equity_value == sample_snapshot.equity_value
    assert restored.num_positions == sample_snapshot.num_positions
    assert restored.holdings_snapshot == sample_snapshot.holdings_snapshot
    assert restored.metadata == sample_snapshot.metadata


def test_snapshot_from_dict_parses_holdings_snapshot_json_string():
    """from_dict() must parse holdings_snapshot when it arrives as a JSON string."""
    import json
    holdings = [{"ticker": "AAPL", "shares": 10.0}]
    data = {
        "snapshot_id": "snap-1",
        "portfolio_id": "pid-1",
        "snapshot_date": "2026-03-20",
        "total_value": 110_000.0,
        "cash": 10_000.0,
        "equity_value": 100_000.0,
        "num_positions": 1,
        "holdings_snapshot": json.dumps(holdings),  # string form as returned by Supabase
    }
    snap = PortfolioSnapshot.from_dict(data)
    assert snap.holdings_snapshot == holdings


# ---------------------------------------------------------------------------
# Holding.enrich()
# ---------------------------------------------------------------------------


def test_holding_enrich_computes_current_value(sample_holding):
    """enrich() must set current_value = current_price * shares."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=100_000.0)
    assert sample_holding.current_value == 200.0 * sample_holding.shares


def test_holding_enrich_computes_unrealized_pnl(sample_holding):
    """enrich() must set unrealized_pnl = current_value - cost_basis."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=100_000.0)
    expected_cost_basis = sample_holding.avg_cost * sample_holding.shares
    expected_pnl = sample_holding.current_value - expected_cost_basis
    assert sample_holding.unrealized_pnl == pytest.approx(expected_pnl)


def test_holding_enrich_computes_unrealized_pnl_pct(sample_holding):
    """enrich() must set unrealized_pnl_pct = unrealized_pnl / cost_basis."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=100_000.0)
    cost_basis = sample_holding.avg_cost * sample_holding.shares
    expected_pct = sample_holding.unrealized_pnl / cost_basis
    assert sample_holding.unrealized_pnl_pct == pytest.approx(expected_pct)


def test_holding_enrich_computes_weight(sample_holding):
    """enrich() must set weight = current_value / portfolio_total_value."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=100_000.0)
    expected_weight = sample_holding.current_value / 100_000.0
    assert sample_holding.weight == pytest.approx(expected_weight)


def test_holding_enrich_returns_self(sample_holding):
    """enrich() must return self for chaining."""
    result = sample_holding.enrich(current_price=200.0, portfolio_total_value=100_000.0)
    assert result is sample_holding


def test_holding_enrich_handles_zero_cost(sample_holding):
    """When avg_cost == 0, unrealized_pnl_pct must be 0 (no ZeroDivisionError)."""
    sample_holding.avg_cost = 0.0
    sample_holding.enrich(current_price=200.0, portfolio_total_value=100_000.0)
    assert sample_holding.unrealized_pnl_pct == 0.0


def test_holding_enrich_handles_zero_portfolio_value(sample_holding):
    """When portfolio_total_value == 0, weight must be 0 (no ZeroDivisionError)."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=0.0)
    assert sample_holding.weight == 0.0


# ---------------------------------------------------------------------------
# Portfolio.enrich()
# ---------------------------------------------------------------------------


def test_portfolio_enrich_computes_total_value(sample_portfolio, sample_holding):
    """Portfolio.enrich() must compute total_value = cash + sum(holding.current_value)."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=1.0)  # sets current_value; dummy total is overwritten by portfolio.enrich()
    sample_portfolio.enrich([sample_holding])
    expected_equity = 200.0 * sample_holding.shares
    assert sample_portfolio.total_value == pytest.approx(sample_portfolio.cash + expected_equity)


def test_portfolio_enrich_computes_equity_value(sample_portfolio, sample_holding):
    """Portfolio.enrich() must set equity_value = sum(holding.current_value)."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=1.0)  # sets current_value; dummy total is overwritten by portfolio.enrich()
    sample_portfolio.enrich([sample_holding])
    assert sample_portfolio.equity_value == pytest.approx(200.0 * sample_holding.shares)


def test_portfolio_enrich_computes_cash_pct(sample_portfolio, sample_holding):
    """Portfolio.enrich() must compute cash_pct = cash / total_value."""
    sample_holding.enrich(current_price=200.0, portfolio_total_value=1.0)  # sets current_value; dummy total is overwritten by portfolio.enrich()
    sample_portfolio.enrich([sample_holding])
    expected_pct = sample_portfolio.cash / sample_portfolio.total_value
    assert sample_portfolio.cash_pct == pytest.approx(expected_pct)


def test_portfolio_enrich_returns_self(sample_portfolio):
    """enrich() must return self for chaining."""
    result = sample_portfolio.enrich([])
    assert result is sample_portfolio


def test_portfolio_enrich_no_holdings(sample_portfolio):
    """Portfolio.enrich() with empty holdings: equity_value=0, total_value=cash."""
    sample_portfolio.enrich([])
    assert sample_portfolio.equity_value == 0.0
    assert sample_portfolio.total_value == sample_portfolio.cash
    assert sample_portfolio.cash_pct == 1.0
