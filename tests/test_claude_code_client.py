"""Tests for the claude_code provider, which runs each call through ``claude -p``.

A fake ``claude`` executable records its argv and stdin and prints a canned
stream of JSON events, so the tests pin the exact CLI contract without a subscription.
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
argv = sys.argv[1:]
system = open(argv[argv.index("--system-prompt-file") + 1]).read()
with open(os.environ["FAKE_CLAUDE_RECORD"], "a") as f:
    f.write(json.dumps({{"argv": argv, "system": system, "stdin": sys.stdin.read(),
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

    def respond(exit_code=0, raw=None, blocks=(), **result):
        """Answer with assistant events of ``blocks``, then one result event."""
        payload = {"type": "result", "is_error": False, "result": "", "num_turns": 1,
                   "total_cost_usd": 0.01, "usage": {"input_tokens": 3}, **result}
        events = [{"type": "system", "subtype": "init"}]
        events += [{"type": "assistant", "message": {"content": [block]}} for block in blocks]
        if "structured_output" in result:
            events.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "StructuredOutput", "input": result["structured_output"]}]}})
        events.append(payload)
        stream = "".join(json.dumps(event) + "\n" for event in events)
        response.write_text(raw if raw is not None else stream)
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
        system_file = flag(call["argv"], "--system-prompt-file")
        assert call["argv"] == [
            "-p", "--model", "claude-opus-5-5", "--effort", "medium", *ISOLATION,
            "--system-prompt-file", system_file, "--output-format", "stream-json", "--verbose"]
        assert call["system"] == "Be terse.\n\nUse English."
        assert call["stdin"] == "[user]\nHi"
        assert not os.path.exists(system_file)

    def test_a_system_prompt_beyond_the_argument_limit_is_passed(self, fake):
        exe, respond, calls = fake
        respond(result="ok")
        system = "ż" * (os.sysconf("SC_ARG_MAX") + 1)
        model(exe).invoke([SystemMessage(system), HumanMessage("Hi")])
        assert calls()[0]["system"] == system

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
        assert "tool_calls" in calls()[0]["system"]

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
        assert "tool_calls" not in calls()[0]["system"]

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

    @pytest.mark.parametrize("raw", ['{"type": "system"}\n{"type": "assist', '{"type": "system"}\nnull\n'])
    def test_a_stream_of_other_than_events(self, fake, raw):
        exe, respond, _ = fake
        respond(raw=raw)
        with pytest.raises(ClaudeCodeError, match="event stream"):
            model(exe).invoke("Hi")

    @pytest.mark.parametrize("count", [0, 2])
    def test_exactly_one_result(self, fake, count):
        exe, respond, _ = fake
        result = json.dumps({"type": "result", "is_error": False, "result": "ok"}) + "\n"
        respond(raw='{"type": "system"}\n' + result * count)
        with pytest.raises(ClaudeCodeError, match=f"{count} results instead of one: .*system"):
            model(exe).invoke("Hi")


REPORT = "A long report on the company, written as plain text."
OUTSIDE = [{"type": "thinking", "thinking": "plan"}, {"type": "text", "text": REPORT},
           {"type": "text", "text": "  "}]


@pytest.mark.unit
class TestOutsideText:
    def test_tool_envelope_keeps_its_content_and_records_the_text(self, fake, caplog):
        exe, respond, _ = fake
        respond(blocks=OUTSIDE, structured_output={"content": "See the report above.", "tool_calls": []})
        with caplog.at_level(logging.WARNING):
            out = model(exe).bind_tools([get_price]).invoke("Report")

        assert out.content == "See the report above."
        assert out.response_metadata["claude_code"]["outside_text"] == REPORT
        (record,) = [r for r in caplog.records if hasattr(r, "claude_code_outside_text")]
        assert record.claude_code_outside_text == len(REPORT)
        assert record.claude_code_final is True
        assert record.claude_code_content_length == len("See the report above.")

    def test_text_beside_tool_calls_is_not_a_final_answer(self, fake, caplog):
        exe, respond, _ = fake
        respond(blocks=[{"type": "text", "text": "Let me fetch the price."}],
                structured_output={"content": "", "tool_calls": [
                    {"name": "get_price", "args": {"ticker": "AAPL", "date": "2026-08-07"}}]})
        with caplog.at_level(logging.WARNING):
            out = model(exe).bind_tools([get_price]).invoke("Price?")
        assert [c["name"] for c in out.tool_calls] == ["get_price"]
        (record,) = [r for r in caplog.records if hasattr(r, "claude_code_outside_text")]
        assert (record.claude_code_final, record.claude_code_content_length) == (False, 0)

    def test_structured_output_records_the_text(self, fake, caplog):
        exe, respond, _ = fake
        respond(blocks=OUTSIDE, structured_output={"rating": "Buy", "reason": "cheap"})
        with caplog.at_level(logging.WARNING):
            out = model(exe).with_structured_output(Decision).first.invoke("Decide")
        assert out.response_metadata["claude_code"]["outside_text"] == REPORT
        (record,) = [r for r in caplog.records if hasattr(r, "claude_code_outside_text")]
        assert record.claude_code_final is True
        assert record.claude_code_content_length == len(out.content)

    def test_text_beside_an_unusable_response_is_still_logged(self, fake, caplog):
        exe, respond, _ = fake
        respond(blocks=OUTSIDE, result="no structured output")
        with caplog.at_level(logging.WARNING), pytest.raises(ClaudeCodeError):
            model(exe).bind_tools([get_price]).invoke("Report")
        (record,) = [r for r in caplog.records if hasattr(r, "claude_code_outside_text")]
        assert (record.claude_code_outside_text, record.claude_code_final) == (len(REPORT), None)

    def test_texts_of_several_turns_are_joined(self, fake):
        exe, respond, _ = fake
        respond(blocks=[{"type": "text", "text": "one"}, {"type": "text", "text": "two"}],
                structured_output={"content": "", "tool_calls": []})
        out = model(exe).bind_tools([get_price]).invoke("Hi")
        assert out.response_metadata["claude_code"]["outside_text"] == "one\n\ntwo"

    @pytest.mark.parametrize("blocks", [[], [{"type": "thinking", "thinking": "x"}, {"type": "text", "text": "\n"}]])
    def test_nothing_is_recorded_without_outside_text(self, fake, caplog, blocks):
        exe, respond, _ = fake
        respond(blocks=blocks, structured_output={"content": "done", "tool_calls": []})
        with caplog.at_level(logging.WARNING):
            out = model(exe).bind_tools([get_price]).invoke("Hi")
        assert "outside_text" not in out.response_metadata["claude_code"]
        assert not [r for r in caplog.records if hasattr(r, "claude_code_outside_text")]

    def test_a_plain_answer_is_its_text(self, fake, caplog):
        exe, respond, _ = fake
        respond(blocks=[{"type": "text", "text": "Hello"}], result="Hello")
        with caplog.at_level(logging.WARNING):
            out = model(exe).invoke("Hi")
        assert out.content == "Hello" and "outside_text" not in out.response_metadata["claude_code"]
        assert not [r for r in caplog.records if hasattr(r, "claude_code_outside_text")]

    def test_odd_assistant_events_are_skipped(self, fake):
        exe, respond, _ = fake
        stream = [{"type": "assistant", "message": "text"}, {"type": "assistant", "message": {"content": "x"}},
                  {"type": "assistant", "message": {"content": [{"type": "text", "text": 3}]}},
                  {"type": "result", "is_error": False, "structured_output": {"content": "ok", "tool_calls": []}}]
        respond(raw="".join(json.dumps(event) + "\n" for event in stream))
        out = model(exe).bind_tools([get_price]).invoke("Hi")
        assert out.content == "ok" and "outside_text" not in out.response_metadata["claude_code"]


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
    answer = llm.invoke([SystemMessage("Reply with only the word PINEAPPLE."), HumanMessage("Hi")])
    assert "PINEAPPLE" in answer.content
    out = llm.bind_tools([get_price]).invoke("What did AAPL close at on 2026-08-07? Use the tool.")
    # About one run in ten Haiku answers without the tool; show what it said.
    assert [c["name"] for c in out.tool_calls] == ["get_price"], (
        out.content, out.response_metadata["claude_code"].get("outside_text"))
