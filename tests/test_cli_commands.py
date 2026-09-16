"""The CLI keeps running an analysis with no arguments, and gains `backtest`.

Every documented invocation is bare (`tradingagents --checkpoint`), so analysis
has to stay the default action while a second command exists alongside it.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import cli.main as m


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(m, "run_analysis", lambda **kw: calls.append(("analysis", kw)))
    calls.clear()
    return CliRunner()


calls: list = []


@pytest.mark.unit
def test_no_arguments_still_runs_an_analysis(runner):
    assert runner.invoke(m.app, []).exit_code == 0
    assert calls == [("analysis", {"checkpoint": None, "portfolio": None})]


@pytest.mark.unit
def test_options_still_parse_without_a_subcommand(runner):
    assert runner.invoke(m.app, ["--checkpoint"]).exit_code == 0
    assert calls[0][1]["checkpoint"] is True


@pytest.mark.unit
def test_backtest_does_not_also_run_an_analysis(runner, monkeypatch, tmp_path):
    swept = []
    monkeypatch.setattr(m, "run_backtest", lambda *a, **kw: swept.append((a, kw)) or _Result(tmp_path))
    monkeypatch.setattr(m, "summarize", lambda log: _Summary())

    result = runner.invoke(m.app, ["backtest", "NVDA,AAPL", "--start", "2026-06-01",
                                   "--end", "2026-06-15", "--every", "7"])

    assert result.exit_code == 0, result.output
    assert calls == []  # the interactive analysis must not run
    (tickers, dates, _config), kwargs = swept[0]
    assert tickers == ["NVDA", "AAPL"]
    assert dates == ["2026-06-01", "2026-06-08", "2026-06-15"]
    assert "scored" in result.output


@pytest.mark.unit
def test_backtest_reports_a_bad_date_instead_of_a_traceback(runner):
    result = runner.invoke(m.app, ["backtest", "NVDA", "--start", "June", "--end", "2026-06-15"])
    assert result.exit_code == 1
    assert "YYYY-MM-DD" in result.output


@pytest.mark.unit
def test_help_lists_the_backtest_command(runner):
    assert "backtest" in runner.invoke(m.app, ["--help"]).output


class _Result:
    def __init__(self, tmp_path):
        self.run_id = "20260916_000000"
        self.log_path = tmp_path / "trading_memory.md"
        self.cells_run = 2
        self.skipped = 0
        self.failures = []
        self.settlement_failures = []


class _Summary:
    def render(self):
        return "scored 2 cells"


@pytest.mark.unit
def test_every_command_is_registered_when_run_as_a_module():
    """README documents `python -m cli.main`, which executes the file top to
    bottom, so a command defined after the __main__ block would not exist."""
    import subprocess
    import sys

    out = subprocess.run([sys.executable, "-m", "cli.main", "backtest", "--help"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-400:]
    assert "--start" in out.stdout
