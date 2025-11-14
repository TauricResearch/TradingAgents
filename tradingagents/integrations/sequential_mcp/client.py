"""Client for delegating planning to the Sequential Thinking MCP server."""

from __future__ import annotations

import asyncio
import logging
import shlex
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from .config import SequentialMCPConfig
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


class SequentialMCPError(RuntimeError):
    """Raised when the Sequential Thinking MCP client cannot satisfy a request."""


class SequentialMCPClient:
    """Simple interface for requesting action plans from the Sequential Thinking MCP server."""

    def __init__(self, config: SequentialMCPConfig, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def generate_plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Request a plan from the sequential thinking server."""
        return self._call_tool("sequential_thinking", payload)

    def verify_connection(self) -> bool:
        """Check that the Sequential MCP server is reachable and exposes its tool."""

        if not self.config.enabled:
            msg = "Sequential MCP disabled; skipping connectivity check."
            self.logger.info(msg)
            emit_console("INFO", msg)
            return False

        try:
            return asyncio.run(self._verify_async())
        except SequentialMCPError as exc:
            msg = f"Sequential MCP connectivity probe failed: {exc}"
            self.logger.warning(msg)
            emit_console("WARNING", msg)
            return False
        except Exception as exc:  # pragma: no cover - diagnostic logging only
            msg = f"Sequential MCP connectivity probe failed: {exc}"
            self.logger.warning(msg)
            emit_console("WARNING", msg)
            return False

    async def _verify_async(self) -> bool:
        async with self._acquire_session() as session:
            tools_response = await session.list_tools()
            available = [getattr(tool, "name", "") for tool in getattr(tools_response, "tools", [])]
            missing = self.config.required_toolset(available)
            if missing:
                msg = "Sequential MCP connected but missing required tools: " + ", ".join(missing)
                self.logger.warning(msg)
                emit_console("WARNING", msg)
                return False
            tools_list = ", ".join(sorted(filter(None, available)))
            msg = f"Sequential MCP connectivity verified (tools={tools_list})"
            self.logger.info(msg)
            emit_console("INFO", msg)
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.config.enabled:
            raise SequentialMCPError("Sequential MCP integration is disabled.")
        if ClientSession is None or (
            self.config.transport == "http" and streamablehttp_client is None
        ):
            raise SequentialMCPError(
                "Package 'mcp' is required to use the Sequential Thinking MCP integration. Install it with `pip install mcp`."
            )

        self.config.validate()
        payload = arguments or {}
        return asyncio.run(self._call_tool_async(tool_name, payload))

    async def _call_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with self._acquire_session() as session:
                tools_response = await session.list_tools()
                available = [getattr(tool, "name", "") for tool in getattr(tools_response, "tools", [])]
                missing = self.config.required_toolset(available)
                if missing:
                    raise SequentialMCPError(
                        "Sequential MCP server is missing required tools: " + ", ".join(missing)
                    )
                if tool_name not in available:
                    raise SequentialMCPError(f"Sequential MCP server does not expose tool '{tool_name}'.")

                result = await session.call_tool(tool_name, arguments)
                return self._extract_content(result)
        except SequentialMCPError:
            raise
        except BaseExceptionGroup as exc_group:  # pragma: no cover
            message = self._flatten_exception_message(exc_group)
            raise SequentialMCPError(f"Failed to call Sequential MCP tool '{tool_name}': {message}") from exc_group
        except Exception as exc:
            raise SequentialMCPError(f"Failed to call Sequential MCP tool '{tool_name}': {exc}") from exc

    @asynccontextmanager
    async def _acquire_session(self) -> "ClientSession":
        if ClientSession is None:
            raise SequentialMCPError(
                "Package 'mcp' is required to use the Sequential Thinking MCP integration. Install it with `pip install mcp`."
            )

        if self.config.transport == "http":
            if streamablehttp_client is None:
                raise SequentialMCPError(
                    "HTTP transport requires the 'mcp' package. Install it with `pip install mcp`."
                )
            base_url = self._build_http_base()
            self.logger.debug("Connecting to Sequential MCP via HTTP at %s", base_url)
            async with streamablehttp_client(
                url=base_url,
                timeout=self.config.timeout_seconds,
            ) as (read_stream, write_stream, _session_id_cb):
                async with ClientSession(read_stream, write_stream) as session:
                    await perform_handshake(
                        session,
                        client_label="Sequential",
                        logger=self.logger,
                    )
                    yield session
            return

        if self.config.transport == "stdio":
            if stdio_client is None or StdioServerParameters is None:
                raise SequentialMCPError(
                    "STDIO transport requires the 'mcp' package. Install it with `pip install mcp`."
                )
            command = self.config.command or "python -m tradingagents.integrations.sequential_mcp.server"
            args = shlex.split(command)
            if not args:
                raise SequentialMCPError("STDIO command is empty.")

            params = StdioServerParameters(command=args[0], args=args[1:])
            self.logger.debug("Launching Sequential MCP via STDIO: %s", args)
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await perform_handshake(
                        session,
                        client_label="Sequential",
                        logger=self.logger,
                    )
                    yield session
            return

        raise SequentialMCPError(f"Unsupported transport '{self.config.transport}'.")

    def _build_http_base(self) -> str:
        if self.config.base_url:
            return self.config.base_url.rstrip("/")
        host = self.config.host
        if host.startswith("http://") or host.startswith("https://"):
            return host.rstrip("/")
        return f"http://{host}:{self.config.port}/mcp"

    @staticmethod
    def _extract_content(result: Any) -> Dict[str, Any]:
        content = getattr(result, "content", None)
        if content is None and isinstance(result, dict):
            content = result.get("content")

        fragments: List[str] = []
        if content:
            for item in content:
                text_value = getattr(item, "text", None)
                if text_value is None and isinstance(item, dict):
                    text_value = item.get("text")
                fragments.append(str(text_value) if text_value is not None else str(item))
        text = "\n".join(fragment for fragment in fragments if fragment)

        structured = getattr(result, "structured_content", None)
        if structured is None and isinstance(result, dict):
            structured = result.get("structured_content") or result.get("structuredContent")

        return {"text": text, "structured": structured, "raw": result}

    @staticmethod
    def _flatten_exception_message(exc: BaseException) -> str:
        if isinstance(exc, BaseExceptionGroup):
            parts: List[str] = []
            for item in exc.exceptions:
                message = SequentialMCPClient._flatten_exception_message(item)
                if message:
                    parts.append(message)
            return "; ".join(parts)
        return str(exc)
