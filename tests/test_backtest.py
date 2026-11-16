"""Backtesting: many single-shot decisions, scored by the memory log.

A run already records its rating and later settles it with realized and alpha
return against the regional benchmark. A backtest is that machinery over a grid
of tickers and dates, aggregated. It evaluates decision quality; it does not
simulate a portfolio, so there is no execution, no fees and no equity curve.
"""

from __future__ import annotations

import random

import pytest

from tradingagents.backtest import (
    iter_grid,
    rating_shuffle_test,
    run_backtest,
    summarize,
)
from tradingagents.memory import TradingMemoryLog
from tradingagents.memory.settlement import Settlement

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
        return Settlement()


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
def test_the_live_memory_log_is_never_written(tmp_path):
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
    return tmp_path / "m.md"


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
def test_sweeps_started_in_the_same_second_get_their_own_runs(tmp_path, monkeypatch):
    import tradingagents.backtest as backtest

    class _Frozen(backtest.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 20, 9, 30, 0)

    monkeypatch.setattr(backtest, "datetime", _Frozen)
    first = run_backtest(["NVDA"], ["2026-01-05"], _config(tmp_path))
    second = run_backtest(["NVDA"], ["2026-01-05"], _config(tmp_path))

    assert first.run_id == "20260120_093000" and second.run_id == "20260120_093000_2"
    assert first.cells_run == second.cells_run == 1


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
        return Settlement()

    monkeypatch.setattr(_FakeGraph, "settle_pending", _settle, raising=False)
    result = run_backtest(["NVDA", "AAPL"], ["2026-01-05"], _config(tmp_path))

    assert result.cells_run == 2
    assert settled == ["AAPL"]
    assert result.settlement_failures == [("NVDA", "reflector timed out")]


@pytest.mark.unit
@pytest.mark.parametrize("failure", ["prices", "reflection"])
def test_handled_settlement_failures_reach_the_backtest_result(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace

    from tradingagents.memory import settlement

    def returns(ticker, *args, **kwargs):
        if ticker == "AAPL":
            return None, None, None, None  # an incomplete window is not a failure
        if failure == "prices":
            raise RuntimeError("vendor unavailable")
        return 0.1, 0.02, 5, "2026-02-01"

    def reflect(**kwargs):
        raise RuntimeError("reflector timed out")

    def settle(self, ticker):
        self.settled.append(ticker)
        return settlement.settle_pending(
            ticker, self.memory_log, SimpleNamespace(reflect_on_final_decision=reflect), self.config,
        )

    monkeypatch.setattr(settlement, "fetch_returns", returns)
    monkeypatch.setattr(_FakeGraph, "settle_pending", settle)
    result = run_backtest(
        ["NVDA", "AAPL"], ["2026-01-05", "2026-01-12"], _config(tmp_path),
    )

    reason = ("prices unavailable: vendor unavailable" if failure == "prices"
              else "reflection failed: reflector timed out")
    assert result.settlement_failures == [
        ("NVDA", f"2026-01-05: {reason}"),
        ("NVDA", f"2026-01-12: {reason}"),
    ]
    assert _FakeGraph.instances[-1].settled == ["NVDA", "AAPL"]
    assert result.cells_run == 4 and not result.failures
    assert len(_FakeGraph.instances[-1].memory_log.get_pending_entries()) == 4


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

    assert "21 trading days" in summarize(tmp_path / "m.md").render()


@pytest.mark.unit
def test_a_backtest_result_is_summarized_directly(tmp_path):
    """The result names its own log, so a caller never builds the log to score it."""
    from tradingagents.backtest import BacktestResult

    path = _log_with(tmp_path, [("NVDA", "2026-01-05", "Rating: Buy\n\nx", (0.10, 0.04))])

    assert summarize(BacktestResult(run_id="r", log_path=path)).resolved == 1


@pytest.mark.unit
def test_a_log_path_that_does_not_exist_is_an_error_not_an_empty_summary(tmp_path):
    missing = tmp_path / "no-such-dir" / "m.md"

    with pytest.raises(FileNotFoundError):
        summarize(missing)
    assert not missing.parent.exists()


@pytest.mark.unit
def test_a_result_whose_cells_all_failed_summarizes_as_empty(tmp_path):
    from tradingagents.backtest import BacktestResult

    result = BacktestResult(run_id="r", log_path=tmp_path / "never-written.md")

    assert summarize(result).resolved == 0


@pytest.mark.unit
def test_progress_is_reported_before_each_cell(tmp_path):
    seen = []

    run_backtest(["NVDA", "AAPL"], ["2026-01-05", "2026-01-12"], _config(tmp_path),
                 progress=lambda done, total, ticker, date: seen.append((done, total, ticker, date)))

    assert seen == [(1, 4, "NVDA", "2026-01-05"), (2, 4, "NVDA", "2026-01-12"),
                    (3, 4, "AAPL", "2026-01-05"), (4, 4, "AAPL", "2026-01-12")]


@pytest.mark.unit
def test_a_resumed_sweep_reports_only_the_cells_it_runs(tmp_path):
    first = run_backtest(["NVDA"], ["2026-01-05"], _config(tmp_path))
    seen = []

    run_backtest(["NVDA"], ["2026-01-05", "2026-01-12"], _config(tmp_path), run_id=first.run_id,
                 progress=lambda done, total, ticker, date: seen.append((done, total, date)))

    assert seen == [(1, 1, "2026-01-12")]


@pytest.mark.unit
def test_a_ticker_or_date_given_twice_runs_and_settles_once(tmp_path):
    run_backtest(["NVDA", "NVDA"], ["2026-01-05", "2026-01-05"], _config(tmp_path))
    graph = _FakeGraph.instances[-1]
    assert graph.calls == [("NVDA", "2026-01-05")]
    assert graph.settled == ["NVDA"]


# --- the rating-shuffle test -------------------------------------------------
# A grid is a handful of cells, so a 60% hit rate or a +1% mean alpha is often
# inside the noise. These pin the check that says whether the ratings did better
# than the same ratings handed out at random on the same dates.

def _no_skill_grid(seed: int, *, dates: int = 6, tickers: int = 4):
    """Ratings and outcomes drawn independently: whatever the ratings claim is luck."""
    ratings = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
    rng = random.Random(seed)
    return [(f"2026-01-{day:02d}", rng.choice(ratings), rng.gauss(0, 0.02))
            for day in range(1, dates + 1) for _ in range(tickers)]


def _planted_edge(dates: int = 8):
    """Every date's Buy is the day's best cell and its Sell the worst."""
    outcomes = (0.03, 0.02, 0.01, 0.0, -0.01, -0.03)
    claimed = ("Buy", "Overweight", "Hold", "Hold", "Underweight", "Sell")
    return [(f"2026-01-{day:02d}", rating, alpha)
            for day in range(1, dates + 1)
            for rating, alpha in zip(claimed, outcomes, strict=True)]


@pytest.mark.unit
def test_a_grid_with_no_skill_clears_the_bar_only_about_as_often_as_chance():
    """Calibration: a 60% hit rate on luck has to read as luck, not as an edge."""
    flagged = sum(rating_shuffle_test(_no_skill_grid(seed), n=200).p_value < 0.05
                  for seed in range(40))

    assert flagged <= 3


@pytest.mark.unit
def test_ratings_that_called_the_outcomes_read_as_significant():
    result = rating_shuffle_test(_planted_edge(), n=2000)

    assert result.observed == pytest.approx(0.0225)
    assert result.observed > result.null_p95
    assert result.p_value < 0.01


@pytest.mark.unit
def test_one_date_where_every_cell_rose_cannot_read_as_skill():
    """Within-date shuffling holds the day's market move fixed, so a single
    uniform day leaves nothing for the ratings to take credit for."""
    cells = [("2026-01-05", rating, 0.05)
             for rating in ("Buy", "Buy", "Buy", "Sell", "Overweight", "Underweight")]

    result = rating_shuffle_test(cells, n=300)

    assert result is not None
    assert result.observed == pytest.approx(2 * 0.05 / 6)
    # Every shuffle only reorders the same products, so the tie has to be exact:
    # a left-to-right float sum leaves it one ulp off, which read as p = 0.42 on
    # Python 3.11 (where sum() has no compensated summation) before math.fsum.
    assert result.null_median == result.null_p95 == result.observed
    assert result.p_value == 1.0


@pytest.mark.unit
def test_dates_with_one_cell_each_fall_back_and_say_so():
    cells = [(f"2026-01-{day:02d}", "Buy" if day % 2 else "Sell", 0.02 if day % 2 else -0.02)
             for day in range(1, 9)]

    result = rating_shuffle_test(cells, n=300)

    assert result.scope.startswith("across all cells")
    assert "across all cells" in result.render()


@pytest.mark.unit
def test_nothing_directional_reports_nothing():
    assert rating_shuffle_test([("2026-01-05", "Hold", 0.01)] * 5) is None


@pytest.mark.unit
def test_a_rating_the_table_does_not_know_is_not_scored():
    result = rating_shuffle_test([("2026-01-05", "Buy", 0.02), ("2026-01-05", "Rating: Nonsense", 0.02)])

    assert result.cells == 1


@pytest.mark.unit
def test_the_p_value_never_reaches_zero():
    """Nothing over a finite number of shuffles is infinitely unlikely."""
    result = rating_shuffle_test(_planted_edge(), n=100)

    assert result.p_value >= 1 / (1 + 100)


@pytest.mark.unit
def test_the_same_cells_give_the_same_answer():
    assert rating_shuffle_test(_no_skill_grid(3), n=200) == rating_shuffle_test(_no_skill_grid(3), n=200)


@pytest.mark.unit
def test_the_summary_reports_the_shuffle_test_over_the_settled_cells(tmp_path):
    log = _log_with(tmp_path, [
        ("NVDA", "2026-01-05", "Rating: Buy\n\nx", (0.03, 3.0)),
        ("AAPL", "2026-01-05", "Rating: Sell\n\nx", (-0.03, -3.0)),
        ("NVDA", "2026-01-12", "Rating: Buy\n\nx", (0.02, 2.0)),
        ("AAPL", "2026-01-12", "Rating: Sell\n\nx", (-0.02, -2.0)),
        ("NVDA", "2026-01-19", "Rating: Buy\n\nx", None),
    ])

    summary = summarize(log)

    assert summary.shuffle is not None and summary.shuffle.cells == 4
    assert "Rating-shuffle test: 4 directional cells" in summary.render()


@pytest.mark.unit
def test_a_summary_whose_cells_claimed_no_direction_omits_the_line(tmp_path):
    log = _log_with(tmp_path, [("NVDA", "2026-01-05", "Rating: Hold\n\nx", (0.03, 3.0))])

    assert summarize(log).shuffle is None
    assert "Rating-shuffle" not in summarize(log).render()
