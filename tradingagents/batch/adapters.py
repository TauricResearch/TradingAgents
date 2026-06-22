from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

from langchain_core.messages import AIMessage, BaseMessage

from tradingagents.llm_clients.anthropic_client import NormalizedChatAnthropic
from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI


class BatchAdapterError(RuntimeError):
    """Raised when provider batch state cannot be created or parsed."""


def _json_loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _text_from_content_blocks(blocks: Any) -> str:
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            block_type = block.get("type")
            if block_type in {"text", "output_text"}:
                parts.append(str(block.get("text", "")))
    return "\n".join(part for part in parts if part)


class BaseBatchAdapter(ABC):
    provider: str
    endpoint: str

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def build_payload(
        self,
        *,
        model: str,
        messages: list[BaseMessage],
        request_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the provider-native request body for one non-streaming call."""

    @abstractmethod
    def line_for_request(self, custom_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Return one JSON-serializable batch input object."""

    @abstractmethod
    def submit_batch(
        self,
        *,
        model: str,
        lines: list[dict[str, Any]],
        input_path: Path,
    ) -> str:
        """Create a provider batch and return its provider batch id."""

    @abstractmethod
    def refresh_batch(self, batch_id: str) -> dict[str, Any]:
        """Return provider status metadata for an existing batch."""

    @abstractmethod
    def download_results(
        self,
        *,
        batch_id: str,
        output_path: Path,
        error_path: Path,
    ) -> dict[str, dict[str, Any]]:
        """Download completed results keyed by custom_id."""

    @abstractmethod
    def message_from_response(self, response_body: dict[str, Any]) -> AIMessage:
        """Convert a successful provider response body into an AIMessage."""

    @abstractmethod
    def structured_args_from_response(self, response_body: dict[str, Any]) -> dict[str, Any]:
        """Extract structured-output tool arguments from a provider response body."""


class OpenAIBatchAdapter(BaseBatchAdapter):
    provider = "openai"
    endpoint = "/v1/responses"

    def build_payload(
        self,
        *,
        model: str,
        messages: list[BaseMessage],
        request_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        llm_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": self.config.get("api_key") or os.environ.get("OPENAI_API_KEY") or "placeholder",
            "use_responses_api": True,
        }
        reasoning_effort = self.config.get("openai_reasoning_effort")
        if reasoning_effort:
            llm_kwargs["reasoning_effort"] = reasoning_effort
        temperature = self.config.get("temperature")
        if temperature not in (None, ""):
            llm_kwargs["temperature"] = float(temperature)
        llm = NormalizedChatOpenAI(**llm_kwargs)
        payload = llm._get_request_payload(messages, **request_kwargs)
        if payload.get("stream") is True:
            raise BatchAdapterError("OpenAI Batch does not support stream=true")
        payload.pop("stream", None)
        return payload

    def line_for_request(self, custom_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "custom_id": custom_id,
            "method": "POST",
            "url": self.endpoint,
            "body": payload,
        }

    def submit_batch(
        self,
        *,
        model: str,
        lines: list[dict[str, Any]],
        input_path: Path,
    ) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.config.get("api_key") or os.environ.get("OPENAI_API_KEY"))
        with input_path.open("rb") as handle:
            input_file = client.files.create(file=handle, purpose="batch")
        batch = client.batches.create(
            input_file_id=input_file.id,
            endpoint=self.endpoint,
            completion_window="24h",
            metadata={"tradingagents_model": model},
        )
        return batch.id

    def refresh_batch(self, batch_id: str) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=self.config.get("api_key") or os.environ.get("OPENAI_API_KEY"))
        batch = client.batches.retrieve(batch_id)
        return batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)

    def download_results(
        self,
        *,
        batch_id: str,
        output_path: Path,
        error_path: Path,
    ) -> dict[str, dict[str, Any]]:
        from openai import OpenAI

        client = OpenAI(api_key=self.config.get("api_key") or os.environ.get("OPENAI_API_KEY"))
        batch = client.batches.retrieve(batch_id)
        batch_data = batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)
        results: dict[str, dict[str, Any]] = {}

        output_file_id = batch_data.get("output_file_id")
        if output_file_id:
            text = client.files.content(output_file_id).text
            output_path.write_text(text, encoding="utf-8")
            for line in text.splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                results[item["custom_id"]] = item

        error_file_id = batch_data.get("error_file_id")
        if error_file_id:
            text = client.files.content(error_file_id).text
            error_path.write_text(text, encoding="utf-8")
            for line in text.splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                results[item["custom_id"]] = item

        return results

    def message_from_response(self, response_body: dict[str, Any]) -> AIMessage:
        if "choices" in response_body:
            message = response_body["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = []
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                tool_calls.append(
                    {
                        "id": call.get("id"),
                        "name": function.get("name"),
                        "args": _json_loads(function.get("arguments") or {}),
                    }
                )
            usage = response_body.get("usage") or {}
            return AIMessage(
                content=content,
                tool_calls=tool_calls,
                usage_metadata={
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            )

        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in response_body.get("output") or []:
            item_type = item.get("type")
            if item_type == "message":
                content_parts.append(_text_from_content_blocks(item.get("content")))
            elif item_type in {"function_call", "tool_call"}:
                tool_calls.append(
                    {
                        "id": item.get("call_id") or item.get("id"),
                        "name": item.get("name"),
                        "args": _json_loads(item.get("arguments") or {}),
                    }
                )
        usage = response_body.get("usage") or {}
        return AIMessage(
            content="\n".join(part for part in content_parts if part),
            tool_calls=tool_calls,
            usage_metadata={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        )

    def structured_args_from_response(self, response_body: dict[str, Any]) -> dict[str, Any]:
        message = self.message_from_response(response_body)
        if message.tool_calls:
            return dict(message.tool_calls[0].get("args") or {})
        text = message.content.strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1]
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise BatchAdapterError("structured response was not a JSON object")
        return parsed


class AnthropicBatchAdapter(BaseBatchAdapter):
    provider = "anthropic"
    endpoint = "/v1/messages/batches"

    def build_payload(
        self,
        *,
        model: str,
        messages: list[BaseMessage],
        request_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        llm_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or "placeholder",
        }
        effort = self.config.get("anthropic_effort")
        if effort:
            llm_kwargs["effort"] = effort
        temperature = self.config.get("temperature")
        if temperature not in (None, ""):
            llm_kwargs["temperature"] = float(temperature)
        llm = NormalizedChatAnthropic(**llm_kwargs)
        payload = llm._get_request_payload(messages, **request_kwargs)
        if payload.get("stream") is True:
            raise BatchAdapterError("Anthropic Message Batches do not support stream=true")
        payload.pop("stream", None)
        return payload

    def line_for_request(self, custom_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"custom_id": custom_id, "params": payload}

    def submit_batch(
        self,
        *,
        model: str,
        lines: list[dict[str, Any]],
        input_path: Path,
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        )
        batch = client.messages.batches.create(requests=lines)
        return batch.id

    def refresh_batch(self, batch_id: str) -> dict[str, Any]:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        )
        batch = client.messages.batches.retrieve(batch_id)
        return batch.model_dump() if hasattr(batch, "model_dump") else dict(batch)

    def download_results(
        self,
        *,
        batch_id: str,
        output_path: Path,
        error_path: Path,
    ) -> dict[str, dict[str, Any]]:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        )
        results: dict[str, dict[str, Any]] = {}
        with output_path.open("w", encoding="utf-8") as handle:
            for result in client.messages.batches.results(batch_id):
                raw = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                handle.write(json.dumps(raw) + "\n")
                results[raw["custom_id"]] = raw
        if not error_path.exists():
            error_path.write_text("", encoding="utf-8")
        return results

    def message_from_response(self, response_body: dict[str, Any]) -> AIMessage:
        content_blocks = response_body.get("content") or []
        tool_calls: list[dict[str, Any]] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "args": block.get("input") or {},
                    }
                )
        usage = response_body.get("usage") or {}
        input_tokens = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        return AIMessage(
            content=_text_from_content_blocks(content_blocks),
            tool_calls=tool_calls,
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )

    def structured_args_from_response(self, response_body: dict[str, Any]) -> dict[str, Any]:
        for block in response_body.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                value = block.get("input") or {}
                if isinstance(value, dict):
                    return value
        text = self.message_from_response(response_body).content.strip()
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise BatchAdapterError("structured response was not a JSON object")
        return parsed


def adapter_for_provider(provider: str, config: dict[str, Any]) -> BaseBatchAdapter:
    provider_key = provider.lower()
    if provider_key == "openai":
        return OpenAIBatchAdapter(config)
    if provider_key == "anthropic":
        return AnthropicBatchAdapter(config)
    raise BatchAdapterError(
        f"Batch mode supports only 'openai' and 'anthropic', not {provider!r}."
    )


def write_jsonl(path: Path, lines: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, separators=(",", ":")) + "\n")
