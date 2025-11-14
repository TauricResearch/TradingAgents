"""Minimal client for calling tools on an Alpaca MCP server."""

from __future__ import annotations

import asyncio
import logging
import shlex
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from .config import AlpacaMCPConfig
from ..mcp_handshake import emit_console, perform_handshake

try:  # pragma: no cover - optional dependency during linting
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError:  # pragma: no cover - surfaced at runtime with helpful error
    ClientSession = None  # type: ignore[assignment]
    streamablehttp_client = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]


class AlpacaMCPError(RuntimeError):
    """Raised when the MCP client cannot satisfy a request."""


class AlpacaMCPClient:
    """Fire-and-forget interface for fetching portfolio context from Alpaca MCP."""

    def __init__(self, config: AlpacaMCPConfig, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def fetch_account_info(self) -> str:
        return self._call_tool("get_account_info")

    def fetch_positions(self) -> str:
        return self._call_tool("get_positions")

    def fetch_orders(self, limit: int = 25) -> str:
        return self._call_tool("get_orders", {"status": "all", "limit": limit})

    def place_stock_order(self, payload: Dict[str, Any]) -> str:
        return self._call_tool("place_stock_order", payload)

    def close_position(self, payload: Dict[str, Any]) -> str:
        return self._call_tool("close_position", payload)

    def fetch_market_clock(self) -> str:
        return self._call_tool("get_market_clock")

    def verify_connection(self) -> bool:
        """Check that the MCP server is reachable and exposes required tools."""

        if not self.config.enabled:
            msg = "Alpaca MCP disabled; skipping connectivity check."
            self.logger.info(msg)
            emit_console("INFO", msg)
            return False

        try:
            return asyncio.run(self._verify_async())
        except AlpacaMCPError as exc:
            msg = f"Alpaca MCP connectivity probe failed: {exc}"
            self.logger.warning(msg)
            emit_console("WARNING", msg)
            return False
        except Exception as exc:  # pragma: no cover - best-effort diagnostics
            msg = f"Alpaca MCP connectivity probe failed: {exc}"
            self.logger.warning(msg)
            emit_console("WARNING", msg)
            return False

    async def _verify_async(self) -> bool:
        async with self._acquire_session() as session:
            tools_response = await session.list_tools()
            available = [getattr(tool, "name", "") for tool in getattr(tools_response, "tools", [])]
            missing = self.config.required_toolset(available)
            if missing:
                msg = "Alpaca MCP connected but missing required tools: " + ", ".join(missing)
                self.logger.warning(msg)
                emit_console("WARNING", msg)
                return False
            tools_list = ", ".join(sorted(filter(None, available)))
            msg = f"Alpaca MCP connectivity verified (tools={tools_list})"
            self.logger.info(msg)
            emit_console("INFO", msg)
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        if not self.config.enabled:
            raise AlpacaMCPError("Alpaca MCP integration is disabled.")
        if ClientSession is None or (
            self.config.transport == "http" and streamablehttp_client is None
        ):
            raise AlpacaMCPError(
                "Package 'mcp' is required to use the Alpaca MCP integration. Install it with `pip install mcp`."
            )

        self.config.validate()
        payload = arguments or {}
        return asyncio.run(self._call_tool_async(tool_name, payload))

    async def _call_tool_async(self, tool_name: str, arguments: Dict[str, Any], *, session: Optional["ClientSession"] = None, validate: bool = True) -> str:
        try:
            if session is None:
                async with self._acquire_session() as managed_session:
                    return await self._call_tool_async(tool_name, arguments, session=managed_session, validate=validate)

            if validate:
                tools_response = await session.list_tools()
                available = [getattr(tool, "name", "") for tool in getattr(tools_response, "tools", [])]
                missing = self.config.required_toolset(available)
                if missing:
                    raise AlpacaMCPError(
                        "Alpaca MCP server is missing required tools: " + ", ".join(missing)
                    )
                if tool_name not in available:
                    raise AlpacaMCPError(f"Alpaca MCP server does not expose tool '{tool_name}'.")

            result = await session.call_tool(tool_name, arguments)
            return self._extract_text(result)
        except AlpacaMCPError:
            raise
        except BaseExceptionGroup as exc_group:  # pragma: no cover - requires Python 3.11+
            message = self._flatten_exception_message(exc_group)
            raise AlpacaMCPError(f"Failed to call Alpaca MCP tool '{tool_name}': {message}") from exc_group
        except Exception as exc:
            raise AlpacaMCPError(f"Failed to call Alpaca MCP tool '{tool_name}': {exc}") from exc

    @asynccontextmanager
    async def _acquire_session(self) -> "ClientSession":
        if ClientSession is None:
            raise AlpacaMCPError(
                "Package 'mcp' is required to use the Alpaca MCP integration. Install it with `pip install mcp`."
            )

        if self.config.transport == "http":
            if streamablehttp_client is None:
                raise AlpacaMCPError(
                    "HTTP transport requires the 'mcp' package. Install it with `pip install mcp`."
                )
            base_url = self._build_http_base()
            self.logger.debug("Connecting to Alpaca MCP via HTTP at %s", base_url)
            async with streamablehttp_client(
                url=base_url,
                timeout=self.config.timeout_seconds,
            ) as (read_stream, write_stream, _session_id_cb):
                async with ClientSession(read_stream, write_stream) as session:
                    await perform_handshake(
                        session,
                        client_label="Alpaca",
                        logger=self.logger,
                    )
                    yield session
            return

        if self.config.transport == "stdio":
            if stdio_client is None or StdioServerParameters is None:
                raise AlpacaMCPError(
                    "STDIO transport requires the 'mcp' package. Install it with `pip install mcp`."
                )
            if not self.config.command:
                raise AlpacaMCPError("STDIO transport requires a command to launch the server.")
            args = shlex.split(self.config.command)
            if not args:
                raise AlpacaMCPError("STDIO command is empty.")

            params = StdioServerParameters(command=args[0], args=args[1:])
            self.logger.debug("Launching Alpaca MCP via STDIO: %s", args)
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await perform_handshake(
                        session,
                        client_label="Alpaca",
                        logger=self.logger,
                    )
                    yield session
            return

        raise AlpacaMCPError(f"Unsupported transport '{self.config.transport}'.")

    def _build_http_base(self) -> str:
        if getattr(self.config, "base_url", ""):
            return self.config.base_url.rstrip("/")
        host = self.config.host
        if host.startswith("http://") or host.startswith("https://"):
            return host.rstrip("/")
        return f"http://{host}:{self.config.port}"

    @staticmethod
    def _extract_text(result: Any) -> str:
        content = getattr(result, "content", None)
        if content is None and isinstance(result, dict):
            content = result.get("content")
        if not content:
            return str(result)

        fragments: List[str] = []
        for item in content:
            text_value = getattr(item, "text", None)
            if text_value is None and isinstance(item, dict):
                text_value = item.get("text")
            fragments.append(str(text_value) if text_value is not None else str(item))
        return "\n".join(fragment for fragment in fragments if fragment)

    @staticmethod
    def _flatten_exception_message(exc: BaseException) -> str:
        if isinstance(exc, BaseExceptionGroup):
            parts: List[str] = []
            for item in exc.exceptions:
                message = AlpacaMCPClient._flatten_exception_message(item)
                if message:
                    parts.append(message)
            return "; ".join(parts)
        return str(exc)
