"""HTTP server implementing the OpenAI Chat Completions compatible surface.

Endpoints:
    POST /v1/chat/completions  — main inference endpoint
    GET  /healthz              — sanitized readiness check
    GET  /v1/models            — list accepted bridge model aliases
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import BridgeConfig
from .executor import DevinExecutor, ExecutorError
from .protocol import ProtocolError, parse_sentinel, validate_envelope
from .runtime import (
    RuntimeSetupError,
    cleanup_runtime,
    find_checkout_root,
    prepare_runtime,
    verify_outside_checkout,
)

logger = logging.getLogger(__name__)


class BridgeError(Exception):
    """Internal bridge error with an HTTP status code."""

    def __init__(self, status: int, message: str, error_type: str = "bridge_error"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.error_type = error_type


def _get_available_models(devin_bin: str) -> set[str]:
    """Query `devin models list` (non-inference) and return available model IDs.

    Returns a set of model identifiers (the leftmost column of the output).
    """
    result = subprocess.run(
        [devin_bin, "models", "list"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise BridgeError(503, f"devin models list failed: {result.stderr.strip()}")

    models: set[str] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Model lines look like: "  glm-5-2                  GLM-5.2 High  [200K context, Free]"
        # The identifier is the first non-empty token after leading whitespace.
        # Skip family header lines (contain parentheses like "GLM-5.2 (glm-5.2)").
        # Skip "aliases:" lines.
        if line.startswith("aliases:") or "(" in line.split()[0:1]:
            # Check if it's a family header: "Family Name (family-slug)"
            parts = line.split()
            if parts and parts[0] == "aliases:":
                continue
            # Family headers have format "Name (slug)" — check if first token has no leading spaces
            # Actually family headers are like "GLM-5.2 (glm-5.2)" — the first token is "GLM-5.2"
            # Model lines are indented with spaces and the first token is the model ID.
            if not line[0:1].isspace():
                continue
        # Model lines are indented; extract the first token as the model ID.
        parts = line.split()
        if parts:
            models.add(parts[0])
    return models


def preflight(config: BridgeConfig, runtime_dir: str) -> None:
    """Run non-inference preflight checks before accepting requests.

    Raises BridgeError if any check fails.
    """
    devin_bin = config.resolve_devin_bin()

    # Check executable exists.
    if not os.path.exists(devin_bin) and not _which(devin_bin):
        raise BridgeError(503, f"Devin executable not found at {devin_bin}")

    # Check devin --version succeeds.
    try:
        result = subprocess.run(
            [devin_bin, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise BridgeError(503, f"devin --version failed: {result.stderr.strip()}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise BridgeError(503, f"devin --version check failed: {e}") from e

    # Check auth status.
    try:
        result = subprocess.run(
            [devin_bin, "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise BridgeError(503, "Devin authentication check failed")
        stdout = result.stdout.lower()
        if "logged in" not in stdout and "authenticated" not in stdout:
            raise BridgeError(503, "Devin is not authenticated")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise BridgeError(503, f"Devin auth check failed: {e}") from e

    # Check runtime workspace.
    if not os.path.isdir(runtime_dir):
        raise BridgeError(503, f"Runtime directory not found: {runtime_dir}")
    config_path = os.path.join(runtime_dir, ".devin", "config.json")
    if not os.path.exists(config_path):
        raise BridgeError(503, f"Runtime config not found: {config_path}")

    # Validate model availability (non-inference).
    try:
        available = _get_available_models(devin_bin)
    except BridgeError:
        raise
    except Exception as e:
        raise BridgeError(503, f"Failed to query available models: {e}") from e

    for alias, model_id in config.model_mapping().items():
        # None means "let the Devin CLI choose its configured/default model"
        # — no availability check needed (we don't know the model ID).
        if model_id == "devin-cli-default":
            continue
        if model_id not in available:
            raise BridgeError(
                503,
                f"Model {model_id!r} (configured for {alias}) is not available "
                f"in your Devin account. Use 'python -m devin_bridge --list-models' "
                f"to see available models."
            )

    logger.info(
        "preflight passed: devin=%s quick=%s deep=%s",
        devin_bin, config.quick_model, config.deep_model,
    )


def _which(bin_name: str) -> bool:
    """Check if a binary is on PATH."""
    from shutil import which
    return which(bin_name) is not None


def make_final_response(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-bridge-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def make_tool_calls_response(calls: list[dict], model: str) -> dict:
    tool_calls = []
    for call in calls:
        call_id = f"call_bridge_{uuid.uuid4().hex[:12]}"
        tool_calls.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": call["name"],
                "arguments": json.dumps(call["arguments"]),
            },
        })
    return {
        "id": f"chatcmpl-bridge-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls,
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Devin bridge."""

    executor: DevinExecutor | None = None
    config: BridgeConfig | None = None

    def _send_json(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, code: int, message: str, error_type: str = "bridge_error"):
        self._send_json(code, {"error": {"message": message, "type": error_type}})

    def do_GET(self):
        if self.path == "/healthz":
            mapping = self.config.model_mapping() if self.config else {}
            self._send_json(200, {
                "status": "ok",
                "models": mapping,
                "runtime_ready": self.executor is not None,
            })
        elif self.path == "/v1/models":
            models = self.config.known_models() if self.config else []
            self._send_json(200, {
                "object": "list",
                "data": [{"id": m, "object": "model"} for m in models],
            })
        else:
            self._send_error(404, f"Unknown path: {self.path}")

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send_error(404, f"Unknown path: {self.path}")
            return

        request_id = uuid.uuid4().hex[:8]
        length = int(self.headers.get("Content-Length", 0))

        try:
            body = json.loads(self.rfile.read(length).decode())
        except Exception as e:
            self._send_error(400, f"Invalid JSON body: {e}")
            return

        # Validate required fields.
        messages = body.get("messages")
        if not isinstance(messages, list):
            self._send_error(400, "'messages' must be a list")
            return
        if not messages:
            self._send_error(400, "'messages' is empty")
            return

        tools = body.get("tools", [])
        if not isinstance(tools, list):
            self._send_error(400, "'tools' must be a list")
            return

        # Validate model.
        requested_model = body.get("model", "")
        if not requested_model:
            self._send_error(400, "'model' is required")
            return
        try:
            mapped_model = self.config.resolve_model(requested_model)
        except ValueError as e:
            self._send_error(400, str(e), "unknown_model")
            return

        # Reject streaming.
        if body.get("stream"):
            self._send_error(
                400,
                "Streaming is not supported by the Devin bridge. Set stream=false.",
                "unsupported_feature",
            )
            return

        # Build allowed tools dict.
        allowed_tools: dict[str, dict] = {}
        for t in tools:
            fn = t.get("function", t)
            if isinstance(fn, dict) and "name" in fn:
                allowed_tools[fn["name"]] = fn

        logger.info(
            "request=%s model=%s messages=%d tools=%s",
            request_id, requested_model, len(messages),
            [t.get("function", {}).get("name", "?") for t in tools] if tools else [],
        )

        # Invoke Devin with the mapped model.
        try:
            raw = self.executor.invoke(messages, tools, mapped_model)
        except ExecutorError as e:
            logger.error("request=%s executor error: %s", request_id, e)
            self._send_error(502, str(e), "devin_cli_error")
            return
        except Exception as e:
            logger.error("request=%s unexpected error: %s", request_id, e)
            self._send_error(500, str(e), "bridge_internal_error")
            return

        # Parse and validate the response.
        try:
            envelope = parse_sentinel(raw)
            validated = validate_envelope(envelope, allowed_tools)
        except ProtocolError as e:
            # Sanitized metadata only (no raw output) in normal mode.
            # In debug mode, also log a bounded raw tail for diagnosis.
            logger.error(
                "request=%s protocol error: %s (stdout_len=%d, content_len=%s)",
                request_id, e, len(raw),
                len(raw) if raw else 0,
            )
            if self.config and self.config.debug:
                raw_tail = raw[-500:] if len(raw) > 500 else raw
                logger.debug(
                    "request=%s raw tail (last 500 chars, debug mode): %r",
                    request_id, raw_tail,
                )
            self._send_error(502, str(e), "invalid_devin_envelope")
            return

        if validated["type"] == "final":
            resp = make_final_response(validated["content"], requested_model)
        else:
            resp = make_tool_calls_response(validated["calls"], requested_model)

        logger.info("request=%s result_type=%s", request_id, validated["type"])
        self._send_json(200, resp)

    def log_message(self, fmt, *args):
        # Use logging instead of raw stderr.
        logger.debug("%s - %s", self.address_string(), fmt % args)


def create_server(config: BridgeConfig) -> ThreadingHTTPServer:
    """Create and configure the bridge HTTP server with preflight."""
    runtime_dir = config.resolve_runtime_dir()
    checkout_dir = find_checkout_root()

    # Verify isolation — rejects runtime inside checkout via real-path resolution.
    verify_outside_checkout(runtime_dir, checkout_dir)

    # Prepare runtime workspace.
    try:
        prepare_runtime(runtime_dir)
    except RuntimeSetupError as e:
        raise BridgeError(503, str(e)) from e

    # Run preflight.
    preflight(config, runtime_dir)

    # Create executor.
    executor = DevinExecutor(config, runtime_dir)

    # Attach config/executor to the handler class (shared across requests).
    BridgeHandler.config = config
    BridgeHandler.executor = executor

    server = ThreadingHTTPServer((config.host, config.port), BridgeHandler)
    return server


def run_server(config: BridgeConfig) -> None:
    """Create and run the bridge server until interrupted."""
    try:
        server = create_server(config)
    except BridgeError as e:
        print(f"[bridge] startup failed: {e.message}", file=sys.stderr)
        sys.exit(1)

    runtime_dir = config.resolve_runtime_dir()
    print(
        f"[bridge] listening on http://{config.host}:{config.port}",
        file=sys.stderr,
    )
    print(f"[bridge] quick_model={config.quick_model}", file=sys.stderr)
    print(f"[bridge] deep_model={config.deep_model}", file=sys.stderr)
    print(f"[bridge] runtime={runtime_dir}", file=sys.stderr)
    print(f"[bridge] concurrency={config.max_concurrency}", file=sys.stderr)
    if config.is_auto_runtime():
        print("[bridge] runtime=auto (will be cleaned up on shutdown)", file=sys.stderr)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if BridgeHandler.executor:
            BridgeHandler.executor.shutdown()
        server.shutdown()
        # Clean up auto-created runtime directory only (not user-supplied).
        if config.is_auto_runtime():
            cleanup_runtime(runtime_dir)
        print("[bridge] stopped", file=sys.stderr)
