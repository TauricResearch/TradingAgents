"""A local web UI for TradingAgents, layered on top of the existing CLI code.

The package adds a FastAPI app (``webapp.app``) that runs the same graph, with
the same live state (``cli.display.MessageBuffer``) and the same report writer
the CLI uses. Nothing in ``cli/`` or ``tradingagents/`` is changed: the web
layer only imports them.

Start it with ``python -m webapp`` (or ``tradingagents-web`` when the console
script is installed) and open http://127.0.0.1:8000/.

``create_app`` is imported lazily: this module is loaded before anything else
when the server starts, and FastAPI is an optional extra, so importing it here
would turn a missing extra into a bare ImportError instead of the install hint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from fastapi import FastAPI

__all__ = ["create_app"]


def create_app(manager=None) -> FastAPI:
    """Build the FastAPI app; see ``webapp.app.create_app``."""
    from webapp.app import create_app as build

    return build(manager)
