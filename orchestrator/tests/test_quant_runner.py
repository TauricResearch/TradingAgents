"""Tests for QuantRunner._calc_confidence()."""
import json
import sqlite3
import pandas as pd
import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.error_taxonomy import ReasonCode
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


def test_get_signal_returns_reason_code_when_no_data(runner, monkeypatch):
    monkeypatch.setattr(
        "orchestrator.quant_runner.yf.download",
        lambda *args, **kwargs: type("EmptyFrame", (), {"empty": True})(),
    )

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.QUANT_NO_DATA.value


def test_get_signal_marks_non_trading_day_on_a_share_holiday(runner, monkeypatch):
    monkeypatch.setattr(
        "orchestrator.quant_runner.yf.download",
        lambda *args, **kwargs: pd.DataFrame(),
    )

    signal = runner.get_signal("600519.SS", "2024-10-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.NON_TRADING_DAY.value
    assert signal.metadata["data_quality"]["state"] == "non_trading_day"


def test_get_signal_marks_non_trading_day_on_market_holiday(runner, monkeypatch):
    monkeypatch.setattr(
        "orchestrator.quant_runner.yf.download",
        lambda *args, **kwargs: pd.DataFrame(),
    )

    signal = runner.get_signal("AAPL", "2024-03-29")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.NON_TRADING_DAY.value
    assert signal.metadata["data_quality"]["state"] == "non_trading_day"


def test_get_signal_marks_non_trading_day_on_weekend(runner, monkeypatch):
    monkeypatch.setattr(
        "orchestrator.quant_runner.yf.download",
        lambda *args, **kwargs: pd.DataFrame(),
    )

    signal = runner.get_signal("AAPL", "2024-01-06")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.NON_TRADING_DAY.value
    assert signal.metadata["data_quality"]["state"] == "non_trading_day"


def test_get_signal_marks_non_trading_day_on_market_holiday(runner, monkeypatch):
    holiday_frame = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.0],
            "Close": [10.5],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2024-07-03"]),
    )
    monkeypatch.setattr(
        "orchestrator.quant_runner.yf.download",
        lambda *args, **kwargs: holiday_frame,
    )

    signal = runner.get_signal("AAPL", "2024-07-04")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.NON_TRADING_DAY.value
    assert signal.metadata["data_quality"]["state"] == "non_trading_day"
    assert signal.metadata["data_quality"]["last_available_date"] == "2024-07-03"


def test_get_signal_marks_stale_data_when_requested_day_missing(runner, monkeypatch):
    stale_frame = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.0],
            "Close": [10.5],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )
    monkeypatch.setattr(
        "orchestrator.quant_runner.yf.download",
        lambda *args, **kwargs: stale_frame,
    )

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.STALE_DATA.value
    assert signal.metadata["data_quality"]["state"] == "stale_data"


def test_get_signal_marks_partial_data_when_required_columns_missing(runner, monkeypatch):
    partial_frame = pd.DataFrame(
        {
            "Open": [10.0],
            "Low": [9.0],
            "Close": [10.5],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )
    monkeypatch.setattr(
        "orchestrator.quant_runner.yf.download",
        lambda *args, **kwargs: partial_frame,
    )

    signal = runner.get_signal("AAPL", "2024-01-02")

    assert signal.degraded is True
    assert signal.reason_code == ReasonCode.PARTIAL_DATA.value
    assert signal.metadata["data_quality"]["state"] == "partial_data"
