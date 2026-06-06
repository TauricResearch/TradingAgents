"""LLM seam for the brain, with autonomous tool calling.

``StructuredLLM.generate`` optionally takes ``tools``: when present, the agent
runs a tool-calling loop — the model decides which tools to call, we execute
them (they extract + write through to the DB), feed the results back, and repeat
until the model is ready, then return the structured opinion. This is the canvas
behaviour ``<agent> -> Extractors set -> DB``, driven by the LLM itself.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, Sequence, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class StructuredLLM(Protocol):
    def generate(
        self, system_prompt: str, context: str, schema: type[T], *, tools: Sequence[Any] = ()
    ) -> T: ...


class ForkStructuredLLM:
    """Real structured LLM with tool calling, backed by the LangChain client.

    Defaults to the project's provider/model (OpenRouter + DeepSeek). The
    underlying client is a ChatOpenAI subclass, so it supports both
    ``bind_tools`` and ``with_structured_output``.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None, *, deep: bool = True, max_tool_iters: int = 4):
        from ..default_config import DEFAULT_CONFIG
        from ..llm_clients import create_llm_client

        self.config = config or DEFAULT_CONFIG
        self.max_tool_iters = max_tool_iters
        model = self.config["deep_think_llm"] if deep else self.config["quick_think_llm"]
        client = create_llm_client(self.config["llm_provider"], model, self.config.get("backend_url"))
        # the LangChain chat model (supports bind_tools + with_structured_output)
        self._model = client.get_llm() if hasattr(client, "get_llm") else client

    def generate(
        self, system_prompt: str, context: str, schema: type[T], *, tools: Sequence[Any] = ()
    ) -> T:
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        messages: list[Any] = [SystemMessage(content=system_prompt), HumanMessage(content=context)]

        if tools:
            bound = self._model.bind_tools(list(tools))
            tool_map = {t.name: t for t in tools}
            for _ in range(self.max_tool_iters):
                ai = bound.invoke(messages)
                messages.append(ai)
                calls = getattr(ai, "tool_calls", None) or []
                if not calls:
                    break
                for call in calls:
                    tool = tool_map.get(call["name"])
                    result = tool.invoke(call.get("args", {})) if tool else f"unknown tool {call['name']}"
                    messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

        return self._model.with_structured_output(schema).invoke(messages)
