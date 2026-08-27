from __future__ import annotations

import builtins
import subprocess

from langchain_core.messages import HumanMessage

import tradingagents.llm_clients.codex_client as codex_module
from tradingagents.llm_clients.codex_client import CodexClient
from tradingagents.llm_clients.factory import create_llm_client


class DummyTool:
    name = "get_stock_data"
    description = "Fetch stock data"
    args = {"ticker": {"type": "string"}}


class _Tty:
    @staticmethod
    def isatty():
        return True

    def write(self, *_args, **_kwargs):
        return 0

    def flush(self):
        return None


class _NonTty(_Tty):
    @staticmethod
    def isatty():
        return False


def _force_interactive(monkeypatch):
    monkeypatch.setattr(codex_module.sys, "stdin", _Tty())
    monkeypatch.setattr(codex_module.sys, "stderr", _Tty())


def test_factory_creates_codex_client():
    client = create_llm_client("codex", "gpt-5.5")
    assert isinstance(client, CodexClient)


def test_codex_chat_model_invokes_exec_read_only_mode(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = CodexClient("gpt-5.5", command="codex-test", timeout=12).get_llm()
    result = llm.invoke([HumanMessage(content="hello")])

    assert result.content == "answer"
    args, kwargs = calls[0]
    assert args[:2] == ["codex-test", "exec"]
    assert "--ephemeral" in args
    sandbox_index = args.index("--sandbox")
    assert args[sandbox_index + 1] == "read-only"
    assert "--ask-for-approval" not in args
    assert "--output-last-message" in args
    assert kwargs["timeout"] == 12
    assert "Human:\nhello" in kwargs["input"]


def test_codex_command_supports_multi_word_wrapper(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = CodexClient("gpt-5.5", command="npx codex", timeout=12).get_llm()
    llm.invoke([HumanMessage(content="hello")])

    assert calls[0][:3] == ["npx", "codex", "exec"]


def test_codex_error_uses_stdout_when_stderr_empty(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=2,
            stdout="stdout failure",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = CodexClient("gpt-5.5").get_llm()

    try:
        llm.invoke([HumanMessage(content="hello")])
    except RuntimeError as exc:
        assert "stdout failure" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_codex_auth_error_explains_relogin(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr=(
                "ERROR: Your access token could not be refreshed because your "
                "refresh token was already used."
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = CodexClient("gpt-5.5").get_llm()

    try:
        llm.invoke([HumanMessage(content="hello")])
    except RuntimeError as exc:
        message = str(exc)
        assert "codex logout" in message
        assert "codex login" in message
        assert "already-invalid Codex refresh token" in message
    else:
        raise AssertionError("Expected RuntimeError")


def test_codex_auth_error_waits_for_reauth_and_retries_once(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr=(
                    "ERROR: Your access token could not be refreshed because your "
                    "refresh token was already used."
                ),
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    _force_interactive(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda prompt: "")
    monkeypatch.setenv("TRADINGAGENTS_CODEX_AUTH_RETRY", "1")

    llm = CodexClient("gpt-5.5").get_llm()
    result = llm.invoke([HumanMessage(content="hello")])

    assert result.content == "answer"
    assert len(calls) == 2


def test_codex_auth_retry_can_be_disabled(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr=(
                "ERROR: Your access token could not be refreshed because your "
                "refresh token was already used."
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    _force_interactive(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda prompt: "")
    monkeypatch.setenv("TRADINGAGENTS_CODEX_AUTH_RETRY", "0")

    llm = CodexClient("gpt-5.5").get_llm()

    try:
        llm.invoke([HumanMessage(content="hello")])
    except RuntimeError as exc:
        assert "codex logout" in str(exc)
        assert len(calls) == 1
    else:
        raise AssertionError("Expected RuntimeError")


def test_codex_auth_retry_is_disabled_by_default_even_in_tty(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="401 Unauthorized: token could not be refreshed",
        )

    def fail_if_prompted(_prompt):
        raise AssertionError("auth retry must be explicitly enabled")

    monkeypatch.setattr(subprocess, "run", fake_run)
    _force_interactive(monkeypatch)
    monkeypatch.setattr(builtins, "input", fail_if_prompted)
    monkeypatch.delenv("TRADINGAGENTS_CODEX_AUTH_RETRY", raising=False)

    llm = CodexClient("gpt-5.5").get_llm()

    try:
        llm.invoke([HumanMessage(content="hello")])
    except RuntimeError:
        assert len(calls) == 1
    else:
        raise AssertionError("Expected RuntimeError")


def test_codex_auth_retry_requires_stderr_tty(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="401 Unauthorized: token could not be refreshed",
        )

    def fail_if_prompted(_prompt):
        raise AssertionError("redirected runs must not block for input")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(codex_module.sys, "stdin", _Tty())
    monkeypatch.setattr(codex_module.sys, "stderr", _NonTty())
    monkeypatch.setattr(builtins, "input", fail_if_prompted)
    monkeypatch.setenv("TRADINGAGENTS_CODEX_AUTH_RETRY", "1")

    llm = CodexClient("gpt-5.5").get_llm()

    try:
        llm.invoke([HumanMessage(content="hello")])
    except RuntimeError:
        assert len(calls) == 1
    else:
        raise AssertionError("Expected RuntimeError")


def test_codex_exec_uses_process_lock(monkeypatch):
    class RecordingLock:
        def __init__(self):
            self.entered = False
            self.exited = False

        def __enter__(self):
            self.entered = True
            return self

        def __exit__(self, exc_type, exc, tb):
            self.exited = True
            return False

    lock = RecordingLock()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(codex_module, "_CODEX_EXEC_LOCK", lock)
    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = CodexClient("gpt-5.5").get_llm()
    llm.invoke([HumanMessage(content="hello")])

    assert calls
    assert lock.entered is True
    assert lock.exited is True


def test_codex_extra_args_use_tradingagents_env(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("TRADINGAGENTS_CODEX_EXTRA_ARGS", "--profile trading --config model=gpt-5.5")

    llm = CodexClient("gpt-5.5").get_llm()
    llm.invoke([HumanMessage(content="hello")])

    assert "--profile" in calls[0]
    assert "trading" in calls[0]
    assert "--config" in calls[0]
    assert "model=gpt-5.5" in calls[0]


def test_codex_tool_call_json_becomes_langchain_tool_call(monkeypatch):
    payload = (
        '{"content":"","tool_calls":'
        '[{"name":"get_stock_data","args":{"ticker":"NVDA"}}]}'
    )

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = CodexClient("gpt-5.5").get_llm().bind_tools([DummyTool()])
    result = llm.invoke([HumanMessage(content="fetch NVDA")])

    assert result.content == ""
    assert result.tool_calls[0]["name"] == "get_stock_data"
    assert result.tool_calls[0]["args"] == {"ticker": "NVDA"}


def test_codex_prose_with_embedded_json_is_not_dropped(monkeypatch):
    payload = 'Recommended allocation: {"AAPL":0.4,"NVDA":0.6}. I recommend BUY.'

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=payload, stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = CodexClient("gpt-5.5").get_llm().bind_tools([DummyTool()])
    result = llm.invoke([HumanMessage(content="recommend an allocation")])

    assert result.content == payload
    assert result.tool_calls == []
