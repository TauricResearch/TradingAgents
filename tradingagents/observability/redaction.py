"""One credential-key registry shared by persistence, hashing, logs, and HTTP."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV

REDACTED_VALUE = "[REDACTED]"
EXACT_CREDENTIAL_LEAVES = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "id_token",
        "bearer_token",
        "client_secret",
        "private_key",
        "aws_secret_access_key",
    }
)
SECRET_SUFFIXES = ("_api_key", "_token", "_secret", "_password", "_private_key")


def normalize_key_segment(segment: str) -> str:
    return re.sub(r"[-\s]+", "_", segment.strip().lower())


def split_normalized_key(raw_key: str) -> tuple[str, ...]:
    return tuple(normalize_key_segment(segment) for segment in raw_key.split("."))


def provider_credential_leaves() -> frozenset[str]:
    return frozenset(
        normalize_key_segment(name)
        for name in PROVIDER_API_KEY_ENV.values()
        if name
    )


def is_secret_leaf(
    leaf: str,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> bool:
    normalized = normalize_key_segment(leaf)
    exact = EXACT_CREDENTIAL_LEAVES | provider_credential_leaves() | frozenset(
        normalize_key_segment(name) for name in additional_credential_names
    )
    return normalized in exact or normalized.endswith(SECRET_SUFFIXES)


@dataclass(frozen=True)
class RedactionRecord:
    path: str
    normalized_leaf: str


@dataclass(frozen=True)
class RedactionResult:
    value: Any
    manifest: tuple[RedactionRecord, ...] = ()

    @property
    def redacted(self) -> bool:
        return bool(self.manifest)


def _declared_mapping(value: Any) -> Any:
    try:
        from langchain_core.messages import BaseMessage, message_to_dict

        if isinstance(value, BaseMessage):
            return message_to_dict(value)
    except ImportError:
        pass
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: getattr(value, item.name) for item in fields(value)}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="python")
    return value


def redact_recursive(
    value: Any,
    *,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> RedactionResult:
    """Redact credential-valued mapping leaves and return a normalized manifest."""
    records: list[RedactionRecord] = []

    def visit(current: Any, path: tuple[str, ...]) -> Any:
        current = _declared_mapping(current)
        if isinstance(current, Mapping):
            output = {}
            for raw_key, child in current.items():
                if isinstance(raw_key, str):
                    normalized_segments = split_normalized_key(raw_key)
                    child_path = (*path, *normalized_segments)
                    leaf = normalized_segments[-1]
                    if is_secret_leaf(leaf, additional_credential_names):
                        records.append(
                            RedactionRecord(".".join(child_path), leaf)
                        )
                        output[raw_key] = REDACTED_VALUE
                        continue
                else:
                    child_path = (*path, str(raw_key))
                output[raw_key] = visit(child, child_path)
            return output
        if isinstance(current, list):
            return [visit(child, (*path, str(index))) for index, child in enumerate(current)]
        if isinstance(current, tuple):
            return tuple(
                visit(child, (*path, str(index))) for index, child in enumerate(current)
            )
        if isinstance(current, set):
            return {visit(child, path) for child in current}
        if isinstance(current, frozenset):
            return frozenset(visit(child, path) for child in current)
        return current

    redacted = visit(value, ())
    manifest = tuple(
        sorted(
            set(records),
            key=lambda record: (record.path, record.normalized_leaf),
        )
    )
    return RedactionResult(redacted, manifest)


def remove_credentials_recursive(
    value: Any,
    *,
    additional_credential_names: tuple[str, ...] | frozenset[str] = (),
) -> RedactionResult:
    """Remove credential-named mapping leaves for resume fingerprinting."""
    records: list[RedactionRecord] = []

    def visit(current: Any, path: tuple[str, ...]) -> Any:
        current = _declared_mapping(current)
        if isinstance(current, Mapping):
            output = {}
            for raw_key, child in current.items():
                if isinstance(raw_key, str):
                    normalized_segments = split_normalized_key(raw_key)
                    child_path = (*path, *normalized_segments)
                    leaf = normalized_segments[-1]
                    if is_secret_leaf(leaf, additional_credential_names):
                        records.append(RedactionRecord(".".join(child_path), leaf))
                        continue
                else:
                    child_path = (*path, str(raw_key))
                output[raw_key] = visit(child, child_path)
            return output
        if isinstance(current, list):
            return [visit(child, (*path, str(index))) for index, child in enumerate(current)]
        if isinstance(current, tuple):
            return tuple(
                visit(child, (*path, str(index))) for index, child in enumerate(current)
            )
        return current

    stripped = visit(value, ())
    manifest = tuple(
        sorted(
            set(records),
            key=lambda record: (record.path, record.normalized_leaf),
        )
    )
    return RedactionResult(stripped, manifest)
