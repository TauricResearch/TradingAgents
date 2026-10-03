"""Launching the server, shared by ``python -m webui`` and ``tradingagents ui``."""

from __future__ import annotations

import logging
import threading
import webbrowser

logger = logging.getLogger(__name__)

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    """Run the UI until interrupted.

    Warns before binding off-loopback: the server has no authentication and
    serves a saved broker export, so a wide bind publishes the book to the
    network. It is still allowed, since a container binds 0.0.0.0 by necessity.
    """
    try:
        import uvicorn
    except ImportError:  # pragma: no cover - depends on the install extra
        raise SystemExit(
            "The web UI needs its extra dependencies:\n"
            '    pip install ".[webui]"'
        ) from None

    from webui.server import create_app

    if host not in _LOOPBACK:
        print(
            f"Warning: binding {host} exposes the UI to the network. It has no "
            "authentication and serves your saved portfolio; prefer the default "
            "127.0.0.1 and an SSH tunnel for remote access."
        )

    url = f"http://{'localhost' if host in _LOOPBACK or host == '0.0.0.0' else host}:{port}"
    print(f"TradingAgents UI on {url}")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
