"""Tiny console-script boundaries that also cover import-time failures."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

from cli.environment import secure_environment_file


def _load_project_environment() -> None:
    from dotenv import load_dotenv

    # Application entrypoints may load only the project the user actually chose.
    # Searching ancestors can silently inherit an unrelated repository's secrets.
    for name in (".env", ".env.enterprise"):
        path = Path.cwd() / name
        if secure_environment_file(path):
            load_dotenv(path, override=False)


def _run(module_name: str, function_name: str, failure: str) -> None:
    try:
        _load_project_environment()
        module = importlib.import_module(module_name)
        function: Callable[[], object] = getattr(module, function_name)
        function()
    except Exception:  # noqa: BLE001 - executable boundaries must not print secrets
        print(failure, file=sys.stderr)
        raise SystemExit(1) from None


def interactive() -> None:
    _run("cli.main", "app", "Command failed.")


def poller() -> None:
    _run("tradingagents.poller", "main", "Collector exited.")


def backtest() -> None:
    _run("tradingagents.backtest", "main", "Backtest failed.")


def walkforward() -> None:
    _run("tradingagents.walkforward", "main", "Walk-forward failed.")


def research() -> None:
    _run("tradingagents.research.cli", "main", "Research command failed.")
