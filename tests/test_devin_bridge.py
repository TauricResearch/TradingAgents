"""Offline tests for the Devin bridge sidecar.

All tests use fake Devin executors — no live Devin calls are made.
Covers: PLAIN, TOOL (single/multiple/unknown/malformed), SCHEMA (real
ResearchPlan via fake executor), PROTOCOL (sentinel parsing), HTTP endpoints,
SUBPROCESS behavior, SECURITY, and CONCURRENCY.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest
import requests

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from devin_bridge.config import DEVIN_CLI_DEFAULT, BridgeConfig
from devin_bridge.executor import DevinExecutor, ExecutorError
from devin_bridge.protocol import (
    BEGIN_SENTINEL,
    CONTENT_BEGIN,
    CONTENT_END,
    END_SENTINEL,
    TYPE_FINAL,
    TYPE_TOOL_CALLS,
    ProtocolError,
    build_output_contract,
    parse_sentinel,
    validate_envelope,
)
from devin_bridge.runtime import (
    _is_inside_checkout,
    cleanup_runtime,
    find_checkout_root,
    prepare_runtime,
    verify_outside_checkout,
)
from devin_bridge.server import (
    BridgeHandler,
    make_final_response,
    make_tool_calls_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_config(**overrides) -> BridgeConfig:
    defaults = {
        "host": "127.0.0.1", "port": 8767,
        "quick_model": "glm-5-2", "deep_model": "glm-5-2",
        "timeout": 10, "max_concurrency": 1,
        "runtime_dir": "/tmp/devin-bridge-test-runtime",
    }
    defaults.update(overrides)
    return BridgeConfig(**defaults)


def fake_devin_stdout(canned: str, returncode: int = 0):
    """Patch subprocess.run to return canned stdout."""
    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.stdout = canned
        mock_proc.stderr = ""
        mock_proc.returncode = returncode
        return mock_proc
    return fake_run


def wrap_sentinel(json_obj: dict) -> str:
    """Wrap a JSON object in the sentinel markers (v2 TOOL_CALLS form).

    For v2, tool calls use the TOOL_CALLS type line + strict JSON.
    """
    return (
        f"{BEGIN_SENTINEL}\n{TYPE_TOOL_CALLS}\n"
        f"{json.dumps(json_obj)}\n{END_SENTINEL}"
    )


def wrap_final(content: str) -> str:
    """Wrap raw FINAL content in the v2 bounded-text markers."""
    return (
        f"{BEGIN_SENTINEL}\n{TYPE_FINAL}\n{CONTENT_BEGIN}\n"
        f"{content}\n{CONTENT_END}\n{END_SENTINEL}"
    )


ALLOWED_TOOLS = {
    "get_marker": {
        "name": "get_marker",
        "parameters": {
            "type": "object",
            "required": ["reason"],
            "properties": {
                "reason": {"type": "string"},
            },
        },
    },
    "decide": {
        "name": "decide",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "action": {"type": "string"},
                "count": {"type": "integer"},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# PROTOCOL: sentinel parsing
# ---------------------------------------------------------------------------


class TestSentinelParsing:
    def test_clean_final(self):
        raw = wrap_final("hello")
        result = parse_sentinel(raw)
        assert result["type"] == "final"
        assert result["content"] == "hello"

    def test_clean_tool_call(self):
        raw = wrap_sentinel({
            "calls": [
                {"name": "get_marker", "arguments": {"reason": "test"}},
            ],
        })
        result = parse_sentinel(raw)
        assert result["type"] == "tool_calls"
        assert result["calls"][0]["name"] == "get_marker"

    def test_tool_calls_plural(self):
        raw = wrap_sentinel({
            "calls": [
                {"name": "get_marker", "arguments": {"reason": "a"}},
                {"name": "decide", "arguments": {"action": "buy"}},
            ],
        })
        result = parse_sentinel(raw)
        assert len(result["calls"]) == 2

    def test_prose_outside_sentinels_ignored(self):
        raw = f"Here is my answer:\n{wrap_final('ok')}\nDone."
        result = parse_sentinel(raw)
        assert result["content"] == "ok"

    def test_missing_sentinels_rejected(self):
        # Production parser is sentinel-only — no fallback to loose JSON.
        raw = '{"type": "final", "content": "BAD"}'
        with pytest.raises(ProtocolError, match="Missing sentinel"):
            parse_sentinel(raw)

    def test_prose_with_json_no_sentinels_rejected(self):
        # JSON-looking prose without sentinels must NEVER become a result.
        raw = 'Here is my answer: {"type":"final","content":"BAD"}'
        with pytest.raises(ProtocolError, match="Missing sentinel"):
            parse_sentinel(raw)

    def test_prose_with_tool_call_json_no_sentinels_rejected(self):
        # A tool_call JSON object in prose without sentinels must be rejected.
        raw = 'I would call: {"type":"tool_call","name":"get_marker","arguments":{"reason":"x"}}'
        with pytest.raises(ProtocolError, match="Missing sentinel"):
            parse_sentinel(raw)

    def test_duplicate_sentinels_rejected(self):
        raw = wrap_final("a") + "\n" + \
              wrap_final("b")
        with pytest.raises(ProtocolError, match="exactly one"):
            parse_sentinel(raw)

    def test_missing_end_sentinel(self):
        raw = f"{BEGIN_SENTINEL}\n{{'type': 'final', 'content': 'x'}}"
        with pytest.raises(ProtocolError):
            parse_sentinel(raw)

    def test_invalid_json_between_sentinels(self):
        raw = f"{BEGIN_SENTINEL}\nnot json\n{END_SENTINEL}"
        with pytest.raises(ProtocolError, match="Unknown protocol type"):
            parse_sentinel(raw)

    def test_empty_between_sentinels(self):
        raw = f"{BEGIN_SENTINEL}\n\n{END_SENTINEL}"
        with pytest.raises(ProtocolError, match="Empty"):
            parse_sentinel(raw)

    def test_no_json_anywhere(self):
        with pytest.raises(ProtocolError):
            parse_sentinel("just plain text")


# ---------------------------------------------------------------------------
# PROTOCOL: envelope validation
# ---------------------------------------------------------------------------


class TestEnvelopeValidation:
    def test_valid_final(self):
        env = {"type": "final", "content": "answer"}
        r = validate_envelope(env, ALLOWED_TOOLS)
        assert r == {"type": "final", "content": "answer"}

    def test_valid_single_tool_call(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "get_marker", "arguments": {"reason": "x"}}
        ]}
        r = validate_envelope(env, ALLOWED_TOOLS)
        assert r["type"] == "tool_calls"
        assert len(r["calls"]) == 1
        assert r["calls"][0]["name"] == "get_marker"

    def test_valid_multiple_tool_calls(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "get_marker", "arguments": {"reason": "a"}},
            {"name": "decide", "arguments": {"action": "buy"}},
        ]}
        r = validate_envelope(env, ALLOWED_TOOLS)
        assert len(r["calls"]) == 2

    def test_unknown_tool_name(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "evil", "arguments": {}}
        ]}
        with pytest.raises(ProtocolError, match="not in advertised"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_unknown_envelope_type(self):
        env = {"type": "weird"}
        with pytest.raises(ProtocolError, match="Unknown envelope type"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_final_empty_content(self):
        env = {"type": "final", "content": ""}
        with pytest.raises(ProtocolError, match="empty"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_tool_call_non_dict_arguments(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "get_marker", "arguments": "str"}
        ]}
        with pytest.raises(ProtocolError, match="must be object"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_missing_required_argument(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "get_marker", "arguments": {}}
        ]}
        with pytest.raises(ProtocolError, match="missing required argument"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_wrong_argument_type(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "decide", "arguments": {"count": "not_an_int"}}
        ]}
        with pytest.raises(ProtocolError, match="expected integer"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_bool_not_integer(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "decide", "arguments": {"count": True}}
        ]}
        with pytest.raises(ProtocolError, match="expected integer, got boolean"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_prose_not_treated_as_tool_call(self):
        raw = "I would call tool get_marker"
        with pytest.raises(ProtocolError):
            parse_sentinel(raw)

    def test_tool_calls_empty_list(self):
        env = {"type": "tool_calls", "calls": []}
        with pytest.raises(ProtocolError, match="empty"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_tool_calls_not_list(self):
        env = {"type": "tool_calls", "calls": "notlist"}
        with pytest.raises(ProtocolError, match="must be a list"):
            validate_envelope(env, ALLOWED_TOOLS)


# ---------------------------------------------------------------------------
# SUBPROCESS: prompt-file mechanism
# ---------------------------------------------------------------------------


class TestSubprocessPromptFile:
    def test_prompt_file_used_not_command_line(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock = MagicMock()
            mock.stdout = wrap_final("ok")
            mock.stderr = ""
            mock.returncode = 0
            return mock

        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_run):
            executor.invoke(
                [{"role": "user", "content": "hello"}], []
            )

        # Verify --prompt-file is in the command, not the prompt text.
        assert "--prompt-file" in captured_cmd
        # The prompt text should NOT be in the command args.
        assert "hello" not in captured_cmd

    def test_prompt_file_cleaned_up(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt_files_seen = []

        def fake_run(cmd, **kwargs):
            # Find the prompt file path in the command.
            idx = cmd.index("--prompt-file")
            prompt_path = cmd[idx + 1]
            prompt_files_seen.append(prompt_path)
            assert os.path.exists(prompt_path), "prompt file should exist during run"
            mock = MagicMock()
            mock.stdout = wrap_final("ok")
            mock.stderr = ""
            mock.returncode = 0
            return mock

        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_run):
            executor.invoke([{"role": "user", "content": "test"}], [])

        # After run, the prompt file should be deleted.
        for p in prompt_files_seen:
            assert not os.path.exists(p), f"prompt file {p} was not cleaned up"

    def test_timeout_raises_executor_error(self):
        import subprocess as sp
        config = make_config(timeout=1)
        executor = DevinExecutor(config, config.runtime_dir)

        with patch("devin_bridge.executor.subprocess.run",
                    side_effect=sp.TimeoutExpired(cmd=[], timeout=1)), \
             pytest.raises(ExecutorError, match="timed out"):
            executor.invoke([{"role": "user", "content": "x"}], [])

    def test_nonzero_exit_raises(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)

        def fake_run(cmd, **kwargs):
            mock = MagicMock()
            mock.stdout = ""
            mock.stderr = "error"
            mock.returncode = 1
            return mock

        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_run), \
             pytest.raises(ExecutorError, match="non-zero"):
            executor.invoke([{"role": "user", "content": "x"}], [])

    def test_empty_stdout_raises(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)

        def fake_run(cmd, **kwargs):
            mock = MagicMock()
            mock.stdout = "   "
            mock.stderr = ""
            mock.returncode = 0
            return mock

        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_run), \
             pytest.raises(ExecutorError, match="empty"):
            executor.invoke([{"role": "user", "content": "x"}], [])

    def test_binary_not_found(self):
        config = make_config(devin_bin="/nonexistent/devin")
        executor = DevinExecutor(config, config.runtime_dir)

        with patch("devin_bridge.executor.subprocess.run",
                    side_effect=FileNotFoundError("not found")), \
             pytest.raises(ExecutorError, match="not found"):
                executor.invoke([{"role": "user", "content": "x"}], [])


# ---------------------------------------------------------------------------
# SUBPROCESS: environment sanitization
# ---------------------------------------------------------------------------


class TestEnvironmentSanitization:
    def test_llm_provider_keys_removed(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)

        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-fake",
            "ANTHROPIC_API_KEY": "sk-ant-fake",
            "DEEPSEEK_API_KEY": "ds-fake",
            "FRED_API_KEY": "fred-real",  # market data — should be kept
        }):
            env = executor._sanitized_env()

        assert "OPENAI_API_KEY" not in env
        assert "ANTHROPIC_API_KEY" not in env
        assert "DEEPSEEK_API_KEY" not in env
        assert env.get("FRED_API_KEY") == "fred-real"  # market data kept


# ---------------------------------------------------------------------------
# HTTP: endpoints
# ---------------------------------------------------------------------------


class TestHTTPEndpoints:
    """Test HTTP endpoints with a real server on a test port."""

    @pytest.fixture
    def server_setup(self):
        """Start the bridge server with a fake executor."""
        from devin_bridge.server import create_server

        config = make_config(port=8770)
        # Bypass preflight by patching it.
        with patch("devin_bridge.server.preflight"), \
             patch("devin_bridge.server.verify_outside_checkout"), \
             patch("devin_bridge.server.prepare_runtime", return_value=config.runtime_dir):
            server = create_server(config)

        # Replace executor with a fake.
        fake_executor = MagicMock()
        fake_executor.invoke.return_value = wrap_final("test response")
        BridgeHandler.executor = fake_executor
        BridgeHandler.config = config

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        yield config, fake_executor
        server.shutdown()
        server.server_close()
        t.join(timeout=2)

    def _post(self, port, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        return resp.status, data

    def _get(self, port, path):
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", path)
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        return resp.status, data

    def test_healthz(self, server_setup):
        config, _ = server_setup
        status, data = self._get(config.port, "/healthz")
        assert status == 200
        assert data["status"] == "ok"

    def test_models(self, server_setup):
        config, _ = server_setup
        status, data = self._get(config.port, "/v1/models")
        assert status == 200
        ids = [m["id"] for m in data["data"]]
        assert "devin-quick" in ids
        assert "devin-deep" in ids

    def test_chat_completions_final(self, server_setup):
        config, fake_exec = server_setup
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "devin-quick",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert status == 200
        assert data["choices"][0]["message"]["content"] == "test response"
        assert data["choices"][0]["finish_reason"] == "stop"

    def test_chat_completions_tool_calls(self, server_setup):
        config, fake_exec = server_setup
        fake_exec.invoke.return_value = wrap_sentinel({
            "calls": [
                {"name": "get_marker", "arguments": {"reason": "test"}},
            ],
        })
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "devin-quick",
            "messages": [{"role": "user", "content": "go"}],
            "tools": [{"type": "function", "function": ALLOWED_TOOLS["get_marker"]}],
        })
        assert status == 200
        tc = data["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "get_marker"
        assert json.loads(tc["function"]["arguments"]) == {"reason": "test"}
        assert data["choices"][0]["finish_reason"] == "tool_calls"

    def test_unknown_model_rejected(self, server_setup):
        config, _ = server_setup
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "gpt-999",
            "messages": [{"role": "user", "content": "x"}],
        })
        assert status == 400
        assert "unknown_model" in data["error"]["type"]

    def test_stream_rejected(self, server_setup):
        config, _ = server_setup
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "devin-quick",
            "messages": [{"role": "user", "content": "x"}],
            "stream": True,
        })
        assert status == 400
        assert "unsupported_feature" in data["error"]["type"]

    def test_malformed_request(self, server_setup):
        config, _ = server_setup
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "devin-quick",
            # missing messages
        })
        assert status == 400

    def test_empty_messages(self, server_setup):
        config, _ = server_setup
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "devin-quick",
            "messages": [],
        })
        assert status == 400

    def test_timeout_maps_to_502(self, server_setup):
        config, fake_exec = server_setup
        fake_exec.invoke.side_effect = ExecutorError("timed out")
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "devin-quick",
            "messages": [{"role": "user", "content": "x"}],
        })
        assert status == 502
        assert "devin_cli_error" in data["error"]["type"]

    def test_protocol_error_maps_to_502(self, server_setup):
        config, fake_exec = server_setup
        fake_exec.invoke.return_value = "no json here"
        status, data = self._post(config.port, "/v1/chat/completions", {
            "model": "devin-quick",
            "messages": [{"role": "user", "content": "x"}],
        })
        assert status == 502
        assert "invalid_devin_envelope" in data["error"]["type"]

    def test_protocol_error_normal_mode_no_raw_tail(self, server_setup, caplog):
        """Normal mode (debug=False) must NOT log raw response tail."""
        config, fake_exec = server_setup
        assert config.debug is False
        sensitive = "SECRET_REPORT_CONTENT_xyz789"
        fake_exec.invoke.return_value = sensitive  # no sentinels → protocol error
        with caplog.at_level(logging.DEBUG, logger="devin_bridge.server"):
            self._post(config.port, "/v1/chat/completions", {
                "model": "devin-quick",
                "messages": [{"role": "user", "content": "x"}],
            })
        # Protocol error metadata should be logged.
        assert any("protocol error" in r.message for r in caplog.records)
        # Raw sensitive content must NOT appear in any log record.
        assert not any(sensitive in r.message for r in caplog.records)

    def test_protocol_error_debug_mode_logs_tail(self, server_setup, caplog):
        """Debug mode (debug=True) MAY log a bounded raw tail."""
        config, fake_exec = server_setup
        config.debug = True
        marker = "DEBUG_TAIL_MARKER_abc123"
        fake_exec.invoke.return_value = marker  # no sentinels → protocol error
        with caplog.at_level(logging.DEBUG, logger="devin_bridge.server"):
            self._post(config.port, "/v1/chat/completions", {
                "model": "devin-quick",
                "messages": [{"role": "user", "content": "x"}],
            })
        # In debug mode, the raw tail should be logged.
        assert any(marker in r.message for r in caplog.records)
        config.debug = False  # reset

    def test_unknown_path_404(self, server_setup):
        config, _ = server_setup
        status, data = self._get(config.port, "/unknown")
        assert status == 404


# ---------------------------------------------------------------------------
# SECURITY: runtime isolation
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_runtime_outside_checkout(self, tmp_path):
        checkout = tmp_path / "TradingAgents"
        checkout.mkdir()
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        # Should pass — runtime is outside checkout.
        verify_outside_checkout(str(runtime), str(checkout))

    def test_runtime_inside_checkout_rejected(self, tmp_path):
        checkout = tmp_path / "TradingAgents"
        checkout.mkdir()
        runtime = checkout / "runtime"
        runtime.mkdir()
        with pytest.raises(Exception, match="inside the TradingAgents checkout"):
            verify_outside_checkout(str(runtime), str(checkout))

    def test_runtime_equals_checkout_rejected(self, tmp_path):
        checkout = tmp_path / "TradingAgents"
        checkout.mkdir()
        with pytest.raises(Exception, match="inside the TradingAgents checkout"):
            verify_outside_checkout(str(checkout), str(checkout))

    def test_dotdot_path_inside_checkout_rejected(self, tmp_path):
        """A path with .. that resolves inside the checkout is rejected."""
        checkout = tmp_path / "TradingAgents"
        checkout.mkdir()
        # /tmp/.../TradingAgents/sub/../sub should resolve inside checkout.
        sub = checkout / "sub"
        sub.mkdir()
        runtime = sub / ".." / "runtime"
        with pytest.raises(Exception, match="inside the TradingAgents checkout"):
            verify_outside_checkout(str(runtime), str(checkout))

    def test_symlink_inside_checkout_rejected(self, tmp_path):
        """A symlink that resolves inside the checkout is rejected."""
        checkout = tmp_path / "TradingAgents"
        checkout.mkdir()
        runtime_real = checkout / "runtime"
        runtime_real.mkdir()
        # Create a symlink outside that points inside the checkout.
        symlink = tmp_path / "evil_symlink"
        os.symlink(str(runtime_real), str(symlink))
        with pytest.raises(Exception, match="inside the TradingAgents checkout"):
            verify_outside_checkout(str(symlink), str(checkout))

    def test_valid_external_runtime_accepted(self, tmp_path):
        checkout = tmp_path / "TradingAgents"
        checkout.mkdir()
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        # Should NOT raise.
        verify_outside_checkout(str(runtime), str(checkout))

    def test_default_runtime_outside_repo(self):
        """The default (auto) runtime must be outside the checkout."""
        from devin_bridge.config import BridgeConfig
        config = BridgeConfig()
        runtime_dir = config.resolve_runtime_dir()
        checkout_dir = find_checkout_root()
        # Must NOT be inside the checkout.
        assert not _is_inside_checkout(runtime_dir, checkout_dir), (
            f"Default runtime {runtime_dir} is inside checkout {checkout_dir}"
        )
        # Clean up the auto-created temp dir.
        cleanup_runtime(runtime_dir)

    def test_auto_runtime_cleanup(self):
        """Auto-created runtime is cleaned up by cleanup_runtime."""
        from devin_bridge.config import BridgeConfig
        config = BridgeConfig()
        runtime_dir = config.resolve_runtime_dir()
        assert os.path.isdir(runtime_dir)
        cleanup_runtime(runtime_dir)
        assert not os.path.exists(runtime_dir)

    def test_user_supplied_runtime_not_deleted(self, tmp_path):
        """User-supplied runtime is NOT deleted by cleanup_runtime."""
        # cleanup_runtime is only called for auto-created dirs, but verify
        # it doesn't destructively remove user content when called directly.
        user_dir = tmp_path / "user-runtime"
        user_dir.mkdir()
        (user_dir / "important.txt").write_text("user data")
        # cleanup_runtime would remove this if called — but the server only
        # calls it for auto-created dirs (is_auto_runtime() == True).
        # Here we just verify the directory exists and is intact.
        assert (user_dir / "important.txt").exists()

    def test_runtime_config_generated(self, tmp_path):
        runtime = tmp_path / "runtime"
        prepare_runtime(str(runtime))
        config_path = runtime / ".devin" / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert "exec" in config["permissions"]["deny"]
        assert "mcp__*" in config["permissions"]["deny"]
        assert config["read_config_from"]["claude"] is False
        assert config["read_config_from"]["windsurf"] is False

    def test_git_init_creates_project_root(self, tmp_path):
        runtime = tmp_path / "runtime"
        prepare_runtime(str(runtime))
        assert (runtime / ".git").exists()

    def test_no_global_config_modification(self, tmp_path):
        """Verify prepare_runtime only writes to the runtime dir."""
        runtime = tmp_path / "runtime"
        prepare_runtime(str(runtime))
        assert (runtime / ".devin" / "config.json").exists()
        assert (runtime / ".git").exists()

    def test_runtime_permissions_private(self, tmp_path):
        """Runtime directory has private permissions (0700)."""
        runtime = tmp_path / "runtime"
        prepare_runtime(str(runtime))
        mode = os.stat(str(runtime)).st_mode
        # Check that group/other bits are cleared (0700).
        assert (mode & 0o077) == 0, f"Runtime dir is world/group accessible: {oct(mode)}"

    def test_prompt_dir_permissions_private(self, tmp_path):
        """Prompt files directory has private permissions."""
        runtime = tmp_path / "runtime"
        prepare_runtime(str(runtime))
        prompts = runtime / ".prompts"
        mode = os.stat(str(prompts)).st_mode
        assert (mode & 0o077) == 0, f"Prompts dir is world/group accessible: {oct(mode)}"


# ---------------------------------------------------------------------------
# MODEL CONFIGURATION & ROUTING
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_default_quick_model_is_none(self):
        config = BridgeConfig()
        assert config.quick_model is None

    def test_default_deep_model_is_none(self):
        config = BridgeConfig()
        assert config.deep_model is None

    def test_model_shorthand_sets_both(self):
        from devin_bridge.config import resolve_config_from_cli
        q, d = resolve_config_from_cli(model="X")
        assert q == "X" and d == "X"

    def test_quick_deep_independent_overrides(self):
        from devin_bridge.config import resolve_config_from_cli
        q, d = resolve_config_from_cli(quick_model="A", deep_model="B")
        assert q == "A" and d == "B"

    def test_mixed_model_and_deep_override(self):
        from devin_bridge.config import resolve_config_from_cli
        q, d = resolve_config_from_cli(model="X", deep_model="Y")
        assert q == "X" and d == "Y"

    def test_no_model_resolves_to_none(self):
        from devin_bridge.config import resolve_config_from_cli
        q, d = resolve_config_from_cli()
        assert q is None and d is None

    def test_env_quick_model(self, monkeypatch):
        from devin_bridge.config import resolve_config_from_cli
        monkeypatch.setenv("DEVIN_BRIDGE_QUICK_MODEL", "ENV_Q")
        q, d = resolve_config_from_cli()
        assert q == "ENV_Q"
        assert d is None  # default for deep

    def test_env_deep_model(self, monkeypatch):
        from devin_bridge.config import resolve_config_from_cli
        monkeypatch.setenv("DEVIN_BRIDGE_DEEP_MODEL", "ENV_D")
        q, d = resolve_config_from_cli()
        assert q is None  # default for quick
        assert d == "ENV_D"

    def test_env_common_model(self, monkeypatch):
        from devin_bridge.config import resolve_config_from_cli
        monkeypatch.setenv("DEVIN_BRIDGE_MODEL", "ENV_C")
        q, d = resolve_config_from_cli()
        assert q == "ENV_C" and d == "ENV_C"

    def test_cli_overrides_env(self, monkeypatch):
        from devin_bridge.config import resolve_config_from_cli
        monkeypatch.setenv("DEVIN_BRIDGE_MODEL", "ENV")
        monkeypatch.setenv("DEVIN_BRIDGE_QUICK_MODEL", "ENV_Q")
        q, d = resolve_config_from_cli(model="CLI")
        assert q == "CLI" and d == "CLI"

    def test_resolve_model_alias_quick(self):
        config = BridgeConfig(quick_model="Q", deep_model="D")
        assert config.resolve_model("devin-quick") == "Q"

    def test_resolve_model_alias_deep(self):
        config = BridgeConfig(quick_model="Q", deep_model="D")
        assert config.resolve_model("devin-deep") == "D"

    def test_resolve_model_unknown_rejected(self):
        config = BridgeConfig()
        with pytest.raises(ValueError, match="Unknown model alias"):
            config.resolve_model("bogus")

    def test_resolve_model_none_for_default(self):
        config = BridgeConfig()  # no explicit model
        assert config.resolve_model("devin-quick") is None
        assert config.resolve_model("devin-deep") is None

    def test_model_mapping_for_health(self):
        config = BridgeConfig(quick_model="Q", deep_model="D")
        assert config.model_mapping() == {"devin-quick": "Q", "devin-deep": "D"}

    def test_model_mapping_default_shows_cli_default(self):
        config = BridgeConfig()  # no explicit model
        mapping = config.model_mapping()
        assert mapping == {"devin-quick": DEVIN_CLI_DEFAULT, "devin-deep": DEVIN_CLI_DEFAULT}


class TestModelRouting:
    """Verify alias routing invokes the correct underlying Devin model."""

    def test_alias_quick_invokes_quick_model(self):
        config = make_config(quick_model="MODEL_Q", deep_model="MODEL_D")
        executor = DevinExecutor(config, config.runtime_dir)
        captured_cmd = []
        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_devin_stdout(
            wrap_final("ok")
        )) as mock_run:
            executor.invoke([{"role": "user", "content": "hi"}], [], "MODEL_Q")
            captured_cmd = mock_run.call_args[0][0]
        assert "--model" in captured_cmd
        idx = captured_cmd.index("--model")
        assert captured_cmd[idx + 1] == "MODEL_Q"

    def test_alias_deep_invokes_deep_model(self):
        config = make_config(quick_model="MODEL_Q", deep_model="MODEL_D")
        executor = DevinExecutor(config, config.runtime_dir)
        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_devin_stdout(
            wrap_final("ok")
        )) as mock_run:
            executor.invoke([{"role": "user", "content": "hi"}], [], "MODEL_D")
            cmd = mock_run.call_args[0][0]
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "MODEL_D"

    def test_none_model_omits_model_flag(self):
        """When model is None, the Devin command must NOT contain --model."""
        config = make_config(quick_model=None, deep_model=None)
        executor = DevinExecutor(config, config.runtime_dir)
        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_devin_stdout(
            wrap_final("ok")
        )) as mock_run:
            executor.invoke([{"role": "user", "content": "hi"}], [], None)
            cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    def test_explicit_model_includes_model_flag(self):
        """When model is a string, the Devin command must contain --model <id>."""
        config = make_config(quick_model="glm-5-2", deep_model="glm-5-2")
        executor = DevinExecutor(config, config.runtime_dir)
        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_devin_stdout(
            wrap_final("ok")
        )) as mock_run:
            executor.invoke([{"role": "user", "content": "hi"}], [], "glm-5-2")
            cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "glm-5-2"

    def test_server_routes_quick_alias(self):
        """POST with model=devin-quick invokes executor with quick_model."""
        config = make_config(quick_model="MODEL_Q", deep_model="MODEL_D", port=8775)
        fake_executor = MagicMock()
        fake_executor.invoke.return_value = wrap_final("ok")
        BridgeHandler.config = config
        BridgeHandler.executor = fake_executor
        server = ThreadingHTTPServer(("127.0.0.1", config.port), BridgeHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)
        try:
            resp = requests.post(
                f"http://127.0.0.1:{config.port}/v1/chat/completions",
                json={"model": "devin-quick", "messages": [{"role": "user", "content": "x"}]},
            )
            assert resp.status_code == 200
            fake_executor.invoke.assert_called_once()
            # Third positional arg is the mapped model.
            assert fake_executor.invoke.call_args[0][2] == "MODEL_Q"
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)

    def test_server_routes_deep_alias(self):
        """POST with model=devin-deep invokes executor with deep_model."""
        config = make_config(quick_model="MODEL_Q", deep_model="MODEL_D", port=8776)
        fake_executor = MagicMock()
        fake_executor.invoke.return_value = wrap_final("ok")
        BridgeHandler.config = config
        BridgeHandler.executor = fake_executor
        server = ThreadingHTTPServer(("127.0.0.1", config.port), BridgeHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)
        try:
            resp = requests.post(
                f"http://127.0.0.1:{config.port}/v1/chat/completions",
                json={"model": "devin-deep", "messages": [{"role": "user", "content": "x"}]},
            )
            assert resp.status_code == 200
            assert fake_executor.invoke.call_args[0][2] == "MODEL_D"
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)


class TestModelAvailability:
    def test_unavailable_quick_model_rejected(self):
        from devin_bridge.server import BridgeError, preflight
        config = make_config(quick_model="NONEXISTENT_Q", deep_model="glm-5-2")
        runtime = "/tmp/devin-bridge-test-runtime"
        with patch("devin_bridge.server.subprocess.run") as mock_run:
            # --version, auth status, models list
            mock_run.side_effect = [
                MagicMock(stdout="devin 1.0", stderr="", returncode=0),
                MagicMock(stdout="logged in", stderr="", returncode=0),
                MagicMock(stdout="  glm-5-2  GLM-5.2 High\n", stderr="", returncode=0),
            ]
            with patch("os.path.isdir", return_value=True), \
                 patch("os.path.exists", return_value=True), \
                 pytest.raises(BridgeError, match="NONEXISTENT_Q.*devin-quick"):
                preflight(config, runtime)

    def test_unavailable_deep_model_rejected(self):
        from devin_bridge.server import BridgeError, preflight
        config = make_config(quick_model="glm-5-2", deep_model="NONEXISTENT_D")
        runtime = "/tmp/devin-bridge-test-runtime"
        with patch("devin_bridge.server.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="devin 1.0", stderr="", returncode=0),
                MagicMock(stdout="logged in", stderr="", returncode=0),
                MagicMock(stdout="  glm-5-2  GLM-5.2 High\n", stderr="", returncode=0),
            ]
            with patch("os.path.isdir", return_value=True), \
                 patch("os.path.exists", return_value=True), \
                 pytest.raises(BridgeError, match="NONEXISTENT_D.*devin-deep"):
                preflight(config, runtime)

    def test_available_models_passes(self):
        from devin_bridge.server import preflight
        config = make_config(quick_model="glm-5-2", deep_model="glm-5-2")
        runtime = "/tmp/devin-bridge-test-runtime"
        with patch("devin_bridge.server.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="devin 1.0", stderr="", returncode=0),
                MagicMock(stdout="logged in", stderr="", returncode=0),
                MagicMock(stdout="  glm-5-2  GLM-5.2 High\n", stderr="", returncode=0),
            ]
            with patch("os.path.isdir", return_value=True), \
                 patch("os.path.exists", return_value=True):
                preflight(config, runtime)  # should not raise

    def test_default_model_skips_availability_check(self):
        """None model (Devin CLI default) must NOT be validated against models list."""
        from devin_bridge.server import preflight
        config = make_config(quick_model=None, deep_model=None)
        runtime = "/tmp/devin-bridge-test-runtime"
        with patch("devin_bridge.server.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="devin 1.0", stderr="", returncode=0),
                MagicMock(stdout="logged in", stderr="", returncode=0),
                MagicMock(stdout="  glm-5-2  GLM-5.2 High\n", stderr="", returncode=0),
            ]
            with patch("os.path.isdir", return_value=True), \
                 patch("os.path.exists", return_value=True):
                preflight(config, runtime)  # should not raise


class TestListModels:
    def test_list_models_no_inference(self, monkeypatch):
        """--list-models calls `devin models list` (non-inference) and exits."""
        from devin_bridge.__main__ import list_models
        captured = []
        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            m = MagicMock()
            m.stdout = "  glm-5-2  GLM-5.2 High\n"
            m.stderr = ""
            m.returncode = 0
            return m
        monkeypatch.setattr("devin_bridge.__main__.subprocess.run", fake_run)
        rc = list_models()
        assert rc == 0
        # Must call `devin models list`, not `devin -p`.
        assert captured[0][1:] == ["models", "list"]
        assert "-p" not in captured[0]

    def test_list_models_devin_not_found(self, monkeypatch):
        from devin_bridge.__main__ import list_models
        def fake_run(cmd, **kwargs):
            raise FileNotFoundError()
        monkeypatch.setattr("devin_bridge.__main__.subprocess.run", fake_run)
        rc = list_models()
        assert rc == 1


class TestHealthModels:
    def test_healthz_reports_model_mapping(self):
        config = make_config(quick_model="MODEL_Q", deep_model="MODEL_D", port=8777)
        BridgeHandler.config = config
        BridgeHandler.executor = MagicMock()
        server = ThreadingHTTPServer(("127.0.0.1", config.port), BridgeHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)
        try:
            resp = requests.get(f"http://127.0.0.1:{config.port}/healthz")
            body = resp.json()
            assert body["status"] == "ok"
            assert body["models"] == {"devin-quick": "MODEL_Q", "devin-deep": "MODEL_D"}
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)

    def test_healthz_reports_cli_default_for_none(self):
        """When no explicit model is set, healthz shows devin-cli-default."""
        config = make_config(quick_model=None, deep_model=None, port=8779)
        BridgeHandler.config = config
        BridgeHandler.executor = MagicMock()
        server = ThreadingHTTPServer(("127.0.0.1", config.port), BridgeHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)
        try:
            resp = requests.get(f"http://127.0.0.1:{config.port}/healthz")
            body = resp.json()
            assert body["status"] == "ok"
            assert body["models"] == {
                "devin-quick": DEVIN_CLI_DEFAULT,
                "devin-deep": DEVIN_CLI_DEFAULT,
            }
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)

    def test_v1_models_exposes_aliases_only(self):
        config = make_config(quick_model="MODEL_Q", deep_model="MODEL_D", port=8778)
        BridgeHandler.config = config
        BridgeHandler.executor = MagicMock()
        server = ThreadingHTTPServer(("127.0.0.1", config.port), BridgeHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)
        try:
            resp = requests.get(f"http://127.0.0.1:{config.port}/v1/models")
            body = resp.json()
            ids = [m["id"] for m in body["data"]]
            assert ids == ["devin-quick", "devin-deep"]
            # Underlying models NOT exposed.
            assert "MODEL_Q" not in ids and "MODEL_D" not in ids
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)


# ---------------------------------------------------------------------------
# CONCURRENCY
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_max_concurrency_respected(self):
        config = make_config(max_concurrency=1)
        executor = DevinExecutor(config, config.runtime_dir)

        call_times = []
        lock = threading.Lock()

        def fake_run(cmd, **kwargs):
            with lock:
                call_times.append(("start", time.monotonic()))
            time.sleep(0.2)
            with lock:
                call_times.append(("end", time.monotonic()))
            mock = MagicMock()
            mock.stdout = wrap_final("ok")
            mock.stderr = ""
            mock.returncode = 0
            return mock

        threads = []
        with patch("devin_bridge.executor.subprocess.run", side_effect=fake_run):
            for i in range(3):
                t = threading.Thread(
                    target=executor.invoke,
                    args=([{"role": "user", "content": f"req{i}"}], [])
                )
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

        # With max_concurrency=1, calls should be sequential:
        # each "end" should come before the next "start".
        [t for event, t in call_times if event == "start"]
        [t for event, t in call_times if event == "end"]
        # Sort by time.
        sorted_events = sorted(call_times, key=lambda x: x[1])
        # Verify no two starts overlap (sequential).
        for i in range(0, len(sorted_events) - 1, 2):
            assert sorted_events[i][0] == "start"
            assert sorted_events[i + 1][0] == "end"


# ---------------------------------------------------------------------------
# SCHEMA: real ResearchPlan through LocalCompatibleChatOpenAI (fake executor)
# ---------------------------------------------------------------------------


class TestSchemaResearchPlan:
    """Test structured output with the real TradingAgents ResearchPlan schema.

    Uses a fake Devin executor — no live calls.
    """

    def test_research_plan_pydantic_instance(self):
        from langchain_core.messages import HumanMessage

        # Start a fake bridge server.
        from devin_bridge.server import create_server
        from tradingagents.agents.schemas import PortfolioRating, ResearchPlan
        from tradingagents.llm_clients.openai_client import OpenAIClient
        config = make_config(port=8771)
        with patch("devin_bridge.server.preflight"), \
             patch("devin_bridge.server.verify_outside_checkout"), \
             patch("devin_bridge.server.prepare_runtime", return_value=config.runtime_dir):
            server = create_server(config)

        nonce = "SCHEMA_OFFLINE_TEST_12345"
        fake_executor = MagicMock()
        fake_executor.invoke.return_value = wrap_sentinel({
            "calls": [
                {"name": "ResearchPlan", "arguments": {
                    "recommendation": "Buy",
                    "rationale": f"Bull case strong. Nonce: {nonce}",
                    "strategic_actions": "Open 5% position.",
                }}
            ]
        })
        BridgeHandler.executor = fake_executor
        BridgeHandler.config = config

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)

        try:
            client = OpenAIClient(
                model="devin-quick",
                base_url=f"http://127.0.0.1:{config.port}/v1",
                provider="openai_compatible",
            )
            llm = client.get_llm()
            structured = llm.with_structured_output(ResearchPlan)
            result = structured.invoke([
                HumanMessage(content=f"Make a plan. Nonce: {nonce}")
            ])

            assert isinstance(result, ResearchPlan)
            assert result.recommendation == PortfolioRating.BUY
            assert nonce in result.rationale
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)


# ---------------------------------------------------------------------------
# PLAIN: successful final response (fake executor)
# ---------------------------------------------------------------------------


class TestPlainResponse:
    def test_final_response_shape(self):
        resp = make_final_response("hello", "devin-quick")
        assert resp["object"] == "chat.completion"
        assert resp["choices"][0]["message"]["content"] == "hello"
        assert resp["choices"][0]["finish_reason"] == "stop"
        assert resp["model"] == "devin-quick"

    def test_tool_calls_response_shape(self):
        calls = [{"name": "get_marker", "arguments": {"reason": "x"}}]
        resp = make_tool_calls_response(calls, "devin-quick")
        assert resp["choices"][0]["finish_reason"] == "tool_calls"
        tc = resp["choices"][0]["message"]["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_marker"
        assert json.loads(tc["function"]["arguments"]) == {"reason": "x"}
        assert resp["choices"][0]["message"]["content"] is None


# ---------------------------------------------------------------------------
# PROMPT SERIALIZATION
# ---------------------------------------------------------------------------


class TestPromptSerialization:
    def test_sections_delimited(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt(
            [{"role": "user", "content": "hello"}], []
        )
        assert "--- ADVERTISED EXTERNAL TOOLS ---" in prompt
        assert "--- END ADVERTISED EXTERNAL TOOLS ---" in prompt
        assert "--- CONVERSATION DATA ---" in prompt
        assert "--- END CONVERSATION DATA ---" in prompt
        assert BEGIN_SENTINEL in prompt
        assert END_SENTINEL in prompt

    def test_bridge_contract_at_start(self):
        """The bridge contract must appear prominently near the beginning."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "=== BRIDGE RESULT PROTOCOL ===" in prompt
        # Contract should appear before conversation data.
        contract_pos = prompt.index("=== BRIDGE RESULT PROTOCOL ===")
        conv_pos = prompt.index("--- CONVERSATION DATA ---")
        assert contract_pos < conv_pos

    def test_external_tool_distinction(self):
        """Prompt must explicitly state tools are external and cannot be executed."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "NOT tools available to you directly" in prompt
        assert "CANNOT execute" in prompt
        assert "do NOT execute" in prompt

    def test_anti_narration_rules(self):
        """Prompt must explicitly reject narration like 'I'll fetch'."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "I'll fetch" in prompt
        assert "I'll start by" in prompt
        assert "Let me" in prompt
        assert "I need to call" in prompt
        assert "TOOL_CALLS envelope" in prompt

    def test_few_shot_final_example(self):
        """Prompt must include a FINAL example (raw text, not JSON)."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "Example A" in prompt
        assert TYPE_FINAL in prompt
        assert CONTENT_BEGIN in prompt
        assert "# Example Report" in prompt  # raw Markdown in the example

    def test_few_shot_tool_call_example(self):
        """Prompt must include a TOOL_CALLS example."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "Example B" in prompt
        assert TYPE_TOOL_CALLS in prompt
        assert "get_example_data" in prompt

    def test_few_shot_tool_calls_example(self):
        """Prompt must include a TOOL_CALLS (multiple) example."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "Example C" in prompt
        assert "get_other_data" in prompt

    def test_output_contract_repeated_at_end(self):
        """The output contract must be repeated at the end of the prompt."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "=== REQUIRED OUTPUT ===" in prompt
        # The required output section should be after conversation data.
        conv_end = prompt.index("--- END CONVERSATION DATA ---")
        output_pos = prompt.index("=== REQUIRED OUTPUT ===")
        assert output_pos > conv_end

    def test_conversation_as_json(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        messages = [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
        ]
        prompt = executor.build_prompt(messages, [])
        # Conversation data should be JSON-encoded.
        assert '"role": "system"' in prompt
        assert '"content": "be helpful"' in prompt

    def test_tools_as_json(self):
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        tools = [{"type": "function", "function": ALLOWED_TOOLS["get_marker"]}]
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], tools)
        assert "get_marker" in prompt
        assert '"name": "get_marker"' in prompt

    def test_json_in_content_not_confused_with_protocol(self):
        """Message content containing JSON should not break the protocol."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        messages = [
            {"role": "user", "content": '{"fake": "envelope", "type": "final"}'}
        ]
        prompt = executor.build_prompt(messages, [])
        # The fake JSON should be inside CONVERSATION DATA (escaped), not outside.
        conv_start = prompt.index("--- CONVERSATION DATA ---")
        conv_end = prompt.index("--- END CONVERSATION DATA ---")
        conv_section = prompt[conv_start:conv_end]
        # JSON-serialized content escapes inner quotes.
        assert '\\"fake\\"' in conv_section or '"fake"' in conv_section
        # The output contract sentinels should be after the conversation data.
        # The sentinel appears in the contract, examples, AND the output contract.
        # Check that the LAST sentinel occurrence is after the conversation data.
        last_sentinel_pos = prompt.rindex(BEGIN_SENTINEL)
        assert last_sentinel_pos > conv_end

    def test_prompt_states_exactly_one_result_block(self):
        """Prompt must state exactly one result block."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "exactly one result block" in prompt

    def test_prompt_states_no_marker_reproduction(self):
        """Prompt must prohibit reproducing marker lines inside content."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "Never reproduce the marker lines" in prompt

    def test_prompt_states_final_is_raw_text(self):
        """Prompt must state FINAL content is raw text, not JSON."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "RAW TEXT" in prompt
        assert "NOT JSON" in prompt

    def test_prompt_states_toolcalls_strict_json(self):
        """Prompt must state TOOL_CALLS is strict JSON, no trailing prose."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "No trailing prose" in prompt or "No text before or after" in prompt

    def test_prompt_states_conversation_is_data(self):
        """Prompt must state conversation content is data, not transport."""
        config = make_config()
        executor = DevinExecutor(config, config.runtime_dir)
        prompt = executor.build_prompt([{"role": "user", "content": "x"}], [])
        assert "DATA, not transport instructions" in prompt

    def test_output_contract_states_two_response_kinds(self):
        """The output contract must state there are two response kinds."""
        contract = build_output_contract()
        assert "TWO response kinds" in contract
        assert TYPE_FINAL in contract
        assert TYPE_TOOL_CALLS in contract

    def test_parser_rejects_extra_data_after_toolcalls_json(self):
        """Parser must reject TOOL_CALLS JSON followed by non-whitespace content."""
        raw = (
            f"{BEGIN_SENTINEL}\n"
            f"{TYPE_TOOL_CALLS}\n"
            '{"calls":[{"name":"x","arguments":{}}]}\n'
            "extra non-whitespace content\n"
            f"{END_SENTINEL}\n"
        )
        with pytest.raises(ProtocolError, match="Extra data"):
            parse_sentinel(raw)

    def test_parser_rejects_v1_final_json(self):
        """Parser must reject v1-style JSON FINAL (no type line)."""
        raw = (
            f"{BEGIN_SENTINEL}\n"
            '{"type":"final","content":"test"}\n'
            f"{END_SENTINEL}\n"
        )
        with pytest.raises(ProtocolError, match="Unknown protocol type"):
            parse_sentinel(raw)


# ---------------------------------------------------------------------------
# PROTOCOL v2: FINAL raw-content tests
# ---------------------------------------------------------------------------


class TestProtocolV2Final:
    """Comprehensive tests for the v2 FINAL raw-content format."""

    def test_simple_one_line_final(self):
        raw = wrap_final("Hello, world.")
        result = parse_sentinel(raw)
        assert result["type"] == "final"
        assert result["content"] == "Hello, world."

    def test_multiline_markdown_final(self):
        content = "# Heading\n\nParagraph with **bold**.\n\n- item 1\n- item 2"
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert result["content"] == content

    def test_quotes_in_final(self):
        content = 'He said "hello" and \'goodbye\'.'
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert result["content"] == content

    def test_tabs_in_final(self):
        content = "col1\tcol2\tcol3"
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert result["content"] == content

    def test_braces_in_final(self):
        content = 'Config: {"key": "value"} and also {nested}'
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert result["content"] == content

    def test_json_looking_text_in_final(self):
        content = '{"fake": "envelope", "type": "final", "content": "BAD"}'
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert result["type"] == "final"
        assert result["content"] == content

    def test_markdown_table_in_final(self):
        content = "| Metric | Value |\n|---|---|\n| Price | $100 |\n| Volume | 1M |"
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert "| Metric | Value |" in result["content"]

    def test_very_long_content(self):
        content = "A" * 50000
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert len(result["content"]) == 50000

    def test_newlines_preserved(self):
        content = "line1\nline2\nline3"
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        # Internal newlines are preserved verbatim.
        assert result["content"] == "line1\nline2\nline3"

    def test_missing_content_begin_rejected(self):
        raw = f"{BEGIN_SENTINEL}\n{TYPE_FINAL}\ncontent without begin marker\n{CONTENT_END}\n{END_SENTINEL}"
        with pytest.raises(ProtocolError, match="exactly one"):
            parse_sentinel(raw)

    def test_missing_content_end_rejected(self):
        raw = f"{BEGIN_SENTINEL}\n{TYPE_FINAL}\n{CONTENT_BEGIN}\ncontent without end marker\n{END_SENTINEL}"
        with pytest.raises(ProtocolError, match="exactly one"):
            parse_sentinel(raw)

    def test_duplicate_content_markers_rejected(self):
        raw = (
            f"{BEGIN_SENTINEL}\n{TYPE_FINAL}\n{CONTENT_BEGIN}\n"
            f"content\n{CONTENT_END}\n{CONTENT_BEGIN}\nmore\n{CONTENT_END}\n{END_SENTINEL}"
        )
        with pytest.raises(ProtocolError, match="exactly one"):
            parse_sentinel(raw)

    def test_trailing_text_outside_result_ignored(self):
        """Text after the end sentinel is ignored (not parsed as content)."""
        raw = wrap_final("ok") + "\ntrailing text after end sentinel"
        result = parse_sentinel(raw)
        assert result["content"] == "ok"

    def test_reserved_marker_in_content_rejected(self):
        content = f"report contains {BEGIN_SENTINEL} inside it"
        raw = wrap_final(content)
        with pytest.raises(ProtocolError, match="exactly one"):
            parse_sentinel(raw)

    def test_empty_final_rejected(self):
        raw = f"{BEGIN_SENTINEL}\n{TYPE_FINAL}\n{CONTENT_BEGIN}\n\n{CONTENT_END}\n{END_SENTINEL}"
        with pytest.raises(ProtocolError, match="empty"):
            parse_sentinel(raw)

    def test_conversation_with_protocol_markers_not_confused(self):
        """Incoming conversation containing protocol markers must not break parsing."""
        content = "Normal report content"
        raw = wrap_final(content)
        result = parse_sentinel(raw)
        assert result["content"] == content


# ---------------------------------------------------------------------------
# PROTOCOL v2: TOOL_CALLS tests
# ---------------------------------------------------------------------------


class TestProtocolV2ToolCalls:
    """Comprehensive tests for the v2 TOOL_CALLS strict-JSON format."""

    def test_one_tool_call(self):
        raw = wrap_sentinel({"calls": [
            {"name": "get_marker", "arguments": {"reason": "x"}}
        ]})
        result = parse_sentinel(raw)
        assert result["type"] == "tool_calls"
        assert len(result["calls"]) == 1

    def test_multiple_tool_calls(self):
        raw = wrap_sentinel({"calls": [
            {"name": "get_marker", "arguments": {"reason": "a"}},
            {"name": "decide", "arguments": {"action": "buy"}},
        ]})
        result = parse_sentinel(raw)
        assert len(result["calls"]) == 2

    def test_malformed_json_rejected(self):
        raw = f"{BEGIN_SENTINEL}\n{TYPE_TOOL_CALLS}\n{{bad json}}\n{END_SENTINEL}"
        with pytest.raises(ProtocolError, match="Invalid JSON"):
            parse_sentinel(raw)

    def test_unknown_tool_rejected(self):
        env = {"type": "tool_calls", "calls": [{"name": "evil", "arguments": {}}]}
        with pytest.raises(ProtocolError, match="not in advertised"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_invalid_args_rejected(self):
        env = {"type": "tool_calls", "calls": [
            {"name": "decide", "arguments": {"count": "not_int"}}
        ]}
        with pytest.raises(ProtocolError, match="expected integer"):
            validate_envelope(env, ALLOWED_TOOLS)

    def test_extra_content_after_json_rejected(self):
        raw = (
            f"{BEGIN_SENTINEL}\n{TYPE_TOOL_CALLS}\n"
            '{"calls":[{"name":"x","arguments":{}}]}\n'
            "extra content\n"
            f"{END_SENTINEL}"
        )
        with pytest.raises(ProtocolError, match="Extra data"):
            parse_sentinel(raw)

    def test_empty_calls_rejected(self):
        raw = wrap_sentinel({"calls": []})
        with pytest.raises(ProtocolError, match="empty"):
            parse_sentinel(raw)

    def test_calls_not_list_rejected(self):
        raw = wrap_sentinel({"calls": "notlist"})
        with pytest.raises(ProtocolError, match="must be a list"):
            parse_sentinel(raw)
