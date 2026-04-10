"""Tests for the hypothesis comparison script."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.compare_hypothesis import (
    compute_metrics,
    compute_7d_return,
    load_baseline_metrics,
    make_decision,
)


# ── compute_metrics ──────────────────────────────────────────────────────────

def test_compute_metrics_empty():
    result = compute_metrics([])
    assert result == {"count": 0, "evaluated": 0, "win_rate": None, "avg_return": None}


def test_compute_metrics_all_wins():
    picks = [
        {"return_7d": 5.0, "win_7d": True},
        {"return_7d": 3.0, "win_7d": True},
    ]
    result = compute_metrics(picks)
    assert result["win_rate"] == 100.0
    assert result["avg_return"] == 4.0
    assert result["evaluated"] == 2


def test_compute_metrics_mixed():
    picks = [
        {"return_7d": 10.0, "win_7d": True},
        {"return_7d": -5.0, "win_7d": False},
        {"return_7d": None, "win_7d": None},   # pending — excluded
    ]
    result = compute_metrics(picks)
    assert result["win_rate"] == 50.0
    assert result["avg_return"] == 2.5
    assert result["evaluated"] == 2
    assert result["count"] == 3


# ── compute_7d_return ────────────────────────────────────────────────────────

def test_compute_7d_return_positive():
    import pandas as pd

    close_data = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0]
    mock_df = pd.DataFrame({"Close": close_data})

    with patch("scripts.compare_hypothesis.download_history", return_value=mock_df):
        ret, win = compute_7d_return("AAPL", "2026-03-01")

    assert ret == pytest.approx(10.0, rel=0.01)
    assert win is True


def test_compute_7d_return_empty_data():
    import pandas as pd

    mock_df = pd.DataFrame()

    with patch("scripts.compare_hypothesis.download_history", return_value=mock_df):
        ret, win = compute_7d_return("AAPL", "2026-03-01")

    assert ret is None
    assert win is None


# ── load_baseline_metrics ────────────────────────────────────────────────────

def test_load_baseline_metrics(tmp_path):
    db = {
        "recommendations_by_date": {
            "2026-03-01": [
                {"strategy_match": "options_flow", "return_7d": 5.0, "win_7d": True},
                {"strategy_match": "options_flow", "return_7d": -2.0, "win_7d": False},
                {"strategy_match": "reddit_dd", "return_7d": 3.0, "win_7d": True},
            ]
        }
    }
    db_file = tmp_path / "performance_database.json"
    db_file.write_text(json.dumps(db))

    result = load_baseline_metrics("options_flow", str(db_file))

    assert result["win_rate"] == 50.0
    assert result["avg_return"] == 1.5
    assert result["count"] == 2


def test_load_baseline_metrics_missing_file(tmp_path):
    result = load_baseline_metrics("options_flow", str(tmp_path / "missing.json"))
    assert result == {"count": 0, "win_rate": None, "avg_return": None}


# ── make_decision ─────────────────────────────────────────────────────────────

def test_make_decision_accepted_by_win_rate():
    hyp = {"win_rate": 60.0, "avg_return": 0.5, "evaluated": 10}
    baseline = {"win_rate": 50.0, "avg_return": 0.5}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "accepted"
    assert "win rate" in reason.lower()


def test_make_decision_accepted_by_return():
    hyp = {"win_rate": 52.0, "avg_return": 3.0, "evaluated": 10}
    baseline = {"win_rate": 50.0, "avg_return": 1.5}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "accepted"
    assert "return" in reason.lower()


def test_make_decision_rejected():
    hyp = {"win_rate": 48.0, "avg_return": 0.2, "evaluated": 10}
    baseline = {"win_rate": 50.0, "avg_return": 1.0}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "rejected"


def test_make_decision_insufficient_data():
    hyp = {"win_rate": 80.0, "avg_return": 5.0, "evaluated": 2}
    baseline = {"win_rate": 50.0, "avg_return": 1.0}
    decision, reason = make_decision(hyp, baseline)
    assert decision == "rejected"
    assert "insufficient" in reason.lower()
