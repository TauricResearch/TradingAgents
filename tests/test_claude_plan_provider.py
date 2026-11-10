"""The claude provider runs on the person's Claude plan, through Claude Code.

Each model call is one Claude Code run that bills the plan and nothing else, with
none of Claude Code's own tools or the machine's settings; an agent's tool calls
come back to be run here, and the CLI offers the plan under "Subscription" and
checks Claude Code's sign-in before a run. The Agent SDK is optional, so these
tests stand in for it.
"""

import json
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest import mock

import pytest
import typer
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from pydantic import BaseModel
from typer.testing import CliRunner

import cli.main as cli_main
import cli.prompts as prompts
from tradingagents import default_config
from tradingagents.agents.analysts.turn import take_turn
from tradingagents.agents.structured import invoke_structured
from tradingagents.llm_clients import claude_plan, factory
from tradingagents.llm_clients.openai_client import SIGNED_IN_PROVIDERS

# --- a stand-in for the Agent SDK -------------------------------------------------

@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class SystemMessage_:
    subtype: str
    data: dict


@dataclass
class AssistantMessage:
    content: list
    error: str | None = None
    usage: dict | None = None
    parent_tool_use_id: str | None = None


@dataclass
class UserMessage:
    content: str = "refused"


@dataclass
class ResultMessage:
    result: str | None = None
    is_error: bool = False
    subtype: str = "success"
    usage: dict | None = None
    structured_output: object = None
    errors: list = field(default_factory=list)


INIT = SystemMessage_("init", {"apiKeySource": "none"})
USAGE = {"input_tokens": 10, "cache_read_input_tokens": 90, "cache_creation_input_tokens": 0, "output_tokens": 5}


class FakeSDK:
    """Plays back ``script`` for each run and records what the run was started with."""

    TextBlock, ToolUseBlock, UserMessage, ResultMessage = TextBlock, ToolUseBlock, UserMessage, ResultMessage
    SystemMessage, AssistantMessage = SystemMessage_, AssistantMessage
    ClaudeSDKError = type("ClaudeSDKError", (Exception,), {})
    ClaudeAgentOptions = SdkMcpTool = staticmethod(lambda **kwargs: SimpleNamespace(**kwargs))

    def __init__(self, *script):
        self.script, self.runs, self.read = list(script), [], 0

    @staticmethod
    def create_sdk_mcp_server(name, tools):
        return SimpleNamespace(name=name, tools=tools)

    async def query(self, prompt, options):
        self.runs.append(SimpleNamespace(prompt=prompt, options=options))
        for message in self.script:
            self.read += 1
            if isinstance(message, Exception):
                raise message
            yield message


@pytest.fixture
def plan(monkeypatch, tmp_path):
    """A signed-in plan and a Claude Code that plays back the given messages."""
    monkeypatch.setattr(claude_plan, "_TRADINGAGENTS_HOME", str(tmp_path))
    monkeypatch.setattr(claude_plan, "status", lambda: {"loggedIn": True, "email": "a@example.com",
                                                        "apiProvider": "firstParty"})

    def play(*script):
        sdk = FakeSDK(*script)
        monkeypatch.setattr(claude_plan, "_sdk", lambda: sdk)
        return sdk

    return play


def _llm(model="claude-sonnet-5", **config):
    config = {**default_config.DEFAULT_CONFIG, "llm_provider": "claude", **config}
    return factory.create_llm_client("claude", model, **factory.build_llm_kwargs(config)).get_llm()


@tool
def get_stock_data(symbol: str, start_date: str) -> str:
    """Prices for a symbol from a start date."""
    return "prices"


# --- one model call ---------------------------------------------------------------

@pytest.mark.unit
def test_an_answer_comes_from_one_bare_claude_code_run_on_the_plan(plan, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-be-used")
    sdk = plan(INIT, AssistantMessage([TextBlock("Hold.")], usage=USAGE), ResultMessage("Hold.", usage=USAGE))

    reply = _llm(anthropic_effort="high").invoke([SystemMessage("Be brief."), HumanMessage("NVDA?")])

    assert isinstance(reply, AIMessage) and reply.content == "Hold." and not reply.tool_calls
    assert reply.usage_metadata["input_tokens"] == 100 and reply.usage_metadata["output_tokens"] == 5
    run = sdk.runs[0]
    assert (run.prompt, run.options.system_prompt) == ("NVDA?", "Be brief.")
    assert (run.options.model, run.options.effort, run.options.max_turns) == ("claude-sonnet-5", "high", 1)
    # None of Claude Code's own tools, MCP servers or settings, and no key or other endpoint to bill.
    assert run.options.tools == [] and run.options.mcp_servers == {} and run.options.setting_sources == []
    assert run.options.strict_mcp_config and run.options.permission_mode == "dontAsk"
    assert {run.options.env[name] for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                                               "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")} == {""}


@pytest.mark.unit
def test_tool_calls_come_back_to_be_run_here_not_by_claude_code(plan):
    sdk = plan(
        INIT,
        AssistantMessage([TextBlock("Checking prices.")], usage=USAGE),
        AssistantMessage([ToolUseBlock("toolu_1", "mcp__tradingagents__get_stock_data",
                                       {"symbol": "NVDA", "start_date": "2026-01-01"})], usage=USAGE),
        UserMessage(),   # Claude Code refuses each call as it comes, then stops at its one turn
        AssistantMessage([ToolUseBlock("toolu_2", "mcp__tradingagents__get_stock_data",
                                       {"symbol": "AMD", "start_date": "2026-01-01"})], usage=USAGE),
        UserMessage(),
        ResultMessage("Reached maximum number of turns (1)", is_error=True, subtype="error_max_turns", usage=USAGE),
        FakeSDK.ClaudeSDKError("exit code 1"),
    )

    reply = _llm().bind_tools([get_stock_data]).invoke("Compare NVDA and AMD.")

    assert reply.content == "Checking prices."
    assert [(c["id"], c["name"], c["args"]["symbol"]) for c in reply.tool_calls] == [
        ("toolu_1", "get_stock_data", "NVDA"), ("toolu_2", "get_stock_data", "AMD")]
    assert reply.usage_metadata["total_tokens"] == 105
    assert sdk.read == 7   # the error result ends the run; the exit code after it is not read
    declared = sdk.runs[0].options.mcp_servers["tradingagents"].tools[0]
    assert (declared.name, declared.description) == ("get_stock_data", "Prices for a symbol from a start date.")
    assert declared.input_schema["required"] == ["symbol", "start_date"]


@pytest.mark.unit
def test_an_analyst_s_tool_round_reaches_claude_written_out(plan):
    sdk = plan(INIT, AssistantMessage([TextBlock("NVDA closed at 120.")]), ResultMessage("NVDA closed at 120."))
    prompt = ChatPromptTemplate.from_messages([("system", "You are the market analyst. Tools: {tool_names}"),
                                               MessagesPlaceholder("messages")]).partial(tool_names="get_stock_data")
    history = [
        HumanMessage("Analyze NVDA."),
        AIMessage("", tool_calls=[{"id": "toolu_1", "name": "get_stock_data", "args": {"symbol": "NVDA"}}]),
        ToolMessage("close=120", tool_call_id="toolu_1", name="get_stock_data"),
    ]

    result, report = take_turn(prompt, _llm(), [get_stock_data], history)

    assert report == "NVDA closed at 120." and not result.tool_calls
    run = sdk.runs[0]
    assert run.options.system_prompt == "You are the market analyst. Tools: get_stock_data"
    assert run.prompt.startswith(claude_plan.CONTINUE)
    assert "<user>\nAnalyze NVDA.\n</user>" in run.prompt
    assert '<tool_call id="toolu_1" name="get_stock_data">{"symbol": "NVDA"}</tool_call>' in run.prompt
    assert '<tool_result id="toolu_1" name="get_stock_data">\nclose=120\n</tool_result>' in run.prompt


class Decision(BaseModel):
    rating: str
    reason: str


@pytest.mark.unit
def test_a_typed_answer_uses_claude_code_s_json_schema_output(plan):
    answer = {"rating": "Buy", "reason": "Momentum."}
    sdk = plan(INIT, AssistantMessage([ToolUseBlock("toolu_s", "StructuredOutput", answer)]), UserMessage(),
               ResultMessage(json.dumps(answer), structured_output=answer, usage=USAGE))

    decision = _llm().with_structured_output(Decision).invoke("Decide on NVDA.")

    assert decision == Decision(rating="Buy", reason="Momentum.")
    options = sdk.runs[0].options
    assert options.output_format == {"type": "json_schema", "schema": Decision.model_json_schema()}
    assert options.max_turns > 1 and options.mcp_servers == {}


@pytest.mark.unit
def test_a_missing_typed_answer_falls_back_to_free_text(plan):
    plan(INIT, AssistantMessage([TextBlock("Buy, on momentum.")]), ResultMessage("Buy, on momentum."))

    assert invoke_structured(_llm().with_structured_output(Decision), "Decide on NVDA.", "Trader") is None


# --- what stops a run -------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("source", ["ANTHROPIC_API_KEY", "apiKeyHelper", "/login managed key"])
def test_a_run_that_would_bill_an_api_key_stops_before_the_answer(plan, source):
    sdk = plan(SystemMessage_("init", {"apiKeySource": source}), AssistantMessage([TextBlock("Hold.")]),
               ResultMessage("Hold."))

    with pytest.raises(claude_plan.ClaudePlanError, match="not a Claude plan"):
        _llm().invoke("NVDA?")
    assert sdk.read == 1


@pytest.mark.unit
def test_a_lapsed_sign_in_says_how_to_sign_in(plan):
    plan(INIT, AssistantMessage([TextBlock("Not logged in · Please run /login")], error="authentication_failed"),
         ResultMessage("Not logged in · Please run /login", is_error=True))

    with pytest.raises(claude_plan.ClaudePlanError, match="tradingagents login claude"):
        _llm().invoke("NVDA?")


@pytest.mark.unit
def test_a_refusal_from_the_plan_is_reported_in_claude_s_words(plan):
    plan(INIT, AssistantMessage([TextBlock("You've hit your usage limit")], error="rate_limit"),
         ResultMessage("You've hit your usage limit · resets 3pm", is_error=True))

    with pytest.raises(claude_plan.ClaudePlanError, match="usage limit · resets 3pm"):
        _llm().invoke("NVDA?")


@pytest.mark.unit
def test_a_claude_code_that_cannot_run_is_reported(plan):
    plan(FakeSDK.ClaudeSDKError("Claude Code not found"))

    with pytest.raises(claude_plan.ClaudePlanError, match="Claude Code not found"):
        _llm().invoke("NVDA?")


@pytest.mark.unit
@pytest.mark.parametrize("found, message", [
    ({"loggedIn": False}, "tradingagents login claude"),
    ({"loggedIn": True, "apiKeySource": "ANTHROPIC_API_KEY"}, "ANTHROPIC_API_KEY, not a Claude plan"),
    ({"loggedIn": True, "apiProvider": "bedrock"}, "bedrock, not a Claude plan"),
])
def test_a_run_without_a_plan_sign_in_stops_before_it_starts(plan, monkeypatch, found, message):
    plan()
    monkeypatch.setattr(claude_plan, "status", lambda: found)

    with pytest.raises(claude_plan.ClaudePlanError, match=message):
        _llm()


@pytest.mark.unit
def test_without_the_agent_sdk_the_extra_to_install_is_named(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "claude_agent_sdk", None)

    with pytest.raises(ImportError, match=r"tradingagents\[claude\]"):
        _llm()


@pytest.mark.unit
def test_settings_a_plan_does_not_take_are_dropped(plan, caplog):
    plan()
    with caplog.at_level(logging.WARNING):
        llm = _llm("claude-haiku-4-5", anthropic_effort="high", temperature=0.2, max_tokens=500)

    assert llm.effort is None   # Haiku takes no effort setting
    assert "does not accept temperature" in caplog.text and "does not accept max_tokens" in caplog.text


@pytest.mark.unit
def test_a_claude_tier_beside_an_anthropic_tier_keeps_the_key_for_anthropic(plan):
    plan()
    config = {**default_config.DEFAULT_CONFIG, "llm_provider": "anthropic", "quick_think_provider": "claude",
              "quick_think_llm": "claude-sonnet-5", "deep_think_llm": "claude-opus-5-5", "anthropic_effort": "low"}

    quick = factory.create_tier_client(config, "quick").get_llm()
    deep = factory.create_tier_client(config, "deep").get_llm()

    assert isinstance(quick, claude_plan.ChatClaudePlan) and quick.effort == "low"
    assert not isinstance(deep, claude_plan.ChatClaudePlan)
    assert deep.anthropic_api_key.get_secret_value() == "placeholder"


# --- Claude Code's sign-in --------------------------------------------------------

@pytest.mark.unit
def test_claude_code_is_asked_about_its_sign_in_without_a_key_in_reach(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-be-used")
    monkeypatch.setattr(claude_plan, "_TRADINGAGENTS_HOME", str(tmp_path))
    monkeypatch.setattr(claude_plan, "_claude_code", lambda: "/sdk/claude")
    ran = []

    def run(argv, **kwargs):
        ran.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"loggedIn": true, "email": "a@example.com"}')

    monkeypatch.setattr(claude_plan.subprocess, "run", run)

    assert claude_plan.sign_in() == "a@example.com"
    assert [argv for argv, _ in ran] == [["/sdk/claude", "auth", "login", "--claudeai"],
                                         ["/sdk/claude", "auth", "status", "--json"]]
    assert all(kwargs["env"]["ANTHROPIC_API_KEY"] == "" for _, kwargs in ran)
    assert all(kwargs["cwd"] == str(tmp_path / "claude-plan") for _, kwargs in ran)


# --- the CLI ----------------------------------------------------------------------

@pytest.mark.unit
def test_the_plans_are_chatgpt_s_sign_in_and_claude_code_s():
    assert (*SIGNED_IN_PROVIDERS, "claude") == factory.PLAN_PROVIDERS


@pytest.mark.unit
def test_claude_is_offered_under_subscription():
    shown = []

    def select(message, choices, **kwargs):
        shown.append([c.title for c in choices])
        pick = (lambda: next(c.value for c in choices if c.title.startswith("Subscription"))) if len(shown) == 1 \
            else (lambda: next(c.value for c in choices if c.title.startswith("Claude")))
        return SimpleNamespace(ask=pick)

    with mock.patch("cli.prompts.questionary.select", select):
        provider, url = prompts.select_llm_provider()

    assert not any(title.startswith("Claude") for title in shown[0])
    assert shown[1] == ["ChatGPT (Plus or Pro plan)", "Claude (Pro or Max plan)"]
    assert (provider, url) == ("claude", None)


@pytest.mark.unit
def test_a_signed_in_claude_plan_is_named_before_the_run(plan, capsys):
    plan()
    prompts.ensure_signed_in("claude")
    assert "Using your Claude plan: a@example.com" in capsys.readouterr().out


@pytest.mark.unit
def test_an_unattended_run_without_the_claude_sign_in_says_how_to_sign_in(plan, monkeypatch, capsys):
    plan()
    monkeypatch.setattr(claude_plan, "status", lambda: {"loggedIn": False})
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))
    with pytest.raises(typer.Exit):
        prompts.ensure_signed_in("claude")
    assert "tradingagents login claude" in " ".join(capsys.readouterr().out.split())


@pytest.mark.unit
def test_an_interactive_run_signs_in_to_claude_through_the_login_command(plan, monkeypatch, capsys):
    plan()
    found = iter([{"loggedIn": False}, {"loggedIn": True, "email": "a@example.com"}])
    monkeypatch.setattr(claude_plan, "status", lambda: next(found))
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    ran = []
    monkeypatch.setattr(prompts.subprocess, "run", lambda argv: ran.append(argv) or SimpleNamespace(returncode=0))
    prompts.ensure_signed_in("claude")
    assert ran[0][1:] == ["-P", "-m", "cli.main", "login", "claude"]
    assert "Using your Claude plan: a@example.com" in capsys.readouterr().out


@pytest.mark.unit
def test_login_and_logout_claude_go_through_claude_code(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(claude_plan, "sign_in", lambda: "a@example.com")
    monkeypatch.setattr(claude_plan, "sign_out", lambda: True)
    signed_in = runner.invoke(cli_main.app, ["login", "claude"])
    assert signed_in.exit_code == 0 and "Signed in to Claude as a@example.com" in signed_in.output
    signed_out = runner.invoke(cli_main.app, ["logout", "claude"])
    assert signed_out.exit_code == 0 and "Signed out of Claude Code on this machine" in signed_out.output

    monkeypatch.setattr(claude_plan, "sign_out", lambda: False)
    assert "Not signed in to Claude" in runner.invoke(cli_main.app, ["logout", "claude"]).output

    def refuse():
        raise claude_plan.ClaudePlanError("Signing in to Claude was not completed")

    monkeypatch.setattr(claude_plan, "sign_in", refuse)
    failed = runner.invoke(cli_main.app, ["login", "claude"])
    assert failed.exit_code == 1 and "was not completed" in failed.output
