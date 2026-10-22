"""Tests for the claude_code provider, which runs each call through ``claude -p``.

A fake ``claude`` executable records its argv and stdin and prints a canned
JSON result, so the tests pin the exact CLI contract without a subscription.
"""

import json
import logging
import os
import shutil
import stat
import sys

from typing import TypedDict

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from tradingagents.llm_clients import build_llm_kwargs, create_llm_client
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.claude_code_client import (
    ChatClaudeCode,
    ClaudeCodeClient,
    ClaudeCodeError,
)
from tradingagents.llm_clients.validators import validate_model

ISOLATION = [
    "--setting-sources", "", "--strict-mcp-config", "--tools", "",
    "--disable-slash-commands", "--no-session-persistence",
    "--exclude-dynamic-system-prompt-sections", "--max-turns", "3",
]

FAKE = f"""#!{sys.executable}
import json, os, sys
with open(os.environ["FAKE_CLAUDE_RECORD"], "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "stdin": sys.stdin.read(),
                        "env": sorted(k for k in os.environ if k.startswith(("ANTHROPIC", "CLAUDE_CODE")))}}) + "\\n")
sys.stdout.write(open(os.environ["FAKE_CLAUDE_RESPONSE"]).read())
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
"""


@tool
def get_price(ticker: str, date: str) -> str:
    """Closing price of a ticker on a date."""
    return "100"


@tool
def get_news(query: str) -> str:
    """News matching a query."""
    return "none"


class Window(BaseModel):
    start: str
    end: str


@tool
def get_range(window: Window) -> str:
    """Prices over a window."""
    return "none"


class Decision(BaseModel):
    rating: str
    reason: str


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Install the fake CLI; returns (path, respond, calls)."""
    exe = tmp_path / "claude"
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    record, response = tmp_path / "record.jsonl", tmp_path / "response.json"
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    monkeypatch.setenv("FAKE_CLAUDE_RESPONSE", str(response))

    def respond(exit_code=0, raw=None, **result):
        payload = {"type": "result", "is_error": False, "result": "", "num_turns": 1,
                   "total_cost_usd": 0.01, "usage": {"input_tokens": 3}, **result}
        response.write_text(raw if raw is not None else json.dumps(payload))
        monkeypatch.setenv("FAKE_CLAUDE_EXIT", str(exit_code))

    def calls():
        return [json.loads(line) for line in record.read_text().splitlines()]

    return str(exe), respond, calls


def model(exe, **kwargs):
    return ChatClaudeCode(model="claude-opus-5-5", executable=exe, **kwargs)


def flag(argv, name):
    return argv[argv.index(name) + 1]


@pytest.mark.unit
class TestPlainCalls:
    def test_runs_the_isolated_cli_with_the_transcript_on_stdin(self, fake):
        exe, respond, calls = fake
        respond(result="Hello")
        out = model(exe, effort="medium").invoke(
            [SystemMessage("Be terse."), SystemMessage("Use English."), HumanMessage("Hi")])

        assert out.content == "Hello"
        assert out.response_metadata["claude_code"] == {
            "total_cost_usd": 0.01, "usage": {"input_tokens": 3}, "num_turns": 1}
        assert out.usage_metadata == {"input_tokens": 3, "output_tokens": 0, "total_tokens": 3}
        (call,) = calls()
        assert call["argv"] == [
            "-p", "--model", "claude-opus-5-5", "--effort", "medium", *ISOLATION,
            "--system-prompt", "Be terse.\n\nUse English.", "--output-format", "json"]
        assert call["stdin"] == "[user]\nHi"

    def test_settings_that_route_away_from_the_sign_in_do_not_reach_the_cli(self, fake, monkeypatch):
        exe, respond, calls = fake
        routing = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                   "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"]
        for name in routing:
            monkeypatch.setenv(name, "1")
        monkeypatch.setenv("ANTHROPIC_LOG", "debug")
        respond(result="ok")
        model(exe).invoke("Hi")
        env = calls()[0]["env"]
        assert "ANTHROPIC_LOG" in env and not set(routing) & set(env)

    def test_effort_is_omitted_when_unset(self, fake):
        exe, respond, calls = fake
        respond(result="ok")
        model(exe).invoke("Hi")
        assert "--effort" not in calls()[0]["argv"]

    def test_block_content_is_rendered_as_text(self, fake):
        exe, respond, calls = fake
        respond(result="ok")
        model(exe).invoke([HumanMessage([{"type": "text", "text": "a"}, "b"])])
        assert calls()[0]["stdin"] == "[user]\na\nb"

    def test_non_text_blocks_are_refused(self, fake):
        exe, _, _ = fake
        with pytest.raises(ValueError, match="image_url"):
            model(exe).invoke([HumanMessage([{"type": "image_url", "image_url": "x"}])])

    def test_stop_sequences_are_refused(self, fake):
        exe, _, _ = fake
        with pytest.raises(ValueError):
            model(exe).invoke("Hi", stop=["\n"])


@pytest.mark.unit
class TestTools:
    def test_schema_has_one_branch_per_tool(self, fake):
        exe, respond, calls = fake
        respond(structured_output={"content": "done", "tool_calls": []})
        out = model(exe).bind_tools([get_price, get_news]).invoke("Hi")

        assert out.content == "done" and out.tool_calls == []
        argv = calls()[0]["argv"]
        schema = json.loads(flag(argv, "--json-schema"))
        assert schema["required"] == ["content", "tool_calls"]
        assert schema["additionalProperties"] is False
        branches = schema["properties"]["tool_calls"]["items"]["oneOf"]
        assert [b["properties"]["name"] for b in branches] == [
            {"const": "get_price"}, {"const": "get_news"}]
        assert set(branches[0]["properties"]["args"]["properties"]) == {"ticker", "date"}
        assert branches[0]["description"] == "Closing price of a ticker on a date."
        assert all(b["additionalProperties"] is False and b["required"] == ["name", "args"]
                   for b in branches)
        assert "tool_calls" in flag(argv, "--system-prompt")

    def test_tool_calls_get_ids_that_the_next_turn_replays(self, fake):
        exe, respond, calls = fake
        llm = model(exe).bind_tools([get_price])
        respond(structured_output={"content": "", "tool_calls": [
            {"name": "get_price", "args": {"ticker": "AAPL", "date": "2026-08-07"}}]})
        first = llm.invoke("Price?")

        (call,) = first.tool_calls
        assert first.content == ""
        assert call["name"] == "get_price" and call["type"] == "tool_call"
        assert call["args"] == {"ticker": "AAPL", "date": "2026-08-07"}
        assert call["id"].startswith("call_")

        respond(structured_output={"content": "It closed at 100.", "tool_calls": []})
        llm.invoke([HumanMessage("Price?"), first, ToolMessage("100", tool_call_id=call["id"])])
        stdin = calls()[1]["stdin"]
        assert f'"id": "{call["id"]}"' in stdin
        assert f"[tool result for {call['id']}]\n100" in stdin

    def test_an_unknown_tool_is_an_error(self, fake):
        exe, respond, _ = fake
        respond(structured_output={"content": "", "tool_calls": [{"name": "rm", "args": {}}]})
        with pytest.raises(ClaudeCodeError):
            model(exe).bind_tools([get_price]).invoke("Hi")

    @pytest.mark.parametrize("options", [{"tool_choice": "get_price"}, {"tool_choice": "any"},
                                         {"parallel_tool_calls": False}, {"strict": True}])
    def test_unsupported_tool_options_are_refused(self, fake, options):
        exe, _, _ = fake
        with pytest.raises(ValueError):
            model(exe).bind_tools([get_price], **options)

    def test_no_tools_means_a_plain_call(self, fake):
        exe, respond, calls = fake
        respond(result="ok")
        assert model(exe).bind_tools([get_price]).bind_tools([]).invoke("Hi").content == "ok"
        assert "--json-schema" not in calls()[0]["argv"]

    def test_nested_argument_models_are_inlined(self, fake):
        exe, respond, calls = fake
        respond(structured_output={"content": "", "tool_calls": []})
        model(exe).bind_tools([get_range]).invoke("Hi")
        schema = flag(calls()[0]["argv"], "--json-schema")
        assert "$ref" not in schema and '"start"' in schema

    def test_tools_and_structured_output_do_not_combine(self, fake):
        exe, _, _ = fake
        with pytest.raises(NotImplementedError):
            model(exe).bind_tools([get_price]).with_structured_output(Decision)
        with pytest.raises(ValueError):
            model(exe).with_structured_output(Decision).first.bind_tools([get_price])


@pytest.mark.unit
class TestStructuredOutput:
    def test_pydantic_schema_returns_an_instance(self, fake):
        exe, respond, calls = fake
        respond(structured_output={"rating": "Buy", "reason": "cheap"})
        out = model(exe).with_structured_output(Decision).invoke("Decide")

        assert out == Decision(rating="Buy", reason="cheap")
        argv = calls()[0]["argv"]
        assert json.loads(flag(argv, "--json-schema")) == Decision.model_json_schema()
        assert "tool_calls" not in flag(argv, "--system-prompt")

    def test_dict_schema_returns_a_dict(self, fake):
        exe, respond, _ = fake
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        respond(structured_output={"n": 3})
        assert model(exe).with_structured_output(schema).invoke("Count") == {"n": 3}

    @pytest.mark.parametrize("options", [{"include_raw": True}, {"method": "json_mode"}])
    def test_other_modes_are_not_implemented(self, fake, options):
        exe, _, _ = fake
        with pytest.raises(NotImplementedError):
            model(exe).with_structured_output(Decision, **options)

    def test_other_schema_kinds_are_not_implemented(self, fake):
        exe, _, _ = fake

        class Typed(TypedDict):
            n: int

        with pytest.raises(NotImplementedError):
            model(exe).with_structured_output(Typed)

    def test_missing_structured_output_is_an_error(self, fake):
        exe, respond, _ = fake
        respond(result="no json here")
        with pytest.raises(ClaudeCodeError):
            model(exe).with_structured_output(Decision).invoke("Decide")


@pytest.mark.unit
class TestFailures:
    def test_missing_executable(self, tmp_path):
        with pytest.raises(ClaudeCodeError, match="not found"):
            model(str(tmp_path / "nowhere")).invoke("Hi")

    def test_error_result(self, fake):
        exe, respond, _ = fake
        respond(exit_code=1, is_error=True, result="Usage limit reached")
        with pytest.raises(ClaudeCodeError, match="Usage limit reached"):
            model(exe).invoke("Hi")

    def test_error_flag_with_exit_zero(self, fake):
        exe, respond, _ = fake
        respond(is_error=True, result="Not signed in")
        with pytest.raises(ClaudeCodeError, match="Not signed in"):
            model(exe).invoke("Hi")

    def test_output_that_is_not_json(self, fake):
        exe, respond, _ = fake
        respond(exit_code=2, raw="segfault")
        with pytest.raises(ClaudeCodeError, match="exited 2"):
            model(exe).invoke("Hi")


@pytest.mark.unit
class TestWiring:
    def test_factory_and_config(self, fake, caplog):
        exe, _, _ = fake
        kwargs = build_llm_kwargs({"llm_provider": "claude_code", "anthropic_effort": "medium",
                                   "claude_code_path": exe, "temperature": 0.2})
        assert kwargs == {"effort": "medium", "claude_code_path": exe, "temperature": 0.2}

        client = create_llm_client("claude_code", "claude-opus-5-5", **kwargs)
        assert isinstance(client, ClaudeCodeClient)
        with caplog.at_level(logging.WARNING):
            llm = client.get_llm()
        assert (llm.model, llm.effort, llm.executable) == ("claude-opus-5-5", "medium", exe)
        assert "temperature" in caplog.text

    def test_claude_on_path_by_default(self):
        assert create_llm_client("claude_code", "claude-opus-5-5").get_llm().executable == "claude"

    def test_needs_no_api_key_and_knows_its_models(self):
        assert get_api_key_env("claude_code") is None
        assert validate_model("claude_code", "claude-opus-5-5")
        assert not validate_model("claude_code", "gpt-6-sol")


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code CLI not installed")
def test_real_cli_answers_and_calls_a_tool():
    """Runs on the signed-in subscription: pytest -m integration."""
    llm = ChatClaudeCode(model=os.environ.get("CLAUDE_CODE_SMOKE_MODEL", "claude-haiku-5-5"))
    assert llm.invoke("Reply with the single word OK.").content.strip()
    out = llm.bind_tools([get_price]).invoke("What did AAPL close at on 2026-08-07? Use the tool.")
    assert [c["name"] for c in out.tool_calls] == ["get_price"]
