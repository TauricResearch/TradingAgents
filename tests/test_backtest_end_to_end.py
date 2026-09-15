"""End-to-end backtest: run the graph over a schedule, then score it.

Uses a stub graph and a stub price fetcher, so the whole path — schedule,
runner, store, resume, portfolio, metrics, scorecard — runs offline.
"""

import pandas as pd
import pytest
from typer.testing import CliRunner

from tradingagents.backtest.portfolio import PortfolioConfig
from tradingagents.backtest.prices import load_prices
from tradingagents.backtest.report import score, write_report
from tradingagents.backtest.runner import BacktestRunner, BacktestSpec
from tradingagents.backtest.store import DecisionStore

CONFIG = {
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.6",
    "quick_think_llm": "gpt-5.6-luna",
    "benchmark_map": {"": "SPY"},
    "llm_prices": {"gpt-5.6": {"input": 1.0, "output": 5.0}},
}

# A market that rises for the first half and falls for the second, so a
# perfectly-timed agent and a badly-timed one produce visibly different curves.
def market(n=60):
    dates = pd.bdate_range("2026-01-05", periods=n)
    prices = [100.0 + i for i in range(n // 2)]
    prices += [prices[-1] - i for i in range(n - n // 2)]
    return pd.DataFrame({"Open": prices, "Close": prices}, index=dates)


class ScriptedGraph:
    """Emits a preset rating sequence, one per propagate call.

    Reports a fixed token spend through the usage handler so the cost columns
    are exercised with real arithmetic rather than zeros.
    """

    # One million input tokens per decision, so at the $1.00/1M input rate in
    # CONFIG each decision costs exactly $1.
    TOKENS_IN_PER_CALL = 1_000_000

    def __init__(self, ratings, handler=None):
        self._ratings = list(ratings)
        self._calls = 0
        self._handler = handler
        self.curr_state = {}

    def propagate(self, company_name, trade_date, asset_type="stock"):
        rating = self._ratings[self._calls % len(self._ratings)]
        self._calls += 1
        if self._handler is not None:
            self._handler.tokens_in += self.TOKENS_IN_PER_CALL
            self._handler.llm_calls += 2
        self.curr_state = {"final_trade_decision": f"Rating: {rating}"}
        return self.curr_state, rating


def run_backtest(tmp_path, ratings, prices=None, label="run"):
    prices = prices if prices is not None else market()
    out_dir = tmp_path / label
    store = DecisionStore(out_dir / "decisions.jsonl")
    spec = BacktestSpec(
        tickers=["NVDA"], start="2026-01-05", end="2026-03-13", every_n_days=5
    )
    runner = BacktestRunner(
        spec=spec, store=store,
        graph_factory=lambda t, c, cb: ScriptedGraph(ratings, handler=cb[0]),
        config=CONFIG, memory_dir=out_dir / "memory",
    )
    summary = runner.run()

    loaded = load_prices(
        spec.tickers, spec.start, spec.end,
        cache_dir=out_dir / "prices", fetcher=lambda *a: prices,
    )
    payload = score(
        store, loaded, signature=runner.signature,
        benchmark="SPY", benchmark_prices=prices,
        config=PortfolioConfig(), n_baseline_trials=20,
    )
    return summary, payload, out_dir


def test_a_full_backtest_produces_a_scorecard(tmp_path):
    summary, payload, out_dir = run_backtest(tmp_path, ["Buy", "Hold", "Sell"])

    assert summary.produced == summary.total_points
    assert summary.failed == 0
    assert payload["coverage"]["n_decisions"] == summary.produced
    assert payload["performance"]["total_return"] is not None

    path = write_report(payload, out_dir)
    text = path.read_text(encoding="utf-8")
    assert "# Backtest scorecard" in text
    assert "Against the baselines" in text


def test_a_well_timed_agent_beats_a_badly_timed_one(tmp_path):
    """The harness must be able to tell good calls from bad ones."""
    prices = market()
    # Buy the rise, sell the fall.
    _, good, _ = run_backtest(
        tmp_path, ["Buy"] * 6 + ["Sell"] * 6, prices=prices, label="good"
    )
    # Exactly inverted.
    _, bad, _ = run_backtest(
        tmp_path, ["Sell"] * 6 + ["Buy"] * 6, prices=prices, label="bad"
    )

    assert good["performance"]["total_return"] > bad["performance"]["total_return"]
    assert good["trading"]["hit_rate"] > bad["trading"]["hit_rate"]


def test_costs_are_attributed_and_priced(tmp_path):
    summary, payload, _ = run_backtest(tmp_path, ["Buy", "Hold"])
    n = summary.produced

    # $1.00/1M input tokens x 1M tokens per decision = $1 per decision.
    assert payload["cost"]["tokens_in"] == n * ScriptedGraph.TOKENS_IN_PER_CALL
    assert payload["cost"]["llm_calls"] == n * 2
    assert payload["cost"]["total_usd"] == pytest.approx(float(n))
    assert payload["cost"]["unpriced_decisions"] == 0


def test_cost_per_point_of_alpha_is_reported(tmp_path):
    _, payload, _ = run_backtest(tmp_path, ["Buy"] * 6 + ["Sell"] * 6)

    alpha = payload["alpha"]
    spend = payload["cost"]["total_usd"]
    assert alpha > 0
    assert payload["cost"]["cost_per_alpha_point"] == pytest.approx(
        spend / (alpha * 100)
    )


def test_an_unpriced_model_reports_tokens_without_dollars(tmp_path):
    """The default config prices nothing, so spend must stay absent."""
    out_dir = tmp_path / "unpriced"
    spec = BacktestSpec(
        tickers=["NVDA"], start="2026-01-05", end="2026-02-06", every_n_days=5
    )
    runner = BacktestRunner(
        spec=spec, store=DecisionStore(out_dir / "decisions.jsonl"),
        graph_factory=lambda t, c, cb: ScriptedGraph(["Buy"], handler=cb[0]),
        config={k: v for k, v in CONFIG.items() if k != "llm_prices"},
        memory_dir=out_dir / "memory",
    )
    runner.run()

    loaded = load_prices(
        ["NVDA"], spec.start, spec.end,
        cache_dir=out_dir / "prices", fetcher=lambda *a: market(),
    )
    payload = score(runner.store, loaded, signature=runner.signature)

    assert payload["cost"]["tokens_in"] > 0
    assert payload["cost"]["total_usd"] is None
    assert payload["cost"]["unpriced_decisions"] == payload["coverage"]["n_decisions"]


def test_rescoring_changes_the_result_without_rerunning_agents(tmp_path):
    """The whole point of the store: execution rules are cheap to vary."""
    prices = market()
    _, first, out_dir = run_backtest(tmp_path, ["Buy", "Hold", "Sell"], prices=prices)

    store = DecisionStore(out_dir / "decisions.jsonl")
    signature = first["signature"]
    loaded = load_prices(
        ["NVDA"], "2026-01-05", "2026-03-13",
        cache_dir=out_dir / "prices", fetcher=lambda *a: prices,
    )

    carried = score(store, loaded, signature=signature,
                    config=PortfolioConfig(hold_policy="carry"))
    flat = score(store, loaded, signature=signature,
                 config=PortfolioConfig(hold_policy="flat"))

    # Same decisions, different execution rule, different curve.
    assert carried["trading"]["n_trades"] != flat["trading"]["n_trades"]


def test_an_interrupted_run_resumes_without_losing_decisions(tmp_path):
    prices = market()
    out_dir = tmp_path / "resumable"
    spec = BacktestSpec(
        tickers=["NVDA"], start="2026-01-05", end="2026-03-13", every_n_days=5
    )

    # First pass: every other date fails.
    class FlakyGraph:
        def __init__(self):
            self.calls = 0
            self.curr_state = {}

        def propagate(self, company_name, trade_date, asset_type="stock"):
            self.calls += 1
            if self.calls % 2 == 0:
                raise RuntimeError("rate limited")
            self.curr_state = {"final_trade_decision": "Rating: Buy"}
            return self.curr_state, "Buy"

    flaky = FlakyGraph()
    first = BacktestRunner(
        spec=spec, store=DecisionStore(out_dir / "decisions.jsonl"),
        graph_factory=lambda t, c, cb: flaky, config=CONFIG,
        memory_dir=out_dir / "memory",
    )
    first_summary = first.run()
    assert first_summary.failed > 0

    # Second pass: a healthy graph fills only the gaps.
    healthy = ScriptedGraph(["Buy"])
    second = BacktestRunner(
        spec=spec, store=DecisionStore(out_dir / "decisions.jsonl"),
        graph_factory=lambda t, c, cb: healthy, config=CONFIG,
        memory_dir=out_dir / "memory",
    )
    second_summary = second.run()

    assert second_summary.skipped == first_summary.produced
    assert second_summary.produced == first_summary.failed

    loaded = load_prices(
        ["NVDA"], "2026-01-05", "2026-03-13",
        cache_dir=out_dir / "prices", fetcher=lambda *a: prices,
    )
    payload = score(
        DecisionStore(out_dir / "decisions.jsonl"), loaded,
        signature=second.signature,
    )
    assert payload["coverage"]["n_decisions"] == spec_points(spec)
    assert payload["coverage"]["n_failed"] == first_summary.failed


def spec_points(spec):
    from tradingagents.backtest.schedule import decision_dates

    return len(decision_dates(spec.start, spec.end, spec.every_n_days))


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def test_backtest_command_is_registered():
    from cli import main as cli_main

    result = CliRunner().invoke(cli_main.app, ["backtest", "--help"])

    assert result.exit_code == 0
    assert "--strict-point-in-time" in result.output


def test_a_bare_invocation_still_runs_the_analysis(monkeypatch):
    """`tradingagents` with no subcommand ran analyze before backtest existed."""
    from cli import main as cli_main

    called = {}
    monkeypatch.setattr(
        cli_main, "run_analysis", lambda **kw: called.setdefault("ran", kw)
    )

    result = CliRunner().invoke(cli_main.app, [])

    assert result.exit_code == 0
    assert called["ran"] == {"checkpoint": None}


def test_analyze_is_still_addressable_by_name(monkeypatch):
    from cli import main as cli_main

    called = {}
    monkeypatch.setattr(
        cli_main, "run_analysis", lambda **kw: called.setdefault("ran", kw)
    )

    result = CliRunner().invoke(cli_main.app, ["analyze", "--checkpoint"])

    assert result.exit_code == 0
    assert called["ran"] == {"checkpoint": True}


_BASE_ARGS = ["backtest", "--tickers", "NVDA", "--start", "2026-01-01", "--end", "2026-06-01"]


@pytest.mark.parametrize("args", [
    ["backtest", "--tickers", "NVDA", "--start", "2026-06-01", "--end", "2026-01-01"],
    ["backtest", "--tickers", "", "--start", "2026-01-01", "--end", "2026-06-01"],
    ["backtest", "--tickers", "../etc", "--start", "2026-01-01", "--end", "2026-06-01"],
    [*_BASE_ARGS, "--hold-policy", "hold"],
    [*_BASE_ARGS, "--capital", "0"],
    [*_BASE_ARGS, "--commission-bps", "-1"],
])
def test_bad_backtest_arguments_exit_cleanly(args, monkeypatch):
    """Every invalid flag must be caught before any agent runs.

    The execution rules are only used when scoring, so building them after the
    replay would let a typo discard a backtest that had already been paid for.
    """
    from cli import backtest_command, main as cli_main

    def never(*a, **kw):
        raise AssertionError("the replay must not start with invalid arguments")

    monkeypatch.setattr(backtest_command, "_produce", never)

    result = CliRunner().invoke(cli_main.app, args)

    assert result.exit_code == 1
    assert not isinstance(result.exception, AttributeError)
