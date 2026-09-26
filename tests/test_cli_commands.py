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
    import re
    import subprocess
    import sys

    out = subprocess.run([sys.executable, "-m", "cli.main", "backtest", "--help"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-400:]
    # Where the terminal takes colour, help styles each option and splits
    # "--start" across escape sequences, so read the text without them.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out.stdout)
    assert "--start" in plain


@pytest.mark.unit
def test_backtest_can_continue_an_interrupted_sweep(runner, monkeypatch, tmp_path):
    """Resuming is what makes a long sweep practical, and the Python API has it."""
    swept = []
    monkeypatch.setattr(m, "run_backtest", lambda *a, **kw: swept.append(kw) or _Result(tmp_path))
    monkeypatch.setattr(m, "summarize", lambda log: _Summary())

    result = runner.invoke(m.app, ["backtest", "NVDA", "--start", "2026-06-01",
                                   "--end", "2026-06-08", "--run-id", "20260617_120000"])

    assert result.exit_code == 0, result.output
    assert swept[0]["run_id"] == "20260617_120000"


@pytest.mark.unit
@pytest.mark.parametrize("args, expected", [
    (["backtest", "NVDA", "--start", "2026-08-01", "--end", "2026-06-08"], "before"),
    (["backtest", ",,", "--start", "2026-06-01", "--end", "2026-06-08"], "ticker"),
])
def test_backtest_rejects_input_that_would_sweep_nothing(runner, args, expected):
    """An inverted range or an empty ticker list reported a clean zero-cell run,
    which reads as 'nothing to find' rather than 'you asked for nothing'."""
    result = runner.invoke(m.app, args)
    assert result.exit_code == 1
    assert expected in result.output.lower()


@pytest.mark.unit
def test_backtest_reports_a_setup_failure_in_one_line(runner, monkeypatch):
    """A missing key or a bad analyst name produced a raw traceback."""
    def _explode(*a, **kw):
        raise ValueError("API key for provider 'openai' is not set")

    monkeypatch.setattr(m, "run_backtest", _explode)
    result = runner.invoke(m.app, ["backtest", "NVDA", "--start", "2026-06-01", "--end", "2026-06-08"])

    assert result.exit_code == 1
    assert "API key" in result.output
    assert "Traceback" not in result.output
