"""Claude Agent SDK client — routes inference through Claude Code's OAuth session.

Works with a Claude Max/Pro subscription; no ANTHROPIC_API_KEY required. Requires
the `claude-agent-sdk` package (bundles the Claude Code CLI).

Shape A: supports plain .invoke() for prompt-only call sites (researchers,
managers, trader, reflection, signal processing). Tool binding raises
NotImplementedError — tool-using analysts must use a different provider until
Shape B.
"""

import asyncio
from typing import Any, List, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
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


class ChatClaudeAgent(Runnable):
    """LangChain-compatible Runnable that routes inference through claude-agent-sdk.

    Authenticates via Claude Code's bundled CLI session. A Claude Max/Pro
    subscription satisfies auth; no API key required.
    """

    def __init__(self, model: str, **kwargs: Any) -> None:
        self.model = model
        self.kwargs = kwargs

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> AIMessage:
        system_prompt, prompt = _coerce_input(input)
        return asyncio.run(self._ainvoke(prompt, system_prompt))

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
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)

        return AIMessage(content="\n".join(text_parts))

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
