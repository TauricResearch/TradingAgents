"""LangChain chat-model adapter for the Claude Agent SDK.

Bridges the Claude Code subscription (no ANTHROPIC_API_KEY required) into
the LangChain ``BaseChatModel`` surface that TradingAgents expects from
``tradingagents.llm_clients.factory.create_llm_client``.

Phase 1 scope: pure chat. ``bind_tools`` is intentionally NOT supported
— analyst nodes that call LangChain tools must stay on a key-based
provider until a LangChain-tool -> MCP bridge is added in phase 2.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)


_KNOWN_MODELS = {
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-opus-4-5",
}


def _flatten_messages(messages: List[BaseMessage]) -> tuple[Optional[str], str]:
    """Collapse a LangChain message list into ``(system_prompt, user_text)``.

    TradingAgents calls ``llm.invoke(single_string)`` which LangChain
    wraps as ``[HumanMessage(...)]``; this helper also handles the
    SystemMessage + HumanMessage shape that ChatPromptTemplate emits.
    Multi-turn fidelity is not a goal in phase 1.
    """
    system_parts: list[str] = []
    body_parts: list[str] = []
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if isinstance(msg, SystemMessage):
            system_parts.append(content)
        elif isinstance(msg, AIMessage):
            body_parts.append(f"[Previous assistant turn]\n{content}")
        else:
            body_parts.append(content)
    system = "\n\n".join(p for p in system_parts if p) or None
    body = "\n\n".join(p for p in body_parts if p)
    return system, body


def _run_async(coro):
    """Run an async coroutine from sync code, even inside a running loop.

    LangGraph's compiled graph defaults to sync ``.invoke`` (no running
    loop), but downstream callers may wrap us in one — escape to a
    worker thread when that happens so the SDK's async generator can
    own its own loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class ClaudeCodeChatModel(BaseChatModel):
    """LangChain chat model backed by the Claude Code subscription.

    Each call shells out to the local ``claude`` CLI via
    ``claude_agent_sdk.query``; the CLI's OAuth token authenticates
    against the user's Pro/Max plan, sidestepping ANTHROPIC_API_KEY.
    """

    model: str = "claude-sonnet-4-6"

    model_config = {"protected_namespaces": ()}

    @property
    def _llm_type(self) -> str:
        return "claude-code"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model, "provider": "claude-code"}

    async def _aquery(self, system_prompt: Optional[str], user_text: str) -> str:
        # Lazy import keeps simply loading this module cheap when the SDK
        # is absent (and lets the install-error point at the right place).
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                TextBlock,
                query,
            )
        except ImportError as e:
            raise ImportError(
                "claude-agent-sdk is required for the 'claude-code' provider. "
                "Install it with: pip install claude-agent-sdk"
            ) from e

        # Pure-chat isolation — strip everything that makes Claude Code
        # *Claude Code*. ``allowed_tools=[]`` alone is not enough: the
        # built-in tool registry and the user's skills are still loaded,
        # and the model autonomously tries to call them and leaks "live
        # data fetch blocked by permissions" prose into the output (we
        # caught this in mini_graph #1).
        options_kwargs: dict[str, Any] = {
            "model": self.model,
            "tools": [],               # disable every built-in tool
            "skills": [],              # hide host skill registry from the model
            "setting_sources": [],     # ignore user/project/local settings.json
            "strict_mcp_config": True, # ignore .mcp.json + plugin MCP servers
            # Caller-provided SystemMessage wins; otherwise pin a minimal
            # prompt so we don't inherit the Claude Code agent preset.
            "system_prompt": system_prompt
            or "You are a helpful assistant. Reply with the requested content directly.",
        }

        parts: list[str] = []
        last_result: Any = None
        try:
            async for msg in query(
                prompt=user_text,
                options=ClaudeAgentOptions(**options_kwargs),
            ):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    last_result = msg
        except Exception as exc:
            # ``is_error=True`` with ``subtype="success"`` is the documented
            # signal for an upstream API failure (429/500/529) — see the
            # ``api_error_status`` field on ResultMessage in SDK 0.2.87+.
            # When that fires after assistant text has already streamed,
            # treat the partial reply as success; only re-raise when we
            # have nothing usable.
            if parts:
                api_err = getattr(last_result, "api_error_status", None)
                logger.warning(
                    "claude-code post-stream finalization error suppressed "
                    "(%s, api_error_status=%s); using %d-char partial text.",
                    exc, api_err, sum(len(p) for p in parts),
                )
            else:
                raise

        if last_result is not None:
            self._log_usage(last_result)

        return "".join(parts).strip()

    def _log_usage(self, result_msg: Any) -> None:
        """Emit a structured per-call usage line so operators can size the
        subscription against real traffic. ``cache_create`` is the most
        important field — the agent-loop preamble dominates first-touch
        cost and shrinks dramatically on cache hits within the same window.
        """
        usage = getattr(result_msg, "usage", None) or {}
        api_err = getattr(result_msg, "api_error_status", None)
        extra = f" api_error_status={api_err}" if api_err else ""
        logger.info(
            "claude-code usage: model=%s duration=%.2fs api_duration=%.2fs "
            "turns=%s input=%s cache_create=%s cache_read=%s output=%s%s",
            self.model,
            (getattr(result_msg, "duration_ms", 0) or 0) / 1000,
            (getattr(result_msg, "duration_api_ms", 0) or 0) / 1000,
            getattr(result_msg, "num_turns", 0),
            usage.get("input_tokens", 0),
            usage.get("cache_creation_input_tokens", 0),
            usage.get("cache_read_input_tokens", 0),
            usage.get("output_tokens", 0),
            extra,
        )

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_prompt, user_text = _flatten_messages(messages)
        text = _run_async(self._aquery(system_prompt, user_text))
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        system_prompt, user_text = _flatten_messages(messages)
        text = await self._aquery(system_prompt, user_text)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    def bind_tools(self, tools, **kwargs):
        # Phase 1 deliberately refuses tool binding. Analyst nodes that
        # call yfinance/Reddit/etc. need a LangChain tool -> MCP server
        # bridge before they can ride the subscription.
        raise NotImplementedError(
            "ClaudeCodeChatModel does not support LangChain bind_tools() in "
            "phase 1. Route tool-using analysts through a key-based provider "
            "(anthropic / openai / deepseek / ...) until the MCP tool bridge lands."
        )

    def with_structured_output(self, schema, **kwargs):
        # Phase 1 has no JSON-schema/tool-calling support. The project's
        # ``bind_structured`` helper catches NotImplementedError and
        # transparently degrades the manager/trader/portfolio agents to
        # free-text generation — so raising here is the correct hook.
        raise NotImplementedError(
            "ClaudeCodeChatModel does not support with_structured_output() "
            "in phase 1; tradingagents will fall back to free-text generation."
        )


class ClaudeCodeClient(BaseLLMClient):
    """Factory wrapper exposed by ``create_llm_client('claude-code', ...)``."""

    provider = "claude-code"

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        if base_url is not None:
            raise ValueError(
                "The 'claude-code' provider has no base_url — endpoint and "
                "auth are owned by the local `claude` CLI's OAuth session."
            )
        super().__init__(model, base_url=None, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        return ClaudeCodeChatModel(model=self.model)

    def validate_model(self) -> bool:
        return self.model in _KNOWN_MODELS
