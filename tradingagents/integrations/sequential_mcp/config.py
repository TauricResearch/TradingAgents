"""Configuration utilities for connecting to the Sequential Thinking MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass
class SequentialMCPConfig:
    """Normalized connection information for the Sequential Thinking MCP server."""

    enabled: bool
    transport: str
    host: str
    base_url: str
    port: int
    command: str
    timeout_seconds: float
    required_tools: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SequentialMCPConfig":
        required = data or {}
        transport = (required.get("transport") or "http").lower()
        return cls(
            enabled=bool(required.get("enabled", False)),
            transport=transport,
            host=required.get("host", "127.0.0.1"),
            base_url=required.get("base_url", ""),
            port=int(required.get("port", 8000)),
            command=required.get("command", ""),
            timeout_seconds=float(required.get("timeout_seconds", 30.0)),
            required_tools=list(required.get("required_tools", [])),
        )

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.transport not in {"http", "stdio"}:
            raise ValueError(f"Unsupported Sequential Thinking MCP transport '{self.transport}'.")
        if self.transport == "http" and not (self.base_url or self.host):
            raise ValueError("HTTP transport requires a host or base_url value.")

    def required_toolset(self, available: Iterable[str]) -> List[str]:
        if not self.required_tools:
            return []
        available_set = set(available)
        return [tool for tool in self.required_tools if tool not in available_set]
