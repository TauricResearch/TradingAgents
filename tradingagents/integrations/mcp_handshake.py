"""Utilities shared by MCP clients for the TradingAgents project.

This module contains a single public helper, :func:`perform_handshake`, which
wraps the Model Context Protocol session bootstrapping sequence.  The helper
adds a thin compatibility layer around the official Python SDK so we can supply
client metadata, negotiate capabilities, and emit useful debug logs without
duplicating this logic in every integration.

The implementation favours graceful degradation – if the optional ``mcp``
package is not installed, or if the runtime SDK version does not implement a
specific API entry point, we simply skip that portion of the handshake while
providing informative logging.  This keeps the behaviour predictable in
development environments where the dependency may not be available yet.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

try:  # pragma: no cover - optional dependency during linting
    from mcp.client.session import ClientSession
except ImportError:  # pragma: no cover - surfaced at runtime with helpful error
    ClientSession = Any  # type: ignore[misc,assignment]

try:  # pragma: no cover - optional dependency during linting
    from mcp.types import ClientCapabilities, Implementation
except ImportError:  # pragma: no cover - surfaced at runtime when missing
    ClientCapabilities = None  # type: ignore[misc,assignment]
    Implementation = None  # type: ignore[misc,assignment]


_DEFAULT_PROTOCOL_VERSION = "2025-06-18"


def emit_console(level: str, message: str) -> None:
    """Mirror log output to stdout when no logging handlers are configured."""

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        print(f"{level.upper()}: {message}")


def _detect_package_version() -> str:
    """Return the installed TradingAgents version, falling back to ``0.0.0``."""

    try:
        return importlib.metadata.version("tradingagents")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


async def perform_handshake(
    session: "ClientSession",
    *,
    client_label: str,
    logger: logging.Logger,
    capabilities: Optional[Any] = None,
    protocol_version: str = _DEFAULT_PROTOCOL_VERSION,
) -> Dict[str, Any]:
    """Execute the MCP initialization handshake and emit diagnostic metadata.

    Parameters
    ----------
    session
        A connected :class:`mcp.client.session.ClientSession` instance.
    client_label
        Human friendly tag used in log messages to identify the integration.
    logger
        Logger used for status updates.  ``perform_handshake`` only emits at
        ``INFO`` and ``DEBUG`` levels, so callers can opt in/out via standard
        logging configuration.
    capabilities
        Optional per-client capability overrides.  When omitted we fall back to
        an empty :class:`ClientCapabilities` object if the SDK exposes one.  If
        the caller supplies a plain mapping, the helper forwards it unchanged to
        the ``initialize`` call – the Python SDK accepts either Pydantic models
        or raw dictionaries.
    protocol_version
        Requested MCP protocol version.  Defaults to the latest spec revision we
        target in this repository.

    Returns
    -------
    dict
        A dictionary with the initial handshake result.  The structure matches
        the underlying ``InitializeResult`` object but is normalised to basic
        Python types so it can be safely logged or inspected by tests if
        desired.
    """

    if ClientSession is Any:  # pragma: no cover - defensive runtime guard
        raise RuntimeError("perform_handshake cannot run without the 'mcp' package installed.")

    initialize_kwargs: Dict[str, Any] = {}

    if protocol_version:
        initialize_kwargs["protocol_version"] = protocol_version

    if Implementation is not None:
        initialize_kwargs["client_info"] = Implementation(
            name=f"TradingAgents::{client_label}",
            version=_detect_package_version(),
        )
    else:
        initialize_kwargs["client_info"] = {
            "name": f"TradingAgents::{client_label}",
            "version": _detect_package_version(),
        }

    if capabilities is not None:
        initialize_kwargs["capabilities"] = capabilities
    elif ClientCapabilities is not None:
        initialize_kwargs["capabilities"] = ClientCapabilities()

    try:
        result = await session.initialize(**initialize_kwargs)
    except TypeError:
        # Older SDK versions did not support keyword arguments.  Retry using the
        # minimal signature, while still surfacing the original failure in debug
        # logs so developers understand why metadata was omitted.
        logger.debug(
            "MCP initialize signature did not accept kwargs for %s, falling back to defaults.",
            client_label,
            exc_info=True,
        )
        result = await session.initialize()

    # Normalise the result into a dictionary for consistent downstream usage.
    payload: Dict[str, Any]
    if hasattr(result, "model_dump"):
        payload = result.model_dump()  # type: ignore[assignment]
    elif is_dataclass(result):
        payload = asdict(result)  # type: ignore[arg-type]
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        payload = {
            "protocolVersion": getattr(result, "protocolVersion", None)
            or getattr(result, "protocol_version", None),
            "capabilities": getattr(result, "capabilities", None),
            "serverInfo": getattr(result, "serverInfo", None)
            or getattr(result, "server_info", None),
            "instructions": getattr(result, "instructions", None),
        }

    protocol = payload.get("protocolVersion") or payload.get("protocol_version")
    server_info = payload.get("serverInfo") or payload.get("server_info")
    msg = f"{client_label} MCP handshake complete (protocol={protocol or 'unknown'}, server={server_info or 'n/a'})"
    logger.info(msg)
    emit_console("INFO", msg)

    instructions = payload.get("instructions")
    if instructions:
        instr_msg = f"{client_label} MCP server instructions: {instructions}"
        logger.debug(instr_msg)
        emit_console("DEBUG", instr_msg)

    # Send notifications/initialized when the SDK exposes the helper.  The
    # attribute name changed between releases, so we probe the common forms.
    notification_senders = [
        getattr(session, "notify_initialized", None),
        getattr(session, "notifications_initialized", None),
    ]

    for sender in notification_senders:
        if callable(sender):
            try:
                maybe_coro = sender()
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
                note = f"Sent notifications/initialized for {client_label}"
                logger.debug(note)
                emit_console("DEBUG", note)
                break
            except Exception as exc:  # pragma: no cover - best-effort notification
                fail_msg = (
                    f"Unable to send notifications/initialized for {client_label}: {exc}"
                )
                logger.debug(fail_msg, exc_info=True)
                emit_console("DEBUG", fail_msg)
                break

    return payload


__all__ = ["perform_handshake", "emit_console"]
