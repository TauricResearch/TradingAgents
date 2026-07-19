"""Regression contracts for migrating terminal rendering onto AnalysisRunner."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from cli.main import MessageBuffer, app
from cli.models import AnalystType
from cli.run_observer import CliRunObserver
from tradingagents.execution.models import AnalysisResult


pytestmark = pytest.mark.unit


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _configured_selections() -> dict[str, object]:
    return {
        "ticker": "AAPL",
        "asset_type": "stock",
        "analysis_date": "2026-07-18",
        "analysts": [AnalystType.MARKET, AnalystType.FUNDAMENTALS],
        "research_depth": 2,
        "llm_provider": "openai",
        "backend_url": None,
        "shallow_thinker": "quick-model",
        "deep_thinker": "deep-model",
        "output_language": "Chinese",
        "save_report": False,
        "display_report": True,
        "data_vendors": {},
    }


def _install_run_harness(monkeypatch, tmp_path, *, result=None, failure=None):
    from cli import main as cli_main

    selections = _configured_selections()
    cli_config = {"run": {"save_report": False, "display_report": True}}
    effective_config = {
        "results_dir": str(tmp_path),
        "checkpoint_enabled": False,
        "max_debate_rounds": 2,
        "max_risk_discuss_rounds": 2,
    }
    final_result = result or AnalysisResult(
        final_state={
            "market_report": "market evidence",
            "fundamentals_report": "fundamental evidence",
            "final_trade_decision": "Rating: Hold",
        },
        final_signal="HOLD",
    )
    graph = MagicMock()
    graph.graph.stream.side_effect = AssertionError(
        "CLI must not create a second direct graph execution path"
    )
    if failure is None:
        graph.run_analysis.return_value = final_result
    else:
        graph.run_analysis.side_effect = failure
    graph_factory = MagicMock(return_value=graph)
    publish = MagicMock()

    monkeypatch.setattr(cli_main, "message_buffer", MessageBuffer())
    monkeypatch.setattr(cli_main, "load_cli_config", lambda _path: cli_config)
    monkeypatch.setattr(cli_main, "get_user_selections", lambda _config: selections)
    monkeypatch.setattr(
        cli_main,
        "_build_run_config",
        lambda _selections, _checkpoint: effective_config,
    )
    monkeypatch.setattr(cli_main, "TradingAgentsGraph", graph_factory)
    monkeypatch.setattr(cli_main, "Live", lambda *_args, **_kwargs: _NullContext())
    monkeypatch.setattr(cli_main, "update_display", MagicMock())
    monkeypatch.setattr(cli_main, "_publish_cli_outputs", publish)
    monkeypatch.chdir(tmp_path)

    return {
        "module": cli_main,
        "selections": selections,
        "cli_config": cli_config,
        "effective_config": effective_config,
        "result": final_result,
        "graph": graph,
        "graph_factory": graph_factory,
        "publish": publish,
    }


def test_cli_executes_once_through_shared_runner_facade_and_publishes_legacy_outputs(
    monkeypatch,
    tmp_path,
):
    harness = _install_run_harness(monkeypatch, tmp_path)

    harness["module"].run_analysis(
        checkpoint=False,
        config_path=tmp_path / "configured.json",
    )

    graph_factory = harness["graph_factory"]
    graph_factory.assert_called_once()
    assert graph_factory.call_args.args == (["market", "fundamentals"],)
    assert graph_factory.call_args.kwargs["config"] is harness["effective_config"]
    assert graph_factory.call_args.kwargs["debug"] is False

    graph = harness["graph"]
    graph.run_analysis.assert_called_once()
    request = graph.run_analysis.call_args.args[0]
    assert request.ticker == "AAPL"
    assert request.analysis_date == "2026-07-18"
    assert request.asset_type == "stock"
    assert request.selected_analysts == ("market", "fundamentals")
    assert request.max_debate_rounds == 2
    assert request.max_risk_discuss_rounds == 2
    assert request.effective_config is harness["effective_config"]
    assert callable(graph.run_analysis.call_args.kwargs["state_update_sink"])
    assert len(graph.run_analysis.call_args.kwargs["callbacks"]) == 1
    graph.graph.stream.assert_not_called()

    harness["publish"].assert_called_once_with(
        harness["result"].final_state,
        harness["selections"],
        harness["cli_config"],
    )


def test_cli_propagates_original_runner_exception_and_never_publishes(
    monkeypatch,
    tmp_path,
):
    original = RuntimeError("provider exploded")
    harness = _install_run_harness(monkeypatch, tmp_path, failure=original)

    with pytest.raises(RuntimeError, match="provider exploded") as exc_info:
        harness["module"].run_analysis(config_path=tmp_path / "configured.json")

    assert exc_info.value is original
    harness["publish"].assert_not_called()
    harness["graph"].graph.stream.assert_not_called()


def test_cli_run_observer_preserves_messages_tools_debates_and_role_statuses():
    buffer = MessageBuffer()
    buffer.init_for_analysis(["market"])
    update_analysts = MagicMock()
    refresh = MagicMock()
    observer = CliRunObserver(
        buffer,
        wall_time_tracker=object(),
        classify_message=lambda _message: ("Agent", "model output"),
        update_analysts=update_analysts,
        refresh_display=refresh,
    )
    message = SimpleNamespace(
        id="message-1",
        tool_calls=[{"name": "get_stock_data", "args": {"ticker": "AAPL"}}],
    )
    chunk = {
        "messages": [message],
        "investment_debate_state": {
            "bull_history": "bull case",
            "bear_history": "bear case",
            "judge_decision": "research verdict",
        },
        "trader_investment_plan": "trading plan",
        "risk_debate_state": {
            "aggressive_history": "aggressive view",
            "conservative_history": "conservative view",
            "neutral_history": "neutral view",
            "judge_decision": "portfolio verdict",
        },
    }

    observer(chunk)

    assert [entry[2] for entry in buffer.messages] == ["model output"]
    assert [(entry[1], entry[2]) for entry in buffer.tool_calls] == [
        ("get_stock_data", {"ticker": "AAPL"})
    ]
    assert buffer.report_sections["investment_plan"].endswith("research verdict")
    assert buffer.report_sections["trader_investment_plan"] == "trading plan"
    assert buffer.report_sections["final_trade_decision"].endswith(
        "portfolio verdict"
    )
    for agent in (
        "Bull Researcher",
        "Bear Researcher",
        "Research Manager",
        "Trader",
        "Aggressive Analyst",
        "Conservative Analyst",
        "Neutral Analyst",
        "Portfolio Manager",
    ):
        assert buffer.agent_status[agent] == "completed"
    update_analysts.assert_called_once_with(
        buffer,
        chunk,
        wall_time_tracker=observer.wall_time_tracker,
    )
    refresh.assert_called_once_with()


@pytest.mark.parametrize("prefix", [[], ["analyze"]])
def test_legacy_root_and_analyze_keep_config_checkpoint_and_success_exit(prefix):
    with patch("cli.main.run_analysis") as run_analysis:
        result = CliRunner().invoke(
            app,
            [*prefix, "--checkpoint", "--config", "configured.json"],
        )

    assert result.exit_code == 0, result.output
    run_analysis.assert_called_once_with(
        checkpoint=True,
        config_path=Path("configured.json"),
    )


@pytest.mark.parametrize("prefix", [[], ["analyze"]])
def test_legacy_root_and_analyze_preserve_failure_exit_and_exception(prefix):
    original = RuntimeError("analysis failed")

    with patch("cli.main.run_analysis", side_effect=original):
        result = CliRunner().invoke(app, [*prefix, "--no-checkpoint"])

    assert result.exit_code != 0
    assert result.exception is original
