"""Claude Code: Claude through the local ``claude`` CLI, signed in with its own account.

Every call is one ``claude -p`` run, stubbed here so no CLI or account is needed.
Tool calls and structured output come back through ``--json-schema``; the tools
themselves still run in the graph.
"""
import json
import subprocess

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client
from tradingagents.llm_clients.validators import validate_model


@tool
def get_price(ticker: str) -> str:
    """Latest close for a ticker."""
    return "100"


class Rating(BaseModel):
    rating: str


def _stub_cli(monkeypatch, *replies, returncode=0):
    """Answer each ``claude -p`` run with the next reply; return the recorded runs."""
    import tradingagents.llm_clients.claude_code_client as cc

    monkeypatch.setattr(cc.shutil, "which", lambda name: "/usr/bin/claude")
    runs, queue = [], list(replies)

    def fake_run(cmd, **kwargs):
        runs.append({"cmd": cmd, "input": kwargs["input"]})
        reply = queue.pop(0)
        stdout = reply if isinstance(reply, str) else json.dumps(reply)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    return runs


def _flag(cmd, name):
    return cmd[cmd.index(name) + 1]


@pytest.mark.unit
def test_factory_routes_claude_code():
    client = create_llm_client("claude_code", "claude-sonnet-5")
    assert type(client).__name__ == "ClaudeCodeClient"


@pytest.mark.unit
def test_no_key_env_and_any_model():
    # Claude Code signs in with its own account, so there is no key to ask for.
    assert get_api_key_env("claude_code") is None
    assert validate_model("claude_code", "sonnet") is True


@pytest.mark.unit
def test_effort_is_forwarded_like_anthropic():
    config = {"llm_provider": "claude_code", "anthropic_effort": "high"}
    assert build_llm_kwargs(config)["effort"] == "high"


@pytest.mark.unit
def test_missing_cli_is_a_clear_error(monkeypatch):
    import tradingagents.llm_clients.claude_code_client as cc

    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
    monkeypatch.setattr(cc.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Claude Code CLI"):
        create_llm_client("claude_code", "claude-sonnet-5").get_llm()


@pytest.mark.unit
def test_plain_call_runs_cli_without_its_own_tools(monkeypatch):
    runs = _stub_cli(monkeypatch, {"result": "pong", "is_error": False})
    llm = create_llm_client("claude_code", "claude-opus-5-5", effort="high").get_llm()

    reply = llm.invoke([SystemMessage(content="Be brief."), HumanMessage(content="ping")])

    assert reply.content == "pong"
    cmd = runs[0]["cmd"]
    assert _flag(cmd, "--model") == "claude-opus-5-5"
    assert _flag(cmd, "--tools") == ""
    assert _flag(cmd, "--system-prompt") == "Be brief."
    assert _flag(cmd, "--effort") == "high"
    assert "--strict-mcp-config" in cmd
    assert "--json-schema" not in cmd
    assert "ping" in runs[0]["input"]


@pytest.mark.unit
def test_bound_tools_come_back_as_tool_calls(monkeypatch):
    runs = _stub_cli(
        monkeypatch,
        {"structured_output": {"tool_calls": [
            {"name": "get_price", "args": {"ticker": "NVDA"}},
            {"name": "not_a_tool", "args": {}},
        ], "content": ""}},
    )
    llm = create_llm_client("claude_code", "claude-sonnet-5").get_llm().bind_tools([get_price])

    reply = llm.invoke([HumanMessage(content="Price of NVDA?")])

    assert [(c["name"], c["args"]) for c in reply.tool_calls] == [("get_price", {"ticker": "NVDA"})]
    assert reply.content == ""
    assert "get_price" in _flag(runs[0]["cmd"], "--system-prompt")
    assert "--json-schema" in runs[0]["cmd"]


@pytest.mark.unit
def test_tool_results_reach_the_next_turn_and_final_answer_is_content(monkeypatch):
    runs = _stub_cli(
        monkeypatch, {"structured_output": {"tool_calls": [], "content": "NVDA closed at 100."}}
    )
    llm = create_llm_client("claude_code", "claude-sonnet-5").get_llm().bind_tools([get_price])
    history = [
        HumanMessage(content="Price of NVDA?"),
        AIMessage(content="", tool_calls=[{"name": "get_price", "args": {"ticker": "NVDA"}, "id": "c1"}]),
        ToolMessage(content="100", name="get_price", tool_call_id="c1"),
    ]

    reply = llm.invoke(history)

    assert reply.tool_calls == []
    assert reply.content == "NVDA closed at 100."
    assert '"get_price"' in runs[0]["input"]
    assert "[Tool result: get_price]\n100" in runs[0]["input"]


@pytest.mark.unit
def test_structured_output_validates_into_the_schema(monkeypatch):
    runs = _stub_cli(monkeypatch, {"structured_output": {"rating": "Buy"}})
    llm = create_llm_client("claude_code", "claude-sonnet-5").get_llm()

    result = llm.with_structured_output(Rating).invoke("Rate NVDA.")

    assert result == Rating(rating="Buy")
    assert json.loads(_flag(runs[0]["cmd"], "--json-schema"))["properties"]["rating"]


@pytest.mark.unit
def test_cli_error_is_retried_then_raised(monkeypatch):
    error = {"is_error": True, "result": "usage limit reached"}
    runs = _stub_cli(monkeypatch, error, error, error)
    llm = create_llm_client("claude_code", "claude-sonnet-5", max_retries=2).get_llm()

    with pytest.raises(RuntimeError, match="usage limit reached"):
        llm.invoke("ping")
    assert len(runs) == 3


@pytest.mark.unit
def test_usage_is_logged_when_asked(monkeypatch, tmp_path):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setenv("TRADINGAGENTS_CLAUDE_CODE_USAGE_LOG", str(log))
    _stub_cli(monkeypatch, {"result": "pong", "total_cost_usd": 0.01, "usage": {"output_tokens": 3}})

    create_llm_client("claude_code", "claude-sonnet-5").get_llm().invoke("ping")

    entry = json.loads(log.read_text())
    assert entry == {"model": "claude-sonnet-5", "cost_usd": 0.01, "usage": {"output_tokens": 3}}
