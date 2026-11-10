"""Run on the person's Claude Pro or Max plan, through Claude Code.

Anthropic gives other apps no sign-in of their own for a Claude plan: a plan is used
through Claude Code, which the Claude Agent SDK (the optional ``[claude]`` extra)
ships and drives. Claude Code keeps the sign-in, so nothing here reads or stores a
token. Each model call is one Claude Code run with no tools of its own and none of
the machine's Claude Code settings. An agent's tools are declared to it and never
run by it: Claude Code refuses each call and the run ends at its one turn, so a tool
call comes back to LangGraph as it does from any other provider. The conversation so far,
earlier tool calls and their results included, is sent written out as text.

A plan is for its subscriber's own use. To serve other people, use the ``anthropic``
provider with an API key.
"""

import asyncio
import contextlib
import json
import logging
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

from tradingagents.default_config import _TRADINGAGENTS_HOME

from .base_client import BaseLLMClient
from .validators import validate_model

logger = logging.getLogger(__name__)

LOGIN_HINT = "Not signed in to Claude; run `tradingagents login claude`."
SERVER = "tradingagents"                 # a declared tool reaches the model as mcp__tradingagents__<name>
TOOL_PREFIX = f"mcp__{SERVER}__"
TIMEOUT = 600                            # seconds one model call may take, as the Anthropic SDK allows
STRUCTURED_TURNS = 4                     # a typed answer is a tool call of Claude Code's own, then the turn's end

# What every Claude Code process started here runs with. An API key, a gateway token,
# another endpoint or a cloud provider set in the environment would take the run off
# the plan and bill it elsewhere, so each is blanked: Claude Code reads a blank one as unset.
PLAN_ENV = {
    "ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": "", "ANTHROPIC_BASE_URL": "",
    "CLAUDE_CODE_USE_BEDROCK": "", "CLAUDE_CODE_USE_VERTEX": "",
    "ENABLE_TOOL_SEARCH": "false",       # declared tools stay in the model's tool list
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",   # no second model call to name the session
    "CLAUDE_AGENT_SDK_CLIENT_APP": "tradingagents",
}

CONTINUE = (
    "The conversation so far is written out below, your earlier tool calls and their results "
    "included. Give your next reply to it, calling tools when you need more data."
)


class ClaudePlanError(RuntimeError):
    """The plan could not be used; the message says what to do."""


# --- Claude Code and its sign-in ----------------------------------------------------

def _sdk():
    try:
        import claude_agent_sdk
    except ImportError as exc:
        raise ImportError(
            "The claude provider requires the optional 'claude-agent-sdk' dependency. "
            'Install it with: pip install "tradingagents[claude]"'
        ) from exc
    return claude_agent_sdk


def _claude_code() -> str:
    """The Claude Code the Agent SDK ships and runs, else the one installed on this machine."""
    bundled = Path(_sdk().__file__).parent / "_bundled"
    for name in ("claude", "claude.exe"):
        if (bundled / name).is_file():
            return str(bundled / name)
    found = shutil.which("claude")
    if not found:
        raise ClaudePlanError('Claude Code was not found; reinstall it with: pip install "tradingagents[claude]"')
    return found


def _workdir() -> str:
    """An empty folder for Claude Code to run in, so no project's files or settings reach it."""
    folder = Path(_TRADINGAGENTS_HOME) / "claude-plan"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def _auth(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([_claude_code(), "auth", *args], env={**os.environ, **PLAN_ENV},
                          cwd=_workdir(), **kwargs)


def _require_plan_billing(key_source: str | None, provider: str | None = None) -> None:
    """Raise unless Claude Code would bill the plan: no API key, and Anthropic's own API."""
    if key_source not in (None, "none") or provider not in (None, "firstParty"):
        raise ClaudePlanError(
            f"Claude Code is set to use {key_source or provider}, not a Claude plan; "
            "run `tradingagents login claude`."
        )


def status() -> dict:
    """Claude Code's own account of its sign-in (``claude auth status``)."""
    try:
        data = json.loads(_auth("status", "--json", capture_output=True, text=True, timeout=60).stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ClaudePlanError(f"Could not ask Claude Code about its sign-in ({type(exc).__name__}).") from None
    return data if isinstance(data, dict) else {}


def require_plan() -> dict:
    """Claude Code's sign-in when it is a Claude plan's; raises with what to do otherwise."""
    found = status()
    if not found.get("loggedIn"):
        raise ClaudePlanError(LOGIN_HINT)
    _require_plan_billing(found.get("apiKeySource"), found.get("apiProvider"))
    return found


def signed_in_as() -> str | None:
    """The signed-in account's email, or None."""
    found = status()
    return (found.get("email") or "your Claude account") if found.get("loggedIn") else None


def sign_in() -> str:
    """Sign in to Claude Code with a Claude plan; returns the account's email.

    Claude Code runs the sign-in itself: it prints the address to open and reads the
    code the browser shows. The sign-in is Claude Code's, shared with a Claude Code
    already used on this machine."""
    try:
        done = _auth("login", "--claudeai")
    except OSError as exc:
        raise ClaudePlanError(f"Could not start Claude Code to sign in ({type(exc).__name__}).") from None
    if done.returncode != 0:
        raise ClaudePlanError("Signing in to Claude was not completed; run `tradingagents login claude` again.")
    return require_plan().get("email") or "your Claude account"


def sign_out() -> bool:
    """Sign Claude Code out on this machine; False when nobody was signed in."""
    if not status().get("loggedIn"):
        return False
    try:
        done = _auth("logout", capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClaudePlanError(f"Could not start Claude Code to sign out ({type(exc).__name__}).") from None
    if done.returncode != 0:
        raise ClaudePlanError("Claude Code could not sign out; run `claude auth logout`.")
    return True


# --- one model call -----------------------------------------------------------------

def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(part if isinstance(part, str) else part.get("text", "")
                     for part in content if isinstance(part, str) or part.get("type") == "text")


def _as_prompt(messages: list[BaseMessage]) -> tuple[str, str]:
    """(system prompt, prompt) for one Claude Code run.

    A run takes one prompt, not a history, so a conversation past its first message is
    written out in order with its tool calls and tool results."""
    system = "\n\n".join(_text(m) for m in messages if isinstance(m, SystemMessage))
    turns = [m for m in messages if not isinstance(m, SystemMessage)]
    if len(turns) == 1 and isinstance(turns[0], HumanMessage):
        return system, _text(turns[0])
    written = []
    for message in turns:
        if isinstance(message, ToolMessage):
            written.append(f'<tool_result id="{message.tool_call_id}" name="{message.name or "tool"}">\n'
                           f"{_text(message)}\n</tool_result>")
        elif isinstance(message, AIMessage):
            calls = [f'<tool_call id="{call["id"]}" name="{call["name"]}">'
                     f'{json.dumps(call["args"], default=str)}</tool_call>' for call in message.tool_calls]
            written.append("<assistant>\n" + "\n".join(filter(None, [_text(message), *calls])) + "\n</assistant>")
        else:
            written.append(f"<user>\n{_text(message)}\n</user>")
    return system, "\n\n".join([CONTINUE, *written])


def _declared(sdk, tools: list[dict]):
    """The agent's tools as Claude Code sees them: named and described, never run."""
    async def handed_back(args):
        return {"content": [{"type": "text", "text": "This call is run by TradingAgents, not here."}]}

    return sdk.create_sdk_mcp_server(SERVER, tools=[
        sdk.SdkMcpTool(name=spec["name"], description=spec.get("description") or "",
                       input_schema=spec.get("parameters") or {"type": "object", "properties": {}},
                       handler=handed_back)
        for spec in (tool["function"] for tool in tools)
    ])


def _usage(raw: dict | None) -> dict | None:
    if not raw:
        return None
    read, written = raw.get("cache_read_input_tokens") or 0, raw.get("cache_creation_input_tokens") or 0
    sent, received = (raw.get("input_tokens") or 0) + read + written, raw.get("output_tokens") or 0
    return {"input_tokens": sent, "output_tokens": received, "total_tokens": sent + received,
            "input_token_details": {"cache_read": read, "cache_creation": written}}


def _run(coroutine):
    """Run to completion from sync code, also when the caller is inside an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


class ChatClaudePlan(BaseChatModel):
    """A Claude model on the person's plan; each call is one Claude Code run."""

    model: str
    effort: str | None = None
    timeout: float = TIMEOUT

    @property
    def _llm_type(self) -> str:
        return "claude-plan"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model, "effort": self.effort}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        """Offer ``tools`` to the model. Claude Code has no ``tool_choice``, so the model
        decides whether to call one."""
        return self.bind(tools=[convert_to_openai_tool(tool) for tool in tools], **kwargs)

    def with_structured_output(self, schema, *, include_raw=False, **kwargs):
        """An answer typed as ``schema`` (a Pydantic model), through Claude Code's JSON-schema output."""
        if include_raw or not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise NotImplementedError("A Claude plan gives structured output for a Pydantic model only.")
        typed = self.bind(output_schema=schema.model_json_schema())
        return typed | RunnableLambda(lambda reply: schema.model_validate(reply.additional_kwargs["structured_output"]))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return _run(self._agenerate(messages, stop, None, **kwargs))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        ask = self._ask(messages, kwargs.get("tools") or [], kwargs.get("output_schema"))
        try:
            reply = await asyncio.wait_for(ask, self.timeout)
        except TimeoutError:
            raise ClaudePlanError(f"Claude did not answer within {self.timeout:g} seconds.") from None
        return ChatResult(generations=[ChatGeneration(message=reply)], llm_output={"model_name": self.model})

    def _options(self, sdk, system: str, tools: list[dict], schema: dict | None):
        return sdk.ClaudeAgentOptions(
            model=self.model,
            effort=self.effort,
            system_prompt=system,                       # in place of Claude Code's own
            tools=[],                                   # none of Claude Code's own tools
            mcp_servers={SERVER: _declared(sdk, tools)} if tools else {},
            strict_mcp_config=True,                     # nor the machine's MCP servers
            setting_sources=[],                         # nor its settings, hooks and CLAUDE.md
            permission_mode="dontAsk",                  # a declared tool is refused, not run
            max_turns=STRUCTURED_TURNS if schema else 1,
            output_format={"type": "json_schema", "schema": schema} if schema else None,
            cwd=_workdir(),
            env=PLAN_ENV,
            verbatim_prompts=True,                      # an @path or /command in a tool result stays text
            extra_args={"no-session-persistence": None},
        )

    async def _ask(self, messages: list[BaseMessage], tools: list[dict], schema: dict | None) -> AIMessage:
        sdk = _sdk()
        system, prompt = _as_prompt(messages)
        said, calls, usage, failure, result = [], [], None, None, None
        try:
            async with contextlib.aclosing(sdk.query(prompt=prompt or "Continue.",
                                                     options=self._options(sdk, system, tools, schema))) as stream:
                async for message in stream:
                    if isinstance(message, sdk.SystemMessage):
                        if message.subtype == "init":
                            _require_plan_billing(message.data.get("apiKeySource"))
                    elif isinstance(message, sdk.AssistantMessage):
                        if message.parent_tool_use_id:
                            continue
                        failure = message.error or failure
                        usage = message.usage or usage
                        for block in message.content:
                            if isinstance(block, sdk.TextBlock):
                                said.append(block.text)
                            elif isinstance(block, sdk.ToolUseBlock) and block.name.startswith(TOOL_PREFIX):
                                calls.append({"id": block.id, "name": block.name.removeprefix(TOOL_PREFIX),
                                              "args": block.input, "type": "tool_call"})
                    elif isinstance(message, sdk.ResultMessage):
                        result = message
                        break       # an error result is followed by the process's exit code, which says no more
        except sdk.ClaudeSDKError as exc:
            raise ClaudePlanError(f"Claude Code could not be run ({exc}).") from None

        if failure == "authentication_failed":
            raise ClaudePlanError(LOGIN_HINT)
        usage = _usage(result and result.usage or usage)
        if calls and not failure:
            # Claude Code refused each call and stopped at its one turn, reporting that as
            # an error; the calls are the answer, to be run by the graph's tool node.
            return AIMessage(content="\n".join(said), tool_calls=calls, usage_metadata=usage)
        if result is None or failure or result.is_error:
            why = (result and (result.result or "; ".join(result.errors or []) or result.subtype)
                   or " ".join(said) or failure or "Claude Code ended without an answer")
            raise ClaudePlanError(f"Claude could not answer on your plan ({why}).")
        if schema is None:
            return AIMessage(content="\n".join(said) or result.result or "", usage_metadata=usage)
        if result.structured_output is None:
            raise ClaudePlanError("Claude returned no structured answer.")
        return AIMessage(content=json.dumps(result.structured_output), usage_metadata=usage,
                         additional_kwargs={"structured_output": result.structured_output})


class ClaudePlanClient(BaseLLMClient):
    """Client for Claude models on the person's Claude plan."""

    provider = "claude"

    def get_llm(self) -> Any:
        """A ChatClaudePlan; raises now when the plan cannot be used, so a run stops
        before it starts rather than at its first model call."""
        from .anthropic_client import _supports_effort

        self.warn_if_unknown_model()
        _sdk()
        require_plan()
        if self.base_url:
            logger.warning("A Claude plan has no endpoint to set; %s is not used.", self.base_url)
        for name in ("temperature", "max_tokens"):
            if self.kwargs.get(name) is not None:
                logger.warning("A Claude plan does not accept %s; it is not sent.", name)
        extra = {"callbacks": self.kwargs["callbacks"]} if self.kwargs.get("callbacks") else {}
        return ChatClaudePlan(
            model=self.model,
            effort=self.kwargs.get("effort") if _supports_effort(self.model) else None,
            timeout=self.kwargs.get("timeout") or TIMEOUT,
            **extra,
        )

    def validate_model(self) -> bool:
        """Validate model for the Claude plan."""
        return validate_model("claude", self.model)
