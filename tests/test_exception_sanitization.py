import os
import subprocess
import sys

import pytest

from cli import entrypoints, main as interactive_cli
from tradingagents import backtest, walkforward
from tradingagents.dataflows import yfinance_news
from tradingagents.dataflows.errors import VendorError
from tradingagents.logging_utils import safe_exception_type
from tradingagents.research import cli as research_cli


@pytest.mark.unit
def test_safe_exception_type_is_bounded_and_never_uses_the_message():
    secret = "https://provider.invalid/?token=must-not-escape"
    assert safe_exception_type(TimeoutError(secret)) == "TimeoutError"

    unsafe_type = type(secret, (Exception,), {})
    assert safe_exception_type(unsafe_type("ignored")) == "Exception"


@pytest.mark.unit
def test_direct_yfinance_failure_raises_sanitized_vendor_error(monkeypatch):
    secret = "https://provider.invalid/?token=must-not-escape"

    def fail(_ticker):
        raise RuntimeError(secret)

    monkeypatch.setattr(yfinance_news.yf, "Ticker", fail)
    with pytest.raises(VendorError) as captured:
        yfinance_news.get_news_yfinance("AAPL", "2026-01-01", "2026-01-02")

    assert secret not in str(captured.value)
    assert "RuntimeError" in str(captured.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("module", "label"),
    [
        (backtest, "Backtest failed"),
        (walkforward, "Walk-forward failed"),
        (research_cli, "Research command failed"),
    ],
)
def test_console_entrypoints_never_render_exception_messages(
    monkeypatch, capsys, module, label
):
    secret = "postgresql://user:password@database.invalid/research"

    def fail():
        raise RuntimeError(secret)

    monkeypatch.setattr(module, "main", fail)
    with pytest.raises(SystemExit) as captured:
        module._main_entrypoint()

    output = capsys.readouterr()
    assert captured.value.code == 1
    assert output.out == ""
    assert output.err == f"{label} (RuntimeError)\n"
    assert secret not in output.err


@pytest.mark.unit
def test_interactive_console_entrypoint_sanitizes_startup_failures(monkeypatch, capsys):
    secret = "postgresql://user:password@database.invalid/research"

    def fail():
        raise RuntimeError(secret)

    monkeypatch.setattr(interactive_cli, "app", fail)
    with pytest.raises(SystemExit) as captured:
        interactive_cli._main_entrypoint()

    output = capsys.readouterr()
    assert captured.value.code == 1
    assert output.out == ""
    assert output.err == "Command failed (RuntimeError).\n"
    assert secret not in output.err


@pytest.mark.unit
def test_lazy_entrypoint_sanitizes_import_time_configuration_failure():
    secret = "not-an-integer-with-secret-material"
    environment = {
        **os.environ,
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": secret,
    }
    completed = subprocess.run(
        [sys.executable, "-c", "from cli.entrypoints import backtest; backtest()"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "Backtest failed.\n"
    assert secret not in completed.stderr


@pytest.mark.unit
def test_lazy_entrypoint_sanitizes_target_import_failure(monkeypatch, capsys):
    secret = "postgresql://user:password@database.invalid/research"

    def fail(_module_name):
        raise RuntimeError(secret)

    monkeypatch.setattr(entrypoints.importlib, "import_module", fail)
    with pytest.raises(SystemExit) as captured:
        entrypoints.poller()

    output = capsys.readouterr()
    assert captured.value.code == 1
    assert output.out == ""
    assert output.err == "Collector exited.\n"
    assert secret not in output.err
