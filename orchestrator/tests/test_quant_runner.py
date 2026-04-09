"""Tests for QuantRunner._calc_confidence()."""
import json
import sqlite3
import tempfile
import os
import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.quant_runner import QuantRunner


def _make_runner(tmp_path):
    """Create a QuantRunner with a minimal SQLite DB so __init__ succeeds."""
    db_dir = tmp_path / "research_results"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "runs.db"

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """CREATE TABLE backtest_results (
                id INTEGER PRIMARY KEY,
                strategy_type TEXT,
                params TEXT,
                sharpe_ratio REAL
            )"""
        )
        conn.execute(
            "INSERT INTO backtest_results (strategy_type, params, sharpe_ratio) VALUES (?, ?, ?)",
            ("BollingerStrategy", json.dumps({"period": 20, "num_std": 2.0,
                                               "position_pct": 0.2,
                                               "stop_loss_pct": 0.05,
                                               "take_profit_pct": 0.15}), 1.5),
        )

    cfg = OrchestratorConfig(quant_backtest_path=str(tmp_path))
    return QuantRunner(cfg)


@pytest.fixture
def runner(tmp_path):
    return _make_runner(tmp_path)


def test_calc_confidence_max_sharpe_zero(runner):
    assert runner._calc_confidence(1.0, 0) == 0.5


def test_calc_confidence_half(runner):
    result = runner._calc_confidence(1.0, 2.0)
    assert result == pytest.approx(0.5)


def test_calc_confidence_full(runner):
    result = runner._calc_confidence(2.0, 2.0)
    assert result == pytest.approx(1.0)


def test_calc_confidence_clamped_above(runner):
    result = runner._calc_confidence(3.0, 2.0)
    assert result == pytest.approx(1.0)


def test_calc_confidence_clamped_below(runner):
    result = runner._calc_confidence(-1.0, 2.0)
    assert result == pytest.approx(0.0)
