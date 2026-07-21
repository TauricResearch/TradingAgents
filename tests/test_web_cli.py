"""CLI compat after the single->multi-command flip: bare ``tradingagents``
still runs analyze, ``tradingagents analyze`` is now valid, and
``tradingagents web`` serves the app (with a friendly hint when the web
extra is missing)."""

import builtins
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import cli.main as cli_main

pytestmark = pytest.mark.unit

runner = CliRunner()


@pytest.fixture
def run_analysis(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(cli_main, "run_analysis", mock)
    return mock


def test_bare_invocation_runs_analyze(run_analysis):
    result = runner.invoke(cli_main.app, [])
    assert result.exit_code == 0
    run_analysis.assert_called_once_with(checkpoint=None)


def test_bare_invocation_carries_checkpoint_flag(run_analysis):
    result = runner.invoke(cli_main.app, ["--checkpoint"])
    assert result.exit_code == 0
    run_analysis.assert_called_once_with(checkpoint=True)


def test_analyze_subcommand_is_valid(run_analysis):
    result = runner.invoke(cli_main.app, ["analyze", "--no-checkpoint"])
    assert result.exit_code == 0
    run_analysis.assert_called_once_with(checkpoint=False)


def test_clear_checkpoints_flag(run_analysis, monkeypatch, tmp_path):
    monkeypatch.setitem(
        cli_main.DEFAULT_CONFIG, "data_cache_dir", str(tmp_path)
    )
    result = runner.invoke(cli_main.app, ["--clear-checkpoints"])
    assert result.exit_code == 0
    assert "Cleared 0 checkpoint" in result.output
    run_analysis.assert_called_once()


def test_web_command_starts_uvicorn(monkeypatch):
    import uvicorn

    run_mock = MagicMock()
    monkeypatch.setattr(uvicorn, "run", run_mock)
    result = runner.invoke(cli_main.app, ["web", "--port", "9999"])
    assert result.exit_code == 0
    assert run_mock.call_args.kwargs["host"] == "127.0.0.1"
    assert run_mock.call_args.kwargs["port"] == 9999
    assert run_mock.call_args.kwargs["workers"] == 1


def test_web_command_hints_at_extra_when_missing(monkeypatch):
    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("No module named 'uvicorn'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    result = runner.invoke(cli_main.app, ["web"])
    assert result.exit_code == 1
    assert 'pip install "tradingagents[web]"' in result.output
