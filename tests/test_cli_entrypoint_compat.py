"""Compatibility contracts for the installed Typer command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from cli.main import MessageBuffer, app
from cli.models import AnalystType


pytestmark = pytest.mark.unit


@pytest.mark.parametrize("prefix", [[], ["analyze"]])
def test_analysis_invocation_forwards_checkpoint_and_config_options(prefix):
    runner = CliRunner()

    with patch("cli.main.run_analysis") as run_analysis:
        result = runner.invoke(
            app,
            [*prefix, "--no-checkpoint", "--config", "custom-config.json"],
        )

    assert result.exit_code == 0, result.output
    run_analysis.assert_called_once_with(
        checkpoint=False,
        config_path=Path("custom-config.json"),
    )


def test_root_help_keeps_legacy_options_and_lists_explicit_analyze():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--checkpoint" in result.output
    assert "--no-checkpoint" in result.output
    assert "--config" in result.output
    assert "--clear-checkpoints" in result.output
    assert "analyze" in result.output


def test_no_argument_root_invocation_uses_existing_defaults():
    with patch("cli.main.run_analysis") as run_analysis:
        result = CliRunner().invoke(app, [])

    assert result.exit_code == 0, result.output
    run_analysis.assert_called_once()
    assert run_analysis.call_args.kwargs["checkpoint"] is None
    assert run_analysis.call_args.kwargs["config_path"].name == "tradingagents.local.json"


@pytest.mark.parametrize("prefix", [[], ["analyze"]])
def test_clear_checkpoints_runs_before_analysis(prefix):
    call_order = []

    with (
        patch(
            "tradingagents.graph.checkpointer.clear_all_checkpoints",
            side_effect=lambda _path: call_order.append("clear") or 2,
        ),
        patch(
            "cli.main.run_analysis",
            side_effect=lambda **_kwargs: call_order.append("analyze"),
        ),
    ):
        result = CliRunner().invoke(app, [*prefix, "--clear-checkpoints"])

    assert result.exit_code == 0, result.output
    assert call_order == ["clear", "analyze"]
    assert "2" in result.output


@pytest.mark.parametrize(
    ("save_report", "display_report"),
    [(True, False), (False, True), (False, False)],
)
def test_configured_output_choices_do_not_prompt(
    tmp_path,
    monkeypatch,
    save_report,
    display_report,
):
    from cli import main as cli_main

    final_state = {"final_trade_decision": "Rating: Hold"}
    selections = {
        "ticker": "AAPL",
        "save_report": save_report,
        "display_report": display_report,
    }
    report_file = tmp_path / "complete_report.md"
    save = MagicMock(return_value=report_file)
    display = MagicMock()
    prompt = MagicMock(side_effect=AssertionError("configured runs must not prompt"))
    monkeypatch.setattr(cli_main, "save_report_to_disk", save)
    monkeypatch.setattr(cli_main, "display_complete_report", display)
    monkeypatch.setattr(cli_main.typer, "prompt", prompt)
    monkeypatch.chdir(tmp_path)

    cli_main._publish_cli_outputs(final_state, selections, {"run": {}})

    assert save.called is save_report
    assert display.called is display_report
    prompt.assert_not_called()
    if save_report:
        assert save.call_args.args[:2] == (final_state, "AAPL")
        assert save.call_args.args[2].parent == tmp_path / "reports"
        assert save.call_args.args[2].name.startswith("AAPL_")


def test_cli_runner_uses_configured_asset_type_without_prompting(tmp_path, monkeypatch):
    """A JSON-configured run must reach graph setup with a concrete asset type."""
    from cli import main as cli_main

    selections = {
        "ticker": "BTC-USD",
        "asset_type": "crypto",
        "analysis_date": "2026-07-17",
        "analysts": [AnalystType.MARKET],
        "research_depth": 1,
        "llm_provider": "openai",
        "backend_url": None,
        "shallow_thinker": "quick",
        "deep_thinker": "deep",
        "output_language": "English",
        "save_report": False,
        "display_report": False,
        "data_vendors": {},
    }
    final_state = {"messages": [], "market_report": "market"}
    fake_graph = MagicMock()
    fake_graph.resolve_instrument_context.return_value = {"symbol": "BTC-USD"}
    fake_graph.propagator.create_initial_state.return_value = {"input": True}
    fake_graph.propagator.get_graph_args.return_value = {}
    fake_graph.graph.stream.return_value = [final_state]
    monkeypatch.setattr(cli_main, "message_buffer", MessageBuffer())
    monkeypatch.setattr(cli_main, "load_cli_config", lambda _path: {"run": {}})
    monkeypatch.setattr(cli_main, "get_user_selections", lambda _config: selections)
    monkeypatch.setattr(
        cli_main,
        "_build_run_config",
        lambda _selections, _checkpoint: {
            "results_dir": str(tmp_path),
            "checkpoint_enabled": False,
        },
    )
    monkeypatch.setattr(cli_main, "TradingAgentsGraph", MagicMock(return_value=fake_graph))
    monkeypatch.setattr(cli_main, "Live", lambda *_args, **_kwargs: _NullContext())
    monkeypatch.setattr(cli_main, "update_display", MagicMock())
    monkeypatch.setattr(cli_main, "_publish_cli_outputs", MagicMock())

    cli_main.run_analysis(config_path=tmp_path / "configured.json")

    fake_graph.resolve_instrument_context.assert_called_once_with("BTC-USD", "crypto")
    fake_graph.propagator.create_initial_state.assert_called_once_with(
        "BTC-USD",
        "2026-07-17",
        asset_type="crypto",
        instrument_context={"symbol": "BTC-USD"},
    )


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False
