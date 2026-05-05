from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _jsonable(value.dict())
    if hasattr(value, "content"):
        return {
            "type": value.__class__.__name__,
            "content": _jsonable(value.content),
        }
    return repr(value)


def _payload_hash(payload: Any) -> str:
    encoded = json.dumps(_jsonable(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_text(payload: Any) -> str:
    if payload is None:
        payload = ""
    if not isinstance(payload, str):
        payload = json.dumps(_jsonable(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _node_name(serialized: dict[str, Any], fallback: str) -> str:
    if isinstance(serialized.get("name"), str) and serialized["name"].strip():
        return serialized["name"].strip()
    ids = serialized.get("id")
    if isinstance(ids, list) and ids:
        tail = ids[-1]
        if isinstance(tail, str) and tail.strip():
            return tail.strip()
    if isinstance(ids, str) and ids.strip():
        return ids.strip()
    return fallback


def _provider_from_serialized(serialized: dict[str, Any], metadata: dict[str, Any] | None = None) -> str | None:
    metadata = metadata or {}
    for candidate in (
        metadata.get("provider"),
        serialized.get("provider"),
        serialized.get("type"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    ids = serialized.get("id")
    if isinstance(ids, list):
        for value in ids:
            if not isinstance(value, str):
                continue
            lower = value.lower()
            for provider in ("openai", "anthropic", "google", "ollama", "xai", "openrouter", "deepseek", "qwen", "glm"):
                if provider in lower:
                    return provider
    return None


def _model_from_serialized(serialized: dict[str, Any], metadata: dict[str, Any] | None = None) -> str | None:
    metadata = metadata or {}
    for candidate in (
        metadata.get("model"),
        metadata.get("model_name"),
        serialized.get("model"),
        serialized.get("model_name"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    kwargs = serialized.get("kwargs")
    if isinstance(kwargs, dict):
        for key in ("model", "model_name", "model_name_or_path"):
            candidate = kwargs.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _generation_text(generation: Any) -> str:
    if generation is None:
        return ""
    text = getattr(generation, "text", None)
    if isinstance(text, str):
        return text
    message = getattr(generation, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return json.dumps(_jsonable(content), sort_keys=True, ensure_ascii=False)
        if content is not None:
            return str(content)
    content = getattr(generation, "content", None)
    if isinstance(content, str):
        return content
    if content is not None:
        return str(content)
    return repr(generation)


def _response_text(response: Any) -> str:
    generations = getattr(response, "generations", None)
    if not generations:
        return ""
    chunks: list[str] = []
    for row in generations:
        if isinstance(row, list):
            chunks.extend(_generation_text(item) for item in row)
        else:
            chunks.append(_generation_text(row))
    return "\n".join(part for part in chunks if part)


def _usage_from_llm_output(llm_output: Any) -> dict[str, int | None]:
    usage: dict[str, int | None] = {"token_input": None, "token_output": None, "token_total": None}
    if not isinstance(llm_output, dict):
        return usage

    token_usage = llm_output.get("token_usage")
    if not isinstance(token_usage, dict):
        token_usage = llm_output.get("usage")
    if not isinstance(token_usage, dict):
        token_usage = llm_output.get("usage_metadata")
    if not isinstance(token_usage, dict):
        token_usage = {}

    input_keys = ("prompt_tokens", "input_tokens", "input", "tokens_in")
    output_keys = ("completion_tokens", "output_tokens", "completion", "tokens_out")
    total_keys = ("total_tokens", "token_total", "total")

    for key in input_keys:
        value = token_usage.get(key)
        if isinstance(value, int):
            usage["token_input"] = value
            break
    for key in output_keys:
        value = token_usage.get(key)
        if isinstance(value, int):
            usage["token_output"] = value
            break
    for key in total_keys:
        value = token_usage.get(key)
        if isinstance(value, int):
            usage["token_total"] = value
            break

    if usage["token_total"] is None and usage["token_input"] is not None and usage["token_output"] is not None:
        usage["token_total"] = int(usage["token_input"]) + int(usage["token_output"])

    return usage


class ToolProvenanceRecorder(BaseCallbackHandler):
    """Capture raw LangChain tool inputs and outputs for forensic run evidence."""

    def __init__(self, *, shadow_run_id: str | None = None) -> None:
        self.shadow_run_id = shadow_run_id
        self._starts: dict[str, dict[str, Any]] = {}
        self.records: list[dict[str, Any]] = []

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        started_at = _now_iso()
        self._starts[run_key] = {
            "run_id": run_key,
            "shadow_run_id": self.shadow_run_id,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tool_name": serialized.get("name") or serialized.get("id", ["unknown"])[-1],
            "serialized": _jsonable(serialized),
            "input": _jsonable(inputs if inputs is not None else input_str),
            "input_text": input_str,
            "tool_args_hash": _payload_hash(inputs if inputs is not None else input_str),
            "tags": tags or [],
            "metadata": _jsonable(metadata or {}),
            "started_at": started_at,
            "_started_monotonic_ns": time.monotonic_ns(),
        }

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish(
            run_id=run_id,
            parent_run_id=parent_run_id,
            status="succeeded",
            output=_jsonable(output),
            error=None,
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish(
            run_id=run_id,
            parent_run_id=parent_run_id,
            status="failed",
            output=None,
            error={"type": error.__class__.__name__, "message": str(error)},
        )

    def _finish(
        self,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        status: str,
        output: Any,
        error: dict[str, Any] | None,
    ) -> None:
        run_key = str(run_id)
        start = self._starts.pop(run_key, {})
        sequence = len(self.records) + 1
        output_hash = _payload_hash(output)
        started_at = start.get("started_at")
        ended_at = _now_iso()
        latency_ms = None
        if isinstance(start.get("_started_monotonic_ns"), int):
            latency_ms = int((time.monotonic_ns() - int(start["_started_monotonic_ns"])) / 1_000_000)
        record = {
            "source_id": f"RAW-TOOL-{sequence:04d}",
            "source_type": "raw_tool_output",
            "status": status,
            "tool_name": start.get("tool_name", "unknown"),
            "run_id": run_key,
            "shadow_run_id": start.get("shadow_run_id") or self.shadow_run_id,
            "parent_run_id": start.get("parent_run_id") or (str(parent_run_id) if parent_run_id else None),
            "started_at": started_at,
            "ended_at": ended_at,
            "latency_ms": latency_ms,
            "input": start.get("input"),
            "input_text": start.get("input_text"),
            "tool_args_hash": start.get("tool_args_hash"),
            "output": output,
            "output_sha256": output_hash,
            "response_hash": output_hash,
            "error": error,
            "tags": start.get("tags", []),
            "metadata": start.get("metadata", {}),
        }
        self.records.append(record)


class RunTelemetryRecorder(BaseCallbackHandler):
    """Capture replay-oriented LLM and tool telemetry for a shadow run."""

    def __init__(self, *, shadow_run_id: str | None = None) -> None:
        self.shadow_run_id = shadow_run_id
        self._starts: dict[str, dict[str, Any]] = {}
        self.records: list[dict[str, Any]] = []

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        prompt_text = "\n\n".join(prompts)
        self._starts[run_key] = {
            "event_type": "llm",
            "shadow_run_id": self.shadow_run_id,
            "callback_run_id": run_key,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "node_name": _node_name(serialized, "llm"),
            "serialized": _jsonable(serialized),
            "prompts": _jsonable(prompts),
            "prompt_text": prompt_text,
            "prompt_hash": _hash_text(prompt_text),
            "provider": _provider_from_serialized(serialized, metadata),
            "model": _model_from_serialized(serialized, metadata),
            "tags": tags or [],
            "metadata": _jsonable(metadata or {}),
            "started_at": _now_iso(),
            "_started_monotonic_ns": time.monotonic_ns(),
        }

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_llm(run_id=run_id, parent_run_id=parent_run_id, tags=tags, response=response, error=None)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_llm(
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            response=None,
            error={"type": error.__class__.__name__, "message": str(error)},
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        input_payload = inputs if inputs is not None else input_str
        self._starts[run_key] = {
            "event_type": "tool",
            "shadow_run_id": self.shadow_run_id,
            "callback_run_id": run_key,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "node_name": _node_name(serialized, "tool"),
            "tool_name": serialized.get("name") or serialized.get("id", ["unknown"])[-1],
            "serialized": _jsonable(serialized),
            "tool_args_text": _jsonable(input_payload),
            "tool_args_hash": _payload_hash(input_payload),
            "provider": _provider_from_serialized(serialized, metadata),
            "model": _model_from_serialized(serialized, metadata),
            "tags": tags or [],
            "metadata": _jsonable(metadata or {}),
            "started_at": _now_iso(),
            "_started_monotonic_ns": time.monotonic_ns(),
        }

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_tool(run_id=run_id, parent_run_id=parent_run_id, output=output, error=None)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_tool(
            run_id=run_id,
            parent_run_id=parent_run_id,
            output=None,
            error={"type": error.__class__.__name__, "message": str(error)},
        )

    def _finish_llm(
        self,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        tags: list[str] | None,
        response: Any,
        error: dict[str, Any] | None,
    ) -> None:
        run_key = str(run_id)
        start = self._starts.pop(run_key, {})
        response_text = _response_text(response) if response is not None else ""
        llm_output = getattr(response, "llm_output", None)
        usage = _usage_from_llm_output(llm_output)
        ended_at = _now_iso()
        latency_ms = None
        if isinstance(start.get("_started_monotonic_ns"), int):
            latency_ms = int((time.monotonic_ns() - int(start["_started_monotonic_ns"])) / 1_000_000)
        record = {
            **start,
            "event_type": "llm",
            "callback_run_id": run_key,
            "parent_run_id": start.get("parent_run_id") or (str(parent_run_id) if parent_run_id else None),
            "ended_at": ended_at,
            "latency_ms": latency_ms,
            "response_text": response_text,
            "response_hash": _hash_text(response_text),
            "llm_output": _jsonable(llm_output) if llm_output is not None else None,
            "token_input": usage["token_input"],
            "token_output": usage["token_output"],
            "token_total": usage["token_total"],
            "status": "failed" if error else "succeeded",
            "error": error,
            "tags": tags or start.get("tags", []),
        }
        self.records.append(record)

    def _finish_tool(
        self,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        output: Any,
        error: dict[str, Any] | None,
    ) -> None:
        run_key = str(run_id)
        start = self._starts.pop(run_key, {})
        output_text = _jsonable(output) if output is not None else ""
        ended_at = _now_iso()
        latency_ms = None
        if isinstance(start.get("_started_monotonic_ns"), int):
            latency_ms = int((time.monotonic_ns() - int(start["_started_monotonic_ns"])) / 1_000_000)
        record = {
            **start,
            "event_type": "tool",
            "callback_run_id": run_key,
            "parent_run_id": start.get("parent_run_id") or (str(parent_run_id) if parent_run_id else None),
            "ended_at": ended_at,
            "latency_ms": latency_ms,
            "response_text": output_text,
            "response_hash": _hash_text(output_text),
            "status": "failed" if error else "succeeded",
            "error": error,
            "tags": start.get("tags", []),
        }
        self.records.append(record)


def summarize_run_telemetry(records: list[dict[str, Any]]) -> dict[str, Any]:
    llm_records = [record for record in records if record.get("event_type") == "llm"]
    tool_records = [record for record in records if record.get("event_type") == "tool"]
    providers = sorted(
        {
            str(record.get("provider"))
            for record in records
            if record.get("provider")
        }
    )
    models = sorted(
        {
            str(record.get("model"))
            for record in records
            if record.get("model")
        }
    )
    token_input = sum(int(record.get("token_input") or 0) for record in llm_records)
    token_output = sum(int(record.get("token_output") or 0) for record in llm_records)
    token_total = sum(int(record.get("token_total") or 0) for record in llm_records)
    return {
        "shadow_run_id": next((record.get("shadow_run_id") for record in records if record.get("shadow_run_id")), None),
        "record_count": len(records),
        "llm_call_count": len(llm_records),
        "tool_call_count": len(tool_records),
        "providers": providers,
        "models": models,
        "token_input_total": token_input,
        "token_output_total": token_output,
        "token_total": token_total,
        "records": [
            {
                "event_type": record.get("event_type"),
                "node_name": record.get("node_name"),
                "tool_name": record.get("tool_name"),
                "status": record.get("status"),
                "prompt_hash": record.get("prompt_hash"),
                "response_hash": record.get("response_hash"),
                "tool_args_hash": record.get("tool_args_hash"),
                "latency_ms": record.get("latency_ms"),
                "provider": record.get("provider"),
                "model": record.get("model"),
                "token_input": record.get("token_input"),
                "token_output": record.get("token_output"),
                "token_total": record.get("token_total"),
            }
            for record in records
        ],
    }


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_jsonable(record), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_tool_provenance(
    records: list[dict[str, Any]],
    directory: Path,
    *,
    shadow_run_id: str | None = None,
) -> dict[str, Any] | None:
    if not records:
        return None

    directory.mkdir(parents=True, exist_ok=True)
    jsonl_path = directory / "raw_tool_outputs.jsonl"
    manifest_path = directory / "raw_tool_outputs_manifest.json"

    _write_jsonl(records, jsonl_path)

    manifest = {
        "kind": "raw_tool_outputs_manifest",
        "shadow_run_id": shadow_run_id or next((record.get("shadow_run_id") for record in records if record.get("shadow_run_id")), None),
        "record_count": len(records),
        "source_ids": [record["source_id"] for record in records],
        "tools": sorted({str(record.get("tool_name", "unknown")) for record in records}),
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": hashlib.sha256(jsonl_path.read_bytes()).hexdigest(),
        "created_at": _now_iso(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def write_run_telemetry(
    records: list[dict[str, Any]],
    directory: Path,
    *,
    shadow_run_id: str | None = None,
) -> dict[str, Any] | None:
    if not records:
        return None

    directory.mkdir(parents=True, exist_ok=True)
    jsonl_path = directory / "run_telemetry.jsonl"
    manifest_path = directory / "run_telemetry_manifest.json"

    _write_jsonl(records, jsonl_path)
    summary = summarize_run_telemetry(records)
    manifest = {
        "kind": "run_telemetry_manifest",
        "shadow_run_id": shadow_run_id or summary.get("shadow_run_id"),
        "record_count": summary["record_count"],
        "llm_call_count": summary["llm_call_count"],
        "tool_call_count": summary["tool_call_count"],
        "providers": summary["providers"],
        "models": summary["models"],
        "token_input_total": summary["token_input_total"],
        "token_output_total": summary["token_output_total"],
        "token_total": summary["token_total"],
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": hashlib.sha256(jsonl_path.read_bytes()).hexdigest(),
        "created_at": _now_iso(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
