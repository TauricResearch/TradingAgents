"""Tests for the accuracy scorer."""
from __future__ import annotations

from web.server.ticker_agent.scorer import (
    compute_score_for_ticker,
    compute_ticker_scores,
)


def _fake_run(ticker: str, date: str, status: str, action: str, start_price: float, end_price: float) -> dict:
    return {
        "id": f"{ticker}_{date}_001",
        "ticker": ticker,
        "started_at": f"{date}T10:00:00Z",
        "status": status,
        "decision_action": action,
        "decision_target": None,
        "start_price": start_price,
        "end_price": end_price,
    }


def test_compute_ticker_scores_aggregates_correctly():
    runs = [
        _fake_run("NVDA", "2024-01-01", "done", "BUY", 100.0, 110.0),   # right (went up)
        _fake_run("NVDA", "2024-01-02", "done", "SELL", 100.0, 90.0),   # right (went down)
        _fake_run("NVDA", "2024-01-03", "done", "BUY", 100.0, 95.0),    # wrong (went down)
        _fake_run("AAPL", "2024-01-01", "done", "BUY", 100.0, 105.0),   # right
    ]
    scores = compute_ticker_scores({"NVDA": [r for r in runs if r["ticker"] == "NVDA"],
                                    "AAPL": [r for r in runs if r["ticker"] == "AAPL"]},
                                   min_samples=1)
    nvda = scores["NVDA"]
    assert nvda.total_runs == 3
    assert nvda.right == 2
    assert nvda.wrong == 1
    assert nvda.win_rate == 2 / 3
    aapl = scores["AAPL"]
    assert aapl.total_runs == 1
    assert aapl.right == 1
    assert aapl.wrong == 0
    assert aapl.win_rate == 1.0


def test_compute_ticker_scores_filters_below_min_samples():
    runs = _fake_run("NVDA", "2024-01-01", "done", "BUY", 100.0, 110.0)
    scores = compute_ticker_scores({"NVDA": [runs]}, min_samples=3)
    assert len(scores) == 0


def test_compute_score_for_ticker_returns_none_for_no_runs():
    result = compute_score_for_ticker("UNKNOWN", [])
    assert result is None
