"""Tests for the backtest runner — scheduling, resume, isolation, failure handling.

No LLM or network is involved: the runner takes an injected graph factory, and
these tests supply stubs that return canned ratings.
"""

import threading

import pytest

from tradingagents.backtest.runner import (
    BacktestRunner,
    BacktestSpec,
    RunProgress,
    run_signature,
)
from tradingagents.backtest.store import DecisionStore

CONFIG = {
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.6",
    "quick_think_llm": "gpt-5.6-luna",
}


class StubGraph:
    """Minimal stand-in for TradingAgentsGraph."""

    def __init__(self, ratings=None, fail_on=None, config=None, handler=None):
        self._ratings = ratings or {}
        self._fail_on = fail_on or set()
        self.config = config or {}
        self.handler = handler
        self.calls: list[tuple[str, str]] = []
        self.curr_state = {}

    def propagate(self, company_name, trade_date, asset_type="stock"):
        self.calls.append((company_name, trade_date))
        if trade_date in self._fail_on:
            raise RuntimeError("provider exploded")
        rating = self._ratings.get(trade_date, "Buy")
        self.curr_state = {"final_trade_decision": f"Rating: {rating}"}
        if self.handler is not None:
            self.handler.tokens_in += 1000
            self.handler.tokens_out += 200
            self.handler.llm_calls += 3
        return self.curr_state, rating


def make_factory(graphs=None, **kwargs):
    """Graph factory that records the config it was handed, per ticker."""
    graphs = graphs if graphs is not None else {}

    def factory(ticker, config, callbacks):
        graph = StubGraph(config=config, handler=callbacks[0], **kwargs)
        graphs.setdefault(ticker, []).append(graph)
        return graph

    return factory


def make_runner(tmp_path, spec=None, factory=None, config=None, **kwargs):
    spec = spec or BacktestSpec(
        tickers=["NVDA"], start="2026-01-05", end="2026-01-16", every_n_days=5
    )
    return BacktestRunner(
        spec=spec,
        store=DecisionStore(tmp_path / "decisions.jsonl"),
        graph_factory=factory or make_factory(),
        config=config or CONFIG,
        memory_dir=tmp_path / "memory",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Scheduling and recording
# ---------------------------------------------------------------------------

def test_runs_every_scheduled_date_and_stores_each_decision(tmp_path):
    runner = make_runner(tmp_path)
    summary = runner.run()

    # 2026-01-05, -12 on a 5-business-day stride through 2026-01-16.
    assert summary.total_points == 2
    assert summary.produced == 2
    assert summary.failed == 0
    assert [r.date for r in runner.store.decisions()] == ["2026-01-05", "2026-01-12"]


def test_records_carry_the_rating_and_decision_text(tmp_path):
    runner = make_runner(tmp_path, factory=make_factory(ratings={"2026-01-05": "Sell"}))
    runner.run()

    record = runner.store.decisions()[0]
    assert record.rating == "Sell"
    assert record.decision == "Rating: Sell"


def test_token_usage_is_attributed_per_decision(tmp_path):
    """The handler accumulates for the graph's lifetime; each record gets its delta."""
    runner = make_runner(tmp_path)
    runner.run()

    records = runner.store.decisions()
    assert len(records) == 2
    for record in records:
        assert record.tokens_in == 1000
        assert record.tokens_out == 200
        assert record.llm_calls == 3


def test_multiple_tickers_each_get_a_full_schedule(tmp_path):
    spec = BacktestSpec(
        tickers=["NVDA", "AAPL"], start="2026-01-05", end="2026-01-16", every_n_days=5
    )
    runner = make_runner(tmp_path, spec=spec)
    summary = runner.run()

    assert summary.total_points == 4
    assert summary.produced == 4
    assert runner.store.tickers() == ["AAPL", "NVDA"]


def test_tickers_are_normalized_to_upper_case():
    spec = BacktestSpec(tickers=[" nvda ", "aapl"], start="2026-01-05", end="2026-01-16")

    assert spec.tickers == ["NVDA", "AAPL"]


# ---------------------------------------------------------------------------
# Graph reuse
# ---------------------------------------------------------------------------

def test_one_graph_is_built_per_ticker_not_per_decision(tmp_path):
    """Constructing a graph builds LLM clients and compiles the workflow."""
    graphs = {}
    runner = make_runner(tmp_path, factory=make_factory(graphs))
    runner.run()

    assert len(graphs["NVDA"]) == 1
    assert len(graphs["NVDA"][0].calls) == 2


def test_no_graph_is_built_when_everything_is_already_stored(tmp_path):
    graphs = {}
    make_runner(tmp_path, factory=make_factory(graphs)).run()

    second_graphs = {}
    make_runner(tmp_path, factory=make_factory(second_graphs)).run()

    assert second_graphs == {}


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def test_resume_skips_stored_points(tmp_path):
    make_runner(tmp_path).run()

    resumed = make_runner(tmp_path)
    summary = resumed.run()

    assert summary.produced == 0
    assert summary.skipped == 2


def test_resume_retries_a_previously_failed_point(tmp_path):
    """A failed date is a gap to retry, not work that is done."""
    first = make_runner(tmp_path, factory=make_factory(fail_on={"2026-01-12"}))
    first_summary = first.run()
    assert first_summary.failed == 1

    second = make_runner(tmp_path)
    second_summary = second.run()

    assert second_summary.skipped == 1        # 2026-01-05 was fine
    assert second_summary.produced == 1       # 2026-01-12 retried and worked
    assert [r.date for r in second.store.decisions()] == ["2026-01-05", "2026-01-12"]


def test_changing_the_model_starts_a_fresh_experiment(tmp_path):
    make_runner(tmp_path).run()

    other_config = dict(CONFIG, deep_think_llm="claude-opus-5")
    resumed = make_runner(tmp_path, config=other_config)
    summary = resumed.run()

    assert summary.skipped == 0
    assert summary.produced == 2


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------

def test_one_bad_date_does_not_abort_the_run(tmp_path):
    runner = make_runner(tmp_path, factory=make_factory(fail_on={"2026-01-05"}))
    summary = runner.run()

    assert summary.failed == 1
    assert summary.produced == 1
    failure = runner.store.failures()[0]
    assert failure.date == "2026-01-05"
    assert "provider exploded" in failure.error


def test_a_failing_graph_factory_is_recorded_not_raised(tmp_path):
    def exploding_factory(ticker, config, callbacks):
        raise RuntimeError("no API key")

    runner = make_runner(tmp_path, factory=exploding_factory)
    summary = runner.run()

    assert summary.produced == 0
    assert summary.failed == 2
    assert all("no API key" in r.error for r in runner.store.failures())


# ---------------------------------------------------------------------------
# Memory-log isolation
# ---------------------------------------------------------------------------

def test_each_ticker_gets_its_own_decision_log(tmp_path):
    """The log is rewritten whole on update, so sharing one file across
    concurrent tickers would lose reflections."""
    graphs = {}
    spec = BacktestSpec(
        tickers=["NVDA", "AAPL"], start="2026-01-05", end="2026-01-09", every_n_days=5
    )
    make_runner(tmp_path, spec=spec, factory=make_factory(graphs)).run()

    paths = {t: graphs[t][0].config["memory_log_path"] for t in ("NVDA", "AAPL")}
    assert paths["NVDA"] != paths["AAPL"]
    assert paths["NVDA"].endswith("NVDA.md")


def test_the_live_memory_log_is_left_alone(tmp_path):
    """A backtest's reflections are simulated history, not the user's record."""
    graphs = {}
    config = dict(CONFIG, memory_log_path=str(tmp_path / "live" / "trading_memory.md"))
    make_runner(tmp_path, factory=make_factory(graphs), config=config).run()

    assert graphs["NVDA"][0].config["memory_log_path"] != config["memory_log_path"]
    assert not (tmp_path / "live" / "trading_memory.md").exists()


@pytest.mark.parametrize("ticker", ["../../etc/passwd", "a/b", "..\\win"])
def test_path_traversal_in_a_ticker_is_rejected_up_front(ticker):
    """Caught at spec validation, not once per scheduled date."""
    with pytest.raises(ValueError, match="not allowed in a filesystem path"):
        BacktestSpec(tickers=[ticker], start="2026-01-05", end="2026-01-09")


def test_whitespace_only_tickers_are_rejected():
    with pytest.raises(ValueError, match="at least one ticker"):
        BacktestSpec(tickers=["  ", ""], start="2026-01-05", end="2026-01-09")


# ---------------------------------------------------------------------------
# Progress reporting and concurrency
# ---------------------------------------------------------------------------

def test_progress_is_reported_for_each_point(tmp_path):
    seen: list[RunProgress] = []
    runner = make_runner(tmp_path, on_progress=seen.append)
    runner.run()

    assert [p.index for p in seen] == [1, 2]
    assert all(p.total == 2 for p in seen)
    assert [p.rating for p in seen] == ["Buy", "Buy"]


def test_progress_marks_skipped_points_on_resume(tmp_path):
    make_runner(tmp_path).run()

    seen: list[RunProgress] = []
    make_runner(tmp_path, on_progress=seen.append).run()

    assert all(p.skipped for p in seen)


def test_concurrent_tickers_do_not_lose_records(tmp_path):
    spec = BacktestSpec(
        tickers=[f"T{i}" for i in range(6)],
        start="2026-01-05", end="2026-01-30", every_n_days=5, max_workers=4,
    )
    runner = make_runner(tmp_path, spec=spec)
    summary = runner.run()

    assert summary.produced == summary.total_points
    assert len(runner.store.decisions()) == summary.total_points


def test_concurrent_tickers_run_on_separate_threads(tmp_path):
    threads: set[int] = set()

    def factory(ticker, config, callbacks):
        threads.add(threading.get_ident())
        return StubGraph(config=config, handler=callbacks[0])

    spec = BacktestSpec(
        tickers=["A", "B", "C", "D"], start="2026-01-05", end="2026-01-16", max_workers=4
    )
    make_runner(tmp_path, spec=spec, factory=factory).run()

    assert len(threads) > 1


def test_a_ticker_runs_its_dates_in_order(tmp_path):
    """The decision log is causal: a run reflects on earlier same-ticker runs."""
    graphs = {}
    spec = BacktestSpec(
        tickers=["NVDA"], start="2026-01-05", end="2026-02-27", every_n_days=5
    )
    make_runner(tmp_path, spec=spec, factory=make_factory(graphs)).run()

    dates = [d for _, d in graphs["NVDA"][0].calls]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Signature and spec validation
# ---------------------------------------------------------------------------

def test_signature_covers_models_and_graph_shape():
    signature = run_signature(CONFIG, ("market", "news"), "stock")

    assert "analysts=market,news" in signature
    assert "deep=gpt-5.6" in signature
    assert "quick=gpt-5.6-luna" in signature
    assert "asset=stock" in signature


@pytest.mark.parametrize("field,value", [
    ("deep_think_llm", "other-model"),
    ("max_debate_rounds", 3),
    ("llm_provider", "anthropic"),
])
def test_signature_changes_with_config(field, value):
    base = run_signature(CONFIG, ("market",))
    changed = run_signature(dict(CONFIG, **{field: value}), ("market",))

    assert base != changed


def test_empty_ticker_list_raises():
    with pytest.raises(ValueError, match="at least one ticker"):
        BacktestSpec(tickers=[], start="2026-01-05", end="2026-01-16")


def test_non_positive_workers_raises():
    with pytest.raises(ValueError, match="max_workers must be >= 1"):
        BacktestSpec(
            tickers=["NVDA"], start="2026-01-05", end="2026-01-16", max_workers=0
        )


def test_empty_schedule_produces_nothing(tmp_path):
    spec = BacktestSpec(tickers=["NVDA"], start="2026-01-10", end="2026-01-11")
    runner = make_runner(tmp_path, spec=spec)
    summary = runner.run()

    assert summary.total_points == 0
    assert summary.produced == 0
