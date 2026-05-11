from __future__ import annotations

import subprocess

from langchain_core.messages import HumanMessage

from tradingagents.llm_clients.codex_client import CodexClient
from tradingagents.llm_clients.factory import create_llm_client


class DummyTool:
    name = "get_stock_data"
    description = "Fetch stock data"
    args = {"ticker": {"type": "string"}}


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
    assert "read-only" in args
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
        'result:\n{"content":"","tool_calls":'
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
