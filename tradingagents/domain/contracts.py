"""Shared behavior for versioned, immutable domain contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

_ANY_ADAPTER = TypeAdapter(Any)


def _reject_unordered_containers(value: Any, *, path: str = "$") -> None:
    if isinstance(value, (set, frozenset)):
        raise TypeError(f"unordered container is not canonical at {path}")
    if isinstance(value, BaseModel):
        _reject_unordered_containers(value.model_dump(mode="python"), path=path)
        return
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            _reject_unordered_containers(getattr(value, field.name), path=f"{path}.{field.name}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_unordered_containers(key, path=f"{path}.<key>")
            _reject_unordered_containers(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_unordered_containers(item, path=f"{path}[{index}]")


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible domain values deterministically."""
    _reject_unordered_containers(value)
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    else:
        value = _ANY_ADAPTER.dump_python(value, mode="json")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_id(prefix: str, value: Any) -> str:
    """Return a stable content-derived identifier for a canonical value."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


class ContractModel(BaseModel):
    """Base for newly versioned contracts crossing a system boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )

    schema_version: Literal[1] = 1

    def canonical_json(self) -> str:
        return canonical_json(self)

    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
