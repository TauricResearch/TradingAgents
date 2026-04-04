from __future__ import annotations

import json
import queue
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .codex_binary import codex_binary_error_message, resolve_codex_binary


class CodexAppServerError(RuntimeError):
    """Raised when the Codex app-server request cycle fails."""


class CodexAppServerAuthError(CodexAppServerError):
    """Raised when Codex login is missing or unusable."""


class CodexAppServerBinaryError(CodexAppServerError):
    """Raised when the Codex binary cannot be started."""


class CodexStructuredOutputError(CodexAppServerError):
    """Raised when Codex does not honor the requested structured output."""


@dataclass(slots=True)
class CodexInvocationResult:
    final_text: str
    notifications: list[dict[str, Any]]


class CodexAppServerSession:
    """Minimal JSON-RPC client for `codex app-server` over stdio JSONL."""

    def __init__(
        self,
        *,
        codex_binary: str | None,
        request_timeout: float,
        workspace_dir: str,
        cleanup_threads: bool,
        client_name: str = "tradingagents_codex",
        client_title: str = "TradingAgents Codex Provider",
        client_version: str = "0.2.3",
    ) -> None:
        self.codex_binary = codex_binary
        self.request_timeout = request_timeout
        self.workspace_dir = str(Path(workspace_dir).expanduser())
        self.cleanup_threads = cleanup_threads
        self.client_name = client_name
        self.client_title = client_title
        self.client_version = client_version
        self._proc: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._pending: deque[dict[str, Any]] = deque()
        self._stderr_lines: deque[str] = deque(maxlen=200)
        self._lock = threading.RLock()
        self._request_lock = threading.RLock()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._proc is not None:
                return

            Path(self.workspace_dir).mkdir(parents=True, exist_ok=True)

            binary = resolve_codex_binary(self.codex_binary)
            if not binary:
                raise CodexAppServerBinaryError(codex_binary_error_message(self.codex_binary))
            self.codex_binary = binary

            try:
                self._proc = subprocess.Popen(
                    [binary, "app-server", "--listen", "stdio://"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    cwd=self.workspace_dir,
                    bufsize=1,
                )
            except OSError as exc:
                raise CodexAppServerBinaryError(
                    f"Failed to start Codex app-server with binary '{binary}': {exc}"
                ) from exc

            self._start_reader_threads()
            self._initialize()

    def close(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            if proc is None:
                return

            try:
                if proc.stdin:
                    proc.stdin.close()
            except OSError:
                pass

            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()

    def account_read(self) -> dict[str, Any]:
        return self.request("account/read", {"refreshToken": False})

    def model_list(self, *, include_hidden: bool = True) -> dict[str, Any]:
        return self.request("model/list", {"includeHidden": include_hidden})

    def invoke(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict[str, Any],
        reasoning_effort: str | None,
        summary: str | None,
        personality: str | None,
    ) -> CodexInvocationResult:
        with self._request_lock:
            self.start()
            thread_id = None
            try:
                thread = self.request(
                    "thread/start",
                    {
                        "approvalPolicy": "never",
                        "cwd": self.workspace_dir,
                        "ephemeral": True,
                        "model": model,
                        "personality": personality,
                        "sandbox": "read-only",
                        "serviceName": "tradingagents_codex",
                    },
                )
                thread_id = thread["thread"]["id"]
                started = self.request(
                    "turn/start",
                    {
                        "threadId": thread_id,
                        "input": [{"type": "text", "text": prompt}],
                        "model": model,
                        "effort": reasoning_effort,
                        "summary": summary,
                        "outputSchema": output_schema,
                    },
                )
                turn_id = started["turn"]["id"]
                final_text, notifications = self._collect_turn(turn_id)
                return CodexInvocationResult(final_text=final_text, notifications=notifications)
            finally:
                if thread_id and self.cleanup_threads:
                    try:
                        self.request("thread/unsubscribe", {"threadId": thread_id})
                    except CodexAppServerError:
                        pass

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        self._write({"id": request_id, "method": method, "params": params or {}})
        deferred: list[dict[str, Any]] = []

        while True:
            message = self._next_message(self.request_timeout)
            if message.get("id") == request_id:
                self._restore_deferred(deferred)
                if "error" in message:
                    error = message["error"] or {}
                    code = error.get("code")
                    text = error.get("message", "unknown Codex app-server error")
                    raise CodexAppServerError(
                        f"{method} failed ({code}): {text}. stderr_tail={self._stderr_tail()}"
                    )
                result = message.get("result")
                if not isinstance(result, dict):
                    raise CodexAppServerError(f"{method} returned a non-object result: {result!r}")
                return result

            if "method" in message and "id" in message:
                self._handle_server_request(message)
                continue

            deferred.append(message)

    def _initialize(self) -> None:
        response = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": self.client_name,
                    "title": self.client_title,
                    "version": self.client_version,
                }
            },
        )
        if not response.get("userAgent"):
            raise CodexAppServerError("Codex initialize response did not include userAgent.")
        self._write({"method": "initialized", "params": {}})

    def _collect_turn(self, turn_id: str) -> tuple[str, list[dict[str, Any]]]:
        notifications: list[dict[str, Any]] = []
        final_messages: list[str] = []
        fallback_messages: list[str] = []

        while True:
            message = self._next_message(self.request_timeout)

            if "method" in message and "id" in message:
                self._handle_server_request(message)
                continue

            if "method" not in message:
                self._pending.append(message)
                continue

            method = message["method"]
            params = message.get("params", {})
            notifications.append(message)

            if (
                method == "item/completed"
                and isinstance(params, dict)
                and params.get("turnId") == turn_id
            ):
                item = params.get("item", {})
                if isinstance(item, dict) and item.get("type") == "agentMessage":
                    text = str(item.get("text", ""))
                    if item.get("phase") == "final_answer":
                        final_messages.append(text)
                    else:
                        fallback_messages.append(text)
                continue

            if method == "turn/completed" and isinstance(params, dict):
                turn = params.get("turn", {})
                if isinstance(turn, dict) and turn.get("id") == turn_id:
                    status = turn.get("status")
                    if status == "failed":
                        error = turn.get("error", {})
                        message_text = error.get("message") if isinstance(error, dict) else None
                        raise CodexAppServerError(
                            message_text or f"Codex turn {turn_id} failed without an error message."
                        )
                    break

        if final_messages:
            return final_messages[-1], notifications
        if fallback_messages:
            return fallback_messages[-1], notifications
        raise CodexStructuredOutputError("Codex turn completed without an assistant message.")

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        try:
            self._write({"id": message["id"], "result": {}})
        except Exception:
            pass

    def _write(self, payload: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise CodexAppServerError("Codex app-server is not running.")
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except OSError as exc:
            raise CodexAppServerError(
                f"Failed to write to Codex app-server: {exc}. stderr_tail={self._stderr_tail()}"
            ) from exc

    def _next_message(self, timeout: float) -> dict[str, Any]:
        if self._pending:
            return self._pending.popleft()

        try:
            message = self._stdout_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise CodexAppServerError(
                f"Timed out waiting for Codex app-server after {timeout}s. stderr_tail={self._stderr_tail()}"
            ) from exc

        if message is None:
            raise CodexAppServerError(
                f"Codex app-server closed unexpectedly. stderr_tail={self._stderr_tail()}"
            )
        return message

    def _start_reader_threads(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        assert self._proc.stderr is not None

        def _read_stdout() -> None:
            stdout = self._proc.stdout
            assert stdout is not None
            for line in stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    self._stderr_lines.append(f"invalid_json_stdout={line}")
                    continue
                if isinstance(payload, dict):
                    self._stdout_queue.put(payload)
            self._stdout_queue.put(None)

        def _read_stderr() -> None:
            stderr = self._proc.stderr
            assert stderr is not None
            for line in stderr:
                self._stderr_lines.append(line.rstrip())

        self._reader_thread = threading.Thread(target=_read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()

    def _stderr_tail(self) -> str:
        return "\n".join(list(self._stderr_lines)[-40:])

    def _restore_deferred(self, deferred: list[dict[str, Any]]) -> None:
        for message in reversed(deferred):
            self._pending.appendleft(message)
