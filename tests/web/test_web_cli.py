"""Contracts for the lazy, localhost-only ``tradingagents web`` launcher."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from cli.main import app
from tradingagents.web.preflight import (
    INSTALL_COMMAND,
    GraphFeatureProbe,
    WebCapabilityReport,
    WebRuntimeError,
)

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_URL = "http://127.0.0.1:8765"

# Rich honors ``FORCE_COLOR`` in the test environment, so the CliRunner output
# carries ANSI color spans that split substrings like ``--port`` or the install
# command across styled runs. Strip ANSI before substring assertions so the
# contracts are checked against the plain text, not its color markup.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_importing_cli_and_web_launcher_does_not_import_optional_web_stack():
    """Help and legacy commands must remain usable without the web extra."""
    script = r"""
import sys

blocked = {"fastapi", "uvicorn", "tradingagents.web.api"}

class BlockOptionalWebImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in blocked or any(fullname.startswith(name + ".") for name in blocked):
            raise AssertionError(f"eager optional web import: {fullname}")
        return None

sys.meta_path.insert(0, BlockOptionalWebImports())
import cli.main
import tradingagents.web.cli
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("open_flag", "expected"),
    [("--open", True), ("--no-open", False)],
)
def test_web_command_lazily_forwards_port_and_open_choice(
    monkeypatch,
    open_flag,
    expected,
):
    launcher = MagicMock()
    lazy_module = ModuleType("tradingagents.web.cli")
    lazy_module.launch_web = launcher
    monkeypatch.setitem(sys.modules, "tradingagents.web.cli", lazy_module)

    result = CliRunner().invoke(app, ["web", "--port", "8765", open_flag])

    assert result.exit_code == 0, result.output
    launcher.assert_called_once_with(port=8765, open_browser=expected)


def test_web_command_defaults_to_no_browser_side_effect(monkeypatch):
    launcher = MagicMock()
    lazy_module = ModuleType("tradingagents.web.cli")
    lazy_module.launch_web = launcher
    monkeypatch.setitem(sys.modules, "tradingagents.web.cli", lazy_module)

    result = CliRunner().invoke(app, ["web", "--port", "8765"])

    assert result.exit_code == 0, result.output
    launcher.assert_called_once_with(port=8765, open_browser=False)


def test_web_command_exposes_no_host_override(monkeypatch):
    launcher = MagicMock()
    lazy_module = ModuleType("tradingagents.web.cli")
    lazy_module.launch_web = launcher
    monkeypatch.setitem(sys.modules, "tradingagents.web.cli", lazy_module)
    runner = CliRunner()

    help_result = runner.invoke(app, ["web", "--help"])
    override_result = runner.invoke(
        app,
        ["web", "--host", "0.0.0.0", "--port", "8765"],
    )

    assert help_result.exit_code == 0, help_result.output
    help_plain = _plain(help_result.output)
    assert "--port" in help_plain
    assert "--open" in help_plain
    assert "--no-open" in help_plain
    assert "--host" not in help_plain
    assert override_result.exit_code != 0
    launcher.assert_not_called()


def test_launcher_preflights_then_builds_and_runs_loopback_app():
    from tradingagents.web.cli import launch_web

    calls: list[object] = []
    report = SimpleNamespace(ok=True)
    application = object()

    def ensure_runtime():
        calls.append("ensure")
        return report

    def app_factory(**kwargs):
        calls.append(("create_app", kwargs))
        return application

    def output(message):
        calls.append(("output", message))

    def server_runner(app_argument, **kwargs):
        calls.append(("run", app_argument, kwargs))

    browser_opener = MagicMock()

    launch_web(
        port=8765,
        ensure_runtime=ensure_runtime,
        app_factory=app_factory,
        server_runner=server_runner,
        browser_opener=browser_opener,
        output=output,
    )

    assert calls[:2] == [
        "ensure",
        ("create_app", {"checkpoint_available": True}),
    ]
    assert calls[2][0] == "output"
    assert LOCAL_URL in calls[2][1]
    assert calls[3] == (
        "run",
        application,
        {"host": "127.0.0.1", "port": 8765},
    )
    browser_opener.assert_not_called()


def test_explicit_open_opens_only_the_printed_localhost_url():
    from tradingagents.web.cli import launch_web

    output = MagicMock()
    browser_opener = MagicMock()
    server_runner = MagicMock()

    launch_web(
        port=8765,
        open_browser=True,
        ensure_runtime=lambda: SimpleNamespace(ok=True),
        app_factory=lambda **_kwargs: object(),
        server_runner=server_runner,
        browser_opener=browser_opener,
        output=output,
    )

    output.assert_called_once()
    assert LOCAL_URL in output.call_args.args[0]
    browser_opener.assert_called_once_with(LOCAL_URL)
    assert server_runner.call_args.kwargs == {"host": "127.0.0.1", "port": 8765}


def test_runtime_failure_prints_exact_install_command_and_exits_nonzero():
    report = WebCapabilityReport(
        versions={"fastapi": None},
        requirements={"fastapi": ">=0.115,<1"},
        stream_accepts_durability=False,
        graph_features=GraphFeatureProbe(),
        issues=("missing distribution fastapi (>=0.115,<1)",),
    )

    with patch(
        "tradingagents.web.preflight.ensure_web_runtime",
        side_effect=WebRuntimeError(report),
    ):
        result = CliRunner().invoke(app, ["web", "--no-open"])

    assert result.exit_code != 0
    assert INSTALL_COMMAND in _plain(result.output)
    assert _plain(result.output).count(INSTALL_COMMAND) == 1
