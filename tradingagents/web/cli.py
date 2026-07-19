"""Loopback-only launcher for the local TradingAgents web workbench."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8000


def launch_web(
    port: int = DEFAULT_WEB_PORT,
    open_browser: bool = False,
    *,
    ensure_runtime: Callable[[], Any] | None = None,
    app_factory: Callable[..., Any] | None = None,
    server_runner: Callable[..., Any] | None = None,
    browser_opener: Callable[[str], Any] | None = None,
    output: Callable[[str], Any] | None = None,
) -> None:
    """Preflight, compose, announce, and serve one local-only application."""
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    if ensure_runtime is None:
        from .preflight import ensure_web_runtime

        ensure_runtime = ensure_web_runtime
    capability_report = ensure_runtime()

    if app_factory is None:
        from .api import create_app

        app_factory = create_app
    application = app_factory(checkpoint_available=bool(capability_report.ok))

    url = f"http://{LOOPBACK_HOST}:{port}"
    (output or print)(url)

    if open_browser:
        if browser_opener is None:
            from webbrowser import open as open_url

            browser_opener = open_url
        browser_opener(url)

    if server_runner is None:
        from uvicorn import run as run_server

        server_runner = run_server
    server_runner(
        application,
        host=LOOPBACK_HOST,
        port=port,
    )
