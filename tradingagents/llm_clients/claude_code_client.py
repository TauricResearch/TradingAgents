"""Claude models on the person's own Claude subscription, through Claude Code.

Every model call runs the unmodified Claude Code CLI once in print mode
(``claude -p``), signed in with the person's own subscription. The CLI holds
the sign-in: this module never reads, stores or passes a credential. It is for
one person signing in to the unmodified binary on their own machine, never for
serving other people (https://code.claude.com/docs/en/legal-and-compliance),
and calls count toward the plan's usage limits. The CLI prefers an API key,
another endpoint or a cloud provider over the sign-in, so the variables that
select those are left out of its environment: settings made for another
provider must not turn subscription calls into billed ones.

The CLI runs isolated from the person's Claude Code setup (no settings,
CLAUDE.md, hooks, MCP servers, skills or built-in tools), with the system
messages as its system prompt, passed in a temporary file so its length is not
bound by the argument size limit, and the rest of the conversation on stdin. Tool
calls and structured output come back through ``--json-schema``, which the CLI
validates: bound tools become an envelope whose ``tool_calls`` items are one
schema branch per tool, so LangGraph's ToolNode still runs the tools in Python.

The CLI reports its run as a stream of JSON events. Assistant text written
outside the structured response does not reach the caller; it is kept in the
message's ``response_metadata`` and logged as a warning whose record carries
``claude_code_outside_text`` (its length), ``claude_code_final`` (whether the
response is a final answer rather than tool calls; None when the response was
unusable) and ``claude_code_content_length`` (the length of the response's
content, the JSON text for structured output), so a
caller can count such calls and spot a final answer that only points to text
it never received.

Limits: no token streaming, no async calls, no sampling or length settings,
and Claude Code adds the real current date to every call, so a run for a past
analysis date sees a conflicting "today".
"""

import json
import logging
import os
import subprocess
import tempfile
import uuid
from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

from .base_client import BaseLLMClient
from .validators import validate_model

logger = logging.getLogger(__name__)

# The CLI's own turns per call: the answer, plus the structured-output step and
# one correction of an invalid object. A bound on iterations, not on time.
_MAX_TURNS = "3"

# Keep the person's own Claude Code configuration out of every call.
_ISOLATION = (
    "--setting-sources", "",
    "--strict-mcp-config",
    "--tools", "",
    "--disable-slash-commands",
    "--no-session-persistence",
    "--exclude-dynamic-system-prompt-sections",
    "--max-turns", _MAX_TURNS,
)

# Variables that would route the CLI away from the sign-in: an API key, another
# endpoint, or a cloud provider (CLAUDE_CODE_USE_BEDROCK, _VERTEX, _FOUNDRY, ...).
_ROUTING_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
_ROUTING_ENV_PREFIX = "CLAUDE_CODE_USE_"


# Settings the CLI has no flag for.
_NOT_SENT = ("temperature", "max_tokens", "max_retries")

_TOOL_INSTRUCTIONS = (
    "The tools named in the tool_calls field of your structured response are run "
    "by the caller, not by you: you cannot call them directly. To use one, return "
    "it in tool_calls with its arguments and stop; its result comes back in a "
    "[tool result] turn. When you have your answer, give it in content with an "
    "empty tool_calls list. Only the structured response reaches the caller and "
    "anything written outside it is discarded, so content must hold your whole "
    "answer, never a pointer to text elsewhere."
)


class ClaudeCodeError(RuntimeError):
    """A Claude Code call failed or returned no usable answer."""


def _text(content: Any) -> str:
    """The text of message content, which may be a string or a list of blocks."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        else:
            raise ValueError(f"claude_code sends text only, not {block.get('type', block)!r} blocks")
    return "\n".join(parts)


def _render(messages: Sequence[BaseMessage]) -> str:
    """The non-system messages as labelled turns, in order."""
    turns = []
    for message in messages:
        text = _text(message.content)
        if isinstance(message, HumanMessage):
            turns.append(f"[user]\n{text}")
        elif isinstance(message, AIMessage):
            turn = f"[assistant]\n{text}"
            if message.tool_calls:
                calls = [{"id": c["id"], "name": c["name"], "args": c["args"]}
                         for c in message.tool_calls]
                turn += f"\n[assistant tool calls]\n{json.dumps(calls, ensure_ascii=False)}"
            turns.append(turn)
        elif isinstance(message, ToolMessage):
            turns.append(f"[tool result for {message.tool_call_id}]\n{text}")
        else:
            turns.append(f"[{message.type}]\n{text}")
    return "\n\n".join(turns)


def _tool_envelope(tools: Sequence[Any]) -> tuple[dict, tuple[str, ...]]:
    """The response schema for bound tools, and the tool names."""
    specs = [convert_to_openai_tool(tool)["function"] for tool in tools]
    branches = [
        {
            "type": "object",
            "description": spec.get("description", ""),
            "properties": {
                "name": {"const": spec["name"]},
                "args": spec.get("parameters") or {"type": "object", "properties": {}},
            },
            "required": ["name", "args"],
            "additionalProperties": False,
        }
        for spec in specs
    ]
    schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "tool_calls": {"type": "array", "items": {"oneOf": branches}},
        },
        "required": ["content", "tool_calls"],
        "additionalProperties": False,
    }
    return schema, tuple(spec["name"] for spec in specs)


def _usage(usage: dict | None) -> dict | None:
    """LangChain usage metadata from the CLI's token counts."""
    if not usage:
        return None
    cached = (usage.get("cache_read_input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0)
    inputs = (usage.get("input_tokens") or 0) + cached
    outputs = usage.get("output_tokens") or 0
    return {"input_tokens": inputs, "output_tokens": outputs, "total_tokens": inputs + outputs}


class ChatClaudeCode(BaseChatModel):
    """A LangChain chat model that runs each call through ``claude -p``."""

    model: str
    effort: str | None = None
    executable: str = "claude"
    # Set by bind_tools / with_structured_output on a copy of the model.
    tool_envelope: dict | None = None
    tool_names: tuple[str, ...] = ()
    response_schema: dict | None = None

    @property
    def _llm_type(self) -> str:
        return "claude-code"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model, "effort": self.effort,
                "tool_envelope": self.tool_envelope, "response_schema": self.response_schema}

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: Any = None,
                   parallel_tool_calls: bool | None = None, **kwargs: Any) -> "ChatClaudeCode":
        if tool_choice not in (None, "auto"):
            raise ValueError(f"claude_code does not support tool_choice={tool_choice!r}")
        if parallel_tool_calls is False:
            raise ValueError("claude_code cannot restrict a turn to one tool call")
        if kwargs:
            raise ValueError(f"claude_code does not support bind_tools options {sorted(kwargs)}")
        if self.response_schema is not None:
            raise ValueError("claude_code cannot bind tools to a structured-output model")
        if not tools:
            return self.model_copy(update={"tool_envelope": None, "tool_names": ()})
        schema, names = _tool_envelope(tools)
        return self.model_copy(update={"tool_envelope": schema, "tool_names": names})

    def with_structured_output(self, schema: Any, *, include_raw: bool = False, **kwargs: Any):
        if include_raw or kwargs:
            raise NotImplementedError("claude_code supports with_structured_output(schema) only")
        if self.tool_envelope is not None:
            raise NotImplementedError("claude_code cannot combine bound tools with structured output")
        is_model = isinstance(schema, type) and issubclass(schema, BaseModel)
        if not is_model and not (isinstance(schema, dict) and "properties" in schema):
            raise NotImplementedError("claude_code takes a Pydantic model or a JSON Schema object")
        json_schema = schema.model_json_schema() if is_model else schema
        bound = self.model_copy(update={"response_schema": json_schema})

        def parse(message: AIMessage):
            if is_model:
                return schema.model_validate_json(message.content)
            return json.loads(message.content)

        return bound | RunnableLambda(parse)

    def _argv(self, system_file: str) -> list[str]:
        argv = [self.executable, "-p", "--model", self.model]
        if self.effort:
            argv += ["--effort", self.effort]
        argv += [*_ISOLATION, "--system-prompt-file", system_file, "--output-format", "stream-json", "--verbose"]
        schema = self.response_schema or self.tool_envelope
        if schema is not None:
            argv += ["--json-schema", json.dumps(schema)]
        return argv

    def _run(self, system: str, transcript: str) -> tuple[dict, str]:
        """Run the CLI once; return its result event and the assistant's text, or raise ClaudeCodeError."""
        env = {k: v for k, v in os.environ.items()
               if k not in _ROUTING_ENV and not k.startswith(_ROUTING_ENV_PREFIX)}
        with tempfile.TemporaryDirectory(prefix="claude-code-") as directory:
            system_file = os.path.join(directory, "system-prompt.txt")
            with open(system_file, "w", encoding="utf-8") as f:
                f.write(system)
            try:
                done = subprocess.run(self._argv(system_file), input=transcript,
                                      capture_output=True, text=True, env=env)
            except FileNotFoundError as exc:
                raise ClaudeCodeError(
                    f"Claude Code CLI not found at {self.executable!r}; install it and sign in "
                    "with `claude`, or set claude_code_path") from exc
        try:
            events = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
        except json.JSONDecodeError:
            events = None
        if events is None or not all(isinstance(event, dict) for event in events):
            raise ClaudeCodeError(
                f"Claude Code exited {done.returncode} without a JSON event stream: "
                f"{(done.stderr or done.stdout).strip()[-2000:]}")
        results = [event for event in events if event.get("type") == "result"]
        if len(results) != 1:
            raise ClaudeCodeError(
                f"Claude Code exited {done.returncode} with {len(results)} results instead of one: "
                f"{(done.stderr or done.stdout).strip()[-2000:]}")
        (result,) = results
        if done.returncode != 0 or result.get("is_error"):
            raise ClaudeCodeError(
                f"Claude Code call failed (exit {done.returncode}): "
                f"{result.get('result') or done.stderr.strip()[-2000:]}")
        texts = []
        for event in events:
            message = event.get("message") if event.get("type") == "assistant" else None
            content = message.get("content") if isinstance(message, dict) else None
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text)
        return result, "\n\n".join(texts)

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        if stop:
            raise ValueError("claude_code does not support stop sequences")
        system = "\n\n".join(_text(m.content) for m in messages if isinstance(m, SystemMessage))
        if self.tool_envelope is not None and self.response_schema is None:
            system = f"{system}\n\n{_TOOL_INSTRUCTIONS}".strip()
        transcript = _render([m for m in messages if not isinstance(m, SystemMessage)])
        result, text = self._run(system, transcript)

        metadata = {
            "model_name": self.model,
            # Reported by the CLI; a subscription is not billed per call.
            "claude_code": {key: result.get(key) for key in ("total_cost_usd", "usage", "num_turns")},
        }
        if text and (self.response_schema is not None or self.tool_envelope is not None):
            # With a schema only the structured response is the answer; the CLI
            # runs no tools of its own, so all of this text is outside it.
            metadata["claude_code"]["outside_text"] = text
        message = None
        try:
            if self.response_schema is not None:
                message = AIMessage(content=json.dumps(self._structured(result)),
                                    response_metadata=metadata)
            elif self.tool_envelope is not None:
                message = self._tool_message(self._structured(result), metadata)
            else:
                message = AIMessage(content=result.get("result") or "", response_metadata=metadata)
        finally:
            if "outside_text" in metadata["claude_code"]:
                self._warn_outside_text(text, message)
        message.usage_metadata = _usage(result.get("usage"))
        return ChatResult(generations=[ChatGeneration(message=message)])

    @staticmethod
    def _warn_outside_text(text: str, message: AIMessage | None) -> None:
        """Log text that did not reach the caller, also when the response was unusable.

        Text beside tool calls is usually narration; beside a final answer it may
        be the answer itself, with content only pointing to it. Without a usable
        response (``message`` is None) whether it was final is unknown (None).
        """
        final = None if message is None else not message.tool_calls
        inside = 0 if message is None else len(message.content)
        kind = {None: "no usable response", True: "final answer", False: "tool calls"}[final]
        logger.warning("Claude Code wrote %d characters outside the structured response "
                       "(%s, %d characters inside); they do not reach the caller",
                       len(text), kind, inside,
                       extra={"claude_code_outside_text": len(text), "claude_code_final": final,
                              "claude_code_content_length": inside})

    @staticmethod
    def _structured(result: dict) -> dict:
        structured = result.get("structured_output")
        if not isinstance(structured, dict):
            raise ClaudeCodeError("Claude Code returned no structured output for the schema")
        return structured

    def _tool_message(self, envelope: dict, metadata: dict) -> AIMessage:
        tool_calls = []
        for call in envelope.get("tool_calls") or []:
            if call.get("name") not in self.tool_names:
                raise ClaudeCodeError(f"Claude Code called an unknown tool {call.get('name')!r}")
            tool_calls.append({"name": call["name"], "args": call.get("args") or {},
                               "id": f"call_{uuid.uuid4().hex}", "type": "tool_call"})
        return AIMessage(content=envelope.get("content") or "", tool_calls=tool_calls,
                         response_metadata=metadata)


class ClaudeCodeClient(BaseLLMClient):
    """Client for Claude models through the person's own Claude Code sign-in."""

    provider = "claude_code"

    def get_llm(self) -> Any:
        """Return a ChatClaudeCode for the configured model."""
        self.warn_if_unknown_model()
        for name in _NOT_SENT:
            if self.kwargs.get(name) is not None:
                logger.warning("Claude Code has no setting for %s; it is not sent.", name)
        return ChatClaudeCode(
            model=self.model,
            effort=self.kwargs.get("effort"),
            executable=self.kwargs.get("claude_code_path") or "claude",
            callbacks=self.kwargs.get("callbacks"),
        )

    def validate_model(self) -> bool:
        """Validate model for Claude Code."""
        return validate_model("claude_code", self.model)
