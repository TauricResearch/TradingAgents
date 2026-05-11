from __future__ import annotations

import subprocess

from langchain_core.messages import HumanMessage

from tradingagents.llm_clients.claude_code_client import ClaudeCodeClient
from tradingagents.llm_clients.factory import create_llm_client


class DummyTool:
    name = "get_stock_data"
    description = "Fetch stock data"
    args = {"ticker": {"type": "string"}}


def test_factory_creates_claude_code_client():
    client = create_llm_client("claude-code", "sonnet")
    assert isinstance(client, ClaudeCodeClient)


def test_claude_code_chat_model_invokes_print_mode(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = ClaudeCodeClient("sonnet", command="claude-test", timeout=12).get_llm()
    result = llm.invoke([HumanMessage(content="hello")])

    assert result.content == "answer"
    args, kwargs = calls[0]
    assert args[:4] == ["claude-test", "-p", "--output-format", "text"]
    assert "--no-session-persistence" in args
    assert "--tools" in args
    assert kwargs["timeout"] == 12
    assert "Human:\nhello" in kwargs["input"]


def test_claude_code_command_supports_multi_word_wrapper(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = ClaudeCodeClient("sonnet", command="npx claude", timeout=12).get_llm()
    llm.invoke([HumanMessage(content="hello")])

    assert calls[0][:3] == ["npx", "claude", "-p"]


def test_claude_code_error_uses_stdout_when_stderr_empty(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=2,
            stdout="stdout failure",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = ClaudeCodeClient("sonnet").get_llm()

    try:
        llm.invoke([HumanMessage(content="hello")])
    except RuntimeError as exc:
        assert "stdout failure" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_claude_code_extra_args_use_tradingagents_env(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="answer", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CODE_EXTRA_ARGS", "--verbose --permission-mode plan")

    llm = ClaudeCodeClient("sonnet").get_llm()
    llm.invoke([HumanMessage(content="hello")])

    assert "--verbose" in calls[0]
    assert "--permission-mode" in calls[0]
    assert "plan" in calls[0]


def test_claude_code_tool_call_json_becomes_langchain_tool_call(monkeypatch):
    payload = (
        'result:\n{"content":"","tool_calls":'
        '[{"name":"get_stock_data","args":{"ticker":"NVDA"}}]}'
    )

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    llm = ClaudeCodeClient("sonnet").get_llm().bind_tools([DummyTool()])
    result = llm.invoke([HumanMessage(content="fetch NVDA")])

    assert result.content == ""
    assert result.tool_calls[0]["name"] == "get_stock_data"
    assert result.tool_calls[0]["args"] == {"ticker": "NVDA"}
