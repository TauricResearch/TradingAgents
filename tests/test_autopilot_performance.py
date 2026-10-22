import pytest
from tradingagents.paper.engine import Book
from tradingagents.paper.autopilot.performance import scorecard


def test_untraded_portfolio_claims_no_observed_edge():
    book=Book.new("2026-10-21")
    report=scorecard(book)
    assert report["equity_gbp"]==10000
    assert report["closed_trades"]==0
    assert report["win_rate_pct"] is None
    assert report["profit_factor"] is None
    assert report["sample_mature"] is False
    assert "No statistically verified edge" in report["conclusion"]


def test_spy_is_labelled_price_only_and_not_total_return():
    b=Book.new("2026-10-21")
    b=b.step("2026-10-21",{},.75,.75,600)
    b=b.step("2026-10-22",{},.75,.75,630)
    r=scorecard(b)
    assert r["spy_return_pct"]==5
    assert r["net_return_pct"]==0
    assert r["excess_return_vs_spy_price_pct_points"]==-5
    assert "price-only" in r["price_only_benchmark"]


def test_no_infinite_profit_factor_when_no_losers():
    b=Book.new("2026-10-21")
    b.completed=[{"pnl_gbp":100.0}]
    r=scorecard(b)
    assert r["win_rate_pct"]==100
    assert r["profit_factor"] is None
    assert r["sample_mature"] is False
