"""A terminal without a console buffer must fail with one actionable line (#1138).

prompt_toolkit raises NoConsoleScreenBufferError before the first prompt in
non-interactive Windows terminals; the CLI should not surface that traceback.
The Windows-only exception import must also stay inert on other platforms.
"""
from __future__ import annotations

import sys

import pytest
import questionary
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


def test_default_callback_does_not_run_for_subcommands(monkeypatch):
    calls = []
    monkeypatch.setattr(
        m,
        "run_analysis",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(m.app, ["config", "show"])

    assert result.exit_code == 0
    assert calls == []


def test_analyze_subcommand_runs_analysis_once(monkeypatch):
    calls = []
    monkeypatch.setattr(
        m,
        "run_analysis",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(m.app, ["analyze"])

    assert result.exit_code == 0
    assert calls == [((), {"checkpoint": None, "configure": False})]


@pytest.mark.parametrize(
    ("option", "checkpoint"),
    [("--checkpoint", True), ("--no-checkpoint", False)],
)
def test_root_analysis_preserves_legacy_checkpoint_options(monkeypatch, option, checkpoint):
    calls = []
    monkeypatch.setattr(
        m,
        "run_analysis",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(m.app, [option])

    assert result.exit_code == 0
    assert calls == [((), {"checkpoint": checkpoint, "configure": False})]


def test_root_analysis_preserves_clear_checkpoint_option(monkeypatch):
    calls = []
    monkeypatch.setattr(
        m,
        "_run_analysis_command",
        lambda **kwargs: calls.append(kwargs),
    )

    result = CliRunner().invoke(m.app, ["--clear-checkpoints"])

    assert result.exit_code == 0
    assert calls == [
        {
            "checkpoint": None,
            "clear_checkpoints": True,
            "configure": False,
        }
    ]


def test_config_set_translates_missing_console(monkeypatch):
    class _NoConsole(Exception):
        pass

    monkeypatch.setattr(m, "_NO_CONSOLE_ERRORS", (_NoConsole,))
    monkeypatch.setattr(
        m,
        "ask_output_language",
        lambda: (_ for _ in ()).throw(_NoConsole("no console")),
    )

    result = CliRunner().invoke(m.app, ["config", "set"])

    assert result.exit_code == 1
    assert "no Windows console available" in result.output
    assert "Traceback" not in result.output


def test_config_reset_translates_missing_console(monkeypatch, tmp_path):
    class _NoConsole(Exception):
        pass

    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(m, "PREFERENCES_PATH", preferences_path)
    monkeypatch.setattr(m, "_NO_CONSOLE_ERRORS", (_NoConsole,))
    monkeypatch.setattr(
        questionary,
        "confirm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_NoConsole("no console")),
    )

    result = CliRunner().invoke(m.app, ["config", "reset"])

    assert result.exit_code == 1
    assert "no Windows console available" in result.output
    assert "Traceback" not in result.output
