"""A terminal without a console buffer must fail with one actionable line (#1138).

prompt_toolkit raises NoConsoleScreenBufferError before the first prompt in
non-interactive Windows terminals; the CLI should not surface that traceback.
The Windows-only exception import must also stay inert on other platforms.
"""
from __future__ import annotations

import sys

from typer.testing import CliRunner

import cli.main as m


def test_no_console_error_tuple_matches_platform():
    # Off Windows the win32 module is never imported (it asserts the platform),
    # so the tuple is empty — which `except` accepts and never matches. On
    # Windows it holds the real exception type, and a broken prompt_toolkit
    # would raise at import rather than silently disabling the handler.
    assert isinstance(m._NO_CONSOLE_ERRORS, tuple)
    assert all(issubclass(e, BaseException) for e in m._NO_CONSOLE_ERRORS)
    if sys.platform == "win32":
        assert m._NO_CONSOLE_ERRORS, "Windows must resolve the console error type"
    else:
        assert m._NO_CONSOLE_ERRORS == ()


def test_missing_console_prints_actionable_message(monkeypatch):
    class _NoConsole(Exception):
        pass

    # Simulate the Windows failure on any platform by registering a stand-in.
    monkeypatch.setattr(m, "_NO_CONSOLE_ERRORS", (_NoConsole,))

    def _boom(*a, **k):
        raise _NoConsole("No Windows console found. Are you running cmd.exe?")

    monkeypatch.setattr(m, "run_analysis", _boom)

    result = CliRunner().invoke(m.app, [])
    assert result.exit_code == 1
    assert "no Windows console available" in result.output
    # The raw prompt_toolkit traceback must not reach the user.
    assert "Traceback" not in result.output


def test_unrelated_errors_still_propagate(monkeypatch):
    # The handler must stay narrow: only the console error is translated.
    monkeypatch.setattr(m, "_NO_CONSOLE_ERRORS", (RuntimeError,))

    def _boom(*a, **k):
        raise ValueError("unrelated")

    monkeypatch.setattr(m, "run_analysis", _boom)
    result = CliRunner().invoke(m.app, [])
    assert isinstance(result.exception, ValueError)
