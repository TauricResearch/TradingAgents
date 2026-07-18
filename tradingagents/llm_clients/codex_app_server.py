"""Small JSON-RPC client for Codex app-server model discovery."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from typing import Any


class CodexAppServerError(RuntimeError):
    """Raised when Codex app-server cannot satisfy a request."""


@dataclass(frozen=True)
class CodexModelInfo:
    """One model entry advertised by Codex app-server."""

    id: str
    model: str
    display_name: str
    description: str
    is_default: bool = False
    hidden: bool = False
    default_reasoning_effort: str | None = None


class CodexAppServerClient:
    """Minimal stdio JSON-RPC client for read-only app-server requests."""

    def __init__(self, command: str | None = None, timeout: float = 10.0):
        self.command = command or os.environ.get("TRADINGAGENTS_CODEX_APP_SERVER_BIN") or "codex"
        self.timeout = timeout
        self._next_id = 0
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr_lines: deque[str] = deque(maxlen=20)
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None

    def __enter__(self) -> CodexAppServerClient:
        self._start()
        try:
            self._initialize()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _start(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [self.command, "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise CodexAppServerError(
                f"Could not start `{self.command} app-server`: {exc}"
            ) from exc

        if self._proc.stdout is None or self._proc.stdin is None:
            raise CodexAppServerError("Codex app-server did not expose stdio pipes.")

        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_reader.start()

    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._messages.put(message)

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for line in self._proc.stderr:
            line = line.strip()
            if line:
                self._stderr_lines.append(line)

    def _stderr_summary(self) -> str:
        if not self._stderr_lines:
            return ""
        return " ".join(list(self._stderr_lines)[-3:])

    def _send(self, message: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise CodexAppServerError("Codex app-server is not running.")
        try:
            self._proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            detail = self._stderr_summary()
            suffix = f": {detail}" if detail else "."
            raise CodexAppServerError(f"Failed to write to Codex app-server{suffix}") from exc

    def _request(self, method: str, params: Any, timeout: float | None = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        self._send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + (timeout or self.timeout)

        while True:
            if time.monotonic() >= deadline:
                detail = self._stderr_summary()
                suffix = f" Last stderr: {detail}" if detail else ""
                raise CodexAppServerError(
                    f"Timed out waiting for Codex app-server response to {method}.{suffix}"
                )
            if self._proc is not None and self._proc.poll() is not None:
                detail = self._stderr_summary()
                suffix = f": {detail}" if detail else "."
                raise CodexAppServerError(f"Codex app-server exited before {method}{suffix}")
            try:
                remaining = max(0.01, min(0.25, deadline - time.monotonic()))
                message = self._messages.get(timeout=remaining)
            except queue.Empty:
                continue

            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                detail = error.get("message") if isinstance(error, dict) else error
                raise CodexAppServerError(f"{method} failed: {detail}")
            return message.get("result")

    def _notify(self, method: str, params: Any) -> None:
        self._send({"method": method, "params": params})

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "tradingagents",
                    "title": "TradingAgents",
                    "version": "0.3.1",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self._notify("initialized", {})

    def list_models(
        self, *, include_hidden: bool = False, limit: int = 100
    ) -> list[CodexModelInfo]:
        """Return all visible models advertised by app-server."""
        models: list[CodexModelInfo] = []
        cursor: str | None = None
        while True:
            result = self._request(
                "model/list",
                {"cursor": cursor, "includeHidden": include_hidden, "limit": limit},
            )
            for item in (result or {}).get("data", []):
                if not isinstance(item, dict):
                    continue
                model = item.get("model") or item.get("id")
                if not model:
                    continue
                models.append(
                    CodexModelInfo(
                        id=str(item.get("id") or model),
                        model=str(model),
                        display_name=str(item.get("displayName") or model),
                        description=str(item.get("description") or ""),
                        is_default=bool(item.get("isDefault")),
                        hidden=bool(item.get("hidden")),
                        default_reasoning_effort=item.get("defaultReasoningEffort"),
                    )
                )
            cursor = (result or {}).get("nextCursor")
            if not cursor:
                return models

    @staticmethod
    def _close_pipe(pipe: Any) -> None:
        if pipe is not None:
            with suppress(Exception):
                pipe.close()

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._close_pipe(proc.stdin)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        self._close_pipe(proc.stdout)
        self._close_pipe(proc.stderr)
        self._proc = None


def list_codex_app_server_models(
    *, include_hidden: bool = False, timeout: float = 10.0
) -> list[CodexModelInfo]:
    """Fetch Codex model catalog from app-server."""
    with CodexAppServerClient(timeout=timeout) as client:
        return client.list_models(include_hidden=include_hidden)
