"""Claude Agent SDK client — routes inference through Claude Code's OAuth session.

Works with a Claude Max/Pro subscription; no ANTHROPIC_API_KEY required. Requires
the `claude-agent-sdk` package (bundles the Claude Code CLI).

Shape A: supports plain .invoke() for prompt-only call sites (researchers,
managers, trader, reflection, signal processing). Tool binding raises
NotImplementedError — tool-using analysts must use a different provider until
Shape B.
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable

from .base_client import BaseLLMClient


# Tools the built-in Claude Code preset would otherwise enable. We disable them
# explicitly so the SDK behaves as a pure LLM for Shape A.
_DISABLED_BUILTIN_TOOLS = [
    "Bash", "Read", "Write", "Edit", "MultiEdit",
    "Glob", "Grep", "WebFetch", "WebSearch",
    "Task", "TodoWrite", "NotebookEdit",
]


def _coerce_input(input: Any) -> Tuple[Optional[str], str]:
    """Collapse LangChain input into (system_prompt, user_prompt).

    The SDK takes one `prompt` string and a separate `system_prompt` option.
    We fold any SystemMessage into system_prompt and concatenate the rest.
    """
    if isinstance(input, str):
        return None, input

    if isinstance(input, PromptValue):
        input = input.to_messages()

    if not isinstance(input, list):
        return None, str(input)

    system_parts: List[str] = []
    user_parts: List[str] = []

    for msg in input:
        if isinstance(msg, SystemMessage):
            system_parts.append(str(msg.content))
            continue
        if isinstance(msg, BaseMessage):
            role = getattr(msg, "type", "human")
            user_parts.append(f"[{role}] {msg.content}")
            continue
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(str(content))
            else:
                user_parts.append(f"[{role}] {content}")
            continue
        user_parts.append(str(msg))

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    user_prompt = "\n\n".join(user_parts)
    return system_prompt, user_prompt


def extract_usage(sdk_usage: Any) -> Dict[str, int]:
    """Normalize the SDK's `usage` dict into LangChain's usage_metadata shape.

    Accepts either a plain dict (ResultMessage.usage) or None. Returns a dict
    with ``input_tokens``, ``output_tokens``, ``total_tokens`` keys.
    """
    if not isinstance(sdk_usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    # The SDK mirrors Anthropic usage shape. Be defensive across versions.
    input_tokens = (
        sdk_usage.get("input_tokens")
        or sdk_usage.get("prompt_tokens")
        or 0
    )
    output_tokens = (
        sdk_usage.get("output_tokens")
        or sdk_usage.get("completion_tokens")
        or 0
    )
    # Count cached input against the input budget too so the TUI reflects it.
    input_tokens += sdk_usage.get("cache_read_input_tokens", 0) or 0
    input_tokens += sdk_usage.get("cache_creation_input_tokens", 0) or 0
    total = input_tokens + output_tokens
    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total),
    }


def fire_llm_callbacks(
    callbacks: List[Any],
    message: AIMessage,
    prompt_preview: str,
) -> None:
    """Manually fire on_chat_model_start + on_llm_end on the given handlers.

    ChatClaudeAgent is a plain Runnable, so LangChain does not fire chat-model
    callbacks automatically. We invoke them ourselves so stats handlers
    (StatsCallbackHandler in the CLI, etc.) see LLM calls and token usage.
    """
    if not callbacks:
        return
    run_id = uuid4()
    serialized = {"name": "ChatClaudeAgent"}
    messages = [[{"role": "user", "content": prompt_preview}]]
    for cb in callbacks:
        if hasattr(cb, "on_chat_model_start"):
            try:
                cb.on_chat_model_start(serialized, messages, run_id=run_id)
            except TypeError:
                # Some handlers don't accept run_id; best-effort.
                try:
                    cb.on_chat_model_start(serialized, messages)
                except Exception:
                    pass
            except Exception:
                pass

    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    for cb in callbacks:
        if hasattr(cb, "on_llm_end"):
            try:
                cb.on_llm_end(result, run_id=run_id)
            except TypeError:
                try:
                    cb.on_llm_end(result)
                except Exception:
                    pass
            except Exception:
                pass


class ChatClaudeAgent(Runnable):
    """LangChain-compatible Runnable that routes inference through claude-agent-sdk.

    Authenticates via Claude Code's bundled CLI session. A Claude Max/Pro
    subscription satisfies auth; no API key required.
    """

    def __init__(self, model: str, **kwargs: Any) -> None:
        self.model = model
        # Pull callbacks out so we can fire them manually around each invoke —
        # Runnable doesn't trigger chat-model callbacks the way BaseChatModel does.
        self.callbacks: List[Any] = list(kwargs.pop("callbacks", None) or [])
        self.kwargs = kwargs

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> AIMessage:
        system_prompt, prompt = _coerce_input(input)
        message = asyncio.run(self._ainvoke(prompt, system_prompt))
        fire_llm_callbacks(self.callbacks, message, prompt)
        return message

    async def _ainvoke(self, prompt: str, system_prompt: Optional[str]) -> AIMessage:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )

        options_kwargs: dict = {
            "model": self.model,
            "allowed_tools": [],
            "disallowed_tools": list(_DISABLED_BUILTIN_TOOLS),
            "permission_mode": "default",
        }
        if system_prompt is not None:
            options_kwargs["system_prompt"] = system_prompt

        options = ClaudeAgentOptions(**options_kwargs)

        text_parts: List[str] = []
        final_usage: Dict[str, int] = {}
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
            # The ResultMessage at the end carries cumulative usage; prefer it.
            # Fall back to AssistantMessage.usage if ResultMessage omits it.
            sdk_usage = getattr(msg, "usage", None)
            if isinstance(sdk_usage, dict) and sdk_usage:
                final_usage = extract_usage(sdk_usage)

        return AIMessage(
            content="\n".join(text_parts),
            usage_metadata=final_usage or None,
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "claude_agent provider does not yet support bind_tools (Shape A). "
            "Configure a different provider (anthropic, openai, etc.) for the "
            "4 analysts that call bind_tools, or wait for Shape B which rewrites "
            "analysts to use the SDK's native tool loop."
        )


class ClaudeAgentClient(BaseLLMClient):
    """LLM client backed by claude-agent-sdk / Claude Code OAuth."""

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        return ChatClaudeAgent(model=self.model, **self.kwargs)

    def validate_model(self) -> bool:
        # Claude Code accepts multiple model aliases (opus/sonnet/haiku, full IDs,
        # short IDs); pass through and let the SDK reject unknown strings.
        return True
