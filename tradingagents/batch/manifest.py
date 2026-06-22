from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.load import dumps, loads
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import convert_to_messages


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


def encode_state(state: dict[str, Any]) -> dict[str, Any]:
    encoded = dict(state)
    encoded["messages"] = json.loads(dumps(convert_to_messages(state.get("messages", []))))
    return encoded


def decode_state(state: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(state)
    messages_json = json.dumps(decoded.get("messages", []))
    decoded["messages"] = loads(
        messages_json,
        allowed_objects="messages",
        valid_namespaces=["langchain"],
    )
    return decoded


@dataclass
class BatchRequest:
    custom_id: str
    provider: str
    model: str
    ticker: str
    node: str
    call_index: int
    kind: str
    payload: dict[str, Any]
    status: str = "pending"  # pending|submitted|succeeded|errored|expired|canceled
    provider_batch_id: str | None = None
    response: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    schema_name: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass
class ProviderBatch:
    provider: str
    model: str
    endpoint: str
    batch_id: str | None
    status: str
    request_ids: list[str]
    input_path: str
    output_path: str | None = None
    error_path: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass
class BatchRunState:
    ticker: str
    trade_date: str
    asset_type: str
    state: dict[str, Any]
    progress: dict[str, Any]
    status: str = "running"  # running|waiting|completed|failed
    final_signal: str | None = None
    report_path: str | None = None
    error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        ticker: str,
        trade_date: str,
        asset_type: str,
        state: dict[str, Any],
    ) -> "BatchRunState":
        return cls(
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            state=encode_state(state),
            progress={
                "phase": "analyst",
                "analyst_index": 0,
                "active_node": None,
                "active_call_requests": [],
            },
        )

    def decoded_state(self) -> dict[str, Any]:
        return decode_state(self.state)

    def set_state(self, state: dict[str, Any]) -> None:
        self.state = encode_state(state)


@dataclass
class BatchManifest:
    run_id: str
    provider: str
    selected_analysts: list[str]
    config: dict[str, Any]
    runs: dict[str, BatchRunState]
    requests: dict[str, BatchRequest] = field(default_factory=dict)
    provider_batches: list[ProviderBatch] = field(default_factory=list)
    status: str = "running"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    @classmethod
    def new(
        cls,
        *,
        provider: str,
        selected_analysts: list[str],
        config: dict[str, Any],
        runs: dict[str, BatchRunState],
    ) -> "BatchManifest":
        return cls(
            run_id=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            + "-"
            + uuid.uuid4().hex[:8],
            provider=provider,
            selected_analysts=selected_analysts,
            config=config,
            runs=runs,
        )

    @property
    def pending_requests(self) -> list[BatchRequest]:
        return [request for request in self.requests.values() if request.status == "pending"]

    @property
    def unfinished_runs(self) -> list[BatchRunState]:
        return [run for run in self.runs.values() if run.status != "completed"]

    def touch(self) -> None:
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BatchManifest":
        runs = {
            ticker: BatchRunState(**run)
            for ticker, run in raw.get("runs", {}).items()
        }
        requests = {
            custom_id: BatchRequest(**request)
            for custom_id, request in raw.get("requests", {}).items()
        }
        provider_batches = [
            ProviderBatch(**batch) for batch in raw.get("provider_batches", [])
        ]
        return cls(
            run_id=raw["run_id"],
            provider=raw["provider"],
            selected_analysts=list(raw.get("selected_analysts", [])),
            config=dict(raw.get("config", {})),
            runs=runs,
            requests=requests,
            provider_batches=provider_batches,
            status=raw.get("status", "running"),
            created_at=raw.get("created_at", _utc_now()),
            updated_at=raw.get("updated_at", _utc_now()),
        )

    def save(self, root: Path) -> Path:
        run_dir = root / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.touch()
        path = run_dir / "manifest.json"
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=_json_default, sort_keys=True),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, root: Path, run_id: str) -> "BatchManifest":
        path = root / run_id / "manifest.json"
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def batch_root(config: dict[str, Any]) -> Path:
    return Path(config["data_cache_dir"]) / "batch"
