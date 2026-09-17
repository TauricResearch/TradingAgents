"""Backtesting: many single-shot decisions, scored by the decision log.

A run already records its rating and later settles it with realized and alpha
return against the regional benchmark. A backtest is that machinery over a grid
of tickers and dates, aggregated. It evaluates decision quality; it does not
simulate a portfolio, so there is no execution, no fees and no equity curve.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.backtest import iter_grid, run_backtest, summarize

DECISION = "Rating: Buy\n\nbuy it"


@pytest.mark.unit
def test_grid_spacing_and_canonical_dates():
    assert iter_grid("2026-01-05", "2026-01-20", every_n_days=7) == ["2026-01-05", "2026-01-12", "2026-01-19"]


@pytest.mark.unit
def test_grid_stops_at_today(monkeypatch):
    import tradingagents.backtest as bt

    monkeypatch.setattr(bt, "get_current_date", lambda: "2026-01-10")
    assert iter_grid("2026-01-05", "2026-02-20", every_n_days=5) == ["2026-01-05", "2026-01-10"]


@pytest.mark.unit
def test_grid_rejects_a_non_canonical_date():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        iter_grid("2026-1-5", "2026-01-20")


class _FakeGraph:
    """Stands in for TradingAgentsGraph, writing to the log the harness gave it."""

    instances: list = []
    fail_on: set = set()

    def __init__(self, selected_analysts=None, config=None, **kw):
        self.analysts = list(selected_analysts) if selected_analysts else None
        self.config = config
        self.memory_log = TradingMemoryLog(config)
        self.calls = []
        self.settled = []
        _FakeGraph.instances.append(self)

    def propagate(self, ticker, trade_date, asset_type="stock", portfolio=None):
        self.calls.append((ticker, trade_date))
        if (ticker, trade_date) in _FakeGraph.fail_on:
            raise RuntimeError("vendor exploded")
        self.memory_log.store_decision(ticker, trade_date, DECISION)
        return {"final_trade_decision": DECISION}, "Buy"

    def settle_pending(self, ticker):
        self.settled.append(ticker)


@pytest.fixture(autouse=True)
def _fake_graph(monkeypatch, tmp_path):
    import tradingagents.backtest as bt

    _FakeGraph.instances = []
    _FakeGraph.fail_on = set()
    monkeypatch.setattr(bt, "TradingAgentsGraph", _FakeGraph)
    return _FakeGraph


def _config(tmp_path):
    return {"results_dir": str(tmp_path / "results"),
            "memory_log_path": str(tmp_path / "live_trading_memory.md")}


@pytest.mark.unit
def test_the_live_decision_log_is_never_written(tmp_path):
    config = _config(tmp_path)
    result = run_backtest(["NVDA"], ["2026-01-05", "2026-01-12"], config)

    assert not (tmp_path / "live_trading_memory.md").exists()
    assert result.log_path.exists() and result.cells_run == 2


@pytest.mark.unit
def test_a_cell_already_in_the_log_is_not_run_again(tmp_path):
    config = _config(tmp_path)
    first = run_backtest(["NVDA"], ["2026-01-05"], config)

    again = run_backtest(["NVDA"], ["2026-01-05", "2026-01-12"], config, run_id=first.run_id)

    assert again.cells_run == 1 and again.skipped == 1
    assert _FakeGraph.instances[-1].calls == [("NVDA", "2026-01-12")]


@pytest.mark.unit
def test_every_ticker_is_settled_after_the_grid(tmp_path):
    """Settlement runs at the start of the next same-ticker run, so the last
    date of each ticker would stay pending without an explicit pass."""
    run_backtest(["NVDA", "AAPL"], ["2026-01-05", "2026-01-12"], _config(tmp_path))
    assert sorted(_FakeGraph.instances[-1].settled) == ["AAPL", "NVDA"]


@pytest.mark.unit
def test_a_failed_cell_does_not_abort_the_sweep(tmp_path):
    _FakeGraph.fail_on = {("NVDA", "2026-01-05")}
    result = run_backtest(["NVDA"], ["2026-01-05", "2026-01-12"], _config(tmp_path))

    assert result.cells_run == 1
    assert result.failures == [("NVDA", "2026-01-05", "vendor exploded")]


# --- reading the result ------------------------------------------------------

def _log_with(tmp_path, rows):
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    for ticker, date, decision, outcome in rows:
        log.store_decision(ticker, date, decision)
        if outcome is not None:
            log.update_with_outcome(ticker, date, outcome[0], outcome[1], 5, "note", "2026-02-01")
    return log


@pytest.mark.unit
def test_summary_scores_resolved_cells_and_keeps_pending_out_of_the_average(tmp_path):
    log = _log_with(tmp_path, [
        ("NVDA", "2026-01-05", "Rating: Buy\n\nx", (0.10, 0.04)),
        ("NVDA", "2026-01-12", "Rating: Buy\n\nx", (-0.02, -0.02)),
        ("AAPL", "2026-01-05", "Rating: Sell\n\nx", None),
    ])

    summary = summarize(log)

    assert summary.resolved == 2 and summary.pending == 1
    buys = summary.by_rating["Buy"]
    assert buys.count == 2 and buys.hit_rate == 0.5 and round(buys.mean_alpha, 4) == 0.01
    assert "Sell" not in summary.by_rating  # unsettled: nothing to score yet


@pytest.mark.unit
def test_summary_states_what_it_cannot_prove(tmp_path):
    text = summarize(_log_with(tmp_path, [("NVDA", "2026-01-05", DECISION, (0.1, 0.05))])).render()
    assert "not archived" in text
    assert "one" in text.lower() and "sampl" in text.lower()


@pytest.mark.unit
def test_the_analyst_set_under_test_is_the_one_that_runs(tmp_path):
    """A backtest of a two-analyst setup must not silently run four."""
    run_backtest(["NVDA"], ["2026-01-05"], _config(tmp_path), selected_analysts=["market", "news"])
    assert _FakeGraph.instances[-1].analysts == ["market", "news"]


@pytest.mark.unit
def test_a_run_id_cannot_escape_the_results_directory(tmp_path):
    """run_id becomes a path segment, so it is validated like a ticker is."""
    with pytest.raises(ValueError):
        run_backtest(["NVDA"], ["2026-01-05"], _config(tmp_path), run_id="../../escaped")
    with pytest.raises(ValueError):
        run_backtest(["NVDA"], ["2026-01-05"], _config(tmp_path), run_id="/etc/cron.d/x")


@pytest.mark.unit
def test_a_failed_settlement_does_not_lose_the_remaining_tickers(tmp_path, monkeypatch):
    """Settlement reflects with an LLM, so it can fail; the sweep still returns
    its result and every other ticker still gets settled."""
    settled = []

    def _settle(self, ticker):
        if ticker == "NVDA":
            raise RuntimeError("reflector timed out")
        settled.append(ticker)

    monkeypatch.setattr(_FakeGraph, "settle_pending", _settle, raising=False)
    result = run_backtest(["NVDA", "AAPL"], ["2026-01-05"], _config(tmp_path))

    assert result.cells_run == 2
    assert settled == ["AAPL"]
    assert result.settlement_failures == [("NVDA", "reflector timed out")]


@pytest.mark.unit
def test_pending_note_appears_only_when_something_is_pending(tmp_path):
    settled = [("NVDA", "2026-01-05", DECISION, (0.1, 0.05))]
    assert "Pending" not in summarize(_log_with(tmp_path, settled)).render()
    assert "Pending" in summarize(_log_with(tmp_path, settled + [("AAPL", "2026-01-05", DECISION, None)])).render()


# --- scoring reads the direction the rating claimed ---------------------------

def _scored(tmp_path, rows):
    log = _log_with(tmp_path, rows)
    return summarize(log).by_rating


@pytest.mark.unit
def test_a_bearish_call_that_fell_counts_as_right(tmp_path):
    """Alpha below the benchmark is the outcome a Sell predicted; scoring it as
    a miss reported the system as wrong exactly when it was right."""
    scores = _scored(tmp_path, [
        ("NVDA", "2026-01-05", "**Rating**: Sell\n\nx", (-0.08, -0.05)),
        ("AAPL", "2026-01-05", "**Rating**: Underweight\n\nx", (-0.03, -0.02)),
    ])
    assert scores["Sell"].hit_rate == 1.0
    assert scores["Underweight"].hit_rate == 1.0


@pytest.mark.unit
def test_a_bearish_call_that_rose_counts_as_wrong(tmp_path):
    scores = _scored(tmp_path, [("NVDA", "2026-01-05", "**Rating**: Sell\n\nx", (0.08, 0.05))])
    assert scores["Sell"].hit_rate == 0.0


@pytest.mark.unit
def test_a_bullish_call_is_scored_the_same_way_as_before(tmp_path):
    scores = _scored(tmp_path, [
        ("NVDA", "2026-01-05", "**Rating**: Buy\n\nx", (0.10, 0.04)),
        ("AAPL", "2026-01-05", "**Rating**: Buy\n\nx", (-0.02, -0.02)),
    ])
    assert scores["Buy"].hit_rate == 0.5


@pytest.mark.unit
def test_hold_claims_no_direction_so_it_gets_no_hit_rate(tmp_path):
    scores = _scored(tmp_path, [("NVDA", "2026-01-05", "**Rating**: Hold\n\nx", (0.01, 0.005))])
    assert scores["Hold"].hit_rate is None
    assert scores["Hold"].mean_alpha == 0.005


@pytest.mark.unit
def test_the_report_names_the_window_the_scores_cover(tmp_path):
    text = summarize(_log_with(tmp_path, [
        ("NVDA", "2026-01-05", "**Rating**: Buy\n\nx", (0.1, 0.05))])).render()
    assert "5" in text and "day" in text.lower()
    assert "Hold" not in text or "no direction" in text.lower()


@pytest.mark.unit
def test_the_window_reported_is_the_one_the_outcomes_used(tmp_path):
    """The log records the window each outcome was measured over; the summary
    must not claim a different one."""
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    log.store_decision("NVDA", "2026-01-05", "**Rating**: Buy\n\nx")
    log.update_with_outcome("NVDA", "2026-01-05", 0.1, 0.04, 21, "note", "2026-02-01")

    assert "21 trading days" in summarize(log).render()
