"""LangChain chat model for ChatGPT/Codex OAuth subscription access."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Optional

import requests
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
from pydantic import BaseModel as PydanticBaseModel

from .base_client import BaseLLMClient
from .codex_oauth import CodexOAuthStore, get_valid_tokens, refresh_tokens


CODEX_BASE_URL = "https://chatgpt.com/backend-api"
CODEX_RESPONSES_PATH = "/codex/responses"
CODEX_MODELS_PATH = "/codex/models"
CODEX_MODELS_CLIENT_VERSION = "1.0.0"


class CodexOAuthChatModel(BaseChatModel):
    model_name: str = Field(default="gpt-5.4-mini")
    base_url: str = Field(default=CODEX_BASE_URL)
    timeout: float = Field(default=300.0)
    reasoning_effort: str = Field(default="medium")
    text_verbosity: str = Field(default="medium")
    bound_tools: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "codex-oauth"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "reasoning_effort": self.reasoning_effort,
            "text_verbosity": self.text_verbosity,
        }

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"bound_tools": list(tools)})

    def with_structured_output(self, schema, *, method=None, **kwargs):
        if not isinstance(schema, type) or not issubclass(schema, PydanticBaseModel):
            raise NotImplementedError("Codex OAuth structured output currently requires a Pydantic schema")
        return CodexOAuthStructuredModel(llm=self, schema=schema)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._build_payload(messages, stop=stop)
        response_payload = self._post(payload)
        message = self._parse_response(response_payload)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _build_payload(self, messages: list[BaseMessage], stop: Optional[list[str]] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": self._messages_to_input(messages),
            "instructions": self._messages_to_instructions(messages),
            "store": False,
            "stream": True,
            "reasoning": {"effort": self.reasoning_effort, "summary": "auto"},
            "text": {"verbosity": self.text_verbosity},
            "include": ["reasoning.encrypted_content"],
        }
        if stop:
            payload["stop"] = stop
        if self.bound_tools:
            payload["tools"] = [self._tool_to_response_tool(tool) for tool in self.bound_tools]
            payload["tool_choice"] = "auto"
        return payload

    def _messages_to_instructions(self, messages: list[BaseMessage]) -> str:
        instructions = [
            self._content_to_text(message.content)
            for message in messages
            if isinstance(message, SystemMessage)
        ]
        if instructions:
            return "\n\n".join(instructions)
        return "You are the LLM backend for TradingAgents. Follow the user's request exactly."

    def _messages_to_input(self, messages: list[BaseMessage]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, ToolMessage):
                items.append({
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": self._content_to_text(message.content),
                })
                continue

            role = "user"
            if isinstance(message, SystemMessage):
                continue
            elif isinstance(message, AIMessage):
                role = "assistant"
            elif isinstance(message, HumanMessage):
                role = "user"

            text = self._content_to_text(message.content)
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                for tool_call in tool_calls:
                    items.append({
                        "type": "function_call",
                        "call_id": tool_call.get("id"),
                        "name": tool_call.get("name"),
                        "arguments": json.dumps(tool_call.get("args", {})),
                    })
            if text:
                items.append({
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                })
        return items

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    def _tool_to_response_tool(self, tool: Any) -> dict[str, Any]:
        args_schema = getattr(tool, "args_schema", None)
        if args_schema is not None and hasattr(args_schema, "model_json_schema"):
            parameters = args_schema.model_json_schema()
        else:
            parameters = getattr(tool, "args", {})
        return {
            "type": "function",
            "name": getattr(tool, "name", tool.__class__.__name__),
            "description": getattr(tool, "description", "") or "",
            "parameters": parameters or {"type": "object", "properties": {}},
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        tokens = get_valid_tokens(CodexOAuthStore())
        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
            "User-Agent": "codex_cli_rs/0.0.1 (TradingAgents)",
            "originator": "codex_cli_rs",
            "OpenAI-Beta": "responses=experimental",
        }
        if tokens.account_id:
            headers["ChatGPT-Account-ID"] = tokens.account_id

        response = requests.post(
            f"{self.base_url.rstrip('/')}{CODEX_RESPONSES_PATH}",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        if response.status_code == 401:
            store = CodexOAuthStore()
            refreshed = refresh_tokens(store.load().refresh_token)
            store.save(refreshed)
            headers["Authorization"] = f"Bearer {refreshed.access_token}"
            if refreshed.account_id:
                headers["ChatGPT-Account-ID"] = refreshed.account_id
            response = requests.post(
                f"{self.base_url.rstrip('/')}{CODEX_RESPONSES_PATH}",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Codex OAuth request failed: HTTP {response.status_code} {response.text}")
        return self._decode_response(response)

    def _decode_response(self, response: requests.Response) -> dict[str, Any]:
        content_type = response.headers.get("Content-Type", "")
        body = response.text
        looks_like_sse = body.lstrip().startswith(("event:", "data:"))
        if "text/event-stream" not in content_type and not looks_like_sse:
            return response.json()

        completed: dict[str, Any] | None = None
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            if event_type == "response.completed" and isinstance(event.get("response"), dict):
                completed = event["response"]
            elif event_type == "response.output_text.delta" and isinstance(event.get("delta"), str):
                text_parts.append(event["delta"])
            elif event_type == "response.output_item.done" and isinstance(event.get("item"), dict):
                item = event["item"]
                if item.get("type") == "function_call":
                    tool_calls.append(item)

        if completed is not None and completed.get("output"):
            return completed
        output: list[dict[str, Any]] = []
        if text_parts:
            output.append({
                "type": "message",
                "content": [{"type": "output_text", "text": "".join(text_parts)}],
            })
        output.extend(tool_calls)
        payload = {"output": output}
        if completed is not None and completed.get("usage"):
            payload["usage"] = completed["usage"]
        return payload

    def _parse_response(self, payload: dict[str, Any]) -> AIMessage:
        tool_calls: list[dict[str, Any]] = []
        text_parts: list[str] = []

        for item in payload.get("output", []) or []:
            item_type = item.get("type")
            if item_type == "function_call":
                arguments = item.get("arguments") or "{}"
                try:
                    args = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError:
                    args = {"input": arguments}
                tool_calls.append({
                    "name": item.get("name", ""),
                    "args": args if isinstance(args, dict) else {"input": args},
                    "id": item.get("call_id") or item.get("id") or f"codex_call_{uuid.uuid4().hex}",
                    "type": "tool_call",
                })
            if item_type == "message":
                for content in item.get("content", []) or []:
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        text_parts.append(content["text"])

        if not text_parts and isinstance(payload.get("output_text"), str):
            text_parts.append(payload["output_text"])

        return AIMessage(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            usage_metadata=self._usage_metadata(payload),
        )

    def _usage_metadata(self, payload: dict[str, Any]) -> dict[str, int] | None:
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens) or 0
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }


def _codex_auth_headers(tokens) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {tokens.access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "codex_cli_rs/1.0.0 (TradingAgents)",
        "originator": "codex_cli_rs",
        "OpenAI-Beta": "responses=experimental",
    }
    if tokens.account_id:
        headers["ChatGPT-Account-ID"] = tokens.account_id
    return headers


def codex_models_to_options(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Convert Codex model-list payloads into questionary display/value pairs."""
    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for model in payload.get("models", []) or []:
        if not isinstance(model, dict):
            continue
        slug = model.get("slug")
        if not isinstance(slug, str) or not slug or slug in seen:
            continue
        if slug.startswith("codex-auto-"):
            continue
        display_name = model.get("display_name") or model.get("title") or slug
        if not isinstance(display_name, str) or not display_name:
            display_name = slug
        options.append((f"{display_name} - ChatGPT OAuth", slug))
        seen.add(slug)
    return options


def fetch_codex_model_options(
    base_url: str | None = None,
    timeout: float = 10,
) -> list[tuple[str, str]]:
    """Fetch currently available ChatGPT/Codex OAuth models for this account."""
    store = CodexOAuthStore()
    tokens = get_valid_tokens(store)
    endpoint = f"{(base_url or os.getenv('TRADINGAGENTS_CODEX_BASE_URL', CODEX_BASE_URL)).rstrip('/')}{CODEX_MODELS_PATH}"
    params = {
        "client_version": os.getenv("TRADINGAGENTS_CODEX_CLIENT_VERSION", CODEX_MODELS_CLIENT_VERSION),
    }
    response = requests.get(
        endpoint,
        params=params,
        headers=_codex_auth_headers(tokens),
        timeout=timeout,
    )
    if response.status_code == 401:
        refreshed = refresh_tokens(store.load().refresh_token)
        store.save(refreshed)
        response = requests.get(
            endpoint,
            params=params,
            headers=_codex_auth_headers(refreshed),
            timeout=timeout,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Codex OAuth model fetch failed: HTTP {response.status_code} {response.text}")
    return codex_models_to_options(response.json())


class CodexOAuthClient(BaseLLMClient):
    def get_llm(self) -> Any:
        return CodexOAuthChatModel(
            model_name=self.model,
            base_url=self.base_url or os.getenv("TRADINGAGENTS_CODEX_BASE_URL", CODEX_BASE_URL),
            timeout=float(self.kwargs.get("timeout", os.getenv("TRADINGAGENTS_CODEX_TIMEOUT", "300"))),
            reasoning_effort=self.kwargs.get("reasoning_effort", os.getenv("TRADINGAGENTS_CODEX_REASONING_EFFORT", "medium")),
            text_verbosity=self.kwargs.get("text_verbosity", os.getenv("TRADINGAGENTS_CODEX_TEXT_VERBOSITY", "medium")),
        )

    def validate_model(self) -> bool:
        return True


class CodexOAuthStructuredModel:
    """Small structured-output adapter for Pydantic schemas."""

    def __init__(self, llm: CodexOAuthChatModel, schema: type[PydanticBaseModel]):
        self.llm = llm
        self.schema = schema

    def invoke(self, input, config=None, **kwargs):
        messages = self.llm._convert_input(input).to_messages()
        instructions = self._structured_instructions()
        structured_messages = [SystemMessage(content=instructions), *messages]
        response = self.llm.invoke(structured_messages, config=config, **kwargs)
        parsed = self._extract_json(response.content)
        return self.schema.model_validate(parsed)

    def _structured_instructions(self) -> str:
        schema_json = json.dumps(self.schema.model_json_schema(), indent=2)
        return (
            "Return only a single valid JSON object that conforms to this JSON Schema. "
            "Do not include markdown fences, prose, comments, or extra keys.\n\n"
            f"{schema_json}"
        )

    def _extract_json(self, text: str) -> Any:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))
