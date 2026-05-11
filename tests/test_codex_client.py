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
