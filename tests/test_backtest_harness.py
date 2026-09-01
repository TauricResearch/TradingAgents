"""Backtest harness: date generation, summary stats, and grid fault tolerance.

The harness itself is deterministic and LLM-free here -- the graph is
mocked -- so the tests pin down the evaluation contract (CSV rows, markdown
summary, one-bad-cell isolation, memory-log opt-out) without spending
API credits.
"""

import pandas as pd
import pytest

import tradingagents.evaluation.backtest as backtest

# ---------------------------------------------------------------------------
# Date generation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_generate_dates_inclusive_with_step():
    dates = backtest.generate_dates("2024-01-01", "2024-01-22", every_n_days=7)
    assert dates == ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"]


@pytest.mark.unit
def test_generate_dates_single_day():
    assert backtest.generate_dates("2024-03-01", "2024-03-01") == ["2024-03-01"]


@pytest.mark.unit
def test_generate_dates_rejects_bad_input():
    with pytest.raises(ValueError):
        backtest.generate_dates("2024-01-22", "2024-01-01")
    with pytest.raises(ValueError):
        backtest.generate_dates("2024-01-01", "2024-01-22", every_n_days=0)


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


def _outcome_df():
    return pd.DataFrame([
        {"ticker": "NVDA", "date": "2024-01-01", "rating": "Buy",
         "raw_return": 0.05, "alpha_return": 0.02, "holding_days": 5, "error": ""},
        {"ticker": "NVDA", "date": "2024-01-08", "rating": "Buy",
         "raw_return": -0.03, "alpha_return": -0.01, "holding_days": 5, "error": ""},
        {"ticker": "AAPL", "date": "2024-01-01", "rating": "Sell",
         "raw_return": -0.02, "alpha_return": 0.01, "holding_days": 5, "error": ""},
        {"ticker": "AAPL", "date": "2024-01-08", "rating": "Hold",
         "raw_return": 0.01, "alpha_return": 0.0, "holding_days": 5, "error": ""},
        {"ticker": "NVDA", "date": "2024-01-15", "rating": "ERROR",
         "raw_return": None, "alpha_return": None, "holding_days": None, "error": "boom"},
    ])


@pytest.mark.unit
def test_summarize_reports_distribution_hits_and_errors():
    summary = backtest.summarize(_outcome_df())
    assert "Runs: 5" in summary
    assert "Errors: 1" in summary
    assert "Resolved outcomes" in summary
    # Buy: 1 of 2 directional hits (alpha +0.02 hit, -0.01 miss) -> 50%.
    assert "| Buy | 2 |" in summary
    assert "50%" in summary
    # Sell with alpha +0.01 is a miss (expected negative alpha).
    assert "| Sell | 1 |" in summary
    # Overall hit rate: 1 hit out of 3 directional rows -> 33%.
    assert "33%" in summary


@pytest.mark.unit
def test_summarize_empty_frame_is_graceful():
    summary = backtest.summarize(pd.DataFrame(columns=["rating", "alpha_return", "raw_return"]))
    assert "Runs: 0" in summary
    assert "n/a" in summary


# ---------------------------------------------------------------------------
# End-to-end grid execution (graph mocked)
# ---------------------------------------------------------------------------


class _FakeGraph:
    """Minimal TradingAgentsGraph stand-in with deterministic outcomes."""

    def __init__(self, config):
        self.config = config

    def _resolve_benchmark(self, ticker):
        return "SPY"

    def propagate(self, ticker, date, asset_type="stock"):
        return {}, "Buy"

    def _fetch_returns(self, ticker, date, holding_days, benchmark):
        return 0.05, 0.02, holding_days


class _FlakyGraph(_FakeGraph):
    def __init__(self, config):
        super().__init__(config)
        self.calls = 0

    def propagate(self, ticker, date, asset_type="stock"):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("simulated LLM outage")
        return {}, "Hold"


@pytest.mark.unit
def test_run_backtest_writes_csv_and_summary(monkeypatch, tmp_path):
    captured = {}

    def fake_factory(config):
        captured["config"] = config
        return _FakeGraph(config)

    monkeypatch.setattr(backtest, "TradingAgentsGraph", fake_factory)
    df, summary = backtest.run_backtest(
        tickers=["NVDA", "AAPL"],
        dates=["2024-01-01", "2024-01-08"],
        save_dir=str(tmp_path),
    )

    assert len(df) == 4
    assert set(df["rating"]) == {"Buy"}
    assert df["alpha_return"].tolist() == [0.02, 0.02, 0.02, 0.02]
    assert (tmp_path / "backtest_results.csv").exists()
    assert (tmp_path / "backtest_summary.md").exists()
    # Memory log is disabled by default so backtests stay out of the log.
    assert captured["config"]["memory_log_path"] is None


@pytest.mark.unit
def test_run_backtest_merges_defaults_when_config_is_empty_dict(monkeypatch):
    # Regression: the CLI passes config={} when no provider/model flags are
    # given; run_backtest must fall back to DEFAULT_CONFIG for every other key
    # instead of handing TradingAgentsGraph a one-key dict (#1234).
    captured = {}

    def fake_factory(config):
        captured["config"] = config
        return _FakeGraph(config)

    monkeypatch.setattr(backtest, "TradingAgentsGraph", fake_factory)
    df, _ = backtest.run_backtest(
        tickers=["NVDA"],
        dates=["2024-01-01"],
        config={},
    )
    assert len(df) == 1
    assert captured["config"]["data_cache_dir"]
    assert captured["config"]["llm_provider"]
    assert captured["config"]["memory_log_path"] is None


@pytest.mark.unit
def test_run_backtest_records_failures_and_continues(monkeypatch):
    monkeypatch.setattr(backtest, "TradingAgentsGraph", _FlakyGraph)
    df, _ = backtest.run_backtest(
        tickers=["NVDA"],
        dates=["2024-01-01", "2024-01-08", "2024-01-15"],
    )
    assert len(df) == 3
    error_rows = df[df["rating"] == "ERROR"]
    assert len(error_rows) == 1
    assert "simulated LLM outage" in error_rows.iloc[0]["error"]
    assert (df["rating"] == "Hold").sum() == 2
